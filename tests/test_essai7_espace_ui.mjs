/**
 * ESSAI-7 — L'ESPACE PARTICIPANT REMET LA RESERVATION EN PREMIER.
 *
 * CE QUI ETAIT CASSE. Quelqu'un qui venait d'obtenir son essai arrivait dans un
 * ecran qui lui montrait d'abord un compteur, puis un QR code, puis — plus bas,
 * apres le pli — la liste des seances. Le QR ne sert a rien tant qu'aucune
 * seance n'est choisie : il repond a « je suis a l'entree du cours », pas a
 * « qu'est-ce que je fais maintenant ? ». Tant qu'aucune seance n'est reservee,
 * l'action dominante doit etre : CHOISIR SA SEANCE.
 *
 * ON LIT LES VRAIS FICHIERS, on n'en reecrit aucun. Aucun reseau, aucune base,
 * aucun DOM. Ce banc protege les promesses qui, defaites en silence,
 * transformeraient l'ecran en mensonge.
 *
 *   node tests/test_essai7_espace_ui.mjs
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const RACINE = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const lire = (p) => fs.readFileSync(path.join(RACINE, p), 'utf8');

const ESPACE = lire('frontend/src/components/SubscriberSpace.js');
const MODULE = lire('frontend/src/utils/essaiReservation.js');

const resultats = [];
const verifier = (nom, cond, detail = '') => resultats.push([nom, !!cond, detail]);

/** Retire commentaires et chaines pour ne raisonner que sur du CODE. */
function codeSeul(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1');
}
const CODE = codeSeul(ESPACE);

