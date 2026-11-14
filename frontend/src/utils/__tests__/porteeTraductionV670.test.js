// V670 — Filet de sécurité de la traduction, par ARBRE SYNTAXIQUE.
//
// Convertir des centaines de textes en `t('clé')` peut casser trois choses sans qu'aucun
// test visuel ne le voie avant la production :
//   1. `t` n'est pas la fonction de traduction dans cette portée (ex. `const t = setInterval(…)`
//      masque la vraie) → « t is not a function » au rendu ;
//   2. la clé n'existe pas → l'utilisateur lit « v_fermr » au lieu de « Fermer » ;
//   3. une `{variable}` du texte n'est pas fournie → « Frais de port : CHF {montant} ».
// Ces trois erreurs sont détectées ici, pour TOUS les appels, pas pour un échantillon.
import fs from 'fs';
import path from 'path';
import { parse } from '@babel/parser';
import traverse from '@babel/traverse';
import { translations } from '../i18n';

const SRC = path.join(__dirname, '..', '..');
const FICHIERS = [
  'App.js',
  'components/PartnersCarousel.js',
  'components/accueil/ColonneAccueil.js',
  'components/accueil/DecouvrirAfroboost.js',
  'components/HeroTexte.js',
  'components/SessionsModal.js',
  'components/OffresAimants.js',
  'components/SubscriberSpace.js',
  'components/Publications.js',
  'components/CoachVitrine.js',
  'components/BecomeCoachPage.js',
];

// Le dictionnaire local d'App.js (fusionné dans `translations` au chargement d'App) :
// on le lit dans l'arbre plutôt que d'importer une App de 11 000 lignes dans un test.
function clesLocalesApp() {
  const code = fs.readFileSync(path.join(SRC, 'App.js'), 'utf8');
  const ast = parse(code, { sourceType: 'module', plugins: ['jsx'], errorRecovery: true });
  const fr = {};
  traverse(ast, {
    VariableDeclarator(p) {
      if (p.node.id.name !== '_traductionsApp') return;
      p.node.init.properties.forEach((langue) => {
        const nom = langue.key.name || langue.key.value;
        (langue.value.properties || []).forEach((kv) => {
          const k = kv.key.name || kv.key.value;
          if (nom === 'fr' && kv.value.type === 'StringLiteral') fr[k] = kv.value.value;
        });
      });
    },
  });
  return fr;
}
const FR_APP = clesLocalesApp();
// Dictionnaire français tel que l'App le voit : local d'abord, puis le dictionnaire unique.
const FR = { ...translations.fr, ...FR_APP };

function analyser(fichier) {
  const code = fs.readFileSync(path.join(SRC, fichier), 'utf8');
  const ast = parse(code, { sourceType: 'module', plugins: ['jsx'], errorRecovery: true });
  const appels = [];
  traverse(ast, {
    CallExpression(p) {
      const c = p.node.callee;
      if (c.type !== 'Identifier' || c.name !== 't') return;
      appels.push({ p, ligne: p.node.loc.start.line });
    },
  });
  return appels;
}

function tLegitime(p) {
  const b = p.scope.getBinding('t');
  if (!b) return 'aucun `t` dans la portée';
  const n = b.path.node;
  if (b.path.isVariableDeclarator()) {
    const init = n.init;
    const c = init && init.type === 'CallExpression'
      ? (init.callee.name || (init.callee.property && init.callee.property.name)) : null;
    return ['useCallback', 'useLanguage', 'useTranslation'].includes(c) ? null : `t local non reconnu (${init && init.type})`;
  }
  if (b.kind === 'param') return null;                                   // ({ t }) ou (t)
  if (b.path.isImportSpecifier()) return null;                           // import { t } from utils/i18n
  return `t de nature « ${b.kind} »`;
}

// Clés lues depuis un 1er argument : littéral, ou ternaire de littéraux.
function cles(arg) {
  if (!arg) return [];
  if (arg.type === 'StringLiteral') return [arg.value];
  if (arg.type === 'ConditionalExpression') return [...cles(arg.consequent), ...cles(arg.alternate)];
  return [];
}

