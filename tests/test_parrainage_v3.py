#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V556 — PARRAINAGE V3 « boule de neige » : le banc sécurité / idempotence.

Règle prouvée : avant de s'inscrire sur une invitation (pass P0), le visiteur
prépare ET partage une invitation ENFANT (P1) ; le serveur refuse le join tant
que ce partage n'a pas été déclenché. Chaîne A -> B -> C -> D, anti-boucle,
anti-double récompense, versions d'aperçu (WhatsApp), anciens liens, OG.

Même harnais que `test_referral_pass_duo.py` (MongoDB en mémoire, VRAIES
routes, VRAI moteur pur, VRAIES gardes ESSAI-1/ESSAI-4) — importé, jamais
recopié. AUCUN réseau, AUCUN e-mail, AUCUNE donnée réelle. Le seul disque
touché est un dossier temporaire (cache des cartes), supprimé à la fin.

Lancement :  python3 tests/test_parrainage_v3.py
"""
import asyncio
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)

import test_referral_pass_duo as H  # noqa: E402  (pose l'environnement du banc)

from PIL import Image  # noqa: E402

S, R, E = H.S, H.R, H.E
verifier, appel = H.verifier, H.appel
FRONT = "https://afroboost.com"

# Les originaux AVANT que `poser_mouchards` ne les remplace (preuve directe
# de la garde « jamais de notification vers une adresse en attente »).
_ORIG_PUSH_PARRAIN = R._push_parrain
_ORIG_EMAIL_PARRAIN = R._email_parrain_debloque

PREFIXE_ATTENTE = E.PREFIXE_PARRAIN_EN_ATTENTE


# ═══════════════════════════════════════════════════════════════════════════
# Outils
# ═══════════════════════════════════════════════════════════════════════════
_IPN = [0]


def req(corps=None, entetes=None):
    """Une requête publique avec une IP NEUVE (le débit 20/h par IP ne gêne pas)."""
    _IPN[0] += 1
    _n = _IPN[0]
    _e = {"CF-Connecting-IP": "198.51.%d.%d" % (_n // 250, _n % 250 + 1)}
    _e.update(entetes or {})
    return H.Requete(corps if corps is not None else {}, _e)


NOMS = {1: "Alice Martin", 2: "Bruno Keller", 3: "Chloe Favre", 4: "David Roux",
        5: "Emma Blanc", 6: "Farid Nguyen", 7: "Gaelle Morel", 8: "Hugo Perret"}


def ident(n):
    """(e-mail, téléphone, nom) — distincts pour chaque personne."""
    return ("personne%d.v3@exemple.test" % n,
            "+41 77 %03d %02d %02d" % (100 + n, (n * 13) % 100, (n * 7) % 100),
            NOMS.get(n, "Personne%d Test" % n))


def chiffres(tel):
    return "".join(c for c in str(tel) if c.isdigit())


def raison(rep):
    return ((rep or {}).get("headers") or {}).get("X-Refus-Raison")


def doc_par_tok(base, tok):
    for d in base["referral_passes"].docs:
        if d.get("share_token") == tok:
            return d
    return None


def doc_par_id(base, pid):
    for d in base["referral_passes"].docs:
        if d.get("id") == pid:
            return d
    return None


def etat(base):
    return {"passes": len(base["referral_passes"].docs), "resas": len(base["reservations"].docs),
            "codes": len(base["discount_codes"].docs), "subs": len(base["subscriptions"].docs),
            "verrous": len(base["free_trial_claims"].docs),
            "mouv": len(base["seance_mouvements"].docs)}


async def pub(tok):
    return await appel(R.referral_pass_public(tok))


CLES = {}          # jeton du parent -> edit_key de SON invitation enfant (« l'appareil »)
_DEF = object()


async def chaine(tok, corps=None):
    c, r = await appel(R.referral_chaine_creer(tok, req(corps or {})))
    if isinstance(r, dict) and r.get("edit_key"):
        CLES[tok] = r["edit_key"]
    return c, r


def _entete_cle(tok, cle):
    _k = CLES.get(tok) if cle is _DEF else cle
    return {"X-Chain-Key": _k} if _k else {}


async def chaine_patch(tok, corps, cle=None):
    _e = {"X-Chain-Key": cle} if cle is not None else {}
    return await appel(R.referral_chaine_modifier(tok, req(corps, _e)))


async def partager(tok, canal="whatsapp", cle=_DEF):
    return await appel(R.referral_chaine_partager(tok, req({"channel": canal}, _entete_cle(tok, cle))))


async def apercu(tok):
    return await appel(R.referral_chaine_apercu(tok, req()))


async def rejoindre(tok, n, email=None, tel=None, nom=None, cle=_DEF):
    _e, _t, _n = ident(n)
    return await appel(R.referral_join(tok, req(H.corps_ami(email or _e, tel or _t, nom or _n),
                                                _entete_cle(tok, cle))))


async def preparer_et_partager(tok, corps=None):
    """Le parcours du visiteur : prépare l'invitation enfant puis la partage
    (depuis « son appareil » : la clé rendue à la création). Rend (T_enfant, clé)."""
    c, r = await chaine(tok, corps)
    assert c in (200, 201), (c, r)
    c2, r2 = await partager(tok)
    assert c2 == 200, (c2, r2)
    return r["child"]["share_token"], CLES.get(tok)


def resas_de(base, email):
    return [r for r in base["reservations"].docs
            if (r.get("userEmail") or "").lower() == email and r.get("status") != "cancelled"]


def codes_de(base, email):
    return [d for d in base["discount_codes"].docs if d.get("assignedEmail") == email]


def debits(base, code):
    return H.bilan_seances(base, code)[0]


async def page(tok, v="", ua="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Safari/604.1"):
    r = await S.share_duo_page(tok, req({}, {"user-agent": ua}), v=v)
    return r.status_code, bytes(getattr(r, "body", b"") or b"").decode("utf-8", "replace"), r


async def carte(tok, v=""):
    r = await S.share_duo_carte(tok, v)
    _t = {k.lower(): val for k, val in dict(r.headers).items()}.get("content-type", "")
    return r.status_code, bytes(getattr(r, "body", b"") or b""), _t


def og(html_texte):
    return E.extraire_og(html_texte)


def image(octets):
    try:
        _i = Image.open(io.BytesIO(octets))
        _i.load()
        return _i
    except Exception:  # noqa: BLE001
        return None


def fuite(objet, base, extra=()):
    """Ce qu'une réponse publique ne doit JAMAIS contenir."""
    _s = json.dumps(objet, ensure_ascii=False, default=str)
    _trouve = list(E.contient_pii(objet))
    for d in base["referral_passes"].docs:
        if d.get("id") and d["id"] in _s:
            _trouve.append("id_interne:" + d["id"][:8])
    for m in ("edit_key_hash", PREFIXE_ATTENTE, "AFR-", H.PARRAIN_EMAIL, H.PARRAIN_CODE,
              chiffres(H.PARRAIN_TEL)) + tuple(extra):
        if m and m in _s:
            _trouve.append(m)
    for n in range(1, 9):
        _e, _t, _ = ident(n)
        if _e in _s or chiffres(_t) in _s:
            _trouve.append("personne%d" % n)
    return _trouve


async def depart(chaine_active=True, **k):
    base, occ = H.base_de_depart(chaine=chaine_active, **k)
    c, p0 = await H.creer_pass(base, occ)
    assert c == 201, (c, p0)
    return base, occ, p0


