#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3-S2 — L'IMPORT DES PROSPECTS COWORK. ESSAI À BLANC PAR DÉFAUT.

    python3 tests/import_prospects_cowork.py                 # analyse, n'écrit RIEN
    python3 tests/import_prospects_cowork.py --appliquer     # écrit

CE QU'IL FAIT, ET RIEN D'AUTRE
==============================================================================
Il lit `Afroboost_P3_Pilotage_Prospection_READY.xlsx`, le traduit dans le modèle
`partner_prospects` de P3-S1, et compare à ce qui existe déjà. Aucun envoi,
aucune candidature, aucun partenaire, aucun contact client.

POURQUOI UN SCRIPT ET PAS UNE ROUTE D'UPLOAD
==============================================================================
Le besoin réel est d'importer UN fichier, puis de le réimporter enrichi. Une
route d'upload publique ajouterait une surface d'attaque (fichier arbitraire,
parsing, quotas) pour un geste que le propriétaire fera quelques fois par an.
Le script suit le précédent du dépôt : `tests/purge_conversations_test.py` et
`tests/bascule_*.py` sont déjà des outils d'administration rangés ici.

UNE SEULE SOURCE DE VÉRITÉ POUR LA VALIDATION
==============================================================================
Il n'a AUCUNE règle à lui : catégories, statuts, plafonds, clé de doublon,
normalisation viennent tous de `api/server.py` (`p3s1_*`). Réécrire ces règles
ici créerait un second endroit à maintenir, donc un second endroit qui finirait
par contredire le premier — et l'import passerait des documents que l'API
refuserait.

L'IDEMPOTENCE, ET CE QU'ELLE PROTÈGE
==============================================================================
La clé est `ref` (l'identifiant Cowork : FES-01, ECO-01...), portée par un index
UNIQUE PARTIEL `(coach_id, ref)` posé par P3-S1. Rejouer l'import ne crée donc
jamais un doublon, même si le fichier a été renommé ou réordonné.

Sur une ligne déjà connue, l'import MET À JOUR la qualification (score, contact,
sources, messages) et NE TOUCHE JAMAIS l'état vivant : `status`, `notes`,
`wave`, les huit dates commerciales, les deux pointeurs P2. Un enrichissement
livré par Cowork ne peut donc pas effacer une réponse reçue ni ramener à
« à contacter » un prospect déjà relancé. C'est la règle qui compte le jour où
le fichier reviendra avec 120 lignes.

