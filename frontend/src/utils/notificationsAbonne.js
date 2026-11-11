// V660 — LES NOTIFICATIONS D'UN ABONNÉ, TIRÉES DE SES PROPRES DONNÉES.
//
// AUCUN SYSTÈME NEUF, ET C'EST VOLONTAIRE. La collection `notifications` du
// serveur ne contient que des avis destinés au COACH (une annulation à lui
// signaler) : rien n'y est écrit pour un abonné. Plutôt que d'inventer un
// deuxième entrepôt à tenir à jour — et à synchroniser — on LIT ce que l'espace
// abonné a déjà en main : ses réservations et son abonnement. Les faits sont
// les mêmes, ils ne peuvent pas diverger, et il n'y a rien de plus à écrire.
//
// CHACUN NE VOIT QUE LES SIENNES, PAR CONSTRUCTION. Cette fonction ne lit
// aucune base : elle reçoit les données de l'espace déjà authentifié. Il n'y a
// pas de requête qui pourrait, un jour, rapporter la ligne d'un autre compte.
//
// Tout est PUR : le banc couvre chaque cas sans navigateur et sans serveur.

const JOUR_MS = 86400000;

function dateFr(iso) {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleDateString('fr-CH', { weekday: 'long', day: 'numeric', month: 'long' });
  } catch (e) { return ''; }
}

function heureFr(iso) {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleTimeString('fr-CH', { hour: '2-digit', minute: '2-digit' });
  } catch (e) { return ''; }
}

/** Le fil de l'abonné, du plus récent au plus ancien. PURE.
 *  `maintenant` est injecté : un banc ne dépend pas de l'heure qu'il est. */
export function notificationsAbonne({ reservations, subscription, maintenant } = {}) {
  const now = typeof maintenant === 'number' ? maintenant : Date.now();
  const res = Array.isArray(reservations) ? reservations.filter(Boolean) : [];
  const sub = subscription || null;
  const liste = [];

  // 1. LA PROCHAINE SÉANCE. C'est l'information que l'on vient chercher.
  const aVenir = res
    .filter((r) => r.datetime && new Date(r.datetime).getTime() > now)
    .sort((a, b) => new Date(a.datetime).getTime() - new Date(b.datetime).getTime());
  if (aVenir.length) {
    const r = aVenir[0];
    const nom = String(r.courseName || r.offerName || 'Ta séance').trim();
    const jours = Math.round((new Date(r.datetime).getTime() - now) / JOUR_MS);
    liste.push({
      id: 'prochaine-' + (r.id || r.reservationCode || r.datetime),
      type: 'cours',
      titre: jours <= 0 ? 'Ta séance, aujourd’hui' : 'Ta prochaine séance',
      texte: nom + '\n' + dateFr(r.datetime) + (heureFr(r.datetime) ? ' à ' + heureFr(r.datetime) : '')
        + (r.locationName ? '\n' + r.locationName : '')
        + (r.reservationCode ? '\n\nCode de réservation : ' + r.reservationCode : ''),
      horodatage: now,
    });
  }

  // 2. LES SÉANCES QUI S'ÉPUISENT. On prévient AVANT d'être à zéro.
  if (sub && typeof sub.remaining_sessions === 'number') {
    const n = sub.remaining_sessions;
    if (n <= 0) {
      liste.push({
        id: 'seances-epuisees', type: 'abonnement',
        titre: 'Il ne te reste plus de séance',
        texte: 'Ton forfait est arrivé au bout. Tu peux le recharger pour continuer à venir aux cours.',
        horodatage: now,
      });
    } else if (n <= 2) {
      liste.push({
        id: 'seances-bientot-' + n, type: 'abonnement',
        titre: n === 1 ? 'Il te reste 1 séance' : 'Il te reste ' + n + ' séances',
        texte: 'Pense à recharger ton forfait pour ne pas être interrompu·e.'
          + (sub.offer_name ? '\n\nTa formule : ' + sub.offer_name : ''),
        horodatage: now,
      });
    }
  }

  // 3. L'ÉCHÉANCE DE L'ABONNEMENT, quinze jours avant et après.
  if (sub && sub.expires_at) {
    const fin = new Date(sub.expires_at).getTime();
    if (!Number.isNaN(fin)) {
      const jours = Math.round((fin - now) / JOUR_MS);
      if (jours < 0) {
        liste.push({
          id: 'abonnement-expire', type: 'abonnement',
          titre: 'Ton abonnement a expiré',
          texte: 'Il s’est terminé le ' + dateFr(sub.expires_at)
            + '. Tu peux le reprendre quand tu veux.',
          horodatage: now,
        });
      } else if (jours <= 15) {
        liste.push({
          id: 'abonnement-fin-' + jours, type: 'abonnement',
          titre: jours === 0 ? 'Ton abonnement se termine aujourd’hui'
            : 'Ton abonnement se termine bientôt',
          texte: 'Fin le ' + dateFr(sub.expires_at)
            + (jours > 0 ? ' — dans ' + jours + ' jour' + (jours > 1 ? 's' : '') + '.' : '.'),
          horodatage: now,
        });
      }
    }
  }

  return liste;
}

// CE QUI N'EXISTE PAS ENCORE, ET QU'IL NE FAUT PAS FAIRE SEMBLANT D'AVOIR.
// Aucune de ces informations n'est enregistrée quelque part où un abonné
// pourrait la relire : les afficher demanderait d'abord que le serveur les
// écrive. Les nommer ici évite qu'on les croie perdues.
export const PAS_ENCORE_SUIVIS = [
  'un cours déplacé ou annulé par le coach',
  'un paiement reçu ou remboursé',
  'un message du coach adressé personnellement',
];
