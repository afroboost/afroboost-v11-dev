import {
  PLATEFORME, plateforme, estInstallee, peutInstallerNativement,
  modeInstallation, faudraitMontrer, ETAPES_IOS, ETAPES_ANDROID,
  lireReport, reportSuivant, RAPPELS_MAX, DELAI_RAPPEL_JOURS,
  installationObligatoire, mobileCompatible,
} from '../installationPWA';

const T0 = new Date('2026-11-11T09:00:00Z').getTime();
const JOUR = 86400000;

const UA = {
  iphone: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1',
  ipad13: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1',
  android: 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/126 Mobile Safari/537.36',
  mac: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36',
};

describe('V659 — reconnaître le téléphone', () => {
  test('iPhone, iPad moderne, Android, ordinateur', () => {
    expect(plateforme(UA.iphone)).toBe(PLATEFORME.IOS);
    expect(plateforme(UA.ipad13)).toBe(PLATEFORME.IOS);   // iPadOS se dit « Macintosh »
    expect(plateforme(UA.android)).toBe(PLATEFORME.ANDROID);
    expect(plateforme(UA.mac)).toBe(PLATEFORME.AUTRE);     // un Mac n'est pas un iPad
    expect(plateforme(null)).toBe(PLATEFORME.AUTRE);
  });

  test('déjà installée : les deux signes comptent', () => {
    expect(estInstallee(true, false)).toBe(true);    // Android : display-mode
    expect(estInstallee(false, true)).toBe(true);    // iOS : navigator.standalone
    expect(estInstallee(false, false)).toBe(false);
    expect(estInstallee(undefined, undefined)).toBe(false);
  });

  test("un bouton natif n'existe que si le navigateur l'a promis", () => {
    expect(peutInstallerNativement({ prompt: () => {} })).toBe(true);
    expect(peutInstallerNativement(null)).toBe(false);
    expect(peutInstallerNativement(undefined)).toBe(false);
  });
});

