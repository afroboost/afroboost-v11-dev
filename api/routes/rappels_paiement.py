# -*- coding: utf-8 -*-
"""V648 — RAPPEL DU DEUXIÈME PAIEMENT (paiements manuels, coach uniquement).

CE QUE CE MODULE FAIT : un coach, depuis « Paiements à encaisser », voit un aperçu,
confirme, et le serveur envoie UN e-mail de rappel après avoir tout revérifié.

CE QU'IL NE FAIT JAMAIS : aucun prélèvement, aucun lien de paiement, aucune écriture sur
`subscriptions` ni sur `discount_codes`. Les seules collections écrites sont les siennes :
`rappels_paiement` (historique) et `rappels_paiement_reglages` (choix du coach).

TROIS VERROUS EN BASE, TOUS ABSENTS DONC FAUX À LA LIVRAISON, RÉGLÉS PAR LE SUPER-ADMIN :
  * `RAPPEL_PAIEMENT_ENVOI_REEL` : faux = la route d'envoi répond « simulation », n'écrit rien, n'appelle personne.
  * `RAPPEL_PAIEMENT_TEST_CONTROLE` : vrai = envoi réel vers UNE SEULE adresse, rangée en base (V651), et aucune autre.
  * `RAPPEL_PAIEMENT_AUTO_ACTIF` : faux = la boucle automatique relit ce drapeau et ressort sans rien lire d'autre.

V650 — L'AUTOMATIQUE (`passage_automatique`). Le coach l'active volontairement ; cela marche sans lui connecté.
POLITIQUE DE FRÉQUENCE : les règles sont celles du manuel, sans exception. Le plus tôt des délais cochés (J-3,
J0, J+3) ouvre le premier rappel, puis chaque rappel attend le délai de relance (7 jours au moins), dans la limite
de 3 par paiement. Avec les trois délais cochés : J-3, J+4, J+11. J0 et J+3 ne suivent donc jamais J-3 : envoyer à
3 jours d'écart violerait la règle des 7 jours. Les échéances antérieures à l'activation sont ignorées : aucun
envoi en masse sur l'historique. 20 messages au plus par passage, jours ouvrés de 8 h à 18 h, heure de Zurich.
Une panne du fournisseur arrête le passage. Sont exclus de l'automatique : les cas qui exigent une confirmation.

V650 — LE TEXTE. Le coach rédige avec {bonjour}, {montant} et {echeance}, que seul le serveur remplit. Un montant,
une date, un lien, une adresse ou un IBAN tapés à la main sont refusés. La mention « si tu as déjà payé » et la
signature sont toujours ajoutées : un solde calculé n'est jamais présenté comme une preuve de non-paiement.

V649 — SEUL UN ABONNEMENT STRIPE RÉEL COMPTE. Le type de l'offre ne dit pas comment CE client paie : une
offre `saison_2x` peut être vendue à la main, en TWINT ou en espèces. Voir `classer_mode_paiement`.

POURQUOI LES ABONNEMENTS STRIPE SONT EXCLUS. `saison_2x` et `mensuel_auto` sont prélevés par
Stripe, et la facture payée ne met à jour ni `montant_encaisse` ni `suivi_paiement`
(`hiver.py`) : le « reste à payer » y reste affiché après le paiement. Relancer ces clients,
c'est leur demander de payer deux fois.

L'ANTI-DOUBLON EST L'IDENTIFIANT LUI-MÊME. `_id` = abonnement|palier|rang : MongoDB garantit son
unicité, sans index à créer. Une seule requête peut insérer un rang ; les autres reçoivent une erreur
de clé dupliquée et n'appellent pas le fournisseur. La date n'en fait pas partie.

TROIS RAPPELS PAR PAIEMENT ATTENDU. Le compteur suit le paiement, jamais la date, la note, le total ou
la session. Un nouveau compteur ne démarre que si le rang du paiement avance ET qu'un encaissement a
été enregistré depuis le dernier rappel. Tout autre écart est une identité incertaine : on bloque,
on ne remet jamais à zéro. Au moins 7 jours entre deux messages partis (le coach peut allonger ce
délai, jamais le raccourcir). Chaque essai garde sa ligne : c'est l'historique complet.

UN APERÇU NE SERT QU'UNE FOIS. Le jeton d'aperçu est signé, valable 30 minutes et lié au coach, aux
données et à l'état des envois : tout essai le périme, il faut rouvrir l'aperçu avant chaque message.

LES ÉTATS D'UN ENVOI :
  en_cours  -> réservé, l'appel au fournisseur est en route
  envoye    -> Resend a accepté, ou le super-admin a apporté la preuve. Il compte dans les 3 rappels.
  echec     -> refus CERTAIN (quota, adresse refusée…) : aucun message parti, on peut réessayer, avec
               une nouvelle clé d'idempotence et une nouvelle date de référence. Il ne compte pas.
  incertain -> coupure, délai dépassé, erreur serveur : le message est PEUT-ÊTRE parti. L'écran dit
               « Envoi à vérifier ». AUCUNE reprise, ni automatique ni manuelle, et aucun délai ne
               débloque : plus aucun envoi de ce coach vers cette personne tant que le super-admin n'a pas résolu.
  non_parti -> le super-admin a prouvé l'absence d'envoi. Il ne compte pas. Le prochain rappel est une
               tentative distincte (nouveau rang, nouvelle clé), selon les règles normales.

RÉSOUDRE, C'EST PROUVER, ET CELA N'ENVOIE JAMAIS RIEN. Envoi prouvé : la fiche Resend existe, avec le
bon destinataire, objet, expéditeur et période. Absence prouvée : l'historique Resend couvre toute
la période, celle-ci est close (24 h, la durée de vie de la clé), et aucun e-mail n'y correspond.
Preuve insuffisante : le blocage reste, on contacte la personne hors du système.

LA SIGNATURE D'UN PARTENAIRE EST STRUCTURÉE. Deux champs validés (nom, activité) dans une formule
fixe, jamais un texte libre : pas de lien, pas d'instruction de paiement. La seule règle est ici :
l'écran affiche le refus renvoyé par le serveur.

UNE RÉPONSE TARDIVE N'ÉCRASE RIEN. Un succès reste un fait, tant qu'il porte la clé en vigueur. Un
échec ne compte que si l'essai est toujours celui en cours : sinon, l'état plus prudent reste.

LE SOLDE N'EST PAS UNE PREUVE. Il est calculé depuis des saisies du coach. Si la case « en
plusieurs fois » n'est pas cochée, rien ne dit qu'un second paiement était prévu : l'envoi reste
bloqué tant que le coach n'a pas saisi lui-même le montant réellement dû, et ce montant doit être
égal au solde calculé. Sinon il corrige d'abord son suivi : rien n'est jamais corrigé ici.
"""
import asyncio
import hashlib
import hmac
import html as _html
import json
import logging
import math
import os
import re
import unicodedata
from email.utils import parseaddr
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from pymongo.errors import DuplicateKeyError

import api.resend_central as _rc
from api.routes.shared import (SUPER_ADMIN_EMAIL, abo_actuel_du_code, b_normaliser_origine, coach_jwt_email,
                               suivi_paiement_lire, suivi_rappel, v617_jour_local, v617_visible_par,
                               v646_compte_coach_autorise)

try:
    import resend
except ImportError:  # pragma: no cover
    resend = None

logger = logging.getLogger(__name__)
router = APIRouter(tags=["rappels-paiement"])
db = None
_refus_email = None

COL_RAPPELS = "rappels_paiement"
COL_REGLAGES = "rappels_paiement_reglages"
COL_EXCLUSIONS = "rappels_paiement_exclusions"     # V652 : un membre exclu, par coach. Jamais supprimé, seulement réactivé
# V652 : un abonnement remplacé ou archivé n'est plus une dette à suivre. Tout autre statut non actif suspend les rappels.
STATUTS_SANS_SUSPENSION = ("active", "superseded", "archived", "")
MOTIF_ACTION_MAX = 200
STATUTS_TRACE = ("annule_tous", "annule_tous_leve", "reprise")     # des décisions du coach, sans rang d'envoi
DRAPEAU_ENVOI_REEL = "RAPPEL_PAIEMENT_ENVOI_REEL"
DRAPEAU_AUTO = "RAPPEL_PAIEMENT_AUTO_ACTIF"
DRAPEAU_TEST = "RAPPEL_PAIEMENT_TEST_CONTROLE"
ID_TEST_ADRESSE = "_test_adresse"     # V651 : hors des drapeaux, dont la lecture est publique
PLAFOND_PASSAGE = 20                  # messages au plus par passage automatique
PERIODE_AUTO_S, DEMARRAGE_AUTO_S = 3600, 180
AUTO_JOURS_APRES_MAX = 30             # au-delà de J+30, l'automatique se tait
OBJET_MAX, CORPS_MAX = 120, 2000
JETONS_MODELE = ("{bonjour}", "{montant}", "{echeance}")
CORPS_DEFAUT = "{bonjour}\n\nPetit rappel amical : il reste {montant} à régler pour ton abonnement Afroboost, prévu le {echeance}."
TONS_IA = {"chaleureux": "chaleureux et encourageant", "professionnel": "professionnel et courtois", "direct": "direct et bref, sans être sec"}
IA_LIMITE_HEURE = 20
# « evil . com », « evil point com ».
RE_LIEN_ESPACE = re.compile(r"(?:\.|\bdot\b|\bpoint\b)\s*(?:com|ch|net|org|fr|io|ly|shop|xyz|app|online|biz|link|club)\b", re.IGNORECASE)
# Extensions qui sont aussi des mots : en minuscules seulement, « Merci. De ton côté » reste une phrase.
RE_LIEN_MOT = re.compile(r"\.\s*(?:de|it|me|co|site|top|info)\b")
# Invisibles que `unicodedata` ne classe pas tous : remplisseurs hangul, blanc braille, joint de graphèmes.
INVISIBLES = frozenset("\u034f\u115f\u1160\u17b4\u17b5\u2800\u3164\uffa0")

MODE_MANUEL = "MANUEL"
MODE_AUTOMATIQUE = "AUTOMATIQUE"
MODES = (MODE_MANUEL, MODE_AUTOMATIQUE)
PALIER_MANUEL = "manuel"
PALIERS_AUTO = {"J-3": -3, "J0": 0, "J+3": 3}
BILLING_STRIPE = ("saison_2x", "mensuel_auto")

SOLDE_MINIMUM = 1.0                   # sous 1 CHF : un arrondi (ex. 199.99 sur 200), pas une dette
FRAIS_EN_COURS = timedelta(minutes=10)  # au-delà, un « en_cours » a perdu son processus
DUREE_CLE_FOURNISSEUR = timedelta(hours=24)   # au-delà, plus aucun effet tardif de cet essai n'est à craindre
LISTE_PAGES_MAX = 30                  # lecture de l'historique Resend : au-delà, preuve insuffisante
DELAI_RELANCE_DEFAUT = 7              # jours entre deux rappels manuels d'une même échéance
DELAI_RELANCE_MIN, DELAI_RELANCE_MAX = 7, 60
MAX_RAPPELS_PAR_ECHEANCE = 3          # le premier rappel compris
DUREE_JETON_APERCU = 1800             # secondes de validité d'un aperçu
NOM_PRO_MAX = 60
ACTIVITE_MAX = 40
NOM_CHIFFRES_MAX = 4                  # « Fit24 » oui ; un numéro de compte, même découpé, non
SIGNE_NOM = " '’&.-"
RE_NOM_DOMAINE = re.compile(r"(\bdot\b|\bpoint\b|\.)\s*(com|ch|net|org|fr|de|it|io|me|ly|co|shop|xyz|app|site|online|info|biz|link|top|club)\b", re.IGNORECASE)
# Sosies : lettres qui ne se décomposent pas, chiffres, et lettres d'autres alphabets identiques à l'œil.
NOM_SOSIES = str.maketrans({"ø": "o", "ß": "ss", "œ": "oe", "æ": "ae", "ð": "d", "þ": "th", "0": "o", "1": "i", "3": "e", "4": "a",
                            "5": "s", "7": "t", "8": "b", "а": "a", "в": "b", "е": "e", "к": "k", "м": "m", "н": "h", "о": "o", "р": "p",
                            "с": "c", "т": "t", "у": "y", "х": "x", "і": "i", "ѕ": "s", "ј": "j", "α": "a", "β": "b", "ε": "e", "ι": "i",
                            "κ": "k", "ν": "v", "ο": "o", "ρ": "p", "τ": "t", "υ": "u", "χ": "x", "օ": "o", "ս": "u",
                            "ł": "l", "đ": "d", "ı": "i", "ħ": "h", "ŋ": "n", "ƀ": "b", "ɪ": "i"})
NOM_SOSIES_COURTS = {ord("œ"): "o", ord("æ"): "a", ord("ß"): "s", ord("þ"): "t"}   # l'autre lecture : une seule lettre
MARQUE_PLATEFORME = "afroboost"
MARQUES_PAIEMENT = ("twint", "paypal", "stripe", "revolut")
# Des mots entiers, jamais des préfixes : Payet, Lien Nguyen ou Jean Carte signent normalement.
MOTS_INTERDITS = frozenset(("iban", "payer", "payez", "paie", "pay", "payment", "paiement", "paiements", "virement", "transfer", "transfert", "envoyez", "envoyer",
                            "send", "bank", "banque", "konto", "zahlung", "uberweisung", "compte", "account", "clique", "cliquez", "click", "urgent", "support",
                            "admin", "administrateur", "administration", "chf", "eur", "usd", "www", "http", "https"))
MOTS_DE_TITRE = frozenset(("coach", "officiel", "officielle", "by", "le", "la", "m", "mr", "mme", "monsieur", "madame", "mister", "dr", "docteur", "team", "equipe"))
RE_RESEND_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
OBJETS_RAPPEL = ("Rappel : ton deuxième paiement Afroboost", "Rappel : ton prochain paiement Afroboost")

SIMULATION_MAX = 50
RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
COACHS_BASSI = ("", "bassi_default", SUPER_ADMIN_EMAIL.lower())

MOTIFS = {
    "aucun_abonnement_actuel": "Cet abonnement n'est plus l'abonnement actuel du code.",
    "plusieurs_abonnements": "Ce code porte plusieurs abonnements actuels : à vérifier d'abord.",
    "code_ambigu": "Ce code existe en plusieurs exemplaires : à vérifier d'abord.",
    "stripe_recurrent": "Prélevé automatiquement par Stripe : pas de rappel manuel pour cette échéance.",
    "paiement_a_verifier": "Paiement à vérifier : les informations de paiement sont contradictoires ou incomplètes. Aucun rappel possible.",
    "solde_inconnu": "Le montant total ou le montant encaissé n'est pas renseigné.",
    "solde_nul": "Il ne reste rien à payer.",
    "suivi_incoherent": "Le suivi de paiement est incohérent : à corriger avant tout rappel.",
    "sans_echeance": "Aucune date d'échéance renseignée.",
    "hors_fenetre": "L'échéance est dans plus de 7 jours.",
    "sans_email": "Aucune adresse e-mail valide sur l'abonnement.",
    "destinataire_ambigu": "L'adresse du code et celle de l'abonnement sont différentes.",
    "refus_email": "Cette personne a demandé à ne plus recevoir d'e-mails.",
    "membre_exclu": "Ce membre est exclu des rappels : aucun envoi manuel ni automatique.",
    "abonnement_suspendu": "Abonnement inactif : rappels suspendus. Le solde reste à traiter par le coach.",
    "signature_manquante": "Renseigne ta signature (nom et activité) dans « Rappels de paiement » : le message ne peut pas être signé.",
}
AVERTISSEMENT_CASE = ("La case « paiement en plusieurs fois » n'est pas cochée alors qu'un solde reste affiché. "
                      "Ce solde est un calcul, pas une preuve de non-paiement : vérifie ce qui est réellement dû.")


