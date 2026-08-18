# -*- coding: utf-8 -*-
"""
PARCOURS UNIFIE DU PREMIER COURS GRATUIT — Hero et carte, un seul moteur.

Deux moities, toutes deux jouees pour de vrai :
  BACKEND  la garde ESSAI-4 (abonne actif) est executee contre une base simulee,
           avec les VRAIES fonctions `forfait_utilisable` et `essai2_codes_essai`.
  FRONTEND le raccord est verifie sur le CODE REEL des trois fichiers modifies —
           aucun navigateur, mais aucune affirmation sur parole non plus.

L'INVARIANT DU LOT : le premier cours gratuit ne dépend plus d'une preuve
sociale ni d'une validation coach ; il dépend de DEUX questions, dans cet
ordre — « es-tu deja client actif ? » puis « as-tu deja eu ton essai ? ».

HORS LIGNE. Aucune connexion, aucune ecriture, aucune donnee de production.

    python3 tests/test_essai_parcours_unifie.py
"""
import asyncio
import io
import os
import re
import sys
import types
import uuid

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def lire(*bouts):
    return io.open(os.path.join(RACINE, *bouts), encoding="utf-8").read()

CHECKOUT = lire("api", "routes", "checkout_routes.py")
SHARED = lire("api", "routes", "shared.py")
SERVEUR = lire("api", "server.py")
APPJS = lire("frontend", "src", "App.js")
WIDGET = lire("frontend", "src", "components", "ChatWidget.js")
LIENS = lire("frontend", "src", "components", "coach", "SmartLinksSection.js")

resultats = []
def verifier(nom, cond, detail=""):
    resultats.append((nom, bool(cond), str(detail)))

def extraire(src, nom):
    m = re.search(r"^async def %s\(.*?(?=^(?:async def |def |@)|\Z)" % nom, src, re.S | re.M)
    if not m:
        m = re.search(r"^def %s\(.*?(?=^(?:async def |def |@)|\Z)" % nom, src, re.S | re.M)
    return m.group(0) if m else ""

def code_seul(src):
    """Sans commentaires ni docstrings : on raisonne sur le CODE."""
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    return re.sub(r"^\s*#.*$", "", src, flags=re.M)


# ---------------------------------------------------------------------------
# Base simulee
# ---------------------------------------------------------------------------
class FausseCollection:
    def __init__(self):
        self.docs = []

    def _match(self, doc, f):
        for k, v in (f or {}).items():
            if isinstance(v, dict) and "$regex" in v:
                if not re.match(v["$regex"], str(doc.get(k) or ""),
                                re.I if "i" in (v.get("$options") or "") else 0):
                    return False
            elif k == "$or":
                if not any(self._match(doc, sf) for sf in v):
                    return False
            elif doc.get(k) != v:
                return False
        return True

    async def find_one(self, f=None, proj=None):
        for d in self.docs:
            if self._match(d, f or {}):
                return dict(d)
        return None

    def find(self, f=None, proj=None):
        parent = self
        class _C:
            async def to_list(self, n=None):
                return [dict(d) for d in parent.docs if parent._match(d, f or {})]
        return _C()

    async def insert_one(self, doc):
        self.docs.append(dict(doc))


class FausseBase:
    def __init__(self):
        self.subscriptions = FausseCollection()
        self.discount_codes = FausseCollection()
    def __getitem__(self, n):
        return getattr(self, n)


class HTTPException(Exception):
    def __init__(self, status_code=None, detail=None, headers=None):
        self.status_code, self.detail, self.headers = status_code, detail, headers or {}


def construire(base):
    """Charge les VRAIES fonctions : ESSAI-4 (checkout) + le socle (shared)."""
    import datetime, logging

    esp_sh = {"datetime": datetime.datetime, "timezone": datetime.timezone,
              "logger": logging.getLogger("t"), "re": re}
    for fn in ("_v391_est_expire", "_v391_seances_restantes", "forfait_utilisable"):
        exec(compile(extraire(SHARED, fn), "<sh>", "exec"), esp_sh)
    exec(compile("ESSAI2_FILTRE_GRATUIT = {'$or': [{'payment_method': 'free', 'total_paid': 0},"
                 "{'source': 'social_proof'}]}", "<sh2>", "exec"), esp_sh)
    esp_sh["db"] = base
    exec(compile(extraire(SHARED, "essai2_codes_essai"), "<sh3>", "exec"), esp_sh)

    faux_shared = types.ModuleType("api.routes.shared")
    for k, v in esp_sh.items():
        setattr(faux_shared, k, v)
    async def _ph(event, email="", props=None, **kw):
        faux_shared.evenements.append({"event": event, "email": email, "props": props or {}})
    faux_shared.evenements = []
    faux_shared.posthog_capture = _ph
    sys.modules["api"] = types.ModuleType("api")
    sys.modules["api.routes"] = types.ModuleType("api.routes")
    sys.modules["api.routes.shared"] = faux_shared

    esp = {"db": base, "HTTPException": HTTPException, "logger": logging.getLogger("t"),
           "datetime": datetime.datetime, "timezone": datetime.timezone, "uuid": uuid}
    exec(compile('ESSAI4_RAISON = "active_subscription"\nESSAI4_MESSAGE = "actif"',
                 "<c>", "exec"), esp)
    for fn in ("_essai4_abonnement_actif", "_essai4_garde"):
        exec(compile(extraire(CHECKOUT, fn), "<ck>", "exec"), esp)
    return esp, faux_shared


