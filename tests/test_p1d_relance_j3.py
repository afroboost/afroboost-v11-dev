# -*- coding: utf-8 -*-
"""P1-d — LA DERNIERE RELANCE, TROIS JOURS APRES UN ESSAI NON CONVERTI.

CE QUE CE LOT PROMET, ET CE QUE CE BANC VERIFIE :
  * UN e-mail, trois jours apres une presence d'essai, a qui n'a rien achete ;
  * PLUS JAMAIS ensuite — un seul J+3, pas de J+7, pas de J+14 ;
  * jamais a quelqu'un qui a paye un COURS depuis son essai ;
  * un checkout abandonne ou une transaction echouee ne protegent de rien :
    seule une PREUVE DE PAIEMENT arrete la relance ;
  * la marchandise (t-shirt) n'est PAS une conversion de cours ;
  * jamais hors de la plage 09:00-20:00 heure SUISSE, ete comme hiver ;
  * jamais un ancien essai, quelle que soit l'ancienneté ;
  * une seule fois, quoi qu'il arrive — rejeu, deux passages, quatre workers ;
  * rien du tout tant que le drapeau est faux ;
  * rien de reel tant que l'envoi reel n'est pas explicitement arme ;
  * et SURTOUT : une presence validee le reste, quoi qu'il arrive a l'e-mail.

LES VRAIES FONCTIONS DU DEPOT, extraites de `api/server.py` par AST. Les seuls
elements remplaces sont le transport Resend (on ne veut aucun envoi reel) et
les deux regles deja prouvees ailleurs : ESSAI-6 (`test_essai6_identite.py`) et
l'etat de conversion LOT A / P1-c (`test_lota_conversion.py`,
`test_p1c_recommandation.py`). Tout ce qui DECIDE ici est le code reel.

AUCUN RESEAU, AUCUNE BASE REELLE, AUCUN E-MAIL.
    python3 tests/test_p1d_relance_j3.py
"""
import ast, asyncio, io, os, sys, types
from datetime import datetime, timezone, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


SERVEUR = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
ARBRE = ast.parse(SERVEUR)


# Le fichier fait 31 000 lignes : on l'indexe UNE fois. Sans ce cache, chaque
# scenario re-parcourait tout l'arbre et le banc mettait deux minutes.
_SRC_FN, _SRC_CST, _COMPILE = {}, {}, {}
for _n in ast.walk(ARBRE):
    if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef)):
        _SRC_FN.setdefault(_n.name, ast.get_source_segment(SERVEUR, _n))
for _n in ARBRE.body:
    if isinstance(_n, ast.Assign):
        for _c in _n.targets:
            if isinstance(_c, ast.Name):
                _SRC_CST.setdefault(_c.id, ast.get_source_segment(SERVEUR, _n))


def extraire(nom):
    if nom not in _SRC_FN:
        raise AssertionError("fonction introuvable : %s" % nom)
    return _SRC_FN[nom]


def constante(nom):
    if nom not in _SRC_CST:
        raise AssertionError("constante introuvable : %s" % nom)
    return _SRC_CST[nom]


def _code(nom, source):
    """Compilation mise en cache : meme code objet pour tous les scenarios."""
    if nom not in _COMPILE:
        _COMPILE[nom] = compile(source, "<p1d>", "exec")
    return _COMPILE[nom]


# Le couple de jetons de `shared.py` : les VRAIES fonctions, indexees UNE fois.
_SRC_SHARED = io.open(os.path.join(RACINE, "api", "routes", "shared.py"),
                      encoding="utf-8").read()
_ARBRE_SHARED = ast.parse(_SRC_SHARED)
_JETONS = {}
for _n in ast.walk(_ARBRE_SHARED):
    if isinstance(_n, ast.AsyncFunctionDef) and _n.name in (
            "_rc_reserver_jeton", "_rc_cloturer_jeton"):
        _JETONS[_n.name] = ast.get_source_segment(_SRC_SHARED, _n)

# R1 (25/08/2026) : la NATURE d'une offre — cours ou marchandise — n'est plus
# definie dans P1-d. Elle vit une seule fois dans `shared.py`, et
# `p1d_offre_est_un_cours` s'y ramene. On charge donc la VRAIE regle : ce banc
# doit voir celle qui tourne, pas une copie qui divergerait le jour ou elle
# changera.
_R1_SRC = {}
for _n in ast.walk(_ARBRE_SHARED):
    if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef)) and _n.name in (
            "essai2_nature_est_un_cours", "essai2_lire_offre",
            "essai2_offre_est_un_cours"):
        _R1_SRC[_n.name] = ast.get_source_segment(_SRC_SHARED, _n)
