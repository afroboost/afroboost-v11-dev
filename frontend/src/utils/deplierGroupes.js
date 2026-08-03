/**
 * deplierGroupes.js — V366
 *
 * POURQUOI CE FICHIER EXISTE
 * --------------------------
 * Une campagne enregistre ses destinataires dans `targetIds`. Quand cette liste ne
 * contient qu'un identifiant de groupe (« grp_ed0b28f8 »), le moteur d'envoi cherche
 * un numéro de téléphone pour cet identifiant, n'en trouve aucun, et la campagne part
 * à ZÉRO destinataire sans le dire. C'est l'état exact de la campagne du 7 août.
 *
 * V364 a corrigé la CRÉATION (cocher un groupe ajoute ses membres). Mais deux chemins
 * continuaient de recopier `targetIds` tel quel : la DUPLICATION et la RÉÉDITION.
 * D'où cette fonction, partagée par les deux.
 *
 * Fonction PURE : elle ne fait aucun appel réseau. Les groupes lui sont fournis par
 * l'appelant (réponse de `GET /api/chat/groups`), ce qui la rend testable sans
 * navigateur ni serveur — voir tests/test_depliage_groupes.mjs.
 */

/** Un identifiant de session de groupe ressemble à « grp_ed0b28f8 ». */
export function estIdentifiantDeGroupe(id) {
  return typeof id === 'string' && id.indexOf('grp_') === 0;
}

/**
 * Retrouve un groupe à partir d'un identifiant de session « grp_xxxxxxxx ».
 * Le backend fabrique cet identifiant à partir des 8 premiers caractères de l'id du
 * groupe (`grp_${group_id[:8]}`) : on accepte donc les deux formes.
 */
function trouverGroupe(identifiant, groupes) {
  return (groupes || []).find(g =>
    g && (g.id === identifiant || `grp_${String(g.id || '').slice(0, 8)}` === identifiant)
  );
}

/**
 * Remplace les identifiants de groupe par les identifiants de leurs membres.
 *
 * RÈGLE DE PRUDENCE — on ne déplie QUE si la campagne ne cible aucune personne.
 * Une campagne « groupe + 25 personnes » est une sélection délibérée : y ajouter les
 * 210 membres du groupe ferait écrire à 185 personnes que le coach n'a jamais
 * choisies. On ne répare donc que le cas réellement cassé (« que des groupes »),
 * jamais celui qui fonctionne déjà.
 *
 * @returns {{ids: string[], deplie: boolean, groupes: number, membres: number, echec: boolean}}
 *   ids     — la liste à enregistrer (inchangée si aucun dépliage n'était justifié)
 *   deplie  — vrai si des membres ont remplacé des identifiants de groupe
 *   groupes — nombre de groupes dépliés
 *   membres — nombre de personnes obtenues
 *   echec   — vrai si un groupe n'a pas pu être résolu (liste laissée intacte)
 */
export function deplierTargetIds(targetIds, groupes) {
  const liste = Array.isArray(targetIds) ? targetIds.filter(Boolean) : [];
  const identifiantsDeGroupe = liste.filter(estIdentifiantDeGroupe);
  const personnes = liste.filter(id => !estIdentifiantDeGroupe(id));

  // Rien à faire : aucune ligne de groupe.
  if (identifiantsDeGroupe.length === 0) {
    return { ids: liste, deplie: false, groupes: 0, membres: 0, echec: false };
  }
  // Cas mixte : des personnes sont déjà ciblées -> on ne touche à rien (cf. règle ci-dessus).
  if (personnes.length > 0) {
    return { ids: liste, deplie: false, groupes: 0, membres: 0, echec: false };
  }

  const membres = [];
  let resolus = 0;
  identifiantsDeGroupe.forEach(identifiant => {
    const groupe = trouverGroupe(identifiant, groupes);
    const ids = (groupe && groupe.member_ids) || [];
    if (ids.length > 0) {
      resolus += 1;
      ids.forEach(id => { if (id) membres.push(id); });
    }
  });

  // Aucun membre récupéré (groupe vide, ou liste des groupes indisponible) : on rend
  // la liste d'origine INTACTE plutôt qu'une campagne sans destinataire.
  if (membres.length === 0) {
    return { ids: liste, deplie: false, groupes: 0, membres: 0, echec: true };
  }

  const uniques = Array.from(new Set(membres)); // dédoublonne en gardant l'ordre
  return {
    ids: uniques,
    deplie: true,
    groupes: resolus,
    membres: uniques.length,
    echec: resolus < identifiantsDeGroupe.length
  };
}

export default deplierTargetIds;