# ═══════════════════════════════════════════════════════════════════════════
# 1. Drapeau  /  2. Porte  /  3-5. Routes de la chaîne
# ═══════════════════════════════════════════════════════════════════════════
async def partie_drapeau_porte_routes():
    # ── 1. drapeau ─────────────────────────────────────────────────────────
    base, occ, p0 = await depart(chaine_active=True)
    t0 = p0["share_token"]
    c, g = await pub(t0)
    verifier("1. chaine=True : GET /pass porte chain_required:true, chain {exists:false, shared:false}",
             c == 200 and g.get("chain_required") is True and g.get("chain") == {"exists": False, "shared": False}, g)

    base_off, occ_off, p0_off = await depart(chaine_active=False)
    c, g = await pub(p0_off["share_token"])
    verifier("1b. chaine=False : chain_required:false", c == 200 and g.get("chain_required") is False, g)
    c, j = await rejoindre(p0_off["share_token"], 1)
    verifier("1c. chaine=False : le join direct marche comme avant (unlocked, 2 billets)",
             c == 200 and j.get("status") == "unlocked" and len(j.get("tickets", [])) == 2, (c, str(j)[:200]))
    c, r = await chaine(p0_off["share_token"])
    verifier("1d. chaine=False : POST /chain -> 404 (règle coupée)", c == 404, (c, r))
    # champ ABSENT = règle ÉTEINTE (décision du 28/09 : on déploie éteint, on allume ensuite)
    base_abs, occ_abs = H.base_de_depart()
    base_abs["feature_flags"].docs[0].pop("parrainage_chaine_enabled", None)
    _, p_abs = await H.creer_pass(base_abs, occ_abs)
    c, g = await pub(p_abs["share_token"])
    verifier("1e. drapeau ABSENT en base = règle ÉTEINTE (chain_required:false)",
             c == 200 and g.get("chain_required") is False, g)
    # et le join direct V2 marche avec le drapeau absent (aucune invitation exigée)
    c, r = await H.appel(H.R.referral_join(p_abs["share_token"], H.Requete(H.corps_ami(), {})))
    verifier("1f. drapeau ABSENT : join direct V2 accepté (aucune 409 invitation_requise)",
             c == 200 and r.get("status") in ("unlocked", "friend_registered"), (c, r))
    # base illisible = règle éteinte aussi
    class _Muette:
        async def find_one(self, *a, **k):
            raise RuntimeError("base muette")
    _vrai = H.R.db
    class _Enveloppe:
        def __getitem__(self, nom):
            return _Muette() if nom == "feature_flags" else _vrai[nom]
        def __getattr__(self, nom):
            return getattr(_vrai, nom)
    H.R.db = _Enveloppe()
    try:
        _act = await H.R._chaine_active()
    finally:
        H.R.db = _vrai
    verifier("1g. drapeau ILLISIBLE = règle ÉTEINTE (repli sûr)", _act is False, _act)

    # ── 2. porte ───────────────────────────────────────────────────────────
    base, occ, p0 = await depart()
    t0 = p0["share_token"]
    await pub(t0)
    avant = etat(base)
    c, r = await rejoindre(t0, 1)
    d0 = doc_par_tok(base, t0)
    verifier("2. join AVANT partage -> 409 X-Refus-Raison: invitation_requise",
             c == 409 and raison(r) == "invitation_requise", (c, r))
    verifier("2b. rien écrit : pas d'invité, ni code, ni réservation, ni verrou d'essai, ni pass",
             d0["invitee"] is None and etat(base) == avant and not base["free_trial_claims"].docs
             and not H.MOUCHARDS["paiements"], (etat(base), avant))
    # préparé mais PAS partagé : toujours refusé
    c, r = await chaine(t0)
    c2, r2 = await rejoindre(t0, 1)
    verifier("2c. invitation préparée mais NON partagée : join toujours 409 invitation_requise",
             c == 201 and c2 == 409 and raison(r2) == "invitation_requise"
             and doc_par_tok(base, t0)["invitee"] is None, (c2, r2))

    # ── 3. POST /chain ─────────────────────────────────────────────────────
    base, occ, p0 = await depart()
    t0 = p0["share_token"]
    c, r = await chaine(t0, {"display_name": "Henri", "message": "Viens avec moi"})
    ch = (r or {}).get("child") or {}
    t1 = ch.get("share_token")
    verifier("3. POST /chain -> 201 + edit_key + child", c == 201 and r.get("edit_key") and t1, (c, str(r)[:300]))
    verifier("3b. child.share_token ≠ parent ; share_url = /api/share/duo/<T1>?v=1 ; card_url https",
             t1 and t1 != t0 and ch.get("share_url") == "%s/api/share/duo/%s?v=1" % (FRONT, t1)
             and str(ch.get("card_url", "")).startswith("https://afroboost.com/api/share/duo/%s/carte.jpg?v=" % t1)
             and ch.get("invite_url") == "%s/duo/%s" % (FRONT, t1)
             and ch.get("whatsapp_text", "").endswith(ch.get("share_url", "#")), ch)
    verifier("3c. réponse de création : shared:false, preview présent",
             r.get("shared") is False and isinstance(r.get("preview"), dict), {k: r.get(k) for k in ("shared", "preview")})
    n_passes = len(base["referral_passes"].docs)
    c2, r2 = await chaine(t0, {"display_name": "Autre"})
    verifier("3d. 2e POST /chain -> 200, MÊME share_token, SANS edit_key, aucun pass en plus",
             c2 == 200 and r2["child"]["share_token"] == t1 and "edit_key" not in r2
             and len(base["referral_passes"].docs) == n_passes and r2["child"]["display_name"] == "Henri",
             (c2, str(r2)[:200]))
    d0, d1 = doc_par_tok(base, t0), doc_par_tok(base, t1)
    verifier("3e. parent.chain.child_pass_id posé = id de l'enfant",
             (d0.get("chain") or {}).get("child_pass_id") == d1["id"], d0.get("chain"))
    verifier("3f. enfant : sponsor en attente (pending, clé chaine-en-attente:<parent>), chain.parent/root/depth",
             d1["sponsor"].get("pending") is True
             and d1["sponsor"]["email_norm"] == PREFIXE_ATTENTE + d0["id"]
             and d1["chain"]["parent_pass_id"] == d0["id"] and d1["chain"]["root_pass_id"] == d0["id"]
             and d1["chain"]["depth"] == 1 and d1["occurrence"] == d0["occurrence"], d1.get("chain"))
    verifier("3g. aucune adresse « chaine-en-attente: » dans les réponses ni dans dto_enfant",
             PREFIXE_ATTENTE not in json.dumps(r) and PREFIXE_ATTENTE not in json.dumps(r2)
             and PREFIXE_ATTENTE not in json.dumps(E.dto_enfant(d1, FRONT))
             and PREFIXE_ATTENTE not in json.dumps((await pub(t1))[1]), "")
    verifier("3h. l'edit_key n'est jamais stockée en clair (hash seulement)",
             r["edit_key"] not in json.dumps(base["referral_passes"].docs)
             and d1["chain"].get("edit_key_hash"), "")

    # concurrence : 3 POST simultanés sur un pass neuf -> UNE enfant
    base, occ, p0 = await depart()
    t0 = p0["share_token"]
    rs = await asyncio.gather(chaine(t0), chaine(t0), chaine(t0))
    enfants = [d for d in base["referral_passes"].docs
               if (d.get("chain") or {}).get("parent_pass_id") == doc_par_tok(base, t0)["id"]]
    toks = {x[1]["child"]["share_token"] for x in rs if x[0] in (200, 201)}
    verifier("3i. 3 POST /chain concurrents (asyncio.gather) : UNE seule enfant, même jeton pour tous, une seule edit_key",
             len(enfants) == 1 and len(toks) == 1 and all(x[0] in (200, 201) for x in rs)
             and sum(1 for x in rs if x[1].get("edit_key")) == 1,
             ([x[0] for x in rs], len(enfants), toks))

    # ── 4. PATCH /chain ────────────────────────────────────────────────────
    base, occ, p0 = await depart()
    t0 = p0["share_token"]
    c, r = await chaine(t0, {"display_name": "Henri"})
    cle, t1, url1 = r["edit_key"], r["child"]["share_token"], r["child"]["share_url"]
    c, x = await chaine_patch(t0, {"display_name": "Zoé"})
    verifier("4. PATCH /chain sans clé -> 403", c == 403, (c, x))
    c, x = await chaine_patch(t0, {"display_name": "Zoé"}, "mauvaise-cle")
    verifier("4b. PATCH /chain mauvaise clé -> 403, rien modifié",
             c == 403 and doc_par_tok(base, t1)["invitation"]["display_name"] == "Henri", (c, x))
    c, x = await chaine_patch(t0, {"display_name": "Zoé", "message": "Nouveau message"}, cle)
    verifier("4c. PATCH bonne clé -> 200, même jeton, share_url change de v, prénom/message appliqués",
             c == 200 and x["child"]["share_token"] == t1 and x["child"]["share_url"] != url1
             and x["child"]["display_name"] == "Zoé" and x["child"]["message"] == "Nouveau message"
             and "edit_key" not in x, (c, str(x)[:300]))
    c, x = await chaine_patch(t0, {"message": "x" * 281}, cle)
    verifier("4d. PATCH message > 280 -> 422", c == 422, (c, x))
    c, x = await chaine_patch(t0, {"display_name": "henri@exemple.test"}, cle)
    verifier("4e. PATCH display_name avec « @ » -> 422", c == 422, (c, x))
    base2, occ2, p02 = await depart()
    c, x = await chaine(p02["share_token"], {"message": "y" * 281})
    verifier("4f. POST /chain message > 280 -> 422, aucune enfant créée",
             c == 422 and len(base2["referral_passes"].docs) == 1, (c, x))
    c, x = await chaine(p02["share_token"], {"display_name": "a@b.ch"})
    verifier("4g. POST /chain display_name avec « @ » -> 422", c == 422, (c, x))

    # ── 5. POST /chain/share ───────────────────────────────────────────────
    base, occ, p0 = await depart()
    t0 = p0["share_token"]
    c, x = await partager(t0)
    verifier("5. share SANS enfant -> 404, rien écrit",
             c == 404 and not (doc_par_tok(base, t0).get("chain") or {}).get("shared_at"), (c, x))
    await chaine(t0)
    c, x = await partager(t0, "pigeon")
    verifier("5b. canal inconnu -> 400, parent non marqué partagé",
             c == 400 and not (doc_par_tok(base, t0).get("chain") or {}).get("shared_at"), (c, x))
    c, x = await partager(t0, "whatsapp")
    d0 = doc_par_tok(base, t0)
    verifier("5c. share whatsapp -> 200 shared:true, shared_at rendu, parent.chain.shared_at posé",
             c == 200 and x.get("shared") is True and x.get("shared_at")
             and d0["chain"].get("shared_at") == x["shared_at"] and d0["chain"].get("share_channel") == "whatsapp",
             (c, str(x)[:200], d0.get("chain")))
    c, g = await pub(t0)
    verifier("5d. GET public après partage : chain {exists:true, shared:true}",
             g.get("chain") == {"exists": True, "shared": True}, g.get("chain"))
    for canal in ("share", "share_image", "copy"):
        c, x = await partager(t0, canal)
        verifier("5e. canal %s accepté (200)" % canal, c == 200, (c, x))
    c, x = await apercu(t0)
    verifier("5f. GET /chain/preview -> 200 {child, shared:true, preview}",
             c == 200 and x.get("shared") is True and x.get("child", {}).get("share_token")
             and isinstance(x.get("preview"), dict), (c, str(x)[:200]))
    base3, occ3, p03 = await depart()
    c, x = await apercu(p03["share_token"])
    verifier("5g. GET /chain/preview sans enfant -> 404", c == 404, (c, x))


