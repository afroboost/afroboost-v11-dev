/**
 * P0 — L'ESPACE PARTICIPANT NE RENDAIT AUCUNE RESERVATION.
 *
 * Vrai mongod jetable, vrai FastAPI, vraies requetes HTTP. Pas de navigateur :
 * ce qui est en cause est la REPONSE de `/api/subscriber/space/{code}`, pas son
 * rendu.
 *
 * MESURE DE PRODUCTION, 24/08/2026 :
 *     GET /api/subscriber/space/AFR-S4QYXD
 *       reservations : []
 *       trial        : {"is_trial": true, "state": "available"}
 * alors que la reservation existe et qu'elle est `validated: true`.
 *
 * CAUSE : `user_email_escaped` etait DEJA echappee, et le `$regex` la
 * re-echappait. `ex\.test` devenait `ex\\\.test` : le motif cherchait un
 * ANTISLASH suivi d'un point. Tout domaine d'e-mail contenant un point, la
 * recherche ne retrouvait PERSONNE.
 *
 * POUR VOIR LE ROUGE :  AFROBOOST_P0_CASSE=1 node tests/test_p0_espace_navigateur.mjs
 * (remet le double echappement le temps du test, puis restaure le fichier)
 *
 *   node tests/test_p0_espace_navigateur.mjs
 */
import fs from 'fs';
import os from 'os';
import path from 'path';
import { spawn, spawnSync } from 'child_process';

const DEPOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const PY = process.env.AFROBOOST_PY || '/tmp/venv-prod/bin/python';
const MONGOD = process.env.AFROBOOST_MONGOD || 'mongod';
const PORT_MONGO = 28033;
const PORT_API = 8109;
const BASE = `http://127.0.0.1:${PORT_API}`;
const DBDIR = path.join(os.tmpdir(), 'afroboost-p0-mongo');
const DBNAME = 'p0_espace';
const SERVEUR = path.join(DEPOT, 'api', 'server.py');

// Adresses REALISTES : un point dans le domaine, c'est tout ce qu'il fallait
// pour que la recherche echoue. On y ajoute un tiret et un `+`, echappes eux
// aussi par `re.escape`.
const ANNE = { email: 'anne.dupont@ex.test', code: 'P0-AVEC' };
const BRUNO = { email: 'bruno+perso@sous.ex-test.io', code: 'P0-SANS' };
const CARLA = { email: 'carla@ex.test', code: 'P0-PAYANT' };

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
  if (r.status !== 0) console.error(r.stderr || r.stdout);
  return (r.stdout || '') + (r.stderr || '');
}

// --- mode ROUGE : on remet le defaut, le temps de la mesure ----------------
const SAIN = fs.readFileSync(SERVEUR, 'utf8');
function casser() {
  const casse = SAIN
    .replace('{"$regex": f"^{member_email_escaped}$", "$options": "i"},',
             '{"$regex": f"^{re.escape(member_email_escaped)}$", "$options": "i"},')
    .replace('{"userEmail": {"$regex": f"^{user_email_escaped}$", "$options": "i"}},',
             '{"userEmail": {"$regex": f"^{re.escape(user_email_escaped)}$", "$options": "i"}},');
  if (casse === SAIN) throw new Error('impossible de remettre le defaut — le code a change');
  fs.writeFileSync(SERVEUR, casse);
}
function restaurer() { fs.writeFileSync(SERVEUR, SAIN); }

