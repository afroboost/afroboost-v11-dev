// U1b — SUGGESTIONS D'ADRESSE (OpenStreetMap / Nominatim).
//
// POURQUOI CE MODULE EXISTE A PART DU COMPOSANT
// Le service est un TIERS GRATUIT, sans contrat : il peut etre lent, en panne,
// bloque par un pare-feu d'entreprise, ou repondre autre chose que du JSON. La
// regle de ce lot est qu'AUCUNE de ces situations ne doit empecher un coach de
// creer ou de modifier une offre. La seule facon de le PROUVER par un banc de
// test est d'isoler l'appel reseau dans une fonction pure a injecter (`fetch`
// est un parametre), qui ne rejette JAMAIS et retombe sur une liste vide.
//
// POLITIQUE D'USAGE NOMINATIM (https://operations.osmfoundation.org/policies/nominatim/)
//   - MAXIMUM 1 REQUETE PAR SECONDE, tous usages confondus. C'est pourquoi le
//     composant applique un debounce (`DELAI_DEBOUNCE_MS`) ET un intervalle
//     minimal entre deux appels reellement emis (`INTERVALLE_MINI_MS`), au lieu
//     d'un seul des deux : le debounce seul autoriserait deux appels en moins
//     d'une seconde si le coach marque une pause pile a la bonne longueur.
//   - Identification de l'application obligatoire. Depuis un NAVIGATEUR,
//     `User-Agent` et `Referer` sont des en-tetes interdits a `fetch` (le
//     navigateur les pose lui-meme et refuse qu'on les ecrase) : le `Referer`
//     envoye automatiquement vaut donc identification, et c'est le mecanisme
//     que Nominatim documente pour les usages front. On n'envoie AUCUN en-tete
//     personnalise : en poser un declencherait un preflight CORS que Nominatim
//     ne sert pas, et casserait la fonctionnalite.
//   - Pas de pays imposes hors `countrycodes` : on borne la recherche a la
//     Suisse et a ses voisins immediats (le coach est en Suisse).
//
// CE MODULE N'ECRIT RIEN, NE MIGRE RIEN, NE NORMALISE AUCUNE ADRESSE DEJA
// SAISIE. Il ne fait que proposer un texte que le coach reste libre d'ignorer.

export const LONGUEUR_MIN = 3;
export const DELAI_DEBOUNCE_MS = 450;
export const INTERVALLE_MINI_MS = 1100; // > 1 s : politique Nominatim
export const TIMEOUT_MS = 4000;
export const LIMITE_RESULTATS = 5;
export const PAYS = 'ch,fr,de,it,at';
export const BASE_NOMINATIM = 'https://nominatim.openstreetmap.org/search';

/** Espaces multiples ecrases, bords rognes. Ne touche a rien d'autre. */
export function nettoyerTexte(valeur) {
  return String(valeur == null ? '' : valeur).replace(/\s+/g, ' ').trim();
}

/** URL de recherche. Extraite pour etre lisible dans un banc de test. */
export function construireUrl(texte, options) {
  const opts = options || {};
  const params = new URLSearchParams({
    q: nettoyerTexte(texte),
    format: 'jsonv2',
    addressdetails: '1',
    limit: String(opts.limite || LIMITE_RESULTATS),
    countrycodes: opts.pays || PAYS,
    'accept-language': opts.langue || 'fr'
  });
  return `${opts.base || BASE_NOMINATIM}?${params.toString()}`;
}

/**
 * Un libelle COURT et lisible sur un telephone.
 * `display_name` de Nominatim fait souvent 90 caracteres (« Rue des
 * Vallangines, 97, Neuchatel, District de Neuchatel, Neuchatel, 2000,
 * Suisse ») : illisible dans une liste, et deborde horizontalement. On
 * recompose « rue numero, code ville » et on garde le pays seulement quand ce
 * n'est PAS la Suisse.
 */
export function formaterAdresse(item) {
  if (!item || typeof item !== 'object') return '';
  const a = item.address && typeof item.address === 'object' ? item.address : {};
  const rue = [a.road, a.house_number].filter(Boolean).join(' ');
  const ville = a.city || a.town || a.village || a.municipality || a.hamlet || a.suburb || '';
  const tete = rue || item.name || a.amenity || a.building || a.leisure || a.tourism || '';
  const codeVille = [a.postcode, ville].filter(Boolean).join(' ');
  const morceaux = [];
  if (tete) morceaux.push(tete);
  if (codeVille && codeVille !== tete) morceaux.push(codeVille);
  if (a.country && String(a.country_code || '').toLowerCase() !== 'ch') morceaux.push(a.country);
  const libelle = nettoyerTexte(morceaux.join(', '));
  return libelle || nettoyerTexte(item.display_name);
}

/** Ligne secondaire, grisee : de quoi distinguer deux « Gare » homonymes. */
export function formaterDetail(item) {
  if (!item || typeof item !== 'object') return '';
  const a = item.address && typeof item.address === 'object' ? item.address : {};
  return nettoyerTexte([a.state || a.county, a.country].filter(Boolean).join(', '));
}

/**
 * Transforme la reponse brute en propositions. Tolerante : tout ce qui n'est
 * pas un tableau d'objets exploitables devient une liste VIDE, jamais une
 * exception.
 */
export function normaliserReponse(donnees) {
  if (!Array.isArray(donnees)) return [];
  const vus = new Set();
  const out = [];
  for (const item of donnees) {
    const libelle = formaterAdresse(item);
    if (!libelle || vus.has(libelle)) continue;
    vus.add(libelle);
    out.push({
      cle: String((item && (item.place_id || item.osm_id)) || libelle),
      libelle,
      detail: formaterDetail(item)
    });
  }
  return out;
}

/**
 * Cherche des adresses. NE REJETTE JAMAIS.
 *
 * @param {string} texte
 * @param {object} [options] { controleur, fetchImpl, timeout, ...options URL }
 * @returns {Promise<Array<{cle:string,libelle:string,detail:string}>>}
 */
export async function chercherAdresses(texte, options) {
  const opts = options || {};
  const propre = nettoyerTexte(texte);
  if (propre.length < LONGUEUR_MIN) return [];

  const requete = opts.fetchImpl
    || (typeof fetch === 'function' ? (u, i) => fetch(u, i) : null);
  if (!requete) return []; // pas de fetch (vieux navigateur) : silence.

  const controleur = opts.controleur
    || (typeof AbortController === 'function' ? new AbortController() : null);
  let minuteur = null;
  if (controleur && typeof setTimeout === 'function') {
    minuteur = setTimeout(() => {
      try { controleur.abort(); } catch (e) { /* deja avorte : sans effet */ }
    }, opts.timeout || TIMEOUT_MS);
  }

  try {
    const reponse = await requete(construireUrl(propre, opts), {
      method: 'GET',
      // AUCUN en-tete personnalise : cf. l'encadre en tete de fichier.
      signal: controleur ? controleur.signal : undefined
    });
    if (!reponse || reponse.ok === false) return [];
    const donnees = await reponse.json();
    return normaliserReponse(donnees);
  } catch (e) {
    // Panne, timeout, abandon, CORS, JSON illisible : meme reponse, le silence.
    return [];
  } finally {
    if (minuteur) clearTimeout(minuteur);
  }
}
