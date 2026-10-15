#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V620 — UN MEDIA (VIDEO OU IMAGE) JOINT A UNE REPONSE PARTENAIRE. ZERO E-MAIL.

CE QUE CE FICHIER PROUVE (aucune base reelle, aucun reseau, transport factice)
==============================================================================
  A. le media se choisit dans la bibliotheque EXISTANTE (`prospection_medias`)
     ou depuis un fichier DEJA envoye (`/api/files`) — du coach appelant seul ;
  B. la miniature vient de la bibliotheque (meme original), jamais inventee ;
  C. retirer le media ne touche pas au texte ; omettre `media` ne change rien ;
  D. l'empreinte couvre le media : changer de media apres l'apercu -> 409 ;
  E. sans media : empreinte, texte et HTML STRICTEMENT identiques a avant V620 ;
  F. l'e-mail : carte miniature + « ▶ Voir la vidéo Afroboost », lien absolu,
     aucune balise video / autoplay, aucune adresse technique en texte visible ;
  G. la trace d'envoi garde l'INSTANTANE du media, meme si la bibliotheque change ;
  H. le fil V619 montre le media avec la reponse envoyee ;
  I. aucune sortie reseau, aucun e-mail reel.
"""
try:   # V608 : le point d'envoi Resend unique
    import builtins as _b608, os as _o608, sys as _s608
    _s608.path.insert(0, _o608.path.dirname(_o608.path.dirname(_o608.path.abspath(__file__))))
    import api.resend_central as _rc608
    _b608._rc = _rc608
except Exception:  # noqa: BLE001
    pass
import asyncio
import io
import json
import os
import re
import socket
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
RESULTATS = []


def verifier(intitule, condition, detail=""):
    RESULTATS.append((intitule, bool(condition), detail))
    print("  %-6s %s" % ("OK  " if condition else "ECHEC", intitule))
    if detail and not condition:
        print("           -> %s" % detail)
    return bool(condition)


_TENTATIVES = []
_GETADDR = socket.getaddrinfo


def _dns(hote, port, *a, **k):
    if str(hote) in ("localhost", "127.0.0.1", "::1", None):
        return _GETADDR(hote, port, *a, **k)
    _TENTATIVES.append(("dns", hote))
    raise OSError("sortie reseau interdite dans ce banc : %s" % hote)


def _conn(self, adresse, *a, **k):
    _TENTATIVES.append(("connect", adresse))
    raise OSError("sortie reseau interdite dans ce banc")


socket.getaddrinfo = _dns
socket.socket.connect = _conn

SECRET = "secret-de-test-v620-sans-aucun-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v620-inexistant:27017")

import jwt as _jwt          # noqa: E402
import api.server as S      # noqa: E402
from fastapi import HTTPException  # noqa: E402

COACH_A = "coach.a.fictif@exemple.test"
COACH_B = "coach.b.fictif@exemple.test"

_BANC = os.path.join(RACINE, "tests", "test_p3s3b_preparation_campagne.py")
_source = io.open(_BANC, encoding="utf-8").read()
_debut = _source.index("def lancer(coroutine):")
_fin = _source.index('# ============================================================================\nprint("\\n1.')
_espace = {"S": S, "asyncio": asyncio, "COACH_A": COACH_A, "COACH_B": COACH_B,
           "INSTANT": "2026-10-15T07:00:00+00:00", "json": json, "os": os, "sys": sys,
           "_jwt": _jwt, "SECRET": SECRET, "HTTPException": HTTPException}
exec(compile(_source[_debut:_fin], _BANC, "exec"), _espace)   # noqa: S102
CollectionBouchon = _espace["CollectionBouchon"]
BaseBouchon = _espace["BaseBouchon"]
RequeteFictive = _espace["RequeteFictive"]
lancer = _espace["lancer"]
JA, JB = _espace["jeton"](COACH_A), _espace["jeton"](COACH_B)


class CollectionUpsert(CollectionBouchon):
    """`update_one(..., upsert=True)` comme Mongo (meme complement qu'AI-P4)."""

    async def update_one(self, filtre, maj, upsert=False, *a, **k):
        for d in self.documents:
            if self._ok(d, filtre):
                d.update(maj.get("$set") or {})
                self.ecritures += 1
                return type("R", (), {"matched_count": 1, "modified_count": 1, "upserted_id": None})()
        if not upsert:
            return type("R", (), {"matched_count": 0, "modified_count": 0, "upserted_id": None})()
        c = dict(filtre)
        c.update(maj.get("$setOnInsert") or {})
        c.update(maj.get("$set") or {})
        self.documents.append(c)
        return type("R", (), {"matched_count": 0, "modified_count": 0, "upserted_id": True})()


class CurseurIterable:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, *a, **k):
        return self

    def skip(self, n):
        return self

    def limit(self, n):
        return self

    async def to_list(self, n=None):
        return [dict(d) for d in self._docs]

    def __aiter__(self):
        self._i = iter(list(self._docs))
        return self

    async def __anext__(self):
        try:
            return dict(next(self._i))
        except StopIteration:
            raise StopAsyncIteration


