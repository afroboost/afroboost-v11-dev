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
  p2d2Taux, p2d2Nombre, p2d2ReponseUtilisable,
} from '../PartnerApplications';
import { construireLienPartenaire } from '../../../utils/partnerLink';
import SmartLinkCard from '../SmartLinkCard';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), patch: jest.fn(), post: jest.fn(), put: jest.fn() }
}));

// Le generateur de QR est remplace par un canvas qui EXPOSE la valeur recue.
// C'est le seul moyen de prouver ce que le QR encode reellement : lire les
// pixels ne dirait rien, et verifier qu'un canvas existe ne prouve pas son
// contenu. La vraie bibliotheque reste utilisee en production, inchangee.
jest.mock('qrcode.react', () => ({
  __esModule: true,
  QRCodeCanvas: ({ value, size }) => {
    const React = require('react');
    return React.createElement('canvas', {
      'data-qr-value': value, width: size, height: size });
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

/** La valeur REELLEMENT encodee par le QR, lue sur la fibre React du canvas.
 *  On ne se contente pas de verifier qu'un canvas existe : ce qui compte est
 *  ce qu'il encode, et rien d'autre ne le prouve. */
const valeurQr = () => {
  const c = conteneur.querySelector('canvas');
  return c ? c.getAttribute('data-qr-value') : null;
};

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
    // P2-D2 A MIGRE CETTE ASSERTION, ET L'A RENDUE PLUS STRICTE.
    // Avant P2-D2, ce composant n'emettait qu'un seul type de GET : compter
    // TOUS les appels d'axios revenait donc a compter ceux de la route des
    // candidatures. P2-D2 ajoute un second GET legitime
    // (`/partners/{slug}/stats`, cf. le bloc P2-D2 plus bas), et le compteur
    // global melangerait desormais deux routes.
    // Ce qui suit epingle l'URL EN PLUS du nombre : c'est un durcissement, pas
    // un assouplissement. L'appel de statistiques n'est pas masque — il est
    // controle separement, et le test « A. » exige qu'il parte exactement une
    // fois.
    const appelsCandidatures = axios.get.mock.calls
      .filter((c) => String(c[0]).includes('/partner-applications/'));
    expect(appelsCandidatures).toHaveLength(2);
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

  // P2-C ajoute DELIBEREMENT le lien UTM et le QR sur une candidature acceptee :
  // l'absence de lien est desormais prouvee sur `pending` et `rejected`, dans la
  // section P2-C. Ce qui reste hors perimetre jusqu'a P2-D, ce sont les
  // statistiques — et le QR ne doit s'afficher que sur demande, pas d'office.
  test('aucune statistique, et le QR ne s\'affiche pas tant qu\'on ne le demande pas',
    async () => {
      axios.get.mockResolvedValue(reponseUne({
        application_decision: 'accepted', partner_slug: 'akoko_tresses' }));
      await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
      expect(texte()).not.toMatch(/clics|conversions|taux/i);
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
describe('P2-C — le lien personnel et son QR', () => {
  const LIEN = construireLienPartenaire('akoko_tresses');

  const accepte = (extra = {}) => reponseUne({
    application_decision: 'accepted', partner_slug: 'akoko_tresses',
    partner_status: 'decouverte', ...extra });

  test('EN ATTENTE : aucun lien, aucun QR', async () => {
    axios.get.mockResolvedValue(reponseUne());
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    expect(conteneur.querySelector('[data-testid="lien-partenaire"]')).toBeNull();
    expect(texte()).not.toContain('utm_source');
    expect(bouton('QR code')).toBeFalsy();
    expect(conteneur.querySelector('canvas')).toBeNull();
  });

  test('REFUSEE : aucun lien, aucun QR', async () => {
    axios.get.mockResolvedValue(reponseUne({ application_decision: 'rejected' }));
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    expect(conteneur.querySelector('[data-testid="lien-partenaire"]')).toBeNull();
    expect(bouton('QR code')).toBeFalsy();
    expect(conteneur.querySelector('canvas')).toBeNull();
  });

  test("ACCEPTEE SANS slug : anomalie sobre, et surtout AUCUN slug fabrique "
     + 'depuis le nom', async () => {
    axios.get.mockResolvedValue(reponseUne({ application_decision: 'accepted' }));
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    expect(texte()).toContain('Partenaire incomplet — identifiant indisponible');
    expect(conteneur.querySelector('[data-testid="lien-partenaire"]')).toBeNull();
    expect(bouton('QR code')).toBeFalsy();
    expect(texte()).not.toContain('akoko_tresses');
  });

  test('ACCEPTEE avec slug : le lien EXACT est affiche', async () => {
    axios.get.mockResolvedValue(accepte());
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    const zone = conteneur.querySelector('[data-testid="lien-partenaire"]');
    expect(zone).toBeTruthy();
    expect(zone.textContent).toBe(LIEN);
    expect(zone.textContent).toBe(
      'https://afroboost.com/cours-essai-gratuit-neuchatel'
      + '?utm_source=partenaire&utm_medium=referral&utm_campaign=essai_neuchatel'
      + '&utm_content=akoko_tresses');
  });

  test("l'identifiant partenaire est affiche", async () => {
    axios.get.mockResolvedValue(accepte());
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    expect(texte()).toContain('Identifiant partenaire');
    expect(texte()).toContain('akoko_tresses');
  });

  test('les trois boutons sont proposes', async () => {
    axios.get.mockResolvedValue(accepte());
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    expect(bouton('Copier')).toBeTruthy();
    expect(bouton('QR code')).toBeTruthy();
    const ouvrir = Array.from(conteneur.querySelectorAll('a'))
      .find((a) => (a.textContent || '').includes('Ouvrir'));
    expect(ouvrir).toBeTruthy();
  });

  test("« Ouvrir » pointe l'URL exacte, dans un nouvel onglet, sans rien declencher",
    async () => {
      axios.get.mockResolvedValue(accepte());
      await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
      const a = Array.from(conteneur.querySelectorAll('a'))
        .find((x) => (x.textContent || '').includes('Ouvrir'));
      expect(a.getAttribute('href')).toBe(LIEN);
      expect(a.getAttribute('target')).toBe('_blank');
      expect(a.getAttribute('rel')).toContain('noopener');
    });

  test('« Copier » met le lien au presse-papiers et confirme « Copié »', async () => {
    axios.get.mockResolvedValue(accepte());
    const ecrire = jest.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: ecrire }, configurable: true });
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    await cliquer(bouton('Copier'));
    expect(ecrire).toHaveBeenCalledWith(LIEN);
    expect(texte()).toContain('Copié');
  });

  test('« QR code » affiche un canvas, et le QR encode l\'URL EXACTE', async () => {
    axios.get.mockResolvedValue(accepte());
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    expect(conteneur.querySelector('canvas')).toBeNull();
    await cliquer(bouton('QR code'));
    expect(conteneur.querySelector('canvas')).toBeTruthy();
    // La valeur REELLEMENT passee au generateur, lue sur le composant monte.
    expect(valeurQr()).toBe(LIEN);
  });

  test('le QR n\'encode ni raccourci, ni identifiant interne', () => {
    expect(LIEN).not.toMatch(/\/v\/|bit\.ly|\?link=/);
    expect(LIEN).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/);
  });

  test('« Télécharger le QR » produit un PNG nomme avec le slug', async () => {
    axios.get.mockResolvedValue(accepte());
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    await cliquer(bouton('QR code'));

    const canvas = conteneur.querySelector('canvas');
    canvas.toDataURL = jest.fn(() => 'data:image/png;base64,FICTIF');
    const ancre = { download: '', href: '', click: jest.fn() };
    const creer = jest.spyOn(document, 'createElement').mockImplementation((t) =>
      (t === 'a' ? ancre : document.createElementNS('http://www.w3.org/1999/xhtml', t)));

    await cliquer(bouton('Télécharger le QR'));

    expect(ancre.download).toBe('afroboost-partenaire-akoko_tresses-qr.png');
    expect(ancre.href).toBe('data:image/png;base64,FICTIF');
    expect(ancre.click).toHaveBeenCalled();
    expect(canvas.toDataURL).toHaveBeenCalledWith('image/png');
    creer.mockRestore();
  });

  test('P2-C ne declenche AUCUNE ecriture : ni PATCH, ni POST, ni PUT', async () => {
    axios.get.mockResolvedValue(accepte());
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    await cliquer(bouton('QR code'));
    await cliquer(bouton('Copier'));
    expect(axios.patch).not.toHaveBeenCalled();
    expect(axios.post).not.toHaveBeenCalled();
    expect(axios.put).not.toHaveBeenCalled();
  });

  test('une candidature acceptee n\'a plus de bouton de decision', async () => {
    axios.get.mockResolvedValue(accepte());
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    expect(bouton('Accepter')).toBeFalsy();
    expect(bouton('Refuser')).toBeFalsy();
    expect(texte()).toContain('Acceptée');
  });

  test('AUCUNE statistique dans ce lot', async () => {
    axios.get.mockResolvedValue(accepte());
    await monter(<PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);
    const t = texte();
    expect(t).not.toMatch(/clics|conversions|présences|taux/i);
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

// ---------------------------------------------------------------------------
// P2-D2 — LES RESULTATS DU PARTENARIAT.
//
// CE QUE CE BLOC VERROUILLE, ET POURQUOI :
//
//   * `null` n'est pas `0`. Le serveur renvoie `null` quand il n'a pas de
//     denominateur et `0` quand il a mesure zero. Afficher « 0 % » dans le
//     premier cas reprocherait a un partenaire une contre-performance qu'il
//     n'a pas eue. Deux tests separes, pour chacun des deux taux.
//   * l'appel n'existe que pour une candidature ACCEPTEE avec slug. En attente,
//     refusee, ou acceptee sans slug : AUCUN appel — verifie sur l'URL, pas sur
//     le nombre total d'appels.
//   * une erreur de la route stats ne doit RIEN emporter avec elle : le lien,
//     le QR et la microcopy sont produits sans reseau, ils doivent rester.
//   * aucune donnee personnelle rendue : la route est agregee, l'ecran aussi.
//
// `axios.get` est aiguille PAR URL : c'est la seule facon de distinguer la
// route des candidatures de celle des statistiques dans le meme composant.
describe('P2-D2 — les resultats du partenariat', () => {
  const SLUG = 'akoko_tresses';
  const URL_STATS = `/api/partners/${SLUG}/stats`;

  const accepteD2 = (extra = {}) => reponseUne({
    application_decision: 'accepted', partner_slug: SLUG,
    partner_status: 'decouverte', ...extra });

  /** La reponse REELLE de la production du 31/08/2026, relevee avec un jeton
   *  coach valide sur `GET /api/partners/bassi_test_interne/stats` (HTTP 200).
   *  Les valeurs ne sont pas inventees pour le test. */
  const STATS_REELLES = {
    partner_slug: SLUG, partner_status: 'decouverte',
    reservations: 1, unique_people: 1,
    unique_people_method: 'discount_code_then_normalized_email',
    attendances: 0, attendance_definition: 'validated_true',
    conversions_unit: 'people',
    conversions: { pulse: 0, member: 0, subscription: 0, total: 0 },
    attendance_rate: 0, conversion_rate: 0,
    attribution: { basis: 'first', source: 'partenaire',
                   medium: 'referral', campaign: 'essai_neuchatel' },
  };

  /** Aiguillage par URL. `stats` peut etre une valeur, ou une fonction pour
   *  faire echouer / varier les appels successifs. */
  function router(candidatures, stats) {
    let n = 0;
    axios.get.mockImplementation((url) => {
      if (String(url).includes('/partners/')) {
        n += 1;
        const r = typeof stats === 'function' ? stats(n) : stats;
        return r instanceof Error ? Promise.reject(r) : Promise.resolve({ data: r });
      }
      return Promise.resolve(candidatures);
    });
  }

  /** Les URL de statistiques réellement appelées. */
  const appelsStats = () => axios.get.mock.calls
    .map((c) => String(c[0])).filter((u) => u.includes('/partners/'));

  const monterFiche = () => monter(
    <PartnerApplications isOpen link={LIEN_PARTENAIRE} API="/api" onClose={jest.fn()} />);

  // --- Les fonctions pures : la regle `null` != `0`, isolee ---------------
  test('p2d2Taux : null et undefined donnent un tiret, JAMAIS « 0 % »', () => {
    expect(p2d2Taux(null)).toBe('—');
    expect(p2d2Taux(undefined)).toBe('—');
    expect(p2d2Taux(null)).not.toContain('0');
  });

  test('p2d2Taux : un vrai zero mesure donne bien « 0 % »', () => {
    expect(p2d2Taux(0)).toBe('0 %');
    expect(p2d2Taux(0.0)).toBe('0 %');
  });

  test('p2d2Taux : les taux reels sont rendus en pourcentage', () => {
    expect(p2d2Taux(1)).toBe('100 %');
    expect(p2d2Taux(0.5)).toBe('50 %');
    expect(p2d2Taux(0.3333)).toBe('33.3 %');
  });

  test('p2d2Nombre : jamais « NaN », jamais un zero invente', () => {
    expect(p2d2Nombre(0)).toBe('0');
    expect(p2d2Nombre(7)).toBe('7');
    expect(p2d2Nombre(undefined)).toBe('—');
    expect(p2d2Nombre(null)).toBe('—');
    expect(p2d2Nombre('abc')).toBe('—');
  });

  test('p2d2ReponseUtilisable : une reponse d\'une autre route est refusee', () => {
    expect(p2d2ReponseUtilisable(STATS_REELLES)).toBe(true);
    expect(p2d2ReponseUtilisable({ reservations: 0 })).toBe(true);
    expect(p2d2ReponseUtilisable({ applications: [] })).toBe(false);
    expect(p2d2ReponseUtilisable(null)).toBe(false);
  });

  // --- A a D : QUAND la route est appelee --------------------------------
  test('A. acceptee + slug : la route stats est appelee EXACTEMENT une fois', async () => {
    router(accepteD2(), STATS_REELLES);
    await monterFiche();
    expect(appelsStats()).toEqual([URL_STATS]);
  });

  test('B. en attente : AUCUN appel a la route stats', async () => {
    router(reponseUne(), STATS_REELLES);
    await monterFiche();
    expect(appelsStats()).toEqual([]);
  });

  test('C. refusee : AUCUN appel a la route stats', async () => {
    router(reponseUne({ application_decision: 'rejected' }), STATS_REELLES);
    await monterFiche();
    expect(appelsStats()).toEqual([]);
  });

  test('D. acceptee SANS slug : AUCUN appel a la route stats', async () => {
    router(reponseUne({ application_decision: 'accepted' }), STATS_REELLES);
    await monterFiche();
    expect(appelsStats()).toEqual([]);
    expect(texte()).toContain('Partenaire incomplet');
  });

  test("l'appel ne pose AUCUN en-tete a la main — le Bearer vient de l'intercepteur",
    async () => {
      router(accepteD2(), STATS_REELLES);
      await monterFiche();
      const appel = axios.get.mock.calls.find((c) => String(c[0]).includes('/partners/'));
      expect(appel).toHaveLength(1);
    });

  // --- E : les valeurs reelles sont rendues ------------------------------
  test('E. les quatre compteurs affichent les valeurs du serveur', async () => {
    router(accepteD2(), STATS_REELLES);
    await monterFiche();
    const grille = conteneur.querySelector('[data-testid="p2d2-compteurs"]');
    expect(grille).not.toBeNull();
    const cases = Array.from(grille.children).map((d) => (d.textContent || '').trim());
    expect(cases).toEqual(['1Réservations', '1Personnes', '0Présences', '0Conversions']);
    expect(texte()).toContain('Résultats de votre partenariat');
  });

  test('E-bis. les compteurs ne sont pas codes en dur : d\'autres chiffres passent',
    async () => {
      router(accepteD2(), {
        ...STATS_REELLES, reservations: 12, unique_people: 9, attendances: 7,
        conversions: { pulse: 2, member: 1, subscription: 3, total: 5 },
      });
      await monterFiche();
      const grille = conteneur.querySelector('[data-testid="p2d2-compteurs"]');
      const cases = Array.from(grille.children).map((d) => (d.textContent || '').trim());
      expect(cases).toEqual(['12Réservations', '9Personnes', '7Présences', '5Conversions']);
      expect(texte()).toContain('Pulse 2');
      expect(texte()).toContain('Membres 1');
      expect(texte()).toContain('Abonnements 3');
    });

  // --- F a H : la regle null != 0, dans le RENDU -------------------------
  test('F. attendance_rate = null : le rendu ne contient PAS « 0 % » de presence',
    async () => {
      router(accepteD2(), {
        ...STATS_REELLES, reservations: 0, unique_people: 0, attendances: 0,
        attendance_rate: null, conversion_rate: null,
      });
      await monterFiche();
      expect(texte()).toContain('Taux de présence —');
      expect(texte()).not.toContain('Taux de présence 0 %');
    });

  test('G. attendance_rate = 0.0 reellement fourni : « 0 % » est affiche', async () => {
    router(accepteD2(), { ...STATS_REELLES, attendance_rate: 0 });
    await monterFiche();
    expect(texte()).toContain('Taux de présence 0 %');
  });

  test('H. conversion_rate = null : pas « 0 % » de conversion', async () => {
    router(accepteD2(), { ...STATS_REELLES, conversion_rate: null });
    await monterFiche();
    expect(texte()).toContain('Taux de conversion —');
    expect(texte()).not.toContain('Taux de conversion 0 %');
  });

  // --- C (etat zero) : un partenaire sans aucune reservation --------------
  test('partenaire a zero : quatre zeros, des tirets, et rien d\'alarmant', async () => {
    router(accepteD2(), {
      ...STATS_REELLES, reservations: 0, unique_people: 0, attendances: 0,
      conversions: { pulse: 0, member: 0, subscription: 0, total: 0 },
      attendance_rate: null, conversion_rate: null,
    });
    await monterFiche();
    const grille = conteneur.querySelector('[data-testid="p2d2-compteurs"]');
    const cases = Array.from(grille.children).map((d) => (d.textContent || '').trim());
    expect(cases).toEqual(['0Réservations', '0Personnes', '0Présences', '0Conversions']);
    expect(texte()).not.toContain('indisponibles');
    expect(texte()).not.toContain('Erreur');
  });

  // --- I : une erreur n'emporte pas le lien ------------------------------
  test('I. erreur API : le lien, le QR et la microcopy RESTENT visibles', async () => {
    router(accepteD2(), new Error('reseau'));
    await monterFiche();
    expect(texte()).toContain('Résultats momentanément indisponibles');
    expect(conteneur.querySelector('[data-testid="lien-partenaire"]')).not.toBeNull();
    expect(texte()).toContain('utm_content=akoko_tresses');
    expect(bouton('Copier')).toBeTruthy();
    expect(bouton('QR code')).toBeTruthy();
    expect(texte()).toContain('Partagez votre invitation Afroboost');
  });

  test('E-bis. 403 : etat d\'erreur ordinaire, aucun contournement d\'authentification',
    async () => {
      router(accepteD2(), Object.assign(new Error('403'), { response: { status: 403 } }));
      await monterFiche();
      expect(texte()).toContain('Résultats momentanément indisponibles');
      // Aucun en-tete d'authentification pose a la main, meme apres un refus.
      const appel = axios.get.mock.calls.find((c) => String(c[0]).includes('/partners/'));
      expect(appel).toHaveLength(1);
    });

  test('une reponse d\'une AUTRE route n\'est pas rendue comme « 0 »', async () => {
    router(accepteD2(), { applications: [], total: 0 });
    await monterFiche();
    expect(texte()).toContain('Résultats momentanément indisponibles');
    expect(conteneur.querySelector('[data-testid="p2d2-compteurs"]')).toBeNull();
  });

  // --- J : reessayer -----------------------------------------------------
  test('J. « Actualiser » relance UN appel propre, sans duplication', async () => {
    router(accepteD2(), (n) => (n === 1 ? new Error('reseau') : STATS_REELLES));
    await monterFiche();
    expect(texte()).toContain('Résultats momentanément indisponibles');
    expect(appelsStats()).toHaveLength(1);

    await cliquer(bouton('Actualiser'));
    expect(appelsStats()).toHaveLength(2);
    expect(texte()).not.toContain('Résultats momentanément indisponibles');
    const grille = conteneur.querySelector('[data-testid="p2d2-compteurs"]');
    expect(Array.from(grille.children)).toHaveLength(4);
  });

  // --- K : aucune donnee personnelle -------------------------------------
  test('K. aucune PII dans la zone des resultats', async () => {
    router(accepteD2(), {
      ...STATS_REELLES,
      // Meme si le serveur en renvoyait un jour, l'ecran ne le rendrait pas :
      // il ne lit que les champs agreges, nommement.
      userEmail: 'ne-doit-pas-sortir@exemple.test',
      discountCode: 'AFR-NEDOITPASSORTIR',
      participants: [{ name: 'Nom Interdit', email: 'x@exemple.test' }],
    });
    await monterFiche();
    const t = texte();
    expect(t).not.toContain('ne-doit-pas-sortir@exemple.test');
    expect(t).not.toContain('AFR-NEDOITPASSORTIR');
    expect(t).not.toContain('Nom Interdit');
    expect(t).not.toMatch(/AFR-[A-Z0-9]{6}/);
  });

  // --- L : aucun minuteur ------------------------------------------------
  test('L. aucun minuteur n\'est arme par ce composant', async () => {
    const si = jest.spyOn(global, 'setInterval');
    router(accepteD2(), STATS_REELLES);
    await monterFiche();
    await cliquer(bouton('Actualiser'));
    expect(si).not.toHaveBeenCalled();
    si.mockRestore();
  });

  test('L-bis. le fichier livre ne contient AUCUN minuteur', () => {
    const fs = require('fs');
    const path = require('path');
    const brut = fs.readFileSync(
      path.join(__dirname, '..', 'PartnerApplications.js'), 'utf8');
    // Commentaires retires : ceux du lot CITENT le mot pour l'interdire, et un
    // balayage naif se piegerait lui-meme sur sa propre documentation.
    const code = brut.replace(/\/\*[\s\S]*?\*\//g, '')
      .split('\n').filter((l) => !l.trim().startsWith('//')).join('\n');
    expect(code).not.toContain('setInterval');
    expect(code).not.toContain('setTimeout(charger');
  });

  // --- ce que les gardes P2-A / P2-B protegeaient, repris ici -------------
  test('aucune metrique de CLICS : P2-D1 n\'en fournit pas, on n\'en invente pas',
    async () => {
      router(accepteD2(), { ...STATS_REELLES, clicks: 42, clics: 42 });
      await monterFiche();
      expect(texte()).not.toContain('42');
      expect(texte().toLowerCase()).not.toContain('clic');
    });

  test('AUCUN calcul local : les nombres rendus sont ceux du serveur, tels quels',
    async () => {
      // Des valeurs volontairement incoherentes entre elles : 3 presences pour
      // 2 reservations. Un ecran qui recalculerait, plafonnerait ou corrigerait
      // quoi que ce soit trahirait sa propre definition de « une presence ».
      // Le serveur est la seule autorite ; l'ecran le montre, meme bizarre.
      router(accepteD2(), {
        ...STATS_REELLES, reservations: 2, unique_people: 5, attendances: 3,
        conversions: { pulse: 1, member: 1, subscription: 1, total: 2 },
        attendance_rate: 0.9, conversion_rate: 0.1,
      });
      await monterFiche();
      const grille = conteneur.querySelector('[data-testid="p2d2-compteurs"]');
      const cases = Array.from(grille.children).map((d) => (d.textContent || '').trim());
      expect(cases).toEqual(['2Réservations', '5Personnes', '3Présences', '2Conversions']);
      // Le total affiche est celui du serveur (2), PAS la somme 1+1+1 = 3.
      expect(cases[3]).toBe('2Conversions');
      // Les taux ne sont pas recalcules depuis les compteurs (3/2 = 150 %).
      expect(texte()).toContain('Taux de présence 90 %');
      expect(texte()).not.toContain('150 %');
    });

  test('le fichier livre ne calcule aucune statistique lui-meme', () => {
    const fs = require('fs');
    const path = require('path');
    const brut = fs.readFileSync(
      path.join(__dirname, '..', 'PartnerApplications.js'), 'utf8');
    const code = brut.replace(/\/\*[\s\S]*?\*\//g, '')
      .split('\n').filter((l) => !l.trim().startsWith('//')).join('\n');
    // Le bloc P2-D2 seul : ni division, ni accumulation, ni `reduce`.
    const bloc = code.split('const StatsPartenaire')[1].split('const BoutonAction')[0];
    expect(bloc).not.toMatch(/\.reduce\(/);
    expect(bloc).not.toMatch(/reservations\s*\/|attendances\s*\//);
    expect(bloc).not.toContain('* 100');
  });

  // --- M : la microcopy partenaire ---------------------------------------
  test('M. la microcopy partenaire est intacte, mot pour mot', async () => {
    router(accepteD2(), STATS_REELLES);
    await monterFiche();
    expect(texte()).toContain(
      "Partagez votre invitation Afroboost. Votre communauté s'inscrit et "
      + 'réserve directement sa séance.');
  });

  // --- le cycle de vie du partenaire n'est pas touche ---------------------
  test('le statut partenaire n\'est JAMAIS ecrit par cet ecran', async () => {
    router(accepteD2(), STATS_REELLES);
    await monterFiche();
    await cliquer(bouton('Actualiser'));
    expect(axios.patch).not.toHaveBeenCalled();
    expect(axios.post).not.toHaveBeenCalled();
    expect(axios.put).not.toHaveBeenCalled();
  });

  test('etat CHARGEMENT visible avant la reponse', async () => {
    let resoudre;
    axios.get.mockImplementation((url) => (String(url).includes('/partners/')
      ? new Promise((r) => { resoudre = r; })
      : Promise.resolve(accepteD2())));
    await monterFiche();
    expect(texte()).toContain('Chargement des résultats…');
    await act(async () => { resoudre({ data: STATS_REELLES }); });
    expect(texte()).not.toContain('Chargement des résultats…');
  });
});
