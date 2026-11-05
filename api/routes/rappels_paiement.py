# -*- coding: utf-8 -*-
"""V648 — RAPPEL DU DEUXIÈME PAIEMENT (paiements manuels, coach uniquement).

CE QUE CE MODULE FAIT : un coach, depuis « Paiements à encaisser », voit un aperçu,
confirme, et le serveur envoie UN e-mail de rappel après avoir tout revérifié.

CE QU'IL NE FAIT JAMAIS : aucun prélèvement, aucun lien de paiement, aucune écriture sur
`subscriptions` ni sur `discount_codes`. Les seules collections écrites sont les siennes :
`rappels_paiement` (historique) et `rappels_paiement_reglages` (choix du coach).

DEUX VERROUS, TOUS DEUX FERMÉS À LA LIVRAISON :
  * `RAPPEL_PAIEMENT_ENVOI_REEL` (drapeau en base, absent = faux) : tant qu'il est faux, la
    route d'envoi répond « simulation », n'écrit rien et n'appelle aucun fournisseur.
  * AUTOMATISATION_DISPONIBLE = False : aucune boucle n'existe. Choisir « Automatique » range
    une préférence ; les délais J-3, J0, J+3 ne sont calculés qu'en simulation, en lecture seule.

POURQUOI LES ABONNEMENTS STRIPE SONT EXCLUS. `saison_2x` et `mensuel_auto` sont prélevés par
Stripe, et la facture payée ne met à jour ni `montant_encaisse` ni `suivi_paiement`
(`hiver.py`) : le « reste à payer » y reste affiché après le paiement. Relancer ces clients,
c'est leur demander de payer deux fois.

L'ANTI-DOUBLON EST L'IDENTIFIANT LUI-MÊME. `_id` = abonnement|échéance|palier|rang : MongoDB
garantit son unicité, sans index à créer. Une seule requête peut insérer un rang ; les autres
reçoivent une erreur de clé dupliquée et n'appellent pas le fournisseur.

V648b — PLUSIEURS RAPPELS POUR UNE MÊME ÉCHÉANCE. Rang 1 = le rappel, rangs 2 et 3 = les relances :
3 messages au plus par échéance, et au moins 7 jours entre deux messages réellement partis, même si
le coach change la date (il peut allonger ce délai, jamais le raccourcir). Chaque rang garde sa ligne.

UN APERÇU NE SERT QU'UNE FOIS. Le jeton d'aperçu est signé, valable 30 minutes et lié au coach, aux
données et à l'état des envois : tout essai le périme, il faut rouvrir l'aperçu avant chaque message.

LES ÉTATS D'UN ENVOI :
  en_cours  -> réservé, l'appel au fournisseur est en route
  envoye    -> Resend a accepté (identifiant reçu). Prochain message seulement après le délai.
  echec     -> refus CERTAIN (quota, adresse refusée…) : aucun message parti, on peut réessayer, avec
               une nouvelle clé d'idempotence et une nouvelle date de référence.
  incertain -> coupure, délai dépassé, erreur serveur : le message est PEUT-ÊTRE parti. Jamais de
               renvoi immédiat. Le coach peut réessayer entre 15 minutes et 23 heures après, avec la
               MÊME clé : Resend ne délivre pas deux fois, et c'est la seule résolution fiable.
               Passé 23 h, Resend a oublié la clé : aucun nouveau message pour cet abonnement, même
               avec une autre date. Une reprise qui échoue reste `incertain`.

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
import logging
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from pymongo.errors import DuplicateKeyError

import api.resend_central as _rc
from api.routes.shared import (SUPER_ADMIN_EMAIL, abo_actuel_du_code, coach_jwt_email,
                               suivi_paiement_lire, suivi_rappel, v617_jour_local, v617_visible_par)

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
DRAPEAU_ENVOI_REEL = "RAPPEL_PAIEMENT_ENVOI_REEL"
AUTOMATISATION_DISPONIBLE = False     # aucune boucle : à changer seulement par une version dédiée

MODE_MANUEL = "MANUEL"
MODE_AUTOMATIQUE = "AUTOMATIQUE"
MODES = (MODE_MANUEL, MODE_AUTOMATIQUE)
PALIER_MANUEL = "manuel"
PALIERS_AUTO = {"J-3": -3, "J0": 0, "J+3": 3}
BILLING_STRIPE = ("saison_2x", "mensuel_auto")

SOLDE_MINIMUM = 1.0                   # sous 1 CHF : un arrondi (ex. 199.99 sur 200), pas une dette
FRAIS_EN_COURS = timedelta(minutes=10)  # au-delà, un « en_cours » a perdu son processus
DUREE_REPRISE = timedelta(hours=23)   # Resend garde une clé d'idempotence 24 h
DELAI_RELANCE_DEFAUT = 7              # jours entre deux rappels manuels d'une même échéance
DELAI_RELANCE_MIN, DELAI_RELANCE_MAX = 7, 60
MAX_RAPPELS_PAR_ECHEANCE = 3          # le premier rappel compris
ATTENTE_REPRISE = timedelta(minutes=15)   # jamais de renvoi immédiat après un résultat incertain
DUREE_JETON_APERCU = 1800             # secondes de validité d'un aperçu
NOM_PRO_MAX = 60
# Lettres latines accentuées : un « а » cyrillique ne peut pas imiter « Afroboost ».
RE_NOM_PRO = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿŒœ0-9][A-Za-zÀ-ÖØ-öø-ÿŒœ0-9 '’&.\-]*$")
RE_NOM_DOMAINE = re.compile(r"\.[a-zà-ÿ]{2,}", re.IGNORECASE)     # « evil.com », « evil.com-pay », « www.x »
RE_NOM_CHIFFRE_COLLE = re.compile(r"[^\W\d_]\d|\d[^\W\d_]")      # « Afr0boost », « CH93 »
NOM_CHIFFRES_MAX = 4                  # un numéro de compte, même découpé, n'y tient pas
# Ces lettres ne se décomposent pas en Unicode : sans cette table, « Afrøboost » passerait.
NOM_SOSIES = str.maketrans({"ø": "o", "ß": "ss", "œ": "oe", "æ": "ae", "ð": "d", "þ": "th",
                            "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b"})
NOM_SOSIES_COURTS = {ord("œ"): "o", ord("æ"): "a", ord("ß"): "s", ord("þ"): "t"}   # l'autre lecture : une seule lettre
NOMS_TROMPEURS = ("afroboost", "bassi", "stripe", "twint", "paypal", "banque", "support", "administrat", "paiement", "service client")

SIMULATION_MAX = 50
RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
COACHS_BASSI = ("", "bassi_default", SUPER_ADMIN_EMAIL.lower())

MOTIFS = {
    "aucun_abonnement_actuel": "Cet abonnement n'est plus l'abonnement actuel du code.",
    "plusieurs_abonnements": "Ce code porte plusieurs abonnements actuels : à vérifier d'abord.",
    "code_ambigu": "Ce code existe en plusieurs exemplaires : à vérifier d'abord.",
    "stripe_recurrent": "Abonnement prélevé par Stripe : aucun rappel à envoyer.",
    "solde_inconnu": "Le montant total ou le montant encaissé n'est pas renseigné.",
    "solde_nul": "Il ne reste rien à payer.",
    "suivi_incoherent": "Le suivi de paiement est incohérent : à corriger avant tout rappel.",
    "sans_echeance": "Aucune date d'échéance renseignée.",
    "hors_fenetre": "L'échéance est dans plus de 7 jours.",
    "sans_email": "Aucune adresse e-mail valide sur l'abonnement.",
    "destinataire_ambigu": "L'adresse du code et celle de l'abonnement sont différentes.",
    "refus_email": "Cette personne a demandé à ne plus recevoir d'e-mails.",
    "signature_manquante": "Nom professionnel du coach absent ou refusé (lien, adresse, nom trompeur ou trop long) : le message ne peut pas être signé.",
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
        return n if n == n else None
    except (TypeError, ValueError):
        return None


def est_recurrent_stripe(sub, offre=None) -> bool:
    """PUR. Vrai dès qu'un seul indice désigne un prélèvement Stripe (au moindre doute, exclu)."""
    _s = sub or {}
    return bool(str(_s.get("stripe_subscription_id") or "").strip()
                or _s.get("billing_mode") in BILLING_STRIPE
                or (offre or {}).get("billing_mode") in BILLING_STRIPE)


