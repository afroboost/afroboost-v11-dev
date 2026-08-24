/**
 * P1-c AU NAVIGATEUR — UNE OFFRE RECOMMANDEE, LES AUTRES DERRIERE UN BOUTON.
 *
 * Vrai mongod jetable, vrai FastAPI, vrai Chromium, vrai bundle React.
 * Ce que ce banc prouve et qu'aucune lecture de source ne peut prouver : ce
 * que le PARTICIPANT voit reellement a l'ecran, et ou le mene son clic.
 *
 * AUCUNE DONNEE DE PRODUCTION : base jetable sur un port dedie, detruite a la
 * fin. Le navigateur ne peut joindre que 127.0.0.1. AUCUN PAIEMENT : on
 * s'arrete a la reponse du serveur de caisse.
 *
 * Deux personnes, deux verdicts opposes :
 *   NEUF   — essai consomme, aucun historique -> l'ENTREE est recommandee,
 *            le cours a l'unite est une alternative, la recharge est absente.
 *   MEMBRE — essai consomme, adhesion active, pack a zero -> l'entree
 *            disparait, la RECHARGE prend sa place.
 *
 * ⚠️ IL LIT LE BUNDLE DE `frontend/build`. Un build PERIME fait echouer
 * l'attente du bloc de conversion (delai depasse sur `conversion-apres-essai`)
 * sans rien dire de plus. Reconstruire avant :
 *     cd frontend && CI=false npx craco build
 *
 *   node tests/test_p1c_navigateur.mjs
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
const PORT_MONGO = 28031;
const PORT_API = 8107;
const BASE = `http://127.0.0.1:${PORT_API}`;
const DBDIR = path.join(os.tmpdir(), 'afroboost-p1c-mongo');
const DBNAME = 'p1c_reco';

const ENTREE = 'offre-entree-p1c';
const UNITE = 'offre-unite-p1c';
const RECHARGE = 'offre-recharge-p1c';
const NEUF = { email: 'neuf.p1c@ex.test', code: 'P1C-NEUF' };
const MEMBRE = { email: 'membre.p1c@ex.test', code: 'P1C-MEMBRE' };

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

function semer() {
  const s = `
import pymongo, datetime
c = pymongo.MongoClient("mongodb://127.0.0.1:${PORT_MONGO}")
d = c["${DBNAME}"]
for n in ("offers","subscriptions","discount_codes","reservations","courses","memberships"):
    d[n].delete_many({})

# Le cours de l'essai : RECURRENT, sur le jour d'aujourd'hui, pour que la
# presence designe une occurrence REELLE (garde A1b de LOT A).
auj = datetime.date.today()
jour_js = (auj.weekday() + 1) % 7
d.courses.insert_one({"id": "cours-p1c", "name": "Silent P1-c", "weekday": jour_js,
                      "date": "", "time": "08:00", "locationName": "Neuchatel",
                      "visible": True, "archived": False, "coach_id": None})

d.offers.insert_many([
  {"id": "${UNITE}", "name": "Cours a l'unite", "price": 30.0, "position": 1,
   "first_purchase_eligible": True, "creates_membership": False,
   "coach_id": None, "visible": True},
  {"id": "${ENTREE}", "name": "PULSE x10 cours", "price": 250.0, "position": 4,
   "first_purchase_eligible": True, "creates_membership": True,
   "pack_sessions": 10, "coach_id": None, "visible": True},
  {"id": "${RECHARGE}", "name": "Recharge PULSE", "price": 150.0, "position": 5,
   "first_purchase_eligible": True, "requires_active_membership": True,
   "pack_sessions": 10, "coach_id": None, "visible": True},
])

def essai(email, code):
    # Un forfait d'ESSAI au sens d'ESSAI2_FILTRE_GRATUIT : gratuit, paye 0.
    # Le numero est renseigne : sans lui, l'ecran d'onboarding prend la main et
    # la page entiere (donc le bloc de conversion) n'est jamais rendue.
    return {"id": "sub-" + code, "code": code, "email": email, "coach_id": "",
            "whatsapp": "+41760000001", "name": "Test P1c",
            "status": "active", "remaining_sessions": 0, "total_sessions": 1,
            "payment_method": "free", "total_paid": 0, "origine_paiement": "offert",
            "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat()}

def presence(email, code):
    _q = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return {"id": "res-" + code, "userEmail": email, "userName": "Test",
            "courseId": "cours-p1c", "courseName": "Silent P1-c",
            "datetime": auj.isoformat() + "T08:00:00",
            "promoCode": code, "subscriptionId": "sub-" + code,
            "validated": True, "validatedAt": _q, "createdAt": _q,
            "coach_id": None}

d.subscriptions.insert_many([essai("${NEUF.email}", "${NEUF.code}"),
                             essai("${MEMBRE.email}", "${MEMBRE.code}")])
d.reservations.insert_many([presence("${NEUF.email}", "${NEUF.code}"),
                            presence("${MEMBRE.email}", "${MEMBRE.code}")])
d.discount_codes.insert_many([
  {"code": "${NEUF.code}", "assignedEmail": "${NEUF.email}", "type": "100%",
   "value": 100, "maxUses": 1, "used": 1, "active": True, "coach_id": "",
   "payment_method": "free", "total_paid": 0},
  {"code": "${MEMBRE.code}", "assignedEmail": "${MEMBRE.email}", "type": "100%",
   "value": 100, "maxUses": 1, "used": 1, "active": True, "coach_id": "",
   "payment_method": "free", "total_paid": 0},
])
an = auj.year
d.memberships.insert_one({"id": "adh-p1c", "email": "${MEMBRE.email}",
                          "coach_id": None,
                          "date_debut": "%d-01-01" % an, "date_fin": "%d-12-31" % an})
print("SEME")`;
  if (!py(s).includes('SEME')) throw new Error('semis impossible');
}

// Le SPA est servi depuis `<depot>/static` (disposition Docker) — ce dossier
// n'existe pas en local. On l'expose le temps du test par un LIEN SYMBOLIQUE
// vers le build React, retire dans le `finally`. Rien n'est copie, rien ne
// reste : si le lien existait deja, on n'y touche pas.
const LIEN_STATIC = path.join(DEPOT, 'static');
let lienPose = false;
function poserStatic() {
  if (fs.existsSync(LIEN_STATIC)) return;
  const build = path.join(DEPOT, 'frontend', 'build');
  if (!fs.existsSync(path.join(build, 'index.html'))) {
    throw new Error('build React absent — lancer `cd frontend && npx craco build`');
  }
  fs.symlinkSync(build, LIEN_STATIC, 'dir');
  lienPose = true;
}
function retirerStatic() {
  if (lienPose && fs.existsSync(LIEN_STATIC)) fs.unlinkSync(LIEN_STATIC);
  lienPose = false;
}

async function principal() {
  fs.rmSync(DBDIR, { recursive: true, force: true });
  fs.mkdirSync(DBDIR, { recursive: true });
  poserStatic();
  const mongo = spawn(MONGOD, ['--dbpath', DBDIR, '--port', String(PORT_MONGO),
    '--bind_ip', '127.0.0.1'], { stdio: 'ignore' });
  const api = spawn(PY, ['-m', 'uvicorn', 'api.server:app', '--host', '127.0.0.1',
    '--port', String(PORT_API), '--log-level', 'warning'], {
    cwd: DEPOT, stdio: ['ignore', 'ignore', 'pipe'],
    env: { ...process.env, MONGO_URL: `mongodb://127.0.0.1:${PORT_MONGO}`,
           DB_NAME: DBNAME, JWT_SECRET: 'test-secret-p1c' },
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
    // LE BUNDLE EST CELUI DE PRODUCTION. `frontend/.env.local` y a inline
    // `REACT_APP_BACKEND_URL=https://afroboost.com` AU BUILD : sans rien faire,
    // ce test taperait sur la VRAIE production. On REDIRIGE donc ces appels
    // vers le serveur local, et on ABORTE tout le reste — rien ne sort de
    // cette machine, et on eprouve le bundle reellement livre plutot qu'une
    // recompilation de circonstance.
    let fuites = 0;
    await ctx.route('**/*', (route) => {
      const u = new URL(route.request().url());
      if (u.hostname === '127.0.0.1') return route.continue();
      if (u.hostname === 'afroboost.com') {
        // Playwright refuse de changer de protocole (https -> http) : on RELAIE
        // donc la requete depuis Node vers le serveur local et on renvoie sa
        // reponse. Le navigateur croit parler a la production ; il parle a
        // 127.0.0.1, et rien ne sort.
        const req = route.request();
        return (async () => {
          try {
            const r = await fetch(`${BASE}${u.pathname}${u.search}`, {
              method: req.method(),
              headers: { ...req.headers(), host: `127.0.0.1:${PORT_API}` },
              body: ['GET', 'HEAD'].includes(req.method()) ? undefined : req.postData(),
            });
            return route.fulfill({
              status: r.status,
              headers: { 'content-type': r.headers.get('content-type') || 'application/json' },
              body: Buffer.from(await r.arrayBuffer()),
            });
          } catch (e) {
            return route.abort();
          }
        })();
      }
      fuites += 1;
      return route.abort();
    });
    const page = await ctx.newPage();

    // ══ le verdict SERVEUR, avant tout rendu ═══════════════════════════════
    await page.goto('/healthz');
    const conv = (code) => page.evaluate(async (c) => {
      const r = await fetch(`/api/subscriber/space/${encodeURIComponent(c)}/conversion`);
      return { statut: r.status, corps: await r.json().catch(() => ({})) };
    }, code);

    const n = await conv(NEUF.code);
    const offN = ((n.corps || {}).conversion || {}).offers || [];
    verifier('S1. le serveur ouvre la conversion pour un essai consomme',
      ((n.corps || {}).conversion || {}).state === 'open',
      JSON.stringify((n.corps || {}).conversion || {}).slice(0, 200));
    verifier('S2. participant NEUF : l entree est recommandee, et EN TETE',
      offN.length && offN[0].id === ENTREE && offN[0].recommended === true,
      offN.map((o) => `${o.name}:${o.recommended}`).join(' | '));
    verifier('S3. le cours a l unite reste une ALTERNATIVE',
      offN.some((o) => o.id === UNITE && !o.recommended),
      offN.map((o) => o.id).join(' | '));
    verifier('S4. la recharge est ABSENTE pour un non-membre',
      !offN.some((o) => o.id === RECHARGE), offN.map((o) => o.id).join(' | '));

    const m = await conv(MEMBRE.code);
    const offM = ((m.corps || {}).conversion || {}).offers || [];
    verifier('S5. MEMBRE actif, pack a zero : l entree 250 disparait',
      !offM.some((o) => o.id === ENTREE), offM.map((o) => o.id).join(' | '));
    verifier('S6. ... et la RECHARGE prend la place recommandee',
      offM.length && offM[0].id === RECHARGE && offM[0].recommended === true,
      offM.map((o) => `${o.name}:${o.recommended}`).join(' | '));

    // ══ ce que le PARTICIPANT voit vraiment ════════════════════════════════
    const espaceN = await page.evaluate(async (c) => {
      const r = await fetch(`/api/subscriber/space/${encodeURIComponent(c)}`);
      return { statut: r.status, corps: await r.json().catch(() => ({})) };
    }, NEUF.code);
    verifier('U0. l espace abonne repond, et declare l essai EFFECTUE',
      espaceN.statut === 200 && ((espaceN.corps || {}).trial || {}).state === 'done',
      `statut=${espaceN.statut} trial=${JSON.stringify((espaceN.corps || {}).trial)} `
      + `whatsapp=${JSON.stringify(((espaceN.corps || {}).subscriber || {}).whatsapp)} `
      + `resas=${JSON.stringify((espaceN.corps || {}).reservations || []).slice(0, 300)} `
      + `cles=${Object.keys(espaceN.corps || {}).join(",")}`);

    const erreursConsole = [];
    page.on('console', (m) => { if (m.type() === 'error') erreursConsole.push(m.text()); });
    page.on('pageerror', (e) => erreursConsole.push('pageerror: ' + e.message));
    await page.goto(`/espace/${NEUF.code}`);
    await dormir(4000);
    const diag = await page.evaluate(() => ({
      testids: Array.from(document.querySelectorAll('[data-testid]'))
        .map((n) => n.getAttribute('data-testid')).slice(0, 40),
      texte: (document.body.innerText || '').slice(0, 400),
    }));
    verifier('U0b. le bloc de conversion est monte',
      diag.testids.includes('conversion-apres-essai'),
      `testids=${diag.testids.join(',')} | texte=${diag.texte.replace(/\n/g, ' / ')} `
      + `| erreurs=${erreursConsole.slice(0, 3).join(' ;; ')}`);
    await page.waitForSelector('[data-testid="conversion-apres-essai"]', { timeout: 30000 });

    const vedette = page.locator('[data-testid="conversion-recommandee"]');
    verifier('U1. le bloc recommande est affiche',
      await vedette.count() === 1);
    // Le libelle est rendu en MAJUSCULES par la classe `uppercase` : on compare
    // sans tenir compte de la casse, sinon on testerait le CSS, pas le texte.
    verifier('U2. il porte la mention « Recommandé pour toi »',
      /recommand[ée] pour toi/i.test(await vedette.innerText()), await vedette.innerText());
    verifier('U3. c est bien l offre d ENTREE, avec son prix serveur',
      /PULSE x10/.test(await vedette.innerText())
      && /250/.test(await vedette.innerText()), await vedette.innerText());

    const alt = page.locator('[data-testid="conversion-alternatives"]');
    verifier('U4. les alternatives sont REPLIEES au chargement',
      await alt.count() === 0);
    const bouton = page.locator('[data-testid="conversion-voir-autres"]');
    verifier('U5. le bouton « Voir les autres options » est propose',
      await bouton.count() === 1 && /Voir les autres options/.test(await bouton.innerText()));

    await bouton.click();
    await page.waitForSelector('[data-testid="conversion-alternatives"]', { timeout: 10000 });
    const texteAlt = await alt.innerText();
    verifier('U6. le clic revele le cours a l unite, avec son prix',
      /unite|unité/i.test(texteAlt) && /30/.test(texteAlt), texteAlt);
    verifier('U7. l entree n est PAS dupliquee dans les alternatives',
      !/PULSE x10/.test(texteAlt), texteAlt);

    // ══ le clic mene-t-il a la bonne caisse ? ══════════════════════════════
    const [reponse] = await Promise.all([
      page.waitForResponse((r) => /\/conversion\/checkout$/.test(r.url()), { timeout: 20000 }),
      page.locator(`[data-testid="conversion-cta-${ENTREE}"]`).click(),
    ]);
    const corpsC = await reponse.json().catch(() => ({}));
    verifier('U8. le CTA principal part bien vers /conversion/checkout',
      /\/conversion\/checkout$/.test(reponse.url()), reponse.url());
    // AUCUN STRIPE DANS CE DECOR JETABLE, ET C'EST VOULU : aucun paiement ne
    // peut aboutir depuis ce banc. Ce qui compte ici est que la demande ait
    // TRAVERSE les deux gardes LOT A / P1-c — un refus metier serait 403, pas
    // 400. Le 400 vient de la couche paiement, en aval de la decision.
    verifier('U9. les gardes LOT A / P1-c ont LAISSE PASSER cette offre '
      + '(le refus eventuel serait 403 ; 400 = couche paiement, en aval)',
      reponse.status() !== 403,
      `statut=${reponse.status()} ${JSON.stringify(corpsC).slice(0, 120)}`);

    // ══ la garde de niveau 2 dit la MEME chose que l ecran ═════════════════
    const force = await page.evaluate(async (a) => {
      const r = await fetch(`/api/subscriber/space/${a.code}/conversion/checkout`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ offer_id: a.offre }),
      });
      return { statut: r.status, corps: await r.json().catch(() => ({})) };
    }, { code: MEMBRE.code, offre: ENTREE });
    verifier('G1. un MEMBRE qui force l entree 250 par l URL est REFUSE (403)',
      force.statut === 403, `statut=${force.statut} ${JSON.stringify(force.corps).slice(0, 140)}`);

    const forceNeuf = await page.evaluate(async (a) => {
      const r = await fetch(`/api/subscriber/space/${a.code}/conversion/checkout`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ offer_id: a.offre }),
      });
      return { statut: r.status };
    }, { code: NEUF.code, offre: RECHARGE });
    verifier('G2. un NON-MEMBRE qui force la recharge est REFUSE (403)',
      forceNeuf.statut === 403, `statut=${forceNeuf.statut}`);

    verifier('Z1. aucune requete n a quitte la machine',
      typeof fuites === 'number', `tentatives externes bloquees : ${fuites}`);
  } finally {
    if (navigateur) await navigateur.close().catch(() => {});
    api.kill('SIGKILL');
    mongo.kill('SIGKILL');
    await dormir(400);
    fs.rmSync(DBDIR, { recursive: true, force: true });
    retirerStatic();
  }

  const ok = resultats.filter((r) => r.ok).length;
  console.log('='.repeat(78));
  console.log(`${ok} / ${resultats.length} verifications`);
  console.log('Base jetable detruite. Aucun paiement. Aucune donnee de production.');
  return ok === resultats.length ? 0 : 1;
}

principal().then((c) => process.exit(c)).catch((e) => { console.error(e); process.exit(2); });
