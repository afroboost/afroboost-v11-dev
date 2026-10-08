// V588 — Messages & relances : la logique PURE de l'onglet (lecture seule).
import {
  ETATS, SUIVI_MANUEL_INDISPONIBLE, etapeJ0, etapeRelance, echeanceRelance, ligneRelance,
  lignesRelances, compteursRelances, filtrerRelances, trierRelances, chronologie, familleCanal,
  organisationDe, dateCourte, nomCampagne, motifLisible, signauxConversation, texteUtile, extrait,
  ilYa, correspondRecherche, prioriteRelance, dernierEvenement,
} from '../messagesRelances';

const MAINTENANT = Date.parse('2026-10-07T14:00:00Z');
const CAMPAGNE = { id: 'c1', subject_j0: 'Proposition de collaboration avec Afroboost',
  subject_j3: 'Re: Proposition de collaboration avec Afroboost', subject_j7: 'Re: Proposition de collaboration avec Afroboost' };

const envoyee = (sur) => Object.assign({
  id: 'a-1', recipient_key: 'ETU-04', organisations: ['BDE HE-Arc'], prospect_ids: ['ETU-04'],
  channel: 'email', execution_type: 'AUTO', statut: 'envoye', target: 'info@bde-hearc.ch',
  message_j0: 'Bonjour J0', message_j3: 'Relance J+3 approuvée', message_j7: 'Relance J+7 approuvée',
  sent_at: '2026-09-03T10:57:00+00:00', provider_message_id: 'res-1', provider_status: 'accepted',
  j3_due_at: '2026-09-06T10:57:00+00:00', j7_due_at: '2026-09-10T10:57:00+00:00',
}, sur || {});

const manuelle = (sur) => Object.assign({
  id: 'a-dm', recipient_key: 'COM-01', organisations: ['Akoko Tresses'], prospect_ids: ['COM-01'],
  channel: 'instagram', execution_type: 'MANUEL', statut: 'pret', message_j0: 'Salut !',
}, sur || {});

const conv = (sur) => Object.assign({
  action_id: 'a-1', organisation: 'BDE HE-Arc', nb_messages: 2, statut_commercial: 'en_attente',
  messages_recus: [
    { id: 'm1', received_at: '2026-09-04T05:25:19.111Z', subject: 'Re: Proposition' },
    { id: 'm2', received_at: '2026-09-05T14:45:26.561Z', subject: 'Re: Proposition' },
  ],
  derniere_reponse_afroboost: { sent_at: '2026-09-08T09:48:24+00:00', objet: 'Re: Proposition' },
}, sur || {});

