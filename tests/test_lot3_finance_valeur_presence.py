# -*- coding: utf-8 -*-
"""LOT 3 FINANCE — LA VALEUR D'UNE PRESENCE, PUIS LE TOTAL D'UNE SEANCE.

LA QUESTION A LAQUELLE CE LOT REPOND. Pour un participant REELLEMENT PRESENT a
une occurrence precise : quelle valeur financiere correspond a CETTE presence ?
Puis, pour l'occurrence entiere : combien vaut la seance ?

CE QUI EST INTERDIT, ET TESTE COMME TEL.
  * Diviser le prix d'un pack par son nombre de seances pour inventer une
    valeur. 250 / 10 = 25 n'est PAS une regle : certaines presences valent
    reellement 15 CHF. La verite est `tarif_applique`, FIGE au moment de la
    reservation par LOT 3a.
  * Ecrire 0 quand on ne sait pas. Une valeur absente vaut « inconnu », jamais
    zero — zero est un montant REEL qui signifie « gratuit prouve ».
  * Compter un absent. Seul `validated: true` entre dans le bilan.

CE QUE CE LOT NE FAIT PAS : aucun partage partenaire, aucun pourcentage, aucun
ecran. C'est le moteur, et rien d'autre.

AUCUNE BASE, AUCUN RESEAU : les deux fonctions sont PURES.
    python3 tests/test_lot3_finance_valeur_presence.py
"""
import ast, importlib.util, io, os, sys, types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from tests._banc_qr import RESULTATS, verifier, _HTTPException  # noqa: E402

_fa = types.ModuleType("fastapi")
_fa.HTTPException = _HTTPException
_fa.APIRouter = object
_fa.Request = object
sys.modules.setdefault("fastapi", _fa)

_spec = importlib.util.spec_from_file_location(
    "l3f_shared", os.path.join(RACINE, "api", "routes", "shared.py"))
SHARED = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SHARED)

SRC_SHARED = io.open(os.path.join(RACINE, "api", "routes", "shared.py"),
                     encoding="utf-8").read()

VALEUR = getattr(SHARED, "lot3f_valeur_presence", None)
BILAN = getattr(SHARED, "lot3f_bilan_occurrence", None)

OCC = "2026-08-26T18:30:00"
COURS = "cours-pulse-1"


def _resa(**kw):
    """Une reservation VALIDEE par defaut : le bilan ne parle que de presences."""
    d = {"id": "r1", "userName": "Alice", "userEmail": "alice@ex.test",
         "validated": True, "courseId": COURS, "datetime": OCC,
         "coach_id": "coach@test"}
    d.update(kw)
    return d


