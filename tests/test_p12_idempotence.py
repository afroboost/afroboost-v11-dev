# -*- coding: utf-8 -*-
"""LOT P1.2 — UN RETRY NE DOIT JAMAIS CREER UN SECOND LEAD.

LE DEFAUT MESURE. Le 29/08/2026, deux leads identiques sont nes a 882 ms
d'intervalle sur le lien partenaire. Le bouton porte pourtant
`disabled={loading}` : la garde d'interface ne suffit pas. Et sans idempotence,
on ne peut PAS offrir un bouton « Reessayer » apres une coupure reseau — le
serveur a peut-etre enregistre la demande et seule la reponse s'est perdue.

CE QUE CE LOT AJOUTE. Un `submission_id` (UUID) genere UNE SEULE FOIS au
montage du tunnel, envoye a chaque tentative, et deduplique COTE SERVEUR.

DEUX NIVEAUX, ET IL FAUT LES DEUX :
  * une VERIFICATION prealable — elle suffit au cas sequentiel (retry) et
    fonctionne des aujourd'hui, sans index ;
  * un INDEX UNIQUE PARTIEL — seul rempart contre deux requetes SIMULTANEES.
    `find_one` puis `insert` n'est pas atomique : entre les deux, l'autre
    requete passe. L'index rend la seconde insertion impossible, et l'erreur
    de cle dupliquee devient le signal « c'est un rejeu ».

L'INDEX EST PARTIEL, ET C'EST OBLIGATOIRE : 145 leads existent SANS
`submission_id`. Un index unique simple les considererait tous comme des
doublons de `null` et refuserait toute nouvelle insertion.

AUCUNE BASE REELLE, AUCUN RESEAU, AUCUNE DONNEE PERSONNELLE.
    python3 tests/test_p12_idempotence.py
"""
import ast, asyncio, importlib.util, io, os, re, sys, types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
ARBRE = ast.parse(SRC)
LIGNES = SRC.splitlines(True)

