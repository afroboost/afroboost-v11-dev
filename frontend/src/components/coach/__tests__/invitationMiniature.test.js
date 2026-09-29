/**
 * INV-3 — InvitationMiniature : défaut affiché, envoi → recadrage 1200×630 →
 * onChange({image_url, image_source:'upload'}), retour au défaut, erreur +
 * Réessayer, onBusyChange(true/false). Aucun réseau : `uploadToCloudinary`
 * et `react-easy-crop` sont mockés ; le canvas est simulé (jsdom n'en a pas).
 */
import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react';

const upload = { impl: null, appels: [] };
jest.mock('../../CloudinaryUploadButton', () => ({
  __esModule: true,
  default: () => null,
  uploadToCloudinary: (file, opts) => { upload.appels.push({ file, opts }); return upload.impl(file, opts); },
}));
jest.mock('react-easy-crop', () => {
  const mockReact = require('react');
  return {
    __esModule: true,
    default: ({ onCropComplete, aspect }) => {
      mockReact.useEffect(() => { onCropComplete({}, { x: 10, y: 20, width: 1600, height: 840 }); }, []); // eslint-disable-line react-hooks/exhaustive-deps
      return mockReact.createElement('div', { 'data-testid': 'fake-cropper', 'data-aspect': String(aspect) });
    },
  };
});

global.IS_REACT_ACT_ENVIRONMENT = true;
const InvitationMiniature = require('../InvitationMiniature').default;

let racine; let conteneur; let dernier; let busyLog; let changes;
function Harnais({ initial }) {
  const [c, setC] = useState(initial || { image_url: null, image_source: 'default' });
  dernier = c;
  return (
    <InvitationMiniature value={c.image_url} source={c.image_source} defaultUrl="/logo512.png"
      onChange={(p) => { changes.push(p); setC(p); }} onBusyChange={(b) => busyLog.push(b)} />
  );
}
const q = (sel) => conteneur.querySelector(sel);
const clic = async (sel) => { await act(async () => { q(sel).dispatchEvent(new MouseEvent('click', { bubbles: true })); }); };
async function monter(initial) { await act(async () => { racine.render(<Harnais initial={initial} />); }); }
async function choisirFichier(file) {
  const input = q('[data-testid="inv-mini-input"]');
  Object.defineProperty(input, 'files', { value: [file], configurable: true });
  await act(async () => { input.dispatchEvent(new Event('change', { bubbles: true })); });
}
const defer = () => { let r, j; const p = new Promise((a, b) => { r = a; j = b; }); return { p, r, j }; };
const imageFile = () => new File([new Uint8Array(2048)], 'photo.png', { type: 'image/png' });

let canvasTaille; let origImage; let origGetContext; let origToBlob; let drawArgs;
beforeEach(() => {
  conteneur = document.createElement('div'); document.body.appendChild(conteneur); racine = createRoot(conteneur);
  let nUrl = 0;
  global.URL.createObjectURL = jest.fn(() => { nUrl += 1; return 'blob:source-' + nUrl; });
  global.URL.revokeObjectURL = jest.fn();
  upload.impl = null; upload.appels = []; busyLog = []; changes = []; canvasTaille = null; drawArgs = null;
  origImage = global.Image;
  global.Image = class { set src(v) { this._src = v; setTimeout(() => this.onload && this.onload(), 0); } get src() { return this._src; } };
  origGetContext = HTMLCanvasElement.prototype.getContext;
  origToBlob = HTMLCanvasElement.prototype.toBlob;
  HTMLCanvasElement.prototype.getContext = function () { return { drawImage: (...a) => { drawArgs = a; } }; };
  HTMLCanvasElement.prototype.toBlob = function (cb) { canvasTaille = [this.width, this.height]; cb(new Blob(['jpg'], { type: 'image/jpeg' })); };
});
afterEach(() => {
  act(() => racine.unmount()); conteneur.remove();
  global.Image = origImage;
  HTMLCanvasElement.prototype.getContext = origGetContext;
  HTMLCanvasElement.prototype.toBlob = origToBlob;
});

async function recadrerEtValider() {
  await choisirFichier(imageFile());
  expect(q('[data-testid="fake-cropper"]')).not.toBeNull();
  await act(async () => {
    q('[data-testid="inv-mini-recadrer-valider"]').dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await new Promise((r) => setTimeout(r, 5));
  });
}

test('A. par défaut : miniature par défaut affichée, pas de bouton « revenir », pas d\'erreur', async () => {
  await monter();
  expect(q('[data-testid="inv-mini"]').getAttribute('data-source')).toBe('default');
  expect(q('[data-testid="inv-mini-image"]').getAttribute('src')).toBe('/logo512.png');
  expect(q('[data-testid="inv-mini-choisir"]').textContent).toMatch(/Choisir une image/);
  expect(q('[data-testid="inv-mini-defaut"]')).toBeNull();
  expect(q('[data-testid="inv-mini-erreur"]')).toBeNull();
});

