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

/* ═══════════════════ P1.2 — SOUMISSION SURE ET MESSAGE HONNETE ═══════════════ */

/**
 * Le message affiche quand la reponse n'est PAS du JSON, ou que la connexion
 * a echoue.
 *
 * POURQUOI IL REMPLACE « Erreur serveur ». Le 29/08, une soumission partenaire
 * a affiche « Erreur serveur » alors que le serveur n'y etait pour rien : la
 * requete n'a JAMAIS atteint FastAPI (aucune trace dans `smart_entry_attempts`,
 * aucun lead, conteneur sain, jamais redemarre). Un proxy a repondu a sa place.
 * Accuser le serveur envoyait le prospect sur une fausse piste et le laissait
 * sans rien faire.
 */
export const P12_MESSAGE_RESEAU =
  'La connexion a été interrompue. Vos réponses sont conservées. Réessayez dans quelques secondes.';

/** Ce lien est-il un lien partenaire ? */
export function p12EstPartenaire(linkData) {
  try {
    if (!linkData || typeof linkData !== 'object' || Array.isArray(linkData)) return false;
    var type = linkData.lead_type;
    if (typeof type !== 'string') return false;
    return type.trim().toLowerCase() === 'partner';
  } catch (e) {
    return false;
  }
}

/**
 * Un identifiant de soumission, genere UNE SEULE FOIS au montage du tunnel.
 *
 * C'EST LUI, ET PAS LE BOUTON, QUI EMPECHE LE DOUBLON. Le bouton porte deja
 * `disabled={loading}` — et deux leads sont quand meme nes a 882 ms d'ecart le
 * 29/08. Une garde d'interface ne survit ni a la touche Entree, ni a une
 * premiere requete qui aboutit avant le second clic. Le serveur, lui, deduplique
 * sur cet identifiant : un rejeu retombe sur le meme document.
 *
 * Il DOIT rester identique pendant toute la vie du tunnel, y compris apres une
 * erreur reseau et un « Reessayer » — le regenerer recreerait le doublon qu'on
 * cherche a eviter.
 */
export function p12NouveauSubmissionId() {
  try {
    if (typeof crypto !== 'undefined' && crypto && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
  } catch (e) { /* repli ci-dessous */ }
  // Repli sans `crypto.randomUUID` (Safari ancien, contexte non securise).
  var hex = '0123456789abcdef';
  var out = '';
  for (var i = 0; i < 36; i++) {
    if (i === 8 || i === 13 || i === 18 || i === 23) { out += '-'; continue; }
    if (i === 14) { out += '4'; continue; }
    var r = Math.floor(Math.random() * 16);
    if (i === 19) r = (r & 0x3) | 0x8;
    out += hex[r];
  }
  return out;
}

/** Forme UUID stricte. Aucune donnee personnelle ne peut satisfaire ce motif. */
export function p12SubmissionIdValide(id) {
  try {
    if (typeof id !== 'string') return false;
    return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(id.trim().toLowerCase());
  } catch (e) {
    return false;
  }
}
