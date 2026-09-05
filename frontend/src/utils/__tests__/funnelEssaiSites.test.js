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
// ESSAI-7 : le funnel ne s'arrete plus a la vitrine. `session_booked` part de
// l'espace participant, ou la reservation est REELLEMENT confirmee.
const ESPACE = fs.readFileSync(
  path.join(__dirname, '..', '..', 'components', 'SubscriberSpace.js'), 'utf8');
const SOURCES = APP + '\n' + ESPACE;

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

  test('les cinq evenements sont tous branches', () => {
    EVENEMENTS_FUNNEL.forEach((nom) => {
      expect(SOURCES).toMatch(motifAppel(nom));
    });
  });

  test('SubscriberSpace.js passe lui aussi par le module, jamais par posthog', () => {
    expect(ESPACE).not.toMatch(/posthog\s*\.\s*capture/);
    expect(ESPACE).toMatch(
      /import\s*\{[^}]*funnelTracer[^}]*\}\s*from\s*['"]\.\.\/utils\/funnelEssai['"]/);
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

  test('le corps du POST /checkout/free garde tout ce qui vient du client', () => {
    const i = position(ANCRE_POST_FREE);
    // Fenetre large : le corps porte desormais un commentaire explicatif.
    const bloc = APP.slice(i, i + 1000);
    ['terms_accepted', 'items', 'customer_name',
     'customer_email', 'customer_phone', 'discount_code'].forEach((champ) => {
      expect(bloc).toContain(champ);
    });
  });

  test('R2b — le navigateur ne DESIGNE plus le vendeur', () => {
    // Avant R2b, la page lisait `selectedOffer.coach_id` — donc l'adresse
    // e-mail du coach — et la renvoyait au serveur. Deux problemes : la route
    // publique devait publier cette adresse, et le NAVIGATEUR decidait qui
    // recoit l'argent. Le serveur la lit maintenant dans le catalogue
    // (`_r2b_resoudre_vendeur`). L'attribution n'est pas perdue : elle est
    // simplement redevenue l'affaire du serveur.
    const i = position(ANCRE_POST_FREE);
    const bloc = APP.slice(i, i + 1000);
    expect(bloc).not.toMatch(/coach_email:/);
    expect(APP).not.toContain('coach_email: selectedOffer.coach_id');
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


// ==========================================================================
// ESSAI-7 — DU CODE OBTENU A LA SEANCE RESERVEE
// ==========================================================================
const ANCRE_RESERVE_POST = '/reserve/${encodeURIComponent(occurrence.course_id)}';

function positionAppelDans(src, nom) {
  const m = src.match(motifAppel(nom));
  expect(m).not.toBeNull();
  return m.index;
}

describe('la redirection apres octroi', () => {
  test('App.js ne fabrique JAMAIS une URL /espace/ lui-meme', () => {
    // Un code reconstruit cote frontend (localStorage, e-mail saisi, memoire
    // d'un ancien achat) enverrait la personne sur l'espace de quelqu'un
    // d'autre — ou sur un 404 juste apres un essai reellement accorde.
    // La seule fabrication autorisee vit dans `utils/essaiReservation.js`.
    expect(APP).not.toMatch(/['"`]\/espace\//);
  });

  test('App.js delegue la decision a cibleRedirectionEssai', () => {
    expect(APP).toMatch(
      /import\s*\{[^}]*cibleRedirectionEssai[^}]*\}\s*from\s*['"]\.\/utils\/essaiReservation['"]/);
    expect(APP).toMatch(/cibleRedirectionEssai\(\s*freeRes\.data\s*\)/);
  });

  test('la redirection vient APRES la reussite du POST et apres trial_granted', () => {
    const iPost = position(ANCRE_POST_FREE);
    const iOctroi = positionAppel('trial_granted');
    const iCible = APP.search(/cibleRedirectionEssai\(/);
    expect(iCible).toBeGreaterThan(iPost);
    expect(iCible).toBeGreaterThan(iOctroi);
  });

  test('aucune redirection n est possible sans cible : la navigation est gardee', () => {
    // Un refus anti-2e-essai part dans le `catch` et ne doit RIEN ouvrir ; un
    // succes sans code (backend non deploye) non plus. La navigation n'existe
    // donc qu'a l'interieur de la garde, et la cible est calculee avant elle.
    const iCalcul = APP.search(/cibleRedirectionEssai\(/);
    const iGarde = APP.search(/if\s*\(\s*cibleEssai\s*\)/);
    const iNav = APP.indexOf('window.location.href = cibleEssai');
    expect(iCalcul).toBeGreaterThan(-1);
    expect(iGarde).toBeGreaterThan(iCalcul);
    expect(iNav).toBeGreaterThan(iGarde);
    // `cibleEssai` ne sert a rien d'autre qu'a cette navigation-la.
    expect(APP.match(/window\.location\.href\s*=\s*cibleEssai/g)).toHaveLength(1);
  });
});

describe('session_booked — au bon moment, et pas avant', () => {
  test('part depuis SubscriberSpace.js, apres la reponse du serveur', () => {
    const iPost = ESPACE.indexOf(ANCRE_RESERVE_POST);
    expect(iPost).toBeGreaterThan(-1);
    const iEvenement = positionAppelDans(ESPACE, 'session_booked');
    expect(iEvenement).toBeGreaterThan(iPost);
  });

  test('reste DANS le try : une reservation refusee ne compte pas', () => {
    const iEvenement = positionAppelDans(ESPACE, 'session_booked');
    // le `catch` de `handleReserve` — tout ce qui suit est un echec
    const iCatch = ESPACE.indexOf('} catch (err) {', ESPACE.indexOf(ANCRE_RESERVE_POST));
    expect(iCatch).toBeGreaterThan(-1);
    expect(iEvenement).toBeLessThan(iCatch);
  });

  test('ne part pas au clic : le bouton n appelle que handleReserve', () => {
    const iBouton = ESPACE.indexOf('onClick={() => handleReserve(occ)}');
    expect(iBouton).toBeGreaterThan(-1);
    expect(ESPACE.slice(iBouton, iBouton + 200)).not.toContain('funnelTracer');
  });

  test('n est jamais attendu (await) : la mesure n ajoute aucune latence', () => {
    expect(ESPACE).not.toMatch(/await\s+funnelTracer/);
  });
});
