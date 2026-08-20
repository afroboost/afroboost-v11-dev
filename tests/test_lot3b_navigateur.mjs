/**
 * LOT 3b — L'AVANTAGE TARIFAIRE MEMBRE : LES PREUVES EN NAVIGATEUR REEL.
 * =====================================================================
 *
 * POURQUOI CE TEST EXISTE
 * -----------------------
 * Lire le source ne prouve rien d'un ecran. Un `data-testid` present dans un
 * fichier peut etre rendu derriere une condition fausse, masque par un parent,
 * ou jamais atteint parce qu'aucun clic n'y mene. Ici on ouvre un VRAI
 * Chromium, on charge le VRAI bundle construit par craco, et on regarde ce qui
 * est reellement a l'ecran — cote coach ET cote client.
 *
 * CE QUI EST SIMULE, ET CE QUI NE L'EST PAS
 * -----------------------------------------
 * SIMULE : le backend. Il ne peut pas tourner sur cette machine (Python 3.9,
 * FastAPI absent, MONGO_URL obligatoire). Les reponses `/api/*` viennent donc
 * d'un bouchon Node local, ecrit plus bas dans CE fichier. Ce test ne dit rien
 * de la REGLE serveur (qui est membre, quel pourcentage l'emporte) : cette
 * partie est couverte par les tests Python. Il dit ce que l'interface FAIT
 * d'une reponse donnee — et c'est precisement ce qu'aucun test Python ne peut
 * dire.
 * PAS SIMULE : le code frontend. Aucun composant n'est remplace, aucun module
 * n'est bouchonne. C'est le bundle de production qui s'execute.
 *
 * DEUX BUNDLES, ET IL FAUT DIRE POURQUOI
 * --------------------------------------
 *   1. `build/`        — le bundle REEL, tel qu'il partirait en production.
 *                        Il sert aux preuves COACH (W*) et a la mesure
 *                        d'atteignabilite (R*).
 *   2. `build-patche/` — le MEME source, avec DEUX lignes remises dans leur
 *                        position d'avant la V225/V226 (voir `PATCHES`). Il ne
 *                        sert QU'AUX scenarios d'affichage client (C*).
 *
 * La raison est mesuree, pas supposee, et le volet R la met noir sur blanc :
 * sur le bundle REEL, l'ecran qui porte la ligne « Avantage membre » n'est
 * atteignable par AUCUN clic de visiteur. Le bloc LOT 3b vit dans le
 * recapitulatif du formulaire de reservation, lequel exige a la fois une offre
 * selectionnee, un cours et une date ; or (a) la grille de dates n'est plus
 * rendue (`const showSessions = false`, V225) et (b) toute offre payante part
 * en paiement direct avant meme d'ouvrir le formulaire (`v225IsDirectCheckout`,
 * V225/V226). Le volet C prouve donc que l'affichage est JUSTE — a condition
 * qu'on puisse un jour l'atteindre. Les deux moities comptent : un affichage
 * juste mais inatteignable n'est pas une fonctionnalite livree.
 *
 * CE QUE CE TEST NE TOUCHE JAMAIS
 * -------------------------------
 * Aucune production, aucune base, aucun paiement. Le bouchon n'autorise QU'UNE
 * ecriture : `POST /api/tarif/estimation`, qui est une route de LECTURE (elle
 * calcule un prix et n'enregistre rien) mais que le contrat HTTP du depot passe
 * en POST. Tout autre verbe non-GET est refuse en 405 ET consigne, de sorte que
 * le test puisse AFFIRMER « rien n'a ete ecrit » sur une mesure. Le navigateur
 * coupe en outre toute requete sortant de 127.0.0.1.
 *
 * LANCEMENT
 *   node tests/test_lot3b_navigateur.mjs                (construit si besoin)
 *   node tests/test_lot3b_navigateur.mjs --sans-build   (reutilise tel quel)
 */
import fs from 'fs';
import os from 'os';
import http from 'http';
import path from 'path';
import crypto from 'crypto';
import { execFileSync } from 'child_process';
import { fileURLToPath } from 'url';
import { createRequire } from 'module';

const require_ = createRequire(import.meta.url);
// Playwright n'est PAS une dependance du projet : on l'emprunte par chemin
// absolu, exactement comme les tests LOT 2 / LOT 2.1 / LOT 3a.
const CHEMIN_PLAYWRIGHT = '/Users/afroboost/.claude/skills/gstack/node_modules/playwright-core';
const { chromium } = require_(CHEMIN_PLAYWRIGHT);

const RACINE = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const TRAVAIL = path.join(os.tmpdir(), 'afroboost-lot3b-navigateur');
const BUILD = path.join(TRAVAIL, 'build');
const BUILD_PATCHE = path.join(TRAVAIL, 'build-patche');
const FRONT_PATCHE = path.join(TRAVAIL, 'frontend-patche');
const CAPTURES = path.join(TRAVAIL, 'captures');
const EMPREINTE = path.join(TRAVAIL, 'empreinte.txt');
const SANS_BUILD = process.argv.includes('--sans-build');

const EMAIL_COACH = 'afroboost.bassi@gmail.com';   // super-admin : ne quitte jamais 127.0.0.1

// ---------------------------------------------------------------------------
// 0. LES BUNDLES
// ---------------------------------------------------------------------------

/** Les fichiers dont depend ce que l'on mesure. Leur empreinte decide de la
 *  reconstruction : inutile de rebatir six minutes pour rien, hors de question
 *  de tester un bundle perime. */
const SOURCES = [
  'frontend/src/App.js',
  'frontend/src/components/CoachDashboard.js',
  'frontend/src/components/dashboard/OfferWizard.js',
  'frontend/src/components/dashboard/OffersManager.js',
  'frontend/src/components/SessionsModal.js',
];

/**
 * LES DEUX LIGNES REMISES EN POSITION D'ORIGINE, ET RIEN D'AUTRE.
 *
 * Elles ne sont appliquees que dans une COPIE hors depot (`frontend-patche/`),
 * jamais dans l'arbre de travail. Chaque motif doit apparaitre EXACTEMENT une
 * fois : s'il disparait (refonte du fichier), la construction s'arrete au lieu
 * de produire en silence un bundle non patche sur lequel les scenarios C
 * passeraient pour de mauvaises raisons.
 *
 *  1. `showSessions` — V225 a fige la grille d'horaires a `false`. Sans elle,
 *     aucun clic ne peut poser un cours ni une date.
 *  2. `v225IsDirectCheckout` — V225/V226 envoient toute offre payante droit
 *     chez Stripe, sans jamais ouvrir le formulaire de reservation.
 */
const PATCHES = [
  {
    quoi: 'grille des horaires rouverte (V225 l\'avait figee a false)',
    de: '          const showSessions = false;',
    vers: '          const showSessions = true;  /* PATCH TEST LOT 3b */',
  },
  {
    quoi: 'parcours FORMULAIRE retabli (V225/V226 envoient tout en paiement direct)',
    de: 'const v225IsDirectCheckout = (offer) => {\n  if (!offer) return false;\n  return v223UnitPrice(offer) > 0;\n};',
    vers: 'const v225IsDirectCheckout = (offer) => {\n  if (!offer) return false;\n  return false;  /* PATCH TEST LOT 3b */\n};',
  },
];

