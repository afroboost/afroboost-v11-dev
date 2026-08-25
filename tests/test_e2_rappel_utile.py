# -*- coding: utf-8 -*-
"""E2 — LE RAPPEL DIT AUSSI OU VENIR, ET OU EST LE QR.

Ce test rejoue le VRAI `cron_reservation_reminders` extrait de `api/server.py`,
avec ses vraies aides, sur le harnais deja ecrit pour RV2 : meme faux MongoDB,
memes mouchards, meme absence totale de reseau. On ne recopie rien a la main —
ce qui est verifie ici est ce qui tournera en production.

CE QUE CE LOT NE TOUCHE PAS, ET QUE CE FICHIER SURVEILLE : la selection, le
fuseau, l'idempotence, le provider, la frequence, le cron, les drapeaux, et le
contenu du PUSH. Un rappel qui gagnerait une adresse en perdant son
anti-doublon serait une regression, pas une amelioration.

Aucun reseau. Aucun Push. Aucun e-mail. Aucune base. Aucune ecriture.

Lancement :  python3 tests/test_e2_rappel_utile.py
"""

import asyncio
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Le cron importe `api.routes.shared` pour reutiliser `n2_ou` : la racine du
# depot doit etre sur le chemin, sinon le test validerait un lieu absent en
# croyant tester le contraire.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import test_rv2_rappels_push_email as H   # noqa: E402  (harnais partage)

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


# --------------------------------------------------------------- jeux de test
JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
LIEU = "Bord du Lac, Auvernier, Neuchâtel"
MAPS_SUR = "https://maps.google.com/?q=Auvernier"
CODE = "AFR-2287CA"


def cours_avec_lieu(cid="c1", lieu=LIEU, maps=None, **extra):
    """Le cours de reference du harnais, augmente de son adresse reelle."""
    d = H.cours(cid=cid, **extra)
    if lieu is not None:
        d["locationName"] = lieu
    if maps is not None:
        d["mapsUrl"] = maps
    return d


def code_doc(code=CODE):
    return {"code": code}


async def passage(resas, cours_docs, codes=None, **kw):
    b, base = H.bac(resas, cours_docs=cours_docs, codes=codes, **kw)
    await b["cron_reservation_reminders"]()
    return b, base


def dernier_mail():
    return H.EMAILS[-1] if H.EMAILS else {}


# ============================================================ A -> F : contenu
async def contenu():
    # --- A. cours RECURRENT (aucune date propre, le jour vient de la resa) ---
    await passage([H.resa()], [cours_avec_lieu()], [code_doc()])
    m = dernier_mail()
    verifier("A. rappel envoye pour un cours recurrent", bool(m), repr(m)[:120])
    verifier("A2. le nom du cours y est", "Danse Afro" in (m.get("html") or ""))

    # --- B. DATE UNIQUE : meme moteur, le cours porte une date propre ---
    H.EMAILS[:] = []
    await passage([H.resa(rid="r2")],
                  [cours_avec_lieu(date="2026-08-26")], [code_doc()])
    verifier("B. rappel envoye pour un cours a date unique", bool(dernier_mail()))

    # --- C / D. date et heure, en heure suisse ---
    H.EMAILS[:] = []
    await passage([H.resa(course_time="18:30")], [cours_avec_lieu()], [code_doc()])
    m = dernier_mail()
    _h = m.get("html") or ""
    _t = m.get("text") or ""
    verifier("C. la date figure dans le rappel",
             any(j in _h for j in JOURS), _h[:200])
    verifier("D. l'heure du cours figure dans le rappel",
             "18:30" in _h and "18:30" in _t)

    # --- E. LE LIEU ---
    verifier("E. le lieu figure dans le HTML", LIEU in _h, _h[:200])
    verifier("E2. le lieu figure aussi dans la version texte", LIEU in _t)

    # --- F. lieu SANS itineraire : l'adresse reste, entiere ---
    verifier("F. sans mapsUrl, aucun lien d'itineraire n'est fabrique",
             "itin" not in _h.lower() and LIEU in _h)

    # --- pas de lieu du tout : on n'invente rien, et rien ne casse ---
    H.EMAILS[:] = []
    await passage([H.resa()], [cours_avec_lieu(lieu=None)], [code_doc()])
    m = dernier_mail()
    verifier("F2. sans adresse connue, le rappel part quand meme", bool(m))
    verifier("F3. et ne parle pas d'un lieu vide",
             "C&rsquo;est au <strong" not in (m.get("html") or ""))


