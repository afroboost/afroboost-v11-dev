# -*- coding: utf-8 -*-
"""V440 (M1) — tests hors ligne. Aucune base, aucun reseau, aucun WhatsApp envoye.

Les fonctions testees sont EXTRAITES du vrai `api/server.py` (via AST), pas
recopiees : si le code change, le test suit. `_lien_offre` est extraite de
`api/routes/bot_whatsapp_routes.py`, car c'est la SEULE fabrique d'URL d'offre
du depot — la tester ailleurs prouverait le contraire de ce qu'on veut prouver.
"""
import ast, os, re, sys, unicodedata
from datetime import datetime, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(RACINE, "api", "server.py")
SRC_BOT = os.path.join(RACINE, "api", "routes", "bot_whatsapp_routes.py")

# V440b : `compute_active_price` est IMPORTEE du vrai module de tarification —
# le meme que celui du site et du checkout. Le recopier ici prouverait que le
# test suit une copie, pas la verite. `api/pricing.py` est un module PUR : il
# n'ouvre aucune connexion base, donc il s'importe sans effet de bord.
sys.path.insert(0, RACINE)
from api.pricing import compute_active_price

A_EXTRAIRE = {"v440_normaliser", "v440_singulier", "v440_mots", "v440_score_offre",
              "v440_offre_certaine", "v440_urls_autorisees", "v440_garde_urls",
              "v440_contexte_metier", "v440_visible", "v440_prix_actif",
              "v440_prix_lisible"}
CONSTANTES = {"V440_MONO_COACH", "V440_MAX_HISTORIQUE", "V440_SEUIL_SCORE",
              "V440_MARGE_SCORE", "V440_SITE", "V440_MOTS_IGNORES"}
# Cote bot : la fabrique d'URL et ses deux constantes.
A_EXTRAIRE_BOT = {"_lien_offre"}
CONSTANTES_BOT = {"SITE", "LIEN_BOUTIQUE"}


def morceaux(chemin, fonctions, constantes):
    src = open(chemin, encoding="utf-8").read()
    out = []
    for n in ast.parse(src).body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in fonctions:
            out.append(ast.get_source_segment(src, n))
        elif isinstance(n, ast.Assign):
            for c in n.targets:
                if isinstance(c, ast.Name) and c.id in constantes:
                    out.append(ast.get_source_segment(src, n))
    return out


class _JournalMuet:
    def warning(self, *a, **k): pass
    def info(self, *a, **k): pass
    def error(self, *a, **k): pass


NS = {"re": re, "_v440_ud": unicodedata,
      "compute_active_price": compute_active_price, "logger": _JournalMuet()}
exec("\n\n".join(morceaux(SRC_BOT, A_EXTRAIRE_BOT, CONSTANTES_BOT)), NS)
# `_lien_offre` est importee dans server.py sous le nom `v440_lien_offre` :
# on reproduit exactement cet alias, sinon le contexte ne saurait pas la nommer.
NS["v440_lien_offre"] = NS["_lien_offre"]
exec("\n\n".join(morceaux(SRC, A_EXTRAIRE, CONSTANTES)), NS)
manquantes = [f for f in (A_EXTRAIRE | A_EXTRAIRE_BOT) if f not in NS]
assert not manquantes, "extraction incomplete : %s" % manquantes

MOTS = NS["v440_mots"]
CERTAINE = NS["v440_offre_certaine"]
AUTORISEES = NS["v440_urls_autorisees"]
GARDE = NS["v440_garde_urls"]
CONTEXTE = NS["v440_contexte_metier"]
LIEN = NS["v440_lien_offre"]
SITE = NS["V440_SITE"]

# === Les VRAIES offres de production, relevees le 14/08/2026 =================
# Y compris leurs mots-cles quasi identiques : c'est precisement ce qui rend
# l'abstention indispensable, et un jeu de donnees invente le masquerait.
_CLES_COMMUNES = ("afrobeat, fitness, danse afro, fitness, cours, afrobeat fitness ,"
                  "danse, cardio, danse cours, fun, sport, ludique, entraînement, "
                  "remise en forme ")
