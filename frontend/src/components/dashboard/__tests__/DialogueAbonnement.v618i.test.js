/**
 * V618i — confirmation de suppression lisible + abonnements sans code (suppression par le coach).
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { useDialogueAbonnement, formaterJour } from '../DialogueAbonnement';
import AbonnementsOrphelins from '../AbonnementsOrphelins';

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;
jest.mock('axios', () => ({ get: jest.fn(), delete: jest.fn() }));
jest.mock('../../SvgIcon', () => ({ name }) => <i data-icon={name} />);

function monter(el) {
  const div = document.createElement('div'); document.body.appendChild(div);
  const root = createRoot(div);
  act(() => { root.render(el); });
  return { div, q: (s) => document.querySelector(s), unmount: () => act(() => root.unmount()) };
}
const attendre = () => act(() => new Promise((r) => setTimeout(r, 0)));

describe('A. fenêtre de confirmation', () => {
  test('résumé (client, abonnement, séances, expiration) + note historique ; le choix est rendu', async () => {
    let demander;
    function Hote() { const [ui, d] = useDialogueAbonnement(); demander = d; return ui; }
    const m = monter(<Hote />);
    let choix;
    act(() => { demander({
      titre: 'Supprimer cet abonnement ?',
      lignes: [['Client', 'a@t.example'], ['Abonnement', 'PULSE'], ['Séances restantes', '8'], ['Expiration', formaterJour('2027-05-05')]],
      note: "Les paiements et réservations passés seront conservés pour l'historique, mais cet abonnement ne sera plus utilisable.",
      boutons: [{ id: 'annuler', label: 'Annuler' }, { id: 'supprimer', label: "Supprimer définitivement l'abonnement", danger: true }],
    }).then((c) => { choix = c; }); });
    const resume = m.q('[data-testid="dialogue-abonnement-resume"]').textContent;
    expect(resume).toMatch(/a@t\.example/);
    expect(resume).toMatch(/05\.05\.2027/);
    expect(m.q('[data-testid="dialogue-abonnement-note"]').textContent).toMatch(/conservés pour l'historique/);
    act(() => { m.q('[data-testid="dialogue-abonnement-supprimer"]').click(); });
    await attendre();
    expect(choix).toBe('supprimer');
    expect(m.q('[data-testid="dialogue-abonnement"]')).toBeNull();
    m.unmount();
  });
});

describe('B. abonnements sans code', () => {
  const axios = require('axios');
  beforeEach(() => { axios.get.mockReset(); axios.delete.mockReset(); });
  test('liste vide -> rien n\'est affiché', async () => {
    axios.get.mockResolvedValue({ data: { orphelins: [] } });
    const m = monter(<AbonnementsOrphelins rafraichir={0} />);
    await attendre();
    expect(m.q('[data-testid="abonnements-orphelins"]')).toBeNull();
    m.unmount();
  });
  test('Annuler -> aucune suppression ; Supprimer -> DELETE puis relecture du serveur', async () => {
    const o = { id: 'so', code: 'AFR-ORPH', email: 'c@t.example', abonnement: 'PULSE', seances_restantes: 4, expiration: '2027-01-01', courant: true };
    axios.get.mockResolvedValueOnce({ data: { orphelins: [o] } }).mockResolvedValue({ data: { orphelins: [] } });
    axios.delete.mockResolvedValue({ data: { success: true, abonnement_actuel_apres: null } });
    const m = monter(<AbonnementsOrphelins rafraichir={0} />);
    await attendre();
    expect(m.q('[data-testid="orphelin-so"]').textContent).toMatch(/AFR-ORPH/);
    act(() => { m.q('[data-testid="supprimer-orphelin-so"]').click(); });
    act(() => { m.q('[data-testid="dialogue-abonnement-annuler"]').click(); });
    await attendre();
    expect(axios.delete).not.toHaveBeenCalled();
    act(() => { m.q('[data-testid="supprimer-orphelin-so"]').click(); });
    act(() => { m.q('[data-testid="dialogue-abonnement-supprimer"]').click(); });
    await attendre(); await attendre();
    expect(axios.delete).toHaveBeenCalledWith(expect.stringMatching(/\/api\/abonnements\/so$/));
    expect(axios.get).toHaveBeenCalledTimes(2);                       // relu depuis le serveur
    expect(m.q('[data-testid="annonce-abonnement"]').textContent).toMatch(/Abonnement supprimé/);
    expect(m.q('[data-testid="abonnements-orphelins"]')).toBeNull();  // le serveur ne le renvoie plus
    m.unmount();
  });
});
