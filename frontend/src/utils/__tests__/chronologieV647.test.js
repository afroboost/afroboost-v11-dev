/**
 * V647 — retrouver un message : tri par date, période, filtres rapides.
 * RÈGLE CENTRALE VÉRIFIÉE ICI : une date de MODIFICATION n'est jamais
 * présentée comme une date d'ENVOI.
 */
import {
  TRIS, PERIODES, FILTRES_RAPIDES, trierPar, dansPeriode, vueRelances,
  dateEnvoi, dateCreation, dateModification, dateActivite, envoyeRecemment,
  enAttenteDeReponse, aRelancer, bloqueOuEnEchec, compteursRapides,
  dateHeureZurich, lignesRelances, compteursRelances, filtrerRelances,
} from '../messagesRelances';

const MAINTENANT = Date.parse('2026-11-10T12:00:00Z');
const J = 86400000;
const iso = (ms) => new Date(ms).toISOString();

const CAMP = { id: 'c', etat: 'approuvee', subject_j0: 'Objet' };

const act = (id, over) => ({
  id, campaign_id: 'c', recipient_key: id, organisations: [id],
  channel: 'email', execution_type: 'AUTO', statut: 'pret',
  message_j0: 'Objet : X\n\nBonjour', message_j0_origine: 'edite',
  created_at: iso(MAINTENANT - 10 * J), updated_at: iso(MAINTENANT - 10 * J), ...over,
});

describe('les trois dates ne sont jamais confondues', () => {
  const prepare = act('prepare', { updated_at: iso(MAINTENANT - 1 * J) });
  const parti = act('parti', { sent_at: iso(MAINTENANT - 3 * J), updated_at: iso(MAINTENANT - 2 * J) });
  const l = (a) => lignesRelances([a], CAMP, [], [], MAINTENANT)[0];

  test('une action PRÉPARÉE n’a aucune date d’envoi, même modifiée hier', () => {
    expect(dateEnvoi(l(prepare))).toBeNull();
    expect(dateModification(l(prepare))).toBe(iso(MAINTENANT - 1 * J));
    expect(dateCreation(l(prepare))).toBe(iso(MAINTENANT - 10 * J));
  });
  test('une action ENVOYÉE porte sa vraie date d’envoi', () => {
    expect(dateEnvoi(l(parti))).toBe(iso(MAINTENANT - 3 * J));
  });
  test('la dernière activité prend le fait le PLUS RÉCENT', () => {
    expect(dateActivite(l(parti))).toBe(iso(MAINTENANT - 2 * J));   // la modification
    expect(dateActivite(l(prepare))).toBe(iso(MAINTENANT - 1 * J));
  });
  test('« envoyé il y a moins de 24 h » s’appuie sur l’envoi, jamais sur la modification', () => {
    const frais = l(act('frais', { sent_at: iso(MAINTENANT - 2 * 3600000) }));
    expect(envoyeRecemment(frais, MAINTENANT, 24)).toBe(true);
    expect(envoyeRecemment(l(prepare), MAINTENANT, 24)).toBe(false);   // modifié hier, jamais envoyé
    expect(envoyeRecemment(l(parti), MAINTENANT, 24)).toBe(false);
  });
});