# ═══════════════════════════════════════════════════════════════════════════
# 6. Deux partages successifs  /  7. join après partage
# ═══════════════════════════════════════════════════════════════════════════
async def partie_partages_successifs():
    base, occ, p0 = await depart()
    t0 = p0["share_token"]
    c, r = await chaine(t0, {"display_name": "Henri"})
    t1 = r["child"]["share_token"]
    url0, carte0 = r["child"]["share_url"], r["child"]["card_url"]
    avant = etat(base)
    n_credits = len(H.MOUCHARDS["paiements"])
    c1, s1 = await partager(t0)
    c2, s2 = await partager(t0)
    url1, url2 = s1["child"]["share_url"], s2["child"]["share_url"]

    def _v(u):
        return int(u.split("?v=")[1]) if "?v=" in u else 0

    verifier("6. deux partages : même share_token, share_url différentes, v strictement croissant",
             c1 == c2 == 200 and s1["child"]["share_token"] == s2["child"]["share_token"] == t1
             and _v(url0) < _v(url1) < _v(url2), (url0, url1, url2))
    verifier("6b. card_url change aussi à chaque partage",
             len({carte0, s1["child"]["card_url"], s2["child"]["card_url"]}) == 3,
             (carte0, s1["child"]["card_url"], s2["child"]["card_url"]))
    verifier("6c. AUCUN nouveau pass, aucune réservation, aucun code, aucun crédit",
             etat(base) == avant and len(H.MOUCHARDS["paiements"]) == n_credits, (etat(base), avant))
    for u in (url0, url1, url2):
        _vv = u.split("?v=")[1] if "?v=" in u else ""
        c, h, _ = await page(t1, _vv, ua="WhatsApp/2.24.1 A")
        verifier("6d. la page ?v=%s sert 200 et og:url = l'URL EXACTE demandée" % _vv,
                 c == 200 and og(h).get("og:url") == u, (c, og(h).get("og:url"), u))
    for cu in (carte0, s2["child"]["card_url"]):
        _hv = cu.split("?v=")[1]
        c, o, t = await carte(t1, _hv)
        verifier("6e. carte ?v=%s -> 200 image/jpeg" % _hv, c == 200 and t.startswith("image/jpeg") and o, (c, t))

    # côté parrain inscrit : POST /api/referral/invitations deux fois
    tok_esp = H.jeton_espace(base)
    c1, i1 = await appel(R.referral_invitation(H.req_parrain(base, {"pass_id": p0["id"], "channel": "whatsapp"}, tok=tok_esp)))
    c2, i2 = await appel(R.referral_invitation(H.req_parrain(base, {"pass_id": p0["id"], "channel": "whatsapp"}, tok=tok_esp)))
    verifier("6f. parrain inscrit : deux POST /invitations -> share_url différentes, même jeton, card_url différentes",
             c1 == c2 == 201 and i1.get("share_url") and i1["share_url"] != i2.get("share_url")
             and i1["share_url"].split("?")[0] == i2["share_url"].split("?")[0] == "%s/api/share/duo/%s" % (FRONT, t0)
             and i1.get("card_url") != i2.get("card_url"),
             (i1.get("share_url"), i2.get("share_url")))
    verifier("6g. les invitations du parrain ne créent ni pass, ni réservation, ni crédit",
             len(base["referral_passes"].docs) == avant["passes"] and len(base["reservations"].docs) == avant["resas"]
             and len(H.MOUCHARDS["paiements"]) == n_credits, etat(base))

    # ── 7. join après partage ──────────────────────────────────────────────
    ea, ta, _ = ident(1)
    c, j = await rejoindre(t0, 1)
    verifier("7. join APRÈS partage -> 200 (unlocked : Léa a des séances)",
             c == 200 and j.get("status") == "unlocked", (c, str(j)[:300]))
    d1 = doc_par_tok(base, t1)
    verifier("7b. l'enfant est LIÉ : sponsor.email_norm = e-mail de A, pending False, code d'A, tel d'A",
             d1["sponsor"]["email_norm"] == ea and d1["sponsor"].get("pending") is False
             and d1["sponsor"].get("subscription_code") == (codes_de(base, ea) or [{}])[0].get("code")
             and chiffres(d1["sponsor"].get("whatsapp_norm")) == chiffres(ta), d1["sponsor"])
    verifier("7c. l'enfant lié garde son prénom d'affichage (Henri) et son jeton",
             d1["invitation"]["display_name"] == "Henri" and d1["share_token"] == t1, d1.get("invitation"))


# ═══════════════════════════════════════════════════════════════════════════
# 8. Chaîne A -> B -> C -> D
# ═══════════════════════════════════════════════════════════════════════════
async def partie_chaine_complete():
    base, occ, p0 = await depart()
    t0 = p0["share_token"]
    (ea, ta, _), (eb, tb, _), (ec, tc, _), (ed, td, _) = ident(1), ident(2), ident(3), ident(4)
    # A
    await pub(t0)
    t1, _ = await preparer_et_partager(t0)
    c, ja = await rejoindre(t0, 1)
    verifier("8. A (après partage de P1) s'inscrit sur P0 -> unlocked", c == 200 and ja.get("status") == "unlocked", (c, str(ja)[:200]))
    code_a = codes_de(base, ea)[0]["code"]
    resa_a = resas_de(base, ea)
    debits_a = debits(base, code_a)
    # B
    c, g1 = await pub(t1)
    verifier("8b. B ouvre P1 : chain_required:true, chain {exists:false}",
             c == 200 and g1.get("chain_required") is True and g1.get("chain") == {"exists": False, "shared": False}, g1)
    c, r = await rejoindre(t1, 2)
    verifier("8c. B ne peut pas s'inscrire avant d'avoir partagé P2 -> 409 invitation_requise",
             c == 409 and raison(r) == "invitation_requise" and doc_par_tok(base, t1)["invitee"] is None, (c, r))
    n_resas_avant_b = len(base["reservations"].docs)
    t2, _ = await preparer_et_partager(t1)
    c, jb = await rejoindre(t1, 2)
    d0, d1 = doc_par_tok(base, t0), doc_par_tok(base, t1)
    verifier("8d. B partage P2 puis s'inscrit : P1 unlocked", c == 200 and jb.get("status") == "unlocked"
             and d1["status"] == "unlocked", (c, str(jb)[:300], d1.get("blocked_reason")))
    verifier("8e. P1 reprend la réservation de filleul d'A sur P0 : reservations.sponsor_id(P1) == reservations.invitee_id(P0)",
             d1["reservations"].get("sponsor_id") and d1["reservations"]["sponsor_id"] == d0["reservations"]["invitee_id"],
             (d1["reservations"], d0["reservations"]))
    verifier("8f. AUCUNE nouvelle réservation pour A, aucun débit de séance en plus pour A",
             len(resas_de(base, ea)) == len(resa_a) == 1 and debits(base, code_a) == debits_a == 1
             and len(base["reservations"].docs) == n_resas_avant_b + 1, (len(resas_de(base, ea)), debits(base, code_a)))
    verifier("8g. B a exactement 1 code d'essai et 1 réservation",
             len(codes_de(base, eb)) == 1 and len(resas_de(base, eb)) == 1, "")
    verifier("8g-bis. le billet parrain de P1 est la réservation d'A (2 billets, un par personne)",
             len(jb.get("tickets", [])) == 2 and len({t.get("reservationCode") for t in jb["tickets"]}) == 2, jb.get("tickets"))
    # C
    c, g2 = await pub(t2)
    verifier("8h. C ouvre P2 : chain_required:true", g2.get("chain_required") is True, g2)
    c, r = await rejoindre(t2, 3)
    verifier("8i. C avant partage -> 409 invitation_requise", c == 409 and raison(r) == "invitation_requise", (c, r))
    t3, _ = await preparer_et_partager(t2)
    code_b = codes_de(base, eb)[0]["code"]
    c, jc = await rejoindre(t2, 3)
    d2 = doc_par_tok(base, t2)
    verifier("8j. C s'inscrit sur P2 -> unlocked, place de B reprise (aucun 2e débit pour B)",
             c == 200 and jc.get("status") == "unlocked"
             and d2["reservations"]["sponsor_id"] == d1["reservations"]["invitee_id"]
             and debits(base, code_b) == 1 and len(resas_de(base, eb)) == 1, (c, str(jc)[:200]))
    # D
    c, g3 = await pub(t3)
    c2, r = await rejoindre(t3, 4)
    verifier("8k. D ouvre P3 : chain_required:true et join avant partage -> 409 invitation_requise",
             g3.get("chain_required") is True and c2 == 409 and raison(r) == "invitation_requise", (g3.get("chain_required"), c2, r))
    d3 = doc_par_tok(base, t3)
    verifier("8l. qui-a-invité-qui : parent_pass_id P1->P0, P2->P1, P3->P2",
             d1["chain"]["parent_pass_id"] == d0["id"] and d2["chain"]["parent_pass_id"] == d1["id"]
             and d3["chain"]["parent_pass_id"] == d2["id"], "")
    verifier("8m. root_pass_id == P0 pour tous, depth 1/2/3",
             all(d["chain"]["root_pass_id"] == d0["id"] for d in (d1, d2, d3))
             and [d["chain"]["depth"] for d in (d1, d2, d3)] == [1, 2, 3], [d["chain"] for d in (d1, d2, d3)])
    verifier("8n. P2 est lié à B, P3 lié à C (pending False)",
             d2["sponsor"]["email_norm"] == eb and d3["sponsor"]["email_norm"] == ec
             and d3["sponsor"].get("pending") is False, "")
    verifier("8o. chacun (A, B, C) n'a reçu qu'UN essai (un code, un verrou e-mail + un verrou tél.)",
             all(len(codes_de(base, e)) == 1 for e in (ea, eb, ec))
             and {"trial:" + e for e in (ea, eb, ec)} <= {d["_id"] for d in base["free_trial_claims"].docs}, "")
    verifier("8p. aucun push vers une adresse en attente pendant toute la chaîne",
             not [m for m in H.MOUCHARDS["push"] if str(m["email"]).startswith(PREFIXE_ATTENTE) or "@" not in str(m["email"])],
             H.MOUCHARDS["push"])
    # vue admin : qui a invité qui
    c, lst = await appel(R.referral_admin_passes(H.Requete({}, H.entetes_admin()))) if hasattr(R, "referral_admin_passes") else (None, None)
    if c == 200:
        _items = lst.get("items") or lst.get("passes") or []
        _p1 = [i for i in _items if (i.get("chain") or {}).get("parent_pass_id") == d0["id"]]
        verifier("8q. vue admin : P1 expose chain.parent_pass_id/depth", bool(_p1) and _p1[0]["chain"]["depth"] == 1, str(_items)[:300])


