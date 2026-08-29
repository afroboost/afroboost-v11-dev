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
  p12CodeDiagnostic,
  p12PromesseInterdite,
  P12_CODE_FETCH,
  P12_DIAG_PREFIXE,
  P12_INTRO_PARTENAIRE,
  P12_FIN_PARTENAIRE,
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

describe('P1.2-DEDUP2 — le MEME submission_id sur les DEUX appels', () => {
  const fs = require('fs');
  const path = require('path');
  const TUNNEL = fs.readFileSync(
    path.join(__dirname, '..', '..', 'components', 'chat', 'OnboardingTunnel.js'), 'utf8');
  const WIDGET = fs.readFileSync(
    path.join(__dirname, '..', '..', 'components', 'ChatWidget.js'), 'utf8');

  // LE DEFAUT MESURE EN PRODUCTION LE 29/08 A 10:24 :
  //   10:24:53  lead 1  submission_id = a3ead67d…   (POST du tunnel)
  //   10:24:54  lead 2  submission_id = ABSENT      (POST du ChatWidget)
  // Un parcours partenaire fait DEUX appels a smart-entry — le tunnel, puis
  // `handleSmartEntry` via `onComplete`. Seul le premier portait l'identifiant :
  // le second ne pouvait donc pas etre deduplique. Ce n'etait PAS un double-clic.

  test('1. le tunnel remonte son submission_id dans onComplete', () => {
    const i = TUNNEL.indexOf('onComplete(participantId, sessionId, {');
    const bloc = TUNNEL.slice(i, i + 900);
    expect(bloc).toMatch(/submission_?[iI]d/);
  });

  test('2. le second POST envoie un submission_id', () => {
    const i = WIDGET.indexOf('axios.post(`${API}/chat/smart-entry`');
    expect(i).toBeGreaterThan(0);
    const bloc = WIDGET.slice(i, i + 900);
    expect(bloc).toContain('submission_id');
  });

  test('3. il le prend de clientData, il n en fabrique pas un autre', () => {
    const i = WIDGET.indexOf('axios.post(`${API}/chat/smart-entry`');
    const bloc = WIDGET.slice(i, i + 900);
    expect(bloc).toMatch(/clientData[\s\S]{0,40}submission/);
  });

  test('4. AUCUN second UUID n est genere dans ChatWidget', () => {
    expect(WIDGET).not.toContain('p12NouveauSubmissionId');
    expect(WIDGET).not.toContain('crypto.randomUUID');
  });

  test('5. le tunnel ne genere toujours qu UN seul UUID, au montage', () => {
    expect((TUNNEL.match(/p12NouveauSubmissionId\(\)/g) || []).length).toBe(1);
    expect(TUNNEL).toMatch(/useState\(\(\) => p12NouveauSubmissionId\(\)\)/);
  });

  test('6. non-regression : absent de clientData -> champ simplement absent', () => {
    const i = WIDGET.indexOf('axios.post(`${API}/chat/smart-entry`');
    const bloc = WIDGET.slice(i, i + 900);
    // aucune valeur de repli fabriquee : un ancien appelant reste inchange
    expect(bloc).not.toMatch(/submission_id:\s*['\"]/);
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
    const i = SRC.indexOf('if (p12EstPartenaire(clientData');
    expect(i).toBeGreaterThan(0);
    const bloc = SRC.slice(i, i + 500);
    expect(bloc).toContain('setShowSubscriberForm(false)');
    expect(bloc).not.toContain('birthday');
  });
  test('19-22. aucun booking, checkout, code promo ni date de naissance sur ce chemin', () => {
    const i = SRC.indexOf('if (p12EstPartenaire(clientData');
    const bloc = SRC.slice(i, i + 500);
    ['booking', 'checkout', 'offre=', 'reserver=1', 'birthday'].forEach((m) => {
      expect(bloc).not.toContain(m);
    });
  });
});


/* ═══════════════════════ P1.2-UXFINAL ════════════════════════════════════════
 *
 * 1. UN CODE DIAGNOSTIC EXPLOITABLE. Deux incidents partenaire le 29/08, deux
 *    fois zero preuve : la requete n'atteignait pas FastAPI et le navigateur
 *    ne gardait rien. Le code doit etre lisible a voix haute au telephone et
 *    ne peut, PAR CONSTRUCTION, contenir aucune donnee personnelle.
 * 2. UN PARTENAIRE N'EST PAS UN PROSPECT D'ESSAI. L'ecran final lui promettait
 *    « ton cours d'essai sur WhatsApp » — mesure sur le parcours reel.
 * 3. UNE INTRO POUR QUI NE CONNAIT PAS AFROBOOST, repliee par defaut.
 */

describe('UXFINAL 1. code diagnostic — la forme exacte', () => {
  test('403 avec une page HTML', () => {
    expect(p12CodeDiagnostic(403, 'text/html; charset=utf-8')).toBe('HTTP-403-HTML');
  });
  test('502 avec une page HTML', () => {
    expect(p12CodeDiagnostic(502, 'text/html')).toBe('HTTP-502-HTML');
  });
  test('503 et 504 sans Content-Type exploitable', () => {
    expect(p12CodeDiagnostic(503, '')).toBe('HTTP-503');
    expect(p12CodeDiagnostic(504, null)).toBe('HTTP-504');
    expect(p12CodeDiagnostic(504, undefined)).toBe('HTTP-504');
  });
  test('du JSON sans detail reste un code nu, jamais -HTML', () => {
    expect(p12CodeDiagnostic(500, 'application/json')).toBe('HTTP-500');
  });
  test('xhtml compte comme une page', () => {
    expect(p12CodeDiagnostic(403, 'application/xhtml+xml')).toBe('HTTP-403-HTML');
  });
  test('un statut hors norme HTTP est nomme, pas invente', () => {
    ['', null, undefined, 0, 42, 999, 'abc', {}, []].forEach((v) => {
      expect(p12CodeDiagnostic(v, 'text/html')).toBe('HTTP-INCONNU');
    });
  });
  test('NET-FETCH est la constante du fetch qui jette', () => {
    expect(P12_CODE_FETCH).toBe('NET-FETCH');
  });
  test('le prefixe affiche ne nomme rien de personnel', () => {
    expect(P12_DIAG_PREFIXE).toBe('Code diagnostic : ');
  });
});

describe('UXFINAL 1bis. le code ne peut PAS fuiter de donnee personnelle', () => {
  // La garantie est STRUCTURELLE : e-mail, telephone, nom, submission_id,
  // participant_id et session_id ne sont pas des parametres de la fonction.
  // Ce banc verifie qu'aucune entree, meme hostile, ne franchit la forme.
  const FORME = /^(HTTP-\d{3}(-HTML)?|HTTP-INCONNU)$/;
  test('quoi qu on lui donne, la sortie garde la forme', () => {
    const HOSTILES = [
      'p12e2e-37d6f585@example.com', '0790000000', 'TEST PLAYWRIGHT PARTNER',
      '25eade25-94bb-4631-9dcd-5c3a2a7eb8d3', 'text/html; boundary=secret@mail.com',
      '<html>bassi@afroboost.com</html>', 200, 403,
    ];
    HOSTILES.forEach((a) => {
      HOSTILES.forEach((b) => {
        const code = p12CodeDiagnostic(a, b);
        expect(code).toMatch(FORME);
        expect(code).not.toMatch(/@/);
        expect(code).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}/);
      });
    });
  });
});

