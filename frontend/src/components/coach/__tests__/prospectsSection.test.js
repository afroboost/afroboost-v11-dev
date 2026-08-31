// P3-S2 — L'ECRAN PROSPECTION, vu du navigateur.
//
// CE QUI EST PROUVE ICI, ET POURQUOI CHAQUE POINT COMPTE :
//
//   * l'ecran vide dit « aucun prospect » — pas un zero, pas un spinner sans
//     fin, pas une erreur : c'est l'etat qu'il aura le jour du deploiement,
//     avant l'import ;
//   * les tuiles lisent `counts` du serveur et JAMAIS la longueur de la page :
//     avec 80 prospects et 25 par page, compter les lignes affichees donnerait
//     25 partout ;
//   * « Candidatures » et « Acceptes » viennent du serveur, qui compte des
//     prospects PORTANT un lien vers P2 — aucun compteur P2 n'est recopie ;
//   * chaque filtre part bien dans la requete, et vider un filtre le retire ;
//   * la pagination envoie un `offset`, sinon on ne verrait jamais les
//     prospects 51 a 80 ;
//   * la fiche montre le detail et n'enregistre QUE ce qui a change — un PATCH
//     complet ecraserait une requalification arrivee entre-temps ;
//   * AUCUN bouton d'envoi n'existe. C'est P3-S3, et le test doit rendre cet
//     oubli difficile.
//
// `axios` est mocke : aucun appel reseau ne part de ces tests.
// `useChargement` est remplace par un pilote deterministe qui EXPOSE la source
// recue — on peut ainsi declencher `appel()` et verifier la requete reelle,
// sans dependre du minutage du vrai crochet (teste ailleurs).
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import ProspectsSection, { CATEGORIES, STATUTS, COLLABORATIONS } from '../ProspectsSection';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), patch: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));

const SECTION = {
  ATTENTE: 'attente', CHARGEMENT: 'chargement', OK: 'ok',
  ERREUR: 'erreur', SESSION: 'session',
};

// Le pilote : il retient la source declaree par l'ecran et rend l'etat qu'on
// lui demande. `mockDerniereSource` permet de rejouer l'appel reel.
// (Le prefixe `mock` est impose par le hoisting de `jest.mock`.)
let mockEtatPilote = { etat: SECTION.OK, donnees: null, motif: 'serveur' };
let mockDerniereSource = null;
const mockReessayer = jest.fn();

jest.mock('../../../hooks/useChargement', () => ({
  __esModule: true,
  SECTION: {
    ATTENTE: 'attente', CHARGEMENT: 'chargement', OK: 'ok',
    ERREUR: 'erreur', SESSION: 'session',
  },
  default: (sources) => {
    mockDerniereSource = sources.prospects;
    return {
      sections: { prospects: { etat: mockEtatPilote.etat, donnees: mockEtatPilote.donnees, motif: mockEtatPilote.motif } },
      reessayer: mockReessayer,
      global: mockEtatPilote.etat,
      donnees: {},
      cles: ['prospects'],
      chargement: mockEtatPilote.etat === 'chargement',
      sessionExpiree: mockEtatPilote.etat === 'session',
    };
  },
}));

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

let conteneur = null;
let racine = null;

async function monter(element) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(element); });
  return conteneur;
}

afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) document.body.removeChild(conteneur);
  racine = null;
  conteneur = null;
  jest.clearAllMocks();
  mockDerniereSource = null;
  mockEtatPilote = { etat: SECTION.OK, donnees: null, motif: 'serveur' };
});

const prospect = (sur) => Object.assign({
  id: 'p-1', ref: 'FES-01', organisation_name: "Festi'neuch", category: 'festival',
  city: 'Neuchâtel', address: 'Jeunes-Rives', website: 'festineuch.ch',
  instagram: '@festineuch', facebook: '', linkedin: '', tiktok: '',
  public_email: null, public_phone: null, contact_name: 'Resp. partenariats',
  contact_role: '', preferred_channel: 'Formulaire / DM', approach: '',
  score: 6.5, priority: 'B', wave: null, status: 'a_contacter',
  collaboration_type: null, notes: 'Idée de collaboration : Silent + QR',
  source_url: 'https://festineuch.ch', secondary_source_url: null,
  verified_at: null, j0_message: '', j3_message: '', j7_message: '',
  interested_message: '', first_contact_at: null, last_contact_at: null,
  next_followup_at: null, replied_at: null,
  partner_application_id: null, partner_id: null,
}, sur || {});

