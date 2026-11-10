/**
 * V646 — LES PUBLICATIONS AU SERVICE DE LA CONVERSION. FONCTIONS PURES.
 *
 * CE FICHIER NE DÉCIDE RIEN ET N'APPELLE RIEN. Il traduit trois champs posés
 * par le coach sur une publication — `objectif`, `cta`, `a_la_une` (V646,
 * `PUT /publications/{id}`) — en libellés, en icône et en action à déclencher.
 *
 * LES CINQ DESTINATIONS EXISTENT DÉJÀ, aucune n'est créée ici :
 *   essai / offres -> la section des offres de l'accueil (`uipubReserver`)
 *   seances        -> la fenêtre des séances (`setShowSessionsModal`)
 *   live           -> l'entrée Live de la barre (`ouvrirLiveDepuisLaBarre`)
 *   boutique       -> la section Boutique (`v541AllerA('shop')`)
 * Un CTA ne sait pas naviguer : il NOMME un rappel déjà fourni par la page
 * dans l'objet `actions` du carrousel. Sans ce rappel, le bouton ne s'affiche
 * pas — jamais un bouton qui ne mène nulle part.
 *
 * L'ORDRE DE LA PAGE EST CELUI DU SERVEUR (`GET /publications` trie
 * `a_la_une` puis `created_at`). Rien n'est retrié ici : la page ne fait que
 * filtrer, et un filtre conserve l'ordre reçu. Une seule vérité d'ordre.
 */

/* Les sept objectifs — MIROIR de `V646_OBJECTIFS` (api/server.py). Le serveur
   refuse toute valeur hors de cette liste ; l'écran n'en propose pas d'autre. */
export const OBJECTIFS = [
  { id: 'temoignage', libelle: 'Témoignage / avis' },
  { id: 'motivation', libelle: 'Motivation / progression' },
  { id: 'ambiance', libelle: 'Ambiance de cours' },
  { id: 'concept', libelle: 'Le concept Afroboost' },
  { id: 'benefices', libelle: 'Bénéfices ressentis' },
  { id: 'boutique', libelle: 'Produit en situation' },
  { id: 'live', libelle: 'Live / communauté' },
];

/* Les cinq appels à l'action — MIROIR de `V646_CTAS` (api/server.py).
   `action` = la clé du rappel attendu dans `actions` ; `icone` = un nom déjà
   présent dans SvgIcon (aucune icône ajoutée, aucun emoji). */
export const CTAS = [
  { id: 'essai', libelle: 'Réserver mon cours d’essai', icone: 'ticket', action: 'onReserve' },
  { id: 'seances', libelle: 'Voir les séances', icone: 'calendar', action: 'onSessions' },
  { id: 'live', libelle: 'Rejoindre Afroboost Live', icone: 'video', action: 'onLive' },
  { id: 'boutique', libelle: 'Découvrir la boutique', icone: 'shoppingCart', action: 'onBoutique' },
  { id: 'offres', libelle: 'En savoir plus', icone: 'gift', action: 'onReserve' },
];

const parId = (liste) => liste.reduce((acc, x) => { acc[x.id] = x; return acc; }, {});
const OBJECTIFS_PAR_ID = parId(OBJECTIFS);
const CTAS_PAR_ID = parId(CTAS);

const cle = (v) => (typeof v === 'string' ? v.trim().toLowerCase() : '');

/** Le libellé de l'objectif d'une publication, ou '' si elle n'en porte pas. */
export function objectifLibelle(pub) {
  const o = OBJECTIFS_PAR_ID[cle((pub || {}).objectif)];
  return o ? o.libelle : '';
}

/** `true` si le coach a marqué cette publication « à la une ». */
export function estALaUne(pub) {
  return !!(pub && pub.a_la_une);
}

/**
 * Le CTA RÉELLEMENT AFFICHABLE d'une publication : `{ id, libelle, icone, lancer }`,
 * ou `null`. Rend `null` dès qu'il manque quelque chose — pas de CTA posé, CTA
 * inconnu, ou page qui n'a pas fourni le rappel correspondant. Un bouton qui ne
 * mène nulle part est pire que pas de bouton.
 */
export function ctaDe(pub, actions) {
  const def = CTAS_PAR_ID[cle((pub || {}).cta)];
  if (!def) return null;
  const lancer = (actions || {})[def.action];
  if (typeof lancer !== 'function') return null;
  return { id: def.id, libelle: def.libelle, icone: def.icone, lancer };
}
