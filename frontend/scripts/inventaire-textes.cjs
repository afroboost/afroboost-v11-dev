/**
 * Inventaire des textes ÉCRITS EN DUR dans le JSX — par arbre syntaxique.
 *
 * Une expression régulière rate les textes sur plusieurs lignes, les attributs
 * et les littéraux passés à une fonction. Ici : le vrai AST (Babel, déjà dans
 * le projet), donc ce qui est compté est ce qui est réellement rendu.
 *
 * Usage : node scripts/inventaire-textes.cjs <fichier.js> [--json]
 * Sortie : texte, ligne, nature (jsx | attribut | message).
 */
const fs = require('fs');
const parser = require('@babel/parser');
const traverse = require('@babel/traverse').default;

const fichier = process.argv[2];
const enJson = process.argv.includes('--json');
const src = fs.readFileSync(fichier, 'utf8');
const ast = parser.parse(src, { sourceType: 'module', plugins: ['jsx'], errorRecovery: true });

const ATTRIBUTS = new Set(['placeholder', 'title', 'aria-label', 'alt', 'label']);
const MESSAGES = new Set(['alert', 'setError', 'setMessage', 'setToast', 'showToast', 'toast', 'setStatus', 'setSuccess']);

// Un texte « à traduire » : contient des lettres, n'est ni une URL, ni un
// identifiant technique, ni un nombre, ni une classe CSS.
function traduisible(t) {
  const s = t.replace(/\s+/g, ' ').trim();
  if (s.length < 2) return false;
  if (!/[A-Za-zÀ-ÿ]{2,}/.test(s)) return false;
  if (/^(https?:|\/|#|\.|data:|[\w-]+\.(js|png|jpg|svg|css))/.test(s)) return false;
  if (/^[\w-]+$/.test(s) && /[-_]/.test(s)) return false;        // classe / identifiant
  if (/^[a-z]+[A-Z]\w*$/.test(s)) return false;                    // camelCase
  return true;
}

const trouves = [];
const ajouter = (texte, ligne, nature) => {
  const t = texte.replace(/\s+/g, ' ').trim();
  if (traduisible(t)) trouves.push({ texte: t, ligne, nature });
};

traverse(ast, {
  JSXText(p) { ajouter(p.node.value, p.node.loc.start.line, 'jsx'); },
  JSXAttribute(p) {
    const nom = p.node.name && p.node.name.name;
    if (!ATTRIBUTS.has(nom)) return;
    const v = p.node.value;
    if (v && v.type === 'StringLiteral') ajouter(v.value, v.loc.start.line, `attribut:${nom}`);
  },
  CallExpression(p) {
    const c = p.node.callee;
    const nom = c.type === 'Identifier' ? c.name : (c.type === 'MemberExpression' && c.property.name) || '';
    if (!MESSAGES.has(nom)) return;
    const a = p.node.arguments[0];
    if (a && a.type === 'StringLiteral') ajouter(a.value, a.loc.start.line, `message:${nom}`);
    if (a && a.type === 'TemplateLiteral' && a.quasis.length === 1) ajouter(a.quasis[0].value.cooked, a.loc.start.line, `message:${nom}`);
  },
});

if (enJson) {
  console.log(JSON.stringify(trouves));
} else {
  for (const t of trouves) console.log(`${t.ligne}\t${t.nature}\t${t.texte}`);
  console.error(`\n${trouves.length} textes en dur dans ${fichier}`);
}
