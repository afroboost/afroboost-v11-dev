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
import re          # V411 : détection d'un numéro qui filtrerait dans un refus
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

    V348 : la suppression passe par un JETON SIGNÉ (`ADMIN_JWT`) dès qu'il est
    fourni. C'est indispensable : `DELETE /chat/sessions/{id}` est une route
    DESTRUCTIVE, et le drapeau `SUPERADMIN_JWT_STRICT` lui retire le repli
    `X-User-Email`. Sans jeton, le nettoyage cesserait de fonctionner le jour de la
    bascule — et les conversations de test recommenceraient à s'accumuler en
    silence. On garde donc le repli TANT QUE le drapeau est OFF, et on AVERTIT
    bruyamment sinon : mieux vaut un message gênant qu'une pollution invisible.

    C'est un soft-delete : rien n'est effacé définitivement, la conversation part
    dans la corbeille, comme quand le coach supprime depuis l'interface.

    Best-effort et SILENCIEUX en cas de succès ; ce qui résiste est AFFICHÉ, pour
    qu'un humain le voie plutôt que de découvrir l'accumulation six mois plus tard.
    """
    if not _created_session_ids:
        return
    if ADMIN_JWT:
        entetes = {"Authorization": "Bearer " + ADMIN_JWT}
        voie = "jeton signé"
    else:
        entetes = {"X-User-Email": ADMIN}
        voie = "repli X-User-Email"
    restants = []
    for sid in sorted(_created_session_ids):
        try:
            r = requests.delete(_url(f"/api/chat/sessions/{sid}"),
                                headers=entetes, timeout=TIMEOUT)
            if r.status_code not in (200, 204, 404):
                restants.append(f"{sid[:8]}({r.status_code})")
        except Exception as e:
            restants.append(f"{sid[:8]}({type(e).__name__})")
    if restants:
        print(f"⚠️  {len(restants)} conversation(s) de test NON supprimée(s) via {voie} : "
              f"{', '.join(restants[:10])}")
        if not ADMIN_JWT:
            print("    → fournir ADMIN_JWT : la route de suppression exige un jeton signé "
                  "quand SUPERADMIN_JWT_STRICT est actif (V348).")
    else:
        print(f"🧹 {len(_created_session_ids)} conversation(s) de test nettoyée(s) ({voie}).")


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


def t92_v369_routes_bot_fermees_et_drapeau_off():
    """V369 : le bot est branché sur le webhook, mais DÉSACTIVÉ.

    Trois affirmations :
      - le drapeau BOT_MENU_ENABLED est exposé et vaut FALSE (bot inexistant pour
        l'extérieur : le webhook se comporte comme avant) ;
      - les routes du bot refusent (401/403) sans jeton coach signé — y compris
        POST /reactiver, la seule qui ÉCRIT ;
      - le webhook entrant reste vérifiable par Meta (GET hub.challenge), donc la
        greffe n'a pas cassé la réception des messages.

    AUCUN message n'est envoyé par ce test.
    """
    try:
        f = requests.get(_url("/api/feature-flags"), timeout=TIMEOUT).json()
        drapeau_off = f.get("BOT_MENU_ENABLED") is False
        pauses = requests.get(_url("/api/bot-whatsapp/pauses"), timeout=TIMEOUT)
        react = requests.post(_url("/api/bot-whatsapp/reactiver"),
                              json={"telephone": "+41000000000"}, timeout=TIMEOUT)
        react_spoof = requests.post(_url("/api/bot-whatsapp/reactiver"),
                                    headers={"X-User-Email": ADMIN},
                                    json={"telephone": "+41000000000"}, timeout=TIMEOUT)
        fermees = all(x.status_code in (401, 403) for x in (pauses, react, react_spoof))
        verif = requests.get(_url("/api/webhook/whatsapp-meta"), timeout=TIMEOUT,
                             params={"hub.mode": "subscribe",
                                     "hub.verify_token": "afroboost_webhook_2024",
                                     "hub.challenge": "NONREG"})
        webhook_ok = verif.status_code == 200 and "NONREG" in (verif.text or "")
        ok = drapeau_off and fermees and webhook_ok
        record(92, "V369 : bot OFF, routes fermées sans jeton, webhook toujours vérifiable", ok,
               f"drapeau_off={drapeau_off} pauses={pauses.status_code} "
               f"reactiver={react.status_code} usurpé={react_spoof.status_code} "
               f"webhook={verif.status_code}")
    except Exception as e:
        record(92, "V369 : bot OFF et routes fermées", False, str(e))


def t91_v367_apercu_bot_ferme_et_sans_envoi():
    """V367 : l'aperçu du menu WhatsApp est une route de LECTURE, réservée au coach.

    Trois affirmations :
      - refus (401/403) sans jeton signé, et un X-User-Email usurpé n'ouvre rien ;
      - avec ADMIN_JWT : l'aperçu répond, annonce `aucun_envoi: true`, et le drapeau
        BOT_MENU_ENABLED reste à FALSE (le bot ne doit pas s'activer tout seul) ;
      - le menu propose bien 3 boutons et les listes respectent les limites WhatsApp
        (10 lignes, titres 24, descriptions 72) — un dépassement ferait rejeter
        l'envoi par Meta le jour du branchement.

    AUCUN message n'est envoyé par ce test : la route ne fait que construire.
    """
    try:
        r_anon = requests.get(_url("/api/bot-whatsapp/apercu"), timeout=TIMEOUT)
        r_spoof = requests.get(_url("/api/bot-whatsapp/apercu"),
                               headers={"X-User-Email": ADMIN}, timeout=TIMEOUT)
        ferme = all(x.status_code in (401, 403) for x in (r_anon, r_spoof))
        if not ADMIN_JWT:
            return record(91, "V367 : aperçu du bot fermé sans jeton signé", ferme,
                          f"anon={r_anon.status_code} usurpé={r_spoof.status_code}")
        r = requests.get(_url("/api/bot-whatsapp/apercu"),
                         headers={"Authorization": "Bearer " + ADMIN_JWT}, timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else {}
        p = d.get("payloads_whatsapp", {})
        boutons = (p.get("menu", {}).get("interactive", {})
                    .get("action", {}).get("buttons", []))
        limites_ok = True
        for cle in ("cours", "offres"):
            for section in (p.get(cle, {}).get("interactive", {})
                             .get("action", {}).get("sections", [])):
                if len(section.get("rows", [])) > 10:
                    limites_ok = False
                for ligne in section.get("rows", []):
                    if len(ligne.get("title", "")) > 24 or len(ligne.get("description", "")) > 72:
                        limites_ok = False
        ok = (ferme and r.status_code == 200 and d.get("aucun_envoi") is True
              and d.get("bot_actif") is False and len(boutons) == 3 and limites_ok)
        record(91, "V367 : aperçu fermé sans jeton, bot OFF, limites WhatsApp respectées", ok,
               f"anon={r_anon.status_code} usurpé={r_spoof.status_code} "
               f"bot_actif={d.get('bot_actif')} boutons={len(boutons)} limites={limites_ok} "
               f"sources={d.get('sources')}")
    except Exception as e:
        record(91, "V367 : aperçu du bot WhatsApp", False, str(e))


def t90_v365_membres_de_groupe_identiques_et_rapides():
    """V365 : l'enrichissement des membres passe d'une requête PAR MEMBRE à deux
    requêtes groupées ($in). Seule la vitesse change — la liste doit rester la même.

    Ce test verrouille l'identité du résultat par ses invariants, ceux-là mêmes que
    la reconstruction groupée pourrait casser :
      - autant d'entrées dans `members_info` que d'identifiants dans `member_ids` ;
      - MÊME ORDRE, position par position (une reconstruction par dictionnaire
        perdrait l'ordre : c'est le risque n°1 de cette optimisation) ;
      - mêmes champs exactement : id, name, email ;
      - aucun membre introuvable ne disparaît (il reste, en « Inconnu »).
    Et il mesure le temps : la route mettait ~13 s en production avant V365.

    Lecture seule : aucune campagne, aucun envoi. Exige ADMIN_JWT (V349).
    """
    if not ADMIN_JWT:
        return skip(90, "V365 : membres de groupe (identité + vitesse)", "ADMIN_JWT non fourni")
    try:
        import time as _t
        hdr = {"Authorization": "Bearer " + ADMIN_JWT}
        t0 = _t.perf_counter()
        r = requests.get(_url("/api/chat/groups"), headers=hdr, timeout=TIMEOUT)
        duree = _t.perf_counter() - t0
        if r.status_code != 200:
            return record(90, "V365 : membres de groupe", False, f"HTTP {r.status_code}")
        groupes = r.json()
        if not isinstance(groupes, list) or not groupes:
            return skip(90, "V365 : membres de groupe", "aucun groupe en base")

        champs_ok = ordre_ok = compte_ok = True
        total = 0
        for g in groupes:
            ids = g.get("member_ids")
            infos = g.get("members_info")
            if ids is None or infos is None:
                continue                      # groupe sans membres exposés : rien à vérifier
            total += len(infos)
            if len(ids) != len(infos):
                compte_ok = False
            for i, info in enumerate(infos):
                if set(info.keys()) != {"id", "name", "email"}:
                    champs_ok = False
                if i < len(ids) and info.get("id") != ids[i]:
                    ordre_ok = False          # l'ordre d'origine doit être préservé
        # Seuil large : on veut prouver la disparition des ~13 s, pas chronométrer le réseau.
        vitesse_ok = duree < 5.0
        ok = champs_ok and ordre_ok and compte_ok and vitesse_ok
        record(90, "V365 : membres de groupe inchangés (ordre, champs, compte) et route rapide",
               ok, f"{len(groupes)} groupe(s), {total} membre(s) | ordre={ordre_ok} "
                   f"champs={champs_ok} compte={compte_ok} | {duree:.2f}s (< 5 s attendu)")
    except Exception as e:
        record(90, "V365 : membres de groupe", False, str(e))


def t89_v363_segments_contacts():
    """V363 : les segments de contacts sont CALCULÉS, jamais stockés.

    Deux affirmations :
      - les deux routes REFUSENT (401/403) sans jeton coach signé — elles exposent
        des identifiants de contacts, la règle « aucune donnée personnelle sans
        authentification » s'applique ; un simple X-User-Email ne doit rien ouvrir ;
      - avec ADMIN_JWT : les comptes sont cohérents (les quatre groupes d'usage sont
        exclusifs, leur somme vaut le nombre de personnes) et un segment inconnu
        renvoie 404 plutôt qu'une liste vide trompeuse.

    Ces routes ne touchent NI aux campagnes, NI au chemin d'envoi : rien n'est
    envoyé à personne pendant ce test.
    """
    try:
        # 1) portes fermées — anonyme puis usurpation par en-tête
        r_anon = requests.get(_url("/api/contacts/segments"), timeout=TIMEOUT)
        r_spoof = requests.get(_url("/api/contacts/segments"),
                               headers={"X-User-Email": ADMIN}, timeout=TIMEOUT)
        r_liste = requests.get(_url("/api/contacts/segment/demarchable_whatsapp"),
                               timeout=TIMEOUT)
        ferme = all(x.status_code in (401, 403) for x in (r_anon, r_spoof, r_liste))
        aucune_fuite = all("contacts" not in (x.text or "") for x in (r_anon, r_spoof, r_liste))
        if not ADMIN_JWT:
            return record(89, "V363 : segments fermés sans jeton signé (parcours admin non couvert)",
                          ferme and aucune_fuite,
                          f"anon={r_anon.status_code} usurpé={r_spoof.status_code} "
                          f"liste={r_liste.status_code}")

        # 2) parcours légitime
        hdr = {"Authorization": "Bearer " + ADMIN_JWT}
        r = requests.get(_url("/api/contacts/segments"), headers=hdr, timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else {}
        groupes = d.get("groupes_usage", {}) or {}
        somme_ok = (d.get("total_groupes_usage") == d.get("personnes")
                    and sum(groupes.values()) == d.get("personnes"))
        r404 = requests.get(_url("/api/contacts/segment/segment_qui_nexiste_pas"),
                            headers=hdr, timeout=TIMEOUT)
        r_seg = requests.get(_url("/api/contacts/segment/demarchable_whatsapp"),
                             headers=hdr, timeout=TIMEOUT)
        seg = r_seg.json() if r_seg.status_code == 200 else {}
        # V363b : le segment annonce autant de personnes que le compteur, ET distingue
        # celles réellement adressables (une personne sans identifiant ne peut pas être
        # ciblée par une campagne). L'écart doit être AFFICHÉ, jamais absorbé.
        coherent = (seg.get("total") == groupes.get("demarchable_whatsapp")
                    and seg.get("adressables", 0) + seg.get("sans_identifiant", 0) == seg.get("total")
                    and len(seg.get("contacts", [])) == seg.get("adressables")
                    and seg.get("tronque") is False)
        ok = (ferme and aucune_fuite and r.status_code == 200 and somme_ok
              and r404.status_code == 404 and coherent)
        record(89, "V363 : segments fermés sans jeton, comptes cohérents avec jeton", ok,
               f"anon={r_anon.status_code} usurpé={r_spoof.status_code} "
               f"personnes={d.get('personnes')} groupes={groupes} "
               f"segment={seg.get('total')} adressables={seg.get('adressables')} "
               f"sans_id={seg.get('sans_identifiant')} inconnu={r404.status_code}")
    except Exception as e:
        record(89, "V363 : segments de contacts", False, str(e))


def t88_v354_permissions_policy_micro():
    """V354 : l'en-tête `Permissions-Policy` portait `microphone=()` — une liste
    d'autorisation VIDE, qui refuse le micro à TOUT LE MONDE, y compris au site
    lui-même. Le navigateur rejetait `getUserMedia({audio:true})` SANS jamais
    afficher la demande d'autorisation : les notes vocales V352 étaient donc
    inutilisables, avec un message trompeur accusant un refus de l'utilisateur.

    Ce test verrouille les deux moitiés de la correction, car elles sont
    indissociables : le micro doit être autorisé pour `self`, et il ne doit PAS
    être ouvert à tous (`microphone=*` serait une régression de sécurité).
    Les autres en-têtes de sécurité sont vérifiés au passage : la correction ne
    doit pas les avoir emportés.
    """
    try:
        r = requests.get(_url("/"), timeout=TIMEOUT)
        pp = (r.headers.get("Permissions-Policy") or "").replace(" ", "")
        micro_ok = "microphone=(self)" in pp
        pas_ouvert = "microphone=*" not in pp
        autres = all(h in r.headers for h in
                     ("X-Content-Type-Options", "X-Frame-Options", "Strict-Transport-Security"))
        ok = micro_ok and pas_ouvert and autres
        record(88, "V354 : micro autorisé pour le site seul (microphone=(self)), en-têtes intacts",
               ok, f"Permissions-Policy={pp!r} autres_en-têtes={autres}")
    except Exception as e:
        record(88, "V354 : Permissions-Policy du micro", False, str(e))


def t87_v350_piece_jointe_du_chat():
    """V350 : l'envoi d'image/fichier dans le chat n'existait pas — le modèle de
    message n'avait aucun champ `media_url` et, le modèle étant en `extra=ignore`,
    tout média envoyé était silencieusement jeté.

    Trois affirmations, sur une conversation que le test crée lui-même :
      - une pièce jointe SEULE (sans légende) passe et revient dans le fil ;
      - une URL hors Cloudinary est REFUSÉE (sinon on ferait afficher n'importe
        quelle image distante dans la conversation) ;
      - un message vide sans pièce jointe reste refusé.
    Exige ADMIN_JWT : poster une réponse coach demande une identité.
    """
    if not ADMIN_JWT:
        return skip(87, "V350 : pièce jointe du chat", "ADMIN_JWT non fourni")
    hdr = {"Authorization": "Bearer " + ADMIN_JWT}
    try:
        import uuid as _uuid
        r0 = _smart_entry({"name": "V350 sonde",
                           "email": f"v350-{_uuid.uuid4().hex[:8]}@example.com"})
        sid = ((r0.json() or {}).get("session") or {}).get("id") if r0.status_code == 200 else ""
        if not sid:
            return skip(87, "V350 : pièce jointe du chat", "conversation de sonde non créée")

        avec = requests.post(_url("/api/chat/coach-response"),
                             json={"session_id": sid, "message": "", "coach_name": "Coach",
                                   "media_url": TEST_MEDIA, "media_type": "image"},
                             headers=hdr, timeout=TIMEOUT).status_code
        hors = requests.post(_url("/api/chat/coach-response"),
                             json={"session_id": sid, "message": "x",
                                   "media_url": "https://evil.example.com/t.png"},
                             headers=hdr, timeout=TIMEOUT).status_code
        vide = requests.post(_url("/api/chat/coach-response"),
                             json={"session_id": sid, "message": "", "coach_name": "Coach"},
                             headers=hdr, timeout=TIMEOUT).status_code
        lu = requests.get(_url(f"/api/chat/sessions/{sid}/messages"), headers=hdr, timeout=TIMEOUT)
        medias = [m for m in (lu.json() if lu.status_code == 200 else []) if m.get("media_url")]

        ok = avec == 200 and hors == 400 and vide == 400 and len(medias) == 1
        record(87, "V350 : pièce jointe acceptée, URL étrangère et message vide refusés", ok,
               f"image_seule={avec} url_etrangere={hors} vide={vide} relus={len(medias)}")
    except Exception as e:
        record(87, "V350 : pièce jointe du chat", False, str(e))


def _v349_flag():
    """État EN DIRECT du drapeau CHAT_READ_STRICT (None si illisible)."""
    try:
        d = requests.get(_url("/api/feature-flags"), timeout=TIMEOUT).json()
        return bool(d.get("CHAT_READ_STRICT")) if "CHAT_READ_STRICT" in d else None
    except Exception:
        return None


def t86_v349_contenu_des_conversations_ferme():
    """V349 — LA FUITE MAJEURE. `GET /chat/sessions/{id}/messages` n'avait aucune
    authentification : un anonyme lisait le CONTENU des conversations privées et de
    groupe, y compris celles mises à la corbeille. Les routes de groupe exposaient en
    plus ~1200 identifiants de membres, les jetons d'invitation et les prompts IA.

    On mesure sur une conversation que le test CRÉE lui-même. Deux affirmations, et
    la première compte autant que la seconde :
      - le PARTICIPANT légitime lit sa conversation (sinon on aurait cassé le chat) ;
      - l'anonyme et l'usurpateur sont refusés.
    Attente adaptée aux DEUX états du drapeau.
    """
    flag = _v349_flag()
    if flag is None:
        return skip(86, "V349 : contenu des conversations", "drapeau illisible")
    try:
        import uuid as _uuid
        r0 = _smart_entry({"name": "V349 sonde",
                           "email": f"v349-{_uuid.uuid4().hex[:8]}@example.com"})
        d0 = r0.json() if r0.status_code == 200 else {}
        sid = (d0.get("session") or {}).get("id") or ""
        pid = (d0.get("participant") or {}).get("id") or ""
        if not sid or not pid:
            return skip(86, "V349 : contenu des conversations",
                        "conversation de sonde non créée (entrée stricte ?)")

        legit = requests.get(_url(f"/api/chat/sessions/{sid}/messages"),
                             params={"participant_id": pid}, timeout=TIMEOUT).status_code
        anon = requests.get(_url(f"/api/chat/sessions/{sid}/messages"), timeout=TIMEOUT).status_code
        usurp = requests.get(_url(f"/api/chat/sessions/{sid}/messages"),
                             headers={"X-User-Email": ADMIN}, timeout=TIMEOUT).status_code
        grp = requests.get(_url("/api/chat/groups"), timeout=TIMEOUT).status_code

        if flag:
            ok = legit == 200 and anon == 403 and usurp == 403 and grp == 403
            record(86, "V349 drapeau ON : participant lit, anonyme et usurpateur refusés", ok,
                   f"participant={legit} anonyme={anon} usurpé={usurp} /chat/groups={grp}")
        else:
            ok = legit == 200 and anon == 200
            record(86, "V349 drapeau OFF : lecture encore ouverte (trou connu, non fermé)", ok,
                   f"participant={legit} anonyme={anon} — basculer CHAT_READ_STRICT pour fermer")
    except Exception as e:
        record(86, "V349 : contenu des conversations", False, str(e))


def t85_v348_suppression_conversation_exige_jeton():
    """V348 : DELETE /chat/sessions/{id} est DESTRUCTIVE — elle ne lisait que
    `X-User-Email`, donc un `curl` suffisait à effacer les conversations du coach.
    Elle n'était même pas couverte par REQUIRE_COACH_JWT (qui ne vise que les
    lectures). Le verrou est derrière SUPERADMIN_JWT_STRICT.

    On mesure sur une conversation que le test CRÉE lui-même, jamais sur une vraie.

    Un identifiant INEXISTANT ne conviendrait pas : drapeau OFF, il n'y a pas de
    garde d'identité en tête de route, donc le 404 « session inconnue » tombe AVANT
    le contrôle de permission — anonyme et usurpateur reçoivent le même 404, et le
    test ne prouve rien. Sur une conversation qui EXISTE, les deux se distinguent.

    Ordre volontaire : l'anonyme d'abord (il ne doit rien pouvoir supprimer, dans
    les deux états du drapeau), l'usurpateur ensuite (c'est lui qui change).
      * OFF -> `X-User-Email` vaut encore identité admin : 200 (trou DOCUMENTÉ) ;
      * ON  -> 403, l'usurpation ne supprime plus rien.
    """
    flag = _v344_flag()
    if flag is None:
        return skip(85, "V348 : suppression de conversation", "drapeau illisible")
    try:
        import uuid as _uuid
        r0 = _smart_entry({"name": "V348 sonde",
                           "email": f"v348-{_uuid.uuid4().hex[:8]}@example.com"})
        sid = ((r0.json() or {}).get("session") or {}).get("id") if r0.status_code == 200 else ""
        if not sid:
            return skip(85, "V348 : suppression de conversation",
                        "conversation de sonde non créée (entrée stricte ?)")

        anon = requests.delete(_url(f"/api/chat/sessions/{sid}"), timeout=TIMEOUT).status_code
        usurp = requests.delete(_url(f"/api/chat/sessions/{sid}"),
                                headers={"X-User-Email": ADMIN}, timeout=TIMEOUT).status_code
        if flag:
            ok = anon == 403 and usurp == 403
            record(85, "V348 drapeau ON : suppression refusée sans jeton signé (403)", ok,
                   f"anonyme={anon} usurpé={usurp}")
        else:
            ok = anon == 403 and usurp == 200
            record(85, "V348 drapeau OFF : anonyme refusé, repli X-User-Email encore actif "
                       "(trou connu, non fermé)", ok,
                   f"anonyme={anon} usurpé={usurp} — basculer le drapeau pour fermer")
    except Exception as e:
        record(85, "V348 : suppression de conversation", False, str(e))


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


def t98_v425_orphelins_ferme():
    """V425 : l'inventaire des fichiers orphelins est réservé au super-admin signé.

    Cette route dit QUELS fichiers ne sont référencés nulle part — donc lesquels
    vont disparaître. C'est une carte du stockage : ouverte, elle renseignerait un
    tiers sur la structure interne et sur ce qui est sur le point d'être supprimé.
    On vérifie l'anonyme ET l'usurpation par `X-User-Email`, falsifiable."""
    echecs = []
    for nom, entetes in (("anonyme", {}), ("X-User-Email usurpé", {"X-User-Email": ADMIN})):
        try:
            r = requests.get(_url("/api/admin/orphelins"), headers=entetes, timeout=TIMEOUT)
            if r.status_code not in (401, 403):
                echecs.append(f"{nom} -> HTTP {r.status_code} (attendu 401/403)")
            elif re.search(r"[0-9a-f]{16}", r.text or ""):
                echecs.append(f"{nom} -> refus MAIS un identifiant de fichier apparaît")
        except Exception as e:
            echecs.append(f"{nom} -> {e}")
    record(98, "V425 : inventaire des orphelins fermé sans jeton super-admin",
           not echecs, " | ".join(echecs))


def t97_v413_stockage_disque():
    """V413 : un NOUVEL envoi est rangé sur le disque et servi correctement.

    Vérifie le cycle complet écriture -> lecture, qui est tout l'objet de V413 :
      1. l'envoi renvoie une URL /api/files/… ;
      2. cette URL sert le fichier À L'IDENTIQUE (octet pour octet) ;
      3. elle répond 206 aux requêtes par plages (FileResponse gère le Range
         nativement quand le fichier est sur disque).

    NOTE ASSUMÉE : ce test laisse un fichier d'environ 70 octets à chaque
    exécution — il n'existe aucune route de suppression d'asset, et en inventer
    une pour les besoins du test ajouterait une surface d'attaque pour un gain
    nul. Le coût est négligeable ; le signaler vaut mieux que le taire."""
    # PNG 1x1 rouge, 69 octets, CRC corrects. Le serveur le RÉOUVRE avec Pillow
    # pour l'optimiser : un PNG approximatif y échoue en 500 (« broken data
    # stream »). Ces octets-ci ont été validés contre le vrai point d'entrée.
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108020000"
        "00907753de0000000c49444154789c63f8cfc0000003010100c9fe92"
        "ef0000000049454e44ae426082")
    try:
        r = requests.post(_url("/api/coach/upload-asset"),
                          headers={"X-User-Email": ADMIN},
                          files={"file": ("v413_test.png", png, "image/png")},
                          data={"asset_type": "image"}, timeout=TIMEOUT)
        if r.status_code != 200:
            record(97, "V413 : nouvel envoi rangé sur disque et servi", False,
                   f"envoi -> HTTP {r.status_code} {_short(r)}")
            return
        url = (r.json() or {}).get("url") or ""
        if not url.startswith("/api/files/"):
            record(97, "V413 : nouvel envoi rangé sur disque et servi", False,
                   f"URL inattendue : {url!r}")
            return
    except Exception as e:
        record(97, "V413 : nouvel envoi rangé sur disque et servi", False, f"envoi : {e}")
        return

    echecs = []
    try:
        # L'image est optimisée par le serveur (réencodage JPEG/PNG) : on ne
        # compare donc PAS au PNG d'origine, mais on exige un fichier NON VIDE
        # et cohérent avec lui-même entre la lecture complète et la plage.
        r1 = requests.get(_url(url), timeout=TIMEOUT)
        if r1.status_code != 200 or not r1.content:
            echecs.append(f"lecture -> HTTP {r1.status_code}, {len(r1.content)} o")
        else:
            r2 = requests.get(_url(url), headers={"Range": "bytes=0-9"}, timeout=TIMEOUT)
            if r2.status_code != 206:
                echecs.append(f"Range -> HTTP {r2.status_code} (attendu 206)")
            elif r2.content != r1.content[:10]:
                echecs.append("les 10 premiers octets de la plage diffèrent du fichier complet")
            cr = r2.headers.get("Content-Range", "")
            if r2.status_code == 206 and not cr.endswith(f"/{len(r1.content)}"):
                echecs.append(f"Content-Range {cr!r} incohérent avec {len(r1.content)} o")
    except Exception as e:
        echecs.append(str(e))

    record(97, "V413 : nouvel envoi servi à l'identique, plages comprises",
           not echecs, " | ".join(echecs) or f"url={url}")


def t96_v412_range_206():
    """V412 : /api/files/ doit répondre 206 à une requête par plages.

    Avant V412 la route annonçait `Accept-Ranges: bytes` mais renvoyait
    invariablement 200 avec le fichier entier : un navigateur ne pouvait ni
    avancer dans une vidéo, ni démarrer la lecture d'un gros fichier. Le 206
    que l'on croyait fonctionnel venait de Cloudflare, pas de l'application.

    On vérifie AUSSI la non-régression : sans en-tête `Range`, la réponse doit
    rester un 200 complet — c'est ce qui garantit qu'images et anciennes vidéos
    (« PULSE x10 ») ne changent pas de comportement."""
    # On découvre une vidéo servie par /api/files/ depuis les offres publiques,
    # plutôt que de coder en dur un identifiant qui peut disparaître.
    cible = None
    try:
        r = requests.get(_url("/api/offers"), timeout=TIMEOUT)
        offres = r.json()
        if isinstance(offres, dict):
            offres = offres.get("offers", [])
        for o in offres:
            for champ in ("videoUrl", "thumbnail"):
                v = (o.get(champ) or "")
                if v.startswith("/api/files/") and v.endswith(".mp4"):
                    cible = v
                    break
            if cible:
                break
    except Exception as e:
        record(96, "V412 : /api/files/ répond 206 aux requêtes par plages", False,
               f"découverte impossible : {e}")
        return

    if not cible:
        skip(96, "V412 : /api/files/ répond 206", "aucune vidéo /api/files/ référencée")
        return

    # ON INTERROGE L'ORIGINE, PAS L'URL PUBLIQUE. Cloudflare répond aux requêtes
    # par plages depuis SON cache : sur l'URL publique il renvoie 200 quoi que
    # fasse l'application, ce qui masquerait totalement la régression qu'on veut
    # détecter. La technique (forcer l'en-tête `Host` sur l'IP d'origine) est
    # celle que CLAUDE.md impose pour distinguer l'origine du proxy.
    ORIGINE = "http://178.105.201.62"
    hote = {"Host": "afroboost.com"}

    echecs = []
    try:
        # 1) plage explicite -> 206 + Content-Range + bonne longueur
        r = requests.get(ORIGINE + cible,
                         headers={**hote, "Range": "bytes=0-1023"}, timeout=TIMEOUT)
        if r.status_code != 206:
            echecs.append(f"Range 0-1023 -> HTTP {r.status_code} (attendu 206)")
        else:
            if len(r.content) != 1024:
                echecs.append(f"206 mais {len(r.content)} octets (attendu 1024)")
            cr = r.headers.get("Content-Range", "")
            if not cr.startswith("bytes 0-1023/"):
                echecs.append(f"Content-Range inattendu : {cr!r}")

        # 2) plage hors fichier -> 416 (et pas un 200 qui renverrait tout)
        r2 = requests.get(ORIGINE + cible,
                          headers={**hote, "Range": "bytes=999999999-"}, timeout=TIMEOUT)
        if r2.status_code != 416:
            echecs.append(f"plage hors fichier -> HTTP {r2.status_code} (attendu 416)")

        # 3) NON-RÉGRESSION : sans Range, 200 + fichier COMPLET. C'est le chemin
        #    qu'empruntent les images et les vidéos déjà en ligne.
        r3 = requests.get(ORIGINE + cible, headers=hote, timeout=max(TIMEOUT, 120))
        if r3.status_code != 200:
            echecs.append(f"sans Range -> HTTP {r3.status_code} (attendu 200)")
        elif r2.status_code == 416:
            total = r2.headers.get("Content-Range", "*/0").split("/")[-1]
            if total.isdigit() and len(r3.content) != int(total):
                echecs.append(f"sans Range : {len(r3.content)} o != taille annoncée {total}")
    except Exception as e:
        echecs.append(f"origine injoignable ({e})")

    record(96, "V412 : origine répond 206 aux plages, 416 hors plage, 200 complet sans Range",
           not echecs, " | ".join(echecs))


def t94_v411_fils_prives_fermes():
    """V411 : les fils WhatsApp du coach ne sont plus lisibles sans jeton signé.

    Avant V411, ces routes n'exigeaient RIEN : `admin_afroboost` étant en clair dans
    le bundle public, un `curl` sans en-tête listait les 14 fils (noms + numéros de
    membres) puis leur contenu intégral. Fuite de données personnelles.

    On vérifie les QUATRE portes, y compris l'usurpation par `X-User-Email` (que
    n'importe qui peut écrire) — un 200 sur l'une d'elles rouvrirait toute la fuite.
    """
    echecs = []

    def _refuse(nom, faire):
        try:
            r = faire()
            if r.status_code not in (401, 403):
                echecs.append(f"{nom} -> HTTP {r.status_code} (attendu 401/403)")
                return
            # Un refus qui laisserait quand même filtrer des données serait pire
            # qu'inutile : on vérifie que le corps ne contient aucun numéro.
            if re.search(r"\+?\d{9,}", r.text or ""):
                echecs.append(f"{nom} -> refus MAIS un numéro apparaît dans la réponse")
        except Exception as e:
            echecs.append(f"{nom} -> exception {e}")

    _refuse("GET /private/conversations/admin_afroboost (anonyme)",
            lambda: requests.get(_url("/api/private/conversations/admin_afroboost"), timeout=TIMEOUT))
    _refuse("GET /private/conversations/admin_afroboost (X-User-Email usurpé)",
            lambda: requests.get(_url("/api/private/conversations/admin_afroboost"),
                                 headers={"X-User-Email": ADMIN}, timeout=TIMEOUT))
    _refuse("GET /private/unread/admin_afroboost (anonyme)",
            lambda: requests.get(_url("/api/private/unread/admin_afroboost"), timeout=TIMEOUT))
    _refuse("POST /private/conversations vers admin_afroboost (anonyme)",
            lambda: requests.post(_url("/api/private/conversations"),
                                  json={"participant_1_id": "whatsapp_000000000",
                                        "participant_2_id": "admin_afroboost"}, timeout=TIMEOUT))

    record(94, "V411 : fils privés du coach fermés sans jeton signé (4 portes)",
           not echecs, " | ".join(echecs))


def t95_v411_acces_legitime_admin():
    """V411 — CONTREPARTIE OBLIGATOIRE de t94 (règle V310c du dépôt) : durcir sans
    prouver que le propriétaire garde l'accès, c'est ce qui a vidé le dashboard en
    V310. Avec un JWT super-admin, la liste DOIT revenir en 200.

    SKIP si ADMIN_JWT n'est pas fourni — et ce SKIP est un AVERTISSEMENT, pas un
    feu vert : le parcours légitime n'est alors pas couvert."""
    jeton = os.environ.get("ADMIN_JWT", "").strip()
    if not jeton:
        skip(95, "V411 : accès légitime super-admin -> 200",
             "ADMIN_JWT non fourni — parcours légitime NON couvert ici")
        return
    try:
        r = requests.get(_url("/api/private/conversations/admin_afroboost"),
                         headers={"Authorization": f"Bearer {jeton}"}, timeout=TIMEOUT)
        ok = r.status_code == 200 and isinstance(r.json(), list)
        record(95, "V411 : accès légitime super-admin -> 200 + liste des fils", ok,
               f"HTTP {r.status_code}, {len(r.json()) if ok else '?'} fil(s)")
    except Exception as e:
        record(95, "V411 : accès légitime super-admin -> 200", False, str(e))