def eligibilite(sub, code_doc=None, offre=None, motif_abo="unique", maintenant=None, ignorer_fenetre=False) -> dict:
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
    if est_recurrent_stripe(_s, offre):
        return _non("stripe_recurrent")

    _vue = suivi_paiement_lire(_s)
    _total, _enc = _nombre(_vue.get("montant_total")), _nombre(_s.get("montant_encaisse"))
    if _total is None or _enc is None:
        return _non("solde_inconnu")
    if _enc > _total + 0.005 or _total <= 0 or _enc <= 0:
        return _non("suivi_incoherent")      # encaissé > total, ou aucun premier paiement enregistré
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


def empreinte(sub_id, verdict) -> str:
    """PUR. Résume ce que le coach a vu : si un seul de ces éléments change, l'envoi est refusé."""
    _b = "|".join(str(x) for x in (sub_id, "%.2f" % verdict["reste"], verdict["devise"], verdict["echeance"],
                                   verdict["destinataire"], verdict.get("paiement_actuel"), verdict.get("nb_paiements")))
    return hashlib.sha256(_b.encode("utf-8")).hexdigest()[:24]


def cle_envoi(sub_id, echeance, rang=1, palier=PALIER_MANUEL) -> str:
    """PUR. Un seul message par abonnement, échéance, palier et rang (1 = rappel, 2+ = relances)."""
    return "%s|%s|%s|%d" % (sub_id, echeance, palier, rang)


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


def _refus_incertain_definitif(doc) -> dict:
    return _refus("incertain_bloque", doc, message=MSG_INCERTAIN + " Plus aucun essai sûr : aucun nouvel envoi pour cet abonnement, contacte la personne directement.")


