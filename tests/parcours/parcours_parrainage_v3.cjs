// V556 — PARRAINAGE V3 « boule de neige » : le parcours du FILLEUL dans un vrai navigateur, sur la pile LOCALE
// (base afroboost_pw_test, faux Stripe/Resend — jamais la production). Aucune requête vers afroboost.com n'est
// laissée partir (routage Playwright : tout hôte autre que 127.0.0.1 en écriture est coupé, afroboost.com entièrement).
//
//   1  parrain fictif → Pass Duo par l'API (jeton abonné signé local) → T0
//   2  étape 1 : qui t'invite, séance, [Continuer] visible sans défiler ; aucun formulaire e-mail ; pas l'ancien CTA
//   3  étape 2 : « Préparation… », carte 1200×630, POST /chain AVANT tout partage, WhatsApp (wa.me + share_url) → /chain/share
//   4  étape 3 : « Invitation prête », formulaire, « M'inscrire à mon essai gratuit » → succès (faux Resend)
//   5  contournement API : join avant partage → 409 invitation_requise ; clé d'appareil (X-Chain-Key) exigée
//   6  chaîne A → B → C → D par les share_url réelles (page d'aperçu → /duo/Tn), vérifiée par l'API admin locale
//   7  deux partages successifs : même jeton, v croissant, pages 200 (og:image absolue, og:url exacte), carte JPEG,
//      robot WhatsApp sans meta refresh
//   8  A recharge après partage → directement l'étape 3
//   9  6 tailles : captures + mesures (défilement horizontal, cibles ≥ 44 px, hauteur en écrans)
//  10  partage natif avec la carte (canShare({files}) simulé) / bouton absent sans canShare
//
// Usage : PW_SCRATCH=<scratch> node parcours_parrainage_v3.cjs   (captures dans $CAPTURES ou <scratch>/captures)
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const BASE = 'http://127.0.0.1:8001';
const RACINE = process.env.RACINE || path.resolve(__dirname, '..', '..');
const SCRATCH = process.env.PW_SCRATCH || __dirname;
const CAP = process.env.CAPTURES || path.join(SCRATCH, 'captures'); fs.mkdirSync(CAP, { recursive: true });
const R = []; let OK = 0, KO = 0;
const v = (nom, cond, detail = '') => { (cond ? OK++ : KO++); R.push(`${cond ? 'OK  ' : 'RATE'} ${nom}${detail !== '' ? '  [' + String(detail).slice(0, 400) + ']' : ''}`); };
const uid = Date.now().toString(36);
const PREFIXE = `pw-v3-${uid}`;
const mail = (n) => `${PREFIXE}-${n}@example.com`;
const PARRAIN = mail('parrain'), PARRAIN_T = mail('parraint');
const TELS = [];
const tel = () => { const n = String(Math.floor(1000000 + Math.random() * 8999999)); const t = `+41 79 ${n.slice(0, 3)} ${n.slice(3, 5)} ${n.slice(5, 7)}`; TELS.push('+4179' + n); return t; };
const fixture = (args) => execSync(`RACINE=${RACINE} python3 ${__dirname}/fixtures_duo.py ${args}`, { encoding: 'utf8' }).trim();
const jwtAbonne = (code, email) => execSync(`python3 -c "import jwt,time;print(jwt.encode({'type':'subscriber','code':'${code}','email':'${email}','iat':int(time.time()),'exp':int(time.time())+3600},'pw-local-secret',algorithm='HS256'))"`, { encoding: 'utf8' }).trim();
const JWT_ADMIN = execSync(`python3 -c "import jwt,time;print(jwt.encode({'email':'contact.artboost@gmail.com','type':'coach','iat':int(time.time()),'exp':int(time.time())+3600},'pw-local-secret',algorithm='HS256'))"`, { encoding: 'utf8' }).trim();
let ipN = 0;
const ip = () => `10.56.${Math.floor(Math.random() * 250) + 1}.${(++ipN % 250) + 1}`;   // quota par IP du serveur (20/h)
const PASS_IDS = [];

const UA_MOBILE = 'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36';
const TAILLES = [
  { w: 360, h: 640, mobile: true }, { w: 390, h: 844, mobile: true }, { w: 414, h: 896, mobile: true }, { w: 430, h: 932, mobile: true },
  { w: 1280, h: 800, mobile: false }, { w: 1440, h: 900, mobile: false },
];

async function api(req, method, p, body, headers = {}) {
  const r = await req.fetch(BASE + p, { method, data: body, headers: { 'Content-Type': 'application/json', 'X-Forwarded-For': ip(), ...headers } });
  let j = null; try { j = await r.json(); } catch (e) { }
  return { status: r.status(), json: j, headers: r.headers() };
}

