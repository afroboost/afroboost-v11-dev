#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PUSH-UI — LES NOTIFICATIONS DE RAPPEL DEVIENNENT VISIBLES.

Exécution : python3 tests/test_pushui_notifications.py

CE QUE ÇA PROUVE — sans envoyer le moindre Push, e-mail, SMS ou WhatsApp :
le serveur envoie bien l'apparence, le Service Worker la LIT enfin (il la
jetait), les deux publics restent distinguables, et les images référencées
existent réellement sur le disque.

Aucun réseau, aucune base, aucune horloge réelle.
"""
import io, json, os, re, sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-pushui:27017")

import api.server as S                                       # noqa: E402

SW = io.open(os.path.join(RACINE, "frontend", "public", "sw.js"),
             encoding="utf-8").read()
SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()

_ok = _ko = 0


def verifie(titre, condition, detail=""):
    global _ok, _ko
    if condition:
        _ok += 1
        print("PASS  %s" % titre)
    else:
        _ko += 1
        print("FAIL  %s%s" % (titre, (" — " + detail) if detail else ""))


def bloc(nom, source=None):
    """Le corps d'une fonction du fichier réel, jamais une copie."""
    _s = source if source is not None else SRC
    _d = _s.find("def %s(" % nom)
    if _d < 0:
        _d = _s.find("async def %s(" % nom)
    _f = _s.find("\ndef ", _d + 1)
    _f2 = _s.find("\nasync def ", _d + 1)
    if _f2 >= 0 and (_f < 0 or _f2 < _f):
        _f = _f2
    return _s[_d:_f if _f > 0 else len(_s)]


print("\n--- A : LE SERVEUR ENVOIE L'APPARENCE, IL NE LA GARDE PLUS POUR LUI ---")
_envoi = bloc("send_push_notification")
for _cle in ("tag", "vibrate", "actions", "image", "renotify", "requireInteraction"):
    verifie("A1. « %s » traverse le payload" % _cle, '"%s"' % _cle in _envoi, _cle)
verifie("A2. rien n'est posé quand l'appelant n'envoie rien",
        "if _val_ui is not None" in _envoi)
verifie("A3. les clés visuelles sont à la RACINE (là où sw.js les lit)",
        "_corps_payload[_cle_ui] = _val_ui" in _envoi)
verifie("A4. le commentaire qui disait « le SW ignore celles-ci » a disparu",
        "ignore celles-ci" not in _envoi)

print("\n--- B : LE SERVICE WORKER LIT ENFIN CE QU'ON LUI ENVOIE ---")
_push = SW[SW.find("self.addEventListener('push'"):SW.find("self.addEventListener('pushsubscriptionchange'")]
for _cle, _lu in (("actions", "data.actions"), ("vibrate", "data.vibrate"),
                  ("tag", "data.tag"), ("image", "data.image"),
                  ("renotify", "data.renotify"),
                  ("requireInteraction", "data.requireInteraction")):
    verifie("B1. sw.js lit « %s » du payload" % _cle, _lu in _push, _cle)
verifie("B2. les valeurs d'hier restent les DÉFAUTS (actions)",
        "{ action: 'open', title: 'Voir' }" in _push
        and "{ action: 'close', title: 'Fermer' }" in _push)
verifie("B3. les valeurs d'hier restent les DÉFAUTS (vibration)",
        "var vibration = [200, 100, 200];" in _push)
verifie("B4. le tag commun reste le défaut", "data.tag || 'afroboost-push'" in _push)

print("\n--- C : UN PAYLOAD MALFORMÉ NE FAIT PAS DISPARAÎTRE LA NOTIFICATION ---")
verifie("C1. chaque action est vérifiée avant usage",
        "typeof act.action === 'string'" in _push and "typeof act.title === 'string'" in _push)
verifie("C2. deux actions au maximum (au-delà, Android ignore)",
        "propres.length < 2" in _push)
verifie("C3. on ne retient un remplacement que s'il reste quelque chose",
        "if (propres.length) { actions = propres; }" in _push)
verifie("C4. la vibration n'accepte que des nombres bornés",
        "typeof ms === 'number'" in _push and "ms <= 5000" in _push)
verifie("C5. `image` n'est posée que si c'est une chaîne non vide",
        "typeof data.image === 'string' && data.image" in _push)

print("\n--- D : VIBRATION DEMANDÉE PAR LE LOT ---")
verifie("D1. le serveur envoie [300, 120, 300]", S.PUSH_UI_VIBRATION == [300, 120, 300],
        str(S.PUSH_UI_VIBRATION))

