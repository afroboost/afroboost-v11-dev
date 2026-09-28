/**
 * PARCOURS HERO — V554 : éditeur visuel du Hero, compte à rebours, disposition,
 * PARITÉ aperçu ↔ page d'accueil, persistance.
 *
 * CE QUE CE BANC VERROUILLE.
 *   A. Accueil SANS heroLayout (concept réel), 7 tailles : titre + CTA (et le
 *      sous-titre en desktop) visibles et entièrement DANS `.af-hero`, rien dans
 *      la zone réservée haute (header du carrousel : logo « Afroboost » et globe),
 *      rien dans la zone basse (bloc coach), aucun défilement horizontal.
 *   B. Compte à rebours (offre FACTICE injectée dans /api/offers) × Vue visiteur
 *      (`/?visitor=true` : c'est ce paramètre qui active `isVisitorMode`, App.js),
 *      7 tailles : barre `[data-sticky-countdown=active]` dans l'écran, AUCUNE
 *      intersection barre / Retour / globe / logo / CTA, globe et Retour
 *      réellement cliquables (elementFromPoint), minuteur ≥ 14 px.
 *   C. Hero POSITIONNÉ (heroLayout de test injecté dans /api/concept, desktop et
 *      mobile différents, CTA desktop collé dans un coin à size 1.8) : chaque
 *      élément reste dans HERO_ZONES_SURES, et chaque appareil applique SA
 *      disposition (centre mesuré ≈ x·L, y·H à ±2 px, après bornage recalculé).
 *   D. PARITÉ : les positions normalisées (centre/L, centre/H, largeur/L) de
 *      title / subtitle / cta mesurées dans `[data-hero-boite]` de l'aperçu de
 *      l'éditeur (Desktop puis Mobile) = celles de la page d'accueil à 1440×900
 *      et 390×844, à 0,5 % près.
 *   E. PERSISTANCE simulée : glisser titre + CTA, taille +, UN SEUL PUT
 *      /api/concept (debounce), rechargement avec ce corps comme concept →
 *      mêmes positions dans l'éditeur → même rendu sur l'accueil.
 *   D et E passent en « SKIP : éditeur absent » tant que `[data-testid=hero-editeur]`
 *   n'existe pas dans le build testé.
 *
 * MESURES. Toujours la géométrie RENDUE (getBoundingClientRect, display calculé,
 * elementFromPoint), jamais un simple comptage DOM (leçon V540).
 *
 * COMMENT LE DASHBOARD COACH EST OUVERT EN LOCAL (D, E).
 *   `App.js` restaure la session coach depuis le localStorage :
 *   `afroboost_coach_mode = 'true'` + `afroboost_coach_user = {email,…}` →
 *   `coachMode` vrai → `CoachDashboard` est rendu à la place de la vitrine.
 *   `afroboost_coach_tab = 'offers'` ouvre l'onglet « Gestion » ; le banc clique
 *   ensuite la carte « Vidéo Hero » puis, à défaut, « Ma Vitrine » (les deux
 *   montent `ConceptEditor`, qui porte les textes du Hero réservés au
 *   super-admin — l'e-mail posé est donc celui du super-admin).
 *   Trois verrous à franchir, sans aucune vraie identité :
 *   - `afroboost_jwt` = JWT FACTICE non signé (exp +1 h) : sans jeton,
 *     SECURITY-S1 (App.js, authValide) ouvre la « Connexion Partenaire » ;
 *   - `GET /api/auth/role` répondu localement (super_admin) : sinon la prod,
 *     interrogée en anonyme, répond « user » → terminerSession('role-invalide') ;
 *   - `GET /api/reservations` répondu localement ({data:[], pagination}) : la
 *     réponse anonyme de la prod ne suffit pas au dashboard.
 *   Les en-têtes d'identité (Authorization, X-User-Email, Cookie) sont RETIRÉS
 *   de toute requête relayée, et `X-Auth-Reason` retiré des réponses (sinon
 *   l'intercepteur axios purge la session du banc). La prod répond donc en
 *   anonyme ; `/api/concept` est servi par le banc. Toute écriture (POST/PUT/PATCH/DELETE) est BLOQUÉE et
 *   répondue localement ; le PUT /api/concept est capturé pour E.
 *
 * LANCEMENT (deux modes).
 *   1) Build statique local, GET /api relayés vers la prod, écritures bloquées :
 *      cd frontend && BUILD_PATH=<scratchpad>/build-tests CI=false npx craco build
 *      BUILD_DIR=<scratchpad>/build-tests RELAIS_API=https://afroboost.com \
 *      CAPTURES=<scratchpad>/tests-hero \
 *      NODE_PATH=$HOME/.claude/skills/gstack/node_modules \
 *      node tests/parcours/parcours_hero_editeur.cjs
 *      (BUILD_DIR : le banc sert lui-même le build, SPA incluse, sur un port libre.)
 *   2) Pile locale (tests/parcours/README.md) :
 *      BASE=http://127.0.0.1:8001 CAPTURES=<dossier hors dépôt> node …/parcours_hero_editeur.cjs
 *      (GET /api vers la pile ; écritures bloquées quand même.)
 *   PARCOURS=A,B,C,D,E pour n'en lancer qu'une partie.
 *   Les captures ne sont JAMAIS écrites dans le dépôt (défaut : dossier temporaire).
 */
