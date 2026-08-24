/**
 * LOT R — LA RECHARGE DANS L'ESPACE ABONNE.
 *
 * POURQUOI DE L'ANALYSE STATIQUE ET PAS UN RENDU. `SubscriberSpace` charge son
 * etat depuis le reseau, vit derriere un routeur et lit un code d'acces dans
 * l'URL : un rendu unitaire ne reproduirait pas honnetement ce contexte. Le
 * PARCOURS reel est couvert par Playwright (`tests/test_lotr_navigateur.mjs`,
 * backend reel + Chromium mobile). Ce fichier garde ce que Playwright ne peut
 * pas garder : que l'ecran ne se remette JAMAIS a decider tout seul.
 *
 * CE QU'IL PROTEGE, ET QUE RIEN D'AUTRE NE PROTEGE :
 *   * l'ecran n'a AUCUNE regle metier. Le jour ou quelqu'un ecrira
 *     `remaining === 0 && estMembre` ici, deux verites cohabiteront — et c'est
 *     celle du navigateur que le client verra.
 *   * aucun montant, aucun nombre de seances en dur : ils viennent du serveur.
 *   * le refus est EXPLIQUE : un bouton absent sans raison est un bug pour
 *     celui qui le cherche.
 */
const fs = require('fs');
const path = require('path');

const CHEMIN = path.join(__dirname, '..', 'SubscriberSpace.js');
const SRC = fs.readFileSync(CHEMIN, 'utf8');

/** Le code executable, prive de ses commentaires. Sans ce nettoyage, un
 *  commentaire qui EXPLIQUE pourquoi l'ecran ne calcule rien ferait echouer
 *  les gardes ci-dessous. */