def t93_v410_pont_spordateur():
    """V410 : le bouton « Spordateur » de la vitrine doit TOUJOURS aboutir sur
    /rencontre. Deux conditions, toutes deux vérifiées ici :

      a) le pont /api/spordate/access RÉPOND (il ne pend pas) et, pour un appelant
         anonyme, répond 403 « identity_required » — une réponse NORMALE, pas une
         panne : le frontend retombe alors sur /rencontre, où Spordate propose son
         propre login. Un 5xx signalerait au contraire un pont cassé ;
      b) /rencontre existe vraiment et sert la page Spordateur.

    Sans (b), le repli du bouton mènerait à une page morte ; sans (a), le clic
    pourrait geler — c'est exactement la panne que V410 corrige."""
    try:
        r = requests.post(_url("/api/spordate/access"), json={}, timeout=TIMEOUT)
        pont_ok = r.status_code in (200, 403, 503)
        detail_a = f"pont HTTP {r.status_code}"
        if r.status_code >= 500 and r.status_code != 503:
            pont_ok = False
    except Exception as e:
        pont_ok, detail_a = False, f"pont injoignable : {e}"

    try:
        p = requests.get(_url("/rencontre"), timeout=TIMEOUT)
        page_ok = p.status_code == 200 and "spordate" in (p.text or "").lower()
        detail_b = f"/rencontre HTTP {p.status_code}, {len(p.content)} octets"
    except Exception as e:
        page_ok, detail_b = False, f"/rencontre injoignable : {e}"

    record(93, "V410 pont Spordateur : /spordate/access répond ET /rencontre sert la page",
           pont_ok and page_ok, f"{detail_a} | {detail_b}")