def decision_relance(docs, delai_jours, maintenant, echeance=None) -> dict:
    """PUR. Que permet l'historique de CET abonnement ? Une seule règle, pour l'écran et pour l'envoi.

    action : nouveau | reessai | reprise | refus. `reprise` exige une demande explicite du coach.
    `echeance` : les envois des AUTRES dates comptent aussi : changer la date ne contourne ni un
    résultat incertain, ni le délai entre deux messages. Le maximum de 3, lui, vaut par échéance.
    Une date illisible bloque : dans le doute, aucun message.
    """
    _delai = timedelta(days=delai_jours)
    _ici = [d for d in docs if echeance is None or d.get("echeance") == echeance]
    for _a in [d for d in docs if echeance is not None and d.get("echeance") != echeance]:
        _s = _statut_effectif(_a, maintenant)
        if _s == "en_cours":
            return _refus("en_cours", _a, message=MSG_EN_COURS)
        if _s == "incertain":
            return _refus_incertain_definitif(_a)
        if _s == "envoye":
            _env = _instant(_a.get("envoye_le"))
            if _env is None:
                return _refus_incertain_definitif(_a)
            if maintenant < _env + _delai:
                return _refus("deja_envoye", _a, prochaine=_env + _delai,
                              message="Un rappel vient d'être envoyé. Prochain envoi possible le %s." % _date_ch((_env + _delai).isoformat()))
    if not _ici:
        return {"action": "nouveau", "rang": 1}
    _der = max(_ici, key=lambda d: int(d.get("rang") or 1))
    _rang = int(_der.get("rang") or 1)
    _statut = _statut_effectif(_der, maintenant)
    if _statut == "echec":
        return {"action": "reessai", "rang": _rang, "doc": _der}
    if _statut == "en_cours":
        return _refus("en_cours", _der, message=MSG_EN_COURS)
    if _statut == "envoye":
        if sum(1 for d in _ici if d.get("statut") == "envoye") >= MAX_RAPPELS_PAR_ECHEANCE or _rang >= MAX_RAPPELS_PAR_ECHEANCE:
            return _refus("maximum_atteint", _der, message="Maximum de %d rappels atteint pour cette échéance." % MAX_RAPPELS_PAR_ECHEANCE)
        _env = _instant(_der.get("envoye_le"))
        if _env is None:
            return _refus_incertain_definitif(_der)
        if maintenant >= _env + _delai:
            return {"action": "nouveau", "rang": _rang + 1}
        return _refus("deja_envoye", _der, prochaine=_env + _delai,
                      message="Déjà envoyé pour cette échéance. Relance possible le %s." % _date_ch((_env + _delai).isoformat()))
    if _statut == "incertain":
        _deb, _maj = _instant(_der.get("premier_essai_le")), _instant(_der.get("maj_le"))
        if _deb is None or _maj is None or maintenant - _deb >= DUREE_REPRISE:
            return _refus_incertain_definitif(_der)
        if maintenant - _maj < ATTENTE_REPRISE:
            return _refus("incertain_attente", _der, prochaine=_maj + ATTENTE_REPRISE,
                          message=MSG_INCERTAIN + " Attends quelques minutes avant de vérifier.")
        return {"action": "reprise", "rang": _rang, "doc": _der}
    return _refus("en_cours", _der, message=MSG_EN_COURS)


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
    except (TypeError, ValueError):
        return "different"
    if not os.environ.get("JWT_SECRET") or not hmac.compare_digest(_sig, _signature_jeton(emp, etat, coach, _q)):
        return "different"
    _age = int(maintenant.timestamp()) - _q
    return "ok" if 0 <= _age <= DUREE_JETON_APERCU else "expire"


def nom_pro_valide(nom) -> bool:
    """PUR. Ce nom peut-il signer un e-mail parti de l'adresse Afroboost ? Au moindre doute, non."""
    if not isinstance(nom, str):
        return False
    _n = nom.strip()
    if not _n or len(_n) > NOM_PRO_MAX or not RE_NOM_PRO.match(_n):
        return False
    if RE_NOM_DOMAINE.search(_n) or RE_NOM_CHIFFRE_COLLE.search(_n) or sum(c.isdigit() for c in _n) > NOM_CHIFFRES_MAX:
        return False
    # « A.f.r-o b0ost », « Bässi » : on compare le nom réduit à ses lettres, chiffres ressemblants compris.
    _plat = unicodedata.normalize("NFKD", _n.lower())
    _plat = "".join(c for c in _plat if not unicodedata.combining(c))
    _lectures = set()
    for _texte in (_plat.translate(NOM_SOSIES), _plat.translate(NOM_SOSIES_COURTS).translate(NOM_SOSIES)):
        _compact = "".join(c for c in _texte if c.isalpha())
        # « l » et « i » se confondent à l'écran : « Bassl » se lit « Bassi ».
        _lectures.update((_compact, _compact.replace("l", "i")))
    return not any(t.replace(" ", "") in v for t in NOMS_TROMPEURS for v in _lectures)


def nom_professionnel(coach) -> str:
    """PUR. Le nom sous lequel un partenaire exerce, s'il est acceptable ; sinon chaîne vide.
    « Afroboost » seul est le défaut de la plateforme : le nom du coach prend alors le relais.
    Un autre nom refusé ne se rattrape pas en silence : le coach doit le corriger."""
    _c = coach or {}
    _plateforme = str(_c.get("platform_name") or "").strip()
    _nom = _plateforme if _plateforme and _plateforme.lower() != "afroboost" else str(_c.get("name") or "").strip()
    return _nom if nom_pro_valide(_nom) else ""


def cle_idempotence(cle, tentative=1) -> str:
    """PUR. Stable pour une même tentative : c'est elle qui rend une reprise sans danger."""
    return "rappel-paiement-" + hashlib.sha256(("%s#%s" % (cle, tentative)).encode("utf-8")).hexdigest()[:40]