function empreinteSources() {
  const h = crypto.createHash('sha256');
  for (const s of SOURCES) h.update(fs.readFileSync(path.join(RACINE, s)));
  h.update(JSON.stringify(PATCHES));
  return h.digest('hex');
}

function copier(src, dst) {
  fs.mkdirSync(dst, { recursive: true });
  for (const e of fs.readdirSync(src, { withFileTypes: true })) {
    const a = path.join(src, e.name);
    const b = path.join(dst, e.name);
    if (e.isDirectory()) copier(a, b);
    else if (e.isSymbolicLink()) { /* ignore */ }
    else fs.copyFileSync(a, b);
  }
}

/**
 * `BUILD_PATH` plutot que le `frontend/build` du depot : la sortie va dans
 * /tmp, et l'arbre de travail n'est JAMAIS touche — pas meme un artefact de
 * construction a restaurer ensuite.
 *
 * `REACT_APP_BACKEND_URL` VIDE, et c'est capital : `frontend/.env.local`
 * contient `https://afroboost.com`. Sans cette neutralisation, le bundle de
 * test enverrait ses appels A LA PRODUCTION. Une variable posee dans
 * l'environnement l'emporte sur les fichiers `.env` (dotenv n'ecrase jamais une
 * cle deja presente) : le fichier du depot n'est ni lu de travers ni modifie.
 * Le navigateur coupe en outre tout ce qui sort de 127.0.0.1 — ceinture ET
 * bretelles, et le scenario Z3 verifie qu'aucune bretelle n'a servi.
 */
function construire(cwd, sortie) {
  execFileSync('npx', ['craco', 'build'], {
    cwd,
    env: { ...process.env, CI: 'false', REACT_APP_BACKEND_URL: '', BUILD_PATH: sortie },
    stdio: 'inherit',
  });
}

function preparerFrontPatche() {
  fs.rmSync(FRONT_PATCHE, { recursive: true, force: true });
  fs.mkdirSync(FRONT_PATCHE, { recursive: true });
  for (const f of ['craco.config.js', 'jsconfig.json', 'package.json', 'postcss.config.js',
    'tailwind.config.js', 'components.json', 'package-lock.json']) {
    const src = path.join(RACINE, 'frontend', f);
    if (fs.existsSync(src)) fs.copyFileSync(src, path.join(FRONT_PATCHE, f));
  }
  for (const d of ['src', 'public', 'plugins']) {
    const src = path.join(RACINE, 'frontend', d);
    if (fs.existsSync(src)) copier(src, path.join(FRONT_PATCHE, d));
  }
  // Lien symbolique : 885 Mo de node_modules ne sont pas copies.
  fs.symlinkSync(path.join(RACINE, 'frontend', 'node_modules'),
    path.join(FRONT_PATCHE, 'node_modules'));

  const cible = path.join(FRONT_PATCHE, 'src', 'App.js');
  let s = fs.readFileSync(cible, 'utf8');
  for (const p of PATCHES) {
    const n = s.split(p.de).length - 1;
    if (n !== 1) {
      throw new Error(`PATCH INTROUVABLE (${n} occurrence(s)) : ${p.quoi}. `
        + 'Le code a change : ce test doit etre relu avant d\'etre cru.');
    }
    s = s.split(p.de).join(p.vers);
  }
  fs.writeFileSync(cible, s);
}

function preparerBundles() {
  const attendue = empreinteSources();
  const connue = fs.existsSync(EMPREINTE) ? fs.readFileSync(EMPREINTE, 'utf8').trim() : '';
  const dejaLa = fs.existsSync(path.join(BUILD, 'index.html'))
    && fs.existsSync(path.join(BUILD_PATCHE, 'index.html'));
  if (dejaLa && connue === attendue) {
    console.log('· deux bundles deja a jour dans ' + TRAVAIL);
    return;
  }
  if (SANS_BUILD) {
    throw new Error('bundles absents ou perimes, et --sans-build demande. Relancer sans l\'option.');
  }
  fs.mkdirSync(TRAVAIL, { recursive: true });
  console.log('· construction du bundle REEL (craco), quelques minutes…');
  fs.rmSync(BUILD, { recursive: true, force: true });
  construire(path.join(RACINE, 'frontend'), BUILD);
  console.log('· copie patchee du frontend (hors depot) puis construction…');
  preparerFrontPatche();
  fs.rmSync(BUILD_PATCHE, { recursive: true, force: true });
  construire(FRONT_PATCHE, BUILD_PATCHE);
  fs.writeFileSync(EMPREINTE, attendue);
  console.log('· bundles prets. Le depot n\'a pas ete touche.');
}

// ---------------------------------------------------------------------------
// 1. LE BOUCHON — copie locale, volontairement NON partagee.
// ---------------------------------------------------------------------------
//
// `tests/serveur_bouchon_lot2.mjs` refuse TOUT verbe non-GET (405). C'est une
// bonne regle et on ne la relache pas la-bas : ce fichier en garde une copie
// avec UNE seule ouverture supplementaire, `POST /api/tarif/estimation`.
//
// Pourquoi cette exception est acceptable : la route est une route de LECTURE.
// Elle calcule « combien couterait cet achat » et n'ecrit rien (api/server.py,
// `lot3b_estimation_tarifaire`). Elle n'est en POST que parce qu'elle recoit un
// corps (offre, cours, liste de dates, code promo) trop long pour une URL. Ici
// elle ne fait meme pas cela : elle renvoie la fixture posee par le scenario en
// cours, et journalise le corps recu — c'est ce qui permet de COMPTER les
// appels et de denoncer une boucle.
//
// Tout le reste (POST/PUT/DELETE) reste refuse en 405 et consigne.

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.txt': 'text/plain; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
  '.webmanifest': 'application/manifest+json',
  '.md': 'text/markdown; charset=utf-8',
};

function etatInitial() {
  return {
    offers: [],
    courses: [],
    /** La reponse que `/api/tarif/estimation` renverra. `null` = 404, comme le
     *  vrai serveur pour une offre introuvable. */
    estimation: null,
    /** Les corps recus par `/api/tarif/estimation`, dans l'ordre. */
    demandes: [],
  };
}

function json(res, statut, corps) {
  const buf = Buffer.from(JSON.stringify(corps), 'utf8');
  res.writeHead(statut, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': buf.length,
    'Cache-Control': 'no-store',
  });
  res.end(buf);
}

