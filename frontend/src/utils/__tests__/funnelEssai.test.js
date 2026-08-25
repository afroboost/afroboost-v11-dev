/**
 * FUNNEL ESSAI — tests de l'instrumentation analytique.
 *
 * HORS LIGNE. `window.posthog` est un espion : aucun evenement ne part.
 *
 * CE QUE CES TESTS PROTEGENT, ET QUI N'EST PAS COSMETIQUE :
 *   1. une panne de mesure ne doit JAMAIS interrompre une reservation ;
 *   2. aucune donnee personnelle ne doit atteindre PostHog ;
 *   3. la variante d'entree (Hero/Chat vs direct) doit SURVIVRE a la
 *      redirection que le tunnel fait vers `?offre=...` — sans quoi 100 % des
 *      parcours Chat seraient comptes comme « direct » et la comparaison
 *      demandee (Hero vs Chat) serait fausse a l'envers.
 *
 * Aucune dependance ajoutee : jest + jsdom viennent de react-scripts, et le
 * module teste est du JS pur (ni React, ni reseau).
 */
import {
  EVENEMENTS_FUNNEL,
  funnelTracer,
  funnelVariante,
  CLE_VARIANTE
} from '../funnelEssai';

const OFFRE_ESSAI = 'c1e5f73c-0f16-402e-a746-2041e23f72e8';

let ph;

beforeEach(() => {
  try { sessionStorage.clear(); } catch (e) { /* jsdom */ }
  window.history.replaceState({}, '', '/');
  ph = { capture: jest.fn() };
  window.posthog = ph;
});

afterEach(() => { delete window.posthog; });

// --------------------------------------------------------------------------
describe('les cinq evenements du funnel', () => {
  test('portent exactement les noms retenus a l audit', () => {
    expect(EVENEMENTS_FUNNEL).toEqual([
      'trial_cta_click',
      'trial_form_open',
      'trial_form_submit',
      'trial_granted',
      // ESSAI-7 : le pas qui manquait. Entre « le code existe » et « la
      // personne vient au cours », rien n'etait mesure — or c'est LA le
      // decrochage constate le 25/08/2026.
      'session_booked'
    ]);
  });

  test('session_booked ferme le funnel : trial_granted -> session_booked', () => {
    // L'ordre de la liste EST la lecture du funnel dans PostHog. Un evenement
    // ajoute au milieu decalerait toutes les etapes de la baseline.
    expect(EVENEMENTS_FUNNEL.indexOf('session_booked'))
      .toBe(EVENEMENTS_FUNNEL.indexOf('trial_granted') + 1);
    expect(EVENEMENTS_FUNNEL[EVENEMENTS_FUNNEL.length - 1]).toBe('session_booked');
  });

  test('session_booked ne laisse passer aucune donnee personnelle', () => {
    // Le point d'appel vit dans l'espace participant, ou le code AFR-, le
    // prenom et les prenoms des accompagnants sont a portee de main.
    funnelTracer('session_booked', {
      course_id: 'cours-42',
      is_trial: true,
      access_code: 'AFR-2287CA',
      prenom: 'Ana',
      guest_name: 'Bea'
    });
    expect(ph.capture).toHaveBeenCalledWith(
      'session_booked',
      { course_id: 'cours-42', is_trial: true }
    );
  });
});

// --------------------------------------------------------------------------
describe('funnelTracer — envoi', () => {
  test('transmet l evenement et ses proprietes a PostHog', () => {
    const decision = funnelTracer('trial_form_open', { offer_id: OFFRE_ESSAI, variante: 'direct' });

    expect(decision).toBe('envoye');
    expect(ph.capture).toHaveBeenCalledTimes(1);
    expect(ph.capture).toHaveBeenCalledWith(
      'trial_form_open',
      { offer_id: OFFRE_ESSAI, variante: 'direct' }
    );
  });

  test('accepte un appel sans proprietes', () => {
    expect(funnelTracer('trial_granted')).toBe('envoye');
    expect(ph.capture).toHaveBeenCalledWith('trial_granted', {});
  });

  test('relaie le transport sendBeacon sans le confondre avec les proprietes', () => {
    // Le CTA du Hero navigue DANS LA FOULEE du clic : sans `sendBeacon`,
    // la requete est annulee par la navigation et le clic n est jamais compte.
    // Ce comportement existe deja en production (App.js) et ne doit pas se
    // perdre en passant par ce module.
    funnelTracer('trial_cta_click', { source: 'homepage_hero' }, { transport: 'sendBeacon' });

    expect(ph.capture).toHaveBeenCalledWith(
      'trial_cta_click',
      { source: 'homepage_hero' },
      { transport: 'sendBeacon' }
    );
  });

  test('sans options, capture est appele avec deux arguments seulement', () => {
    funnelTracer('trial_granted', { offer_id: OFFRE_ESSAI });
    expect(ph.capture.mock.calls[0]).toHaveLength(2);
  });

  test('refuse un nom d evenement hors des quatre, et n envoie RIEN', () => {
    // Garde-fou contre la faute de frappe : un evenement mal nomme ne serait
    // jamais retrouve dans PostHog et la baseline serait silencieusement trouee.
    expect(funnelTracer('trial_form_opened', { offer_id: OFFRE_ESSAI })).toBe('evenement-inconnu');
    expect(ph.capture).not.toHaveBeenCalled();
  });
});

