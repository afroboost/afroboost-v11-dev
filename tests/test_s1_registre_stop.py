# -*- coding: utf-8 -*-
"""S1 — « STOP » DEVIENT EXPRIMABLE POUR LES CIBLES WHATSAPP D'UNE CAMPAGNE.

CE QUE CE LOT REPARE. `_v332_stop_whatsapp` n'ecrit un refus que si le numero a
DEJA une ligne dans `subscribers`. Or la seule porte d'entree du registre est le
formulaire d'opt-in : 6 lignes pour 280 numeros joignables. Mesure du
26/08/2026 : 274 numeros sur 280 tombaient sur « numero non inscrit — rien a
faire ». Repondre STOP ne produisait RIEN, et la campagne suivante repartait.

CE QUE FAIT LE LOT. Au moment ou une cible WhatsApp entre dans le chemin de
campagne, une ligne NEUTRE est creee au registre — ni consentement, ni refus.
C'est tout : le STOP ulterieur trouve alors sa ligne et produit le vrai
`opted_out`, par le chemin EXISTANT, sans qu'une seule ligne de
`_v332_stop_whatsapp` change pour le cas STOP.

ETRE INSCRIT N'EST PAS AVOIR REFUSE, et n'est pas non plus avoir accepte. La
ligne creee porte `status: "targeted"`, sans `consent_at`, sans `consent_text`,
sans `unsubscribe_token`. `v332_liste` ne rend que les `confirmed`,
`c2_consentement` lit tout le reste comme « inconnu », et `c3_refus_exprimes` ne
retient que `opted_out` : cette ligne ne peut se lire ni comme un accord, ni
comme un refus. Les tests B et E le prouvent des deux cotes.

LA REGLE DE SURETE. Un numero n'est inscrit — et n'est envoye — que si l'on
saura reconnaitre son STOP : soit son INDICATIF EST DANS LA DONNEE (`+…`, `00…`),
soit c'est un MOBILE SUISSE EN FORMAT LOCAL (075 a 079, dix chiffres), ce qui est
une lecture du plan de numerotation et non un pari. Tout le reste est ecarte —
`format_phone_e164`, lui, tranche toujours, et fait d'un « 053… » inconnu un
numero ghaneen. Une cible dont on ne saurait pas lire le STOP n'est pas
demarchee du tout.

CE QUE LE LOT NE TOUCHE PAS : le canal e-mail (lot distinct), `List-Unsubscribe`,
les credits, les fournisseurs, la resolution des destinataires, le depliage des
groupes, l'exclusion du numero business, la garde C3, P1-b, P1-d, les rappels.

Aucun reseau. Aucun e-mail. Aucun WhatsApp. Aucune base. Aucune ecriture reelle.

Lancement :  python3 tests/test_s1_registre_stop.py
"""

