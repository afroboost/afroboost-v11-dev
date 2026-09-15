// PARCOURS 2 (essai gratuit) + PARCOURS 3 (espace abonné, réservation, reconnexion) — pile LOCALE.
// Faux Resend : l'OTP est LU dans pw_emails.jsonl (jamais envoyé). Aucune donnée de production.
const { chromium, devices } = require('playwright');
const fs = require('fs');
const BASE = 'http://127.0.0.1:8001';
const CAP = __dirname + '/pw_captures'; fs.mkdirSync(CAP, { recursive: true });
const EMAILS = __dirname + '/pw_emails.jsonl';
const ESSAI = 'c1e5f73c-0f16-402e-a746-2041e23f72e8';
const R = []; let OK = 0, KO = 0;
const v = (nom, cond, detail = '') => { (cond ? OK++ : KO++); R.push(`${cond ? 'OK  ' : 'RATE'} ${nom}${cond ? '' : '  [' + String(detail).slice(0, 300) + ']'}`); };
const uid = Date.now().toString(36);
const EMAIL = `pw-essai-${uid}@example.com`;
const TEL = '+41 79 ' + String(Date.now() % 10000000).padStart(7, '0').replace(/(\d{3})(\d{2})(\d{2})/, '$1 $2 $3');
const lireEmails = () => { try { return fs.readFileSync(EMAILS, 'utf8').trim().split('\n').filter(Boolean).map(l => JSON.parse(l)); } catch (e) { return []; } };
const attendreEmail = async (pred, ms = 30000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { const m = lireEmails().filter(pred); if (m.length) return m[m.length - 1]; await new Promise(r => setTimeout(r, 500)); } return null; };
const otpDe = (html) => { const m = (html || '').replace(/<[^>]+>/g, ' ').match(/\b(\d{6})\b/); return m ? m[1] : ''; };

async function parcours(nom, fn) { if (process.env.PARCOURS && !process.env.PARCOURS.split(',').includes(nom)) return; try { await fn(); } catch (e) { v(`${nom}. ERREUR d'exécution`, false, String(e).split('\n')[0]); } }

