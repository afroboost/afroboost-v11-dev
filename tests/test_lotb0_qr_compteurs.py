# -*- coding: utf-8 -*-
"""LOT B0 — UN SCAN QR NE DESYNCHRONISE PLUS LES DEUX COMPTEURS.

LE DEFAUT, PROUVE PAR LA PRODUCTION AVANT D'ETRE CORRIGE. Le chemin « CAS B »
du scan (abonne sans reservation, presence constatee a la porte) debitait
`subscriptions.used_sessions` et ne touchait JAMAIS `discount_codes.used`.
Trois codes le montrent a la seconde pres — `AFR-0C60A3`, `AFR-B7E009`,
`AFR-E77BD4` : l'abonnement passe a `used: 1` a l'instant exact du
`validatedAt` d'une reservation `source: qr_scan_coach`, le code reste a
`used: 0`. Depuis le LOT A, la page « Code promo » fait foi : une presence
qu'elle ignore est une seance RENDUE — deux fois un cours d'essai gratuit.

CE BANC NE CORRIGE AUCUNE DONNEE ET N'EN LIT AUCUNE. Il prouve qu'aucune
NOUVELLE divergence ne peut naitre de ce chemin, et que tout ce qui marchait
avant marche encore : idempotence, essai gratuit, presence deja validee, refus
sur forfait inutilisable, et le funnel de presence.

AUCUNE BASE REELLE, AUCUN RESEAU, AUCUNE DONNEE PERSONNELLE.
    python3 tests/test_lotb0_qr_compteurs.py
"""
import asyncio, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tests._banc_qr as B
from tests._banc_qr import (_Base, _HTTPException, PRESENCES, construire,
                            faux_shared, faux_api_server, forfait, resa,
                            scanner, aujourdhui)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def fiche(code="AFR-ESSAI1", used=0, **kw):
    """Une fiche `discount_codes`, telle qu'elle existe en production."""
    d = {"id": "dc-" + code, "code": code, "maxUses": 10, "used": used,
         "active": True, "expiresAt": None}
    d.update(kw)
    return d


def monde(sub=None, fiches=None, resas=None):
    db = _Base()
    if fiches is not None:
        db.discount_codes.docs.extend(fiches)
    if resas:
        db.reservations.docs.extend(resas)
    _sub = sub if sub is not None else forfait(remaining_sessions=5,
                                               used_sessions=2, total_sessions=10)
    db.subscriptions.docs.append(_sub)
    return db, _sub