print("\n--- E : SILENCIEUX = NON, ET RIEN DE PLUS N'EST PROMIS ---")
verifie("E1. `silent: false` est explicite", "silent: false" in _push)
_sw_code = "\n".join(l for l in SW.split("\n") if not l.strip().startswith("//"))
verifie("E2. `silent: true` n'est posé nulle part (commentaires exclus)",
        "silent: true" not in _sw_code)

print("\n--- F : UN TAG PAR COURS, PLUS UN TAG POUR TOUT LE MONDE ---")
verifie("F1. deux cours différents -> deux tags différents",
        S.push_ui_tag_cours("62fcac27") != S.push_ui_tag_cours("23534f7c"))
verifie("F2. le MÊME cours -> le MÊME tag, quelle que soit la règle",
        S.push_ui_tag_cours("62fcac27") == S.push_ui_tag_cours("62fcac27"))
verifie("F3. sans identifiant, on retombe sur le défaut du SW",
        S.push_ui_tag_cours("") == "afroboost-push"
        and S.push_ui_tag_cours(None) == "afroboost-push")
verifie("F4. le tag ne s'étend pas sans borne", len(S.push_ui_tag_cours("x" * 500)) <= 80)

print("\n--- G : RENOTIFY / REQUIREINTERACTION ---")
verifie("G1. renotify reste VRAI par défaut", "data.renotify !== false" in _push)
verifie("G2. requireInteraction reste FAUX par défaut",
        "data.requireInteraction === true" in _push)

print("\n--- H : L'HEURE ET LE MOMENT SONT DYNAMIQUES ---")
verifie("H1. matin", S.push_ui_moment("same_day:07:00", "09:00") == "CE MATIN")
verifie("H2. après-midi", S.push_ui_moment("same_day:07:00", "14:30") == "CET APRÈS-MIDI")
verifie("H3. soir", S.push_ui_moment("same_day:07:00", "18:30") == "CE SOIR")
verifie("H4. veille (24 h / 48 h) -> DEMAIN",
        S.push_ui_moment("relative:1440m", "18:30") == "DEMAIN"
        and S.push_ui_moment("relative:2880m", "18:30") == "DEMAIN")
# Un rappel « 1 h avant » tombe le MEME jour : dire « demain » etait faux, et
# c'est ce que faisait l'ancien libelle.
verifie("H4b. regle courte (1 h / 3 h) -> le moment du jour, pas « demain »",
        S.push_ui_moment("defaut", "18:30") == "CE SOIR"
        and S.push_ui_moment("relative:180m", "09:00") == "CE MATIN")
verifie("H5. heure illisible -> un mot toujours vrai",
        S.push_ui_moment("same_day:07:00", "") == "AUJOURD'HUI"
        and S.push_ui_moment("same_day:07:00", "ab:cd") == "AUJOURD'HUI"
        and S.push_ui_moment("same_day:07:00", "99:00") == "AUJOURD'HUI")
verifie("H6. l'heure s'affiche 18H30", S.push_ui_heure("18:30") == "18H30")
verifie("H7. sans heure, aucun tiret orphelin",
        S.push_ui_titre("🔥", "same_day:07:00", "") == "🔥 AFROBOOST AUJOURD'HUI")

print("\n--- I : LE TITRE DEMANDÉ PAR LE COACH ---")
_t_nb = S.rvab_push_titre("same_day:09:30", "18:30")
_t_ok = S.n1b2_titre("same_day:09:30", "18:30")
verifie("I1. NON-RÉSERVÉ : 🔥 AFROBOOST CE SOIR — 18H30",
        _t_nb == "🔥 AFROBOOST CE SOIR — 18H30", _t_nb)
verifie("I2. RÉSERVÉ : 🎧 AFROBOOST CE SOIR — 18H30",
        _t_ok == "🎧 AFROBOOST CE SOIR — 18H30", _t_ok)
verifie("I3. les deux publics restent distinguables au premier coup d'œil",
        _t_nb != _t_ok)

print("\n--- J : DEUX CORPS, DEUX MESSAGES QUI NE SE CONTREDISENT PAS ---")
_c_nb = S.rvab_push_corps("Cours à l'unité")
_c_ok = S.n1b2_corps("same_day:09:30", "Cours à l'unité", "18:30")
verifie("J1. NON-RÉSERVÉ : constate l'absence de réservation",
        "pas encore réservé" in _c_nb, _c_nb)
