# -*- coding: utf-8 -*-
"""V673 — LE MESSAGE EXCEPTIONNEL DU COACH, JOINT AUX RAPPELS AVANT COURS.

Exemple metier : « Coach Bassi est absent ce mercredi 25 novembre, Marie
assure le cours. » Le coach l'ecrit une fois, sur le ou les cours concernes,
pour une PERIODE de seances (du ... au ...). Le rappel habituel part a son heure
habituelle, et porte en plus ce message.

CE QUE CE MODULE GARANTIT — et c'est tout ce qu'il fait :

1. LE MESSAGE EST ATTACHE A DES SEANCES, PAS AU COURS POUR TOUJOURS.
   Il ne s'applique qu'aux occurrences dont la date LOCALE (Europe/Zurich) tombe
   dans [du, au]. La seance suivante, hors periode, repart avec le rappel
   habituel : aucune reutilisation automatique. La periode est bornee
   (MAX_JOURS) pour qu'un message ne puisse pas devenir permanent par erreur.

2. AUCUN EFFET SUR LE CALENDRIER NI SUR L'ANTI-DOUBLON.
   Le message n'entre dans aucune cle d'envoi. Un rappel deja parti n'est donc
   jamais renvoye parce que le message a change ; un rappel pas encore parti lit
   le message tel qu'il est au moment de partir (le moteur relit le cours a
   chaque passage).

3. FONCTIONS PURES. Aucune base, aucun reseau : le moteur et la route les
   appellent, les bancs les testent directement.
"""
from datetime import date, datetime, timezone

CHAMP = "message_exceptionnel"
MAX_CARACTERES = 600
MAX_JOURS = 31            # une periode d'au plus un mois
PUSH_MAX = 140            # le Push n'en porte qu'un extrait


def _date_iso(valeur):
    """`date` depuis « AAAA-MM-JJ », ou None."""
    if not isinstance(valeur, str):
        return None
    try:
        return date.fromisoformat(valeur.strip()[:10])
    except ValueError:
        return None


def nettoyer_texte(brut):
    """Texte libre du coach : retours a la ligne gardes, controles retires.

    Trois retours a la ligne d'affilee au plus. Aucun HTML n'est interprete : le
    texte est ECHAPPE a la sortie (e-mail), jamais ici — on stocke ce que le
    coach a ecrit.
    """
    if not isinstance(brut, str):
        return ""
    _t = brut.replace("\r\n", "\n").replace("\r", "\n")
    _t = "".join(c for c in _t if c == "\n" or c == "\t" or ord(c) >= 32)
    _t = _t.replace("\t", " ")
    while "\n\n\n" in _t:
        _t = _t.replace("\n\n\n", "\n\n")
    _lignes = [l.rstrip() for l in _t.split("\n")]
    return "\n".join(_lignes).strip()


def valider(corps, aujourd_hui):
    """(message, None) si le corps est acceptable, sinon (None, motif lisible).

    `aujourd_hui` est la date LOCALE suisse du jour : une periode entierement
    passee n'a aucun sens — aucun rappel ne pourra plus la porter.
    """
    if not isinstance(corps, dict):
        return None, "Corps de requête illisible."
    _texte = nettoyer_texte(corps.get("texte"))
    if not _texte:
        return None, "Le message est vide."
    if len(_texte) > MAX_CARACTERES:
        return None, "Le message dépasse %d caractères." % MAX_CARACTERES
    _du = _date_iso(corps.get("du"))
    _au = _date_iso(corps.get("au")) if corps.get("au") else _du
    if not _du or not _au:
        return None, "Indique la date de la séance concernée."
    if _au < _du:
        return None, "La date de fin précède la date de début."
    if (_au - _du).days > MAX_JOURS:
        return None, "La période ne peut pas dépasser %d jours." % MAX_JOURS
    if _au < aujourd_hui:
        return None, "Cette période est déjà passée."
    return {"texte": _texte, "du": _du.isoformat(), "au": _au.isoformat()}, None


def message_pour_seance(cours, instant_utc, zurich):
    """Le texte a joindre au rappel de CETTE seance, ou "".

    Lecture defensive : un champ absent, abime ou hors periode donne "" — le
    rappel part alors exactement comme avant ce lot.
    """
    try:
        _m = (cours or {}).get(CHAMP)
        if not isinstance(_m, dict) or instant_utc is None:
            return ""
        _texte = nettoyer_texte(_m.get("texte"))
        _du = _date_iso(_m.get("du"))
        _au = _date_iso(_m.get("au")) or _du
        if not _texte or not _du or not _au:
            return ""
        if instant_utc.tzinfo is None:
            instant_utc = instant_utc.replace(tzinfo=timezone.utc)
        _jour = instant_utc.astimezone(zurich).date()
        if _du <= _jour <= _au:
            return _texte[:MAX_CARACTERES]
    except Exception:  # noqa: BLE001 — un message illisible ne bloque jamais un rappel
        return ""
    return ""


def extrait_push(texte):
    """Une ligne courte pour l'ecran verrouille."""
    _t = " ".join((texte or "").split())
    if len(_t) <= PUSH_MAX:
        return _t
    return _t[:PUSH_MAX - 1].rstrip() + "…"


def corps_push(corps_habituel, texte):
    """Corps du Push : l'habituel, puis le message. Inchange sans message."""
    if not texte:
        return corps_habituel
    return "%s\n%s" % (corps_habituel, extrait_push(texte))


def bloc_html(texte, accent):
    """Encadre HTML du message, ECHAPPE. "" sans message."""
    if not texte:
        return ""
    from html import escape as _h
    _corps = "<br>".join(_h(l) for l in texte.split("\n"))
    return (
        '<div style="margin:16px 0 8px;padding:14px 16px;border-radius:10px;'
        'background:rgba(255,255,255,0.06);border-left:3px solid %s;">'
        '<p style="margin:0 0 6px;font-size:12px;letter-spacing:.04em;'
        'text-transform:uppercase;color:%s;">Message de ton coach</p>'
        '<p style="margin:0;color:#fff;line-height:1.6;">%s</p></div>'
        % (_h(accent or "#D91CD2", quote=True), _h(accent or "#D91CD2", quote=True), _corps))


def lignes_texte(texte):
    """Version texte brut du meme message."""
    if not texte:
        return []
    return ["", "Message de ton coach :", texte]


def aujourd_hui_zurich(zurich, maintenant=None):
    return (maintenant or datetime.now(timezone.utc)).astimezone(zurich).date()


__all__ = ["CHAMP", "MAX_CARACTERES", "MAX_JOURS", "nettoyer_texte", "valider",
           "message_pour_seance", "extrait_push", "corps_push", "bloc_html",
           "lignes_texte", "aujourd_hui_zurich"]
