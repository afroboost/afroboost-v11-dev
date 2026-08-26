# -*- coding: utf-8 -*-
"""P1-b — LA RELANCE J+0, APRES UN ESSAI REELLEMENT CONSOMME.

CE QUE CE LOT PROMET, ET CE QUE CE BANC VERIFIE :
  * UN e-mail, le jour meme, a quelqu'un qui est VENU ;
  * jamais a un absent, jamais a un client payant ;
  * une seule fois, quoi qu'il arrive — rejeu, re-scan, double appel ;
  * rien du tout tant que le drapeau est faux ;
  * rien de reel tant que l'envoi reel n'est pas explicitement arme ;
  * et SURTOUT : une presence validee le reste, quoi qu'il arrive a l'e-mail.

LES VRAIES FONCTIONS DU DEPOT, extraites de `api/server.py` par AST. Le seul
element remplace est le transport Resend — on ne veut pas d'un envoi reel, et
c'est justement ce que ce banc doit prouver.

AUCUN RESEAU, AUCUNE BASE REELLE, AUCUN E-MAIL.
    python3 tests/test_p1b_relance_j0.py
"""
import ast, asyncio, io, logging, os, sys, types
from datetime import datetime, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


SERVEUR = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
ARBRE = ast.parse(SERVEUR)