def init_db(database, refus_email=None):
    global db, _refus_email
    db = database
    _refus_email = refus_email


# ═══════════════════════════ RÈGLES PURES ═══════════════════════════

def _nombre(v):
    try:
        if v in (None, ""):
            return None
        n = float(v)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError, OverflowError):
        return None


MODES_MANUELS = {"twint": "TWINT", "especes": "Espèces", "virement": "Virement"}
MODES_SANS_PRELEVEMENT = {"stripe": "Carte, paiement unique", "mobile_money": "Mobile Money, paiement unique"}


def classer_mode_paiement(sub) -> dict:
    """PUR. Comment CE client paie, d'après son abonnement : {classe, libelle}.

    classe : stripe_auto | manuel | a_verifier. Un prélèvement automatique exige un vrai abonnement Stripe
    (`stripe_subscription_id`). Ni le type de l'offre, ni un ancien paiement Stripe ne le prouvent.
    Données contradictoires ou insuffisantes : `a_verifier`, sans rien affirmer.
    """
    _s = sub or {}
    _id = str(_s.get("stripe_subscription_id") or "").strip()
    _o = b_normaliser_origine(_s.get("origine_paiement"))
    if _id:
        if _o in MODES_MANUELS or _o == "offert":
            return {"classe": "a_verifier", "libelle": "Paiement à vérifier"}
        return {"classe": "stripe_auto", "libelle": "Prélèvement automatique Stripe"}
    if _s.get("billing_mode") in BILLING_STRIPE and _s.get("payment_mode") != "full":
        return {"classe": "a_verifier", "libelle": "Paiement à vérifier"}     # automatique annoncé, aucun abonnement Stripe
    if _o in MODES_MANUELS:
        return {"classe": "manuel", "libelle": MODES_MANUELS[_o]}
    if _o in MODES_SANS_PRELEVEMENT:
        return {"classe": "manuel", "libelle": MODES_SANS_PRELEVEMENT[_o]}
    return {"classe": "a_verifier", "libelle": "Paiement à vérifier"}         # inconnu, ou « offert » avec un solde


def eligibilite(sub, code_doc=None, motif_abo="unique", maintenant=None, ignorer_fenetre=False) -> dict:
    """PUR. Ce rappel peut-il partir ? {ok, motif, message, avertissement, reste, ...}.

    Jamais de correction silencieuse : une donnée douteuse bloque, et le coach lit pourquoi.
    `ok` dit seulement qu'un aperçu peut être montré. Une case « en plusieurs fois » non cochée
    pose `verification_requise` : la route d'envoi refuse alors tant que le coach n'a pas
    confirmé le montant dû, et l'automatique exclut ce cas (`incomplet`).
    """
    def _non(motif):
        return {"ok": False, "motif": motif, "message": MOTIFS.get(motif, motif)}

    if motif_abo == "plusieurs":
        return _non("plusieurs_abonnements")
    _s = sub or {}
    if motif_abo != "unique" or str(_s.get("status") or "").strip().lower() != "active":
        return _non("aucun_abonnement_actuel")
    _classe = classer_mode_paiement(_s)["classe"]
    if _classe == "stripe_auto":
        return _non("stripe_recurrent")
    if _classe == "a_verifier":
        return _non("paiement_a_verifier")

    _vue = suivi_paiement_lire(_s)
    _total, _enc = _nombre(_vue.get("montant_total")), _nombre(_s.get("montant_encaisse"))
    if _total is None or _enc is None:
        return _non("solde_inconnu")
    if _enc > _total + 0.005 or _total <= 0 or _enc <= 0:
        return _non("suivi_incoherent")      # encaissé > total, ou aucun premier paiement enregistré
    if not re.match(r"^[A-Z]{3}$", str(_s.get("devise") or "CHF")):
        return _non("suivi_incoherent")      # la devise est écrite dans l'e-mail : rien d'autre que son code
    _reste = round(_total - _enc, 2)
    if _reste <= 0.005:
        return _non("solde_nul")
    if _reste < SOLDE_MINIMUM:
        return _non("suivi_incoherent")

    _plusieurs = bool(_vue.get("plusieurs_fois"))
    _nb, _act = _vue.get("nb_paiements"), _vue.get("paiement_actuel")
    if _plusieurs and (not _nb or not _act or _act >= _nb):
        return _non("suivi_incoherent")      # « dernier paiement fait », et pourtant un solde

    _ech = _vue.get("prochaine_echeance")
    if not _ech:
        return _non("sans_echeance")
    try:
        datetime.strptime(_ech, "%Y-%m-%d")
    except (TypeError, ValueError):
        return _non("suivi_incoherent")
    if not ignorer_fenetre and suivi_rappel(_s, maintenant) is None:
        return _non("hors_fenetre")

    # Le destinataire vient de l'ABONNEMENT ACTUEL : la fiche du code n'a pas toujours d'adresse.
    _email = str(_s.get("email") or "").strip().lower()
    if not RE_EMAIL.match(_email):
        return _non("sans_email")
    _email_code = str((code_doc or {}).get("assignedEmail") or "").strip().lower()
    if _email_code and _email_code != _email:
        return _non("destinataire_ambigu")

    return {"ok": True, "motif": None, "message": "", "reste": _reste, "devise": _s.get("devise") or "CHF",
            "echeance": _ech, "destinataire": _email, "incomplet": not _plusieurs,
            "verification_requise": not _plusieurs, "paiement_actuel": _act, "nb_paiements": _nb,
            "avertissement": AVERTISSEMENT_CASE if not _plusieurs else ""}


def empreinte(sub_id, verdict, texte="") -> str:
    """PUR. Résume ce que le coach a vu : si un seul de ces éléments change, l'envoi est refusé."""
    _b = "|".join(str(x) for x in (sub_id, "%.2f" % verdict["reste"], verdict["devise"], verdict["echeance"],
                                   verdict["destinataire"], verdict.get("paiement_actuel"), verdict.get("nb_paiements"), texte))
    return hashlib.sha256(_b.encode("utf-8")).hexdigest()[:24]


def cle_envoi(sub_id, rang=1, palier=PALIER_MANUEL) -> str:
    """PUR. Un seul essai par abonnement, palier et rang. La date n'y est pas : la changer n'ouvre rien."""
    return "%s|%s|%d" % (sub_id, palier, rang)


def etape_du_rang(rang) -> str:
    """PUR. Le nom de l'étape dans l'historique."""
    return "Rappel" if int(rang or 1) <= 1 else "Relance %d" % (int(rang) - 1)


def _instant(iso):
    try:
        _d = datetime.fromisoformat(str(iso))
    except (TypeError, ValueError):
        return None
    return _d if _d.tzinfo else _d.replace(tzinfo=timezone.utc)


def _refus(type_, doc=None, rang=None, prochaine=None, message="") -> dict:
    _d = {"action": "refus", "type": type_, "rang": rang or int((doc or {}).get("rang") or 1), "doc": doc, "message": message}
    if prochaine is not None:
        _d["prochaine_le"] = prochaine.isoformat()
    return _d


MSG_INCERTAIN = "Le dernier envoi n'a pas pu être confirmé : le message est peut-être déjà parti."
MSG_EN_COURS = "Un envoi est déjà en cours."


def _statut_effectif(doc, maintenant) -> str:
    """PUR. Un « en_cours » trop ancien a perdu son processus : le message est peut-être parti."""
    _s = (doc or {}).get("statut")
    if _s == "en_cours":
        _m = _instant(doc.get("maj_le"))
        if _m is None or maintenant - _m >= FRAIS_EN_COURS:
            return "incertain"
    return _s


def _refus_incertain(doc) -> dict:
    return _refus("incertain_bloque", doc, message="Envoi à vérifier : " + MSG_INCERTAIN + " Aucun nouvel envoi sans preuve du fournisseur : contacte la personne directement, hors du système.")


def paiement_attendu(sub_id, sub) -> dict:
    """PUR. Ce qui identifie le paiement attendu. Le rang n'existe que si l'échéancier est renseigné."""
    _vue = suivi_paiement_lire(sub)
    _act = _vue.get("paiement_actuel")
    return {"sub": sub_id, "numero": _act + 1 if _vue.get("plusieurs_fois") and isinstance(_act, int) else None, "nb": _vue.get("nb_paiements"),
            "encaisse": _nombre((sub or {}).get("montant_encaisse")), "total": _nombre(_vue.get("montant_total"))}


def classer_paiement(doc, paiement) -> str:
    """PUR. Ce rappel déjà parti visait-il le paiement attendu ? meme | distinct | ambigu.

    `distinct` exige deux preuves à la fois : le rang avance, et l'encaissé a monté d'au moins la part
    attendue pour les rangs passés. Avancer le rang avec 1 centime, ou baisser le total, ne suffit pas.
    Une correction du suivi (date, note, total, case) reste le même paiement. Un écart contradictoire
    est `ambigu` : l'envoi est bloqué, le compteur n'est jamais remis à zéro.
    Autre abonnement de la même personne : `distinct` seulement si l'ancien est clos ET soldé. Sinon la
    même dette reste le même paiement, et un écart de montants, même d'un centime, reste `ambigu`.
    """
    _e0, _t0 = _nombre(doc.get("encaisse_au_rappel")), _nombre(doc.get("total_au_rappel"))
    _e, _t = paiement.get("encaisse"), paiement.get("total")
    if _e0 is None or _e is None:
        return "ambigu"
    if doc.get("subscription_id") != paiement.get("sub"):
        if doc.get("_abonnement_solde") is True:
            return "distinct"
        if _t0 is None or _t is None:
            return "ambigu"
        return "meme" if abs(_t0 - _t) <= 0.005 and abs(_e0 - _e) <= 0.005 else "ambigu"
    _n0, _n = doc.get("paiement_numero"), paiement.get("numero")
    _monte = _e > _e0 + 0.005
    if _n0 is None or _n is None:          # sans échéancier : une correction, si rien n'est entré
        return "ambigu" if _monte else "meme"
    if _n == _n0:
        return "meme"                      # un acompte ne change pas le paiement attendu
    _nb0 = doc.get("nb_au_rappel")
    if _n < _n0 or _n > 12 or not _monte or _t0 is None or not isinstance(_nb0, int) or isinstance(_nb0, bool) or not _n0 <= _nb0 <= 12 or _n > _nb0:
        return "ambigu"
    _part = (_t0 - _e0) / (_nb0 - _n0 + 1)
    return "distinct" if _e - _e0 >= (_n - _n0) * _part - 0.005 else "ambigu"


def _date_effet(doc):
    """PUR. La date qui fait courir le délai : l'envoi réel, ou la date retenue pour un rappel annulé."""
    return _instant(doc.get("envoye_le") or doc.get("effet_le"))


def decision_relance(docs, delai_jours, maintenant, paiement=None) -> dict:
    """PUR. Que permet l'historique de cette personne chez ce coach ? Une seule règle, pour l'écran et l'envoi.

    action : nouveau | reessai | refus. `rang` identifie l'essai ; `numero` est le rappel (1 à 3) de ce paiement.
    Une date illisible bloque : dans le doute, aucun message.
    """
    _delai = timedelta(days=delai_jours)
    for _d in docs:
        if _statut_effectif(_d, maintenant) == "incertain":
            return _refus_incertain(_d)
    for _d in docs:
        if _statut_effectif(_d, maintenant) == "en_cours":
            return _refus("en_cours", _d, message=MSG_EN_COURS)
    # V652 : « annuler les rappels futurs » tient tant qu'un paiement distinct n'est pas prouvé. Le doute garde le blocage.
    for _d in docs:
        if _d.get("statut") == "annule_tous" and (not paiement or classer_paiement(_d, paiement) != "distinct"):
            return _refus("annule_tous", _d, message="Rappels annulés pour ce paiement.")
    # V652 : un rappel annulé consomme sa place : il ne revient pas, et le suivant attend le délai à partir de sa date.
    _partis = [d for d in docs if d.get("statut") in ("envoye", "annule")]
    _compte = 0
    for _d in _partis:
        _c = classer_paiement(_d, paiement) if paiement else "meme"
        if _c == "ambigu":
            return _refus("paiement_ambigu", _d, message="Impossible de savoir s'il s'agit du même paiement : vérifie l'échéancier et le montant encaissé. Aucun rappel possible.")
        if _c == "meme":
            _compte += 1
    if _compte >= MAX_RAPPELS_PAR_ECHEANCE:
        return _refus("maximum_atteint", _partis[-1], message="Maximum de %d rappels atteint pour ce paiement." % MAX_RAPPELS_PAR_ECHEANCE)
    _dates = [_date_effet(d) for d in _partis]
    if any(x is None for x in _dates):
        return _refus_incertain(next(d for d in _partis if _date_effet(d) is None))
    _ici = [d for d in docs if d.get("statut") not in STATUTS_TRACE and (not paiement or d.get("subscription_id") == paiement.get("sub"))]
    _der = max(_ici, key=lambda d: int(d.get("rang") or 1)) if _ici else None
    _rang_suivant = int((_der or {}).get("rang") or 0) + 1
    if _dates and maintenant < max(_dates) + _delai:
        _proch = max(_dates) + _delai
        _dernier = _partis[_dates.index(max(_dates))]
        _texte = "Rappel annulé. Prochain rappel possible le %s." if _dernier.get("statut") == "annule" else "Déjà envoyé. Relance possible le %s."
        return dict(_refus("deja_envoye", _dernier, prochaine=_proch, message=_texte % _date_ch(_proch.isoformat())),
                    numero_suivant=_compte + 1, rang_suivant=_rang_suivant)
    if _der is not None and _der.get("statut") == "echec":
        return {"action": "reessai", "rang": int(_der.get("rang") or 1), "numero": _compte + 1, "doc": _der}
    return {"action": "nouveau", "rang": _rang_suivant, "numero": _compte + 1}


def etat_decision(decision) -> str:
    """PUR. Résume l'état des envois : tout nouvel essai le change, donc périme les anciens aperçus."""
    return "%s|%s|%s" % (decision.get("action"), decision.get("rang"), int((decision.get("doc") or {}).get("tentatives") or 0))


