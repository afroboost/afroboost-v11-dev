/**
 * ESSAI-3 — le funnel d'essai gratuit du dashboard coach.
 *
 * Meme harnais que CourseRemindersCard.test.js : react-dom/client + React.act,
 * axios remplace par un jest.fn. Aucun reseau, aucun essai, aucun paiement.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import FunnelEssaiCard, { pourcent, jours } from '../FunnelEssaiCard';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn() }
}));

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

/** La reponse du serveur, telle que la route la rend : deja sans aucune PII. */
const REPONSE = {
  period: '30d',
  offer_id: '',
  offers: [
    { id: 'off-a', name: 'Cours d’essai GRATUIT' },
    { id: 'off-b', name: 'Essai duo' }
  ],
  cohort: { anchor: 'granted_at', since: '2026-07-18T00:00:00+00:00',
            oldest_grant: '2026-07-23T09:00:00+00:00' },
  granted: 100, booked: 70, attended: 52, converted: 18,
  rates: { booking: 0.7, attendance: 0.7428, conversion: 0.3461, overall: 0.18 },
  conversion_delay: { average_days: 4.2, median_days: 3.0, sample_size: 18 },
  diagnostic: { cle: 'present_converti', etape: 'present_converti' },
  coverage: { conversion_measured_since: '2026-08-17', partial: false,
              min_sample_for_diagnostic: 10 }
};

const avec = (extra) => JSON.parse(JSON.stringify({ ...REPONSE, ...extra }));

let conteneur = null;
let racine = null;

async function monter(donnees = REPONSE, { echec = null, suspendu = false } = {}) {
  axios.get.mockReset();
  if (echec) axios.get.mockRejectedValue(echec);
  else if (suspendu) axios.get.mockReturnValue(new Promise(() => {}));
  else axios.get.mockResolvedValue({ data: donnees });

  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(<FunnelEssaiCard />); });
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