# ====================================================== G -> H : surete des liens
async def surete_liens():
    # --- G. URL https SURE -> cliquable ---
    H.EMAILS[:] = []
    await passage([H.resa()], [cours_avec_lieu(maps=MAPS_SUR)], [code_doc()])
    _h = dernier_mail().get("html") or ""
    verifier("G. une URL https legitime devient un lien",
             ('href="%s"' % MAPS_SUR) in _h, _h[:240])
    verifier("G2. et le lieu reste affiche a cote", LIEU in _h)

    # --- H. schemas dangereux -> JAMAIS un lien, et le lieu SURVIT ---
    for hostile in ("javascript:alert(document.cookie)",
                    "data:text/html;base64,PHNjcmlwdD4=",
                    "vbscript:msgbox(1)",
                    "JaVaScRiPt:alert(1)",
                    "  javascript:alert(1)",
                    "//evil.example.com/x"):
        H.EMAILS[:] = []
        await passage([H.resa()], [cours_avec_lieu(maps=hostile)], [code_doc()])
        _h = dernier_mail().get("html") or ""
        _t = dernier_mail().get("text") or ""
        verifier("H. « %s » ne devient jamais un href" % hostile[:26],
                 ('href="%s"' % hostile) not in _h
                 and "javascript:" not in _h.lower()
                 and "vbscript:" not in _h.lower()
                 and "data:text/html" not in _h.lower(), _h[:200])
        verifier("H2. et l'adresse reste visible malgre le refus (%s)" % hostile[:16],
                 LIEU in _h and LIEU in _t)

    # --- injection HTML dans le NOM du lieu ---
    H.EMAILS[:] = []
    await passage([H.resa()],
                  [cours_avec_lieu(lieu='Lac <script>alert(1)</script> & Co')],
                  [code_doc()])
    _h = dernier_mail().get("html") or ""
    verifier("H3. le nom du lieu est echappe, jamais injecte",
             "<script>" not in _h and "&lt;script&gt;" in _h, _h[:240])


# ================================================ I -> J : lien espace / QR
async def lien_espace():
    b, _ = H.bac([], cours_docs=[])
    lien = b["rv2_lien_espace"]

    # --- I. lien correct, construit sur la route EXISTANTE ---
    H.EMAILS[:] = []
    await passage([H.resa(promoCode=CODE)], [cours_avec_lieu()], [code_doc()])
    m = dernier_mail()
    _h = m.get("html") or ""
    _t = m.get("text") or ""
    _attendu = "https://afroboost.com/espace/%s" % CODE
    verifier("I. le rappel porte le lien vers l'espace participant",
             ('href="%s"' % _attendu) in _h, _h[-400:])
    verifier("I2. le lien figure aussi en texte", _attendu in _t)
    verifier("I3. le bouton parle du QR",
             "QR" in _h)

    # --- I4. `discountCode` sert de repli, comme partout ailleurs ---
    H.EMAILS[:] = []
    await passage([H.resa(discountCode=CODE)], [cours_avec_lieu()], [code_doc()])
    verifier("I4. `discountCode` est lu quand `promoCode` manque",
             _attendu in (dernier_mail().get("html") or ""))

    # --- I5. la casse de la base n'empeche pas de retrouver le code ---
    H.EMAILS[:] = []
    await passage([H.resa(promoCode="AURELIEBOOST-26")], [cours_avec_lieu()],
                  [code_doc("AurelieBoost-26")])
    verifier("I5. un code retrouve malgre une casse differente en base",
             "https://afroboost.com/espace/AURELIEBOOST-26"
             in (dernier_mail().get("html") or ""))

    # --- J. AUCUN code invente ---
    H.EMAILS[:] = []
    await passage([H.resa()], [cours_avec_lieu()], [code_doc()])
    _h = dernier_mail().get("html") or ""
    verifier("J. sans code sur la reservation, aucun lien espace n'est fabrique",
             "/espace/" not in _h, _h[-300:])

    # --- J2. code PRESENT mais INCONNU en base -> aucun lien mort ---
    H.EMAILS[:] = []
    await passage([H.resa(promoCode="CLUBPMI-AFRO")], [cours_avec_lieu()],
                  [code_doc(CODE)])
    verifier("J2. un code orphelin ne produit jamais un lien mort",
             "/espace/" not in (dernier_mail().get("html") or ""))

    # --- J3. l'aide elle-meme n'accepte que de l'ASCII de code ---
    verifier("J3. un code vide ne donne aucun lien", lien("") == "" and lien(None) == "")
    for mauvais in ("../admin", "a/b", "AFR 123", "AFR?x=1", "AFR#z", "aé9xyz",
                    "AFR:1", "ab", "-AFR12", "A" * 41):
        verifier("J3. « %s » est refuse par rv2_lien_espace" % mauvais[:18],
                 lien(mauvais) == "", repr(lien(mauvais)))
    verifier("J4. un code legitime passe, normalise en majuscules",
             lien("afr-2287ca") == "https://afroboost.com/espace/AFR-2287CA")


