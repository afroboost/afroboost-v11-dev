# -*- coding: utf-8 -*-
# V610p : LIEN D'ACCÈS À L'ESPACE (e-mail « Accède à ton espace Afroboost »).
"""V610p — Le lien de l'e-mail d'accès ouvre l'ESPACE ABONNÉ (jamais le ChatWidget).

Avant : `https://afroboost.com/?qr=<CODE>` — App.js mémorisait le code et le ChatWidget
s'ouvrait en plein écran (connexion « chat »), le contexte de l'événement était perdu.

Maintenant : `<front>/espace/<CODE>?acces=<jeton>[&evt=<offre>&inv=<jeton d'invitation>]`.
  - `acces` : jeton ALÉATOIRE (256 bits), stocké HACHÉ (jamais en clair), lié au code ET à
    l'adresse à laquelle l'e-mail est parti. Il vaut la même preuve que le code à 6 chiffres
    (posséder la boîte) : il ouvre la MÊME session d'espace (jeton B3-S1 révocable).
    24 h, 5 ouvertures au plus (bouton + QR sur un 2e appareil), puis l'écran OTP habituel.
  - `evt` / `inv` : l'événement d'où vient la demande, VÉRIFIÉ ici (invitation active qui porte
    bien cette offre). Pas une adresse de redirection : un identifiant d'offre et un jeton
    d'invitation publics, que l'espace utilise pour ouvrir CETTE carte. Rien d'autre.
"""
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

COLL = "espace_liens_acces"
DUREE_H = 24
MAX_OUVERTURES = 5
RE_CODE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,40}$")
RE_JETON_ACCES = re.compile(r"^[A-Za-z0-9_-]{30,80}$")
RE_OFFRE = re.compile(r"^[A-Za-z0-9_-]{4,80}$")
RE_JETON_INV = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def _maintenant():
    return datetime.now(timezone.utc)


def empreinte(jeton) -> str:
    return hashlib.sha256(("acces|" + str(jeton or "")).encode("utf-8")).hexdigest()


async def creer_lien(db, *, code, email, coach_id, slug="", maintenant=None) -> str:
    """Un jeton d'accès neuf (rendu UNE fois, pour l'e-mail) ; seule son empreinte est gardée."""
    _jeton = secrets.token_urlsafe(32)
    _t = maintenant or _maintenant()
    await db[COLL].insert_one({
        "_id": empreinte(_jeton), "code": str(code or "").strip().upper(), "email": str(email or "").strip().lower(),
        "coach_id": coach_id or "", "slug": slug or "", "created_at": _t.isoformat(),
        "expires_at": (_t + timedelta(hours=DUREE_H)).isoformat(), "ouvertures": 0,
    })
    return _jeton


async def contexte_evenement(db, offre, jeton):
    """(offre, jeton) seulement si l'invitation (coach ou lien personnel) est ACTIVE, de type
    événement, et porte BIEN cette offre ; sinon ("", "")."""
    _o, _j = str(offre or "").strip(), str(jeton or "").strip()
    if not RE_OFFRE.match(_o) or not RE_JETON_INV.match(_j):
        return "", ""
    try:
        _camp = await db["referral_campaigns"].find_one({"share_token": _j}, {"_id": 0, "status": 1, "type": 1, "offer_id": 1})
        if not _camp:
            _rel = await db["invitation_relais"].find_one({"jeton": _j}, {"_id": 0, "campagne_id": 1})
            if _rel:
                _camp = await db["referral_campaigns"].find_one({"id": _rel.get("campagne_id")},
                                                                {"_id": 0, "status": 1, "type": 1, "offer_id": 1})
    except Exception:  # noqa: BLE001
        return "", ""
    if not _camp or _camp.get("status") != "active" or _camp.get("type") not in ("event_paid", "event_free") \
            or str(_camp.get("offer_id") or "") != _o:
        return "", ""
    return _o, _j


def url_acces(front, code, jeton, offre="", jeton_inv="") -> str:
    _b = str(front or "https://afroboost.com").rstrip("/")
    _u = "%s/espace/%s?acces=%s" % (_b, quote(str(code or ""), safe=""), quote(str(jeton or ""), safe=""))
    if offre and jeton_inv:
        _u += "&evt=%s&inv=%s" % (quote(offre, safe=""), quote(jeton_inv, safe=""))
    return _u


