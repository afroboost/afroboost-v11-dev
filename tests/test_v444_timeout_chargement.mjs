/**
 * V444 — une requete qui PEND ne laisse plus sa section muette.
 *
 * `avecDelai` et `appliquer` sont EXTRAITES du vrai CoachDashboard.js et
 * executees telles quelles. Le delai de production (15 s) est celui du fichier ;
 * les tests le surchargent par le 3e parametre pour rester rapides — c'est bien
 * le meme code qui tourne.
 *
 * Aucun reseau, aucun DOM, aucun React.
 * node tests/test_v444_timeout_chargement.mjs
 */
import fs from 'fs';
import path from 'path';
import { execFileSync } from 'child_process';
import { fileURLToPath } from 'url';

const RACINE = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const CHEMIN = 'frontend/src/components/CoachDashboard.js';
const SRC = fs.readFileSync(path.join(RACINE, CHEMIN), 'utf8');

const resultats = [];
const verifier = (nom, cond, detail = '') => resultats.push([nom, !!cond, detail]);

/** Extrait un bloc `const <nom> = ` … jusqu'a l'accolade equilibree. */
function extraire(nom, amorce) {
  const debut = SRC.indexOf(amorce);
  if (debut < 0) throw new Error(`${nom} introuvable dans ${CHEMIN}`);
  let i = SRC.indexOf('{', debut), prof = 0, fin = -1;
  for (; i < SRC.length; i++) {
    if (SRC[i] === '{') prof++;
    else if (SRC[i] === '}') { prof--; if (prof === 0) { fin = i + 1; break; } }
  }
  return SRC.slice(debut, fin) + ';';
}

const srcDelai = extraire('avecDelai', 'const avecDelai = (promesse, nom, delai = DELAI_CHARGE_MS) =>');
const srcAppliquer = extraire('appliquer', 'const appliquer = (nom, reponse, poser) => {');

verifier('0. le delai de production est bien 15 s dans le fichier',
  /const DELAI_CHARGE_MS = 15000;/.test(SRC), 'constante absente ou modifiee');
