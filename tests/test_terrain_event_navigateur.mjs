/**
 * CORRECTIFS TERRAIN EVENT — LE PARCOURS REEL, DANS UN VRAI NAVIGATEUR.
 *
 * CE QUE CE BANC PROUVE, ET QUE LE BANC PYTHON NE PROUVE PAS. Le banc Python
 * execute les fonctions sur une base en memoire qui IGNORE LES PROJECTIONS —
 * c'est exactement ce qui a rendu deux correctifs inertes en production sans
 * qu'aucun test ne bronche. Ici : un vrai mongod, un vrai FastAPI, un vrai
 * Chromium, un vrai jeton. Une projection amputee se voit tout de suite.
 *
 * LES TROIS PARCOURS DU TERRAIN :
 *   A. scanner un essai gratuit -> l'alerte part, avec le tarif SI il existe.
 *   B. scanner puis changer l'etat d'un casque -> le serveur confirme, et
 *      l'etat relu est le meme partout.
 *   C. faire reconnaitre un bilan par un partenaire -> refus tant que le total
 *      est provisoire, acceptation ensuite, peremption si le total bouge.
 *
 * AUCUNE DONNEE DE PRODUCTION : mongod jetable sur un port dedie, base
 * detruite a la fin. Le navigateur ne peut joindre que 127.0.0.1.
 *
 *   node tests/test_terrain_event_navigateur.mjs
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
const PORT_MONGO = 28023;
const PORT_API = 8101;
const BASE = `http://127.0.0.1:${PORT_API}`;
const DBDIR = path.join(os.tmpdir(), 'afroboost-terrain-mongo');
const DBNAME = 'terrain_event';

const COACH = 'coach.terrain@partenaire.ch';
const VOISIN = 'coach.voisin@partenaire.ch';
const MDP = 'MotDePasseTest!2026';
const COURS = 'cours-terrain-1';
// Le bilan a signer vit sur SON cours : sinon les presences validees
// par les scans de la partie B (datees d'aujourd'hui) tomberaient dans
// ce meme bilan et le rendraient provisoire — un artefact du decor.
const COURS_BILAN = 'cours-terrain-bilan';
const OCC = '2026-08-21T18:30:00';
const OCC2 = '2026-08-28T18:30:00';

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

// Le jour du scan doit etre AUJOURD'HUI : la garde A0 refuse de valider une
// autre occurrence. On seme donc les reservations scannees a la date du jour.
const AUJ = new Date().toISOString().slice(0, 10);

function semer() {
  const s = `
import pymongo
c = pymongo.MongoClient("mongodb://127.0.0.1:${PORT_MONGO}")
d = c["${DBNAME}"]
for n in ("reservations","subscriptions","discount_codes","coaches","courses","session_shares"):
    d[n].delete_many({})
d.coaches.insert_many([{"email":"${COACH}"},{"email":"${VOISIN}"}])
d.courses.insert_many([
  {"id":"${COURS}","name":"Afroboost","time":"18:30","coach_id":"${COACH}"},
  {"id":"${COURS_BILAN}","name":"Afroboost Silent","time":"18:30","coach_id":"${COACH}"},
])

# ── LES DROITS ────────────────────────────────────────────────────────────
# Deux essais GRATUITS au sens du moteur de paiement, et un forfait payant.
d.discount_codes.insert_many([
  {"code":"ESSAI-AVEC","payment_method":"free","total_paid":0},
  {"code":"ESSAI-SANS","payment_method":"free","total_paid":0},
])
d.subscriptions.insert_one({"id":"sub-pulse","code":"PULSE-01","email":"marc@ex.test",
  "coach_id":"${COACH}","status":"active","renewal_sessions":10,"remaining_sessions":8,
  "used_sessions":2,"offer_name":"PULSE x10"})

d.reservations.insert_many([
  # ESSAI avec un tarif FIGE a l'achat -> le coach peut annoncer 25 CHF
  {"id":"re-avec","reservationCode":"SCAN-AVEC","userName":"Khady Sow",
   "userEmail":"khady@ex.test","validated":False,"courseId":"${COURS}",
   "datetime":"${AUJ}T18:30:00","coach_id":"${COACH}","courseName":"Afroboost",
   "promoCode":"ESSAI-AVEC","tarif_public":25.0,"tarif_devise":"CHF",
   "quantity":2,"guests":["Ami Ndiaye"],"guest_headphones":[None],
   "headphone_status":None},
  # ESSAI SANS tarif fige -> aucun montant ne doit apparaitre
  {"id":"re-sans","reservationCode":"SCAN-SANS","userName":"Fatou Ba",
   "userEmail":"fatou@ex.test","validated":False,"courseId":"${COURS}",
   "datetime":"${AUJ}T18:30:00","coach_id":"${COACH}","courseName":"Afroboost",
   "promoCode":"ESSAI-SANS"},
  # PAYANT -> aucune alerte essai
  {"id":"re-payant","reservationCode":"SCAN-PAYE","userName":"Marc Diallo",
   "userEmail":"marc@ex.test","validated":False,"courseId":"${COURS}",
   "datetime":"${AUJ}T18:30:00","coach_id":"${COACH}","courseName":"Afroboost",
   "promoCode":"PULSE-01","tarif_public":30.0},

  # ── LE BILAN A SIGNER : deux presences chiffrees, une A VERIFIER ────────
  {"id":"b1","userName":"Alice","userEmail":"a@ex.test","validated":True,
   "courseId":"${COURS_BILAN}","datetime":"${OCC}","coach_id":"${COACH}",
   "courseName":"Afroboost","tarif_applique":200.0,"tarif_raison":"public"},
  {"id":"b2","userName":"Bruno","userEmail":"b@ex.test","validated":True,
   "courseId":"${COURS_BILAN}","datetime":"${OCC}","coach_id":"${COACH}",
   "courseName":"Afroboost","tarif_applique":100.0,"tarif_raison":"public"},
  {"id":"b3","userName":"Chloe","userEmail":"c@ex.test","validated":True,
   "courseId":"${COURS_BILAN}","datetime":"${OCC}","coach_id":"${COACH}",
   "courseName":"Afroboost","promoCode":"HISTORIQUE-SANS-PREUVE"},
  # MEME cours, AUTRE date : un bilan, un partage et une signature a part.
  {"id":"b4","userName":"Dora","userEmail":"d@ex.test","validated":True,
   "courseId":"${COURS_BILAN}","datetime":"${OCC2}","coach_id":"${COACH}",
   "courseName":"Afroboost","tarif_applique":50.0,"tarif_raison":"public"},
])
print("SEME")`;
  if (!py(s).includes('SEME')) throw new Error('semis impossible');
}

// Un PNG 8x8 blanc avec un trait — une vraie image, pas une chaine inventee.
const SIGNATURE_PNG = 'data:image/png;base64,'
  + 'iVBORw0KGgoAAAANSUhEUgAAAAgAAAAIAQMAAAD+wSzIAAAABlBMVEX///+/v7'
  + '+jQ3Y5AAAADklEQVQI12P4AIX8EAgALgAD/aNpbtEAAAAASUVORK5CYII=';

async function principal() {
  fs.rmSync(DBDIR, { recursive: true, force: true });
  fs.mkdirSync(DBDIR, { recursive: true });
  const mongo = spawn(MONGOD, ['--dbpath', DBDIR, '--port', String(PORT_MONGO),
    '--bind_ip', '127.0.0.1'], { stdio: 'ignore' });
  const api = spawn(PY, ['-m', 'uvicorn', 'api.server:app', '--host', '127.0.0.1',
    '--port', String(PORT_API), '--log-level', 'warning'], {
    cwd: DEPOT, stdio: ['ignore', 'ignore', 'pipe'],
    env: { ...process.env, MONGO_URL: `mongodb://127.0.0.1:${PORT_MONGO}`,
           DB_NAME: DBNAME, JWT_SECRET: 'test-secret-terrain' },
  });
  let journal = '';
  api.stderr.on('data', (b) => { journal += b.toString(); });

  let navigateur;
  try {
    await dormir(1500);
    if (!await attendre(`${BASE}/healthz`)) {
      console.error('Backend non demarre.\n' + journal.slice(-2000));
      return 2;
    }
    semer();

    navigateur = await chromium.launch({ headless: true });
    const ctx = await navigateur.newContext({ baseURL: BASE });
    await ctx.route('**/*', (route) => {
      const u = new URL(route.request().url());
      if (u.hostname !== '127.0.0.1') return route.abort();
      return route.continue();
    });

    const page = await ctx.newPage();
    await page.goto('/healthz');

    // Un VRAI compte, un VRAI jeton — la preuve exigee par V310c.
    await page.evaluate(async ({ e, m }) => {
      await fetch('/api/auth/register', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: e, password: m, name: 'Coach' }),
      }).catch(() => {});
    }, { e: COACH, m: MDP });
    py(`
import pymongo
c = pymongo.MongoClient("mongodb://127.0.0.1:${PORT_MONGO}")
c["${DBNAME}"].users_auth.update_one({"email": "${COACH}"},
                                     {"$set": {"pending_validation": False}})
print("VALIDE")`);
    const jeton = await page.evaluate(async ({ e, m }) => {
      const r = await fetch('/api/auth/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: e, password: m }),
      });
      const j = await r.json().catch(() => ({}));
      return j.token || j.access_token || (j.data && j.data.token) || '';
    }, { e: COACH, m: MDP });
    verifier('0. un vrai jeton coach est emis par /auth/login', !!jeton,
             'aucun jeton — le reste du banc ne prouverait rien');

    const appeler = (chemin, options) => page.evaluate(async ({ c, o, t }) => {
      const init = { headers: { Authorization: 'Bearer ' + t } };
      if (o) {
        init.method = o.methode || 'POST';
        init.headers['Content-Type'] = 'application/json';
        init.body = JSON.stringify(o.corps || {});
      }
      const r = await fetch('/api' + c, init);
      return { statut: r.status, corps: await r.json().catch(() => ({})) };
    }, { c: chemin, o: options || null, t: jeton });

    // ══ A — L'ESSAI GRATUIT AU SCAN ═════════════════════════════════════════
    const sAvec = await appeler('/qr/scan-validate', { corps: { code: 'SCAN-AVEC' } });
    verifier('A1. le scan d un essai aboutit (la presence est validee)',
             sAvec.statut === 200 && sAvec.corps.success === true,
             `statut=${sAvec.statut} ${JSON.stringify(sAvec.corps).slice(0, 160)}`);
    verifier('A2. l essai est signale au coach',
             (sAvec.corps.acces || {}).essai === true,
             `acces=${JSON.stringify(sAvec.corps.acces)}`);
    verifier('A3. le tarif FIGE a l achat traverse la PROJECTION et arrive au navigateur',
             (sAvec.corps.acces || {}).tarif_public === 25
             && (sAvec.corps.acces || {}).tarif_devise === 'CHF',
             `acces=${JSON.stringify(sAvec.corps.acces)}`);

    const sSans = await appeler('/qr/scan-validate', { corps: { code: 'SCAN-SANS' } });
    verifier('A4. sans tarif fige : AUCUN montant invente, la cle est absente',
             (sSans.corps.acces || {}).essai === true
             && !('tarif_public' in (sSans.corps.acces || {})),
             `acces=${JSON.stringify(sSans.corps.acces)}`);

    const sPaye = await appeler('/qr/scan-validate', { corps: { code: 'SCAN-PAYE' } });
    verifier('A5. un droit PAYANT n est jamais annonce comme un essai',
             (sPaye.corps.acces || {}).essai === false
             && !('tarif_public' in (sPaye.corps.acces || {})),
             `acces=${JSON.stringify(sPaye.corps.acces)}`);

    // ══ B — LE CASQUE ══════════════════════════════════════════════════════
    const bloc = sAvec.corps.reservation || {};
    verifier('B1. le scan expose l identifiant et les accompagnants, avec leurs prenoms',
             bloc.id === 're-avec'
             && Array.isArray(bloc.guests) && bloc.guests[0] === 'Ami Ndiaye'
             && Array.isArray(bloc.guest_headphones),
             `reservation=${JSON.stringify(bloc)}`);
    verifier('B2. la quantite (nombre de casques a prevoir) arrive aussi',
             bloc.quantity === 2, `quantity=${bloc.quantity}`);

    // ROUGE : le casque part avec le participant.
    const hp1 = await appeler('/reservations/re-avec/headphone',
                              { methode: 'PUT', corps: { status: 'taken' } });
    verifier('B3. le serveur accepte « casque remis » (ROUGE)', hp1.statut === 200,
             `statut=${hp1.statut}`);

    // On RESCANNE : l'etat doit revenir tel quel. C'est ce qui garantit que
    // les deux ecrans lisent le meme etat, et non deux copies divergentes.
    const rescan = await appeler('/qr/scan-validate', { corps: { code: 'SCAN-AVEC' } });
    verifier('B4. l etat ecrit est RELU par le scan — une seule source de verite',
             (rescan.corps.reservation || {}).headphone_status === 'taken',
             `relu=${JSON.stringify((rescan.corps.reservation || {}).headphone_status)}`);

    // VERT : le casque revient au coach.
    await appeler('/reservations/re-avec/headphone',
                  { methode: 'PUT', corps: { status: 'returned' } });
    const rescan2 = await appeler('/qr/scan-validate', { corps: { code: 'SCAN-AVEC' } });
    verifier('B5. « casque rendu » (VERT) est relu de la meme facon',
             (rescan2.corps.reservation || {}).headphone_status === 'returned',
             `relu=${JSON.stringify((rescan2.corps.reservation || {}).headphone_status)}`);

    const hpInv = await appeler('/reservations/re-avec/headphone',
                                { methode: 'PUT', corps: { status: 'taken', guest_index: 0 } });
    const rescan3 = await appeler('/qr/scan-validate', { corps: { code: 'SCAN-AVEC' } });
    verifier('B6. le casque d un ACCOMPAGNANT se change independamment',
             hpInv.statut === 200
             && ((rescan3.corps.reservation || {}).guest_headphones || [])[0] === 'taken'
             && (rescan3.corps.reservation || {}).headphone_status === 'returned',
             `resa=${JSON.stringify(rescan3.corps.reservation)}`);

    // ══ C — LA SIGNATURE ═══════════════════════════════════════════════════
    const b0 = await appeler(`/reservations/bilan-seance?courseId=${encodeURIComponent(COURS_BILAN)}&occurrence=${encodeURIComponent(OCC)}`);
    verifier('C1. le bilan est PROVISOIRE : une presence reste a verifier',
             b0.corps.provisoire === true && b0.corps.total_connu === 300,
             `provisoire=${b0.corps.provisoire} total=${b0.corps.total_connu}`);

    await appeler('/reservations/bilan-seance/partage', {
      corps: { courseId: COURS_BILAN, occurrence: OCC, partner_name: 'LAFF', partner_percentage: 30 } });

    const sigTot = await appeler('/reservations/bilan-seance/signature', {
      corps: { courseId: COURS_BILAN, occurrence: OCC, partner_signature: SIGNATURE_PNG } });
    verifier('C2. on ne fait pas signer un total PROVISOIRE : refus franc',
             sigTot.statut === 409,
             `statut=${sigTot.statut} ${JSON.stringify(sigTot.corps).slice(0, 120)}`);

    // La derniere presence devient chiffree -> le bilan cesse de bouger.
    py(`
import pymongo
c = pymongo.MongoClient("mongodb://127.0.0.1:${PORT_MONGO}")
c["${DBNAME}"].reservations.update_one({"id":"b3"},
    {"$set": {"tarif_applique": 0.0, "tarif_raison": "essai"}})
print("FIGE")`);

    const b1 = await appeler(`/reservations/bilan-seance?courseId=${encodeURIComponent(COURS_BILAN)}&occurrence=${encodeURIComponent(OCC)}`);
    verifier('C3. bilan complet : plus rien a verifier, total inchange a 300',
             b1.corps.provisoire === false && b1.corps.total_connu === 300,
             `provisoire=${b1.corps.provisoire} total=${b1.corps.total_connu}`);

    const mauvaise = await appeler('/reservations/bilan-seance/signature', {
      corps: { courseId: COURS_BILAN, occurrence: OCC, partner_signature: 'data:text/html,<script>' } });
    verifier('C4. une « signature » qui n est pas une image est refusee',
             mauvaise.statut === 400, `statut=${mauvaise.statut}`);

    const sigOk = await appeler('/reservations/bilan-seance/signature', {
      corps: { courseId: COURS_BILAN, occurrence: OCC, partner_signature: SIGNATURE_PNG } });
    verifier('C5. le partenaire signe, et le serveur accepte', sigOk.statut === 200,
             `statut=${sigOk.statut} ${JSON.stringify(sigOk.corps).slice(0, 160)}`);

    const b2 = await appeler(`/reservations/bilan-seance?courseId=${encodeURIComponent(COURS_BILAN)}&occurrence=${encodeURIComponent(OCC)}`);
    const sg = (b2.corps.partage || {}).signature || {};
    verifier('C6. le bilan restitue la signature, avec le montant RECONNU (90)',
             sg.partner_amount === 90 && !!sg.signed_at,
             `signature=${JSON.stringify(sg)}`);
    verifier('C7. cote Afroboost : le coach AUTHENTIFIE, horodate',
             sg.afroboost_valide_par === COACH && !!sg.afroboost_valide_le,
             `valide_par=${sg.afroboost_valide_par}`);
    verifier('C8. la signature est reputee couvrir les montants du jour',
             sg.perimee === false, `perimee=${sg.perimee}`);
    verifier('C9. le TRAIT lui-meme ne circule pas a chaque lecture du bilan',
             !('partner_signature' in sg),
             `cles=${Object.keys(sg).join(',')}`);

    // ── LE TOTAL BOUGE APRES LA SIGNATURE ───────────────────────────────────
    await appeler('/reservations/bilan-seance/partage', {
      corps: { courseId: COURS_BILAN, occurrence: OCC, partner_name: 'LAFF', partner_percentage: 50 } });
    const b3 = await appeler(`/reservations/bilan-seance?courseId=${encodeURIComponent(COURS_BILAN)}&occurrence=${encodeURIComponent(OCC)}`);
    const sg3 = (b3.corps.partage || {}).signature || {};
    verifier('C10. le montant change -> la signature est dite PERIMEE',
             sg3.perimee === true, `perimee=${sg3.perimee}`);
    verifier('C11. ... et le montant SIGNE reste 90, jamais reecrit en douce',
             sg3.partner_amount === 90
             && (b3.corps.partage || {}).partner_amount === 150,
             `signe=${sg3.partner_amount} courant=${(b3.corps.partage || {}).partner_amount}`);

    // ── SANS JETON ──────────────────────────────────────────────────────────
    const anon = await page.evaluate(async ({ c, o, img }) => {
      const r = await fetch('/api/reservations/bilan-seance/signature', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ courseId: c, occurrence: o, partner_signature: img }),
      });
      return r.status;
    }, { c: COURS_BILAN, o: OCC, img: SIGNATURE_PNG });
    verifier('C12. sans jeton : REFUS (403), jamais une signature anonyme',
             anon === 403, `statut=${anon}`);

    // ── SIGNER N EST PAS PAYER ──────────────────────────────────────────────
    const enBase = py(`
import pymongo, json
c = pymongo.MongoClient("mongodb://127.0.0.1:${PORT_MONGO}")
d = c["${DBNAME}"]["session_shares"].find_one({"courseId":"${COURS_BILAN}"}, {"_id":0})
print(json.dumps(sorted((d or {}).keys())))`);
    verifier('C13. le document ne porte AUCUNE trace de paiement',
             !/paid|stripe|payout|transfer/i.test(enBase),
             `cles=${enBase.trim().slice(0, 200)}`);
    verifier('C14. une seule ligne de partage : signer ne duplique pas',
             py(`
import pymongo
c = pymongo.MongoClient("mongodb://127.0.0.1:${PORT_MONGO}")
print(c["${DBNAME}"]["session_shares"].count_documents({}))`).trim() === '1',
             'plusieurs documents pour la meme seance');

    // ── DEUX OCCURRENCES DU MEME COURS : DEUX SIGNATURES ────────────────────
    // Le meme cours le 21 et le 28 sont deux seances. Si la signature se
    // rattachait au COURS, celle du 21 vaudrait pour le 28 — le partenaire
    // aurait reconnu un montant qu'il n'a jamais vu.
    await appeler('/reservations/bilan-seance/partage', {
      corps: { courseId: COURS_BILAN, occurrence: OCC2, partner_name: 'LAFF', partner_percentage: 40 } });
    const b2b = await appeler(`/reservations/bilan-seance?courseId=${encodeURIComponent(COURS_BILAN)}&occurrence=${encodeURIComponent(OCC2)}`);
    verifier('C17. la seance du 28 a SON total (50), independant du 21',
             b2b.corps.total_connu === 50, `total=${b2b.corps.total_connu}`);
    verifier('C18. ... et AUCUNE signature : celle du 21 ne deborde pas',
             !((b2b.corps.partage || {}).signature),
             `signature=${JSON.stringify((b2b.corps.partage || {}).signature)}`);

    // ── UN AUTRE COACH NE SIGNE PAS LE BILAN DU VOISIN ──────────────────────
    await page.evaluate(async ({ e, m }) => {
      await fetch('/api/auth/register', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: e, password: m, name: 'Voisin' }),
      }).catch(() => {});
    }, { e: VOISIN, m: MDP });
    py(`
import pymongo
c = pymongo.MongoClient("mongodb://127.0.0.1:${PORT_MONGO}")
c["${DBNAME}"].users_auth.update_one({"email": "${VOISIN}"},
                                     {"$set": {"pending_validation": False}})
print("VALIDE")`);
    const jetonVoisin = await page.evaluate(async ({ e, m }) => {
      const r = await fetch('/api/auth/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: e, password: m }),
      });
      const j = await r.json().catch(() => ({}));
      return j.token || j.access_token || (j.data && j.data.token) || '';
    }, { e: VOISIN, m: MDP });
    const croise = await page.evaluate(async ({ c, o, t, img }) => {
      const faire = async (chemin, corps) => {
        const r = await fetch('/api' + chemin, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + t },
          body: JSON.stringify(corps),
        });
        return r.status;
      };
      return {
        signature: await faire('/reservations/bilan-seance/signature',
          { courseId: c, occurrence: o, partner_signature: img }),
        partage: await faire('/reservations/bilan-seance/partage',
          { courseId: c, occurrence: o, partner_name: 'PIRATE', partner_percentage: 90 }),
        paiement: await faire('/reservations/bilan-seance/paiement',
          { courseId: c, occurrence: o, paye: true }),
      };
    }, { c: COURS_BILAN, o: OCC, t: jetonVoisin, img: SIGNATURE_PNG });
    verifier('C19. cross-coach : un autre coach ne SIGNE pas le bilan du voisin',
             croise.signature === 403, `statut=${croise.signature}`);
    verifier('C20. ... ne MODIFIE pas son partage', croise.partage === 403,
             `statut=${croise.partage}`);
    verifier('C21. ... ne DECLARE pas son paiement', croise.paiement === 403,
             `statut=${croise.paiement}`);
    const intact = await appeler(`/reservations/bilan-seance?courseId=${encodeURIComponent(COURS_BILAN)}&occurrence=${encodeURIComponent(OCC)}`);
    verifier('C22. apres les trois tentatives, le bilan du proprietaire est INTACT',
             (intact.corps.partage || {}).partner_name === 'LAFF'
             && (intact.corps.partage || {}).partner_percentage === 50,
             `partage=${JSON.stringify(intact.corps.partage)}`);

    // ── SIGNE N EST PAS PAYE ────────────────────────────────────────────────
    verifier('P1. par defaut le paiement n est PAS renseigne',
             ((intact.corps.partage || {}).paiement || {}).paye === false,
             `paiement=${JSON.stringify((intact.corps.partage || {}).paiement)}`);
    const decl = await appeler('/reservations/bilan-seance/paiement', {
      corps: { courseId: COURS_BILAN, occurrence: OCC, paye: true, payment_method: 'especes' } });
    verifier('P2. le coach DECLARE le reglement', decl.statut === 200,
             `statut=${decl.statut}`);
    const apres = await appeler(`/reservations/bilan-seance?courseId=${encodeURIComponent(COURS_BILAN)}&occurrence=${encodeURIComponent(OCC)}`);
    verifier('P3. la declaration est relue, avec son auteur',
             ((apres.corps.partage || {}).paiement || {}).paye === true
             && ((apres.corps.partage || {}).paiement || {}).paid_by === COACH,
             `paiement=${JSON.stringify((apres.corps.partage || {}).paiement)}`);
    verifier('P4. declarer un paiement ne touche AUCUN montant',
             (apres.corps.partage || {}).partner_amount === (intact.corps.partage || {}).partner_amount
             && apres.corps.total_connu === intact.corps.total_connu,
             `avant=${(intact.corps.partage || {}).partner_amount} apres=${(apres.corps.partage || {}).partner_amount}`);
    const retire = await appeler('/reservations/bilan-seance/paiement', {
      corps: { courseId: COURS_BILAN, occurrence: OCC, paye: false } });
    const apres2 = await appeler(`/reservations/bilan-seance?courseId=${encodeURIComponent(COURS_BILAN)}&occurrence=${encodeURIComponent(OCC)}`);
    verifier('P5. une declaration erronee se retire proprement',
             retire.statut === 200
             && ((apres2.corps.partage || {}).paiement || {}).paye === false,
             `paiement=${JSON.stringify((apres2.corps.partage || {}).paiement)}`);

    // ── L ECRITURE CASQUE QUI ECHOUE NE CHANGE RIEN ─────────────────────────
    const avantEchec = py(`
import pymongo
c = pymongo.MongoClient("mongodb://127.0.0.1:${PORT_MONGO}")
r = c["${DBNAME}"]["reservations"].find_one({"id":"re-avec"}, {"_id":0,"headphone_status":1})
print(r.get("headphone_status"))`).trim();
    const echec = await appeler('/reservations/id-qui-nexiste-pas/headphone',
                                { methode: 'PUT', corps: { status: 'taken' } });
    const apresEchec = py(`
import pymongo
c = pymongo.MongoClient("mongodb://127.0.0.1:${PORT_MONGO}")
r = c["${DBNAME}"]["reservations"].find_one({"id":"re-avec"}, {"_id":0,"headphone_status":1})
print(r.get("headphone_status"))`).trim();
    verifier('B7. une ecriture casque qui echoue est REFUSEE, pas silencieuse',
             echec.statut >= 400, `statut=${echec.statut}`);
    verifier('B8. ... et aucun autre casque n a bouge',
             avantEchec === apresEchec && avantEchec === 'returned',
             `avant=${avantEchec} apres=${apresEchec}`);
    const statutInvalide = await appeler('/reservations/re-avec/headphone',
                                         { methode: 'PUT', corps: { status: 'perdu' } });
    verifier('B9. un etat de casque invente est refuse (400)',
             statutInvalide.statut === 400, `statut=${statutInvalide.statut}`);

    // ── LE FORMAT QUE PRODUIT VRAIMENT UN CANVAS ────────────────────────────
    // Jusqu'ici la signature envoyee etait un PNG que J'AI fabrique. Ce test
    // referme la boucle : un canvas de navigateur, peint et trace exactement
    // comme le fait l'ecran, puis `toDataURL` — et le serveur l'accepte.
    // C'est le seul moyen de savoir que la validation ne rejettera pas la
    // seule image que le coach produira jamais.
    const duCanvas = await page.evaluate(async ({ c, o, t }) => {
      const cv = document.createElement('canvas');
      cv.width = 560; cv.height = 170;
      const ctx = cv.getContext('2d');
      ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, cv.width, cv.height);
      ctx.lineWidth = 2.5; ctx.lineCap = 'round'; ctx.strokeStyle = '#111111';
      ctx.beginPath(); ctx.moveTo(40, 120); ctx.lineTo(160, 40);
      ctx.lineTo(260, 130); ctx.stroke();
      const image = cv.toDataURL('image/png');
      const r = await fetch('/api/reservations/bilan-seance/signature', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + t },
        body: JSON.stringify({ courseId: c, occurrence: o, partner_signature: image }),
      });
      return { statut: r.status, prefixe: image.slice(0, 22), taille: image.length };
    }, { c: COURS_BILAN, o: OCC, t: jeton });
    verifier('C15. l image que produit REELLEMENT un canvas est acceptee',
             duCanvas.statut === 200
             && duCanvas.prefixe === 'data:image/png;base64,',
             `statut=${duCanvas.statut} prefixe=${duCanvas.prefixe} taille=${duCanvas.taille}`);
    verifier('C16. ... et elle tient largement sous la borne serveur',
             duCanvas.taille < 400000, `taille=${duCanvas.taille}`);

    // ── L ECRAN, MOBILE D ABORD ─────────────────────────────────────────────
    // Le panneau vit dans un portail au sein d'un ChatWidget de 12 000 lignes :
    // le monter ici exigerait un contexte que ce banc ne reproduirait pas
    // honnetement. Ce qu'on verifie donc, c'est que le MARQUAGE attendu par
    // l'ecran correspond exactement a ce que la route rend — et on le dit.
    const source = fs.readFileSync(path.join(DEPOT, 'frontend/src/components/ChatWidget.js'), 'utf8');
    for (const [ecran, taille] of [['mobile', { width: 390, height: 844 }],
                                   ['desktop', { width: 1280, height: 900 }]]) {
      const p2 = await ctx.newPage();
      await p2.setViewportSize(taille);
      await p2.goto('/healthz');
      const largeur = await p2.evaluate(() => window.innerWidth);
      verifier(`D. ${ecran} : la page s ouvre a ${taille.width} px`,
               largeur === taille.width, `largeur=${largeur}`);
      await p2.close();
    }
    verifier('D1. l ecran lit `acces.tarif_public` — le champ que la route rend',
             source.includes('acces.tarif_public'));
    verifier('D2. l ecran lit `partage.signature` — le champ que la route rend',
             source.includes('partage.signature'));
    verifier('D3. le scan rend la MEME rangee de casques que les transactions',
             source.includes('renderCoachHeadphoneRow(qrScanResult.reservation, true)'));
    verifier('D6. sur le scan, la cible du casque fait 44 px — utilisable en mouvement',
             /minHeight: grand \? '44px'/.test(source));
    verifier('D7. l etat du casque est dit par un MOT, pas seulement par une couleur',
             source.includes('casque-libelle') && source.includes("'Casque remis'")
             && source.includes("'Casque rendu'"));
    verifier('D8. SIGNE et PAYE sont deux lignes distinctes a l ecran',
             source.includes('paiement-statut') && source.includes('Non renseigné'));
    verifier('D9. le recapitulatif porte le cours ET la date de la seance signee',
             /ligneRecap\('Cours'/.test(source) && /ligneRecap\('Date'/.test(source));
    verifier('D4. la couleur du casque n avance qu APRES la reponse du serveur',
             /axios\.put\(url, body\)\.then\(function\(\) \{\s*applyStatus\(next\)/.test(source),
             'un affichage optimiste subsiste');
    verifier('D5. aucune boite modale bloquante dans le parcours casque',
             !/alert\('Impossible de mettre a jour|alert\('Impossible de mettre à jour/.test(source));

    const ok = resultats.filter((r) => r.ok).length;
    console.log('\n' + '='.repeat(74));
    console.log('TERRAIN EVENT — NAVIGATEUR REEL (essai, casque, signature)');
    console.log('='.repeat(74));
    console.log(`Backend reel, mongod jetable, Chromium. Donnees de production : 0.`);
    console.log(`Aucun paiement declenche. ${ok} / ${resultats.length} verifications`);
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
