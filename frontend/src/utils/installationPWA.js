// V659 — RECONNAÎTRE LE TÉLÉPHONE, SANS JAMAIS MENTIR SUR CE QU'IL SAIT FAIRE.
//
// Tout est PUR ici : on reçoit ce qu'on a lu du navigateur, on rend un verdict.
// Aucune lecture de `window`, donc le banc d'essai couvre chaque téléphone sans
// navigateur — et personne n'a besoin d'un iPhone pour vérifier le guide iPhone.
//
// LA RÈGLE QUI GOUVERNE CE FICHIER : on ne propose un bouton « Installer » que
// là où un bouton installe VRAIMENT. Sur iPhone, aucune page web ne peut
// déclencher l'ajout à l'écran d'accueil — seul l'utilisateur le peut, par le
// menu Partager. Un faux bouton qui ne ferait rien serait pire que pas de
// bouton du tout : il ferait croire à une panne.

export const PLATEFORME = {
  IOS: 'ios',
  ANDROID: 'android',
  AUTRE: 'autre',
};

/** Quel téléphone ? À partir de l'`userAgent` seul. PURE. */
export function plateforme(userAgent) {
  const ua = String(userAgent || '');
  if (/iPad|iPhone|iPod/.test(ua)) return PLATEFORME.IOS;
  // iPadOS 13+ se présente comme un Mac : le vrai signe est l'écran tactile.
  if (/Macintosh/.test(ua) && /Mobile|Touch/.test(ua)) return PLATEFORME.IOS;
  if (/Android/i.test(ua)) return PLATEFORME.ANDROID;
  return PLATEFORME.AUTRE;
}

/** L'application tourne-t-elle DÉJÀ depuis l'écran d'accueil ? PURE.
 *  `standaloneMedia` = `matchMedia('(display-mode: standalone)').matches`
 *  `navigatorStandalone` = `navigator.standalone` (le signe propre à iOS). */
export function estInstallee(standaloneMedia, navigatorStandalone) {
  return Boolean(standaloneMedia) || navigatorStandalone === true;
}

/** Le navigateur sait-il installer tout seul ? PURE.
 *  Vrai UNIQUEMENT si un `beforeinstallprompt` a été capturé — c'est la seule
 *  preuve qu'un bouton fonctionnera. On ne le déduit jamais de la plateforme. */
export function peutInstallerNativement(prompt) {
  return Boolean(prompt);
}

/** Que montrer à cette personne ? PURE. Rend l'un de :
 *   'deja-installee' · 'bouton-natif' · 'guide-ios' · 'instructions-android'
 *   · 'non-supporte'  */
export function modeInstallation({ userAgent, standaloneMedia, navigatorStandalone, prompt }) {
  if (estInstallee(standaloneMedia, navigatorStandalone)) return 'deja-installee';
  const p = plateforme(userAgent);
  if (p === PLATEFORME.IOS) return 'guide-ios';        // jamais de bouton : il ne peut pas marcher
  if (peutInstallerNativement(prompt)) return 'bouton-natif';
  if (p === PLATEFORME.ANDROID) return 'instructions-android';
  return 'non-supporte';
}

/** Les étapes du guide iPhone. PURE, et volontairement courtes. */
export const ETAPES_IOS = [
  { n: 1, texte: 'Ouvre Afroboost dans Safari.' },
  { n: 2, texte: 'Touche le bouton Partager, en bas de l’écran.' },
  { n: 3, texte: 'Fais défiler et choisis « Sur l’écran d’accueil ».' },
  { n: 4, texte: 'Touche « Ajouter », en haut à droite.' },
  { n: 5, texte: 'Ouvre Afroboost depuis sa nouvelle icône.' },
];

/** Les étapes Android, quand le navigateur refuse le bouton. PURE. */
export const ETAPES_ANDROID = [
  { n: 1, texte: 'Ouvre le menu du navigateur (les trois points).' },
  { n: 2, texte: 'Choisis « Installer l’application » ou « Ajouter à l’écran d’accueil ».' },
  { n: 3, texte: 'Confirme l’ajout.' },
  { n: 4, texte: 'Ouvre Afroboost depuis sa nouvelle icône.' },
];

// ON NE REDEMANDE PAS À QUELQU'UN QUI A DÉJÀ DIT NON. La fenêtre se montre une
// fois, puis se tait — sauf si la personne demande elle-même à la revoir.
export const CLE_VUE = 'af_installation_vue';

/** Faut-il montrer la fenêtre ? PURE.
 *  `estAbonne` : les visiteurs de passage n'ont rien à installer. */
export function faudraitMontrer({ mode, estAbonne, dejaVue }) {
  if (!estAbonne) return false;
  if (mode === 'deja-installee') return false;
  if (dejaVue) return false;
  return true;
}