def _signature_jeton(emp, etat, coach, quand) -> str:
    _cle = os.environ.get("JWT_SECRET", "").encode("utf-8")
    return hmac.new(_cle, ("%s|%s|%s|%d" % (emp, etat, coach, quand)).encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def jeton_apercu(emp, etat, coach, maintenant) -> str:
    """Le jeton remis avec un aperçu. Signé : on ne peut pas envoyer sans l'avoir demandé."""
    _q = int(maintenant.timestamp())
    return "%d.%s" % (_q, _signature_jeton(emp, etat, coach, _q))


def jeton_valide(jeton, emp, etat, coach, maintenant) -> str:
    """ok | expire | different."""
    try:
        _q, _sig = str(jeton).split(".", 1)
        _q = int(_q)
    except (TypeError, ValueError, OverflowError):
        return "different"
    if not os.environ.get("JWT_SECRET") or not hmac.compare_digest(_sig.encode("utf-8"), _signature_jeton(emp, etat, coach, _q).encode("utf-8")):
        return "different"
    _age = int(maintenant.timestamp()) - _q
    return "ok" if 0 <= _age <= DUREE_JETON_APERCU else "expire"


def _lectures_nom(texte) -> list:
    """PUR. Comment ce texte se lit à l'œil : accents retirés, sosies remplacés, « l » lu « i »."""
    _plat = unicodedata.normalize("NFKD", texte.casefold()).casefold()
    _plat = "".join(c for c in _plat if not unicodedata.combining(c))
    _sortie = []
    for _t in (_plat.translate(NOM_SOSIES), _plat.translate(NOM_SOSIES_COURTS).translate(NOM_SOSIES)):
        _sortie.extend((_t, _t.replace("l", "i")))
    return _sortie


def _alphabet(c) -> str:
    return unicodedata.name(c, "?").split(" ")[0]


def _caractere_accepte(texte, i) -> bool:
    """PUR. Lettres et chiffres de tous alphabets, signes de nom. Les marques et les liaisons
    (ZWJ/ZWNJ) seulement dans une écriture qui en a besoin : en latin, elles cachent des mots."""
    _c = texte[i]
    if _c.isalnum() or _c in SIGNE_NOM:
        return True
    _av = texte[i - 1] if i else ""
    _ap = texte[i + 1] if i + 1 < len(texte) else ""
    _non_latin = lambda x: bool(x) and (x.isalpha() or unicodedata.category(x).startswith("M")) and _alphabet(x) != "LATIN"  # noqa: E731
    if _c in "\u200c\u200d":
        return _non_latin(_av) and (not _ap or _ap == " " or _non_latin(_ap))
    _nom = unicodedata.name(_c, "")
    if not unicodedata.category(_c).startswith("M") or "VARIATION SELECTOR" in _nom or "GRAPHEME JOINER" in _nom:
        return False
    return _non_latin(_av) or (_av.isalpha() and unicodedata.combining(_c) != 0)


def _mot_coherent(mot) -> bool:
    """PUR. Un mot latin ne contient que des lettres qui se lisent en latin simple, et aucun autre alphabet."""
    _lettres = [c for c in unicodedata.normalize("NFKD", mot) if c.isalpha()]
    _alph = {_alphabet(c) for c in _lettres}
    if "LATIN" in _alph and len(_alph) > 1:
        return False
    if _alph == {"LATIN"}:
        return all(c.casefold().translate(NOM_SOSIES).isascii() for c in _lettres)
    return True


def motif_nom_refuse(texte, maximum=NOM_PRO_MAX) -> str:
    """PUR. Chaîne vide si ce texte peut entrer dans une signature ; sinon l'explication pour le coach.

    Accepte les chiffres, les accents et tous les alphabets. « Bassi » n'est refusé que seul ou avec un
    titre (« Coach Bassi ») : Bassirou ou Jean Bassi signent normalement.
    """
    if not isinstance(texte, str) or not texte.strip():
        return "Ce champ est vide."
    _n = unicodedata.normalize("NFC", texte.strip())
    if len(_n) > maximum:
        return "Trop long : %d caractères au plus." % maximum
    if not all(_caractere_accepte(_n, i) for i in range(len(_n))):
        return "Seuls les lettres, chiffres, espaces et les signes ' & . - sont acceptés : pas de lien ni d'adresse e-mail."
    if not _n[0].isalnum():
        return "Commence par une lettre ou un chiffre."
    if RE_NOM_DOMAINE.search(_n):
        return "Pas de lien ni d'adresse de site."
    for _mot in _n.split():
        _parts = _mot.split(".")
        # Un point ne sert qu'aux initiales (A.B., St.) : « evil.shop » ou « 1.1.1.1 » sont des adresses.
        if len(_parts) > 1 and (any(len(p) > 1 for p in _parts[1:]) or any(p.isdigit() for p in _parts)):
            return "Pas de lien ni d'adresse de site."
    if sum(c.isdigit() for c in _n) > NOM_CHIFFRES_MAX:
        return "Trop de chiffres : %d au plus, pas de numéro de compte ni de téléphone." % NOM_CHIFFRES_MAX
    if not all(_mot_coherent(m) for m in re.split(r"[\s'’&.\-]+", _n) if m):
        return "Un même mot mélange plusieurs alphabets ou des lettres inhabituelles : écris-le simplement."
    for _l in _lectures_nom(_n):
        _mots = [m for m in re.split(r"[^\w]+", _l) if m]
        if MARQUE_PLATEFORME in "".join(c for c in _l if c.isalpha()):
            return "Ce nom imite la marque Afroboost."
        # Les lettres isolées (« T W I N T ») se recollent ; deux vrais mots non : Christ Ripert signe normalement.
        _blocs, _court = [], ""
        for _m in _mots:
            if len(_m) <= 2:
                _court += _m
            else:
                _blocs.extend([_court, _m] if _court else [_m])
                _court = ""
        _blocs.append(_court)
        if any(m in b for m in MARQUES_PAIEMENT for b in _blocs):
            return "Ce nom imite un moyen de paiement (TWINT, Stripe…)."
        if set(_mots) & MOTS_INTERDITS or "serviceclient" in "".join(_mots):
            return "Pas d'instruction de paiement ni de mot de service (paiement, compte, support…)."
        if "".join(m for m in _mots if m not in MOTS_DE_TITRE) == "bassi":
            return "« Coach Bassi » est réservé à la signature officielle : ajoute ton prénom et ton nom."
    return ""


def signature_structuree(sig) -> str:
    """PUR. Deux champs validés dans une formule fixe. Chaîne vide si un champ est absent ou refusé."""
    _s = sig if isinstance(sig, dict) else {}
    _nom, _act = _s.get("nom"), _s.get("activite")
    if motif_nom_refuse(_nom, NOM_PRO_MAX):
        return ""
    if _act not in (None, "") and motif_nom_refuse(_act, ACTIVITE_MAX):
        return ""
    if sum(c.isdigit() for c in _nom + (_act or "")) > NOM_CHIFFRES_MAX:
        return ""                        # un numéro ne se répartit pas entre les deux champs
    _ligne = _nom.strip() + (", " + _act.strip() if _act else "")
    return _ligne + "\nCoach partenaire d'Afroboost"


def cle_idempotence(cle, tentative=1) -> str:
    """PUR. Propre à chaque essai : une clé n'est jamais réutilisée pour un nouvel appel."""
    return "rappel-paiement-" + hashlib.sha256(("%s#%s" % (cle, tentative)).encode("utf-8")).hexdigest()[:40]


def signature_du_code(code_doc, sig=None) -> str:
    """PUR. « Coach Bassi, d'Afroboost » pour ses codes ; un partenaire signe avec SES champs validés.
    Chaîne vide s'ils manquent : l'envoi est alors refusé, plutôt que signé au hasard."""
    _proprio = str((code_doc or {}).get("coach_id") or "").strip().lower()
    if _proprio in COACHS_BASSI:
        return "Coach Bassi, d'Afroboost"
    return signature_structuree(sig)


def _prenom(nom) -> str:
    _n = str(nom or "").strip()
    if not _n or "@" in _n:
        return ""
    _p = _n.split()[0][:40]
    return "" if motif_nom_refuse(_p) else _p      # le nom vient de saisies : rien d'autre qu'un prénom dans l'e-mail


def _montant_lisible(m) -> str:
    return "%d" % m if float(m).is_integer() else "%.2f" % m


def _date_ch(iso) -> str:
    _a, _m, _j = str(iso)[:10].split("-")
    return "%s.%s.%s" % (_j, _m, _a)


def sujet_defaut(paiement_actuel=None) -> str:
    """PUR. Le mot « deuxième » n'est écrit que s'il est vrai : au 3e paiement, l'objet dit « prochain »."""
    return "Rappel : ton %s paiement Afroboost" % ("prochain" if paiement_actuel and paiement_actuel >= 2 else "deuxième")


def motif_modele_refuse(sujet, corps) -> str:
    """PUR. Chaîne vide si ce texte peut être envoyé ; sinon l'explication pour le coach."""
    if not isinstance(sujet, str) or not isinstance(corps, str):
        return "Objet ou message illisible."
    _s, _c = sujet.strip(), corps.strip()
    if not 3 <= len(_s) <= OBJET_MAX or "\n" in _s or "\r" in _s:
        return "Objet : une seule ligne, %d caractères au plus." % OBJET_MAX
    if not _c or len(_c) > CORPS_MAX:
        return "Message : %d caractères au plus." % CORPS_MAX
    if re.search(r"[{}]", _s):
        return "L'objet ne peut pas contenir de variable."
    _jetons = re.findall(r"\{[^{}]*\}", _c)
    if any(j not in JETONS_MODELE for j in _jetons) or re.search(r"[{}]", re.sub(r"\{[^{}]*\}", "", _c)):
        return "Seules les variables {bonjour}, {montant} et {echeance} sont acceptées."
    if "{montant}" not in _c or "{echeance}" not in _c:
        return "Garde {montant} et {echeance} : le serveur les remplit avec les données vérifiées."
    # Lu comme à l'œil : caractères invisibles retirés, signes de compatibilité (．＠) ramenés à leur forme simple.
    # Pour ce contrôle seulement : le texte envoyé garde ses accents et ses émojis.
    _tout = "".join(c for c in unicodedata.normalize("NFKC", _s + "\n" + _c)
                    if unicodedata.category(c) not in ("Cf", "Mn", "Me") and c not in INVISIBLES).replace("\u3002", ".")
    if re.search(r"https?:|www\.|@|\w\.[^\W\d_]{2,}", _tout, re.IGNORECASE) or RE_LIEN_ESPACE.search(_tout) or RE_LIEN_MOT.search(_tout):
        return "Pas de lien ni d'adresse e-mail dans le message."
    if re.search(r"\biban\b", _tout, re.IGNORECASE):
        return "Pas de coordonnées de paiement dans le message."
    if re.search(r"\d", _tout):
        return "Pas de chiffres dans le texte : le serveur remplit {montant} et {echeance}."
    if re.search(r"\b(?:chf|eur|euros?|francs?|janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre)\b", _tout, re.IGNORECASE):
        return "N'écris ni montant ni date : utilise {montant} et {echeance}."
    return ""


def construire_message(prenom, reste, devise, echeance, signature, paiement_actuel=None, modele=None) -> dict:
    """PUR. Le texte validé par Bassi le 05/11/2026, ou le modèle du coach. {sujet, texte, html}.

    Le montant et la date viennent du serveur. La mention « si tu as déjà payé » et la signature sont
    toujours ajoutées. Toute valeur variable est échappée dans le HTML.
    """
    _m = modele if isinstance(modele, dict) else {}
    _sujet = (_m.get("sujet") or sujet_defaut(paiement_actuel)).strip()
    _bonjour = "Bonjour %s," % prenom if prenom else "Bonjour,"
    _rendu = (_m.get("corps") or CORPS_DEFAUT).strip().replace("\r\n", "\n").replace("{bonjour}", _bonjour) \
        .replace("{montant}", "%s %s" % (_montant_lisible(reste), devise)).replace("{echeance}", _date_ch(echeance))
    _p2 = "Si tu as déjà payé, ne tiens pas compte de ce message. Pour toute question, réponds simplement à cet e-mail."
    _p3 = "À très vite en cours !"
    _texte = "\n\n".join((_rendu, _p2, _p3 + "\n" + signature))
    _esc = lambda x: _html.escape(x, quote=True).replace("\n", "<br>")  # noqa: E731
    _lignes = "".join('<p style="margin:0 0 16px">%s</p>' % _esc(x) for x in _rendu.split("\n\n") + [_p2])
    _fin = '<p style="margin:0">%s<br>%s</p>' % (_esc(_p3), _esc(signature))
    _corps = ('<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:#222;'
              'max-width:520px;margin:0 auto;padding:16px">%s%s</div>' % (_lignes, _fin))
    return {"sujet": _sujet, "texte": _texte, "html": _corps}


def classer_erreur(err) -> str:
    """PUR. `echec` seulement si on est CERTAIN que rien n'est parti ; tout le reste est `incertain`.

    Se tromper dans ce sens coûte un clic au coach. Dans l'autre, un double e-mail au client.
    """
    if isinstance(err, _rc.QuotaResendAtteint):
        return "echec"                      # bloqué avant tout appel au fournisseur
    _code = getattr(err, "code", None)
    try:
        _code = int(_code)
    except (TypeError, ValueError):
        return "incertain"
    if _code in (408, 409):                 # délai dépassé, clé d'idempotence déjà en cours
        return "incertain"
    return "echec" if 400 <= _code < 500 else "incertain"


def _nom_jalon(offset) -> str:
    return "J0" if offset == 0 else ("J%+d" % offset)


def jalons_simulation(echeance, delais, maintenant=None, delai_jours=DELAI_RELANCE_DEFAUT, envoyes=0, prochaine=None) -> list:
    """PUR. Les dates que le moteur retiendrait : jamais une date passée. Le premier rappel part au plus
    tôt des délais cochés (ou aujourd'hui s'il est dépassé) ; les suivants, tous les `delai_jours`."""
    _auj = v617_jour_local(maintenant)
    _base = datetime.strptime(echeance, "%Y-%m-%d")
    _coches = [PALIERS_AUTO[p] for p in PALIERS_AUTO if p in delais]
    if not _coches:
        return []
    _aujourdhui = datetime.strptime(_auj, "%Y-%m-%d")
    _debut = max(_base + timedelta(days=min(_coches)), _aujourdhui)
    if prochaine:
        _debut = max(_debut, datetime.strptime(prochaine[:10], "%Y-%m-%d"))
    _sortie = []
    for _i in range(max(0, MAX_RAPPELS_PAR_ECHEANCE - envoyes)):
        _date = _debut + timedelta(days=_i * delai_jours)
        _off = (_date - _base).days
        if _off > AUTO_JOURS_APRES_MAX:
            break
        _d = _date.strftime("%Y-%m-%d")
        _sortie.append({"palier": _nom_jalon(_off), "date": _d, "etat": "aujourdhui" if _d == _auj else "a_venir"})
    return _sortie


def delais_du_reglage(doc) -> list:
    """PUR. Jamais réglé : les trois délais. Tout décoché : aucun, donc aucun envoi automatique."""
    _d = (doc or {}).get("delais")
    return list(PALIERS_AUTO) if _d is None else [p for p in _d if p in PALIERS_AUTO]


def auto_doit_envoyer(echeance, delais, jour) -> bool:
    """PUR. Le jour est-il ouvert pour un rappel automatique ? Le délai de 7 jours et le plafond sont dans `decision_relance`."""
    _coches = [PALIERS_AUTO[p] for p in PALIERS_AUTO if p in (delais or [])]
    if not _coches:
        return False
    try:
        _j = (datetime.strptime(jour, "%Y-%m-%d") - datetime.strptime(echeance, "%Y-%m-%d")).days
    except (TypeError, ValueError):
        return False
    return min(_coches) <= _j <= AUTO_JOURS_APRES_MAX


def adresse_de_test(destinataire, autorisee) -> bool:
    """PUR. V651 : égalité stricte avec l'unique adresse autorisée. Aucune adresse rangée : personne."""
    _d, _a = str(destinataire or "").strip().lower(), str(autorisee or "").strip().lower()
    return bool(_a) and "@" in _a and _d == _a


def auto_heure_ouvree(maintenant=None) -> bool:
    _z = (maintenant or datetime.now(timezone.utc)).astimezone(ZoneInfo("Europe/Zurich"))
    return _z.weekday() < 5 and 8 <= _z.hour < 18


# ═══════════════════════════ LECTURES ═══════════════════════════

async def _exiger_coach(request: Request):
    """La même porte que `GET /discount-codes/echeances` : un jeton signé, jamais un en-tête."""
    _email = (coach_jwt_email(request) or "").lower().strip()
    _admin = _email == SUPER_ADMIN_EMAIL.lower()
    # La règle existante : un compte désactivé ou en attente de validation n'écrit plus à personne.
    if not _admin and not await v646_compte_coach_autorise(db, _email):
        raise HTTPException(status_code=403, detail="Authentification coach requise — reconnectez-vous")
    return _email, _admin


async def _drapeau(nom: str) -> bool:
    _f = await db.feature_flags.find_one({"id": "feature_flags"}, {"_id": 0, nom: 1}) or {}
    return _f.get(nom) is True


async def _envoi_reel_autorise() -> bool:
    return await _drapeau(DRAPEAU_ENVOI_REEL)


async def _envoi_autorise_vers(destinataire: str) -> bool:
    """Envoi réel ouvert à tous ; ou mode test, vers l'unique adresse rangée en base."""
    if await _drapeau(DRAPEAU_ENVOI_REEL):
        return True
    if not await _drapeau(DRAPEAU_TEST):
        return False
    _doc = await db[COL_REGLAGES].find_one({"_id": ID_TEST_ADRESSE}, {"adresse": 1}) or {}
    return adresse_de_test(destinataire, _doc.get("adresse"))


def _peut_voir(code_doc, sub, appelant, admin) -> bool:
    """PUR. Un partenaire ne voit que SES codes, et jamais l'abonnement marqué d'un autre coach."""
    if not code_doc or not v617_visible_par(code_doc, appelant, admin):
        return False
    _proprio = str((sub or {}).get("coach_id") or "").strip().lower()
    return admin or not _proprio or _proprio == appelant


def _acces(ctx: dict, appelant, admin) -> bool:
    """PUR. Toutes les fiches de ce code, pas la première : un doublon ne donne pas accès au client d'un autre."""
    if not ctx or not ctx.get("code"):
        return False
    return _peut_voir(ctx.get("code"), ctx.get("sub"), appelant, admin) and all(
        v617_visible_par(c, appelant, admin) for c in ctx.get("codes") or [])


def _cle_reglages(proprio) -> str:
    """Les fiches de la plateforme, avec ou sans propriétaire, partagent les réglages du super-admin."""
    return proprio if proprio not in COACHS_BASSI else SUPER_ADMIN_EMAIL.lower()


async def _contexte(sub_id: str) -> dict:
    """Tout est relu en base à chaque appel : rien de ce que le navigateur envoie n'est cru."""
    _sub = await db.subscriptions.find_one({"id": sub_id}, {"_id": 0})
    if not _sub or not str(_sub.get("code") or "").strip():
        return {}
    _re = {"$regex": "^%s$" % re.escape(str(_sub["code"]).strip()), "$options": "i"}
    _codes = await db.discount_codes.find({"code": _re}, {"_id": 0}).to_list(20)
    _tous = await db.subscriptions.find({"code": _re}, {"_id": 0}).to_list(50)
    _code = _codes[0] if _codes else None
    _actuel, _motif = abo_actuel_du_code(_tous, (_code or {}).get("assignedEmail"))
    # Ce rappel ne vise que l'abonnement ACTUEL : un abonnement remplacé ne reçoit rien.
    if _motif == "unique" and (_actuel or {}).get("id") != _sub.get("id"):
        _motif = "aucun"
    _proprio = str((_code or {}).get("coach_id") or "").strip().lower()
    _reg = await db[COL_REGLAGES].find_one({"_id": _cle_reglages(_proprio)}, {"signature": 1, "modele": 1}) or {}
    return {"sub": _sub, "code": _code, "motif_abo": _motif, "codes_trouves": len(_codes), "codes": _codes,
            "actif_sur_code": any(str(x.get("status") or "").strip().lower() == "active" for x in _tous),
            "proprio": _proprio, "signature": None if _proprio in COACHS_BASSI else _reg.get("signature"), "modele": _reg.get("modele")}


def cle_membre(proprio, sub, code_doc=None) -> list:
    """PUR. Les clés d'exclusion de ce membre chez ce coach : ses adresses, sinon son code."""
    _coach = _cle_reglages(str(proprio or "").strip().lower())
    _mails = [str(x or "").strip().lower() for x in ((sub or {}).get("email"), (code_doc or {}).get("assignedEmail"))]
    _mails = [m for m in dict.fromkeys(_mails) if m]
    _qui = _mails or ["code:%s" % str((sub or {}).get("code") or "").strip().upper()]
    return ["%s|%s" % (_coach, q) for q in _qui]


def abonnement_suspendu(sub) -> bool:
    """PUR. Inactif, résilié, expiré ou épuisé : les rappels s'arrêtent, le solde reste."""
    return str((sub or {}).get("status") or "").strip().lower() not in STATUTS_SANS_SUSPENSION


async def _exclusion(ctx: dict) -> dict:
    """La fiche d'exclusion de ce membre chez ce coach, active ou réactivée. Relue à chaque appel."""
    _cles = cle_membre(ctx.get("proprio"), ctx.get("sub"), ctx.get("code"))
    _docs = await db[COL_EXCLUSIONS].find({"_id": {"$in": _cles}}).to_list(5)
    return next((d for d in _docs if d.get("actif") is True), None) or (_docs[0] if _docs else None)


async def _jour_de_reprise(ctx: dict) -> str:
    """Après une réactivation ou une reprise : l'automatique ne revient pas sur les échéances déjà passées."""
    _jours = [str((await _exclusion(ctx) or {}).get("reprise_jour") or "")]
    _jours += [str(d.get("reprise_jour") or "") for d in await _docs_abonnement(ctx["sub"].get("id"), ctx) if d.get("statut") == "reprise"]
    return max(_jours)


async def _verdict(ctx: dict, maintenant=None, ignorer_fenetre=False) -> dict:
    if (await _exclusion(ctx) or {}).get("actif") is True:
        return {"ok": False, "motif": "membre_exclu", "message": MOTIFS["membre_exclu"]}
    if abonnement_suspendu(ctx.get("sub")) and not ctx.get("actif_sur_code"):
        return {"ok": False, "motif": "abonnement_suspendu", "message": MOTIFS["abonnement_suspendu"]}
    if ctx.get("codes_trouves", 0) > 1:
        return {"ok": False, "motif": "code_ambigu", "message": MOTIFS["code_ambigu"]}
    _v = eligibilite(ctx.get("sub"), ctx.get("code"), ctx.get("motif_abo"),
                     maintenant, ignorer_fenetre)
    if _v["ok"] and not signature_du_code(ctx.get("code"), ctx.get("signature")):
        return {"ok": False, "motif": "signature_manquante", "message": MOTIFS["signature_manquante"]}
    if _v["ok"] and _refus_email is not None and await _refus_email("email", _v["destinataire"]):
        return {"ok": False, "motif": "refus_email", "message": MOTIFS["refus_email"]}
    return _v


def modele_enregistre(modele) -> dict:
    """PUR. Un modèle rangé repasse le contrôle à chaque usage : s'il ne le passe plus, le texte d'origine reprend."""
    if not isinstance(modele, dict):
        return None
    return modele if not motif_modele_refuse(modele.get("sujet") or sujet_defaut(), modele.get("corps")) else None


def _message_de(ctx: dict, verdict: dict, modele: dict = None) -> dict:
    return construire_message(_prenom(ctx["sub"].get("name")), verdict["reste"], verdict["devise"], verdict["echeance"],
                              signature_du_code(ctx.get("code"), ctx.get("signature")), verdict.get("paiement_actuel"),
                              modele or modele_enregistre(ctx.get("modele")))


def _empreinte_message(sub_id, verdict, msg) -> str:
    return empreinte(sub_id, verdict, msg["sujet"] + "\n" + msg["texte"])


def _modele_saisi(sujet, corps) -> dict:
    """Le texte envoyé par le navigateur, contrôlé ; None si le coach n'a rien modifié."""
    if sujet is None and corps is None:
        return None
    _m = motif_modele_refuse(sujet, corps)
    if _m:
        raise HTTPException(status_code=400, detail={"type": "modele_refuse", "message": _m})
    # L'objet d'origine reste calculé : « deuxième » deviendrait faux au 3e paiement.
    return {"sujet": "" if sujet.strip() in OBJETS_RAPPEL else sujet.strip(), "corps": corps.strip()}


def _delai_valide(v) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) and DELAI_RELANCE_MIN <= v <= DELAI_RELANCE_MAX else DELAI_RELANCE_DEFAUT


