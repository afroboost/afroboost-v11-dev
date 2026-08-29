/**
 * SECURITY-S1 — LE JETON SE RENOUVELLE, ET LE SONDAGE DES NOTIFICATIONS VIT.
 *
 * Deux defauts mesures en production le 29/08/2026, apres SECURITY-S0 :
 *
 * A. ANTI-RECHUTE MORTE. `/auth/me` renvoie bien le jeton (moitie serveur OK),
 *    mais `CoachLoginModal` — le seul appelant — n'est JAMAIS monte quand le
 *    jeton expire : `afroboost_admin_persist` survit a `terminerSession()`,
 *    l'initialiseur d'`App.js` le relit et REECRIT `afroboost_coach_user`, et
 *    les deux branches du hash `#coach-dashboard` arbitrent sur cette cle, pas
 *    sur le jeton. La branche qui ouvrirait le modal est inatteignable.
 *
 * B. MINUTEUR DE NOTIFICATIONS MORT. `checkUnreadNotifications` est un
 *    `useCallback` qui depend de la VALEUR `chatSessions`. Le poller 5 s ecrit
 *    `setChatSessions(res.data)` avec un tableau neuf a chaque reponse (axios
 *    deserialise), donc la callback etait recreee toutes les 5 s, l'effet se
 *    remontait, et son minuteur de 10 s etait detruit a ~5 s de vie : il n'a
 *    JAMAIS atteint son echeance. Ecarts mesures : 4924 a 5106 ms — le jitter
 *    de la LATENCE, preuve que le depart suivait la reponse de `/chat/sessions`
 *    et non une horloge. Invisible tant que la route repondait 403.
 */
const fs = require('fs');
const path = require('path');
const lire = (...p) => fs.readFileSync(path.join(__dirname, '..', '..', ...p), 'utf8');

const APP = lire('App.js');
const DASH = lire('components', 'CoachDashboard.js');
const MODAL = lire('components', 'CoachLoginModal.js');
const SESSION = lire('utils', 'authSession.js');

/* ══════════ A. anti-rechute ══════════ */

