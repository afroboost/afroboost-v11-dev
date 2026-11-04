/**
 * V646 — PARCOURS BOUTIQUE, sur la pile LOCALE (pile_locale.py : vraie application,
 * base de test, faux Stripe). Aucun paiement, aucun e-mail, aucune écriture en prod.
 *
 * Couvre : /boutique et l'URL produit (accès direct, recharge, retour navigateur),
 * galerie, zoom, variantes, checkout, fond sombre, menu violet, indépendance et
 * persistance des deux bannières, absence d'écrasement par l'enregistrement général,
 * et la non-régression de l'accueil.
 *
 * Toutes les mesures lisent le CALCULÉ (display, couleurs, rectangles), jamais un
 * simple comptage DOM (leçon V540).
 *
 * ISOLATION (obligatoire, vérifiée au démarrage : le script refuse de tourner sinon)
 *   - le serveur ET ce script tournent dans `reseau_local.sb` : le noyau macOS refuse
 *     toute connexion hors de 127.0.0.1 (redirections, WebSocket, tâches de fond,
 *     Resend, Stripe, Cloudinary, PostHog, DNS) ;
 *   - Chromium ne résout aucun nom, et chaque requête non locale est coupée puis journalisée ;
 *   - aucun relais vers la production : les médias absents sont servis depuis FICHIERS ;
 *   - la base est `afroboost_pw_test` sur 127.0.0.1, adresse écrite en dur ci-dessous.
 *
 * LANCEMENT (depuis la racine, build React préalable dans <hors dépôt>/pw_build) :
 *   sandbox-exec -f tests/parcours/reseau_local.sb env PW_SCRATCH=<hors dépôt> python3 tests/parcours/pile_locale.py &
 *   CAPTURES=<hors dépôt> FICHIERS=<hors dépôt> NODE_PATH=$HOME/.claude/skills/gstack/node_modules \
 *     sandbox-exec -f tests/parcours/reseau_local.sb node tests/parcours/parcours_boutique.cjs
 *   FICHIERS contient : tshirt-1.jpg, tshirt-2.jpg, banniere-a.png, banniere-b.png, clip.webm
 */
const { chromium, devices } = require('playwright');
const { execFileSync } = require('child_process');
const fs = require('fs');
const net = require('net');
const path = require('path');

const BASE = 'http://127.0.0.1:8001';
const CAPTURES = process.env.CAPTURES;
const FICHIERS = process.env.FICHIERS;
const TSHIRT_ID = '84b7d8c6-b859-410a-8a09-0d1ee0069404';
const URL_TSHIRT = '/boutique/t-shirt-1-cours-offert-84b7d8c6';
const SUPER_ADMIN = 'contact.artboost@gmail.com';
const CHAMPS = (o, p) => Object.fromEntries(Object.entries(o).filter(([k]) => k.startsWith(p)));

const resultats = [];
function v(nom, ok, detail = '') {
  resultats.push({ nom, ok });
  console.log(`${ok ? 'OK ' : 'KO '} ${nom}${detail !== '' ? ' — ' + detail : ''}`);
}
async function capture(p, nom) {
  if (CAPTURES) await p.screenshot({ path: path.join(CAPTURES, nom + '.jpg'), type: 'jpeg', quality: 72 });
}
const visible = (p, sel) => p.locator(sel).first().isVisible().catch(() => false);

// ═══════════════════════════ ISOLATION ═══════════════════════════
const coupes = [];
const FIXTURES = { e84ee4af364646eb: 'tshirt-1.jpg', d80a96504a2841ad: 'tshirt-2.jpg' };

/** Seul 127.0.0.1:8001 passe. Un média absent de la base locale vient de FICHIERS. */
async function verrouiller(ctx) {
  await ctx.route('**/*', async (route) => {
    const r = route.request();
    const u = new URL(r.url());
    if (u.protocol === 'data:' || u.protocol === 'blob:') return route.continue();
    if (u.origin !== BASE) { coupes.push(`${r.method()} ${u.origin}${u.pathname.slice(0, 50)}`); return route.abort(); }
    if (r.method() === 'GET' && u.pathname.startsWith('/api/files/')) {
      const local = await route.fetch().catch(() => null);
      if (local && local.ok()) return route.fulfill({ response: local });
      const id = u.pathname.split('/')[3];
      return route.fulfill({ status: 200, path: path.join(FICHIERS, FIXTURES[id] || 'banniere-a.png') });
    }
    return route.continue();
  });
  await ctx.routeWebSocket(/.*/, (ws) => { coupes.push('WS ' + ws.url().slice(0, 60)); ws.close(); });
}

/** Le script refuse de tourner si le noyau laisse sortir quoi que ce soit. */
async function exigerIsolation() {
  const sort = await new Promise((res) => {
    const s = net.connect({ host: '1.1.1.1', port: 443 });
    s.setTimeout(4000);
    s.on('connect', () => { s.destroy(); res(true); });
    s.on('timeout', () => { s.destroy(); res(true); });
    s.on('error', (e) => res(e.code !== 'EPERM'));
  });
  if (sort) { console.error('ARRÊT : ce script doit tourner dans reseau_local.sb'); process.exit(2); }
  const serveur = execFileSync('python3', ['-c', `
import ctypes,subprocess
pid=int(subprocess.check_output(["lsof","-nP","-iTCP:8001","-sTCP:LISTEN","-t"]).split()[0])
print(ctypes.CDLL(None).sandbox_check(pid,None,0))`], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
  if (serveur !== '1') { console.error('ARRÊT : le serveur 8001 ne tourne pas dans reseau_local.sb'); process.exit(2); }
  v('Z0 script et serveur dans le bac à sable réseau', true);
}

/** Base LOCALE uniquement : l'adresse est écrite ici, jamais lue dans l'environnement. */
function mongo(code) {
  return JSON.parse(execFileSync('python3', ['-c', `
import json
from pymongo import MongoClient
db=MongoClient("mongodb://127.0.0.1:27017")["afroboost_pw_test"]
${code}`], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }));
}
function reinitialiserBannieres() {
  mongo(`
db.concept.update_one({"id":"concept"},{"$set":{
 "home_shop_banner_url":"/api/files/807c0a791f82443d/image_807c0a791f82443d.jpg","home_shop_banner_type":"image",
 "home_shop_banner_trim_start":0.0,"home_shop_banner_trim_end":0.0,"home_shop_banner_thumbnail":"","home_shop_banner_crop":None,
 "boutique_page_banner_url":"","boutique_page_banner_type":"","boutique_page_banner_trim_start":0.0,
 "boutique_page_banner_trim_end":0.0,"boutique_page_banner_thumbnail":"","boutique_page_banner_crop":None}})
print("true")`);
}
/** Styles calculés d'un onglet, une fois stables : `transition-all` et le chargement
    des couleurs du coach font varier la valeur pendant quelques centaines de ms. */