async def _delai_relance(ctx: dict) -> int:
    """Le délai du coach PROPRIÉTAIRE du code : le super-admin qui agit sur un code partenaire le respecte."""
    _r = await db[COL_REGLAGES].find_one({"_id": _cle_reglages(ctx.get("proprio"))}, {"delai_relance_jours": 1}) or {}
    return _delai_valide(_r.get("delai_relance_jours"))


async def _docs_abonnement(sub_id: str, ctx: dict = None) -> list:
    """Les envois de cet abonnement, de ce code, et de cette personne chez ce coach : remplacer ou renouveler
    un abonnement ne doit effacer ni un envoi à vérifier, ni le délai, ni le compteur. Jamais ceux d'un autre coach."""
    _ctx = ctx or {}
    _ou = [{"subscription_id": sub_id}]
    _proprio = _ctx.get("proprio", "")
    # Les fiches anciennes de la plateforme n'ont pas de propriétaire : toutes valent le même coach.
    _coachs = list(COACHS_BASSI) if _proprio in COACHS_BASSI else [_proprio]
    _dest = str((_ctx.get("sub") or {}).get("email") or "").strip().lower()
    if _dest:
        _ou.append({"destinataire": _dest, "coach_id": {"$in": _coachs}})
    _code = str((_ctx.get("sub") or {}).get("code") or "").strip()
    if _code:
        _ou.append({"code": {"$regex": "^%s$" % re.escape(_code), "$options": "i"}, "coach_id": {"$in": _coachs}})
    _docs = await db[COL_RAPPELS].find({"palier": PALIER_MANUEL, "$or": _ou}).to_list(200)
    _autres = {d.get("subscription_id") for d in _docs if d.get("subscription_id") != sub_id}
    if _autres:
        _clos = {}
        async for _s in db.subscriptions.find({"id": {"$in": list(_autres)}}, {"_id": 0, "id": 1, "status": 1, "montant_encaisse": 1}):
            if str(_s.get("status") or "").strip().lower() != "active":
                _clos[_s.get("id")] = _nombre(_s.get("montant_encaisse"))
        for _d in _docs:
            # Le total du rappel, pas le total actuel : le baisser ne solde aucune dette.
            _e, _t = _clos.get(_d.get("subscription_id")), _nombre(_d.get("total_au_rappel"))
            _d["_abonnement_solde"] = _e is not None and _t is not None and _e >= _t - 0.005
    return _docs


def _vue_envoi(decision: dict, delai: int, admin: bool = False) -> dict:
    """Ce que l'écran doit dire de l'envoi suivant. La route d'envoi redécide de toute façon."""
    _a = decision["action"]
    _verif = decision.get("type") == "incertain_bloque"
    return {"peut_envoyer": _a != "refus", "action": _a, "type": decision.get("type"),
            "etape": etape_du_rang(decision.get("numero") or decision.get("rang")), "prochaine_le": decision.get("prochaine_le"),
            "numero": decision.get("numero") or decision.get("numero_suivant"),
            "message": decision.get("message", ""), "delai_jours": delai, "a_verifier": _verif, "verification_admin": _verif and admin}


def _ligne_historique(doc) -> dict:
    return {"palier": doc.get("palier"), "rang": doc.get("rang"), "etape": etape_du_rang(doc.get("numero") or doc.get("rang")),
            "echeance": doc.get("echeance"), "statut": doc.get("statut"), "montant": doc.get("montant"),
            "devise": doc.get("devise"), "destinataire": doc.get("destinataire"), "envoye_le": doc.get("envoye_le"),
            "maj_le": doc.get("maj_le"), "envoye_par": doc.get("envoye_par"), "tentatives": doc.get("tentatives"),
            "mode_envoi": doc.get("mode_envoi") or "manuel", "sujet": doc.get("sujet"),
            "montant_confirme": doc.get("montant_confirme"), "motif_action": doc.get("motif_action"), "annule_le": doc.get("annule_le")}


async def _historique(sub_id: str) -> list:
    _docs = await db[COL_RAPPELS].find({"subscription_id": sub_id}).sort([("cree_le", -1), ("rang", -1)]).to_list(100)
    return [_ligne_historique(d) for d in _docs]


def statut_affiche(verdict, decision, programme_le=None):
    """PUR. Programmé, Envoyé, Annulé, Suspendu ou Exclu ; rien si la ligne attend simplement le coach."""
    _m = (verdict or {}).get("motif")
    if _m == "membre_exclu":
        return {"code": "exclu", "libelle": "Exclu"}
    if _m == "abonnement_suspendu":
        return {"code": "suspendu", "libelle": "Suspendu"}
    _d = decision or {}
    if _d.get("type") == "annule_tous":
        return {"code": "annule", "libelle": "Annulé"}
    if _d.get("type") in ("deja_envoye", "maximum_atteint"):
        if (_d.get("doc") or {}).get("statut") == "annule":
            return {"code": "annule", "libelle": "Annulé"}
        return {"code": "envoye", "libelle": "Envoyé"}
    if programme_le:
        return {"code": "programme", "libelle": "Programmé", "date": programme_le}
    return None


async def _ligne_liste(ctx: dict, maintenant: datetime, admin: bool = False) -> dict:
    """Une ligne de la section « Rappels de paiement ». Lecture seule."""
    _sub = ctx["sub"]
    _sid = _sub.get("id")
    _vue = suivi_paiement_lire(_sub)
    _v = await _verdict(ctx, maintenant)
    _ech = _vue.get("prochaine_echeance")
    _nb, _act = _vue.get("nb_paiements"), _vue.get("paiement_actuel")
    _ligne = {"subscription_id": _sid, "code": _sub.get("code"), "nom": _sub.get("name") or "",
              "reste_a_payer": _vue.get("reste_a_payer"), "devise": _sub.get("devise") or "CHF", "prochaine_echeance": _ech,
              "en_retard": bool(_ech) and _ech < v617_jour_local(maintenant),
              "paiement_suivant": ("%d/%d" % (_act + 1, _nb)) if _nb and _act and _act < _nb else None,
              "mode_paiement": classer_mode_paiement(_sub)["libelle"], "possible": bool(_v["ok"]), "motif": _v.get("motif"), "message": _v.get("message", ""),
              "verification_requise": bool(_v.get("verification_requise")), "envoi": None}
    _dec = None
    # Une échéance lointaine n'est pas encore envoyable à la main, mais son rappel automatique peut déjà être annulé.
    _va = await _verdict(ctx, maintenant, ignorer_fenetre=True) if _v.get("motif") == "hors_fenetre" else _v
    if _va["ok"]:
        _delai = await _delai_relance(ctx)
        _dec = decision_relance(await _docs_abonnement(_sid, ctx), _delai, maintenant, paiement_attendu(_sid, _sub))
    if _v["ok"]:
        _ligne["envoi"] = _vue_envoi(_dec, _delai, admin)
    # V652 : le statut affiché et ce que le menu « ⋯ » peut proposer. Les routes redécident de toute façon.
    _reg = await db[COL_REGLAGES].find_one({"_id": _cle_reglages(ctx.get("proprio"))}, {"mode": 1, "delais": 1, "auto_actif_depuis": 1}) or {}
    _auto = _reg.get("mode") == MODE_AUTOMATIQUE and await _drapeau(DRAPEAU_AUTO)
    _jalons = []
    _reprise = await _jour_de_reprise(ctx)
    if _auto and _dec and _dec["action"] != "refus" and not _va.get("incomplet") and _ech and _ech >= max(str(_reg.get("auto_actif_depuis") or "9999"), _reprise):
        try:
            _jalons = jalons_simulation(_ech, delais_du_reglage(_reg), maintenant, _delai)
        except ValueError:
            _jalons = []
    _ligne["numero_rappel"] = (_dec or {}).get("numero") or (_dec or {}).get("numero_suivant")
    _ligne["statut_rappel"] = statut_affiche(_va, _dec, _jalons[0]["date"] if _jalons else None)
    _exclu = _v.get("motif") == "membre_exclu"
    _ligne["actions"] = {"annuler_un": bool(_dec) and (_dec["action"] != "refus" or (_dec.get("type") == "deja_envoye" and (_dec.get("numero_suivant") or 9) <= MAX_RAPPELS_PAR_ECHEANCE)),
                         "annuler_tous": bool(_dec) and _dec.get("type") != "annule_tous", "reprendre": bool(_dec) and _dec.get("type") == "annule_tous",
                         "exclure": not _exclu, "reactiver": _exclu}
    return _ligne