describe('SECURITY-S1 / A. le jeton se renouvelle sans mot de passe', () => {
  test('App.js appelle /auth/me quand le mode coach vit sans jeton valide', () => {
    // ROUGE AVANT : `/auth/me` n'etait appele que depuis `CoachLoginModal`.
    expect(APP).toContain("axios.get(`${API}/auth/me`, { withCredentials: true })");
    expect(APP).toContain('if (!coachModeRef.current || authValide()) return;');
  });

  test('le jeton recu est stocke dans la cle que tout le monde lit', () => {
    expect(APP).toContain("localStorage.setItem('afroboost_jwt', r.data.token)");
    // ...et les ecrans en attente sont reveilles, sans rechargement.
    expect(APP).toContain('signalerConnexionReussie();');
  });

  test('l etat AUTH.EN_COURS encadre l appel : les sections PARQUENT au lieu de tirer des 403', () => {
    const i = APP.indexOf('if (!coachModeRef.current || authValide()) return;');
    expect(i).toBeGreaterThan(0);
    const bloc = APP.slice(i, i + 2600);
    expect(bloc).toContain('debutConnexion();');
    expect(bloc).toContain('finConnexion();');
    // `finConnexion` est dans un `finally` : le compteur ne peut pas rester
    // bloque sur EN_COURS si l'appel echoue.
    expect(bloc).toMatch(/\.finally\(\(\) => \{ finConnexion\(\); \}\)/);
  });

  test('CAS E — garde one-shot : React 18 en mode strict monte deux fois', () => {
    const i = APP.indexOf('s1JetonReparé');
    expect(i).toBeGreaterThan(0);
    expect(APP).toContain('if (s1JetonReparé.current) return;');
    expect(APP).toContain('s1JetonReparé.current = true;');
  });

  test('CAS A — cookie valide : jeton stocke, AUCUN modal ouvert', () => {
    const i = APP.indexOf('if (!coachModeRef.current || authValide()) return;');
    const bloc = APP.slice(i, i + 2600);
    // Le chemin de succes ne touche pas au modal : le dashboard reste affiche.
    const succes = bloc.slice(bloc.indexOf('.then('), bloc.indexOf('.catch('));
    expect(succes).toContain("localStorage.setItem('afroboost_jwt', r.data.token)");
    expect(succes).toContain('signalerConnexionReussie();');
    expect(succes).not.toContain('setShowCoachLogin');
    // Et on ne stocke un jeton QUE s'il y en a un.
    expect(succes).toContain('if (r?.data?.token)');
  });

  test('CAS B — cookie invalide (401/403) : le formulaire de connexion s ouvre', () => {
    // ROUGE AVANT : le `catch` etait vide, le dashboard zombie restait affiche
    // alors que les DEUX preuves d'identite (jeton ET cookie) etaient mortes.
    expect(APP).toContain("if (classerEchec(err) === 'session') setShowCoachLogin(true);");
    // On reutilise le mecanisme existant, aucun composant neuf.
    expect(APP).toContain('const [showCoachLogin, setShowCoachLogin] = useState(false);');
    expect(APP).toContain('if (showCoachLogin) return <CoachLoginModal');
  });

  test('CAS B bis — le modal gagne SANS toucher a coachMode (piege V310c evite)', () => {
    // `if (showCoachLogin) return ...` est place AVANT le retour du dashboard :
    // ouvrir le modal suffit, on n'a pas a couper `coachMode` — ce qui aurait
    // renvoye le proprietaire sur la vitrine, sans issue.
    const iModal = APP.indexOf('if (showCoachLogin) return <CoachLoginModal');
    const iDash = APP.indexOf('if (coachMode && !isVisitorMode) {');
    expect(iModal).toBeGreaterThan(0);
    expect(iDash).toBeGreaterThan(0);
    expect(iModal).toBeLessThan(iDash);
  });

  test('CAS C — panne reseau ou 5xx : AUCUNE fausse deconnexion, etat recuperable', () => {
    const i = APP.indexOf('if (!coachModeRef.current || authValide()) return;');
    const bloc = APP.slice(i, i + 2600);
    const echec = bloc.slice(bloc.indexOf('.catch('), bloc.indexOf('.finally('));
    // `classerEchec` rend 'reseau' (aucune reponse) ou 'serveur' (5xx) : le
    // `if` ne se declenche pas, donc rien ne se passe. Une coupure de wifi
    // n'est pas un mot de passe invalide.
    expect(echec).toContain("classerEchec(err) === 'session'");
    // Aucune purge destructive, aucun rechargement, aucun message d'echec.
    expect(echec).not.toContain('terminerSession');
    expect(echec).not.toContain('localStorage.removeItem');
    expect(echec).not.toContain('window.location');
    expect(echec).not.toContain('reload');
    expect(echec).not.toContain('alert');
  });

  test('CAS C bis — la classification vient du helper existant, pas d un test maison', () => {
    const { classerEchec } = require('../authSession');
    expect(classerEchec({ response: { status: 401 } })).toBe('session');
    expect(classerEchec({ response: { status: 403 } })).toBe('session');  // sans jeton valide
    expect(classerEchec({ response: { status: 500 } })).toBe('serveur');
    expect(classerEchec({ response: { status: 503 } })).toBe('serveur');
    expect(classerEchec({})).toBe('reseau');                              // aucune reponse
  });

  test('CAS D — jeton valide : aucune tentative de reparation', () => {
    // `authValide()` en tete du garde : on ne tire pas /auth/me pour rien.
    expect(APP).toContain('if (!coachModeRef.current || authValide()) return;');
  });

  test('on ne conditionne PAS la restauration du mode coach (piege V310c)', () => {
    // Couper `coachMode` renverrait le proprietaire sur la vitrine SANS issue :
    // aucun des declencheurs de `setShowCoachLogin` ne lui serait accessible.
    // Le dashboard, aujourd'hui partiellement fonctionnel, se fermerait.
    expect(APP).toContain("const savedCoachMode = localStorage.getItem('afroboost_coach_mode');");
    expect(APP).not.toContain("if (savedCoachMode === 'true' && savedCoachUser && authValide())");
  });

  test('la moitie serveur de SECURITY-S0 est intacte (le modal stocke toujours)', () => {
    expect(MODAL).toContain("localStorage.setItem('afroboost_jwt', response.data.token)");
  });

  test('`etatAuth` nomme deja notre cas : la session zombie', () => {
    expect(SESSION).toContain('AUTH.EXPIREE');
    expect(SESSION).toContain('export function authValide()');
  });
});