const styleStable = (p, sel) => p.evaluate(async (s) => {
  const lire = () => { const e = document.querySelector(s); const c = getComputedStyle(e); return JSON.stringify({ actif: e.dataset.actif, fond: c.backgroundImage, bord: c.borderColor, texte: c.color }); };
  let avant = lire(); let stable = 0;
  for (let i = 0; i < 100 && stable < 10; i += 1) {
    await new Promise((r) => setTimeout(r, 100));
    const ici = lire(); stable = ici === avant ? stable + 1 : 0; avant = ici;
  }
  return JSON.parse(avant);
}, sel);
const pret = (p, sel) => p.waitForSelector(sel, { state: 'visible', timeout: 30000 });

/** Mesure de la fiche : fond, débordement des photos, lisibilité. */
const mesurerFiche = (p) => p.evaluate(() => {
  const css = (s, k) => { const e = document.querySelector(s); return e ? getComputedStyle(e)[k] : null; };
  const lum = (c) => { const m = (c || '').match(/\d+(\.\d+)?/g) || []; return (0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]) / 255; };
  const cells = [...document.querySelectorAll('.af-fiche-cell')].map((c) => {
    const i = c.querySelector('img'); const r = c.getBoundingClientRect();
    return { w: r.width, h: r.height, ratioCell: r.width / r.height, ratioPhoto: i ? i.naturalWidth / i.naturalHeight : 0, filtre: i ? getComputedStyle(i).filter : '' };
  });
  return {
    galerie: lum(css('.af-fiche-galerie-premium', 'backgroundColor')),
    cellule: lum(css('.af-fiche-cell', 'backgroundColor')),
    panneau: lum(css('.af-fiche-infos-premium', 'backgroundColor')),
    titre: lum(css('.af-fiche-titre-premium', 'color')),
    description: lum(css('.af-fiche-desc-premium', 'color')),
    puce: lum(css('.af-fiche-chip', 'color')),
    cells,
    debordement: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  };
});

