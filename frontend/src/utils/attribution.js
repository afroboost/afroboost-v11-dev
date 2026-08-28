/**
 * attribution.js — D'OU VIENT CETTE PERSONNE, et pourquoi on s'en souvient.
 *
 * CE QUE CE MODULE FAIT. Il memorise l'origine d'un visiteur pendant 30 jours,
 * pour qu'une reservation faite trois jours apres un post Instagram soit encore
 * attribuee a Instagram.
 *
 * CE QU'IL NE FAIT PAS, ET C'EST DELIBERE. Il ne decide de rien. Le serveur
 * re-valide TOUT ce qu'il envoie (`m2a_bloc_propre`, api/routes/shared.py) :
 * un `localStorage` bricole a la main ne peut donc pas injecter une source
 * inventee en base. Cette couche est une commodite, pas une autorite.
 *
 * LES TROIS INVARIANTS, tous couverts par `__tests__/attribution.test.js` :
 *
 *   1. UNE PANNE DE SUIVI N'INTERROMPT JAMAIS UN PARCOURS. Tout passe par un
 *      `try` et une valeur de repli. `localStorage` peut etre indisponible
 *      (navigation privee stricte, stockage plein, extension) : c'est un cas
 *      NORMAL, pas une exception.
 *
 *   2. `first` EST FIGE, ET UNE VISITE DIRECTE N'EFFACE RIEN. Sans cette regle,
 *      toute personne revenant une seconde fois deviendrait « direct » et la
 *      mesure ne voudrait plus rien dire. Une visite directe ne remplace donc
 *      NI `first` NI `last`.
 *
 *   3. AUCUNE DONNEE PERSONNELLE, AUCUNE URL COMPLETE. Les valeurs sont
 *      reduites a `[a-z0-9_-]` et tronquees ; du referrer, seul l'HOTE est lu —
 *      jamais l'URL, qui contiendrait la requete tapee dans Google.
 *
 * La liste des sources est FERMEE et volontairement courte : une source
 * nouvelle arrive avec sa page et son lot, jamais par une chaine libre.
 */

/** Cle de stockage. Distincte de `af_funnel_variante` (sessionStorage), qui
 *  mesure la variante d'ENTREE sur un onglet, pas l'origine sur 30 jours. */
export const CLE_ATTRIBUTION = 'af_attribution';

/** 30 jours : assez pour qu'une personne revienne apres un post et un e-mail. */
export const DUREE_MS = 30 * 24 * 60 * 60 * 1000;

const MAX = 64;
const MAX_CHEMIN = 128;

export const SOURCES = [
  'google', 'instagram', 'tiktok', 'youtube', 'facebook',
  'whatsapp', 'partenaire', 'direct',
];

/** Hote -> [source, canal]. `google` est traite a part : domaines regionaux. */
const HOTES = [
  ['instagram.com', 'instagram', 'social'],
  ['tiktok.com', 'tiktok', 'social'],
  ['youtube.com', 'youtube', 'social'],
  ['youtu.be', 'youtube', 'social'],
  ['facebook.com', 'facebook', 'social'],
  ['fb.com', 'facebook', 'social'],
  ['whatsapp.com', 'whatsapp', 'messaging'],
  ['wa.me', 'whatsapp', 'messaging'],
];

/** Un referrer interne n'est PAS une origine. */
const HOTES_INTERNES = ['afroboost.com', 'afroboosteur.com', 'localhost', '127.0.0.1'];

function propre(valeur, maxi) {
  try {
    const brut = valeur === null || valeur === undefined ? '' : String(valeur);
    return brut
      .normalize('NFKD')
      .replace(/[̀-ͯ]/g, '')
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9_-]/g, '')
      .slice(0, maxi || MAX);
  } catch (e) {
    return '';
  }
}

function cheminPropre(valeur) {
  try {
    const brut = valeur === null || valeur === undefined ? '' : String(valeur);
    return brut.split('?')[0].split('#')[0].trim().toLowerCase()
      .replace(/[^a-z0-9/_-]/g, '')
      .slice(0, MAX_CHEMIN);
  } catch (e) {
    return '';
  }
}

/** Le jeton s'il appartient a la liste fermee, sinon la chaine vide. */
export function attributionNormaliser(valeur) {
  const jeton = propre(valeur);
  return SOURCES.indexOf(jeton) === -1 ? '' : jeton;
}