const reponse = (prospects, counts, total) => ({
  total: total === undefined ? prospects.length : total,
  returned: prospects.length,
  limit: 25,
  offset: 0,
  counts: Object.assign({
    a_contacter: 0, contacte: 0, repondu: 0, interesse: 0,
    sans_reponse_pause: 0, refuse: 0, total: prospects.length,
    candidature: 0, accepte: 0,
  }, counts || {}),
  prospects,
});

// React installe un traqueur sur `value` : ecrire `el.value = x` le met a jour
// et React conclut que rien n'a change — onChange n'est jamais appele. On passe
// donc par le setter NATIF, puis on emet l'evenement.
function saisir(element, valeur) {
  const prototype = element instanceof HTMLTextAreaElement
    ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototype, 'value').set;
  setter.call(element, valeur);
  element.dispatchEvent(new Event('input', { bubbles: true }));
}

const texte = () => conteneur.textContent;
const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const tous = (sel) => Array.from(conteneur.querySelectorAll(sel));

// ---------------------------------------------------------------------------
describe('P3-S2 — écran vide', () => {
  test("dit « aucun prospect », sans zéro trompeur ni spinner sans fin", async () => {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([]) };
    await monter(<ProspectsSection API="/api" />);
    expect(par('prospection-vide')).not.toBeNull();
    expect(texte()).toContain('Aucun prospect pour le moment');
    expect(texte()).not.toContain('Chargement des prospects');
    expect(conteneur.querySelector('table')).toBeNull();
  });

  test('avec filtres actifs, le message dit que ce sont les filtres', async () => {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([]) };
    await monter(<ProspectsSection API="/api" />);
    await act(async () => {
      const select = par('filtre-category');
      select.value = 'bar';
      select.dispatchEvent(new Event('change', { bubbles: true }));
    });
    expect(texte()).toContain('Aucun prospect ne correspond à ces filtres');
  });
});

describe('P3-S2 — chargement et erreurs', () => {
  test("pendant le chargement, l'écran ne montre ni 0 ni liste vide", async () => {
    mockEtatPilote = { etat: SECTION.CHARGEMENT, donnees: null };
    await monter(<ProspectsSection API="/api" />);
    expect(texte()).toContain('Chargement des prospects');
    expect(par('prospection-vide')).toBeNull();
    // Les tuiles disent « — », jamais « 0 » : on ne sait pas encore.
    expect(par('tuile-Total').textContent).toContain('—');
  });

  test('une erreur serveur est annoncée et rejouable', async () => {
    mockEtatPilote = { etat: SECTION.ERREUR, donnees: null, motif: 'serveur' };
    await monter(<ProspectsSection API="/api" />);
    expect(texte().toLowerCase()).toContain('prospects');
    expect(par('prospection-vide')).toBeNull();
  });

  test('une session expirée est annoncée comme telle, pas comme une liste vide', async () => {
    mockEtatPilote = { etat: SECTION.SESSION, donnees: null, motif: 'session' };
    await monter(<ProspectsSection API="/api" />);
    expect(par('prospection-vide')).toBeNull();
  });

  test("la source déclare une route authentifiée (portillon de signature)", async () => {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([]) };
    await monter(<ProspectsSection API="/api" />);
    expect(mockDerniereSource.url).toBe('/api/partner-prospects');
    expect(mockDerniereSource.signature).toBe(true);
  });
});

describe('P3-S2 — la liste', () => {
  test('une ligne montre les 10 colonnes utiles, et « — » pour ce qui manque', async () => {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([prospect()]) };
    await monter(<ProspectsSection API="/api" />);
    const ligne = par('ligne-FES-01');
    expect(ligne).not.toBeNull();
    expect(ligne.textContent).toContain("Festi'neuch");
    expect(ligne.textContent).toContain('Festival');
    expect(ligne.textContent).toContain('Neuchâtel');
    expect(ligne.textContent).toContain('6.5');
    expect(ligne.textContent).toContain('À contacter');
    // `next_followup_at` et `last_contact_at` sont nuls -> « — », pas vide.
    expect(ligne.textContent).toContain('—');
  });

  test('le tableau est masqué sur mobile, remplacé par des cartes', async () => {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([prospect()]) };
    await monter(<ProspectsSection API="/api" />);
    expect(conteneur.querySelector('.hidden.md\\:block')).not.toBeNull();
    expect(conteneur.querySelector('.md\\:hidden')).not.toBeNull();
    expect(par('carte-FES-01')).not.toBeNull();
  });

  test('les catégories affichées sont les libellés des clés du serveur', async () => {
    mockEtatPilote = {
      etat: SECTION.OK,
      donnees: reponse(CATEGORIES.map((c, i) => prospect({
        id: `p-${i}`, ref: `R-${i}`, category: c.cle, organisation_name: `Org ${i}`,
      }))),
    };
    await monter(<ProspectsSection API="/api" />);
    CATEGORIES.forEach((c) => expect(texte()).toContain(c.libelle));
  });
});

