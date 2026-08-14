/**
 * analyticsIdentity.js — C9-B : rattacher la visite anonyme a la personne.
 *
 * CE FICHIER EST LE SEUL DU DEPOT AUTORISE A APPELER `posthog.identify()` ET
 * `posthog.reset()`. Un test de source le verifie. La raison n'est pas
 * stylistique : chacun de ces appels peut declencher une FUSION D'IDENTITE
 * IRREVERSIBLE cote PostHog — « Split IDs » ne garantit rien sur le passe. Un
 * second point d'appel, ajoute plus tard ailleurs, ne serait decouvert qu'une
 * fois les profils melanges.
 *
 * POURQUOI SI TARD DANS LE PARCOURS. L'e-mail saisi au tunnel d'essai n'est
 * jamais verifie — pas meme un `@`. Identifier dessus ferait qu'une faute de
 * frappe cree une personne fantome captant tout l'historique anonyme. On
 * attend donc que le serveur ait constate qu'un code INDIVIDUEL appartient a
 * cette adresse, et c'est lui — jamais le navigateur — qui calcule le
 * pseudonyme.
 *
 * CE QUE LE NAVIGATEUR NE FAIT JAMAIS : recalculer le hachage (il faudrait
 * embarquer le sel, donc le rendre public et le pseudonyme re-calculable), ni
 * envoyer la moindre donnee personnelle. `identify()` est appele avec UN SEUL
 * argument — les 2e et 3e parametres de l'API PostHog sont les proprietes de
 * personne, c'est-a-dire la seule voie de fuite possible. Ne jamais les ajouter.
 */

// Pseudonyme serveur : sha256 sale, tronque a 32 hexadecimaux (`posthog_id`,
// api/routes/shared.py). Ce motif est aussi ce qui distingue un identifiant
// POSE PAR NOUS d'un identifiant anonyme de PostHog, qui est un UUID a tirets
// (36 caracteres) — voir `c9bIdentifier`.
export const C9B_FORMAT = /^[0-9a-f]{32}$/;

// Le funnel d'acquisition ne doit jamais contenir le proprietaire du site.
// ⚠️ Liste dupliquee de `ChatWidget.js` (COACH_EMAILS) et `App.js`
// (SUPER_ADMINS) : un test de source verifie qu'elles restent identiques.
export const C9B_EMAILS_COACH = [
  'contact.artboost@gmail.com',
  'afroboost.bassi@gmail.com'
];

function c9bLire(cle) {
  try { return window.localStorage.getItem(cle); } catch (e) { return null; }
}

function c9bPostHog() {
  try {
    if (window.posthog && typeof window.posthog.identify === 'function') return window.posthog;
  } catch (e) { /* PostHog bloque par une extension : cas normal, pas une erreur */ }
  return null;
}

/**
 * Le navigateur est-il en session coach/admin ?
 *
 * ⚠️ On n'utilise PAS `v319CoachAllowed()` : elle renvoie `true` par DEFAUT
 * tant que le drapeau serveur REQUIRE_COACH_JWT est OFF — ce qui est le cas.
 * S'en servir comme test « est coach » repondrait oui pour tout le monde.
 *
 * On prend donc l'union de signaux independants, et on tranche en EXCLUANT au
 * moindre doute : un faux positif coute une personne non mesuree, un faux
 * negatif fusionne l'historique du proprietaire dans la fiche d'un client.
 */
export function c9bSessionCoach(email) {
  if (c9bLire('afroboost_jwt')) return true;                       // seul /auth/login en emet
  if (c9bLire('afroboost_coach_mode') === 'true') return true;
  if (c9bLire('afroboost_coach_user')) return true;
  if (c9bLire('afroboost_admin_persist')) return true;
  // Filet ultime : le seul signal qui ne depende d'aucun etat de session, donc
  // le seul qui tienne sur un navigateur vierge.
  const e = String(email || '').trim().toLowerCase();
  return !!e && C9B_EMAILS_COACH.indexOf(e) !== -1;
}

/**
 * Coupe-circuit. Quand C9-B est eteint, on ne se contente pas de ne plus
 * identifier : on coupe le traitement des personnes pour TOUT le navigateur.
 *
 * C'est ce qui rend l'interrupteur utile APRES coup. Le premier `identify()`
 * ecrit un drapeau persistant dans le navigateur, qui rendrait identifies tous
 * les evenements suivants a vie ; `person_profiles: 'never'` prend le pas sur
 * lui, y compris sur un navigateur deja identifie.
 *
 * ⚠️ Cela n'ANNULE AUCUNE fusion deja produite. Rien ne le peut.
 */