describe('V659 — que montrer, et à qui', () => {
  test('iPhone : JAMAIS de bouton, toujours le guide', () => {
    // La règle la plus importante du fichier : sur iPhone, aucune page web ne
    // peut installer. Même si un prompt traînait, on montre le guide.
    expect(modeInstallation({ userAgent: UA.iphone, prompt: null })).toBe('guide-ios');
    expect(modeInstallation({ userAgent: UA.iphone, prompt: { prompt: () => {} } })).toBe('guide-ios');
    expect(modeInstallation({ userAgent: UA.ipad13, prompt: null })).toBe('guide-ios');
  });

  test('Android : bouton natif si le navigateur le permet, sinon instructions', () => {
    expect(modeInstallation({ userAgent: UA.android, prompt: { prompt: () => {} } })).toBe('bouton-natif');
    expect(modeInstallation({ userAgent: UA.android, prompt: null })).toBe('instructions-android');
  });

  test('déjà installée : on ne montre plus rien, quel que soit le téléphone', () => {
    for (const ua of Object.values(UA)) {
      expect(modeInstallation({ userAgent: ua, standaloneMedia: true })).toBe('deja-installee');
      expect(modeInstallation({ userAgent: ua, navigatorStandalone: true })).toBe('deja-installee');
    }
  });

  test('ordinateur sans prompt : on le dit, on n’invente pas', () => {
    expect(modeInstallation({ userAgent: UA.mac, prompt: null })).toBe('non-supporte');
  });

  test('la fenêtre ne s’impose qu’aux abonnés', () => {
    const base = { mode: 'guide-ios', estAbonne: true, report: null, maintenant: T0 };
    expect(faudraitMontrer(base)).toBe(true);
    expect(faudraitMontrer({ ...base, estAbonne: false })).toBe(false);          // visiteur : jamais
    expect(faudraitMontrer({ ...base, mode: 'deja-installee' })).toBe(false);    // installée : jamais
    expect(faudraitMontrer({ ...base, jamaisPlus: true })).toBe(false);
  });

  test('V666 — l’installation est une ÉTAPE sur mobile, et seulement là', () => {
    // Un ABONNÉ sur mobile compatible : c'est une étape.
    expect(installationObligatoire({ mode: 'guide-ios', estAbonne: true })).toBe(true);
    expect(installationObligatoire({ mode: 'bouton-natif', estAbonne: true })).toBe(true);
    expect(installationObligatoire({ mode: 'instructions-android', estAbonne: true })).toBe(true);
    // Un VISITEUR n'a rien à installer pour regarder.
    expect(installationObligatoire({ mode: 'guide-ios', estAbonne: false })).toBe(false);
    // Un ORDINATEUR ne peut pas installer : on n'exige rien.
    expect(installationObligatoire({ mode: 'non-supporte', estAbonne: true })).toBe(false);
    // DÉJÀ INSTALLÉE : il n'y a plus d'étape.
    expect(installationObligatoire({ mode: 'deja-installee', estAbonne: true })).toBe(false);
    // Et la porte de dépannage est respectée : personne n'est pris en otage.
    expect(installationObligatoire({ mode: 'guide-ios', estAbonne: true, depannage: true })).toBe(false);
  });

  test('V666 — « mobile compatible » ne déborde jamais sur l’ordinateur', () => {
    expect(mobileCompatible('guide-ios')).toBe(true);
    expect(mobileCompatible('bouton-natif')).toBe(true);
    expect(mobileCompatible('instructions-android')).toBe(true);
    expect(mobileCompatible('non-supporte')).toBe(false);
    expect(mobileCompatible('deja-installee')).toBe(false);
    expect(mobileCompatible(null)).toBe(false);
  });

  test('V660 — « Plus tard » reporte d’une semaine, trois fois au plus', () => {
    const base = { mode: 'guide-ios', estAbonne: true, maintenant: T0 };
    // Le lendemain : on se tait.
    expect(faudraitMontrer({ ...base, report: { le: T0 - JOUR, fois: 1 } })).toBe(false);
    // Six jours : toujours trop tôt.
    expect(faudraitMontrer({ ...base, report: { le: T0 - 6 * JOUR, fois: 1 } })).toBe(false);
    // Sept jours : on repropose.
    expect(faudraitMontrer({ ...base, report: { le: T0 - 7 * JOUR, fois: 1 } })).toBe(true);
    expect(faudraitMontrer({ ...base, report: { le: T0 - 30 * JOUR, fois: 2 } })).toBe(true);
    // Au troisième « Plus tard », on n'insiste plus JAMAIS — même un an après.
    expect(faudraitMontrer({ ...base, report: { le: T0 - 365 * JOUR, fois: 3 } })).toBe(false);
    expect(RAPPELS_MAX).toBe(3);
    expect(DELAI_RAPPEL_JOURS).toBe(7);
  });

  test('V660 — un report illisible ne bloque rien', () => {
    expect(lireReport('nawak')).toBeNull();
    expect(lireReport(null)).toBeNull();
    expect(lireReport('{}')).toBeNull();
    expect(lireReport('{"le":0}')).toBeNull();
    expect(lireReport('{"le":123}')).toEqual({ le: 123, fois: 1 });
    // Illisible = jamais reporté = on propose : le cas le moins pénalisant.
    expect(faudraitMontrer({ mode: 'guide-ios', estAbonne: true, report: null, maintenant: T0 })).toBe(true);
  });

  test('V660 — chaque report incrémente le compteur', () => {
    expect(reportSuivant(null).fois).toBe(1);
    expect(reportSuivant({ le: 1, fois: 1 }).fois).toBe(2);
    expect(reportSuivant({ le: 1, fois: 2 }).fois).toBe(3);
  });

  test('les guides existent et tiennent en quelques étapes', () => {
    expect(ETAPES_IOS.length).toBe(5);
    expect(ETAPES_ANDROID.length).toBe(4);
    expect(ETAPES_IOS.map(e => e.n)).toEqual([1, 2, 3, 4, 5]);
    expect(ETAPES_IOS.every(e => e.texte.length > 10)).toBe(true);
    // Le guide iOS doit nommer le vrai chemin, pas un raccourci inventé.
    expect(ETAPES_IOS.some(e => /Partager/i.test(e.texte))).toBe(true);
    expect(ETAPES_IOS.some(e => /écran d’accueil/i.test(e.texte))).toBe(true);
  });
});
