/**
 * LOT 3b EN PRODUCTION, DRAPEAU ETEINT — LA PREUVE QUE RIEN N'A BOUGE.
 * ====================================================================
 *
 * CE QUE CE TEST PROUVE
 * ---------------------
 * LOT 3b (avantage tarifaire membre) est deploye en production avec
 * `MEMBER_PRICING_ENABLED = false`. La promesse d'un coupe-circuit eteint est
 * simple et totale : **le site se comporte EXACTEMENT comme avant**. Ce
 * fichier ne lit pas le code, il ouvre un vrai Chromium sur
 * https://afroboost.com et mesure ce que le visiteur voit et ce que le
 * navigateur envoie, en 1280x800 ET en 390x844.
 *
 * LECTURE SEULE STRICTE — ce qui est mecaniquement empeche
 * --------------------------------------------------------
 *   1. TOUTE requete non-GET est INTERCEPTEE et ABORTEE, quel que soit l'hote,
 *      apres consignation de son verbe, de son chemin et de son corps. Rien
 *      n'est ecrit en production ; on sait pourtant exactement ce que l'app a
 *      TENTE d'envoyer. `POST /api/tarif/estimation` fait exception au
 *      seul titre du COMPTAGE (voir plus bas) : il est lui aussi aborte.
 *   2. TOUTE navigation vers un hote autre qu'afroboost.com est ABORTEE :
 *      aucune page Stripe / TWINT / CinetPay / PawaPay ne peut s'ouvrir, meme
 *      si un clic y menait.
 *   3. Aucune donnee client n'est saisie, aucun formulaire n'est soumis.
 *
 * POURQUOI `/api/tarif/estimation` EST QUAND MEME ABORTE
 * ------------------------------------------------------
 * C'est une route de LECTURE (elle calcule un prix, n'enregistre rien) et la
 * consigne l'autorisait a passer. Mais ce que ce test doit prouver, c'est
 * qu'AUCUN appel n'est emis : le compteur est donc la mesure, et laisser
 * partir l'appel n'apporterait rien. On l'aborte, on le compte, on le publie.
 * Si le compteur n'est pas nul, le test ECHOUE — l'abort ne masque rien.
 *
 * CE QUI N'EST PAS TESTABLE ICI, ET QUI EST DIT COMME TEL
 * -------------------------------------------------------
 * Deux des huit offres de production portent `visible: false` : elles ne sont
 * PAS sur la vitrine. Leur prix a l'ecran est donc NON TESTABLE en navigateur.
 * Le fichier le declare « NON TESTE » avec la raison, et verifie a la place le
 * prix que l'API sert (`active_price` / `price`), qui est la source unique du
 * prix affiche (`v223UnitPrice`, App.js). Il n'ecrit JAMAIS « OK » a la place.
 *
 *   node tests/test_lot3b_production_dormant.mjs
 */
import fs from 'fs';
import os from 'os';
import path from 'path';
import { createRequire } from 'module';

const require_ = createRequire(import.meta.url);
// Playwright n'est PAS une dependance du projet : emprunte par chemin absolu,
// exactement comme les tests LOT 2 / LOT 3a / LOT 3b navigateur.
const { chromium } = require_('/Users/afroboost/.claude/skills/gstack/node_modules/playwright-core');

const BASE = process.env.AFROBOOST_BASE || 'https://afroboost.com';
const HOTE = new URL(BASE).host;
const CAPTURES = path.join(os.tmpdir(), 'afroboost-lot3b-production-dormant');

// ---------------------------------------------------------------------------
// LE CATALOGUE ATTENDU — releve AVANT le deploiement de LOT 3b.
// ---------------------------------------------------------------------------
// `prix` = le montant qui doit s'afficher a l'ecran (donc `active_price` quand
// l'offre est en tarif progressif, `price` sinon — c'est ce que fait
// `v223UnitPrice` dans App.js).
const CATALOGUE = [
  { cle: 'unite', id: 'fea0ab6a-8adc-460d-9d7d-bbff57059ca5',
    nom: "Cours à l'unité", prix: 30, payante: true, surVitrine: true },
  { cle: 'pulse', id: 'a687ce86-94d6-4ba9-a847-c8a20e787491',
    nom: 'PULSE x10 cours', prix: 250, payante: true, surVitrine: true },
  { cle: 'membres', id: '484c4519-15dc-4b86-8aa3-48e3c01c9645',
    nom: 'Membres', prix: 150, payante: true, surVitrine: true },
  { cle: 'tshirt', id: '84b7d8c6-b859-410a-8a09-0d1ee0069404',
    nom: 'T-shirt + 1 cours offert!', prix: 59.99, payante: true, surVitrine: true,
    // Garde V226 anterieure a LOT 3b : le bouton reste desactive tant qu'une
    // taille et une couleur ne sont pas choisies.
    boutonBloqueParVariante: true },
  { cle: 'vidy', id: '184e76e0-d3a0-4ba4-b63e-a6eb773bf8d7',
    nom: 'Silent Dance & Fitness au bord du Lac', prix: 33, payante: true,
    surVitrine: false, raisonAbsence: 'offre masquee en base (visible: false)' },
  { cle: 'silent', id: '76a78f31-614a-415a-876b-9d2d1a4b441c',
    nom: 'Afroboost Silent avec Bassi', prix: 15, payante: true, surVitrine: true },
  { cle: 'lakeside', id: '9fb0945a-5f16-482b-9662-fa4b8e28416b',
    nom: 'SILENT LAKESIDE', prix: 0, payante: false,
    surVitrine: false, raisonAbsence: 'offre masquee en base (visible: false)' },
  { cle: 'essai', id: 'c1e5f73c-0f16-402e-a746-2041e23f72e8',
    nom: "Cours d'essai GRATUIT", prix: 0, payante: false, surVitrine: true },
];

