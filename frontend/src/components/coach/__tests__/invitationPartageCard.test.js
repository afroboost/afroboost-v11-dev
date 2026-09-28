/**
 * V551 — Parrainage V2 : carte coach « Invitation & partage ».
 *
 * Meme harnais que FunnelEssaiCard.test.js : react-dom/client + React.act,
 * axios remplace par des jest.fn. Aucun reseau.
 *
 * Ce que ces tests verrouillent :
 *  - la lecture GET /referral/share-settings ;
 *  - l'enregistrement du message par PUT, SANS aucun champ d'identite
 *    (email, coach_id) : l'identite est celle du jeton, decidee par le serveur ;
 *  - le retour a l'image par defaut = PUT share_image_url:null ;
 *  - le refus COTE CLIENT d'un fichier trop lourd ou d'un mauvais type ;
 *  - un 403 affiche « Réservé au coach connecté ».
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import InvitationPartageCard, { verifierFichier, MAX_OCTETS } from '../InvitationPartageCard';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), put: jest.fn(), post: jest.fn() }
}));

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const API = '/api';
const URL_REGLAGES = '/api/referral/share-settings';

const REPONSE = {
  default_message: null,
  share_image_url: null,
  effective: {
    message: "Je t'invite à venir essayer Afroboost avec moi. Réserve ta place ici :",
    image_url: '/api/files/abc123/defaut.jpg'
  },
  defaults: { message: "Je t'invite à venir essayer Afroboost avec moi. Réserve ta place ici :" },
  updated_at: null
};

const copie = (extra) => JSON.parse(JSON.stringify({ ...REPONSE, ...extra }));

let conteneur = null;
let racine = null;

async function monter({ donnees = REPONSE, echec = null, suspendu = false } = {}) {
  axios.get.mockReset();
  axios.put.mockReset();
  axios.post.mockReset();
  if (echec) axios.get.mockRejectedValue(echec);
  else if (suspendu) axios.get.mockReturnValue(new Promise(() => {}));
  else axios.get.mockResolvedValue({ data: donnees });

  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(<InvitationPartageCard API={API} />); });
}

afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) conteneur.remove();
  racine = null;
  conteneur = null;
});

const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const texte = () => conteneur.textContent;

async function cliquer(id) {
  await act(async () => {
    par(id).dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });
}

async function saisir(id, valeur) {
  const el = par(id);
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
  await act(async () => {
    setter.call(el, valeur);
    el.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

async function choisirFichier(fichier) {
  const input = par('pv2-image-input');
  Object.defineProperty(input, 'files', { value: [fichier], configurable: true });
  await act(async () => {
    input.dispatchEvent(new Event('change', { bubbles: true }));
  });
}

function faux(nom, type, taille) {
  const f = new File(['x'], nom, { type });
  Object.defineProperty(f, 'size', { value: taille });
  return f;
}

describe('V551 — Invitation & partage (coach)', () => {
  test('I1. chargement : GET des réglages, image et message effectifs affichés', async () => {
    await monter({ suspendu: true });
    expect(par('pv2-chargement')).not.toBeNull();
    await afterEachManuel();

    await monter();
    expect(axios.get).toHaveBeenCalledWith(URL_REGLAGES);
    expect(texte()).toContain('Invitation & partage');
    expect(texte()).toContain("Image affichée dans l'aperçu WhatsApp");
    expect(par('pv2-image').getAttribute('src')).toBe('/api/files/abc123/defaut.jpg');
    expect(par('pv2-message').getAttribute('placeholder')).toBe(REPONSE.defaults.message);
    expect(par('pv2-apercu').textContent).toContain("t'invite à Afroboost");
    expect(par('pv2-apercu').textContent).toContain(REPONSE.effective.message);
  });

  test('I2. enregistrer le message : PUT default_message, jamais email/coach_id', async () => {
    await monter();
    axios.put.mockResolvedValue({ data: copie({ default_message: 'Viens danser !',
      effective: { ...REPONSE.effective, message: 'Viens danser !' } }) });
    await saisir('pv2-message', 'Viens danser !');
    expect(texte()).toContain('14 / 280');
    await cliquer('pv2-enregistrer');
    expect(axios.put).toHaveBeenCalledTimes(1);
    const [url, corps] = axios.put.mock.calls[0];
    expect(url).toBe(URL_REGLAGES);
    expect(corps).toEqual({ default_message: 'Viens danser !' });
    expect(corps).not.toHaveProperty('email');
    expect(corps).not.toHaveProperty('coach_id');
    expect(par('pv2-succes')).not.toBeNull();
  });

  test('I3. revenir au message par défaut : PUT default_message:null', async () => {
    await monter({ donnees: copie({ default_message: 'Perso' }) });
    axios.put.mockResolvedValue({ data: copie({}) });
    await cliquer('pv2-message-defaut');
    expect(axios.put).toHaveBeenCalledWith(URL_REGLAGES, { default_message: null });
  });

  test('I4. revenir à l’image par défaut : PUT share_image_url:null', async () => {
    await monter({ donnees: copie({ share_image_url: '/api/files/zz/perso.png' }) });
    axios.put.mockResolvedValue({ data: copie({}) });
    await cliquer('pv2-image-defaut');
    expect(axios.put).toHaveBeenCalledTimes(1);
    const [url, corps] = axios.put.mock.calls[0];
    expect(url).toBe(URL_REGLAGES);
    expect(corps).toEqual({ share_image_url: null });
  });

  test('I5. upload refusé côté client : > 3 Mo ou mauvais type, aucun envoi', async () => {
    await monter();
    await choisirFichier(faux('grosse.jpg', 'image/jpeg', MAX_OCTETS + 1));
    expect(axios.post).not.toHaveBeenCalled();
    expect(par('pv2-erreur').textContent).toMatch(/3 Mo/);

    await choisirFichier(faux('anim.gif', 'image/gif', 1000));
    expect(axios.post).not.toHaveBeenCalled();
    expect(par('pv2-erreur').textContent).toMatch(/JPEG, PNG ou WebP/);

    expect(verifierFichier(faux('ok.png', 'image/png', 1000))).toBeNull();
  });

  test('I6. upload valide : POST multipart champ file', async () => {
    await monter();
    axios.post.mockResolvedValue({ data: copie({ share_image_url: '/api/files/n1/x.webp',
      effective: { ...REPONSE.effective, image_url: '/api/files/n1/x.webp' } }) });
    await choisirFichier(faux('x.webp', 'image/webp', 2000));
    expect(axios.post).toHaveBeenCalledTimes(1);
    const [url, corps] = axios.post.mock.calls[0];
    expect(url).toBe(`${URL_REGLAGES}/image`);
    expect(corps).toBeInstanceOf(FormData);
    expect(corps.get('file')).toBeTruthy();
    expect(corps.get('email')).toBeNull();
    expect(corps.get('coach_id')).toBeNull();
    expect(par('pv2-image').getAttribute('src')).toBe('/api/files/n1/x.webp');
  });

  test('I7. 403 : « Réservé au coach connecté »', async () => {
    await monter({ echec: { response: { status: 403, data: { detail: 'x' } } } });
    expect(par('pv2-erreur').textContent).toContain('Réservé au coach connecté');
  });
});

async function afterEachManuel() {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) conteneur.remove();
  racine = null;
  conteneur = null;
}
