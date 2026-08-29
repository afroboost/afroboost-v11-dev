/**
 * P1.2 — LE PARCOURS PARTENAIRE, COURT ET SUR.
 *
 * TROIS DEFAUTS FERMES ICI :
 *
 * 1. LE DOUBLE ENVOI. Le 29/08, deux leads identiques sont nes a 882 ms
 *    d'intervalle. Le bouton porte pourtant `disabled={loading}` : la garde
 *    d'interface ne suffit pas — une requete qui aboutit puis un second clic,
 *    ou la touche Entree, passent au travers. La seule protection qui tienne
 *    est un `submission_id` stable, deduplique COTE SERVEUR.
 *
 * 2. « ERREUR SERVEUR » QUAND LE SERVEUR N'Y EST POUR RIEN. Le message
 *    generique s'affichait aussi quand la reponse n'etait pas du JSON — donc
 *    quand un proxy avait repondu a la place de l'application. Prouve le
 *    29/08 : la requete n'a jamais atteint FastAPI (0 trace, 0 lead).
 *
 * 3. LE PROSPECT PARTENAIRE RENVOYE VERS L'ABONNE quand l'enregistrement
 *    echoue (`acquisition_saved: false`) — la limite laissee ouverte par P1.1.
 */
import {
  p11FinSansFormulaireAbonne,
  p12EstPartenaire,
  p12NouveauSubmissionId,
  p12SubmissionIdValide,
  P12_MESSAGE_RESEAU,
} from '../finTunnelPartenaire';

const OK = { acquisition_saved: true, proof_required: true };
const PARTNER = { lead_type: 'partner' };

describe('7-8. submission_id', () => {
  test('c est un UUID', () => {
    const id = p12NouveauSubmissionId();
    expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
  });
  test('deux appels donnent deux identifiants differents', () => {
    expect(p12NouveauSubmissionId()).not.toBe(p12NouveauSubmissionId());
  });
  test('la validation accepte un UUID et refuse le reste', () => {
    expect(p12SubmissionIdValide(p12NouveauSubmissionId())).toBe(true);
    expect(p12SubmissionIdValide('pas-un-uuid')).toBe(false);
    expect(p12SubmissionIdValide('')).toBe(false);
    expect(p12SubmissionIdValide(null)).toBe(false);
    expect(p12SubmissionIdValide('x'.repeat(200))).toBe(false);
    expect(p12SubmissionIdValide({})).toBe(false);
  });
  test('aucune donnee personnelle ne peut s y glisser', () => {
    expect(p12SubmissionIdValide('moi@exemple.invalid')).toBe(false);
    expect(p12SubmissionIdValide('+41791234567')).toBe(false);
  });
});

describe('17. partenaire : jamais le formulaire abonne', () => {
  test('un lien partenaire est reconnu', () => {
    expect(p12EstPartenaire(PARTNER)).toBe(true);
    expect(p12EstPartenaire({ lead_type: ' Partner ' })).toBe(true);
  });
  test('les autres types ne le sont pas', () => {
    expect(p12EstPartenaire({ lead_type: 'participant' })).toBe(false);
    expect(p12EstPartenaire({})).toBe(false);
    expect(p12EstPartenaire(null)).toBe(false);
    expect(p12EstPartenaire([])).toBe(false);
    expect(p12EstPartenaire('partner')).toBe(false);
  });
  test('acquisition_saved=false + partner : pas de confirmation, mais partenaire reconnu', () => {
    expect(p11FinSansFormulaireAbonne({ acquisition_saved: false }, '807fe7', PARTNER)).toBe(false);
    expect(p12EstPartenaire(PARTNER)).toBe(true);   // ChatWidget doit l'aiguiller ailleurs
  });
});

describe('9. message reseau', () => {
  test('le texte est celui demande, sans « Erreur serveur »', () => {
    expect(P12_MESSAGE_RESEAU).toContain('La connexion a été interrompue');
    expect(P12_MESSAGE_RESEAU).toContain('Vos réponses sont conservées');
    expect(P12_MESSAGE_RESEAU).toContain('Réessayez dans quelques secondes');
    expect(P12_MESSAGE_RESEAU).not.toContain('Erreur serveur');
  });
});

