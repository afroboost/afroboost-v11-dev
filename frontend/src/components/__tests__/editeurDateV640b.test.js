/**
 * V640b — les champs date et heure de l'éditeur d'invitation sont TOUJOURS
 * déverrouillés, même sans cours lié (cas exact de Hétaïra).
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn(), put: jest.fn(), create: jest.fn(), interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } } }));
jest.mock('../coach/InvitationMiniature', () => function Mini() { return null; });
// eslint-disable-next-line import/first
import axios from 'axios';
// eslint-disable-next-line import/first
import EditeurInvitation from '../coach/EditeurInvitation';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let conteneur = null; let racine = null;
function rendre(el) { conteneur = document.createElement('div'); document.body.appendChild(conteneur); racine = createRoot(conteneur); racine.render(el); }
afterEach(() => { if (racine) act(() => racine.unmount()); if (conteneur) conteneur.remove(); racine = null; conteneur = null; jest.clearAllMocks(); });
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
async function attendre(fn) { let e; for (let i = 0; i < 40; i += 1) { try { fn(); return; } catch (x) { e = x; } await act(async () => { await new Promise((r) => setTimeout(r, 25)); }); } throw e; }

// Hétaïra = event_paid SANS course_id → le serveur renvoie date_modifiable: true après V640b-fix
const EVT_SANS_COURS = {
  date: '2026-11-15', heure: '18:45', lieu: 'Neuchâtel',
  date_modifiable: true, cours_recurrent: false,
  tarifs: { prevente: 25, standard: 30, derniere_minute: 40,
    libelles: { prevente: 'Prévente', standard: 'Standard', derniere_minute: 'Dernière minute' },
    fin_prevente: '2026-11-08T18:45', fin_standard: '2026-11-14T18:45', debut_evenement: '2026-11-15T18:45',
    prix_actif: 30, palier_actif: 'standard' },
  membres: null, participants: { reservations: 0, paiements: 0 },
  avantages: null, urgence: null,
};
const INV_HETAIRA = {
  id: 'HETAIRA', type: 'event_paid', status: 'active', title: 'Hétaïra',
  subtitle: '', description: null, message: null, cta_label: '',
  image_url: null, image_source: 'default', video_url: null, audio_url: null, audio_partage_url: null,
  share_url: 'https://afroboost.com/i/HET', share_token: 'HET', version: 1,
  inviter_display: { prenom: 'Bassi' },
  date_label: 'samedi 15 novembre', time_label: '18:45', lieu: 'Neuchâtel',
  prix_actif: { prix: 30, palier: 'standard', libelle: 'Standard', paliers: [] },
};

function mockEdition(inv, evt) {
  axios.get.mockImplementation((url) => {
    if (url.includes('campaigns-edition/')) return Promise.resolve({ data: { invitation: inv, evenement: evt } });
    if (url.includes('campaigns-medias')) return Promise.resolve({ data: { items: [] } });
    return Promise.resolve({ data: {} });
  });
}

describe('V640b — date/heure toujours modifiables', () => {
  async function ouvrirSection() {
    await attendre(() => expect(q('ed-titre')).toBeTruthy());
    await act(async () => { q('edit-section-evenement-titre').click(); });
    await attendre(() => expect(q('ed-date')).toBeTruthy());
  }

  test('événement SANS cours lié (Hétaïra) : date et heure déverrouillées', async () => {
    mockEdition(INV_HETAIRA, EVT_SANS_COURS);
    await act(async () => { rendre(React.createElement(EditeurInvitation, { invitationId: 'HETAIRA', onClose: () => {} })); });
    await ouvrirSection();
    expect(q('ed-date').disabled).toBe(false);
    expect(q('ed-heure').disabled).toBe(false);
    expect(q('ed-date').value).toBe('2026-11-15');
    expect(q('ed-heure').value).toBe('18:45');
  });

  test('événement avec cours récurrent : date et heure déverrouillées', async () => {
    mockEdition(INV_HETAIRA, { ...EVT_SANS_COURS, cours_recurrent: true });
    await act(async () => { rendre(React.createElement(EditeurInvitation, { invitationId: 'HETAIRA', onClose: () => {} })); });
    await ouvrirSection();
    expect(q('ed-date').disabled).toBe(false);
    expect(q('ed-heure').disabled).toBe(false);
  });

  test('invitation archivée : date et heure verrouillées', async () => {
    mockEdition({ ...INV_HETAIRA, status: 'archived' }, EVT_SANS_COURS);
    await act(async () => { rendre(React.createElement(EditeurInvitation, { invitationId: 'HETAIRA', onClose: () => {} })); });
    await attendre(() => expect(q('ed-titre')).toBeTruthy());
    // Section archivée : le titre s'affiche mais les champs sont verrouillés
    await act(async () => { q('edit-section-evenement-titre').click(); });
    await attendre(() => expect(q('ed-date')).toBeTruthy());
    expect(q('ed-date').disabled).toBe(true);
    expect(q('ed-heure').disabled).toBe(true);
  });

  test('RÉGRESSION : date_modifiable=false bloque les champs', async () => {
    mockEdition(INV_HETAIRA, { ...EVT_SANS_COURS, date_modifiable: false });
    await act(async () => { rendre(React.createElement(EditeurInvitation, { invitationId: 'HETAIRA', onClose: () => {} })); });
    await attendre(() => expect(q('ed-titre')).toBeTruthy());
    await act(async () => { q('edit-section-evenement-titre').click(); });
    await attendre(() => expect(q('ed-date')).toBeTruthy());
    expect(q('ed-date').disabled).toBe(true);
    expect(q('ed-heure').disabled).toBe(true);
  });
});
