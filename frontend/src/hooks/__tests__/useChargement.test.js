/**
 * P0-SOCLE — tests du mécanisme de chargement commun.
 *
 * Ces tests REPRODUISENT LE BUG HISTORIQUE avant de vérifier sa disparition.
 * Le cas 1 est la panne exacte décrite dans l'audit : 5 routes en 200, 2 en 403,
 * et un tableau de bord entièrement vide.
 *
 * HORS LIGNE, sans dépendance ajoutée : on rend avec `react-dom/client` et on
 * pilote le DOM directement, comme le fait déjà ReminderRulesCard.test.js.
 * Aucune requête réseau, aucune écriture en base, aucune donnée de production.
 */

import React from 'react';
import { createRoot } from 'react-dom/client';
import useChargement, { SECTION, GLOBAL, reduireGlobal } from '../useChargement';
import { terminerSession, _reinitialiserConnexions, debutConnexion, finConnexion } from '../../utils/authSession';

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

function jeton(decalageSecondes) {
  const entete = btoa(JSON.stringify({ alg: 'HS256' }));
  const charge = btoa(
    JSON.stringify({ email: 'coach@test.ch', exp: Math.floor(Date.now() / 1000) + decalageSecondes })
  );
  return `${entete}.${charge}.factice`;
}

function poserJetonValide() {
  localStorage.setItem('afroboost_jwt', jeton(3600));
}
function poserSessionZombie() {
  // Mode coach persistant SANS jeton : l'état laissé par l'ancien intercepteur.
  localStorage.setItem('afroboost_coach_mode', 'true');
  localStorage.setItem('afroboost_coach_user', JSON.stringify({ email: 'coach@test.ch' }));
}

const ok = (donnees) => Promise.resolve({ data: donnees });
const refus = (statut) => Promise.reject({ response: { status: statut }, isAxiosError: true });
const coupure = () => Promise.reject({ message: 'Network Error' });

/** Rend le hook et expose son dernier retour. */
function monter(construireSources, options) {
  const conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  const racine = createRoot(conteneur);
  const boite = { courant: null, rendus: 0 };

  function Sonde(props) {
    boite.rendus += 1;
    boite.courant = useChargement(construireSources(props), options);
    return null;
  }

  return {
    boite,
    conteneur,
    async rendre(props) {
      await act(async () => {
        racine.render(<Sonde {...(props || {})} />);
      });
    },
    async demonter() {
      await act(async () => {
        racine.unmount();
      });
      conteneur.remove();
    },
  };
}

/** Laisse tourner les promesses en attente + les minuteries. */
async function laisserTourner(ms) {
  await act(async () => {
    jest.advanceTimersByTime(ms || 0);
    await Promise.resolve();
    await Promise.resolve();
  });
}

beforeEach(() => {
  jest.useFakeTimers();
  localStorage.clear();
  _reinitialiserConnexions();
});

afterEach(() => {
  jest.useRealTimers();
});

// ---------------------------------------------------------------------------
// reduireGlobal — la règle qui décide de l'état de l'écran
// ---------------------------------------------------------------------------
describe('reduireGlobal', () => {
  const s = (etat) => ({ etat, motif: '', donnees: undefined });

  test('une seule section en chargement suffit à dire « chargement »', () => {
    expect(reduireGlobal({ a: s(SECTION.OK), b: s(SECTION.CHARGEMENT) })).toBe(GLOBAL.CHARGEMENT);
  });

  test('des succès ET des échecs -> PARTIEL, jamais ERREUR', () => {
    expect(reduireGlobal({ a: s(SECTION.OK), b: s(SECTION.ERREUR) })).toBe(GLOBAL.PARTIEL);
    expect(reduireGlobal({ a: s(SECTION.OK), b: s(SECTION.SESSION) })).toBe(GLOBAL.PARTIEL);
  });

  test('tout en session -> SESSION_EXPIREE (et pas une simple erreur)', () => {
    expect(reduireGlobal({ a: s(SECTION.SESSION), b: s(SECTION.SESSION) })).toBe(
      GLOBAL.SESSION_EXPIREE
    );
  });

  test('tout en échec, motifs mélangés -> ERREUR', () => {
    expect(reduireGlobal({ a: s(SECTION.ERREUR), b: s(SECTION.SESSION) })).toBe(GLOBAL.ERREUR);
  });

  test('tout réussi -> OK', () => {
    expect(reduireGlobal({ a: s(SECTION.OK), b: s(SECTION.OK) })).toBe(GLOBAL.OK);
  });
});

