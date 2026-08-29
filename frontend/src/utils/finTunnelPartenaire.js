/**
 * finTunnelPartenaire.js — P1.1-FIX : PARTNER != SUBSCRIBER.
 *
 * CE QUI N'ALLAIT PAS. A la fin d'un tunnel, si la personne est deja connue en
 * base (e-mail ou numero deja vus), le serveur renvoie `proof_required` sous le
 * drapeau SUBSCRIBER_STRICT_ENTRY — actif en production. ChatWidget n'avait
 * qu'UNE porte de sortie propre, l'ecran « votre demande est enregistree », et
 * elle etait reservee a UN SEUL token code en dur : celui du lien d'essai.
 * Tout autre lien — dont « Devenir Partenaire Afroboost » — tombait sur le
 * formulaire ABONNE : code promo, date de naissance, « Valider mon abonnement ».
 *
 * Reclamer un code d'abonne a un gerant de salon qui propose un partenariat,
 * ce n'est pas une friction : c'est la fin de la conversation.
 *
 * LA REGLE EST GENERIQUE, PAS UN CONTOURNEMENT SUR UN TOKEN. On lit `lead_type`,
 * deja charge par le tunnel avant l'affichage et remonte dans
 * `clientData.linkData`. Tout lien partenaire en beneficie — les deux anciens
 * comme les futurs — sans qu'on ait a inscrire un identifiant quelque part.
 *
 * POURQUOI CE MODULE EXISTE PLUTOT QU'UNE CONDITION DANS `ChatWidget.js`.
 * Ce fichier fait 9400 lignes en ES5 et n'est PAS importable par Jest : l'import
 * echoue. Une decision enfouie dedans serait intestable — or c'est exactement le
 * genre de condition qu'il faut pouvoir prouver, cas par cas. Ce module ne
 * contient que la regle, sans etat, sans effet de bord.
 */

/** Le lien d'essai. Son comportement ne change pas d'un iota. */
export const P11_LIEN_ESSAI = 'b83914b4-c5a';

/**
 * Faut-il sortir par l'ecran « demande enregistree » plutot que par le
 * formulaire abonne ?
 *
 * @param {object} reponse  la reponse de `POST /chat/smart-entry`
 * @param {string} linkToken le lien emprunte
 * @param {object} linkData  les donnees du lien (porte `lead_type`)
 * @returns {boolean} true = ecran de confirmation ; false = comportement historique
 */
export function p11FinSansFormulaireAbonne(reponse, linkToken, linkData) {
  try {
    // `acquisition_saved` est le SIGNAL DU SERVEUR : la demande a bien ete
    // conservee. Sans lui on ne promet rien — on ne dit pas « c'est enregistre »
    // quand ca ne l'est pas.
    if (!reponse || reponse.acquisition_saved !== true) return false;
    // Le lien d'essai : strictement le comportement d'avant ce lot.
    if (linkToken === P11_LIEN_ESSAI) return true;
    // La regle generique.
    var type = (linkData && typeof linkData === 'object' && !Array.isArray(linkData))
      ? linkData.lead_type : '';
    if (typeof type !== 'string') return false;
    return type.trim().toLowerCase() === 'partner';
  } catch (e) {
    // Une regle de confort ne fait jamais tomber un parcours.
    return false;
  }
}