describe('ESSAI-3 — funnel essai gratuit', () => {
  test('F1. les quatre etages sont visibles, dans l’ordre', async () => {
    await monter();
    ['granted', 'booked', 'attended', 'converted'].forEach((c) => {
      expect(par(`funnel-${c}`)).not.toBeNull();
    });
    expect(par('funnel-etapes').querySelectorAll('[role="listitem"]')).toHaveLength(4);
    expect(texte()).toMatch(/Essais accordés[\s\S]*Essais réservés[\s\S]*Essais présents[\s\S]*Clients convertis/);
  });

  test('F2. les chiffres rendus sont ceux du serveur, jamais recalcules', async () => {
    await monter();
    expect(par('funnel-granted').textContent).toBe('100');
    expect(par('funnel-booked').textContent).toBe('70');
    expect(par('funnel-attended').textContent).toBe('52');
    expect(par('funnel-converted').textContent).toBe('18');
  });

  test('F3. les taux sont formates, et le global ne se confond pas avec present -> converti', async () => {
    await monter();
    expect(par('funnel-taux-booking').textContent).toBe('70 %');
    expect(par('funnel-taux-attendance').textContent).toBe('74 %');
    expect(par('funnel-taux-conversion').textContent).toBe('35 %');
    expect(par('funnel-global').textContent).toBe('18 %');
    expect(par('funnel-global').textContent).not.toBe(par('funnel-taux-conversion').textContent);
  });

  test('F3b. un taux absent s’affiche « — », jamais NaN ni 0 %', async () => {
    await monter(avec({
      granted: 3, booked: 0, attended: 0, converted: 0,
      rates: { booking: 0, attendance: null, conversion: null, overall: 0 }
    }));
    expect(par('funnel-taux-booking').textContent).toBe('0 %');
    expect(par('funnel-taux-attendance').textContent).toBe('—');
    expect(texte()).not.toMatch(/NaN|Infinity/);
    expect(pourcent(null)).toBe('—');
    expect(pourcent(undefined)).toBe('—');
    expect(pourcent(0)).toBe('0 %');
  });

  test('F4. changer 7 / 30 / 90 / Tout recharge les donnees avec la bonne periode', async () => {
    await monter();
    expect(axios.get.mock.calls[0][1].params.period).toBe('30d');
    for (const p of ['7d', '90d', 'all']) {
      await cliquer(`funnel-periode-${p}`);
      const dernier = axios.get.mock.calls[axios.get.mock.calls.length - 1];
      expect(dernier[1].params.period).toBe(p);
    }
    expect(axios.get).toHaveBeenCalledTimes(4);
  });

  test('F5. le filtre par offre part au serveur, et le menu garde toutes les offres', async () => {
    await monter();
    const select = par('funnel-offre');
    expect(Array.from(select.options).map((o) => o.value))
      .toEqual(['', 'off-a', 'off-b']);
    const poser = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set;
    await act(async () => {
      poser.call(select, 'off-b');
      select.dispatchEvent(new Event('change', { bubbles: true }));
    });
    const dernier = axios.get.mock.calls[axios.get.mock.calls.length - 1];
    expect(dernier[1].params.offer_id).toBe('off-b');
    expect(Array.from(par('funnel-offre').options)).toHaveLength(3);
  });

  test('F5b. une seule offre : pas de menu inutile', async () => {
    await monter(avec({ offers: [{ id: 'off-a', name: 'Essai' }] }));
    expect(par('funnel-offre')).toBeNull();
  });

  test('F6. chargement : un squelette, jamais une page blanche ni un zero', async () => {
    await monter(REPONSE, { suspendu: true });
    expect(par('funnel-chargement')).not.toBeNull();
    expect(par('funnel-etapes')).toBeNull();
    expect(texte()).not.toMatch(/\b0\b/);
  });

  test('F7. aucune donnee : un message utile, pas un funnel de zeros', async () => {
    await monter(avec({
      granted: 0, booked: 0, attended: 0, converted: 0, offers: [],
      rates: { booking: null, attendance: null, conversion: null, overall: null },
      conversion_delay: { average_days: null, median_days: null, sample_size: 0 },
      diagnostic: { cle: 'aucune_donnee', etape: null }
    }));
    expect(par('funnel-vide')).not.toBeNull();
    expect(par('funnel-etapes')).toBeNull();
    expect(texte()).not.toMatch(/NaN|—\s*%/);
    expect(texte()).toMatch(/Aucun essai gratuit accordé/);
  });

  test('F8. erreur : message clair et bouton pour reessayer', async () => {
    await monter(REPONSE, { echec: { response: { status: 500 } } });
    expect(par('funnel-erreur')).not.toBeNull();
    expect(texte()).toMatch(/Impossible de charger le funnel/);
    axios.get.mockResolvedValue({ data: REPONSE });
    await act(async () => {
      conteneur.querySelector('button').dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    expect(par('funnel-granted').textContent).toBe('100');
  });

  test('F8b. un refus d’acces le dit franchement', async () => {
    await monter(REPONSE, { echec: { response: { status: 403 } } });
    expect(texte()).toMatch(/Accès refusé/);
  });

  test('F9. historique partiel : la limite est annoncee, sans alarmisme', async () => {
    await monter(avec({ coverage: { conversion_measured_since: '2026-08-17', partial: true } }));
    expect(par('funnel-couverture')).not.toBeNull();
    expect(texte()).toMatch(/mesurées depuis le 17 août 2026/);
    await monter();
    expect(par('funnel-couverture')).toBeNull();
  });

  test('F10. le diagnostic affiche est celui que le serveur a decide', async () => {
    await monter();
    expect(par('funnel-diagnostic').textContent).toMatch(/opportunité est la conversion après l['’]essai/);
    await monter(avec({ diagnostic: { cle: 'accorde_reserve' } }));
    expect(par('funnel-diagnostic').textContent).toMatch(/entre l['’]essai accordé et la réservation/);
    await monter(avec({ diagnostic: { cle: 'reserve_present' } }));
    expect(par('funnel-diagnostic').textContent).toMatch(/entre la réservation et la présence/);
  });

  test('F11. echantillon faible : aucune conclusion trompeuse', async () => {
    await monter(avec({
      granted: 4, booked: 1, attended: 0, converted: 0,
      diagnostic: { cle: 'echantillon_faible', etape: null }
    }));
    expect(par('funnel-diagnostic').textContent).toMatch(/Trop peu d['’]essais/);
    expect(texte()).not.toMatch(/principale perte|opportunité/);
  });

  test('F11b. un verdict inconnu du serveur n’affiche rien plutot qu’un texte vide', async () => {
    await monter(avec({ diagnostic: { cle: 'chose_inconnue' } }));
    expect(par('funnel-diagnostic')).toBeNull();
  });

  test('F12. mobile : largeurs relatives, aucune barre sous 150 px, select a 16 px', async () => {
    await monter();
    const barres = Array.from(par('funnel-etapes').querySelectorAll('[role="listitem"] > div:last-child'));
    expect(barres).toHaveLength(4);
    barres.forEach((b) => {
      expect(b.style.width).toMatch(/%$/);          // jamais une largeur en pixels
      expect(b.style.minWidth).toBe('150px');       // le chiffre reste lisible
    });
    // 16 px : en dessous, iOS zoome sur le champ des l'ouverture du menu.
    expect(par('funnel-offre').style.fontSize).toBe('16px');
  });

  test('F12b. l’etage le plus etroit reste lisible', async () => {
    await monter(avec({ granted: 100, booked: 3, attended: 1, converted: 0 }));
    const barres = Array.from(par('funnel-etapes').querySelectorAll('[role="listitem"] > div:last-child'));
    barres.forEach((b) => expect(parseInt(b.style.width, 10)).toBeGreaterThanOrEqual(18));
  });

  test('F13. AUCUNE donnee de participant n’est affichee', async () => {
    await monter();
    expect(texte()).not.toMatch(/@|AFR-|\+41|\bcode\b/i);
    const envoye = JSON.stringify(axios.get.mock.calls);
    expect(envoye).not.toMatch(/email|coach_id/);
  });

  test('F13b. le delai n’est jamais invente quand il manque', async () => {
    await monter(avec({
      conversion_delay: { average_days: null, median_days: null, sample_size: 0 }
    }));
    expect(par('funnel-delai').textContent).toBe('—');
    expect(par('funnel-delai').textContent).not.toMatch(/0 jour/);
    expect(jours(null)).toBe('—');
    expect(jours(4.2)).toBe('4,2 jours');
    expect(jours(1)).toBe('1 jour');
  });
});