// ════════════════════════ A. PAGE, FICHE, ACHAT ════════════════════════
async function parcoursVisiteur(browser, nom, opt) {
  const mobile = nom === 'mobile';
  const ctx = await browser.newContext({ ...opt, serviceWorkers: 'block' });
  await verrouiller(ctx);
  const p = await ctx.newPage();
  const erreurs = [];
  p.on('pageerror', (e) => erreurs.push(e.message));
  let appelsApi = 0;
  p.on('request', (r) => { if (r.url().includes('/api/')) appelsApi += 1; });

  // Accès direct à la liste
  await p.goto(BASE + '/boutique', { waitUntil: 'domcontentloaded' });
  await pret(p, '[data-testid="page-boutique"]');
  await pret(p, `[data-testid="voir-produit-${TSHIRT_ID}"]`);
  v(`${nom} A1 accès direct /boutique : page affichée`, await visible(p, '[data-testid="page-boutique-banniere"]'));
  v(`${nom} A2 pas de Hero, pas de Shop d'accueil en double`, !(await visible(p, '[data-testid="hero-carrousel"]')) && !(await visible(p, '#products-section')));
  v(`${nom} A3 titre d'onglet`, /Boutique Afroboost/.test(await p.title()), await p.title());
  v(`${nom} A4 un seul produit réel, aucune carte « à venir »`,
    (await p.locator('[data-testid="page-boutique-produits"] [data-testid^="voir-produit-"]').count()) === 1
    && (await p.locator('.af-avenir-carte').count()) === 0);
  const base = await p.evaluate(() => ({ d: document.documentElement.scrollWidth - document.documentElement.clientWidth }));
  v(`${nom} A5 aucun défilement horizontal`, base.d <= 0, base.d);
  await capture(p, `${nom}-boutique`);

  // Menu actif
  if (!mobile) {
    const s = await styleStable(p, '[data-testid="nav-tab-shop"]');
    v(`${nom} A6 Shop actif, en violet`, s.actif === 'true' && /gradient/.test(s.fond), s.fond.slice(0, 70));
    await p.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
    await pret(p, '[data-testid="nav-tab-all"]');
    const ref = await styleStable(p, '[data-testid="nav-tab-all"]');
    v(`${nom} A7 état actif STRICTEMENT identique à l'onglet actif de l'accueil`,
      ref.actif === 'true' && s.fond === ref.fond && s.bord === ref.bord && s.texte === ref.texte, JSON.stringify({ s, ref }));
    await p.goto(BASE + '/boutique', { waitUntil: 'domcontentloaded' });
    await pret(p, `[data-testid="voir-produit-${TSHIRT_ID}"]`);
  }

  // Vers la fiche produit
  await p.click(`[data-testid="voir-produit-${TSHIRT_ID}"]`);
  await pret(p, `[data-testid="fiche-produit-${TSHIRT_ID}"]`);
  v(`${nom} B1 « Voir le produit » ouvre l'URL du produit`, new URL(p.url()).pathname === URL_TSHIRT, p.url());
  v(`${nom} B2 aucune modale : la fiche est la page`, (await p.locator(`[data-testid="product-detail-${TSHIRT_ID}"]`).count()) === 0);
  await p.waitForFunction(() => { const i = [...document.querySelectorAll('.af-fiche-cell img')]; return i.length === 2 && i.every((x) => x.complete && x.naturalWidth > 0); }, null, { timeout: 30000 });
  const m = await mesurerFiche(p);
  v(`${nom} C1 fond de galerie et de panneau sombres`, m.galerie < 0.1 && m.cellule < 0.1 && m.panneau < 0.1, `${m.galerie.toFixed(2)} / ${m.panneau.toFixed(2)}`);
  v(`${nom} C2 texte lisible (titre, description, tailles)`, m.titre > 0.9 && m.description > 0.5 && m.puce > 0.9);
  v(`${nom} C3 photos sans bande ni coupe (cellule au format de la photo)`,
    m.cells.length === 2 && m.cells.every((c) => Math.abs(c.ratioCell - c.ratioPhoto) < 0.02), m.cells.map((c) => c.ratioCell.toFixed(3) + '/' + c.ratioPhoto.toFixed(3)).join(' '));
  v(`${nom} C4 photos non altérées (aucun filtre CSS)`, m.cells.every((c) => c.filtre === 'none'));
  v(`${nom} C5 aucun défilement horizontal`, m.debordement <= 0, m.debordement);
  if (mobile) await verifierBulle(p, nom);
  await capture(p, `${nom}-fiche`);

  // Accès direct et recharge de l'URL produit
  await p.reload({ waitUntil: 'domcontentloaded' });
  await pret(p, `[data-testid="fiche-produit-${TSHIRT_ID}"]`);
  v(`${nom} D1 recharge de l'URL produit`, new URL(p.url()).pathname === URL_TSHIRT);
  v(`${nom} D2 nom du produit dans l'onglet`, /T-shirt/.test(await p.title()), await p.title());

  // Zoom
  await p.locator('.af-fiche-cell').first().click();
  await p.waitForSelector('.fixed.inset-0.z-\\[60\\]', { timeout: 5000 });
  const zoom = p.locator('.fixed.inset-0.z-\\[60\\]');
  v(`${nom} E1 zoom ouvert, compteur 1 / 2`, (await zoom.innerText()).includes('1 / 2'));
  await capture(p, `${nom}-zoom`);
  await zoom.getByRole('button', { name: '›' }).click();
  v(`${nom} E2 navigation dans le zoom`, (await zoom.innerText()).includes('2 / 2'));
  await zoom.getByRole('button', { name: '×' }).click();
  v(`${nom} E3 zoom refermé, URL inchangée`, (await zoom.count()) === 0 && new URL(p.url()).pathname === URL_TSHIRT);

  // Variantes et quantité
  const cta = p.locator(`[data-testid="detail-reserve-${TSHIRT_ID}"]`);
  v(`${nom} F1 achat bloqué sans variante`, await cta.isDisabled(), await cta.innerText());
  await p.click(`[data-testid="detail-variant-size-${TSHIRT_ID}-M"]`);
  await p.click(`[data-testid="detail-variant-color-${TSHIRT_ID}-Noir"]`);
  await p.getByRole('button', { name: 'Plus', exact: true }).click();
  v(`${nom} F2 variantes + quantité : total affiché`, /119[.,]98/.test(await cta.innerText()), await cta.innerText());
  await capture(p, `${nom}-variantes`);

  // Checkout : même parcours, faux Stripe, rien n'est payé pour de vrai
  const envois = [];
  const surEnvoi = (r) => { if (r.method() === 'POST' && /checkout/i.test(r.url())) envois.push(r.postDataJSON()); };
  p.on('request', surEnvoi);
  await cta.click();
  const nomClient = p.locator('input[autocomplete="name"], input[placeholder*="om" i]').first();
  await nomClient.waitFor({ state: 'visible', timeout: 15000 });
  await capture(p, `${nom}-inscription`);
  await nomClient.fill('Client Banc');
  await p.locator('input[type="email"]').first().fill(`banc-${nom}-${Date.now()}@example.com`);
  await p.locator('input[type="tel"]').first().fill('+41791234567');
  await p.getByRole('button', { name: /continuer|payer|valider|suivant/i }).last().click();
  await p.waitForSelector('[data-testid="faux-stripe"]', { timeout: 30000 });
  p.off('request', surEnvoi);
  const cs = new URL(p.url()).searchParams.get('cs');
  const envoi = envois[envois.length - 1] || {};
  v(`${nom} G1a le navigateur demande 2 × T-shirt M / Noir`, envoi.quantity === 2 && envoi.variants && envoi.variants.size === 'M' && envoi.variants.color === 'Noir', JSON.stringify({ q: envoi.quantity, v: envoi.variants }));
  const tx = mongo(`print(json.dumps(db.payment_transactions.find_one({"session_id":${JSON.stringify(cs)}},{"_id":0,"quantity":1,"expected_amount":1,"server_unit_price":1,"amount_source":1,"metadata":1})))`) || {};
  const meta = tx.metadata || {};
  v(`${nom} G1b serveur : quantité 2, total 119.98, unitaire 59.99 calculés côté serveur`, tx.quantity === 2 && tx.expected_amount === 119.98 && tx.server_unit_price === 59.99 && tx.amount_source === 'server', JSON.stringify({ q: tx.quantity, t: tx.expected_amount, u: tx.server_unit_price }));
  v(`${nom} G1c serveur : variantes M / Noir transmises au paiement`, meta.variant_size === 'M' && meta.variant_color === 'Noir' && meta.quantity === '2', `${meta.variant_size}/${meta.variant_color}`);
  v(`${nom} G1d faux Stripe : le bon produit`, /T-shirt/.test(await p.locator('[data-testid="faux-produit"]').innerText()) && /59\.99/.test(await p.locator('[data-testid="faux-montant"]').innerText()));
  await capture(p, `${nom}-faux-stripe`);

  // Produit inconnu
  await p.goto(BASE + '/boutique/chaussettes-00000000', { waitUntil: 'domcontentloaded' });
  await pret(p, '[data-testid="page-boutique-retour"]');
  await p.waitForFunction(() => /plus disponible/.test((document.querySelector('[data-testid="page-boutique-introuvable"]') || {}).textContent || ''), null, { timeout: 30000 });
  v(`${nom} H1 produit inconnu : message, pas d'écran vide`, true);
  await p.click('[data-testid="page-boutique-retour"]');
  await pret(p, '[data-testid="page-boutique-banniere"]');
  v(`${nom} H2 retour à la liste`, new URL(p.url()).pathname === '/boutique');

  // Navigation et retour navigateur
  const ouvrirShop = async () => {
    if (mobile) { await p.click('[data-testid="nav-mobile-menu"]'); await p.click('[data-testid="nav-menu-shop"]'); } else { await p.click('[data-testid="nav-tab-shop"]'); }
  };
  await p.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  await pret(p, '[data-testid="hero-carrousel"]');
  await pret(p, '#products-section');
  await ouvrirShop();
  await pret(p, '[data-testid="page-boutique-banniere"]');
  v(`${nom} I1 le menu Shop ouvre /boutique`, new URL(p.url()).pathname === '/boutique');
  await p.click(`[data-testid="voir-produit-${TSHIRT_ID}"]`);
  await pret(p, `[data-testid="fiche-produit-${TSHIRT_ID}"]`);
  await p.goBack();
  await pret(p, '[data-testid="page-boutique-banniere"]');
  v(`${nom} I2 Précédent : du produit à la liste`, new URL(p.url()).pathname === '/boutique');
  await p.goBack();
  await pret(p, '[data-testid="hero-carrousel"]');
  v(`${nom} I3 Précédent : retour à l'accueil, Hero et Shop revenus`, new URL(p.url()).pathname === '/' && await visible(p, '#products-section'));
  await p.goForward();
  await pret(p, '[data-testid="page-boutique-banniere"]');
  v(`${nom} I4 Suivant : retour à /boutique`, new URL(p.url()).pathname === '/boutique');
  const actifMenu = mobile ? null : await p.getAttribute('[data-testid="nav-tab-shop"]', 'data-actif');
  if (!mobile) v(`${nom} I5 Shop reste actif après l'historique`, actifMenu === 'true');
  if (mobile) {
    await p.click('[data-testid="nav-mobile-marque"]');
  } else {
    await p.click('[data-testid="nav-tab-offers"]');
  }
  await pret(p, '[data-testid="hero-carrousel"]');
  v(`${nom} I6 quitter /boutique par le menu`, new URL(p.url()).pathname === '/');

  // Non-régression de l'accueil
  await p.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  await pret(p, '#products-section');
  await p.waitForTimeout(600);
  v(`${nom} J1 Hero présent`, await visible(p, '[data-testid="hero-carrousel"]'));
  v(`${nom} J2 Publications / Reels présents`, (await p.locator('#mur-publications').count()) === 1);
  v(`${nom} J3 offres montées (lien profond)`, (await p.locator('[data-testid="offres-aimants"], #offers-section').count()) >= 1);
  // Desktop : la carte. Mobile : masquée par décision V543 (« accueil épuré »), elle vit dans le tiroir.
  if (mobile) {
    const masquee = await p.evaluate(() => getComputedStyle(document.querySelector('[data-testid="accueil-carte-spordateur"]')).display);
    await p.click('[data-testid="nav-mobile-menu"]');
    const entree = p.locator('[data-testid="nav-menu-spordateur"]');
    v(`${nom} J4 Spordateur : carte masquée (V543), entrée visible dans le tiroir`, masquee === 'none' && await entree.isVisible() && /Spordateur/.test(await entree.innerText()), masquee);
    await p.keyboard.press('Escape');
  } else {
    const carte = p.locator('[data-testid="accueil-carte-spordateur"]');
    const lien = p.locator('[data-testid="accueil-spordateur-ouvrir"]');
    v(`${nom} J4 Spordateur : carte et lien visibles`, await carte.isVisible() && /Spordateur/.test(await carte.innerText()) && await lien.isVisible() && !!(await lien.getAttribute('href')), await lien.getAttribute('href'));
  }
  const banniereAccueil = await p.locator('#products-section .af-boutique-banniere img, #products-section .af-boutique-banniere video').first().getAttribute('src');
  v(`${nom} J5 Shop d'accueil : sa bannière`, !!banniereAccueil, banniereAccueil);
  await p.locator('#products-section').scrollIntoViewIfNeeded();
  const inline = await p.evaluate(() => getComputedStyle(document.querySelector('.af-boutique-fiche--inline')).display);
  v(`${nom} J6 Shop d'accueil : présentation d'origine`, mobile ? inline === 'none' : inline === 'block', inline);
  await p.locator('.af-boutique-toutvoir:visible, .af-boutique-banniere-cta:visible').first().click();
  await p.waitForTimeout(200);
  v(`${nom} J7 « Découvrir » / « Tout voir » défilent sans quitter l'accueil`, new URL(p.url()).pathname === '/');
  if (mobile) {
    await p.locator('[data-testid="boutique-fiche-carte"] [data-testid^="voir-produit-"]').click();
    await pret(p, `[data-testid="product-detail-${TSHIRT_ID}"]`);
    v(`${nom} J8 accueil mobile : « Voir le produit » garde sa modale`, new URL(p.url()).pathname === '/');
    await capture(p, 'mobile-accueil-modale');
    await p.getByRole('button', { name: 'Fermer' }).click();
  }
  await capture(p, `${nom}-accueil-shop`);

  // Vitrine partenaire : son Shop reste le sien
  await p.route('**/api/coach/vitrine/**', (r) => r.fulfill({ json: { offers: [{ id: 'p1', name: 'Produit partenaire', price: 10, isProduct: true, visible: true, images: [] }], courses: [], concept: {} } }));
  await p.goto(BASE + '/partner/coach-banc', { waitUntil: 'domcontentloaded' });
  await pret(p, '#products-section');
  if (!mobile) {
    await p.click('[data-testid="nav-tab-shop"]');
    await p.waitForTimeout(300);
    v(`${nom} K1 vitrine partenaire : Shop ne part pas vers /boutique`, new URL(p.url()).pathname === '/partner/coach-banc', p.url());
  }

  // Anti-boucle : la page au repos ne multiplie pas les appels API
  await p.goto(BASE + '/boutique', { waitUntil: 'networkidle' }).catch(() => {});
  const avant = appelsApi;
  await p.waitForTimeout(5000);
  v(`${nom} L1 aucune boucle d'appels API au repos`, appelsApi - avant <= 3, appelsApi - avant);
  v(`${nom} L2 aucune erreur JavaScript`, erreurs.length === 0, erreurs.slice(0, 2).join(' | '));
  await ctx.close();
}