def signature_du_code(code_doc, coach=None) -> str:
    """PUR. « Coach Bassi, d'Afroboost » pour ses codes ; un partenaire signe de SON nom professionnel.
    Chaîne vide si ce nom manque : l'envoi est alors refusé, plutôt que signé au hasard."""
    _proprio = str((code_doc or {}).get("coach_id") or "").strip().lower()
    if _proprio in COACHS_BASSI:
        return "Coach Bassi, d'Afroboost"
    return nom_professionnel(coach)


def _prenom(nom) -> str:
    _n = str(nom or "").strip()
    if not _n or "@" in _n:
        return ""
    return _n.split()[0][:40]


def _montant_lisible(m) -> str:
    return "%d" % m if float(m).is_integer() else "%.2f" % m


def _date_ch(iso) -> str:
    _a, _m, _j = str(iso)[:10].split("-")
    return "%s.%s.%s" % (_j, _m, _a)


def construire_message(prenom, reste, devise, echeance, signature, paiement_actuel=None) -> dict:
    """PUR. Le texte validé par Bassi le 05/11/2026. {sujet, texte, html}.

    Le mot « deuxième » n'est écrit que s'il est vrai : au 3e paiement d'un échéancier en
    quatre fois, l'objet dit « prochain ». Toute valeur variable est échappée dans le HTML.
    """
    _rang = "prochain" if paiement_actuel and paiement_actuel >= 2 else "deuxième"
    _sujet = "Rappel : ton %s paiement Afroboost" % _rang
    _bonjour = "Bonjour %s," % prenom if prenom else "Bonjour,"
    _montant, _date = _montant_lisible(reste), _date_ch(echeance)
    _p1 = "Petit rappel amical : il reste %s %s à régler pour ton abonnement Afroboost, prévu le %s." % (_montant, devise, _date)
    _p2 = "Si tu as déjà payé, ne tiens pas compte de ce message. Pour toute question, réponds simplement à cet e-mail."
    _p3 = "À très vite en cours !"
    _texte = "\n\n".join((_bonjour, _p1, _p2, _p3 + "\n" + signature))
    _lignes = "".join('<p style="margin:0 0 16px">%s</p>' % _html.escape(x, quote=True) for x in (_bonjour, _p1, _p2))
    _fin = '<p style="margin:0">%s<br>%s</p>' % (_html.escape(_p3, quote=True), _html.escape(signature, quote=True))
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


def jalons_simulation(echeance, delais, maintenant=None) -> list:
    """PUR. Les dates des paliers. Un palier passé reste passé : jamais de rattrapage."""
    _auj = v617_jour_local(maintenant)
    _base = datetime.strptime(echeance, "%Y-%m-%d")
    _sortie = []
    for _p in PALIERS_AUTO:
        if _p not in delais:
            continue
        _d = (_base + timedelta(days=PALIERS_AUTO[_p])).strftime("%Y-%m-%d")
        _sortie.append({"palier": _p, "date": _d,
                        "etat": "passe" if _d < _auj else ("aujourdhui" if _d == _auj else "a_venir")})
    return _sortie


# ═══════════════════════════ LECTURES ═══════════════════════════

async def _exiger_coach(request: Request):
    """La même porte que `GET /discount-codes/echeances` : un jeton signé, jamais un en-tête."""
    _email = (coach_jwt_email(request) or "").lower().strip()
    _admin = _email == SUPER_ADMIN_EMAIL.lower()
    _ok = _admin
    if not _ok and _email:
        if await db.coaches.find_one({"email": _email}, {"_id": 1}) or \
           await db.coach_auth.find_one({"email": _email}, {"_id": 1}):
            _ok = True
    if not _ok:
        raise HTTPException(status_code=403, detail="Authentification coach requise — reconnectez-vous")
    return _email, _admin


async def _envoi_reel_autorise() -> bool:
    _f = await db.feature_flags.find_one({"id": "feature_flags"}, {"_id": 0, DRAPEAU_ENVOI_REEL: 1}) or {}
    return _f.get(DRAPEAU_ENVOI_REEL) is True


def _peut_voir(code_doc, sub, appelant, admin) -> bool:
    """PUR. Un partenaire ne voit que SES codes, et jamais l'abonnement marqué d'un autre coach."""
    if not code_doc or not v617_visible_par(code_doc, appelant, admin):
        return False
    _proprio = str((sub or {}).get("coach_id") or "").strip().lower()
    return admin or not _proprio or _proprio == appelant


async def _contexte(sub_id: str) -> dict:
    """Tout est relu en base à chaque appel : rien de ce que le navigateur envoie n'est cru."""
    _sub = await db.subscriptions.find_one({"id": sub_id}, {"_id": 0})
    if not _sub or not str(_sub.get("code") or "").strip():
        return {}
    _re = {"$regex": "^%s$" % re.escape(str(_sub["code"]).strip()), "$options": "i"}
    _codes = await db.discount_codes.find({"code": _re}, {"_id": 0}).to_list(2)
    _tous = await db.subscriptions.find({"code": _re}, {"_id": 0}).to_list(50)
    _code = _codes[0] if _codes else None
    _actuel, _motif = abo_actuel_du_code(_tous, (_code or {}).get("assignedEmail"))
    # Ce rappel ne vise que l'abonnement ACTUEL : un abonnement remplacé ne reçoit rien.
    if _motif == "unique" and (_actuel or {}).get("id") != _sub.get("id"):
        _motif = "aucun"
    _offre = None
    if _sub.get("offer_id"):
        _offre = await db.offers.find_one({"id": _sub["offer_id"]}, {"_id": 0, "billing_mode": 1})
    _proprio = str((_code or {}).get("coach_id") or "").strip().lower()
    _coach = None
    if _proprio not in COACHS_BASSI:
        _coach = await db.coaches.find_one({"email": _proprio}, {"_id": 0, "name": 1, "platform_name": 1})
    return {"sub": _sub, "code": _code, "offre": _offre, "motif_abo": _motif, "codes_trouves": len(_codes),
            "proprio": _proprio, "coach": _coach}