# ═══════════════════════════════════════════════════════════════════════════
# A a E — LA VALEUR VIENT DU TARIF FIGE
# ═══════════════════════════════════════════════════════════════════════════
def partie_valeurs():
    if not VALEUR:
        verifier("A. `lot3f_valeur_presence` existe", False, "fonction absente")
        return

    # A — PULSE : le snapshot dit 15, et c'est 15. Surtout pas 250/10 = 25.
    l = VALEUR(_resa(tarif_applique=15.0, tarif_raison="forfait",
                     promoCode="PULSE-01"),
               {"code": "PULSE-01", "offer_price": 250.0, "total_sessions": 10},
               {"code": "PULSE-01", "stripe_amount": 250.0,
                "session_id": "cs_1", "maxUses": 10})
    verifier("A. PULSE : la valeur est le tarif FIGE (15), jamais le pack "
             "divise (250/10 = 25)",
             l.get("valeur") == 15.0 and l.get("statut_valeur") == "connu",
             "valeur=%r statut=%r" % (l.get("valeur"), l.get("statut_valeur")))
    verifier("A2. ... et la raison est conservee telle qu'elle a ete figee",
             l.get("tarif_raison") == "forfait", "raison=%r" % l.get("tarif_raison"))

    # B — cours a l'unite
    l = VALEUR(_resa(tarif_applique=30.0, tarif_raison="public", totalPrice=30.0), None, None)
    verifier("B. cours a l'unite : 30 CHF",
             l.get("valeur") == 30.0 and l.get("statut_valeur") == "connu",
             "valeur=%r" % l.get("valeur"))

    # C — essai : ZERO PROUVE, ce n'est pas « inconnu »
    l = VALEUR(_resa(tarif_applique=0.0, tarif_raison="essai"), None, None)
    verifier("C. essai gratuit : 0 CHF, et c'est un montant CONNU "
             "(zero prouve n'est pas une absence de valeur)",
             l.get("valeur") == 0.0 and l.get("statut_valeur") == "connu",
             "valeur=%r statut=%r" % (l.get("valeur"), l.get("statut_valeur")))

    # D — offert
    l = VALEUR(_resa(tarif_applique=0.0, tarif_raison="offert"), None, None)
    verifier("D. offert : 0 CHF, connu, et la raison reste `offert`",
             l.get("valeur") == 0.0 and l.get("statut_valeur") == "connu"
             and l.get("tarif_raison") == "offert",
             "valeur=%r raison=%r" % (l.get("valeur"), l.get("tarif_raison")))

    # E — promo : le montant REELLEMENT retenu, pas le plein tarif
    l = VALEUR(_resa(tarif_applique=24.0, tarif_raison="promo", tarif_public=30.0), None, None)
    verifier("E. promo : la valeur est le montant retenu (24), pas le plein "
             "tarif (30)", l.get("valeur") == 24.0, "valeur=%r" % l.get("valeur"))

    # Futur tarif membre : meme regle, aucune exception
    l = VALEUR(_resa(tarif_applique=15.0, tarif_raison="membre", tarif_public=30.0), None, None)
    verifier("E2. tarif membre : le montant fige (15) fait foi, "
             "le plein tarif (30) ne sert que de repere",
             l.get("valeur") == 15.0 and l.get("tarif_raison") == "membre",
             "valeur=%r" % l.get("valeur"))


# ═══════════════════════════════════════════════════════════════════════════
# F — CE QU'ON NE SAIT PAS RESTE INCONNU
# ═══════════════════════════════════════════════════════════════════════════
def partie_inconnu():
    if not VALEUR:
        return
    # Aucun snapshot, et un forfait dont le montant n'est PAS prouve
    # (`offer_price` est un prix de catalogue, pas une preuve d'encaissement).
    l = VALEUR(_resa(promoCode="VIEUX-01"),
               {"code": "VIEUX-01", "offer_price": 250.0, "total_sessions": 10},
               {"code": "VIEUX-01", "maxUses": 10})
    verifier("F. historique sans preuve : la valeur est INCONNUE, "
             "jamais un 0 invente",
             l.get("statut_valeur") == "inconnu" and l.get("valeur") is None,
             "valeur=%r statut=%r" % (l.get("valeur"), l.get("statut_valeur")))
    verifier("F2. ... et surtout PAS 25.0 (250/10 sur un montant non prouve)",
             l.get("valeur") != 25.0, "valeur=%r" % l.get("valeur"))

    # Un montant PROUVE sans snapshot : la valeur par seance est calculable, et
    # la source est nommee — on ne fait pas passer un repli pour un tarif fige.
    l = VALEUR(_resa(promoCode="PROUVE-01"),
               {"code": "PROUVE-01", "renewal_sessions": 10},
               {"code": "PROUVE-01", "stripe_amount": 150.0,
                "session_id": "cs_x", "maxUses": 10})
    verifier("F3. montant PROUVE sans snapshot : la valeur est connue (15.0) "
             "et sa source est nommee, pas confondue avec un tarif fige",
             l.get("valeur") == 15.0 and l.get("statut_valeur") == "connu"
             and l.get("source_valeur") != "snapshot",
             "valeur=%r source=%r" % (l.get("valeur"), l.get("source_valeur")))


