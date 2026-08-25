# -*- coding: utf-8 -*-
"""N2 — LA CONFIRMATION DIT QUAND ET OU, ET L'ANNULATION DIT VRAI.

TROIS DEFAUTS MESURES LE 25/08/2026, TOUS SUR DES DONNEES REELLES.

1. L'E-MAIL DE CONFIRMATION NE DIT PAS QUAND. Le gabarit affiche la date via
   `selectedDatesText`, un champ que SEUL le chemin `website` renseigne :
       sans selectedDatesText : 121 / 139 reservations
         subscriber_space       77/77
         chat_widget_abonne     39/39
         website                 0/18
   87 % des participants recoivent donc une confirmation sans date, sans heure
   et sans lieu — la seule trace ecrite qu'ils gardent ne permet pas de venir.

2. L'HEURE EST LUE COMME DE L'UTC. Deux formats coexistent en base : « ...Z »
   (UTC explicite) et « 2026-05-13T18:30:00 » (NAIF, heure suisse). Le garde
   d'annulation fait `replace(tzinfo=utc)` sur les naives : le cours parait
   deux heures plus tard qu'il ne l'est. C'est EXACTEMENT le defaut que V435 a
   corrige sur les rappels, resté en place ici.

3. LE BOUTON D'ANNULATION EST MORT. L'ecran l'affiche jusqu'a 2 h avant ;
   le serveur refuse en dessous de 24 h (`T1_DELAI_ANNULATION_H = 24`). Entre
   les deux, la personne clique et recoit une erreur. Decision du proprietaire
   du 25/08/2026 : la regle est DEUX HEURES, pour qu'un imprevu du jour meme
   se solde par une annulation propre plutot que par un no-show.

Les vraies fonctions sont extraites par AST des fichiers de production.
Aucun reseau. Aucune base. Aucun e-mail. Aucune reservation.

Lancement :  python3 tests/test_n2_confirmation.py
"""

import ast
import asyncio
import io
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZURICH = ZoneInfo("Europe/Zurich")
RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def source(chemin):
    return io.open(os.path.join(RACINE, chemin), encoding="utf-8").read()


def extraire(src, nom):
    arbre = ast.parse(src)
    lignes = src.splitlines(True)
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return "".join(lignes[n.lineno - 1:n.end_lineno])
    raise AssertionError("introuvable : %s" % nom)


SRC_SHARED = source("api/routes/shared.py")
SRC_SERVEUR = source("api/server.py")
SRC_RESA = source("api/routes/reservation_routes.py")
SRC_ESPACE = source("frontend/src/components/SubscriberSpace.js")

# --- les aides partagees, montees dans un espace de noms minimal -----------
BAC = {"datetime": datetime, "timezone": timezone, "timedelta": timedelta,
       "ZoneInfo": ZoneInfo,
       "logger": type("l", (), {k: staticmethod(lambda *a, **kw: None)
                                for k in ("info", "warning", "error", "debug")})}
# Les constantes de module (fuseau, mois, jours) sont relues DANS le fichier de
# production : les recopier ici ferait mentir le banc le jour ou elles changent.
def _constantes(src, prefixe):
    """Les affectations de module dont le nom commence par `prefixe`, telles
    quelles — une valeur sur plusieurs lignes (un tuple) reste entiere."""
    _lignes = src.splitlines(True)
    _out = []
    for n in ast.parse(src).body:
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id.startswith(prefixe) for t in n.targets):
            _out.append("".join(_lignes[n.lineno - 1:n.end_lineno]))
    return "".join(_out)


_CONSTANTES = _constantes(SRC_SHARED, "N2_")
assert "N2_FUSEAU" in _CONSTANTES, "constantes N2 introuvables"
exec(compile(_CONSTANTES, "<n2>", "exec"), BAC)
for _f in ("n2_instant_reel", "n2_quand_lisible", "n2_lien_carte", "n2_ou"):
    exec(compile(extraire(SRC_SHARED, _f), "<n2>", "exec"), BAC)

n2_instant_reel = BAC["n2_instant_reel"]
n2_quand_lisible = BAC["n2_quand_lisible"]
n2_ou = BAC["n2_ou"]
n2_lien_carte = BAC["n2_lien_carte"]