def url_espace(front, code, offre="", jeton_inv="") -> str:
    """L'espace (et l'événement) SANS jeton d'accès — pour le QR, fabriqué par un service externe."""
    _b = str(front or "https://afroboost.com").rstrip("/")
    _u = "%s/espace/%s" % (_b, quote(str(code or ""), safe=""))
    if offre and jeton_inv:
        _u += "?evt=%s&inv=%s" % (quote(offre, safe=""), quote(jeton_inv, safe=""))
    return _u


async def consommer(db, code, jeton, maintenant=None):
    """Le lien (doc) s'il ouvre CE code : connu, non expiré, ouvertures restantes. L'ouverture
    est comptée de façon atomique (deux clics simultanés ne dépassent pas la borne)."""
    _c = str(code or "").strip().upper()
    _j = str(jeton or "").strip()
    if not RE_CODE.match(_c) or not RE_JETON_ACCES.match(_j):
        return None
    _id = empreinte(_j)
    _doc = await db[COLL].find_one({"_id": _id})
    if not _doc or _doc.get("code") != _c:
        return None
    _t = (maintenant or _maintenant()).isoformat()
    if str(_doc.get("expires_at") or "") <= _t or int(_doc.get("ouvertures") or 0) >= MAX_OUVERTURES:
        return None
    _r = await db[COLL].update_one({"_id": _id, "ouvertures": int(_doc.get("ouvertures") or 0)},
                                   {"$inc": {"ouvertures": 1}, "$set": {"derniere_ouverture": _t}})
    if not getattr(_r, "modified_count", 0):
        return None
    return _doc


def html_email(*, nom, code, restantes, total, url, qr_url) -> str:
    """« Accède à ton espace Afroboost » — mobile d'abord : le GROS bouton, le code, puis le QR
    (secondaire : ordinateur -> téléphone). Couleurs en dur : un e-mail ne lit pas les variables CSS."""
    _rose = "#D91CD2"
    from html import escape as _esc
    nom, code = _esc(str(nom or "")), _esc(str(code or ""))
    url, qr_url = _esc(str(url or ""), quote=True), _esc(str(qr_url or ""), quote=True)
    restantes, total = _esc(str(restantes)), _esc(str(total))
    return f"""
<div style="max-width:560px;margin:0 auto;background:#0b0710;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#ffffff;border-radius:16px;overflow:hidden">
  <div style="padding:28px 20px 8px">
    <h1 style="margin:0 0 6px;font-size:24px;line-height:1.25">Accède à ton espace Afroboost</h1>
    <p style="margin:0;color:#d4d4d8;font-size:15px">Bonjour {nom},</p>
  </div>
  <div style="padding:16px 20px 8px;text-align:center">
    <a href="{url}" style="display:block;background:{_rose};color:#ffffff;text-decoration:none;font-weight:800;font-size:17px;padding:18px 16px;border-radius:14px">ACCÉDER À MON ESPACE AFROBOOST</a>
    <p style="margin:10px 0 0;color:#a1a1aa;font-size:12px">Lien personnel, valable 24 h. Ne le transfère pas.</p>
  </div>
  <div style="margin:16px 20px;padding:16px;border-radius:12px;background:#17111d;border-left:4px solid {_rose}">
    <p style="margin:0 0 6px;color:#a1a1aa;font-size:12px">Ton code</p>
    <p style="margin:0;font-size:26px;font-weight:800;font-family:'Courier New',monospace;letter-spacing:1px">{code}</p>
    <p style="margin:10px 0 0;color:#a1a1aa;font-size:13px">Séances restantes : <strong style="color:#ffffff">{restantes}/{total}</strong></p>
  </div>
  <div style="padding:8px 20px 24px;text-align:center">
    <p style="margin:0 0 10px;color:#a1a1aa;font-size:13px">Sur ordinateur ? Scanne ce QR code avec ton téléphone.</p>
    <img src="{qr_url}" alt="QR code d'accès" width="140" height="140" style="width:140px;height:140px;border-radius:8px;background:#ffffff;padding:6px">
  </div>
  <div style="padding:14px 20px;border-top:1px solid #27202e">
    <p style="margin:0;color:#71717a;font-size:11px">Tu n'as rien demandé ? Ignore simplement cet e-mail.</p>
  </div>
</div>
"""
