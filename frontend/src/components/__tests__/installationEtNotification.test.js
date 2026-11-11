import React, { act } from 'react';
import fs from 'fs';
import path from 'path';
import { createRoot } from 'react-dom/client';
import InstallationAfroboost from '../InstallationAfroboost';
import NotificationGrande from '../NotificationGrande';
import { CLE_REPORT, CLE_VUE } from '../../utils/installationPWA';

const UA = {
  iphone: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1',
  android: 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/126 Mobile Safari/537.36',
  firefox: 'Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0',
  // V666 : un ordinateur. Aucune installation possible, donc aucune barriere.
  bureau: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36',
};

let conteneur, racine;
const el = (id) => document.querySelector(`[data-testid="${id}"]`);
const txt = (id) => (el(id) ? el(id).textContent : null);
const clic = (id) => act(async () => {
  el(id).dispatchEvent(new MouseEvent('click', { bubbles: true }));
  await Promise.resolve();
});

function simuler({ ua, standalone = false, iosStandalone = undefined }) {
  Object.defineProperty(window.navigator, 'userAgent', { value: ua, configurable: true });
  Object.defineProperty(window.navigator, 'standalone', { value: iosStandalone, configurable: true });
  window.matchMedia = () => ({ matches: standalone, addListener() {}, removeListener() {} });
}

const monter = async (jsx) => {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(jsx); });
  await act(async () => { await Promise.resolve(); });
};

beforeEach(() => { try { localStorage.clear(); } catch (e) { /* mode privé */ } });
afterEach(() => { if (racine) act(() => racine.unmount()); if (conteneur) conteneur.remove(); });