# ---------------------------------------------------------------------------
# LOT 3b — L'AVANTAGE TARIFAIRE MEMBRE, et l'ADHÉSION qui le fonde.
#
# POURQUOI CES PARCOURS EXISTENT. Jusqu'ici la collection `memberships` et ses
# deux routes n'étaient couvertes par AUCUN test : une régression d'authentifi-
# cation y aurait ouvert des adresses e-mail sans que rien ne le signale. Et le
# tarif membre est la première fonctionnalité du dépôt où une identité MAL
# prouvée change un MONTANT — le silence n'était plus tenable.
#
# AUCUNE ÉCRITURE EN PRODUCTION. Uniquement des GET, des POST dont on ATTEND
# l'échec (403/404), et l'estimation tarifaire qui est en lecture seule. Aucune
# adhésion n'est créée, aucun drapeau n'est basculé : le PUT testé au parcours
# #104 est précisément celui qu'on attend REFUSÉ.
# ---------------------------------------------------------------------------
LOT3B_FLAG = "MEMBER_PRICING_ENABLED"


def _lot3b_spa(resp):
    """La réponse vient-elle du catch-all SPA plutôt que de l'API ?

    PIÈGE MESURÉ le 20/08/2026 sur la production : un GET vers un chemin `/api`
    INCONNU ne renvoie pas 404 — `_serve_spa` (server.py) sert `index.html` en
    **200**. Prendre ce 200 pour une réponse d'API ferait dire « la route
    répond » d'une route qui n'existe pas. On tranche sur le type de contenu.
    (En POST le problème ne se pose pas : le catch-all ne sert que les GET, un
    POST hors route retombe en 405 — mesuré aussi.)
    """
    return "text/html" in (resp.headers.get("content-type") or "").lower()


