// PROSPECTION FOCUS — LES QUATRE PHRASES, PROUVÉES UNE PAR UNE.
//
// CE QUI EST VÉRIFIÉ ICI, ET POURQUOI :
//   * « réponse envoyée » n'est JAMAIS déduite d'un statut : sans trace, la
//     phrase dit qu'aucune réponse n'est partie. C'est la garantie centrale du
//     lot — Bassi lisait « EN ATTENTE » en croyant « j'ai répondu » ;
//   * une réponse ANTÉRIEURE au dernier message reçu ne clôt pas le dossier :
//     c'est le cas réel du BDE HE-Arc (envoi 05/09 13:05, message 05/09 14:45) ;
//   * une date illisible rend '' — jamais « Invalid Date », jamais aujourd'hui ;
//   * la conversation suivante est celle qui attend un GESTE, jamais la
//     suivante dans la liste.
import {
  attendUneAction, etatReponse, jourHeure, jourMois,
  ligneDernierEnvoi, suivanteATraiter,
} from '../prospectionFocus';

const conv = (extra = {}) => ({
  cle: 'act-1', statut_commercial: 'a_repondre',
  dernier_message_at: '2026-09-05T14:45:26+00:00',
  derniere_reponse_afroboost: null,
  reponse_apres_dernier_message: false,
  ...extra,
});

const ENVOI = { sent_at: '2026-09-05T13:05:42+00:00', to_email: 'info@bde-hearc.ch' };

describe('les dates', () => {
  test('jourMois rend « JJ/MM » sur deux chiffres', () => {
    expect(jourMois('2026-09-06T07:45:00+00:00')).toMatch(/^0[56]\/09$/);
  });

  test('jourHeure ajoute l’heure', () => {
    expect(jourHeure('2026-09-05T14:45:26+00:00')).toMatch(/^0[56]\/09 à \d{2}:\d{2}$/);
  });

  /* UNE DATE ILLISIBLE NE DEVIENT PAS AUJOURD'HUI. Se tromper de date sur un
     historique commercial est pire que ne rien dire. */
  test('une date absente ou illisible rend une chaîne vide', () => {
    ['', null, undefined, 'pas une date', '2026-13-45'].forEach((v) => {
      expect(jourMois(v)).toBe('');
      expect(jourHeure(v)).toBe('');
    });
  });
});

describe('attendUneAction', () => {
  test('« à répondre » et « appel à faire » attendent un geste', () => {
    expect(attendUneAction(conv({ statut_commercial: 'a_repondre' }))).toBe(true);
    expect(attendUneAction(conv({ statut_commercial: 'appel_a_faire' }))).toBe(true);
  });

  test('« en attente », « refus » et « traité » n’en attendent aucun', () => {
    ['en_attente', 'refus', 'traite'].forEach((s) => {
      expect(attendUneAction(conv({ statut_commercial: s }))).toBe(false);
    });
  });

  test('sans statut, on suppose qu’il reste à répondre — jamais l’inverse', () => {
    expect(attendUneAction({})).toBe(true);
  });
});

describe('etatReponse — le fait, jamais la déduction', () => {
  test('une réponse partie APRÈS le dernier message est annoncée avec sa date', () => {
    const e = etatReponse(conv({
      statut_commercial: 'en_attente',
      derniere_reponse_afroboost: { sent_at: '2026-09-06T09:00:00+00:00' },
      reponse_apres_dernier_message: true,
    }));
    expect(e.code).toBe('envoyee');
    expect(e.texte).toContain('Réponse Afroboost envoyée le');
    expect(e.texte).toContain('/09');
  });

  /* LE CAS RÉEL DU BDE HE-ARC, mesuré le 06/09/2026. */
  test('une réponse ANTÉRIEURE au dernier message ne clôt rien', () => {
    const e = etatReponse(conv({
      derniere_reponse_afroboost: ENVOI, reponse_apres_dernier_message: false,
    }));
    expect(e.code).toBe('a_repondre');
    expect(e.texte).toContain('aucune réponse Afroboost envoyée après ce message');
  });

  test('sans AUCUNE trace, l’écran écrit qu’aucune réponse n’est partie', () => {
    const e = etatReponse(conv());
    expect(e.code).toBe('a_repondre');
    expect(e.texte).toBe('À répondre — aucune réponse Afroboost envoyée');
  });

  test('un dossier qui n’attend rien le dit, sans prétendre avoir répondu', () => {
    const e = etatReponse(conv({ statut_commercial: 'en_attente' }));
    expect(e.code).toBe('attente');
    expect(e.texte).toBe('Aucune réponse nécessaire — en attente du partenaire');
    expect(e.texte).not.toContain('envoyée');
  });

  /* LA GARANTIE CENTRALE : un statut, quel qu'il soit, ne fabrique jamais une
     phrase d'envoi. Seule la trace le fait. */
  test('AUCUN statut ne suffit à faire dire « réponse envoyée »', () => {
    ['a_repondre', 'appel_a_faire', 'en_attente', 'refus', 'traite'].forEach((s) => {
      expect(etatReponse(conv({ statut_commercial: s })).code).not.toBe('envoyee');
    });
  });
});

describe('ligneDernierEnvoi', () => {
  test('avec une trace, elle donne la date', () => {
    expect(ligneDernierEnvoi(conv({ derniere_reponse_afroboost: ENVOI })))
      .toContain('Réponse envoyée le');
  });

  test('sans trace, elle l’écrit noir sur blanc', () => {
    expect(ligneDernierEnvoi(conv())).toBe('Aucune réponse envoyée.');
    expect(ligneDernierEnvoi(null)).toBe('Aucune réponse envoyée.');
  });
});

describe('suivanteATraiter', () => {
  const file = [
    conv({ cle: 'a', statut_commercial: 'a_repondre' }),
    conv({ cle: 'b', statut_commercial: 'en_attente' }),
    conv({ cle: 'c', statut_commercial: 'appel_a_faire' }),
    conv({ cle: 'd', statut_commercial: 'refus' }),
  ];

  test('elle saute celle qu’on vient de traiter', () => {
    expect(suivanteATraiter(file, 'a').cle).toBe('c');
  });

  test('elle saute ce qui n’attend AUCUN geste', () => {
    expect(suivanteATraiter(file, '').cle).toBe('a');
    expect(suivanteATraiter([file[1], file[3]], '')).toBeNull();
  });

  test('elle ne réordonne rien : l’ordre vient du serveur', () => {
    expect(suivanteATraiter([file[2], file[0]], '').cle).toBe('c');
  });

  test('une file vide ne casse rien', () => {
    expect(suivanteATraiter([], 'a')).toBeNull();
    expect(suivanteATraiter(null, 'a')).toBeNull();
  });
});
