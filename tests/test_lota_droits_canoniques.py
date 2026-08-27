# -*- coding: utf-8 -*-
"""LOT A — LA VERITE DES SEANCES VIENT DE `discount_codes`.

Decision metier du 27/08/2026 : la page « Code promo » fait foi. Ce banc fige
la regle de lecture, cas par cas, sur les FORMES REELLES rencontrees en
production le 27/08/2026 — pas sur des exemples inventes.

CE QU'IL GARANTIT, ET C'EST TOUT LE LOT :
  * OK          -> `maxUses - used`, jamais `subscriptions.used_sessions` ;
  * AUCUN_DROIT -> code inactif, expire ou epuise ;
  * AMBIGU      -> AUCUN chiffre : ni 0, ni la somme, ni le premier venu.

Le septieme test est le plus important du fichier : il prouve qu'un
`used_sessions` divergent NE DEPLACE PAS le resultat. C'est l'anti-repli, et
c'est la seule chose qui empeche l'ancienne chaine de revenir par la fenetre.

AUCUNE BASE REELLE, AUCUN RESEAU, AUCUNE DONNEE PERSONNELLE.
    python3 tests/test_lota_droits_canoniques.py
"""
import asyncio, importlib.util, os, re, sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

_spec = importlib.util.spec_from_file_location(
    "lota_shared", os.path.join(RACINE, "api", "routes", "shared.py"))
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


AUJ = "2026-08-27"


def code(nom, maxUses, used, active=True, expiresAt=None, **extra):
    d = {"code": nom, "maxUses": maxUses, "used": used, "active": active,
         "expiresAt": expiresAt}
    d.update(extra)
    return d


def sub(status="active", used_sessions=0, remaining_sessions=None):
    return {"status": status, "used_sessions": used_sessions,
            "remaining_sessions": remaining_sessions}


# ── 1. OK — LA DECISION DE REFERENCE ─────────────────────────────────────────
# AFR-53F288, cite dans la decision du 27/08/2026 : total 9, used 8, restant 1.
r = S.lota_etat_du_code([code("AFR-53F288", 9, 8, expiresAt="2026-09-13")],
                        [sub(used_sessions=8, remaining_sessions=1)], 0, AUJ)
verifier("1. AFR-53F288 : etat OK", r["etat"] == "OK", r["etat"])
verifier("1. AFR-53F288 : total 9", r["total"] == 9, r["total"])
verifier("1. AFR-53F288 : utilise 8", r["utilise"] == 8, r["utilise"])
verifier("1. AFR-53F288 : restant 1", r["restant"] == 1, r["restant"])
verifier("1. AFR-53F288 : aucun message", r["message"] == "", r["message"])

# ── 2. AUCUN_DROIT — les trois refus, tous lus dans `discount_codes` ─────────
for nom, doc, attendu in (
    ("inactif", code("X", 10, 2, active=False), "inactif"),
    ("expire", code("X", 10, 2, expiresAt="2026-08-26"), "expire"),
    ("epuise", code("X", 9, 9), "epuise"),
):
    r = S.lota_etat_du_code([doc], [], 0, AUJ)
    verifier("2. %s -> AUCUN_DROIT" % nom, r["etat"] == "AUCUN_DROIT", r["etat"])
    verifier("2. %s -> motif %s" % (nom, attendu), r["motif"] == attendu, r["motif"])
    verifier("2. %s -> aucun chiffre" % nom, r["restant"] is None, r["restant"])

r = S.lota_etat_du_code([], [], 0, AUJ)
verifier("2. aucun document -> AUCUN_DROIT", r["etat"] == "AUCUN_DROIT", r["etat"])

# Un code sans `expiresAt` n'expire pas : plusieurs codes a duree libre
# existent en production, les exclure les ferait disparaitre de leur espace.
r = S.lota_etat_du_code([code("DIANABOO2026", 9, 1, expiresAt=None)], [], 0, AUJ)
verifier("2. sans expiration -> OK", r["etat"] == "OK" and r["restant"] == 8, r)

