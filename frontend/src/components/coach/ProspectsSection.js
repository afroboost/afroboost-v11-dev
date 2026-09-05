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

export default function ProspectsSection({ API }) {
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

  /* Les dépendances sont des CHAÎNES, jamais l'objet `filtres` — qui est neuf à
     chaque rendu et relancerait l'effet en boucle (règle absolue, incident V305). */
  const signature = [
    filtres.status, filtres.category, filtres.priority, filtres.wave, filtres.city,
    String(taille), String(page),
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
          const rep = await axios.get(`${base}/prospect-inbound`,
            { params: { limit: 20 } });
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
  const reponsesEnAttente = (sectionReponses && sectionReponses.etat === SECTION.OK
    && sectionReponses.donnees && sectionReponses.donnees.en_attente) || 0;

  /* READ-P1 — LES DEUX COMPTEURS VIENNENT DU SERVEUR, JAMAIS DE LA PAGE.
     La liste est paginée (20 par défaut) : les recompter ici donnerait un badge
     qui change selon la page affichée. Ils survivent donc au rafraîchissement,
     à la reconnexion et à la navigation, parce qu'ils ne dérivent d'aucun état
     de navigateur. */
  const reponsesNonLues = (sectionReponses && sectionReponses.etat === SECTION.OK
    && sectionReponses.donnees && sectionReponses.donnees.non_lues) || 0;
  const reponsesARepondre = (sectionReponses && sectionReponses.etat === SECTION.OK
    && sectionReponses.donnees && sectionReponses.donnees.a_repondre) || 0;

  /* ---------- READ-P1 + AI-P1 — L'ÉTAT DES RÉPONSES REÇUES ----------

     TOUT EST INDEXÉ PAR `message.id`, ET C'EST LA RÈGLE CENTRALE DU LOT.
     Trois partenaires ont répondu le même jour, au même objet, sur la même
     campagne. Une variable unique (`brouillon`, `enCours`…) partagée par les
     cartes ferait apparaître le texte d'ETU-04 sur la carte de LSN-A3 — le
     mélange exact que ce chantier existe pour empêcher. Une table par
     identifiant rend ce mélange structurellement impossible.

     `reponseOuverte` est une CHAÎNE (l'id), jamais l'objet : la règle V305
     interdit de reposer un objet neuf quand rien n'a changé. */
  const [reponseOuverte, setReponseOuverte] = useState('');
  const [brouillons, setBrouillons] = useState({});      // id -> brouillon serveur
  const [iaEnCours, setIaEnCours] = useState('');        // id de la carte en génération
  const [iaErreurs, setIaErreurs] = useState({});        // id -> message d'erreur
  const [etatEnCours, setEtatEnCours] = useState('');    // id de la carte dont l'état change

  /* READ-P1 — OUVRIR, C'EST LIRE. Et rien d'autre ne l'est.
     Ce clic est le SEUL chemin qui écrit `read_at`. Ni le chargement de
     l'écran, ni l'analyse IA, ni la future notification ne passent par ici.
     Refermer la carte ne « dé-lit » pas : on n'oublie pas ce qu'on a vu. */
  const ouvrirReponse = useCallback(async (id) => {
    if (!id) return;
    if (reponseOuverte === id) { setReponseOuverte(''); return; }
    setReponseOuverte(id);
    try {
      await axios.post(`${base}/prospect-inbound/${encodeURIComponent(id)}/lu`);
      chargement.reessayer('reponses');
    } catch (e) {
      /* La lecture n'a pas pu être enregistrée : la carte s'ouvre quand même.
         Un état de badge n'est jamais une raison de cacher un message. */
    }
    /* Le brouillon éventuel est relu à l'ouverture, jamais avant : le charger
       pour toutes les cartes ferait N appels pour un panneau que personne
       n'a encore déplié. */
    try {
      const r = await axios.get(`${base}/prospect-inbound/${encodeURIComponent(id)}/brouillon`);
      const b = (r && r.data && r.data.brouillon) || null;
      if (b) setBrouillons((prev) => ({ ...prev, [id]: b }));
    } catch (e) { /* pas de brouillon = cas normal, pas une panne */ }
  }, [base, reponseOuverte, chargement]);

  /* AI-P1 — L'ANALYSE. Elle NE MARQUE RIEN comme lu ni traité.
     `ton` vide = première génération ; sinon régénération orientée. */
  const analyserReponse = useCallback(async (id, ton) => {
    if (!id || iaEnCours) return;
    setIaEnCours(id);
    setIaErreurs((prev) => (prev[id] ? { ...prev, [id]: '' } : prev));
    try {
      const r = await axios.post(
        `${base}/prospect-inbound/${encodeURIComponent(id)}/analyser`,
        ton ? { ton } : {});
      const b = (r && r.data && r.data.brouillon) || null;
      if (b) setBrouillons((prev) => ({ ...prev, [id]: b }));
    } catch (e) {
      const detail = (e && e.response && e.response.data && e.response.data.detail)
        || "L'analyse n'a pas abouti.";
      setIaErreurs((prev) => ({ ...prev, [id]: String(detail) }));
    } finally {
      setIaEnCours('');
    }
  }, [base, iaEnCours]);

  /* READ-P1 — « TRAITÉ » EST UNE DÉCISION, JAMAIS UNE DÉDUCTION.
     Lire ne traite pas, analyser ne traite pas. Seul ce clic le fait — et il
     est réversible, parce qu'un état qu'on ne peut pas corriger finit ignoré. */
  const basculerTraite = useCallback(async (id, traite) => {
    if (!id || etatEnCours) return;
    setEtatEnCours(id);
    try {
      await axios.post(`${base}/prospect-inbound/${encodeURIComponent(id)}/traite`,
        { traite: !!traite });
      chargement.reessayer('reponses');
    } catch (e) {
      setIaErreurs((prev) => ({ ...prev, [id]: "L'état n'a pas pu être enregistré." }));
    } finally {
      setEtatEnCours('');
    }
  }, [base, etatEnCours, chargement]);

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

      {/* ---------- P3-U3 / READ-P1 / AI-P1 : LES RÉPONSES REÇUES ----------

           TROIS ÉTATS, TROIS QUESTIONS DIFFÉRENTES, et les confondre est le
           défaut que ce bloc corrige :
             « NOUVEAU »    — je ne l'ai jamais OUVERTE   (`read_at` absent)
             « À RÉPONDRE » — je n'ai pas encore AGI       (`traite_at` absent)
             « TRAITÉ »     — j'ai agi, explicitement
           Ouvrir n'est pas répondre : le badge NOUVEAU disparaît à l'ouverture,
           « À RÉPONDRE » reste tant que le coach n'a pas décidé le contraire.

           TOUT EST INDEXÉ PAR `r.id`. Aucune variable partagée entre les
           cartes : le brouillon d'ETU-04 ne peut pas s'afficher sur LSN-A3. */}
      {reponses.length > 0 && (
        <div data-testid="reponses-recues"
             style={{
               padding: '12px 14px', marginBottom: '14px', borderRadius: '10px',
               border: `1px solid rgba(${RGB}, 0.4)`, background: `rgba(${RGB}, 0.10)`,
             }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px',
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
            {reponsesEnAttente > 0 && (
              <span data-testid="reponses-en-attente"
                    style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '999px',
                             background: 'rgba(255,255,255,0.10)', color: TEXTE, fontWeight: 600 }}>
                {reponsesEnAttente} à rattacher à la main
              </span>
            )}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {reponses.map((r) => {
              /* Tout ce qui suit est LOCAL à cette carte. Aucune de ces
                 variables n'existe en dehors de l'itération : c'est ce qui
                 garantit qu'aucune donnée d'un prospect n'atteint un autre. */
              const nonLue = !r.read_at;
              const traitee = !!r.traite_at;
              const deplie = reponseOuverte === r.id;
              const bro = brouillons[r.id] || null;
              const erreurIa = iaErreurs[r.id] || '';
              const genere = iaEnCours === r.id;
              return (
                <div key={r.id} data-testid="reponse-ligne"
                     style={{
                       padding: '8px 10px', borderRadius: '8px',
                       background: nonLue ? `rgba(${RGB}, 0.14)` : 'rgba(255,255,255,0.05)',
                       borderLeft: `3px solid ${r.statut === 'rattache'
                         ? `rgba(${RGB}, 0.9)` : 'rgba(245,158,11,0.9)'}`,
                     }}>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap',
                                alignItems: 'baseline' }}>
                    {nonLue && (
                      <span data-testid="badge-nouveau"
                            style={{ fontSize: '10px', fontWeight: 700, letterSpacing: '0.04em',
                                     padding: '2px 7px', borderRadius: '999px', color: TEXTE,
                                     background: `rgba(${RGB}, 0.55)` }}>
                        NOUVEAU
                      </span>
                    )}
                    <span style={{ fontSize: '12px', fontWeight: 700, color: TEXTE }}>
                      {r.recipient_key || 'Prospect à identifier'}
                    </span>
                    <span style={{ fontSize: '11px', opacity: 0.75, color: TEXTE }}>{r.from_email}</span>
                    <span data-testid={traitee ? 'badge-traite' : 'badge-a-repondre'}
                          style={{ fontSize: '10px', fontWeight: 600, padding: '2px 7px',
                                   borderRadius: '999px', color: TEXTE,
                                   background: traitee ? 'rgba(34,197,94,0.22)' : 'rgba(245,158,11,0.22)' }}>
                      {traitee ? 'TRAITÉ' : 'À RÉPONDRE'}
                    </span>
                    <span style={{ fontSize: '11px', opacity: 0.6, color: TEXTE, marginLeft: 'auto' }}>
                      {(r.received_at || '').slice(0, 16).replace('T', ' ')}
                    </span>
                  </div>
                  <div style={{ fontSize: '12px', marginTop: '3px', color: TEXTE }}>{r.subject}</div>

                  {/* Le corps est du TEXTE, jamais du HTML : on n'injecte pas le
                      contenu d'un inconnu dans la page. Replié, on n'en montre
                      qu'un aperçu — l'original complet est un clic plus loin. */}
                  {!deplie && (
                    <div style={{ fontSize: '11px', opacity: 0.75, marginTop: '3px',
                                  whiteSpace: 'pre-wrap', color: TEXTE }}>
                      {(r.body_text || '').slice(0, 180)}
                      {(r.body_text || '').length > 180 ? '…' : ''}
                    </div>
                  )}

                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap',
                                alignItems: 'center', marginTop: '6px' }}>
                    <button type="button" data-testid="voir-reponse"
                            onClick={() => ouvrirReponse(r.id)}
                            style={{ ...stylePetitBouton, fontWeight: 600 }}>
                      {deplie ? 'Replier' : 'Voir la réponse'}
                    </button>
                    {deplie && (
                      <button type="button" data-testid="basculer-traite"
                              onClick={() => basculerTraite(r.id, !traitee)}
                              disabled={etatEnCours === r.id}
                              style={{ ...stylePetitBouton,
                                       opacity: etatEnCours === r.id ? 0.6 : 1 }}>
                        {traitee ? 'Remettre à répondre' : 'Marquer comme traité'}
                      </button>
                    )}
                    <span style={{ fontSize: '10px', opacity: 0.6, color: TEXTE, marginLeft: 'auto' }}>
                      {r.statut === 'rattache'
                        ? `rattaché — ${r.matching_method} (confiance ${r.matching_confidence})`
                        : `à rattacher — ${r.motif || 'ambigu'}`}
                      {r.campaign_id ? ` · campagne ${String(r.campaign_id).slice(0, 8)}` : ''}
                    </span>
                  </div>

                  {deplie && (
                    <div style={{ marginTop: '8px', paddingTop: '8px',
                                  borderTop: '1px solid rgba(255,255,255,0.12)' }}>
                      <div style={{ fontSize: '10px', fontWeight: 700, opacity: 0.7,
                                    color: TEXTE, marginBottom: '4px' }}>
                        MESSAGE ORIGINAL
                      </div>
                      <div data-testid="corps-original"
                           style={{ fontSize: '12px', whiteSpace: 'pre-wrap', color: TEXTE,
                                    lineHeight: 1.5 }}>
                        {r.body_text || '(aucun contenu lisible pour cette réponse)'}
                      </div>
                      {/* L'historique cité reste SÉPARÉ du nouveau texte : c'est
                          la coupure faite par P3-R4, on ne la recolle pas ici. */}
                      {r.body_quoted ? (
                        <details style={{ marginTop: '6px' }}>
                          <summary style={{ fontSize: '11px', cursor: 'pointer',
                                            opacity: 0.7, color: TEXTE }}>
                            Historique cité
                          </summary>
                          <div style={{ fontSize: '11px', whiteSpace: 'pre-wrap',
                                        opacity: 0.7, color: TEXTE, marginTop: '4px' }}>
                            {r.body_quoted}
                          </div>
                        </details>
                      ) : null}

                      {/* ---- AI-P1 : l'analyse et le brouillon ----
                          RIEN NE PART D'ICI. Aucun bouton d'envoi : le brouillon
                          se lit, se copie, se régénère. L'envoi appartient à un
                          lot ultérieur, derrière une confirmation explicite. */}
                      <div style={{ marginTop: '10px', display: 'flex', gap: '8px',
                                    flexWrap: 'wrap', alignItems: 'center' }}>
                        <button type="button" data-testid="analyser-ia"
                                onClick={() => analyserReponse(r.id, '')}
                                disabled={genere}
                                style={{ ...styleBouton, opacity: genere ? 0.6 : 1 }}>
                          {genere ? 'Analyse en cours…'
                            : (bro ? 'Régénérer' : "Analyser avec l'IA")}
                        </button>
                        {bro && !genere && ['court', 'chaleureux', 'professionnel', 'direct'].map((t) => (
                          <button key={t} type="button" data-testid={`ton-${t}`}
                                  onClick={() => analyserReponse(r.id, t)}
                                  style={stylePetitBouton}>
                            Plus {t}
                          </button>
                        ))}
                      </div>

                      {erreurIa ? (
                        <div data-testid="erreur-ia"
                             style={{ fontSize: '11px', marginTop: '6px', padding: '6px 8px',
                                      borderRadius: '6px', color: TEXTE,
                                      background: 'rgba(239,68,68,0.18)' }}>
                          {erreurIa}
                        </div>
                      ) : null}

                      {bro ? (
                        <div data-testid="brouillon-ia" style={{ marginTop: '8px' }}>
                          {bro.validation_requise && (
                            <div data-testid="validation-bassi"
                                 style={{ display: 'flex', gap: '6px', alignItems: 'center',
                                          fontSize: '11px', fontWeight: 700, color: TEXTE,
                                          padding: '6px 8px', borderRadius: '6px',
                                          background: 'rgba(245,158,11,0.25)', marginBottom: '6px' }}>
                              <SvgIcon name="warning" size={13} />
                              VALIDATION BASSI NÉCESSAIRE — {bro.motifs_validation.join(', ')}
                            </div>
                          )}
                          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap',
                                        marginBottom: '6px' }}>
                            <Etiquette texte={`intention : ${bro.intention}`} ton="primaire" />
                            <Etiquette texte={`langue : ${bro.langue}`} />
                            <Etiquette texte={`version ${bro.version}`} />
                          </div>
                          {bro.resume ? (
                            <div style={{ fontSize: '11px', color: TEXTE, marginBottom: '3px' }}>
                              <strong>Résumé :</strong> {bro.resume}
                            </div>
                          ) : null}
                          {bro.demande ? (
                            <div style={{ fontSize: '11px', color: TEXTE, marginBottom: '3px' }}>
                              <strong>Demande :</strong> {bro.demande}
                            </div>
                          ) : null}
                          {bro.prochaine_action ? (
                            <div style={{ fontSize: '11px', color: TEXTE, marginBottom: '6px' }}>
                              <strong>Prochaine action :</strong> {bro.prochaine_action}
                            </div>
                          ) : null}
                          <div style={{ fontSize: '10px', fontWeight: 700, opacity: 0.7,
                                        color: TEXTE, marginBottom: '3px' }}>
                            BROUILLON POUR {bro.to_email}
                          </div>
                          <div data-testid="reponse-proposee"
                               style={{ fontSize: '12px', whiteSpace: 'pre-wrap', color: TEXTE,
                                        lineHeight: 1.5, padding: '8px 10px', borderRadius: '8px',
                                        background: 'rgba(0,0,0,0.25)',
                                        border: `1px solid rgba(${RGB}, 0.35)` }}>
                            {bro.reponse_proposee}
                          </div>
                          <div style={{ fontSize: '10px', opacity: 0.6, color: TEXTE,
                                        marginTop: '4px' }}>
                            Brouillon — rien n'est envoyé. L'envoi viendra dans un lot dédié.
                          </div>
                        </div>
                      ) : null}
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