# ============================================================================
#            A/B/F. QUAND — LA DATE ET L'HEURE, DANS LE BON FUSEAU
# ============================================================================
def quand():
    # --- F. une date NAIVE est de l'heure suisse, jamais de l'UTC ----------
    # « 2026-08-26T18:30:00 » = le cours du mercredi a 18h30 a Neuchatel.
    _i = n2_instant_reel("2026-08-26T18:30:00")
    verifier("F1. une date naive est lue en Europe/Zurich",
             _i is not None and _i == datetime(2026, 8, 26, 16, 30, tzinfo=timezone.utc),
             repr(_i))

    # --- F2. l'ete et l'hiver, sans decalage fixe --------------------------
    _ete = n2_instant_reel("2026-08-26T18:30:00")          # UTC+2
    _hiver = n2_instant_reel("2026-01-14T18:30:00")        # UTC+1
    verifier("F2. l'heure d'ete et l'heure d'hiver different d'une heure",
             _ete.hour == 16 and _hiver.hour == 17,
             "%s / %s" % (_ete, _hiver))

    # --- F3. une date UTC explicite reste ce qu'elle est -------------------
    _z = n2_instant_reel("2026-08-26T16:30:00Z")
    verifier("F3. une date en Z n'est pas retouchee",
             _z == datetime(2026, 8, 26, 16, 30, tzinfo=timezone.utc), repr(_z))

    # --- F4. une valeur inexploitable ne leve jamais ------------------------
    for mauvais in (None, "", "  ", "pas une date", 42, {}, []):
        verifier("F4. valeur inexploitable -> None (%r)" % (mauvais,),
                 n2_instant_reel(mauvais) is None)

    # --- A/B. la phrase montree au participant ------------------------------
    _txt = n2_quand_lisible({"datetime": "2026-08-26T18:30:00"})
    verifier("A1. la date est dite", "26" in _txt and ("août" in _txt or "aout" in _txt),
             repr(_txt))
    verifier("B1. l'heure est dite, en heure suisse", "18:30" in _txt, repr(_txt))

    _txt_z = n2_quand_lisible({"datetime": "2026-08-26T16:30:00Z"})
    verifier("B2. une date en Z est rendue en heure suisse",
             "18:30" in _txt_z, repr(_txt_z))

    # --- E. date unique / D. recurrent : meme champ, meme resultat ---------
    verifier("D1. cours recurrent (occurrence datee) : phrase complete",
             "18:30" in n2_quand_lisible(
                 {"datetime": "2026-08-26T18:30:00", "courseTime": "18:30"}))
    verifier("E1. date unique : phrase complete",
             "18:30" in n2_quand_lisible(
                 {"datetime": "2026-12-24T18:30:00", "courseTime": ""}))

    # --- repli : sans `datetime`, on ne fabrique rien -----------------------
    verifier("A2. sans date exploitable, la phrase est vide (jamais inventee)",
             n2_quand_lisible({"datetime": ""}) == ""
             and n2_quand_lisible({}) == "")
    verifier("A3. l'ancien champ `selectedDatesText` reste prioritaire s'il existe",
             n2_quand_lisible({"selectedDatesText": "mer. 26 août",
                               "datetime": "2026-08-26T18:30:00"})
             .startswith("mer. 26 août"))


# ============================================================================
#                        C. OU — LE LIEU ET L'ITINERAIRE
# ============================================================================
def ou():
    _nom, _maps = n2_ou({"locationName": "Rue des Vallangines 97, Neuchâtel",
                         "mapsUrl": "https://maps.example/x"})
    verifier("C1. le lieu est rendu", _nom == "Rue des Vallangines 97, Neuchâtel", _nom)
    verifier("C2. l'itineraire est rendu quand il existe",
             _maps == "https://maps.example/x", _maps)

    _nom2, _maps2 = n2_ou({"locationName": "Salle B"})
    verifier("C3. sans itineraire, le lieu reste rendu",
             _nom2 == "Salle B" and _maps2 == "", "%r %r" % (_nom2, _maps2))

    for vide in (None, {}, {"locationName": ""}):
        verifier("C4. sans cours ni lieu, rien n'est invente (%r)" % (vide,),
                 n2_ou(vide) == ("", ""))


