// V659 — CE QU'UNE NOTIFICATION DIT, ET CE QU'ELLE PROPOSE DE FAIRE.
// Fonctions PURES : le banc les couvre sans navigateur.

// L'ICÔNE SUIT LE SENS, PAS L'EXPÉDITEUR. Un même type se reconnaît d'un coup
// d'œil, qu'il s'adresse à un abonné ou au coach.
export const TYPES = {
  cours: 'cours', reservation: 'reservation', abonnement: 'abonnement',
  message: 'message', paiement: 'paiement', info: 'info',
};

/** Le type d'une notification, déduit de ce qu'elle porte. PURE.
 *  On ne devine jamais : sans indice clair, c'est `info`. */
export function typeDe(notif) {
  const n = notif || {};
  const brut = String(n.type || n.kind || '').toLowerCase();
  if (TYPES[brut]) return TYPES[brut];
  const t = (String(n.titre || n.title || '') + ' ' + String(n.texte || n.body || '')).toLowerCase();
  if (/réserv|reserv|inscription/.test(t)) return TYPES.reservation;
  if (/abonnement|séances restantes|seances restantes|carte/.test(t)) return TYPES.abonnement;
  if (/paiement|facture|remboursement/.test(t)) return TYPES.paiement;
  if (/cours|séance|seance|horaire|annul/.test(t)) return TYPES.cours;
  if (/message|répond|repond|conversation/.test(t)) return TYPES.message;
  return TYPES.info;
}

/** L'action proposée au bas de la fenêtre, ou `null`. PURE.
 *  AUCUNE ACTION INVENTÉE : sans destination connue, on ne met pas de bouton
 *  plutôt qu'un bouton qui ne mène nulle part. */
export function actionDe(notif) {
  const n = notif || {};
  if (n.action && n.action.libelle && (n.action.href || typeof n.action.onClick === 'function')) {
    return n.action;
  }
  const url = n.url || n.deeplink || n.lien || '';
  if (!url) return null;
  const libelles = {
    [TYPES.cours]: 'Voir mon cours',
    [TYPES.reservation]: 'Voir ma réservation',
    [TYPES.abonnement]: 'Consulter mon abonnement',
    [TYPES.paiement]: 'Voir le paiement',
    [TYPES.message]: 'Lire le message',
    [TYPES.info]: 'Ouvrir',
  };
  return { libelle: libelles[typeDe(n)] || 'Ouvrir', href: url };
}

/** Le texte complet, JAMAIS tronqué. PURE.
 *  C'est tout l'objet de V659 : l'ancienne vignette coupait à 60 caractères. */
export function texteComplet(notif) {
  const n = notif || {};
  return String(n.texte || n.body || n.content || n.message || '').trim();
}

/** Le titre, avec un repli honnête. PURE. */
export function titreDe(notif) {
  const n = notif || {};
  return String(n.titre || n.title || n.senderName || 'Afroboost').trim() || 'Afroboost';
}

/** UNE SEULE FENÊTRE À LA FOIS. PURE.
 *  Les vignettes s'empilaient par quatre ; on montre la plus récente non lue
 *  et on garde les autres dans la liste, où elles restent consultables. */
export function aMontrer(file) {
  const l = Array.isArray(file) ? file.filter(Boolean) : [];
  if (!l.length) return null;
  const nonLues = l.filter((n) => !(n && (n.lu || n.read)));
  return (nonLues.length ? nonLues : l)[nonLues.length ? nonLues.length - 1 : l.length - 1];
}