import ast
import asyncio
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import test_rv2_rappels_push_email as H   # noqa: E402  (faux MongoDB partage)

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
ARBRE = ast.parse(SRC)
LIGNES = SRC.splitlines(keepends=True)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def noeud(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return n
    raise AssertionError("introuvable : %s" % nom)


def source(nom):
    n = noeud(nom)
    return "".join(LIGNES[n.lineno - 1:n.end_lineno])


def code_nu(nom):
    """Le code EXECUTE, sans docstring ni commentaires — les commentaires de ce
    lot citent `opted_out` et `subscribers` pour expliquer, une recherche brute
    les prendrait pour du code."""
    n = noeud(nom)
    corps = list(n.body)
    if (corps and isinstance(corps[0], ast.Expr)
            and isinstance(getattr(corps[0], "value", None), ast.Constant)
            and isinstance(corps[0].value.value, str)):
        corps = corps[1:]
    return "\n".join(ast.unparse(x) for x in corps)


# ------------------------------------------------- faux Mongo, cote ECRITURE
def _appliquer(doc, m, insere):
    """`$setOnInsert` en plus des operateurs du harnais partage.

    Sa semantique EST le coeur du lot : sur un document DEJA present, il ne
    change RIEN. C'est ce qui garantit qu'inscrire une cible ne peut jamais
    ecraser un `opted_out` ni fabriquer un `confirmed`."""
    for op, champs in m.items():
        if op == "$setOnInsert":
            if insere:
                for k, v in champs.items():
                    doc[k] = v
        elif op == "$set":
            for k, v in champs.items():
                doc[k] = v
        elif op == "$unset":
            for k in champs:
                doc.pop(k, None)
        else:
            raise AssertionError("operateur non simule : %s" % op)


class _Registre(H._Coll):
    """`subscribers` avec upsert et `bulk_write`, plus un compteur d'ecritures.

    Le compteur sert les tests C et F : « aucune inscription » ne se prouve pas
    en regardant seulement le contenu final, il faut aussi montrer qu'aucune
    ecriture n'a ete TENTEE."""

    def __init__(self, docs=None):
        H._Coll.__init__(self, docs)
        self.ecritures = 0
        self.allers_retours = 0

    async def update_one(self, q, m, upsert=False, **k):
        await asyncio.sleep(0)
        self.allers_retours += 1
        for d in self.docs:
            if H._match(d, q):
                avant = dict(d)
                _appliquer(d, m, insere=False)
                if d != avant:
                    self.ecritures += 1
                return _Res(1, 0)
        if not upsert:
            return _Res(0, 0)
        neuf = dict(q)
        _appliquer(neuf, m, insere=True)
        self.docs.append(neuf)
        self.ecritures += 1
        return _Res(0, 1)

    async def bulk_write(self, ops, ordered=True):
        await asyncio.sleep(0)
        self.allers_retours += 1          # UN seul trajet, quel que soit le nombre
        crees = 0
        for op in ops:
            trouve = None
            for d in self.docs:
                if H._match(d, op._filter):
                    trouve = d
                    break
            if trouve is not None:
                avant = dict(trouve)
                _appliquer(trouve, op._doc, insere=False)
                if trouve != avant:
                    self.ecritures += 1
            elif getattr(op, "_upsert", False):
                neuf = dict(op._filter)
                _appliquer(neuf, op._doc, insere=True)
                self.docs.append(neuf)
                self.ecritures += 1
                crees += 1
        return _Res(0, crees)


class _Res(object):
    def __init__(self, matched, upserted):
        self.matched_count = matched
        self.modified_count = matched
        self.upserted_count = upserted


# ------------------------------------------------------- le bac d'execution
A_EXTRAIRE = ["format_phone_e164", "_v332_normaliser",
              "s1_valeur_sure", "s1_inscrire_cibles",
              "_v332_stop_whatsapp",
              "c3_refus_exprimes", "c3_refus_exprime", "c3_verdict",
              "_v286_should_send_notification", "p1b_destinataire_autorise"]

def constante(nom):
    """La constante telle qu'elle est ECRITE dans server.py, pas une copie.

    Une copie en dur dans le harnais finirait par diverger du code — et un test
    qui affirme « le statut n'est pas un refus » ne vaut que s'il parle du statut
    reellement utilise en production."""
    for n in ARBRE.body:
        if isinstance(n, ast.Assign) and any(
                isinstance(c, ast.Name) and c.id == nom for c in n.targets):
            return "".join(LIGNES[n.lineno - 1:n.end_lineno])
    raise AssertionError("constante introuvable : %s" % nom)


PREAMBULE = """
P1B_PREFIXE = "[P1-b]"
P1B_TYPE_PREFERENCE = "trial_followup"
C3_CANAUX_CAMPAGNE = ("email", "whatsapp")
""" + constante("S1_STATUT_CIBLE") + constante("S1_SOURCE_CIBLE") \
    + constante("S1_MOBILE_CH_LOCAL")


def bac(docs=None, prefs=None):
    import datetime as _dt
    import uuid as _uuid
    base = type("B", (), {})()
    base.subscribers = _Registre(docs or [])
    base.notification_preferences = H._Coll(prefs or [])
    b = {
        "db": base, "asyncio": asyncio, "os": os, "re": __import__("re"),
        "datetime": _dt.datetime, "timezone": _dt.timezone, "uuid": _uuid,
        "logger": type("l", (), {k: staticmethod(lambda *a, **kw: None)
                                 for k in ("info", "warning", "error", "debug")}),
    }
    morceaux = [PREAMBULE] + [source(f) for f in A_EXTRAIRE]
    exec(compile("\n\n".join(morceaux), "<s1>", "exec"), b)
    absents = [f for f in A_EXTRAIRE if f not in b]
    assert not absents, "extraction incomplete : %s" % absents
    return b, base.subscribers


def ligne(valeur, statut, **extra):
    d = {"channel": "whatsapp", "value": valeur, "status": statut}
    d.update(extra)
    return d


SUISSE = "+41791112233"
FRANCE = "+33765880749"


# =============================================================== A. inscription
async def a_inscription():
    b, reg = bac()
    cree = await b["s1_inscrire_cibles"]([SUISSE])
    verifier("A. une cible joignable entre au registre", cree == 1, repr(cree))
    verifier("A2. exactement une ligne, sur le canal whatsapp",
             len(reg.docs) == 1 and reg.docs[0]["channel"] == "whatsapp",
             repr(reg.docs))
    verifier("A3. la valeur stockee est la forme canonique",
             reg.docs[0]["value"] == SUISSE, repr(reg.docs[0].get("value")))

    # 270 cibles ne doivent pas coûter 270 trajets : la regle du depot sur les
    # grands groupes vaut aussi pour les ecritures.
    b, reg = bac()
    beaucoup = ["+4179111%04d" % i for i in range(270)]
    await b["s1_inscrire_cibles"](beaucoup)
    verifier("A4. 270 cibles = UN SEUL aller-retour",
             reg.allers_retours == 1, "trajets=%d" % reg.allers_retours)
    verifier("A5. et 270 lignes creees", len(reg.docs) == 270, len(reg.docs))


# ====================================================== B. inscrit != opted_out
async def b_inscrit_nest_pas_refus():
    b, reg = bac()
    await b["s1_inscrire_cibles"]([SUISSE])
    doc = reg.docs[0]

    verifier("B. la ligne creee n'est PAS un refus",
             doc.get("status") != "opted_out", repr(doc.get("status")))
    verifier("B2. elle n'est pas non plus un consentement",
             doc.get("status") != "confirmed", repr(doc.get("status")))
    verifier("B3. aucune preuve de consentement n'est fabriquee",
             not doc.get("consent_at") and not doc.get("consent_text"),
             repr({k: doc.get(k) for k in ("consent_at", "consent_text")}))

    # La preuve qui compte : la garde des campagnes ne la lit pas comme un refus.
    refus = await b["c3_refus_exprimes"]("whatsapp", [SUISSE])
    verifier("B4. la garde C3 n'y voit aucun refus", refus == set(), repr(refus))
    verifier("B5. la cible reste donc envoyable",
             b["c3_verdict"]("whatsapp", SUISSE, refus, set()) == "")


# ================================================================ C. doublons
async def c_doublons():
    b, reg = bac()
    await b["s1_inscrire_cibles"]([SUISSE, SUISSE, "+41 79 111 22 33"])
    verifier("C. le meme numero ecrit de trois facons = une seule ligne",
             len(reg.docs) == 1, repr(reg.docs))

    cree = await b["s1_inscrire_cibles"]([SUISSE])
    verifier("C2. une campagne suivante ne recree rien", cree == 0, repr(cree))
    verifier("C3. et n'ecrit rien du tout", reg.ecritures == 1,
             "ecritures=%d" % reg.ecritures)

    # Le point le plus important : une ligne existante n'est JAMAIS ecrasee.
    b, reg = bac([ligne(SUISSE, "confirmed", consent_at="2026-08-05T00:00:00+00:00",
                        consent_text="J'accepte", unsubscribe_token="jeton")])
    await b["s1_inscrire_cibles"]([SUISSE])
    verifier("C4. un consentement existant reste intact",
             reg.docs[0]["status"] == "confirmed"
             and reg.docs[0]["consent_at"] == "2026-08-05T00:00:00+00:00"
             and reg.docs[0]["unsubscribe_token"] == "jeton", repr(reg.docs[0]))
    verifier("C5. et aucune ecriture n'a eu lieu", reg.ecritures == 0,
             "ecritures=%d" % reg.ecritures)


# ============================================== D. le STOP devient fonctionnel
async def d_stop_fonctionnel():
    # Le parcours complet, dans l'ordre reel : ciblage, puis STOP, puis campagne.
    b, reg = bac()
    await b["s1_inscrire_cibles"]([SUISSE])
    traite = await b["_v332_stop_whatsapp"]("41791112233", "STOP")
    verifier("D. le STOP est traite comme une commande", traite is True, repr(traite))
    verifier("D2. et produit un VRAI refus",
             reg.docs[0]["status"] == "opted_out", repr(reg.docs[0]))
    verifier("D3. et le refus est date",
             bool(reg.docs[0].get("updated_at")), repr(reg.docs[0]))
    # DETTE CONSIGNEE, HORS LOT : le STOP WhatsApp ne pose pas `opted_out_at`,
    # alors que le lien de desinscription (`v332_unsubscribe`) le fait. Les deux
    # chemins produisent le meme `status`, donc la garde C3 se comporte
    # identiquement — seule la tracabilite RGPD du MOMENT du refus differe. Le
    # test le CONSTATE plutot que de l'exiger : corriger cette asymetrie
    # changerait le traitement du STOP, ce que ce lot s'interdit.
    verifier("D3b. (dette constatee) le STOP WhatsApp n'horodate pas `opted_out_at`",
             reg.docs[0].get("opted_out_at") is None, repr(reg.docs[0]))

    refus = await b["c3_refus_exprimes"]("whatsapp", [SUISSE])
    verifier("D4. la campagne suivante l'ecarte",
             b["c3_verdict"]("whatsapp", SUISSE, refus, set()) == "refus")

    # Variantes de langue et de ponctuation, deja gerees — on verifie qu'elles
    # produisent bien un refus maintenant qu'une ligne existe.
    for mot in ("stop", "Arrêt !", "Désabonner.", "unsubscribe"):
        b, reg = bac()
        await b["s1_inscrire_cibles"]([SUISSE])
        await b["_v332_stop_whatsapp"]("41791112233", mot)
        verifier("D5. « %s » enregistre le refus" % mot,
                 reg.docs[0]["status"] == "opted_out", repr(reg.docs[0]))

    # Un message ordinaire ne doit rien ecrire ni couper le flux.
    b, reg = bac()
    await b["s1_inscrire_cibles"]([SUISSE])
    ecritures = reg.ecritures
    traite = await b["_v332_stop_whatsapp"]("41791112233", "Bonjour, un cours demain ?")
    verifier("D6. un message ordinaire n'est pas une commande", traite is False)
    verifier("D7. et n'ecrit rien", reg.ecritures == ecritures)

    # START ne doit PAS fabriquer un consentement sur une ligne de ciblage :
    # personne n'a coche de case. Sans cette garde, le lot creerait un
    # consentement RGPD a partir d'un simple « oui ».
    b, reg = bac()
    await b["s1_inscrire_cibles"]([SUISSE])
    await b["_v332_stop_whatsapp"]("41791112233", "START")
    verifier("D8. START sur une ligne de ciblage ne fabrique aucun consentement",
             reg.docs[0]["status"] != "confirmed", repr(reg.docs[0]))

    # Mais un vrai inscrit qui s'etait desabonne peut revenir : sa ligne PORTE
    # une preuve de consentement, ce chemin ne change pas.
    b, reg = bac([ligne(SUISSE, "opted_out", consent_at="2026-08-05T00:00:00+00:00",
                        consent_text="J'accepte")])
    await b["_v332_stop_whatsapp"]("41791112233", "START")
    verifier("D9. un inscrit qui avait consenti peut revenir",
             reg.docs[0]["status"] == "confirmed", repr(reg.docs[0]))


# ============================================ E. un refus existant est respecte
async def e_refus_existant():
    b, reg = bac([ligne(SUISSE, "opted_out", opted_out_at="2026-08-20T10:00:00+00:00")])
    cree = await b["s1_inscrire_cibles"]([SUISSE])
    verifier("E. cibler quelqu'un qui a refuse ne cree rien", cree == 0, repr(cree))
    verifier("E2. son refus reste intact",
             reg.docs[0]["status"] == "opted_out"
             and reg.docs[0]["opted_out_at"] == "2026-08-20T10:00:00+00:00",
             repr(reg.docs[0]))
    verifier("E3. aucune ecriture", reg.ecritures == 0, "ecritures=%d" % reg.ecritures)

    refus = await b["c3_refus_exprimes"]("whatsapp", [SUISSE])
    verifier("E4. la garde C3 l'ecarte toujours",
             b["c3_verdict"]("whatsapp", SUISSE, refus, set()) == "refus")


# ================================== F. numero non normalisable de facon sure
async def f_numero_non_sur():
    """Ce qui reste ecarte, et qui doit le rester.

    La regle a ete ELARGIE aux mobiles suisses locaux (cf. `f2_mobiles_suisses`) :
    ecarter 26 % des cibles d'une campagne pour se premunir d'une ambiguite
    theorique coutait plus cher que le risque. Ce qui suit est ce qui reste
    dehors, et pour chacun la raison tient en une phrase : on ne saurait pas
    reconnaitre le STOP de cette personne.
    """
    b, reg = bac()
    ecartes = (
        # Prefixes qui n'existent PAS comme mobiles suisses. Certains sont des
        # fixes suisses REELS (021 Lausanne, 055 Rapperswil) — WhatsApp ne
        # s'adresse pas a un fixe, les ecarter est exact.
        ("0532545508", "prefixe 053 inexistant en Suisse"),
        ("0502851261", "prefixe 050 inexistant en Suisse"),
        ("0596854367", "prefixe 059 inexistant en Suisse"),
        ("0212345678", "fixe suisse (Lausanne), pas un mobile"),
        ("0552251470", "fixe suisse (Rapperswil), pas un mobile"),
        ("0745203363", "074 n'est pas un prefixe mobile suisse"),
        # Mobile francais en format LOCAL : 06 n'existe pas en Suisse, et le
        # transformer en +41 fabriquerait un numero qui n'est pas le sien.
        ("0612345678", "mobile francais local — ce serait deviner un indicatif"),
        # Longueurs impossibles.
        ("07654355442", "11 chiffres"),
        ("076520345", "9 chiffres"),
        ("079", "trop court"),
        ("", "vide"), (None, "absent"), ("pas-un-numero", "pas un numero"),
    )
    for brut, pourquoi in ecartes:
        verifier("F. « %s » reste ecarte (%s)" % (brut, pourquoi),
                 b["s1_valeur_sure"](brut) == "", repr(b["s1_valeur_sure"](brut)))

    cree = await b["s1_inscrire_cibles"](["0532545508", "0612345678", "", None])
    verifier("F2. aucune de ces cibles n'entre au registre",
             cree == 0 and len(reg.docs) == 0, repr(reg.docs))
    verifier("F3. et aucun aller-retour n'est meme tente",
             reg.allers_retours == 0, "trajets=%d" % reg.allers_retours)

    # Un indicatif ETRANGER ne se devine toujours pas, et un prefixe inconnu non
    # plus : le helper historique, lui, tranchait dans les deux cas.
    verifier("F4. le helper historique fait d'un 06 francais un +33",
             b["format_phone_e164"]("0612345678") == "+33612345678",
             b["format_phone_e164"]("0612345678"))
    # Et il ne s'arrete pas a +41 : un prefixe qu'il ne reconnait pas devient un
    # numero GHANEEN. Mesure faite : « 0532545508 » -> « +233532545508 ». C'est
    # exactement le genre de valeur qui ne correspondrait a aucun STOP recu.
    verifier("F5. le helper fait d'un 053 inconnu un numero ghaneen",
             b["format_phone_e164"]("0532545508") == "+233532545508",
             b["format_phone_e164"]("0532545508"))
    verifier("F6. la ou nous refusons plutot que de parier",
             b["s1_valeur_sure"]("0532545508") == "")


# ================================ F2. les mobiles suisses locaux sont reconnus
async def f2_mobiles_suisses():
    """LE correctif : un mobile suisse ecrit « 076… » n'est plus ecarte.

    MESURE QUI A DECIDE (26/08/2026, donnees reelles) : la regle « indicatif
    obligatoire » ecartait 26 %, 17 % et 16 % des cibles des trois campagnes —
    dont 90 mobiles suisses parfaitement valides (076 x49, 078 x23, 079 x16,
    077 x2) que le coach saisit sans indicatif depuis toujours. Sur l'univers
    entier : 32 % d'exclusion, ramenes a 9 %.

    CE QUE CE N'EST PAS. Ce n'est pas « deviner un indicatif ». Un prefixe mobile
    suisse valide, sur exactement dix chiffres, DESIGNE un numero suisse : c'est
    une lecture du plan de numerotation, pas un pari. Le pari — que ce lot refuse
    toujours — serait de decider qu'un « 06… » francais ou un « 020… » inconnu
    est suisse parce qu'on n'a rien de mieux.

    RISQUE RESIDUEL, ASSUME ET ECRIT : la France attribue elle aussi des mobiles
    en 07, et « 0765880749 » s'ecrit exactement comme un 076 suisse. Un contact
    francais saisi en format LOCAL sera donc lu comme suisse. Le depot en heberge
    — mais stockes AVEC leur `+33`, donc reconnus sans ambiguite. Le cas qui
    resterait faux est celui d'un numero etranger saisi sans indicatif : il
    l'etait deja avant ce lot, et l'inscription au registre ne l'aggrave pas.
    """
    b, _ = bac()
    for brut, attendu in (("0765203363", "+41765203363"),
                          ("076 520 33 63", "+41765203363"),
                          ("076-520-33-63", "+41765203363"),
                          ("0752693565", "+41752693565"),
                          ("0772693565", "+41772693565"),
                          ("0786240606", "+41786240606"),
                          ("0799193486", "+41799193486")):
        verifier("F2a. « %s » -> %s" % (brut, attendu),
                 b["s1_valeur_sure"](brut) == attendu, b["s1_valeur_sure"](brut))

    # La valeur inscrite doit etre EXACTEMENT celle que Meta renverra au STOP,
    # sinon le refus serait enregistre a cote et ne bloquerait rien.
    b, reg = bac()
    cree = await b["s1_inscrire_cibles"](["0765203363"])
    verifier("F2b. le mobile suisse local entre au registre", cree == 1, repr(cree))
    _ligne = reg.docs[0] if reg.docs else {}
    verifier("F2c. sous sa forme canonique",
             _ligne.get("value") == "+41765203363", repr(_ligne))
    await b["_v332_stop_whatsapp"]("41765203363", "STOP")
    _ligne = reg.docs[0] if reg.docs else {}
    verifier("F2d. et son STOP le bloque — meme valeur des deux cotes",
             _ligne.get("status") == "opted_out", repr(_ligne))
    _r = await b["c3_refus_exprimes"]("whatsapp", ["0765203363"])
    verifier("F2e. la campagne suivante l'ecarte, meme ecrit en local",
             b["c3_verdict"]("whatsapp", "0765203363", _r, set()) == "refus")

    # Les trois ecritures de la MEME personne ne font qu'une seule ligne.
    b, reg = bac()
    await b["s1_inscrire_cibles"](["0765203363", "+41765203363", "0041765203363"])
    verifier("F2f. local, +41 et 0041 sont le meme numero",
             len(reg.docs) == 1, repr(reg.docs))


# ======================================================= G / H. les numeros surs
async def g_h_numeros_surs():
    b, _ = bac()
    # G. Suisse, sous les formes qui PORTENT leur indicatif.
    for brut in ("+41791112233", "+41 79 111 22 33", "+41-79-111-22-33",
                 "0041791112233", "0041 79 111 22 33"):
        verifier("G. « %s » -> %s" % (brut, SUISSE),
                 b["s1_valeur_sure"](brut) == SUISSE, b["s1_valeur_sure"](brut))

    # H. International deja canonique : conserve TEL QUEL, jamais suissifie.
    for brut, attendu in (("+33765880749", FRANCE),
                          ("+33 7 65 88 07 49", FRANCE),
                          ("+447876137368", "+447876137368"),
                          ("00233201234567", "+233201234567")):
        verifier("H. « %s » -> %s" % (brut, attendu),
                 b["s1_valeur_sure"](brut) == attendu, b["s1_valeur_sure"](brut))

    verifier("H2. un numero francais n'est jamais transforme en suisse",
             not b["s1_valeur_sure"](FRANCE).startswith("+41"))

    # La valeur inscrite doit etre EXACTEMENT celle que la garde C3 comparera,
    # sinon le refus enregistre ne bloquerait rien.
    b, reg = bac()
    await b["s1_inscrire_cibles"]([FRANCE])
    refus_apres_stop = await b["c3_refus_exprimes"]("whatsapp", [FRANCE])
    verifier("H3. inscrite, la cible reste envoyable", refus_apres_stop == set())
    await b["_v332_stop_whatsapp"]("33765880749", "STOP")
    refus_apres_stop = await b["c3_refus_exprimes"]("whatsapp", [FRANCE])
    verifier("H4. son STOP la bloque — meme valeur des deux cotes",
             refus_apres_stop == {FRANCE}, repr(refus_apres_stop))


# ============================================================ I. P1-b inchange
async def i_p1b_inchange():
    b, _ = bac([{"channel": "email", "value": "abo@exemple.com",
                 "status": "opted_out"}])
    verifier("I. P1-b refuse toujours une adresse desinscrite",
             await b["p1b_destinataire_autorise"]("abo@exemple.com") is False)
    b, _ = bac()
    verifier("I2. et laisse passer une adresse qui n'a rien refuse",
             await b["p1b_destinataire_autorise"]("abo@exemple.com") is True)
    verifier("I3. P1-b passe toujours par la garde partagee",
             "c3_refus_exprime" in code_nu("p1b_destinataire_autorise"))
    verifier("I4. S1 ne touche pas P1-b",
             "s1_" not in code_nu("p1b_destinataire_autorise"))


# ==================================== J. P1-d, et le reste du monde, intacts
def j_hors_perimetre():
    lancement = code_nu("launch_campaign")
    inscription = code_nu("s1_inscrire_cibles")
    sure = code_nu("s1_valeur_sure")

    verifier("J. le lot n'introduit aucun drapeau",
             "P1_TRIAL" not in (lancement + inscription + sure)
             and "feature_flag" not in (inscription + sure))
    verifier("J2. P1-d garde ses deux drapeaux",
             "P1_TRIAL_J3_ENABLED" in SRC and "P1_TRIAL_J3_ENVOI_REEL" in SRC)

    # Le canal e-mail est HORS LOT : l'inscription ne doit jamais l'ecrire.
    verifier("J3. l'inscription ne concerne que le canal whatsapp",
             '"email"' not in inscription and "'email'" not in inscription,
             inscription[:200])
    verifier("J4. aucun en-tete de desinscription n'est ajoute",
             "_v336_entetes_desinscription" not in lancement)

    # Aucune route nouvelle, aucun decorateur sur les fonctions du lot.
    for nom in ("s1_valeur_sure", "s1_inscrire_cibles"):
        verifier("J5. `%s` n'est pas une route" % nom,
                 not noeud(nom).decorator_list)

    # Les garde-fous existants de la campagne restent en place.
    for marqueur, quoi in (("business_phone_number", "l'exclusion du numero business"),
                           ("_c3_wa", "la garde C3 WhatsApp"),
                           ("_c3_mail", "la garde C3 e-mail"),
                           ("skipped_count", "le compte des ecarts")):
        verifier("J6. %s est toujours la" % quoi, marqueur in lancement)


# ============================================ structure : l'ordre dans le code
def structure():
    src = source("launch_campaign")
    pos_inscription = src.find("s1_inscrire_cibles")
    pos_boucle = src.find("for contact in contacts:")
    pos_valeur = src.find("s1_valeur_sure")

    verifier("S. l'inscription a lieu AVANT la boucle des destinataires",
             0 < pos_inscription < pos_boucle,
             "inscription=%d boucle=%d" % (pos_inscription, pos_boucle))
    verifier("S2. la valeur sure est calculee dans la boucle",
             pos_valeur > pos_boucle, "valeur=%d" % pos_valeur)

    # La condition d'envoi WhatsApp doit EXIGER la valeur sure : sans cela, un
    # numero dont le STOP ne marcherait pas serait quand meme demarche.
    envois = [l for l in src.splitlines()
              if 'channels.get("whatsapp")' in l and "contact_phone" in l and "if" in l]
    verifier("S3. l'envoi WhatsApp exige une valeur sure",
             any("_s1_val" in l for l in envois), repr(envois))

    # Le canal e-mail garde exactement sa condition d'avant.
    mails = [l for l in src.splitlines()
             if 'channels.get("email")' in l and "contact_email" in l and "if" in l]
    verifier("S4. le canal e-mail n'est pas touche",
             all("_s1" not in l for l in mails), repr(mails))

    verifier("S5. l'ecart est compte, jamais silencieux",
             src.count("skipped_count += 1") >= 3, src.count("skipped_count += 1"))

    verifier("S6. une seule ecriture groupee, pas une par destinataire",
             "bulk_write" in code_nu("s1_inscrire_cibles"))
    verifier("S7. et jamais un ecrasement : `$setOnInsert` uniquement",
             "$setOnInsert" in code_nu("s1_inscrire_cibles")
             and "$set'" not in code_nu("s1_inscrire_cibles").replace("$setOnInsert", ""))


def main():
    boucle = asyncio.new_event_loop()
    for etape in (a_inscription, b_inscrit_nest_pas_refus, c_doublons,
                  d_stop_fonctionnel, e_refus_existant, f_numero_non_sur,
                  f2_mobiles_suisses, g_h_numeros_surs, i_p1b_inchange):
        boucle.run_until_complete(etape())
    j_hors_perimetre()
    structure()
    boucle.close()

    ok = 0
    for nom, res, detail in RESULTATS:
        print("  %s  %s%s" % ("PASS" if res else "ECHEC", nom,
                              "" if res else "   -> %s" % detail))
        ok += 1 if res else 0
    print("=" * 78)
    print("E-mails REELLEMENT envoyes : 0 — `resend` n'est jamais importe")
    print("WhatsApp REELLEMENT envoyes: 0 — aucun module de messagerie charge")
    print("Ecritures en production    : 0 — aucune base, aucun reseau")
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())