verifie("J2. NON-RÉSERVÉ : invite à réserver", "Réserve maintenant" in _c_nb, _c_nb)
verifie("J3. RÉSERVÉ : annonce la place tenue",
        "ta place est réservée" in _c_ok, _c_ok)
verifie("J4. RÉSERVÉ : n'invite JAMAIS à réserver",
        "réserve ta place" not in _c_ok.lower()
        and "réserver" not in (_t_ok + _c_ok).lower(), _c_ok)
verifie("J5. RÉSERVÉ : porte l'heure du rendez-vous", "18:30" in _c_ok, _c_ok)
_c_ok_sans_h = S.n1b2_corps("same_day:09:30", "Danse", "")
verifie("J6. RÉSERVÉ sans heure : aucun « à » orphelin",
        "tout à l'heure" in _c_ok_sans_h and "à  " not in _c_ok_sans_h, _c_ok_sans_h)
verifie("J7. les deux corps diffèrent", _c_nb != _c_ok)
verifie("J8. le nom du cours est porté par les deux",
        "Cours à l'unité" in _c_nb and "Cours à l'unité" in _c_ok)

print("\n--- K : LES ACTIONS, ET CE QU'ELLES OUVRENT ---")
verifie("K1. NON-RÉSERVÉ -> « 🎟️ Réserver maintenant »",
        S.PUSH_UI_ACTIONS_RESERVER[0]["title"] == "🎟️ Réserver maintenant")
verifie("K2. RÉSERVÉ -> « 👟 Voir mon cours »",
        S.PUSH_UI_ACTIONS_MON_COURS[0]["title"] == "👟 Voir mon cours")
verifie("K3. les deux gardent l'identifiant `open`, celui que sw.js sait ouvrir",
        S.PUSH_UI_ACTIONS_RESERVER[0]["action"] == "open"
        and S.PUSH_UI_ACTIONS_MON_COURS[0]["action"] == "open")
_clic = SW[SW.find("self.addEventListener('notificationclick'"):]
verifie("K4. seul « close » ferme ; toute autre action ouvre l'URL",
        "event.action === 'close'" in _clic and "notification.data" in _clic)
verifie("K5. les deux publics ont une seconde action « Fermer »",
        S.PUSH_UI_ACTIONS_RESERVER[1]["action"] == "close"
        and S.PUSH_UI_ACTIONS_MON_COURS[1]["action"] == "close")

print("\n--- L : LES FICHIERS RÉFÉRENCÉS EXISTENT VRAIMENT ---")
_pub = os.path.join(RACINE, "frontend", "public")
for _f in ("logo192.png", "notification-badge-96.png", "og-image.png"):
    verifie("L1. %s est bien servi par le site" % _f,
            os.path.exists(os.path.join(_pub, _f)), _f)
verifie("L2. l'image du rappel est celle qui existe",
        S.PUSH_UI_IMAGE_COURS == "/og-image.png"
        and os.path.exists(os.path.join(_pub, "og-image.png")))
verifie("L3. `icon` et `badge` gardent leurs rôles V445",
        "icon: '/logo192.png'" in _push and "badge: '/notification-badge-96.png'" in _push)
_m = re.search(r"var CACHE_NAME = 'afroboost-v(\d+)'", SW)
verifie("L4. CACHE_NAME bumpé (sinon le SW en cache jette encore ces champs)",
        bool(_m) and int(_m.group(1)) >= 503, _m.group(0) if _m else "absent")

print("\n--- M : LES DEUX SITES D'APPEL ENVOIENT BIEN TOUT ÇA ---")
for _nom, _attendu in (("cron_reservation_reminders", "PUSH_UI_ACTIONS_MON_COURS"),
                       ("_rvab_passage", "PUSH_UI_ACTIONS_RESERVER")):
    _b = bloc(_nom)
    verifie("M1. %s : actions" % _nom, _attendu in _b)
    verifie("M2. %s : vibration" % _nom, "PUSH_UI_VIBRATION" in _b)
    verifie("M3. %s : image" % _nom, "PUSH_UI_IMAGE_COURS" in _b)
    verifie("M4. %s : tag par cours" % _nom, "push_ui_tag_cours(" in _b)

print("\n--- O : LE CLIC MÈNE À LA BONNE PAGE, APPLICATION OUVERTE OU FERMÉE ---")
_APP = io.open(os.path.join(RACINE, "frontend", "src", "App.js"), encoding="utf-8").read()
_CW = io.open(os.path.join(RACINE, "frontend", "src", "components", "ChatWidget.js"),
              encoding="utf-8").read()