describe('UXFINAL 2. ecran final partenaire — aucune promesse d essai', () => {
  test('le texte est exactement celui demande', () => {
    expect(P12_FIN_PARTENAIRE.titre).toBe('Merci 🙌');
    expect(P12_FIN_PARTENAIRE.corps).toBe('Votre demande de collaboration a bien été enregistrée.');
    expect(P12_FIN_PARTENAIRE.suite).toBe('Bassi la consultera personnellement et vous contactera si une collaboration est pertinente.');
    expect(P12_FIN_PARTENAIRE.signature).toBe('À bientôt,');
    expect(P12_FIN_PARTENAIRE.marque).toBe('Afroboost 🎧🔥');
  });
  test('le detecteur de promesse interdite fonctionne VRAIMENT', () => {
    // Sans cette assertion, celle du dessous serait vide de sens : un
    // detecteur toujours muet ferait passer n'importe quel texte.
    expect(p12PromesseInterdite("On te confirme ton cours d'essai sur WhatsApp.")).toBeTruthy();
    expect(p12PromesseInterdite('Réservez votre séance')).toBeTruthy();
    expect(p12PromesseInterdite('Entrez votre code promo')).toBeTruthy();
    expect(p12PromesseInterdite('Votre abonnement est actif')).toBeTruthy();
    expect(p12PromesseInterdite('Procéder au paiement')).toBeTruthy();
  });
  test('aucun texte partenaire ne promet cours, reservation, promo, paiement ni abonnement', () => {
    Object.keys(P12_FIN_PARTENAIRE).forEach((k) => {
      expect(p12PromesseInterdite(P12_FIN_PARTENAIRE[k])).toBe('');
    });
    Object.keys(P12_INTRO_PARTENAIRE).forEach((k) => {
      expect(p12PromesseInterdite(P12_INTRO_PARTENAIRE[k])).toBe('');
    });
  });
});