const { chromium } = require('playwright');
const fs = require('fs');
const os = require('os');
const path = require('path');
const http = require('http');

const RELAIS = (process.env.RELAIS_API || '').replace(/\/$/, '');
const BUILD_DIR = process.env.BUILD_DIR || '';
let BASE = process.env.BASE || 'http://127.0.0.1:8001';
const CAP = process.env.CAPTURES || path.join(os.tmpdir(), 'afroboost-tests-hero');
fs.mkdirSync(CAP, { recursive: true });

// Doivent rester égales à frontend/src/utils/heroLayout.js (contrat V554).
const ZONES = { desktop: { haut: 44, bas: 56, cote: 12 }, mobile: { haut: 44, bas: 104, cote: 12 } };
const SEUIL_MOBILE = 1024;
const TAILLES = [
  { n: '1280x800', w: 1280, h: 800 }, { n: '1440x900', w: 1440, h: 900 },
  { n: '768x1024', w: 768, h: 1024 }, { n: '360x640', w: 360, h: 640 },
  { n: '390x844', w: 390, h: 844 }, { n: '414x896', w: 414, h: 896 },
  { n: '430x932', w: 430, h: 932 },
];
const SUPER_ADMIN = 'contact.artboost@gmail.com';

// Disposition de test : desktop et mobile DIFFÉRENTS, CTA desktop collé dans le
// coin bas-droit à la taille maximale (le bornage doit le ramener dans la zone).
const LAYOUT_TEST = {
  v: 1,
  desktop: {
    title: { x: 0.3, y: 0.35, size: 1.2, align: 'left' },
    subtitle: { x: 0.68, y: 0.55, size: 0.8, align: 'right' },
    cta: { x: 1, y: 1, size: 1.8 },
  },
  mobile: {
    title: { x: 0.5, y: 0.3, size: 0.9, align: 'center' },
    subtitle: null,
    cta: { x: 0.5, y: 0.62, size: 1.2 },
  },
};

// ─── Comptes ────────────────────────────────────────────────────────────────
const R = []; let OK = 0, KO = 0, SK = 0;
const v = (nom, cond, mesure = '') => {
  if (cond) OK++; else KO++;
  R.push(`${cond ? 'OK    ' : 'ÉCHEC '} ${nom}${mesure ? '  [' + String(mesure).slice(0, 320) + ']' : ''}`);
};
const skip = (nom, raison) => { SK++; R.push(`SKIP   ${nom}  [${raison}]`); };
const info = (nom, mesure) => { R.push(`INFO   ${nom}  [${mesure}]`); }; // constat non compté
const actif = (p) => !process.env.PARCOURS || process.env.PARCOURS.split(',').includes(p);
async function parcours(nom, fn) {
  if (!actif(nom)) return;
  try { await fn(); } catch (e) { v(`${nom}. ERREUR d'exécution`, false, String(e).split('\n')[0]); }
}

// ─── Serveur statique (BUILD_DIR) ───────────────────────────────────────────
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'application/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.webp': 'image/webp', '.woff2': 'font/woff2', '.txt': 'text/plain', '.map': 'application/json', '.md': 'text/plain' };
function servirBuild(dir) {
  return new Promise((ok) => {
    const srv = http.createServer((req, res) => {
      const url = decodeURIComponent((req.url || '/').split('?')[0]);
      let f = path.join(dir, url);
      if (!f.startsWith(dir)) { res.writeHead(403); return res.end(); }
      if (!fs.existsSync(f) || fs.statSync(f).isDirectory()) f = path.join(dir, 'index.html'); // SPA
      res.writeHead(200, { 'content-type': TYPES[path.extname(f)] || 'application/octet-stream', 'cache-control': 'no-store' });
      fs.createReadStream(f).pipe(res);
    });
    srv.listen(0, '127.0.0.1', () => ok(srv));
  });
}

// ─── Réseau : relais GET, écritures bloquées, surcharges concept / offres ───
/**
 * opts.concept(conceptReel) -> concept servi ; opts.offres(listeReelle) -> liste servie.
 * Retourne { puts: [] } : les corps des PUT /api/concept capturés.
 */
