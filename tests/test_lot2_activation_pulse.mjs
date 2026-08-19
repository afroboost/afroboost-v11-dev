/**
 * VERIFICATION NAVIGATEUR — ACTIVATION DE `creates_membership` SUR PULSE x10.
 *
 * CE QUE CE TEST PROUVE, ET QUE `test_lot2_navigateur.mjs` NE PROUVAIT PAS
 * ------------------------------------------------------------------------
 * Le test LOT 2 existant ouvre une offre NEUVE et verifie que la case existe,
 * qu'elle est decochee par defaut et qu'elle est cochable. Il declarait
 * lui-meme un point non teste : « X4 la persistance de `creates_membership` ».
 * C'est exactement ce trou que ce fichier comble, sur le seul cas qui compte
 * aujourd'hui : l'EDITION d'une offre EXISTANTE dont le flag est deja pose en
 * base de production.
 *
 * LA DONNEE EST CELLE DE LA PRODUCTION, PAS UNE FIXTURE
 * ----------------------------------------------------
 * Les offres sont lues en Node, AVANT le lancement du navigateur, sur
 * `https://afroboost.com/api/offers` — une route publique, en LECTURE SEULE,
 * sans aucun identifiant. Elles sont ensuite servies telles quelles par le
 * serveur bouchon. Une fixture ecrite a la main prouverait que le composant
 * sait afficher une case cochee ; servir le document REEL prouve en plus que
 * c'est bien la valeur posee en base qui coche cette case.
 *
 * CE QU'IL N'ECRIT NULLE PART
 * ---------------------------
 * Aucune ecriture : le bouchon refuse tout ce qui n'est pas un GET (405) et le
 * consigne. Aucun paiement. Aucun client cree. Le navigateur ne peut joindre
 * que 127.0.0.1.
 *
 *   node tests/test_lot2_activation_pulse.mjs
 *   node tests/test_lot2_activation_pulse.mjs --sans-build   (bundle reutilise)
 */
import fs from 'fs';
import os from 'os';
import path from 'path';
import { fileURLToPath } from 'url';
import { createRequire } from 'module';
import { demarrer, etatInitial, EMAIL_COACH } from './serveur_bouchon_lot2.mjs';

const require_ = createRequire(import.meta.url);
const CHEMIN_PLAYWRIGHT = '/Users/afroboost/.claude/skills/gstack/node_modules/playwright-core';
const { chromium } = require_(CHEMIN_PLAYWRIGHT);

const RACINE = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const TRAVAIL = path.join(os.tmpdir(), 'afroboost-lot2-navigateur');
const BUILD = path.join(TRAVAIL, 'build');
const CAPTURES = path.join(TRAVAIL, 'captures-activation');

/** Les trois offres nommement citees dans la demande. La verification porte
 *  sur le NOM, jamais sur le prix : le jour ou « Membres » passe a 160 CHF, ce
 *  test doit continuer a dire la meme chose. */
const CIBLE_ATTENDUE = 'PULSE x10 cours';
const TEMOINS_ATTENDUS_DECOCHES = [/essai/i, /^Membres$/i];

const resultats = [];
function verifier(titre, condition, detail) {
  resultats.push({ titre, ok: !!condition, detail: detail || '' });
  console.log(`${condition ? '  OK  ' : ' ECHEC'} ${titre}${condition || !detail ? '' : ` — ${detail}`}`);
}

async function offresDeProduction() {
  const r = await fetch('https://afroboost.com/api/offers');
  if (!r.ok) throw new Error(`lecture des offres de production: HTTP ${r.status}`);
  const corps = await r.json();
  const liste = Array.isArray(corps) ? corps : corps.offers;
  if (!Array.isArray(liste) || !liste.length) throw new Error('aucune offre lue en production');
  return liste;
}

/** Jeton NON signe, valide en forme seulement : il ne quitte jamais
 *  127.0.0.1 et le bouchon ne verifie aucune signature. */
function jetonFactice(email) {
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
  const exp = Math.floor(Date.now() / 1000) + 3600 * 24 * 30;
  return `${b64({ alg: 'HS256', typ: 'JWT' })}.${b64({ email, sub: email, exp })}.signature-factice`;
}