# ── 3. AMBIGU / multi-fiches — le cas BASSBOOSTX-16 ─────────────────────────
# Deux fiches ACTIVES et contradictoires (9/45 et 6/12). `lota_resoudre_code`
# retiendrait `actifs[0]`, un ordre ARBITRAIRE : on refuse ce pari.
deux = [code("BASSBOOSTX-16", 45, 9, expiresAt="2027-05-05"),
        code("BASSBOOSTX-16", 12, 6, expiresAt="2027-07-10")]
r = S.lota_etat_du_code(deux, [sub(used_sessions=6)], 0, AUJ)
verifier("3. deux fiches -> AMBIGU", r["etat"] == "AMBIGU", r["etat"])
verifier("3. deux fiches -> motif", r["motif"] == "plusieurs_docs_code", r["motif"])
verifier("3. deux fiches -> restant None", r["restant"] is None, r["restant"])
verifier("3. deux fiches -> total None", r["total"] is None, r["total"])
verifier("3. deux fiches -> ni 0 ni somme",
         r["restant"] not in (0, 36, 6, 45, 12), r["restant"])
verifier("3. deux fiches -> message affiche",
         r["message"].startswith("Plusieurs forfaits"), r["message"])
verifier("3. deux fiches -> expiration conservee",
         r["expire_le"] == "2027-05-05", r["expire_le"])

# Une ambiguite sans consequence n'en est pas une : BASSBOOSTX-09 porte deux
# fiches, l'une inactive, l'autre expiree le 17/08. Quel que soit le document
# retenu, ce code ne donne plus rien. Le declarer AMBIGU rendrait ambigu son
# porteur — dont le VRAI forfait (AmandaBoost-26) est parfaitement lisible.
mortes = [code("BASSBOOSTX-09", 47, 31, active=False, expiresAt="2026-05-05"),
          code("BASSBOOSTX-09", 10, 8, expiresAt="2026-08-17")]
r = S.lota_etat_du_code(mortes, [sub(status="completed", used_sessions=10)], 0, AUJ)
verifier("3. deux fiches MORTES -> AUCUN_DROIT", r["etat"] == "AUCUN_DROIT", r["etat"])
verifier("3. deux fiches mortes -> motif lisible", r["motif"] == "expire", r["motif"])

# Une fiche morte a cote d'une vivante ne cree aucune hesitation : la vivante
# fait foi, et le chiffre est rendu.
melange = [code("X", 47, 31, active=False, expiresAt="2026-05-05"),
           code("X", 10, 2, expiresAt="2026-12-31")]
r = S.lota_etat_du_code(melange, [], 0, AUJ)
verifier("3. une seule fiche vivante -> OK",
         r["etat"] == "OK" and r["restant"] == 8, r)

# ── 4. AMBIGU / plusieurs `canonical: true` — la garde V429, rejouee ─────────
r = S.lota_etat_du_code(
    [code("X", 10, 1, canonical=True), code("X", 20, 2, canonical=True)], [], 0, AUJ)
verifier("4. deux canonical -> AMBIGU", r["etat"] == "AMBIGU", r["etat"])
verifier("4. deux canonical -> motif", r["motif"] == "code_indetermine", r["motif"])

# Un SEUL `canonical: true` tranche, meme au milieu d'autres fiches : c'est
# une decision humaine, prise pour cette raison exacte.
r = S.lota_etat_du_code(
    [code("X", 45, 40), code("X", 10, 3, canonical=True)], [], 0, AUJ)
verifier("4. un seul canonical -> il tranche",
         r["etat"] == "OK" and r["restant"] == 7 and r["motif"] == "canonical", r)
r = S.lota_etat_du_code([code("X", 10, 3, canonical=True)], [], 0, AUJ)
verifier("4. canonical unique et fiche unique -> OK",
         r["etat"] == "OK" and r["restant"] == 7, r)

# Un `canonical: true` VIVANT tranche, meme entoure d'autres fiches vivantes :
# c'est une decision humaine, et le filtre « vivants » ne doit pas l'annuler.
r = S.lota_etat_du_code(
    [code("X", 45, 40, expiresAt="2027-01-01"),
     code("X", 10, 3, canonical=True, expiresAt="2027-01-01")], [], 0, AUJ)
verifier("4. canonical vivant tranche malgre d'autres fiches vivantes",
         r["etat"] == "OK" and r["restant"] == 7, r)