// ==========================================================================
// 1. L'ETAT VIENT DU SERVEUR, PAS D'UN CALCUL LOCAL
// ==========================================================================
verifier("1a. l'espace importe etatEssaiAffiche du module dedie",
  /import\s*\{[^}]*etatEssaiAffiche[^}]*\}\s*from\s*['"]\.\.\/utils\/essaiReservation['"]/.test(ESPACE));

verifier("1b. l'etat affiche passe par la fonction, pas par une copie locale",
  /etatEssaiAffiche\s*\(/.test(CODE));

// L'ETAT ('available'/'booked'/'done') n'est jamais compare a la main hors de
// la derivation : deux lectures concurrentes de l'etat finiraient par diverger.
verifier("1c. l'etat brut du serveur n'est lu qu'a la derivation",
  (CODE.match(/essai\.state/g) || []).length === 1,
  String((CODE.match(/essai\.state/g) || []).length));

// Le module est la seule fabrique d'adresse d'espace.
verifier("1d. le module connait la forme exacte des codes du serveur",
  /AFR-\[A-Z0-9\]\{6\}/.test(MODULE));

// ==========================================================================
// 2. TANT QU'AUCUNE SEANCE N'EST CHOISIE : LA RESERVATION DOMINE
// ==========================================================================
verifier("2a. un bloc prioritaire existe",
  ESPACE.includes('data-testid="essai7-priorite"'));

verifier("2b. il annonce que l'essai est ACTIVE",
  /Ton cours d'essai est activ/.test(ESPACE));

verifier("2c. il dit quoi faire ensuite : choisir sa seance",
  /Choisis maintenant ta s/.test(ESPACE));

verifier("2d. il n'apparait QUE si l'essai reste a reserver",
  /\{essaiAReserver\s*&&/.test(CODE));

verifier("2e. le CTA dominant nomme l'action, pas l'abstraction",
  ESPACE.includes('Réserver cette séance'));

// La priorite est un ORDRE d'affichage, pas une suppression : rien n'est cache.
verifier("2f. la priorite passe par `order`, jamais par un demontage",
  /order:\s*essaiPrioritaire\s*\?/.test(CODE) || /order:\s*\(?essaiAReserver/.test(CODE),
  'aucun style order conditionnel trouve');

verifier("2g. le conteneur est un flux ordonnable (flex), pas space-y",
  /className="max-w-md mx-auto px-4 pt-6 flex flex-col gap-5"/.test(ESPACE));

// ==========================================================================
// 3. APRES LA RESERVATION : L'ETAT RESERVE DOMINE, LE QR DEVIENT UTILE
// ==========================================================================
verifier("3a. un bloc de confirmation existe",
  ESPACE.includes('data-testid="essai7-reserve"'));

verifier("3b. il annonce la seance reservee",
  /Ta séance est réservée/.test(ESPACE));

verifier("3c. il dit quoi faire du QR a l'arrivee",
  /Présente-le au coach/.test(ESPACE));

verifier("3d. son CTA ouvre le QR, il ne le remplace pas",
  /data-testid="essai7-voir-qr"/.test(ESPACE)
  && /setQrFullscreen\(true\)/.test(CODE));

verifier("3e. il n'apparait QUE si une seance est reellement reservee",
  /\{essaiReserve\s*&&/.test(CODE));

// ==========================================================================
// 4. ZERO CRENEAU : DIRE LA VERITE, NE RIEN PROMETTRE
// ==========================================================================
verifier("4a. un etat vide dedie existe",
  ESPACE.includes('data-testid="essai7-aucun-creneau"'));

verifier("4b. il confirme que l'essai est bien activé",
  /Aucun nouveau créneau/.test(ESPACE));

verifier("4c. il n'invente AUCUNE notification future",
  !/(pr[ée]viendrons|notifier|te pr[ée]viens|alerte|d[èe]s qu'un cr[ée]neau)/i.test(ESPACE));

// ==========================================================================
// 5. CE QUI NE DOIT PAS AVOIR BOUGE
// ==========================================================================
verifier("5a. le QR reste rendu, sans nouvelle condition",
  /data-testid="subscriber-space-qr"/.test(ESPACE));

verifier("5b. la section de reservation existe toujours",
  /data-testid="subscriber-space-reservation"/.test(ESPACE));

verifier("5c. le bouton d'annulation existe toujours",
  /data-testid=\{`cancel-reservation-\$\{r\.id\}`\}/.test(ESPACE));

verifier("5d. la reservation reste EXPLICITE : aucun appel automatique",
  !/useEffect\([^)]*handleReserve/.test(CODE)
  && (CODE.match(/handleReserve\(/g) || []).length <= 2,
  String((CODE.match(/handleReserve\(/g) || []).length));

verifier("5e. un forfait payant garde son compteur de seances",
  /Séances restantes/.test(ESPACE));

// ==========================================================================
// 6. LES COULEURS DU COACH, PARTOUT (regle absolue du projet)
// ==========================================================================
/** Le corps d'une <section> reperee par son data-testid. */
function section(testid) {
  const i = ESPACE.indexOf(`data-testid="${testid}"`);
  if (i < 0) return '';
  const debut = ESPACE.lastIndexOf('<section', i);
  const fin = ESPACE.indexOf('</section>', i);
  return ESPACE.slice(debut, fin);
}
const NOUVEAUX = section('essai7-priorite') + '\n' + section('essai7-reserve');
verifier("6a. les deux blocs ESSAI-7 existent bien comme sections",
  NOUVEAUX.length > 400, String(NOUVEAUX.length));
verifier("6b. ils n'imposent AUCUNE couleur en dur",
  !/#[0-9a-fA-F]{3,8}\b/.test(NOUVEAUX.replace(/var\([^)]*\)/g, '')),
  (NOUVEAUX.replace(/var\([^)]*\)/g, '').match(/#[0-9a-fA-F]{3,8}\b/g) || []).join(' '));
verifier("6c. ils passent par la couleur du coach",
  /COLORS\.primary/.test(NOUVEAUX) && /--primary-rgb/.test(NOUVEAUX));

// ==========================================================================
// 7. LA MESURE
// ==========================================================================
verifier("7a. session_booked part de cet ecran",
  /funnelTracer\(\s*'session_booked'/.test(ESPACE));

verifier("7b. la mesure ne peut pas interrompre la reservation (jamais awaitee)",
  !/await\s+funnelTracer/.test(ESPACE));

verifier("7c. aucune donnee personnelle dans les proprietes envoyees",
  (() => {
    const i = ESPACE.search(/funnelTracer\(\s*'session_booked'/);
    if (i < 0) return false;
    const bloc = ESPACE.slice(i, i + 400);
    return !/(email|prenom|firstName|guestNames|accessCode|access_code|subscriber\.name)/.test(bloc);
  })());

// --------------------------------------------------------------------------
const ok = resultats.filter(([, r]) => r).length;
console.log('='.repeat(78));
for (const [nom, r, detail] of resultats) {
  console.log((r ? '  PASS  ' : '  FAIL  ') + nom + (r || !detail ? '' : `   -> ${detail}`));
}
console.log('='.repeat(78));
console.log(`${ok}/${resultats.length} verifications`);
process.exit(ok === resultats.length ? 0 : 1);
