#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CO-1 — Onglets Contacts et Campagnes pour les coachs partenaires : gardes serveur.

Ouvrir ces onglets aux partenaires expose deux réglages GLOBAUX que le tableau
de bord touchait sans le dire. Ce banc prouve qu'ils sont fermés côté serveur :

  A. `ai_config` (prompt, activation IA, lien Twint, dernier média) :
     PUT /ai-config   partenaire signé -> 403 ; X-User-Email super-admin seul -> 403 ;
                      super-admin signé -> 200 (écrit) ;
     GET /ai-config   anonyme / partenaire -> `{"enabled": …}` SEUL ;
                      super-admin signé -> document complet ;
     GET/DELETE /ai-logs  anonyme / partenaire -> 403 ; super-admin signé -> 200.
  B. WhatsApp d'une campagne = numéro officiel Afroboost :
     POST /campaigns partenaire + whatsapp -> 403 ; sans whatsapp -> 200 ;
     PUT  /campaigns/{id} partenaire qui ajoute whatsapp -> 403 ;
     POST /campaigns/{id}/launch d'une campagne partenaire WhatsApp -> 403,
       AUCUN crédit débité ;
     moteur `launch_campaign` (boucle programmée) : canal WhatsApp neutralisé,
       aucun appel au fournisseur ;
     super-admin : POST /campaigns + whatsapp -> 200, lancement NON bloqué par CO-1.