// ---------------------------------------------------------------------------
// CAS 1 — LE BUG HISTORIQUE : 6 succès, 1 refus secondaire
// ---------------------------------------------------------------------------
describe('CAS 1 — succès partiel : les réponses valides ne sont plus jetées', () => {
  test('6 requêtes en 200 + 1 en 403 -> les 6 données sont affichées', async () => {
    poserJetonValide(); // preuve signée valable : le 403 est donc un refus de DROIT
    const vue = monter(() => ({
      reservations: { url: '/api/reservations', appel: () => ok({ data: [1, 2, 3] }) },
      cours: { url: '/api/courses', appel: () => ok(['c1', 'c2']) },
      offres: { url: '/api/offers', appel: () => ok(['o1']) },
      liens: { url: '/api/payment-links', appel: () => ok({ stripe: 'x' }) },
      concept: { url: '/api/concept', appel: () => ok({ appName: 'Afroboost' }) },
      codes: { url: '/api/discount-codes', appel: () => ok(['AFR-1']) },
      contacts: { url: '/api/users', appel: () => refus(403) },
    }));

    await vue.rendre();
    await laisserTourner();

    const r = vue.boite.courant;

    // Les six réussies sont là — c'est précisément ce que Promise.all détruisait.
    expect(r.sections.reservations.etat).toBe(SECTION.OK);
    expect(r.donnees.cours).toEqual(['c1', 'c2']);
    expect(r.donnees.offres).toEqual(['o1']);
    expect(r.donnees.liens).toEqual({ stripe: 'x' });
    expect(r.donnees.concept).toEqual({ appName: 'Afroboost' });
    expect(r.donnees.codes).toEqual(['AFR-1']);

    // La septième est en erreur de SECTION, pas en panne globale.
    expect(r.sections.contacts.etat).toBe(SECTION.ERREUR);
    expect(r.sections.contacts.motif).toBe('droit');
    expect(r.donnees.contacts).toBeUndefined();

    // L'écran est PARTIEL : utilisable, avec une section signalée.
    expect(r.global).toBe(GLOBAL.PARTIEL);

    await vue.demonter();
  });

  test('la panne exacte de l\'audit : /users et /discount-codes en 403', async () => {
    poserJetonValide();
    const vue = monter(() => ({
      reservations: { url: '/api/reservations', appel: () => ok({ data: [] }) },
      cours: { url: '/api/courses', appel: () => ok([]) },
      offres: { url: '/api/offers', appel: () => ok([]) },
      liens: { url: '/api/payment-links', appel: () => ok({}) },
      concept: { url: '/api/concept', appel: () => ok({ primaryColor: '#D91CD2' }) },
      contacts: { url: '/api/users', appel: () => refus(403) },
      codes: { url: '/api/discount-codes', appel: () => refus(403) },
    }));

    await vue.rendre();
    await laisserTourner();
    const r = vue.boite.courant;

    // AVANT ce correctif : les 7 restaient à []. Le concept notamment n'était
    // jamais posé — la vitrine perdait les couleurs personnalisées du coach.
    expect(r.donnees.concept).toEqual({ primaryColor: '#D91CD2' });
    expect(r.sections.reservations.etat).toBe(SECTION.OK);
    expect(r.donnees.liens).toEqual({});

    // Les DEUX seules routes à signature du lot ont été refusées : l'escalade
    // conclut que c'est la PREUVE qui est en cause, pas ces ressources-là.
    // C'est exactement le diagnostic attendu du cas B.
    expect(r.sections.contacts.etat).toBe(SECTION.SESSION);
    expect(r.sections.codes.etat).toBe(SECTION.SESSION);

    // Mais l'écran reste UTILISABLE : cinq sections sur sept sont servies.
    expect(r.global).toBe(GLOBAL.PARTIEL);

    await vue.demonter();
  });
});