# ═══════════════════════════════════════════════════════════════════════════
# 9. Ordre inversé  /  10. Anti-boucle
# ═══════════════════════════════════════════════════════════════════════════
async def partie_ordre_inverse_anti_boucle():
    base, occ, p0 = await depart()
    t0 = p0["share_token"]
    (ea, ta, _), (eb, tb, _) = ident(1), ident(2)
    t1, _ = await preparer_et_partager(t0)       # A partage P1 mais NE s'inscrit PAS
    t2, _ = await preparer_et_partager(t1)       # B partage P2
    H.MOUCHARDS["push"][:] = []
    H.MOUCHARDS["email_parrain"][:] = []
    c, jb = await rejoindre(t1, 2)
    d1 = doc_par_tok(base, t1)
    verifier("9. B rejoint P1 (A non inscrit) -> 200, P1 friend_registered, blocked_reason parrain_non_inscrit",
             c == 200 and d1["status"] == "friend_registered" and d1["blocked_reason"] == "parrain_non_inscrit"
             and jb.get("status") == "friend_registered", (c, d1["status"], d1.get("blocked_reason"), str(jb)[:200]))
    verifier("9b. AUCUN push / e-mail vers une adresse « chaine-en-attente: »",
             not [m for m in H.MOUCHARDS["push"] if PREFIXE_ATTENTE in str(m["email"])]
             and d1["id"] not in H.MOUCHARDS["email_parrain"], (H.MOUCHARDS["push"], H.MOUCHARDS["email_parrain"]))
    verifier("9c. B a sa place (1 réservation) ; la réponse ne fuit pas l'adresse en attente",
             len(resas_de(base, eb)) == 1 and PREFIXE_ATTENTE not in json.dumps(jb), "")
    # garde réelle (sans mouchard) de _push_parrain / _email_parrain_debloque
    _envois = []

    async def _faux_push(email, *a, **k):
        _envois.append(email)
    _orig_sp = getattr(S, "send_push_by_email", None)
    S.send_push_by_email = _faux_push
    try:
        await _ORIG_PUSH_PARRAIN(PREFIXE_ATTENTE + "x", "t", "c", {})
        await _ORIG_PUSH_PARRAIN("vrai@exemple.test", "t", "c", {})
    finally:
        if _orig_sp is not None:
            S.send_push_by_email = _orig_sp
    _faux_resend = types.ModuleType("resend")
    _mails = []
    _faux_resend.Emails = type("Emails", (), {"send": staticmethod(lambda d: _mails.append(d) or {"id": "x"})})
    _orig_mod = sys.modules.get("resend")
    sys.modules["resend"] = _faux_resend
    os.environ["RESEND_API_KEY"] = "re_banc_v556"
    try:
        _r_mail = await _ORIG_EMAIL_PARRAIN(d1)
    finally:
        os.environ.pop("RESEND_API_KEY", None)
        if _orig_mod is not None:
            sys.modules["resend"] = _orig_mod
        else:
            sys.modules.pop("resend", None)
    verifier("9d. garde réelle : _push_parrain n'envoie rien à « chaine-en-attente:… » (mais envoie à une vraie adresse)",
             _envois == ["vrai@exemple.test"], _envois)
    verifier("9e. garde réelle : _email_parrain_debloque n'écrit pas à un parrain en attente",
             _r_mail is False and not _mails, (_r_mail, _mails))

    # A s'inscrit enfin sur P0 -> P1 se débloque tout seul
    c, ja = await rejoindre(t0, 1)
    d0, d1 = doc_par_tok(base, t0), doc_par_tok(base, t1)
    verifier("9f. A s'inscrit sur P0 -> P1 devient unlocked automatiquement, blocked_reason effacé",
             c == 200 and d1["status"] == "unlocked" and d1.get("blocked_reason") is None
             and d1["sponsor"]["email_norm"] == ea, (c, d1["status"], d1.get("blocked_reason")))
    verifier("9g. la place d'A dans P1 = sa réservation de filleul de P0 (aucun 2e débit)",
             d1["reservations"]["sponsor_id"] == d0["reservations"]["invitee_id"]
             and len(resas_de(base, ea)) == 1 and debits(base, codes_de(base, ea)[0]["code"]) == 1,
             (d1["reservations"], d0["reservations"]))
    verifier("9h. le déblocage différé notifie A (vraie adresse) et jamais l'adresse en attente",
             any(m["email"] == ea and m["data"].get("pass_id") == d1["id"] for m in H.MOUCHARDS["push"])
             and not [m for m in H.MOUCHARDS["push"] if PREFIXE_ATTENTE in str(m["email"])], H.MOUCHARDS["push"])

    # ── 10. anti-boucle ────────────────────────────────────────────────────
    base, occ, p0 = await depart()
    t0 = p0["share_token"]
    t1, _ = await preparer_et_partager(t0)
    c, _ = await rejoindre(t0, 1)                  # A inscrit
    assert c == 200
    t2, _ = await preparer_et_partager(t1)         # le visiteur de P1 a partagé P2
    ea, ta, _ = ident(1)
    avant = etat(base)
    # PAR-1 (A1) : un refus d'IDENTITÉ depuis l'appareil qui a partagé libère sa
    # place d'enfant (annulée, jamais supprimée) ; chaque nouvel essai de cet
    # appareil repart donc de « préparer + partager » (nouvelle enfant).
    c, r = await rejoindre(t1, 1)
    verifier("10. B = A (même e-mail) sur P1 -> 409 auto_parrainage", c == 409 and raison(r) == "auto_parrainage", (c, r))
    verifier("10-lib. PAR-1 : ce refus libère l'enfant P2 de l'appareil (cancelled, parent rouvert)",
             doc_par_tok(base, t2)["status"] == "cancelled"
             and not (doc_par_tok(base, t1).get("chain") or {}).get("shared_at"), doc_par_tok(base, t2)["status"])
    c, r = await rejoindre(t1, 5, tel=ta)
    verifier("10b. B = A (même téléphone, autre e-mail) sur P1 -> 409 auto_parrainage",
             c == 409 and raison(r) == "auto_parrainage", (c, r))
    await preparer_et_partager(t1)
    c, r = await rejoindre(t1, 5, email=H.PARRAIN_EMAIL, tel=ident(5)[1])
    verifier("10c. B = Léa (parrain racine, par e-mail) sur P1 -> 409 auto_parrainage",
             c == 409 and raison(r) == "auto_parrainage", (c, r))
    await preparer_et_partager(t1)
    c, r = await rejoindre(t1, 5, tel=H.PARRAIN_TEL)
    verifier("10d. B = Léa (par téléphone, autre e-mail) sur P1 -> 409 auto_parrainage",
             c == 409 and raison(r) == "auto_parrainage", (c, r))
    _sans_passes = lambda e: {k: v for k, v in e.items() if k != "passes"}  # noqa: E731
    verifier("10e. aucune écriture laissée par ces refus (pas d'invité, ni code, ni résa, ni verrou)",
             _sans_passes(etat(base)) == _sans_passes(avant) and doc_par_tok(base, t1)["invitee"] is None,
             (etat(base), avant))
    # plus loin dans la chaîne : C = A sur P2
    t2, _ = await preparer_et_partager(t1)
    c, _ = await rejoindre(t1, 2)                  # B inscrit sur P1
    t3, _ = await preparer_et_partager(t2)
    avant = etat(base)
    c, r = await rejoindre(t2, 1)
    verifier("10f. C = A (grand-parrain, 2 maillons plus haut) sur P2 -> 409 auto_parrainage, rien écrit",
             c == 409 and raison(r) == "auto_parrainage" and etat(base) == avant, (c, r))
    await preparer_et_partager(t2)
    c, r = await rejoindre(t2, 6, email=H.PARRAIN_EMAIL.upper(), tel=ident(6)[1])
    verifier("10g. C = Léa (racine, casse différente) sur P2 -> 409 auto_parrainage", c == 409 and raison(r) == "auto_parrainage", (c, r))

    # A s'inscrivant sur P0 avec l'identité de B déjà inscrit sur P1
    base, occ, p0 = await depart()
    t0 = p0["share_token"]
    t1, _ = await preparer_et_partager(t0)
    t2, _ = await preparer_et_partager(t1)
    c, _ = await rejoindre(t1, 2)                  # B inscrit (A pas encore)
    avant = etat(base)
    c, r = await rejoindre(t0, 2)
    verifier("10h. inscription sur P0 avec l'identité de B (déjà filleul de P1) -> 409 auto_parrainage, rien écrit",
             c == 409 and raison(r) == "auto_parrainage" and etat(base) == avant
             and doc_par_tok(base, t0)["invitee"] is None, (c, r))
    c, r = await rejoindre(t0, 7, tel=ident(2)[1])
    verifier("10i. idem par le téléphone de B (autre e-mail) -> 409 auto_parrainage",
             c == 409 and raison(r) == "auto_parrainage", (c, r))


