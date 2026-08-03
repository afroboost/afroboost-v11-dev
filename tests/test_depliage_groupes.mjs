/**
 * V366 — dépliage des groupes en personnes (duplication + réédition).
 *
 * Test UNITAIRE hors ligne : aucune connexion réseau, aucune base, aucun envoi.
 * Il porte sur le VRAI fichier livré (frontend/src/utils/deplierGroupes.js), chargé
 * en retirant simplement les mots-clés `export` — le dépôt n'a aucune chaîne de test
 * JavaScript, et en installer une n'était pas demandé.
 *
 * MODE D'EMPLOI
 *     node tests/test_depliage_groupes.mjs
 *
 * CE QUI EST VERROUILLÉ
 *   1. Une campagne ne ciblant QU'UN GROUPE est dépliée en vraies personnes —
 *      c'est le cas de « Silent Lakeside – Rappel J-2 », qui n'écrivait à personne.
 *   2. L'identifiant de groupe ne subsiste JAMAIS dans le résultat.
 *   3. Une campagne ciblant déjà des personnes n'est PAS gonflée des membres du
 *      groupe (elle enverrait à des gens jamais choisis).
 *   4. Si les groupes sont indisponibles, la liste d'origine est rendue INTACTE
 *      (on ne fabrique pas une campagne vide).
 */
import { copyFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ICI = dirname(fileURLToPath(import.meta.url));
const SOURCE = join(ICI, '..', 'frontend', 'src', 'utils', 'deplierGroupes.js');

// Le fichier est un module ESM, mais son extension .js le fait lire comme CommonJS
// (frontend/package.json ne déclare pas "type": "module"). On en prend donc une copie
// EXACTE en .mjs, que Node importe nativement : le test porte bien sur le fichier
// livré, sans évaluation dynamique de code.
const copie = join(mkdtempSync(join(tmpdir(), 'v366-')), 'deplierGroupes.mjs');
copyFileSync(SOURCE, copie);
const { deplierTargetIds, estIdentifiantDeGroupe } = await import(pathToFileURL(copie).href);

// Jeu d'essai : un groupe de 4 membres, calqué sur la vraie structure renvoyée par
// GET /api/chat/groups (identifiant de session « grp_ » + 8 premiers caractères).
const GROUPES = [
  { id: 'ed0b28f8-1111-2222-3333-444455556666',
    name: 'Contacts WhatsApp',
    member_ids: ['p-ana', 'p-marc', 'p-leila', 'p-tom'] },
  { id: 'ffffffff-0000-0000-0000-000000000000', name: 'Vide', member_ids: [] }
];

let echecs = 0;
function verifier(titre, condition, detail) {
  if (condition) {
    console.log(`✅ PASS  ${titre}`);
  } else {
    echecs += 1;
    console.log(`❌ FAIL  ${titre}\n         → ${detail}`);
  }
}

// 1. Le cas réellement cassé : la campagne du 7 août.
{
  const r = deplierTargetIds(['grp_ed0b28f8'], GROUPES);
  verifier('une campagne ne ciblant QUE le groupe est dépliée en personnes',
    r.deplie === true && r.membres === 4 &&
    JSON.stringify(r.ids) === JSON.stringify(['p-ana', 'p-marc', 'p-leila', 'p-tom']),
    `obtenu ${JSON.stringify(r)}`);

  verifier("l'identifiant de groupe ne subsiste pas dans le résultat",
    r.ids.every(id => !estIdentifiantDeGroupe(id)),
    `obtenu ${JSON.stringify(r.ids)}`);
}

// 2. L'ordre des membres est conservé (il porte l'ordre d'ajout au groupe).
{
  const r = deplierTargetIds(['grp_ed0b28f8'], GROUPES);
  verifier("l'ordre des membres est conservé",
    JSON.stringify(r.ids) === JSON.stringify(GROUPES[0].member_ids),
    `obtenu ${JSON.stringify(r.ids)}`);
}

// 3. Prudence : une campagne qui cible déjà des personnes n'est pas gonflée.
{
  const depart = ['grp_ed0b28f8', 'p-ana', 'p-zoe'];
  const r = deplierTargetIds(depart, GROUPES);
  verifier('une campagne ciblant déjà des personnes reste inchangée',
    r.deplie === false && JSON.stringify(r.ids) === JSON.stringify(depart),
    `obtenu ${JSON.stringify(r)}`);
}

// 4. Groupes indisponibles (403, réseau coupé) : liste d'origine intacte + échec signalé.
{
  const r = deplierTargetIds(['grp_ed0b28f8'], []);
  verifier('groupes indisponibles : la liste d’origine est rendue intacte',
    r.deplie === false && r.echec === true &&
    JSON.stringify(r.ids) === JSON.stringify(['grp_ed0b28f8']),
    `obtenu ${JSON.stringify(r)}`);
}

// 5. Groupe vide : on ne renvoie pas une campagne sans destinataire.
{
  const r = deplierTargetIds(['grp_ffffffff'], GROUPES);
  verifier('groupe vide : la liste d’origine est rendue intacte',
    r.deplie === false && r.echec === true && r.ids.length === 1,
    `obtenu ${JSON.stringify(r)}`);
}

// 6. Aucune ligne de groupe : rien ne bouge.
{
  const depart = ['p-ana', 'p-marc'];
  const r = deplierTargetIds(depart, GROUPES);
  verifier('sans groupe, la liste est rendue telle quelle',
    r.deplie === false && JSON.stringify(r.ids) === JSON.stringify(depart),
    `obtenu ${JSON.stringify(r)}`);
}

// 7. Doublons : un membre présent deux fois n'est compté qu'une fois.
{
  const groupesAvecDoublon = [{ id: 'ed0b28f8-aaaa', member_ids: ['p-ana', 'p-ana', 'p-marc'] }];
  const r = deplierTargetIds(['grp_ed0b28f8'], groupesAvecDoublon);
  verifier('les doublons de membres sont supprimés',
    JSON.stringify(r.ids) === JSON.stringify(['p-ana', 'p-marc']),
    `obtenu ${JSON.stringify(r.ids)}`);
}

// 8. Entrées vides / absurdes : pas d'exception.
{
  const a = deplierTargetIds([], GROUPES);
  const b = deplierTargetIds(null, GROUPES);
  const c = deplierTargetIds(['grp_inconnu'], GROUPES);
  verifier('entrées vides ou inconnues : aucune exception, liste cohérente',
    a.ids.length === 0 && b.ids.length === 0 && c.ids.length === 1 && c.echec === true,
    `obtenu ${JSON.stringify([a, b, c])}`);
}

console.log(`\nV366 : ${echecs === 0 ? 'tous les tests passent' : `${echecs} échec(s)`}`);
process.exit(echecs === 0 ? 0 : 1);
