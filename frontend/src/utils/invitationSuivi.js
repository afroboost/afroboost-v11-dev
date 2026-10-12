// V607 — SUIVI DES INVITATIONS (côté navigateur). Un seul appel, public, sans
// donnée personnelle : `{jeton, evenement, visiteur}` -> POST /api/invitation/suivi.
//
// HONNÊTETÉ : `partage_whatsapp_declenche` = WhatsApp a été OUVERT avec le message
// prérempli. Personne ne sait si le message est parti : on ne l'écrit jamais.
// Le serveur ignore un jeton inconnu ou un événement hors liste ; un même
// appareil ne compte qu'une fois par événement et par jeton (`visiteur`).
// FAIL-OPEN : jamais d'exception, jamais d'attente côté parcours.
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const CLE_VISITEUR = 'af_inv_visiteur';

export const EVENEMENTS_SUIVI = [
  'lien_ouvert', 'seance_choisie', 'etape_invitation_atteinte',
  'partage_whatsapp_declenche', 'partage_autre_declenche', 'reservation_commencee',
];

/** Identifiant ALÉATOIRE de cet appareil (aucune donnée personnelle). */
export function visiteurSuivi() {
  try {
    let v = window.localStorage.getItem(CLE_VISITEUR);
    if (!v || !/^[a-z0-9]{8,40}$/.test(v)) {
      v = (Math.random().toString(36).slice(2) + Date.now().toString(36)).slice(0, 24);
      window.localStorage.setItem(CLE_VISITEUR, v);
    }
    return v;
  } catch (e) { return ''; }
}

/** Enregistre un événement ; ne lève jamais, ne bloque jamais. */
export function suivreInvitation(jeton, evenement) {
  if (!jeton || EVENEMENTS_SUIVI.indexOf(evenement) < 0) return;
  try {
    const corps = JSON.stringify({ jeton: String(jeton), evenement, visiteur: visiteurSuivi() });
    const url = `${BACKEND_URL}/api/invitation/suivi`;
    // keepalive : l'événement survit à l'ouverture de WhatsApp / au départ de la page.
    fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: corps, keepalive: true })
      .catch(() => {});
  } catch (e) { /* suivi facultatif */ }
}
