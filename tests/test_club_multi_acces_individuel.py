# -*- coding: utf-8 -*-
"""CLUB MULTI — CHAQUE PARTICIPANT ENTRE CHEZ LUI, PAS CHEZ LE TITULAIRE.

LE BUG FERME, constate sur `CLUBPMI` le 14/09/2026 (7 membres, 20/40 seances).
Un code de club porte UN titulaire (`discount_codes.assignedEmail`) et N
participants (`code_members`, chacun avec son `slug`). Sans `?m=slug` dans
l'URL, `_b3s1_contact_enregistre` retombait sur `assignedEmail` :

  * le participant qui saisissait SA propre adresse ne recevait aucun OTP,
    parce que son adresse n'est pas celle du titulaire ;
  * l'ecran qui revele les liens personnels `?m=slug` est LUI-MEME derriere
    cette porte.

Obtenir son lien personnel exigeait donc de deja l'avoir. Tout convergeait vers
la boite du titulaire.

CE QUI NE DOIT PAS BOUGER : une adresse inconnue n'ouvre toujours RIEN, et le
titulaire garde exactement son chemin d'avant. L'identite se lit en base, jamais
dans la requete.

AUCUNE BASE REELLE, AUCUN RESEAU, AUCUN E-MAIL, AUCUNE DONNEE PERSONNELLE.
    python3 tests/test_club_multi_acces_individuel.py
"""
import ast, asyncio, io, os, re, sys, types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
ARBRE = ast.parse(SRC)
LIGNES = SRC.splitlines(True)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


CODE = "CLUBSYNTH"
TITULAIRE = "titulaire@exemple.invalid"
MEMBRE = "participant@exemple.invalid"
INCONNU = "personne@exemple.invalid"
SLUG_MEMBRE = "slug-participant"
COACH = "coach-synthetique"


# ═════════════════════════ faux Mongo minimal ════════════════════════════════
def _corr(doc, filtre):
    """Egalite stricte, plus le seul `$regex` que la production utilise ici."""
    for cle, cond in (filtre or {}).items():
        v = doc.get(cle)
        if isinstance(cond, dict) and "$regex" in cond:
            if not re.match(cond["$regex"], str(v or ""), re.I):
                return False
        elif v != cond:
            return False
    return True


class Coll:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.filtres = []

    async def find_one(self, filtre, projection=None):
        self.filtres.append(dict(filtre or {}))
        for d in self.docs:
            if _corr(d, filtre):
                return dict(d)
        return None


class Base:
    def __init__(self):
        self.discount_codes = Coll([
            {"code": CODE, "assignedEmail": TITULAIRE, "coach_id": COACH,
             "multi_member": True, "maxUses": 40, "used": 20},
        ])
        self.code_members = Coll([
            {"code": CODE, "slug": "slug-titulaire", "email": TITULAIRE, "name": "Titulaire"},
            {"code": CODE, "slug": SLUG_MEMBRE, "email": MEMBRE, "name": "Participante"},
        ])
        self.subscriptions = Coll([])