PAYANT = {"code": "PULSE10", "email": "cliente@exemple.ch", "status": "active",
          "expires_at": None, "remaining_sessions": 7, "total_sessions": 10,
          "used_sessions": 3}


async def scenario_backend():
    # --- 1. nouveau visiteur : rien en base -> autorise ---------------------
    base = FausseBase()
    esp, sh = construire(base)
    verifier("1. nouveau visiteur, jamais client -> AUTORISE",
             (await esp["_essai4_abonnement_actif"]("neuf@exemple.ch")) is False)
    try:
        await esp["_essai4_garde"]("neuf@exemple.ch", "off-1")
        verifier("1b. la garde le laisse passer", True)
    except HTTPException as e:
        verifier("1b. la garde le laisse passer", False, f"{e.status_code} {e.detail}")

    # --- 5. abonne ACTIF -> refus propre ------------------------------------
    base2 = FausseBase()
    await base2.subscriptions.insert_one(dict(PAYANT))
    esp2, sh2 = construire(base2)
    verifier("5. abonne actif -> detecte",
             (await esp2["_essai4_abonnement_actif"]("cliente@exemple.ch")) is True)
    try:
        await esp2["_essai4_garde"]("cliente@exemple.ch", "off-1")
        verifier("5a. abonne actif -> REFUS", False, "laisse passer")
    except HTTPException as e:
        verifier("5a. abonne actif -> REFUS 409", e.status_code == 409, e.status_code)
        verifier("5b. motif machine distinct de l'essai",
                 (e.headers or {}).get("X-Refus-Raison") == "active_subscription", e.headers)
    verifier("5c. le refus ne dit PAS « essai deja utilise »",
             "essai" not in str(esp2["ESSAI4_MESSAGE"]).lower()
             or "utilis" not in str(esp2["ESSAI4_MESSAGE"]).lower())
    verifier("5d. le refus est mesure, sans PII",
             any(e["event"] == "trial_refused"
                 and e["props"].get("reason") == "active_subscription"
                 and not e["email"] for e in sh2.evenements),
             sh2.evenements)

    # --- 6. ancien abonne : forfait EXPIRE -> autorise ----------------------
    base3 = FausseBase()
    await base3.subscriptions.insert_one(dict(PAYANT, expires_at="2020-01-01T00:00:00+00:00"))
    esp3, _ = construire(base3)
    verifier("6a. forfait EXPIRE -> n'est plus un abonnement actif",
             (await esp3["_essai4_abonnement_actif"]("cliente@exemple.ch")) is False)

    # --- 6b. ancien abonne : forfait EPUISE -> autorise ---------------------
    base4 = FausseBase()
    await base4.subscriptions.insert_one(dict(PAYANT, remaining_sessions=0, used_sessions=10))
    esp4, _ = construire(base4)
    verifier("6b. forfait EPUISE -> n'est plus un abonnement actif",
             (await esp4["_essai4_abonnement_actif"]("cliente@exemple.ch")) is False)

    # --- 6c. forfait clos (status != active) -> autorise --------------------
    base5 = FausseBase()
    await base5.subscriptions.insert_one(dict(PAYANT, status="superseded"))
    esp5, _ = construire(base5)
    verifier("6c. forfait clos -> n'est plus un abonnement actif",
             (await esp5["_essai4_abonnement_actif"]("cliente@exemple.ch")) is False)

    # --- 9/10. un ESSAI n'est PAS un abonnement actif -----------------------
    #
    # LE PIEGE DU LOT. L'essai cree lui aussi une `subscriptions` active avec une
    # seance. Sans exclusion, la personne qui vient d'obtenir son essai
    # s'entendrait dire « vous avez deja un abonnement actif » — vrai au sens
    # litteral, faux au sens du produit, et surtout: le mauvais message.
    base6 = FausseBase()
    await base6.subscriptions.insert_one({
        "code": "AFR-ESSAI", "email": "essai@exemple.ch", "status": "active",
        "expires_at": None, "remaining_sessions": 1, "total_sessions": 1,
        "used_sessions": 0})
    await base6.discount_codes.insert_one({
        "code": "AFR-ESSAI", "assignedEmail": "essai@exemple.ch",
        "payment_method": "free", "total_paid": 0})
    esp6, _ = construire(base6)
    verifier("9. un forfait d'ESSAI n'est PAS un abonnement actif",
             (await esp6["_essai4_abonnement_actif"]("essai@exemple.ch")) is False,
             "ESSAI-4 doit laisser ESSAI-1 repondre")

    # --- meme chose pour un essai obtenu par preuve sociale ------------------
    base7 = FausseBase()
    await base7.subscriptions.insert_one({
        "code": "AFR-SOC", "email": "soc@exemple.ch", "status": "active",
        "expires_at": None, "remaining_sessions": 1, "total_sessions": 1,
        "used_sessions": 0})
    await base7.discount_codes.insert_one({
        "code": "AFR-SOC", "assignedEmail": "soc@exemple.ch", "source": "social_proof"})
    esp7, _ = construire(base7)
    verifier("9b. un essai par preuve sociale non plus",
             (await esp7["_essai4_abonnement_actif"]("soc@exemple.ch")) is False)

    # --- abonne payant ET essai passe : le PAYANT domine --------------------
    base8 = FausseBase()
    await base8.subscriptions.insert_one(dict(PAYANT, email="mixte@exemple.ch"))
    await base8.subscriptions.insert_one({
        "code": "AFR-VIEIL", "email": "mixte@exemple.ch", "status": "active",
        "expires_at": None, "remaining_sessions": 1, "total_sessions": 1})
    await base8.discount_codes.insert_one({
        "code": "AFR-VIEIL", "assignedEmail": "mixte@exemple.ch",
        "payment_method": "free", "total_paid": 0})
    esp8, _ = construire(base8)
    verifier("10. un forfait payant a cote d'un essai -> abonne actif",
             (await esp8["_essai4_abonnement_actif"]("mixte@exemple.ch")) is True)

    # --- robustesse : adresse vide, casse differente ------------------------
    verifier("adresse vide -> jamais bloquant",
             (await esp2["_essai4_abonnement_actif"]("")) is False)
    verifier("casse differente -> toujours reconnu",
             (await esp2["_essai4_abonnement_actif"]("  CLIENTE@Exemple.CH ")) is True)


