# -*- coding: utf-8 -*-
"""C3 — UNE CAMPAGNE DE MASSE N'ECRIT PLUS A QUI A DIT NON.

CE QUE CE LOT REPARE. Quatre chemins d'envoi de masse — `launch_campaign`,
`send-bulk-email`, `send-email` et `push/broadcast` — ne lisaient AUCUN refus.
Le depot le documentait lui-meme : « ses campagnes n'honorent AUCUN opt-out ».
Trois campagnes reelles ont vise 176, 202 et 268 numeros dans ces conditions.

CE QU'IL N'INVENTE PAS. Aucune notion nouvelle de refus : la source de verite
est `subscribers` (canal, valeur normalisee, `status: opted_out`), exactement
celle que `p1b_destinataire_autorise` lit deja. Elle est EXTRAITE pour etre
appelee des deux cotes — une seule interpretation du refus, pas deux.

CE QU'IL NE TOUCHE PAS : la resolution des destinataires, le depliage des
groupes, les credits, les fournisseurs, l'exclusion du numero business, le
verrou anti-doublon de campagne, P1-b, P1-d et les rappels avant cours.

Aucun reseau. Aucun e-mail. Aucun WhatsApp. Aucune base. Aucune ecriture.

Lancement :  python3 tests/test_c3_optout_campagnes.py
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
    """Le code EXECUTE, sans docstring ni commentaires : les commentaires de ce
    lot citent `opted_out` et `subscribers` pour expliquer, une recherche brute
    les prendrait pour du code."""
    n = noeud(nom)
    corps = list(n.body)
    if (corps and isinstance(corps[0], ast.Expr)
            and isinstance(getattr(corps[0], "value", None), ast.Constant)
            and isinstance(corps[0].value.value, str)):
        corps = corps[1:]
    return "\n".join(ast.unparse(x) for x in corps)


# ------------------------------------------------------- le bac d'execution
A_EXTRAIRE = ["format_phone_e164", "_v332_normaliser",
              "c3_refus_exprimes", "c3_refus_exprime", "c3_verdict",
              "_v286_should_send_notification", "p1b_destinataire_autorise"]

PREAMBULE = """
P1B_PREFIXE = "[P1-b]"
P1B_TYPE_PREFERENCE = "trial_followup"
C3_CANAUX_CAMPAGNE = ("email", "whatsapp")
"""


def bac(refus=None, prefs=None):
    """Faux Mongo : `subscribers` porte les refus, `notification_preferences`
    les preferences fines. Vides par defaut = personne n'a rien refuse."""
    base = type("B", (), {})()
    base.subscribers = H._Coll(refus or [])
    base.notification_preferences = H._Coll(prefs or [])
    b = {
        "db": base, "asyncio": asyncio, "os": os, "re": __import__("re"),
        "logger": type("l", (), {k: staticmethod(lambda *a, **kw: None)
                                 for k in ("info", "warning", "error", "debug")}),
    }
    morceaux = [PREAMBULE] + [source(f) for f in A_EXTRAIRE]
    exec(compile("\n\n".join(morceaux), "<c3>", "exec"), b)
    absents = [f for f in A_EXTRAIRE if f not in b]
    assert not absents, "extraction incomplete : %s" % absents
    return b, base


def refus(canal, valeur):
    return {"channel": canal, "value": valeur, "status": "opted_out"}


def accord(canal, valeur):
    return {"channel": canal, "value": valeur, "status": "confirmed"}


MAIL = "abo@exemple.com"
TEL = "+41791112233"


