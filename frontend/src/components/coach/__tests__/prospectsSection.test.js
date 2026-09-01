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
    axios.get.mock.calls.forEach(([url]) => {
      expect(url).toBe('/api/partner-prospects');
    });
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
      expect(libelle).not.toMatch(/^(envoyer|lancer|relancer|contacter|send|notifier|approuver)\b/);
    });
    // Et l'écran ne connaît aucune route d'envoi.
    const source = require('fs').readFileSync(
      require('path').join(__dirname, '..', 'ProspectsSection.js'), 'utf8');
    ['/send', '/launch', '/dispatch', '/approve'].forEach((chemin) => {
      expect(source).not.toContain(chemin);
    });
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