const TAILLES = [
  { cle: 'desktop', l: 1280, h: 800, titre: 'desktop 1280x800' },
  { cle: 'mobile', l: 390, h: 844, titre: 'mobile 390x844 (iPhone 12/13)' },
];

/**
 * Les SIGNATURES LOT 3b qui ne doivent apparaitre NULLE PART, drapeau eteint.
 *
 * ATTENTION, PIEGE MESURE PENDANT L'ECRITURE DE CE TEST : l'expression nue
 * « avantage membre » EST DEJA presente en production, dans la description
 * commerciale des offres « PULSE x10 cours » et « Membres » (« 🎁 Ton avantage
 * membre : … »), redigee par le proprietaire bien avant LOT 3b. Chercher la
 * simple expression donne donc un FAUX POSITIF sur chaque page. On cible ici la
 * signature EXACTE de la ligne d'interface (libelle + pourcentage sur la meme
 * ligne, « Avantage membre -50% ») et celle de l'invitation, jamais la phrase
 * seule. Le controle B5bis verifie separement qu'aucune occurrence nouvelle de
 * l'expression n'est apparue.
 */
const MOTS_INTERDITS = [
  { motif: /Avantage\s+membre\s*[-–]\s*\d+\s*%/i,
    quoi: 'ligne d\'interface « Avantage membre -N% »' },
  { motif: /Membre\s+Afroboost\s*\?\s*Ouvrez\s+votre\s+espace/i,
    quoi: 'invitation « Membre Afroboost ? Ouvrez votre espace »' },
  { motif: /Prix\s+public/i, quoi: 'ligne « Prix public » (barree)' },
  { motif: /votre_tarif|avantage_pct|member_discount_pct|identification_requise/i,
    quoi: 'nom de champ technique LOT 3b' },
];

// ---------------------------------------------------------------------------
// JOURNAL
// ---------------------------------------------------------------------------
const resultats = [];
const nonTestes = [];
const ecrituresAbortees = [];   // toutes les requetes non-GET interceptees
const navigationsBloquees = [];
const navigationsHorsSite = [];  // navigations qui ont REELLEMENT abouti ailleurs
const reponses5xx = [];
const erreursJs = [];
let appelsEstimation = 0;

function verifier(titre, condition, detail) {
  const ok = !!condition;
  resultats.push({ titre, ok, detail: detail || '' });
  console.log(`${ok ? '  OK   ' : ' ECHEC '} ${titre}${ok || !detail ? '' : ` — ${detail}`}`);
}

function nonTeste(titre, raison) {
  nonTestes.push({ titre, raison });
  console.log(` N.TEST ${titre}\n         raison : ${raison}`);
}

async function capture(page, nom) {
  fs.mkdirSync(CAPTURES, { recursive: true });
  const c = path.join(CAPTURES, `${nom}.png`);
  await page.screenshot({ path: c, fullPage: false });
  return c;
}

