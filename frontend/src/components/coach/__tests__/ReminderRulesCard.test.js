/**
 * N1B-3C — tests de l'interface de reglage des rappels.
 *
 * HORS LIGNE, comme les tests backend : `axios` est simule, aucune base,
 * aucun reseau, et surtout AUCUNE ecriture sur la production. Le `PUT` est
 * reellement appele sur la prod depuis le navigateur du coach — le declencher
 * depuis une suite de tests ecrirait de vraies regles sur un vrai profil.
 *
 * AUCUNE DEPENDANCE AJOUTEE. `@testing-library/react` n'est pas installe et
 * l'installer modifierait package.json / package-lock.json, partages avec les
 * autres chantiers. On rend donc avec `react-dom/client` et on pilote le DOM
 * directement, ce qui suffit largement pour un composant a deux menus.
 *
 * Les valeurs de `<select>` sont posees via le setter natif du prototype avant
 * l'evenement `change` : React memorise la derniere valeur vue et ignorerait
 * une affectation faite directement sur l'element.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import fs from 'fs';
import path from 'path';
import axios from 'axios';
import ReminderRulesCard from '../ReminderRulesCard';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), put: jest.fn() }
}));

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const R1H = { type: 'relative', minutes: 60 };
const R24H = { type: 'relative', minutes: 1440 };
const SD700 = { type: 'same_day', heure: 7, minute: 0 };
const SD730 = { type: 'same_day', heure: 7, minute: 30 };
const SD800 = { type: 'same_day', heure: 8, minute: 0 };

let conteneur = null;
let racine = null;

async function monter({ rules = [R1H], par_defaut = false, echecGet = null } = {}) {
  axios.get.mockReset();
  axios.put.mockReset();
  if (echecGet) axios.get.mockRejectedValue(echecGet);
  else axios.get.mockResolvedValue({ data: { rules, par_defaut } });

  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => {
    racine.render(<ReminderRulesCard coachEmail="coach@afroboost.com" />);
  });
}

afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) conteneur.remove();
  racine = null;
  conteneur = null;
});

const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const texte = () => conteneur.textContent;

async function choisir(id, valeur) {
  const el = par(id);
  const poser = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set;
  await act(async () => {
    poser.call(el, valeur);
    el.dispatchEvent(new Event('change', { bubbles: true }));
  });
}

async function cliquer(id) {
  await act(async () => {
    par(id).dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });
}

const corpsDuPut = () => axios.put.mock.calls[0][1];

// --------------------------------------------------------------------------
describe('chargement des regles', () => {
  test('la regle renvoyee par le serveur est affichee', async () => {
    await monter({ rules: [R24H] });
    expect(axios.get).toHaveBeenCalledTimes(1);
    expect(axios.get.mock.calls[0][0]).toBe('/api/coach/reminder-rules');
    expect(par('reminder-moment-0').value).toBe('rel:1440');
  });

  test("l'identite du coach part en en-tete — le serveur ne la prend jamais du corps", async () => {
    await monter();
    expect(axios.get.mock.calls[0][1].headers['X-User-Email']).toBe('coach@afroboost.com');
  });

  test('« par défaut » est annonce quand le coach n\'a rien configure', async () => {
    await monter({ rules: [R1H], par_defaut: true });
    expect(texte()).toContain('par défaut');
  });

  test('le badge disparait quand la configuration vient du coach', async () => {
    await monter({ rules: [R1H], par_defaut: false });
    expect(texte()).not.toContain('par défaut');
  });

  test('le titre et la phrase demandes sont bien la', async () => {
    await monter();
    expect(texte()).toContain('Rappels avant cours');
    expect(texte()).toContain('Choisis jusqu’à 2 moments pour rappeler automatiquement tes participants.');
  });

  test('une heure fixe chargee remplit les DEUX menus', async () => {
    await monter({ rules: [SD730] });
    expect(par('reminder-moment-0').value).toBe('same_day');
    expect(par('reminder-heure-0').value).toBe('7:30');
  });
});

// --------------------------------------------------------------------------
describe('0 / 1 / 2 rappels', () => {
  test('a 1 regle : aucune croix, et on peut en ajouter une', async () => {
    await monter({ rules: [R1H] });
    expect(par('reminder-moment-1')).toBeNull();
    expect(par('reminder-retirer-0')).toBeNull();
    expect(par('reminder-ajouter')).not.toBeNull();
  });

  test('a 2 regles : deux croix, et plus de bouton d\'ajout', async () => {
    await monter({ rules: [R1H, R24H] });
    expect(par('reminder-moment-1')).not.toBeNull();
    expect(par('reminder-retirer-0')).not.toBeNull();
    expect(par('reminder-retirer-1')).not.toBeNull();
    expect(par('reminder-ajouter')).toBeNull();
  });

  test('jamais plus de 2 : le maximum est atteint apres un seul ajout', async () => {
    await monter({ rules: [R1H] });
    await cliquer('reminder-ajouter');
    expect(par('reminder-moment-1')).not.toBeNull();
    expect(par('reminder-ajouter')).toBeNull();
  });

  test('« 0 rappel » est impossible : retirer laisse toujours une regle', async () => {
    await monter({ rules: [R1H, R24H] });
    await cliquer('reminder-retirer-1');
    expect(par('reminder-moment-0')).not.toBeNull();
    expect(par('reminder-moment-1')).toBeNull();
    // La derniere regle n'offre plus de croix — le serveur refuse une liste
    // vide (400), un bouton qui y menerait serait un piege.
    expect(par('reminder-retirer-0')).toBeNull();
  });

  test('le second rappel propose ne double jamais le premier', async () => {
    await monter({ rules: [R1H] });
    await cliquer('reminder-ajouter');
    expect(par('reminder-moment-1').value).toBe('rel:1440');
    expect(texte()).not.toContain('identiques');
  });

  test('si 24 h est deja pris, l\'ajout bascule sur l\'heure fixe', async () => {
    await monter({ rules: [R24H] });
    await cliquer('reminder-ajouter');
    expect(par('reminder-moment-1').value).toBe('same_day');
    expect(par('reminder-heure-1').value).toBe('7:0');
  });
});

// --------------------------------------------------------------------------
describe('07:00 / 07:30 et les valeurs autorisees', () => {
  test('le menu d\'heure n\'offre que :00 et :30, sur 24 h', async () => {
    await monter({ rules: [SD700] });
    const options = Array.from(par('reminder-heure-0').options).map((o) => o.textContent);
    expect(options).toHaveLength(48);
    expect(options[0]).toBe('00:00');
    expect(options[15]).toBe('07:30');
    expect(options[47]).toBe('23:30');
    expect(options.some((o) => /:(15|45)$/.test(o))).toBe(false);
  });

  test('choisir 07:30 envoie bien minute 30', async () => {
    await monter({ rules: [SD700] });
    axios.put.mockResolvedValue({ data: { success: true, rules: [SD730], avertissements: [] } });
    await choisir('reminder-heure-0', '7:30');
    await cliquer('reminder-enregistrer');
    expect(corpsDuPut()).toEqual({ rules: [SD730] });
  });

  test('les delais proposes sont exactement les quatre admis', async () => {
    await monter();
    const valeurs = Array.from(par('reminder-moment-0').options).map((o) => o.value);
    expect(valeurs).toEqual(['rel:60', 'rel:180', 'rel:1440', 'rel:2880', 'same_day']);
  });

  test('07:00 + 07:30 est refuse AVANT le serveur', async () => {
    await monter({ rules: [SD700, SD730] });
    expect(texte()).toContain('moins d’une heure d’écart');
    expect(par('reminder-enregistrer').disabled).toBe(true);
  });

  test('07:00 + 08:00 ne declenche aucun refus', async () => {
    await monter({ rules: [SD700, SD800] });
    expect(texte()).not.toContain('moins d’une heure d’écart');
  });

  test('07:00 + 08:00 part bien au serveur — 60 min pile, c\'est bon', async () => {
    // On part de 08:00 + 24 h, et on passe la 2e regle a l'heure fixe (07:00) :
    // une VRAIE modification, contrairement a deux changements qui se seraient
    // annules — auquel cas le bouton resterait inactif, a juste titre.
    await monter({ rules: [SD800, R24H] });
    axios.put.mockResolvedValue({ data: { success: true, rules: [SD800, SD700], avertissements: [] } });
    await choisir('reminder-moment-1', 'same_day');
    expect(texte()).not.toContain('moins d’une heure d’écart');
    expect(par('reminder-enregistrer').disabled).toBe(false);
    await cliquer('reminder-enregistrer');
    expect(corpsDuPut()).toEqual({ rules: [SD800, SD700] });
  });

  test('07:30 + 08:00 est refuse — 30 min d\'ecart seulement', async () => {
    await monter({ rules: [SD730, SD800] });
    expect(texte()).toContain('moins d’une heure d’écart');
    expect(par('reminder-enregistrer').disabled).toBe(true);
  });

  test('deux rappels identiques sont refuses avant le serveur', async () => {
    await monter({ rules: [R1H, R24H] });
    await choisir('reminder-moment-1', 'rel:60');
    expect(texte()).toContain('identiques');
    expect(par('reminder-enregistrer').disabled).toBe(true);
    expect(axios.put).not.toHaveBeenCalled();
  });
});

// --------------------------------------------------------------------------
describe('sauvegarde', () => {
  test('rien a enregistrer tant que rien n\'a change', async () => {
    await monter({ rules: [R1H] });
    expect(par('reminder-enregistrer').disabled).toBe(true);
  });

  test('le bouton s\'active des qu\'on touche a un menu', async () => {
    await monter({ rules: [R1H] });
    await choisir('reminder-moment-0', 'rel:180');
    expect(par('reminder-enregistrer').disabled).toBe(false);
  });

  test('« 24 h + 07:00 » part au serveur dans la forme attendue', async () => {
    await monter({ rules: [R1H] });
    axios.put.mockResolvedValue({ data: { success: true, rules: [R24H, SD700], avertissements: [] } });
    await choisir('reminder-moment-0', 'rel:1440');
    await cliquer('reminder-ajouter');
    await choisir('reminder-moment-1', 'same_day');
    await cliquer('reminder-enregistrer');

    expect(axios.put.mock.calls[0][0]).toBe('/api/coach/reminder-rules');
    expect(corpsDuPut()).toEqual({ rules: [R24H, SD700] });
    expect(axios.put.mock.calls[0][2].headers['X-User-Email']).toBe('coach@afroboost.com');
  });

  test('« Enregistré » s\'affiche, et le bouton se rendort', async () => {
    await monter({ rules: [R1H] });
    axios.put.mockResolvedValue({ data: { success: true, rules: [R24H], avertissements: [] } });
    await choisir('reminder-moment-0', 'rel:1440');
    await cliquer('reminder-enregistrer');
    expect(texte()).toContain('Enregistré');
    expect(par('reminder-enregistrer').disabled).toBe(true);
  });

  test('la confirmation disparait des qu\'on retouche un menu', async () => {
    await monter({ rules: [R1H] });
    axios.put.mockResolvedValue({ data: { success: true, rules: [R24H], avertissements: [] } });
    await choisir('reminder-moment-0', 'rel:1440');
    await cliquer('reminder-enregistrer');
    expect(texte()).toContain('Enregistré');
    await choisir('reminder-moment-0', 'rel:180');
    expect(texte()).not.toContain('Enregistré');
  });

  test('le badge « par défaut » tombe apres un enregistrement', async () => {
    await monter({ rules: [R1H], par_defaut: true });
    axios.put.mockResolvedValue({ data: { success: true, rules: [R24H], avertissements: [] } });
    await choisir('reminder-moment-0', 'rel:1440');
    await cliquer('reminder-enregistrer');
    expect(texte()).not.toContain('par défaut');
  });

  test('les regles renvoyees par le serveur font foi, pas celles de l\'ecran', async () => {
    await monter({ rules: [R1H] });
    axios.put.mockResolvedValue({ data: { success: true, rules: [SD800], avertissements: [] } });
    await choisir('reminder-moment-0', 'rel:1440');
    await cliquer('reminder-enregistrer');
    expect(par('reminder-moment-0').value).toBe('same_day');
    expect(par('reminder-heure-0').value).toBe('8:0');
  });

  test('les avertissements de collision du serveur sont affiches tels quels', async () => {
    await monter({ rules: [R1H] });
    axios.put.mockResolvedValue({
      data: {
        success: true,
        rules: [R1H, SD700],
        avertissements: ['Ton cours du mardi à 08:00 recevrait deux rappels à 07:00.']
      }
    });
    await choisir('reminder-moment-0', 'rel:1440');
    await cliquer('reminder-enregistrer');
    expect(par('reminder-avertissements')).not.toBeNull();
    expect(texte()).toContain('Ton cours du mardi à 08:00 recevrait deux rappels à 07:00.');
    // Un avertissement n'est PAS un refus : la configuration est bien enregistree.
    expect(texte()).toContain('Enregistré');
  });
});

// --------------------------------------------------------------------------
describe('erreurs API', () => {
  test('route absente au chargement : on le dit, et aucun editeur', async () => {
    await monter({ echecGet: { response: { status: 404 } } });
    expect(texte()).toContain('Réglage des rappels indisponible pour le moment.');
    expect(par('reminder-moment-0')).toBeNull();
    expect(par('reminder-enregistrer')).toBeNull();
  });

  test('session non reconnue : on invite a se reconnecter', async () => {
    await monter({ echecGet: { response: { status: 401 } } });
    expect(texte()).toContain('Reconnecte-toi pour régler tes rappels.');
    expect(par('reminder-moment-0')).toBeNull();
  });

  test('403 est traite comme 401', async () => {
    await monter({ echecGet: { response: { status: 403 } } });
    expect(texte()).toContain('Reconnecte-toi pour régler tes rappels.');
  });

  test('panne reseau au chargement : message generique, pas de formulaire mort', async () => {
    await monter({ echecGet: new Error('Network Error') });
    expect(texte()).toContain('Réglage des rappels indisponible pour le moment.');
    expect(par('reminder-moment-0')).toBeNull();
  });

  test('refus 400 : le motif du serveur est montre mot pour mot', async () => {
    await monter({ rules: [R1H] });
    axios.put.mockRejectedValue({
      response: { status: 400, data: { detail: 'Configuration de rappels invalide : au plus 2 règles.' } }
    });
    await choisir('reminder-moment-0', 'rel:1440');
    await cliquer('reminder-enregistrer');
    expect(par('reminder-erreur').textContent)
      .toBe('Configuration de rappels invalide : au plus 2 règles.');
    expect(texte()).not.toContain('Enregistré');
  });

  test('erreur sans detail : message de repli, et rien n\'est confirme', async () => {
    await monter({ rules: [R1H] });
    axios.put.mockRejectedValue({ response: { status: 500, data: {} } });
    await choisir('reminder-moment-0', 'rel:1440');
    await cliquer('reminder-enregistrer');
    expect(par('reminder-erreur').textContent)
      .toBe('Enregistrement impossible. Réessaie dans un instant.');
    expect(texte()).not.toContain('Enregistré');
  });

  test('apres un echec, le bouton reste actif pour reessayer', async () => {
    await monter({ rules: [R1H] });
    axios.put.mockRejectedValue({ response: { status: 500, data: {} } });
    await choisir('reminder-moment-0', 'rel:1440');
    await cliquer('reminder-enregistrer');
    expect(par('reminder-enregistrer').disabled).toBe(false);
  });

  test('un echec n\'ecrase pas ce que le coach avait saisi', async () => {
    await monter({ rules: [R1H] });
    axios.put.mockRejectedValue({ response: { status: 400, data: { detail: 'non' } } });
    await choisir('reminder-moment-0', 'rel:2880');
    await cliquer('reminder-enregistrer');
    expect(par('reminder-moment-0').value).toBe('rel:2880');
  });

  test('l\'erreur precedente disparait quand on corrige', async () => {
    await monter({ rules: [R1H] });
    axios.put.mockRejectedValue({ response: { status: 400, data: { detail: 'non' } } });
    await choisir('reminder-moment-0', 'rel:1440');
    await cliquer('reminder-enregistrer');
    expect(par('reminder-erreur')).not.toBeNull();
    await choisir('reminder-moment-0', 'rel:180');
    expect(par('reminder-erreur')).toBeNull();
  });
});

// --------------------------------------------------------------------------
describe('mise en page', () => {
  test('la ligne est bornee en largeur — sans quoi le menu s\'etire sur tout l\'ecran', async () => {
    await monter({ rules: [R1H] });
    const ligne = par('reminder-moment-0').closest('.max-w-md');
    expect(ligne).not.toBeNull();
  });

  test('aucune couleur de marque codee en dur hors valeur de secours', () => {
    // Regle absolue du depot : toute couleur passe par var(--primary-color, …),
    // l'hexadecimal n'etant qu'un repli DANS le var().
    //
    // Ce test lit la SOURCE, pas le DOM rendu : jsdom ne sait pas parser
    // `var()` avec valeur de secours et retire purement et simplement la
    // declaration `color` des styles en ligne. Un controle sur le DOM ne
    // trouverait donc aucune couleur — il passerait toujours, sans rien
    // verifier. Verifie le 14/08/2026 sur le DOM extrait : zero `color`.
    const source = fs.readFileSync(
      path.join(__dirname, '..', 'ReminderRulesCard.js'), 'utf8'
    );
    const lignes = source.split('\n');
    const fautives = lignes.filter((l) => {
      const hex = l.match(/#[0-9a-fA-F]{6}/g);
      if (!hex) return false;
      return hex.some((c) => !l.includes(`var(--primary-color, ${c})`));
    });
    expect(fautives).toEqual([]);
  });

  test('les teintes de marque passent par les canaux nus, pas par un rgba fige', () => {
    const source = fs.readFileSync(
      path.join(__dirname, '..', 'ReminderRulesCard.js'), 'utf8'
    );
    if (source.includes('backgroundColor') && source.includes('--primary-rgb')) {
      expect(source).toContain('rgba(var(--primary-rgb, 217, 28, 210)');
    }
  });

  test('chaque menu porte un libelle accessible', async () => {
    await monter({ rules: [SD700] });
    expect(par('reminder-moment-0').getAttribute('aria-label')).toBe('Moment du rappel 1');
    expect(par('reminder-heure-0').getAttribute('aria-label')).toBe('Heure du rappel 1');
  });
});
