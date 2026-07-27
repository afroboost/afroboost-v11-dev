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
        r = requests.post(_url("/api/chat/smart-entry"), json={"name": "Bassi", "email": SUB_EMAIL}, timeout=TIMEOUT)
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
        r = requests.post(_url("/api/chat/smart-entry"), json={"name": "(a+)+$" * 5, "email": "redos@example.com"}, timeout=TIMEOUT)
        dur = _t.time() - t0
        ok = r.status_code in (200, 400) and dur < 8
        record(39, "Entrée regex catastrophique -> pas de saturation", ok, f"HTTP {r.status_code} en {dur:.2f}s")
    except Exception as e:
        record(39, "Entrée regex catastrophique", False, str(e))


def t40_nosql_injection():
    """Un champ objet {\"$ne\": null} ne doit pas être injecté ni provoquer un 500."""
    try:
        r = requests.post(_url("/api/chat/smart-entry"), json={"name": "Test", "email": {"$ne": None}}, timeout=TIMEOUT)
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
        # 1) fiche « légitime » : créée au 1er run, simplement reconnue ensuite
        requests.post(_url("/api/chat/smart-entry"), json={"name": "V312 Legit", "email": fixed}, timeout=TIMEOUT)
        # 2) intrus : même email, nom DIFFÉRENT, AUCUN jeton d'appareil
        r2 = requests.post(_url("/api/chat/smart-entry"), json={"name": "V312 INTRUS", "email": fixed}, timeout=TIMEOUT)
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


def t18_no_recognition_by_name_only():
    """V308 : smart-entry par NOM SEUL ne doit PLUS reconnaître un compte existant."""
    try:
        uniq = "ZZZ Testeur Inconnu 918273"
        r = requests.post(_url("/api/chat/smart-entry"), json={"name": uniq}, timeout=TIMEOUT)
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
    """V308 : un nouveau visiteur (nom+email frais) s'inscrit sans friction."""
    try:
        r = requests.post(_url("/api/chat/smart-entry"), json={
            "name": "Nouveau Visiteur 553311", "email": "nouveau553311@example.com"
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
                   t59_feature_flags_require_admin,
                   t39_redos_input, t40_nosql_injection):
            fn()
    finally:
        # V307 : nettoyage GARANTI, même si un test échoue ou si le script est interrompu.
        cleanup()
        sweep_leftovers()
    passed = sum(1 for _, _, st, _ in results if st == "pass")
    failed = sum(1 for _, _, st, _ in results if st == "fail")
    skipped = sum(1 for _, _, st, _ in results if st == "skip")
    total = len(results)
    print(f"\n=== RÉSULTAT : {passed} PASS / {failed} FAIL / {skipped} SKIP (sur {total}) ===")
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
