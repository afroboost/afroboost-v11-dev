// V528 — PARCOURS ABONNEMENT MENSUEL sur la pile LOCALE (vraie app, base de test, faux Stripe/Resend).
// AUCUN paiement réel, AUCUN e-mail réel, AUCUN appel Stripe live.
//   E1  offre récurrente, visiteur anonyme -> étape « Ton e-mail » (V528, plus de window.prompt) -> Stripe prérempli (J)
//   E2  paiement TEST -> espace abonné (OTP lu dans pw_emails.jsonl) -> bloc « Mon abonnement mensuel » (A..E)
//   E3  Résilier (Stripe mocké) -> cancel_at_period_end true en base -> « Résiliation programmée », accès conservé (F)
//   E4  Continuer -> cancel_at_period_end false -> « Actif » (G)
//   E5  même e-mail, même offre -> 409 « déjà cet abonnement actif », 0 checkout créé (I)
// Le tout sur DESKTOP puis MOBILE (iPhone 13), avec deux abonnés distincts (règle OTP 120 s par code).
const { chromium, devices } = require('playwright');
const fs = require('fs');
const BASE = 'http://127.0.0.1:8001';
const SCR = process.env.PW_SCRATCH || __dirname;
const CAP = SCR + '/pw_captures';
fs.mkdirSync(CAP, { recursive: true });
const EMAILS = SCR + '/pw_emails.jsonl';
const R = []; let OK = 0, KO = 0;
const v = (nom, cond, detail = '') => { (cond ? OK++ : KO++); R.push(`${cond ? 'OK  ' : 'RATE'} ${nom}${cond ? '' : '  [' + String(detail).slice(0, 300) + ']'}`); };
const uid = Date.now().toString(36);
const lireEmails = () => { try { return fs.readFileSync(EMAILS, 'utf8').trim().split('\n').filter(Boolean).map(l => JSON.parse(l)); } catch (e) { return []; } };
const attendreEmail = async (pred, ms = 30000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { const m = lireEmails().filter(pred); if (m.length) return m[m.length - 1]; await new Promise(r => setTimeout(r, 500)); } return null; };
const otpDe = (html) => { const m = (html || '').replace(/<[^>]+>/g, ' ').match(/\b(\d{6})\b/); return m ? m[1] : ''; };
const abonnement = async (p, email) => (await (await p.request.get(BASE + '/faux-stripe/abonnement?email=' + encodeURIComponent(email))).json());
const modifs = async (p) => (await (await p.request.get(BASE + '/faux-stripe/modifs')).json()).modifs;
const nbSessions = async (p) => Object.keys(await (await p.request.get(BASE + '/faux-stripe/etat')).json()).length;

async function page(browser, mobile, url) {
  const ctx = mobile ? await browser.newContext({ ...devices['iPhone 13'] }) : await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  const dialogs = []; const erreurs = [];
  p.on('dialog', async d => { dialogs.push(d.type() + ':' + d.message().slice(0, 120)); await d.accept(); });   // confirm() de résiliation = accepté ; alert 409 = lu
  p.on('pageerror', e => erreurs.push(String(e).slice(0, 200)));
  await p.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  return { ctx, p, dialogs, erreurs };
}

// V540 : les offres ne sont plus sur l'écran d'accueil, elles sont sous
// l'onglet « Offres ». On clique le vrai bouton, comme un visiteur.
// (Quand l'URL porte déjà `?offre=<id>`, la fiche s'ouvre seule : le lien
// profond garde sa propre porte, et ce chemin-là n'a pas besoin de l'onglet.)
async function ouvrirFiche(p) {
  await p.waitForSelector('[data-testid="accueil-colonnes"]', { timeout: 60000 });
  if (!(await p.locator('[data-testid="fiche-cta"]').count())) {
    await p.click('[data-testid="nav-tab-offers"]');
    await p.waitForSelector('[data-testid="offres-aimants"]', { state: 'visible', timeout: 30000 });
  }
  await p.waitForSelector('[data-testid="fiche-cta"]', { timeout: 30000 });
}