async function reseau(ctx, opts = {}) {
  const etat = { puts: [], ecritures: [] };
  // Pas de mesure d'audience depuis un banc.
  await ctx.route(/posthog|google-analytics|googletagmanager|facebook\.net/i, (r) => r.abort());
  await ctx.route((u) => new URL(u).pathname.startsWith('/api/'), async (route) => {
    const req = route.request();
    const u = new URL(req.url());
    const methode = req.method();
    if (methode !== 'GET' && methode !== 'HEAD') {
      let corps = null;
      try { corps = req.postDataJSON(); } catch (e) { corps = req.postData(); }
      if (methode === 'PUT' && u.pathname === '/api/concept') {
        etat.puts.push({ t: Date.now(), corps });
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(corps || {}) });
      }
      etat.ecritures.push(`${methode} ${u.pathname}`);
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{"banc":"ecriture bloquee"}' });
    }
    // Identité TOUJOURS retirée (relais ou pile locale) : le jeton du banc est
    // factice, et aucune lecture ne doit partir au nom du super-admin.
    const relayer = async () => {
      const h = { ...req.headers() };
      delete h['authorization']; delete h['x-user-email']; delete h['cookie'];
      if (!RELAIS) return route.fetch({ headers: h });
      delete h['host']; delete h['origin']; delete h['referer'];
      return route.fetch({ url: RELAIS + u.pathname + u.search, headers: h });
    };
    if (opts.fixes && Object.prototype.hasOwnProperty.call(opts.fixes, u.pathname)) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(opts.fixes[u.pathname]) });
    }
    const estConcept = u.pathname === '/api/concept';
    const estOffres = u.pathname === '/api/offers';
    if ((estConcept && opts.concept) || (estOffres && opts.offres)) {
      let brut = null;
      try { const rep = await relayer(); brut = await rep.json(); } catch (e) { brut = estConcept ? {} : []; }
      const servi = estConcept ? opts.concept(brut) : (Array.isArray(brut) ? opts.offres(brut) : brut);
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(servi) });
    }
    try {
      const rep = await relayer();
      // Les routes privées répondent 401 + `X-Auth-Reason` à une requête
      // anonymisée : l'intercepteur axios d'App.js y voit une session morte et
      // purge la session coach du banc (écran « Votre session a expiré »). On
      // garde le statut (l'écran reçoit bien un refus) mais on retire la raison.
      const h = { ...rep.headers() };
      delete h['x-auth-reason'];
      return route.fulfill({ response: rep, headers: h });
    } catch (e) {
      return route.fulfill({ status: 502, body: 'relais indisponible' });
    }
  });
  return etat;
}

async function contexte(browser, t, extra = {}) {
  const mobile = t.w < SEUIL_MOBILE;
  return browser.newContext({
    viewport: { width: t.w, height: t.h },
    isMobile: mobile, hasTouch: mobile, deviceScaleFactor: mobile ? 2 : 1,
    serviceWorkers: 'block', // sinon le SW contourne l'interception réseau
    ...extra,
  });
}

// ─── Géométrie (exécutée dans la page) ──────────────────────────────────────
const mesurerAccueil = () => {
  const rect = (el) => {
    if (!el) return null;
    for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
      if (getComputedStyle(n).display === 'none') return null;
    }
    const r = el.getBoundingClientRect();
    if (!(r.width > 0 && r.height > 0)) return null;
    return { l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height };
  };
  const q = (s) => document.querySelector(s);
  const racine = q('.af-hero [data-hero-racine]');
  return {
    hero: rect(q('.af-hero')),
    racine: racine ? { appareil: racine.getAttribute('data-appareil'), mode: racine.getAttribute('data-mode') } : null,
    title: rect(q('.af-hero [data-hero-el="title"]')),
    subtitle: rect(q('.af-hero [data-hero-el="subtitle"]')),
    cta: rect(q('.af-hero [data-hero-el="cta"]')),
    logo: rect(q('[data-testid="afroboost-logo"]')),
    globe: rect(q('[data-testid="lang-selector-btn"]')),
    barre: rect(q('[data-sticky-countdown="active"]')),
    retour: rect(q('[data-testid="af-barre-haute-retour"]')),
    compte: rect(q('[data-testid="af-barre-haute-compte"]')),
    texteBarre: (q('[data-sticky-countdown="active"]') || {}).innerText || '',
    policeMinuteur: (() => { const m = q('.af-barre-haute-minuteur'); return m ? parseFloat(getComputedStyle(m).fontSize) : 0; })(),
    scrollW: document.documentElement.scrollWidth,
    innerW: window.innerWidth,
    innerH: window.innerHeight,
  };
};

const f1 = (x) => (x == null ? 'null' : Math.round(x * 10) / 10);
const txtR = (r) => (r ? `${f1(r.l)},${f1(r.t)} → ${f1(r.r)},${f1(r.b)}` : 'absent');
const intersecte = (a, b) => !!(a && b) && a.l < b.r - 0.5 && b.l < a.r - 0.5 && a.t < b.b - 0.5 && b.t < a.b - 0.5;
const dedans = (e, c, tol = 0.5) => !!(e && c) && e.l >= c.l - tol && e.t >= c.t - tol && e.r <= c.r + tol && e.b <= c.b + tol;

// Réplique de heroLayout.borner (en px, relatif à la boîte) — la vérité attendue.
function bornerPx(cx, cy, w, h, L, H, appareil) {
  const z = ZONES[appareil];
  const axe = (c, t, d, f) => (t >= f - d ? d + (f - d) / 2 : Math.min(f - t / 2, Math.max(d + t / 2, c)));
  return { x: axe(cx, w, z.cote, L - z.cote), y: axe(cy, h, z.haut, H - z.bas) };
}

async function attendreHero(p, mode) {
  await p.waitForSelector('.af-hero [data-hero-racine]', { timeout: 60000 });
  if (mode) await p.waitForSelector(`.af-hero [data-hero-racine][data-mode="${mode}"]`, { timeout: 30000 });
  await p.evaluate(() => (document.fonts ? document.fonts.ready : null)).catch(() => {});
  await p.waitForTimeout(2500);
}

