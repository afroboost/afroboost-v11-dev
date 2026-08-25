/**
 * ESSAI-7 — DU CODE OBTENU A LA SEANCE RESERVEE.
 *
 * Deux decisions, deux fonctions pures, zero reseau :
 *
 *   1. `cibleRedirectionEssai` — OU envoyer la personne apres `POST
 *      /checkout/free`. C'est le seul endroit du frontend autorise a fabriquer
 *      une URL `/espace/...`. Elle n'accepte QUE le code renvoye par le
 *      serveur : ni le localStorage, ni la saisie, ni une reconstruction.
 *      Un echec de checkout ne doit produire AUCUNE cible — une redirection
 *      apres un refus anti-2e-essai ferait croire a un octroi qui n'a pas eu
 *      lieu.
 *
 *   2. `etatEssaiAffiche` — QUEL etat l'espace participant doit montrer. Le
 *      serveur derive l'etat au CHARGEMENT (`t2_etat_essai`) ; une reservation
 *      faite juste apres n'y figure donc pas encore. Sans cette fonction,
 *      l'ecran continuerait a crier « Choisis ta seance » a quelqu'un qui vient
 *      precisement d'en choisir une.
 *
 * Le serveur reste l'AUTORITE : ces fonctions ne decident jamais qu'un essai
 * existe, elles lisent ce qu'il a repondu.
 */
import {
  cibleRedirectionEssai,
  etatEssaiAffiche,
  MOTIF_CODE_AFR
} from '../essaiReservation';

const REPONSE_OK = {
  success: true,
  free: true,
  transaction_id: 'free_abcdef123456',
  access_code: 'AFR-2287CA',
  message: 'Réservation confirmée gratuitement !'
};

// --------------------------------------------------------------------------
describe('cibleRedirectionEssai — succes', () => {
  test('renvoie /espace/<CODE> a partir du code du serveur, et de lui seul', () => {
    expect(cibleRedirectionEssai(REPONSE_OK)).toBe('/espace/AFR-2287CA');
  });

  test('normalise la casse sans jamais inventer de caracteres', () => {
    expect(cibleRedirectionEssai({ ...REPONSE_OK, access_code: ' afr-2287ca ' }))
      .toBe('/espace/AFR-2287CA');
  });

  test('le motif du code est celui du serveur : AFR- puis 6 caracteres', () => {
    expect(MOTIF_CODE_AFR.test('AFR-2287CA')).toBe(true);
    expect(MOTIF_CODE_AFR.test('AFR-2287C')).toBe(false);
    expect(MOTIF_CODE_AFR.test('AFR-2287CAZ')).toBe(false);
    expect(MOTIF_CODE_AFR.test('BSS-2287CA')).toBe(false);
  });
});

// --------------------------------------------------------------------------
describe('cibleRedirectionEssai — aucune redirection sans octroi prouve', () => {
  test('checkout en erreur : rien', () => {
    expect(cibleRedirectionEssai(undefined)).toBeNull();
    expect(cibleRedirectionEssai(null)).toBeNull();
    expect(cibleRedirectionEssai({})).toBeNull();
  });

  test('refus anti-2e-essai (pas de success) : rien', () => {
    // Le backend repond 400/409 : axios part dans le `catch` et rien n'arrive
    // ici. Mais si un jour une reponse 200 sans octroi passait, elle ne doit
    // PAS rediriger : ce serait annoncer un essai qui n'a pas ete accorde.
    expect(cibleRedirectionEssai({ detail: 'Essai déjà utilisé.' })).toBeNull();
    expect(cibleRedirectionEssai({ success: false, access_code: 'AFR-2287CA' }))
      .toBeNull();
  });

  test('succes SANS code : rien, jamais de 404', () => {
    // Deux situations REELLES produisent ce cas, et aucune ne doit rediriger :
    //   - le backend n'est pas encore deploye (champ absent) ;
    //   - ESSAI-7 a refuse de rendre le code parce que l'adresse a deja un
    //     passe (`espace_vierge` faux). L'essai EST accorde, mais le code ne
    //     part que par e-mail — exactement comme avant Option B.
    expect(cibleRedirectionEssai({ success: true, free: true })).toBeNull();
    expect(cibleRedirectionEssai({ success: true, access_code: null })).toBeNull();
    expect(cibleRedirectionEssai({ success: true, access_code: '' })).toBeNull();
  });

  test('debit depasse (429) : axios part dans le catch, rien a rediriger', () => {
    // Par securite, meme si une reponse 429 arrivait ici, elle ne porte
    // ni `success`, ni code.
    expect(cibleRedirectionEssai({ detail: 'Trop de demandes depuis cette connexion.' }))
      .toBeNull();
  });

  test('code de forme inattendue : rien', () => {
    ['AFR-', 'AFR-12345', 'AFR-12345678', 'PROMO10', '../admin',
     'AFR-2287CA/../x', 42, {}, []].forEach((valeur) => {
      expect(cibleRedirectionEssai({ success: true, access_code: valeur })).toBeNull();
    });
  });

  test('une valeur hostile ne peut pas sortir de /espace/', () => {
    const cible = cibleRedirectionEssai({
      success: true,
      access_code: 'AFR-ABCDEF?next=https://ailleurs.test'
    });
    expect(cible).toBeNull();
  });
});

// --------------------------------------------------------------------------
describe('etatEssaiAffiche — un forfait payant n est pas un essai', () => {
  test('sans bloc trial : aucun etat d essai', () => {
    expect(etatEssaiAffiche(null, 0)).toBeNull();
    expect(etatEssaiAffiche(undefined, 3)).toBeNull();
    expect(etatEssaiAffiche({ is_trial: false }, 0)).toBeNull();
  });
});

describe('etatEssaiAffiche — les trois etats', () => {
  test('essai accorde, rien de reserve : disponible', () => {
    expect(etatEssaiAffiche({ is_trial: true, state: 'available' }, 0))
      .toBe('available');
  });

  test('le serveur dit reserve : reserve', () => {
    expect(etatEssaiAffiche({ is_trial: true, state: 'booked' }, 0))
      .toBe('booked');
  });

  test('le serveur dit effectue : effectue, meme avec une seance a venir', () => {
    expect(etatEssaiAffiche({ is_trial: true, state: 'done' }, 1)).toBe('done');
  });

  test('reservation faite APRES le chargement : reserve, sans rechargement', () => {
    // Le cas qui motive la fonction. `t2_etat_essai` a repondu « available »
    // au chargement ; la personne vient de reserver ; l'ecran doit basculer.
    expect(etatEssaiAffiche({ is_trial: true, state: 'available' }, 1))
      .toBe('booked');
  });

  test('un etat inconnu du serveur ne fait pas disparaitre l essai', () => {
    expect(etatEssaiAffiche({ is_trial: true, state: 'zzz' }, 0)).toBe('available');
    expect(etatEssaiAffiche({ is_trial: true }, 0)).toBe('available');
  });

  test('un nombre de reservations aberrant ne casse rien', () => {
    expect(etatEssaiAffiche({ is_trial: true, state: 'available' }, null))
      .toBe('available');
    expect(etatEssaiAffiche({ is_trial: true, state: 'available' }, 'deux'))
      .toBe('available');
    expect(etatEssaiAffiche({ is_trial: true, state: 'available' }, -1))
      .toBe('available');
  });
});
