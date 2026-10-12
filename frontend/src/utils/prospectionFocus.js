/**
 * PROSPECTION FOCUS — LES QUATRE PHRASES QUE L'ÉCRAN DOIT SAVOIR DIRE.
 * ===================================================================
 *
 * CE FICHIER NE CONTIENT QUE DES FONCTIONS PURES. Aucune requête, aucun état,
 * aucun rendu : uniquement la traduction de faits déjà établis par le serveur
 * en phrases lisibles. C'est ce qui permet de les prouver une par une, sans
 * monter un composant.
 *
 * CE QU'IL NE FAIT PAS, ET C'EST L'ESSENTIEL : il ne DÉDUIT jamais qu'un
 * e-mail est parti. `derniere_reponse_afroboost` vient de `prospect_reply_sends`
 * — la trace écrite par AI-P4 après un envoi accepté par le fournisseur. Son
 * absence n'est pas une incertitude : c'est la preuve que rien n'est parti, et
 * l'écran l'écrit noir sur blanc.
 *
 * POURQUOI DEUX PHRASES ET PAS UNE. « EN ATTENTE » (statut commercial, AI-P3)
 * répond à « qu'est-ce que je dois faire ? ». « Réponse envoyée le… » répond à
 * « qu'est-ce qui est parti ? ». Bassi lisait la première en croyant la
 * seconde. Elles ne se calculent pas ensemble et ne s'affichent pas ensemble.
 */

/* Les statuts qui appellent encore un geste. Même liste que côté serveur
   (`pf_rang`) : un dossier en attente, refusé ou traité n'attend rien de nous. */
export const STATUTS_ACTION = ['a_repondre', 'appel_a_faire'];

/* Une date illisible rend '' — jamais « Invalid Date », jamais aujourd'hui.
   Se tromper de date sur un historique commercial est pire que ne rien dire. */
function versDate(iso) {
  const texte = String(iso || '').trim();
  if (!texte) return null;
  const d = new Date(texte);
  return Number.isNaN(d.getTime()) ? null : d;
}

const deuxChiffres = (n) => String(n).padStart(2, '0');

/** « 06/09 » — ce qui tient sur une ligne de file compacte. */
export function jourMois(iso) {
  const d = versDate(iso);
  if (!d) return '';
  return `${deuxChiffres(d.getDate())}/${deuxChiffres(d.getMonth() + 1)}`;
}

/** « 06/09 à 15:05 » — la précision utile quand on lit UN dossier. */
export function jourHeure(iso) {
  const d = versDate(iso);
  if (!d) return '';
  return `${jourMois(iso)} à ${deuxChiffres(d.getHours())}:${deuxChiffres(d.getMinutes())}`;
}

/** Ce dossier attend-il encore un geste de notre part ? */
export function attendUneAction(conversation) {
  const statut = (conversation && conversation.statut_commercial) || 'a_repondre';
  return STATUTS_ACTION.indexOf(statut) !== -1;
}

/**
 * L'ÉTAT D'ENVOI, EN UNE PHRASE FACTUELLE. Trois cas, trois codes :
 *
 *   `envoyee`  — une réponse est partie APRÈS le dernier message reçu ;
 *   `a_repondre` — le partenaire a écrit, rien n'est parti depuis ;
 *   `attente`  — rien à envoyer : la balle est chez lui, ou le dossier est clos.
 *
 * LE CAS QUI COMPTE EST LE DEUXIÈME, et il est réel : le BDE HE-Arc a reçu une
 * réponse le 05/09 à 15:05, puis a réécrit le même jour à 16:45. Une réponse
 * existe donc bien — mais elle ne répond pas au dernier message. Dire
 * « réponse envoyée » ici ferait passer un dossier actif pour un dossier clos.
 */
export function etatReponse(conversation) {
  const c = conversation || {};
  const envoi = c.derniere_reponse_afroboost || null;
  // V608 — le DERNIER envoi suivi, s'il est plus récent que la dernière réponse REMISE :
  // accepté ≠ remis ; un échec, un quota ou un rebond laissent la conversation « à répondre ».
  const suivi = c.envoi_suivi || null;
  if (suivi && suivi.etat !== 'remis' && (!envoi || String(suivi.quand || '') > String(envoi.sent_at || ''))) {
    const raison = suivi.raison && suivi.etat === 'echec' ? ` (${String(suivi.raison).slice(0, 80)})` : '';
    const TEXTES = {
      envoi_en_cours: { code: 'en_cours', texte: 'Envoi en cours — remise pas encore confirmée' },
      en_preparation: { code: 'en_cours', texte: 'Envoi en préparation' },
      indetermine: { code: 'a_repondre', texte: 'Envoi incertain — vérifier avant de réessayer' },
      echec: { code: 'a_repondre', texte: `Échec d\u2019envoi${raison} — la réponse n\u2019est pas partie`, reessai: true },
      quota: { code: 'a_repondre', texte: 'Non envoyé — quota Resend atteint', reessai: true },
      rebond: { code: 'a_repondre', texte: 'Rebond — l\u2019adresse n\u2019a pas reçu la réponse' },
      plainte: { code: 'a_repondre', texte: 'Plainte / spam signalée par le destinataire' },
    };
    if (TEXTES[suivi.etat]) return TEXTES[suivi.etat];
  }
  if (c.reponse_apres_dernier_message && envoi && envoi.sent_at) {
    return {
      code: 'envoyee',
      texte: suivi && suivi.etat === 'remis'
        ? `Réponse Afroboost remise le ${jourHeure(envoi.sent_at)}`
        : `Réponse Afroboost envoyée le ${jourHeure(envoi.sent_at)}`,
    };
  }
  if (attendUneAction(c)) {
    return {
      code: 'a_repondre',
      texte: envoi && envoi.sent_at
        ? 'À répondre — aucune réponse Afroboost envoyée après ce message'
        : 'À répondre — aucune réponse Afroboost envoyée',
    };
  }
  return {
    code: 'attente',
    texte: 'Aucune réponse nécessaire — en attente du partenaire',
  };
}

/** « Dernière réponse Afroboost : … » — la ligne factuelle du §6. */
export function ligneDernierEnvoi(conversation) {
  const envoi = (conversation || {}).derniere_reponse_afroboost || null;
  return envoi && envoi.sent_at
    ? `Réponse envoyée le ${jourHeure(envoi.sent_at)}`
    : 'Aucune réponse envoyée.';
}

/**
 * LA CONVERSATION SUIVANTE À TRAITER, ou `null`.
 *
 * ELLE NE S'OUVRE PAS TOUTE SEULE et n'envoie rien : elle est PROPOSÉE. La
 * liste arrive déjà triée par le serveur (`pf_conversations`) — on prend donc
 * la première qui attend un geste et qui n'est pas celle qu'on vient de
 * traiter, sans réordonner quoi que ce soit ici.
 */
export function suivanteATraiter(conversations, cleCourante) {
  const liste = conversations || [];
  for (let i = 0; i < liste.length; i += 1) {
    if (liste[i].cle !== cleCourante && attendUneAction(liste[i])) return liste[i];
  }
  return null;
}
