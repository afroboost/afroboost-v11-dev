// V608 — accepté ≠ remis : états affichés pour les envois SUIVIS (les envois historiques restent « Soumis »).
import { etatReponse } from '../prospectionFocus';
import { livraisonDe, etapeJ0, etapeRelance, LIBELLES_ETAT } from '../messagesRelances';

const MSG = { received_at: '2026-10-11T07:38:00+00:00' };
const conv = (suivi, envoi) => ({ dernier_message: MSG, dernier_message_at: MSG.received_at, statut_commercial: 'a_repondre',
  messages_recus: [MSG], envoi_suivi: suivi, derniere_reponse_afroboost: envoi || null,
  reponse_apres_dernier_message: !!envoi });

test('Conversation : accepté → « Envoi en cours », jamais « envoyée »', () => {
  const e = etatReponse(conv({ etat: 'envoi_en_cours', quand: '2026-10-11T10:03:21Z' }));
  expect(e.code).toBe('en_cours');
  expect(e.texte).toMatch(/Envoi en cours/);
});

test('Conversation : échec → « Réponse attendue » (à répondre) + Réessayer', () => {
  const e = etatReponse(conv({ etat: 'echec', raison: 'boom', quand: '2026-10-11T10:03:21Z' }));
  expect(e.code).toBe('a_repondre');
  expect(e.texte).toMatch(/Échec/);
  expect(e.reessai).toBe(true);
});

test('Conversation : quota → message de COMPTE, pas d’adresse fautive', () => {
  const e = etatReponse(conv({ etat: 'quota', quand: '2026-10-11T10:03:21Z' }));
  expect(e.texte).toBe('Non envoyé — quota Resend atteint');
  expect(e.reessai).toBe(true);
});

test('Conversation : remis → « remise le … »', () => {
  const envoi = { sent_at: '2026-10-11T10:03:21Z' };
  const e = etatReponse(conv({ etat: 'remis', quand: '2026-10-11T10:04:00Z' }, envoi));
  expect(e.code).toBe('envoyee');
  expect(e.texte).toMatch(/remise le/);
});

test('Messages & relances : remise suivie (J0 + relance) ; historique non suivi = « Soumis »', () => {
  expect(livraisonDe('delivered', true).libelle).toBe('Remis');
  expect(livraisonDe('accepted', true).libelle).toBe('Envoi en cours');
  expect(livraisonDe('failed', true, 'Reached the daily sending quota').libelle).toBe('Non envoyé — quota Resend atteint');
  expect(livraisonDe('failed', true, 'x').libelle).toMatch(/Échec/);
  expect(livraisonDe('accepted', false)).toBeNull();
  expect(LIBELLES_ETAT.envoye).toBe('Soumis');
  const j0 = etapeJ0({ sent_at: 'x', provider_status: 'delivered', suivi_livraison: true }, {});
  expect(j0.livraison.libelle).toBe('Remis');
  const j3 = etapeRelance({ sent_at: 'x', j3_sent_at: 'y', j3_provider_status: 'accepted' }, {}, 'j3', null, Date.now());
  expect(j3.livraison.libelle).toBe('Envoi en cours');
});
