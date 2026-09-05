/**
 * P3-S2 — L'ÉCRAN PROSPECTION.
 * ============================
 *
 * CE QU'IL FAIT : il affiche les prospects partenaires préparés par Cowork,
 * les filtre, ouvre la fiche de chacun, et permet de corriger ce qui se corrige
 * à la main. Rien d'autre.
 *
 * CE QU'IL NE FAIT PAS, ET C'EST DÉLIBÉRÉ : il n'envoie RIEN. Aucun bouton
 * « Envoyer », aucun « Contacter », aucune relance. Les messages J0/J+3/J+7
 * sont affichés en lecture et copiables — l'envoi appartient à P3-S3, derrière
 * une file d'approbation. Un bouton d'envoi ici serait un envoi accidentel à un
 * vrai festival.
 *
 * LES PROSPECTS NE SONT PAS DES CLIENTS. Cet écran lit `partner_prospects` et
 * cette collection seule. Il ne touche ni aux contacts, ni aux abonnés, ni aux
 * participants, ni aux réservations — et ses compteurs ne modifient aucun
 * compteur métier.
 *
 * CANDIDATURE / ACCEPTÉ viennent du serveur, qui compte les prospects PORTANT
 * un lien vers P2. Ils valent 0 tant que P3-S3 n'a pas construit ce
 * rattachement : afficher ici le nombre de partenaires de P2 donnerait un
 * chiffre juste au premier coup d'œil et faux dès le premier partenaire venu
 * d'ailleurs.
 *
 * CHARGEMENT : `useChargement` (socle P0). Une liste vide ne peut donc pas être
 * confondue avec un refus — tant que la réponse n'est pas là, l'écran dit « — ».
 *
 * COULEURS : uniquement `var(--primary-color)` / `var(--primary-rgb)`. Les
 * hexadécimaux après la virgule sont des REPLIS, jamais des valeurs imposées.
 * ICÔNES : SVG inline via `SvgIcon`, jamais d'emoji.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import SvgIcon from '../SvgIcon';
import useChargement, { SECTION } from '../../hooks/useChargement';
import { SectionErreur } from '../ui/EtatChargement';

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const RGB = 'var(--primary-rgb, 217, 28, 210)';
/* LE TEXTE EST POSÉ ICI, PAS HÉRITÉ — la leçon de P3-S2.
   Le tableau de bord est sombre par dessin (`.section-gradient` et
   `.card-gradient` sont des dégradés noirs), mais le jeu de jetons shadcn
   resté actif est le jeu CLAIR : `--foreground: 0 0% 3.9%`, et la classe
   `.dark` n'est posée nulle part. Un composant qui écrit `color: inherit`
   hérite donc d'un `rgb(10,10,10)` quasi noir SUR DU NOIR — contraste 1.06,
   texte invisible. Tous les autres écrans du tableau de bord
   (AdhesionsManager, PartnerApplications, ContactsManager) posent leur
   couleur explicitement : celui-ci fait pareil. Aucun thème global n'est
   touché — ce serait un autre lot, et un risque sans rapport. */
const TEXTE = '#fff';
/* P3-S2D — LA COULEUR DE MARQUE, RENDUE LISIBLE SANS CHANGER DE TEINTE.
   Le chiffre de la tuile ACTIVE s'ecrit dans la couleur du coach, sur le fond
   teinte de cette meme couleur a 16 % sur du noir. Avec la couleur mesuree en
   production (#9f2d70, un magenta sombre), cela donnait 2.85:1 — sous le seuil
   WCAG << gros texte >> de 3:1, qui s'applique ici (20 px, gras).

   `color-mix` eclaircit la couleur DU COACH de 20 % vers le blanc : la teinte
   est conservee, l'identite aussi, et le calcul suit sa couleur quelle qu'elle
   soit — aucun hexadecimal n'est fige. Mesure sur les trois couleurs reellement
   en base : #9f2d70 -> 4.29:1, #c328be et #d91cd2 -> au-dela de 5:1.

   REPLI : un navigateur sans `color-mix` (avant Chrome 111 / Safari 16.2)
   rejette la declaration ; le chiffre herite alors du blanc de la racine —
   19.78:1, lisible, simplement pas colore. La degradation est sure.

   LIMITE ASSUMEE : une couleur personnalisee EXTREMEMENT sombre resterait sous
   3:1 meme eclaircie de 20 %. La traiter demanderait un jeton conscient de la
   luminance, applicable a tout le tableau de bord — un autre lot.

   La bordure et le fond de la tuile gardent la couleur BRUTE : l'identite
   visuelle de l'etat actif ne change pas. */
const PRIMAIRE_LISIBLE = 'color-mix(in srgb, var(--primary-color, #D91CD2) 80%, white)';

/* Les valeurs techniques sont celles du serveur (P3S1_CATEGORIES). Le libellé
   n'existe que pour l'affichage : c'est la clé qui voyage, jamais le mot. */
export const CATEGORIES = [
  { cle: 'festival', libelle: 'Festival' },
  { cle: 'ecole_danse', libelle: 'École de danse' },
  { cle: 'restaurant', libelle: 'Restaurant' },
  { cle: 'bar', libelle: 'Bar' },
  { cle: 'commerce', libelle: 'Commerce' },
  { cle: 'organisateur_evenement', libelle: 'Organisateur événementiel' },
  { cle: 'communaute_etudiante', libelle: 'Communauté étudiante' },
  { cle: 'influenceur', libelle: 'Influenceur' },
  // P3-S2B — l'expansion Lausanne / Genève / Zurich. « Association » reste
  // distincte de « Communauté étudiante » : on n'écrit pas la même chose à une
  // faîtière de la diaspora qu'à un bureau des étudiants.
  { cle: 'association', libelle: 'Association' },
  { cle: 'fitness', libelle: 'Fitness' },
];

/* Les six statuts AMONT. `decouverte`, `actif` et `ambassadeur` n'y sont pas :
   ils appartiennent au partenaire (P2), pas au prospect. */
export const STATUTS = [
  { cle: 'a_contacter', libelle: 'À contacter' },
  { cle: 'contacte', libelle: 'Contacté' },
  { cle: 'repondu', libelle: 'Répondu' },
  { cle: 'interesse', libelle: 'Intéressé' },
  { cle: 'sans_reponse_pause', libelle: 'Sans réponse — pause' },
  { cle: 'refuse', libelle: 'Refusé' },
];

export const COLLABORATIONS = [
  { cle: '', libelle: '— non défini' },
  { cle: 'community', libelle: 'Communauté (lien + QR)' },
  { cle: 'event_programming', libelle: 'Prestation / programmation' },
  { cle: 'both', libelle: 'Les deux' },
];

const PRIORITES = ['A', 'B', 'C'];

/* P3-S3-B — les libellés lisibles des vocabulaires du serveur. Aucun calcul :
   le serveur décide du canal et du type d'exécution, l'écran ne fait que
   traduire. Deux endroits pour une même règle finiraient par diverger. */
const LIBELLE_CANAL = {
  email: 'E-mail', whatsapp: 'WhatsApp', instagram: 'Instagram',
  formulaire: 'Formulaire', telephone: 'Téléphone', visite: 'Visite', aucun: 'Aucun',
};
const LIBELLE_EXECUTION = {
  AUTO: 'Automatique', ASSISTE: 'Assisté', MANUEL: 'Manuel', BLOQUE: 'Bloqué',
};
const LIBELLE_ETAT = {
  preparee: 'Campagne préparée', approuvee: 'Campagne approuvée',
  en_cours: 'En cours', terminee: 'Terminée', annulee: 'Annulée', brouillon: 'Brouillon',
};
const LIBELLE_STATUT_ACTION = {
  pret: 'Prêt', exclu: 'Exclu', bloque: 'Bloqué',
};

const erreurLisible = (err, repli) => {
  const detail = err && err.response && err.response.data && err.response.data.detail;
  return typeof detail === 'string' ? detail : repli;
};
const TAILLES = [25, 50];

const libelleDe = (liste, cle) => {
  const trouve = liste.find((x) => x.cle === cle);
  return trouve ? trouve.libelle : (cle || '—');
};

/* Une valeur absente s'affiche « — », jamais 0 ni une chaîne vide : c'est ce
   qui distingue « pas de donnée » de « donnée nulle ». */
const ou = (valeur) => {
  if (valeur === null || valeur === undefined || valeur === '') return '—';
  return valeur;
};

const estUrl = (v) => typeof v === 'string' && /^https?:\/\//i.test(v.trim());

/* Un lien externe ne s'ouvre JAMAIS tout seul : c'est un `<a>` que l'humain
   clique. `noopener` empêche la page ouverte d'accéder à la nôtre. */
function LienExterne({ href, children }) {
  const url = (href || '').trim();
  if (!url) return <span>—</span>;
  const complet = estUrl(url) ? url : `https://${url.replace(/^\/+/, '')}`;
  return (
    <a
      href={complet}
      target="_blank"
      rel="noopener noreferrer"
      style={{ color: PRIMAIRE, textDecoration: 'none', wordBreak: 'break-all' }}
    >
      {children || url}{' '}
      <SvgIcon name="externalLink" size={11} />
    </a>
  );
}

function Tuile({ libelle, valeur, actif, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        flex: '1 1 110px',
        minWidth: '104px',
        textAlign: 'left',
        padding: '10px 12px',
        borderRadius: '10px',
        cursor: onClick ? 'pointer' : 'default',
        border: `1px solid ${actif ? PRIMAIRE : 'rgba(255,255,255,0.10)'}`,
        background: actif ? `rgba(${RGB}, 0.16)` : 'rgba(255,255,255,0.04)',
        color: 'inherit',
      }}
      data-testid={`tuile-${libelle}`}
    >
      <div style={{ fontSize: '11px', opacity: 0.65, lineHeight: 1.3 }}>{libelle}</div>
      <div style={{ fontSize: '20px', fontWeight: 700, color: actif ? PRIMAIRE_LISIBLE : 'inherit' }}>
        {valeur}
      </div>
    </button>
  );
}

/* AI-P2 — LES LIBELLÉS D'INTENTION, EN FRANÇAIS ET EN MAJUSCULES.
   La valeur stockée reste anglaise-neutre (`question`, `refus`…) : elle sert
   au tri et aux tests. Ce qui s'affiche est traduit ICI, une seule fois, pour
   qu'un renommage d'interface ne touche jamais la donnée. */
const LIBELLE_INTENTION = {
  question: 'QUESTION',
  positif: 'POSITIF',
  refus: 'REFUS',
  absence: 'ABSENCE',
  autre: 'À QUALIFIER',
};

/* Les quatre tons de régénération. Liste FERMÉE côté serveur aussi : une
   valeur libre entrerait dans une invite, donc serait une injection. */
/* AI-P3 — LES CINQ ÉTATS COMMERCIAUX. Ils répondent à « qu'est-ce que je dois
   faire ? », jamais à « est-ce que je l'ai lu ? » : les deux dimensions ont
   leurs propres champs et ne se confondent pas. Les couleurs sont SÉMANTIQUES
   (ambre = il faut agir, vert = clos, neutre = on attend), jamais la couleur de
   marque — qui, elle, appartient au coach. */
const STATUT_COMMERCIAL = {
  a_repondre: { libelle: 'À RÉPONDRE', fond: 'rgba(245,158,11,0.22)' },
  appel_a_faire: { libelle: 'APPEL À FAIRE', fond: 'rgba(245,158,11,0.30)' },
  en_attente: { libelle: 'EN ATTENTE', fond: 'rgba(255,255,255,0.14)' },
  refus: { libelle: 'REFUS', fond: 'rgba(239,68,68,0.20)' },
  traite: { libelle: 'TRAITÉ', fond: 'rgba(34,197,94,0.22)' },
};

/* Les cinq canaux d'une action humaine. Liste fermée côté serveur aussi. */
const TYPES_NOTE = [
  { cle: 'appel', libelle: 'Appel' },
  { cle: 'whatsapp', libelle: 'WhatsApp' },
  { cle: 'rencontre', libelle: 'Rencontre' },
  { cle: 'information', libelle: 'Information' },
  { cle: 'autre', libelle: 'Autre' },
];

const TONS_IA = [
  { cle: 'court', libelle: 'Plus court' },
  { cle: 'chaleureux', libelle: 'Plus chaleureux' },
  { cle: 'professionnel', libelle: 'Plus professionnel' },
  { cle: 'direct', libelle: 'Plus direct' },
];

function Etiquette({ texte, ton }) {
  const fonds = {
    neutre: 'rgba(255,255,255,0.08)',
    primaire: `rgba(${RGB}, 0.18)`,
  };
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: '999px',
        fontSize: '11px',
        whiteSpace: 'nowrap',
        background: fonds[ton] || fonds.neutre,
        color: ton === 'primaire' ? PRIMAIRE : 'inherit',
      }}
    >
      {texte}
    </span>
  );
}

