// V297/V298 — Liste UNIQUE des langues de traduction du chat.
// V670 — Elle est maintenant AUSSI l'unique source du sélecteur de langue du site
// (PartnersCarousel + App.js) et du statut de relecture de chaque langue.
//
// Alignée sur le sélecteur de langue du site : FR/EN/DE/LN/WO/SW/BM/BA/CR ;
// traductions dans utils/i18n.js. Importée par ChatWidget (roue de traduction +
// mini-globe des bulles) pour que les langues ne divergent JAMAIS de celles du site.
//
// - code    : code TECHNIQUE (stocké dans `af_lang`, envoyé à POST /api/translate).
//             ⚠️ Il diffère du sigle visible pour le bassa (`bas` / BA) et le
//             créole (`ht` / CR) : ne jamais afficher `code.toUpperCase()`.
// - label   : sigle court visible (2 lettres).
// - name    : libellé affiché dans la roue du chat (endonyme).
// - fullName: nom complet affiché dans le menu du sélecteur (lève les ambiguïtés
//             « BA » / « CR » / « LN »).
// - aiName  : nom complet envoyé à l'IA (redondance de sécurité pour la traduction).
// - country : code pays pour le petit drapeau SVG (composant FlagIcon).
// - locale  : étiquette BCP 47 pour les dates (Intl) — jours/mois issus de CLDR,
//             jamais écrits à la main. Repli français si le navigateur ne la connaît pas.
// - status  : niveau de fiabilité de l'interface dans cette langue.
//     'source'   : français, langue d'origine.
//     'complete' : interface entièrement traduite (relecture interne).
//     'draft'    : interface traduite en totalité mais À FAIRE RELIRE par un locuteur natif.
//     'partial'  : seul un petit lexique est traduit ; tout le reste s'affiche en
//                  FRANÇAIS (repli). Ne jamais présenter ces langues comme « complètes ».
// V302 : `aiName` = désignation ISO 639-3 précise (lève l'ambiguïté « bassa » du
// Liberia vs Cameroun, etc.). Doit rester ALIGNÉ avec _V292_LANGS (api/server.py).
export const TRANSLATE_LANGS = [
  { code: 'fr',  label: 'FR', name: 'Français',  fullName: 'Français',        locale: 'fr-CH', status: 'source',   aiName: 'français',                                                                                          country: 'fr' },
  { code: 'en',  label: 'EN', name: 'English',   fullName: 'English',         locale: 'en-GB', status: 'complete', aiName: 'anglais',                                                                                           country: 'gb' },
  { code: 'de',  label: 'DE', name: 'Deutsch',   fullName: 'Deutsch',         locale: 'de-CH', status: 'complete', aiName: 'allemand',                                                                                          country: 'de' },
  { code: 'ln',  label: 'LN', name: 'Lingala',   fullName: 'Lingála',         locale: 'ln',    status: 'partial',  aiName: 'lingala (lingála), langue bantoue du Congo — ISO 639-3 : lin',                                       country: 'cd' },
  { code: 'wo',  label: 'WO', name: 'Wolof',     fullName: 'Wolof',           locale: 'wo',    status: 'partial',  aiName: 'wolof (wolof làkk), langue du Sénégal — ISO 639-3 : wol',                                            country: 'sn' },
  { code: 'sw',  label: 'SW', name: 'Kiswahili', fullName: 'Kiswahili',       locale: 'sw',    status: 'draft',    aiName: 'kiswahili (swahili standard) — ISO 639-3 : swh',                                                     country: 'ke' },
  { code: 'bm',  label: 'BM', name: 'Bambara',   fullName: 'Bamanankan',      locale: 'bm',    status: 'partial',  aiName: 'bambara (bamanankan), langue mandingue du Mali — ISO 639-3 : bam',                                   country: 'ml' },
  { code: 'bas', label: 'BA', name: 'Bassa',     fullName: 'Bàsàa (Bassa)',   locale: 'bas',   status: 'partial',  aiName: 'bàsàa (basaa), langue bantoue A43 du Cameroun, régions du Centre et du Littoral — code ISO 639-3 : bas', country: 'cm' },
  { code: 'ht',  label: 'CR', name: 'Kreyòl',    fullName: 'Kreyòl ayisyen',  locale: 'ht',    status: 'draft',    aiName: 'kreyòl ayisyen (créole haïtien) — ISO 639-3 : hat',                                                  country: 'ht' },
];

// V670 — Ce que le visiteur lit à côté d'une langue qui n'est pas « complète ».
// Le texte dit la vérité : pas « traduit », pas « vérifié ».
export const STATUT_LANGUE = {
  source:   { etiquette: '',        aide: '' },
  complete: { etiquette: '',        aide: '' },
  draft:    { etiquette: 'bêta',    aide: 'Traduction complète, en cours de relecture par des locuteurs natifs.' },
  partial:  { etiquette: 'partiel', aide: 'Traduction partielle : le reste du site s’affiche en français.' },
};

export const LANGUE_DEFAUT = 'fr';
export const CODES_LANGUES = TRANSLATE_LANGS.map((l) => l.code);

/** Entrée de configuration pour un code (insensible à la casse), sinon null. */
export function getLangue(code) {
  const c = String(code || '').toLowerCase();
  return TRANSLATE_LANGS.find((l) => l.code === c) || null;
}
