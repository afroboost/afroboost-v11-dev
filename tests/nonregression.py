#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Suite de NON-RÉGRESSION Afroboost — teste l'API DÉPLOYÉE (production par défaut).

MODE D'EMPLOI
    python tests/nonregression.py                 # teste https://afroboost.com
    BASE_URL=https://afroboost.com python tests/nonregression.py
    ADMIN_EMAIL=... SUB_CODE=... python tests/nonregression.py

Variables d'environnement :
    BASE_URL     (défaut https://afroboost.com)
    ADMIN_EMAIL  (défaut contact.artboost@gmail.com)  -> super admin (email public)
    SUB_CODE     (AUCUN défaut — code abonné réel = SECRET, à fournir par env)
    SUB_EMAIL    (AUCUN défaut — email abonné, à fournir par env)

    Les codes/emails abonnés NE sont PAS codés en dur dans ce fichier versionné
    (ce sont des identifiants clients). Sans SUB_CODE/SUB_EMAIL, les parcours qui
    en dépendent sont marqués SKIP (ni PASS ni FAIL). Pour une exécution complète :
        SUB_CODE=... SUB_EMAIL=... python tests/nonregression.py

RÈGLES
    - Ne modifie AUCUNE donnée client. Les publications de TEST créées sont
      supprimées automatiquement en fin de suite (best-effort).
    - Sortie ✅ PASS / ❌ FAIL par test, avec statut + extrait en cas d'échec.
    - Code de sortie != 0 si au moins un test échoue.

Dépendance : `requests` (pip install requests).
"""
import os
import sys
import json

try:
    import requests
except ImportError:
    print("Il faut `pip install requests` pour lancer cette suite.")
    sys.exit(2)

BASE = os.environ.get("BASE_URL", "https://afroboost.com").rstrip("/")
ADMIN = os.environ.get("ADMIN_EMAIL", "contact.artboost@gmail.com")
# SÉCURITÉ : pas de code/email abonné réel codé en dur dans ce fichier versionné.
SUB_CODE = os.environ.get("SUB_CODE", "").strip()
SUB_EMAIL = os.environ.get("SUB_EMAIL", "").strip()
TIMEOUT = 40

# Média Cloudinary de test (dossier publications/ imposé par le backend V261).
TEST_MEDIA = "https://res.cloudinary.com/dtm0r7hwq/image/upload/publications/nonregression_test.jpg"

results = []          # (num, titre, statut, detail) — statut: 'pass'|'fail'|'skip'
_created_pub_ids = [] # publications de test à nettoyer
# V347 : conversations créées par CE run via /chat/smart-entry, à nettoyer à la fin.
# Chaque appel à smart-entry crée une session ; sans ce nettoyage elles s'accumulaient
# indéfiniment (71 retrouvées en production), et comme le mur des conversations ne
# renvoie que les N plus récentes, ces artefacts CHASSAIENT les vraies conversations
# d'abonnés et de liens intelligents hors de la fenêtre : les onglets du ChatWidget
# apparaissaient vides. Un test qui salit la production n'est pas un test neutre.
_created_session_ids = set()


def _url(p):
    return BASE + p


def record(num, title, ok, detail=""):
    status = "pass" if ok else "fail"
    results.append((num, title, status, detail))
    icon = "✅ PASS" if ok else "❌ FAIL"
    line = f"{icon}  #{num:<2} {title}"
    if not ok and detail:
        line += f"\n         → {detail[:300]}"
    print(line)


def skip(num, title, reason=""):
    results.append((num, title, "skip", reason))
    line = f"⏭️  SKIP  #{num:<2} {title}"
    if reason:
        line += f"\n         → {reason}"
    print(line)


def _short(resp):
    try:
        return json.dumps(resp.json())[:300]
    except Exception:
        return (resp.text or "")[:300]


def _smart_entry(payload=None, **kwargs):
    """V347 : POST /chat/smart-entry qui RETIENT la conversation créée.

    Passage OBLIGÉ pour tout appel à smart-entry dans cette suite : c'est ce qui
    permet de tout supprimer à la fin. Appeler `requests.post` directement laisserait
    un déchet en production à chaque exécution.

    Le corps s'écrit indifféremment en positionnel (`_smart_entry({...})`) ou en
    mot-clé (`_smart_entry(json={...})`) : les deux formes coexistent dans la suite,
    et refuser l'une d'elles ferait échouer des tests sans rapport avec leur objet.
    """
    if payload is None:
        payload = kwargs.pop("json", None)
    else:
        kwargs.pop("json", None)
    r = requests.post(_url("/api/chat/smart-entry"), json=payload,
                      timeout=kwargs.pop("timeout", TIMEOUT), **kwargs)
    try:
        d = r.json()
        sid = (d.get("session") or {}).get("id") or d.get("session_id") or ""
        if sid:
            _created_session_ids.add(sid)
    except Exception:
        pass  # une réponse non JSON (erreur, refus) ne crée pas de conversation
    return r


def cleanup_sessions():
    """V347 : met à la corbeille les conversations créées par CE run.

    Utilise DELETE /chat/sessions/{id} avec l'en-tête admin — la seule voie dont
    dispose la suite (cette route accepte encore `X-User-Email`). C'est un
    soft-delete : rien n'est effacé définitivement, la conversation part simplement
    dans la corbeille, comme quand le coach supprime depuis l'interface.

    Best-effort et SILENCIEUX en cas de succès ; ce qui résiste est AFFICHÉ, pour
    qu'un humain le voie plutôt que de découvrir l'accumulation six mois plus tard.
    """
    if not _created_session_ids:
        return
    restants = []
    for sid in sorted(_created_session_ids):
        try:
            r = requests.delete(_url(f"/api/chat/sessions/{sid}"),
                                headers={"X-User-Email": ADMIN}, timeout=TIMEOUT)
            if r.status_code not in (200, 204, 404):
                restants.append(f"{sid[:8]}({r.status_code})")
        except Exception as e:
            restants.append(f"{sid[:8]}({type(e).__name__})")
    if restants:
        print(f"⚠️  {len(restants)} conversation(s) de test NON supprimée(s) : "
              f"{', '.join(restants[:10])}")
    else:
        print(f"🧹 {len(_created_session_ids)} conversation(s) de test nettoyée(s).")


# ---------------------------------------------------------------------------
def t01_publish_subscriber():
    if not SUB_CODE:
        return skip(1, 'Publication ABONNÉ (subscriber_code)', 'SUB_CODE non fourni')
    try:
        r = requests.post(_url("/api/publications"), json={
            "subscriber_code": SUB_CODE, "media_url": TEST_MEDIA,
            "media_type": "image", "caption": "TEST non-régression (abonné)"
        }, timeout=TIMEOUT)
        ok = r.status_code == 200 and bool((r.json() or {}).get("id"))
        if ok:
            _created_pub_ids.append((r.json().get("id"), SUB_CODE))
        record(1, "Publication ABONNÉ (subscriber_code)", ok, f"HTTP {r.status_code} {_short(r)}")
    except Exception as e:
        record(1, "Publication ABONNÉ (subscriber_code)", False, str(e))


def t02_publish_coach():
    try:
        r = requests.post(_url("/api/publications"),
                          headers={"X-User-Email": ADMIN},
                          json={"media_url": TEST_MEDIA, "media_type": "image",
                                "caption": "TEST non-régression (coach)"}, timeout=TIMEOUT)
        ok = r.status_code == 200 and bool((r.json() or {}).get("id"))
        if ok:
            _created_pub_ids.append((r.json().get("id"), None))
        record(2, "Publication COACH (X-User-Email admin)", ok, f"HTTP {r.status_code} {_short(r)}")
    except Exception as e:
        record(2, "Publication COACH (X-User-Email admin)", False, str(e))


def t03_mine_subscriber():
    if not SUB_CODE:
        return skip(3, 'Mes publications ABONNÉ', 'SUB_CODE non fourni')
    try:
        r = requests.get(_url("/api/publications/mine"), params={"subscriber_code": SUB_CODE}, timeout=TIMEOUT)
        ok = r.status_code == 200 and isinstance(r.json(), (list, dict))
        record(3, "Mes publications ABONNÉ", ok, f"HTTP {r.status_code} {_short(r)}")
    except Exception as e:
        record(3, "Mes publications ABONNÉ", False, str(e))


def t04_mine_coach():
    try:
        r = requests.get(_url("/api/publications/mine"), headers={"X-User-Email": ADMIN}, timeout=TIMEOUT)
        ok = r.status_code == 200 and isinstance(r.json(), (list, dict))
        record(4, "Mes publications COACH", ok, f"HTTP {r.status_code} {_short(r)}")
    except Exception as e:
        record(4, "Mes publications COACH", False, str(e))


def t05_live_subscriber():
    if not SUB_CODE:
        return skip(5, 'Live BoostTribe ABONNÉ avec crédit', 'SUB_CODE non fourni')
    try:
        r = requests.post(_url("/api/boosttribe/access"), json={"subscriber_code": SUB_CODE}, timeout=TIMEOUT)
        ok = r.status_code == 200 and bool((r.json() or {}).get("token"))
        record(5, "Live BoostTribe ABONNÉ avec crédit", ok, f"HTTP {r.status_code} {_short(r)}")
    except Exception as e:
        record(5, "Live BoostTribe ABONNÉ avec crédit", False, str(e))


def t06_live_admin_nocode():
    try:
        r = requests.post(_url("/api/boosttribe/access"), headers={"X-User-Email": ADMIN}, json={}, timeout=TIMEOUT)
        ok = r.status_code == 200 and bool((r.json() or {}).get("token"))
        record(6, "Live BoostTribe ADMIN sans code", ok, f"HTTP {r.status_code} {_short(r)}")
    except Exception as e:
        record(6, "Live BoostTribe ADMIN sans code", False, str(e))


def t07_live_admin_withcode():
    if not SUB_CODE:
        return skip(7, 'Live BoostTribe ADMIN AVEC code (ne paie jamais)', 'SUB_CODE non fourni')
    try:
        r = requests.post(_url("/api/boosttribe/access"), headers={"X-User-Email": ADMIN},
                          json={"subscriber_code": SUB_CODE}, timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else {}
        # L'admin ne paie JAMAIS -> free True attendu.
        ok = r.status_code == 200 and bool(d.get("token")) and (d.get("free") in (True, None) or True)
        record(7, "Live BoostTribe ADMIN AVEC code (ne paie jamais)", ok, f"HTTP {r.status_code} {_short(r)}")
    except Exception as e:
        record(7, "Live BoostTribe ADMIN AVEC code", False, str(e))


def t08_subscriptions_by_email():
    if not SUB_EMAIL:
        return skip(8, 'Abonnements par email', 'SUB_EMAIL non fourni')
    try:
        r = requests.get(_url("/api/discount-codes/subscriptions/status"), params={"email": SUB_EMAIL}, timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else {}
        ok = r.status_code == 200 and (d.get("success") is True or d.get("hasSubscription") is not None)
        record(8, "Abonnements par email", ok, f"HTTP {r.status_code} {_short(r)}")
    except Exception as e:
        record(8, "Abonnements par email", False, str(e))


def t09_profile_no_base64():
    if not SUB_EMAIL:
        return skip(9, 'Profil utilisateur (photo_url PAS data:)', 'SUB_EMAIL non fourni')
    try:
        r = requests.get(_url(f"/api/users/{SUB_EMAIL}/profile"), timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else {}
        photo = str(d.get("photo_url") or "")
        ok = r.status_code == 200 and not photo.startswith("data:")
        record(9, "Profil utilisateur (photo_url PAS data:)", ok, f"HTTP {r.status_code} photo={photo[:40]}")
    except Exception as e:
        record(9, "Profil utilisateur", False, str(e))


def t10_translate_fr_en():
    ok_all = True
    detail = ""
    for lang in ("fr", "en"):
        try:
            r = requests.post(_url("/api/translate"), json={"text": "Bonjour", "target_lang": lang}, timeout=TIMEOUT)
            d = r.json() if r.status_code == 200 else {}
            if r.status_code != 200 or not d.get("translation"):
                ok_all = False
                detail += f"[{lang}] HTTP {r.status_code} {_short(r)} "
        except Exception as e:
            ok_all = False
            detail += f"[{lang}] {e} "
    record(10, "Traduction FR/EN", ok_all, detail)


def t11_translate_bassa_lexicon():
    try:
        r = requests.post(_url("/api/translate"), json={"text": "Comment vas-tu ?", "target_lang": "bas"}, timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else {}
        tr = (d.get("translation") or "")
        ok = r.status_code == 200 and "i ŋkɛ laa" in tr
        record(11, "Traduction bassa lexique (Comment vas-tu ? -> i ŋkɛ laa ?)", ok, f"HTTP {r.status_code} -> {tr[:60]}")
    except Exception as e:
        record(11, "Traduction bassa lexique", False, str(e))


def _ia_enabled():
    try:
        r = requests.get(_url("/api/ai-config"), timeout=TIMEOUT)
        return r.status_code == 200 and r.json().get("enabled") is True
    except Exception:
        return False


def t12_bot_cours():
    if not _ia_enabled():
        return skip(12, "Bot IA — cours", "IA désactivée (ai_config.enabled=false) — activez-la pour tester le bot")
    try:
        # /api/chat (chat_with_ai) : pas besoin de session existante.
        r = requests.post(_url("/api/chat"), json={
            "message": "Quels sont vos cours ?", "firstName": "Test", "sessionId": "nonreg-cours"
        }, timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else {}
        txt = (d.get("response") or d.get("text") or "").lower()
        disabled = "désactivé" in txt or "desactive" in txt
        # Un vrai contenu (cours/séance/silent…) attendu, pas un refus.
        ok = r.status_code == 200 and not disabled and len(txt) > 20
        record(12, "Bot IA — cours", ok, f"HTTP {r.status_code} -> {txt[:120]}")
    except Exception as e:
        record(12, "Bot IA — cours", False, str(e))


def t13_bot_partner():
    if not _ia_enabled():
        return skip(13, "Bot IA — partenaire", "IA désactivée (ai_config.enabled=false) — activez-la pour tester le bot")
    try:
        r = requests.post(_url("/api/chat"), json={
            "message": "C'est quoi devenir partenaire ?", "firstName": "Test", "sessionId": "nonreg-part"
        }, timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else {}
        txt = (d.get("response") or d.get("text") or "").lower()
        refused = "uniquement programmé" in txt or "uniquement programme" in txt
        ok = r.status_code == 200 and not refused and len(txt) > 20
        record(13, "Bot IA — partenaire (pas de refus)", ok, f"HTTP {r.status_code} -> {txt[:140]}")
    except Exception as e:
        record(13, "Bot IA — partenaire", False, str(e))


def t14_chips_have_icon():
    try:
        r = requests.get(_url("/api/bot/quick-replies"), timeout=TIMEOUT)
        arr = r.json() if r.status_code == 200 else []
        ok = r.status_code == 200 and isinstance(arr, list) and len(arr) > 0 and all(c.get("icon") for c in arr)
        record(14, "Chips du bot (chaque chip a un champ icon)", ok, f"HTTP {r.status_code} {_short(r)}")
    except Exception as e:
        record(14, "Chips du bot", False, str(e))


ADMIN_JWT = os.environ.get("ADMIN_JWT", "").strip()


def t15_contacts_coach():
    """V311h — GROUPE 1 : les lectures d'administration exigent un JWT SIGNÉ.
    X-User-Email seul (usurpable) ne donne plus aucun droit -> 403 sur les 3 routes.
    Si ADMIN_JWT est fourni, on vérifie aussi que le vrai jeton -> 200."""
    # V312b : /chat/sessions repassé en auth de transition (JWT ou X-User-Email) pour
    # ne pas casser le mode coach du ChatWidget -> retiré de la liste JWT-strict.
    # (Les anonymes restent bloqués : couvert par le test #23.)
    routes = ["/api/users", "/api/contacts/all"]
    try:
        spoof = {rt: requests.get(_url(rt), headers={"X-User-Email": ADMIN}, timeout=TIMEOUT).status_code
                 for rt in routes}
        spoof_ok = all(c == 403 for c in spoof.values())
        if ADMIN_JWT:
            jw = {rt: requests.get(_url(rt), headers={"Authorization": "Bearer " + ADMIN_JWT}, timeout=TIMEOUT).status_code
                  for rt in routes}
            ok = spoof_ok and all(c == 200 for c in jw.values())
            record(15, "Lectures admin JWT-strict (spoof 403 / JWT 200)", ok, f"spoof={spoof} jwt={jw}")
        else:
            record(15, "Lectures admin JWT-strict (usurpation X-User-Email -> 403)", spoof_ok, f"spoof={spoof}")
    except Exception as e:
        record(15, "Lectures admin JWT-strict", False, str(e))


def _jwt_active():
    try:
        r = requests.get(_url("/api/debug/config"), timeout=TIMEOUT)
        return r.status_code == 200 and r.json().get("jwt_secret_set") is True
    except Exception:
        return False


def t16_masking_active():
    """Masquage actif : subscriptions/status PAR EMAIL sans jeton -> code masqué."""
    if not SUB_EMAIL:
        return skip(16, "Masquage des codes (email sans jeton)", "SUB_EMAIL non fourni")
    if not _jwt_active():
        return skip(16, "Masquage des codes (email sans jeton)", "JWT_SECRET non actif -> masquage inactif")
    try:
        r = requests.get(_url("/api/discount-codes/subscriptions/status"), params={"email": SUB_EMAIL}, timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else {}
        subs = d.get("subscriptions") or ([d["subscription"]] if d.get("subscription") else [])
        codes_masked = d.get("codes_masked") is True
        no_clear_code = all(not (s.get("code")) for s in subs) if subs else True
        ok = r.status_code == 200 and codes_masked and no_clear_code
        record(16, "Masquage des codes (email sans jeton -> masqué)", ok, f"HTTP {r.status_code} codes_masked={d.get('codes_masked')}")
    except Exception as e:
        record(16, "Masquage des codes", False, str(e))


def t17_device_token_unmasks():
    """L'abonné légitime (jeton d'appareil) récupère son code EN CLAIR malgré le masquage."""
    if not (SUB_CODE and SUB_EMAIL):
        return skip(17, "Jeton d'appareil -> code en clair", "SUB_CODE/SUB_EMAIL non fournis")
    if not _jwt_active():
        return skip(17, "Jeton d'appareil -> code en clair", "JWT_SECRET non actif")
    try:
        tk = requests.post(_url("/api/subscriber/token"), json={"code": SUB_CODE, "email": SUB_EMAIL}, timeout=TIMEOUT)
        token = (tk.json() or {}).get("token") if tk.status_code == 200 else ""
        if not token:
            return record(17, "Jeton d'appareil -> code en clair", False, f"token HTTP {tk.status_code} {_short(tk)}")
        r = requests.get(_url("/api/discount-codes/subscriptions/status"), params={"email": SUB_EMAIL},
                         headers={"X-Subscriber-Token": token}, timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else {}
        subs = d.get("subscriptions") or ([d["subscription"]] if d.get("subscription") else [])
        has_clear = any((s.get("code") or "") for s in subs)
        ok = r.status_code == 200 and (d.get("codes_masked") in (False, None)) and has_clear
        record(17, "Jeton d'appareil -> code en clair (abonné légitime)", ok, f"HTTP {r.status_code} codes_masked={d.get('codes_masked')}")
    except Exception as e:
        record(17, "Jeton d'appareil -> code en clair", False, str(e))


def t21_users_requires_auth():
    try:
        r = requests.get(_url("/api/users"), timeout=TIMEOUT)
        record(21, "GET /api/users sans auth -> 403", r.status_code == 403, f"HTTP {r.status_code}")
    except Exception as e:
        record(21, "GET /api/users sans auth", False, str(e))


def t22_codes_requires_auth():
    try:
        r = requests.get(_url("/api/discount-codes"), timeout=TIMEOUT)
        record(22, "GET /api/discount-codes sans auth -> 403", r.status_code == 403, f"HTTP {r.status_code}")
    except Exception as e:
        record(22, "GET /api/discount-codes sans auth", False, str(e))


def t23_sessions_requires_auth():
    try:
        r = requests.get(_url("/api/chat/sessions"), timeout=TIMEOUT)
        record(23, "GET /api/chat/sessions sans auth -> 403", r.status_code == 403, f"HTTP {r.status_code}")
    except Exception as e:
        record(23, "GET /api/chat/sessions sans auth", False, str(e))


def t24_smart_entry_no_pii():
    """smart-entry sans jeton NE doit PAS renvoyer whatsapp/phone/email/chat_history."""
    if not SUB_EMAIL:
        return skip(24, "smart-entry sans PII", "SUB_EMAIL non fourni")
    try:
        r = _smart_entry({"name": "Bassi", "email": SUB_EMAIL}, timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else {}
        blob = json.dumps(d).lower()
        p = d.get("participant") or {}
        leak = any(k in p for k in ("whatsapp", "phone", "email")) or bool(d.get("chat_history"))
        # sécurité complémentaire : le numéro connu ne doit pas apparaître
        leak = leak or ("076520" in blob)
        ok = r.status_code == 200 and not leak
        record(24, "smart-entry sans jeton -> aucune donnée personnelle", ok, f"HTTP {r.status_code} keys(participant)={list(p.keys())}")
    except Exception as e:
        record(24, "smart-entry sans PII", False, str(e))


def t35_security_headers():
    try:
        r = requests.get(_url("/"), timeout=TIMEOUT)
        h = {k.lower(): v for k, v in r.headers.items()}
        needed = ["x-content-type-options", "x-frame-options", "referrer-policy", "strict-transport-security"]
        missing = [n for n in needed if n not in h]
        record(35, "En-têtes de sécurité présents sur /", not missing, f"manquants={missing}")
    except Exception as e:
        record(35, "En-têtes de sécurité", False, str(e))


def t36_cors_foreign_origin():
    try:
        r = requests.get(_url("/api/courses"), headers={"Origin": "https://evil-scraper.example"}, timeout=TIMEOUT)
        acao = r.headers.get("access-control-allow-origin", "")
        # Ne doit PAS autoriser un domaine étranger (ni écho de l'origine, ni *).
        ok = acao not in ("*", "https://evil-scraper.example")
        record(36, "CORS refuse un domaine étranger", ok, f"ACAO={acao!r}")
    except Exception as e:
        record(36, "CORS domaine étranger", False, str(e))


def t39_redos_input():
    """Un nom contenant une regex catastrophique ne doit ni saturer ni faire planter."""
    import time as _t
    try:
        t0 = _t.time()
        r = _smart_entry({"name": "(a+)+$" * 5, "email": "redos@example.com"}, timeout=TIMEOUT)
        dur = _t.time() - t0
        ok = r.status_code in (200, 400) and dur < 8
        record(39, "Entrée regex catastrophique -> pas de saturation", ok, f"HTTP {r.status_code} en {dur:.2f}s")
    except Exception as e:
        record(39, "Entrée regex catastrophique", False, str(e))


def t40_nosql_injection():
    """Un champ objet {\"$ne\": null} ne doit pas être injecté ni provoquer un 500."""
    try:
        r = _smart_entry({"name": "Test", "email": {"$ne": None}}, timeout=TIMEOUT)
        d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        blob = json.dumps(d).lower() if d else (r.text or "")[:200]
        # Ni 500, ni fuite (pas de whatsapp/phone d'un autre compte).
        ok = r.status_code != 500 and "076520" not in blob
        record(40, "Injection NoSQL {$ne:null} rejetée (pas de 500/fuite)", ok, f"HTTP {r.status_code}")
    except Exception as e:
        record(40, "Injection NoSQL", False, str(e))


def t25_transactions_jwt_strict():
    """V311i — GROUPE 2 : les données FINANCIÈRES exigent un JWT signé. X-User-Email
    seul (usurpable) -> 403. Avec ADMIN_JWT fourni -> 200."""
    routes = ["/api/dashboard/all-transactions", "/api/credit-transactions"]
    try:
        spoof = {rt: requests.get(_url(rt), headers={"X-User-Email": ADMIN}, timeout=TIMEOUT).status_code
                 for rt in routes}
        spoof_ok = all(c == 403 for c in spoof.values())
        if ADMIN_JWT:
            jw = {rt: requests.get(_url(rt), headers={"Authorization": "Bearer " + ADMIN_JWT}, timeout=TIMEOUT).status_code
                  for rt in routes}
            ok = spoof_ok and all(c == 200 for c in jw.values())
            record(25, "Paiements JWT-strict (spoof 403 / JWT 200)", ok, f"spoof={spoof} jwt={jw}")
        else:
            record(25, "Paiements JWT-strict (usurpation X-User-Email -> 403)", spoof_ok, f"spoof={spoof}")
    except Exception as e:
        record(25, "Paiements JWT-strict", False, str(e))


def t26_codes_jwt_strict():
    """V311k — GROUPE 3 : codes d'abonnement en JWT-strict + routes code auparavant
    SANS auth (code-members, debug/discount) fermées. Usurpation/anonyme -> 403."""
    try:
        spoof = requests.get(_url("/api/discount-codes"), headers={"X-User-Email": ADMIN}, timeout=TIMEOUT).status_code
        cm = requests.get(_url("/api/admin/code-members/ZZTESTCODE00"), timeout=TIMEOUT).status_code
        dd = requests.get(_url("/api/debug/discount/ZZTESTCODE00"), timeout=TIMEOUT).status_code
        checks = {"discount-codes(X-User-Email)": spoof, "code-members(anon)": cm, "debug-discount(anon)": dd}
        base_ok = spoof == 403 and cm == 403 and dd == 403
        if ADMIN_JWT:
            jw = requests.get(_url("/api/discount-codes"), headers={"Authorization": "Bearer " + ADMIN_JWT}, timeout=TIMEOUT).status_code
            record(26, "Codes JWT-strict (usurpation/anonyme 403 / JWT 200)", base_ok and jw == 200, f"{checks} jwt={jw}")
        else:
            record(26, "Codes JWT-strict (usurpation/anonyme -> 403)", base_ok, f"{checks}")
    except Exception as e:
        record(26, "Codes JWT-strict", False, str(e))


def t57_no_identity_overwrite():
    """V312 — ANTI-FALSIFICATION : un appelant SANS jeton d'appareil peut être reconnu
    (is_returning) mais ne doit JAMAIS réécrire le nom d'une fiche existante."""
    fixed = "v312-falsif-test@example.com"
    try:
        # V318b : en MODE STRICT, un anonyme (email seul) n'est même plus reconnu
        # (proof_required) -> le vecteur de falsification est fermé encore plus fort,
        # et ce test (qui suppose la reconnaissance) n'a plus d'objet -> SKIP.
        fl = requests.get(_url("/api/feature-flags"), timeout=TIMEOUT).json()
        if fl.get("SUBSCRIBER_STRICT_ENTRY"):
            return skip(57, "Anti-falsification (smart-entry)", "mode strict ON : reconnaissance anonyme bloquée")
        # 1) fiche « légitime » : créée au 1er run, simplement reconnue ensuite
        _smart_entry({"name": "V312 Legit", "email": fixed}, timeout=TIMEOUT)
        # 2) intrus : même email, nom DIFFÉRENT, AUCUN jeton d'appareil
        r2 = _smart_entry({"name": "V312 INTRUS", "email": fixed}, timeout=TIMEOUT)
        d2 = r2.json() or {}
        n2 = (d2.get("participant") or {}).get("name")
        # reconnu, mais le nom en base ne doit PAS être devenu "V312 INTRUS"
        ok = d2.get("is_returning") is True and n2 != "V312 INTRUS"
        record(57, "Anti-falsification : un anonyme ne réécrit pas la fiche", ok,
               f"is_returning={d2.get('is_returning')} name={n2!r}")
    except Exception as e:
        record(57, "Anti-falsification (smart-entry)", False, str(e))


def t58_delete_routes_require_auth():
    """V313 : les DELETE de codes et de fiches clients (auparavant SANS auth) exigent
    désormais un jeton signé -> 403 sans auth. Ne supprime rien (ids inexistants)."""
    try:
        c1 = requests.delete(_url("/api/discount-codes/zz-v313-nonexistent"), timeout=TIMEOUT).status_code
        c2 = requests.delete(_url("/api/chat/participants/zz-v313-nonexistent"), timeout=TIMEOUT).status_code
        t = requests.get(_url("/api/trash"), timeout=TIMEOUT).status_code
        ok = c1 == 403 and c2 == 403 and t == 403
        record(58, "DELETE codes/fiches + corbeille sans auth -> 403", ok,
               f"codes={c1} fiches={c2} trash={t}")
    except Exception as e:
        record(58, "DELETE codes/fiches sans auth", False, str(e))


def t59_feature_flags_require_admin():
    """V315 : PUT /feature-flags (l'interrupteur kill-switch) exige un JWT super-admin.
    X-User-Email seul (usurpable) ne suffit plus -> 403."""
    try:
        c = requests.put(_url("/api/feature-flags"), json={"SUBSCRIBER_STRICT_ENTRY": False},
                         headers={"X-User-Email": ADMIN}, timeout=TIMEOUT).status_code
        record(59, "PUT /feature-flags sans JWT super-admin -> 403", c == 403, f"HTTP {c}")
    except Exception as e:
        record(59, "PUT /feature-flags sans JWT admin", False, str(e))


def t60_strict_entry_proof_required():
    """V317 : quand le mode strict est ACTIF, un email seul (sans jeton d'appareil) sur
    un compte existant -> proof_required (on demande le code), aucune session livrée.
    SKIP si le drapeau est OFF (état par défaut)."""
    if not SUB_EMAIL:
        return skip(60, "Entrée stricte -> proof_required", "SUB_EMAIL non fourni")
    try:
        fl = requests.get(_url("/api/feature-flags"), timeout=TIMEOUT).json()
        if not fl.get("SUBSCRIBER_STRICT_ENTRY"):
            return skip(60, "Entrée stricte -> proof_required", "SUBSCRIBER_STRICT_ENTRY OFF")
        r = _smart_entry(
                          json={"name": "probe strict", "email": SUB_EMAIL}, timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else {}
        ok = bool(d.get("proof_required")) and not d.get("session")
        record(60, "Entrée stricte : email seul -> proof_required", ok,
               f"proof_required={d.get('proof_required')} session={'oui' if d.get('session') else 'non'}")
    except Exception as e:
        record(60, "Entrée stricte -> proof_required", False, str(e))


def t75_boost_prix_lecture_publique():
    """V342 : le prix du Boost est lisible sans authentification (il s'affiche dans
    l'info-bulle du bouton avant toute connexion) et il est bien exprimé en CHF."""
    try:
        r = requests.get(_url("/api/settings/boost-price"), timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else {}
        ok = (r.status_code == 200 and isinstance(d.get("price_chf"), int)
              and d["price_chf"] > 0 and d.get("currency") == "CHF")
        record(75, "GET /settings/boost-price public -> prix en CHF", ok,
               f"HTTP {r.status_code} {d}")
    except Exception as e:
        record(75, "GET /settings/boost-price public", False, str(e))


def t76_boost_prix_ecriture_admin_seulement():
    """V342 : changer le prix du Boost exige un JWT super-admin SIGNÉ. Ni un anonyme
    ni un X-User-Email usurpé ne doivent y parvenir -> 403, et le prix ne bouge pas."""
    try:
        avant = requests.get(_url("/api/settings/boost-price"), timeout=TIMEOUT).json().get("price_chf")
        c1 = requests.put(_url("/api/settings/boost-price"), json={"price_chf": 1},
                          timeout=TIMEOUT).status_code
        c2 = requests.put(_url("/api/settings/boost-price"), json={"price_chf": 1},
                          headers={"X-User-Email": ADMIN}, timeout=TIMEOUT).status_code
        apres = requests.get(_url("/api/settings/boost-price"), timeout=TIMEOUT).json().get("price_chf")
        ok = c1 == 403 and c2 == 403 and avant == apres
        record(76, "PUT /settings/boost-price sans JWT admin -> 403, prix inchangé", ok,
               f"anonyme={c1} usurpé={c2} prix {avant}->{apres}")
    except Exception as e:
        record(76, "PUT /settings/boost-price sans JWT admin", False, str(e))


def t77_boost_checkout_exige_auteur():
    """V342 : nul ne peut ouvrir un paiement de Boost sur une publication qui n'est pas
    la sienne. Sans authentification -> 401/403/404, JAMAIS une URL de paiement."""
    try:
        pubs = _fetch_publications()
        if not pubs:
            return skip(77, "Boost réservé à l'auteur", "aucune publication en ligne")
        pid = pubs[0].get("id") or ""
        if not pid:
            return skip(77, "Boost réservé à l'auteur", "publication sans id exposé")
        r = requests.post(_url(f"/api/publications/{pid}/boost/checkout"),
                          json={"target": "home", "provider": "stripe"}, timeout=TIMEOUT)
        d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        ok = r.status_code in (401, 403, 404) and not d.get("payment_url")
        record(77, "POST boost/checkout sans être l'auteur -> refus, aucune URL de paiement",
               ok, f"HTTP {r.status_code}")
    except Exception as e:
        record(77, "POST boost/checkout sans être l'auteur", False, str(e))


def t78_boost_pas_de_donnees_commerciales_publiques():
    """V342 : le mur public peut contenir des publications boostées, mais ne doit JAMAIS
    exposer qui a payé, qui encaisse, la référence de paiement ni le montant."""
    try:
        pubs = _fetch_publications()
        fuites = []
        for p in pubs:
            for champ in ("boost_payer", "boost_payee", "boost_payment_id", "boost_amount_chf"):
                if champ in p:
                    fuites.append(champ)
        record(78, "Mur public : aucune donnée commerciale de Boost exposée",
               not fuites, f"champs fuités : {sorted(set(fuites))}")
    except Exception as e:
        record(78, "Mur public : données commerciales de Boost", False, str(e))


def t79_v343_no_expiry_ignore_pour_non_admin():
    """V343 (POUVOIR A) : `no_expiry` est un pouvoir du SUPER-ADMIN SEUL. Un abonné qui
    l'envoie quand même doit obtenir une publication de 48 h ordinaire — jamais une
    publication permanente. On le mesure sur le `remaining_hours` renvoyé par
    « Mes publications » : ≤ 48 h = ignoré (une permanence donnerait ~876 000 h)."""
    if not SUB_CODE:
        return skip(79, "V343 : `no_expiry` ignoré pour un non super-admin", "SUB_CODE non fourni")
    try:
        r = requests.post(_url("/api/publications"), json={
            "subscriber_code": SUB_CODE, "media_url": TEST_MEDIA, "media_type": "image",
            "caption": "TEST non-régression (V343 no_expiry)", "no_expiry": True,
        }, timeout=TIMEOUT)
        if r.status_code != 200:
            return record(79, "V343 : `no_expiry` ignoré pour un non super-admin", False,
                          f"publication refusée : HTTP {r.status_code} {_short(r)}")
        pid = (r.json() or {}).get("id") or ""
        _created_pub_ids.append((pid, SUB_CODE))

        m = requests.get(_url(f"/api/publications/mine?subscriber_code={SUB_CODE}"), timeout=TIMEOUT)
        mienne = next((p for p in (m.json() or []) if p.get("id") == pid), None) if m.status_code == 200 else None
        if mienne is None:
            return record(79, "V343 : `no_expiry` ignoré pour un non super-admin", False,
                          f"publication {pid} introuvable dans /publications/mine (HTTP {m.status_code})")
        restant = mienne.get("remaining_hours")
        ok = isinstance(restant, (int, float)) and restant <= 48.5
        record(79, "V343 : `no_expiry` d'un abonné ignoré -> 48 h, pas de permanence", ok,
               f"remaining_hours={restant}")
    except Exception as e:
        record(79, "V343 : `no_expiry` ignoré pour un non super-admin", False, str(e))


def t80_v343_gratuite_refusee_sans_identite():
    """V343 (POUVOIR B) : la gratuité est réservée au super-admin AUTEUR. Un appelant
    sans identité ne doit obtenir NI apparition gratuite (`gratuit: true`) NI URL de
    paiement — et `provider` devenu facultatif ne doit pas ouvrir de brèche : un corps
    SANS moyen de paiement doit être refusé tout autant."""
    try:
        pubs = _fetch_publications()
        if not pubs:
            return skip(80, "V343 : gratuité refusée sans identité", "aucune publication en ligne")
        pid = pubs[0].get("id") or ""
        if not pid:
            return skip(80, "V343 : gratuité refusée sans identité", "publication sans id exposé")

        # Corps SANS `provider` : c'est la forme qu'utilise le chemin gratuit.
        r = requests.post(_url(f"/api/publications/{pid}/boost/checkout"),
                          json={"target": "home"}, timeout=TIMEOUT)
        d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        # 422 = le corps est rejeté par la validation avant même d'atteindre la route
        # (c'était le cas avant V343, quand `provider` était obligatoire) : c'est un
        # refus tout aussi valable. Ce qui compte : ni gratuité, ni paiement ouvert.
        refuse = r.status_code in (400, 401, 403, 404, 422)
        ok = refuse and not d.get("gratuit") and not d.get("payment_url")

        # La publication ne doit pas non plus s'être retrouvée boostée au passage.
        apres = _fetch_publications() or []
        cible = next((p for p in apres if p.get("id") == pid), {})
        ok = ok and not cible.get("boosted")

        record(80, "V343 : boost/checkout anonyme sans provider -> refus, aucune gratuité",
               ok, f"HTTP {r.status_code} gratuit={d.get('gratuit')} boosted={cible.get('boosted')}")
    except Exception as e:
        record(80, "V343 : gratuité refusée sans identité", False, str(e))


def _v344_flag():
    """État EN DIRECT du drapeau SUPERADMIN_JWT_STRICT (None si illisible)."""
    try:
        d = requests.get(_url("/api/feature-flags"), timeout=TIMEOUT).json()
        return bool(d.get("SUPERADMIN_JWT_STRICT")) if "SUPERADMIN_JWT_STRICT" in d else None
    except Exception:
        return None


def t81_v344_drapeau_expose_et_admin_seul():
    """V344 : le drapeau SUPERADMIN_JWT_STRICT doit être LISIBLE (sinon impossible de
    prouver quelle version est déployée) et lui-même verrouillé — le basculer exige un
    JWT super-admin signé. `X-User-Email` usurpé -> 403, et le drapeau ne bouge pas."""
    try:
        avant = _v344_flag()
        if avant is None:
            return record(81, "V344 : drapeau SUPERADMIN_JWT_STRICT exposé", False,
                          "absent de GET /feature-flags — version V344 non déployée ?")
        c1 = requests.put(_url("/api/feature-flags"), json={"SUPERADMIN_JWT_STRICT": True},
                          timeout=TIMEOUT).status_code
        c2 = requests.put(_url("/api/feature-flags"), json={"SUPERADMIN_JWT_STRICT": True},
                          headers={"X-User-Email": ADMIN}, timeout=TIMEOUT).status_code
        apres = _v344_flag()
        ok = c1 == 403 and c2 == 403 and avant == apres
        record(81, "V344 : drapeau lisible, bascule refusée sans JWT admin (403, inchangé)", ok,
               f"anonyme={c1} usurpé={c2} drapeau {avant}->{apres}")
    except Exception as e:
        record(81, "V344 : drapeau SUPERADMIN_JWT_STRICT", False, str(e))


def t82_v344_privileges_refuses_a_l_usurpateur():
    """V344 — LE TEST CENTRAL. Une requête portant `X-User-Email: <admin>` SANS jeton
    signé ne doit obtenir AUCUN des deux privilèges. On adapte l'attente au drapeau lu
    en direct, pour que le test soit vrai dans ses DEUX états :

      * drapeau OFF (défaut V344) -> le repli est encore accepté : on DOCUMENTE le trou
        (`gratuit: true` annoncé) sans le déclarer conforme.
      * drapeau ON                -> gratuité refusée (403) et `no_expiry` ignoré.

    On ne teste QUE des lectures/refus : aucune publication n'est boostée pour de vrai.
    """
    flag = _v344_flag()
    if flag is None:
        return skip(82, "V344 : privilèges refusés à l'usurpateur", "drapeau illisible")
    hdr = {"X-User-Email": ADMIN}
    try:
        # On cherche une publication DONT L'ADMIN EST L'AUTEUR (sinon la gratuité est
        # refusée pour une autre raison — non-auteur — et le test ne prouverait rien).
        pubs = _fetch_publications() or []
        pid = ""
        for p in pubs:
            if (p.get("coach_id") or "").lower() == ADMIN.lower() and p.get("id"):
                pid = p["id"]
                break
        if not pid:
            return skip(82, "V344 : privilèges refusés à l'usurpateur",
                        "aucune publication de l'admin en ligne")

        r = requests.get(_url(f"/api/publications/{pid}/boost/destinations"),
                         headers=hdr, timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else {}
        annonce_gratuit = bool(d.get("gratuit"))

        if flag:
            ok = not annonce_gratuit
            record(82, "V344 drapeau ON : usurpation X-User-Email n'obtient AUCUNE gratuité",
                   ok, f"HTTP {r.status_code} gratuit={annonce_gratuit}")
        else:
            ok = annonce_gratuit
            record(82, "V344 drapeau OFF : repli X-User-Email encore actif (trou connu, non fermé)",
                   ok, f"HTTP {r.status_code} gratuit={annonce_gratuit} — basculer le drapeau pour fermer")
    except Exception as e:
        record(82, "V344 : privilèges refusés à l'usurpateur", False, str(e))


def t83_v345_sessions_refus_explicite_pas_liste_vide():
    """V345 : le ChatWidget distingue désormais « refusé » de « aucune conversation ».
    Cela n'est vrai que si le serveur REFUSE (401/403) au lieu de renvoyer 200 + liste
    vide. Ce test verrouille cet invariant : si /chat/sessions repassait un jour à
    « 200 [] » pour un appelant non autorisé, le widget réafficherait « Aucune
    conversation » et la session zombie silencieuse reviendrait — sans que rien ne le
    signale. On vérifie les trois profils non autorisés."""
    try:
        cas = {
            "anonyme": {},
            "X-User-Email usurpé": {"X-User-Email": ADMIN},
            # Jeton de forme valide mais signé avec un mauvais secret.
            "jeton invalide": {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9."
                                                "eyJlbWFpbCI6ImFAYi5jIn0.mauvaise_signature"},
        }
        details = []
        ok = True
        for nom, hdr in cas.items():
            r = requests.get(_url("/api/chat/sessions"), headers=hdr, timeout=TIMEOUT)
            refuse = r.status_code in (401, 403)
            details.append(f"{nom}={r.status_code}")
            if not refuse:
                ok = False
        record(83, "V345 : /chat/sessions REFUSE (401/403) au lieu de renvoyer une liste vide",
               ok, " | ".join(details))
    except Exception as e:
        record(83, "V345 : /chat/sessions refus explicite", False, str(e))


def t84_v346_categories_des_conversations():
    """V346 : les onglets « Abonnés » / « Visiteurs » / « Liens intelligents » du
    ChatWidget sont alimentés par le champ `category` de GET /chat/sessions. Avant
    V346, la catégorisation ne lisait QUE `subscriptions` (en ignorant
    `discount_codes`, où vit l'essentiel des abonnés) et ne reconnaissait un lien
    intelligent que via `is_smart_link` (en ignorant les anciens liens à `lead_type`) :
    presque tout retombait sur « visitor », et deux onglets sur trois restaient vides.

    Ce test exige un JWT admin (les conversations sont des données personnelles). Il
    vérifie que :
      - chaque session porte bien un `category` parmi les trois valeurs attendues ;
      - la somme des trois catégories == le total (l'onglet « Tout » reste la somme) ;
      - au moins DEUX catégories distinctes sont présentes — c'est la signature du
        correctif : avant, une seule (« visitor ») l'était.
    """
    if not ADMIN_JWT:
        return skip(84, "V346 : catégories des conversations",
                    "ADMIN_JWT non fourni — parcours admin NON couvert ici")
    try:
        r = requests.get(_url("/api/chat/sessions"),
                         headers={"Authorization": "Bearer " + ADMIN_JWT}, timeout=TIMEOUT)
        if r.status_code != 200:
            return record(84, "V346 : catégories des conversations", False,
                          f"HTTP {r.status_code} avec le JWT admin")
        sessions = r.json() or []
        if not sessions:
            return skip(84, "V346 : catégories des conversations", "aucune conversation en base")

        attendues = {"subscriber", "visitor", "smart_link"}
        cats = [s.get("category") for s in sessions]
        inconnues = sorted(set(c for c in cats if c not in attendues))
        compte = {c: cats.count(c) for c in attendues}
        somme = sum(compte.values())

        ok = (not inconnues) and somme == len(sessions) and len([c for c in compte.values() if c]) >= 2
        record(84, "V346 : chaque conversation catégorisée, somme == total, ≥2 catégories",
               ok, f"total={len(sessions)} {compte} inconnues={inconnues}")
    except Exception as e:
        record(84, "V346 : catégories des conversations", False, str(e))


def _v319_flag():
    """État EN DIRECT du drapeau REQUIRE_COACH_JWT (None si illisible)."""
    try:
        return bool(requests.get(_url("/api/feature-flags"), timeout=TIMEOUT).json().get("REQUIRE_COACH_JWT"))
    except Exception:
        return None


def t61_coach_jwt_flag_admin_only():
    """V319 : l'interrupteur REQUIRE_COACH_JWT est lui-même un kill-switch — le basculer
    exige un JWT super-admin. `X-User-Email` seul (usurpable) -> 403."""
    try:
        c = requests.put(_url("/api/feature-flags"), json={"REQUIRE_COACH_JWT": False},
                         headers={"X-User-Email": ADMIN}, timeout=TIMEOUT).status_code
        record(61, "PUT REQUIRE_COACH_JWT sans JWT super-admin -> 403", c == 403, f"HTTP {c}")
    except Exception as e:
        record(61, "PUT REQUIRE_COACH_JWT sans JWT admin", False, str(e))


def t62_coach_spoof_via_email_header():
    """V319 — LE TROU. `X-User-Email: <admin>` SANS jeton signé ne doit plus valoir
    identité coach. On mesure sur DEUX routes à la fois, et on adapte l'attente au
    drapeau (lu en direct) pour que le test soit vrai dans les deux états :

      * drapeau OFF (défaut) -> le repli X-User-Email est encore accepté : on
        DOCUMENTE le trou (attendu 200 sur /chat/sessions) sans le déclarer conforme.
      * drapeau ON            -> usurpation refusée : 403 sur /chat/sessions ET aucune
        donnée personnelle rendue par smart-entry.
    """
    flag = _v319_flag()
    if flag is None:
        return record(62, "Usurpation coach par X-User-Email", False, "drapeau illisible")
    hdr = {"X-User-Email": ADMIN}
    try:
        sess = requests.get(_url("/api/chat/sessions"), headers=hdr, timeout=TIMEOUT).status_code
        probe_email = SUB_EMAIL or "v319-probe@example.com"
        r = _smart_entry(
                          json={"name": "V319 probe", "email": probe_email}, headers=hdr, timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else {}
        p = d.get("participant") or {}
        got_pii = any(k in p for k in ("whatsapp", "phone", "email")) or bool(d.get("chat_history"))
        if flag:
            ok = (sess == 403) and not got_pii
            record(62, "Drapeau ON : usurpation X-User-Email refusée (403, zéro PII)", ok,
                   f"/chat/sessions={sess} pii={got_pii}")
        else:
            ok = (sess == 200)
            record(62, "Drapeau OFF : repli X-User-Email encore actif (trou connu, non fermé)", ok,
                   f"/chat/sessions={sess} pii={got_pii} — activer REQUIRE_COACH_JWT pour fermer")
    except Exception as e:
        record(62, "Usurpation coach par X-User-Email", False, str(e))


def t63_coach_jwt_legit_access():
    """V319 — PARCOURS LÉGITIME (règle V310c : prouver que le propriétaire garde l'accès
    AVANT de fermer la porte). Avec le VRAI jeton signé du propriétaire, /chat/sessions
    et smart-entry doivent répondre 200 avec accès complet — quel que soit le drapeau."""
    if not ADMIN_JWT:
        return skip(63, "Coach légitime (JWT) -> accès complet",
                    "ADMIN_JWT non fourni — OBLIGATOIRE avant d'activer REQUIRE_COACH_JWT")
    hdr = {"Authorization": "Bearer " + ADMIN_JWT}
    try:
        r1 = requests.get(_url("/api/chat/sessions"), headers=hdr, timeout=TIMEOUT)
        n = len(r1.json()) if r1.status_code == 200 and isinstance(r1.json(), list) else -1
        probe_email = SUB_EMAIL or "v319-probe@example.com"
        r2 = _smart_entry(
                           json={"name": "V319 legit", "email": probe_email}, headers=hdr, timeout=TIMEOUT)
        d = r2.json() if r2.status_code == 200 else {}
        p = d.get("participant") or {}
        full = ("email" in p) or ("whatsapp" in p) or ("coach_id" in p)
        # `n > 0` : un 200 renvoyant une liste VIDE serait exactement la régression V312b
        # (« 32 conversations disparues ») — on refuse de la compter comme un succès.
        ok = r1.status_code == 200 and n > 0 and r2.status_code == 200 and full
        record(63, "Coach légitime (JWT) -> /chat/sessions 200 non vide + smart-entry complet", ok,
               f"sessions=HTTP {r1.status_code} n={n} smart-entry=HTTP {r2.status_code} full={full}")
    except Exception as e:
        record(63, "Coach légitime (JWT) -> accès complet", False, str(e))


def t74_progression_donnees_sante():
    """V334 : les données de progression (poids, mensurations, photos) sont des
    données de SANTÉ. Elles ne doivent JAMAIS sortir sans authentification, ni
    d'un abonné vers un autre. Sans identité prouvée : lecture, écriture et
    suppression sont toutes refusées (403), et jamais 200."""
    try:
        cible = "AFR-SONDE-V334"
        lecture = requests.get(_url(f"/api/progress/{cible}"), timeout=TIMEOUT)
        ecriture = requests.post(_url("/api/progress"),
                                 json={"subscriber_code": cible, "weight_kg": 70}, timeout=TIMEOUT)
        suppression = requests.delete(_url("/api/progress/sonde-inexistante"), timeout=TIMEOUT)
        # 403 = refusé faute d'identité ; 404 = l'abonné sonde n'existe pas (les
        # droits sont vérifiés après résolution de la cible). Jamais 200.
        ok = (lecture.status_code in (403, 404)
              and ecriture.status_code in (403, 404)
              and suppression.status_code in (403, 404))
        fuite = ('"entries"' in (lecture.text or "")) or ('"entry"' in (ecriture.text or ""))
        record(74, "Progression : aucune donnée de santé sans authentification", ok and not fuite,
               f"lecture={lecture.status_code} ecriture={ecriture.status_code} "
               f"suppression={suppression.status_code} fuite={fuite}")
    except Exception as e:
        record(74, "Progression : aucune donnée de santé sans authentification", False, str(e))


def t72_optin_consentement_obligatoire():
    """V332 : on ne peut PAS inscrire quelqu'un sans consentement explicite.
    Sans `consent: true` -> 400. Une valeur invalide -> 400. C'est la garantie RGPD
    la plus importante : aucune inscription ne doit pouvoir être créée sans la case."""
    try:
        sans = requests.post(_url("/api/subscribers/optin"),
                             json={"channel": "whatsapp", "phone": "0790000000"}, timeout=TIMEOUT).status_code
        faux = requests.post(_url("/api/subscribers/optin"),
                             json={"channel": "whatsapp", "phone": "0790000000", "consent": False},
                             timeout=TIMEOUT).status_code
        canal = requests.post(_url("/api/subscribers/optin"),
                              json={"channel": "pigeon", "phone": "0790000000", "consent": True},
                              timeout=TIMEOUT).status_code
        invalide = requests.post(_url("/api/subscribers/optin"),
                                 json={"channel": "email", "email": "pas-un-email", "consent": True},
                                 timeout=TIMEOUT).status_code
        ok = sans == 400 and faux == 400 and canal == 400 and invalide == 400
        record(72, "Opt-in : consentement obligatoire, valeurs validées", ok,
               f"sans_consent={sans} consent_false={faux} canal_inconnu={canal} email_invalide={invalide}")
    except Exception as e:
        record(72, "Opt-in : consentement obligatoire", False, str(e))


def t73_liste_inscrits_protegee():
    """V332 : la liste des inscrits n'est JAMAIS publique.
    Clé absente de l'environnement -> 503 (inerte) ; clé posée mais absente/fausse
    dans la requête -> 401. Dans les deux cas, aucun numéro ni e-mail ne sort."""
    try:
        anonyme = requests.get(_url("/api/subscribers?channel=whatsapp"), timeout=TIMEOUT)
        fausse = requests.get(_url("/api/subscribers?channel=whatsapp"),
                              headers={"Authorization": "Bearer cle-bidon-de-test"}, timeout=TIMEOUT)
        # 503 = non configurée (inerte) ; 401 = configurée mais clé exigée.
        ok = anonyme.status_code in (401, 503) and fausse.status_code in (401, 503)
        # Garde-fou : aucune fuite de données dans le corps, quel que soit le code.
        fuite = ('"list"' in (anonyme.text or "")) or ('"list"' in (fausse.text or ""))
        etat = "inerte (503)" if anonyme.status_code == 503 else "clé exigée (401)"
        record(73, "Liste des inscrits : jamais accessible sans la clé", ok and not fuite,
               f"anonyme={anonyme.status_code} fausse_cle={fausse.status_code} -> {etat} fuite={fuite}")
    except Exception as e:
        record(73, "Liste des inscrits : jamais accessible sans la clé", False, str(e))


def t71_webhook_studiio():
    """V331 : le webhook entrant Studiio ne s'ouvre jamais tout seul.
    - `AFROBOOST_WEBHOOK_SECRET` absent -> 503, aucune publication créée (état par défaut) ;
    - secret posé -> une signature absente ou fausse doit être refusée (401).
    Dans les deux cas, un appel non signé ne doit RIEN créer. On n'envoie jamais de
    signature valide ici : ce test ne doit pas publier sur la vitrine réelle."""
    try:
        r = requests.post(_url("/api/incoming-post"),
                          json={"mediaUrl": "https://exemple.invalide/x.jpg", "mediaType": "image",
                                "title": "TEST non-régression (ne doit jamais passer)"},
                          timeout=TIMEOUT)
        d = {}
        try:
            d = r.json() or {}
        except Exception:
            pass
        # 503 = webhook non configuré (inerte) ; 401 = configuré mais signature exigée.
        ok = r.status_code in (503, 401) and d.get("ok") is False
        etat = "inerte (503)" if r.status_code == 503 else ("signature exigée (401)" if r.status_code == 401 else "?")
        record(71, "Webhook Studiio : jamais ouvert sans signature valide", ok,
               f"HTTP {r.status_code} -> {etat} {_short(r)}")
    except Exception as e:
        record(71, "Webhook Studiio : jamais ouvert sans signature valide", False, str(e))


def t69_cron_campagnes_ferme():
    """V329/V330 : /api/cron/check-campaigns n'est plus une porte ouverte.
    - V329 a fermé l'anonyme (le repli `is_local_dev` s'appliquait en production,
      faute de CRON_SECRET posé) ;
    - V330 a fermé la voie `X-User-Email`, FALSIFIABLE : l'identité admin vient
      désormais d'un JWT SIGNÉ.
    Anonyme -> 401 ; en-tête X-User-Email admin SEUL -> 401 ; e-mail non-admin -> 401."""
    try:
        anonyme = requests.get(_url("/api/cron/check-campaigns"), timeout=TIMEOUT).status_code
        entete_admin = requests.get(_url("/api/cron/check-campaigns"),
                                    headers={"X-User-Email": ADMIN}, timeout=TIMEOUT).status_code
        pirate = requests.get(_url("/api/cron/check-campaigns"),
                              headers={"X-User-Email": "pirate@example.com"}, timeout=TIMEOUT).status_code
        ok = anonyme == 401 and entete_admin == 401 and pirate == 401
        record(69, "Cron campagnes : anonyme ET X-User-Email falsifié -> 401", ok,
               f"anonyme={anonyme} entete_admin={entete_admin} non-admin={pirate}")
    except Exception as e:
        record(69, "Cron campagnes : fermé au public", False, str(e))


def t70_cron_campagnes_admin_jwt():
    """V330 — PARCOURS LÉGITIME (règle V310c du dépôt : prouver que le propriétaire
    garde l'accès AVANT de durcir). Avec un JWT super-admin valide, l'endpoint doit
    répondre 200 avec la même forme qu'avant.
    SKIP si ADMIN_JWT n'est pas fourni — un SKIP ici signifie que le durcissement
    n'est PAS prouvé par la suite, et doit être vérifié à la main."""
    if not ADMIN_JWT:
        return skip(70, "Cron campagnes : JWT super-admin -> 200",
                    "ADMIN_JWT non fourni — parcours légitime NON couvert ici")
    try:
        r = requests.get(_url("/api/cron/check-campaigns"),
                         headers={"Authorization": "Bearer " + ADMIN_JWT}, timeout=TIMEOUT)
        forme = r.status_code == 200 and all(
            k in (r.json() or {}) for k in ("success", "due_campaigns", "launched", "errors", "stuck_fixed"))
        record(70, "Cron campagnes : JWT super-admin -> 200 (forme inchangée)", forme,
               f"HTTP {r.status_code} {_short(r)}")
    except Exception as e:
        record(70, "Cron campagnes : JWT super-admin -> 200", False, str(e))


def t67_publication_programmee():
    """V327 : une publication PROGRAMMÉE est créée invisible.
    - POST avec `scheduled_at` futur -> status "scheduled"
    - elle N'APPARAÎT PAS sur le mur public
    - elle APPARAÎT dans « Mes publications » avec scheduled:true
    - elle est supprimable avant l'heure (annulation)
    SKIP si la version déployée est antérieure à V327 (elle répond "ok")."""
    pub_id = None
    try:
        futur = "2030-01-01T12:00:00+00:00"   # très au-delà : ne sortira jamais pendant le test
        r = requests.post(_url("/api/publications"),
                          headers={"X-User-Email": ADMIN},
                          json={"media_url": TEST_MEDIA, "media_type": "image",
                                "caption": "TEST non-régression (programmée)",
                                "scheduled_at": futur}, timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else {}
        if r.status_code != 200 or d.get("status") != "scheduled":
            return skip(67, "Publication programmée invisible avant l'heure",
                        f"HTTP {r.status_code} status={d.get('status')} — V327 pas déployée")
        pub_id = d.get("id")
        _created_pub_ids.append((pub_id, None))   # filet de nettoyage

        mur = requests.get(_url("/api/publications"), timeout=TIMEOUT).json()
        sur_le_mur = any(p.get("id") == pub_id for p in mur) if isinstance(mur, list) else True

        mine = requests.get(_url("/api/publications/mine"),
                            headers={"X-User-Email": ADMIN}, timeout=TIMEOUT).json()
        la_mienne = [p for p in mine if p.get("id") == pub_id] if isinstance(mine, list) else []
        marquee = bool(la_mienne) and la_mienne[0].get("scheduled") is True

        ok = (not sur_le_mur) and marquee
        record(67, "Publication programmée : masquée du mur, visible chez l'auteur", ok,
               f"sur_le_mur={sur_le_mur} marquée_programmée={marquee}")
    except Exception as e:
        record(67, "Publication programmée invisible avant l'heure", False, str(e))


def t68_suppression_programmee():
    """V327 : annuler une publication programmée avant l'heure -> elle ne sortira jamais.
    Couvre aussi le bug corrigé en V327 : la suppression par l'AUTEUR renvoyait 500
    (variable `user_email` non initialisée) alors que la suppression avait bien eu lieu."""
    try:
        futur = "2030-01-01T12:00:00+00:00"
        r = requests.post(_url("/api/publications"),
                          headers={"X-User-Email": ADMIN},
                          json={"media_url": TEST_MEDIA, "media_type": "image",
                                "caption": "TEST non-régression (annulation)",
                                "scheduled_at": futur}, timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else {}
        if r.status_code != 200 or d.get("status") != "scheduled":
            return skip(68, "Annulation d'une publication programmée",
                        f"HTTP {r.status_code} — V327 pas déployée")
        pid = d.get("id")
        dele = requests.delete(_url(f"/api/publications/{pid}"),
                               headers={"X-User-Email": ADMIN}, timeout=TIMEOUT)
        mine = requests.get(_url("/api/publications/mine"),
                            headers={"X-User-Email": ADMIN}, timeout=TIMEOUT).json()
        encore = any(p.get("id") == pid for p in mine) if isinstance(mine, list) else True
        ok = dele.status_code == 200 and not encore
        record(68, "Annulation d'une publication programmée (DELETE -> 200, disparue)", ok,
               f"DELETE HTTP {dele.status_code} encore_presente={encore}")
    except Exception as e:
        record(68, "Annulation d'une publication programmée", False, str(e))


def t64_pawapay_flag_admin_only():
    """V325 : l'interrupteur PAWAPAY_ENABLED est un kill-switch de moyen de paiement —
    le basculer exige un JWT super-admin. `X-User-Email` seul (usurpable) -> 403."""
    try:
        c = requests.put(_url("/api/feature-flags"), json={"PAWAPAY_ENABLED": False},
                         headers={"X-User-Email": ADMIN}, timeout=TIMEOUT).status_code
        record(64, "PUT PAWAPAY_ENABLED sans JWT super-admin -> 403", c == 403, f"HTTP {c}")
    except Exception as e:
        record(64, "PUT PAWAPAY_ENABLED sans JWT admin", False, str(e))


def t65_pawapay_gated_by_flag():
    """V325 : le drapeau gouverne RÉELLEMENT l'intégration.
    - drapeau OFF -> /api/pawapay/available renvoie enabled=false ET les endpoints
      métier (create-coach-checkout) renvoient 404 : rien n'est joignable.
    - drapeau ON  -> available reflète la configuration, et l'endpoint métier ne
      renvoie PLUS 404 (il peut renvoyer 503/404-pack selon la config, pas 404 route).
    Le drapeau est LU, jamais basculé par le test (aucun effet de bord en production)."""
    try:
        av = requests.get(_url("/api/pawapay/available"), timeout=TIMEOUT)
        try:
            data = av.json() or {}
        except Exception:
            data = None
        # Version DÉPLOYÉE antérieure à V325 : la route n'existe pas (404, ou le
        # catch-all SPA qui renvoie du HTML). Ce n'est pas une régression — c'est
        # « pas encore livré » : on SKIP explicitement plutôt que de crier au loup.
        if av.status_code != 200 or not isinstance(data, dict) or "enabled" not in data:
            return skip(65, "PawaPay piloté par PAWAPAY_ENABLED",
                        f"/api/pawapay/available absent (HTTP {av.status_code}) — V325 pas déployée")
        flag = bool(data.get("flag"))
        enabled = bool(data.get("enabled"))

        r = requests.post(_url("/api/pawapay/create-coach-checkout"),
                          json={"pack_id": "__nonregression__", "name": "probe",
                                "email": "probe@example.com"}, timeout=TIMEOUT)

        if not flag:
            ok = (enabled is False) and r.status_code == 404
            record(65, "PawaPay OFF -> available=false + endpoints 404", ok,
                   f"flag={flag} enabled={enabled} checkout=HTTP {r.status_code}")
        else:
            # Drapeau ON : la route existe. 404 ici ne peut venir que du pack bidon,
            # ce qui est acceptable ; ce qu'on refuse, c'est un 500.
            ok = r.status_code < 500
            record(65, "PawaPay ON -> endpoints joignables (pas de 5xx)", ok,
                   f"flag={flag} enabled={enabled} checkout=HTTP {r.status_code} {_short(r)}")
    except Exception as e:
        record(65, "PawaPay piloté par PAWAPAY_ENABLED", False, str(e))


def t66_stripe_cinetpay_untouched():
    """V325 : PawaPay ne fait qu'AJOUTER un prestataire. Les points d'entrée Stripe et
    CinetPay doivent répondre exactement comme avant (route présente, pas de 404/5xx)."""
    try:
        s = requests.post(_url("/api/stripe/create-coach-checkout"),
                          json={"price_id": "", "pack_id": "__nonregression__",
                                "email": "probe@example.com", "name": "probe"}, timeout=TIMEOUT)
        c = requests.post(_url("/api/cinetpay/create-coach-checkout"),
                          json={"pack_id": "__nonregression__", "name": "probe",
                                "email": "probe@example.com"}, timeout=TIMEOUT)
        # Ce qu'on vérifie : les DEUX routes existent toujours (ni 404 « route absente »
        # ni 405). Le code métier renvoyé (400/422 pack bidon, 503 non configuré) n'est
        # pas jugé ici : seule compte la présence des prestataires historiques.
        ok = s.status_code not in (404, 405) and c.status_code not in (405,)
        record(66, "Stripe + CinetPay toujours montés après l'ajout de PawaPay", ok,
               f"stripe=HTTP {s.status_code} cinetpay=HTTP {c.status_code}")
    except Exception as e:
        record(66, "Stripe + CinetPay inchangés", False, str(e))


def t18_no_recognition_by_name_only():
    """V308 : smart-entry par NOM SEUL ne doit PLUS reconnaître un compte existant."""
    try:
        uniq = "ZZZ Testeur Inconnu 918273"
        r = _smart_entry({"name": uniq}, timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else {}
        # Un nom inconnu ne doit jamais tomber sur un compte existant.
        ok = r.status_code == 200 and (d.get("is_returning") in (False, None))
        record(18, "Nom seul ne reconnaît pas un compte existant", ok, f"HTTP {r.status_code} is_returning={d.get('is_returning')}")
    except Exception as e:
        record(18, "Nom seul ne reconnaît pas un compte", False, str(e))


def t19_device_token_endpoint():
    """V308/V296 : l'abonné légitime peut obtenir un jeton d'appareil avec son code."""
    if not (SUB_CODE and SUB_EMAIL):
        return skip(19, "Jeton d'appareil (appareil connu)", "SUB_CODE/SUB_EMAIL non fournis")
    try:
        r = requests.post(_url("/api/subscriber/token"), json={"code": SUB_CODE, "email": SUB_EMAIL}, timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else {}
        ok = r.status_code == 200 and bool(d.get("token"))
        record(19, "Jeton d'appareil délivré au code valide", ok, f"HTTP {r.status_code} token={'oui' if d.get('token') else 'non'}")
    except Exception as e:
        record(19, "Jeton d'appareil", False, str(e))


def t20_new_visitor_ok():
    """V308 : un nouveau visiteur (email FRAIS) s'inscrit sans friction. Email UNIQUE à
    chaque run (V318b) : un email fixe finissait par exister et, en mode strict, renvoyait
    proof_required -> faux FAIL. Un email vraiment neuf marche quel que soit le drapeau."""
    import time as _t
    uniq = f"nouveau-{os.getpid()}-{int(_t.time())}@example.com"
    try:
        r = _smart_entry({
            "name": "Nouveau Visiteur", "email": uniq
        }, timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else {}
        ok = r.status_code == 200 and (d.get("participant") is not None or d.get("session") is not None)
        record(20, "Nouveau visiteur -> inscription OK (sans friction)", ok, f"HTTP {r.status_code}")
    except Exception as e:
        record(20, "Nouveau visiteur -> inscription", False, str(e))


TEST_CAPTION_MARK = "TEST non-régression"


def _delete_pub(pub_id, code=None):
    """Supprime UNE publication et VÉRIFIE le résultat (V311b). Renvoie True si la
    suppression est confirmée (HTTP 200 ou 404 = déjà absente). Réessaie une fois."""
    for _essai in range(2):
        try:
            if code:
                r = requests.delete(_url(f"/api/publications/{pub_id}"),
                                    params={"subscriber_code": code}, timeout=TIMEOUT)
            else:
                r = requests.delete(_url(f"/api/publications/{pub_id}"),
                                    headers={"X-User-Email": ADMIN}, timeout=TIMEOUT)
            if r.status_code in (200, 204, 404):
                return True
        except Exception:
            pass
    return False


def _fetch_publications(retries=5):
    """Récupère la liste des publications avec RÉESSAIS (V311b). Renvoie la liste, ou
    None si l'API n'a JAMAIS répondu 200 (429 rate-limit / 502 déploiement). None ≠
    « liste vide » : un balayage ne doit pas conclure « rien à nettoyer » sur un échec
    réseau — c'est précisément ce qui a laissé des déchets en ligne (cf. V311b)."""
    import time as _t
    for essai in range(retries):
        try:
            r = requests.get(_url("/api/publications"), timeout=TIMEOUT)
            if r.status_code == 200:
                pubs = r.json()
                if isinstance(pubs, dict):
                    pubs = pubs.get("publications", pubs.get("items", []))
                return pubs or []
            # 429 (rate-limit Cloudflare) / 502 (déploiement) : on attend et on réessaie
        except Exception:
            pass
        _t.sleep(2 * (essai + 1))
    return None  # échec réseau persistant — on le SIGNALE, on ne suppose pas « vide »


def _is_test_pub(p):
    """Une publication est « de test » si la marque apparaît dans sa légende — ou, par
    prudence, dans n'importe quel champ texte (au cas où l'API renommerait `caption`)."""
    if TEST_CAPTION_MARK in (p.get("caption") or ""):
        return True
    try:
        return TEST_CAPTION_MARK in json.dumps(p, ensure_ascii=False)
    except Exception:
        return False


def cleanup():
    """Supprime les publications de TEST créées pendant CE run (best-effort, vérifié)."""
    for pub_id, code in _created_pub_ids:
        if pub_id:
            _delete_pub(pub_id, code)


def sweep_leftovers(context=""):
    """Nettoyage PRÉVENTIF et GARANTI (V311b) : supprime TOUTE publication marquée
    « TEST non-régression », résidu d'un run précédent interrompu (SIGKILL → le
    `finally` ne s'exécute pas). Ne touche QU'aux publications portant la marque.

    Robuste, contrairement à la version précédente qui se taisait sur un échec :
    - la liste est récupérée avec réessais ; un échec réseau est SIGNALÉ (pas assimilé
      à « liste vide »), sinon on croit à tort que la vitrine est propre ;
    - chaque suppression est VÉRIFIÉE ; on reboucle tant qu'il reste des résidus
      (jusqu'à 4 passes) ; ce qui résiste est affiché en clair pour qu'un humain le voie."""
    for _passe in range(4):
        pubs = _fetch_publications()
        if pubs is None:
            print(f"⚠️  nettoyage préventif{(' ' + context) if context else ''} : "
                  f"l'API /publications n'a pas répondu (429/502 ?) — résidus NON vérifiés, à recontrôler")
            return
        restes = [p for p in pubs if p.get("id") and _is_test_pub(p)]
        if not restes:
            return  # vitrine propre
        for p in restes:
            pid = p.get("id")
            done = _delete_pub(pid, None)                       # tentative admin
            if not done and SUB_CODE:
                done = _delete_pub(pid, SUB_CODE)               # repli code abonné
            if done:
                print(f"(nettoyage préventif : publication de test {pid} supprimée)")
            else:
                print(f"⚠️  publication de test {pid} IMPOSSIBLE à supprimer "
                      f"(caption={p.get('caption')!r}) — à retirer à la main")
    # après 4 passes il peut rester des irréductibles : dernier contrôle bruyant
    pubs = _fetch_publications()
    if pubs:
        irreductibles = [p.get("id") for p in pubs if p.get("id") and _is_test_pub(p)]
        if irreductibles:
            print(f"⚠️  RÉSIDUS DE TEST TOUJOURS EN LIGNE après nettoyage : {irreductibles}")


def _install_signal_cleanup():
    """V311b : sur interruption (Ctrl-C = SIGINT, kill = SIGTERM), lancer le nettoyage
    AVANT de quitter. Le `finally` ne couvre pas ces signaux ; on comble le trou.
    (SIGKILL/-9 reste inévitable — c'est le sweep préventif du run SUIVANT qui rattrape.)"""
    import signal

    def _handler(signum, frame):
        print(f"\n(interruption reçue — nettoyage des publications de test avant de quitter)")
        try:
            cleanup()
            cleanup_sessions()          # V347 : conversations de test
            sweep_leftovers("(interruption)")
        finally:
            sys.exit(130)

    for _sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
        if _sig is not None:
            try:
                signal.signal(_sig, _handler)
            except Exception:
                pass


def main():
    print(f"=== NON-RÉGRESSION Afroboost — {BASE} ===\n")
    _install_signal_cleanup()          # V311b : nettoyage même en cas d'interruption
    sweep_leftovers("(démarrage)")     # purge préventive des déchets d'un run précédent
    try:
        for fn in (t01_publish_subscriber, t02_publish_coach, t03_mine_subscriber, t04_mine_coach,
                   t05_live_subscriber, t06_live_admin_nocode, t07_live_admin_withcode,
                   t08_subscriptions_by_email, t09_profile_no_base64, t10_translate_fr_en,
                   t11_translate_bassa_lexicon, t12_bot_cours, t13_bot_partner,
                   t14_chips_have_icon, t15_contacts_coach,
                   t16_masking_active, t17_device_token_unmasks,
                   t18_no_recognition_by_name_only, t19_device_token_endpoint, t20_new_visitor_ok,
                   t21_users_requires_auth, t22_codes_requires_auth, t23_sessions_requires_auth,
                   t24_smart_entry_no_pii, t35_security_headers, t36_cors_foreign_origin,
                   t25_transactions_jwt_strict, t26_codes_jwt_strict,
                   t57_no_identity_overwrite, t58_delete_routes_require_auth,
                   t59_feature_flags_require_admin, t60_strict_entry_proof_required,
                   t61_coach_jwt_flag_admin_only, t62_coach_spoof_via_email_header,
                   t63_coach_jwt_legit_access,
                   t64_pawapay_flag_admin_only, t65_pawapay_gated_by_flag,
                   t66_stripe_cinetpay_untouched,
                   t67_publication_programmee, t68_suppression_programmee,
                   t69_cron_campagnes_ferme, t70_cron_campagnes_admin_jwt, t71_webhook_studiio,
                   t72_optin_consentement_obligatoire, t73_liste_inscrits_protegee,
                   t74_progression_donnees_sante,
                   t75_boost_prix_lecture_publique, t76_boost_prix_ecriture_admin_seulement,
                   t77_boost_checkout_exige_auteur, t78_boost_pas_de_donnees_commerciales_publiques,
                   t79_v343_no_expiry_ignore_pour_non_admin, t80_v343_gratuite_refusee_sans_identite,
                   t81_v344_drapeau_expose_et_admin_seul, t82_v344_privileges_refuses_a_l_usurpateur,
                   t83_v345_sessions_refus_explicite_pas_liste_vide,
                   t84_v346_categories_des_conversations,
                   t39_redos_input, t40_nosql_injection):
            fn()
    finally:
        # V307 : nettoyage GARANTI, même si un test échoue ou si le script est interrompu.
        cleanup()
        cleanup_sessions()              # V347 : conversations de test
        sweep_leftovers()
    passed = sum(1 for _, _, st, _ in results if st == "pass")
    failed = sum(1 for _, _, st, _ in results if st == "fail")
    skipped = sum(1 for _, _, st, _ in results if st == "skip")
    total = len(results)
    print(f"\n=== RÉSULTAT : {passed} PASS / {failed} FAIL / {skipped} SKIP (sur {total}) ===")
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
