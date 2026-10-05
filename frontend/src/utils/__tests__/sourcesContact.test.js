// V573 — Contacts : toutes les origines d'une fiche, avec un libellé lisible.
import { libelleSource, sourcesAffichees } from '../sourcesContact';

test('« live_afroboost » s’affiche « Afroboost Live » (valeur interne inchangée)', () => {
  expect(libelleSource('live_afroboost')).toBe('Afroboost Live');
  expect(libelleSource('google')).toBe('Google');
  expect(libelleSource('app')).toBe('App');
  expect(libelleSource('stripe_payment')).toBe('Stripe');
  expect(libelleSource('chat_login')).toBe('chat_login');
  expect(libelleSource('')).toBe('Import');
});

test('B. chat_login + live_afroboost → deux badges, dans l’ordre', () => {
  expect(sourcesAffichees({ source: 'chat_login', sources: ['chat_login', 'live_afroboost'] }))
    .toEqual(['chat_login', 'live_afroboost']);
});

test('ancienne réponse sans `sources` → la source principale seule', () => {
  expect(sourcesAffichees({ source: 'google' })).toEqual(['google']);
  expect(sourcesAffichees({})).toEqual(['import']);
});

test('jamais deux fois le même badge, valeurs vides ignorées', () => {
  expect(sourcesAffichees({ source: 'app', sources: ['app', '', null, 'app', 'live_afroboost'] }))
    .toEqual(['app', 'live_afroboost']);
});
