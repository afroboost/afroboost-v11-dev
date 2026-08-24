# -*- coding: utf-8 -*-
"""LE MESSAGE J+0 DEFINITIF — copie validee, HTML et TEXTE qui disent la MEME chose.

Trois choses sont verrouillees ici :

1. LA COPIE. Celle validee par le proprietaire, mot pour mot sur les phrases
   qui portent l'intention. Aucun prix, aucune offre nommee, aucune urgence.

2. LA SYMETRIE. La version texte portait moins d'informations que le HTML (le
   nom du cours y manquait). Un client mail sans HTML lisait donc un autre
   message. Les deux versions doivent desormais porter : prenom, cours, corps,
   CTA en URL, sortie, signature.

3. AUCUNE PROMESSE DE DESINSCRIPTION QUI NE SERAIT PAS TENUE.

   La chaine « reponds STOP » a ete tracee de bout en bout le 24/08/2026, et
   elle NE FONCTIONNE PAS :
     * la reponse arrive dans une boite Gmail — aucun webhook entrant, aucun
       IMAP, aucun parseur ne la lit (verifie : rien dans `api/`) ;
     * aucune interface ne permet au coach d'acter la demande (les deux seules
       occurrences frontend concernent le PUSH navigateur) ;
     * la seule route qui ecrit `opted_out` est `v332_unsubscribe`, et elle
       EXIGE un jeton — inexistant pour ce public (0 des 34 adresses ayant
       reserve figurent dans `subscribers`).

   Ecrire « Reponds STOP » serait donc une fonctionnalite de facade. Le
   proprietaire a tranche : on ne l'affiche pas. Ce test VERROUILLE cette
   absence — il echouera le jour ou quelqu'un remettra la promesse sans avoir
   d'abord construit le chemin qui la tient.

   Les gardes qui MARCHENT, elles, restent : une personne deja `opted_out` ou
   portant une preference contraire ne recoit rien (section E).

Aucun reseau. Aucune base. Aucun e-mail.

Lancement :  python3 tests/test_p1b_message_final.py
"""

import ast
import io
import os
import re
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
ARBRE = ast.parse(SOURCE)
LIGNES = SOURCE.splitlines(True)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def extraire(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return "".join(LIGNES[n.lineno - 1:n.end_lineno])
    raise AssertionError("introuvable : %s" % nom)


def constante(nom):
    for n in ARBRE.body:
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == nom for t in n.targets):
            return "".join(LIGNES[n.lineno - 1:n.end_lineno])
    raise AssertionError("constante introuvable : %s" % nom)


ESP = {"__builtins__": __builtins__, "RV2_REPLY_TO": "contact.artboost@gmail.com"}
for _c in ("_V259_DEFAULT_COLOR", "P1B_DOMAINE"):
    try:
        exec(compile(constante(_c), "<c>", "exec"), ESP)
    except AssertionError:
        pass
for _f in ("_v259_primary_rgb", "_email_wrapper", "p1b_lien_espace",
           "p1b_contenu_relance"):
    exec(compile(extraire(_f), "<srv>", "exec"), ESP)

LIEN = ESP["p1b_lien_espace"]("AFR-ESSAI1")
SUJET, HTML, TEXTE = ESP["p1b_contenu_relance"]("Ana", "Silent Mercredi", LIEN, "#D91CD2")


def visible(html):
    """Le texte que le client mail AFFICHE (entites decodees, balises retirees)."""
    import html as _h
    v = re.sub(r"<br\s*/?>", "\n", html)
    v = re.sub(r"</(div|p|td|tr)>", "\n", v)
    v = re.sub(r"<[^>]+>", "", v)
    return _h.unescape(v)


VIS = visible(HTML)