// ═════════════════════════════ A. ACCUEIL ═════════════════════════════
async function parcoursA(browser) {
  for (const t of TAILLES) {
    const ctx = await contexte(browser, t);
    // Concept RÉEL, mais sans disposition quoi qu'il arrive (la prod pourrait en avoir une un jour).
    await reseau(ctx, { concept: (c) => ({ ...(c || {}), heroLayout: null }) });
    const p = await ctx.newPage();
    await p.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 60000 });
    await attendreHero(p, 'flux');
    const m = await p.evaluate(mesurerAccueil);
    await p.screenshot({ path: path.join(CAP, `A_${t.n}.png`) });
    const app = t.w >= SEUIL_MOBILE ? 'desktop' : 'mobile';
    const z = ZONES[app];
    v(`A ${t.n}. mode flux, appareil ${app}`, m.racine && m.racine.mode === 'flux' && m.racine.appareil === app, JSON.stringify(m.racine));
    v(`A ${t.n}. titre visible et DANS .af-hero`, dedans(m.title, m.hero), `titre ${txtR(m.title)} | hero ${txtR(m.hero)}`);
    v(`A ${t.n}. CTA visible et DANS .af-hero`, dedans(m.cta, m.hero), `cta ${txtR(m.cta)} | hero ${txtR(m.hero)}`);
    if (app === 'desktop') v(`A ${t.n}. sous-titre visible et DANS .af-hero`, dedans(m.subtitle, m.hero), `sous-titre ${txtR(m.subtitle)}`);
    else v(`A ${t.n}. sous-titre masqué sur mobile`, m.subtitle === null, txtR(m.subtitle));
    v(`A ${t.n}. logo et globe du carrousel présents`, !!(m.logo && m.globe), `logo ${txtR(m.logo)} | globe ${txtR(m.globe)}`);
    const els = [['titre', m.title], ['sous-titre', m.subtitle], ['CTA', m.cta]].filter((e) => e[1]);
    const chevauche = [];
    els.forEach(([n, r]) => {
      if (intersecte(r, m.logo)) chevauche.push(`${n}×logo`);
      if (intersecte(r, m.globe)) chevauche.push(`${n}×globe`);
    });
    v(`A ${t.n}. aucun texte ne chevauche le logo ni le globe`, chevauche.length === 0, chevauche.join(', ') || `logo ${txtR(m.logo)} globe ${txtR(m.globe)}`);
    if (m.hero) {
      const hautMin = m.hero.t + z.haut;
      const basMax = m.hero.b - z.bas;
      const topMin = Math.min(...els.map((e) => e[1].t));
      const botMax = Math.max(...els.map((e) => e[1].b));
      v(`A ${t.n}. rien dans la zone réservée haute (${z.haut} px)`, topMin >= hautMin - 0.5, `haut du texte ${f1(topMin - m.hero.t)} px ≥ ${z.haut}`);
      v(`A ${t.n}. rien dans la zone réservée basse / bloc coach (${z.bas} px)`, botMax <= basMax + 0.5, `bas du texte ${f1(botMax - m.hero.t)} px ≤ ${f1(m.hero.h - z.bas)}`);
    }
    v(`A ${t.n}. aucun défilement horizontal`, m.scrollW <= m.innerW, `scrollWidth ${m.scrollW} / innerWidth ${m.innerW}`);
    await ctx.close();
  }
}

// ═════════════════════════ B. COMPTE À REBOURS ═════════════════════════
function offreFactice() {
  const d = new Date(Date.now() + 3 * 86400 * 1000);
  return {
    id: 'banc-hero-offre-countdown', name: 'Offre BANC compte à rebours', price: 0, visible: false,
    countdown_enabled: true, countdown_date: d.toISOString().slice(0, 10), countdown_time: '23:59',
    countdown_text: 'OFFRE FONDATEURS',
  };
}
async function parcoursB(browser) {
  for (const t of TAILLES) {
    const ctx = await contexte(browser, t);
    await reseau(ctx, {
      concept: (c) => ({ ...(c || {}), heroLayout: null }),
      offres: (liste) => [offreFactice(), ...liste.map((o) => ({ ...o, countdown_enabled: false }))],
    });
    const p = await ctx.newPage();
    await p.goto(BASE + '/?visitor=true', { waitUntil: 'domcontentloaded', timeout: 60000 });
    await attendreHero(p);
    await p.waitForSelector('[data-sticky-countdown="active"]', { timeout: 20000 }).catch(() => {});
    await p.waitForTimeout(800);
    const m = await p.evaluate(mesurerAccueil);
    await p.screenshot({ path: path.join(CAP, `B_${t.n}.png`) });
    const ecran = { l: 0, t: 0, r: m.innerW, b: m.innerH };
    v(`B ${t.n}. barre du compte à rebours affichée (OFFRE FONDATEURS)`, !!m.barre && /OFFRE FONDATEURS/.test(m.texteBarre), `barre ${txtR(m.barre)} « ${m.texteBarre.replace(/\s+/g, ' ').slice(0, 60)} »`);
    v(`B ${t.n}. barre entièrement dans l'écran`, dedans(m.barre, ecran), `barre ${txtR(m.barre)} écran ${m.innerW}×${m.innerH}`);
    v(`B ${t.n}. bouton Retour présent (Vue visiteur)`, !!m.retour, txtR(m.retour));
    const paires = [
      ['barre', 'globe'], ['barre', 'logo'], ['barre', 'cta'],
      ['retour', 'globe'], ['retour', 'logo'], ['retour', 'cta'], ['retour', 'compte'],
      ['globe', 'cta'], ['logo', 'cta'],
    ];
    const coll = paires.filter(([a, b]) => intersecte(m[a], m[b])).map(([a, b]) => `${a}×${b} (${txtR(m[a])} / ${txtR(m[b])})`);
    v(`B ${t.n}. zéro intersection barre / Retour / globe / logo / CTA`, coll.length === 0, coll.join(' ; ') || `barre ${txtR(m.barre)} globe ${txtR(m.globe)} logo ${txtR(m.logo)} cta ${txtR(m.cta)}`);
    const cliquable = async (sel) => p.evaluate((s) => {
      const el = document.querySelector(s);
      if (!el) return 'absent';
      const r = el.getBoundingClientRect();
      const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      if (!hit) return 'rien au point';
      return el === hit || el.contains(hit) ? 'oui' : `masqué par <${hit.tagName.toLowerCase()} class="${String(hit.className).slice(0, 60)}">`;
    }, sel);
    const cg = await cliquable('[data-testid="lang-selector-btn"]');
    v(`B ${t.n}. globe cliquable (elementFromPoint)`, cg === 'oui', cg);
    const cr = await cliquable('[data-testid="af-barre-haute-retour"]');
    v(`B ${t.n}. Retour cliquable (elementFromPoint)`, cr === 'oui', cr);
    v(`B ${t.n}. aucun défilement horizontal`, m.scrollW <= m.innerW, `scrollWidth ${m.scrollW} / innerWidth ${m.innerW}`);
    v(`B ${t.n}. chiffres du minuteur ≥ 14 px`, m.policeMinuteur >= 14, `${m.policeMinuteur} px`);
    await ctx.close();
  }
}

