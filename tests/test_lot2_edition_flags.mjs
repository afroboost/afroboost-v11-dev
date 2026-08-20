/**
 * LOT 2 FIX — LES DEUX CASES SURVIVENT A L'EDITION D'UNE OFFRE.
 *
 * LE BUG QUE CE TEST VERROUILLE
 * -----------------------------
 * `startEditOffer` (CoachDashboard.js) rechargeait le nom, le prix, les
 * seances, la description… mais NI `creates_membership` NI
 * `first_purchase_eligible`. Rouvrir une offre qui portait `true` en base
 * affichait donc deux cases DECOCHEES, et comme `PUT /offers/{id}` fait un
 * `$set` du model_dump COMPLET, la premiere sauvegarde remettait les deux
 * champs a `false` en base. Perte silencieuse, sans message, sans trace.
 *
 * C'etait la SIXIEME occurrence du meme piege sur ce fichier (V223 paliers,
 * V225 libelles, V256 lien partenaire, V260 prix alternatif) — d'ou un test
 * dedie plutot qu'une simple relecture.
 *
 * LES DONNEES SONT CELLES DE LA PRODUCTION
 * ----------------------------------------
 * Les offres sont lues en Node, AVANT le navigateur, sur
 * `https://afroboost.com/api/offers` — route publique, LECTURE SEULE, sans
 * identifiant. Trois cas reels et complementaires y sont couverts :
 *
 *   PULSE x10 cours   creates_membership=true   first_purchase_eligible=true
 *   Cours a l'unite   creates_membership=false  first_purchase_eligible=true
 *   Membres           creates_membership=false  first_purchase_eligible=false
 *
 * Le cas MIXTE est le plus important : il interdit un « correctif » qui
 * cocherait les deux cases ensemble. Les deux champs doivent rester
 * independants.
 *
 * CE QUI N'EST JAMAIS TOUCHE
 * --------------------------
 * Aucune ecriture en base : la sauvegarde de l'etape 8 va au serveur bouchon,
 * qui fusionne en MEMOIRE (`persisterOffres: true`) et meurt avec le test.
 * Aucun paiement. Aucun client cree. Le navigateur ne peut joindre que
 * 127.0.0.1.
 *
 *   node tests/test_lot2_edition_flags.mjs
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

const TRAVAIL = path.join(os.tmpdir(), 'afroboost-lot2-navigateur');
// AFROBOOST_BUNDLE permet de viser un bundle AUTRE que celui construit ici —
// en pratique celui REELLEMENT SERVI par la production, aspire au prealable.
// Tester le code deploye vaut mieux que tester une reconstruction locale.
const BUILD = process.env.AFROBOOST_BUNDLE || path.join(TRAVAIL, 'build');
// `--sans-sauvegarde` s'arrete apres l'etape 6 (ouvrir / fermer / rouvrir) et
// n'enregistre RIEN. C'est le mode a utiliser contre un bundle de production :
// on verifie l'affichage sans jamais declencher d'ecriture.
const SANS_SAUVEGARDE = process.argv.includes('--sans-sauvegarde');
const CAPTURES = path.join(TRAVAIL, 'captures-edition');

/** Libelles REELS a l'ecran (OfferWizard.js). Le test lit ce que le coach lit. */
const LIBELLE_ADHESION = "Ouvre une adhésion d'un an";
const LIBELLE_CONVERSION = 'Proposer après la séance découverte';

/** Les trois offres, designees par leur NOM — jamais par leur prix. */
const CAS = [
  { nom: 'PULSE x10 cours', adhesion: true, conversion: true },
  { nom: "Cours à l'unité", adhesion: false, conversion: true },
  { nom: 'Membres', adhesion: false, conversion: false },
];

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

function jetonFactice(email) {
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
  const exp = Math.floor(Date.now() / 1000) + 3600 * 24 * 30;
  return `${b64({ alg: 'HS256', typ: 'JWT' })}.${b64({ email, sub: email, exp })}.signature-factice`;
}

