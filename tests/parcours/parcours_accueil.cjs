// V540 — LA NOUVELLE PAGE D'ACCUEIL, VÉRIFIÉE POUR CE QU'ELLE EST.
//
// POURQUOI CE FICHIER EXISTE. Les parcours d'achat attendaient les trois
// cartes d'offres VISIBLES sur l'écran d'accueil. C'était vrai de l'ancienne
// mise en page, et c'est devenu faux : le contenu passe devant, les offres
// vivent sous l'onglet « Offres ». Ces parcours ont été corrigés pour cliquer
// le vrai onglet — mais corriger un banc ne prouve RIEN si personne ne
// verrouille la règle nouvelle. C'est le rôle de ce fichier : dire par écrit
// ce que l'accueil doit montrer, et ce qu'il ne doit PAS montrer.
//
// LA MESURE EST TOUJOURS `display` CALCULÉ, JAMAIS `.hidden` NI UN COMPTAGE DOM.
// Leçon payée : le bloc des offres reste MONTÉ en permanence (il porte la
// logique du lien profond `?offre=` / `&reserver=1`), simplement masqué. Un
// `count()` le trouve donc toujours, et un test qui compte passe au vert sur un
// écran faux. Seul `getComputedStyle().display` dit la vérité.
//
// Pile LOCALE : aucun paiement, aucun e-mail réel, jamais la production.
const { chromium, devices } = require('playwright');
const fs = require('fs');
const BASE = process.env.BASE || 'http://127.0.0.1:8001';
const CAP = __dirname + '/pw_captures';
fs.mkdirSync(CAP, { recursive: true });
const FID = 'cc73f6ee-163a-433d-b5f0-c00c6392b437';          // Fondateurs
const ESSAI = 'c1e5f73c-0f16-402e-a746-2041e23f72e8';        // 1er cours gratuit
const R = []; let OK = 0, KO = 0;
const v = (nom, cond, detail = '') => { (cond ? OK++ : KO++); R.push(`${cond ? 'OK  ' : 'RATE'} ${nom}${cond ? '' : '  [' + String(detail).slice(0, 300) + ']'}`); };

// `display` réellement calculé par le navigateur, et rien d'autre.
const affiche = (p, sel) => p.evaluate((s) => {
  const el = document.querySelector(s);
  if (!el) return 'absent';
  // Un ancêtre masqué masque l'enfant : on remonte, comme le fait le rendu.
  for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
    if (getComputedStyle(n).display === 'none') return 'none';
  }
  return getComputedStyle(el).display;
}, sel);

// « Pas montré » couvre DEUX cas, et la nuance compte :
//   `none`   = présent dans le DOM, mais masqué ;
//   `absent` = pas rendu du tout.
// Pour le BLOC DES OFFRES, seul `none` est acceptable sur l'accueil : il porte
// la logique du lien profond et doit rester monté (test A, vérifié à part).
// Partout ailleurs, ne pas rendre vaut mieux que masquer, et les deux
// satisfont la règle « ce n'est pas le contenu dominant ».
const masque = (d) => d === 'none' || d === 'absent';

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

async function page(browser, mobile = false, url = BASE + '/') {
  const ctx = mobile ? await browser.newContext({ ...devices['iPhone 13'] })
                     : await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  const erreurs = [];
  p.on('pageerror', (e) => erreurs.push(String(e).slice(0, 200)));
  p.on('dialog', async (d) => { await d.dismiss(); });
  await p.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  return { ctx, p, erreurs };
}
async function parcours(nom, fn) {
  if (process.env.PARCOURS && !process.env.PARCOURS.split(',').includes(nom)) return;
  try { await fn(); } catch (e) { v(`${nom}. ERREUR d'exécution`, false, String(e).split('\n')[0]); }
}

