"""05/10 — « Faire la promo » d'un INVITÉ IDENTIFIÉ du Live : la session invité EXISTANTE (cookie
`afb_live_guest`, V574 « Bon retour ») est convertie en un jeton COURT pour le serveur du Live.

- Aucune 2e authentification : seule preuve = le cookie HttpOnly déjà posé à l'entrée du Live.
- Jeton HS256, secret partagé EXISTANT (`AFRO_BT_SHARED_SECRET`), iss=afroboost,
  aud=boosttribe-live-guest (réservée), sub = id de l'invité, pseudo, session_code, 10 min.
- JAMAIS d'e-mail / WhatsApp dans le jeton ; le corps n'accepte que `session_code`.
- Cookie absent / expiré / révoqué → 401 (réidentification) ; Live inconnu → 404 ; sans secret → 503.
"""
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_live_guest_bon_retour import (S, CODE_A, CODE_B, CORPS, Req, appel, rejoindre, jeton_de,  # noqa: F401
                                        base)

SECRET = "secret-partage-de-test-suffisamment-long"


@pytest.fixture()
def secret(monkeypatch):
    monkeypatch.setenv("AFRO_BT_SHARED_SECRET", SECRET)


def decoder(j):
    return pyjwt.decode(j, SECRET, algorithms=["HS256"], audience="boosttribe-live-guest", issuer="afroboost")


def test_session_invite_valide_donne_un_jeton_court_sans_coordonnees(base, secret):
    _, vue, rep = rejoindre()
    st, r = appel(S.live_guest_jeton, Req({"session_code": CODE_A}, jeton_de(rep)))
    assert st == 200 and 0 < r["expire_dans"] <= 600
    p = decoder(r["jeton"])
    (ident,) = base.invites_live.docs.values()
    assert p["sub"] == ident["id"] and p["pseudo"] == "Bass" and p["session_code"] == CODE_A
    assert p["exp"] - p["iat"] <= 600 and p["jti"]
    brut = str(p)
    assert "bass@exemple.ch" not in brut and "41791234512" not in brut      # aucune coordonnée


def test_corps_ne_choisit_jamais_l_identite(base, secret):
    _, _, rep = rejoindre()
    st, r = appel(S.live_guest_jeton, Req({"session_code": CODE_A, "pseudo": "Autre", "email": "x@y.ch", "sub": "pirate"},
                                          jeton_de(rep)))
    p = decoder(r["jeton"])
    (ident,) = base.invites_live.docs.values()
    assert st == 200 and p["pseudo"] == "Bass" and p["sub"] == ident["id"]
    assert ident["email"] == "bass@exemple.ch"                               # rien n'est modifié


def test_sans_cookie_ou_cookie_inconnu_401(base, secret):
    assert appel(S.live_guest_jeton, Req({"session_code": CODE_A}))[0] == 401
    assert appel(S.live_guest_jeton, Req({"session_code": CODE_A}, "jeton-invente"))[0] == 401


def test_session_expiree_ou_revoquee_401_reidentification(base, secret):
    _, _, rep = rejoindre()
    t = jeton_de(rep)
    (ident,) = base.invites_live.docs.values()
    ident["appareils"][0]["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    assert appel(S.live_guest_jeton, Req({"session_code": CODE_A}, t))[0] == 401
    _, _, rep2 = rejoindre()                                                  # réidentification : nouveau cookie
    assert appel(S.live_guest_jeton, Req({"session_code": CODE_A}, jeton_de(rep2)))[0] == 200
    appel(S.live_guest_oublier, Req(cookie=jeton_de(rep2)), type("R", (), {"delete_cookie": lambda *a, **k: None})())
    assert appel(S.live_guest_jeton, Req({"session_code": CODE_A}, jeton_de(rep2)))[0] == 401   # « Ce n'est pas moi »


def test_live_inconnu_404_code_invalide_400_sans_secret_503(base, secret, monkeypatch):
    _, _, rep = rejoindre()
    assert appel(S.live_guest_jeton, Req({"session_code": "ZZZZ-INCONNU"}, jeton_de(rep)))[0] == 404
    assert appel(S.live_guest_jeton, Req({"session_code": "<script>"}, jeton_de(rep)))[0] == 400
    monkeypatch.setenv("AFRO_BT_SHARED_SECRET", "")
    assert appel(S.live_guest_jeton, Req({"session_code": CODE_A}, jeton_de(rep)))[0] == 503


def test_audience_reservee_distincte_des_autres_jetons(base, secret):
    _, _, rep = rejoindre()
    j = appel(S.live_guest_jeton, Req({"session_code": CODE_A}, jeton_de(rep)))[1]["jeton"]
    for aud in ("boosttribe", "afroboost-contacts"):
        with pytest.raises(pyjwt.InvalidAudienceError):
            pyjwt.decode(j, SECRET, algorithms=["HS256"], audience=aud, issuer="afroboost")


def test_debit_borne_par_identite(base, secret):
    _, _, rep = rejoindre()
    statuts = [appel(S.live_guest_jeton, Req({"session_code": CODE_A}, jeton_de(rep)))[0] for _ in range(S.LIVE_GUEST_JETON_MAX + 1)]
    assert statuts[:-1] == [200] * S.LIVE_GUEST_JETON_MAX and statuts[-1] == 429
    assert time.time() > 0