/** (source, canal) deduits de l'HOTE du referrer — jamais de son URL. */
export function attributionDuReferrer(referrer) {
  try {
    const brut = (referrer === null || referrer === undefined ? '' : String(referrer)).trim();
    if (!brut) return null;
    let hote = brut.split('//').pop().split('/')[0].split('?')[0].split('@').pop().split(':')[0]
      .trim().toLowerCase();
    if (!hote || hote.indexOf('.') === -1) return null;
    if (hote.indexOf('www.') === 0) hote = hote.slice(4);
    for (let i = 0; i < HOTES_INTERNES.length; i++) {
      const it = HOTES_INTERNES[i];
      if (hote === it || hote.slice(-(it.length + 1)) === '.' + it) return null;
    }
    if (/(^|\.)google\.[a-z]{2,}(\.[a-z]{2,})?$/.test(hote)) {
      return { source: 'google', medium: 'organic' };
    }
    for (let i = 0; i < HOTES.length; i++) {
      const [cle, src, canal] = HOTES[i];
      if (hote === cle || hote.slice(-(cle.length + 1)) === '.' + cle) {
        return { source: src, medium: canal };
      }
    }
    return null;
  } catch (e) {
    return null;
  }
}

function touche(source, medium, campaign, content, term, chemin) {
  return {
    source: attributionNormaliser(source),
    medium: propre(medium),
    campaign: propre(campaign),
    content: propre(content),
    term: propre(term),
    landing_path: cheminPropre(chemin),
    touch_at: new Date().toISOString(),
  };
}

/**
 * La touche portee par CETTE arrivee, ou `null`.
 * Les UTM explicites gagnent toujours ; le referrer ne sert que faute d'UTM —
 * c'est ce qui rattrape le SEO Google, ou personne ne peut poser d'UTM.
 */
export function attributionDepuisUrl(recherche, referrer, chemin) {
  try {
    let params = { get: () => null };
    try {
      params = new URLSearchParams(recherche || '');
    } catch (e) { /* repli : aucune UTM lisible */ }
    const src = attributionNormaliser(params.get('utm_source'));
    if (src) {
      return touche(src, params.get('utm_medium'), params.get('utm_campaign'),
        params.get('utm_content'), params.get('utm_term'), chemin);
    }
    const duRef = attributionDuReferrer(referrer);
    if (duRef) {
      return touche(duRef.source, duRef.medium, params.get('utm_campaign'),
        params.get('utm_content'), params.get('utm_term'), chemin);
    }
    return null;
  } catch (e) {
    return null;
  }
}

function lireBrut() {
  try {
    const brut = window.localStorage.getItem(CLE_ATTRIBUTION);
    if (!brut) return null;
    const objet = JSON.parse(brut);
    if (!objet || typeof objet !== 'object') return null;
    // 30 jours : au-dela, l'origine ne dit plus rien d'utile.
    if (!objet.at || (Date.now() - objet.at) > DUREE_MS) return null;
    return objet;
  } catch (e) {
    // JSON corrompu, stockage bloque : on repart de zero plutot que de propager.
    return null;
  }
}

/** L'attribution memorisee, ou `null`. Ne leve jamais. */
export function attributionActuelle() {
  const objet = lireBrut();
  if (!objet || (!objet.first && !objet.last)) return null;
  return { first: objet.first || null, last: objet.last || null };
}

/**
 * Enregistre l'arrivee courante et renvoie l'attribution resultante.
 *
 * `first` fige ; `last` remplace UNIQUEMENT par une origine externe. Une visite
 * directe ne touche a rien — c'est l'invariant n°2.
 */
export function attributionEnregistrer(recherche, referrer, chemin) {
  try {
    const neuf = attributionDepuisUrl(recherche, referrer, chemin);
    const ancien = attributionActuelle();
    if (!neuf) return ancien;
    let resultat;
    if (!ancien || !ancien.first) {
      resultat = { first: neuf, last: neuf };
    } else {
      const externe = neuf.source && neuf.source !== 'direct';
      resultat = { first: ancien.first, last: externe ? neuf : (ancien.last || ancien.first) };
    }
    try {
      window.localStorage.setItem(CLE_ATTRIBUTION, JSON.stringify({
        v: 1, at: Date.now(), first: resultat.first, last: resultat.last,
      }));
    } catch (e) { /* stockage indisponible : la mesure est perdue, pas le parcours */ }
    return resultat;
  } catch (e) {
    return null;
  }
}