/** Bulle de chat sur la fiche : mesurée à toutes les positions de défilement (méthode V543). */
async function verifierBulle(p, nom) {
  // `transition-all` anime aussi le z-index (250 ms mesurées) : il doit atteindre sa valeur finale.
  await p.waitForFunction(() => getComputedStyle(document.querySelector('[data-testid="chat-widget-button"]')).zIndex === '30', null, { timeout: 5000 });
  const m = await p.evaluate(async () => {
    const zone = (s) => { const e = document.querySelector(s); return e ? e.getBoundingClientRect() : null; };
    const touche = (a, b) => a && b && a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
    // Le prix et le titre sont des blocs pleine largeur, vides à droite : on mesure
    // les lignes de TEXTE réellement dessinées, pas la boîte.
    const toucheTexte = (b, s) => {
      const e = document.querySelector(s);
      if (!e) return false;
      const plage = document.createRange();
      plage.selectNodeContents(e);
      return [...plage.getClientRects()].some((l) => touche(b, l));
    };
    const haut = document.documentElement.scrollHeight - innerHeight;
    const r = { positions: 0, prix: 0, titre: 0, puces: 0, cta: 0, ctaBloque: 0, bulle: null };
    for (let y = 0; y <= haut; y += 40) {
      window.scrollTo({ top: y, behavior: 'instant' });
      await new Promise((f) => requestAnimationFrame(f));
      const b = zone('[data-testid="chat-widget-button"]');
      r.bulle = { gauche: Math.round(b.left), droite: Math.round(b.right), bas: Math.round(innerHeight - b.bottom), vue: innerWidth };
      r.positions += 1;
      if (toucheTexte(b, '.af-fiche-prix-premium')) r.prix += 1;
      if (toucheTexte(b, '.af-fiche-titre-premium')) r.titre += 1;
      if ([...document.querySelectorAll('.af-fiche-chip, .af-fiche-qty-btn')].some((c) => touche(b, c.getBoundingClientRect()))) r.puces += 1;
      const c = zone('.af-fiche-cta');
      if (touche(b, c)) r.cta += 1;
      if (c && c.top >= 0 && c.bottom <= innerHeight) {
        // Toute la surface du bouton, pas seulement son centre : la bulle mordait son bord droit.
        const bulle = document.querySelector('[data-testid="chat-widget-button"]');
        for (const fx of [0.01, 0.25, 0.5, 0.75, 0.99]) for (const fy of [0.08, 0.5, 0.92]) {
          const e = document.elementFromPoint(c.left + c.width * fx, c.top + c.height * fy);
          if (e && (bulle === e || bulle.contains(e))) { r.ctaBloque += 1; break; }
        }
      }
    }
    window.scrollTo({ top: 0, behavior: 'instant' });
    return r;
  });
  v(`${nom} S1 bulle présente, à droite, entièrement visible`, m.bulle.droite <= m.bulle.vue && m.bulle.gauche > m.bulle.vue / 2, JSON.stringify(m.bulle));
  v(`${nom} S2 prix jamais recouvert`, m.positions > 3 && m.prix === 0, `${m.positions} positions, ${m.prix} chevauchement`);
  v(`${nom} S3 titre, tailles, couleurs et quantité jamais recouverts`, m.titre === 0 && m.puces === 0, `titre ${m.titre}, sélecteurs ${m.puces}`);
  v(`${nom} S4 bouton d'achat jamais recouvert par la bulle, sur toute sa surface`, m.ctaBloque === 0, `${m.cta} croisements, ${m.ctaBloque} recouvrement`);
}