describe('étapes', () => {
  test('J+3 échu, non envoyé, non annulé → EN RETARD avec ancienneté exacte', () => {
    const e = etapeRelance(envoyee(), CAMPAGNE, 'j3', null, MAINTENANT);
    expect(e.etat).toBe(ETATS.EN_RETARD);
    expect(e.retard_jours).toBe(31);
    expect(e.message).toBe('Relance J+3 approuvée');
    expect(e.objet).toBe(CAMPAGNE.subject_j3);
    expect(e.date_prevue).toBe('2026-09-06T10:57:00+00:00');
  });

  test('le J+7 attend le J+3 : jamais « en retard » tant que le J+3 n\'est pas parti', () => {
    const e = etapeRelance(envoyee(), CAMPAGNE, 'j7', null, MAINTENANT);
    expect(e.etat).toBe(ETATS.PREVU);
    expect(e.date_prevue).toBeNull();
  });

  test('J+7 : échéance = max(j7_due_at, J+3 parti + 4 jours)', () => {
    const a = envoyee({ j3_sent_at: '2026-10-07T08:00:00Z' });
    expect(echeanceRelance(a, 'j7')).toBe('2026-10-11T08:00:00.000Z');
    expect(etapeRelance(a, CAMPAGNE, 'j3', null, MAINTENANT).etat).toBe(ETATS.ENVOYE);
    expect(etapeRelance(a, CAMPAGNE, 'j7', null, MAINTENANT).etat).toBe(ETATS.PREVU);
  });

  test('annulation « reponse recue » → Répondu, avec le motif', () => {
    const a = envoyee({ replied_at: '2026-09-04T05:25:19Z', j3_annule_le: '2026-09-04T05:25:20Z',
      j3_annule_motif: 'reponse recue', j7_annule_le: '2026-09-04T05:25:20Z', j7_annule_motif: 'reponse recue' });
    expect(etapeRelance(a, CAMPAGNE, 'j3', conv(), MAINTENANT).etat).toBe(ETATS.REPONDU);
    expect(etapeRelance(a, CAMPAGNE, 'j7', conv(), MAINTENANT).etat).toBe(ETATS.REPONDU);
  });

  test('refus exprimé dans la conversation → Refus (prime sur Répondu)', () => {
    const a = envoyee({ replied_at: '2026-09-04T05:25:19Z', j3_annule_le: 'x', j3_annule_motif: 'reponse recue' });
    expect(etapeRelance(a, CAMPAGNE, 'j3', conv({ statut_commercial: 'refus' }), MAINTENANT).etat).toBe(ETATS.REFUS);
  });

  test('rebond permanent → J0 Rebond, relances Rebond', () => {
    const a = envoyee({ bounce_type: 'Permanent', provider_status: 'bounced',
      j3_annule_le: '2026-09-03T11:00:00Z', j3_annule_motif: 'rebond permanent' });
    expect(etapeJ0(a, CAMPAGNE).etat).toBe(ETATS.REBOND);
    expect(etapeRelance(a, CAMPAGNE, 'j3', null, MAINTENANT).etat).toBe(ETATS.REBOND);
    expect(etapeRelance(a, CAMPAGNE, 'j7', null, MAINTENANT).etat).toBe(ETATS.REBOND);
  });

  test('rebond TEMPORAIRE : le moteur relancerait → le J+3 reste en retard', () => {
    const a = envoyee({ bounce_type: 'Transient' });
    expect(etapeJ0(a, CAMPAGNE).etat).toBe(ETATS.REBOND);
    expect(etapeRelance(a, CAMPAGNE, 'j3', null, MAINTENANT).etat).toBe(ETATS.EN_RETARD);
  });

  test('DM Instagram jamais tracé → À faire manuellement + « Suivi manuel non encore disponible »', () => {
    const j0 = etapeJ0(manuelle(), CAMPAGNE);
    expect(j0.etat).toBe(ETATS.MANUEL);
    expect(j0.motif).toBe(SUIVI_MANUEL_INDISPONIBLE);
    expect(etapeRelance(manuelle(), CAMPAGNE, 'j3', null, MAINTENANT).etat).toBe(ETATS.SANS_OBJET);
  });

  test('bloqué / exclu → Stoppé avec motif', () => {
    expect(etapeJ0({ channel: 'aucun', execution_type: 'BLOQUE', statut: 'bloque', execution_reason: 'aucun canal' }).motif).toBe('aucun canal');
    expect(etapeJ0({ channel: 'email', execution_type: 'AUTO', statut: 'exclu' }).etat).toBe(ETATS.STOPPE);
  });

  test('e-mail AUTO pas encore parti → À envoyer', () => {
    expect(etapeJ0({ channel: 'email', execution_type: 'AUTO', statut: 'pret' }).etat).toBe(ETATS.A_ENVOYER);
  });

  test('texte de la FICHE ignoré : seul le texte de l\'ACTION compte', () => {
    const a = envoyee({ message_j3: '' });
    const fiche = { ref: 'ETU-04', status: 'contacte', j3_message: 'BROUILLON NON APPROUVÉ' };
    const l = ligneRelance(a, CAMPAGNE, null, { 'ETU-04': fiche }, MAINTENANT);
    expect(l.j3.message).toBe('');
    expect(l.j3.etat).toBe(ETATS.STOPPE);
    expect(JSON.stringify(l.j3)).not.toMatch(/BROUILLON/);
  });
});

