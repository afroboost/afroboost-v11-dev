/**
 * Modale « Invitation » de la page Campagnes (coach).
 *
 * CE QU'IL PROUVE
 *   B. la modale s'ouvre (isOpen) et montre les 4 types ;
 *   C. aucune notion de campagne d'envoi (contacts, destinataires, canal,
 *      programmation, case à cocher) aux étapes 1 et 2 ;
 *   D/E/F. trial / pass_duo / event_free : POST avec les bons champs, sans
 *      champ interdit (recipients, channel, send_at, scheduledAt, coach_id) ;
 *   G. event_paid : brouillon, pas d'« Activer », texte fuseau, partage coupé ;
 *   2e enregistrement → PUT (jamais un 2e POST) ; partage = share_url ;
 *   validation (titre vide, cours manquant) bloque « Suivant » ; 401 → reconnexion ;
 *   fermeture avec saisie non enregistrée → confirmation dans la modale.
 *
 * axios est mocké : aucun réseau. InvitationMiniature (AGENT 3) est simulée.
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import InvitationModal, { urlHttps } from '../InvitationModal';
import { TEXTE_RECONNEXION, TEXTE_FUSEAU_PALIERS, CTA_MAX } from '../../../utils/invitationCampagne';

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), patch: jest.fn(), delete: jest.fn() },
}));
jest.mock('qrcode.react', () => ({
  QRCodeSVG: (p) => <svg data-testid="qr-svg" data-value={p.value} />,
}));
jest.mock('../InvitationMiniature', () => ({
  __esModule: true,
  default: (p) => (
    <button type="button" data-testid="mock-miniature"
            onClick={() => p.onChange({ image_url: 'https://res.cloudinary.com/x/img.jpg', image_source: 'upload' })}>
      miniature
    </button>
  ),
}), { virtual: true });

const OPTIONS = {
  courses: [
    { id: 'c1', name: 'Afroboost Dimanche', location: 'Bord du Lac, Auvernier', time: '18:30', weekday: 0 },
    { id: 'c2', name: 'Afroboost Mercredi', location: 'Neuchâtel', time: '19h15', weekday: 3 },
  ],
  offers: [
    { id: 'free1', name: 'Essai offert', price: 0, is_free: true },
    { id: 'pay1', name: 'Soirée spéciale', price: 30, is_free: false, has_progressive_pricing: true,
      price_early_bird: 20, price_standard: 30, price_last_minute: 40 },
  ],
};
const DATE = '2030-10-06';
const INTERDITS = ['recipients', 'channel', 'send_at', 'scheduledAt', 'coach_id'];

function dto(extra) {
  return Object.assign({
    id: 'inv-1', type: 'trial', status: 'draft', title: 'T', message: 'Viens danser !', version: 1,
    inviter_display: { prenom: 'Bassi', photo_url: null, source: 'coach' },
    share_token: 'TOK', share_url: '', card_url: '',
  }, extra || {});
}

let conteneur, racine;
beforeEach(() => {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  axios.get.mockReset(); axios.post.mockReset(); axios.put.mockReset();
  axios.get.mockImplementation((url) => {
    if (/campaigns\/options$/.test(String(url))) return Promise.resolve({ data: OPTIONS });
    if (/invite-preview/.test(String(url))) return Promise.resolve({ data: new Blob(['x'], { type: 'image/jpeg' }) });
    return Promise.resolve({ data: {} });
  });
  URL.createObjectURL = jest.fn(() => 'blob:apercu-1');
  URL.revokeObjectURL = jest.fn();
});
afterEach(() => {
  if (racine) act(() => racine.unmount());
  racine = null;
  conteneur.remove();
});

const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
async function flush() {
  await act(async () => { for (let i = 0; i < 12; i += 1) await Promise.resolve(); });
}
async function monter(props) {
  const p = Object.assign({ isOpen: true, onClose: jest.fn(), API: '', dateInitiale: DATE }, props || {});
  await act(async () => { racine = createRoot(conteneur); racine.render(<InvitationModal {...p} />); });
  await flush();
  return p;
}
async function cliquer(id) {
  const el = par(id);
  if (!el) throw new Error(`élément absent : ${id}`);
  await act(async () => { el.click(); });
  await flush();
}
async function saisir(id, valeur) {
  const el = par(id);
  if (!el) throw new Error(`champ absent : ${id}`);
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value').set;
  await act(async () => {
    setter.call(el, valeur);
    el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
  });
  await flush();
}

describe('InvitationModal — ouverture et types (B, C)', () => {
  test('fermée → rien ; ouverte → 4 types, options chargées UNE fois', async () => {
    await act(async () => { racine = createRoot(conteneur); racine.render(<InvitationModal isOpen={false} onClose={() => {}} API="" />); });
    expect(par('inv-modal')).toBeNull();
    expect(axios.get).not.toHaveBeenCalled();
    act(() => racine.unmount()); racine = null;
    await monter();
    expect(par('inv-modal')).not.toBeNull();
    ['trial', 'pass_duo', 'event_free', 'event_paid'].forEach((t) => expect(par(`inv-type-${t}`)).not.toBeNull());
    expect(axios.get.mock.calls.filter((c) => /campaigns\/options$/.test(String(c[0]))).length).toBe(1);
  });

  test('C — aucun contact, destinataire, canal, programmation ni case à cocher (étapes 1 et 2)', async () => {
    await monter();
    const verifier = () => {
      const txt = par('inv-modal').textContent;
      ['Contacts', 'Destinataires', 'WhatsApp', 'Programm', 'crédit', 'Canal'].forEach((mot) => expect(txt).not.toContain(mot));
      expect(par('inv-modal').querySelectorAll('input[type="checkbox"]').length).toBe(0);
    };
    verifier();
    for (const t of ['trial', 'pass_duo', 'event_free', 'event_paid']) {
      await cliquer(`inv-type-${t}`);
      expect(par('inv-titre')).not.toBeNull(); // étape 2
      verifier();
      await cliquer('inv-precedent');
    }
  });
});

describe('InvitationModal — création par type (D, E, F)', () => {
  test('D trial : POST type/course_id/occurrence/offer_id, sans champ interdit ; heure et lieu du cours', async () => {
    axios.post.mockResolvedValue({ data: dto() });
    await monter();
    await cliquer('inv-type-trial');
    expect(par('inv-cta').value).toBe('Réserver mon essai');
    await saisir('inv-cours', 'c1');
    expect(par('inv-heure').value).toBe('18:30');
    expect(par('inv-date').value).toBe(DATE);
    expect(par('inv-modal').textContent).toContain('Bord du Lac, Auvernier');
    await saisir('inv-offre', 'free1');
    await saisir('inv-message', 'Viens danser !');
    await cliquer('inv-suivant');
    expect(axios.post).toHaveBeenCalledTimes(1);
    const [url, corps] = axios.post.mock.calls[0];
    expect(url).toBe('/api/referral/campaigns');
    expect(corps).toMatchObject({ type: 'trial', course_id: 'c1', occurrence: `${DATE}T18:30`, offer_id: 'free1', status: 'draft' });
    INTERDITS.forEach((k) => expect(corps).not.toHaveProperty(k));
    expect(par('inv-apercu')).not.toBeNull();
  });

  test('E pass_duo : cours + occurrence, pas d\'offre', async () => {
    axios.post.mockResolvedValue({ data: dto({ type: 'pass_duo' }) });
    await monter();
    await cliquer('inv-type-pass_duo');
    expect(par('inv-offre')).toBeNull();
    await saisir('inv-cours', 'c2');
    expect(par('inv-heure').value).toBe('19:15');
    await cliquer('inv-suivant');
    const corps = axios.post.mock.calls[0][1];
    expect(corps).toMatchObject({ type: 'pass_duo', course_id: 'c2', occurrence: `${DATE}T19:15`, offer_id: null, cta_label: 'Créer mon Pass Duo' });
    INTERDITS.forEach((k) => expect(corps).not.toHaveProperty(k));
  });

  test('F event_free : offre gratuite obligatoire, cours facultatif', async () => {
    axios.post.mockResolvedValue({ data: dto({ type: 'event_free' }) });
    await monter({ dateInitiale: null });
    await cliquer('inv-type-event_free');
    await saisir('inv-offre', '');
    await cliquer('inv-suivant');
    expect(axios.post).not.toHaveBeenCalled();
    await saisir('inv-offre', 'free1');
    await cliquer('inv-suivant');
    const corps = axios.post.mock.calls[0][1];
    expect(corps).toMatchObject({ type: 'event_free', offer_id: 'free1', course_id: null, occurrence: null, cta_label: "Je m'inscris" });
  });
});

describe('InvitationModal — event_paid (G), PUT, partage', () => {
  test('G event_paid : brouillon, paliers en lecture seule, pas d\'Activer, texte fuseau, partage coupé ; 2e enregistrement → PUT', async () => {
    axios.post.mockResolvedValue({ data: dto({ type: 'event_paid' }) });
    axios.put.mockResolvedValue({ data: dto({ type: 'event_paid', version: 2 }) });
    await monter();
    await cliquer('inv-type-event_paid');
    await saisir('inv-offre', 'pay1');
    const txt = par('inv-modal').textContent;
    expect(txt).toContain('Prévente');
    expect(txt).toContain('Standard');
    expect(txt).toContain('Dernière minute');
    await cliquer('inv-suivant');
    expect(axios.post.mock.calls[0][1]).toMatchObject({ type: 'event_paid', offer_id: 'pay1', status: 'draft', occurrence: null, course_id: null });
    expect(par('inv-activer')).toBeNull();
    expect(par('inv-modal').textContent).toContain(TEXTE_FUSEAU_PALIERS);
    ['inv-whatsapp', 'inv-partager-carte', 'inv-partager', 'inv-copier', 'inv-qr'].forEach((id) => {
      expect(par(id)).not.toBeNull();
      expect(par(id).disabled).toBe(true);
    });
    await cliquer('inv-enregistrer');
    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(axios.put).toHaveBeenCalledTimes(1);
    expect(axios.put.mock.calls[0][0]).toBe('/api/referral/campaigns/inv-1');
    expect(axios.put.mock.calls[0][1]).not.toHaveProperty('type');
    // retour à l'étape 2, modification, Suivant → PUT encore, jamais un 2e POST
    await cliquer('inv-precedent');
    await saisir('inv-titre', 'Grande soirée');
    await cliquer('inv-suivant');
    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(axios.put).toHaveBeenCalledTimes(2);
    expect(axios.put.mock.calls[1][1].title).toBe('Grande soirée');
  });

  test('aperçu brouillon chargé en blob (JWT via axios), puis Activer → partage sur share_url', async () => {
    const SHARE = 'https://afroboost.com/api/share/invite/TOK?v=2';
    axios.post.mockResolvedValue({ data: dto({ type: 'pass_duo' }) });
    axios.put.mockResolvedValue({ data: dto({ type: 'pass_duo', status: 'active', version: 2, share_url: SHARE, card_url: 'https://afroboost.com/api/share/invite/TOK/carte.jpg?v=2' }) });
    const open = jest.spyOn(window, 'open').mockImplementation(() => null);
    Object.assign(navigator, { clipboard: { writeText: jest.fn().mockResolvedValue() } });
    navigator.share = jest.fn().mockResolvedValue();
    await monter();
    await cliquer('inv-type-pass_duo');
    await saisir('inv-cours', 'c1');
    await cliquer('inv-suivant');
    const appelApercu = axios.get.mock.calls.find((c) => /invite-preview\/inv-1\.jpg$/.test(String(c[0])));
    expect(appelApercu).toBeTruthy();
    expect(appelApercu[1].responseType).toBe('blob');
    expect(par('inv-apercu').querySelector('img').getAttribute('src')).toBe('blob:apercu-1');
    expect(par('inv-whatsapp').disabled).toBe(true); // brouillon : pas encore de lien
    expect(par('bandeau-invitant').textContent).toContain('Bassi');

    await cliquer('inv-activer');
    expect(axios.put.mock.calls[0][1]).toEqual({ status: 'active' });
    expect(par('inv-activer')).toBeNull();
    expect(par('inv-apercu').querySelector('img').getAttribute('src')).toContain('carte.jpg?v=2');

    await cliquer('inv-whatsapp');
    expect(open.mock.calls[0][0]).toContain(encodeURIComponent(SHARE));
    await cliquer('inv-copier');
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(SHARE);
    await cliquer('inv-partager');
    expect(navigator.share.mock.calls[0][0].url).toBe(SHARE);
    await cliquer('inv-qr');
    expect(par('qr-svg').getAttribute('data-value')).toBe(SHARE);
    open.mockRestore();
  });
});

describe('InvitationModal — validation, erreurs, fermeture', () => {
  test('titre vide ou cours manquant (trial) bloque Suivant', async () => {
    await monter();
    await cliquer('inv-type-trial');
    await saisir('inv-titre', '');
    await cliquer('inv-suivant');
    expect(axios.post).not.toHaveBeenCalled();
    expect(par('inv-titre-erreur')).not.toBeNull();
    expect(par('inv-cours-erreur')).not.toBeNull();
    expect(par('inv-titre')).not.toBeNull(); // toujours étape 2
    await saisir('inv-titre', 'Mon essai');
    await cliquer('inv-suivant');
    expect(axios.post).not.toHaveBeenCalled(); // le cours manque encore
  });

  test('401 au chargement des options → « Reconnecte-toi »', async () => {
    axios.get.mockImplementation(() => Promise.reject({ response: { status: 401 } }));
    await monter();
    expect(par('inv-modal').textContent).toContain(TEXTE_RECONNEXION);
  });

  test('403 à l\'enregistrement → « Reconnecte-toi »', async () => {
    axios.post.mockRejectedValue({ response: { status: 403 } });
    await monter();
    await cliquer('inv-type-pass_duo');
    await saisir('inv-cours', 'c1');
    await cliquer('inv-suivant');
    expect(par('inv-modal').textContent).toContain(TEXTE_RECONNEXION);
    expect(par('inv-titre')).not.toBeNull(); // on reste sur l'étape 2
  });

  test('fermer avec saisie non enregistrée → confirmation dans la modale (Échap aussi)', async () => {
    const p = await monter();
    await cliquer('inv-type-trial');
    await saisir('inv-message', 'Brouillon en cours');
    await cliquer('inv-fermer');
    expect(p.onClose).not.toHaveBeenCalled();
    expect(par('inv-confirmer-fermeture')).not.toBeNull();
    await cliquer('inv-continuer-edition');
    expect(par('inv-confirmer-fermeture')).toBeNull();
    await act(async () => { document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); });
    await flush();
    expect(par('inv-confirmer-fermeture')).not.toBeNull();
    await cliquer('inv-quitter');
    expect(p.onClose).toHaveBeenCalledTimes(1);
  });

  test('fermer sans saisie → onClose directement', async () => {
    const p = await monter();
    await cliquer('inv-fermer');
    expect(p.onClose).toHaveBeenCalledTimes(1);
  });
});

describe('InvitationModal — retours des captures (360 → 1440)', () => {
  afterEach(() => { window.innerWidth = 1024; });

  test('1 — chaque changement d\'étape remet le défilement en haut', async () => {
    axios.post.mockResolvedValue({ data: dto({ type: 'pass_duo' }) });
    await monter();
    const el = par('inv-defilement');
    let valeur = 0;
    Object.defineProperty(el, 'scrollTop', { configurable: true, get: () => valeur, set: (v) => { valeur = v; } });
    valeur = 480;
    await cliquer('inv-type-pass_duo');
    expect(valeur).toBe(0);
    await saisir('inv-cours', 'c1');
    valeur = 900; // l'étape 2 a défilé jusqu'au pied
    await cliquer('inv-suivant');
    expect(par('inv-apercu')).not.toBeNull();
    expect(valeur).toBe(0); // l'aperçu arrive en haut, jamais tronqué
  });

  test('2 — événement : pas de date du calendrier sans cours ; avec un cours, date + heure du cours', async () => {
    axios.post.mockResolvedValue({ data: dto({ type: 'event_free' }) });
    await monter();
    await cliquer('inv-type-event_free');
    expect(par('inv-date').value).toBe('');
    expect(par('inv-heure').value).toBe('');
    await cliquer('inv-suivant'); // offre unique présélectionnée : rien ne bloque
    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(axios.post.mock.calls[0][1]).toMatchObject({ occurrence: null, course_id: null });
    await cliquer('inv-precedent');
    await saisir('inv-cours', 'c1');
    expect(par('inv-date').value).toBe(DATE);
    expect(par('inv-heure').value).toBe('18:30');
  });

  test('2bis — trial / pass_duo gardent la date du calendrier', async () => {
    await monter();
    await cliquer('inv-type-event_paid');
    await cliquer('inv-precedent');
    await cliquer('inv-type-pass_duo');
    expect(par('inv-date').value).toBe(DATE);
  });

  test('3 — mobile 360 px : pied sur une ligne, Précédent en icône 44×44, « Brouillon »', async () => {
    window.innerWidth = 360;
    await monter();
    await cliquer('inv-type-pass_duo');
    const pied = par('inv-pied-boutons');
    expect(pied.style.flexWrap).toBe('nowrap');
    const prec = par('inv-precedent');
    expect(prec.getAttribute('aria-label')).toBe('Précédent');
    expect(prec.textContent.trim()).toBe('');
    expect(prec.style.width).toBe('44px');
    expect(prec.style.minHeight).toBe('44px');
    expect(par('inv-enregistrer').textContent.trim()).toBe('Brouillon');
    expect(par('inv-suivant').style.flex).toContain('1');
  });

  test('4 — lien ACTIF : plus de « brouillon » ; « Enregistrer les modifications » sans repasser en draft', async () => {
    const actif = dto({ type: 'pass_duo', status: 'active', version: 2, share_url: 'https://afroboost.com/i/T?v=2' });
    axios.post.mockResolvedValue({ data: dto({ type: 'pass_duo' }) });
    axios.put.mockResolvedValue({ data: actif });
    await monter();
    await cliquer('inv-type-pass_duo');
    await saisir('inv-cours', 'c1');
    await cliquer('inv-suivant');
    expect(par('inv-enregistrer').textContent).toContain('Enregistrer le brouillon');
    await cliquer('inv-activer');
    expect(par('inv-enregistrer')).toBeNull(); // rien à enregistrer
    await cliquer('inv-precedent');
    await saisir('inv-titre', 'Nouveau titre');
    expect(par('inv-enregistrer').textContent).toContain('Enregistrer les modifications');
    expect(par('inv-modal').textContent).not.toContain('Enregistrer le brouillon');
    await cliquer('inv-enregistrer');
    const corps = axios.put.mock.calls[axios.put.mock.calls.length - 1][1];
    expect(corps.title).toBe('Nouveau titre');
    expect(corps).not.toHaveProperty('status'); // jamais un retour en draft
    await cliquer('inv-suivant');
    expect(par('inv-enregistrer')).toBeNull();
  });

  test('CTA : 30 caractères au plus (le serveur refuse au-delà), compteur /30', async () => {
    expect(CTA_MAX).toBe(30);
    await monter();
    await cliquer('inv-type-trial');
    expect(Number(par('inv-cta').getAttribute('maxLength'))).toBe(30);
    await saisir('inv-cta', 'x'.repeat(45));
    expect(par('inv-cta').value.length).toBe(30);
    expect(par('inv-cta-compteur').textContent).toBe('30/30');
  });

  test('urlHttps : https ou chemin du même site ; jamais d\'espace, de « \\ », de « // »', () => {
    expect(urlHttps('https://res.cloudinary.com/x.jpg')).toBe('https://res.cloudinary.com/x.jpg');
    expect(urlHttps('/logo512.png')).toBe('/logo512.png');
    expect(urlHttps('//evil.com/x.jpg')).toBe('');
    expect(urlHttps('/\\evil.com')).toBe('');
    expect(urlHttps('https://a.ch/x y.jpg')).toBe('');
    expect(urlHttps('/a\\b.png')).toBe('');
    expect(urlHttps('http://a.ch/x.jpg')).toBe('');
    expect(urlHttps('javascript:alert(1)')).toBe('');
  });
});