# ============================================================================
#          G/H/I. ANNULATION — DEUX HEURES, EN HEURE REELLE DU COURS
# ============================================================================
def annulation():
    # La constante est la decision du proprietaire, pas une valeur en dur.
    _m = re.search(r"^T1_DELAI_ANNULATION_H\s*=\s*(\d+)", SRC_SERVEUR, re.M)
    verifier("G0. le delai d'annulation est de 2 h",
             _m is not None and _m.group(1) == "2",
             _m.group(1) if _m else "constante introuvable")

    _garde = extraire(SRC_SERVEUR, "cancel_reservation_from_space")
    # Les commentaires PARLENT de `delete_one` : raisonner sur le texte brut
    # ferait croire a une suppression posee avant la trace.
    _garde_code = re.sub(r"(?m)^\s*#.*$", "", _garde)

    # --- le defaut corrige : plus aucune date naive lue comme de l'UTC -----
    verifier("H0. le garde n'interprete plus une date naive comme de l'UTC",
             "replace(tzinfo=timezone.utc)" not in _garde,
             "`replace(tzinfo=timezone.utc)` encore present")
    verifier("H1. le garde passe par l'aide partagee Europe/Zurich",
             "n2_instant_reel" in _garde)

    # --- la frontiere, decidee sur des instants REELS ----------------------
    # Cours naif « 18:30 » = 16:30 UTC. A 14:29 UTC il reste 2h01 -> autorise ;
    # a 14:31 UTC il reste 1h59 -> refuse. Lu comme de l'UTC, l'ancien code
    # aurait repondu l'inverse pendant deux heures entieres.
    _cours = "2026-08-26T18:30:00"
    _reel = n2_instant_reel(_cours)
    for etiquette, maintenant, autorise in (
        ("G1. plus de 2 h avant -> autorise", _reel - timedelta(hours=2, minutes=1), True),
        ("H2. exactement 2 h -> autorise (la borne appartient au client)",
         _reel - timedelta(hours=2), True),
        ("I1. moins de 2 h -> refuse", _reel - timedelta(hours=1, minutes=59), False),
        ("I2. cours deja commence -> refuse", _reel + timedelta(minutes=1), False),
    ):
        _restant = (_reel - maintenant).total_seconds() / 3600.0
        verifier(etiquette, (_restant >= 2.0) is autorise,
                 "reste %.2f h" % _restant)

    # --- le refus est PARLANT, et ne promet rien qui n'existe pas ----------
    verifier("I3. le refus nomme le delai reel, sans canal invente",
             "T1_DELAI_ANNULATION_H" in _garde
             and not re.search(r"(appelle|t[ée]l[ée]phone|whatsapp|contacte)", _garde, re.I))

    # --- L. l'essai garde son exemption -----------------------------------
    verifier("L1. l'essai reste exempte du delai (regle T1 inchangee)",
             "not _t1_essai" in _garde)

    # --- J. la trace precede toujours la suppression -----------------------
    _i_trace = _garde_code.find("t1_tracer_annulation")
    _i_suppr = _garde_code.find("delete_one")
    verifier("J1. l'annulation est tracee AVANT la suppression",
             _i_trace > -1 and _i_suppr > -1 and _i_trace < _i_suppr)
    verifier("J2. AUTO-PRESENCE ne peut pas valider une annulation : le document part",
             "delete_one" in _garde_code)


# ============================================================================
#              A/C. L'E-MAIL ET L'ECRAN DISENT LA MEME CHOSE
# ============================================================================
def surfaces():
    _mail = extraire(SRC_RESA, "_send_reservation_email")
    verifier("A4. l'e-mail affiche QUAND, derive de la reservation",
             "n2_quand_lisible" in _mail)
    verifier("C5. l'e-mail affiche OU",
             "n2_ou" in _mail)
    # Le vrai invariant : la ligne « Quand » ne doit PAS etre conditionnee par
    # `dates_text`, sinon les 87 % de reservations sans ce champ resteraient
    # muettes — c'est exactement le defaut qu'on corrige.
    _i_quand = _mail.find("Quand</td>")
    verifier("A5. la ligne QUAND existe et depend de `quand_text`, pas de `dates_text`",
             _i_quand > -1 and "if quand_text" in _mail[_i_quand:_i_quand + 260],
             _mail[_i_quand:_i_quand + 200] if _i_quand > -1 else "ligne absente")
    verifier("D2. les regles d'annulation de l'e-mail annoncent 2 h, dans les 3 langues",
             SRC_RESA.count("2 h avant la séance") == 1
             and SRC_RESA.count("2 h before the session") == 1
             and SRC_RESA.count("2 Std. vor der Session") == 1
             and "24h avant la séance" not in SRC_RESA
             and "24h before the session" not in SRC_RESA)

    # L'espace renvoie desormais le lieu avec chaque reservation.
    _espace = extraire(SRC_SERVEUR, "get_subscriber_space")
    verifier("C6. l'espace joint le lieu aux reservations",
             "locationName" in _espace and "mapsUrl" in _espace)
    verifier("C7. le lieu est joint par une requete groupee, jamais en boucle",
             "$in" in _espace)

    # Ecran participant.
    verifier("C8. l'ecran affiche le lieu des seances reservees",
             'data-testid="resa-lieu"' in SRC_ESPACE)
    verifier("C9. l'ecran met en avant la seance du jour",
             'data-testid="resa-aujourdhui"' in SRC_ESPACE)
    verifier("I4. l'ecran explique pourquoi l'annulation n'est plus possible",
             'data-testid="annulation-trop-tard"' in SRC_ESPACE)
    verifier("K1. le QR reste accessible",
             'data-testid="subscriber-space-qr"' in SRC_ESPACE)
    verifier("N1. les blocs ESSAI-7 sont intacts",
             'data-testid="essai7-priorite"' in SRC_ESPACE
             and 'data-testid="essai7-reserve"' in SRC_ESPACE)


