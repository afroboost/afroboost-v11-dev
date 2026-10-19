#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V625 — PROSPECTION : PDF + PLUSIEURS FICHIERS, ET CRÉATION D'UNE NOUVELLE CAMPAGNE. ZÉRO E-MAIL.

CE QUE CE FICHIER PROUVE (aucune base réelle, aucun réseau, transport factice)
==============================================================================
  P. le PDF entre par l'envoi EXISTANT (`upload-asset` / `upload-chunk`, asset
     `document`) : type exact, signature `%PDF-`, 20 Mo au plus, message clair ;
  Q. la bibliothèque Médias range un « Document PDF » sans rien archiver ;
  R. une réponse porte PLUSIEURS fichiers (1 PDF + 2 images) : brouillon, aperçu,
     e-mail (cartes + liens, aucune adresse technique visible), trace, fil V619 ;
  S. COMPATIBILITÉ V620 : 0 ou 1 média vidéo/image = empreinte, texte et HTML
     STRICTEMENT identiques ; un ancien brouillon / une ancienne trace (champ
     `media` seul) se lit toujours ;
  T. la préparation de campagne recopie J0, J+3, J+7 DE LA FICHE (rien d'inventé) ;
  U. « Préparer une autre campagne » + `allow_new` crée UNE nouvelle campagne
     `preparee` ; double clic (même clé) = une seule ; rien n'est approuvé ni envoyé.
"""
import io
import os
import re
import sys
import tempfile

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MEDIA = tempfile.mkdtemp(prefix="v625-media-")
os.environ["MEDIA_DIR"] = _MEDIA   # jamais /app/media : le banc écrit dans un dossier jetable

# LE BANC V620 EST RÉUTILISÉ TEL QUEL (bouchons, faux transport, fixtures) : deux
# bancs divergeraient, et le second finirait par mentir.
_V620 = os.path.join(RACINE, "tests", "test_v620_media_reponse.py")
_src = io.open(_V620, encoding="utf-8").read()
_fin = _src.index('# ============================================================================\nprint("\\nA.')
_g = {"__file__": _V620, "__name__": "banc_v620"}
exec(compile(_src[:_fin], _V620, "exec"), _g)   # noqa: S102
globals().update({k: v for k, v in _g.items() if not k.startswith("__")})
RESULTATS.clear()
APPELS.clear()

import shutil  # noqa: E402

PDF_ID = "abcdef0123456789"
PDF = "/api/files/%s/document_%s.pdf" % (PDF_ID, PDF_ID)
IMG2_ID = "1212121234343434"
IMG2 = "/api/files/%s/image_%s.jpg" % (IMG2_ID, IMG2_ID)
FICHIERS_V625 = FICHIERS + [
    {"file_id": PDF_ID, "filename": "document_%s.pdf" % PDF_ID, "coach_email": COACH_A,
     "content_type": "application/pdf", "asset_type": "document", "size": 1572864,
     "original_name": "Brochure_Afroboost.pdf"},
    {"file_id": IMG2_ID, "filename": "image_%s.jpg" % IMG2_ID, "coach_email": COACH_A,
     "content_type": "image/jpeg", "asset_type": "image", "original_name": "Photo_cours.jpg"},
]


def base624(**k):
    b = base(**k)
    b["uploaded_files"] = CollectionBouchon("uploaded_files", [dict(f) for f in FICHIERS_V625])
    return b


class FichierFictif:
    """Le strict nécessaire d'un `UploadFile` FastAPI."""

    def __init__(self, contenu, type_mime, nom):
        self._c, self.content_type, self.filename = contenu, type_mime, nom

    async def read(self):
        return self._c


def televerser(contenu, type_mime="application/pdf", nom="Brochure.pdf", asset_type="document"):
    return lancer(S.upload_coach_asset(RequeteFictive(jeton_=JA), FichierFictif(contenu, type_mime, nom), asset_type))


def morceau(contenu, upload_id, i, n, type_mime="application/pdf", asset_type="document"):
    return lancer(S.upload_chunk(RequeteFictive(jeton_=JA), FichierFictif(contenu, "application/octet-stream", "blob"),
                                 upload_id, i, n, "Brochure.pdf", type_mime, asset_type))


def detail_erreur(fn):
    try:
        fn()
    except HTTPException as e:
        return e.status_code, e.detail
    return None, None


# ============================================================================
print("\nP. LE PDF ENTRE PAR L'ENVOI EXISTANT, STRICTEMENT CONTRÔLÉ")
_b = base624()
verifier("P0. limite PDF = 20 Mo, message exact",
         S.V625_PDF_MAX == 20 * 1024 * 1024
         and S.V625_MSG_PDF_LOURD == "Ce PDF dépasse la taille maximale autorisée de 20 Mo.")
_r = televerser(b"%PDF-1.7\n" + b"x" * 2048)
verifier("P1. un vrai PDF est accepté (asset document, extension .pdf posée par le serveur)",
         _r["success"] and _r["asset_type"] == "document" and _r["url"].endswith(".pdf"), str(_r))
_fiche = [f for f in _b["uploaded_files"].documents if f.get("filename") == _r["filename"]]
verifier("P2. rangé dans `uploaded_files` (même stockage), type application/pdf",
         _fiche and _fiche[0]["content_type"] == "application/pdf" and _fiche[0]["asset_type"] == "document")
_st, _d = detail_erreur(lambda: televerser(b"%PDF-" + b"0" * (20 * 1024 * 1024)))
verifier("P3. TEST F — PDF trop lourd : 400 + message clair", _st == 400 and _d == S.V625_MSG_PDF_LOURD, str(_d))
_avant = len(_b["uploaded_files"].documents)
verifier("P4. ... et RIEN n'est stocké", len(_b["uploaded_files"].documents) == _avant)
_st, _d = detail_erreur(lambda: televerser(b"<html>pas un pdf</html>"))
verifier("P5. un faux PDF (signature absente) est refusé", _st == 400 and "PDF" in str(_d), str(_d))
_st, _ = detail_erreur(lambda: televerser(b"%PDF-1.4", asset_type="image"))
verifier("P6. un PDF déclaré « image » est refusé (type exact par catégorie)", _st == 400)
_st, _ = detail_erreur(lambda: televerser(b"\x89PNG....", type_mime="image/png", asset_type="document"))
verifier("P7. un PNG déclaré « document » est refusé", _st == 400)
# Envoi par morceaux : le type vient du client, il n'est cru qu'après la signature.
_st, _ = detail_erreur(lambda: morceau(b"%PDF-1.4", "up624a", 0, 1, type_mime="audio/mpeg"))
verifier("P8. morceaux : `document` avec un autre type -> 400", _st == 400)
_st, _ = detail_erreur(lambda: morceau(b"%PDF-1.4", "up624b", 0, 1, asset_type="audio"))
verifier("P9. morceaux : un PDF hors `document` -> 400", _st == 400)
_st, _d = detail_erreur(lambda: morceau(b"GIF89a....", "up624c", 0, 1))
verifier("P10. morceaux : signature absente -> 400, dossier provisoire nettoyé",
         _st == 400 and not os.path.exists(os.path.join(_MEDIA, ".uploads", "up624c")), str(_d))
morceau(b"%PDF-" + b"0" * (12 * 1024 * 1024), "up624d", 0, 2)
_st, _d = detail_erreur(lambda: morceau(b"0" * (9 * 1024 * 1024), "up624d", 1, 2))
verifier("P11. morceaux : total > 20 Mo -> 400 + message clair", _st == 400 and _d == S.V625_MSG_PDF_LOURD, str(_d))
morceau(b"%PDF-1.5\n" + b"y" * 4096, "up624e", 0, 2)
_r = morceau(b"z" * 100, "up624e", 1, 2)
verifier("P12. morceaux : un PDF valide est assemblé en .pdf", _r.get("status") == "complete" and _r["url"].endswith(".pdf"))

# ============================================================================
print("\nQ. LA BIBLIOTHÈQUE MÉDIAS RANGE UN « DOCUMENT PDF »")
_b = base624()


async def _niche_ok(niche, appelant):   # la validation de niche (V598) n'est pas l'objet de ce banc
    return None


S.v598_verifier_niche = _niche_ok


def ajouter_media(corps):
    return lancer(S.v595_ajouter_media(RequeteFictive(jeton_=JA, corps=corps)))


_q1 = ajouter_media({"niche": "B", "format": "document", "url": PDF, "fichier": {"nom": "Brochure_Afroboost.pdf"}})
_q2 = ajouter_media({"niche": "B", "format": "document", "url": PDF})
verifier("Q1. un PDF contrôlé s'enregistre au format « document » (nom + taille du serveur)",
         _q1["media"]["format"] == "document" and _q1["media"]["fichier"]["taille"] == 1572864
         and _q1["media"]["fichier"]["type"] == "application/pdf")
verifier("Q2. deux PDF coexistent : aucun archivage à l'ajout", _q2["archives"] == 0
         and all(m["statut"] != "archivee" for m in _b[S.V595_MEDIAS].documents if m.get("format") == "document"))
verifier("Q3. un PDF NON contrôlé (ancien fichier) est refusé",
         statut_erreur(lambda: ajouter_media({"niche": "B", "format": "document",
                                              "url": "/api/files/5555444433332222/doc_5555444433332222"})) == 400)
verifier("Q4. une vidéo ne peut pas être rangée comme document",
         statut_erreur(lambda: ajouter_media({"niche": "B", "format": "document", "url": IMPORT_V})) == 400)
verifier("Q5. un lien externe ne peut pas être un document",
         statut_erreur(lambda: ajouter_media({"niche": "B", "format": "document",
                                              "url": "https://exemple.test/brochure.pdf"})) == 400)
_choix = S.v601_choisir_media({"category": "association"}, "B", _b[S.V595_MEDIAS].documents)
verifier("Q6. le choix automatique de vidéo (V601) ignore les documents",
         (_choix.get("media") or {}).get("format") != "document")

# ============================================================================
print("\nR. PLUSIEURS FICHIERS DANS UNE RÉPONSE (TEST E : 1 PDF + 2 IMAGES)")
_b = base624()
_doc = ajouter_media({"niche": "B", "format": "document", "url": PDF,
                      "fichier": {"nom": "Brochure_Afroboost.pdf"}})["media"]
_r = patch({"reponse_proposee": TEXTE, "medias": [{"media_id": _doc["id"]}, {"fichier_url": IMPORT_M},
                                                  {"fichier_url": IMG2, "nom": "Photo_cours.jpg"}]})
_br = _r["brouillon"]
verifier("R1. le brouillon porte les 3 fichiers, dans l'ordre choisi",
         [m["type"] for m in _br["medias"]] == ["document", "image", "image"], str([m.get("type") for m in _br["medias"]]))
verifier("R2. le PDF est résolu en base : titre lisible + taille", _br["medias"][0]["titre"] == "Brochure Afroboost"
         and _br["medias"][0]["taille"] == 1572864, str(_br["medias"][0]))
verifier("R3. `media` (lecteurs V620) = le premier", (_br.get("media") or {}).get("url") == PDF)
_r = patch({"reponse_proposee": TEXTE, "medias": [{"fichier_url": IMPORT_M}, {"fichier_url": IMPORT_M}]})
verifier("R4. un même fichier choisi deux fois n'est joint qu'une fois", len(_r["brouillon"]["medias"]) == 1)
verifier("R5. 7 fichiers -> 400 (6 au plus)",
         statut_erreur(lambda: patch({"reponse_proposee": TEXTE, "medias": [{"fichier_url": IMPORT_M}] * 7})) == 400)
verifier("R6. un fichier d'un AUTRE coach dans la liste -> 403, rien n'est écrit",
         statut_erreur(lambda: patch({"reponse_proposee": TEXTE, "medias": [{"fichier_url": IMPORT_M},
                                                                            {"fichier_url": AUTRE}]})) == 403
         and len(_b[S.P3AI_BROUILLONS].documents[0]["medias"]) == 1)
_r = patch({"reponse_proposee": TEXTE, "medias": [{"media_id": _doc["id"]}, {"fichier_url": IMPORT_M},
                                                  {"fichier_url": IMG2, "nom": "Photo_cours.jpg"}]})
_a = apercu()
verifier("R7. l'aperçu montre les 3 fichiers avant « Confirmer l'envoi »", len(_a["medias"]) == 3)
_h = _a["html_email"]
_vis = texte_visible(_h)
verifier("R8. e-mail : le texte d'abord, puis les cartes",
         _h.index("Voici notre courte") < _h.index(S.V625_LIBELLE_DOC))
verifier("R9. carte PDF : nom, taille, bouton « Voir / télécharger le document »",
         "Brochure Afroboost" in _vis and "1,5 Mo" in _vis and S.V625_LIBELLE_DOC in _vis, _vis[-400:])
verifier("R10. 2 images = 2 cartes « Voir l'image » (liens absolus vers /api/files)",
         _h.count('href="' + S.V604_SITE + IMPORT_M + '"') >= 1 and _h.count('href="' + S.V604_SITE + IMG2 + '"') >= 1)
verifier("R11. AUCUNE adresse technique dans le texte visible du HTML", "/api/files" not in _vis and "http" not in _vis)
verifier("R11-bis. chaque image a son bouton « Voir l'image » (plusieurs fichiers)",
         __import__("html").unescape(_vis).count(S.V620_LIBELLE_IMAGE) == 2, _vis[-300:])
verifier("R12. pas de pièce jointe Resend réelle", "attachments" not in S.P3AI4FournisseurReponse(False).charge_utile(
    {"texte": TEXTE, "medias": _a["medias"], "destinataire": "x@y.test"})["params"])
verifier("R13. l'empreinte couvre les 3 fichiers (et leur ordre)",
         _a["draft_hash"] == S.v625_empreinte(TEXTE, _b[S.P3AI_BROUILLONS].documents[0]["medias"])
         and _a["draft_hash"] != S.v625_empreinte(TEXTE, list(reversed(_b[S.P3AI_BROUILLONS].documents[0]["medias"]))))
# Retirer un fichier après l'aperçu : l'envoi sur l'ancienne empreinte est refusé.
_ancien = _a["draft_hash"]
patch({"reponse_proposee": TEXTE, "medias": [{"media_id": _doc["id"]}, {"fichier_url": IMPORT_M}]})
verifier("R14. retirer un fichier après l'aperçu -> l'ancienne empreinte est refusée (409)",
         statut_erreur(lambda: envoyer(_ancien)) == 409 and not APPELS)
patch({"reponse_proposee": TEXTE, "medias": [{"media_id": _doc["id"]}, {"fichier_url": IMPORT_M},
                                             {"fichier_url": IMG2, "nom": "Photo_cours.jpg"}]})
_a = apercu()
_r = envoyer(_a["draft_hash"])
verifier("R15. UN appel au FAUX transport, HTML transmis = HTML de l'aperçu",
         len(APPELS) == 1 and APPELS[0]["params"]["html"] == _a["html_email"])
_txt = APPELS[0]["params"]["text"]
verifier("R16. version texte : le message puis une ligne par fichier",
         _txt.startswith(TEXTE) and _txt.count(S.V604_SITE + "/api/files/") == 3, _txt)
_t = _b[S.P3AI4_COLLECTION].documents[0]
verifier("R17. la trace fige les 3 fichiers (instantanés datés)",
         [m["type"] for m in _t["medias"]] == ["document", "image", "image"] and all(m.get("date") for m in _t["medias"])
         and _t["medias"][0]["taille"] == 1572864)
verifier("R18. double clic sur « Confirmer » : aucun second envoi",
         (envoyer(_a["draft_hash"]) or {}).get("deja_envoye") is True and len(APPELS) == 1)
_APPELS_ENVOI = list(APPELS)   # le seul envoi du banc (les bases suivantes remettent APPELS à zéro)

print("\nG. HISTORIQUE V619 : LES FICHIERS RÉELLEMENT ENVOYÉS")
for d in _b[S.V595_MEDIAS].documents:
    if d.get("id") == _doc["id"]:
        d["fichier"]["nom"] = "AUTRE_NOM.pdf"
        d["url"] = "/api/files/ffffeeeeddddcccc/document_ffffeeeeddddcccc.pdf"
patch({"reponse_proposee": TEXTE, "medias": []})
_fil = S.v619_fil([dict(MESSAGE)], dict(ACTION), {}, {}, [dict(_t)])
_rep = [e for e in _fil if e.get("type") == "manual_reply"][0]
verifier("G1. le fil montre les 3 fichiers envoyés, même après changement de bibliothèque et de brouillon",
         [m["titre"] for m in _rep["medias"]] == ["Brochure Afroboost", "demo", "Photo cours"]
         and _rep["medias"][0]["url"] == PDF and _rep["medias"][0]["taille"] == 1572864,
         str([m.get("titre") for m in _rep.get("medias") or []]))
verifier("G2. `media` (ancien écran) = le premier fichier", _rep["media"]["url"] == PDF)
_fd = S.v621_fil_depuis(_fil, dict(MESSAGE), dict(ACTION))
_nos = [x for x in _fd if x.get("de") == "afroboost"]
verifier("G3. le générateur IA (V621) voit aussi les 3 fichiers", _nos and len(_nos[-1]["medias"]) == 3)

# ============================================================================
print("\nS. TEST H — COMPATIBILITÉ V620 (0 OU 1 MÉDIA, ANCIENNES DONNÉES)")
_v = {"type": "video", "url": VIDEO, "miniature_url": MINI, "titre": "Démo"}
verifier("S1. 0 média : empreinte = AI-P4, HTML = AI-P4, texte = message",
         S.v625_empreinte(TEXTE, []) == S.p3ai4_empreinte(TEXTE)
         and S.v625_corps_html(TEXTE, []) == S.p3s3d2_corps_html(TEXTE) and S.v625_texte(TEXTE, []) == TEXTE)
verifier("S2. 1 vidéo : empreinte IDENTIQUE à V620 (anciennes clés d'idempotence valables)",
         S.v625_empreinte(TEXTE, [_v]) == S.v620_empreinte(TEXTE, _v))
verifier("S3. 1 vidéo : HTML et texte IDENTIQUES à V620",
         S.v625_corps_html(TEXTE, [_v]) == S.v620_corps_html(TEXTE, _v)
         and S.v625_texte(TEXTE, [_v]) == S.v620_texte(TEXTE, _v))
_ancien_brouillon = dict(BROUILLON, media=dict(_v, media_id="exp-1"))   # champ `media` SEUL, sans `medias`
verifier("S4. ancien brouillon (champ `media` seul) : lu comme 1 média", S.v625_medias(_ancien_brouillon) == [_ancien_brouillon["media"]])
_b = base624(brouillon=_ancien_brouillon)
_a = apercu()
verifier("S5. son aperçu = celui de V620 (HTML + empreinte)",
         _a["html_email"] == S.v620_corps_html(TEXTE, S.v620_instantane_envoi(_ancien_brouillon["media"], ""))
         and _a["draft_hash"] == S.v620_empreinte(TEXTE, _ancien_brouillon["media"]))
_ancienne_trace = {"send_status": S.P3AI4_ENVOYE, "approved_text": TEXTE, "sent_at": "2026-10-15T11:00:00+00:00",
                   "media": S.v620_instantane_envoi(_v, "2026-10-15T11:00:00+00:00")}
_rep = [e for e in S.v619_fil([], dict(ACTION), {}, {}, [_ancienne_trace]) if e["type"] == "manual_reply"][0]
verifier("S6. ancienne trace V620 (1 vidéo) : toujours visible, `media` et `medias` cohérents",
         _rep["media"]["url"] == VIDEO and len(_rep["medias"]) == 1 and _rep["medias"][0]["url"] == VIDEO)
verifier("S7. PATCH ancien format (`media`) : toujours accepté, `medias` tenu à jour",
         (lambda br: br["media"]["media_id"] == "exp-1" and len(br["medias"]) == 1)(
             patch({"reponse_proposee": TEXTE, "media": {"media_id": "exp-1"}})["brouillon"]))
_br = patch({"reponse_proposee": TEXTE, "media": {"media_id": "exp-1"}})["brouillon"]
verifier("S8. un seul média par l'ancien format : empreinte de l'aperçu = V620",
         apercu()["draft_hash"] == S.v620_empreinte(TEXTE, _br["media"]))

# ============================================================================
print("\nT. LA PRÉPARATION RECOPIE J0 / J+3 / J+7 DE LA FICHE, RIEN D'AUTRE")
_f = {"id": "p-x", "organisation_name": "Asso X", "public_email": "info@asso-x.test", "preferred_channel": None,
      "j0_message": "Objet : A\n\nBonjour", "j3_message": "Objet : Re: A\n\nRelance 1", "j7_message": "Objet : Re: A\n\nRelance 2"}
_act = S.p3s3_action_preparee("camp-x", COACH_A, [_f], "2026-10-19T12:00:00+00:00")
verifier("T1. J0, J+3, J+7 copiés depuis la fiche (origine « fiche »)",
         _act["message_j0"] == _f["j0_message"] and _act["message_j3"] == _f["j3_message"]
         and _act["message_j7"] == _f["j7_message"] and _act["message_j3_origine"] == "fiche"
         and _act["message_j7_origine"] == "fiche")
_act2 = S.p3s3_action_preparee("camp-x", COACH_A, [dict(_f, j3_message=None, j7_message="  ")], "2026-10-19T12:00:00+00:00")
verifier("T2. relance absente sur la fiche = aucune clé (rien d'inventé, ancien comportement)",
         "message_j3" not in _act2 and "message_j7" not in _act2)
verifier("T3. aucune relance n'est armée par la préparation (ni échéance, ni envoi, ni verrou)",
         not any(k in _act for k in ("j3_due_at", "j7_due_at", "sent_at", "verrou_actif", "relances_validees")))

# ============================================================================
print("\nU. TEST I — « PRÉPARER UNE AUTRE CAMPAGNE » : UNE NOUVELLE, UNE SEULE")
fiche_ = _g["_espace"]["fiche"] if "_espace" in _g else None
_fiches = [fiche_("TST-1", "Prospect TEST 1", "Neuchatel", public_email="test1@exemple.test",
                  preferred_channel="E-mail", j0_message="Bonjour 1", j3_message="Relance 1"),
           fiche_("TST-2", "Prospect TEST 2", "Neuchatel", public_email="test2@exemple.test",
                  preferred_channel="E-mail", j0_message="Bonjour 2")]
_bc = BaseBouchon([dict(x) for x in _fiches])
S.db = _bc


def preparer(**corps):
    return lancer(S.p3s3_preparer_campagne(RequeteFictive(jeton_=JA, corps=corps)))


_anc = preparer(dry_run=False, prospect_ids=["TST-1"], idempotency_key="ancienne")["campaign"]
_apercu = preparer(dry_run=True, prospect_ids=["TST-1", "TST-2"])
verifier("U1. l'aperçu signale la campagne déjà ouverte (l'écran sait qu'on en demande une autre)",
         (_apercu.get("campagne_ouverte") or {}).get("id") == _anc["id"])
_sans = preparer(dry_run=False, prospect_ids=["TST-1", "TST-2"], idempotency_key=_apercu["campaign"]["id"])
verifier("U2. CAUSE DU BUG : sans `allow_new`, l'ancienne campagne est rendue (rien de créé)",
         _sans.get("reouverte") is True and _sans["campaign"]["id"] == _anc["id"]
         and len(_bc["prospect_campaigns"].documents) == 1)
_cle = _apercu["campaign"]["id"] + "-b"
_n1 = preparer(dry_run=False, prospect_ids=["TST-1", "TST-2"], idempotency_key=_cle, allow_new=True)
_n2 = preparer(dry_run=False, prospect_ids=["TST-1", "TST-2"], idempotency_key=_cle, allow_new=True)
verifier("U3. CORRIGÉ : avec `allow_new`, UNE nouvelle campagne `preparee` est créée",
         _n1["rejeu"] is False and _n1["campaign"]["etat"] == "preparee" and _n1["campaign"]["id"] != _anc["id"])
verifier("U4. double clic (même clé) : la même campagne est rendue, aucune jumelle",
         _n2["rejeu"] is True and _n2["campaign"]["id"] == _n1["campaign"]["id"]
         and len(_bc["prospect_campaigns"].documents) == 2)
_acts = [a for a in _bc["prospect_campaign_actions"].documents if a["campaign_id"] == _n1["campaign"]["id"]]
verifier("U5. 2 destinataires, J0 de la fiche ; J+3 seulement là où la fiche en a un",
         len(_acts) == 2 and sorted(a["message_j0"] for a in _acts) == ["Bonjour 1", "Bonjour 2"]
         and sorted(bool(a.get("message_j3")) for a in _acts) == [False, True])
_c = _bc["prospect_campaigns"].documents[1]
verifier("U6. ni approuvée, ni démarrée, ni scellée, ni relances validées",
         _c["approved_at"] is None and _c["started_at"] is None and not _c.get("snapshot_hash")
         and not _c.get("relances_validees"))
verifier("U7. aucune action réservée ni envoyée", all(not a.get("verrou_actif") and not a.get("sent_at")
                                                       and a["statut"] in ("pret", "bloque") for a in _acts))
verifier("U8. l'ancienne campagne est intacte", _bc["prospect_campaigns"].documents[0]["id"] == _anc["id"]
         and _bc["prospect_campaigns"].documents[0]["etat"] == "preparee")

# ============================================================================
print("\nI. AUCUN E-MAIL RÉEL, AUCUNE SORTIE RÉSEAU")
verifier("I1. aucune sortie réseau tentée", not _TENTATIVES, str(_TENTATIVES))
verifier("I2. un seul appel de tout le banc, au FAUX transport, vers l'adresse fictive",
         len(_APPELS_ENVOI) == 1 and not APPELS
         and _APPELS_ENVOI[0]["params"]["to"] == ["madame@partenaire.exemple.test"])
shutil.rmtree(_MEDIA, ignore_errors=True)

print("\n" + "=" * 78)
_echecs = [r for r in RESULTATS if not r[1]]
print("V625 PROSPECTION 4 CORRECTIONS — %d vérifications, %d échec(s)" % (len(RESULTATS), len(_echecs)))
print("=" * 78)
sys.exit(1 if _echecs else 0)