async def principal():
    # ══ A. UN SCAN QUI CONSOMME : LES DEUX COMPTEURS BOUGENT ENSEMBLE ══════
    PRESENCES.clear()
    faux_api_server()
    db, sub = monde(fiches=[fiche(used=2)])
    faux_shared(abonnement=sub)
    ns = construire(db)
    rep = await scanner(ns, "AFR-ESSAI1", courseId="cours-1")
    dc = db.discount_codes.docs[0]
    verifier("A. le scan cree la reservation et debite",
             rep.get("success") and sub["used_sessions"] == 3, rep.get("message", ""))
    verifier("A. discount_codes.used suit : 2 -> 3", dc["used"] == 3, dc["used"])
    verifier("A. INVARIANT used == used_sessions",
             dc["used"] == sub["used_sessions"], (dc["used"], sub["used_sessions"]))
    verifier("A. le restant de l'abonnement decroit de 1",
             sub["remaining_sessions"] == 4, sub["remaining_sessions"])
    # `$inc` et non `$set` : deux portiers simultanes ne doivent pas s'ecraser.
    _maj = [m for (_t, _f, m) in db.discount_codes.ecritures if m]
    verifier("A. l'ecriture du code est un $inc atomique, jamais un $set calcule",
             any("$inc" in (m or {}) for m in _maj) and
             not any("$set" in (m or {}) for m in _maj), _maj)

    # ══ B. SCAN REJOUE : AUCUNE DEUXIEME CONSOMMATION ══════════════════════
    rep2 = await scanner(ns, "AFR-ESSAI1", courseId="cours-1")
    verifier("B. le rejeu ne debite pas une seconde fois",
             sub["used_sessions"] == 3 and dc["used"] == 3,
             (sub["used_sessions"], dc["used"]))
    verifier("B. l'invariant tient apres rejeu",
             dc["used"] == sub["used_sessions"], (dc["used"], sub["used_sessions"]))
    verifier("B. le rejeu repond quand meme au portier",
             rep2.get("success") is True, rep2.get("message", ""))
    verifier("B. une seule reservation creee au total",
             len([r for r in db.reservations.docs if r.get("source") == "qr_scan_coach"]) == 1,
             len(db.reservations.docs))

    # ══ C. PRESENCE DEJA VALIDEE : AUCUN COMPTEUR NE BOUGE ═════════════════
    PRESENCES.clear()
    _deja = resa(code="AF-DEJA", validated=True, validatedAt="2026-08-27T16:00:00")
    db, sub = monde(sub=forfait(remaining_sessions=5, used_sessions=2, total_sessions=10),
                    fiches=[fiche(used=2)], resas=[_deja])
    faux_shared(abonnement=sub)
    ns = construire(db)
    rep = await scanner(ns, "AFR-ESSAI1", courseId="cours-1")
    dc = db.discount_codes.docs[0]
    verifier("C. presence deja validee : aucun debit d'abonnement",
             sub["used_sessions"] == 2 and sub["remaining_sessions"] == 5,
             (sub["used_sessions"], sub["remaining_sessions"]))
    verifier("C. ... et AUCUNE ecriture sur discount_codes",
             db.discount_codes.ecritures == [] and dc["used"] == 2,
             db.discount_codes.ecritures)
    verifier("C. le portier obtient bien « deja valide »",
             "jà valid" in str(rep.get("message", "")), rep.get("message", ""))

    # ══ D. DERNIERE SEANCE : PASSE A 0 EXACTEMENT UNE FOIS ═════════════════
    PRESENCES.clear()
    db, sub = monde(sub=forfait(remaining_sessions=1, used_sessions=9, total_sessions=10),
                    fiches=[fiche(used=9)])
    faux_shared(abonnement=sub)
    ns = construire(db)
    await scanner(ns, "AFR-ESSAI1", courseId="cours-1")
    dc = db.discount_codes.docs[0]
    verifier("D. la derniere seance tombe a 0",
             sub["remaining_sessions"] == 0 and sub["used_sessions"] == 10,
             (sub["remaining_sessions"], sub["used_sessions"]))
    verifier("D. le code atteint 10 exactement", dc["used"] == 10, dc["used"])
    verifier("D. l'abonnement se cloture", sub.get("status") == "completed", sub.get("status"))
    await scanner(ns, "AFR-ESSAI1", courseId="cours-1")
    verifier("D. un second scan ne descend pas sous 0",
             sub["remaining_sessions"] == 0 and dc["used"] == 10,
             (sub["remaining_sessions"], dc["used"]))

    # ══ E. FORFAIT INUTILISABLE : AUCUNE CONSOMMATION ILLEGITIME ═══════════
    PRESENCES.clear()
    db, sub = monde(sub=forfait(remaining_sessions=0, used_sessions=10, total_sessions=10),
                    fiches=[fiche(used=10, active=False)])
    faux_shared(abonnement=sub, forfait_ok=(False, "Abonnement expiré"))
    ns = construire(db)
    _refus = None
    try:
        await scanner(ns, "AFR-ESSAI1", courseId="cours-1")
    except _HTTPException as e:
        _refus = e
    verifier("E. le scan est refuse (garde V393 inchangee)",
             _refus is not None and _refus.status_code == 400,
             getattr(_refus, "detail", "aucun refus"))
    verifier("E. aucun compteur touche : ni l'abonnement, ni le code",
             db.subscriptions.ecritures == [] and db.discount_codes.ecritures == [],
             (db.subscriptions.ecritures, db.discount_codes.ecritures))
    verifier("E. un code inactif n'est jamais ressuscite",
             db.discount_codes.docs[0]["used"] == 10 and
             db.discount_codes.docs[0]["active"] is False, db.discount_codes.docs[0])

    # ══ F. DEUX FICHES POUR UN MEME CODE : AUCUN CHOIX ARBITRAIRE ══════════
    PRESENCES.clear()
    db, sub = monde(sub=forfait(remaining_sessions=5, used_sessions=2, total_sessions=10),
                    fiches=[fiche(used=2), dict(fiche(used=7), id="dc-bis", maxUses=45)])
    faux_shared(abonnement=sub)
    ns = construire(db)
    await scanner(ns, "AFR-ESSAI1", courseId="cours-1")
    verifier("F. la presence est constatee malgre l'ambiguite",
             sub["used_sessions"] == 3, sub["used_sessions"])
    verifier("F. AUCUNE des deux fiches n'est ecrite",
             db.discount_codes.ecritures == [] and
             [d["used"] for d in db.discount_codes.docs] == [2, 7],
             [d["used"] for d in db.discount_codes.docs])
    verifier("F. l'abstention est journalisee pour le LOT C",
             any("LOT B0" in str(x) and "fiches concurrentes" in str(x)
                 for x in ns["logger"].lignes), ns["logger"].lignes[-3:])

    # ══ G. ESSAI GRATUIT : COMPORTEMENT EXISTANT NON REGRESSE ══════════════
    # Un essai reserve a l'avance est deja debite : le scan CONSTATE, il ne
    # reconsomme rien. C'est la regle A0-1, et le LOT B0 ne doit pas la frôler.
    PRESENCES.clear()
    _essai = resa(code="AFR-ESSAI1")
    db, sub = monde(sub=forfait(remaining_sessions=0, used_sessions=1, total_sessions=1),
                    fiches=[fiche(used=1, maxUses=1)], resas=[_essai])
    faux_shared(abonnement=sub)
    ns = construire(db)
    rep = await scanner(ns, "AFR-ESSAI1", courseId="cours-1")
    verifier("G. essai deja reserve : presence validee sans refus",
             rep.get("success") and db.reservations.docs[0]["validated"] is True,
             rep.get("message", ""))
    verifier("G. aucun credit reconsomme sur l'abonnement",
             sub["used_sessions"] == 1 and db.subscriptions.ecritures == [],
             sub["used_sessions"])
    verifier("G. aucune ecriture sur le code non plus",
             db.discount_codes.ecritures == [] and db.discount_codes.docs[0]["used"] == 1,
             db.discount_codes.ecritures)

    # ══ H. HISTORIQUE ET PRESENCE TOUJOURS ENREGISTRES ═════════════════════
    PRESENCES.clear()
    db, sub = monde(fiches=[fiche(used=0)])
    faux_shared(abonnement=sub)
    ns = construire(db)
    await scanner(ns, "AFR-ESSAI1", courseId="cours-1")
    _creee = [r for r in db.reservations.docs if r.get("source") == "qr_scan_coach"]
    verifier("H. la reservation de presence est bien creee", len(_creee) == 1, len(_creee))
    verifier("H. elle est validee et nommee `walkin`",
             _creee and _creee[0].get("validated") is True
             and _creee[0].get("validation_source") == "walkin", _creee[:1])
    verifier("H. le funnel de presence a bien recu l'evenement",
             len(PRESENCES) == 1, PRESENCES)

    # ══ I. LE LOT NE REECRIT AUCUNE DIVERGENCE HISTORIQUE ══════════════════
    # Un scan sur UN code ne doit toucher que CE code. Les divergences deja en
    # base ne sont ni lues, ni reparees, ni aggravees par ce lot.
    PRESENCES.clear()
    _voisin = fiche(code="AUTRECODE", used=8, id="dc-voisin")
    db, sub = monde(fiches=[fiche(used=0), _voisin])
    faux_shared(abonnement=sub)
    ns = construire(db)
    await scanner(ns, "AFR-ESSAI1", courseId="cours-1")
    verifier("I. le code voisin n'est pas touche", _voisin["used"] == 8, _voisin["used"])
    _ecrits = {f.get("id") for (_t, f, _m) in db.discount_codes.ecritures}
    verifier("I. une seule fiche ecrite, ciblee par son `id`",
             _ecrits == {"dc-AFR-ESSAI1"}, _ecrits)

    # ══ J. AUCUNE FICHE : RIEN A REFLETER, ET AUCUNE ERREUR ════════════════
    PRESENCES.clear()
    db, sub = monde(fiches=[])
    faux_shared(abonnement=sub)
    ns = construire(db)
    rep = await scanner(ns, "AFR-ESSAI1", courseId="cours-1")
    verifier("J. abonnement sans fiche code : le scan aboutit quand meme",
             rep.get("success") and sub["used_sessions"] == 3, rep.get("message", ""))
    verifier("J. et aucune fiche n'est inventee",
             db.discount_codes.docs == [], db.discount_codes.docs)


asyncio.get_event_loop().run_until_complete(principal())

echecs = [x for x in RESULTATS if not x[1]]
print("\nLOT B0 — SCAN QR ET COHERENCE DES COMPTEURS (%d verifications)\n" % len(RESULTATS))
for nom, ok, detail in RESULTATS:
    print("  %s %-62s %s" % ("OK  " if ok else "ECHEC", nom, "" if ok else detail))
print("\n%d/%d au vert" % (len(RESULTATS) - len(echecs), len(RESULTATS)))
sys.exit(1 if echecs else 0)