// ═════════════════════════ C. HERO POSITIONNÉ ═════════════════════════
async function parcoursC(browser) {
  for (const t of TAILLES) {
    const ctx = await contexte(browser, t);
    await reseau(ctx, { concept: (c) => ({ ...(c || {}), heroLayout: LAYOUT_TEST }) });
    const p = await ctx.newPage();
    await p.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 60000 });
    try { await attendreHero(p, 'positionne'); } catch (e) { /* mesuré ci-dessous */ }
    const m = await p.evaluate(mesurerAccueil);
    await p.screenshot({ path: path.join(CAP, `C_${t.n}.png`) });
    if (!m.hero || !m.racine) { v(`C ${t.n}. hero rendu`, false, 'absent'); await ctx.close(); continue; }
    const L = m.hero.w, H = m.hero.h;
    const app = L >= SEUIL_MOBILE ? 'desktop' : 'mobile';
    const z = ZONES[app];
    v(`C ${t.n}. mode positionné, appareil ${app} (boîte ${f1(L)}×${f1(H)})`, m.racine.mode === 'positionne' && m.racine.appareil === app, JSON.stringify(m.racine));
    const zone = { l: m.hero.l + z.cote, r: m.hero.r - z.cote, t: m.hero.t + z.haut, b: m.hero.b - z.bas };
    ['title', 'subtitle', 'cta'].forEach((el) => {
      const r = m[el];
      const attendu = LAYOUT_TEST[app][el];
      if (el === 'subtitle' && app === 'mobile') {
        v(`C ${t.n}. sous-titre masqué sur mobile (même positionné)`, r === null, txtR(r));
        return;
      }
      if (!r) { v(`C ${t.n}. ${el} visible`, false, 'absent'); return; }
      v(`C ${t.n}. ${el} dans la zone sûre`, dedans(r, zone, 1), `${el} ${txtR(r)} | zone ${txtR(zone)}`);
      const e = attendu || { x: 0.5, y: 0.5 };
      const cx = (r.l + r.r) / 2 - m.hero.l, cy = (r.t + r.b) / 2 - m.hero.t;
      const b = bornerPx(e.x * L, e.y * H, r.w, r.h, L, H, app);
      const borne = Math.abs(b.x - e.x * L) > 0.5 || Math.abs(b.y - e.y * H) > 0.5;
      v(`C ${t.n}. ${el} à SA position ${app} (x=${e.x}, y=${e.y}${borne ? ', bornée' : ''}) ±2 px`,
        Math.abs(cx - b.x) <= 2 && Math.abs(cy - b.y) <= 2,
        `centre ${f1(cx)},${f1(cy)} attendu ${f1(b.x)},${f1(b.y)}${borne ? ` (brut ${f1(e.x * L)},${f1(e.y * H)})` : ''}`);
    });
    v(`C ${t.n}. aucun défilement horizontal`, m.scrollW <= m.innerW, `scrollWidth ${m.scrollW} / innerWidth ${m.innerW}`);
    await ctx.close();
  }
}

