/**
 * LOT R — LA RECHARGE PULSE, DANS UN VRAI NAVIGATEUR.
 *
 * CE QUE CE BANC PROUVE, ET QUE LE BANC PYTHON NE PROUVE PAS. Le banc Python
 * juge la REGLE sur une base en memoire qui IGNORE LES PROJECTIONS. Ici : un
 * vrai mongod, un vrai FastAPI, un vrai Chromium, un vrai JWT. Une garde
 * oubliee sur une porte se voit tout de suite.
 *
 * LES SEPT CAS DU PROPRIETAIRE :
 *   A. membre actif + 0 seance -> voit la recharge, et obtient 10 seances.
 *   B. membre actif + 3 seances -> pas de recharge.
 *   C. non-membre               -> refuse cote SERVEUR.
 *   D. membre expire            -> refuse.
 *   E. double confirmation      -> une seule recharge.
 *   F. achat de recharge        -> AUCUN nouveau membership.
 *   G. PULSE 250 initial        -> 10 seances + membership.
 *
 * AUCUNE DONNEE DE PRODUCTION : mongod jetable sur un port dedie, base
 * detruite a la fin. Le navigateur ne peut joindre que 127.0.0.1.
 *
 *   node tests/test_lotr_navigateur.mjs
 */
import fs from 'fs';
import os from 'os';
import path from 'path';
import { spawn, spawnSync } from 'child_process';
import { createRequire } from 'module';

const require_ = createRequire(import.meta.url);
const { chromium } = require_('/Users/afroboost/.claude/skills/gstack/node_modules/playwright-core');

const DEPOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const PY = process.env.AFROBOOST_PY || '/tmp/venv-prod/bin/python';
const MONGOD = process.env.AFROBOOST_MONGOD || 'mongod';
const PORT_MONGO = 28025;
const PORT_API = 8103;
const BASE = `http://127.0.0.1:${PORT_API}`;
const DBDIR = path.join(os.tmpdir(), 'afroboost-lotr-mongo');
const DBNAME = 'lotr_recharge';

const OFFRE_250 = 'offre-entree-250';
const OFFRE_150 = 'offre-recharge-150';
const MDP = 'MotDePasseTest!2026';

// Quatre clients, un par cas. Codes d'acces distincts : l'espace abonne se lit
// par le code, jamais par une session.
const CLIENTS = {
  vide:    { email: 'membre.vide@ex.test',    code: 'LOTR-VIDE',    seances: 0 },
  garni:   { email: 'membre.garni@ex.test',   code: 'LOTR-GARNI',   seances: 3 },
  inconnu: { email: 'sans.adhesion@ex.test',  code: 'LOTR-INCONNU', seances: 0 },
  echu:    { email: 'membre.echu@ex.test',    code: 'LOTR-ECHU',    seances: 0 },
};

const resultats = [];
function verifier(titre, condition, detail) {
  resultats.push({ titre, ok: !!condition, detail: detail || '' });
  console.log(`${condition ? '  OK  ' : ' ECHEC'} ${titre}${condition || !detail ? '' : ` -> ${detail}`}`);
}
const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

async function attendre(url, essais = 40) {
  for (let i = 0; i < essais; i++) {
    try { const r = await fetch(url); if (r.ok) return true; } catch { /* pas encore */ }
    await dormir(500);
  }
  return false;
}

function py(script) {
  const r = spawnSync(PY, ['-c', script], { encoding: 'utf-8' });
  return (r.stdout || '') + (r.stderr || '');
}

// L'annee en cours, pour que « adhesion active » le soit vraiment le jour du test.
const AN = new Date().getFullYear();

