# -*- coding: utf-8 -*-
"""LOT M1-GEO1 — UNE REGION STRUCTUREE, PARCE QUE LE TEXTE LIBRE NE PEUT PAS.

CE QUI BLOQUAIT. La page `/cours-essai-gratuit-neuchatel` s'intitule
« a Neuchatel » mais rien ne garantissait qu'elle n'afficherait pas une seance
lausannoise : le seul champ geographique d'un cours etait `locationName`, du
TEXTE LIBRE. Le recensement l'a montre — 23 cours, 8 libelles pour 4 endroits,
dont « LAUSANNE ESPLANADE & CASINO DE MONTBENON » et
« ESPLANADE & CASINO DE MONTBENON, LAUSANNE ». Filtrer la-dessus serait une
recherche par morceau de texte, et `courseLocation.js` documente deja que
l'alias `location` a DIVERGE en production.

CE QUE CE LOT AJOUTE. Un champ `region` sur le cours, avec une LISTE FERMEE —
la meme pour la validation serveur, le selecteur du dashboard et les pages SEO.

LA REGLE QUI COMPTE, ET ELLE EST FAIL CLOSED : absent, vide, non classe ou
inconnu -> le cours n'apparait sur AUCUNE page locale. Mieux vaut une page
incomplete qu'une page qui ment sur sa ville.

CE QUI NE BOUGE PAS. `/api/courses/occurrences` sans region rend exactement ce
qu'il rendait ; le ChatWidget n'est pas touche ; aucune reservation, aucun
tarif, aucune regle d'essai.

AUCUNE BASE REELLE, AUCUN RESEAU, AUCUNE DONNEE PERSONNELLE.
    python3 tests/test_m1geo1_region.py
"""
import ast, asyncio, io, json, os, re, sys
from datetime import datetime, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.join(RACINE, "tests"))

# La machinerie du banc M1 : meme faux Mongo, meme extraction du VRAI server.py.
import test_m1_page_seo_locale as M1

ARBRE, LIGNES = M1.ARBRE, M1.LIGNES
RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


NE = "neuchatel"
LA = "lausanne"
LIEU_NE = "Bord du Lac, Auvernier, Neuchâtel"
LIEU_LA = "ESPLANADE & CASINO DE MONTBENON, LAUSANNE"


