/**
 * CHAT-LOOP1 — LE SONDAGE NE DOIT PLUS DEPENDRE DU NOMBRE DE CONVERSATIONS.
 *
 * Mesure du 29/08 : 126 660 requetes/24 h depuis une seule IP vers
 * `/api/chat/sessions/<id>/messages`, 98,69 k bloquees par Cloudflare — 73 %
 * du trafic du site. Cause : `checkNewMessages` bouclait sur les 69 sessions
 * en mode humain, toutes les 5 s, sans garde de visibilite.
 *
 * L'ORDRE DES BANCS COMPTE. Les assertions de NON-REGRESSION sont ecrites
 * EN PREMIER et etaient vertes AVANT le correctif : elles prouvent que le
 * badge non-lu, le fil de la conversation ouverte et les toasts ne dependaient
 * deja PAS de la boucle supprimee. Sans cette preuve prealable, retirer la
 * boucle serait un pari.
 */
import {
  cl1DoitSonder,
  cl1RequetesMessagesParCycle,
  cl1RequetesParHeure,
  CL1_INTERVALLE_SESSIONS,
  CL1_INTERVALLE_CONVERSATIONS,
  CL1_INTERVALLE_NOTIFICATIONS,
} from '../chatPolling';

const fs = require('fs');
const path = require('path');
const DASH = fs.readFileSync(
  path.join(__dirname, '..', '..', 'components', 'CoachDashboard.js'), 'utf8');

/**
 * Retire les commentaires avant d'affirmer qu'un symbole a disparu.
 * Sans cela, le commentaire qui EXPLIQUE la suppression ferait echouer
 * l'assertion — et la tentation serait d'affaiblir l'assertion plutot que
 * de la faire porter sur ce qui compte : le code execute.
 */
function sansCommentaires(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')   // blocs
    .replace(/(^|[^:])\/\/.*$/gm, '$1');  // lignes (sans casser « http:// »)
}
const DASH_CODE = sansCommentaires(DASH);
const GROUPE = fs.readFileSync(
  path.join(__dirname, '..', '..', 'components', 'coach', 'GroupChatModule.js'), 'utf8');
const WIDGET = fs.readFileSync(
  path.join(__dirname, '..', '..', 'components', 'ChatWidget.js'), 'utf8');

/* ══════════ NON-REGRESSION — vert AVANT comme APRES le correctif ══════════ */

describe('CHAT-LOOP1 / 10-12. le nouveau message reste detecte SANS la boucle', () => {
  test('10-11. le badge non-lu vient de /notifications/unread, pas de la boucle', () => {
    expect(DASH).toContain('/notifications/unread');
    expect(DASH).toContain('setUnreadCount(count)');
    // ...et son poller a sa propre cadence, independante.
    expect(DASH).toContain('checkUnreadNotifications();');
  });
  test('10. le fil de la conversation OUVERTE est rafraichi par le poller 8 s', () => {
    const i = DASH.indexOf('if (msgRes?.data) setSessionMessages(msgRes.data)');
    expect(i).toBeGreaterThan(0);
    const bloc = DASH.slice(i - 400, i);
    expect(bloc).toContain('selectedSession?.id');
    expect(bloc).toContain('/chat/sessions/${selectedSession.id}/messages');
  });
  test('11. les toasts continuent de retrouver leur session', () => {
    expect(DASH).toContain('chatSessions.find(s => s.id === msg.session_id)');
  });
  test('12. last_message / message_count arrivent toujours par /conversations', () => {
    expect(DASH).toContain("axios.get(`${API}/conversations`");
    expect(DASH).toContain('setEnrichedConversations(');
  });
  test('la liste complete des sessions reste alimentee par /chat/sessions', () => {
    expect(DASH).toContain("axios.get(`${API}/chat/sessions`)");
  });
});

describe('CHAT-LOOP1 / 13-15. les parcours voisins ne bougent pas', () => {
  test('13. le poller 3 s du ChatWidget visiteur est intact, garde comprise', () => {
    expect(WIDGET).toContain('const POLL_INTERVAL = 3000');
    expect(WIDGET).toContain("document.visibilityState === 'visible' && navigator.onLine");
    expect(WIDGET).toContain('clearInterval(pollRef)');
  });
  test('14-15. essai gratuit et funnel partenaire intacts', () => {
    expect(WIDGET).toContain("On te confirme ton cours d'essai sur WhatsApp.");
    expect(WIDGET).toContain('trialConfirmPartner ? P12_FIN_PARTENAIRE.corps :');
    expect(WIDGET).toContain('submission_id');
  });
});

/* ══════════ L'INVARIANT DU LOT — rouge AVANT, vert APRES ══════════ */

