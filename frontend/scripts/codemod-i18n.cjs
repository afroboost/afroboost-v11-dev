/**
 * Codemod i18n — remplace les textes FRANÇAIS ÉCRITS EN DUR par `t('clé')`.
 *
 * Par arbre syntaxique (Babel) : ce qui est converti est exactement ce qui est
 * rendu, au caractère près. Deux temps :
 *
 *   node scripts/codemod-i18n.cjs <fichier> --plan [--prefixe v_]   (à blanc)
 *   node scripts/codemod-i18n.cjs <fichier> --appliquer              (écrit)
 *
 * GARANTIE « le français ne change pas » : chaque clé créée a pour valeur
 * française le texte d'origine, au caractère près (test dédié). Un texte dont on
 * ne peut pas PROUVER que `t` est la bonne fonction dans sa portée est IGNORÉ et
 * listé — jamais converti « à tout hasard ».
 *
 * Ne convertit PAS :
 *   - un texte qui n'est qu'un FRAGMENT de phrase (frères = autres textes ou
 *     `{expressions}`) : l'ordre des mots change d'une langue à l'autre, il se
 *     traduit à la main avec ses variables ;
 *   - les noms de marque, devises, adresses, courriels ;
 *   - ce qui est dans une fonction qui n'est pas un composant (règle des hooks).
 */
const fs = require('fs');
const parser = require('@babel/parser');
const traverse = require('@babel/traverse').default;

const [, , fichier, ...args] = process.argv;
const appliquer = args.includes('--appliquer');
const iPref = args.indexOf('--prefixe');
const PREFIXE = iPref >= 0 ? args[iPref + 1] : 'v_';
const FICHIER_TABLE = (args.find((a) => a.startsWith('--table=')) || '').slice(8);
const IGNORER_COMPOSANTS = new Set((args.find((a) => a.startsWith('--ignorer=')) || '').slice(10).split(',').filter(Boolean));

const src = fs.readFileSync(fichier, 'utf8');
const ast = parser.parse(src, { sourceType: 'module', plugins: ['jsx'], errorRecovery: true });

const ATTRIBUTS = new Set(['placeholder', 'title', 'aria-label', 'alt']);
// Tout setter dont le NOM dit qu'il porte un message à l'utilisateur : setError, setErreur,
// setV528EmailErreur, setMessage, setToast, setStatus, setSuccess, setNotice, setInfo…
const MESSAGES = { has: (n) => n === 'alert' || /^set[A-Za-z0-9]*(Err|Erreur|Error|Message|Msg|Toast|Status|Notice|Success|Info)$/.test(n) };
// Propriétés d'objet qui portent un message : { erreur: '…' }, { error: '…' }, { message: '…' }.
const CLES_MESSAGE = new Set(['erreur', 'error', 'message', 'msg']);