for _n in _ARBRE_SHARED.body:
    if isinstance(_n, ast.Assign) and any(
            isinstance(c, ast.Name) and c.id == "ESSAI2_CHAMP_PRODUIT" for c in _n.targets):
        _R1_SRC["ESSAI2_CHAMP_PRODUIT"] = ast.get_source_segment(_SRC_SHARED, _n)


# ───────────────────────── faux Mongo, minimal et fidele ────────────────────
def _valeur(doc, cle):
    val = doc
    for part in cle.split("."):
        val = (val or {}).get(part) if isinstance(val, dict) else None
    return val


def _match(doc, filtre):
    for cle, cond in (filtre or {}).items():
        val = _valeur(doc, cle)
        if isinstance(cond, dict):
            for op, ref in cond.items():
                if op == "$exists":
                    if (val is not None) != ref:
                        return False
                elif op == "$ne":
                    if val == ref:
                        return False
                elif op == "$gte":
                    if val is None or not (str(val) >= str(ref)):
                        return False
                elif op == "$lte":
                    if val is None or not (str(val) <= str(ref)):
                        return False
                else:
                    raise AssertionError("operateur non simule : %s" % op)
        elif val != cond:
            return False
    return True


class _Maj:
    def __init__(self, n): self.matched_count = n; self.modified_count = n


class _Curseur:
    def __init__(self, rows): self._rows = rows

    async def to_list(self, n=None):
        return [dict(r) for r in (self._rows if n is None else self._rows[:n])]


class _Coll:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    async def find_one(self, filtre=None, proj=None):
        for d in self.docs:
            if _match(d, filtre or {}):
                return dict(d)
        return None

    def find(self, filtre=None, proj=None):
        return _Curseur([d for d in self.docs if _match(d, filtre or {})])

    async def update_one(self, filtre, maj, upsert=False):
        for d in self.docs:
            if _match(d, filtre):
                for cle, val in (maj.get("$set") or {}).items():
                    cible, parts = d, cle.split(".")
                    for p in parts[:-1]:
                        cible = cible.setdefault(p, {})
                    cible[parts[-1]] = val
                return _Maj(1)
        return _Maj(0)


class _Base:
    def __init__(self, **cols):
        self._c = {n: _Coll(v) for n, v in cols.items()}

    def __getitem__(self, n): return self._c.setdefault(n, _Coll())

    def __getattr__(self, n):
        if n.startswith("_"):
            raise AttributeError(n)
        return self[n]


# ───────────────────────────── le banc ──────────────────────────────────────
ENVOIS = []          # ce qui serait REELLEMENT parti chez Resend
JOURNAL = []


class _Journal:
    def _n(self, m, *a):
        try:
            JOURNAL.append(str(m) % a if a else str(m))
        except Exception:
            JOURNAL.append(str(m))
    info = warning = error = debug = _n


# Le decor temporel du banc. La borne d'activation par defaut du depot vaut
# 2026-08-26 ; toutes les dates ci-dessous s'y rapportent explicitement.
BORNE = "2026-08-26T00:00:00+00:00"
# Presence validee le 1er septembre a 16:30 UTC (18:30 heure suisse).
PRESENCE = "2026-09-01T16:30:00+00:00"
# J+3 tombe le 4 septembre 16:30 UTC = 18:30 suisse -> DANS la fenetre.
J3_DANS = datetime(2026, 9, 4, 16, 30, tzinfo=timezone.utc)
# Meme jour a 21:00 UTC = 23:00 suisse -> HORS fenetre.
J3_HORS = datetime(2026, 9, 4, 21, 0, tzinfo=timezone.utc)
# J+11 : la fenetre haute est passee.
J3_TARD = datetime(2026, 9, 12, 16, 30, tzinfo=timezone.utc)