# ============================================ K : l'annulation n'est pas promise
async def annulation():
    H.EMAILS[:] = []
    await passage([H.resa()], [cours_avec_lieu(maps=MAPS_SUR)], [code_doc()])
    m = dernier_mail()
    _tout = ((m.get("html") or "") + (m.get("text") or "") + (m.get("subject") or "")).lower()
    for mot in ("annul", "rembours", "storn", "cancel"):
        verifier("K. le rappel ne promet rien sur « %s »" % mot,
                 mot not in _tout, _tout[:200])
    # et le code EXECUTE n'en parle pas davantage
    verifier("K2. aucune mention d'annulation dans le contenu execute",
             not any(m in H.code_nu("rv2_contenu_rappel").lower()
                     for m in ("annul", "cancel", "2 h", "2h")))


# =================================== L -> N : la mecanique reste celle d'avant
async def mecanique():
    # --- L. IDEMPOTENCE : deux passages, un seul e-mail ---
    H.EMAILS[:] = []
    r = H.resa(promoCode=CODE)
    b, base = H.bac([r], cours_docs=[cours_avec_lieu()], codes=[code_doc()])
    await b["cron_reservation_reminders"]()
    n1 = len(H.EMAILS)
    await b["cron_reservation_reminders"]()
    verifier("L. deux passages du cron n'envoient qu'un seul e-mail",
             n1 == 1 and len(H.EMAILS) == 1, "%d puis %d" % (n1, len(H.EMAILS)))
    verifier("L2. le marqueur d'idempotence est bien pose",
             bool(H.marqueur(base.reservations.docs[0])))

    # --- M. cours ARCHIVE : exclu, exactement comme avant ---
    H.EMAILS[:] = []
    await passage([H.resa()], [cours_avec_lieu(archive=True)], [code_doc()])
    verifier("M. un cours archive n'envoie aucun rappel", not H.EMAILS)

    # --- N. cours NON ACTIVE (champ absent) : muet, comme le parc historique ---
    H.EMAILS[:] = []
    await passage([H.resa()], [cours_avec_lieu(actif=None)], [code_doc()])
    verifier("N. un cours sans `reminders_enabled` reste muet", not H.EMAILS)
    H.EMAILS[:] = []
    await passage([H.resa()], [cours_avec_lieu(actif=False)], [code_doc()])
    verifier("N2. un cours explicitement desactive reste muet", not H.EMAILS)

    # --- le PUSH est inchange : ni lieu, ni lien, ni QR ---
    H.PUSHS[:] = []
    await passage([H.resa(promoCode=CODE)], [cours_avec_lieu(maps=MAPS_SUR)],
                  [code_doc()])
    p = H.PUSHS[-1] if H.PUSHS else {}
    verifier("N3. le push part toujours", bool(p))
    verifier("N4. le push reste mot pour mot celui d'avant E2",
             p.get("titre") == "📅 Ton cours commence dans 1h"
             and p.get("corps") == "Danse Afro à 18:30 — prépare-toi !",
             repr(p)[:200])


