// P2-A — la lecture des candidatures partenaire, vue du navigateur.
//
// CE QUI EST PROUVE ICI, ET POURQUOI CHAQUE POINT COMPTE :
//
//   * le bouton « Candidatures (N) » n'apparait QUE sur un lien partenaire —
//     sur un lien participant, la route backend refuse de repondre, proposer le
//     bouton mènerait donc a un message d'erreur ;
//   * le nombre vient des donnees, jamais d'une constante ;
//   * les quatre etats de la fenetre existent : chargement, liste, vide, erreur ;
//   * les reponses sont rendues a partir de `question`/`answer`, sans jamais
//     nommer `q_0` ni `q_1` — c'est ce qui permettra de changer le questionnaire
//     du tunnel sans toucher a ce composant ;
//   * aucune action Accepter/Refuser, aucun slug, aucun QR : ce lot est en
//     lecture, et le test doit le rendre difficile a oublier.
//
// `axios` est mocke : aucun appel reseau ne part de ces tests.

// Harnais identique a CourseRemindersCard.test.js et ReminderRulesCard.test.js :
// react-dom/client + React.act, axios remplace par un jest.fn. Aucun reseau.
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import PartnerApplications, {
  p2aNormaliserReponses, p2aDateLisible, p2bSuggererSlug, p2bSlugValide,
} from '../PartnerApplications';
import SmartLinkCard from '../SmartLinkCard';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), patch: jest.fn() }
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
  if (racine) { await act(async () => { racine.unmount(); }); racine = null; }
  if (conteneur) { conteneur.remove(); conteneur = null; }
});

/** Le texte visible, comme le coach le lit. */
const texte = () => (conteneur ? conteneur.textContent : '');

/** Combien de fois cette chaine apparait dans le rendu. */
const compter = (chaine) => texte().split(chaine).length - 1;

/** Le bouton dont le texte contient `chaine`. */
const bouton = (chaine) => Array.from(conteneur.querySelectorAll('button'))
  .find(b => (b.textContent || '').includes(chaine));

async function cliquer(el) {
  await act(async () => {
    el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });
}

const LIEN_PARTENAIRE = {
  id: 'lien-1',
  link_token: 'tok_fictif',
  title: 'Devenir Partenaire (fictif)',
  lead_type: 'partner',
  tunnel_questions: [{ id: 1, text: 'q' }],
};

const LIEN_PARTICIPANT = { ...LIEN_PARTENAIRE, id: 'lien-2', lead_type: 'participant' };

const REPONSE_DEUX = {
  data: {
    link_token: 'tok_fictif',
    title: 'Devenir Partenaire (fictif)',
    lead_type: 'partner',
    total: 2,
    applications: [
      {
        id: 'c-2', submission_id: null, link_token: 'tok_fictif',
        name: 'Recente Fictive', email: 'recente@exemple.test',
        whatsapp: '+41000000003', source: 'link_tok_fictif',
        created_at: '2026-08-28T10:00:00+00:00',
        application_decision: 'pending',
        answers: {
          q_0: { question: 'Votre activite ?', answer: 'Salon fictif, Neuchatel' },
          q_1: { question: 'Quelle collaboration ?', answer: 'Visibilite croisee' },
        },
      },
      {
        id: 'c-1', submission_id: 'sub-fictif', link_token: 'tok_fictif',
        name: 'Ancienne Fictive', email: 'ancienne@exemple.test',
        whatsapp: '+41000000001', source: 'link_tok_fictif',
        created_at: '2026-08-01T10:00:00+00:00',
        application_decision: 'pending',
        answers: { q_0: { question: 'Votre activite ?', answer: 'Association fictive' } },
      },
    ],
  },
};

/** Une reponse a un seul element, dans l'etat demande. */
const reponseUne = (extra = {}) => ({
  data: {
    link_token: 'tok_fictif', title: 'Devenir Partenaire (fictif)',
    lead_type: 'partner', total: 1,
    applications: [{
      id: 'c-1', submission_id: null, link_token: 'tok_fictif',
      name: 'Akoko Tresses', email: 'a@exemple.test', whatsapp: '+41000000001',
      source: 'link_tok_fictif', created_at: '2026-08-28T10:00:00+00:00',
      application_decision: 'pending',
      answers: { q_0: { question: 'Votre activite ?', answer: 'Salon' } },
      ...extra,
    }],
  },
});

