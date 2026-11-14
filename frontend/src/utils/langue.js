// V670 — Petites fonctions AUTOUR du système de traduction existant (utils/i18n.js).
// Ce n'est PAS un second moteur : aucune traduction n'est écrite ici. On y trouve
// seulement ce qui doit être vrai pour TOUTES les langues, au même endroit :
//   - un code de langue est toujours un code VALIDE (jamais « BAS », « undefined »…) ;
//   - le choix survit au rechargement, à la navigation et à la connexion ;
//   - la page annonce sa langue (<html lang>) aux lecteurs d'écran et aux navigateurs ;
//   - les dates suivent la langue SANS inventer de mot (CLDR via Intl, repli français).
import { CODES_LANGUES, LANGUE_DEFAUT, getLangue } from '../config/translateLangs';

export const CLE_LANGUE = 'af_lang';

// Anciennes valeurs ou sigles visibles qu'un visiteur / un lien / une extension
// pourrait avoir laissés : on les ramène au code technique plutôt que de retomber
// en français sans explication.
const ALIAS = { ba: 'bas', cr: 'ht', bassa: 'bas', kreyol: 'ht', creole: 'ht' };

/** Code technique valide (`fr`…`ht`), quelle que soit l'entrée. Défaut : français. */
export function normaliserLangue(valeur) {
  if (typeof valeur !== 'string') return LANGUE_DEFAUT;
  const brut = valeur.trim().toLowerCase().replace('_', '-');
  if (!brut) return LANGUE_DEFAUT;
  if (CODES_LANGUES.includes(brut)) return brut;
  const base = brut.split('-')[0];            // « en-GB » → « en », « fr-CH » → « fr »
  if (CODES_LANGUES.includes(base)) return base;
  return ALIAS[brut] || ALIAS[base] || LANGUE_DEFAUT;
}

function stockage(s) {
  if (s) return s;
  try { return typeof window !== 'undefined' ? window.localStorage : null; } catch (e) { return null; }
}

/** Langue mémorisée. Un stockage absent, bloqué ou corrompu ne fait jamais planter : français. */
export function lireLangue(s) {
  try {
    const st = stockage(s);
    return normaliserLangue(st ? st.getItem(CLE_LANGUE) : null);
  } catch (e) {
    return LANGUE_DEFAUT;
  }
}

/** Mémorise la langue pour les visites suivantes. Renvoie le code effectivement retenu. */
export function ecrireLangue(code, s) {
  const c = normaliserLangue(code);
  try {
    const st = stockage(s);
    if (st) st.setItem(CLE_LANGUE, c);
  } catch (e) { /* navigation privée / quota : le choix vaut pour la session seulement */ }
  return c;
}

/** Déclare la langue de la page (accessibilité, césure, lecteurs d'écran). */
export function appliquerLangueDocument(code, doc) {
  const d = doc || (typeof document !== 'undefined' ? document : null);
  if (!d || !d.documentElement) return;
  d.documentElement.setAttribute('lang', normaliserLangue(code));
}

/**
 * Vide le stockage du navigateur (déconnexion, « réinitialiser ») SANS perdre la langue.
 *
 * Avant : `localStorage.clear()` à quatre endroits du chat. Ces appels effaçaient AUSSI
 * `af_lang` : un visiteur qui avait choisi le wolof (ou l'allemand) se déconnectait et
 * retrouvait le français. Le choix de langue n'est pas une donnée de session : il
 * appartient à la personne, pas à sa connexion.
 */
export function viderStockagesSaufLangue(local, session) {
  const langue = lireLangue(local);
  try { (local || window.localStorage).clear(); } catch (e) { /* stockage bloqué */ }
  try { (session || window.sessionStorage).clear(); } catch (e) { /* stockage bloqué */ }
  ecrireLangue(langue, local);
  return langue;
}

// ── Dates ──────────────────────────────────────────────────────────────────
// Règle de FIABILITÉ DES RÉSERVATIONS : une date mal rendue fait manquer une
// séance. On ne localise donc que les langues dont l'interface est traduite
// (source / complete / draft) ET que le navigateur connaît réellement (CLDR).
// Pour une langue « partielle », le reste de la phrase est en français : la date
// reste en français aussi, plutôt qu'un mot de jour isolé dans une phrase française.
const LANGUES_DATES_LOCALISEES = new Set(['source', 'complete', 'draft']);

const FR = 'fr-CH';

function localeSupportee(locale) {
  try {
    return Intl.DateTimeFormat.supportedLocalesOf([locale]).length > 0;
  } catch (e) {
    return false;
  }
}

/** Étiquette BCP 47 à utiliser pour les dates de cette langue (repli : fr-CH). */
export function localeDates(code) {
  const l = getLangue(normaliserLangue(code));
  if (!l || !LANGUES_DATES_LOCALISEES.has(l.status)) return FR;
  return localeSupportee(l.locale) ? l.locale : FR;
}

/** `date.toLocaleDateString` dans la langue du visiteur, sans jamais lever d'exception. */
export function formaterDate(date, code, options) {
  const d = date instanceof Date ? date : new Date(date);
  if (Number.isNaN(d.getTime())) return '';
  try {
    return d.toLocaleDateString(localeDates(code), options);
  } catch (e) {
    return d.toLocaleDateString(FR, options);
  }
}

/** Les sept jours (dimanche → samedi), noms CLDR du navigateur. Repli : null (l'appelant garde son tableau). */
export function nomsJoursSemaine(code, style) {
  const loc = localeDates(code);
  if (loc === FR && normaliserLangue(code) !== 'fr') return null;
  try {
    // `timeZone: 'UTC'` : le formateur lit le jour dans le MÊME fuseau que celui où
    // on construit la date. Sans cela, un navigateur en UTC+13 décalerait tous les noms.
    const f = new Intl.DateTimeFormat(loc, { weekday: style || 'long', timeZone: 'UTC' });
    // 4 janvier 1970 = dimanche (jour 0), à midi UTC.
    return [0, 1, 2, 3, 4, 5, 6].map((i) => f.format(new Date(Date.UTC(1970, 0, 4 + i, 12))));
  } catch (e) {
    return null;
  }
}