# ═══════════════════════════ ENVOI ═══════════════════════════

def _exiger_permis(decision: dict) -> None:
    """Lève 409 si l'historique interdit ce message. Une seule traduction, pour l'envoi et la réservation."""
    if decision["action"] == "refus":
        _detail = {"type": decision["type"], "message": decision.get("message", "")}
        if decision.get("prochaine_le"):
            _detail["prochaine_le"] = decision["prochaine_le"]
        if decision["type"] == "deja_envoye":
            _detail["envoye_le"] = (decision.get("doc") or {}).get("envoye_le")
        raise HTTPException(status_code=409, detail=_detail)


async def _docs_interrompus_inscrits(sub_id: str, maintenant: datetime, ctx: dict = None) -> list:
    """Un processus disparu pendant l'appel : on l'écrit, l'historique doit dire la vérité."""
    _docs = await _docs_abonnement(sub_id, ctx)
    _marques = False
    for _x in _docs:
        if _x.get("statut") == "en_cours" and _statut_effectif(_x, maintenant) == "incertain":
            await db[COL_RAPPELS].update_one({"_id": _x["_id"], "statut": "en_cours", "maj_le": _x.get("maj_le")},
                                             {"$set": {"statut": "incertain", "erreur": "interrompu", "maj_le": maintenant.isoformat()}})
            _marques = True
    return await _docs_abonnement(sub_id, ctx) if _marques else _docs


async def _reserver(sub_id: str, base: dict, maintenant: datetime, delai: int, ctx: dict = None, etat_vu: str = None, paiement: dict = None) -> dict:
    """La SEULE porte vers le fournisseur. Rend le document réservé, ou lève 409. Atomique."""
    _iso = maintenant.isoformat()
    _occupe = {"type": "en_cours", "message": MSG_EN_COURS}
    _d = decision_relance(await _docs_interrompus_inscrits(sub_id, maintenant, ctx), delai, maintenant, paiement)
    _exiger_permis(_d)
    if etat_vu is not None and etat_decision(_d) != etat_vu:
        raise HTTPException(status_code=409, detail=_occupe)      # un autre essai est passé depuis l'aperçu
    _ex = _d.get("doc") or {}
    if _d["action"] == "nouveau":
        _rang = _d["rang"]
        _cle = cle_envoi(sub_id, _rang)
        _doc = dict(base, _id=_cle, rang=_rang, numero=_d["numero"], statut="en_cours", tentatives=1,
                    idempotency_key=cle_idempotence(_cle, 1), premier_essai_le=_iso, cree_le=_iso, maj_le=_iso)
        try:
            await db[COL_RAPPELS].insert_one(_doc)     # une seule requête gagne ce rang
        except DuplicateKeyError:
            raise HTTPException(status_code=409, detail=_occupe)
        return await _seul_en_cours(sub_id, _doc, ctx, maintenant, _occupe, delai, paiement)
    # reessai : refus certain, rien n'est parti. Nouvelle clé (Resend garde aussi les refus), donc nouvelle date.
    _maj = {"$set": dict(base, statut="en_cours", numero=_d["numero"], maj_le=_iso, premier_essai_le=_iso,
                         idempotency_key=cle_idempotence(_ex["_id"], int(_ex.get("tentatives") or 1) + 1)),
            "$inc": {"tentatives": 1}}
    _pris = await db[COL_RAPPELS].find_one_and_update(
        {"_id": _ex["_id"], "statut": "echec", "maj_le": _ex.get("maj_le")}, _maj, return_document=True)
    if not _pris:
        raise HTTPException(status_code=409, detail=_occupe)
    return await _seul_en_cours(sub_id, _pris, ctx, maintenant, _occupe, delai, paiement)


async def _seul_en_cours(sub_id: str, doc: dict, ctx: dict, maintenant: datetime, occupe: dict, delai: int = DELAI_RELANCE_DEFAUT, paiement: dict = None) -> dict:
    """Le rang est unique par abonnement, la personne peut en avoir deux. Après avoir réservé, chacun relit
    tout l'historique sans sa propre ligne, et rejoue la règle : un envoi en cours, tout juste terminé ou
    incertain le fait renoncer, sans appeler le fournisseur. Les deux peuvent renoncer, jamais les deux
    passer. L'essai reste un `echec` : rien n'est parti."""
    _autres = [x for x in await _docs_abonnement(sub_id, ctx) if x.get("_id") != doc["_id"]]
    if decision_relance(_autres, delai, maintenant, paiement)["action"] == "refus":
        await _clore_sans_succes(doc, "echec", "envoi_concurrent")
        raise HTTPException(status_code=409, detail=occupe)
    return doc


async def _clore_sans_succes(doc: dict, statut: str, erreur: str) -> bool:
    """Échec ou incertitude : seulement si CET essai est toujours celui en cours. Réponse tardive = sans effet."""
    _r = await db[COL_RAPPELS].update_one({"_id": doc["_id"], "statut": "en_cours", "tentatives": doc.get("tentatives")},
                                          {"$set": {"statut": statut, "erreur": erreur, "maj_le": datetime.now(timezone.utc).isoformat()}})
    return bool(getattr(_r, "modified_count", 0))


async def _appel_fournisseur(cle: str, params: dict, options: dict):
    return await asyncio.to_thread(
        _rc.emails("rappels_paiement:envoyer", critique=False, type_email="rappel_paiement",
                   reference=cle, sdk=resend).send, params, options)


def date_fournisseur(valeur):
    """PUR. Les dates de Resend varient (espace, « +00 », « Z », fraction courte). None si illisible."""
    _t = str(valeur or "").strip().replace(" ", "T")
    _t = re.sub(r"Z$", "+00:00", _t)
    _t = re.sub(r"([+-]\d{2})$", r"\1:00", _t)
    _t = re.sub(r"\.(\d{1,6})\d*", lambda m: "." + m.group(1).ljust(6, "0"), _t)
    return _instant(_t)


def adresses_fiche(email):
    """PUR. Les adresses d'une fiche du fournisseur, ou None si elles sont absentes ou illisibles."""
    _a = (email or {}).get("to") if isinstance(email, dict) else None
    _a = _a if isinstance(_a, list) else [_a]
    _sortie = []
    for _x in _a:
        _ad = parseaddr(_x)[1].strip().lower() if isinstance(_x, str) else ""
        if not RE_EMAIL.match(_ad):
            return None
        _sortie.append(_ad)
    return _sortie or None


def objet_fiche(email):
    """PUR. L'objet d'une fiche, sans espaces autour, ou None s'il est absent."""
    _o = (email or {}).get("subject") if isinstance(email, dict) else None
    return _o.strip() if isinstance(_o, str) and _o.strip() else None


def preuve_conforme(email, doc) -> str:
    """PUR. Cette fiche du fournisseur prouve-t-elle CET envoi ? Chaîne vide si oui, sinon le motif."""
    if not isinstance(email, dict):
        return "Réponse du fournisseur illisible."
    if str(doc.get("destinataire") or "").lower() not in (adresses_fiche(email) or []):
        return "Le destinataire ne correspond pas."
    if objet_fiche(email) not in OBJETS_RAPPEL + (doc.get("sujet"),):
        return "L'objet ne correspond pas à un rappel de paiement."
    if "notifications@afroboost.com" not in str(email.get("from") or ""):
        return "L'expéditeur ne correspond pas."
    _cree = date_fournisseur(email.get("created_at"))
    _deb = _instant(doc.get("premier_essai_le"))
    if _cree is None or _deb is None:
        return "Date du fournisseur illisible."
    if not _deb - timedelta(minutes=10) <= _cree <= _deb + timedelta(hours=24):
        return "La date de cet e-mail ne correspond pas à cet essai."
    return ""


async def lire_periode_fournisseur(debut: datetime, fin: datetime):
    """Les e-mails Resend de cette période, ou None si la période n'est pas ENTIÈREMENT couverte.

    Il faut atteindre un e-mail plus ancien que le début : une liste qui s'arrête avant (fin de
    rétention, petite liste) ne prouve rien. Dates illisibles ou ordre inattendu : None.
    """
    _trouves, _apres, _precedent = [], None, None
    for _ in range(LISTE_PAGES_MAX):
        _params = {"limit": 100}
        if _apres:
            _params["after"] = _apres
        _r = await asyncio.to_thread(resend.Emails.list, _params)
        _data = _r.get("data") if isinstance(_r, dict) else None
        if not isinstance(_data, list) or not _data:
            return None
        _couvert = False
        for _m in _data:                      # la page entière : un désordre après un e-mail ancien annule tout
            _q = date_fournisseur((_m or {}).get("created_at"))
            if _q is None or (_precedent is not None and _q > _precedent):
                return None
            _precedent = _q
            _couvert = _couvert or _q < debut
            if debut <= _q <= fin:
                if adresses_fiche(_m) is None or objet_fiche(_m) is None:
                    return None               # une fiche illisible peut être l'e-mail cherché
                _trouves.append(_m)
        if _couvert:
            return _trouves
        if not _r.get("has_more") or not _data[-1].get("id"):
            return None
        _apres = _data[-1]["id"]
    return None


class PreuveEnvoi(BaseModel):
    model_config = ConfigDict(extra="ignore")
    resend_id: str = ""
    verifier_absence: bool = False


class EnvoiRappel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    empreinte: str = ""
    confirmation: bool = False
    montant_confirme: object = None       # seulement si le suivi est incomplet : la saisie du coach
    sujet: object = None                  # texte modifié : contrôlé et rendu par le serveur
    corps: object = None


