/**
 * V618L — « Voir l'événement » : la VRAIE page de l'événement. Place offerte à ce membre -> sa
 * carte dans l'espace (ancre) ; sinon l'invitation active du coach (`lien_evenement`, donnée
 * par le serveur) ; à défaut seulement, l'ancien lien vitrine. Jamais « / » quand on sait mieux.
 */
export function lienVoirEvenement(occ, data) {
  const o = occ || {};
  const offerts = (data && data.evenements_offerts) || [];
  if (o.offer_id && offerts.some((e) => e && e.offer_id === o.offer_id)) return `#evt-offert-${encodeURIComponent(o.offer_id)}`;
  if (typeof o.lien_evenement === "string" && /^\/i\/[A-Za-z0-9_-]{8,80}$/.test(o.lien_evenement)) return o.lien_evenement;
  return o.offer_id ? `/?offre=${encodeURIComponent(o.offer_id)}` : "/";
}

