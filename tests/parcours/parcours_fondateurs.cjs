// PARCOURS CLIENT — Playwright sur la pile LOCALE (vraie app, base de test, faux Stripe/Resend).
// AUCUN paiement réel, AUCUN e-mail réel, rien en production.
const { chromium, devices } = require('playwright');
const fs = require('fs');
const BASE = 'http://127.0.0.1:8001';
const CAP = __dirname + '/pw_captures';
fs.mkdirSync(CAP, { recursive: true });
const R = []; let OK = 0, KO = 0;
const v = (nom, cond, detail = '') => { (cond ? OK++ : KO++); R.push(`${cond ? 'OK  ' : 'RATE'} ${nom}${cond ? '' : '  [' + String(detail).slice(0, 300) + ']'}`); };
const dialogs = [];
const uid = Date.now().toString(36);

async function page(browser, mobile = false, url = BASE + '/') {
  const ctx = mobile ? await browser.newContext({ ...devices['iPhone 13'] }) : await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  p.on('dialog', async d => { dialogs.push(d.message()); await d.dismiss(); });
  const erreurs = []; const ressources = []; p.on('pageerror', e => erreurs.push(String(e).slice(0, 200)));
  p.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) erreurs.push(m.text().slice(0, 200)); });
  p.on('response', r => { if (r.status() >= 500 && !/\/api\/files\//.test(r.url())) ressources.push(r.status() + ' ' + r.url().replace(BASE, '').slice(0, 80)); });   // /api/files : médias sur le disque du serveur de prod, absents en local
  await p.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  return { ctx, p, erreurs, ressources };
}

async function ouvrirFondateurs(p, tag) {
  await p.waitForSelector('[data-testid="offres-aimants"]', { timeout: 60000 });
  await p.screenshot({ path: `${CAP}/${tag}-1-accueil.png`, fullPage: false });
  const carte = p.locator('[data-testid="aimant-lancement"]');
  v(`${tag}. la carte Fondateurs (aimant « lancement ») est visible`, await carte.count() === 1);
  const texte = (await carte.textContent()) || '';
  v(`${tag}. la carte affiche 59 CHF / mois, places restantes et la date limite`, /59\s*CHF/.test(texte) && /places/i.test(texte) && /30\/09|septembre/i.test(texte), texte.slice(0, 200));
  await carte.click();
  await p.waitForSelector('[data-testid="fiche-nom"]', { timeout: 20000 });
  await p.screenshot({ path: `${CAP}/${tag}-2-fiche.png`, fullPage: false });
  const nom = await p.locator('[data-testid="fiche-nom"]').textContent();
  const prix = await p.locator('[data-testid="fiche-prix"]').textContent();
  v(`${tag}. la fiche s'ouvre : Fondateurs, prix 59 CHF / mois`, /Fondateurs/i.test(nom || '') && /59/.test(prix || ''), `${nom} | ${prix}`);
  const cta = p.locator('[data-testid="fiche-cta"]');
  v(`${tag}. le bouton d'achat est visible dans la fenêtre`, await cta.isVisible());
  const box = await cta.boundingBox();
  v(`${tag}. taille tactile du bouton ≥ 44 px`, box && box.height >= 44, JSON.stringify(box));
  return { click: async (opts) => { for (let i = 0; i < 4; i++) { try { await p.locator('[data-testid="fiche-cta"]').click({ timeout: 8000, ...(opts || {}) }); return; } catch (e) { if (i === 3) throw e; } } } };
}
async function parcours(nom, fn) { if (process.env.PARCOURS && !process.env.PARCOURS.split(',').includes(nom)) return; try { await fn(); } catch (e) { v(`${nom}. ERREUR d'exécution`, false, String(e).split('\n')[0]); } }

(async () => {
  const browser = await chromium.launch({ headless: true });

  await parcours('P1', async () => {
    const { ctx, p, erreurs, ressources } = await page(browser, false);
    const cta = await ouvrirFondateurs(p, 'P1');
    const [nav] = await Promise.all([p.waitForNavigation({ url: /faux-stripe/, timeout: 30000 }).catch(() => null), cta.click()]);
    v('P1. le clic conduit au checkout Stripe (page TEST locale, mode subscription)', !!nav && /faux-stripe/.test(p.url()), p.url());
    await p.screenshot({ path: `${CAP}/P1-3-checkout.png` });
    const montant = await p.locator('[data-testid="faux-montant"]').textContent();
    const methodes = await p.locator('[data-testid="faux-methodes"]').textContent();
    v('P1. montant Stripe = 59.00 CHF / month, mode subscription, carte seule', /59\.00 CHF \/ month/.test(montant || '') && /subscription/.test(montant || '') && (methodes || '').trim() === 'card', `${montant} | ${methodes}`);
    // « Payer (TEST) » : fabrique checkout.session.completed -> VRAI webhook -> success_url
    await Promise.all([p.waitForNavigation({ timeout: 60000 }), p.click('[data-testid="faux-payer"]')]);
    await p.waitForTimeout(2500);
    await p.screenshot({ path: `${CAP}/P1-4-retour.png` });
    v('P1. retour sur le site (URL nettoyée par l\'app, modale « Paiement confirmé »)', /127\.0\.0\.1:8001/.test(p.url()) && /Paiement confirm/i.test(await p.textContent('body')), p.url());
    const corps = await p.textContent('body');
    v('P1. le site confirme le paiement (message visible)', /confirm|merci|code|e-mail|email/i.test(corps || ''), (corps || '').slice(0, 120));
    v('P1. aucune erreur JS bloquante', erreurs.length === 0, erreurs.join(' | '));
    v('P1. aucune réponse 5xx du serveur pendant le parcours (hors médias sur disque, absents en local)', ressources.length === 0, [...new Set(ressources)].join(' | '));
    await ctx.close();
  });

  await parcours('P4', async () => {
    const { ctx, p, erreurs } = await page(browser, true);
    const cta = await ouvrirFondateurs(p, 'P4');
    const scrollX = await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    v('P4. aucun scroll horizontal parasite sur mobile', !scrollX);
    const overflow = await p.evaluate(() => getComputedStyle(document.body).overflow);
    const [nav] = await Promise.all([p.waitForNavigation({ url: /faux-stripe/, timeout: 30000 }).catch(() => null), cta.click()]);
    v('P4. mobile : le bouton d\'achat conduit au checkout', !!nav, p.url());
    await p.screenshot({ path: `${CAP}/P4-3-checkout-mobile.png` });
    await Promise.all([p.waitForNavigation({ timeout: 60000 }), p.click('[data-testid="faux-payer"]')]);
    await p.waitForTimeout(2000);
    await p.screenshot({ path: `${CAP}/P4-4-retour-mobile.png` });
    v('P4. mobile : retour sur le site + modale « Paiement confirmé »', /127\.0\.0\.1:8001/.test(p.url()) && /Paiement confirm/i.test(await p.textContent('body')), p.url());
    v('P4. mobile : aucune erreur JS', erreurs.length === 0, erreurs.join(' | '));
    await ctx.close();
  });

  await parcours('P5', async () => {
    const { ctx, p } = await page(browser, false);
    const cta = await ouvrirFondateurs(p, 'P5');
    const avant = Object.keys(await (await p.request.get(BASE + '/faux-stripe/etat')).json()).length;
    // Deux clics quasi simultanés sur « Choisir cette formule »
    // Double clic RÉEL (deux événements successifs, comme un utilisateur) :
    await Promise.all([p.waitForNavigation({ url: /faux-stripe/, timeout: 30000 }).catch(() => null), p.locator('[data-testid="fiche-cta"]').dblclick({ timeout: 8000 }).catch(() => null)]);
    await p.waitForTimeout(1500);
    const apres = Object.keys(await (await p.request.get(BASE + '/faux-stripe/etat')).json()).length;
    v('P5. double clic réel = UNE seule session de checkout créée (garde checkoutBusy)', apres - avant === 1, `${avant} -> ${apres}`);
    const cs = new URL(p.url()).searchParams.get('cs');
    await Promise.all([p.waitForNavigation({ timeout: 60000 }), p.click('[data-testid="faux-payer"]')]);
    await p.waitForTimeout(1500);
    // Refresh de l'URL de retour + retour arrière
    await p.reload({ waitUntil: 'domcontentloaded' }); await p.waitForTimeout(1500);
    await p.goBack().catch(() => null); await p.waitForTimeout(800);
    // Rejeu du MÊME webhook (Stripe rejoue parfois)
    await p.request.post(BASE + '/faux-stripe/rejouer', { form: { cs } });
    const etat = await (await p.request.get(BASE + '/faux-stripe/etat')).json();
    v('P5. le webhook rejoué répond OK sans erreur', String(etat[cs].webhook) === '200', JSON.stringify(etat[cs]));
    await ctx.close();
  });

  await parcours('P6', async () => {
    const { ctx, p } = await page(browser, false, BASE + '/?utm_source=instagram&utm_medium=reel&utm_campaign=fondateurs_test&utm_content=' + uid);
    await p.waitForSelector('[data-testid="offres-aimants"]', { timeout: 60000 });
    const stocke = await p.evaluate(() => { try { return JSON.parse(localStorage.getItem('af_attribution') || 'null'); } catch (e) { return null; } });
    v('P6. l\'origine UTM est capturée côté navigateur (af_attribution first = instagram)', stocke && stocke.first && stocke.first.source === 'instagram' && stocke.first.campaign === 'fondateurs_test', JSON.stringify(stocke).slice(0, 200));
    const cta = await ouvrirFondateurs(p, 'P6');
    await Promise.all([p.waitForNavigation({ url: /faux-stripe/, timeout: 30000 }).catch(() => null), cta.click()]);
    const cs = new URL(p.url()).searchParams.get('cs');
    const etat = await (await p.request.get(BASE + '/faux-stripe/etat')).json();
    const md = (etat[cs] || {}).metadata || {};
    v('P6. l\'attribution voyage dans les metadata Stripe (attribution_first_source = instagram, content = ' + uid + ')', md.attribution_first_source === 'instagram' && md.attribution_first_content === uid, JSON.stringify(md).slice(0, 300));
    await Promise.all([p.waitForNavigation({ timeout: 60000 }), p.click('[data-testid="faux-payer"]')]);
    await p.waitForTimeout(1500);
    fs.writeFileSync(__dirname + '/pw_p6_cs.txt', cs);
    await ctx.close();
  });

  v('Global. aucune boîte de dialogue bloquante (alert) pendant les parcours', dialogs.length === 0, dialogs.join(' | '));
  await browser.close();
  console.log(R.join('\n'));
  console.log(`\n${OK}/${OK + KO} au vert (Playwright parcours 1, 4, 5, 6)`);
  process.exit(KO ? 1 : 0);
})().catch(e => { console.error('ERREUR', e); process.exit(2); });