describe('P3-S2 — les compteurs', () => {
  test('les tuiles lisent counts du serveur, jamais la longueur de la page', async () => {
    mockEtatPilote = {
      etat: SECTION.OK,
      donnees: reponse([prospect()],
        { total: 80, a_contacter: 71, contacte: 6, repondu: 2, interesse: 1 }, 80),
    };
    await monter(<ProspectsSection API="/api" />);
    expect(par('tuile-Total').textContent).toContain('80');
    expect(par('tuile-À contacter').textContent).toContain('71');
    expect(par('tuile-Contacté').textContent).toContain('6');
    expect(par('tuile-Répondu').textContent).toContain('2');
    expect(par('tuile-Intéressé').textContent).toContain('1');
  });

  test('Candidatures et Acceptés viennent du serveur — aucun compteur P2 recopié', async () => {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([prospect()], { candidature: 0, accepte: 0 }) };
    await monter(<ProspectsSection API="/api" />);
    expect(par('tuile-Candidatures').textContent).toContain('0');
    expect(par('tuile-Acceptés').textContent).toContain('0');
  });

  test('les six statuts amont ont chacun leur tuile, et aucun statut P2', async () => {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([]) };
    await monter(<ProspectsSection API="/api" />);
    STATUTS.forEach((s) => expect(par(`tuile-${s.libelle}`)).not.toBeNull());
    ['Découverte', 'Actif', 'Ambassadeur'].forEach((mot) => {
      expect(texte()).not.toContain(mot);
    });
  });

  test('cliquer une tuile filtre sur ce statut', async () => {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([prospect()], { contacte: 3 }) };
    await monter(<ProspectsSection API="/api" />);
    await act(async () => { par('tuile-Contacté').click(); });
    expect(par('filtre-status').value).toBe('contacte');
  });
});

describe('P3-S2 — les filtres partent dans la requête', () => {
  async function requeteApres(action) {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([prospect()]) };
    await monter(<ProspectsSection API="/api" />);
    if (action) await act(async () => { action(); });
    axios.get.mockResolvedValue({ data: reponse([]) });
    await act(async () => { await mockDerniereSource.appel(); });
    return axios.get.mock.calls[0][1].params;
  }

  test('sans filtre : seulement limit et offset', async () => {
    const params = await requeteApres(null);
    expect(params.limit).toBe(25);
    expect(params.offset).toBe(0);
    expect(Object.keys(params).sort()).toEqual(['limit', 'offset']);
  });

  test('catégorie', async () => {
    const params = await requeteApres(() => {
      const s = par('filtre-category'); s.value = 'bar';
      s.dispatchEvent(new Event('change', { bubbles: true }));
    });
    expect(params.category).toBe('bar');
  });

  test('statut', async () => {
    const params = await requeteApres(() => {
      const s = par('filtre-status'); s.value = 'repondu';
      s.dispatchEvent(new Event('change', { bubbles: true }));
    });
    expect(params.status).toBe('repondu');
  });

  test('priorité', async () => {
    const params = await requeteApres(() => {
      const s = par('filtre-priority'); s.value = 'A';
      s.dispatchEvent(new Event('change', { bubbles: true }));
    });
    expect(params.priority).toBe('A');
  });

  test('vague', async () => {
    const params = await requeteApres(() => {
      saisir(par('filtre-wave'), 'Vague 1');
    });
    expect(params.wave).toBe('Vague 1');
  });

  test('ville', async () => {
    const params = await requeteApres(() => {
      saisir(par('filtre-city'), 'Neuchâtel');
    });
    expect(params.city).toBe('Neuchâtel');
  });

  test('un filtre vidé disparaît de la requête', async () => {
    const params = await requeteApres(() => {
      const s = par('filtre-category');
      s.value = 'bar';
      s.dispatchEvent(new Event('change', { bubbles: true }));
      s.value = '';
      s.dispatchEvent(new Event('change', { bubbles: true }));
    });
    expect(params.category).toBeUndefined();
  });
});

