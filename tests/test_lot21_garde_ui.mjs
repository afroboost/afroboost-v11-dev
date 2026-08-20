/**
 * LOT 2.1 — LE GARDE-FOU VISUEL : UNE OFFRE GRATUITE N'OUVRE PAS D'ADHESION.
 *
 * Le VRAI bundle React, servi par le serveur bouchon, nourri avec les offres
 * REELLES de production (lues en LECTURE SEULE sur la route publique).
 *
 * Ce que ce test verrouille, et que le backend ne peut pas dire a la place de
 * l'interface : le coach doit COMPRENDRE, au moment ou il configure son offre,
 * pourquoi la case ne repond pas. Une garde serveur silencieuse le laisserait
 * cocher une case sans effet, et decouvrir le probleme le jour d'un achat.
 *
 * Le scenario suit le geste reel : mettre le prix a 0 sur une offre qui portait
 * le reglage, puis le redonner. Le reglage ne doit PAS etre efface en chemin —
 * sinon le coach le perd sans s'en apercevoir.
 *
 * Aucune ecriture : le bouchon refuse tout ce qui n'est pas un GET.
 *
 *   node tests/test_lot21_garde_ui.mjs
 */
import fs from 'fs';
import os from 'os';
import path from 'path';
import { createRequire } from 'module';
import { demarrer, etatInitial, EMAIL_COACH } from './serveur_bouchon_lot2.mjs';

const require_ = createRequire(import.meta.url);
const { chromium } = require_('/Users/afroboost/.claude/skills/gstack/node_modules/playwright-core');

// AFROBOOST_BUNDLE permet de viser le bundle REELLEMENT SERVI par la
// production plutot qu'une reconstruction locale : c'est ce qui transforme ce
// test en verification de ce qui est EN LIGNE.
const BUILD = process.env.AFROBOOST_BUNDLE
  || path.join(os.tmpdir(), 'afroboost-lot2-navigateur', 'build');
const CAPTURES = path.join(os.tmpdir(), 'afroboost-lot2-navigateur', 'captures-lot21');

const PULSE = 'PULSE x10 cours';          // 250 CHF, case cochee
const GRATUITE = "🎁 Cours d'essai GRATUIT";  // 0 CHF

const resultats = [];
function verifier(titre, condition, detail) {
  resultats.push({ titre, ok: !!condition, detail: detail || '' });
  console.log(`${condition ? '  OK  ' : ' ECHEC'} ${titre}${condition || !detail ? '' : ` — ${detail}`}`);
}

async function offresDeProduction() {
  const r = await fetch('https://afroboost.com/api/offers');
  if (!r.ok) throw new Error(`lecture des offres de production: HTTP ${r.status}`);
  const c = await r.json();
  const l = Array.isArray(c) ? c : c.offers;
  if (!Array.isArray(l) || !l.length) throw new Error('aucune offre lue');
  return l;
}

function jetonFactice(email) {
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
  const exp = Math.floor(Date.now() / 1000) + 3600 * 24 * 30;
  return `${b64({ alg: 'HS256', typ: 'JWT' })}.${b64({ email, sub: email, exp })}.signature-factice`;
}

async function contexte(navigateur, base) {
  const ctx = await navigateur.newContext({ viewport: { width: 1280, height: 1000 }, baseURL: base });
  const hote = new URL(base).host;
  await ctx.route('**/*', (route) => {
    const u = new URL(route.request().url());
    if (u.host !== hote) return route.abort();
    if (u.pathname === '/sw.js') return route.abort();
    return route.continue();
  });
  await ctx.addInitScript(([e, j]) => {
    localStorage.setItem('afroboost_coach_mode', 'true');
    localStorage.setItem('afroboost_coach_user', JSON.stringify({ email: e, name: 'Coach Test' }));
    localStorage.setItem('afroboost_jwt', j);
  }, [EMAIL_COACH, jetonFactice(EMAIL_COACH)]);
  return ctx;
}

async function capture(page, nom) {
  fs.mkdirSync(CAPTURES, { recursive: true });
  const c = path.join(CAPTURES, `${nom}.png`);
  await page.screenshot({ path: c, fullPage: false });
  return c;
}