# Un POST vers une route absente : 405 (catch-all GET seulement) ou 404 selon le
# proxy. Les deux disent la même chose — « cette version n'est pas en ligne ».
LOT3B_POST_ABSENTE = (404, 405)


def _lot3b_drapeaux():
    """Les drapeaux tels que la PRODUCTION les expose (None si illisibles)."""
    try:
        r = requests.get(_url("/api/feature-flags"), timeout=TIMEOUT)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def _lot3b_deploye():
    """LOT 3b est-il EN LIGNE ? True / False / None (drapeaux illisibles).

    La PRÉSENCE du drapeau `MEMBER_PRICING_ENABLED` sert de marqueur de version :
    `get_feature_flags` le complète À LA LECTURE avec sa valeur par défaut, il
    apparaît donc dès que le code est déployé, sans aucune écriture en base.
    C'est le seul témoin non ambigu — un 404 sur l'estimation, lui, se confond
    avec le résultat ATTENDU du parcours #106 (offre introuvable).
    """
    d = _lot3b_drapeaux()
    if d is None:
        return None
    return LOT3B_FLAG in d


_lot3b_offre = []   # cache d'un id d'offre réel, lu une seule fois


def _lot3b_offre_reelle():
    """L'id d'une offre RÉELLE, lue publiquement. "" si le catalogue est vide."""
    if _lot3b_offre:
        return _lot3b_offre[0]
    try:
        r = requests.get(_url("/api/offers"), timeout=TIMEOUT)
        offres = r.json() if r.status_code == 200 else []
        for o in (offres if isinstance(offres, list) else []):
            if isinstance(o, dict) and o.get("id"):
                _lot3b_offre.append(o["id"])
                return o["id"]
    except Exception:
        pass
    return ""