// ═════════════════════ D / E. ÉDITEUR (dashboard coach) ═════════════════════
async function sessionCoach(ctx) {
  await ctx.addInitScript((email) => {
    try {
      // JETON FACTICE, non signé : seule sa date d'expiration est lue localement
      // (utils/authSession.etatAuth). Sans lui, SECURITY-S1 voit une « session
      // zombie » et ouvre le formulaire de connexion par-dessus le dashboard.
      // Il ne quitte jamais le navigateur : le banc retire Authorization.
      const b64 = (o) => btoa(JSON.stringify(o)).replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_');
      localStorage.setItem('afroboost_jwt', b64({ alg: 'none', typ: 'JWT' }) + '.' + b64({ email, role: 'super_admin', exp: Math.floor(Date.now() / 1000) + 3600 }) + '.banc');
      localStorage.setItem('afroboost_coach_mode', 'true');
      localStorage.setItem('afroboost_coach_user', JSON.stringify({ email, name: 'Banc hero', role: 'super_admin' }));
      if (!sessionStorage.getItem('banc_onglet_pose')) {
        localStorage.setItem('afroboost_coach_tab', 'offers');
        sessionStorage.setItem('banc_onglet_pose', '1');
      }
    } catch (e) { /* stockage bloqué : le banc le verra (éditeur absent) */ }
  }, SUPER_ADMIN);
}

// `App.js` vérifie la session coach au démarrage par GET /api/auth/role ; la
// requête étant anonymisée, la prod répondrait « user » et le banc serait
// déconnecté (terminerSession('role-invalide')). Réponse locale, lecture seule.
const FIXES_COACH = {
  '/api/auth/role': { role: 'super_admin', is_coach: true, is_super_admin: true, email: SUPER_ADMIN },
  // Un tableau nu fait planter le dashboard : il attend la forme paginée.
  '/api/reservations': { data: [], reservations: [], pagination: { total: 0, page: 1, pages: 0, limit: 20 } },
};

/** Ouvre l'éditeur ; renvoie true s'il est là (sinon `p.__diag` dit où le banc s'est arrêté). */
async function ouvrirEditeur(p) {
  await p.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await p.waitForTimeout(4000);
  const present = async () => (await p.locator('[data-testid="hero-editeur"]').count()) > 0;
  const diag = { dashboard: false, sections: [] };
  p.__diag = diag;
  diag.dashboard = await p.evaluate(() => /Connecté en tant que/.test(document.body.innerText || '')).catch(() => false);
  if (await present()) return true;
  for (const libelle of ['Vidéo Hero', 'Ma Vitrine']) {
    const b = p.locator('button', { hasText: libelle }).first();
    if (await b.isVisible().catch(() => false)) {
      await b.click().catch(() => {});
      await p.waitForTimeout(1500);
      const textes = (await p.locator('[data-testid="v547-hero-textes"]').count()) > 0;
      diag.sections.push(`${libelle}${textes ? ' (textes du Hero V547 visibles)' : ''}`);
      if (await present()) {
        await p.locator('[data-testid="hero-editeur"]').first().scrollIntoViewIfNeeded().catch(() => {});
        await p.waitForTimeout(600);
        return true;
      }
    }
  }
  return present();
}

// Pour que le SKIP dise OÙ le banc s'est arrêté (dashboard non ouvert ≠ éditeur absent).
async function diagnosticEditeur(p) {
  const d = p.__diag || {};
  return `éditeur absent : [data-testid=hero-editeur] introuvable — dashboard coach ${d.dashboard ? 'OUVERT' : 'NON ouvert'}` +
    `, sections essayées : ${(d.sections || []).join(', ') || 'aucune'}`;
}

async function choisirAppareil(p, app) {
  await p.click(`[data-testid="hero-editeur-appareil-${app}"]`);
  await p.waitForFunction((a) => {
    const b = document.querySelector(`[data-testid="hero-editeur-appareil-${a}"]`);
    const r = document.querySelector('[data-testid="hero-editeur-apercu"] [data-hero-boite] [data-hero-racine]');
    return b && b.getAttribute('aria-pressed') === 'true' && r && r.getAttribute('data-appareil') === a;
  }, app, { timeout: 10000 });
  await p.waitForTimeout(800);
}

// Positions NORMALISÉES dans une boîte : centre/L, centre/H, largeur/L (l'échelle de l'aperçu s'annule).
const mesurerNormalise = (selBoite) => {
  const boite = document.querySelector(selBoite);
  if (!boite) return null;
  const B = boite.getBoundingClientRect();
  const sortie = { L: B.width, H: B.height, natif: { L: boite.offsetWidth, H: boite.offsetHeight } };
  ['title', 'subtitle', 'cta'].forEach((el) => {
    const n = boite.querySelector(`[data-hero-el="${el}"]`);
    let visible = !!n;
    for (let x = n; visible && x && x !== boite; x = x.parentElement) if (getComputedStyle(x).display === 'none') visible = false;
    const r = n ? n.getBoundingClientRect() : null;
    sortie[el] = visible && r && r.width > 0
      ? { cx: (r.left + r.width / 2 - B.left) / B.width, cy: (r.top + r.height / 2 - B.top) / B.height, w: r.width / B.width }
      : null;
  });
  return sortie;
};
const SEL_APERCU = '[data-testid="hero-editeur-apercu"] [data-hero-boite]';
const pct = (x) => `${(x * 100).toFixed(2)} %`;
function comparer(nom, a, b, tol = 0.005) {
  ['title', 'subtitle', 'cta'].forEach((el) => {
    const x = a && a[el], y = b && b[el];
    if (!x && !y) { v(`${nom} ${el} : masqué des deux côtés`, true); return; }
    if (!x || !y) { v(`${nom} ${el} : présent des deux côtés`, false, `aperçu ${!!x} / accueil ${!!y}`); return; }
    const d = Math.max(Math.abs(x.cx - y.cx), Math.abs(x.cy - y.cy), Math.abs(x.w - y.w));
    v(`${nom} ${el} : écart ≤ ${pct(tol)}`, d <= tol,
      `écart max ${pct(d)} — aperçu cx ${pct(x.cx)} cy ${pct(x.cy)} w ${pct(x.w)} / accueil cx ${pct(y.cx)} cy ${pct(y.cy)} w ${pct(y.w)}`);
  });
}

