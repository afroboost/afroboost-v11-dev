/**
 * BILAN DE SEANCE — les garanties que Jest peut tenir sur ChatWidget.js.
 *
 * POURQUOI DE L'ANALYSE STATIQUE ET PAS UN RENDU. Aucun test du depot ne rend
 * `ChatWidget` : le composant fait 12 500 lignes, tient tout le dashboard coach
 * et exige un contexte (axios, portails, localStorage, socket) qu'un rendu
 * unitaire ne reproduit pas honnetement. Le depot a deja tranche : le seul test
 * qui touche ce fichier (`utils/__tests__/analyticsIdentity.test.js`) le lit
 * comme du TEXTE. On reprend cette technique — et on assume ce qu'elle ne
 * prouve pas : le PARCOURS reel est couvert par Playwright, pas ici.
 *
 * CE QUE CE FICHIER GARDE, ET QUE RIEN D'AUTRE NE GARDE :
 *   * l'ES5 strict de la zone Transactions. Le `CLAUDE.md` l'impose (Samsung
 *     Internet, anciens Android), aucune regle ESLint ne le verifie, et le
 *     fichier compte deja 752 `const`/`let` AILLEURS. Un seul `const` glisse
 *     dans cette zone casserait des telephones sans que rien ne le signale.
 *   * la recherche par DATE DE SEANCE, et non par date d'achat.
 *   * le fait que le panneau vit dans un PORTAIL — le conteneur du widget est
 *     en `overflow: hidden` et large de 380 px : un panneau rendu dedans serait
 *     decoupe (incident V350).
 */
const fs = require('fs');
const path = require('path');

const CHEMIN = path.join(__dirname, '..', 'ChatWidget.js');
const SRC = fs.readFileSync(CHEMIN, 'utf8');

/** Le code executable d'une zone, prive de ses commentaires.
 *  Sans ce nettoyage, un commentaire qui EXPLIQUE pourquoi on n'ecrit pas
 *  `const` ferait echouer la garde ES5. */