describe('lignes, compteurs, filtres', () => {
  const actions = [
    envoyee({ id: 'late1' }),
    envoyee({ id: 'late2', organisations: ['Dynam'], j3_due_at: '2026-10-01T10:00:00Z' }),
    envoyee({ id: 'rep', replied_at: '2026-09-04T05:25:19Z', j3_annule_le: 'x', j3_annule_motif: 'reponse recue', j7_annule_le: 'x', j7_annule_motif: 'reponse recue' }),
    envoyee({ id: 'refus', organisations: ['SalsaRica'], replied_at: '2026-09-05T00:00:00Z', j3_annule_le: 'x', j3_annule_motif: 'reponse recue' }),
    envoyee({ id: 'bounce', bounce_type: 'Permanent', j3_annule_le: 'x', j3_annule_motif: 'rebond permanent', j7_annule_le: 'x', j7_annule_motif: 'rebond permanent' }),
    manuelle({ id: 'dm' }),
    manuelle({ id: 'wa', channel: 'whatsapp', execution_type: 'ASSISTE' }),
    { id: 'bloque', channel: 'aucun', execution_type: 'BLOQUE', statut: 'bloque', organisations: ['X'] },
    { id: 'futur', channel: 'email', execution_type: 'AUTO', statut: 'envoye', sent_at: '2026-10-06T10:00:00Z',
      j3_due_at: '2026-10-09T10:00:00Z', message_j3: 'r3', message_j7: 'r7', organisations: ['Futur'] },
  ];
  const convs = [conv({ action_id: 'rep' }), conv({ action_id: 'refus', statut_commercial: 'refus', organisation: 'SalsaRica' })];
  const prospects = [{ ref: 'ETU-04', status: 'repondu' }];
  const lignes = lignesRelances(actions, CAMPAGNE, convs, prospects, MAINTENANT);

  test('compteurs exacts', () => {
    expect(compteursRelances(lignes)).toMatchObject({
      total: 9, j0Envoyes: 5 + 1, j3AVenir: 1, j3EnRetard: 2, j7AVenir: 3, reponses: 2, stoppes: 3, manuel: 2,
    });
  });

  test('états globaux et prochaines actions', () => {
    const par = Object.fromEntries(lignes.map((l) => [l.id, l]));
    expect(par.late1.etat).toBe(ETATS.EN_RETARD);
    expect(par.late1.prochaineAction).toMatch(/J\+3 en retard/);
    expect(par.late1.statutProspect).toBe('repondu');
    expect(par.rep.etat).toBe(ETATS.REPONDU);
    expect(par.rep.reponseLe).toBe('2026-09-04T05:25:19Z');
    expect(par.refus.etat).toBe(ETATS.REFUS);
    expect(par.bounce.etat).toBe(ETATS.REBOND);
    expect(par.bounce.motifArret).toMatch(/adresse morte/);
    expect(par.dm.etat).toBe(ETATS.MANUEL);
    expect(par.bloque.etat).toBe(ETATS.STOPPE);
    expect(par.futur.etat).toBe(ETATS.PREVU);
    expect(par.futur.prochaineDate).toBe('2026-10-09T10:00:00Z');
  });

  test('filtres par état et par canal', () => {
    const ids = (f, c) => filtrerRelances(lignes, f, c).map((l) => l.id).sort();
    expect(ids('en_retard')).toEqual(['late1', 'late2']);
    expect(ids('repondus')).toEqual(['refus', 'rep']);
    expect(ids('stoppes')).toEqual(['bloque', 'bounce', 'refus']);
    expect(ids('manuel')).toEqual(['dm', 'wa']);
    expect(ids('envoyes')).toHaveLength(6);
    expect(ids('a_envoyer')).toEqual([]);
    expect(ids('tous', 'dm')).toEqual(['dm']);
    expect(ids('tous', 'whatsapp')).toEqual(['wa']);
    expect(ids('manuel', 'email')).toEqual([]);
  });

  test('tri : retards d\'abord, le plus ancien en tête', () => {
    expect(trierRelances(lignes).slice(0, 2).map((l) => l.id)).toEqual(['late1', 'late2']);
  });
});

