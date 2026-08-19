/**
 * SERVEUR BOUCHON — LOT 2 (adhesion automatique a l'achat).
 *
 * A QUOI IL SERT
 * --------------
 * Le vrai backend ne peut pas tourner sur cette machine (Python 3.9, FastAPI
 * absent, MONGO_URL obligatoire). Pour autant, on ne veut PAS se contenter de
 * relire le code source : un test qui lit du texte ne prouve pas qu'un ecran
 * s'affiche. Ce serveur sert donc le VRAI bundle React construit par craco, et
 * repond aux appels `/api/*` avec des fixtures ecrites a la main.
 *
 * CE QU'IL NE FAIT PAS, ET C'EST VOLONTAIRE
 * -----------------------------------------
 *   - il ne parle a AUCUNE base de donnees (pas une ligne de Mongo) ;
 *   - il REFUSE tout ce qui n'est pas un GET, avec un 405, et le consigne :
 *     un test qui declencherait une ecriture serait ainsi denonce, pas cache ;
 *   - il n'atteint aucun service externe, et le navigateur lui-meme coupe
 *     toute requete hors de cette origine (voir le test).
 *
 * Le contenu des reponses est PILOTE par l'objet `etat` que l'appelant modifie
 * entre deux scenarios : c'est lui qui fait la difference entre « aucune
 * adhesion », « adhesion active » et « adhesion expiree ».
 */
import http from 'http';
import fs from 'fs';
import path from 'path';

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.txt': 'text/plain; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
  '.webmanifest': 'application/manifest+json',
  '.md': 'text/markdown; charset=utf-8',
};

/** L'email coach utilise : « contacts » est un onglet reserve aux super-admins
 *  (ADMIN_ONLY_TAB_IDS, CoachDashboard.js). Un autre email masquerait l'ecran
 *  meme a tester. Cette valeur ne quitte jamais 127.0.0.1. */
export const EMAIL_COACH = 'afroboost.bassi@gmail.com';

/** Etat mutable : le test le reecrit entre deux scenarios. */
export function etatInitial() {
  return {
    // Statut HTTP renvoye par /api/contacts/all (200 par defaut, 403 pour le
    // scenario « acces refuse »).
    statutContacts: 200,
    contacts: [],
    compteurs: null,
    offers: [],
  };
}

function json(res, statut, corps) {
  const buf = Buffer.from(JSON.stringify(corps), 'utf8');
  res.writeHead(statut, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': buf.length,
    'Cache-Control': 'no-store',
  });
  res.end(buf);
}

/**
 * Les reponses `/api/*`. Chaque cle est un chemin EXACT (sans `/api`), chaque
 * valeur une fonction de l'etat. Ce qui n'est pas liste tombe sur le repli.
 */