async def _verdict(ctx: dict, maintenant=None, ignorer_fenetre=False) -> dict:
    if ctx.get("codes_trouves", 0) > 1:
        return {"ok": False, "motif": "code_ambigu", "message": MOTIFS["code_ambigu"]}
    _v = eligibilite(ctx.get("sub"), ctx.get("code"), ctx.get("offre"), ctx.get("motif_abo"),
                     maintenant, ignorer_fenetre)
    if _v["ok"] and not signature_du_code(ctx.get("code"), ctx.get("coach")):
        return {"ok": False, "motif": "signature_manquante", "message": MOTIFS["signature_manquante"]}
    if _v["ok"] and _refus_email is not None and await _refus_email("email", _v["destinataire"]):
        return {"ok": False, "motif": "refus_email", "message": MOTIFS["refus_email"]}
    return _v


def _message_de(ctx: dict, verdict: dict) -> dict:
    return construire_message(_prenom(ctx["sub"].get("name")), verdict["reste"], verdict["devise"], verdict["echeance"],
                              signature_du_code(ctx.get("code"), ctx.get("coach")), verdict.get("paiement_actuel"))


def _delai_valide(v) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) and DELAI_RELANCE_MIN <= v <= DELAI_RELANCE_MAX else DELAI_RELANCE_DEFAUT


async def _delai_relance(ctx: dict) -> int:
    """Le délai du coach PROPRIÉTAIRE du code : le super-admin qui agit sur un code partenaire le respecte."""
    _cle = ctx.get("proprio") if ctx.get("proprio") not in COACHS_BASSI else SUPER_ADMIN_EMAIL.lower()
    _r = await db[COL_REGLAGES].find_one({"_id": _cle}, {"delai_relance_jours": 1}) or {}
    return _delai_valide(_r.get("delai_relance_jours"))


async def _docs_abonnement(sub_id: str) -> list:
    return await db[COL_RAPPELS].find({"subscription_id": sub_id, "palier": PALIER_MANUEL}).to_list(200)


def _vue_envoi(decision: dict, delai: int) -> dict:
    """Ce que l'écran doit dire de l'envoi suivant. La route d'envoi redécide de toute façon."""
    _a = decision["action"]
    return {"peut_envoyer": _a != "refus", "action": _a, "type": decision.get("type"),
            "etape": etape_du_rang(decision.get("rang")), "prochaine_le": decision.get("prochaine_le"),
            "message": decision.get("message", ""), "confirmation_incertain": _a == "reprise", "delai_jours": delai}


def _ligne_historique(doc) -> dict:
    return {"palier": doc.get("palier"), "rang": doc.get("rang"), "etape": etape_du_rang(doc.get("rang")),
            "echeance": doc.get("echeance"), "statut": doc.get("statut"), "montant": doc.get("montant"),
            "devise": doc.get("devise"), "destinataire": doc.get("destinataire"), "envoye_le": doc.get("envoye_le"),
            "maj_le": doc.get("maj_le"), "envoye_par": doc.get("envoye_par"), "tentatives": doc.get("tentatives"),
            "montant_confirme": doc.get("montant_confirme")}


async def _historique(sub_id: str) -> list:
    _docs = await db[COL_RAPPELS].find({"subscription_id": sub_id}).sort([("cree_le", -1), ("rang", -1)]).to_list(100)
    return [_ligne_historique(d) for d in _docs]


async def _ligne_liste(ctx: dict, maintenant: datetime) -> dict:
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
              "possible": bool(_v["ok"]), "motif": _v.get("motif"), "message": _v.get("message", ""),
              "verification_requise": bool(_v.get("verification_requise")), "envoi": None}
    if _v["ok"]:
        _delai = await _delai_relance(ctx)
        _ligne["envoi"] = _vue_envoi(decision_relance(await _docs_abonnement(_sid), _delai, maintenant, _v["echeance"]), _delai)
    return _ligne


# ═══════════════════════════ ENVOI ═══════════════════════════

def _exiger_permis(decision: dict, reprise: bool) -> None:
    """Lève 409 si l'historique interdit ce message. Une seule traduction, pour l'envoi et la réservation."""
    if decision["action"] == "refus":
        _detail = {"type": decision["type"], "message": decision.get("message", ""), "reprise_possible": False}
        if decision.get("prochaine_le"):
            _detail["prochaine_le"] = decision["prochaine_le"]
        if decision["type"] == "deja_envoye":
            _detail["envoye_le"] = (decision.get("doc") or {}).get("envoye_le")
        raise HTTPException(status_code=409, detail=_detail)
    if decision["action"] == "reprise" and not reprise:
        raise HTTPException(status_code=409, detail={"type": "incertain", "reprise_possible": True, "message": MSG_INCERTAIN})