// ---------------------------------------------------------------------------
// CAS 2 — l'authentification n'est pas prête
// ---------------------------------------------------------------------------
describe('CAS 2 — aucune requête condamnée ne part prématurément', () => {
  test('AUTH EN COURS : rien ne part, tout reste en chargement', async () => {
    debutConnexion();
    const appels = [];
    const vue = monter(() => ({
      contacts: {
        url: '/api/users',
        appel: () => {
          appels.push('contacts');
          return ok([]);
        },
      },
      cours: {
        url: '/api/courses',
        appel: () => {
          appels.push('cours');
          return ok([]);
        },
      },
    }));

    await vue.rendre();
    await laisserTourner();

    expect(appels).toEqual([]); // on ATTEND, on ne devine pas
    expect(vue.boite.courant.global).toBe(GLOBAL.CHARGEMENT);

    await vue.demonter();
    finConnexion();
  });

  test('quand la connexion se TERMINE, les requêtes parquées partent enfin', async () => {
    // Sans cela, une section parquée en « chargement » pendant AUTH EN_COURS ne
    // repartirait jamais : loader infini, exactement ce que ce lot supprime.
    debutConnexion();
    const appels = [];
    const vue = monter(() => ({
      contacts: {
        url: '/api/users',
        appel: () => { appels.push('contacts'); return ok(['c']); },
      },
      cours: {
        url: '/api/courses',
        appel: () => { appels.push('cours'); return ok(['x']); },
      },
    }));

    await vue.rendre();
    await laisserTourner();
    expect(appels).toEqual([]);
    expect(vue.boite.courant.global).toBe(GLOBAL.CHARGEMENT);

    // La connexion aboutit : un jeton est en poche, l'état redevient connu.
    await act(async () => {
      poserJetonValide();
      finConnexion();
    });
    await laisserTourner();

    expect(appels.sort()).toEqual(['contacts', 'cours']);
    expect(vue.boite.courant.global).toBe(GLOBAL.OK);

    await vue.demonter();
  });

  test('une connexion qui ÉCHOUE ne laisse pas de loader infini non plus', async () => {
    debutConnexion();
    const vue = monter(() => ({
      contacts: { url: '/api/users', appel: () => ok(['c']) },
    }));

    await vue.rendre();
    await laisserTourner();
    expect(vue.boite.courant.global).toBe(GLOBAL.CHARGEMENT);

    // Mauvais mot de passe : aucun jeton posé, l'état retombe à ANONYME.
    await act(async () => { finConnexion(); });
    await laisserTourner();

    // La section est refusée POUR SESSION — jamais laissée en « chargement ».
    expect(vue.boite.courant.sections.contacts.etat).toBe(SECTION.SESSION);
    expect(vue.boite.courant.global).toBe(GLOBAL.SESSION_EXPIREE);

    await vue.demonter();
  });

  test('sans preuve signée, la route à signature ne part pas — mais les autres si', async () => {
    poserSessionZombie(); // état EXPIREE : le serveur répondrait 403 à coup sûr
    const appels = [];
    const vue = monter(() => ({
      contacts: {
        url: '/api/users',
        appel: () => {
          appels.push('contacts');
          return ok([]);
        },
      },
      reservations: {
        url: '/api/reservations',
        appel: () => {
          appels.push('reservations');
          return ok({ data: [7] });
        },
      },
    }));

    await vue.rendre();
    await laisserTourner();

    // /users n'est pas partie : le serveur l'aurait refusée, c'est mesuré.
    expect(appels).toEqual(['reservations']);
    expect(vue.boite.courant.sections.contacts.etat).toBe(SECTION.SESSION);

    // /reservations est PARTIE : elle accepte le repli X-User-Email (règle V310c).
    expect(vue.boite.courant.sections.reservations.etat).toBe(SECTION.OK);
    expect(vue.boite.courant.donnees.reservations).toEqual({ data: [7] });

    await vue.demonter();
  });
});

