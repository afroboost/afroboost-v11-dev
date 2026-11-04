// V646 — l'onglet « Bot visiteurs » du ChatWidget n'est proposé qu'au super-admin : le serveur
// refuse tout autre compte, un partenaire n'aurait qu'un éditeur dont chaque envoi échoue.
const fs = require('fs');
const path = require('path');

const source = fs.readFileSync(path.join(__dirname, '..', 'ChatWidget.js'), 'utf8');

test('le filtre des onglets réserve « Bot visiteurs » à la seule adresse du super-admin', () => {
  const debut = source.indexOf("{ key: 'bot', label: 'Bot visiteurs' }");
  expect(debut).toBeGreaterThan(-1);
  const filtre = source.slice(debut, source.indexOf('var v263Current', debut));
  expect(filtre).toMatch(/tab\.key === 'bot' && String\(getCoachEmail\(\) \|\| ''\)\.toLowerCase\(\) !== 'contact\.artboost@gmail\.com'\) return false/);
});

test('les autres onglets restent proposés', () => {
  const debut = source.indexOf('var v263Tabs = [');
  const liste = source.slice(debut, source.indexOf('].filter', debut));
  ['conversations', 'reservations', 'scanner', 'bot'].forEach((cle) => {
    expect(liste).toContain(`key: '${cle}'`);
  });
});