AUCUN réseau, AUCUNE base réelle (MongoDB en mémoire du banc test_referral_pass_duo).
Lancement :  python3 tests/test_co1_onglets_coach.py
"""
import asyncio
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)

import test_referral_pass_duo as H  # noqa: E402  (pose l'environnement du banc)

S = H.S
import api.routes.campaign_routes as CR  # noqa: E402
from api.routes import co1_onglets_coach as CO1  # noqa: E402
from fastapi import HTTPException  # noqa: E402

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


ADMIN = "contact.artboost@gmail.com"
A = "coach.a@exemple.test"
PROMPT_SECRET = "PROMPT-PLATEFORME-NE-PAS-DIVULGUER"


def req(jeton_de=None, entete=None, corps=None):
    e = {}
    if jeton_de:
        e["Authorization"] = "Bearer " + H.jeton_admin(jeton_de)
    if entete:
        e["X-User-Email"] = entete
    return H.Requete(corps if corps is not None else {}, e)


async def appel(coro):
    try:
        return 200, await coro
    except HTTPException as e:
        return e.status_code, e.detail


APPELS_WA = []


async def _espion_wa(*a, **k):
    APPELS_WA.append((a, k))
    return {"status": "success", "sid": "espion"}


class _CollJournal(H._Coll):
    """Ajoute `delete_many` au faux Mongo (DELETE /ai-logs)."""

    async def delete_many(self, q=None, **k):
        avant = len(self.docs)
        self.docs[:] = [d for d in self.docs if not H._match(d, q or {})]
        return type("R", (), {"deleted_count": avant - len(self.docs)})()


def base_de_depart():
    base = H._Base()
    base._c["ai_logs"] = _CollJournal("ai_logs")
    base["coaches"].docs += [{"email": A, "credits": 50}]
    base["ai_config"].docs += [{"id": "ai_config", "enabled": True, "systemPrompt": PROMPT_SECRET,
                                "twintPaymentUrl": "https://twint.exemple/pay", "lastMediaUrl": "m.jpg",
                                "campaignPrompt": "cp", "model": "gpt-4o-mini", "provider": "openai"}]
    base["ai_logs"].docs += [{"id": "l1", "timestamp": "2026-09-01", "fromPhone": "+41790000000",
                              "incomingMessage": "salut", "aiResponse": "ok"}]
    # Contact RÉEL (ni « test » ni sans relation) : sans la garde CO-1, le moteur
    # lui enverrait vraiment un WhatsApp — le banc est donc discriminant.
    base["users"].docs += [{"id": "uA1", "name": "Alice Martin", "email": "alice.martin@bluewin.ch",
                            "whatsapp": "+41791112233", "coach_id": A}]
    base["reservations"].docs += [{"id": "r1", "userWhatsapp": "+41791112233",
                                   "userEmail": "alice.martin@bluewin.ch", "coach_id": A}]
    base["campaigns"].docs += [
        {"id": "cA", "name": "Camp A", "coach_id": A, "status": "draft", "results": [],
         "channels": {"internal": True}, "targetIds": [], "createdAt": "2026-09-01"},
        {"id": "cAwa", "name": "Camp A WhatsApp", "coach_id": A, "status": "draft", "results": [],
         "channels": {"whatsapp": True, "internal": False, "email": False},
         "targetType": "all", "targetIds": [], "createdAt": "2026-09-02"},
    ]
    S.db = base
    CR.init_campaign_db(base)
    for nom in ("send_whatsapp_direct", "_send_whatsapp_campaign_template"):
        setattr(S, nom, _espion_wa)
    APPELS_WA[:] = []
    return base


def credits(base, email):
    return next((d.get("credits") for d in base["coaches"].docs if d.get("email") == email), None)


def ia(base):
    return next(d for d in base["ai_config"].docs if d.get("id") == "ai_config")


# ─────────────────────────────────────────────────────────────────────────────
# A. ai_config / ai_logs
# ─────────────────────────────────────────────────────────────────────────────
async def partie_ia():
    base = base_de_depart()
    c, r = await appel(S.update_ai_config(S.AIConfigUpdate(systemPrompt="pirate"), req(A)))
    verifier("A1. PUT /ai-config partenaire signé -> 403", c == 403, (c, r))
    verifier("A2. ... et le prompt global est intact", ia(base)["systemPrompt"] == PROMPT_SECRET)
    c, r = await appel(S.update_ai_config(S.AIConfigUpdate(lastMediaUrl="x.jpg"), req(A)))
    verifier("A3. PUT lastMediaUrl (envoi groupé) partenaire -> 403", c == 403, (c, r))
    c, r = await appel(S.update_ai_config(S.AIConfigUpdate(enabled=False), req(entete=ADMIN)))
    verifier("A4. PUT X-User-Email super-admin SANS jeton -> 403", c == 403, (c, r))
    c, r = await appel(S.update_ai_config(S.AIConfigUpdate(enabled=False), req()))
    verifier("A5. PUT anonyme -> 403", c == 403, (c, r))
    c, r = await appel(S.update_ai_config(S.AIConfigUpdate(), req()))
    verifier("A5b. PUT anonyme corps VIDE -> 403 (sonde inerte de nonregression)", c == 403, (c, r))
    verifier("A6. ... toujours activée", ia(base)["enabled"] is True)
    c, r = await appel(S.update_ai_config(S.AIConfigUpdate(systemPrompt="nouveau prompt"), req(ADMIN)))
    verifier("A7. PUT super-admin signé -> 200 et écrit", c == 200 and ia(base)["systemPrompt"] == "nouveau prompt", (c, r))
    ia(base)["systemPrompt"] = PROMPT_SECRET

    c, r = await appel(S.get_ai_config(req()))
    verifier("A8. GET /ai-config anonyme -> {enabled} seul", c == 200 and r == {"enabled": True}, (c, r))
    c, r = await appel(S.get_ai_config(req(A)))
    verifier("A9. GET /ai-config partenaire -> {enabled} seul (aucun prompt)", c == 200 and r == {"enabled": True}, (c, r))
    c, r = await appel(S.get_ai_config(req(entete=ADMIN)))
    verifier("A10. GET X-User-Email super-admin sans jeton -> {enabled} seul", c == 200 and r == {"enabled": True}, (c, r))
    c, r = await appel(S.get_ai_config(req(ADMIN)))
    verifier("A11. GET super-admin signé -> document complet",
             c == 200 and r.get("systemPrompt") == PROMPT_SECRET and r.get("twintPaymentUrl"), (c, r))

    for nom, rq in (("anonyme", req()), ("partenaire", req(A)), ("X-User-Email admin", req(entete=ADMIN))):
        c, r = await appel(S.get_ai_logs(rq))
        verifier("A12. GET /ai-logs %s -> 403" % nom, c == 403, (c, r))
        c, r = await appel(S.clear_ai_logs(rq))
        verifier("A13. DELETE /ai-logs %s -> 403" % nom, c == 403, (c, r))
    verifier("A14. ... journal IA intact", len(base["ai_logs"].docs) == 1)
    c, r = await appel(S.get_ai_logs(req(ADMIN)))
    verifier("A15. GET /ai-logs super-admin signé -> 200", c == 200 and isinstance(r, list) and len(r) == 1, (c, r))
    c, r = await appel(S.clear_ai_logs(req(ADMIN)))
    verifier("A16. DELETE /ai-logs super-admin signé -> 200", c == 200 and len(base["ai_logs"].docs) == 0, (c, r))


# ─────────────────────────────────────────────────────────────────────────────
# B. WhatsApp des campagnes
# ─────────────────────────────────────────────────────────────────────────────
async def partie_whatsapp():
    verifier("B0. règle pure : partenaire + whatsapp -> interdit",
             CO1.whatsapp_campagne_interdit(A, {"whatsapp": True}))
    verifier("B0b. règle pure : super-admin / historique / sans whatsapp -> permis",
             not CO1.whatsapp_campagne_interdit(ADMIN, {"whatsapp": True})
             and not CO1.whatsapp_campagne_interdit("", {"whatsapp": True})
             and not CO1.whatsapp_campagne_interdit(A, {"whatsapp": False, "email": True}))

    base = base_de_depart()
    n0 = len(base["campaigns"].docs)
    c, r = await appel(S.create_campaign(S.CampaignCreate(name="WA", message="m",
                                                          channels={"whatsapp": True}), req(A)))
    verifier("B1. POST /campaigns partenaire + WhatsApp -> 403 message clair",
             c == 403 and "numéro officiel Afroboost" in str(r), (c, r))
    verifier("B2. ... aucune campagne créée", len(base["campaigns"].docs) == n0)
    c, r = await appel(S.create_campaign(S.CampaignCreate(name="Mail", message="m",
                                                          channels={"email": True, "whatsapp": False}), req(A)))
    verifier("B3. POST /campaigns partenaire e-mail -> 200", c == 200 and r.get("coach_id") == A, (c, r))

    c, r = await appel(S.update_campaign("cA", req(A, corps={"channels": {"whatsapp": True}})))
    verifier("B4. PUT partenaire qui ajoute WhatsApp -> 403", c == 403, (c, r))
    c, r = await appel(S.update_campaign("cA", req(A, corps={"name": "Camp A bis"})))
    verifier("B5. PUT partenaire sans toucher aux canaux -> 200", c == 200, (c, r))

    avant = credits(base, A)
    c, r = await appel(S.v451_lancer_campagne_http("cAwa", req(A)))
    verifier("B6. launch d'une campagne partenaire WhatsApp -> 403", c == 403 and "numéro officiel" in str(r), (c, r))
    verifier("B7. ... aucun crédit débité", credits(base, A) == avant, (avant, credits(base, A)))
    verifier("B8. ... aucun appel WhatsApp", not APPELS_WA)

    # Moteur (boucle programmée, sans passer par la porte HTTP) : défense en profondeur.
    try:
        res = await S.launch_campaign("cAwa")
    except HTTPException as e:
        res = {"_http": e.status_code}
    wa = [x for x in (res.get("results") or []) if x.get("channel") == "whatsapp" and x.get("status") != "skipped"] \
        if isinstance(res, dict) else []
    verifier("B9. moteur : campagne partenaire WhatsApp -> aucun envoi WhatsApp", not APPELS_WA and not wa,
             (APPELS_WA, res))

    # Super-admin : inchangé.
    c, r = await appel(S.create_campaign(S.CampaignCreate(name="WA admin", message="m",
                                                          channels={"whatsapp": True}), req(ADMIN)))
    verifier("B10. POST /campaigns super-admin + WhatsApp -> 200", c == 200, (c, r))
    if c == 200:
        c2, r2 = await appel(S.v451_lancer_campagne_http(r["id"], req(ADMIN)))
        verifier("B11. launch super-admin WhatsApp -> pas de refus CO-1",
                 not (c2 == 403 and "numéro officiel" in str(r2)), (c2, str(r2)[:200]))
        verifier("B12. témoin positif : le super-admin atteint bien le fournisseur WhatsApp",
                 len(APPELS_WA) >= 1, (APPELS_WA, str(r2)[:300]))


def main():
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
    except Exception:
        pass
    boucle = asyncio.get_event_loop()
    for partie in (partie_ia, partie_whatsapp):
        try:
            boucle.run_until_complete(partie())
        except Exception as e:
            import traceback
            traceback.print_exc()
            verifier("%s s'exécute sans exception" % partie.__name__, False, repr(e))
    ok = sum(1 for _, c, _ in RESULTATS if c)
    print("=" * 78)
    print("CO-1 — ONGLETS COACH : %d vérifications" % len(RESULTATS))
    print("=" * 78)
    for nom, cond, detail in RESULTATS:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom,
                               ("" if cond or not detail else "\n         -> " + str(detail)[:400])))
    print("-" * 78)
    print("%d / %d verifications au vert" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())
