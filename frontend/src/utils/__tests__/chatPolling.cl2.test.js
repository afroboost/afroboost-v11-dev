/**
 * CHAT-LOOP2 — AUCUN SONDAGE PERIODIQUE DU DASHBOARD NE DOIT RESTER SANS GARDE.
 *
 * CE QUE CE BANC REPARE. Celui de CHAT-LOOP1 verifiait que la chaine
 * `cl1DoitSonder(` etait PRESENTE dans `CoachDashboard.js`, au moins 3 fois.
 * Le fichier en comptait 8 `setInterval` : 3 gardes suffisaient a le rendre
 * vert. La validation en production du 29/08 a trouve les 5 autres, dont
 * `v441ChargerNonLus` qui tirait `GET /api/private/nonlus` toutes les 5 s sur
 * TOUS les onglets — 17 280 requetes/24 h, en 403.
 *
 * Un test de PRESENCE ne prouve pas une COUVERTURE. Celui-ci enumere les sites
 * d'appel et exige que chacun soit garde, ou declare avec sa raison.
 */
import {
  cl2AnalyserSetIntervals,
  cl2RequetesParJour,
  CL2_POLLERS_DASHBOARD,
  cl1DoitSonder,
} from '../chatPolling';

const fs = require('fs');
const path = require('path');
const DASH = fs.readFileSync(
  path.join(__dirname, '..', '..', 'components', 'CoachDashboard.js'), 'utf8');
const GROUPE = fs.readFileSync(
  path.join(__dirname, '..', '..', 'components', 'coach', 'GroupChatModule.js'), 'utf8');
const WIDGET = fs.readFileSync(
  path.join(__dirname, '..', '..', 'components', 'ChatWidget.js'), 'utf8');

/**
 * Meme depoussierage que le banc CHAT-LOOP1 : une assertion « ce symbole a
 * disparu » doit porter sur le CODE EXECUTE, pas sur le commentaire qui
 * explique la suppression — sinon on serait tente d'affaiblir l'assertion.
 */
function sansCommentaires(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1');
}
const DASH_CODE = sansCommentaires(DASH);

/* ══════════ L'OUTIL D'ABORD : un detecteur non prouve ne prouve rien ══════════ */

describe('CHAT-LOOP2 / 0. le detecteur attrape bien le cas qui a echappe', () => {
  test("`setInterval(fn, 5000)` nu est signale NON garde", () => {
    const faux = 'const t = setInterval(v441ChargerNonLus, 5000);';
    const [site] = cl2AnalyserSetIntervals(faux);
    expect(site.garde).toBe(false);
    expect(site.intervalleMs).toBe(5000);
  });

  test('la forme gardee est reconnue', () => {
    const bon = [
      'const t = setInterval(() => {',
      '  if (!cl1DoitSonder(document.visibilityState, navigator.onLine)) return;',
      '  v441ChargerNonLus();',
      '}, 5000);',
    ].join('\n');
    const [site] = cl2AnalyserSetIntervals(bon);
    expect(site.garde).toBe(true);
    expect(site.intervalleMs).toBe(5000);
  });

  test('une garde posee DANS la fonction appelee ne compte pas au site d appel', () => {
    // Volontaire : la cadence et sa garde doivent se lire au meme endroit.
    const trompeur = [
      'const f = () => { if (!cl1DoitSonder(a, b)) return; g(); };',
      'const t = setInterval(f, 5000);',
    ].join('\n');
    const sites = cl2AnalyserSetIntervals(trompeur);
    expect(sites).toHaveLength(1);
    expect(sites[0].garde).toBe(false);
  });

  test('les parentheses imbriquees ne cassent pas la lecture', () => {
    const imbrique = 'setInterval(() => { f(g(h(1)), k(2)); }, 8000);';
    const [site] = cl2AnalyserSetIntervals(imbrique);
    expect(site.intervalleMs).toBe(8000);
  });

  test('le detecteur aurait ete ROUGE sur le dashboard d avant CHAT-LOOP2', () => {
    // Reconstitution fidele des 5 sites oublies, tels qu'ils etaient ecrits.
    const avant = [
      'const id = setInterval(check, 60000);',
      'const interval = setInterval(checkSchedulerHealth, 30000);',
      'const campaignCheckInterval = setInterval(triggerCheck, 60000);',
      'const fastPollInterval = setInterval(pollSending, 3000);',
      'const t = setInterval(v441ChargerNonLus, 5000);',
    ].join('\n');
    const nonGardes = cl2AnalyserSetIntervals(avant).filter((s) => !s.garde);
    expect(nonGardes).toHaveLength(5);
  });
});

/* ══════════ LE FICHIER REEL ══════════ */

describe('CHAT-LOOP2 / 1. couverture reelle de CoachDashboard.js', () => {
  const sites = cl2AnalyserSetIntervals(DASH);

  test('chaque setInterval du dashboard est declare au registre', () => {
    // 3 pollers gardes par CHAT-LOOP1 + les 5 du registre CHAT-LOOP2.
    expect(sites.length).toBe(CL2_POLLERS_DASHBOARD.length + 3);
  });

  test('AUCUN setInterval du dashboard ne reste sans garde', () => {
    const nonGardes = sites.filter((s) => !s.garde);
    // Le message d'echec doit nommer le coupable, pas juste compter.
    expect(nonGardes.map((s) => s.extrait)).toEqual([]);
  });

  test('les cadences du registre existent bien dans le fichier', () => {
    const cadences = sites.map((s) => s.intervalleMs);
    CL2_POLLERS_DASHBOARD.forEach((p) => {
      expect(cadences).toContain(p.intervalleMs);
    });
  });

  test('aucun poller n est autorise a tirer en arriere-plan', () => {
    // Si un jour l'un doit vraiment tourner cache, il devra le declarer ICI,
    // avec sa raison — et ce test le rendra visible en revue.
    const enFond = CL2_POLLERS_DASHBOARD.filter((p) => p.fondAutorise);
    expect(enFond.map((p) => p.cle)).toEqual([]);
    CL2_POLLERS_DASHBOARD.forEach((p) => {
      expect(typeof p.raison).toBe('string');
      expect(p.raison.length).toBeGreaterThan(30);
    });
  });
});