# ============================================================================
#   S. LES TROIS PUITS OUVERTS PAR CE LOT, ET LEUR FERMETURE
# ============================================================================
#
# CE LOT FAIT SORTIR DEUX DONNEES VERS DES SURFACES DANGEREUSES :
#   - `locationName` part dans du HTML d'e-mail (concatenation, pas de gabarit
#     qui echappe) ;
#   - `mapsUrl` devient un `href` clique par le PARTICIPANT.
# Les deux viennent du COURS, donc du tableau de bord : elles ne sont pas
# saisies par un inconnu, mais elles ne sont pas non plus des constantes. Et
# `n2_quand_lisible` peut rendre `selectedDatesText`, qui vient du NAVIGATEUR
# au moment de la reservation — celle-la est bel et bien d'origine inconnue.
#
# React n'assainit PAS un `href` : `javascript:...` s'execute au clic, dans la
# page du participant, avec son code AFR- a portee. On ferme donc a la SOURCE
# (`n2_ou` ne rend qu'un schema http/https) ET aux deux puits.


def surete():
    # --- S1. seuls http/https survivent -----------------------------------
    for hostile in ("javascript:alert(1)", "JavaScript:alert(1)",
                    "  javascript:alert(1)", "data:text/html,<script>x</script>",
                    "vbscript:msgbox", "file:///etc/passwd", "//evil.test",
                    "j\tavascript:alert(1)"):
        _nom, _url = n2_ou({"locationName": "Salle", "mapsUrl": hostile})
        verifier("S1. schema refuse : %r" % hostile, _url == "", repr(_url))
        verifier("S1b. ...mais le lieu reste affiche : %r" % hostile,
                 _nom == "Salle", repr(_nom))

    for bon in ("https://maps.example/x", "http://maps.example/x",
                "HTTPS://maps.example/x"):
        _, _url = n2_ou({"locationName": "S", "mapsUrl": bon})
        verifier("S2. schema accepte : %r" % bon, _url == bon.strip(), repr(_url))

    # --- S3. l'e-mail echappe ce qu'il concatene ---------------------------
    _mail = extraire(SRC_RESA, "_send_reservation_email")
    for var in ("quand_text", "lieu_text", "lieu_maps"):
        # On verifie que la variable n'entre JAMAIS nue dans le HTML : chacune
        # de ses apparitions dans une concatenation doit passer par l'echappeur
        # (avec ou sans arguments — `quote=True` pour ce qui devient un `href`).
        _nu = re.findall(r'"\s*\+\s*%s\s*\+' % var, _mail)
        _echappe = re.search(r"_n2_html\(\s*%s\b" % var, _mail)
        verifier("S3. `%s` est echappe avant d'entrer dans le HTML" % var,
                 _echappe is not None and not _nu,
                 "concatenations brutes : %d" % len(_nu))

    # --- S4. l'ecran ne rend jamais un href non verifie --------------------
    verifier("S4. l'ecran filtre le schema avant d'en faire un lien",
             "lienCarteSur" in SRC_ESPACE,
             "href pose directement depuis mapsUrl")
    verifier("S4b. aucun `href={r.mapsUrl}` brut ne subsiste",
             "href={r.mapsUrl}" not in SRC_ESPACE
             and "href={prochaineSeance.mapsUrl}" not in SRC_ESPACE)


def main():
    quand(); ou(); annulation(); surfaces(); surete()
    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 78)
    for nom, r, detail in RESULTATS:
        print(("  PASS  " if r else "  FAIL  ") + nom + (("   -> " + detail) if not r else ""))
    print("=" * 78)
    print("Reservations / e-mails / annulations REELS : 0 — aucune base, aucun reseau")
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())
