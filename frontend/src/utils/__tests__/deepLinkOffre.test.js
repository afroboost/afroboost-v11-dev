// P2-FIX2 — LE LIEN PROFOND `?offre=<id>&reserver=1` OUVRE LE FORMULAIRE.
//
// LE DEFAUT, MESURE EN CONTEXTE VISITEUR ANONYME LE 31/08/2026
// ===========================================================================
//     t=800 ms   la carte passe a scale(1.02)  -> elle EST selectionnee
//     t=1200 ms  elle revient a scale(1)       -> la selection est DEFAITE
//
// `&reserver=1` fonctionnait donc, puis se defaisait 400 ms plus tard. Le
// visiteur arrivait devant une carte non ouverte et devait cliquer lui-meme.
//
// LA CHAINE COMPLETE, et elle n'a rien d'evident :
//   1. l'effet du lien profond depend de `[offers]` ;
//   2. `offers` vaut `filteredServices`, un tableau RECREE a chaque rendu ;
//   3. ouvrir le formulaire change l'etat -> nouveau rendu -> nouveau tableau ;
//   4. l'effet se rejoue, la sonde retrouve la carte, rappelle `onSelectOffer` ;
//   5. `handleSelectOffer` voit la MEME offre deja selectionnee et applique la
//      bascule de v56 : « on la deselectionne ».
// Le correctif ferme l'etape 4 : l'effet ne s'execute qu'UNE fois.
//
// POURQUOI UNE `ref` ET UN `state`, ET PAS L'UN OU L'AUTRE
// ===========================================================================
// La `ref` garde l'effet : elle change IMMEDIATEMENT, alors qu'un `state` ne
// serait a jour qu'au rendu suivant — trop tard, exactement le defaut corrige
// en P2-B sur le double clic. Le `state`, lui, RELANCE le defilement
// automatique : une `ref` ne provoque aucun rendu, si bien qu'un lien `?offre=`
// SANS `reserver=1` (qui defile et met en evidence, mais n'ouvre rien) aurait
// laisse le carrousel suspendu pour toujours.
//
// CE FICHIER teste la LOGIQUE, sur le source livre. Le comportement reel a ete
// mesure separement en navigateur anonyme (Playwright, build local, ecritures
// bloquees) : voir le rapport du lot.

import fs from 'fs';
import path from 'path';

const APP = fs.readFileSync(
  path.join(__dirname, '..', '..', 'App.js'), 'utf8');

/** Le CODE seul : commentaires de ligne et de bloc retires. Sans ce nettoyage,
 *  ce fichier se piegerait lui-meme — les commentaires du correctif citent
 *  `setSelectedOffer(null)` et `reserver=1` pour les EXPLIQUER. */
const code = (() => {
  const sans = APP.replace(/\/\*[\s\S]*?\*\//g, '');
  return sans.split('\n').filter((l) => !l.trim().startsWith('//')).join('\n');
})();

describe('P2-FIX2 — le verrou du lien profond', () => {
  test('un verrou en `ref` existe', () => {
    expect(code).toContain('const p2fix2LienProfondTraite = useRef(false);');
  });

  test("l'effet du lien profond sort immediatement s'il a deja tourne", () => {
    expect(code).toContain('if (p2fix2LienProfondTraite.current) return;');
  });

  test('le verrou est pose APRES la decouverte de la carte, jamais avant', () => {
    // Pose avant, il empecherait de repasser tant que les offres ne sont pas
    // montees — et le lien profond ne fonctionnerait plus du tout.
    const i = code.indexOf('const carte = document.querySelector');
    const j = code.indexOf('p2fix2LienProfondTraite.current = true;');
    expect(i).toBeGreaterThan(-1);
    expect(j).toBeGreaterThan(i);
  });

  test('la bascule v56 existe toujours — on ne la supprime pas, on cesse de la declencher', () => {
    expect(code).toContain('setSelectedOffer(null);');
    expect(code).toMatch(/selectedOffer\.id === offer\.id/);
  });

  test('`&reserver=1` appelle toujours onSelectOffer', () => {
    expect(code).toContain("get('reserver') === '1'");
    expect(code).toContain('onSelectOffer(v449Offre)');
  });

  test('la garde « offre inconnue » est conservee', () => {
    expect(code).toContain('if (!offers.some(o => o && o.id === cible)) return;');
  });
});

describe('P2-FIX2 — le defilement automatique', () => {
  test('il se tait pendant le traitement d\'un lien profond', () => {
    expect(code).toContain('if (p2fix2LienProfondEnCours && !p2fix2LienProfondFini) return;');
  });

  test('le drapeau d\'entree est calcule depuis l\'URL, une seule fois', () => {
    expect(code).toContain('const [p2fix2LienProfondEnCours] = useState(() => {');
    expect(code).toMatch(/p2fix2LienProfondEnCours[\s\S]{0,320}get\('offre'\)/);
  });

  test('la reprise passe par un `state`, sinon le carrousel resterait fige', () => {
    expect(code).toContain('setP2fix2LienProfondFini(true);');
    expect(code).toContain('const [p2fix2LienProfondFini, setP2fix2LienProfondFini] = useState(false);');
  });

  test('les deux drapeaux sont dans les dependances de l\'effet', () => {
    expect(code).toMatch(/p2fix2LienProfondEnCours,\s*\n?\s*p2fix2LienProfondFini\]/);
  });

  test('les gardes existantes sont INTACTES — aucune regression visiteur', () => {
    expect(code).toContain(
      'if (!offers || offers.length <= 1 || isPaused || v383Formulaires > 0 || selectedOffer) return;');
  });

  test('la cadence de 3,5 s est inchangee', () => {
    expect(code).toContain('const AUTO_PLAY_INTERVAL = 3500;');
  });

  test('sans lien profond, la garde P2-FIX2 est inerte', () => {
    // `p2fix2LienProfondEnCours` vaut false quand l'URL ne porte pas `offre` :
    // la condition court-circuite et le defilement reprend son cours habituel.
    const ligne = code.split('\n').find((l) => l.includes('p2fix2LienProfondEnCours && !p2fix2LienProfondFini'));
    expect(ligne.trim().startsWith('if (p2fix2LienProfondEnCours')).toBe(true);
  });
});

describe('P2-FIX2 — le perimetre : frontend seul, rien d\'autre touche', () => {
  test('aucune route backend n\'est appelee par le correctif', () => {
    const bloc = code.split('const p2fix2LienProfondTraite')[1].slice(0, 2500);
    expect(bloc).not.toMatch(/axios\.(get|post|put|patch|delete)/);
    expect(bloc).not.toContain('checkout/free');
  });

  test('ESSAI-7 est intact', () => {
    expect(code).toContain('cibleRedirectionEssai(freeRes.data)');
    expect(code).toContain('window.location.href = cibleEssai');
  });

  test('l\'attribution M2 est intacte', () => {
    expect(code).toContain('attributionEnregistrer(window.location.search');
    expect(code).toContain('attributionActuelle()');
  });

  test('le checkout gratuit n\'est pas modifie', () => {
    expect(code).toContain('`${API}/checkout/free`');
  });

  test('aucune selection n\'est declenchee sans `reserver=1`', () => {
    // Le lien `?offre=` seul defile et met en evidence : c'est la regle V371,
    // « un lien ne doit jamais ouvrir un paiement tout seul ». On la garde.
    expect(code).toMatch(/if \(v449Reserver && typeof onSelectOffer === 'function'\)/);
  });
});
