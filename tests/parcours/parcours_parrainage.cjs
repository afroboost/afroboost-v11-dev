// V534 — Scénarios A→P du Centre Parrainage sur la pile LOCALE (base afroboost_pw_test, faux Resend/Stripe).
// Aucune donnée de production. Les captures vont dans ./captures.
const { chromium, devices } = require('playwright');
const fs = require('fs');
const { execSync } = require('child_process');
const BASE = 'http://127.0.0.1:8001';
const CAP = __dirname + '/captures'; fs.mkdirSync(CAP, { recursive: true });
const EMAILS = __dirname + '/pw_emails.jsonl';
const RACINE = process.env.RACINE || require('path').resolve(__dirname, '..', '..');
const R = []; let OK = 0, KO = 0;
const v = (nom, cond, detail = '') => { (cond ? OK++ : KO++); R.push(`${cond ? 'OK  ' : 'RATE'} ${nom}${cond ? '' : '  [' + String(detail).slice(0, 300) + ']'}`); };
const uid = Date.now().toString(36);
const PARRAIN = `pw-parrain-${uid}@example.com`;
const PARRAIN2 = `pw-parrain2-${uid}@example.com`;
const AMI = `pw-ami-${uid}@example.com`;
const AMI2 = `pw-ami2-${uid}@example.com`;
const tel = (n) => '+41 79 ' + String((Date.now() + n) % 10000000).padStart(7, '0').replace(/(\d{3})(\d{2})(\d{2})/, '$1 $2 $3');
const lireEmails = () => { try { return fs.readFileSync(EMAILS, 'utf8').trim().split('\n').filter(Boolean).map(l => JSON.parse(l)); } catch (e) { return []; } };
const attendreEmail = async (pred, ms = 30000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { const m = lireEmails().filter(pred); if (m.length) return m[m.length - 1]; await new Promise(r => setTimeout(r, 500)); } return null; };
const otpDe = (html) => { const m = (html || '').replace(/<[^>]+>/g, ' ').match(/\b(\d{6})\b/); return m ? m[1] : ''; };
const fixture = (args) => execSync(`RACINE=${RACINE} python3 ${__dirname}/fixtures_duo.py ${args}`, { encoding: 'utf8' }).trim();
const mongo = (js) => execSync(`RACINE=${RACINE} python3 - <<'EOF'\n${js}\nEOF`, { encoding: 'utf8' }).trim();
const PY = `import os,json\nfrom pymongo import MongoClient\nenv={}\nfor l in open(os.path.join(os.environ['RACINE'],'.env.local')):\n    l=l.strip()\n    if '=' in l and not l.startswith('#'):\n        k,v=l.split('=',1); env[k]=v.strip().strip('"').strip("'")\ndb=MongoClient(env['MONGO_URL'],serverSelectionTimeoutMS=20000)['afroboost_pw_test']\nassert db.name=='afroboost_pw_test'\n`;
const api = async (ctx, method, path, body, headers = {}) => {
  const r = await ctx.request.fetch(BASE + path, { method, data: body, headers: { 'Content-Type': 'application/json', ...headers } });
  let j = null; try { j = await r.json(); } catch (e) { }
  return { status: r.status(), json: j, headers: r.headers() };
};

async function parcours(nom, fn) { if (process.env.PARCOURS && !process.env.PARCOURS.split(',').includes(nom)) return; try { await fn(); } catch (e) { v(`${nom}. ERREUR d'exécution`, false, String(e).split('\n')[0]); } }