class CollectionIterable(CollectionBouchon):
    def find(self, filtre=None, projection=None, *a, **k):
        return CurseurIterable([dict(d) for d in self.documents if self._ok(d, filtre)])


APPELS = []


async def faux_transport(params, options):
    APPELS.append({"params": dict(params), "options": dict(options)})
    return {"id": "resend-v620-" + str(len(APPELS))}


_VRAI = S.P3AI4FournisseurReponse


class FournisseurTrace(_VRAI):
    def __init__(self, envoi_autorise=False, transport=None, expediteur=None):
        super().__init__(envoi_autorise=envoi_autorise, transport=faux_transport, expediteur=expediteur)


S.P3AI4FournisseurReponse = FournisseurTrace

# ============================================================================
# FIXTURES — fictives, calquees sur la forme REELLE (prod du 15/10).
# ============================================================================
VIDEO = "/api/files/c39d44275d0049bb/video_c39d44275d0049bb"
MINI = "/api/files/7f0d8e0842244e56/image_7f0d8e0842244e56"
VIDEO2 = "/api/files/aaaa1111bbbb2222/video_aaaa1111bbbb2222"
IMPORT_V = "/api/files/ccccdddd00001111/video_ccccdddd00001111"
IMPORT_M = "/api/files/eeeeffff00002222/image_eeeeffff00002222"
AUTRE = "/api/files/9999888877776666/video_9999888877776666"

MEDIAS = [
    {"id": "orig-1", "coach_id": COACH_A, "niche": "B", "format": "original", "statut": "en_cours",
     "url": "/api/files/fc9beadc662e480d/video_fc9beadc662e480d", "source_id": None,
     "fichier": {"nom": "AFROBOOST_9_ETUDIANTS.mp4", "duree": 51.77}},
    {"id": "exp-1", "coach_id": COACH_A, "niche": "B", "format": "16_9", "statut": "a_verifier",
     "url": VIDEO, "source_id": "orig-1", "origine": "export", "cible": {"nom": "Associations"},
     "fichier": {"nom": "AFROBOOST_9_ETUDIANTS_16x9.mp4", "duree": 51.82}},
    {"id": "mini-1", "coach_id": COACH_A, "niche": "B", "format": "miniature", "statut": "en_cours",
     "url": MINI, "source_id": "orig-1", "fichier": {"nom": "AFROBOOST_9_ETUDIANTS_miniature.jpg"}},
    {"id": "mini-old", "coach_id": COACH_A, "niche": "B", "format": "miniature", "statut": "archivee",
     "url": "/api/files/0000000000000000/image_0000000000000000", "source_id": "orig-1"},
    {"id": "exp-2", "coach_id": COACH_A, "niche": "C", "format": "16_9", "statut": "a_verifier",
     "url": VIDEO2, "source_id": "orig-2", "fichier": {"nom": "AFROBOOST_6_FESTIVAL_16x9.mp4", "duree": 49.1}},
    {"id": "arch-1", "coach_id": COACH_A, "niche": "C", "format": "16_9", "statut": "archivee",
     "url": "/api/files/1234123412341234/video_1234123412341234", "source_id": "orig-2"},
    {"id": "b-1", "coach_id": COACH_B, "niche": "A", "format": "16_9", "statut": "en_cours",
     "url": AUTRE, "source_id": None},
]
NICHES = [{"id": "n-b", "coach_id": COACH_A, "cle": "B", "nom": "Étudiants / associations"},
          {"id": "n-c", "coach_id": COACH_A, "cle": "C", "nom": "Festivals"}]