# ... mais une decision CADUQUE ne tranche plus rien (cas reel BASSBOOSTX-31 :
# la fiche marquee canonique a expire, une autre vit encore et concorde avec
# l'abonnement actif).
r = S.lota_etat_du_code(
    [code("BASSBOOSTX-31", 7, 6, expiresAt="2026-09-30", canonical=False),
     code("BASSBOOSTX-31", 9, 0, expiresAt="2026-07-10", canonical=True)],
    [sub(used_sessions=6, remaining_sessions=1)], 0, AUJ)
verifier("4. canonical expire -> la fiche vivante fait foi",
         r["etat"] == "OK" and r["restant"] == 1, r)

# ── 5. AMBIGU / deux abonnements actifs — le cas CHRISTOUX10 ────────────────
# Meme code, deux abonnements ACTIFS disant 5 et 8 seances consommees.
r = S.lota_etat_du_code(
    [code("CHRISTOUX10", 10, 8, expiresAt="2026-09-03")],
    [sub(used_sessions=5, remaining_sessions=5), sub(used_sessions=8, remaining_sessions=2)],
    0, AUJ)
verifier("5. CHRISTOUX10 -> AMBIGU", r["etat"] == "AMBIGU", r["etat"])
verifier("5. CHRISTOUX10 -> motif", r["motif"] == "plusieurs_abonnements", r["motif"])
verifier("5. CHRISTOUX10 -> aucun chiffre", r["restant"] is None, r["restant"])

# Un abonnement CLOS a cote d'un actif ne rend rien ambigu.
r = S.lota_etat_du_code(
    [code("X", 10, 2)], [sub(used_sessions=2), sub(status="completed", used_sessions=9)], 0, AUJ)
verifier("5. un seul actif -> OK", r["etat"] == "OK" and r["restant"] == 8, r)

# ── 6. AMBIGU / consommation contradictoire — les essais deja pris ──────────
# AFR-S4QYXD : le code dit « intact » (used 0), l'abonnement dit « consomme ».
# S'en tenir a `used: 0` rendrait un cours d'essai GRATUIT une deuxieme fois.
r = S.lota_etat_du_code([code("AFR-S4QYXD", 1, 0)],
                        [sub(status="completed", used_sessions=1, remaining_sessions=0)], 0, AUJ)
verifier("6. essai deja pris -> AMBIGU", r["etat"] == "AMBIGU", r["etat"])
verifier("6. essai deja pris -> motif",
         r["motif"] == "consommation_contradictoire", r["motif"])
verifier("6. essai deja pris -> aucune seance rendue", r["restant"] is None, r["restant"])

# ── 7. AMBIGU / divergence bloquante — le cas AURELIEBOOST-26 ───────────────
# Le code promo dit « 1 restante », l'abonnement actif dit 0. La reservation,
# elle, lit `subscriptions` : afficher « 1 » ferait venir quelqu'un pour rien.
r = S.lota_etat_du_code([code("AURELIEBOOST-26", 9, 8, expiresAt="2026-09-01")],
                        [sub(used_sessions=9, remaining_sessions=0)], 0, AUJ)
verifier("7. divergence bloquante -> AMBIGU", r["etat"] == "AMBIGU", r["etat"])
verifier("7. divergence bloquante -> motif",
         r["motif"] == "divergence_bloquante", r["motif"])

# ── 8. L'ANTI-REPLI — `used_sessions` NE DEPLACE JAMAIS LE RESULTAT ─────────
# Le test central du lot. Meme code, trois `used_sessions` differents et un
# `remaining_sessions` qui ment : le resultat canonique ne bouge pas d'un pouce.
base = code("AmandaBoost-26", 9, 5, expiresAt="2026-10-05")
attendus = []
for u, rem in ((1, 8), (6, 3), (99, 7), (0, None)):
    r = S.lota_etat_du_code([base], [sub(used_sessions=u, remaining_sessions=rem)], 0, AUJ)
    attendus.append((r["etat"], r["total"], r["utilise"], r["restant"]))
verifier("8. anti-repli : resultat identique quel que soit used_sessions",
         len(set(attendus)) == 1, attendus)