// ---------------------------------------------------------------------------
// CAS 3 — session réellement expirée
// ---------------------------------------------------------------------------
describe('CAS 3 — session expirée : état cohérent, aucun loader infini', () => {
  test('toutes les sections protégées refusées -> SESSION_EXPIREE, jamais « chargement »', async () => {
    poserSessionZombie();
    const vue = monter(() => ({
      contacts: { url: '/api/users', appel: () => refus(403) },
      codes: { url: '/api/discount-codes', appel: () => refus(403) },
    }));

    await vue.rendre();
    await laisserTourner();

    expect(vue.boite.courant.global).toBe(GLOBAL.SESSION_EXPIREE);
    expect(vue.boite.courant.sessionExpiree).toBe(true);
    Object.values(vue.boite.courant.sections).forEach((s) => {
      expect(s.etat).not.toBe(SECTION.CHARGEMENT);
    });

    await vue.demonter();
  });

  test('ESCALADE : jeton en apparence valide mais refusé partout -> session, pas « droit »', async () => {
    // Secret serveur changé, compte révoqué : le navigateur croit son jeton bon.
    poserJetonValide();
    const surSessionInvalide = jest.fn();
    const vue = monter(
      () => ({
        contacts: { url: '/api/users', appel: () => refus(403) },
        codes: { url: '/api/discount-codes', appel: () => refus(403) },
        cours: { url: '/api/courses', appel: () => ok(['c']) },
      }),
      { surSessionInvalide }
    );

    await vue.rendre();
    await laisserTourner();
    const r = vue.boite.courant;

    // Toutes les routes À SIGNATURE ont été refusées -> c'est la preuve globale.
    expect(r.sections.contacts.etat).toBe(SECTION.SESSION);
    expect(r.sections.codes.etat).toBe(SECTION.SESSION);
    expect(surSessionInvalide).toHaveBeenCalledTimes(1);

    // Mais la ressource publique reste servie : dégradation partielle, pas noire.
    expect(r.sections.cours.etat).toBe(SECTION.OK);
    expect(r.global).toBe(GLOBAL.PARTIEL);

    await vue.demonter();
  });

  test('UN SEUL refus parmi plusieurs routes protégées -> « droit », pas escalade', async () => {
    poserJetonValide();
    const surSessionInvalide = jest.fn();
    const vue = monter(
      () => ({
        contacts: { url: '/api/users', appel: () => refus(403) },
        codes: { url: '/api/discount-codes', appel: () => ok(['AFR-1']) },
      }),
      { surSessionInvalide }
    );

    await vue.rendre();
    await laisserTourner();

    expect(vue.boite.courant.sections.contacts.motif).toBe('droit');
    expect(surSessionInvalide).not.toHaveBeenCalled();

    await vue.demonter();
  });
});