PULSE = {"id": "a687ce86-94d6-4ba9-a847-c8a20e787491", "name": "PULSE x10 cours",
         "price": 250.0, "keywords": _CLES_COMMUNES, "isProduct": False}
UNITE = {"id": "fea0ab6a-8adc-460d-9d7d-bbff57059ca5", "name": "Cours à l'unité",
         "price": 30.0, "keywords": "Cours, session,  séances, séance, fitness, danse, dance, tanze, cardio, sport",
         "isProduct": False}
TSHIRT = {"id": "84b7d8c6-b859-410a-8a09-0d1ee0069404", "name": "T-shirt + 1 cours offert!",
          "price": 59.99, "keywords": "Shirt, t-shirt, vêtement", "isProduct": True}
# V440b : l'offre du LAAF Festival, avec sa tarification progressive REELLE.
# `price` vaut 0.0 — c'est une SENTINELLE, pas une gratuite. Le vrai tarif est
# dans les trois paliers, et c'est tout l'objet de ce lot.
CASQUE = {"id": "76a78f31-614a-415a-876b-9d2d1a4b441c",
          "name": " Afroboost Silent avec Bassi Le prix du billet correspond à la réservation du casque Silent (cours offert).",
          "price": 0.0, "keywords": _CLES_COMMUNES, "isProduct": False,
          "visible": True, "progressive_pricing": True,
          "countdown_date": "2026-08-21", "countdown_time": "18:30",
          "early_bird_days_before": 7, "standard_hours_before": 24,
          "price_early_bird": 10.0, "price_standard": 15.0, "price_last_minute": 25.0}
MEMBRES = {"id": "484c4519-15dc-4b86-8aa3-48e3c01c9645", "name": "Membres",
           "price": 150.0, "keywords": _CLES_COMMUNES, "isProduct": False}
OFFRES = [PULSE, UNITE, TSHIRT, CASQUE, MEMBRES]

# Doublon REEL, masque par le coach : il ne doit JAMAIS etre propose.
VIDY = {"id": "184e76e0-d3a0-4ba4-b63e-a6eb773bf8d7",
        "name": "Silent Dance & Fitness au bord du Lac de Vidy – Lausanne",
        "price": 25.0, "keywords": "silent, casque, lausanne, vidy",
        "isProduct": False, "visible": False}
# Une offre VRAIMENT gratuite (prix plat 0, aucune tarification progressive).
GRATUITE = {"id": "11111111-1111-1111-1111-111111111111", "name": "Portes ouvertes découverte",
            "price": 0.0, "keywords": "portesouvertes", "isProduct": False, "visible": True}

# Bornes de palier de l'offre du festival : reference = 21/08 18:30 UTC,
# early_bird_days_before = 7 -> bascule le 14/08 a 18:30 ; standard_hours_before
# = 24 -> bascule le 20/08 a 18:30.
T_EARLY = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)          # avant
T_LIMITE_MOINS = datetime(2026, 8, 14, 18, 29, 59, tzinfo=timezone.utc)
T_LIMITE_PILE = datetime(2026, 8, 14, 18, 30, 0, tzinfo=timezone.utc)  # la limite
T_STANDARD = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)       # apres
T_LM_MOINS = datetime(2026, 8, 20, 18, 29, 59, tzinfo=timezone.utc)
T_LM_PILE = datetime(2026, 8, 20, 18, 30, 0, tzinfo=timezone.utc)
T_APRES = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)          # evenement passe

resultats = []


def verifier(nom, obtenu, attendu):
    resultats.append((obtenu == attendu, nom, obtenu, attendu))


def verifier_vrai(nom, condition, detail=""):
    resultats.append((bool(condition), nom, detail or condition, True))


# === 1. Hypothese mono-coach, ecrite et testable ============================
verifier("hypothese mono-coach explicite", NS["V440_MONO_COACH"], True)