// ── Le navigateur ─────────────────────────────────────────────────────────
// partage : 'aucun' (navigator.share absent), 'lien' (share sans canShare), 'carte' (share + canShare({files}) vrai)
async function contexte(browser, t, partage = 'aucun') {
  const opts = { viewport: { width: t.w, height: t.h }, serviceWorkers: 'block', permissions: ['clipboard-read', 'clipboard-write'],
                 extraHTTPHeaders: { 'X-Forwarded-For': ip() } };
  if (t.mobile) Object.assign(opts, { isMobile: true, hasTouch: true, deviceScaleFactor: 2, userAgent: UA_MOBILE });
  const ctx = await browser.newContext(opts);
  await ctx.route('**/*', (route) => {
    const u = new URL(route.request().url());
    if (/afroboost\.com$/.test(u.hostname)) return route.abort();                                   // jamais la prod
    if (u.hostname !== '127.0.0.1' && route.request().method() !== 'GET') return route.abort();
    if (u.hostname !== '127.0.0.1' && !/fonts\.(googleapis|gstatic)\.com|cdn\.jsdelivr\.net|cdnjs\.cloudflare\.com/.test(u.hostname)) return route.abort();
    return route.continue();
  });
  await ctx.addInitScript((mode) => {
    window.__opens = []; window.__partages = []; window.__vuPrep = false;
    window.open = function (u) { window.__opens.push(String(u)); return null; };
    try {
      if (mode === 'aucun') { delete Navigator.prototype.share; delete Navigator.prototype.canShare; }
      else {
        Object.defineProperty(Navigator.prototype, 'share', { configurable: true, value: async function (d) {
          const f = (d && d.files) || [];
          window.__partages.push({ text: d && d.text, url: d && d.url, title: d && d.title,
                                   files: f.map((x) => ({ name: x.name, type: x.type, size: x.size })) });
        } });
        if (mode === 'carte') Object.defineProperty(Navigator.prototype, 'canShare', { configurable: true, value: function (d) { return !!(d && d.files && d.files.length && d.files.every((x) => /^image\//.test(x.type))); } });
        else delete Navigator.prototype.canShare;
      }
    } catch (e) { }
    new MutationObserver(() => { if (document.querySelector('[data-testid="wf-preparation"]')) window.__vuPrep = true; })
      .observe(document, { childList: true, subtree: true });
  }, partage);
  return ctx;
}

function journal(page) {
  const j = [];
  page.on('request', (r) => { if (/\/api\/referral\/pass\//.test(r.url())) j.push({ t: Date.now(), m: r.method(), u: r.url().replace(BASE, '') }); });
  page.on('response', async (r) => {
    if (/\/api\/referral\/pass\/[^/]+\/chain(\/share)?$/.test(r.url()) && r.request().method() !== 'GET') {
      try { const e = j.find((x) => x.u === r.url().replace(BASE, '') && x.m === r.request().method() && !x.corps); if (e) { e.status = r.status(); e.corps = await r.json(); } } catch (x) { }
    }
  });
  return j;
}

async function mesurer(page, tag) {
  await page.waitForTimeout(400);
  const m = await page.evaluate(() => {
    const racine = document.querySelector('[data-testid="invitation-duo"]') || document.body;
    const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
    const petits = [...racine.querySelectorAll('button, a[href], input:not([type=hidden]):not([type=checkbox]), textarea, select, label.cp-chk')]
      .filter(vis).map((e) => ({ id: e.getAttribute('data-testid') || (e.textContent || e.getAttribute('placeholder') || e.tagName).trim().slice(0, 30), h: Math.round(e.getBoundingClientRect().height) }))
      .filter((x) => x.h < 44);
    const de = document.documentElement;
    return { iw: window.innerWidth, ih: window.innerHeight, sw: Math.max(de.scrollWidth, document.body.scrollWidth), sh: Math.max(de.scrollHeight, document.body.scrollHeight), petits };
  });
  m.ecrans = +(m.sh / m.ih).toFixed(2);
  m.hscroll = m.sw > m.iw;
  await page.screenshot({ path: path.join(CAP, `${tag}.png`), fullPage: true });
  return m;
}

async function creerPass(req, code, email, courseIdx, occIdx) {
  const cfg = await api(req, 'GET', '/api/referral/config');
  const c = cfg.json.courses[courseIdx];
  const offre = c.default_offer_id || c.offers[0].id;
  const tok = jwtAbonne(code, email);
  const r = await api(req, 'POST', '/api/referral/pass', { course_id: c.id, occurrence: c.occurrences[occIdx], offer_id: offre, terms_accepted: true }, { 'X-Subscriber-Token': tok });
  if (r.json && r.json.id) PASS_IDS.push(r.json.id);
  const token = r.json && (r.json.share_token || String(r.json.invite_url || '').split('/duo/')[1]);
  return { status: r.status, id: r.json && r.json.id, token, dto: r.json };
}

async function adminPasses(req) {
  const r = await api(req, 'GET', '/api/referral/admin/passes?page=1', null, { Authorization: `Bearer ${JWT_ADMIN}` });
  return (r.json && r.json.items) || [];
}
const parJeton = (items, tok) => items.find((p) => String(p.invite_url || '').endsWith('/duo/' + tok) || p.share_token === tok);

// Le parcours du filleul, de l'étape 1 au succès. `action` : 'whatsapp' | 'copy' | 'share_image'.
async function filleul(page, jrn, tag, { action, nom, email, inscrire = true, controles = true, surEtape3 = null }) {
  const out = { mesures: {} };
  await page.waitForSelector('[data-testid="wf-etape-1"]', { timeout: 30000 });
  await page.waitForTimeout(500);
  if (controles) {
    const e1 = await page.evaluate(() => {
      const cta = document.querySelector('[data-testid="wf-continuer"]').getBoundingClientRect();
      const t = document.body.innerText;
      return { ctaBas: Math.round(cta.bottom), ctaHaut: Math.round(cta.top), ctaH: Math.round(cta.height), ih: innerHeight, sy: scrollY, qui: (document.querySelector('[data-testid="invitation-de"]') || {}).textContent || '',
               seance: !!document.querySelector('[data-testid="invitation-seance"]'), emails: document.querySelectorAll('[data-testid="invitation-email"], input[type=email]').length,
               ancien: t.includes("M'inscrire et débloquer le duo"), invite: /invite (à ton tour )?un ami/i.test(t) && /débloquer ton essai/i.test(t), lead: (document.querySelector('.cp-wf-lead') || {}).textContent || '' };
    });
    out.e1 = e1;
    v(`${tag} 2. étape 1 : [Continuer] ENTIÈREMENT dans la fenêtre au chargement (haut ${e1.ctaHaut} ≥ 0, bas ${e1.ctaBas} ≤ ${e1.ih})`, e1.ctaHaut >= 0 && e1.ctaBas <= e1.ih && e1.sy === 0 && e1.ctaH >= 44, JSON.stringify({ haut: e1.ctaHaut, bas: e1.ctaBas, h: e1.ctaH, ih: e1.ih }));
    v(`${tag} 2. étape 1 : qui m'invite + séance + texte « invite un ami pour débloquer ton essai »`, /t'invite/.test(e1.qui) && e1.seance && e1.invite, `${e1.qui} | ${e1.lead}`);
    v(`${tag} 2. étape 1 : AUCUN champ e-mail, pas de « M'inscrire et débloquer le duo »`, e1.emails === 0 && !e1.ancien, JSON.stringify({ emails: e1.emails, ancien: e1.ancien }));
  }
  out.mesures.e1 = await mesurer(page, `${tag}-e1`);
  const tClic = Date.now();
  await page.click('[data-testid="wf-continuer"]');
  await page.waitForSelector('[data-testid="wf-etape-2"]', { timeout: 10000 });
  await page.waitForFunction(() => {
    const i = document.querySelector('[data-testid="wf-carte"] img'); const b = document.querySelector('[data-testid="wf-copier"]');
    return i && i.complete && i.naturalWidth > 0 && b && !b.disabled && !document.querySelector('[data-testid="wf-preparation"]');
  }, null, { timeout: 30000 });
  const e2 = await page.evaluate(() => {
    const i = document.querySelector('[data-testid="wf-carte"] img');
    const b = [...document.querySelectorAll('[data-testid^="wf-"]')].filter((x) => x.tagName === 'BUTTON');
    return { nw: i.naturalWidth, nh: i.naturalHeight, prep: window.__vuPrep, emails: document.querySelectorAll('[data-testid="invitation-email"], input[type=email]').length,
             boutons: b.map((x) => `${x.getAttribute('data-testid')}${x.disabled ? '(off)' : ''}`), simplifie: !!document.querySelector('[data-testid="wf-apercu-simplifie"]'),
             carteBtn: !!document.querySelector('[data-testid="wf-partager-carte"]'), partagerBtn: !!document.querySelector('[data-testid="wf-partager"]') };
  });
  out.e2 = e2;
  const chainPost = jrn.find((x) => x.m === 'POST' && /\/chain$/.test(x.u) && x.t >= tClic);
  if (controles) {
    v(`${tag} 3. étape 2 : « Préparation de ton invitation… » affiché avant la carte`, e2.prep === true);
    v(`${tag} 3. étape 2 : carte 1200×630 chargée, boutons actifs, aucun champ e-mail`, e2.nw === 1200 && e2.nh === 630 && e2.emails === 0 && !e2.boutons.some((b) => /wf-(whatsapp|copier)\(off\)/.test(b)), JSON.stringify(e2));
    v(`${tag} 3. POST /chain parti à l'entrée de l'étape 2, AVANT tout partage`, !!chainPost && !jrn.some((x) => /\/chain\/share$/.test(x.u) && x.t <= chainPost.t), chainPost ? `${chainPost.status}` : 'absent');
  }
  out.mesures.e2 = await mesurer(page, `${tag}-e2`);
  // Le share_url COURANT = celui de la dernière réponse /chain (ou /chain/share) reçue
  await page.waitForTimeout(200);
  const derniere = [...jrn].reverse().find((x) => x.corps && x.corps.child);
  out.shareAvant = derniere && derniere.corps.child.share_url;
  out.tokenEnfant = derniere && derniere.corps.child.share_token;
  const nShare = jrn.filter((x) => /\/chain\/share$/.test(x.u)).length;
  if (action === 'whatsapp') {
    await page.click('[data-testid="wf-whatsapp"]');
    await page.waitForFunction(() => window.__opens.length > 0, null, { timeout: 5000 });
    out.wa = (await page.evaluate(() => window.__opens))[0];
    out.partagee = out.shareAvant;
    if (controles) v(`${tag} 3. WhatsApp : wa.me contient la share_url courante`, /^https:\/\/wa\.me\/\?text=/.test(out.wa) && decodeURIComponent(out.wa.split('text=')[1]).includes(out.shareAvant), out.wa.slice(0, 160));
  } else if (action === 'copy') {
    await page.click('[data-testid="wf-copier"]');
    await page.waitForTimeout(400);
    out.partagee = await page.evaluate(() => navigator.clipboard.readText().catch(() => ''));
    if (controles) v(`${tag} 3. Copier le lien : presse-papiers = share_url courante`, out.partagee === out.shareAvant, `${out.partagee} vs ${out.shareAvant}`);
  } else if (action === 'share_image') {
    await page.click('[data-testid="wf-partager-carte"]');
    await page.waitForFunction(() => window.__partages.length > 0, null, { timeout: 5000 });
    out.natif = (await page.evaluate(() => window.__partages))[0];
    out.partagee = out.shareAvant;
  }
  await page.waitForSelector('[data-testid="wf-etape-3"]', { timeout: 15000 });
  const sh = jrn.filter((x) => /\/chain\/share$/.test(x.u));
  out.shareApres = sh.length > nShare && sh[sh.length - 1].corps ? sh[sh.length - 1].corps.child.share_url : '';
  if (controles) v(`${tag} 3. POST /chain/share après l'action → étape 3`, sh.length === nShare + 1 && sh[sh.length - 1].status === 200, String(sh.length - nShare));
  await page.waitForTimeout(300);
  const e3 = await page.evaluate(() => ({ t: document.querySelector('[data-testid="wf-etape-3"]').innerText,
    champs: ['invitation-prenom', 'invitation-email', 'invitation-whatsapp', 'invitation-consent', 'invitation-marketing'].every((id) => document.querySelector(`[data-testid="${id}"]`)),
    cta: (document.querySelector('[data-testid="invitation-rejoindre"]') || {}).textContent || '' }));
  if (controles) v(`${tag} 4. étape 3 : « Invitation prête » + prénom/e-mail/WhatsApp/consentements + « M'inscrire à mon essai gratuit »`, /Invitation prête/.test(e3.t) && e3.champs && /M'inscrire à mon essai gratuit/.test(e3.cta), e3.cta);
  out.mesures.e3 = await mesurer(page, `${tag}-e3`);
  if (surEtape3) await surEtape3(out);
  if (!inscrire) return out;
  await page.fill('[data-testid="invitation-prenom"]', nom);
  await page.fill('[data-testid="invitation-email"]', email);
  await page.fill('[data-testid="invitation-whatsapp"]', tel());
  await page.check('[data-testid="invitation-consent"]');
  await page.click('[data-testid="invitation-rejoindre"]');
  await page.waitForSelector('[data-testid="invitation-succes"], [data-testid="invitation-succes-attente"], [data-testid="invitation-erreur"], [data-testid="wf-avis"]', { timeout: 30000 });
  out.succes = await page.evaluate(() => (document.querySelector('[data-testid="invitation-succes"]') && 'succes') || (document.querySelector('[data-testid="invitation-succes-attente"]') && 'attente')
    || ((document.querySelector('[data-testid="invitation-erreur"], [data-testid="wf-avis"]') || {}).textContent || 'inconnu'));
  if (controles) v(`${tag} 4. inscription → écran de succès`, out.succes === 'succes' || out.succes === 'attente', out.succes);
  out.mesures.succes = await mesurer(page, `${tag}-e4-succes`);
  return out;
}

async function pageApercu(url, ua) {
  const r = execSync(`curl -s -A "${ua}" -w "\\n__%{http_code}" "${url}"`, { encoding: 'utf8' });
  const [html, code] = r.split('\n__');
  const og = (p) => { const m = html.match(new RegExp(`<meta property="${p}" content="([^"]*)"`)); return m ? m[1].replace(/&amp;/g, '&') : ''; };
  return { code: +code, ogImage: og('og:image'), ogUrl: og('og:url'), refresh: /http-equiv="refresh"/.test(html) };
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const reqCtx = await browser.newContext();
  const req = reqCtx.request;
  const MESURES = {};
  try {
    // ═══ 1. parrain + P0 ═══
    const flag = execSync(`RACINE=${RACINE} python3 - <<'EOF'\nimport os\nfrom pymongo import MongoClient\nenv={}\nfor l in open(os.path.join(os.environ['RACINE'],'.env.local')):\n    l=l.strip()\n    if '=' in l and not l.startswith('#'):\n        k,v=l.split('=',1); env[k]=v.strip().strip('"').strip("'")\ndb=MongoClient(env['MONGO_URL'])['afroboost_pw_test']\nassert db.name=='afroboost_pw_test'\nprint(repr((db.feature_flags.find_one({'id':'feature_flags'}) or {}).get('parrainage_chaine_enabled','ABSENT')))\nEOF`, { encoding: 'utf8' }).trim();
    v('0. base de TEST : parrainage_chaine_enabled absent ou vrai (règle ACTIVE)', flag === "'ABSENT'" || flag === 'True', flag);
    const code = fixture(`parrain ${PARRAIN} 8`);
    const codeT = fixture(`parrain ${PARRAIN_T} 8`);
    v('1. fixtures parrains (8 séances) dans la base de TEST', /^AFR-PD/.test(code) && /^AFR-PD/.test(codeT), `${code} ${codeT}`);
    const P0 = await creerPass(req, code, PARRAIN, 0, 0);
    v('1. Pass Duo créé par l\'API (jeton abonné signé local) → T0', P0.status === 201 && !!P0.token, `${P0.status} ${JSON.stringify(P0.dto).slice(0, 200)}`);
    const pub0 = await api(req, 'GET', `/api/referral/pass/${P0.token}`);
    v('1. GET public T0 : chain_required=true, chain={exists:false,shared:false}', pub0.json.chain_required === true && pub0.json.chain && pub0.json.chain.exists === false && pub0.json.chain.shared === false, JSON.stringify({ r: pub0.json.chain_required, c: pub0.json.chain }));

    // ═══ 2-4 + 7 + 8 : A (390×844) ═══
    const t390 = TAILLES[1];
    const ctxA = await contexte(browser, t390, 'lien');
    const pA = await ctxA.newPage(); const jA = journal(pA);
    await pA.goto(`${BASE}/duo/${P0.token}`, { waitUntil: 'domcontentloaded' });
    let A2;
    const A = await filleul(pA, jA, 'A', { action: 'whatsapp', nom: 'Awa', email: mail('a'), inscrire: false });
    // 8. retour avant inscription
    await pA.reload({ waitUntil: 'domcontentloaded' });
    await pA.waitForSelector('[data-testid="wf-etape-1"], [data-testid="wf-etape-3"], [data-testid="wf-etape-2"]', { timeout: 30000 });
    const retour = await pA.evaluate(() => (document.querySelector('[data-testid="wf-etape-3"]') && 3) || (document.querySelector('[data-testid="wf-etape-2"]') && 2) || 1);
    v('8. A recharge /duo/T0 après partage, avant inscription → directement l\'étape 3', retour === 3, `étape ${retour}`);
    await pA.screenshot({ path: path.join(CAP, 'A-8-retour-etape3.png') });
    // 7. « Partager encore » : 2e partage de la même invitation
    await pA.click('[data-testid="wf-partager-encore"]');
    A2 = await filleul2(pA, jA);
    async function filleul2(page, jrn) {
      await page.waitForSelector('[data-testid="wf-etape-2"]', { timeout: 10000 });
      await page.waitForFunction(() => { const b = document.querySelector('[data-testid="wf-copier"]'); const i = document.querySelector('[data-testid="wf-carte"] img'); return b && !b.disabled && i && i.complete && i.naturalWidth > 0; }, null, { timeout: 30000 });
      const n = jrn.filter((x) => /\/chain\/share$/.test(x.u)).length;
      await page.click('[data-testid="wf-copier"]');
      await page.waitForSelector('[data-testid="wf-etape-3"]', { timeout: 15000 });
      await page.waitForTimeout(300);
      const s = jrn.filter((x) => /\/chain\/share$/.test(x.u));
      return { copie: await page.evaluate(() => navigator.clipboard.readText().catch(() => '')), n2: s.length - n, apres: s[s.length - 1].corps && s[s.length - 1].corps.child };
    }
    const u1 = A.partagee, u2 = A2.copie;
    const vv = (u) => +((u || '').match(/[?&]v=(\d+)/) || [0, 0])[1];
    const tk = (u) => ((u || '').match(/\/share\/duo\/([^/?]+)/) || [0, ''])[1];
    v('7. deux partages : même jeton T1, share_url différente, v croissant', !!u1 && !!u2 && tk(u1) === tk(u2) && tk(u1) === A.tokenEnfant && u1 !== u2 && vv(u2) > vv(u1), `${u1} → ${u2}`);
    for (const [i, u] of [[1, u1], [2, u2]]) {
      const pg = await pageApercu(u, 'Mozilla/5.0 Chrome/124');
      v(`7. partage ${i} : page 200, og:image absolue, og:url = l'URL exacte, meta refresh pour un navigateur`, pg.code === 200 && /^https?:\/\//.test(pg.ogImage) && pg.ogUrl === u && pg.refresh, JSON.stringify(pg));
      const img = execSync(`curl -s -o /dev/null -w "%{http_code} %{content_type} %{size_download}" "${pg.ogImage}"`, { encoding: 'utf8' });
      v(`7. partage ${i} : og:image → 200 image/jpeg`, /^200 image\/jpeg \d{4,}/.test(img), img);
      const rb = await pageApercu(u, 'WhatsApp/2.24');
      v(`7. partage ${i} : robot « WhatsApp/2.24 » → 200, AUCUN meta refresh, og:url exacte`, rb.code === 200 && !rb.refresh && rb.ogUrl === u, JSON.stringify(rb));
      if (!/^https:/.test(pg.ogImage)) R.push(`INFO 7. og:image en http:// en LOCAL (FRONTEND_URL=${BASE}) : le contrôle serveur og_image_https est donc faux ici → « Aperçu simplifié » attendu en local`);
    }
    // 4. A s'inscrit
    await pA.fill('[data-testid="invitation-prenom"]', 'Awa');
    await pA.fill('[data-testid="invitation-email"]', mail('a'));
    await pA.fill('[data-testid="invitation-whatsapp"]', tel());
    await pA.check('[data-testid="invitation-consent"]');
    await pA.click('[data-testid="invitation-rejoindre"]');
    await pA.waitForSelector('[data-testid="invitation-succes"], [data-testid="invitation-succes-attente"], [data-testid="invitation-erreur"], [data-testid="wf-avis"]', { timeout: 30000 });
    const succesA = await pA.evaluate(() => (document.querySelector('[data-testid="invitation-succes"]') && 'succes') || (document.querySelector('[data-testid="invitation-succes-attente"]') && 'attente') || ((document.querySelector('[data-testid="invitation-erreur"], [data-testid="wf-avis"]') || {}).textContent || '?'));
    v('4. A s\'inscrit (faux Resend) → écran de succès', succesA === 'succes' || succesA === 'attente', succesA);
    await pA.screenshot({ path: path.join(CAP, 'A-4-succes.png'), fullPage: true });

    // ═══ 6. B ouvre la share_url de A ═══
    const ctxB = await contexte(browser, t390, 'lien');
    const pB = await ctxB.newPage(); const jB = journal(pB);
    await pB.goto(u2, { waitUntil: 'domcontentloaded' });
    await pB.waitForURL((u) => /^\/duo\/[^/]+$/.test(new URL(u).pathname), { timeout: 15000 });
    v('6. B ouvre la share_url de A → redirection navigateur vers /duo/T1', pB.url() === `${BASE}/duo/${A.tokenEnfant}`, pB.url());
    const B = await filleul(pB, jB, 'B', { action: 'copy', nom: 'Bintou', email: mail('b') });
    let items = await adminPasses(req);
    const aP0 = parJeton(items, P0.token), aP1 = parJeton(items, A.tokenEnfant), aP2 = parJeton(items, B.tokenEnfant);
    v('6. admin : P1.chain.parent_pass_id = P0, profondeur 1, parrain A relié (plus en attente)', aP1 && aP1.chain && aP1.chain.parent_pass_id === P0.id && aP1.chain.depth === 1 && aP1.chain.sponsor_pending === false && aP1.sponsor.email === mail('a'), JSON.stringify(aP1 && { c: aP1.chain, s: aP1.sponsor }));
    v('6. admin : P0 débloqué (A inscrit)', aP0 && aP0.status === 'unlocked', aP0 && aP0.status);
    v('6. admin : P1 débloqué quand B s\'inscrit', aP1 && aP1.status === 'unlocked' && aP1.invitee && aP1.invitee.email === mail('b'), aP1 && aP1.status);
    v('6. admin : P2.chain.parent_pass_id = P1, profondeur 2, root = P0', aP2 && aP2.chain && aP2.chain.parent_pass_id === (aP1 && aP1.id) && aP2.chain.depth === 2 && aP2.chain.root_pass_id === P0.id, JSON.stringify(aP2 && aP2.chain));

    // ═══ 6 + 10. C (partage natif AVEC la carte) ═══
    const ctxC = await contexte(browser, t390, 'carte');
    const pC = await ctxC.newPage(); const jC = journal(pC);
    await pC.goto(B.partagee, { waitUntil: 'domcontentloaded' });
    await pC.waitForURL((u) => /^\/duo\/[^/]+$/.test(new URL(u).pathname), { timeout: 15000 });
    v('6. C ouvre la share_url de B → /duo/T2', pC.url() === `${BASE}/duo/${B.tokenEnfant}`, pC.url());
    const C = await filleul(pC, jC, 'C', { action: 'share_image', nom: 'Chloé', email: mail('c') });
    v('10. canShare({files}) vrai → [Partager avec la carte] présent', C.e2.carteBtn === true, JSON.stringify(C.e2.boutons));
    const f = (C.natif && C.natif.files) || [];
    v('10. navigator.share reçoit un File image/jpeg + un texte contenant la share_url', f.length === 1 && f[0].type === 'image/jpeg' && f[0].size > 1000 && (C.natif.text || '').includes(C.shareAvant), JSON.stringify(C.natif).slice(0, 300));
    // ═══ D ouvre, voit l'étape 1, ne s'inscrit pas ═══
    const ctxD = await contexte(browser, t390, 'lien');
    const pD = await ctxD.newPage(); const jD = journal(pD);
    await pD.goto(C.partagee, { waitUntil: 'domcontentloaded' });
    await pD.waitForURL((u) => /^\/duo\/[^/]+$/.test(new URL(u).pathname), { timeout: 15000 });
    await pD.waitForSelector('[data-testid="wf-etape-1"]', { timeout: 30000 });
    const quiD = await pD.textContent('[data-testid="invitation-de"]');
    v('6. D ouvre la share_url de C → /duo/T3, étape 1 (« … t\'invite »)', pD.url() === `${BASE}/duo/${C.tokenEnfant}` && /t'invite/.test(quiD), `${pD.url()} | ${quiD}`);
    await pD.screenshot({ path: path.join(CAP, 'D-6-etape1.png') });
    await pD.click('[data-testid="wf-continuer"]');
    await pD.waitForFunction(() => { const b = document.querySelector('[data-testid="wf-copier"]'); return b && !b.disabled; }, null, { timeout: 30000 });
    const dBtn = await pD.evaluate(() => ({ carte: !!document.querySelector('[data-testid="wf-partager-carte"]'), partager: !!document.querySelector('[data-testid="wf-partager"]') }));
    v('10. share sans canShare → [Partager avec la carte] ABSENT, [Partager] présent', !dBtn.carte && dBtn.partager, JSON.stringify(dBtn));
    items = await adminPasses(req);
    const aP2b = parJeton(items, B.tokenEnfant), aP3 = parJeton(items, C.tokenEnfant);
    v('6. admin : P2 débloqué (C inscrit), P3.parent = P2 (profondeur 3), P3 en attente (D non inscrit)', aP2b && aP2b.status === 'unlocked' && aP3 && aP3.chain && aP3.chain.parent_pass_id === aP2b.id && aP3.chain.depth === 3 && aP3.status !== 'unlocked' && !aP3.invitee, JSON.stringify({ p2: aP2b && aP2b.status, p3: aP3 && { s: aP3.status, c: aP3.chain } }));

    // ═══ 5. contournement par l'API ═══
    const PX = await creerPass(req, code, PARRAIN, 0, 1);
    const corpsJoin = (n, e) => ({ name: n, email: e, whatsapp: tel(), consent_reservation: true, terms_accepted: true, marketing_consent: false });
    const j1 = await api(req, 'POST', `/api/referral/pass/${PX.token}/join`, corpsJoin('Xavier', mail('x')));
    v('5. POST /join direct AVANT partage → 409 invitation_requise', j1.status === 409 && j1.headers['x-refus-raison'] === 'invitation_requise', `${j1.status} ${j1.headers['x-refus-raison']}`);
    const ch = await api(req, 'POST', `/api/referral/pass/${PX.token}/chain`, {});
    const cle = ch.json && ch.json.edit_key;
    v('5. POST /chain → 201 + edit_key', ch.status === 201 && !!cle, String(ch.status));
    const sh0 = await api(req, 'POST', `/api/referral/pass/${PX.token}/chain/share`, { channel: 'copy' });
    v('5. POST /chain/share SANS X-Chain-Key → 403 (refusé)', sh0.status === 403, `${sh0.status} ${sh0.headers['x-refus-raison'] || ''}`);
    const sh1 = await api(req, 'POST', `/api/referral/pass/${PX.token}/chain/share`, { channel: 'copy' }, { 'X-Chain-Key': cle });
    v('5. POST /chain/share AVEC la clé → 200 shared', sh1.status === 200 && sh1.json.shared === true, String(sh1.status));
    const j2 = await api(req, 'POST', `/api/referral/pass/${PX.token}/join`, corpsJoin('Xavier', mail('x')));
    v('5. join après partage mais SANS la clé de l\'appareil → 403 invitation_autre_appareil', j2.status === 403 && j2.headers['x-refus-raison'] === 'invitation_autre_appareil', `${j2.status} ${j2.headers['x-refus-raison']}`);
    const j3 = await api(req, 'POST', `/api/referral/pass/${PX.token}/join`, corpsJoin('Xavier', mail('x')), { 'X-Chain-Key': cle });
    v('5. join AVEC la clé → 200/201', j3.status === 200 || j3.status === 201, `${j3.status} ${JSON.stringify(j3.json).slice(0, 160)}`);

    // ═══ 9. six tailles ═══
    const slots = [[0, 2], [0, 3], [1, 0], [1, 1], [1, 2], [0, 4]];
    for (let i = 0; i < TAILLES.length; i++) {
      const t = TAILLES[i]; const tag = `${t.w}x${t.h}`;
      try {
        const P = await creerPass(req, codeT, PARRAIN_T, slots[i][0], slots[i][1]);
        if (P.status !== 201) { v(`9. ${tag} : pass créé`, false, `${P.status} ${JSON.stringify(P.dto).slice(0, 200)}`); continue; }
        const ctx = await contexte(browser, t, t.mobile ? 'lien' : 'aucun');
        const pg = await ctx.newPage(); const jr = journal(pg);
        await pg.goto(`${BASE}/duo/${P.token}`, { waitUntil: 'domcontentloaded' });
        const r = await filleul(pg, jr, tag, { action: t.mobile ? 'whatsapp' : 'copy', nom: 'Test' + i, email: mail('t' + i) });
        MESURES[tag] = r.mesures;
        await ctx.close();
      } catch (e) { v(`9. ${tag} : ERREUR d'exécution`, false, String(e).split('\n')[0]); }
    }
    for (const [tag, m] of Object.entries(MESURES)) {
      const mobile = +tag.split('x')[0] < 500;
      const etapes = Object.entries(m);
      v(`9. ${tag} : aucun défilement horizontal (scrollWidth ≤ innerWidth) à chaque étape`, etapes.every(([, x]) => !x.hscroll), etapes.map(([k, x]) => `${k}:${x.sw}/${x.iw}`).join(' '));
      const petits = etapes.flatMap(([k, x]) => x.petits.map((p) => `${k}:${p.id}=${p.h}`));
      v(`9. ${tag} : cibles cliquables ≥ 44 px`, petits.length === 0, petits.join(', '));
      R.push(`INFO 9. ${tag} hauteur (écrans) : ${etapes.map(([k, x]) => `${k}=${x.ecrans}`).join(' ')}${mobile && etapes.some(([, x]) => x.ecrans > 2.5) ? '  ⚠ > 2,5 écrans' : ''}`);
    }
  } catch (e) {
    v('ERREUR d\'exécution', false, String(e.stack || e).split('\n').slice(0, 3).join(' | '));
  } finally {
    await browser.close();
    fs.writeFileSync(path.join(SCRATCH, 'v3_nettoyage.json'), JSON.stringify({ prefixe: PREFIXE, passes: PASS_IDS, tels: TELS }));
    console.log(R.join('\n'));
    console.log(`\n${OK} OK / ${KO} RATE — captures : ${CAP} — préfixe de nettoyage : ${PREFIXE}`);
    console.log('MESURES ' + JSON.stringify(MESURES));
  }
})();
