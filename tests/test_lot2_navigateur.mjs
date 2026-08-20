/**
 * LOT 2 — ADHESION AUTOMATIQUE A L'ACHAT : LES PREUVES EN NAVIGATEUR REEL.
 * =======================================================================
 *
 * POURQUOI CE TEST EXISTE
 * -----------------------
 * Les autres tests `.mjs` du depot LISENT le code source. C'est utile, mais un
 * fichier qui contient `data-testid="badge-membre"` ne prouve pas qu'un badge
 * s'affiche : il peut etre rendu derriere une condition fausse, masque par un
 * parent, ou casse par une erreur JavaScript survenue plus tot. Ici on ouvre un
 * VRAI Chromium, on charge le VRAI bundle construit par craco, et on regarde ce
 * qui est reellement a l'ecran.
 *
 * CE QUI EST SIMULE, ET CE QUI NE L'EST PAS
 * -----------------------------------------
 * SIMULE : le backend. Il ne peut pas tourner ici (Python 3.9, FastAPI absent,
 * MONGO_URL obligatoire). Les reponses `/api/*` viennent donc de fixtures
 * ecrites a la main (`tests/serveur_bouchon_lot2.mjs`). Ce test ne dit donc
 * RIEN de la regle serveur qui cree l'adhesion a l'achat — il dit ce que
 * l'interface fait d'une reponse donnee. La regle serveur est couverte, elle,
 * par les tests Python (`tests/test_p1bisa_adhesions.py`).
 * PAS SIMULE : le code frontend. Aucun composant n'est reecrit, aucun module
 * n'est remplace. C'est le bundle de production qui s'execute.
 *
 * CE QUE CE TEST NE TOUCHE JAMAIS
 * -------------------------------
 * Aucun paiement, aucun clic d'achat, aucune ecriture. Le bouchon refuse tout
 * verbe autre que GET (405) et le consigne ; le scenario final le verifie. Le
 * navigateur coupe en outre toute requete sortant de 127.0.0.1 : rien ne part
 * vers la production.
 *
 * LANCEMENT
 *   node tests/test_lot2_navigateur.mjs            (construit si necessaire)
 *   node tests/test_lot2_navigateur.mjs --sans-build   (reutilise tel quel)
 */
import fs from 'fs';
import os from 'os';
import path from 'path';
import crypto from 'crypto';
import { execFileSync } from 'child_process';
import { fileURLToPath } from 'url';
import { createRequire } from 'module';
import { demarrer, etatInitial, EMAIL_COACH } from './serveur_bouchon_lot2.mjs';

const require_ = createRequire(import.meta.url);
const CHEMIN_PLAYWRIGHT = '/Users/afroboost/.claude/skills/gstack/node_modules/playwright-core';
const { chromium } = require_(CHEMIN_PLAYWRIGHT);

const RACINE = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const TRAVAIL = path.join(os.tmpdir(), 'afroboost-lot2-navigateur');
const BUILD = path.join(TRAVAIL, 'build');
const CAPTURES = path.join(TRAVAIL, 'captures');
const EMPREINTE = path.join(TRAVAIL, 'empreinte.txt');
const SANS_BUILD = process.argv.includes('--sans-build');

// ---------------------------------------------------------------------------
// 0. LE BUNDLE : construit a partir du VRAI arbre de travail, hors du depot.
// ---------------------------------------------------------------------------

/** Les fichiers dont dependent les ecrans testes. Leur empreinte decide du
 *  rafraichissement : inutile de reconstruire 3 minutes pour rien, mais hors de
 *  question de tester un bundle perime. */
const SOURCES = [
  'frontend/src/App.js',
  'frontend/src/components/CoachDashboard.js',
  'frontend/src/components/dashboard/ContactsManager.js',
  'frontend/src/components/dashboard/FicheContact.js',
  'frontend/src/components/dashboard/CarteContact.js',
  'frontend/src/components/dashboard/OfferWizard.js',
  'frontend/src/components/dashboard/OffersManager.js',
  'frontend/src/utils/authSession.js',
  'frontend/src/utils/useLargeurEcran.js',
];

function empreinteSources() {
  const h = crypto.createHash('sha256');
  for (const s of SOURCES) h.update(fs.readFileSync(path.join(RACINE, s)));
  return h.digest('hex');
}

function copier(src, dst) {
  fs.mkdirSync(dst, { recursive: true });
  for (const e of fs.readdirSync(src, { withFileTypes: true })) {
    const a = path.join(src, e.name), b = path.join(dst, e.name);
    if (e.isDirectory()) copier(a, b);
    else fs.copyFileSync(a, b);
  }
}

