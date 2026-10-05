"""V574 — « Bon retour [pseudo] » (même appareil) : identité invité GLOBALE + jeton opaque.

- `invites_live` : l'identité de l'invité (pseudo, photo, e-mail, WhatsApp, empreintes
  d'appareils). AUCUN consentement, aucune donnée de coach.
- `chat_participants` reste la RELATION invité ↔ coach (V572/V573, portée du coach).
- Cookie `afb_live_guest` : 32 octets aléatoires, HttpOnly, Secure, SameSite=Lax, posé par
  afroboost.com/api ; seule l'empreinte SHA-256 est en base ; il ne donne AUCUN droit.
- Durée : 180 jours glissants (renouvelés à chaque « Continuer »), plafond 395 jours.
"""
import asyncio
import copy
import hashlib
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_btlive_proprietaire import S, _Coll, COACH_A  # noqa: E402
from test_btlive_invite_contact import _CollContacts  # noqa: E402

COACH_B = "coach-b@exemple.invalid"
CODE_A, CODE_B = "LIVEA-AAAA", "LIVEB-BBBB"
PHOTO = "https://x.supabase.co/storage/v1/object/public/session-media/invites/LIVEA-AAAA/p.jpg"


class _CollId(_CollContacts):
    """invites_live : correspondance sur un élément de tableau (`appareils.h`)."""

    def _ok(self, d, f):
        for k, v in f.items():
            if "." in k and not k.startswith("$"):
                tab, champ = k.split(".", 1)
                if not any(isinstance(e, dict) and e.get(champ) == v for e in (d.get(tab) or [])):
                    return False
            elif not super()._ok(d, {k: v}):
                return False
        return True

    async def insert_one(self, d):
        self.docs[d["id"]] = copy.deepcopy(d)


@pytest.fixture()
def base(monkeypatch):
    monkeypatch.setattr(S, "is_super_admin", lambda e: e == COACH_A)
    import api.routes.tenant_contacts as TC
    monkeypatch.setattr(TC, "is_super_admin", lambda e: e == COACH_A, raising=False)
    fausse = type("DB", (), {})()
    fausse.boosttribe_live = _Coll()
    fausse.boosttribe_live_journal = _CollContacts()
    fausse.chat_participants = _CollContacts()
    fausse.invites_live = _CollId()
    fausse.subscribers = _CollContacts()
    maintenant = datetime.now(timezone.utc).isoformat()
    fausse.boosttribe_live.docs["actuel"] = {"_id": "actuel", "session_code": CODE_A, "host": COACH_A,
                                             "ended": False, "started_at": maintenant}
    fausse.boosttribe_live_journal.docs["b"] = {"event": "started", "session_code": CODE_B, "by": COACH_B, "at": maintenant}
    monkeypatch.setattr(S, "db", fausse)
    S._live_guest_debit.clear()
    return fausse


class Req:
    def __init__(self, corps=None, cookie=None, ip="1.2.3.4"):
        self.corps = corps or {}
        self.cookies = {"afb_live_guest": cookie} if cookie else {}
        self.headers = {"x-forwarded-for": ip}
        self.client = type("C", (), {"host": ip})()

    async def json(self):
        return self.corps


class Rep:
    def __init__(self):
        self.poses, self.effaces = {}, []

    def set_cookie(self, key, value, **kw):
        self.poses[key] = (value, kw)

    def delete_cookie(self, key, **kw):
        self.effaces.append((key, kw))


def run(c):
    return asyncio.new_event_loop().run_until_complete(c)


def appel(fn, *a):
    try:
        return 200, run(fn(*a))
    except S.HTTPException as e:
        return e.status_code, e.detail


CORPS = {"session_code": CODE_A, "pseudo": "Bass", "email": "bass@exemple.ch",
         "whatsapp": "079 123 45 12", "photo_url": PHOTO}


def rejoindre(corps=None, cookie=None):
    rep = Rep()
    st, r = appel(S.live_guest_rejoindre, Req(corps or CORPS, cookie), rep)
    return st, r, rep


def jeton_de(rep):
    return rep.poses["afb_live_guest"][0]


# ── A / B : première participation ────────────────────────────────────────────
def test_A_sans_cookie_moi_401_donc_formulaire_complet(base):
    assert appel(S.live_guest_moi, Req())[0] == 401


def test_B_premiere_participation_cookie_pose_et_securise(base):
    st, r, rep = rejoindre()
    assert st == 200
    valeur, kw = rep.poses["afb_live_guest"]
    assert len(valeur) >= 43                                      # 32 octets en base64url
    assert kw["httponly"] is True and kw["secure"] is True and kw["samesite"] == "lax"
    assert kw["path"] == "/api/live-guest" and 0 < kw["max_age"] <= 180 * 86400
    (f,) = base.chat_participants.docs.values()                    # relation coach V572/V573
    assert "live_afroboost" in f["sources"] and f["lives"][0]["pseudo"] == "Bass"
    (ident,) = base.invites_live.docs.values()
    assert ident["pseudo"] == "Bass" and ident["email"] == "bass@exemple.ch" and ident["whatsapp"] == "+41791234512"