# ═══════════════════════════════════════════════════════════════════════════
# 11. Double récompense  /  12. chaîne fantôme
# ═══════════════════════════════════════════════════════════════════════════
async def partie_double_recompense_fantome():
    base, occ, p0 = await depart()
    t0 = p0["share_token"]
    t1, _ = await preparer_et_partager(t0)
    c, _ = await rejoindre(t0, 1)
    ea = ident(1)[0]
    avant = etat(base)
    n_pay = len(H.MOUCHARDS["paiements"])
    c, j = await rejoindre(t0, 1)
    c2, j2 = await rejoindre(t0, 1, email=ea.upper())
    verifier("11. rejouer le join (même e-mail, casse différente) -> 200 idempotent, aucun 2e code/réservation/crédit",
             c == c2 == 200 and j.get("status") == "unlocked" and etat(base) == avant
             and len(H.MOUCHARDS["paiements"]) == n_pay, (c, c2, etat(base), avant))
    # rejouer le partage 5 fois
    shared_at = doc_par_tok(base, t0)["chain"]["shared_at"]
    n_passes = len(base["referral_passes"].docs)
    for _ in range(5):
        await partager(t0)
    d0 = doc_par_tok(base, t0)
    verifier("11b. /chain/share rejoué 5 fois : un seul shared_at (inchangé), un seul évènement chain_shared, 0 pass en plus",
             d0["chain"]["shared_at"] == shared_at
             and sum(1 for e in d0.get("events", []) if e.get("type") == E.EVENEMENT_CHAINE_PARTAGEE) == 1
             and len(base["referral_passes"].docs) == n_passes, (d0["chain"], len(base["referral_passes"].docs)))
    # unlock de P1 : jamais une 2e séance pour A ; rejoin B idempotent
    t2, _ = await preparer_et_partager(t1)
    code_a = codes_de(base, ea)[0]["code"]
    c, jb = await rejoindre(t1, 2)
    avant = etat(base)
    c2, jb2 = await rejoindre(t1, 2)
    verifier("11c. unlock de P1 : A n'est débité qu'UNE fois (seance_mouvements), rejoin de B idempotent",
             debits(base, code_a) == 1 and c2 == 200 and etat(base) == avant
             and jb2.get("status") == "unlocked", (debits(base, code_a), c2, etat(base), avant))
    sub_a = [s for s in base["subscriptions"].docs if s.get("code") == code_a][0]
    verifier("11d. le forfait d'essai d'A n'a jamais été débité sous zéro",
             (sub_a.get("remaining_sessions") or 0) >= 0 and (sub_a.get("used_sessions") or 0) <= (sub_a.get("total_sessions") or 1),
             {k: sub_a.get(k) for k in ("remaining_sessions", "used_sessions", "total_sessions")})

    # même filleul sur deux pass de la même séance (autre racine)
    base["subscriptions"].docs.append({
        "id": "sub-marc", "code": "BASS-DUO-02", "email": "marc.parrain@exemple.test", "name": "Marc Parrain",
        "whatsapp": "+41 79 300 40 50", "offer_name": "Pack 10", "offer_id": "pack-10", "total_sessions": 10,
        "used_sessions": 7, "remaining_sessions": 3, "expires_at": base["subscriptions"].docs[0]["expires_at"],
        "status": "active", "coach_id": "", "payment_method": "card", "total_paid": 250})
    base["discount_codes"].docs.append({
        "id": "code-marc", "code": "BASS-DUO-02", "name": "Marc Parrain", "assignedEmail": "marc.parrain@exemple.test",
        "active": True, "maxUses": 10, "used": 7, "coach_id": "", "payment_method": "card", "total_paid": 250,
        "stripe_amount": 250})
    tok_marc = H.jeton_espace(base, code="BASS-DUO-02", email="marc.parrain@exemple.test")
    c, pm = await H.creer_pass(base, occ, tok=tok_marc)
    tm = pm.get("share_token")
    await preparer_et_partager(tm)
    eb = ident(2)[0]
    avant = etat(base)
    c, r = await rejoindre(tm, 2)
    verifier("11e. B (déjà filleul de P1 sur cette séance) rejoint un 2e pass de la même séance -> refusé (409), rien écrit",
             c == 409 and etat(base) == avant and doc_par_tok(base, tm)["invitee"] is None
             and len(codes_de(base, eb)) == 1, (c, r))
    c, r = await rejoindre(tm, 8, tel=ident(2)[1])
    verifier("11f. autre e-mail mais téléphone de B -> refusé par le verrou d'essai réel (ESSAI-1), aucun 2e essai",
             c in (409, 403) and doc_par_tok(base, tm)["invitee"] is None and not codes_de(base, ident(8)[0]),
             (c, r, raison(r)))

    # ── 12. chaîne fantôme ─────────────────────────────────────────────────
    base, occ, p0 = await depart()
    t0 = p0["share_token"]
    c, r = await chaine(t0)
    t1 = r["child"]["share_token"]              # P1, A non inscrit
    c, r = await chaine(t1)
    t2 = r["child"]["share_token"]              # P2, B non inscrit
    c3, r3 = await chaine(t2)
    t3 = (r3.get("child") or {}).get("share_token")   # P3, C non inscrit
    verifier("12. P1, P2, P3 créés sans que personne ne s'inscrive (2 maillons en attente tolérés)",
             c3 == 201 and t3, (c3, r3))
    n = len(base["referral_passes"].docs)
    c4, r4 = await chaine(t3)
    verifier("12b. 4e maillon depuis P3 -> 409 X-Refus-Raison: chaine_en_attente, aucun pass créé",
             c4 == 409 and raison(r4) == "chaine_en_attente" and len(base["referral_passes"].docs) == n, (c4, r4))
    # une fois A inscrit, la chaîne peut repartir
    await partager(t0)
    c, _ = await rejoindre(t0, 1)
    c5, r5 = await chaine(t3)
    verifier("12c. dès qu'un maillon amont s'inscrit (A), le 4e maillon est possible (201)",
             c == 200 and c5 == 201, (c, c5, r5))


# ═══════════════════════════════════════════════════════════════════════════
# 13. Séance
# ═══════════════════════════════════════════════════════════════════════════
async def partie_seance():
    base, occ, p0 = await depart()
    t0 = p0["share_token"]
    c, g0 = await pub(t0)
    occs = [o for o in (g0.get("occurrences") or []) if (o.get("occurrence") if isinstance(o, dict) else o) != occ]
    if not occs:
        verifier("13. (préalable) le cours propose une 2e occurrence", False, g0.get("occurrences"))
        return
    occ2 = occs[0].get("occurrence") if isinstance(occs[0], dict) else occs[0]
    c, r = await chaine(t0)
    t1 = r["child"]["share_token"]
    carte_avant = r["child"]["card_url"]
    d0 = doc_par_tok(base, t0)
    c, x = await appel(R.referral_changer_seance(t0, req({"occurrence": occ2, "version": E.version_pass(d0)})))
    d0, d1 = doc_par_tok(base, t0), doc_par_tok(base, t1)
    verifier("13. A change la séance de P0 (PATCH public) -> 200", c == 200 and d0["occurrence"] == occ2, (c, str(x)[:200]))
    c, pv = await apercu(t0)
    verifier("13b. P1 suit : même jeton, occurrence et expires_at mis à jour, card_url changée",
             d1["share_token"] == t1 and d1["occurrence"] == occ2 and d1["expires_at"] == occ2
             and pv["child"]["card_url"] != carte_avant and pv["child"]["occurrence"] == occ2,
             (d1["occurrence"], d1["expires_at"], pv["child"].get("card_url"), carte_avant))
    c, g1 = await pub(t1)
    c, x = await appel(R.referral_changer_seance(t1, req({"occurrence": occ, "version": g1.get("version")})))
    verifier("13c. B tente de changer la séance de P1 -> 409 (liée à la séance de son parrain)",
             c == 409 and doc_par_tok(base, t1)["occurrence"] == occ2, (c, x))
    verifier("13d. GET public de P1 : aucune autre séance proposée (occurrences vide)",
             g1.get("occurrences") == [], g1.get("occurrences"))
    # B rejoint P1 -> la séance de P0 est figée
    await preparer_et_partager(t0)
    await preparer_et_partager(t1)
    c, jb = await rejoindre(t1, 2)
    verifier("13e. (préalable) B rejoint P1 sur la nouvelle séance", c == 200, (c, str(jb)[:200]))
    d0 = doc_par_tok(base, t0)
    c, x = await appel(R.referral_changer_seance(t0, req({"occurrence": occ, "version": E.version_pass(d0)})))
    verifier("13f. B a rejoint P1 : changer la séance de P0 (porte publique) -> 409, rien ne bouge",
             c == 409 and doc_par_tok(base, t0)["occurrence"] == occ2 and doc_par_tok(base, t1)["occurrence"] == occ2, (c, x))
    c, x = await appel(R.referral_changer_seance(p0["id"], H.req_parrain(
        base, {"occurrence": occ, "version": E.version_pass(doc_par_tok(base, t0))})))
    verifier("13g. idem par la porte du parrain (Léa, jeton d'espace) -> 409",
             c == 409 and doc_par_tok(base, t0)["occurrence"] == occ2, (c, x))

    # ── 13h. la séance du parent change alors que la chaîne a DEUX maillons
    # non rejoints (P1 et P2) : tout ce qui est en aval doit suivre.
    base, occ, p0 = await depart()
    t0 = p0["share_token"]
    c, r = await chaine(t0)
    t1 = r["child"]["share_token"]
    c, r = await chaine(t1)
    t2 = r["child"]["share_token"]
    d0 = doc_par_tok(base, t0)
    c, x = await appel(R.referral_changer_seance(t0, req({"occurrence": occ2, "version": E.version_pass(d0)})))
    occs = [doc_par_tok(base, t)["occurrence"] for t in (t0, t1, t2)]
    verifier("13h. changement de séance de P0 : l'enfant P1 ET le petit-enfant P2 (non rejoints) suivent",
             c == 200 and occs == [occ2, occ2, occ2], (c, occs))
    # conséquence métier si P2 reste sur l'ancienne séance
    await partager(t0)
    await partager(t1)
    c_a, _ = await rejoindre(t0, 1)
    c_b, _ = await rejoindre(t1, 2)
    await preparer_et_partager(t2)
    eb = ident(2)[0]
    code_b = (codes_de(base, eb) or [{}])[0].get("code")
    c_c, jc = await rejoindre(t2, 3)
    d2 = doc_par_tok(base, t2)
    verifier("13i. …et C rejoint P2 sur la MÊME séance que B (P2 unlocked avec la place de filleul de B, aucun 2e débit)",
             c_a == c_b == c_c == 200 and d2["status"] == "unlocked" and d2["occurrence"] == occ2
             and debits(base, code_b) == 1 and len(resas_de(base, eb)) == 1,
             {"codes": (c_a, c_b, c_c), "P2": (d2["status"], d2.get("blocked_reason"), d2["occurrence"]),
              "occ_B": [r_.get("datetime") for r_ in resas_de(base, eb)], "debits_B": debits(base, code_b)})