/** Reponses `/api/*`. Cle = chemin EXACT sans `/api`. */
function routes(etat) {
  return {
    '/offers': () => [200, etat.offers],
    '/courses': () => [200, etat.courses],
    // Liste NUE attendue par le dashboard (`setCourses(r.data)` puis `.reduce`).
    '/coach/courses': () => [200, etat.courses],
    '/concept': () => [200, {}],
    '/feature-flags': () => [200, { MEMBER_PRICING_ENABLED: true }],
    '/pawapay/available': () => [200, { available: false, enabled: false, countries: [] }],
    '/contacts/all': () => [200, {
      success: true, contacts: [],
      compteurs: { tous: 0, abonnes: 0, anciens: 0, prospects: 0, non_classes: 0 },
    }],
    '/contact-categories': () => [200, { success: true, categories: [] }],
    '/google-contacts/status': () => [200, { connected: false, configured: false, last_sync: null }],
    '/coach/profile': () => [200, { success: true, profile: {} }],
    '/audio-tracks': () => [200, []],
    '/social-proofs': () => [200, []],
    '/private/nonlus': () => [200, { success: true, count: 0, conversations: [] }],
    '/whatsapp-config': () => [200, { success: true, configured: false }],
    '/auth/whoami': () => [200, { success: true, email: EMAIL_COACH, role: 'super_admin' }],
    '/partners/active': () => [200, []],
    '/users': () => [200, []],
    '/discount-codes': () => [200, []],
    '/payment-links': () => [200, []],
    '/publications': () => [200, []],
    '/platform-settings': () => [200, { success: true, settings: {} }],
    '/page-likes': () => [200, { likes: 0, liked: false }],
    '/comments': () => [200, []],
    // Enveloppe {data, pagination} : une liste nue ferait PLANTER le dashboard.
    '/reservations': () => [200, {
      success: true, data: [], pagination: { page: 1, limit: 20, total: 0, pages: 0 },
    }],
    '/chat/sessions': () => [200, { success: true, sessions: [] }],
    '/chat/groups': () => [200, { success: true, groups: [] }],
    '/trash': () => [200, { success: true, items: [] }],
    '/notifications/unread': () => [200, { success: true, count: 0 }],
    '/coach/notifications': () => [200, { success: true, notifications: [] }],
    '/dashboard/all-transactions': () => [200, { success: true, transactions: [] }],
    '/credit-transactions': () => [200, { success: true, transactions: [] }],
    // Sans cette reponse, App.js purge la session coach et le dashboard
    // disparait avant d'avoir ete teste.
    '/auth/role': () => [200, {
      role: 'super_admin', is_coach: true, is_super_admin: true, email: EMAIL_COACH,
    }],
  };
}

const REPLI = {
  success: true, data: [], items: [], results: [], count: 0, total: 0,
  offers: [], courses: [], contacts: [], sessions: [], messages: [],
  notifications: [], transactions: [], groups: [], categories: [], faqs: [],
  tracks: [], comments: [], publications: [],
};

function demarrerBouchon({ racine, etat }) {
  const journal = [];

  const serveur = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://127.0.0.1');
    const chemin = decodeURIComponent(url.pathname);

    if (chemin.startsWith('/api/')) {
      // SEULE ouverture : l'estimation tarifaire (route de LECTURE en POST).
      if (req.method === 'POST' && chemin === '/api/tarif/estimation') {
        let brut = '';
        req.on('data', (c) => { brut += c; });
        req.on('end', () => {
          let corps = {};
          try { corps = JSON.parse(brut || '{}'); } catch (e) { corps = {}; }
          etat.demandes.push({ corps, t: Date.now() });
          journal.push({ methode: 'POST', chemin, statut: etat.estimation ? 200 : 404 });
          if (!etat.estimation) return json(res, 404, { detail: 'Offre introuvable' });
          return json(res, 200, etat.estimation);
        });
        return undefined;
      }
      // GARDE-FOU : aucune autre ecriture, jamais.
      if (req.method !== 'GET') {
        journal.push({ methode: req.method, chemin, statut: 405 });
        return json(res, 405, { detail: 'Ecriture interdite dans le bouchon' });
      }
      const cle = chemin.replace(/^\/api/, '');
      const fabrique = routes(etat)[cle];
      const [statut, corps] = fabrique ? fabrique() : [200, REPLI];
      journal.push({ methode: 'GET', chemin, statut });
      return json(res, statut, corps);
    }

    let fichier = path.join(racine, chemin);
    if (!fichier.startsWith(racine)) fichier = path.join(racine, 'index.html');
    if (!fs.existsSync(fichier) || fs.statSync(fichier).isDirectory()) {
      fichier = path.join(racine, 'index.html');
    }
    const buf = fs.readFileSync(fichier);
    res.writeHead(200, {
      'Content-Type': TYPES[path.extname(fichier).toLowerCase()] || 'application/octet-stream',
      'Content-Length': buf.length,
      'Cache-Control': 'no-store',
    });
    res.end(buf);
  });

  return new Promise((resoudre) => {
    serveur.listen(0, '127.0.0.1', () => {
      const port = serveur.address().port;
      resoudre({
        port,
        base: `http://127.0.0.1:${port}`,
        journal,
        arreter: () => new Promise((r) => serveur.close(r)),
      });
    });
  });
}

// ---------------------------------------------------------------------------
// 2. LES FIXTURES
// ---------------------------------------------------------------------------

const COURS = {
  id: 'cours-lot3b', name: 'Cardio Afrobeat', weekday: 1, time: '18:30',
  locationName: 'Lausanne', maxCapacity: 20, reservations: 0,
  active: true, is_active: true, visible: true, price: 30,
  coach_id: EMAIL_COACH, audio_tracks: [], playlist: [],
};

const OFFRE_30 = {
  id: 'offre-unite', name: "Cours à l'unité", title: "Cours à l'unité",
  description: 'Une séance', price: 30, currency: 'CHF', sessions: 1,
  active: true, is_active: true, visible: true,
  member_discount_pct: 50, linked_course_ids: [COURS.id],
  coach_id: EMAIL_COACH, images: [],
};

/** PULSE 250 : l'offre d'entree. Elle OUVRE l'adhesion, donc elle ne doit
 *  jamais etre vendue au tarif membre (on n'achete pas son adhesion a moitie
 *  prix). Le serveur le sait ; l'ecran doit le refleter. */
const OFFRE_PULSE = {
  id: 'offre-pulse', name: 'PULSE x10 cours', title: 'PULSE x10 cours',
  description: 'Dix séances', price: 250, currency: 'CHF', sessions: 10,
  active: true, is_active: true, visible: true,
  creates_membership: true, linked_course_ids: [COURS.id],
  coach_id: EMAIL_COACH, images: [],
};

/** Le squelette commun de toutes les reponses de `/api/tarif/estimation`,
 *  copie sur la forme REELLE produite par api/server.py. */
const estimation = (extra) => ({
  offer_id: OFFRE_30.id, quantity: 1, devise: 'CHF',
  prix_public_unitaire: 30, prix_public: 30, votre_tarif: 30,
  membre: false, avantage_pct: null, raison: 'public',
  ...extra,
});

// ---------------------------------------------------------------------------
// 3. RESULTATS
// ---------------------------------------------------------------------------

const resultats = [];
const bloqueesGlobal = [];
const erreursPage = [];