async function nouveauContexte(navigateur, base) {
  const contexte = await navigateur.newContext({ viewport: { width: 1280, height: 1000 }, baseURL: base });
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

/** ETAPE 1 : Gestion > Offres. */
async function ouvrirEcranOffres(page, base) {
  await page.goto(`${base}/#partner-dashboard`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('[data-testid="coach-nav-toggle"]', { timeout: 30000 });
  await page.click('[data-testid="coach-nav-toggle"]');
  await page.click('[data-testid="coach-tab-offers"]');
  await page.waitForSelector('[data-testid="offers-search-input"]', { timeout: 20000 });
}

/** ETAPE 2 : ouvrir une offre en modification, et attendre qu'elle soit GARNIE.
 *  Les cartes (`OfferCard`) ne portent aucun data-testid : on passe par le
 *  titre affiche, puis par le bouton « Modifier » de SA carte. */
async function ouvrirOffre(page, nom) {
  const titre = page.locator('h3', { hasText: nom }).first();
  const bouton = titre
    .locator('xpath=ancestor::div[contains(@class,"transition-all")][1]')
    .getByRole('button', { name: 'Modifier' }).first();
  await bouton.waitFor({ state: 'attached', timeout: 20000 });
  await bouton.scrollIntoViewIfNeeded();
  await bouton.click();
  // Temoin de garnissage : le champ « Nom de l'offre » du MODAL. Lire les cases
  // avant que l'effet du wizard ait recopie l'offre mesurerait un formulaire
  // encore vierge et accuserait a tort.
  const champNom = page.getByPlaceholder("Ex: Cours à l'unité").first();
  for (let i = 0; i < 40; i += 1) {
    const v = await champNom.inputValue().catch(() => '');
    if ((v || '').trim()) break;
    await page.waitForTimeout(250);
  }
  return (await champNom.inputValue().catch(() => '')) || '';
}

async function lireLesDeuxCases(page) {
  const adhesion = page.locator('[data-testid="offer-creates-membership"]');
  const conversion = page.locator('[data-testid="offer-first-purchase-eligible"]');
  await adhesion.waitFor({ state: 'visible', timeout: 15000 });
  return {
    adhesion: await adhesion.isChecked(),
    conversion: await conversion.isChecked(),
    libelleAdhesion: await page.locator('label', { has: adhesion }).innerText(),
    libelleConversion: await page.locator('label', { has: conversion }).innerText(),
  };
}

/** ETAPE 4 : fermer SANS sauvegarder. */
async function fermerSansSauvegarder(page) {
  await page.getByRole('button', { name: 'Annuler' }).first().click();
  await page.locator('[data-testid="offer-creates-membership"]')
    .waitFor({ state: 'detached', timeout: 10000 });
}

/** ETAPES 7-8 : modifier un champ SANS RAPPORT, puis enregistrer.
 *  Le champ choisi est « Mots-cles » : il ne touche ni au prix, ni au
 *  checkout, ni aux seances, ni a aucune regle metier. */
async function modifierPuisEnregistrer(page, suffixe) {
  // Champ choisi : « Mots-cles » du wizard (etape 1). Il ne touche ni au prix,
  // ni aux seances, ni au checkout, ni a aucune regle metier — c'est bien un
  // champ SANS RAPPORT avec les deux cases. On traverse ensuite les trois
  // etapes jusqu'a « Enregistrer », ce qui eprouve aussi la traversee complete
  // du wizard.
  const motsCles = page.getByPlaceholder(/session, s[ée]ance, cardio/).first();
  try {
    await motsCles.waitFor({ state: 'visible', timeout: 15000 });
  } catch (e) {
    const vus = await page.locator('[data-testid]').evaluateAll(
      (ns) => ns.map((n) => n.getAttribute('data-testid')));
    await capture(page, 'diagnostic-mots-cles');
    throw new Error(`champ « Mots-cles » introuvable. data-testid a l'ecran : ${JSON.stringify(vus)}`);
  }
  await motsCles.scrollIntoViewIfNeeded();
  const avant = await motsCles.inputValue();
  await motsCles.fill(`${avant}${suffixe}`);
  for (let i = 0; i < 2; i += 1) {
    await page.getByRole('button', { name: /Suivant/ }).first().click();
    await page.waitForTimeout(400);
  }
  const enregistrer = page.getByRole('button', { name: 'Enregistrer' }).first();
  await enregistrer.waitFor({ state: 'visible', timeout: 10000 });
  await enregistrer.click();
  await page.locator('[data-testid="offer-creates-membership"]')
    .waitFor({ state: 'detached', timeout: 15000 });
  return `${avant}${suffixe}`;
}

async function principal() {
  if (!fs.existsSync(path.join(BUILD, 'index.html'))) {
    throw new Error(`bundle absent dans ${BUILD} — lancer d'abord `
      + `\`node tests/test_lot2_navigateur.mjs\` (sans --sans-build) pour le construire`);
  }

  console.log('· lecture des offres REELLES de production (GET public, lecture seule)…');
  const offres = await offresDeProduction();
  for (const cas of CAS) {
    const o = offres.find((x) => (x.name || '').trim() === cas.nom);
    if (!o) throw new Error(`offre « ${cas.nom} » absente de la production`);
    console.log(`    ${cas.nom} : creates_membership=${o.creates_membership} `
      + `first_purchase_eligible=${o.first_purchase_eligible}`);
    verifier(`P0 « ${cas.nom} » : la production porte bien les valeurs attendues`,
      o.creates_membership === cas.adhesion && o.first_purchase_eligible === cas.conversion,
      `lu : cm=${o.creates_membership} fpe=${o.first_purchase_eligible} `
      + `— attendu : cm=${cas.adhesion} fpe=${cas.conversion}`);
  }

  const etat = etatInitial();
  etat.offers = JSON.parse(JSON.stringify(offres));
  // Seule breche, explicite : la sauvegarde de l'etape 8, EN MEMOIRE.
  const serveur = await demarrer({ racine: BUILD, etat, persisterOffres: !SANS_SAUVEGARDE });
  const navigateur = await chromium.launch({ headless: true });
  const erreursPage = [];

  try {
    for (const cas of CAS) {
      const attendu = `adhesion=${cas.adhesion} conversion=${cas.conversion}`;
      const contexte = await nouveauContexte(navigateur, serveur.base);
      const page = await contexte.newPage();
      page.on('pageerror', (e) => erreursPage.push(`${cas.nom}: ${e.message}`));
      // `addOffer` conclut par un `alert()` : sans ce gestionnaire, la boite
      // bloquerait la page et tout le reste du scenario.
      page.on('dialog', (d) => d.accept().catch(() => {}));

      // --- ETAPES 1-3 : ouvrir, lire les deux cases ----------------------
      await ouvrirEcranOffres(page, serveur.base);
      const nomLu = await ouvrirOffre(page, cas.nom);
      verifier(`E2 « ${cas.nom} » : le formulaire s'ouvre garni`,
        nomLu.trim() === cas.nom, `champ Nom lu : ${JSON.stringify(nomLu)}`);
      const lu1 = await lireLesDeuxCases(page);
      verifier(`E3 « ${cas.nom} » : a la 1re ouverture, ${attendu}`,
        lu1.adhesion === cas.adhesion && lu1.conversion === cas.conversion,
        `lu : adhesion=${lu1.adhesion} conversion=${lu1.conversion}`);
      verifier(`E3b « ${cas.nom} » : les libelles a l'ecran sont les vrais`,
        lu1.libelleAdhesion.includes(LIBELLE_ADHESION)
        && lu1.libelleConversion.includes(LIBELLE_CONVERSION),
        `lus : ${JSON.stringify([lu1.libelleAdhesion, lu1.libelleConversion])}`);
      await capture(page, `1-${cas.nom.slice(0, 12)}-ouverture`);

      // --- ETAPES 4-6 : fermer sans sauvegarder, rouvrir -----------------
      await fermerSansSauvegarder(page);
      await ouvrirOffre(page, cas.nom);
      const lu2 = await lireLesDeuxCases(page);
      verifier(`E6 « ${cas.nom} » : apres fermeture SANS sauvegarde, ${attendu}`,
        lu2.adhesion === cas.adhesion && lu2.conversion === cas.conversion,
        `lu : adhesion=${lu2.adhesion} conversion=${lu2.conversion}`);

      if (SANS_SAUVEGARDE) {
        console.log('    capture : ' + await capture(page, `1-${cas.nom.slice(0, 12)}-reouverture`));
        await contexte.close();
        continue;
      }

      // --- ETAPES 7-8 : modifier un champ sans rapport, enregistrer ------
      const motsClesAttendus = await modifierPuisEnregistrer(page, ' lot2fix');
      const put = (serveur.journal || []).filter(
        (e) => e.methode === 'PUT' && e.chemin.startsWith('/api/offers/'));
      const dernier = put[put.length - 1];
      verifier(`E8 « ${cas.nom} » : l'enregistrement a bien emis un PUT /offers`,
        !!dernier, `PUT vus : ${put.length}`);
      const enBase = (etat.offers || []).find((o) => (o.name || '').trim() === cas.nom) || {};
      verifier(`E8b « ${cas.nom} » : le PUT a transmis les DEUX champs, ${attendu}`,
        enBase.creates_membership === cas.adhesion
        && enBase.first_purchase_eligible === cas.conversion,
        `recu cote serveur : cm=${enBase.creates_membership} fpe=${enBase.first_purchase_eligible}`);
      verifier(`E8c « ${cas.nom} » : le champ modifie a bien ete enregistre`,
        (enBase.keywords || '') === motsClesAttendus,
        `mots-cles cote serveur : ${JSON.stringify(enBase.keywords)}`);
      verifier(`E8d « ${cas.nom} » : le prix et les seances sont intacts`,
        enBase.price === (offres.find((o) => (o.name || '').trim() === cas.nom) || {}).price
        && enBase.pack_sessions === (offres.find((o) => (o.name || '').trim() === cas.nom) || {}).pack_sessions,
        `prix=${enBase.price} seances=${enBase.pack_sessions}`);

      // --- ETAPES 9-10 : rouvrir, les cases tiennent ---------------------
      await ouvrirOffre(page, cas.nom);
      const lu3 = await lireLesDeuxCases(page);
      verifier(`E10 « ${cas.nom} » : APRES enregistrement et reouverture, ${attendu}`,
        lu3.adhesion === cas.adhesion && lu3.conversion === cas.conversion,
        `lu : adhesion=${lu3.adhesion} conversion=${lu3.conversion}`);
      console.log('    capture : ' + await capture(page, `2-${cas.nom.slice(0, 12)}-apres-sauvegarde`));
      await contexte.close();
    }

    // --- Garde-fous transverses ----------------------------------------
    {
      const nonGet = (serveur.journal || []).filter((e) => e.methode !== 'GET');
      const horsOffres = nonGet.filter((e) => !/^\/api\/offers\//.test(e.chemin));
      verifier('G1 aucune ecriture hors des offres n\'a abouti',
        horsOffres.every((e) => e.statut >= 400),
        `abouties : ${JSON.stringify(horsOffres.filter((e) => e.statut < 400))}`);
      verifier('G2 aucune ecriture sur les adhesions',
        !nonGet.some((e) => e.chemin.includes('/memberships')),
        JSON.stringify(nonGet.filter((e) => e.chemin.includes('/memberships'))));
      const bruit = /ERR_FAILED|fetching the script|405 \(Method Not Allowed\)|sanitize-data|auto-save/i;
      const vraies = erreursPage.filter((e) => !bruit.test(e));
      verifier('G3 aucune erreur JavaScript imprevue', vraies.length === 0, vraies.slice(0, 5).join(' | '));
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