async function nouveauContexte(navigateur, base) {
  const contexte = await navigateur.newContext({
    viewport: { width: 1280, height: 1000 },
    baseURL: base,
  });
  // Ceinture ET bretelles : rien ne sort de 127.0.0.1 — ni PostHog, ni
  // Cloudinary, ni la production. Et `/sw.js` est coupe net : le Service
  // Worker rejouerait un bundle en cache et le test mesurerait un fantome.
  const hote = new URL(base).host;
  await contexte.route('**/*', (route) => {
    const u = new URL(route.request().url());
    if (u.host !== hote) return route.abort();
    if (u.pathname === '/sw.js') return route.abort();
    return route.continue();
  });
  await contexte.addInitScript(
    ([email, jeton]) => {
      localStorage.setItem('afroboost_coach_mode', 'true');
      localStorage.setItem('afroboost_coach_user', JSON.stringify({ email, name: 'Coach Test' }));
      localStorage.setItem('afroboost_jwt', jeton);
    },
    [EMAIL_COACH, jetonFactice(EMAIL_COACH)]
  );
  return contexte;
}

async function capture(page, nom) {
  fs.mkdirSync(CAPTURES, { recursive: true });
  const chemin = path.join(CAPTURES, `${nom}.png`);
  await page.screenshot({ path: chemin, fullPage: false });
  return chemin;
}

