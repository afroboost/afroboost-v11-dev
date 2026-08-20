/**
 * LOT 3b — L'AVANTAGE TARIFAIRE MEMBRE : LES PREUVES EN NAVIGATEUR REEL.
 * =====================================================================
 *
 * POURQUOI CE TEST EXISTE
 * -----------------------
 * Lire le source ne prouve rien d'un ecran. Un `data-testid` present dans un
 * fichier peut etre rendu derriere une condition fausse, masque par un parent,
 * ou jamais atteint parce qu'aucun clic n'y mene. Ici on ouvre un VRAI
 * Chromium, on charge le VRAI bundle construit par craco, et on regarde ce qui
 * est reellement a l'ecran — cote coach ET cote client.
 *
 * CE QUI A CHANGE DEPUIS LA VERSION PRECEDENTE DE CE FICHIER
 * ----------------------------------------------------------
 * La version precedente devait construire DEUX bundles : le vrai, et une copie
 * hors depot ou deux lignes etaient remises dans leur position d'avant V225 —
 * sans quoi l'ecran portant la ligne « Avantage membre » n'etait atteignable
 * par AUCUN clic (defaut R6). Ce contournement est SUPPRIME. Le correctif de
 * joignabilite (drapeau `memberPricingEnabled` + predicat
 * `lot3bChoixDateRequis`) est desormais dans `frontend/src/App.js`, et TOUT ce
 * fichier mesure le bundle REEL, non modifie. Un seul bundle, aucune retouche.
 *
 * CE QUI EST SIMULE, ET CE QUI NE L'EST PAS
 * -----------------------------------------
 * SIMULE : le backend. Il ne peut pas tourner sur cette machine (Python 3.9,
 * FastAPI absent, MONGO_URL obligatoire). Les reponses `/api/*` viennent donc
 * d'un bouchon Node local, ecrit plus bas dans CE fichier. Ce test ne dit rien
 * de la REGLE serveur (qui est membre, quel pourcentage l'emporte, quelle
 * occurrence est refusee) : cette partie est couverte par les tests Python. Il
 * dit ce que l'interface FAIT d'une reponse donnee, et ce qu'elle ENVOIE —
 * c'est precisement ce qu'aucun test Python ne peut dire.
 * PAS SIMULE : le code frontend. Aucun composant n'est remplace, aucun module
 * n'est bouchonne, aucune ligne d'App.js n'est retouchee.
 *
 * DEUX VOIES DE CLIC, PAS UNE
 * ----------------------------
 * Une carte d'offre porte DEUX aiguillages : le bouton « Réserver »
 * (`v226BuyDirect`) et le corps de la carte (`handleSelectOffer`). Une premiere
 * mesure de ce test a trouve le bouton NON corrige alors que le corps l'etait —
 * l'ecran etait donc atteignable en laboratoire mais pas par le CTA que le
 * visiteur clique. Le volet R EXIGE desormais les deux, explicitement, au lieu
 * de constater laquelle des deux marche.
 *
 * LE DRAPEAU EST LE SUJET, PAS UN DECOR
 * -------------------------------------
 * Le bouchon sert `/api/feature-flags` avec `MEMBER_PRICING_ENABLED` pilote par
 * le scenario : `true` pour les parcours membres, `false` pour prouver que le
 * coupe-circuit rend EXACTEMENT le comportement d'avant (R5).
 *
 * CE QUE CE TEST NE TOUCHE JAMAIS
 * -------------------------------
 * Aucune production, aucune base, aucun paiement. Le bouchon n'autorise QU'UNE
 * ecriture : `POST /api/tarif/estimation`, qui est une route de LECTURE (elle
 * calcule un prix et n'enregistre rien) mais que le contrat HTTP du depot passe
 * en POST. Tout autre verbe non-GET est refuse en 405 ET consigne — corps
 * compris, ce qui permet de PROUVER ce que le navigateur voulait envoyer sans
 * que rien ne parte. Le navigateur coupe en outre toute requete sortant de
 * 127.0.0.1. Le `frontend/build` du depot n'est jamais ecrit (`BUILD_PATH`).
 *
 * LANCEMENT
 *   node tests/test_lot3b_navigateur.mjs                (construit si besoin)
 *   node tests/test_lot3b_navigateur.mjs --sans-build   (reutilise tel quel)
 */
import fs from 'fs';
import os from 'os';
import http from 'http';
import path from 'path';
import crypto from 'crypto';
import { execFileSync } from 'child_process';
import { fileURLToPath } from 'url';
import { createRequire } from 'module';

const require_ = createRequire(import.meta.url);
// Playwright n'est PAS une dependance du projet : on l'emprunte par chemin
// absolu, exactement comme les tests LOT 2 / LOT 2.1 / LOT 3a.
const CHEMIN_PLAYWRIGHT = '/Users/afroboost/.claude/skills/gstack/node_modules/playwright-core';
const { chromium } = require_(CHEMIN_PLAYWRIGHT);

const RACINE = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const TRAVAIL = path.join(os.tmpdir(), 'afroboost-lot3b-navigateur');
const BUILD = path.join(TRAVAIL, 'build');
const CAPTURES = path.join(TRAVAIL, 'captures');
const EMPREINTE = path.join(TRAVAIL, 'empreinte.txt');
const SANS_BUILD = process.argv.includes('--sans-build');

const EMAIL_COACH = 'afroboost.bassi@gmail.com';   // super-admin : ne quitte jamais 127.0.0.1

// ---------------------------------------------------------------------------
// 0. LE BUNDLE — un seul, le vrai.
// ---------------------------------------------------------------------------

/** Les fichiers dont depend ce que l'on mesure. Leur empreinte decide de la
 *  reconstruction : inutile de rebatir plusieurs minutes pour rien, hors de
 *  question de tester un bundle perime. */
const SOURCES = [
  'frontend/src/App.js',
  'frontend/src/components/CoachDashboard.js',
  'frontend/src/components/dashboard/OfferWizard.js',
  'frontend/src/components/dashboard/OffersManager.js',
  'frontend/src/components/SessionsModal.js',
];

function empreinteSources() {
  const h = crypto.createHash('sha256');
  for (const s of SOURCES) h.update(fs.readFileSync(path.join(RACINE, s)));
  return h.digest('hex');
}

/**
 * `BUILD_PATH` plutot que le `frontend/build` du depot : la sortie va dans
 * /tmp, et l'arbre de travail n'est JAMAIS touche — pas meme un artefact de
 * construction a restaurer ensuite.
 *
 * `REACT_APP_BACKEND_URL` VIDE, et c'est capital : `frontend/.env.local`
 * contient `https://afroboost.com`. Sans cette neutralisation, le bundle de
 * test enverrait ses appels A LA PRODUCTION. Une variable posee dans
 * l'environnement l'emporte sur les fichiers `.env` (dotenv n'ecrase jamais une
 * cle deja presente) : le fichier du depot n'est ni lu de travers ni modifie.
 * Le navigateur coupe en outre tout ce qui sort de 127.0.0.1 — ceinture ET
 * bretelles, et le scenario Z3 verifie qu'aucune bretelle n'a servi.
 */
function construire(cwd, sortie) {
  execFileSync('npx', ['craco', 'build'], {
    cwd,
    env: { ...process.env, CI: 'false', REACT_APP_BACKEND_URL: '', BUILD_PATH: sortie },
    stdio: 'inherit',
  });
}

function preparerBundle() {
  const attendue = empreinteSources();
  const connue = fs.existsSync(EMPREINTE) ? fs.readFileSync(EMPREINTE, 'utf8').trim() : '';
  if (fs.existsSync(path.join(BUILD, 'index.html')) && connue === attendue) {
    console.log('· bundle REEL deja a jour dans ' + TRAVAIL);
    return;
  }
  if (SANS_BUILD) {
    throw new Error('bundle absent ou perime, et --sans-build demande. Relancer sans l\'option.');
  }
  fs.mkdirSync(TRAVAIL, { recursive: true });
  console.log('· construction du bundle REEL (craco), quelques minutes…');
  fs.rmSync(BUILD, { recursive: true, force: true });
  construire(path.join(RACINE, 'frontend'), BUILD);
  fs.writeFileSync(EMPREINTE, attendue);
  console.log('· bundle pret. Le depot n\'a pas ete touche.');
}

// ---------------------------------------------------------------------------
// 1. LE BOUCHON — copie locale, volontairement NON partagee.
// ---------------------------------------------------------------------------
//
// `tests/serveur_bouchon_lot2.mjs` refuse TOUT verbe non-GET (405). C'est une
// bonne regle et on ne la relache pas la-bas : ce fichier en garde une copie
// avec UNE seule ouverture supplementaire, `POST /api/tarif/estimation`.
//
// Pourquoi cette exception est acceptable : la route est une route de LECTURE.
// Elle calcule « combien couterait cet achat » et n'ecrit rien (api/server.py,
// `lot3b_estimation_tarifaire`). Elle n'est en POST que parce qu'elle recoit un
// corps (offre, cours, liste de dates, code promo) trop long pour une URL.
//
// Tout le reste (POST/PUT/DELETE) reste refuse en 405 — mais le CORPS est lu et
// consigne avant le refus. C'est ce qui permet de prouver ce que le navigateur
// ENVOIE (format des occurrences, montant) sans qu'une seule ecriture aboutisse.

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