def copie():
    verifier("A1. l'objet est inchange", SUJET == "Merci pour ton énergie aujourd'hui 🔥", SUJET)
    for _p in ("Bravo pour ton premier cours Afroboost",
               "On espère que tu as aimé l'expérience",
               "Envie de continuer à bouger, progresser et booster ton énergie avec nous",
               "Retrouve tes prochaines possibilités directement dans ton espace Afroboost"):
        verifier("A2. le HTML porte : « %s… »" % _p[:38], _p in VIS, VIS[:400])
    verifier("A3. le prenom ouvre le message", "Merci Ana," in VIS)
    verifier("A4. le nom du cours reste affiche", "Silent Mercredi" in VIS)
    verifier("A5. l'invitation a repondre est conservee",
             "Une question ?" in VIS and "Réponds simplement à cet e-mail" in VIS)
    # Le gabarit affiche DEJA « AFROBOOST / MOVE • GROOVE • BOOST » en en-tete.
    # La repeter en pied du corps est une redite visuelle : decision du
    # proprietaire, on la retire du HTML et on la garde en TEXTE (section B),
    # ou elle sert reellement de signature — le texte n'a pas d'en-tete.
    verifier("A6. le HTML ne REPETE pas l'identite deja portee par l'en-tete",
             VIS.count("Move • Groove • Boost") == 0
             and VIS.count("MOVE • GROOVE • BOOST") == 1,
             VIS)
    verifier("A7. AUCUN prix, AUCUNE offre nommee, AUCUNE urgence",
             not any(m in VIS for m in ("CHF", "PULSE", "250", "150", "Achète",
                                        "Achete", "dernière chance", "Plus que",
                                        "% de", "promo", "réduction", "€")),
             [m for m in ("CHF", "PULSE", "Achète", "réduction") if m in VIS])
    verifier("A8. aucun emoji utilise comme PICTOGRAMME d'interface",
             HTML.count("🔥") <= 1)


def symetrie():
    verifier("B1. le TEXTE porte le prenom", "Merci Ana," in TEXTE)
    verifier("B2. le TEXTE porte le nom du cours — l'asymetrie est fermee",
             "Silent Mercredi" in TEXTE, TEXTE)
    verifier("B3. le TEXTE porte le corps du message",
             "Bravo pour ton premier cours Afroboost" in TEXTE
             and "Retrouve tes prochaines possibilités" in TEXTE)
    verifier("B4. le TEXTE porte le CTA sous forme d'URL", LIEN in TEXTE)
    verifier("B5. le TEXTE ne promet AUCUNE desinscription non tenue",
             "STOP" not in TEXTE and "désinscri" not in TEXTE.lower(), TEXTE)
    verifier("B6. le TEXTE porte la signature — il n'a pas d'en-tete, elle y sert",
             "Afroboost\nMove • Groove • Boost" in TEXTE, TEXTE[-260:])
    # LE POINT DE FOND : les deux versions ne racontent pas deux histoires.
    for _cle in ("Ana", "Silent Mercredi", "Bravo pour ton premier cours Afroboost",
                 "Retrouve tes prochaines possibilités", "Une question ?"):
        verifier("B7. « %s… » est dans LES DEUX versions" % _cle[:32],
                 (_cle in VIS) and (_cle in TEXTE),
                 "html=%s texte=%s" % (_cle in VIS, _cle in TEXTE))


def sortie():
    """AUCUNE PROMESSE QUI NE SERAIT PAS TENUE — la garde de ce lot."""
    # Le message ne doit contenir NI lien, NI en-tete, NI phrase promettant une
    # desinscription, tant que rien ne sait enregistrer la demande.
    verifier("C1. aucune phrase « reponds STOP » dans le HTML",
             "STOP" not in VIS, VIS[-300:])
    verifier("C2. ni dans la version TEXTE", "STOP" not in TEXTE)
    verifier("C3. aucun mot de desinscription nulle part",
             not re.search(r"(?i)d[ée]sinscri|se d[ée]sabonner|unsubscribe", VIS + TEXTE))
    verifier("C4. AUCUNE URL de desinscription n'est forgee",
             not re.search(r'href="[^"]*unsubscribe[^"]*"', HTML))
    verifier("C5. aucun e-mail en clair dans une URL du message",
             not re.search(r'href="[^"]*[?&](email|mail|e=)[^"]*"', HTML))
    verifier("C6. aucun en-tete List-Unsubscribe n'est promis a l'envoi",
             "List-Unsubscribe" not in extraire("p1b_envoyer_email"),
             "un en-tete de desabonnement adosse a une boite que RIEN ne lit "
             "est une promesse non tenue")
    verifier("C7. la fonction d'en-tetes a bien ete retiree, pas laissee morte",
             "p1b_entetes_desinscription" not in SOURCE,
             "du code mort se remet en service tout seul un jour")
    # CE QUI RESTE, ET QUI MARCHE : l'invitation a repondre — le `reply_to` est
    # une boite REELLEMENT RELEVEE, donc cette phrase-la est tenable.
    verifier("C8. l'invitation a repondre subsiste, et elle, elle est tenable",
             "Réponds simplement à cet e-mail" in VIS
             and "Réponds simplement à cet e-mail" in TEXTE)