# ═══════════════════════════════════════════════════════════════════════════
# G, K, L — QUI ENTRE DANS LE BILAN, ET DANS QUEL BILAN
# ═══════════════════════════════════════════════════════════════════════════
def partie_bilan():
    if not (VALEUR and BILAN):
        verifier("G. `lot3f_bilan_occurrence` existe", False, "fonction absente")
        return

    lignes = [
        VALEUR(_resa(id="r1", userName="Alice", userEmail="a@ex.test",
                     tarif_applique=15.0, tarif_raison="forfait"), None, None),
        VALEUR(_resa(id="r2", userName="Marc", userEmail="m@ex.test",
                     tarif_applique=30.0, tarif_raison="public"), None, None),
        VALEUR(_resa(id="r3", userName="Sophie", userEmail="s@ex.test",
                     tarif_applique=0.0, tarif_raison="essai"), None, None),
        # Paul : historique sans preuve -> inconnu
        VALEUR(_resa(id="r4", userName="Paul", userEmail="p@ex.test",
                     promoCode="VIEUX-01"),
               {"code": "VIEUX-01", "offer_price": 250.0}, {"code": "VIEUX-01"}),
        # G — un ABSENT ne doit pas entrer
        VALEUR(_resa(id="r5", userName="Absent", userEmail="x@ex.test",
                     validated=False, tarif_applique=30.0, tarif_raison="public"),
               None, None),
    ]
    b = BILAN(lignes)

    verifier("G. l'absent n'est PAS compte comme present",
             b.get("participants_presents") == 4,
             "presents=%r (attendu 4)" % b.get("participants_presents"))
    verifier("G2. ... et sa valeur n'entre pas dans le total",
             b.get("total_connu") == 45.0,
             "total=%r (attendu 45 = 15+30+0)" % b.get("total_connu"))
    verifier("G3. le compte des valeurs connues et inconnues est rendu",
             b.get("participants_valeur_connue") == 3
             and b.get("participants_valeur_inconnue") == 1,
             "connues=%r inconnues=%r" % (b.get("participants_valeur_connue"),
                                          b.get("participants_valeur_inconnue")))
    verifier("G4. le bilan rend une ligne par present, pas un simple total",
             len(b.get("lignes") or []) == 4,
             "lignes=%r" % len(b.get("lignes") or []))

    # J — la meme presence ne compte qu'UNE fois, meme si deux reservations
    # la decrivent (le vrai double comptage d'un bilan de seance).
    doublon = lignes[:2] + [VALEUR(_resa(id="r99", userName="Alice",
                                         userEmail="a@ex.test",
                                         tarif_applique=15.0,
                                         tarif_raison="forfait"), None, None)]
    b2 = BILAN(doublon)
    verifier("J. un participant present DEUX fois a la meme occurrence "
             "ne compte qu'une fois",
             b2.get("participants_presents") == 2 and b2.get("total_connu") == 45.0,
             "presents=%r total=%r" % (b2.get("participants_presents"),
                                       b2.get("total_connu")))

    # K — deux occurrences du meme cours = deux bilans distincts
    autre = VALEUR(_resa(id="r6", userName="Alice", userEmail="a@ex.test",
                         datetime="2026-09-02T18:30:00",
                         tarif_applique=15.0, tarif_raison="forfait"), None, None)
    b3 = BILAN(lignes + [autre], occurrence=OCC)
    verifier("K. deux occurrences du meme cours donnent des bilans SEPARES",
             b3.get("participants_presents") == 4,
             "presents=%r (l'occurrence du 02/09 ne doit pas entrer)"
             % b3.get("participants_presents"))

    # L — cloisonnement : la valeur ne franchit pas la frontiere d'un coach
    etranger = VALEUR(_resa(id="r7", userName="Autre", userEmail="z@ex.test",
                            coach_id="coach.b@test",
                            tarif_applique=99.0, tarif_raison="public"), None, None)
    b4 = BILAN(lignes + [etranger], coach_id="coach@test")
    verifier("L. cross-coach : la presence d'un autre coach n'entre pas "
             "dans le bilan",
             b4.get("total_connu") == 45.0 and b4.get("participants_presents") == 4,
             "total=%r presents=%r" % (b4.get("total_connu"),
                                       b4.get("participants_presents")))


