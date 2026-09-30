/**
 * V548 — LOT 1 COCKPIT MEMBRE : l'espace abonné est allégé.
 *
 * Lecture du SOURCE (comme RechargePulse.test.js) : ce banc fige l'ORDRE et
 * les retraits décidés par le propriétaire, sans monter l'écran entier.
 *   - « Inviter un ami » vit juste SOUS « Réserver une séance » ;
 *   - la recharge SORT du formulaire de réservation, repliée sous
 *     « Recharger mes séances », puis vient le Guide rapide ;
 *   - « Partager mon expérience » n'est plus rendu dans l'espace ;
 *   - « Mon cockpit » s'appelle « Ma progression ».
 */
const fs = require('fs');
const path = require('path');

const SRC = fs.readFileSync(path.join(__dirname, '..', 'SubscriberSpace.js'), 'utf8');
const COCKPIT = fs.readFileSync(path.join(__dirname, '..', 'SubscriberCockpit.js'), 'utf8');

const pos = (s) => SRC.indexOf(s);

describe('V548 — ordre et allègement de l espace membre', () => {
  // V561 — DASHBOARD COURT : une fonction = un seul point d'entrée (le menu rapide).
  test('dashboard : en-tête < menu rapide < Ma progression < prochaines séances', () => {
    const suite = [
      'data-testid="subscriber-space-header"',
      '<MenuRapide entrees={[',
      'data-testid="subscriber-space-sessions"',
      'data-testid="subscriber-space-upcoming"',
    ].map(pos);
    suite.forEach((p) => expect(p).toBeGreaterThan(0));
    for (let i = 1; i < suite.length; i += 1) expect(suite[i]).toBeGreaterThan(suite[i - 1]);
  });

  test('plus de gros QR, de bloc Parrainage, de bloc Créateur visible, ni de guide rapide', () => {
    expect(SRC).not.toContain('data-testid="subscriber-space-qr"');
    expect(SRC).not.toContain('<CarteParrainage ');
    expect(SRC).not.toContain('data-testid="subscriber-space-guide"');
    expect(SRC).toMatch(/<CarteCreateur[^>]*sansCarte/);        // la fenêtre seule, ouverte par le menu
    expect(SRC).not.toContain('p2ux-parrainage-ouvrir');        // « Inviter un ami » = menu « Inviter »
  });

  test('Réserver et Recharger vivent dans des FENÊTRES, hors du dashboard', () => {
    const resa = pos('data-testid="subscriber-space-reservation"');
    const recharge = pos('data-testid="subscriber-space-recharge"');
    const fenResa = pos('titre="Réserver une séance"');
    const fenRecharge = pos('titre="Recharger mes séances"');
    expect(fenResa).toBeGreaterThan(0);
    expect(resa).toBeGreaterThan(fenResa);
    expect(recharge).toBeGreaterThan(fenRecharge);
    expect(pos('data-testid="renew-subscription-btn"')).toBeGreaterThan(fenRecharge);
    expect(SRC).toContain('{reservationOuverte ? (');
    expect(SRC).toContain('{rechargeModale && rechargeDisponible ? (');
    // Un lien d'invitation (séance présélectionnée) ouvre la réservation d'office.
    expect(SRC).toContain('useState(() => !!inv2Seance)');
  });

  test('la recharge garde tout son contenu serveur (offres, CTA, motif, Stripe)', () => {
    const recharge = SRC.slice(pos('data-testid="subscriber-space-recharge"'), pos('data-testid="renew-subscription-btn"'));
    expect(recharge.indexOf('{rechargeVisible && (')).toBeLessThan(recharge.indexOf('recharge-offres'));
    ['recharge-offres', 'recharge-cta', 'recharge-motif', 'handleRecharge', 'ChoixModePaiement']
      .forEach((m) => expect(recharge).toContain(m));
    expect(recharge).not.toContain('data-testid="recharge-toggle"'); // plus d'accordéon en double
  });

  test('Ma progression = UNE carte : titre, compteur, barre, « Réserver », détail intégré', () => {
    const carte = SRC.slice(pos('data-testid="subscriber-space-sessions"'), pos('data-testid="subscriber-space-upcoming"'));
    expect(carte).toContain('data-testid="progression-titre"');
    expect(carte).toContain('data-testid="progression-reserver"');
    expect(carte).toContain('<SubscriberCockpit accessCode={accessCode} integre />');
    expect(SRC.split('<SubscriberCockpit ').length - 1).toBe(1);
  });

  test('« Partager mon expérience » n est plus rendu dans l espace', () => {
    expect(SRC).not.toMatch(/<InvitationTemoignage/);
    expect(SRC).not.toMatch(/import InvitationTemoignage/);
  });

  test('la réconciliation des notifications reste MONTÉE', () => {
    expect(SRC).toMatch(/<CarteNotifications[\s\S]{0,200}role="subscriber"/);
  });

  test('« Mon cockpit » devient « Ma progression »', () => {
    expect(COCKPIT).toContain('>Ma progression</span>');
    expect(COCKPIT).not.toContain('>Mon cockpit</span>');
  });
});
