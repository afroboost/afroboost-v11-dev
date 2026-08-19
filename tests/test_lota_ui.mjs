/**
 * LOT A — L'ECRAN D'APRES-ESSAI : les invariants d'interface.
 *
 * On lit les VRAIS fichiers, on n'en reecrit aucun. Ce test protege les cinq
 * promesses qui, defaites en silence, transformeraient l'ecran en mensonge :
 * aucun prix ecrit en dur, aucune liste d'offres en dur, aucune couleur imposee,
 * aucune boucle d'appels, et une garde metier qui reste cote serveur.
 *
 * Aucun reseau, aucun DOM, aucune base. `node tests/test_lota_ui.mjs`
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const RACINE = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const lire = (p) => fs.readFileSync(path.join(RACINE, p), 'utf8');

const ECRAN = lire('frontend/src/components/ConversionApresEssai.js');
const ESPACE = lire('frontend/src/components/SubscriberSpace.js');
const WIZARD = lire('frontend/src/components/dashboard/OfferWizard.js');
const DASH = lire('frontend/src/components/CoachDashboard.js');

const resultats = [];
const verifier = (nom, cond, detail = '') => resultats.push([nom, !!cond, detail]);

/** Retire commentaires et chaines pour ne raisonner que sur du CODE. */
function codeSeul(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1');
}
const ecran = codeSeul(ECRAN);

// --- A. LES PRIX ET LES OFFRES VIENNENT DU SERVEUR --------------------------
verifier('A1. aucun montant du catalogue ecrit en dur dans l\'ecran',
  !/\b(250|150|30)\b/.test(ecran.replace(/size=\{\d+\}/g, '')),
  'le prix doit venir de `o.price`, rendu par le serveur');

verifier('A2. le prix affiche est bien celui recu du serveur',
  ecran.includes('montant(o.price, o.currency)'));

verifier('A3. le nombre de seances vient du serveur',
  ecran.includes('o.sessions'));