function semer() {
  const s = `
import pymongo
c = pymongo.MongoClient("mongodb://127.0.0.1:${PORT_MONGO}")
d = c["${DBNAME}"]
for n in ("reservations","subscriptions","discount_codes","coaches","courses",
          "offers","memberships","payment_transactions","code_members"):
    d[n].delete_many({})

# ── LE CATALOGUE : deux offres, et la SEULE difference qui compte est un
#    booleen declare — jamais un montant. ──────────────────────────────────
d.offers.insert_many([
  {"id":"${OFFRE_250}","name":"PULSE x10 cours","price":250.0,"pack_sessions":10,
   "visible":True,"position":1,"category":"service","coach_id":None,
   "creates_membership":True,"first_purchase_eligible":True,
   "requires_active_membership":False,"progressive_pricing":False},
  {"id":"${OFFRE_150}","name":"PULSE x10 — recharge","price":150.0,"pack_sessions":10,
   "visible":False,"position":2,"category":"service","coach_id":None,
   "creates_membership":False,"first_purchase_eligible":False,
   "requires_active_membership":True,"progressive_pricing":False},
])

def _forfait(email, code, reste):
    return {"id":"sub-"+code,"code":code,"email":email,"name":email.split("@")[0],
            "coach_id":None,"status":"active","offer_name":"PULSE x10 cours",
            "total_sessions":10,"used_sessions":10-reste,"remaining_sessions":reste,
            "expires_at":"${AN}-12-31T23:59:59+00:00",
            "created_at":"${AN}-01-15T10:00:00+00:00"}

def _code(email, code, reste):
    return {"id":"dc-"+code,"code":code,"type":"100%","value":100,
            "assignedEmail":email,"maxUses":10,"used":10-reste,"active":True,
            "courses":[],"stripe_amount":250.0,
            "expiresAt":"${AN}-12-31","created_at":"${AN}-01-15T10:00:00+00:00"}

def _adhesion(email, debut, fin):
    return {"_id":"adh:sub-"+email,"id":"adh-"+email,"email":email,"coach_id":None,
            "date_debut":debut,"date_fin":fin,"source":"achat",
            "offer_id":"${OFFRE_250}","subscription_id":"sub-x"}

d.subscriptions.insert_many([
  _forfait("${CLIENTS.vide.email}",    "${CLIENTS.vide.code}",    0),
  _forfait("${CLIENTS.garni.email}",   "${CLIENTS.garni.code}",   3),
  _forfait("${CLIENTS.inconnu.email}", "${CLIENTS.inconnu.code}", 0),
  _forfait("${CLIENTS.echu.email}",    "${CLIENTS.echu.code}",    0),
])
d.discount_codes.insert_many([
  _code("${CLIENTS.vide.email}",    "${CLIENTS.vide.code}",    0),
  _code("${CLIENTS.garni.email}",   "${CLIENTS.garni.code}",   3),
  _code("${CLIENTS.inconnu.email}", "${CLIENTS.inconnu.code}", 0),
  _code("${CLIENTS.echu.email}",    "${CLIENTS.echu.code}",    0),
])
# Trois adhesions : une VALIDE, une ECHUE, et rien pour l'inconnu.
d.memberships.insert_many([
  _adhesion("${CLIENTS.vide.email}",  "${AN}-01-01", "${AN}-12-31"),
  _adhesion("${CLIENTS.garni.email}", "${AN}-01-01", "${AN}-12-31"),
  _adhesion("${CLIENTS.echu.email}",  "${AN - 2}-01-01", "${AN - 2}-12-31"),
])
print("SEME")`;
  if (!py(s).includes('SEME')) throw new Error('semis impossible');
}