describe('UXFINAL 3-5. intro partenaire — court, long, sous-titre', () => {
  test('l accroche et le texte court sont ceux demandes', () => {
    expect(P12_INTRO_PARTENAIRE.titre)
      .toBe('Et si vous proposiez à vos clients ou membres une expérience qu’ils n’ont encore jamais vécue ? 🎧🔥');
    expect(P12_INTRO_PARTENAIRE.texte)
      .toBe('Afroboost mélange danse afro, fitness et musique au casque dans une expérience immersive, fun et accessible à tous.');
  });
  test('le contenu deplie est celui demande', () => {
    expect(P12_INTRO_PARTENAIRE.detail1).toContain('quelques partenaires à Neuchâtel');
    expect(P12_INTRO_PARTENAIRE.detail1).toContain('30 jours');
    expect(P12_INTRO_PARTENAIRE.detail1).toContain('gratuite et sans engagement');
    expect(P12_INTRO_PARTENAIRE.detail1).toContain('visibilité croisée');
    expect(P12_INTRO_PARTENAIRE.detail2).toContain('créer de la valeur ensemble');
    expect(P12_INTRO_PARTENAIRE.detail2).toContain('sans engagement à long terme');
  });
  test('les deux libelles du depliant', () => {
    expect(P12_INTRO_PARTENAIRE.plus).toBe('… Lire plus');
    expect(P12_INTRO_PARTENAIRE.moins).toBe('Lire moins');
  });
  test('le sous-titre remplace « personnaliser votre experience »', () => {
    expect(P12_INTRO_PARTENAIRE.sousTitre).toBe('Voyons en 1 minute si une collaboration est possible 🤝');
    expect(P12_INTRO_PARTENAIRE.sousTitre).not.toContain('personnaliser');
  });
});