const champSlug = () => conteneur.querySelector('input[aria-label="Identifiant du partenaire"]');

beforeEach(() => {
  jest.clearAllMocks();
});

// ---------------------------------------------------------------------------
describe('P2-A — le bouton sur la carte', () => {
  const proprietes = (link, extra = {}) => ({
    link,
    copiedLinkId: null,
    onCopy: jest.fn(), onDelete: jest.fn(), onEdit: jest.fn(),
    onToggleSelect: jest.fn(), selected: false,
    ...extra,
  });

  test('un lien PARTENAIRE affiche « Candidatures » avec le nombre reel', async () => {
    await monter(<SmartLinkCard {...proprietes(LIEN_PARTENAIRE, {
      applicationsCount: 6, onOpenApplications: jest.fn() })} />);
    expect(texte()).toContain('Candidatures (6)');
  });

  test("un lien PARTICIPANT n'affiche AUCUN bouton Candidatures", async () => {
    await monter(<SmartLinkCard {...proprietes(LIEN_PARTICIPANT, {
      applicationsCount: 6, onOpenApplications: jest.fn() })} />);
    expect(texte()).not.toContain('Candidatures');
  });

  test('compte inconnu : le bouton reste, SANS nombre — un « (0) » serait faux', async () => {
    await monter(<SmartLinkCard {...proprietes(LIEN_PARTENAIRE, {
      applicationsCount: undefined, onOpenApplications: jest.fn() })} />);
    expect(texte()).toContain('Candidatures');
    expect(texte()).not.toContain('Candidatures (');
  });

  test('zero candidature affiche bien « (0) », pas rien', async () => {
    await monter(<SmartLinkCard {...proprietes(LIEN_PARTENAIRE, {
      applicationsCount: 0, onOpenApplications: jest.fn() })} />);
    expect(texte()).toContain('Candidatures (0)');
  });

  test('le clic remonte le lien au parent', async () => {
    const ouvrir = jest.fn();
    await monter(<SmartLinkCard {...proprietes(LIEN_PARTENAIRE, {
      applicationsCount: 2, onOpenApplications: ouvrir })} />);
    await cliquer(bouton('Candidatures (2)'));
    expect(ouvrir).toHaveBeenCalledWith(LIEN_PARTENAIRE);
  });

  test("sans callback, aucun bouton — on ne propose pas une action morte", async () => {
    await monter(<SmartLinkCard {...proprietes(LIEN_PARTENAIRE, { applicationsCount: 3 })} />);
    expect(texte()).not.toContain('Candidatures');
  });
});