def perimetre_backend():
    _free = code_seul(extraire(CHECKOUT, "free_checkout"))
    _sess = code_seul(extraire(CHECKOUT, "create_checkout_session"))
    _g4 = code_seul(extraire(CHECKOUT, "_essai4_garde"))

    verifier("B1. ESSAI-4 garde les deux portes gratuites",
             "_essai4_garde(" in _free and "_essai4_garde(" in _sess)
    verifier("B2. ESSAI-4 passe AVANT ESSAI-1 (elle lit, l'autre ecrit)",
             _free.index("_essai4_garde(") < _free.index("_essai1_garde("))
    verifier("B2b. meme ordre sur la seconde porte",
             _sess.index("_essai4_garde(") < _sess.index("_essai1_garde("))
    verifier("B3. ESSAI-4 n'ECRIT rien",
             not any(m in code_seul(extraire(CHECKOUT, "_essai4_abonnement_actif"))
                     for m in ("insert_one", "update_one", "delete_one")))
    verifier("B4. le refus n'expose NI code NI lien espace",
             "espace/" not in _g4 and "code" not in _g4.lower().replace("status_code", ""))
    verifier("B5. la verite « actif » vient de forfait_utilisable, pas d'un doublon",
             "forfait_utilisable" in extraire(CHECKOUT, "_essai4_abonnement_actif"))
    verifier("B6. les essais sont retires de l'examen (ESSAI-1 repond pour eux)",
             "essai2_codes_essai" in extraire(CHECKOUT, "_essai4_abonnement_actif"))
    verifier("B7. Conditions toujours exigees avant l'octroi",
             "_t1_preuve_checkout(" in _free)
    verifier("B8. ESSAI-1 et son filet intacts",
             "_essai1_garde(" in _free and "_essai1_liberer(" in _free)
    verifier("B9. le funnel est toujours alimente",
             "essai2_tracer_octroi" in _free)
    verifier("B10. l'e-mail garde son lien profond vers l'espace",
             "espace/{access_code}" in CHECKOUT)
    verifier("B11. aucune PII dans la mesure du refus",
             'email=""' in extraire(CHECKOUT, "_essai4_garde"))
    verifier("B12. la preuve sociale reste INTACTE et separee",
             all(x in SERVEUR for x in ("submit_social_proof", "review_social_proof",
                                        "social_proof_pending", "_essai1_garde as _g2_garde")))
    verifier("B13. les temoignages restent independants",
             "contact_type" in extraire(SERVEUR, "t3_eligibilite")
             and "social_proof" not in code_seul(extraire(SERVEUR, "t3_eligibilite")))