verifier('A4. aucun identifiant d\'offre code en dur',
  !/off-|offer_id\s*[:=]\s*['"][a-z0-9-]/i.test(ecran.replace(/offer_id: offre\.id/, '')),
  'la liste des offres est celle que le serveur rend, pas une liste locale');

verifier('A5. la liste rendue est celle du serveur, sans filtrage local',
  ecran.includes('etat.offers') && !/\.filter\(/.test(ecran),
  'un filtre cote client serait une seconde regle metier a maintenir');

// --- B. LA GARDE RESTE SERVEUR ---------------------------------------------
verifier('B1. l\'achat repasse par la route serveur de conversion',
  ecran.includes('/conversion/checkout'));

verifier('B2. l\'ecran ne construit aucune session de paiement lui-meme',
  !ecran.includes('checkout/create-session') && !ecran.includes('stripe'));

verifier('B2b. l\'ecran n\'envoie AUCUNE URL de retour (pas de redirection ouverte)',
  !ecran.includes('originUrl') && !ecran.includes('window.location.origin'),
  'le serveur connait FRONTEND_URL ; la laisser au navigateur ouvrirait une redirection');

verifier('B3. l\'eligibilite n\'est pas recalculee cote client',
  !ecran.includes('validated') && !ecran.includes('validatedAt'),
  'seul `etat.state`, rendu par le serveur, decide');

verifier('B4. l\'ecran se rend invisible si le serveur n\'ouvre rien',
  ecran.includes('if (!etat || !etat.eligible) return null'));

verifier('B5. aucune offre proposee -> aucun cadre vide, aucun crash',
  ecran.includes("etat.state !== \"open\" || offres.length === 0) return null"));

verifier('B6. deja converti -> la personne n\'est plus traitee en prospect',
  ecran.includes('etat.state === "purchased"'));

// --- C. AUCUNE BOUCLE D'APPELS API -----------------------------------------
verifier('C1. l\'effet ne depend que du code, une valeur primitive',
  /useEffect\([\s\S]*?\}, \[code\]\)/.test(ecran),
  'dependre d\'un objet relancerait l\'appel a chaque rendu (V305)');

verifier('C2. un garde-fou empeche le second appel pour le meme code',
  ecran.includes('demande.current === c'));

verifier('C3. le composant demonte ne pose plus d\'etat',
  ecran.includes('if (!vivant) return') && ecran.includes('vivant = false'));

verifier('C4. le bouton ne peut pas partir deux fois',
  ecran.includes('if (enCours) return') && ecran.includes('disabled={!!enCours}'));

// --- D. COULEURS DU COACH ---------------------------------------------------
const hexRestants = (ecran.match(/#[0-9a-fA-F]{6}/g) || [])
  .filter((h) => h.toUpperCase() !== '#D91CD2');
verifier('D1. aucune couleur de marque imposee (hex hors valeur de secours)',
  hexRestants.every((h) => ECRAN.includes(`"${h}"`) && /fca5a5/i.test(h)),
  `hex trouves : ${hexRestants.join(', ')}`);

// Le rose ne survit qu'a l'interieur d'un `var()` : on retire toutes les
// expressions `var(--primary-…, …)` et on verifie qu'il n'en reste aucun.
const ecranSansVar = ecran.replace(/var\(--primary-[a-z]+,[^)]*\)/g, '');
verifier('D2. le rose n\'apparait que comme valeur de secours dans var()',
  !ecranSansVar.includes('#D91CD2') && !ecranSansVar.includes('217, 28, 210'),
  'hors commentaires, chaque #D91CD2 doit etre le repli d\'un var()');

verifier('D3. la couleur primaire du coach est utilisee partout',
  ecran.includes('var(--primary-color, #D91CD2)'));

// --- E. LES ICONES SONT DES SVG --------------------------------------------
verifier('E1. aucune emoji utilisee comme icone',
  !/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(ECRAN));

verifier('E2. les icones passent par SvgIcon',
  ECRAN.includes('<SvgIcon name='));

// --- F. LE BRANCHEMENT DANS L'ESPACE ABONNE --------------------------------
const espace = codeSeul(ESPACE);
verifier('F1. l\'ecran est branche dans l\'espace abonne',
  espace.includes('<ConversionApresEssai'));

verifier('F2. il n\'est sollicite qu\'apres un essai effectue',
  espace.includes('estEssai && etatEssai === "done" && ('));

const lignesEcran = ESPACE.split('\n').filter((l) => l.includes('ConversionApresEssai'));
verifier('F3. le retrait de l\'ecran tient en un import et une balise',
  lignesEcran.length === 2 && lignesEcran[0].startsWith('import'),
  `rollback UI seul : ${lignesEcran.length} lignes concernees`);

// --- G. LE REGLAGE COTE COACH ----------------------------------------------
const wizard = codeSeul(WIZARD);
verifier('G1. la case existe dans le formulaire d\'offre',
  wizard.includes("set('first_purchase_eligible', e.target.checked)"));

verifier('G2. elle est decochee par defaut (aucune valeur imposee)',
  wizard.includes('checked={!!form.first_purchase_eligible}'));

const dash = codeSeul(DASH);
verifier('G3. le champ traverse la liste blanche d\'enregistrement',
  dash.includes('first_purchase_eligible: !!src.first_purchase_eligible'),
  'absent de la liste blanche, le PUT le remettrait a false a chaque sauvegarde');

verifier('G4. le formulaire est remis a zero entre deux offres',
  dash.includes('first_purchase_eligible: false'));

// --- Rapport ---------------------------------------------------------------
let echecs = 0;
for (const [nom, ok, detail] of resultats) {
  console.log(`${ok ? 'OK  ' : 'ECHEC'}  ${nom}${!ok && detail ? `\n         -> ${detail}` : ''}`);
  if (!ok) echecs++;
}
console.log(`\n=== LOT A (UI) : ${resultats.length - echecs}/${resultats.length} verifications ===`);
process.exit(echecs ? 1 : 0);