/** Petit écran, comme V543, et hors de la fiche : la bulle garde sa place. */
async function parcoursBulle(browser) {
  const ctx = await browser.newContext({ ...devices['iPhone 13'], viewport: { width: 360, height: 640 }, serviceWorkers: 'block' });
  await verrouiller(ctx);
  const p = await ctx.newPage();
  await p.goto(BASE + URL_TSHIRT, { waitUntil: 'domcontentloaded' });
  await pret(p, `[data-testid="fiche-produit-${TSHIRT_ID}"]`);
  await pret(p, '[data-testid="chat-widget-button"]');
  await p.waitForTimeout(500);
  await verifierBulle(p, 'mobile360');
  await capture(p, 'mobile360-fiche');
  const cote = () => p.evaluate(() => { const b = document.querySelector('[data-testid="chat-widget-button"]').getBoundingClientRect(); return b.left < innerWidth / 2 ? 'gauche' : 'droite'; });
  const repere = () => p.evaluate(() => document.body.hasAttribute('data-af-fiche-produit'));
  await p.click('[data-testid="page-boutique-retour"]');
  await pret(p, '[data-testid="page-boutique-banniere"]');
  await p.waitForTimeout(500);
  v('mobile360 S5 liste /boutique : bulle à sa place d\'origine', (await cote()) === 'gauche' && !(await repere()));
  await p.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  await pret(p, '[data-testid="chat-widget-button"]');
  await p.waitForTimeout(500);
  v('mobile360 S6 accueil : bulle à sa place d\'origine', (await cote()) === 'gauche' && !(await repere()));
  // La position choisie au doigt reste prioritaire, et le chat s'ouvre toujours.
  await p.evaluate((u) => { localStorage.setItem('afroboost_bulle_chat', JSON.stringify({ x: 20, y: 300 })); history.pushState({}, '', u); dispatchEvent(new PopStateEvent('popstate')); }, URL_TSHIRT);
  await pret(p, `[data-testid="fiche-produit-${TSHIRT_ID}"]`);
  await p.reload({ waitUntil: 'domcontentloaded' });
  await pret(p, '[data-testid="chat-widget-button"]');
  await p.waitForTimeout(700);
  v('mobile360 S7 position choisie au doigt conservée', (await cote()) === 'gauche');
  await p.evaluate(() => localStorage.removeItem('afroboost_bulle_chat'));
  await p.reload({ waitUntil: 'domcontentloaded' });
  await pret(p, '[data-testid="chat-widget-button"]');
  await p.click('[data-testid="chat-widget-button"]');
  await pret(p, '[data-testid="chat-widget-window"]');
  v('mobile360 S8 la bulle ouvre toujours le chat', true);
  await ctx.close();
}

