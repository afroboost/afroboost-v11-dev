#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V455 — la pause ne doit plus emprisonner la conversation.

CE QUI S'EST PASSE, mesure en production le 26/08/2026 (logs + base) :
  15:56:51  « Hi »          -> accepte comme creneau. `creneau_demande = 'Hi'`,
                              notification au coach, et PAUSE DE 7 JOURS posee.
  15:57:22  clic « Nos cours » -> [BOT-WA] silence (pause active)
  15:57:55  « ? »              -> silence
  15:58:04  « Hello »          -> silence
Tous les webhooks etaient recus, toutes les signatures V453 valides : le bot a
CHOISI de se taire. Le test de pause etait la PREMIERE instruction de
`decider_reponse`, avant meme la branche des boutons.

DEUX DEFAUTS DISTINCTS, DEUX CORRECTIFS :
  A. la pause faisait taire AUSSI les actions globales ;
  B. n'importe quel texte non vide valait un horaire (« Hi » compris).

DECISIONS DU COACH (26/08/2026), verrouillees ici :
  1. une action globale (clic de bouton, ou le mot « menu ») repond TOUJOURS,
     pause ou non — mais elle NE LEVE PAS la pause : le relais humain reste
     protege, seul le texte libre est silencieux ;
  2. « quand tu veux », « n'importe quand », « des que possible » sont de VRAIES
     reponses : on les enregistre comme disponibilite FLEXIBLE, jamais comme un
     faux horaire ;
  3. premiere reponse invalide -> on repose la question avec des exemples ;
     deuxieme consecutive -> on abandonne proprement et on propose le menu.
     Jamais de boucle.

Test UNITAIRE hors ligne : AUCUNE connexion MongoDB, AUCUN appel reseau,
AUCUN message envoye.

    python tests/test_v455_pause_et_creneau.py
"""
import ast
import asyncio
import os
import re
import sys
import types
from datetime import datetime, timedelta, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_BOT = os.path.join(RACINE, "api", "routes", "bot_whatsapp_routes.py")
SERVEUR = os.path.join(RACINE, "api", "server.py")

SRC_BOT = open(MODULE_BOT, encoding="utf-8").read()
SRC_SERVEUR = open(SERVEUR, encoding="utf-8").read()


def _charger():
    """Preleve du VRAI module tout ce qui n'exige pas FastAPI."""
    arbre = ast.parse(SRC_BOT)
    gardes = []
    for n in arbre.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # on ecarte uniquement les routes HTTP (decorateurs @bot_router)
            if any(isinstance(d, ast.Call) and getattr(getattr(d, "func", None), "attr", "")
                   in ("get", "post") for d in n.decorator_list):
                continue
            gardes.append(n)
        elif isinstance(n, ast.Assign):
            gardes.append(n)
    silencieux = type("L", (), {"info": lambda *a, **k: None,
                                "warning": lambda *a, **k: None,
                                "error": lambda *a, **k: None})()
    # Le module cree son propre `logger` et son `APIRouter` au chargement. On
    # fournit des doubles muets plutot que d'ecarter ces lignes : on veut executer
    # le VRAI fichier, pas une version amputee.
    faux_logging = types.SimpleNamespace(getLogger=lambda *a, **k: silencieux)
    espace = {"re": re, "datetime": datetime, "timedelta": timedelta,
              "timezone": timezone, "logger": silencieux, "os": os,
              "logging": faux_logging, "__name__": "bot_whatsapp_routes",
              "APIRouter": lambda **k: types.SimpleNamespace(
                  get=lambda *a, **k: (lambda f: f),
                  post=lambda *a, **k: (lambda f: f)),
              "HTTPException": Exception, "Request": object}
    exec(compile(ast.Module(body=gardes, type_ignores=[]), MODULE_BOT, "exec"), espace)
    return espace


BOT = _charger()

# `lire_occurrences` importe `api.server` a l'execution (import paresseux V454).
_AGENDA = [
    {"course_id": "c1", "name": "Cours à l'unité", "weekday": 2, "time": "18:30",
     "locationName": "Auvernier", "datetime": "2026-09-02T18:30:00",
     "date": "2026-09-02", "offers": [{"id": "o1", "name": "Cours à l'unité"}],
     "recurrent": True},
]


