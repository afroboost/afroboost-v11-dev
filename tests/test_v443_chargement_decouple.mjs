/**
 * V443 — preuve COMPORTEMENTALE du decouplage du chargement du dashboard.
 *
 * La fonction `appliquer` est EXTRAITE du vrai CoachDashboard.js et executee telle
 * quelle. On ne la reecrit pas : si quelqu'un la modifie un jour, ce test suit.
 *
 * Aucun reseau, aucun DOM, aucun React. `node tests/test_v443_chargement_decouple.mjs`
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const RACINE = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const SRC = fs.readFileSync(path.join(RACINE, 'frontend/src/components/CoachDashboard.js'), 'utf8');

const resultats = [];
const verifier = (nom, cond, detail = '') => resultats.push([nom, !!cond, detail]);

/** Extrait `const appliquer = (…) => { … };` du fichier reel. */
function extraireAppliquer() {
  const debut = SRC.indexOf('const appliquer = (nom, reponse, poser) => {');
  if (debut < 0) throw new Error('fonction `appliquer` introuvable dans CoachDashboard.js');
  let i = SRC.indexOf('{', debut), profondeur = 0, fin = -1;
  for (; i < SRC.length; i++) {
    if (SRC[i] === '{') profondeur++;
    else if (SRC[i] === '}') { profondeur--; if (profondeur === 0) { fin = i + 1; break; } }
  }
  if (fin < 0) throw new Error('accolade fermante introuvable');
  return SRC.slice(debut, fin) + ';';
}

const source = extraireAppliquer();
verifier('0. la fonction est bien extraite du fichier reel', source.includes('reponse.status'), source.slice(0, 60));

// Bac a sable : `echecs` et une console muette, comme dans le composant.
function nouveauBac() {
  const echecs = [];
  const journal = [];
  const console = { error: (...a) => journal.push(a[0]) };
  // eslint-disable-next-line no-new-func
  const appliquer = new Function('echecs', 'console', `${source} return appliquer;`)(echecs, console);
  return { appliquer, echecs, journal };
}

const ok = (v) => ({ status: 'fulfilled', value: v });
const ko = (r) => ({ status: 'rejected', reason: r });

// --- 1. une source qui REUSSIT alimente son etat
{
  const { appliquer, echecs } = nouveauBac();
  let pose = null;
  appliquer('Réservations', ok({ data: { data: [1, 2, 3], pagination: { total: 3 } } }), (r) => { pose = r.data.data; });
  verifier('1. source OK -> etat alimente', JSON.stringify(pose) === '[1,2,3]', JSON.stringify(pose));
  verifier('1b. source OK -> aucun echec enregistre', echecs.length === 0, JSON.stringify(echecs));
}

// --- 2. une source qui ECHOUE n'empeche pas les autres  (le coeur du lot)
{
  const { appliquer, echecs } = nouveauBac();
  let reservations = null, codes = null, users = null;
  appliquer('Réservations', ok({ data: { data: ['r1'], pagination: {} } }), (r) => { reservations = r.data.data; });
  appliquer('Utilisateurs', ko(new Error('403 Forbidden')), (r) => { users = r.data; });
  appliquer('Codes promo', ok({ data: ['c1', 'c2'] }), (r) => { codes = r.data; });
  verifier('2. users echoue -> Reservations restent alimentees',
    JSON.stringify(reservations) === '["r1"]', JSON.stringify(reservations));
  verifier('2b. users echoue -> Codes promo restent alimentes',
    JSON.stringify(codes) === '["c1","c2"]', JSON.stringify(codes));
  verifier('2c. users reste vide, et lui seul', users === null, String(users));
  verifier('2d. l\'echec est enregistre nommement',
    JSON.stringify(echecs) === '["Utilisateurs"]', JSON.stringify(echecs));
}

// --- 3. l'inverse : discount-codes echoue, le reste vit
{
  const { appliquer, echecs } = nouveauBac();
  let reservations = null, cours = null;
  appliquer('Réservations', ok({ data: { data: ['r1', 'r2'], pagination: {} } }), (r) => { reservations = r.data.data; });
  appliquer('Cours', ok({ data: ['c'] }), (r) => { cours = r.data; });
  appliquer('Codes promo', ko(new Error('403')), () => { throw new Error('ne doit pas etre appele'); });
  verifier('3. codes promo echoue -> Reservations visibles',
    JSON.stringify(reservations) === '["r1","r2"]', JSON.stringify(reservations));
  verifier('3b. codes promo echoue -> Cours visibles', JSON.stringify(cours) === '["c"]', JSON.stringify(cours));
  verifier('3c. un seul echec recense', JSON.stringify(echecs) === '["Codes promo"]', JSON.stringify(echecs));
}

// --- 4. une reponse 200 dont l'EXPLOITATION leve n'emporte pas les autres
{
  const { appliquer, echecs } = nouveauBac();
  let codes = null;
  appliquer('Offres', ok({ data: null }), (r) => { r.data.filter(() => true); });   // TypeError
  appliquer('Codes promo', ok({ data: ['c1'] }), (r) => { codes = r.data; });
  verifier('4. un `poser` qui leve est confine',
    JSON.stringify(echecs) === '["Offres"]', JSON.stringify(echecs));
  verifier('4b. la source suivante est quand meme alimentee',
    JSON.stringify(codes) === '["c1"]', JSON.stringify(codes));
}

// --- 5. tout echoue -> les 7 sections sont nommees, aucune silencieuse
{
  const { appliquer, echecs, journal } = nouveauBac();
  const sections = ['Réservations', 'Cours', 'Offres', 'Utilisateurs', 'Liens de paiement', 'Vitrine', 'Codes promo'];
  sections.forEach((s) => appliquer(s, ko(new Error('panne')), () => {}));
  verifier('5. les 7 sections en echec sont nommees', echecs.length === 7, JSON.stringify(echecs));
  verifier('5b. chaque echec est aussi journalise', journal.length === 7, String(journal.length));
}

// --- 6. rien n'est jamais silencieux : un echec produit TOUJOURS une trace
{
  const { appliquer, echecs, journal } = nouveauBac();
  appliquer('Vitrine', ko(new Error('x')), () => {});
  verifier('6. un echec alimente a la fois le bandeau et la console',
    echecs.length === 1 && journal.length === 1, `${echecs.length}/${journal.length}`);
}

const passes = resultats.filter(([, r]) => r).length;
console.log('='.repeat(76));
for (const [nom, r, detail] of resultats) console.log((r ? '  PASS  ' : '  FAIL  ') + nom + (r ? '' : '   -> ' + detail));
console.log('='.repeat(76));
console.log(`${passes}/${resultats.length} verifications`);
process.exit(passes === resultats.length ? 0 : 1);