async function entrerDansEspace(p, tag, code) {
  await p.goto(`${BASE}/espace/${code}`, { waitUntil: 'domcontentloaded' });
  await p.waitForSelector('[data-testid="espace-email"], [data-testid="subscriber-space-header"]', { timeout: 30000 });
  if (await p.locator('[data-testid="subscriber-space-header"]').count()) { v(`${tag}. l'espace s'ouvre directement (session d'appareil valide)`, true); return; }
  // Anti-renvoi B3-S1 : 120 s entre deux demandes d'OTP pour le même code (règle du moteur, pas du test).
  if (global.__dernierOtp) { const reste = 125000 - (Date.now() - global.__dernierOtp); if (reste > 0) { v(`${tag}. (attente de ${Math.ceil(reste / 1000)} s : anti-renvoi OTP 120 s du moteur)`, true); await p.waitForTimeout(reste); } }
  global.__dernierOtp = Date.now();
  await p.fill('[data-testid="espace-email"]', EMAIL);
  const nAvant = lireEmails().length;
  await p.click('[data-testid="espace-valider"]');
  try { await p.waitForSelector('[data-testid="espace-otp"]', { timeout: 45000 }); }
  catch (e) { v(`${tag}. écran OTP non atteint`, false, 'erreur affichée=' + (await p.locator('[data-testid="espace-erreur"]').textContent().catch(() => '')) + ' | info=' + (await p.locator('[data-testid="espace-info"]').textContent().catch(() => ''))); throw e; }
  const mail = await attendreEmail((m, i) => (m.to || []).includes(EMAIL) && /code|otp|vérif|verif/i.test(m.subject || '') , 30000);
  v(`${tag}. un e-mail OTP est émis vers l'adresse enregistrée (faux Resend, jamais envoyé)`, !!mail, JSON.stringify(lireEmails().slice(nAvant).map(m => m.subject)));
  const otp = otpDe(mail && mail.html);
  v(`${tag}. l'OTP a 6 chiffres`, /^\d{6}$/.test(otp), otp);
  await p.fill('[data-testid="espace-otp"]', otp);
  await p.click('[data-testid="espace-valider"]');
  await p.waitForSelector('[data-testid="subscriber-space-header"]', { timeout: 30000 });
  v(`${tag}. l'espace s'ouvre après l'OTP`, true);
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  let code = '';

  // ═══ PARCOURS 2 — visiteur → premier cours gratuit → inscription → réservation ═══
  await parcours('P2', async () => {
    const ctx = await browser.newContext({ ...devices['iPhone 13'] });
    const p = await ctx.newPage();
    p.on('dialog', async d => { v('P2. dialogue inattendu : ' + d.message().slice(0, 80), false); await d.dismiss(); });
    // Entrée = ce que produit le tunnel du hero et la page SEO : /?offre=<essai>&reserver=1
    await p.goto(`${BASE}/?offre=${ESSAI}&reserver=1`, { waitUntil: 'domcontentloaded' });
    await p.waitForSelector('[data-testid="user-email-input"]', { timeout: 30000 });
    await p.waitForTimeout(3000);
    v('P2. le lien profond du tunnel ouvre le formulaire d\'essai (et il RESTE ouvert)', await p.locator('[data-testid="user-email-input"]').count() === 1);
    await p.locator('[data-testid="user-email-input"]').scrollIntoViewIfNeeded();
    await p.screenshot({ path: `${CAP}/P2-1-formulaire.png` });
    await p.fill('[data-testid="user-name-input"]', 'Test Essai PW');
    await p.fill('[data-testid="user-email-input"]', EMAIL);
    await p.fill('[data-testid="user-whatsapp-input"]', TEL);
    if (await p.locator('[data-testid="user-birthday-input"]').count()) await p.fill('[data-testid="user-birthday-input"]', '1990-05-05');
    if (await p.locator('[data-testid="conditions-case"]').count()) await p.locator('[data-testid="conditions-case"]').check({ force: true });
    const bouton = p.locator('[data-testid="submit-reservation-btn"]');
    v('P2. le bouton dit « gratuit » et est actif', /gratuit|free/i.test((await bouton.textContent()) || '') && !(await bouton.isDisabled()), await bouton.textContent());
    await bouton.click();
    await p.waitForURL(/\/espace\/AFR-/, { timeout: 40000 }).catch(() => null);
    v('P2. après l\'octroi, redirection vers /espace/AFR-… (ESSAI-7)', /\/espace\/AFR-/.test(p.url()), p.url());
    code = (p.url().match(/AFR-[A-Z0-9]+/) || [''])[0];
    const bienvenue = await attendreEmail(m => (m.to || []).includes(EMAIL) && /AFR-/.test(m.html || ''), 20000);
    v('P2. e-mail d\'accès avec le code AFR- et le bouton « Réserver ma séance » (faux Resend)', !!bienvenue && /R[ée]server/i.test(bienvenue.html), bienvenue && bienvenue.subject);
    await p.screenshot({ path: `${CAP}/P2-2-espace-otp.png` });
    // L'espace exige l'OTP même juste après l'octroi (double saisie constatée par l'audit) :
    v('P2. l\'espace redemande l\'e-mail + OTP juste après l\'octroi (constat B3 : double saisie)', await p.locator('[data-testid="espace-email"]').count() === 1);
    await entrerDansEspace(p, 'P2', code);
    await p.screenshot({ path: `${CAP}/P2-3-espace.png` });
    const texte = await p.textContent('body');
    v('P2. l\'espace montre l\'essai (bandeau essai / 1 séance)', /essai/i.test(texte || ''), (texte || '').slice(0, 100));
    // Réservation d'un créneau depuis l'espace
    const choisir = p.locator('[data-testid="essai7-choisir"]');
    if (await choisir.count()) await choisir.click();
    await p.waitForTimeout(1000);
    if (await p.locator('[data-testid="conditions-case"]').count()) await p.locator('[data-testid="conditions-case"]').first().check({ force: true });
    const reserver = p.locator('[data-testid^="reserve-"]');
    v('P2. un créneau est proposé avec un bouton « Réserver »', await reserver.count() >= 1, `${await reserver.count()} bouton(s) ; aucun créneau=${await p.locator('[data-testid="essai7-aucun-creneau"]').count()}`);
    if (await reserver.count()) {
      await reserver.first().scrollIntoViewIfNeeded();
      await reserver.first().click();
      await p.waitForSelector('[data-testid="p2ux-confirmation"]', { timeout: 60000 }).catch(() => null);
      await p.waitForTimeout(1000);
      await p.screenshot({ path: `${CAP}/P2-4-reservation.png` });
      v('P2. confirmation visible après la réservation', (await p.locator('[data-testid="p2ux-confirmation"]').count()) >= 1 || /confirm/i.test(await p.textContent('body')), (await p.textContent('body')).slice(0, 120));
      const conf = await attendreEmail(m => (m.to || []).includes(EMAIL) && /r[ée]serv|confirm/i.test(m.subject || ''), 20000);
      v('P2. e-mail de confirmation de réservation (faux Resend)', !!conf, conf && conf.subject);
    }
    await ctx.close();
  });

  // ═══ PARCOURS 3 — reconnexion plus tard (autre appareil) → espace → mes réservations ═══
  await parcours('P3', async () => {
    v('P3. un code d\'essai existe pour ce parcours', !!code, code);
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });   // « autre appareil » : contexte vierge
    const p = await ctx.newPage();
    await entrerDansEspace(p, 'P3', code);
    await p.screenshot({ path: `${CAP}/P3-1-espace-desktop.png` });
    const texte = await p.textContent('body');
    v('P3. l\'offre et les droits sont visibles (essai / séance)', /essai|s[ée]ance/i.test(texte || ''));
    v('P3. la réservation faite au P2 est visible (mes prochaines séances)', (await p.locator('[data-testid="subscriber-space-reservation"]').count()) >= 1 || /prochaine/i.test(texte || ''), (texte || '').slice(0, 160));
    v('P3. bouton « Se déconnecter de cet appareil » présent', (await p.locator('[data-testid="espace-deconnexion"]').count()) === 1);
    // Reconnexion sur le MÊME appareil : la session tient (jeton 30 j)
    await p.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' }); await p.waitForTimeout(1500);
    await p.goto(`${BASE}/espace/${code}`, { waitUntil: 'domcontentloaded' });
    await p.waitForSelector('[data-testid="subscriber-space-header"], [data-testid="espace-email"]', { timeout: 30000 });
    v('P3. retour sur /espace/CODE sans OTP (session d\'appareil conservée)', (await p.locator('[data-testid="subscriber-space-header"]').count()) === 1);
    await ctx.close();
  });

  // ═══ P5 bis — double inscription : le même e-mail ne reçoit pas un 2e essai ═══
  await parcours('P5b', async () => {
    const ctx = await browser.newContext({ ...devices['iPhone 13'] });
    const p = await ctx.newPage();
    await p.goto(`${BASE}/?offre=${ESSAI}&reserver=1`, { waitUntil: 'domcontentloaded' });
    await p.waitForSelector('[data-testid="user-email-input"]', { timeout: 30000 }); await p.waitForTimeout(2500);
    await p.fill('[data-testid="user-name-input"]', 'Test Essai PW');
    await p.fill('[data-testid="user-email-input"]', EMAIL);
    await p.fill('[data-testid="user-whatsapp-input"]', TEL.replace(/\d$/, d => String((Number(d) + 1) % 10)));
    if (await p.locator('[data-testid="user-birthday-input"]').count()) await p.fill('[data-testid="user-birthday-input"]', '1990-05-05');
    if (await p.locator('[data-testid="conditions-case"]').count()) await p.locator('[data-testid="conditions-case"]').check({ force: true });
    let dialogue = ''; p.on('dialog', async d => { dialogue = d.message(); await d.dismiss(); });
    await p.click('[data-testid="submit-reservation-btn"]');
    await p.waitForTimeout(5000);
    const texte = await p.textContent('body');
    v('P5b. second essai avec le même e-mail REFUSÉ (message visible, pas de 2e code)', !/\/espace\/AFR-/.test(p.url()) && (/déjà|deja|un seul|essai/i.test(dialogue + ' ' + (texte || ''))), (dialogue || (texte || '').slice(0, 120)));
    await ctx.close();
  });

  // ═══ PARCOURS 3 bis — un acheteur Fondateurs (parcours 1) entre dans son espace ═══
  await parcours('P3b', async () => {
    const bienvenue = lireEmails().filter(m => /Bienvenue chez Afroboost - Ton code AFR-/.test(m.subject || '') && (m.to || [])[0] && /^pw-[0-9a-f]{8}@example\.com$/.test((m.to || [])[0]));
    v('P3b. un e-mail d\'accès Fondateurs existe (issu du parcours 1)', bienvenue.length >= 1, String(bienvenue.length));
    if (!bienvenue.length) return;
    const m = bienvenue[bienvenue.length - 1];
    const codeF = (m.subject.match(/AFR-[A-Z0-9]+/) || [''])[0];
    const emailF = m.to[0];
    v('P3b. l\'e-mail d\'accès dit « 8 seance(s) par mois, renouvelées automatiquement » et comment arrêter (correction)', /8 s[ée]ance/i.test(m.html) && /par mois/.test(m.html) && /renouvel/.test(m.html) && /contact@afroboosteur.com/.test(m.html), m.html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').slice(0, 300));
    const ctx = await browser.newContext({ ...devices['iPhone 13'] });
    const p = await ctx.newPage();
    await p.goto(`${BASE}/espace/${codeF}`, { waitUntil: 'domcontentloaded' });
    try { await p.waitForSelector('[data-testid="espace-email"]', { timeout: 30000 }); }
    catch (e) { await p.screenshot({ path: `${CAP}/P3b-echec-entree.png` }); v('P3b. écran d\'identification non atteint', false, (await p.textContent('body')).replace(/\s+/g, ' ').slice(0, 200)); throw e; }
    if (global.__dernierOtp) { const reste = 125000 - (Date.now() - global.__dernierOtp); if (reste > 0) await p.waitForTimeout(reste); }
    global.__dernierOtp = Date.now();
    await p.fill('[data-testid="espace-email"]', emailF);
    await p.click('[data-testid="espace-valider"]');
    try { await p.waitForSelector('[data-testid="espace-otp"]', { timeout: 45000 }); }
    catch (e) { v('P3b. écran OTP non atteint', false, 'erreur=' + (await p.locator('[data-testid="espace-erreur"]').textContent().catch(() => '')) + ' url=' + p.url()); throw e; }
    const mail = await attendreEmail(x => (x.to || []).includes(emailF) && /code de v/i.test(x.subject || ''), 30000);
    await p.fill('[data-testid="espace-otp"]', otpDe(mail && mail.html));
    await p.click('[data-testid="espace-valider"]');
    // Nouvel acheteur : l'onboarding « Complète ton profil » (nom, WhatsApp, objectifs, opt-in WA) précède l'espace.
    await p.waitForSelector('[data-testid="subscriber-space-header"], [data-testid="onboarding-objectifs"]', { timeout: 30000 });
    if (await p.locator('[data-testid="onboarding-objectifs"]').count()) {
      v('P3b. un nouvel acheteur passe par « Complète ton profil » (WhatsApp, objectifs, opt-in WhatsApp non pré-coché)', !(await p.locator('[data-testid="onboarding-optin-wa"]').isChecked().catch(() => false)));
      await p.screenshot({ path: `${CAP}/P3b-onboarding.png` });
      await p.getByRole('button', { name: /C'est parti|Plus tard/ }).first().click();
    }
    try { await p.waitForSelector('[data-testid="subscriber-space-header"]', { timeout: 30000 }); }
    catch (e) { v('P3b. espace non ouvert après OTP', false, 'otp=' + otpDe(mail && mail.html) + ' erreur=' + (await p.locator('[data-testid="espace-erreur"]').textContent().catch(() => ''))); throw e; }
    await p.screenshot({ path: `${CAP}/P3b-espace-fondateurs.png`, fullPage: true });
    const texte = (await p.textContent('body')) || '';
    v('P3b. l\'espace Fondateurs montre l\'offre et 8 séances', /Fondateurs/.test(texte) && /8/.test(texte), texte.slice(0, 200));
    v('P3b. l\'espace NE montre PAS « mensuel », le prix récurrent ni de bouton de résiliation (constat audit : D)', !/59 CHF|r[ée]silier|prochaine [ée]ch[ée]ance/i.test(texte));
    const reserver = p.locator('[data-testid^="reserve-"]');
    v('P3b. des créneaux réservables sont proposés', await reserver.count() >= 1, String(await reserver.count()));
    await ctx.close();
  });

  await browser.close();
  console.log(R.join('\n'));
  console.log(`\n${OK}/${OK + KO} au vert (Playwright parcours 2, 3, 3b, 5b)`);
  process.exit(KO ? 1 : 0);
})().catch(e => { console.error('ERREUR', e); process.exit(2); });
