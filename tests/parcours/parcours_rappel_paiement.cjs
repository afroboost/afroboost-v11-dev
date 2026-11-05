/**
 * V648 — PARCOURS « RAPPELS DE PAIEMENT », sur la pile LOCALE (pile_locale.py) : vraie application,
 * base de test, données fictives @example.test, faux Resend. Aucun e-mail réel.
 * Chemin réel du coach : Gestion → Paiements → Rappels de paiement.
 *
 * LANCEMENT (depuis la racine, le serveur tournant déjà dans reseau_local.sb) :
 *   CAPTURES=<hors dépôt> EMAILS=<hors dépôt>/pw_emails.jsonl NODE_PATH=$HOME/.claude/skills/gstack/node_modules \
 *     node tests/parcours/parcours_rappel_paiement.cjs
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
const PARTENAIRE = 'partenaire.v648@example.test';
const jetonDe = (email) => execFileSync('python3', ['-c', 'import jwt,sys,time;print(jwt.encode({"email":sys.argv[1],"type":"coach","iat":int(time.time()),"exp":int(time.time())+1800},"pw-local-secret",algorithm="HS256"))', email], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
const JETON_PARTENAIRE = jetonDe(PARTENAIRE);
const id = (x) => `[data-testid="${x}"]`;

async function capture(p, nom, options = {}) {
  if (CAPTURES) await p.screenshot({ path: path.join(CAPTURES, nom + '.jpg'), type: 'jpeg', quality: 80, ...options });
}
/** La fenêtre s'ouvre en fondu : on ne mesure et on ne photographie qu'une fois l'animation finie. */
async function fenetreStable(p, sel) {
  await p.waitForFunction((s) => {
    const el = document.querySelector(s);
    return el && el.getAnimations().every((a) => a.playState !== 'running') && getComputedStyle(el).opacity === '1';
  }, sel, { timeout: 5000 });
}
const fenetreFermee = (p, sel) => p.waitForSelector(sel, { state: 'detached', timeout: 5000 });
async function fermer(p) {
  await p.keyboard.press('Escape');
  await fenetreFermee(p, id('v648-dialogue'));
}

async function contexte(browser, viewport, onglet, email = SUPER_ADMIN) {
  const ctx = await browser.newContext({ viewport, serviceWorkers: 'block' });
  await ctx.route('**/*', (route) => {
    const u = new URL(route.request().url());
    if (['data:', 'blob:'].includes(u.protocol) || u.hostname === '127.0.0.1') return route.continue();
    return route.abort();
  });
  await ctx.addInitScript(({ mail, j, tab, role }) => {
    localStorage.setItem('afroboost_jwt', j);
    localStorage.setItem('afroboost_coach_mode', 'true');
    localStorage.setItem('afroboost_coach_user', JSON.stringify({ email: mail, name: 'Banc', role }));
    localStorage.setItem('afroboost_coach_tab', tab);
  }, { mail: email, j: email === PARTENAIRE ? JETON_PARTENAIRE : jetonDe(email), tab: onglet, role: email === SUPER_ADMIN ? 'super_admin' : 'coach' });
  const p = await ctx.newPage();
  p.appels = { liste: 0, erreurs: [] };
  p.on('request', (r) => { if (r.url().endsWith('/rappels-paiement/liste')) p.appels.liste += 1; });
  p.on('pageerror', (e) => p.appels.erreurs.push(String(e).slice(0, 160)));
  await p.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  return { ctx, p };
}

/** Le vrai chemin : la carte « Paiements » de Gestion, puis la section repliable. */
async function ouvrirPagePaiements(browser, viewport, email = SUPER_ADMIN) {
  const { ctx, p } = await contexte(browser, viewport, 'offers', email);
  const carte = p.getByRole('button', { name: /^Paiements/ }).first();
  await carte.waitFor({ timeout: 60000 });
  await carte.click();
  await p.waitForSelector(id('v199-accordion-rappels'));
  return { ctx, p };
}
async function ouvrirSection(p) {
  await p.click(`${id('v199-accordion-rappels')} [role="button"]`);
  await p.waitForSelector(id('v648-liste'), { timeout: 20000 });
  await p.locator(id('v199-accordion-rappels')).scrollIntoViewIfNeeded();
}