// ---------------------------------------------------------------------------
// CAS 4 — API temporairement en 500
// ---------------------------------------------------------------------------
describe('CAS 4 — 500 temporaire : erreur claire, relance possible, aucun faux zéro', () => {
  test('un 500 produit une erreur qualifiée, pas un tableau vide', async () => {
    poserJetonValide();
    const vue = monter(() => ({
      cours: { url: '/api/courses', appel: () => refus(503) },
    }));

    await vue.rendre();
    await laisserTourner();

    expect(vue.boite.courant.sections.cours.etat).toBe(SECTION.ERREUR);
    expect(vue.boite.courant.sections.cours.motif).toBe('serveur');
    // La donnée reste INCONNUE : surtout pas [] qui vaudrait « il n'y en a pas ».
    expect(vue.boite.courant.donnees.cours).toBeUndefined();

    await vue.demonter();
  });

  test('« Réessayer » relance UNE section et la répare, sans recharger la page', async () => {
    poserJetonValide();
    let tour = 0;
    const vue = monter(() => ({
      cours: {
        url: '/api/courses',
        appel: () => {
          tour += 1;
          return tour === 1 ? refus(500) : ok(['cours-reparé']);
        },
      },
      offres: { url: '/api/offers', appel: () => ok(['o']) },
    }));

    await vue.rendre();
    await laisserTourner();
    expect(vue.boite.courant.sections.cours.etat).toBe(SECTION.ERREUR);

    await act(async () => {
      vue.boite.courant.reessayer('cours');
    });
    await laisserTourner();

    expect(vue.boite.courant.sections.cours.etat).toBe(SECTION.OK);
    expect(vue.boite.courant.donnees.cours).toEqual(['cours-reparé']);
    expect(vue.boite.courant.global).toBe(GLOBAL.OK);

    await vue.demonter();
  });

  test('un échec RÉSEAU est relancé une seule fois, automatiquement', async () => {
    poserJetonValide();
    let tour = 0;
    const vue = monter(() => ({
      cours: {
        url: '/api/courses',
        appel: () => {
          tour += 1;
          return tour === 1 ? coupure() : ok(['revenu']);
        },
      },
    }));

    await vue.rendre();
    await laisserTourner();
    expect(vue.boite.courant.sections.cours.motif).toBe('reseau');

    await laisserTourner(900); // la relance unique
    expect(vue.boite.courant.sections.cours.etat).toBe(SECTION.OK);
    expect(tour).toBe(2);

    // Et elle ne boucle pas : plus rien ne part ensuite.
    await laisserTourner(5000);
    expect(tour).toBe(2);

    await vue.demonter();
  });

  test('un 4xx n\'est JAMAIS relancé automatiquement', async () => {
    poserJetonValide();
    let tour = 0;
    const vue = monter(() => ({
      contacts: {
        url: '/api/users',
        appel: () => {
          tour += 1;
          return refus(403);
        },
      },
    }));

    await vue.rendre();
    await laisserTourner();
    await laisserTourner(5000);

    expect(tour).toBe(1);
    await vue.demonter();
  });
});

// ---------------------------------------------------------------------------
// CAS 5 — réponse vide RÉELLE
// ---------------------------------------------------------------------------
describe('CAS 5 — le vide réel reste du vide', () => {
  test('une liste vraiment vide donne OK + [] (le « 0 » est alors légitime)', async () => {
    poserJetonValide();
    const vue = monter(() => ({
      contacts: { url: '/api/users', appel: () => ok([]) },
    }));

    await vue.rendre();
    await laisserTourner();

    expect(vue.boite.courant.sections.contacts.etat).toBe(SECTION.OK);
    expect(vue.boite.courant.donnees.contacts).toEqual([]);
    expect(vue.boite.courant.global).toBe(GLOBAL.OK);

    await vue.demonter();
  });
});

