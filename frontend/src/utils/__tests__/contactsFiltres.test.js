/**
 * CONTACTS V2 — les filtres cumulables.
 *
 * Le point à ne jamais perdre de vue : un canal disponible n'est pas une
 * autorisation de démarchage. Les deux dimensions sont testées séparément.
 */
import {
  filtrerContacts, FILTRES_VIDES, nombreFiltresActifs, VUES_RAPIDES,
} from '../contactsFiltres';

const c = (o) => ({
  name: 'Sans nom', email: '', whatsapp: '', phone: '',
  contact_type: null, statut_abonnement: 'non_abonne', zone: 'inconnue',
  canaux: { email: false, whatsapp: false, telephone: false },
  consentement: { email: 'inconnu', whatsapp: 'inconnu' },
  ...o,
});

const MARIE = c({ name: 'Marie Dupont', email: 'marie@x.io', whatsapp: '+41791234567',
  contact_type: 'participant', statut_abonnement: 'actif', zone: 'suisse',
  canaux: { email: true, whatsapp: true, telephone: true },
  consentement: { email: 'autorise', whatsapp: 'inconnu' } });

const PAUL = c({ name: 'Paul Mbeki', email: 'paul@x.io',
  contact_type: 'participant', statut_abonnement: 'ancien', zone: 'afrique',
  canaux: { email: true, whatsapp: false, telephone: false },
  consentement: { email: 'refuse', whatsapp: 'inconnu' } });

const ZOE = c({ name: 'Zoé Martin', whatsapp: '+33612345678',
  contact_type: 'prospect', statut_abonnement: 'non_abonne', zone: 'europe',
  canaux: { email: false, whatsapp: true, telephone: true } });

const ANON = c({ name: 'Sans classement', email: 'anon@x.io',
  canaux: { email: true, whatsapp: false, telephone: false } });

const TOUS = [MARIE, PAUL, ZOE, ANON];
const noms = (r) => r.map((x) => x.name).sort();
const f = (o) => ({ ...FILTRES_VIDES, ...o });