def construire(base, flags, essai=True, etat="open", resend_ok=True,
               resend_present=True, autorise_v286=True):
    """Charge les VRAIES fonctions P1-d avec un decor controle."""
    esp = {
        "__builtins__": __builtins__, "asyncio": asyncio, "os": os,
        "datetime": datetime, "timezone": timezone, "timedelta": timedelta,
        "logger": _Journal(), "db": base,
        "RESEND_AVAILABLE": resend_present,
        "RESEND_API_KEY": "cle" if resend_present else "",
        "RV2_REPLY_TO": "contact.artboost@gmail.com",
    }

    # Le transport, et LUI SEUL, est remplace : ce banc ne doit envoyer aucun
    # e-mail. Tout ce qui decide — les gardes, l'horloge, le contenu, le
    # jeton — est le code reel du depot.
    class _Resend:
        class Emails:
            @staticmethod
            def send(params):
                if not resend_ok:
                    raise RuntimeError("provider indisponible")
                ENVOIS.append(dict(params))
                return {"id": "faux"}
    esp["resend"] = _Resend

    async def _faux_flags():
        return dict(flags)
    esp["get_feature_flags"] = _faux_flags

    async def _couleur(coach_email=""):
        return "#D91CD2"
    esp["_v259_primary_color"] = _couleur

    async def _v286(email, role, notif_type):
        return autorise_v286
    esp["_v286_should_send_notification"] = _v286

    # `_conv_contexte` : on lui donne le forfait d'essai de la base du banc.
    async def _contexte(code):
        _c = str(code or "").strip().upper()
        _f = None
        for _d in base.subscriptions.docs:
            if str(_d.get("code") or "").upper() == _c:
                _f = dict(_d)
                break
        return _c, _f, ""
    esp["_conv_contexte"] = _contexte

    # Les VRAIES fonctions communes, extraites du depot.
    for fn in ("_v259_primary_rgb", "_email_wrapper", "rv2_email_valide",
               "p1b_lien_espace", "p1b_destinataire_autorise", "p1b_envoyer_email"):
        exec(_code(fn, extraire(fn)), esp)
    for c in ("P1B_PREFIXE", "P1B_TYPE_PREFERENCE", "P1B_DOMAINE",
              "P1D_CANAL", "P1D_PREFIXE", "P1D_TYPE_PREFERENCE", "P1D_DOMAINE",
              "P1D_DELAI_JOURS", "P1D_FENETRE_JOURS", "P1D_HEURE_DEBUT",
              "P1D_HEURE_FIN", "P1D_FUSEAU", "P1D_PERIODE_S", "P1D_LOT_MAX",
              "P1D_BORNE_DEFAUT", "_P1D_TZ"):
        exec(_code("cst:" + c, constante(c)), esp)
    for fn in ("p1d_fuseau", "p1d_parse_iso", "p1d_borne_activation",
               "p1d_dans_la_fenetre", "p1d_echeance", "p1d_contenu_relance",
               "p1d_offre_est_un_cours", "p1d_conversion_cours",
               "p1d_relance_j3", "p1d_candidats", "p1d_passage"):
        exec(_code(fn, extraire(fn)), esp)

    # ESSAI-6 et l'etat LOT A / P1-c : on les PILOTE pour dessiner les cas ;
    # leur logique propre est prouvee par leurs propres bancs.
    async def _est_essai(db_, forfait=None, code=""):
        return essai

    async def _conv_etat(db_, forfait, coach_id=""):
        return {"state": etat, "offers": []}

    faux_shared = types.ModuleType("api.routes.shared")
    faux_shared.est_un_essai = _est_essai
    faux_shared.conv_etat = _conv_etat
    faux_shared.CONV_OUVERTE = "open"
    faux_shared.CONV_TERMINEE = "purchased"
    faux_shared.CONV_INELIGIBLE = "not_eligible"

    # Le couple de jetons : les VRAIES fonctions du depot, extraites de shared.py.
    _esp_sh = {"logger": _Journal()}
    for _nom_j, _src_j in _JETONS.items():
        exec(_code("sh:" + _nom_j, _src_j), _esp_sh)
    # La regle de nature R1, la VRAIE, dans le meme espace.
    for _nom_r, _src_r in _R1_SRC.items():
        exec(_code("r1:" + _nom_r, _src_r), _esp_sh)
    faux_shared.essai2_offre_est_un_cours = _esp_sh["essai2_offre_est_un_cours"]
    faux_shared._rc_reserver_jeton = _esp_sh["_rc_reserver_jeton"]
    faux_shared._rc_cloturer_jeton = _esp_sh["_rc_cloturer_jeton"]
    for _nom in ("api", "api.routes"):
        sys.modules.setdefault(_nom, types.ModuleType(_nom))
    sys.modules["api.routes.shared"] = faux_shared
    return esp


ACTIF = {"P1_TRIAL_J3_ENABLED": True, "P1_TRIAL_J3_ENVOI_REEL": True}
SIMU = {"P1_TRIAL_J3_ENABLED": True, "P1_TRIAL_J3_ENVOI_REEL": False}
ETEINT = {"P1_TRIAL_J3_ENABLED": False, "P1_TRIAL_J3_ENVOI_REEL": True}

OFFRES = [
    {"id": "off-pulse", "name": "PULSE x10 cours", "isProduct": False},
    {"id": "off-unite", "name": "Cours a l'unite", "isProduct": False},
    {"id": "off-membres", "name": "Membres", "isProduct": False},
    {"id": "off-tshirt", "name": "T-shirt", "isProduct": True},
    {"id": "off-essai", "name": "Cours d'essai GRATUIT", "isProduct": False},
]