// ════════════════════════ B. LES DEUX BANNIÈRES ════════════════════════
async function parcoursBannieres(browser, jeton) {
  reinitialiserBannieres();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, serviceWorkers: 'block' });
  await verrouiller(ctx);
  await ctx.addInitScript(({ email, jeton: j }) => {
    localStorage.setItem('afroboost_jwt', j);
    localStorage.setItem('afroboost_coach_mode', 'true');
    localStorage.setItem('afroboost_coach_user', JSON.stringify({ email, name: 'Banc', role: 'super_admin' }));
    localStorage.setItem('afroboost_coach_tab', 'offers');
  }, { email: SUPER_ADMIN, jeton });
  const p = await ctx.newPage();
  const puts = [];
  p.on('request', (r) => { if (r.method() === 'PUT' && r.url().endsWith('/api/concept')) puts.push(r.postDataJSON()); });
  const visiteur = await browser.newContext({ viewport: { width: 1440, height: 900 }, serviceWorkers: 'block' });
  await verrouiller(visiteur);
  const pub = await visiteur.newPage();
  const lireConcept = async () => (await (await fetch(BASE + '/api/concept')).json());
  const PREFIXES = { boutique: 'boutique_page_banner', accueil: 'home_shop_banner' };

  // Le vrai parcours : Gestion (ouverte d'office) → Offres & Cours → Modifier T-shirt → Medias.
  const ouvrirWizard = async () => {
    await p.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
    await pret(p, 'button:has-text("Offres & Cours")');
    await p.locator('button:has-text("Offres & Cours")').first().click();
    const titre = p.locator('h3', { hasText: 'T-shirt + 1 cours offert' }).first();
    await titre.waitFor({ state: 'attached', timeout: 30000 });
    await titre.locator('xpath=ancestor::div[.//button[normalize-space()="Modifier"]][1]').getByRole('button', { name: 'Modifier', exact: true }).click();
    await p.getByRole('button', { name: '(3) Medias', exact: true }).click();
    await pret(p, '[data-testid="banniere-page-boutique-titre"]');
  };
  const deplier = async (tid) => {
    const ouvert = await p.locator(`[data-testid="${tid}-section"]`).evaluate((e) => e.open);
    if (!ouvert) await p.click(`[data-testid="${tid}-titre"]`);
  };

  /** Une bannière, de bout en bout, l'autre devant rester strictement identique. */
  async function parcoursCible(cible, tid, fichierImage) {
    const prefixe = PREFIXES[cible];
    const autre = PREFIXES[cible === 'boutique' ? 'accueil' : 'boutique'];
    const n = (s) => `${cible} ${s}`;
    const autreAvant = JSON.stringify(CHAMPS(await lireConcept(), autre));
    const autreIntacte = async () => JSON.stringify(CHAMPS(await lireConcept(), autre)) === autreAvant;
    const racine = p.locator(`[data-testid="${tid}-section"]`);
    const selMedia = cible === 'boutique' ? '[data-testid="page-boutique-banniere"]' : '#products-section .af-boutique-banniere';
    const urlPublique = cible === 'boutique' ? '/boutique' : '/';
    const champ = (c, k) => c[`${prefixe}_${k}`];

    // Image, recadrage, zoom
    await ouvrirWizard();
    await deplier(tid);
    await racine.locator('input[type="file"]').setInputFiles(path.join(FICHIERS, fichierImage));
    await pret(p, `[data-testid="${tid}-apercu-img"]`);
    v(n('P1 import image : aperçu'), true);
    await p.click(`[data-testid="${tid}-cadrer"]`);
    await pret(p, `[data-testid="${tid}-cadrage-zoom"]`);
    await p.waitForTimeout(400);
    await capture(p, `bannieres-${cible}-cadrage`);
    await p.locator(`[data-testid="${tid}-cadrage-zoom"]`).fill('1.8');
    await p.waitForTimeout(400);
    await p.click(`[data-testid="${tid}-cadrage-valider"]`);
    await p.click(`[data-testid="${tid}-enregistrer"]`);
    await pret(p, `[data-testid="${tid}-etat-ok"]`);
    const c1 = await lireConcept();
    const crop = champ(c1, 'crop') || {};
    v(n('P2 image et cadrage sauvegardés'), /^\/api\/files\//.test(champ(c1, 'url')) && champ(c1, 'type') === 'image' && crop.zoom === 1.8, JSON.stringify(crop));
    v(n('P3 l\'autre bannière n\'a pas bougé'), await autreIntacte());

    await pub.goto(BASE + urlPublique, { waitUntil: 'domcontentloaded' });
    await pret(pub, `${selMedia} img`);
    const style = await pub.getAttribute(`${selMedia} img`, 'style');
    v(n('P4 rendu public : son média et son zoom'), (await pub.getAttribute(`${selMedia} img`, 'src')) === champ(c1, 'url') && /scale\(1\.8\)/.test(style || ''), style);
    await pub.locator(`${selMedia}`).first().scrollIntoViewIfNeeded();
    await capture(pub, `bannieres-${cible}-public-image`);

    await ouvrirWizard();
    await deplier(tid);
    await pret(p, `[data-testid="${tid}-apercu-img"]`);
    v(n('P5 rechargement : média et cadrage restitués'),
      (await p.getAttribute(`[data-testid="${tid}-apercu-img"]`, 'src')) === champ(c1, 'url')
      && /×1\.80/.test(await p.innerText(`[data-testid="${tid}-cadrage-resume"]`)));

    // Vidéo, découpe, miniature
    await racine.locator('input[type="file"]').setInputFiles(path.join(FICHIERS, 'clip.webm'));
    await pret(p, `[data-testid="${tid}-apercu-video"] [data-testid="vte-timeline"]`);
    const video = racine.locator('[data-testid="video-trim-editor"]');
    for (let i = 0; i < 10; i += 1) await video.locator('[data-testid="vte-debut-plus"]').click();
    for (let i = 0; i < 10; i += 1) await video.locator('[data-testid="vte-fin-moins"]').click();
    // Miniature : l'envoi échoue une fois (erreur claire, nouvel essai possible).
    const ROUTE_UPLOAD = '**/api/coach/upload-asset';
    await p.route(ROUTE_UPLOAD, (route) => route.abort(), { times: 1 });
    await video.locator('[data-testid="vte-capturer"]').click();
    await pret(p, `[data-testid="${tid}-mini-erreur"]`);
    v(n('R1 échec de l\'envoi : erreur claire, sans URL temporaire'), /a échoué.*conservée.*Réessayez/.test(await p.innerText(`[data-testid="${tid}-mini-erreur"]`))
      && !(await racine.locator('[data-testid="vte-miniature-apercu"]').count()));
    // Puis un envoi lent : le bouton doit être bloqué DÈS le clic, pas seulement après la capture.
    let libererEnvoi;
    const envoiRetenu = new Promise((res) => { libererEnvoi = res; });
    await p.route(ROUTE_UPLOAD, async (route) => { await envoiRetenu; await route.continue(); }, { times: 1 });
    const putsAvant = puts.length;
    const desLeClic = await p.evaluate(async (id) => {
      const racineCible = document.querySelector(`[data-testid="${id}-section"]`);
      racineCible.querySelector('[data-testid="vte-capturer"]').click();
      await Promise.resolve();
      await new Promise((r) => setTimeout(r, 0));
      return document.querySelector(`[data-testid="${id}-enregistrer"]`).disabled;
    }, tid);
    v(n('R2 Enregistrer bloqué dès le clic sur Capturer'), desLeClic === true);
    await pret(p, `[data-testid="${tid}-mini-envoi"]`);
    v(n('R3 indicateur « Enregistrement de la miniature... »'), (await p.innerText(`[data-testid="${tid}-mini-envoi"]`)).includes('Enregistrement de la miniature...'));
    await p.waitForTimeout(800);
    v(n('R4 pendant l\'envoi : bouton toujours bloqué, aucune sauvegarde'), await p.locator(`[data-testid="${tid}-enregistrer"]`).isDisabled() && puts.length === putsAvant);
    await capture(p, `bannieres-${cible}-miniature-envoi`);
    libererEnvoi();
    await p.unroute(ROUTE_UPLOAD);
    // La capture puis l'envoi prennent du temps : on enregistre une fois la VRAIE
    // miniature reçue du serveur (son URL), comme le ferait un coach qui la voit s'afficher.
    await p.waitForFunction((id) => {
      const racineCible = document.querySelector(`[data-testid="${id}-section"]`);
      const img = racineCible.querySelector('[data-testid="vte-miniature-apercu"]');
      const e = document.querySelector(`[data-testid="${id}-enregistrer"]`);
      return img && img.getAttribute('src').startsWith('/api/files/') && e && !e.disabled;
    }, tid, { timeout: 30000 });
    await capture(p, `bannieres-${cible}-video`);
    await p.click(`[data-testid="${tid}-enregistrer"]`);
    await pret(p, `[data-testid="${tid}-etat-ok"]`);
    const c2 = await lireConcept();
    const debut = champ(c2, 'trim_start'); const fin = champ(c2, 'trim_end');
    v(n('P6 vidéo : découpe sauvegardée'), champ(c2, 'type') === 'video' && debut > 0.5 && fin > debut && fin < 8, `${debut}→${fin}`);
    v(n('P7 vidéo : miniature sauvegardée (jamais blob:)'), /^\/api\/files\//.test(champ(c2, 'thumbnail')), champ(c2, 'thumbnail'));
    v(n('P8 l\'autre bannière n\'a pas bougé'), await autreIntacte());

    await pub.goto(BASE + urlPublique, { waitUntil: 'domcontentloaded' });
    await pret(pub, `${selMedia} video`);
    await pub.locator(selMedia).first().scrollIntoViewIfNeeded();
    v(n('P9 rendu public : vidéo et miniature'), (await pub.getAttribute(`${selMedia} video`, 'poster')) === champ(c2, 'thumbnail'));
    await pub.waitForFunction((s) => { const e = document.querySelector(`${s} video`); return e && e.readyState >= 2; }, selMedia, { timeout: 20000 });
    await pub.waitForTimeout(1500);
    const t1 = await pub.evaluate((s) => document.querySelector(`${s} video`).currentTime, selMedia);
    v(n('P10 rendu public : lecture dans le segment découpé'), t1 >= debut - 0.2 && t1 <= fin + 0.4, `t=${t1.toFixed(2)} dans [${debut}, ${fin}]`);

    await ouvrirWizard();
    await deplier(tid);
    await pret(p, `[data-testid="${tid}-apercu-video"] [data-testid="vte-timeline"]`);
    const debutAffiche = await racine.locator('[data-testid="vte-debut-precis"]').innerText();
    v(n('P11 rechargement : découpe restituée dans l\'éditeur'), debutAffiche.includes(String(debut).replace(/\.0$/, '')), `${debutAffiche} / ${debut}`);

    // Retirer puis restaurer
    await p.click(`[data-testid="${tid}-retirer"]`);
    await pret(p, `[data-testid="${tid}-etat-ok"]`);
    const c3 = await lireConcept();
    v(n('P12 retirer : tout est vidé'), champ(c3, 'url') === '' && champ(c3, 'trim_end') === 0 && champ(c3, 'thumbnail') === '');
    v(n('P13 retirer n\'efface pas l\'autre'), await autreIntacte());
    await pub.goto(BASE + urlPublique, { waitUntil: 'domcontentloaded' });
    await pret(pub, selMedia);
    v(n('P14 sans média : dégradé, jamais la bannière de l\'autre'), (await pub.locator(`${selMedia} img, ${selMedia} video`).count()) === 0);
    await p.click(`[data-testid="${tid}-restaurer"]`);
    await p.click(`[data-testid="${tid}-enregistrer"]`);
    await pret(p, `[data-testid="${tid}-etat-ok"]`);
    const c4 = await lireConcept();
    v(n('P15 restaurer : média, découpe et miniature revenus'), champ(c4, 'url') === champ(c2, 'url') && champ(c4, 'trim_end') === fin && champ(c4, 'thumbnail') === champ(c2, 'thumbnail'));
  }

  await ouvrirWizard().catch(async (e) => { await capture(p, 'echec-wizard'); throw e; });
  v('M1 Gestion → Offres & Cours → Modifier T-shirt → Medias : les deux rubriques',
    await visible(p, '[data-testid="banniere-boutique-titre"]') && await visible(p, '[data-testid="banniere-page-boutique-titre"]'));
  v('M2 un seul éditeur : même composant pour les deux', (await p.locator('details[data-testid$="-section"]').count()) === 2);
  await capture(p, 'bannieres-deux-rubriques');
  try {
    await parcoursCible('boutique', 'banniere-page-boutique', 'banniere-a.png');
    await parcoursCible('accueil', 'banniere-boutique', 'banniere-b.png');
  } catch (e) { await capture(p, 'echec-bannieres'); throw e; }

  // Anti-écrasement : ce dashboard a lu le concept AVANT, puis on enregistre une bannière,
  // puis on modifie un réglage général SANS recharger.
  await p.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  await pret(p, 'button:has-text("Ma Vitrine")');
  await p.waitForTimeout(1500);
  await p.locator('button:has-text("Offres & Cours")').first().click();
  const titre = p.locator('h3', { hasText: 'T-shirt + 1 cours offert' }).first();
  await titre.waitFor({ state: 'attached', timeout: 30000 });
  await titre.locator('xpath=ancestor::div[.//button[normalize-space()="Modifier"]][1]').getByRole('button', { name: 'Modifier', exact: true }).click();
  await p.getByRole('button', { name: '(3) Medias', exact: true }).click();
  await deplier('banniere-page-boutique');
  await p.locator('[data-testid="banniere-page-boutique-section"] input[type="file"]').setInputFiles(path.join(FICHIERS, 'banniere-b.png'));
  await pret(p, '[data-testid="banniere-page-boutique-apercu-img"]');
  await p.click('[data-testid="banniere-page-boutique-enregistrer"]');
  await pret(p, '[data-testid="banniere-page-boutique-etat-ok"]');
  const reference = await lireConcept();
  await p.getByRole('button', { name: 'Fermer', exact: true }).first().click();
  await p.locator('button:has-text("Ma Vitrine")').first().click();
  await pret(p, '[data-testid="banniere-boutique-renvoi"]');
  v('N1 « Ma Vitrine » : plus d\'éditeur de bannière, un simple renvoi', (await p.locator('[data-testid="banniere-boutique-editeur"], [data-testid$="-section"] input[type="file"]').count()) === 0);
  await capture(p, 'bannieres-ma-vitrine-renvoi');
  const nbAvant = puts.length;
  // Un vrai champ de `concept` : l'URL du logo.
  const champ = p.locator('input[type="url"][placeholder="https://..."]:visible').first();
  const valeur = await champ.inputValue();
  await champ.fill('https://example.test/logo-banc.png');
  await p.waitForTimeout(2500);
  const nouveaux = puts.slice(nbAvant);
  v('N2 l\'enregistrement général s\'est bien déclenché, avec le réglage modifié', nouveaux.some((b) => b.logoUrl === 'https://example.test/logo-banc.png'), nouveaux.length);
  const banniere = /^(home_shop|boutique_page)_banner/;
  const generaux = puts.filter((b) => Object.keys(b).some((k) => !banniere.test(k)));
  v('N3 aucun enregistrement général de la session ne porte une bannière', generaux.length >= 1 && generaux.every((b) => !Object.keys(b).some((k) => banniere.test(k))), `${generaux.length} PUT généraux`);
  const apres = await lireConcept();
  v('N4 les deux bannières sont intactes en base',
    JSON.stringify(CHAMPS(apres, 'home_shop_banner')) === JSON.stringify(CHAMPS(reference, 'home_shop_banner'))
    && JSON.stringify(CHAMPS(apres, 'boutique_page_banner')) === JSON.stringify(CHAMPS(reference, 'boutique_page_banner')));
  await champ.fill(valeur);
  await p.waitForTimeout(1500);

  // Coach connecté : l'URL de boutique montre la boutique, et il retrouve son tableau de bord.
  await p.goto(BASE + '/boutique', { waitUntil: 'domcontentloaded' });
  await pret(p, '[data-testid="page-boutique-banniere"]');
  v('Q1 coach connecté sur /boutique : la page, pas le dashboard', !(await visible(p, 'button:has-text("Ma Vitrine")')));
  await p.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  await pret(p, 'button:has-text("Ma Vitrine")');
  v('Q2 coach connecté sur / : son tableau de bord, intact', true);
  await p.goto(BASE + '/?visitor=true', { waitUntil: 'domcontentloaded' });
  await pret(p, '[data-testid="nav-tab-shop"]');
  await p.click('[data-testid="nav-tab-shop"]');
  await pret(p, '[data-testid="page-boutique-banniere"]');
  v('Q3 Vue Visiteur : ?visitor=true conservé vers /boutique', new URL(p.url()).search === '?visitor=true' && new URL(p.url()).pathname === '/boutique', p.url());
  await p.click('[data-testid="nav-tab-all"]');
  await pret(p, '[data-testid="hero-carrousel"]');
  v('Q4 Vue Visiteur : retour accueil sans basculer au dashboard', new URL(p.url()).search === '?visitor=true' && !(await visible(p, 'button:has-text("Ma Vitrine")')), p.url());
  await visiteur.close();
  await ctx.close();
}

// ════════════════════════════════════════════════════════════════════════
(async () => {
  for (const f of ['tshirt-1.jpg', 'tshirt-2.jpg', 'banniere-a.png', 'banniere-b.png', 'clip.webm']) {
    if (!FICHIERS || !fs.existsSync(path.join(FICHIERS, f))) { console.error('ARRÊT : fixture manquante ' + f); process.exit(2); }
  }
  await exigerIsolation();
  reinitialiserBannieres();
  // Jeton signé avec le secret de la pile locale, jamais affiché, expire en 2 h.
  const jeton = execFileSync('python3', ['-c', 'import jwt,sys,time;print(jwt.encode({"email":sys.argv[1],"type":"coach","iat":int(time.time()),"exp":int(time.time())+7200},"pw-local-secret",algorithm="HS256"))', SUPER_ADMIN], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
  const browser = await chromium.launch({ args: ['--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1', '--disable-background-networking'] });
  const garde = async (nom, f) => { try { await f(); } catch (e) { v(`${nom} : parcours interrompu`, false, String(e.message).split('\n').slice(0, 8).join(' | ')); } };
  const seul = process.env.SEUL || '';
  if (!seul || seul === 'desktop') await garde('desktop', () => parcoursVisiteur(browser, 'desktop', { viewport: { width: 1440, height: 900 } }));
  if (!seul || seul === 'mobile') await garde('mobile', () => parcoursVisiteur(browser, 'mobile', { ...devices['iPhone 13'] }));
  if (!seul || seul === 'mobile') await garde('mobile360', () => parcoursBulle(browser));
  if (!seul || seul === 'bannieres') await garde('bannières', () => parcoursBannieres(browser, jeton));
  await browser.close();
  console.log(`\nZ1 requêtes non locales coupées : ${coupes.length}`);
  [...new Set(coupes)].forEach((c) => console.log('   ' + c));
  const ko = resultats.filter((r) => !r.ok);
  console.log(`\n${resultats.length - ko.length}/${resultats.length} OK`);
  ko.forEach((r) => console.log('  KO ' + r.nom));
  process.exit(ko.length ? 1 : 0);
})();