describe('OnboardingTunnel — cablage (lecture de la source)', () => {
  const fs = require('fs');
  const path = require('path');
  const SRC = fs.readFileSync(
    path.join(__dirname, '..', '..', 'components', 'chat', 'OnboardingTunnel.js'), 'utf8');

  test('4-5. l image partenaire pointe sur /hero-afroboost.jpg', () => {
    expect(SRC).toContain('/hero-afroboost.jpg');
  });
  test('4. elle n est affichee QUE pour lead_type partner', () => {
    const i = SRC.indexOf('/hero-afroboost.jpg');
    const bloc = SRC.slice(Math.max(0, i - 700), i + 400);
    expect(bloc).toMatch(/p12EstPartenaire|lead_type/);
  });
  test('4. elle porte un alt descriptif et object-fit cover', () => {
    const i = SRC.indexOf('/hero-afroboost.jpg');
    const bloc = SRC.slice(Math.max(0, i - 400), i + 1400);
    expect(bloc).toMatch(/alt="[^"]{25,}"/);
    expect(bloc).toContain('cover');
  });

  test('4bis. le cadrage ne decapite pas le sujet', () => {
    // La photo est CARREE : une banniere n'en montre que ~38 % de la hauteur.
    // A `50% 30%` (premiere version, constatee en production) la fenetre
    // commencait sous le haut du crane. Mesure en decoupant la photo : `10 %`
    // garde chevelure, casque et visage entiers.
    const i = SRC.indexOf('/hero-afroboost.jpg');
    const bloc = SRC.slice(i, i + 1400);
    expect(bloc).toMatch(/objectPosition: '50% 10%'/);
    expect(bloc).not.toMatch(/objectPosition: '50% 30%'/);
    expect(bloc).toMatch(/height: '1[45]0px'/);
  });
  test('3. le tunnel essai ne recoit aucune image', () => {
    // Le logo rond historique reste, la banniere est conditionnelle.
    expect(SRC).toContain('/logo192.png');
  });
  test('6. garde anti-double-clic en tete de handleNext', () => {
    // Fenetre elargie : la garde est precedee de son commentaire d'explication.
    const i = SRC.indexOf('const handleNext');
    const tete = SRC.slice(i, i + 600);
    expect(tete).toMatch(/if \(loading\) return/);
    // Elle doit venir AVANT la lecture de la valeur, sinon elle ne garde rien.
    expect(tete.indexOf('if (loading) return')).toBeLessThan(tete.indexOf('getCurrentValue()'));
  });
  test('5. submission_id genere UNE fois au montage', () => {
    expect(SRC).toMatch(/useState\(\(\) => p12NouveauSubmissionId\(\)\)/);
  });
  test('5. il est envoye dans le corps', () => {
    expect(SRC).toMatch(/submission_id/);
  });
  test('8. il n est jamais regenere dans handleNext', () => {
    const i = SRC.indexOf('const handleNext');
    const bloc = SRC.slice(i, SRC.indexOf('\n  }, [', i));
    expect(bloc).not.toContain('p12NouveauSubmissionId(');
  });
  test('9-10. non-JSON -> message reseau ; detail conserve', () => {
    expect(SRC).toContain('P12_MESSAGE_RESEAU');
    expect(SRC).toMatch(/errData\.detail/);
    expect(SRC).not.toContain("|| 'Erreur serveur'");
  });
});

describe('ChatWidget — cablage (lecture de la source)', () => {
  const fs = require('fs');
  const path = require('path');
  const SRC = fs.readFileSync(
    path.join(__dirname, '..', '..', 'components', 'ChatWidget.js'), 'utf8');

  test('17. un partenaire non confirme n ouvre PAS le formulaire abonne', () => {
    expect(SRC).toContain('p12EstPartenaire');
    // On vise l'USAGE, pas la ligne d'import (qui vient en premier dans le fichier).
    const i = SRC.indexOf('p12EstPartenaire(clientData');
    expect(i).toBeGreaterThan(0);
    const bloc = SRC.slice(i, i + 500);
    expect(bloc).toContain('setShowSubscriberForm(false)');
    expect(bloc).not.toContain('birthday');
  });
  test('19-22. aucun booking, checkout, code promo ni date de naissance sur ce chemin', () => {
    const i = SRC.indexOf('p12EstPartenaire(clientData');
    const bloc = SRC.slice(i, i + 500);
    ['booking', 'checkout', 'offre=', 'reserver=1', 'birthday'].forEach((m) => {
      expect(bloc).not.toContain(m);
    });
  });
});
