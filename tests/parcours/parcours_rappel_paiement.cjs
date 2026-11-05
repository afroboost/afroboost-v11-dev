/**
 * V648 — PARCOURS « RAPPEL DE PAIEMENT », sur la pile LOCALE (pile_locale.py) : vraie application,
 * base de test, données fictives @example.test, faux Resend. Aucun e-mail réel.
 *
 * LANCEMENT (depuis la racine, le serveur tournant déjà dans reseau_local.sb) :
 *   CAPTURES=<hors dépôt> EMAILS=<hors dépôt>/pw_emails.jsonl NODE_PATH=$HOME/.claude/skills/gstack/node_modules \
 *     sandbox-exec -f tests/parcours/reseau_local.sb node tests/parcours/parcours_rappel_paiement.cjs
 */
const { chromium } = require('playwright');
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const BASE = 'http://127.0.0.1:8001';
const CAPTURES = process.env.CAPTURES;
const EMAILS = process.env.EMAILS;
const SUPER_ADMIN = 'contact.artboost@gmail.com';
const FIX = path.join(__dirname, 'fixtures_rappel_paiement.py');

const resultats = [];
function v(nom, ok, detail = '') {
  resultats.push({ nom, ok });
  console.log(`${ok ? 'OK ' : 'KO '} ${nom}${detail !== '' ? ' — ' + detail : ''}`);
}
const fixture = (...a) => execFileSync('python3', [FIX, ...a], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
const compter = () => JSON.parse(fixture('compter'));
const lignesEmails = () => (fs.existsSync(EMAILS) ? fs.readFileSync(EMAILS, 'utf8').trim().split('\n').filter(Boolean).map((l) => JSON.parse(l)) : []);
const rappelsEmails = () => lignesEmails().filter((m) => /paiement Afroboost/.test(m.subject || ''));
const jeton = execFileSync('python3', ['-c', 'import jwt,sys,time;print(jwt.encode({"email":sys.argv[1],"type":"coach","iat":int(time.time()),"exp":int(time.time())+1800},"pw-local-secret",algorithm="HS256"))', SUPER_ADMIN], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
const id = (x) => `[data-testid="${x}"]`;

async function capture(p, nom) {
  if (CAPTURES) await p.screenshot({ path: path.join(CAPTURES, nom + '.jpg'), type: 'jpeg', quality: 80 });
}
/** La fenêtre s'ouvre en fondu : on ne mesure et on ne photographie qu'une fois l'animation finie. */
async function fenetreStable(p, sel) {
  await p.waitForFunction((s) => {
    const el = document.querySelector(s);
    return el && el.getAnimations().every((a) => a.playState !== 'running') && getComputedStyle(el).opacity === '1';
  }, sel, { timeout: 5000 });
}
/** Une fenêtre fermée a quitté le DOM : plus de fondu sur la capture suivante. */
const fenetreFermee = (p, sel) => p.waitForSelector(sel, { state: 'detached', timeout: 5000 });

async function ouvrir(browser, viewport) {
  const ctx = await browser.newContext({ viewport, serviceWorkers: 'block' });
  await ctx.route('**/*', (route) => {
    const u = new URL(route.request().url());
    if (['data:', 'blob:'].includes(u.protocol) || u.hostname === '127.0.0.1') return route.continue();
    return route.abort();
  });
  await ctx.addInitScript(({ email, j }) => {
    localStorage.setItem('afroboost_jwt', j);
    localStorage.setItem('afroboost_coach_mode', 'true');
    localStorage.setItem('afroboost_coach_user', JSON.stringify({ email, name: 'Banc', role: 'super_admin' }));
    localStorage.setItem('afroboost_coach_tab', 'codes');
  }, { email: SUPER_ADMIN, j: jeton });
  const p = await ctx.newPage();
  p.appels = { echeances: 0 };
  p.on('request', (r) => { if (r.url().includes('/discount-codes/echeances')) p.appels.echeances += 1; });
  await p.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  await p.waitForSelector(id('v617-echeances'), { timeout: 60000 });
  await p.locator(id('v617-echeances')).scrollIntoViewIfNeeded();
  return { ctx, p };
}

(async () => {
  fixture('poser');
  const browser = await chromium.launch({ headless: true });
  try {
    const emailsAvant = rappelsEmails().length;

    // ── A. Drapeau éteint (l'état de livraison) ──
    let { ctx, p } = await ouvrir(browser, { width: 1440, height: 900 });
    v('l\'encadré affiche les 5 abonnements fictifs', (await p.locator(`${id('v617-echeances')} li`).count()) === 5);
    v('cas normal : bouton « Envoyer le rappel »', await p.locator(id('v648-rappel-V648-NORMAL')).isVisible());
    v('case non cochée : bouton présent', await p.locator(id('v648-rappel-V648-CASE')).isVisible());
    v('retard : bouton présent', await p.locator(id('v648-rappel-V648-RETARD')).isVisible());
    v('saison_2x : aucun bouton, motif affiché', (await p.locator(id('v648-rappel-V648-STRIPE')).count()) === 0
      && /Stripe/.test(await p.locator(id('v648-bloque-V648-STRIPE')).textContent()));
    v('sans e-mail : aucun bouton, motif affiché', (await p.locator(id('v648-rappel-V648-SANSMAIL')).count()) === 0
      && /e-mail/.test(await p.locator(id('v648-bloque-V648-SANSMAIL')).textContent()));
    const c = await p.locator(id('v648-rappel-V648-NORMAL')).evaluate((el) => ({ bouton: getComputedStyle(el).color, primaire: (() => {
      const s = document.createElement('span'); s.style.color = 'var(--primary-color, #D91CD2)'; document.body.appendChild(s);
      const r = getComputedStyle(s).color; s.remove(); return r; })() }));
    v('le bouton suit la couleur du coach', c.bouton === c.primaire, JSON.stringify(c));
    await capture(p, '01-encadre-bureau');

    await p.click(id('v648-rappel-V648-NORMAL'));
    await p.waitForSelector(id('v648-texte'));
    await fenetreStable(p, id('v648-dialogue'));
    const cadre = await p.locator(id('v648-dialogue')).evaluate((el) => ({ fond: getComputedStyle(el).backgroundColor, style: getComputedStyle(el).outlineStyle, contour: getComputedStyle(el).outlineColor }));
    v('fenêtre opaque', !/rgba\(.*, 0\)|transparent/.test(cadre.fond), cadre.fond);
    v('aucun contour de focus visible', cadre.style === 'none' || /rgba\(.*, 0\)|transparent/.test(cadre.contour), JSON.stringify(cadre));
    v('aperçu : destinataire', (await p.locator(id('v648-destinataire')).textContent()) === 'marie.fictive@example.test');
    v('aperçu : montant', (await p.locator(id('v648-montant')).textContent()) === '200.00 CHF');
    const texte = await p.locator(id('v648-texte')).textContent();
    v('aperçu : texte validé et signature', texte.startsWith('Bonjour Marie,') && texte.includes('Petit rappel amical : il reste 200 CHF') && texte.trim().endsWith("Coach Bassi, d'Afroboost"), texte);
    v('aperçu : envoi réel annoncé comme coupé', await p.locator(id('v648-envoi-coupe')).isVisible());
    v('aperçu : bouton inactif sans confirmation', await p.locator(id('v648-envoyer')).isDisabled());
    await capture(p, '02-apercu-bureau');
    await p.check(id('v648-confirmation'));
    await p.click(id('v648-envoyer'));
    await p.waitForSelector(id('v648-resultat'));
    v('drapeau éteint : réponse « Simulation »', /Simulation/.test(await p.locator(id('v648-resultat')).textContent()));
    await capture(p, '03-simulation-bureau');
    const n1 = compter();
    v('drapeau éteint : AUCUN e-mail', rappelsEmails().length === emailsAvant);
    v('drapeau éteint : AUCUNE écriture', n1.rappels === 0 && n1.journal === 0, JSON.stringify(n1));
    await p.keyboard.press('Escape');
    await fenetreFermee(p, id('v648-dialogue'));

    await p.click(id('v648-rappel-V648-CASE'));
    await p.waitForSelector(id('v648-avertissement'));
    await fenetreStable(p, id('v648-dialogue'));
    v('case non cochée : avertissement visible', /plusieurs fois/.test(await p.locator(id('v648-avertissement')).textContent()));
    await capture(p, '04-avertissement-bureau');
    await p.keyboard.press('Escape');
    await fenetreFermee(p, id('v648-dialogue'));

    // ── B. Réglage Manuel / Automatique ──
    await p.click(`${id('v617-echeances')} ${id('v648-ouvrir-reglages')}`);
    await p.waitForSelector(id('v648-mode-MANUEL'));
    await fenetreStable(p, id('v648-reglages'));
    v('réglage : MANUEL par défaut', await p.locator(id('v648-mode-MANUEL')).isChecked());
    v('réglage : pas de délais en Manuel', (await p.locator(id('v648-delai-J0')).count()) === 0);
    await capture(p, '05-reglage-manuel');
    await p.click(id('v648-mode-AUTOMATIQUE'));
    await p.waitForSelector(id('v648-auto-coupe'));
    await p.click(id('v648-voir-simulation'));
    await p.waitForSelector(id('v648-simulation'));
    v('simulation : la ligne normale affiche ses dates', /J0 :/.test(await p.locator(id('v648-sim-V648-NORMAL')).textContent()));
    v('simulation : saison_2x exclu', /Exclu/.test(await p.locator(id('v648-sim-V648-STRIPE')).textContent()));
    v('simulation : case non cochée exclue', /Exclu/.test(await p.locator(id('v648-sim-V648-CASE')).textContent()));
    await capture(p, '06-reglage-automatique-simulation');
    await p.waitForTimeout(1500);
    const n2 = compter();
    v('mode automatique choisi : AUCUN e-mail, aucun rappel écrit', rappelsEmails().length === emailsAvant && n2.rappels === 0, JSON.stringify(n2));
    await p.click(id('v648-mode-MANUEL'));
    await p.waitForSelector(id('v648-enregistre'));
    await p.keyboard.press('Escape');
    await ctx.close();

    // ── C. Fournisseur simulé : drapeau allumé EN BASE DE TEST ──
    fixture('envoi', 'on');
    ({ ctx, p } = await ouvrir(browser, { width: 1440, height: 900 }));
    await p.click(id('v648-rappel-V648-NORMAL'));
    await p.waitForSelector(id('v648-confirmation'));
    v('drapeau allumé : plus de bandeau « coupé »', (await p.locator(id('v648-envoi-coupe')).count()) === 0);
    await p.check(id('v648-confirmation'));
    await p.dblclick(id('v648-envoyer')).catch(() => {});
    await p.waitForSelector(id('v648-resultat'));
    await capture(p, '07-envoye-faux-fournisseur');
    const envoyes = rappelsEmails().slice(emailsAvant);
    v('double clic : UN seul e-mail, au faux fournisseur', envoyes.length === 1, envoyes.length);
    v('destinataire fictif', JSON.stringify(envoyes[0]?.to) === JSON.stringify(['marie.fictive@example.test']));
    v('clé d\'idempotence transmise', /^rappel-paiement-/.test(envoyes[0]?.options?.idempotency_key || ''));
    v('l\'e-mail ne contient aucun lien', !/https?:/.test(envoyes[0]?.html || '') && !/https?:/.test(envoyes[0]?.text || ''));
    const n3 = compter();
    v('historique : un rappel envoyé', n3.rappels === 1 && n3.statuts[0] === 'envoye', JSON.stringify(n3));
    v('journal Resend central : une ligne', n3.journal === 1, n3.journal);
    await p.keyboard.press('Escape');
    await fenetreFermee(p, id('v648-dialogue'));
    await p.waitForSelector(id('v648-envoye-V648-NORMAL'));
    v('la ligne affiche « Rappel envoyé le »', /Rappel envoyé le/.test(await p.locator(id('v648-envoye-V648-NORMAL')).textContent()));
    v('le bouton a disparu de la ligne', (await p.locator(id('v648-rappel-V648-NORMAL')).count()) === 0);
    await capture(p, '08-encadre-apres-envoi');
    const avantPause = p.appels.echeances;
    await p.waitForTimeout(3000);
    v('aucune boucle d\'appels (3 s sans nouvel appel à la liste)', p.appels.echeances === avantPause, `${avantPause} → ${p.appels.echeances}`);
    await ctx.close();
    fixture('envoi', 'off');

    // ── D. Téléphone ──
    ({ ctx, p } = await ouvrir(browser, { width: 390, height: 844 }));
    const debord = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    v('téléphone : aucun débordement horizontal', debord <= 0, debord);
    await capture(p, '09-encadre-telephone');
    await p.click(id('v648-rappel-V648-RETARD'));
    await p.waitForSelector(id('v648-texte'));
    await fenetreStable(p, id('v648-dialogue'));
    const boite = await p.locator(id('v648-dialogue')).boundingBox();
    v('téléphone : fenêtre dans l\'écran (gouttière 16 px)', Math.round(boite.x) === 16 && Math.round(boite.x + boite.width) === 374, JSON.stringify(boite));
    v('téléphone : la fenêtre tient en hauteur', boite.y >= 0 && boite.y + boite.height <= 844, JSON.stringify(boite));
    await capture(p, '10-apercu-telephone');
    await ctx.close();
  } finally {
    await browser.close();
    fixture('nettoyer');
  }
  const ko = resultats.filter((r) => !r.ok);
  console.log(`\n${resultats.length - ko.length}/${resultats.length} ${ko.length ? 'ÉCHECS' : 'TOUT EST VERT'}`);
  process.exit(ko.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