describe('CONTACTS V2 — filtres cumulables', () => {
  test('F1. sans filtre ni recherche, tout passe', () => {
    expect(filtrerContacts(TOUS, FILTRES_VIDES, '')).toHaveLength(4);
  });

  test('F2. type : « non classé » est une valeur, pas une absence de filtre', () => {
    expect(noms(filtrerContacts(TOUS, f({ types: ['__non_classe__'] }), '')))
      .toEqual(['Sans classement']);
    expect(noms(filtrerContacts(TOUS, f({ types: ['participant'] }), '')))
      .toEqual(['Marie Dupont', 'Paul Mbeki']);
  });

  test('F3. plusieurs cases dans une dimension = OU', () => {
    expect(filtrerContacts(TOUS, f({ types: ['participant', 'prospect'] }), '')).toHaveLength(3);
  });

  test('F4. deux dimensions = ET — Participant + Suisse', () => {
    expect(noms(filtrerContacts(TOUS, f({ types: ['participant'], zones: ['suisse'] }), '')))
      .toEqual(['Marie Dupont']);
  });

  test('F5. Participant + Afrique + Email', () => {
    expect(noms(filtrerContacts(TOUS, f({
      types: ['participant'], zones: ['afrique'], canaux: ['email'],
    }), ''))).toEqual(['Paul Mbeki']);
  });

  test('F6. Abonné actif + Suisse', () => {
    expect(noms(filtrerContacts(TOUS, f({ statuts: ['actif'], zones: ['suisse'] }), '')))
      .toEqual(['Marie Dupont']);
  });

  test('F7. Ancien abonné + WhatsApp → personne (Paul n’a pas WhatsApp)', () => {
    expect(filtrerContacts(TOUS, f({ statuts: ['ancien'], canaux: ['whatsapp'] }), ''))
      .toHaveLength(0);
  });

  test('F8. Prospect + Email → personne (Zoé n’a pas d’e-mail)', () => {
    expect(filtrerContacts(TOUS, f({ types: ['prospect'], canaux: ['email'] }), ''))
      .toHaveLength(0);
  });

  test('C1. CANAL disponible ≠ AUTORISATION : Paul a un e-mail, refusé', () => {
    expect(noms(filtrerContacts(TOUS, f({ canaux: ['email'] }), '')))
      .toEqual(['Marie Dupont', 'Paul Mbeki', 'Sans classement']);
    expect(noms(filtrerContacts(TOUS, f({ consentEmail: ['autorise'] }), '')))
      .toEqual(['Marie Dupont']);
    expect(noms(filtrerContacts(TOUS, f({ consentEmail: ['refuse'] }), '')))
      .toEqual(['Paul Mbeki']);
  });

  test('C2. sans trace, le consentement est « inconnu », jamais autorisé', () => {
    expect(noms(filtrerContacts(TOUS, f({ consentEmail: ['inconnu'] }), '')))
      .toEqual(['Sans classement', 'Zoé Martin']);
    expect(filtrerContacts(TOUS, f({ consentWhatsapp: ['autorise'] }), '')).toHaveLength(0);
  });

  test('R1. recherche insensible à la casse et aux accents', () => {
    expect(noms(filtrerContacts(TOUS, FILTRES_VIDES, 'zoe'))).toEqual(['Zoé Martin']);
    expect(noms(filtrerContacts(TOUS, FILTRES_VIDES, 'MARIE'))).toEqual(['Marie Dupont']);
  });

  test('R2. recherche par numéro — la forme nationale trouve le format E.164', () => {
    // La base est majoritairement en +41… ; on tape pourtant « 079… ».
    expect(noms(filtrerContacts(TOUS, FILTRES_VIDES, '0791234567'))).toEqual(['Marie Dupont']);
    expect(noms(filtrerContacts(TOUS, FILTRES_VIDES, '+41791234567'))).toEqual(['Marie Dupont']);
    expect(noms(filtrerContacts(TOUS, FILTRES_VIDES, '791234'))).toEqual(['Marie Dupont']);
    expect(filtrerContacts(TOUS, FILTRES_VIDES, '12')).toHaveLength(0); // < 3 chiffres
  });

  test('R3. recherche + filtres se combinent — « Marie » + Participant + Suisse', () => {
    expect(noms(filtrerContacts(TOUS, f({ types: ['participant'], zones: ['suisse'] }), 'marie')))
      .toEqual(['Marie Dupont']);
    expect(filtrerContacts(TOUS, f({ zones: ['afrique'] }), 'marie')).toHaveLength(0);
  });

  test('N1. le compteur de filtres actifs additionne les dimensions', () => {
    expect(nombreFiltresActifs(FILTRES_VIDES)).toBe(0);
    expect(nombreFiltresActifs(f({ types: ['participant'], zones: ['suisse', 'europe'] }))).toBe(3);
  });

  test('V1. cinq vues rapides seulement, et elles portent de vrais filtres', () => {
    expect(VUES_RAPIDES.map((v) => v.id))
      .toEqual(['tous', 'participants', 'abonnes', 'prospects', 'non_classes']);
    expect(noms(filtrerContacts(TOUS, VUES_RAPIDES[1].filtres, '')))
      .toEqual(['Marie Dupont', 'Paul Mbeki']);
    expect(noms(filtrerContacts(TOUS, VUES_RAPIDES[2].filtres, ''))).toEqual(['Marie Dupont']);
    expect(noms(filtrerContacts(TOUS, VUES_RAPIDES[4].filtres, ''))).toEqual(['Sans classement']);
  });

  test('P1. un contact sans dimensions dérivées ne fait pas planter le filtre', () => {
    const brut = [{ name: 'Brut' }];
    expect(filtrerContacts(brut, FILTRES_VIDES, '')).toHaveLength(1);
    expect(filtrerContacts(brut, f({ zones: ['inconnue'] }), '')).toHaveLength(1);
    expect(filtrerContacts(brut, f({ types: ['__non_classe__'] }), '')).toHaveLength(1);
  });
});
