/**
 * PARCOURS RECHERCHE — V545.
 *
 * CE QUE CE BANC PROUVE, ET POURQUOI IL EXISTE.
 * Le propriétaire a signalé que les mots-clés saisis dans « Mots-clés (pour la
 * recherche) » ne faisaient pas remonter les offres. Le moteur n'était pas en
 * cause : `keywords` est indexé depuis longtemps (App.js, `filteredServices` /
 * `filteredProducts`). Ce qui manquait, c'est que le RÉSULTAT s'affiche :
 * depuis V540 la zone des offres est montée mais `display:none` hors de
 * l'onglet « Offres », et le fil disparaît dès qu'on tape. Mesuré en
 * production : l'offre était trouvée (sa carte était dans le DOM) et la
 * colonne principale tombait à 88 px — écran vide, sans même le message
 * « aucun résultat », celui-ci exigeant que les TROIS listes soient vides.
 *
 * LES MOTS TÉMOINS NE SONT PAS CHOISIS AU HASARD. « promotion », « flexible »,
 * « cadeau », « merchandising » ont été vérifiés sur la donnée réelle : ils
 * n'existent NI dans un nom NI dans une description. Trouver l'offre par l'un
 * d'eux ne peut donc venir que des mots-clés. Si le catalogue change, ce banc
 * doit être revérifié AVANT d'être cru — un mot témoin qui passerait dans un
 * nom rendrait le test vert pour la mauvaise raison.
 *
 * Lancement :
 *   BASE=http://127.0.0.1:8001 \
 *   NODE_PATH=/Users/afroboost/.npm/_npx/<hash>/node_modules \
 *   node tests/parcours/parcours_recherche.cjs
 */
const { chromium } = require('playwright');
const BASE = process.env.BASE || 'http://127.0.0.1:8001';
const R = []; let OK = 0, KO = 0;
const v = (nom, cond, detail = '') => { (cond ? OK++ : KO++); R.push(`${cond ? 'OK  ' : 'RATE'} ${nom}${cond ? '' : '  [' + String(detail).slice(0, 200) + ']'}`); };

/* On mesure la HAUTEUR RÉELLE, jamais la présence dans le DOM : le bloc des
   offres reste monté en permanence (il porte le lien profond `?offre=`), un
   `count()` passerait au vert sur un écran vide. */
const lire = () => {
  const vis = (s) => {
    const n = document.querySelector(s);
    if (!n) return { visible: false, h: 0, txt: '' };
    const r = n.getBoundingClientRect();
    return { visible: getComputedStyle(n).display !== 'none' && r.height > 0, h: Math.round(r.height), txt: (n.innerText || '').slice(0, 900) };
  };
  return {
    offres: vis('[data-testid="offres-aimants"]'),
    produits: vis('#products-section'),
    fil: vis('[data-testid="publications-fil"]'),
    aucunResultat: /Aucun r[ée]sultat|No results/i.test(document.body.innerText || ''),
  };
};