// ---------------------------------------------------------------------------
// LE GARDE-FOU — pose sur CHAQUE contexte.
// ---------------------------------------------------------------------------
async function poserGardeFou(ctx) {
  await ctx.route('**/*', (route) => {
    const req = route.request();
    let u;
    try { u = new URL(req.url()); } catch { return route.abort(); }

    // Le Service Worker servirait un bundle en cache : on mesure le bundle
    // REELLEMENT deploye, pas une copie locale.
    if (u.pathname === '/sw.js') return route.abort();

    // (1) AUCUNE ECRITURE. Verbe, chemin et corps consignes AVANT l'abort.
    if (req.method() !== 'GET') {
      const entree = {
        verbe: req.method(),
        cible: u.host + u.pathname,
        corps: (req.postData() || '').slice(0, 400),
      };
      ecrituresAbortees.push(entree);
      if (u.pathname === '/api/tarif/estimation') appelsEstimation += 1;
      return route.abort();
    }

    // (2) AUCUN DEPART VERS UNE CAISSE. Toute navigation hors du site est
    //     coupee : Stripe, TWINT, CinetPay, PawaPay ne peuvent pas s'ouvrir.
    if (req.isNavigationRequest() && u.host !== HOTE) {
      navigationsBloquees.push(u.host + u.pathname);
      return route.abort();
    }

    return route.continue();
  });
}

async function nouveauContexte(navigateur, taille) {
  const ctx = await navigateur.newContext({
    viewport: { width: taille.l, height: taille.h },
    // Pas de storage : chaque taille repart d'un visiteur neuf.
    serviceWorkers: 'block',
  });
  await poserGardeFou(ctx);
  const page = await ctx.newPage();
  page.on('pageerror', (e) => erreursJs.push(`[${taille.cle}] ${e.message}`));
  page.on('response', (r) => {
    if (r.status() >= 500) reponses5xx.push(`[${taille.cle}] ${r.status()} ${r.url().slice(0, 120)}`);
  });
  // MESURE, et non postulat : ou le cadre principal a-t-il REELLEMENT atterri ?
  page.on('framenavigated', (f) => {
    if (f !== page.mainFrame()) return;
    const url = f.url();
    if (!url || url === 'about:blank') return;
    try {
      if (new URL(url).host !== HOTE) navigationsHorsSite.push(`[${taille.cle}] ${url.slice(0, 140)}`);
    } catch { /* url non analysable : ignoree */ }
  });
  return { ctx, page };
}

// ---------------------------------------------------------------------------
// LECTEURS D'ECRAN
// ---------------------------------------------------------------------------

/** Le prix REELLEMENT affiche dans la carte d'une offre.
 *  App.js rend « CHF {montant}.- » dans la carte ; on lit ce texte-la, pas
 *  une donnee d'API reinjectee. */
async function prixAffiche(page, idOffre) {
  return page.evaluate((id) => {
    const carte = document.querySelector(`[data-testid="offer-card-${id}"]`);
    if (!carte) return { present: false };
    const noeuds = [...carte.querySelectorAll('*')].filter((e) => e.children.length === 0);
    for (const n of noeuds) {
      const t = (n.textContent || '').trim();
      const m = t.match(/^CHF\s*([\d]+(?:[.,][\d]+)?)\s*\.?-?$/);
      if (m) {
        const st = getComputedStyle(n);
        return {
          present: true,
          texte: t,
          montant: parseFloat(m[1].replace(',', '.')),
          visible: st.display !== 'none' && st.visibility !== 'hidden' && parseFloat(st.opacity || '1') > 0.05,
        };
      }
    }
    return { present: true, texte: null, montant: null, visible: false };
  }, idOffre);
}

