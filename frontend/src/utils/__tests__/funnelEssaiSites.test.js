/**
 * FUNNEL ESSAI — les POINTS D'APPEL dans App.js, lus comme du texte.
 *
 * POURQUOI UN TEST DE SOURCE. `App.js` fait 8 100 lignes et monte toute la
 * vitrine : le rendre dans jsdom demanderait de simuler le reseau, le routeur,
 * le slider et PostHog. Ces tests ne remplacent pas un banc navigateur — ils
 * repondent a la seule question qu'un banc ne pose jamais deux fois : les
 * quatre evenements sont-ils TOUJOURS branches, et au BON endroit ?
 *
 * Ils protegent aussi, et c'est le plus important pour l'ETAPE 1, ce qui ne
 * doit PAS bouger : la navigation du Hero et le corps du POST /checkout/free.
 * L'instrumentation est censee etre invisible pour l'utilisateur ; un test qui
 * ne verifie que les ajouts ne le prouverait pas.
 */
import fs from 'fs';
import path from 'path';
import { EVENEMENTS_FUNNEL } from '../funnelEssai';

const APP = fs.readFileSync(path.join(__dirname, '..', '..', 'App.js'), 'utf8');

// Reperes stables du fichier, verifies un a un a l'audit du 25/08/2026.
const ANCRE_SELECT_OFFER = 'const handleSelectOffer = (offer) => {';
const ANCRE_SUBMIT = 'const handleSubmit = async (e) => {';
const ANCRE_BRANCHE_GRATUIT = 'if (totalPrice === 0) {';
const ANCRE_POST_FREE = "axios.post(`${API}/checkout/free`";
const ANCRE_SUCCES_FREE = 'setLastReservation(freeRes.data);';

function position(extrait) {
  const i = APP.indexOf(extrait);
  expect(i).toBeGreaterThan(-1);   // l'ancre elle-meme doit exister
  return i;
}

/**
 * Position d'un appel `funnelTracer('<nom>'`, insensible au formatage : un
 * appel sur plusieurs lignes est le meme appel. On teste le branchement, pas
 * la mise en page.
 */
function motifAppel(nom) {
  return new RegExp(`funnelTracer\\(\\s*'${nom}'`);
}

function positionAppel(nom) {
  const m = APP.match(motifAppel(nom));
  expect(m).not.toBeNull();
  return m.index;
}

// --------------------------------------------------------------------------
describe('le module est bien la source unique de la mesure', () => {
  test('App.js importe funnelTracer et funnelVariante', () => {
    expect(APP).toMatch(/import\s*\{[^}]*funnelTracer[^}]*\}\s*from\s*['"]\.\/utils\/funnelEssai['"]/);
    expect(APP).toMatch(/import\s*\{[^}]*funnelVariante[^}]*\}\s*from\s*['"]\.\/utils\/funnelEssai['"]/);
  });

  test('plus AUCUN posthog.capture direct ne subsiste dans App.js', () => {
    // Un appel direct echapperait au filtre de donnees personnelles et au
    // try/catch : les deux garanties de l'ETAPE 1 tomberaient sans bruit.
    expect(APP).not.toMatch(/posthog\s*\.\s*capture/);
  });

  test('les quatre evenements sont tous branches', () => {
    EVENEMENTS_FUNNEL.forEach((nom) => {
      expect(APP).toMatch(motifAppel(nom));
    });
  });
});

// --------------------------------------------------------------------------
describe('chaque evenement part au bon moment', () => {
  test('trial_cta_click reste sur le CTA du Hero, avec sa variante et sendBeacon', () => {
    const i = positionAppel('trial_cta_click');
    const bloc = APP.slice(i, i + 400);
    expect(bloc).toContain('homepage_hero');
    expect(bloc).toContain('variante');
    // Le clic navigue dans la foulee : sans sendBeacon il n'est jamais compte.
    expect(bloc).toContain('sendBeacon');
  });

  test('trial_form_open part la ou le formulaire s ouvre REELLEMENT', () => {
    // `handleSelectOffer` est le point d'entree unique de TOUS les chemins de
    // selection (le commentaire V260 le dit). Mais il sort avant pour la preuve
    // sociale et pour l'achat direct : l'evenement doit donc etre colle au
    // `setSelectedOffer(offer)` final, pas en tete de fonction — sinon on
    // compterait des ouvertures qui n'ont pas lieu.
    const debut = position(ANCRE_SELECT_OFFER);
    const iOuverture = APP.indexOf('setSelectedOffer(offer);', debut);
    const iEvenement = positionAppel('trial_form_open');
    expect(iOuverture).toBeGreaterThan(debut);
    expect(iEvenement).toBeGreaterThan(debut);
    // colle a l'ouverture : moins de 500 caracteres d'ecart
    expect(Math.abs(iEvenement - iOuverture)).toBeLessThan(500);
  });

  test('trial_form_submit part APRES les validations et AVANT le branchement gratuit', () => {
    // Avant les validations, un formulaire refuse trois fois compterait trois
    // soumissions : le taux serait faux et gonfle.
    const debutSubmit = position(ANCRE_SUBMIT);
    const iEvenement = positionAppel('trial_form_submit');
    const iBranche = APP.indexOf(ANCRE_BRANCHE_GRATUIT, debutSubmit);

    expect(iEvenement).toBeGreaterThan(debutSubmit);
    expect(iBranche).toBeGreaterThan(-1);
    expect(iEvenement).toBeLessThan(iBranche);

    // ... et apres la derniere garde qui peut encore renvoyer (`return`).
    const iGardeTerms = APP.indexOf('termsRequired && !hasAcceptedTerms', debutSubmit);
    expect(iEvenement).toBeGreaterThan(iGardeTerms);
  });

  test('trial_granted part APRES la reussite du POST, jamais avant', () => {
    const iPost = position(ANCRE_POST_FREE);
    const iSucces = position(ANCRE_SUCCES_FREE);
    const iEvenement = positionAppel('trial_granted');
    expect(iEvenement).toBeGreaterThan(iPost);
    expect(iEvenement).toBeGreaterThan(iSucces);
  });
});

// --------------------------------------------------------------------------
describe('ETAPE 1 — ce qui ne doit PAS avoir bouge', () => {
  test('le CTA du Hero pointe TOUJOURS sur le tunnel Chat', () => {
    // Le changement de navigation est l'ETAPE 2, explicitement non autorisee.
    expect(APP).toContain('href="/?link=b83914b4-c5a"');
    expect(APP).not.toContain('href="/?offre=');
  });

  test('le corps du POST /checkout/free est inchange', () => {
    const i = position(ANCRE_POST_FREE);
    const bloc = APP.slice(i, i + 700);
    ['terms_accepted', 'coach_email', 'items', 'customer_name',
     'customer_email', 'customer_phone', 'discount_code'].forEach((champ) => {
      expect(bloc).toContain(champ);
    });
  });

  test('aucune mesure ne s intercale entre la soumission et le POST', () => {
    // Un `await` de mesure ajouterait de la latence au checkout : interdit.
    const iEvenement = positionAppel('trial_form_submit');
    const bloc = APP.slice(iEvenement, iEvenement + 200);
    expect(bloc).not.toContain('await funnelTracer');
  });

  test('aucun funnelTracer n est attendu (await) nulle part', () => {
    expect(APP).not.toMatch(/await\s+funnelTracer/);
  });
});