async function ouvrirOffre(page, base, nom) {
  await page.goto(`${base}/#partner-dashboard`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('[data-testid="coach-nav-toggle"]', { timeout: 30000 });
  await page.click('[data-testid="coach-nav-toggle"]');
  await page.click('[data-testid="coach-tab-offers"]');
  await page.waitForSelector('[data-testid="offers-search-input"]', { timeout: 20000 });
  const titre = page.locator('h3', { hasText: nom }).first();
  const bouton = titre.locator('xpath=ancestor::div[contains(@class,"transition-all")][1]')
    .getByRole('button', { name: 'Modifier' }).first();
  await bouton.waitFor({ state: 'attached', timeout: 20000 });
  await bouton.scrollIntoViewIfNeeded();
  await bouton.click();
  // TEMOIN DE GARNISSAGE : le champ « Nom », surtout pas le prix. Un prix
  // affiche « 0 » est une valeur NON VIDE : s'en servir ferait sortir la
  // boucle sur un formulaire encore vierge, et le test mesurerait une case
  // desactivee a tort (defaut constate le 20/08/2026).
  const champNom = page.getByPlaceholder("Ex: Cours à l'unité").first();
  for (let i = 0; i < 40; i += 1) {
    const v = await champNom.inputValue().catch(() => '');
    if ((v || '').trim() === nom.trim()) break;
    await page.waitForTimeout(250);
  }
  return page.getByPlaceholder('30').first();
}

async function principal() {
  if (!fs.existsSync(path.join(BUILD, 'index.html'))) {
    throw new Error(`bundle absent dans ${BUILD} — lancer d'abord tests/test_lot2_navigateur.mjs`);
  }
  console.log('· lecture des offres REELLES de production (GET public, lecture seule)…');
  const etat = etatInitial();
  etat.offers = await offresDeProduction();

  const serveur = await demarrer({ racine: BUILD, etat });
  const navigateur = await chromium.launch({ headless: true });
  const erreurs = [];
  const casePw = (p) => p.locator('[data-testid="offer-creates-membership"]');
  const message = (p) => p.locator('[data-testid="offer-membership-gratuite"]');

  try {
    // === A — PULSE x10 : RIEN NE CHANGE POUR UNE OFFRE PAYANTE ===========
    {
      const ctx = await contexte(navigateur, serveur.base);
      const page = await ctx.newPage();
      page.on('pageerror', (e) => erreurs.push(`A: ${e.message}`));
      const champPrix = await ouvrirOffre(page, serveur.base, PULSE);
      verifier('A1 « PULSE x10 » : la case est COCHEE', (await casePw(page).isChecked()) === true);
      verifier('A2 ... et UTILISABLE (offre payante)', (await casePw(page).isDisabled()) === false);
      verifier('A3 ... et aucun avertissement n\'est affiche',
        (await message(page).count()) === 0);
      console.log('    capture : ' + await capture(page, 'a-pulse-payante'));

      // --- le coach ramene le prix a 0 -------------------------------------
      await champPrix.fill('0');
      await page.waitForTimeout(400);
      verifier('A4 prix ramene a 0 -> la case devient DESACTIVEE',
        (await casePw(page).isDisabled()) === true);
      verifier('A5 ... et elle n\'apparait plus cochee (le reglage ne s\'applique pas)',
        (await casePw(page).isChecked()) === false);
      const txt = (await message(page).innerText().catch(() => '')) || '';
      verifier('A6 ... et l\'explication est affichee au coach',
        /Une offre gratuite ne peut pas ouvrir une adh[ée]sion/i.test(txt),
        `lu : ${JSON.stringify(txt.slice(0, 120))}`);
      verifier('A7 ... en l\'avertissant que SON reglage etait actif',
        /r[ée]glage [ée]tait activ[ée]/i.test(txt), `lu : ${JSON.stringify(txt.slice(0, 160))}`);
      // Amener le message a l'ecran : dans un modal defilant il nait sous la
      // ligne de flottaison, et une capture le montrerait coupe.
      await message(page).scrollIntoViewIfNeeded().catch(() => {});
      await page.waitForTimeout(250);
      console.log('    capture : ' + await capture(page, 'b-prix-zero-avertissement'));

      // --- il redonne un prix ---------------------------------------------
      await champPrix.fill('250');
      await page.waitForTimeout(400);
      verifier('A8 prix redonne -> la case redevient utilisable',
        (await casePw(page).isDisabled()) === false);
      verifier('A9 ... et le reglage du coach n\'a PAS ete efface en chemin',
        (await casePw(page).isChecked()) === true);
      verifier('A10 ... et l\'avertissement disparait', (await message(page).count()) === 0);
      console.log('    capture : ' + await capture(page, 'c-prix-restaure'));
      await ctx.close();
    }

    // === B — UNE OFFRE REELLEMENT GRATUITE ==============================
    {
      const ctx = await contexte(navigateur, serveur.base);
      const page = await ctx.newPage();
      page.on('pageerror', (e) => erreurs.push(`B: ${e.message}`));
      await ouvrirOffre(page, serveur.base, GRATUITE);
      verifier('B1 « Cours d\'essai GRATUIT » : la case est DESACTIVEE',
        (await casePw(page).isDisabled()) === true);
      verifier('B2 ... et decochee', (await casePw(page).isChecked()) === false);
      verifier('B3 ... et l\'explication est affichee',
        (await message(page).count()) === 1);
      verifier('B4 ... SANS l\'avertissement « votre reglage etait actif » '
        + '(il ne l\'avait pas active)',
        !/r[ée]glage [ée]tait activ[ée]/i.test(await message(page).innerText()));
      // Un clic ne doit RIEN faire : c'est la garde, pas une decoration.
      await casePw(page).click({ force: true }).catch(() => {});
      await page.waitForTimeout(300);
      verifier('B5 un clic force sur la case ne la coche pas',
        (await casePw(page).isChecked()) === false);
      await message(page).scrollIntoViewIfNeeded().catch(() => {});
      await page.waitForTimeout(250);
      console.log('    capture : ' + await capture(page, 'd-offre-gratuite'));
      await ctx.close();
    }

    // === C — GARDE-FOUS TRANSVERSES =====================================
    {
      const nonGet = (serveur.journal || []).filter((e) => e.methode !== 'GET');
      verifier('C1 aucune ecriture sur les offres n\'a abouti',
        !nonGet.some((e) => /\/api\/offers/.test(e.chemin) && e.statut < 400),
        JSON.stringify(nonGet.filter((e) => /\/api\/offers/.test(e.chemin))));
      const bruit = /ERR_FAILED|fetching the script|405|sanitize-data|auto-save/i;
      const vraies = erreurs.filter((e) => !bruit.test(e));
      verifier('C2 aucune erreur JavaScript imprevue', vraies.length === 0,
        vraies.slice(0, 4).join(' | '));
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
