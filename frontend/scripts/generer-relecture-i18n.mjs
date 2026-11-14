// Génère docs/I18N_A_RELIRE.md : toutes les traductions à faire relire par des locuteurs natifs.
// Source : frontend/src/utils/i18n-visiteur.js (jamais retapée ici).
//   node scripts/generer-relecture-i18n.mjs
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const racine = path.resolve(import.meta.dirname, '..');
const src = path.join(racine, 'src', 'utils', 'i18n-visiteur.js');
const tmp = path.join(os.tmpdir(), `i18n-visiteur-${process.pid}.mjs`);
fs.copyFileSync(src, tmp);
const { VISITEUR, VISITEUR_APP } = await import(tmp);
fs.unlinkSync(tmp);

const esc = (s) => String(s ?? '').replace(/\|/g, '\\|').replace(/\n/g, ' ');
const lignes = [];
lignes.push('# Traductions à faire relire — V670', '');
lignes.push('> **Fichier GÉNÉRÉ** par `frontend/scripts/generer-relecture-i18n.mjs` depuis `src/utils/i18n-visiteur.js`. Ne pas le modifier à la main : corriger la source, puis régénérer.', '');
lignes.push('## Statut des langues', '');
lignes.push('| Code | Langue | Statut | Ce que cela veut dire |', '|---|---|---|---|');
lignes.push('| `fr` | Français | source | Langue d\'origine. |');
lignes.push('| `en`, `de` | English, Deutsch | complète | Interface entièrement traduite (relecture interne). |');
lignes.push('| `sw`, `ht` | Kiswahili, Kreyòl ayisyen | **bêta — à relire** | Interface entièrement traduite, **jamais relue par un locuteur natif**. Visible dans le menu avec la mention « bêta ». |');
lignes.push('| `ln`, `wo`, `bm`, `bas` | Lingála, Wolof, Bamanankan, Bàsàa | **partielle** | Quelques mots seulement ; **tout le reste s\'affiche en français**. Aucune phrase n\'a été inventée : ces langues ont trop peu de données pour qu\'une traduction automatique soit fiable. Mention « partiel » dans le menu. |', '');
lignes.push('## Comment relire', '');
lignes.push('1. Ouvrir la table ci-dessous, colonne de la langue concernée.', '2. Corriger directement dans `frontend/src/utils/i18n-visiteur.js` (clé → langue).', '3. Ne JAMAIS modifier la colonne `fr` : un test vérifie que le français affiché n\'a pas changé.', '4. Une fois une langue relue en entier, passer son `status` de `draft` à `complete` dans `src/config/translateLangs.js` : la mention « bêta » disparaît du menu.', '');

const cles = Object.keys(VISITEUR);
lignes.push(`## Kiswahili et créole haïtien — interface visiteur (${cles.length} textes)`, '');
lignes.push('| Clé | Français | Kiswahili (sw) | Kreyòl (ht) |', '|---|---|---|---|');
for (const k of cles) lignes.push(`| \`${k}\` | ${esc(VISITEUR[k].fr)} | ${esc(VISITEUR[k].sw)} | ${esc(VISITEUR[k].ht)} |`);
lignes.push('');
const app = Object.keys(VISITEUR_APP);
lignes.push(`## Kiswahili et créole haïtien — réservation, paiement, billet, jours (${app.length} textes)`, '');
lignes.push('| Clé | Kiswahili (sw) | Kreyòl (ht) |', '|---|---|---|');
for (const k of app) lignes.push(`| \`${k}\` | ${esc(VISITEUR_APP[k].sw)} | ${esc(VISITEUR_APP[k].ht)} |`);
lignes.push('');

lignes.push('## Lingala, wolof, bambara, bàsàa — le peu qui existe', '');
lignes.push('Ces entrées sont du **vocabulaire** (un ou deux mots). Elles viennent de la table visiteur ou du lexique vérifié du serveur (`_V302_LEXIQUE`, avec ses sources).', '');
for (const l of ['ln', 'wo', 'bm', 'bas']) {
  const e = cles.filter((k) => VISITEUR[k][l]).map((k) => `\`${VISITEUR[k].fr}\` → \`${VISITEUR[k][l]}\``);
  lignes.push(`- **${l}** : ${e.length ? e.join(' ; ') : '— (aucune entrée : tout en français)'}`);
}
lignes.push('', '## Retiré parce que faux', '');
lignes.push('- `wo.discoverCta` : la phrase contenait « cours », « réservé » et « next » — du français et de l\'anglais dans une phrase censée être en wolof. Le français vaut mieux qu\'un faux wolof.', '');
fs.writeFileSync(path.resolve(racine, '..', 'docs', 'I18N_A_RELIRE.md'), lignes.join('\n'));
console.log(`docs/I18N_A_RELIRE.md : ${cles.length} + ${app.length} textes`);
