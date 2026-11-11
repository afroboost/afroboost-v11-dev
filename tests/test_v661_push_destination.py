# -*- coding: utf-8 -*-
"""V661 — UN RAPPEL DE COURS DOIT OUVRIR LE COURS, PAS LE CHAT.

LE DEFAUT MESURE. `send_push_notification` retombe sur « /?openChat=true »
quand la charge ne porte pas d'`url` :

    _push_url = (data or {}).get("url") or "/?openChat=true"

Or la charge du rappel de cours ne portait AUCUNE url. Toucher la notification
« Ton cours dans 1 h » ouvrait donc une conversation. L'adresse juste etait
pourtant calculee trois lignes plus haut, pour l'e-mail.

Ce banc est HORS LIGNE : il lit la source, sans base ni reseau.
"""
import io, os, re, sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
SW = io.open(os.path.join(RACINE, "frontend", "public", "sw.js"), encoding="utf-8").read()

_ok = _ko = 0


def v(nom, cond, detail=""):
    global _ok, _ko
    if cond:
        _ok += 1
        print("  PASS  %s" % nom)
    else:
        _ko += 1
        print("  RATE  %s  %s" % (nom, str(detail)[:90]))


print("== V661 — la destination du rappel ==")

_bloc = re.search(r'\{"type": "course_reminder".*?PUSH_UI_IMAGE_COURS\}', SRC, re.S)
v("la charge du rappel de cours existe", bool(_bloc))
_b = _bloc.group(0) if _bloc else ""
# On compare le CODE, pas les commentaires : les lignes `#` expliquent
# justement pourquoi `_e2_espace` est absent, et les y chercher ferait
# echouer le controle pour la raison inverse de celle qu'il surveille.
_bc = "\n".join(l for l in _b.split("\n") if not l.strip().startswith("#"))

# =====================================================================
# V661b — CE BANC GARDE MAINTENANT LA PORTE FERMEE, PAS OUVERTE
# =====================================================================
# V661 posait l'url de l'espace dans la charge. Retire : cette url CONTIENT
# le code d'acces, et `POST /push/subscribe` n'exige aucune authentification
# tout en lisant `email` dans le corps de la requete. N'importe qui peut donc
# recevoir les push de quelqu'un d'autre ; il ne doit rien y trouver qui
# OUVRE son espace.
v("AUCUNE url dans la charge du rappel", '"url"' not in _bc, _bc[:140])
v("AUCUN code d'acces dans la charge du rappel", '_e2_espace' not in _bc)
# L'url de l'espace reste calculee — pour l'E-MAIL, qui part a une adresse
# verifiee. C'est le canal qui change le risque, pas le lien.
v("l'espace reste envoye par e-mail (canal verifie)",
  '_e2_espace = (rv2_lien_espace' in SRC and SRC.count('_e2_espace') >= 3)

_url = re.search(r'_push_url = \(data or \{\}\)\.get\("url"\) or "([^"]+)"', SRC)
v("le repli du serveur s'applique donc", bool(_url) and _url.group(1) == "/?openChat=true")

# La route du front exige le code : une adresse sans code ne mene nulle part.
# C'est la raison pour laquelle il n'y a pas de demi-mesure possible ici.
APP = io.open(os.path.join(RACINE, "frontend", "src", "App.js"), encoding="utf-8").read()
v("la route de l'espace exige le code (pas de `/espace` nu)",
  r"/^\/espace\/([^/]+)\/?$/" in APP)

# LE TROU DE FOND, NOMME ET SURVEILLE : tant que cette route est ouverte, aucun
# secret ne doit voyager par push. Si elle est fermee un jour, ce controle le
# dira — et le lien pourra revenir.
_sub = re.search(r'@api_router\.post\("/push/subscribe"\)(.{0,4000})', SRC, re.S)
v("/push/subscribe lit toujours l'e-mail dans le corps (trou connu, non corrige ici)",
  bool(_sub) and 'body.get("email")' in _sub.group(1))

print()
print("== V661 — le Service Worker suit bien cette url ==")
v("il lit `data.url`", "event.notification.data.url" in SW)
v("et garde son repli quand il n'y en a pas", "'/?openChat=true'" in SW)
v("il gere l'arrivee d'un push", "addEventListener('push'" in SW)
v("et le clic sur la notification", "addEventListener('notificationclick'" in SW)
# Un abonnement revoque se recree tout seul : sans cela, le telephone devient
# injoignable en silence.
v("il gere le renouvellement d'abonnement", "addEventListener('pushsubscriptionchange'" in SW)

print()
print("== V661 — ce qui ne doit PAS avoir bouge ==")
v("l'anti-doublon par canal est toujours la", "rv2_reserver_canal" in SRC)
v("le respect des refus est toujours la", "rv2_canal_autorise" in SRC)
v("le tag par cours evite l'empilement", "push_ui_tag_cours" in SRC)

print()
print("  %d/%d" % (_ok, _ok + _ko))
sys.exit(0 if _ko == 0 else 1)
