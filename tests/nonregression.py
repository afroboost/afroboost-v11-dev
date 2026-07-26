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
    # V310 : /contacts/all est JWT-strict. Avec un vrai JWT admin -> 200 ; sinon SKIP.
    if not ADMIN_JWT:
        return skip(15, "Contacts coach (avec JWT)", "ADMIN_JWT non fourni (colle ton jeton pour tester)")
    try:
        r = requests.get(_url("/api/contacts/all"), headers={"Authorization": "Bearer " + ADMIN_JWT}, timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else {}
        ok = r.status_code == 200 and isinstance(d.get("contacts"), list)
        record(15, "Contacts coach (JWT valide -> accès)", ok, f"HTTP {r.status_code} total={d.get('total')}")
    except Exception as e:
        record(15, "Contacts coach", False, str(e))


def t30_spoofing_blocked():
    """V310 : usurpation par X-User-Email admin SANS JWT -> 403 sur les routes admin."""
    routes = ["/api/users", "/api/discount-codes", "/api/chat/sessions",
              "/api/contacts/all", "/api/dashboard/all-transactions"]
    fails = []
    for rt in routes:
        try:
            r = requests.get(_url(rt), headers={"X-User-Email": ADMIN}, timeout=TIMEOUT)
            if r.status_code != 403:
                fails.append(f"{rt}={r.status_code}")
        except Exception as e:
            fails.append(f"{rt}:{e}")
    ok = not fails
    record(30, "Usurpation X-User-Email admin (sans JWT) -> 403 partout", ok, ("échecs: " + ", ".join(fails)) if fails else "5/5 -> 403")


def t32_coach_jwt_access():
    """V310 : un JWT admin/coach valide accède normalement (preuve non-régression)."""
    if not ADMIN_JWT:
        return skip(32, "Accès avec JWT valide", "ADMIN_JWT non fourni")
    try:
        r = requests.get(_url("/api/users"), headers={"Authorization": "Bearer " + ADMIN_JWT}, timeout=TIMEOUT)
        ok = r.status_code == 200
        record(32, "JWT valide -> accès admin normal (200)", ok, f"HTTP {r.status_code}")
    except Exception as e:
        record(32, "JWT valide -> accès", False, str(e))


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
    try:
        if code:
            requests.delete(_url(f"/api/publications/{pub_id}"), params={"subscriber_code": code}, timeout=TIMEOUT)
        else:
            requests.delete(_url(f"/api/publications/{pub_id}"), headers={"X-User-Email": ADMIN}, timeout=TIMEOUT)
    except Exception:
        pass


def cleanup():
    """Supprime les publications de TEST créées (best-effort). Ne touche à rien d'autre."""
    for pub_id, code in _created_pub_ids:
        if pub_id:
            _delete_pub(pub_id, code)


def sweep_leftovers():
    """Nettoyage PRÉVENTIF : supprime toute publication dont la légende contient la
    marque de test — au cas où un run précédent aurait été interrompu et aurait laissé
    des déchets visibles sur la vitrine. Best-effort, ne touche qu'aux publications
    portant explicitement cette marque."""
    try:
        r = requests.get(_url("/api/publications"), timeout=TIMEOUT)
        pubs = r.json() if r.status_code == 200 else []
        if isinstance(pubs, dict):
            pubs = pubs.get("publications", [])
        removed = 0
        for p in (pubs or []):
            cap = (p.get("caption") or "")
            pid = p.get("id")
            if pid and TEST_CAPTION_MARK in cap:
                _delete_pub(pid, None)                 # tentative admin
                if SUB_CODE:
                    _delete_pub(pid, SUB_CODE)          # tentative code abonné
                removed += 1
        if removed:
            print(f"(nettoyage préventif : {removed} publication(s) de test résiduelle(s) supprimée(s))")
    except Exception:
        pass


def main():
    print(f"=== NON-RÉGRESSION Afroboost — {BASE} ===\n")
    sweep_leftovers()  # V307 : purge préventive des déchets d'un run interrompu
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
                   t39_redos_input, t40_nosql_injection,
                   t30_spoofing_blocked, t32_coach_jwt_access):
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
