// V670 — OUTIL DE TEST / DE RAPPORT (jamais importé par l'application).
// Lit le dictionnaire local d'App.js (`_traductionsApp`) PAR ARBRE SYNTAXIQUE, sans
// importer App.js : une App de 11 000 lignes ne se charge pas dans un test unitaire.
const fs = require('fs');
const path = require('path');
const { parse } = require('@babel/parser');
const traverse = require('@babel/traverse').default;

function lireDictionnaireApp() {
  const code = fs.readFileSync(path.join(__dirname, '..', '..', 'App.js'), 'utf8');
  const ast = parse(code, { sourceType: 'module', plugins: ['jsx'], errorRecovery: true });
  const dict = {};
  traverse(ast, {
    VariableDeclarator(p) {
      if (p.node.id.name !== '_traductionsApp') return;
      p.node.init.properties.forEach((langue) => {
        const nom = langue.key.name || langue.key.value;
        dict[nom] = dict[nom] || {};
        (langue.value.properties || []).forEach((kv) => {
          if (kv.value.type === 'StringLiteral') dict[nom][kv.key.name || kv.key.value] = kv.value.value;
        });
      });
    },
  });
  return dict;
}

module.exports = { lireDictionnaireApp };
