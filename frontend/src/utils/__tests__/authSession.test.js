/**
 * P0-SOCLE — tests de la stratégie d'authentification unique.
 *
 * HORS LIGNE. Aucun réseau, aucune écriture en base. On pilote uniquement le
 * localStorage simulé, exactement comme le navigateur du coach le ferait.
 */

import {
  AUTH,
  etatAuth,
  authValide,
  signatureRequise,
  classerEchec,
  terminerSession,
  abonnerAuth,
  debutConnexion,
  finConnexion,
  _reinitialiserConnexions,
} from '../authSession';

// Un jeton dont on maîtrise `exp`. La signature n'est jamais vérifiée côté
// navigateur (seul le serveur juge) — seule la charge utile compte ici.
function jeton(expSecondes) {
  const entete = btoa(JSON.stringify({ alg: 'HS256' }));
  const charge = btoa(JSON.stringify({ email: 'coach@test.ch', exp: expSecondes }));
  return `${entete}.${charge}.signature-factice`;
}

const DANS_UNE_HEURE = () => Math.floor(Date.now() / 1000) + 3600;
const IL_Y_A_UNE_HEURE = () => Math.floor(Date.now() / 1000) - 3600;

beforeEach(() => {
  localStorage.clear();
  _reinitialiserConnexions();
});

describe('etatAuth — les quatre états', () => {
  test('ANONYME : rien en poche, personne ne prétend être connecté', () => {
    expect(etatAuth()).toBe(AUTH.ANONYME);
    expect(authValide()).toBe(false);
  });

  test('VALIDE : jeton signé non expiré', () => {
    localStorage.setItem('afroboost_jwt', jeton(DANS_UNE_HEURE()));
    expect(etatAuth()).toBe(AUTH.VALIDE);
    expect(authValide()).toBe(true);
  });

  test('EXPIREE : jeton présent mais périmé', () => {
    localStorage.setItem('afroboost_jwt', jeton(IL_Y_A_UNE_HEURE()));
    expect(etatAuth()).toBe(AUTH.EXPIREE);
    expect(authValide()).toBe(false);
  });

  test('EXPIREE : SESSION ZOMBIE — le mode coach survit sans aucun jeton', () => {
    // Exactement l'état laissé par l'ancien intercepteur V345 : il effaçait le
    // jeton et gardait `afroboost_coach_user`. L'interface se croyait connectée.
    localStorage.setItem('afroboost_coach_mode', 'true');
    localStorage.setItem('afroboost_coach_user', JSON.stringify({ email: 'coach@test.ch' }));
    expect(etatAuth()).toBe(AUTH.EXPIREE);
    expect(authValide()).toBe(false);
  });

  test('EN_COURS : une connexion est en vol, on ne conclut pas', () => {
    debutConnexion();
    expect(etatAuth()).toBe(AUTH.EN_COURS);
    expect(authValide()).toBe(false);
    finConnexion();
    expect(etatAuth()).toBe(AUTH.ANONYME);
  });

  test('EN_COURS prime sur un jeton expiré déjà présent (reconnexion en cours)', () => {
    localStorage.setItem('afroboost_jwt', jeton(IL_Y_A_UNE_HEURE()));
    debutConnexion();
    expect(etatAuth()).toBe(AUTH.EN_COURS);
    finConnexion();
    expect(etatAuth()).toBe(AUTH.EXPIREE);
  });

  test('un jeton illisible ne verrouille pas dehors — le serveur tranchera', () => {
    // Règle de prudence héritée de V345 : on n'échoue jamais « fermé » sur un
    // détail de format. Sans `exp` lisible, le jeton est réputé utilisable.
    localStorage.setItem('afroboost_jwt', 'pas-du-tout-un-jwt-mais-assez-long');
    expect(etatAuth()).toBe(AUTH.VALIDE);
  });
});