class ApercuPersonnalise(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sujet: object = None
    corps: object = None


class DemandeIA(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sujet: object = None
    corps: object = None
    ton: str = "chaleureux"


@router.get("/api/rappels-paiement/reglages")
async def lire_reglages(request: Request):
    _email, _ = await _exiger_coach(request)
    _doc = await db[COL_REGLAGES].find_one({"_id": _email}) or {}
    return {"mode": _doc.get("mode") if _doc.get("mode") in MODES else MODE_MANUEL,
            "delais": delais_du_reglage(_doc),
            "delai_relance_jours": _delai_valide(_doc.get("delai_relance_jours")),
            "signature_officielle": _email in COACHS_BASSI,
            "signature": _doc.get("signature") or {"nom": "", "activite": ""},
            "automatisation_disponible": await _drapeau(DRAPEAU_AUTO), "auto_actif_depuis": _doc.get("auto_actif_depuis"),
            "modele": _doc.get("modele") or None, "modele_defaut": {"sujet": sujet_defaut(), "corps": CORPS_DEFAUT},
            "envoi_reel": await _envoi_reel_autorise()}


@router.put("/api/rappels-paiement/reglages")
async def ecrire_reglages(request: Request):
    """Le choix du coach. Passer en Automatique est un acte explicite, daté : les échéances antérieures restent à l'écart."""
    _email, _ = await _exiger_coach(request)
    try:
        _corps = await request.json()
    except Exception:  # noqa: BLE001
        _corps = None
    if not isinstance(_corps, dict):
        raise HTTPException(status_code=400, detail="Réglage illisible.")
    _mode = _corps.get("mode")
    if _mode not in MODES:
        raise HTTPException(status_code=400, detail="Mode inconnu : MANUEL ou AUTOMATIQUE.")
    _delais = _corps.get("delais", list(PALIERS_AUTO))
    if not isinstance(_delais, list) or not all(isinstance(d, str) and d in PALIERS_AUTO for d in _delais):
        raise HTTPException(status_code=400, detail="Délais inconnus : J-3, J0 ou J+3.")
    _propres = [p for p in PALIERS_AUTO if p in _delais]
    _champs = {"mode": _mode, "delais": _propres, "maj_le": datetime.now(timezone.utc).isoformat()}
    _avant = await db[COL_REGLAGES].find_one({"_id": _email}, {"mode": 1}) or {}
    _operation = {}
    if _mode == MODE_AUTOMATIQUE and _avant.get("mode") != MODE_AUTOMATIQUE:
        if _corps.get("confirmation_auto") is not True:
            raise HTTPException(status_code=400, detail="Confirme l'activation de l'automatique : des e-mails réels partiront sans que tu sois connecté.")
        _champs["auto_actif_depuis"] = v617_jour_local()
    elif _mode == MODE_MANUEL:
        _operation["$unset"] = {"auto_actif_depuis": ""}
    if "delai_relance_jours" in _corps:
        _j = _corps["delai_relance_jours"]
        if not isinstance(_j, int) or isinstance(_j, bool) or not DELAI_RELANCE_MIN <= _j <= DELAI_RELANCE_MAX:
            raise HTTPException(status_code=400, detail="Délai de relance : entre %d et %d jours." % (DELAI_RELANCE_MIN, DELAI_RELANCE_MAX))
        _champs["delai_relance_jours"] = _j
    await db[COL_REGLAGES].update_one({"_id": _email}, dict(_operation, **{"$set": _champs}), upsert=True)
    _doc = await db[COL_REGLAGES].find_one({"_id": _email}) or {}
    return {"mode": _mode, "delais": _propres, "delai_relance_jours": _delai_valide(_doc.get("delai_relance_jours")),
            "automatisation_disponible": await _drapeau(DRAPEAU_AUTO), "auto_actif_depuis": _doc.get("auto_actif_depuis")}


@router.put("/api/rappels-paiement/modele")
async def ecrire_modele(corps: ApercuPersonnalise, request: Request):
    """Le modèle du coach pour ses envois futurs. Le sien seulement."""
    _email, _ = await _exiger_coach(request)
    _m = _modele_saisi(corps.sujet, corps.corps)
    if not _m:
        raise HTTPException(status_code=400, detail={"type": "modele_refuse", "message": "Objet ou message illisible."})
    await db[COL_REGLAGES].update_one({"_id": _cle_reglages(_email)}, {"$set": {"modele": _m, "maj_le": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    return {"modele": _m}


@router.delete("/api/rappels-paiement/modele")
async def effacer_modele(request: Request):
    """Retour au texte validé."""
    _email, _ = await _exiger_coach(request)
    await db[COL_REGLAGES].update_one({"_id": _cle_reglages(_email)}, {"$unset": {"modele": ""}})
    return {"modele": None, "modele_defaut": {"sujet": sujet_defaut(), "corps": CORPS_DEFAUT}}


_appels_ia = {}


def nettoyer_proposition(sujet, corps, sujet_coach) -> dict:
    """PUR. Deux écarts sans risque, réparés plutôt que refusés : un objet vide garde celui du coach, et une
    devise écrite après {montant} est retirée (le serveur l'y met déjà). Le reste passe par le contrôle habituel."""
    _s = sujet.strip() if isinstance(sujet, str) else ""
    _c = corps.strip() if isinstance(corps, str) else ""
    _c = re.sub(r"(\{montant\})\s*(?:chf|eur|euros?|€|francs?(?:\s+suisses?)?|frs?\.?)(?!\w)", r"\1", _c, flags=re.IGNORECASE)
    return {"sujet": _s or sujet_coach, "corps": _c}


async def appeler_ia(systeme: str, texte: str) -> str:
    """Le même client OpenAI que le reste du site. Remplacé par un faux dans les tests."""
    from openai import OpenAI
    _cl = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"), timeout=15.0, max_retries=0)
    _r = await asyncio.wait_for(asyncio.to_thread(
        _cl.chat.completions.create, model="gpt-4o-mini", temperature=0.5, max_tokens=500, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": systeme}, {"role": "user", "content": texte}]), timeout=18.0)
    return (_r.choices[0].message.content or "").strip()


@router.post("/api/rappels-paiement/aide-ia")
async def aide_ia(demande: DemandeIA, request: Request):
    """Une PROPOSITION : rien n'est enregistré ni remplacé. Le texte part sans aucune donnée client,
    avec les variables, et la proposition repasse par le même contrôle qu'une saisie du coach."""
    _email, _ = await _exiger_coach(request)
    if demande.ton not in TONS_IA:
        raise HTTPException(status_code=400, detail={"type": "ton_inconnu", "message": "Ton inconnu."})
    _m = _modele_saisi(demande.sujet, demande.corps)
    if not _m:
        raise HTTPException(status_code=400, detail={"type": "modele_refuse", "message": "Objet ou message illisible."})
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail={"type": "ia_indisponible", "message": "L'aide IA n'est pas disponible pour le moment."})
    _heure = datetime.now(timezone.utc).timestamp() - 3600
    _recents = [t for t in _appels_ia.get(_email, []) if t > _heure]
    if len(_recents) >= IA_LIMITE_HEURE:
        raise HTTPException(status_code=429, detail={"type": "ia_limite", "message": "Trop de demandes : réessaie dans une heure."})
    _appels_ia[_email] = _recents + [datetime.now(timezone.utc).timestamp()]
    # V653 : la consigne dit tout ce que le contrôle refuse, sinon l'IA écrit un texte normal que le contrôle rejette.
    _sys = ("Tu reformules en français un e-mail de rappel de paiement d'un coach de fitness à son membre. Ton : %s. Reste court et humain. "
            "Le solde peut déjà être réglé : n'accuse jamais, ne menace jamais, n'affirme pas que la personne n'a pas payé. "
            "OBJET : une seule ligne de texte simple, sans aucune variable ni accolade, sans chiffre. "
            "MESSAGE : garde exactement {bonjour}, {montant} et {echeance}, une fois chacune, sans en ajouter. "
            "{montant} contient déjà la devise : n'écris jamais CHF, francs ou un autre mot de devise. {echeance} contient déjà la date. "
            "N'écris aucun chiffre, aucun nom de mois, aucun lien, aucun numéro, aucune adresse. "
            "Pas de signature ni de formule de fin : elles sont ajoutées automatiquement. "
            'Réponds uniquement en JSON : {"sujet": "...", "corps": "..."}.' % TONS_IA[demande.ton])
    # L'objet RÉEL : `_modele_saisi` vide l'objet d'origine pour l'enregistrement, l'IA doit quand même le lire.
    _sujet_reel = demande.sujet.strip()
    _texte = json.dumps({"sujet": _sujet_reel, "corps": _m["corps"]}, ensure_ascii=False)
    _motif = ""
    for _essai in (1, 2):
        _demande = _texte if not _motif else _texte + "\n\nTa proposition précédente a été refusée : " + _motif
        try:
            _brut = json.loads(await appeler_ia(_sys, _demande))
            _prop = nettoyer_proposition(_brut.get("sujet"), _brut.get("corps"), _sujet_reel)
        except Exception as _err:  # noqa: BLE001
            # Le type et le code d'erreur seulement : jamais le texte, ni la réponse du fournisseur.
            logger.warning("[V653] aide IA : erreur %s (statut %s, code %s, essai %d)", type(_err).__name__, getattr(_err, "status_code", "-"), getattr(_err, "code", "-"), _essai)
            raise HTTPException(status_code=503, detail={"type": "ia_erreur", "message": "L'aide IA n'a pas répondu. Ton texte n'a pas changé."})
        _motif = motif_modele_refuse(_prop["sujet"], _prop["corps"])
        if not _motif:
            return {"proposition": _prop, "ton": demande.ton}
        # Le motif vient de nos règles : il ne contient aucun texte du coach.
        logger.warning("[V653] aide IA : proposition refusée (essai %d) : %s", _essai, _motif)
    raise HTTPException(status_code=422, detail={"type": "ia_refusee", "message": "La proposition n'a pas passé le contrôle. Ton texte n'a pas changé. (%s)" % _motif})


@router.put("/api/rappels-paiement/signature")
async def ecrire_signature(request: Request):
    """Les deux champs de la signature d'un partenaire. Un refus explique pourquoi, champ par champ."""
    _email, _ = await _exiger_coach(request)
    if _email in COACHS_BASSI:
        raise HTTPException(status_code=400, detail={"type": "signature_officielle", "message": "La signature officielle d'Afroboost n'est pas modifiable."})
    try:
        _corps = await request.json()
    except Exception:  # noqa: BLE001
        _corps = None
    if not isinstance(_corps, dict):
        raise HTTPException(status_code=400, detail={"type": "nom_refuse", "champ": "nom", "message": "Signature illisible."})
    _nom = _corps.get("nom")
    _act = _corps.get("activite") or ""
    _m = motif_nom_refuse(_nom, NOM_PRO_MAX)
    if _m:
        raise HTTPException(status_code=400, detail={"type": "nom_refuse", "champ": "nom", "message": "Nom : " + _m})
    if _act:
        _m = motif_nom_refuse(_act, ACTIVITE_MAX)
        if _m:
            raise HTTPException(status_code=400, detail={"type": "nom_refuse", "champ": "activite", "message": "Activité : " + _m})
    if not isinstance(_act, str):
        raise HTTPException(status_code=400, detail={"type": "nom_refuse", "champ": "activite", "message": "Activité illisible."})
    if sum(c.isdigit() for c in _nom + _act) > NOM_CHIFFRES_MAX:
        raise HTTPException(status_code=400, detail={"type": "nom_refuse", "champ": "nom", "message": "Trop de chiffres au total : %d au plus." % NOM_CHIFFRES_MAX})
    _sig = {"nom": _nom.strip(), "activite": _act.strip()}
    await db[COL_REGLAGES].update_one({"_id": _email}, {"$set": {"signature": _sig, "maj_le": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    return {"signature": _sig, "apercu": signature_structuree(_sig)}


@router.get("/api/rappels-paiement/liste")
async def liste_rappels(request: Request):
    """Les soldes restants des abonnements ACTUELS visibles par ce coach. Lecture seule, 50 lignes au plus.
    Les abonnements exclus (Stripe…) restent listés avec leur motif : le coach doit comprendre."""
    _email, _admin = await _exiger_coach(request)
    _maintenant = datetime.now(timezone.utc)
    _lignes = []
    async for _s in db.subscriptions.find({"suivi_paiement": {"$type": "object"}, "status": {"$nin": ["superseded", "archived"]}}, {"_id": 0, "id": 1}):
        _ctx = await _contexte(_s.get("id"))
        if not _acces(_ctx, _email, _admin):
            continue
        if (suivi_paiement_lire(_ctx["sub"]).get("reste_a_payer") or 0) <= 0:
            continue
        # V652 : un abonnement inactif garde sa ligne, sauf si le même code a déjà un abonnement actif.
        if str(_ctx["sub"].get("status") or "").strip().lower() != "active" and (not abonnement_suspendu(_ctx["sub"]) or _ctx.get("actif_sur_code")):
            continue
        _lignes.append(await _ligne_liste(_ctx, _maintenant, _admin))
    _lignes.sort(key=lambda x: (x.get("motif") == "abonnement_suspendu", x.get("prochaine_echeance") or "9999"))
    return {"lignes": _lignes[:SIMULATION_MAX], "envoi_reel": await _envoi_reel_autorise()}


@router.get("/api/rappels-paiement/historique")
async def historique_rappels(request: Request):
    """Les 50 derniers envois de ce coach : date, destinataire, étape, résultat, coach. Super-admin : tous."""
    _email, _admin = await _exiger_coach(request)
    _filtre = {} if _admin else {"coach_id": _email}
    _docs = await db[COL_RAPPELS].find(_filtre).sort([("maj_le", -1)]).to_list(SIMULATION_MAX)
    return {"historique": [dict(_ligne_historique(d), code=d.get("code")) for d in _docs]}


@router.get("/api/rappels-paiement/simulation")
async def simuler_automatique(request: Request):
    """Ce que l'automatique FERAIT, en LECTURE SEULE : aucun envoi, aucune écriture, aucun jeton."""
    _email, _admin = await _exiger_coach(request)
    _reg = await db[COL_REGLAGES].find_one({"_id": _email}) or {}
    _delais = delais_du_reglage(_reg)
    _lignes = []
    async for _s in db.subscriptions.find({"suivi_paiement": {"$type": "object"}, "status": "active"}, {"_id": 0, "id": 1}):
        _ctx = await _contexte(_s.get("id"))
        if not _acces(_ctx, _email, _admin):
            continue
        _v = await _verdict(_ctx, ignorer_fenetre=True)
        _vue = suivi_paiement_lire(_ctx["sub"])
        _ech = _vue.get("prochaine_echeance")
        _exclu = _v.get("motif") if not _v["ok"] else ("suivi_incomplet" if _v.get("incomplet") else None)
        _depuis = _reg.get("auto_actif_depuis")
        _reprise = await _jour_de_reprise(_ctx)
        if _exclu is None and _ech and ((_depuis and _ech < _depuis) or _ech < _reprise):
            _exclu = "echeance_ancienne"
        _jalons, _msg_dec = [], ""
        if _ech and (_v["ok"] or _v.get("motif") != "suivi_incoherent"):
            _paie = paiement_attendu(_ctx["sub"].get("id"), _ctx["sub"])
            _docs = await _docs_abonnement(_ctx["sub"].get("id"), _ctx)
            _dec = decision_relance(_docs, await _delai_relance(_ctx), datetime.now(timezone.utc), _paie)
            if _dec["action"] == "refus" and _dec.get("type") != "deja_envoye":
                _exclu, _msg_dec = _exclu or _dec.get("type"), _dec.get("message", "")
            else:
                try:
                    _jalons = jalons_simulation(_ech, _delais, delai_jours=await _delai_relance(_ctx), prochaine=_dec.get("prochaine_le"),
                                                envoyes=sum(1 for d in _docs if d.get("statut") in ("envoye", "annule") and classer_paiement(d, _paie) == "meme"))
                except ValueError:
                    _jalons = []
        _lignes.append({"code": _ctx["sub"].get("code"), "nom": _ctx["sub"].get("name") or "",
                        "reste": _vue.get("reste_a_payer"), "echeance": _ech, "enverrait": _exclu is None,
                        "motif_exclusion": _exclu,
                        "message_exclusion": ("Case « en plusieurs fois » non cochée : à confirmer par le coach." if _exclu == "suivi_incomplet"
                                              else "Échéance antérieure à l'activation : jamais de rappel automatique." if _exclu == "echeance_ancienne"
                                              else _msg_dec or MOTIFS.get(_exclu, "")),
                        "jalons": _jalons})
    _lignes.sort(key=lambda x: x.get("echeance") or "")
    return {"simulation": True, "aucun_envoi": True, "automatisation_disponible": await _drapeau(DRAPEAU_AUTO),
            "delais": _delais, "lignes": _lignes[:SIMULATION_MAX]}


async def _reponse_apercu(sub_id: str, _ctx: dict, _email: str, _admin: bool, modele: dict = None) -> dict:
    _v = await _verdict(_ctx)
    _hist = await _historique(sub_id)
    _reel = await _envoi_reel_autorise()
    if not _v["ok"]:
        return {"possible": False, "motif": _v["motif"], "message": _v["message"], "historique": _hist, "envoi_reel": _reel}
    _msg = _message_de(_ctx, _v, modele)
    _delai = await _delai_relance(_ctx)
    _maintenant = datetime.now(timezone.utc)
    _dec = decision_relance(await _docs_abonnement(sub_id, _ctx), _delai, _maintenant, paiement_attendu(sub_id, _ctx["sub"]))
    _envoi = _vue_envoi(_dec, _delai, _admin)
    _m = modele or modele_enregistre(_ctx.get("modele")) or {}
    return {"possible": True, "envoi_reel": await _envoi_autorise_vers(_v["destinataire"]), "mode_paiement": classer_mode_paiement(_ctx["sub"])["libelle"],
            "empreinte": jeton_apercu(_empreinte_message(sub_id, _v, _msg), etat_decision(_dec), _email, _maintenant),
            "destinataire": _v["destinataire"],
            "reste": _v["reste"], "devise": _v["devise"], "echeance": _v["echeance"], "avertissement": _v.get("avertissement", ""),
            "verification_requise": bool(_v.get("verification_requise")), "envoi": _envoi,
            "sujet": _msg["sujet"], "texte": _msg["texte"], "code": _ctx["sub"].get("code"), "historique": _hist,
            "modele": {"sujet": _m.get("sujet") or sujet_defaut(_v.get("paiement_actuel")), "corps": _m.get("corps") or CORPS_DEFAUT},
            "modele_defaut": {"sujet": sujet_defaut(_v.get("paiement_actuel")), "corps": CORPS_DEFAUT}}


@router.get("/api/rappels-paiement/{sub_id}/apercu")
async def apercu_rappel(sub_id: str, request: Request):
    """L'aperçu obligatoire. Lecture seule. 404 (et non 403) sur le client d'un autre coach."""
    _email, _admin = await _exiger_coach(request)
    _ctx = await _contexte(sub_id)
    if not _acces(_ctx, _email, _admin):
        raise HTTPException(status_code=404, detail="Abonnement introuvable.")
    return await _reponse_apercu(sub_id, _ctx, _email, _admin)


@router.post("/api/rappels-paiement/{sub_id}/apercu")
async def apercu_personnalise(sub_id: str, corps: ApercuPersonnalise, request: Request):
    """L'aperçu du texte modifié. Rien n'est enregistré. Le jeton rendu vaut pour ce texte exact."""
    _email, _admin = await _exiger_coach(request)
    _ctx = await _contexte(sub_id)
    if not _acces(_ctx, _email, _admin):
        raise HTTPException(status_code=404, detail="Abonnement introuvable.")
    return await _reponse_apercu(sub_id, _ctx, _email, _admin, _modele_saisi(corps.sujet, corps.corps))


@router.post("/api/rappels-paiement/{sub_id}/verifier-envoi")
async def verifier_envoi(sub_id: str, corps: PreuveEnvoi, request: Request):
    """Résoudre un « Envoi à vérifier » sur PREUVE du fournisseur. SUPER-ADMIN. N'ENVOIE JAMAIS RIEN.

    Envoi prouvé (journal central, identifiant fourni, ou e-mail retrouvé dans l'historique) : la
    ligne passe à `envoye` avec sa date réelle, elle compte dans les 3 rappels et le délai s'applique.
    Absence prouvée (`verifier_absence`) : la ligne passe à `non_parti`, elle ne compte pas, et le
    prochain rappel sera une tentative distincte. Aucune clé n'est réutilisée. Sinon le blocage reste.
    """
    _email, _admin = await _exiger_coach(request)
    if not _admin:
        raise HTTPException(status_code=403, detail="Réservé au super-admin.")
    _sans = lambda motif, msg: {"resolu": False, "motif": motif, "message": msg + " Le blocage reste : contacte la personne hors du système."}  # noqa: E731
    _maintenant = datetime.now(timezone.utc)
    _ctx = await _contexte(sub_id)
    _doc = next((d for d in sorted(await _docs_interrompus_inscrits(sub_id, _maintenant, _ctx), key=lambda x: str(x.get("cree_le")), reverse=True)
                 if d.get("statut") == "incertain"), None)
    if not _doc:
        raise HTTPException(status_code=409, detail={"type": "rien_a_verifier", "message": "Aucun envoi à vérifier sur cet abonnement."})
    _rid = str(corps.resend_id or "").strip()
    if _rid and not RE_RESEND_ID.match(_rid):
        raise HTTPException(status_code=400, detail="Identifiant du fournisseur illisible.")
    _journal = await db[_rc.COL_JOURNAL].find_one({"reference": _doc["_id"], "resend_id": {"$nin": [None, ""]}}, {"_id": 0, "resend_id": 1})
    _source = "journal" if _journal else "identifiant"
    _rid = (_journal or {}).get("resend_id") or _rid
    if not _rid and corps.verifier_absence:
        _deb = _instant(_doc.get("premier_essai_le"))
        if _deb is None or _maintenant < _deb + DUREE_CLE_FOURNISSEUR:
            return _sans("trop_tot", "Cet essai a moins de 24 heures : son résultat peut encore arriver.")
        if resend is None or not os.environ.get("RESEND_API_KEY"):
            return _sans("fournisseur_indisponible", "Le fournisseur n'est pas joignable.")
        try:
            _liste = await lire_periode_fournisseur(_deb - timedelta(minutes=10), _deb + DUREE_CLE_FOURNISSEUR)
        except Exception as _err:  # noqa: BLE001
            logger.warning("[V648] historique illisible : %s", type(_err).__name__)
            _liste = None
        if _liste is None:
            return _sans("preuve_insuffisante", "L'historique du fournisseur ne couvre pas toute la période.")
        _dest = str(_doc.get("destinataire") or "").lower()
        # Le bon destinataire suffit à douter : un objet inattendu vers cette personne n'est pas une absence.
        _vers_elle = [m for m in _liste if _dest in adresses_fiche(m)]
        _pareils = [m for m in _vers_elle if objet_fiche(m) in OBJETS_RAPPEL + (_doc.get("sujet"),)]
        if any(m not in _pareils and any(t in objet_fiche(m).casefold() for t in ("rappel", "paiement", "=?")) for m in _vers_elle):
            return _sans("preuve_insuffisante", "Un e-mail ressemblant existe pour cette personne : impossible de trancher.")
        if not _pareils:
            _pris = await db[COL_RAPPELS].find_one_and_update(
                {"_id": _doc["_id"], "statut": "incertain", "maj_le": _doc.get("maj_le")},
                {"$set": {"statut": "non_parti", "maj_le": _maintenant.isoformat(),
                          "resolution": {"par": _email, "le": _maintenant.isoformat(), "source": "historique_fournisseur"}},
                 "$unset": {"erreur": ""}})
            if not _pris:
                raise HTTPException(status_code=409, detail={"type": "en_cours", "message": MSG_EN_COURS})
            return {"resolu": True, "non_parti": True, "message": "Absence prouvée : cet essai n'est pas parti et ne compte pas. Un nouveau rappel reste soumis aux règles normales. Aucun message n'a été envoyé."}
        if len(_pareils) > 1 or not _pareils[0].get("id") or not RE_RESEND_ID.match(str(_pareils[0]["id"])):
            return _sans("preuve_insuffisante", "Plusieurs e-mails ou une fiche illisible : impossible de trancher.")
        _rid, _source = str(_pareils[0]["id"]), "historique_fournisseur"
    if not _rid:
        return _sans("aucune_preuve", "Aucune trace de cet envoi dans le journal, et aucun identifiant fourni.")
    _ailleurs = await db[_rc.COL_JOURNAL].find_one({"resend_id": _rid, "reference": {"$nin": [_doc["_id"], None, ""]}}, {"_id": 1})
    if _ailleurs or await db[COL_RAPPELS].find_one({"resend_id": _rid, "_id": {"$ne": _doc["_id"]}}, {"_id": 1}):
        return _sans("preuve_deja_utilisee", "Cet identifiant prouve déjà un autre rappel.")
    if resend is None or not os.environ.get("RESEND_API_KEY"):
        return _sans("fournisseur_indisponible", "Le fournisseur n'est pas joignable.")
    try:
        _fiche = await asyncio.to_thread(resend.Emails.get, _rid)
    except Exception as _err:  # noqa: BLE001
        logger.warning("[V648] preuve illisible : %s", type(_err).__name__)
        return _sans("fournisseur_indisponible", "Le fournisseur n'a pas confirmé cet e-mail.")
    _motif = preuve_conforme(_fiche, _doc)
    if _motif:
        return _sans("preuve_non_conforme", _motif)
    _cree = date_fournisseur(_fiche.get("created_at"))
    _pris = await db[COL_RAPPELS].find_one_and_update(
        {"_id": _doc["_id"], "statut": "incertain", "maj_le": _doc.get("maj_le")},
        {"$set": {"statut": "envoye", "resend_id": _rid, "envoye_le": _cree.isoformat(), "maj_le": _maintenant.isoformat(),
                  "resolution": {"par": _email, "le": _maintenant.isoformat(), "source": _source, "dernier_evenement": _fiche.get("last_event")}},
         "$unset": {"erreur": ""}})
    if not _pris:
        raise HTTPException(status_code=409, detail={"type": "en_cours", "message": MSG_EN_COURS})
    _note = " Le fournisseur signale un échec de remise : préviens la personne autrement." if _fiche.get("last_event") in ("bounced", "failed", "complained") else ""
    return {"resolu": True, "message": "Preuve reçue : cet envoi est bien parti. Aucun message n'a été envoyé." + _note}


class ActionRappel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    confirmation: bool = False
    portee: str = ""        # annuler : `un` ou `tous`
    numero: object = None   # annuler `un` : le rappel que le coach voyait
    motif: object = None


def _motif_action(valeur) -> str:
    if valeur is None:
        return ""
    if not isinstance(valeur, str) or len(valeur.strip()) > MOTIF_ACTION_MAX:
        raise HTTPException(status_code=400, detail={"type": "motif_refuse", "message": "Motif : %d caractères au plus." % MOTIF_ACTION_MAX})
    return valeur.strip()


async def _contexte_action(sub_id: str, corps: ActionRappel, request: Request):
    """La porte commune : jeton signé, confirmation, puis droits. 404 sur le client d'un autre coach."""
    _email, _admin = await _exiger_coach(request)
    if corps.confirmation is not True:
        raise HTTPException(status_code=400, detail={"type": "confirmation", "message": "Confirmation du coach requise."})
    _motif = _motif_action(corps.motif)
    _ctx = await _contexte(sub_id)
    if not _acces(_ctx, _email, _admin):
        raise HTTPException(status_code=404, detail="Abonnement introuvable.")
    return _email, _admin, _ctx, _motif


def _champs_annulation(sub_id: str, ctx: dict, paiement: dict, par: str, motif: str, quand: str, statut: str) -> dict:
    _vue = suivi_paiement_lire(ctx["sub"])
    return {"subscription_id": sub_id, "code": ctx["sub"].get("code"), "coach_id": ctx.get("proprio", ""), "palier": PALIER_MANUEL,
            "statut": statut, "echeance": _vue.get("prochaine_echeance"), "montant": _vue.get("reste_a_payer"), "devise": ctx["sub"].get("devise") or "CHF",
            "destinataire": str(ctx["sub"].get("email") or "").strip().lower(), "envoye_par": par, "motif_action": motif, "annule_le": quand, "maj_le": quand,
            "paiement_numero": paiement["numero"], "nb_au_rappel": paiement["nb"], "encaisse_au_rappel": paiement["encaisse"], "total_au_rappel": paiement["total"]}


@router.post("/api/rappels-paiement/{sub_id}/annuler")
async def annuler_rappel(sub_id: str, corps: ActionRappel, request: Request):
    """Annule le prochain rappel (`un`) ou tous ceux de ce paiement (`tous`). N'efface rien, n'envoie rien, ne touche à aucun solde."""
    _email, _admin, _ctx, _motif = await _contexte_action(sub_id, corps, request)
    if corps.portee not in ("un", "tous"):
        raise HTTPException(status_code=400, detail={"type": "portee", "message": "Portée inconnue."})
    _v = await _verdict(_ctx, ignorer_fenetre=True)
    if not _v["ok"]:
        raise HTTPException(status_code=409, detail={"type": _v["motif"], "message": _v["message"]})
    _maintenant = datetime.now(timezone.utc)
    _iso = _maintenant.isoformat()
    _paiement = paiement_attendu(sub_id, _ctx["sub"])
    _delai = await _delai_relance(_ctx)
    _docs = await _docs_interrompus_inscrits(sub_id, _maintenant, _ctx)

    if corps.portee == "tous":
        _reprises = await db[COL_RAPPELS].count_documents({"subscription_id": sub_id, "statut": "annule_tous_leve"})
        _cle = "%s|annule_tous|%s|%s|%d" % (sub_id, _paiement["numero"], _paiement["encaisse"], _reprises)
        try:
            await db[COL_RAPPELS].insert_one(dict(_champs_annulation(sub_id, _ctx, _paiement, _email, _motif, _iso, "annule_tous"), _id=_cle, rang=0, cree_le=_iso))
        except DuplicateKeyError:
            return {"annule": True, "deja": True, "message": "Ces rappels étaient déjà annulés."}
        # Écrit D'ABORD, relu ENSUITE : un envoi qui n'a pas encore fait sa dernière vérification s'arrêtera.
        _encours = any(_statut_effectif(d, _maintenant) in ("en_cours", "incertain") for d in await _docs_abonnement(sub_id, _ctx))
        return {"annule": True, "envoi_en_cours": _encours,
                "message": "Rappels futurs annulés. Un envoi déjà en cours peut encore arriver." if _encours else "Rappels futurs annulés pour ce paiement."}

    _dec = decision_relance(_docs, _delai, _maintenant, _paiement)
    if _dec["action"] == "refus" and _dec.get("type") != "deja_envoye":
        raise HTTPException(status_code=409, detail={"type": _dec.get("type"), "message": _dec.get("message", "")})
    _numero = _dec.get("numero") or _dec.get("numero_suivant")
    if corps.numero != _numero:
        raise HTTPException(status_code=409, detail={"type": "etat_change", "message": "La situation a changé : recharge la liste. Rien n'a été annulé."})
    # Le délai repart de la date où ce rappel aurait pu partir : le suivant ne part pas dans l'heure.
    _effet = _instant(_dec.get("prochaine_le")) or _maintenant
    _champs = dict(_champs_annulation(sub_id, _ctx, _paiement, _email, _motif, _iso, "annule"), numero=_numero, effet_le=max(_effet, _maintenant).isoformat())
    if _dec["action"] == "reessai":
        _ex = _dec["doc"]
        _pris = await db[COL_RAPPELS].find_one_and_update({"_id": _ex["_id"], "statut": "echec", "maj_le": _ex.get("maj_le")}, {"$set": _champs})
        if not _pris:
            raise HTTPException(status_code=409, detail={"type": "en_cours", "message": MSG_EN_COURS})
    else:
        _rang = _dec.get("rang_suivant") or _dec["rang"]
        try:   # le même `_id` qu'un envoi de ce rang : l'annulation et l'envoi ne peuvent pas gagner tous les deux
            await db[COL_RAPPELS].insert_one(dict(_champs, _id=cle_envoi(sub_id, _rang), rang=_rang, cree_le=_iso))
        except DuplicateKeyError:
            raise HTTPException(status_code=409, detail={"type": "en_cours", "message": MSG_EN_COURS})
    return {"annule": True, "message": "Rappel annulé."}


@router.post("/api/rappels-paiement/{sub_id}/reprendre")
async def reprendre_rappels(sub_id: str, corps: ActionRappel, request: Request):
    """Lève « annuler les rappels futurs », sur décision du coach. N'envoie rien. Les rappels déjà annulés gardent leur
    place, le délai et le plafond s'appliquent, et l'automatique ne revient pas sur une échéance déjà passée."""
    _email, _admin, _ctx, _motif = await _contexte_action(sub_id, corps, request)
    _v = await _verdict(_ctx, ignorer_fenetre=True)
    if not _v["ok"]:
        raise HTTPException(status_code=409, detail={"type": _v["motif"], "message": _v["message"]})
    _maintenant = datetime.now(timezone.utc)
    _iso = _maintenant.isoformat()
    _paiement = paiement_attendu(sub_id, _ctx["sub"])
    _docs = await _docs_interrompus_inscrits(sub_id, _maintenant, _ctx)
    _cibles = [d for d in _docs if d.get("statut") == "annule_tous" and classer_paiement(d, _paiement) != "distinct"]
    _repris = 0
    for _d in _cibles:
        # Conditionnel : un double clic ne reprend qu'une fois, et la décision d'annulation reste dans l'historique.
        if await db[COL_RAPPELS].find_one_and_update({"_id": _d["_id"], "statut": "annule_tous"}, {"$set": {"statut": "annule_tous_leve", "maj_le": _iso}}):
            _repris += 1
            await db[COL_RAPPELS].insert_one(dict(_champs_annulation(sub_id, _ctx, _paiement, _email, _motif, _iso, "reprise"),
                                                  _id=_d["_id"] + "|reprise", rang=0, cree_le=_iso, reprise_jour=v617_jour_local(_maintenant)))
    if not _repris:
        raise HTTPException(status_code=409, detail={"type": "pas_annule", "message": "Les rappels de ce paiement ne sont pas annulés."})
    _dec = decision_relance(await _docs_abonnement(sub_id, _ctx), await _delai_relance(_ctx), _maintenant, _paiement)
    return {"repris": True, "message": "Rappels repris. Rien n'a été envoyé. " + (_dec.get("message") if _dec["action"] == "refus" else "Le prochain rappel suivra les règles habituelles.")}


@router.post("/api/rappels-paiement/{sub_id}/exclure")
async def exclure_membre(sub_id: str, corps: ActionRappel, request: Request):
    """Plus aucun rappel, manuel ou automatique, pour ce membre chez ce coach. Le compte, l'abonnement et le solde ne bougent pas."""
    _email, _admin, _ctx, _motif = await _contexte_action(sub_id, corps, request)
    _iso = datetime.now(timezone.utc).isoformat()
    _coach = _cle_reglages(_ctx.get("proprio"))
    for _cle in cle_membre(_ctx.get("proprio"), _ctx["sub"], _ctx.get("code")):
        await db[COL_EXCLUSIONS].update_one({"_id": _cle}, {
            "$set": {"actif": True, "coach_id": _coach, "code": _ctx["sub"].get("code"), "par": _email, "le": _iso, "motif": _motif},
            "$unset": {"reprise_jour": ""},
            "$push": {"journal": {"action": "exclu", "par": _email, "le": _iso, "motif": _motif}}}, upsert=True)
    return {"exclu": True, "message": "Membre exclu des rappels. Son abonnement et son solde ne changent pas."}


@router.post("/api/rappels-paiement/{sub_id}/reactiver")
async def reactiver_membre(sub_id: str, corps: ActionRappel, request: Request):
    """Lève l'exclusion. Rien n'est envoyé ici, et l'automatique ne reprend qu'aux échéances à partir d'aujourd'hui."""
    _email, _admin, _ctx, _motif = await _contexte_action(sub_id, corps, request)
    _iso = datetime.now(timezone.utc).isoformat()
    _maj = 0
    for _cle in cle_membre(_ctx.get("proprio"), _ctx["sub"], _ctx.get("code")):
        _r = await db[COL_EXCLUSIONS].update_one({"_id": _cle, "actif": True}, {
            "$set": {"actif": False, "reprise_jour": v617_jour_local(), "reactive_par": _email, "reactive_le": _iso},
            "$push": {"journal": {"action": "reactive", "par": _email, "le": _iso, "motif": _motif}}})
        _maj += _r.modified_count
    if not _maj:
        raise HTTPException(status_code=409, detail={"type": "pas_exclu", "message": "Ce membre n'est pas exclu."})
    _v = await _verdict(_ctx)
    return {"reactive": True, "eligible": bool(_v["ok"]), "message": "Rappels réactivés." if _v["ok"] else "Rappels réactivés. Pour l'instant : " + _v["message"]}


@router.post("/api/rappels-paiement/{sub_id}/envoyer")
async def envoyer_rappel(sub_id: str, corps: EnvoiRappel, request: Request):
    """L'envoi. Le navigateur n'apporte qu'une empreinte et une confirmation : tout le reste
    (montant, abonnement, destinataire, droits) est relu ici, et le message reconstruit ici."""
    _email, _admin = await _exiger_coach(request)
    if corps.confirmation is not True:
        raise HTTPException(status_code=400, detail="Confirmation du coach requise.")
    _ctx = await _contexte(sub_id)
    if not _acces(_ctx, _email, _admin):
        raise HTTPException(status_code=404, detail="Abonnement introuvable.")
    _v = await _verdict(_ctx)
    if not _v["ok"]:
        raise HTTPException(status_code=409, detail={"type": _v["motif"], "message": _v["message"]})
    _modele = _modele_saisi(corps.sujet, corps.corps)
    _msg = _message_de(_ctx, _v, _modele)
    _emp = _empreinte_message(sub_id, _v, _msg)
    _delai = await _delai_relance(_ctx)
    _instant_envoi = datetime.now(timezone.utc)
    _reel = await _envoi_autorise_vers(_v["destinataire"])
    _docs = await _docs_interrompus_inscrits(sub_id, _instant_envoi, _ctx) if _reel else await _docs_abonnement(sub_id, _ctx)
    _paiement = paiement_attendu(sub_id, _ctx["sub"])
    _dec = decision_relance(_docs, _delai, _instant_envoi, _paiement)
    _exiger_permis(_dec)
    _jeton = jeton_valide(corps.empreinte, _emp, etat_decision(_dec), _email, _instant_envoi)
    if _jeton == "expire":
        raise HTTPException(status_code=409, detail={"type": "apercu_expire", "message": "Cet aperçu est trop ancien. Rouvre l'aperçu."})
    if _jeton != "ok":
        raise HTTPException(status_code=409, detail={
            "type": "donnees_changees", "message": "Le texte, le montant, l'échéance ou les envois ont changé depuis l'aperçu. Rouvre l'aperçu."})
    # Suivi incomplet : le solde calculé ne suffit pas, le coach dit lui-même ce qui est dû.
    # Rien n'est corrigé ici : s'il ne correspond pas, c'est au coach de reprendre son suivi.
    _confirme = None
    if _v.get("verification_requise"):
        _confirme = _nombre(corps.montant_confirme)
        if _confirme is None:
            raise HTTPException(status_code=409, detail={
                "type": "verification_requise", "message": "Saisis le montant réellement dû avant d'envoyer ce rappel."})
        if abs(_confirme - _v["reste"]) > 0.005:
            raise HTTPException(status_code=409, detail={
                "type": "montant_different",
                "message": "Ce montant ne correspond pas au solde calculé. Corrige d'abord le suivi de paiement : rien n'a été envoyé ni modifié."})

    # VERROU D'ENVOI. Ici, aucune écriture et aucun fournisseur : rien ne peut partir.
    if not _reel:
        return {"issue": "simulation", "envoye": False, "message": "Simulation : aucun e-mail n'a été envoyé."}
    return await _executer_envoi(sub_id, _ctx, _v, _msg, _emp, _paiement, _delai, etat_decision(_dec), _email, _confirme, "manuel", _modele)


async def _executer_envoi(sub_id: str, _ctx: dict, _v: dict, _msg: dict, _emp: str, _paiement: dict, _delai: int, etat: str, envoye_par: str,
                          confirme, mode_envoi: str, modele: dict = None, palier_auto: str = None, fenetre_libre: bool = False) -> dict:
    """Le seul chemin vers le fournisseur, pour le manuel comme pour l'automatique : réservation, dernière
    relecture, appel, historique. Lève HTTPException sur tout refus."""
    if resend is None or not os.environ.get("RESEND_API_KEY"):
        raise HTTPException(status_code=503, detail="Service d'e-mail non configuré : rien n'a été envoyé.")
    _base = {"subscription_id": sub_id, "code": _ctx["sub"].get("code"), "coach_id": _ctx.get("proprio", ""),
             "palier": PALIER_MANUEL, "mode_envoi": mode_envoi, "palier_auto": palier_auto, "sujet": _msg["sujet"],
             "echeance": _v["echeance"], "montant": _v["reste"], "devise": _v["devise"],
             "destinataire": _v["destinataire"], "empreinte": _emp, "envoye_par": envoye_par, "montant_confirme": confirme,
             "paiement_numero": _paiement["numero"], "nb_au_rappel": _paiement["nb"], "encaisse_au_rappel": _paiement["encaisse"], "total_au_rappel": _paiement["total"]}
    _doc = await _reserver(sub_id, _base, datetime.now(timezone.utc), _delai, _ctx, etat, _paiement)
    _cle = _doc["_id"]

    # DERNIÈRE VÉRIFICATION, jeton en main : un paiement saisi pendant la réservation arrête tout.
    _ctx2 = await _contexte(sub_id)
    _v2 = await _verdict(_ctx2, ignorer_fenetre=fenetre_libre) if _ctx2 else {"ok": False, "motif": "aucun_abonnement_actuel", "message": ""}
    if not _v2["ok"] or _empreinte_message(sub_id, _v2, _message_de(_ctx2, _v2, modele)) != _emp:
        await _clore_sans_succes(_doc, "echec", "donnees_changees")     # l'appel n'a pas eu lieu
        raise HTTPException(status_code=409, detail={"type": "donnees_changees", "message": "Les données ont changé : rien n'a été envoyé."})
    # V652 : une annulation enregistrée pendant la réservation arrête l'envoi. L'exclusion est déjà relue par le verdict ci-dessus.
    _autres = [x for x in await _docs_abonnement(sub_id, _ctx2) if x.get("_id") != _cle]
    _dec2 = decision_relance(_autres, _delai, datetime.now(timezone.utc), _paiement)
    if _dec2["action"] == "refus":
        await _clore_sans_succes(_doc, "echec", "annule_ou_concurrent")
        raise HTTPException(status_code=409, detail={"type": _dec2.get("type"), "message": _dec2.get("message") or "Rien n'a été envoyé."})

    _params = {"from": "Afroboost <notifications@afroboost.com>", "to": [_v["destinataire"]],
               "subject": _msg["sujet"], "html": _msg["html"], "text": _msg["texte"]}
    if _base["coach_id"] not in COACHS_BASSI:
        _params["reply_to"] = _base["coach_id"]   # le client d'un partenaire répond à son coach
    _msg_incertain = {"type": "incertain",
                      "message": "Envoi à vérifier : le message est peut-être parti. Aucun nouvel envoi sans preuve du fournisseur."}
    try:
        _brut = await _appel_fournisseur(_cle, _params, {"idempotency_key": _doc["idempotency_key"]})
    except Exception as _err:  # noqa: BLE001
        _issue = classer_erreur(_err)
        logger.warning("[V648] envoi %s : %s", _issue, type(_err).__name__)
        _ecrit = await _clore_sans_succes(_doc, _issue, type(_err).__name__)
        # V653 : 503 et non 502, que Cloudflare remplace par sa page, sans le message du serveur.
        if _issue == "incertain" or not _ecrit:
            raise HTTPException(status_code=503, detail=_msg_incertain)
        # Quota, clé refusée, trop de demandes : tous les clients suivants échoueraient aussi.
        raise HTTPException(status_code=503, detail={"type": "echec", "message": "L'envoi a été refusé : aucun message n'est parti.",
                                                     "general": isinstance(_err, _rc.QuotaResendAtteint) or str(getattr(_err, "code", "")) in ("401", "403", "429")})

    _rid = _brut.get("id") if isinstance(_brut, dict) else getattr(_brut, "id", None)
    if not _rid:
        await _clore_sans_succes(_doc, "incertain", "sans_identifiant")
        raise HTTPException(status_code=503, detail=_msg_incertain)
    # Un succès reste un fait, même tardif : seule la clé compte, et un envoi déjà confirmé ne bouge plus.
    _fin = datetime.now(timezone.utc).isoformat()
    await db[COL_RAPPELS].update_one({"_id": _cle, "idempotency_key": _doc["idempotency_key"], "statut": {"$ne": "envoye"}}, {
        "$set": {"statut": "envoye", "resend_id": _rid, "envoye_le": _fin, "maj_le": _fin}, "$unset": {"erreur": ""}})
    logger.info("[V648] rappel de paiement envoyé (échéance %s, %s)", _v["echeance"], mode_envoi)
    return {"issue": "envoye", "envoye": True, "envoye_le": _fin, "message": "E-mail envoyé."}


# ═══════════════════════════ AUTOMATIQUE (V650) ═══════════════════════════

async def passage_automatique(maintenant: datetime = None) -> dict:
    """Un passage. Drapeau éteint : ressort sans rien lire d'autre. Mêmes vérifications et même chemin que le manuel."""
    _bilan = {"actif": False, "envoyes": 0, "ecartes": 0}
    if not await _drapeau(DRAPEAU_AUTO):
        return _bilan
    _bilan["actif"] = True
    _maintenant = maintenant or datetime.now(timezone.utc)
    if not auto_heure_ouvree(_maintenant):
        _bilan["hors_horaire"] = True
        return _bilan
    _coachs = {}
    async for _r in db[COL_REGLAGES].find({"mode": MODE_AUTOMATIQUE}, {"delais": 1, "auto_actif_depuis": 1}):
        _coachs[_r["_id"]] = _r
    if not _coachs:
        return _bilan
    _jour = v617_jour_local(_maintenant)
    async for _s in db.subscriptions.find({"suivi_paiement": {"$type": "object"}, "status": "active"}, {"_id": 0, "id": 1}):
        if _bilan["envoyes"] >= PLAFOND_PASSAGE:
            _bilan["plafond"] = True
            break
        _sid = _s.get("id")
        _ctx = await _contexte(_sid)
        _reg = _coachs.get(_cle_reglages(_ctx.get("proprio"))) if _ctx.get("code") else None
        if not _reg or not _reg.get("auto_actif_depuis"):
            continue
        # Le même contrôle que le manuel : le réglage d'un coach ne vaut que pour ses propres clients.
        if _ctx["proprio"] in COACHS_BASSI:
            if str(_ctx["sub"].get("coach_id") or "").strip().lower() not in COACHS_BASSI:
                _bilan["ecartes"] += 1
                continue
        elif not _acces(_ctx, _ctx["proprio"], False) or not await v646_compte_coach_autorise(db, _ctx["proprio"]):
            _bilan["ecartes"] += 1
            continue
        _v = await _verdict(_ctx, _maintenant, ignorer_fenetre=True)
        if not _v["ok"] or _v.get("incomplet") or _v["echeance"] < _reg["auto_actif_depuis"] \
                or not auto_doit_envoyer(_v["echeance"], delais_du_reglage(_reg), _jour) \
                or not await _envoi_autorise_vers(_v["destinataire"]):
            _bilan["ecartes"] += 1
            continue
        # V652 : réactiver un membre ne réexpédie pas ses anciennes échéances. L'automatique reprend aux échéances suivantes.
        if _v["echeance"] < await _jour_de_reprise(_ctx):
            _bilan["ecartes"] += 1
            continue
        _delai = await _delai_relance(_ctx)
        _paiement = paiement_attendu(_sid, _ctx["sub"])
        _dec = decision_relance(await _docs_interrompus_inscrits(_sid, _maintenant, _ctx), _delai, _maintenant, _paiement)
        # Après un refus du fournisseur : un seul essai automatique par jour, jamais à chaque passage.
        if _dec["action"] == "refus" or (_dec["action"] == "reessai" and str(_dec["doc"].get("maj_le") or "")[:10] == _maintenant.date().isoformat()):
            _bilan["ecartes"] += 1
            continue
        _msg = _message_de(_ctx, _v)
        _off = (datetime.strptime(_jour, "%Y-%m-%d") - datetime.strptime(_v["echeance"], "%Y-%m-%d")).days
        try:
            await _executer_envoi(_sid, _ctx, _v, _msg, _empreinte_message(_sid, _v, _msg), _paiement, _delai, etat_decision(_dec), "automatique",
                                  None, "automatique", palier_auto=_nom_jalon(_off), fenetre_libre=True)
            _bilan["envoyes"] += 1
        except HTTPException as _err:
            _d = _err.detail if isinstance(_err.detail, dict) else {}
            # Une adresse refusée ne concerne qu'un client : les suivants passent. Le reste arrête le passage.
            if _err.status_code >= 500 and not (_d.get("type") == "echec" and not _d.get("general")):
                _bilan["arret"] = True
                break
            _bilan["ecartes"] += 1
    return _bilan


async def boucle_automatique():
    """Le réveil horaire. Il relit le drapeau à chaque passage, et une panne ne l'arrête pas."""
    await asyncio.sleep(DEMARRAGE_AUTO_S)
    while True:
        try:
            _b = await passage_automatique()
            if _b.get("envoyes") or _b.get("arret"):
                logger.info("[V650] passage automatique : %s envoyés, arrêt=%s", _b.get("envoyes"), bool(_b.get("arret")))
        except Exception as _err:  # noqa: BLE001
            logger.warning("[V650] passage ignoré : %s", type(_err).__name__)
        await asyncio.sleep(PERIODE_AUTO_S)
