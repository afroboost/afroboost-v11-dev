/**
 * CHAT-LOOP3 — LE GARDE-FOU S'ETEND A TOUT LE DASHBOARD, PAS A UN FICHIER.
 *
 * CHAT-LOOP2 auditait `CoachDashboard.js` et rien d'autre. Il restait donc
 * quatre sondages reseau du dashboard sans garde, dans `coach/CRMSection.js`
 * et `coach/MessagesWhatsApp.js`. Un registre qui ne couvre qu'un fichier ne
 * prouve rien sur les autres — c'est la meme lecon qu'en CHAT-LOOP2, ou un
 * test de PRESENCE ne prouvait rien sur la COUVERTURE.
 */
import {
  cl2AnalyserSetIntervals,
  cl2RequetesParJour,
  cl3RequetesRetireesParJour,
  CL3_POLLERS_DASHBOARD,
  CL3_EXCEPTIONS_DASHBOARD,
  cl1DoitSonder,
} from '../chatPolling';

const fs = require('fs');
const path = require('path');
const lire = (...p) => fs.readFileSync(path.join(__dirname, '..', '..', ...p), 'utf8');

const DASH = lire('components', 'CoachDashboard.js');
const CRM = lire('components', 'coach', 'CRMSection.js');
const WA = lire('components', 'coach', 'MessagesWhatsApp.js');
const GROUPE = lire('components', 'coach', 'GroupChatModule.js');
const WIDGET = lire('components', 'ChatWidget.js');
const CONTACTS = lire('components', 'dashboard', 'ContactsManager.js');

/* ══════════ 5. LE PERIMETRE AUDITE ══════════ */

describe('CHAT-LOOP3 / 5. le registre couvre tout le dashboard', () => {
  const PERIMETRE = [
    ['CoachDashboard.js', DASH],
    ['coach/CRMSection.js', CRM],
    ['coach/MessagesWhatsApp.js', WA],
    ['coach/GroupChatModule.js', GROUPE],
  ];

  test('AUCUN setInterval du perimetre dashboard ne reste sans garde', () => {
    const coupables = [];
    PERIMETRE.forEach(([nom, src]) => {
      cl2AnalyserSetIntervals(src)
        .filter((s) => !s.garde)
        .forEach((s) => coupables.push(`${nom} :: ${s.extrait}`));
    });
    // Le message d'echec nomme le fichier ET la ligne fautive.
    expect(coupables).toEqual([]);
  });

  test('chaque fichier du perimetre est reellement lu (garde-fou du garde-fou)', () => {
    PERIMETRE.forEach(([nom, src]) => {
      expect(typeof src).toBe('string');
      expect(src.length).toBeGreaterThan(500);
    });
    // Si un jour un fichier ne contenait plus aucun timer, le dire plutot que
    // de laisser le test passer par vacuite.
    const total = PERIMETRE.reduce((n, [, s]) => n + cl2AnalyserSetIntervals(s).length, 0);
    expect(total).toBe(8 + 2 + 1 + 1);   // dashboard 8, CRM 2, WhatsApp 1, groupe 1
  });

  test('les pollers hors CoachDashboard sont tous declares au registre', () => {
    const declares = CL3_POLLERS_DASHBOARD.length;
    const reels = cl2AnalyserSetIntervals(CRM).length
      + cl2AnalyserSetIntervals(WA).length
      + cl2AnalyserSetIntervals(GROUPE).length;
    expect(declares).toBe(reels);
    CL3_POLLERS_DASHBOARD.forEach((p) => {
      expect(p.fondAutorise).toBe(false);
      expect(p.raison.length).toBeGreaterThan(40);
      // Meme regle que CHAT-LOOP2 : reprise immediate seulement si l'attente serait visible.
      expect(p.repriseImmediate).toBe(p.intervalleMs >= 30000);
    });
  });

  test('les deux exceptions restent documentees et sans reseau periodique', () => {
    expect(CL3_EXCEPTIONS_DASHBOARD.map((e) => e.cle).sort())
      .toEqual(['clignotement-titre', 'oauth-google-contacts']);
    // L'exception OAuth doit rester auto-terminante : sans `clearInterval`
    // dans sa propre boucle, ce ne serait plus une exception acceptable.
    expect(CONTACTS).toContain('clearInterval(poll)');
    CL3_EXCEPTIONS_DASHBOARD.forEach((e) => expect(e.raison.length).toBeGreaterThan(40));
  });
});

