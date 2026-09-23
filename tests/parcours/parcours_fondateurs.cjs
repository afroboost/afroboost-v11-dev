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

// V540 — L'ACCUEIL NE MONTRE PLUS LES TROIS CARTES D'OFFRES.
// Le fil de publications occupe la zone principale ; les offres vivent sous
// l'onglet « Offres ». Ce banc suivait l'ANCIENNE mise en page : il attendait
// `offres-aimants` VISIBLE dès le chargement de l'accueil, et échouait donc sur
// la nouvelle. On reproduit le vrai parcours : charger l'accueil, vérifier qu'il
// est rendu, CLIQUER sur l'onglet, puis attendre les offres.
// Aucun `force`, aucun `visibility:false`, aucun sélecteur affaibli, aucun
// timeout rallongé pour masquer le problème : un vrai clic sur le vrai bouton.
// V541 — LE CHEMIN VERS UN ONGLET DÉPEND DE L'ÉCRAN.
// Sur grand écran la barre horizontale est là. Sur téléphone elle a été
// remplacée par une barre compacte et un tiroir : cliquer `nav-tab-offers`
// n'a plus de sens, le bouton n'est plus affiché. On regarde donc CE QUE LE
// VISITEUR VOIT, et on emprunte le même chemin que lui — sans `force`, sans
// sélecteur affaibli : le hamburger, puis l'entrée du tiroir.
async function ouvrirOnglet(p, cle) {
  const hamburger = p.locator('[data-testid="nav-mobile-menu"]');
  if (await hamburger.isVisible().catch(() => false)) {
    await hamburger.click();
    await p.waitForSelector('[data-testid="nav-mobile-tiroir"]', { timeout: 15000 });
    await p.click('[data-testid="nav-menu-' + cle + '"]');
    return;
  }
  await p.click('[data-testid="nav-tab-' + cle + '"]');
}

async function allerAuxOffres(p) {
  await p.waitForSelector('[data-testid="accueil-colonnes"]', { timeout: 60000 });
  await ouvrirOnglet(p, 'offers');
  await p.waitForSelector('[data-testid="offres-aimants"]', { state: 'visible', timeout: 30000 });
}

