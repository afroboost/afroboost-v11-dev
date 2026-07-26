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
// V302 : `aiName` = désignation ISO 639-3 précise (lève l'ambiguïté « bassa » du
// Liberia vs Cameroun, etc.). Doit rester ALIGNÉ avec _V292_LANGS (api/server.py).
export const TRANSLATE_LANGS = [
  { code: 'fr',  label: 'FR', name: 'Français',  aiName: 'français',                                                                                          country: 'fr' },
  { code: 'en',  label: 'EN', name: 'English',   aiName: 'anglais',                                                                                           country: 'gb' },
  { code: 'de',  label: 'DE', name: 'Deutsch',   aiName: 'allemand',                                                                                          country: 'de' },
  { code: 'ln',  label: 'LN', name: 'Lingala',   aiName: 'lingala (lingála), langue bantoue du Congo — ISO 639-3 : lin',                                       country: 'cd' },
  { code: 'wo',  label: 'WO', name: 'Wolof',     aiName: 'wolof (wolof làkk), langue du Sénégal — ISO 639-3 : wol',                                            country: 'sn' },
  { code: 'sw',  label: 'SW', name: 'Kiswahili', aiName: 'kiswahili (swahili standard) — ISO 639-3 : swh',                                                     country: 'ke' },
  { code: 'bm',  label: 'BM', name: 'Bambara',   aiName: 'bambara (bamanankan), langue mandingue du Mali — ISO 639-3 : bam',                                   country: 'ml' },
  { code: 'bas', label: 'BA', name: 'Bassa',     aiName: 'bàsàa (basaa), langue bantoue A43 du Cameroun, régions du Centre et du Littoral — code ISO 639-3 : bas', country: 'cm' },
  { code: 'ht',  label: 'CR', name: 'Kreyòl',    aiName: 'kreyòl ayisyen (créole haïtien) — ISO 639-3 : hat',                                                  country: 'ht' },
];