async function mesurerAccueilNormalise(browser, t, concept) {
  const ctx = await contexte(browser, t);
  await reseau(ctx, { concept: (c) => ({ ...(c || {}), ...concept }) });
  const p = await ctx.newPage();
  await p.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await attendreHero(p, concept.heroLayout ? undefined : 'flux');
  const m = await p.evaluate(mesurerNormalise, '.af-hero');
  await p.screenshot({ path: path.join(CAP, `accueil_${t.n}_${concept.heroLayout ? 'dispo' : 'flux'}_${Date.now()}.png`) });
  await ctx.close();
  return m;
}

const ELEMENTS_D = ['title', 'subtitle', 'cta'];
async function parcoursD(browser) {
  const ctx = await contexte(browser, { w: 1440, h: 900 });
  await sessionCoach(ctx);
  await reseau(ctx, { fixes: FIXES_COACH, concept: (c) => ({ ...(c || {}), heroLayout: LAYOUT_TEST }) });
  const p = await ctx.newPage();
  const la = await ouvrirEditeur(p);
  await p.screenshot({ path: path.join(CAP, 'D_dashboard.png') });
  if (!la) { skip('D. parité aperçu ↔ accueil (desktop + mobile)', await diagnosticEditeur(p)); await ctx.close(); return; }
  const apercu = {};
  for (const app of ['desktop', 'mobile']) {
    await choisirAppareil(p, app);
    apercu[app] = await p.evaluate(mesurerNormalise, SEL_APERCU);
    await p.locator('[data-testid="hero-editeur"]').first().screenshot({ path: path.join(CAP, `D_apercu_${app}.png`) }).catch(() => {});
    const attendu = app === 'desktop' ? [1440, 387] : [386, 473];
    const nat = apercu[app] && apercu[app].natif;
    v(`D. aperçu ${app} : boîte simulée ${attendu[0]}×${attendu[1]} (taille native)`, !!nat && Math.abs(nat.L - attendu[0]) <= 1 && Math.abs(nat.H - attendu[1]) <= 1, nat ? `${nat.L}×${nat.H}` : 'absente');
  }
  await ctx.close();
  for (const [app, t] of [['desktop', { n: '1440x900', w: 1440, h: 900 }], ['mobile', { n: '390x844', w: 390, h: 844 }]]) {
    const acc = await mesurerAccueilNormalise(browser, t, { heroLayout: LAYOUT_TEST });
    // Constat, pas une condition : si la boîte réelle diffère de la boîte simulée,
    // seule la comparaison NORMALISÉE ci-dessous fait foi (consigne du contrat).
    const cible = app === 'desktop' ? [1440, 387] : [386, 473];
    const memeBoite = !!acc && Math.abs(acc.L - cible[0]) <= 1 && Math.abs(acc.H - cible[1]) <= 1;
    info(`D. accueil ${t.n} : .af-hero ${memeBoite ? '=' : '≠'} boîte simulée ${cible[0]}×${cible[1]}${memeBoite ? '' : ' → comparaison normalisée seule'}`,
      acc ? `${f1(acc.L)}×${f1(acc.H)}` : 'absent');
    comparer(`D. parité ${app} (aperçu vs accueil ${t.n})`, apercu[app], acc);
  }
}