function codeNu(texte) {
  return texte
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .filter((l) => !/^\s*(\/\/|\*|\{\/\*)/.test(l))
    .join('\n');
}

/** La zone de la recharge : le CTA et son alternative, rien d'autre. */
const ZONE_CTA = (() => {
  let i = SRC.indexOf('LOT R — LA RECHARGE DU PACK');
  // On REMONTE jusqu a l ouverture du commentaire JSX. Sans cela, la zone
  // commence APRES le `{/*` : le depouillement ne peut plus reconnaitre le
  // commentaire, et son texte serait mesure comme du code.
  if (i > 0) {
    const ouverture = SRC.lastIndexOf('{/*', i);
    if (ouverture > 0) i = ouverture;
  }
  const j = i >= 0 ? SRC.indexOf('Guide rapide', i) : -1;
  return i >= 0 && j > i ? SRC.slice(i, j) : '';
})();

const ZONE_APPEL = (() => {
  const i = SRC.indexOf('const handleRecharge');
  const j = i >= 0 ? SRC.indexOf('// V202: Scroll fluide', i) : -1;
  return i >= 0 && j > i ? SRC.slice(i, j) : '';
})();

describe('Recharge PULSE — espace abonne', () => {
  test('les deux zones existent vraiment', () => {
    expect(ZONE_CTA.length).toBeGreaterThan(300);
    expect(ZONE_APPEL.length).toBeGreaterThan(200);
  });

  // ── L'ECRAN NE DECIDE RIEN ────────────────────────────────────────────────
  test('le CTA est conditionne au verdict DU SERVEUR', () => {
    expect(ZONE_CTA).toContain('data?.recharge?.eligible');
  });

  test('l ecran ne rejuge PAS l eligibilite lui-meme', () => {
    // ON MESURE LA DECISION D AFFICHER LE CTA, pas tout le bloc. Le REPLI
    // historique (« contacte ton coach », pour un coach qui n a declare aucune
    // offre de recharge) lit legitimement `remaining` : il ne juge aucune
    // eligibilite, il remplace un message. Interdire `remaining` partout
    // reviendrait a interdire ce repli — que le dernier test de ce fichier
    // exige justement de garder.
    const iRepli = ZONE_CTA.indexOf('recharge-motif');
    const decision = codeNu((iRepli > 0 ? ZONE_CTA.slice(0, iRepli) : ZONE_CTA)
                            + '\n' + ZONE_APPEL);
    expect(decision.length).toBeGreaterThan(200);
    // Le CTA ne depend QUE du verdict serveur.
    expect(decision).toContain('data?.recharge?.eligible');
    // Aucune regle metier recopiee : ni comptage de seances, ni jugement
    // d adhesion, ni lecture de dates. Deux verites divergeraient un jour.
    expect(decision).not.toMatch(/remaining/);
    expect(decision).not.toMatch(/membership|adhesion|adhésion/i);
    expect(decision).not.toMatch(/date_fin|date_debut/);
  });

  test('aucun montant ni nombre de seances code en dur', () => {
    const bloc = codeNu(ZONE_CTA + '\n' + ZONE_APPEL);
    expect(bloc).not.toMatch(/\b150\b/);
    expect(bloc).not.toMatch(/\b250\b/);
    // Le libelle vient du serveur, y compris le nombre de seances.
    expect(bloc).toContain('data.recharge.seances');
    expect(bloc).toContain('data.recharge.prix');
  });

  // ── LE REFUS EST EXPLIQUE ─────────────────────────────────────────────────
  test('quand le CTA n apparait pas, la raison s affiche', () => {
    expect(ZONE_CTA).toContain('recharge-motif');
    expect(ZONE_CTA).toContain('data.recharge.message');
  });

  test('le message affiche est celui du serveur, pas une phrase locale', () => {
    const bloc = codeNu(ZONE_CTA);
    // Aucune des trois phrases de refus n est ecrite ici.
    expect(bloc).not.toMatch(/réservée aux membres|Termine-les|échéance/i);
  });

  // ── L'APPEL ───────────────────────────────────────────────────────────────
  test('la recharge passe par la caisse, avec l offre que le serveur a donnee', () => {
    expect(ZONE_APPEL).toContain('/create-checkout-session');
    expect(ZONE_APPEL).toMatch(/offerId:\s*r\.offer_id/);
  });

  test('un double clic ne lance pas deux paiements', () => {
    expect(ZONE_APPEL).toContain('rechargeLoading');
    expect(ZONE_APPEL).toMatch(/if\s*\(rechargeLoading/);
    expect(ZONE_CTA).toMatch(/disabled=\{rechargeLoading\}/);
  });

  test('un refus serveur est montre au client, jamais avale', () => {
    expect(ZONE_APPEL).toContain('setActionError');
    expect(ZONE_APPEL).toContain('response?.data?.detail');
  });

  // ── REGLES DU DEPOT ───────────────────────────────────────────────────────
  test('l icone est un SVG inline, jamais un emoji', () => {
    expect(ZONE_CTA).toContain('<svg');
    // Aucun emoji dans la zone (la regle du CLAUDE.md vise les icones).
    expect(ZONE_CTA).not.toMatch(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u);
  });

  test('les couleurs du coach sont respectees : aucune couleur de marque en dur', () => {
    const bloc = codeNu(ZONE_CTA);
    const hex = bloc.match(/#[0-9a-fA-F]{6}/g) || [];
    hex.forEach((h) => {
      // Seuls le blanc et le noir sont admis (texte du bouton) ; la couleur de
      // marque doit passer par COLORS.primary / la variable CSS.
      expect(['#ffffff', '#000000']).toContain(h.toLowerCase());
    });
    expect(bloc).toContain('COLORS.primary');
  });

  test('le CTA ne declenche aucun paiement direct ni aucune ecriture locale', () => {
    expect(ZONE_APPEL).not.toMatch(/stripe\.|PaymentIntent|localStorage\.setItem/);
  });

  test('le message historique reste pour un forfait sans offre de recharge', () => {
    // Un coach qui n a declare aucune offre de recharge ne doit pas perdre
    // l information « contacte ton coach » : c est le repli.
    expect(ZONE_CTA).toMatch(/Contacte ton coach/);
  });
});