# === 2. Normalisation et extraction de mots =================================
verifier("accents ignores", NS["v440_normaliser"]("Casqué Silent"), "casque silent")
verifier("majuscules ignorees", NS["v440_normaliser"]("TWINT"), "twint")
verifier_vrai("« twint » n'est pas un mot d'offre", "twint" not in MOTS("payer par twint"))
verifier_vrai("« payer » n'est pas un mot d'offre", "payer" not in MOTS("je veux payer"))
verifier_vrai("« casque » est retenu", "casque" in MOTS("mon casque"))
verifier_vrai("mots de 3 lettres ecartes", "les" not in MOTS("les cours"))

# === 3. Les 5 formulations imposees, SANS contexte d'offre ==================
# Aucune ne doit elire une offre : elles ne parlent d'aucune offre precise.
FORMULATIONS = [
    "Puis-je payer par twint ?",
    "Je peux payer avec TWINT ?",
    "Comment payer ?",
    "Twint marche ?",
    "puis je payer par TwInT",          # majuscules melangees
    "Puis-je payer par twinter?",        # faute
    "je peux payer par tw int",          # coupure
    "Vous acceptez Twint",
]
_elues = [(t, CERTAINE(t, OFFRES)[0]) for t in FORMULATIONS]
verifier("aucune formulation seule n'elit une offre",
         [t for t, o in _elues if o is not None], [])
# ... et le contexte produit pour chacune ne contient AUCUN lien d'offre.
_fuites = []
for _t, _o in _elues:
    _offre_t, _motif_t = CERTAINE(_t, OFFRES)
    _ctx_t = CONTEXTE(OFFRES, _offre_t, _motif_t)
    if "OFFRE CONCERNÉE" in _ctx_t:
        _fuites.append(_t)
verifier("aucune formulation seule ne produit un lien cible", _fuites, [])

verifier("« Je veux payer mon casque par Twint » -> l'offre casque",
         (CERTAINE("Je veux payer mon casque par Twint", OFFRES)[0] or {}).get("id"),
         CASQUE["id"])
verifier("« je voudrais un t-shirt » -> l'offre t-shirt",
         (CERTAINE("je voudrais un t-shirt", OFFRES)[0] or {}).get("id"),
         TSHIRT["id"])

# === 4. Ambiguite : jamais de choix arbitraire ==============================
# « cours » figure dans 4 offres sur 5 : l'egalite doit produire None.
_o, _motif = CERTAINE("je veux reserver un cours", OFFRES)
verifier("« cours » (4 offres) -> aucune selection", _o, None)
verifier_vrai("motif d'abstention explicite", "galit" in _motif or "insuffisant" in _motif, _motif)
verifier("« danse fitness cardio » -> aucune selection",
         CERTAINE("danse fitness cardio", OFFRES)[0], None)
verifier("liste d'offres vide -> aucune selection", CERTAINE("casque", [])[0], None)
verifier("message vide -> aucune selection", CERTAINE("", OFFRES)[0], None)

# Deterministe : le meme texte donne toujours la meme reponse, quel que soit
# l'ordre des offres en base.
verifier("resultat independant de l'ordre des offres",
         (CERTAINE("mon casque", list(reversed(OFFRES)))[0] or {}).get("id"),
         (CERTAINE("mon casque", OFFRES)[0] or {}).get("id"))

# === 5. LE CAS CONVERSATIONNEL REEL =========================================
# Message 1 : les 3 casques. Message 2 : la question TWINT, seule.
M1 = "J'aimerais 3 casques pour le LAAF Festival samedi à 18h."
M2 = "Puis-je payer par Twint ?"
verifier("message 2 SEUL -> aucune offre (c'est le bug d'origine)",
         CERTAINE(M2, OFFRES)[0], None)
_fil = M1 + " " + M2
verifier("fil complet -> l'offre casque est retrouvee",
         (CERTAINE(_fil, OFFRES)[0] or {}).get("id"), CASQUE["id"])

# ... et comme cette offre est GRATUITE, aucune promesse de TWINT.
# V440b : cette offre N'EST PAS gratuite malgre `price: 0.0` — son tarif du jour
# vient des paliers. Le 14/08 a 10:00, c'est 10 CHF.
_ctx_casque = CONTEXTE(OFFRES, CASQUE, "offre identifiée", maintenant=T_EARLY)
verifier_vrai("l'offre du festival est annoncee PAYANTE, pas gratuite",
              "au tarif actuel de 10 CHF" in _ctx_casque, _ctx_casque[:200])
