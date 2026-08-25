# -*- coding: utf-8 -*-
"""LE PIED DE PAGE DES E-MAILS DOIT MENER OU IL DIT MENER.

Defaut ferme par ce test : le pied de page du gabarit partage
`_email_wrapper` AFFICHAIT « afroboost.com » mais son `href` pointait vers
`https://afroboost-v11-dev-pm7l.vercel.app` — un residu de l'ancienne
installation Vercel qui sert un bundle PERIME (cf. CLAUDE.md, section
« Deploiement »). Un client qui cliquait sur ce lien n'arrivait pas sur le
site d'aujourd'hui.

Ce test ne verifie PAS le design : il verifie une seule chose, mais sur les
DEUX bouts — le texte affiche et la destination reelle doivent designer le
meme domaine, celui qui est reellement servi.

Perimetre volontairement etroit : le gabarit partage, et le message J+0
(P1-b) qui l'utilise. Les liens des e-mails COACH (`#partner-dashboard`)
portent le meme residu et restent une dette consignee, hors de ce correctif.

Aucun reseau. Aucun e-mail. Aucune base. Aucun envoi.

Lancement :  python3 tests/test_p1b_footer_domaine.py
"""

import ast
import io
import os
import re
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVEUR = os.path.join(RACINE, "api", "server.py")
SOURCE = io.open(SERVEUR, encoding="utf-8").read()
ARBRE = ast.parse(SOURCE)
LIGNES = SOURCE.splitlines(True)

