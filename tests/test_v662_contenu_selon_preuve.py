# -*- coding: utf-8 -*-
"""V662 — QUEL CONTENU PART VERS QUEL APPAREIL ?

Le coeur du correctif. On remplace `webpush` par un espion et on CAPTURE la
charge reellement transmise, pour chaque abonnement :

  - appareil PROUVE (`push_verifie: True`) -> texte COMPLET (nom du cours,
    heure, actions, tag) : les rappels existants ne changent pas d'un iota.
  - appareil NON PROUVE (les 262 anterieurs)  -> charge NEUTRE : il sonne,
    il n'apprend RIEN. Ni nom de cours, ni heure, ni identifiant de
    reservation, ni code d'acces.

Hors ligne : aucun envoi reel, aucun reseau. `webpush` est intercepte.
"""
import asyncio, json, os, sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ["DB_NAME"] = "test_v662_contenu"
os.environ["JWT_SECRET"] = "banc-v662-contenu"

_ok = _ko = 0


def v(nom, cond, detail=""):
    global _ok, _ko
    if cond:
        _ok += 1
        print("  PASS  %s" % nom)
    else:
        _ko += 1
        print("  RATE  %s  -> %s" % (nom, str(detail)[:160]))


import api.server as S                                             # noqa: E402

CAPTURE = []


def _webpush_espion(subscription_info=None, data=None, **kw):
    CAPTURE.append((subscription_info.get("endpoint"), json.loads(data)))

    class _R:
        status_code = 201
    return _R()


S.webpush = _webpush_espion
S.WEBPUSH_AVAILABLE = True
S.VAPID_PRIVATE_KEY = "cle-de-banc"
S.VAPID_PUBLIC_KEY = "pub-de-banc"


async def principal():
    db = S.db
    await db.push_subscriptions.delete_many({})
    PID = "pid-contenu-v662"
    await db.push_subscriptions.insert_many([
        {"participant_id": PID, "active": True, "push_verifie": True,
         "email": "prouve@exemple.test", "updated_at": "2026-11-11T10:00:00+00:00",
         "subscription": {"endpoint": "https://fcm.test/prouve",
                          "keys": {"p256dh": "p" * 60, "auth": "a" * 20}}},
        {"participant_id": PID, "active": True,          # pas de `push_verifie`
         "updated_at": "2026-11-11T09:00:00+00:00",
         "subscription": {"endpoint": "https://fcm.test/inconnu",
                          "keys": {"p256dh": "q" * 60, "auth": "b" * 20}}},
    ])

    await S.send_push_notification(
        PID, "Ton cours dans 1 h",
        "Afro Cardio a 19:00, Salle de la Maladiere",
        {"type": "course_reminder", "reservation_id": "resa-secrete-123",
         "tag": "cours-abc", "actions": [{"action": "open", "title": "Mon cours"}]})

    recu = dict(CAPTURE)
    v("les DEUX appareils ont ete sollicites", len(recu) == 2, sorted(recu))

    plein = recu.get("https://fcm.test/prouve") or {}
    neutre = recu.get("https://fcm.test/inconnu") or {}

    print()
    print("  -- appareil PROUVE : rien ne doit avoir change --")
    v("il recoit le vrai titre", plein.get("title") == "Ton cours dans 1 h", plein.get("title"))
    v("il recoit le nom du cours et l'heure",
      "Afro Cardio" in str(plein.get("body")) and "19:00" in str(plein.get("body")), plein.get("body"))
    v("il garde le tag par cours", plein.get("tag") == "cours-abc", plein.get("tag"))
    v("il garde les actions", bool(plein.get("actions")), plein.get("actions"))
    v("il garde l'identifiant de reservation",
      (plein.get("data") or {}).get("reservation_id") == "resa-secrete-123", plein.get("data"))

    print()
    print("  -- appareil NON PROUVE : il sonne, il n'apprend rien --")
    v("titre neutre", neutre.get("title") == "Afroboost", neutre.get("title"))
    _s = json.dumps(neutre, ensure_ascii=False)
    v("AUCUN nom de cours", "Afro Cardio" not in _s, _s[:140])
    v("AUCUNE heure", "19:00" not in _s, _s[:140])
    v("AUCUN identifiant de reservation", "resa-secrete-123" not in _s, _s[:140])
    v("AUCUNE adresse e-mail", "@exemple.test" not in _s, _s[:140])
    v("aucune url portant un code d'acces", "/espace/" not in str(neutre.get("url")), neutre.get("url"))
    v("il sonne quand meme (titre + corps presents)",
      bool(neutre.get("title")) and bool(neutre.get("body")), neutre)
    v("et il invite a ouvrir l'application",
      "ouvrez l'application" in str(neutre.get("body")).lower(), neutre.get("body"))

    await db.push_subscriptions.delete_many({})


asyncio.get_event_loop().run_until_complete(principal())
print()
print("  %d/%d" % (_ok, _ok + _ko))
sys.exit(0 if _ko == 0 else 1)