/* ══════════ V441 : le sondage doit VIVRE quand l'onglet est visible ══════════ */

describe('CHAT-LOOP2 / 2. V441 nonlus : garde, pas suppression', () => {
  test('1. visible -> le sondage part', () => {
    expect(cl1DoitSonder('visible', true)).toBe(true);
  });
  test('2. cache -> zero appel', () => {
    expect(cl1DoitSonder('hidden', true)).toBe(false);
  });
  test('le sondage V441 existe toujours, a la meme cadence', () => {
    expect(DASH).toContain('/private/nonlus');
    expect(DASH).toContain('v441ChargerNonLus');
    const site = cl2AnalyserSetIntervals(DASH).find((s) => s.intervalleMs === 5000
      && s.extrait.includes('v441ChargerNonLus'));
    expect(site).toBeDefined();
    expect(site.garde).toBe(true);
  });
  test('3. le retour a l ecran declenche UNE relance, pas un timer de plus', () => {
    const poses = (DASH.match(/addEventListener\('visibilitychange'/g) || []).length;
    const retires = (DASH.match(/removeEventListener\('visibilitychange'/g) || []).length;
    // 2 de CHAT-LOOP1 (conversations 8 s, notifications 10 s) + 3 de CHAT-LOOP2
    // (les cadences lentes : 60 s, 30 s, 60 s). Exact, pour qu'un ecouteur
    // ajoute par megarde se voie en revue.
    const attendus = 2 + CL2_POLLERS_DASHBOARD.filter((p) => p.repriseImmediate).length;
    expect(poses).toBe(attendus);
    expect(retires).toBe(poses);           // 4. aucun ecouteur orphelin
    // La relance est un appel direct, jamais un nouveau setInterval.
    expect(DASH).not.toMatch(/visibilitychange[\s\S]{0,200}setInterval/);
  });
  test('les cadences rapides n ont PAS de reprise immediate (pas de rafale)', () => {
    CL2_POLLERS_DASHBOARD.forEach((p) => {
      // Regle explicite : reprise seulement si l'attente serait visible.
      expect(p.repriseImmediate).toBe(p.intervalleMs >= 30000);
    });
  });
  test('5. chaque setInterval a son clearInterval', () => {
    const poses = (DASH.match(/setInterval\s*\(/g) || []).length;
    const retires = (DASH.match(/clearInterval\s*\(/g) || []).length;
    expect(retires).toBeGreaterThanOrEqual(poses);
  });
});

/* ══════════ CHIFFRAGE ══════════ */

describe('CHAT-LOOP2 / 3. trafic retire', () => {
  test('le calcul, dashboard ouvert en continu', () => {
    expect(cl2RequetesParJour(5000)).toBe(17280);   // nonlus
    expect(cl2RequetesParJour(3000)).toBe(28800);   // progression d envoi
    expect(cl2RequetesParJour(30000)).toBe(2880);   // sante scheduler
    expect(cl2RequetesParJour(60000)).toBe(1440);   // badge, campagnes
    const total = CL2_POLLERS_DASHBOARD
      .reduce((s, p) => s + cl2RequetesParJour(p.intervalleMs), 0);
    expect(total).toBe(17280 + 2880 + 1440 + 28800 + 1440);
  });
});

/* ══════════ NON-REGRESSION : rien d autre ne bouge ══════════ */

describe('CHAT-LOOP2 / 4. les acquis de CHAT-LOOP1 tiennent', () => {
  test('8. la boucle N sessions est toujours absente', () => {
    expect(DASH_CODE).not.toContain('checkNewMessages');
    expect(DASH_CODE).not.toContain('lastMessageCountRef');
    expect(DASH_CODE).not.toMatch(/for\s*\([^)]*of\s+\w*[Ss]essions\w*\s*\)[\s\S]{0,400}\/messages/);
  });
  test('8bis. le depoussierage ne vide pas le fichier', () => {
    // Sans ce garde-fou, toute assertion « absent » passerait par construction.
    expect(DASH_CODE).toContain('v441ChargerNonLus');
    expect(DASH_CODE.length).toBeGreaterThan(DASH.length * 0.5);
  });
  test('9. une conversation ouverte reste a un seul poller', () => {
    const appels = DASH.match(/\/chat\/sessions\/\$\{[^}]+\}\/messages/g) || [];
    expect(appels.length).toBeLessThanOrEqual(3);
  });
  test('10. le ChatWidget visiteur est inchange', () => {
    expect(WIDGET).toContain("document.visibilityState === 'visible' && navigator.onLine");
    expect(WIDGET).not.toContain('cl2AnalyserSetIntervals');
  });
  test('11. le funnel partenaire est inchange', () => {
    expect(WIDGET).toContain('smart-entry');
  });
  test('le poller de groupe reste garde', () => {
    const sites = cl2AnalyserSetIntervals(GROUPE);
    expect(sites.length).toBe(1);
    expect(sites[0].garde).toBe(true);
  });
});