# ═══════════════════════════════════════════════════════════════════════════
# CORRECTIFS D'AUDIT (coordinateur) : clé d'appareil, pass fermé, version du
# parent, séance du parrain lié, plafond de partages, suivi d'offre, reprise
# de la liaison.
# ═══════════════════════════════════════════════════════════════════════════
async def partie_correctifs_audit():
    # ── C1. /chain/share exige X-Chain-Key ────────────────────────────────
    base, occ, p0 = await depart()
    t0 = p0["share_token"]
    c, r = await chaine(t0)
    t1 = r["child"]["share_token"]
    n_inv = len(base["referral_invitations"].docs)
    c1, x1 = await partager(t0, cle=None)
    c2, x2 = await partager(t0, cle="pas-la-bonne-cle")
    d0 = doc_par_tok(base, t0)
    verifier("C1. /chain/share SANS clé -> 403 invitation_autre_appareil",
             c1 == 403 and raison(x1) == "invitation_autre_appareil", (c1, x1))
    verifier("C1b. /chain/share mauvaise clé -> 403 invitation_autre_appareil ; rien écrit (ni shared_at, ni journal, ni version d'aperçu)",
             c2 == 403 and raison(x2) == "invitation_autre_appareil"
             and not (d0.get("chain") or {}).get("shared_at")
             and len(base["referral_invitations"].docs) == n_inv
             and not doc_par_tok(base, t1).get("preview_version"), (c2, x2))
    # ── C4. créer / partager n'incrémente pas la version du parent ────────
    v_avant = E.version_pass(doc_par_tok(base, t0))
    c3, _ = await partager(t0)
    await partager(t0)
    await chaine(t0)
    verifier("C4. créer puis partager l'enfant ne change pas la `version` du parent (pas de 409 conflit_version côté page)",
             c3 == 200 and E.version_pass(doc_par_tok(base, t0)) == v_avant == E.version_pass(p0) + 0
             or (c3 == 200 and E.version_pass(doc_par_tok(base, t0)) == v_avant),
             (v_avant, E.version_pass(doc_par_tok(base, t0))))
    # ── C2. le JOIN exige X-Chain-Key ─────────────────────────────────────
    avant = etat(base)
    c1, x1 = await rejoindre(t0, 1, cle=None)
    c2, x2 = await rejoindre(t0, 1, cle="cle-dun-tiers")
    verifier("C2. join après partage SANS clé -> 403 invitation_autre_appareil, rien écrit",
             c1 == 403 and raison(x1) == "invitation_autre_appareil" and etat(base) == avant
             and doc_par_tok(base, t0)["invitee"] is None, (c1, x1))
    verifier("C2b. join avec une mauvaise clé -> 403, rien écrit", c2 == 403 and etat(base) == avant, (c2, x2))
    # la clé d'un AUTRE maillon ne sert pas
    c, r_autre = await chaine(t1)
    c3, x3 = await rejoindre(t0, 1, cle=r_autre.get("edit_key"))
    verifier("C2c. la clé d'une AUTRE invitation (enfant de P1) n'ouvre pas le join de P0 -> 403",
             c3 == 403 and etat(base)["verrous"] == avant["verrous"], (c3, x3))
    c4, x4 = await rejoindre(t0, 1)
    verifier("C2d. join avec la bonne clé -> 200", c4 == 200 and x4.get("status") == "unlocked", (c4, str(x4)[:200]))
    c5, x5 = await rejoindre(t0, 1, cle=None)
    verifier("C2e. rejeu idempotent du MÊME filleul sans clé -> 200 (aucun nouvel octroi)",
             c5 == 200 and len(codes_de(base, ident(1)[0])) == 1, (c5, x5))

    base_v, occ_v, p0_v = await depart()
    c, g = await pub(p0_v["share_token"])
    v_lue = g.get("version")
    await preparer_et_partager(p0_v["share_token"])
    _occs = [o.get("occurrence") if isinstance(o, dict) else o for o in (g.get("occurrences") or [])]
    _autre = [o for o in _occs if o != occ_v]
    if _autre:
        c, x = await appel(R.referral_changer_seance(p0_v["share_token"], req({"occurrence": _autre[0], "version": v_lue})))
        verifier("C4b. la page qui a lu la version AVANT de préparer/partager peut encore changer la séance (200)",
                 c == 200, (c, x))


    # ── C3. POST /chain sur un pass déjà rejoint / non ouvert ─────────────
    base, occ = H.base_de_depart(chaine=False)
    _, pj = await H.creer_pass(base, occ)
    c, _ = await rejoindre(pj["share_token"], 1, cle=None)
    base["feature_flags"].docs[0]["parrainage_chaine_enabled"] = True
    n = len(base["referral_passes"].docs)
    c, x = await chaine(pj["share_token"])
    verifier("C3. POST /chain sur un pass DÉJÀ rejoint -> 409 pass_ferme, aucune enfant orpheline",
             c == 409 and raison(x) == "pass_ferme" and len(base["referral_passes"].docs) == n, (c, x))
    base, occ, p0 = await depart()
    tok_esp = H.jeton_espace(base)
    c, _ = await appel(R.referral_annuler(p0["id"], H.req_parrain(base, tok=tok_esp)))
    c2, x = await chaine(p0["share_token"])
    verifier("C3b. POST /chain sur un pass annulé -> 410 (ou 409), aucune enfant",
             c == 200 and c2 in (409, 410) and len(base["referral_passes"].docs) == 1, (c, c2, x))

    # ── C5. le parrain LIÉ ne change pas la séance d'un pass de chaîne ────
    base, occ, p0 = await depart()
    t0 = p0["share_token"]
    c, g0 = await pub(t0)
    t1, _ = await preparer_et_partager(t0)
    await rejoindre(t0, 1)
    ea = ident(1)[0]
    code_a = codes_de(base, ea)[0]["code"]
    tok_a = H.jeton_espace(base, code=code_a, email=ea)
    _occs = [o.get("occurrence") if isinstance(o, dict) else o for o in (g0.get("occurrences") or [])]
    _autre = [o for o in _occs if o != occ]
    d1 = doc_par_tok(base, t1)
    c, x = await appel(R.referral_changer_seance(d1["id"], H.req_parrain(
        base, {"occurrence": (_autre or [occ])[0], "version": E.version_pass(d1)}, tok=tok_a)))
    verifier("C5. A (parrain lié de P1, jeton d'espace) change la séance de P1 -> 409, P1 reste sur la séance de P0",
             c == 409 and doc_par_tok(base, t1)["occurrence"] == occ, (c, x))
    c, x = await appel(R.referral_changer_seance(t1, H.req_parrain(
        base, {"occurrence": (_autre or [occ])[0], "version": E.version_pass(d1)}, tok=tok_a)))
    verifier("C5b. idem en visant P1 par son share_token -> 409", c == 409, (c, x))

    # ── C6. plafond de partages (PARTAGES_MAX) ────────────────────────────
    base, occ, p0 = await depart()
    t0 = p0["share_token"]
    c, r = await chaine(t0)
    t1 = r["child"]["share_token"]
    urls = []
    for _ in range(E.PARTAGES_MAX):
        c, x = await partager(t0, "copy")
        urls.append(x["child"]["share_url"])
    d1 = doc_par_tok(base, t1)
    n_inv, n_evt, pv = len(base["referral_invitations"].docs), len(d1.get("events", [])), d1.get("preview_version")
    verifier("C6. %d partages : %d URL toutes différentes, preview_version = %d" % (E.PARTAGES_MAX, E.PARTAGES_MAX, E.PARTAGES_MAX),
             len(set(urls)) == E.PARTAGES_MAX and pv == E.PARTAGES_MAX, (len(set(urls)), pv))
    reps = [await partager(t0, "whatsapp") for _ in range(3)]
    d1 = doc_par_tok(base, t1)
    verifier("C6b. au-delà du plafond : partage accepté (200, shared:true) mais RIEN écrit (journal, évènements, version d'aperçu)",
             all(c_ == 200 and x_.get("shared") is True for c_, x_ in reps)
             and len(base["referral_invitations"].docs) == n_inv and len(d1.get("events", [])) == n_evt
             and d1.get("preview_version") == pv and len(base["referral_passes"].docs) == 2,
             (len(base["referral_invitations"].docs), n_inv, len(d1.get("events", [])), n_evt, d1.get("preview_version")))
    verifier("C6c. au-delà du plafond : la share_url rendue reste une URL valide et stable (même jeton)",
             len({x_["child"]["share_url"] for _, x_ in reps}) == 1
             and reps[0][1]["child"]["share_token"] == t1, [x_["child"]["share_url"] for _, x_ in reps])
    c, x = await rejoindre(t0, 1)
    verifier("C6d. le visiteur plafonné peut toujours s'inscrire (200)", c == 200, (c, str(x)[:200]))

    # ── C8. changement d'offre du parent APRÈS join : l'enfant suit ───────
    base, occ, p0 = await depart()
    t0 = p0["share_token"]
    t1, _ = await preparer_et_partager(t0)
    await rejoindre(t0, 1)
    t2, _ = await preparer_et_partager(t1)
    c, jb = await rejoindre(t1, 2)
    ea = ident(1)[0]
    d0, d1 = doc_par_tok(base, t0), doc_par_tok(base, t1)
    ancien_rid, ancien_code = d0["reservations"]["invitee_id"], d0["invitee_access_code"]
    verifier("C8-pré. P1 unlocked sur la place d'A (P0)", d1["status"] == "unlocked"
             and d1["reservations"]["sponsor_id"] == ancien_rid, (d1["status"], d1["reservations"]))
    tok_esp = H.jeton_espace(base)
    c, x = await H.patch_offre(base, p0["id"], H.OFFRE_B, E.version_pass(d0), tok=tok_esp)
    d0, d1 = doc_par_tok(base, t0), doc_par_tok(base, t1)
    nouveau_rid, nouveau_code = d0["reservations"]["invitee_id"], d0["invitee_access_code"]
    verifier("C8. Léa change l'offre de P0 après le join d'A -> 200, nouvelle réservation + nouveau code pour A",
             c == 200 and nouveau_rid and nouveau_rid != ancien_rid and nouveau_code != ancien_code, (c, str(x)[:300]))
    verifier("C8b. P1 suit : reservations.sponsor_id = nouvelle réservation d'A, sponsor.subscription_code = nouveau code",
             d1["reservations"]["sponsor_id"] == nouveau_rid and d1["sponsor"]["subscription_code"] == nouveau_code
             and d1["reservations"].get("sponsor_code") == (await base["reservations"].find_one({"id": nouveau_rid}) or {}).get("reservationCode"),
             (d1["reservations"], d1["sponsor"].get("subscription_code"), nouveau_rid, nouveau_code))
    c, g1 = await pub(t1)
    c2, jb2 = await rejoindre(t1, 2)
    _statuts = []
    for t_ in jb2.get("tickets", []):
        _r_ = await base["reservations"].find_one({"reservationCode": t_["reservationCode"]})
        _statuts.append((_r_.get("status") or "vivante") if _r_ else "ABSENTE")
    verifier("C8c. P1 reste unlocked et ses billets pointent vers une réservation VIVANTE d'A",
             g1.get("status") == "unlocked" and c2 == 200 and len(jb2.get("tickets", [])) == 2
             and all(_st not in ("cancelled", "ABSENTE") for _st in _statuts), (g1.get("status"), jb2.get("tickets"), _statuts))
    # enfant lié mais pas encore rejoint : seul le code suit
    base, occ, p0 = await depart()
    t0 = p0["share_token"]
    t1, _ = await preparer_et_partager(t0)
    await rejoindre(t0, 1)
    d0 = doc_par_tok(base, t0)
    tok_esp = H.jeton_espace(base)
    c, x = await H.patch_offre(base, p0["id"], H.OFFRE_B, E.version_pass(d0), tok=tok_esp)
    d0, d1 = doc_par_tok(base, t0), doc_par_tok(base, t1)
    verifier("C8d. enfant lié NON rejoint : son sponsor.subscription_code suit le nouveau code d'A",
             c == 200 and d1["sponsor"]["subscription_code"] == d0["invitee_access_code"], (c, d1["sponsor"]))
    t2, _ = await preparer_et_partager(t1)
    c, jb = await rejoindre(t1, 2)
    d1 = doc_par_tok(base, t1)
    verifier("C8e. …puis B rejoint P1 : unlocked sur la NOUVELLE réservation d'A, aucun débit hors essai",
             c == 200 and d1["status"] == "unlocked" and d1["reservations"]["sponsor_id"] == d0["reservations"]["invitee_id"],
             (c, d1["status"], d1.get("blocked_reason"), d1["reservations"]))

    # ── C9. reprise d'une liaison manquée : join idempotent / confirm ─────
    async def _chaine_liaison_manquee():
        base, occ, p0 = await depart()
        t0 = p0["share_token"]
        t1, _ = await preparer_et_partager(t0)
        await rejoindre(t0, 1)
        d1 = doc_par_tok(base, t1)
        # simule une liaison ratée (panne entre le join et `_lier_enfant`)
        d1["sponsor"] = {"email_norm": PREFIXE_ATTENTE + doc_par_tok(base, t0)["id"], "name": "", "whatsapp_norm": None,
                         "subscription_code": None, "terms_accepted": False, "pending": True}
        return base, t0, t1
    base, t0, t1 = await _chaine_liaison_manquee()
    c, _ = await rejoindre(t0, 1, cle=None)
    d1 = doc_par_tok(base, t1)
    verifier("C9. liaison manquée : le rejeu idempotent du join d'A la reprend (P1 lié à A)",
             c == 200 and d1["sponsor"].get("pending") is False and d1["sponsor"]["email_norm"] == ident(1)[0], (c, d1["sponsor"]))
    # confirm : B a déjà rejoint P1, bloqué (parrain non inscrit) ; qui peut appeler /confirm ?
    base, t0, t1 = await _chaine_liaison_manquee()
    t2, _ = await preparer_et_partager(t1)
    c, _ = await rejoindre(t1, 2)
    d1 = doc_par_tok(base, t1)
    ok_pre = d1["status"] == "friend_registered" and d1.get("blocked_reason") == "parrain_non_inscrit"
    ea = ident(1)[0]
    code_a = codes_de(base, ea)[0]["code"]
    tok_a = H.jeton_espace(base, code=code_a, email=ea)
    c_a, x_a = await appel(R.referral_confirmer(d1["id"], H.req_parrain(base, {}, tok=tok_a)))
    tok_lea = H.jeton_espace(base)
    c_l, x_l = await appel(R.referral_confirmer(doc_par_tok(base, t0)["id"], H.req_parrain(base, {}, tok=tok_lea)))
    d1 = doc_par_tok(base, t1)
    verifier("C9b. liaison manquée + B déjà inscrit sur P1 : un /confirm (A sur P1, ou Léa sur P0) reprend la liaison et débloque P1",
             ok_pre and d1["sponsor"].get("pending") is False and d1["status"] == "unlocked",
             {"pré": ok_pre, "confirm_A_sur_P1": c_a, "confirm_Lea_sur_P0": c_l,
              "P1": (d1["status"], d1.get("blocked_reason"), d1["sponsor"].get("email_norm"))})
    c, _ = await rejoindre(t0, 1, cle=None)
    d1 = doc_par_tok(base, t1)
    verifier("C9c. (même cas) le rejeu idempotent du join d'A reprend la liaison ET débloque P1 (sans 2e débit)",
             c == 200 and d1["status"] == "unlocked" and debits(base, code_a) == 1, (c, d1["status"], d1.get("blocked_reason")))

    # ── C10. page OG : Vary: User-Agent ───────────────────────────────────
    c, h, rr = await page(t1, "1", ua="WhatsApp/2.24")
    _vary = {k.lower(): v for k, v in dict(rr.headers).items()}.get("vary", "")
    verifier("C10. page d'aperçu : en-tête Vary contient User-Agent", "user-agent" in _vary.lower(), _vary)


