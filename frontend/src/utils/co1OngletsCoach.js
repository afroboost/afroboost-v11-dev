/**
 * CO-1 — Onglets du tableau de bord coach : UNE seule liste des onglets
 * autorisés, partagée par la barre d'onglets, la restauration depuis le
 * localStorage et la garde de rendu.
 *
 * Contacts et Campagnes sont désormais ouverts aux coachs partenaires : le
 * serveur cloisonne déjà chaque route par coach (lots MT-1 / MT-2). Ce qui
 * reste réservé au super-admin l'est par le SERVEUR (réglages plateforme :
 * ai_config, ai_logs, numéro WhatsApp officiel) — ce module ne décide d'aucun
 * droit, il évite seulement d'afficher un onglet qui n'existe pas.
 */

export const ONGLETS_COMMUNS = [
  'reservations', 'offers', 'codes', 'contacts', 'campaigns',
  'prospection', 'conversations', 'corbeille',
];

// Onglets propres au coach partenaire (le super-admin ne paie pas de crédits
// et n'a pas de compte Stripe Connect à relier).
export const ONGLETS_PARTENAIRE_SEUL = ['boutique', 'stripe'];

export const ONGLET_PAR_DEFAUT = 'reservations';

// Anciens identifiants encore présents dans des localStorage (v36).
const MIGRATIONS = {
  payments: 'offers',
  'page-vente': 'offers',
  concept: 'offers',
  courses: 'offers',
};

export function ongletsAutorises(isSuperAdmin) {
  return isSuperAdmin ? ONGLETS_COMMUNS.slice() : ONGLETS_COMMUNS.concat(ONGLETS_PARTENAIRE_SEUL);
}

/** L'onglet réellement affichable : sinon, repli sur Réservations. */
export function ongletValide(onglet, isSuperAdmin) {
  const migre = MIGRATIONS[onglet] || onglet;
  return ongletsAutorises(isSuperAdmin).indexOf(migre) !== -1 ? migre : ONGLET_PAR_DEFAUT;
}

/**
 * Le numéro WhatsApp officiel d'Afroboost n'est jamais proposé à un coach
 * partenaire : une campagne WhatsApp partirait de ce numéro (le serveur la
 * refuse de toute façon, cf. api/routes/co1_onglets_coach.py).
 */
export function canalCampagneAutorise(cle, isSuperAdmin) {
  return !!isSuperAdmin || cle !== 'whatsapp';
}

export const MESSAGE_WHATSAPP_PARTENAIRE =
  "WhatsApp : les campagnes WhatsApp partent du numéro officiel Afroboost, réservé à la plateforme. "
  + "Utilise le chat interne ou l'e-mail, ou écris à tes contacts depuis ton propre téléphone.";