# Le domaine reellement servi en production (Coolify / Hetzner, derriere
# Cloudflare). Ce n'est pas une preference d'ecriture : c'est le seul nom qui
# repond avec le bundle a jour.
DOMAINE_VIVANT = "https://afroboost.com"
RESIDU_MORT = "vercel.app"

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def extraire(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return "".join(LIGNES[n.lineno - 1:n.end_lineno])
    raise AssertionError("introuvable : %s" % nom)


def liens(html):
    """[(texte affiche, href)] — le couple qui doit rester coherent."""
    out = []
    for m in re.finditer(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        out.append((re.sub(r"<[^>]+>", "", m.group(2)).strip(), m.group(1)))
    return out


def gabarit():
    """Le pied de page du gabarit partage, rendu par la VRAIE fonction."""
    esp = {"__builtins__": __builtins__}
    for fn in ("_v259_primary_rgb", "_email_wrapper"):
        exec(compile(extraire(fn), "<srv>", "exec"), esp)
    html = esp["_email_wrapper"]("linear-gradient(135deg,#D91CD2,#7c3aed)",
                                 "<div>CORPS</div>", "#D91CD2")

    _pied = [(t, h) for t, h in liens(html) if t == "afroboost.com"]
    verifier("W1. le pied de page affiche bien « afroboost.com »",
             len(_pied) == 1, "trouves : %s" % _pied)
    if _pied:
        _texte, _href = _pied[0]
        verifier("W2. et il POINTE vers afroboost.com — pas ailleurs",
                 _href.rstrip("/") == DOMAINE_VIVANT, "href = %s" % _href)
        verifier("W3. aucun residu Vercel dans la destination du pied de page",
                 RESIDU_MORT not in _href, "href = %s" % _href)

    verifier("W4. aucun residu Vercel nulle part dans le gabarit",
             RESIDU_MORT not in html,
             [u for u in re.findall(r'https?://[^\s"\'<>]+', html) if RESIDU_MORT in u])

    # Le correctif porte sur UNE destination. Le reste du gabarit — en-tete,
    # copyright, couleur d'accent — doit etre intact : c'est ce qui prouve
    # qu'on n'a pas refondu l'e-mail au passage.
    verifier("W5. l'en-tete du gabarit est INCHANGE",
             "AFROBOOST" in html and "MOVE • GROOVE • BOOST" in html)
    verifier("W6. le copyright est INCHANGE",
             "© 2026 Afroboost — Tous droits réservés" in html)
    verifier("W7. la couleur d'accent colore toujours le lien du pied",
             "color:#D91CD2;font-size:11px" in html)
    verifier("W8. le corps qu'on lui passe est toujours insere",
             "<div>CORPS</div>" in html)


def message_j0():
    """Le message J+0 complet : AUCUN de ses liens ne part vers un domaine mort."""
    sys.path.insert(0, os.path.join(RACINE, "tests"))
    import test_p1b_relance_j0 as T

    esp = T.construire(T.monde(), T.SIMU)
    lien = esp["p1b_lien_espace"]("AFR-ESSAI1")
    sujet, html, texte = esp["p1b_contenu_relance"](
        "Ana", "Silent Mercredi", lien, "#D91CD2")

    _tous = liens(html)
    verifier("J1. le message J+0 porte exactement DEUX liens : CTA et pied de page",
             len(_tous) == 2, _tous)
    verifier("J2. le CTA mene a l'espace du participant, sur le domaine vivant",
             ("Continuer avec Afroboost", "%s/espace/AFR-ESSAI1" % DOMAINE_VIVANT) in _tous,
             _tous)
    verifier("J3. le pied de page mene au domaine vivant",
             ("afroboost.com", DOMAINE_VIVANT) in _tous, _tous)
    verifier("J4. AUCUN lien du HTML ne part vers un domaine mort",
             not any(RESIDU_MORT in h for _t, h in _tous),
             [h for _t, h in _tous if RESIDU_MORT in h])
    verifier("J5. la version TEXTE non plus",
             RESIDU_MORT not in texte,
             [u for u in re.findall(r'https?://\S+', texte) if RESIDU_MORT in u])
    verifier("J6. chaque texte affiche designe bien sa destination",
             all(h.rstrip("/").startswith(DOMAINE_VIVANT) for _t, h in _tous), _tous)

    # Ce que le message NE contient PAS — donc rien a auditer de ce cote.
    verifier("J7. aucun lien WhatsApp dans ce message",
             "wa.me" not in html and "whatsapp" not in html.lower())
    verifier("J8. aucun lien de desinscription/preferences dans ce message",
             not any(m in html.lower() for m in
                     ("unsubscribe", "desinscri", "désinscri", "préférence", "preference")))
    verifier("J9. le sujet est inchange par ce correctif",
             sujet == "Merci pour ton énergie aujourd'hui 🔥", sujet)


def voisins():
    """Les autres e-mails qui partagent le gabarit ne sont pas casses."""
    # Les quatre autres appelants passent par la MEME fonction : si le pied de
    # page est sain une fois, il l'est pour tous. Ce qu'on verifie ici, c'est
    # que la signature n'a pas bouge — un appelant casse est un e-mail perdu.
    _src = extraire("_email_wrapper")
    verifier("V1. la signature du gabarit est INCHANGEE",
             "def _email_wrapper(header_gradient: str, body_html: str, "
             "accent: str = \"#D91CD2\") -> str:" in _src, _src[:120])
    # COMPTE EXACT, jamais `>=` : un `>=` laisserait passer la PERTE d'un
    # appelant compensee par l'ajout d'un autre — exactement ce que ce garde
    # doit voir. Le compte est monte de 6 a 7 le 25/08/2026 avec P1-d
    # (`p1d_contenu_relance`), qui reutilise le meme gabarit. Toute nouvelle
    # variation de ce nombre doit etre EXPLIQUEE ici.
    verifier("V2. les six appelants du gabarit sont toujours la (dont P1-d)",
             SOURCE.count("_email_wrapper(") == 7,
             "occurrences (definition comprise) : %d" % SOURCE.count("_email_wrapper("))


def main():
    gabarit()
    message_j0()
    voisins()
    print("=" * 78)
    for nom, ok, detail in RESULTATS:
        print("  %-6s %s" % ("OK" if ok else "ECHEC", nom))
        if not ok and detail:
            print("         -> %s" % (detail,))
    _ok = sum(1 for _n, o, _d in RESULTATS if o)
    print("-" * 78)
    print("%d / %d verifications" % (_ok, len(RESULTATS)))
    print("E-mails REELLEMENT envoyes : 0 — aucun transport, aucune base.")
    return 0 if _ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())