verifier_vrai("offre payante -> TWINT est propose", "TWINT est possible" in _ctx_casque)
verifier_vrai("offre payante -> le lien reel est donne", LIEN(CASQUE) in _ctx_casque)

# Une offre REELLEMENT gratuite, elle, n'ouvre aucune promesse de paiement.
_ctx_vraiment_gratuit = CONTEXTE([GRATUITE], GRATUITE, "offre identifiée", maintenant=T_EARLY)
verifier_vrai("offre reellement gratuite -> annoncee gratuite",
              "GRATUITE" in _ctx_vraiment_gratuit)
verifier_vrai("offre reellement gratuite -> aucune promesse TWINT",
              "Ne propose donc PAS de paiement ni TWINT" in _ctx_vraiment_gratuit)
verifier_vrai("offre reellement gratuite -> le lien est quand meme donne",
              LIEN(GRATUITE) in _ctx_vraiment_gratuit)

# === 6. Offre payante identifiee -> bon lien reel ===========================
_ctx_tshirt = CONTEXTE(OFFRES, TSHIRT, "offre identifiée")
verifier_vrai("offre payante -> TWINT confirme", "TWINT est possible" in _ctx_tshirt)
verifier_vrai("offre payante -> lien EXACT de cette offre", LIEN(TSHIRT) in _ctx_tshirt)
verifier("le lien est bien derive de l'id reel", LIEN(TSHIRT),
         "https://afroboost.com/?offre=" + TSHIRT["id"])
verifier_vrai("aucun identifiant interne expose hors de l'URL",
              _ctx_tshirt.count(TSHIRT["id"]) == _ctx_tshirt.count(LIEN(TSHIRT)))

# === 7. Aucune offre identifiee -> aucun lien d'offre =======================
_ctx_rien = CONTEXTE(OFFRES, None, "score insuffisant")
verifier_vrai("sans offre -> interdiction de donner un lien",
              "AUCUN lien d'offre" in _ctx_rien)
verifier_vrai("sans offre -> on demande laquelle",
              "Demande gentiment de quelle offre" in _ctx_rien)
verifier_vrai("sans offre -> TWINT reste presente comme possible",
              "TWINT existe sur le site" in _ctx_rien)

# Le contexte ne contient JAMAIS d'URL hors de l'ensemble autorise.
_permises = AUTORISEES(OFFRES)
for _nom_ctx, _ctx in (("cible", _ctx_tshirt), ("sans cible", _ctx_rien),
                       ("gratuite", _ctx_casque)):
    _trouvees = re.findall(r"https?://[^\s]+", _ctx)
    verifier("contexte (%s) : toutes les URL sont autorisees" % _nom_ctx,
             [u for u in _trouvees if u not in _permises], [])

# On n'envoie jamais vers un tiers.
# Le contexte NOMME twint.ch pour l'interdire — c'est voulu. Ce qu'il ne doit
# jamais contenir, c'est une ADRESSE cliquable vers ce domaine.
for _nom_ctx, _ctx in (("cible", _ctx_tshirt), ("sans cible", _ctx_rien)):
    verifier("contexte (%s) : aucune ADRESSE twint.ch" % _nom_ctx,
             re.findall(r"(?:https?://|\bwww\.)[^\s]*twint\.ch[^\s]*", _ctx.lower())
             + re.findall(r"twint\.ch/", _ctx.lower()), [])
verifier_vrai("le contexte interdit d'envoyer vers l'app TWINT",
              "N'envoie JAMAIS quelqu'un chercher sur l'application" in _ctx_rien)

# === 8. Garde de sortie anti-invention ======================================
verifier("URL d'offre reelle -> conservee",
         GARDE("Voici le lien : " + LIEN(TSHIRT), _permises)[0],
         "Voici le lien : " + LIEN(TSHIRT))