describe.each(FICHIERS)('%s — appels à t(…)', (fichier) => {
  const appels = analyser(fichier);

  it('⚠️ un `t` appelé AVEC des variables sait les interpoler (sinon « {n} places » s\'affiche tel quel)', () => {
    // Régression réelle, trouvée dans un navigateur : le `t` d'App.js n'avait qu'UN paramètre,
    // donc `t('vm_places', { n: 12 })` rendait « {n} places ». Aucun test unitaire ne le voyait.
    const fautes = [];
    appels.forEach(({ p, ligne }) => {
      if (!p.node.arguments.some((a) => a.type === 'ObjectExpression')) return;
      const b = p.scope.getBinding('t');
      const init = b && b.path.isVariableDeclarator() ? b.path.node.init : null;
      if (init && init.type === 'CallExpression' && init.callee.name === 'useCallback') {
        const fn = init.arguments[0];
        if (!fn || !fn.params || fn.params.length < 2) fautes.push(`${fichier}:${ligne}`);
      }
    });
    expect(fautes).toEqual([]);
  });

  it('le `t` d\'App.js passe bien par `interpoler`', () => {
    const code = fs.readFileSync(path.join(SRC, fichier), 'utf8');
    if (fichier === 'App.js') expect(code).toMatch(/const t = useCallback\(\(key, vars\) => interpoler\(/);
  });

  it('il y a des appels à vérifier (le test ne passe pas à vide)', () => {
    expect(appels.length).toBeGreaterThan(0);
  });

  it('⚠️ chaque `t` est la fonction de traduction de sa portée', () => {
    const fautes = appels
      .map(({ p, ligne }) => ({ ligne, raison: tLegitime(p) }))
      .filter((x) => x.raison);
    expect(fautes).toEqual([]);
  });

  it('⚠️ chaque clé littérale existe dans le dictionnaire FRANÇAIS', () => {
    const manquantes = [];
    appels.forEach(({ p, ligne }) => {
      cles(p.node.arguments[0]).forEach((k) => {
        if (!FR[k]) manquantes.push(`${fichier}:${ligne} → ${k}`);
      });
    });
    expect(manquantes).toEqual([]);
  });

  it('⚠️ chaque {variable} du texte français est fournie à l\'appel', () => {
    const fautes = [];
    appels.forEach(({ p, ligne }) => {
      const ks = cles(p.node.arguments[0]);
      // Le 2e argument est `vars` dans App.js (t(clé, vars)) ; dans PartnersCarousel
      // et ailleurs, c'est la langue : on ne vérifie que les objets littéraux.
      const objet = p.node.arguments.find((a) => a.type === 'ObjectExpression');
      ks.forEach((k) => {
        const fr = FR[k];
        if (typeof fr !== 'string') return;
        const attendues = [...fr.matchAll(/\{([A-Za-z0-9_]+)\}/g)].map((m) => m[1]);
        if (!attendues.length) return;
        const fournies = new Set(
          (objet ? objet.properties : []).map((pr) => (pr.key && (pr.key.name || pr.key.value))),
        );
        attendues.forEach((v) => { if (!fournies.has(v)) fautes.push(`${fichier}:${ligne} → ${k} attend {${v}}`); });
      });
    });
    expect(fautes).toEqual([]);
  });
});

describe('Le dictionnaire local d\'App.js est bien lu', () => {
  it('il porte les clés historiques (sinon le test ci-dessus ne protège rien)', () => {
    expect(Object.keys(FR_APP).length).toBeGreaterThan(100);
    expect(FR_APP.reservationConfirmed).toBeTruthy();
    expect(FR_APP.paymentDone).toBeTruthy();
  });
});

describe('LanguageMenu', () => {
  it('sa clé de libellé existe en français et dans les langues complètes', () => {
    expect(translations.fr.v_langue).toBe('Langue');
    expect(translations.en.v_langue).toBe('Language');
    expect(translations.de.v_langue).toBe('Sprache');
  });
});