_spec = importlib.util.spec_from_file_location(
    "p12_shared", os.path.join(RACINE, "api", "routes", "shared.py"))
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def source_de(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return "".join(LIGNES[n.lineno - 1:n.end_lineno])
    return ""


UUID_OK = "3f2504e0-4f89-11d3-9a0c-0305e82c3301"


async def principal():
    # ═══════════ 1. LA VALIDATION DU submission_id ══════════════════════════
    verifier("1. `p12_submission_id_propre` existe", hasattr(S, "p12_submission_id_propre"))
    if not hasattr(S, "p12_submission_id_propre"):
        return
    f = S.p12_submission_id_propre
    verifier("2. Un UUID valide est accepte", f(UUID_OK) == UUID_OK, f(UUID_OK))
    verifier("3. La casse est normalisee", f(UUID_OK.upper()) == UUID_OK)
    verifier("4. Les espaces sont retires", f("  " + UUID_OK + "  ") == UUID_OK)
    for mauvais in ("pas-un-uuid", "", None, 42, {}, [], "x" * 300,
                    "moi@exemple.invalid", "'; DROP TABLE", "../../etc/passwd",
                    UUID_OK + "-suffixe"):
        verifier("5. Rejete : %r" % (mauvais,), f(mauvais) == "", repr(f(mauvais))[:60])
    verifier("6. Aucune PII ne peut passer",
             f("jean.dupont@exemple.invalid") == "" and f("+41791234567") == "")
    verifier("7. Ne leve jamais",
             all(f(x) == "" or isinstance(f(x), str)
                 for x in (None, 0, [], {}, object())))

    # ═══════════ 2. LE SERVEUR L'ACCEPTE, DE FACON ADDITIVE ═════════════════
    se = source_de("smart_chat_entry")
    verifier("8. `smart-entry` lit `submission_id` du corps",
             'body.get("submission_id")' in se)
    verifier("9. Il le valide avant tout usage", "p12_submission_id_propre" in se)
    verifier("10. Un ancien client SANS `submission_id` reste accepte",
             'raise HTTPException' not in se.split('submission_id')[1][:400]
             if 'submission_id' in se else False,
             "aucune 400 ne doit apparaitre pour un champ absent")

    # ═══════════ 3. LA DEDUPLICATION ════════════════════════════════════════
    verifier("11. Le lead porte `submission_id`", '"submission_id"' in se)
    verifier("12. Verification prealable (cas sequentiel, sans index)",
             se.count('{"submission_id": p12_submission}') >= 2,
             "un `find_one` prealable sur CHACUN des deux sites d'insertion")
    verifier("13. Erreur de cle dupliquee traitee (cas concurrent)",
             "DuplicateKeyError" in se or "duplicate key" in se.lower(),
             "sans cela, deux requetes simultanees creent deux leads")
    verifier("14. Un rejeu rend quand meme `acquisition_saved: True`",
             se.count("_c2f_acq = True") >= 2,
             "le prospect doit voir la confirmation, pas une erreur")
    # DEUX sites inserent un lead : la branche `proof_required` (C2-F) et le
    # chemin normal (V100), chacun avec sa notification. Les DEUX doivent etre
    # dedupliques — sinon un rejeu sur le chemin normal cree un second lead et
    # une seconde alerte. (Premiere ecriture de ce controle : elle supposait un
    # seul site, et aurait laisse le second ouvert.)
    verifier("15. Les DEUX sites d'insertion de lead sont dedupliques",
             se.count("_c2f_lead") > 0 and "_p12_rejeu" in se
             and se.count("DuplicateKeyError") >= 2,
             "sites dedupliques : %d" % se.count("DuplicateKeyError"))
    verifier("15b. Aucune notification sur un rejeu",
             "if not _p12_rejeu:" in se
             and se.index("if not _p12_rejeu:") < se.index("notifier_nouveau_prospect as _c17c", se.index("_p12_rejeu")),
             "la notification du chemin normal doit etre sous la garde de rejeu")

    # ═══════════ 4. L'INDEX, PREPARE MAIS PAS CREE ══════════════════════════
    verifier("16. La forme de l'index est documentee dans le code",
             "partialFilterExpression" in SRC or "partial_filter_expression" in SRC,
             "l'index doit etre PARTIEL : 145 leads n'ont pas de submission_id")
    verifier("17. Aucun `create_index` n'est execute par ce lot",
             "create_index" not in se,
             "l'index sera cree au deploiement, hors chemin de requete")

    # ═══════════ 5. RIEN D'AUTRE N'EST TOUCHE ═══════════════════════════════
    verifier("18. Le limiteur de debit est intact",
             "Trop de tentatives" in se and "smart_entry_attempts" in se)
    verifier("19. Le controle du nom reste AVANT tout ecriture",
             se.index('detail="Le nom est requis"') < se.index("smart_entry_attempts"))
    verifier("20. `proof_required` garde sa forme",
             '"proof_required": True' in se and '"acquisition_saved"' in se)

    # ═══════════ 6. AUCUN NOM LIBRE — LA LECON, APPLIQUEE D'EMBLEE ══════════
    # Deux fois deja un nom appele mais jamais importe a rendu du code inerte en
    # production (`_RESEND_OK` pour l'OTP, `m2a_attribution_entrante` pour M2-A),
    # les deux fois avale par un `except`. Ce controle est pose AVANT la mise en
    # ligne cette fois-ci — il a d'ailleurs attrape `DuplicateKeyError` manquant.
    manquants = _noms_libres("smart_chat_entry")
    verifier("21. `smart_chat_entry` n'utilise aucun nom inexistant", not manquants,
             "noms absents de api/server.py : %s" % sorted(manquants))


def _noms_libres(nom_fonction):
    """Tout nom LU par cette fonction et qui n'existe nulle part -> NameError."""
    import builtins
    globaux = set()
    for n in ARBRE.body:
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    globaux.add(t.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            globaux.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for al in n.names:
                globaux.add((al.asname or al.name).split(".")[0])
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            globaux.add(n.target.id)
        elif isinstance(n, ast.Try):
            for sous in n.body + [x for h in n.handlers for x in h.body] + n.orelse + n.finalbody:
                if isinstance(sous, (ast.Import, ast.ImportFrom)):
                    for al in sous.names:
                        globaux.add((al.asname or al.name).split(".")[0])
                elif isinstance(sous, ast.Assign):
                    for t in sous.targets:
                        if isinstance(t, ast.Name):
                            globaux.add(t.id)
    cible = None
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom_fonction:
            cible = n
    if cible is None:
        return {nom_fonction + " (fonction absente)"}
    locaux = set(a.arg for a in cible.args.args)
    for n in ast.walk(cible):
        if isinstance(n, ast.Lambda):
            for _a in list(n.args.args) + list(n.args.posonlyargs) + list(n.args.kwonlyargs):
                locaux.add(_a.arg)
    for n in ast.walk(cible):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            locaux.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for al in n.names:
                locaux.add((al.asname or al.name).split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            locaux.add(n.name)
    for n in ast.walk(cible):
        if isinstance(n, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            for g in n.generators:
                for x in ast.walk(g.target):
                    if isinstance(x, ast.Name):
                        locaux.add(x.id)
    manquants = set()
    for n in ast.walk(cible):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            if n.id not in locaux and n.id not in globaux and not hasattr(builtins, n.id):
                manquants.add(n.id)
    return manquants


if __name__ == "__main__":
    try:
        asyncio.run(principal())
    except Exception as _e:
        RESULTATS.append(("BANC INTERROMPU : %s: %s" % (type(_e).__name__, _e), False, ""))
    ok = 0
    for nom, bon, detail in RESULTATS:
        print(("  OK   " if bon else "  RATE ") + nom + (("   [%s]" % detail) if (detail and not bon) else ""))
        ok += 1 if bon else 0
    print("\n%d/%d au vert" % (ok, len(RESULTATS)))
    sys.exit(0 if ok == len(RESULTATS) else 1)