# ═══════════ la FONCTION DE PRODUCTION, extraite telle quelle ════════════════
def _source(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return "".join(LIGNES[n.lineno - 1:n.end_lineno])
    raise AssertionError("fonction introuvable : " + nom)


BASE = Base()
_env = {"re": re, "db": BASE, "DEFAULT_COACH_ID": "bassi_default"}
exec(compile(_source("_b3s1_contact_enregistre"), "<prod>", "exec"), _env)
contact = _env["_b3s1_contact_enregistre"]


def appel(**kw):
    return asyncio.get_event_loop().run_until_complete(contact(**kw))


# ═══════════════════════════════ les bancs ═══════════════════════════════════
# 1. LE BUG : le participant saisit SON adresse, sans lien personnel.
_em, _coach, _slug = appel(code_upper=CODE, slug="", email_demande=MEMBRE)
verifier("participant reconnu par sa propre adresse", _em == MEMBRE,
         "rendu=%r (avant le correctif : l'adresse du titulaire)" % (_em,))
verifier("le jeton sera lie a SON espace", _slug == SLUG_MEMBRE, "slug=%r" % (_slug,))

# 2. Le titulaire n'a rien perdu.
_em2, _c2, _s2 = appel(code_upper=CODE, slug="", email_demande=TITULAIRE)
verifier("le titulaire garde son chemin", _em2 == TITULAIRE, "rendu=%r" % (_em2,))
verifier("le titulaire n'est pas capture par un slug de membre", _s2 == "",
         "slug=%r" % (_s2,))

# 3. Une adresse inconnue n'ouvre RIEN de plus qu'avant : on retombe sur
#    l'adresse enregistree, que l'appelant comparera — et la comparaison echoue.
_em3, _c3, _s3 = appel(code_upper=CODE, slug="", email_demande=INCONNU)
verifier("adresse inconnue : aucun membre reconnu", _s3 == "", "slug=%r" % (_s3,))
verifier("adresse inconnue : l'OTP ne peut pas lui etre adresse",
         _em3 != INCONNU, "rendu=%r" % (_em3,))

# 4. Le lien personnel (?m=slug) continue de primer, inchange.
_em4, _c4, _s4 = appel(code_upper=CODE, slug=SLUG_MEMBRE, email_demande="")
verifier("le lien personnel reste souverain", (_em4, _s4) == (MEMBRE, SLUG_MEMBRE),
         "rendu=%r slug=%r" % (_em4, _s4))
_em5, _c5, _s5 = appel(code_upper=CODE, slug="slug-inexistant", email_demande=MEMBRE)
verifier("un slug inconnu refuse, il ne se rabat pas sur l'adresse",
         _em5 is None, "rendu=%r" % (_em5,))

# 5. Un code SIMPLE (non multi) n'est pas touche : pas de recherche de membre.
BASE.discount_codes.docs[0]["multi_member"] = False
BASE.code_members.filtres.clear()
_em6, _c6, _s6 = appel(code_upper=CODE, slug="", email_demande=MEMBRE)
verifier("code simple : comportement d'avant, inchange",
         (_em6, _s6) == (TITULAIRE, ""), "rendu=%r slug=%r" % (_em6, _s6))
verifier("code simple : la table des membres n'est meme pas lue",
         not BASE.code_members.filtres, "filtres=%r" % (BASE.code_members.filtres,))
BASE.discount_codes.docs[0]["multi_member"] = True

# 6. AUCUNE saisie utilisateur n'entre dans une regex Mongo.
BASE.code_members.filtres.clear()
appel(code_upper=CODE, slug="", email_demande="a+b(c)[d]@exemple.invalid")
_filtres_membres = [f for f in BASE.code_members.filtres if "email" in f]
verifier("l'adresse saisie est comparee par EGALITE, jamais par regex",
         all(not isinstance(f.get("email"), dict) for f in _filtres_membres),
         "filtres=%r" % (_filtres_membres,))

# 7. Le chemin cote route : le slug reconnu voyage jusqu'au jeton ET au client.
_req = _source("b3s1_demander_otp")
_ver = _source("b3s1_verifier_otp")
verifier("la demande memorise le membre reconnu",
         '"membre_slug": _slug_resolu if _correspond else ""' in _req)
verifier("la verification lie le jeton a ce membre",
         'slug = str(_doc.get("membre_slug") or "").strip() or slug' in _ver)
verifier("le client apprend quel espace ouvrir",
         '"member_slug": slug or None' in _ver)

# ════════════════════════════════ rapport ════════════════════════════════════
_ko = [r for r in RESULTATS if not r[1]]
for nom, ok, detail in RESULTATS:
    print(("  OK   " if ok else "  ECHEC") + " " + nom + ("" if ok else "  <- " + detail))
print("\n%d/%d" % (len(RESULTATS) - len(_ko), len(RESULTATS)))
sys.exit(1 if _ko else 0)