verifier("8. anti-repli : la valeur est celle de discount_codes",
         attendus[0] == ("OK", 9, 5, 4), attendus[0])
# La garde « divergence bloquante » ne se declenche QUE sur un restant nul cote
# abonnement : elle ne doit pas devenir un refus general de la divergence, sinon
# la decision « discount_codes fait foi » ne s'appliquerait plus nulle part.
r = S.lota_etat_du_code([base], [sub(used_sessions=99, remaining_sessions=0)], 0, AUJ)
verifier("8. garde bloquante : seulement si l'abonnement est a zero",
         r["etat"] == "AMBIGU" and r["motif"] == "divergence_bloquante", r["motif"])
r = S.lota_etat_du_code([base], [sub(status="completed", remaining_sessions=0)], 0, AUJ)
verifier("8. garde bloquante : un abonnement CLOS ne bloque pas",
         r["etat"] == "OK" and r["restant"] == 4, r)

# ── 9. UN CODE PARTAGE N'EST PAS AMBIGU — le cas CLUBPMI ───────────────────
# Un document, un compteur (16/40), 7 porteurs. La lecture n'hesite pas : ce
# qui est partage, c'est la PROPRIETE des seances, pas leur nombre. Leur dire
# « plusieurs forfaits a ton nom » serait faux et casserait un ecran qui marche.
r = S.lota_etat_du_code([code("CLUBPMI", 40, 16, multi_member=True, expiresAt="2026-09-12")],
                        [sub(used_sessions=16, remaining_sessions=24)], 7, AUJ)
verifier("9. CLUBPMI -> OK", r["etat"] == "OK", r["etat"])
verifier("9. CLUBPMI -> restant 24", r["restant"] == 24, r["restant"])
verifier("9. CLUBPMI -> drapeau partage", r["partage"] is True, r["partage"])
verifier("9. CLUBPMI -> aucun message", r["message"] == "", r["message"])

# ── 10. LE DRAPEAU DE ROLLBACK ─────────────────────────────────────────────
os.environ["LOTA_DROITS_CANONIQUES"] = "false"
verifier("10. drapeau false -> lot eteint", S.lota_actif() is False, S.lota_actif())
os.environ["LOTA_DROITS_CANONIQUES"] = "true"
verifier("10. drapeau true -> lot actif", S.lota_actif() is True, S.lota_actif())
del os.environ["LOTA_DROITS_CANONIQUES"]
verifier("10. drapeau absent -> lot actif par defaut", S.lota_actif() is True, S.lota_actif())


# ── 11. LE BRANCHEMENT — requetes ciblees, regex echappee, zero ecriture ───
class FausseCollection:
    def __init__(self, docs, journal, nom):
        self.docs, self.journal, self.nom = docs, journal, nom

    def _filtrer(self, filtre):
        cond = (filtre or {}).get("code") or {}
        motif = cond.get("$regex", "")
        return [d for d in self.docs
                if re.search(motif, str(d.get("code") or ""), re.I)]

    def find(self, filtre, projection=None):
        self.journal.append((self.nom, "find", filtre))
        docs = self._filtrer(filtre)

        class _C:
            async def to_list(self_inner, n):
                return list(docs[:n])
        return _C()

    async def count_documents(self, filtre):
        self.journal.append((self.nom, "count", filtre))
        return len(self._filtrer(filtre))

    def __getattr__(self, nom):
        raise AssertionError("ecriture interdite dans le LOT A : %s" % nom)


class FausseBase:
    def __init__(self, codes, subs, membres):
        self.journal = []
        self.discount_codes = FausseCollection(codes, self.journal, "discount_codes")
        self.subscriptions = FausseCollection(subs, self.journal, "subscriptions")
        self.code_members = FausseCollection(membres, self.journal, "code_members")


db = FausseBase([code("AFR-53F288", 9, 8, expiresAt="2026-09-13")],
                [dict(sub(used_sessions=8, remaining_sessions=1), code="AFR-53F288")],
                [])
r = asyncio.get_event_loop().run_until_complete(S.lota_droits_du_code(db, "afr-53f288"))
verifier("11. lecture par code : OK", r["etat"] == "OK", r["etat"])
verifier("11. lecture par code : restant 1", r["restant"] == 1, r["restant"])
verifier("11. lecture par code : casse indifferente", r["code"] == "AFR-53F288", r["code"])
verifier("11. trois lectures seulement, aucune ecriture",
         len(db.journal) == 3, db.journal)