async def _faux_agenda(days=60):
    return {"occurrences": list(_AGENDA), "jours": days}


_faux = types.ModuleType("api.server")
_faux._agenda_occurrences = _faux_agenda
sys.modules.setdefault("api", types.ModuleType("api"))
sys.modules["api.server"] = _faux


# --- base simulee : rien ne sort de la memoire du test ---
class _Curseur:
    def __init__(self, docs): self.docs = docs
    async def to_list(self, n): return self.docs[:n]


class _Collection:
    def __init__(self, docs=None): self.docs = docs or []
    def find(self, q=None, p=None): return _Curseur(self.docs)
    async def find_one(self, q, p=None):
        for d in self.docs:
            if all((v in d.get(k)) if isinstance(d.get(k), list) else d.get(k) == v
                   for k, v in q.items()):
                return dict(d)
        return None
    async def update_one(self, q, maj, upsert=False):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                d.update(maj.get("$set", {}))
                return
        if upsert:
            nd = dict(q); nd.update(maj.get("$set", {})); self.docs.append(nd)


class _Base:
    def __init__(self, etat=None):
        self.offers = _Collection([
            {"id": "o1", "name": "Cours à l'unité", "price": 30.0, "visible": True,
             "description": "1h de cardio-danse.", "linked_course_ids": ["c1"]}])
        self.courses = _Collection([
            {"id": "c1", "name": "Cours à l'unité", "weekday": 3, "time": "18:30",
             "locationName": "Auvernier", "visible": True, "archived": False}])
        self.etat = _Collection([dict(etat)] if etat else [])
    def __getitem__(self, nom):
        return self.etat if nom == "bot_whatsapp_etat" else _Collection([])


MOI = "+41765203363"
DANS_5_JOURS = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()

echecs = 0


def verifier(titre, condition, detail=""):
    global echecs
    if condition:
        print("✅ PASS  %s" % titre)
    else:
        echecs += 1
        print("❌ FAIL  %s\n         → %s" % (titre, detail))


def jouer(etat, texte="", bouton=""):
    """Rejoue UN message et renvoie (reponse, notif, etat_final)."""
    base = _Base(etat)
    BOT["db"] = base
    rep, notif = asyncio.new_event_loop().run_until_complete(
        BOT["decider_reponse"](MOI, texte, bouton, "Bassi"))
    final = base.etat.docs[0] if base.etat.docs else {}
    return rep, notif, final


EN_PAUSE = {"telephone": MOI, "etape": "", "creneau_demande": "Hi",
            "pause_jusqu_a": DANS_5_JOURS}
ATTEND = {"telephone": MOI, "etape": "attente_creneau"}


# ============================================== 1. LA PAUSE N'EMPRISONNE PLUS
def test_pause_clic_nos_cours():
    rep, _, fin = jouer(EN_PAUSE, "📅 Nos cours", BOT["BOUTON_COURS"])
    verifier("1. pause active + clic « Nos cours » -> la liste part",
             rep is not None and rep.get("interactive", {}).get("type") == "list",
             "rep=%r" % (rep,))
    verifier("1. le clic NE LEVE PAS la pause (relais humain protege)",
             fin.get("pause_jusqu_a") == DANS_5_JOURS,
             "pause_jusqu_a=%r" % fin.get("pause_jusqu_a"))


def test_pause_clic_nos_offres():
    rep, _, _ = jouer(EN_PAUSE, "🛍️ Nos offres", BOT["BOUTON_OFFRES"])
    verifier("1. pause active + clic « Nos offres » -> une reponse part",
             rep is not None and rep.get("interactive", {}).get("type") == "list",
             "rep=%r" % (rep,))


def test_pause_mot_menu():
    rep, _, _ = jouer(EN_PAUSE, "menu", "")
    verifier("1. pause active + « menu » -> le menu revient",
             rep is not None and len(rep.get("interactive", {})
                                     .get("action", {}).get("buttons", [])) == 3,
             "rep=%r" % (rep,))


