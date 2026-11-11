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

v("elle porte desormais une url", '"url"' in _b, _b[:120])
v("et cette url est l'espace DEJA valide pour l'e-mail (`_e2_espace`)",
  '_e2_espace' in _b)
# ON NE FABRIQUE PAS DE DESTINATION. Code douteux -> `rv2_lien_espace` rend une
# chaine vide -> aucune `url` posee -> le repli d'origine s'applique.
v("une adresse vide n'est PAS posee (pas de destination inventee)",
  'if _e2_espace else {}' in _b)

_url = re.search(r'_push_url = \(data or \{\}\)\.get\("url"\) or "([^"]+)"', SRC)
v("le repli du serveur est inchange", bool(_url) and _url.group(1) == "/?openChat=true")

v("`_e2_espace` est calcule AVANT l'envoi du push",
  SRC.index("_e2_espace = (rv2_lien_espace") < SRC.index('{"type": "course_reminder"'))

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