def resa(**kw):
    d = {"id": "r-1", "userEmail": "prospect@exemple.ch", "userName": "Ana Lopez",
         "userWhatsapp": "+41791112233", "courseName": "Silent Mercredi",
         "promoCode": "AFR-ESSAI1", "coach_id": "", "validated": True,
         "validatedAt": PRESENCE}
    d.update(kw)
    return d


def forfait_essai(**kw):
    d = {"id": "s-essai", "code": "AFR-ESSAI1", "email": "prospect@exemple.ch",
         "offer_id": "off-essai", "created_at": "2026-09-01T09:00:00+00:00",
         "montant_encaisse": 0.0, "origine_paiement": "offert"}
    d.update(kw)
    return d


def achat(offer_id, montant=250.0, quand="2026-09-02T10:00:00+00:00", **kw):
    d = {"id": "s-achat", "code": "AFR-ACHAT", "email": "prospect@exemple.ch",
         "offer_id": offer_id, "created_at": quand, "montant_encaisse": montant,
         "origine_paiement": "stripe"}
    d.update(kw)
    return d


def monde(reservations=None, subscriptions=None, subscribers=None,
          discount_codes=None, **kw):
    return _Base(
        reservations=reservations if reservations is not None else [resa(**kw)],
        subscriptions=subscriptions if subscriptions is not None else [forfait_essai()],
        subscribers=subscribers or [],
        notification_preferences=[],
        discount_codes=discount_codes or [],
        offers=OFFRES,
    )