def test_M_jeton_jamais_en_clair_en_base(base):
    _, _, rep = rejoindre()
    t = jeton_de(rep)
    (ident,) = base.invites_live.docs.values()
    assert t not in str(ident)
    assert ident["appareils"][0]["h"] == hashlib.sha256(t.encode()).hexdigest()


def test_identite_globale_sans_donnee_de_coach_ni_consentement(base):
    rejoindre()
    (ident,) = base.invites_live.docs.values()
    interdits = {"marketing_consent", "consent", "tags", "categories", "notes", "coach_id", "campaigns", "contact_type"}
    assert not interdits & set(ident)


# ── C / D / E : retour même appareil ──────────────────────────────────────────
def test_C_D_E_bon_retour_pseudo_photo_coordonnees_masquees_rien_du_coach(base):
    _, _, rep = rejoindre()
    st, vue = appel(S.live_guest_moi, Req(cookie=jeton_de(rep)))
    assert st == 200
    assert vue == {"pseudo": "Bass", "photo_url": PHOTO, "email_masque": "b***@exemple.ch",
                   "whatsapp_masque": "+41 ** *** ** 12"}


# ── F / G : continuer ─────────────────────────────────────────────────────────
def test_F_G_continuer_rattache_sans_doublon_et_tourne_le_jeton(base):
    _, _, rep = rejoindre()
    ancien = jeton_de(rep)
    base.boosttribe_live.docs["actuel"]["session_code"] = "LIVEA-SUIV"
    rep2 = Rep()
    st, vue = appel(S.live_guest_continuer, Req({"session_code": "LIVEA-SUIV"}, ancien), rep2)
    assert st == 200 and vue["pseudo"] == "Bass"
    (f,) = base.chat_participants.docs.values()                    # G : même coach → même fiche
    assert [x["session_code"] for x in f["lives"]] == [CODE_A, "LIVEA-SUIV"]
    nouveau = jeton_de(rep2)
    assert nouveau != ancien
    assert appel(S.live_guest_moi, Req(cookie=ancien))[0] == 401    # N : rotation → ancien invalide
    assert appel(S.live_guest_moi, Req(cookie=nouveau))[0] == 200


# ── H : autre coach ───────────────────────────────────────────────────────────
def test_H_autre_coach_meme_identite_relation_separee_aucune_fuite(base):
    _, _, rep = rejoindre()
    (fa,) = base.chat_participants.docs.values()
    fa.update({"tags": ["vip-A"], "categories": ["cat-A"], "marketing_consent": True, "notes": "privé A"})
    rep2 = Rep()
    st, _ = appel(S.live_guest_continuer, Req({"session_code": CODE_B}, jeton_de(rep)), rep2)
    assert st == 200
    assert len(base.invites_live.docs) == 1                        # même identité globale
    fb = [f for f in base.chat_participants.docs.values() if f.get("coach_id") == COACH_B]
    assert len(fb) == 1 and len(base.chat_participants.docs) == 2   # relation propre à B
    fb = fb[0]
    assert not {"tags", "categories", "notes"} & {k for k, v in fb.items() if v}
    assert fb.get("marketing_consent") is False
    assert fb["lives"][0]["coach"] == COACH_B
    assert fa["tags"] == ["vip-A"] and fa["marketing_consent"] is True   # A intact


# ── I / J : ce n'est pas moi / oublier ────────────────────────────────────────
def test_I_J_oublier_revoque_cet_appareil_et_efface_le_cookie(base):
    _, _, rep = rejoindre()
    t = jeton_de(rep)
    rep2 = Rep()
    assert appel(S.live_guest_oublier, Req(cookie=t), rep2)[0] == 200
    assert rep2.effaces and rep2.effaces[0][0] == "afb_live_guest"
    assert appel(S.live_guest_moi, Req(cookie=t))[0] == 401          # L : révoqué → refus
    assert len(base.invites_live.docs) == 1 and len(base.chat_participants.docs) == 1   # rien supprimé côté serveur


def test_oublier_sans_cookie_ne_plante_pas(base):
    assert appel(S.live_guest_oublier, Req(), Rep())[0] == 200