const contient = (txt, mot) => {
  const n = (t) => (t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  return n(txt).includes(n(mot));
};

/* Sur téléphone le champ est replié derrière la loupe ; sur grand écran il est
   toujours là. On ouvre seulement si nécessaire. */
async function chercher(p, mot, mobile) {
  const champ = p.locator('[data-testid="nav-search"]').first();
  if (!(await champ.isVisible().catch(() => false)) && mobile) {
    await p.locator('[data-testid="nav-mobile-recherche"]').first().click().catch(() => {});
    await p.waitForTimeout(900);
  }
  await champ.fill('');
  if (mot) await champ.type(mot, { delay: 30 });
  await p.waitForTimeout(2200);
}

(async () => {
  const browser = await chromium.launch({ headless: true });

  for (const vp of [{ n: '390x844', w: 390, h: 844, m: true }, { n: '1440x900', w: 1440, h: 900, m: false }]) {
    const ctx = await browser.newContext({
      viewport: { width: vp.w, height: vp.h },
      isMobile: vp.m, hasTouch: vp.m, deviceScaleFactor: vp.m ? 2 : 1,
    });
    const p = await ctx.newPage();
    const erreurs = [];
    p.on('pageerror', (e) => erreurs.push(String(e).slice(0, 200)));
    await p.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 60000 });
    await p.waitForSelector('[data-testid="accueil-colonnes"]', { timeout: 60000 });
    await p.waitForTimeout(4000);
    let e = await p.evaluate(lire);

    // ── La règle V540 ne bouge pas tant qu'on ne cherche pas ──
    v(`${vp.n}. hors recherche : les offres restent masquées (règle V540)`, !e.offres.visible, `h=${e.offres.h}`);
    v(`${vp.n}. hors recherche : le fil est le contenu de l'accueil`, e.fil.visible, `h=${e.fil.h}`);

    // ── Un mot qui n'existe QUE dans les mots-clés fait apparaître l'offre ──
    await chercher(p, 'promotion', vp.m);
    e = await p.evaluate(lire);
    v(`${vp.n}. mot-clé seul « promotion » → l'offre Fondateurs S'AFFICHE, sans changer d'onglet`,
      e.offres.visible && contient(e.offres.txt, 'fondateurs'), `h=${e.offres.h}`);

    await chercher(p, 'flexible', vp.m);
    e = await p.evaluate(lire);
    v(`${vp.n}. mot-clé seul « flexible » → Mensuel Liberté s'affiche`,
      e.offres.visible && contient(e.offres.txt, 'mensuel'), `h=${e.offres.h}`);

    // ── Idem pour un PRODUIT ──
    await chercher(p, 'cadeau', vp.m);
    e = await p.evaluate(lire);
    v(`${vp.n}. mot-clé seul « cadeau » → le T-shirt s'affiche`,
      e.produits.visible && contient(e.produits.txt, 't-shirt'), `h=${e.produits.h}`);

    await chercher(p, 'merchandising', vp.m);
    e = await p.evaluate(lire);
    v(`${vp.n}. mot-clé seul « merchandising » → le T-shirt s'affiche`,
      e.produits.visible && contient(e.produits.txt, 't-shirt'), `h=${e.produits.h}`);

    // ── Accents et casse : la normalisation existante doit suffire ──
    for (const forme of ['etudiant', 'Etudiant', 'ETUDIANT', 'étudiant']) {
      await chercher(p, forme, vp.m);
      e = await p.evaluate(lire);
      v(`${vp.n}. « ${forme} » trouve l'offre Étudiant (accents et casse indifférents)`,
        e.offres.visible && contient(e.offres.txt, 'etudiant'), `h=${e.offres.h}`);
    }

    // ── Rien de l'existant ne recule ──
    await chercher(p, 'Fondateurs', vp.m);
    e = await p.evaluate(lire);
    v(`${vp.n}. non-régression : recherche par NOM d'offre`, e.offres.visible && contient(e.offres.txt, 'fondateurs'), `h=${e.offres.h}`);

    await chercher(p, 'abo', vp.m);
    e = await p.evaluate(lire);
    v(`${vp.n}. non-régression : préfixe / synonyme « abo »`, e.offres.visible, `h=${e.offres.h}`);

    await chercher(p, 'casque', vp.m);
    e = await p.evaluate(lire);
    v(`${vp.n}. non-régression : mot présent dans la DESCRIPTION`, e.offres.visible, `h=${e.offres.h}`);

    /* LIMITE CONNUE, HORS PÉRIMÈTRE — figée volontairement.
       `OffresAimants` ne fabrique de carte que pour trois familles (lancement,
       saison, mensuel). Une recherche dont TOUS les résultats sont hors de ces
       familles n'affiche donc rien — et c'est vrai aussi d'une recherche par
       NOM, donc sans rapport avec les mots-clés. Le composant a été exclu du
       périmètre par le propriétaire. On fige l'état ACTUEL : le jour où il
       change, ce test le dira au lieu de laisser la régression passer. */
    await chercher(p, 'workshop', vp.m);
    e = await p.evaluate(lire);
    v(`${vp.n}. limite connue : résultats hors familles à carte → rien à l'écran (OffresAimants, hors périmètre)`,
      !e.offres.visible, `h=${e.offres.h}`);

    // ── Aucun résultat : un message, pas un écran muet ──
    await chercher(p, 'zzzznexistepasdutout', vp.m);
    e = await p.evaluate(lire);
    v(`${vp.n}. aucun résultat : le message est affiché`, e.aucunResultat === true);
    v(`${vp.n}. aucun résultat : aucune zone n'est ouverte à tort`, !e.offres.visible && !e.produits.visible);

    // ── En vidant la recherche, on revient exactement à l'accueil V540 ──
    await chercher(p, '', vp.m);
    e = await p.evaluate(lire);
    v(`${vp.n}. recherche vidée : les offres redeviennent masquées`, !e.offres.visible, `h=${e.offres.h}`);
    v(`${vp.n}. recherche vidée : le fil revient`, e.fil.visible, `h=${e.fil.h}`);

    const bloquantes = erreurs.filter((x) => !/AbortError|play\(\) request|ResizeObserver/i.test(x));
    v(`${vp.n}. aucune erreur JS bloquante`, bloquantes.length === 0, bloquantes.join(' | '));
    await ctx.close();
  }

  await browser.close();
  console.log(R.join('\n'));
  console.log(`\n${OK}/${OK + KO} au vert (recherche V545 : mots-clés offres et produits, accents, non-régression, limite connue)`);
  process.exit(KO ? 1 : 0);
})().catch((e) => { console.error('ERREUR', e); process.exit(2); });