describe('signatureRequise — le portillon ne bloque QUE le prouvé', () => {
  test.each([
    '/api/users',
    '/api/discount-codes',
    '/api/contacts/all',
    '/api/dashboard/all-transactions',
    '/api/credit-transactions',
    '/api/trash',
    '/api/coach/notifications',
    '/api/chat/groups',
  ])('%s exige une signature', (url) => {
    expect(signatureRequise(url)).toBe(true);
  });

  test.each([
    '/api/reservations?page=1&limit=20',
    '/api/chat/sessions',
    '/api/courses?scope=mine',
    '/api/offers?scope=mine',
    '/api/concept',
    '/api/payment-links',
    '/api/contact-categories',
    '/api/google-contacts/status',
  ])('%s NE doit PAS être bloquée côté navigateur', (url) => {
    expect(signatureRequise(url)).toBe(false);
  });

  test('/reservations reste ouverte : le serveur y accepte le repli X-User-Email', () => {
    // Mesuré en production : 200 avec X-User-Email seul. La bloquer priverait
    // de leurs réservations toutes les sessions sans jeton signé (règle V310c).
    expect(signatureRequise('/api/reservations')).toBe(false);
  });

  test('la chaîne de requête et le domaine absolu ne trompent pas le portillon', () => {
    expect(signatureRequise('https://afroboost.com/api/users?page=2')).toBe(true);
    expect(signatureRequise('/api/users/sous-route')).toBe(true);
  });

  test('une URL vide ou absente ne déclenche aucun blocage', () => {
    expect(signatureRequise('')).toBe(false);
    expect(signatureRequise(undefined)).toBe(false);
  });
});

describe('classerEchec — distinguer la ressource de la session', () => {
  test('aucune réponse -> reseau', () => {
    expect(classerEchec({ message: 'Network Error' })).toBe('reseau');
  });

  test('401 -> session, toujours', () => {
    localStorage.setItem('afroboost_jwt', jeton(DANS_UNE_HEURE()));
    expect(classerEchec({ response: { status: 401 } })).toBe('session');
  });

  test('403 SANS preuve signée -> session (cas B : preuve globale invalide)', () => {
    localStorage.setItem('afroboost_coach_mode', 'true');
    expect(classerEchec({ response: { status: 403 } })).toBe('session');
  });

  test('403 AVEC preuve signée valide -> droit (cas A : ressource secondaire)', () => {
    localStorage.setItem('afroboost_jwt', jeton(DANS_UNE_HEURE()));
    expect(classerEchec({ response: { status: 403 } })).toBe('droit');
  });

  test('500 -> serveur, 404 -> introuvable', () => {
    expect(classerEchec({ response: { status: 503 } })).toBe('serveur');
    expect(classerEchec({ response: { status: 404 } })).toBe('introuvable');
  });
});

describe('terminerSession — sortie propre et cohérente', () => {
  test('purge les TROIS clés d\'un bloc, pas seulement le jeton', () => {
    localStorage.setItem('afroboost_jwt', jeton(IL_Y_A_UNE_HEURE()));
    localStorage.setItem('afroboost_coach_user', JSON.stringify({ email: 'x@y.ch' }));
    localStorage.setItem('afroboost_coach_mode', 'true');

    terminerSession('expiree');

    expect(localStorage.getItem('afroboost_jwt')).toBeNull();
    expect(localStorage.getItem('afroboost_coach_user')).toBeNull();
    expect(localStorage.getItem('afroboost_coach_mode')).toBeNull();
    // Et surtout : plus de session zombie. L'état retombe à ANONYME, pas EXPIREE.
    expect(etatAuth()).toBe(AUTH.ANONYME);
  });

  test('prévient les abonnés sans recharger la page', () => {
    const vus = [];
    const desabonner = abonnerAuth((info) => vus.push(info));
    localStorage.setItem('afroboost_coach_mode', 'true');

    terminerSession('expiree');

    expect(vus).toHaveLength(1);
    expect(vus[0].etat).toBe(AUTH.ANONYME);
    expect(vus[0].raison).toBe('expiree');
    desabonner();
  });

  test('le désabonnement coupe réellement la diffusion', () => {
    const vus = [];
    abonnerAuth((info) => vus.push(info))();
    terminerSession('expiree');
    expect(vus).toHaveLength(0);
  });
});