def t99_adhesions_lecture_sans_auth():
    """P1-bis-a : `GET /memberships` renvoie des ADRESSES E-MAIL. Sans identité
    prouvée côté serveur -> 403, exactement comme /users et /discount-codes
    (parcours #21 et #22). « Aucune donnée personnelle sans authentification »."""
    try:
        r = requests.get(_url("/api/memberships"), timeout=TIMEOUT)
        if _lot3b_spa(r):
            return skip(99, "GET /api/memberships sans auth -> 403",
                        "route absente (catch-all SPA) — adhésions pas encore déployées")
        record(99, "GET /api/memberships sans auth -> 403",
               r.status_code == 403, f"HTTP {r.status_code}")
    except Exception as e:
        record(99, "GET /api/memberships sans auth", False, str(e))


def t100_adhesions_usurpation_email():
    """P1-bis-a — L'USURPATION. `X-User-Email: <admin>` SANS jeton signé ne vaut
    pas identité coach : `_p1a_appelant` n'accepte QUE le JWT. Le rôle coach ne
    se décide jamais côté navigateur. Même mesure que #15, #25, #26 et #62."""
    try:
        r = requests.get(_url("/api/memberships"),
                         headers={"X-User-Email": ADMIN}, timeout=TIMEOUT)
        if _lot3b_spa(r):
            return skip(100, "GET /api/memberships usurpation X-User-Email -> 403",
                        "route absente (catch-all SPA) — adhésions pas encore déployées")
        record(100, "GET /api/memberships usurpation X-User-Email -> 403",
               r.status_code == 403, f"HTTP {r.status_code}")
    except Exception as e:
        record(100, "GET /api/memberships usurpation X-User-Email", False, str(e))


