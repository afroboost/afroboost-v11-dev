"""
L0 — IDENTITÉ DE L'INVITANT (29/09/2026).

Règle de Bassi : sur la carte reçue, sur l'aperçu OG et autour des boutons de partage,
l'invité voit QUI l'invite.
  - invitation d'un MEMBRE -> photo du membre (celle choisie pour l'invitation, sinon
    celle de son profil), prénom du membre ;
  - aucune photo -> avatar Afroboost (jamais la photo du coach à la place d'un membre) ;
  - invitation directe du coach -> photo du coach (source « coach », réservée).
`inviter_display = {prenom, photo_url, source}` est FIGÉ côté serveur (création,
modification, chaîne) et exposé dans l'API publique SANS aucune donnée personnelle.
Les photos hébergées sur Cloudinary sont admises (hôte res.cloudinary.com).
Les anciens liens (pass sans `inviter_display`) gardent EXACTEMENT leur version de carte.

Lancer : python3 tests/test_parrainage_l0_identite.py
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_parrainage_v3 as V3  # noqa: E402  (pose l'environnement du banc)

H = V3.H
E, R = H.E, H.R
verifier = H.verifier

PHOTO_PROFIL = "https://res.cloudinary.com/dtm0r7hwq/image/upload/v1/profil-lea.jpg"
PHOTO_CHOISIE = "https://lh3.googleusercontent.com/a/photo-lea"


def _doc(base, tok):
    return V3.doc_par_tok(base, tok)


async def partie_regles_pures():
    # Cloudinary admis, http/javascript toujours refusés
    verifier("L0-1 Cloudinary https admis", E.valider_photo_url(PHOTO_PROFIL) == PHOTO_PROFIL)
    for mauvais in ("http://res.cloudinary.com/x.jpg", "javascript:alert(1)", "https://evil.example/x.jpg"):
        try:
            E.valider_photo_url(mauvais)
            ok = False
        except E.InvitationInvalide:
            ok = True
        verifier("L0-1b refusé : %s" % mauvais[:30], ok)

    # identite_invitant : photo choisie > photo de profil > avatar Afroboost ; jamais le coach pour un membre
    p = {"sponsor": {"name": "Léa Parrain", "email_norm": "lea@exemple.test"},
         "invitation": {"display_name": "Léa", "photo_url": PHOTO_CHOISIE}}
    i = E.identite_invitant(p, photo_profil=PHOTO_PROFIL)
    verifier("L0-2 photo choisie prioritaire", i == {"prenom": "Léa", "photo_url": PHOTO_CHOISIE, "source": "member"}, i)
    p2 = {"sponsor": {"name": "Léa Parrain", "email_norm": "parrain.l@exemple.test"}}
    i2 = E.identite_invitant(p2, photo_profil=PHOTO_PROFIL)
    verifier("L0-2b photo de profil sinon", i2["photo_url"] == PHOTO_PROFIL and i2["source"] == "member", i2)
    i3 = E.identite_invitant(p2, photo_profil=None)
    verifier("L0-2c aucune photo -> avatar Afroboost (photo None), toujours membre", i3["photo_url"] is None
             and i3["source"] == "member" and i3["prenom"] == "Léa", i3)
    i4 = E.identite_invitant({}, photo_profil=None)
    verifier("L0-2d personne -> source afroboost", i4 == {"prenom": "", "photo_url": None, "source": "afroboost"}, i4)
    i5 = E.identite_invitant(p2, photo_profil="javascript:alert(1)")
    verifier("L0-2e photo de profil invalide ignorée", i5["photo_url"] is None, i5)
    verifier("L0-2f jamais d'e-mail dans l'identité", "@" not in json.dumps(i2))

    # Version de carte : un ancien pass (sans inviter_display) garde EXACTEMENT sa version
    ancien = {"share_token": "t", "occurrence": "2026-10-01T18:30", "course_id": "c",
              "sponsor": {"name": "Léa"}, "invitation": {"display_name": "Léa", "photo_url": PHOTO_CHOISIE}}
    v0 = E.version_carte(ancien)
    avec_meme = dict(ancien, inviter_display={"prenom": "Léa", "photo_url": PHOTO_CHOISIE, "source": "member"})
    verifier("L0-3 identité identique à l'invitation -> version inchangée", E.version_carte(avec_meme) == v0)
    avec_profil = dict(ancien, invitation={"display_name": "Léa"},
                       inviter_display={"prenom": "Léa", "photo_url": PHOTO_PROFIL, "source": "member"})
    sans = dict(ancien, invitation={"display_name": "Léa"})
    verifier("L0-3b photo de profil utilisée -> NOUVELLE version (WhatsApp rafraîchit)",
             E.version_carte(avec_profil) != E.version_carte(sans))

    fige = {"invitation": {"display_name": "Léa", "photo_url": PHOTO_CHOISIE},
            "inviter_display": {"prenom": "Ancien", "photo_url": PHOTO_PROFIL, "source": "member"}}
    d = E.inviter_display_du_pass(fige)
    verifier("L0-3c le choix de l'invitation prime sur l'identité figée",
             d["photo_url"] == PHOTO_CHOISIE and d["prenom"] == "Léa", d)
    d = E.inviter_display_du_pass(dict(fige, invitation={}))
    verifier("L0-3d sans choix : l'identité figée complète (photo de profil)",
             d["photo_url"] == PHOTO_PROFIL and d["prenom"] == "Ancien", d)
    d = E.inviter_display_du_pass(dict(fige, invitation={}, inviter_display={"photo_url": "javascript:x", "source": "member"}))
    verifier("L0-3e photo figée invalide ignorée", d["photo_url"] is None, d)


async def partie_routes():
    base, occ = H.base_de_depart(chaine=True)
    base["users"].docs.append({"id": "u-lea", "email": H.PARRAIN_EMAIL, "photo_url": PHOTO_PROFIL})
    c, p0 = await H.creer_pass(base, occ)
    verifier("L0-4 création du pass", c == 201, (c, p0))
    d = _doc(base, p0["share_token"])
    idt = (d or {}).get("inviter_display") or {}
    verifier("L0-4b inviter_display figé à la création (photo de profil Cloudinary)",
             idt.get("photo_url") == PHOTO_PROFIL and idt.get("source") == "member" and idt.get("prenom"), idt)

    c, pubd = await V3.pub(p0["share_token"])
    verifier("L0-5 API publique : inviter_display exposé", c == 200 and (pubd.get("inviter_display") or {}).get("photo_url") == PHOTO_PROFIL, pubd.get("inviter_display"))
    verifier("L0-5b API publique : aucune donnée personnelle", not V3.fuite(pubd, base), V3.fuite(pubd, base))

    # modification de l'invitation : la photo choisie prend le dessus, identité re-figée
    c, r = await H.appel(R.referral_pass_invitation_put(p0["id"], H.req_parrain(base, {"photo_url": PHOTO_CHOISIE, "display_name": "Léa"})))
    d = _doc(base, p0["share_token"])
    verifier("L0-6 modification : identité re-figée sur la photo choisie", c == 200 and
             (d.get("inviter_display") or {}).get("photo_url") == PHOTO_CHOISIE, (c, d.get("inviter_display")))

    # chaîne V556 : l'enfant porte le prénom saisi, pas de photo (A pas encore inscrit), jamais le coach
    c, ch = await V3.chaine(p0["share_token"], {"display_name": "Bruno"})
    enfant = (ch or {}).get("child") or {}
    idc = enfant.get("inviter_display") or {}
    verifier("L0-7 chaîne : enfant = prénom saisi, avatar Afroboost, source membre",
             c in (200, 201) and idc.get("prenom") == "Bruno" and idc.get("photo_url") is None and idc.get("source") == "member",
             (c, idc))
    verifier("L0-7b chaîne : aucune donnée personnelle", not V3.fuite(ch, base), V3.fuite(ch, base))


def main():
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
    except Exception:  # noqa: BLE001
        pass
    boucle = asyncio.get_event_loop()
    for partie in (partie_regles_pures, partie_routes):
        try:
            boucle.run_until_complete(partie())
        except Exception as err:  # noqa: BLE001
            import traceback
            verifier("PARTIE %s sans exception" % partie.__name__, False,
                     "%s: %s\n%s" % (type(err).__name__, err, traceback.format_exc()[-1500:]))
    res = [r for r in H.RESULTATS if str(r[0]).startswith(("L0", "PARTIE"))]
    ok = sum(1 for _, c, _ in res if c)
    for nom, cond, detail in res:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom, ("" if cond or not detail else "\n         -> " + str(detail)[:600])))
    print("%d / %d verifications L0 au vert" % (ok, len(res)))
    return 0 if ok == len(res) else 1


if __name__ == "__main__":
    sys.exit(main())