# ── K : expiration ────────────────────────────────────────────────────────────
def test_K_jeton_expire_formulaire_normal(base):
    _, _, rep = rejoindre()
    (ident,) = base.invites_live.docs.values()
    ident["appareils"][0]["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    assert appel(S.live_guest_moi, Req(cookie=jeton_de(rep)))[0] == 401


def test_duree_180_jours_glissants_plafond_395(base):
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert S.live_guest_expiration(t0, t0) == t0 + timedelta(days=180)
    assert S.live_guest_expiration(t0 + timedelta(days=300), t0) == t0 + timedelta(days=395)


# ── modifier ──────────────────────────────────────────────────────────────────
def test_modifier_pseudo_photo_met_a_jour_identite_et_live_courant_sans_ecraser_le_crm(base):
    _, _, rep = rejoindre()
    (f,) = base.chat_participants.docs.values()
    f["name"] = "Nom saisi par le coach"
    st, vue = appel(S.live_guest_modifier, Req({"pseudo": "Bassou", "photo_url": PHOTO.replace("p.jpg", "q.jpg"),
                                                "session_code": CODE_A}, jeton_de(rep)), Rep())
    assert st == 200 and vue["pseudo"] == "Bassou"
    (ident,) = base.invites_live.docs.values()
    assert ident["pseudo"] == "Bassou"
    assert f["name"] == "Nom saisi par le coach"                     # CRM du coach intact
    assert f["lives"][-1]["pseudo"] == "Bassou" and f["lives"][-1]["photo_url"].endswith("q.jpg")


def test_modifier_email_revoque_les_autres_appareils(base):
    _, _, rep = rejoindre()
    t1 = jeton_de(rep)
    rep2 = Rep()
    appel(S.live_guest_continuer, Req({"session_code": CODE_A}, t1), rep2)   # appareil 1 (tourné)
    t1 = jeton_de(rep2)
    (ident,) = base.invites_live.docs.values()
    ident["appareils"].append({"h": hashlib.sha256(b"autre-appareil").hexdigest(), "created_at": ident["created_at"],
                               "last_used_at": ident["created_at"], "expires_at": ident["appareils"][0]["expires_at"],
                               "revoked_at": None})
    assert appel(S.live_guest_modifier, Req({"email": "nouveau@exemple.ch"}, t1), Rep())[0] == 200
    assert appel(S.live_guest_moi, Req(cookie="autre-appareil"))[0] == 401   # autres appareils révoqués
    assert appel(S.live_guest_moi, Req(cookie=t1))[0] == 200                 # celui-ci garde l'accès


def test_rejoindre_avec_adresse_d_un_autre_ne_donne_pas_son_identite(base):
    """Sans cookie, un e-mail déjà connu ne rattache JAMAIS à l'identité existante (non vérifié)."""
    rejoindre()
    st, r, rep = rejoindre({**CORPS, "pseudo": "Intrus"})
    assert st == 200 and r["pseudo"] == "Intrus" and len(base.invites_live.docs) == 2


# ── O / P / sécurité ──────────────────────────────────────────────────────────
def test_O_live_inconnu_ou_ancien_refuse(base):
    assert rejoindre({**CORPS, "session_code": "INCONNU-ZZZZ"})[0] == 404
    base.boosttribe_live.docs["actuel"]["started_at"] = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    assert rejoindre()[0] == 404
    assert base.invites_live.docs == {}


def test_P_aucun_consentement_marketing_ajoute(base):
    rejoindre()
    (f,) = base.chat_participants.docs.values()
    assert f["marketing_consent"] is False and base.subscribers.docs == {}


def test_coordonnees_invalides_400(base):
    assert rejoindre({**CORPS, "email": "", "whatsapp": "12"})[0] == 400
    assert rejoindre({**CORPS, "pseudo": "x"})[0] == 400


def test_debit_limite_par_ip(base):
    for _ in range(S.LIVE_GUEST_DEBIT_MAX):
        rejoindre()
    assert rejoindre()[0] == 429


def test_continuer_sans_cookie_401(base):
    assert appel(S.live_guest_continuer, Req({"session_code": CODE_A}), Rep())[0] == 401


def test_en_tete_set_cookie_reel_starlette(base):
    """Le VRAI en-tête produit par Starlette : HttpOnly, Secure, SameSite=Lax, chemin restreint."""
    from starlette.responses import Response as StarletteResponse
    rep = StarletteResponse()
    run(S.live_guest_rejoindre(Req(CORPS), rep))
    entete = rep.headers["set-cookie"]
    assert entete.startswith("afb_live_guest=")
    for attendu in ("HttpOnly", "Secure", "SameSite=lax", "Path=/api/live-guest", "Max-Age="):
        assert attendu in entete, attendu
    assert "Domain=" not in entete                                  # jamais partagé avec api-live / sous-domaines
    rep2 = StarletteResponse()
    run(S.live_guest_oublier(Req(), rep2))
    assert 'afb_live_guest=""' in rep2.headers["set-cookie"] and "Max-Age=0" in rep2.headers["set-cookie"]