// ---------------------------------------------------------------------------
describe('P2-A — la fenetre des candidatures', () => {
  test("fermee, elle ne rend rien et n'appelle rien", async () => {
    await monter(<PartnerApplications isOpen={false} link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    expect(conteneur.innerHTML).toBe('');
    expect(axios.get).not.toHaveBeenCalled();
  });

  test('ouverte, elle appelle la route en axios avec le jeton du lien', async () => {
    axios.get.mockResolvedValue(REPONSE_DEUX);
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    expect(axios.get).toHaveBeenCalledWith('/api/partner-applications/tok_fictif');
    // UN SEUL argument : aucun en-tete pose a la main. Le Bearer vient de
    // l'intercepteur global, et de lui seul.
    expect(axios.get.mock.calls[0]).toHaveLength(1);
  });

  test('etat CHARGEMENT tant que la reponse n\'est pas arrivee', async () => {
    let resoudre;
    axios.get.mockReturnValue(new Promise((r) => { resoudre = r; }));
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    expect(texte()).toContain('Chargement des candidatures');
    await act(async () => { resoudre(REPONSE_DEUX); });
    expect(texte()).not.toContain('Chargement des candidatures');
  });

  test('etat LISTE : noms, coordonnees, libelles ET reponses', async () => {
    axios.get.mockResolvedValue(REPONSE_DEUX);
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    const t = texte();
    expect(t).toContain('Recente Fictive');
    expect(t).toContain('Ancienne Fictive');
    expect(t).toContain('recente@exemple.test');
    expect(t).toContain('+41000000001');
    // Les LIBELLES viennent des donnees, pas du composant.
    expect(compter('Votre activite ?')).toBe(2);
    expect(t).toContain('Quelle collaboration ?');
    expect(t).toContain('Salon fictif, Neuchatel');
    expect(t).toContain('Visibilite croisee');
  });

  test('« pending » s\'affiche « En attente », une fois par candidature', async () => {
    axios.get.mockResolvedValue(REPONSE_DEUX);
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    expect(compter('En attente')).toBe(2);
  });

  test('aucun QR, aucun slug, aucune statistique — meme avec la decision P2-B', async () => {
    axios.get.mockResolvedValue(REPONSE_DEUX);
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    const t = texte();
    expect(t).not.toMatch(/slug/i);
    expect(t).not.toMatch(/\bQR\b/);
    expect(t).not.toMatch(/utm_/);
    expect(conteneur.querySelector('canvas')).toBeNull();
    // P2-B ajoute Accepter/Refuser sur les candidatures EN ATTENTE : c'est
    // attendu ici. Leur ABSENCE sur une candidature deja tranchee est prouvee
    // dans la section « P2-B — la decision ».
    const libelles = Array.from(conteneur.querySelectorAll('button'))
      .map(b => (b.getAttribute('aria-label') || b.textContent || '').trim());
    expect(libelles).toEqual(['Fermer', 'Accepter', 'Refuser', 'Accepter', 'Refuser']);
  });

  test('etat VIDE : un message, pas une liste blanche', async () => {
    axios.get.mockResolvedValue({ data: { total: 0, applications: [], title: 'X' } });
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    expect(texte()).toContain("Aucune candidature pour l'instant");
  });

  test('etat ERREUR reseau : message + « Réessayer » qui rappelle la route', async () => {
    axios.get.mockRejectedValueOnce(new Error('reseau'));
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    expect(texte()).toContain('Chargement impossible');
    axios.get.mockResolvedValueOnce(REPONSE_DEUX);
    await cliquer(bouton('Réessayer'));
    expect(texte()).toContain('Recente Fictive');
  });

  test("un 403 dit de se reconnecter — « reessayer » n'y changerait rien", async () => {
    axios.get.mockRejectedValue({ response: { status: 403 } });
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    expect(texte()).toContain('Accès refusé');
  });

  test("un 404 dit que le lien n'a pas de candidatures partenaire", async () => {
    axios.get.mockRejectedValue({ response: { status: 404 } });
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    expect(texte()).toContain('pas de candidatures partenaire');
  });

  test('le bouton Fermer remonte au parent', async () => {
    axios.get.mockResolvedValue(REPONSE_DEUX);
    const fermer = jest.fn();
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={fermer} />);
    await cliquer(conteneur.querySelector('button[aria-label="Fermer"]'));
    expect(fermer).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
describe('P2-B — la decision', () => {
  test('EN ATTENTE : les deux boutons de decision sont proposes', async () => {
    axios.get.mockResolvedValue(reponseUne());
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    expect(bouton('Accepter')).toBeTruthy();
    expect(bouton('Refuser')).toBeTruthy();
  });

  test('ACCEPTEE : plus aucun bouton de decision — on ne renverse pas', async () => {
    axios.get.mockResolvedValue(reponseUne({
      application_decision: 'accepted', partner_slug: 'akoko_tresses' }));
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    expect(bouton('Accepter')).toBeFalsy();
    expect(bouton('Refuser')).toBeFalsy();
    expect(texte()).toContain('Acceptée');
    expect(texte()).toContain('akoko_tresses');
  });

  test('REFUSEE : plus aucun bouton de decision', async () => {
    axios.get.mockResolvedValue(reponseUne({ application_decision: 'rejected' }));
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    expect(bouton('Accepter')).toBeFalsy();
    expect(bouton('Refuser')).toBeFalsy();
    expect(texte()).toContain('Refusée');
  });

  test('« Accepter » ouvre la saisie du slug, PRE-REMPLIE depuis le nom', async () => {
    axios.get.mockResolvedValue(reponseUne());
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    await cliquer(bouton('Accepter'));
    expect(champSlug()).toBeTruthy();
    expect(champSlug().value).toBe('akoko_tresses');
    expect(texte()).toContain("ne pourra plus être modifié après l'acceptation");
  });

  test('la suggestion est MODIFIABLE avant validation', async () => {
    axios.get.mockResolvedValue(reponseUne());
    axios.patch.mockResolvedValue({ data: { success: true } });
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    await cliquer(bouton('Accepter'));
    await act(async () => {
      const c = champSlug();
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')
        .set.call(c, 'autre_nom_choisi');
      c.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await cliquer(bouton('Accepter le partenaire'));
    expect(axios.patch).toHaveBeenCalledWith(
      '/api/partner-applications/c-1/decision',
      { decision: 'accepted', partner_slug: 'autre_nom_choisi' });
  });

  test('un slug invalide est refuse AVANT tout appel reseau', async () => {
    axios.get.mockResolvedValue(reponseUne());
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    await cliquer(bouton('Accepter'));
    await act(async () => {
      const c = champSlug();
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')
        .set.call(c, 'Nom Avec Espaces');
      c.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await cliquer(bouton('Accepter le partenaire'));
    expect(axios.patch).not.toHaveBeenCalled();
    expect(texte()).toContain('3 à 40 caractères');
  });

  test('le refus demande une confirmation avant de partir', async () => {
    axios.get.mockResolvedValue(reponseUne());
    axios.patch.mockResolvedValue({ data: { success: true } });
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    await cliquer(bouton('Refuser'));
    expect(axios.patch).not.toHaveBeenCalled();
    expect(texte()).toContain('Cette décision est définitive');
    await cliquer(bouton('Confirmer le refus'));
    expect(axios.patch).toHaveBeenCalledWith(
      '/api/partner-applications/c-1/decision', { decision: 'rejected' });
  });

  test('un refus n\'envoie AUCUN slug', async () => {
    axios.get.mockResolvedValue(reponseUne());
    axios.patch.mockResolvedValue({ data: { success: true } });
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    await cliquer(bouton('Refuser'));
    await cliquer(bouton('Confirmer le refus'));
    expect(axios.patch.mock.calls[0][1]).not.toHaveProperty('partner_slug');
  });

  test('succes : la liste est RECHARGEE depuis le serveur', async () => {
    axios.get.mockResolvedValueOnce(reponseUne());
    axios.patch.mockResolvedValue({ data: { success: true } });
    axios.get.mockResolvedValueOnce(reponseUne({
      application_decision: 'accepted', partner_slug: 'akoko_tresses' }));
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    await cliquer(bouton('Accepter'));
    await cliquer(bouton('Accepter le partenaire'));
    expect(axios.get).toHaveBeenCalledTimes(2);
    expect(texte()).toContain('Acceptée');
    expect(bouton('Accepter')).toBeFalsy();
  });

  test('double clic : un seul appel part', async () => {
    axios.get.mockResolvedValue(reponseUne());
    let resoudre;
    axios.patch.mockReturnValue(new Promise((r) => { resoudre = r; }));
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    await cliquer(bouton('Accepter'));
    const valider = bouton('Accepter le partenaire');
    await act(async () => {
      valider.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      valider.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    expect(axios.patch).toHaveBeenCalledTimes(1);
    expect(texte()).toContain('Enregistrement…');
    await act(async () => { resoudre({ data: { success: true } }); });
  });

  test('collision de slug : le message du serveur est affiche', async () => {
    axios.get.mockResolvedValue(reponseUne());
    axios.patch.mockRejectedValue({
      response: { status: 409, data: { detail: 'Ce slug est déjà utilisé' } } });
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    await cliquer(bouton('Accepter'));
    await cliquer(bouton('Accepter le partenaire'));
    expect(texte()).toContain('Ce slug est déjà utilisé');
  });

  test('un 403 dit de se reconnecter', async () => {
    axios.get.mockResolvedValue(reponseUne());
    axios.patch.mockRejectedValue({ response: { status: 403 } });
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    await cliquer(bouton('Refuser'));
    await cliquer(bouton('Confirmer le refus'));
    expect(texte()).toContain('Accès refusé');
  });

  test('AUCUN QR, AUCUNE statistique, AUCUN lien UTM dans ce lot', async () => {
    axios.get.mockResolvedValue(reponseUne({
      application_decision: 'accepted', partner_slug: 'akoko_tresses' }));
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    const t = texte();
    expect(t).not.toMatch(/utm_/);
    expect(t).not.toMatch(/\bQR\b/);
    expect(t).not.toMatch(/clics|conversion/i);
    expect(conteneur.querySelector('canvas')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
describe('P2-B — le slug', () => {
  test('la suggestion deplie les accents au lieu de les supprimer', () => {
    expect(p2bSuggererSlug('Récif Neuchâtel')).toBe('recif_neuchatel');
    expect(p2bSuggererSlug('Akoko Tresses')).toBe('akoko_tresses');
  });

  test('les separateurs multiples sont fondus, jamais laisses aux bords', () => {
    expect(p2bSuggererSlug('  Vénus   Nails -- Neuchâtel !! ')).toBe('venus_nails_neuchatel');
  });

  test('la suggestion est bornee a 40 caracteres', () => {
    expect(p2bSuggererSlug('a'.repeat(80)).length).toBe(40);
  });

  test('un nom vide ne fait pas planter la suggestion', () => {
    expect(p2bSuggererSlug('')).toBe('');
    expect(p2bSuggererSlug(null)).toBe('');
  });

  test('la validation applique EXACTEMENT la regle du serveur', () => {
    expect(p2bSlugValide('akoko_tresses')).toBe(true);
    expect(p2bSlugValide('ab')).toBe(false);
    expect(p2bSlugValide('a'.repeat(41))).toBe(false);
    expect(p2bSlugValide('Akoko_Tresses')).toBe(false);
    expect(p2bSlugValide('akoko tresses')).toBe(false);
    expect(p2bSlugValide('akoko-tresses')).toBe(false);
    expect(p2bSlugValide('récif')).toBe(false);
    expect(p2bSlugValide('')).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe('P2-A — le rendu des reponses est generique', () => {
  test('un dict est ordonne par cle, et les libelles sont conserves', () => {
    const r = p2aNormaliserReponses({
      q_1: { question: 'B ?', answer: 'deux' },
      q_0: { question: 'A ?', answer: 'un' },
    });
    expect(r).toEqual([{ question: 'A ?', answer: 'un' }, { question: 'B ?', answer: 'deux' }]);
  });

  test('une LISTE est acceptee aussi — les deux formes existent en base', () => {
    expect(p2aNormaliserReponses([{ question: 'A ?', answer: 'un' }]))
      .toEqual([{ question: 'A ?', answer: 'un' }]);
  });

  test('un questionnaire tout different passe sans changer une ligne de code', () => {
    const r = p2aNormaliserReponses({
      q_0: { question: 'Combien de membres ?', answer: '25' },
      q_1: { question: 'Votre commune ?', answer: 'Neuchatel' },
      q_2: { question: 'Un evenement vous interesse ?', answer: 'Oui' },
    });
    expect(r).toHaveLength(3);
    expect(r[2].question).toBe('Un evenement vous interesse ?');
  });

  test('les entrees vides ou malformees sont ecartees, sans planter', () => {
    expect(p2aNormaliserReponses({ q_0: null, q_1: {}, q_2: 'texte' })).toEqual([]);
    expect(p2aNormaliserReponses(null)).toEqual([]);
    expect(p2aNormaliserReponses(undefined)).toEqual([]);
  });

  test('une reponse numerique reste lisible', () => {
    expect(p2aNormaliserReponses({ q_0: { question: 'Combien ?', answer: 25 } }))
      .toEqual([{ question: 'Combien ?', answer: '25' }]);
  });

  test('une date invalide n\'affiche jamais « Invalid Date »', () => {
    expect(p2aDateLisible('pas-une-date')).toBe('—');
    expect(p2aDateLisible('')).toBe('—');
    expect(p2aDateLisible(null)).toBe('—');
    expect(p2aDateLisible('2026-08-28T10:00:00+00:00')).not.toBe('—');
  });
});
