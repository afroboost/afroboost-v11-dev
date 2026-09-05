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
let mockSourcesDeclarees = null;
let mockEtatParSection = null;
const mockReessayer = jest.fn();

jest.mock('../../../hooks/useChargement', () => ({
  __esModule: true,
  SECTION: {
    ATTENTE: 'attente', CHARGEMENT: 'chargement', OK: 'ok',
    ERREUR: 'erreur', SESSION: 'session',
  },
  default: (sources) => {
    mockDerniereSource = sources.prospects;
    mockSourcesDeclarees = sources;
    const sections = {};
    Object.keys(sources).forEach((cle) => {
      const e = (mockEtatParSection && mockEtatParSection[cle]) || mockEtatPilote;
      sections[cle] = { etat: e.etat, donnees: e.donnees, motif: e.motif };
    });
    return {
      sections,
      reessayer: mockReessayer,
      global: mockEtatPilote.etat,
      donnees: {},
      cles: Object.keys(sources),
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
  mockSourcesDeclarees = null;
  mockEtatParSection = null;
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

/* GOOGLE-2 — DESIGNER UN APPEL PAR SA ROUTE, JAMAIS PAR SON RANG.
   L'ecran interroge desormais aussi `/api/google/status` ; un `calls[0]` ne
   designait donc plus la requete des prospects. Le rang etait deja fragile —
   il l'aurait ete au lot suivant de toute facon. */
function appelProspects() {
  const trouve = axios.get.mock.calls.find(
    ([url]) => String(url).includes('/partner-prospects'));
  if (!trouve) throw new Error('aucun appel a /partner-prospects');
  return trouve;
}

describe('P3-S2 — les filtres partent dans la requête', () => {
  async function requeteApres(action) {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([prospect()]) };
    await monter(<ProspectsSection API="/api" />);
    if (action) await act(async () => { action(); });
    axios.get.mockResolvedValue({ data: reponse([]) });
    await act(async () => { await mockDerniereSource.appel(); });
    return appelProspects()[1].params;
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
    expect(appelProspects()[1].params.offset).toBe(25);
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
    expect(appelProspects()[1].params.offset).toBe(0);
    expect(appelProspects()[1].params.limit).toBe(50);
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

// P3-S2C — LE CONTRASTE. Ce bloc existe parce que la version deployee etait
// ILLISIBLE : le composant ecrivait `color: inherit`, et le tableau de bord
// herite d'un `rgb(10,10,10)` (jeton shadcn CLAIR reste actif, classe `.dark`
// jamais posee) sur un fond NOIR — contraste mesure 1.06 en production.
// jsdom ne calcule pas l'heritage : aucun test ne pouvait le voir. On verifie
// donc la CAUSE — une couleur explicite a la racine — plutot que le pixel.
describe('P3-S2C — contraste', () => {
  test("la racine pose une couleur EXPLICITE, jamais 'inherit'", async () => {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([]) };
    await monter(<ProspectsSection API="/api" />);
    const racine = par('prospection-section');
    expect(racine.style.color).toBeTruthy();
    expect(racine.style.color).not.toBe('inherit');
  });

  test('aucune opacité de texte sous 0.5 — en dessous, le blanc sur noir passe sous 4.5:1', () => {
    const source = require('fs').readFileSync(
      require('path').join(__dirname, '..', 'ProspectsSection.js'), 'utf8');
    const trop_pales = (source.match(/opacity:\s*(0\.[0-4]\d*)\b/g) || []);
    expect(trop_pales).toEqual([]);
  });

  test('les champs de saisie posent leur couleur — un <option> est rendu par l’OS', async () => {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([]) };
    await monter(<ProspectsSection API="/api" />);
    ['filtre-category', 'filtre-status', 'filtre-wave'].forEach((id) => {
      expect(par(id).style.color).toBeTruthy();
      expect(par(id).style.color).not.toBe('inherit');
    });
  });

  // P3-S2D — le chiffre de la tuile ACTIVE etait ecrit dans la couleur de marque
  // BRUTE sur un fond teinte de cette meme couleur : 2.85:1 avec la couleur
  // mesuree en production (#9f2d70), sous le seuil << gros texte >> de 3:1.
  //
  // CES TROIS CONTROLES LISENT LA SOURCE, PAS LE DOM. jsdom ne stocke ni
  // `color-mix`, ni un `var()` place dans un raccourci `border`/`background`,
  // ni le mot-cle `inherit` : sonde a l'appui, `style.color`, `style.border` et
  // `style.background` reviennent tous vides. Le navigateur, lui, les applique.
  const SOURCE = require('fs').readFileSync(
    require('path').join(__dirname, '..', 'ProspectsSection.js'), 'utf8');

  test("le chiffre de la tuile active éclaircit la couleur de marque, sans en changer", () => {
    const decl = SOURCE.match(/const PRIMAIRE_LISIBLE = '([^']+)'/);
    expect(decl).not.toBeNull();
    // On part de la variable du coach : aucune couleur n'est figée.
    expect(decl[1]).toContain('var(--primary-color');
    // On l'éclaircit vers le blanc — pas vers une couleur sans rapport.
    expect(decl[1]).toContain('color-mix');
    expect(decl[1]).toContain('white');
    // Et c'est bien elle qu'utilise le chiffre de la tuile active.
    expect(SOURCE).toContain("color: actif ? PRIMAIRE_LISIBLE : 'inherit'");
  });

  test('les tuiles INACTIVES gardent leur chiffre hérité — rien d’autre ne change', () => {
    // Un seul endroit distingue actif / inactif pour la couleur du chiffre,
    // et l'inactif retombe sur l'héritage, donc sur le blanc de la racine.
    expect(SOURCE.match(/PRIMAIRE_LISIBLE/g)).toHaveLength(2); // la déclaration + l'usage
    expect(SOURCE).toContain("color: actif ? PRIMAIRE_LISIBLE : 'inherit'");
  });

  test('la bordure et le fond de la tuile active gardent la couleur de marque BRUTE', () => {
    // L'identité visuelle de l'état actif ne bouge pas : seul le chiffre change.
    expect(SOURCE).toContain("border: `1px solid ${actif ? PRIMAIRE : 'rgba(255,255,255,0.10)'}`");
    expect(SOURCE).toContain("background: actif ? `rgba(${RGB}, 0.16)`");
  });

  test('la fiche hérite de la racine, donc du texte lisible', async () => {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([prospect()]) };
    await monter(<ProspectsSection API="/api" />);
    await act(async () => { par('ligne-FES-01').click(); });
    const racine = par('prospection-section');
    expect(par('fiche-prospect')).not.toBeNull();
    expect(racine.contains(par('fiche-prospect'))).toBe(true);
    expect(racine.style.color).not.toBe('inherit');
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
    // GOOGLE-2 ajoute UN appel, et un seul : l'etat du droit d'ecriture Google,
    // qui commande l'affichage de la case « Synchroniser ». On le NOMME plutot
    // que d'assouplir l'assertion — toute autre route reste interdite.
    axios.get.mock.calls.forEach(([url]) => {
      expect(['/api/partner-prospects', '/api/google/status']).toContain(url);
    });
    const routes = axios.get.mock.calls.map(([u]) => u);
    expect(routes).toContain('/api/partner-prospects');
  });
});

// ---------------------------------------------------------------------------
// P3-S3-B — LA PREPARATION DE CAMPAGNE, VUE DU NAVIGATEUR.
//
// Ce que ces tests rendent difficile a casser :
//   * le PREMIER clic est une SIMULATION — s'il ecrivait, un clic curieux
//     creerait une campagne en production ;
//   * creer la campagne demande un SECOND clic, explicite ;
//   * deux clics sur « Creer » portent la MEME cle d'idempotence, donc le
//     serveur rend la campagne deja creee au lieu d'en fabriquer une jumelle ;
//   * exclure passe par un PATCH sur l'ACTION, jamais sur le prospect ;
//   * aucun bouton d'envoi n'apparait, meme campagne preparee.
// ---------------------------------------------------------------------------
const actionFictive = (sur) => Object.assign({
  id: 'a-1', recipient_key: 'GVA-F3', prospect_ids: ['GVA-F3', 'LSN-F3'],
  organisations: ['Wellness Genève', 'Wellness Lausanne'],
  cities: ['Genève', 'Lausanne'], category: 'fitness', priority: 'B',
  language: 'FR', channel: 'email', backup_channel: 'instagram',
  execution_type: 'AUTO', message_j0: 'Bonjour Wellness', statut: 'pret',
}, sur || {});

const resumeFictif = (sur) => Object.assign({
  destinataires: 2, exclus: 0, fiches: 3, multi_fiches: 1, sans_message_j0: 1,
  par_execution: { AUTO: 1, ASSISTE: 0, MANUEL: 1, BLOQUE: 0 },
  par_canal: { email: 1, instagram: 1 },
  par_langue: { FR: 2 },
}, sur || {});

const apercuFictif = () => ({
  dry_run: true,
  campaign: { id: 'c-1', nom: 'P3-LAUNCH-2', etat: 'preparee' },
  summary: resumeFictif(),
  actions: [actionFictive(), actionFictive({
    id: 'a-2', recipient_key: 'INF-01', prospect_ids: ['INF-01'],
    organisations: ['Coach Ikram'], cities: ['Neuchâtel'],
    channel: 'instagram', backup_channel: null, execution_type: 'MANUEL',
    message_j0: '',
  })],
});

async function ouvrirApercu() {
  mockEtatPilote = { etat: SECTION.OK, donnees: reponse([prospect()]) };
  axios.post.mockResolvedValue({ data: apercuFictif() });
  await monter(<ProspectsSection API="/api" />);
  await act(async () => { par('preparer-campagne').click(); });
}

describe('P3-S3-B — préparation de campagne', () => {
  test('le bandeau existe et rien n’est préparé au chargement', async () => {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([prospect()]) };
    await monter(<ProspectsSection API="/api" />);
    expect(par('bandeau-campagne')).not.toBeNull();
    expect(par('preparer-campagne')).not.toBeNull();
    expect(par('panneau-campagne')).toBeNull();
    expect(axios.post).not.toHaveBeenCalled();
  });

  test('le premier clic est une SIMULATION : dry_run true', async () => {
    await ouvrirApercu();
    expect(axios.post).toHaveBeenCalledTimes(1);
    const [url, corps] = axios.post.mock.calls[0];
    expect(url).toBe('/api/prospect-campaigns/prepare');
    expect(corps.dry_run).toBe(true);
  });

  test('le résumé affiche destinataires, exécution, canaux et langues', async () => {
    await ouvrirApercu();
    expect(par('panneau-campagne')).not.toBeNull();
    expect(par('resume-campagne').textContent).toContain('Destinataires');
    expect(par('resume-campagne').textContent).toContain('Automatique');
    expect(par('resume-campagne').textContent).toContain('Bloqué');
    expect(par('resume-canaux').textContent).toContain('E-mail');
    expect(par('resume-langues').textContent).toContain('FR');
    expect(par('resume-langues').textContent).toContain('sans message J0');
  });

  test('l’aperçu compact montre chaque destinataire sans ouvrir 137 fiches', async () => {
    await ouvrirApercu();
    expect(par('action-GVA-F3')).not.toBeNull();
    expect(par('action-INF-01')).not.toBeNull();
    // Les deux fiches d'un même destinataire tiennent sur UNE ligne.
    expect(par('action-GVA-F3').textContent).toContain('GVA-F3, LSN-F3');
    expect(par('action-GVA-F3').textContent).toContain('Bonjour Wellness');
    expect(par('action-INF-01').textContent).toContain('aucun message');
  });

  test('tant que c’est un aperçu, on ne peut ni exclure ni modifier', async () => {
    await ouvrirApercu();
    expect(par('exclure-GVA-F3')).toBeNull();
    expect(par('ouvrir-action-GVA-F3')).toBeNull();
    expect(par('creer-campagne')).not.toBeNull();
  });

  test('créer la campagne demande un SECOND clic, avec dry_run false', async () => {
    await ouvrirApercu();
    axios.post.mockResolvedValue({
      data: { dry_run: false, rejeu: false, campaign: { id: 'c-1', nom: 'P3-LAUNCH-2', etat: 'preparee' } },
    });
    axios.get.mockResolvedValue({
      data: { campaign: { id: 'c-1', nom: 'P3-LAUNCH-2', etat: 'preparee' },
              summary: resumeFictif(), actions: [actionFictive()] },
    });
    await act(async () => { par('creer-campagne').click(); });
    const dernier = axios.post.mock.calls[axios.post.mock.calls.length - 1][1];
    expect(dernier.dry_run).toBe(false);
    expect(dernier.idempotency_key).toBe('c-1');
    expect(par('message-campagne').textContent).toContain("Aucun message n'a été envoyé");
  });

  test('deux clics sur « Créer » portent la MÊME clé d’idempotence', async () => {
    await ouvrirApercu();
    axios.post.mockResolvedValue({
      data: { dry_run: false, rejeu: true, campaign: { id: 'c-1', nom: 'P3-LAUNCH-2', etat: 'preparee' } },
    });
    axios.get.mockResolvedValue({
      data: { campaign: { id: 'c-1', etat: 'preparee', nom: 'P3-LAUNCH-2' },
              summary: resumeFictif(), actions: [actionFictive()] },
    });
    await act(async () => { par('creer-campagne').click(); });
    // Le panneau n'est plus un aperçu : le bouton disparaît, donc pas de
    // troisième création possible par inadvertance.
    expect(par('creer-campagne')).toBeNull();
    const cles = axios.post.mock.calls.slice(1).map((c) => c[1].idempotency_key);
    expect(new Set(cles).size).toBe(1);
  });

  test('exclure passe par un PATCH sur l’ACTION, jamais sur le prospect', async () => {
    await ouvrirApercu();
    axios.post.mockResolvedValue({
      data: { dry_run: false, rejeu: false, campaign: { id: 'c-1', nom: 'X', etat: 'preparee' } },
    });
    axios.get.mockResolvedValue({
      data: { campaign: { id: 'c-1', nom: 'X', etat: 'preparee' },
              summary: resumeFictif(), actions: [actionFictive()] },
    });
    await act(async () => { par('creer-campagne').click(); });
    axios.patch.mockResolvedValue({
      data: { action: actionFictive({ statut: 'exclu' }),
              summary: resumeFictif({ destinataires: 1, exclus: 1 }) },
    });
    await act(async () => { par('exclure-GVA-F3').click(); });
    const [url, corps] = axios.patch.mock.calls[0];
    expect(url).toBe('/api/prospect-campaigns/c-1/actions/a-1');
    expect(corps).toEqual({ excluded: true });
    // Aucun PATCH n'est parti vers un prospect.
    axios.patch.mock.calls.forEach(([u]) => {
      expect(u).not.toContain('/partner-prospects/');
    });
  });

  test('la sélection envoie prospect_ids, et la case n’ouvre pas la fiche', async () => {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([prospect()]) };
    axios.post.mockResolvedValue({ data: apercuFictif() });
    await monter(<ProspectsSection API="/api" />);
    await act(async () => { par('choix-FES-01').click(); });
    expect(par('fiche-prospect')).toBeNull();          // le tiroir ne s'ouvre pas
    await act(async () => { par('preparer-campagne').click(); });
    expect(axios.post.mock.calls[0][1].prospect_ids).toEqual(['p-1']);
  });

  test('« Tout sélectionner » coche puis décoche toute la page', async () => {
    mockEtatPilote = {
      etat: SECTION.OK,
      donnees: reponse([prospect(), prospect({ id: 'p-2', ref: 'FES-02' })]),
    };
    await monter(<ProspectsSection API="/api" />);
    await act(async () => { par('tout-selectionner').click(); });
    expect(par('choix-FES-01').checked).toBe(true);
    expect(par('choix-FES-02').checked).toBe(true);
    await act(async () => { par('tout-selectionner').click(); });
    expect(par('choix-FES-01').checked).toBe(false);
  });

  test('AUCUN bouton d’envoi, même campagne préparée', async () => {
    await ouvrirApercu();
    axios.post.mockResolvedValue({
      data: { dry_run: false, rejeu: false, campaign: { id: 'c-1', nom: 'X', etat: 'preparee' } },
    });
    axios.get.mockResolvedValue({
      data: { campaign: { id: 'c-1', nom: 'X', etat: 'preparee' },
              summary: resumeFictif(), actions: [actionFictive()] },
    });
    await act(async () => { par('creer-campagne').click(); });
    tous('button').map((b) => b.textContent.trim().toLowerCase()).forEach((libelle) => {
      expect(libelle).not.toMatch(/^(envoyer|lancer|relancer|contacter|send|notifier)\b/);
    });
    // Et l'écran ne connaît aucune route d'envoi.
    const source = require('fs').readFileSync(
      require('path').join(__dirname, '..', 'ProspectsSection.js'), 'utf8');
    ['/send', '/launch', '/dispatch', '/execute', '/retry'].forEach((chemin) => {
      expect(source).not.toContain(chemin);
    });
    /* LA LISTE RESTE EXACTE — elle s'allonge seulement quand un POST est
       ajouté EN CONSCIENCE. CAL-3 en ajoute un troisième : planifier un
       rendez-vous. Ce n'est pas un envoi — il écrit dans le calendrier natif
       et ne touche ni au prospect, ni à la campagne, ni à Resend. On le NOMME
       plutôt que d'assouplir la comparaison : une garde de périmètre qui
       accepterait n'importe quoi ne garderait plus rien. */
    /* `[\s\S]*` et non `.*` : un appel écrit sur DEUX lignes (celui de
       l'analyse IA l'est) laissait sinon « axios.post(\n » collé devant le
       chemin, et le recensement accusait une route qui n'existe pas. Le point
       ne traverse pas les sauts de ligne en JavaScript. */
    const posts = (source.match(/axios\.post\(\s*`\$\{base\}([^`]*)`/g) || [])
      .map((m) => m.replace(/[\s\S]*\$\{base\}/, '').replace(/`[\s\S]*/, ''));
    /* READ-P1 / AI-P1 ajoutent TROIS POST, et on les nomme un par un.
       Aucun n'est un envoi : `/lu` enregistre que le coach a ouvert la
       réponse, `/traite` qu'il a agi dessus, `/analyser` range un brouillon
       sans rien expédier. Ils écrivent tous sur la réponse REÇUE — jamais sur
       une fiche prospect, jamais vers Resend. */
    expect(new Set(posts)).toEqual(new Set([
      '/prospect-campaigns/prepare',
      '/prospect-campaigns/${campagne.id}/approve',
      '/prospect-agenda/${encodeURIComponent(refOuverte)}/appointment',
      '/prospect-inbound/${encodeURIComponent(id)}/lu',
      '/prospect-inbound/${encodeURIComponent(id)}/traite',
      '/prospect-inbound/${encodeURIComponent(id)}/analyser',
    ]));
  });

  test('une erreur serveur est dite, sans casser l’écran', async () => {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([prospect()]) };
    axios.post.mockRejectedValue({ response: { data: { detail: 'Aucun prospect ne correspond' } } });
    await monter(<ProspectsSection API="/api" />);
    await act(async () => { par('preparer-campagne').click(); });
    expect(par('message-campagne')).not.toBeNull();
    expect(par('message-campagne').textContent).toContain('Aucun prospect ne correspond');
    expect(par('prospection-section')).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
// P3-S2F — LE DOUBLON VISUEL DESKTOP.
//
// Le defaut : `<div className="md:hidden" style={{ display: 'flex' }}>`.
// Un style EN LIGNE l'emporte sur n'importe quelle classe, media query
// comprise. `md:hidden` ne masquait donc jamais rien, et chaque prospect
// s'affichait DEUX fois sur desktop — une ligne de tableau et une carte.
// Mesure en production avant correctif : 25 lignes + 25 cartes.
//
// POURQUOI CES TESTS LISENT LA SOURCE PLUTOT QUE LE DOM.
// jsdom n'embarque pas la feuille Tailwind : `md:hidden` et `flex` n'y sont
// que des chaines de caracteres, et `getComputedStyle` renverrait le meme
// resultat AVANT et APRES le correctif. Un test DOM serait donc muet — c'est
// exactement pourquoi les 45 tests precedents n'ont pas vu le bug. On verifie
// donc la CAUSE STRUCTURELLE : aucune classe responsive ne doit etre
// contredite par un `display` en ligne. La preuve visuelle, elle, se fait au
// navigateur, a deux viewports reels.
describe('P3-S2F — responsive : une fiche ne s’affiche jamais deux fois', () => {
  const SRC_F = require('fs').readFileSync(
    require('path').join(__dirname, '..', 'ProspectsSection.js'), 'utf8');

  // Toutes les balises du fichier qui portent une classe responsive.
  const balisesResponsive = SRC_F.match(/<div className="[^"]*(?:md:hidden|md:block|hidden)[^"]*"[^>]*>/g) || [];

  test('les deux conteneurs responsive existent toujours', () => {
    expect(balisesResponsive.length).toBe(2);
    expect(SRC_F).toContain('className="hidden md:block"');   // le tableau
    expect(SRC_F).toContain('className="md:hidden flex"');    // les cartes
  });

  test('AUCUNE classe responsive n’est contredite par un display en ligne', () => {
    const fautives = balisesResponsive.filter((b) => /style=\{\{[^}]*display\s*:/.test(b));
    expect(fautives).toEqual([]);
  });

  test('les cartes tiennent leur display de la CLASSE, pas du style', () => {
    const carte = balisesResponsive.find((b) => b.includes('md:hidden'));
    expect(carte).toContain('flex');            // la classe porte le display
    expect(carte).not.toMatch(/display\s*:/);   // le style ne le porte plus
    // Le reste de la mise en page ne bouge pas : colonne + gouttiere.
    expect(carte).toContain("flexDirection: 'column'");
    expect(carte).toContain("gap: '8px'");
  });

  test('le tableau garde son défilement interne, sans display en ligne', () => {
    const table = balisesResponsive.find((b) => b.includes('hidden md:block'));
    expect(table).toContain("overflowX: 'auto'");
    expect(table).not.toMatch(/display\s*:/);
  });

  test('les deux conteneurs restent MUTUELLEMENT exclusifs', () => {
    // L'un se cache a partir de md, l'autre s'y montre : jamais les deux,
    // jamais aucun des deux.
    expect(SRC_F).toMatch(/className="hidden md:block"/);
    expect(SRC_F).toMatch(/className="md:hidden flex"/);
  });

  test('les deux rendus contiennent les MÊMES prospects — le doublon était visuel, pas des données', async () => {
    mockEtatPilote = {
      etat: SECTION.OK,
      donnees: reponse([prospect(), prospect({ id: 'p-2', ref: 'FES-02' })]),
    };
    await monter(<ProspectsSection API="/api" />);
    const refsLignes = tous('[data-testid^="ligne-"]').map((e) => e.getAttribute('data-testid'));
    const refsCartes = tous('[data-testid^="carte-"]').map((e) => e.getAttribute('data-testid'));
    expect(refsLignes).toEqual(['ligne-FES-01', 'ligne-FES-02']);
    expect(refsCartes).toEqual(['carte-FES-01', 'carte-FES-02']);
    // Deux rendus du MÊME jeu : 2 prospects, jamais 4.
    expect(new Set(refsLignes.concat(refsCartes).map((r) => r.split('-').slice(1).join('-'))).size).toBe(2);
  });

  test('sélectionner depuis la carte ne compte pas le prospect deux fois', async () => {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([prospect()]) };
    axios.post.mockResolvedValue({ data: apercuFictif() });
    await monter(<ProspectsSection API="/api" />);
    // La case vit dans la ligne de tableau ; le prospect n'a qu'un seul id.
    await act(async () => { par('choix-FES-01').click(); });
    await act(async () => { par('preparer-campagne').click(); });
    expect(axios.post.mock.calls[0][1].prospect_ids).toEqual(['p-1']);
  });
});

// ---------------------------------------------------------------------------
// P3-S3-C — ROUVRIR PLUTOT QUE RECREER, ET APPROUVER UNE FOIS.
//
// Le defaut ferme ici : l'ecran ne savait pas qu'une campagne existait deja.
// Il ne proposait que « Preparer », et deux preparations successives
// fabriquaient deux campagnes pour un seul lancement.
// ---------------------------------------------------------------------------
const campagneOuverteFictive = (sur) => Object.assign({
  id: 'c-1', nom: 'P3-LAUNCH-137', etat: 'preparee', nb_destinataires: 137,
  nb_fiches: 142, created_at: '2026-09-01T08:29:36.738198+00:00',
  approved_at: null, approved_by: null,
}, sur || {});

// `useChargement` est pilote : les DEUX sources recoivent le meme etat. On
// distingue donc les reponses par l'URL demandee dans `axios.get`.
function brancherDeuxSources(campagnes, prospects) {
  mockEtatPilote = { etat: SECTION.OK, donnees: null };
  axios.get.mockImplementation((url) => {
    if (String(url).includes('/prospect-campaigns/')) {
      return Promise.resolve({ data: {
        campaign: campagneOuverteFictive(), summary: resumeFictif(), actions: [actionFictive()],
      } });
    }
    if (String(url).includes('/prospect-campaigns')) {
      return Promise.resolve({ data: { total: campagnes.length, campaigns: campagnes } });
    }
    return Promise.resolve({ data: prospects });
  });
}

describe('P3-S3-C — réouverture et approbation', () => {
  test('l’écran demande les campagnes OUVERTES au chargement', async () => {
    brancherDeuxSources([], reponse([prospect()]));
    await monter(<ProspectsSection API="/api" />);
    // La source déclarée pointe bien vers les campagnes ouvertes.
    expect(SOURCE_C).toContain("params: { ouvertes: 1, limit: 5 }");
    expect(SOURCE_C).toContain('`${base}/prospect-campaigns`');
  });

  test('sans campagne ouverte, le bouton reste « Préparer la campagne »', async () => {
    mockEtatPilote = { etat: SECTION.OK, donnees: reponse([prospect()]) };
    await monter(<ProspectsSection API="/api" />);
    expect(par('campagne-ouverte')).toBeNull();
    expect(par('preparer-campagne').textContent).toContain('Préparer la campagne');
  });

  test('avec une campagne ouverte, l’écran propose « Ouvrir » et non « Créer »', async () => {
    mockEtatParSection = {
      prospects: { etat: SECTION.OK, donnees: reponse([prospect()]) },
      campagnes: { etat: SECTION.OK, donnees: { total: 1, campaigns: [campagneOuverteFictive()] } },
    };
    await monter(<ProspectsSection API="/api" />);
    const banniere = par('campagne-ouverte');
    expect(banniere).not.toBeNull();
    expect(banniere.textContent).toContain('P3-LAUNCH-137');
    expect(banniere.textContent).toContain('137 destinataires');
    expect(banniere.textContent).toContain('Campagne préparée');
    expect(banniere.textContent).toContain('2026-09-01');
    expect(banniere.textContent).toContain('0 envoyé');
    expect(par('ouvrir-campagne')).not.toBeNull();
    // « Préparer » devient secondaire, et le dit.
    expect(par('preparer-campagne').textContent).toContain('Préparer une autre campagne');
    // Aucun appel de préparation n'est parti tout seul.
    expect(axios.post).not.toHaveBeenCalled();
  });

  test('« Ouvrir » LIT la campagne existante — aucun POST, donc aucune création', async () => {
    mockEtatParSection = {
      prospects: { etat: SECTION.OK, donnees: reponse([prospect()]) },
      campagnes: { etat: SECTION.OK, donnees: { total: 1, campaigns: [campagneOuverteFictive()] } },
    };
    axios.get.mockResolvedValue({ data: {
      campaign: campagneOuverteFictive(), summary: resumeFictif(), actions: [actionFictive()],
    } });
    await monter(<ProspectsSection API="/api" />);
    await act(async () => { par('ouvrir-campagne').click(); });
    expect(axios.get).toHaveBeenCalledWith('/api/prospect-campaigns/c-1');
    expect(axios.post).not.toHaveBeenCalled();
    expect(par('panneau-campagne')).not.toBeNull();
    expect(par('creer-campagne')).toBeNull();          // ce n'est pas un aperçu
    expect(par('approuver-campagne')).not.toBeNull();  // c'est une campagne réelle
  });

  test('« Approuver » appelle /approve et n’envoie rien', async () => {
    mockEtatParSection = {
      prospects: { etat: SECTION.OK, donnees: reponse([prospect()]) },
      campagnes: { etat: SECTION.OK, donnees: { total: 1, campaigns: [campagneOuverteFictive()] } },
    };
    axios.get.mockResolvedValue({ data: {
      campaign: campagneOuverteFictive(), summary: resumeFictif(), actions: [actionFictive()],
    } });
    axios.post.mockResolvedValue({ data: {
      campaign: campagneOuverteFictive({ etat: 'approuvee', approved_at: '2026-09-01T10:00:00+00:00',
                                         approved_by: 'coach@test' }),
      summary: resumeFictif(), deja_approuvee: false,
    } });
    await monter(<ProspectsSection API="/api" />);
    await act(async () => { par('ouvrir-campagne').click(); });
    await act(async () => { par('approuver-campagne').click(); });
    expect(axios.post).toHaveBeenCalledWith('/api/prospect-campaigns/c-1/approve', {});
    expect(par('message-campagne').textContent).toContain("Aucun message n'a été envoyé");
    expect(par('envoi-desactive')).not.toBeNull();
  });

  test('après approbation, plus aucun bouton d’édition ni d’exclusion', async () => {
    mockEtatParSection = {
      prospects: { etat: SECTION.OK, donnees: reponse([prospect()]) },
      campagnes: { etat: SECTION.OK,
                   donnees: { total: 1, campaigns: [campagneOuverteFictive({ etat: 'approuvee' })] } },
    };
    axios.get.mockResolvedValue({ data: {
      campaign: campagneOuverteFictive({ etat: 'approuvee',
                                         approved_at: '2026-09-01T10:00:00+00:00' }),
      summary: resumeFictif(), actions: [actionFictive()],
    } });
    await monter(<ProspectsSection API="/api" />);
    await act(async () => { par('ouvrir-campagne').click(); });
    expect(par('exclure-GVA-F3')).toBeNull();
    expect(par('ouvrir-action-GVA-F3')).toBeNull();
    expect(par('approuver-campagne')).toBeNull();      // déjà approuvée
    expect(par('envoi-desactive')).not.toBeNull();
  });

  test('le filtre « langue non précisée » rend ces cas visibles avant tout envoi', async () => {
    mockEtatParSection = {
      prospects: { etat: SECTION.OK, donnees: reponse([prospect()]) },
      campagnes: { etat: SECTION.OK, donnees: { total: 1, campaigns: [campagneOuverteFictive()] } },
    };
    axios.get.mockResolvedValue({ data: {
      campaign: campagneOuverteFictive(), summary: resumeFictif(),
      actions: [actionFictive(),
                actionFictive({ id: 'a-2', recipient_key: 'BAR-09', prospect_ids: ['BAR-09'],
                                organisations: ['Les Brasseurs'], cities: ['Neuchâtel'],
                                language: '', message_j0: '', channel: 'aucun',
                                execution_type: 'BLOQUE', statut: 'bloque' })],
    } });
    await monter(<ProspectsSection API="/api" />);
    await act(async () => { par('ouvrir-campagne').click(); });
    expect(par('filtre-apercu-sans_langue').textContent).toContain('(1)');
    expect(par('action-GVA-F3')).not.toBeNull();
    await act(async () => { par('filtre-apercu-sans_langue').click(); });
    expect(par('action-BAR-09')).not.toBeNull();
    expect(par('action-GVA-F3')).toBeNull();           // filtré, pas supprimé
    await act(async () => { par('filtre-apercu-tous').click(); });
    expect(par('action-GVA-F3')).not.toBeNull();
  });

  test('AUCUN bouton d’envoi, même campagne approuvée', async () => {
    mockEtatParSection = {
      prospects: { etat: SECTION.OK, donnees: reponse([prospect()]) },
      campagnes: { etat: SECTION.OK,
                   donnees: { total: 1, campaigns: [campagneOuverteFictive({ etat: 'approuvee' })] } },
    };
    axios.get.mockResolvedValue({ data: {
      campaign: campagneOuverteFictive({ etat: 'approuvee',
                                         approved_at: '2026-09-01T10:00:00+00:00' }),
      summary: resumeFictif(), actions: [actionFictive()],
    } });
    await monter(<ProspectsSection API="/api" />);
    await act(async () => { par('ouvrir-campagne').click(); });
    tous('button').map((b) => b.textContent.trim().toLowerCase()).forEach((libelle) => {
      expect(libelle).not.toMatch(/^(envoyer|lancer|relancer|contacter|send|notifier)\b/);
    });
  });
});

const SOURCE_C = require('fs').readFileSync(
  require('path').join(__dirname, '..', 'ProspectsSection.js'), 'utf8');

/* ==========================================================================
   P3-U3 — LES RÉPONSES REÇUES DEVIENNENT VISIBLES

   Le moteur U2 stockait les réponses, la route les rendait, et l'écran ne les
   demandait pas : une réponse invisible est une réponse perdue. Ce panneau
   répond à UNE question — « qui nous a répondu, et est-ce rattaché au bon
   prospect ? » — et rien de plus. Ce n'est pas une messagerie.
   ========================================================================== */

const reponseFictive = (extra = {}) => ({
  id: 'msg-1',
  campaign_id: 'camp-abcdef12',
  action_id: 'act-1',
  recipient_key: 'BAR-01',
  from_email: 'hotel@beaulac.exemple.test',
  to_email: 'contact@reply.afroboosteur.com',
  subject: 'Re: Proposition de collaboration avec Afroboost',
  body_text: 'Bonjour, cela nous intéresse beaucoup.',
  received_at: '2026-09-02T11:00:00+00:00',
  matching_method: 'A_IN_REPLY_TO',
  matching_confidence: 100,
  statut: 'rattache',
  motif: '',
  ...extra,
});

describe('P3-U3 — les réponses reçues', () => {
  /* READ-P1 : le serveur rend DEUX compteurs à côté des messages. Le faux les
     dérive de la même page pour rester fidèle — mais l'écran, lui, ne les
     recalcule jamais : il affiche ce que le serveur a compté sur la portée
     complète du coach, pagination comprise. */
  const avecReponses = (messages, en_attente = 0) => {
    mockEtatParSection = {
      prospects: { etat: SECTION.OK, donnees: reponse([prospect()]) },
      campagnes: { etat: SECTION.OK, donnees: { total: 0, campaigns: [] } },
      reponses: { etat: SECTION.OK,
                  donnees: { messages, total: messages.length, en_attente,
                             non_lues: messages.filter((m) => !m.read_at).length,
                             a_repondre: messages.filter((m) => !m.traite_at).length } },
    };
  };

  /* AI-P2 — OUVRIR UNE CARTE. Le détail (email original, corrélation, brouillon)
     n'existe plus dans la carte FERMÉE : il est derrière « Voir la réponse ».
     Ce helper fait ce que le coach fait, pour que les vérifications portent sur
     ce qu'il voit vraiment. */
  const ouvrirCarte = async (indice = 0) => {
    axios.post.mockResolvedValue({ data: { ok: true, non_lues: 0, a_repondre: 1 } });
    axios.get.mockResolvedValue({ data: { brouillon: null } });
    await act(async () => { tous('[data-testid="voir-reponse"]')[indice].click(); });
  };

  test('l’écran DEMANDE les réponses au chargement', async () => {
    avecReponses([]);
    await monter(<ProspectsSection API="/api" />);
    expect(mockSourcesDeclarees.reponses).toBeDefined();
    expect(mockSourcesDeclarees.reponses.url).toContain('/prospect-inbound');
  });

  test('tant que personne n’a répondu, le panneau ne s’affiche pas', async () => {
    avecReponses([]);
    await monter(<ProspectsSection API="/api" />);
    expect(document.querySelector('[data-testid="reponses-recues"]')).toBeNull();
  });

  /* AI-P2 SÉPARE CE QUI SE LIT EN TROIS SECONDES DE CE QUI SE CONSULTE.
     La carte fermée répond à « qui, quand, quoi faire ». Le sujet, le corps
     complet et le diagnostic de corrélation ne DISPARAISSENT pas — ils passent
     derrière « Voir la réponse », parce qu'affichés en permanence ils noyaient
     les six lignes utiles sous un bloc d'email brut. */
  test('la carte FERMÉE dit qui a répondu et quand', async () => {
    avecReponses([reponseFictive()]);
    await monter(<ProspectsSection API="/api" />);
    const panneau = par('reponses-recues');
    expect(panneau).toBeTruthy();
    expect(panneau.textContent).toContain('BAR-01');
    expect(panneau.textContent).toContain('hotel@beaulac.exemple.test');
    expect(panneau.textContent).toContain('2026-09-02');
  });

  test('la carte OUVERTE porte le sujet, le corps entier et la corrélation', async () => {
    avecReponses([reponseFictive()]);
    await monter(<ProspectsSection API="/api" />);
    await ouvrirCarte();
    const panneau = par('reponses-recues');
    expect(panneau.textContent).toContain('Proposition de collaboration');
    expect(par('corps-original').textContent).toContain('cela nous intéresse');
    // 8 caractères, comme l'écran les tronque — `camp-abcdef12` -> `camp-abc`.
    expect(panneau.textContent).toContain('campagne camp-abc');
  });

  test('l’email original est REPLIÉ par défaut, jamais un bloc permanent', async () => {
    avecReponses([reponseFictive()]);
    await monter(<ProspectsSection API="/api" />);
    await ouvrirCarte();
    const details = par('email-original');
    expect(details.tagName.toLowerCase()).toBe('details');
    expect(details.hasAttribute('open')).toBe(false);
    expect(details.querySelector('summary').textContent).toContain('Voir l’email original');
  });

  test('méthode et confiance restent consultables — dans le détail, pas sur la carte', async () => {
    avecReponses([reponseFictive()]);
    await monter(<ProspectsSection API="/api" />);
    // Du diagnostic : utile quand quelque chose cloche, illisible quand tout va bien.
    expect(par('reponses-recues').textContent).not.toContain('A_IN_REPLY_TO');
    await ouvrirCarte();
    expect(par('email-original').textContent).toContain('A_IN_REPLY_TO');
    expect(par('email-original').textContent).toContain('100');
  });

  test('un message ambigu est montré comme À RATTACHER, avec son motif', async () => {
    avecReponses([reponseFictive({
      statut: 'manual_review', action_id: null, recipient_key: null,
      matching_method: 'AUCUNE', matching_confidence: 0,
      motif: 'plusieurs actions pourraient correspondre — un humain tranche',
    })], 1);
    await monter(<ProspectsSection API="/api" />);
    // Le BADGE alerte sur la carte fermée ; le motif détaillé est dans le détail.
    expect(par('badge-a-rattacher')).toBeTruthy();
    await ouvrirCarte();
    expect(par('email-original').textContent).toContain('à rattacher');
    expect(par('email-original').textContent).toContain('plusieurs actions');
    expect(par('reponses-recues').textContent).toContain('Prospect à identifier');
    expect(par('reponses-en-attente').textContent).toContain('1');
  });

  test('le corps est rendu en TEXTE — aucun HTML d’un inconnu n’est injecté', async () => {
    avecReponses([reponseFictive({
      body_text: '<script>alert(1)</script><b>gras</b>',
      subject: '<img src=x onerror=alert(2)>',
    })]);
    await monter(<ProspectsSection API="/api" />);
    const panneau = par('reponses-recues');
    expect(panneau.querySelector('script')).toBeNull();
    expect(panneau.querySelector('b')).toBeNull();
    expect(panneau.querySelector('img')).toBeNull();
    expect(panneau.textContent).toContain('<script>alert(1)</script>');
  });

  test('un message long ne déroule pas la carte fermée', async () => {
    avecReponses([reponseFictive({ body_text: 'x'.repeat(400) })]);
    await monter(<ProspectsSection API="/api" />);
    // Sans analyse IA, la carte montre au plus deux lignes du message réel.
    expect(par('carte-sans-analyse').textContent.length).toBeLessThanOrEqual(160);
    expect(par('reponses-recues').textContent).not.toContain('x'.repeat(200));
    // Et le texte entier reste accessible, une fois la carte ouverte.
    await ouvrirCarte();
    expect(par('corps-original').textContent).toContain('x'.repeat(400));
  });

  test('plusieurs réponses sont listées, une ligne chacune', async () => {
    avecReponses([reponseFictive(),
                  reponseFictive({ id: 'msg-2', recipient_key: 'BAR-02' })]);
    await monter(<ProspectsSection API="/api" />);
    expect(tous('[data-testid="reponse-ligne"]').length).toBe(2);
  });

  /* AI-P1 A DONNÉ DES BOUTONS À CE PANNEAU, ET LA GARDE CHANGE DE FORME.
     Exiger ZÉRO bouton était la façon la plus simple de prouver « rien ne
     part d'ici » tant que le panneau était une liste morte. Il est devenu un
     outil de travail : on ouvre une réponse, on l'analyse, on la marque
     traitée. Ce qui doit rester vrai n'est donc plus « aucun bouton » mais
     « aucun bouton n'EXPÉDIE quoi que ce soit » — et cela se vérifie sur les
     libellés ET sur les routes, pas sur un décompte. */
  test('AUCUN bouton n’expédie quoi que ce soit depuis ce panneau', async () => {
    avecReponses([reponseFictive()]);
    await monter(<ProspectsSection API="/api" />);
    const libelles = [...par('reponses-recues').querySelectorAll('button')]
      .map((b) => b.textContent.trim().toLowerCase());
    expect(libelles.length).toBeGreaterThan(0);
    libelles.forEach((libelle) => {
      expect(libelle).not.toMatch(/envoyer|expédier|répondre au|relancer|contacter|send/);
    });
    // Et le panneau ne connaît aucune route d'envoi.
    /* LE MARQUEUR VISE LE RENDU, PAS UN COMMENTAIRE. « LES RÉPONSES REÇUES »
       apparaît d'abord dans la prose qui décrit la source `useChargement` :
       la découpe démarrait 500 lignes trop haut et jugeait du code étranger au
       panneau. `data-testid` n'existe, lui, que dans le JSX. */
    const bloc = SOURCE_C.slice(SOURCE_C.indexOf('data-testid="reponses-recues"'),
                                SOURCE_C.indexOf('{messageCampagne &&'));
    ['/send', '/launch', '/dispatch', '/execute', '/retry', 'resend']
      .forEach((chemin) => { expect(bloc).not.toContain(chemin); });
  });

  test('une réponse jamais ouverte porte NOUVEAU et À RÉPONDRE', async () => {
    avecReponses([reponseFictive()]);
    await monter(<ProspectsSection API="/api" />);
    expect(par('badge-nouveau')).toBeTruthy();
    expect(par('badge-a-repondre')).toBeTruthy();
    expect(par('badge-traite')).toBeFalsy();
  });

  test('une réponse déjà ouverte perd NOUVEAU mais garde À RÉPONDRE', async () => {
    avecReponses([reponseFictive({ read_at: '2026-09-05T10:00:00Z' })]);
    await monter(<ProspectsSection API="/api" />);
    expect(par('badge-nouveau')).toBeFalsy();
    expect(par('badge-a-repondre')).toBeTruthy();
  });

  test('une réponse traitée porte TRAITÉ, plus À RÉPONDRE', async () => {
    avecReponses([reponseFictive({ read_at: '2026-09-05T10:00:00Z',
                                   traite_at: '2026-09-05T11:00:00Z' })]);
    await monter(<ProspectsSection API="/api" />);
    expect(par('badge-traite')).toBeTruthy();
    expect(par('badge-a-repondre')).toBeFalsy();
  });

  test('AFFICHER la liste n’appelle JAMAIS la route de lecture', async () => {
    avecReponses([reponseFictive()]);
    await monter(<ProspectsSection API="/api" />);
    const appels = axios.post.mock.calls.map((c) => String(c[0]));
    expect(appels.some((u) => u.includes('/lu'))).toBe(false);
  });

  /* ======================================================================
     AI-P2 — TROIS CARTES AFFICHÉES EN MÊME TEMPS, AUCUN ÉTAT PARTAGÉ.

     C'est LE test de ce lot. Trois partenaires ont répondu le même jour, au
     même objet, sur la même campagne ; un état global (`ouvert`, `brouillon`,
     `edition`) ferait apparaître le texte de l'un sur la carte de l'autre.
     Tout est indexé par `message.id` — ces tests le prouvent en manipulant
     une carte et en vérifiant que les deux autres n'ont pas bougé.
     ====================================================================== */
  const TROIS = () => [
    reponseFictive({ id: 'inb-etu04', recipient_key: 'ETU-04',
                     from_email: 'info@bde-hearc.ch',
                     body_text: 'Cela nous semble intéressant, ça consiste en quoi ?' }),
    reponseFictive({ id: 'inb-lsna3', recipient_key: 'LSN-A3',
                     from_email: 'eveline.sautaux@assoacd.org',
                     body_text: 'Ndongo Beye est joignable au 076.' }),
    reponseFictive({ id: 'inb-zrhd5', recipient_key: 'ZRH-D5',
                     from_email: 'info@salsarica.ch',
                     body_text: 'Danke, aber wir sind nicht interessiert.' }),
  ];

  const brouillonDe = (extra = {}) => ({
    id: 'b-1', inbound_id: 'inb-etu04', action_id: 'act-1',
    organisation: 'BDE HE-ARC', to_email: 'info@bde-hearc.ch',
    intention: 'question', langue: 'fr', version: 1,
    resume: 'Le BDE trouve l’idée intéressante et demande des précisions.',
    demande: 'Comprendre en quoi consiste Afroboost.',
    prochaine_action: 'Répondre et proposer un échange.',
    reponse_proposee: 'Bonjour, merci pour votre intérêt. Bassi',
    validation_requise: false, motifs_validation: [], ...extra,
  });

  test('ouvrir ETU-04 laisse LSN-A3 et ZRH-D5 FERMÉES', async () => {
    avecReponses(TROIS());
    await monter(<ProspectsSection API="/api" />);
    expect(tous('[data-testid="voir-reponse"]').length).toBe(3);
    await ouvrirCarte(0);
    // Une seule carte déplie son détail.
    expect(tous('[data-testid="email-original"]').length).toBe(1);
    const libelles = tous('[data-testid="voir-reponse"]').map((b) => b.textContent.trim());
    expect(libelles).toEqual(['Replier', 'Voir la réponse', 'Voir la réponse']);
  });

  test('marquer ETU-04 lu n’appelle la route QUE pour ETU-04', async () => {
    avecReponses(TROIS());
    await monter(<ProspectsSection API="/api" />);
    await ouvrirCarte(0);
    const appels = axios.post.mock.calls.map((c) => String(c[0]));
    expect(appels.filter((u) => u.includes('/lu'))).toEqual(['/api/prospect-inbound/inb-etu04/lu']);
  });

  test('le brouillon d’ETU-04 ne s’affiche QUE sur la carte d’ETU-04', async () => {
    avecReponses(TROIS());
    await monter(<ProspectsSection API="/api" />);
    axios.post.mockResolvedValue({ data: { ok: true, non_lues: 2, a_repondre: 3 } });
    axios.get.mockResolvedValue({ data: { brouillon: brouillonDe() } });
    await act(async () => { tous('[data-testid="voir-reponse"]')[0].click(); });
    expect(tous('[data-testid="reponse-proposee"]').length).toBe(1);
    expect(par('reponse-proposee').textContent).toContain('merci pour votre intérêt');
    // La carte de LSN-A3 ne porte ni brouillon, ni intention, ni résumé.
    const cartes = tous('[data-testid="reponse-ligne"]');
    expect(cartes[1].textContent).not.toContain('merci pour votre intérêt');
    expect(cartes[1].textContent).not.toContain('BDE HE-ARC');
    expect(cartes[2].textContent).not.toContain('BDE HE-ARC');
  });

  test('modifier le brouillon d’ETU-04 ne touche pas les autres cartes', async () => {
    avecReponses(TROIS());
    await monter(<ProspectsSection API="/api" />);
    axios.post.mockResolvedValue({ data: { ok: true, non_lues: 2, a_repondre: 3 } });
    axios.get.mockResolvedValue({ data: { brouillon: brouillonDe() } });
    await act(async () => { tous('[data-testid="voir-reponse"]')[0].click(); });
    await act(async () => { par('modifier-brouillon').click(); });
    const zone = par('editeur-brouillon');
    expect(zone.value).toContain('merci pour votre intérêt');
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')
        .set.call(zone, 'TEXTE CORRIGÉ À LA MAIN');
      zone.dispatchEvent(new Event('input', { bubbles: true }));
    });
    expect(par('editeur-brouillon').value).toBe('TEXTE CORRIGÉ À LA MAIN');
    // Une seule zone d'édition existe, et les deux autres cartes sont intactes.
    expect(tous('[data-testid="editeur-brouillon"]').length).toBe(1);
    const cartes = tous('[data-testid="reponse-ligne"]');
    expect(cartes[1].textContent).not.toContain('TEXTE CORRIGÉ');
    expect(cartes[2].textContent).not.toContain('TEXTE CORRIGÉ');
  });

  test('enregistrer une correction passe par PATCH, jamais par un envoi', async () => {
    avecReponses(TROIS());
    await monter(<ProspectsSection API="/api" />);
    axios.post.mockResolvedValue({ data: { ok: true, non_lues: 2, a_repondre: 3 } });
    axios.get.mockResolvedValue({ data: { brouillon: brouillonDe() } });
    await act(async () => { tous('[data-testid="voir-reponse"]')[0].click(); });
    await act(async () => { par('modifier-brouillon').click(); });
    axios.patch.mockResolvedValue({
      data: { brouillon: brouillonDe({ reponse_proposee: 'CORRIGÉ' }) } });
    await act(async () => { par('enregistrer-brouillon').click(); });
    expect(axios.patch).toHaveBeenCalledWith(
      '/api/prospect-inbound/inb-etu04/brouillon',
      { reponse_proposee: 'Bonjour, merci pour votre intérêt. Bassi' });
    expect(par('reponse-proposee').textContent).toContain('CORRIGÉ');
  });

  test('un brouillon EXISTANT est affiché sans relancer l’IA', async () => {
    avecReponses([reponseFictive({ id: 'inb-etu04' })]);
    await monter(<ProspectsSection API="/api" />);
    axios.post.mockResolvedValue({ data: { ok: true, non_lues: 0, a_repondre: 1 } });
    axios.get.mockResolvedValue({ data: { brouillon: brouillonDe() } });
    await act(async () => { par('voir-reponse').click(); });
    // Aucun POST /analyser : ouvrir ne coûte pas un appel au modèle.
    const appels = axios.post.mock.calls.map((c) => String(c[0]));
    expect(appels.some((u) => u.includes('/analyser'))).toBe(false);
    expect(par('analyser-ia').textContent.trim()).toBe('Régénérer');
  });

  test('sans brouillon, l’écran PROPOSE de générer — il ne génère pas tout seul', async () => {
    avecReponses([reponseFictive({ id: 'inb-etu04' })]);
    await monter(<ProspectsSection API="/api" />);
    await ouvrirCarte();
    const appels = axios.post.mock.calls.map((c) => String(c[0]));
    expect(appels.some((u) => u.includes('/analyser'))).toBe(false);
    expect(par('analyser-ia').textContent.trim()).toBe('Générer une réponse avec l’IA');
  });

  test('l’IA en panne laisse la carte utilisable', async () => {
    avecReponses([reponseFictive({ id: 'inb-etu04', recipient_key: 'ETU-04' })]);
    await monter(<ProspectsSection API="/api" />);
    await ouvrirCarte();
    axios.post.mockRejectedValue({
      response: { data: { detail: 'Analyse indisponible (OPENAI_API_KEY absente)' } } });
    await act(async () => { par('analyser-ia').click(); });
    expect(par('erreur-ia').textContent).toContain('Analyse indisponible');
    // Rien n'est cassé : organisation, adresse, message et statut restent là.
    const carte = par('reponse-ligne');
    expect(carte.textContent).toContain('ETU-04');
    expect(carte.textContent).toContain('hotel@beaulac.exemple.test');
    expect(par('corps-original')).toBeTruthy();
    expect(par('badge-a-repondre')).toBeTruthy();
  });

  test('les quatre tons de régénération ne partent qu’avec un brouillon', async () => {
    avecReponses([reponseFictive({ id: 'inb-etu04' })]);
    await monter(<ProspectsSection API="/api" />);
    await ouvrirCarte();
    expect(par('ton-court')).toBeFalsy();          // rien à régénérer encore
    axios.post.mockResolvedValue({ data: { brouillon: brouillonDe() } });
    await act(async () => { par('analyser-ia').click(); });
    ['court', 'chaleureux', 'professionnel', 'direct']
      .forEach((t) => expect(par(`ton-${t}`)).toBeTruthy());
    await act(async () => { par('ton-court').click(); });
    expect(axios.post).toHaveBeenCalledWith(
      '/api/prospect-inbound/inb-etu04/analyser', { ton: 'court' });
  });

  test('AUCUN bouton d’envoi : l’écran le DIT au lieu de le mimer', async () => {
    avecReponses([reponseFictive({ id: 'inb-etu04' })]);
    await monter(<ProspectsSection API="/api" />);
    await ouvrirCarte();
    expect(par('envoi-a-venir').textContent).toContain('Envoi disponible prochainement');
    expect(par('envoi-a-venir').tagName.toLowerCase()).toBe('span');   // pas un bouton
  });

  test('MOBILE — rien ne peut déborder horizontalement', async () => {
    avecReponses(TROIS());
    await monter(<ProspectsSection API="/api" />);
    /* LE MARQUEUR VISE LE RENDU, PAS UN COMMENTAIRE. « LES RÉPONSES REÇUES »
       apparaît d'abord dans la prose qui décrit la source `useChargement` :
       la découpe démarrait 500 lignes trop haut et jugeait du code étranger au
       panneau. `data-testid` n'existe, lui, que dans le JSX. */
    const bloc = SOURCE_C.slice(SOURCE_C.indexOf('data-testid="reponses-recues"'),
                                SOURCE_C.indexOf('{messageCampagne &&'));
    // Aucune largeur fixe, aucune colonne rigide, aucun défilement latéral.
    expect(bloc).not.toMatch(/width:\s*'\d+px'/);
    expect(bloc).not.toMatch(/minWidth:\s*'\d{3,}px'/);
    expect(bloc).not.toContain('overflowX');
    expect(bloc).not.toContain('whiteSpace: \'nowrap\', width');
    // L'adresse, seule chaîne insécable, est bornée par une ellipse.
    expect(bloc).toContain("textOverflow: 'ellipsis'");
    expect(bloc).toContain("maxWidth: '100%'");
    // Et tout ce qui s'aligne se replie.
    expect((bloc.match(/flexWrap: 'wrap'/g) || []).length).toBeGreaterThanOrEqual(5);
  });

  test('« Voir la réponse » est le SEUL chemin qui marque comme lu', async () => {
    avecReponses([reponseFictive()]);
    await monter(<ProspectsSection API="/api" />);
    axios.post.mockResolvedValue({ data: { ok: true, non_lues: 0, a_repondre: 1 } });
    axios.get.mockResolvedValue({ data: { brouillon: null } });
    await act(async () => { par('voir-reponse').click(); });
    const appels = axios.post.mock.calls.map((c) => String(c[0]));
    expect(appels.filter((u) => u.includes('/lu')).length).toBe(1);
  });

  test('le panneau n’utilise aucune couleur codée en dur', () => {
    /* Le marqueur ne nomme plus UN lot : READ-P1 et AI-P1 se sont ajoutés au
       même bandeau, et un marqueur qui épelle la liste des lots casse à chaque
       nouveau. On vise ce qui ne bougera pas : le titre du panneau. */
    /* LE MARQUEUR VISE LE RENDU, PAS UN COMMENTAIRE. « LES RÉPONSES REÇUES »
       apparaît d'abord dans la prose qui décrit la source `useChargement` :
       la découpe démarrait 500 lignes trop haut et jugeait du code étranger au
       panneau. `data-testid` n'existe, lui, que dans le JSX. */
    const bloc = SOURCE_C.slice(SOURCE_C.indexOf('data-testid="reponses-recues"'),
                                SOURCE_C.indexOf('{messageCampagne &&'));
    const hex = bloc.match(/#[0-9a-fA-F]{6}/g) || [];
    expect(hex).toEqual([]);
    expect(bloc).toContain('RGB');
  });
});

/* ==========================================================================
   CAL-3 — PLANIFIER DEPUIS UNE FICHE PROSPECT

   Le maillon qui manquait entre P3 et le calendrier : un prospect qui répond
   « appelez-moi jeudi à 14 h » peut enfin être planifié. Ce qui est prouvé ici :

     * le bouton existe et n'ouvre son formulaire que sur demande ;
     * la création part sur `/prospect-agenda/{ref}/appointment` — la route du
       calendrier, pas une seconde ;
     * le prochain rendez-vous et les tâches ouvertes s'affichent ;
     * une tâche terminée n'apparaît PAS dans les tâches ouvertes ;
     * la fiche prospect n'est JAMAIS modifiée par une planification ;
     * l'agenda est chargé à l'ouverture de la fiche, pas pour les 142 lignes.
   ========================================================================== */

const agendaFictif = (extra = {}) => ({
  reference: 'FES-01', recipient_key: 'FES-01',
  campaign_id: 'camp-1', campaign_action_id: 'act-1',
  next_appointment: null, appointments: [], open_tasks: [],
  meeting_types: ['appel', 'visio', 'rencontre', 'autre'],
  durations: [15, 30, 45, 60, 90, 120], ...extra,
});

const rdvFictif = (extra = {}) => ({
  id: 'rdv-1', title: 'Appel partenariat — Festival du Lac',
  starts_at: '2026-09-10T14:00:00+00:00', event_type: 'appointment',
  status: 'prevu', meeting_type: 'appel', modifiable: true, ...extra,
});

describe('CAL-3 — planifier depuis la fiche', () => {
  const ouvrirFiche = async (agenda = agendaFictif()) => {
    mockEtatParSection = {
      prospects: { etat: SECTION.OK, donnees: reponse([prospect({ ref: 'FES-01' })]) },
      campagnes: { etat: SECTION.OK, donnees: { total: 0, campaigns: [] } },
      reponses: { etat: SECTION.OK, donnees: { messages: [], total: 0, en_attente: 0 } },
    };
    axios.get.mockResolvedValue({ data: agenda });
    axios.post.mockResolvedValue({ data: { appointment: rdvFictif() } });
    await monter(<ProspectsSection API="/api" />);
    await act(async () => { par('ligne-FES-01').click(); });
  };

  test('l’agenda est chargé à l’ouverture de la fiche', async () => {
    await ouvrirFiche();
    const appels = axios.get.mock.calls.map((c) => String(c[0]));
    expect(appels.some((u) => u.includes('/prospect-agenda/FES-01'))).toBe(true);
  });

  test('sans rendez-vous, la fiche le DIT', async () => {
    await ouvrirFiche();
    expect(par('aucun-rdv')).toBeTruthy();
    expect(par('prochain-rdv')).toBeNull();
  });

  test('le prochain rendez-vous s’affiche avec date, type et statut', async () => {
    await ouvrirFiche(agendaFictif({ next_appointment: rdvFictif() }));
    const bloc = par('prochain-rdv');
    expect(bloc).toBeTruthy();
    expect(bloc.textContent).toContain('Appel partenariat');
    expect(bloc.textContent).toContain('2026-09-10');
    expect(bloc.textContent).toContain('appel');
    expect(bloc.textContent).toContain('prevu');
  });

  test('le formulaire ne s’ouvre que sur demande', async () => {
    await ouvrirFiche();
    expect(par('formulaire-planification')).toBeNull();
    await act(async () => { par('planifier').click(); });
    expect(par('formulaire-planification')).toBeTruthy();
  });

  test('la date est pré-remplie — on ne demande pas de tout saisir', async () => {
    await ouvrirFiche();
    await act(async () => { par('planifier').click(); });
    expect(par('planif-quand').value).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
  });

  test('les quatre types et les six durées sont proposés', async () => {
    await ouvrirFiche();
    await act(async () => { par('planifier').click(); });
    expect(par('planif-type').querySelectorAll('option').length).toBe(4);
    expect(par('planif-duree').querySelectorAll('option').length).toBe(6);
  });

  test('créer part sur la route du calendrier, avec un ISO', async () => {
    await ouvrirFiche();
    await act(async () => { par('planifier').click(); });
    await act(async () => { par('planif-valider').click(); });
    expect(axios.post).toHaveBeenCalledTimes(1);
    const [url, corps] = axios.post.mock.calls[0];
    expect(url).toContain('/prospect-agenda/FES-01/appointment');
    expect(corps.starts_at).toMatch(/Z$/);
    expect(corps.duration_minutes).toBe(30);
    expect(corps.meeting_type).toBe('appel');
  });

  test('la fiche prospect n’est JAMAIS modifiée par une planification', async () => {
    await ouvrirFiche();
    await act(async () => { par('planifier').click(); });
    await act(async () => { par('planif-valider').click(); });
    expect(axios.patch).not.toHaveBeenCalled();
  });

  test('un refus du serveur est annoncé, sans casser la fiche', async () => {
    await ouvrirFiche();
    axios.post.mockRejectedValue(new Error('refus'));
    await act(async () => { par('planifier').click(); });
    await act(async () => { par('planif-valider').click(); });
    expect(par('message-fiche')).toBeTruthy();
    expect(par('fiche-prospect')).toBeTruthy();
  });

  test('annuler referme le formulaire sans rien envoyer', async () => {
    await ouvrirFiche();
    await act(async () => { par('planifier').click(); });
    await act(async () => { par('planif-annuler').click(); });
    expect(par('formulaire-planification')).toBeNull();
    expect(axios.post).not.toHaveBeenCalled();
  });
});

describe('CAL-3 — les tâches ouvertes sur la fiche', () => {
  const ouvrirAvec = async (taches) => {
    mockEtatParSection = {
      prospects: { etat: SECTION.OK, donnees: reponse([prospect({ ref: 'FES-01' })]) },
      campagnes: { etat: SECTION.OK, donnees: { total: 0, campaigns: [] } },
      reponses: { etat: SECTION.OK, donnees: { messages: [], total: 0, en_attente: 0 } },
    };
    axios.get.mockResolvedValue({ data: agendaFictif({ open_tasks: taches }) });
    await monter(<ProspectsSection API="/api" />);
    await act(async () => { par('ligne-FES-01').click(); });
  };

  test('sans tâche, la fiche le DIT', async () => {
    await ouvrirAvec([]);
    expect(par('aucune-tache')).toBeTruthy();
  });

  test('les tâches ouvertes sont listées', async () => {
    await ouvrirAvec([
      { id: 't-1', title: 'Rappeler le festival', starts_at: '2026-09-08T10:00:00+00:00',
        bucket: 'a_venir' },
      { id: 't-2', title: 'Envoyer le dossier', starts_at: '2026-08-20T10:00:00+00:00',
        bucket: 'en_retard' },
    ]);
    expect(tous('[data-testid="tache-ouverte"]').length).toBe(2);
    expect(conteneur.textContent).toContain('Rappeler le festival');
  });

  test('le retard est signalé', async () => {
    await ouvrirAvec([{ id: 't-2', title: 'Envoyer le dossier',
                        starts_at: '2026-08-20T10:00:00+00:00', bucket: 'en_retard' }]);
    expect(par('tache-ouverte').textContent).toContain('en retard');
  });

  test('le serveur ne renvoie que des tâches ouvertes — l’écran n’en filtre aucune', () => {
    // La règle vit côté serveur (CAL2_STATUTS_CLOS) : l'écran affiche ce qu'il
    // reçoit. Le vérifier ici empêcherait de croire à un second filtrage.
    const source = require('fs').readFileSync(
      require('path').join(__dirname, '..', 'ProspectsSection.js'), 'utf8');
    expect(source).toContain('agenda.open_tasks');
    expect(source).not.toContain("status !== 'fait'");
  });
});

/* ==========================================================================
   GOOGLE-2 — « SYNCHRONISER AVEC GOOGLE CALENDAR », DEPUIS LA FICHE PROSPECT
   --------------------------------------------------------------------------
   C'est le cas prioritaire du lot : un rendez-vous convenu avec un prospect
   part dans l'agenda du coach. Trois règles y sont vérifiées, et ce sont les
   trois que le lot promet :

     * L'OPTION N'EXISTE QUE SI ELLE PEUT ABOUTIR — un jeton Google sans droit
       d'écriture ne doit pas donner une case qui échouerait en 403 ;
     * LE CHOIX EST EXPLICITE — décoché, rien ne part chez Google ; le corps
       de la requête ne porte même pas le drapeau ;
     * LE RENDEZ-VOUS AFROBOOST PASSE D'ABORD — la case ne change rien à la
       route appelée ni aux champs métier : c'est le serveur qui, ensuite,
       tente Google.
   ========================================================================== */
describe('GOOGLE-2 — la case « Synchroniser avec Google Calendar »', () => {
  const ouvrirAvecGoogle = async (google) => {
    mockEtatParSection = {
      prospects: { etat: SECTION.OK, donnees: reponse([prospect({ ref: 'FES-01' })]) },
      campagnes: { etat: SECTION.OK, donnees: { total: 0, campaigns: [] } },
      reponses: { etat: SECTION.OK, donnees: { messages: [], total: 0, en_attente: 0 } },
    };
    axios.get.mockImplementation((url) => {
      if (String(url).includes('/google/status')) return Promise.resolve({ data: google });
      return Promise.resolve({ data: agendaFictif() });
    });
    axios.post.mockResolvedValue({ data: { appointment: rdvFictif() } });
    await monter(<ProspectsSection API="/api" />);
    await act(async () => { par('ligne-FES-01').click(); });
    await act(async () => { par('planifier').click(); });
  };

  const CONNECTE_ECRITURE = { connected: true, calendar_granted: true,
                              calendar_write_granted: true };
  const CONNECTE_LECTURE = { connected: true, calendar_granted: true,
                             calendar_write_granted: false };

  test('Google absent : AUCUNE case — on ne propose pas ce qui échouerait', async () => {
    await ouvrirAvecGoogle({ connected: false, configured: false });
    expect(par('planif-google')).toBeNull();
    expect(par('formulaire-planification')).toBeTruthy();
  });

  test('Google en LECTURE SEULE : toujours aucune case', async () => {
    await ouvrirAvecGoogle(CONNECTE_LECTURE);
    expect(par('planif-google')).toBeNull();
  });

  test('Google avec droit d’écriture : la case apparaît, DÉCOCHÉE', async () => {
    await ouvrirAvecGoogle(CONNECTE_ECRITURE);
    expect(par('planif-google')).toBeTruthy();
    expect(par('planif-google-case').checked).toBe(false);
    expect(par('planif-google').textContent).toContain('Synchroniser avec Google Calendar');
  });

  test('DÉCOCHÉE : le corps ne porte pas le drapeau — rien ne part chez Google', async () => {
    await ouvrirAvecGoogle(CONNECTE_ECRITURE);
    await act(async () => { par('planif-valider').click(); });
    const corps = axios.post.mock.calls[0][1];
    expect(corps.google_sync).toBeUndefined();
    expect('google_sync' in JSON.parse(JSON.stringify(corps))).toBe(false);
  });

  test('COCHÉE : le drapeau part, et rien d’autre ne change', async () => {
    await ouvrirAvecGoogle(CONNECTE_ECRITURE);
    // Un vrai clic : c'est lui qui bascule la case ET déclenche `onChange`.
    // Forcer `checked` avant le clic le rebasculerait aussitôt.
    await act(async () => {
      par('planif-google-case').dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    expect(par('planif-google-case').checked).toBe(true);
    await act(async () => { par('planif-valider').click(); });
    const [url, corps] = axios.post.mock.calls[0];
    expect(corps.google_sync).toBe(true);
    // La route et les champs métier sont EXACTEMENT ceux d'avant le lot.
    expect(url).toContain('/prospect-agenda/FES-01/appointment');
    expect(corps.meeting_type).toBe('appel');
    expect(corps.duration_minutes).toBe(30);
    expect(String(corps.starts_at)).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });

  test('la case ne déclenche AUCUN appel direct à Google depuis le navigateur', async () => {
    await ouvrirAvecGoogle(CONNECTE_ECRITURE);
    // Un vrai clic : c'est lui qui bascule la case ET déclenche `onChange`.
    // Forcer `checked` avant le clic le rebasculerait aussitôt.
    await act(async () => {
      par('planif-google-case').dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    expect(par('planif-google-case').checked).toBe(true);
    await act(async () => { par('planif-valider').click(); });
    const sortants = axios.post.mock.calls.map(([u]) => String(u))
      .concat(axios.get.mock.calls.map(([u]) => String(u)));
    expect(sortants.some((u) => u.includes('googleapis.com'))).toBe(false);
    expect(sortants.some((u) => u.includes('google.com'))).toBe(false);
  });

  test('un échec du statut Google laisse la planification utilisable', async () => {
    mockEtatParSection = {
      prospects: { etat: SECTION.OK, donnees: reponse([prospect({ ref: 'FES-01' })]) },
      campagnes: { etat: SECTION.OK, donnees: { total: 0, campaigns: [] } },
      reponses: { etat: SECTION.OK, donnees: { messages: [], total: 0, en_attente: 0 } },
    };
    axios.get.mockImplementation((url) => (String(url).includes('/google/status')
      ? Promise.reject(new Error('502'))
      : Promise.resolve({ data: agendaFictif() })));
    axios.post.mockResolvedValue({ data: { appointment: rdvFictif() } });
    await monter(<ProspectsSection API="/api" />);
    await act(async () => { par('ligne-FES-01').click(); });
    await act(async () => { par('planifier').click(); });
    expect(par('formulaire-planification')).toBeTruthy();
    expect(par('planif-google')).toBeNull();
    await act(async () => { par('planif-valider').click(); });
    expect(axios.post).toHaveBeenCalledTimes(1);
  });
});
