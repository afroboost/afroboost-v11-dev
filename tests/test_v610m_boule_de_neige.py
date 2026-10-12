#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V610m — la boule de neige d'un ÉVÉNEMENT PAYANT jusqu'au 4e maillon, et l'espace
qui rend à chaque participant SA réservation + SON lien.

  H. Bassi (invitation du coach) -> Sophie -> Nadine -> Julie : chacun SON lien,
     inviteur direct, racine, génération 1 / 2 / 3 ; jamais le lien de l'invitant ;
  N. webhook rejoué (même session Stripe) -> le MÊME relais, rien de neuf ;
  12. POST /api/invitation/relais/mes-evenements : 403 sans session d'espace ; avec la
     session de Nadine -> SON événement et SON lien, rien de Sophie ni de Julie ;
     un événement passé n'apparaît plus.

Banc sur les VRAIES routes (`invitation_relais.py`) et le MongoDB en mémoire.
Lancement : python3 tests/test_v610m_boule_de_neige.py
"""
import asyncio
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_v607_invitation_evenement as V7  # noqa: E402  (pose l'environnement du banc)

T, H, RL, SI, SV = V7.T, V7.H, V7.RL, V7.SI, V7.SV
verifier, appel = H.verifier, H.appel


class _RqEspace:
    """Requête de l'espace : corps JSON + en-tête x-espace-token (la session est simulée)."""
    def __init__(self, corps, jeton=""):
        self._c = corps
        self.headers = V7._Ent({"x-espace-token": jeton, "user-agent": ""})
        self.client = type("C", (), {"host": "10.9.9.9"})()

    async def json(self):
        return self._c