# ═══════════════════════════════════════════════════════════════════════════
# PERIMETRE
# ═══════════════════════════════════════════════════════════════════════════
def partie_perimetre():
    arbre = ast.parse(SRC_SHARED)
    corps = ""
    for n in ast.walk(arbre):
        if isinstance(n, ast.FunctionDef) and n.name in (
                "lot3f_valeur_presence", "lot3f_bilan_occurrence"):
            f = ast.parse(ast.unparse(n)).body[0]
            b = list(f.body)
            if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant):
                b = b[1:]
            f.body = b or [ast.Pass()]
            corps += ast.unparse(f)
    verifier("P. le moteur est PUR : aucune ecriture, aucune lecture de base",
             corps and "update_one" not in corps and "insert_one" not in corps
             and "find_one" not in corps and "await" not in corps,
             "(fonctions absentes)" if not corps else "acces detecte")
    verifier("P2. aucun partage partenaire ni pourcentage dans ce lot",
             corps and "partenaire" not in corps.lower()
             and "pourcentage" not in corps.lower() and "* 0.3" not in corps)
    verifier("P3. MEMBER_PRICING_ENABLED n'est pas touche",
             "MEMBER_PRICING" not in corps)


def partie_hij_droits():
    """H, I, J — le moteur honore le droit qu'on lui donne, il n'en choisit pas."""
    if not (VALEUR and BILAN):
        return

    # H — PLUSIEURS OFFRES. LOT 3c-0c a deja tranche QUEL droit a servi ; le
    # moteur financier ne doit pas re-arbitrer. On lui passe le cours a l'unite
    # alors qu'un PULSE existe aussi : il doit valoriser CE qu'on lui donne.
    l = VALEUR(_resa(tarif_applique=30.0, tarif_raison="public",
                     promoCode="UNITE-01"),
               {"code": "UNITE-01", "offer_name": "Cours a l'unite"},
               {"code": "UNITE-01", "stripe_amount": 30.0,
                "session_id": "cs_u", "maxUses": 1})
    verifier("H. plusieurs offres : le moteur valorise le droit RESOLU en "
             "amont (30 = unite), il ne rearbitre pas vers le PULSE",
             l.get("valeur") == 30.0, "valeur=%r" % l.get("valeur"))

    # I — DEUX SOUSCRIPTIONS DE LA MEME OFFRE. Le departage appartient a
    # `choisir_abonnement` (LOT 3c-0c) ; le moteur reste sur le document recu.
    _bon = {"code": "DUO-01", "id": "sub-reel", "renewal_sessions": 10}
    l = VALEUR(_resa(promoCode="DUO-01"), _bon,
               {"code": "DUO-01", "stripe_amount": 150.0,
                "session_id": "cs_d", "maxUses": 10})
    verifier("I. deux souscriptions de la meme offre : le moteur valorise "
             "celle qu'on lui donne (15.0), sans en choisir une autre",
             l.get("valeur") == 15.0, "valeur=%r" % l.get("valeur"))

    # J — LE DOUBLE COMPTAGE D'UN ACHAT NE PEUT PAS ATTEINDRE CE CALCUL.
    # Un achat Stripe produit une ligne souscription ET une ligne paiement.
    # Ici on ne somme pas des achats : on somme des PRESENCES. Meme en donnant
    # au moteur un droit dont l'achat est double en base, une presence reste
    # UNE ligne et vaut UNE fois sa valeur.
    doublement_achete = {"code": "DUP-01", "renewal_sessions": 10}
    jumeau = {"code": "DUP-01", "stripe_amount": 250.0, "session_id": "cs_dup",
              "maxUses": 10, "canonical": True}
    lignes = [VALEUR(_resa(id="rA", userName="A", userEmail="a@ex.test",
                           promoCode="DUP-01"), doublement_achete, jumeau)]
    b = BILAN(lignes)
    verifier("J. un achat double en base (souscription + paiement) ne double "
             "PAS la valeur d'une presence : on somme des presences, pas des achats",
             b.get("total_connu") == 25.0 and b.get("participants_presents") == 1,
             "total=%r presents=%r" % (b.get("total_connu"),
                                       b.get("participants_presents")))


def principal():
    partie_valeurs()
    partie_inconnu()
    partie_bilan()
    partie_hij_droits()
    partie_perimetre()

    ok = sum(1 for _, c, _ in RESULTATS if c)
    print("\n" + "=" * 74)
    print("LOT 3 FINANCE — LA VALEUR D'UNE PRESENCE, PUIS LE TOTAL D'UNE SEANCE")
    print("=" * 74)
    for nom, cond, detail in RESULTATS:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom,
                              "" if cond or not detail else "\n          -> %s" % detail))
    print("-" * 74)
    print("Fonctions PURES : aucune base, aucun reseau. Donnees de production : 0")
    print("%d / %d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(principal())