# ═══════════════════════════════════════════════════════════════════════════
# 14. Anciens liens  /  15. OG HTML  /  16. santé de l'aperçu  /  17. fuites
# ═══════════════════════════════════════════════════════════════════════════
def _moteur_avant_v556():
    """Le moteur tel qu'il était AVANT V556 (HEAD), pour prouver que la
    version de carte d'un ancien pass n'a pas bougé."""
    try:
        src = subprocess.check_output(["git", "-C", os.path.dirname(ICI), "show", "HEAD:api/routes/referral_engine.py"],
                                      stderr=subprocess.DEVNULL)
    except Exception:  # noqa: BLE001
        return None
    d = tempfile.mkdtemp(prefix="banc_v556_moteur_")
    chemin = os.path.join(d, "referral_engine_avant_v556.py")
    with open(chemin, "wb") as f:
        f.write(src)
    spec = importlib.util.spec_from_file_location("referral_engine_avant_v556", chemin)
    m = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(m)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return m


async def partie_anciens_liens_og():
    # ── 14. anciens liens ──────────────────────────────────────────────────
    base, occ = H.base_de_depart(chaine=False)
    c, p = await H.creer_pass(base, occ)
    tok = p["share_token"]
    d = doc_par_tok(base, tok)
    verifier("14. ancien pass : ni chain ni preview_version ; share_url SANS ?v",
             "chain" not in d and "preview_version" not in d
             and p.get("share_url") == "%s/api/share/duo/%s" % (FRONT, tok), (p.get("share_url"), list(d)))
    c, h, _ = await page(tok)
    c2, o, t = await carte(tok, E.version_carte(d))
    verifier("14b. GET /api/share/duo/<token> (sans v) -> 200 ; carte -> 200 image/jpeg",
             c == 200 and c2 == 200 and t.startswith("image/jpeg"), (c, c2, t))
    M0 = _moteur_avant_v556()
    if M0 is None:
        verifier("14c. version_carte identique au moteur d'avant V556 (git HEAD)", False, "git show HEAD indisponible")
    else:
        verifier("14c. version_carte d'un ancien pass INCHANGÉE (= moteur git HEAD d'avant V556)",
                 E.version_carte(d) == M0.version_carte(d) and E.url_carte(FRONT, d) == M0.url_carte(FRONT, d),
                 (E.version_carte(d), M0.version_carte(d)))
        d_inv = dict(d, invitation={"display_name": "Léa", "photo_url": None, "message": "Salut"}, invitation_version=2)
        verifier("14d. idem pour un ancien pass AVEC invitation V551 (url_partage_versionnee et carte inchangées)",
                 E.version_carte(d_inv) == M0.version_carte(d_inv)
                 and E.url_partage_versionnee(FRONT, d_inv) == M0.url_partage_versionnee(FRONT, d_inv),
                 (E.url_partage_versionnee(FRONT, d_inv), M0.url_partage_versionnee(FRONT, d_inv)))
    verifier("14e. version_carte(preview_version=0) == sans le champ ; ≠ avec preview_version=1",
             E.version_carte(dict(d, preview_version=0)) == E.version_carte(d)
             != E.version_carte(dict(d, preview_version=1)), "")
    # la règle s'allume : l'ancien lien passe par le wizard, sans changer de jeton
    base["feature_flags"].docs[0]["parrainage_chaine_enabled"] = True
    c, g = await pub(tok)
    verifier("14f. règle active : l'ancien lien -> chain_required:true, même jeton, join direct refusé (invitation_requise)",
             g.get("chain_required") is True and doc_par_tok(base, tok)["share_token"] == tok
             and (await rejoindre(tok, 1))[1].get("headers", {}).get("X-Refus-Raison") == "invitation_requise", g)
    c, r = await chaine(tok)
    verifier("14g. l'ancien lien peut créer son invitation enfant (201), le parent garde son jeton",
             c == 201 and doc_par_tok(base, tok)["share_token"] == tok, (c, str(r)[:200]))

    # ── 15. OG HTML ────────────────────────────────────────────────────────
    base, occ, p0 = await depart()
    t0 = p0["share_token"]
    c, r = await chaine(t0, {"display_name": "Henri"})
    t1 = r["child"]["share_token"]
    await partager(t0)
    await rejoindre(t0, 1)       # A lié : e-mail/tel/code réels existent sur P1
    c, h, _ = await page(t1, "2", ua="WhatsApp/2.24.1 A")
    o = og(h)
    requis = ("og:title", "og:description", "og:image", "og:image:secure_url", "og:image:type",
              "og:image:width", "og:image:height", "og:url", "og:type")
    verifier("15. la page brute contient toutes les balises OG requises",
             c == 200 and all(o.get(k) for k in requis), [k for k in requis if not o.get(k)])
    verifier("15b. og:image absolue https, 1200×630, image/jpeg, secure_url = og:image",
             o.get("og:image", "").startswith("https://") and o.get("og:image:width") == "1200"
             and o.get("og:image:height") == "630" and o.get("og:image:type") == "image/jpeg"
             and o.get("og:image:secure_url") == o.get("og:image"), o)
    for ua in ("WhatsApp/2.24.1 A", "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"):
        c, h2, _ = await page(t1, "2", ua=ua)
        verifier("15c. UA robot « %s » -> PAS de meta refresh" % ua[:22],
                 c == 200 and 'http-equiv="refresh"' not in h2, "")
    c, h3, _ = await page(t1, "2")
    verifier("15d. UA navigateur -> meta refresh vers /duo/<token>",
             c == 200 and ('http-equiv="refresh" content="0;url=%s/duo/%s"' % (FRONT, t1)) in h3, "")
    for v in ("abc", "99999999", "1<script>", "-3"):
        c, h4, _ = await page(t1, v, ua="WhatsApp/2.24")
        verifier("15e. ?v=%r -> og:url nettoyée (sans v), rien de brut dans le HTML" % v,
                 c == 200 and og(h4).get("og:url") == "%s/api/share/duo/%s" % (FRONT, t1) and "<script" not in h4,
                 og(h4).get("og:url"))
    ea, ta, _ = ident(1)
    code_a = codes_de(base, ea)[0]["code"]
    _tout = h + h3
    _mauvais = [m for m in (ea, chiffres(ta), code_a, H.PARRAIN_EMAIL, chiffres(H.PARRAIN_TEL), H.PARRAIN_CODE,
                            PREFIXE_ATTENTE, doc_par_tok(base, t1)["id"]) if m and m in _tout]
    verifier("15f. aucun e-mail / téléphone / code / placeholder / id interne dans le HTML", not _mauvais, _mauvais)
    # enfant pas encore lié : pas de placeholder non plus
    base2, occ2, p02 = await depart()
    c, r2 = await chaine(p02["share_token"])
    c, h5, _ = await page(r2["child"]["share_token"], "1", ua="WhatsApp/2.24")
    verifier("15g. enfant NON lié : HTML sans « chaine-en-attente: » et sans e-mail",
             c == 200 and PREFIXE_ATTENTE not in h5 and "@" not in h5.split("<body")[0].replace("og:", ""), "")
    r = await S.share_duo_page("jeton-inconnu-v556", req({}, {"user-agent": "WhatsApp/2.24"}), v="1")
    verifier("15h. jeton inconnu -> 302 vers l'accueil", r.status_code == 302 and r.headers.get("location") == FRONT,
             (r.status_code, r.headers.get("location")))

    # ── 16. santé de l'aperçu ──────────────────────────────────────────────
    d1 = doc_par_tok(base, t1)
    b = await S._v556_bilan_apercu(d1)
    ch = b.get("checks") or {}
    verifier("16. _v556_bilan_apercu(child) : ok True, checks tous verts",
             b.get("ok") is True and all(ch.get(k) for k in ("share_page", "og_title", "og_description", "og_image",
                                                             "og_image_https", "image_ok")), b)
    verifier("16b. image_bytes > 0 et ≤ 600 Ko, image/jpeg", 0 < (ch.get("image_bytes") or 0) <= 600 * 1024
             and ch.get("image_type") == "image/jpeg", ch)
    _oct, _typ, _perso = await S._v556_octets_carte(d1)
    im = image(_oct)
    verifier("16c. la carte contrôlée est un JPEG 1200×630 lisible (Pillow), personnalisée",
             im is not None and im.size == (1200, 630) and _perso is True, (im and im.size, _perso))
    bon_html = E.page_apercu_html("T", "D", "https://afroboost.com/x.jpg", "https://afroboost.com/u", "https://afroboost.com/c", robot=True)
    verifier("16d. controle_apercu : HTML + image correcte -> ok True",
             E.controle_apercu(bon_html, _oct, "image/jpeg")["ok"] is True, E.controle_apercu(bon_html, _oct, "image/jpeg"))
    sans_img = E.page_apercu_html("T", "D", "", "https://afroboost.com/u", "https://afroboost.com/c", robot=True)
    verifier("16e. controle_apercu : HTML sans og:image -> ok False",
             E.controle_apercu(sans_img, _oct, "image/jpeg")["ok"] is False, "")
    verifier("16f. controle_apercu : image vide -> ok False",
             E.controle_apercu(bon_html, b"", "image/jpeg")["ok"] is False, "")
    http_img = E.page_apercu_html("T", "D", "http://afroboost.com/x.jpg", "https://afroboost.com/u", "https://afroboost.com/c", robot=True)
    verifier("16g. controle_apercu : og:image en http:// -> ok False",
             E.controle_apercu(http_img, _oct, "image/jpeg")["ok"] is False, "")
    verifier("16h. controle_apercu : octets non-image -> ok False ; image > 600 Ko -> ok False",
             E.controle_apercu(bon_html, b"<html>pas une image</html>", "image/jpeg")["ok"] is False
             and E.controle_apercu(bon_html, b"\xff\xd8\xff" + b"\x00" * (600 * 1024), "image/jpeg")["ok"] is False, "")

    # ── 17. aucune fuite ───────────────────────────────────────────────────
    base, occ, p0 = await depart()
    t0 = p0["share_token"]
    reps = []
    reps.append(("GET public P0", (await pub(t0))[1]))
    c, r = await chaine(t0, {"display_name": "Henri"})
    reps.append(("POST chain", r))
    t1 = r["child"]["share_token"]
    reps.append(("POST chain (idempotent)", (await chaine(t0))[1]))
    reps.append(("PATCH chain", (await chaine_patch(t0, {"message": "Salut"}, r["edit_key"]))[1]))
    reps.append(("POST share", (await partager(t0))[1]))
    reps.append(("GET preview", (await apercu(t0))[1]))
    await rejoindre(t0, 1)
    reps.append(("GET public P1 (parrain lié)", (await pub(t1))[1]))
    reps.append(("GET preview (parrain lié)", (await apercu(t0))[1]))
    t2, _ = await preparer_et_partager(t1)
    reps.append(("join B", (await rejoindre(t1, 2))[1]))
    reps.append(("GET public P1 (rejoint)", (await pub(t1))[1]))
    for nom, rep in reps:
        _x = dict(rep) if isinstance(rep, dict) else rep
        if isinstance(_x, dict):
            _x.pop("edit_key", None)          # capacité voulue, rendue au créateur seulement
        verifier("17. aucune fuite (%s) : ni e-mail, tél., id interne, edit_key_hash, code, placeholder" % nom,
                 not fuite(_x, base) and "id" not in (_x.get("child") or {}) and "id" not in _x,
                 fuite(_x, base))