FICHIERS = [
    {"file_id": "ccccdddd00001111", "filename": "video_ccccdddd00001111", "coach_email": COACH_A,
     "content_type": "video/mp4", "original_name": "Demo_Afroboost.mp4"},
    {"file_id": "eeeeffff00002222", "filename": "image_eeeeffff00002222", "coach_email": COACH_A,
     "content_type": "image/jpeg", "original_name": "demo.jpg"},
    {"file_id": "9999888877776666", "filename": "video_9999888877776666", "coach_email": COACH_B,
     "content_type": "video/mp4", "original_name": "autre.mp4"},
    {"file_id": "5555444433332222", "filename": "doc_5555444433332222", "coach_email": COACH_A,
     "content_type": "application/pdf", "original_name": "x.pdf"},
]
ACTION = {"id": "act-v620", "campaign_id": "camp-v620", "coach_id": COACH_A, "channel": "email",
          "target": "info@partenaire.exemple.test", "recipient_key": "TEST-620",
          "organisations": ["Partenaire Test"], "prospect_uuids": ["p-620"], "language": "FR",
          "statut": "envoye", "sent_at": "2026-10-11T08:00:00+00:00",
          S.P3R1_CHAMP_TOKEN: "3d861143c6def8776acb318c233f9357"}
MESSAGE = {"id": "inb-620", "coach_id": COACH_A, "action_id": "act-v620", "recipient_key": "TEST-620",
           "from_email": "madame@partenaire.exemple.test",
           "subject": "Re: Afroboost", "body_text": "Pouvez-vous m'envoyer une vidéo ?",
           "message_id": "<abc@partenaire.exemple.test>", "received_at": "2026-10-14T10:00:00+00:00",
           "statut": "rattache", "read_at": None, "traite_at": None}
TEXTE = "Bonjour Madame,\nVoici notre courte vidéo de démonstration.\nBassi"
BROUILLON = {"id": "b-620", "inbound_id": "inb-620", "action_id": "act-v620", "coach_id": COACH_A,
             "organisation": "Partenaire Test", "to_email": "madame@partenaire.exemple.test",
             "intention": "question", "langue": "fr", "version": 1, "reponse_proposee": TEXTE,
             "validation_requise": False, "motifs_validation": [],
             "genere_le": "2026-10-14T12:00:00+00:00"}
OUVERT = {"P3_REPONSE_ACTIF": True, "P3_REPONSE_ENVOI_REEL": True}


def base(flags=OUVERT, brouillon=BROUILLON):
    b = BaseBouchon([])
    b[S.P3S3_ACTIONS] = CollectionBouchon(S.P3S3_ACTIONS, [dict(ACTION)])
    b[S.P3U2_COLLECTION] = CollectionBouchon(S.P3U2_COLLECTION, [dict(MESSAGE)])
    b[S.P3AI_BROUILLONS] = CollectionUpsert(S.P3AI_BROUILLONS, [dict(brouillon)] if brouillon else [])
    b[S.P3N_COLLECTION] = CollectionBouchon(S.P3N_COLLECTION, [])
    b[S.P3AI4_COLLECTION] = CollectionBouchon(S.P3AI4_COLLECTION, [], uniques=[(("id",), None)])
    b[S.V595_MEDIAS] = CollectionBouchon(S.V595_MEDIAS, MEDIAS)
    b[S.V598_NICHES] = CollectionBouchon(S.V598_NICHES, NICHES)
    b["uploaded_files"] = CollectionBouchon("uploaded_files", FICHIERS)
    b["feature_flags"] = CollectionBouchon("feature_flags", [{"id": "feature_flags", **(flags or {})}])
    b["subscribers"] = CollectionIterable("subscribers", [])
    b["coaches"] = CollectionBouchon("coaches", [{"email": COACH_A}, {"email": COACH_B}])
    b["coach_auth"] = CollectionBouchon("coach_auth", [])
    S.db = b
    APPELS.clear()
    return b


def patch(corps, jeton_=JA):
    return lancer(S.p3ai_modifier_brouillon("inb-620", RequeteFictive(jeton_=jeton_, corps=corps)))


def apercu():
    return lancer(S.p3ai4_apercu("inb-620", RequeteFictive(jeton_=JA)))


def envoyer(empreinte):
    return lancer(S.p3ai4_envoyer_reponse(
        "inb-620", RequeteFictive(jeton_=JA, corps={"confirme": True, "draft_hash": empreinte})))


def statut_erreur(fn):
    try:
        fn()
    except HTTPException as e:
        return e.status_code
    return None


