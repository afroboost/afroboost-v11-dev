/**
 * V669 — LES DEUX DÉFAUTS SIGNALÉS SUR LE VRAI ESPACE MEMBRE.
 *
 * Les deux ont été REPRODUITS dans un navigateur réel (11/11/2026) avant
 * d'être corrigés. Ce banc fige les corrections.
 *
 * DÉFAUT 1 — « Réactiver » ne disait rien. Mesure avant correction :
 *     avant le clic : « Reçois les rappels de cours | Activer »
 *     après le clic : « Reçois les rappels de cours | Activer »
 * Identique au caractère près, aucun message. `assurerAbonnementPush` calcule
 * pourtant un `motif` — il était jeté. Et en cas de succès la carte
 * disparaissait sans rien confirmer.
 *
 * DÉFAUT 2 — la fenêtre d'installation était INVISIBLE, pas absente : elle
 * s'affichait à `z-index: 10000`, DERRIÈRE la grande fenêtre de notification
 * (`z-index: 10050`). Mesuré dans le navigateur.
 *
 * DÉFAUT 3, trouvé au passage — Chrome de BUREAU déclenche
 * `beforeinstallprompt`, donc `modeInstallation` rendait `bouton-natif` et
 * l'installation devenait obligatoire SUR ORDINATEUR. La consigne l'interdit.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import CarteNotifications, { messageEchec } from '../CarteNotifications';
import {
  installationObligatoire, mobileCompatible, PLATEFORME,
} from '../../utils/installationPWA';

jest.mock('../../services/pushNotificationService', () => ({
  __esModule: true,
  etatNotifications: jest.fn(() => 'default'),
  assurerAbonnementPush: jest.fn(async () => ({ etat: 'default', abonne: false })),
  activerNotifications: jest.fn(async () => ({ etat: 'default', abonne: false })),
}));
const svc = require('../../services/pushNotificationService');

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

let conteneur, racine;
const el = (t) => conteneur.querySelector(`[data-testid="${t}"]`);

async function monter() {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => {
    racine.render(<CarteNotifications participantId="sub_x" role="subscriber" email="x@y.z" />);
  });
  await act(async () => { await Promise.resolve(); });
}

afterEach(async () => {
  if (racine) await act(async () => racine.unmount());
  if (conteneur) conteneur.remove();
  racine = null; conteneur = null;
  jest.clearAllMocks();
  svc.etatNotifications.mockReturnValue('default');
});

describe('V669 — défaut 1 : « Réactiver » dit enfin ce qui se passe', () => {
  test('SUCCÈS : « Rappels activés », et le bouton disparaît', async () => {
    svc.activerNotifications.mockResolvedValue({ etat: 'granted', abonne: true, endpoint: 'https://fcm/x' });
    await monter();
    await act(async () => { el('carte-notifications-activer').click(); });
    await act(async () => { await Promise.resolve(); });

    expect(el('carte-notifications-confirme')).toBeTruthy();
    expect(el('carte-notifications-confirme').textContent).toMatch(/Rappels activés/);
    // Le bouton n'a plus lieu d'être.
    expect(el('carte-notifications-activer')).toBeNull();
  });

  test('ÉCHEC : une explication s’affiche, et AUCUNE fausse confirmation', async () => {
    svc.activerNotifications.mockResolvedValue({ etat: 'default', abonne: false });
    await monter();
    const avant = el('carte-notifications').textContent;
    await act(async () => { el('carte-notifications-activer').click(); });
    await act(async () => { await Promise.resolve(); });

    // C'EST LE CŒUR DU DÉFAUT : avant, ces deux textes étaient identiques.
    expect(el('carte-notifications').textContent).not.toBe(avant);
    expect(el('carte-notifications-echec')).toBeTruthy();
    expect(el('carte-notifications-confirme')).toBeNull();
  });

  test('PERMISSION ACCORDÉE MAIS AUCUN ABONNEMENT n’est PAS un succès', async () => {
    // Le piège : `etat: granted` sans abonnement. Annoncer « activés » ici
    // laisserait quelqu'un croire qu'il recevra des rappels qu'il n'aura pas.
    svc.activerNotifications.mockResolvedValue({ etat: 'granted', abonne: false, motif: 'vapid_absente' });
    await monter();
    await act(async () => { el('carte-notifications-activer').click(); });
    await act(async () => { await Promise.resolve(); });

    expect(el('carte-notifications-confirme')).toBeNull();
    expect(el('carte-notifications-echec').textContent).toMatch(/indisponible|Réessaie/i);
  });

  test('chaque cause a son geste — et jamais « réessaie » sur un iPhone non installé', () => {
    expect(messageEchec({ etat: 'non_supporte' })).toMatch(/écran d['’]accueil/);
    expect(messageEchec({ etat: 'non_supporte' })).not.toMatch(/Réessaie/);
    expect(messageEchec({ etat: 'denied' })).toMatch(/réglages/i);
    expect(messageEchec({ etat: 'default' })).toMatch(/Autoriser/);
    expect(messageEchec({ etat: 'granted', motif: 'vapid_absente' })).toMatch(/indisponible/);
    expect(messageEchec({})).toMatch(/Réessaie/);
  });
});

describe('V669 — défaut 3 : un ordinateur n’est jamais bloqué', () => {
  test('Chrome de BUREAU sait installer, mais n’est pas un mobile', () => {
    // C'est exactement ce qui rendait l'étape obligatoire sur ordinateur.
    expect(mobileCompatible('bouton-natif', PLATEFORME.AUTRE)).toBe(false);
    expect(installationObligatoire({
      mode: 'bouton-natif', estAbonne: true, plate: PLATEFORME.AUTRE,
    })).toBe(false);
  });

  test('un ANDROID reste obligatoire, un iPHONE aussi', () => {
    expect(mobileCompatible('bouton-natif', PLATEFORME.ANDROID)).toBe(true);
    expect(mobileCompatible('instructions-android', PLATEFORME.ANDROID)).toBe(true);
    expect(mobileCompatible('guide-ios', PLATEFORME.IOS)).toBe(true);
    // Sur iPhone, le guide vaut même sans plateforme transmise.
    expect(mobileCompatible('guide-ios')).toBe(true);
    expect(installationObligatoire({
      mode: 'bouton-natif', estAbonne: true, plate: PLATEFORME.ANDROID,
    })).toBe(true);
  });

  test('déjà installée, ou dépannage déclaré : jamais obligatoire', () => {
    expect(mobileCompatible('deja-installee', PLATEFORME.ANDROID)).toBe(false);
    expect(installationObligatoire({
      mode: 'guide-ios', estAbonne: true, plate: PLATEFORME.IOS, depannage: true,
    })).toBe(false);
  });
});