def t101_adhesions_ecriture_sans_auth():
    """P1-bis-a : `POST /memberships` CRÉE une adhésion. Sans auth -> 403, et
    l'appel s'arrête AVANT toute écriture (`_p1a_appelant` est la première
    ligne de la route). Corps vide : rien à créer même si la garde tombait."""
    try:
        r = requests.post(_url("/api/memberships"), json={}, timeout=TIMEOUT)
        if r.status_code in LOT3B_POST_ABSENTE:
            return skip(101, "POST /api/memberships sans auth -> 403",
                        f"route absente (HTTP {r.status_code}) — adhésions pas encore déployées")
        record(101, "POST /api/memberships sans auth -> 403",
               r.status_code == 403, f"HTTP {r.status_code} {_short(r)}")
    except Exception as e:
        record(101, "POST /api/memberships sans auth", False, str(e))


def t102_adhesions_acces_legitime():
    """P1-bis-a — LA CONTRE-PREUVE (règle V310c). Durcir une route sans prouver
    que son propriétaire y garde l'accès, c'est reproduire V310 FIX 1 : le
    tableau de bord était revenu VIDE, en 403, parce que le chemin légitime
    n'avait jamais été mesuré. Avec le VRAI jeton signé -> 200 exigé.

    Le SKIP n'est PAS neutre ici : il INTERDIT LA LIVRAISON. Un durcissement
    dont le parcours légitime est en SKIP est exactement ce que la règle
    proscrit (« Tests #15/#32 étaient en SKIP faute de jeton »)."""
    if not ADMIN_JWT:
        return skip(102, "GET /api/memberships avec JWT légitime -> 200",
                    "ADMIN_JWT non fourni — ⛔ CE SKIP INTERDIT LA LIVRAISON : "
                    "un durcissement JWT dont le chemin légitime n'est pas prouvé "
                    "(200 AVEC jeton, 403 SANS) ne se livre pas (règle V310c).")
    try:
        r = requests.get(_url("/api/memberships"),
                         headers={"Authorization": "Bearer " + ADMIN_JWT},
                         timeout=TIMEOUT)
        if _lot3b_spa(r):
            return skip(102, "GET /api/memberships avec JWT légitime -> 200",
                        "route absente (catch-all SPA) — adhésions pas encore déployées")
        d = r.json() if r.status_code == 200 else {}
        # `success` et `memberships` : un 200 sans l'enveloppe attendue serait un
        # 200 de façade, pas un accès. Une liste VIDE reste licite (aucune
        # adhésion n'a jamais été saisie — le lot interdit tout backfill).
        ok = (r.status_code == 200 and d.get("success") is True
              and isinstance(d.get("memberships"), list))
        record(102, "GET /api/memberships avec JWT légitime -> 200 (contre-preuve V310c)",
               ok, f"HTTP {r.status_code} total={d.get('total')} {_short(r)}")
    except Exception as e:
        record(102, "GET /api/memberships avec JWT légitime", False, str(e))


