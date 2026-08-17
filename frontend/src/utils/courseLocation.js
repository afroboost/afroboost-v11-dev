/**
 * Le lieu d'un cours vit dans DEUX champs, et c'est un piege.
 *
 * `locationName` porte la valeur metier. `location` n'en est qu'un alias, que
 * `GET /courses` recalcule a la lecture — mais que le `PUT` ecrit tel qu'on le
 * lui donne. Renvoyer l'objet entier apres n'avoir modifie que `locationName`
 * figeait donc l'alias sur l'adresse PRECEDENTE : au fil des editions, les deux
 * champs divergent, et l'ecran qui lit l'un contredit celui qui lit l'autre.
 *
 * C'est exactement ce qui s'est produit en production. On aligne donc l'alias
 * avant chaque enregistrement, plutot que de le laisser derailler.
 */

export function alignerLieu(cours) {
  if (!cours || typeof cours !== 'object') return cours;
  const aJour = { ...cours };
  if (typeof aJour.locationName === 'string' && aJour.locationName.trim() !== '') {
    aJour.location = aJour.locationName;
  }
  return aJour;
}

export default alignerLieu;
