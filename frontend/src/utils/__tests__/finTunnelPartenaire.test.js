/**
 * P1.1-FIX — UN PROSPECT PARTENAIRE N'EST PAS UN ABONNE.
 *
 * CE QUI N'ALLAIT PAS. A la fin d'un tunnel, si la personne est deja connue en
 * base (e-mail ou numero deja vus), le serveur renvoie `proof_required` sous le
 * drapeau SUBSCRIBER_STRICT_ENTRY — actif en production. ChatWidget n'avait
 * qu'UNE porte de sortie propre, l'ecran « votre demande est enregistree », et
 * elle etait reservee a UN SEUL token code en dur : celui du lien d'essai
 * (`C2G_LIEN_ESSAI`). Tout autre lien — dont « Devenir Partenaire Afroboost » —
 * tombait sur le formulaire ABONNE : nom, WhatsApp, e-mail, CODE PROMO, DATE DE
 * NAISSANCE, « Valider mon abonnement ».
 *
 * Reclamer un code d'abonne a un gerant de salon qui propose un partenariat, ce
 * n'est pas une friction : c'est la fin de la conversation.
 *
 * LA REGLE, GENERIQUE : partner != subscriber. On ne teste plus un token, on
 * lit `lead_type` — deja charge par le tunnel avant l'affichage et remonte dans
 * `clientData.linkData`.
 *
 * POURQUOI CETTE REGLE VIT DANS UN MODULE A PART. `ChatWidget.js` (9400 lignes,
 * ES5) n'est PAS importable par Jest : l'import echoue. Une decision enfouie
 * dedans serait donc intestable, et c'est precisement le genre de condition
 * qu'il faut pouvoir prouver. Le module ne contient que la regle, sans etat.
 */
import { p11FinSansFormulaireAbonne, P11_LIEN_ESSAI } from '../finTunnelPartenaire';

const OK = { acquisition_saved: true, proof_required: true };
const PARTNER = { lead_type: 'partner' };
const PARTICIPANT = { lead_type: 'participant' };

describe('1. le cas qui motive le lot', () => {
  test('lien partenaire + proof_required -> PAS le formulaire abonne', () => {
    expect(p11FinSansFormulaireAbonne(OK, '807fe7', PARTNER)).toBe(true);
  });
  test('la regle ne depend PAS du token 807fe7', () => {
    expect(p11FinSansFormulaireAbonne(OK, 'un-autre-lien-partenaire', PARTNER)).toBe(true);
  });
  test('les deux anciens liens partenaire en beneficient aussi', () => {
    expect(p11FinSansFormulaireAbonne(OK, '3f89357f-dec', PARTNER)).toBe(true);
    expect(p11FinSansFormulaireAbonne(OK, '14ee7437-370', PARTNER)).toBe(true);
  });
});

describe('2. le lien d essai : strictement identique', () => {
  test('il sort toujours par la porte propre', () => {
    expect(p11FinSansFormulaireAbonne(OK, P11_LIEN_ESSAI, { lead_type: 'participant' })).toBe(true);
  });
  test('meme sans linkData (comportement d avant ce lot)', () => {
    expect(p11FinSansFormulaireAbonne(OK, P11_LIEN_ESSAI, null)).toBe(true);
    expect(p11FinSansFormulaireAbonne(OK, P11_LIEN_ESSAI, undefined)).toBe(true);
  });
  test('le token de l essai est bien celui de production', () => {
    expect(P11_LIEN_ESSAI).toBe('b83914b4-c5a');
  });
});

describe('3. les autres Smart Links : rien ne change', () => {
  test('un lien participant garde le comportement historique', () => {
    expect(p11FinSansFormulaireAbonne(OK, 'lien-participant-x', PARTICIPANT)).toBe(false);
  });
  test('un lien collaboration aussi', () => {
    expect(p11FinSansFormulaireAbonne(OK, 'lien-collab', { lead_type: 'collaboration' })).toBe(false);
  });
  test('un lien sans lead_type aussi', () => {
    expect(p11FinSansFormulaireAbonne(OK, 'lien-vieux', {})).toBe(false);
    expect(p11FinSansFormulaireAbonne(OK, 'lien-vieux', null)).toBe(false);
  });
});

describe('4. prospect inconnu : parcours normal', () => {
  test('sans proof_required ni acquisition_saved, la regle ne s applique pas', () => {
    expect(p11FinSansFormulaireAbonne({}, '807fe7', PARTNER)).toBe(false);
    expect(p11FinSansFormulaireAbonne({ participant: { id: 'x' } }, '807fe7', PARTNER)).toBe(false);
  });
  test('acquisition_saved false : comportement historique conserve', () => {
    expect(p11FinSansFormulaireAbonne({ acquisition_saved: false }, '807fe7', PARTNER)).toBe(false);
  });
});

describe('5. robustesse — jamais d exception', () => {
  [null, undefined, 0, 'x', [], { lead_type: ['partner'] }].forEach((mauvais) => {
    test(`linkData = ${JSON.stringify(mauvais)}`, () => {
      expect(() => p11FinSansFormulaireAbonne(OK, '807fe7', mauvais)).not.toThrow();
    });
  });
  test('reponse absente', () => {
    expect(p11FinSansFormulaireAbonne(null, '807fe7', PARTNER)).toBe(false);
    expect(p11FinSansFormulaireAbonne(undefined, '807fe7', PARTNER)).toBe(false);
  });
  test('lead_type est compare en minuscules, sans espaces', () => {
    expect(p11FinSansFormulaireAbonne(OK, '807fe7', { lead_type: ' Partner ' })).toBe(true);
  });
});

describe('6. ChatWidget consomme bien la regle', () => {
  const fs = require('fs');
  const path = require('path');
  const SRC = fs.readFileSync(path.join(__dirname, '..', '..', 'components', 'ChatWidget.js'), 'utf8');

  test('la condition n est plus un test de token seul', () => {
    expect(SRC).not.toContain("acquisition_saved === true && linkToken === C2G_LIEN_ESSAI");
  });
  test('elle passe par la regle partagee', () => {
    expect(SRC).toContain('p11FinSansFormulaireAbonne');
  });
  test('le lead_type vient de clientData.linkData', () => {
    expect(SRC).toMatch(/p11FinSansFormulaireAbonne\([\s\S]{0,120}linkData/);
  });
  test('aucun booking ni checkout ajoute sur ce chemin', () => {
    const i = SRC.indexOf('p11FinSansFormulaireAbonne(');
    const bloc = SRC.slice(i, i + 400);
    ['booking', 'checkout', 'payment', 'offre=', 'reserver=1'].forEach((m) => {
      expect(bloc).not.toContain(m);
    });
  });
  test('aucun code promo ni date de naissance demandes sur ce chemin', () => {
    const i = SRC.indexOf('p11FinSansFormulaireAbonne(');
    const bloc = SRC.slice(i, i + 400);
    expect(bloc).not.toContain('birthday');
    expect(bloc).toContain('setShowSubscriberForm(false)');
  });
});