verifier("racine du site -> conservee",
         GARDE("Va sur " + SITE, _permises)[0], "Va sur " + SITE)

_faux = SITE + "/?offre=00000000-0000-0000-0000-000000000000"
_txt, _ret = GARDE("Voici le lien pour ton offre : " + _faux, _permises)
verifier("offre INVENTEE -> ramenee sur la racine",
         _txt, "Voici le lien pour ton offre : " + SITE)
verifier("offre inventee -> signalee", _ret, [_faux])

_txt2, _ret2 = GARDE("Paye ici : https://twint.ch/payer", _permises)
verifier("lien TWINT tiers -> neutralise", _txt2, "Paye ici : " + SITE)
verifier("lien tiers -> signale", _ret2, ["https://twint.ch/payer"])

_txt3, _ret3 = GARDE("Regarde afroboost.com/?offre=bidon pour payer.", _permises)
verifier("URL sans protocole -> neutralisee aussi",
         _txt3, "Regarde " + SITE + " pour payer.")

verifier("ponctuation finale preservee",
         GARDE("Le lien : " + LIEN(PULSE) + ".", _permises)[0],
         "Le lien : " + LIEN(PULSE) + ".")
verifier("parenthese fermante preservee",
         GARDE("(voir " + LIEN(PULSE) + ")", _permises)[0],
         "(voir " + LIEN(PULSE) + ")")

verifier("texte sans URL -> inchange",
         GARDE("Oui, tu peux payer par TWINT sur le site.", _permises),
         ("Oui, tu peux payer par TWINT sur le site.", []))
verifier("texte vide -> inchange", GARDE("", _permises), ("", []))
verifier("None -> inchange", GARDE(None, _permises), (None, []))

# Les 5 liens d'offres reels passent tous la garde.
verifier("les 5 liens reels sont autorises",
         [o["name"] for o in OFFRES if LIEN(o) not in _permises], [])

# Le cas historique EXACT : la reponse « Twitter » envoyee le 13/08.
_reelle = ("Salut Esther, je m'occupe de ta réservation. "
           "N'hésite pas à me contacter par https://twitter.com/afroboost")
_nettoye, _ = GARDE(_reelle, _permises)
verifier_vrai("la reponse « Twitter » du 13/08 est neutralisee",
              "twitter.com" not in _nettoye and SITE in _nettoye, _nettoye)

# === 9. Non-regression d'intention : une question hors paiement ==============
# Ces messages ne doivent elire aucune offre, donc ne declencher aucun lien.
HORS_PAIEMENT = ["À quelle heure le cours ?", "Où ça se passe ?",
                 "Je peux annuler ma réservation ?", "Bonjour !",
                 "Merci beaucoup 🙏", "C'est ouvert dimanche ?"]
verifier("aucune question hors paiement n'elit d'offre",
         [t for t in HORS_PAIEMENT if CERTAINE(t, OFFRES)[0] is not None], [])

# === 10. Robustesse : rien ne doit lever =====================================
_anomalies = []
for _entree in (None, "", 123, {"a": 1}, [], "   ", "🎧🔥", "a" * 5000):
    try:
        MOTS(_entree); CERTAINE(_entree if isinstance(_entree, str) else "", OFFRES)
        GARDE(_entree if isinstance(_entree, str) else "", _permises)
    except Exception as _e:
        _anomalies.append((_entree, type(_e).__name__))
verifier("aucune entree bizarre ne fait lever", _anomalies, [])
_anomalies2 = []
for _offres in ([], [{}], [{"id": None}], [{"name": None, "price": None}]):
    try:
        CERTAINE("casque", _offres); AUTORISEES(_offres); CONTEXTE(_offres, None, "x")
    except Exception as _e:
        _anomalies2.append((_offres, type(_e).__name__))
verifier("offres malformees -> aucune exception", _anomalies2, [])

# === 11. V440b — LE PRIX RÉEL, PAS LE CHAMP PLAT ============================
PRIX = NS["v440_prix_actif"]
VISIBLE = NS["v440_visible"]
LISIBLE = NS["v440_prix_lisible"]