describe('trierPar', () => {
  const lignes = lignesRelances([
    act('a', { sent_at: iso(MAINTENANT - 1 * J), created_at: iso(MAINTENANT - 9 * J), updated_at: iso(MAINTENANT - 1 * J) }),
    act('b', { sent_at: iso(MAINTENANT - 5 * J), created_at: iso(MAINTENANT - 8 * J), updated_at: iso(MAINTENANT - 5 * J) }),
    act('c', { created_at: iso(MAINTENANT - 7 * J), updated_at: iso(MAINTENANT - 2 * J) }),   // jamais envoyé
  ], CAMP, [], [], MAINTENANT);
  const ids = (t) => trierPar(lignes, t).map((l) => l.id);

  test('la liste des tris contient la priorité puis les six dates du cahier', () => {
    expect(TRIS.map((t) => t.id)).toEqual(
      ['priorite', 'activite', 'envoi_desc', 'envoi_asc', 'creation_desc', 'creation_asc', 'modif_desc']);
  });
  test('envoi — plus récent au plus ancien', () => expect(ids('envoi_desc')).toEqual(['a', 'b', 'c']));
  test('envoi — plus ancien au plus récent ; le jamais-envoyé reste EN FIN', () => {
    expect(ids('envoi_asc')).toEqual(['b', 'a', 'c']);
  });
  test('création, dans les deux sens', () => {
    expect(ids('creation_desc')).toEqual(['c', 'b', 'a']);
    expect(ids('creation_asc')).toEqual(['a', 'b', 'c']);
  });
  test('dernière modification', () => expect(ids('modif_desc')).toEqual(['a', 'c', 'b']));
  test('dernière activité', () => expect(ids('activite')).toEqual(['a', 'c', 'b']));
  test('un tri inconnu retombe sur l’ordre de priorité d’avant V647', () => {
    expect(ids('inconnu')).toEqual(ids('priorite'));
  });
});

describe('dansPeriode', () => {
  const l = (quand) => lignesRelances(
    [act('x', { updated_at: quand, created_at: quand })], CAMP, [], [], MAINTENANT)[0];
  const aujourdhui = l(iso(MAINTENANT - 3600000));
  const hier = l(iso(MAINTENANT - 30 * 3600000));
  const vieux = l(iso(MAINTENANT - 40 * J));

  test('la liste des périodes est celle du cahier', () => {
    expect(PERIODES.map((p) => p.id)).toEqual(['tout', 'aujourdhui', '7j', '30j', 'perso']);
  });
  test('toutes les dates : rien n’est écarté', () => {
    [aujourdhui, hier, vieux].forEach((x) => expect(dansPeriode(x, 'tout', '', '', MAINTENANT)).toBe(true));
  });
  test('aujourd’hui', () => {
    expect(dansPeriode(aujourdhui, 'aujourdhui', '', '', MAINTENANT)).toBe(true);
    expect(dansPeriode(hier, 'aujourdhui', '', '', MAINTENANT)).toBe(false);
  });
  test('7 et 30 derniers jours', () => {
    expect(dansPeriode(hier, '7j', '', '', MAINTENANT)).toBe(true);
    expect(dansPeriode(vieux, '7j', '', '', MAINTENANT)).toBe(false);
    expect(dansPeriode(vieux, '30j', '', '', MAINTENANT)).toBe(false);
    expect(dansPeriode(hier, '30j', '', '', MAINTENANT)).toBe(true);
  });
  test('période personnalisée, bornes incluses', () => {
    expect(dansPeriode(aujourdhui, 'perso', '2026-11-10', '2026-11-10', MAINTENANT)).toBe(true);
    expect(dansPeriode(aujourdhui, 'perso', '2026-11-11', '', MAINTENANT)).toBe(false);
    expect(dansPeriode(aujourdhui, 'perso', '', '2026-11-09', MAINTENANT)).toBe(false);
    // Aucune borne fournie : la période personnalisée ne filtre rien par accident.
    expect(dansPeriode(aujourdhui, 'perso', '', '', MAINTENANT)).toBe(false);
  });
});

