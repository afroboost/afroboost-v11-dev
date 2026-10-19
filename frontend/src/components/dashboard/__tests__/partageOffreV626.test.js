/**
 * V626 — chaque offre du coach a son lien : « Copier le lien » + « Partager ».
 * UNE OFFRE = UN LIEN STABLE (`/?offre=<id>`), réutilisé tel quel — aucun jeton.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import OfferCard from '../OfferCard';
import { urlOffre, offrePartageable, texteOffre, partagerOffre } from '../../../utils/partageOffre';

jest.mock('axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));

const act = React.act;
const base = { id: 'o-essai', name: "Cours d'essai GRATUIT", price: 0, visible: true, offer_type: 'single_class' };
const props = { onEdit: () => {}, onDuplicate: () => {}, onDelete: () => {}, onToggleVisible: () => {} };

let host; let root;
function monter(offer, extra = {}) {
  host = document.createElement('div'); document.body.appendChild(host);
  root = createRoot(host);
  act(() => { root.render(<OfferCard offer={offer} {...props} {...extra} />); });
  return host;
}
afterEach(() => { act(() => root && root.unmount()); if (host) host.remove(); host = null; root = null; jest.restoreAllMocks(); delete navigator.share; });

describe('utilitaire', () => {
  test('lien stable = /?offre=<id>, identique à chaque appel', () => {
    expect(urlOffre(base, 'https://afroboost.com')).toBe('https://afroboost.com/?offre=o-essai');
    expect(urlOffre(base, 'https://afroboost.com')).toBe(urlOffre(base, 'https://afroboost.com'));
  });
  test('partageable : visible, non archivée, pas un produit ; privée oui', () => {
    expect(offrePartageable(base)).toBe(true);
    expect(offrePartageable({ ...base, link_only: true })).toBe(true);
    expect(offrePartageable({ ...base, visible: false })).toBe(false);
    expect(offrePartageable({ ...base, archived: true })).toBe(false);
    expect(offrePartageable({ ...base, isProduct: true })).toBe(false);
    expect(offrePartageable({ name: 'sans id' })).toBe(false);
  });
  test('texte de partage = nom de l’offre', () => {
    expect(texteOffre({ name: 'Mensuel Liberté' })).toBe('Mensuel Liberté — réserve ta place sur Afroboost');
  });
  test('partage natif (téléphone) : le lien exact de l’offre', async () => {
    navigator.share = jest.fn(() => Promise.resolve());
    const r = await partagerOffre({ ...base, id: 'o-mensuel', name: 'Mensuel' });
    expect(navigator.share).toHaveBeenCalledWith({ title: 'Mensuel', text: 'Mensuel — réserve ta place sur Afroboost', url: `${window.location.origin}/?offre=o-mensuel` });
    expect(r.methode).toBe('share');
  });
  test('sans partage natif (ordinateur) : WhatsApp avec le lien, et copie', async () => {
    const ouvrir = jest.spyOn(window, 'open').mockImplementation(() => null);
    const r = await partagerOffre({ ...base, id: 'o-flex', name: 'Flex 4' });
    expect(r.methode).toBe('whatsapp');
    expect(ouvrir.mock.calls[0][0]).toContain('https://wa.me/?text=');
    expect(decodeURIComponent(ouvrir.mock.calls[0][0])).toContain(`${window.location.origin}/?offre=o-flex`);
  });
});

describe('carte d’offre du tableau de bord', () => {
  test('essai gratuit, offre payante, abonnement : les deux boutons', () => {
    for (const o of [base, { ...base, id: 'o-unite', name: 'Cours à l’unité', price: 30 }, { ...base, id: 'o-abo', name: 'Mensuel', price: 89, offer_type: 'subscription' }]) {
      const h = monter(o);
      expect(h.querySelector(`[data-testid="offer-copy-link-${o.id}"]`).textContent).toContain('Copier le lien');
      expect(h.querySelector(`[data-testid="offer-share-${o.id}"]`).textContent).toContain('Partager');
      act(() => root.unmount()); host.remove(); root = null; host = null;
    }
  });
  test('offre masquée, archivée, produit : aucun bouton de partage', () => {
    for (const o of [{ ...base, id: 'h', visible: false }, { ...base, id: 'a', archived: true }, { ...base, id: 'p', isProduct: true }]) {
      const h = monter(o);
      expect(h.querySelector(`[data-testid="offer-partage-${o.id}"]`)).toBeNull();
      act(() => root.unmount()); host.remove(); root = null; host = null;
    }
  });
  test('offre d’un autre coach (non supprimable) : pas de partage', () => {
    const h = monter(base, { canDelete: false });
    expect(h.querySelector('[data-testid="offer-partage-o-essai"]')).toBeNull();
  });
  test('offre privée : badge conservé, un seul bouton de copie (pas de doublon)', () => {
    const h = monter({ ...base, link_only: true });
    expect(h.querySelector('[data-testid="offer-link-only-o-essai"]').textContent).toContain('Privée — sur lien');
    expect(h.querySelectorAll('[data-testid="offer-copy-link-o-essai"]').length).toBe(1);
  });
  test('les boutons existants restent : Modifier, Dupliquer, Supprimer', () => {
    const h = monter(base);
    expect(h.textContent).toContain('Modifier');
    expect(h.querySelector('[title="Dupliquer"]')).not.toBeNull();
    expect(h.querySelector('[title="Supprimer"]')).not.toBeNull();
  });
  test('« Copier le lien » copie l’URL exacte et affiche « Lien copié ! »', async () => {
    const ecrire = jest.fn(() => Promise.resolve());
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: ecrire }, configurable: true });
    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });
    const h = monter({ ...base, id: 'o-unite', price: 30 });
    const btn = h.querySelector('[data-testid="offer-copy-link-o-unite"]');
    await act(async () => { btn.click(); await new Promise((r) => setTimeout(r, 0)); });
    expect(ecrire).toHaveBeenCalledWith(`${window.location.origin}/?offre=o-unite`);
    expect(btn.textContent).toContain('Lien copié !');
  });
});