CE QUI EST REFUSÉ PLUTÔT QUE DEVINÉ
==============================================================================
Une catégorie que le libellé et le préfixe d'identifiant ne confirment pas
ENSEMBLE est un CONFLIT, pas une valeur à choisir. Une organisation qui
ressemble à une autre sans porter la même `ref` est un CONFLIT. Rien n'est
fusionné automatiquement : le rapport dit quoi regarder, l'humain tranche.
"""
import argparse
import asyncio
import os
import re
import sys
import zipfile
from html import unescape

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

CHEMIN_DEFAUT = os.path.expanduser(
    "~/Downloads/Afroboost_P3_Pilotage_Prospection_READY.xlsx")

# ============================================================================
# 1. LECTEUR .XLSX — sans dépendance
# ============================================================================
# Ajouter `openpyxl` à `api/requirements.txt` l'embarquerait dans l'image de
# production, où il ne servirait jamais. Un .xlsx est un zip de XML.
#
# LE PIÈGE QU'IL ÉVITE : une cellule vide n'est PAS écrite dans le XML. Lire les
# `<c>` dans l'ordre décalerait donc toutes les colonnes suivantes dès le
# premier trou — et ce fichier en compte beaucoup. On lit l'attribut `r`
# (« C7 ») pour ranger chaque cellule à SA place.

_RE_LIGNE = re.compile(r"<row[^>]*>(.*?)</row>", re.S)
_RE_CELL = re.compile(r"<c\b([^>]*)>(.*?)</c>|<c\b([^>]*)/>", re.S)
_RE_REF = re.compile(r'\br="([A-Z]+)\d+"')
_RE_TYPE = re.compile(r'\bt="(\w+)"')
_RE_V = re.compile(r"<v>(.*?)</v>", re.S)
_RE_IS = re.compile(r"<is>(.*?)</is>", re.S)
_RE_BALISE = re.compile(r"<[^>]+>")


def _col(lettres):
    n = 0
    for c in lettres:
        n = n * 26 + (ord(c) - 64)
    return n - 1


def _txt(fragment):
    return unescape(_RE_BALISE.sub("", fragment or "")).strip()


def lire_classeur(chemin):
    """{nom_de_feuille: [[cellules...], ...]} — colonnes alignées."""
    z = zipfile.ZipFile(chemin)
    noms = z.namelist()
    partages = []
    if "xl/sharedStrings.xml" in noms:
        brut = z.read("xl/sharedStrings.xml").decode("utf-8")
        partages = [_txt(m) for m in re.findall(r"<si>(.*?)</si>", brut, re.S)]
    wb = z.read("xl/workbook.xml").decode("utf-8")
    declarees = re.findall(r'<sheet[^>]*name="([^"]*)"[^>]*r:id="([^"]*)"', wb)
    cibles = {}
    if "xl/_rels/workbook.xml.rels" in noms:
        rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        for rid, cible in re.findall(
                r'<Relationship[^>]*Id="([^"]*)"[^>]*Target="([^"]*)"', rels):
            cibles[rid] = cible.lstrip("/")
    fichiers = sorted(n for n in noms
                      if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
    feuilles = {}
    for i, (nom, rid) in enumerate(declarees):
        cible = cibles.get(rid, "")
        chemin_f = ("xl/" + cible) if cible and not cible.startswith("xl/") else cible
        if chemin_f not in noms:
            chemin_f = fichiers[i] if i < len(fichiers) else None
        if chemin_f:
            feuilles[unescape(nom)] = _lignes(z.read(chemin_f).decode("utf-8"), partages)
    z.close()
    return feuilles


def _lignes(xml, partages):
    sortie = []
    for brut in _RE_LIGNE.findall(xml):
        cellules = {}
        for a1, contenu, a2 in _RE_CELL.findall(brut):
            attrs = a1 or a2
            ref = _RE_REF.search(attrs)
            if not ref:
                continue
            typ = _RE_TYPE.search(attrs)
            typ = typ.group(1) if typ else None
            if typ == "inlineStr":
                m = _RE_IS.search(contenu or "")
                valeur = _txt(m.group(1)) if m else ""
            else:
                m = _RE_V.search(contenu or "")
                brute = _txt(m.group(1)) if m else ""
                valeur = (partages[int(brute)]
                          if typ == "s" and brute.isdigit() and int(brute) < len(partages)
                          else brute)
            cellules[_col(ref.group(1))] = valeur
        sortie.append([cellules.get(i, "") for i in range(max(cellules) + 1)]
                      if cellules else [])
    return sortie


# ============================================================================
# 2. LA TRADUCTION XLSX -> MODÈLE P3-S1
# ============================================================================

# Le libellé de la feuille ET le préfixe de l'identifiant. Les DEUX doivent
# désigner la même catégorie : c'est un contrôle croisé gratuit, et une
# divergence signale une ligne mal saisie plutôt qu'une catégorie à deviner.
CATEGORIE_PAR_LIBELLE = {
    "festival": "festival",
    "ecole de danse": "ecole_danse",
    "restaurant": "restaurant",
    "bar": "bar",
    "commerce": "commerce",
    "organisateur": "organisateur_evenement",
    "organisateur evenementiel": "organisateur_evenement",
    "communaute etudiante": "communaute_etudiante",
    "etudiant": "communaute_etudiante",
    "influenceur": "influenceur",
}
CATEGORIE_PAR_PREFIXE = {
    "FES": "festival", "ECO": "ecole_danse", "RES": "restaurant",
    "BAR": "bar", "COM": "commerce", "ORG": "organisateur_evenement",
    "ETU": "communaute_etudiante", "INF": "influenceur",
}
STATUT_PAR_LIBELLE = {"a contacter": "a_contacter"}

# « NON TROUVÉ », « — », « (masqué sur le site) » ne sont pas des coordonnées.
# Les stocker tels quels ferait croire, six mois plus tard, qu'on peut écrire à
# ce festival. Ils deviennent `null` — mais leur texte est CONSERVÉ en note,
# parce qu'il contient souvent l'indice qui manque (« NON TROUVÉ (formulaire) »).
_RE_ABSENT = re.compile(r"^(non trouv|—|-|n/?a|aucun|inconnu)", re.I)
_RE_MAIL = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")


def _presente(valeur):
    """La valeur si c'est une vraie donnée, sinon ''."""
    v = (valeur or "").strip()
    if not v or _RE_ABSENT.match(v):
        return ""
    return v