def test_pause_texte_libre_reste_silencieux():
    for libre in ("ok merci", "Hello", "je serai là", "?"):
        rep, notif, _ = jouer(EN_PAUSE, libre, "")
        verifier("1. pause active + texte libre « %s » -> SILENCE" % libre,
                 rep is None and notif is None, "rep=%r" % (rep,))


def test_pause_clic_ligne_de_liste():
    """Sans cela, cliquer une ligne de la liste obtenue pendant la pause
    retomberait dans le silence : la liste serait decorative."""
    rep, _, _ = jouer(EN_PAUSE, "Cours à l'unité", BOT["PREFIXE_OCCURRENCE"] + "c1__2026-09-02T18:30")
    verifier("1. pause active + clic sur une ligne -> la fiche part",
             rep is not None and rep.get("type") == "text", "rep=%r" % (rep,))


# ============================================== 2. VALIDATION DU CRENEAU
def test_creneau_invalide_ne_cree_rien():
    for mauvais in ("Hi", "?", "Hello", "cours"):
        rep, notif, fin = jouer(ATTEND, mauvais, "")
        verifier("2. « %s » -> AUCUNE demande de rappel creee" % mauvais,
                 notif is None and not fin.get("creneau_demande")
                 and not fin.get("pause_jusqu_a"),
                 "notif=%s creneau=%r pause=%r" % (notif is not None,
                                                   fin.get("creneau_demande"),
                                                   fin.get("pause_jusqu_a")))
        verifier("2. « %s » -> la question est reposee" % mauvais,
                 rep is not None and rep.get("type") == "text", "rep=%r" % (rep,))


def test_creneau_precis_accepte():
    for bon in ("mercredi 18h", "demain vers 18h", "vendredi matin", "ce soir"):
        rep, notif, fin = jouer(ATTEND, bon, "")
        verifier("2. « %s » -> demande de rappel CREEE" % bon,
                 notif is not None and fin.get("creneau_demande") == bon
                 and fin.get("pause_jusqu_a"),
                 "notif=%s creneau=%r" % (notif is not None, fin.get("creneau_demande")))
        verifier("2. « %s » -> enregistre comme horaire PRECIS" % bon,
                 fin.get("creneau_flexible") is not True,
                 "creneau_flexible=%r" % fin.get("creneau_flexible"))


def test_creneau_flexible_accepte_comme_flexible():
    for souple in ("quand tu veux", "n'importe quand", "dès que possible",
                   "peu importe l'heure"):
        rep, notif, fin = jouer(ATTEND, souple, "")
        verifier("2. « %s » -> demande CREEE" % souple,
                 notif is not None and fin.get("creneau_demande") == souple,
                 "notif=%s creneau=%r" % (notif is not None, fin.get("creneau_demande")))
        verifier("2. « %s » -> marquee DISPONIBILITE FLEXIBLE" % souple,
                 fin.get("creneau_flexible") is True,
                 "creneau_flexible=%r" % fin.get("creneau_flexible"))


# ============================================== 3. PAS DE BOUCLE
def test_deux_invalides_ramenent_au_menu():
    r1, n1, f1 = jouer(ATTEND, "Hi", "")
    verifier("3. 1re invalide -> on repose la question, l'attente CONTINUE",
             f1.get("etape") == "attente_creneau" and n1 is None,
             "etape=%r" % f1.get("etape"))
    f1["telephone"] = MOI
    r2, n2, f2 = jouer(f1, "??", "")
    charges = r2 if isinstance(r2, list) else [r2]
    a_le_menu = any(len((c or {}).get("interactive", {})
                        .get("action", {}).get("buttons", [])) == 3 for c in charges)
    verifier("3. 2e invalide consecutive -> le MENU est propose", a_le_menu,
             "r2=%r" % (r2,))
    verifier("3. 2e invalide -> l'attente est ABANDONNEE (pas de boucle)",
             f2.get("etape") != "attente_creneau", "etape=%r" % f2.get("etape"))
    verifier("3. 2e invalide -> toujours AUCUNE demande creee",
             n2 is None and not f2.get("creneau_demande"),
             "creneau=%r" % f2.get("creneau_demande"))