function preparerBundle() {
  const attendue = empreinteSources();
  const connue = fs.existsSync(EMPREINTE) ? fs.readFileSync(EMPREINTE, 'utf8').trim() : '';
  if (fs.existsSync(path.join(BUILD, 'index.html')) && connue === attendue) {
    console.log('· bundle deja a jour dans ' + BUILD);
    return;
  }
  if (SANS_BUILD) {
    throw new Error('bundle absent ou perime, et --sans-build demande. Relancer sans l\'option.');
  }
  console.log('· construction du frontend (craco), quelques minutes…');
  // `REACT_APP_BACKEND_URL` VIDE, et c'est capital : `frontend/.env.local`
  // contient `https://afroboost.com`. Sans cette neutralisation, le bundle de
  // test enverrait ses appels A LA PRODUCTION. Une variable posee dans
  // l'environnement du shell l'emporte sur les fichiers `.env` (dotenv
  // n'ecrase jamais une cle deja presente) : le fichier du depot n'est donc ni
  // lu de travers ni modifie. Le navigateur coupe en outre toute requete hors
  // de 127.0.0.1 — ceinture ET bretelles.
  execFileSync('npx', ['craco', 'build'], {
    cwd: path.join(RACINE, 'frontend'),
    env: { ...process.env, CI: 'false', REACT_APP_BACKEND_URL: '' },
    stdio: 'inherit',
  });
  fs.rmSync(BUILD, { recursive: true, force: true });
  fs.mkdirSync(TRAVAIL, { recursive: true });
  copier(path.join(RACINE, 'frontend', 'build'), BUILD);
  // Le depot ne doit garder AUCUNE trace du test : `frontend/build` contient
  // 16 fichiers suivis par git (index.html, manifest, icones). On les remet
  // exactement dans l'etat du depot. Le reste (`build/static`) est ignore par
  // `.gitignore`, donc invisible pour git.
  execFileSync('git', ['checkout', '--', 'frontend/build'], { cwd: RACINE, stdio: 'inherit' });
  fs.writeFileSync(EMPREINTE, attendue);
  console.log('· bundle copie dans ' + BUILD + ', depot restaure');
}

// ---------------------------------------------------------------------------
// 1. Les fixtures : trois contacts, trois etats d'adhesion.
// ---------------------------------------------------------------------------

const contactBase = (extra) => ({
  type: 'user', source: 'app', contact_type: 'participant',
  statut_abonnement: 'actif', pays: 'CH', zone: 'suisse',
  canaux: { email: true, whatsapp: true, telephone: false },
  consentement: { email: 'autorise', whatsapp: 'inconnu' },
  categories: [],
  ...extra,
});

const SANS_ADHESION = contactBase({
  id: 'c-sans', name: 'Awa Nouvelle', email: 'awa@example.test',
  whatsapp: '+41760000001',
});

const AVEC_ADHESION_ACTIVE = contactBase({
  id: 'c-active', name: 'Bintou Membre', email: 'bintou@example.test',
  whatsapp: '+41760000002',
  adhesion: {
    statut: 'active', date_debut: '2026-08-19', date_fin: '2027-08-19', source: 'achat',
  },
});

const AVEC_ADHESION_EXPIREE = contactBase({
  id: 'c-expiree', name: 'Chloe Expiree', email: 'chloe@example.test',
  whatsapp: '+41760000003',
  adhesion: {
    statut: 'expiree', date_debut: '2024-01-01', date_fin: '2025-01-01', source: 'manuelle',
  },
});

const OFFRE_ENTREE = {
  id: 'offre-adhesion', name: 'Adhésion Afroboost', title: 'Adhésion Afroboost',
  description: "L'offre d'entrée : un an de membre.",
  price: 250, currency: 'CHF', sessions: 10, active: true, is_active: true,
  creates_membership: true, first_purchase_eligible: true,
  coach_id: EMAIL_COACH, images: [],
};

// ---------------------------------------------------------------------------
// 2. Tableau de resultats.
// ---------------------------------------------------------------------------

const resultats = [];
/** Toute URL que le navigateur a refusé de laisser sortir de 127.0.0.1. */
const bloqueesGlobal = [];
const verifier = (nom, condition, detail = '') => {
  resultats.push({ nom, ok: !!condition, detail: condition ? '' : detail });
};
const nonTeste = (nom, pourquoi) => resultats.push({ nom, ok: null, detail: pourquoi });

