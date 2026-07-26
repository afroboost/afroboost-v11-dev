// V297/V298 — Liste UNIQUE des langues de traduction du chat.
//
// Alignée sur le sélecteur de langue du site (frontend/src/App.js ~ligne 904 :
// FR/EN/DE/LN/WO/SW/BM/BA/CR ; traductions dans utils/i18n.js ~lignes 312-362).
// Importée par ChatWidget (roue de traduction + mini-globe des bulles) pour que
// les langues ne divergent JAMAIS de celles du site.
//
// - code    : envoyé à POST /api/translate (le backend le mappe au nom complet).
// - label   : sigle court (2 lettres).
// - name    : libellé affiché dans la roue (endonyme, comme le sélecteur du site).
// - aiName  : nom complet envoyé à l'IA (redondance de sécurité pour la traduction).
// - country : code pays pour le petit drapeau SVG (composant FlagIcon).
export const TRANSLATE_LANGS = [
  { code: 'fr',  label: 'FR', name: 'Français',  aiName: 'français',          country: 'fr' },
  { code: 'en',  label: 'EN', name: 'English',   aiName: 'anglais',           country: 'gb' },
  { code: 'de',  label: 'DE', name: 'Deutsch',   aiName: 'allemand',          country: 'de' },
  { code: 'ln',  label: 'LN', name: 'Lingala',   aiName: 'lingala',           country: 'cd' },
  { code: 'wo',  label: 'WO', name: 'Wolof',     aiName: 'wolof',             country: 'sn' },
  { code: 'sw',  label: 'SW', name: 'Kiswahili', aiName: 'swahili',           country: 'ke' },
  { code: 'bm',  label: 'BM', name: 'Bambara',   aiName: 'bambara',           country: 'ml' },
  { code: 'bas', label: 'BA', name: 'Bassa',     aiName: 'bassa (Cameroun)',  country: 'cm' },
  { code: 'ht',  label: 'CR', name: 'Kreyòl',    aiName: 'créole haïtien',    country: 'ht' },
];