def _nombre(valeur):
    v = (valeur or "").strip().replace(",", ".")
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _reseaux(valeur):
    """Range « Autres réseaux » dans facebook / linkedin / tiktok, sans deviner."""
    v = _presente(valeur)
    trouves = {}
    if not v:
        return trouves, ""
    bas = v.lower()
    reste = []
    for champ, motifs in (("facebook", ("facebook", "fb ", "fb,", "fb :", "fb:")),
                          ("linkedin", ("linkedin",)),
                          ("tiktok", ("tiktok", "tik tok"))):
        if any(m in bas for m in motifs):
            trouves[champ] = v
    if not trouves:
        reste.append(v)
    return trouves, (reste[0] if reste else "")


def _contact(valeur):
    """« Resp. partenariats (via site) » -> (nom, rôle) quand c'est explicite."""
    v = _presente(valeur)
    if not v:
        return "", ""
    m = re.match(r"^(.*?)\s*[—–-]\s*(.+)$", v)
    if m and len(m.group(1)) > 1:
        return m.group(1).strip(), m.group(2).strip()
    return v, ""


def traduire(feuilles, coach_id):
    """Les 80 documents, prêts pour `partner_prospects`. FONCTION PURE.

    Aucune base n'est ouverte ici : c'est ce qui permet au banc d'essai de
    vérifier la traduction sans MongoDB, et au dry-run de ne rien risquer.
    """
    import api.server as S

    pilotage = feuilles.get("Pilotage") or []
    if not pilotage:
        raise SystemExit("Feuille « Pilotage » absente — fichier inattendu.")
    entetes = pilotage[0]

    def cel(ligne, nom):
        if nom not in entetes:
            return ""
        i = entetes.index(nom)
        return (ligne[i] if i < len(ligne) else "") or ""

    # --- Les jointures : le classeur est relationnel ---
    # Les messages J0/J+3/J+7 ne sont PAS dans « Pilotage » (sa colonne
    # « Message prêt » n'est qu'un drapeau Oui/Non) : ils vivent dans le Kit.
    kit = {}
    feuille_kit = feuilles.get("Vague 1 — Kit") or []
    if feuille_kit:
        ent_k = feuille_kit[0]
        for ligne in feuille_kit[1:]:
            def k(nom):
                if nom not in ent_k:
                    return ""
                i = ent_k.index(nom)
                return (ligne[i] if i < len(ligne) else "") or ""
            if k("ID"):
                kit[k("ID").strip().upper()] = {
                    "canal": k("Meilleur canal"), "approche": k("Approche"),
                    "j0": k("Message J0"), "j3": k("Message J+3"),
                    "j7": k("Message J+7"), "interesse": k("Message si intéressé"),
                    "src1": k("Source officielle"), "src2": k("Source secondaire"),
                    "verifie": k("Vérifié le"),
                }
    # La vague ne figure pas dans « Pilotage » non plus.
    vagues = {}
    feuille_top = feuilles.get("TOP 20 global") or []
    if feuille_top:
        ent_t = feuille_top[0]
        i_id = ent_t.index("ID") if "ID" in ent_t else None
        i_vg = ent_t.index("Vague") if "Vague" in ent_t else None
        if i_id is not None and i_vg is not None:
            for ligne in feuille_top[1:]:
                if i_id < len(ligne) and ligne[i_id]:
                    vagues[ligne[i_id].strip().upper()] = (
                        ligne[i_vg] if i_vg < len(ligne) else "")

    documents = []
    for ligne in pilotage[1:]:
        ref = cel(ligne, "ID").strip().upper()
        if not ref:
            continue
        anomalies = []
        notes = []

        # --- catégorie : libellé ET préfixe doivent concorder ---
        libelle = S.p3s1_normaliser(cel(ligne, "Catégorie"))
        par_libelle = CATEGORIE_PAR_LIBELLE.get(libelle)
        par_prefixe = CATEGORIE_PAR_PREFIXE.get(ref.split("-")[0])
        if par_libelle and par_prefixe and par_libelle != par_prefixe:
            anomalies.append("categorie ambigue : libelle « %s » -> %s, prefixe %s -> %s"
                             % (cel(ligne, "Catégorie"), par_libelle,
                                ref.split("-")[0], par_prefixe))
        categorie = par_libelle or par_prefixe
        if not categorie:
            anomalies.append("categorie inconnue : « %s »" % cel(ligne, "Catégorie"))

        statut = STATUT_PAR_LIBELLE.get(S.p3s1_normaliser(cel(ligne, "Statut")))
        if not statut:
            anomalies.append("statut inconnu : « %s »" % cel(ligne, "Statut"))

        info_kit = kit.get(ref, {})

        # --- coordonnées : présentes, ou nulles AVEC la trace de l'original ---
        courriel = _presente(cel(ligne, "E-mail"))
        if courriel and not _RE_MAIL.match(courriel):
            notes.append("E-mail (source XLSX, non exploitable) : %s" % cel(ligne, "E-mail"))
            courriel = ""
        elif not courriel and cel(ligne, "E-mail").strip():
            notes.append("E-mail (source XLSX) : %s" % cel(ligne, "E-mail").strip())

        telephone = _presente(cel(ligne, "Téléphone"))
        if telephone and len(re.sub(r"\D", "", telephone)) < 6:
            notes.append("Téléphone (source XLSX, non exploitable) : %s" % telephone)
            telephone = ""
        elif not telephone and cel(ligne, "Téléphone").strip():
            notes.append("Téléphone (source XLSX) : %s" % cel(ligne, "Téléphone").strip())

        insta = _presente(cel(ligne, "Instagram"))
        if not insta and cel(ligne, "Instagram").strip():
            notes.append("Instagram (source XLSX) : %s" % cel(ligne, "Instagram").strip())

        reseaux, reste_reseaux = _reseaux(cel(ligne, "Autres réseaux"))
        if reste_reseaux:
            notes.append("Autres réseaux : %s" % reste_reseaux)

        nom_contact, role_contact = _contact(cel(ligne, "Contact + rôle"))

        # --- tout ce qui n'a pas de champ dédié finit en note, jamais perdu ---
        for etiquette, colonne in (("Pourquoi Afroboost", "Pourquoi Afroboost"),
                                   ("Idée de collaboration", "Idée de collaboration"),
                                   ("Source (libellé)", "Source"),
                                   ("Notes Cowork", "Notes")):
            valeur = _presente(cel(ligne, colonne))
            if valeur:
                notes.append("%s : %s" % (etiquette, valeur))

        # GIANT STUDIO — la seule ligne dont le traitement diffère, et la
        # différence est CONSIGNÉE, pas encodée dans un statut inventé.
        if ref == "ECO-01":
            notes.insert(0, "RELATION CHAUDE — Afroboost est déjà au planning. "
                            "Traitement séparé de la vague commerciale : ne pas "
                            "inclure dans un envoi groupé. Aucun partenariat "
                            "officiel n'existe à ce jour.")

        document = {
            "ref": ref,
            "organisation_name": cel(ligne, "Nom").strip(),
            "category": categorie,
            "status": statut,
            "city": _presente(cel(ligne, "Ville")),
            "address": _presente(cel(ligne, "Adresse")),
            "website": _presente(cel(ligne, "Site")),
            "instagram": insta,
            "facebook": reseaux.get("facebook", ""),
            "linkedin": reseaux.get("linkedin", ""),
            "tiktok": reseaux.get("tiktok", ""),
            "public_email": courriel,
            "public_phone": telephone,
            "contact_name": nom_contact,
            "contact_role": role_contact,
            # Le Kit porte le canal le plus précis (il nomme l'adresse exacte) ;
            # « Pilotage » sert de repli pour les 70 autres.
            "preferred_channel": _presente(info_kit.get("canal")) or _presente(cel(ligne, "Canal")),
            "approach": _presente(info_kit.get("approche")) or _presente(cel(ligne, "Approche")),
            "score": _nombre(cel(ligne, "Score /10")),
            "priority": (_presente(cel(ligne, "Priorité")) or "").upper() or None,
            "wave": _presente(vagues.get(ref, "")),
            "source_url": (_presente(info_kit.get("src1"))
                           or _presente(cel(ligne, "Source officielle (URL)"))
                           or _presente(cel(ligne, "Source"))),
            "secondary_source_url": (_presente(info_kit.get("src2"))
                                     or _presente(cel(ligne, "Source secondaire (URL)"))),
            "verified_at": _presente(info_kit.get("verifie")) or _presente(cel(ligne, "Vérifié le")),
            "j0_message": _presente(info_kit.get("j0")),
            "j3_message": _presente(info_kit.get("j3")),
            "j7_message": _presente(info_kit.get("j7")),
            "interested_message": _presente(info_kit.get("interesse")),
            # Le fichier ne porte AUCUNE colonne de type de collaboration. La
            # déduire de la catégorie poserait sur chaque prospect une intention
            # que personne n'a vérifiée. Elle reste nulle : le coach la choisit.
            "collaboration_type": None,
            "notes": "\n".join(notes),
            "_anomalies": anomalies,
        }
        # Les colonnes « Candidature », « Accepté », « Lien/QR envoyé »,
        # « Réservations », « Présences », « Conversions » ne sont PAS importées :
        # ce sont des RÉSULTATS que P2 sait déjà calculer. Les recopier créerait
        # deux vérités qui finiraient par se contredire.
        documents.append(document)
    return documents