async def principal():
    base, occ = T.depart()
    base._c["invitation_relais"] = H._Coll("invitation_relais", uniques=[(("jeton",), None), (("preuve_cle",), None)])
    base._c["invitation_events"] = H._Coll("invitation_events", uniques=[(("cle",), None)])
    for m in (SI, RL, SV):
        m.init_db(base)
    c, ev = await T.creer(T.COACH_A, {"type": "event_paid", "status": "active", "offer_id": T.OFFRE_A_PAYANTE,
                                      "occurrence": occ, "title": "AFROBOOST SILENT"})
    verifier("M-0 événement payant actif", c == 201, (c, ev))
    racine = ev["share_token"]

    # ── H. Bassi -> Sophie -> Nadine -> Julie ───────────────────────────────
    sophie = await RL.relais_depuis_paiement_stripe(base, V7.session("cs_test_SOPHIE1", racine, "sophie@test.example", "Sophie Test"))
    nadine = await RL.relais_depuis_paiement_stripe(base, V7.session("cs_test_NADINE1", sophie["jeton"], "nadine@test.example", "Nadine Test"))
    julie = await RL.relais_depuis_paiement_stripe(base, V7.session("cs_test_JULIE01", nadine["jeton"], "julie@test.example", "Julie Test"))
    verifier("H-1 Sophie : génération 1, invitée par l'invitation du coach (racine)",
             sophie["generation"] == 1 and sophie["parent_relais_id"] is None and sophie["parent_jeton"] == racine, sophie)
    verifier("H-2 Nadine : génération 2, inviteur direct = Sophie",
             nadine["generation"] == 2 and nadine["parent_relais_id"] == sophie["id"] and nadine["parent_jeton"] == sophie["jeton"], nadine)
    verifier("H-3 Julie : génération 3, inviteur direct = Nadine",
             julie["generation"] == 3 and julie["parent_relais_id"] == nadine["id"] and julie["parent_jeton"] == nadine["jeton"], julie)
    verifier("H-4 même racine pour les trois (l'invitation du coach)",
             {sophie["racine_jeton"], nadine["racine_jeton"], julie["racine_jeton"]} == {racine})
    verifier("H-5 chacun SON lien, jamais celui de l'invitant",
             len({racine, sophie["jeton"], nadine["jeton"], julie["jeton"]}) == 4)
    _, ch = await appel(RL.chaine_campagne(ev["id"], T.rq(T.COACH_A)))
    _g = {n["prenom"]: (n["generation"], n["invite_par"]) for n in (ch or {}).get("noeuds", [])}
    verifier("H-6 chaîne reconstruite : Sophie (1, coach) -> Nadine (2, Sophie) -> Julie (3, Nadine)",
             _g.get("Sophie") == (1, "coach") and _g.get("Nadine") == (2, "Sophie") and _g.get("Julie") == (3, "Nadine"), _g)

    # ── N. webhook rejoué : idempotent ──────────────────────────────────────
    _n = len(base["invitation_relais"].docs)
    bis = await RL.relais_depuis_paiement_stripe(base, V7.session("cs_test_NADINE1", sophie["jeton"], "nadine@test.example", "Nadine Test"))
    verifier("N-1 même session Stripe rejouée -> le MÊME relais, aucun doublon",
             bis["id"] == nadine["id"] and len(base["invitation_relais"].docs) == _n, (bis.get("id"), _n))

    # ── 12. Espace : ma réservation + mon lien ──────────────────────────────
    ancien = RL._porteur_espace
    sessions = {"jeton-nadine": {"email": "nadine@test.example", "code": "AFR-NAD"}}

    async def faux_porteur(request, code, slug):
        _ch = sessions.get(request.headers.get("x-espace-token"))
        return _ch if _ch and _ch["code"] == code else None
    RL._porteur_espace = faux_porteur
    try:
        c403, _ = await appel(RL.relais_mes_evenements(_RqEspace({"code": "AFR-NAD"}, "")))
        verifier("12-1 sans session d'espace -> 403", c403 == 403, c403)
        c403b, _ = await appel(RL.relais_mes_evenements(_RqEspace({"code": "AFR-AUTRE"}, "jeton-nadine")))
        verifier("12-2 la session de Nadine n'ouvre pas un AUTRE code -> 403", c403b == 403, c403b)
        c, r = await appel(RL.relais_mes_evenements(_RqEspace({"code": "AFR-NAD", "slug": ""}, "jeton-nadine")))
        evts = (r or {}).get("evenements") or []
        verifier("12-3 Nadine : SON événement, SON lien (rien de Sophie ni de Julie)",
                 c == 200 and len(evts) == 1 and evts[0]["relais"]["jeton"] == nadine["jeton"]
                 and evts[0]["titre"] == "AFROBOOST SILENT" and evts[0]["offer_id"] == T.OFFRE_A_PAYANTE, (c, r))
        verifier("12-4 aucune donnée d'un tiers (ni e-mail, ni empreinte, ni coach)",
                 "@" not in str(r) and "empreinte" not in str(r) and T.COACH_A not in str(r), r)
        # événement passé : n'apparaît plus
        for d in base["referral_campaigns"].docs:
            if d.get("id") == ev["id"]:
                d["occurrence"] = "2020-01-01T18:45:00"
        c, r2 = await appel(RL.relais_mes_evenements(_RqEspace({"code": "AFR-NAD"}, "jeton-nadine")))
        verifier("12-5 événement passé -> plus listé", c == 200 and (r2 or {}).get("evenements") == [], r2)
    finally:
        RL._porteur_espace = ancien
    verifier("12-6 « à venir » : le soir même encore listé, la veille non",
             RL._a_venir("2026-10-28T18:45:00", datetime(2026, 10, 28, 20, 0))
             and not RL._a_venir("2026-10-27T18:45:00", datetime(2026, 10, 28, 20, 0)))


def main():
    asyncio.run(principal())
    _res = [r for r in H.RESULTATS if r[0][:2] in ("M-", "H-", "N-", "12")]
    _ok = 0
    for nom, ok, detail in _res:
        print(("  OK     " if ok else "  ECHEC  ") + nom)
        if not ok:
            print("         -> %s" % str(detail)[:500])
        _ok += ok
    print("%d / %d verifications V610m au vert" % (_ok, len(_res)))
    sys.exit(0 if _ok == len(_res) else 1)


if __name__ == "__main__":
    main()