(async () => {
  fixture('poser');
  const browser = await chromium.launch({ headless: true });
  try {
    const emailsAvant = rappelsEmails().length;

    // ── A. La page Paiements, drapeau éteint (l'état de livraison) ──
    let { ctx, p } = await ouvrirPagePaiements(browser, { width: 1440, height: 900 });
    for (const s of ['payments', 'conditions', 'logos', 'invoices', 'landing', 'rappels']) {
      v(`page Paiements : section ${s} présente`, await p.locator(id(`v199-accordion-${s}`)).isVisible());
    }
    const ouverte = await p.locator(`${id('v199-accordion-payments')} [role="button"]`).getAttribute('aria-expanded');
    v('Configuration des Paiements reste ouverte par défaut', ouverte === 'true', ouverte);
    const config = await p.locator(id('v199-accordion-payments')).textContent();
    v('Stripe et TWINT sont toujours dans la configuration', /Stripe/i.test(config) && /TWINT/i.test(config));
    v('Rappels de paiement est fermée par défaut', (await p.locator(id('v648-section')).count()) === 0);
    v('ordre : juste après la configuration', await p.evaluate(() => {
      const a = [...document.querySelectorAll('[data-testid^="v199-accordion-"]')].map((e) => e.getAttribute('data-testid'));
      return a[0] === 'v199-accordion-payments' && a[1] === 'v199-accordion-rappels';
    }));

    await ouvrirSection(p);
    v('la section garde la configuration ouverte', (await p.locator(`${id('v199-accordion-payments')} [role="button"]`).getAttribute('aria-expanded')) === 'true');
    v('la section annonce que l\'envoi réel est coupé', await p.locator(id('v648-section-coupe')).isVisible());
    v('Manuel coché par défaut', await p.locator(id('v648-mode-MANUEL')).isChecked());
    v('délai de relance : 7 jours par défaut', (await p.locator(id('v648-delai-relance')).inputValue()) === '7');
    v('la liste affiche les 5 abonnements fictifs', (await p.locator(`${id('v648-liste')} > li`).count()) === 5);
    const lNormale = await p.locator(id('v648-ligne-V648-NORMAL')).textContent();
    v('montant et échéance sur la ligne', /200\.00 CHF/.test(lNormale) && /Échéance/.test(lNormale), lNormale.slice(0, 90));
    v('boutons Prévisualiser et Envoyer le rappel', (await p.locator(id('v648-voir-V648-NORMAL')).textContent()) === 'Prévisualiser' && (await p.locator(id('v648-rappel-V648-NORMAL')).textContent()) === 'Envoyer le rappel');
    v('saison_2x : aucun bouton, motif affiché', (await p.locator(id('v648-rappel-V648-STRIPE')).count()) === 0 && /Stripe/.test(await p.locator(id('v648-bloque-V648-STRIPE')).textContent()));
    v('sans e-mail : aucun bouton, motif affiché', (await p.locator(id('v648-rappel-V648-SANSMAIL')).count()) === 0 && /e-mail/.test(await p.locator(id('v648-bloque-V648-SANSMAIL')).textContent()));
    const c = await p.locator(id('v648-rappel-V648-NORMAL')).evaluate((el) => ({ bouton: getComputedStyle(el).color, primaire: (() => {
      const s = document.createElement('span'); s.style.color = 'var(--primary-color, #D91CD2)'; document.body.appendChild(s);
      const r = getComputedStyle(s).color; s.remove(); return r; })() }));
    v('le bouton suit la couleur du coach', c.bouton === c.primaire, JSON.stringify(c));
    await capture(p, '01-page-paiements-section', { fullPage: true });

    await p.click(id('v648-voir-V648-NORMAL'));
    await p.waitForSelector(id('v648-texte'));
    await fenetreStable(p, id('v648-dialogue'));
    const cadre = await p.locator(id('v648-dialogue')).evaluate((el) => ({ fond: getComputedStyle(el).backgroundColor, style: getComputedStyle(el).outlineStyle, contour: getComputedStyle(el).outlineColor }));
    v('fenêtre opaque, sans contour visible', !/rgba\(.*, 0\)|transparent/.test(cadre.fond) && (cadre.style === 'none' || /rgba\(.*, 0\)|transparent/.test(cadre.contour)), JSON.stringify(cadre));
    v('Prévisualiser : aucun bouton d\'envoi', (await p.locator(id('v648-envoyer')).count()) === 0);
    const texte = await p.locator(id('v648-texte')).textContent();
    v('aperçu : texte validé et signature de Bassi', texte.startsWith('Bonjour Marie,') && texte.includes('Petit rappel amical : il reste 200 CHF') && texte.trim().endsWith("Coach Bassi, d'Afroboost"));
    await capture(p, '02-previsualiser');
    await p.click(id('v648-continuer'));
    await p.waitForSelector(id('v648-envoyer'));
    v('envoi : bouton inactif sans confirmation', await p.locator(id('v648-envoyer')).isDisabled());
    await p.check(id('v648-confirmation'));
    await p.click(id('v648-envoyer'));
    await p.waitForSelector(id('v648-resultat'));
    v('drapeau éteint : réponse « Simulation »', /Simulation/.test(await p.locator(id('v648-resultat')).textContent()));
    const n1 = compter();
    v('drapeau éteint : AUCUN e-mail, AUCUNE écriture', rappelsEmails().length === emailsAvant && n1.rappels === 0 && n1.journal === 0, JSON.stringify(n1));
    await fermer(p);

    // ── B. Case « en plusieurs fois » non cochée ──
    v('case non cochée : la ligne annonce la vérification', await p.locator(id('v648-a-verifier-V648-CASE')).isVisible());
    await p.click(id('v648-rappel-V648-CASE'));
    await p.waitForSelector(id('v648-avertissement'));
    await fenetreStable(p, id('v648-dialogue'));
    v('avertissement clair', /pas une preuve de non-paiement/.test(await p.locator(id('v648-avertissement')).textContent()));
    await p.check(id('v648-confirmation'));
    v('case cochée sans montant : envoi toujours bloqué', await p.locator(id('v648-envoyer')).isDisabled());
    await p.fill(id('v648-montant-confirme'), '150');
    await p.check(id('v648-confirmation'));
    await capture(p, '03-suivi-a-verifier');
    await p.click(id('v648-envoyer'));
    await p.waitForSelector(id('v648-erreur'));
    v('montant différent : refus expliqué', /ne correspond pas/.test(await p.locator(id('v648-erreur')).textContent()));
    v('montant différent : aucun e-mail', rappelsEmails().length === emailsAvant);
    await fermer(p);

    // ── C. Manuel / Automatique ──
    await p.click(id('v648-mode-AUTOMATIQUE'));
    await p.waitForSelector(id('v648-auto-coupe'));
    await p.click(id('v648-voir-simulation'));
    await p.waitForSelector(id('v648-simulation'));
    v('simulation : la ligne normale affiche ses dates', /J0 :/.test(await p.locator(id('v648-sim-V648-NORMAL')).textContent()));
    v('simulation : saison_2x exclu', /Exclu/.test(await p.locator(id('v648-sim-V648-STRIPE')).textContent()));
    v('simulation : case non cochée exclue', /Exclu/.test(await p.locator(id('v648-sim-V648-CASE')).textContent()));
    await p.locator(id('v648-simulation')).scrollIntoViewIfNeeded();
    await capture(p, '04-automatique-simulation');
    await p.waitForTimeout(1500);
    const n2 = compter();
    v('mode automatique choisi : AUCUN e-mail, aucun rappel écrit', rappelsEmails().length === emailsAvant && n2.rappels === 0, JSON.stringify(n2));
    await p.click(id('v648-mode-MANUEL'));
    await p.waitForSelector(id('v648-enregistre'));
    await ctx.close();

    // ── D. Fournisseur simulé : drapeau allumé EN BASE DE TEST ──
    fixture('envoi', 'on');
    ({ ctx, p } = await ouvrirPagePaiements(browser, { width: 1440, height: 900 }));
    await ouvrirSection(p);
    v('drapeau allumé : plus de bandeau « coupé »', (await p.locator(id('v648-section-coupe')).count()) === 0);
    await p.click(id('v648-rappel-V648-NORMAL'));
    await p.waitForSelector(id('v648-confirmation'));
    await p.check(id('v648-confirmation'));
    await p.dblclick(id('v648-envoyer')).catch(() => {});
    await p.waitForSelector(id('v648-resultat'));
    let envoyes = rappelsEmails().slice(emailsAvant);
    v('double clic : UN seul e-mail, au faux fournisseur', envoyes.length === 1, envoyes.length);
    v('destinataire fictif', JSON.stringify(envoyes[0]?.to) === JSON.stringify(['marie.fictive@example.test']));
    v('clé d\'idempotence transmise', /^rappel-paiement-/.test(envoyes[0]?.options?.idempotency_key || ''));
    v('l\'e-mail ne contient aucun lien', !/https?:/.test(envoyes[0]?.html || '') && !/https?:/.test(envoyes[0]?.text || ''));
    let n3 = compter();
    v('historique : un rappel envoyé', n3.rappels === 1 && n3.statuts[0] === 'envoye', JSON.stringify(n3));
    v('journal Resend central : une ligne', n3.journal === 1, n3.journal);
    await fermer(p);
    await p.waitForSelector(id('v648-attente-V648-NORMAL'));
    v('avant 7 jours : plus de bouton, date de relance affichée', (await p.locator(id('v648-rappel-V648-NORMAL')).count()) === 0 && /Prochain envoi possible le/.test(await p.locator(id('v648-attente-V648-NORMAL')).textContent()));
    await p.click(id('v648-voir-V648-NORMAL'));
    await p.waitForSelector(id('v648-envoi-bloque'));
    await fenetreStable(p, id('v648-dialogue'));
    v('l\'aperçu reste possible, et dit pourquoi l\'envoi est bloqué', /Relance possible le/.test(await p.locator(id('v648-envoi-bloque')).textContent()) && (await p.locator(id('v648-envoyer')).count()) === 0);
    await fermer(p);

    await p.click(id('v648-rappel-V648-CASE'));
    await p.waitForSelector(id('v648-montant-confirme'));
    await p.fill(id('v648-montant-confirme'), '200');
    await p.check(id('v648-confirmation'));
    await p.click(id('v648-envoyer'));
    await p.waitForSelector(id('v648-resultat'));
    envoyes = rappelsEmails().slice(emailsAvant);
    v('montant vérifié : le rappel part', envoyes.length === 2 && envoyes[1].to[0] === 'lea.fictive@example.test', envoyes.length);
    await fermer(p);

    fixture('vieillir', 'v648-v648-normal');     // 8 jours passent sur le rappel de Marie
    await ctx.close();
    ({ ctx, p } = await ouvrirPagePaiements(browser, { width: 1440, height: 900 }));
    await ouvrirSection(p);
    const relance = p.locator(id('v648-rappel-V648-NORMAL'));
    v('après 7 jours : « Envoyer la relance »', (await relance.textContent()) === 'Envoyer la relance');
    await relance.click();
    await p.waitForSelector(id('v648-confirmation'));
    v('la relance exige une nouvelle confirmation', await p.locator(id('v648-envoyer')).isDisabled());
    await p.check(id('v648-confirmation'));
    await p.click(id('v648-envoyer'));
    await p.waitForSelector(id('v648-resultat'));
    envoyes = rappelsEmails().slice(emailsAvant);
    v('relance : un e-mail de plus', envoyes.length === 3, envoyes.length);
    v('relance : autre clé d\'idempotence', envoyes[2].options.idempotency_key !== envoyes[0].options.idempotency_key);
    await fermer(p);
    await p.locator(`${id('v648-historique-general')} summary`).click();
    const hist = await p.locator(id('v648-historique-general')).textContent();
    v('historique général : étapes, résultat, destinataire et coach', /Rappel/.test(hist) && /Relance 1/.test(hist) && /Envoyé/.test(hist) && /marie\.fictive@example\.test/.test(hist) && hist.includes(`Par ${SUPER_ADMIN}`));
    await p.locator(id('v648-historique-general')).scrollIntoViewIfNeeded();
    await capture(p, '05-historique-relance', { fullPage: true });
    const avantPause = p.appels.liste;
    await p.waitForTimeout(3000);
    v('aucune boucle d\'appels (3 s sans nouvel appel à la liste)', p.appels.liste === avantPause, `${avantPause} → ${p.appels.liste}`);
    v('aucune erreur JavaScript', p.appels.erreurs.length === 0, p.appels.erreurs.join(' | '));
    await ctx.close();
    fixture('envoi', 'off');

    // ── E. Téléphone ──
    ({ ctx, p } = await ouvrirPagePaiements(browser, { width: 390, height: 844 }));
    await ouvrirSection(p);
    const debord = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    v('téléphone : aucun débordement horizontal', debord <= 0, debord);
    await capture(p, '06-section-telephone', { fullPage: true });
    await p.click(id('v648-voir-V648-RETARD'));
    await p.waitForSelector(id('v648-texte'));
    await fenetreStable(p, id('v648-dialogue'));
    const boite = await p.locator(id('v648-dialogue')).boundingBox();
    v('téléphone : fenêtre dans l\'écran (gouttière 16 px)', Math.round(boite.x) === 16 && Math.round(boite.x + boite.width) === 374, JSON.stringify(boite));
    v('téléphone : la fenêtre tient en hauteur', boite.y >= 0 && boite.y + boite.height <= 844, JSON.stringify(boite));
    await capture(p, '07-apercu-telephone');
    await ctx.close();

    // ── F bis. Envoi à vérifier (super-admin) ──
    fixture('incertain', 'v648-v648-retard');
    ({ ctx, p } = await ouvrirPagePaiements(browser, { width: 1440, height: 900 }));
    await ouvrirSection(p);
    v('statut visible « Envoi à vérifier »', (await p.locator(id('v648-a-verifier-envoi-V648-RETARD')).textContent()) === 'Envoi à vérifier');
    v('aucun bouton d\'envoi sur cette ligne', (await p.locator(id('v648-rappel-V648-RETARD')).count()) === 0);
    await p.click(id('v648-voir-V648-RETARD'));
    await p.waitForSelector(id('v648-verification'));
    await fenetreStable(p, id('v648-dialogue'));
    v('contact manuel proposé', /hors du système/.test(await p.locator(id('v648-envoi-bloque')).textContent()));
    v('aucun bouton d\'envoi dans la fenêtre', (await p.locator(id('v648-envoyer')).count()) === 0);
    await capture(p, '08-envoi-a-verifier');
    const avantV = rappelsEmails().length;
    await p.click(id('v648-verifier'));
    await p.waitForSelector(id('v648-preuve'));
    v('sans preuve : le blocage reste', /blocage reste/.test(await p.locator(id('v648-preuve')).textContent()));
    v('vérifier n\'envoie aucun e-mail', rappelsEmails().length === avantV);
    await fermer(p);
    await ctx.close();

    // ── F ter. Partenaire : signature structurée, réglée sur la même page ──
    fixture('partenaire', JETON_PARTENAIRE);
    ({ ctx, p } = await ouvrirPagePaiements(browser, { width: 1440, height: 900 }, PARTENAIRE));
    await ouvrirSection(p);
    v('partenaire : ses seuls clients', (await p.locator(`${id('v648-liste')} > li`).count()) === 1 && await p.locator(id('v648-ligne-V648-PART')).isVisible());
    v('partenaire sans signature : aucun envoi, motif clair', (await p.locator(id('v648-rappel-V648-PART')).count()) === 0 && /signature/i.test(await p.locator(id('v648-bloque-V648-PART')).textContent()));
    for (const [mauvais, attendu] of [['evil.com', /lien/i], ['Coach Bassi', /réservé/i], ['Paie ici', /paiement/i]]) {
      await p.fill(id('v648-signature-nom'), mauvais);
      await p.click(id('v648-signature-enregistrer'));
      await p.waitForSelector(id('v648-signature-refus'));
      v(`signature « ${mauvais} » : refus expliqué`, attendu.test(await p.locator(id('v648-signature-refus')).textContent()), await p.locator(id('v648-signature-refus')).textContent());
    }
    await p.locator(id('v648-signature')).scrollIntoViewIfNeeded();
    await capture(p, '09-signature-refusee');
    await p.fill(id('v648-signature-nom'), 'Bassirou Diop');
    await p.fill(id('v648-signature-activite'), 'Fit24');
    await p.click(id('v648-signature-enregistrer'));
    await p.waitForSelector(id('v648-signature-apercu'));
    v('nom légitime accepté, signature montrée', /Bassirou Diop, Fit24/.test(await p.locator(id('v648-signature-apercu')).textContent()));
    await p.waitForSelector(id('v648-rappel-V648-PART'));
    await p.click(id('v648-voir-V648-PART'));
    await p.waitForSelector(id('v648-texte'));
    await fenetreStable(p, id('v648-dialogue'));
    const tp = await p.locator(id('v648-texte')).textContent();
    v('le message porte sa signature, jamais celle de Bassi', tp.includes('Bassirou Diop, Fit24') && tp.includes("Coach partenaire d'Afroboost") && !tp.includes('Coach Bassi'));
    v('partenaire : pas de bouton de résolution', (await p.locator(id('v648-verification')).count()) === 0);
    await capture(p, '10-apercu-partenaire');
    await ctx.close();

    // ── F. L'encadré de Codes promo reste celui de la production ──
    ({ ctx, p } = await contexte(browser, { width: 1440, height: 900 }, 'codes'));
    await p.waitForSelector(id('v617-echeances'), { timeout: 60000 });
    v('Codes promo : « Paiements à encaisser » toujours là', await p.locator(id('v617-rappel-V648-RETARD')).isVisible());
    v('Codes promo : aucun bouton de rappel ajouté', (await p.locator(`${id('v617-echeances')} [data-testid^="v648-"]`).count()) === 0);
    v('Codes promo : texte d\'origine conservé', /aucun message n'est envoyé au client/.test(await p.locator(id('v617-echeances')).textContent()));
    await ctx.close();
  } finally {
    await browser.close();
    fixture('nettoyer');
  }
  const ko = resultats.filter((r) => !r.ok);
  console.log(`\n${resultats.length - ko.length}/${resultats.length} ${ko.length ? 'ÉCHECS' : 'TOUT EST VERT'}`);
  process.exit(ko.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