describe('V659 — parcours d’installation', () => {
  test('1. abonné Android non installé : un VRAI bouton', async () => {
    simuler({ ua: UA.android });
    await monter(<InstallationAfroboost estAbonne prompt={{ prompt() {}, userChoice: Promise.resolve({}) }} />);
    expect(el('installation-afroboost')).toBeTruthy();
    expect(txt('installation-bouton-natif')).toMatch(/Installer Afroboost/);
  });

  test('2. abonné iPhone non installé : le guide, et AUCUN faux bouton', async () => {
    simuler({ ua: UA.iphone });
    await monter(<InstallationAfroboost estAbonne prompt={null} />);
    expect(el('installation-guide-ios')).toBeTruthy();
    expect(el('installation-bouton-natif')).toBeNull();   // la règle qui compte
    expect(txt('installation-guide-ios')).toMatch(/Partager/);
    expect(txt('installation-guide-ios')).toMatch(/écran d’accueil/);
  });

  test('2 bis. même avec un prompt qui traîne, l’iPhone garde le guide', async () => {
    simuler({ ua: UA.iphone });
    await monter(<InstallationAfroboost estAbonne prompt={{ prompt() {} }} />);
    expect(el('installation-bouton-natif')).toBeNull();
    expect(el('installation-guide-ios')).toBeTruthy();
  });

  test('3. déjà installée : RIEN, pas même le lien discret', async () => {
    simuler({ ua: UA.android, standalone: true });
    await monter(<InstallationAfroboost estAbonne prompt={{ prompt() {} }} />);
    expect(el('installation-afroboost')).toBeNull();
    expect(el('installation-lien-discret')).toBeNull();
  });

  test('3 bis. iPhone déjà ajouté à l’écran d’accueil : rien non plus', async () => {
    simuler({ ua: UA.iphone, iosStandalone: true });
    await monter(<InstallationAfroboost estAbonne prompt={null} />);
    expect(el('installation-afroboost')).toBeNull();
    expect(el('installation-lien-discret')).toBeNull();
  });

  test('un visiteur non abonné n’est jamais sollicité', async () => {
    simuler({ ua: UA.android });
    await monter(<InstallationAfroboost estAbonne={false} prompt={{ prompt() {} }} />);
    expect(el('installation-afroboost')).toBeNull();
    expect(el('installation-lien-discret')).toBeNull();   // visiteur : rien du tout
  });

  // ===================================================================
  // V666 — L'INSTALLATION EST UNE ÉTAPE, PLUS UNE SUGGESTION
  // ===================================================================
  // Ces trois contrôles REMPLACENT ceux du report (V660/V661) : sur un mobile
  // compatible, un abonné ne contourne plus la fenêtre. Ce qui protégeait
  // quelqu'un reste couvert ailleurs — visiteur, ordinateur et application
  // déjà installée sont testés plus haut, inchangés.

  test('V666 — sur mobile, l’abonné ne peut PAS fermer la fenêtre', async () => {
    simuler({ ua: UA.iphone });
    await monter(<InstallationAfroboost estAbonne prompt={null} />);
    const f = el('installation-afroboost');
    expect(f).toBeTruthy();
    // Le titre dit que c'est une étape d'accès, pas une invitation.
    expect(f.textContent).toMatch(/pour accéder à ton espace membre/i);
    // Ni « Plus tard », ni croix.
    expect(el('installation-plus-tard')).toBeNull();
    expect(conteneur.querySelector('[aria-label="Fermer"]')).toBeNull();
    // Un clic à côté ne la ferme pas non plus.
    await act(async () => { f.click(); });
    expect(el('installation-afroboost')).toBeTruthy();
  });

  test('V666 — mais « je n’arrive pas à installer » donne l’accès, et s’en souvient', async () => {
    simuler({ ua: UA.iphone });
    await monter(<InstallationAfroboost estAbonne prompt={null} />);
    const porte = el('installation-depannage');
    expect(porte).toBeTruthy();
    expect(porte.textContent).toMatch(/accéder quand même/i);
    await clic('installation-depannage');
    expect(el('installation-afroboost')).toBeNull();
    // Au rechargement, on ne la redemande pas : personne n'est pris en otage
    // d'un téléphone récalcitrant.
    act(() => racine.unmount()); conteneur.remove();
    await monter(<InstallationAfroboost estAbonne prompt={null} />);
    expect(el('installation-afroboost')).toBeNull();
  });

  test('V666 — un ORDINATEUR n’est jamais bloqué', async () => {
    simuler({ ua: UA.bureau });
    await monter(<InstallationAfroboost estAbonne prompt={null} />);
    // Sur ordinateur, la fenêtre EXPLIQUE (comportement d'origine, conservé)
    // mais ne barre jamais la route : le titre n'est pas celui d'une étape
    // d'accès, « Plus tard » est là, et aucune porte de dépannage n'est
    // nécessaire puisqu'il n'y a rien à dépanner.
    const f = el('installation-afroboost');
    if (f) {
      expect(f.textContent).not.toMatch(/pour accéder à ton espace membre/i);
      expect(el('installation-plus-tard')).toBeTruthy();
      expect(el('installation-depannage')).toBeNull();
    } else {
      // Rien du tout convient aussi : dans les deux cas, rien ne bloque.
      expect(el('installation-depannage')).toBeNull();
    }
  });


  test('navigateur incompatible : on explique, on ne bloque rien', async () => {
    simuler({ ua: UA.firefox });
    await monter(<InstallationAfroboost estAbonne prompt={null} />);
    expect(txt('installation-non-supporte')).toMatch(/réservations et tes paiements fonctionnent/);
  });
});