async function parcoursE(browser) {
  // Départ SANS disposition : la 1re prise crée la disposition depuis le mode flux.
  let conceptServi = { heroLayout: null };
  const ctx = await contexte(browser, { w: 1440, h: 900 });
  await sessionCoach(ctx);
  const etat = await reseau(ctx, { fixes: FIXES_COACH, concept: (c) => ({ ...(c || {}), ...conceptServi }) });
  const p = await ctx.newPage();
  const la = await ouvrirEditeur(p);
  if (!la) { skip('E. persistance (glisser, taille, PUT unique, rechargement, accueil)', await diagnosticEditeur(p)); await ctx.close(); return; }
  await choisirAppareil(p, 'desktop');
  await p.waitForTimeout(2500); // laisse passer un éventuel auto-save du chargement
  const avant = await p.evaluate(mesurerNormalise, SEL_APERCU);
  const nbAvant = etat.puts.length;

  const glisser = async (el, dx, dy) => {
    const n = p.locator(`${SEL_APERCU} [data-hero-el="${el}"]`).first();
    const b = await n.boundingBox();
    if (!b) throw new Error(`${el} introuvable dans l'aperçu`);
    const x = b.x + b.width / 2, y = b.y + b.height / 2;
    await p.mouse.move(x, y);
    await p.mouse.down();
    for (let i = 1; i <= 8; i++) await p.mouse.move(x + (dx * i) / 8, y + (dy * i) / 8);
    await p.mouse.up();
    return b;
  };
  const boite = await p.locator(SEL_APERCU).first().boundingBox();
  // Déplacements exprimés en fraction de la boîte (indépendants de l'échelle de l'aperçu).
  const DX_T = -0.12, DY_T = 0.08, DX_C = 0.15, DY_C = -0.05;
  await p.click('[data-testid="hero-editeur-choisir-title"]');
  await glisser('title', DX_T * boite.width, DY_T * boite.height);
  await p.click('[data-testid="hero-editeur-choisir-cta"]');
  await glisser('cta', DX_C * boite.width, DY_C * boite.height);
  await p.click('[data-testid="hero-editeur-taille-plus"]');
  await p.waitForTimeout(600);
  const apres = await p.evaluate(mesurerNormalise, SEL_APERCU);
  await p.locator('[data-testid="hero-editeur"]').first().screenshot({ path: path.join(CAP, 'E_apres_edition.png') }).catch(() => {});

  // Aucun saut à la 1re prise : le titre s'est déplacé EXACTEMENT du geste (±2 px de la boîte native 1440).
  const saut = (el, dx, dy) => {
    if (!avant[el] || !apres[el]) return null;
    return { ex: (apres[el].cx - avant[el].cx - dx) * 1440, ey: (apres[el].cy - avant[el].cy - dy) * 387 };
  };
  const sT = saut('title', DX_T, DY_T);
  v('E. titre : suit le geste sans saut (±2 px natifs)', !!sT && Math.abs(sT.ex) <= 2 && Math.abs(sT.ey) <= 2, sT ? `écart ${f1(sT.ex)},${f1(sT.ey)} px` : 'mesure impossible');

  const debut = Date.now();
  while (etat.puts.length === nbAvant && Date.now() - debut < 8000) await p.waitForTimeout(200);
  await p.waitForTimeout(3000); // un 2e PUT éventuel aurait eu le temps de partir
  const puts = etat.puts.slice(nbAvant);
  v('E. un seul PUT /api/concept (debounce)', puts.length === 1, `${puts.length} PUT`);
  const corps = puts.length ? puts[puts.length - 1].corps : null;
  const hl = corps && corps.heroLayout;
  v('E. PUT : heroLayout est un OBJET (jamais texte/liste → 422)', !!hl && typeof hl === 'object' && !Array.isArray(hl), JSON.stringify(hl).slice(0, 200));
  const dCta = hl && hl.desktop && hl.desktop.cta;
  v('E. PUT : taille du CTA augmentée (> 1)', !!dCta && dCta.size > 1, JSON.stringify(dCta));
  v('E. PUT : disposition mobile intacte (null)', !!hl && (hl.mobile === null || hl.mobile === undefined), JSON.stringify(hl && hl.mobile));
  const statut = await p.locator('[data-testid="hero-editeur-statut"]').first().innerText().catch(() => '');
  v('E. statut « Enregistré »', /Enregistr[ée]/.test(statut) && !/…|\.\.\./.test(statut), statut);
  await ctx.close();
  if (!corps) return;

  // Rechargement : le concept servi EST le corps du PUT.
  conceptServi = corps;
  const ctx2 = await contexte(browser, { w: 1440, h: 900 });
  await sessionCoach(ctx2);
  await reseau(ctx2, { fixes: FIXES_COACH, concept: (c) => ({ ...(c || {}), ...conceptServi }) });
  const p2 = await ctx2.newPage();
  const la2 = await ouvrirEditeur(p2);
  v('E. éditeur rouvert après rechargement', la2);
  if (la2) {
    await choisirAppareil(p2, 'desktop');
    const recharge = await p2.evaluate(mesurerNormalise, SEL_APERCU);
    comparer('E. après rechargement, éditeur = avant rechargement :', apres, recharge);
  }
  await ctx2.close();
  const acc = await mesurerAccueilNormalise(browser, { n: '1440x900', w: 1440, h: 900 }, { heroLayout: corps.heroLayout });
  comparer('E. accueil 1440×900 = aperçu édité :', apres, acc);
}

// ═════════════════════════════════════════════════════════════════════════════
(async () => {
  let srv = null;
  if (BUILD_DIR) {
    srv = await servirBuild(path.resolve(BUILD_DIR));
    BASE = `http://127.0.0.1:${srv.address().port}`;
  }
  console.log(`BASE=${BASE}  RELAIS_API=${RELAIS || '(aucun : GET vers BASE)'}  CAPTURES=${CAP}`);
  const browser = await chromium.launch({ headless: true });
  await parcours('A', () => parcoursA(browser));
  await parcours('B', () => parcoursB(browser));
  await parcours('C', () => parcoursC(browser));
  await parcours('D', () => parcoursD(browser));
  await parcours('E', () => parcoursE(browser));
  await browser.close();
  if (srv) srv.close();
  console.log(R.join('\n'));
  console.log(`\n${OK}/${OK + KO} au vert, ${SK} SKIP (hero V554 : accueil, compte à rebours, disposition, parité, persistance)`);
  process.exit(KO ? 1 : 0);
})().catch((e) => { console.error('ERREUR', e); process.exit(2); });