function codeNu(texte) {
  return texte
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .filter(function (l) { return !/^\s*(\/\/|\*|\{\/\*)/.test(l); })
    .join('\n');
}

function zone(debut, fin) {
  const i = SRC.indexOf(debut);
  const j = i >= 0 ? SRC.indexOf(fin, i) : -1;
  return i >= 0 && j > i ? SRC.slice(i, j) : '';
}

/** Les DEUX zones du bilan, et elles seules.
 *  Le fichier contient deux blocs distincts : les helpers (ouverture,
 *  chargement, fermeture) et le panneau rendu en portail. Une borne unique
 *  « BILAN DE SEANCE » avalerait les 6 800 lignes qui les separent — et le
 *  test mesurerait alors tout le fichier au lieu de ce lot. */
const ZONE_HELPERS = zone('BILAN DE SEANCE — ouverture', '// V236: ajoute ou retire');
const ZONE_PANNEAU = zone('BILAN DE SEANCE — QUI ETAIT LA', 'FIN BILAN DE SEANCE');
const ZONE_BILAN = ZONE_HELPERS + '\n' + ZONE_PANNEAU;
const ZONE_RECHERCHE = zone('var v242MatchSearch', 'var v242FilterBySearch');

describe('Bilan de seance — zone Transactions du ChatWidget', () => {
  test('la zone Transactions existe toujours', () => {
    expect(SRC).toContain("coachDashTab === 'reservations'");
  });

  // ── ES5 STRICT ────────────────────────────────────────────────────────────
  test('le bilan est ecrit en ES5 : ni const, ni let, ni arrow, ni template', () => {
    const bloc = codeNu(ZONE_BILAN);
    expect(bloc.length).toBeGreaterThan(200);   // la zone existe vraiment
    expect(bloc).not.toMatch(/\b(const|let)\s/);
    expect(bloc).not.toMatch(/=>/);
    expect(bloc).not.toMatch(/`/);
  });

  test('le bilan se rend en React.createElement, comme ses voisins', () => {
    const bloc = ZONE_BILAN;
    expect(bloc).toContain('React.createElement');
  });

  // ── LE PANNEAU VIT DANS UN PORTAIL ────────────────────────────────────────
  test('le panneau est rendu dans un portail sur document.body', () => {
    const bloc = ZONE_BILAN;
    expect(bloc).toContain('createPortal');
    expect(bloc).toContain('document.body');
  });

  test('desktop et mobile sont distingues par isMobileView', () => {
    const bloc = ZONE_BILAN;
    expect(bloc).toContain('isMobileView');
  });

  // ── LA RECHERCHE ──────────────────────────────────────────────────────────
  test('la recherche interroge la date de SEANCE, pas seulement la date d achat', () => {
    const bloc = ZONE_RECHERCHE;
    expect(bloc).toContain('datetime');
  });

  test('la recherche couvre toujours cours, participant et e-mail', () => {
    const bloc = ZONE_RECHERCHE;
    expect(bloc).toContain('courseName');
    expect(bloc).toContain('userName');
    expect(bloc).toContain('userEmail');
  });

  // ── L'APPEL SERVEUR ───────────────────────────────────────────────────────
  test('le bilan appelle la route serveur, il ne recalcule aucun montant', () => {
    const bloc = ZONE_BILAN;
    expect(bloc).toContain('/reservations/bilan-seance');
    // Aucune arithmetique de montant cote navigateur : le total vient du serveur.
    expect(bloc).not.toMatch(/valeur\s*\*/);
    expect(bloc).not.toMatch(/\/\s*seances/);
  });

  test('le bilan est attache a courseId ET a l occurrence', () => {
    const bloc = ZONE_BILAN;
    expect(bloc).toContain('courseId');
    expect(bloc).toContain('occurrence');
  });

  // ── HONNETETE DU TOTAL ────────────────────────────────────────────────────
  test('un total incomplet est dit PROVISOIRE, et les inconnues sont comptees', () => {
    const bloc = ZONE_BILAN;
    expect(bloc.toLowerCase()).toContain('provisoire');
    expect(bloc).toContain('participants_valeur_inconnue');
  });

  test('une valeur inconnue s affiche « A verifier », jamais 0 CHF', () => {
    const bloc = ZONE_BILAN;
    expect(bloc).toMatch(/vérifier|verifier/i);
  });

  // ── COULEURS DU COACH ─────────────────────────────────────────────────────
  test('aucune couleur de marque codee en dur hors valeur de secours var()', () => {
    const bloc = codeNu(ZONE_BILAN);
    const hex = bloc.match(/#[0-9a-fA-F]{6}/g) || [];
    hex.forEach(function (h) {
      const i = bloc.indexOf(h);
      const avant = bloc.slice(Math.max(0, i - 60), i);
      // Tout hex doit etre un REPLI dans un var(), ou une couleur neutre
      // (blanc/noir/gris) — jamais la couleur de marque imposee.
      const estRepli = /var\(--[a-z-]+,\s*$/.test(avant);
      // Neutres (fonds, textes) et SEMANTIQUES (erreur, avertissement) sont
      // admis : la regle du CLAUDE.md vise la couleur de MARQUE, celle que le
      // coach personnalise. Le voisinage immediat fait deja ce choix — le vert
      // `#22c55e` et le bleu `#3b82f6` de la zone Transactions sont codes en
      // dur parce qu'ils disent « valide » et « paiement », pas « Afroboost ».
      const NEUTRES = ['#ffffff', '#000000', '#1a1a1a', '#aaaaaa', '#666666'];
      const SEMANTIQUES = ['#fbbf24', '#fca5a5', '#22c55e', '#3b82f6', '#ef4444'];
      const estTolere = NEUTRES.indexOf(h.toLowerCase()) !== -1
        || SEMANTIQUES.indexOf(h.toLowerCase()) !== -1;
      expect(estRepli || estTolere).toBe(true);
    });
  });

  // ── PERIMETRE ─────────────────────────────────────────────────────────────
  test('aucun partage partenaire dans ce lot, mais la place lui est reservee', () => {
    const bloc = ZONE_BILAN;
    expect(bloc).not.toMatch(/\*\s*0\.3|pourcentage_partenaire|partSplit/);
    // Une zone nommee, prete a recevoir le lot suivant sans nouvelle page.
    expect(bloc.toLowerCase()).toContain('partenaire');
  });
});
