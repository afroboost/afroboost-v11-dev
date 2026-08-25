# -*- coding: utf-8 -*-
"""P1-c — LE VENDEUR QUI ENCAISSE N'EST PAS LE MARQUEUR DE PROPRIETE.

LE DEFAUT, CONSTATE EN PRODUCTION LE 25/08/2026. Le vrai parcours terrain est
alle jusqu'au bout : e-mail J+0 recu, CTA clique, ecran P1-c affiche, PULSE x10
recommandee a 250 CHF. Au clic sur « Choisir cette offre », le serveur a
repondu :

    « Paiements non configures. Le partenaire doit configurer ses methodes de
      paiement. »

Or Stripe fonctionne (cle d'environnement posee) et cette offre a deja ete
vendue 29 fois. La cause n'etait ni Stripe, ni une configuration manquante :
`post_conversion_checkout` passait a la caisse `coach_email=coach_id`, le
MARQUEUR DE PROPRIETE du forfait — vide (`""`) pour tous les codes d'essai,
`None` sur les 8 offres de production. `get_payment_keys("")` cherchait alors
un partenaire nomme « chaine vide », n'en trouvait aucun, et refusait.

UN MARQUEUR DE PROPRIETE AVAIT ETE PRIS POUR UNE CLE DE ROUTAGE BANCAIRE.
Les deux coincident pour un vrai partenaire, et divergent totalement pour la
plateforme, dont les offres n'ont — par conception LOT A — aucun proprietaire.

LA REGLE ARRETEE PAR LE PROPRIETAIRE, en entier :
  A. offre plateforme (aucun proprietaire, nulle part) -> repli sur le compte
     PLATEFORME, celui qui encaisse deja les 29 ventes PULSE ;
  B. offre d'un partenaire identifie -> SA configuration, inchangee ;
  C. partenaire identifie mais NON configure -> ERREUR, et AUCUN repli.
     « Je refuse qu'Afroboost encaisse a la place d'un partenaire sans que ce
     soit deliberement configure. »

Ce banc reutilise le decor du banc LOT A (meme faux Mongo, meme mouchard de
caisse) : les regles d'eligibilite y sont deja prouvees, on ne les rejoue pas.

AUCUN RESEAU, AUCUNE BASE REELLE, AUCUN PAIEMENT.
    python3 tests/test_p1c_vendeur_paiement.py
"""
import ast, asyncio, io, os, sys, types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.join(RACINE, "tests"))

import test_lota_conversion as T   # le decor LOT A, reutilise tel quel

RESULTATS = []
PLATEFORME = "contact.artboost@gmail.com"   # la valeur ATTENDUE, pas la source
PARTENAIRE = "partenaire@coach.ch"
AUTRE = "autre@coach.ch"


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


# ───────── la vraie `get_payment_keys`, extraite de checkout_routes.py ───────
_SRC_CK = io.open(os.path.join(RACINE, "api", "routes", "checkout_routes.py"),
                  encoding="utf-8").read()
_ARBRE_CK = ast.parse(_SRC_CK)


def _extraire_ck(nom):
    for n in ast.walk(_ARBRE_CK):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return ast.get_source_segment(_SRC_CK, n)
    raise AssertionError("introuvable : %s" % nom)


def caisse_reelle(configs, env_stripe="sk_test_env"):
    """`get_payment_keys` et `is_super_admin`, les VRAIES, avec un decor pilote."""
    class _Coll:
        def __init__(self, docs): self.docs = docs
        async def find_one(self, f=None, p=None):
            for d in self.docs:
                if all(d.get(k) == v for k, v in (f or {}).items()):
                    return dict(d)
            return None

    class _Base:
        def __init__(self, docs): self._c = _Coll(docs)
        def __getitem__(self, n): return self._c

    esp = {"__builtins__": __builtins__, "os": types.SimpleNamespace(
        environ={"STRIPE_SECRET_KEY": env_stripe} if env_stripe else {}),
        "db": _Base(configs),
        "SUPER_ADMIN_EMAILS": [PLATEFORME, "afroboost.bassi@gmail.com"]}
    for fn in ("is_super_admin", "get_payment_keys"):
        exec(compile(_extraire_ck(fn), "<ck>", "exec"), esp)
    return esp