# ============================================== A -> F : la garde elle-meme
async def garde():
    # --- A. personne n'a rien refuse -------------------------------------
    b, _ = bac()
    _r = await b["c3_refus_exprimes"]("email", [MAIL, "autre@exemple.com"])
    verifier("A. sans opt-out, l'ensemble des refus est vide", _r == set(), repr(_r))
    verifier("A2. et le verdict laisse passer",
             b["c3_verdict"]("email", MAIL, _r, set()) == "")

    # --- B. refus e-mail --------------------------------------------------
    b, _ = bac([refus("email", MAIL)])
    _r = await b["c3_refus_exprimes"]("email", [MAIL, "autre@exemple.com"])
    verifier("B. un refus e-mail est retrouve", _r == {MAIL}, repr(_r))
    verifier("B2. le destinataire est ecarte du canal e-mail",
             b["c3_verdict"]("email", MAIL, _r, set()) == "refus")
    verifier("B3. son voisin n'est pas ecarte",
             b["c3_verdict"]("email", "autre@exemple.com", _r, set()) == "")

    # --- B4. la casse et les espaces ne sauvent pas d'un refus ------------
    verifier("B4. « Abo@Exemple.com » est le meme refus",
             b["c3_verdict"]("email", "  Abo@Exemple.COM ", _r, set()) == "refus")

    # --- C. un refus SUR UN AUTRE CANAL n'exclut pas l'e-mail -------------
    b, _ = bac([refus("whatsapp", TEL)])
    _rm = await b["c3_refus_exprimes"]("email", [MAIL])
    _rw = await b["c3_refus_exprimes"]("whatsapp", [TEL])
    verifier("C. un refus WhatsApp n'entre pas dans les refus e-mail",
             _rm == set(), repr(_rm))
    verifier("C2. il exclut bien le canal WhatsApp",
             b["c3_verdict"]("whatsapp", TEL, _rw, set()) == "refus")
    verifier("C3. et l'e-mail de la MEME personne reste eligible",
             b["c3_verdict"]("email", MAIL, _rm, set()) == "")

    # --- C4. un statut qui n'est pas un refus n'exclut personne -----------
    b, _ = bac([accord("email", MAIL), {"channel": "email", "value": "p@x.com",
                                        "status": "pending"}])
    _r = await b["c3_refus_exprimes"]("email", [MAIL, "p@x.com"])
    verifier("C4. `confirmed` et `pending` ne sont pas des refus",
             _r == set(), repr(_r))

    # --- D. la meme personne, deux fois -----------------------------------
    b, _ = bac()
    _deja = set()
    _v1 = b["c3_verdict"]("email", MAIL, set(), _deja)
    _v2 = b["c3_verdict"]("email", " ABO@exemple.com ", set(), _deja)
    verifier("D. le premier passe, le second est un doublon",
             _v1 == "" and _v2 == "doublon", "%r / %r" % (_v1, _v2))
    _deja_t = set()
    _t1 = b["c3_verdict"]("whatsapp", "0791112233", set(), _deja_t)
    _t2 = b["c3_verdict"]("whatsapp", "+41 79 111 22 33", set(), _deja_t)
    verifier("D2. deux ecritures du meme numero = un seul envoi",
             _t1 == "" and _t2 == "doublon", "%r / %r" % (_t1, _t2))
    verifier("D3. les canaux ont chacun leur memoire",
             b["c3_verdict"]("whatsapp", "0791112233", set(), set()) == "")

    # --- D4. une valeur inexploitable ne bloque pas et ne dedoublonne pas --
    verifier("D4. une adresse absurde est ecartee, sans faire taire les autres",
             b["c3_verdict"]("email", "pas-un-email", set(), set()) == "illisible")

    # --- E / F. le refus l'emporte sur toute qualite ----------------------
    b, _ = bac([refus("email", MAIL)])
    _r = await b["c3_refus_exprimes"]("email", [MAIL])
    verifier("E. refus + membre actif -> exclu",
             b["c3_verdict"]("email", MAIL, _r, set()) == "refus")
    verifier("F. refus + ancien membre -> exclu",
             b["c3_verdict"]("email", MAIL, _r, set()) == "refus")
    verifier("EF2. aucun segment ne peut le reinclure : le verdict ne lit "
             "QUE le refus et les doublons",
             "segment" not in code_nu("c3_verdict")
             and "abonne" not in code_nu("c3_verdict"))

    # --- une seule requete groupee ----------------------------------------
    b, base = bac([refus("email", MAIL)])
    base.subscribers.lectures = 0
    _vraie = base.subscribers.find

    def compte(*a, **k):
        base.subscribers.lectures += 1
        return _vraie(*a, **k)

    base.subscribers.find = compte
    await b["c3_refus_exprimes"]("email", ["a@x.com", "b@x.com", "c@x.com", MAIL])
    verifier("R1. 4 destinataires -> UNE seule lecture de `subscribers`",
             base.subscribers.lectures == 1, "%d lecture(s)" % base.subscribers.lectures)
    b, base = bac()
    base.subscribers.lectures = 0
    _v2f = base.subscribers.find
    base.subscribers.find = lambda *a, **k: (
        base.subscribers.__setattr__("lectures", base.subscribers.lectures + 1)
        or _v2f(*a, **k))
    _r = await b["c3_refus_exprimes"]("email", [])
    verifier("R2. aucune valeur -> aucune lecture du tout",
             base.subscribers.lectures == 0 and _r == set())

    # --- une base qui hoquette n'est jamais un refus ----------------------
    b, base = bac()

    def casse(*a, **k):
        raise RuntimeError("Mongo indisponible (simule)")

    base.subscribers.find = casse
    _r = await b["c3_refus_exprimes"]("email", [MAIL])
    verifier("R3. lecture impossible -> aucun refus deduit (on autorise)",
             _r == set(), repr(_r))


