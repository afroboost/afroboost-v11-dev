/**
 * P1-c — UNE OFFRE EN AVANT, LES AUTRES DERRIERE UN BOUTON.
 *
 * Lecture STATIQUE des sources : ni navigateur, ni reseau, ni base. Ce banc
 * verrouille ce que le rendu doit dire de lui-meme.
 *
 * CE QU'IL FERME. L'ecran d'apres-essai empilait des cartes de MEME POIDS,
 * distinguees par la seule couleur. Le proprietaire veut une hierarchie : une
 * offre mise en avant, un CTA principal, et les alternatives repliees derriere
 * « Voir les autres options ».
 *
 * CE QU'IL PROTEGE SURTOUT : l'ecran ne DECIDE toujours rien. Il ne cherche pas
 * la recommandee, il ne trie pas, il ne filtre pas — le serveur la place en
 * tete, l'ecran prend `offres[0]` et `offres.slice(1)`. C'est la regle de LOT A
 * (« l'interface n'est jamais une barriere metier »), et elle survit a P1-c.
 *
 *   node tests/test_p1c_ui.mjs
 */
import fs from 'fs';
import path from 'path';

const ICI = path.dirname(new URL(import.meta.url).pathname);
const RACINE = path.resolve(ICI, '..');
const lire = (...p) => fs.readFileSync(path.join(RACINE, ...p), 'utf8');
const ECRAN = lire('frontend', 'src', 'components', 'ConversionApresEssai.js');

const R = [];
const verifier = (nom, cond, detail = '') => R.push([nom, !!cond, detail]);

// --- A. la hierarchie ------------------------------------------------------
verifier('A1. la recommandee est prise EN TETE, sans recherche',
  /offres\[0\]/.test(ECRAN));
verifier('A2. les alternatives sont le RESTE, par tranche — jamais un filtre',
  /\.slice\(1\)/.test(ECRAN));
verifier('A3. AUCUN filtrage cote client (regle LOT A, A5)',
  !/\.filter\(/.test(ECRAN), 'le serveur decide, l\'ecran affiche');
verifier('A4. aucun tri cote client non plus',
  !/\.sort\(/.test(ECRAN));
verifier('A5. l\'ecran ne cherche pas la recommandee lui-meme',
  !/\.find\(/.test(ECRAN));

// --- B. le bouton « Voir les autres options » ------------------------------
verifier('B1. le repli existe et porte un libelle explicite',
  /Voir les autres options/.test(ECRAN));
verifier('B2. il est pilote par un etat, pas par du CSS',
  /useState\(false\)/.test(ECRAN) && /autresOuvertes|voirAutres/.test(ECRAN));
verifier('B3. il porte un marqueur de test',
  /data-testid="conversion-voir-autres"/.test(ECRAN));
verifier('B4. les alternatives portent leur propre marqueur',
  /data-testid="conversion-alternatives"/.test(ECRAN));
verifier('B5. le bloc recommande porte le sien',
  /data-testid="conversion-recommandee"/.test(ECRAN));
verifier('B6. le repli ne s\'affiche QUE s\'il y a des alternatives',
  /autres\.length\s*>\s*0|autres\.length\s*\?/.test(ECRAN));

// --- C. ce que P1-c ne doit PAS casser (invariants LOT A) -----------------
verifier('C1. aucun montant en dur', !/\b(250|150|30|59\.99)\b/.test(ECRAN));
verifier('C2. aucun identifiant d\'offre en dur',
  !/a687ce86|fea0ab6a|484c4519/.test(ECRAN));
verifier('C3. le prix vient du serveur, seulement mis en forme',
  /montant\(o\.price, o\.currency\)/.test(ECRAN));
verifier('C4. les trois gardes de rendu sont intactes, MOT POUR MOT',
  ECRAN.includes('if (!etat || !etat.eligible) return null;')
  && ECRAN.includes('etat.state !== "open" || offres.length === 0')
  && ECRAN.includes('etat.state === "purchased"'));
verifier('C5. l\'achat passe toujours par le serveur',
  /\/conversion\/checkout/.test(ECRAN));
// Le corps REELLEMENT envoye, pas le texte du fichier : le commentaire qui
// explique qu'on n'envoie pas d'origine contient le mot « origine ».
const CORPS_POST = (ECRAN.match(/axios\.post\([\s\S]{0,400}?\)\s*;/) || [''])[0];
verifier('C6. le POST n\'envoie QUE offer_id — aucune URL de retour',
  /offer_id/.test(CORPS_POST)
  && !/return_url|success_url|window\.location/.test(CORPS_POST), CORPS_POST.slice(0, 160));

// --- D. couleurs et icones -------------------------------------------------
const hex = (ECRAN.match(/#[0-9a-fA-F]{6}/g) || []);
verifier('D1. aucune couleur de marque imposee — hex uniquement en repli var()',
  hex.every((h) => h === '#D91CD2' || h === '#fca5a5'), hex.join(' '));
verifier('D2. la couleur du coach pilote la mise en avant',
  /var\(--primary-color/.test(ECRAN));
verifier('D3. aucune emoji comme pictogramme',
  !/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(ECRAN));
verifier('D4. les icones passent par SvgIcon', /<SvgIcon name=/.test(ECRAN));

// --- E. mobile first -------------------------------------------------------
verifier('E1. aucun breakpoint desktop — la page est un rail mobile',
  !/\b(sm|md|lg|xl):/.test(ECRAN));
verifier('E2. le CTA principal est pleine largeur et tactile',
  /w-full/.test(ECRAN) && /active:scale-95/.test(ECRAN));

// --- F. rollback ------------------------------------------------------------
const ESPACE = lire('frontend', 'src', 'components', 'SubscriberSpace.js');
const lignes = ESPACE.split('\n').filter((l) => /ConversionApresEssai/.test(l));
verifier('F1. le montage reste retirable en 2 lignes (1 import + 1 balise)',
  lignes.length === 2, lignes.join(' | '));

console.log('='.repeat(78));
let ok = 0;
for (const [nom, bon, detail] of R) {
  console.log(`  ${bon ? 'OK    ' : 'ECHEC '} ${nom}`);
  if (!bon && detail) console.log(`         -> ${detail}`);
  if (bon) ok += 1;
}
console.log('-'.repeat(78));
console.log(`${ok} / ${R.length} verifications`);
console.log('Lecture statique — aucun navigateur, aucun reseau, aucune base.');
process.exit(ok === R.length ? 0 : 1);