def source_de(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return "".join(LIGNES[n.lineno - 1:n.end_lineno])
    return ""


def monde(regions):
    """Un cours a venir par entree de `regions` — la region est le SEUL
    discriminant : les deux lieux restent du texte libre, jamais filtre."""
    db, j = M1.Base(), M1.Journal()
    docs = []
    for i, reg in enumerate(regions):
        d = {"id": "c%d" % i, "name": "Séance %d" % i,
             "date": (datetime.now() + timedelta(days=2 + i)).date().isoformat(),
             "time": "18:30", "coach_id": M1.COACH, "visible": True,
             "locationName": LIEU_NE if reg != LA else LIEU_LA}
        if reg is not None:
            d["region"] = reg
        docs.append(d)
    db.courses.docs = docs
    return db, j


async def principal():
    ns = M1.monter(M1.Base(), M1.Journal())

    # ---- 1. LA LISTE FERMEE, UNE SEULE ------------------------------------
    verifier("1. La liste fermee des regions existe", "M1GEO1_REGIONS" in ns)
    regions = tuple(ns.get("M1GEO1_REGIONS") or ())
    verifier("2. Elle contient exactement `neuchatel` et `lausanne`",
             tuple(sorted(regions)) == (LA, NE), "regions=%s" % (regions,))

    # ---- 2. LA NORMALISATION ET LE REFUS -----------------------------------
    norm = ns.get("m1geo1_region_normalisee")
    verifier("3. La normalisation existe", callable(norm))
    if callable(norm):
        for entree in ("Neuchâtel", "NEUCHATEL", "neuchatel", "  Neuchatel  ",
                       "NEUCHÂTEL", "neuchâtel"):
            j, st = norm(entree)
            verifier("4. « %s » -> `neuchatel`" % entree, (j, st) == (NE, "valide"),
                     "obtenu=%r" % ((j, st),))
        j, st = norm("Lausanne")
        verifier("5. « Lausanne » -> `lausanne`", (j, st) == (LA, "valide"), "%r" % ((j, st),))
        for vide in (None, "", "   "):
            j, st = norm(vide)
            verifier("6. %r -> non classe (jamais une region par defaut)" % vide,
                     (j, st) == ("", "absent"), "%r" % ((j, st),))
        for faux in ("geneve", "neuchatelll", "Neuchatel-Ville", "ne", "lausane", "<script>"):
            j, st = norm(faux)
            verifier("7. « %s » -> INCONNUE (jamais enregistree en silence)" % faux,
                     st == "inconnue", "%r" % ((j, st),))

    # ---- 3. LE REFUS EST APPLIQUE AUX DEUX ECRIVAINS -----------------------
    for ecrivain in ("create_course", "update_course"):
        src = source_de(ecrivain)
        verifier("8. `%s` valide la region" % ecrivain,
                 "m1geo1_region_normalisee" in src)
        verifier("9. `%s` REFUSE une region inconnue en 400" % ecrivain,
                 "inconnue" in src and "status_code=400" in src)

    # ---- 4. LE MODELE ------------------------------------------------------
    for modele in ("Course", "CourseCreate"):
        src = ""
        for n in ast.walk(ARBRE):
            if isinstance(n, ast.ClassDef) and n.name == modele:
                src = "".join(LIGNES[n.lineno - 1:n.end_lineno])
        verifier("10. `%s` porte `region`" % modele, re.search(r"^\s+region\s*:", src, re.M) is not None)
        verifier("11. `%s` : `region` est OPTIONNEL (aucune migration forcee)" % modele,
                 re.search(r"^\s+region\s*:\s*Optional\[str\]\s*=\s*None", src, re.M) is not None)

    # ---- 5. LE FILTRE DE LA ROUTE PUBLIQUE ---------------------------------
    src_occ = source_de("n456_occurrences_publiques")
    verifier("12. La route accepte un parametre `region`",
             re.search(r"async def n456_occurrences_publiques\([^)]*region", src_occ) is not None)
    verifier("13. Le filtre porte sur le champ `region`, JAMAIS sur `locationName`",
             '"region"' in src_occ and "locationName" not in src_occ.split("_filtre")[-1][:400])
    verifier("14. Aucune adresse ecrite dans le filtrage",
             not any(m.lower() in src_occ.lower() for m in
                     ("Auvernier", "Vallangines", "Montbenon", "Vidy", "St-Blaise")))

    occ = ns["n456_occurrences_publiques"]

    # --- le coeur du lot : les deux villes dans le meme jeu ---
    db, j = monde([NE, LA])
    r_ne = await M1.monter(db, j)["n456_occurrences_publiques"](coach=M1.COACH, region=NE)
    ids = [o["course_id"] for o in r_ne["occurrences"]]
    verifier("15. Page Neuchatel : la seance neuchateloise est la", "c0" in ids, ids)
    verifier("16. Page Neuchatel : la seance LAUSANNOISE est ABSENTE", "c1" not in ids, ids)

    db, j = monde([NE, LA])
    r_la = await M1.monter(db, j)["n456_occurrences_publiques"](coach=M1.COACH, region=LA)
    ids = [o["course_id"] for o in r_la["occurrences"]]
    verifier("17. Page Lausanne : le meme moteur rend l'autre ville", ids == ["c1"], ids)

    db, j = monde([None, "", NE])
    r = await M1.monter(db, j)["n456_occurrences_publiques"](coach=M1.COACH, region=NE)
    ids = [o["course_id"] for o in r["occurrences"]]
    verifier("18. Cours SANS region -> absent de toute page locale", ids == ["c2"], ids)

    db, j = monde([NE])
    r = await M1.monter(db, j)["n456_occurrences_publiques"](coach=M1.COACH, region="geneve")
    verifier("19. Region inconnue demandee -> liste vide, aucun oracle",
             r == {"occurrences": []}, r)

    db, j = monde([NE, LA, None])
    r = await M1.monter(db, j)["n456_occurrences_publiques"](coach=M1.COACH)
    verifier("20. SANS region : la route generique rend TOUT, comme avant",
             sorted(o["course_id"] for o in r["occurrences"]) == ["c0", "c1", "c2"],
             [o["course_id"] for o in r["occurrences"]])

    db, j = monde([NE])
    db.courses.docs[0]["coach_id"] = "un-autre-coach"
    r = await M1.monter(db, j)["n456_occurrences_publiques"](coach=M1.COACH, region=NE)
    verifier("21. Isolation tenant CONSERVEE : region et coach filtrent ensemble",
             r["occurrences"] == [], r)

    # ---- 6. LA PAGE SEO ----------------------------------------------------
    src_page = source_de("_m1_seances")
    verifier("22. La page passe explicitement sa region a la source",
             "region=" in src_page and "_M1_REGION" in src_page)
    verifier("23. La region de la page vient de la liste fermee",
             str(ns.get("_M1_REGION")) in regions, str(ns.get("_M1_REGION")))

    db, j = monde([NE, LA])
    _, corps = await M1.rendre(db, j)
    verifier("24. HTML de la page Neuchatel : la seance lausannoise n'y est pas",
             "Séance 0" in corps and "Séance 1" not in corps)
    verifier("25. HTML : le lieu lausannois n'apparait nulle part", LIEU_LA not in corps)
    plats = [o for b in M1.blocs_jsonld(corps) for o in M1._plat(b)]
    evs = [o for o in plats if o.get("@type") == "Event"]
    verifier("26. JSON-LD : un seul `Event`, le neuchatelois", len(evs) == 1, [e.get("name") for e in evs])
    verifier("27. JSON-LD : aucun lieu lausannois",
             all((e.get("location") or {}).get("name") != LIEU_LA for e in evs))

    db, j = monde([None, None])
    _, corps = await M1.rendre(db, j)
    verifier("28. Aucun cours classe -> page honnete, aucune seance inventee",
             "Aucune séance" in corps and "Séance 0" not in corps)

    # ---- 7. LE DASHBOARD : UN SELECTEUR, PAS UNE SAISIE LIBRE --------------
    cm = io.open(os.path.join(RACINE, "frontend", "src", "components", "dashboard",
                              "CoursesManager.js"), encoding="utf-8").read()
    verifier("29. Le dashboard connait la region", "region" in cm)
    bloc = ""
    for m in re.finditer(r"<select[\s\S]{0,900}?</select>", cm):
        if "region" in m.group(0).lower():
            bloc = m.group(0)
    verifier("30. La region se choisit dans un `<select>`", bloc != "")
    # Le selecteur rend ses options DEPUIS la liste fermee — c'est la liste
    # qu'il faut lire, pas le balisage. (Premiere ecriture de ce controle :
    # elle cherchait les libelles dans le `<select>` lui-meme, ce qui testait la
    # FACON d'ecrire le composant plutot que la propriete voulue.)
    liste = re.search(r"const M1GEO1_REGIONS = \[([\s\S]*?)\];", cm)
    verifier("31a. Le selecteur rend ses options depuis la liste fermee",
             liste is not None and "M1GEO1_REGIONS.map" in bloc)
    corps_liste = liste.group(1) if liste else ""
    verifier("31b. La liste propose Non classe / Neuchatel / Lausanne",
             all(x in corps_liste for x in ("Non classé", "Neuchâtel", "Lausanne")),
             corps_liste[:120])
    verifier("32. AUCUNE saisie libre de region (pas d'`<input>` region)",
             not re.search(r'<input[^>]*(region|Région)', cm, re.I))
    # Et surtout : les JETONS du dashboard sont EXACTEMENT ceux du serveur.
    jetons_dash = tuple(sorted(
        v for v in re.findall(r"valeur:\s*'([^']*)'", corps_liste) if v))
    verifier("33. Le dashboard porte EXACTEMENT les jetons du serveur",
             jetons_dash == tuple(sorted(regions)),
             "dashboard=%s serveur=%s" % (jetons_dash, tuple(sorted(regions))))
    verifier("33b. Et il propose « Non classé » comme valeur vide legitime",
             "" in re.findall(r"valeur:\s*'([^']*)'", corps_liste))

    # ---- 8. CE QUI NE DOIT PAS BOUGER -------------------------------------
    cw = io.open(os.path.join(RACINE, "frontend", "src", "components",
                              "ChatWidget.js"), encoding="utf-8").read()
    debut = cw.index("var loadAvailableCourses = useCallback(")
    corps_cw = cw[debut:cw.index("\n  }, [", debut)]
    verifier("34. ChatWidget INCHANGE : il n'envoie aucune region",
             "region" not in corps_cw)
    verifier("35. ChatWidget INCHANGE : il lit toujours la route generique",
             "/courses/occurrences" in corps_cw)
    for interdit in ("price", "tarif", "reservation", "checkout", "discount", "used_sessions"):
        verifier("36. Le filtrage ne touche a aucune regle metier (`%s`)" % interdit,
                 interdit not in src_occ.lower() and interdit not in src_page.lower())

    # ---- 9. UN CHAMP ADDITIF, TOLERE PAR L'ANCIENNE APPLICATION -----------
    # L'ancienne application tourne encore pendant l'etiquetage des donnees.
    # Son modele `Course` ne connait pas `region` : il faut prouver qu'un
    # document qui le porte ne la fait PAS tomber.
    from pydantic import BaseModel, ConfigDict
    from typing import Optional as _Opt

    class CoursAncien(BaseModel):            # le modele TEL QU'IL ETAIT
        model_config = ConfigDict(extra="ignore")
        id: str
        name: str
        time: str
        locationName: str
        weekday: _Opt[int] = None
        date: _Opt[str] = None

    doc = {"id": "x", "name": "Séance", "time": "18:30",
           "locationName": LIEU_NE, "weekday": 0, "region": NE}
    try:
        ancien = CoursAncien(**doc)
        verifier("37. L'ancienne application lit le document SANS erreur", True)
        verifier("38. Elle ignore simplement `region` (extra=ignore)",
                 not hasattr(ancien, "region"))
    except Exception as e:
        verifier("37. L'ancienne application lit le document SANS erreur", False, str(e)[:90])
        verifier("38. Elle ignore simplement `region` (extra=ignore)", False, "")
    src_c = ""
    for n in ast.walk(ARBRE):
        if isinstance(n, ast.ClassDef) and n.name == "Course":
            src_c = "".join(LIGNES[n.lineno - 1:n.end_lineno])
    verifier("39. `Course` garde bien `extra=\"ignore\"`", 'extra="ignore"' in src_c)


if __name__ == "__main__":
    try:
        asyncio.run(principal())
    except Exception as _e:
        RESULTATS.append(("BANC INTERROMPU : %s: %s" % (type(_e).__name__, _e), False, ""))
    ok = 0
    for nom, bon, detail in RESULTATS:
        print(("  OK   " if bon else "  RATE ") + nom + (("   [%s]" % detail) if (detail and not bon) else ""))
        ok += 1 if bon else 0
    print("\n%d/%d au vert" % (ok, len(RESULTATS)))
    sys.exit(0 if ok == len(RESULTATS) else 1)