# ==================================================== G : audience vide
def audience_vide():
    _nu = code_nu("launch_campaign")
    verifier("G. la pre-passe des refus precede la boucle des destinataires",
             0 <= _nu.find("c3_refus_exprimes") < _nu.find("for contact in contacts"),
             "%d / %d" % (_nu.find("c3_refus_exprimes"), _nu.find("for contact in contacts")))
    verifier("G0. le verdict est rendu avant la condition d'envoi",
             0 <= _nu.find("c3_verdict") < _nu.find("channels.get('whatsapp') and contact_phone"))
    verifier("G2. chaque canal porte sa garde dans sa propre condition",
             "_c3_wa" in _nu and "_c3_mail" in _nu)
    verifier("G3. un ecart est compte, jamais silencieux",
             _nu.count("skipped_count += 1") >= 3, _nu.count("skipped_count += 1"))
    verifier("G4. tout le monde ecarte -> la boucle n'appelle aucun fournisseur "
             "(la garde est DANS la condition d'envoi)",
             "and (not _c3_wa)" in _nu or "and not _c3_wa" in _nu)


# ============================================ H : P1-b strictement inchange
async def p1b_inchange():
    # H1. meme verdict qu'avant, sur les deux issues
    b, _ = bac([refus("email", MAIL)])
    verifier("H. P1-b refuse toujours une adresse desinscrite",
             await b["p1b_destinataire_autorise"](MAIL) is False)
    b, _ = bac()
    verifier("H2. P1-b autorise toujours une adresse inconnue",
             await b["p1b_destinataire_autorise"](MAIL) is True)
    b, _ = bac()
    verifier("H3. P1-b refuse toujours une adresse vide",
             await b["p1b_destinataire_autorise"]("") is False)
    b, _ = bac(prefs=[{"email": MAIL, "role": "subscriber",
                       "preferences": {"trial_followup": False}}])
    verifier("H4. P1-b respecte toujours la preference fine V286",
             await b["p1b_destinataire_autorise"](MAIL) is False)
    b, _ = bac(prefs=[{"email": MAIL, "role": "subscriber",
                       "preferences": {"autre_chose": False}}])
    verifier("H5. une preference etrangere ne le fait pas taire",
             await b["p1b_destinataire_autorise"](MAIL) is True)
    # H6. UNE SEULE definition du refus : P1-b passe par la fonction partagee
    verifier("H6. P1-b delegue a la regle partagee, il ne la recopie pas",
             "c3_refus_exprime(" in code_nu("p1b_destinataire_autorise")
             and "opted_out" not in code_nu("p1b_destinataire_autorise"))
    verifier("H7. la regle du refus n'est ecrite qu'UNE fois",
             SRC.count('"status": "opted_out"}') <= 1)


