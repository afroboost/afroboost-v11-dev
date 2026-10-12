#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V610k — le mot AUDIO de l'invitation « Essai gratuit » arrive au parcours de l'invité.

`GET /api/referral/pass/{jeton}` rend `audio_url` = l'audio RÉELLEMENT configuré sur
l'invitation d'origine (P0 et descendants, `origin.campaign_id`) ; rien sinon (jamais
inventé) ; un Pass Duo n'en a pas. Banc sur les vraies routes, MongoDB en mémoire.

Lancement : python3 tests/test_v610k_audio_essai.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_parrainage_campagne_chaine as CC  # noqa: E402  (pose l'environnement du banc)

H, R = CC.H, CC.R
verifier, appel = H.verifier, H.appel


async def pass_public(jeton):
    return await appel(R.referral_pass_public(jeton))


async def principal():
    # Invitation Essai gratuit AVEC un mot audio
    base, occ = CC.depart(audio_url="/api/files/a1/mot.mp3")
    c, r = await CC.entree()
    verifier("A-1 entrée de campagne -> 201", c == 201, (c, r))
    s, d = await pass_public(r["share_token"])
    verifier("A-2 le pass public porte l'audio de l'invitation", s == 200 and d.get("audio_url") == "/api/files/a1/mot.mp3", (s, d))
    verifier("A-3 type « Essai gratuit »", d.get("invitation_type") == "trial")

    # Invitation Essai gratuit SANS audio : rien d'inventé
    base, occ = CC.depart()
    c, r = await CC.entree()
    s, d = await pass_public(r["share_token"])
    verifier("A-4 sans audio configuré -> audio_url vide", s == 200 and d.get("audio_url") is None, d.get("audio_url"))

    # Une adresse non sûre n'est jamais rendue
    base, occ = CC.depart(audio_url="javascript:alert(1)")
    c, r = await CC.entree()
    s, d = await pass_public(r["share_token"])
    verifier("A-5 adresse non sûre -> jamais rendue", d.get("audio_url") is None, d.get("audio_url"))


if __name__ == "__main__":
    asyncio.run(principal())
    _res = getattr(H, "RESULTATS", None) or getattr(H, "RES", None)
    if _res is not None:
        _ok = sum(1 for x in _res if (x[0] if isinstance(x, tuple) else x))
        print("\n%d / %d vérifications V610k audio" % (_ok, len(_res)))
        sys.exit(0 if _ok == len(_res) else 1)