function routes(etat) {
  return {
    // --- le coeur du LOT 2 -------------------------------------------------
    '/contacts/all': () => {
      if (etat.statutContacts !== 200) {
        return [etat.statutContacts, { detail: 'Acces refuse' }];
      }
      return [200, {
        success: true,
        contacts: etat.contacts,
        compteurs: etat.compteurs || {
          tous: etat.contacts.length, abonnes: 0, anciens: 0,
          prospects: 0, non_classes: etat.contacts.length,
        },
      }];
    },
    '/contact-categories': () => [200, { success: true, categories: [] }],
    '/google-contacts/status': () => [200, { connected: false, configured: false, last_sync: null }],

    // --- ce que la vitrine et le dashboard reclament au demarrage ----------
    '/offers': () => [200, etat.offers],
    '/courses': () => [200, []],
    // Liste NUE attendue : `setCourses(r.data)` puis `courses.reduce(...)` dans
    // la barre de sous-onglets de « Gestion ». Un objet y faisait planter la
    // page entiere.
    '/coach/courses': () => [200, []],
    '/coach/profile': () => [200, { success: true, profile: {} }],
    '/audio-tracks': () => [200, []],
    '/social-proofs': () => [200, []],
    '/private/nonlus': () => [200, { success: true, count: 0, conversations: [] }],
    '/whatsapp-config': () => [200, { success: true, configured: false }],
    '/auth/whoami': () => [200, { success: true, email: EMAIL_COACH, role: 'super_admin' }],
    '/partners/active': () => [200, []],
    '/users': () => [200, []],
    '/discount-codes': () => [200, []],
    '/payment-links': () => [200, []],
    '/publications': () => [200, []],
    '/concept': () => [200, {}],
    '/platform-settings': () => [200, { success: true, settings: {} }],
    '/feature-flags': () => [200, {}],
    '/page-likes': () => [200, { likes: 0, liked: false }],
    '/comments': () => [200, []],
    // Enveloppe {data, pagination} — et pas une liste nue : le dashboard fait
    // `setReservations(res.data.data)` puis `reservations.map(...)` dans un
    // useMemo. Une liste nue rendrait `reservations` undefined et ferait
    // PLANTER tout l'ecran avant meme d'atteindre l'onglet Contacts.
    '/reservations': () => [200, {
      success: true, data: [], pagination: { page: 1, limit: 20, total: 0, pages: 0 },
    }],
    '/chat/sessions': () => [200, { success: true, sessions: [] }],
    '/chat/groups': () => [200, { success: true, groups: [] }],
    '/trash': () => [200, { success: true, items: [] }],
    '/notifications/unread': () => [200, { success: true, count: 0 }],
    '/coach/notifications': () => [200, { success: true, notifications: [] }],
    '/dashboard/all-transactions': () => [200, { success: true, transactions: [] }],
    '/credit-transactions': () => [200, { success: true, transactions: [] }],
    // Sans cette reponse, App.js considere la session coach invalide et purge
    // le localStorage : le dashboard disparaitrait avant d'etre teste.
    '/auth/role': () => [200, {
      role: 'super_admin', is_coach: true, is_super_admin: true, email: EMAIL_COACH,
    }],
  };
}

/**
 * Repli pour toute route `/api/*` non listee. Volontairement generique : les
 * ecrans du depot sont defensifs (socle P0), un objet vide leur suffit. Aucune
 * donnee personnelle n'y figure — c'est important pour le scenario 403, ou l'on
 * verifie qu'aucune information d'abonne n'atteint le DOM.
 */
const REPLI = {
  success: true, data: [], items: [], results: [], count: 0, total: 0,
  offers: [], courses: [], contacts: [], sessions: [], messages: [],
  notifications: [], transactions: [], groups: [], categories: [], faqs: [],
  tracks: [], comments: [], publications: [],
};

export function demarrer({ racine, etat }) {
  const journal = [];

  const serveur = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://127.0.0.1');
    const chemin = decodeURIComponent(url.pathname);

    if (chemin.startsWith('/api/')) {
      // GARDE-FOU : aucune ecriture, jamais. Un POST/PUT/DELETE est refuse ET
      // consigne, de sorte que le test puisse affirmer « rien n'a ete ecrit »
      // sur une mesure, pas sur une intention.
      if (req.method !== 'GET') {
        journal.push({ methode: req.method, chemin, statut: 405 });
        return json(res, 405, { detail: 'Ecriture interdite dans le bouchon' });
      }
      const cle = chemin.replace(/^\/api/, '');
      const table = routes(etat);
      const fabrique = table[cle];
      const [statut, corps] = fabrique ? fabrique() : [200, REPLI];
      journal.push({ methode: 'GET', chemin, statut });
      return json(res, statut, corps);
    }

    // --- statique + repli SPA ---------------------------------------------
    let fichier = path.join(racine, chemin);
    if (!fichier.startsWith(racine)) fichier = path.join(racine, 'index.html');
    if (!fs.existsSync(fichier) || fs.statSync(fichier).isDirectory()) {
      fichier = path.join(racine, 'index.html');
    }
    const ext = path.extname(fichier).toLowerCase();
    const buf = fs.readFileSync(fichier);
    journal.push({ methode: req.method, chemin, statut: 200 });
    res.writeHead(200, {
      'Content-Type': TYPES[ext] || 'application/octet-stream',
      'Content-Length': buf.length,
      'Cache-Control': 'no-store',
    });
    res.end(buf);
  });

  return new Promise((resoudre) => {
    serveur.listen(0, '127.0.0.1', () => {
      const port = serveur.address().port;
      resoudre({
        port,
        base: `http://127.0.0.1:${port}`,
        journal,
        arreter: () => new Promise((r) => serveur.close(r)),
      });
    });
  });
}