async def _docs_interrompus_inscrits(sub_id: str, maintenant: datetime) -> list:
    """Un processus disparu pendant l'appel : on l'écrit, l'historique doit dire la vérité."""
    _docs = await _docs_abonnement(sub_id)
    _marques = False
    for _x in _docs:
        if _x.get("statut") == "en_cours" and _statut_effectif(_x, maintenant) == "incertain":
            await db[COL_RAPPELS].update_one({"_id": _x["_id"], "statut": "en_cours", "maj_le": _x.get("maj_le")},
                                             {"$set": {"statut": "incertain", "erreur": "interrompu", "maj_le": maintenant.isoformat()}})
            _marques = True
    return await _docs_abonnement(sub_id) if _marques else _docs


async def _reserver(sub_id: str, base: dict, reprise: bool, maintenant: datetime, delai: int) -> dict:
    """La SEULE porte vers le fournisseur. Rend le document réservé, ou lève 409. Atomique."""
    _iso = maintenant.isoformat()
    _occupe = {"type": "en_cours", "message": MSG_EN_COURS}
    _d = decision_relance(await _docs_interrompus_inscrits(sub_id, maintenant), delai, maintenant, base["echeance"])
    _exiger_permis(_d, reprise)
    _ex = _d.get("doc") or {}
    _action = _d["action"]

    if _action == "nouveau":
        _rang = _d["rang"]
        _cle = cle_envoi(sub_id, base["echeance"], _rang)
        _doc = dict(base, _id=_cle, rang=_rang, statut="en_cours", tentatives=1, idempotency_key=cle_idempotence(_cle, 1),
                    premier_essai_le=_iso, cree_le=_iso, maj_le=_iso)
        try:
            await db[COL_RAPPELS].insert_one(_doc)     # une seule requête gagne ce rang
        except DuplicateKeyError:
            raise HTTPException(status_code=409, detail=_occupe)
        return _doc

    if _action == "reprise":
        # Même clé = même message : Resend ne délivre pas deux fois, mais seulement à l'identique.
        if _ex.get("empreinte") != base.get("empreinte"):
            raise HTTPException(status_code=409, detail={
                "type": "incertain_attente", "reprise_possible": False,
                "message": MSG_INCERTAIN + " Les données ont changé : le même message n'est plus possible."})
        _maj = {"$set": {"statut": "en_cours", "maj_le": _iso, "envoye_par": base.get("envoye_par")}, "$inc": {"tentatives": 1}}
    else:    # reessai : refus certain, rien n'est parti. Nouvelle clé (Resend garde aussi les refus), donc nouvelle date.
        _maj = {"$set": dict(base, statut="en_cours", maj_le=_iso, premier_essai_le=_iso,
                             idempotency_key=cle_idempotence(_ex["_id"], int(_ex.get("tentatives") or 1) + 1)),
                "$inc": {"tentatives": 1}}
    _pris = await db[COL_RAPPELS].find_one_and_update(
        {"_id": _ex["_id"], "statut": _ex.get("statut"), "maj_le": _ex.get("maj_le")}, _maj, return_document=True)
    if not _pris:
        raise HTTPException(status_code=409, detail=_occupe)
    _pris["_reprise"] = _action == "reprise"
    return _pris


async def _clore_sans_succes(doc: dict, statut: str, erreur: str) -> bool:
    """Échec ou incertitude : seulement si CET essai est toujours celui en cours. Réponse tardive = sans effet."""
    _r = await db[COL_RAPPELS].update_one({"_id": doc["_id"], "statut": "en_cours", "tentatives": doc.get("tentatives")},
                                          {"$set": {"statut": statut, "erreur": erreur, "maj_le": datetime.now(timezone.utc).isoformat()}})
    return bool(getattr(_r, "modified_count", 0))


async def _appel_fournisseur(cle: str, params: dict, options: dict):
    return await asyncio.to_thread(
        _rc.emails("rappels_paiement:envoyer", critique=False, type_email="rappel_paiement",
                   reference=cle, sdk=resend).send, params, options)


class EnvoiRappel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    empreinte: str = ""
    confirmation: bool = False
    reprise_incertain: bool = False
    montant_confirme: object = None       # seulement si le suivi est incomplet : la saisie du coach


@router.get("/api/rappels-paiement/reglages")
async def lire_reglages(request: Request):
    _email, _ = await _exiger_coach(request)
    _doc = await db[COL_REGLAGES].find_one({"_id": _email}) or {}
    return {"mode": _doc.get("mode") if _doc.get("mode") in MODES else MODE_MANUEL,
            "delais": [p for p in (_doc.get("delais") or list(PALIERS_AUTO)) if p in PALIERS_AUTO],
            "delai_relance_jours": _delai_valide(_doc.get("delai_relance_jours")),
            "automatisation_disponible": AUTOMATISATION_DISPONIBLE,
            "envoi_reel": await _envoi_reel_autorise()}


@router.put("/api/rappels-paiement/reglages")
async def ecrire_reglages(request: Request):
    """Range une préférence, et rien d'autre : aucun moteur ne lit ce réglage aujourd'hui."""
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
    if not isinstance(_delais, list) or not all(d in PALIERS_AUTO for d in _delais):
        raise HTTPException(status_code=400, detail="Délais inconnus : J-3, J0 ou J+3.")
    _propres = [p for p in PALIERS_AUTO if p in _delais]
    _champs = {"mode": _mode, "delais": _propres, "maj_le": datetime.now(timezone.utc).isoformat()}
    if "delai_relance_jours" in _corps:
        _j = _corps["delai_relance_jours"]
        if not isinstance(_j, int) or isinstance(_j, bool) or not DELAI_RELANCE_MIN <= _j <= DELAI_RELANCE_MAX:
            raise HTTPException(status_code=400, detail="Délai de relance : entre %d et %d jours." % (DELAI_RELANCE_MIN, DELAI_RELANCE_MAX))
        _champs["delai_relance_jours"] = _j
    await db[COL_REGLAGES].update_one({"_id": _email}, {"$set": _champs}, upsert=True)
    _doc = await db[COL_REGLAGES].find_one({"_id": _email}) or {}
    return {"mode": _mode, "delais": _propres, "delai_relance_jours": _delai_valide(_doc.get("delai_relance_jours")),
            "automatisation_disponible": AUTOMATISATION_DISPONIBLE}