/* ══════════ 1-4. MessagesWhatsApp ══════════ */

describe('CHAT-LOOP3 / 1-4. MessagesWhatsApp : /private/nonlus', () => {
  const sites = cl2AnalyserSetIntervals(WA);

  test('1+2. le sondage 5 s est garde (visible -> tire, hidden -> 0)', () => {
    expect(sites).toHaveLength(1);
    expect(sites[0].intervalleMs).toBe(5000);
    expect(sites[0].garde).toBe(true);
    expect(cl1DoitSonder('visible', true)).toBe(true);
    expect(cl1DoitSonder('hidden', true)).toBe(false);
  });
  test('le sondage existe toujours et vise le meme endpoint', () => {
    expect(WA).toContain('/private/nonlus');
    expect(WA).toContain('chargerNonLus');
  });
  test('l appel immediat au montage est conserve', () => {
    // Ouvrir l'ecran = le coach regarde : la premiere lecture reste inconditionnelle.
    expect(WA).toMatch(/chargerNonLus\(\);\s*\n\s*(\/\/[^\n]*\n\s*)*const t = setInterval/);
  });
  test('3. quitter le sous-onglet detruit le timer', () => {
    expect(WA).toContain('clearInterval(t)');
    expect(DASH).toContain("offersSubTab === 'whatsapp'");
  });
  test('4. aucune reprise immediate (cadence 5 s < 30 s)', () => {
    expect(WA).not.toContain('visibilitychange');
  });
});

/* ══════════ 5-10. CRMSection ══════════ */

