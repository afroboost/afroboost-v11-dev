#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V369 — bot WhatsApp à menu : priorités et garde-fous.

Test UNITAIRE hors ligne : base simulée en mémoire, AUCUNE connexion à MongoDB,
AUCUN appel réseau, AUCUN message envoyé.

CE QUI EST VERROUILLÉ
  1. ORDRE DES PRIORITÉS dans le webhook (vérifié sur le VRAI code source) :
     le STOP (V332) est traité AVANT le bot, et le bot avant le flux IA.
     Un « STOP » qui recevrait un menu marketing serait illégal, pas seulement gênant.
  2. Le bloc du bot est conditionné au drapeau BOT_MENU_ENABLED — tant qu'il est
     OFF, le webhook se comporte exactement comme avant.
  3. La liste blanche : seul le numéro du coach obtient une réponse pendant les tests.
  4. La PAUSE l'emporte : une personne en attente de rappel n'obtient plus rien,
     même en écrivant « menu ».
  5. Le créneau est repris TEL QUEL, sans interprétation (menu seul, jamais d'IA).
  6. Un message inconnu ramène au menu — l'IA n'est jamais appelée.

MODE D'EMPLOI
    python tests/test_bot_whatsapp.py
"""
import ast
import asyncio
import os
import re
import sys
from datetime import datetime, timedelta, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_BOT = os.path.join(RACINE, "api", "routes", "bot_whatsapp_routes.py")
SERVEUR = os.path.join(RACINE, "api", "server.py")

NOMS = {"_couper", "_formater_prix", "_bloc_tarifs", "_prochaine_seance",
        "construire_fiche_offre", "construire_fiche_cours", "lire_offre", "lire_un_cours",
        "_lien_offre", "lire_offre_du_cours", "construire_boutons_offre",
        "offre_payable_par_lien", "creer_lien_paiement", "_message_lien",
        "PREFIXE_PAYER", "MINUTES_REUTILISATION_LIEN",
        "lire_cours_de_offre", "LIEN_BOUTIQUE", "_LIBELLE_PALIER", "_cle_tri_cours", "_prix", "_sans_vrai_nom", "_dedoublonner_cours",
        "_cle_numero", "construire_menu_principal", "construire_liste_cours",
        "construire_liste_offres", "construire_repli", "construire_demande_creneau",
        "construire_confirmation_creneau", "construire_notification_coach",
        "numero_autorise", "lire_etat", "ecrire_etat", "en_pause", "decider_reponse",
        "lire_cours", "lire_offres", "JOURS", "SITE", "MAX_LIGNES_LISTE",
        "MAX_TITRE_LIGNE", "MAX_DESCRIPTION_LIGNE", "MAX_TITRE_BOUTON", "BOUTON_COURS",
        "BOUTON_OFFRES", "BOUTON_COACH", "ETAPE_ATTENTE_CRENEAU", "COLLECTION_ETAT",
        "JOURS_DE_PAUSE", "NUMEROS_AUTORISES"}


def _charger_bot():
    """Prélève les fonctions du VRAI module (il importe FastAPI, absent ici)."""
    src = open(MODULE_BOT, encoding="utf-8").read()
    arbre = ast.parse(src)
    gardes = [n for n in arbre.body
              if (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in NOMS)
              or (isinstance(n, ast.Assign)
                  and any(getattr(t, "id", None) in NOMS for t in n.targets))]
    silencieux = type("L", (), {"info": lambda *a, **k: None, "warning": lambda *a, **k: None,
                                "error": lambda *a, **k: None})()
    espace = {"re": re, "datetime": datetime, "timedelta": timedelta,
              "timezone": timezone, "logger": silencieux}
    exec(compile(ast.Module(body=gardes, type_ignores=[]), MODULE_BOT, "exec"), espace)
    return espace


# --- base simulée : rien ne sort de la mémoire du test ---
class _Curseur:
    def __init__(self, docs): self.docs = docs
    async def to_list(self, n): return self.docs[:n]


class _Collection:
    def __init__(self, docs=None): self.docs = docs or []
    def find(self, q=None, p=None): return _Curseur(self.docs)
    @staticmethod
    def _correspond(doc, cle, valeur):
        """Reproduit la sémantique MongoDB : un champ TABLEAU correspond si la
        valeur y figure. Sans ça, `find_one({"linked_course_ids": "c1"})` — la
        requête qui relie un cours à son offre — ne trouvait jamais rien."""
        champ = doc.get(cle)
        if isinstance(champ, list):
            return valeur in champ
        return champ == valeur

    async def find_one(self, q, p=None):
        for d in self.docs:
            if all(self._correspond(d, k, v) for k, v in q.items()):
                return dict(d)
        return None
    async def update_one(self, q, maj, upsert=False):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                d.update(maj.get("$set", {}))
                return
        if upsert:
            nd = dict(q)
            nd.update(maj.get("$set", {}))
            self.docs.append(nd)


class _Base:
    def __init__(self, bot_actif=True):
        self.courses = _Collection([
            {"id": "c1", "name": "Afroboost Silent", "weekday": 3, "time": "18:30",
             "locationName": "Auvernier", "visible": True, "archived": False}])
        self.offers = _Collection([
            {"id": "o1", "name": "Cours à l'unité", "price": 30.0,
             "description": "1h de cardio-danse afro, intense et joyeuse.", "visible": True,
             "linked_course_ids": ["c1"]},
            {"id": "o2", "name": "Événement à paliers", "price": 25.0, "visible": True,
             "progressive_pricing": True, "countdown_date": "", "countdown_time": "23:59",
             "early_bird_days_before": 7, "price_early_bird": 25.0,
             "price_standard": 33.0, "price_last_minute": 50.0,
             "description": "Soirée au bord du lac."}])
        self.feature_flags = _Collection([
            {"id": "feature_flags", "BOT_MENU_ENABLED": bot_actif}])
        self.etat = _Collection([])
    def __getitem__(self, nom):
        return self.etat if nom == "bot_whatsapp_etat" else _Collection([])


BOT = _charger_bot()
MOI = "+41765203363"
QUELQUUN_DAUTRE = "+41790000000"

echecs = 0


def verifier(titre, condition, detail=""):
    global echecs
    if condition:
        print(f"✅ PASS  {titre}")
    else:
        echecs += 1
        print(f"❌ FAIL  {titre}\n         → {detail}")


# ---------------------------------------------------------------- 1. ordre du webhook
def test_ordre_des_priorites_dans_le_webhook():
    src = open(SERVEUR, encoding="utf-8").read()
    pos_stop = src.find("await _v332_stop_whatsapp(")   # l'APPEL dans le webhook, pas la définition
    pos_bot = src.find("BOT À MENU DE BOUTONS")   # marqueur sans numéro de version
    pos_ia = src.find("[META-WEBHOOK] AI disabled")
    verifier("le STOP (V332) est traité AVANT le bot",
             0 < pos_stop < pos_bot, f"stop={pos_stop} bot={pos_bot}")
    verifier("le bot est branché AVANT le flux IA",
             0 < pos_bot < pos_ia, f"bot={pos_bot} ia={pos_ia}")
    # V369b : LA régression qui a coûté un test complet. Le bloc utilisait
    # `meta_contact_name` AVANT sa définition -> NameError avalé par le `except`,
    # et l'IA reprenait la main. Vérifier l'ordre STOP/bot/IA ne suffisait pas :
    # il faut que les variables utilisées soient DÉFINIES avant.
    pos_nom = src.find("meta_contact_name = None")
    verifier("les variables du bloc sont définies AVANT lui (NameError de V369)",
             0 < pos_nom < pos_bot,
             f"meta_contact_name défini en {pos_nom}, bloc du bot en {pos_bot}")
    verifier("les erreurs du bot ne sont plus silencieuses (trace exposée)",
             "DERNIERE_ERREUR" in src)
    verifier("le bloc du bot est conditionné au drapeau",
             "_bot_actif()" in src and "await _bot_actif() and _bot_numero_ok" in src)
    # On cherche des APPELS et des CHAÎNES, pas des mots : le module mentionne
    # « launch_campaign » dans un commentaire, précisément pour dire qu'il ne
    # l'utilise pas. Un simple `in` donnerait un faux positif.
    arbre_bot = ast.parse(open(MODULE_BOT, encoding="utf-8").read())
    appels, chaines = set(), set()
    for n in ast.walk(arbre_bot):
        if isinstance(n, ast.Call):
            f = n.func
            appels.add(getattr(f, "id", None) or getattr(f, "attr", None))
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            chaines.add(n.value)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                appels.add(a.name)
    verifier("le bot n'appelle NI launch_campaign NI le template des campagnes",
             "launch_campaign" not in appels
             and not any("afroboost_campagne" in c for c in chaines),
             f"appels suspects={appels & {'launch_campaign'}}")


# ---------------------------------------------------------------- 2. liste blanche
def test_liste_blanche():
    verifier("le numéro du coach est autorisé", BOT["numero_autorise"](MOI) is True)
    verifier("tout autre numéro est refusé",
             BOT["numero_autorise"](QUELQUUN_DAUTRE) is False,
             "un abonné recevrait un message pendant la phase de test")
    verifier("le format local du même numéro est reconnu",
             BOT["numero_autorise"]("0765203363") is True)


# ---------------------------------------------------------------- 3. décisions
def test_decisions():
    async def scenario():
        BOT["db"] = _Base()
        d = BOT["decider_reponse"]

        rep, notif = await d(MOI, "bonjour", "", "Bassi")
        verifier("« bonjour » -> menu à 3 boutons",
                 rep and len(rep["interactive"]["action"]["buttons"]) == 3)

        rep, _ = await d(MOI, "", BOT["BOUTON_COURS"], "Bassi")
        verifier("clic « Nos cours » -> liste de cours",
                 rep and rep["interactive"]["type"] == "list")

        rep, _ = await d(MOI, "n'importe quoi", "", "Bassi")
        verifier("message inconnu -> repli vers le menu, jamais l'IA",
                 rep and rep["type"] == "text" and "coach" in rep["text"]["body"])

        rep, _ = await d(MOI, "", BOT["BOUTON_COACH"], "Bassi")
        verifier("clic « Parler à un coach » -> demande de créneau",
                 rep and "rappelé" in rep["text"]["body"])

        rep, notif = await d(MOI, "mardi vers 18h si possible", "", "Bassi")
        verifier("le créneau est repris TEL QUEL, sans interprétation",
                 rep and "mardi vers 18h si possible" in rep["text"]["body"])
        verifier("le coach est notifié (push + messagerie)",
                 notif and "mardi vers 18h si possible" in notif["push"]["corps"]
                 and "+41765203363" in notif["message_messagerie"])

        rep, _ = await d(MOI, "bonjour ?", "", "Bassi")
        verifier("APRÈS la demande, la PAUSE impose le silence",
                 rep is None, "le bot a répondu alors qu'il devait se taire")

        rep, _ = await d(MOI, "menu", "", "Bassi")
        verifier("« menu » ne contourne pas la pause", rep is None)

        etat = BOT["db"].etat.docs[0]
        verifier("l'état contient le créneau et la fin de pause",
                 etat.get("creneau_demande") == "mardi vers 18h si possible"
                 and etat.get("pause_jusqu_a"), str(etat))
        verifier("la pause dure 7 jours",
                 BOT["JOURS_DE_PAUSE"] == 7, str(BOT["JOURS_DE_PAUSE"]))
    asyncio.run(scenario())


# ---------------------------------------------------------------- 4. fiches détaillées
def test_fiches_detaillees():
    """Sélectionner une ligne doit donner le message COMPLET, pas la version coupée."""
    async def scenario():
        BOT["db"] = _Base()
        d = BOT["decider_reponse"]

        rep, _ = await d(MOI, "", "offre_o1", "Bassi")
        # V372 : la sélection d'une offre renvoie DEUX messages — la fiche, puis
        # les boutons. La fiche est le premier.
        fiche = rep[0] if isinstance(rep, list) else rep
        corps = fiche["text"]["body"]
        verifier("le lien de l'offre pointe sur l'offre précise, pas la boutique",
                 "?offre=o1" in corps and "#offers-slider" not in corps, corps[-120:])
        verifier("sélection d'une offre -> fiche complète (nom, prix, description, lien)",
                 "Cours à l'unité" in corps and "30 CHF" in corps
                 and "cardio-danse afro, intense et joyeuse" in corps
                 and "afroboost.com" in corps, corps[:120])
        verifier("la fiche n'est pas tronquée par « … »",
                 "…" not in corps, corps[:160])
        verifier("l'aperçu de lien est activé", fiche["text"].get("preview_url") is True)
        verifier("la fiche tient sous la limite WhatsApp (4096)", len(corps) <= 4000, len(corps))

        rep, _ = await d(MOI, "", "cours_c1", "Bassi")
        corps = rep["text"]["body"]
        verifier("sélection d'un cours -> fiche complète (nom, jour, lieu, lien)",
                 "Afroboost Silent" in corps and "Auvernier" in corps
                 and "afroboost.com" in corps, corps[:120])
        # V371 : le cours c1 est rattaché à l'offre o1 -> il hérite de sa description
        verifier("un cours rattaché hérite de la description de son offre",
                 "cardio-danse afro, intense et joyeuse" in corps
                 and "Détail de l'offre" in corps, corps[:200])
        verifier("le lien mène DIRECTEMENT à l'offre (?offre=<id>)",
                 "?offre=o1" in corps, corps[-120:])

        # Paliers : countdown_date VIDE -> ne PAS annoncer des tarifs inapplicables
        rep, _ = await d(MOI, "", "offre_o2", "Bassi")
        corps = (rep[0] if isinstance(rep, list) else rep)["text"]["body"]
        verifier("paliers non annoncés quand la date de référence manque",
                 "Dernière minute" not in corps and "25 CHF" in corps,
                 "le client verrait des prix qui ne s'appliquent jamais")

        # V371 : un cours SANS offre ne doit pas provoquer d'erreur ni de ligne vide
        BOT["db"].courses.docs.append({"id": "orphelin", "name": "Cours orphelin",
                                       "weekday": 0, "time": "10:00",
                                       "locationName": "Plage", "visible": True})
        rep, _ = await d(MOI, "", "cours_orphelin", "Bassi")
        corps = rep["text"]["body"]
        verifier("un cours orphelin s'affiche sans erreur et sans description",
                 "Cours orphelin" in corps and "Détail de l'offre" not in corps
                 and "None" not in corps, corps[:160])

        rep, _ = await d(MOI, "", "offre_inconnue", "Bassi")
        verifier("identifiant inconnu -> repli, jamais d'erreur",
                 rep and (rep[0] if isinstance(rep, list) else rep)["type"] == "text")
    asyncio.run(scenario())


# ------------------------------------------------- 5. paiement : aucune fausse session
def test_paiement_aucune_fausse_transaction():
    """LA garantie : consulter des offres ne crée AUCUNE session Stripe.

    Le compteur d'appels ci-dessous remplace `create_checkout_session` : il compte
    exactement combien de fois Stripe aurait été sollicité. Une ligne
    `payment_transactions` naît à CHAQUE appel — d'où l'importance de ne le faire
    qu'au clic explicite sur « Réserver et payer ».
    """
    async def scenario():
        BOT["db"] = _Base()
        BOT["db"].offers.docs.append(
            {"id": "ovar", "name": "T-shirt", "price": 59.99, "visible": True,
             "variants": {"taille": ["S", "M"]}, "description": "T-shirt Afroboost"})
        BOT["db"].offers.docs.append(
            {"id": "ogratuit", "name": "Cours d'essai", "price": 0.0, "visible": True,
             "description": "Essai gratuit"})
        d = BOT["decider_reponse"]

        appels = {"n": 0}

        async def faux_stripe(requete):
            appels["n"] += 1
            return {"url": f"https://checkout.stripe.com/c/pay/cs_test_{appels['n']}"}

        # On remplace l'appel réel : le test ne contacte jamais Stripe.
        import types, sys
        faux_module = types.ModuleType("api.server")
        faux_module.create_checkout_session = faux_stripe
        faux_module.CreateCheckoutRequest = lambda **kw: kw
        sys.modules["api.server"] = faux_module
        faux_pricing = types.ModuleType("api.pricing")
        faux_pricing.compute_active_price = lambda o, now=None: {
            "price": float(o.get("price") or 0), "tier": "regular"}
        sys.modules["api.pricing"] = faux_pricing

        # 1) CINQ fiches consultées -> AUCUN appel
        for _ in range(5):
            await d(MOI, "", "offre_o1", "Bassi")
        verifier("consulter 5 fiches ne crée AUCUNE session Stripe",
                 appels["n"] == 0, f"{appels['n']} appel(s)")

        # 2) la fiche est bien suivie de boutons
        rep, _ = await d(MOI, "", "offre_o1", "Bassi")
        verifier("la fiche est suivie d'un message à boutons",
                 isinstance(rep, list) and len(rep) == 2
                 and rep[1]["interactive"]["type"] == "button", str(type(rep)))
        titre = rep[1]["interactive"]["action"]["buttons"][0]["reply"]["title"]
        verifier("le bouton d'une offre payante propose de payer",
                 "payer" in titre.lower(), titre)

        # 3) UN clic « payer » -> EXACTEMENT un appel
        rep, _ = await d(MOI, "", "payer_o1", "Bassi")
        verifier("un clic « Réserver et payer » crée exactement 1 session",
                 appels["n"] == 1, f"{appels['n']} appel(s)")
        corps = rep["text"]["body"]
        verifier("le message porte le lien Stripe et ses conditions",
                 "checkout.stripe.com" in corps and "24 h" in corps
                 and "usage unique" in corps, corps[:140])

        # 4) re-clic dans l'heure -> lien RÉUTILISÉ, aucun appel de plus
        rep, _ = await d(MOI, "", "payer_o1", "Bassi")
        verifier("re-cliquer dans l'heure réutilise le lien (pas de doublon)",
                 appels["n"] == 1 and "cs_test_1" in rep["text"]["body"],
                 f"{appels['n']} appel(s)")

        # 5) offre GRATUITE -> aucun appel, renvoi vers le site
        rep, _ = await d(MOI, "", "payer_ogratuit", "Bassi")
        verifier("offre gratuite : aucune session Stripe, renvoi vers le site",
                 appels["n"] == 1 and "?offre=ogratuit" in rep["text"]["body"],
                 rep["text"]["body"][:120])

        # 6) offre à VARIANTES -> aucun appel
        rep, _ = await d(MOI, "", "payer_ovar", "Bassi")
        verifier("offre à variantes : aucune session Stripe, renvoi vers le site",
                 appels["n"] == 1 and "?offre=ovar" in rep["text"]["body"],
                 rep["text"]["body"][:120])

        rep, _ = await d(MOI, "", "offre_ogratuit", "Bassi")
        titre = rep[1]["interactive"]["action"]["buttons"][0]["reply"]["title"]
        verifier("le bouton d'une offre gratuite dit « Voir sur le site »",
                 "site" in titre.lower(), titre)
    asyncio.run(scenario())


if __name__ == "__main__":
    test_ordre_des_priorites_dans_le_webhook()
    test_paiement_aucune_fausse_transaction()
    test_fiches_detaillees()
    test_liste_blanche()
    test_decisions()
    print("\nV369 :", "tous les tests passent" if not echecs else f"{echecs} échec(s)")
    sys.exit(1 if echecs else 0)