@router.get("/api/rappels-paiement/liste")
async def liste_rappels(request: Request):
    """Les soldes restants des abonnements ACTUELS visibles par ce coach. Lecture seule, 50 lignes au plus.
    Les abonnements exclus (Stripe…) restent listés avec leur motif : le coach doit comprendre."""
    _email, _admin = await _exiger_coach(request)
    _maintenant = datetime.now(timezone.utc)
    _lignes = []
    async for _s in db.subscriptions.find({"suivi_paiement": {"$type": "object"}, "status": "active"}, {"_id": 0, "id": 1}):
        _ctx = await _contexte(_s.get("id"))
        if not _ctx or not _peut_voir(_ctx.get("code"), _ctx.get("sub"), _email, _admin):
            continue
        if (suivi_paiement_lire(_ctx["sub"]).get("reste_a_payer") or 0) <= 0:
            continue
        _lignes.append(await _ligne_liste(_ctx, _maintenant))
    _lignes.sort(key=lambda x: x.get("prochaine_echeance") or "9999")
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
    _delais = [p for p in (_reg.get("delais") or list(PALIERS_AUTO)) if p in PALIERS_AUTO]
    _lignes = []
    async for _s in db.subscriptions.find({"suivi_paiement": {"$type": "object"}, "status": "active"}, {"_id": 0, "id": 1}):
        _ctx = await _contexte(_s.get("id"))
        if not _ctx or not _peut_voir(_ctx.get("code"), _ctx.get("sub"), _email, _admin):
            continue
        _v = await _verdict(_ctx, ignorer_fenetre=True)
        _vue = suivi_paiement_lire(_ctx["sub"])
        _ech = _vue.get("prochaine_echeance")
        _exclu = _v.get("motif") if not _v["ok"] else ("suivi_incomplet" if _v.get("incomplet") else None)
        _jalons = []
        if _ech and (_v["ok"] or _v.get("motif") != "suivi_incoherent"):
            try:
                _jalons = jalons_simulation(_ech, _delais)
            except ValueError:
                _jalons = []
        _lignes.append({"code": _ctx["sub"].get("code"), "nom": _ctx["sub"].get("name") or "",
                        "reste": _vue.get("reste_a_payer"), "echeance": _ech, "enverrait": _exclu is None,
                        "motif_exclusion": _exclu,
                        "message_exclusion": ("Case « en plusieurs fois » non cochée : à confirmer par le coach."
                                              if _exclu == "suivi_incomplet" else MOTIFS.get(_exclu, "")),
                        "jalons": _jalons})
    _lignes.sort(key=lambda x: x.get("echeance") or "")
    return {"simulation": True, "aucun_envoi": True, "automatisation_disponible": AUTOMATISATION_DISPONIBLE,
            "delais": _delais, "lignes": _lignes[:SIMULATION_MAX]}


@router.get("/api/rappels-paiement/{sub_id}/apercu")
async def apercu_rappel(sub_id: str, request: Request):
    """L'aperçu obligatoire. Lecture seule. 404 (et non 403) sur le client d'un autre coach."""
    _email, _admin = await _exiger_coach(request)
    _ctx = await _contexte(sub_id)
    if not _ctx or not _peut_voir(_ctx.get("code"), _ctx.get("sub"), _email, _admin):
        raise HTTPException(status_code=404, detail="Abonnement introuvable.")
    _v = await _verdict(_ctx)
    _hist = await _historique(sub_id)
    _reel = await _envoi_reel_autorise()
    if not _v["ok"]:
        return {"possible": False, "motif": _v["motif"], "message": _v["message"], "historique": _hist, "envoi_reel": _reel}
    _msg = _message_de(_ctx, _v)
    _delai = await _delai_relance(_ctx)
    _maintenant = datetime.now(timezone.utc)
    _dec = decision_relance(await _docs_abonnement(sub_id), _delai, _maintenant, _v["echeance"])
    _envoi = _vue_envoi(_dec, _delai)
    return {"possible": True, "envoi_reel": _reel, "empreinte": jeton_apercu(empreinte(sub_id, _v), etat_decision(_dec), _email, _maintenant),
            "destinataire": _v["destinataire"],
            "reste": _v["reste"], "devise": _v["devise"], "echeance": _v["echeance"], "avertissement": _v.get("avertissement", ""),
            "verification_requise": bool(_v.get("verification_requise")), "envoi": _envoi,
            "sujet": _msg["sujet"], "texte": _msg["texte"], "code": _ctx["sub"].get("code"), "historique": _hist}


