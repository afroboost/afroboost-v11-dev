#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V618j — INVITATION « ESSAI GRATUIT » : CONTINUER SUR UN AUTRE APPAREIL AVANT CONFIRMATION.

Cause mesurée (Playwright, 13/10) : POST /chain ne rendait la clé d'édition qu'à l'appareil qui
CRÉAIT l'invitation de l'ami ; un second appareil (PC -> mobile, lien rouvert depuis WhatsApp)
recevait l'invitation SANS clé -> partage et inscription refusés (403 invitation_autre_appareil)
-> écran « termine l'inscription sur l'autre appareil ».

Banc permanent, vraies routes, base en mémoire, données synthétiques.
Lancement : python3 tests/test_v618j_cross_device.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_parrainage_essai_moi_dabord as M  # noqa: E402  (pose le banc V3 + campagnes)

V3, H = M.V3, M.H
R, E = H.R, H.E
appel, req, raison = H.appel, V3.req, V3.raison
RESULTATS = []


def verifier(nom, ok, detail=""):
    RESULTATS.append((nom, bool(ok), detail))


async def creer(tok, cle=None):
    return await appel(R.referral_chaine_creer(tok, req({}, {"X-Chain-Key": cle} if cle else {})))


async def partager(tok, cle):
    return await appel(R.referral_chaine_partager(tok, req({"channel": "whatsapp"}, {"X-Chain-Key": cle} if cle else {})))


async def rejoindre(tok, cle, email="essai.j@exemple.test", tel="+41791110000", nom="Jade"):
    return await appel(R.referral_join(tok, req(H.corps_ami(email, tel, nom), {"X-Chain-Key": cle} if cle else {})))


async def principal():
    base, _ = M.depart()
    _, r = await M.entree(base)
    t0 = r["share_token"]

    c, a = await creer(t0)
    cle_a = a.get("edit_key")
    verifier("1 appareil A crée l'invitation de l'ami : 201 + clé A", c == 201 and cle_a, (c, a))
    c, b = await creer(t0)
    cle_b = b.get("edit_key")
    verifier("2 appareil B, MÊME lien, AVANT confirmation : 200 + SA clé (plus d'écran « autre appareil »)",
             c == 200 and cle_b and cle_b != cle_a and b["child"]["share_token"] == a["child"]["share_token"], (c, b))
    verifier("2b une seule invitation d'ami (aucun doublon créé par le second appareil)",
             len([d for d in base["referral_passes"].docs if (d.get("chain") or {}).get("parent_pass_id")]) == 1)
    c, _ = await partager(t0, None)
    verifier("3 sans clé : le partage reste refusé (le lien seul ne suffit pas)", c == 403)
    c, _ = await partager(t0, "fausse-cle")
    verifier("3b clé inventée : refusée", c == 403)
    c, _ = await partager(t0, cle_b)
    verifier("4 appareil B partage avec SA clé : accepté", c == 200)
    c, j = await rejoindre(t0, cle_b)
    verifier("5 appareil B confirme sa place : accepté", c in (200, 201), (c, j))
    c, x = await creer(t0)
    verifier("6 APRÈS confirmation : un autre appareil ne reçoit PLUS de clé (relecture seule)",
             c == 200 and not x.get("edit_key"), (c, x))
    c, j2 = await rejoindre(t0, cle_a, email="autre@exemple.test", tel="+41792220000", nom="Autre")
    verifier("7 un second appareil ne prend JAMAIS une seconde place sur le même lien",
             c in (403, 409, 410) or (isinstance(j2, dict) and j2.get("status") in ("unlocked", "used", "friend_registered")
                                     and len(V3.resas_de(base, "autre@exemple.test")) == 0), (c, j2))
    verifier("7b une seule réservation d'essai pour ce lien", len(V3.resas_de(base, "essai.j@exemple.test")) == 1
             and len(V3.resas_de(base, "autre@exemple.test")) == 0)
    c, j3 = await rejoindre(t0, cle_b)
    verifier("8 double clic / retour : la confirmation est idempotente (aucune seconde réservation)",
             len(V3.resas_de(base, "essai.j@exemple.test")) == 1, (c, j3))

    # Plafond : au-delà de CLES_APPAREIL_MAX appareils, plus de nouvelle clé (écran de protection).
    _, r2 = await M.entree(base)
    t1 = r2["share_token"]
    c, a = await creer(t1)
    cles = [a.get("edit_key")]
    for _ in range(R.CLES_APPAREIL_MAX + 2):
        c, x = await creer(t1)
        cles.append(x.get("edit_key"))
    emises = [k for k in cles[1:] if k]
    verifier("9 plafond : %d clés supplémentaires au plus, puis relecture sans clé" % R.CLES_APPAREIL_MAX,
             len(emises) == R.CLES_APPAREIL_MAX and cles[-1] is None, len(emises))
    c, _ = await partager(t1, cles[0])
    verifier("10 la clé du PREMIER appareil reste valable (aucun appareil n'en évince un autre)", c == 200)
    enf = await R._enfant_de(V3.doc_par_tok(base, t1))
    verifier("11 aucune clé stockée en clair (empreintes seulement)",
             all(k not in str(enf.get("chain")) for k in [x for x in cles if x]))
    c, pubd = await appel(R.referral_pass_public(t1))
    verifier("12 la page publique ne révèle aucune empreinte de clé", "edit_key" not in str(pubd))


def main():
    asyncio.run(principal())
    _ok = 0
    for nom, ok, detail in RESULTATS:
        print(("  OK     " if ok else "  ECHEC  ") + nom)
        if not ok:
            print("         -> %s" % str(detail)[:700])
        _ok += ok
    print("%d / %d verifications V618j au vert" % (_ok, len(RESULTATS)))
    sys.exit(0 if _ok == len(RESULTATS) else 1)


if __name__ == "__main__":
    main()