export default function ProspectsSection({ API, inboundCible, onCibleConsommee }) {
  const base = API || '';

  const [filtres, setFiltres] = useState({
    status: '', category: '', priority: '', wave: '', city: '',
  });
  const [taille, setTaille] = useState(25);
  const [page, setPage] = useState(0);
  const [ouvert, setOuvert] = useState(null); // le prospect affiché en fiche
  const [brouillon, setBrouillon] = useState(null);
  const [enregistrement, setEnregistrement] = useState(false);
  const [message, setMessage] = useState(null);

  /* CAL-3 — L'AGENDA DE LA FICHE OUVERTE.
     Chargé à l'ouverture d'une fiche, jamais avant : c'est une lecture par
     prospect, et la charger pour les 142 lignes de la liste ferait 142 appels
     pour une information que personne ne regarde. */
  const [agenda, setAgenda] = useState(null);
  const [planifOuvert, setPlanifOuvert] = useState(false);
  const [planif, setPlanif] = useState({ quand: '', duree: 30, type: 'appel', titre: '' });
  const [planifEnCours, setPlanifEnCours] = useState(false);

  const chargerAgenda = React.useCallback(async (reference) => {
    if (!reference) { setAgenda(null); return; }
    try {
      const r = await axios.get(`${base}/prospect-agenda/${encodeURIComponent(reference)}`);
      setAgenda((r && r.data) || null);
    } catch (e) {
      setAgenda(null);
    }
  }, [base]);

  /* P3-S3-B — LA PREPARATION DE CAMPAGNE.
     `selection` est un TABLEAU d'identifiants, pas un objet : la règle V305
     interdit de reposer un objet neuf quand rien n'a changé, et une liste de
     chaînes se compare sans risque. Vide = « toute la sélection courante ». */
  /* La dépendance est la RÉFÉRENCE, une chaîne — jamais l'objet `ouvert`,
     qui est neuf à chaque rendu et relancerait l'effet en boucle (règle
     absolue, incident V305). */
  const refOuverte = (ouvert && ouvert.ref) || '';
  useEffect(() => {
    if (refOuverte) chargerAgenda(refOuverte);
    else { setAgenda(null); setPlanifOuvert(false); }
  }, [refOuverte, chargerAgenda]);

  const [selection, setSelection] = useState([]);
  const [campagne, setCampagne] = useState(null);      // aperçu OU campagne créée
  const [actions, setActions] = useState([]);
  const [prepEnCours, setPrepEnCours] = useState(false);
  const [messageCampagne, setMessageCampagne] = useState(null);
  const [actionOuverte, setActionOuverte] = useState(null);
  /* P3-S3-C — filtre de l'aperçu : '' | 'sans_langue' | 'sans_message'.
     Les 78 destinataires sans langue déclarée doivent pouvoir être VUS avant
     toute activation ; l'écran ne les corrige pas et ne suppose rien. */
  const [filtreApercu, setFiltreApercu] = useState('');
  /* AI-P3 — le filtre commercial des réponses reçues. Une CHAÎNE, jamais un
     objet : la règle V305 interdit de reposer un objet neuf quand rien n'a
     changé, et une chaîne se compare sans risque. */
  const [filtreStatut, setFiltreStatut] = useState('');

  /* Les dépendances sont des CHAÎNES, jamais l'objet `filtres` — qui est neuf à
     chaque rendu et relancerait l'effet en boucle (règle absolue, incident V305). */
  const signature = [
    filtres.status, filtres.category, filtres.priority, filtres.wave, filtres.city,
    String(taille), String(page),
    /* Le filtre commercial entre dans la signature : sans lui, changer de
       filtre ne relancerait aucune lecture et l'écran mentirait. */
    filtreStatut,
  ].join('|');

  const chargement = useChargement(
    {
      prospects: {
        url: `${base}/partner-prospects`,
        signature: true,
        appel: async () => {
          const params = { limit: taille, offset: page * taille };
          Object.keys(filtres).forEach((cle) => {
            if (filtres[cle]) params[cle] = filtres[cle];
          });
          const rep = await axios.get(`${base}/partner-prospects`, { params });
          return rep && rep.data ? rep.data : null;
        },
        extraire: (donnees) => donnees,
      },
      /* P3-S3-C — LA CAMPAGNE OUVERTE, s'il y en a une.
         Sans cette lecture, l'écran ne savait pas qu'une campagne existait
         déjà : il ne proposait que « Préparer », et deux préparations
         successives fabriquaient deux campagnes pour un seul lancement. */
      campagnes: {
        url: `${base}/prospect-campaigns`,
        signature: true,
        appel: async () => {
          const rep = await axios.get(`${base}/prospect-campaigns`,
            { params: { ouvertes: 1, limit: 5 } });
          return rep && rep.data ? rep.data : null;
        },
        extraire: (donnees) => donnees,
      },
      /* P3-U3 — LES RÉPONSES REÇUES.
         Elles n'apparaissaient nulle part : le moteur U2 les stocke, la route
         les rend, et l'écran ne les demandait pas. Une réponse invisible est
         une réponse perdue — c'est exactement ce que ce chantier veut éviter.
         Chargée comme les deux autres sources, donc jamais de compteur à 0
         suivi d'un rafraîchissement obligatoire (socle P0). */
      reponses: {
        url: `${base}/prospect-inbound`,
        signature: true,
        appel: async () => {
          /* AI-P3 — LE FILTRE PART AU SERVEUR, JAMAIS À L'ÉCRAN. Le statut
             commercial est DÉRIVÉ (traité, dernière note déclarée, intention) :
             il n'existe dans aucun champ. Filtrer la page rendue donnerait un
             écran qui ment dès la deuxième page ; le serveur, lui, calcule sur
             toute la portée du coach puis pagine. */
          const params = { limit: 20 };
          if (filtreStatut) params.statut_commercial = filtreStatut;
          const rep = await axios.get(`${base}/prospect-inbound`, { params });
          return rep && rep.data ? rep.data : null;
        },
        extraire: (donnees) => donnees,
      },
    },
    { deps: [base, signature] }
  );

  const sectionCampagnes = chargement.sections.campagnes;
  const campagnesOuvertes = (sectionCampagnes && sectionCampagnes.etat === SECTION.OK
    && sectionCampagnes.donnees && sectionCampagnes.donnees.campaigns) || [];
  const campagneOuverte = campagnesOuvertes[0] || null;

  /* P3-U3 — dérivé de la section, jamais recopié dans un état local. */
  const sectionReponses = chargement.sections.reponses;
  const reponses = (sectionReponses && sectionReponses.etat === SECTION.OK
    && sectionReponses.donnees && sectionReponses.donnees.messages) || [];
  /* `a_rattacher` — les messages qu'aucune action n'a pu réclamer. À ne pas
     confondre avec l'état commercial « EN ATTENTE » (AI-P3), qui veut dire
     « j'attends une réponse du partenaire » : les deux portaient le même nom,
     et le second écrasait le premier. */
  const reponsesARattacher = (sectionReponses && sectionReponses.etat === SECTION.OK
    && sectionReponses.donnees && sectionReponses.donnees.a_rattacher) || 0;

  /* READ-P1 — LES DEUX COMPTEURS VIENNENT DU SERVEUR, JAMAIS DE LA PAGE.
     La liste est paginée (20 par défaut) : les recompter ici donnerait un badge
     qui change selon la page affichée. Ils survivent donc au rafraîchissement,
     à la reconnexion et à la navigation, parce qu'ils ne dérivent d'aucun état
     de navigateur. */
  const reponsesNonLues = (sectionReponses && sectionReponses.etat === SECTION.OK
    && sectionReponses.donnees && sectionReponses.donnees.non_lues) || 0;
  const reponsesARepondre = (sectionReponses && sectionReponses.etat === SECTION.OK
    && sectionReponses.donnees && sectionReponses.donnees.a_repondre) || 0;
  /* AI-P3 — les cinq états viennent du serveur, dérivés d'une seule règle.
     L'écran ne recompte rien : il afficherait sinon un chiffre qui diverge du
     badge de la carte dès qu'une note change un statut. */
  const compteursEtat = (sectionReponses && sectionReponses.etat === SECTION.OK
    && sectionReponses.donnees) || {};

  /* ---------- READ-P1 + AI-P2 — L'ÉTAT DES CARTES DE RÉPONSE ----------

     UNE SEULE TABLE, INDEXÉE PAR `message.id`, ET C'EST LA RÈGLE CENTRALE.
     Trois partenaires ont répondu le même jour, au même objet, sur la même
     campagne. Une variable unique (`brouillon`, `ouvert`, `edition`…) partagée
     par les cartes ferait apparaître le texte d'ETU-04 sur la carte de LSN-A3 —
     le mélange exact que ce chantier existe pour empêcher. Chaque entrée vaut
     `{ ouvert, brouillon, chargement, erreur, edition, texte }` et ne concerne
     QUE son message.

     LES MISES À JOUR SONT FONCTIONNELLES et ne touchent qu'une clé : reposer
     l'objet entier relancerait les effets qui en dépendent (règle absolue,
     incident V305). */
  const [cartes, setCartes] = useState({});

  const majCarte = useCallback((id, champs) => {
    setCartes((prev) => ({ ...prev, [id]: { ...(prev[id] || {}), ...champs } }));
  }, []);

  const carteDe = useCallback((id) => cartes[id] || {}, [cartes]);

  /* READ-P1 — OUVRIR, C'EST LIRE. Et rien d'autre ne l'est.
     Ce clic est le SEUL chemin qui écrit `read_at`. Ni le chargement de
     l'écran, ni l'ouverture de l'onglet, ni l'analyse IA ne passent par ici.
     Refermer la carte ne « dé-lit » pas : on n'oublie pas ce qu'on a vu.

     LE BROUILLON EXISTANT EST RELU, JAMAIS RÉGÉNÉRÉ. Une régénération
     automatique à chaque ouverture coûterait un appel au modèle par clic et
     écraserait une correction écrite à la main. */
  const ouvrirReponse = useCallback(async (id) => {
    if (!id) return;
    if (carteDe(id).ouvert) { majCarte(id, { ouvert: false }); return; }
    majCarte(id, { ouvert: true });
    try {
      await axios.post(`${base}/prospect-inbound/${encodeURIComponent(id)}/lu`);
      chargement.reessayer('reponses');
    } catch (e) {
      /* La lecture n'a pas pu être enregistrée : la carte s'ouvre quand même.
         Un état de badge n'est jamais une raison de cacher un message. */
    }
    if (carteDe(id).brouillon !== undefined) return;   // déjà chargé une fois
    /* Les deux lectures partent ENSEMBLE : le brouillon et le dossier
       (notes, historique, état commercial) s'affichent dans le même panneau,
       les charger l'un après l'autre ferait clignoter la carte. */
    try {
      const [b, d] = await Promise.all([
        axios.get(`${base}/prospect-inbound/${encodeURIComponent(id)}/brouillon`),
        axios.get(`${base}/prospect-inbound/${encodeURIComponent(id)}/notes`),
      ]);
      majCarte(id, {
        brouillon: (b && b.data && b.data.brouillon) || null,
        notes: (d && d.data && d.data.notes) || [],
        timeline: (d && d.data && d.data.timeline) || [],
        obsolete: !!(d && d.data && d.data.contexte_obsolete),
      });
    } catch (e) {
      majCarte(id, { brouillon: null, notes: [], timeline: [] });
    }
  }, [base, carteDe, majCarte, chargement]);

  /* AI-P3 — LA MÉMOIRE COMMERCIALE. Une note raconte ce qui s'est passé HORS
     des e-mails : un appel, un WhatsApp, une rencontre. Elle est append-only —
     jamais une modification de l'ancienne — et elle NE MARQUE RIEN comme lu :
     noter un appel n'est pas relire le message du partenaire. */
  const ajouterNote = useCallback(async (id) => {
    const carte = carteDe(id);
    const f = carte.formNote || {};
    const texte = (f.texte || '').trim();
    if (!id || !texte || carte.chargement) return;
    majCarte(id, { chargement: true, erreur: '' });
    try {
      const r = await axios.post(
        `${base}/prospect-inbound/${encodeURIComponent(id)}/notes`,
        { type: f.type || 'appel', texte,
          occurred_at: f.date || undefined,
          status_after: f.statut || undefined });
      const d = (r && r.data) || {};
      majCarte(id, {
        chargement: false, noteOuverte: false, formNote: null,
        notes: d.notes || [], timeline: d.timeline || [],
        obsolete: !!d.contexte_obsolete,
      });
      /* Le statut commercial et les compteurs sont RECALCULÉS PAR LE SERVEUR :
         on relit la liste plutôt que de les rejouer ici. Deux règles pour un
         même statut finissent toujours par diverger. */
      chargement.reessayer('reponses');
    } catch (e) {
      const detail = (e && e.response && e.response.data && e.response.data.detail)
        || "La note n'a pas pu être enregistrée.";
      majCarte(id, { chargement: false, erreur: String(detail) });
    }
  }, [base, carteDe, majCarte, chargement]);

  /* AI-P1/P2 — L'ANALYSE. Elle NE MARQUE RIEN comme lu ni traité.
     `ton` vide = première génération ; sinon régénération orientée. */
  const analyserReponse = useCallback(async (id, ton) => {
    if (!id || carteDe(id).chargement) return;
    majCarte(id, { chargement: true, erreur: '' });
    try {
      const r = await axios.post(
        `${base}/prospect-inbound/${encodeURIComponent(id)}/analyser`,
        ton ? { ton } : {});
      const b = (r && r.data && r.data.brouillon) || null;
      /* Régénérer REMPLACE : on referme l'édition en cours, sinon le coach
         croirait corriger un texte qui n'existe plus. */
      /* Le brouillon vient d'être écrit AVEC les notes actuelles : il n'est
         plus périmé. */
      majCarte(id, { brouillon: b, chargement: false, edition: false, texte: '',
                     obsolete: false });
    } catch (e) {
      const detail = (e && e.response && e.response.data && e.response.data.detail)
        || "Analyse IA temporairement indisponible.";
      majCarte(id, { chargement: false, erreur: String(detail) });
    }
  }, [base, carteDe, majCarte]);

  /* AI-P2 — LA CORRECTION À LA MAIN, ENREGISTRÉE.
     Un brouillon dont la correction disparaît au premier repli n'est pas
     modifiable : c'est un piège. Le texte part donc au serveur. */
  const enregistrerBrouillon = useCallback(async (id) => {
    const carte = carteDe(id);
    const texte = (carte.texte || '').trim();
    if (!id || !texte || carte.chargement) return;
    majCarte(id, { chargement: true, erreur: '' });
    try {
      const r = await axios.patch(
        `${base}/prospect-inbound/${encodeURIComponent(id)}/brouillon`,
        { reponse_proposee: texte });
      majCarte(id, { brouillon: (r && r.data && r.data.brouillon) || carte.brouillon,
                     chargement: false, edition: false, texte: '' });
    } catch (e) {
      majCarte(id, { chargement: false,
                     erreur: "La correction n'a pas pu être enregistrée." });
    }
  }, [base, carteDe, majCarte]);

  /* ---------- AI-P4 — VALIDER, PUIS ENVOYER. DEUX GESTES, JAMAIS UN. ----------

     « Valider et envoyer » N'ENVOIE RIEN : il demande au serveur ce qui
     partirait, et affiche cet aperçu. Seul « Confirmer l'envoi » appelle la
     route d'envoi. Un e-mail à un partenaire est irréversible ; un clic de
     trop ne doit pas suffire.

     L'APERÇU VIENT DU SERVEUR, PAS DE L'ÉCRAN. Recalculer ici le destinataire
     ou l'objet créerait une seconde vérité : le jour où elle diverge, le coach
     approuve un texte et un autre part. L'écran affiche ce que le serveur dit
     qu'il ferait — destinataire compris. */
  const preparerEnvoi = useCallback(async (id) => {
    if (!id || carteDe(id).chargement) return;
    majCarte(id, { chargement: true, erreur: '' });
    try {
      const r = await axios.get(`${base}/prospect-inbound/${encodeURIComponent(id)}/apercu-envoi`);
      majCarte(id, { chargement: false, apercu: (r && r.data) || null });
    } catch (e) {
      const detail = (e && e.response && e.response.data && e.response.data.detail)
        || "L'aperçu n'a pas pu être préparé.";
      majCarte(id, { chargement: false, erreur: String(detail) });
    }
  }, [base, carteDe, majCarte]);

  /* L'ENVOI RÉEL. Il porte l'empreinte du texte AFFICHÉ : si le brouillon a
     changé entre l'aperçu et la confirmation, le serveur refuse plutôt que
     d'expédier un autre texte. */
  const confirmerEnvoi = useCallback(async (id) => {
    const carte = carteDe(id);
    const apercu = carte.apercu;
    if (!id || !apercu || carte.chargement) return;
    majCarte(id, { chargement: true, erreur: '' });
    try {
      const r = await axios.post(
        `${base}/prospect-inbound/${encodeURIComponent(id)}/envoyer-reponse`,
        { confirme: true, draft_hash: apercu.draft_hash });
      const d = (r && r.data) || {};
      majCarte(id, { chargement: false, apercu: null,
                     envoye: (d.envoi || {}).send_status || 'envoye' });
      chargement.reessayer('reponses');
    } catch (e) {
      const detail = (e && e.response && e.response.data && e.response.data.detail)
        || "L'envoi n'a pas abouti.";
      majCarte(id, { chargement: false, erreur: String(detail) });
    }
  }, [base, carteDe, majCarte, chargement]);

  /* READ-P1 — « TRAITÉ » EST UNE DÉCISION, JAMAIS UNE DÉDUCTION.
     Lire ne traite pas, analyser ne traite pas. Seul ce clic le fait — et il
     est réversible, parce qu'un état qu'on ne peut pas corriger finit ignoré. */
  const basculerTraite = useCallback(async (id, traite) => {
    if (!id || carteDe(id).chargement) return;
    majCarte(id, { chargement: true, erreur: '' });
    try {
      await axios.post(`${base}/prospect-inbound/${encodeURIComponent(id)}/traite`,
        { traite: !!traite });
      majCarte(id, { chargement: false });
      chargement.reessayer('reponses');
    } catch (e) {
      majCarte(id, { chargement: false,
                     erreur: "L'état n'a pas pu être enregistré." });
    }
  }, [base, carteDe, majCarte, chargement]);

  /* READ-P2 — LA CARTE VISÉE PAR LA NOTIFICATION.
     Le coach a touché une notification : on ouvre CETTE réponse, une seule
     fois, dès qu'elle est chargée. `ouvrirReponse` est le chemin normal — donc
     la lecture est enregistrée exactement comme si le coach avait cliqué
     lui-même, ce qui est le cas : toucher la notification PUIS voir la carte
     EST une lecture. Tant qu'il reste bloqué au login, rien ne s'ouvre et rien
     n'est marqué.

     LA DÉPENDANCE EST L'IDENTIFIANT, une chaîne — jamais la liste `reponses`,
     qui est un tableau neuf à chaque rendu et relancerait l'effet en boucle
     (règle absolue, incident V305). */
  const cibleTrouvee = inboundCible
    && reponses.some((r) => r.id === inboundCible) ? inboundCible : '';
  useEffect(() => {
    if (!cibleTrouvee) return;
    ouvrirReponse(cibleTrouvee);
    if (onCibleConsommee) onCibleConsommee();
    /* Le défilement est un confort, jamais une condition : si l'ancre n'existe
       pas encore, la carte est ouverte de toute façon. */
    try {
      const noeud = document.querySelector('[data-inbound="' + cibleTrouvee + '"]');
      if (noeud && noeud.scrollIntoView) {
        noeud.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    } catch (e) { /* silencieux */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cibleTrouvee]);

  /* Une cible qui ne correspond à AUCUNE réponse chargée n'ouvre rien et ne
     casse rien : l'écran reste utilisable, et on le DIT plutôt que de laisser
     le coach chercher une carte qui n'existe pas (message d'un autre coach,
     réponse supprimée, lien périmé). */
  const cibleIntrouvable = !!inboundCible && !cibleTrouvee
    && sectionReponses && sectionReponses.etat === SECTION.OK;

  const section = chargement.sections.prospects;
  const etat = (section && section.etat) || SECTION.CHARGEMENT;
  const charge = etat === SECTION.OK && section.donnees ? section.donnees : null;

  /* Dérivé de la section, jamais recopié dans un état local : aucun `setState`
     d'objet, donc aucun effet à relancer. */
  const liste = (charge && charge.prospects) || [];
  const compteurs = (charge && charge.counts) || {};
  const total = charge ? charge.total : null;
  const chargeUnFois = etat === SECTION.OK;

  const recharger = useCallback(() => chargement.reessayer('prospects'), [chargement]);

  const majFiltre = (cle, valeur) => {
    setPage(0);
    setFiltres((prec) => (prec[cle] === valeur ? prec : { ...prec, [cle]: valeur }));
  };

  const villes = useMemo(() => {
    const vues = [];
    liste.forEach((p) => {
      if (p.city && vues.indexOf(p.city) === -1) vues.push(p.city);
    });
    return vues.sort();
  }, [liste]);

  const ouvrir = (prospect) => {
    setMessage(null);
    setOuvert(prospect);
    setBrouillon({
      status: prospect.status || 'a_contacter',
      priority: prospect.priority || '',
      wave: prospect.wave || '',
      preferred_channel: prospect.preferred_channel || '',
      collaboration_type: prospect.collaboration_type || '',
      public_email: prospect.public_email || '',
      public_phone: prospect.public_phone || '',
      contact_name: prospect.contact_name || '',
      contact_role: prospect.contact_role || '',
      website: prospect.website || '',
      instagram: prospect.instagram || '',
      notes: prospect.notes || '',
      j0_message: prospect.j0_message || '',
      j3_message: prospect.j3_message || '',
      j7_message: prospect.j7_message || '',
      interested_message: prospect.interested_message || '',
    });
  };

  const fermer = () => {
    setOuvert(null);
    setBrouillon(null);
    setMessage(null);
  };

  const majBrouillon = (cle, valeur) => {
    setBrouillon((prec) => (prec && prec[cle] === valeur ? prec : { ...prec, [cle]: valeur }));
  };

  /* CAL-3 — PLANIFIER. Le rendez-vous part dans le calendrier natif ; la fiche
     prospect n'est PAS modifiée. Planifier un appel n'est pas un événement de
     prospection : c'est une note d'agenda, et le coach reste seul juge de ce
     que la fiche doit dire. */
  const ouvrirPlanification = () => {
    const dans2j = new Date(Date.now() + 2 * 86400000);
    dans2j.setHours(14, 0, 0, 0);
    const p = (n) => String(n).padStart(2, '0');
    setPlanif({
      quand: `${dans2j.getFullYear()}-${p(dans2j.getMonth() + 1)}-${p(dans2j.getDate())}T14:00`,
      duree: 30, type: 'appel', titre: '', google: false,
    });
    setMessage(null);
    setPlanifOuvert(true);
  };

  /* GOOGLE-2 — L'OPTION N'APPARAÎT QUE SI ELLE PEUT ABOUTIR. Proposer une
     case qui échouerait en 403 serait pire que ne rien proposer : on interroge
     donc l'état réel du droit d'écriture, et une erreur laisse simplement
     l'option masquée — la planification, elle, marche toujours. */
  const [googleSync, setGoogleSync] = useState(false);
  useEffect(() => {
    let vivant = true;
    (async () => {
      try {
        const r = await axios.get(`${base}/google/status`);
        const d = (r && r.data) || {};
        if (vivant) setGoogleSync(Boolean(d.connected && d.calendar_write_granted));
      } catch (e) {
        if (vivant) setGoogleSync(false);
      }
    })();
    return () => { vivant = false; };
  }, [base]);

  const planifier = async () => {
    if (!planif.quand) {
      setMessage({ type: 'erreur', texte: 'Une date et une heure sont nécessaires.' });
      return;
    }
    setPlanifEnCours(true); setMessage(null);
    try {
      await axios.post(`${base}/prospect-agenda/${encodeURIComponent(refOuverte)}/appointment`, {
        starts_at: new Date(planif.quand).toISOString(),
        duration_minutes: Number(planif.duree),
        meeting_type: planif.type,
        title: planif.titre.trim() || undefined,
        /* GOOGLE-2, §6 — LE CHOIX EST EXPLICITE, ET IL NE PART QUE S'IL EST
           FAIT. `undefined` plutôt que `false` : on n'envoie pas une intention
           que le coach n'a pas exprimée. Le rendez-vous Afroboost est créé
           dans tous les cas — Google n'est tenté qu'ensuite, côté serveur. */
        google_sync: planif.google ? true : undefined,
      });
      setPlanifOuvert(false);
      await chargerAgenda(refOuverte);
      setMessage({ type: 'ok', texte: 'Rendez-vous planifié.' });
    } catch (e) {
      setMessage({ type: 'erreur', texte: erreurLisible(e, 'Planification refusée par le serveur.') });
    } finally {
      setPlanifEnCours(false);
    }
  };

  const enregistrer = async () => {
    if (!ouvert || !brouillon) return;
    setEnregistrement(true);
    setMessage(null);
    try {
      /* On n'envoie QUE ce qui a changé : un PATCH complet réécrirait des
         champs qu'on n'a pas touchés, et écraserait au passage une
         requalification arrivée entre-temps. */
      const modifs = {};
      Object.keys(brouillon).forEach((cle) => {
        const avant = ouvert[cle] === null || ouvert[cle] === undefined ? '' : ouvert[cle];
        if (String(brouillon[cle]) !== String(avant)) modifs[cle] = brouillon[cle] || null;
      });
      if (!Object.keys(modifs).length) {
        setMessage({ type: 'ok', texte: 'Rien à enregistrer.' });
        setEnregistrement(false);
        return;
      }
      const rep = await axios.patch(`${base}/partner-prospects/${ouvert.id}`, modifs);
      setOuvert(rep && rep.data ? rep.data : ouvert);
      setMessage({ type: 'ok', texte: 'Enregistré.' });
      recharger();
    } catch (err) {
      const detail = err && err.response && err.response.data && err.response.data.detail;
      setMessage({
        type: 'erreur',
        texte: typeof detail === 'string' ? detail : "Enregistrement refusé par le serveur.",
      });
    }
    setEnregistrement(false);
  };

  /* ------------------------------------------------------------------
     P3-S3-B — PREPARER N'ENVOIE RIEN.
     Cet écran ne connaît aucune route d'envoi : il prépare, il montre, il
     laisse exclure ou corriger. Le premier appel est toujours une SIMULATION
     (`dry_run: true`) ; créer la campagne demande un second clic explicite.
     ------------------------------------------------------------------ */
  const corpsPreparation = (simulation, cle) => {
    const corps = { dry_run: simulation };
    if (selection.length) {
      corps.prospect_ids = selection;
    } else {
      Object.keys(filtres).forEach((k) => { if (filtres[k]) corps[k] = filtres[k]; });
    }
    if (cle) corps.idempotency_key = cle;
    return corps;
  };

  const apercuCampagne = async () => {
    setPrepEnCours(true);
    setMessageCampagne(null);
    try {
      const rep = await axios.post(`${base}/prospect-campaigns/prepare`, corpsPreparation(true));
      const d = (rep && rep.data) || {};
      setCampagne(d.campaign ? { ...d.campaign, summary: d.summary, dry_run: true } : null);
      setActions(d.actions || []);
    } catch (err) {
      setCampagne(null);
      setActions([]);
      setMessageCampagne({ type: 'erreur', texte: erreurLisible(err, 'Préparation refusée par le serveur.') });
    }
    setPrepEnCours(false);
  };

  /* La clé d'idempotence est calculée UNE FOIS pour cet aperçu : deux clics sur
     « Créer la campagne » portent donc la même clé, et le serveur rend la
     campagne déjà créée au lieu d'en fabriquer une jumelle. */
  const creerCampagne = async () => {
    if (!campagne || !campagne.dry_run || prepEnCours) return;
    setPrepEnCours(true);
    setMessageCampagne(null);
    try {
      const rep = await axios.post(`${base}/prospect-campaigns/prepare`,
        corpsPreparation(false, campagne.id));
      const d = (rep && rep.data) || {};
      if (d.campaign) {
        const lu = await axios.get(`${base}/prospect-campaigns/${d.campaign.id}`);
        const c = (lu && lu.data) || {};
        setCampagne({ ...(c.campaign || d.campaign), summary: c.summary || d.summary, dry_run: false });
        setActions(c.actions || []);
        setMessageCampagne({
          type: 'ok',
          texte: d.rejeu ? 'Campagne déjà préparée : rien n\'a été recréé.'
                         : 'Campagne préparée. Aucun message n\'a été envoyé.',
        });
      }
    } catch (err) {
      setMessageCampagne({ type: 'erreur', texte: erreurLisible(err, 'Création refusée par le serveur.') });
    }
    setPrepEnCours(false);
  };

  const modifierAction = async (action, modifs) => {
    if (!campagne || campagne.dry_run) return;
    setMessageCampagne(null);
    try {
      const rep = await axios.patch(
        `${base}/prospect-campaigns/${campagne.id}/actions/${action.id}`, modifs);
      const d = (rep && rep.data) || {};
      if (d.action) {
        setActions((prec) => prec.map((a) => (a.id === d.action.id ? d.action : a)));
        if (actionOuverte && actionOuverte.id === d.action.id) setActionOuverte(d.action);
      }
      if (d.summary) setCampagne((prec) => (prec ? { ...prec, summary: d.summary } : prec));
    } catch (err) {
      setMessageCampagne({ type: 'erreur', texte: erreurLisible(err, 'Modification refusée.') });
    }
  };

  /* ROUVRIR : on CHARGE la campagne existante. On n'en prépare pas une autre. */
  const ouvrirCampagne = async (id) => {
    setPrepEnCours(true);
    setMessageCampagne(null);
    try {
      const rep = await axios.get(`${base}/prospect-campaigns/${id}`);
      const d = (rep && rep.data) || {};
      setCampagne({ ...d.campaign, summary: d.summary, dry_run: false });
      setActions(d.actions || []);
    } catch (err) {
      setMessageCampagne({ type: 'erreur', texte: erreurLisible(err, "Campagne illisible.") });
    }
    setPrepEnCours(false);
  };

  /* APPROUVER N'ENVOIE RIEN. La route ne connaît aucun fournisseur, et les
     deux drapeaux d'envoi restent fermés. */
  const approuverCampagne = async () => {
    if (!campagne || campagne.dry_run || campagne.etat !== 'preparee' || prepEnCours) return;
    setPrepEnCours(true);
    setMessageCampagne(null);
    try {
      const rep = await axios.post(`${base}/prospect-campaigns/${campagne.id}/approve`, {});
      const d = (rep && rep.data) || {};
      if (d.campaign) {
        setCampagne({ ...d.campaign, summary: d.summary, dry_run: false });
        setMessageCampagne({
          type: 'ok',
          texte: d.deja_approuvee
            ? 'Campagne déjà approuvée : rien n\'a été refait.'
            : 'Campagne approuvée. Aucun message n\'a été envoyé.',
        });
        chargement.reessayer('campagnes');
      }
    } catch (err) {
      setMessageCampagne({ type: 'erreur', texte: erreurLisible(err, "Approbation refusée.") });
    }
    setPrepEnCours(false);
  };

  const fermerCampagne = () => {
    setCampagne(null);
    setActions([]);
    setActionOuverte(null);
    setMessageCampagne(null);
  };

  const basculerSelection = (identifiant) => {
    setSelection((prec) => (prec.indexOf(identifiant) === -1
      ? prec.concat([identifiant])
      : prec.filter((x) => x !== identifiant)));
  };

  const toutSelectionner = () => {
    const visibles = liste.map((p) => p.id);
    const tousDejaPris = visibles.length > 0 && visibles.every((x) => selection.indexOf(x) !== -1);
    setSelection(tousDejaPris ? [] : visibles);
  };

  const nb = (cle) => (chargeUnFois ? (compteurs[cle] || 0) : '—');
  const resume = (campagne && campagne.summary) || null;

  return (
    <div style={{ padding: '4px 0', color: TEXTE }} data-testid="prospection-section">
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
        <SvgIcon name="compass" size={18} />
        <h2 style={{ fontSize: '18px', fontWeight: 700, margin: 0 }}>Prospection</h2>
      </div>
      <p style={{ fontSize: '12px', opacity: 0.6, margin: '0 0 14px' }}>
        Les organisations à démarcher pour un partenariat. Aucun message n'est envoyé
        depuis cet écran.
      </p>

      {/* ---------- P3-S3-B : PREPARER LA CAMPAGNE ---------- */}
      <div data-testid="bandeau-campagne"
           style={{
             display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '10px',
             padding: '10px 12px', marginBottom: '14px', borderRadius: '10px',
             border: `1px solid rgba(${RGB}, 0.35)`, background: `rgba(${RGB}, 0.08)`,
           }}>
        <span style={{ fontSize: '12px', opacity: 0.85 }}>
          {selection.length
            ? `${selection.length} prospect${selection.length > 1 ? 's' : ''} sélectionné${selection.length > 1 ? 's' : ''}`
            : 'Aucune sélection : la campagne couvrira tous les prospects filtrés.'}
        </span>
        {selection.length > 0 && (
          <button type="button" onClick={() => setSelection([])} data-testid="vider-selection"
                  style={{ ...styleBouton, background: 'transparent', border: '1px solid rgba(255,255,255,0.2)' }}>
            Vider la sélection
          </button>
        )}
        <button type="button" onClick={apercuCampagne} disabled={prepEnCours}
                data-testid="preparer-campagne"
                style={{
                  ...styleBouton, opacity: prepEnCours ? 0.6 : 1, marginLeft: 'auto',
                  /* Quand une campagne est déjà ouverte, « Préparer » devient
                     secondaire : l'action attendue est « Ouvrir ». */
                  ...(campagneOuverte ? { background: 'transparent',
                                          border: '1px solid rgba(255,255,255,0.22)' } : {}),
                }}>
          {prepEnCours ? 'Calcul…' : (campagneOuverte ? 'Préparer une autre campagne' : 'Préparer la campagne')}
        </button>
      </div>

      {/* ---------- P3-S3-C : LA CAMPAGNE DÉJÀ PRÉPARÉE ---------- */}
      {campagneOuverte && !campagne && (
        <div data-testid="campagne-ouverte"
             style={{
               display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '12px',
               padding: '12px 14px', marginBottom: '14px', borderRadius: '10px',
               border: `1px solid rgba(${RGB}, 0.5)`, background: `rgba(${RGB}, 0.14)`,
             }}>
          <div style={{ minWidth: '220px' }}>
            <div style={{ fontSize: '13px', fontWeight: 700 }}>{campagneOuverte.nom}</div>
            <div style={{ fontSize: '12px', opacity: 0.8 }}>
              {campagneOuverte.nb_destinataires} destinataires ·{' '}
              {LIBELLE_ETAT[campagneOuverte.etat] || campagneOuverte.etat} ·{' '}
              créée le {(campagneOuverte.created_at || '').slice(0, 10)} · 0 envoyé
            </div>
          </div>
          <button type="button" onClick={() => ouvrirCampagne(campagneOuverte.id)}
                  disabled={prepEnCours} data-testid="ouvrir-campagne"
                  style={{ ...styleBouton, marginLeft: 'auto' }}>
            Ouvrir
          </button>
        </div>
      )}

      {/* ---------- LES RÉPONSES REÇUES — CARTES COMPACTES (AI-P2) ----------

           CE QUE LA CARTE FERMÉE DOIT DIRE EN TROIS SECONDES, dans cet ordre :
             1. est-ce NOUVEAU ?          2. dois-je encore RÉPONDRE ?
             3. QUI ?                     4. quelle INTENTION ?
             5. le RÉSUMÉ                 6. l'ACTION recommandée
           Et rien d'autre. Le mode de corrélation, la confiance, l'identifiant
           de campagne sont du diagnostic : ils existent toujours, mais dans la
           carte OUVERTE. Les afficher fermés noyait les six lignes utiles.

           TROIS ÉTATS, TROIS QUESTIONS :
             « NOUVEAU »    — jamais OUVERTE     (`read_at` absent)
             « À RÉPONDRE » — jamais AGI dessus  (`traite_at` absent)
             l'INTENTION    — ce que le message demande (vient du brouillon)
           Ouvrir n'est pas répondre : le badge NOUVEAU disparaît à l'ouverture,
           « À RÉPONDRE » reste tant que le coach n'a pas décidé le contraire.

           MOBILE D'ABORD : cartes pleine largeur, `flexWrap` partout, adresse
           tronquée par ellipse plutôt que par débordement. Aucune largeur fixe,
           donc aucun défilement horizontal. */}
      {reponses.length > 0 && (
        <div data-testid="reponses-recues"
             style={{
               padding: '12px 14px', marginBottom: '14px', borderRadius: '10px',
               border: `1px solid rgba(${RGB}, 0.4)`, background: `rgba(${RGB}, 0.10)`,
             }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px',
                        marginBottom: '10px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '13px', fontWeight: 700, color: TEXTE }}>
              Réponses reçues ({reponses.length})
            </span>
            {reponsesNonLues > 0 && (
              <span data-testid="reponses-non-lues"
                    style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '999px',
                             background: `rgba(${RGB}, 0.30)`, color: TEXTE,
                             border: `1px solid rgba(${RGB}, 0.6)`, fontWeight: 700 }}>
                {reponsesNonLues} nouvelle{reponsesNonLues > 1 ? 's' : ''}
              </span>
            )}
            {reponsesARepondre > 0 && (
              <span data-testid="reponses-a-repondre"
                    style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '999px',
                             background: 'rgba(245,158,11,0.22)', color: TEXTE, fontWeight: 600 }}>
                {reponsesARepondre} à répondre
              </span>
            )}
            {reponsesARattacher > 0 && (
              <span data-testid="reponses-en-attente"
                    style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '999px',
                             background: 'rgba(255,255,255,0.10)', color: TEXTE, fontWeight: 600 }}>
                {reponsesARattacher} à rattacher à la main
              </span>
            )}
          </div>

          {/* AI-P3 — LES FILTRES COMMERCIAUX. Ils n'apparaissent que s'il y a
              plus d'un état à trier : sur trois réponses toutes à répondre, une
              barre de filtres serait du décor. Chaque puce porte SON compteur,
              calculé par le serveur — un filtre qui annonce un chiffre faux est
              pire que pas de filtre. */}
          {Object.keys(STATUT_COMMERCIAL).filter((c) => compteursEtat[c] > 0).length > 1 && (
            <div data-testid="filtres-statut"
                 style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '10px' }}>
              {[{ cle: '', libelle: 'Toutes' }].concat(
                Object.keys(STATUT_COMMERCIAL)
                  .filter((c) => compteursEtat[c] > 0)
                  .map((c) => ({ cle: c, libelle: STATUT_COMMERCIAL[c].libelle }))
              ).map((f) => (
                <button key={f.cle || 'toutes'} type="button"
                        data-testid={`filtre-${f.cle || 'toutes'}`}
                        onClick={() => setFiltreStatut(f.cle)}
                        style={{
                          ...stylePetitBouton,
                          fontWeight: filtreStatut === f.cle ? 700 : 500,
                          background: filtreStatut === f.cle
                            ? `rgba(${RGB}, 0.28)` : 'transparent',
                          borderColor: filtreStatut === f.cle
                            ? `rgba(${RGB}, 0.55)` : 'rgba(255,255,255,0.22)',
                        }}>
                  {f.libelle}{f.cle ? ` (${compteursEtat[f.cle]})` : ''}
                </button>
              ))}
            </div>
          )}

          {cibleIntrouvable && (
            <div data-testid="cible-introuvable"
                 style={{ fontSize: '11px', padding: '7px 9px', borderRadius: '7px',
                          background: 'rgba(255,255,255,0.10)', color: TEXTE,
                          marginBottom: '10px' }}>
              La réponse liée à cette notification n’est pas dans cette liste.
              Elle a peut-être été traitée ailleurs.
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {reponses.map((r) => {
              /* Tout ce qui suit est LOCAL à cette carte : aucune de ces
                 variables n'existe hors de l'itération, et tout état persistant
                 est lu dans `cartes[r.id]`. C'est ce qui rend le mélange entre
                 prospects structurellement impossible. */
              const carte = cartes[r.id] || {};
              const nonLue = !r.read_at;
              const statut = r.statut_commercial || 'a_repondre';
              const libelleStatut = STATUT_COMMERCIAL[statut] || STATUT_COMMERCIAL.a_repondre;
              const traitee = statut === 'traite';
              const notes = carte.notes || [];
              const form = carte.formNote || {};
              const deplie = !!carte.ouvert;
              const bro = carte.brouillon || null;
              const occupe = !!carte.chargement;
              return (
                <div key={r.id} data-testid="reponse-ligne" data-inbound={r.id}
                     style={{
                       padding: '10px 12px', borderRadius: '10px',
                       background: nonLue ? `rgba(${RGB}, 0.14)` : 'rgba(255,255,255,0.05)',
                       borderLeft: `3px solid ${nonLue
                         ? `rgba(${RGB}, 0.9)` : 'rgba(255,255,255,0.18)'}`,
                     }}>

                  {/* ---- ligne 1 : les deux badges d'état, rien d'autre ---- */}
                  <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap',
                                alignItems: 'center', marginBottom: '6px' }}>
                    {nonLue && (
                      <span data-testid="badge-nouveau"
                            style={{ fontSize: '10px', fontWeight: 700, letterSpacing: '0.04em',
                                     padding: '2px 8px', borderRadius: '999px', color: TEXTE,
                                     background: `rgba(${RGB}, 0.55)` }}>
                        NOUVEAU
                      </span>
                    )}
                    {/* AI-P3 — L'ÉTAT COMMERCIAL VIENT DU SERVEUR, DÉRIVÉ.
                        L'écran ne le recalcule pas : deux règles pour un même
                        statut finissent toujours par diverger. */}
                    <span data-testid={`badge-statut-${statut}`}
                          style={{ fontSize: '10px', fontWeight: 700, letterSpacing: '0.04em',
                                   padding: '2px 8px', borderRadius: '999px', color: TEXTE,
                                   background: libelleStatut.fond }}>
                      {libelleStatut.libelle}
                    </span>
                    {r.statut !== 'rattache' && (
                      <span data-testid="badge-a-rattacher"
                            style={{ fontSize: '10px', fontWeight: 700, padding: '2px 8px',
                                     borderRadius: '999px', color: TEXTE,
                                     background: 'rgba(255,255,255,0.14)' }}>
                        À RATTACHER
                      </span>
                    )}
                    <span style={{ fontSize: '11px', opacity: 0.55, color: TEXTE,
                                   marginLeft: 'auto' }}>
                      {(r.received_at || '').slice(0, 10)}
                    </span>
                  </div>

                  {/* ---- ligne 2 : QUI. L'organisation d'abord, l'adresse en
                       dessous et tronquée — sur un téléphone, une adresse longue
                       poussait la carte hors de l'écran. ---- */}
                  <div style={{ fontSize: '14px', fontWeight: 700, color: TEXTE,
                                lineHeight: 1.25 }}>
                    {(bro && bro.organisation) || r.recipient_key || 'Prospect à identifier'}
                  </div>
                  <div title={r.from_email}
                       style={{ fontSize: '11px', opacity: 0.7, color: TEXTE,
                                overflow: 'hidden', textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap', maxWidth: '100%' }}>
                    {r.from_email}
                  </div>

                  {/* ---- ligne 3 : ce que ça demande, et ce qu'il faut faire ---- */}
                  {bro ? (
                    <div style={{ marginTop: '7px' }}>
                      <span data-testid="carte-intention"
                            style={{ fontSize: '11px', fontWeight: 700, letterSpacing: '0.04em',
                                     color: PRIMAIRE }}>
                        {LIBELLE_INTENTION[bro.intention] || bro.intention.toUpperCase()}
                      </span>
                      {bro.resume ? (
                        <div data-testid="carte-resume"
                             style={{ fontSize: '12px', color: TEXTE, lineHeight: 1.45,
                                      marginTop: '2px' }}>
                          {bro.resume}
                        </div>
                      ) : null}
                      {!deplie && bro.prochaine_action ? (
                        <div style={{ fontSize: '11px', opacity: 0.75, color: TEXTE,
                                      marginTop: '3px' }}>
                          <strong style={{ opacity: 0.9 }}>À faire :</strong> {bro.prochaine_action}
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    /* Pas encore d'analyse : on montre deux lignes du message
                       réel plutôt qu'une carte muette — et on ne lance AUCUN
                       appel au modèle tant que personne ne l'a demandé. */
                    <div data-testid="carte-sans-analyse"
                         style={{ fontSize: '12px', opacity: 0.7, color: TEXTE,
                                  marginTop: '7px', lineHeight: 1.4,
                                  display: '-webkit-box', WebkitLineClamp: 2,
                                  WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                      {(r.body_text || '').slice(0, 160) || 'Aucun contenu lisible.'}
                    </div>
                  )}

                  {/* ---- ligne 4 : l'action ---- */}
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap',
                                alignItems: 'center', marginTop: '9px' }}>
                    <button type="button" data-testid="voir-reponse"
                            onClick={() => ouvrirReponse(r.id)}
                            style={{ ...stylePetitBouton, fontWeight: 600 }}>
                      {deplie ? 'Replier' : 'Voir la réponse'}
                    </button>
                    {deplie && (
                      <button type="button" data-testid="basculer-traite"
                              onClick={() => basculerTraite(r.id, !traitee)}
                              disabled={occupe}
                              style={{ ...stylePetitBouton, opacity: occupe ? 0.6 : 1 }}>
                        {traitee ? 'Remettre à répondre' : 'Marquer comme traité'}
                      </button>
                    )}
                  </div>

                  {/* ================= LE DÉTAIL ================= */}
                  {deplie && (
                    <div style={{ marginTop: '10px', paddingTop: '10px',
                                  borderTop: '1px solid rgba(255,255,255,0.12)' }}>

                      {carte.erreur ? (
                        <div data-testid="erreur-ia"
                             style={{ fontSize: '11px', marginBottom: '8px', padding: '7px 9px',
                                      borderRadius: '6px', color: TEXTE,
                                      background: 'rgba(239,68,68,0.18)' }}>
                          {carte.erreur}
                        </div>
                      ) : null}

                      {/* ---- ANALYSE IA ---- */}
                      {bro ? (
                        <div data-testid="analyse-ia" style={{ marginBottom: '10px' }}>
                          <div style={{ fontSize: '10px', fontWeight: 700, opacity: 0.65,
                                        color: TEXTE, letterSpacing: '0.05em',
                                        marginBottom: '5px' }}>
                            ANALYSE IA
                          </div>
                          {bro.validation_requise && (
                            <div data-testid="validation-bassi"
                                 style={{ display: 'flex', gap: '6px', alignItems: 'center',
                                          fontSize: '11px', fontWeight: 700, color: TEXTE,
                                          padding: '6px 8px', borderRadius: '6px',
                                          background: 'rgba(245,158,11,0.25)', marginBottom: '7px',
                                          flexWrap: 'wrap' }}>
                              <SvgIcon name="warning" size={13} />
                              VALIDATION BASSI NÉCESSAIRE — {bro.motifs_validation.join(', ')}
                            </div>
                          )}
                          {bro.demande ? (
                            <div style={{ fontSize: '12px', color: TEXTE, marginBottom: '3px',
                                          lineHeight: 1.45 }}>
                              <strong>Ce qu’il demande :</strong> {bro.demande}
                            </div>
                          ) : null}
                          {bro.prochaine_action ? (
                            <div style={{ fontSize: '12px', color: TEXTE, lineHeight: 1.45 }}>
                              <strong>Action recommandée :</strong> {bro.prochaine_action}
                            </div>
                          ) : null}
                        </div>
                      ) : null}

                      {/* ---- RÉPONSE PROPOSÉE ---- */}
                      {/* AI-P3 — UN BROUILLON PÉRIMÉ SE SIGNALE, IL NE SE
                          RÉÉCRIT PAS TOUT SEUL. Une note ajoutée après sa
                          rédaction change les faits : le régénérer sans
                          demander effacerait une correction manuelle et
                          coûterait un appel au modèle que personne n'a
                          demandé. C'est une comparaison de DATES, jamais une
                          lecture du texte. */}
                      {bro && carte.obsolete && !carte.edition ? (
                        <div data-testid="contexte-obsolete"
                             style={{ fontSize: '11px', padding: '7px 9px', borderRadius: '7px',
                                      background: 'rgba(245,158,11,0.22)', color: TEXTE,
                                      marginBottom: '7px', display: 'flex', gap: '8px',
                                      alignItems: 'center', flexWrap: 'wrap' }}>
                          <SvgIcon name="warning" size={13} />
                          <span style={{ flex: 1, minWidth: '160px' }}>
                            Le contexte a changé depuis la génération de cette réponse.
                          </span>
                          <button type="button" data-testid="regenerer-contexte"
                                  onClick={() => analyserReponse(r.id, '')}
                                  disabled={occupe}
                                  style={{ ...stylePetitBouton, fontWeight: 600,
                                           opacity: occupe ? 0.6 : 1 }}>
                            Régénérer avec les nouvelles informations
                          </button>
                        </div>
                      ) : null}
                      <div style={{ fontSize: '10px', fontWeight: 700, opacity: 0.65,
                                    color: TEXTE, letterSpacing: '0.05em', marginBottom: '5px' }}>
                        {bro ? `RÉPONSE PROPOSÉE POUR ${bro.to_email}` : 'RÉPONSE PROPOSÉE'}
                      </div>

                      {bro && carte.edition ? (
                        <>
                          <textarea
                            data-testid="editeur-brouillon"
                            value={carte.texte}
                            onChange={(e) => majCarte(r.id, { texte: e.target.value })}
                            rows={9}
                            style={{
                              width: '100%', boxSizing: 'border-box', fontSize: '12px',
                              lineHeight: 1.5, color: TEXTE, padding: '9px 10px',
                              borderRadius: '8px', background: 'rgba(0,0,0,0.32)',
                              border: `1px solid rgba(${RGB}, 0.45)`, resize: 'vertical',
                              fontFamily: 'inherit',
                            }} />
                          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap',
                                        marginTop: '7px' }}>
                            <button type="button" data-testid="enregistrer-brouillon"
                                    onClick={() => enregistrerBrouillon(r.id)}
                                    disabled={occupe || !(carte.texte || '').trim()}
                                    style={{ ...styleBouton,
                                             opacity: occupe || !(carte.texte || '').trim() ? 0.6 : 1 }}>
                              {occupe ? 'Enregistrement…' : 'Enregistrer'}
                            </button>
                            <button type="button" data-testid="annuler-edition"
                                    onClick={() => majCarte(r.id, { edition: false, texte: '' })}
                                    style={stylePetitBouton}>
                              Annuler
                            </button>
                          </div>
                        </>
                      ) : bro ? (
                        <div data-testid="reponse-proposee"
                             style={{ fontSize: '12px', whiteSpace: 'pre-wrap', color: TEXTE,
                                      lineHeight: 1.5, padding: '9px 10px', borderRadius: '8px',
                                      background: 'rgba(0,0,0,0.25)',
                                      border: `1px solid rgba(${RGB}, 0.35)` }}>
                          {bro.reponse_proposee}
                        </div>
                      ) : (
                        <div style={{ fontSize: '12px', opacity: 0.75, color: TEXTE }}>
                          Aucune réponse n'a encore été préparée pour ce partenaire.
                        </div>
                      )}

                      {/* ---- les commandes ---- */}
                      {!carte.edition && (
                        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap',
                                      alignItems: 'center', marginTop: '8px' }}>
                          <button type="button" data-testid="analyser-ia"
                                  onClick={() => analyserReponse(r.id, '')}
                                  disabled={occupe}
                                  style={{ ...styleBouton, opacity: occupe ? 0.6 : 1 }}>
                            {occupe ? 'Analyse en cours…'
                              : (bro ? 'Régénérer' : "Générer une réponse avec l’IA")}
                          </button>
                          {bro && !occupe && (
                            <button type="button" data-testid="modifier-brouillon"
                                    onClick={() => majCarte(r.id, {
                                      edition: true, texte: bro.reponse_proposee || '' })}
                                    style={stylePetitBouton}>
                              Modifier
                            </button>
                          )}
                          {/* AI-P4 — « VALIDER ET ENVOYER » N'ENVOIE PAS.
                              Il ouvre l'aperçu. Seul « Confirmer l'envoi »
                              expédie — un e-mail à un partenaire est
                              irréversible, un clic de trop ne doit pas
                              suffire. */}
                          {bro && (
                            <button type="button" data-testid="valider-envoyer"
                                    onClick={() => preparerEnvoi(r.id)}
                                    disabled={occupe}
                                    style={{ ...stylePetitBouton, fontWeight: 600,
                                             opacity: occupe ? 0.6 : 1 }}>
                              Valider et envoyer
                            </button>
                          )}
                        </div>
                      )}

                      {/* ============ AI-P4 : L'ÉCRAN DE CONFIRMATION ============
                          Compact, dans la carte — pas une modale pleine page.
                          Il montre EXACTEMENT ce qui partirait, tel que le
                          serveur l'a calculé : organisation, destinataire,
                          objet, texte final. */}
                      {carte.apercu && (
                        <div data-testid="confirmation-envoi"
                             style={{ marginTop: '10px', padding: '11px',
                                      borderRadius: '9px',
                                      background: 'rgba(0,0,0,0.30)',
                                      border: `1px solid rgba(${RGB}, 0.5)` }}>
                          <div style={{ fontSize: '10px', fontWeight: 700, opacity: 0.7,
                                        color: TEXTE, letterSpacing: '0.05em',
                                        marginBottom: '7px' }}>
                            AVANT D’ENVOYER — VÉRIFIEZ
                          </div>
                          {carte.apercu.validation_requise && (
                            <div data-testid="confirmation-validation"
                                 style={{ fontSize: '11px', fontWeight: 700, color: TEXTE,
                                          padding: '6px 8px', borderRadius: '6px',
                                          background: 'rgba(245,158,11,0.28)',
                                          marginBottom: '7px' }}>
                              VALIDATION BASSI NÉCESSAIRE — {(carte.apercu.motifs_validation || []).join(', ')}
                            </div>
                          )}
                          {[['Organisation', carte.apercu.organisation],
                            ['Destinataire', carte.apercu.destinataire],
                            ['Objet', carte.apercu.objet],
                            ['État du dossier',
                             (STATUT_COMMERCIAL[carte.apercu.statut_commercial]
                              || STATUT_COMMERCIAL.a_repondre).libelle]].map(([cle, val]) => (
                            <div key={cle} style={{ fontSize: '11px', color: TEXTE,
                                                    marginBottom: '2px', wordBreak: 'break-word' }}>
                              <span style={{ opacity: 0.65 }}>{cle} : </span>
                              <strong data-testid={`apercu-${cle.split(' ')[0].toLowerCase()}`}>
                                {val || '—'}
                              </strong>
                            </div>
                          ))}
                          <div data-testid="apercu-texte"
                               style={{ fontSize: '12px', whiteSpace: 'pre-wrap', color: TEXTE,
                                        lineHeight: 1.5, marginTop: '7px', padding: '8px 9px',
                                        borderRadius: '7px', background: 'rgba(0,0,0,0.30)' }}>
                            {carte.apercu.texte}
                          </div>
                          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap',
                                        marginTop: '9px', alignItems: 'center' }}>
                            {/* LE BOUTON N'EST ACTIF QUE SI L'ENVOI L'EST VRAIMENT.
                                Un bouton qui a l'air cliquable et qui refuse est
                                pire qu'un bouton désactivé qui dit pourquoi. */}
                            <button type="button" data-testid="confirmer-envoi"
                                    onClick={() => confirmerEnvoi(r.id)}
                                    disabled={occupe || !carte.apercu.envoi_possible
                                              || carte.apercu.contexte_obsolete
                                              || carte.apercu.deja_envoye}
                                    style={{ ...styleBouton,
                                             opacity: (occupe || !carte.apercu.envoi_possible
                                                       || carte.apercu.contexte_obsolete
                                                       || carte.apercu.deja_envoye) ? 0.5 : 1,
                                             cursor: carte.apercu.envoi_possible ? 'pointer' : 'not-allowed' }}>
                              {occupe ? 'Envoi…' : 'Confirmer l’envoi'}
                            </button>
                            <button type="button" data-testid="annuler-envoi"
                                    onClick={() => majCarte(r.id, { apercu: null })}
                                    style={stylePetitBouton}>
                              Annuler
                            </button>
                            {!carte.apercu.envoi_possible && (
                              <span data-testid="envoi-non-active"
                                    style={{ fontSize: '11px', opacity: 0.7, color: TEXTE }}>
                                Envoi non activé
                              </span>
                            )}
                            {carte.apercu.deja_envoye && (
                              <span data-testid="deja-envoye"
                                    style={{ fontSize: '11px', opacity: 0.7, color: TEXTE }}>
                                Déjà envoyé
                              </span>
                            )}
                            {carte.apercu.contexte_obsolete && (
                              <span data-testid="envoi-bloque-contexte"
                                    style={{ fontSize: '11px', opacity: 0.8, color: TEXTE }}>
                                Le contexte a changé — régénérez avant d’envoyer.
                              </span>
                            )}
                            {carte.apercu.fil_rattache && (
                              <span style={{ fontSize: '10px', opacity: 0.55, color: TEXTE }}>
                                rattaché au fil d’origine
                              </span>
                            )}
                          </div>
                        </div>
                      )}

                      {carte.envoye && (
                        <div data-testid="envoi-reussi"
                             style={{ fontSize: '11px', marginTop: '8px', padding: '7px 9px',
                                      borderRadius: '7px', color: TEXTE,
                                      background: 'rgba(34,197,94,0.20)' }}>
                          Réponse envoyée.
                        </div>
                      )}

                      {bro && !carte.edition && !occupe && (
                        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap',
                                      marginTop: '7px', alignItems: 'center' }}>
                          <span style={{ fontSize: '10px', opacity: 0.6, color: TEXTE }}>
                            Régénérer en :
                          </span>
                          {TONS_IA.map((t) => (
                            <button key={t.cle} type="button" data-testid={`ton-${t.cle}`}
                                    onClick={() => analyserReponse(r.id, t.cle)}
                                    style={stylePetitBouton}>
                              {t.libelle}
                            </button>
                          ))}
                        </div>
                      )}


                      {/* ================= AI-P3 : L'HISTORIQUE ================= */}
                      {/* UNE CHRONOLOGIE VERTICALE, PAS UN TABLEAU. Sur un
                          téléphone un tableau déborde ; une colonne de lignes
                          datées se lit partout. On n'y met QUE ce qu'un humain
                          comprend : ni identifiant Mongo, ni action_id, ni
                          jeton de réponse, ni score de corrélation. */}
                      {(carte.timeline || []).length > 0 && (
                        <div data-testid="historique" style={{ marginTop: '12px' }}>
                          <div style={{ fontSize: '10px', fontWeight: 700, opacity: 0.65,
                                        color: TEXTE, letterSpacing: '0.05em',
                                        marginBottom: '6px' }}>
                            HISTORIQUE
                          </div>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px',
                                        borderLeft: `2px solid rgba(${RGB}, 0.35)`,
                                        paddingLeft: '10px' }}>
                            {(carte.timeline || []).map((e, i) => (
                              <div key={i} data-testid="historique-ligne"
                                   style={{ fontSize: '11px', color: TEXTE,
                                            opacity: e.annulee ? 0.45 : 1,
                                            textDecoration: e.annulee ? 'line-through' : 'none' }}>
                                <span style={{ opacity: 0.65 }}>
                                  {e.quand ? String(e.quand).slice(0, 10) : 'Maintenant'}
                                </span>
                                {' · '}
                                <strong>{e.titre}</strong>
                                {e.genre === 'statut' && e.statut ? (
                                  <span style={{ marginLeft: '6px', fontWeight: 700,
                                                 color: PRIMAIRE }}>
                                    {(STATUT_COMMERCIAL[e.statut]
                                      || STATUT_COMMERCIAL.a_repondre).libelle}
                                  </span>
                                ) : null}
                                {e.texte ? (
                                  <div style={{ opacity: 0.85, marginTop: '1px',
                                                whiteSpace: 'pre-wrap' }}>
                                    {e.texte}
                                  </div>
                                ) : null}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* ================= AI-P3 : AJOUTER UNE NOTE ================= */}
                      {/* UN FORMULAIRE INTÉGRÉ, JAMAIS UNE MODALE. Le coach note
                          un appel en trois secondes, sans quitter la carte ni
                          perdre de vue ce qu'il vient de lire. */}
                      {!carte.noteOuverte ? (
                        <div style={{ marginTop: '10px' }}>
                          <button type="button" data-testid="ouvrir-note"
                                  onClick={() => majCarte(r.id, {
                                    noteOuverte: true,
                                    formNote: { type: 'appel', texte: '', statut: '',
                                                date: new Date().toISOString().slice(0, 10) } })}
                                  style={stylePetitBouton}>
                            Ajouter une note
                          </button>
                        </div>
                      ) : (
                        <div data-testid="formulaire-note"
                             style={{ marginTop: '10px', padding: '10px', borderRadius: '8px',
                                      background: 'rgba(0,0,0,0.22)',
                                      border: '1px solid rgba(255,255,255,0.14)' }}>
                          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap',
                                        marginBottom: '7px' }}>
                            <label style={{ fontSize: '11px', color: TEXTE, opacity: 0.8 }}>
                              Type
                              <select data-testid="note-type" value={form.type || 'appel'}
                                      onChange={(ev) => majCarte(r.id, {
                                        formNote: { ...form, type: ev.target.value } })}
                                      style={{ display: 'block', marginTop: '2px',
                                               fontSize: '12px', padding: '5px 7px',
                                               borderRadius: '6px', color: TEXTE,
                                               background: 'rgba(0,0,0,0.35)',
                                               border: '1px solid rgba(255,255,255,0.2)' }}>
                                {TYPES_NOTE.map((t) => (
                                  <option key={t.cle} value={t.cle}>{t.libelle}</option>
                                ))}
                              </select>
                            </label>
                            <label style={{ fontSize: '11px', color: TEXTE, opacity: 0.8 }}>
                              Date
                              <input type="date" data-testid="note-date" value={form.date || ''}
                                     onChange={(ev) => majCarte(r.id, {
                                       formNote: { ...form, date: ev.target.value } })}
                                     style={{ display: 'block', marginTop: '2px',
                                              fontSize: '12px', padding: '5px 7px',
                                              borderRadius: '6px', color: TEXTE,
                                              background: 'rgba(0,0,0,0.35)',
                                              border: '1px solid rgba(255,255,255,0.2)' }} />
                            </label>
                            <label style={{ fontSize: '11px', color: TEXTE, opacity: 0.8 }}>
                              État après cette action
                              {/* LE STATUT EST DÉCLARÉ, JAMAIS DEVINÉ DANS LE
                                  TEXTE. « J'attends sa proposition » et « je
                                  dois le rappeler » se ressemblent trop pour
                                  qu'une machine tranche. */}
                              <select data-testid="note-statut" value={form.statut || ''}
                                      onChange={(ev) => majCarte(r.id, {
                                        formNote: { ...form, statut: ev.target.value } })}
                                      style={{ display: 'block', marginTop: '2px',
                                               fontSize: '12px', padding: '5px 7px',
                                               borderRadius: '6px', color: TEXTE,
                                               background: 'rgba(0,0,0,0.35)',
                                               border: '1px solid rgba(255,255,255,0.2)' }}>
                                <option value="">— inchangé —</option>
                                {Object.keys(STATUT_COMMERCIAL).map((cle) => (
                                  <option key={cle} value={cle}>
                                    {STATUT_COMMERCIAL[cle].libelle}
                                  </option>
                                ))}
                              </select>
                            </label>
                          </div>
                          <textarea data-testid="note-texte" rows={3}
                                    value={form.texte || ''}
                                    placeholder="Ce qui s'est passé : appel, rencontre, information…"
                                    onChange={(ev) => majCarte(r.id, {
                                      formNote: { ...form, texte: ev.target.value } })}
                                    style={{ width: '100%', boxSizing: 'border-box',
                                             fontSize: '12px', lineHeight: 1.5, color: TEXTE,
                                             padding: '8px 9px', borderRadius: '7px',
                                             background: 'rgba(0,0,0,0.32)',
                                             border: '1px solid rgba(255,255,255,0.2)',
                                             resize: 'vertical', fontFamily: 'inherit' }} />
                          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap',
                                        marginTop: '7px' }}>
                            <button type="button" data-testid="enregistrer-note"
                                    onClick={() => ajouterNote(r.id)}
                                    disabled={occupe || !(form.texte || '').trim()}
                                    style={{ ...styleBouton,
                                             opacity: occupe || !(form.texte || '').trim()
                                               ? 0.6 : 1 }}>
                              {occupe ? 'Enregistrement…' : 'Enregistrer la note'}
                            </button>
                            <button type="button" data-testid="annuler-note"
                                    onClick={() => majCarte(r.id, {
                                      noteOuverte: false, formNote: null })}
                                    style={stylePetitBouton}>
                              Annuler
                            </button>
                          </div>
                        </div>
                      )}

                      {/* ---- L'EMAIL ORIGINAL, REPLIÉ PAR DÉFAUT ----
                           Il reste accessible — c'est la seule source de vérité
                           du message reçu — mais il ne s'impose plus. */}
                      <details data-testid="email-original" style={{ marginTop: '11px' }}>
                        <summary style={{ fontSize: '11px', cursor: 'pointer', opacity: 0.8,
                                          color: TEXTE }}>
                          Voir l’email original
                        </summary>
                        <div style={{ fontSize: '11px', opacity: 0.6, color: TEXTE,
                                      marginTop: '5px' }}>
                          {r.subject}
                        </div>
                        {/* Du TEXTE, jamais du HTML : on n'injecte pas le
                            contenu d'un inconnu dans la page. */}
                        <div data-testid="corps-original"
                             style={{ fontSize: '12px', whiteSpace: 'pre-wrap', color: TEXTE,
                                      lineHeight: 1.5, marginTop: '4px' }}>
                          {r.body_text || '(aucun contenu lisible pour cette réponse)'}
                        </div>
                        {/* L'historique cité reste SÉPARÉ du nouveau texte :
                            c'est la coupure faite par P3-R4, on ne la recolle pas. */}
                        {r.body_quoted ? (
                          <details style={{ marginTop: '6px' }}>
                            <summary style={{ fontSize: '11px', cursor: 'pointer',
                                              opacity: 0.6, color: TEXTE }}>
                              Historique cité
                            </summary>
                            <div style={{ fontSize: '11px', whiteSpace: 'pre-wrap',
                                          opacity: 0.6, color: TEXTE, marginTop: '4px' }}>
                              {r.body_quoted}
                            </div>
                          </details>
                        ) : null}
                        {/* Le diagnostic de corrélation vit ICI, pas sur la
                            carte fermée : utile quand quelque chose cloche,
                            illisible quand tout va bien. */}
                        <div style={{ fontSize: '10px', opacity: 0.5, color: TEXTE,
                                      marginTop: '7px' }}>
                          {r.statut === 'rattache'
                            ? `rattaché — ${r.matching_method} (confiance ${r.matching_confidence})`
                            : `à rattacher — ${r.motif || 'ambigu'}`}
                          {r.campaign_id ? ` · campagne ${String(r.campaign_id).slice(0, 8)}` : ''}
                        </div>
                      </details>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {messageCampagne && (
        <div data-testid="message-campagne"
             style={{
               fontSize: '12px', padding: '8px 10px', borderRadius: '8px', marginBottom: '12px',
               background: messageCampagne.type === 'ok' ? 'rgba(34,197,94,0.14)' : 'rgba(239,68,68,0.16)',
             }}>
          {messageCampagne.texte}
        </div>
      )}

      {campagne && (
        <div data-testid="panneau-campagne"
             style={{
               marginBottom: '16px', padding: '14px', borderRadius: '12px',
               border: '1px solid rgba(255,255,255,0.14)', background: 'rgba(0,0,0,0.22)',
             }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '10px' }}>
            <strong style={{ fontSize: '14px' }}>{campagne.nom}</strong>
            <Etiquette
              texte={campagne.dry_run
                ? 'Aperçu — rien n\'est enregistré'
                : (LIBELLE_ETAT[campagne.etat] || campagne.etat)}
              ton="primaire" />
            {campagne.approved_at && (
              <span data-testid="envoi-desactive" style={{ fontSize: '12px', opacity: 0.85 }}>
                Envoi désactivé — aucun message ne peut partir
              </span>
            )}
            <button type="button" onClick={fermerCampagne} data-testid="fermer-campagne"
                    style={{ ...styleBouton, background: 'transparent', border: '1px solid rgba(255,255,255,0.2)', marginLeft: 'auto' }}>
              Fermer
            </button>
          </div>

          {resume && (
            <>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '10px' }}
                   data-testid="resume-campagne">
                <Tuile libelle="Fiches" valeur={resume.fiches} />
                <Tuile libelle="Destinataires" valeur={resume.destinataires} actif />
                {['AUTO', 'ASSISTE', 'MANUEL', 'BLOQUE'].map((k) => (
                  <Tuile key={k} libelle={LIBELLE_EXECUTION[k]} valeur={resume.par_execution[k] || 0} />
                ))}
                {resume.exclus > 0 && <Tuile libelle="Exclus" valeur={resume.exclus} />}
              </div>
              <div style={{ fontSize: '12px', opacity: 0.75, marginBottom: '4px' }} data-testid="resume-canaux">
                <strong>Par canal :</strong>{' '}
                {Object.keys(resume.par_canal).map((c) => `${LIBELLE_CANAL[c] || c} ${resume.par_canal[c]}`).join(' · ')}
              </div>
              <div style={{ fontSize: '12px', opacity: 0.75, marginBottom: '10px' }} data-testid="resume-langues">
                <strong>Par langue :</strong>{' '}
                {Object.keys(resume.par_langue).map((l) => `${l} ${resume.par_langue[l]}`).join(' · ')}
                {resume.sans_message_j0 > 0
                  ? ` — ${resume.sans_message_j0} sans message J0`
                  : ''}
              </div>
            </>
          )}

          {campagne.dry_run && (
            <button type="button" onClick={creerCampagne} disabled={prepEnCours}
                    data-testid="creer-campagne" style={{ ...styleBouton, marginBottom: '10px' }}>
              Créer la campagne préparée
            </button>
          )}

          {/* APPROUVER N'ENVOIE RIEN : la route ne connaît aucun fournisseur. */}
          {!campagne.dry_run && campagne.etat === 'preparee' && (
            <button type="button" onClick={approuverCampagne} disabled={prepEnCours}
                    data-testid="approuver-campagne" style={{ ...styleBouton, marginBottom: '10px' }}>
              Approuver la campagne
            </button>
          )}

          {/* Le filtre de l'aperçu : voir les cas à traiter AVANT toute activation. */}
          {!campagne.dry_run && (
            <div style={{ display: 'flex', gap: '8px', marginBottom: '10px', flexWrap: 'wrap' }}>
              {[['', 'Tous'], ['sans_langue', `Langue non précisée (${actions.filter((a) => !(a.language || '').trim()).length})`],
                ['sans_message', `Sans message J0 (${actions.filter((a) => !(a.message_j0 || '').trim()).length})`],
                ['exclus', `Exclus (${actions.filter((a) => a.statut === 'exclu').length})`]].map(([cle, libelle]) => (
                <button key={cle || 'tous'} type="button" onClick={() => setFiltreApercu(cle)}
                        data-testid={`filtre-apercu-${cle || 'tous'}`}
                        style={{
                          ...stylePetitBouton,
                          background: filtreApercu === cle ? `rgba(${RGB}, 0.28)` : 'transparent',
                          borderColor: filtreApercu === cle ? PRIMAIRE : 'rgba(255,255,255,0.22)',
                        }}>
                  {libelle}
                </button>
              ))}
            </div>
          )}

          {/* L'APERCU COMPACT : on ne doit pas ouvrir 137 fiches une par une. */}
          <div style={{ overflowX: 'auto', maxHeight: '420px', overflowY: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
              <thead>
                <tr style={{ textAlign: 'left', opacity: 0.6, fontSize: '11px' }}>
                  {['Organisation', 'Ville', 'Canal', 'Langue', 'Exécution', 'Message J0', 'État', ''].map((h, i) => (
                    <th key={`${h}-${i}`} style={{ padding: '5px 8px', whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {actions.filter((a) => (
                  filtreApercu === 'sans_langue' ? !(a.language || '').trim()
                    : filtreApercu === 'sans_message' ? !(a.message_j0 || '').trim()
                      : filtreApercu === 'exclus' ? a.statut === 'exclu'
                        : true
                )).map((a) => (
                  <tr key={a.id} data-testid={`action-${a.recipient_key}`}
                      style={{
                        borderTop: '1px solid rgba(255,255,255,0.06)',
                        opacity: a.statut === 'exclu' ? 0.55 : 1,
                      }}>
                    <td style={{ padding: '6px 8px', fontWeight: 600 }}>
                      {a.organisations.join(' + ')}
                      <span style={{ opacity: 0.55, fontSize: '11px' }}> · {a.prospect_ids.join(', ')}</span>
                    </td>
                    <td style={{ padding: '6px 8px' }}>{ou(a.cities.filter(Boolean).join(' / '))}</td>
                    <td style={{ padding: '6px 8px' }}>{LIBELLE_CANAL[a.channel] || a.channel}</td>
                    <td style={{ padding: '6px 8px' }}>{ou(a.language)}</td>
                    <td style={{ padding: '6px 8px' }}>
                      <Etiquette texte={LIBELLE_EXECUTION[a.execution_type] || a.execution_type}
                                 ton={a.execution_type === 'AUTO' ? 'primaire' : 'neutre'} />
                    </td>
                    <td style={{ padding: '6px 8px', maxWidth: '260px' }}>
                      {a.message_j0
                        ? `${a.message_j0.slice(0, 90)}${a.message_j0.length > 90 ? '…' : ''}`
                        : <span style={{ opacity: 0.5 }}>aucun message</span>}
                    </td>
                    <td style={{ padding: '6px 8px' }}>{LIBELLE_STATUT_ACTION[a.statut] || a.statut}</td>
                    <td style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>
                      {/* Après approbation, le snapshot est FIGÉ : plus aucun
                          bouton d'édition. Le serveur refuse déjà (409) — on
                          ne laisse pas non plus l'interface le proposer. */}
                      {!campagne.dry_run && campagne.etat === 'preparee' && (
                        <>
                          <button type="button" data-testid={`ouvrir-action-${a.recipient_key}`}
                                  onClick={() => setActionOuverte(a)}
                                  style={{ ...stylePetitBouton }}>Modifier</button>
                          <button type="button" data-testid={`exclure-${a.recipient_key}`}
                                  onClick={() => modifierAction(a, { excluded: a.statut !== 'exclu' })}
                                  style={{ ...stylePetitBouton, marginLeft: '6px' }}>
                            {a.statut === 'exclu' ? 'Réintégrer' : 'Exclure'}
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {actionOuverte && (
            <div data-testid="edition-action"
                 style={{ marginTop: '12px', padding: '12px', borderRadius: '10px',
                          border: `1px solid rgba(${RGB}, 0.35)` }}>
              <div style={{ fontSize: '12px', opacity: 0.7, marginBottom: '8px' }}>
                Ces corrections ne touchent que cette campagne — la fiche prospect
                reste telle quelle.
              </div>
              <Champ libelle="Canal">
                <select value={actionOuverte.channel} data-testid="action-canal" style={styleChamp}
                        onChange={(e) => modifierAction(actionOuverte, { channel: e.target.value })}>
                  {Object.keys(LIBELLE_CANAL).map((c) => (
                    <option key={c} value={c}>{LIBELLE_CANAL[c]}</option>
                  ))}
                </select>
              </Champ>
              <Champ libelle="Message J0">
                <textarea defaultValue={actionOuverte.message_j0 || ''} rows={5}
                          data-testid="action-message" style={{ ...styleChamp, width: '100%' }}
                          onBlur={(e) => modifierAction(actionOuverte, { message_j0: e.target.value })} />
              </Champ>
              <button type="button" onClick={() => setActionOuverte(null)}
                      data-testid="fermer-edition-action"
                      style={{ ...styleBouton, background: 'transparent', border: '1px solid rgba(255,255,255,0.2)' }}>
                Fermer
              </button>
            </div>
          )}
        </div>
      )}

      {/* ---------- LES COMPTEURS ---------- */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '14px' }}>
        <Tuile libelle="Total" valeur={nb('total')} actif={!filtres.status}
               onClick={() => majFiltre('status', '')} />
        {STATUTS.map((s) => (
          <Tuile
            key={s.cle}
            libelle={s.libelle}
            valeur={nb(s.cle)}
            actif={filtres.status === s.cle}
            onClick={() => majFiltre('status', filtres.status === s.cle ? '' : s.cle)}
          />
        ))}
        <Tuile libelle="Candidatures" valeur={nb('candidature')} />
        <Tuile libelle="Acceptés" valeur={nb('accepte')} />
      </div>

      {/* ---------- LES FILTRES ---------- */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '12px' }}>
        <select value={filtres.category} onChange={(e) => majFiltre('category', e.target.value)}
                aria-label="Catégorie" data-testid="filtre-category" style={styleChamp}>
          <option value="">Toutes les catégories</option>
          {CATEGORIES.map((c) => <option key={c.cle} value={c.cle}>{c.libelle}</option>)}
        </select>
        <select value={filtres.status} onChange={(e) => majFiltre('status', e.target.value)}
                aria-label="Statut" data-testid="filtre-status" style={styleChamp}>
          <option value="">Tous les statuts</option>
          {STATUTS.map((s) => <option key={s.cle} value={s.cle}>{s.libelle}</option>)}
        </select>
        <select value={filtres.priority} onChange={(e) => majFiltre('priority', e.target.value)}
                aria-label="Priorité" data-testid="filtre-priority" style={styleChamp}>
          <option value="">Toutes priorités</option>
          {PRIORITES.map((p) => <option key={p} value={p}>Priorité {p}</option>)}
        </select>
        <input value={filtres.wave} onChange={(e) => majFiltre('wave', e.target.value)}
               placeholder="Vague" aria-label="Vague" data-testid="filtre-wave" style={styleChamp} />
        <input value={filtres.city} onChange={(e) => majFiltre('city', e.target.value)}
               placeholder="Ville" aria-label="Ville" data-testid="filtre-city"
               list="prospection-villes" style={styleChamp} />
        <datalist id="prospection-villes">
          {villes.map((v) => <option key={v} value={v} />)}
        </datalist>
        <select value={String(taille)} onChange={(e) => { setPage(0); setTaille(Number(e.target.value)); }}
                aria-label="Par page" data-testid="filtre-taille" style={styleChamp}>
          {TAILLES.map((n) => <option key={n} value={n}>{n} par page</option>)}
        </select>
      </div>

      {etat === SECTION.ERREUR || etat === SECTION.SESSION ? (
        <SectionErreur
          motif={(section && section.motif) || 'serveur'}
          quoi="les prospects"
          onReessayer={recharger}
        />
      ) : null}

      {etat === SECTION.CHARGEMENT && (
        <div style={{ opacity: 0.55, fontSize: '12px', padding: '10px 0' }}>
          Chargement des prospects…
        </div>
      )}

      {chargeUnFois && liste.length === 0 && (
        <div
          data-testid="prospection-vide"
          style={{
            padding: '28px 16px', textAlign: 'center', borderRadius: '12px',
            border: '1px dashed rgba(255,255,255,0.14)', opacity: 0.75, fontSize: '13px',
          }}
        >
          <SvgIcon name="compass" size={22} />
          <div style={{ marginTop: '8px' }}>
            {Object.values(filtres).some(Boolean)
              ? 'Aucun prospect ne correspond à ces filtres.'
              : 'Aucun prospect pour le moment.'}
          </div>
        </div>
      )}

      {/* ---------- LE TABLEAU (large) ---------- */}
      {chargeUnFois && liste.length > 0 && (
        <>
          <div className="hidden md:block" style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ textAlign: 'left', opacity: 0.6, fontSize: '11px' }}>
                  <th style={{ padding: '6px 8px' }}>
                    <input type="checkbox" data-testid="tout-selectionner"
                           aria-label="Tout sélectionner"
                           checked={liste.length > 0 && liste.every((p) => selection.indexOf(p.id) !== -1)}
                           onChange={toutSelectionner} />
                  </th>
                  {['Organisation', 'Catégorie', 'Ville', 'Score', 'Priorité', 'Vague',
                    'Canal', 'Statut', 'Prochaine action', 'Dernier contact'].map((h) => (
                    <th key={h} style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {liste.map((p) => (
                  <tr
                    key={p.id}
                    onClick={() => ouvrir(p)}
                    data-testid={`ligne-${p.ref || p.id}`}
                    style={{ cursor: 'pointer', borderTop: '1px solid rgba(255,255,255,0.06)' }}
                  >
                    {/* La case n'ouvre PAS la fiche : sans `stopPropagation`,
                        cocher un prospect ouvrirait le tiroir à chaque clic. */}
                    <td style={{ padding: '8px' }} onClick={(e) => e.stopPropagation()}>
                      <input type="checkbox" data-testid={`choix-${p.ref || p.id}`}
                             aria-label={`Sélectionner ${p.organisation_name}`}
                             checked={selection.indexOf(p.id) !== -1}
                             onChange={() => basculerSelection(p.id)} />
                    </td>
                    <td style={{ padding: '8px', fontWeight: 600 }}>
                      {p.organisation_name}
                      {p.ref ? <span style={{ opacity: 0.55, fontSize: '11px' }}> · {p.ref}</span> : null}
                    </td>
                    <td style={{ padding: '8px' }}>{libelleDe(CATEGORIES, p.category)}</td>
                    <td style={{ padding: '8px' }}>{ou(p.city)}</td>
                    <td style={{ padding: '8px', fontVariantNumeric: 'tabular-nums' }}>{ou(p.score)}</td>
                    <td style={{ padding: '8px' }}>{ou(p.priority)}</td>
                    <td style={{ padding: '8px' }}>{ou(p.wave)}</td>
                    <td style={{ padding: '8px', maxWidth: '160px' }}>{ou(p.preferred_channel)}</td>
                    <td style={{ padding: '8px' }}>
                      <Etiquette texte={libelleDe(STATUTS, p.status)}
                                 ton={p.status === 'a_contacter' ? 'primaire' : 'neutre'} />
                    </td>
                    <td style={{ padding: '8px' }}>{ou(p.next_followup_at)}</td>
                    <td style={{ padding: '8px' }}>{ou(p.last_contact_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* ---------- LES CARTES (mobile) ---------- */}
          {/* P3-S2F — `display` VIENT DE LA CLASSE, JAMAIS DU STYLE EN LIGNE.
              Un style en ligne l'emporte sur n'importe quelle classe, media
              query comprise : `display: 'flex'` écrasait donc `md:hidden`, et
              les cartes destinées au mobile restaient affichées sur desktop —
              chaque prospect apparaissait deux fois, en ligne de tableau ET en
              carte. Mesuré en production : 25 lignes + 25 cartes.
              `flex` passe en classe pour que `md:hidden` puisse le battre ;
              `flexDirection` et `gap` restent en ligne, ils n'entrent en
              conflit avec rien. Le voisin ligne 716 (`hidden md:block`) était
              déjà correct — son style en ligne ne touche pas `display`. */}
          <div className="md:hidden flex" style={{ flexDirection: 'column', gap: '8px' }}>
            {liste.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => ouvrir(p)}
                data-testid={`carte-${p.ref || p.id}`}
                style={{
                  textAlign: 'left', padding: '12px', borderRadius: '10px',
                  border: '1px solid rgba(255,255,255,0.10)',
                  background: 'rgba(255,255,255,0.04)', color: 'inherit',
                }}
              >
                <div style={{ fontWeight: 700, fontSize: '14px' }}>{p.organisation_name}</div>
                <div style={{ fontSize: '11px', opacity: 0.65, margin: '2px 0 6px' }}>
                  {libelleDe(CATEGORIES, p.category)} · {ou(p.city)}
                  {p.priority ? ` · Priorité ${p.priority}` : ''}
                  {p.wave ? ` · ${p.wave}` : ''}
                </div>
                <Etiquette texte={libelleDe(STATUTS, p.status)}
                           ton={p.status === 'a_contacter' ? 'primaire' : 'neutre'} />
              </button>
            ))}
          </div>

          {/* ---------- PAGINATION ---------- */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px',
                        marginTop: '12px', fontSize: '12px', flexWrap: 'wrap' }}>
            <button type="button" disabled={page === 0} onClick={() => setPage((p) => Math.max(p - 1, 0))}
                    data-testid="page-precedente" style={stylePagination(page === 0)}>
              <SvgIcon name="arrowLeft" size={12} /> Précédent
            </button>
            <span style={{ opacity: 0.7 }}>
              {page * taille + 1}–{page * taille + liste.length} sur {ou(total)}
            </span>
            <button type="button"
                    disabled={(page + 1) * taille >= (total || 0)}
                    onClick={() => setPage((p) => p + 1)}
                    data-testid="page-suivante"
                    style={stylePagination((page + 1) * taille >= (total || 0))}>
              Suivant <SvgIcon name="arrowRight" size={12} />
            </button>
          </div>
        </>
      )}

      {/* ---------- LA FICHE ---------- */}
      {ouvert && brouillon && (
        <div
          data-testid="fiche-prospect"
          onClick={fermer}
          style={{
            position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(0,0,0,0.62)',
            display: 'flex', justifyContent: 'flex-end',
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: '100%', maxWidth: '560px', height: '100%', overflowY: 'auto',
              background: '#15121a', borderLeft: `2px solid ${PRIMAIRE}`, padding: '18px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '10px' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '17px', fontWeight: 700 }}>
                  {ouvert.organisation_name}
                </h3>
                <div style={{ fontSize: '11px', opacity: 0.6, marginTop: '2px' }}>
                  {ouvert.ref ? `${ouvert.ref} · ` : ''}{libelleDe(CATEGORIES, ouvert.category)}
                </div>
              </div>
              <button type="button" onClick={fermer} data-testid="fermer-fiche"
                      aria-label="Fermer" style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}>
                <SvgIcon name="close" size={18} />
              </button>
            </div>

            <Bloc titre="Identité">
              <Champ libelle="Ville">{ou(ouvert.city)}</Champ>
              <Champ libelle="Adresse">{ou(ouvert.address)}</Champ>
              <Champ libelle="Site"><LienExterne href={ouvert.website} /></Champ>
              <Champ libelle="Instagram">
                {ouvert.instagram
                  ? <LienExterne href={`https://instagram.com/${String(ouvert.instagram).replace(/^@/, '')}`}
                                 children={ouvert.instagram} />
                  : '—'}
              </Champ>
              <Champ libelle="Facebook"><LienExterne href={ouvert.facebook} /></Champ>
              <Champ libelle="LinkedIn"><LienExterne href={ouvert.linkedin} /></Champ>
              <Champ libelle="TikTok"><LienExterne href={ouvert.tiktok} /></Champ>
              <Champ libelle="Source"><LienExterne href={ouvert.source_url} /></Champ>
              <Champ libelle="Source secondaire"><LienExterne href={ouvert.secondary_source_url} /></Champ>
              <Champ libelle="Vérifié le">{ou(ouvert.verified_at)}</Champ>
              <Champ libelle="Score">{ou(ouvert.score)}</Champ>
            </Bloc>

            <Bloc titre="Qualification (modifiable)">
              <Ligne libelle="Statut">
                <select value={brouillon.status} data-testid="edit-status"
                        onChange={(e) => majBrouillon('status', e.target.value)} style={styleChamp}>
                  {STATUTS.map((s) => <option key={s.cle} value={s.cle}>{s.libelle}</option>)}
                </select>
              </Ligne>
              <Ligne libelle="Priorité">
                <select value={brouillon.priority} data-testid="edit-priority"
                        onChange={(e) => majBrouillon('priority', e.target.value)} style={styleChamp}>
                  <option value="">—</option>
                  {PRIORITES.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </Ligne>
              <Ligne libelle="Vague">
                <input value={brouillon.wave} data-testid="edit-wave"
                       onChange={(e) => majBrouillon('wave', e.target.value)} style={styleChamp} />
              </Ligne>
              <Ligne libelle="Canal">
                <input value={brouillon.preferred_channel} data-testid="edit-channel"
                       onChange={(e) => majBrouillon('preferred_channel', e.target.value)} style={styleChamp} />
              </Ligne>
              <Ligne libelle="Collaboration">
                <select value={brouillon.collaboration_type} data-testid="edit-collaboration"
                        onChange={(e) => majBrouillon('collaboration_type', e.target.value)} style={styleChamp}>
                  {COLLABORATIONS.map((c) => <option key={c.cle} value={c.cle}>{c.libelle}</option>)}
                </select>
              </Ligne>
            </Bloc>

            <Bloc titre="Coordonnées (modifiables)">
              <Ligne libelle="E-mail">
                <input value={brouillon.public_email} data-testid="edit-email"
                       onChange={(e) => majBrouillon('public_email', e.target.value)} style={styleChamp} />
              </Ligne>
              <Ligne libelle="Téléphone">
                <input value={brouillon.public_phone} data-testid="edit-phone"
                       onChange={(e) => majBrouillon('public_phone', e.target.value)} style={styleChamp} />
              </Ligne>
              <Ligne libelle="Contact">
                <input value={brouillon.contact_name}
                       onChange={(e) => majBrouillon('contact_name', e.target.value)} style={styleChamp} />
              </Ligne>
              <Ligne libelle="Rôle">
                <input value={brouillon.contact_role}
                       onChange={(e) => majBrouillon('contact_role', e.target.value)} style={styleChamp} />
              </Ligne>
            </Bloc>

            <Bloc titre="Approche">
              <Champ libelle="Approche">{ou(ouvert.approach)}</Champ>
            </Bloc>

            {/* LES MESSAGES SONT DU TEXTE. Aucun bouton d'envoi : P3-S3. */}
            <Bloc titre="Messages préparés — aucun envoi depuis cet écran">
              {[['j0_message', 'Message J0'], ['j3_message', 'Relance J+3'],
                ['j7_message', 'Relance J+7'], ['interested_message', 'Si intéressé']].map(([cle, lib]) => (
                <div key={cle} style={{ marginBottom: '10px' }}>
                  <div style={{ fontSize: '11px', opacity: 0.6, marginBottom: '3px' }}>{lib}</div>
                  <textarea
                    value={brouillon[cle]}
                    data-testid={`edit-${cle}`}
                    onChange={(e) => majBrouillon(cle, e.target.value)}
                    rows={cle === 'j0_message' ? 6 : 3}
                    style={{ ...styleChamp, width: '100%', resize: 'vertical' }}
                  />
                </div>
              ))}
            </Bloc>

            <Bloc titre="Notes">
              <textarea value={brouillon.notes} data-testid="edit-notes" rows={6}
                        onChange={(e) => majBrouillon('notes', e.target.value)}
                        style={{ ...styleChamp, width: '100%', resize: 'vertical' }} />
            </Bloc>

            {/* ---------- CAL-3 : PLANIFIER ET AGENDA ----------
                Deux blocs, et rien de plus. Une fiche prospect sert à
                qualifier ; y déverser tout l'historique la rendrait illisible
                pour le seul cas qui compte — le coach qui rappelle quelqu'un. */}
            <Bloc titre="Rendez-vous">
              {agenda && agenda.next_appointment ? (
                <div data-testid="prochain-rdv"
                     style={{ padding: '8px 10px', borderRadius: '8px',
                              background: `rgba(${RGB}, 0.12)`,
                              borderLeft: `3px solid ${PRIMAIRE}`, marginBottom: '8px' }}>
                  <div style={{ fontSize: '12px', fontWeight: 700, color: TEXTE }}>
                    {agenda.next_appointment.title}
                  </div>
                  <div style={{ fontSize: '11px', opacity: 0.8, color: TEXTE }}>
                    {String(agenda.next_appointment.starts_at).slice(0, 16).replace('T', ' à ')}
                    {agenda.next_appointment.meeting_type
                      ? ` · ${agenda.next_appointment.meeting_type}` : ''}
                    {agenda.next_appointment.status
                      ? ` · ${agenda.next_appointment.status}` : ''}
                  </div>
                </div>
              ) : (
                <div data-testid="aucun-rdv"
                     style={{ fontSize: '12px', opacity: 0.6, color: TEXTE, marginBottom: '8px' }}>
                  Aucun rendez-vous à venir.
                </div>
              )}

              {!planifOuvert ? (
                <button type="button" data-testid="planifier"
                        onClick={ouvrirPlanification} style={styleBouton}>
                  Planifier un rendez-vous
                </button>
              ) : (
                <div data-testid="formulaire-planification"
                     style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  <input data-testid="planif-quand" type="datetime-local" value={planif.quand}
                         onChange={(e) => setPlanif({ ...planif, quand: e.target.value })}
                         style={{ ...styleChamp, flex: '1 1 170px' }} />
                  <select data-testid="planif-type" value={planif.type}
                          onChange={(e) => setPlanif({ ...planif, type: e.target.value })}
                          style={{ ...styleChamp, flex: '0 1 120px' }}>
                    <option value="appel">Appel</option>
                    <option value="visio">Visioconférence</option>
                    <option value="rencontre">Rencontre</option>
                    <option value="autre">Autre</option>
                  </select>
                  <select data-testid="planif-duree" value={planif.duree}
                          onChange={(e) => setPlanif({ ...planif, duree: e.target.value })}
                          style={{ ...styleChamp, flex: '0 1 100px' }}>
                    {[15, 30, 45, 60, 90, 120].map((d) => (
                      <option key={d} value={d}>{d} min</option>
                    ))}
                  </select>
                  <input data-testid="planif-titre" value={planif.titre}
                         placeholder="Titre (facultatif)"
                         onChange={(e) => setPlanif({ ...planif, titre: e.target.value })}
                         style={{ ...styleChamp, flex: '2 1 180px' }} />
                  {googleSync ? (
                    <label data-testid="planif-google"
                           style={{ display: 'flex', alignItems: 'center', gap: '6px',
                                    flex: '1 1 100%', fontSize: '12px',
                                    color: 'rgba(255,255,255,0.75)', cursor: 'pointer' }}>
                      <input type="checkbox" data-testid="planif-google-case"
                             checked={planif.google}
                             onChange={(e) => setPlanif({ ...planif, google: e.target.checked })}
                             style={{ accentColor: PRIMAIRE }} />
                      Synchroniser avec Google Calendar
                    </label>
                  ) : null}
                  <button type="button" data-testid="planif-valider" onClick={planifier}
                          disabled={planifEnCours} style={styleBouton}>
                    {planifEnCours ? '…' : 'Créer'}
                  </button>
                  <button type="button" data-testid="planif-annuler"
                          onClick={() => setPlanifOuvert(false)}
                          style={{ ...styleBouton, background: 'transparent',
                                   border: `1px solid rgba(${RGB}, 0.4)` }}>
                    Annuler
                  </button>
                </div>
              )}
            </Bloc>

            <Bloc titre="Tâches ouvertes">
              {agenda && (agenda.open_tasks || []).length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                  {agenda.open_tasks.map((tc) => (
                    <div key={tc.id} data-testid="tache-ouverte"
                         style={{ display: 'flex', gap: '8px', alignItems: 'baseline',
                                  fontSize: '12px', color: TEXTE }}>
                      <span style={{ flex: '1 1 auto', minWidth: 0, overflow: 'hidden',
                                     textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {tc.title}
                      </span>
                      <span style={{ fontSize: '11px', opacity: 0.7, whiteSpace: 'nowrap',
                                     color: tc.bucket === 'en_retard'
                                       ? 'rgba(239,68,68,0.95)' : 'inherit' }}>
                        {tc.bucket === 'en_retard' ? 'en retard' : ''}
                        {' '}{String(tc.starts_at).slice(0, 16).replace('T', ' ')}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div data-testid="aucune-tache"
                     style={{ fontSize: '12px', opacity: 0.6, color: TEXTE }}>
                  Aucune tâche ouverte.
                </div>
              )}
            </Bloc>

            <Bloc titre="Suivi">
              <Champ libelle="Premier contact">{ou(ouvert.first_contact_at)}</Champ>
              <Champ libelle="Dernier contact">{ou(ouvert.last_contact_at)}</Champ>
              <Champ libelle="Prochaine action">{ou(ouvert.next_followup_at)}</Champ>
              <Champ libelle="Réponse le">{ou(ouvert.replied_at)}</Champ>
              <Champ libelle="Candidature liée">{ou(ouvert.partner_application_id)}</Champ>
              <Champ libelle="Partenaire lié">{ou(ouvert.partner_id)}</Champ>
            </Bloc>

            {message && (
              <div data-testid="message-fiche"
                   style={{ fontSize: '12px', margin: '8px 0',
                            color: message.type === 'ok' ? PRIMAIRE : '#ff8a80' }}>
                {message.texte}
              </div>
            )}

            <div style={{ display: 'flex', gap: '8px', marginTop: '12px' }}>
              <button type="button" onClick={enregistrer} disabled={enregistrement}
                      data-testid="enregistrer-prospect"
                      style={{ padding: '9px 16px', borderRadius: '8px', border: 'none',
                               background: PRIMAIRE, color: '#fff', fontWeight: 600,
                               cursor: enregistrement ? 'default' : 'pointer', opacity: enregistrement ? 0.6 : 1 }}>
                {enregistrement ? 'Enregistrement…' : 'Enregistrer'}
              </button>
              <button type="button" onClick={fermer}
                      style={{ padding: '9px 16px', borderRadius: '8px', color: 'inherit',
                               border: '1px solid rgba(255,255,255,0.16)', background: 'transparent',
                               cursor: 'pointer' }}>
                Fermer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const styleBouton = {
  padding: '7px 14px', borderRadius: '8px', fontSize: '12px', fontWeight: 600,
  cursor: 'pointer', color: TEXTE, border: `1px solid rgba(${RGB}, 0.55)`,
  background: `rgba(${RGB}, 0.28)`,
};

const stylePetitBouton = {
  padding: '3px 9px', borderRadius: '6px', fontSize: '11px', cursor: 'pointer',
  color: TEXTE, border: '1px solid rgba(255,255,255,0.22)', background: 'transparent',
};

const styleChamp = {
  padding: '7px 10px',
  borderRadius: '8px',
  border: '1px solid rgba(255,255,255,0.14)',
  background: 'rgba(255,255,255,0.05)',
  color: TEXTE,
  fontSize: '13px',
};

const stylePagination = (inactif) => ({
  padding: '6px 12px',
  borderRadius: '8px',
  border: '1px solid rgba(255,255,255,0.14)',
  background: 'transparent',
  color: 'inherit',
  cursor: inactif ? 'default' : 'pointer',
  opacity: inactif ? 0.35 : 1,
});

function Bloc({ titre, children }) {
  return (
    <section style={{ marginTop: '16px' }}>
      <div style={{ fontSize: '11px', letterSpacing: '0.06em', textTransform: 'uppercase',
                    opacity: 0.55, marginBottom: '6px' }}>
        {titre}
      </div>
      {children}
    </section>
  );
}

function Champ({ libelle, children }) {
  return (
    <div style={{ display: 'flex', gap: '8px', fontSize: '12.5px', padding: '3px 0' }}>
      <div style={{ minWidth: '132px', opacity: 0.6 }}>{libelle}</div>
      <div style={{ flex: 1, wordBreak: 'break-word' }}>{children}</div>
    </div>
  );
}

function Ligne({ libelle, children }) {
  return (
    <div style={{ display: 'flex', gap: '8px', alignItems: 'center', padding: '4px 0', flexWrap: 'wrap' }}>
      <div style={{ minWidth: '132px', opacity: 0.6, fontSize: '12.5px' }}>{libelle}</div>
      <div style={{ flex: 1, minWidth: '180px' }}>{children}</div>
    </div>
  );
}
