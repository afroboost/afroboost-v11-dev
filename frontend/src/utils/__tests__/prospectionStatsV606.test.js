// V606 — une fiche « adresse à corriger » ne compte dans aucune étape ; elle est comptée à part.
import { compter, etapes } from '../prospectionStats';

const F = (o) => ({ id: o.ref, ref: o.ref, created_at: '2026-09-01T00:00:00Z', ...o });

test('les 10 fiches à adresse partagée ne gonflent ni Contactés ni Réponses', () => {
  const fiches = [
    F({ ref: 'T', status: 'repondu', replied_at: '2026-10-11T08:23:00Z', first_contact_sent_at: '2026-10-11T08:09:00Z' }),
    ...Array.from({ length: 10 }, (_, i) => F({ ref: `E${i}`, status: 'repondu', replied_at: '2026-10-11T08:23:00Z',
      first_contact_sent_at: '2026-10-11T08:09:00Z', adresse_a_corriger: true })),
    F({ ref: 'S', status: 'contacte', first_contact_sent_at: '2026-10-11T08:09:00Z' }),
    F({ ref: 'A', status: 'a_contacter' }),
  ];
  const c = compter(fiches);
  expect(c.total).toBe(13);
  expect(c.contacte).toBe(2);
  expect(c.reponse).toBe(1);
  expect(c.sans_reponse).toBe(1);
  expect(c.a_contacter).toBe(1);
  expect(c.adresse_a_corriger).toBe(10);
  expect(etapes(fiches[1]).adresse_a_corriger).toBe(true);
});
