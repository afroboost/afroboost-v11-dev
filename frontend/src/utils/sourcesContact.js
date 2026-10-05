// V573 — Contacts : les ORIGINES d'une fiche (une fiche peut en avoir plusieurs, ex.
// chat_login + live_afroboost) et leur libellé à l'écran. Les valeurs internes ne changent pas.
const LIBELLES = {
  google: 'Google',
  app: 'App',
  stripe_payment: 'Stripe',
  live_afroboost: 'Afroboost Live',
};

export function libelleSource(source) {
  if (!source) return 'Import';
  return LIBELLES[source] || source;
}

/** `sources` (V573) si le serveur les renvoie, sinon la source principale seule. */
export function sourcesAffichees(contact) {
  const c = contact || {};
  const brutes = Array.isArray(c.sources) && c.sources.length ? c.sources : [c.source || 'import'];
  const vues = [];
  brutes.forEach((s) => { if (s && typeof s === 'string' && vues.indexOf(s) === -1) vues.push(s); });
  return vues.length ? vues : ['import'];
}
