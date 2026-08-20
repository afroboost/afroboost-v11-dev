/**
 * LOT 3c-0b — LES QUATRE PORTES, MESUREES POUR DE VRAI.
 *
 * POURQUOI CE TEST EXISTE. Les tests unitaires extraient une fonction et lui
 * donnent une identite fabriquee. Ils prouvent la REGLE. Ils ne prouvent pas
 * que le SERVEUR refuse vraiment un anonyme, ni qu'un JWT REELLEMENT EMIS par
 * `/auth/login` ouvre la porte. C'est pourtant la seule preuve qu'exige la
 * regle V310c : « 200 AVEC le jeton legitime, 403 SANS, sur LA MEME route ».
 *
 * Ici tournent : le VRAI backend FastAPI, une VRAIE base MongoDB jetable, de
 * VRAIS comptes coach crees par `/auth/register`, de VRAIS jetons signes, et
 * un VRAI navigateur Chromium qui emet les requetes — enferme sur 127.0.0.1.
 *
 * LES QUATRE PORTES :
 *   A  PUT /discount-codes/subscriptions/{id}   seances + montant
 *   B  PUT /subscriptions/{id}/sessions         solde de seances
 *   C  PUT /subscriptions/{code}/profile        donnees personnelles
 *   D  POST /discount-codes                     creation d'un code
 *
 * AUCUNE DONNEE DE PRODUCTION. Base jetable, port 28019, detruite a la fin.
 *
 *   node tests/test_lot3c0b_navigateur.mjs
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
const PORT_MONGO = 28019;
const PORT_API = 8097;
const BASE = `http://127.0.0.1:${PORT_API}`;
const DBDIR = path.join(os.tmpdir(), 'afroboost-lot3c0b-mongo');
const DBNAME = 'lot3c0b_navigateur';

const ADMIN = 'contact.artboost@gmail.com';
const COACH_B = 'coach.b@partenaire.ch';
const COACH_C = 'coach.c@partenaire.ch';
const MDP = 'MotDePasseTest!2026';

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

function semer() {
  const s = `
import pymongo
c = pymongo.MongoClient("mongodb://127.0.0.1:${PORT_MONGO}")
d = c["${DBNAME}"]
for n in ("subscriptions","discount_codes","coaches"): d[n].delete_many({})
d.coaches.insert_many([{"email":"${ADMIN}"},{"email":"${COACH_B}"},{"email":"${COACH_C}"}])
d.subscriptions.insert_one({"id":"sub-B","code":"BCODE-01","coach_id":"${COACH_B}",
  "email":"client.b@test.ch","remaining_sessions":5,"used_sessions":5,
  "offer_price":250.0,"total_sessions":10,"status":"active","name":"Nom initial"})
print("SEME")`;
  if (!py(s).includes('SEME')) throw new Error('semis impossible');
}

function lire(coll, filtre) {
  const s = `
import pymongo, json
c = pymongo.MongoClient("mongodb://127.0.0.1:${PORT_MONGO}")
docs = list(c["${DBNAME}"]["${coll}"].find(${filtre}, {"_id":0}))
print("JSON:"+json.dumps(docs, default=str))`;
  const out = py(s);
  const l = out.split('\n').find((x) => x.startsWith('JSON:'));
  return l ? JSON.parse(l.slice(5)) : [];
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
           DB_NAME: DBNAME, JWT_SECRET: 'test-secret-lot3c0b' },
  });
  let journal = '';
  api.stderr.on('data', (b) => { journal += b.toString(); });

  let navigateur;
  try {
    await dormir(1500);
    if (!await attendre(`${BASE}/healthz`)) {
      console.error('Backend non demarre.\n' + journal.slice(-1500));
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

    /** Un VRAI compte, un VRAI jeton : c'est la preuve exigee par V310c.
     *
     *  L'auto-inscription cree le compte en `pending_validation: true` — un
     *  administrateur doit l'approuver avant la premiere connexion. On rejoue
     *  donc cette approbation sur la base JETABLE, sinon `/auth/login` refuse
     *  et le test ne pourrait pas prouver le « 200 AVEC jeton ». C'est une
     *  fixture, pas un contournement : elle reproduit ce que fait l'admin. */
    const inscrire = async (email) => {
      await page.evaluate(async ({ e, m }) => {
        await fetch('/api/auth/register', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: e, password: m, name: e.split('@')[0] }),
        }).catch(() => {});
      }, { e: email, m: MDP });
      py(`
import pymongo
c = pymongo.MongoClient("mongodb://127.0.0.1:${PORT_MONGO}")
c["${DBNAME}"].users_auth.update_one({"email": "${email}"},
                                     {"$set": {"pending_validation": False}})
print("VALIDE")`);
      return page.evaluate(async ({ e, m }) => {
        const r = await fetch('/api/auth/login', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: e, password: m }),
        });
        const j = await r.json().catch(() => ({}));
        return j.token || j.access_token || (j.data && j.data.token) || '';
      }, { e: email, m: MDP });
    };

    const jetonB = await inscrire(COACH_B);
    const jetonC = await inscrire(COACH_C);
    verifier('0a le coach B obtient un VRAI jeton signe via /auth/login',
      !!jetonB && jetonB.split('.').length === 3, jetonB ? 'len=' + jetonB.length : 'AUCUN');
    verifier('0b le coach C aussi', !!jetonC && jetonC.split('.').length === 3);

    /** Un appel HTTP depuis le navigateur. `jeton` = signature ; `declare` =
     *  en-tete X-User-Email seul, c'est-a-dire une identite NON prouvee. */
    const appel = (methode, url, corps, jeton, declare) => page.evaluate(
      async ({ m, u, c, j, d }) => {
        const h = { 'Content-Type': 'application/json' };
        if (j) h['Authorization'] = 'Bearer ' + j;
        if (d) h['X-User-Email'] = d;
        const r = await fetch(u, { method: m, headers: h, body: c ? JSON.stringify(c) : undefined });
        return r.status;
      }, { m: methode, u: url, c: corps, j: jeton, d: declare });

    // === A — PUT /discount-codes/subscriptions/{id} =======================
    const A = '/api/discount-codes/subscriptions/sub-B';
    verifier('A1 anonyme -> 403', await appel('PUT', A, { remaining_sessions: 99 }) === 403);
    verifier('A2 X-User-Email FORGE (sans signature) -> 403',
      await appel('PUT', A, { remaining_sessions: 99 }, null, COACH_B) === 403);
    verifier('A3 un AUTRE coach, pourtant signe -> 403',
      await appel('PUT', A, { remaining_sessions: 99 }, jetonC) === 403);
    verifier('A4 le PROPRIETAIRE signe -> 200  (preuve V310c : meme route)',
      await appel('PUT', A, { remaining_sessions: 7 }, jetonB) === 200);
    verifier('A5 ... et la valeur est REELLEMENT enregistree',
      (lire('subscriptions', '{"id":"sub-B"}')[0] || {}).remaining_sessions === 7,
      JSON.stringify(lire('subscriptions', '{"id":"sub-B"}')[0] || {}).slice(0, 120));

    // === B — PUT /subscriptions/{id}/sessions =============================
    const B = '/api/subscriptions/sub-B/sessions';
    verifier('B1 anonyme -> 403', await appel('PUT', B, { action: 'add', amount: 1 }) === 403);
    verifier('B2 X-User-Email FORGE -> 403 (avant, `require_auth` l\'acceptait)',
      await appel('PUT', B, { action: 'add', amount: 1 }, null, COACH_B) === 403);
    verifier('B3 un AUTRE coach signe -> 403',
      await appel('PUT', B, { action: 'add', amount: 1 }, jetonC) === 403);
    const avantB = (lire('subscriptions', '{"id":"sub-B"}')[0] || {}).remaining_sessions;
    verifier('B4 le PROPRIETAIRE signe -> 200  (preuve V310c)',
      await appel('PUT', B, { action: 'add', amount: 1 }, jetonB) === 200);
    verifier('B5 ... et la seance est REELLEMENT ajoutee (regle metier intacte)',
      (lire('subscriptions', '{"id":"sub-B"}')[0] || {}).remaining_sessions === avantB + 1,
      `avant=${avantB} apres=${(lire('subscriptions', '{"id":"sub-B"}')[0] || {}).remaining_sessions}`);

    // === C — PUT /subscriptions/{code}/profile ============================
    const C = '/api/subscriptions/BCODE-01/profile';
    verifier('C0 anonyme SANS code ni jeton -> 403',
      await appel('PUT', C, { name: 'Anonyme' }) === 403);
    verifier('C1 un AUTRE coach signe -> 403 (le cloisonnement inter-coach)',
      await appel('PUT', C, { name: 'Vole' }, jetonC) === 403);
    verifier('C2 le coach PROPRIETAIRE signe -> 200',
      await appel('PUT', C, { name: 'Par le coach' }, jetonB) === 200);
    verifier('C3 L\'ABONNE LUI-MEME, avec son code, passe TOUJOURS — le parcours '
      + 'd\'onboarding n\'est pas casse (regle V310c)',
      await appel('PUT', C, { name: 'Par l\'abonne', code: 'BCODE-01' }) === 200);
    verifier('C4 ... et son nom est REELLEMENT enregistre',
      (lire('subscriptions', '{"id":"sub-B"}')[0] || {}).name === "Par l'abonne",
      String((lire('subscriptions', '{"id":"sub-B"}')[0] || {}).name));
    verifier('C5 le champ `code` du corps n\'a PAS ete ecrit en base',
      (lire('subscriptions', '{"id":"sub-B"}')[0] || {}).code === 'BCODE-01');

    // === D — POST /discount-codes ========================================
    const D = '/api/discount-codes';
    const codeCorps = (c, proprio) => ({
      code: c, type: '100%', value: 100, maxUses: 10, courses: [],
      targetCategories: [], coach_id: proprio || null,
    });
    verifier('D1 anonyme -> 403 (il creait un code gratuit + 2 e-mails)',
      await appel('POST', D, codeCorps('ANON-01')) === 403);
    verifier('D2 X-User-Email FORGE -> 403',
      await appel('POST', D, codeCorps('FORGE-01'), null, COACH_B) === 403);
    verifier('D3 aucun code n\'a ete cree par les deux refus',
      lire('discount_codes', '{}').length === 0, String(lire('discount_codes', '{}').length));
    verifier('D4 le coach signe cree son code -> 200',
      await appel('POST', D, codeCorps('B-01'), jetonB) === 200);
    verifier('D5 ... et le code lui appartient',
      (lire('discount_codes', '{"code":"B-01"}')[0] || {}).coach_id === COACH_B,
      String((lire('discount_codes', '{"code":"B-01"}')[0] || {}).coach_id));
    await appel('POST', D, codeCorps('B-02', COACH_C), jetonB);
    verifier('D6 CROSS-COACH — B declare C dans le corps : IGNORE, le code reste a B',
      (lire('discount_codes', '{"code":"B-02"}')[0] || {}).coach_id === COACH_B,
      String((lire('discount_codes', '{"code":"B-02"}')[0] || {}).coach_id));

    await ctx.close();
  } finally {
    if (navigateur) await navigateur.close().catch(() => {});
    api.kill('SIGKILL'); mongo.kill('SIGKILL');
    await dormir(400);
    fs.rmSync(DBDIR, { recursive: true, force: true });
  }

  const ok = resultats.filter((r) => r.ok).length;
  console.log('\n' + '='.repeat(74));
  console.log('LOT 3c-0b — LES QUATRE PORTES, MESUREES DANS UN VRAI NAVIGATEUR');
  console.log('='.repeat(74));
  console.log('Base jetable detruite. Donnees de production touchees : 0.');
  console.log(`${ok} / ${resultats.length} verifications`);
  return ok === resultats.length ? 0 : 1;
}

principal().then((c) => process.exit(c)).catch((e) => {
  console.error('ERREUR : ' + (e && e.stack ? e.stack : e));
  process.exit(2);
});
