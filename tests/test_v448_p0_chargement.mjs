/**
 * V448 — P0 CHARGEMENT : les invariants qui ne doivent plus jamais reculer.
 *
 * Meme esprit que test_v443_chargement_decouple.mjs : on lit les VRAIS fichiers,
 * on n'en reecrit aucun. Si quelqu'un defait un de ces points, ce test le dit.
 *
 * Aucun reseau, aucun DOM, aucune base. `node tests/test_v448_p0_chargement.mjs`
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const RACINE = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const lire = (p) => fs.readFileSync(path.join(RACINE, p), 'utf8');

const APP = lire('frontend/src/App.js');
const DASH = lire('frontend/src/components/CoachDashboard.js');
const CONTACTS = lire('frontend/src/components/dashboard/ContactsManager.js');
const AUTH = lire('frontend/src/utils/authSession.js');
const HOOK = lire('frontend/src/hooks/useChargement.js');
const ETATS = lire('frontend/src/components/ui/EtatChargement.js');

const resultats = [];
const verifier = (nom, cond, detail = '') => resultats.push([nom, !!cond, detail]);

/** Retire commentaires et chaines pour ne raisonner que sur du CODE. */
function codeSeul(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1');
}

// --- A. App.js : la vitrine ne perd plus les reponses 200 -------------------
const appCode = codeSeul(APP);
verifier('A1. fetchData utilise allSettled, plus Promise.all',
  appCode.includes('await Promise.allSettled(requests)') && !appCode.includes('await Promise.all(requests)'));

verifier('A2. la fermeture de fetchData depend des valeurs qu\'elle lit',
  appCode.includes('[isCacheValid, v448VitrineCoach, v448EmailCoach]'),
  'sinon se connecter pendant la session ne recharge rien jusqu\'au prochain F5');

verifier('A3. les deux routes a signature ne partent pas sans preuve',
  appCode.includes('if (v448EmailCoach && authValide())'));

verifier('A4. aucune donnee n\'est posee sans reponse (pas de faux zero)',
  appCode.includes('if (coursesData !== undefined)') &&
  appCode.includes('if (offersData !== undefined)') &&
  appCode.includes('if (usersData !== undefined) setUsers(usersData)'));

verifier('A5. l\'intercepteur ne recharge plus la page ni n\'alerte',
  !appCode.includes("alert('Votre session a expiré. Merci de vous reconnecter.')") &&
  !/hadSession\s*\)\s*\{[\s\S]{0,120}location\.reload/.test(appCode));

verifier('A6. la sortie de session passe par terminerSession (purge complete)',
  (appCode.match(/terminerSession\(/g) || []).length >= 3);

verifier('A7. la fin de session est EXPLIQUEE et propose la reconnexion',
  appCode.includes('setLoginWelcomeMessage(\'Votre session a expiré') &&
  appCode.includes('setShowCoachLogin(true)'));

// --- B. Contacts : pas de faux zero, et Contacts V2 intact -----------------
const contactsCode = codeSeul(CONTACTS);
verifier('B1. les compteurs de tete passent par <Compteur> (— pendant le chargement)',
  contactsCode.includes('<Compteur') && contactsCode.includes('etat={etatContacts}'));

verifier('B2. un `success: false` en HTTP 200 devient un echec, pas une liste vide',
  contactsCode.includes("echecDeReponse('contacts non livres'"));

verifier('B3. CONTACTS V2 preserve : `compteurs` est toujours pose depuis l\'enveloppe',
  contactsCode.includes('setCompteurs(') && contactsCode.includes('c.donnees.compteurs'));

verifier('B4. CONTACTS V2 preserve : les cinq vues rapides sont intactes',
  contactsCode.includes('compteurs.abonnes_actifs') &&
  contactsCode.includes('compteurs.non_classes') &&
  contactsCode.includes("typeof n === 'number'"));

verifier('B5. une section en echec propose sa relance',
  contactsCode.includes('onReessayer={() => chargementContacts.reessayer(cle)}'));

// --- C. Conversations : une liste secondaire ne tue plus l'ecran -----------
const dashCode = codeSeul(DASH);
verifier('C1. loadConversations utilise allSettled',
  dashCode.includes('const [conversationsRes, participantsRes, linksRes] = await Promise.allSettled(['));

verifier('C2. participants et liens s\'appliquent independamment',
  dashCode.includes("if (participantsRes.status === 'fulfilled') setChatParticipants(") &&
  dashCode.includes("if (linksRes.status === 'fulfilled') setChatLinks("));

verifier('C3. le repli ne recharge QUE les conversations',
  dashCode.includes('const sessionsRes = await axios.get(`${API}/chat/sessions`);') &&
  !dashCode.includes('const [sessionsRes, participantsRes, linksRes] = await Promise.all(['));

verifier('C4. l\'echec des conversations est qualifie, plus muet',
  dashCode.includes('setConversationsErreur(classerEchec('));

verifier('C5. l\'ecran des conversations propose une relance',
  dashCode.includes('data-testid="v448-reessayer-conversations"'));

// --- D. V443/V444 toujours en place (aucune regression) -------------------
verifier('D1. V443 : le decouplage des sept sources est intact',
  dashCode.includes('const reponses = await Promise.allSettled([') &&
  dashCode.includes('const appliquer = (nom, reponse, poser) => {'));

verifier('D2. V444 : le delai d\'expiration est intact',
  dashCode.includes('DELAI_CHARGE_MS') && dashCode.includes('const avecDelai = ('));

verifier('D3. V443 : le bandeau d\'echec existe toujours',
  dashCode.includes('data-testid="v443-bandeau-echec"'));

verifier('D4. le bandeau ne renvoie plus l\'utilisateur au rafraichissement',
  dashCode.includes('data-testid="v448-reessayer"') &&
  !DASH.includes('Rechargez la page ; si le problème'));

// --- E. Le socle lui-meme -------------------------------------------------
const socle = codeSeul(AUTH) + codeSeul(HOOK) + codeSeul(ETATS);
verifier('E1. la recuperation appartient a l\'application (aucun reload dans le socle)',
  !/location\s*\.\s*reload/.test(socle) && !/location\s*\.\s*href\s*=/.test(socle));

verifier('E2. le portillon ne retient QUE des routes prouvees',
  AUTH.includes("'/users'") && AUTH.includes("'/contacts/all'") &&
  !AUTH.includes("'/reservations'") && !AUTH.includes("'/chat/sessions'"),
  '/reservations et /chat/sessions acceptent un autre chemin : les bloquer serait un durcissement aveugle');

verifier('E3. aucun repli X-User-Email n\'est reintroduit cote navigateur',
  !codeSeul(AUTH).includes("X-User-Email"));

verifier('E4. le hook n\'utilise jamais Promise.all',
  codeSeul(HOOK).includes('Promise.allSettled') && !/await Promise\.all\(/.test(codeSeul(HOOK)));

verifier('E5. aucune section ne peut rester en chargement (finally present)',
  codeSeul(HOOK).includes('} finally {'));

verifier('E6. un 4xx n\'est jamais relance automatiquement',
  codeSeul(HOOK).includes("if (motif === 'reseau') aRelancerReseau.push(cle)"));

// --- Rapport ---------------------------------------------------------------
let echecs = 0;
for (const [nom, ok, detail] of resultats) {
  console.log(`${ok ? 'OK  ' : 'ECHEC'}  ${nom}${!ok && detail ? `\n         -> ${detail}` : ''}`);
  if (!ok) echecs++;
}
console.log(`\n=== V448 : ${resultats.length - echecs}/${resultats.length} verifications ===`);
process.exit(echecs ? 1 : 0);