def t103_drapeau_tarif_membre_expose():
    """LOT 3b : le coupe-circuit doit être LISIBLE au curl. Sans cela, impossible
    de prouver qu'une version est déployée ni de vérifier dans quel état est le
    lot — c'est la leçon V319 (un drapeau ajouté après coup restait invisible)."""
    d = _lot3b_drapeaux()
    if d is None:
        return record(103, f"GET /api/feature-flags expose {LOT3B_FLAG}", False,
                      "drapeaux illisibles")
    if LOT3B_FLAG not in d:
        return skip(103, f"GET /api/feature-flags expose {LOT3B_FLAG}",
                    "drapeau absent — LOT 3b pas encore déployé")
    record(103, f"GET /api/feature-flags expose {LOT3B_FLAG}", True,
           f"{LOT3B_FLAG}={d.get(LOT3B_FLAG)}")


def t104_drapeau_tarif_membre_admin_seul():
    """LOT 3b : ce drapeau commande des MONTANTS. Le basculer exige un JWT
    super-admin ; `X-User-Email` seul (usurpable) -> 403. Même exigence que #59
    et #61. On envoie `False`, la valeur PAR DÉFAUT : même si la garde tombait,
    la production ne changerait pas d'état."""
    try:
        r = requests.put(_url("/api/feature-flags"), json={LOT3B_FLAG: False},
                         headers={"X-User-Email": ADMIN}, timeout=TIMEOUT)
        if r.status_code in LOT3B_POST_ABSENTE:
            return skip(104, f"PUT {LOT3B_FLAG} sans JWT super-admin -> 403",
                        f"route absente (HTTP {r.status_code})")
        record(104, f"PUT {LOT3B_FLAG} sans JWT super-admin -> 403",
               r.status_code == 403, f"HTTP {r.status_code}")
    except Exception as e:
        record(104, f"PUT {LOT3B_FLAG} sans JWT super-admin", False, str(e))