# ============================================================================
# 3. LE PLAN — lecture pure, aucune écriture
# ============================================================================

# Mis à jour à chaque import : ce que Cowork requalifie.
CHAMPS_REQUALIFIABLES = (
    "organisation_name", "category", "city", "address", "website", "instagram",
    "facebook", "linkedin", "tiktok", "public_email", "public_phone",
    "contact_name", "contact_role", "preferred_channel", "approach", "score",
    "priority", "source_url", "secondary_source_url", "verified_at",
    "j0_message", "j3_message", "j7_message", "interested_message",
)
# JAMAIS réécrits par un import : l'état vivant appartient au terrain.
CHAMPS_INTOUCHABLES = ("status", "notes", "wave", "collaboration_type",
                       "partner_application_id", "partner_id", "coach_id",
                       "id", "created_at", "created_by")


async def planifier(db, documents, coach_id):
    """Classe chaque ligne. NE MODIFIE RIEN."""
    import api.server as S

    par_ref = {}
    async for existant in db[S.P3S1_COLLECTION].find(
            {"coach_id": coach_id}, {"_id": 0}):
        if existant.get("ref"):
            par_ref[existant["ref"]] = existant
    par_cle = {}
    for existant in par_ref.values():
        par_cle.setdefault(existant.get("dedupe_key") or "", []).append(existant)

    plan = {"nouveaux": [], "identiques": [], "mises_a_jour": [],
            "conflits": [], "invalides": []}
    vus = {}

    for doc in documents:
        anomalies = list(doc.pop("_anomalies", []))

        if doc["ref"] in vus:
            plan["conflits"].append((doc, ["ref « %s » présente deux fois dans le "
                                           "fichier" % doc["ref"]]))
            continue
        vus[doc["ref"]] = True

        # La validation est celle de l'API, pas une copie.
        try:
            corps = {k: v for k, v in doc.items() if v not in ("", None)}
            corps.setdefault("category", doc.get("category") or "")
            S.p3s1_champs_valides(corps, creation=True)
        except Exception as err:
            anomalies.append("refusé par la validation P3-S1 : %s"
                             % getattr(err, "detail", err))
        if anomalies:
            plan["invalides"].append((doc, anomalies))
            continue

        doc["dedupe_key"] = S.p3s1_cle_doublon(doc["organisation_name"], doc["city"])
        existant = par_ref.get(doc["ref"])

        if existant is None:
            # Pas de `ref` connue — mais peut-être la même organisation sous une
            # autre référence. On ne tranche pas : on signale.
            homonymes = [a for a in par_cle.get(doc["dedupe_key"], [])
                         if a.get("ref") != doc["ref"]]
            if homonymes:
                plan["conflits"].append((doc, [
                    "même organisation+ville que « %s » (ref %s) mais ref différente — "
                    "aucune fusion automatique" % (h.get("organisation_name"), h.get("ref"))
                    for h in homonymes]))
            else:
                plan["nouveaux"].append(doc)
            continue

        changements = {}
        for champ in CHAMPS_REQUALIFIABLES:
            neuf = doc.get(champ)
            neuf = None if neuf in ("", None) else neuf
            ancien = existant.get(champ)
            ancien = None if ancien in ("", None) else ancien
            # Un champ VIDÉ dans le fichier n'efface pas une valeur connue :
            # une absence n'est pas une correction.
            if neuf is not None and neuf != ancien:
                changements[champ] = {"avant": ancien, "apres": neuf}
        if changements:
            plan["mises_a_jour"].append((doc, existant, changements))
        else:
            plan["identiques"].append(doc)

    return plan