const MARQUES = /^(afroboost|chf|twint|paypal|visa|mastercard|maps|spordateur|afroboost live|afroboost collection|youtube video|vimeo video|media|event poster|photo profil|auto|stripe|©.*)$/i;
function exclu(t) {
  const s = t.trim();
  if (MARQUES.test(s)) return 'marque';
  if (/@/.test(s) || /^https?:/.test(s)) return 'contact';
  if (/^[a-z0-9]+(_[a-z0-9]+)+$/.test(s)) return 'identifiant technique';
  if (/[{};]/.test(s) && /[:;]\s*[\w!#.-]+/.test(s) && /[\[.#>@]|!important|display|margin|padding/.test(s)) return 'css';
  if (/^[+\d\sXx().-]+$/.test(s) && /[Xx]/.test(s)) return 'gabarit (téléphone, date…)';
  if (/^[\w-]+(\.[\w-]+)*\.(com|ch|fr|org|net)$/i.test(s)) return 'domaine';
  if (/\b(rue|chemin)\b.*\d{4}/i.test(s) || /^\w{3} \d{1,2}H\d{2}/.test(s)) return 'adresse/horaire';
  if (/^[\W\d_]+$/.test(s)) return 'symboles';
  if (/^(MER|DIM|LUN|MAR|JEU|VEN|SAM)\b/.test(s)) return 'horaire';
  return null;
}
function norm(t) { return t.replace(/\s+/g, ' ').trim(); }

function slug(t) {
  const base = t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 36) || 'texte';
  return PREFIXE + base;
}

const cles = {};          // texte -> clé
const textes = {};        // clé -> texte
function cleDe(texte) {
  if (cles[texte]) return cles[texte];
  let k = slug(texte); let n = 2;
  while (textes[k] && textes[k] !== texte) k = `${slug(texte)}_${n++}`;
  cles[texte] = k; textes[k] = texte;
  return k;
}

// ── Reconnaître le `t` légitime dans une portée ────────────────────────────
function tLegitime(path) {
  const b = path.scope.getBinding('t');
  if (!b) return { ok: false, raison: 't absent de la portée' };
  const n = b.path.node;
  // const t = useCallback(...) / const { t } = useLanguage() / const { t } = useTranslation(...)
  if (b.path.isVariableDeclarator()) {
    const init = n.init;
    if (init && init.type === 'CallExpression') {
      const c = init.callee.name || (init.callee.property && init.callee.property.name);
      if (['useCallback', 'useLanguage', 'useTranslation'].includes(c)) return { ok: true, pos: n.start, fin: n.end };
    }
    return { ok: false, raison: `t local non reconnu (${n.init && n.init.type})` };
  }
  // paramètre : ({ t, ... }) ou (t)
  if (b.kind === 'param') return { ok: true, pos: 0, fin: 0 };
  return { ok: false, raison: `t de nature ${b.kind}` };
}

function composantEnglobant(path) {
  // La fonction la plus EXTERNE dont les ancêtres, jusqu'au module, ne sont que des
  // déclarations (const X = …, export const X = …, export default function X).
  let p = path; let dernier = null;
  while (p) {
    if (p.isFunction()) {
      let a = p.parentPath; let ok = true;
      while (a && !a.isProgram()) {
        if (!(a.isVariableDeclarator() || a.isVariableDeclaration() || a.isExportNamedDeclaration() || a.isExportDefaultDeclaration())) { ok = false; break; }
        a = a.parentPath;
      }
      if (ok) dernier = p;
    }
    p = p.parentPath;
  }
  return dernier;
}
function nomDe(f) {
  if (!f) return null;
  if (f.node.id) return f.node.id.name;
  const par = f.parentPath;
  if (par.isVariableDeclarator() && par.node.id.type === 'Identifier') return par.node.id.name;
  return null;
}

const plan = [];         // { debut, fin, remplacement, texte, cle, nature, ligne }
const ignores = [];
const injections = new Map(); // composant -> true (besoin de `const { t } = useLanguage();`)

function considerer(path, texte, debut, fin, nature, fabriquer) {
  const ligne = path.node.loc.start.line;
  const n = norm(texte);
  if (!/[A-Za-zÀ-ÿ]{2,}/.test(n) || n.length < 2) return;
  const ex = exclu(n);
  if (ex) { ignores.push({ ligne, texte: n, raison: ex }); return; }
  // `setInstallStatus('waiting')`, `{ status: 'success' }` : un CODE d'état n'est pas un texte.
  if ((nature.startsWith('message:') || nature.startsWith('propriete:')) && /^[a-z][a-z0-9_-]*$/.test(n)) {
    ignores.push({ ligne, texte: n, raison: 'code d\'état (jeton technique)' }); return;
  }

  const comp = composantEnglobant(path);
  const nomComp = nomDe(comp);
  if (nomComp && IGNORER_COMPOSANTS.has(nomComp)) { ignores.push({ ligne, texte: n, raison: `composant ignoré (${nomComp})` }); return; }

  let verdict = tLegitime(path);
  if (!verdict.ok) {
    // Pas de `t` : on peut en injecter un SEULEMENT dans un composant (PascalCase,
    // règle des hooks) — pas dans une fonction utilitaire appelée conditionnellement.
    if (comp && nomComp && /^[A-Z]/.test(nomComp) && verdict.raison === 't absent de la portée') {
      injections.set(comp, nomComp);
      verdict = { ok: true, pos: -1 };
    } else {
      ignores.push({ ligne, texte: n, raison: `${verdict.raison}${nomComp ? ' · ' + nomComp : ''}` });
      return;
    }
  }
  // `t` défini APRÈS son usage dans le même corps (zone morte temporelle) : on ne touche pas.
  if (verdict.pos > 0 && debut < verdict.pos) {
    ignores.push({ ligne, texte: n, raison: 'avant la déclaration de t (zone morte)' }); return;
  }
  const cle = cleDe(n);
  plan.push({ debut, fin, texte: n, cle, nature, ligne, remplacement: fabriquer(cle), composant: nomComp });
}

traverse(ast, {
  JSXText(path) {
    const parent = path.parentPath;
    if (!parent.isJSXElement() && !parent.isJSXFragment()) return;
    const freres = parent.node.children;
    // Un frère est GÊNANT s'il porte du texte : un autre texte, une expression
    // `{…}`, ou un élément qui contient lui-même du texte (<strong>…</strong>).
    // Une icône (<svg/>, <img/>) à côté n'empêche pas de traduire la phrase entière.
    const portetexte = (c) => {
      if (c.type === 'JSXText') return !!c.value.trim();
      if (c.type === 'JSXExpressionContainer') return c.expression.type !== 'JSXEmptyExpression';
      if (c.type === 'JSXElement' || c.type === 'JSXFragment') return c.children.some(portetexte);
      return true;
    };
    const autres = freres.filter((c) => c !== path.node && portetexte(c));
    // Un mot en <strong>/<b>/<em>/<span>/<a> au milieu d'une phrase n'est PAS une
    // phrase : le traduire seul fabrique une phrase hybride. On le laisse à la main.
    // Emphase : un mot en <strong> au milieu d'une phrase, quel que soit le voisin.
    // <span> : simple conteneur de libellé — on ne le tient pour une phrase coupée
    // que s'il touche du TEXTE NU (« Appuyez sur <span>Ajouter</span> »), pas un
    // simple élément voisin (une icône, un compteur).
    const EMPHASE = new Set(['strong', 'b', 'em', 'i', 'u', 'mark', 'a', 'small', 'code']);
    const nomParent = parent.isJSXElement() && parent.node.openingElement.name.name;
    let dansPhrase = false;
    const gp = parent.parentPath;
    if (gp && (gp.isJSXElement() || gp.isJSXFragment())) {
      const voisins = gp.node.children.filter((c) => c !== parent.node);
      if (EMPHASE.has(nomParent)) dansPhrase = voisins.some(portetexte);
      else if (nomParent === 'span') dansPhrase = voisins.some((c) => (c.type === 'JSXText' && !!c.value.trim()));
    }
    if (autres.length || dansPhrase) {
      const n = norm(path.node.value);
      if (/[A-Za-zÀ-ÿ]{2,}/.test(n) && !exclu(n)) ignores.push({ ligne: path.node.loc.start.line, texte: n, raison: 'fragment de phrase (à traduire à la main)' });
      return;
    }
    const v = path.node.value;
    const lead = v.match(/^\s*/)[0]; const trail = v.match(/\s*$/)[0];
    considerer(path, v, path.node.start, path.node.end, 'jsx', (k) => `${lead}{t('${k}')}${trail}`);
  },
  // {'Texte'} · {cond ? 'A' : 'B'} · {cond && 'Texte'} — en ENFANT JSX ou dans un attribut textuel.
  StringLiteral(path) {
    const parent = path.parentPath;
    // Les attributs `title="x"` sont déjà traités par JSXAttribute : on ne traite ICI que
    // les littéraux enveloppés dans une expression.
    let n = path; let sortie = null;
    for (let i = 0; i < 4 && n.parentPath; i += 1) {
      const pp = n.parentPath;
      if (pp.isConditionalExpression() && (pp.node.consequent === n.node || pp.node.alternate === n.node)) { n = pp; continue; }
      if (pp.isLogicalExpression() && pp.node.operator === '&&' && pp.node.right === n.node) { n = pp; continue; }
      if (pp.isJSXExpressionContainer()) { sortie = pp; }
      break;
    }
    if (!sortie) return;
    const hote = sortie.parentPath;
    if (hote.isJSXAttribute()) {
      const nom = hote.node.name && hote.node.name.name;
      if (!ATTRIBUTS.has(nom)) return;
    } else if (!(hote.isJSXElement() || hote.isJSXFragment())) return;
    else {
      // enfant JSX : ne pas toucher un texte qui côtoie d'autres textes (fragment de phrase)
      const freres = hote.node.children.filter((c) => c !== sortie.node);
      const portetexte = (c) => (c.type === 'JSXText' ? !!c.value.trim() : c.type === 'JSXExpressionContainer' && c.expression.type !== 'JSXEmptyExpression');
      if (freres.some(portetexte)) { ignores.push({ ligne: path.node.loc.start.line, texte: norm(path.node.value), raison: 'expression au milieu de texte (à la main)' }); return; }
    }
    considerer(path, path.node.value, path.node.start, path.node.end, 'expression', (k) => `t('${k}')`);
  },
  JSXAttribute(path) {
    const nom = path.node.name && path.node.name.name;
    if (!ATTRIBUTS.has(nom)) return;
    const v = path.node.value;
    if (!v || v.type !== 'StringLiteral') return;
    considerer(path, v.value, v.start, v.end, `attribut:${nom}`, (k) => `{t('${k}')}`);
  },
  ObjectProperty(path) {
    const k = path.node.key && (path.node.key.name || path.node.key.value);
    const v = path.node.value;
    if (!CLES_MESSAGE.has(k) || !v || v.type !== 'StringLiteral') return;
    considerer(path, v.value, v.start, v.end, `propriete:${k}`, (cle) => `t('${cle}')`);
  },
  CallExpression(path) {
    const c = path.node.callee;
    const nom = c.type === 'Identifier' ? c.name : '';
    if (!MESSAGES.has(nom)) return;
    const a = path.node.arguments[0];
    if (!a || a.type !== 'StringLiteral') return;
    considerer(path, a.value, a.start, a.end, `message:${nom}`, (k) => `t('${k}')`);
  },
});

const convertis = plan.length;
const parNature = plan.reduce((m, p) => { const n = p.nature.split(':')[0]; m[n] = (m[n] || 0) + 1; return m; }, {});
console.error(`[plan] ${convertis} conversions (${JSON.stringify(parNature)}), ${Object.keys(textes).length} clés, ${ignores.length} ignorés, ${injections.size} composants à équiper de useLanguage()`);

if (!appliquer) {
  for (const p of plan) console.log(`OK \t${p.ligne}\t${p.cle}\t${p.texte.slice(0, 90)}`);
  for (const i of ignores) console.log(`NON\t${i.ligne}\t${i.raison}\t${i.texte.slice(0, 90)}`);
  for (const [, nom] of injections) console.log(`USE\t-\t${nom}`);
  process.exit(0);
}

// ── Application : de la fin vers le début, pour que les décalages ne comptent pas ──
let out = src;
const ops = plan.map((p) => ({ debut: p.debut, fin: p.fin, texte: p.remplacement }));
for (const [comp] of injections) {
  const corps = comp.node.body;
  if (corps.type === 'BlockStatement') {
    ops.push({ debut: corps.start + 1, fin: corps.start + 1, texte: '\n  const { t } = useLanguage();' });
  } else {
    // `=> ( <jsx> )`  devient  `=> { const { t } = useLanguage(); return ( <jsx> ); }`
    // (le corps peut être entre parenthèses : on part de la parenthèse ouvrante).
    const debut = corps.extra && corps.extra.parenthesized ? corps.extra.parenStart : corps.start;
    ops.push({ debut, fin: debut, texte: '{\n  const { t } = useLanguage();\n  return ' });
    ops.push({ debut: comp.node.end, fin: comp.node.end, texte: ';\n}' });
  }
}
// Import de useLanguage si on a équipé au moins un composant et qu'il n'est pas déjà importé.
if (injections.size && !/\buseLanguage\b[^;]*from\s+['"][^'"]*LanguageContext['"]/.test(src)) {
  const pathMod = require('path');
  const rel = pathMod.relative(pathMod.dirname(pathMod.resolve(fichier)), pathMod.resolve(__dirname, '..', 'src', 'contexts', 'LanguageContext')).split(pathMod.sep).join('/');
  const chemin = rel.startsWith('.') ? rel : './' + rel;
  const imports = ast.program.body.filter((n) => n.type === 'ImportDeclaration');
  const apres = imports.length ? imports[imports.length - 1].end : 0;
  ops.push({ debut: apres, fin: apres, texte: `\nimport { useLanguage } from '${chemin}'; // V670` });
}
ops.sort((a, b) => b.debut - a.debut || b.fin - a.fin);
for (const o of ops) out = out.slice(0, o.debut) + o.texte + out.slice(o.fin);
fs.writeFileSync(fichier, out);

if (FICHIER_TABLE) {
  const lignes = Object.keys(textes).sort().map((k) => `  ${JSON.stringify(k)}: { fr: ${JSON.stringify(textes[k])} },`);
  fs.writeFileSync(FICHIER_TABLE, `// GÉNÉRÉ par scripts/codemod-i18n.cjs — clés → texte français d'ORIGINE.\n// Les autres langues sont ajoutées à la main dans utils/i18n-visiteur.js.\nmodule.exports = {\n${lignes.join('\n')}\n};\n`);
}
console.error(`[appliqué] ${fichier} modifié.`);
