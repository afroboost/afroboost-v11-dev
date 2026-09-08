/**
 * CLEANUP PROFIL LEGACY AFROBOOST — l'ancien éditeur social Afroboost sort de
 * l'interface, le profil social actif est Spordateur (F2/F3/F4).
 *
 * Ces bancs lisent la SOURCE : ChatWidget.js fait 12 000 lignes et son montage
 * réel dépend d'un contexte que le banc ne reproduit pas. On prouve donc ce qui
 * est vérifiable sans ambiguïté : le formulaire legacy n'existe plus dans le
 * code exécuté, et les chemins F2/F3/F4 sont intacts.
 *
 * L'ORDRE COMPTE. Les assertions de NON-RÉGRESSION (chat, F2, F3, F4, routes
 * backend) sont écrites AVANT celles de suppression : elles étaient vertes
 * avant le nettoyage, donc un rouge après le nettoyage désigne le nettoyage.
 */
const fs = require('fs');
const path = require('path');

const RACINE = path.join(__dirname, '..', '..', '..', '..');
const lire = (p) => fs.readFileSync(path.join(RACINE, p), 'utf8');

/** Retire les commentaires : un commentaire qui EXPLIQUE une suppression ne
 *  doit jamais faire échouer l'assertion portant sur le code exécuté. */
function sansCommentaires(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1');
}

const CHAT = lire('frontend/src/components/ChatWidget.js');
const CHAT_CODE = sansCommentaires(CHAT);
const CARTE = lire('frontend/src/components/CarteProfilSpordateur.js');
const SERVEUR = lire('api/server.py');
const SPORDATE = lire('api/routes/spordate_routes.py');

/* ------------------------------------------------------------------ */
/* NON-RÉGRESSION — ce qui doit rester debout                          */
/* ------------------------------------------------------------------ */

test('J. le chat du ChatWidget est intact (envoi, sondage, pièces jointes)', () => {
  expect(CHAT_CODE).toMatch(/chat\/sessions/);
  expect(CHAT_CODE).toMatch(/setMessages/);
  expect(CHAT_CODE).toMatch(/handleSendMessage/);
  expect(CHAT_CODE).toMatch(/sendPrivateMessage/);
  expect(CHAT_CODE).toMatch(/v355EnvoyerMediaAbonne/); // pièces jointes
});

test('D. F2 — le profil unifié read-only reste lisible côté serveur et client', () => {
  expect(SERVEUR + SPORDATE).toMatch(/unified-profile/);
  expect(CHAT_CODE).toMatch(/spordate\/unified-profile\/me/);
  expect(fs.existsSync(path.join(RACINE, 'frontend/src/components/ProfilSocialPartage.js'))).toBe(true);
});

test('E. F3 — la route de handoff serveur répond bien en 303', () => {
  expect(SPORDATE).toMatch(/status_code=303/);
});

test('F. le drapeau SOCIAL_PROFILE_LINKS existe toujours et pilote les profils liés', () => {
  expect(SERVEUR).toMatch(/SOCIAL_PROFILE_LINKS/);
  expect(SPORDATE).toMatch(/SOCIAL_PROFILE_LINKS/);
});

test('G/H. mini-fiche : compte lié -> vrai profil, non lié -> état sûr', () => {
  expect(CHAT_CODE).toMatch(/mp-social-voir/);          // lié : ouvre Spordateur
  expect(CHAT_CODE).toMatch(/mp-social-viewer-non-lie/); // non lié : invitation
  expect(CHAT_CODE).toMatch(/mp-social-non-active/);     // cible non activée
});

test('I. F4 — la carte d’activation volontaire et son consentement sont conservés', () => {
  expect(CARTE).toMatch(/SOCIAL_ACTIVATION_ENABLED/);
  expect(CARTE).toMatch(/carte-consent-case/);
  expect(CARTE).toMatch(/carte-activer-confirmer/);
  expect(SERVEUR).toMatch(/SOCIAL_ACTIVATION_ENABLED/);
});

test('K/L. aucune route ni donnée historique de profil supprimée côté serveur', () => {
  // Lecture : encore utilisée par la mini-fiche ET par le chargement de photo.
  expect(SERVEUR).toMatch(/@api_router\.get\("\/users\/\{participant_id\}\/profile"\)/);
  // Écriture : plus appelée par le front, mais CONSERVÉE (clients tiers/PWA).
  expect(SERVEUR).toMatch(/@api_router\.patch\("\/users\/\{participant_id\}\/profile"\)/);
  // Les champs historiques restent servis : rien n'est effacé en base.
  expect(SERVEUR).toMatch(/"passions"/);
  expect(SERVEUR).toMatch(/"bio"/);
});

/* ------------------------------------------------------------------ */
/* NETTOYAGE — ce qui doit avoir disparu                               */
/* ------------------------------------------------------------------ */

test('A/C. l’ancien formulaire Nom/Bio/Âge/Passions n’existe plus dans le code', () => {
  expect(CHAT_CODE).not.toMatch(/showProfileForm/);
  expect(CHAT_CODE).not.toMatch(/setShowProfileForm/);
  expect(CHAT_CODE).not.toMatch(/savingProfile/);
  expect(CHAT_CODE).not.toMatch(/profileData/);
  expect(CHAT_CODE).not.toMatch(/getProfileKey/);
  expect(CHAT_CODE).not.toMatch(/openProfileForm/);
  expect(CHAT_CODE).not.toMatch(/\bsaveProfile\b/);
  expect(CHAT_CODE).not.toMatch(/Nom affiché/);
  expect(CHAT_CODE).not.toMatch(/Biographie/);
  expect(CHAT_CODE).not.toMatch(/Passions \/ Centres/);
});

test('A. plus aucune écriture Afroboost du profil social depuis le ChatWidget', () => {
  expect(CHAT_CODE).not.toMatch(/axios\.patch\(`\$\{API\}\/users\//);
});

test('B. « Mon profil » ouvre la page Spordateur, dans les deux espaces', () => {
  expect(CHAT_CODE).toMatch(/const ouvrirProfilSpordateur/);
  expect(CHAT_CODE).toMatch(/entrerDansSpordate\('\/profile'\)/);
  // deux entrées : menu utilisateur (abonné/visiteur) + barre du dashboard coach
  const clics = CHAT_CODE.match(/onClick=\{ouvrirProfilSpordateur\}/g) || [];
  expect(clics.length).toBe(2);
});

test('B. le seul bouton restant de la mini-fiche mène aussi à Spordateur', () => {
  expect(CHAT_CODE).toMatch(/mp-completer-spordate/);
  expect(CHAT_CODE).not.toMatch(/openProfileForm\(\)/);
});