// La declaration s'ecrit `avecDelai = (`, elle ne compte donc pas dans ce motif :
// on attend exactement 7 APPELS, un par source.
verifier('0b. les 7 sources sont enrobees par avecDelai',
  (SRC.match(/avecDelai\(/g) || []).length === 7,
  String((SRC.match(/avecDelai\(/g) || []).length));

function bac() {
  const echecs = [];
  const journal = [];
  // On garde TOUS les arguments : le vrai code journalise un libelle en 1er et
  // l'erreur en 2nd — ne capturer que le premier masquerait le motif reel.
  const console = { error: (...a) => journal.push(a) };
  // eslint-disable-next-line no-new-func
  const f = new Function('echecs', 'console', 'DELAI_CHARGE_MS',
    `${srcDelai}\n${srcAppliquer}\nreturn { avecDelai, appliquer };`)(echecs, console, 15000);
  return { ...f, echecs, journal };
}

const pend = () => new Promise(() => {});                 // ne se regle JAMAIS
const erreurHttp = (code) => { const e = new Error(`Request failed with status code ${code}`); e.response = { status: code }; return e; };

/** Rejoue le vrai enchainement : allSettled sur des sources enrobees, puis application. */
async function charger(sources, delai) {
  const b = bac();
  const reponses = await Promise.allSettled(
    sources.map((s) => b.avecDelai(s.promesse, s.nom, delai)));
  const poses = {};
  sources.forEach((s, i) => b.appliquer(s.nom, reponses[i], (r) => { poses[s.nom] = r.data; }));
  return { poses, echecs: b.echecs, journal: b.journal };
}

const t0 = Date.now();

// --- 1. reponse rapide -> comportement historique, aucun echec
{
  const { poses, echecs } = await charger([
    { nom: 'Réservations', promesse: Promise.resolve({ data: ['r1'] }) },
    { nom: 'Codes promo', promesse: Promise.resolve({ data: ['c1', 'c2'] }) },
  ], 500);
  verifier('1. reponse rapide -> section alimentee', JSON.stringify(poses['Réservations']) === '["r1"]', JSON.stringify(poses));
  verifier('1b. reponse rapide -> aucun echec', echecs.length === 0, JSON.stringify(echecs));
  verifier('1c. le succes n\'est pas retarde par l\'echeance', Date.now() - t0 < 400, `${Date.now() - t0} ms`);
}

// --- 2. 403 -> section en erreur, les autres visibles
{
  const { poses, echecs } = await charger([
    { nom: 'Réservations', promesse: Promise.resolve({ data: ['r1', 'r2'] }) },
    { nom: 'Codes promo', promesse: Promise.reject(erreurHttp(403)) },
    { nom: 'Cours', promesse: Promise.resolve({ data: ['c'] }) },
  ], 500);
  verifier('2. 403 -> la section est en echec', JSON.stringify(echecs) === '["Codes promo"]', JSON.stringify(echecs));
  verifier('2b. 403 -> Reservations restent visibles', JSON.stringify(poses['Réservations']) === '["r1","r2"]', JSON.stringify(poses));
  verifier('2c. 403 -> Cours restent visibles', JSON.stringify(poses['Cours']) === '["c"]', JSON.stringify(poses));
}

// --- 3. 500 -> idem
{
  const { poses, echecs } = await charger([
    { nom: 'Réservations', promesse: Promise.reject(erreurHttp(500)) },
    { nom: 'Codes promo', promesse: Promise.resolve({ data: ['c1'] }) },
  ], 500);
  verifier('3. 500 -> la section est en echec', JSON.stringify(echecs) === '["Réservations"]', JSON.stringify(echecs));
  verifier('3b. 500 -> Codes promo restent visibles', JSON.stringify(poses['Codes promo']) === '["c1"]', JSON.stringify(poses));
}

// --- 4. requete qui PEND -> echec visible au lieu du silence  (le coeur du lot)
{
  const debut = Date.now();
  const { poses, echecs, journal } = await charger([
    { nom: 'Réservations', promesse: pend() },
    { nom: 'Codes promo', promesse: Promise.resolve({ data: ['c1'] }) },
    { nom: 'Cours', promesse: Promise.resolve({ data: ['c'] }) },
  ], 60);
  const duree = Date.now() - debut;
  verifier('4. requete suspendue -> section en echec', JSON.stringify(echecs) === '["Réservations"]', JSON.stringify(echecs));
  verifier('4b. l\'echeance est bien respectee', duree >= 55 && duree < 900, `${duree} ms`);
  const motif = String((journal[0] && journal[0][1] && journal[0][1].message) || '');
  verifier('4c. le motif nomme la section et le delai',
    /Réservations : aucune reponse en 60 ms/.test(motif), JSON.stringify(motif));
  verifier('4e. le libelle du journal nomme aussi la section',
    /Réservations/.test(String(journal[0] && journal[0][0])), JSON.stringify(String(journal[0] && journal[0][0])));
  verifier('4d. AUCUNE autre section n\'est videe',
    JSON.stringify(poses['Codes promo']) === '["c1"]' && JSON.stringify(poses['Cours']) === '["c"]', JSON.stringify(poses));
}

// --- 5. les 7 sources suspendues -> 7 echecs nommes, rien de silencieux
{
  const sections = ['Réservations', 'Cours', 'Offres', 'Utilisateurs', 'Liens de paiement', 'Vitrine', 'Codes promo'];
  const { echecs, journal } = await charger(sections.map((n) => ({ nom: n, promesse: pend() })), 40);
  verifier('5. les 7 sections suspendues sont toutes signalees', echecs.length === 7, JSON.stringify(echecs));
  verifier('5b. chacune est aussi journalisee', journal.length === 7, String(journal.length));
}

// --- 6. une reponse tardive APRES l'echeance ne ressuscite pas la section
{
  let resoudre;
  const tardive = new Promise((r) => { resoudre = r; });
  const b = bac();
  const reponses = await Promise.allSettled([b.avecDelai(tardive, 'Réservations', 40)]);
  let pose = null;
  b.appliquer('Réservations', reponses[0], (r) => { pose = r.data; });
  resoudre({ data: ['trop tard'] });
  await new Promise((r) => setTimeout(r, 30));
  verifier('6. reponse arrivee apres l\'echeance -> section toujours en echec',
    JSON.stringify(b.echecs) === '["Réservations"]', JSON.stringify(b.echecs));
  verifier('6b. et l\'etat n\'est pas ecrase apres coup', pose === null, JSON.stringify(pose));
}

// --- 7. le minuteur est desamorce : aucun compte a rebours ne survit au succes
{
  const b = bac();
  const avant = process._getActiveHandles ? process._getActiveHandles().length : -1;
  await b.avecDelai(Promise.resolve({ data: [] }), 'Cours', 30000);
  await new Promise((r) => setImmediate(r));
  const apres = process._getActiveHandles ? process._getActiveHandles().length : -1;
  verifier('7. le minuteur est annule des que la reponse arrive', apres <= avant, `${avant} -> ${apres}`);
}

// --- 8. AUCUNE ECRITURE NOUVELLE, AUCUN AUTOSAVE SUPPLEMENTAIRE
{
  const blocDe = (rev) => {
    const txt = rev
      ? execFileSync('git', ['show', `${rev}:${CHEMIN}`], { cwd: RACINE, maxBuffer: 64 * 1024 * 1024 }).toString()
      : SRC;
    const d = txt.indexOf('const loadData = async');
    return txt.slice(d, txt.indexOf('loadData();', d));
  };
  const compter = (bloc, re) => (bloc.match(re) || []).length;
  const avant = blocDe('2cd1e75');
  const apres = blocDe(null);

  for (const [libelle, re] of [
    ['axios.post', /axios\.post\(/g], ['axios.put', /axios\.put\(/g],
    ['axios.delete', /axios\.delete\(/g], ['axios.patch', /axios\.patch\(/g],
    ['fetch', /fetch\(/g],
  ]) {
    verifier(`8. aucune ecriture nouvelle au chargement (${libelle} : inchange)`,
      compter(avant, re) === compter(apres, re), `${compter(avant, re)} -> ${compter(apres, re)}`);
  }
  for (const [libelle, re] of [['setConcept', /setConcept\(/g], ['setPaymentLinks', /setPaymentLinks\(/g]]) {
    verifier(`8b. aucun autosave supplementaire declenche (${libelle} : inchange)`,
      compter(avant, re) === compter(apres, re), `${compter(avant, re)} -> ${compter(apres, re)}`);
  }
  verifier('8c. le nombre d\'appels axios.get au chargement est inchange',
    compter(avant, /axios\.get\(/g) === compter(apres, /axios\.get\(/g),
    `${compter(avant, /axios\.get\(/g)} -> ${compter(apres, /axios\.get\(/g)}`);
  verifier('8d. sur echeance, la section n\'est PAS appliquee (donc aucun setState, donc aucun autosave)',
    /if \(reponse\.status !== 'fulfilled'\)/.test(srcAppliquer), srcAppliquer.slice(0, 60));
}

const passes = resultats.filter(([, r]) => r).length;
console.log('='.repeat(78));
for (const [nom, r, detail] of resultats) console.log((r ? '  PASS  ' : '  FAIL  ') + nom + (r ? '' : '   -> ' + detail));
console.log('='.repeat(78));
console.log(`${passes}/${resultats.length} verifications`);
process.exit(passes === resultats.length ? 0 : 1);