function semer() {
  const s = `
import pymongo, datetime
c = pymongo.MongoClient("mongodb://127.0.0.1:${PORT_MONGO}")
d = c["${DBNAME}"]
for n in ("offers","subscriptions","discount_codes","reservations","courses","memberships"):
    d[n].delete_many({})
auj = datetime.date.today()
jour_js = (auj.weekday() + 1) % 7
d.courses.insert_one({"id": "cours-p0", "name": "Silent P0", "weekday": jour_js,
                      "date": "", "time": "08:00", "locationName": "Neuchatel",
                      "visible": True, "archived": False, "coach_id": None})
d.offers.insert_one({"id": "offre-p0", "name": "PULSE x10 cours", "price": 250.0,
                     "position": 1, "first_purchase_eligible": True,
                     "creates_membership": True, "pack_sessions": 10,
                     "coach_id": None, "visible": True})

def forfait(email, code, gratuit=True):
    b = {"id": "sub-" + code, "code": code, "email": email, "coach_id": "",
         "whatsapp": "+41760000009", "name": "Test", "status": "active",
         "remaining_sessions": 0 if gratuit else 7, "total_sessions": 1 if gratuit else 10,
         "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    if gratuit:
        b.update({"payment_method": "free", "total_paid": 0, "origine_paiement": "offert"})
    else:
        b.update({"payment_method": "card", "total_paid": 250})
    return b

_q = datetime.datetime.now(datetime.timezone.utc).isoformat()
d.subscriptions.insert_many([forfait("${ANNE.email}", "${ANNE.code}"),
                             forfait("${BRUNO.email}", "${BRUNO.code}"),
                             forfait("${CARLA.email}", "${CARLA.code}", gratuit=False)])
# ANNE seule a une presence. BRUNO n'a rien reserve. CARLA est payante.
d.reservations.insert_one({"id": "res-anne", "userEmail": "${ANNE.email}",
    "userName": "Anne", "courseId": "cours-p0", "courseName": "Silent P0",
    "datetime": auj.isoformat() + "T08:00:00", "promoCode": "${ANNE.code}",
    "subscriptionId": "sub-${ANNE.code}", "validated": True, "validatedAt": _q,
    "createdAt": _q, "coach_id": None})
d.discount_codes.insert_many([
  {"code": "${ANNE.code}", "assignedEmail": "${ANNE.email}", "type": "100%",
   "value": 100, "maxUses": 1, "used": 1, "active": True, "coach_id": "",
   "payment_method": "free", "total_paid": 0},
  {"code": "${BRUNO.code}", "assignedEmail": "${BRUNO.email}", "type": "100%",
   "value": 100, "maxUses": 1, "used": 0, "active": True, "coach_id": "",
   "payment_method": "free", "total_paid": 0},
])
print("SEME")`;
  if (!py(s).includes('SEME')) throw new Error('semis impossible');
}

const espace = async (code) => {
  const r = await fetch(`${BASE}/api/subscriber/space/${encodeURIComponent(code)}`);
  return { statut: r.status, corps: await r.json().catch(() => ({})) };
};