def extraire(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return ast.get_source_segment(SERVEUR, n)
    raise AssertionError("fonction introuvable : %s" % nom)


def constante(nom):
    for n in ARBRE.body:
        if isinstance(n, ast.Assign) and any(
                isinstance(c, ast.Name) and c.id == nom for c in n.targets):
            return ast.get_source_segment(SERVEUR, n)
    raise AssertionError("constante introuvable : %s" % nom)


# ───────────────────────── faux Mongo, minimal et fidele ────────────────────
def _match(doc, filtre):
    for cle, cond in (filtre or {}).items():
        val = doc
        for part in cle.split("."):
            val = (val or {}).get(part) if isinstance(val, dict) else None
        if isinstance(cond, dict):
            for op, ref in cond.items():
                if op == "$exists":
                    if (val is not None) != ref:
                        return False
                elif op == "$ne":
                    if val == ref:
                        return False
                elif op == "$in":
                    if val not in (ref or []):
                        return False
                else:
                    raise AssertionError("operateur non simule : %s" % op)
        elif val != cond:
            return False
    return True


class _Maj:
    def __init__(self, n): self.matched_count = n; self.modified_count = n


class _Curseur:
    """Curseur asynchrone minimal — `async for d in coll.find(...)`.

    C3 : la garde d'opt-out lit `subscribers` par une requete GROUPEE, la meme
    pour un destinataire que pour deux cents. Sans ce curseur, le harnais
    renverrait vide et validerait a l'aveugle une garde qui ne garde rien.
    """

    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        self._i = 0
        return self

    async def __anext__(self):
        if self._i >= len(self._docs):
            raise StopAsyncIteration
        self._i += 1
        return dict(self._docs[self._i - 1])

    async def to_list(self, n=None):
        return [dict(d) for d in (self._docs if n is None else self._docs[:n])]


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
                    cible = d
                    parts = cle.split(".")
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


def construire(base, flags, essai=True, consomme=True, resend_ok=True,
               resend_present=True, autorise_v286=True):
    """Charge les vraies fonctions P1-b avec un decor controle."""
    esp = {
        "__builtins__": __builtins__, "asyncio": asyncio, "datetime": datetime,
        "timezone": timezone, "logger": _Journal(), "db": base,
        "RESEND_AVAILABLE": resend_present, "RESEND_API_KEY": "cle" if resend_present else "",
        "RV2_REPLY_TO": "contact.artboost@gmail.com",
    }

    # Le transport, et LUI SEUL, est remplace : ce banc ne doit envoyer aucun
    # e-mail. Tout ce qui decide — les gardes, le contenu, le jeton — est le
    # code reel.
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

    # `_email_wrapper`, `_v259_primary_rgb` et `rv2_email_valide` : les VRAIES.
    # C3 : `p1b_destinataire_autorise` ne recopie plus la lecture du refus, il
    # appelle la regle PARTAGEE avec les campagnes. On extrait donc aussi ses
    # dependances — sinon le harnais testerait une fonction amputee.
    for fn in ("_v259_primary_rgb", "_email_wrapper", "rv2_email_valide",
               "format_phone_e164", "_v332_normaliser",
               "c3_refus_exprimes", "c3_refus_exprime"):
        exec(compile(extraire(fn), "<srv>", "exec"), esp)
    for c in ("P1B_CANAL", "P1B_PREFIXE", "P1B_TYPE_PREFERENCE", "P1B_DOMAINE"):
        exec(compile(constante(c), "<cst>", "exec"), esp)
    for fn in ("p1b_lien_espace", "p1b_contenu_relance", "p1b_destinataire_autorise",
               "p1b_envoyer_email", "p1b_relance_j0", "p1b_apres_presence"):
        exec(compile(extraire(fn), "<p1b>", "exec"), esp)

    # ESSAI-6 : la nature de l'essai et sa consommation. On les pilote pour
    # dessiner les cas ; leur logique propre est prouvee par
    # `tests/test_essai6_identite.py`, sur un vrai mongod.
    async def _est_essai(db_, forfait=None, code=""):
        return essai

    async def _consomme(db_, email="", telephone="", coach_id=None):
        return {"id": "r-1"} if consomme else None

    faux_shared = types.ModuleType("api.routes.shared")
    faux_shared.est_un_essai = _est_essai
    faux_shared.essai6_consomme = _consomme

    # Le couple de jetons : les VRAIES fonctions du depot, extraites de shared.py.
    _src_shared = io.open(os.path.join(RACINE, "api", "routes", "shared.py"),
                          encoding="utf-8").read()
    _arbre_shared = ast.parse(_src_shared)
    _esp_sh = {"logger": _Journal()}
    for _n in ast.walk(_arbre_shared):
        if isinstance(_n, ast.AsyncFunctionDef) and _n.name in (
                "_rc_reserver_jeton", "_rc_cloturer_jeton"):
            exec(compile(ast.get_source_segment(_src_shared, _n), "<sh>", "exec"), _esp_sh)
    faux_shared._rc_reserver_jeton = _esp_sh["_rc_reserver_jeton"]
    faux_shared._rc_cloturer_jeton = _esp_sh["_rc_cloturer_jeton"]
    for _nom in ("api", "api.routes"):
        sys.modules.setdefault(_nom, types.ModuleType(_nom))
    sys.modules["api.routes.shared"] = faux_shared
    return esp


ACTIF = {"P1_TRIAL_J0_ENABLED": True, "P1_TRIAL_J0_ENVOI_REEL": True}
SIMU = {"P1_TRIAL_J0_ENABLED": True, "P1_TRIAL_J0_ENVOI_REEL": False}
ETEINT = {"P1_TRIAL_J0_ENABLED": False, "P1_TRIAL_J0_ENVOI_REEL": True}


def resa(**kw):
    d = {"id": "r-1", "userEmail": "prospect@exemple.ch", "userName": "Ana Lopez",
         "userWhatsapp": "+41791112233", "courseName": "Silent Mercredi",
         "promoCode": "AFR-ESSAI1", "coach_id": "", "validated": True}
    d.update(kw)
    return d


def monde(**kw):
    return _Base(reservations=[resa(**kw)], subscribers=[], notification_preferences=[])


async def scenarios():
    # ══ CAS A — essai consomme -> candidat, et l'e-mail part ════════════════
    ENVOIS.clear()
    b = monde()
    esp = construire(b, ACTIF)
    issue = await esp["p1b_relance_j0"](resa())
    verifier("CAS A. essai consomme -> relance envoyee", issue == "envoye", issue)
    verifier("CAS A2. UN seul e-mail", len(ENVOIS) == 1, len(ENVOIS))
    verifier("CAS A3. adresse = celle de la presence",
             ENVOIS and ENVOIS[0]["to"] == ["prospect@exemple.ch"])
    verifier("CAS A4. trace posee : statut envoye",
             (b.reservations.docs[0].get("confirmation") or {}).get("relance_j0", {}).get("statut") == "envoye",
             b.reservations.docs[0].get("confirmation"))

    # ══ CAS B — reserve mais ABSENT -> rien ═════════════════════════════════
    ENVOIS.clear()
    b = monde()
    esp = construire(b, ACTIF, consomme=False)
    issue = await esp["p1b_relance_j0"](resa())
    verifier("CAS B. absent -> aucune relance", issue == "non_consomme", issue)
    verifier("CAS B2. aucun e-mail", not ENVOIS)
    verifier("CAS B3. aucune trace posee — son droit reste entier",
             "confirmation" not in b.reservations.docs[0])

    # ══ CAS C — rejeu technique -> UN SEUL e-mail ═══════════════════════════
    ENVOIS.clear()
    b = monde()
    esp = construire(b, ACTIF)
    issues = [await esp["p1b_relance_j0"](resa()) for _ in range(3)]
    verifier("CAS C. trois rejeux -> un envoi, deux refus",
             issues == ["envoye", "deja_traitee", "deja_traitee"], issues)
    verifier("CAS C2. UN SEUL e-mail malgre trois appels", len(ENVOIS) == 1, len(ENVOIS))

    ENVOIS.clear()
    b = monde()
    esp = construire(b, ACTIF)
    simultanes = await asyncio.gather(*[esp["p1b_relance_j0"](resa()) for _ in range(4)])
    verifier("CAS C3. quatre appels SIMULTANES -> un seul e-mail",
             len(ENVOIS) == 1 and sorted(simultanes).count("envoye") == 1,
             (len(ENVOIS), sorted(simultanes)))

    # ══ CAS D — e-mail absent -> le parcours ne casse pas ═══════════════════
    ENVOIS.clear()
    b = _Base(reservations=[resa(userEmail="")], subscribers=[])
    esp = construire(b, ACTIF)
    issue = await esp["p1b_relance_j0"](resa(userEmail=""))
    verifier("CAS D. adresse absente -> sortie propre, aucune exception",
             issue == "sans_email", issue)
    verifier("CAS D2. aucun e-mail", not ENVOIS)
    verifier("CAS D3. la presence reste validee", b.reservations.docs[0]["validated"] is True)

    # ══ CAS E — e-mail INVALIDE -> presence intacte, erreur journalisee ═════
    ENVOIS.clear()
    JOURNAL.clear()
    b = _Base(reservations=[resa(userEmail="pas une adresse")], subscribers=[])
    esp = construire(b, ACTIF)
    issue = await esp["p1b_relance_j0"](resa(userEmail="pas une adresse"))
    verifier("CAS E. adresse invalide -> refusee par le filtre existant",
             issue == "sans_email", issue)
    verifier("CAS E2. presence intacte", b.reservations.docs[0]["validated"] is True)
    verifier("CAS E3. l'evenement est journalise",
             any("adresse exploitable" in l for l in JOURNAL), JOURNAL[-2:])

    # ══ CAS F — drapeau faux -> ZERO envoi, et pas meme une lecture ═════════
    ENVOIS.clear()
    b = monde()
    esp = construire(b, ETEINT)
    issue = await esp["p1b_relance_j0"](resa())
    verifier("CAS F. drapeau faux -> desactive", issue == "desactive", issue)
    verifier("CAS F2. aucun e-mail", not ENVOIS)
    verifier("CAS F3. aucune trace : la production est litteralement inchangee",
             "confirmation" not in b.reservations.docs[0])

    # ══ CAS G — simulation -> tout est calcule, personne n'est contacte ═════
    ENVOIS.clear()
    JOURNAL.clear()
    b = monde()
    esp = construire(b, SIMU)
    issue = await esp["p1b_relance_j0"](resa())
    verifier("CAS G. simulation -> issue « simulation »", issue == "simulation", issue)
    verifier("CAS G2. AUCUN e-mail reel", not ENVOIS)
    verifier("CAS G3. le destinataire et le sujet sont journalises",
             any("SIMULATION" in l and "prospect@exemple.ch" in l for l in JOURNAL),
             JOURNAL[-1:])
    verifier("CAS G4. aucun jeton pose — simuler ne brule pas le droit d'envoyer",
             "confirmation" not in b.reservations.docs[0])
    esp2 = construire(b, ACTIF)
    verifier("CAS G5. ... et l'envoi reel fonctionne ensuite",
             (await esp2["p1b_relance_j0"](resa())) == "envoye")

    # ══ CAS H — provider en panne -> presence intacte, echec trace ══════════
    ENVOIS.clear()
    b = monde()
    esp = construire(b, ACTIF, resend_ok=False)
    issue = await esp["p1b_relance_j0"](resa())
    verifier("CAS H. provider en panne -> issue « echec », aucune exception",
             issue == "echec", issue)
    verifier("CAS H2. la presence reste validee", b.reservations.docs[0]["validated"] is True)
    verifier("CAS H3. l'echec est TRACE, donc rattrapable a la main",
             (b.reservations.docs[0].get("confirmation") or {}).get("relance_j0", {}).get("statut") == "echec",
             b.reservations.docs[0].get("confirmation"))

    ENVOIS.clear()
    b = monde()
    esp = construire(b, ACTIF, resend_present=False)
    verifier("CAS H4. Resend non configure -> echec propre, pas de crash",
             (await esp["p1b_relance_j0"](resa())) == "echec")

    # ══ CAS I — participant PAYANT -> aucune relance d'essai ════════════════
    ENVOIS.clear()
    b = monde()
    esp = construire(b, ACTIF, essai=False)
    issue = await esp["p1b_relance_j0"](resa(promoCode="PULSE-X10"))
    verifier("CAS I. client payant -> pas_un_essai", issue == "pas_un_essai", issue)
    verifier("CAS I2. aucun e-mail", not ENVOIS)

    # ══ CAS J — un DEUXIEME essai refuse ne relance rien ════════════════════
    # Un essai refuse ne cree ni reservation ni presence : aucune sequence J+0
    # ne peut donc demarrer. On le prouve par la seule porte d'entree du lot.
    ENVOIS.clear()
    b = monde()
    esp = construire(b, ACTIF, consomme=False, essai=True)
    issue = await esp["p1b_relance_j0"](resa(id=""))
    verifier("CAS J. sans presence identifiable -> aucune sequence",
             issue == "deja_traitee", issue)
    verifier("CAS J2. aucun e-mail", not ENVOIS)

    # ══ OPT-OUT — un refus explicite se respecte ════════════════════════════
    ENVOIS.clear()
    b = _Base(reservations=[resa()],
              subscribers=[{"channel": "email", "value": "prospect@exemple.ch",
                            "status": "opted_out"}])
    esp = construire(b, ACTIF)
    verifier("OPT-OUT. desinscription explicite -> aucune relance",
             (await esp["p1b_relance_j0"](resa())) == "refuse")
    verifier("OPT-OUT2. aucun e-mail", not ENVOIS)

    ENVOIS.clear()
    b = monde()
    esp = construire(b, ACTIF, autorise_v286=False)
    verifier("OPT-OUT3. preference V286 contraire -> aucune relance",
             (await esp["p1b_relance_j0"](resa())) == "refuse")

    ENVOIS.clear()
    b = _Base(reservations=[resa()],
              subscribers=[{"channel": "email", "value": "prospect@exemple.ch",
                            "status": "confirmed"}])
    esp = construire(b, ACTIF)
    verifier("OPT-OUT4. inscrit confirme -> la relance part",
             (await esp["p1b_relance_j0"](resa())) == "envoye")


def _bouton_de(html):
    """Le fragment du CTA seul, isole du gabarit partage."""
    _i = html.find("Continuer avec Afroboost")
    return html[max(0, _i - 300):_i + 40] if _i >= 0 else ""


def contenu():
    esp = construire(monde(), ACTIF)
    sujet, html, texte = esp["p1b_contenu_relance"](
        "Ana", "Silent Mercredi", "https://afroboost.com/espace/AFR-ESSAI1", "#D91CD2")

    verifier("C1. le sujet ne COMMENCE pas par un emoji (filtrage Gmail)",
             sujet[0].isalpha(), sujet)
    verifier("C2. le sujet est celui demande par le proprietaire",
             sujet == "Merci pour ton énergie aujourd'hui 🔥", sujet)
    verifier("C3. AUCUNE offre, AUCUN prix, AUCUNE urgence dans le message",
             not any(m in html for m in ("PULSE", "250", "150", "CHF", "30 CHF",
                                         "Achète", "Achete", "dernière chance")),
             "P1-c decidera de l'offre, pas ce lot")
    verifier("C4. le CTA pointe vers l'espace du participant",
             'href="https://afroboost.com/espace/AFR-ESSAI1"' in html)
    verifier("C5. le libelle du CTA est celui demande",
             "Continuer avec Afroboost" in html)
    verifier("C6. le gabarit partage est reutilise, pas reecrit",
             "AFROBOOST" in html and "MOVE • GROOVE • BOOST" in html)
    verifier("C7. une version TEXTE accompagne le HTML",
             "Afroboost" in texte and "https://afroboost.com/espace/AFR-ESSAI1" in texte)
    verifier("C8. le prenom est repris", "Merci Ana," in html)

    _s2, _h2, _t2 = esp["p1b_contenu_relance"]("", "", "", "#D91CD2")
    verifier("C9. sans prenom ni cours ni lien : aucun trou, aucun bouton mort",
             "Merci," in _h2 and "Continuer avec Afroboost" not in _h2
             and "None" not in _h2 and "ton cours" not in _h2)
    # DETTE LEVEE. Le pied de page de `_email_wrapper` affichait
    # « afroboost.com » en pointant vers `afroboost-v11-dev-pm7l...`, un residu
    # Vercel qui sert un bundle perime ; son `href` a ete corrige, et la garde
    # de perimetre du lot RV2 qui gelait cette fonction est desormais bornee a
    # sa propre plage de commits. La preuve complete — pied de page ET CTA, sur
    # le texte affiche comme sur la destination — vit dans
    # `tests/test_p1b_footer_domaine.py`. Ce qui reste verifie ICI, c'est le
    # lien que CE lot fabrique.
    verifier("C9b. le CTA fabrique par ce lot ne porte aucun residu Vercel",
             "vercel.app" not in (_bouton_de(html) or ""))
    verifier("C9c. et le message entier non plus — pied de page compris",
             "vercel.app" not in html and "vercel.app" not in texte,
             [u for u in __import__("re").findall(r'https?://[^\s"\'<>]+', html)
              if "vercel.app" in u])
    _s3, _h3, _t3 = esp["p1b_contenu_relance"](
        '<script>x</script>', '"><b>', "https://afroboost.com/espace/A", "#D91CD2")
    verifier("C10. le nom et le cours sont ECHAPPES",
             "<script>" not in _h3 and "&lt;script&gt;" in _h3)

    verifier("C11. le lien refuse un code hors alphabet",
             esp["p1b_lien_espace"]("../admin") == ""
             and esp["p1b_lien_espace"]("a b") == ""
             and esp["p1b_lien_espace"]("") == "")
    verifier("C12. le lien met le code en MAJUSCULES, comme l'exige le frontend",
             esp["p1b_lien_espace"]("afr-abc123")
             == "https://afroboost.com/espace/AFR-ABC123")
    verifier("C13. le domaine est en dur — FRONTEND_URL porte le residu Vercel",
             "afroboost-v11-dev-pm7l" not in esp["p1b_lien_espace"]("AFR-1"))


def structure():
    """Ce que le code doit dire de lui-meme."""
    nu_a0 = extraire("_a0_marquer_presente") if False else None
    _resa_src = io.open(os.path.join(RACINE, "api", "routes", "reservation_routes.py"),
                        encoding="utf-8").read()
    verifier("S1. la relance est branchee sur la transition ATOMIQUE de presence",
             _resa_src.count("_p1b_apres_presence(") == 3,
             "1 definition + 2 points d'appel")
    _arbre_r = ast.parse(_resa_src)
    _fn = {n.name: ast.get_source_segment(_resa_src, n) for n in ast.walk(_arbre_r)
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    verifier("S2. elle part APRES le verdict d'atomicite, jamais avant",
             _fn["_a0_marquer_presente"].index("matched_count")
             < _fn["_a0_marquer_presente"].index("_p1b_apres_presence"))
    verifier("S3. l'accesseur avale TOUT — une presence ne casse pas sur un e-mail",
             "except Exception" in _fn["_p1b_apres_presence"]
             and "presence reste validee" in _fn["_p1b_apres_presence"])

    nu_lance = extraire("p1b_apres_presence")
    verifier("S4. l'envoi part en tache de fond, jamais dans le chemin HTTP",
             "asyncio.create_task" in nu_lance)
    nu = extraire("p1b_relance_j0")
    verifier("S5. le drapeau est lu AVANT toute lecture metier",
             nu.index("P1_TRIAL_J0_ENABLED") < nu.index("est_un_essai"))
    verifier("S6. le jeton est pris APRES la simulation — simuler ne brule rien",
             nu.index('"simulation"') < nu.index("_rc_reserver_jeton"))
    verifier("S7. le jeton est pris AVANT l'envoi, jamais apres",
             nu.index("_p1b_reserver") < nu.index("p1b_envoyer_email"))
    verifier("S8. aucune offre ni aucun prix n'est nomme dans tout le lot",
             not any(m in nu + extraire("p1b_contenu_relance")
                     for m in ("PULSE", "249", "250", "150 CHF")))
    nu_env = extraire("p1b_envoyer_email")
    verifier("S9. le transport existant est reutilise, sans nouveau moteur",
             "resend.Emails.send" in nu_env and "asyncio.to_thread" in nu_env)
    verifier("S10. un reply_to relevé accompagne l'invitation a repondre",
             "RV2_REPLY_TO" in nu_env)
    verifier("S11. le second drapeau n'est PAS nomme DRY_RUN (absent = envoi reel)",
             "P1_TRIAL_J0_DRY_RUN" not in SERVEUR
             and SERVEUR.count("P1_TRIAL_J0_ENVOI_REEL") >= 5)
    verifier("S12. les deux drapeaux sont declares aux 4 emplacements obligatoires",
             SERVEUR.count("P1_TRIAL_J0_ENABLED") >= 5)


def principal():
    asyncio.get_event_loop().run_until_complete(scenarios())
    contenu()
    structure()
    print("=" * 78)
    print("P1-b — LA RELANCE J+0 APRES UN ESSAI CONSOMME")
    print("=" * 78)
    rates = 0
    for nom, ok, detail in RESULTATS:
        print("  %s %s" % ("OK    " if ok else "ECHEC ", nom))
        if detail and not ok:
            print("         -> %s" % (detail,))
        rates += 0 if ok else 1
    print("-" * 78)
    print("%d / %d verifications" % (len(RESULTATS) - rates, len(RESULTATS)))
    print("E-mails REELLEMENT envoyes : 0 — transport remplace, base en memoire.")
    return 1 if rates else 0


if __name__ == "__main__":
    sys.exit(principal())