async function cliquerCta(p) {
  for (let i = 0; i < 4; i++) { try { await p.locator('[data-testid="fiche-cta"]').click({ timeout: 8000 }); return; } catch (e) { if (i === 3) throw e; } }
}

async function entrerDansEspace(p, tag, code, email) {
  await p.goto(`${BASE}/espace/${code}`, { waitUntil: 'domcontentloaded' });
  await p.waitForSelector('[data-testid="espace-email"], [data-testid="subscriber-space-header"]', { timeout: 30000 });
  if (await p.locator('[data-testid="subscriber-space-header"]').count()) { v(`${tag}. l'espace s'ouvre directement (session d'appareil)`, true); return; }
  await p.fill('[data-testid="espace-email"]', email);
  const nAvant = lireEmails().length;
  await p.click('[data-testid="espace-valider"]');
  await p.waitForSelector('[data-testid="espace-otp"]', { timeout: 45000 });
  const mail = await attendreEmail((m) => (m.to || []).includes(email) && /code|otp|vérif|verif/i.test(m.subject || ''), 30000);
  v(`${tag}. e-mail OTP émis (faux Resend)`, !!mail, JSON.stringify(lireEmails().slice(nAvant).map(m => m.subject)));
  const otp = otpDe(mail && mail.html);
  await p.fill('[data-testid="espace-otp"]', otp);
  await p.click('[data-testid="espace-valider"]');
  // V528: un nouvel abonné arrive sur l'onboarding profil (Nom/WhatsApp) avant l'espace.
  await p.waitForSelector('[data-testid="onboarding-nom"], [data-testid="subscriber-space-header"]', { timeout: 30000 });
  if (await p.locator('[data-testid="onboarding-nom"]').count()) {
    await p.fill('[data-testid="onboarding-nom"]', 'Test Abo');
    await p.fill('[data-testid="onboarding-whatsapp"]', '+41 76 555 00 ' + String(Math.floor(Math.random() * 90) + 10));
    const b = p.locator('[data-testid="onboarding-valider"]');
    await b.scrollIntoViewIfNeeded().catch(() => null);
    await b.click();
    await p.waitForSelector('[data-testid="onboarding-nom"]', { state: 'detached', timeout: 30000 }).catch(() => null);
  }
  await p.waitForSelector('[data-testid="subscriber-space-header"]', { timeout: 45000 });
}