def texte_visible(html):
    """Le texte LISIBLE d'un HTML (sans balises ni attributs)."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


# ============================================================================
print("\nA. LE MEDIA VIENT DE LA BIBLIOTHEQUE EXISTANTE (ou d'un fichier deja envoye)")
_b = base()
_r = patch({"reponse_proposee": TEXTE, "media": {"media_id": "exp-1"}})
_m = _r["brouillon"].get("media") or {}
verifier("A1. un media de la bibliotheque se joint par son id", _m.get("media_id") == "exp-1")
verifier("A2. l'adresse est RESOLUE en base (pas fournie par le navigateur)", _m.get("url") == VIDEO)
verifier("A3. type video, origine bibliotheque, duree et niche reprises",
         _m.get("type") == "video" and _m.get("origine") == "bibliotheque"
         and _m.get("duree") == 51.82 and _m.get("niche_nom") == "Étudiants / associations"
         and _m.get("public") == "Associations", json.dumps(_m, ensure_ascii=False))
verifier("A4. un titre lisible (pas le nom technique du fichier)",
         _m.get("titre") == "AFROBOOST 9 ETUDIANTS 16x9", _m.get("titre"))
verifier("A5. le media d'un AUTRE coach est refuse (400, pas d'oracle)",
         statut_erreur(lambda: patch({"reponse_proposee": TEXTE, "media": {"media_id": "b-1"}})) == 400)
verifier("A6. un media archive n'est pas proposable",
         statut_erreur(lambda: patch({"reponse_proposee": TEXTE, "media": {"media_id": "arch-1"}})) == 400)
_r = patch({"reponse_proposee": TEXTE, "media": {"fichier_url": IMPORT_V, "miniature_url": IMPORT_M,
                                                  "duree": 12.5, "nom": "Demo_Afroboost.mp4"}})
_m = _r["brouillon"]["media"]
verifier("A7. un fichier importe par l'envoi existant se joint (video + miniature)",
         _m["origine"] == "import" and _m["type"] == "video" and _m["url"] == IMPORT_V
         and _m["miniature_url"] == IMPORT_M and _m["duree"] == 12.5, json.dumps(_m))
verifier("A8. le fichier d'un AUTRE coach est refuse (403)",
         statut_erreur(lambda: patch({"reponse_proposee": TEXTE, "media": {"fichier_url": AUTRE}})) == 403)
verifier("A9. un type non pris en charge (PDF) est refuse (400)",
         statut_erreur(lambda: patch({"reponse_proposee": TEXTE, "media": {
             "fichier_url": "/api/files/5555444433332222/doc_5555444433332222"}})) == 400)
verifier("A10. une adresse arbitraire est refusee (400)",
         statut_erreur(lambda: patch({"reponse_proposee": TEXTE, "media": {
             "fichier_url": "https://evil.exemple.test/x.mp4"}})) == 400)
_r = patch({"reponse_proposee": TEXTE, "media": {"fichier_url": IMPORT_M}})
verifier("A11. une IMAGE importee est acceptee (type image, miniature = elle-meme)",
         _r["brouillon"]["media"]["type"] == "image"
         and _r["brouillon"]["media"]["miniature_url"] == IMPORT_M)

# ============================================================================
print("\nB. LA MINIATURE EST CELLE DE LA BIBLIOTHEQUE, JAMAIS INVENTEE")
_b = base()
_m = patch({"reponse_proposee": TEXTE, "media": {"media_id": "exp-1"}})["brouillon"]["media"]
verifier("B1. export 16:9 -> la miniature active du meme original", _m["miniature_url"] == MINI, _m["miniature_url"])
_m = patch({"reponse_proposee": TEXTE, "media": {"media_id": "orig-1"}})["brouillon"]["media"]
verifier("B2. original -> la meme miniature", _m["miniature_url"] == MINI)
_m = patch({"reponse_proposee": TEXTE, "media": {"media_id": "exp-2"}})["brouillon"]["media"]
verifier("B3. sans miniature en bibliotheque -> aucune (None), rien d'invente", _m["miniature_url"] is None)
_m = patch({"reponse_proposee": TEXTE, "media": {"media_id": "mini-1"}})["brouillon"]["media"]
verifier("B4. une image de la bibliotheque (format miniature) se joint comme IMAGE",
         _m["type"] == "image" and _m["url"] == MINI)

# ============================================================================
print("\nC. RETIRER / OMETTRE")
_b = base()
patch({"reponse_proposee": TEXTE, "media": {"media_id": "exp-1"}})
_r = patch({"reponse_proposee": TEXTE + " (corrige)"})
verifier("C1. sans cle `media`, le media joint est CONSERVE", (_r["brouillon"].get("media") or {}).get("media_id") == "exp-1")
_r = patch({"reponse_proposee": TEXTE + " (corrige)", "media": None})
verifier("C2. media = null -> retire", _r["brouillon"].get("media") is None)
verifier("C3. et le texte n'est pas touche", _r["brouillon"]["reponse_proposee"] == TEXTE + " (corrige)")
verifier("C4. un brouillon vide reste refuse meme avec un media",
         statut_erreur(lambda: patch({"reponse_proposee": "  ", "media": {"media_id": "exp-1"}})) == 400)

# ============================================================================
print("\nD/E. L'EMPREINTE COUVRE LE MEDIA ; SANS MEDIA, RIEN NE CHANGE")
verifier("E1. sans media : empreinte IDENTIQUE a AI-P4",
         S.v620_empreinte(TEXTE, None) == S.p3ai4_empreinte(TEXTE))
verifier("E2. sans media : HTML IDENTIQUE a avant V620",
         S.v620_corps_html(TEXTE, None) == S.p3s3d2_corps_html(TEXTE))
verifier("E3. sans media : texte IDENTIQUE", S.v620_texte(TEXTE, None) == TEXTE)
_ch = S.P3AI4FournisseurReponse(envoi_autorise=False).charge_utile(
    {"destinataire": "x@exemple.test", "objet": "Re: x", "texte": TEXTE, "cle": "k"})
verifier("E4. charge utile sans media : text/html inchanges",
         _ch["params"]["text"] == TEXTE and _ch["params"]["html"] == S.p3s3d2_corps_html(TEXTE))
_b = base()
_a0 = apercu()
verifier("E5. apercu sans media : media None, draft_hash = empreinte AI-P4",
         _a0["media"] is None and _a0["draft_hash"] == S.p3ai4_empreinte(TEXTE))
patch({"reponse_proposee": TEXTE, "media": {"media_id": "exp-1"}})
_a1 = apercu()
verifier("D1. apercu avec media : la carte ET l'empreinte changent",
         _a1["media"]["url"] == VIDEO and _a1["draft_hash"] != _a0["draft_hash"])
verifier("D2. l'ancienne empreinte (sans media) est refusee : 409",
         statut_erreur(lambda: envoyer(_a0["draft_hash"])) == 409 and not APPELS)
patch({"reponse_proposee": TEXTE, "media": {"media_id": "exp-2"}})
verifier("D3. changer de media APRES l'apercu -> 409, aucun envoi",
         statut_erreur(lambda: envoyer(_a1["draft_hash"])) == 409 and not APPELS)

# ============================================================================
print("\nF. L'E-MAIL : UNE CARTE PROPRE, JAMAIS D'AUTOPLAY, JAMAIS D'URL EN CLAIR")
patch({"reponse_proposee": TEXTE, "media": {"media_id": "exp-1"}})
_a = apercu()
_h = _a["html_email"]
verifier("F1. l'apercu rend l'HTML EXACT de l'envoi (meme fonction)",
         _h == S.v620_corps_html(TEXTE, _a["media"]))
verifier("F2. le texte de la reponse est AU-DESSUS de la carte",
         _h.index("Voici notre courte") < _h.index("<table"))
verifier("F3. miniature absolue dans <img>", ('src="%s%s"' % (S.V604_SITE, MINI)) in _h)
verifier("F4. lien absolu vers la video", ('href="%s%s"' % (S.V604_SITE, VIDEO)) in _h)
verifier("F5. bouton « ▶ Voir la vidéo Afroboost » + legende",
         "&#9654;" in _h and "Voir la vidéo Afroboost" in _h and "Découvrir Afroboost en vidéo" in _h)
verifier("F6. AUCUNE balise video / autoplay / script", not re.search(r"(?i)<video|autoplay|<script", _h))
verifier("F7. aucune adresse technique dans le texte VISIBLE",
         "/api/files" not in texte_visible(_h) and "http" not in texte_visible(_h), texte_visible(_h)[-200:])
verifier("F8. le nom technique du fichier n'apparait pas dans l'e-mail", "AFROBOOST_9" not in _h)
_imgh = S.v620_corps_html(TEXTE, S.v620_instantane_envoi(
    {"type": "image", "url": MINI, "miniature_url": MINI, "titre": "x"}, ""))
verifier("F9. une IMAGE : l'image cliquable, sans bouton video",
         ('src="%s%s"' % (S.V604_SITE, MINI)) in _imgh and "Voir la vidéo" not in _imgh)
_sans_mini = S.v620_corps_html(TEXTE, S.v620_instantane_envoi(
    {"type": "video", "url": VIDEO2, "miniature_url": None, "titre": "x"}, ""))
verifier("F10. video sans miniature : bouton ▶ seul, aucune image cassee",
         "<img" not in _sans_mini and "Voir la vidéo Afroboost" in _sans_mini)
verifier("F11. une adresse piegee ne passe jamais dans l'HTML",
         S.v620_carte_html({"type": "video", "url": 'javascript:alert(1)'}) == ""
         and S.v620_carte_html({"type": "video", "url": 'https://x.test/a"onmouseover=1'}) == "")

# ============================================================================
print("\nG. L'ENVOI FIGE LE MEDIA EXACT")
_r = envoyer(_a["draft_hash"])
verifier("G1. UN appel au (faux) fournisseur", len(APPELS) == 1, str(len(APPELS)))
_p = APPELS[0]["params"]
verifier("G2. l'HTML transmis = l'HTML de l'apercu", _p["html"] == _h)
verifier("G3. la version texte porte le lien (secours), apres le message",
         _p["text"].startswith(TEXTE) and _p["text"].endswith(S.V604_SITE + VIDEO))
_t = _r["envoi"]
_tm = _t.get("media") or {}
verifier("G4. la trace garde l'instantane : id, url, titre, miniature, type, date",
         _tm.get("media_id") == "exp-1" and _tm.get("url") == VIDEO and _tm.get("titre")
         and _tm.get("miniature_url") == MINI and _tm.get("type") == "video" and _tm.get("date"),
         json.dumps(_tm))
verifier("G5. et l'adresse ABSOLUE reellement utilisee", _tm.get("url_absolue") == S.V604_SITE + VIDEO)
verifier("G6. approved_text reste le TEXTE seul (V619 inchange)", _t["approved_text"] == TEXTE)
# La bibliotheque change APRES l'envoi : la trace ne bouge pas.
for d in _b[S.V595_MEDIAS].documents:
    if d["id"] == "exp-1":
        d["url"] = "/api/files/ffff000011112222/video_ffff000011112222"
_trace = _b[S.P3AI4_COLLECTION].documents[0]
verifier("G7. la bibliotheque change ensuite : la trace garde l'ancien media",
         _trace["media"]["url"] == VIDEO)
patch({"reponse_proposee": TEXTE, "media": None})
verifier("G8. retirer le media du brouillon ensuite : la trace le garde", _trace["media"]["url"] == VIDEO)

# ============================================================================
print("\nH. LE FIL V619 MONTRE LE MEDIA ENVOYE")
_fil = S.v619_fil([dict(MESSAGE)], dict(ACTION), {}, {}, [dict(_trace)])
_rep = [e for e in _fil if e.get("type") == "manual_reply"]
verifier("H1. la reponse envoyee est dans le fil, avec son texte", _rep and _rep[0]["text"] == TEXTE)
_fm = (_rep[0] if _rep else {}).get("media") or {}
verifier("H2. et avec SON media (titre, miniature, url)",
         _fm.get("url") == VIDEO and _fm.get("miniature_url") == MINI and _fm.get("titre"), json.dumps(_fm))
_sans = S.v619_fil([], dict(ACTION), {}, {}, [dict(_trace, media=None)])
verifier("H3. une reponse sans media : `media` vaut None (rien d'autre ne change)",
         [e for e in _sans if e["type"] == "manual_reply"][0]["media"] is None)
verifier("H4. une adresse piegee en base n'atteint pas l'ecran",
         S.v620_media_du_fil({"type": "video", "url": "javascript:alert(1)"}) is None)

# ============================================================================
print("\nI. AUCUN E-MAIL REEL, AUCUNE SORTIE RESEAU")
verifier("I1. aucune sortie reseau tentee", not _TENTATIVES, str(_TENTATIVES))
verifier("I2. tous les appels sont passes par le faux transport", all(a["params"] for a in APPELS))

print("\n" + "=" * 78)
_echecs = [r for r in RESULTATS if not r[1]]
print("V620 MEDIA DANS LES REPONSES — %d verifications, %d echec(s)" % (len(RESULTATS), len(_echecs)))
print("=" * 78)
sys.exit(1 if _echecs else 0)