async def appliquer(db, plan, coach_id):
    """Écrit le plan. Les créations et les requalifications, rien d'autre."""
    import uuid
    from datetime import datetime, timezone
    import api.server as S

    maintenant = datetime.now(timezone.utc).isoformat()
    crees = majs = 0

    for doc in plan["nouveaux"]:
        prospect = {champ: (doc.get(champ) if doc.get(champ) not in ("",) else None)
                    for champ in doc if not champ.startswith("_")}
        prospect["id"] = str(uuid.uuid4())
        prospect["coach_id"] = coach_id
        prospect["created_by"] = coach_id
        prospect["created_at"] = maintenant
        prospect["updated_at"] = maintenant
        prospect["city_key"] = S.p3s1_normaliser(doc.get("city"))
        prospect["website_domain"] = S.p3s1_domaine(doc.get("website"))
        for champ in S.P3S1_DATES:
            prospect.setdefault(champ, None)
        prospect.setdefault("partner_application_id", None)
        prospect.setdefault("partner_id", None)
        prospect.setdefault("collaboration_type", None)
        await db[S.P3S1_COLLECTION].insert_one(prospect)
        crees += 1

    for doc, existant, changements in plan["mises_a_jour"]:
        champs = {c: v["apres"] for c, v in changements.items()}
        champs["updated_at"] = maintenant
        if "organisation_name" in champs or "city" in champs:
            champs["dedupe_key"] = S.p3s1_cle_doublon(
                champs.get("organisation_name", existant.get("organisation_name")),
                champs.get("city", existant.get("city")))
            champs["city_key"] = S.p3s1_normaliser(
                champs.get("city", existant.get("city")))
        if "website" in champs:
            champs["website_domain"] = S.p3s1_domaine(champs["website"])
        await db[S.P3S1_COLLECTION].update_one(
            {"id": existant["id"]}, {"$set": champs})
        majs += 1

    return {"crees": crees, "mis_a_jour": majs}