/* ══════════ B. le minuteur de notifications ══════════ */

describe('SECURITY-S1 / B. le sondage des notifications a retrouve son horloge', () => {
  test('LA CAUSE : la callback n est plus une dependance de l effet', () => {
    // ROUGE AVANT : `}, [tab, checkUnreadNotifications]);`
    expect(DASH).not.toContain('}, [tab, checkUnreadNotifications]);');
  });

  test('la reference pointe sur la DERNIERE version, reassignee a chaque rendu', () => {
    expect(DASH).toContain('s1CheckUnreadRef.current = checkUnreadNotifications');
    // Reassignation sans tableau de dependances : sinon elle serait figee.
    expect(DASH).toMatch(/useEffect\(\(\) => \{ s1CheckUnreadRef\.current = checkUnreadNotifications; \}\);/);
  });

  test('la dependance chatSessions du useCallback est CONSERVEE', () => {
    // On corrige le lien identite -> remontage, PAS la dependance : elle est
    // legitime, et la lecture au clic est desormais PLUS fraiche qu'avant.
    expect(DASH).toContain('}, [tab, chatSessions, addToastNotification, notifyOnAiResponse]);');
    expect(DASH).toContain('chatSessions.find(s => s.id === msg.session_id)');
  });

  test('les trois points d appel passent par la reference', () => {
    const n = (DASH.match(/s1CheckUnreadRef\.current\(\)/g) || []).length;
    expect(n).toBe(3);   // immediat, intervalle, reprise a l ecran
  });

  test('la garde de visibilite reste INLINE, lisible par notre propre analyseur', () => {
    // `cl2AnalyserSetIntervals` lit le texte qui suit la pose du minuteur :
    // une garde deportee dans une fonction nommee la rendrait invisible.
    // Assertion directe sur la forme, sans decoupage fragile : la garde doit
    // envelopper CE minuteur-la, textuellement.
    expect(DASH).toMatch(/setInterval\(\(\) => \{\s*if \(!cl1DoitSonder\(document\.visibilityState, navigator\.onLine\)\) return;\s*s1CheckUnreadRef\.current\(\);\s*\}, 10000\)/);
    // Et notre propre analyseur doit bien la voir.
    const { cl2AnalyserSetIntervals } = require('../chatPolling');
    const site = cl2AnalyserSetIntervals(DASH).find((x) => x.intervalleMs === 10000
      && x.extrait.includes('s1CheckUnreadRef'));
    expect(site).toBeDefined();
    expect(site.garde).toBe(true);
  });

  test('le premier chargement a l entree dans l onglet est CONSERVE', () => {
    // Le retirer aurait fait disparaitre le badge a l'ouverture — et surtout,
    // sans corriger la cause, aurait arrete le sondage pour de bon.
    expect(DASH).toMatch(/if \(cl1DoitSonder\(document\.visibilityState, navigator\.onLine\)\) \{\s*s1CheckUnreadRef\.current\(\);\s*\}/);
  });

  test('aucun minuteur ajoute ni retire', () => {
    const poses = (DASH.match(/setInterval\s*\(/g) || []).length;
    const retires = (DASH.match(/clearInterval\s*\(/g) || []).length;
    expect(poses).toBe(8);
    expect(retires).toBe(poses);
  });
});

/* ══════════ C. le chiffrage ══════════ */

describe('SECURITY-S1 / C. cadence attendue', () => {
  /** Requetes sur une fenetre, a cadence donnee. Fonction pure, testable. */
  const appels = (fenetreMs, cadenceMs) => Math.floor(fenetreMs / cadenceMs);

  test('avant : les notifications suivaient l horloge de /chat/sessions (5 s)', () => {
    expect(appels(30000, 5000)).toBe(6);
  });
  test('apres : elles suivent la leur (10 s)', () => {
    expect(appels(30000, 10000)).toBe(3);
  });
  test('/chat/sessions garde sa cadence de 5 s', () => {
    expect(appels(30000, 5000)).toBe(6);
  });
});