# Une entree hostile ne devient jamais une regex active.
db2 = FausseBase([code("AFR-53F288", 9, 8)], [], [])
r = asyncio.get_event_loop().run_until_complete(S.lota_droits_du_code(db2, "AFR-.*"))
verifier("11. regex echappee : aucun code capture",
         r["etat"] == "AUCUN_DROIT", r["etat"])
verifier("11. regex echappee : le motif est litteral",
         "\\.\\*" in db2.journal[0][2]["code"]["$regex"], db2.journal[0][2])

_ = asyncio.get_event_loop().run_until_complete(S.lota_droits_du_code(db2, ""))
verifier("11. code vide -> AUCUN_DROIT sans lecture", _["motif"] == "code_absent", _)


# ── 12. LECTURE PAR PERSONNE — la porte de R1, pas celle de l'ecran ────────
class BasePersonne(FausseBase):
    def __init__(self, codes, subs, membres):
        FausseBase.__init__(self, codes, subs, membres)
        for c in (self.discount_codes, self.subscriptions, self.code_members):
            c.find = _find_souple(c)


def _find_souple(collection):
    def find(filtre, projection=None):
        collection.journal.append((collection.nom, "find", filtre))
        docs = []
        for d in collection.docs:
            ok = True
            for cle, cond in (filtre or {}).items():
                v = d.get(cle)
                if isinstance(cond, dict) and "$regex" in cond:
                    ok = ok and re.search(cond["$regex"], str(v or ""), re.I) is not None
                else:
                    ok = ok and v == cond
            if ok:
                docs.append(d)

        class _C:
            def __aiter__(self_inner):
                async def gen():
                    for d in docs:
                        yield d
                return gen()

            async def to_list(self_inner, n):
                return list(docs[:n])
        return _C()
    return find


db3 = BasePersonne(
    [code("AFR-53F288", 9, 8, expiresAt="2026-09-13", assignedEmail="ry@x.ch"),
     code("BASSBOOSTX-14.", 9, 7, expiresAt="2026-09-16", assignedEmail="ry@x.ch")],
    [dict(sub(used_sessions=8, remaining_sessions=1), code="AFR-53F288", email="ry@x.ch"),
     dict(sub(used_sessions=7, remaining_sessions=2), code="BASSBOOSTX-14.", email="ry@x.ch")],
    [])
r = asyncio.get_event_loop().run_until_complete(S.lota_droits_membre(db3, email="RY@X.ch"))
verifier("12. deux codes utilisables -> AMBIGU", r["etat"] == "AMBIGU", r["etat"])
verifier("12. deux codes -> motif multi_codes", r["motif"] == "multi_codes", r["motif"])
verifier("12. deux codes -> aucun chiffre", r["restant"] is None, r["restant"])
verifier("12. deux codes -> ni somme (3) ni premier venu",
         r["restant"] not in (1, 2, 3), r["restant"])
verifier("12. deux codes -> les deux sont nommes pour le LOT C",
         sorted(r["codes_concurrents"]) == ["AFR-53F288", "BASSBOOSTX-14."],
         r["codes_concurrents"])

# La MEME personne, vue PAR SON CODE : la reponse redevient un chiffre juste.
r = asyncio.get_event_loop().run_until_complete(S.lota_droits_du_code(db3, "AFR-53F288"))
verifier("12. le meme porteur, par code -> OK 1",
         r["etat"] == "OK" and r["restant"] == 1, r)


# ═══════════════════════════ BILAN ═══════════════════════════════════════════
echecs = [x for x in RESULTATS if not x[1]]
print("\nLOT A — DROITS CANONIQUES (%d verifications)\n" % len(RESULTATS))
for nom, ok, detail in RESULTATS:
    print("  %s %-58s %s" % ("OK  " if ok else "ECHEC", nom, "" if ok else detail))
print("\n%d/%d au vert" % (len(RESULTATS) - len(echecs), len(RESULTATS)))
sys.exit(1 if echecs else 0)