# ============================================================================
# 4. LE RAPPORT
# ============================================================================

def afficher(plan, documents, applique=False):
    total = len(documents)
    print("\n" + "=" * 78)
    print("IMPORT PROSPECTS COWORK — %s" % ("APPLIQUÉ" if applique else "ESSAI À BLANC (rien n'est écrit)"))
    print("=" * 78)
    print("  total source          %3d" % total)
    print("  nouveaux              %3d" % len(plan["nouveaux"]))
    print("  déjà présents         %3d" % len(plan["identiques"]))
    print("  mises à jour possible %3d" % len(plan["mises_a_jour"]))
    print("  conflits              %3d" % len(plan["conflits"]))
    print("  invalides             %3d" % len(plan["invalides"]))
    somme = (len(plan["nouveaux"]) + len(plan["identiques"]) + len(plan["mises_a_jour"])
             + len(plan["conflits"]) + len(plan["invalides"]))
    print("  ---------------------------")
    print("  somme                 %3d   %s" % (somme, "OK" if somme == total else "!! ÉCART"))

    if plan["conflits"]:
        print("\n  CONFLITS — aucun n'est tranché automatiquement :")
        for doc, motifs in plan["conflits"]:
            print("    %-8s %-30s %s" % (doc["ref"], doc["organisation_name"][:30], motifs[0]))
    if plan["invalides"]:
        print("\n  INVALIDES — refusés, jamais corrigés en silence :")
        for doc, motifs in plan["invalides"]:
            print("    %-8s %-30s %s" % (doc.get("ref"), (doc.get("organisation_name") or "")[:30], motifs[0]))
    if plan["mises_a_jour"]:
        print("\n  REQUALIFICATIONS (l'état vivant n'est jamais touché) :")
        for doc, _e, changements in plan["mises_a_jour"][:12]:
            print("    %-8s %-26s %s" % (doc["ref"], doc["organisation_name"][:26],
                                         ", ".join(sorted(changements))[:70]))
        if len(plan["mises_a_jour"]) > 12:
            print("    ... et %d autres" % (len(plan["mises_a_jour"]) - 12))

    if plan["nouveaux"]:
        import collections
        print("\n  RÉPARTITION DES NOUVEAUX :")
        for cle, libelle in (("category", "catégorie"), ("priority", "priorité"),
                             ("wave", "vague"), ("status", "statut")):
            compte = collections.Counter((d.get(cle) or "—") for d in plan["nouveaux"])
            print("    %-10s %s" % (libelle, dict(compte)))
        avec = sum(1 for d in plan["nouveaux"] if d.get("j0_message"))
        print("    messages J0 prêts : %d" % avec)
    print("=" * 78 + "\n")


