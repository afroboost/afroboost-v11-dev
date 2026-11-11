import { notificationsAbonne, PAS_ENCORE_SUIVIS } from '../notificationsAbonne';

const T0 = new Date('2026-11-11T09:00:00Z').getTime();
const dans = (j, h = 0) => new Date(T0 + j * 86400000 + h * 3600000).toISOString();

describe('V660 — le fil de l’abonné, tiré de ses propres données', () => {
  test('la prochaine séance arrive en tête, avec son code', () => {
    const l = notificationsAbonne({
      maintenant: T0,
      reservations: [
        { id: 'r2', datetime: dans(9), courseName: 'Cours à l’unité' },
        { id: 'r1', datetime: dans(2), courseName: 'Cardio-danse', locationName: 'Valangines 97',
          reservationCode: 'AFR-123456' },
        { id: 'r0', datetime: dans(-5), courseName: 'Passé' },   // déjà fait : ignoré
      ],
    });
    expect(l[0].type).toBe('cours');
    expect(l[0].titre).toBe('Ta prochaine séance');
    expect(l[0].texte).toContain('Cardio-danse');          // la PLUS PROCHE, pas la première du tableau
    expect(l[0].texte).toContain('Valangines 97');
    expect(l[0].texte).toContain('AFR-123456');
    expect(l[0].texte).not.toContain('Passé');
  });

  test('une séance du jour est annoncée comme telle', () => {
    const l = notificationsAbonne({ maintenant: T0, reservations: [{ id: 'r', datetime: dans(0, 4), courseName: 'Cours' }] });
    expect(l[0].titre).toBe('Ta séance, aujourd’hui');
  });

  test('aucune réservation à venir : aucune notification de cours', () => {
    const l = notificationsAbonne({ maintenant: T0, reservations: [{ id: 'r', datetime: dans(-2) }] });
    expect(l.filter((n) => n.type === 'cours')).toHaveLength(0);
  });

  test('les séances qui s’épuisent : on prévient AVANT zéro', () => {
    const a1 = notificationsAbonne({ maintenant: T0, subscription: { remaining_sessions: 1, offer_name: 'PULSE x10' } });
    expect(a1[0].titre).toBe('Il te reste 1 séance');
    expect(a1[0].texte).toContain('PULSE x10');
    const a2 = notificationsAbonne({ maintenant: T0, subscription: { remaining_sessions: 2 } });
    expect(a2[0].titre).toBe('Il te reste 2 séances');
    // Au-delà de 2, on ne dit rien : ce n'est pas une information utile.
    expect(notificationsAbonne({ maintenant: T0, subscription: { remaining_sessions: 5 } })).toHaveLength(0);
  });

  test('plus aucune séance : on le dit clairement', () => {
    const l = notificationsAbonne({ maintenant: T0, subscription: { remaining_sessions: 0 } });
    expect(l[0].titre).toBe('Il ne te reste plus de séance');
  });

  test('l’échéance de l’abonnement, avant et après', () => {
    const proche = notificationsAbonne({ maintenant: T0, subscription: { expires_at: dans(5) } });
    expect(proche[0].titre).toBe('Ton abonnement se termine bientôt');
    expect(proche[0].texte).toContain('dans 5 jours');
    const aujourdhui = notificationsAbonne({ maintenant: T0, subscription: { expires_at: dans(0) } });
    expect(aujourdhui[0].titre).toBe('Ton abonnement se termine aujourd’hui');
    const passe = notificationsAbonne({ maintenant: T0, subscription: { expires_at: dans(-3) } });
    expect(passe[0].titre).toBe('Ton abonnement a expiré');
    // Au-delà de 15 jours, rien : on n'inquiète pas pour rien.
    expect(notificationsAbonne({ maintenant: T0, subscription: { expires_at: dans(60) } })).toHaveLength(0);
  });

  test('tout vide, tout cassé : aucune erreur, aucune notification inventée', () => {
    expect(notificationsAbonne()).toEqual([]);
    expect(notificationsAbonne({})).toEqual([]);
    expect(notificationsAbonne({ reservations: null, subscription: null })).toEqual([]);
    expect(notificationsAbonne({ reservations: [null, undefined, {}] })).toEqual([]);
    expect(notificationsAbonne({ maintenant: T0, subscription: { expires_at: 'pas-une-date' } })).toEqual([]);
    expect(notificationsAbonne({ maintenant: T0, reservations: [{ datetime: 'nawak' }] })).toEqual([]);
  });

  test('un abonné complet reçoit plusieurs notifications, sans doublon d’identifiant', () => {
    const l = notificationsAbonne({
      maintenant: T0,
      reservations: [{ id: 'r', datetime: dans(1), courseName: 'Cardio' }],
      subscription: { remaining_sessions: 1, expires_at: dans(4) },
    });
    expect(l.length).toBe(3);
    expect(new Set(l.map((n) => n.id)).size).toBe(3);
  });

  test('ce qui n’existe pas encore est NOMMÉ, pas inventé', () => {
    expect(PAS_ENCORE_SUIVIS.length).toBeGreaterThan(0);
    expect(PAS_ENCORE_SUIVIS.join(' ')).toMatch(/annulé par le coach/);
    // Aucune de ces situations ne doit produire une notification fabriquée.
    const l = notificationsAbonne({ maintenant: T0, reservations: [], subscription: { remaining_sessions: 8 } });
    expect(l).toEqual([]);
  });
});
