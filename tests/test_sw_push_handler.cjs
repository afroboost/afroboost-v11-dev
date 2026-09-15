// V525: banc du gestionnaire `push` du Service Worker EXISTANT (frontend/public/sw.js).
// Charge sw.js dans un faux `self`, rejoue l'événement push avec le payload EXACT
// produit par server.py (_corps_payload) et par le push de test, et vérifie :
// showNotification appelé exactement 1 fois, titre/corps corrects, aucune exception.
// Lancer : node tests/test_sw_push_handler.cjs
const fs = require('fs'), path = require('path'), vm = require('vm'), assert = require('assert');
const src = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'public', 'sw.js'), 'utf8');

function bancSW() {
  const handlers = {}, shown = [];
  const self = {
    addEventListener: (t, fn) => { (handlers[t] = handlers[t] || []).push(fn); },
    registration: { showNotification: (title, options) => { shown.push({ title, options }); return Promise.resolve(); },
                    pushManager: { subscribe: () => Promise.resolve(null) } },
    clients: { claim: () => Promise.resolve(), matchAll: () => Promise.resolve([]), openWindow: () => Promise.resolve(null) },
    skipWaiting: () => Promise.resolve(),
    location: { origin: 'https://afroboost.com' },
  };
  self.self = self;
  const ctx = { self, caches: { open: () => Promise.resolve({ match: () => Promise.resolve(null), addAll: () => Promise.resolve(), put: () => Promise.resolve() }), keys: () => Promise.resolve([]), delete: () => Promise.resolve(true) },
                fetch: () => Promise.resolve({ ok: true, clone() { return this; } }), URL, Promise, console, setTimeout, Response, Request };
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  vm.runInContext(src, ctx, { filename: 'sw.js' });
  return { handlers, shown };
}

async function rejouer(payload) {
  const { handlers, shown } = bancSW();
  assert.ok(handlers.push && handlers.push.length === 1, 'un seul gestionnaire push');
  let attendu = null, erreur = null;
  const event = { data: { json: () => JSON.parse(JSON.stringify(payload)), text: () => JSON.stringify(payload) },
                  waitUntil: (p) => { attendu = p; } };
  try { handlers.push[0](event); } catch (e) { erreur = e; }
  assert.strictEqual(erreur, null, 'aucune exception synchrone');
  assert.ok(attendu, 'event.waitUntil appelé');
  await attendu;
  return shown;
}

(async () => {
  let ok = 0;
  // 1) payload EXACT de server.py (_corps_payload) — réservation coach
  const prod = { title: 'Nouvelle réservation', body: 'ruth-esther — Session Cardio, mer. 16/09 18:30', icon: '/logo192.png',
                 badge: '/notification-badge-96.png', url: '/?openChat=true', session_id: null, data: { type: 'reservation' },
                 timestamp: '2026-09-15T18:10:19.355904+00:00' };
  let s = await rejouer(prod);
  assert.strictEqual(s.length, 1, 'showNotification 1 fois (prod)');
  assert.strictEqual(s[0].title, prod.title); assert.strictEqual(s[0].options.body, prod.body);
  assert.strictEqual(s[0].options.tag, 'afroboost-push'); assert.strictEqual(s[0].options.silent, false);
  assert.strictEqual(JSON.stringify(s[0].options.actions), JSON.stringify([{ action: 'open', title: 'Voir' }, { action: 'close', title: 'Fermer' }]));
  ok++; console.log('OK 1 payload serveur (réservation) → showNotification ×1, titre/corps exacts');
  // 2) payload EXACT du push de test envoyé à Bassi le 15/09 20:12 UTC
  const test = { title: 'Test notification Afroboost', body: 'Si tu vois ce message, les notifications Push fonctionnent correctement.',
                 icon: '/logo192.png', badge: '/notification-badge-96.png', url: '/', data: { type: 'test_push_bassi' }, tag: 'afroboost-test-push' };
  s = await rejouer(test);
  assert.strictEqual(s.length, 1); assert.strictEqual(s[0].title, test.title); assert.strictEqual(s[0].options.body, test.body);
  assert.strictEqual(s[0].options.tag, 'afroboost-test-push');
  ok++; console.log('OK 2 payload du push de test → showNotification ×1');
  // 3) payload rappel RV2 (actions + tag par cours) — le rendu validé le 09/09
  const rappel = { title: '🎧 AFROBOOST CE SOIR — 18H30', body: 'Ta place est réservée. Valangines.', url: 'https://afroboost.com/espace/AF9A4415C8',
                   tag: 'afroboost-cours-64b4c975', actions: [{ action: 'open', title: '👟 Voir mon cours' }], vibrate: [200, 100, 200], requireInteraction: true, data: {} };
  s = await rejouer(rappel);
  assert.strictEqual(s.length, 1); assert.strictEqual(s[0].options.tag, 'afroboost-cours-64b4c975');
  assert.strictEqual(s[0].options.requireInteraction, true); assert.strictEqual(s[0].options.actions.length, 1);
  ok++; console.log('OK 3 payload rappel (actions/tag/requireInteraction) → showNotification ×1');
  // 4) payload sans AUCUN champ attendu / non JSON → notification par défaut, jamais d'échec
  s = await rejouer({});
  assert.strictEqual(s.length, 1); assert.strictEqual(s[0].title, 'Afroboost');
  const { handlers, shown } = bancSW();
  handlers.push[0]({ data: { json: () => { throw new Error('pas du JSON'); }, text: () => 'brut' }, waitUntil: async (p) => { await p; } });
  await new Promise(r => setTimeout(r, 10));
  assert.strictEqual(shown.length, 1); assert.strictEqual(shown[0].options.body, 'brut');
  ok++; console.log('OK 4 payload vide / non-JSON → notification par défaut, aucune exception');
  console.log(`\n${ok}/4 verts — sw.js ${(src.match(/CACHE_NAME = '([^']+)'/) || [])[1]}`);
})().catch(e => { console.error('ROUGE:', e.message); process.exit(1); });