CONFIG_PARTENAIRE = {"coach_email": PARTENAIRE, "stripe_enabled": True,
                     "stripe_secret_key": "sk_live_partenaire"}


async def scenarios():
    # ══════════════════════════════════════════════════════════════════════
    # NIVEAU 1 — LA RESOLUTION DU VENDEUR DANS P1-c
    # ══════════════════════════════════════════════════════════════════════

    # ── A. LE CAS REEL DE PRODUCTION : rien ne porte de proprietaire ───────
    # Les 8 offres portent `coach_id: None`, les 12 forfaits d'essai `""`.
    T.CAISSE[:] = []
    ns, nsr, base = T.bac(
        codes=[T.code_gratuit(coach_id="")],
        subs=[T.forfait(coach_id="")],
        resas=[T.resa(validee=True)], courses=[T.cours_recurrent()],
        offers=[T.PULSE(coach_id=None), T.UNITE(coach_id=None), T.MEMBRES()])
    await nsr["post_conversion_checkout"]("AFR-ESSAI", T._Requete({"offer_id": "off-pulse"}))
    verifier("A. PULSE 250 plateforme (offre None + forfait '') -> vendeur = PLATEFORME",
             T.CAISSE and T.CAISSE[0].coach_email == PLATEFORME,
             T.CAISSE[0].coach_email if T.CAISSE else "(aucun appel caisse)")
    verifier("A2. le prix reste celui du catalogue",
             T.CAISSE and T.CAISSE[0].items[0].price == 250.0)

    T.CAISSE[:] = []
    ns, nsr, base = T.bac(
        codes=[T.code_gratuit(coach_id="")],
        subs=[T.forfait(coach_id="")],
        resas=[T.resa(validee=True)], courses=[T.cours_recurrent()],
        offers=[T.PULSE(coach_id=None), T.UNITE(coach_id=None), T.MEMBRES()])
    await nsr["post_conversion_checkout"]("AFR-ESSAI", T._Requete({"offer_id": "off-unite"}))
    verifier("A3. Cours a l'unite 30 plateforme -> vendeur = PLATEFORME",
             T.CAISSE and T.CAISSE[0].coach_email == PLATEFORME,
             T.CAISSE[0].coach_email if T.CAISSE else "(aucun appel caisse)")

    # A4 — les TROIS formes de « sans proprietaire » se valent : None, "", absent.
    for _forme, _val in (("None", None), ("chaine vide", ""), ("champ absent", "ABSENT")):
        T.CAISSE[:] = []
        _off = T.PULSE(coach_id=None) if _val == "ABSENT" else T.PULSE(coach_id=_val)
        if _val == "ABSENT":
            _off.pop("coach_id", None)
        ns, nsr, base = T.bac(
            codes=[T.code_gratuit(coach_id="")], subs=[T.forfait(coach_id="")],
            resas=[T.resa(validee=True)], courses=[T.cours_recurrent()],
            offers=[_off, T.UNITE(coach_id=None), T.MEMBRES()])
        await nsr["post_conversion_checkout"]("AFR-ESSAI", T._Requete({"offer_id": "off-pulse"}))
        verifier("A4. offre sans proprietaire (%s) -> PLATEFORME" % _forme,
                 T.CAISSE and T.CAISSE[0].coach_email == PLATEFORME,
                 T.CAISSE[0].coach_email if T.CAISSE else "(aucun appel)")

    # ── B. OFFRE D'UN PARTENAIRE IDENTIFIE : rien ne change ────────────────
    T.CAISSE[:] = []
    ns, nsr, base = T.bac(
        codes=[T.code_gratuit(coach_id=PARTENAIRE)],
        subs=[T.forfait(coach_id=PARTENAIRE)],
        resas=[T.resa(validee=True)], courses=[T.cours_recurrent(coach_id=PARTENAIRE)],
        offers=[T.PULSE(coach_id=PARTENAIRE), T.UNITE(coach_id=PARTENAIRE), T.MEMBRES()])
    await nsr["post_conversion_checkout"]("AFR-ESSAI", T._Requete({"offer_id": "off-pulse"}))
    verifier("B. offre d'un partenaire -> vendeur = CE partenaire, jamais la plateforme",
             T.CAISSE and T.CAISSE[0].coach_email == PARTENAIRE,
             T.CAISSE[0].coach_email if T.CAISSE else "(aucun appel)")

    # ── AUCUN CROSS-COACH : c'est l'OFFRE qui decide, pas le forfait ───────
    T.CAISSE[:] = []
    ns, nsr, base = T.bac(
        codes=[T.code_gratuit(coach_id=AUTRE)],
        subs=[T.forfait(coach_id=AUTRE)],
        resas=[T.resa(validee=True)], courses=[T.cours_recurrent(coach_id=AUTRE)],
        offers=[T.PULSE(coach_id=AUTRE), T.UNITE(coach_id=AUTRE), T.MEMBRES()])
    await nsr["post_conversion_checkout"]("AFR-ESSAI", T._Requete({"offer_id": "off-pulse"}))
    verifier("X. l'argent va au proprietaire de l'OFFRE, jamais a un autre coach",
             T.CAISSE and T.CAISSE[0].coach_email == AUTRE,
             T.CAISSE[0].coach_email if T.CAISSE else "(aucun appel)")

    # ── D. offre SANS proprietaire + forfait D'UN PARTENAIRE ──────────────
    # CE CAS N'EXISTE PAS, et c'est LOT A qui l'interdit en amont : le filtre
    # coach est SYMETRIQUE — un essai qui declare un coach ne voit QUE les
    # offres de ce coach, jamais celles « sans proprietaire ». La caisse n'est
    # donc jamais atteinte, et le repli sur le forfait est inatteignable par
    # construction. On le PROUVE ici plutot que de l'affirmer : c'est ce qui
    # garantit qu'aucune combinaison ne peut faire encaisser la plateforme a la
    # place d'un partenaire identifiable.
    T.CAISSE[:] = []
    ns, nsr, base = T.bac(
        codes=[T.code_gratuit(coach_id=PARTENAIRE)],
        subs=[T.forfait(coach_id=PARTENAIRE)],
        resas=[T.resa(validee=True)], courses=[T.cours_recurrent(coach_id=PARTENAIRE)],
        offers=[T.PULSE(coach_id=None), T.UNITE(coach_id=None), T.MEMBRES()])
    try:
        await nsr["post_conversion_checkout"]("AFR-ESSAI", T._Requete({"offer_id": "off-pulse"}))
        verifier("D. offre sans proprietaire + forfait d'un partenaire -> REFUS LOT A",
                 False, "la caisse a ete atteinte : %s" % (
                     T.CAISSE[0].coach_email if T.CAISSE else "?"))
    except T._HTTPException as ex:
        verifier("D. offre sans proprietaire + forfait d'un partenaire -> REFUS LOT A",
                 ex.status_code == 403 and not T.CAISSE,
                 "%s / caisse=%d" % (ex.status_code, len(T.CAISSE)))

    # ── le corps de la requete ne peut toujours RIEN injecter ──────────────
    T.CAISSE[:] = []
    ns, nsr, base = T.bac(
        codes=[T.code_gratuit(coach_id="")], subs=[T.forfait(coach_id="")],
        resas=[T.resa(validee=True)], courses=[T.cours_recurrent()],
        offers=[T.PULSE(coach_id=None), T.UNITE(coach_id=None), T.MEMBRES()])
    await nsr["post_conversion_checkout"]("AFR-ESSAI", T._Requete(
        {"offer_id": "off-pulse", "coach_email": "pirate@mail.ch"}))
    verifier("S. `coach_email` fourni par le navigateur reste IGNORE",
             T.CAISSE and T.CAISSE[0].coach_email == PLATEFORME,
             T.CAISSE[0].coach_email if T.CAISSE else "(aucun appel)")

    # ══════════════════════════════════════════════════════════════════════
    # NIVEAU 2 — CE QUE LA CAISSE FAIT DE CE VENDEUR (vraie `get_payment_keys`)
    # ══════════════════════════════════════════════════════════════════════
    ck = caisse_reelle([CONFIG_PARTENAIRE])

    cles, err = await ck["get_payment_keys"](PLATEFORME, "card")
    verifier("A5. PLATEFORME -> cle d'environnement, paiement DISPONIBLE",
             err is None and cles and cles.get("stripe_secret_key") == "sk_test_env",
             "%s / %s" % (cles, err))

    cles, err = await ck["get_payment_keys"](PARTENAIRE, "card")
    verifier("B2. partenaire CONFIGURE -> SA cle, pas celle de la plateforme",
             err is None and cles and cles.get("stripe_secret_key") == "sk_live_partenaire",
             "%s / %s" % (cles, err))

    cles, err = await ck["get_payment_keys"]("inconnu@coach.ch", "card")
    verifier("C. partenaire NON configure -> ERREUR, aucun repli plateforme",
             cles is None and err and "non configur" in err.lower(), "%s / %s" % (cles, err))

    ck2 = caisse_reelle([{"coach_email": AUTRE, "stripe_enabled": False,
                          "stripe_secret_key": ""}])
    cles, err = await ck2["get_payment_keys"](AUTRE, "card")
    verifier("C2. partenaire connu mais Stripe desactive -> ERREUR explicite",
             cles is None and err and "carte" in err.lower(), "%s / %s" % (cles, err))

    cles, err = await ck["get_payment_keys"]("", "card")
    verifier("C3. chaine vide -> TOUJOURS refusee (la regle de la caisse ne bouge pas)",
             cles is None and err and "non configur" in err.lower(), "%s / %s" % (cles, err))

    ck3 = caisse_reelle([CONFIG_PARTENAIRE], env_stripe="")
    cles, err = await ck3["get_payment_keys"](PLATEFORME, "card")
    verifier("A6. plateforme SANS cle d'environnement -> erreur admin explicite",
             cles is None and err and "admin" in err.lower(), "%s / %s" % (cles, err))

    # ══════════════════════════════════════════════════════════════════════
    # NON-REGRESSION — ce que ce correctif ne doit PAS toucher
    # ══════════════════════════════════════════════════════════════════════
    _src_srv = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
    verifier("NR1. la vitrine garde SON endpoint, non modifie",
             '@api_router.post("/create-checkout-session")' in _src_srv)
    verifier("NR2. `get_payment_keys` n'est pas modifiee par ce lot",
             "Paiements non configurés. Le partenaire doit configurer ses méthodes de paiement."
             in _SRC_CK)
    # NR3 — la consigne du proprietaire : « ne hardcode pas une deuxieme fois
    # l'adresse si une fonction centrale existe ». On verifie donc que le
    # correctif s'appuie sur les briques du depot et n'ecrit AUCUNE adresse.
    _corr = ""
    for _n in ast.walk(ast.parse(_src_srv)):
        if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef)) and _n.name == "post_conversion_checkout":
            _corr = ast.get_source_segment(_src_srv, _n)
    verifier("NR3a. aucune adresse ecrite en dur dans la fonction corrigee",
             _corr and "contact.artboost" not in _corr, _corr[:120] or "(fonction introuvable)")
    verifier("NR3b. le correctif reutilise la constante plateforme du depot",
             "COACH_EMAIL" in _corr)
    verifier("NR3c. ... et le normaliseur central des trois formes de « sans proprietaire »",
             "lot2_proprietaire" in _corr)
    # LOT R / PULSE 150 : la garde de recharge n'est pas touchee.
    verifier("NR4. la garde LOT R reste en place dans la caisse",
             "_lotr_garde" in _SRC_CK)


def main():
    asyncio.run(scenarios())
    ok = sum(1 for _, c, _ in RESULTATS if c)
    for nom, cond, detail in RESULTATS:
        print(("  OK   " if cond else "  ECHEC") + "  " + nom
              + ("" if cond else "   -> %s" % (detail,)))
    print("\n=== P1-c vendeur : %d/%d ===" % (ok, len(RESULTATS)))
    print("Paiements REELS : 0 — aucune base, aucun reseau, aucune configuration ecrite.")
    sys.exit(0 if ok == len(RESULTATS) else 1)


if __name__ == "__main__":
    main()
