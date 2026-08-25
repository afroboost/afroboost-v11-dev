/**
 * heureCours.js — N2 : l'ecran lit l'heure d'un cours comme le serveur.
 *
 * POURQUOI CE FICHIER EXISTE. Deux formats de date coexistent en base (mesure
 * du 12/08/2026 sur 125 reservations) :
 *     57  « 2026-03-11T17:01:14.738Z »  -> UTC explicite
 *     67  « 2026-05-13T18:30:00 »       -> NAIF, en heure SUISSE
 *
 * `new Date("2026-05-13T18:30:00")` lit la seconde forme dans le fuseau du
 * NAVIGATEUR. A Neuchatel le resultat est juste par accident ; ailleurs il est
 * faux de plusieurs heures. L'ecran deciderait alors d'afficher « Annuler »
 * quand le serveur refuse — le bouton mort que ce lot vient precisement de
 * retirer, reintroduit par la porte de derriere.
 *
 * Le pendant serveur est `n2_instant_reel` (api/routes/shared.py). Les deux
 * appliquent la MEME regle : sans fuseau, c'est de l'heure suisse.
 *
 * AUCUNE DEPENDANCE. `Intl` est disponible partout ou l'application tourne, et
 * il connait seul le passage ete/hiver — un decalage fixe de +2 h serait faux
 * la moitie de l'annee.
 */

export const FUSEAU_COURS = 'Europe/Zurich';

/** Vrai si la chaine porte deja son fuseau (`Z` ou `+HH:MM`). */
const A_UN_FUSEAU = /(Z|[+-]\d{2}:?\d{2})$/;

/**
 * L'instant REEL d'une occurrence, en millisecondes depuis l'epoque.
 *
 * @param {string} iso date de la reservation, telle qu'elle est en base
 * @returns {number} horodatage, ou `NaN` si la date est illisible — on ne
 *          fabrique jamais une date de repli, qui enverrait quelqu'un le
 *          mauvais jour.
 */
export function instantReelCours(iso) {
  if (typeof iso !== 'string' || !iso.trim()) return NaN;
  const brut = iso.trim();

  if (A_UN_FUSEAU.test(brut)) return Date.parse(brut);

  // Date naive : on la lit d'abord COMME SI elle etait en UTC, puis on retire
  // le decalage suisse de ce jour-la. On obtient le decalage en reformatant cet
  // instant dans le fuseau cible : l'ecart entre les deux EST le decalage.
  const commeUtc = Date.parse(brut.slice(0, 19) + 'Z');
  if (Number.isNaN(commeUtc)) return NaN;

  try {
    const parts = {};
    new Intl.DateTimeFormat('en-US', {
      timeZone: FUSEAU_COURS, hour12: false,
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    }).formatToParts(new Date(commeUtc)).forEach((p) => { parts[p.type] = p.value; });

    const relu = Date.UTC(
      Number(parts.year), Number(parts.month) - 1, Number(parts.day),
      Number(parts.hour) % 24, Number(parts.minute), Number(parts.second)
    );
    if (Number.isNaN(relu)) return NaN;
    return commeUtc - (relu - commeUtc);
  } catch (e) {
    // `Intl` sans base de fuseaux (environnement tres restreint) : on retombe
    // sur la lecture du navigateur, qui est le comportement d'avant ce lot.
    return Date.parse(brut);
  }
}

/**
 * Cette occurrence tombe-t-elle AUJOURD'HUI, en heure suisse ?
 *
 * On compare des JOURS CALENDAIRES, pas un ecart d'heures : une seance a 18h30
 * vue a 23h la veille est « demain », pas « dans 19 h ». Et le jour de
 * reference est le jour SUISSE — celui du cours, pas celui du telephone.
 */
export function estAujourdhuiZurich(iso) {
  const instant = instantReelCours(iso);
  if (Number.isNaN(instant)) return false;
  try {
    const jour = (ms) => new Intl.DateTimeFormat('en-CA', {
      timeZone: FUSEAU_COURS, year: 'numeric', month: '2-digit', day: '2-digit',
    }).format(new Date(ms));
    return jour(instant) === jour(Date.now());
  } catch (e) {
    return false;
  }
}
