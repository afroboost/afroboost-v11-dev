// partnerLink.js — P2-C : le lien personnel d'un partenaire, et rien d'autre.
//
// POURQUOI UN FICHIER À PART. Le lien sera relu par P2-D pour rapprocher les
// statistiques d'un partenaire de son `utm_content`. Deux constructions
// séparées de la même URL finiraient par diverger d'un caractère — et une
// attribution qui ne retombe pas sur ses pieds est indétectable à l'œil. Une
// seule fonction, un seul endroit.
//
// LE LIEN N'EST JAMAIS STOCKÉ. Il est DÉRIVÉ du `partner_slug`, qui vit sur
// `partners.partner_slug` et nulle part ailleurs. Persister `partner_url`,
// `qr_url` ou équivalent créerait une seconde source de vérité, donc un jour
// une contradiction. Le QR suit la même règle : c'est une image du lien,
// calculée à l'affichage, pas une donnée métier.
//
// LES QUATRE VALEURS UTM SONT VERROUILLÉES. `partenaire` figure dans la liste
// blanche des sources de M2 (`attribution.js`) et la page d'essai propage
// elle-même les paramètres vers le tunnel. Renommer l'une des quatre romprait
// l'attribution en silence : aucune erreur, aucun 500, simplement des
// partenaires qui n'auraient jamais rien apporté. Un test les fige.

/** LA règle du slug, écrite une seule fois. Identique au serveur
 *  (`P2B_SLUG_MOTIF`, api/server.py) — les deux doivent rester jumeaux. */
export const P2C_MOTIF_SLUG = /^[a-z0-9_]{3,40}$/;

/** La page d'atterrissage de l'essai, rendue par le serveur (`_M1_CHEMIN`).
 *  C'est ELLE qui reporte les UTM sur le tunnel existant `/?link=…` : on ne
 *  vise donc pas le tunnel directement, sous peine de perdre l'attribution. */
export const P2C_BASE_ESSAI = 'https://afroboost.com/cours-essai-gratuit-neuchatel';

/** Les trois valeurs fixes. `utm_content` vaut le slug, il n'est pas ici. */
export const P2C_UTM = Object.freeze({
  utm_source: 'partenaire',
  utm_medium: 'referral',
  utm_campaign: 'essai_neuchatel',
});

/** Le slug est-il acceptable ? MÊME règle que le serveur, mot pour mot. */
export function p2bSlugValide(slug) {
  return P2C_MOTIF_SLUG.test(String(slug || ''));
}

/** Suggestion de slug à partir d'un nom. Le coach peut TOUJOURS la corriger.
 *
 *  Les accents sont dépliés (NFD) plutôt que supprimés : « Récif » donne
 *  `recif`, pas `rcif`. Tout ce qui n'est pas [a-z0-9] devient `_`, les `_`
 *  consécutifs sont fondus, et le résultat est borné à 40 caractères — la même
 *  règle que le serveur, qui reste le seul à décider si un slug est valide.
 */
export function p2bSuggererSlug(nom) {
  return String(nom || '')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '')
    .slice(0, 40);
}

/** Le lien personnel du partenaire, ou '' si le slug ne vaut rien.
 *
 *  FONCTION PURE : elle ne lit ni le `localStorage`, ni l'heure, ni la page ;
 *  elle n'écrit rien. Deux appels avec le même slug rendent la même chaîne,
 *  ce qui est exactement ce qu'un test peut figer.
 *
 *  Renvoie '' plutôt que de fabriquer un lien approximatif : un lien partenaire
 *  faux est pire que pas de lien du tout — il partirait chez un commerçant qui
 *  l'afficherait, et l'attribution ne reviendrait jamais.
 */
export function construireLienPartenaire(partnerSlug) {
  const slug = String(partnerSlug || '').trim();
  if (!p2bSlugValide(slug)) return '';
  const parametres = [
    ['utm_source', P2C_UTM.utm_source],
    ['utm_medium', P2C_UTM.utm_medium],
    ['utm_campaign', P2C_UTM.utm_campaign],
    ['utm_content', slug],
  ].map(([cle, valeur]) => `${cle}=${encodeURIComponent(valeur)}`).join('&');
  return `${P2C_BASE_ESSAI}?${parametres}`;
}

/** Nom du fichier QR téléchargé. Lisible, sans espace, reconnaissable dans un
 *  dossier de téléchargements où le coach en aura plusieurs. */
export function p2cNomFichierQr(partnerSlug) {
  const slug = String(partnerSlug || '').trim();
  return p2bSlugValide(slug) ? `afroboost-partenaire-${slug}-qr.png` : '';
}