function verifier(nom, condition, detail = '') {
  const ok = !!condition;
  resultats.push({ nom, ok, detail: ok ? '' : String(detail || '') });
  console.log(`${ok ? '  OK   ' : ' ECHEC '} ${nom}${ok || !detail ? '' : ` — ${detail}`}`);
}
function nonCouvert(nom, pourquoi) {
  resultats.push({ nom, ok: null, detail: pourquoi });
  console.log(`  N.C.  ${nom}`);
}
function noter(nom, valeur) {
  resultats.push({ nom, ok: null, detail: String(valeur) });
  console.log(`  info  ${nom} — ${valeur}`);
}

// ---------------------------------------------------------------------------
// 4. PILOTAGE DU NAVIGATEUR
// ---------------------------------------------------------------------------

/** JWT NON SIGNE mais de forme valide, `exp` lointain. Le frontend ne verifie
 *  que `exp` (utils/jwt.js : la signature ne peut pas etre verifiee dans un
 *  navigateur). Aucune garde serveur n'est franchie : le serveur est ici un
 *  bouchon local qui ne protege rien. */
function jetonFactice(email) {
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
  const exp = Math.floor(Date.now() / 1000) + 3600 * 24 * 30;
  return `${b64({ alg: 'HS256', typ: 'JWT' })}.${b64({ email, sub: email, exp })}.signature-factice`;
}

/**
 * @param connecte false = simple VISITEUR. Indispensable pour la vitrine :
 *   avec une session coach, App.js rend le dashboard a la place de la page
 *   publique et l'offre n'est jamais a l'ecran.
 */
async function nouveauContexte(navigateur, base, largeur, hauteur, connecte, etiquette) {
  const contexte = await navigateur.newContext({
    viewport: { width: largeur, height: hauteur }, baseURL: base,
  });
  const hote = new URL(base).host;
  // AUCUNE sortie hors de 127.0.0.1 : ni PostHog, ni Cloudinary, ni la prod.
  await contexte.route('**/*', (route) => {
    const u = new URL(route.request().url());
    if (u.host !== hote) { bloqueesGlobal.push(u.href); return route.abort(); }
    // Le Service Worker servirait un bundle cache : on le coupe net.
    if (u.pathname === '/sw.js') return route.abort();
    return route.continue();
  });
  if (connecte) {
    await contexte.addInitScript(([email, jeton]) => {
      localStorage.setItem('afroboost_coach_mode', 'true');
      localStorage.setItem('afroboost_coach_user', JSON.stringify({ email, name: 'Coach Test' }));
      localStorage.setItem('afroboost_jwt', jeton);
    }, [EMAIL_COACH, jetonFactice(EMAIL_COACH)]);
  }
  const page = await contexte.newPage();
  page.on('pageerror', (e) => erreursPage.push(`${etiquette}: ${e.message}`));
  return { contexte, page };
}

async function capture(page, nom) {
  fs.mkdirSync(CAPTURES, { recursive: true });
  await page.screenshot({ path: path.join(CAPTURES, `${nom}.png`), fullPage: false });
}