# Le coeur du lot : `price` vaut 0.0, l'offre n'est PAS gratuite.
verifier("le champ plat vaut bien 0.0 (sentinelle)", CASQUE["price"], 0.0)
verifier("prix actif AVANT la bascule -> 10 CHF", PRIX(CASQUE, T_EARLY), 10.0)
verifier("prix actif A LA LIMITE PILE -> 15 CHF (borne exclue)", PRIX(CASQUE, T_LIMITE_PILE), 15.0)
verifier("prix actif 1 s AVANT la limite -> encore 10 CHF", PRIX(CASQUE, T_LIMITE_MOINS), 10.0)
verifier("prix actif APRES la bascule -> 15 CHF", PRIX(CASQUE, T_STANDARD), 15.0)
verifier("2e bascule, 1 s avant -> encore 15 CHF", PRIX(CASQUE, T_LM_MOINS), 15.0)
verifier("2e bascule pile -> 25 CHF", PRIX(CASQUE, T_LM_PILE), 25.0)
verifier("evenement passe -> 25 CHF (last minute)", PRIX(CASQUE, T_APRES), 25.0)

# Les offres a prix plat ne changent pas de comportement.
verifier("prix plat inchange (PULSE)", PRIX(PULSE, T_EARLY), 250.0)
verifier("prix plat inchange (T-shirt)", PRIX(TSHIRT, T_APRES), 59.99)
verifier("offre vraiment gratuite -> 0.0", PRIX(GRATUITE, T_EARLY), 0.0)
verifier("offre absente -> 0.0 et pas d'exception", PRIX({}, T_EARLY), 0.0)

# Mise en forme des prix.
verifier("prix entier sans decimale", LISIBLE(10.0), "10 CHF")
verifier("prix a virgule conserve", LISIBLE(59.99), "59.99 CHF")

# Le contexte SUIT le palier — c'est l'exigence « pas de cache obsolete ».
_ctx_e = CONTEXTE(OFFRES, CASQUE, "ok", maintenant=T_EARLY)
_ctx_s = CONTEXTE(OFFRES, CASQUE, "ok", maintenant=T_STANDARD)
_ctx_l = CONTEXTE(OFFRES, CASQUE, "ok", maintenant=T_LM_PILE)
verifier_vrai("contexte a T_EARLY annonce 10 CHF", "au tarif actuel de 10 CHF" in _ctx_e)
verifier_vrai("contexte a T_STANDARD annonce 15 CHF", "au tarif actuel de 15 CHF" in _ctx_s)
verifier_vrai("contexte a T_LAST_MINUTE annonce 25 CHF", "au tarif actuel de 25 CHF" in _ctx_l)
verifier_vrai("le contexte change bien entre deux paliers", _ctx_e != _ctx_s)
verifier_vrai("aucun contexte n'annonce cette offre gratuite",
              all("GRATUITE" not in c for c in (_ctx_e, _ctx_s, _ctx_l)))
# ... et la liste generale suit aussi, pas seulement la ligne « offre concernee ».
verifier_vrai("la liste des offres payantes suit le palier",
              "— 10 CHF —" in _ctx_e and "— 15 CHF —" in _ctx_s)

# === 12. Offre invisible : jamais resolue, jamais liee ======================
_OFFRES_AVEC_MASQUEE = OFFRES + [VIDY]
verifier("offre invisible -> visible() False", VISIBLE(VIDY), False)
verifier("offre sans champ visible -> consideree visible", VISIBLE({"id": "x"}), True)
# L'exigence est « une offre invisible n'est JAMAIS proposee » — pas « ce message
# ne resout rien ». Ici « silent » figure aussi dans le nom de l'offre VISIBLE du
# festival, qui est donc elue : c'est acceptable, la carte porte son vrai nom et
# ses vraies dates. Ce qui compte est que VIDY ne sorte jamais.
_res_vidy = CERTAINE("je veux le silent a vidy lausanne", _OFFRES_AVEC_MASQUEE)[0]
verifier("l'offre masquee n'est JAMAIS celle qui est elue",
         (_res_vidy or {}).get("id") == VIDY["id"], False)