describe('V659 — la grande fenêtre de notification', () => {
  const notif = { id: 'n1', titre: 'Cours de mercredi déplacé',
                  texte: 'B'.repeat(400), type: 'cours', url: '/espace' };

  test('7-9. le texte ENTIER s’affiche, avec une action adaptée', async () => {
    simuler({ ua: UA.android });
    await monter(<NotificationGrande file={[notif]} />);
    expect(txt('notification-grande-titre')).toBe('Cours de mercredi déplacé');
    expect(txt('notification-grande-texte')).toHaveLength(400);   // rien n'est coupé
    expect(txt('notification-grande-texte')).not.toContain('…');
    expect(txt('notification-grande-action')).toBe('Voir mon cours');
  });

  test('10. l’action agit et marque la notification lue', async () => {
    const vus = [];
    simuler({ ua: UA.android });
    await monter(<NotificationGrande
      file={[{ ...notif, action: { libelle: 'Voir mon cours', onClick: () => vus.push('ouvert') } }]}
      onLue={(n) => vus.push('lue:' + n.id)} />);
    await clic('notification-grande-action');
    expect(vus).toEqual(expect.arrayContaining(['ouvert', 'lue:n1']));
  });

  test('la fermeture conserve l’état lu', async () => {
    const lues = [];
    simuler({ ua: UA.android });
    await monter(<NotificationGrande file={[notif]} onLue={(n) => lues.push(n.id)} />);
    await clic('notification-grande-fermer');
    expect(el('notification-grande')).toBeNull();
    expect(lues).toEqual(['n1']);
  });

  test('une seule fenêtre à la fois', async () => {
    simuler({ ua: UA.android });
    await monter(<NotificationGrande file={[{ id: 'a', titre: 'A', texte: 'a' },
                                            { id: 'b', titre: 'B', texte: 'b' }]} />);
    expect(document.querySelectorAll('[data-testid="notification-grande"]')).toHaveLength(1);
  });

  // LES DIMENSIONS SE LISENT DANS LA SOURCE, et non via `element.style` :
  // jsdom ne sait pas analyser `min(94vw, 520px)` ni `env(safe-area-inset-*)`
  // et vide alors la propriete. Un vrai navigateur, lui, les applique. On
  // verifie donc ce qui est ECRIT — objectif, et sans faux negatif.
  const SRC_NOTIF = fs.readFileSync(path.join(__dirname, '..', 'NotificationGrande.js'), 'utf8');
  const SRC_INST = fs.readFileSync(path.join(__dirname, '..', 'InstallationAfroboost.js'), 'utf8');

  test('les DIMENSIONS demandées sont bien celles déclarées', () => {
    expect(SRC_NOTIF).toContain("width: 'min(94vw, 520px)'");   // ~94 % sur téléphone
    expect(SRC_NOTIF).toContain("maxHeight: '85vh'");           // jusqu'à 85 % de la hauteur
    expect(SRC_NOTIF).toContain('borderRadius: 22');            // coins arrondis
    expect(SRC_NOTIF).toContain('fontSize: 16');                // 16-18 px demandés
    expect(SRC_NOTIF).toContain("overflowY: 'auto'");           // défilement interne
    expect(SRC_NOTIF).toContain("whiteSpace: 'pre-wrap'");      // aucun texte coupé
    expect(SRC_NOTIF).toContain('minHeight: 52');               // bouton principal large
    expect(SRC_NOTIF).toMatch(/env\(safe-area-inset-top\)/);    // encoche iPhone
    expect(SRC_NOTIF).toMatch(/env\(safe-area-inset-bottom\)/);
  });

  test('la fenêtre d’installation respecte les mêmes règles', () => {
    expect(SRC_INST).toContain("width: 'min(94vw, 460px)'");
    expect(SRC_INST).toContain("maxHeight: '85vh'");
    expect(SRC_INST).toContain("overflowY: 'auto'");
    expect(SRC_INST).toMatch(/env\(safe-area-inset-bottom\)/);
    expect(SRC_INST).toContain('minHeight: 54');                // « Installer » large
  });

  test('aucune couleur de marque en dur : la couleur du coach est respectée', () => {
    for (const src of [SRC_NOTIF, SRC_INST]) {
      const hex = (src.match(/#[0-9a-fA-F]{6}/g) || []).filter((h) => h.toUpperCase() !== '#D91CD2');
      // Seules des teintes de fond neutres sont admises, jamais un accent figé.
      expect(hex.every((h) => /^#0|^#1/.test(h))).toBe(true);
      expect(src).toContain('var(--primary-color, #D91CD2)');
    }
  });

  test('sans destination, aucun bouton inventé', async () => {
    simuler({ ua: UA.android });
    await monter(<NotificationGrande file={[{ id: 'c', titre: 'Info', texte: 'coucou' }]} />);
    expect(el('notification-grande-action')).toBeNull();
    expect(el('notification-grande-fermer')).toBeTruthy();   // on peut toujours fermer
  });
});