/** Ouvre le formulaire d'une NOUVELLE offre, etape 1 « Bases ». */
async function ouvrirNouvelleOffre(page, base) {
  await page.goto(`${base}/#partner-dashboard`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('[data-testid="coach-nav-toggle"]', { timeout: 40000 });
  await page.click('[data-testid="coach-nav-toggle"]');
  await page.click('[data-testid="coach-tab-offers"]');
  await page.click('text=Offres & Cours');
  await page.waitForSelector('text=+ NOUVELLE OFFRE', { timeout: 30000 });
  await page.click('text=+ NOUVELLE OFFRE');
  // TEMOIN DE MONTAGE : le champ « Nom », surtout pas le prix — un prix
  // affiche « 0 » est une valeur NON VIDE et sortirait la boucle sur un
  // formulaire encore vierge (defaut deja rencontre au LOT 2.1).
  await page.waitForSelector('[placeholder="Ex: Cours à l\'unité"]', { timeout: 20000 });
  return page.getByPlaceholder('30').first();
}

/** Le montant lu dans la ligne « Total » du recapitulatif. */
async function totalAffiche(page) {
  const t = await page.locator('[data-testid="total-price"]').innerText();
  const m = t.match(/CHF\s*([\d]+[.,]?[\d]*)/);
  return m ? m[1].replace(',', '.') : null;
}

/**
 * Mene un VISITEUR jusqu'au recapitulatif : clic sur l'offre (le formulaire
 * s'ouvre), puis clic sur une date (le cours et l'occurrence sont poses, et
 * c'est CE geste qui declenche l'estimation).
 * @returns le nombre d'appels a /api/tarif/estimation provoques par ce geste.
 */
async function menerAuRecapitulatif(page, base, etat, idOffre, indexDate = 0) {
  await page.goto(`${base}/`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector(`[data-testid="offer-reserve-${idOffre}"]`, { timeout: 40000 });
  await page.click(`[data-testid="offer-reserve-${idOffre}"]`);
  await page.waitForSelector('[data-testid="user-info-section"]', { timeout: 20000 });
  const avant = etat.demandes.length;
  await page.click(`[data-testid="date-btn-${COURS.id}-${indexDate}"]`);
  await page.waitForSelector('[data-testid="total-price"]', { timeout: 20000 });
  // On laisse VOLONTAIREMENT du temps : c'est dans cette fenetre qu'une boucle
  // d'appels se manifesterait (mesure : ~2,5 appels/s lors d'un essai rate).
  await page.waitForTimeout(4000);
  return etat.demandes.length - avant;
}

/** La ligne « Prix public » barree, qui n'a pas de data-testid : on la lit par
 *  sa position (frere precedent de la ligne d'avantage) et on VERIFIE que le
 *  navigateur la barre reellement (style calcule, pas attribut). */
async function lignePrixPublic(page) {
  return page.evaluate(() => {
    const l = document.querySelector('[data-testid="member-advantage-line"]');
    if (!l) return null;
    const p = l.previousElementSibling;
    if (!p) return null;
    const spans = p.querySelectorAll('span');
    const dernier = spans[spans.length - 1];
    return {
      texte: (p.innerText || '').replace(/\s+/g, ' ').trim(),
      decoration: dernier ? getComputedStyle(dernier).textDecorationLine : '',
    };
  });
}

// ---------------------------------------------------------------------------
// 5. LES SCENARIOS
// ---------------------------------------------------------------------------

async function principal() {
  preparerBundles();

  const etat = etatInitial();
  etat.offers = [OFFRE_30, OFFRE_PULSE];
  etat.courses = [COURS];

  const navigateur = await chromium.launch({ headless: true });
  const reel = await demarrerBouchon({ racine: BUILD, etat });
  const patche = await demarrerBouchon({ racine: BUILD_PATCHE, etat });

  try {
    // =====================================================================
    // W — COTE COACH : le reglage, sur le VRAI bundle.
    // =====================================================================
    {
      const { contexte, page } = await nouveauContexte(navigateur, reel.base, 1280, 1000, true, 'coach');
      const champPrix = await ouvrirNouvelleOffre(page, reel.base);
      const champ = page.locator('[data-testid="offer-member-discount-pct"]');

      // --- W1 : une offre NEUVE nait a 0 CHF -> aucun avantage a regler ---
      verifier('W1 sur une offre gratuite (0 CHF), le champ « Avantage membre » est ABSENT',
        (await champ.count()) === 0,
        'le champ est rendu alors qu\'il n\'y a rien a reduire');
      await capture(page, 'w1-offre-gratuite-champ-absent');

      // --- W2 : le coach donne un prix -> le champ apparait ---------------
      await champPrix.fill('30');
      await page.waitForTimeout(400);
      let present = (await champ.count()) === 1 && await champ.isVisible();
      verifier('W2 des qu\'un prix est saisi, le champ apparait et est visible', present,
        'aucun [data-testid="offer-member-discount-pct"] visible a 30 CHF');

      if (!present) {
        verifier('W3 le champ est place JUSTE SOUS le prix', false, 'champ absent');
        verifier('W4 son libelle annonce « Avantage membre (%) »', false, 'champ absent');
        verifier('W5 il vaut AUCUN AVANTAGE par defaut', false, 'champ absent');
      } else {
        // Position REELLE dans le DOM, pas dans le source : on compte les
        // controles de saisie entre le prix et l'avantage. Zero = « juste
        // sous ». C'est la seule facon de prouver un placement.
        const pos = await page.evaluate(() => {
          const champs = [...document.querySelectorAll(
            '[data-testid="offer-wizard"] input, input, select, textarea')];
          const av = document.querySelector('[data-testid="offer-member-discount-pct"]');
          const prix = champs.find((e) => e.getAttribute('placeholder') === '30');
          return { i: champs.indexOf(av), p: champs.indexOf(prix) };
        });
        verifier('W3 le champ est place JUSTE SOUS le prix (aucune saisie entre les deux)',
          pos.p >= 0 && pos.i === pos.p + 1, `prix=#${pos.p} avantage=#${pos.i}`);
        const libelle = await page.evaluate(() => {
          const av = document.querySelector('[data-testid="offer-member-discount-pct"]');
          const l = av.parentElement.querySelector('label');
          return l ? l.textContent.trim() : '';
        });
        verifier('W4 son libelle annonce « Avantage membre (%) »',
          /Avantage membre \(%\)/i.test(libelle), `lu : « ${libelle} »`);
        // « Vide ou 0 = AUCUN avantage », dit le code, et le formulaire d'une
        // offre neuve nait bien a 0 (CoachDashboard.js, `member_discount_pct: 0`).
        // Ce qui compte n'est donc pas la forme de la valeur mais son SENS :
        // aucune offre ne doit devenir reduite toute seule.
        const parDefaut = await champ.inputValue();
        verifier('W5 il vaut AUCUN AVANTAGE par defaut (aucune offre ne devient reduite seule)',
          parDefaut === '' || parseFloat(parDefaut) === 0, `lu : « ${parDefaut} »`);
        noter('W5b valeur affichee par defaut dans le champ',
          parDefaut === '' ? 'champ vide' : `« ${parDefaut} » (le placeholder « Ex : 50 » reste donc invisible)`);
      }
      await capture(page, 'w2-champ-visible-a-30chf');

      // --- W6 : l'apercu du tarif membre ---------------------------------
      await champ.fill('50');
      await page.waitForTimeout(400);
      const texteBloc = await page.evaluate(() => {
        const av = document.querySelector('[data-testid="offer-member-discount-pct"]');
        return av ? (av.parentElement.innerText || '').replace(/\s+/g, ' ') : '';
      });
      verifier('W6 50 % sur une offre a 30 CHF affiche « Tarif membre : CHF 15.00 »',
        /Tarif membre\s*:\s*CHF\s*15\.00/i.test(texteBloc), `lu : « ${texteBloc.slice(0, 200) }»`);
      await capture(page, 'w6-apercu-tarif-membre');

      // --- W7 : PULSE 250 — la case « ouvre une adhesion » verrouille -----
      const caseAdhesion = page.locator('[data-testid="offer-creates-membership"]');
      await caseAdhesion.check();
      await page.waitForTimeout(400);
      verifier('W7 case « ouvre une adhesion d\'un an » cochee -> le champ est DESACTIVE',
        (await champ.isDisabled()) === true,
        'on pourrait acheter son adhesion au tarif membre (protection PULSE 250 absente)');
      const explication = await page.evaluate(() => {
        const av = document.querySelector('[data-testid="offer-member-discount-pct"]');
        return av ? (av.parentElement.innerText || '').replace(/\s+/g, ' ') : '';
      });
      verifier('W8 ... et le coach lit POURQUOI (message explicatif affiche)',
        /Indisponible/i.test(explication) && /adh[ée]sion/i.test(explication),
        `lu : « ${explication.slice(0, 200)} »`);
      verifier('W9 ... et l\'apercu du tarif membre disparait (il serait mensonger)',
        !/Tarif membre\s*:/i.test(explication));
      await capture(page, 'w7-verrou-adhesion');

      await caseAdhesion.uncheck();
      await page.waitForTimeout(400);
      verifier('W10 case decochee -> le champ redevient utilisable',
        (await champ.isDisabled()) === false);
      verifier('W11 ... et le reglage du coach n\'a PAS ete efface en chemin',
        (await champ.inputValue()) === '50', `lu : « ${await champ.inputValue()} »`);

      // --- W12 : produit physique — rien a reduire ------------------------
      await page.click('text=(2) Logistique');
      const caseProduit = page.locator('label', { hasText: 'Produit physique' })
        .locator('input[type="checkbox"]').first();
      await caseProduit.check();
      await page.click('text=(1) Bases');
      await page.waitForTimeout(400);
      verifier('W12 sur un produit physique, le champ « Avantage membre » est ABSENT',
        (await champ.count()) === 0,
        'le champ est propose sur un produit alors que l\'avantage ne vise que les seances');
      await capture(page, 'w12-produit-physique');

      // --- W13 : le prix retombe a 0 -> le champ disparait ---------------
      await page.click('text=(2) Logistique');
      await caseProduit.uncheck();
      await page.click('text=(1) Bases');
      await page.waitForTimeout(300);
      await champPrix.fill('0');
      await page.waitForTimeout(400);
      verifier('W13 prix ramene a 0 -> le champ disparait a nouveau',
        (await champ.count()) === 0);

      await contexte.close();
    }

    // --- W14 : aucune couleur codee en dur (lecture du SOURCE) -----------
    {
      const blocs = [
        {
          nom: 'OfferWizard.js (bloc coach)',
          source: fs.readFileSync(
            path.join(RACINE, 'frontend/src/components/dashboard/OfferWizard.js'), 'utf8'),
          debut: 'LOT 3b — AVANTAGE MEMBRE',
          fin: 'V260: prix alternatif',
        },
        {
          nom: 'App.js (bloc client)',
          source: fs.readFileSync(path.join(RACINE, 'frontend/src/App.js'), 'utf8'),
          debut: "LOT 3b — L'AVANTAGE MEMBRE, EN DEUX LIGNES",
          fin: '{appliedDiscount && (',
        },
      ];
      for (const b of blocs) {
        const i = b.source.indexOf(b.debut);
        const j = b.source.indexOf(b.fin, i);
        if (i < 0 || j < 0) {
          verifier(`W14 ${b.nom} : le bloc LOT 3b est localisable dans le source`, false,
            'reperes introuvables — le fichier a change, ce controle doit etre relu');
          continue;
        }
        const bloc = b.source.slice(i, j);
        // On retire d'abord toutes les valeurs de SECOURS legitimes
        // (`var(--x, #hex)`), puis on regarde s'il reste un hex. S'il en reste
        // un, c'est une couleur imposee — exactement ce que la regle interdit.
        const restant = bloc.replace(/var\(\s*--[a-z0-9-]+\s*,\s*#[0-9a-fA-F]{3,8}\s*\)/g, '');
        const durs = restant.match(/#[0-9a-fA-F]{6}\b/g) || [];
        verifier(`W14 ${b.nom} : aucune couleur magenta codee en dur`,
          durs.length === 0, `hex hors var() : ${durs.join(', ')}`);
        verifier(`W15 ${b.nom} : la couleur de marque passe bien par var(--primary-color, …)`,
          /var\(\s*--primary-color/.test(bloc) || /\bPINK\b/.test(bloc),
          'aucune reference a --primary-color ni a la constante PINK');
      }
    }

    // =====================================================================
    // R — ATTEIGNABILITE, sur le bundle REEL. C'est ici que ca fait mal.
    // =====================================================================
    {
      etat.estimation = estimation({ membre: true, raison: 'membre', avantage_pct: 50, votre_tarif: 15 });
      const avant = etat.demandes.length;
      const { contexte, page } = await nouveauContexte(navigateur, reel.base, 1280, 1100, false, 'visiteur-reel');
      await page.goto(`${reel.base}/`, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector(`[data-testid="offer-card-${OFFRE_30.id}"]`, { timeout: 40000 });

      verifier('R1 la vitrine affiche bien l\'offre a 30 CHF servie par le serveur',
        /30/.test(await page.locator(`[data-testid="offer-card-${OFFRE_30.id}"]`).innerText()));
      const grille = await page.locator('[data-testid^="date-btn-"]').count();
      verifier('R2 AUCUNE grille de dates n\'est rendue sur la vitrine reelle',
        grille === 0, `${grille} boutons de date rendus (le test R3 changerait de sens)`);

      // Le geste reel du visiteur : « Réserver » sur la carte.
      await page.click(`[data-testid="offer-reserve-${OFFRE_30.id}"]`);
      await page.waitForTimeout(4000);
      const formulaire = await page.locator('[data-testid="user-info-section"]').count();
      verifier('R3 ce clic n\'ouvre PAS le formulaire de reservation',
        formulaire === 0, `${formulaire} formulaire(s) ouvert(s) — le parcours a change, relire ce test`);
      const tentativeCheckout = reel.journal.some(
        (e) => e.methode === 'POST' && /create-checkout-session/.test(e.chemin));
      verifier('R4 il part en PAIEMENT DIRECT (la tentative de session Stripe est mesuree, '
        + 'et refusee 405 par le bouchon)', tentativeCheckout,
        'aucune tentative de checkout : le parcours a change, relire ce test');
      const appelsReels = etat.demandes.length - avant;
      verifier('R5 aucune estimation tarifaire n\'est demandee sur le parcours reel',
        appelsReels === 0, `${appelsReels} appel(s) — contredit R3, relire ce test`);

      // LE CONSTAT. Il est volontairement redige comme une VERIFICATION, et il
      // ECHOUE : l'ecran existe, il est juste (volet C), mais aucun visiteur ne
      // peut l'atteindre. Le dire « non couvert » serait le maquiller.
      verifier('R6 DEFAUT — la ligne « Avantage membre » est ATTEIGNABLE par un visiteur',
        false,
        'le bloc LOT 3b vit dans le recapitulatif du formulaire, lequel exige offre + cours '
        + '+ date ; or la grille de dates n\'est plus rendue (showSessions = false, V225) et '
        + 'toute offre payante part en paiement direct (v225IsDirectCheckout, V225/V226). '
        + 'Mesure ci-dessus : 0 formulaire, 0 estimation. La fonctionnalite est ECRITE mais '
        + 'INVISIBLE en production.');
      await capture(page, 'r-parcours-reel-sans-formulaire');
      await contexte.close();
    }

    // =====================================================================
    // C — COTE CLIENT : l'affichage, sur le bundle au parcours retabli.
    // =====================================================================
    // Chaque scenario ouvre un contexte NEUF : aucune memoire ne survit d'un
    // scenario a l'autre, et l'affichage mesure ne peut venir que de la reponse
    // du serveur.

    /** Fabrique un scenario client complet et compte ses appels. */
    async function scenarioClient(cle, reponse, idOffre = OFFRE_30.id) {
      etat.estimation = reponse;
      const { contexte, page } = await nouveauContexte(navigateur, patche.base, 1280, 1100, false, cle);
      const appels = await menerAuRecapitulatif(page, patche.base, etat, idOffre);
      const total = await totalAffiche(page);
      const ligne = await page.locator('[data-testid="member-advantage-line"]').count();
      const invitation = await page.locator('[data-testid="member-identification-hint"]').count();
      const corps = (await page.locator('body').innerText()).replace(/\s+/g, ' ');
      return { contexte, page, appels, total, ligne, invitation, corps };
    }

    // --- C1 : NON-MEMBRE -------------------------------------------------
    {
      const s = await scenarioClient('C1', estimation({ membre: false, votre_tarif: 30 }));
      verifier('C1.1 non-membre : le total affiche est 30.00', s.total === '30.00', `lu : ${s.total}`);
      verifier('C1.2 non-membre : AUCUNE ligne « Avantage membre »', s.ligne === 0);
      verifier('C1.3 non-membre : aucune invitation a s\'identifier', s.invitation === 0);
      verifier('C1.4 une seule estimation demandee pour une seule selection',
        s.appels === 1, `${s.appels} appels`);
      await capture(s.page, 'c1-non-membre');
      await s.contexte.close();
    }

    // --- C2 : MEMBRE ACTIF, 50 % ----------------------------------------
    {
      const s = await scenarioClient('C2', estimation({
        membre: true, raison: 'membre', avantage_pct: 50, prix_public: 30, votre_tarif: 15,
      }));
      verifier('C2.1 membre 50 % : la ligne « Avantage membre » est affichee', s.ligne === 1);
      const l = s.ligne === 1
        ? (await s.page.locator('[data-testid="member-advantage-line"]').innerText()).replace(/\s+/g, ' ')
        : '';
      verifier('C2.2 ... et elle annonce -50%', /-\s*50\s*%/.test(l), `lu : « ${l} »`);
      const pub = await lignePrixPublic(s.page);
      verifier('C2.3 le prix public 30.00 est affiche juste au-dessus',
        !!pub && /Prix public/i.test(pub.texte) && /30\.00/.test(pub.texte),
        pub ? `lu : « ${pub.texte} »` : 'ligne absente');
      verifier('C2.4 ... et il est REELLEMENT barre (style calcule)',
        !!pub && /line-through/.test(pub.decoration),
        pub ? `decoration : « ${pub.decoration} »` : 'ligne absente');
      verifier('C2.5 le total affiche est 15.00', s.total === '15.00', `lu : ${s.total}`);
      verifier('C2.6 une seule estimation demandee', s.appels === 1, `${s.appels} appels`);
      await capture(s.page, 'c2-membre-50');
      await s.contexte.close();
    }

    // --- C3 / C4 : ADHESION EXPIREE, puis ADHESION FUTURE ----------------
    // Le serveur tranche : dans les DEUX cas il renvoie `membre: false`. Ce que
    // l'ecran doit prouver, c'est qu'il n'invente rien — et qu'il ne laisse pas
    // fuir le vocabulaire interne (« adhesion_expiree ») sous les yeux du client.
    for (const [cle, raison, titre] of [
      ['C3', 'adhesion_expiree', 'adhesion EXPIREE'],
      ['C4', 'adhesion_future', 'adhesion FUTURE (pas encore commencee)'],
    ]) {
      const s = await scenarioClient(cle, estimation({
        membre: false, raison, avantage_offre_pct: 50, votre_tarif: 30,
      }));
      verifier(`${cle}.1 ${titre} : le total reste 30.00`, s.total === '30.00', `lu : ${s.total}`);
      verifier(`${cle}.2 ${titre} : aucune ligne d'avantage`, s.ligne === 0);
      verifier(`${cle}.3 ${titre} : le vocabulaire interne ne fuite pas a l'ecran`,
        !/adhesion_expiree|adhesion_future|votre_tarif|prix_public_unitaire/i.test(s.corps),
        'un nom de champ technique est visible par le client');
      await capture(s.page, `${cle.toLowerCase()}-${raison}`);
      await s.contexte.close();
    }

    // --- C5 : AVANTAGE 30 % ---------------------------------------------
    {
      const s = await scenarioClient('C5', estimation({
        membre: true, raison: 'membre', avantage_pct: 30, prix_public: 30, votre_tarif: 21,
      }));
      verifier('C5.1 avantage 30 % : le total affiche est 21.00', s.total === '21.00', `lu : ${s.total}`);
      const l = s.ligne === 1
        ? (await s.page.locator('[data-testid="member-advantage-line"]').innerText()).replace(/\s+/g, ' ')
        : '';
      verifier('C5.2 ... et la ligne annonce -30%', /-\s*30\s*%/.test(l), `lu : « ${l} »`);
      await capture(s.page, 'c5-avantage-30');
      await s.contexte.close();
    }

    // --- C6 : MEMBRE 50 % CONTRE PROMO 70 % -> la promo l'emporte --------
    {
      const s = await scenarioClient('C6', estimation({
        membre: false, raison: 'promo', avantage_pct: 70, avantage_offre_pct: 50,
        prix_public: 30, votre_tarif: 9,
      }));
      verifier('C6.1 quand la promo l\'emporte, AUCUNE ligne « Avantage membre »',
        s.ligne === 0, 'l\'ecran attribuerait au statut de membre une remise qui vient du code promo');
      verifier('C6.2 ... ni ligne « Prix public » barree', !/Prix public/i.test(s.corps));
      // MESURE, pas verdict : sans code promo saisi dans le formulaire, le
      // recapitulatif retombe sur son calcul local (30.00). Le total « 9.00 »
      // du serveur n'est PAS repris — c'est conforme au code (`calculateTotal`
      // ne suit le serveur que si `membre` est vrai) et sans consequence, la
      // caisse restant l'autorite. On le consigne pour que ce ne soit pas une
      // surprise le jour ou quelqu'un s'y fiera.
      noter('C6.3 total affiche quand la promo gagne (le navigateur garde son calcul local)',
        `${s.total} CHF — le serveur disait 9.00`);
      await capture(s.page, 'c6-promo-gagne');
      await s.contexte.close();
    }

    // --- C7 : EGALITE 50 / 50 -> le membre gagne l'egalite ---------------
    {
      const s = await scenarioClient('C7', estimation({
        membre: true, raison: 'membre', avantage_pct: 50, prix_public: 30, votre_tarif: 15,
      }));
      verifier('C7.1 a egalite (membre 50 % / promo 50 %), la ligne « Avantage membre » EST affichee',
        s.ligne === 1, 'le membre perdrait l\'egalite a l\'ecran');
      verifier('C7.2 ... et le total est bien 15.00', s.total === '15.00', `lu : ${s.total}`);
      await capture(s.page, 'c7-egalite');
      await s.contexte.close();
    }

    // --- C8 : MEMBRE NON IDENTIFIE ---------------------------------------
    {
      const s = await scenarioClient('C8', estimation({
        membre: false, identification_requise: true, avantage_offre_pct: 50, votre_tarif: 30,
      }));
      verifier('C8.1 membre non identifie : l\'invitation discrete est affichee',
        s.invitation === 1 && await s.page.locator('[data-testid="member-identification-hint"]').isVisible(),
        'le membre croirait avoir perdu son avantage');
      verifier('C8.2 ... elle invite a ouvrir son espace, sans rien reveler',
        /Membre Afroboost/i.test(s.corps) && !/@/.test(
          await s.page.locator('[data-testid="member-identification-hint"]').innerText()));
      verifier('C8.3 ... et aucune ligne d\'avantage n\'est affichee (il n\'y a pas droit tant '
        + 'qu\'il n\'est pas identifie)', s.ligne === 0);
      verifier('C8.4 ... le total reste le prix public 30.00', s.total === '30.00', `lu : ${s.total}`);
      await capture(s.page, 'c8-non-identifie');
      await s.contexte.close();
    }

    // --- C9 : LE SERVEUR CHANGE D'AVIS (50 % puis 30 %) -------------------
    // Deux estimations successives sur la MEME offre. Si l'ecran suivait sa
    // propre memoire plutot que le serveur, le second montant resterait a 15.
    {
      etat.estimation = estimation({
        membre: true, raison: 'membre', avantage_pct: 50, prix_public: 30, votre_tarif: 15,
      });
      const { contexte, page } = await nouveauContexte(navigateur, patche.base, 1280, 1100, false, 'C9');
      const a1 = await menerAuRecapitulatif(page, patche.base, etat, OFFRE_30.id, 0);
      verifier('C9.1 premiere estimation (50 %) : 15.00 affiche',
        (await totalAffiche(page)) === '15.00', `lu : ${await totalAffiche(page)}`);
      verifier('C9.2 ... obtenue en UN seul appel', a1 === 1, `${a1} appels`);

      // Le coach a change son reglage entre-temps : le serveur repond autrement.
      etat.estimation = estimation({
        membre: true, raison: 'membre', avantage_pct: 30, prix_public: 30,
        quantity: 2, prix_public_unitaire: 30, votre_tarif: 21,
      });
      const avant = etat.demandes.length;
      // Une SEULE nouvelle selection : on ajoute la deuxieme date.
      await page.click(`[data-testid="date-btn-${COURS.id}-1"]`);
      await page.waitForTimeout(4000);
      const a2 = etat.demandes.length - avant;
      verifier('C9.3 seconde estimation (30 %) : 21.00 affiche — l\'ecran relaie le serveur, '
        + 'il ne memorise rien', (await totalAffiche(page)) === '21.00',
        `lu : ${await totalAffiche(page)}`);
      const l = (await page.locator('[data-testid="member-advantage-line"]').innerText()).replace(/\s+/g, ' ');
      verifier('C9.4 ... et la ligne annonce desormais -30%', /-\s*30\s*%/.test(l), `lu : « ${l} »`);
      verifier('C9.5 ... obtenue en UN seul appel supplementaire (aucune rafale)',
        a2 === 1, `${a2} appels pour un seul changement de selection`);
      await capture(page, 'c9-changement-50-vers-30');
      await contexte.close();
    }

    // --- C10 : PULSE 250 N'EST PAS AFFECTE --------------------------------
    {
      const s = await scenarioClient('C10', {
        offer_id: OFFRE_PULSE.id, quantity: 1, devise: 'CHF',
        prix_public_unitaire: 250, prix_public: 250, votre_tarif: 250,
        membre: false, avantage_pct: null, raison: 'public',
      }, OFFRE_PULSE.id);
      verifier('C10.1 PULSE 250 (offre qui OUVRE l\'adhesion) : le total reste 250.00',
        s.total === '250.00', `lu : ${s.total}`);
      verifier('C10.2 ... et aucune ligne d\'avantage membre n\'apparait', s.ligne === 0,
        'on vendrait l\'adhesion au tarif membre');
      await capture(s.page, 'c10-pulse-250');
      await s.contexte.close();
    }

    // =====================================================================
    // Z — GARDE-FOUS TRANSVERSES
    // =====================================================================
    {
      const ecritures = [...reel.journal, ...patche.journal]
        .filter((e) => e.methode !== 'GET' && e.chemin.startsWith('/api/'));
      const horsEstimation = ecritures.filter((e) => e.chemin !== '/api/tarif/estimation');
      const abouties = horsEstimation.filter((e) => e.statut !== 405);
      verifier('Z1 aucune ecriture autre que l\'estimation n\'a abouti (toutes refusees en 405)',
        abouties.length === 0, abouties.map((e) => `${e.methode} ${e.chemin}`).join(', '));
      const spontanees = [...new Set(horsEstimation.map((e) => `${e.methode} ${e.chemin}`))];
      noter('Z1b ecritures tentees spontanement par l\'app, toutes refusees',
        spontanees.join(', ') || 'aucune');

      const bruit = /ERR_FAILED|ERR_ABORTED|fetching the script|405|sanitize-data|auto-save/i;
      const vraies = erreursPage.filter((e) => !bruit.test(e));
      verifier('Z2 aucune erreur JavaScript sur l\'ensemble des parcours traverses',
        vraies.length === 0, vraies.slice(0, 4).join(' | '));

      // Si le bundle avait ete construit avec la valeur de `frontend/.env.local`
      // (https://afroboost.com), les appels seraient partis vers la PRODUCTION.
      // Le navigateur les couperait, mais un tel bundle ne prouverait plus rien :
      // ce test doit le DIRE, pas le taire.
      const fuites = [...new Set(bloqueesGlobal.filter((u) => u.includes('/api/')))];
      verifier('Z3 aucun appel API n\'a tente de sortir vers un autre hote',
        fuites.length === 0, `bundle mal construit ? ${fuites.slice(0, 3).join(', ')}`);

      // Compte GLOBAL : 10 selections faites au total sur les scenarios C
      // (C1..C8 = 8, C9 = 2, C10 = 1) -> 11 estimations attendues, pas une de
      // plus. Une boucle d'appels ferait exploser ce nombre.
      verifier('Z4 aucune boucle d\'appels : 11 estimations pour 11 changements de selection',
        etat.demandes.length === 11, `${etat.demandes.length} appels au total`);
    }

    // =====================================================================
    // CE QUI N'EST PAS COUVERT, ET QUI DOIT SE VOIR
    // =====================================================================
    nonCouvert('X1 la REGLE serveur (qui est membre, quel pourcentage l\'emporte, '
      + 'revalidation des occurrences)',
      'le backend ne peut pas tourner ici (Python 3.9, FastAPI absent, MONGO_URL requis) : '
      + 'les reponses /api/tarif/estimation sont des fixtures. Couverture = tests Python '
      + '(tests/test_lot3b_avantage_membre.py).');
    nonCouvert('X2 le montant REELLEMENT preleve a la caisse',
      'aucun paiement n\'est declenche (consigne). L\'estimation est un affichage ; '
      + 'la caisse recalcule tout de son cote et ignore le total du navigateur (V429).');
    nonCouvert('X3 la persistance de `member_discount_pct` (PUT /offers)',
      'toute ecriture est refusee par le bouchon (405) : seuls la presence et le '
      + 'comportement du champ sont mesures, pas son enregistrement.');
    nonCouvert('X4 les scenarios C sur le bundle REEL',
      'ils tournent sur un bundle ou DEUX lignes ont ete remises dans leur position '
      + 'd\'avant V225/V226 (voir PATCHES), faute de quoi l\'ecran est inatteignable — '
      + 'c\'est l\'objet du defaut R6. L\'affichage est donc prouve JUSTE, pas prouve VISIBLE.');
  } finally {
    await navigateur.close();
    await reel.arreter();
    await patche.arreter();
  }
}

// ---------------------------------------------------------------------------
// 6. RAPPORT
// ---------------------------------------------------------------------------

principal()
  .then(() => {
    const largeur = Math.min(Math.max(...resultats.map((r) => r.nom.length), 40), 110);
    console.log('\n╔' + '═'.repeat(largeur + 12) + '╗');
    console.log('║ LOT 3b — AVANTAGE TARIFAIRE MEMBRE : PREUVES EN NAVIGATEUR REEL'
      + ' '.repeat(Math.max(0, largeur - 51)) + '║');
    console.log('╚' + '═'.repeat(largeur + 12) + '╝');
    let echecs = 0;
    for (const r of resultats) {
      const etiquette = r.ok === null ? 'NON TESTE' : r.ok ? '   OK    ' : '  ECHEC  ';
      if (r.ok === false) echecs += 1;
      console.log(`[${etiquette}] ${r.nom}`);
      if (r.detail) console.log('            ↳ ' + r.detail);
    }
    const ok = resultats.filter((r) => r.ok === true).length;
    const nc = resultats.filter((r) => r.ok === null).length;
    console.log(`\n${ok} OK · ${echecs} ECHEC · ${nc} non teste / informatif`);
    console.log('Captures : ' + CAPTURES);
    process.exit(echecs === 0 ? 0 : 1);
  })
  .catch((e) => {
    console.error('\nARRET BRUTAL :', e && e.stack ? e.stack : e);
    process.exit(2);
  });
