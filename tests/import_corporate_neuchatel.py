#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V657 — import HORS LIGNE des prospects « AFROBOOST CORPORATE — NEUCHÂTEL » (fichier Excel).

    python3 tests/import_corporate_neuchatel.py [chemin.xlsx]              # DRY-RUN (défaut) : n'écrit RIEN
    MONGO_URL=... DB_NAME=... python3 tests/import_corporate_neuchatel.py --appliquer

- Lecture : feuilles « Prospects », « Dossiers », « Messages » (stdlib zipfile + xml, sans openpyxl).
- Correspondance : ville Neuchâtel (adresse précise conservée), catégorie `entreprise`, niche
  « Entreprises » (id lu en base), vague `CORP-NE`, `j0_message` = « Premier message (BROUILLON) »,
  `notes` = le dossier. Statut `a_contacter`. Aucun message n'est envoyé, aucune campagne créée.
- Anti-doublon (règle Prospection) : nom+ville, e-mail, téléphone, domaine enregistrable du site.
  Un doublon est SIGNALÉ et IGNORÉ, jamais fusionné. `ref` = CORP-NE-NN (ré-import idempotent).
- Écrit UNIQUEMENT avec `--appliquer`, et exige MONGO_URL + DB_NAME dans l'environnement.
"""
import os
import re
import sys
import unicodedata
import uuid
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

FICHIER_DEFAUT = "/Users/afroboost/Desktop/AFROBOOST_CORPORATE_NEUCHATEL_PROSPECTION.xlsx"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
COACH = "contact.artboost@gmail.com"   # le super-admin unique, propriétaire de la prospection
VAGUE = "CORP-NE"
VILLE = "Neuchâtel"


# ── Lecture du classeur (stdlib) ───────────────────────────────────────────────
def lire_classeur(chemin) -> dict:
    """{nom_feuille: [ {entête: valeur}, ... ]} — la 1re ligne de chaque feuille fait les entêtes."""
    z = zipfile.ZipFile(chemin)
    partages = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            partages.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    sortie = {}
    for sh in wb.find("m:sheets", NS):
        cible = rels[sh.get("{%s}id" % NS["r"])].lstrip("/")
        cible = cible if cible.startswith("xl/") else "xl/" + cible
        lignes = []
        for row in ET.fromstring(z.read(cible)).iter("{%s}row" % NS["m"]):
            d = {}
            for c in row.findall("m:c", NS):
                col = re.match(r"[A-Z]+", c.get("r")).group(0)
                v, t = c.find("m:v", NS), c.get("t")
                if t == "s" and v is not None:
                    val = partages[int(v.text)]
                elif t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter("{%s}t" % NS["m"]))
                else:
                    val = v.text if v is not None else ""
                d[col] = (val or "").strip()
            lignes.append(d)
        if not lignes:
            sortie[sh.get("name")] = []
            continue
        entetes = lignes[0]
        sortie[sh.get("name")] = [{entetes.get(k, k): v for k, v in l.items()} for l in lignes[1:] if any(l.values())]
    return sortie


# ── Normalisations (identiques à server.py : p3s1_normaliser / p3s1_domaine / V657) ──
def normaliser(v) -> str:
    if not v:
        return ""
    t = "".join(c for c in unicodedata.normalize("NFD", str(v).strip().lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def domaine(url) -> str:
    t = re.sub(r"^[a-z]+://", "", str(url or "").strip().lower()).split("/")[0].split("?")[0].split("#")[0]
    t = re.sub(r"^www\.", "", t)
    return t if "." in t else ""


SUFFIXES_2 = {"co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "co.jp", "com.br", "co.za", "com.fr", "co.nz"}
PARTAGES = {"facebook.com", "instagram.com", "linkedin.com", "tiktok.com", "youtube.com", "google.com", "linktr.ee",
            "wixsite.com", "wix.com", "business.site", "jimdo.com", "jimdofree.com", "wordpress.com", "blogspot.com",
            "squarespace.com", "webnode.ch", "webnode.com", "x.com", "twitter.com", "local.ch", "search.ch", "github.io"}


def enregistrable(d) -> str:
    d = str(d or "").strip().lower().rstrip(".")
    if "." not in d:
        return ""
    p = d.split(".")
    n = 3 if ".".join(p[-2:]) in SUFFIXES_2 and len(p) >= 3 else 2
    r = ".".join(p[-n:])
    return "" if r in PARTAGES else r


def texte(v, plafond):
    v = str(v or "").strip()
    return v[:plafond] if v else None


# ── V658 : messages alignés sur l'offre par abonnement (le classeur n'est jamais modifié) ──
OFFRE = ("Le format : un abonnement d’entreprise avec un événement par mois, pour 5, 10 ou 20 collaborateurs, "
         "sur 3, 6 ou 12 mois. Vous recevez un lien et un QR code personnalisés : vos collaborateurs s’inscrivent "
         "eux-mêmes, sans payer les places couvertes par l’abonnement.")
OFFRE_RESUME = ("En résumé : une séance mensuelle de cardio-danse afrobeat accessible aux débutants, avec ou sans casques "
                "audio. Afroboost Corporate fonctionne par abonnement : un événement par mois, pour 5, 10 ou 20 "
                "collaborateurs, avec un engagement de 3, 6 ou 12 mois (à partir de 300 CHF par mois). Vous recevez un "
                "lien d’invitation personnalisé et un QR code : vos collaborateurs s’inscrivent eux-mêmes, sans payer les "
                "places comprises dans votre abonnement. Musiciens live et Silent Live Fusion sur devis.")
LIENS_A_VALIDER = "[À COMPLÉTER AVANT ENVOI : lien de la présentation PDF et lien de la vidéo, une fois validés]"


def _apres_paragraphe(t, motif, ajout):
    """Insère `ajout` après le premier paragraphe qui contient `motif`. Rend (texte, inséré ?)."""
    if not t or OFFRE[:30] in t:
        return t, bool(t and OFFRE[:30] in t)
    blocs = t.split("\n\n")
    for i, b in enumerate(blocs):
        if motif in b:
            # Si le paragraphe suivant détaille déjà le principe, l'offre vient après lui.
            j = i + 1 if i + 1 < len(blocs) and blocs[i + 1].startswith("Le principe est simple") else i
            return "\n\n".join(blocs[:j + 1] + [ajout] + blocs[j + 1:]), True
    return t, False


def adapter_premier(t):
    t = (t or "").replace("autour d’une séance de cardio-danse", "autour de séances mensuelles de cardio-danse") \
                 .replace("une séance de cardio-danse", "des séances mensuelles de cardio-danse") \
                 .replace("afrobeat, accessible aux débutants", "afrobeat, accessibles aux débutants") \
                 .replace("débutants, qui réunit", "débutants, qui réunissent") \
                 .replace("pour une prochaine sortie d’équipe", "pour vos équipes")
    return _apres_paragraphe(t, "Afroboost Corporate Experience", OFFRE)


def adapter_documentation(t):
    t = re.sub(r"Comme convenu, vous trouverez ci-joint notre présentation Afroboost Corporate Experience \(PDF, 6 pages\) "
               r"et le lien vers notre vidéo de présentation\.",
               "Comme convenu, voici notre présentation Afroboost Corporate Experience et notre vidéo :\n" + LIENS_A_VALIDER, t or "")
    t, n = re.subn(r"En résumé :.*?sur devis\.", OFFRE_RESUME, t, flags=re.S)
    t = re.sub(r"\n*Pièce jointe :[^\n]*", "", t)
    t = re.sub(r"\n*Vidéo : \[LIEN À CRÉER[^\n]*", "", t)
    return t.strip(), bool(n) and "ci-joint" not in t and "LIEN À CRÉER" not in t


def adapter_relance1(t):
    return _apres_paragraphe(t, "événements interentreprises", OFFRE.replace("Le format :", "Le format est simple :"))


# ── Correspondance ─────────────────────────────────────────────────────────────
def construire(classeur, niche_id) -> list:
    dossiers = {normaliser(d.get("Entreprise")): d for d in classeur.get("Dossiers", [])}
    messages = {normaliser(m.get("Entreprise")): m for m in classeur.get("Messages", [])}
    fiches = []
    for p in classeur.get("Prospects", []):
        nom = texte(p.get("Entreprise"), 160)
        if not nom:
            continue
        cle = normaliser(nom)
        dos, msg = dossiers.get(cle, {}), messages.get(cle, {})
        lieu = p.get("Ville") or ""
        adresse = re.search(r"\(([^)]+)\)", lieu)
        prio = (p.get("Priorité") or "").strip().upper()[:1]
        notes = "\n".join("%s : %s" % (k, dos[k]) for k in (
            "Pourquoi cette cible", "Format Afroboost adapté", "Besoins à vérifier en rendez-vous",
            "Qui pourrait décider", "Argument principal", "Offre suggérée (hypothèse)", "Documents à associer",
            "Historique réel") if dos.get(k))
        # V658 : messages alignés sur l'abonnement ; la documentation (envoyée seulement après accord) va dans les notes.
        j0, ok_j0 = adapter_premier(msg.get("Premier message (BROUILLON)"))
        doc_msg, ok_doc = adapter_documentation(msg.get("Message avec documentation (si accord)"))
        j3, ok_j3 = adapter_relance1(msg.get("Relance 1 (5 à 7 jours ouvrables)"))
        if doc_msg:
            notes = (notes + "\n\n" if notes else "") + "MESSAGE AVEC DOCUMENTATION (après accord, liens à compléter) :\n" + doc_msg
        try:
            num = int(float(p.get("N°") or 0))
        except ValueError:
            num = 0
        site = texte(p.get("Site officiel"), 300)
        fiches.append({
            "ref": "CORP-NE-%02d" % num if num else None,
            "organisation_name": nom, "city": VILLE,
            "address": texte(adresse.group(1) if adresse else None, 200),
            "category": "entreprise", "subcategory": texte(p.get("Secteur"), 160),
            "niche_id": niche_id, "wave": VAGUE, "status": "a_contacter",
            "priority": prio if prio in ("A", "B", "C") else None,
            "website": site, "public_email": (texte(p.get("E-mail public"), 160) or "").lower() or None,
            "public_phone": texte(p.get("Téléphone public"), 40),
            "contact_role": texte(p.get("Interlocuteur / service"), 120),
            "preferred_channel": texte(p.get("Canal recommandé"), 60),
            "source_url": texte(p.get("Source"), 500),
            "j0_message": texte(j0, 4000),
            "j3_message": texte(j3, 4000),                                              # V658 : relance 1
            "j7_message": texte(msg.get("Relance 2 (7 à 10 jours après relance 1)"), 4000),  # V658 : relance 2
            "notes": texte(notes, 4000),
            "deja_dans_la_base_selon_fichier": (p.get("Déjà dans la base ?") or "").strip(),
            "_controle": {"j0": ok_j0, "doc": ok_doc, "j3": ok_j3, "notes_tronquees": len(notes) > 4000},
        })
    return fiches


def motifs_doublon(f, existants) -> list:
    sortie = []
    cle = normaliser(f["organisation_name"]) + "|" + normaliser(f["city"])
    dom = enregistrable(domaine(f.get("website")))
    for e in existants:
        m = []
        if e.get("dedupe_key") == cle:
            m.append("nom_et_ville")
        if f.get("public_email") and e.get("public_email") == f["public_email"]:
            m.append("email")
        if f.get("public_phone") and e.get("public_phone") == f["public_phone"]:
            m.append("telephone")
        if dom and (e.get("website_registrable") == dom or enregistrable(e.get("website_domain")) == dom):
            m.append("domaine")
        if f.get("ref") and e.get("ref") == f["ref"]:
            m.append("ref")
        if m:
            sortie.append("%s (%s)" % (e.get("organisation_name"), ", ".join(m)))
    return sortie


def principal(argv):
    appliquer = "--appliquer" in argv
    chemins = [a for a in argv[1:] if not a.startswith("--")]
    chemin = chemins[0] if chemins else FICHIER_DEFAUT
    url, base = os.environ.get("MONGO_URL"), os.environ.get("DB_NAME")
    if not url or not base:
        print("REFUS : MONGO_URL et DB_NAME doivent être définis (aucune valeur par défaut).")
        return 2
    from pymongo import MongoClient
    db = MongoClient(url, serverSelectionTimeoutMS=5000)[base]
    print("Cible : base « %s » sur %s — mode %s" % (base, re.sub(r"//[^@]*@", "//***@", url).split("?")[0],
                                                     "ÉCRITURE" if appliquer else "DRY-RUN (rien n'est écrit)"))
    niche = db.prospection_niches.find_one({"coach_id": COACH, "nom": "Entreprises", "supprimee": {"$ne": True}}, {"id": 1})
    if not niche:
        print("REFUS : niche « Entreprises » introuvable pour %s." % COACH)
        return 3
    fiches = construire(lire_classeur(chemin), niche["id"])
    existants = list(db.partner_prospects.find({"coach_id": COACH}, {"_id": 0, "organisation_name": 1, "dedupe_key": 1,
                                                                    "public_email": 1, "public_phone": 1, "website_domain": 1,
                                                                    "website_registrable": 1, "ref": 1}))
    # V658 : `--inclure=REF` crée une fiche signalée UNIQUEMENT par un domaine partagé (jamais si nom, e-mail ou téléphone coïncident).
    inclure = {a.split("=", 1)[1].strip().upper() for a in argv if a.startswith("--inclure=")}
    a_creer, ignores = [], []
    for f in fiches:
        m = motifs_doublon(f, existants)
        if m and (f.get("ref") or "").upper() in inclure and all(x.endswith("(domaine)") for x in m):
            print("  ~ %s créée malgré le domaine partagé (%s)" % (f["ref"], "; ".join(m)[:120]))
            m = []
        (ignores if m else a_creer).append((f, m))
        if not m:   # un doublon INTERNE au fichier est aussi détecté
            existants.append(dict(f, dedupe_key=normaliser(f["organisation_name"]) + "|" + normaliser(f["city"]),
                                  website_registrable=enregistrable(domaine(f.get("website")))))
    print("\n%d fiche(s) lue(s) : %d à créer, %d ignorée(s) (doublons signalés, jamais fusionnés)\n" % (len(fiches), len(a_creer), len(ignores)))
    for f, _ in a_creer:
        print("  + %-12s %s  [%s] %s" % (f.get("ref") or "-", f["organisation_name"], f.get("priority") or "-", f.get("public_email") or ""))
    for f, m in ignores:
        print("  = %-12s %s  -> déjà présent : %s" % (f.get("ref") or "-", f["organisation_name"], "; ".join(m)))
    _c = [f["_controle"] for f, _ in a_creer]
    print("\nMessages adaptés (fiches à créer) : premiers %d/%d, documentation %d/%d, relance 1 %d/%d, relance 2 présentes %d/%d, notes tronquées %d"
          % (sum(x["j0"] for x in _c), len(_c), sum(x["doc"] for x in _c), len(_c), sum(x["j3"] for x in _c), len(_c),
             sum(1 for f, _ in a_creer if f.get("j7_message")), len(_c), sum(x["notes_tronquees"] for x in _c)))
    if not all(x["j0"] and x["doc"] and x["j3"] and not x["notes_tronquees"] for x in _c):
        print("ARRÊT : un message n'a pas pu être adapté ; rien ne sera écrit.")
        return 4
    if not appliquer:
        print("\nDRY-RUN : aucune écriture. Relancer avec --appliquer pour créer les fiches.")
        return 0
    maintenant = datetime.now(timezone.utc).isoformat()
    n = 0
    for f, _ in a_creer:
        doc = {k: v for k, v in f.items() if k not in ("deja_dans_la_base_selon_fichier", "_controle")}
        dom = domaine(f.get("website"))
        doc.update({"id": str(uuid.uuid4()), "coach_id": COACH, "created_by": COACH,
                    "dedupe_key": normaliser(f["organisation_name"]) + "|" + normaliser(f["city"]),
                    "city_key": normaliser(f["city"]), "website_domain": dom,
                    "website_registrable": enregistrable(dom) or None,
                    "collaboration_type": None, "score": None, "partner_application_id": None, "partner_id": None,
                    "created_at": maintenant, "updated_at": maintenant, "source_import": "V657-CORP-NE"})
        try:
            db.partner_prospects.insert_one(doc)
            n += 1
        except Exception as e:  # noqa: BLE001 — ref déjà prise : ré-import idempotent
            print("  ! %s non créé (%s)" % (f["organisation_name"], type(e).__name__))
    print("\n%d fiche(s) créée(s). Aucun message envoyé, aucune campagne créée." % n)
    return 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv))