verifie("O1. application FERMÉE : le SW ouvre l'url de la notification",
        "self.clients.openWindow(cible)" in _clic)
verifie("O2. application OUVERTE : on emmène vraiment la fenêtre sur la page",
        "client.navigate(cible)" in _clic or "window.location.assign(chemin)" in _APP)
verifie("O3. on ne recharge pas quand on y est déjà",
        "if (chemin !== ici)" in _APP and "client.url !== cible" in _clic)
verifie("O4. le chat ne s'ouvre plus par-dessus une notification qui vise une page",
        "if (vise && vise !== '/') return;" in _CW)
verifie("O5. la prospection garde son chemin (aucune régression READ-P2)",
        "prospection=1" in _APP and "prospection=1" in _CW)

print("\n--- P : LA DESTINATION EST ABSOLUE (le defaut du 09/09) ---")
# Le serveur envoie « https://afroboost.com/espace/<CODE> », pas un chemin.
# Les gardes qui testaient `url.charAt(0) === '/'` ne se declenchaient donc
# JAMAIS : rien ne naviguait, et le chat s'ouvrait par-dessus.
verifie("P1. le lien de l'espace est bien ABSOLU (c'est la cause du defaut)",
        S.rv2_lien_espace("AFR-9CB0A0").startswith("http"), S.rv2_lien_espace("AFR-9CB0A0"))
# Le code EXECUTE, commentaires exclus : App.js explique le defaut en toutes
# lettres, et une recherche brute prendrait cette explication pour du code.
def _code_js(txt):
    return "\n".join(l for l in txt.split("\n") if not l.strip().startswith("//"))
verifie("P2. plus aucune garde ne suppose un chemin relatif",
        "url.charAt(0) === '/'" not in _code_js(_APP)
        and "url.charAt(0) === '/'" not in _code_js(_CW))
verifie("P3. sw.js ramene toute destination a une url absolue",
        "new URL(targetUrl, self.location.origin)" in _clic)
verifie("P4. sw.js emmene la fenetre DEJA OUVERTE sur la page visee",
        "client.navigate(cible)" in _clic
        and "typeof client.navigate === 'function'" in _clic)
verifie("P5. si `navigate` manque ou echoue, le message d'hier reste le repli",
        ".catch(function () {" in _clic and "client.postMessage(message);" in _clic)
verifie("P6. prospection et chat gardent le chemin par MESSAGE (READ-P2 intact)",
        "var parMessage = (cible.indexOf('prospection=1') !== -1" in _clic
        and "|| cible.indexOf('openChat') !== -1);" in _clic)
verifie("P7. application fermee : la fenetre s'ouvre sur l'url absolue",
        "self.clients.openWindow(cible)" in _clic)
verifie("P8. App n'accepte que le MEME site (une url recue ne redirige pas ailleurs)",
        "u.origin === window.location.origin" in _APP)
verifie("P9. App navigue sur le chemin, pas sur l'url brute",
        "window.location.assign(chemin)" in _APP)
verifie("P10. le chat ne s'ouvre plus quand la notification vise une page",
        "if (vise && vise !== '/') return;" in _CW)

print("\n--- N : CE LOT N'ENVOIE RIEN ---")
# La preuve se lit sur l'ARBRE du fichier, pas sur son texte : un banc qui
# cherche « resend » dans ses propres lignes se dénonce lui-même.
import ast as _ast
_INTERDITS = {"webpush", "send", "post", "request", "urlopen",
              "send_push_notification", "send_push_by_email",
              "rv2_envoyer_email_rappel"}
_appels = set()
for _n in _ast.walk(_ast.parse(io.open(os.path.abspath(__file__), encoding="utf-8").read())):
    if isinstance(_n, _ast.Call):
        _f = _n.func
        _appels.add(_f.attr if isinstance(_f, _ast.Attribute)
                    else (_f.id if isinstance(_f, _ast.Name) else ""))
verifie("N1. aucun appel d'envoi dans ce banc (lecture de l'arbre)",
        not (_appels & _INTERDITS), str(sorted(_appels & _INTERDITS)))
verifie("N2. aucun module réseau importé par ce banc",
        not {"requests", "httpx", "pywebpush", "aiohttp"}
        & {_a.name.split(".")[0] for _n in _ast.walk(
            _ast.parse(io.open(os.path.abspath(__file__), encoding="utf-8").read()))
           if isinstance(_n, _ast.Import) for _a in _n.names})

print("\n%d PASS / %d FAIL" % (_ok, _ko))
sys.exit(1 if _ko else 0)
