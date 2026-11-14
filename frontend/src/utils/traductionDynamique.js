// V670 — Traduction À L'AFFICHAGE des contenus PUBLICS rédigés par le coach (nom et
// description d'une offre, nom d'un cours). Réutilise POST /api/translate : aucun second
// moteur, aucun service nouveau.
//
// PRINCIPES (dans l'ordre où ils s'appliquent) :
//   1. L'ORIGINAL N'EST JAMAIS MODIFIÉ. On ne touche ni à la base ni à l'objet : on ne fait
//      qu'afficher autre chose, et l'original reste disponible (infobulle, repli).
//   2. Jamais pour une langue dont l'IA n'est pas fiable (« partial » : lingala, wolof,
//      bambara, bàsàa) : une phrase inventée serait pire que l'original. On affiche l'original.
//   3. Cherche d'abord ce qu'on a DÉJÀ (cache local), puis le serveur (qui a son propre cache
//      persistant et son lexique vérifié), et seulement alors, côté serveur, l'IA.
//   4. Ne retraduit jamais deux fois le même texte : cache local + requêtes en vol dédupliquées.
//   5. Borne la dépense côté navigateur (60 demandes par session) et ne harcèle pas un
//      service en panne (une défaillance met le texte de côté 5 minutes).
//   6. Si quoi que ce soit échoue : le texte d'origine. Jamais d'erreur visible, jamais de blanc.
//
// Ne sert QUE des champs publics. Un message privé (chat) ne passe JAMAIS ici.
import { getLangue } from '../config/translateLangs';
import { normaliserLangue } from './langue';

export const CLE_CACHE_TRADUCTIONS = 'af_trad_v1';
export const MAX_ENTREES_CACHE = 300;
export const BUDGET_PAR_SESSION = 60;
export const PAUSE_APRES_ECHEC_MS = 5 * 60 * 1000;
export const LONGUEUR_MAX = 1500;
export const DELAI_REQUETE_MS = 12000;

/** Une langue pour laquelle on accepte d'afficher une traduction automatique. */
export function langueTraduisible(code) {
  const l = getLangue(normaliserLangue(code));
  return !!l && (l.status === 'complete' || l.status === 'draft');
}

/** Empreinte 53 bits (cyrb53) : la clé de cache n'a pas à contenir le texte. */
export function empreinte(texte) {
  let h1 = 0xdeadbeef;
  let h2 = 0x41c6ce57;
  for (let i = 0; i < texte.length; i += 1) {
    const ch = texte.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(36);
}

const compacter = (t) => String(t).replace(/\s+/g, ' ').trim();

export function cleLocale(lang, texte) {
  const t = compacter(texte);
  return `${normaliserLangue(lang)}:${t.length}:${empreinte(t)}`;
}

function stockageNavigateur() {
  try { return typeof window !== 'undefined' ? window.localStorage : null; } catch (e) { return null; }
}

export function lireCacheLocal(storage) {
  try {
    const st = storage || stockageNavigateur();
    const brut = st ? st.getItem(CLE_CACHE_TRADUCTIONS) : null;
    const obj = brut ? JSON.parse(brut) : {};
    return obj && typeof obj === 'object' && !Array.isArray(obj) ? obj : {};
  } catch (e) {
    return {};
  }
}

export function ecrireCacheLocal(cache, storage) {
  try {
    const st = storage || stockageNavigateur();
    if (!st) return;
    const cles = Object.keys(cache);
    // Au-delà du plafond, on retire les plus anciennes (ordre d'insertion).
    const garde = cles.length > MAX_ENTREES_CACHE ? cles.slice(cles.length - MAX_ENTREES_CACHE) : cles;
    const sortie = {};
    garde.forEach((k) => { sortie[k] = cache[k]; });
    st.setItem(CLE_CACHE_TRADUCTIONS, JSON.stringify(sortie));
  } catch (e) { /* quota / navigation privée : on continue sans cache local */ }
}

/** État partagé par la page (dédoublonnage, budget, pauses). Injectable pour les tests. */
export function creerEtat() {
  return { enVol: new Map(), demandes: 0, echecs: new Map() };
}
const ETAT_PAGE = creerEtat();

function apiParDefaut() {
  return `${process.env.REACT_APP_BACKEND_URL || ''}/api`;
}

/**
 * Cherche la traduction d'un texte PUBLIC. Renvoie toujours `{ texte, auto }` :
 * `auto: true` seulement si `texte` est une traduction ; sinon c'est l'original.
 * Ne lève jamais d'exception.
 */
export async function obtenirTraduction(original, lang, options) {
  const o = options || {};
  const etat = o.etat || ETAT_PAGE;
  const maintenant = o.maintenant || (() => Date.now());
  const brut = typeof original === 'string' ? original : '';
  const source = compacter(brut);
  const cible = normaliserLangue(lang);
  const rien = { texte: original, auto: false };

  if (!source || source.length < 2 || source.length > LONGUEUR_MAX) return rien;
  if (!langueTraduisible(cible)) return rien;                 // fr (source) et langues partielles
  // Un texte sans lettre (« 18:30 », « 12.- ») n'a rien à traduire.
  if (!/[A-Za-zÀ-ÿ]{2,}/.test(source)) return rien;

  const cle = cleLocale(cible, source);
  const cache = lireCacheLocal(o.storage);
  if (cache[cle] && typeof cache[cle] === 'string') return { texte: cache[cle], auto: true };

  const echec = etat.echecs.get(cle);
  if (echec && maintenant() - echec < PAUSE_APRES_ECHEC_MS) return rien;

  if (etat.enVol.has(cle)) return etat.enVol.get(cle);        // la même demande, déjà partie
  if (etat.demandes >= BUDGET_PAR_SESSION) return rien;

  const f = o.fetchImpl || (typeof fetch !== 'undefined' ? fetch : null);
  if (!f) return rien;
  etat.demandes += 1;

  const demande = (async () => {
    let minuteur = null;
    try {
      const ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
      if (ctrl) minuteur = setTimeout(() => ctrl.abort(), o.delai || DELAI_REQUETE_MS);
      const r = await f(`${o.api || apiParDefaut()}/translate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // `cache: true` : contenu PUBLIC, le serveur peut le mémoriser. Sans ce drapeau, il ne le ferait pas.
        body: JSON.stringify({ text: source, target_lang: cible, cache: true }),
        signal: ctrl ? ctrl.signal : undefined,
      });
      if (!r || !r.ok) throw new Error(`HTTP ${r && r.status}`);
      const j = await r.json();
      const traduit = j && typeof j.translation === 'string' ? j.translation.trim() : '';
      // `approximate` : des mots français sont restés dans la traduction. Ce n'est pas
      // une traduction qu'on peut afficher comme telle : l'original vaut mieux.
      if (!traduit || j.approximate) throw new Error('traduction inutilisable');
      const c = lireCacheLocal(o.storage);
      c[cle] = traduit;
      ecrireCacheLocal(c, o.storage);
      return { texte: traduit, auto: true };
    } catch (e) {
      etat.echecs.set(cle, maintenant());
      return rien;
    } finally {
      if (minuteur) clearTimeout(minuteur);
      etat.enVol.delete(cle);
    }
  })();

  etat.enVol.set(cle, demande);
  return demande;
}
