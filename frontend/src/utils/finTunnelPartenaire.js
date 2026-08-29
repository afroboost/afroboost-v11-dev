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

/* ═════════════ P1.2-UXFINAL — DIAGNOSTIC RESEAU NON SENSIBLE ════════════════ */

/** Le `fetch` lui-meme a jete : rien n'est parti, ou rien n'est revenu. */
export const P12_CODE_FETCH = 'NET-FETCH';

/** Prefixe affiche sous le message d'erreur. */
export const P12_DIAG_PREFIXE = 'Code diagnostic : ';

/**
 * Construit un code diagnostic a partir de la SEULE enveloppe HTTP.
 *
 * POURQUOI CE CODE EXISTE. Deux incidents partenaire le 29/08, deux fois zero
 * preuve : la requete n'avait jamais atteint FastAPI (aucune ligne uvicorn,
 * aucune entree dans `smart_entry_attempts`), et le navigateur du prospect
 * n'avait rien garde. Impossible de dire si Cloudflare avait bloque, si un
 * proxy avait rendu une page HTML, ou si le telephone avait perdu le reseau.
 * Un code court, lisible a voix haute au telephone, rend le prochain incident
 * diagnosticable en une phrase.
 *
 * CE QU'IL NE CONTIENT JAMAIS. Il est fabrique uniquement avec le statut HTTP
 * et la famille du `Content-Type`. Ni le corps de la reponse, ni l'URL, ni le
 * nom, l'e-mail, le telephone, le `submission_id`, le `participant_id` ou le
 * `session_id` ne peuvent y entrer : ces valeurs ne sont pas des parametres de
 * cette fonction. C'est structurel, pas une precaution de redaction.
 *
 * @param {number} status      le statut HTTP de la reponse
 * @param {string} contentType l'en-tete `Content-Type` brut, ou ''
 * @returns {string} ex. `HTTP-403-HTML`, `HTTP-502-HTML`, `HTTP-503`
 */
export function p12CodeDiagnostic(status, contentType) {
  try {
    var n = parseInt(status, 10);
    // Un statut hors norme HTTP ne renseigne rien : on le dit plutot que
    // d'imprimer un nombre fantaisiste dans l'interface du prospect.
    if (!isFinite(n) || n < 100 || n > 599) return 'HTTP-INCONNU';
    var ct = (typeof contentType === 'string') ? contentType.toLowerCase() : '';
    // `text/html`, `application/xhtml+xml` : une PAGE a repondu a la place de
    // l'API — signature d'un proxy (challenge Cloudflare, page d'erreur).
    var estPage = ct.indexOf('html') !== -1;
    return 'HTTP-' + n + (estPage ? '-HTML' : '');
  } catch (e) {
    return 'HTTP-INCONNU';
  }
}

/* ═════════════ P1.2-UXFINAL — TEXTES DU TUNNEL PARTENAIRE ═══════════════════ */

/**
 * L'intro partenaire, ecrite pour quelqu'un qui ne connait PAS Afroboost.
 * `detail` est REPLIE par defaut : sur un telephone, un pave de texte au
 * chargement fait fermer l'onglet avant la premiere question.
 */
export const P12_INTRO_PARTENAIRE = {
  titre: 'Et si vous proposiez à vos clients ou membres une expérience qu’ils n’ont encore jamais vécue ? 🎧🔥',
  texte: 'Afroboost mélange danse afro, fitness et musique au casque dans une expérience immersive, fun et accessible à tous.',
  detail1: 'Nous sélectionnons quelques partenaires à Neuchâtel pour tester pendant 30 jours une collaboration gratuite et sans engagement : visibilité croisée, création de contenu, événement ou découverte Afroboost pour votre communauté.',
  detail2: 'L’objectif : créer de la valeur ensemble et mesurer les résultats, sans engagement à long terme.',
  plus: '… Lire plus',
  moins: 'Lire moins',
  sousTitre: 'Voyons en 1 minute si une collaboration est possible 🤝',
};

/**
 * L'ecran de fin partenaire.
 *
 * CE QU'IL REMPLACE. L'ecran C2-G annoncait « On te confirme ton cours d'essai
 * sur WhatsApp » — mesure le 29/08 sur le parcours partenaire reel. Un gerant
 * de salon qui propose une collaboration ne reserve pas un cours d'essai : la
 * phrase promettait autre chose que ce qui allait arriver.
 */
export const P12_FIN_PARTENAIRE = {
  titre: 'Merci 🙌',
  corps: 'Votre demande de collaboration a bien été enregistrée.',
  suite: 'Bassi la consultera personnellement et vous contactera si une collaboration est pertinente.',
  signature: 'À bientôt,',
  marque: 'Afroboost 🎧🔥',
};

/**
 * Ce qu'un ecran partenaire ne doit JAMAIS dire. Un partenaire n'achete rien
 * et ne reserve rien — toute promesse de ce registre est fausse chez lui.
 * Liste exportee pour que le banc puisse la faire respecter texte par texte.
 */
export const P12_MOTS_INTERDITS_PARTENAIRE = [
  'cours d’essai', 'cours d\'essai', 'essai gratuit',
  'réserv', 'code promo', 'paiement', 'payer', 'abonnement',
];

/** Un texte destine a un partenaire contient-il une promesse interdite ? */
export function p12PromesseInterdite(texte) {
  try {
    if (typeof texte !== 'string') return '';
    var bas = texte.toLowerCase();
    for (var i = 0; i < P12_MOTS_INTERDITS_PARTENAIRE.length; i++) {
      if (bas.indexOf(P12_MOTS_INTERDITS_PARTENAIRE[i].toLowerCase()) !== -1) {
        return P12_MOTS_INTERDITS_PARTENAIRE[i];
      }
    }
    return '';
  } catch (e) {
    return '';
  }
}
