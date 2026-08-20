/**
 * LOT 3c-0 — LE PARCOURS PARTENAIRE, DANS UN VRAI NAVIGATEUR.
 *
 * CE QUE CE TEST PROUVE, ET QU'UN TEST UNITAIRE NE PROUVE PAS
 * ----------------------------------------------------------
 * Les tests unitaires extraient une fonction et l'executent contre une base en
 * memoire. Ils prouvent la REGLE. Ils ne prouvent pas que la regle est bien
 * celle que le serveur applique quand une requete arrive vraiment, ni que le
 * modele Pydantic laisse passer les champs dont elle depend — c'est
 * exactement le genre de trou qui a fait planter b159717 en production.
 *
 * Ici tournent : le VRAI backend FastAPI du depot (uvicorn), une VRAIE base
 * MongoDB jetable, et un VRAI navigateur Chromium qui emet les requetes. Le
 * navigateur est enferme : toute requete hors de 127.0.0.1 est coupee.
 *
 * LE SCENARIO CRITIQUE
 * --------------------
 *   Coach A = la plateforme.  Coach B = un partenaire.
 *   Un client reserve chez B  -> la reservation appartient a B.
 *   Un client reserve chez A  -> la reservation appartient a A.
 *   Un menteur reserve le cours de A en se declarant B -> elle reste a A.
 *
 * ET LA NON-REGRESSION LOT 1 : sur un cours RECURRENT, la 2e occurrence
 * choisie est bien celle enregistree — meme jour, meme heure, meme cours,
 * meme proprietaire. LOT 3c-0 ne doit pas defaire ce que LOT 1 a corrige.
 *
 * AUCUNE DONNEE DE PRODUCTION. Base jetable, port 28018, detruite a la fin.
 *
 *   node tests/test_lot3c0_navigateur.mjs
 */
import fs from 'fs';
import os from 'os';
import path from 'path';
import { spawn, spawnSync } from 'child_process';
import { createRequire } from 'module';

const require_ = createRequire(import.meta.url);
const { chromium } = require_('/Users/afroboost/.claude/skills/gstack/node_modules/playwright-core');

const RACINE = path.dirname(new URL(import.meta.url).pathname.replace(/\/tests$/, ''));
const DEPOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const PY = process.env.AFROBOOST_PY || '/tmp/venv-prod/bin/python';
const MONGOD = process.env.AFROBOOST_MONGOD || 'mongod';
const PORT_MONGO = 28018;
const PORT_API = 8098;
const BASE = `http://127.0.0.1:${PORT_API}`;
const DBDIR = path.join(os.tmpdir(), 'afroboost-lot3c0-mongo');
const DBNAME = 'lot3c0_navigateur';

const ADMIN = 'contact.artboost@gmail.com';   // = SUPER_ADMIN_EMAILS[0] = plateforme
const COACH_B = 'coach.b@partenaire.ch';

const resultats = [];
function verifier(titre, condition, detail) {
  resultats.push({ titre, ok: !!condition, detail: detail || '' });
  console.log(`${condition ? '  OK  ' : ' ECHEC'} ${titre}${condition || !detail ? '' : ` -> ${detail}`}`);
}

const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

async function attendre(url, essais = 40) {
  for (let i = 0; i < essais; i++) {
    try {
      const r = await fetch(url);
      if (r.ok) return true;
    } catch { /* pas encore la */ }
    await dormir(500);
  }
  return false;
}

/** Seme la base par pymongo — le navigateur n'a aucun moyen de creer un cours
 *  sans authentification, et lui en donner une fausserait le test. */
function semer() {
  const script = `
import pymongo
c = pymongo.MongoClient("mongodb://127.0.0.1:${PORT_MONGO}")
d = c["${DBNAME}"]
for n in ("reservations","courses","coaches","offers"): d[n].delete_many({})
d.coaches.insert_many([{"email": "${ADMIN}"}, {"email": "${COACH_B}"}])
d.courses.insert_many([
  {"id":"cours-A","name":"Silent Lundi A","coach_id":"${ADMIN}","weekday":1,
   "time":"18:30","visible":True,"archived":False,"locationName":"Geneve"},
  # LOT 1 : cours RECURRENT du mercredi -> plusieurs occurrences possibles.
  {"id":"cours-B","name":"Afro Mercredi B","coach_id":"${COACH_B}","weekday":3,
   "time":"19:00","visible":True,"archived":False,"locationName":"Lausanne"},
])
print("SEME")
`;
  const r = spawnSync(PY, ['-c', script], { encoding: 'utf-8' });
  if (!r.stdout.includes('SEME')) throw new Error('semis impossible : ' + (r.stderr || r.stdout));
}