describe('UXFINAL — OnboardingTunnel cable (lecture de la source)', () => {
  const fs = require('fs');
  const path = require('path');
  const SRC = fs.readFileSync(
    path.join(__dirname, '..', '..', 'components', 'chat', 'OnboardingTunnel.js'), 'utf8');

  test('1. le code vient du statut ET du Content-Type, de rien d autre', () => {
    expect(SRC).toContain("p12CodeDiagnostic(response.status, response.headers.get('content-type'))");
  });
  test('1. un refus applicatif porteur d un detail n affiche AUCUN code', () => {
    const i = SRC.indexOf('erreur.codeDiag');
    expect(i).toBeGreaterThan(0);
    const bloc = SRC.slice(i, i + 220);
    expect(bloc).toContain('errData.detail');
    expect(bloc).toContain("''");
  });
  test('1. un fetch qui jette donne NET-FETCH', () => {
    expect(SRC).toContain("const notre = (typeof err.codeDiag === 'string')");
    expect(SRC).toContain('setDiagCode(notre ? err.codeDiag : P12_CODE_FETCH)');
  });
  test('1. un fetch qui jette n affiche JAMAIS le message du navigateur', () => {
    // `err.message` vaut « Failed to fetch » sur un abort Chromium : une chaine
    // technique, en anglais, incomprehensible pour un prospect. On ne reprend
    // `err.message` que si l'erreur vient de NOUS (elle porte alors `codeDiag`).
    expect(SRC).toContain('setError(notre ? (err.message || P12_MESSAGE_RESEAU) : P12_MESSAGE_RESEAU)');
    expect(SRC).not.toContain('setError(err.message || P12_MESSAGE_RESEAU)');
  });
  test('1. le code est remis a zero a chaque nouvelle tentative', () => {
    expect(SRC).toContain("setDiagCode('')");
  });
  test('1. il n est affiche QUE s il existe, sous le message', () => {
    expect(SRC).toContain('{error && diagCode && (');
    expect(SRC).toContain('{P12_DIAG_PREFIXE}{diagCode}');
  });
  test('1. rien de personnel n est passe a la fonction', () => {
    const i = SRC.indexOf('p12CodeDiagnostic(response.status');
    expect(i).toBeGreaterThan(0);
    const bloc = SRC.slice(i, i + 160);
    ['email', 'whatsapp', 'formData', 'submissionId', 'participant', 'session']
      .forEach((m) => expect(bloc).not.toContain(m));
  });

  test('3-4. l intro partenaire est cablee sur les constantes', () => {
    ['titre', 'texte', 'detail1', 'detail2', 'sousTitre', 'plus', 'moins'].forEach((k) => {
      expect(SRC).toContain('P12_INTRO_PARTENAIRE.' + k);
    });
  });
  test('4. le depliant est REPLIE au chargement', () => {
    expect(SRC).toContain('const [introDepliee, setIntroDepliee] = useState(false)');
    expect(SRC).toContain('hidden={!introDepliee}');
  });
  test('4. le bouton bascule plus <-> moins', () => {
    expect(SRC).toContain('introDepliee ? P12_INTRO_PARTENAIRE.moins : P12_INTRO_PARTENAIRE.plus');
    expect(SRC).toContain('setIntroDepliee(v => !v)');
  });
  test('4. accessibilite : vrai <button>, aria-expanded, aria-controls', () => {
    const i = SRC.indexOf('data-testid="p12-intro-toggle"');
    expect(i).toBeGreaterThan(0);
    const bloc = SRC.slice(i - 400, i + 200);
    expect(bloc).toContain('<button');
    expect(bloc).toContain('type="button"');
    expect(bloc).toContain('aria-expanded={introDepliee}');
    expect(bloc).toContain('aria-controls="p12-intro-detail"');
  });
  test('4. aucun scroll force', () => {
    expect(SRC).not.toContain('scrollIntoView');
    expect(SRC).not.toContain('window.scrollTo');
  });
  test('5-9. NON-REGRESSION : le tunnel non-partenaire garde son texte', () => {
    expect(SRC).toContain('étapes pour personnaliser votre expérience');
    expect(SRC).toContain('{welcomeMsg}');
    // ...et il vient APRES l'intro partenaire : c'est la branche « sinon ».
    const i = SRC.indexOf('étapes pour personnaliser votre expérience');
    const j = SRC.indexOf('P12_INTRO_PARTENAIRE.sousTitre');
    expect(j).toBeGreaterThan(0);
    expect(i).toBeGreaterThan(j);
  });
  test('6. NON-REGRESSION : le cadrage HEROFIX est intact', () => {
    expect(SRC).toContain("objectPosition: '50% 10%'");
    expect(SRC).toContain("height: '150px'");
    expect(SRC).toContain("objectFit: 'cover'");
    expect(SRC).toContain('/hero-afroboost.jpg');
  });
});

describe('UXFINAL — ChatWidget cable (lecture de la source)', () => {
  const fs = require('fs');
  const path = require('path');
  const SRC = fs.readFileSync(
    path.join(__dirname, '..', '..', 'components', 'ChatWidget.js'), 'utf8');

  test('2. le drapeau partenaire est pose AVANT d ouvrir l ecran', () => {
    const i = SRC.indexOf('setTrialConfirmPartner(p12EstPartenaire(');
    const j = SRC.indexOf('setShowTrialConfirm(true)');
    expect(i).toBeGreaterThan(0);
    expect(j).toBeGreaterThan(i);
  });
  test('2. un partenaire ne lit PLUS « ton cours d essai »', () => {
    expect(SRC).toContain('trialConfirmPartner ? P12_FIN_PARTENAIRE.corps :');
    expect(SRC).toContain('trialConfirmPartner ? P12_FIN_PARTENAIRE.titre :');
    expect(SRC).toContain('trialConfirmPartner ? P12_FIN_PARTENAIRE.signature :');
  });
  test('2. NON-REGRESSION : le tunnel d essai garde exactement son texte', () => {
    expect(SRC).toContain('🎉 Ta demande est bien enregistrée !');
    expect(SRC).toContain("On te confirme ton cours d'essai sur WhatsApp.");
    expect(SRC).toContain('À très vite chez Afroboost 🎧🔥');
  });
  test('2. la phrase d essai est BORNEE a la branche non-partenaire', () => {
    const i = SRC.indexOf("On te confirme ton cours d'essai sur WhatsApp.");
    const bloc = SRC.slice(i - 240, i);
    expect(bloc).toContain('trialConfirmPartner ?');
  });
});