function etatInitial() {
  return {
    offers: [],
    courses: [],
    /** L'interrupteur LOT 3b, servi par `/api/feature-flags`. Chaque scenario le
     *  pose AVANT d'ouvrir sa page : le frontend le lit une fois au montage. */
    memberPricing: true,
    /** La reponse que `/api/tarif/estimation` renverra. `null` = 404, comme le
     *  vrai serveur pour une offre introuvable. */
    estimation: null,
    /** Les corps recus par `/api/tarif/estimation`, dans l'ordre. */
    demandes: [],
    /** Les corps des `POST /api/create-checkout-session` TENTES (tous refuses). */
    checkouts: [],
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

/** Le concept est RENVOYE ENTIER : `setConcept(conceptData)` REMPLACE l'objet
 *  (App.js ~l.5827), un objet partiel effacerait les valeurs par defaut.
 *  `paymentCreditCard: true` est indispensable : sans lui, la soumission du
 *  formulaire ne passe jamais par `POST /api/create-checkout-session`, et les
 *  preuves H/I/J/L n'auraient rien a observer. */
const CONCEPT = {
  appName: 'Afroboost', description: '', heroImageUrl: '', logoUrl: '', faviconUrl: '',
  termsText: '', googleReviewsUrl: '', defaultLandingSection: 'all',   // 'all' -> la BOUTIQUE est rendue elle aussi (R9)
  vitrineSectionOrder: 'sessions-first', externalLink1Title: '', externalLink1Url: '',
  externalLink2Title: '', externalLink2Url: '',
  paymentTwint: false, paymentPaypal: false, paymentCreditCard: true,
  eventPosterEnabled: false, eventPosterMediaUrl: '',
};

/** Reponses `/api/*`. Cle = chemin EXACT sans `/api`. */
function routes(etat) {
  return {
    '/offers': () => [200, etat.offers],
    '/courses': () => [200, etat.courses],
    // Liste NUE attendue par le dashboard (`setCourses(r.data)` puis `.reduce`).
    '/coach/courses': () => [200, etat.courses],
    '/concept': () => [200, CONCEPT],
    // LE DRAPEAU LOT 3b. C'est la MEME requete que le drapeau audio : le
    // correctif de joignabilite n'ajoute aucun appel reseau.
    '/feature-flags': () => [200, {
      AUDIO_SERVICE_ENABLED: false,
      MEMBER_PRICING_ENABLED: !!etat.memberPricing,
    }],
    '/pawapay/available': () => [200, { available: false, enabled: false, countries: [] }],
    '/contacts/all': () => [200, {
      success: true, contacts: [],
      compteurs: { tous: 0, abonnes: 0, anciens: 0, prospects: 0, non_classes: 0 },
    }],
    '/contact-categories': () => [200, { success: true, categories: [] }],
    '/google-contacts/status': () => [200, { connected: false, configured: false, last_sync: null }],
    '/coach/profile': () => [200, { success: true, profile: {} }],
    '/audio-tracks': () => [200, []],
    '/social-proofs': () => [200, []],
    '/private/nonlus': () => [200, { success: true, count: 0, conversations: [] }],
    '/whatsapp-config': () => [200, { success: true, configured: false }],
    '/auth/whoami': () => [200, { success: true, email: EMAIL_COACH, role: 'super_admin' }],
    '/partners/active': () => [200, []],
    '/users': () => [200, []],
    '/discount-codes': () => [200, []],
    '/payment-links': () => [200, {}],
    '/publications': () => [200, []],
    '/platform-settings': () => [200, { success: true, settings: {} }],
    '/page-likes': () => [200, { likes: 0, liked: false }],
    '/comments': () => [200, []],
    // Enveloppe {data, pagination} : une liste nue ferait PLANTER le dashboard.
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
    // Sans cette reponse, App.js purge la session coach et le dashboard
    // disparait avant d'avoir ete teste.
    '/auth/role': () => [200, {
      role: 'super_admin', is_coach: true, is_super_admin: true, email: EMAIL_COACH,
    }],
  };
}

const REPLI = {
  success: true, data: [], items: [], results: [], count: 0, total: 0,
  offers: [], courses: [], contacts: [], sessions: [], messages: [],
  notifications: [], transactions: [], groups: [], categories: [], faqs: [],
  tracks: [], comments: [], publications: [],
};

function demarrerBouchon({ racine, etat }) {
  const journal = [];

  const serveur = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://127.0.0.1');
    const chemin = decodeURIComponent(url.pathname);

    if (chemin.startsWith('/api/')) {
      if (req.method !== 'GET') {
        // On LIT le corps meme quand on refuse : c'est la preuve de ce que le
        // navigateur voulait envoyer. Rien n'est ecrit pour autant.
        let brut = '';
        req.on('data', (c) => { brut += c; });
        req.on('end', () => {
          let corps = {};
          try { corps = JSON.parse(brut || '{}'); } catch (e) { corps = {}; }

          // SEULE ouverture : l'estimation tarifaire (route de LECTURE en POST).
          if (req.method === 'POST' && chemin === '/api/tarif/estimation') {
            etat.demandes.push({ corps, t: Date.now() });
            journal.push({ methode: 'POST', chemin, statut: etat.estimation ? 200 : 404 });
            if (!etat.estimation) return json(res, 404, { detail: 'Offre introuvable' });
            return json(res, 200, etat.estimation);
          }

          if (chemin === '/api/create-checkout-session') {
            etat.checkouts.push({ corps, t: Date.now() });
          }
          // GARDE-FOU : aucune autre ecriture n'aboutit, jamais.
          journal.push({ methode: req.method, chemin, statut: 405, corps });
          return json(res, 405, { detail: 'Ecriture interdite dans le bouchon' });
        });
        return undefined;
      }
      const cle = chemin.replace(/^\/api/, '');
      const fabrique = routes(etat)[cle];
      const [statut, corps] = fabrique ? fabrique() : [200, REPLI];
      journal.push({ methode: 'GET', chemin, statut });
      return json(res, statut, corps);
    }

    let fichier = path.join(racine, chemin);
    if (!fichier.startsWith(racine)) fichier = path.join(racine, 'index.html');
    if (!fs.existsSync(fichier) || fs.statSync(fichier).isDirectory()) {
      fichier = path.join(racine, 'index.html');
    }
    const buf = fs.readFileSync(fichier);
    res.writeHead(200, {
      'Content-Type': TYPES[path.extname(fichier).toLowerCase()] || 'application/octet-stream',
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

// ---------------------------------------------------------------------------
// 2. LES FIXTURES
// ---------------------------------------------------------------------------

const COURS = {
  id: 'cours-lot3b', name: 'Cardio Afrobeat', weekday: 1, time: '18:30',
  locationName: 'Lausanne', maxCapacity: 20, reservations: 0,
  active: true, is_active: true, visible: true, price: 30,
  coach_id: EMAIL_COACH, audio_tracks: [], playlist: [],
};

/** L'offre du LOT 3b : payante, avantage membre reel, liee a un cours.
 *  C'est la SEULE forme d'offre que le correctif de joignabilite deroute. */
const OFFRE_30 = {
  id: 'offre-unite', name: "Cours à l'unité", title: "Cours à l'unité",
  description: 'Une séance', price: 30, currency: 'CHF', sessions: 1,
  active: true, is_active: true, visible: true,
  member_discount_pct: 50, linked_course_ids: [COURS.id],
  coach_id: EMAIL_COACH, images: [],
};

/** Offre PAYANTE mais SANS avantage membre : son parcours ne doit pas bouger
 *  d'un pixel, drapeau allume ou non (R6). */
const OFFRE_SANS_AVANTAGE = {
  id: 'offre-simple', name: 'Séance découverte', title: 'Séance découverte',
  description: 'Sans avantage membre', price: 40, currency: 'CHF', sessions: 1,
  active: true, is_active: true, visible: true,
  member_discount_pct: 0, linked_course_ids: [COURS.id],
  coach_id: EMAIL_COACH, images: [],
};

/** Avantage membre MAIS aucun cours lie : il n'y aurait aucune date a montrer,
 *  donc rien a deroute (R7). */
const OFFRE_AVANTAGE_SANS_COURS = {
  id: 'offre-orpheline', name: 'Bon cadeau membre', title: 'Bon cadeau membre',
  description: 'Avantage sans cours lié', price: 35, currency: 'CHF', sessions: 1,
  active: true, is_active: true, visible: true,
  member_discount_pct: 50, linked_course_ids: [],
  coach_id: EMAIL_COACH, images: [],
};

/** Offre GRATUITE : parcours historique (formulaire, sans grille) — R8. */
const OFFRE_GRATUITE = {
  id: 'offre-gratuite', name: 'Premier cours offert', title: 'Premier cours offert',
  description: 'Gratuit', price: 0, currency: 'CHF', sessions: 1,
  active: true, is_active: true, visible: true,
  member_discount_pct: 0, linked_course_ids: [COURS.id],
  coach_id: EMAIL_COACH, images: [],
};

/** PULSE 250 : l'offre d'entree. Elle OUVRE l'adhesion, donc elle ne doit
 *  jamais etre vendue au tarif membre (on n'achete pas son adhesion a moitie
 *  prix). Le serveur le sait ; l'ecran doit le refleter — scenario L. */
const OFFRE_PULSE = {
  id: 'offre-pulse', name: 'PULSE x10 cours', title: 'PULSE x10 cours',
  description: 'Dix séances', price: 250, currency: 'CHF', sessions: 10,
  active: true, is_active: true, visible: true,
  creates_membership: true, member_discount_pct: 0, linked_course_ids: [COURS.id],
  coach_id: EMAIL_COACH, images: [],
};

/** Un cours MASQUE (`visible: false`). Il existe en base, il est renvoye par
 *  /api/courses, mais il n'est plus affichable. C'est la CINQUIEME condition du
 *  predicat : une offre dont tous les horaires sont masques ne doit PAS ouvrir
 *  une grille vide — le visiteur ne pourrait plus acheter du tout. */
const COURS_MASQUE = {
  id: 'cours-masque', name: 'Cours retire', weekday: 3, time: '19:00',
  locationName: 'Lausanne', maxCapacity: 20, reservations: 0,
  active: true, is_active: true, visible: false, archived: false, price: 30,
  coach_id: EMAIL_COACH, audio_tracks: [], playlist: [],
};

/** Avantage membre, cours lie... mais ce cours est MASQUE (R7ter). */
const OFFRE_COURS_MASQUE = {
  id: 'offre-cours-masque', name: 'Seance horaire retire', title: 'Seance horaire retire',
  description: 'Avantage membre, mais tous les horaires sont masques',
  price: 30, currency: 'CHF', sessions: 1,
  active: true, is_active: true, visible: true,
  member_discount_pct: 50, linked_course_ids: [COURS_MASQUE.id],
  coach_id: EMAIL_COACH, images: [],
};

/** LE CAS DUR DE LA BOUTIQUE (R9). Ce produit physique remplit TOUTES les
 *  conditions du predicat (payant, avantage 50 %, cours lie et affichable) :
 *  si la prop `lot3bChoixDateRequis` fuitait jusqu'au carrousel des produits,
 *  son bouton cesserait de partir en achat direct. Un produit ordinaire, lui,
 *  passerait ce test meme si le relais etait mal cable — il ne prouverait rien.
 *  (Le formulaire coach interdit deja ce reglage sur un produit : W12.) */
const OFFRE_BOUTIQUE = {
  id: 'produit-tshirt', name: 'T-shirt Afroboost', title: 'T-shirt Afroboost',
  description: 'Produit physique', price: 45, currency: 'CHF',
  active: true, is_active: true, visible: true,
  isProduct: true, isPhysicalProduct: true,
  member_discount_pct: 50, linked_course_ids: [COURS.id],
  coach_id: EMAIL_COACH, images: [],
};

/** Le squelette commun de toutes les reponses de `/api/tarif/estimation`,
 *  copie sur la forme REELLE produite par api/server.py. */
const estimation = (extra) => ({
  offer_id: OFFRE_30.id, quantity: 1, devise: 'CHF',
  prix_public_unitaire: 30, prix_public: 30, votre_tarif: 30,
  membre: false, avantage_pct: null, raison: 'public',
  ...extra,
});

/** LA MEME arithmetique que `getNextOccurrences` (App.js ~l.821), refaite ici
 *  pour pouvoir COMPARER ce que le navigateur envoie a ce qu'il devait
 *  envoyer. Si les deux divergent, le test le dit. */
function occurrencesAttendues(weekday, heure, combien = 4) {
  const now = new Date();
  const diffBrut = weekday - now.getDay();
  const diff = diffBrut < 0 ? diffBrut + 7 : diffBrut;
  const [h, m] = heure.split(':');
  const pad = (n) => String(n).padStart(2, '0');
  const out = [];
  const courant = new Date(now.getFullYear(), now.getMonth(), now.getDate() + diff);
  for (let i = 0; i < combien; i += 1) {
    const d = new Date(courant);
    out.push({
      naif: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
        + `T${pad(parseInt(h, 10))}:${pad(parseInt(m, 10))}:00`,
      jour: pad(d.getDate()),
      mois: pad(d.getMonth() + 1),
    });
    courant.setDate(courant.getDate() + 7);
  }
  return out;
}

const OCCURRENCES = occurrencesAttendues(COURS.weekday, COURS.time);

// ---------------------------------------------------------------------------
// 3. RESULTATS
// ---------------------------------------------------------------------------

const resultats = [];
const bloqueesGlobal = [];
const erreursPage = [];
/** Chaque clic sur un bouton de date = UN changement de selection = UNE
 *  estimation attendue. Ce compteur est la reference du controle anti-boucle
 *  Z4 : il est incremente par le seul helper qui clique une date. */
let gestesSelection = 0;

function verifier(nom, condition, detail = '') {
  const ok = !!condition;
  resultats.push({ nom, ok, detail: ok ? '' : String(detail || '') });
  console.log(`${ok ? '  OK   ' : ' ECHEC '} ${nom}${ok || !detail ? '' : ` — ${detail}`}`);
}
function nonCouvert(nom, pourquoi) {
  resultats.push({ nom, ok: null, detail: pourquoi });
  console.log(`  N.C.  ${nom}`);
}
function noter(nom, valeur) {
  resultats.push({ nom, ok: null, detail: String(valeur) });
  console.log(`  info  ${nom} — ${valeur}`);
}

// ---------------------------------------------------------------------------
// 4. PILOTAGE DU NAVIGATEUR
// ---------------------------------------------------------------------------

/** JWT NON SIGNE mais de forme valide, `exp` lointain. Le frontend ne verifie
 *  que `exp` (utils/jwt.js : la signature ne peut pas etre verifiee dans un
 *  navigateur). Aucune garde serveur n'est franchie : le serveur est ici un
 *  bouchon local qui ne protege rien. */
function jetonFactice(email) {
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
  const exp = Math.floor(Date.now() / 1000) + 3600 * 24 * 30;
  return `${b64({ alg: 'HS256', typ: 'JWT' })}.${b64({ email, sub: email, exp })}.signature-factice`;
}

/**
 * @param connecte false = simple VISITEUR. Indispensable pour la vitrine :
 *   avec une session coach, App.js rend le dashboard a la place de la page
 *   publique et l'offre n'est jamais a l'ecran.
 */
async function nouveauContexte(navigateur, base, largeur, hauteur, connecte, etiquette) {
  const contexte = await navigateur.newContext({
    viewport: { width: largeur, height: hauteur }, baseURL: base,
  });
  const hote = new URL(base).host;
  // AUCUNE sortie hors de 127.0.0.1 : ni PostHog, ni Cloudinary, ni la prod.
  await contexte.route('**/*', (route) => {
    const u = new URL(route.request().url());
    if (u.host !== hote) { bloqueesGlobal.push(u.href); return route.abort(); }
    // Le Service Worker servirait un bundle cache : on le coupe net.
    if (u.pathname === '/sw.js') return route.abort();
    return route.continue();
  });
  if (connecte) {
    await contexte.addInitScript(([email, jeton]) => {
      localStorage.setItem('afroboost_coach_mode', 'true');
      localStorage.setItem('afroboost_coach_user', JSON.stringify({ email, name: 'Coach Test' }));
      localStorage.setItem('afroboost_jwt', jeton);
    }, [EMAIL_COACH, jetonFactice(EMAIL_COACH)]);
  }
  const page = await contexte.newPage();
  page.on('pageerror', (e) => erreursPage.push(`${etiquette}: ${e.message}`));
  return { contexte, page };
}

async function capture(page, nom) {
  fs.mkdirSync(CAPTURES, { recursive: true });
  await page.screenshot({ path: path.join(CAPTURES, `${nom}.png`), fullPage: false });
}

/** Ouvre le formulaire d'une NOUVELLE offre, etape 1 « Bases ». */
async function ouvrirNouvelleOffre(page, base) {
  await page.goto(`${base}/#partner-dashboard`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('[data-testid="coach-nav-toggle"]', { timeout: 40000 });
  await page.click('[data-testid="coach-nav-toggle"]');
  await page.click('[data-testid="coach-tab-offers"]');
  await page.click('text=Offres & Cours');
  await page.waitForSelector('text=+ NOUVELLE OFFRE', { timeout: 30000 });
  await page.click('text=+ NOUVELLE OFFRE');
  // TEMOIN DE MONTAGE : le champ « Nom », surtout pas le prix — un prix
  // affiche « 0 » est une valeur NON VIDE et sortirait la boucle sur un
  // formulaire encore vierge (defaut deja rencontre au LOT 2.1).
  await page.waitForSelector('[placeholder="Ex: Cours à l\'unité"]', { timeout: 20000 });
  return page.getByPlaceholder('30').first();
}

/** Le montant lu dans la ligne « Total » du recapitulatif. */
async function totalAffiche(page) {
  const t = await page.locator('[data-testid="total-price"]').innerText();
  const m = t.match(/CHF\s*([\d]+[.,]?[\d]*)/);
  return m ? m[1].replace(',', '.') : null;
}

/**
 * LE GESTE DU VISITEUR : ouvrir la vitrine, puis agir sur la carte d'offre.
 * @param voie 'bouton' = le bouton « Réserver » (le CTA principal, celui que
 *   le proprietaire designe) ; 'carte' = le corps de la carte.
 */
async function ouvrirOffre(page, base, idOffre, voie) {
  await page.goto(`${base}/`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector(`[data-testid="offer-card-${idOffre}"]`, { timeout: 40000 });
  if (voie === 'bouton') {
    await page.click(`[data-testid="offer-reserve-${idOffre}"]`);
  } else {
    // Coin haut-gauche : on vise le corps de la carte, pas un enfant qui
    // arrete la propagation (pastilles d'images, lien partenaire).
    await page.locator(`[data-testid="offer-card-${idOffre}"]`)
      .click({ position: { x: 6, y: 6 } });
  }
  await page.waitForTimeout(2500);
}

/** Etat OBSERVABLE de la vitrine apres le clic. */
async function etatEcran(page) {
  return {
    dates: await page.locator('[data-testid^="date-btn-"]').count(),
    formulaire: await page.locator('[data-testid="user-info-section"]').count(),
  };
}

/**
 * Clique un bouton de date et attend le recapitulatif. C'est CE geste qui
 * declenche l'estimation ; on laisse volontairement 4 s pour qu'une eventuelle
 * boucle d'appels se manifeste (mesure : ~2,5 appels/s lors d'un essai rate).
 * @returns le nombre d'appels a /api/tarif/estimation provoques par ce geste.
 */
async function choisirDate(page, etat, indexDate = 0, attendreTotal = true) {
  const avant = etat.demandes.length;
  gestesSelection += 1;
  await page.click(`[data-testid="date-btn-${COURS.id}-${indexDate}"]`);
  if (attendreTotal) {
    await page.waitForSelector('[data-testid="total-price"]', { timeout: 20000 });
  }
  await page.waitForTimeout(4000);
  return etat.demandes.length - avant;
}

/** La ligne « Prix public » barree, qui n'a pas de data-testid : on la lit par
 *  sa position (frere precedent de la ligne d'avantage) et on VERIFIE que le
 *  navigateur la barre reellement (style calcule, pas attribut). */
async function lignePrixPublic(page) {
  return page.evaluate(() => {
    const l = document.querySelector('[data-testid="member-advantage-line"]');
    if (!l) return null;
    const p = l.previousElementSibling;
    if (!p) return null;
    const spans = p.querySelectorAll('span');
    const dernier = spans[spans.length - 1];
    return {
      texte: (p.innerText || '').replace(/\s+/g, ' ').trim(),
      decoration: dernier ? getComputedStyle(dernier).textDecorationLine : '',
    };
  });
}

/** Remplit le formulaire client et le soumet. Le POST partira vers le bouchon,
 *  qui le REFUSE en 405 apres avoir consigne son corps : rien n'est ecrit, mais
 *  on sait exactement ce que le navigateur voulait envoyer. */
async function soumettreFormulaire(page) {
  await page.fill('[data-testid="user-name-input"]', 'Test Visiteur');
  await page.fill('[data-testid="user-email-input"]', 'visiteur@example.invalid');
  await page.fill('[data-testid="user-whatsapp-input"]', '+41760000000');
  await page.fill('[data-testid="user-birthday-input"]', '1990-05-14');
  const cases = page.locator('[data-testid="user-info-section"] input[type="checkbox"]');
  const n = await cases.count();
  for (let i = 0; i < n; i += 1) {
    const c = cases.nth(i);
    if (await c.isVisible() && !(await c.isChecked())) await c.check().catch(() => {});
  }
  await page.click('[data-testid="submit-reservation-btn"]');
  await page.waitForTimeout(2500);
}

// ---------------------------------------------------------------------------
// 5. LES SCENARIOS
// ---------------------------------------------------------------------------

/** La voie qui MENE REELLEMENT au formulaire pour une offre a avantage membre.
 *  Elle est MESUREE par le volet R, pas supposee. */
let VOIE_UTILE = null;

async function principal() {
  preparerBundle();

  const etat = etatInitial();
  etat.offers = [OFFRE_30, OFFRE_SANS_AVANTAGE, OFFRE_AVANTAGE_SANS_COURS,
    OFFRE_GRATUITE, OFFRE_PULSE, OFFRE_COURS_MASQUE, OFFRE_BOUTIQUE];
  etat.courses = [COURS, COURS_MASQUE];

  const navigateur = await chromium.launch({ headless: true });
  const srv = await demarrerBouchon({ racine: BUILD, etat });

  try {
    // =====================================================================
    // W — COTE COACH : le reglage, sur le VRAI bundle.
    // =====================================================================
    {
      etat.memberPricing = true;
      const { contexte, page } = await nouveauContexte(navigateur, srv.base, 1280, 1000, true, 'coach');
      const champPrix = await ouvrirNouvelleOffre(page, srv.base);
      const champ = page.locator('[data-testid="offer-member-discount-pct"]');

      // --- W1 : une offre NEUVE nait a 0 CHF -> aucun avantage a regler ---
      verifier('W1 sur une offre gratuite (0 CHF), le champ « Avantage membre » est ABSENT',
        (await champ.count()) === 0,
        'le champ est rendu alors qu\'il n\'y a rien a reduire');
      await capture(page, 'w1-offre-gratuite-champ-absent');

      // --- W2 : le coach donne un prix -> le champ apparait ---------------
      await champPrix.fill('30');
      await page.waitForTimeout(400);
      const present = (await champ.count()) === 1 && await champ.isVisible();
      verifier('W2 des qu\'un prix est saisi, le champ apparait et est visible', present,
        'aucun [data-testid="offer-member-discount-pct"] visible a 30 CHF');

      if (!present) {
        verifier('W3 le champ est place JUSTE SOUS le prix', false, 'champ absent');
        verifier('W4 son libelle annonce « Avantage membre (%) »', false, 'champ absent');
        verifier('W5 il vaut AUCUN AVANTAGE par defaut', false, 'champ absent');
      } else {
        // Position REELLE dans le DOM, pas dans le source : on compte les
        // controles de saisie entre le prix et l'avantage. Zero = « juste
        // sous ». C'est la seule facon de prouver un placement.
        const pos = await page.evaluate(() => {
          const champs = [...document.querySelectorAll(
            '[data-testid="offer-wizard"] input, input, select, textarea')];
          const av = document.querySelector('[data-testid="offer-member-discount-pct"]');
          const prix = champs.find((e) => e.getAttribute('placeholder') === '30');
          return { i: champs.indexOf(av), p: champs.indexOf(prix) };
        });
        verifier('W3 le champ est place JUSTE SOUS le prix (aucune saisie entre les deux)',
          pos.p >= 0 && pos.i === pos.p + 1, `prix=#${pos.p} avantage=#${pos.i}`);
        const libelle = await page.evaluate(() => {
          const av = document.querySelector('[data-testid="offer-member-discount-pct"]');
          const l = av.parentElement.querySelector('label');
          return l ? l.textContent.trim() : '';
        });
        verifier('W4 son libelle annonce « Avantage membre (%) »',
          /Avantage membre \(%\)/i.test(libelle), `lu : « ${libelle} »`);
        // « Vide ou 0 = AUCUN avantage », dit le code, et le formulaire d'une
        // offre neuve nait bien a 0 (CoachDashboard.js, `member_discount_pct: 0`).
        const parDefaut = await champ.inputValue();
        verifier('W5 il vaut AUCUN AVANTAGE par defaut (aucune offre ne devient reduite seule)',
          parDefaut === '' || parseFloat(parDefaut) === 0, `lu : « ${parDefaut} »`);
        noter('W5b valeur affichee par defaut dans le champ',
          parDefaut === '' ? 'champ vide' : `« ${parDefaut} »`);
      }
      await capture(page, 'w2-champ-visible-a-30chf');

      // --- W6 : l'apercu du tarif membre ---------------------------------
      await champ.fill('50');
      await page.waitForTimeout(400);
      const texteBloc = await page.evaluate(() => {
        const av = document.querySelector('[data-testid="offer-member-discount-pct"]');
        return av ? (av.parentElement.innerText || '').replace(/\s+/g, ' ') : '';
      });
      verifier('W6 50 % sur une offre a 30 CHF affiche « Tarif membre : CHF 15.00 »',
        /Tarif membre\s*:\s*CHF\s*15\.00/i.test(texteBloc), `lu : « ${texteBloc.slice(0, 200)} »`);
      await capture(page, 'w6-apercu-tarif-membre');

      // --- W7 : PULSE 250 — la case « ouvre une adhesion » verrouille -----
      const caseAdhesion = page.locator('[data-testid="offer-creates-membership"]');
      await caseAdhesion.check();
      await page.waitForTimeout(400);
      verifier('W7 case « ouvre une adhesion d\'un an » cochee -> le champ est DESACTIVE',
        (await champ.isDisabled()) === true,
        'on pourrait acheter son adhesion au tarif membre (protection PULSE 250 absente)');
      const explication = await page.evaluate(() => {
        const av = document.querySelector('[data-testid="offer-member-discount-pct"]');
        return av ? (av.parentElement.innerText || '').replace(/\s+/g, ' ') : '';
      });
      verifier('W8 ... et le coach lit POURQUOI (message explicatif affiche)',
        /Indisponible/i.test(explication) && /adh[ée]sion/i.test(explication),
        `lu : « ${explication.slice(0, 200)} »`);
      verifier('W9 ... et l\'apercu du tarif membre disparait (il serait mensonger)',
        !/Tarif membre\s*:/i.test(explication));
      await capture(page, 'w7-verrou-adhesion');

      await caseAdhesion.uncheck();
      await page.waitForTimeout(400);
      verifier('W10 case decochee -> le champ redevient utilisable',
        (await champ.isDisabled()) === false);
      verifier('W11 ... et le reglage du coach n\'a PAS ete efface en chemin',
        (await champ.inputValue()) === '50', `lu : « ${await champ.inputValue()} »`);

      // --- W12 : produit physique — rien a reduire ------------------------
      await page.click('text=(2) Logistique');
      const caseProduit = page.locator('label', { hasText: 'Produit physique' })
        .locator('input[type="checkbox"]').first();
      await caseProduit.check();
      await page.click('text=(1) Bases');
      await page.waitForTimeout(400);
      verifier('W12 sur un produit physique, le champ « Avantage membre » est ABSENT',
        (await champ.count()) === 0,
        'le champ est propose sur un produit alors que l\'avantage ne vise que les seances');
      await capture(page, 'w12-produit-physique');

      // --- W13 : le prix retombe a 0 -> le champ disparait ---------------
      await page.click('text=(2) Logistique');
      await caseProduit.uncheck();
      await page.click('text=(1) Bases');
      await page.waitForTimeout(300);
      await champPrix.fill('0');
      await page.waitForTimeout(400);
      verifier('W13 prix ramene a 0 -> le champ disparait a nouveau',
        (await champ.count()) === 0);

      await contexte.close();
    }

    // --- W14 : aucune couleur codee en dur (lecture du SOURCE) -----------
    {
      const blocs = [
        {
          nom: 'OfferWizard.js (bloc coach)',
          source: fs.readFileSync(
            path.join(RACINE, 'frontend/src/components/dashboard/OfferWizard.js'), 'utf8'),
          debut: 'LOT 3b — AVANTAGE MEMBRE',
          fin: 'V260: prix alternatif',
        },
        {
          nom: 'App.js (bloc client)',
          source: fs.readFileSync(path.join(RACINE, 'frontend/src/App.js'), 'utf8'),
          debut: "LOT 3b — L'AVANTAGE MEMBRE, EN DEUX LIGNES",
          fin: '{appliedDiscount && (',
        },
      ];
      for (const b of blocs) {
        const i = b.source.indexOf(b.debut);
        const j = b.source.indexOf(b.fin, i);
        if (i < 0 || j < 0) {
          verifier(`W14 ${b.nom} : le bloc LOT 3b est localisable dans le source`, false,
            'reperes introuvables — le fichier a change, ce controle doit etre relu');
          continue;
        }
        const bloc = b.source.slice(i, j);
        // On retire d'abord toutes les valeurs de SECOURS legitimes
        // (`var(--x, #hex)`), puis on regarde s'il reste un hex. S'il en reste
        // un, c'est une couleur imposee — exactement ce que la regle interdit.
        const restant = bloc.replace(/var\(\s*--[a-z0-9-]+\s*,\s*#[0-9a-fA-F]{3,8}\s*\)/g, '');
        const durs = restant.match(/#[0-9a-fA-F]{6}\b/g) || [];
        verifier(`W14 ${b.nom} : aucune couleur magenta codee en dur`,
          durs.length === 0, `hex hors var() : ${durs.join(', ')}`);
        verifier(`W15 ${b.nom} : la couleur de marque passe bien par var(--primary-color, …)`,
          /var\(\s*--primary-color/.test(bloc) || /\bPINK\b/.test(bloc),
          'aucune reference a --primary-color ni a la constante PINK');
      }
    }

    // =====================================================================
    // R — JOIGNABILITE. Le defaut a refermer, sur le bundle REEL.
    // =====================================================================

    // --- R1 : drapeau ON, offre a avantage membre, LES DEUX VOIES DE CLIC -
    //
    // Une carte d'offre porte DEUX aiguillages distincts : le bouton
    // « Réserver » (App.js ~l.2913, via `v226BuyDirect`) et le corps de la
    // carte (App.js ~l.2229, qui delegue a `handleSelectOffer`). Les mesurer
    // separement n'est pas un luxe : la version precedente de ce test a
    // justement trouve le bouton non corrige alors que le corps l'etait. On
    // EXIGE desormais les deux, on ne se contente plus de constater laquelle
    // des deux marche.
    const voies = {};
    for (const voie of ['bouton', 'carte']) {
      etat.memberPricing = true;
      etat.estimation = estimation({ membre: true, raison: 'membre', avantage_pct: 50, votre_tarif: 15 });
      const cAvant = etat.checkouts.length;
      const eAvant = etat.demandes.length;
      const { contexte, page } = await nouveauContexte(
        navigateur, srv.base, 1280, 1100, false, `R1-${voie}`);
      await ouvrirOffre(page, srv.base, OFFRE_30.id, voie);
      const vu = await etatEcran(page);
      voies[voie] = {
        dates: vu.dates,
        checkouts: etat.checkouts.length - cAvant,
        estimations: etat.demandes.length - eAvant,
      };
      await capture(page, `r1-${voie}-drapeau-on`);
      await contexte.close();
    }

    verifier('R1.1 drapeau ON + offre a avantage membre : le clic « Réserver » '
      + 'ne declenche AUCUN POST /api/create-checkout-session',
      voies.bouton.checkouts === 0,
      `${voies.bouton.checkouts} tentative(s) de paiement direct declenchee(s) par le bouton`);
    verifier('R1.2 ... et la grille d\'horaires APPARAIT apres ce clic « Réserver »',
      voies.bouton.dates > 0, `${voies.bouton.dates} bouton(s) de date rendu(s)`);
    verifier('R1.3 le clic sur le CORPS de la carte ne declenche pas non plus de paiement direct',
      voies.carte.checkouts === 0, `${voies.carte.checkouts} tentative(s)`);
    verifier('R1.4 ... et il ouvre lui aussi la grille d\'horaires',
      voies.carte.dates > 0, `${voies.carte.dates} bouton(s) de date rendu(s)`);
    verifier('R1.5 LES DEUX voies de clic mènent au meme endroit — aucune asymetrie '
      + 'entre le bouton et le corps de la carte',
      voies.bouton.dates > 0 && voies.carte.dates > 0
      && voies.bouton.checkouts === 0 && voies.carte.checkouts === 0,
      `bouton=${JSON.stringify(voies.bouton)} carte=${JSON.stringify(voies.carte)}`);
    verifier('R1.6 aucune estimation n\'est demandee tant qu\'aucune date n\'est choisie',
      voies.bouton.estimations === 0 && voies.carte.estimations === 0,
      `bouton=${voies.bouton.estimations} carte=${voies.carte.estimations}`);

    // La suite (R2-R4, scenarios A-L, desktop/mobile) se joue sur le CTA
    // principal des qu'il fonctionne ; le corps de carte ne sert de repli que
    // si le bouton echoue, pour que le reste du test dise quand meme quelque
    // chose au lieu de s'arreter net.
    if (voies.bouton.dates > 0) VOIE_UTILE = 'bouton';
    else if (voies.carte.dates > 0) VOIE_UTILE = 'carte';

    if (!VOIE_UTILE) {
      verifier('R2 choisir un cours puis une date ouvre le formulaire de reservation', false,
        'aucune des deux voies (bouton « Réserver », corps de carte) n\'affiche la grille : '
        + 'l\'ecran reste inatteignable');
      verifier('R3 une estimation /api/tarif/estimation est reellement demandee', false,
        'grille inatteignable');
      verifier('R4 le bloc « Prix public / Avantage membre / Total » est VISIBLE a l\'ecran', false,
        'grille inatteignable');
    } else {
      noter('R-voie voie de clic utilisee pour la suite du test',
        VOIE_UTILE === 'bouton'
          ? 'le bouton « Réserver » (le CTA principal) — les deux voies fonctionnent'
          : 'le CORPS de la carte, EN REPLI : le bouton « Réserver » ne mene pas au formulaire');

      // --- R2 / R3 / R4 : la selection, l'appel, l'affichage -------------
      etat.memberPricing = true;
      etat.estimation = estimation({
        membre: true, raison: 'membre', avantage_pct: 50, prix_public: 30, votre_tarif: 15,
      });
      const { contexte, page } = await nouveauContexte(navigateur, srv.base, 1280, 1100, false, 'R2-R4');
      await ouvrirOffre(page, srv.base, OFFRE_30.id, VOIE_UTILE);
      // Le cours et la date se posent d'un seul geste : le bouton de date porte
      // les deux (App.js ~l.6958). C'est la selection reelle du visiteur.
      const appels = await choisirDate(page, etat, 0);
      const formulaire = await page.locator('[data-testid="user-info-section"]').count();
      verifier('R2 choisir un cours puis une date remplit la selection ET ouvre le formulaire',
        formulaire === 1, `${formulaire} formulaire(s) ouvert(s)`);
      // La selection est VISIBLE : la carte du cours porte la classe `.selected`
      // (App.js ~l.8330), ce qui prouve que `selectedCourse` a bien ete pose.
      const coursSelectionne = await page
        .locator(`[data-testid="course-card-${COURS.id}"].selected`).count();
      verifier('R2b ... et le cours choisi est visuellement marque comme retenu',
        coursSelectionne === 1, `${coursSelectionne} carte(s) .selected`);
      verifier('R3 une estimation /api/tarif/estimation est REELLEMENT demandee',
        appels === 1, `${appels} appel(s) pour une selection`);

      const ligne = await page.locator('[data-testid="member-advantage-line"]');
      const ligneVisible = (await ligne.count()) === 1 && await ligne.isVisible();
      const pub = await lignePrixPublic(page);
      const total = await totalAffiche(page);
      verifier('R4.1 la ligne « Avantage membre » est a l\'ecran ET visible', ligneVisible);
      verifier('R4.2 la ligne « Prix public » barree est juste au-dessus',
        !!pub && /Prix public/i.test(pub.texte) && /30\.00/.test(pub.texte)
        && /line-through/.test(pub.decoration),
        pub ? `texte « ${pub.texte} » / decoration « ${pub.decoration} »` : 'ligne absente');
      verifier('R4.3 le Total affiche le tarif membre 15.00', total === '15.00', `lu : ${total}`);
      await capture(page, 'r4-bloc-avantage-membre-bundle-reel');
      await contexte.close();
    }

    // --- R5 : LE COUPE-CIRCUIT. Drapeau OFF -> comportement d'AVANT ------
    // Mesure sur LES DEUX voies de clic : le relais de prop ne doit rien
    // changer quand le drapeau est eteint, ni au bouton ni au corps de carte.
    {
      const off = {};
      for (const voie of ['bouton', 'carte']) {
        etat.memberPricing = false;
        etat.estimation = estimation({ membre: true, raison: 'membre', avantage_pct: 50, votre_tarif: 15 });
        const cAvant = etat.checkouts.length;
        const eAvant = etat.demandes.length;
        const { contexte, page } = await nouveauContexte(
          navigateur, srv.base, 1280, 1100, false, `R5-off-${voie}`);
        await ouvrirOffre(page, srv.base, OFFRE_30.id, voie);
        const vu = await etatEcran(page);
        off[voie] = {
          dates: vu.dates, formulaire: vu.formulaire,
          checkouts: etat.checkouts.length - cAvant,
          estimations: etat.demandes.length - eAvant,
        };
        if (voie === 'bouton') await capture(page, 'r5-drapeau-off-achat-direct');
        await contexte.close();
      }
      for (const voie of ['bouton', 'carte']) {
        const o = off[voie];
        verifier(`R5.${voie === 'bouton' ? 'a' : 'b'}1 drapeau OFF (${voie}) : AUCUNE grille d'horaires`,
          o.dates === 0, `${o.dates} bouton(s) de date — le coupe-circuit ne coupe rien`);
        verifier(`R5.${voie === 'bouton' ? 'a' : 'b'}2 drapeau OFF (${voie}) : achat DIRECT `
          + '(tentative de session Stripe mesuree, refusee 405 par le bouchon)',
          o.checkouts === 1, `${o.checkouts} tentative(s) POST /api/create-checkout-session`);
        verifier(`R5.${voie === 'bouton' ? 'a' : 'b'}3 drapeau OFF (${voie}) : AUCUNE estimation demandee`,
          o.estimations === 0, `${o.estimations} appel(s)`);
        verifier(`R5.${voie === 'bouton' ? 'a' : 'b'}4 drapeau OFF (${voie}) : aucun formulaire ouvert`,
          o.formulaire === 0, `${o.formulaire} formulaire(s)`);
      }
      verifier('R5.5 drapeau OFF : les deux voies se comportent A L\'IDENTIQUE',
        JSON.stringify(off.bouton) === JSON.stringify(off.carte),
        `bouton=${JSON.stringify(off.bouton)} carte=${JSON.stringify(off.carte)}`);
    }

    // --- R6 : offre PAYANTE SANS avantage membre, drapeau ON -------------
    {
      etat.memberPricing = true;
      const cAvant = etat.checkouts.length;
      const eAvant = etat.demandes.length;
      const { contexte, page } = await nouveauContexte(navigateur, srv.base, 1280, 1100, false, 'R6');
      await ouvrirOffre(page, srv.base, OFFRE_SANS_AVANTAGE.id, 'bouton');
      const vu = await etatEcran(page);
      const checkouts = etat.checkouts.length - cAvant;
      verifier('R6.1 offre payante SANS avantage membre, drapeau ON : le bouton « Réserver » '
        + 'part TOUJOURS en achat direct (le relais de prop ne casse rien)',
        checkouts === 1, `${checkouts} tentative(s) de checkout`);
      verifier('R6.2 ... et aucune grille d\'horaires', vu.dates === 0, `${vu.dates} bouton(s)`);
      verifier('R6.3 ... et aucune estimation',
        etat.demandes.length - eAvant === 0, `${etat.demandes.length - eAvant} appel(s)`);
      await capture(page, 'r6-offre-sans-avantage');
      await contexte.close();
    }

    // --- R7 : avantage membre MAIS aucun cours lie -----------------------
    {
      etat.memberPricing = true;
      const cAvant = etat.checkouts.length;
      const { contexte, page } = await nouveauContexte(navigateur, srv.base, 1280, 1100, false, 'R7');
      await ouvrirOffre(page, srv.base, OFFRE_AVANTAGE_SANS_COURS.id, 'bouton');
      const vu = await etatEcran(page);
      const checkouts = etat.checkouts.length - cAvant;
      verifier('R7.1 avantage membre mais AUCUN cours lie, drapeau ON : achat direct',
        checkouts === 1, `${checkouts} tentative(s) de checkout`);
      verifier('R7.2 ... et aucune grille d\'horaires (il n\'y aurait rien a dater)',
        vu.dates === 0, `${vu.dates} bouton(s)`);
      await capture(page, 'r7-avantage-sans-cours');
      await contexte.close();
    }

    // --- R7ter : avantage membre, cours lie... mais MASQUE ---------------
    // CINQUIEME condition du predicat. Sans elle, la grille s'ouvrirait VIDE :
    // le visiteur devrait choisir une date qui n'existe pas et ne pourrait plus
    // acheter du tout — une regression sur un parcours qui PAIE.
    {
      etat.memberPricing = true;
      const cAvant = etat.checkouts.length;
      const { contexte, page } = await nouveauContexte(navigateur, srv.base, 1280, 1100, false, 'R7ter');
      await ouvrirOffre(page, srv.base, OFFRE_COURS_MASQUE.id, 'bouton');
      const vu = await etatEcran(page);
      const checkouts = etat.checkouts.length - cAvant;
      verifier('R7ter.1 avantage membre mais TOUS les horaires masques : achat direct '
        + '(la grille ne s\'ouvre pas vide)',
        checkouts === 1 && vu.dates === 0,
        `${checkouts} tentative(s) de checkout, ${vu.dates} bouton(s) de date`);
      await capture(page, 'r7ter-cours-masque');
      await contexte.close();
    }

    // --- R9 : LA BOUTIQUE N'A PAS BOUGE ---------------------------------
    // Le carrousel des produits garde le defaut `lot3bChoixDateRequis = () =>
    // false` : la prop n'est relayee QU'au carrousel des services. Le produit
    // testé remplit pourtant TOUTES les conditions du predicat — si le relais
    // fuyait jusqu'a la boutique, son bouton cesserait de partir en achat
    // direct. Un produit ordinaire passerait ce test meme mal cable.
    {
      etat.memberPricing = true;
      const cAvant = etat.checkouts.length;
      const eAvant = etat.demandes.length;
      const { contexte, page } = await nouveauContexte(navigateur, srv.base, 1280, 1400, false, 'R9');
      await ouvrirOffre(page, srv.base, OFFRE_BOUTIQUE.id, 'bouton');
      const vu = await etatEcran(page);
      const nouveaux = etat.checkouts.slice(cAvant);
      verifier('R9.1 BOUTIQUE, drapeau ON : le bouton « Réserver » d\'un produit physique '
        + 'part TOUJOURS en achat direct',
        nouveaux.length === 1, `${nouveaux.length} tentative(s) de checkout`);
      verifier('R9.2 ... avec le montant du produit (45), pas un tarif membre',
        nouveaux.length === 1 && Math.abs(parseFloat(nouveaux[0].corps.amount) - 45) < 0.001,
        nouveaux.length ? `amount = ${nouveaux[0].corps.amount}` : 'aucun paiement tente');
      verifier('R9.3 ... et AUCUNE grille d\'horaires n\'apparait dans la boutique',
        vu.dates === 0, `${vu.dates} bouton(s) de date`);
      verifier('R9.4 ... et aucune estimation tarifaire n\'est demandee',
        etat.demandes.length - eAvant === 0, `${etat.demandes.length - eAvant} appel(s)`);
      await capture(page, 'r9-boutique-produit-physique');
      await contexte.close();
    }

    // --- R8 : offre GRATUITE — parcours inchange, drapeau ON comme OFF ---
    {
      const observe = {};
      for (const drapeau of [true, false]) {
        etat.memberPricing = drapeau;
        const cAvant = etat.checkouts.length;
        const { contexte, page } = await nouveauContexte(
          navigateur, srv.base, 1280, 1100, false, `R8-${drapeau}`);
        await ouvrirOffre(page, srv.base, OFFRE_GRATUITE.id, 'bouton');
        const vu = await etatEcran(page);
        observe[drapeau] = {
          dates: vu.dates, formulaire: vu.formulaire, checkouts: etat.checkouts.length - cAvant,
        };
        if (drapeau) await capture(page, 'r8-offre-gratuite-drapeau-on');
        await contexte.close();
      }
      verifier('R8.1 offre gratuite : le parcours est IDENTIQUE drapeau ON et drapeau OFF',
        JSON.stringify(observe[true]) === JSON.stringify(observe[false]),
        `ON=${JSON.stringify(observe[true])} OFF=${JSON.stringify(observe[false])}`);
      verifier('R8.2 offre gratuite : le formulaire s\'ouvre, sans grille ni paiement direct',
        observe[true].formulaire === 1 && observe[true].dates === 0
        && observe[true].checkouts === 0, JSON.stringify(observe[true]));
    }

    // =====================================================================
    // A a L — LES SCENARIOS DEMANDES PAR LE PROPRIETAIRE
    // =====================================================================
    // Chaque scenario ouvre un contexte NEUF : aucune memoire ne survit d'un
    // scenario a l'autre, et l'affichage mesure ne peut venir que de la reponse
    // du serveur. Tout tourne sur le bundle REEL, drapeau ON.

    /** Fabrique un scenario client complet et compte ses appels. */
    async function scenarioClient(cle, reponse, idOffre = OFFRE_30.id) {
      etat.memberPricing = true;
      etat.estimation = reponse;
      const { contexte, page } = await nouveauContexte(navigateur, srv.base, 1280, 1100, false, cle);
      await ouvrirOffre(page, srv.base, idOffre, VOIE_UTILE || 'carte');
      const appels = await choisirDate(page, etat, 0);
      const total = await totalAffiche(page);
      const ligne = await page.locator('[data-testid="member-advantage-line"]').count();
      const invitation = await page.locator('[data-testid="member-identification-hint"]').count();
      const corps = (await page.locator('body').innerText()).replace(/\s+/g, ' ');
      return { contexte, page, appels, total, ligne, invitation, corps };
    }

    const scenariosPossibles = !!VOIE_UTILE;

    if (!scenariosPossibles) {
      for (const c of ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']) {
        verifier(`${c} scenario client`, false,
          'ecran inatteignable sur le bundle reel (voir R1) : rien a mesurer');
      }
    } else {
      // --- A : NON-MEMBRE -> 30 -----------------------------------------
      {
        const s = await scenarioClient('A', estimation({ membre: false, votre_tarif: 30 }));
        verifier('A.1 non-membre : le total affiche est 30.00', s.total === '30.00', `lu : ${s.total}`);
        verifier('A.2 non-membre : AUCUNE ligne « Avantage membre »', s.ligne === 0);
        verifier('A.3 non-membre : aucune invitation a s\'identifier', s.invitation === 0);
        verifier('A.4 une seule estimation pour une seule selection',
          s.appels === 1, `${s.appels} appels`);
        await capture(s.page, 'a-non-membre-30');
        await s.contexte.close();
      }

      // --- B : MEMBRE ACTIF A LA DATE -> 15 ------------------------------
      {
        const s = await scenarioClient('B', estimation({
          membre: true, raison: 'membre', avantage_pct: 50, prix_public: 30, votre_tarif: 15,
        }));
        verifier('B.1 membre actif a la date : la ligne « Avantage membre » est affichee',
          s.ligne === 1);
        const l = s.ligne === 1
          ? (await s.page.locator('[data-testid="member-advantage-line"]').innerText()).replace(/\s+/g, ' ')
          : '';
        verifier('B.2 ... et elle annonce -50%', /-\s*50\s*%/.test(l), `lu : « ${l} »`);
        const pub = await lignePrixPublic(s.page);
        verifier('B.3 le prix public 30.00 est affiche juste au-dessus, REELLEMENT barre',
          !!pub && /Prix public/i.test(pub.texte) && /30\.00/.test(pub.texte)
          && /line-through/.test(pub.decoration),
          pub ? `« ${pub.texte} » / ${pub.decoration}` : 'ligne absente');
        verifier('B.4 le total affiche est 15.00', s.total === '15.00', `lu : ${s.total}`);
        verifier('B.5 une seule estimation demandee', s.appels === 1, `${s.appels} appels`);
        await capture(s.page, 'b-membre-actif-15');
        await s.contexte.close();
      }

      // --- C / D : ADHESION EXPIREE, puis ADHESION FUTURE -> 30 ----------
      // Le serveur tranche : dans les DEUX cas il renvoie `membre: false`. Ce que
      // l'ecran doit prouver, c'est qu'il n'invente rien — et qu'il ne laisse pas
      // fuir le vocabulaire interne (« adhesion_expiree ») sous les yeux du client.
      for (const [cle, raison, titre] of [
        ['C', 'adhesion_expiree', 'adhesion EXPIREE avant la seance'],
        ['D', 'adhesion_future', 'adhesion COMMENCANT APRES la seance'],
      ]) {
        const s = await scenarioClient(cle, estimation({
          membre: false, raison, avantage_offre_pct: 50, votre_tarif: 30,
        }));
        verifier(`${cle}.1 ${titre} : le total reste 30.00`, s.total === '30.00', `lu : ${s.total}`);
        verifier(`${cle}.2 ${titre} : aucune ligne d'avantage`, s.ligne === 0);
        verifier(`${cle}.3 ${titre} : le vocabulaire interne ne fuite pas a l'ecran`,
          !/adhesion_expiree|adhesion_future|votre_tarif|prix_public_unitaire/i.test(s.corps),
          'un nom de champ technique est visible par le client');
        await capture(s.page, `${cle.toLowerCase()}-${raison}`);
        await s.contexte.close();
      }

      // --- E : MEMBRE 50 % CONTRE PROMO 20 % -> le membre l'emporte ------
      {
        const s = await scenarioClient('E', estimation({
          membre: true, raison: 'membre', avantage_pct: 50, avantage_promo_pct: 20,
          prix_public: 30, votre_tarif: 15,
        }));
        verifier('E.1 membre 50 % vs promo 20 % : la ligne « Avantage membre » est affichee',
          s.ligne === 1, 'le meilleur des deux n\'est pas celui qui s\'affiche');
        verifier('E.2 ... et le total est le tarif membre 15.00',
          s.total === '15.00', `lu : ${s.total}`);
        await capture(s.page, 'e-membre-bat-promo20');
        await s.contexte.close();
      }

      // --- F : MEMBRE 50 % CONTRE PROMO 70 % -> la promo l'emporte -------
      {
        const s = await scenarioClient('F', estimation({
          membre: false, raison: 'promo', avantage_pct: 70, avantage_offre_pct: 50,
          prix_public: 30, votre_tarif: 9,
        }));
        verifier('F.1 promo 70 % > membre 50 % : AUCUNE ligne « Avantage membre »',
          s.ligne === 0,
          'l\'ecran attribuerait au statut de membre une remise qui vient du code promo');
        verifier('F.2 ... ni ligne « Prix public » barree', !/Prix public/i.test(s.corps));
        // MESURE, pas verdict : sans code promo saisi dans le formulaire, le
        // recapitulatif retombe sur son calcul local (30.00). Le total « 9.00 »
        // du serveur n'est PAS repris — c'est conforme au code (`calculateTotal`
        // ne suit le serveur que si `membre` est vrai) et sans consequence, la
        // caisse restant l'autorite (V429). On le consigne pour que ce ne soit
        // pas une surprise le jour ou quelqu'un s'y fiera.
        noter('F.3 total affiche quand la promo gagne (le navigateur garde son calcul local)',
          `${s.total} CHF — le serveur disait 9.00`);
        await capture(s.page, 'f-promo70-gagne');
        await s.contexte.close();
      }

      // --- G : EGALITE 50 / 50 -> le membre gagne l'egalite --------------
      {
        const s = await scenarioClient('G', estimation({
          membre: true, raison: 'membre', avantage_pct: 50, avantage_promo_pct: 50,
          prix_public: 30, votre_tarif: 15,
        }));
        verifier('G.1 a egalite (membre 50 % / promo 50 %), la ligne « Avantage membre » EST affichee',
          s.ligne === 1, 'le membre perdrait l\'egalite a l\'ecran');
        verifier('G.2 ... et le total est bien 15.00', s.total === '15.00', `lu : ${s.total}`);
        await capture(s.page, 'g-egalite-membre-gagne');
        await s.contexte.close();
      }

      // --- H / I / J : LES REFUS. Ce qui est prouvable cote navigateur ---
      //
      // La DECISION de refuser (date falsifiee, occurrence d'un autre cours,
      // offre d'un autre coach) appartient au SERVEUR — il revalide les
      // occurrences (`lot3b_occurrences_prouvees`) et ignore ce que le
      // navigateur raconte. Aucun test navigateur ne peut la prouver.
      //
      // Ce qui EST prouvable, et qui compte : (1) le navigateur envoie les
      // occurrences au format naif local attendu, (2) ces dates sont exactement
      // celles qu'il a affichees, (3) quand le serveur refuse l'avantage,
      // l'ecran affiche le plein tarif au lieu d'inventer une remise.
      {
        etat.memberPricing = true;
        // Le serveur REFUSE : occurrence non prouvee -> aucun avantage.
        etat.estimation = estimation({
          membre: false, raison: 'occurrence_non_prouvee', avantage_offre_pct: 50, votre_tarif: 30,
        });
        const { contexte, page } = await nouveauContexte(navigateur, srv.base, 1280, 1100, false, 'HIJ');
        await ouvrirOffre(page, srv.base, OFFRE_30.id, VOIE_UTILE);

        // Le libelle REELLEMENT affiche sur le premier bouton de date.
        const libelleDate = (await page.locator(`[data-testid="date-btn-${COURS.id}-0"]`).innerText())
          .replace(/\s+/g, ' ').trim();
        const appels = await choisirDate(page, etat, 0);
        verifier('H.1 une estimation part avec la selection (une seule)',
          appels === 1, `${appels} appel(s)`);

        const envoyeEstim = etat.demandes[etat.demandes.length - 1].corps;
        const dates = envoyeEstim.occurrenceDates || [];
        verifier('H.2 le navigateur envoie `occurrenceDates` au format naif local '
          + '(« 2026-08-26T18:30:00 »), sans Z ni decalage',
          Array.isArray(dates) && dates.length === 1
          && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00$/.test(dates[0]),
          `recu : ${JSON.stringify(dates)}`);
        verifier('H.3 ... et cette date est EXACTEMENT la premiere occurrence affichee',
          dates[0] === OCCURRENCES[0].naif,
          `envoye ${dates[0]} / attendu ${OCCURRENCES[0].naif} (bouton : « ${libelleDate} »)`);
        verifier('H.4 ... et le libelle du bouton porte bien ce jour et cette heure',
          libelleDate.includes(`${OCCURRENCES[0].jour}.${OCCURRENCES[0].mois}`)
          && libelleDate.includes(COURS.time),
          `bouton : « ${libelleDate} » / occurrence ${OCCURRENCES[0].naif}`);

        const totalRefus = await totalAffiche(page);
        const ligneRefus = await page.locator('[data-testid="member-advantage-line"]').count();
        verifier('I.1 le serveur refuse l\'avantage -> le total AFFICHE suit le serveur '
          + '(plein tarif 30.00, pas de remise inventee)',
          totalRefus === '30.00' && ligneRefus === 0,
          `total ${totalRefus}, ${ligneRefus} ligne(s) d'avantage`);

        // On soumet : le POST create-checkout-session est capture puis REFUSE.
        const cAvant = etat.checkouts.length;
        await soumettreFormulaire(page);
        const nouveaux = etat.checkouts.slice(cAvant);
        verifier('J.1 la soumission envoie bien un POST /api/create-checkout-session '
          + '(capture puis REFUSE 405 : rien n\'est ecrit)',
          nouveaux.length === 1, `${nouveaux.length} tentative(s)`);
        const payload = nouveaux.length ? nouveaux[0].corps : {};
        const dcs = payload.occurrenceDates || [];
        verifier('J.2 le paiement porte `occurrenceDates` au MEME format naif local',
          Array.isArray(dcs) && dcs.length === 1
          && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00$/.test(dcs[0]),
          `recu : ${JSON.stringify(dcs)}`);
        verifier('J.3 ... et ce sont exactement les occurrences affichees et estimees',
          dcs[0] === OCCURRENCES[0].naif && dcs[0] === dates[0],
          `checkout ${dcs[0]} / estimation ${dates[0]} / attendu ${OCCURRENCES[0].naif}`);
        verifier('J.4 ... et le montant envoye est le plein tarif refuse par le serveur',
          Math.abs(parseFloat(payload.amount) - 30) < 0.001, `amount = ${payload.amount}`);
        noter('J.5 `offerId` transmis au paiement (le serveur recalcule tout depuis lui)',
          String(payload.offerId));
        await capture(page, 'hij-refus-serveur-plein-tarif');
        await contexte.close();
      }

      // --- MULTI-DATES : deux occurrences, deux dates envoyees -----------
      // Une adhesion couvre une PERIODE : sur un panier de plusieurs seances,
      // n'envoyer que la premiere ferait payer les autres au tarif de celle-ci.
      {
        etat.memberPricing = true;
        etat.estimation = estimation({
          membre: true, raison: 'membre', avantage_pct: 50, prix_public: 30, votre_tarif: 15,
        });
        const { contexte, page } = await nouveauContexte(navigateur, srv.base, 1280, 1100, false, 'MULTI');
        await ouvrirOffre(page, srv.base, OFFRE_30.id, VOIE_UTILE);
        const a1 = await choisirDate(page, etat, 0);
        etat.estimation = estimation({
          membre: true, raison: 'membre', avantage_pct: 30, prix_public: 60,
          quantity: 2, prix_public_unitaire: 30, votre_tarif: 42,
        });
        const a2 = await choisirDate(page, etat, 1);
        verifier('M1.1 premiere selection : UN appel', a1 === 1, `${a1} appels`);
        verifier('M1.2 seconde selection : UN appel de plus (aucune rafale)',
          a2 === 1, `${a2} appels pour un seul changement`);
        const envoye = etat.demandes[etat.demandes.length - 1].corps;
        verifier('M1.3 les DEUX occurrences sont envoyees, au format naif local',
          Array.isArray(envoye.occurrenceDates) && envoye.occurrenceDates.length === 2
          && envoye.occurrenceDates[0] === OCCURRENCES[0].naif
          && envoye.occurrenceDates[1] === OCCURRENCES[1].naif,
          `recu : ${JSON.stringify(envoye.occurrenceDates)}`);
        verifier('M1.4 la quantite suit le nombre de dates',
          envoye.quantity === 2, `quantity = ${envoye.quantity}`);
        verifier('M1.5 l\'ecran relaie la NOUVELLE reponse serveur (42.00), il ne memorise rien',
          (await totalAffiche(page)) === '42.00', `lu : ${await totalAffiche(page)}`);
        const l = (await page.locator('[data-testid="member-advantage-line"]').innerText())
          .replace(/\s+/g, ' ');
        verifier('M1.6 ... et la ligne annonce desormais -30%', /-\s*30\s*%/.test(l), `lu : « ${l} »`);
        await capture(page, 'm1-multi-dates');
        await contexte.close();
      }

      // --- MEMBRE NON IDENTIFIE (l'invitation discrete) -------------------
      {
        const s = await scenarioClient('IDENT', estimation({
          membre: false, identification_requise: true, avantage_offre_pct: 50, votre_tarif: 30,
        }));
        verifier('N1.1 membre non identifie : l\'invitation discrete est affichee',
          s.invitation === 1
          && await s.page.locator('[data-testid="member-identification-hint"]').isVisible(),
          'le membre croirait avoir perdu son avantage');
        verifier('N1.2 ... elle invite a ouvrir son espace, sans rien reveler',
          /Membre Afroboost/i.test(s.corps) && !/@/.test(
            await s.page.locator('[data-testid="member-identification-hint"]').innerText()));
        verifier('N1.3 ... et aucune ligne d\'avantage tant qu\'il n\'est pas identifie',
          s.ligne === 0);
        verifier('N1.4 ... le total reste le prix public 30.00', s.total === '30.00', `lu : ${s.total}`);
        await capture(s.page, 'n1-membre-non-identifie');
        await s.contexte.close();
      }
    }

    // --- K : MEMBRE CONSOMMANT PULSE x10 --------------------------------
    // Consommer un credit d'un pack deja paye ne produit AUCUNE surface
    // navigateur dans ce parcours : le decompte des seances vit cote serveur
    // (abonnement + credits), pas dans le recapitulatif d'achat. Ce qui est
    // mesurable ici, c'est qu'aucun paiement n'est declenche tant que le
    // visiteur n'a pas soumis le formulaire.
    nonCouvert('K « membre consommant PULSE x10 -> aucun paiement supplementaire »',
      'DECISION SERVEUR — couverture = tests Python. La consommation d\'un credit '
      + 'd\'abonnement n\'a aucune representation dans le recapitulatif d\'achat : '
      + 'le navigateur n\'a rien a afficher ni a envoyer. Ne PAS compter ce point '
      + 'comme verifie cote interface.');

    // --- L : PULSE 250 -> 250 et AUCUNE ligne d'avantage ----------------
    // PULSE n'a pas d'avantage membre (elle OUVRE l'adhesion) : le correctif de
    // joignabilite ne la deroute pas, elle part en achat direct. La preuve est
    // donc dans le MONTANT envoye a la caisse, et dans l'absence de tout ecran
    // d'avantage.
    {
      etat.memberPricing = true;
      etat.estimation = estimation({
        offer_id: OFFRE_PULSE.id, prix_public_unitaire: 250, prix_public: 250,
        votre_tarif: 250, membre: false, avantage_pct: null, raison: 'public',
      });
      const cAvant = etat.checkouts.length;
      const eAvant = etat.demandes.length;
      const { contexte, page } = await nouveauContexte(navigateur, srv.base, 1280, 1100, false, 'L');
      await ouvrirOffre(page, srv.base, OFFRE_PULSE.id, 'bouton');
      const nouveaux = etat.checkouts.slice(cAvant);
      verifier('L.1 PULSE 250 (offre qui OUVRE l\'adhesion) part en achat direct',
        nouveaux.length === 1, `${nouveaux.length} tentative(s) de checkout`);
      verifier('L.2 ... et le montant envoye est bien 250, pas un tarif membre',
        nouveaux.length === 1 && Math.abs(parseFloat(nouveaux[0].corps.amount) - 250) < 0.001,
        nouveaux.length ? `amount = ${nouveaux[0].corps.amount}` : 'aucun paiement tente');
      verifier('L.3 ... aucune ligne « Avantage membre » nulle part a l\'ecran',
        (await page.locator('[data-testid="member-advantage-line"]').count()) === 0);
      verifier('L.4 ... et aucune estimation n\'a ete demandee pour elle',
        etat.demandes.length - eAvant === 0, `${etat.demandes.length - eAvant} appel(s)`);
      await capture(page, 'l-pulse-250');
      await contexte.close();
    }

    // =====================================================================
    // M — DESKTOP ET MOBILE : le parcours modifie, dans les deux tailles.
    // =====================================================================
    if (!VOIE_UTILE) {
      verifier('M desktop/mobile : le parcours de reservation modifie est jouable', false,
        'ecran inatteignable sur le bundle reel (voir R1)');
    } else {
      const TAILLES = [
        { cle: 'desktop', l: 1280, h: 800, titre: 'desktop 1280x800' },
        { cle: 'mobile', l: 390, h: 844, titre: 'mobile 390x844 (iPhone 12/13)' },
      ];
      for (const t of TAILLES) {
        etat.memberPricing = true;
        etat.estimation = estimation({
          membre: true, raison: 'membre', avantage_pct: 50, prix_public: 30, votre_tarif: 15,
        });
        const { contexte, page } = await nouveauContexte(
          navigateur, srv.base, t.l, t.h, false, `M-${t.cle}`);
        await ouvrirOffre(page, srv.base, OFFRE_30.id, VOIE_UTILE);

        // 1. La grille d'horaires : visible ET defilable.
        const grille = await page.evaluate(() => {
          const sec = document.getElementById('sessions-section');
          if (!sec) return null;
          const conteneur = sec.querySelector('.sessions-scrollbar');
          const r = sec.getBoundingClientRect();
          const cs = conteneur ? getComputedStyle(conteneur) : null;
          return {
            visible: r.width > 0 && r.height > 0 && getComputedStyle(sec).display !== 'none',
            dansLaVue: r.top < window.innerHeight && r.bottom > 0,
            overflowY: cs ? cs.overflowY : 'absent',
            maxHeight: cs ? cs.maxHeight : 'absent',
          };
        });
        verifier(`M.${t.cle}.1 la grille d'horaires est rendue et visible (${t.titre})`,
          !!grille && grille.visible, JSON.stringify(grille));
        verifier(`M.${t.cle}.2 ... et elle est DEFILABLE (overflow-y auto/scroll + hauteur bornee)`,
          !!grille && /auto|scroll/.test(grille.overflowY) && grille.maxHeight !== 'none',
          JSON.stringify(grille));

        await choisirDate(page, etat, 0);

        // 2. Le bloc de prix : visible, sans debordement horizontal.
        await page.locator('[data-testid="total-price"]').scrollIntoViewIfNeeded();
        await page.waitForTimeout(600);
        const bloc = await page.evaluate(() => {
          const total = document.querySelector('[data-testid="total-price"]');
          const av = document.querySelector('[data-testid="member-advantage-line"]');
          const pub = av ? av.previousElementSibling : null;
          const dansVue = (el) => {
            if (!el) return false;
            const r = el.getBoundingClientRect();
            return r.top >= 0 && r.bottom <= window.innerHeight
              && r.left >= 0 && r.right <= window.innerWidth && r.width > 0;
          };
          // Qui est REELLEMENT au-dessus du total, en son centre ?
          let recouvrement = null;
          if (total) {
            const r = total.getBoundingClientRect();
            const dessus = document.elementFromPoint(
              Math.min(window.innerWidth - 1, Math.max(0, r.left + r.width / 2)),
              Math.min(window.innerHeight - 1, Math.max(0, r.top + r.height / 2)));
            if (dessus && !total.contains(dessus) && !dessus.contains(total)) {
              recouvrement = `${dessus.tagName}.${(dessus.className || '').toString().slice(0, 40)}`;
            }
          }
          return {
            scrollWidth: document.documentElement.scrollWidth,
            clientWidth: document.documentElement.clientWidth,
            totalDansVue: dansVue(total),
            avantageDansVue: dansVue(av),
            publicDansVue: dansVue(pub),
            texteTotal: total ? (total.innerText || '').replace(/\s+/g, ' ') : null,
            recouvrement,
          };
        });
        verifier(`M.${t.cle}.3 le bloc « Prix public / Avantage membre / Total » est ENTIEREMENT `
          + `dans le viewport (${t.titre})`,
          bloc.totalDansVue && bloc.avantageDansVue && bloc.publicDansVue,
          JSON.stringify(bloc));
        verifier(`M.${t.cle}.4 aucun debordement horizontal `
          + '(documentElement.scrollWidth <= clientWidth)',
          bloc.scrollWidth <= bloc.clientWidth,
          `scrollWidth=${bloc.scrollWidth} clientWidth=${bloc.clientWidth}`);
        verifier(`M.${t.cle}.5 aucun element ne recouvre le Total`,
          bloc.recouvrement === null, `recouvert par ${bloc.recouvrement}`);
        verifier(`M.${t.cle}.6 le Total affiche bien le tarif membre 15.00`,
          /15\.00/.test(bloc.texteTotal || ''), `lu : « ${bloc.texteTotal} »`);

        // 3. Le bouton de reservation : atteignable apres defilement.
        const btn = page.locator('[data-testid="submit-reservation-btn"]');
        await btn.scrollIntoViewIfNeeded();
        await page.waitForTimeout(500);
        const etatBtn = await page.evaluate(() => {
          const b = document.querySelector('[data-testid="submit-reservation-btn"]');
          if (!b) return null;
          const r = b.getBoundingClientRect();
          const dessus = document.elementFromPoint(
            Math.min(window.innerWidth - 1, Math.max(0, r.left + r.width / 2)),
            Math.min(window.innerHeight - 1, Math.max(0, r.top + r.height / 2)));
          return {
            dansVue: r.top >= 0 && r.bottom <= window.innerHeight && r.width > 0 && r.height > 0,
            cliquable: !!dessus && (b === dessus || b.contains(dessus) || dessus.contains(b)),
            couvertPar: dessus && !(b === dessus || b.contains(dessus) || dessus.contains(b))
              ? `${dessus.tagName}.${(dessus.className || '').toString().slice(0, 40)}` : null,
          };
        });
        verifier(`M.${t.cle}.7 le bouton de reservation est atteignable apres defilement`,
          !!etatBtn && etatBtn.dansVue && etatBtn.cliquable, JSON.stringify(etatBtn));

        await capture(page, `m-${t.cle}-recapitulatif`);
        await contexte.close();
      }
    }

    // =====================================================================
    // Z — GARDE-FOUS TRANSVERSES
    // =====================================================================
    {
      const ecritures = srv.journal.filter((e) => e.methode !== 'GET' && e.chemin.startsWith('/api/'));
      const horsEstimation = ecritures.filter((e) => e.chemin !== '/api/tarif/estimation');
      const abouties = horsEstimation.filter((e) => e.statut !== 405);
      verifier('Z1 aucune ecriture autre que l\'estimation n\'a abouti (toutes refusees en 405)',
        abouties.length === 0, abouties.map((e) => `${e.methode} ${e.chemin}`).join(', '));
      const spontanees = [...new Set(horsEstimation.map((e) => `${e.methode} ${e.chemin}`))];
      noter('Z1b ecritures tentees par l\'app (toutes refusees)', spontanees.join(', ') || 'aucune');

      const bruit = /ERR_FAILED|ERR_ABORTED|fetching the script|405|sanitize-data|auto-save/i;
      const vraies = erreursPage.filter((e) => !bruit.test(e));
      verifier('Z2 aucune erreur JavaScript sur l\'ensemble des parcours traverses',
        vraies.length === 0, vraies.slice(0, 4).join(' | '));

      // Si le bundle avait ete construit avec la valeur de `frontend/.env.local`
      // (https://afroboost.com), les appels seraient partis vers la PRODUCTION.
      // Le navigateur les couperait, mais un tel bundle ne prouverait plus rien :
      // ce test doit le DIRE, pas le taire.
      const fuites = [...new Set(bloqueesGlobal.filter((u) => u.includes('/api/')))];
      verifier('Z3 aucun appel API n\'a tente de sortir vers un autre hote',
        fuites.length === 0, `bundle mal construit ? ${fuites.slice(0, 3).join(', ')}`);

      // ANTI-BOUCLE. Le nombre attendu n'est pas une constante ecrite a la main
      // (elle deviendrait fausse au premier scenario ajoute) : c'est le nombre
      // de clics sur un bouton de date, compte par le seul helper qui en fait.
      verifier('Z4 aucune boucle d\'appels : une estimation par changement de selection, '
        + 'pas une de plus',
        etat.demandes.length === gestesSelection,
        `${etat.demandes.length} estimations pour ${gestesSelection} selections`);
    }

    // =====================================================================
    // CE QUI N'EST PAS COUVERT, ET QUI DOIT SE VOIR
    // =====================================================================
    nonCouvert('X1 la REGLE serveur (qui est membre, quel pourcentage l\'emporte, '
      + 'revalidation des occurrences)',
      'DECISION SERVEUR — le backend ne peut pas tourner ici (Python 3.9, FastAPI absent, '
      + 'MONGO_URL requis) : les reponses /api/tarif/estimation sont des fixtures. '
      + 'Couverture = tests Python (tests/test_lot3b_avantage_membre.py). Les scenarios '
      + 'H, I, J et K en dependent pour leur moitie « refus ».');
    nonCouvert('X2 le montant REELLEMENT preleve a la caisse',
      'aucun paiement n\'est declenche (consigne). L\'estimation est un affichage ; '
      + 'la caisse recalcule tout de son cote et ignore le total du navigateur (V429).');
    nonCouvert('X3 la persistance de `member_discount_pct` (PUT /offers)',
      'toute ecriture est refusee par le bouchon (405) : seuls la presence et le '
      + 'comportement du champ sont mesures, pas son enregistrement.');
    nonCouvert('X4 le comportement du drapeau lu depuis la VRAIE table de flags',
      '`MEMBER_PRICING_ENABLED` est servi par le bouchon. Ce test prouve que le frontend '
      + 'obeit au drapeau, pas que la production le posera a la bonne valeur.');
  } finally {
    await navigateur.close();
    await srv.arreter();
  }
}

// ---------------------------------------------------------------------------
// 6. RAPPORT
// ---------------------------------------------------------------------------

principal()
  .then(() => {
    const largeur = Math.min(Math.max(...resultats.map((r) => r.nom.length), 40), 110);
    console.log('\n╔' + '═'.repeat(largeur + 12) + '╗');
    console.log('║ LOT 3b — AVANTAGE TARIFAIRE MEMBRE : PREUVES EN NAVIGATEUR REEL'
      + ' '.repeat(Math.max(0, largeur - 51)) + '║');
    console.log('╚' + '═'.repeat(largeur + 12) + '╝');
    let echecs = 0;
    for (const r of resultats) {
      const etiquette = r.ok === null ? 'NON TESTE' : r.ok ? '   OK    ' : '  ECHEC  ';
      if (r.ok === false) echecs += 1;
      console.log(`[${etiquette}] ${r.nom}`);
      if (r.detail) console.log('            ↳ ' + r.detail);
    }
    const ok = resultats.filter((r) => r.ok === true).length;
    const nc = resultats.filter((r) => r.ok === null).length;
    console.log(`\n${ok} OK · ${echecs} ECHEC · ${nc} non teste / informatif`);
    console.log('Voie de clic menant au formulaire : ' + (VOIE_UTILE || 'AUCUNE'));
    console.log('Captures : ' + CAPTURES);
    process.exit(echecs === 0 ? 0 : 1);
  })
  .catch((e) => {
    console.error('\nARRET BRUTAL :', e && e.stack ? e.stack : e);
    process.exit(2);
  });