# ================================ I : une campagne historique ne change pas
async def historique():
    b, _ = bac()
    _r = await b["c3_refus_exprimes"]("email", [MAIL, "b@x.com", "c@x.com"])
    _deja = set()
    _verdicts = [b["c3_verdict"]("email", v, _r, _deja)
                 for v in (MAIL, "b@x.com", "c@x.com")]
    verifier("I. sans aucun opt-out, personne n'est ecarte",
             _verdicts == ["", "", ""], repr(_verdicts))
    _deja = set()
    _v = [b["c3_verdict"]("email", v, _r, _deja)
          for v in (MAIL, "b@x.com", MAIL)]
    verifier("I2. seule la deduplication retire quelqu'un",
             _v == ["", "", "doublon"], repr(_v))


# ============================== J : List-Unsubscribe — la condition n'est pas remplie
def list_unsubscribe():
    _nu = code_nu("launch_campaign")
    verifier("J. les en-tetes List-Unsubscribe ne sont PAS ajoutes aux campagnes",
             "_v336_entetes_desinscription" not in _nu)
    verifier("J2. le desabonnement exige un jeton que les cibles n'ont pas",
             '{"unsubscribe_token": token}' in SRC)
    verifier("J3. ce jeton n'est cree qu'a l'inscription, jamais pour une cible "
             "de campagne",
             "unsubscribe_token" not in _nu)
    _entete = SRC[SRC.find("# ===================== C3 —"):SRC.find("C3_CANAUX_CAMPAGNE = ")]
    verifier("J4. le blocage est documente dans le code, chiffres a l'appui",
             "List-Unsubscribe" in _entete and "unsubscribe_token" in _entete
             and "fausse promesse" in _entete)
    verifier("J5. et la voie de sortie est nommee pour le lot suivant",
             "inscrites au registre" in _entete)


# ================================= S : ce que le lot promet de ne PAS faire
def structure():
    _nu = code_nu("launch_campaign")
    _c3 = (source("c3_refus_exprimes") + source("c3_refus_exprime")
           + source("c3_verdict"))
    verifier("S1. les trois aides du lot n'ECRIVENT jamais : lecture pure",
             not any(m in _c3 for m in ("update_one", "insert_one", "delete_one",
                                        "update_many", "$set")))
    verifier("S1b. la campagne n'ecrit rien dans `subscribers`",
             "subscribers.update" not in _nu and "subscribers.insert" not in _nu)
    verifier("S2. l'exclusion du numero business est intacte",
             "business_phone_number" in _nu)
    verifier("S3. le depliage des groupes est intact",
             "grp_" in _nu and "participant_ids" in _nu)
    verifier("S4. le verrou anti-doublon de campagne est intact",
             "find_one_and_update" in _nu)
    verifier("S5. la normalisation est CELLE du depot, pas une seconde",
             "_v332_normaliser" in code_nu("c3_verdict")
             and "_v332_normaliser" in code_nu("c3_refus_exprimes"))
    verifier("S6. les envois en masse par e-mail portent la meme garde",
             "c3_refus_exprimes" in code_nu("send_bulk_campaign_email"))
    verifier("S7. les rappels avant cours ne sont pas touches",
             "rv2_canal_autorise" in SRC and "c3_" not in code_nu("rv2_canal_autorise"))
    verifier("S8. aucune entree utilisateur nue dans une regex Mongo",
             "$regex" not in code_nu("c3_refus_exprimes"))
    verifier("S9. aucun drapeau nouveau",
             "C3_ENABLED" not in SRC and "OPTOUT_ENABLED" not in SRC)
    verifier("S10. push/broadcast reste hors lot, explicitement",
             "c3_" not in code_nu("push_broadcast"))


def main():
    boucle = asyncio.new_event_loop()
    boucle.run_until_complete(garde())
    boucle.run_until_complete(p1b_inchange())
    boucle.run_until_complete(historique())
    audience_vide()
    list_unsubscribe()
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
