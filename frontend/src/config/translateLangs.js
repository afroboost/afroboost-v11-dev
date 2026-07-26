// V297 — Liste UNIQUE des langues de traduction du chat.
//
// Alignée sur le sélecteur de langue du site (frontend/src/App.js ~ligne 913 :
// FR/EN/DE/LN/WO/SW/BM/BA/CR). Les langues africaines manquaient dans le chat
// (V292 n'avait que 6 langues européennes) -> on les ajoute ici pour que le
// bouton de traduction propose EXACTEMENT les mêmes langues que le reste du site.
//
// `code` : envoyé à POST /api/translate (le backend le mappe au nom complet via
//          _V292_LANGS, server.py). `label` : sigle affiché (2 lettres).
export const TRANSLATE_LANGS = [
  { code: 'fr', label: 'FR' },
  { code: 'en', label: 'EN' },
  { code: 'de', label: 'DE' },
  { code: 'ln', label: 'LN' },   // Lingala
  { code: 'wo', label: 'WO' },   // Wolof
  { code: 'sw', label: 'SW' },   // Swahili
  { code: 'bm', label: 'BM' },   // Bambara
  { code: 'bas', label: 'BA' },  // Bassa (Cameroun)
  { code: 'ht', label: 'CR' },   // Créole haïtien
  // it/es/pt conservés EN PLUS (V292) — aucune régression
  { code: 'it', label: 'IT' },
  { code: 'es', label: 'ES' },
  { code: 'pt', label: 'PT' },
];