describe('chronologie', () => {
  test('envoi, Resend, J+3 prévu + en retard, réponses, réponse Afroboost, notes (corrigées exclues)', () => {
    const l = ligneRelance(envoyee(), CAMPAGNE, conv({ statut_commercial: 'en_attente', nb_messages: 0 }), {}, MAINTENANT);
    // nb_messages 0 mais messages présents : la ligne reste « en retard » pour ce test.
    const notes = [
      { id: 'n1', type: 'appel', texte: 'Appelé le comité', occurred_at: '2026-09-09T09:00:00Z' },
      { id: 'n2', type: 'appel', texte: 'faux', occurred_at: '2026-09-09T10:00:00Z' },
      { id: 'n3', type: 'information', texte: 'correction', corrige_note_id: 'n2', occurred_at: '2026-09-09T11:00:00Z' },
    ];
    const titres = chronologie(l, notes).map((e) => `${dateCourte(e.quand)} ${e.titre}`);
    expect(titres).toEqual([
      '03/09/2026 J0 envoyé (E-mail)',
      '03/09/2026 Accepté par Resend',
      '04/09/2026 Réponse reçue',
      '05/09/2026 Réponse reçue',
      '06/09/2026 J+3 prévu',
      '06/09/2026 J+3 en retard (31 j)',
      '08/09/2026 Réponse envoyée par Afroboost',
      '09/09/2026 Note (appel)',
      '09/09/2026 Note (information)',
    ]);
  });

  test('réponse reçue → J+3 et J+7 annulés figurent avec leur motif', () => {
    const a = envoyee({ replied_at: '2026-09-04T05:25:19Z', j3_annule_le: '2026-09-04T05:25:20Z', j3_annule_motif: 'reponse recue',
      j7_annule_le: '2026-09-04T05:25:20Z', j7_annule_motif: 'reponse recue' });
    const ev = chronologie(ligneRelance(a, CAMPAGNE, conv(), {}, MAINTENANT), []);
    expect(ev.filter((e) => /annulé/.test(e.titre)).map((e) => [e.titre, e.detail]))
      .toEqual([['J+3 annulé', 'réponse reçue'], ['J+7 annulé', 'réponse reçue']]);
    expect(ev.some((e) => /prévu|retard/.test(e.titre))).toBe(false);
  });
});

test('utilitaires', () => {
  expect(familleCanal('instagram')).toBe('dm');
  expect(familleCanal('formulaire')).toBe('autre');
  expect(organisationDe({ organisations: ['A', 'B'] })).toBe('A · B');
  expect(organisationDe({ recipient_key: 'K' }, { organisation: 'Conv' })).toBe('Conv');
  expect(dateCourte('')).toBe('—');
  expect(nomCampagne({ id: 'x', nom: 'P3-LAUNCH-137' })).toBe('P3-LAUNCH-137');
  expect(motifLisible('reponse recue')).toBe('réponse reçue');
});


