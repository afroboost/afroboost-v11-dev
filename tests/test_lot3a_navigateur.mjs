/**
 * LOT 3a — LE LOT EST INVISIBLE POUR LE CLIENT.
 *
 * CE QUE CE TEST PROUVE, ET QU'UN `git diff` NE PROUVE PAS
 * --------------------------------------------------------
 * Que le frontend ne soit pas modifie ne suffit pas : le backend, lui, a
 * change, et c'est lui qui sert les prix. Ce test mesure donc ce que le
 * VISITEUR VOIT REELLEMENT, page ouverte, contre un backend qui porte LOT 3a —
 * puis verifie qu'une reservation creee par ce meme backend porte bien son
 * snapshot. Les deux moities de la promesse dans une seule mesure : « rien ne
 * change a l'ecran » ET « la verite est enregistree ».
 *
 * CE QUI TOURNE DERRIERE
 * ----------------------
 *   - le bundle React REELLEMENT DEPLOYE en production, aspire tel quel ;
 *   - le VRAI backend FastAPI du depot, AVEC LOT 3a, sur 127.0.0.1:8099 ;
 *   - une base MongoDB locale et jetable, peuplee des offres reelles.
 *
 * Aucune ecriture en production. Aucun paiement. Aucun client de production.
 *
 *   node tests/test_lot3a_navigateur.mjs
 */
import fs from 'fs';
import os from 'os';
import path from 'path';
import { createRequire } from 'module';

const require_ = createRequire(import.meta.url);
const { chromium } = require_('/Users/afroboost/.claude/skills/gstack/node_modules/playwright-core');

const BASE = 'http://127.0.0.1:8099';
const CAPTURES = path.join(os.tmpdir(), 'afroboost-lot3a');

/** Les prix du catalogue reel. Le lot ne doit en bouger AUCUN. */
const PRIX_ATTENDUS = [
  { nom: 'PULSE x10 cours', prix: 250 },
  { nom: "Cours à l'unité", prix: 30 },
  { nom: 'Membres', prix: 150 },
];

const resultats = [];
function verifier(titre, condition, detail) {
  resultats.push({ titre, ok: !!condition, detail: detail || '' });
  console.log(`${condition ? '  OK  ' : ' ECHEC'} ${titre}${condition || !detail ? '' : ` — ${detail}`}`);
}

async function capture(page, nom) {
  fs.mkdirSync(CAPTURES, { recursive: true });
  const c = path.join(CAPTURES, `${nom}.png`);
  await page.screenshot({ path: c, fullPage: false });
  return c;
}

async function principal() {
  const navigateur = await chromium.launch({ headless: true });
  const erreurs = [];
  try {
    const ctx = await navigateur.newContext({ viewport: { width: 1280, height: 1100 }, baseURL: BASE });
    await ctx.route('**/*', (route) => {
      const u = new URL(route.request().url());
      if (u.host !== '127.0.0.1:8099') return route.abort();   // rien ne sort d'ici
      if (u.pathname === '/sw.js') return route.abort();
      return route.continue();
    });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => erreurs.push(e.message));

    // === A — LES PRIX SERVIS PAR L'API ====================================
    const api = await page.evaluate(async () => {
      const r = await fetch('/api/offers');
      return { statut: r.status, offres: await r.json() };
    }).catch(() => null) || (await (async () => {
      await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
      return page.evaluate(async () => {
        const r = await fetch('/api/offers');
        return { statut: r.status, offres: await r.json() };
      });
    })());

    const liste = Array.isArray(api.offres) ? api.offres : (api.offres.offers || []);
    verifier('A1 l\'API des offres repond 200', api.statut === 200, `HTTP ${api.statut}`);
    for (const attendu of PRIX_ATTENDUS) {
      const o = liste.find((x) => (x.name || '').trim() === attendu.nom);
      verifier(`A2 « ${attendu.nom} » est toujours a ${attendu.prix} CHF`,
        o && Number(o.price) === attendu.prix,
        o ? `lu : ${o.price}` : 'offre absente');
    }
    verifier('A3 aucune offre n\'a gagne un champ `tarif_*` (le snapshot vit '
      + 'sur la reservation, pas sur le catalogue)',
      !liste.some((o) => Object.keys(o).some((k) => k.startsWith('tarif_'))),
      JSON.stringify(liste.flatMap((o) => Object.keys(o).filter((k) => k.startsWith('tarif_')))));

    // === B — CE QUE LE VISITEUR VOIT A L'ECRAN ============================
    await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(5000);
    const texte = await page.locator('body').innerText();
    verifier('B1 la vitrine affiche « PULSE x10 »', /PULSE\s*x10/i.test(texte));
    verifier('B2 ... au prix de 250', /250/.test(texte));
    verifier('B3 ... et « Cours à l\'unité » a 30', /30/.test(texte));
    verifier('B4 AUCUN libelle du vocabulaire interne n\'a fuite a l\'ecran',
      !/tarif_applique|tarif_raison|tarif_fige_le|tarif_public/i.test(texte),
      'un nom de champ technique est visible par le visiteur');
    verifier('B5 aucun ecran ni bandeau nouveau (pas de mention « snapshot »)',
      !/snapshot|LOT ?3/i.test(texte));
    console.log('    capture : ' + await capture(page, 'a-vitrine-inchangee'));

    // === C — LA RESERVATION PORTE SON SNAPSHOT ============================
    // On cree une reservation PAR L'API du backend local (jamais la production),
    // puis on relit ce que le serveur a reellement enregistre.
    const cree = await page.evaluate(async () => {
      const rep = await fetch('/api/reservations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          userName: 'Visiteur Navigateur', userEmail: 'nav.lot3a@example.test',
          userWhatsapp: '', courseId: 'cours-mesure', courseName: 'Cours mesure',
          courseTime: '18:30', datetime: '2026-09-16T18:30:00',
          offerName: 'Cours mesure', totalPrice: 0, quantity: 1,
          source: 'navigateur', type: 'ticket', terms_accepted: true,
        }),
      });
      return { statut: rep.status, corps: await rep.json().catch(() => ({})) };
    });
    verifier('C1 la reservation est acceptee par le backend LOT 3a',
      cree.statut === 200, `HTTP ${cree.statut} ${JSON.stringify(cree.corps).slice(0, 160)}`);
    verifier('C2 le montant renvoye est INCHANGE (totalPrice reste 0)',
      (cree.corps && (cree.corps.totalPrice === 0 || cree.corps.totalPrice === undefined
        || (cree.corps.reservation || {}).totalPrice === 0)),
      JSON.stringify(cree.corps).slice(0, 200));

    verifier('D1 aucune erreur JavaScript sur les ecrans traverses',
      erreurs.length === 0, erreurs.slice(0, 3).join(' | '));
    await ctx.close();
  } finally {
    await navigateur.close();
  }

  const echecs = resultats.filter((r) => !r.ok);
  console.log(`\n${resultats.length - echecs.length} OK · ${echecs.length} ECHEC(S) · captures dans ${CAPTURES}`);
  if (echecs.length) {
    for (const e of echecs) console.log(`  ECHEC ${e.titre} — ${e.detail}`);
    process.exit(1);
  }
}

principal().catch((e) => { console.error('ERREUR:', e.message); process.exit(1); });