describe('CHAT-LOOP1 / 1+3. N conversations ne font plus N requetes', () => {
  test('1. la boucle par session a disparu du CODE', () => {
    expect(DASH_CODE).not.toContain('const humanSessions = chatSessions.filter');
    expect(DASH_CODE).not.toContain('for (const session of humanSessions)');
    expect(DASH_CODE).not.toContain('checkNewMessages');
    expect(DASH_CODE).not.toContain('lastMessageCountRef');
  });
  test('1bis. le depoussierage des commentaires ne masque pas le code', () => {
    // Garde-fou du garde-fou : si `sansCommentaires` retirait trop, toute
    // assertion « absent » deviendrait vraie par construction.
    expect(DASH_CODE).toContain('const [chatSessions, setChatSessions] = useState([]);');
    expect(DASH_CODE).toContain('cl1DoitSonder(document.visibilityState, navigator.onLine)');
    expect(DASH_CODE.length).toBeGreaterThan(DASH.length * 0.5);
  });
  test('3. le nombre de requetes de messages par cycle est CONSTANT', () => {
    // 0, 1, 20, 69, 915 : la valeur ne bouge pas avec le nombre de sessions.
    [0, 1, 20, 69, 915, 10000].forEach((n) => {
      expect(cl1RequetesMessagesParCycle(n, true)).toBe(1);
      expect(cl1RequetesMessagesParCycle(n, false)).toBe(0);
    });
  });
  test('2. une conversation ouverte -> AU PLUS un poller de messages', () => {
    const appels = DASH.match(/\/chat\/sessions\/\$\{[^}]+\}\/messages/g) || [];
    // Il en reste : le chargement a la selection, et le rafraichissement du
    // poller 8 s. Aucun autre — surtout aucun a l'interieur d'une boucle.
    expect(appels.length).toBeLessThanOrEqual(3);
    expect(DASH).not.toMatch(/for\s*\([^)]*of\s+\w*[Ss]essions\w*\s*\)[\s\S]{0,400}\/messages/);
  });
});

describe('CHAT-LOOP1 / 6-7. garde de visibilite sur le dashboard', () => {
  test('6. les pollers du dashboard ne tirent pas onglet cache', () => {
    expect(DASH).toContain("import { cl1DoitSonder }");
    const occurrences = (DASH.match(/cl1DoitSonder\(/g) || []).length;
    // Les trois pollers de l'onglet Conversations : 10 s, 5 s, 8 s.
    expect(occurrences).toBeGreaterThanOrEqual(3);
  });
  test('6. le poller de groupe non plus', () => {
    expect(GROUPE).toContain('cl1DoitSonder(');
  });
  test('7. le retour a l ecran declenche UNE relance immediate', () => {
    expect(DASH).toContain("document.addEventListener('visibilitychange'");
    expect(DASH).toContain("document.removeEventListener('visibilitychange'");
  });
});

describe('CHAT-LOOP1 / 4-5+8-9. cycles de vie des timers', () => {
  test('4-5. chaque setInterval du dashboard a son clearInterval', () => {
    const poses = (DASH.match(/setInterval\(/g) || []).length;
    const retires = (DASH.match(/clearInterval\(/g) || []).length;
    expect(retires).toBeGreaterThanOrEqual(poses);
  });
  test('8. le poller 5 s ne depend plus d une fonction recreee a chaque rendu', () => {
    // `[tab, checkNewMessages]` detruisait et recreait l'intervalle a chaque
    // ecriture de `chatSessions` — soit toutes les 5 et 8 secondes.
    expect(DASH).not.toContain('}, [tab, checkNewMessages]);');
  });
  test('9. une seule source ecrit la liste affichee des conversations', () => {
    // Le poller 8 s ecrivait `chatSessions` avec 20 elements pendant que le
    // poller 5 s y ecrivait la liste complete : l'etat oscillait entre 915 et 20.
    expect(DASH).not.toContain('setChatSessions(convsRes.data.conversations)');
  });
});

describe('CHAT-LOOP1 / regles pures', () => {
  test('on ne sonde pas onglet cache', () => {
    expect(cl1DoitSonder('visible', true)).toBe(true);
    expect(cl1DoitSonder('hidden', true)).toBe(false);
    expect(cl1DoitSonder('prerender', true)).toBe(false);
    expect(cl1DoitSonder('visible', false)).toBe(false);
  });
  test('une entree aberrante ne bloque jamais le chat', () => {
    expect(cl1DoitSonder(undefined, undefined)).toBe(false);
    expect(cl1DoitSonder('visible', undefined)).toBe(true);
  });
  test('les cadences sont celles en place', () => {
    expect(CL1_INTERVALLE_SESSIONS).toBe(5000);
    expect(CL1_INTERVALLE_CONVERSATIONS).toBe(8000);
    expect(CL1_INTERVALLE_NOTIFICATIONS).toBe(10000);
  });
  test('10. le chiffrage avant/apres', () => {
    // AVANT : 69 sessions humaines, une requete chacune, toutes les 5 s.
    expect(cl1RequetesParHeure(69, CL1_INTERVALLE_SESSIONS)).toBe(49680);
    // APRES : une conversation ouverte, une requete, toutes les 8 s.
    expect(cl1RequetesParHeure(1, CL1_INTERVALLE_CONVERSATIONS)).toBe(450);
  });
});