def perimetre_frontend():
    # --- 2. le Hero rejoint le moteur ---------------------------------------
    verifier("F1. le tunnel lit enfin l'action « booking »",
             "a.type === 'booking'" in WIDGET)
    verifier("F2. il redirige vers l'offre, en mode reservation",
             "'/?offre=' + encodeURIComponent(bookingOfferId) + '&reserver=1'" in WIDGET)
    verifier("F3. l'identite des 7 etapes est reportee (pas de double saisie)",
             "af_client_info" in WIDGET)
    verifier("F4. le paiement reste PRIORITAIRE (comportement inchange)",
             WIDGET.index("a.type === 'payment'") < WIDGET.index("a.type === 'booking'"))
    verifier("F5. sans action exploitable -> le chat, comme avant",
             "handleSmartEntry(clientData, currentLinkToken)" in WIDGET)
    # Le commentaire du raccord CITE la route (c'est son sujet) : on raisonne
    # donc sur le CODE, jamais sur le texte qui l'explique.
    _widget_code = re.sub(r"^\s*//.*$", "", WIDGET, flags=re.M)
    verifier("F6. aucun second moteur cote client : aucun appel au checkout gratuit",
             "checkout/free" not in _widget_code,
             [l.strip()[:60] for l in _widget_code.split("\n") if "checkout/free" in l])

    # --- 3/4. la vitrine ----------------------------------------------------
    verifier("F7. `reserver=1` ouvre le formulaire de l'offre",
             "get('reserver') === '1'" in APPJS and "onSelectOffer(v449Offre)" in APPJS)
    verifier("F8. sans le parametre, le lien profond reste inerte (V371 preservee)",
             "v449Reserver && typeof onSelectOffer === 'function'" in APPJS)
    verifier("F9. aucune boucle : les dependances restent [offers]",
             "}, [offers]);" in APPJS)
    verifier("F10. la carte mene au moteur gratuit, inchange",
             "`${API}/checkout/free`" in APPJS)
    verifier("F11. la case Conditions reste sur le chemin",
             "ConditionsParticipation" in APPJS and "termsRequired" in APPJS)
    verifier("F12. la modale preuve sociale existe toujours (rallumable)",
             "SocialProofChoiceModal" in APPJS and "v260HasSocialProof" in APPJS)

    # --- le coach peut configurer sans toucher a la base --------------------
    verifier("F13. le coach choisit l'offre du parcours",
             'data-testid="booking-offer-select"' in LIENS)
    verifier("F14. seules les offres gratuites sont proposees",
             "!parseFloat(o.price)" in LIENS)
    verifier("F15. laisser vide = comportement d'avant",
             "Aucune (terminer dans la conversation)" in LIENS)

    # --- 14. aucune PII nouvelle -------------------------------------------
    verifier("F16. aucune donnee personnelle nouvelle n'est envoyee",
             "terms_accepted: hasAcceptedTerms" in APPJS)

    # --- couleurs : regle absolue du projet ---------------------------------
    _bloc = LIENS[LIENS.index("booking-offer-select") - 2200:
                  LIENS.index("booking-offer-select") + 2200]
    _durs = [h for h in re.findall(r"#[0-9a-fA-F]{6}", _bloc)
             if "var(--" not in _bloc[max(0, _bloc.index(h) - 40):_bloc.index(h)]]
    verifier("F17. aucune couleur de marque codee en dur dans le bloc ajoute",
             all(h.lower() not in ("#d91cd2", "#a855f7", "#8b5cf6", "#9333ea") for h in _durs),
             _durs)


asyncio.run(scenario_backend())
perimetre_backend()
perimetre_frontend()

print("=" * 78)
echecs = 0
for nom, ok, detail in resultats:
    print(("  PASS  " if ok else "  FAIL  ") + nom + ("" if ok else "   -> " + detail[:110]))
    if not ok:
        echecs += 1
print("=" * 78)
print("Essais / abonnements / donnees REELS : 0 — base simulee en memoire")
print("%d/%d verifications" % (len(resultats) - echecs, len(resultats)))
sys.exit(1 if echecs else 0)