def test_un_creneau_valide_remet_le_compteur_a_zero():
    _, _, f1 = jouer(ATTEND, "Hi", "")
    f1["telephone"] = MOI
    _, notif, f2 = jouer(f1, "mercredi 18h", "")
    verifier("3. invalide PUIS valide -> la demande est bien creee",
             notif is not None and f2.get("creneau_demande") == "mercredi 18h",
             "creneau=%r" % f2.get("creneau_demande"))
    verifier("3. le compteur d'essais est remis a zero",
             not f2.get("creneau_essais"), "essais=%r" % f2.get("creneau_essais"))


# ============================================== 4. NON-REGRESSION
def test_parcours_normal_intact():
    rep, _, fin = jouer({"telephone": MOI}, "", BOT["BOUTON_COACH"])
    verifier("4. clic « Parler à un coach » -> question posee, attente armee",
             rep and "rappelé" in rep["text"]["body"]
             and fin.get("etape") == "attente_creneau", "rep=%r" % (rep,))
    rep, _, _ = jouer({"telephone": MOI}, "bonjour", "")
    verifier("4. hors pause, « bonjour » -> menu (inchange)",
             rep and len(rep["interactive"]["action"]["buttons"]) == 3)
    rep, _, _ = jouer({"telephone": MOI}, "", BOT["BOUTON_COURS"])
    verifier("4. V454 intact : « Nos cours » rend toujours une liste",
             rep and rep["interactive"]["type"] == "list")


def test_perimetre_du_lot():
    verifier("5. V453/HMAC intact — la garde reste dans server.py",
             "_v453_signature_refusee" in SRC_SERVEUR and "X-Hub-Signature-256" in SRC_SERVEUR)
    # On compare DANS le handler, pas dans le fichier entier : « bot_whatsapp_routes
    # import » apparait aussi en tete de server.py, et la comparaison globale
    # mesurait alors deux endroits sans rapport.
    _h = SRC_SERVEUR[SRC_SERVEUR.index("async def handle_meta_whatsapp_webhook"):]
    _h = _h[:_h.index("\n@api_router")] if "\n@api_router" in _h else _h
    verifier("5. STOP intact — traite dans le webhook AVANT le bot",
             _h.index("_v332_stop_whatsapp(from_phone") < _h.index("bot_whatsapp_routes import"),
             "STOP=%d bot=%d" % (_h.index("_v332_stop_whatsapp(from_phone"),
                                 _h.index("bot_whatsapp_routes import")))
    verifier("5. V453 refuse AVANT tout le reste dans le webhook",
             _h.index("_v453_signature_refusee") < _h.index("_v332_stop_whatsapp(from_phone"))
    verifier("5. V454 intact — le bot consomme toujours l'agenda du site",
             "_agenda_occurrences" in SRC_BOT and "construire_liste_occurrences" in SRC_BOT)
    for interdit, libelle in (("launch_campaign(", "campagnes"),
                              ("registre_stop", "registre STOP"),
                              ("courses.update", "donnees cours"),
                              ("courses.delete", "suppression cours")):
        verifier("5. le bot ne touche pas a %s" % libelle, interdit not in SRC_BOT)


def principal():
    for essai in (test_pause_clic_nos_cours, test_pause_clic_nos_offres,
                  test_pause_mot_menu, test_pause_texte_libre_reste_silencieux,
                  test_pause_clic_ligne_de_liste,
                  test_creneau_invalide_ne_cree_rien, test_creneau_precis_accepte,
                  test_creneau_flexible_accepte_comme_flexible,
                  test_deux_invalides_ramenent_au_menu,
                  test_un_creneau_valide_remet_le_compteur_a_zero,
                  test_parcours_normal_intact, test_perimetre_du_lot):
        try:
            essai()
        except Exception as e:
            verifier(essai.__name__, False, "%s: %s" % (type(e).__name__, e))
    print("=" * 78)
    print("Reseau : 0   |   Base : 0   |   Envois WhatsApp : 0")
    if echecs:
        print("%d ECHEC(S)" % echecs)
        sys.exit(1)
    print("TOUT EST VERT")


if __name__ == "__main__":
    principal()