async function principal() {
  fs.rmSync(DBDIR, { recursive: true, force: true });
  fs.mkdirSync(DBDIR, { recursive: true });
  const mongo = spawn(MONGOD, ['--dbpath', DBDIR, '--port', String(PORT_MONGO),
    '--bind_ip', '127.0.0.1'], { stdio: 'ignore' });
  const api = spawn(PY, ['-m', 'uvicorn', 'api.server:app', '--host', '127.0.0.1',
    '--port', String(PORT_API), '--log-level', 'warning'], {
    cwd: DEPOT, stdio: ['ignore', 'ignore', 'pipe'],
    env: { ...process.env, MONGO_URL: `mongodb://127.0.0.1:${PORT_MONGO}`,
           DB_NAME: DBNAME, JWT_SECRET: 'test-secret-lotr' },
  });
  let journal = '';
  api.stderr.on('data', (b) => { journal += b.toString(); });

  let navigateur;
  try {
    await dormir(1500);
    if (!await attendre(`${BASE}/healthz`)) {
      console.error('Backend non demarre.\n' + journal.slice(-2500));
      return 2;
    }
    semer();

    navigateur = await chromium.launch({ headless: true });
    const ctx = await navigateur.newContext({ baseURL: BASE,
      viewport: { width: 390, height: 844 } });   // MOBILE D'ABORD
    await ctx.route('**/*', (route) => {
      const u = new URL(route.request().url());
      if (u.hostname !== '127.0.0.1') return route.abort();
      return route.continue();
    });
    const page = await ctx.newPage();
    await page.goto('/healthz');

    const espace = (code) => page.evaluate(async (c) => {
      const r = await fetch(`/api/subscriber/space/${encodeURIComponent(c)}`);
      return { statut: r.status, corps: await r.json().catch(() => ({})) };
    }, code);

    const caisse = (offerId, email, montant) => page.evaluate(async (a) => {
      const r = await fetch('/api/create-checkout-session', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          productName: 'Recharge', amount: a.montant, customerEmail: a.email,
          originUrl: 'http://127.0.0.1', offerId: a.offerId, quantity: 1,
        }),
      });
      return { statut: r.status, corps: await r.json().catch(() => ({})) };
    }, { offerId, email, montant });

    // ══ A — MEMBRE ACTIF, PACK EPUISE : LA RECHARGE EST OUVERTE ════════════
    const a = await espace(CLIENTS.vide.code);
    verifier('A1. l espace abonne repond', a.statut === 200, `statut=${a.statut}`);
    verifier('A2. le serveur declare la recharge ELIGIBLE',
             (a.corps.recharge || {}).eligible === true,
             `recharge=${JSON.stringify(a.corps.recharge)}`);
    verifier('A3. il donne l offre, son PRIX et ses SEANCES — l ecran n invente rien',
             (a.corps.recharge || {}).offer_id === OFFRE_150
             && (a.corps.recharge || {}).prix === 150
             && (a.corps.recharge || {}).seances === 10,
             `recharge=${JSON.stringify(a.corps.recharge)}`);
    verifier('A4. le compteur est bien a 0',
             (a.corps.subscription || {}).remaining_sessions === 0,
             `reste=${(a.corps.subscription || {}).remaining_sessions}`);

    const aCaisse = await caisse(OFFRE_150, CLIENTS.vide.email, 150);
    verifier('A5. la caisse ACCEPTE la recharge de ce membre',
             aCaisse.statut === 200 || !!aCaisse.corps.url
             || /stripe/i.test(JSON.stringify(aCaisse.corps)),
             `statut=${aCaisse.statut} ${JSON.stringify(aCaisse.corps).slice(0, 200)}`);

    // ══ B — IL RESTE DES SEANCES : PAS DE RECHARGE ═════════════════════════
    const b = await espace(CLIENTS.garni.code);
    verifier('B1. 3 seances restantes -> recharge NON eligible',
             (b.corps.recharge || {}).eligible === false,
             `recharge=${JSON.stringify(b.corps.recharge)}`);
    verifier('B2. ... avec le motif `seances_restantes`, pas un refus muet',
             (b.corps.recharge || {}).motif === 'seances_restantes',
             `motif=${(b.corps.recharge || {}).motif}`);
    verifier('B3. ... et une phrase pour le client',
             ((b.corps.recharge || {}).message || '').length > 20,
             `message=${(b.corps.recharge || {}).message}`);
    const bCaisse = await caisse(OFFRE_150, CLIENTS.garni.email, 150);
    verifier('B4. la caisse REFUSE (403), meme si le bouton etait force',
             bCaisse.statut === 403, `statut=${bCaisse.statut}`);

    // ══ C — NON-MEMBRE : REFUSE COTE SERVEUR ══════════════════════════════
    const c = await espace(CLIENTS.inconnu.code);
    verifier('C1. sans adhesion -> recharge NON eligible',
             (c.corps.recharge || {}).eligible === false
             && (c.corps.recharge || {}).motif === 'adhesion_absente',
             `recharge=${JSON.stringify(c.corps.recharge)}`);
    verifier('C2. ... et le message ORIENTE vers l offre d entree',
             /entrée|entree/i.test((c.corps.recharge || {}).message || ''),
             (c.corps.recharge || {}).message);
    const cCaisse = await caisse(OFFRE_150, CLIENTS.inconnu.email, 150);
    verifier('C3. la caisse REFUSE un non-membre (403)',
             cCaisse.statut === 403, `statut=${cCaisse.statut}`);
    const cAnon = await caisse(OFFRE_150, '', 150);
    verifier('C4. ... et refuse aussi un acheteur NON IDENTIFIE',
             cAnon.statut === 403, `statut=${cAnon.statut}`);

    // ══ D — ADHESION EXPIREE : REFUSE ══════════════════════════════════════
    const d = await espace(CLIENTS.echu.code);
    verifier('D1. adhesion echue -> recharge NON eligible',
             (d.corps.recharge || {}).eligible === false,
             `recharge=${JSON.stringify(d.corps.recharge)}`);
    verifier('D2. ... avec un motif DISTINCT de l absence d adhesion : '
             + 'un fidele de 13 mois n est pas un inconnu',
             (d.corps.recharge || {}).motif === 'adhesion_expiree',
             `motif=${(d.corps.recharge || {}).motif}`);
    const dCaisse = await caisse(OFFRE_150, CLIENTS.echu.email, 150);
    verifier('D3. la caisse REFUSE une adhesion echue (403)',
             dCaisse.statut === 403, `statut=${dCaisse.statut}`);

    // ══ LA PORTE GRATUITE NE CONTOURNE PAS LA REGLE ════════════════════════
    const gratuit = await page.evaluate(async (a) => {
      const r = await fetch('/api/checkout/free', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          coach_email: '', items: [{ id: a.offerId, name: 'Recharge', price: 0, quantity: 1 }],
          customer_name: 'Pirate', customer_email: a.email, customer_phone: '',
          terms_accepted: true,
        }),
      });
      return { statut: r.status, corps: await r.json().catch(() => ({})) };
    }, { offerId: OFFRE_150, email: CLIENTS.inconnu.email });
    // MESURE : cette porte refuse DEJA, mais par une garde ANTERIEURE — elle
    // n'accepte que les offres a 0 CHF, et la recharge coute 150. Le refus est
    // donc acquis ; ce qui compte est qu'il existe.
    verifier('C5. la porte GRATUITE refuse la recharge (ici par sa propre garde '
             + 'de gratuite : une offre a 150 CHF n y entre pas)',
             gratuit.statut === 403 || gratuit.statut === 400,
             `statut=${gratuit.statut} ${JSON.stringify(gratuit.corps).slice(0, 150)}`);

    // ET SI LE COACH COCHAIT LES DEUX ? Une offre protegee ET gratuite est une
    // erreur de configuration possible — c'est LA situation ou ma garde doit
    // parler sur cette porte. Sans ce cas, la garde y serait posee sans preuve.
    py(`
import pymongo
c = pymongo.MongoClient("mongodb://127.0.0.1:${PORT_MONGO}")
c["${DBNAME}"].offers.insert_one({"id":"offre-piege","name":"Recharge offerte",
  "price":0.0,"pack_sessions":10,"visible":False,"coach_id":None,
  "creates_membership":False,"first_purchase_eligible":False,
  "requires_active_membership":True,"progressive_pricing":False})
print("PIEGE")`);
    const piege = await page.evaluate(async (a) => {
      const r = await fetch('/api/checkout/free', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          coach_email: '', items: [{ id: 'offre-piege', name: 'Recharge offerte', price: 0, quantity: 1 }],
          customer_name: 'Pirate', customer_email: a.email, customer_phone: '',
          terms_accepted: true,
        }),
      });
      return { statut: r.status, corps: await r.json().catch(() => ({})) };
    }, { email: CLIENTS.inconnu.email });
    verifier('C6. une offre protegee ET gratuite : la garde LOT R parle bien '
             + 'sur la porte gratuite (403), elle n y est pas decorative',
             piege.statut === 403,
             `statut=${piege.statut} ${JSON.stringify(piege.corps).slice(0, 180)}`);

    // ══ G — L OFFRE D ENTREE RESTE OUVERTE A TOUS ══════════════════════════
    const g = await caisse(OFFRE_250, CLIENTS.inconnu.email, 250);
    verifier('G1. l offre d ENTREE reste achetable par un non-membre — sinon '
             + 'plus personne ne pourrait devenir membre',
             g.statut !== 403, `statut=${g.statut}`);

    // ══ F + A6 — LE WEBHOOK : 10 SEANCES, AUCUN NOUVEAU MEMBERSHIP ═════════
    // On simule la confirmation de paiement exactement comme Stripe l'envoie :
    // c'est ce chemin, et lui seul, qui accorde les seances.
    const webhook = (sessionId, offerId, email, montant) => page.evaluate(async (a) => {
      const r = await fetch('/api/webhook/stripe', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: 'checkout.session.completed',
          data: { object: {
            id: a.sessionId, object: 'checkout.session', payment_status: 'paid',
            amount_total: a.montant * 100, currency: 'chf',
            payment_intent: 'pi_' + a.sessionId,
            customer_details: { email: a.email, name: 'Test' },
            metadata: {
              product_name: 'PULSE x10', customer_email: a.email,
              offer_id: a.offerId, pack_sessions: '10', quantity: '1',
              source: 'afroboost_checkout',
            },
          } },
        }),
      });
      return { statut: r.status, corps: await r.text().catch(() => '') };
    }, { sessionId, offerId, email, montant });

    const compter = (email) => py(`
import pymongo, json
c = pymongo.MongoClient("mongodb://127.0.0.1:${PORT_MONGO}")
d = c["${DBNAME}"]
subs = list(d.subscriptions.find({"email":"${email}"}, {"_id":0}))
adh  = list(d.memberships.find({"email":"${email}"}, {"_id":0}))
print(json.dumps({
  "forfaits": len(subs), "adhesions": len(adh),
  "neufs": [{"seances": s.get("total_sessions"), "reste": s.get("remaining_sessions"),
             "origine": s.get("origine_paiement"), "montant": s.get("montant_encaisse"),
             "achetees": s.get("seances_a_l_achat"), "ref": s.get("reference_paiement"),
             "statut": s.get("status")}
            for s in subs if s.get("id","").startswith("sub-") is False],
}, default=str))`);

    const avant = JSON.parse(compter(CLIENTS.vide.email).trim().split('\n').pop());
    await webhook('cs_lotr_recharge_1', OFFRE_150, CLIENTS.vide.email, 150);
    await dormir(700);
    const apres = JSON.parse(compter(CLIENTS.vide.email).trim().split('\n').pop());
    const neuf = (apres.neufs || [])[0] || {};

    verifier('A6. paiement confirme -> 10 seances, pas 1, pas « le reste d avant »',
             neuf.seances === 10 && neuf.reste === 10,
             `forfait=${JSON.stringify(neuf)}`);
    verifier('F1. la recharge ne cree AUCUN nouveau membership',
             apres.adhesions === avant.adhesions && apres.adhesions === 1,
             `avant=${avant.adhesions} apres=${apres.adhesions}`);
    verifier('F2. la trace financiere dit « renouvellement » et non « premier achat »',
             /renouvellement/i.test(String(neuf.origine || '')),
             `origine=${neuf.origine}`);
    verifier('F3. ... avec le montant, les seances achetees et la reference',
             neuf.montant === 150 && neuf.achetees === 10 && !!neuf.ref,
             `trace=${JSON.stringify(neuf)}`);

    // ══ E — DOUBLE CONFIRMATION : UNE SEULE RECHARGE ═══════════════════════
    const forfaitsApres1 = apres.forfaits;
    await webhook('cs_lotr_recharge_1', OFFRE_150, CLIENTS.vide.email, 150);
    await dormir(700);
    const rejoue = JSON.parse(compter(CLIENTS.vide.email).trim().split('\n').pop());
    verifier('E1. le MEME paiement rejoue n accorde pas un second pack',
             rejoue.forfaits === forfaitsApres1,
             `avant=${forfaitsApres1} apres=${rejoue.forfaits}`);
    verifier('E2. ... et ne cree pas d adhesion supplementaire',
             rejoue.adhesions === 1, `adhesions=${rejoue.adhesions}`);

    // ══ G — L ENTREE A 250 : 10 SEANCES *ET* UNE ADHESION ══════════════════
    const gEmail = 'nouveau.client@ex.test';
    await webhook('cs_lotr_entree_1', OFFRE_250, gEmail, 250);
    await dormir(700);
    const gApres = JSON.parse(compter(gEmail).trim().split('\n').pop());
    const gNeuf = (gApres.neufs || [])[0] || {};
    verifier('G2. l entree a 250 donne 10 seances',
             gNeuf.seances === 10 && gNeuf.reste === 10, JSON.stringify(gNeuf));
    verifier('G3. ... ET ouvre l adhesion (c est ce qui la distingue de la recharge)',
             gApres.adhesions === 1, `adhesions=${gApres.adhesions}`);
    verifier('G4. ... et n est PAS marquee « renouvellement »',
             !/renouvellement/i.test(String(gNeuf.origine || '')),
             `origine=${gNeuf.origine}`);

    // ── APRES LA RECHARGE, LE CLIENT VOIT SES SEANCES ──────────────────────
    const finale = await espace(CLIENTS.vide.code);
    verifier('A7. la recharge n est plus proposee : le pack est de nouveau garni',
             (finale.corps.recharge || {}).eligible === false
             && (finale.corps.recharge || {}).motif === 'seances_restantes',
             `recharge=${JSON.stringify(finale.corps.recharge)}`);

    // ══ LE BOUTON « RENOUVELER » : LE DEFAUT BLOQUANT, MESURE ══════════════
    //
    // AVANT, cette route lisait `discount_codes.stripe_amount` — le montant du
    // PRECEDENT achat — et n'envoyait ni `offer_id` ni `pack_sessions`. Le
    // webhook retombait alors sur une regex du nom du produit et n'accordait
    // qu'UNE seance.
    //
    // LE SYMPTOME QUI SE MESURE SANS STRIPE : un code SANS `stripe_amount`
    // dont l'offre a un prix. Avant, la route repondait 400 « Aucun montant
    // configure ». Maintenant elle resout le prix dans le CATALOGUE, donc elle
    // depasse cette borne — et n'echoue plus que sur Stripe, faute de cle dans
    // ce banc. C'est exactement la difference qu'il fallait prouver.
    py(`
import pymongo
c = pymongo.MongoClient("mongodb://127.0.0.1:${PORT_MONGO}")
d = c["${DBNAME}"]
d.subscriptions.insert_one({"id":"sub-BTN","code":"LOTR-BTN",
  "email":"bouton@ex.test","name":"Bouton","coach_id":None,"status":"active",
  "offer_name":"PULSE x10 cours","total_sessions":10,"used_sessions":10,
  "remaining_sessions":0,"expires_at":"${AN}-12-31T23:59:59+00:00"})
d.discount_codes.insert_one({"id":"dc-BTN","code":"LOTR-BTN","type":"100%",
  "value":100,"assignedEmail":"bouton@ex.test","maxUses":10,"used":10,
  "active":True,"courses":[],"expiresAt":"${AN}-12-31"})
print("BTN")`);
    const bouton = await page.evaluate(async () => {
      const r = await fetch('/api/subscriber/space/LOTR-BTN/stripe-checkout', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ originUrl: 'http://127.0.0.1', email: 'bouton@ex.test' }),
      });
      return { statut: r.status, corps: await r.text().catch(() => '') };
    });
    verifier('BTN1. le bouton ne repond plus « Aucun montant configuré » : le '
             + 'prix vient desormais du CATALOGUE, pas du precedent achat',
             !/Aucun montant configur/i.test(bouton.corps),
             `statut=${bouton.statut} ${bouton.corps.slice(0, 200)}`);
    verifier('BTN2. il va bien jusqu a la caisse (l echec restant vient de '
             + 'Stripe, absent de ce banc — pas de la resolution du prix)',
             bouton.statut !== 400 || /stripe|clé|key/i.test(bouton.corps),
             `statut=${bouton.statut} ${bouton.corps.slice(0, 200)}`);
    const srcServeur = fs.readFileSync(path.join(DEPOT, 'api/server.py'), 'utf8');
    const zoneBouton = srcServeur.slice(
      srcServeur.indexOf('async def subscriber_stripe_checkout'),
      srcServeur.indexOf('async def subscriber_stripe_checkout') + 7000);
    verifier('BTN3. la metadata porte `offer_id` ET `pack_sessions` — sans eux '
             + 'le webhook n accorderait qu UNE seance',
             /"offer_id":\s*str\(\(_lotr_offre/.test(zoneBouton)
             && /"pack_sessions":\s*_lotr_pack/.test(zoneBouton));
    verifier('BTN4. la garde LOT R y est posee aussi',
             zoneBouton.includes('lotr_garde_achat'));

    // ── L ECRAN, EN MOBILE ─────────────────────────────────────────────────
    // Le panneau vit dans `SubscriberSpace`, monte par le routeur de l'app :
    // on verifie que le MARQUAGE attendu par l'ecran correspond a ce que la
    // route rend, et on le dit — le rendu complet est couvert par Jest.
    const src = fs.readFileSync(
      path.join(DEPOT, 'frontend/src/components/SubscriberSpace.js'), 'utf8');
    verifier('UX1. l ecran lit `recharge.eligible` — le champ que la route rend',
             src.includes('data?.recharge?.eligible'));
    verifier('UX2. le CTA affiche les seances et le prix VENUS DU SERVEUR',
             src.includes('data.recharge.seances') && src.includes('data.recharge.prix'));
    verifier('UX3. le motif de refus est affiche quand le CTA est absent',
             src.includes('recharge-motif') && src.includes('data.recharge.message'));
    verifier('UX4. aucun montant en dur dans le bloc de recharge',
             !/recharge[\s\S]{0,1200}(150|250)\s*(CHF|<)/.test(src));
    verifier('UX5. l icone est un SVG inline, jamais un emoji (regle du depot)',
             /recharge-cta[\s\S]{0,900}<svg/.test(src));
    const largeur = await page.evaluate(() => window.innerWidth);
    verifier('UX6. le banc a tourne en viewport MOBILE (390 px)', largeur === 390,
             `largeur=${largeur}`);

    const ok = resultats.filter((r) => r.ok).length;
    console.log('\n' + '='.repeat(76));
    console.log('LOT R — RECHARGE PULSE : NAVIGATEUR REEL');
    console.log('='.repeat(76));
    console.log('Backend reel, mongod jetable, Chromium mobile. Production : 0.');
    console.log(`${ok} / ${resultats.length} verifications`);
    return ok === resultats.length ? 0 : 1;
  } finally {
    if (navigateur) await navigateur.close().catch(() => {});
    api.kill('SIGTERM'); mongo.kill('SIGTERM');
    await dormir(400);
    fs.rmSync(DBDIR, { recursive: true, force: true });
  }
}

principal().then((c) => process.exit(c)).catch((e) => {
  console.error(e); process.exit(2);
});
