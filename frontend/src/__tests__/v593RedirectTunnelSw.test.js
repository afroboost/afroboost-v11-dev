// V593 — la fin du tunnel ne doit plus être annulée par le rechargement « mise à jour du SW ».
//
// On EXÉCUTE le vrai bloc <script> de public/index.html (celui de V121/V130) avec un
// navigateur simulé, au lieu de chercher des mots dans le fichier : c'est le comportement
// qui est figé, pas l'écriture.
//
// Scénario mesuré en local (B1.6, 08/10/2026) : première visite -> le ChatWidget enregistre
// le SW AVANT `load` -> l'ancien garde-fou lisait `controller` au `load` et se croyait en
// « mise à jour » -> au clic final du tunnel, un nouveau SW prend la main pendant la
// navigation vers /?offre=…&reserver=1 -> `location.reload()` annulait cette navigation.
const fs = require('fs');
const path = require('path');

const HTML = fs.readFileSync(path.join(__dirname, '..', '..', 'public', 'index.html'), 'utf8');
const BLOC = (() => {
  const scripts = HTML.split('<script>').map((s) => s.split('</script>')[0]);
  const b = scripts.find((s) => s.includes('V121: Register SW'));
  if (!b) throw new Error('bloc SW introuvable dans index.html');
  return b;
})();

function monter({ controleurAuChargement }) {
  const ecouteurs = {};
  const swEcouteurs = {};
  const on = (table) => (type, fn) => { (table[type] = table[type] || []).push(fn); };
  const emettre = (table, type, evt) => (table[type] || []).forEach((fn) => fn(evt || {}));
  const reload = jest.fn();
  const reg = { update: jest.fn(), waiting: null, addEventListener: () => {}, scope: '/' };
  const sw = {
    controller: controleurAuChargement ? {} : null,
    addEventListener: on(swEcouteurs),
    register: () => Promise.resolve(reg),
    getRegistration: () => Promise.resolve(reg),
  };
  const fenetre = { addEventListener: on(ecouteurs), location: { reload } };
  const doc = { addEventListener: () => {}, visibilityState: 'visible' };
  // eslint-disable-next-line no-new-func
  new Function('window', 'navigator', 'document', 'console', 'setInterval', BLOC)(
    fenetre, { serviceWorker: sw }, doc, { log: () => {} }, () => 0);
  return {
    reload, sw,
    fenetre: (type) => emettre(ecouteurs, type),
    swEvt: (type, evt) => emettre(swEcouteurs, type, evt),
  };
}

test('1re visite : le SW enregistré par le ChatWidget AVANT load ne réarme pas le rechargement', () => {
  const p = monter({ controleurAuChargement: false });
  p.sw.controller = {};            // le ChatWidget a installé + pris la main avant `load`
  p.fenetre('load');
  p.fenetre('beforeunload');       // fin du tunnel : navigation vers /?offre=…&reserver=1
  p.swEvt('controllerchange');     // un nouveau SW prend la main pendant la navigation
  p.swEvt('message', { data: { type: 'SW_UPDATED', version: 'x' } });
  expect(p.reload).not.toHaveBeenCalled();
});

test('1re visite, même sans navigation en cours : aucun rechargement', () => {
  const p = monter({ controleurAuChargement: false });
  p.sw.controller = {};
  p.fenetre('load');
  p.swEvt('controllerchange');
  expect(p.reload).not.toHaveBeenCalled();
});

test('visiteur revenu : une navigation en cours n’est jamais annulée par la mise à jour', () => {
  const p = monter({ controleurAuChargement: true });
  p.fenetre('load');
  p.fenetre('beforeunload');
  p.swEvt('controllerchange');
  expect(p.reload).not.toHaveBeenCalled();
});

test('visiteur revenu, page posée : la mise à jour recharge toujours (comportement V130 conservé)', () => {
  const p = monter({ controleurAuChargement: true });
  p.fenetre('load');
  p.swEvt('controllerchange');
  expect(p.reload).toHaveBeenCalledTimes(1);
});

test('retour par le cache arrière (pageshow) : le rechargement de mise à jour est réarmé', () => {
  const p = monter({ controleurAuChargement: true });
  p.fenetre('load');
  p.fenetre('pagehide');
  p.fenetre('pageshow');
  p.swEvt('message', { data: { type: 'SW_UPDATED', version: 'x' } });
  expect(p.reload).toHaveBeenCalledTimes(1);
});