# ═══════════════════════════════════════════════════════════════════════════
async def partie_interrupteur_super_admin():
    """V556 — l'interrupteur du Super Admin : PUT /feature-flags accepte
    `parrainage_chaine_enabled`, SEULEMENT avec un JWT super-admin signé ; la
    valeur écrite est celle que lit la porte de la chaîne (preuve V310c)."""
    base, occ = H.base_de_depart(chaine=False)
    S.db = base
    try:
        S.FeatureFlagsUpdate(parrainage_chaine_enabled=True)
        _modele = True
    except Exception:  # noqa: BLE001
        _modele = False
    verifier("SA-1. le modèle PUT /feature-flags accepte parrainage_chaine_enabled", _modele)
    c, _ = await H.appel(S.update_feature_flags(S.FeatureFlagsUpdate(parrainage_chaine_enabled=True),
                                                H.Requete({}, {})))
    verifier("SA-2. SANS jeton -> 403 et rien d'écrit", c == 403 and await R._chaine_active() is False, c)
    c, _ = await H.appel(S.update_feature_flags(S.FeatureFlagsUpdate(parrainage_chaine_enabled=True),
                                                H.Requete({}, {"Authorization": "Bearer " + H.jeton_admin("coach.x@exemple.test")})))
    verifier("SA-3. JWT d'un coach NON super-admin -> 403", c == 403 and await R._chaine_active() is False, c)
    c, r = await H.appel(S.update_feature_flags(S.FeatureFlagsUpdate(parrainage_chaine_enabled=True),
                                                H.Requete({}, {"Authorization": "Bearer " + H.jeton_admin(H.ADMIN)})))
    verifier("SA-4. JWT super-admin -> 200, valeur relue true, la porte s'allume",
             c == 200 and (r or {}).get("parrainage_chaine_enabled") is True and await R._chaine_active() is True, (c, r))
    c, r = await H.appel(S.update_feature_flags(S.FeatureFlagsUpdate(parrainage_chaine_enabled=False),
                                                H.Requete({}, {"Authorization": "Bearer " + H.jeton_admin(H.ADMIN)})))
    verifier("SA-5. coupe-circuit : false -> la porte s'éteint (parcours V2)",
             c == 200 and await R._chaine_active() is False, (c, r))
    g = await S.get_feature_flags()
    verifier("SA-6. GET /feature-flags rend parrainage_chaine_enabled", "parrainage_chaine_enabled" in g, g)


def main():
    _tmp = tempfile.mkdtemp(prefix="banc_v556_")
    _orig = S._V413_MEDIA_DIR
    S._V413_MEDIA_DIR = _tmp
    try:
        try:
            asyncio.set_event_loop(asyncio.new_event_loop())
        except Exception:  # noqa: BLE001
            pass
        boucle = asyncio.get_event_loop()
        for partie in (partie_drapeau_porte_routes, partie_partages_successifs, partie_chaine_complete,
                       partie_ordre_inverse_anti_boucle, partie_double_recompense_fantome, partie_seance,
                       partie_anciens_liens_og, partie_correctifs_audit, partie_interrupteur_super_admin):
            try:
                boucle.run_until_complete(partie())
            except Exception as err:  # noqa: BLE001  (banc ROUGE : on le dit, on ne plante pas)
                import traceback
                verifier("PARTIE %s exécutée sans exception" % partie.__name__, False,
                         "%s: %s\n%s" % (type(err).__name__, err, traceback.format_exc()[-1200:]))
    finally:
        S._V413_MEDIA_DIR = _orig
        shutil.rmtree(_tmp, ignore_errors=True)
    ok = sum(1 for _, c, _ in H.RESULTATS if c)
    print("=" * 78)
    print("V556 — PARRAINAGE V3 (chaîne boule de neige) : %d vérifications" % len(H.RESULTATS))
    print("=" * 78)
    for nom, cond, detail in H.RESULTATS:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom,
                               ("" if cond or not detail else "\n         -> " + str(detail)[:900])))
    print("-" * 78)
    print("%d / %d verifications au vert" % (ok, len(H.RESULTATS)))
    return 0 if ok == len(H.RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())
