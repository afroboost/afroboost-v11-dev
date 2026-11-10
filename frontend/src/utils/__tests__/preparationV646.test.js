/**
 * V646 — AVANT L'ENVOI : brouillon / à relire / prêt / bloqué / envoyé.
 * Cas réels de la campagne « AFROBOOST CORPORATE — NEUCHÂTEL » (V658) :
 * e-mails avec « Objet : … » en première ligne, scripts téléphoniques,
 * fiches sans coordonnée, et le marqueur « [À COMPLÉTER AVANT ENVOI ] ».
 */
import {
  objetEtCorps, preparationJ0, compteursPreparation, campagneAvantEnvoi,
  PREPARATIONS, lignesRelances, compteursRelances, filtrerRelances, etapeJ0,
} from '../messagesRelances';

const PREPAREE = { id: 'c1', etat: 'preparee' };
const APPROUVEE = { id: 'c1', etat: 'approuvee', subject_j0: 'Objet de secours' };

const EMAIL_OK = 'Objet : Une expérience originale pour vos équipes\n\nBonjour,\n\nJe suis Coach Bassi.';

const act = (over) => ({
  id: 'a', campaign_id: 'c1', recipient_key: 'CORP-NE-01', channel: 'email',
  execution_type: 'AUTO', statut: 'pret', message_j0: EMAIL_OK, message_j0_origine: 'edite',
  updated_at: '2026-11-10T03:00:00+00:00', ...over,
});

describe('objetEtCorps : miroir de v602_objet_et_corps (serveur)', () => {
  test('« Objet : X » en première ligne devient l’objet et SORT du corps', () => {
    const r = objetEtCorps(EMAIL_OK, 'secours');
    expect(r.objet).toBe('Une expérience originale pour vos équipes');
    expect(r.corps.startsWith('Bonjour,')).toBe(true);
    expect(r.corps).not.toMatch(/Objet\s*:/);
    expect(r.objetPropre).toBe(true);
  });
  test('sans ligne « Objet : », l’objet de la campagne sert de secours, corps intact', () => {
    const r = objetEtCorps('Bonjour,\n\nTexte.', 'secours');
    expect(r.objet).toBe('secours');
    expect(r.corps).toBe('Bonjour,\n\nTexte.');
    expect(r.objetPropre).toBe(false);
  });
  test('« Sujet : … » n’est PAS un objet (le formulaire Microcity en porte un)', () => {
    expect(objetEtCorps('Sujet : Une expérience\n\nBonjour', '').objet).toBe('');
  });
  test('message absent : ni objet ni corps, aucune exception', () => {
    expect(objetEtCorps(null, '')).toEqual({ objet: '', corps: '', objetPropre: false });
  });
});

describe('preparationJ0', () => {
  test('e-mail complet, campagne NON approuvée -> À RELIRE', () => {
    const p = preparationJ0(act(), PREPAREE, null);
    expect(p.code).toBe(PREPARATIONS.A_RELIRE);
    expect(p.manques).toEqual([]);
    expect(p.prochaine).toMatch(/approuver/i);
  });
  test('le MÊME message, campagne approuvée -> PRÊT, aucun blocage', () => {
    const p = preparationJ0(act(), APPROUVEE, null);
    expect(p.code).toBe(PREPARATIONS.PRET);
    expect(p.prochaine).toMatch(/aucun blocage/i);
  });
  test('e-mail SANS objet (ni dans le texte ni sur la campagne) -> BROUILLON', () => {
    const p = preparationJ0(act({ message_j0: 'Bonjour,\n\nTexte.' }), PREPAREE, null);
    expect(p.code).toBe(PREPARATIONS.BROUILLON);
    expect(p.manques).toContain('objet manquant');
  });
  test('objet porté par la campagne : plus de manque', () => {
    expect(preparationJ0(act({ message_j0: 'Bonjour,' }), APPROUVEE, null).code).toBe(PREPARATIONS.PRET);
  });
  test('marqueur « [À COMPLÉTER AVANT ENVOI ] » -> BROUILLON', () => {
    const p = preparationJ0(act({ message_j0: 'Objet : X\n\nVoici [À COMPLÉTER AVANT ENVOI : lien PDF]' }), APPROUVEE, null);
    expect(p.code).toBe(PREPARATIONS.BROUILLON);
    expect(p.manques).toContain('information à compléter dans le texte');
  });
  test('« LIEN À CRÉER » aussi', () => {
    expect(preparationJ0(act({ message_j0: 'Objet : X\n\nVidéo : [LIEN À CRÉER]' }), APPROUVEE, null).code)
      .toBe(PREPARATIONS.BROUILLON);
  });
  test('message absent (origine « absent ») -> BROUILLON, message manquant', () => {
    const p = preparationJ0(act({ message_j0: '', message_j0_origine: 'absent' }), APPROUVEE, null);
    expect(p.code).toBe(PREPARATIONS.BROUILLON);
    expect(p.manques).toContain('message manquant');
  });
  test('un SCRIPT téléphonique n’a pas besoin d’objet -> à relire, aucun manque', () => {
    const p = preparationJ0(act({ channel: 'telephone', execution_type: 'MANUEL',
      message_j0: 'SCRIPT D’APPEL\n\nBonjour, je suis Coach Bassi.' }), PREPAREE, null);
    expect(p.code).toBe(PREPARATIONS.A_RELIRE);
    expect(p.manques).toEqual([]);
  });
  test('aucune coordonnée -> BLOQUÉ, avec le motif du serveur', () => {
    const p = preparationJ0(act({ channel: 'aucun', execution_type: 'BLOQUE', statut: 'bloque',
      execution_reason: 'aucune coordonnee numerique exploitable' }), PREPAREE, null);
    expect(p.code).toBe(PREPARATIONS.BLOQUE);
    expect(p.prochaine).toMatch(/aucune coordonnee/i);
  });
  test('exclu -> BLOQUÉ ; déjà envoyé -> ENVOYÉ', () => {
    expect(preparationJ0(act({ statut: 'exclu' }), PREPAREE, null).code).toBe(PREPARATIONS.BLOQUE);
    expect(preparationJ0(act({ sent_at: '2026-11-01T08:00:00+00:00' }), APPROUVEE, null).code)
      .toBe(PREPARATIONS.ENVOYE);
  });
  test('refus de contact / corbeille sur la fiche -> BLOQUÉ', () => {
    expect(preparationJ0(act(), PREPAREE, { ne_plus_contacter: true }).code).toBe(PREPARATIONS.BLOQUE);
    expect(preparationJ0(act(), PREPAREE, { corbeille: true }).code).toBe(PREPARATIONS.BLOQUE);
  });
  test('la date de dernière modification est celle de l’action', () => {
    expect(preparationJ0(act(), PREPAREE, null).modifieLe).toBe('2026-11-10T03:00:00+00:00');
  });
});

