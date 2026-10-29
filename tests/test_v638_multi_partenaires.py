#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V638 — Système multi-partenaires Afroboost (TDD).

Sections :
  [1] CRUD partenaire (créer / lister / modifier / supprimer)
  [2] Isolation multi-coach
  [3] Détails agrégés (plusieurs codes)
  [4] Déduplication (session_id entre codes du même partenaire)
  [5] Conflits inter-partenaires (signaler ≠ répartir)
  [6] Jeton au niveau partenaire
  [7] Espèces au niveau partenaire
  [8] Vue publique agrégée (anonymisée)
  [9] Rétrocompatibilité /codes/{code}/
  [10] Sécurité et non-régression

Lancement :  python3 tests/test_v638_multi_partenaires.py
"""
import asyncio, json, os, sys, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_parrainage_v3 as V3
H = V3.H
RESULTATS = []

import api.routes.partner_routes as PR

COACH1 = H.ADMIN
COACH2 = "autrecoach@exemple.test"
HETAIRA10  = "HETAIRA10"
HETAIRA20  = "HETAIRA20"
FOOBAR5    = "FOOBAR5"
INV_ID_1   = "inv-smart-link-001"
SESSION_H10_1   = "cs_h10_001"
SESSION_H10_2   = "cs_h10_002"
SESSION_H20_1   = "cs_h20_001"
SESSION_CONFLIT = "cs_conflit_001"
SESSION_INV     = "cs_inv_001"
DATE_SEANCE = "2026-11-11T18:45:00+01:00"

def jeton1(): return {"Authorization": "Bearer " + H.jeton_admin(COACH1)}
def jeton2(): return {"Authorization": "Bearer " + H.jeton_admin(COACH2)}
def req(entetes=None): return H.Requete({}, entetes or {})
def pd(name, pct, codes, inv=None):
    return PR.PartenaireData(name=name, pct=pct, codes=codes, invitation_ids=inv or [])
async def appel(coro): return await H.appel(coro)
def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))

def base_multi():
    base, _ = H.base_de_depart()
    base["discount_codes"].docs += [
        {"id":"dc-h10","code":HETAIRA10,"active":True,"maxUses":50,"used":0,"coach_id":COACH1,"type":"CHF","value":10},
        {"id":"dc-h20","code":HETAIRA20,"active":True,"maxUses":50,"used":0,"coach_id":COACH1,"type":"CHF","value":5},
        {"id":"dc-fb5","code":FOOBAR5,  "active":True,"maxUses":50,"used":0,"coach_id":COACH1,"type":"PCT","value":5},
        {"id":"dc-c2", "code":"COACH2CODE","active":True,"maxUses":10,"used":0,"coach_id":COACH2,"type":"CHF","value":5},
    ]
    base["payment_transactions"].docs += [
        {"session_id":SESSION_H10_1,"customer_name":"Alice Martin","customer_email":"alice@test.ch","promo_code":HETAIRA10,"tarif_applique":20.0,"tarif_public":30.0,"quantity":1,"payment_status":"paid","coach_id":COACH1,"created_at":"2026-11-01T10:00:00Z"},
        {"session_id":SESSION_H10_2,"customer_name":"Bruno Keller","customer_email":"bruno@test.ch","promo_code":HETAIRA10,"tarif_applique":20.0,"tarif_public":30.0,"quantity":1,"payment_status":"paid","coach_id":COACH1,"created_at":"2026-11-02T11:00:00Z"},
        {"session_id":SESSION_CONFLIT,"customer_name":"Chloé Favre","customer_email":"chloe@test.ch","promo_code":HETAIRA10,"tarif_applique":20.0,"tarif_public":30.0,"quantity":1,"payment_status":"paid","coach_id":COACH1,"created_at":"2026-11-03T09:00:00Z"},
        {"session_id":SESSION_CONFLIT,"customer_name":"Chloé Favre","customer_email":"chloe@test.ch","promo_code":FOOBAR5,"tarif_applique":20.0,"tarif_public":30.0,"quantity":1,"payment_status":"paid","coach_id":COACH1,"created_at":"2026-11-03T09:00:00Z"},
        {"session_id":SESSION_H20_1,"customer_name":"Diane Müller","customer_email":"diane@test.ch","promo_code":HETAIRA20,"tarif_applique":25.0,"tarif_public":30.0,"quantity":1,"payment_status":"paid","coach_id":COACH1,"created_at":"2026-11-04T08:00:00Z"},
        {"session_id":SESSION_INV,"customer_name":"Eva Blanc","customer_email":"eva@test.ch","promo_code":None,"tarif_applique":30.0,"tarif_public":30.0,"quantity":1,"payment_status":"paid","coach_id":COACH1,"created_at":"2026-11-05T07:00:00Z"},
    ]
    base["reservations"].docs += [
        {"id":"r-h10-1","userName":"Alice Martin","userEmail":"alice@test.ch","promoCode":HETAIRA10,"stripeSessionId":SESSION_H10_1,"courseName":"Cours à l'unité","datetime":DATE_SEANCE,"coach_id":COACH1},
        {"id":"r-h10-2","userName":"Bruno Keller","userEmail":"bruno@test.ch","promoCode":HETAIRA10,"stripeSessionId":SESSION_H10_2,"courseName":"Cours à l'unité","datetime":DATE_SEANCE,"coach_id":COACH1},
        {"id":"r-conflit-1","userName":"Chloé Favre","userEmail":"chloe@test.ch","promoCode":HETAIRA10,"stripeSessionId":SESSION_CONFLIT,"courseName":"Cours à l'unité","datetime":DATE_SEANCE,"coach_id":COACH1},
        {"id":"r-h20-1","userName":"Diane Müller","userEmail":"diane@test.ch","promoCode":HETAIRA20,"stripeSessionId":SESSION_H20_1,"courseName":"Cours à l'unité","datetime":DATE_SEANCE,"coach_id":COACH1},
        {"id":"r-inv-1","userName":"Eva Blanc","userEmail":"eva@test.ch","invitation_id":INV_ID_1,"stripeSessionId":SESSION_INV,"courseName":"Cours à l'unité","datetime":DATE_SEANCE,"coach_id":COACH1},
    ]
    PR.init_partner_db(base)
    return base

# ══ Section 1 ═════════════════════════════════════════════════════════════════
async def section_crud():
    base_multi()
    c, r = await appel(PR.creer_partenaire(pd("Société Hétaïra",40,[HETAIRA10]), req(jeton1())))
    verifier("1.1 créer → 201", c==201, (c,r))
    pid = (r or {}).get("id","")
    verifier("1.1b id présent", bool(pid))
    verifier("1.1c name", r.get("name")=="Société Hétaïra", r)
    verifier("1.1d pct=40", r.get("pct")==40, r)
    verifier("1.1e code", HETAIRA10 in r.get("codes",[]), r)

    c2,r2 = await appel(PR.lister_partenaires(req(jeton1())))
    verifier("1.2 lister → 200", c2==200)
    verifier("1.2b présent dans liste", any(p["id"]==pid for p in r2.get("partenaires",[])))

    c3,r3 = await appel(PR.obtenir_partenaire(pid, req(jeton1())))
    verifier("1.3 obtenir → 200", c3==200)
    verifier("1.3b nom correct", r3.get("name")=="Société Hétaïra", r3)

    c4,r4 = await appel(PR.modifier_partenaire(pid, pd("Hétaïra Sàrl",35,[HETAIRA10,HETAIRA20],[INV_ID_1]), req(jeton1())))
    verifier("1.4 modifier → 200", c4==200)
    _,r4b = await appel(PR.obtenir_partenaire(pid, req(jeton1())))
    verifier("1.4b nom modifié", r4b.get("name")=="Hétaïra Sàrl", r4b)
    verifier("1.4c pct=35", r4b.get("pct")==35, r4b)
    verifier("1.4d code ajouté", HETAIRA20 in r4b.get("codes",[]), r4b)
    verifier("1.4e inv ajoutée", INV_ID_1 in r4b.get("invitation_ids",[]), r4b)

    _,rt = await appel(PR.creer_partenaire(pd("Tmp",50,[]), req(jeton1())))
    ptmp = rt["id"]
    cd,_ = await appel(PR.supprimer_partenaire(ptmp, req(jeton1())))
    verifier("1.5 supprimer → 200", cd==200)
    _,rl2 = await appel(PR.lister_partenaires(req(jeton1())))
    verifier("1.5b absent après suppression", not any(p["id"]==ptmp for p in rl2.get("partenaires",[])))

    c6,r6 = await appel(PR.creer_partenaire(pd("Gym Pro",25,[FOOBAR5]), req(jeton1())))
    verifier("1.6 arbitraire → 201", c6==201)
    verifier("1.6b pct=25", r6.get("pct")==25, r6)

# ══ Section 2 ═════════════════════════════════════════════════════════════════
async def section_isolation():
    base_multi()
    _,r1 = await appel(PR.creer_partenaire(pd("Coach1 Partner",40,[HETAIRA10]), req(jeton1())))
    pid1 = r1["id"]

    _,r2 = await appel(PR.lister_partenaires(req(jeton2())))
    verifier("2.1 coach2 ne voit pas les partenaires de coach1", not any(p["id"]==pid1 for p in r2.get("partenaires",[])))

    c3,_ = await appel(PR.obtenir_partenaire(pid1, req(jeton2())))
    verifier("2.2 obtenir autre coach → 403/404", c3 in (403,404), c3)

    c4,_ = await appel(PR.modifier_partenaire(pid1, pd("Hack",100,[]), req(jeton2())))
    verifier("2.3 modifier autre coach → 403/404", c4 in (403,404), c4)

    c5,_ = await appel(PR.supprimer_partenaire(pid1, req(jeton2())))
    verifier("2.4 supprimer autre coach → 403/404", c5 in (403,404), c5)

    c6,_ = await appel(PR.details_partenaire(pid1, req(jeton2())))
    verifier("2.5 détails autre coach → 403/404", c6 in (403,404), c6)

    c7,_ = await appel(PR.lister_partenaires(req()))
    verifier("2.6 sans JWT → 403", c7==403, c7)

# ══ Section 3 ═════════════════════════════════════════════════════════════════
async def section_details_agrege():
    base_multi()
    _,rp = await appel(PR.creer_partenaire(pd("Hétaïra",40,[HETAIRA10,HETAIRA20]), req(jeton1())))
    pid = rp["id"]

    c,r = await appel(PR.details_partenaire(pid, req(jeton1())))
    verifier("3.1 détails → 200", c==200)
    lignes = r.get("lignes",[])
    totaux = r.get("totaux",{})
    sids = [l.get("session_id") for l in lignes if l.get("session_id")]

    verifier("3.2 H10_1 présent", SESSION_H10_1 in sids, sids)
    verifier("3.3 H10_2 présent", SESSION_H10_2 in sids, sids)
    verifier("3.4 H20_1 présent", SESSION_H20_1 in sids, sids)
    verifier("3.5 >= 4 lignes", len(lignes)>=4, len(lignes))

    net = totaux.get("total_net_chf",0)
    verifier("3.6 net >= 85 CHF", net>=85.0, net)
    pp = totaux.get("part_partenaire_chf",0)
    verifier("3.7 part pct=40", abs(pp - round(net*0.40,2))<0.01, (pp,net))
    pa = totaux.get("part_afroboost_chf",0)
    verifier("3.8 part AF=60%", abs(pa - round(net*0.60,2))<0.01, (pa,net))

    await appel(PR.modifier_partenaire(pid, pd("Hétaïra",30,[HETAIRA10,HETAIRA20]), req(jeton1())))
    _,r2 = await appel(PR.details_partenaire(pid, req(jeton1())))
    n2 = r2.get("totaux",{}).get("total_net_chf",0)
    p2 = r2.get("totaux",{}).get("part_partenaire_chf",0)
    verifier("3.9 pct=30 appliqué", abs(p2 - round(n2*0.30,2))<0.01, (p2,n2))

# ══ Section 4 ═════════════════════════════════════════════════════════════════
async def section_deduplication():
    base_multi()
    _,rp = await appel(PR.creer_partenaire(pd("Test Dedup",40,[HETAIRA10,FOOBAR5]), req(jeton1())))
    _,r = await appel(PR.details_partenaire(rp["id"], req(jeton1())))
    sids = [l.get("session_id") for l in r.get("lignes",[]) if l.get("session_id")]
    verifier("4.1 SESSION_CONFLIT comptée 1 fois", sids.count(SESSION_CONFLIT)==1, (sids.count(SESSION_CONFLIT), sids))
    nn = [s for s in sids if s]
    verifier("4.2 aucun session_id en double", len(nn)==len(set(nn)), nn)

# ══ Section 5 ═════════════════════════════════════════════════════════════════
async def section_conflits():
    base_multi()
    _,rA = await appel(PR.creer_partenaire(pd("A",40,[HETAIRA10]), req(jeton1())))
    _,rB = await appel(PR.creer_partenaire(pd("B",30,[FOOBAR5]),  req(jeton1())))

    c,r = await appel(PR.conflits_partenaires(req(jeton1())))
    verifier("5.1 conflits → 200", c==200)
    conflits = r.get("conflits",[])
    sid_conflits = [cf.get("session_id") for cf in conflits]
    verifier("5.2 SESSION_CONFLIT détecté", SESSION_CONFLIT in sid_conflits, sid_conflits)

    cf_doc = next((cf for cf in conflits if cf.get("session_id")==SESSION_CONFLIT), None)
    verifier("5.3 2 partenaires en conflit", cf_doc and len(cf_doc.get("partenaires",[]))==2, cf_doc)

    _,rAd = await appel(PR.details_partenaire(rA["id"], req(jeton1())))
    _,rBd = await appel(PR.details_partenaire(rB["id"], req(jeton1())))
    sA = [l.get("session_id") for l in rAd.get("lignes",[])]
    sB = [l.get("session_id") for l in rBd.get("lignes",[])]
    verifier("5.4a A voit SESSION_CONFLIT", SESSION_CONFLIT in sA, sA)
    verifier("5.4b B voit SESSION_CONFLIT", SESSION_CONFLIT in sB, sB)

    _,rC = await appel(PR.creer_partenaire(pd("C",50,[HETAIRA20]), req(jeton1())))
    ids_en_conflit = {p.get("id") for cf in conflits for p in cf.get("partenaires",[])}
    verifier("5.5 C absent des conflits", rC["id"] not in ids_en_conflit)

    c6,_ = await appel(PR.conflits_partenaires(req()))
    verifier("5.6 conflits sans JWT → 403", c6==403, c6)

# ══ Section 6 ═════════════════════════════════════════════════════════════════
async def section_jeton():
    from fastapi import Response as FR
    base_multi()
    _,rp = await appel(PR.creer_partenaire(pd("Hétaïra Jeton",40,[HETAIRA10]), req(jeton1())))
    pid = rp["id"]

    c1,r1 = await appel(PR.generer_token_partenaire_v2(pid, req(jeton1())))
    verifier("6.1 générer jeton → 200/201", c1 in (200,201), (c1,r1))
    token = r1.get("token","")
    verifier("6.2 token >= 20 chars", len(token)>=20, token)
    verifier("6.3 token_id présent", bool(r1.get("token_id")), r1)

    c2,r2 = await appel(PR.vue_partenaire(token, req(), FR()))
    verifier("6.4 vue_partenaire → 200", c2==200, (c2,r2))
    verifier("6.5 code(s) présent", bool(r2.get("code") or r2.get("codes")), r2)
    verifier("6.6 totaux présents", bool(r2.get("totaux")), r2)
    verifier("6.7 pas d'email exposé", "@test.ch" not in json.dumps(r2,default=str), r2)

    c3,_ = await appel(PR.vue_partenaire("a"*50, req(), FR()))
    verifier("6.8 token invalide → 404", c3==404, c3)

    _,r_new = await appel(PR.generer_token_partenaire_v2(pid, req(jeton1())))
    token_new = r_new.get("token","")
    c4,_ = await appel(PR.vue_partenaire(token, req(), FR()))
    verifier("6.9 ancien token révoqué → 404", c4==404, c4)
    c5,_ = await appel(PR.vue_partenaire(token_new, req(), FR()))
    verifier("6.10 nouveau token → 200", c5==200, c5)

    c6,_ = await appel(PR.revoquer_token_partenaire_v2(pid, req(jeton1())))
    verifier("6.11 révoquer → 200", c6==200)
    c7,_ = await appel(PR.vue_partenaire(token_new, req(), FR()))
    verifier("6.12 révoqué → 404", c7==404, c7)

    c8,_ = await appel(PR.generer_token_partenaire_v2(pid, req(jeton2())))
    verifier("6.13 jeton autre coach → 403/404", c8 in (403,404), c8)

# ══ Section 7 ═════════════════════════════════════════════════════════════════
async def section_especes():
    base_multi()
    _,rp = await appel(PR.creer_partenaire(pd("Hétaïra Esp",40,[HETAIRA10]), req(jeton1())))
    pid = rp["id"]

    dc = PR.EspecesDeclaration(prenom="François",nom="Dupont",date_seance="2026-11-11",montant_chf=30.0,idempotence_key=f"{pid}:e001")

    c1,r1 = await appel(PR.declarer_especes_partenaire(pid, dc, req(jeton1())))
    verifier("7.1 espèces → 200/201", c1 in (200,201), (c1,r1))
    verifier("7.2 id présent", bool(r1.get("id")), r1)
    verifier("7.3 pas doublon", r1.get("doublon") is False, r1)

    _,rd = await appel(PR.details_partenaire(pid, req(jeton1())))
    lignes_esp = [l for l in rd.get("lignes",[]) if l.get("moyen")=="especes"]
    verifier("7.4 espèces dans détails", len(lignes_esp)>=1, lignes_esp)
    verifier("7.5 montant=30", any(l.get("montant_chf")==30.0 for l in lignes_esp), lignes_esp)

    c2,r2 = await appel(PR.declarer_especes_partenaire(pid, dc, req(jeton1())))
    verifier("7.6 doublon détecté", r2.get("doublon") is True, (c2,r2))

    dh = PR.EspecesDeclaration(prenom="Hack",nom="Att",date_seance="2026-11-11",montant_chf=1000.0,idempotence_key=f"{pid}:hack")
    c3,_ = await appel(PR.declarer_especes_partenaire(pid, dh, req(jeton2())))
    verifier("7.7 espèces autre coach → 403/404", c3 in (403,404), c3)

# ══ Section 8 ═════════════════════════════════════════════════════════════════
async def section_vue_publique():
    from fastapi import Response as FR
    base_multi()
    _,rp = await appel(PR.creer_partenaire(pd("Hétaïra Pub",40,[HETAIRA10,HETAIRA20]), req(jeton1())))
    _,rt = await appel(PR.generer_token_partenaire_v2(rp["id"], req(jeton1())))
    token = rt["token"]

    c,r = await appel(PR.vue_partenaire(token, req(), FR()))
    verifier("8.1 vue publique → 200", c==200)
    lignes = r.get("lignes",[])
    totaux = r.get("totaux",{})

    for l in lignes:
        nom = l.get("nom_masque","")
        if nom and " " in nom:
            verifier(f"8.2 nom masqué {nom}", nom.split()[-1].endswith("."), nom)

    s = json.dumps(r,ensure_ascii=False,default=str).lower()
    verifier("8.3 aucun champ sensible", not any(k in s for k in ("token_hash",)), s[:50])

    verifier("8.4 totaux présents", totaux.get("total_net_chf") is not None, totaux)
    verifier("8.5 part_partenaire présente", totaux.get("part_partenaire_chf") is not None, totaux)
    verifier("8.6 >= 2 lignes", len(lignes)>=2, len(lignes))

    emails = [e for e in ("alice@test.ch","bruno@test.ch","diane@test.ch") if e in json.dumps(r,default=str)]
    verifier("8.7 aucun email exposé", not emails, emails)

# ══ Section 9 ═════════════════════════════════════════════════════════════════
async def section_retrocompat():
    from fastapi import Response as FR
    base_multi()

    c1,r1 = await appel(PR.details_code(HETAIRA10, req(jeton1())))
    verifier("9.1 /codes/HETAIRA10/details → 200", c1==200)
    verifier("9.2 lignes non vides", len(r1.get("lignes",[]))>=1, r1)

    c3,r3 = await appel(PR.config_partenaire(HETAIRA10, PR.ConfigPartenaire(partner_name="Test",partner_pct=45), req(jeton1())))
    verifier("9.3 /codes/.../config → 200", c3==200)

    c4,r4 = await appel(PR.generer_token_partenaire(HETAIRA10, req(jeton1())))
    verifier("9.4 /codes/.../generate-token → 200", c4 in (200,201))
    token_code = r4.get("token","")
    c5,_ = await appel(PR.vue_partenaire(token_code, req(), FR()))
    verifier("9.5 vue_partenaire via token-code → 200", c5==200, c5)

    c6,r6 = await appel(PR.export_csv(HETAIRA10, req(jeton1())))
    verifier("9.6 /codes/.../export.csv → 200", c6==200)

# ══ Section 10 ════════════════════════════════════════════════════════════════
async def section_securite():
    base = base_multi()

    try:
        PR.PartenaireData(name="T",pct=101,codes=[],invitation_ids=[])
        verifier("10.1 pct>100 rejeté", False)
    except Exception:
        verifier("10.1 pct>100 rejeté", True)

    try:
        PR.PartenaireData(name="T",pct=-1,codes=[],invitation_ids=[])
        verifier("10.2 pct<0 rejeté", False)
    except Exception:
        verifier("10.2 pct<0 rejeté", True)

    try:
        PR.PartenaireData(name="",pct=40,codes=[],invitation_ids=[])
        verifier("10.3 nom vide rejeté", False)
    except Exception:
        verifier("10.3 nom vide rejeté", True)

    c4,_ = await appel(PR.creer_partenaire(pd("Hack",40,[]), req()))
    verifier("10.4 sans JWT → 403", c4==403, c4)

    base2 = base_multi()
    base2["payment_transactions"].docs.append({"session_id":"cs_inj","customer_name":'=HYPERLINK("http://evil.com","!")','customer_email':"ev@ev.ev","promo_code":HETAIRA10,"tarif_applique":20.0,"tarif_public":30.0,"quantity":1,"payment_status":"paid","coach_id":COACH1,"created_at":"2026-11-10T10:00:00Z"})
    PR.init_partner_db(base2)
    _,rp2 = await appel(PR.creer_partenaire(pd("CSV Test",40,[HETAIRA10]), req(jeton1())))
    c5,r5 = await appel(PR.export_csv_partenaire(rp2["id"], req(jeton1())))
    if c5==200:
        content = getattr(r5,"body",b"").decode("utf-8-sig","replace") if hasattr(r5,"body") else str(r5)
        verifier("10.5 CSV anti-injection", "'=HYPERLINK" in content, content[:120])
    else:
        verifier("10.5 CSV export → 200", False, c5)

    PR.init_partner_db(base)
    c6,r6 = await appel(PR.details_code(HETAIRA10, req(jeton1())))
    verifier("10.6 routes /codes/ non cassées", c6==200 and len(r6.get("lignes",[]))>=1, (c6,len(r6.get("lignes",[]))))

# ══ Exécution ═════════════════════════════════════════════════════════════════
async def run():
    SECTIONS = [
        ("[1/10] CRUD partenaire",            section_crud),
        ("[2/10] Isolation multi-coach",       section_isolation),
        ("[3/10] Détails agrégés",             section_details_agrege),
        ("[4/10] Déduplication",               section_deduplication),
        ("[5/10] Conflits inter-partenaires",  section_conflits),
        ("[6/10] Jeton partenaire",            section_jeton),
        ("[7/10] Espèces partenaire",          section_especes),
        ("[8/10] Vue publique agrégée",        section_vue_publique),
        ("[9/10] Rétrocompatibilité",          section_retrocompat),
        ("[10/10] Sécurité",                   section_securite),
    ]
    print("V638 — Système multi-partenaires")
    print("═"*50)
    for label, fn in SECTIONS:
        print(f"  {label}")
        try:
            await fn()
        except Exception:
            RESULTATS.append((f"CRASH {label}", False, traceback.format_exc()[-300:]))

    ok  = sum(1 for _,b,_ in RESULTATS if b)
    ko  = [(n,d) for n,b,d in RESULTATS if not b]
    print(); print("═"*50)
    print(f"Résultat : {ok}/{len(RESULTATS)} tests réussis")
    if ko:
        print("\nÉchecs :")
        for n,d in ko:
            print(f"  ✗ {n}  →  {str(d)[:120]}")
    else:
        print("\nTous les tests sont au vert ✓")
    return len(ko)

if __name__=="__main__":
    sys.exit(0 if asyncio.run(run())==0 else 1)