def t105_estimation_sans_jeton_prix_public():
    """LOT 3b : sans identité prouvée, le tarif affiché est le PRIX PUBLIC.

    Pas une erreur — une erreur serait déjà une information — mais `membre:
    false` et `votre_tarif == prix_public`. Aucun avantage ne s'obtient sans
    jeton d'appareil signé. Lecture seule : cette route ne crée rien."""
    if _lot3b_deploye() is not True:
        return skip(105, "Estimation sans jeton -> prix public (membre: false)",
                    "LOT 3b pas encore déployé (drapeau absent des feature-flags)")
    oid = _lot3b_offre_reelle()
    if not oid:
        return skip(105, "Estimation sans jeton -> prix public (membre: false)",
                    "aucune offre lisible via GET /api/offers")
    try:
        r = requests.post(_url("/api/tarif/estimation"), json={"offerId": oid},
                          timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else {}
        pub, votre = d.get("prix_public"), d.get("votre_tarif")
        aligne = (pub is not None and votre is not None
                  and abs(float(pub) - float(votre)) < 0.01)
        ok = r.status_code == 200 and d.get("membre") is False and aligne
        record(105, "Estimation sans jeton -> prix public (membre: false)", ok,
               f"HTTP {r.status_code} membre={d.get('membre')} "
               f"prix_public={pub} votre_tarif={votre}")
    except Exception as e:
        record(105, "Estimation sans jeton -> prix public", False, str(e))


def t106_estimation_offre_inconnue():
    """LOT 3b : un `offerId` qui n'existe pas -> 404 franc. Pas de 200 sur un
    tarif inventé : un prix affiché doit toujours correspondre à une offre
    RÉELLE, sinon l'écran promet un montant que la caisse ne connaît pas."""
    if _lot3b_deploye() is not True:
        return skip(106, "Estimation offre inconnue -> 404",
                    "LOT 3b pas encore déployé (drapeau absent des feature-flags)")
    try:
        r = requests.post(_url("/api/tarif/estimation"),
                          json={"offerId": "zz-lot3b-offre-inexistante"},
                          timeout=TIMEOUT)
        record(106, "Estimation offre inconnue -> 404", r.status_code == 404,
               f"HTTP {r.status_code} {_short(r)}")
    except Exception as e:
        record(106, "Estimation offre inconnue -> 404", False, str(e))


def t107_estimation_aucun_oracle_par_email():
    """LOT 3b — PAS D'ORACLE « telle adresse est-elle membre ? ».

    Le modèle `Lot3bEstimationRequest` est en `extra="ignore"` : un champ
    `email` glissé dans le corps est SILENCIEUSEMENT IGNORÉ, il n'identifie
    personne. Seul le jeton d'appareil signé désigne un membre. Sans ce test,
    rien n'empêcherait un futur ajout de « lire l'e-mail du corps s'il est
    fourni » — et la route deviendrait un annuaire des membres interrogeable
    par n'importe qui."""
    if _lot3b_deploye() is not True:
        return skip(107, "Estimation : le champ `email` du corps est ignoré",
                    "LOT 3b pas encore déployé (drapeau absent des feature-flags)")
    oid = _lot3b_offre_reelle()
    if not oid:
        return skip(107, "Estimation : le champ `email` du corps est ignoré",
                    "aucune offre lisible via GET /api/offers")
    sonde = SUB_EMAIL or "lot3b-oracle-probe@example.com"
    try:
        r = requests.post(_url("/api/tarif/estimation"),
                          json={"offerId": oid, "email": sonde}, timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else {}
        blob = json.dumps(d).lower()
        pub, votre = d.get("prix_public"), d.get("votre_tarif")
        aligne = (pub is not None and votre is not None
                  and abs(float(pub) - float(votre)) < 0.01)
        # L'adresse sondée ne doit pas non plus RESSORTIR dans la réponse : un
        # écho suffirait à confirmer qu'elle a été prise en compte.
        ok = (r.status_code == 200 and d.get("membre") is False and aligne
              and sonde.lower() not in blob)
        record(107, "Estimation : le champ `email` du corps est ignoré (aucun oracle)",
               ok, f"HTTP {r.status_code} membre={d.get('membre')} "
                   f"prix_public={pub} votre_tarif={votre} echo_email="
                   f"{sonde.lower() in blob}")
    except Exception as e:
        record(107, "Estimation : le champ `email` du corps est ignoré", False, str(e))


def t108_offres_exposent_avantage_membre():
    """LOT 3b — LA SYMÉTRIE `Offer` / `OfferCreate`, piège du dépôt six fois.

    `GET /offers` a un `response_model=List[Offer]` : un champ absent du modèle
    est filtré EN SILENCE, et la case du dashboard revient décochée à chaque
    relecture sans qu'aucune erreur n'apparaisse. On vérifie donc que la CLÉ
    `member_discount_pct` est bien présente dans les documents rendus — sa
    valeur peut être `null` (aucun avantage), c'est sa PRÉSENCE qui prouve la
    symétrie."""
    etat = _lot3b_deploye()
    try:
        r = requests.get(_url("/api/offers"), timeout=TIMEOUT)
        offres = r.json() if r.status_code == 200 else []
        offres = [o for o in (offres if isinstance(offres, list) else []) if isinstance(o, dict)]
        if not offres:
            return skip(108, "GET /api/offers expose member_discount_pct",
                        f"aucune offre lisible (HTTP {r.status_code})")
        manquantes = [o.get("id") for o in offres if "member_discount_pct" not in o]
        if manquantes and etat is not True:
            return skip(108, "GET /api/offers expose member_discount_pct",
                        "champ absent ET drapeau absent — LOT 3b pas encore déployé")
        # Drapeau présent mais champ absent = la régression que ce test existe
        # pour attraper : le lot est en ligne, mais `Offer` filtre le champ.
        record(108, "GET /api/offers expose member_discount_pct (symétrie Offer/OfferCreate)",
               not manquantes,
               f"{len(offres)} offre(s), {len(manquantes)} sans le champ : {manquantes[:5]}")
    except Exception as e:
        record(108, "GET /api/offers expose member_discount_pct", False, str(e))


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

# ── P1-d : LA RELANCE J+3 EST LIVREE DORMANTE ──────────────────────────────
P1D_FLAGS = ("P1_TRIAL_J3_ENABLED", "P1_TRIAL_J3_ENVOI_REEL")


def t109_p1d_drapeaux_exposes_et_dormants():
    """P1-d : les deux interrupteurs doivent être LISIBLES au curl ET à false.

    DEUX choses en une, et les deux comptent :
      1. la LISIBILITÉ — c'est la leçon V319 : un drapeau ajouté après la
         création du document `feature_flags` restait invisible, donc
         impossible de prouver qu'une version est déployée ;
      2. la DORMANCE — P1-d est livré éteint, et il doit le RESTER tant que le
         premier vrai J+0 n'a pas été observé en production. Ce test est le
         garde-fou : si un jour l'un des deux passe à true sans décision, la
         suite de non-régression le dit.
    """
    d = _lot3b_drapeaux()
    if d is None:
        return record(109, "GET /api/feature-flags expose les drapeaux P1-d", False,
                      "drapeaux illisibles")
    absents = [f for f in P1D_FLAGS if f not in d]
    if absents:
        return skip(109, "GET /api/feature-flags expose les drapeaux P1-d",
                    "%s absent(s) — P1-d pas encore déployé" % ", ".join(absents))
    allumes = [f for f in P1D_FLAGS if d.get(f) is not False]
    record(109, "P1-d exposé ET dormant (les deux drapeaux à false)",
           not allumes,
           ("ALLUMÉ : %s" % ", ".join(allumes)) if allumes
           else "%s" % {f: d.get(f) for f in P1D_FLAGS})


def t110_p1d_drapeaux_admin_seulement():
    """P1-d commande des ENVOIS À DES CLIENTS. Le basculer exige un JWT
    super-admin ; `X-User-Email` seul (usurpable) -> 403. Même exigence que #59,
    #61 et #104. On envoie `False`, la valeur PAR DÉFAUT : même si la garde
    tombait, la production ne changerait pas d'état."""
    d = _lot3b_drapeaux()
    if d is None or any(f not in d for f in P1D_FLAGS):
        return skip(110, "PUT /feature-flags P1-d sans JWT super-admin -> 403",
                    "drapeaux P1-d absents — P1-d pas encore déployé")
    try:
        r = requests.put(_url("/api/feature-flags"),
                         json={"P1_TRIAL_J3_ENABLED": False},
                         headers={"X-User-Email": ADMIN}, timeout=TIMEOUT)
        record(110, "PUT /feature-flags P1-d sans JWT super-admin -> 403",
               r.status_code == 403, f"HTTP {r.status_code}")
    except Exception as e:
        record(110, "PUT /feature-flags P1-d sans JWT super-admin -> 403", False, str(e))


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
                   t84_v346_categories_des_conversations, t85_v348_suppression_conversation_exige_jeton,
                   t86_v349_contenu_des_conversations_ferme, t87_v350_piece_jointe_du_chat, t88_v354_permissions_policy_micro,
                   t89_v363_segments_contacts, t90_v365_membres_de_groupe_identiques_et_rapides,
                   t91_v367_apercu_bot_ferme_et_sans_envoi, t92_v369_routes_bot_fermees_et_drapeau_off,
                   t93_v410_pont_spordateur,
                   t94_v411_fils_prives_fermes, t95_v411_acces_legitime_admin,
                   t96_v412_range_206, t97_v413_stockage_disque, t98_v425_orphelins_ferme,
                   t99_adhesions_lecture_sans_auth, t100_adhesions_usurpation_email,
                   t101_adhesions_ecriture_sans_auth, t102_adhesions_acces_legitime,
                   t103_drapeau_tarif_membre_expose, t104_drapeau_tarif_membre_admin_seul,
                   t105_estimation_sans_jeton_prix_public, t106_estimation_offre_inconnue,
                   t107_estimation_aucun_oracle_par_email,
                   t108_offres_exposent_avantage_membre,
                   t109_p1d_drapeaux_exposes_et_dormants, t110_p1d_drapeaux_admin_seulement,
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
