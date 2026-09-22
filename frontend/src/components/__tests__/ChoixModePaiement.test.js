// V535 — « Choisis ton mode de paiement » : aucune présélection, choix explicite, montants dérivés de l'offre.
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react';
import ChoixModePaiement from '../ChoixModePaiement';

let conteneur, racine;
beforeEach(() => { conteneur = document.createElement('div'); document.body.appendChild(conteneur); });
afterEach(() => { if (racine) act(() => racine.unmount()); racine = null; conteneur.remove(); });
const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
async function monter(el) { await act(async () => { racine = createRoot(conteneur); racine.render(el); }); }
const M8 = { name: 'Membres — 8 mois', price: 199.99, billing_mode: 'saison_2x', full_payment_available: true, installment_interval_months: 1 };

describe('V535 ChoixModePaiement', () => {
  test('deux options, AUCUNE présélectionnée, « Continuer » désactivé tant que rien n’est choisi', async () => {
    const onChoisir = jest.fn();
    await monter(<ChoixModePaiement offre={M8} onChoisir={onChoisir} />);
    expect(par('mode-paiement-full').getAttribute('data-choisi')).toBe('0');
    expect(par('mode-paiement-2x').getAttribute('data-choisi')).toBe('0');
    expect(par('mode-paiement-continuer').disabled).toBe(true);
    expect(conteneur.textContent).toContain('399,98 CHF');
    expect(conteneur.textContent).toContain('199,99 CHF aujourd’hui puis 199,99 CHF dans 1 mois');
    await act(async () => { par('mode-paiement-continuer').click(); });
    expect(onChoisir).not.toHaveBeenCalled();
  });
  test('choisir « en 2 fois » puis Continuer → onChoisir("2x") ; « intégral » → "full"', async () => {
    const onChoisir = jest.fn();
    await monter(<ChoixModePaiement offre={M8} onChoisir={onChoisir} />);
    await act(async () => { par('mode-paiement-2x').querySelector('input').click(); });
    expect(par('mode-paiement-2x').getAttribute('data-choisi')).toBe('1');
    await act(async () => { par('mode-paiement-continuer').click(); });
    expect(onChoisir).toHaveBeenCalledWith('2x');
    await act(async () => { par('mode-paiement-full').querySelector('input').click(); });
    await act(async () => { par('mode-paiement-continuer').click(); });
    expect(onChoisir).toHaveBeenLastCalledWith('full');
  });
  test('offre sans choix → rien n’est rendu ; occupé → tout est désactivé', async () => {
    await monter(<ChoixModePaiement offre={{ price: 299, billing_mode: 'saison_2x' }} onChoisir={jest.fn()} />);
    expect(par('choix-mode-paiement')).toBeNull();
    await monter(<ChoixModePaiement offre={M8} onChoisir={jest.fn()} occupe />);
    expect(par('mode-paiement-continuer').disabled).toBe(true);
  });
});