describe('P3-S2 — pagination', () => {
  test("la page suivante envoie un offset : sans lui, on ne verrait jamais les 51 à 80", async () => {
    mockEtatPilote = {
      etat: SECTION.OK,
      donnees: reponse(Array.from({ length: 25 }, (_, i) => prospect({ id: `p${i}`, ref: `R-${i}` })),
        { total: 80 }, 80),
    };
    await monter(<ProspectsSection API="/api" />);
    await act(async () => { par('page-suivante').click(); });
    axios.get.mockResolvedValue({ data: reponse([]) });
    await act(async () => { await mockDerniereSource.appel(); });
    expect(axios.get.mock.calls[0][1].params.offset).toBe(25);
  });

  test('« Précédent » est inactif sur la première page', async () => {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([prospect()], { total: 80 }, 80) };
    await monter(<ProspectsSection API="/api" />);
    expect(par('page-precedente').disabled).toBe(true);
  });

  test('« Suivant » est inactif quand tout est affiché', async () => {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([prospect()], { total: 1 }, 1) };
    await monter(<ProspectsSection API="/api" />);
    expect(par('page-suivante').disabled).toBe(true);
  });

  test('changer la taille de page revient à la première page', async () => {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([prospect()], { total: 80 }, 80) };
    await monter(<ProspectsSection API="/api" />);
    await act(async () => { par('page-suivante').click(); });
    await act(async () => {
      const s = par('filtre-taille'); s.value = '50';
      s.dispatchEvent(new Event('change', { bubbles: true }));
    });
    axios.get.mockResolvedValue({ data: reponse([]) });
    await act(async () => { await mockDerniereSource.appel(); });
    expect(axios.get.mock.calls[0][1].params.offset).toBe(0);
    expect(axios.get.mock.calls[0][1].params.limit).toBe(50);
  });
});

describe('P3-S2 — la fiche', () => {
  async function ouvrirFiche(sur) {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([prospect(sur)]) };
    await monter(<ProspectsSection API="/api" />);
    await act(async () => { par('ligne-FES-01').click(); });
    return par('fiche-prospect');
  }

  test("s'ouvre au clic et montre le détail", async () => {
    const fiche = await ouvrirFiche({ address: 'Jeunes-Rives 1', verified_at: '31.08.2026' });
    expect(fiche).not.toBeNull();
    expect(fiche.textContent).toContain("Festi'neuch");
    expect(fiche.textContent).toContain('FES-01');
    expect(fiche.textContent).toContain('Jeunes-Rives 1');
    expect(fiche.textContent).toContain('31.08.2026');
  });

  test('les liens externes sont cliquables, en nouvel onglet et sans opener', async () => {
    const fiche = await ouvrirFiche({ website: 'festineuch.ch', source_url: 'https://a.ch' });
    const liens = Array.from(fiche.querySelectorAll('a'));
    expect(liens.length).toBeGreaterThan(0);
    liens.forEach((a) => {
      expect(a.getAttribute('target')).toBe('_blank');
      expect(a.getAttribute('rel')).toBe('noopener noreferrer');
      expect(a.getAttribute('href')).toMatch(/^https?:\/\//);
    });
  });

  test("une coordonnée absente s'affiche « — », jamais « null »", async () => {
    const fiche = await ouvrirFiche({ public_email: null, wave: null });
    expect(fiche.textContent).not.toContain('null');
    expect(fiche.textContent).toContain('—');
  });

  test('les quatre messages sont affichés, en texte modifiable', async () => {
    const fiche = await ouvrirFiche({
      j0_message: 'Bonjour J0', j3_message: 'J3', j7_message: 'J7',
      interested_message: 'Si intéressé',
    });
    expect(par('edit-j0_message').value).toBe('Bonjour J0');
    expect(par('edit-j3_message').value).toBe('J3');
    expect(par('edit-j7_message').value).toBe('J7');
    expect(par('edit-interested_message').value).toBe('Si intéressé');
    expect(fiche.textContent).toContain('aucun envoi depuis cet écran');
  });

  test('se ferme', async () => {
    await ouvrirFiche();
    await act(async () => { par('fermer-fiche').click(); });
    expect(par('fiche-prospect')).toBeNull();
  });
});