test('B. choisir → recadrer 1200×630 → envoi avec progression → onChange(upload) ; busy true puis false', async () => {
  const d = defer();
  upload.impl = async (file, opts) => { opts.onProgress(40); await d.p; opts.onProgress(100); return { url: '/api/files/abc/invitation.jpg', resourceType: 'image' }; };
  await monter();
  await recadrerEtValider();
  expect(q('[data-testid="fake-cropper"]')).toBeNull();
  expect(canvasTaille).toEqual([1200, 630]);
  expect(drawArgs.slice(1)).toEqual([10, 20, 1600, 840, 0, 0, 1200, 630]);
  expect(q('[data-testid="inv-mini-progression"]').textContent).toMatch(/40 %/);
  expect(busyLog).toContain(true);
  expect(upload.appels[0].file.type).toBe('image/jpeg');
  await act(async () => { d.r(); await d.p; });
  expect(changes[changes.length - 1]).toEqual({ image_url: '/api/files/abc/invitation.jpg', image_source: 'upload' });
  expect(busyLog[busyLog.length - 1]).toBe(false);
  expect(q('[data-testid="inv-mini-image"]').getAttribute('src')).toBe('/api/files/abc/invitation.jpg');
  expect(q('[data-testid="inv-mini-choisir"]').textContent).toMatch(/Remplacer/);
});

test('C. le recadreur est au ratio 1200/630', async () => {
  await monter();
  await choisirFichier(imageFile());
  expect(Number(q('[data-testid="fake-cropper"]').getAttribute('data-aspect'))).toBeCloseTo(1200 / 630, 5);
});

test('D. « Revenir à l\'image par défaut » → onChange({image_url:null, image_source:"default"})', async () => {
  await monter({ image_url: '/api/files/x/perso.jpg', image_source: 'upload' });
  expect(q('[data-testid="inv-mini-image"]').getAttribute('src')).toBe('/api/files/x/perso.jpg');
  await clic('[data-testid="inv-mini-defaut"]');
  expect(changes[changes.length - 1]).toEqual({ image_url: null, image_source: 'default' });
  expect(q('[data-testid="inv-mini-image"]').getAttribute('src')).toBe('/logo512.png');
  expect(dernier.image_source).toBe('default');
});

test('E. erreur d\'envoi → message + Réessayer, qui renvoie le même recadrage et réussit', async () => {
  let n = 0;
  upload.impl = async () => { n += 1; if (n === 1) throw new Error('Réseau indisponible'); return { url: '/api/files/ok/i.jpg' }; };
  await monter();
  await recadrerEtValider();
  expect(q('[data-testid="inv-mini-erreur"]').textContent).toMatch(/Réseau indisponible/);
  expect(q('[data-testid="inv-mini"]').getAttribute('data-etat')).toBe('error');
  expect(changes).toEqual([]);
  await act(async () => { q('[data-testid="inv-mini-reessayer"]').dispatchEvent(new MouseEvent('click', { bubbles: true })); });
  expect(n).toBe(2);
  expect(changes[changes.length - 1]).toEqual({ image_url: '/api/files/ok/i.jpg', image_source: 'upload' });
  expect(q('[data-testid="inv-mini-erreur"]')).toBeNull();
});

test('F. format ou taille refusés : message, aucun envoi', async () => {
  await monter();
  await choisirFichier(new File(['x'], 'a.gif', { type: 'image/gif' }));
  expect(q('[data-testid="inv-mini-erreur"]').textContent).toMatch(/JPG, PNG ou WEBP/);
  const gros = new File(['x'], 'g.jpg', { type: 'image/jpeg' });
  Object.defineProperty(gros, 'size', { value: 26 * 1024 * 1024 });
  await choisirFichier(gros);
  expect(q('[data-testid="inv-mini-erreur"]').textContent).toMatch(/25 Mo/);
  expect(upload.appels.length).toBe(0);
  expect(q('[data-testid="inv-mini-cropper"]')).toBeNull();
});

test('G. boutons ≥ 44 px et couleurs via var() uniquement', async () => {
  await monter({ image_url: '/api/files/x/perso.jpg', image_source: 'upload' });
  ['inv-mini-choisir', 'inv-mini-defaut'].forEach((id) => {
    expect(q('[data-testid="' + id + '"]').style.minHeight).toBe('44px');
  });
  const src = require('fs').readFileSync(require('path').join(__dirname, '..', 'InvitationMiniature.js'), 'utf8');
  const hex = (src.match(/#[0-9a-fA-F]{6}\b/g) || []);
  // Le seul hex « de marque » toléré est la valeur de secours d'un var().
  hex.forEach((h) => { if (h.toUpperCase() === '#D91CD2') expect(src).toMatch(/var\(--primary-color, #D91CD2\)/); });
  expect(hex.filter((h) => /^#(a855f7|8b5cf6|9333ea)$/i.test(h))).toEqual([]);
});

test('H. (audit P2) URL temporaires révoquées : validation, annulation, remplacement, démontage', async () => {
  upload.impl = async () => ({ url: '/api/files/ok/i.jpg' });
  await monter();
  // validation du recadrage
  await recadrerEtValider();
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:source-1');
  // annulation du recadrage
  await choisirFichier(imageFile());
  await clic('[data-testid="inv-mini-recadrer-annuler"]');
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:source-2');
  expect(q('[data-testid="inv-mini-cropper"]')).toBeNull();
  // remplacement : un 2e fichier pendant qu'un recadrage est ouvert
  await choisirFichier(imageFile());
  await choisirFichier(imageFile());
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:source-3');
  expect(URL.revokeObjectURL).not.toHaveBeenCalledWith('blob:source-4');
  // démontage avec un recadrage encore ouvert
  await act(async () => { racine.unmount(); });
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:source-4');
  racine = createRoot(conteneur);
  // chaque URL créée a été révoquée exactement une fois
  expect(URL.createObjectURL).toHaveBeenCalledTimes(4);
  expect(URL.revokeObjectURL).toHaveBeenCalledTimes(4);
});
