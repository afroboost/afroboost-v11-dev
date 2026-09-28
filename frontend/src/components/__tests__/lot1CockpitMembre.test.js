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
  test('séances < QR < réservation < parrainage < recharge < guide', () => {
    const suite = [
      'data-testid="subscriber-space-sessions"',
      'data-testid="subscriber-space-qr"',
      'data-testid="subscriber-space-reservation"',
      '<CarteParrainage enabled={parrainageOn} />',
      'data-testid="subscriber-space-recharge"',
      'data-testid="subscriber-space-guide"',
    ].map(pos);
    suite.forEach((p) => expect(p).toBeGreaterThan(0));
    for (let i = 1; i < suite.length; i += 1) expect(suite[i]).toBeGreaterThan(suite[i - 1]);
  });

  test('la carte parrainage n est rendue qu une fois', () => {
    expect(SRC.split('<CarteParrainage ').length - 1).toBe(1);
  });

  test('la recharge n est plus DANS la section de réservation', () => {
    const debut = pos('data-testid="subscriber-space-reservation"');
    const fin = SRC.indexOf('</section>', pos('{/* Séance sélectionnée */}'));
    const reservation = SRC.slice(debut, SRC.indexOf('<CarteParrainage', fin));
    expect(reservation).not.toContain('recharge-offres');
    expect(reservation).not.toContain('handleRecharge');
  });

  test('la recharge est repliable, et son contenu passe par le verrou', () => {
    const recharge = SRC.slice(pos('data-testid="subscriber-space-recharge"'), pos('Guide rapide ====='));
    expect(recharge).toContain('data-testid="recharge-toggle"');
    expect(recharge).toContain('Recharger mes séances');
    expect(recharge).toContain('aria-expanded={rechargeVisible}');
    expect(recharge.indexOf('{rechargeVisible && (')).toBeLessThan(recharge.indexOf('recharge-offres'));
    // Le contenu serveur (offres, CTA, motif, Stripe) est toujours là.
    ['recharge-offres', 'recharge-cta', 'recharge-motif', 'handleRecharge', 'ChoixModePaiement']
      .forEach((m) => expect(recharge).toContain(m));
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