describe('les huit filtres rapides', () => {
  const lignes = lignesRelances([
    act('brouillon', { message_j0: 'Bonjour sans objet' }),
    act('a_relire'),
    act('attente', { sent_at: iso(MAINTENANT - 2 * J) }),
    act('relancer', { sent_at: iso(MAINTENANT - 9 * J), j3_due_at: iso(MAINTENANT - 6 * J),
      message_j3: 'Relance approuvée' }),
    act('bloque', { channel: 'aucun', execution_type: 'BLOQUE', statut: 'bloque' }),
    act('echec', { sent_at: iso(MAINTENANT - 4 * J), provider_status: 'failed' }),
  ], CAMP, [], [], MAINTENANT);
  const ids = (f) => filtrerRelances(lignes, f).map((l) => l.id).sort();

  test('la liste est exactement celle du cahier', () => {
    expect(FILTRES_RAPIDES.map((f) => f.id)).toEqual(
      ['tous', 'brouillons', 'a_relire', 'prets', 'derniers_envois', 'en_attente_reponse', 'a_relancer', 'bloques']);
  });
  test('derniers envois = ceux qui ont RÉELLEMENT un envoi', () => {
    expect(ids('derniers_envois')).toEqual(['attente', 'echec', 'relancer']);
    expect(ids('derniers_envois')).not.toContain('a_relire');
  });
  test('en attente de réponse', () => {
    expect(enAttenteDeReponse(lignes.find((l) => l.id === 'attente'))).toBe(true);
    expect(enAttenteDeReponse(lignes.find((l) => l.id === 'a_relire'))).toBe(false);
    // Un envoi en ÉCHEC n'attend rien : le message n'est jamais arrivé.
    expect(enAttenteDeReponse(lignes.find((l) => l.id === 'echec'))).toBe(false);
  });
  test('à relancer = une relance ÉCHUE et non partie', () => {
    expect(aRelancer(lignes.find((l) => l.id === 'relancer'))).toBe(true);
    expect(aRelancer(lignes.find((l) => l.id === 'attente'))).toBe(false);
  });
  test('bloqués / erreurs réunit l’impasse avant envoi ET l’échec d’envoi', () => {
    expect(ids('bloques')).toEqual(['bloque', 'echec']);
    expect(bloqueOuEnEchec(lignes.find((l) => l.id === 'echec'))).toBe(true);
  });
  test('les compteurs viennent des données, pas d’un second moteur', () => {
    expect(compteursRapides(lignes, MAINTENANT)).toMatchObject(
      { derniersEnvois: 3, enAttenteReponse: 2, aRelancer: 1, bloquesErreurs: 2 });
    expect(compteursRelances(lignes)).toMatchObject({ derniersEnvois: 3, aRelancer: 1 });
  });
});

describe('vueRelances : filtres combinés puis tri', () => {
  const lignes = lignesRelances([
    act('recent', { sent_at: iso(MAINTENANT - 1 * J), updated_at: iso(MAINTENANT - 1 * J) }),
    act('ancien', { sent_at: iso(MAINTENANT - 40 * J), updated_at: iso(MAINTENANT - 40 * J),
      created_at: iso(MAINTENANT - 40 * J) }),
    act('jamais'),
  ], CAMP, [], [], MAINTENANT);

  test('envoyés + 7 derniers jours + tri par envoi décroissant', () => {
    const v = vueRelances(lignes, { filtre: 'derniers_envois', periode: '7j', tri: 'envoi_desc', maintenant: MAINTENANT });
    expect(v.map((l) => l.id)).toEqual(['recent']);
  });
  test('la période seule n’invente aucun envoi', () => {
    const v = vueRelances(lignes, { filtre: 'tous', periode: '30j', tri: 'envoi_desc', maintenant: MAINTENANT });
    expect(v.map((l) => l.id)).toEqual(['recent', 'jamais']);
  });
  test('la recherche se combine aux autres filtres', () => {
    const v = vueRelances(lignes, { filtre: 'tous', recherche: 'ancien', periode: 'tout', tri: 'activite', maintenant: MAINTENANT });
    expect(v.map((l) => l.id)).toEqual(['ancien']);
  });
});

describe('dateHeureZurich', () => {
  test('affiche l’heure de Neuchâtel, pas celle d’UTC', () => {
    // 10/11/2026 12:00 UTC = 13:00 à Zurich (heure d'hiver, UTC+1).
    expect(dateHeureZurich('2026-11-10T12:00:00Z')).toBe('10.11.2026 à 13:00');
  });
  test('heure d’été : UTC+2', () => {
    expect(dateHeureZurich('2026-07-10T12:00:00Z')).toBe('10.07.2026 à 14:00');
  });
  test('date absente ou illisible : un tiret, jamais une date inventée', () => {
    expect(dateHeureZurich(null)).toBe('—');
    expect(dateHeureZurich('pas une date')).toBe('—');
  });
});