// ---------------------------------------------------------------------------
// CAS 6 et 7 — première ouverture == rafraîchissement == navigation interne
// ---------------------------------------------------------------------------
describe('CAS 6 et 7 — le rafraîchissement ne change plus le résultat', () => {
  test('avant toute réponse, l\'état est CHARGEMENT et aucune donnée n\'est affirmée', async () => {
    poserJetonValide();
    let resoudre;
    const vue = monter(() => ({
      cours: { url: '/api/courses', appel: () => new Promise((r) => { resoudre = r; }) },
    }));

    await vue.rendre();

    // C'est LA fin du « zéro menteur » : pendant le chargement, on ne sait pas.
    expect(vue.boite.courant.global).toBe(GLOBAL.CHARGEMENT);
    expect(vue.boite.courant.donnees.cours).toBeUndefined();

    await act(async () => {
      resoudre({ data: ['c'] });
    });
    await laisserTourner();
    expect(vue.boite.courant.donnees.cours).toEqual(['c']);

    await vue.demonter();
  });

  test('un montage frais (= rafraîchissement) donne le MÊME résultat', async () => {
    poserJetonValide();
    const sources = () => ({
      cours: { url: '/api/courses', appel: () => ok(['c1']) },
      contacts: { url: '/api/users', appel: () => refus(403) },
    });

    const premier = monter(sources);
    await premier.rendre();
    await laisserTourner();
    const avant = {
      global: premier.boite.courant.global,
      cours: premier.boite.courant.donnees.cours,
      contacts: premier.boite.courant.sections.contacts.etat,
    };
    await premier.demonter();

    const second = monter(sources);
    await second.rendre();
    await laisserTourner();
    expect({
      global: second.boite.courant.global,
      cours: second.boite.courant.donnees.cours,
      contacts: second.boite.courant.sections.contacts.etat,
    }).toEqual(avant);
    await second.demonter();
  });

  test('l\'identité change en cours de session -> le chargement est REJOUÉ', async () => {
    // C'est le cas C de l'audit : se connecter PENDANT la session laissait les
    // données vides jusqu'au prochain F5, à cause d'une fermeture figée.
    poserJetonValide();
    const appels = [];
    const vue = monter(
      (props) => ({
        cours: {
          url: '/api/courses',
          appel: () => {
            appels.push(props.email || 'anonyme');
            return ok(['c']);
          },
        },
      }),
      { deps: [] }
    );

    // On simule la dépendance primitive en remontant avec une autre valeur.
    function Sonde({ email }) {
      const sources = {
        cours: {
          url: '/api/courses',
          appel: () => {
            appels.push(email || 'anonyme');
            return ok(['c']);
          },
        },
      };
      useChargement(sources, { deps: [email] });
      return null;
    }
    const conteneur = document.createElement('div');
    document.body.appendChild(conteneur);
    const racine = createRoot(conteneur);

    appels.length = 0;
    await act(async () => racine.render(<Sonde email="" />));
    await laisserTourner();
    expect(appels).toEqual(['anonyme']);

    await act(async () => racine.render(<Sonde email="coach@test.ch" />));
    await laisserTourner();
    expect(appels).toEqual(['anonyme', 'coach@test.ch']);

    await act(async () => racine.unmount());
    conteneur.remove();
    await vue.demonter();
  });
});