describe('V588b/c — nouveau, appel à faire, réponse attendue, priorité, recherche', () => {
  const convDe = (id, sur) => conv(Object.assign({ action_id: id, reponse_apres_dernier_message: false,
    organisation: '', from_email: `${id}@exemple.ch`,
    dernier_message: { received_at: '2026-10-07T13:48:00Z', body_text: 'Bonjour,\n\nNous en avons parlé au comité, on revient vers vous.\n\nLe 3 sept. 2026, Afroboost a écrit :\n> ancien texte' } }, sur || {}));
  const actions = [
    envoyee({ id: 'nouveau', organisations: ['BDE HE-Arc'], replied_at: '2026-10-07T13:48:00Z' }),
    envoyee({ id: 'lu', organisations: ['ACD'], replied_at: '2026-09-05T00:00:00Z' }),
    envoyee({ id: 'appel', organisations: ['Festival X'], replied_at: '2026-10-06T00:00:00Z' }),
    envoyee({ id: 'attendue', organisations: ['Dynam'], replied_at: '2026-09-04T00:00:00Z' }),
    envoyee({ id: 'repondue', organisations: ['Urban Team'], replied_at: '2026-09-04T00:00:00Z' }),
    envoyee({ id: 'retard', organisations: ['Afrik'] }),
    manuelle({ id: 'dm' }),
    envoyee({ id: 'mort', organisations: ['Case à Chocs'], bounce_type: 'Permanent' }),
  ];
  const convs = [
    convDe('nouveau', { non_lues: 2, statut_commercial: 'a_repondre' }),
    convDe('lu', { non_lues: 0, statut_commercial: 'en_attente' }),
    convDe('appel', { non_lues: 0, statut_commercial: 'appel_a_faire' }),
    convDe('attendue', { non_lues: 0, statut_commercial: 'a_repondre' }),
    convDe('repondue', { non_lues: 0, statut_commercial: 'a_repondre', reponse_apres_dernier_message: true }),
  ];
  const prospects = [{ ref: 'COM-01', city: 'Neuchâtel', category: 'commerce', contact_name: 'Awa', public_email: 'hello@akoko.ch' }];
  actions.forEach((a) => { a.target = `${a.id}@exemple.ch`; });
  const L = lignesRelances(actions, CAMPAGNE, convs, prospects, MAINTENANT);
  const par = Object.fromEntries(L.map((l) => [l.id, l]));

  test('NOUVEAU vient de non_lues (lu/non-lu existant) ; APPEL À FAIRE est indépendant', () => {
    expect(par.nouveau.nonLues).toBe(2);
    expect(par.nouveau.appel).toBe(false);
    expect(par.lu.nonLues).toBe(0);
    expect(par.appel.appel).toBe(true);
    expect(par.appel.nonLues).toBe(0);
    expect(par.appel).not.toHaveProperty('urgent');            // V588c : aucune « urgence » inventée
  });

  test('réponse attendue seulement si Afroboost n\'a rien envoyé après et le dossier attend une action', () => {
    expect(par.attendue.reponseAttendue).toBe(true);
    expect(par.attendue.prochaineAction).toBe('Répondre au partenaire');
    expect(par.repondue.reponseAttendue).toBe(false);            // Afroboost a répondu après
    expect(par.lu.reponseAttendue).toBe(false);                  // en attente du partenaire
    expect(signauxConversation({ nb_messages: 1, statut_commercial: 'refus' }).reponseAttendue).toBe(false);
  });

  test('« À traiter » = nouveaux + appels à faire + réponses attendues, JAMAIS les relances en retard', () => {
    expect(filtrerRelances(L, 'a_traiter').map((l) => l.id).sort()).toEqual(['appel', 'attendue', 'nouveau']);
    expect(compteursRelances(L)).toMatchObject({ aTraiter: 3, nouveaux: 2, conversationsNonLues: 1, appels: 1, j3EnRetard: 1 });
  });

  test('ordre : non lu → appel à faire → réponse attendue → retard → manuel → sans action → clos', () => {
    expect(trierRelances(L).map((l) => l.id)).toEqual(['nouveau', 'appel', 'attendue', 'retard', 'dm', 'lu', 'repondue', 'mort']);
    expect(prioriteRelance({ appel: true, nonLues: 1 })).toBe(0);
  });

  test('recherche instantanée sans accents : organisation, ville, catégorie, nom, e-mail, statut', () => {
    const ids = (q) => filtrerRelances(L, 'tous', 'tous', q).map((l) => l.id);
    expect(ids('bde')).toEqual(['nouveau']);
    expect(ids('akoko')).toEqual(['dm']);
    expect(ids('neuchatel')).toEqual(['dm']);
    expect(ids('Commerce')).toEqual(['dm']);
    expect(ids('awa')).toEqual(['dm']);
    expect(ids('appel a faire')).toEqual(['appel']);
    expect(ids('urgent')).toEqual([]);                          // aucune ligne n'est « urgente »
    expect(ids('rebond')).toEqual(['mort']);
    expect(ids('dynam repondu')).toEqual(['attendue']);
    expect(ids('')).toHaveLength(8);
  });

  test('extrait sans salutation ni citation ; ilYa', () => {
    expect(texteUtile('Bonjour\n\nOui !\n> cité')).toBe('Bonjour\n\nOui !');
    expect(par.nouveau.extrait).toBe('Nous en avons parlé au comité, on revient vers vous.');
    expect(ilYa('2026-10-07T13:48:00Z', MAINTENANT)).toBe('il y a 12 min');
    expect(ilYa('2026-10-07T12:00:00Z', MAINTENANT)).toBe('il y a 2 h');
    expect(ilYa('2026-09-03T10:57:00Z', MAINTENANT)).toBe('le 03/09/2026');
  });

  test('dernier événement réel (jamais une échéance)', () => {
    expect(dernierEvenement(par.retard).titre).toBe('J0 envoyé (E-mail)');
    expect(dernierEvenement(par.dm)).toBeNull();
  });
});