function lireReservations() {
  const script = `
import pymongo, json
c = pymongo.MongoClient("mongodb://127.0.0.1:${PORT_MONGO}")
docs = list(c["${DBNAME}"].reservations.find({}, {"_id":0,"userName":1,"coach_id":1,"courseId":1,"datetime":1,"selectedDates":1}))
print(json.dumps(docs, default=str))
`;
  const r = spawnSync(PY, ['-c', script], { encoding: 'utf-8' });
  try { return JSON.parse(r.stdout.trim().split('\n').pop()); }
  catch { throw new Error('lecture impossible : ' + (r.stderr || r.stdout)); }
}

/** Les deux prochains mercredis, en heure locale — LOT 1 exige que la date
 *  envoyee tombe le bon JOUR de la semaine, sinon elle refuse (a juste titre). */
function prochainsMercredis() {
  const out = [];
  const d = new Date();
  d.setHours(19, 0, 0, 0);
  while (out.length < 2) {
    d.setDate(d.getDate() + 1);
    if (d.getDay() === 3) out.push(new Date(d));
  }
  return out;
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
           DB_NAME: DBNAME, JWT_SECRET: 'test-secret-lot3c0' },
  });
  let journalApi = '';
  api.stderr.on('data', (b) => { journalApi += b.toString(); });

  let navigateur;
  try {
    if (!await attendre(`http://127.0.0.1:${PORT_MONGO}`, 30)) {
      // mongod repond en HTTP par un refus : c'est suffisant pour dire « il ecoute ».
    }
    await dormir(1500);
    if (!await attendre(`${BASE}/healthz`)) {
      console.error('\nLe backend n\'a pas demarre. Journal :\n' + journalApi.slice(-2000));
      console.error('\nPrerequis : mongod dans le PATH, et le venv de production :');
      console.error('  python3.13 -m venv /tmp/venv-prod');
      console.error('  /tmp/venv-prod/bin/pip install -r api/requirements.txt');
      return 2;
    }
    semer();

    navigateur = await chromium.launch({ headless: true });
    const ctx = await navigateur.newContext({ baseURL: BASE });
    await ctx.route('**/*', (route) => {
      const u = new URL(route.request().url());
      if (u.hostname !== '127.0.0.1') return route.abort();   // rien ne sort d'ici
      return route.continue();
    });
    const page = await ctx.newPage();
    const erreurs = [];
    page.on('pageerror', (e) => erreurs.push(String(e)));
    await page.goto('/healthz');

    // Le navigateur emet les reservations, comme le ferait la vitrine.
    const reserver = (corps) => page.evaluate(async (c) => {
      const r = await fetch('/api/reservations', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(c),
      });
      let corpsRep = null;
      try { corpsRep = await r.json(); } catch { corpsRep = null; }
      return { statut: r.status, corps: corpsRep };
    }, corps);

    const [merc1, merc2] = prochainsMercredis();
    const lundiA = (() => {
      const d = new Date(); d.setHours(18, 30, 0, 0);
      while (d.getDay() !== 1) d.setDate(d.getDate() + 1);
      return d;
    })();

    // === A — LE CLIENT RESERVE CHEZ LE PARTENAIRE B ======================
    const rB = await reserver({
      userName: 'Client de B', userEmail: 'client.b@test.ch',
      courseId: 'cours-B', courseName: 'Afro Mercredi B', courseTime: '19:00',
      datetime: merc1.toISOString(), selectedDates: [merc1.toISOString()],
      offerName: 'Séance', totalPrice: 30, quantity: 1,
      coach_id: COACH_B, source: 'vitrine_partenaire',
    });
    verifier('A1 la reservation chez B est acceptee', rB.statut === 200,
      JSON.stringify(rB.corps).slice(0, 200));

    // === B — LE CLIENT RESERVE CHEZ LA PLATEFORME A ======================
    const rA = await reserver({
      userName: 'Client de A', userEmail: 'client.a@test.ch',
      courseId: 'cours-A', courseName: 'Silent Lundi A', courseTime: '18:30',
      datetime: lundiA.toISOString(), selectedDates: [lundiA.toISOString()],
      offerName: 'Séance', totalPrice: 30, quantity: 1, source: 'website',
    });
    verifier('B1 la reservation chez A est acceptee', rA.statut === 200,
      JSON.stringify(rA.corps).slice(0, 200));

    // === C — LE VOL : cours de A, mais le corps declare B ================
    const rVol = await reserver({
      userName: 'Menteur', userEmail: 'menteur@test.ch',
      courseId: 'cours-A', courseName: 'Silent Lundi A', courseTime: '18:30',
      datetime: lundiA.toISOString(), selectedDates: [lundiA.toISOString()],
      offerName: 'Séance', totalPrice: 30, quantity: 1,
      coach_id: COACH_B, source: 'vitrine_partenaire',
    });
    verifier('C1 la tentative de vol est acceptee comme reservation (elle paie)',
      rVol.statut === 200, JSON.stringify(rVol.corps).slice(0, 200));

    // === D — PRODUIT chez B, sans cours : le coach declare VERIFIE sert ==
    const rProd = await reserver({
      userName: 'Produit de B', userEmail: 'prod.b@test.ch',
      offerName: 'T-shirt', totalPrice: 40, quantity: 1, isProduct: true,
      coach_id: COACH_B, source: 'vitrine_partenaire',
    });
    verifier('D1 le produit vendu chez B est accepte', rProd.statut === 200,
      JSON.stringify(rProd.corps).slice(0, 200));

    // === E — PRODUIT avec un coach INVENTE ===============================
    const rPirate = await reserver({
      userName: 'Pirate', userEmail: 'pirate@test.ch',
      offerName: 'T-shirt', totalPrice: 40, quantity: 1, isProduct: true,
      coach_id: 'pirate@nulle-part.xx',
    });
    verifier('E1 le produit au coach invente est accepte comme reservation',
      rPirate.statut === 200, JSON.stringify(rPirate.corps).slice(0, 200));

    // === F — LOT 1 : la 2e OCCURRENCE d'un cours recurrent ===============
    const rOcc = await reserver({
      userName: 'Occurrence 2', userEmail: 'occ2@test.ch',
      courseId: 'cours-B', courseName: 'Afro Mercredi B', courseTime: '19:00',
      datetime: merc2.toISOString(), selectedDates: [merc2.toISOString()],
      offerName: 'Séance', totalPrice: 30, quantity: 1, coach_id: COACH_B,
    });
    verifier('F1 la 2e occurrence est acceptee', rOcc.statut === 200,
      JSON.stringify(rOcc.corps).slice(0, 200));

    // === G — CE QUE LA BASE A REELLEMENT ENREGISTRE ======================
    const docs = lireReservations();
    const par = (n) => docs.find((d) => d.userName === n) || {};

    verifier('G1 PROPRIETE — le client de B appartient a B',
      par('Client de B').coach_id === COACH_B, par('Client de B').coach_id);
    verifier('G2 PROPRIETE — le client de A appartient a A',
      par('Client de A').coach_id === ADMIN, par('Client de A').coach_id);
    verifier('G3 ISOLATION — la reservation de B n\'appartient PAS a A',
      par('Client de B').coach_id !== ADMIN, par('Client de B').coach_id);
    verifier('G4 FALSIFICATION — le cours de A l\'emporte sur le coach_id declare : '
      + 'la propriete ne se vole pas',
      par('Menteur').coach_id === ADMIN, par('Menteur').coach_id);
    verifier('G5 PRODUIT — un coach declare et VERIFIE garde sa vente',
      par('Produit de B').coach_id === COACH_B, par('Produit de B').coach_id);
    verifier('G6 PRODUIT — un coach INVENTE n\'obtient rien',
      par('Pirate').coach_id === ADMIN, par('Pirate').coach_id);

    // LOT 1 — ce que le client a choisi est ce qui est enregistre.
    const occ = par('Occurrence 2');
    const jour = (s) => String(s || '').slice(0, 10);
    verifier('G7 LOT 1 — la 2e occurrence garde SA date (pas celle du clic)',
      jour(occ.datetime) === jour(merc2.toISOString())
      || jour((occ.selectedDates || [])[0]) === jour(merc2.toISOString()),
      `enregistre=${occ.datetime} attendu=${merc2.toISOString()}`);
    verifier('G8 LOT 1 — ... et elle garde le bon cours',
      occ.courseId === 'cours-B', occ.courseId);
    verifier('G9 LOT 1 — ... et le bon proprietaire',
      occ.coach_id === COACH_B, occ.coach_id);
    verifier('G10 LOT 1 — les deux occurrences sont DISTINCTES',
      jour(par('Client de B').datetime) !== jour(occ.datetime),
      `${par('Client de B').datetime} vs ${occ.datetime}`);

    // === H — LES REPLIS NON PROUVES SONT CRIES ===========================
    verifier('H1 le repli plateforme d\'un coach invente est CRIE dans les journaux',
      journalApi.includes('coach_declare_inconnu'),
      journalApi.slice(-300));

    verifier('I1 aucune erreur JavaScript', erreurs.length === 0, erreurs.slice(0, 2).join(' | '));

    await ctx.close();
  } finally {
    if (navigateur) await navigateur.close().catch(() => {});
    api.kill('SIGKILL');
    mongo.kill('SIGKILL');
    await dormir(400);
    fs.rmSync(DBDIR, { recursive: true, force: true });
  }

  const ok = resultats.filter((r) => r.ok).length;
  console.log('\n' + '='.repeat(74));
  console.log('LOT 3c-0 — LE PARCOURS PARTENAIRE, DANS UN VRAI NAVIGATEUR');
  console.log('='.repeat(74));
  console.log('Base jetable detruite. Donnees de production touchees : 0.');
  console.log(`${ok} / ${resultats.length} verifications`);
  return ok === resultats.length ? 0 : 1;
}

principal().then((c) => process.exit(c)).catch((e) => {
  console.error('ERREUR : ' + (e && e.stack ? e.stack : e));
  process.exit(2);
});
