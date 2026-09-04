/**
 * RAPPELS V2 — niveau 1 : le coach choisit quels cours envoient des rappels.
 *
 * Meme harnais que ReminderRulesCard.test.js : react-dom/client + React.act,
 * axios remplace par deux jest.fn. Aucun reseau, aucun envoi.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import CourseRemindersCard from '../CourseRemindersCard';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), put: jest.fn() }
}));

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const R24H = { type: 'relative', minutes: 1440 };
const SD700 = { type: 'same_day', heure: 7, minute: 0 };

// Les VRAIS cours du coach, tels que la route dediee les rend : recurrents,
// ARCHIVES, mais vendus par des offres publiques. C'est le cas reel qui a fait
// poser les rappels au mauvais endroit.
const VENDUES = [
  { id: 'pulse', name: 'PULSE x10 cours', publique: true },
  { id: 'membres', name: 'Membres', publique: true }
];
const MERCREDI = {
  id: 'merc', name: 'Afroboost Silent – Session Cardio', weekday: 3, time: '18:30',
  visible: true, archived: true, agenda_abonne: true, offres: VENDUES
};
const DIMANCHE = {
  id: 'dim', name: 'Afroboost Silent – Sunday Vibes', weekday: 0, time: '18:30',
  visible: true, archived: true, agenda_abonne: true, offres: VENDUES,
  reminders_enabled: true, reminder_rules: [R24H, SD700]
};
// Un brouillon : non publie, rattache a rien.
const BROUILLON = {
  id: 'brouillon2', name: 'Nouveau cours', weekday: 3, time: '18:30',
  visible: false, archived: false, offres: []
};
// Un cours rattache UNIQUEMENT a une offre masquee.
const MASQUE_SEUL = {
  id: 'masq', name: 'Silent Lakeside', weekday: 0, time: '11:00',
  visible: true, archived: false,
  offres: [{ id: 'lakeside', name: 'SILENT LAKESIDE', publique: false }]
};
const ARCHIVE = {
  id: 'vieux', name: 'Ancien cours', weekday: 1, time: '19:00',
  visible: true, archived: true, offres: []
};

let conteneur = null;
let racine = null;

async function monter({ cours = [MERCREDI, DIMANCHE], echecGet = null, sansChoix = false, sansRepli = false, fermee = false } = {}) {
  axios.get.mockReset();
  axios.put.mockReset();
  if (echecGet) axios.get.mockRejectedValue(echecGet);
  else axios.get.mockResolvedValue({ data: cours });

  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => {
    racine.render(<CourseRemindersCard coachEmail="coach@afroboost.com" />);
  });
  // L'ECRAN NE PRESELECTIONNE PLUS RIEN — c'est le correctif meme. Les
  // scenarios qui eprouvent le reglage d'UN cours cochent donc explicitement
  // le premier, comme le ferait le coach. `sansChoix` garde l'etat initial
  // pour les scenarios qui eprouvent l'absence de selection.
  // LA CARTE EST REPLIEE PAR DEFAUT dans l'ecran : les scenarios qui
  // eprouvent son contenu l'ouvrent d'abord, comme le ferait le coach.
  // `fermee` garde l'etat initial pour les scenarios du repli lui-meme.
  if (!fermee) {
    const _bascule = par('cr-bascule');
    if (_bascule) await act(async () => {
      _bascule.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
  }
  // LE REPLI DES COURS NON RESERVABLES EST DEPLIE PAR DEFAUT DANS LE BANC. Les cours que personne ne
  // peut reserver sont replies derriere un bouton — ils ne sont pas SUPPRIMES.
  // Les scenarios ci-dessous eprouvent le contenu de la liste ; ils la
  // deplient donc, comme le ferait un coach qui cherche un brouillon.
  if (!echecGet && !sansRepli) {
    const _bouton = par('cr-voir-tout');
    if (_bouton) await act(async () => {
      _bouton.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
  }
  if (!sansChoix && !echecGet) {
    const _liste = (cours || []);
    if (_liste.length > 0) await choisir('cr-cours', _liste[0].id);
  }
}

afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) conteneur.remove();
  racine = null;
  conteneur = null;
});

const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const texte = () => conteneur.textContent;
// Les cours ne sont plus des `option` mais des cases a cocher : une ligne par
// cours, visible en permanence, avec son etat reel a droite.
const valeursCours = () => Array.from(
  conteneur.querySelectorAll('[data-testid^="cr-cours-"]')
).map((el) => el.getAttribute('data-testid').slice('cr-cours-'.length));

const libellesCours = () => Array.from(
  conteneur.querySelectorAll('[data-testid^="cr-cours-"]')
).map((el) => el.textContent);

async function cocher(id) {
  const _ligne = par(`cr-cours-${id}`);
  const _case = _ligne ? _ligne.querySelector('input[type="checkbox"]') : null;
  await act(async () => {
    if (_case) _case.click();
  });
}

async function choisir(id, valeur) {
  if (id === 'cr-cours') {
    // Selection EXCLUSIVE, pour rejouer l'ancien parcours mono-cours : on
    // decoche ce qui l'etait, puis on coche le cours demande.
    const _coches = Array.from(
      conteneur.querySelectorAll('[data-testid^="cr-cours-"] input:checked')
    );
    for (let _i = 0; _i < _coches.length; _i += 1) {
      // eslint-disable-next-line no-await-in-loop
      await act(async () => { _coches[_i].click(); });
    }
    await cocher(valeur);
    return;
  }
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

describe('la liste des cours a configurer', () => {
  test('elle vient de la portee du coach, identite en en-tete', async () => {
    await monter();
    expect(axios.get).toHaveBeenCalledTimes(1);
    expect(axios.get.mock.calls[0][0]).toBe('/api/coach/courses');
    expect(axios.get.mock.calls[0][1].headers['X-User-Email']).toBe('coach@afroboost.com');
  });

  test('un cours NON PUBLIE reste selectionnable — publier n\'est pas administrer', async () => {
    await monter({ cours: [BROUILLON, MERCREDI] });
    expect(BROUILLON.visible).toBe(false);
    expect(valeursCours()).toEqual(['brouillon2', 'merc']);
  });

  test('et on le dit au coach, pour qu\'il ne croie pas a une erreur', async () => {
    await monter({ cours: [BROUILLON] });
    expect(par('cr-non-publie')).not.toBeNull();
  });

  test('le client ne refiltre RIEN : c\'est le serveur qui a tranche', async () => {
    // Refiltrer ici reintroduirait le bug : les vraies seances du coach sont
    // ARCHIVEES, et un filtre client les ferait disparaitre a nouveau.
    await monter({ cours: [MERCREDI, ARCHIVE, DIMANCHE] });
    expect(valeursCours()).toEqual(['merc', 'vieux', 'dim']);
  });

  test('un cours ARCHIVE mais VENDU reste configurable — le cas reel', async () => {
    await monter({ cours: [MERCREDI, DIMANCHE] });
    expect(MERCREDI.archived).toBe(true);
    expect(valeursCours()).toEqual(['merc', 'dim']);
    expect(libellesCours()[0]).toContain('vendu');
  });

  test('le coach voit PAR QUELLES OFFRES le cours est vendu', async () => {
    await monter({ cours: [MERCREDI] });
    expect(par('cr-vendu-par').textContent).toContain('PULSE x10 cours');
    expect(par('cr-vendu-par').textContent).toContain('Membres');
  });

  test('un brouillon sans offre est signale comme inerte', async () => {
    await monter({ cours: [BROUILLON] });
    expect(par('cr-sans-offre')).not.toBeNull();
    expect(par('cr-vendu-par')).toBeNull();
    expect(par('cr-sans-offre').textContent).toContain('aucun rappel ne partira');
  });

  test('un cours rattache a une offre MASQUEE est signale comme non reservable', async () => {
    await monter({ cours: [MASQUE_SEUL] });
    expect(par('cr-offre-masquee')).not.toBeNull();
  });

  test('une offre masquee n\'est JAMAIS nommee dans l\'ecran coach', async () => {
    await monter({ cours: [MASQUE_SEUL] });
    expect(texte()).not.toContain('SILENT LAKESIDE');
  });

  test('le jour et l\'heure figurent dans le libelle — mercredi et dimanche 18:30', async () => {
    await monter();
    const libelles = libellesCours();
    expect(libelles[0]).toContain('Mercredi');
    expect(libelles[0]).toContain('18:30');
    expect(libelles[1]).toContain('Dimanche');
    expect(libelles[1]).toContain('18:30');
  });

  test('aucun cours du tout : on le dit, sans editeur mort', async () => {
    await monter({ cours: [] });
    expect(par('cr-aucun-cours')).not.toBeNull();
    expect(par('cr-actif')).toBeNull();
  });
});

describe('flexibilite — n\'importe quel cours, n\'importe quel jour', () => {
  const JEUDI = { id: 'jeu', name: 'Atelier du jeudi', weekday: 4, time: '19:00', archived: false };
  const JEUDI2 = { id: 'jeu2', name: 'Cours du soir', weekday: 4, time: '20:30', archived: false };
  const PONCTUEL = { id: 'unique', name: 'Atelier special', date: '2026-09-12', time: '14:00', archived: false };
  const SANS_JOUR = { id: 'flou', name: 'Cours sans jour', time: '10:00', archived: false };

  test('les sept jours sont proposes sans distinction', async () => {
    const sept = [0, 1, 2, 3, 4, 5, 6].map((j) => ({
      id: `j${j}`, name: `Cours ${j}`, weekday: j, time: '18:30', archived: false
    }));
    await monter({ cours: sept });
    expect(valeursCours()).toEqual(['j0', 'j1', 'j2', 'j3', 'j4', 'j5', 'j6']);
  });

  test('un cours ponctuel est configurable comme un autre', async () => {
    await monter({ cours: [PONCTUEL] });
    expect(valeursCours()).toEqual(['unique']);
    expect(libellesCours()[0]).toContain('2026-09-12');
  });

  test('deux cours le meme jour restent distincts a l\'ecran', async () => {
    await monter({ cours: [JEUDI, JEUDI2] });
    expect(valeursCours()).toEqual(['jeu', 'jeu2']);
    const libelles = libellesCours();
    expect(libelles[0]).toContain('19:00');
    expect(libelles[1]).toContain('20:30');
    expect(libelles[0]).not.toBe(libelles[1]);
  });

  test('un cours sans jour ni date reste selectionnable', async () => {
    await monter({ cours: [SANS_JOUR] });
    expect(valeursCours()).toEqual(['flou']);
    expect(par('cr-actif')).not.toBeNull();
  });

  test('un cours cree plus tard s\'ajoute sans rien changer au code', async () => {
    await monter({ cours: [MERCREDI, DIMANCHE, JEUDI] });
    expect(valeursCours()).toContain('jeu');
    await choisir('cr-cours', 'jeu');
    await cliquer('cr-actif');
    expect(par('cr-moment-0')).not.toBeNull();
  });

  test('la configuration part sur l\'identifiant du cours, jamais sur son jour', async () => {
    await monter({ cours: [JEUDI, JEUDI2] });
    axios.put.mockResolvedValue({ data: { success: true, reminders_enabled: true, rules: [R24H] } });
    await choisir('cr-cours', 'jeu2');
    await cliquer('cr-actif');
    await cliquer('cr-enregistrer');
    expect(axios.put.mock.calls[0][0]).toBe('/api/coach/courses/jeu2/reminders');
  });
});

describe('activation par cours', () => {
  test('un cours jamais configure arrive ETEINT', async () => {
    await monter();
    expect(par('cr-actif').getAttribute('aria-checked')).toBe('false');
    expect(par('cr-moment-0')).toBeNull();
  });

  test('les moments n\'apparaissent qu\'une fois les rappels allumes', async () => {
    await monter();
    await cliquer('cr-actif');
    expect(par('cr-actif').getAttribute('aria-checked')).toBe('true');
    expect(par('cr-moment-0')).not.toBeNull();
  });

  test('la proposition par defaut est bien « la veille » + « le jour meme »', async () => {
    await monter();
    await cliquer('cr-actif');
    expect(par('cr-moment-0').value).toBe('rel:1440');
    expect(par('cr-moment-1').value).toBe('same_day');
    expect(par('cr-heure-1').value).toBe('7:0');
  });

  test('un cours deja configure arrive ALLUME, avec ses propres regles', async () => {
    await monter();
    await choisir('cr-cours', 'dim');
    expect(par('cr-actif').getAttribute('aria-checked')).toBe('true');
    expect(par('cr-moment-0').value).toBe('rel:1440');
    expect(par('cr-moment-1').value).toBe('same_day');
  });

  test('changer de cours recharge SA configuration, pas celle du precedent', async () => {
    await monter();
    await choisir('cr-cours', 'dim');
    expect(par('cr-moment-0')).not.toBeNull();
    await choisir('cr-cours', 'merc');
    expect(par('cr-actif').getAttribute('aria-checked')).toBe('false');
    expect(par('cr-moment-0')).toBeNull();
  });

  test('le fuseau est rappele des que des moments sont regles', async () => {
    await monter();
    await cliquer('cr-actif');
    expect(par('cr-fuseau').textContent).toContain('Europe/Zurich');
  });
});

describe('enregistrement', () => {
  test('rien a enregistrer sur un cours DEJA configure et non touche', async () => {
    // DIMANCHE porte deja `reminders_enabled` et ses deux regles : le
    // formulaire montre l'etat de la base, il n'y a rien a poser.
    await monter({ cours: [DIMANCHE] });
    expect(par('cr-enregistrer').disabled).toBe(true);
  });

  test('mais un cours VIERGE est enregistrable tout de suite', async () => {
    // C'est le piege corrige : MERCREDI n'a AUCUNE regle, l'ecran en propose
    // deux, et l'ancien bouton restait gris sans dire pourquoi. Desormais la
    // proposition est annoncee comme telle ET elle est enregistrable.
    await monter({ cours: [MERCREDI] });
    expect(par('cr-proposees')).toBeNull();      // tant que c'est desactive
    await cliquer('cr-actif');
    expect(par('cr-proposees')).not.toBeNull();
    expect(par('cr-enregistrer').disabled).toBe(false);
  });

  test('l\'activation part au serveur sur la route du COURS choisi', async () => {
    await monter();
    axios.put.mockResolvedValue({
      data: { success: true, reminders_enabled: true, rules: [R24H, SD700] }
    });
    await cliquer('cr-actif');
    await cliquer('cr-enregistrer');
    expect(axios.put.mock.calls[0][0]).toBe('/api/coach/courses/merc/reminders');
    expect(axios.put.mock.calls[0][1]).toEqual({ enabled: true, rules: [R24H, SD700] });
    expect(axios.put.mock.calls[0][2].headers['X-User-Email']).toBe('coach@afroboost.com');
  });

  test('couper les rappels envoie enabled=false', async () => {
    await monter();
    axios.put.mockResolvedValue({ data: { success: true, reminders_enabled: false, rules: [] } });
    await choisir('cr-cours', 'dim');
    await cliquer('cr-actif');
    await cliquer('cr-enregistrer');
    expect(axios.put.mock.calls[0][0]).toBe('/api/coach/courses/dim/reminders');
    expect(axios.put.mock.calls[0][1].enabled).toBe(false);
  });

  test('« Enregistré » s\'affiche et le bouton se rendort', async () => {
    await monter();
    axios.put.mockResolvedValue({
      data: { success: true, reminders_enabled: true, rules: [R24H, SD700] }
    });
    await cliquer('cr-actif');
    await cliquer('cr-enregistrer');
    expect(par('cr-confirme')).not.toBeNull();
    expect(par('cr-enregistrer').disabled).toBe(true);
  });

  test('deux rappels identiques sont refuses AVANT le serveur', async () => {
    await monter();
    await cliquer('cr-actif');
    await choisir('cr-moment-1', 'rel:1440');
    expect(par('cr-refus')).not.toBeNull();
    expect(par('cr-enregistrer').disabled).toBe(true);
    expect(axios.put).not.toHaveBeenCalled();
  });

  test('le refus du serveur est montre mot pour mot', async () => {
    await monter();
    axios.put.mockRejectedValue({ response: { status: 400, data: { detail: 'Motif du serveur.' } } });
    await cliquer('cr-actif');
    await cliquer('cr-enregistrer');
    // Le motif du serveur est rendu mot pour mot, ET le cours concerne est
    // NOMME : « une erreur est survenue » ne dit pas quoi refaire.
    expect(par('cr-erreur').textContent).toContain('Motif du serveur.');
    expect(par('cr-erreur').textContent).toContain('Session Cardio');
    expect(par('cr-confirme')).toBeNull();
  });
});

describe('erreurs de chargement', () => {
  test('session non reconnue : on invite a se reconnecter, aucun editeur', async () => {
    await monter({ echecGet: { response: { status: 401 } } });
    expect(texte()).toContain('Reconnecte-toi pour régler tes rappels.');
    expect(par('cr-cours')).toBeNull();
    expect(par('cr-enregistrer')).toBeNull();
  });

  test('panne reseau : message generique, pas de formulaire mort', async () => {
    await monter({ echecGet: new Error('Network Error') });
    expect(texte()).toContain('Réglage des rappels indisponible pour le moment.');
    expect(par('cr-cours')).toBeNull();
  });
});

// ============================================================================
// LE BUG DU 03/09/2026 — L'ECRAN DISAIT « ACTIVES » POUR UN AUTRE COURS
// ============================================================================
// Le proprietaire a active « les rappels du mercredi », lu « Rappels avant
// cours : actives », et la base n'a rien enregistre sur le mercredi. Son
// enregistrement etait parti sur le DIMANCHE — le premier cours de la liste,
// que l'ecran preselectionnait tout seul, et qui etait deja actif.
// Ces verifications existent pour que cela ne puisse plus se reproduire.

// Deux cours reguliers VIERGES : ni l'un ni l'autre n'a jamais ete active.
const DIM_VIERGE = { ...DIMANCHE, reminders_enabled: undefined, reminder_rules: undefined };
const VIERGES = [MERCREDI, DIM_VIERGE];

describe('l\'ecran reflete la base, et rien d\'autre', () => {
  test('aucun cours actif en base -> aucun coche a l\'ouverture', async () => {
    await monter({ cours: VIERGES, sansChoix: true });
    expect(conteneur.querySelectorAll('[data-testid^="cr-cours-"] input:checked').length)
      .toBe(0);
  });

  test('un cours ACTIF en base est coche a l\'ouverture — et lui seul', async () => {
    // C'est la persistance : apres un rechargement, ce qui est regle le reste.
    // Et c'est fidele : on ne coche pas « le premier de la liste », on coche
    // ce que la base porte.
    await monter({ sansChoix: true });
    const _coches = Array.from(
      conteneur.querySelectorAll('[data-testid^="cr-cours-"] input:checked')
    ).length;
    expect(_coches).toBe(1);
    expect(par('cr-etat-dim').textContent).toBe('rappels actifs');
    expect(par('cr-etat-merc').textContent).toBe('aucun rappel');
  });

  test('et l\'interrupteur n\'est meme pas affiche sans selection', async () => {
    await monter({ cours: VIERGES, sansChoix: true });
    expect(par('cr-actif')).toBeNull();
    expect(par('cr-aucun-choix')).not.toBeNull();
  });

  test('le bouton Enregistrer ne peut pas partir a l\'aveugle', async () => {
    await monter({ cours: VIERGES, sansChoix: true });
    expect(par('cr-enregistrer').disabled).toBe(true);
  });

  test('le lieu est affiche — c\'est lui qui departage les homonymes', async () => {
    await monter({ sansChoix: true });
    expect(par('cr-cours-merc').textContent).toContain('vendu');
  });

  test('un cours ARCHIVE est marque comme tel', async () => {
    await monter({ sansChoix: true });
    expect(par('cr-cours-merc').textContent).toContain('archivé');
  });

  test('decocher le dernier cours efface l\'etat affiche', async () => {
    await monter({ cours: [DIMANCHE], sansChoix: true });
    expect(par('cr-actif')).not.toBeNull();   // coche car actif en base
    await cocher('dim');
    expect(par('cr-actif')).toBeNull();
  });

  test('un cours que PERSONNE ne peut reserver est replie, jamais perdu', async () => {
    await monter({ cours: [DIMANCHE, BROUILLON], sansChoix: true, sansRepli: true });
    expect(par('cr-cours-brouillon2')).toBeNull();
    expect(par('cr-voir-tout')).not.toBeNull();
    await cliquer('cr-voir-tout');
    expect(par('cr-cours-brouillon2')).not.toBeNull();
  });
});

describe('regler DEUX cours en une fois', () => {
  test('un seul Enregistrer ecrit sur les deux cours', async () => {
    await monter({ cours: VIERGES, sansChoix: true });
    // APRES le montage : `monter` remet les mocks a zero.
    axios.put.mockResolvedValue({
      data: { success: true, reminders_enabled: true, rules: [R24H, SD700] }
    });
    await cocher('merc');
    await cocher('dim');
    await cliquer('cr-actif');
    await cliquer('cr-enregistrer');
    expect(axios.put).toHaveBeenCalledTimes(2);
    expect(axios.put.mock.calls[0][0]).toBe('/api/coach/courses/merc/reminders');
    expect(axios.put.mock.calls[1][0]).toBe('/api/coach/courses/dim/reminders');
  });

  test('les deux recoivent EXACTEMENT le meme reglage', async () => {
    await monter({ cours: VIERGES, sansChoix: true });
    // APRES le montage : `monter` remet les mocks a zero.
    axios.put.mockResolvedValue({
      data: { success: true, reminders_enabled: true, rules: [R24H, SD700] }
    });
    await cocher('merc');
    await cocher('dim');
    await cliquer('cr-actif');
    await cliquer('cr-enregistrer');
    expect(axios.put.mock.calls[0][1]).toEqual(axios.put.mock.calls[1][1]);
    expect(axios.put.mock.calls[0][1].enabled).toBe(true);
    expect(axios.put.mock.calls[0][1].rules).toEqual([R24H, SD700]);
  });

  test('le compte rendu dit combien de cours ont ete ecrits', async () => {
    await monter({ cours: VIERGES, sansChoix: true });
    // APRES le montage : `monter` remet les mocks a zero.
    axios.put.mockResolvedValue({
      data: { success: true, reminders_enabled: true, rules: [R24H, SD700] }
    });
    await cocher('merc');
    await cocher('dim');
    await cliquer('cr-actif');
    await cliquer('cr-enregistrer');
    expect(par('cr-confirme').textContent).toContain('2 cours sur 2');
  });

  test('deux cours aux reglages differents sont signales', async () => {
    // MERCREDI est vierge, DIMANCHE est deja regle : cocher les deux doit le
    // dire AVANT d'enregistrer, sinon on ecrase un reglage sans le savoir.
    await monter({ sansChoix: true });
    await cocher('merc');
    expect(par('cr-divergents')).not.toBeNull();
  });

  test('un echec sur UN cours n\'affiche jamais « Enregistre »', async () => {
    await monter({ cours: VIERGES, sansChoix: true });
    axios.put
      .mockResolvedValueOnce({ data: { success: true, reminders_enabled: true, rules: [R24H] } })
      .mockRejectedValueOnce({ response: { data: { detail: 'Refus du serveur.' } } });
    await cocher('merc');
    await cocher('dim');
    await cliquer('cr-actif');
    await cliquer('cr-enregistrer');
    expect(par('cr-confirme')).toBeNull();
    expect(par('cr-erreur').textContent).toContain('Refus du serveur.');
    expect(par('cr-erreur').textContent).toContain('Sunday Vibes');
  });

  test('et le cours qui a REUSSI garde son etat, lui', async () => {
    await monter({ cours: VIERGES, sansChoix: true });
    axios.put
      .mockResolvedValueOnce({ data: { success: true, reminders_enabled: true, rules: [R24H] } })
      .mockRejectedValueOnce({ response: { data: { detail: 'Refus du serveur.' } } });
    await cocher('merc');
    await cocher('dim');
    await cliquer('cr-actif');
    await cliquer('cr-enregistrer');
    expect(par('cr-etat-merc').textContent).toBe('rappels actifs');
  });
});

// ============================================================================
// LA CARTE EST REPLIEE — MAIS ELLE NE CACHE RIEN
// ============================================================================
// Le dashboard est une pile de cartes. Celle-ci occupait un ecran entier pour
// un reglage qu'on touche deux fois par an. Repliee, elle doit malgre tout
// dire l'essentiel : sinon replier revient a cacher.

describe('la carte se replie et se deplie', () => {
  test('elle est FERMEE a l\'ouverture du dashboard', async () => {
    await monter({ fermee: true });
    expect(par('cr-cours')).toBeNull();
    expect(par('cr-enregistrer')).toBeNull();
  });

  test('un clic sur la ligne ouvre le panneau complet', async () => {
    await monter({ fermee: true });
    await cliquer('cr-bascule');
    expect(par('cr-cours')).not.toBeNull();
  });

  test('un second clic le referme', async () => {
    await monter({ fermee: true });
    await cliquer('cr-bascule');
    await cliquer('cr-bascule');
    expect(par('cr-cours')).toBeNull();
  });

  test('l\'etat est annonce a la bascule, pour les lecteurs d\'ecran', async () => {
    await monter({ fermee: true });
    expect(par('cr-bascule').getAttribute('aria-expanded')).toBe('false');
    await cliquer('cr-bascule');
    expect(par('cr-bascule').getAttribute('aria-expanded')).toBe('true');
  });

  test('FERMEE, elle dit combien de cours sont actifs', async () => {
    // DIMANCHE est actif et vendu, MERCREDI est vendu sans rappel.
    await monter({ fermee: true });
    expect(par('cr-resume').textContent).toContain('1 cours actif');
    expect(par('cr-resume').textContent).toContain('1 sans rappel');
  });

  test('FERMEE, elle alerte quand AUCUN cours n\'a de rappel', async () => {
    const _dimVierge = { ...DIMANCHE, reminders_enabled: undefined, reminder_rules: undefined };
    await monter({ cours: [MERCREDI, _dimVierge], fermee: true });
    expect(par('cr-resume').textContent).toBe('aucun rappel actif');
  });

  test('le resume ne compte QUE les cours reservables', async () => {
    // Un brouillon actif ne rassure personne : il n'entre pas dans le compte.
    const _brouillonActif = { ...BROUILLON, reminders_enabled: true, reminder_rules: [R24H] };
    await monter({ cours: [_brouillonActif, DIMANCHE], fermee: true });
    expect(par('cr-resume').textContent).toBe('1 cours actif');
  });

  test('ouverte, le resume laisse la place au panneau', async () => {
    await monter({ fermee: true });
    await cliquer('cr-bascule');
    expect(par('cr-resume')).toBeNull();
  });
});

describe('mobile — rien n\'est coupe, rien ne sort de l\'ecran', () => {
  test('le nom du cours n\'est JAMAIS tronque', async () => {
    await monter({ sansChoix: true });
    const _ligne = par('cr-cours-merc');
    expect(_ligne.className).not.toContain('truncate');
    expect(_ligne.textContent).toContain('Session Cardio');
  });

  test('la ligne peut passer a la ligne quand la place manque', async () => {
    await monter({ sansChoix: true });
    expect(par('cr-cours-merc').className).toContain('flex-wrap');
  });

  test('le statut reste dans le flux — il ne peut pas sortir a droite', async () => {
    await monter({ sansChoix: true });
    // Il est DANS la ligne, apres le bloc texte : quand la largeur manque, le
    // `flex-wrap` du parent le fait descendre au lieu de le pousser dehors.
    expect(par('cr-cours-merc').contains(par('cr-etat-merc'))).toBe(true);
  });

  test('la liste ne defile jamais horizontalement', async () => {
    await monter({ sansChoix: true });
    const _liste = par('cr-cours').querySelector('.overflow-y-auto');
    expect(_liste.className).toContain('overflow-x-hidden');
  });

  test('la carte elle-meme ne deborde pas', async () => {
    await monter({ fermee: true });
    expect(par('cr-bascule').parentElement.className).toContain('overflow-x-hidden');
  });
});