def principal():
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--fichier", default=CHEMIN_DEFAUT)
    parseur.add_argument("--appliquer", action="store_true",
                         help="écrit réellement (sans ce drapeau : essai à blanc)")
    parseur.add_argument("--coach", default="")
    options = parseur.parse_args()

    if not os.path.exists(options.fichier):
        raise SystemExit("Fichier introuvable : %s" % options.fichier)

    from dotenv import dotenv_values
    config = dotenv_values(os.path.join(RACINE, ".env.local"))
    os.environ.setdefault("MONGO_URL", config.get("MONGO_URL") or "")
    os.environ.setdefault("JWT_SECRET", config.get("JWT_SECRET") or "import-local")
    coach = (options.coach or config.get("AUTHORIZED_COACH_EMAIL")
             or "contact.artboost@gmail.com").strip().lower()

    from motor.motor_asyncio import AsyncIOMotorClient
    import api.server as S
    client = AsyncIOMotorClient(config["MONGO_URL"], serverSelectionTimeoutMS=20000)
    base = client[config.get("DB_NAME") or "afroboost_db"]

    feuilles = lire_classeur(options.fichier)
    documents = traduire(feuilles, coach)
    print("\nfichier  : %s" % options.fichier)
    print("feuilles : %s" % ", ".join(feuilles))
    print("coach    : %s" % coach)
    print("cible    : %s.%s" % (base.name, S.P3S1_COLLECTION))

    boucle = asyncio.new_event_loop()
    plan = boucle.run_until_complete(planifier(base, documents, coach))
    afficher(plan, documents, applique=False)

    if options.appliquer:
        if plan["conflits"] or plan["invalides"]:
            raise SystemExit("REFUS : des conflits ou des lignes invalides subsistent. "
                             "Corrige le fichier, relance l'essai à blanc.")
        resultat = boucle.run_until_complete(appliquer(base, plan, coach))
        print("APPLIQUÉ : %d créés, %d mis à jour\n" % (resultat["crees"], resultat["mis_a_jour"]))
    else:
        print("Essai à blanc — RIEN n'a été écrit. Relancer avec --appliquer.\n")
    client.close()


if __name__ == "__main__":
    principal()