async function principal() {
  const CASSE = process.env.AFROBOOST_P0_CASSE === '1';
  if (CASSE) { casser(); console.log('*** MODE ROUGE : le double echappement est remis ***'); }

  fs.rmSync(DBDIR, { recursive: true, force: true });
  fs.mkdirSync(DBDIR, { recursive: true });
  const mongo = spawn(MONGOD, ['--dbpath', DBDIR, '--port', String(PORT_MONGO),
    '--bind_ip', '127.0.0.1'], { stdio: 'ignore' });
  const api = spawn(PY, ['-m', 'uvicorn', 'api.server:app', '--host', '127.0.0.1',
    '--port', String(PORT_API), '--log-level', 'warning'], {
    cwd: DEPOT, stdio: ['ignore', 'ignore', 'pipe'],
    env: { ...process.env, MONGO_URL: `mongodb://127.0.0.1:${PORT_MONGO}`,
           DB_NAME: DBNAME, JWT_SECRET: 'test-secret-p0' },
  });
  let journal = '';
  api.stderr.on('data', (b) => { journal += b.toString(); });

  try {
    await dormir(1500);
    if (!await attendre(`${BASE}/healthz`)) {
      console.error('Backend non demarre.\n' + journal.slice(-2500));
      return 2;
    }
    semer();

    // ══ 1. CODE VALIDE, PARTICIPANT AVEC RESERVATION ═══════════════════════
    const a = await espace(ANNE.code);
    verifier('1a. la route repond 200', a.statut === 200, `statut=${a.statut}`);
    verifier('1b. LE DEFAUT : elle rend la reservation de ce participant',
      (a.corps.reservations || []).length === 1,
      `reservations=${JSON.stringify(a.corps.reservations || []).slice(0, 200)}`);
    verifier('1c. c est bien SA seance, avec son nom de cours',
      ((a.corps.reservations || [])[0] || {}).courseName === 'Silent P0',
      JSON.stringify((a.corps.reservations || [])[0] || {}).slice(0, 200));
    verifier('1d. la presence est marquee validee',
      ((a.corps.reservations || [])[0] || {}).validated === true);

    // ══ 2. ESSAI CONSOMME -> l etat bascule, et c est ce qui ouvre LOT A ════
    verifier('2a. l essai est declare EFFECTUE, pas « disponible »',
      (a.corps.trial || {}).state === 'done', JSON.stringify(a.corps.trial));
    const conv = await fetch(`${BASE}/api/subscriber/space/${ANNE.code}/conversion`)
      .then((r) => r.json()).catch(() => ({}));
    verifier('2b. ... donc l ecran de conversion s ouvre enfin',
      ((conv || {}).conversion || {}).state === 'open',
      JSON.stringify((conv || {}).conversion || {}).slice(0, 160));

    // ══ 3. PARTICIPANT SANS RESERVATION ════════════════════════════════════
    const b = await espace(BRUNO.code);
    verifier('3a. la route repond 200 pour qui n a rien reserve',
      b.statut === 200, `statut=${b.statut}`);
    verifier('3b. sa liste est vide — et c est la verite, pas une panne',
      (b.corps.reservations || []).length === 0,
      JSON.stringify(b.corps.reservations || []).slice(0, 160));
    verifier('3c. son essai reste DISPONIBLE',
      (b.corps.trial || {}).state === 'available', JSON.stringify(b.corps.trial));

    // ══ 4. CLOISONNEMENT : personne ne voit les seances d un autre ═════════
    verifier('4a. le participant SANS reservation ne voit pas celle d Anne',
      !JSON.stringify(b.corps.reservations || []).includes('Anne'),
      JSON.stringify(b.corps.reservations || []).slice(0, 160));
    // Le code d'acces et l'adresse vivent sous `subscriber` ; `subscription`
    // porte l'identifiant du forfait. On verifie les DEUX.
    verifier('4b. chaque code ne rend QUE son propre porteur',
      (a.corps.subscriber || {}).code === ANNE.code
      && (a.corps.subscriber || {}).email === ANNE.email
      && (b.corps.subscriber || {}).code === BRUNO.code
      && (b.corps.subscriber || {}).email === BRUNO.email
      && (a.corps.subscription || {}).id !== (b.corps.subscription || {}).id,
      `A=${JSON.stringify(a.corps.subscription || {}).slice(0, 200)} `
      + `B=${JSON.stringify(b.corps.subscription || {}).slice(0, 200)} `
      + `subA=${JSON.stringify(a.corps.subscriber || {}).slice(0, 160)}`);
    verifier('4c. aucune adresse d autrui ne fuit dans la reponse',
      !JSON.stringify(b.corps).includes(ANNE.email)
      && !JSON.stringify(a.corps).includes(BRUNO.email));

    // ══ 5. FORFAIT PAYANT : rien ne change pour lui ═════════════════════════
    const c = await espace(CARLA.code);
    verifier('5a. un forfait PAYANT n est pas requalifie en essai',
      (c.corps.trial || {}).is_trial === false, JSON.stringify(c.corps.trial));
    verifier('5b. son compteur de seances reste juste',
      (c.corps.subscription || {}).remaining_sessions === 7,
      JSON.stringify((c.corps.subscription || {}).remaining_sessions));

    // ══ 6. CODE INCONNU ════════════════════════════════════════════════════
    const z = await espace('CODE-QUI-N-EXISTE-PAS');
    verifier('6a. un code inconnu ne rend AUCUNE donnee',
      z.statut === 404 || z.corps.success === false
      || (z.corps.reservations || []).length === 0,
      `statut=${z.statut} ${JSON.stringify(z.corps).slice(0, 140)}`);
    verifier('6b. ... et ne fuit l adresse de personne',
      !JSON.stringify(z.corps).includes('@ex.test'),
      JSON.stringify(z.corps).slice(0, 140));

    // ══ 7. L INJECTION REGEX RESTE REFUSEE (ce que V310 protegeait) ════════
    const inj = await espace('.*');
    verifier('7a. un code en forme d expression reguliere ne rend rien',
      inj.statut === 404 || (inj.corps.reservations || []).length === 0,
      `statut=${inj.statut} ${JSON.stringify(inj.corps).slice(0, 140)}`);
  } finally {
    api.kill('SIGKILL');
    mongo.kill('SIGKILL');
    await dormir(400);
    fs.rmSync(DBDIR, { recursive: true, force: true });
    if (CASSE) restaurer();
  }

  const ok = resultats.filter((r) => r.ok).length;
  console.log('='.repeat(78));
  console.log(`${ok} / ${resultats.length} verifications`);
  console.log('Base jetable detruite. Aucune donnee de production. Aucun envoi.');
  return ok === resultats.length ? 0 : 1;
}

principal().then((c) => process.exit(c)).catch((e) => { restaurer(); console.error(e); process.exit(2); });