export function c9bCoupeCircuit(actif) {
  const ph = c9bPostHog();
  if (!ph || typeof ph.set_config !== 'function') return false;
  try {
    // `identified_only` est le reglage nominal : aucun profil de personne tant
    // qu'on n'identifie pas. `never` va plus loin et rend `identify()` inerte —
    // c'est pour cela qu'il ne peut PAS etre le reglage permanent.
    ph.set_config({ person_profiles: actif ? 'identified_only' : 'never' });
    return true;
  } catch (e) { return false; }
}

/**
 * Applique l'identite analytique. Renvoie TOUJOURS une chaine decrivant la
 * decision prise — c'est ce qui rend chaque cas testable, y compris les refus.
 *
 * Ne leve jamais : une panne de mesure ne doit pas empecher un abonne d'entrer.
 *
 * Trois cas, et rien d'autre :
 *   1. navigateur anonyme            -> identify()  (la visite anterieure est rattachee)
 *   2. deja identifie, MEME id       -> on ne touche a rien
 *   3. deja identifie, id DIFFERENT  -> reset() PUIS identify()
 *
 * Le cas 3 est le seul qui justifie un `reset()`. En appeler un preventivement
 * detruirait l'identifiant anonyme courant — donc precisement l'historique
 * qu'on cherche a rattacher.
 */
export function c9bIdentifier(analyticsId, options) {
  const opts = options || {};
  try {
    if (!opts.actif) return 'coupe-circuit';
    // Couvre d'un coup : champ absent, chaine vide, null, undefined, nombre,
    // objet, longueur fausse, majuscules, UUID anonyme a tirets. Un objet passe
    // a `identify()` leverait une TypeError NON RATTRAPEE par le SDK.
    if (typeof analyticsId !== 'string' || !C9B_FORMAT.test(analyticsId)) return 'identifiant-invalide';
    if (c9bSessionCoach(opts.email)) return 'coach';

    const ph = c9bPostHog();
    if (!ph) return 'posthog-indisponible';

    // ⚠️ TANT QUE LE VRAI SDK N'EST PAS CHARGE, ON N'IDENTIFIE PAS.
    // Le snippet pose en <head> installe un STUB : ses methodes empilent l'appel
    // et renvoient `undefined` jusqu'a l'arrivee de `array.js`, servi par un hote
    // distinct (souvent lent, parfois filtre). Sans ce garde, `get_distinct_id()`
    // rendrait `undefined` -> on croirait le navigateur anonyme -> on identifierait
    // sans `reset()`. Le vrai SDK rejouerait ensuite la file alors que son
    // identifiant persiste est celui de la personne PRECEDENTE, et fusionnerait
    // l'ancienne dans la nouvelle. Irreversible.
    // Le chemin QR/`?code=` s'auto-connecte sans aucune saisie humaine : il peut
    // parfaitement s'achever avant le chargement du SDK. Ce n'est pas un cas rare.
    // Renoncer coute une identification ; se tromper coute une fusion definitive.
    let courant = '';
    try { courant = String(ph.get_distinct_id() || ''); } catch (e) { courant = ''; }
    if (!courant) return 'sdk-non-charge';

    if (courant === analyticsId) return 'idempotent';

    // Un identifiant courant AU NOTRE FORMAT ne peut venir que d'un `identify()`
    // precedent : c'est une AUTRE personne sur ce navigateur (appareil partage,
    // QR d'un tiers, changement de compte). Sans ce `reset()`, PostHog basculerait
    // silencieusement — sans evenement, sans fusion, et SANS AVERTISSEMENT — et
    // l'historique de la personne precedente suivrait la nouvelle.
    if (C9B_FORMAT.test(courant)) {
      if (typeof ph.reset === 'function') ph.reset();
      ph.identify(analyticsId);
      return 'change';
    }

    // Navigateur anonyme : c'est ici, et seulement ici, que la visite anterieure
    // est rattachee a la personne.
    ph.identify(analyticsId);
    return 'identifie';
  } catch (e) {
    return 'erreur';
  }
}
