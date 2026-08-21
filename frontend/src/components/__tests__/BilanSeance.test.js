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
      // `#111111` est l ENCRE de la signature sur un fond blanc — la teindre
      // de la couleur du coach la rendrait moins lisible et ne dirait rien de
      // la marque. Neutre au meme titre que le noir.
      const NEUTRES = ['#ffffff', '#000000', '#111111', '#1a1a1a', '#aaaaaa', '#666666'];
      const SEMANTIQUES = ['#fbbf24', '#fca5a5', '#22c55e', '#3b82f6', '#ef4444'];
      const estTolere = NEUTRES.indexOf(h.toLowerCase()) !== -1
        || SEMANTIQUES.indexOf(h.toLowerCase()) !== -1;
      expect(estRepli || estTolere).toBe(true);
    });
  });

  // ── PERIMETRE ─────────────────────────────────────────────────────────────
  // ── PARTAGE PARTENAIRE ────────────────────────────────────────────────────
  test('le partage vit DANS le Bilan — aucune nouvelle page', () => {
    const bloc = ZONE_BILAN;
    expect(bloc.toLowerCase()).toContain('partage partenaire');
    expect(bloc).toContain('partage-ajouter');
    expect(bloc).toContain('partage-nom');
    expect(bloc).toContain('partage-pct');
  });

  test('le navigateur ne calcule AUCUN montant : il envoie nom + %, le serveur repond', () => {
    const bloc = ZONE_BILAN;
    expect(bloc).toContain('/reservations/bilan-seance/partage');
    // Aucune arithmetique de repartition cote client.
    expect(bloc).not.toMatch(/\*\s*0\.3|total\s*\*\s*p|pct\s*\/\s*100/);
    // Les montants affiches viennent du serveur, pas d'un calcul local.
    expect(bloc).toContain('partage.partner_amount');
    expect(bloc).toContain('partage.afroboost_amount');
  });

  test('le pourcentage est borne 0-100 avant meme l envoi', () => {
    const bloc = ZONE_BILAN;
    expect(bloc).toMatch(/pct\s*<\s*0\s*\|\|\s*pct\s*>\s*100/);
  });

  test('un partage provisoire est annonce comme tel', () => {
    const bloc = ZONE_BILAN;
    expect(bloc).toContain("statut === 'provisoire'");
    expect(bloc.toLowerCase()).toContain('provisoires');
  });

  test('le panneau dit que ce n est PAS un paiement', () => {
    const bloc = ZONE_BILAN;
    expect(bloc).toMatch(/aucun paiement/i);
    // Et il ne declenche effectivement rien de tel.
    expect(bloc).not.toMatch(/stripe|virement|payout|transfer|facture/i);
  });

  // ── SIGNATURE PARTENAIRE ──────────────────────────────────────────────────
  test('la signature vit dans le Bilan, sous le partage — aucune nouvelle page', () => {
    const bloc = ZONE_BILAN;
    expect(bloc).toContain('signature-zone');
    expect(bloc).toContain('signature-cadre');
    expect(bloc).toContain('/reservations/bilan-seance/signature');
  });

  test('on ne fait pas signer un total provisoire', () => {
    const bloc = ZONE_BILAN;
    expect(bloc).toContain('signature-bloquee');
    // Le bouton reste VISIBLE et desactive : le cacher laisserait croire que
    // la signature n existe pas.
    expect(bloc).toMatch(/bilanSeance\.provisoire/);
    expect(bloc).toMatch(/disabled:\s*true/);
  });

  test('cote Afroboost : le coach authentifie, pas un second trait au doigt', () => {
    const bloc = ZONE_BILAN;
    expect(bloc).toContain('afroboost_valide_par');
    // Un seul cadre de signature dans tout le panneau.
    expect((bloc.match(/signature-cadre/g) || []).length).toBe(1);
  });

  test('le montant SIGNE vient du serveur et n est pas recalcule', () => {
    const bloc = ZONE_BILAN;
    expect(bloc).toContain('partage.signature.partner_amount');
    expect(bloc).not.toMatch(/signature[\s\S]{0,80}\*\s*bilanSeance/);
  });

  test('une signature perimee est signalee, jamais reecrite ni cachee', () => {
    const bloc = ZONE_BILAN;
    expect(bloc).toContain('signature-perimee');
    expect(bloc).toContain('signature.perimee');
  });

  test('signer n est pas payer, et le panneau le dit', () => {
    const bloc = ZONE_BILAN;
    expect(bloc).toMatch(/Signature de reconnaissance[\s\S]{0,60}aucun paiement/i);
  });

  test('le cadre est utilisable au doigt : le geste trace au lieu de defiler', () => {
    const bloc = ZONE_BILAN;
    expect(bloc).toContain('onPointerDown');
    expect(bloc).toContain("touchAction: 'none'");
  });

  test('un cadre vide est refuse par le navigateur, seul temoin du geste', () => {
    const bloc = ZONE_BILAN;
    expect(bloc).toContain('sgTrace');
  });

  test('le recapitulatif porte le cours, la date et les DEUX parts', () => {
    const bloc = ZONE_BILAN;
    expect(bloc).toContain('signature-recap');
    ['Cours', 'Date', 'Total séance', 'Partenaire',
     'Part partenaire', 'Montant partenaire', 'Part Afroboost']
      .forEach((l) => expect(bloc).toContain(`ligneRecap('${l}'`));
  });

  // ── SIGNE N EST PAS PAYE ──────────────────────────────────────────────────
  test('le paiement est une ligne A PART, affichee meme quand rien n est renseigne', () => {
    const bloc = ZONE_BILAN;
    expect(bloc).toContain('paiement-statut');
    expect(bloc).toContain('Non renseigné');
  });

  test('le navigateur DECLARE le paiement, il ne l encaisse pas', () => {
    const bloc = ZONE_BILAN;
    expect(bloc).toContain('/reservations/bilan-seance/paiement');
    expect(bloc).not.toMatch(/stripe|virement|payout|transfer|facture/i);
  });

  test('le partage est rattache au cours ET a l occurrence', () => {
    const bloc = ZONE_BILAN;
    expect(bloc).toMatch(/courseId:\s*bilanSeance\.course_id/);
    expect(bloc).toMatch(/occurrence:\s*bilanSeance\.occurrence/);
  });
});