async def scenarios():
    # ══ CAS A — essai consomme, J+3 atteint, aucun achat -> l'e-mail part ════
    ENVOIS.clear()
    b = monde()
    esp = construire(b, ACTIF)
    issue = await esp["p1d_relance_j3"](resa(), J3_DANS)
    verifier("A. J+3 sans achat -> relance envoyee", issue == "envoye", issue)
    verifier("A2. UN seul e-mail", len(ENVOIS) == 1, len(ENVOIS))
    verifier("A3. adresse = celle de la presence",
             ENVOIS and ENVOIS[0]["to"] == ["prospect@exemple.ch"])
    verifier("A4. trace posee sous confirmation.relance_j3",
             (b.reservations.docs[0].get("confirmation") or {})
             .get("relance_j3", {}).get("statut") == "envoye",
             b.reservations.docs[0].get("confirmation"))
    verifier("A5. la presence reste validee",
             b.reservations.docs[0].get("validated") is True)
    verifier("A6. le jeton J+0 n'est PAS touche",
             "relance_j0" not in (b.reservations.docs[0].get("confirmation") or {}))

    # ══ CAS B — achat PULSE 250 avant le J+3 -> aucun message ═══════════════
    ENVOIS.clear()
    b = monde(subscriptions=[forfait_essai(), achat("off-pulse", 250.0)])
    esp = construire(b, ACTIF)
    issue = await esp["p1d_relance_j3"](resa(), J3_DANS)
    verifier("B. achat PULSE 250 -> aucun J+3", issue == "deja_converti", issue)
    verifier("B2. aucun e-mail", not ENVOIS, len(ENVOIS))
    verifier("B3. aucun jeton brule",
             "confirmation" not in b.reservations.docs[0]
             or "relance_j3" not in (b.reservations.docs[0].get("confirmation") or {}))

    # ══ CAS C — cours a l'unite paye -> aucun message ═══════════════════════
    ENVOIS.clear()
    b = monde(subscriptions=[forfait_essai(), achat("off-unite", 30.0)])
    esp = construire(b, ACTIF)
    issue = await esp["p1d_relance_j3"](resa(), J3_DANS)
    verifier("C. cours a l'unite paye -> aucun J+3", issue == "deja_converti", issue)
    verifier("C2. aucun e-mail", not ENVOIS)

    # ══ CAS D — recharge membre 150 -> aucun message ════════════════════════
    ENVOIS.clear()
    b = monde(subscriptions=[forfait_essai(), achat("off-membres", 150.0)])
    esp = construire(b, ACTIF)
    issue = await esp["p1d_relance_j3"](resa(), J3_DANS)
    verifier("D. recharge membre 150 -> aucun J+3", issue == "deja_converti", issue)
    verifier("D2. aucun e-mail", not ENVOIS)

    # ══ CAS E — checkout ABANDONNE -> le J+3 part quand meme ════════════════
    # Une session de caisse ouverte n'est pas un paiement. Le forfait paye
    # n'existe pas ; seule une transaction `pending` traine.
    ENVOIS.clear()
    b = monde(subscriptions=[forfait_essai()])
    b["checkout_transactions"].docs.append({"id": "t-1", "status": "pending"})
    b["payment_transactions"].docs.append({"id": "p-1", "payment_status": "pending",
                                           "customer_email": "prospect@exemple.ch"})
    esp = construire(b, ACTIF)
    issue = await esp["p1d_relance_j3"](resa(), J3_DANS)
    verifier("E. checkout abandonne -> J+3 autorise", issue == "envoye", issue)
    verifier("E2. un e-mail parti", len(ENVOIS) == 1)

    # ══ CAS F — transaction ECHOUEE -> le J+3 part quand meme ═══════════════
    ENVOIS.clear()
    b = monde(subscriptions=[forfait_essai(),
                             achat("off-pulse", 0.0, code="AFR-ECHEC")])
    b["discount_codes"].docs.append({"code": "AFR-ECHEC", "total_paid": 0,
                                     "payment_method": "card"})
    esp = construire(b, ACTIF)
    issue = await esp["p1d_relance_j3"](resa(), J3_DANS)
    verifier("F. transaction echouee (0 encaisse) -> J+3 autorise",
             issue == "envoye", issue)
    verifier("F2. un e-mail parti", len(ENVOIS) == 1)

    # ══ CAS G — desinscription explicite -> aucun message ═══════════════════
    ENVOIS.clear()
    b = monde(subscribers=[{"channel": "email", "value": "prospect@exemple.ch",
                            "status": "opted_out"}])
    esp = construire(b, ACTIF)
    issue = await esp["p1d_relance_j3"](resa(), J3_DANS)
    verifier("G. opt-out -> aucun J+3", issue == "refuse", issue)
    verifier("G2. aucun e-mail", not ENVOIS)

    # G3 — preference V286 `trial_followup` contraire
    ENVOIS.clear()
    b = monde()
    esp = construire(b, ACTIF, autorise_v286=False)
    issue = await esp["p1d_relance_j3"](resa(), J3_DANS)
    verifier("G3. preference trial_followup a false -> aucun J+3",
             issue == "refuse", issue)
    verifier("G4. aucun e-mail", not ENVOIS)

    # ══ CAS H — deja envoye -> aucun doublon, et plus jamais candidat ═══════
    ENVOIS.clear()
    b = monde()
    esp = construire(b, ACTIF)
    i1 = await esp["p1d_relance_j3"](resa(), J3_DANS)
    i2 = await esp["p1d_relance_j3"](dict(b.reservations.docs[0]), J3_DANS)
    verifier("H. premier appel -> envoye", i1 == "envoye", i1)
    verifier("H2. second appel -> deja_traitee", i2 == "deja_traitee", i2)
    verifier("H3. toujours UN seul e-mail", len(ENVOIS) == 1, len(ENVOIS))
    cands = await esp["p1d_candidats"](J3_DANS)
    verifier("H4. sort de la liste des candidats", cands == [], cands)

    # ══ CAS I — CONCURRENCE : quatre passages simultanes, un seul envoi ═════
    ENVOIS.clear()
    b = monde()
    esp = construire(b, ACTIF)
    issues = await asyncio.gather(*[esp["p1d_relance_j3"](resa(), J3_DANS)
                                    for _ in range(4)])
    verifier("I. 4 appels simultanes -> 1 seul e-mail", len(ENVOIS) == 1,
             "%s / envois=%d" % (issues, len(ENVOIS)))
    verifier("I2. exactement un 'envoye'",
             sum(1 for i in issues if i == "envoye") == 1, issues)
    verifier("I3. les autres sont 'deja_traitee'",
             sum(1 for i in issues if i == "deja_traitee") == 3, issues)

    # ══ CAS J — essai HISTORIQUE anterieur a la borne -> jamais rattrape ════
    ENVOIS.clear()
    vieille = resa(id="r-vieux", validatedAt="2026-04-12T16:30:00+00:00")
    b = monde(reservations=[vieille])
    esp = construire(b, ACTIF)
    issue = await esp["p1d_relance_j3"](vieille, J3_DANS)
    verifier("J. presence anterieure a la borne -> hors_borne",
             issue == "hors_borne", issue)
    verifier("J2. aucun e-mail", not ENVOIS)
    cands = await esp["p1d_candidats"](J3_DANS)
    verifier("J3. pas meme CHARGEE comme candidate", cands == [], cands)

    # J4 — la fenetre haute : passe J+10, plus jamais
    ENVOIS.clear()
    b = monde()
    esp = construire(b, ACTIF)
    issue = await esp["p1d_relance_j3"](resa(), J3_TARD)
    verifier("J4. J+11 -> trop_tard, le tunnel est clos", issue == "trop_tard", issue)
    verifier("J5. aucun e-mail", not ENVOIS)

    # J6 — avant l'echeance : rien ne part
    b = monde()
    esp = construire(b, ACTIF)
    issue = await esp["p1d_relance_j3"](resa(), J3_DANS - timedelta(days=2))
    verifier("J6. J+1 -> pas_encore", issue == "pas_encore", issue)

    # ══ CAS K — hors plage 09:00-20:00 suisse -> REPORT, pas abandon ════════
    ENVOIS.clear()
    b = monde()
    esp = construire(b, ACTIF)
    issue = await esp["p1d_relance_j3"](resa(), J3_HORS)
    verifier("K. 23:00 suisse -> hors_fenetre", issue == "hors_fenetre", issue)
    verifier("K2. aucun e-mail", not ENVOIS)
    verifier("K3. aucun jeton brule -> il repassera",
             "relance_j3" not in (b.reservations.docs[0].get("confirmation") or {}))
    # ... et au passage suivant, dans la fenetre, il part
    issue = await esp["p1d_relance_j3"](resa(), J3_DANS + timedelta(days=1))
    verifier("K4. passage suivant dans la fenetre -> envoye", issue == "envoye", issue)
    verifier("K5. l'e-mail reporte est bien parti", len(ENVOIS) == 1)

    # ══ CAS L — HEURE D'ETE / HEURE D'HIVER, via pytz ═══════════════════════
    b = monde()
    esp = construire(b, ACTIF)
    _f = esp["p1d_dans_la_fenetre"]
    # 1er juillet, 07:30 UTC = 09:30 CEST (UTC+2) -> DANS la fenetre
    verifier("L. ete : 07:30 UTC = 09:30 suisse -> dans la fenetre",
             _f(datetime(2026, 7, 1, 7, 30, tzinfo=timezone.utc)) is True)
    # 15 janvier, 07:30 UTC = 08:30 CET (UTC+1) -> HORS fenetre
    verifier("L2. hiver : 07:30 UTC = 08:30 suisse -> hors fenetre",
             _f(datetime(2026, 1, 15, 7, 30, tzinfo=timezone.utc)) is False)
    # 15 janvier, 08:30 UTC = 09:30 CET -> DANS la fenetre
    verifier("L3. hiver : 08:30 UTC = 09:30 suisse -> dans la fenetre",
             _f(datetime(2026, 1, 15, 8, 30, tzinfo=timezone.utc)) is True)
    # 1er juillet, 18:30 UTC = 20:30 CEST -> HORS (borne haute)
    verifier("L4. ete : 18:30 UTC = 20:30 suisse -> hors fenetre",
             _f(datetime(2026, 7, 1, 18, 30, tzinfo=timezone.utc)) is False)
    # 1er juillet, 17:30 UTC = 19:30 CEST -> DANS
    verifier("L5. ete : 17:30 UTC = 19:30 suisse -> dans la fenetre",
             _f(datetime(2026, 7, 1, 17, 30, tzinfo=timezone.utc)) is True)
    verifier("L6. aucun offset UTC ecrit en dur dans le lot",
             "timedelta(hours=2)" not in extraire("p1d_dans_la_fenetre"))

    # ══ CAS M — PRODUIT PHYSIQUE : ce n'est PAS une conversion de cours ═════
    b = monde(subscriptions=[forfait_essai(), achat("off-tshirt", 59.99)])
    esp = construire(b, ACTIF)
    _conv = await esp["p1d_conversion_cours"](forfait_essai())
    verifier("M. t-shirt paye -> PAS une conversion de cours", _conv is False, _conv)
    _cours = await esp["p1d_offre_est_un_cours"]("off-tshirt")
    verifier("M2. l'offre t-shirt est reconnue comme marchandise",
             _cours is False, _cours)
    _cours = await esp["p1d_offre_est_un_cours"]("off-pulse")
    verifier("M3. l'offre PULSE est reconnue comme cours", _cours is True, _cours)
    _cours = await esp["p1d_offre_est_un_cours"]("off-inconnue")
    verifier("M4. offre introuvable -> indetermine, jamais 'marchandise'",
             _cours is None, _cours)
    # M5 — DETTE CONSIGNEE : ESSAI-2 pose `converted_at` sur un achat de
    # marchandise, ce qui FERME l'ecran P1-c en amont. P1-d ne peut alors pas
    # promettre « voir mes options » : il se tait. Le test dit l'etat REEL.
    ENVOIS.clear()
    esp = construire(b, ACTIF, etat="purchased")
    issue = await esp["p1d_relance_j3"](resa(), J3_DANS)
    verifier("M5. ecran P1-c ferme par ESSAI-2 -> aucun message (dette connue)",
             issue == "deja_converti", issue)
    verifier("M6. aucun e-mail", not ENVOIS)

    # ══ CAS N — LE CONTENU NE FIGE NI PRIX NI OFFRE ═════════════════════════
    b = monde()
    esp = construire(b, ACTIF)
    sujet, html, texte = esp["p1d_contenu_relance"](
        "Ana", "https://afroboost.com/espace/AFR-ESSAI1", "#D91CD2")
    for _nom, _t in (("sujet", sujet), ("html", html), ("texte", texte)):
        verifier("N. aucun prix dans le %s" % _nom,
                 not any(x in _t for x in ("250", "150", "30 CHF", "CHF")), _t[:80])
        verifier("N2. aucune offre nommee dans le %s" % _nom,
                 not any(x in _t for x in ("PULSE", "Membres", "Cours à l'unité")),
                 _t[:80])
    verifier("N3. le CTA pointe vers l'espace du participant",
             "https://afroboost.com/espace/AFR-ESSAI1" in html
             and "https://afroboost.com/espace/AFR-ESSAI1" in texte)
    verifier("N4. le sujet ne COMMENCE pas par un emoji",
             sujet[0].isalpha(), sujet[:12])
    verifier("N5. aucune fausse promesse « reponds STOP »",
             "STOP" not in html and "STOP" not in texte)
    verifier("N6. aucun compte a rebours / urgence",
             not any(x in html.lower() for x in ("plus que", "derniers", "expire",
                                                 "dépêche", "compte à rebours")))
    verifier("N7. HTML et texte portent le meme CTA",
             "Voir mes options" in html and "Voir mes options" in texte)
    verifier("N8. il ne repete pas le J+0",
             "Bravo pour ton premier cours" not in html)
    # N9 — l'e-mail reellement construit par la relance porte bien ce contenu
    ENVOIS.clear()
    esp = construire(monde(), ACTIF)
    await esp["p1d_relance_j3"](resa(), J3_DANS)
    verifier("N9. l'e-mail envoye porte le sujet valide",
             ENVOIS and ENVOIS[0]["subject"] == "Envie de continuer l'expérience Afroboost ? 🔥",
             ENVOIS[0]["subject"] if ENVOIS else "(aucun)")
    verifier("N10. l'e-mail porte une version texte", ENVOIS and ENVOIS[0].get("text"))

    # ══ DORMANCE — drapeau faux : rien, pas meme une lecture ════════════════
    ENVOIS.clear()
    b = monde()
    esp = construire(b, ETEINT)
    issue = await esp["p1d_relance_j3"](resa(), J3_DANS)
    verifier("DORMANT. drapeau faux -> desactive", issue == "desactive", issue)
    verifier("DORMANT2. aucun e-mail", not ENVOIS)
    resume = await esp["p1d_passage"](J3_DANS)
    verifier("DORMANT3. le passage ressort sans rien lire",
             resume == {"desactive": 1}, resume)
    verifier("DORMANT4. aucun jeton pose",
             "confirmation" not in b.reservations.docs[0])

    # ══ SIMULATION — tout est pret, personne n'est contacte ═════════════════
    ENVOIS.clear()
    b = monde()
    esp = construire(b, SIMU)
    issue = await esp["p1d_relance_j3"](resa(), J3_DANS)
    verifier("SIMU. envoi reel desarme -> simulation", issue == "simulation", issue)
    verifier("SIMU2. aucun e-mail", not ENVOIS)
    verifier("SIMU3. AUCUN jeton pose — le droit d'envoyer reste entier",
             "relance_j3" not in (b.reservations.docs[0].get("confirmation") or {}))
    verifier("SIMU4. le journal montre ce qui serait parti",
             any("SIMULATION" in l and "prospect@exemple.ch" in l for l in JOURNAL))

    # ══ PANNE PROVIDER — echec trace, presence intacte, aucun doublon ═══════
    ENVOIS.clear()
    b = monde()
    esp = construire(b, ACTIF, resend_ok=False)
    issue = await esp["p1d_relance_j3"](resa(), J3_DANS)
    verifier("PANNE. Resend refuse -> echec", issue == "echec", issue)
    verifier("PANNE2. trace 'echec' posee",
             (b.reservations.docs[0].get("confirmation") or {})
             .get("relance_j3", {}).get("statut") == "echec")
    verifier("PANNE3. la presence reste validee",
             b.reservations.docs[0].get("validated") is True)
    i2 = await esp["p1d_relance_j3"](dict(b.reservations.docs[0]), J3_DANS)
    verifier("PANNE4. aucun doublon au passage suivant", i2 == "deja_traitee", i2)

    # Resend absent : aucune exception, aucun envoi
    ENVOIS.clear()
    b = monde()
    esp = construire(b, ACTIF, resend_present=False)
    issue = await esp["p1d_relance_j3"](resa(), J3_DANS)
    verifier("PANNE5. Resend non configure -> echec, jamais d'exception",
             issue == "echec", issue)

    # ══ PRESENCE PAYANTE — un client n'est pas un prospect ══════════════════
    ENVOIS.clear()
    b = monde()
    esp = construire(b, ACTIF, essai=False)
    issue = await esp["p1d_relance_j3"](resa(), J3_DANS)
    verifier("PAYANT. presence payante -> pas_un_essai", issue == "pas_un_essai", issue)
    verifier("PAYANT2. aucun e-mail", not ENVOIS)

    # ══ ECRAN FERME — P1-c ne proposerait rien -> on ne promet rien ═════════
    ENVOIS.clear()
    b = monde()
    esp = construire(b, ACTIF, etat="not_eligible")
    issue = await esp["p1d_relance_j3"](resa(), J3_DANS)
    verifier("ECRAN. P1-c non eligible -> ecran_ferme, aucun message",
             issue == "ecran_ferme", issue)
    verifier("ECRAN2. aucun e-mail", not ENVOIS)

    # ══ SANS ADRESSE — on ne peut ecrire a personne, rien ne casse ══════════
    ENVOIS.clear()
    b = monde(reservations=[resa(userEmail="")])
    esp = construire(b, ACTIF)
    issue = await esp["p1d_relance_j3"](resa(userEmail=""), J3_DANS)
    verifier("ADRESSE. sans e-mail -> sans_email", issue == "sans_email", issue)
    issue = await esp["p1d_relance_j3"](resa(userEmail="pas-une-adresse"), J3_DANS)
    verifier("ADRESSE2. adresse invalide -> sans_email", issue == "sans_email", issue)

    # ══ CONVERSION INDETERMINEE — on n'ecrit a personne ════════════════════
    ENVOIS.clear()
    b = monde(subscriptions=[forfait_essai(), achat("off-disparue", 250.0)])
    esp = construire(b, ACTIF)
    issue = await esp["p1d_relance_j3"](resa(), J3_DANS)
    verifier("INDET. offre achetee illisible -> aucun message",
             issue == "conversion_indeterminee", issue)
    verifier("INDET2. aucun e-mail", not ENVOIS)

    # ══ ACHAT ANTERIEUR A L'ESSAI — hors sujet, ne bloque pas ══════════════
    b = monde(subscriptions=[forfait_essai(),
                             achat("off-pulse", 250.0, quand="2026-05-01T10:00:00+00:00")])
    esp = construire(b, ACTIF)
    _conv = await esp["p1d_conversion_cours"](forfait_essai())
    verifier("ANTERIEUR. achat anterieur a l'essai -> pas une conversion",
             _conv is False, _conv)

    # ══ BORNE — illisible = borne INFINIE, jamais « aucune borne » ═════════
    b = monde()
    esp = construire(b, ACTIF)
    os.environ["P1D_BORNE_ACTIVATION"] = "n'importe quoi"
    try:
        _b = esp["p1d_borne_activation"]()
        verifier("BORNE. borne illisible -> borne lointaine (aucun candidat)",
                 _b.year >= 2999, _b)
        issue = await esp["p1d_relance_j3"](resa(), J3_DANS)
        verifier("BORNE2. et donc aucun message", issue == "hors_borne", issue)
    finally:
        os.environ.pop("P1D_BORNE_ACTIVATION", None)
    verifier("BORNE3. la borne par defaut du depot est bien posee",
             esp["p1d_borne_activation"]().isoformat().startswith("2026-08-26"),
             esp["p1d_borne_activation"]())

    # ══ PASSAGE COMPLET — le decompte par issue ════════════════════════════
    ENVOIS.clear()
    b = monde(reservations=[
        resa(id="r-a"),
        resa(id="r-vieux", validatedAt="2026-04-12T16:30:00+00:00"),
        resa(id="r-fait", confirmation={"relance_j3": {"statut": "envoye"}}),
    ])
    esp = construire(b, ACTIF)
    resume = await esp["p1d_passage"](J3_DANS)
    verifier("PASSAGE. un seul envoi sur trois presences",
             resume.get("envoye") == 1 and len(ENVOIS) == 1, "%s / %d" % (resume, len(ENVOIS)))
    verifier("PASSAGE2. l'ancienne et la deja-traitee ne sont meme pas chargees",
             sum(resume.values()) == 1, resume)


def main():
    asyncio.run(scenarios())
    ok = sum(1 for _, c, _ in RESULTATS if c)
    for nom, cond, detail in RESULTATS:
        print(("  OK   " if cond else "  ECHEC") + "  " + nom
              + ("" if cond else "   -> %s" % (detail,)))
    print("\n=== P1-d : %d/%d ===" % (ok, len(RESULTATS)))
    sys.exit(0 if ok == len(RESULTATS) else 1)


if __name__ == "__main__":
    main()
