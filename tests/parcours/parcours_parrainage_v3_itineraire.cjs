// V556 — contrôle ciblé : hauteur du lien « Itinéraire » (≥ 44 px), 6 tailles, 3 écrans.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const BUILD = process.env.BUILD;
const OCC = new Date(Date.now() + 3 * 864e5).toISOString();
const PASS = (chain) => ({
  status: 'waiting', sponsor_first_name: 'Bassi', sponsor_display_name: 'Bassi', sponsor_photo_url: null,
  course: { name: 'Afro Cardio', time: '18:30', locationName: 'Salle Nord', mapsUrl: 'https://maps.example/x' },
  occurrence: OCC, expired: false, offer: { id: 'o1', name: 'Essai gratuit', price: 0 }, offers: [{ id: 'o1', name: 'Essai gratuit', price: 0 }],
  version: 1, occurrences: [], chain_required: chain, chain: { exists: false, shared: false },
});
const JOIN = { status: 'unlocked', tickets: [], sponsor_first_name: 'Bassi',
  course: { name: 'Afro Cardio', locationName: 'Salle Nord', mapsUrl: 'https://maps.example/x' }, occurrence: OCC,
  offer: { id: 'o1', name: 'Essai gratuit', price: 0 }, version: 2 };
const TYPES = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml', '.ico': 'image/x-icon' };
(async () => {
  const b = await chromium.launch();
  const tailles = [[360, 640, 1], [390, 844, 1], [414, 896, 1], [430, 932, 1], [1280, 800, 0], [1440, 900, 0]];
  const res = []; let ko = 0;
  for (const [w, h, mob] of tailles) {
    for (const ecran of ['ancien-formulaire', 'wizard-etape1', 'succes']) {
      const ctx = await b.newContext({ viewport: { width: w, height: h }, isMobile: !!mob, hasTouch: !!mob });
      const chain = ecran === 'wizard-etape1';
      await ctx.route('**/*', async (route) => {
        const u = new URL(route.request().url());
        if (!/^(127\.0\.0\.1|localhost)$/.test(u.hostname)) return route.abort();      // rien vers l'extérieur
        if (u.pathname.startsWith('/api/referral/pass/T0/join')) return route.fulfill({ json: JOIN });
        if (u.pathname === '/api/referral/pass/T0') return route.fulfill({ json: PASS(chain) });
        if (u.pathname.startsWith('/api/')) return route.fulfill({ json: {} });
        let f = path.join(BUILD, u.pathname);
        if (!fs.existsSync(f) || fs.statSync(f).isDirectory()) f = path.join(BUILD, 'index.html');
        return route.fulfill({ body: fs.readFileSync(f), contentType: TYPES[path.extname(f)] || 'application/octet-stream' });
      });
      const p = await ctx.newPage();
      await p.goto('http://127.0.0.1:9/duo/T0');
      if (ecran === 'wizard-etape1') {
        await p.waitForSelector('[data-testid=wf-etape-1]');
      } else {
        await p.waitForSelector('[data-testid=invitation-seance]');
        if (ecran === 'succes') {
          const conv = p.locator('[data-testid=offre-convient]'); if (await conv.count()) await conv.click();
          await p.fill('[data-testid=invitation-prenom]', 'Aminata');
          await p.fill('[data-testid=invitation-email]', 'a@exemple.test');
          await p.fill('[data-testid=invitation-whatsapp]', '+41790000000');
          await p.check('[data-testid=invitation-consent]');
          await p.click('[data-testid=invitation-rejoindre]');
          await p.waitForSelector('[data-testid=invitation-succes]');
        }
      }
      await p.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => null))));
      const el = p.locator('[data-testid=invitation-itineraire]').first();
      const hauteur = (await el.count()) ? (await el.boundingBox()).height : -1;
      const ok = hauteur >= 44; if (!ok) ko++;
      res.push(`${w}x${h} ${ecran.padEnd(18)} ${hauteur.toFixed(1)} px ${ok ? 'OK' : 'ÉCHEC'}`);
      if (w === 390 && ecran === 'succes') { await p.waitForTimeout(1500); console.log('opacite carte', await p.locator('[data-testid=invitation-seance]').evaluate((e) => getComputedStyle(e).opacity)); } if (w === 390 && ecran === 'succes') await p.screenshot({ path: path.join(process.env.CAPT, '390x844-succes-itineraire.png'), fullPage: true });
      await ctx.close();
    }
  }
  await b.close();
  console.log(res.join('\n')); console.log(`${res.length - ko} / ${res.length} au vert`);
  process.exit(ko ? 1 : 0);
})();