/** Ouvre le formulaire d'edition d'une offre et rend l'etat de la case. */
async function lireCaseDeLOffre(page, base, offre) {
  await page.goto(`${base}/#partner-dashboard`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('[data-testid="coach-nav-toggle"]', { timeout: 30000 });
  await page.click('[data-testid="coach-nav-toggle"]');
  await page.click('[data-testid="coach-tab-offers"]');
  await page.waitForSelector('[data-testid="offers-search-input"]', { timeout: 20000 });
  // V224 : les cartes d'offres sont rendues par `OfferCard`, qui ne porte AUCUN
  // data-testid — l'ancien rendu qui en avait un est mort (`{false && ...}`,
  // OffersManager.js:670). On cible donc le titre affiche, puis le bouton
  // « Modifier » de SA carte. Aucun code produit n'est modifie pour ce test.
  const titre = page.locator('h3', { hasText: (offre.name || '').trim() }).first();
  const bouton = titre.locator(
    'xpath=ancestor::div[contains(@class,"transition-all")][1]'
  ).getByRole('button', { name: 'Modifier' }).first();
  try {
    await bouton.waitFor({ state: 'attached', timeout: 20000 });
    await bouton.scrollIntoViewIfNeeded();
    await bouton.waitFor({ state: 'visible', timeout: 10000 });
  } catch (e) {
    const vus = await page.locator('h3').evaluateAll(
      (ns) => ns.map((n) => n.textContent.trim()).slice(0, 30));
    await capture(page, 'diagnostic-liste-offres');
    throw new Error(`carte introuvable pour « ${offre.name} ».\n  titres h3 vus : ${JSON.stringify(vus)}`);
  }
  await bouton.click();
  const casePw = page.locator('[data-testid="offer-creates-membership"]');
  await casePw.waitFor({ state: 'visible', timeout: 15000 });
  // ATTENDRE QUE LE FORMULAIRE SOIT REELLEMENT GARNI avant de lire la case.
  // `startEditOffer` remplit l'etat du parent, le wizard le recopie dans un
  // effet : lire trop tot mesurerait un formulaire encore vierge et
  // accuserait a tort. Le champ « Nom de l'offre » sert de temoin.
  // Le champ « Nom de l'offre » DU MODAL, cible par son placeholder : viser
  // `input` tout court attraperait la barre de recherche des offres, qui est
  // vide par nature et ferait croire a un formulaire vierge.
  const champNom = page.getByPlaceholder("Ex: Cours à l'unité").first();
  let nomLu = '';
  for (let i = 0; i < 40; i += 1) {
    nomLu = await champNom.inputValue().catch(() => '<champ introuvable>');
    if (nomLu && nomLu !== '<champ introuvable>' && nomLu.trim()) break;
    await page.waitForTimeout(250);
  }
  const prixLu = await page.getByPlaceholder('0.00').first().inputValue().catch(() => '<absent>');
  return {
    nomDansLeFormulaire: nomLu,
    prixDansLeFormulaire: prixLu,
    cochee: await casePw.isChecked(),
    libelle: await page.locator('label', { has: casePw }).innerText(),
  };
}

async function principal() {
  if (!fs.existsSync(path.join(BUILD, 'index.html'))) {
    throw new Error(`bundle absent dans ${BUILD} — lancer d'abord tests/test_lot2_navigateur.mjs`);
  }

  console.log('· lecture des offres REELLES de production (GET public, lecture seule)…');
  const offres = await offresDeProduction();
  const cible = offres.find((o) => (o.name || '').trim() === CIBLE_ATTENDUE);
  if (!cible) throw new Error(`offre « ${CIBLE_ATTENDUE} » absente de la production`);

  console.log(`· ${offres.length} offres lues. Etat du flag tel que la PRODUCTION le renvoie :`);
  for (const o of offres) console.log(`    ${String(o.creates_membership).padEnd(6)} ${(o.name || '').trim()}`);

  const etat = etatInitial();
  etat.offers = offres;
  const serveur = await demarrer({ racine: BUILD, etat });
  const navigateur = await chromium.launch({ headless: true });
  const erreursPage = [];
  const traceReseau = [];

  try {
    // === A — L'OFFRE CIBLE PORTE LA CASE COCHEE ============================
    {
      const contexte = await nouveauContexte(navigateur, serveur.base);
      const page = await contexte.newPage();
      page.on('pageerror', (e) => erreursPage.push(`A: ${e.message}`));
      page.on('console', (m) => { if (m.type() === 'error') erreursPage.push(`console: ${m.text().slice(0, 200)}`); });
      page.on('response', (r) => {
        if (r.url().includes('/api/')) traceReseau.push(`${r.status()} ${new URL(r.url()).pathname}${new URL(r.url()).search}`);
      });
      let lu;
      try {
        lu = await lireCaseDeLOffre(page, serveur.base, cible);
      } catch (e) {
        throw new Error(`${e.message}\n  appels /api/ : ${JSON.stringify(traceReseau)}\n  erreurs page : ${JSON.stringify(erreursPage.slice(0, 8))}`);
      }
      verifier(`A1 « ${CIBLE_ATTENDUE} » : la case est COCHEE a l'ouverture du formulaire`,
        lu.cochee === true, `isChecked() = ${lu.cochee}`);
      verifier('A2 le libelle lu a l\'ecran est bien « Ouvre une adhésion d\'un an »',
        /Ouvre une adh[ée]sion d['’]un an/i.test(lu.libelle), `lu : ${lu.libelle.replace(/\n/g, ' / ')}`);
      verifier("A0 le formulaire s'ouvre GARNI avec l'offre (temoin : champ Nom)",
        (lu.nomDansLeFormulaire || '').trim() === CIBLE_ATTENDUE,
        `champ Nom lu : ${JSON.stringify(lu.nomDansLeFormulaire)} · champ Prix lu : ${JSON.stringify(lu.prixDansLeFormulaire)} — vides = le wizard s'ouvre vierge`);
      verifier('A3 la valeur affichee vient de la production, pas d\'une fixture',
        cible.creates_membership === true,
        `l'API de production renvoie creates_membership = ${cible.creates_membership}`);
      console.log('    capture : ' + await capture(page, 'a-pulse-formulaire-reouvert'));
      await contexte.close();
    }

    // === B — LES AUTRES OFFRES NE LA PORTENT PAS ===========================
    for (const motif of TEMOINS_ATTENDUS_DECOCHES) {
      const temoin = offres.find((o) => motif.test((o.name || '').trim()));
      if (!temoin) { verifier(`B0 offre temoin ${motif} presente en production`, false, 'introuvable'); continue; }
      const contexte = await nouveauContexte(navigateur, serveur.base);
      const page = await contexte.newPage();
      page.on('pageerror', (e) => erreursPage.push(`B: ${e.message}`));
      const lu = await lireCaseDeLOffre(page, serveur.base, temoin);
      verifier(`B1 « ${temoin.name.trim()} » : la case est DECOCHEE a l'ecran`,
        lu.cochee === false, `isChecked() = ${lu.cochee}`);
      verifier(`B2 « ${temoin.name.trim()} » : la production la renvoie a false`,
        temoin.creates_membership !== true,
        `creates_membership = ${temoin.creates_membership}`);
      console.log('    capture : ' + await capture(page, `b-temoin-${temoin.id.slice(0, 8)}`));
      await contexte.close();
    }

    // === C — UNE SEULE OFFRE PORTE LE FLAG, SUR TOUTE LA PRODUCTION ========
    {
      const porteuses = offres.filter((o) => o.creates_membership === true).map((o) => (o.name || '').trim());
      verifier('C1 exactement UNE offre porte le flag sur toute la production',
        porteuses.length === 1, `porteuses = ${JSON.stringify(porteuses)}`);
      verifier('C2 et c\'est bien celle demandee',
        porteuses.length === 1 && porteuses[0] === CIBLE_ATTENDUE, `lu : ${porteuses[0]}`);
    }

    // === D — AUCUNE ECRITURE DECLENCHEE PAR CE TEST ========================
    {
      // Le bouchon journalise TOUTES les requetes. Ce qui compte ici : aucune
      // ECRITURE ne doit avoir abouti. On isole donc les non-GET et on verifie
      // qu'ils ont tous ete refuses (405). Le seul present est un
      // `POST /api/sanitize-data` emis par l'application elle-meme au
      // chargement du dashboard — pas par ce test — et il est refuse.
      const nonGet = (serveur.journal || []).filter((e) => e.methode !== 'GET');
      const aboutis = nonGet.filter((e) => e.statut < 400);
      verifier('D1 aucune ecriture n\'a abouti (tout non-GET est refuse par le bouchon)',
        aboutis.length === 0, `abouties : ${JSON.stringify(aboutis)}`);
      const ecrituresSensibles = nonGet.filter(
        (e) => /\/api\/(offers|memberships)/.test(e.chemin));
      verifier('D2 aucune ecriture tentee sur les offres ni sur les adhesions',
        ecrituresSensibles.length === 0,
        `tentatives : ${JSON.stringify(ecrituresSensibles)}`);
      // Les autres non-GET sont des auto-sauvegardes que l'application declenche
      // seule au chargement du dashboard (concept, liens de paiement,
      // sanitize-data). Toutes refusees en 405 : on les NOMME plutot que de les
      // taire, mais elles ne concernent pas ce lot.
      console.log('    non-GET emis par l\'application, tous refuses : '
        + JSON.stringify([...new Set(nonGet.map((e) => `${e.methode} ${e.chemin} -> ${e.statut}`))]));
      // Les erreurs console attendues sont les ressources que le test coupe
      // VOLONTAIREMENT (`/sw.js`, hors-origine) et le 405 ci-dessus. Toute
      // autre erreur serait un vrai defaut d'ecran.
      const bruitAttendu = /ERR_FAILED|fetching the script|405 \(Method Not Allowed\)|sanitize-data|auto-save concept|auto-save payment links|payment-links/i;
      const vraiesErreurs = erreursPage.filter((e) => !bruitAttendu.test(e));
      verifier('D3 aucune erreur JavaScript imprevue sur les ecrans traverses',
        vraiesErreurs.length === 0, vraiesErreurs.slice(0, 5).join(' | '));
    }
  } finally {
    await navigateur.close();
    await serveur.arreter();
  }

  const echecs = resultats.filter((r) => !r.ok);
  console.log(`\n${resultats.length - echecs.length} OK · ${echecs.length} ECHEC(S) · captures dans ${CAPTURES}`);
  if (echecs.length) {
    for (const e of echecs) console.log(`  ECHEC ${e.titre} — ${e.detail}`);
    process.exit(1);
  }
}

principal().catch((e) => { console.error('ERREUR:', e.message); process.exit(1); });