// ---------------------------------------------------------------------------
// Garanties structurelles
// ---------------------------------------------------------------------------
describe('Garanties structurelles', () => {
  test('AUCUN chemin ne laisse une section en « chargement »', async () => {
    poserJetonValide();
    const vue = monter(() => ({
      a: { url: '/api/courses', appel: () => ok([1]) },
      b: { url: '/api/offers', appel: () => refus(500) },
      c: { url: '/api/users', appel: () => refus(403) },
      d: { url: '/api/concept', appel: () => coupure() },
      e: {
        url: '/api/payment-links',
        appel: () => {
          throw new Error('exception synchrone');
        },
      },
    }));

    await vue.rendre();
    await laisserTourner();
    await laisserTourner(2000); // laisse passer la relance réseau

    Object.entries(vue.boite.courant.sections).forEach(([cle, s]) => {
      expect([SECTION.OK, SECTION.ERREUR, SECTION.SESSION]).toContain(s.etat);
    });

    await vue.demonter();
  });

  test('un démontage en plein vol ne provoque aucune mise à jour', async () => {
    poserJetonValide();
    const erreurs = [];
    const espion = jest.spyOn(console, 'error').mockImplementation((m) => erreurs.push(m));

    let resoudre;
    const vue = monter(() => ({
      cours: { url: '/api/courses', appel: () => new Promise((r) => { resoudre = r; }) },
    }));
    await vue.rendre();
    await vue.demonter();

    await act(async () => {
      resoudre({ data: ['trop tard'] });
      await Promise.resolve();
    });

    expect(erreurs).toEqual([]);
    espion.mockRestore();
  });

  test('des données identiques ne provoquent aucun rendu en trop (anti-boucle V305)', async () => {
    poserJetonValide();
    const memeTableau = ['stable'];
    let appels = 0;
    const vue = monter(() => ({
      cours: {
        url: '/api/courses',
        appel: () => {
          appels += 1;
          return ok(memeTableau);
        },
      },
    }));

    await vue.rendre();
    await laisserTourner();
    const apresPremierChargement = vue.boite.rendus;

    // Une relance coûte exactement DEUX rendus : « chargement » puis retour à
    // « ok ». Le second est dû au seul changement d'état — la donnée, elle, est
    // strictement la même référence et n'ajoute rien (comparaison avant setState).
    async function relancer() {
      await act(async () => {
        vue.boite.courant.reessayer('cours');
      });
      await laisserTourner();
    }

    await relancer();
    const coutDUneRelance = vue.boite.rendus - apresPremierChargement;
    expect(coutDUneRelance).toBe(2);

    // Le coût est CONSTANT : rien ne s'emballe, aucune boucle ne s'amorce.
    await relancer();
    await relancer();
    expect(vue.boite.rendus - apresPremierChargement).toBe(coutDUneRelance * 3);
    expect(appels).toBe(4); // 1 chargement initial + 3 relances explicites

    // Et surtout : le temps qui passe seul ne déclenche AUCUN appel.
    await laisserTourner(10000);
    expect(appels).toBe(4);

    await vue.demonter();
  });

  test('une section en erreur CONSERVE les données déjà affichées', async () => {
    poserJetonValide();
    let tour = 0;
    const vue = monter(() => ({
      cours: {
        url: '/api/courses',
        appel: () => {
          tour += 1;
          return tour === 1 ? ok(['déjà là']) : refus(500);
        },
      },
    }));

    await vue.rendre();
    await laisserTourner();
    expect(vue.boite.courant.donnees.cours).toEqual(['déjà là']);

    await act(async () => {
      vue.boite.courant.reessayer('cours');
    });
    await laisserTourner();

    expect(vue.boite.courant.sections.cours.etat).toBe(SECTION.ERREUR);
    // Un rafraîchissement raté n'efface pas ce que le coach avait sous les yeux.
    expect(vue.boite.courant.donnees.cours).toEqual(['déjà là']);

    await vue.demonter();
  });

  test('la reconnexion relance SEULEMENT les sections refusées pour session', async () => {
    poserSessionZombie();
    const appels = [];
    const vue = monter(() => ({
      contacts: {
        url: '/api/users',
        appel: () => {
          appels.push('contacts');
          return ok(['c']);
        },
      },
      cours: {
        url: '/api/courses',
        appel: () => {
          appels.push('cours');
          return ok(['x']);
        },
      },
    }));

    await vue.rendre();
    await laisserTourner();
    expect(appels).toEqual(['cours']); // contacts bloquée par le portillon
    expect(vue.boite.courant.sections.contacts.etat).toBe(SECTION.SESSION);

    // Le coach se reconnecte : un jeton signé apparaît, l'événement est diffusé.
    await act(async () => {
      poserJetonValide();
      window.dispatchEvent(
        new CustomEvent('afroboost:auth', { detail: { etat: 'valide', raison: 'connecte' } })
      );
    });
    await laisserTourner();

    // Seule `contacts` est rejouée — `cours` avait déjà réussi.
    expect(appels).toEqual(['cours', 'contacts']);
    expect(vue.boite.courant.sections.contacts.etat).toBe(SECTION.OK);
    expect(vue.boite.courant.global).toBe(GLOBAL.OK);

    await vue.demonter();
  });

  test('la récupération appartient à l\'application : aucun rechargement de page', () => {
    // `window.location` n'est pas configurable sous jsdom : on ne peut pas
    // espionner `reload`. On vérifie donc la garantie à la SOURCE, ce qui est
    // même plus fort — le socle ne doit contenir aucun appel de ce genre, quel
    // que soit le chemin d'exécution emprunté.
    const fs = require('fs');
    const path = require('path');
    const racine = path.resolve(__dirname, '..', '..');
    const fichiersSocle = [
      path.join(racine, 'hooks', 'useChargement.js'),
      path.join(racine, 'utils', 'authSession.js'),
      path.join(racine, 'components', 'ui', 'EtatChargement.js'),
    ];

    fichiersSocle.forEach((fichier) => {
      const source = fs.readFileSync(fichier, 'utf8');
      const code = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
      expect(code).not.toMatch(/location\s*\.\s*reload/);
      expect(code).not.toMatch(/location\s*\.\s*href\s*=/);
    });

    // Et `terminerSession` s'exécute jusqu'au bout sans quitter la page.
    poserSessionZombie();
    expect(() => terminerSession('expiree')).not.toThrow();
    expect(localStorage.getItem('afroboost_coach_mode')).toBeNull();
  });
});