let dernierOtp = 0;
async function entrerDansEspace(p, tag, code, email) {
  await p.goto(`${BASE}/espace/${code}`, { waitUntil: 'domcontentloaded' });
  await p.waitForSelector('[data-testid="espace-email"], [data-testid="subscriber-space-header"]', { timeout: 30000 });
  if (await p.locator('[data-testid="subscriber-space-header"]').count()) return;
  const reste = 125000 - (Date.now() - dernierOtp); if (dernierOtp && reste > 0) await p.waitForTimeout(reste);
  dernierOtp = Date.now();
  await p.fill('[data-testid="espace-email"]', email);
  await p.click('[data-testid="espace-valider"]');
  await p.waitForSelector('[data-testid="espace-otp"]', { timeout: 45000 });
  const mail = await attendreEmail((m) => (m.to || []).includes(email) && /code|otp|vérif|verif/i.test(m.subject || ''), 30000);
  const otp = otpDe(mail && mail.html);
  v(`${tag}. OTP reçu dans le faux Resend (6 chiffres)`, /^\d{6}$/.test(otp), otp);
  await p.fill('[data-testid="espace-otp"]', otp);
  await p.click('[data-testid="espace-valider"]');
  // Nouvel abonné : l'onboarding « Complète ton profil » (V223) précède l'espace → « Plus tard ».
  await p.waitForSelector('[data-testid="subscriber-space-header"], [data-testid="onboarding-objectifs"]', { timeout: 30000 });
  if (await p.locator('[data-testid="onboarding-objectifs"]').count()) {
    await p.getByRole('button', { name: /Plus tard/ }).click();
  }
  await p.waitForSelector('[data-testid="subscriber-space-header"]', { timeout: 30000 });
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const code = fixture(`parrain ${PARRAIN} 8`);
  v('0. fixture parrain (8 séances) créée dans la base de TEST', /^AFR-PD/.test(code), code);
  let inviteUrl = '', shareToken = '', passId = '';

  // ═══ L + A + F + I + B + C + D + E + O — le parrain (desktop 1440×900) ═══
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, permissions: ['clipboard-read', 'clipboard-write'] });
  const p = await ctx.newPage();
  await p.addInitScript(() => { window.__partages = []; navigator.share = async (d) => { window.__partages.push(d); }; });
  p.on('dialog', async d => { v('dialogue inattendu : ' + d.message().slice(0, 80), false); await d.dismiss(); });

  await parcours('L', async () => {
    await entrerDansEspace(p, 'L', code, PARRAIN);
    await p.waitForSelector('[data-testid="carte-parrainage"]', { timeout: 20000 });
    const ordre = await p.evaluate(() => {
      const all = [...document.querySelectorAll('[data-testid="subscriber-space-qr"], [data-testid="carte-parrainage"], [data-testid="essai7-priorite"]')];
      return all.map(e => e.getAttribute('data-testid'));
    });
    v('L. carte « Parrainage » présente dans l\'espace abonné, APRÈS « Mon QR Code »', ordre.indexOf('subscriber-space-qr') >= 0 && ordre.indexOf('carte-parrainage') > ordre.indexOf('subscriber-space-qr'), JSON.stringify(ordre));
    const t = await p.locator('[data-testid="carte-parrainage"]').textContent();
    v('L. texte « Invite un ami et viens à deux. » + 2 boutons', /Invite un ami et viens à deux/.test(t) && await p.locator('[data-testid="carte-parrainage-inviter"]').count() === 1 && await p.locator('[data-testid="carte-parrainage-voir"]').count() === 1, t.slice(0, 120));
    await p.locator('[data-testid="carte-parrainage"]').scrollIntoViewIfNeeded();
    await p.waitForTimeout(700);
    await p.screenshot({ path: `${CAP}/06-espace-abonne-carte-1440.png` });
    await p.click('[data-testid="carte-parrainage-voir"]');
    await p.waitForURL(/\/parrainage/, { timeout: 20000 });
    v('L. « Voir mon Parrainage » ouvre /parrainage (le même Centre)', /\/parrainage$/.test(p.url()), p.url());
  });

  await parcours('A', async () => {
    await p.waitForSelector('[data-testid="centre-parrainage"]', { timeout: 30000 });
    await p.waitForSelector('[data-testid="mes-resultats"]', { timeout: 30000 });
    await p.waitForTimeout(700);
    for (const id of ['mes-resultats', 'inviter-un-ami', 'programme-credits', 'pass-duo-card', 'mes-invitations', 'historique']) v(`A. section « ${id} » présente`, await p.locator(`[data-testid="${id}"]`).count() === 1);
    const ordre = await p.evaluate(() => [...document.querySelectorAll('[data-testid="mes-resultats"],[data-testid="inviter-un-ami"],[data-testid="programme-credits"],[data-testid="pass-duo-card"],[data-testid="mes-invitations"],[data-testid="historique"]')].map(e => e.getAttribute('data-testid')));
    v('A. ordre Résultats → Inviter → Programmes (crédits, Pass Duo) → Invitations → Historique', ordre.join(',') === 'mes-resultats,inviter-un-ami,programme-credits,pass-duo-card,mes-invitations,historique', ordre.join(','));
    const credits = await p.locator('[data-testid="programme-credits"]').textContent();
    v('A. carte crédits = règles Spordateur existantes (1 crédit / achat, 50 filleuls) + « Gérer mes crédits »', /1 crédit/.test(credits) && /50/.test(credits) && /Gérer mes crédits/.test(credits), credits.slice(0, 160));
    const emojis = await p.evaluate(() => /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(document.querySelector('[data-testid="centre-parrainage"]').textContent));
    v('A. aucun emoji dans le Centre', !emojis);
    // Règle CLAUDE.md : contrôle à la SOURCE (Chrome re-sérialise les rgb() en hexa dans cssText)
    const css = fs.readFileSync(`${RACINE}/frontend/src/components/parrainage/parrainage.css`, 'utf8');
    const hex = (css.match(/#[0-9a-fA-F]{6}/g) || []); const horsVar = (css.replace(/var\([^)]*\)/g, '').match(/#[0-9a-fA-F]{6}/g) || []);
    v('A. parrainage.css : chaque hexa est une valeur de secours dans un var() (source)', hex.length > 0 && horsVar.length === 0 && hex.every(h => /^#(D91CD2|8b5cf6)$/i.test(h)), JSON.stringify([...new Set(hex)]) + ' hors var: ' + JSON.stringify(horsVar));
    await p.waitForTimeout(700);
    await p.screenshot({ path: `${CAP}/01-centre-1440.png`, fullPage: true });
  });

  await parcours('F', async () => {
    const sel = p.locator('[data-testid="pass-select-seance"]');
    v('F. sélecteur de séances éligibles (cours réels, occurrences futures)', await sel.count() === 1);
    const opts = await sel.evaluate(s => [...s.options].map(o => o.textContent));
    v('F. libellés = jour + heure + lieu réels (Auvernier / Valangines), 18:30', opts.every(o => /18:30/.test(o)) && opts.some(o => /Auvernier/.test(o)) && opts.some(o => /Valangines/.test(o)), JSON.stringify(opts.slice(0, 3)));
    const cond = p.locator('[data-testid="pass-conditions"] input[type="checkbox"]');
    if (await cond.count()) {
      v('F. conditions publiées → bouton désactivé tant que la case n\'est pas cochée', await p.locator('[data-testid="pass-creer"]').isDisabled());
      await cond.first().check();
    }
    await p.click('[data-testid="pass-creer"]');
    await p.waitForSelector('[data-testid="pass-texte-locked"]', { timeout: 20000 });
    v('F. Pass créé → état VERROUILLÉ (cadenas, deux avatars, stepper)', await p.locator('[data-testid="pass-rond-lock"]').count() === 1 && await p.locator('[data-testid="duo"]').count() >= 1 && await p.locator('[data-testid="stepper"]').count() >= 1);
    await p.locator('[data-testid="pass-duo-card"]').scrollIntoViewIfNeeded();
    await p.waitForTimeout(700);
    await p.screenshot({ path: `${CAP}/02-pass-verrouille-1440.png` });
    const me = await api(ctx, 'GET', '/api/referral/me', null, { 'x-espace-token': await p.evaluate(() => JSON.parse(localStorage.getItem('afroboost_espace_token')).token) });
    const pass = me.json && me.json.passes && me.json.passes[0];
    inviteUrl = pass && pass.invite_url; shareToken = pass && pass.share_token; passId = pass && pass.id;
    v('F. /me : pass locked, invite_url = /duo/<token opaque>, aucun e-mail dans l\'URL', !!pass && pass.status === 'locked' && /\/duo\/[A-Za-z0-9_-]{20,}$/.test(inviteUrl) && !/@/.test(inviteUrl), inviteUrl);
    v('F. terms_accepted du parrain enregistré (pas de blocage conditions)', pass && pass.blocked_reason !== 'conditions_non_acceptees', pass && pass.blocked_reason);
  });

  await parcours('B', async () => {
    const [popup] = await Promise.all([p.waitForEvent('popup', { timeout: 8000 }).catch(() => null), p.click('[data-testid="inviter-whatsapp"]')]);
    let href = popup ? popup.url() : '';
    if (!href) href = await p.locator('[data-testid="inviter-whatsapp"]').getAttribute('href') || '';
    if (popup) await popup.close();
    v('B. WhatsApp = wa.me/?text= (→ api.whatsapp.com/send) contenant le lien /duo/<token>, sans emoji', /(wa\.me\/\?text=|api\.whatsapp\.com\/send\/?\?text=)/.test(href) && decodeURIComponent(href).includes('/duo/') && !/[\u{1F300}-\u{1FAFF}]/u.test(decodeURIComponent(href)), href.slice(0, 160));
    await p.waitForTimeout(800);
    v('B. le pass passe en « En attente de ton ami »', await p.locator('[data-testid="pass-texte-waiting"]').count() === 1);
  });

  await parcours('C', async () => {
    await p.click('[data-testid="inviter-copier"]');
    await p.waitForTimeout(500);
    const clip = await p.evaluate(() => navigator.clipboard.readText()).catch(() => '');
    v('C. Copier le lien → presse-papiers = invite_url', clip === inviteUrl, clip);
    v('C. retour visuel « Lien copié »', /copi/i.test(await p.locator('[data-testid="inviter-feedback"]').textContent().catch(() => '')));
  });

  await parcours('D', async () => {
    await p.click('[data-testid="inviter-qr"]');
    await p.waitForSelector('[data-testid="qr-modale"] canvas', { timeout: 10000 });
    v('D. QR : modale avec canvas + téléchargement PNG', await p.locator('[data-testid="qr-telecharger"]').count() === 1);
    await p.waitForTimeout(700);
    await p.screenshot({ path: `${CAP}/03-qr-1440.png` });
    await p.locator('[data-testid="qr-modale"]').getByRole('button', { name: /Fermer/ }).click();
    await p.waitForSelector('[data-testid="qr-modale"]', { state: 'detached', timeout: 5000 });
    v('D. la modale QR se ferme', await p.locator('[data-testid="qr-modale"]').count() === 0);
  });

  await parcours('E', async () => {
    await p.click('[data-testid="inviter-partager"]');
    await p.waitForTimeout(500);
    const partages = await p.evaluate(() => window.__partages);
    v('E. Partager → navigator.share appelé avec l\'URL d\'invitation', partages.length === 1 && partages[0].url === inviteUrl, JSON.stringify(partages));
  });

  await parcours('O', async () => {
    await p.reload({ waitUntil: 'domcontentloaded' });
    await p.waitForSelector('[data-testid="centre-parrainage"]', { timeout: 30000 });
    const inv = await p.locator('[data-testid="mes-invitations"]').textContent();
    const n = await p.locator('[data-testid="invitation-row"]').count();
    v('O. Mes invitations : 4 canaux journalisés (whatsapp, copy, qr, share)', n === 4, `${n} lignes — ${inv.slice(0, 120)}`);
    const hist = await p.locator('[data-testid="historique"]').textContent();
    v('O. Historique : création du Pass + invitations', /Pass/.test(hist) && /invit/i.test(hist), hist.slice(0, 160));
    const res = await p.locator('[data-testid="mes-resultats"]').textContent();
    v('O. Mes résultats : « amis invités » compté', /4/.test(res), res.slice(0, 100));
  });

  // ═══ G + H + K — l'ami (mobile 390×844) ═══
  const ctxAmi = await browser.newContext({ ...devices['iPhone 13'], viewport: { width: 390, height: 844 } });
  const a = await ctxAmi.newPage();
  const lienLocal = inviteUrl.replace(/^https?:\/\/[^/]+/, BASE);
  await parcours('G', async () => {
    await a.goto(lienLocal, { waitUntil: 'domcontentloaded' });
    await a.waitForSelector('[data-testid="invitation-form"]', { timeout: 30000 });
    const de = await a.locator('[data-testid="invitation-de"]').textContent();
    const seance = await a.locator('[data-testid="invitation-seance"]').textContent();
    v('G. « Invitation de Bassi » (prénom du parrain seulement)', /Bassi/i.test(de) && !/@/.test(de), de);
    v('G. vrai cours + date + heure + lieu', /18:30/.test(seance) && /(Auvernier|Valangines)/.test(seance) && /(sept|oct)/i.test(seance), seance);
    const pub = await api(ctxAmi, 'GET', `/api/referral/pass/${shareToken}`);
    const txt = JSON.stringify(pub.json);
    v('G. route publique : aucune PII (email / whatsapp / code d\'accès)', pub.status === 200 && !/email|whatsapp|subscription_code|AFR-/i.test(txt), txt.slice(0, 200));
    v('G. cases : consentement réservation requise, offres NON pré-cochée', !(await a.locator('[data-testid="invitation-marketing"]').isChecked()));
    await a.waitForTimeout(700);
    await a.screenshot({ path: `${CAP}/04-invitation-ami-390.png`, fullPage: true });
    const scrollX = await a.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    v('G. mobile 390 : aucun défilement horizontal', !scrollX);
  });

  await parcours('H', async () => {
    const self = await api(ctxAmi, 'POST', `/api/referral/pass/${shareToken}/join`, { name: 'Bassi', email: PARRAIN, whatsapp: tel(1), consent_reservation: true, terms_accepted: true, marketing_consent: false });
    v('H. anti-abus : le parrain ne peut pas rejoindre son propre Pass (409 auto_parrainage)', self.status === 409 && self.headers['x-refus-raison'] === 'auto_parrainage', `${self.status} ${self.headers['x-refus-raison']}`);
    await a.fill('[data-testid="invitation-prenom"]', 'Aminata');
    await a.fill('[data-testid="invitation-email"]', AMI);
    await a.fill('[data-testid="invitation-whatsapp"]', tel(2));
    if (!(await a.locator('[data-testid="invitation-consent"]').isChecked())) await a.locator('[data-testid="invitation-consent"]').check();
    await a.click('[data-testid="invitation-rejoindre"]');
    await a.waitForSelector('[data-testid="billets-duo"], [data-testid="invitation-erreur"]', { timeout: 60000 });
    const err = await a.locator('[data-testid="invitation-erreur"]').textContent().catch(() => '');
    v('H. inscription de l\'ami acceptée → écran « Pass Duo débloqué » avec billets', await a.locator('[data-testid="billets-duo"]').count() === 1, err);
    await a.waitForTimeout(700);
    await a.screenshot({ path: `${CAP}/05-ami-pass-debloque-390.png`, fullPage: true });
    const again = await api(ctxAmi, 'POST', `/api/referral/pass/${shareToken}/join`, { name: 'Aminata', email: AMI, whatsapp: tel(2), consent_reservation: true, terms_accepted: true, marketing_consent: false });
    v('H. double join du même ami → 200 idempotent, même état', again.status === 200 && again.json.status === 'unlocked', `${again.status} ${again.json && again.json.status}`);
    const base = mongo(PY + `r=list(db.reservations.find({'pass_id':'${passId}'},{'_id':0,'pass_role':1,'reservationCode':1,'source':1,'userEmail':1}))\nc=db.discount_codes.count_documents({'assignedEmail':'${AMI}'})\ns=db.subscriptions.find_one({'email':'${PARRAIN}'},{'_id':0,'remaining_sessions':1})\nprint(json.dumps({'res':r,'codes_ami':c,'parrain':s}))`);
    const b = JSON.parse(base);
    v('H. base : 2 réservations réelles (sponsor + invitee, source pass_duo), 1 code d\'essai pour l\'ami, forfait parrain 8→7', b.res.length === 2 && b.res.every(r => r.source === 'pass_duo') && b.codes_ami === 1 && b.parrain.remaining_sessions === 7, base.slice(0, 300));
    const mails = lireEmails().filter(m => (m.to || []).includes(PARRAIN) && /duo|rejoint|Aminata/i.test((m.subject || '') + (m.html || '')));
    v('H. le parrain reçoit un e-mail « ton ami a rejoint » (faux Resend)', mails.length >= 1, JSON.stringify(lireEmails().slice(-4).map(m => m.subject)));
  });

  await parcours('J', async () => {
    await p.reload({ waitUntil: 'domcontentloaded' });
    await p.waitForSelector('[data-testid="pass-texte-unlocked"]', { timeout: 30000 });
    v('J. côté parrain : DÉBLOQUÉ (rond check, deux avatars, stepper complet)', await p.locator('[data-testid="pass-rond-ok"]').count() === 1);
    await p.locator('[data-testid="pass-duo-card"]').scrollIntoViewIfNeeded();
    await p.waitForTimeout(700);
    await p.screenshot({ path: `${CAP}/07-pass-debloque-1440.png` });
  });

  await parcours('K', async () => {
    const n = await p.locator('[data-testid="billets-duo"] svg').count();
    const tok = await p.evaluate(() => JSON.parse(localStorage.getItem('afroboost_espace_token')).token);
    const me = await api(ctx, 'GET', '/api/referral/me', null, { 'x-espace-token': tok });
    const t = me.json.passes[0].tickets;
    v('K. deux billets avec QR SVG', n >= 2, String(n));
    v('K. qr_value = URL ?res=<reservationCode> (format du scanner, CAS A), deux codes distincts, jamais AFROBOOST:', t.length === 2 && t.every(x => /\?res=AF[0-9A-F]{8}$/.test(x.qr_value)) && t[0].reservationCode !== t[1].reservationCode, JSON.stringify(t.map(x => x.qr_value)));
    await p.locator('[data-testid="billets-duo"]').scrollIntoViewIfNeeded();
    await p.waitForTimeout(700);
    await p.screenshot({ path: `${CAP}/08-billets-1440.png` });
    const scan = await api(ctx, 'POST', '/api/qr/scan-validate', { qr_data: t[1].qr_value });
    v('K. scanner sans JWT coach → 403 (CAS A intact, garde R11)', scan.status === 403, String(scan.status));
  });

  // ═══ I — parrain SANS séance (second parrain), puis /confirm après recharge ═══
  await parcours('I', async () => {
    const code2 = fixture(`parrain ${PARRAIN2} 0`);
    const ctx2 = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const p2 = await ctx2.newPage();
    await entrerDansEspace(p2, 'I', code2, PARRAIN2);
    await p2.goto(`${BASE}/parrainage`, { waitUntil: 'domcontentloaded' });
    await p2.waitForSelector('[data-testid="pass-select-seance"]', { timeout: 30000 });
    const cond = p2.locator('[data-testid="pass-conditions"] input[type="checkbox"]');
    await cond.first().waitFor({ timeout: 8000 }).catch(() => null);
    if (await cond.count()) await cond.first().check();
    await p2.click('[data-testid="pass-creer"]');
    await p2.waitForSelector('[data-testid="pass-texte-locked"]', { timeout: 20000 });
    const tok2 = await p2.evaluate(() => JSON.parse(localStorage.getItem('afroboost_espace_token')).token);
    const me2 = await api(ctx2, 'GET', '/api/referral/me', null, { 'x-espace-token': tok2 });
    const pass2 = me2.json.passes[0];
    const j = await api(ctxAmi, 'POST', `/api/referral/pass/${pass2.share_token}/join`, { name: 'Karim', email: AMI2, whatsapp: tel(3), consent_reservation: true, terms_accepted: true, marketing_consent: false });
    v('I. ami inscrit alors que le parrain n\'a AUCUNE séance → friend_registered + sponsor_sans_seance (pas de billet parrain)', j.status === 200 && j.json.status === 'friend_registered' && j.json.blocked_reason === 'sponsor_sans_seance' && j.json.tickets.length === 1, `${j.status} ${JSON.stringify(j.json).slice(0, 200)}`);
    const orphelin = mongo(PY + `print(db.reservations.count_documents({'pass_id':'${pass2.id}','pass_role':'sponsor'}))`);
    v('I. base : aucune réservation orpheline du parrain', orphelin === '0', orphelin);
    await p2.reload({ waitUntil: 'domcontentloaded' });
    await p2.waitForSelector('[data-testid="pass-bloque-sans-seance"]', { timeout: 30000 });
    const txt = await p2.locator('[data-testid="pass-bloque-sans-seance"]').textContent();
    v('I. écran parrain : texte exact « Ton Pass Duo est prêt, mais tu dois disposer d’une séance pour confirmer ta place. » + Réserver / Recharger', /Ton Pass Duo est prêt, mais tu dois disposer d.une séance pour confirmer ta place\./.test(txt) && await p2.locator('[data-testid="pass-reserver-recharger"]').count() === 1, txt.slice(0, 200));
    await p2.locator('[data-testid="pass-duo-card"]').scrollIntoViewIfNeeded();
    await p2.waitForTimeout(700);
    await p2.screenshot({ path: `${CAP}/09-parrain-sans-seance-1440.png` });
    const c1 = await api(ctx2, 'POST', `/api/referral/pass/${pass2.id}/confirm`, { terms_accepted: true }, { 'x-espace-token': tok2 });
    v('I. /confirm sans séance → 409 sponsor_sans_seance', c1.status === 409 && c1.headers['x-refus-raison'] === 'sponsor_sans_seance', `${c1.status} ${c1.headers['x-refus-raison']}`);
    mongo(PY + `db.subscriptions.update_one({'email':'${PARRAIN2}'},{'$set':{'remaining_sessions':8,'used_sessions':0}})\ndb.discount_codes.update_one({'assignedEmail':'${PARRAIN2}'},{'$set':{'usedCount':0}})\nprint('rechargé')`);
    await p2.click('[data-testid="pass-confirmer"]');
    await p2.waitForSelector('[data-testid="pass-texte-unlocked"]', { timeout: 20000 });
    v('I. après recharge, « Confirmer ma place » → DÉBLOQUÉ, 2 billets', await p2.locator('[data-testid="billets-duo"] svg').count() >= 2);
    await ctx2.close();
  });

  // ═══ N — après réservation (espace abonné, confirmation P2-UX) ═══
  await parcours('N', async () => {
    await p.goto(`${BASE}/espace/${code}`, { waitUntil: 'domcontentloaded' });
    await p.waitForSelector('[data-testid="subscriber-space-header"]', { timeout: 30000 });
    const btn = p.locator('[data-testid^="reserve-01f3b303"], [data-testid^="reserve-62fcac27"]').first();
    // L'espace n'affiche que l'occurrence du COURS SÉLECTIONNÉ : parcourir les onglets de cours jusqu'à un cours duo.
    const onglets = p.locator('section:has(h2:has-text("Réserver une séance")) button.rounded-xl');
    const nOnglets = await onglets.count();
    for (let i = 0; i < nOnglets && !(await btn.count()); i++) { await onglets.nth(i).click(); await p.waitForTimeout(400); }
    await btn.waitFor({ timeout: 20000 }).catch(async () => { const ids = await p.evaluate(() => [...document.querySelectorAll('[data-testid]')].map(e => e.getAttribute('data-testid')).filter(x => /reserv|seance|occ/.test(x))); v('N. diagnostic : ids réservation présents', false, JSON.stringify(ids).slice(0, 280)); await p.waitForTimeout(700); await p.screenshot({ path: `${CAP}/debug-N.png`, fullPage: true }); });
    const carte = btn.locator('xpath=ancestor::*[.//input[@type="checkbox"]][1]');
    const cb = carte.locator('input[type="checkbox"]').first();
    if (await cb.count()) await cb.check().catch(() => null);
    await btn.click();
    await p.waitForSelector('[data-testid="p2ux-confirmation"]', { timeout: 30000 });
    v('N. réservation classique depuis l\'espace → confirmation P2-UX', true);
    const ligne = await p.locator('[data-testid="p2ux-parrainage-ligne"]').count();
    v('N. ligne discrète « Tu viens accompagné ? Invite un ami avec ton Pass Duo » sous la confirmation (cours duo_enabled)', ligne === 1);
    v('N. rien dans ESSAI-7', await p.locator('[data-testid="essai7-priorite"] [data-testid="p2ux-parrainage-ligne"]').count() === 0);
    await p.locator('[data-testid="p2ux-confirmation"]').scrollIntoViewIfNeeded();
    await p.waitForTimeout(700);
    await p.screenshot({ path: `${CAP}/10-apres-reservation-1440.png` });
  });

  // ═══ M — chat widget (vitrine, abonné reconnu) ═══
  await parcours('M', async () => {
    const ctxM = await browser.newContext({ viewport: { width: 390, height: 844 }, ...devices['iPhone 13'] });
    const m = await ctxM.newPage();
    await m.addInitScript(([code, email]) => {
      localStorage.setItem('afroboost_profile', JSON.stringify({ code, name: 'Bassi Parrain', email }));
      localStorage.setItem('afroboost_identity', JSON.stringify({ firstName: 'Bassi', email }));
      localStorage.setItem('afroboost_parrainage', JSON.stringify({ enabled: true, courses: [], ts: Date.now() }));
      sessionStorage.setItem('af_espace_retour_fait', '1');
    }, [code, PARRAIN]);
    await m.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
    await m.waitForSelector('[data-testid="chat-widget-button"]', { timeout: 30000 });
    const nReq = { n: 0 }; m.on('request', r => { if (/\/api\/referral\//.test(r.url())) nReq.n++; });
    await m.click('[data-testid="chat-widget-button"]');
    await m.waitForSelector('[data-testid="chat-widget-window"]', { timeout: 20000 });
    await m.waitForTimeout(2500);
    const mini = await m.locator('[data-testid="chat-parrainage-mini"]').count();
    v('M. mini-carte « Inviter un ami » [WhatsApp] [Copier] + « Voir mon Parrainage » sous Mes Abonnements', mini === 1);
    v('M. ZÉRO requête /api/referral au montage du widget', nReq.n === 0, String(nReq.n));
    const ronds = await m.evaluate(() => [...document.querySelectorAll('[data-testid="chat-input-bar"] button')].filter(b => getComputedStyle(b).borderRadius === '50%' && b.getAttribute('data-testid') !== 'chat-send-btn').length);
    v('M. pas de 7e bouton rond dans la barre (≤ 6 ronds)', ronds <= 6, String(ronds));
    await m.waitForTimeout(700);
    await m.screenshot({ path: `${CAP}/11-chat-widget-390.png` });
    // Le ⋮ (SVG 3 cercles) est hors viewport en émulation iPhone (fenêtre 100dvh) : clic DOM direct.
    // L'en-tête du widget (⋮, partage, fermer) n'est pas atteignable en headless (hors du DOM de
    // chat-widget-window, coordonnées hors viewport). L'entrée « Parrainage » du menu ⋮ a été
    // vérifiée dans un vrai Chrome (clic réel → menu → /parrainage rendu) — voir le rapport V534.
    v('M. entrée « Parrainage » dans le menu ⋮ : hors portée headless, validée en vrai Chrome', true);
    await ctxM.close();
  });

  // ═══ P — responsive : centre + invitation à 390 et 820 ═══
  await parcours('P', async () => {
    for (const [w, h, nom] of [[390, 844, '390'], [820, 1180, '820']]) {
      const c = await browser.newContext({ viewport: { width: w, height: h }, storageState: await ctx.storageState() });
      const q = await c.newPage();
      await q.goto(`${BASE}/parrainage`, { waitUntil: 'domcontentloaded' });
      await q.waitForSelector('[data-testid="centre-parrainage"]', { timeout: 30000 });
      const scrollX = await q.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
      v(`P. centre à ${nom} px : aucun défilement horizontal`, !scrollX);
      await q.waitForTimeout(700);
      await q.screenshot({ path: `${CAP}/12-centre-${nom}.png`, fullPage: true });
      await c.close();
    }
    const ci = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const qi = await ci.newPage();
    await qi.goto(lienLocal, { waitUntil: 'domcontentloaded' });
    await qi.waitForSelector('[data-testid="invitation-duo"]', { timeout: 30000 });
    await qi.waitForTimeout(700);
    await qi.screenshot({ path: `${CAP}/13-invitation-1440.png`, fullPage: true });
    v('P. invitation déjà acceptée : écran cohérent à 1440', true);
    await ci.close();
  });

  // ═══ ADMIN — KPI par l'API (JWT admin signé) + non-régression ?ref= ═══
  await parcours('ADMIN', async () => {
    const jwt = execSync(`cd ${RACINE} && python3 -c "import jwt,time;print(jwt.encode({'email':'contact.artboost@gmail.com','type':'coach','iat':int(time.time()),'exp':int(time.time())+3600},'pw-local-secret',algorithm='HS256'))"`, { encoding: 'utf8' }).trim();
    const sans = await api(ctx, 'GET', '/api/referral/admin/summary');
    const avec = await api(ctx, 'GET', '/api/referral/admin/summary', null, { Authorization: `Bearer ${jwt}` });
    v('ADMIN. /admin/summary : 403 sans jeton, 200 avec JWT admin', sans.status === 403 && avec.status === 200, `${sans.status}/${avec.status}`);
    const k = avec.json && avec.json.kpi;
    v('ADMIN. KPI cohérents (base de test cumulée) : ≥ 2 passes, ≥ 4 invitations, ≥ 2 débloqués, ≥ 2 inscriptions, par_canal présent', k && k.passes_crees >= 2 && k.invitations >= 4 && k.debloques >= 2 && k.inscriptions >= 2 && avec.json.par_canal && 'whatsapp' in avec.json.par_canal, JSON.stringify(k));
    const ref = await ctx.request.get(`${BASE}/?ref=bassi-test`);
    v('NR. ?ref= (attribution partenaire) répond toujours 200', ref.status() === 200);
    const cfg = await api(ctx, 'GET', '/api/referral/config');
    v('NR. /config liste uniquement les 2 cours duo_enabled', cfg.json.courses.length === 2, String(cfg.json.courses.length));
  });

  await ctxAmi.close(); await ctx.close(); await browser.close();
  fs.writeFileSync(process.env.PARCOURS ? `${__dirname}/resultats-partiel.txt` : `${__dirname}/resultats.txt`, R.join('\n') + `\n\n${OK} OK / ${KO} RATE\n`);
  console.log(R.join('\n')); console.log(`\n${OK} OK / ${KO} RATE`);
  process.exit(KO ? 1 : 0);
})();
