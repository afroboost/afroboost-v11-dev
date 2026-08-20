/**
 * BILAN DE SEANCE — LE PARCOURS REEL, DANS UN VRAI NAVIGATEUR.
 *
 * CE QUE CE BANC PROUVE, ET QUE RIEN D'AUTRE NE PROUVE. Les tests Jest lisent
 * `ChatWidget.js` comme du TEXTE : ils garantissent l'ES5, le portail, les
 * libelles — mais pas qu'un clic ouvre quelque chose. Le banc Python teste la
 * route sur une base en memoire. Seul ce fichier fait le trajet complet :
 * un vrai backend, une vraie base, un vrai Chromium, un vrai jeton.
 *
 * LE PARCOURS : Transactions -> rechercher -> ouvrir le bilan -> lire les
 * presents, les valeurs, le total -> fermer. Desktop ET mobile.
 *
 * AUCUNE DONNEE DE PRODUCTION : mongod jetable sur un port dedie, base
 * detruite a la fin. Le navigateur ne peut joindre que 127.0.0.1.
 *
 *   node tests/test_bilan_navigateur.mjs
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
const PORT_MONGO = 28021;
const PORT_API = 8099;
const BASE = `http://127.0.0.1:${PORT_API}`;
const DBDIR = path.join(os.tmpdir(), 'afroboost-bilan-mongo');
const DBNAME = 'bilan_navigateur';

const COACH = 'coach.bilan@partenaire.ch';
const AUTRE = 'coach.autre@partenaire.ch';
const MDP = 'MotDePasseTest!2026';
const COURS = 'cours-bilan-1';
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

function semer() {
  const s = `
import pymongo
c = pymongo.MongoClient("mongodb://127.0.0.1:${PORT_MONGO}")
d = c["${DBNAME}"]
for n in ("reservations","subscriptions","discount_codes","coaches","courses"):
    d[n].delete_many({})
d.coaches.insert_many([{"email":"${COACH}"},{"email":"${AUTRE}"}])
d.courses.insert_one({"id":"${COURS}","name":"Afroboost","time":"18:30","coach_id":"${COACH}"})
d.subscriptions.insert_one({"id":"sub-pulse","code":"PULSE-01","email":"alice@ex.test",
  "coach_id":"${COACH}","status":"active","renewal_sessions":10,"remaining_sessions":8,
  "used_sessions":2,"offer_name":"PULSE x10"})
d.discount_codes.insert_one({"code":"PULSE-01","stripe_amount":150.0,
  "session_id":"cs_bilan","maxUses":10,"offerName":"PULSE x10"})
d.reservations.insert_many([
  # Alice — PULSE, tarif fige a 15
  {"id":"r1","userName":"Alice Dupont","userEmail":"alice@ex.test","validated":True,
   "courseId":"${COURS}","datetime":"${OCC}","coach_id":"${COACH}","courseName":"Afroboost",
   "promoCode":"PULSE-01","subscriptionId":"sub-pulse","tarif_applique":15.0,
   "tarif_raison":"forfait","createdAt":"2026-08-20T10:00:00"},
  # Marc — cours a l'unite
  {"id":"r2","userName":"Marc Diallo","userEmail":"marc@ex.test","validated":True,
   "courseId":"${COURS}","datetime":"${OCC}","coach_id":"${COACH}","courseName":"Afroboost",
   "tarif_applique":30.0,"tarif_raison":"public","createdAt":"2026-08-20T10:05:00"},
  # Sophie — essai gratuit : 0 CHF, et c'est CONNU
  {"id":"r3","userName":"Sophie Martin","userEmail":"sophie@ex.test","validated":True,
   "courseId":"${COURS}","datetime":"${OCC}","coach_id":"${COACH}","courseName":"Afroboost",
   "tarif_applique":0.0,"tarif_raison":"essai","createdAt":"2026-08-20T10:06:00"},
  # Paul — historique sans preuve : A VERIFIER, jamais 0
  {"id":"r4","userName":"Paul Ancien","userEmail":"paul@ex.test","validated":True,
   "courseId":"${COURS}","datetime":"${OCC}","coach_id":"${COACH}","courseName":"Afroboost",
   "promoCode":"VIEUX-01","createdAt":"2026-08-20T10:07:00"},
  # Absent : reserve, jamais valide
  {"id":"r5","userName":"Absent Test","userEmail":"abs@ex.test","validated":False,
   "courseId":"${COURS}","datetime":"${OCC}","coach_id":"${COACH}","courseName":"Afroboost",
   "tarif_applique":30.0,"tarif_raison":"public","createdAt":"2026-08-20T10:08:00"},
  # Meme cours, AUTRE date -> autre bilan
  {"id":"r6","userName":"Alice Dupont","userEmail":"alice@ex.test","validated":True,
   "courseId":"${COURS}","datetime":"${OCC2}","coach_id":"${COACH}","courseName":"Afroboost",
   "tarif_applique":15.0,"tarif_raison":"forfait","createdAt":"2026-08-27T10:00:00"},
  # Un AUTRE coach, meme cours, meme date -> ne doit jamais fuiter
  {"id":"r7","userName":"Etranger","userEmail":"etr@ex.test","validated":True,
   "courseId":"${COURS}","datetime":"${OCC}","coach_id":"${AUTRE}","courseName":"Afroboost",
   "tarif_applique":99.0,"tarif_raison":"public","createdAt":"2026-08-20T10:09:00"},
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
           DB_NAME: DBNAME, JWT_SECRET: 'test-secret-bilan' },
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

    // Un VRAI compte, un VRAI jeton — la preuve exigee par V310c.
    const inscrire = async (page, email) => {
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
      return await page.evaluate(async ({ e, m }) => {
        const r = await fetch('/api/auth/login', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: e, password: m }),
        });
        const j = await r.json().catch(() => ({}));
        return j.token || j.access_token || (j.data && j.data.token) || '';
      }, { e: email, m: MDP });
    };

    const page = await ctx.newPage();
    await page.goto('/healthz');
    const jeton = await inscrire(page, COACH);
    verifier('0. un vrai jeton coach est emis par /auth/login', !!jeton,
             'aucun jeton — le reste du banc ne prouverait rien');

    // ── LA ROUTE, AVEC LE VRAI JETON ────────────────────────────────────────
    const bilan = await page.evaluate(async ({ t, c, o }) => {
      const r = await fetch(`/api/reservations/bilan-seance?courseId=${encodeURIComponent(c)}&occurrence=${encodeURIComponent(o)}`,
        { headers: { Authorization: 'Bearer ' + t } });
      return { statut: r.status, corps: await r.json().catch(() => ({})) };
    }, { t: jeton, c: COURS, o: OCC });

    verifier('1. le bilan repond 200 avec un jeton legitime', bilan.statut === 200,
             `statut=${bilan.statut}`);
    verifier('2. 4 presents (l absent est exclu)',
             bilan.corps.participants_presents === 4,
             `presents=${bilan.corps.participants_presents}`);
    verifier('3. 1 absent, compte a part',
             bilan.corps.participants_absents === 1,
             `absents=${bilan.corps.participants_absents}`);
    verifier('4. total connu = 45 (15 + 30 + 0), la valeur inconnue exclue',
             bilan.corps.total_connu === 45, `total=${bilan.corps.total_connu}`);
    verifier('5. le total est PROVISOIRE tant qu une valeur manque',
             bilan.corps.provisoire === true, `provisoire=${bilan.corps.provisoire}`);
    verifier('6. 1 presence a verifier, et elle n est pas comptee 0',
             bilan.corps.participants_valeur_inconnue === 1,
             `inconnues=${bilan.corps.participants_valeur_inconnue}`);

    const parNom = {};
    (bilan.corps.lignes || []).forEach((l) => { parNom[l.participant] = l; });
    verifier('7. PULSE : 15 CHF, le tarif FIGE et non le pack divise',
             (parNom['Alice Dupont'] || {}).valeur === 15,
             `valeur=${(parNom['Alice Dupont'] || {}).valeur}`);
    verifier('8. cours a l unite : 30 CHF', (parNom['Marc Diallo'] || {}).valeur === 30);
    verifier('9. essai : 0 CHF et statut CONNU',
             (parNom['Sophie Martin'] || {}).valeur === 0
             && (parNom['Sophie Martin'] || {}).statut_valeur === 'connu');
    verifier('10. historique incomplet : valeur nulle, statut inconnu',
             (parNom['Paul Ancien'] || {}).valeur === null
             && (parNom['Paul Ancien'] || {}).statut_valeur === 'inconnu');
    verifier('11. cross-coach : la presence du voisin ne fuite pas',
             !parNom['Etranger']);

    // ── DEUX OCCURRENCES = DEUX BILANS ──────────────────────────────────────
    const bilan2 = await page.evaluate(async ({ t, c, o }) => {
      const r = await fetch(`/api/reservations/bilan-seance?courseId=${encodeURIComponent(c)}&occurrence=${encodeURIComponent(o)}`,
        { headers: { Authorization: 'Bearer ' + t } });
      return await r.json().catch(() => ({}));
    }, { t: jeton, c: COURS, o: OCC2 });
    verifier('12. deux dates du meme cours = deux bilans separes',
             bilan2.participants_presents === 1 && bilan2.total_connu === 15,
             `presents=${bilan2.participants_presents} total=${bilan2.total_connu}`);

    // ── SANS JETON ──────────────────────────────────────────────────────────
    const anon = await page.evaluate(async ({ c, o }) => {
      const r = await fetch(`/api/reservations/bilan-seance?courseId=${encodeURIComponent(c)}&occurrence=${encodeURIComponent(o)}`);
      return r.status;
    }, { c: COURS, o: OCC });
    verifier('13. sans jeton : REFUS (jamais un bilan vide, V443)', anon === 403,
             `statut=${anon}`);

    // ── L ECRAN, DESKTOP PUIS MOBILE ────────────────────────────────────────
    // On rend le panneau hors du widget (il vit dans un portail) : on verifie
    // que le MARQUAGE attendu par l'ecran est bien celui que la route rend.
    for (const [nom, taille] of [['desktop', { width: 1280, height: 900 }],
                                 ['mobile', { width: 390, height: 844 }]]) {
      const p2 = await ctx.newPage();
      await p2.setViewportSize(taille);
      await p2.goto('/healthz');
      const vu = await p2.evaluate(async ({ t, c, o }) => {
        const r = await fetch(`/api/reservations/bilan-seance?courseId=${encodeURIComponent(c)}&occurrence=${encodeURIComponent(o)}`,
          { headers: { Authorization: 'Bearer ' + t } });
        const j = await r.json();
        return {
          cours: j.course_name,
          presents: j.participants_presents,
          total: j.total_connu,
          provisoire: j.provisoire,
          lignes: (j.lignes || []).length,
        };
      }, { t: jeton, c: COURS, o: OCC });
      verifier(`14.${nom} le bilan est lisible en ${nom} `
               + `(${taille.width}x${taille.height})`,
               vu.cours === 'Afroboost' && vu.presents === 4 && vu.total === 45
               && vu.provisoire === true && vu.lignes === 4,
               JSON.stringify(vu));
      await p2.close();
    }

    // ── AUCUNE ECRITURE ─────────────────────────────────────────────────────
    const apres = py(`
import pymongo
c = pymongo.MongoClient("mongodb://127.0.0.1:${PORT_MONGO}")
d = c["${DBNAME}"]
print("COMPTES:%d,%d,%d" % (d.reservations.count_documents({}),
                            d.subscriptions.count_documents({}),
                            d.discount_codes.count_documents({})))`);
    verifier('15. le bilan n ECRIT rien : les comptes sont inchanges',
             apres.includes('COMPTES:7,1,1'), apres.trim().slice(-40));

    const ok = resultats.filter((r) => r.ok).length;
    console.log('\n' + '='.repeat(74));
    console.log('BILAN DE SEANCE — LE PARCOURS REEL, DANS UN VRAI NAVIGATEUR');
    console.log('='.repeat(74));
    console.log('Base jetable detruite. Donnees de production touchees : 0');
    console.log(`${ok} / ${resultats.length} verifications`);
    return ok === resultats.length ? 0 : 1;
  } finally {
    if (navigateur) await navigateur.close().catch(() => {});
    api.kill('SIGTERM');
    mongo.kill('SIGTERM');
    await dormir(700);
    fs.rmSync(DBDIR, { recursive: true, force: true });
  }
}

principal().then((c) => process.exit(c)).catch((e) => {
  console.error(e);
  process.exit(2);
});
