// V625 — PROSPECTION : 4 CORRECTIONS (liste, catégorie, fichiers, création de campagne).
//
// Le VRAI ProspectsSection, la VRAIE MediaReponse, le VRAI FilConversation.
// `axios`, `useChargement` et l'envoi de fichiers sont mockés : aucun appel réseau.
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import ProspectsSection, {
  HAUTEUR_FILE_CONVERSATIONS, libelleCategorie, cleCategorie, filtrerParCategorie, categoriesPresentes, SANS_CATEGORIE,
} from '../ProspectsSection';
import MediaReponse, { mediasDe, refusFichiers, tailleLisible, elementsBibliotheque, filtrerBibliotheque, MAX_FICHIERS } from '../prospection/MediaReponse';
import FilConversation from '../FilConversation';
import { uploadToCloudinary } from '../../CloudinaryUploadButton';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(() => Promise.resolve({ data: {} })), patch: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));
jest.mock('../../CloudinaryUploadButton', () => ({
  __esModule: true, uploadToCloudinary: jest.fn(), PDF_MAX_MO: 20,
  MESSAGE_PDF_LOURD: 'Ce PDF dépasse la taille maximale autorisée de 20 Mo.',
}));

let mockEtatParSection = null;
jest.mock('../../../hooks/useChargement', () => ({
  __esModule: true,
  SECTION: { ATTENTE: 'attente', CHARGEMENT: 'chargement', OK: 'ok', ERREUR: 'erreur', SESSION: 'session' },
  default: (sources) => {
    const sections = {};
    Object.keys(sources).forEach((cle) => {
      const e = (mockEtatParSection && mockEtatParSection[cle]) || { etat: 'ok', donnees: null };
      sections[cle] = { etat: e.etat, donnees: e.donnees, motif: 'serveur' };
    });
    return { sections, reessayer: jest.fn(), global: 'ok', donnees: {}, cles: Object.keys(sources),
             chargement: false, sessionExpiree: false };
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
  racine = null; conteneur = null; mockEtatParSection = null;
  jest.clearAllMocks();
});
const $ = (t) => document.querySelector(`[data-testid="${t}"]`);
const $$ = (t) => Array.from(document.querySelectorAll(`[data-testid="${t}"]`));
const cliquer = async (el) => { await act(async () => { el.click(); }); };
const choisirOption = async (select, valeur) => {
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set;
    setter.call(select, valeur);
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
};

// --- 50 conversations, dont Troodi / Centre Momboye / AGEF (catégories RÉELLES de prod, lues le 19/10) ---
const VRAIES = [
  { org: 'Troodi', categorie: 'commerce', pid: 'p-troodi' },
  { org: 'Centre Momboye', categorie: 'ecole_danse', pid: 'p-momboye' },
  { org: 'AGEF — Association générale des étudiant·e·s', categorie: 'communaute_etudiante', pid: 'p-agef' },
];
function conversation(i, sur) {
  const id = `m-${i}`;
  const action = `a-${i}`;
  const msg = { id, action_id: action, recipient_key: action, from_email: `${action}@ex.test`, subject: 'Re: Proposition',
                body_text: 'Bonjour', received_at: '2026-10-14T05:25:19+00:00', statut: 'rattache', read_at: '2026-10-14T06:00:00+00:00' };
  return Object.assign({
    cle: action, action_id: action, organisation: `Partenaire ${i}`, recipient_key: action, from_email: msg.from_email,
    nb_messages: 1, message_ids: [id], non_lues: 0, statut_commercial: 'en_attente', intention: '',
    dernier_message: msg, dernier_message_at: msg.received_at, messages_recus: [msg], derniere_reponse_afroboost: null,
    reponse_apres_dernier_message: false, rang: 4, prospect_id: `p-${i}`,
    categorie: i % 3 === 0 ? 'association' : (i % 3 === 1 ? 'festival' : null),
  }, sur || {});
}
function cinquante() {
  const convs = [];
  for (let i = 0; i < 50; i += 1) {
    const v = VRAIES[i];
    convs.push(conversation(i, v ? { organisation: v.org, categorie: v.categorie, prospect_id: v.pid } : {}));
  }
  return convs;
}
function servir(conversations, campagnes) {
  mockEtatParSection = {
    prospects: { etat: 'ok', donnees: { total: 1, returned: 1, limit: 25, offset: 0, counts: { total: 1 },
      prospects: [{ id: 'p-x', organisation_name: 'X', category: 'association', status: 'a_contacter' }] } },
    campagnes: { etat: 'ok', donnees: { total: (campagnes || []).length, campaigns: campagnes || [] } },
    reponses: { etat: 'ok', donnees: { messages: conversations.map((c) => c.dernier_message), total: conversations.length,
      a_rattacher: 0, conversations, conversations_total: conversations.length,
      conversations_counts: { total: conversations.length, en_attente: conversations.length } } },
  };
}

describe('V625 — fonctions pures', () => {
  test('catégorie : libellé, « Non classé », filtre, catégories présentes', () => {
    expect(libelleCategorie('commerce')).toBe('Commerce');
    expect(libelleCategorie('ecole_danse')).toBe('École de danse');
    expect(libelleCategorie('communaute_etudiante')).toBe('Communauté étudiante');
    expect(libelleCategorie(null)).toBe('Non classé');
    expect(cleCategorie({ categorie: 'inconnue' })).toBe(SANS_CATEGORIE);
    const c = cinquante();
    expect(filtrerParCategorie(c, '')).toHaveLength(50);
    expect(filtrerParCategorie(c, 'association').every((x) => x.categorie === 'association')).toBe(true);
    const pres = categoriesPresentes(c);
    expect(pres[pres.length - 1]).toMatchObject({ cle: SANS_CATEGORIE, libelle: 'Non classé' });
  });
  test('fichiers : ancien `media` seul lu comme une liste, contrôle avant envoi', () => {
    expect(mediasDe({ media: { type: 'video', url: '/api/files/a1/v.mp4' } })).toHaveLength(1);
    expect(mediasDe({ medias: [], media: { type: 'video', url: '/api/files/a1/v.mp4' } })).toHaveLength(0);
    expect(mediasDe({ media: { type: 'video', url: 'javascript:alert(1)' } })).toHaveLength(0);
    expect(mediasDe(null)).toEqual([]);
    const pdf = (taille) => ({ type: 'application/pdf', size: taille, name: 'b.pdf' });
    expect(refusFichiers([pdf(21 * 1024 * 1024)], 6)).toBe('Ce PDF dépasse la taille maximale autorisée de 20 Mo.');
    expect(refusFichiers([pdf(1024)], 6)).toBe('');
    expect(refusFichiers([{ type: 'text/plain', size: 1 }], 6)).toMatch(/PDF/);
    expect(refusFichiers([pdf(1), pdf(1)], 1)).toMatch(/Encore 1 fichier/);
    expect(MAX_FICHIERS).toBe(6);
    expect(tailleLisible(1572864)).toBe('1,5 Mo');
  });
  test('bibliothèque : un PDF est un « document » (nom, taille, date), filtre Documents', () => {
    const el = elementsBibliotheque([{ id: 'd1', niche: 'B', format: 'document', statut: 'en_cours', url: '/api/files/d1/document_d1.pdf',
                                       created_at: '2026-10-19T10:00:00Z', fichier: { nom: 'Brochure_Afroboost.pdf', taille: 1572864 } }], []);
    expect(el[0]).toMatchObject({ type: 'document', titre: 'Brochure Afroboost', taille: 1572864, miniature_url: null });
    expect(filtrerBibliotheque(el, 'document', '')).toHaveLength(1);
    expect(filtrerBibliotheque(el, 'video', '')).toHaveLength(0);
  });
});

describe('V625 — CORRECTIONS 1 et 2 : la liste des conversations', () => {
  test('TEST A — 50 conversations : hauteur limitée, défilement interne, détail juste dessous', async () => {
    servir(cinquante());
    await monter(<ProspectsSection API="/api" />);
    const file = $('file-conversations');
    expect($$('conversation-ligne')).toHaveLength(50);
    expect(file.style.maxHeight).toBe(HAUTEUR_FILE_CONVERSATIONS);
    expect(file.style.overflowY).toBe('auto');
    await cliquer($$('conversation-ligne')[30]);
    const nom = $('conversation-nom');
    expect(nom.textContent).toBe('Partenaire 30');
    // Le détail SUIT la liste (et non la 50e ligne d'une liste dépliée) : aucune ligne après lui.
    expect(file.compareDocumentPosition(nom) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(file.contains(nom)).toBe(false);
  });

  test('TEST B — badge catégorie de la fiche sur chaque ligne et dans l’en-tête', async () => {
    servir(cinquante());
    await monter(<ProspectsSection API="/api" />);
    const lignes = $$('conversation-ligne');
    const badge = (l) => l.querySelector('[data-testid="conversation-categorie"]').textContent;
    expect(badge(lignes[0])).toBe('Commerce');                // Troodi
    expect(badge(lignes[1])).toBe('École de danse');          // Centre Momboye
    expect(badge(lignes[2])).toBe('Communauté étudiante');    // AGEF
    expect(lignes.every((l) => l.querySelector('[data-testid="conversation-categorie"]'))).toBe(true);
    expect(badge(lignes[5])).toBe('Non classé');              // fiche sans catégorie
    await cliquer(lignes[1]);
    expect($('conversation-categorie-entete').textContent).toBe('École de danse');
  });

  test('TEST C — filtre « Association » : uniquement les prospects Association', async () => {
    servir(cinquante());
    await monter(<ProspectsSection API="/api" />);
    const select = $('filtre-categorie-conversations');
    expect(Array.from(select.options).map((o) => o.textContent)).toContain('Non classé (15)');
    await choisirOption(select, 'association');
    const lignes = $$('conversation-ligne');
    expect(lignes.length).toBeGreaterThan(0);
    expect(lignes.every((l) => l.querySelector('[data-testid="conversation-categorie"]').textContent === 'Association')).toBe(true);
    expect($('compteur-conversations').textContent).toMatch(/50 conversations/);   // les compteurs restent ceux du serveur
    await choisirOption(select, '');
    expect($$('conversation-ligne')).toHaveLength(50);
    expect(axios.get.mock.calls.some((c) => /categor/.test(String(c[0])))).toBe(false);   // filtre d'écran, aucun appel
  });

  test('TEST D — « Voir la fiche » ouvre la fiche EXISTANTE (route existante, même panneau)', async () => {
    servir(cinquante());
    axios.get.mockImplementation((url) => (url === '/api/partner-prospects/p-momboye'
      ? Promise.resolve({ data: { id: 'p-momboye', organisation_name: 'Centre Momboye', category: 'ecole_danse', status: 'repondu' } })
      : Promise.resolve({ data: {} })));
    await monter(<ProspectsSection API="/api" />);
    await cliquer($$('conversation-ligne')[1]);
    await cliquer($('voir-fiche'));
    expect(axios.get).toHaveBeenCalledWith('/api/partner-prospects/p-momboye');
    expect($$('fiche-prospect')).toHaveLength(1);
    expect($('fiche-prospect').textContent).toMatch(/Centre Momboye/);
    // aucune fiche créée : le seul POST est le marquage « lu » existant de la conversation ouverte
    expect(axios.post.mock.calls.map((c) => c[0])).toEqual(['/api/prospect-inbound/m-1/lu']);
  });

  test('sans fiche rattachée : « Non classé », pas de lien « Voir la fiche »', async () => {
    servir([conversation(1, { prospect_id: null, categorie: null })]);
    await monter(<ProspectsSection API="/api" />);
    await cliquer($('conversation-ligne'));
    expect($('conversation-categorie-entete').textContent).toBe('Non classé');
    expect($('voir-fiche')).toBeNull();
  });
});

describe('V625 — CORRECTION 3 : plusieurs fichiers (vidéos, images, PDF)', () => {
  function Hote({ onVal }) {
    const [v, setV] = React.useState([]);
    return <MediaReponse API="/api" valeur={v} onChange={(l) => { setV(l); if (onVal) onVal(l); }} />;
  }
  const fichier = (nom, type, taille) => { const f = new File(['x'], nom, { type }); Object.defineProperty(f, 'size', { value: taille }); return f; };
  async function importer(fichiers) {
    await cliquer($('ajouter-media'));
    await cliquer($('media-onglet-importer'));
    const champ = $('media-fichier');
    expect(champ.multiple).toBe(true);
    expect(champ.getAttribute('accept')).toMatch(/application\/pdf/);
    Object.defineProperty(champ, 'files', { value: fichiers, configurable: true });
    await act(async () => { champ.dispatchEvent(new Event('change', { bubbles: true })); });
  }

  test('TEST E — 1 PDF + 2 images en une fois : 3 cartes, chacune retirable, « Ajouter un autre fichier »', async () => {
    axios.get.mockResolvedValue({ data: { medias: [], niches: [] } });
    let n = 0;
    uploadToCloudinary.mockImplementation(() => { n += 1; return Promise.resolve({ url: `/api/files/f${n}/fichier_f${n}` }); });
    const valeurs = [];
    await monter(<Hote onVal={(l) => valeurs.push(l)} />);
    await importer([fichier('Brochure_Afroboost.pdf', 'application/pdf', 1572864),
                    fichier('Photo_cours.jpg', 'image/jpeg', 2000), fichier('Salle.png', 'image/png', 3000)]);
    expect(uploadToCloudinary).toHaveBeenCalledTimes(3);
    const cartes = $$('media-joint');
    expect(cartes.map((c) => c.getAttribute('data-type'))).toEqual(['document', 'image', 'image']);
    expect(cartes[0].textContent).toMatch(/DOCUMENT PDF JOINT/);
    expect(cartes[0].textContent).toMatch(/Brochure Afroboost/);
    expect(cartes[0].textContent).toMatch(/1,5 Mo/);
    expect($$('media-retirer')).toHaveLength(3);
    expect($('ajouter-autre-fichier')).not.toBeNull();
    expect(valeurs[valeurs.length - 1]).toHaveLength(3);
    await cliquer($$('media-retirer')[1]);
    expect($$('media-joint').map((c) => c.getAttribute('data-type'))).toEqual(['document', 'image']);
  });

  test('TEST F — PDF trop lourd : message clair, RIEN envoyé', async () => {
    axios.get.mockResolvedValue({ data: { medias: [], niches: [] } });
    await monter(<Hote />);
    await importer([fichier('Catalogue.pdf', 'application/pdf', 21 * 1024 * 1024)]);
    expect(uploadToCloudinary).not.toHaveBeenCalled();
    expect($('media-import-erreur').textContent).toBe('Ce PDF dépasse la taille maximale autorisée de 20 Mo.');
    expect($('media-joint')).toBeNull();
  });

  test('TEST G — le fil montre les fichiers RÉELLEMENT envoyés (3), dans l’ordre', async () => {
    const e = { id: 's1', direction: 'outgoing', type: 'manual_reply', date: '2026-10-14T14:27:00Z', text: 'Bonjour …',
                texte_garanti: true,
                media: { type: 'document', titre: 'Brochure Afroboost', url: '/api/files/d1/document_d1.pdf', taille: 1572864 },
                medias: [{ type: 'document', titre: 'Brochure Afroboost', url: '/api/files/d1/document_d1.pdf', taille: 1572864 },
                         { type: 'video', titre: 'Démonstration', url: '/api/files/v1/video_v1', miniature_url: null },
                         { type: 'image', titre: 'Photo', url: '/api/files/i1/image_i1', miniature_url: '/api/files/i1/image_i1' }] };
    await monter(<FilConversation fil={[e]} />);
    const m = $$('fil-media');
    expect(m.map((x) => x.getAttribute('data-type'))).toEqual(['document', 'video', 'image']);
    expect(m[0].textContent).toMatch(/DOCUMENT PDF ENVOYÉ/);
    expect(m[0].querySelector('a').textContent).toMatch(/Voir \/ télécharger le document/);
    expect($('fil-fichiers-envoyes').textContent).toMatch(/Fichiers envoyés \(3\)/);
  });

  test('TEST H — ancienne réponse V620 (1 vidéo, champ `media` seul) : toujours visible, identique', async () => {
    const e = { id: 's0', direction: 'outgoing', type: 'manual_reply', date: '2026-10-15T11:00:00Z', text: 'Bonjour',
                texte_garanti: true, media: { type: 'video', titre: 'Afroboost — démonstration', url: '/api/files/v0/video_v0', miniature_url: '/api/files/m0/image_m0' } };
    await monter(<FilConversation fil={[e]} />);
    const m = $$('fil-media');
    expect(m).toHaveLength(1);
    expect(m[0].textContent).toMatch(/VIDÉO ENVOYÉE/);
    expect($('fil-fichiers-envoyes')).toBeNull();
  });
});

describe('V625 — CORRECTION 4 : « Préparer une autre campagne » crée une NOUVELLE campagne', () => {
  const ANCIENNE = { id: 'c-ancienne', nom: 'J0 12-10-2026', etat: 'approuvee', nb_destinataires: 40, created_at: '2026-10-12T06:16:11Z' };
  const RESUME = { fiches: 4, destinataires: 4, exclus: 0, par_execution: { AUTO: 4 }, par_canal: { email: 4 },
                   par_langue: { FR: 4 }, sans_message_j0: 0, multi_fiches: 0 };
  async function preparerPuisCreer(campagnes, ouverteServeur) {
    servir([], campagnes);
    axios.post.mockImplementation((url, corps) => {
      if (corps && corps.dry_run) {
        return Promise.resolve({ data: { dry_run: true, campaign: { id: 'apercu-1', nom: 'Nouvelle', etat: 'preparee' },
                                         summary: RESUME, actions: [],
                                         campagne_ouverte: ouverteServeur } });
      }
      return Promise.resolve({ data: { dry_run: false, rejeu: false, campaign: { id: 'c-nouvelle', nom: 'Nouvelle', etat: 'preparee' } } });
    });
    axios.get.mockImplementation((url) => Promise.resolve({ data: url === '/api/prospect-campaigns/c-nouvelle'
      ? { campaign: { id: 'c-nouvelle', nom: 'Nouvelle', etat: 'preparee' }, summary: RESUME, actions: [] } : {} }));
    await monter(<ProspectsSection API="/api" ongletPilote="prospects" />);
    await cliquer($('preparer-campagne'));
    await cliquer($('creer-campagne'));
    await cliquer($('creer-campagne') || document.body);   // double clic : même aperçu, même clé
    return axios.post.mock.calls.filter((c) => c[1] && c[1].dry_run === false).map((c) => c[1]);
  }

  test('TEST I (écran) — une campagne ouverte existe : `allow_new` + clé stable de l’aperçu', async () => {
    const creations = await preparerPuisCreer([ANCIENNE], ANCIENNE);
    expect(creations.length).toBeGreaterThanOrEqual(1);
    creations.forEach((c) => {
      expect(c.allow_new).toBe(true);
      expect(c.idempotency_key).toBe('apercu-1');
    });
    expect($('message-campagne').textContent).toMatch(/Aucun message n'a été envoyé/);
    expect($('panneau-campagne').textContent).toMatch(/Brouillon \/ Campagne préparée — non envoyée/);
  });

  test('aucune campagne ouverte : pas de `allow_new` (garde « une seule ouverte » intacte)', async () => {
    const creations = await preparerPuisCreer([], null);
    expect(creations.length).toBeGreaterThanOrEqual(1);
    creations.forEach((c) => expect(c.allow_new).toBeUndefined());
  });

  test('l’écran ne connaît toujours aucune route d’envoi ni d’approbation automatique', async () => {
    await preparerPuisCreer([ANCIENNE], ANCIENNE);
    const urls = axios.post.mock.calls.map((c) => c[0]);
    expect(urls.every((u) => u === '/api/prospect-campaigns/prepare')).toBe(true);
  });
});
