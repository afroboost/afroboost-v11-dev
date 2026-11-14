// Détecte tout appel t(...) / TexteDynamique placé DANS le corps d'une requête réseau
// (axios.post/put/patch, fetch avec body). Un libellé traduit envoyé au serveur à la place
// d'un identifiant casse silencieusement une réservation.
const fs = require('fs'); const parser = require('@babel/parser'); const traverse = require('@babel/traverse').default;
let total = 0; const fautes = [];
for (const f of process.argv.slice(2)) {
  const ast = parser.parse(fs.readFileSync(f, 'utf8'), { sourceType: 'module', plugins: ['jsx'], errorRecovery: true });
  traverse(ast, {
    CallExpression(p) {
      const c = p.node.callee;
      const nom = c.type === 'MemberExpression' ? `${c.object.name || ''}.${c.property.name || ''}` : (c.name || '');
      const estReseau = /^(axios\.(post|put|patch|delete)|fetch)$/.test(nom) || /\.(post|put|patch)$/.test(nom);
      if (!estReseau) return;
      total += 1;
      const aVerifier = p.node.arguments.slice(1);   // 1er arg = URL (peut contenir des identifiants, pas de libellés)
      aVerifier.forEach((arg) => {
        const sub = { found: [] };
        p.get(`arguments.${p.node.arguments.indexOf(arg)}`).traverse({
          CallExpression(q) { if (q.node.callee.type === 'Identifier' && q.node.callee.name === 't') sub.found.push(q.node.loc.start.line); },
        });
        if (arg.type === 'CallExpression' && arg.callee.name === 't') sub.found.push(arg.loc.start.line);
        // Indirect : une variable dont la déclaration appelle t(), utilisée dans le corps.
        p.get(`arguments.${p.node.arguments.indexOf(arg)}`).traverse({
          Identifier(q) {
            if (!q.isReferencedIdentifier()) return;
            const b = q.scope.getBinding(q.node.name);
            if (!b || !b.path.isVariableDeclarator() || !b.path.node.init) return;
            let contientT = false;
            b.path.get('init').traverse({ CallExpression(r) { if (r.node.callee.type === 'Identifier' && r.node.callee.name === 't') contientT = true; } });
            if (b.path.node.init.type === 'CallExpression' && b.path.node.init.callee.name === 't') contientT = true;
            if (contientT) sub.found.push(q.node.loc.start.line);
          },
        });
        sub.found.forEach((l) => fautes.push(`${f}:${l} ← t() dans le corps de ${nom}`));
      });
    },
  });
}
console.log(`${total} appels réseau examinés ; ${fautes.length} t() dans un corps de requête`);
fautes.forEach((x) => console.log('  !', x));
process.exit(fautes.length ? 1 : 0);