@router.post("/api/rappels-paiement/{sub_id}/envoyer")
async def envoyer_rappel(sub_id: str, corps: EnvoiRappel, request: Request):
    """L'envoi. Le navigateur n'apporte qu'une empreinte et une confirmation : tout le reste
    (montant, abonnement, destinataire, droits) est relu ici, et le message reconstruit ici."""
    _email, _admin = await _exiger_coach(request)
    if corps.confirmation is not True:
        raise HTTPException(status_code=400, detail="Confirmation du coach requise.")
    _ctx = await _contexte(sub_id)
    if not _ctx or not _peut_voir(_ctx.get("code"), _ctx.get("sub"), _email, _admin):
        raise HTTPException(status_code=404, detail="Abonnement introuvable.")
    _v = await _verdict(_ctx)
    if not _v["ok"]:
        raise HTTPException(status_code=409, detail={"type": _v["motif"], "message": _v["message"]})
    _emp = empreinte(sub_id, _v)
    _delai = await _delai_relance(_ctx)
    _instant_envoi = datetime.now(timezone.utc)
    _dec = decision_relance(await _docs_interrompus_inscrits(sub_id, _instant_envoi), _delai, _instant_envoi, _v["echeance"])
    _exiger_permis(_dec, corps.reprise_incertain)
    _jeton = jeton_valide(corps.empreinte, _emp, etat_decision(_dec), _email, _instant_envoi)
    if _jeton == "expire":
        raise HTTPException(status_code=409, detail={"type": "apercu_expire", "message": "Cet aperçu est trop ancien. Rouvre l'aperçu."})
    if _jeton != "ok":
        raise HTTPException(status_code=409, detail={
            "type": "donnees_changees", "message": "Le montant, l'échéance ou les envois ont changé depuis l'aperçu. Rouvre l'aperçu."})
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
    if not await _envoi_reel_autorise():
        return {"issue": "simulation", "envoye": False, "message": "Simulation : aucun e-mail n'a été envoyé."}
    if resend is None or not os.environ.get("RESEND_API_KEY"):
        raise HTTPException(status_code=503, detail="Service d'e-mail non configuré : rien n'a été envoyé.")

    _msg = _message_de(_ctx, _v)
    _base = {"subscription_id": sub_id, "code": _ctx["sub"].get("code"), "coach_id": _ctx.get("proprio", ""),
             "palier": PALIER_MANUEL, "echeance": _v["echeance"], "montant": _v["reste"], "devise": _v["devise"],
             "destinataire": _v["destinataire"], "empreinte": _emp, "envoye_par": _email, "montant_confirme": _confirme}
    _doc = await _reserver(sub_id, _base, corps.reprise_incertain, datetime.now(timezone.utc), _delai)
    _cle = _doc["_id"]
    _reprise = bool(_doc.get("_reprise"))
    # L'échec d'une reprise ne dit rien du premier essai : le message est toujours peut-être parti.
    _si_refus = "incertain" if _reprise else "echec"

    # DERNIÈRE VÉRIFICATION, jeton en main : un paiement saisi pendant la réservation arrête tout.
    _ctx2 = await _contexte(sub_id)
    _v2 = await _verdict(_ctx2) if _ctx2 else {"ok": False, "motif": "aucun_abonnement_actuel", "message": ""}
    if not _v2["ok"] or empreinte(sub_id, _v2) != _emp:
        await _clore_sans_succes(_doc, _si_refus, "donnees_changees")
        raise HTTPException(status_code=409, detail={"type": "donnees_changees", "message": "Les données ont changé : rien n'a été envoyé."})

    _params = {"from": "Afroboost <notifications@afroboost.com>", "to": [_v["destinataire"]],
               "subject": _msg["sujet"], "html": _msg["html"], "text": _msg["texte"]}
    if _base["coach_id"] not in COACHS_BASSI:
        _params["reply_to"] = _base["coach_id"]   # le client d'un partenaire répond à son coach
    _msg_incertain = {"type": "incertain", "reprise_possible": True,
                      "message": "Envoi non confirmé : le message est peut-être parti. Vérifie avant de réessayer."}
    try:
        _brut = await _appel_fournisseur(_cle, _params, {"idempotency_key": _doc["idempotency_key"]})
    except Exception as _err:  # noqa: BLE001
        _issue = "incertain" if _reprise else classer_erreur(_err)
        logger.warning("[V648] envoi %s : %s", _issue, type(_err).__name__)
        _ecrit = await _clore_sans_succes(_doc, _issue, type(_err).__name__)
        if _issue == "incertain" or not _ecrit:
            raise HTTPException(status_code=502, detail=_msg_incertain)
        raise HTTPException(status_code=502, detail={"type": "echec", "message": "L'envoi a été refusé : aucun message n'est parti."})

    _rid = _brut.get("id") if isinstance(_brut, dict) else getattr(_brut, "id", None)
    if not _rid:
        await _clore_sans_succes(_doc, "incertain", "sans_identifiant")
        raise HTTPException(status_code=502, detail=_msg_incertain)
    # Un succès reste un fait, même tardif : seule la clé compte, et un envoi déjà confirmé ne bouge plus.
    _fin = datetime.now(timezone.utc).isoformat()
    await db[COL_RAPPELS].update_one({"_id": _cle, "idempotency_key": _doc["idempotency_key"], "statut": {"$ne": "envoye"}}, {
        "$set": {"statut": "envoye", "resend_id": _rid, "envoye_le": _fin, "maj_le": _fin}, "$unset": {"erreur": ""}})
    logger.info("[V648] rappel de paiement envoyé (échéance %s)", _v["echeance"])
    return {"issue": "envoye", "envoye": True, "envoye_le": _fin, "message": "Rappel envoyé."}