async function scenario(browser, mobile) {
  const T = mobile ? 'MOBILE' : 'DESKTOP';
  const EMAIL = `pw-abo-${T.toLowerCase()}-${uid}@example.com`;
  const fond = (await (await (await browser.newContext()).newPage()).request.get(BASE + '/api/offers')).json();
  const offre = (await fond).find(o => /ondateur/.test(o.name || ''));
  v(`${T} E0. l'offre Fondateurs (récurrente) est servie par la pile locale`, !!offre, JSON.stringify((await fond).map(o => o.name)));
  if (!offre) return;

  // ── E1 : étape e-mail (V528) puis Stripe prérempli ────────────────────────
  const { ctx, p, dialogs, erreurs } = await page(browser, mobile, `${BASE}/?offre=${offre.id}`);
  await ouvrirFiche(p);
  const nAvantE1 = await nbSessions(p);
  await cliquerCta(p);
  const etape = p.locator('[data-testid="v528-etape-email"]');
  await etape.waitFor({ timeout: 15000 }).catch(() => null);
  v(`${T} E1. clic Acheter (anonyme, offre récurrente) -> l'étape « Ton e-mail » s'affiche, aucun checkout encore créé`,
    await etape.count() === 1 && (await nbSessions(p)) === nAvantE1, `etape=${await etape.count()} sessions=${await nbSessions(p)}`);
  await p.screenshot({ path: `${CAP}/E1-etape-email-${T}.png` });
  const boiteVisible = await p.locator('[data-testid="v528-email-input"]').isVisible().catch(() => false);
  const boite = await p.locator('[data-testid="v528-email-input"]').boundingBox().catch(() => null);
  v(`${T} E1. le champ e-mail est visible dans le viewport (mobile prioritaire)`, boiteVisible && boite && boite.y >= 0 && boite.y < (mobile ? 700 : 900), JSON.stringify(boite));
  await p.fill('[data-testid="v528-email-input"]', 'a@b.c');
  await p.click('[data-testid="v528-email-continuer"]');
  await p.waitForTimeout(400);
  v(`${T} E1. adresse invalide -> message d'erreur, toujours 0 checkout`, (await p.locator('[data-testid="v528-etape-email"] [role="alert"]').count()) >= 1 && (await nbSessions(p)) === nAvantE1);
  await p.fill('[data-testid="v528-email-input"]', EMAIL);
  const [nav] = await Promise.all([p.waitForNavigation({ url: /faux-stripe/, timeout: 30000 }).catch(() => null), p.click('[data-testid="v528-email-continuer"]')]);
  v(`${T} E1/J. « Continuer » -> checkout Stripe créé EXACTEMENT une fois (client sans abonnement)`, !!nav && (await nbSessions(p)) === nAvantE1 + 1, `${p.url()} sessions ${nAvantE1}->${await nbSessions(p)}`);
  const emailStripe = (await p.locator('[data-testid="faux-email"]').textContent().catch(() => '')) || '';
  v(`${T} E1. l'e-mail est prérempli sur la page Stripe`, emailStripe.trim().toLowerCase() === EMAIL, emailStripe);
  const montant = await p.locator('[data-testid="faux-montant"]').textContent();
  v(`${T} E1. mode subscription, 59.00 CHF / month`, /59\.00 CHF \/ month/.test(montant || '') && /subscription/.test(montant || ''), montant);

  // ── E2 : paiement TEST -> espace abonné ──────────────────────────────────
  await Promise.all([p.waitForNavigation({ timeout: 60000 }), p.click('[data-testid="faux-payer"]')]);
  await p.waitForTimeout(2500);
  let abo = await abonnement(p, EMAIL);
  for (let i = 0; i < 10 && abo.n === 0; i++) { await p.waitForTimeout(1000); abo = await abonnement(p, EMAIL); }
  const a = abo.abonnements[0] || {};
  v(`${T} E2. le webhook a créé UN abonnement mensuel actif (stripe_subscription_id fictif, cancel_at_period_end false, 8 séances, 59 CHF)`,
    abo.n === 1 && a.status === 'active' && /^sub_faux_/.test(a.stripe_subscription_id || '') && !a.cancel_at_period_end && a.remaining_sessions === 8 && Number(a.renewal_price) === 59,
    JSON.stringify(a));
  const code = a.code || a.access_code;
  v(`${T} E2. un code d'accès existe`, !!code, JSON.stringify(a));
  if (!code) { await ctx.close(); return; }
  await entrerDansEspace(p, `${T} E2`, code, EMAIL);
  const bloc = p.locator('[data-testid="subscriber-space-abonnement-mensuel"]');
  await bloc.waitFor({ timeout: 15000 }).catch(() => null);
  const texte = (await bloc.textContent().catch(() => '')) || '';
  v(`${T} A. bloc « Mon abonnement mensuel » visible`, (await bloc.count()) === 1 && await bloc.isVisible(), texte.slice(0, 200));
  v(`${T} B. prix / mois visible (59.00 CHF / mois)`, /59\.00 CHF \/ mois/.test(texte), texte.slice(0, 200));
  v(`${T} C. prochaine échéance visible (date JJ/MM/AAAA)`, /Prochaine échéance/.test(texte) && /\d{2}\/\d{2}\/\d{4}/.test(texte), texte.slice(0, 200));
  v(`${T} D. séances restantes visibles (8 restantes sur 8)`, /8 restantes sur 8/.test(texte), texte.slice(0, 200));
  v(`${T} D. offre visible (Fondateurs)`, /Fondateurs/.test(texte));
  v(`${T} D. règle « ne sont pas reportées au mois suivant » visible`, /ne sont pas reportées/.test(texte));
  v(`${T} A. état = Actif`, ((await p.locator('[data-testid="abonnement-etat"]').textContent().catch(() => '')) || '').trim() === 'Actif');
  const btnResilier = p.locator('[data-testid="abonnement-resilier"]');
  v(`${T} E. bouton « Résilier mon abonnement » visible`, (await btnResilier.count()) === 1 && /Résilier mon abonnement/.test((await btnResilier.textContent()) || ''));
  await p.screenshot({ path: `${CAP}/E2-espace-actif-${T}.png`, fullPage: true });

  // ── E3 : Résilier (Stripe mocké) ─────────────────────────────────────────
  const nModifsAvant = (await modifs(p)).length;
  await btnResilier.click();
  await p.waitForSelector('[data-testid="abonnement-continuer"]', { timeout: 15000 }).catch(() => null);
  await p.waitForTimeout(500);
  const m1 = (await modifs(p)).slice(nModifsAvant);
  v(`${T} F. clic Résilier -> confirmation acceptée -> Stripe Subscription.modify(cancel_at_period_end=true) appelé UNE fois sur le bon id`,
    m1.length === 1 && m1[0].cancel_at_period_end === true && m1[0].id === a.stripe_subscription_id, JSON.stringify(m1));
  abo = await abonnement(p, EMAIL); const a2 = abo.abonnements[0] || {};
  v(`${T} F. en base : cancel_at_period_end true, resiliation_demandee_le posé, status TOUJOURS active, expires_at et séances intacts`,
    a2.cancel_at_period_end === true && !!a2.resiliation_demandee_le && a2.status === 'active' && a2.expires_at === a.expires_at && a2.remaining_sessions === 8, JSON.stringify(a2));
  const etat2 = ((await p.locator('[data-testid="abonnement-etat"]').textContent().catch(() => '')) || '').trim();
  const texte2 = (await bloc.textContent().catch(() => '')) || '';
  v(`${T} F. l'espace affiche « Résiliation programmée » et « Fin d'accès » à la date, accès conservé (séances toujours affichées)`,
    etat2 === 'Résiliation programmée' && /Fin d'accès/.test(texte2) && /8 restantes sur 8/.test(texte2), `${etat2} | ${texte2.slice(0, 200)}`);
  v(`${T} F. la confirmation dit que l'accès et les séances sont gardés jusqu'au terme`, dialogs.some(d => /^confirm:/.test(d) && /gardes ton accès/.test(d)), dialogs.join(' | '));
  await p.screenshot({ path: `${CAP}/E3-resiliation-programmee-${T}.png`, fullPage: true });

  // ── E4 : Continuer (réactivation) ────────────────────────────────────────
  await p.locator('[data-testid="abonnement-continuer"]').click();
  await p.waitForSelector('[data-testid="abonnement-resilier"]', { timeout: 15000 }).catch(() => null);
  await p.waitForTimeout(500);
  const m2 = (await modifs(p)).slice(nModifsAvant + 1);
  v(`${T} G. clic Continuer -> Subscription.modify(cancel_at_period_end=false) UNE fois`, m2.length === 1 && m2[0].cancel_at_period_end === false && m2[0].id === a.stripe_subscription_id, JSON.stringify(m2));
  abo = await abonnement(p, EMAIL); const a3 = abo.abonnements[0] || {};
  v(`${T} G. en base : cancel_at_period_end false, résiliation retirée, toujours active`, a3.cancel_at_period_end === false && !a3.resiliation_demandee_le && a3.status === 'active', JSON.stringify(a3));
  v(`${T} G. l'espace revient à « Actif » + « Prochaine échéance »`, ((await p.locator('[data-testid="abonnement-etat"]').textContent().catch(() => '')) || '').trim() === 'Actif' && /Prochaine échéance/.test((await bloc.textContent()) || ''));
  await p.screenshot({ path: `${CAP}/E4-reactive-${T}.png`, fullPage: true });

  // ── E5 : anti-double anonyme (même e-mail, même offre) ───────────────────
  const { ctx: ctx2, p: p2, dialogs: dialogs2 } = await page(browser, mobile, `${BASE}/?offre=${offre.id}`);
  await ouvrirFiche(p2);
  const nAvantE5 = await nbSessions(p2);
  await cliquerCta(p2);
  await p2.locator('[data-testid="v528-etape-email"]').waitFor({ timeout: 15000 }).catch(() => null);
  await p2.fill('[data-testid="v528-email-input"]', EMAIL.toUpperCase());   // normalisation côté client/serveur
  await p2.click('[data-testid="v528-email-continuer"]');
  // V529 : LE REFUS N'EST PLUS UN `alert()`, C'EST UNE MODALE.
  // Ce banc a été écrit à V528, quand le 409 passait par une boîte native. V529
  // les a toutes retirées (parcours_fondateurs P9 le verrouille déjà) : lire
  // `dialogs2` ici revenait donc à attendre un mécanisme SUPPRIMÉ, et le banc
  // échouait sur un comportement correct. On mesure maintenant la modale — et
  // on exige EN PLUS qu'aucune boîte native n'apparaisse, ce que l'ancienne
  // version ne pouvait pas vérifier. Rien n'est affaibli : les deux garanties
  // qui comptent (0 session Stripe, 1 seul abonnement) sont inchangées.
  const refus = p2.locator('[data-testid="v529-refus"]');
  const refusOuvert = await refus.waitFor({ timeout: 15000 }).then(() => true).catch(() => false);
  const refusTexte = (await refus.textContent().catch(() => '')) || '';
  v(`${T} I. même e-mail (en MAJUSCULES) + même offre -> refus V529 « Tu as déjà cette formule », AUCUN checkout Stripe créé`,
    refusOuvert && /Tu as déjà cette formule/.test(refusTexte)
    && /Aucun nouveau paiement n.a été créé/.test(refusTexte)
    && (await nbSessions(p2)) === nAvantE5 && !/faux-stripe/.test(p2.url()),
    `${refusTexte.replace(/\s+/g, ' ').slice(0, 160)} | sessions ${nAvantE5}->${await nbSessions(p2)} | ${p2.url()}`);
  v(`${T} I. aucune boîte de dialogue NATIVE (alert/confirm) — c'est la règle V529`,
    dialogs2.length === 0, dialogs2.join(' | '));
  abo = await abonnement(p2, EMAIL);
  v(`${T} I. toujours UN seul abonnement en base pour cette adresse`, abo.n === 1, JSON.stringify(abo.abonnements.map(x => x.id)));
  v(`${T} I. l'app propose l'espace abonné (bouton « Accéder à mon espace »)`,
    (await p2.locator('[data-testid="v529-refus-espace"]').count()) === 1
    || /\/espace/.test(p2.url()), p2.url());
  await p2.screenshot({ path: `${CAP}/E5-409-${T}.png` });
  v(`${T} Global. aucune erreur JS`, erreurs.length === 0, erreurs.join(' | '));
  await ctx2.close(); await ctx.close();
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  try { await scenario(browser, false); } catch (e) { v('DESKTOP. ERREUR d\'exécution', false, String(e).split('\n')[0]); }
  try { await scenario(browser, true); } catch (e) { v('MOBILE. ERREUR d\'exécution', false, String(e).split('\n')[0]); }
  await browser.close();
  console.log(R.join('\n'));
  console.log(`\n${OK}/${OK + KO} verts — captures dans ${CAP}`);
  process.exit(KO ? 1 : 0);
})();