describe('CHAT-LOOP3 / 5-10. CRMSection : conversations 30 s et messages 15 s', () => {
  const sites = cl2AnalyserSetIntervals(CRM);

  test('5+6. le poller conversations 30 s est garde', () => {
    const s = sites.find((x) => x.intervalleMs === 30000);
    expect(s).toBeDefined();
    expect(s.garde).toBe(true);
    expect(CRM).toContain('loadConversations(false)');
  });
  test('7. il a UNE reprise immediate, et aucun timer de plus', () => {
    const poses = (CRM.match(/addEventListener\('visibilitychange'/g) || []).length;
    const retires = (CRM.match(/removeEventListener\('visibilitychange'/g) || []).length;
    expect(poses).toBe(1);              // seul le 30 s en a droit
    expect(retires).toBe(poses);
    expect(CRM).not.toMatch(/visibilitychange[\s\S]{0,200}setInterval/);
  });
  test('8+9. le poller messages 15 s est garde', () => {
    const s = sites.find((x) => x.intervalleMs === 15000);
    expect(s).toBeDefined();
    expect(s.garde).toBe(true);
    expect(CRM).toContain('loadSessionMessages(selectedSession.id)');
  });
  test('10. changer de conversation detruit l ancien timer', () => {
    expect(CRM).toContain('clearInterval(msgInterval)');
    expect(CRM).toContain('clearInterval(convInterval)');
    expect(CRM).toMatch(/selectedSession\?\.id.*\]/s);
  });
});

/* ══════════ 11-12. le risque latent de boucle ══════════ */

describe('CHAT-LOOP3 / 11-12. la chaine remontage -> requete est coupee', () => {
  test('11. l appel IMMEDIAT de l effet notifications est garde', () => {
    // C'est le point precis : l'intervalle etait garde depuis CHAT-LOOP1,
    // mais l'appel immediat du (re)montage, lui, ne l'etait pas.
    // Assertion directe sur la forme exacte : la garde doit envelopper CET
    // appel-la, pas seulement exister quelque part dans le fichier.
    // SECURITY-S1 : l'appel passe par la reference vers la derniere version.
    expect(DASH).toMatch(
      /if \(cl1DoitSonder\(document\.visibilityState, navigator\.onLine\)\) \{\s*s1CheckUnreadRef\.current\(\);\s*\}/);
    // Et il ne doit plus rester d'appel immediat NU dans cet effet.
    expect(DASH).not.toMatch(/^\s{4}checkUnreadNotifications\(\);$/m);
    // SECURITY-S1 — LA CAUSE, pas seulement le symptome : la fonction ne doit
    // plus figurer dans les dependances de l'effet, sinon chaque ecriture de
    // `chatSessions` (toutes les 5 s) le remonterait et detruirait son minuteur
    // de 10 s avant son echeance — il ne tirait JAMAIS.
    expect(DASH).not.toContain('}, [tab, checkUnreadNotifications]);');
    expect(DASH).toContain('s1CheckUnreadRef.current = checkUnreadNotifications');
  });
  test('12. la dependance chatSessions est CONSERVEE (elle est utilisee)', () => {
    // On corrige l'appel, pas la dependance : `chatSessions.find(...)` est lu
    // dans le corps de la fonction. La retirer serait un bug de fraicheur.
    expect(DASH).toContain('}, [tab, chatSessions, addToastNotification, notifyOnAiResponse]);');
    expect(DASH).toContain('chatSessions.find(s => s.id === msg.session_id)');
  });
});

/* ══════════ 7. chiffrage ══════════ */

describe('CHAT-LOOP3 / 7. trafic retire onglet cache', () => {
  test('le calcul, dashboard laisse ouvert', () => {
    const r = cl3RequetesRetireesParJour();
    expect(r.crm_conversations).toBe(11520);   // 4 requetes x 2880 cycles
    expect(r.crm_messages).toBe(5760);
    expect(r.whatsapp_nonlus).toBe(17280);
    expect(cl2RequetesParJour(30000)).toBe(2880);
  });
});

/* ══════════ 13-17. non-regression ══════════ */

describe('CHAT-LOOP3 / 13-17. rien d autre ne bouge', () => {
  test('13. CHAT-LOOP1 : la boucle N sessions reste absente', () => {
    const sansCommentaires = (s) => s
      .replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');
    const code = sansCommentaires(DASH);
    expect(code).not.toContain('checkNewMessages');
    expect(code).not.toContain('lastMessageCountRef');
    expect(code.length).toBeGreaterThan(DASH.length * 0.5);
  });
  test('14. CHAT-LOOP2 : les 8 timers de CoachDashboard restent gardes', () => {
    const sites = cl2AnalyserSetIntervals(DASH);
    expect(sites).toHaveLength(8);
    expect(sites.filter((s) => !s.garde)).toEqual([]);
  });
  test('15. une conversation ouverte : deux pollers connus, tous deux gardes', () => {
    // 8 s dans CoachDashboard + 15 s dans CRMSection. Pas un de plus.
    const dash8 = cl2AnalyserSetIntervals(DASH).find((s) => s.intervalleMs === 8000);
    const crm15 = cl2AnalyserSetIntervals(CRM).find((s) => s.intervalleMs === 15000);
    expect(dash8.garde).toBe(true);
    expect(crm15.garde).toBe(true);
  });
  test('16. le funnel partenaire est inchange', () => {
    expect(WIDGET).toContain('smart-entry');
  });
  test('17. le ChatWidget visiteur est inchange', () => {
    expect(WIDGET).toContain("document.visibilityState === 'visible' && navigator.onLine");
    expect(WIDGET).not.toContain('CL3_POLLERS_DASHBOARD');
  });
});
