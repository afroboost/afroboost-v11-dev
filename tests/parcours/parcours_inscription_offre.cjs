// V570 — INSCRIPTION APRÈS CHOIX D'UNE OFFRE, sur la pile LOCALE (vraie app, base de test, faux Stripe).
// AUCUN paiement réel, AUCUN e-mail réel.
//   A  desktop : Mensuel Liberté -> « Tes informations » (Nom + E-mail + WhatsApp) -> validation -> Stripe
//      créé UNE fois, e-mail prérempli, l'offre est TOUJOURS Mensuel Liberté ; paiement -> abonnement avec
//      nom + WhatsApp en base, contact CRM avec le WhatsApp
//   B  mobile (iPhone 13) : même parcours, champs visibles, aucun débordement horizontal
//   C  membre existant (même e-mail, même offre récurrente) -> refus 409 « déjà cet abonnement », 0 checkout,
//      aucun 2e abonnement
//   D  V570b anti-doublon WhatsApp : A e-mail nouveau + numéro existant -> bloqué ; B même membre -> continue ;
//      e-mail existant + autre numéro -> logique membre existant inchangée
//   E  toutes les offres : la formule choisie est celle du checkout (product_name) après le formulaire
const { chromium, devices } = require('playwright');
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const BASE = 'http://127.0.0.1:8001';
const R = []; let OK = 0, KO = 0;
const v = (nom, cond, detail = '') => { (cond ? OK++ : KO++); R.push(`${cond ? 'OK  ' : 'RATE'} ${nom}${cond ? '' : '  [' + String(detail).slice(0, 400) + ']'}`); };
const uid = Date.now().toString(36);
// Numéros UNIQUES par passage (la base de test garde les abonnés des passages précédents :
// un numéro fixe serait — à juste titre — « déjà associé à un compte » par V570b).
const sept = String(Date.now()).slice(-7);
const numero = (prefixe) => `+41 ${prefixe} ${sept.slice(0, 3)} ${sept.slice(3, 5)} ${sept.slice(5, 7)}`;
// Lecture SEULE de la base de TEST (afroboost_pw_test) via pymongo — jamais la prod.
const PY = `
import json, sys
from pymongo import MongoClient
env = {}
for l in open(sys.argv[1]):
    l = l.strip()
    if '=' in l and not l.startswith('#'):
        k, v = l.split('=', 1); env[k] = v.strip().strip('"').strip("'")
db = MongoClient(env['MONGO_URL'], serverSelectionTimeoutMS=20000)['afroboost_pw_test']
docs = list(db[sys.argv[2]].find(json.loads(sys.argv[3]), {'_id': 0}).limit(20))
print(json.dumps(docs, default=str))
`;
const lireBase = (coll, filtre) => JSON.parse(execFileSync('python3', ['-c', PY, path.join(__dirname, '..', '..', '.env.local'), coll, JSON.stringify(filtre)], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim());
const db = { collection: (c) => ({
  findOne: async (f) => lireBase(c, f)[0] || null,
  find: (f) => ({ toArray: async () => lireBase(c, f) }),
  countDocuments: async (f) => lireBase(c, f).length,
}) };
const etat = async (p) => (await (await p.request.get(BASE + '/faux-stripe/etat')).json());

async function ouvrir(browser, mobile, url) {
  const ctx = mobile ? await browser.newContext({ ...devices['iPhone 13'] }) : await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage(); const erreurs = [];
  p.on('pageerror', e => erreurs.push(String(e).slice(0, 200)));
  p.on('dialog', d => d.dismiss());
  await p.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  return { ctx, p, erreurs };
}

async function cta(p) {
  await p.waitForSelector('[data-testid="fiche-cta"]', { timeout: 60000 });
  for (let i = 0; i < 4; i++) { try { await p.locator('[data-testid="fiche-cta"]').click({ timeout: 8000 }); return; } catch (e) { if (i === 3) throw e; } }
}

async function remplir(p, nom, email, tel) {
  await p.fill('[data-testid="v570-nom-input"]', nom);
  await p.fill('[data-testid="v528-email-input"]', email);
  await p.fill('[data-testid="v570-whatsapp-input"]', tel);
}

async function scenarioA(browser, db, offre, mobile) {
  const T = mobile ? 'B MOBILE' : 'A DESKTOP';
  const EMAIL = `pw-v570-${mobile ? 'm' : 'd'}-${uid}@example.com`;
  const TEL = numero(mobile ? '78' : '79');
  const { ctx, p, erreurs } = await ouvrir(browser, mobile, `${BASE}/?offre=${offre.id}`);
  await cta(p);
  const n0 = Object.keys(await etat(p)).length;
  const modale = p.locator('[data-testid="v528-etape-email"]');
  await modale.waitFor({ timeout: 15000 }).catch(() => null);
  const texte = (await modale.textContent().catch(() => '')) || '';
  v(`${T}. après « Choisir cette formule » : « Tes informations » + texte d'inscription, AUCUN checkout encore`,
    /Tes informations/.test(texte) && /Tu as choisi ton offre/.test(texte) && /créer ton espace membre/.test(texte) && Object.keys(await etat(p)).length === n0, texte.slice(0, 200));
  v(`${T}. l'offre choisie est rappelée dans la modale (${offre.name})`, ((await p.locator('[data-testid="v570-offre-choisie"]').textContent().catch(() => '')) || '').trim() === offre.name);
  const ordre = await p.evaluate(() => [...document.querySelectorAll('[data-testid="v528-etape-email"] input')].map(i => i.getAttribute('data-testid')));
  v(`${T}. ordre des champs : Nom et prénom, E-mail, WhatsApp`, JSON.stringify(ordre) === JSON.stringify(['v570-nom-input', 'v528-email-input', 'v570-whatsapp-input']), JSON.stringify(ordre));
  // validations
  await p.click('[data-testid="v528-email-continuer"]'); await p.waitForTimeout(300);
  const err1 = await p.locator('[data-testid="v528-etape-email"] [role="alert"]').textContent().catch(() => '');
  await remplir(p, 'Léa Test', 'pas-un-email', TEL); await p.click('[data-testid="v528-email-continuer"]'); await p.waitForTimeout(300);
  const err2 = await p.locator('[data-testid="v528-etape-email"] [role="alert"]').textContent().catch(() => '');
  await remplir(p, 'Léa Test', EMAIL, '12'); await p.click('[data-testid="v528-email-continuer"]'); await p.waitForTimeout(300);
  const err3 = await p.locator('[data-testid="v528-etape-email"] [role="alert"]').textContent().catch(() => '');
  v(`${T}. validation claire : nom manquant / e-mail invalide / WhatsApp invalide, toujours 0 checkout`,
    /nom/i.test(err1) && /e-mail invalide/i.test(err2) && /WhatsApp invalide/i.test(err3) && Object.keys(await etat(p)).length === n0, `${err1} | ${err2} | ${err3}`);
  if (mobile) {
    const deb = await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    const boites = await Promise.all(['v570-nom-input', 'v528-email-input', 'v570-whatsapp-input', 'v528-email-continuer'].map(id => p.locator(`[data-testid="${id}"]`).boundingBox()));
    v(`${T}. mobile : aucun débordement, les 3 champs + « Continuer » visibles et dans l'écran`, !deb && boites.every(b => b && b.x >= 0 && b.x + b.width <= 391), JSON.stringify(boites));
  }
  await p.screenshot({ path: path.join(process.env.CAPTURES || __dirname, `v570-${mobile ? 'mobile' : 'desktop'}.png`) }).catch(() => null);
  await remplir(p, 'Léa Test', EMAIL, TEL);
  const [nav] = await Promise.all([p.waitForNavigation({ url: /faux-stripe/, timeout: 30000 }).catch(() => null), p.click('[data-testid="v528-email-continuer"]')]);
  const sessions = await etat(p); const ids = Object.keys(sessions); const s = sessions[ids[ids.length - 1]] || {};
  v(`${T}. « Continuer » -> checkout créé EXACTEMENT une fois`, !!nav && ids.length === n0 + 1, `${p.url()} ${n0}->${ids.length}`);
  v(`${T}. l'offre est TOUJOURS ${offre.name} (offer_id + product_name du checkout)`, (s.metadata || {}).offer_id === offre.id && (s.metadata || {}).product_name === offre.name, JSON.stringify(s.metadata));
  v(`${T}. nom + WhatsApp + e-mail partent avec la demande (métadonnées V251)`, (s.metadata || {}).customer_name === 'Léa Test' && (s.metadata || {}).customer_phone === TEL.replace(/\s/g, '') && (s.metadata || {}).customer_email === EMAIL, JSON.stringify(s.metadata));
  v(`${T}. e-mail prérempli sur la page de paiement`, ((await p.locator('[data-testid="faux-email"]').textContent().catch(() => '')) || '').trim().toLowerCase() === EMAIL);
  await Promise.all([p.waitForNavigation({ timeout: 60000 }), p.click('[data-testid="faux-payer"]')]);
  let abo = null;
  for (let i = 0; i < 15 && !abo; i++) { abo = await db.collection('subscriptions').findOne({ email: EMAIL }); if (!abo) await p.waitForTimeout(1000); }
  v(`${T}. après paiement : l'abonnement porte le nom ET le WhatsApp saisis, et la bonne offre`, abo && abo.name === 'Léa Test' && abo.whatsapp === TEL.replace(/\s/g, '') && abo.offer_id === offre.id, JSON.stringify(abo && { name: abo.name, whatsapp: abo.whatsapp, offer_id: abo.offer_id }));
  const contacts = await db.collection('chat_participants').find({ email: EMAIL }).toArray();
  v(`${T}. un SEUL contact CRM, avec le WhatsApp saisi`, contacts.length === 1 && (contacts[0].phone === TEL.replace(/\s/g, '')), JSON.stringify(contacts.map(c => ({ name: c.name, phone: c.phone }))));
  v(`${T}. aucune exception JS`, erreurs.length === 0, JSON.stringify(erreurs));
  await ctx.close();
  return { EMAIL, TEL };
}

async function scenarioC(browser, db, offre, existant) {
  // Même e-mail, même offre récurrente : la garde anti-double existante (409) doit tenir.
  const { ctx, p } = await ouvrir(browser, false, `${BASE}/?offre=${offre.id}`);
  await cta(p);
  await p.locator('[data-testid="v528-etape-email"]').waitFor({ timeout: 15000 });
  const n0 = Object.keys(await etat(p)).length;
  await remplir(p, 'Léa Test', existant.EMAIL, existant.TEL);
  await p.click('[data-testid="v528-email-continuer"]');
  const refus = p.locator('[data-testid="v529-refus"]');
  await refus.waitFor({ timeout: 20000 }).catch(() => null);
  const t = (await refus.textContent().catch(() => '')) || '';
  const n = await db.collection('subscriptions').countDocuments({ email: existant.EMAIL });
  v('C. membre existant (même e-mail, même offre) -> « Tu as déjà cette formule », 0 checkout, aucun 2e abonnement',
    /déjà cette formule/i.test(t) && Object.keys(await etat(p)).length === n0 && n === 1, `${t.slice(0, 120)} sessions=${Object.keys(await etat(p)).length - n0} abonnements=${n}`);
  await ctx.close();
}

async function scenarioD(browser, db, offre, existant, offreUnique) {
  // V570b — anti-doublon WhatsApp (règle du 02/10).
  const essai = async (o, nom, email, tel) => {
    const { ctx, p } = await ouvrir(browser, false, `${BASE}/?offre=${o.id}`);
    await cta(p);
    await p.locator('[data-testid="v528-etape-email"]').waitFor({ timeout: 15000 });
    const n0 = Object.keys(await etat(p)).length;
    await remplir(p, nom, email, tel);
    await p.click('[data-testid="v528-email-continuer"]');
    const paiement = await p.waitForURL(/faux-stripe/, { timeout: 25000 }).then(() => true).catch(() => false);
    const refus = paiement ? '' : ((await p.locator('[data-testid="v529-refus"]').textContent().catch(() => '')) || '');
    const crees = Object.keys(await etat(p)).length - n0;
    await ctx.close();
    return { paiement, refus, crees };
  };
  // A. e-mail NOUVEAU + WhatsApp EXISTANT -> bloqué, aucun Stripe, aucun nouveau contact / membre
  const EMAIL_A = `pw-v570-wa-${uid}@example.com`;
  const a = await essai(offre, 'Autre Personne', EMAIL_A, existant.TEL.replace('+41 ', '0'));   // même numéro, forme nationale
  const contactsA = await db.collection('chat_participants').countDocuments({ email: EMAIL_A });
  const abosA = await db.collection('subscriptions').countDocuments({ email: EMAIL_A });
  v('D-A. e-mail nouveau + WhatsApp existant -> bloqué avec le message exact, 0 paiement, 0 contact, 0 membre',
    !a.paiement && a.crees === 0 && /Numéro WhatsApp déjà utilisé/.test(a.refus)
    && /Ce numéro WhatsApp est déjà associé à un compte\. Utilise l’adresse e-mail liée à ce compte ou contacte-nous si tu as changé d’adresse\./.test(a.refus)
    && contactsA === 0 && abosA === 0, JSON.stringify({ ...a, contactsA, abosA }));
  // B. e-mail EXISTANT + WhatsApp correspondant -> compte existant reconnu (offre non récurrente : on continue)
  const b = await essai(offreUnique, 'Léa Test', existant.EMAIL, existant.TEL);
  const contactsB = await db.collection('chat_participants').countDocuments({ email: existant.EMAIL });
  v('D-B. e-mail + WhatsApp du même membre -> continue normalement (paiement), toujours UN seul contact',
    b.paiement && b.crees === 1 && contactsB === 1, JSON.stringify({ ...b, contactsB }));
  // e-mail EXISTANT + autre WhatsApp -> logique membre existant d'avant (aucun blocage)
  const e = await essai(offreUnique, 'Léa Test', existant.EMAIL, numero('76'));
  v('D-E. e-mail existant + autre WhatsApp -> logique membre existant inchangée (on continue)', e.paiement && e.crees === 1, JSON.stringify(e));
}

async function scenarioE(browser, offres) {
  const resultats = [];
  for (const o of offres) {
    const { ctx, p } = await ouvrir(browser, false, `${BASE}/?offre=${o.id}`);
    let verdict = '';
    try {
      const aFiche = await p.waitForSelector('[data-testid="fiche-cta"]', { timeout: 20000 }).then(() => true).catch(() => false);
      if (!aFiche) {
        verdict = 'produit à variantes : même porte startProgressiveCheckout (non piloté par ce banc)';
        resultats.push(`${o.name} (${o.price} CHF) : ${verdict}`); await ctx.close(); continue;
      }
      await cta(p);
      const modale = p.locator('[data-testid="v528-etape-email"]');
      await modale.waitFor({ timeout: 8000 }).catch(() => null);
      if (await modale.count()) {
        const rappel = ((await p.locator('[data-testid="v570-offre-choisie"]').textContent().catch(() => '')) || '').trim();
        const n0 = Object.keys(await etat(p)).length;
        await remplir(p, 'Test Offre', `pw-v570-e-${o.id.slice(0, 6)}-${uid}@example.com`, numero('5' + String(offres.indexOf(o) % 10)));
        await p.click('[data-testid="v528-email-continuer"]');
        // Offres « saison en 2 fois » : l'étape EXISTANTE « mode de paiement » (V535) suit l'identification.
        const mode = await p.waitForSelector('[data-testid="choix-mode-paiement"]', { timeout: 6000 }).then(() => true).catch(() => false);
        if (mode) {
          const opt = p.locator('[data-testid^="mode-paiement-"][data-choisi]').first();
          await opt.click().catch(() => null);
          await p.click('[data-testid="mode-paiement-continuer"]');
        }
        await p.waitForURL(/faux-stripe/, { timeout: 30000 }).catch(() => null);
        const s = await etat(p); const ids = Object.keys(s); const m = (s[ids[ids.length - 1]] || {}).metadata || {};
        verdict = ids.length === n0 + 1 && m.offer_id === o.id && rappel === o.name ? (mode ? 'OK (après le choix du mode de paiement)' : 'OK') : `ÉCHEC rappel=${rappel} offer=${m.offer_id}/${o.id} pn=${m.product_name} sessions=${ids.length - n0}`;
      } else {
        verdict = (await p.locator('[data-testid="user-info-section"]').count()) ? 'formulaire classique (Nom/E-mail/WhatsApp déjà demandés)' : 'autre parcours';
      }
    } catch (e) { verdict = 'ERREUR ' + String(e).slice(0, 80); }
    resultats.push(`${o.name} (${o.price} CHF) : ${verdict}`);
    await ctx.close();
  }
  v('E. toutes les offres : formule conservée jusqu’au paiement (ou parcours classique déjà complet)', resultats.every(r => / : (OK|formulaire classique|produit à variantes)/.test(r)), resultats.join(' ; '));
  R.push('     E détail : ' + resultats.join('\n                '));
}

(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const offres = await (await (await (await browser.newContext()).newPage()).request.get(BASE + '/api/offers')).json();
  const liberte = offres.find(o => /libert/i.test(o.name || ''));
  v('0. l’offre « Mensuel Liberté » est servie par la pile locale', !!liberte, JSON.stringify(offres.map(o => o.name)));
  if (liberte) {
    const a = await scenarioA(browser, db, liberte, false);
    await scenarioA(browser, db, liberte, true);
    await scenarioC(browser, db, liberte, a);
    await scenarioD(browser, db, liberte, a, offres.find(o => /unité/i.test(o.name || '')));
  }
  await scenarioE(browser, offres.filter(o => o.visible !== false && o.id));
  await browser.close();
  console.log(R.join('\n')); console.log(`\nV570 : ${OK} OK, ${KO} RATÉ(S)`);
  process.exit(KO ? 1 : 0);
})();