/** L'etat observable de l'ecran : grille d'horaires ? formulaire ? surfaces LOT 3b ? */
async function etatEcran(page) {
  return page.evaluate(() => ({
    dates: document.querySelectorAll('[data-testid^="date-btn-"]').length,
    formulaire: document.querySelectorAll('[data-testid="user-info-section"]').length,
    ligneAvantage: document.querySelectorAll('[data-testid="member-advantage-line"]').length,
    invitationMembre: document.querySelectorAll('[data-testid="member-identification-hint"]').length,
    texte: (document.body.innerText || '').replace(/\s+/g, ' '),
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
}

/**
 * Ouvre la vitrine et attend que le carrousel d'offres soit monte.
 *
 * TROIS TENTATIVES, et ce n'est pas de la complaisance : la production repond
 * « 404 page not found » (page d'erreur Traefik, conteneur momentanement
 * absent) sur ~1 a 2 % des requetes, hors deploiement — c'est documente dans
 * CLAUDE.md et sans rapport avec LOT 3b. Une seule tentative ferait echouer le
 * test sur cet alea. Chaque tentative ratee est CONSIGNEE et affichee : le
 * repli ne masque rien.
 */
const rechargements = [];
async function ouvrirVitrine(page) {
  let dernier = null;
  for (let essai = 1; essai <= 3; essai += 1) {
    try {
      const rep = await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded', timeout: 60000 });
      dernier = rep ? rep.status() : null;
      await page.waitForSelector('[data-testid^="offer-card-"]', { timeout: 30000 });
      await page.waitForTimeout(3500);
      if (essai > 1) rechargements.push(`succes au ${essai}e essai (dernier statut ${dernier})`);
      return dernier;
    } catch (e) {
      rechargements.push(`essai ${essai} echoue (statut ${dernier}) : `
        + e.message.split('\n')[0].slice(0, 90));
      if (essai === 3) throw e;
      await page.waitForTimeout(4000);
    }
  }
  return dernier;
}

/**
 * LE GESTE DU VISITEUR sur une carte d'offre.
 * @param voie 'bouton' = le CTA « Réserver » ; 'carte' = le corps de la carte.
 *
 * Le survol prealable met le carrousel en pause (`setIsPaused`), sans quoi
 * l'auto-play de 3,5 s peut deplacer la carte entre la visee et le clic.
 *
 * POURQUOI LE CORPS DE CARTE EST VISE PAR SON TITRE, ET NON PAR SON COIN.
 * Le coin haut-gauche (x:6, y:6) — le point de visee du test LOT 3b en
 * laboratoire — tombe sur la ZONE MEDIA de la carte. Mesure faite ici sur la
 * production : ce point rend `<video>` pour « PULSE x10 cours », dont le
 * `onClick` appelle `stopPropagation` (V227 : un clic sur la vignette lance la
 * lecture, il ne doit pas declencher un paiement) ; et pour une carte plus haute
 * que la fenetre (« Afroboost Silent », 822 px) ce coin reste HORS ECRAN apres
 * defilement, si bien que le clic expire. Dans les deux cas c'est le POINT DE
 * VISEE qui echoue, pas l'application — viser le coin mesurerait le test, pas le
 * site. Le titre de l'offre est, lui, un noeud du corps de carte sans gestionnaire
 * propre : il relaie donc bien le clic au `onClick` de la carte.
 */
async function cliquerOffre(page, offre, voie) {
  const carte = page.locator(`[data-testid="offer-card-${offre.id}"]`);
  const btn = page.locator(`[data-testid="offer-reserve-${offre.id}"]`);
  const libelleBouton = (await btn.innerText().catch(() => '')).replace(/\s+/g, ' ').trim();
  // `v226BlockedByVariant` (garde V226, anterieure a LOT 3b) desactive le
  // bouton ET fait echouer `v226BuyDirect` depuis le corps de la carte : le
  // meme predicat garde LES DEUX voies.
  const bloqueVariante = (await btn.isDisabled().catch(() => null)) === true;

  await carte.scrollIntoViewIfNeeded().catch(() => {});
  await carte.hover().catch(() => {});
  await page.waitForTimeout(400);

  // Deux tentatives : le carrousel defile en douceur et la vignette video de
  // certaines cartes change leur hauteur pendant le chargement — Playwright
  // refuse alors de cliquer une cible « non stable ». C'est un alea du POINT DE
  // VISEE, pas un comportement du site ; un second essai apres stabilisation le
  // leve. Un echec des DEUX essais reste un ECHEC franc.
  const cliquerStable = async (cible) => {
    for (let essai = 1; essai <= 2; essai += 1) {
      try {
        await cible.scrollIntoViewIfNeeded();
        await page.waitForTimeout(essai === 1 ? 300 : 1500);
        await cible.click({ timeout: 10000 });
        return;
      } catch (e) {
        if (essai === 2) throw e;
        await carte.hover().catch(() => {});
      }
    }
  };

  if (voie === 'bouton') {
    if (bloqueVariante) {
      return { clique: false, libelle: libelleBouton, libelleBouton, bloqueVariante: true };
    }
    await cliquerStable(btn);
    await page.waitForTimeout(3500);
    return { clique: true, libelle: libelleBouton, libelleBouton, bloqueVariante: false };
  }

  await cliquerStable(carte.locator('p.font-semibold').first());
  await page.waitForTimeout(3500);
  return {
    clique: true, libelle: '(titre, dans le corps de la carte)', libelleBouton, bloqueVariante,
  };
}

/** Les tentatives de paiement consignees depuis un index donne. */
function checkoutsDepuis(index) {
  return ecrituresAbortees.slice(index)
    .filter((e) => e.cible.endsWith('/api/create-checkout-session'))
    .map((e) => {
      let corps = {};
      try { corps = JSON.parse(e.corps); } catch { corps = {}; }
      return corps;
    });
}

// ---------------------------------------------------------------------------
// LE TEST
// ---------------------------------------------------------------------------
async function principal() {
  fs.mkdirSync(CAPTURES, { recursive: true });
  console.log(`\nCIBLE : ${BASE}  (LECTURE SEULE STRICTE)\n`);

  const navigateur = await chromium.launch({ headless: true });
  let apiOffres = null;

  try {
    // =====================================================================
    // A — L'API DEPLOYEE. Mesuree DEPUIS le navigateur, sur la vraie prod.
    // =====================================================================
    console.log('--- A. L\'API deployee -------------------------------------');
    {
      const { ctx, page } = await nouveauContexte(navigateur, TAILLES[0]);
      await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded', timeout: 60000 });

      const flags = await page.evaluate(async () => {
        const r = await fetch('/api/feature-flags', { cache: 'no-store' });
        return { statut: r.status, corps: await r.json().catch(() => null) };
      });
      console.log('    reponse reelle /api/feature-flags : '
        + JSON.stringify(flags.corps));
      verifier('A1 GET /api/feature-flags repond 200', flags.statut === 200, `HTTP ${flags.statut}`);
      verifier('A2 MEMBER_PRICING_ENABLED est present dans la reponse (le drapeau '
        + 'LOT 3b est bien deploye)',
        !!flags.corps && Object.prototype.hasOwnProperty.call(flags.corps, 'MEMBER_PRICING_ENABLED'),
        'cle absente');
      verifier('A3 ... et il vaut EXACTEMENT false (booleen, pas une chaine)',
        !!flags.corps && flags.corps.MEMBER_PRICING_ENABLED === false,
        `lu : ${JSON.stringify(flags.corps && flags.corps.MEMBER_PRICING_ENABLED)}`);

      const offres = await page.evaluate(async () => {
        const r = await fetch('/api/offers', { cache: 'no-store' });
        const d = await r.json().catch(() => null);
        return { statut: r.status, liste: Array.isArray(d) ? d : (d && d.offers) || [] };
      });
      apiOffres = offres.liste;
      verifier('A4 GET /api/offers repond 200', offres.statut === 200, `HTTP ${offres.statut}`);
      verifier(`A5 les ${CATALOGUE.length} offres de production sont servies`,
        apiOffres.length === CATALOGUE.length, `${apiOffres.length} offre(s) recue(s)`);

      // A6 — la PREUVE que le nouveau modele est deploye.
      const sansChamp = apiOffres
        .filter((o) => !Object.prototype.hasOwnProperty.call(o, 'member_discount_pct'))
        .map((o) => (o.name || o.id || '?').slice(0, 40));
      verifier('A6 CHAQUE offre expose le champ `member_discount_pct` (le modele '
        + 'LOT 3b est bien en ligne)',
        apiOffres.length > 0 && sansChamp.length === 0,
        `sans le champ : ${JSON.stringify(sansChamp)}`);

      // A7 — ... mais AUCUNE n'a d'avantage configure.
      const configurees = apiOffres
        .filter((o) => o.member_discount_pct !== null && o.member_discount_pct !== undefined
          && Number(o.member_discount_pct) !== 0)
        .map((o) => `${(o.name || '').slice(0, 30)} = ${o.member_discount_pct}`);
      verifier('A7 ... et sa valeur est nulle/absente sur TOUTES les offres '
        + '(aucun avantage configure en production)',
        configurees.length === 0, JSON.stringify(configurees));

      // A8 — le bundle reellement servi (tracabilite du build mesure).
      const bundle = await page.evaluate(() => {
        const s = [...document.querySelectorAll('script[src]')]
          .map((e) => e.getAttribute('src'))
          .find((x) => /static\/js\/main\.[0-9a-f]+\.js/.test(x || ''));
        return s || null;
      });
      console.log(`    bundle servi : ${bundle}`);
      verifier('A8 un bundle React est bien servi par la production',
        !!bundle && /static\/js\/main\.[0-9a-f]+\.js/.test(bundle), `lu : ${bundle}`);

      await ctx.close();
    }

    // A9/A10 — les deux offres masquees : prix verifie a la SOURCE.
    console.log('\n--- A bis. Les offres masquees (hors vitrine) --------------');
    for (const attendue of CATALOGUE.filter((o) => !o.surVitrine)) {
      const o = (apiOffres || []).find((x) => x.id === attendue.id);
      const affichable = o
        ? ((o.progressive_pricing && o.active_price != null) ? o.active_price : o.price)
        : null;
      verifier(`A9.${attendue.cle} « ${attendue.nom} » : le prix servi par l'API vaut `
        + `toujours ${attendue.prix}`,
        o != null && Math.abs(Number(affichable) - attendue.prix) < 0.001,
        o ? `lu : ${affichable} (price=${o.price}, active_price=${o.active_price})` : 'offre absente de l\'API');
      nonTeste(`A10.${attendue.cle} le prix de « ${attendue.nom} » TEL QU'AFFICHE a l'ecran`,
        `${attendue.raisonAbsence} : la carte n'est rendue sur AUCUNE vitrine, il n'y a `
        + 'donc rien a lire a l\'ecran. Seul le prix servi par l\'API est verifie (A9), '
        + 'et c\'est lui que `v223UnitPrice` afficherait.');
    }

    // =====================================================================
    // B — LA VITRINE, DANS LES DEUX TAILLES.
    // =====================================================================
    for (const taille of TAILLES) {
      console.log(`\n--- B/C/D. ${taille.titre} --------------------------------`);
      const { ctx, page } = await nouveauContexte(navigateur, taille);

      // --- B : la vitrine charge -----------------------------------------
      const statut = await ouvrirVitrine(page);
      verifier(`B1.${taille.cle} la vitrine repond 200`, statut === 200, `HTTP ${statut}`);

      const etat = await etatEcran(page);
      const cartes = await page.locator('[data-testid^="offer-card-"]').count();
      const attenduesVitrine = CATALOGUE.filter((o) => o.surVitrine).length;
      verifier(`B2.${taille.cle} les ${attenduesVitrine} offres visibles sont rendues a l'ecran`,
        cartes === attenduesVitrine, `${cartes} carte(s) rendue(s)`);

      // --- C : les prix affiches ------------------------------------------
      const releve = [];
      for (const attendue of CATALOGUE.filter((o) => o.surVitrine)) {
        const p = await prixAffiche(page, attendue.id);
        releve.push(`${attendue.nom} -> ${p.texte}`);
        verifier(`C.${taille.cle}.${attendue.cle} « ${attendue.nom} » affiche `
          + `${attendue.prix}${attendue.prix === 0 ? ' (offre a 0 CHF)' : ''}`,
          p.present && p.montant != null && Math.abs(p.montant - attendue.prix) < 0.001,
          p.present ? `lu a l'ecran : « ${p.texte} »` : 'carte absente de l\'ecran');
        if (p.present && p.montant != null) {
          verifier(`C.${taille.cle}.${attendue.cle}.vis ... et ce prix est REELLEMENT visible`,
            p.visible === true, `visible=${p.visible}`);
        }
      }
      console.log('    prix releves a l\'ecran : ' + releve.join(' | '));

      // --- B suite : aucune surface LOT 3b --------------------------------
      verifier(`B3.${taille.cle} AUCUNE ligne « Avantage membre » dans le DOM `
        + '(data-testid="member-advantage-line")',
        etat.ligneAvantage === 0, `${etat.ligneAvantage} occurrence(s)`);
      verifier(`B4.${taille.cle} AUCUNE invitation « Membre Afroboost ? Ouvrez votre `
        + 'espace » (data-testid="member-identification-hint")',
        etat.invitationMembre === 0, `${etat.invitationMembre} occurrence(s)`);
      for (const m of MOTS_INTERDITS) {
        verifier(`B5.${taille.cle} aucun texte « ${m.quoi} » a l'ecran`,
          !m.motif.test(etat.texte),
          `motif ${m.motif} trouve dans le texte de la page`);
      }
      // B5bis — l'expression NUE « avantage membre » existe deja dans les
      // descriptions commerciales des offres, en base, ecrite par le
      // proprietaire. Ce controle exige que CHAQUE occurrence a l'ecran soit
      // expliquee par une description servie par l'API : une occurrence de
      // PLUS serait une surface LOT 3b qui a fuite.
      {
        const occurrencesEcran = (etat.texte.match(/avantage\s+membre/gi) || []).length;
        const occurrencesApi = (apiOffres || []).reduce((n, o) => n
          + (String(o.description || '').match(/avantage\s+membre/gi) || []).length, 0);
        verifier(`B5bis.${taille.cle} les ${occurrencesEcran} occurrence(s) de l'expression `
          + '« avantage membre » a l\'ecran proviennent TOUTES des descriptions '
          + 'd\'offres deja en base (texte commercial du proprietaire, anterieur a LOT 3b)',
          occurrencesEcran <= occurrencesApi,
          `${occurrencesEcran} a l'ecran pour ${occurrencesApi} en base`);
      }
      verifier(`B6.${taille.cle} aucun debordement horizontal `
        + '(documentElement.scrollWidth <= clientWidth)',
        etat.scrollWidth <= etat.clientWidth,
        `scrollWidth=${etat.scrollWidth} clientWidth=${etat.clientWidth}`);
      console.log('    capture : ' + await capture(page, `${taille.cle}-1-vitrine`));

      // --- D : le parcours d'achat, DEUX voies ----------------------------
      for (const offre of CATALOGUE.filter((o) => o.surVitrine && o.payante)) {
        for (const voie of ['bouton', 'carte']) {
          const idJournal = ecrituresAbortees.length;
          const estAvant = appelsEstimation;

          let geste;
          try {
            await ouvrirVitrine(page);
            geste = await cliquerOffre(page, offre, voie);
          } catch (e) {
            verifier(`D.${taille.cle}.${offre.cle}.${voie} le geste est realisable `
              + '(vitrine ouverte, carte cliquee)',
              false, e.message.split('\n')[0].slice(0, 120));
            continue;
          }

          const apres = await etatEcran(page);
          const nom = `D.${taille.cle}.${offre.cle}.${voie}`;

          // 5 — AUCUNE grille d'horaires ne s'ouvre.
          verifier(`${nom} AUCUNE grille d'horaires ne s'ouvre `
            + `(« ${offre.nom} », voie ${voie})`,
            apres.dates === 0, `${apres.dates} bouton(s) de date a l'ecran`);
          verifier(`${nom}.form AUCUN formulaire de reservation ne s'ouvre`,
            apres.formulaire === 0, `${apres.formulaire} formulaire(s)`);
          verifier(`${nom}.av AUCUNE ligne « Avantage membre -N% » apres le clic`,
            apres.ligneAvantage === 0 && !MOTS_INTERDITS[0].motif.test(apres.texte),
            `${apres.ligneAvantage} noeud(s) member-advantage-line, signature dans le `
            + `texte : ${MOTS_INTERDITS[0].motif.test(apres.texte)}`);
          verifier(`${nom}.inv AUCUNE invitation « Membre Afroboost ? Ouvrez votre `
            + 'espace » apres le clic',
            apres.invitationMembre === 0 && !MOTS_INTERDITS[1].motif.test(apres.texte));

          // 9 — le clic tente bien un ACHAT DIRECT (et il est aborte).
          const tentatives = checkoutsDepuis(idJournal);
          if (geste.bloqueVariante) {
            nonTeste(`${nom}.checkout l'achat direct depuis cette voie`,
              `geste tente : ${geste.libelle}. Le bouton « Réserver » de cette carte `
              + `affiche « ${geste.libelleBouton} » et est DESACTIVE. `
              + 'C\'est la garde V226 `v226BlockedByVariant` (choix de variante '
              + 'obligatoire), anterieure a LOT 3b, et elle garde LES DEUX voies : le '
              + 'bouton comme le corps de la carte passent par `v226BuyDirect`, qui '
              + 're-teste le meme predicat. Le parcours n\'est donc pas atteignable par '
              + 'ce geste, ni avant ni apres le deploiement. L\'absence de grille '
              + 'd\'horaires et de surface LOT 3b reste, elle, mesuree ci-dessus.');
          } else {
            const bonne = tentatives.filter((c) => c.offerId === offre.id);
            verifier(`${nom}.checkout le clic tente UN achat direct `
              + '(POST /api/create-checkout-session), ABORTE avant depart',
              bonne.length === 1,
              `${tentatives.length} tentative(s), dont ${bonne.length} sur cette offre : `
              + JSON.stringify(tentatives.map((c) => ({ o: c.offerId, a: c.amount }))));
            verifier(`${nom}.montant ... pour le montant historique ${offre.prix} CHF`,
              bonne.length === 1 && Math.abs(Number(bonne[0].amount) - offre.prix) < 0.001,
              bonne.length ? `amount = ${bonne[0].amount}` : 'aucun paiement tente');
          }

          verifier(`${nom}.est AUCUN appel a /api/tarif/estimation provoque par ce geste`,
            appelsEstimation - estAvant === 0,
            `${appelsEstimation - estAvant} appel(s)`);
        }
      }
      console.log('    capture : ' + await capture(page, `${taille.cle}-2-apres-clics`));

      const fin = await etatEcran(page);
      verifier(`B7.${taille.cle} toujours aucun debordement horizontal apres les clics`,
        fin.scrollWidth <= fin.clientWidth,
        `scrollWidth=${fin.scrollWidth} clientWidth=${fin.clientWidth}`);

      await ctx.close();
    }

    // =====================================================================
    // E — LE BILAN GLOBAL.
    // =====================================================================
    console.log('\n--- E. Bilan global ---------------------------------------');
    verifier('E1 AUCUN appel a /api/tarif/estimation sur TOUT le parcours '
      + '(le drapeau eteint ne declenche rien)',
      appelsEstimation === 0, `${appelsEstimation} appel(s)`);
    verifier('E2 AUCUNE erreur JavaScript sur les ecrans traverses',
      erreursJs.length === 0, erreursJs.slice(0, 4).join(' | '));
    // E3 — LES 5xx. Le parcours LOT 3b d'abord, le reste ensuite, et l'un ne
    // couvre pas l'autre.
    {
      const ROUTES_LOT3B = /\/api\/(offers|feature-flags|create-checkout-session|tarif\/estimation|memberships|courses|reservations)/;
      const surLeParcours = reponses5xx.filter((l) => ROUTES_LOT3B.test(l));
      verifier('E3a AUCUNE 5xx sur les routes du parcours LOT 3b (offres, drapeaux, '
        + 'caisse, estimation, cours, reservations)',
        surLeParcours.length === 0, surLeParcours.slice(0, 4).join(' | '));

      // Le reste : documente, et VERIFIE — une 5xx d'une autre nature ferait
      // echouer ce point plutot que de passer inapercue.
      const autres = reponses5xx.filter((l) => !ROUTES_LOT3B.test(l));
      const MEDIA = /\/api\/files\/[0-9a-f]+\/optimized/;
      const uniques = [...new Set(autres.map((l) => l.replace(/^\[[a-z]+\]\s*/, '')))];
      verifier(`E3b les ${autres.length} 5xx restantes portent TOUTES sur `
        + '/api/files/<id>/optimized — service de MEDIA, code non modifie par '
        + 'LOT 3b (0 ligne dans le diff 0e276ad..51e6330). Toute 5xx d\'une autre '
        + 'nature ferait echouer ce point.',
        autres.every((l) => MEDIA.test(l)),
        uniques.slice(0, 4).join(' | '));
      if (uniques.length) {
        console.log(`    5xx hors parcours LOT 3b, a traiter separement (${autres.length} `
          + `occurrence(s), ${uniques.length} URL distincte(s)) :`);
        for (const u of uniques) console.log(`      ${u}`);
      }
    }
    // MESURE : le cadre principal n'a JAMAIS quitte afroboost.com. C'est la
    // preuve qu'aucune page de paiement ne s'est ouverte.
    verifier(`E4 le navigateur n'a JAMAIS quitte ${HOTE} — aucune page de caisse `
      + '(Stripe / TWINT / CinetPay / PawaPay) ne s\'est ouverte',
      navigationsHorsSite.length === 0,
      navigationsHorsSite.slice(0, 4).join(' | '));
    // Le garde-fou est-il VIVANT ? S'il ne s'etait pas declenche une seule fois,
    // les « OK » ci-dessus ne prouveraient pas la lecture seule.
    verifier('E5 le garde-fou anti-ecriture s\'est REELLEMENT declenche (au moins '
      + 'une requete non-GET interceptee) et n\'a laisse passer aucun verbe GET '
      + 'par erreur',
      ecrituresAbortees.length > 0
      && ecrituresAbortees.every((e) => typeof e.verbe === 'string' && e.verbe !== 'GET'),
      `${ecrituresAbortees.length} requete(s) interceptee(s)`);

    console.log(`\n    requetes non-GET INTERCEPTEES ET ABORTEES (${ecrituresAbortees.length}) :`);
    const parCible = new Map();
    for (const e of ecrituresAbortees) {
      const k = `${e.verbe} ${e.cible}`;
      parCible.set(k, (parCible.get(k) || 0) + 1);
    }
    for (const [k, n] of parCible) console.log(`      x${n}  ${k}`);
    console.log(`    navigations hors ${HOTE} bloquees : ${navigationsBloquees.length}`
      + (navigationsBloquees.length ? ` (${[...new Set(navigationsBloquees)].join(', ')})` : ''));
    if (rechargements.length) {
      console.log(`    chargements de vitrine ayant demande un nouvel essai `
        + `(${rechargements.length}) :`);
      for (const r of rechargements) console.log(`      ${r}`);
    } else {
      console.log('    aucun rechargement de vitrine n\'a ete necessaire.');
    }
  } finally {
    await navigateur.close();
  }

  // ---------------------------------------------------------------------
  const echecs = resultats.filter((r) => !r.ok);
  console.log('\n===========================================================');
  console.log(`${resultats.length - echecs.length} OK · ${echecs.length} ECHEC(S) · `
    + `${nonTestes.length} NON TESTE(S)`);
  console.log(`captures : ${CAPTURES}`);
  if (nonTestes.length) {
    console.log('\nNON TESTES (jamais comptes comme reussis) :');
    for (const n of nonTestes) console.log(`  - ${n.titre}\n    -> ${n.raison}`);
  }
  if (echecs.length) {
    console.log('\nECHECS :');
    for (const e of echecs) console.log(`  - ${e.titre} — ${e.detail}`);
    process.exit(1);
  }
  console.log('\nVERDICT : drapeau eteint, le site se comporte comme avant le deploiement.');
}

principal().catch((e) => { console.error('ERREUR:', e.stack || e.message); process.exit(1); });