(async () => {
  const browser = await chromium.launch({ headless: true });

  // ── A. SUR L'ACCUEIL : le contenu, pas le catalogue ─────────────────────
  await parcours('A', async () => {
    const { ctx, p, erreurs } = await page(browser, false);
    await p.waitForSelector('[data-testid="accueil-colonnes"]', { timeout: 60000 });
    await p.waitForSelector('[data-testid="publications-fil"]', { timeout: 30000 });
    // Les offres arrivent d'un appel réseau. Tant qu'elles ne sont pas là, dire
    // « elles ne sont pas visibles » ne prouve RIEN : on attendrait le vide.
    // On attend donc qu'elles soient DANS LE DOM (`attached`, jamais `visible`),
    // puis on mesure ce qui nous intéresse : leur `display`.
    await p.waitForSelector('[data-testid="offres-aimants"]', { state: 'attached', timeout: 60000 });

    v('A. l\'accueil est rendu en deux zones (fil + colonne)', (await affiche(p, '[data-testid="accueil-colonnes"]')) !== 'none');
    v('A. le fil de publications est visible', (await affiche(p, '[data-testid="publications-fil"]')) !== 'none');
    v('A. les trois grosses cartes d\'offres ne sont PAS visibles dans le flux principal',
      (await affiche(p, '[data-testid="offres-aimants"]')) === 'none', await affiche(p, '[data-testid="offres-aimants"]'));
    // …mais elles restent MONTÉES : c'est ce bloc qui résout `?offre=`.
    v('A. le bloc des offres reste monté (il porte le lien profond `?offre=` / `&reserver=1`)',
      (await p.locator('[data-testid="offres-aimants"]').count()) === 1);
    v('A. la petite carte « Offre du moment » est autorisée en colonne',
      (await affiche(p, '[data-testid="accueil-offre-du-moment"]')) !== 'none');
    v('A. la colonne porte Live et Spordateur',
      (await affiche(p, '[data-testid="accueil-carte-live"]')) !== 'none'
      && (await affiche(p, '[data-testid="accueil-carte-spordateur"]')) !== 'none');

    // UNE publication par ligne, même sur desktop : on compare les `x` réels.
    const lignes = await p.$$eval('[data-testid="publication-fil-carte"]', (els) => {
      const par = {};
      els.forEach((e) => { const b = e.getBoundingClientRect(); const k = Math.round(b.top / 20); par[k] = (par[k] || 0) + 1; });
      return { max: Math.max(0, ...Object.values(par)), n: els.length };
    });
    v('A. jamais deux publications côte à côte (1 par ligne, desktop compris)', lignes.max <= 1, JSON.stringify(lignes));
    v('A. aucune erreur JS sur l\'accueil', erreurs.length === 0, erreurs.join(' | '));
    await p.screenshot({ path: `${CAP}/ACCUEIL-A-fil.png` });
    await ctx.close();
  });

  // ── B. APRÈS CLIC « OFFRES » : le catalogue prend la main ───────────────
  await parcours('B', async () => {
    const { ctx, p } = await page(browser, false);
    await p.waitForSelector('[data-testid="accueil-colonnes"]', { timeout: 60000 });
    await p.waitForSelector('[data-testid="offres-aimants"]', { state: 'attached', timeout: 60000 });
    const onglet = p.locator('[data-testid="nav-tab-offers"]');
    v('B. l\'onglet « Offres » est un vrai bouton cliquable', await onglet.isVisible());
    await onglet.click();
    await p.waitForSelector('[data-testid="offres-aimants"]', { state: 'visible', timeout: 30000 });

    v('B. les offres deviennent visibles', (await affiche(p, '[data-testid="offres-aimants"]')) !== 'none');
    const cartes = await p.locator('[data-testid="grille-aimants"] > *').count();
    const noms = (await p.locator('[data-testid="grille-aimants"]').textContent()) || '';
    v('B. trois offres sont présentées', cartes === 3, `${cartes} carte(s) : ${noms.replace(/\s+/g, ' ').slice(0, 220)}`);
    v('B. ce sont bien Fondateurs, la saison 8 mois et le mensuel',
      /Fondateur/i.test(noms) && /8\s*mois|saison/i.test(noms) && /mensuel|libert/i.test(noms),
      noms.replace(/\s+/g, ' ').slice(0, 260));
    v('B. le fil n\'est plus le contenu dominant', masque(await affiche(p, '[data-testid="publications-fil"]')),
      await affiche(p, '[data-testid="publications-fil"]'));
    v('B. la colonne reste accessible : Live + Spordateur',
      (await affiche(p, '[data-testid="accueil-carte-live"]')) !== 'none'
      && (await affiche(p, '[data-testid="accueil-carte-spordateur"]')) !== 'none');
    v('B. l\'« Offre du moment » n\'est PAS dupliquée à côté du catalogue',
      masque(await affiche(p, '[data-testid="accueil-offre-du-moment"]')),
      await affiche(p, '[data-testid="accueil-offre-du-moment"]'));
    v('B. « Voir toutes les offres » reste le chemin vers le catalogue complet',
      (await p.locator('[data-testid="voir-toutes-les-offres"]').count()) === 1);
    await p.screenshot({ path: `${CAP}/ACCUEIL-B-offres.png` });

    // Retour « Accueil » : l'écran redevient un fil.
    await p.click('[data-testid="nav-tab-all"]');
    await p.waitForTimeout(600);
    v('B. « Accueil » ramène le fil et remasque les offres',
      (await affiche(p, '[data-testid="publications-fil"]')) !== 'none'
      // strict `none`, pas `masque` : de retour sur l'accueil, le bloc doit etre
      // MONTE et masque — c'est la condition du lien profond.
      && (await affiche(p, '[data-testid="offres-aimants"]')) === 'none');
    await ctx.close();
  });

  // ── C. LIEN PROFOND DIRECT : sans jamais toucher l'onglet ───────────────
  // C'est un parcours DIFFÉRENT de B : le visiteur arrive d'un lien (WhatsApp,
  // page SEO, lien partenaire) et ne clique sur rien. La régression qu'on a
  // introduite puis corrigée était exactement là : démonter le bloc des offres
  // hors de l'onglet coupait cette porte.
  await parcours('C', async () => {
    const { ctx, p, erreurs } = await page(browser, false, `${BASE}/?offre=${FID}`);
    await p.waitForSelector('[data-testid="fiche-cta"]', { timeout: 60000 });
    v('C. `?offre=<id>` ouvre la fiche SANS cliquer sur « Offres »',
      /Fondateur/i.test((await p.locator('[data-testid="fiche-nom"]').textContent()) || ''),
      await p.locator('[data-testid="fiche-nom"]').textContent().catch(() => ''));
    v('C. le bouton d\'achat est là (la caisse n\'a pas bougé)', await p.locator('[data-testid="fiche-cta"]').isVisible());
    v('C. aucune erreur JS sur ce chemin', erreurs.length === 0, erreurs.join(' | '));
    await ctx.close();
  });

  await parcours('C2', async () => {
    const { ctx, p, erreurs } = await page(browser, true, `${BASE}/?offre=${ESSAI}&reserver=1`);
    await p.waitForSelector('[data-testid="user-email-input"]', { state: 'attached', timeout: 60000 });
    v('C2. `?offre=<essai>&reserver=1` ouvre le FORMULAIRE de réservation, en bloc dans la page',
      (await p.locator('[data-testid="user-email-input"]').count()) === 1);
    v('C2. les champs transactionnels sont tous là (nom, e-mail, WhatsApp, envoi)',
      (await p.locator('[data-testid="user-name-input"]').count()) === 1
      && (await p.locator('[data-testid="user-whatsapp-input"]').count()) === 1
      && (await p.locator('[data-testid="submit-reservation-btn"]').count()) === 1);
    v('C2. le formulaire RESTE ouvert (aucun effet ne le referme 400 ms plus tard)',
      await (async () => { await p.waitForTimeout(1500); return (await p.locator('[data-testid="user-email-input"]').count()) === 1; })());
    v('C2. aucune erreur JS sur ce chemin', erreurs.length === 0, erreurs.join(' | '));
    await p.screenshot({ path: `${CAP}/ACCUEIL-C2-formulaire.png` });
    await ctx.close();
  });

  // ── D. MOBILE : une seule colonne, rien qui déborde ─────────────────────
  await parcours('D', async () => {
    const { ctx, p } = await page(browser, true);
    await p.waitForSelector('[data-testid="accueil-colonnes"]', { timeout: 60000 });
    await p.waitForSelector('[data-testid="publications-fil"]', { state: 'attached', timeout: 60000 });
    await p.waitForSelector('[data-testid="offres-aimants"]', { state: 'attached', timeout: 60000 });
    v('D. mobile : le fil est bien le contenu de l\'accueil', (await affiche(p, '[data-testid="publications-fil"]')) !== 'none');
    v('D. mobile : les offres restent masquées sur l\'accueil',
      (await affiche(p, '[data-testid="offres-aimants"]')) === 'none');
    const debord = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    v('D. mobile : aucun débordement horizontal', debord <= 1, `${debord} px`);
    await ouvrirOnglet(p, 'offers');
    await p.waitForSelector('[data-testid="offres-aimants"]', { state: 'visible', timeout: 30000 });
    v('D. mobile : « Offres » s\'atteint par le hamburger et le tiroir',
      (await affiche(p, '[data-testid="offres-aimants"]')) !== 'none');
    await p.screenshot({ path: `${CAP}/ACCUEIL-D-mobile.png` });
    await ctx.close();
  });

  // ── E. HERO MOBILE : un seul message, une seule ligne, de l'air ─────────
  // V544. Trois choses qu'on ne veut plus jamais revoir sur téléphone :
  //   1. le libellé du bouton cassé en deux lignes (« …1er cours » / « gratuit ») ;
  //   2. la promesse « premier cours gratuit » écrite DEUX fois, dans la ligne
  //      d'offre puis dans le bouton, à 26 px d'intervalle ;
  //   3. un hero si tassé que titre, bouton et bloc coach se touchent.
  // On mesure aux deux tailles qui servent de référence au projet. Le nombre
  // de lignes se lit sur le nœud de TEXTE (`getClientRects()`), jamais sur la
  // hauteur du bouton : un bouton haut n'est pas un bouton à deux lignes.
  await parcours('E', async () => {
    const ATTENDU = 'Réserver mon 1er cours gratuit';
    for (const vp of [{ n: '390x844', width: 390, height: 844 }, { n: '360x640', width: 360, height: 640 }]) {
      const ctx = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        isMobile: true, hasTouch: true, deviceScaleFactor: 2,
      });
      const p2 = await ctx.newPage();
      await p2.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 60000 });
      await p2.waitForSelector('[data-testid="c1-hero-cta"]', { timeout: 60000 });
      await p2.waitForTimeout(2500);
      const m = await p2.evaluate(() => {
        const q = (s) => document.querySelector(s);
        const r = (n) => { if (!n) return null; const b = n.getBoundingClientRect(); return { y: Math.round(b.y), h: Math.round(b.height) }; };
        const cta = q('[data-testid="c1-hero-cta"]');
        const h1 = q('.af-hero-texte h1');
        const offre = q('.af-hero-offre');
        let lignes = null;
        if (cta) {
          const t = Array.from(cta.childNodes).find((x) => x.nodeType === 3 && x.textContent.trim());
          if (t) { const g = document.createRange(); g.selectNodeContents(t); lignes = g.getClientRects().length; }
        }
        return {
          texte: cta ? cta.textContent.replace(/\s+/g, ' ').trim() : '',
          lignes,
          deborde: cta ? cta.scrollWidth > cta.clientWidth + 1 : null,
          police: cta ? parseFloat(getComputedStyle(cta).fontSize) : null,
          offreAffichee: offre ? getComputedStyle(offre).display !== 'none' : null,
          offreMontee: !!offre,
          ecart: h1 && cta ? Math.round(cta.getBoundingClientRect().y - (h1.getBoundingClientRect().y + h1.getBoundingClientRect().height)) : null,
          debord: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          _h1: r(h1), _cta: r(cta),
        };
      });
      v(`E. ${vp.n} : le bouton affiche exactement « ${ATTENDU} »`, m.texte === ATTENDU, m.texte);
      v(`E. ${vp.n} : le libellé tient sur UNE ligne`, m.lignes === 1, `${m.lignes} ligne(s)`);
      v(`E. ${vp.n} : le libellé n'est ni coupé ni en débordement`, m.deborde === false, `scrollWidth > clientWidth = ${m.deborde}`);
      v(`E. ${vp.n} : la police du bouton reste lisible (>= 14 px)`, m.police >= 14, `${m.police} px`);
      v(`E. ${vp.n} : la promesse n'est PLUS écrite deux fois (ligne d'offre masquée)`, m.offreAffichee === false, `affichée = ${m.offreAffichee}`);
      v(`E. ${vp.n} : la ligne d'offre reste montée (masquée, jamais supprimée)`, m.offreMontee === true);
      v(`E. ${vp.n} : le titre et le bouton respirent (>= 34 px)`, m.ecart !== null && m.ecart >= 34, `${m.ecart} px`);
      v(`E. ${vp.n} : aucun débordement horizontal`, m.debord <= 1, `${m.debord} px`);
      await p2.screenshot({ path: `${CAP}/ACCUEIL-E-hero-${vp.width}.png` });
      await ctx.close();
    }
    // Sur grand écran, RIEN ne change : la ligne d'offre est toujours là.
    const { ctx, p: pd } = await page(browser, false);
    await pd.waitForSelector('[data-testid="c1-hero-cta"]', { timeout: 60000 });
    await pd.waitForTimeout(1500);
    v('E. desktop : la ligne d\'offre du hero reste affichée', (await affiche(pd, '.af-hero-offre')) !== 'none', await affiche(pd, '.af-hero-offre'));
    await ctx.close();
  });

  await browser.close();
  console.log(R.join('\n'));
  console.log(`\n${OK}/${OK + KO} au vert (accueil : A fil, B onglet Offres, C/C2 liens profonds, D mobile, E hero V544)`);
  process.exit(KO ? 1 : 0);
})().catch((e) => { console.error('ERREUR', e); process.exit(2); });