// ---------------------------------------------------------------------------
// 3. Pilotage du navigateur.
// ---------------------------------------------------------------------------

/** Un JWT NON SIGNE mais de forme valide, avec `exp` lointain. Le frontend ne
 *  verifie que `exp` (utils/jwt.js le dit explicitement : la signature ne peut
 *  pas etre verifiee dans un navigateur). Aucune garde serveur n'est franchie :
 *  le serveur ici est un bouchon local, il ne protege rien. */
function jetonFactice(email) {
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
  const exp = Math.floor(Date.now() / 1000) + 3600 * 24 * 30;
  return `${b64({ alg: 'HS256', typ: 'JWT' })}.${b64({ email, sub: email, exp })}.signature-factice`;
}

/**
 * @param connecte  false = simple VISITEUR (aucune cle coach dans le
 *   localStorage). Indispensable pour la vitrine : avec une session coach,
 *   App.js rend le dashboard a la place de la page publique, et l'offre
 *   d'entree ne serait jamais a l'ecran.
 */
async function nouveauContexte(navigateur, base, largeur, hauteur, connecte = true) {
  const contexte = await navigateur.newContext({
    viewport: { width: largeur, height: hauteur },
    baseURL: base,
  });
  // AUCUNE sortie hors de 127.0.0.1 : ni PostHog, ni Cloudinary, ni la prod.
  const hote = new URL(base).host;
  await contexte.route('**/*', (route) => {
    const u = new URL(route.request().url());
    if (u.host !== hote) { bloqueesGlobal.push(u.href); return route.abort(); }
    // Le Service Worker servirait un bundle cache : on le coupe net.
    if (u.pathname === '/sw.js') return route.abort();
    return route.continue();
  });
  if (!connecte) return { contexte };
  await contexte.addInitScript(
    ([email, jeton]) => {
      localStorage.setItem('afroboost_coach_mode', 'true');
      localStorage.setItem('afroboost_coach_user', JSON.stringify({ email, name: 'Coach Test' }));
      localStorage.setItem('afroboost_jwt', jeton);
      // Le Service Worker n'est PAS neutralise ici : `index.html` appelle
      // `navigator.serviceWorker.register(...)` sans garde, et le retirer
      // provoquerait une fausse erreur de page. Couper `/sw.js` au niveau du
      // reseau (voir `contexte.route`) suffit : l'enregistrement echoue, le
      // depot l'attrape deja (« [V121] SW fail »), et aucun cache n'est rejoue.
    },
    [EMAIL_COACH, jetonFactice(EMAIL_COACH)]
  );
  return { contexte };
}