async function ouvrirFondateurs(p, tag) {
  await allerAuxOffres(p);
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
  // E1 (16/09) : depuis V528, une offre récurrente demande d'abord l'e-mail (étape modale) quand
  // l'adresse est inconnue ; `click` la remplit et valide, `clickSeul` n'ouvre que l'étape.
  const clickSeul = async (opts) => { for (let i = 0; i < 4; i++) { try { await p.locator('[data-testid="fiche-cta"]').click({ timeout: 8000, ...(opts || {}) }); return; } catch (e) { if (i === 3) throw e; } } };
  const click = async (opts, email) => {
    await clickSeul(opts);
    const etape = p.locator('[data-testid="v528-etape-email"]');
    if (await etape.waitFor({ timeout: 5000 }).then(() => true).catch(() => false)) {
      await p.fill('[data-testid="v528-email-input"]', email || ('pw-' + tag.toLowerCase() + '-' + uid + '@example.com'));
      await p.click('[data-testid="v528-email-continuer"]');
    }
  };
  return { click, clickSeul };
}
const FID = 'cc73f6ee-163a-433d-b5f0-c00c6392b437';
const { execSync } = require('child_process');
const fixture = (action) => execSync('python3 ' + __dirname + '/pw_fixtures.py ' + action, { encoding: 'utf8' }).trim();
const nbSessions = async (p) => Object.keys(await (await p.request.get(BASE + '/faux-stripe/etat')).json()).length;
const abonnements = async (p, email) => (await (await p.request.get(BASE + '/faux-stripe/abonnement?email=' + encodeURIComponent(email))).json());
const checkoutDirect = async (p, email) => p.request.post(BASE + '/api/create-checkout-session', { data: { productName: 'Fondateurs', amount: 59, originUrl: BASE, offerId: FID, quantity: 1, allowPromotionCodes: true, collectShipping: false, customerEmail: email } });
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
    const emailP5 = 'pw-p5-' + uid + '@example.com';
    await p.locator('[data-testid="fiche-cta"]').dblclick({ timeout: 8000 }).catch(() => null);
    await p.waitForTimeout(800);
    const etapeApresDbl = await p.locator('[data-testid="v528-etape-email"]').count();
    v('P5. double clic sur Acheter : 0 checkout créé', (await nbSessions(p)) === avant, `sessions ${avant} -> ${await nbSessions(p)}`);
    // V529 (E1.1) : Acheter n'est jamais un toggle — le 2e clic, qui tombe sur le fond de la
    // modale à peine montée, ne la referme plus. L'étape e-mail RESTE ouverte.
    v('P5. double clic sur Acheter : l\'étape e-mail reste OUVERTE (V529, plus de toggle par le fond)', etapeApresDbl === 1, `étape présente = ${etapeApresDbl}`);
    await p.screenshot({ path: `${CAP}/P5-apres-double-clic.png` });
    if (!etapeApresDbl) { await p.locator('[data-testid="fiche-cta"]').click({ timeout: 8000 }); await p.locator('[data-testid="v528-etape-email"]').waitFor({ timeout: 8000 }); }
    await p.fill('[data-testid="v528-email-input"]', emailP5);
    await Promise.all([p.waitForNavigation({ url: /faux-stripe/, timeout: 30000 }).catch(() => null), p.locator('[data-testid="v528-email-continuer"]').dblclick({ timeout: 8000 }).catch(() => null)]);
    await p.waitForTimeout(1500);
    const apres = await nbSessions(p);
    v('P5. double clic réel sur « Continuer » = UNE seule session de checkout créée (garde checkoutBusy)', apres - avant === 1, `${avant} -> ${apres}`);
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
    const abosP5 = await abonnements(p, emailP5);
    v('P5. refresh + retour + rejeu du webhook = UN seul abonnement, 8 séances (aucun double crédit)', abosP5.n === 1 && abosP5.abonnements[0].remaining_sessions === 8 && abosP5.abonnements[0].total_sessions !== 16, JSON.stringify(abosP5).slice(0, 300));
    await ctx.close();
  });

  await parcours('P6', async () => {
    const { ctx, p } = await page(browser, false, BASE + '/?utm_source=instagram&utm_medium=reel&utm_campaign=fondateurs_test&utm_content=' + uid);
    // V540 : cette attente ne sert qu'à savoir que l'accueil est rendu avant de
    // lire le localStorage — c'est la zone d'accueil qu'on attend, pas les offres.
    await p.waitForSelector('[data-testid="accueil-colonnes"]', { timeout: 60000 });
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

  await parcours('P0', async () => {
    // E1 : landing SEO -> lien Fondateurs -> fiche (le lien porte ?offre=<id>)
    const { ctx, p, erreurs } = await page(browser, true, BASE + '/cours-essai-gratuit-neuchatel');
    const lien = p.locator('a[href*="offre=' + FID + '"]').first();
    v('P0. la landing propose un lien vers l\'offre Fondateurs', (await lien.count()) >= 1);
    const texte = ((await p.textContent('body')) || '').replace(/\s+/g, ' ');
    v('P0. la landing dit 59 CHF / mois, 8 séances, « N places restantes sur 50 », 30 septembre, séances non reportées', /59 CHF/.test(texte) && /8 séances/.test(texte) && /\d+ places? restantes? sur 50/.test(texte) && /30 septembre 2026/.test(texte) && /ne sont pas reportées/.test(texte), texte.slice(0, 200));
    await Promise.all([p.waitForNavigation({ timeout: 30000 }).catch(() => null), lien.click()]);
    await p.waitForSelector('[data-testid="fiche-nom"]', { timeout: 60000 });
    v('P0. le lien ouvre la fiche Fondateurs dans l\'app', /Fondateurs/i.test((await p.locator('[data-testid="fiche-nom"]').textContent()) || ''));
    v('P0. mobile : aucune erreur JS', erreurs.length === 0, erreurs.join(' | '));
    await ctx.close();
  });

  await parcours('P6b', async () => {
    // E1 : lien partenaire court `?offre=<id>&ref=<slug>` -> source partenaire / referral / content = slug
    const { ctx, p } = await page(browser, false, BASE + '/?offre=' + FID + '&ref=coach-test-' + uid);
    await p.waitForSelector('[data-testid="fiche-cta"]', { timeout: 60000 });
    const stocke = await p.evaluate(() => { try { return JSON.parse(localStorage.getItem('af_attribution') || 'null'); } catch (e) { return null; } });
    v('P6b. `?ref=` est capturé (first.source = partenaire, content = slug)', stocke && stocke.first && stocke.first.source === 'partenaire' && stocke.first.content === 'coach-test-' + uid, JSON.stringify(stocke).slice(0, 200));
    await Promise.all([p.waitForNavigation({ url: /faux-stripe/, timeout: 30000 }).catch(() => null), (async () => { await p.locator('[data-testid="fiche-cta"]').click(); await p.locator('[data-testid="v528-etape-email"]').waitFor({ timeout: 8000 }).catch(() => null); await p.fill('[data-testid="v528-email-input"]', 'pw-p6b-' + uid + '@example.com'); await p.click('[data-testid="v528-email-continuer"]'); })()]);
    const cs = new URL(p.url()).searchParams.get('cs');
    const md = ((await (await p.request.get(BASE + '/faux-stripe/etat')).json())[cs] || {}).metadata || {};
    v('P6b. le lien partenaire voyage dans les metadata Stripe (attribution_first_source = partenaire)', md.attribution_first_source === 'partenaire' && md.attribution_first_content === 'coach-test-' + uid && md.offer_id === FID, JSON.stringify(md).slice(0, 300));
    await ctx.close();
  });

  await parcours('P7', async () => {
    // E1 : DEADLINE DÉPASSÉE (simulée dans la base de test) -> l'offre disparaît de la vitrine ET la caisse refuse (409)
    fixture('deadline-passee');
    try {
      const { ctx, p } = await page(browser, true);
      // V540 : on ouvre l'onglet « Offres », là où les cartes vivent désormais —
      // c'est le seul endroit où leur absence veut dire quelque chose.
      await p.waitForSelector('[data-testid="accueil-colonnes"]', { timeout: 60000 });
      await ouvrirOnglet(p, 'offers');
      await p.waitForTimeout(1500);
      const offres = await (await p.request.get(BASE + '/api/offers')).json();
      v('P7. deadline passée : Fondateurs n\'est plus servie par GET /api/offers', !offres.some(o => o.id === FID));
      v('P7. deadline passée : la carte « lancement » n\'est plus affichée', (await p.locator('[data-testid="aimant-lancement"]').count()) === 0);
      const r = await checkoutDirect(p, 'pw-p7-' + uid + '@example.com');
      const corps = await r.text();
      v('P7. deadline passée : la caisse répond 409 « offre terminée » (aucune session Stripe)', r.status() === 409 && /terminée|date limite/i.test(corps), r.status() + ' ' + corps.slice(0, 160));
      await ctx.close();
    } finally { fixture('deadline-restaurer'); }
  });

  await parcours('P8', async () => {
    // E1 : 50/50 (50 abonnements Fondateurs confirmés, simulés) -> « complet » : plus en vitrine, caisse 409
    fixture('stock-plein');
    try {
      const { ctx, p } = await page(browser, false);
      await p.waitForTimeout(1500);
      const offres = await (await p.request.get(BASE + '/api/offers')).json();
      const f = offres.find(o => o.id === FID);
      v('P8. 50/50 : Fondateurs sort de la vitrine (places_restantes = 0 -> retirée)', !f, f ? 'places_restantes=' + f.places_restantes : 'absente');
      v('P8. 50/50 : la carte « lancement » n\'est plus affichée', (await p.locator('[data-testid="aimant-lancement"]').count()) === 0);
      const r = await checkoutDirect(p, 'pw-p8-' + uid + '@example.com');
      const corps = await r.text();
      v('P8. 50/50 : la caisse répond 409 « offre complète » (aucune session Stripe)', r.status() === 409 && /complète|places/i.test(corps), r.status() + ' ' + corps.slice(0, 160));
      await ctx.close();
    } finally { fixture('stock-restaurer'); }
  });

  await parcours('P9', async () => {
    // E1 : anti-double ANONYME — un abonné actif (fixture) redonne son e-mail dans l'étape -> 409, 0 checkout.
    // E1.1 (V529) : le refus est une MODALE (plus d'alert()), avec « Accéder à mon espace » / « Fermer ».
    const emailP9 = 'pw-p9-' + uid + '@example.com';
    fixture('abonne-actif ' + emailP9);
    try {
      for (const mobile of [true, false]) {
        const tag = mobile ? 'P9m' : 'P9d';
        const { ctx, p } = await page(browser, mobile);
        const cta = await ouvrirFondateurs(p, tag);
        const avant = await nbSessions(p);
        const nDialogsAvant = dialogs.length;
        const recovers = []; p.on('request', r => { if (/\/api\/subscriber\/recover$/.test(r.url()) && r.method() === 'POST') recovers.push(r.url()); });
        const checkouts = []; p.on('response', r => { if (/create-checkout-session|checkout\/create-session/.test(r.url())) checkouts.push(r.status()); });
        await cta.click({}, emailP9.toUpperCase());
        const modale = p.locator('[data-testid="v529-refus"]');
        const ouverte = await modale.waitFor({ timeout: 15000 }).then(() => true).catch(() => false);
        v(`${tag}. abonné actif (e-mail en MAJUSCULES) -> modale propre « Tu as déjà cette formule » (V529)`, ouverte && /Tu as déjà cette formule/.test(await p.textContent('[data-testid="v529-refus"]') || ''), String(ouverte));
        v(`${tag}. texte « Aucun nouveau paiement n'a été créé. »`, /Aucun nouveau paiement n.a été créé/.test(await p.textContent('[data-testid="v529-refus-texte"]').catch(() => '') || ''));
        v(`${tag}. aucune boîte de dialogue NATIVE (alert/confirm)`, dialogs.length === nDialogsAvant, dialogs.slice(nDialogsAvant).join(' | '));
        v(`${tag}. 0 checkout Stripe créé (409 serveur, aucune session)`, (await nbSessions(p)) === avant && !/faux-stripe/.test(p.url()) && checkouts.every(c => c === 409), `sessions ${avant} -> ${await nbSessions(p)} | statuts ${checkouts.join(',')}`);
        const bEspace = p.locator('[data-testid="v529-refus-espace"]');
        const bFermer = p.locator('[data-testid="v529-refus-fermer"]');
        v(`${tag}. boutons « Accéder à mon espace » + « Fermer » présents`, (await bEspace.count()) === 1 && (await bFermer.count()) === 1);
        await p.screenshot({ path: `${CAP}/${tag}-409-modale.png` });
        // B : appareil NEUF (aucune session d'espace) -> le bouton mène au parcours d'accès existant :
        // POST /subscriber/recover (« Retrouver mes accès »), lien /espace/<CODE> envoyé par e-mail (faux Resend).
        await bEspace.click();
        for (let i = 0; i < 30 && !(await p.locator('[data-testid="v529-refus-envoi"]').count()); i++) { await p.waitForTimeout(300); }
        const statut = (await p.locator('[data-testid="v529-refus-envoi"]').textContent().catch(() => '')) || '';
        v(`${tag}. sans session : « Accéder à mon espace » appelle le parcours d'accès existant (POST /subscriber/recover, 1×)`, recovers.length === 1, `appels = ${recovers.length}`);
        v(`${tag}. la modale confirme l'envoi du lien d'accès à l'adresse masquée`, /vient d.être envoyé à pw•+@example\.com|envoyé à/.test(statut), statut.slice(0, 160));
        const mails = fs.existsSync(__dirname + '/pw_emails.jsonl') ? fs.readFileSync(__dirname + '/pw_emails.jsonl', 'utf8') : (fs.existsSync(process.env.PW_SCRATCH + '/pw_emails.jsonl') ? fs.readFileSync(process.env.PW_SCRATCH + '/pw_emails.jsonl', 'utf8') : '');
        const mailsP9 = mails.split('\n').filter(l => l.includes(emailP9) && /code d.acc/i.test(l));
        v(`${tag}. le faux Resend a bien reçu l'e-mail « Votre code d'accès » pour cet abonné (code AFR-… dedans)`, mailsP9.length >= 1 && /AFR-[A-Z0-9]{4,}/.test(mailsP9.join('')), mails ? `${mailsP9.length} e-mail(s)` : 'pw_emails.jsonl introuvable');
        v(`${tag}. aucune boîte native non plus après le clic`, dialogs.length === nDialogsAvant);
        await bFermer.click();
        v(`${tag}. « Fermer » referme la modale`, (await p.locator('[data-testid="v529-refus"]').count()) === 0);
        await p.screenshot({ path: `${CAP}/${tag}-409-apres.png` });
        await ctx.close();
      }
    } finally { fixture('nettoyer-abonnes'); }
  });

  v('Global. AUCUNE boîte de dialogue native pendant les parcours (V529 : le 409 est une modale)', dialogs.length === 0, dialogs.join(' | '));
  await browser.close();
  console.log(R.join('\n'));
  console.log(`\n${OK}/${OK + KO} au vert (Playwright parcours 0, 1, 4, 5, 6, 6b, 7, 8, 9)`);
  process.exit(KO ? 1 : 0);
})().catch(e => { console.error('ERREUR', e); process.exit(2); });