// --------------------------------------------------------------------------
describe('funnelTracer — ne bloque JAMAIS le parcours', () => {
  test('PostHog absent : renvoie une decision, ne leve pas', () => {
    delete window.posthog;
    expect(() => funnelTracer('trial_granted')).not.toThrow();
    expect(funnelTracer('trial_granted')).toBe('posthog-indisponible');
  });

  test('PostHog present mais sans capture : ne leve pas', () => {
    window.posthog = {};
    expect(() => funnelTracer('trial_granted')).not.toThrow();
    expect(funnelTracer('trial_granted')).toBe('posthog-indisponible');
  });

  test('capture() qui leve (adblock, quota, SDK casse) : avale et signale', () => {
    window.posthog = { capture: () => { throw new Error('bloque par une extension'); } };
    expect(() => funnelTracer('trial_form_submit')).not.toThrow();
    expect(funnelTracer('trial_form_submit')).toBe('erreur');
  });
});

// --------------------------------------------------------------------------
describe('funnelTracer — aucune donnee personnelle', () => {
  test('retire e-mail, nom et telephone avant l envoi', () => {
    funnelTracer('trial_form_submit', {
      offer_id: OFFRE_ESSAI,
      email: 'quelquun@exemple.ch',
      customer_email: 'quelquun@exemple.ch',
      name: 'Prenom Nom',
      userName: 'Prenom Nom',
      whatsapp: '+41790000000',
      customer_phone: '+41790000000',
      code: 'AFR-123456'
    });

    expect(ph.capture).toHaveBeenCalledWith('trial_form_submit', { offer_id: OFFRE_ESSAI });
  });

  test('conserve les proprietes non personnelles', () => {
    funnelTracer('trial_cta_click', { source: 'homepage_hero', variante: 'chat', is_free: true });

    expect(ph.capture).toHaveBeenCalledWith(
      'trial_cta_click',
      { source: 'homepage_hero', variante: 'chat', is_free: true }
    );
  });
});

// --------------------------------------------------------------------------
describe('funnelVariante — d ou vient la personne', () => {
  test('« chat » quand l URL porte ?link=', () => {
    window.history.replaceState({}, '', '/?link=b83914b4-c5a');
    expect(funnelVariante()).toBe('chat');
  });

  test('« direct » quand l URL porte ?offre= sans ?link=', () => {
    window.history.replaceState({}, '', `/?offre=${OFFRE_ESSAI}&reserver=1`);
    expect(funnelVariante()).toBe('direct');
  });

  test('« organique » sans aucun parametre', () => {
    expect(funnelVariante()).toBe('organique');
  });

  test('LE CAS QUI COMPTE : la variante « chat » survit a la redirection du tunnel', () => {
    // 1. la personne entre par le Hero, qui pointe aujourd hui sur le Chat
    window.history.replaceState({}, '', '/?link=b83914b4-c5a');
    expect(funnelVariante()).toBe('chat');

    // 2. le tunnel s acheve et redirige vers la carte d offre : `link` DISPARAIT
    window.history.replaceState({}, '', `/?offre=${OFFRE_ESSAI}&reserver=1`);

    // 3. sans memoire, on compterait ce parcours comme « direct » — a l envers.
    expect(funnelVariante()).toBe('chat');
  });

  test('une entree directe n est pas ecrasee par une visite ulterieure', () => {
    window.history.replaceState({}, '', `/?offre=${OFFRE_ESSAI}`);
    expect(funnelVariante()).toBe('direct');
    window.history.replaceState({}, '', '/?link=b83914b4-c5a');
    expect(funnelVariante()).toBe('direct');
  });

  test('memorise la variante sous une cle dediee', () => {
    window.history.replaceState({}, '', '/?link=b83914b4-c5a');
    funnelVariante();
    expect(sessionStorage.getItem(CLE_VARIANTE)).toBe('chat');
  });

  test('une visite organique ne fige RIEN — la vraie entree reste mesurable', () => {
    expect(funnelVariante()).toBe('organique');
    expect(sessionStorage.getItem(CLE_VARIANTE)).toBe(null);
    window.history.replaceState({}, '', '/?link=b83914b4-c5a');
    expect(funnelVariante()).toBe('chat');
  });

  test('stockage indisponible (navigation privee) : ne leve pas', () => {
    const vrai = Object.getOwnPropertyDescriptor(window, 'sessionStorage');
    Object.defineProperty(window, 'sessionStorage', {
      configurable: true,
      get() { throw new Error('acces refuse'); }
    });
    try {
      expect(() => funnelVariante()).not.toThrow();
      expect(funnelVariante()).toBe('inconnu');
    } finally {
      if (vrai) Object.defineProperty(window, 'sessionStorage', vrai);
    }
  });
});