# ============================================================ S : structure
def structure():
    nu = H.code_nu("rv2_contenu_rappel")
    verifier("S1. le contenu n'a toujours AUCUN acces a `datetime`",
             "datetime" not in nu)
    verifier("S2. il ne connait toujours que l'heure qu'on lui passe",
             "courseTime" not in nu)
    verifier("S3. le gabarit HTML existant est reutilise, pas reecrit",
             "_email_wrapper" in nu)
    verifier("S4. tout ce que E2 concatene est echappe",
             nu.count("_e2_html(") >= 3, str(nu.count("_e2_html(")))

    nu_cron = H.code_nu("cron_reservation_reminders")
    verifier("S5. le lieu reutilise `n2_ou`, sans seconde implementation",
             "n2_ou" in nu_cron and "locationName" not in nu_cron.replace(
                 "'locationName': 1", "").replace('"locationName": 1', ""))
    verifier("S6. le code d'acces est LU, jamais fabrique",
             "promoCode" in nu_cron and "uuid" not in nu_cron)
    verifier("S7. la verification des codes est UNE requete groupee",
             nu_cron.count("discount_codes") == 1
             and "$or" in nu_cron and "re.escape" in nu_cron)
    verifier("S8. chaque regex MongoDB est construite avec re.escape",
             nu_cron.count("$regex") == nu_cron.count("re.escape") >= 1,
             "%d regex / %d escape" % (nu_cron.count("$regex"), nu_cron.count("re.escape")))
    verifier("S9. le cron n'ecrit rien de neuf en base",
             nu_cron.count("insert_one") == 0 and nu_cron.count("delete_one") == 0)

    nu_lien = H.code_nu("rv2_lien_espace")
    verifier("S10. le lien espace est une liste BLANCHE, pas une liste noire",
             "RV2_ESPACE_CARACTERES" in nu_lien
             and not any(m in nu_lien for m in ("javascript", "vbscript", "data:")))
    verifier("S11. il reutilise l'origine publique existante",
             "_v184_public_origin" in nu_lien)
    verifier("S12. il n'utilise PAS isalnum (vrai pour l'unicode)",
             "isalnum" not in nu_lien)

    # --- O. le perimetre du lot : un seul fichier de production ---
    verifier("O1. le drapeau AUTO-PRESENCE n'est pas touche",
             "AUTO_PRESENCE_TRIAL_ENABLED: bool = False" in SRC)
    verifier("O2. le drapeau P1-d n'est pas touche",
             "P1_TRIAL_J3_ENVOI_REEL: bool = False" in SRC)
    verifier("O3. la regle d'annulation 2 h est intacte",
             "T1_DELAI_ANNULATION_H = 2" in SRC)
    verifier("O4. la fenetre et l'horizon du moteur sont inchanges",
             "N1B2_DEMI_FENETRE_MIN = 30" in SRC
             and "N1B2_HORIZON_MIN = 2880 + N1B2_DEMI_FENETRE_MIN" in SRC)
    verifier("O5. les delais proposes sont inchanges",
             "N1B2_DELAIS_AUTORISES = (60, 180, 1440, 2880)" in SRC)


def main():
    boucle = asyncio.new_event_loop()
    try:
        boucle.run_until_complete(contenu())
        boucle.run_until_complete(surete_liens())
        boucle.run_until_complete(lien_espace())
        boucle.run_until_complete(annulation())
        boucle.run_until_complete(mecanique())
    finally:
        boucle.close()
    structure()
    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 78)
    for nom, r, detail in RESULTATS:
        print(("  PASS  " if r else "  FAIL  ") + nom + (("   -> " + detail) if not r else ""))
    print("=" * 78)
    print("E-mails REELLEMENT envoyes : 0 — `resend` n'est jamais importe")
    print("Push REELLEMENT envoyes    : 0 — `pywebpush` n'est jamais importe")
    print("Ecritures en production    : 0 — aucune base, aucun reseau")
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())