describe('P3-S2 — édition', () => {
  async function ouvrir(sur) {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([prospect(sur)]) };
    await monter(<ProspectsSection API="/api" />);
    await act(async () => { par('ligne-FES-01').click(); });
  }

  test("n'envoie QUE les champs modifiés", async () => {
    await ouvrir();
    axios.patch.mockResolvedValue({ data: prospect({ status: 'contacte' }) });
    await act(async () => {
      const s = par('edit-status'); s.value = 'contacte';
      s.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await act(async () => { par('enregistrer-prospect').click(); });
    expect(axios.patch).toHaveBeenCalledTimes(1);
    const [url, corps] = axios.patch.mock.calls[0];
    expect(url).toBe('/api/partner-prospects/p-1');
    expect(corps).toEqual({ status: 'contacte' });
  });

  test('sans modification, aucun appel réseau', async () => {
    await ouvrir();
    await act(async () => { par('enregistrer-prospect').click(); });
    expect(axios.patch).not.toHaveBeenCalled();
    expect(par('message-fiche').textContent).toContain('Rien à enregistrer');
  });

  test('les champs de gestion attendus sont modifiables', async () => {
    await ouvrir();
    ['edit-status', 'edit-priority', 'edit-wave', 'edit-channel', 'edit-collaboration',
     'edit-email', 'edit-phone', 'edit-notes', 'edit-j0_message'].forEach((id) => {
      expect(par(id)).not.toBeNull();
    });
  });

  test('le choix de collaboration propose les valeurs du serveur, et « non défini »', async () => {
    await ouvrir();
    const options = Array.from(par('edit-collaboration').options).map((o) => o.value);
    expect(options).toEqual(COLLABORATIONS.map((c) => c.cle));
    expect(options).toContain('');
    expect(options).toContain('community');
    expect(options).toContain('event_programming');
  });

  test('un refus du serveur est affiché, pas avalé', async () => {
    await ouvrir();
    axios.patch.mockRejectedValue({ response: { data: { detail: 'Statut inconnu.' } } });
    await act(async () => {
      const s = par('edit-status'); s.value = 'refuse';
      s.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await act(async () => { par('enregistrer-prospect').click(); });
    expect(par('message-fiche').textContent).toContain('Statut inconnu.');
  });

  test('le statut proposé ne contient AUCUN statut partenaire P2', async () => {
    await ouvrir();
    const options = Array.from(par('edit-status').options).map((o) => o.value);
    expect(options).toEqual(STATUTS.map((s) => s.cle));
    ['decouverte', 'actif', 'ambassadeur'].forEach((s) => expect(options).not.toContain(s));
  });
});

describe('P3-S2 — ce que l’écran ne fait pas', () => {
  test('aucun bouton d’envoi nulle part — c’est P3-S3', async () => {
    mockEtatPilote = {
      etat: SECTION.OK,
      donnees: reponse([prospect({ j0_message: 'Bonjour', public_email: 'a@b.ch' })]),
    };
    await monter(<ProspectsSection API="/api" />);
    await act(async () => { par('ligne-FES-01').click(); });
    // « À contacter » est un STATUT, pas une action : on cherche un verbe
    // d'envoi EN TETE de libelle, jamais le mot n'importe ou dans la phrase.
    const boutons = tous('button').map((b) => b.textContent.trim().toLowerCase());
    boutons.forEach((libelle) => {
      expect(libelle).not.toMatch(/^(envoyer|relancer|contacter|send|notifier)\b/);
    });
    expect(boutons.length).toBeGreaterThan(0);
  });

  test('aucune création ni suppression : PATCH seulement', async () => {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([prospect()]) };
    await monter(<ProspectsSection API="/api" />);
    await act(async () => { par('ligne-FES-01').click(); });
    expect(axios.post).not.toHaveBeenCalled();
    expect(axios.delete).not.toHaveBeenCalled();
    expect(axios.put).not.toHaveBeenCalled();
  });

  test("n'interroge que la route des prospects", async () => {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([]) };
    await monter(<ProspectsSection API="/api" />);
    axios.get.mockResolvedValue({ data: reponse([]) });
    await act(async () => { await mockDerniereSource.appel(); });
    axios.get.mock.calls.forEach(([url]) => {
      expect(url).toBe('/api/partner-prospects');
    });
  });
});