describe('intégration : lignes, compteurs, filtres', () => {
  const actions = [
    act({ id: 'ok1', recipient_key: 'CORP-NE-01' }),
    act({ id: 'ok2', recipient_key: 'CORP-NE-02' }),
    act({ id: 'sansObjet', recipient_key: 'CORP-NE-03', message_j0: 'Bonjour,' }),
    act({ id: 'bloque', recipient_key: 'CORP-NE-11', channel: 'aucun', execution_type: 'BLOQUE', statut: 'bloque' }),
    act({ id: 'parti', recipient_key: 'CORP-NE-14', sent_at: '2026-11-01T08:00:00+00:00' }),
  ];
  const lignes = lignesRelances(actions, PREPAREE, [], [], Date.parse('2026-11-10T04:00:00Z'));

  test('chaque ligne porte sa préparation, sans toucher `etat`', () => {
    const par = {};
    lignes.forEach((l) => { par[l.id] = l.preparation.code; });
    expect(par).toEqual({
      ok1: PREPARATIONS.A_RELIRE, ok2: PREPARATIONS.A_RELIRE,
      sansObjet: PREPARATIONS.BROUILLON, bloque: PREPARATIONS.BLOQUE, parti: PREPARATIONS.ENVOYE,
    });
    expect(lignes.find((l) => l.id === 'parti').etat).toBeDefined();
  });

  test('compteurs : 1 brouillon, 2 à relire, 1 bloqué, 1 envoyé', () => {
    expect(compteursPreparation(lignes)).toEqual({ brouillons: 1, aRelire: 2, prets: 0, bloques: 1, envoyes: 1 });
    expect(compteursRelances(lignes)).toMatchObject({ brouillons: 1, aRelire: 2, bloques: 1 });
  });

  test('les compteurs HISTORIQUES ne bougent pas', () => {
    expect(compteursRelances(lignes)).toMatchObject({ total: 5, j0Envoyes: 1 });
  });

  test('filtres : un clic montre uniquement les brouillons', () => {
    const ids = (f) => filtrerRelances(lignes, f).map((l) => l.id).sort();
    expect(ids('brouillons')).toEqual(['sansObjet']);
    expect(ids('a_relire')).toEqual(['ok1', 'ok2']);
    expect(ids('prets')).toEqual([]);
    expect(ids('bloques')).toEqual(['bloque']);
    expect(ids('tous')).toHaveLength(5);
  });

  test('la recherche trouve un brouillon par son libellé', () => {
    expect(filtrerRelances(lignes, 'tous', 'tous', 'brouillon').map((l) => l.id)).toEqual(['sansObjet']);
  });

  test('l’étape J0 affiche l’objet du message et un corps sans la ligne « Objet : »', () => {
    const e = etapeJ0(act(), PREPAREE);
    expect(e.objet).toBe('Une expérience originale pour vos équipes');
    expect(e.message).not.toMatch(/Objet\s*:/);
  });
});

describe('campagneAvantEnvoi', () => {
  test('vrai tant que la campagne n’est pas approuvée', () => {
    expect(campagneAvantEnvoi({ etat: 'preparee' })).toBe(true);
    expect(campagneAvantEnvoi({ etat: 'brouillon' })).toBe(true);
    expect(campagneAvantEnvoi({ etat: 'approuvee' })).toBe(false);
    expect(campagneAvantEnvoi({ etat: 'en_cours' })).toBe(false);
    expect(campagneAvantEnvoi({})).toBe(false);
  });
});
