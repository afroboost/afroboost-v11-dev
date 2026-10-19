// V626 — PARTAGER UNE OFFRE : UNE OFFRE = UN LIEN INDIVIDUEL STABLE.
//
// AUCUN NOUVEAU SYSTÈME DE LIENS. Le lien est celui qui existe déjà et que la
// vitrine sait ouvrir : `/?offre=<id>` (OffresAimants, V537/V546). Il ne
// dépend que de l'identifiant de l'offre — jamais d'un jeton fabriqué au clic —
// donc il est le même à chaque copie, pour chaque personne, sur chaque appareil.
//
// AUCUNE NOUVELLE MÉCANIQUE DE PARTAGE. Copie, partage natif et lien WhatsApp
// sont ceux du Centre Parrainage (`utils/parrainage.js`), déjà en production.
import { copier, partager, lienWhatsApp } from './parrainage';

/** L'URL publique EXACTE d'une offre. Pure. */
export function urlOffre(offre, origine) {
  const base = origine || (typeof window !== 'undefined' ? window.location.origin : 'https://afroboost.com');
  return `${base}/?offre=${encodeURIComponent(String((offre && offre.id) || ''))}`;
}

/** Une offre se partage-t-elle ? Celles que le lien `/?offre=` sait réellement ouvrir. Pure.
 *  - masquée (`visible: false`) ou archivée : le serveur ne la rend pas -> lien mort ;
 *  - produit de la boutique : le lien d'offre ne vise que les services.
 *  Une offre PRIVÉE (`link_only`) se partage : le lien est même son seul accès (V537). */
export function offrePartageable(offre) {
  return !!(offre && offre.id) && offre.visible !== false && offre.archived !== true && !offre.isProduct;
}

/** Le texte qui accompagne le lien (WhatsApp, partage natif). Pur. */
export function texteOffre(offre) {
  const nom = String((offre && offre.name) || 'Offre Afroboost').trim();
  return `${nom} — réserve ta place sur Afroboost`;
}

/** Copie le lien de l'offre. -> Promise<boolean> */
export function copierLienOffre(offre) {
  return copier(urlOffre(offre));
}

/**
 * Partage le lien de l'offre.
 * - téléphone : partage natif (WhatsApp, SMS, Messenger… au choix de la personne) ;
 * - sans partage natif (ordinateur) : le lien est copié ET WhatsApp s'ouvre avec
 *   le message prêt, dans un nouvel onglet.
 * @returns {Promise<{ok:boolean, methode:'share'|'copie'|'whatsapp'|'none'}>}
 */
export async function partagerOffre(offre) {
  const url = urlOffre(offre);
  const text = texteOffre(offre);
  if (typeof navigator !== 'undefined' && typeof navigator.share === 'function') {
    return partager({ title: String((offre && offre.name) || 'Afroboost'), text, url });
  }
  const ok = await copier(url);
  try {
    window.open(lienWhatsApp(`${text}\n${url}`), '_blank', 'noopener,noreferrer');
  } catch (e) { /* le lien reste copié */ }
  return { ok, methode: 'whatsapp' };
}