/** Ouvre le dashboard sur l'onglet demande et attend qu'il soit rendu. */
async function ouvrirDashboard(page, base, onglet) {
  await page.goto(`${base}/#partner-dashboard`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('[data-testid="coach-nav-toggle"]', { timeout: 30000 });
  if (onglet) {
    await page.click('[data-testid="coach-nav-toggle"]');
    await page.click(`[data-testid="coach-tab-${onglet}"]`);
  }
}

async function capture(page, nom) {
  fs.mkdirSync(CAPTURES, { recursive: true });
  await page.screenshot({ path: path.join(CAPTURES, `${nom}.png`), fullPage: false });
}

// ---------------------------------------------------------------------------
// 4. Les scenarios.
// ---------------------------------------------------------------------------

async function principal() {
  preparerBundle();

  const etat = etatInitial();
  const serveur = await demarrer({ racine: BUILD, etat });
  const navigateur = await chromium.launch({ headless: true });
  const erreursPage = [];

  try {
    // === S1 — L'OFFRE D'ENTREE S'AFFICHE SUR LA VITRINE ====================
    {
      etat.offers = [OFFRE_ENTREE];
      etat.contacts = [];
      // VISITEUR, pas coach : sinon App.js rendrait le dashboard.
      const { contexte } = await nouveauContexte(navigateur, serveur.base, 1280, 900, false);
      const page = await contexte.newPage();
      page.on('pageerror', (e) => erreursPage.push(`vitrine: ${e.message}`));
      await page.goto(serveur.base + '/', { waitUntil: 'domcontentloaded' });
      const carte = page.locator(`[data-testid="offer-card-${OFFRE_ENTREE.id}"]`).first();
      let vue = false;
      try { await carte.waitFor({ state: 'visible', timeout: 20000 }); vue = true; } catch (e) { /* mesure */ }
      verifier('S1.1 la carte de l\'offre d\'entree est visible sur la vitrine', vue,
        'aucun [data-testid="offer-card-offre-adhesion"] visible');
      if (vue) {
        const texte = await carte.innerText();
        verifier('S1.2 le nom de l\'offre est affiche', /Adh[ée]sion Afroboost/i.test(texte), texte.slice(0, 160));
        verifier('S1.3 le prix rendu par le serveur est affiche', /250/.test(texte), texte.slice(0, 160));
      } else {
        verifier('S1.2 le nom de l\'offre est affiche', false, 'carte absente');
        verifier('S1.3 le prix rendu par le serveur est affiche', false, 'carte absente');
      }
      await capture(page, 's1-vitrine-offre-entree');
      await contexte.close();
    }

    // === S2 — AUCUNE NOUVELLE ENTREE DE NAVIGATION ========================
    // On compare les onglets REELLEMENT rendus a ceux declares dans le
    // CoachDashboard.js de HEAD (donc AVANT le LOT 2). Toute entree ajoutee
    // par le lot ferait echouer ce test.
    let ongletsVus = [];
    {
      const { contexte } = await nouveauContexte(navigateur, serveur.base, 1280, 900);
      const page = await contexte.newPage();
      page.on('pageerror', (e) => erreursPage.push(`nav: ${e.message}`));
      await ouvrirDashboard(page, serveur.base);
      await page.click('[data-testid="coach-nav-toggle"]');
      ongletsVus = await page.$$eval('[data-testid^="coach-tab-"]',
        (n) => n.map((e) => e.getAttribute('data-testid').replace('coach-tab-', '')));
      await capture(page, 's2-onglets-dashboard');

      const sourceHead = execFileSync('git',
        ['show', 'HEAD:frontend/src/components/CoachDashboard.js'], { cwd: RACINE, maxBuffer: 64e6 })
        .toString('utf8');
      const bloc = sourceHead.slice(sourceHead.indexOf('const baseTabs = ['));
      const ongletsHead = [...bloc.slice(0, bloc.indexOf('];')).matchAll(/\{\s*id:\s*"([^"]+)"/g)]
        .map((m) => m[1]);

      verifier('S2.1 les onglets sont lisibles depuis HEAD', ongletsHead.length >= 5,
        `extraits : ${ongletsHead.join(', ')}`);
      verifier('S2.2 aucune entree de navigation ajoutee ni retiree par le LOT 2',
        JSON.stringify(ongletsVus) === JSON.stringify(ongletsHead),
        `rendus : [${ongletsVus.join(', ')}] / HEAD : [${ongletsHead.join(', ')}]`);
      verifier('S2.3 aucun onglet ne parle d\'adhesion ou de membre',
        !ongletsVus.some((o) => /adhes|membre|member/i.test(o)),
        ongletsVus.join(', '));
      await contexte.close();
    }

    // === S3 — AVANT CONFIRMATION : AUCUNE ADHESION N'EXISTE ================
    {
      etat.contacts = [SANS_ADHESION];
      // 3a. liste desktop : aucun badge « Membre ».
      const { contexte } = await nouveauContexte(navigateur, serveur.base, 1280, 900);
      const page = await contexte.newPage();
      page.on('pageerror', (e) => erreursPage.push(`s3-desktop: ${e.message}`));
      await ouvrirDashboard(page, serveur.base, 'contacts');
      await page.waitForSelector('text=Awa Nouvelle', { timeout: 20000 });
      verifier('S3.1 avant confirmation, aucun badge « Membre » dans la liste',
        (await page.locator('[data-testid="badge-membre"]').count()) === 0);
      await capture(page, 's3-liste-sans-adhesion');
      await contexte.close();

      // 3b. fiche (rendu mobile : c'est le seul chemin d'ouverture de la fiche).
      const m = await nouveauContexte(navigateur, serveur.base, 400, 860);
      const pm = await m.contexte.newPage();
      pm.on('pageerror', (e) => erreursPage.push(`s3-mobile: ${e.message}`));
      await ouvrirDashboard(pm, serveur.base, 'contacts');
      await pm.waitForSelector('[data-testid="carte-contact"]', { timeout: 20000 });
      verifier('S3.2 avant confirmation, aucune puce « Membre » sur la carte',
        !(await pm.locator('[data-testid="carte-contact"]').first().innerText()).includes('Membre'));
      await pm.click(`[data-testid="ouvrir-${SANS_ADHESION.id}"]`);
      await pm.waitForSelector('[data-testid="fiche-contact"]', { timeout: 10000 });
      const titresS3 = await pm.evaluate(() => [...document
        .querySelector('[data-testid="fiche-contact"]').querySelectorAll('p')]
        .map((n) => (n.textContent || '').trim()));
      verifier('S3.3 la fiche n\'affiche AUCUNE section Adhesion',
        !titresS3.some((t) => /^Adh[ée]sion$/i.test(t)),
        `titres lus : ${titresS3.filter(Boolean).join(' | ').slice(0, 220)}`);
      verifier('S3.4 aucun statut d\'adhesion n\'est rendu',
        (await pm.locator('[data-testid="fiche-adhesion-statut"]').count()) === 0);
      await capture(pm, 's3-fiche-sans-adhesion');
      await m.contexte.close();
    }

    // === S4 — APRES CONFIRMATION SIMULEE : LE MEMBRE APPARAIT =============
    {
      etat.contacts = [AVEC_ADHESION_ACTIVE];
      const { contexte } = await nouveauContexte(navigateur, serveur.base, 1280, 900);
      const page = await contexte.newPage();
      page.on('pageerror', (e) => erreursPage.push(`s4-desktop: ${e.message}`));
      await ouvrirDashboard(page, serveur.base, 'contacts');
      await page.waitForSelector('text=Bintou Membre', { timeout: 20000 });
      const badge = page.locator('[data-testid="badge-membre"]');
      verifier('S4.1 le badge « Membre » apparait dans la liste',
        (await badge.count()) === 1 && (await badge.first().isVisible()));
      verifier('S4.2 le badge porte bien le mot « Membre »',
        (await badge.first().innerText()).trim() === 'Membre');
      await capture(page, 's4-liste-membre-actif');
      await contexte.close();

      const m = await nouveauContexte(navigateur, serveur.base, 400, 860);
      const pm = await m.contexte.newPage();
      pm.on('pageerror', (e) => erreursPage.push(`s4-mobile: ${e.message}`));
      await ouvrirDashboard(pm, serveur.base, 'contacts');
      await pm.waitForSelector('[data-testid="carte-contact"]', { timeout: 20000 });
      verifier('S4.3 la carte mobile porte la puce « Membre »',
        (await pm.locator('[data-testid="carte-contact"]').first().innerText()).includes('Membre'));
      await pm.click(`[data-testid="ouvrir-${AVEC_ADHESION_ACTIVE.id}"]`);
      await pm.waitForSelector('[data-testid="fiche-adhesion-statut"]', { timeout: 10000 });
      const statut = (await pm.locator('[data-testid="fiche-adhesion-statut"]').innerText()).trim();
      verifier('S4.4 la fiche affiche « Membre Afroboost »',
        statut === 'Membre Afroboost', `lu : « ${statut} »`);
      const fiche = await pm.locator('[data-testid="fiche-contact"]').innerText();
      verifier('S4.5 la fiche affiche « Actif jusqu\'au » suivi de la date de fin',
        /Actif jusqu[’']au/.test(fiche) && fiche.includes('19.08.2027'),
        fiche.slice(fiche.search(/ADH[ÉE]SION/i), fiche.search(/ADH[ÉE]SION/i) + 180));
      verifier('S4.6 l\'origine « Achat en ligne » est affichee',
        fiche.includes('Achat en ligne'));
      verifier('S4.7 la fiche ne montre PAS de periode quand l\'adhesion est active',
        !fiche.includes('2026-08-19') && !/P[ée]riode/.test(fiche));
      await capture(pm, 's4-fiche-membre-actif');
      await m.contexte.close();
    }

    // === S5 — DEJA MEMBRE, MAIS ADHESION EXPIREE ==========================
    {
      etat.contacts = [AVEC_ADHESION_EXPIREE];
      const { contexte } = await nouveauContexte(navigateur, serveur.base, 1280, 900);
      const page = await contexte.newPage();
      page.on('pageerror', (e) => erreursPage.push(`s5-desktop: ${e.message}`));
      await ouvrirDashboard(page, serveur.base, 'contacts');
      await page.waitForSelector('text=Chloe Expiree', { timeout: 20000 });
      verifier('S5.1 une adhesion expiree n\'affiche AUCUN badge « Membre »',
        (await page.locator('[data-testid="badge-membre"]').count()) === 0);
      await capture(page, 's5-liste-expiree');
      await contexte.close();

      const m = await nouveauContexte(navigateur, serveur.base, 400, 860);
      const pm = await m.contexte.newPage();
      pm.on('pageerror', (e) => erreursPage.push(`s5-mobile: ${e.message}`));
      await ouvrirDashboard(pm, serveur.base, 'contacts');
      await pm.waitForSelector('[data-testid="carte-contact"]', { timeout: 20000 });
      verifier('S5.2 la carte mobile ne porte PAS la puce « Membre »',
        !(await pm.locator('[data-testid="carte-contact"]').first().innerText()).includes('Membre'));
      await pm.click(`[data-testid="ouvrir-${AVEC_ADHESION_EXPIREE.id}"]`);
      await pm.waitForSelector('[data-testid="fiche-adhesion-statut"]', { timeout: 10000 });
      const statut = (await pm.locator('[data-testid="fiche-adhesion-statut"]').innerText()).trim();
      verifier('S5.3 la fiche dit « Adhésion expirée »', statut === 'Adhésion expirée', `lu : « ${statut} »`);
      const fiche = await pm.locator('[data-testid="fiche-contact"]').innerText();
      verifier('S5.4 la periode complete est affichee',
        /P[ée]riode/.test(fiche) && fiche.includes('01.01.2024') && fiche.includes('01.01.2025'),
        fiche.slice(0, 400));
      verifier('S5.5 l\'origine « Saisie manuelle » est affichee', fiche.includes('Saisie manuelle'));
      await capture(pm, 's5-fiche-expiree');
      await m.contexte.close();
    }

    // === S6 — LA SECTION EST DANS LA FICHE, AU BON ENDROIT, SANS NOUVELLE PAGE
    {
      etat.contacts = [AVEC_ADHESION_ACTIVE];
      const m = await nouveauContexte(navigateur, serveur.base, 400, 860);
      const pm = await m.contexte.newPage();
      pm.on('pageerror', (e) => erreursPage.push(`s6: ${e.message}`));
      await ouvrirDashboard(pm, serveur.base, 'contacts');
      await pm.waitForSelector('[data-testid="carte-contact"]', { timeout: 20000 });
      const urlAvant = pm.url();
      await pm.click(`[data-testid="ouvrir-${AVEC_ADHESION_ACTIVE.id}"]`);
      await pm.waitForSelector('[data-testid="fiche-adhesion-statut"]', { timeout: 10000 });

      verifier('S6.1 ouvrir la fiche ne change pas d\'URL (aucune nouvelle page)',
        pm.url() === urlAvant, `${urlAvant} -> ${pm.url()}`);
      verifier('S6.2 le statut d\'adhesion est bien A L\'INTERIEUR de la fiche',
        await pm.evaluate(() => {
          const f = document.querySelector('[data-testid="fiche-contact"]');
          const s = document.querySelector('[data-testid="fiche-adhesion-statut"]');
          return !!(f && s && f.contains(s));
        }));

      const titres = await pm.evaluate(() => {
        const f = document.querySelector('[data-testid="fiche-contact"]');
        return [...f.querySelectorAll('p')]
          .map((p) => (p.textContent || '').trim())
          .filter((t) => /^(Identit|Afroboost|Adh|Canaux|Consent|Étiquett|Etiquett)/i.test(t));
      });
      const iAdh = titres.findIndex((t) => /^Adh/i.test(t));
      const iAfro = titres.findIndex((t) => /^Afroboost/i.test(t));
      const iCan = titres.findIndex((t) => /^Canaux/i.test(t));
      verifier('S6.3 la section « Adhésion » est placee entre « Afroboost » et « Canaux »',
        iAdh > -1 && iAfro > -1 && iCan > -1 && iAfro < iAdh && iAdh < iCan,
        `titres lus : ${titres.join(' | ')}`);
      verifier('S6.4 la fiche reste un panneau : le dashboard est toujours monte derriere',
        (await pm.locator('[data-testid="coach-nav-toggle"]').count()) === 1);
      await capture(pm, 's6-placement-section');
      await m.contexte.close();
    }

    // === S7 — UN 403 SUR /contacts/all NE FUIT RIEN ET NE CASSE RIEN ======
    {
      etat.contacts = [AVEC_ADHESION_ACTIVE];
      etat.statutContacts = 403;
      const { contexte } = await nouveauContexte(navigateur, serveur.base, 1280, 900);
      const page = await contexte.newPage();
      const erreurs403 = [];
      page.on('pageerror', (e) => erreurs403.push(e.message));
      await ouvrirDashboard(page, serveur.base, 'contacts');
      // On laisse le socle de chargement conclure.
      await page.waitForTimeout(3000);

      const corps = await page.locator('body').innerText();
      verifier('S7.1 aucune donnee personnelle n\'apparait apres un 403',
        !corps.includes('Bintou Membre') && !corps.includes('bintou@example.test')
        && !corps.includes('+41760000002'),
        'une donnee de la fixture a fuite dans le DOM');
      verifier('S7.2 aucun badge « Membre » n\'est rendu apres un 403',
        (await page.locator('[data-testid="badge-membre"]').count()) === 0);
      verifier('S7.3 l\'ecran ne plante pas (aucune erreur JavaScript non capturee)',
        erreurs403.length === 0, erreurs403.join(' | '));
      verifier('S7.4 le dashboard reste utilisable (navigation toujours presente)',
        (await page.locator('[data-testid="coach-nav-toggle"]').count()) === 1);
      verifier('S7.5 le refus est DIT, pas tu (message d\'erreur ou fin de session)',
        (await page.locator('[data-testid="erreur-contacts-contacts"]').count()) === 1
        || /session|expir|refus|erreur|reconnect/i.test(corps),
        'ecran muet : ni message d\'erreur ni invitation a se reconnecter');
      await capture(page, 's7-contacts-403');
      await contexte.close();
      etat.statutContacts = 200;
    }

    // === S8 — LA CASE « OUVRE UNE ADHESION D'UN AN » EXISTE ================
    {
      etat.offers = [OFFRE_ENTREE];
      const { contexte } = await nouveauContexte(navigateur, serveur.base, 1280, 1000);
      const page = await contexte.newPage();
      page.on('pageerror', (e) => erreursPage.push(`s8: ${e.message}`));
      await ouvrirDashboard(page, serveur.base, 'offers');
      await page.click('text=Offres & Cours');
      await page.waitForSelector('text=+ NOUVELLE OFFRE', { timeout: 20000 });
      await page.click('text=+ NOUVELLE OFFRE');
      const casePw = page.locator('[data-testid="offer-creates-membership"]');
      let presente = false;
      try { await casePw.waitFor({ state: 'visible', timeout: 10000 }); presente = true; } catch (e) { /* mesure */ }
      verifier('S8.1 la case [data-testid="offer-creates-membership"] existe et est visible',
        presente, 'case introuvable dans le formulaire d\'offre');
      if (presente) {
        verifier('S8.2 c\'est bien une case a cocher',
          (await casePw.getAttribute('type')) === 'checkbox');
        verifier('S8.3 elle est DECOCHEE par defaut (aucune offre ne devient adherente seule)',
          (await casePw.isChecked()) === false);
        const libelle = await page.locator('label', { has: casePw }).innerText();
        verifier('S8.4 le libelle annonce « Ouvre une adhésion d\'un an »',
          /Ouvre une adh[ée]sion d['’]un an/i.test(libelle), `lu : ${libelle}`);
        // LOT 2.1 : une offre NEUVE nait a 0 CHF, et la case y est desormais
        // DESACTIVEE — une offre gratuite ne peut pas ouvrir une adhesion.
        // On verifie ce garde-fou, puis on donne un prix a l'offre : la case
        // redevient utilisable. C'est exactement le geste du coach.
        verifier('S8.4b a 0 CHF la case est desactivee (offre gratuite)',
          (await casePw.isDisabled()) === true);
        verifier('S8.4c ... et l\'explication est affichee',
          (await page.locator('[data-testid="offer-membership-gratuite"]').count()) === 1);
        await page.getByPlaceholder('30').first().fill('250');
        await page.waitForTimeout(300);
        verifier('S8.4d des qu\'un prix est saisi, la case redevient utilisable',
          (await casePw.isDisabled()) === false);
        await casePw.check();
        verifier('S8.5 la case est reellement cochable', (await casePw.isChecked()) === true);
      } else {
        verifier('S8.2 c\'est bien une case a cocher', false, 'case absente');
        verifier('S8.3 elle est DECOCHEE par defaut', false, 'case absente');
        verifier('S8.4 le libelle annonce « Ouvre une adhésion d\'un an »', false, 'case absente');
        verifier('S8.5 la case est reellement cochable', false, 'case absente');
      }
      await capture(page, 's8-case-adhesion-offre');
      await contexte.close();
    }

    // === S9 — INNOCUITE : rien n'a ete ecrit, rien n'est sorti ============
    {
      // Le dashboard tente de lui-meme quelques ecritures au chargement
      // (`POST /sanitize-data`, autosave `PUT /concept`, `PUT /payment-links`).
      // Ce test ne les provoque pas et ne peut pas les empecher ; ce qu'il
      // GARANTIT, c'est qu'aucune n'aboutit — le bouchon les refuse toutes en
      // 405 — et qu'aucune ne vise un chemin sensible.
      const ecritures = serveur.journal.filter((l) => l.methode !== 'GET' && l.chemin.startsWith('/api/'));
      const abouties = ecritures.filter((e) => e.statut !== 405);
      verifier('S9.1 aucune ecriture n\'a abouti (toutes refusees en 405)',
        abouties.length === 0, abouties.map((e) => `${e.methode} ${e.chemin}`).join(', '));
      const sensibles = ecritures.filter((e) => /checkout|payment-intent|stripe|pawapay|cinetpay|order|subscription|adhesion|reservation|contacts|offers/i.test(e.chemin));
      verifier('S9.1b aucune ecriture n\'a vise un paiement, une adhesion, une offre ou un contact',
        sensibles.length === 0, sensibles.map((e) => `${e.methode} ${e.chemin}`).join(', '));
      const spontanees = [...new Set(ecritures.map((e) => `${e.methode} ${e.chemin}`))];
      resultats.push({ nom: `S9.1c ecritures tentees SPONTANEMENT par l'app, toutes refusees : ${spontanees.join(', ') || 'aucune'}`, ok: null, detail: '' });
      verifier('S9.2 aucune erreur JavaScript non capturee sur les parcours nominaux',
        erreursPage.length === 0, erreursPage.slice(0, 3).join(' | '));
      // Si le bundle avait ete construit avec `REACT_APP_BACKEND_URL=https://afroboost.com`
      // (valeur de `frontend/.env.local`), les appels seraient partis vers la
      // PRODUCTION. Ils seraient coupes par le navigateur, mais ce test doit le
      // DIRE plutot que de le taire : un tel bundle ne prouverait plus rien.
      const fuites = bloqueesGlobal.filter((u) => u.includes('/api/'));
      verifier('S9.3 aucun appel API n\'a tente de sortir vers un autre hote',
        fuites.length === 0,
        `bundle mal construit ? ${[...new Set(fuites)].slice(0, 3).join(', ')}`);
    }

    // === CE QUI N'EST PAS COUVERT, ET QUI DOIT SE VOIR ====================
    nonTeste('X1 la creation reelle de l\'adhesion a l\'achat (regle serveur)',
      'le backend ne peut pas tourner ici (Python 3.9, FastAPI absent, MONGO_URL requis) : '
      + 'les reponses /api sont des fixtures. Couverture serveur = tests Python.');
    nonTeste('X2 le parcours de paiement (Stripe / PawaPay) de bout en bout',
      'interdit par la consigne : aucun paiement ne doit etre declenche.');
    nonTeste('X3 le calcul serveur du statut (active / future / expiree) a partir des dates',
      'ce test affiche le statut recu ; il ne le derive pas. Voir tests/test_p1bisa_adhesions.py.');
    nonTeste('X4 la persistance de `creates_membership` (PUT /offers)',
      'toute ecriture est refusee par le bouchon (405) : seule la presence et le '
      + 'comportement de la case sont mesures, pas son enregistrement.');
  } finally {
    await navigateur.close();
    await serveur.arreter();
  }
}

// ---------------------------------------------------------------------------
// 5. Rapport.
// ---------------------------------------------------------------------------

principal()
  .then(() => {
    const largeur = Math.max(...resultats.map((r) => r.nom.length), 40);
    console.log('\n╔' + '═'.repeat(largeur + 14) + '╗');
    console.log('║ LOT 2 — PREUVES EN NAVIGATEUR REEL' + ' '.repeat(largeur - 21) + '║');
    console.log('╚' + '═'.repeat(largeur + 14) + '╝');
    let echecs = 0;
    for (const r of resultats) {
      const etiquette = r.ok === null ? 'NON TESTE' : r.ok ? '   OK    ' : '  ECHEC  ';
      if (r.ok === false) echecs += 1;
      console.log(`[${etiquette}] ${r.nom.padEnd(largeur)}${r.detail ? '  <- ' + r.detail : ''}`);
      if (r.ok === null && r.detail) console.log(' '.repeat(13) + '  ' + r.detail);
    }
    const ok = resultats.filter((r) => r.ok === true).length;
    console.log(`\n${ok} OK · ${echecs} ECHEC · ${resultats.filter((r) => r.ok === null).length} non teste`);
    console.log('Captures : ' + CAPTURES);
    process.exit(echecs === 0 ? 0 : 1);
  })
  .catch((e) => {
    console.error('\nARRET BRUTAL :', e && e.stack ? e.stack : e);
    process.exit(2);
  });