def cta_et_pied():
    liens = re.findall(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', HTML, re.S)
    liens = [(h, re.sub(r"<[^>]+>", "", t).strip()) for h, t in liens]
    verifier("D1. le CTA est conserve, texte et destination",
             (LIEN, "Continuer avec Afroboost") in liens, liens)
    verifier("D2. le CTA vise l'espace du participant sur afroboost.com",
             LIEN == "https://afroboost.com/espace/AFR-ESSAI1", LIEN)
    verifier("D3. le pied de page mene a afroboost.com",
             ("https://afroboost.com", "afroboost.com") in liens, liens)
    verifier("D4. aucun residu Vercel, HTML comme TEXTE",
             "vercel.app" not in HTML and "vercel.app" not in TEXTE)
    verifier("D5. exactement DEUX liens cliquables : CTA et pied de page",
             len(liens) == 2, liens)

    _s2, _h2, _t2 = ESP["p1b_contenu_relance"]("", "", "", "#D91CD2")
    _v2 = visible(_h2)
    verifier("D6. sans prenom, sans cours, sans lien : aucun trou, aucun bouton mort",
             "Merci," in _v2 and "Continuer avec Afroboost" not in _h2
             and "None" not in _h2 and "ton cours" not in _h2, _v2[:200])
    verifier("D7. meme degrade en version TEXTE",
             "Merci," in _t2 and "None" not in _t2 and "http" not in _t2, _t2)
    _s3, _h3, _t3 = ESP["p1b_contenu_relance"](
        "<script>x</script>", '"><b>', LIEN, "#D91CD2")
    verifier("D8. le nom et le cours restent ECHAPPES",
             "<script>" not in _h3 and "&lt;script&gt;" in _h3)


def envoi():
    nu = extraire("p1b_envoyer_email")
    verifier("E1. l'envoi ne porte AUCUN en-tete de desabonnement de facade",
             "headers" not in nu and "List-Unsubscribe" not in nu, nu[:400])
    verifier("E2. le transport, l'expediteur et le reply_to sont INCHANGES",
             "resend.Emails.send" in nu and "asyncio.to_thread" in nu
             and "notifications@afroboost.com" in nu and "RV2_REPLY_TO" in nu)
    verifier("E3. sans cle Resend, rien n'est tente",
             "RESEND_AVAILABLE" in nu and "RESEND_API_KEY" in nu)
    verifier("E4. une panne du fournisseur ne leve jamais",
             "except Exception" in nu and "return False" in nu)

    nu_r = extraire("p1b_relance_j0")
    # `_reel` est ASSIGNE tout en haut ; la garde, elle, est `if not _reel:`.
    # C'est a elle qu'il faut comparer, sinon on mesure autre chose.
    verifier("E5. les DEUX gardes d'opt-out restent AVANT tout envoi",
             nu_r.index("p1b_destinataire_autorise") < nu_r.index("if not _reel:")
             < nu_r.index("p1b_envoyer_email"),
             "l'ordre des gardes a change")
    verifier("E6. la simulation sort AVANT le jeton — rejeu idempotent, "
             "et simuler ne brule pas le droit d'envoyer",
             nu_r.index("if not _reel:") < nu_r.index("_p1b_reserver"))
    verifier("E7. le jeton est pris AVANT l'envoi, jamais apres",
             nu_r.index("_p1b_reserver") < nu_r.index("p1b_envoyer_email"))
    nu_a = extraire("p1b_destinataire_autorise")
    verifier("E8. porte 1 : une desinscription explicite est respectee",
             'status": "opted_out"' in nu_a or "'status': 'opted_out'" in nu_a
             or "opted_out" in nu_a)
    verifier("E9. porte 2 : la preference V286 contraire est respectee",
             "_v286_should_send_notification" in nu_a)


def main():
    copie(); symetrie(); sortie(); cta_et_pied(); envoi()
    print("=" * 78)
    for nom, ok, detail in RESULTATS:
        print("  %-6s %s" % ("OK" if ok else "ECHEC", nom))
        if not ok and detail != "":
            print("         -> %s" % (detail,))
    _ok = sum(1 for _n, o, _d in RESULTATS if o)
    print("-" * 78)
    print("%d / %d verifications" % (_ok, len(RESULTATS)))
    print("E-mails REELLEMENT envoyes : 0 — aucun transport, aucune base.")
    return 0 if _ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())