verifier("aucun mot ne peut elire l'offre masquee",
         [m for m in ("vidy", "lausanne", "silent", "casque")
          if (CERTAINE(m, _OFFRES_AVEC_MASQUEE)[0] or {}).get("id") == VIDY["id"]], [])
verifier_vrai("le lien de l'offre masquee n'est PAS autorise",
              LIEN(VIDY) not in AUTORISEES(_OFFRES_AVEC_MASQUEE))
verifier_vrai("le lien de l'offre masquee est neutralise par la garde",
              GARDE("Paye ici " + LIEN(VIDY), AUTORISEES(_OFFRES_AVEC_MASQUEE))[0]
              == "Paye ici " + SITE)
_ctx_masque = CONTEXTE(_OFFRES_AVEC_MASQUEE, None, "x", maintenant=T_EARLY)
verifier_vrai("l'offre masquee n'apparait pas dans le contexte",
              VIDY["id"] not in _ctx_masque and "Vidy" not in _ctx_masque)
# Meme designee explicitement, une offre masquee ne produit pas de lien cible.
_ctx_force = CONTEXTE(_OFFRES_AVEC_MASQUEE, VIDY, "force", maintenant=T_EARLY)
verifier_vrai("offre masquee imposee -> traitee comme non identifiee",
              "AUCUNE OFFRE" in _ctx_force and VIDY["id"] not in _ctx_force)

# === 13. Disponibilite REELLE du paiement ===================================
_ctx_sans_twint = CONTEXTE(OFFRES, CASQUE, "ok", maintenant=T_EARLY, twint_disponible=False)
verifier_vrai("paiement non configure -> aucune promesse TWINT",
              "TWINT est possible" not in _ctx_sans_twint)
verifier_vrai("paiement non configure -> on annonce l'indisponibilite",
              "aucun moyen de paiement en ligne n'est configuré" in _ctx_sans_twint)
verifier_vrai("paiement non configure -> on propose de faire suivre au coach",
              "Coach Bassi" in _ctx_sans_twint)
verifier_vrai("paiement non configure -> le lien de l'offre reste donne",
              LIEN(CASQUE) in _ctx_sans_twint)
_ctx_sans_twint_sans_offre = CONTEXTE(OFFRES, None, "rien", maintenant=T_EARLY,
                                      twint_disponible=False)
verifier_vrai("sans offre ET sans paiement -> aucune mention de TWINT possible",
              "TWINT existe sur le site" not in _ctx_sans_twint_sans_offre)

# === 14. Non-regression M1 : la garde anti-invention est intacte ============
_permises_b = AUTORISEES(_OFFRES_AVEC_MASQUEE)
for _t_inj in (T_EARLY, T_STANDARD, T_LM_PILE, T_APRES):
    _ctx_i = CONTEXTE(_OFFRES_AVEC_MASQUEE, CASQUE, "ok", maintenant=_t_inj)
    _hors = [u for u in re.findall(r"https?://[^\s]+", _ctx_i) if u not in _permises_b]
    verifier("contexte a %s : aucune URL hors liste" % _t_inj.strftime("%d/%m"), _hors, [])
verifier("la resolution d'offre n'a pas change (cas conversationnel)",
         (CERTAINE(M1 + " " + M2, OFFRES)[0] or {}).get("id"), CASQUE["id"])
verifier("l'abstention n'a pas change (message 2 seul)",
         CERTAINE(M2, OFFRES)[0], None)
verifier("l'ambiguite n'a pas change (« cours »)",
         CERTAINE("je veux reserver un cours", OFFRES)[0], None)

print("=" * 74)
echecs = 0
for ok, nom, obtenu, attendu in resultats:
    print(("  PASS  " if ok else "  FAIL  ") + nom)
    if not ok:
        echecs += 1
        print("          obtenu  : %r" % (obtenu,))
        print("          attendu : %r" % (attendu,))
print("=" * 74)
print("  %d/%d" % (len(resultats) - echecs, len(resultats)))
sys.exit(1 if echecs else 0)
