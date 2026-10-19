#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V627 — CORBEILLE DES PROSPECTS. ZÉRO E-MAIL, AUCUNE BASE RÉELLE, AUCUN RÉSEAU.

CE QUE CE FICHIER PROUVE (prospects FICTIFS, transport factice)
==============================================================================
  A. « Mettre à la corbeille » : JWT signé + propriété, motif facultatif et borné,
     fiche CONSERVÉE (marquée), entrée dans la corbeille EXISTANTE, double clic = 1 ;
  B. la fiche sort des listes ACTIVES ; les statistiques peuvent toujours la compter ;
  C. « Restaurer » (route EXISTANTE /trash/{id}/restore) retire la marque ;
  D. « Ne souhaite plus être contacté » = refus DURABLE (fiche + registre STOP),
     CONSERVÉ après restauration ;
  E. plus AUCUN envoi : préparation, J0 (même campagne approuvée AVANT, fiche sans
     `ref`), relances J+3/J+7/J+14 (moteur + boucle horaire), réponse manuelle ;
  F. conversations : masquées, sauf nouveau message non lu ; historique intact ;
  G. doublons : la corbeille est vue ; un refus n'est JAMAIS recréé (même
     `allow_duplicate`), import Cowork compris.
"""
import io
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_V620 = os.path.join(RACINE, "tests", "test_v620_media_reponse.py")
_src = io.open(_V620, encoding="utf-8").read()
_fin = _src.index('# ============================================================================\nprint("\\nA.')
_g = {"__file__": _V620, "__name__": "banc_v620"}
exec(compile(_src[:_fin], _V620, "exec"), _g)   # noqa: S102
globals().update({k: v for k, v in _g.items() if not k.startswith("__")})
RESULTATS.clear()
APPELS.clear()
fiche_ = _g["_espace"]["fiche"]


class Coll(CollectionUpsert):
    """Le bouchon des bancs, complété de ce que V627 utilise : $unset, delete_one,
    update_many, parcours asynchrone."""

    async def update_one(self, filtre, maj, upsert=False, *a, **k):
        for d in self.documents:
            if self._ok(d, filtre):
                d.update(maj.get("$set") or {})
                for cle in (maj.get("$unset") or {}):
                    d.pop(cle, None)
                self.ecritures += 1
                return type("R", (), {"matched_count": 1, "modified_count": 1, "upserted_id": None})()
        if not upsert:
            return type("R", (), {"matched_count": 0, "modified_count": 0, "upserted_id": None})()
        c = {k: v for k, v in dict(filtre).items() if not isinstance(v, dict)}
        c.update(maj.get("$setOnInsert") or {})
        c.update(maj.get("$set") or {})
        self.documents.append(c)
        self.ecritures += 1
        return type("R", (), {"matched_count": 0, "modified_count": 0, "upserted_id": True})()

    async def update_many(self, filtre, maj, *a, **k):
        n = 0
        for d in self.documents:
            if self._ok(d, filtre):
                d.update(maj.get("$set") or {})
                n += 1
        self.ecritures += n
        return type("R", (), {"matched_count": n, "modified_count": n})()

    async def delete_one(self, filtre, *a, **k):
        for i, d in enumerate(self.documents):
            if self._ok(d, filtre):
                del self.documents[i]
                self.ecritures += 1
                return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()

    def find(self, filtre=None, projection=None, *a, **k):
        return CurseurIterable([dict(d) for d in self.documents if self._ok(d, filtre)])


def prospects(*fiches):
    b = BaseBouchon([])
    b["partner_prospects"] = Coll("partner_prospects", [dict(f) for f in fiches],
                                  uniques=[(("coach_id", "ref"), {"ref": {"$type": "string"}}), (("id",), None)])
    for nom in ("deleted_items", "subscribers", S.P3S3_ACTIONS, S.P3S3_CAMPAGNES):
        b[nom] = Coll(nom, [])
    b["feature_flags"] = Coll("feature_flags", [{"id": "feature_flags", "P3_LAUNCH_ENABLED": False,
                                                 "P3_LAUNCH_ENVOI_REEL": False}])
    S.db = b
    return b


def corbeiller(pid, corps=None, jeton_=JA):
    return lancer(S.v627_mettre_en_corbeille(pid, RequeteFictive(jeton_=jeton_, corps=corps or {})))


def restaurer(trash_id, jeton_=JA):
    return lancer(S.restore_trash(trash_id, RequeteFictive(jeton_=jeton_, corps={})))


def lister(**params):
    return lancer(S.p3s1_lister_prospects(RequeteFictive(jeton_=JA, params=params)))


def code_erreur(fn):
    try:
        fn()
    except HTTPException as e:
        return e.status_code, e.detail
    return None, None


F1 = fiche_("TST-V627-1", "Studio TEST V627 Un", "Neuchatel", public_email="un@exemple.test",
            public_phone="+41 79 000 00 01", preferred_channel="E-mail", j0_message="Bonjour 1", j3_message="Relance 1")
F2 = fiche_("TST-V627-2", "Studio TEST V627 Deux", "Neuchatel", public_email="deux@exemple.test",
            preferred_channel="E-mail", j0_message="Bonjour 2")
F3 = dict(fiche_("TST-V627-3", "Studio TEST V627 Trois", "Neuchatel", public_email="trois@exemple.test",
                 preferred_channel="E-mail", j0_message="Bonjour 3"), ref=None)   # fiche SANS ref (créée à l'écran)
FB = dict(fiche_("TST-V627-B", "Studio TEST V627 Autre coach", "Neuchatel"), coach_id=COACH_B)

# ============================================================================
print("\nA. METTRE À LA CORBEILLE : AUTORISATION, CONSERVATION, ENTRÉE DE CORBEILLE")
_b = prospects(F1, F2, F3, FB)
verifier("A1. sans jeton : 403", code_erreur(lambda: corbeiller(F1["id"], jeton_=None))[0] in (401, 403))
verifier("A2. la fiche d'un AUTRE coach : refusée (403)", code_erreur(lambda: corbeiller(FB["id"]))[0] == 403)
verifier("A3. fiche inconnue : 404", code_erreur(lambda: corbeiller("inexistant"))[0] == 404)
verifier("A4. motif inconnu : 400", code_erreur(lambda: corbeiller(F1["id"], {"motif": "n'importe"}))[0] == 400)
_r = corbeiller(F2["id"], {"motif": "pas_interesse"})
_f2 = [f for f in _b["partner_prospects"].documents if f["id"] == F2["id"]][0]
verifier("A5. la fiche RESTE en base, marquée (motif, date, auteur)",
         _f2.get("corbeille") is True and _f2.get("corbeille_motif") == "pas_interesse" and _f2.get("corbeille_par") == COACH_A
         and _f2["organisation_name"] == F2["organisation_name"] and _f2.get("public_email") == "deux@exemple.test")
_e = _b["deleted_items"].documents
verifier("A6. UNE entrée dans la corbeille EXISTANTE (deleted_items), coach + instantané",
         len(_e) == 1 and _e[0]["original_collection"] == "partner_prospects" and _e[0]["original_id"] == F2["id"]
         and _e[0]["coach_id"] == COACH_A and _e[0]["payload"]["organisation_name"] == F2["organisation_name"]
         and _e[0]["id"] == _r["trash_id"] and _e[0]["motif_libelle"] == "Pas intéressé")
verifier("A7. double clic : 409, toujours UNE entrée", code_erreur(lambda: corbeiller(F2["id"]))[0] == 409 and len(_e) == 1)
verifier("A8. message « Prospect déplacé dans la corbeille »", _r["message"] == "Prospect déplacé dans la corbeille")
verifier("A9. « Pas intéressé » n'inscrit RIEN au registre STOP", not _b["subscribers"].documents and _r["ne_plus_contacter"] is False)
_r3 = corbeiller(F3["id"])
verifier("A10. motif facultatif : accepté sans motif", _r3["motif"] is None)
verifier("A11. la corbeille existante liste l'élément (GET /trash du coach)",
         len(lancer(S.list_trash(RequeteFictive(jeton_=JA)))["items"]) == 2
         and len(lancer(S.list_trash(RequeteFictive(jeton_=JB)))["items"]) == 0)

# ============================================================================
print("\nB. LISTES ACTIVES / STATISTIQUES")
_l = lister()
verifier("B1. les fiches en corbeille sortent de la liste active",
         {p["id"] for p in _l["prospects"]} == {F1["id"]} and _l["total"] == 1, str([p["id"] for p in _l["prospects"]]))
verifier("B2. et des tuiles (total actif = 1) ; compteur « corbeille » = 2",
         _l["counts"]["total"] == 1 and _l["counts"]["corbeille"] == 2, str(_l["counts"]))
verifier("B3. statistiques / historique : `inclure_corbeille=1` les compte toujours",
         lister(inclure_corbeille="1")["total"] == 3)
verifier("B4. la fiche reste lisible par son id (Voir la fiche, historique)",
         lancer(S.p3s1_lire_prospect(F2["id"], RequeteFictive(jeton_=JA)))["corbeille"] is True)

# ============================================================================
print("\nC. RESTAURER (route EXISTANTE de la corbeille)")
verifier("C1. un autre coach ne restaure pas", code_erreur(lambda: restaurer(_r["trash_id"], jeton_=JB))[0] == 403)
_rr = restaurer(_r["trash_id"])
_f2 = [f for f in _b["partner_prospects"].documents if f["id"] == F2["id"]][0]
verifier("C2. la marque est retirée, la fiche revient intacte",
         _rr["restored"] and not any(k in _f2 for k in S.V627_CHAMPS_CORBEILLE) and _f2.get("restaure_par") == COACH_A
         and _f2["organisation_name"] == F2["organisation_name"])
verifier("C3. l'entrée de corbeille est retirée ; aucun doublon de fiche",
         len(_b["deleted_items"].documents) == 1
         and len([f for f in _b["partner_prospects"].documents if f["id"] == F2["id"]]) == 1)
verifier("C4. elle revient dans la liste active", F2["id"] in {p["id"] for p in lister()["prospects"]})

# ============================================================================
print("\nD. « NE SOUHAITE PLUS ÊTRE CONTACTÉ » : REFUS DURABLE")
# Sécurité : une adresse JAMAIS contactée par ce coach n'entre PAS au registre commun.
_rx = corbeiller(F2["id"], {"motif": "ne_plus_contacter"})
verifier("D0. adresse jamais contactée par ce coach : refus sur la fiche, RIEN au registre commun",
         _rx["registre_stop"] == [] and not _b["subscribers"].documents
         and [f for f in _b["partner_prospects"].documents if f["id"] == F2["id"]][0].get("ne_plus_contacter"))
# F1 a réellement reçu un J0 de ce coach : son refus va au registre canonique.
_b[S.P3S3_ACTIONS].documents.append({"id": "act-f1", "coach_id": COACH_A, "target": "un@exemple.test",
                                     "channel": "email", "sent_at": "2026-10-11T08:00:00+00:00"})
_rn = corbeiller(F1["id"], {"motif": "ne_plus_contacter"})
_f1 = [f for f in _b["partner_prospects"].documents if f["id"] == F1["id"]][0]
_stop = {(d["channel"], d["value"]): d["status"] for d in _b["subscribers"].documents}
verifier("D1. la fiche porte le refus durable", (_f1.get("ne_plus_contacter") or {}).get("par") == COACH_A)
verifier("D2. adresse réellement contactée : registre STOP canonique inscrit (e-mail) ; le WhatsApp jamais contacté, non",
         _stop.get(("email", "un@exemple.test")) == "opted_out" and ("whatsapp", "+41790000001") not in _stop, str(_stop))
_rr = restaurer(_rn["trash_id"])
_f1 = [f for f in _b["partner_prospects"].documents if f["id"] == F1["id"]][0]
verifier("D3. restauré : il quitte la corbeille MAIS le refus est CONSERVÉ",
         not _f1.get("corbeille") and _f1.get("ne_plus_contacter") and _rr["ne_plus_contacter"] is True)
verifier("D4. … et le registre STOP aussi", {(d["channel"], d["value"]): d["status"] for d in _b["subscribers"].documents}
         .get(("email", "un@exemple.test")) == "opted_out")

# ============================================================================
print("\nE. PLUS AUCUN ENVOI (côté serveur)")
_bp = prospects(F1, F2, F3)
_prep = lancer(S.p3s3_preparer_campagne(RequeteFictive(jeton_=JA, corps={
    "dry_run": False, "idempotency_key": "v627-e", "prospect_ids": [F1["id"], F2["id"], F3["id"]]})))
_cid = _prep["campaign"]["id"]
_bp[S.P3S3_CAMPAGNES].documents[0][S.P3S3D2_CHAMP_OBJET] = "Objet de banc"
lancer(S.p3s3_approuver_campagne(_cid, RequeteFictive(jeton_=JA, corps={})))
verifier("E0. campagne de TEST préparée PUIS approuvée avec 3 destinataires (avant la corbeille)",
         len(_bp[S.P3S3_ACTIONS].documents) == 3 and _bp[S.P3S3_CAMPAGNES].documents[0]["etat"] == "approuvee")
corbeiller(F2["id"], {"motif": "doublon"})
corbeiller(F3["id"], {"motif": "ne_plus_contacter"})
_sim = lancer(S.p3s3d_executer_campagne(_cid, COACH_A, simulation=True))
_codes = {r.get("recipient_key"): r.get("code") for r in _sim["resultats"]}
_k = {a["prospect_uuids"][0]: a["recipient_key"] for a in _bp[S.P3S3_ACTIONS].documents}
verifier("E1. J0 d'une campagne DÉJÀ APPROUVÉE : la fiche en corbeille est arrêtée (CORBEILLE)",
         _codes.get(_k[F2["id"]]) == "CORBEILLE", str(_codes))
verifier("E2. … la fiche SANS `ref` aussi (relue par son id) : NE_PLUS_CONTACTER",
         _codes.get(_k[F3["id"]]) in ("NE_PLUS_CONTACTER", "REFUS_EXPRIME"), str(_codes))
verifier("E3. la fiche active, elle, reste envoyable (aucun effet de bord)",
         _codes.get(_k[F1["id"]]) not in ("CORBEILLE", "NE_PLUS_CONTACTER"), str(_codes))
_rel = lancer(S.p3r2_relations_humaines(_bp[S.P3S3_ACTIONS].documents))
_par_uuid = {a["prospect_uuids"][0]: a["id"] for a in _bp[S.P3S3_ACTIONS].documents}
verifier("E4. relances J+3/J+7/J+14 (moteur ET boucle horaire) : bloquées",
         _rel.get(_par_uuid[F2["id"]]) == "prospect dans la corbeille"
         and _rel.get(_par_uuid[F3["id"]]) == "ne souhaite plus etre contacte" and _par_uuid[F1["id"]] not in _rel, str(_rel))
verifier("E5. pure : le refus durable passe avant la corbeille",
         S.v627_blocage([{"corbeille": True, "ne_plus_contacter": {"at": "x"}}]) == "NE_PLUS_CONTACTER"
         and S.v627_blocage([{}]) == "")
_p2 = lancer(S.p3s3_preparer_campagne(RequeteFictive(jeton_=JA, corps={
    "dry_run": True, "prospect_ids": [F1["id"], F2["id"], F3["id"]]})))
verifier("E6. nouvelle campagne : les fiches en corbeille / refus n'y entrent pas",
         _p2["summary"]["destinataires"] == 1, str(_p2["summary"]))
verifier("E7. la campagne existante n'est pas modifiée par la corbeille (actions intactes)",
         len(_bp[S.P3S3_ACTIONS].documents) == 3 and all(a["statut"] in ("pret", "bloque") for a in _bp[S.P3S3_ACTIONS].documents))
# Réponse manuelle : le banc V620 (même dossier), fiche rattachée mise à la corbeille.
_bv = base()
_bv["partner_prospects"] = Coll("partner_prospects", [dict(fiche_("TEST-620", "Partenaire Test", "Neuchatel"),
                                                           id="p-620", corbeille=True)])
_a = apercu()
verifier("E8. réponse manuelle : l'aperçu DIT que l'envoi est bloqué",
         _a["envoi_possible"] is False and _a["blocage_prospect"] == S.V627_MSG_CORBEILLE, str(_a.get("blocage_prospect")))
verifier("E9. … et « Confirmer l'envoi » est refusé (409), rien ne part",
         code_erreur(lambda: envoyer(_a["draft_hash"]))[0] == 409 and not APPELS)
_bv["partner_prospects"].documents[0].update(corbeille=False, ne_plus_contacter={"at": "x"})
verifier("E10. refus durable (fiche restaurée) : toujours refusé", code_erreur(lambda: envoyer(apercu()["draft_hash"]))[1] == S.V627_MSG_REFUS)

# ============================================================================
print("\nF. CONVERSATIONS ET HISTORIQUE")
_convs = [{"cle": "a1", "corbeille": True, "non_lues": 0}, {"cle": "a2", "corbeille": True, "non_lues": 2},
          {"cle": "a3", "corbeille": False, "non_lues": 0}]
verifier("F1. une conversation de prospect en corbeille sort de la liste active, SAUF s'il a écrit depuis (non lu)",
         [c["cle"] for c in S.v627_conversations_actives(_convs)] == ["a2", "a3"])
_bc = prospects(dict(F2, corbeille=True))
_conv = [{"cle": "act-x", "action_id": "act-x"}]
lancer(S.v625_categories_des_conversations(_conv, {"act-x": {"prospect_uuids": [F2["id"]]}}, COACH_A))
verifier("F3. la conversation porte le drapeau (badge « Corbeille »)", _conv[0]["corbeille"] is True)
verifier("F4. historique : aucune action, aucun message, aucune réponse envoyée n'est touché par la corbeille",
         _bp[S.P3S3_ACTIONS].ecritures >= 0 and all(a.get("sent_at") is None for a in _bp[S.P3S3_ACTIONS].documents)
         and "delete_many" not in io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
         .split("async def v627_mettre_en_corbeille")[1].split("async def _v592_prospect_du_coach")[0])

# ============================================================================
print("\nG. DOUBLONS : LA CORBEILLE EST VUE, UN REFUS N'EST JAMAIS RECRÉÉ")
_cle = lambda f: S.p3s1_cle_doublon(f["organisation_name"], f["city"])   # noqa: E731
_bd = prospects(dict(F1, corbeille=True, dedupe_key=_cle(F1)), dict(F2, ne_plus_contacter={"at": "x"}, dedupe_key=_cle(F2)))


def creer(**corps):
    return lancer(S.p3s1_creer_prospect(RequeteFictive(jeton_=JA, corps=dict(corps))))


_st, _d = code_erreur(lambda: creer(organisation_name="Studio TEST V627 Un", city="Neuchatel", category="festival"))
verifier("G1. un homonyme d'une fiche EN CORBEILLE est signalé (409, « corbeille »)",
         _st == 409 and any(x.get("corbeille") for x in _d["possible_duplicates"]), str(_d))
_st, _d = code_erreur(lambda: creer(organisation_name="Autre nom", city="Lausanne", category="festival",
                                    public_email="deux@exemple.test", allow_duplicate=True))
verifier("G2. même e-mail qu'un refus durable : JAMAIS recréé, même avec allow_duplicate",
         _st == 409 and _d.get("code") == "NE_PLUS_CONTACTER", str(_d))
_bd["subscribers"].documents.append({"channel": "email", "value": "stop@exemple.test", "status": "opted_out"})
JSA = _g["_espace"]["jeton"]("contact.artboost@gmail.com")
_st, _d = code_erreur(lambda: lancer(S.p3s1_creer_prospect(RequeteFictive(jeton_=JSA, corps=dict(
    organisation_name="Encore autre", city="Bienne", category="festival", public_email="stop@exemple.test",
    allow_duplicate=True)))))
verifier("G3. super-admin (propriétaire du registre) : adresse au registre STOP jamais recréée",
         _st == 409 and _d.get("code") == "NE_PLUS_CONTACTER", str(_d))
_st, _d = code_erreur(lambda: creer(organisation_name="Encore autre", city="Bienne", category="festival",
                                    public_email="stop@exemple.test", allow_duplicate=True))
verifier("G3-bis. un autre coach n'interroge PAS le registre commun (aucun oracle d'appartenance)", _st is None, str(_d))
_ok = creer(organisation_name="Studio TEST V627 Un", city="Neuchatel", category="festival", allow_duplicate=True)
verifier("G4. un simple homonyme en corbeille (sans refus) reste créable si le coach confirme",
         (_ok.get("prospect") or _ok).get("organisation_name") == "Studio TEST V627 Un")
import importlib.util as _ilu   # noqa: E402
_spec = _ilu.spec_from_file_location("import_cowork", os.path.join(RACINE, "tests", "import_prospects_cowork.py"))
_imp = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_imp)
_bi = prospects(dict(F1, corbeille=True), dict(F2, ne_plus_contacter={"at": "x"}))
_docs = [dict(ref="TST-V627-1", organisation_name="Studio TEST V627 Un", city="Neuchatel", category="festival"),
         dict(ref="NOUVEAU-1", organisation_name="Nouveau nom", city="Lausanne", category="festival",
              public_email="deux@exemple.test")]
_plan = lancer(_imp.planifier(_bi, [dict(d) for d in _docs], COACH_A))
_conf = {d["ref"]: m for d, m in _plan["conflits"]}
verifier("G5. import : une fiche en corbeille n'est pas réécrite (conflit explicite)",
         "TST-V627-1" in _conf and "corbeille" in _conf["TST-V627-1"][0], str(_conf))
verifier("G6. import : un refus durable n'est JAMAIS réimporté comme nouveau",
         "NOUVEAU-1" in _conf and not _plan["nouveaux"], str(_conf))
verifier("G7. import : les champs corbeille / refus sont intouchables",
         "corbeille" in _imp.CHAMPS_INTOUCHABLES and "ne_plus_contacter" in _imp.CHAMPS_INTOUCHABLES)

# ============================================================================
print("\nI. AUCUN E-MAIL RÉEL, AUCUNE SORTIE RÉSEAU")
verifier("I1. aucune sortie réseau tentée", not _TENTATIVES, str(_TENTATIVES))
verifier("I2. aucun appel au fournisseur d'e-mail", not APPELS)

print("\n" + "=" * 78)
_echecs = [r for r in RESULTATS if not r[1]]
print("V627 CORBEILLE DES PROSPECTS — %d vérifications, %d échec(s)" % (len(RESULTATS), len(_echecs)))
print("=" * 78)
sys.exit(1 if _echecs else 0)
