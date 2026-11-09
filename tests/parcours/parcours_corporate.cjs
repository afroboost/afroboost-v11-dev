/**
 * V657 — PARCOURS « AFROBOOST CORPORATE », sur la pile LOCALE (pile_locale.py) : vraie application,
 * base de test, données fictives, faux Stripe / faux Resend. Aucun paiement, aucun e-mail réel.
 *
 * LANCEMENT (depuis la racine, le serveur tournant déjà dans reseau_local.sb) :
 *   CAPTURES=<hors dépôt> NODE_PATH=$HOME/.claude/skills/gstack/node_modules node tests/parcours/parcours_corporate.cjs
 */
const { chromium } = require('playwright');
const { execFileSync } = require('child_process');
const path = require('path');

const BASE = 'http://127.0.0.1:8001';
const CAPTURES = process.env.CAPTURES;
const ADMIN = 'contact.artboost@gmail.com';
const FIX = path.join(__dirname, 'fixtures_corporate.py');
const EVT = 'v657-evt-corporate';
const resultats = [];
const v = (nom, ok, detail = '') => { resultats.push({ nom, ok }); console.log(`${ok ? 'OK ' : 'KO '} ${nom}${detail !== '' ? ' — ' + detail : ''}`); };
const fixture = (...a) => execFileSync('python3', [FIX, ...a], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
const etat = () => JSON.parse(fixture('etat'));
const jeton = execFileSync('python3', ['-c', 'import jwt,time;print(jwt.encode({"email":"contact.artboost@gmail.com","type":"coach","iat":int(time.time()),"exp":int(time.time())+3600},"pw-local-secret",algorithm="HS256"))'], { encoding: 'utf8' }).trim();
const id = (x) => `[data-testid="${x}"]`;
const capture = async (p, nom) => { if (CAPTURES) await p.screenshot({ path: path.join(CAPTURES, nom + '.jpg'), type: 'jpeg', quality: 80, fullPage: true }); };

async function api(chemin, { method = 'GET', body, auth = true } = {}) {
  const r = await fetch(BASE + chemin, { method, headers: Object.assign({ 'Content-Type': 'application/json' }, auth ? { Authorization: 'Bearer ' + jeton } : {}), body: body ? JSON.stringify(body) : undefined });
  let d = null; try { d = await r.json(); } catch (e) { d = null; }
  return { status: r.status, d };
}

async function nouveauContexte(browser, viewport, admin) {
  const ctx = await browser.newContext({ viewport, serviceWorkers: 'block' });
  await ctx.route('**/*', (route) => {
    const u = new URL(route.request().url());
    if (['data:', 'blob:'].includes(u.protocol) || u.hostname === '127.0.0.1') return route.continue();
    return route.abort();
  });
  if (admin) {
    await ctx.addInitScript(({ j, mail }) => {
      localStorage.setItem('afroboost_jwt', j);
      localStorage.setItem('afroboost_coach_mode', 'true');
      localStorage.setItem('afroboost_coach_user', JSON.stringify({ email: mail, name: 'Banc', role: 'super_admin' }));
      localStorage.setItem('afroboost_coach_tab', 'offers');
    }, { j: jeton, mail: ADMIN });
  }
  const p = await ctx.newPage();
  p.erreurs = [];
  p.on('pageerror', (e) => p.erreurs.push(String(e).slice(0, 160)));
  return { ctx, p };
}

async function ouvrirCorporate(browser, viewport) {
  const { ctx, p } = await nouveauContexte(browser, viewport, true);
  await p.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  const carte = p.getByRole('button', { name: /^Corporate$/ }).first();
  try {
    await carte.waitFor({ timeout: 60000 });
  } catch (e) {
    await capture(p, 'ZZ-diagnostic-dashboard');
    console.log('boutons visibles :', JSON.stringify(await p.evaluate(() => [...document.querySelectorAll('button')].map((b) => b.textContent.trim()).filter(Boolean).slice(0, 40))));
    throw e;
  }
  await carte.click();
  await p.waitForSelector(id('corporate-contrats'), { timeout: 20000 });
  return { ctx, p };
}

async function inscrire(p, nom, email) {
  await p.fill('[aria-label="Prénom et nom"]', nom);
  await p.fill('[aria-label="E-mail"]', email);
  await p.check('input[type="checkbox"]').catch(() => {});
  await p.click(id('corp-public-inscrire'));
}

(async () => {
  fixture('poser');
  const browser = await chromium.launch({ headless: true });
  let token = '';
  try {
    // ── A. Desktop 1440 : devis -> signature -> édition -> lien + QR ──
    let { ctx, p } = await ouvrirCorporate(browser, { width: 1440, height: 900 });
    await p.click(id('corp-nouveau'));
    await p.waitForSelector(id('corp-prospect'));
    await p.waitForFunction(() => document.querySelectorAll('[data-testid="corp-prospect"] option').length > 1, null, { timeout: 15000 });
    await p.selectOption(id('corp-prospect'), { label: 'Corporate Test SA — Neuchâtel' });
    await p.selectOption(id('corp-places'), '5');
    await p.selectOption(id('corp-mois'), '3');
    await p.fill(id('corp-debut'), '2026-12');
    await p.waitForFunction(() => /350\.00 CHF \/ mois · total 1050\.00 CHF/.test(document.querySelector('[data-testid="corp-prix"]').textContent), null, { timeout: 10000 });
    v('prix calculé par le serveur : 350/mois, total 1050', true);
    await capture(p, 'A1-desktop-nouveau-devis');
    await p.click(id('corp-creer'));
    await p.waitForSelector(id('corp-signer'), { timeout: 15000 });
    v('devis créé (statut Devis)', /Devis/.test(await p.locator(id('corp-contrat')).first().textContent()));
    await p.click(id('corp-signer'));
    await p.waitForSelector(id('corp-lien'), { timeout: 15000 });
    v('signature confirmée (statut Signé)', /Signé/.test(await p.locator(id('corp-contrat')).first().textContent()));
    if (!(await p.locator(id('corp-lier-2026-12')).count())) await p.click(id('corp-details'));
    await p.waitForSelector(id('corp-lier-2026-12'));
    await p.selectOption('[aria-label="Événement pour 2026-12"]', EVT);
    await p.click(id('corp-lier-2026-12'));
    await p.waitForFunction(() => /places retenues/.test((document.querySelector('[data-testid="corp-msg"]') || {}).textContent || ''), null, { timeout: 15000 });
    v('édition de décembre liée à l’événement (places retenues)', etat().retenues === 1, JSON.stringify(etat()));
    v('janvier et février restent « À planifier »', (await p.getByText('2027-01 · À planifier').count()) === 1 && (await p.getByText('2027-02 · À planifier').count()) === 1);
    await p.click(id('corp-lien'));
    await p.waitForSelector(id('corp-lien-url'));
    const url = (await p.locator(id('corp-lien-url')).textContent()).trim();
    token = url.split('/entreprise/')[1];
    v('lien privé + QR visibles', /\/entreprise\/[A-Za-z0-9_-]{32,}$/.test(url) && (await p.locator(`${id('corp-contrat')} svg`).count()) > 0, url.replace(/\/entreprise\/.*/, '/entreprise/<jeton masqué>'));
    await capture(p, 'A2-desktop-contrat-signe-lien-qr');
    v('aucune erreur JS côté admin (desktop)', p.erreurs.length === 0, p.erreurs.join(' | '));
    await ctx.close();

    // ── B. Mobile 390 : l'employée s'inscrit à 0 CHF ──
    ({ ctx, p } = await nouveauContexte(browser, { width: 390, height: 844 }, false));
    await p.goto(`${BASE}/entreprise/${token}`, { waitUntil: 'domcontentloaded' });
    await p.waitForSelector(id('corp-public-entreprise'), { timeout: 30000 });
    v('page publique : entreprise affichée', (await p.locator(id('corp-public-entreprise')).textContent()) === 'Corporate Test SA');
    v('janvier « À planifier », sans date inventée', /À planifier/.test(await p.locator(id('corp-edition-2027-01')).textContent()));
    v('décembre : date réelle et 5 places', /16\.12\.2026 à 19h00/.test(await p.locator(id('corp-edition-2026-12')).textContent()) && /5 place/.test(await p.locator(id('corp-edition-2026-12')).textContent()));
    const largeur = await p.evaluate(() => document.documentElement.scrollWidth);
    v('mobile : aucune barre horizontale', largeur <= 390, String(largeur));
    await capture(p, 'B1-mobile-invitation');
    await inscrire(p, 'Employée Une', 'employee1@example.test');
    await p.waitForSelector(id('corp-public-billet'), { timeout: 20000 });
    const code = (await p.locator(id('corp-public-code')).textContent()).trim();
    v('billet à 0 CHF + QR d’entrée', /0 CHF/.test(await p.locator(id('corp-public-billet')).textContent()) && /^AF[0-9A-F]{8}$/.test(code) && (await p.locator(`${id('corp-public-billet')} svg`).count()) > 0, code);
    await capture(p, 'B2-mobile-billet');
    await p.goto(`${BASE}/entreprise/${token}`, { waitUntil: 'domcontentloaded' });
    await p.waitForSelector(id('corp-public-form'));
    await inscrire(p, 'Employée Une bis', 'EMPLOYEE1@example.test');
    await p.waitForSelector(id('corp-public-msg'));
    v('même identité (majuscules) refusée', /déjà inscrite/.test(await p.locator(id('corp-public-msg')).textContent()));
    await capture(p, 'B3-mobile-doublon-refuse');
    for (let i = 2; i <= 5; i += 1) {
      const r = await api(`/api/corporate/invitation/${token}/inscription`, { auth: false, body: { mois: '2026-12', nom: 'Employé ' + i, email: `employee${i}@example.test`, terms_accepted: true }, method: 'POST' });
      if (r.status !== 200) v('inscription API ' + i, false, String(r.status));
    }
    const plein = await api(`/api/corporate/invitation/${token}/inscription`, { auth: false, method: 'POST', body: { mois: '2026-12', nom: 'Sixième', email: 'employee6@example.test', terms_accepted: true } });
    v('6e personne : 409 « places prises »', plein.status === 409 && /places/.test(plein.d.detail), JSON.stringify(plein));
    await p.goto(`${BASE}/entreprise/${token}`, { waitUntil: 'domcontentloaded' });
    await p.waitForSelector(id('corp-public-entreprise'));
    v('page : 0 place restante, formulaire masqué', /0 place/.test(await p.locator(id('corp-edition-2026-12')).textContent()) && (await p.locator(id('corp-public-form')).count()) === 0);
    await capture(p, 'B4-mobile-complet');
    await ctx.close();

    // ── C. Mobile 390 admin : inscrits, annulation = la place revient ──
    ({ ctx, p } = await ouvrirCorporate(browser, { width: 390, height: 844 }));
    await p.click(id('corp-details'));
    await p.getByRole('button', { name: 'Inscrits' }).first().click();
    await p.waitForSelector(id('corp-inscriptions-2026-12'));
    v('admin : 5 inscrits listés', /5 inscrit/.test(await p.locator(id('corp-inscriptions-2026-12')).textContent()));
    p.once('dialog', (d) => d.accept());
    await p.locator(`${id('corp-inscriptions-2026-12')} [aria-label="Annuler l’inscription"]`).first().click();
    await p.waitForFunction(() => /4 inscrit/.test(document.querySelector('[data-testid="corp-inscriptions-2026-12"]').textContent), null, { timeout: 10000 });
    v('annulation : 4 inscrits, 1 place libre', /1 place\(s\) libre/.test(await p.locator(id('corp-inscriptions-2026-12')).textContent()));
    const largeurA = await p.evaluate(() => document.documentElement.scrollWidth);
    v('admin mobile : aucune barre horizontale', largeurA <= 390, String(largeurA));
    await capture(p, 'C1-mobile-admin-inscrits');
    await ctx.close();
    const inv = await api(`/api/corporate/invitation/${token}`, { auth: false });
    v('la place annulée revient à l’entreprise (1 restante)', inv.d.editions[0].places_restantes === 1, JSON.stringify(inv.d.editions[0]));

    // ── D. Factures : devis + facture de décembre depuis l’écran, liste « Entreprise » ──
    ({ ctx, p } = await ouvrirCorporate(browser, { width: 1440, height: 900 }));
    await p.click(id('corp-details'));
    const dl1 = p.waitForEvent('download');
    await p.click(id('corp-devis-pdf'));
    v('devis PDF téléchargé (DEVIS-AAAA-NNNN)', /^DEVIS-\d{4}-\d{4}\.pdf$/.test((await dl1).suggestedFilename()), (await dl1).suggestedFilename());
    const dl2 = p.waitForEvent('download');
    await p.click(id('corp-facture-2026-12'));
    v('facture de décembre téléchargée (AF-CORP-AAAA-NNNN)', /^AF-CORP-\d{4}-\d{4}\.pdf$/.test((await dl2).suggestedFilename()), (await dl2).suggestedFilename());
    await p.waitForFunction(() => /Émise/.test(document.querySelector('[data-testid="corp-contrat"]').textContent), null, { timeout: 10000 });
    await capture(p, 'D1-desktop-facturation-contrat');
    await ctx.close();

    // ── E. Non-régression : invitation payante existante (/i/) + paiement classique ──
    const camp = await api('/api/referral/campaigns', { method: 'POST', body: { type: 'event_paid', status: 'active', offer_id: EVT, course_id: 'v657-cours-corporate', occurrence: '2026-12-16T19:00:00', title: 'Invitation test V657' } });
    v('invitation payante créée (route existante)', camp.status === 201 && camp.d.share_token, String(camp.status) + ' ' + ((camp.d && camp.d.detail) || ''));
    if (camp.d && camp.d.share_token) {
      ({ ctx, p } = await nouveauContexte(browser, { width: 390, height: 844 }, false));
      await p.goto(`${BASE}/i/${camp.d.share_token}`, { waitUntil: 'domcontentloaded' });
      await p.waitForSelector(id('inv-pub-titre'), { timeout: 30000 });
      const restantes = await p.locator(id('inv-pub-places-restantes')).textContent().catch(() => '');
      v('page /i/ existante : titre + places restantes (45 − 5 retenues = 40)', /40/.test(restantes), restantes);
      await capture(p, 'E1-mobile-invitation-payante-existante');
      await p.click(id('inv-pub-cta'));
      await p.waitForURL(/faux-stripe/, { timeout: 20000 }).catch(() => {});
      v('réservation payante : redirection vers le paiement (faux Stripe)', /faux-stripe/.test(p.url()), p.url());
      await capture(p, 'E2-mobile-paiement-test');
      await ctx.close();
    }
    const classique = await api('/api/create-checkout-session', { method: 'POST', auth: false, body: { amount: 30, productName: "Cours à l'unité", originUrl: BASE, offerId: 'fea0ab6a-8adc-460d-9d7d-bbff57059ca5', quantity: 1, customerEmail: 'classique.v657@example.test' } });
    v('réservation classique (offre ordinaire) : session de paiement ouverte', classique.status === 200 && /faux-stripe/.test(classique.d.url || ''), String(classique.status));
  } catch (e) {
    v('exception du parcours', false, String(e).slice(0, 300));
  } finally {
    await browser.close();
    fixture('nettoyer');
  }
  const ko = resultats.filter((r) => !r.ok).length;
  console.log(`\n${resultats.length - ko}/${resultats.length} OK`);
  process.exit(ko ? 1 : 0);
})();
