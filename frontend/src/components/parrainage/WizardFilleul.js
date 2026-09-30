/**
 * V556 — PARRAINAGE V3 « BOULE DE NEIGE » : LE PARCOURS DU FILLEUL.
 *
 * V558 — LE WIZARD « INVITATION & PARRAINAGE » EN QUATRE ÉTAPES, une seule visible
 * à la fois : 1 Offre · 2 Séance · 3 Ta carte · 4 Partage (puis l'inscription).
 *   1. « Qu'est-ce que tu veux offrir à ton ami ? » — les types AUTORISÉS par le
 *      serveur (GET /chain/options) : Essai gratuit / Pass Duo, et Parrainage /
 *      Affiliation seulement si un programme réel existe ;
 *   2. « Choisis la séance de ton ami » — le calendrier EXISTANT (SessionsModal,
 *      `occurrencesFournies`) sur les seules séances renvoyées par le serveur ;
 *      puis un résumé compact et « Changer de séance ». La séance reçue et la
 *      séance offerte sont DEUX choses : l'enfant porte la sienne ;
 *   3. « Personnalise ton invitation » — l'enfant est créé ICI (après le choix de
 *      la séance), avec le type et la séance ; tes informations + aperçu ;
 *   4. « Envoie ton invitation » — les partages existants, puis l'inscription.
 * L'essai gratuit n'est jamais promis : il est UNE fois par personne, et seul le
 * serveur le sait au moment de l'inscription.
 *
 * Utilisé par InvitationDuo quand le serveur répond `chain_required: true`
 * (et que le pass n'est pas déjà rejoint). Trois étapes courtes :
 *   1. « Ton invitation »  — qui t'invite, la séance, l'offre → [Continuer] ;
 *   2. « Invite un ami »   — l'invitation ENFANT est créée À L'ENTRÉE (POST
 *      /chain, avant tout partage), aperçu de la carte, puis WhatsApp /
 *      Partager avec la carte / Partager / Copier le lien. Le partage
 *      DÉCLENCHÉ est enregistré (POST /chain/share) → étape 3 ;
 *   3. « Ton essai est débloqué » — SEULEMENT maintenant, le formulaire
 *      d'inscription (fourni par InvitationDuo, qui garde le POST /join).
 *
 * RÈGLES :
 *   - on n'écrit JAMAIS que WhatsApp a envoyé, ni que la miniature s'affichera ;
 *   - WhatsApp / navigator.share partent SYNCHRONES dans le clic avec le
 *     share_url COURANT, puis on enregistre, puis on remplace l'enfant par la
 *     réponse (nouveau share_url : un 2e partage n'a jamais la même URL) ;
 *   - le File de la carte est PRÉ-chargé pendant la préparation (le geste
 *     utilisateur est perdu si on télécharge au moment du clic) ;
 *   - aucune boucle d'appels : les effets dépendent de primitives, et la
 *     création de l'enfant est gardée par une référence (un seul POST en vol).
 *
 * UX-P2 — ENREGISTREMENT AUTOMATIQUE (plus de bouton « Mettre à jour ma carte ») :
 *   - le bandeau « <Prénom> t'invite à découvrir Afroboost » suit la frappe
 *     (état local) ; la photo aussi ;
 *   - prénom / message / photo / WhatsApp / consentement → PATCH 500 ms après la
 *     DERNIÈRE modification (un seul minuteur, en référence ; aucun PATCH si la
 *     signature — une chaîne — n'a pas changé ; un échec n'est pas relancé tant
 *     que rien ne change : pas de boucle) ;
 *   - un clic de partage avec une modification en attente FORCE l'enregistrement
 *     (minuteur annulé, requête attendue) et partage le share_url / card_url
 *     RENVOYÉS. Si l'enregistrement échoue : AUCUN partage (on ne partage jamais
 *     une ancienne version), le message d'erreur dit quoi corriger ;
 *   - OUVERTURE DE FENÊTRE après un `await` (bloquée par les navigateurs) :
 *       · WhatsApp : rien en attente → `window.open(lien)` synchrone comme avant ;
 *         en attente → fenêtre VIDE ouverte synchrone dans le clic (opener coupé),
 *         puis `fen.location.href = lien` après l'enregistrement (fermée en cas
 *         d'échec) ; fenêtre refusée → « touche encore WhatsApp » ;
 *       · Partager : on tente `navigator.share` après l'enregistrement ; si le
 *         navigateur refuse (NotAllowedError, geste perdu) → « touche encore » ;
 *       · Partager avec la carte : le fichier de la NOUVELLE carte doit être
 *         pré-chargé → après l'enregistrement, on demande de toucher à nouveau ;
 *       · Copier : copie tentée après l'enregistrement, sinon « touche encore » ;
 *       · QR : affiché après l'enregistrement (aucun geste requis).
 */
import React, { useEffect, useRef, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import SvgIcon from '../SvgIcon';
import { AvatarInvitant } from './BandeauInvitant'; // L0
import SessionsModal from '../SessionsModal'; // V558 — le calendrier EXISTANT, réutilisé
import {
  MESSAGE_CHAINE_DEFAUT, MESSAGE_MAX, NOM_MAX, bornerMessage, nomAffichable,
  creerInvitationChaine, modifierInvitationChaine, enregistrerPartageChaine,
  verifierApercuNavigateur, lireCleChaine, ecrireCleChaine, lireRefus, messageRefus,
  lienWhatsApp, copier, texteChaine, libelleOccurrence, TEXTE_AUTRE_APPAREIL,
  envoyerPhotoChaine, refusPhotoChaine, numeroWhatsAppChaine, INDICATIFS, INDICATIF_DEFAUT,
  lireOptionsChaine, choisirSeanceChaine, seancesPourCalendrier, messageRefusSeance,
} from '../../utils/parrainage';

/**
 * V556 — AUTRE APPAREIL. L'invitation a été préparée (et parfois partagée) sur un
 * autre appareil : le serveur n'accepte le partage et l'inscription qu'avec la clé
 * de CET appareil-là. On le dit simplement, sans erreur technique.
 * « Recommencer sur cet appareil » a été AUDITÉ et ÉCARTÉ : ré-émettre une clé sans
 * identité vérifiée rendrait l'invitation à quiconque possède le même lien (groupe
 * WhatsApp) — l'attaque exacte que la clé empêche. Seule action proposée : copier le
 * lien de cette page pour l'ouvrir sur le bon appareil (inoffensif, rien n'est écrit).
 */
function AutreAppareil() {
  const [copie, setCopie] = useState('');
  const url = typeof window !== 'undefined' && window.location ? window.location.href : '';
  return (
    <div className="cp-notice cp-wf-autre" role="status" data-testid="wf-autre-appareil">
      <p style={{ margin: 0 }}>{TEXTE_AUTRE_APPAREIL}</p>
      {url ? (
        <button type="button" className="cp-b cp-b--secondary cp-wz-cible" style={{ marginTop: 12 }}
                onClick={() => copier(url).then((ok) => setCopie(ok ? 'Lien copié : ouvre-le sur ton autre appareil.' : 'Copie impossible.'))}
                data-testid="wf-copier-page">
          <SvgIcon name="link" size={20} /> Copier le lien de cette invitation
        </button>
      ) : null}
      {copie ? <p className="cp-mini" role="status" style={{ marginBottom: 0 }}>{copie}</p> : null}
    </div>
  );
}
import { Etapes, CartesOffre, ResumeSeance, CarteInvitation, libelleTypeInvitation, typesDeRepli } from './wizardCommun'; // V558 / V560
import './invitationWizard.css'; // V556 : cibles 44 px (cp-wz-tap / cp-wz-cible) et cadre de carte, absents de /duo sinon
import './wizardFilleul.css';

/** Le message FR d'un refus de création / modification de l'invitation enfant. */
export function messageErreurChaine(refus) {
  const r = refus || {};
  if (r.status === 409 && r.raison === 'chaine_en_attente') return messageRefus('chaine_en_attente');
  if (r.status === 409 && r.raison === 'pass_ferme') return messageRefus('pass_ferme');
  if (r.status === 409) return 'Ton ami a déjà rejoint cette invitation : elle ne peut plus changer.';
  if (r.status === 403) return 'Cette carte ne peut plus être modifiée depuis cet appareil.';
  if (r.status === 410) return 'Cette invitation a expiré';
  if (r.status === 404) return 'Invitation indisponible';
  if (r.status === 422 || r.status === 400) return 'Vérifie ton prénom et ton message.';
  if (r.status === 429) return 'Trop de tentatives. Réessaie dans un instant.';
  return 'Ton invitation ne se prépare pas pour le moment. Réessaie dans un instant.';
}

/** UX-P2 : délai de l'enregistrement automatique après la dernière frappe. */
export const DELAI_AUTOSAVE_MS = 500;

/** UX-P2 : libellé de la case de consentement (non cochée par défaut). */
// UX-P4 — le badge suit le type RÉEL renvoyé par le serveur ; jamais « Pass Duo » par défaut.
// V558 : badge, cartes d'offre, stepper et résumé de séance viennent du module COMMUN
// (le même Wizard que l'espace abonné) ; ré-exportés pour les appelants existants.
export { libelleTypeInvitation, ResumeSeance };

/** V558 — la séance CHOISIE pour l'ami, telle que la carte la montre. */
function seanceDepuisEnfant(c) {
  if (!c || c.seance_choisie !== true || !c.occurrence) return null;
  const co = c.course || {};
  return { course_id: null, occurrence: c.occurrence, nom: co.name || '', lieu: co.locationName || '' };
}

export const TEXTE_CONSENT_CONTACT = "J'accepte d'être contacté(e) par Afroboost au sujet de cette invitation et de mon essai.";

const MSG_WHATSAPP_INVALIDE = 'Ce numéro WhatsApp n’est pas valide. Corrige-le (ex. : +41 79 123 45 67) ou efface-le pour partager.';

function _signature(v) {
  return JSON.stringify([String(v.nom || '').trim(), v.message || '', v.photo || null, v.wa || '', !!v.consent]);
}

function _chiffres(s) {
  return (String(s || '').match(/\d/g) || []).length;
}

/**
 * @param {string}   token          le jeton du pass reçu (T0)
 * @param {object}   pass           le PassDTO public (chain, course, occurrence…)
 * @param {string}   prenom         le prénom affichable du parrain
 * @param {string}   photo          sa photo autorisée, ou null (étape 1 seulement : jamais sur la carte du filleul)
 * @param {node}     blocInvitation la séance + l'offre (rendus par InvitationDuo)
 * @param {node}     formulaire     le formulaire d'inscription (rendu par InvitationDuo)
 * @param {function} onPrenom       (prénom saisi à l'étape 2) → préremplit l'inscription
 * @param {function} onWhatsApp     (numéro saisi à l'étape 2) → préremplit l'inscription (UX-P2)
 * @param {number}   retourEtape2   compteur : chaque incrément ramène à l'étape 2 (409 invitation_requise)
 * @param {string}   messageEtape2  message affiché à l'étape 2 après ce retour
 */
export default function WizardFilleul({
  token, pass, prenom, photo, blocInvitation, formulaire, onPrenom, onWhatsApp, retourEtape2, messageEtape2,
}) {
  const dejaPartagee = !!(pass && pass.chain && pass.chain.shared === true);
  const [etape, setEtape] = useState(dejaPartagee ? 4 : 1);
  const [partage, setPartage] = useState(dejaPartagee);      // V558 : partage enregistré -> inscription
  const [opts, setOpts] = useState(null);                    // V558 : {types, seances} du serveur
  const [optsKo, setOptsKo] = useState(false);
  const [kind, setKind] = useState('');
  const [seance, setSeance] = useState(null);                // {course_id, occurrence, nom, lieu}
  const [calendrier, setCalendrier] = useState(false);
  const [erreurSeance, setErreurSeance] = useState('');
  const [seanceKo, setSeanceKo] = useState(false);           // « Choisir une autre séance »
  const [majSeance, setMajSeance] = useState(false);
  const [child, setChild] = useState(null);
  const [editKey, setEditKey] = useState(() => lireCleChaine(token));
  const [creation, setCreation] = useState(false);
  const [erreurCreation, setErreurCreation] = useState('');
  const [nom, setNom] = useState('');
  const [message, setMessage] = useState('');
  const [messageOuvert, setMessageOuvert] = useState(false);
  const [photoCarte, setPhotoCarte] = useState(null);     // UX-P2 : photo choisie (URL) ou null
  const [indicatif, setIndicatif] = useState(INDICATIF_DEFAUT);
  const [numero, setNumero] = useState('');
  const [consent, setConsent] = useState(false);
  const [sauve, setSauve] = useState('');                 // signature des valeurs enregistrées
  const [echec, setEchec] = useState('');                 // signature dont l'enregistrement a échoué
  const [maj, setMaj] = useState(false);
  const [statut, setStatut] = useState('');               // '' | 'enregistre'
  const [erreurMaj, setErreurMaj] = useState('');
  const [envoiPhoto, setEnvoiPhoto] = useState(false);
  const [erreurPhoto, setErreurPhoto] = useState('');
  const [qrOuvert, setQrOuvert] = useState(false);
  const [verif, setVerif] = useState({ cle: '', ok: false, file: null }); // contrôle navigateur
  const [carteKo, setCarteKo] = useState(false);
  const [enregistrement, setEnregistrement] = useState(false);
  const [aReessayer, setAReessayer] = useState(''); // canal dont l'enregistrement a échoué
  const [info, setInfo] = useState('');
  const [avis, setAvis] = useState(''); // message venu d'InvitationDuo (409 invitation_requise)
  const enVol = useRef(false);
  const enVolMaj = useRef(null);      // promesse du PATCH en vol (une seule)
  const minuteur = useRef(null);      // minuteur de l'enregistrement automatique
  const childRef = useRef(null);
  const sauveRef = useRef('');
  const sauveValeurs = useRef(null);  // valeurs du dernier enregistrement réussi
  const inputGalerie = useRef(null);
  const inputCamera = useRef(null);

  const wa = numeroWhatsAppChaine(indicatif, numero);
  const valeurs = { nom, message, photo: photoCarte || null, wa, consent };
  const valeursRef = useRef(valeurs);
  valeursRef.current = valeurs;
  const sigCourante = _signature(valeurs);
  childRef.current = child;
  sauveRef.current = sauve;

  // 409 invitation_requise au join → retour au PARTAGE (vérité serveur).
  useEffect(() => {
    if (!retourEtape2) return;
    setEtape(4);
    setPartage(false);
    setAvis(messageEtape2 || messageRefus('invitation_requise'));
  }, [retourEtape2, messageEtape2]);

  // V558 : UNE lecture des options au montage (jeton = primitive ; aucune boucle).
  useEffect(() => {
    let vivant = true;
    lireOptionsChaine({ token })
      .then((r) => {
        if (!vivant) return;
        const d = (r && r.data) || {};
        setOpts({ types: Array.isArray(d.types) ? d.types : [], seances: Array.isArray(d.seances) ? d.seances : [] });
      })
      .catch(() => { if (vivant) setOptsKo(true); });
    return () => { vivant = false; };
  }, [token]);

  // Démontage : aucun minuteur orphelin.
  useEffect(() => () => { if (minuteur.current) clearTimeout(minuteur.current); }, []);

  // Création : les champs locaux partent des valeurs de l'enfant. JAMAIS rappelé après
  // un PATCH (on écraserait la frappe en cours).
  const poserChild = (c) => {
    if (!c || !c.share_url) return;
    const n = nomAffichable(c.display_name) || '';
    const m = typeof c.message === 'string' && c.message.trim() ? bornerMessage(c.message) : MESSAGE_CHAINE_DEFAUT;
    const surCarte = (c.inviter_display && c.inviter_display.photo_url) || null;
    // Photo : celle déjà sur la carte, sinon la photo de profil suggérée (préremplie :
    // l'enregistrement automatique la pose sur la carte), sinon rien (logo Afroboost).
    const initiale = surCarte || (typeof c.photo_suggeree === 'string' && c.photo_suggeree) || null;
    const base = { nom: n, message: m, photo: surCarte, wa: '', consent: false };
    sauveValeurs.current = base;
    setChild(c);
    const sc = seanceDepuisEnfant(c);
    if (sc) setSeance((prev) => (prev && prev.occurrence === sc.occurrence ? prev : sc));
    if (c.kind) setKind((prev) => prev || c.kind);
    setNom(n);
    setMessage(m);
    setPhotoCarte(initiale);
    setSauve(_signature(base));
    setCarteKo(false);
  };

  // ÉTAPE 2 : l'invitation enfant est créée (ou relue, idempotent) AVANT tout partage.
  // V558 : l'enfant naît À L'ÉTAPE 3 — APRÈS le choix de l'offre et de la séance,
  // qui partent avec lui (le serveur les revalide ; le parent garde sa séance).
  const aUnChild = !!child;
  const typesAffiches = (opts && opts.types && opts.types.length) ? opts.types : typesDeRepli(pass && pass.invitation_type);
  const kindEffectif = kind || (typesAffiches[0] && typesAffiches[0].id) || '';
  const creer = () => {
    if (enVol.current) return;
    enVol.current = true;
    setCreation(true); setErreurCreation('');
    const s0 = seanceRef.current;
    creerInvitationChaine({
      token, message: MESSAGE_CHAINE_DEFAUT, kind: kindRef.current || undefined,
      course_id: s0 && s0.course_id, occurrence: s0 && s0.course_id ? s0.occurrence : undefined,
    })
      .then((r) => {
        const d = (r && r.data) || {};
        if (d.edit_key) { ecrireCleChaine(token, d.edit_key); setEditKey(String(d.edit_key)); }
        poserChild(d.child ? Object.assign({}, d.child, d.preview ? { preview: d.preview } : {}) : null);
        if (!d.child) setErreurCreation(messageErreurChaine({}));
      })
      .catch((e) => {
        const refus = lireRefus(e);
        if (/^seance_|^type_non_autorise$/.test(refus.raison || '')) {
          // Jamais de bascule silencieuse vers une autre séance : on revient au choix.
          setErreurSeance(messageRefusSeance(refus));
          setSeanceKo(refus.raison !== 'type_non_autorise');
          setEtape(refus.raison === 'type_non_autorise' ? 1 : 2);
          return;
        }
        setErreurCreation(messageErreurChaine(refus));
      })
      .finally(() => { enVol.current = false; setCreation(false); });
  };
  const kindRef = useRef('');
  const seanceRef = useRef(null);
  kindRef.current = kindEffectif;
  seanceRef.current = seance;
  useEffect(() => {
    if ((etape === 3 || (etape === 4 && !partage)) && !aUnChild) creer();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [etape, partage, aUnChild, token]);

  /** Étape 2 → 3 : l'enfant existe déjà (retour en arrière) → sa séance / son type suivent (PATCH). */
  const validerSeance = () => {
    setErreurSeance(''); setSeanceKo(false);
    const c = childRef.current;
    const change = c && !c.shared && editKey && (
      (seance && seance.course_id && seance.occurrence !== c.occurrence) || (kindEffectif && kindEffectif !== c.kind));
    if (!change) { setEtape(3); return; }
    setMajSeance(true);
    choisirSeanceChaine({
      token, editKey, kind: kindEffectif !== c.kind ? kindEffectif : undefined,
      course_id: seance && seance.course_id, occurrence: seance && seance.course_id ? seance.occurrence : undefined,
    })
      .then((r) => {
        const d = (r && r.data) || {};
        if (d.child && d.child.share_url) {
          const suivant = Object.assign({}, childRef.current || {}, d.child,
            { preview: d.preview || (childRef.current && childRef.current.preview) });
          childRef.current = suivant;
          setChild(suivant);
          setCarteKo(false);
        }
        setEtape(3);
      })
      .catch((e) => {
        const refus = lireRefus(e);
        setErreurSeance(messageRefusSeance(refus));
        setSeanceKo(/^seance_/.test(refus.raison || ''));
      })
      .finally(() => setMajSeance(false));
  };

  // Contrôle d'aperçu côté navigateur (card_url + share_url COURANTS). Clé = les deux URL.
  const cardUrl = (child && child.card_url) || '';
  const shareUrl = (child && child.share_url) || '';
  const cleVerif = `${cardUrl}|${shareUrl}`;
  useEffect(() => {
    if (!shareUrl) return undefined;
    let vivant = true;
    verifierApercuNavigateur({ cardUrl, shareUrl })
      .then((v) => {
        if (!vivant) return;
        setVerif((prev) => (prev.cle === cleVerif && prev.ok === v.ok && prev.file === v.file
          ? prev : { cle: cleVerif, ok: !!v.ok, file: v.file || null }));
      });
    return () => { vivant = false; };
  }, [cardUrl, shareUrl, cleVerif]);

  // UX-P2 : seule la PREMIÈRE préparation bloque le partage. Après un enregistrement
  // (nouvelle carte), le contrôle repart en arrière-plan : seul « Partager avec la
  // carte » attend le fichier de la nouvelle carte.
  const verifActuelle = verif.cle === cleVerif;
  const preparation = creation || !child || !verif.cle;
  // L'aperçu serveur voyage à côté de `child` (réponse POST/PATCH) : on le range dessus.
  // Absent (serveur ancien) : on ne pénalise pas, seul le contrôle navigateur tranche.
  const serveurOk = !(child && child.preview && child.preview.ok === false);
  const apercuSimplifie = !preparation && ((verifActuelle && (!verif.ok || !serveurOk)) || carteKo);

  const nomValide = nomAffichable(nom);
  const editable = !!editKey;
  const enAttente = sigCourante !== sauve || maj;
  // V556 : sans la clé de CET appareil, le serveur refuse le partage (403) — on le dit.
  const boutonsInactifs = preparation || enregistrement || !editable || envoiPhoto;
  // Un numéro en cours de frappe (1 à 7 chiffres) n'est pas envoyé automatiquement.
  const waIncomplet = _chiffres(numero) > 0 && _chiffres(numero) < 8;

  /** Un PATCH avec les valeurs COURANTES. Résout avec l'enfant à jour, rejette si refusé. */
  const sauvegarder = () => {
    const v = valeursRef.current;
    const sig = _signature(v);
    if (String(v.nom || '').trim() && !nomAffichable(v.nom)) {
      setErreurMaj('Indique un prénom (sans adresse e-mail).'); setEchec(sig); setStatut('');
      return Promise.reject({ status: 0, raison: 'prenom' });
    }
    const avant = sauveValeurs.current || {};
    const corps = { token, editKey, display_name: v.nom, message: v.message };
    if ((v.photo || null) !== (avant.photo || null)) corps.photo_url = v.photo || null;
    if ((v.wa || '') !== (avant.wa || '')) corps.whatsapp = v.wa || '';
    if (!!v.consent !== !!avant.consent) corps.consent_contact = !!v.consent;
    setMaj(true); setStatut('');
    const p = modifierInvitationChaine(corps)
      .then((r) => {
        const d = (r && r.data) || {};
        let suivant = childRef.current;
        if (d.child && d.child.share_url) {
          suivant = Object.assign({}, childRef.current || {}, d.child,
            { preview: d.preview || d.child.preview || (childRef.current && childRef.current.preview) });
          childRef.current = suivant;
          setChild(suivant);
          setCarteKo(false);
        }
        sauveValeurs.current = v;
        sauveRef.current = sig;
        setSauve(sig); setEchec(''); setErreurMaj(''); setStatut('enregistre');
        return suivant;
      })
      .catch((e) => {
        const refus = e && e.response ? lireRefus(e) : (e || {});
        if (refus.status === 403) setEditKey('');
        const waEnvoye = corps.whatsapp !== undefined;
        const raisonWa = /whatsapp|phone|telephone|numero/i.test(`${refus.raison || ''} ${refus.detail || ''}`);
        setErreurMaj(refus.status === 422 && (raisonWa || waEnvoye) ? MSG_WHATSAPP_INVALIDE : messageErreurChaine(refus));
        setEchec(sig); setStatut('');
        throw refus;
      })
      .finally(() => { enVolMaj.current = null; setMaj(false); });
    enVolMaj.current = p;
    return p;
  };

  // ENREGISTREMENT AUTOMATIQUE : un minuteur, relancé à chaque changement de signature.
  useEffect(() => {
    if (!aUnChild || !editKey || maj || waIncomplet) return undefined;
    if (sigCourante === sauve || sigCourante === echec) return undefined;
    const t = setTimeout(() => {
      if (minuteur.current === t) minuteur.current = null;
      sauvegarder().catch(() => { /* message déjà affiché */ });
    }, DELAI_AUTOSAVE_MS);
    minuteur.current = t;
    return () => { clearTimeout(t); if (minuteur.current === t) minuteur.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sigCourante, sauve, echec, aUnChild, editKey, maj, waIncomplet]);

  /**
   * Avant un partage : annule le minuteur, attend le PATCH en vol, enregistre ce
   * qui reste. Résout avec l'enfant À JOUR (share_url / card_url renvoyés).
   */
  const garantirAJour = () => {
    if (minuteur.current) { clearTimeout(minuteur.current); minuteur.current = null; }
    const attente = enVolMaj.current ? enVolMaj.current.catch(() => null) : Promise.resolve();
    return attente.then(() => {
      if (_signature(valeursRef.current) === sauveRef.current) return childRef.current;
      return sauvegarder();
    });
  };
  const aEnregistrer = () => _signature(valeursRef.current) !== sauveRef.current || !!enVolMaj.current;

  // Enregistre le partage DÉCLENCHÉ, remplace l'enfant (nouveau share_url), passe à l'étape 3.
  const enregistrer = (channel) => {
    setEnregistrement(true); setAReessayer(''); setInfo('');
    enregistrerPartageChaine({ token, channel })
      .then((r) => {
        const d = (r && r.data) || {};
        if (d.child && d.child.share_url) {
          setChild((prev) => Object.assign({}, prev || {}, d.child, { preview: (d.child.preview || (prev && prev.preview)) }));
        }
        setAvis('');
        const v = valeursRef.current;
        const n = nomAffichable(v.nom);
        if (typeof onPrenom === 'function' && n) onPrenom(n);
        if (typeof onWhatsApp === 'function' && v.wa) onWhatsApp(v.wa);
        setPartage(true);
      })
      .catch(() => { setAReessayer(channel); })
      .finally(() => setEnregistrement(false));
  };

  const messageSauve = () => ((sauveValeurs.current && sauveValeurs.current.message) || message);
  const texte = texteChaine(message, shareUrl);
  const surWhatsApp = () => {
    if (boutonsInactifs || !shareUrl) return;
    setInfo('');
    if (!aEnregistrer()) {
      window.open(lienWhatsApp(texte), '_blank', 'noopener'); // synchrone : geste utilisateur
      enregistrer('whatsapp');
      return;
    }
    // Modification en attente : fenêtre vide ouverte DANS le geste, URL posée après.
    let fen = null;
    try { fen = window.open('', '_blank'); } catch (e) { fen = null; }
    if (fen) { try { fen.opener = null; } catch (e) { /* ignore */ } }
    garantirAJour()
      .then((c) => {
        const lien = lienWhatsApp(texteChaine(messageSauve(), c && c.share_url));
        if (fen) {
          try { fen.location.href = lien; } catch (e) { /* ignore */ }
          enregistrer('whatsapp');
        } else {
          setInfo('Ta carte est enregistrée. Touche encore WhatsApp pour la partager.');
        }
      })
      .catch(() => { if (fen) { try { fen.close(); } catch (e) { /* ignore */ } } });
  };
  const nav = typeof navigator !== 'undefined' ? navigator : null;
  const peutPartager = !!(nav && typeof nav.share === 'function');
  let peutCarte = false;
  if (peutPartager && verifActuelle && verif.file && typeof nav.canShare === 'function') {
    try { peutCarte = !!nav.canShare({ files: [verif.file] }); } catch (e) { peutCarte = false; }
  }
  const apresShare = (channel, libelle) => (p) => Promise.resolve(p)
    .then(() => enregistrer(channel))
    .catch((e) => {
      if (e && e.name === 'AbortError') return; // annulé : rien
      if (e && e.name === 'NotAllowedError') { setInfo(`Ta carte est enregistrée. Touche encore « ${libelle} ».`); return; }
      setInfo('Le partage n’a pas abouti. Essaie WhatsApp ou copie le lien.');
    });
  const surPartagerCarte = () => {
    if (boutonsInactifs || !peutCarte) return;
    setInfo('');
    if (aEnregistrer()) {
      // Le fichier de la NOUVELLE carte doit être pré-chargé : on redemande le geste.
      garantirAJour()
        .then(() => setInfo('Ta carte est enregistrée. Touche encore « Partager ».'))
        .catch(() => {});
      return;
    }
    let p;
    try { p = nav.share({ files: [verif.file], text: texte }); } catch (e) { p = Promise.reject(e); }
    apresShare('share_image', 'Partager')(p);
  };
  const surPartager = () => {
    if (boutonsInactifs || (!peutPartager && !peutCarte)) return;
    setInfo('');
    if (aEnregistrer()) {
      garantirAJour()
        .then((c) => {
          let p;
          try { p = nav.share({ title: 'Afroboost', text: messageSauve(), url: c && c.share_url }); } catch (e) { p = Promise.reject(e); }
          return apresShare('share', 'Partager')(p);
        })
        .catch(() => {});
      return;
    }
    // V560 : UN seul bouton « Partager » — la carte est jointe quand le téléphone
    // sait partager un fichier (canal share_image), sinon le lien seul.
    if (peutCarte) { surPartagerCarte(); return; }
    let p;
    try { p = nav.share({ title: 'Afroboost', text: message, url: shareUrl }); } catch (e) { p = Promise.reject(e); }
    apresShare('share', 'Partager')(p);
  };
  const copierUrl = (url, apresEnregistrement) => copier(url).then((ok) => {
    if (ok) { setInfo('Lien copié'); enregistrer('copy'); } else if (apresEnregistrement) {
      setInfo('Ta carte est enregistrée. Touche encore « Copier le lien ».');
    } else setInfo('Copie impossible : réessaie ou choisis WhatsApp.');
  });
  const surCopier = () => {
    if (boutonsInactifs || !shareUrl) return;
    setInfo('');
    if (aEnregistrer()) {
      garantirAJour().then((c) => copierUrl(c && c.share_url, true)).catch(() => {});
      return;
    }
    copierUrl(shareUrl, false);
  };
  const surQr = () => {
    if (boutonsInactifs || !shareUrl) return;
    if (qrOuvert) { setQrOuvert(false); return; }
    garantirAJour().then(() => setQrOuvert(true)).catch(() => {});
  };

  // ── Photo ──
  const choisirPhoto = (e) => {
    const cible = e && e.target;
    const f = cible && cible.files && cible.files[0];
    try { if (cible) cible.value = ''; } catch (err) { /* ignore */ }
    if (!f || !editKey) return;
    const refus = refusPhotoChaine(f);
    if (refus) { setErreurPhoto(refus); return; }
    setEnvoiPhoto(true); setErreurPhoto('');
    envoyerPhotoChaine({ token, editKey, file: f })
      .then((r) => {
        const u = r && r.data && r.data.photo_url;
        if (u) setPhotoCarte(String(u)); // l'enregistrement automatique pose photo_url
        else setErreurPhoto('Ta photo n’a pas pu être envoyée. Réessaie.');
      })
      .catch((err) => {
        const r = lireRefus(err);
        if (r.status === 403) setEditKey('');
        if (r.status === 413) setErreurPhoto('Cette photo dépasse 5 Mo : choisis-en une plus légère.');
        else if (r.status === 415 || r.status === 422 || r.status === 400) setErreurPhoto('Choisis une photo JPEG, PNG ou WebP.');
        else setErreurPhoto('Ta photo n’a pas pu être envoyée. Réessaie.');
      })
      .finally(() => setEnvoiPhoto(false));
  };
  const ouvrir = (ref) => { if (ref.current && !envoiPhoto) ref.current.click(); };

  const retour = (n) => (
    <button type="button" className="cp-link cp-wz-tap cp-wz-retour" onClick={() => { setInfo(''); setEtape(n); }} data-testid="wf-retour">
      <SvgIcon name="arrowLeft" size={14} /> Retour
    </button>
  );
  const seancesCal = seancesPourCalendrier(opts && opts.seances);
  const dejaEnvoyee = !!(child && child.shared);
  // Aucune séance proposable (serveur ancien, liste vide) : l'ami est invité à TA séance.
  const sansChoix = optsKo || (opts && seancesCal.length === 0);
  const maSeance = { occurrence: pass && pass.occurrence, nom: ((pass && pass.course) || {}).name || '',
                     lieu: ((pass && pass.course) || {}).locationName || '' };
  const seanceAmi = seance || (child && child.occurrence
    ? { occurrence: child.occurrence, nom: (child.course || {}).name || '', lieu: (child.course || {}).locationName || '' }
    : null);

  const coursAmi = seanceAmi ? seanceAmi.nom : '';
  const lieuAmi = seanceAmi ? seanceAmi.lieu : '';
  const typeAmi = (child && child.kind) || kindEffectif;
  // V560 : LA carte de l'invitation que CETTE personne envoie (une seule par écran).
  const maCarte = (testid) => (
    <CarteInvitation testid={testid} prenom={nomValide} photo={photoCarte} type={typeAmi}
                     occurrence={seanceAmi && seanceAmi.occurrence} cours={coursAmi} lieu={lieuAmi} />
  );

  // ── ÉTAPE 1 : OFFRE ────────────────────────────────────────────────────────
  if (etape === 1) {
    const c = (pass && pass.course) || {};
    return (
      <div className="cp-wf" data-testid="wf-etape-1">
        <Etapes className="cp-wf-etapes" etape={1} />
        {/* V560 : l'invitation REÇUE en une seule carte (photo, prénom, type, séance, lieu). */}
        <CarteInvitation testid="wf-invitation-recue" prenom={prenom} photo={photo} type={pass && pass.invitation_type}
                         occurrence={pass && pass.occurrence} cours={c.name} lieu={c.locationName}>
          {blocInvitation}
        </CarteInvitation>
        <p className="cp-wf-aide" data-testid="wf-lead">
          Pour débloquer ton essai, invite à ton tour une autre personne. Une fois ton invitation partagée, tu peux finaliser ton inscription.
        </p>
        <p className="cp-wf-regle" data-testid="wf-regle-essai">
          <SvgIcon name="info" size={14} /> L’essai gratuit est disponible une seule fois par personne.
        </p>
        <h2 className="cp-wf-titre" data-testid="wf-offre-titre">Que veux-tu partager ?</h2>
        <p className="cp-wf-aide">Choisis ce que tu veux proposer à ton ami.</p>
        {erreurSeance && !seanceKo ? <p className="cp-error" role="alert" data-testid="wf-offre-erreur">{erreurSeance}</p> : null}
        <CartesOffre types={typesAffiches} choisi={kindEffectif} verrouille={dejaEnvoyee}
                     onChoisir={(id) => { setKind(id); setErreurSeance(''); }} />
        {/* collant en bas d'écran : [Continuer] est visible dès le premier écran */}
        <button type="button" className="cp-b cp-wz-cible cp-wf-cta" onClick={() => { setErreurSeance(''); setEtape(2); }}
                disabled={!kindEffectif} data-testid="wf-continuer">
          Continuer <SvgIcon name="arrowRight" size={20} />
        </button>
      </div>
    );
  }

  // ── ÉTAPE 2 : SÉANCE DE L'AMI ─────────────────────────────────────────────
  if (etape === 2) {
    const choixRequis = !sansChoix && !dejaEnvoyee;
    return (
      <div className="cp-wf" data-testid="wf-etape-2">
        <Etapes className="cp-wf-etapes" etape={2} />
        <h2 className="cp-wf-titre" data-testid="wf-seance-titre">Choisis la séance de ton ami</h2>
        <p className="cp-wf-aide">Sélectionne la séance que ton ami recevra avec ton invitation.</p>
        {!opts && !optsKo ? (
          <p className="cp-mini cp-wf-prep" role="status" data-testid="wf-seances-chargement">
            <span className="cp-spinner cp-wf-spin" aria-hidden="true" /> Chargement des séances…
          </p>
        ) : null}
        {erreurSeance ? <p className="cp-error" role="alert" data-testid="wf-seance-erreur">{erreurSeance}</p> : null}
        {seanceKo && !dejaEnvoyee ? (
          <button type="button" className="cp-b cp-b--secondary cp-wz-cible"
                  onClick={() => { setSeance(null); setErreurSeance(''); setSeanceKo(false); setCalendrier(true); }}
                  data-testid="wf-seance-autre">
            <SvgIcon name="calendar" size={20} /> Choisir une autre séance
          </button>
        ) : null}
        {dejaEnvoyee ? (
          <>
            <ResumeSeance seance={seanceAmi} />
            <p className="cp-fine" data-testid="wf-seance-figee">Ton invitation a déjà été envoyée : sa séance ne change plus.</p>
          </>
        ) : null}
        {!dejaEnvoyee && sansChoix ? (
          <ResumeSeance seance={maSeance} titre="Ton ami est invité à la même séance que toi" testid="wf-seance-meme" />
        ) : null}
        {choixRequis && seance && !seanceKo ? (
          <ResumeSeance seance={seance} onChanger={() => { setErreurSeance(''); setCalendrier(true); }} />
        ) : null}
        {choixRequis && !seance && !seanceKo ? (
          <button type="button" className="cp-b cp-b--secondary cp-wz-cible" onClick={() => setCalendrier(true)}
                  disabled={!opts} data-testid="wf-seance-choisir">
            <SvgIcon name="calendar" size={20} /> Choisir la séance
          </button>
        ) : null}
        {calendrier ? (
          <SessionsModal
            open
            onClose={() => setCalendrier(false)}
            occurrencesFournies={seancesCal}
            libelleAction="Choisir cette séance"
            noteAction="C’est la séance que ton ami recevra avec ton invitation."
            onReserve={(occ) => {
              if (!occ || !occ.iso) return;
              setSeance({ course_id: occ.id, occurrence: occ.iso, nom: occ.nom || '', lieu: occ.lieu || '' });
              setErreurSeance(''); setSeanceKo(false); setCalendrier(false);
            }}
          />
        ) : null}
        <button type="button" className="cp-b cp-wz-cible cp-wf-cta" onClick={validerSeance}
                disabled={majSeance || (choixRequis && (!seance || seanceKo)) || (!opts && !optsKo)} data-testid="wf-seance-continuer">
          {majSeance ? 'Un instant…' : 'Continuer'} <SvgIcon name="arrowRight" size={20} />
        </button>
        {retour(1)}
      </div>
    );
  }

  // ── ÉTAPE 4 (après partage) : L'INSCRIPTION ────────────────────────────────
  if (etape === 4 && partage) {
    const c = (pass && pass.course) || {};
    return (
      <div className="cp-wf" data-testid="wf-etape-3">
        <Etapes className="cp-wf-etapes" etape={4} />
        <div className="cp-wf-ok" role="status">
          <span className="cp-wf-ok-ic"><SvgIcon name="check" size={22} strokeWidth="2.5" /></span>
          <div>
            <b>Invitation envoyée</b>
            {/* PAR-3 (A2) : rien n'est promis avant la réponse du serveur (l'essai peut être refusé au join). */}
            <p>Termine ton inscription pour réserver ta place.</p>
          </div>
        </div>
        <p className="cp-wf-rappel" data-testid="wf-rappel-seance">
          <SvgIcon name="calendar" size={16} />
          <span>{c.name ? `${c.name} · ` : ''}{libelleOccurrence(pass && pass.occurrence, c.locationName)}</span>
        </p>
        {editKey ? formulaire : <AutreAppareil />}
        {editKey ? (
          <button type="button" className="cp-link cp-wz-tap cp-wf-encore" onClick={() => { setInfo(''); setPartage(false); }} data-testid="wf-partager-encore">
            <SvgIcon name="share" size={14} /> Partager encore
          </button>
        ) : null}
      </div>
    );
  }

  const blocsCommuns = (
    <>
      {avis ? <p className="cp-notice" role="alert" data-testid="wf-avis">{avis}</p> : null}
      {erreurCreation ? (
        <div data-testid="wf-erreur-creation">
          <p className="cp-error" role="alert">{erreurCreation}</p>
          <button type="button" className="cp-b cp-b--secondary cp-wz-cible" onClick={creer} data-testid="wf-reessayer-creation">
            <SvgIcon name="refresh" size={20} /> Réessayer
          </button>
        </div>
      ) : null}
      {!erreurCreation && preparation ? (
        <p className="cp-mini cp-wf-prep" role="status" data-testid="wf-preparation">
          <span className="cp-spinner cp-wf-spin" aria-hidden="true" /> Préparation de ton invitation…
        </p>
      ) : null}
      {child && !editable ? <AutreAppareil /> : null}
    </>
  );

  // ── ÉTAPE 3 : TA CARTE ─────────────────────────────────────────────────────
  if (etape === 3) {
    // Continuer n'attend PAS le contrôle d'aperçu (seul le partage en a besoin).
    const carteInactive = !child || creation || enregistrement || !editable || envoiPhoto;
    const continuer = () => {
      if (carteInactive) return;
      garantirAJour().then(() => { setInfo(''); setEtape(4); }).catch(() => {});
    };
    return (
      <div className="cp-wf" data-testid="wf-etape-carte">
        <Etapes className="cp-wf-etapes" etape={3} />
        <div className="cp-wf-derniere" data-testid="wf-derniere-etape">
          <h2 className="cp-wf-titre">Personnalise ton invitation</h2>
          <p className="cp-wf-aide">Ton ami verra que l’invitation vient de toi.</p>
        </div>
        {blocsCommuns}
        {/* UX-P2 / V560 : UNE carte, rendue en direct — prénom et photo suivent la frappe. */}
        {child && editable ? maCarte('wf-apercu') : null}

        {child && editable ? (
          <div className="cp-wf-perso">
            <label className="cp-label" htmlFor="wf-nom">Ton prénom</label>
            <input id="wf-nom" className="cp-input" value={nom} maxLength={NOM_MAX} placeholder="Ex. : Henri"
                   onChange={(e) => setNom(e.target.value.slice(0, NOM_MAX))} autoComplete="given-name" data-testid="wf-nom" />

            <span className="cp-label" id="wf-photo-titre">Ta photo</span>
            <div className="cp-wf-photo" data-testid="wf-photo">
              <AvatarInvitant photoUrl={photoCarte} className="cp-wf-photo-av" testidPhoto="wf-photo-img" testidAvatar="wf-photo-logo" />
              <div className="cp-wf-photo-actions">
                <button type="button" className="cp-b cp-b--secondary cp-wz-cible" onClick={() => ouvrir(inputGalerie)} disabled={envoiPhoto} data-testid="wf-photo-ajouter">
                  <SvgIcon name="image" size={20} /> {photoCarte ? 'Changer de photo' : 'Ajouter une photo'}
                </button>
                <button type="button" className="cp-link cp-wz-tap" onClick={() => ouvrir(inputCamera)} disabled={envoiPhoto} data-testid="wf-photo-prendre">
                  <SvgIcon name="camera" size={14} /> Prendre une photo
                </button>
                {photoCarte ? (
                  <button type="button" className="cp-link cp-wz-tap" onClick={() => setPhotoCarte(null)} disabled={envoiPhoto} data-testid="wf-photo-retirer">
                    <SvgIcon name="x" size={14} /> Retirer
                  </button>
                ) : null}
              </div>
              <input ref={inputGalerie} type="file" accept="image/*" hidden onChange={choisirPhoto} aria-labelledby="wf-photo-titre" data-testid="wf-photo-fichier" />
              <input ref={inputCamera} type="file" accept="image/*" capture="user" hidden onChange={choisirPhoto} aria-labelledby="wf-photo-titre" data-testid="wf-photo-camera" />
            </div>
            {envoiPhoto ? <p className="cp-mini" role="status" data-testid="wf-photo-envoi">Envoi de ta photo…</p> : null}
            {erreurPhoto ? <p className="cp-error" role="alert" data-testid="wf-photo-erreur">{erreurPhoto}</p> : null}

            <label className="cp-label" htmlFor="wf-whatsapp-numero">Ton numéro WhatsApp</label>
            <div className="cp-wf-tel">
              <select className="cp-select cp-wf-indicatif" value={indicatif} aria-label="Indicatif du pays"
                      onChange={(e) => setIndicatif(e.target.value)} data-testid="wf-indicatif">
                {INDICATIFS.map(([code, pays]) => <option key={code} value={code}>{`${code} ${pays}`}</option>)}
              </select>
              <input id="wf-whatsapp-numero" className="cp-input" type="tel" inputMode="tel" value={numero}
                     placeholder="79 123 45 67" autoComplete="tel-national"
                     onChange={(e) => setNumero(e.target.value.slice(0, 30))} data-testid="wf-whatsapp-numero" />
            </div>
            <p className="cp-fine" data-testid="wf-whatsapp-aide">C’est ton numéro, pas celui de la personne que tu invites.</p>
            {child.whatsapp_renseigne === true && !numero.trim() ? (
              <p className="cp-fine" data-testid="wf-whatsapp-connu">Ton numéro est déjà enregistré.</p>
            ) : null}
            <label className="cp-chk">
              <input type="checkbox" checked={consent} onChange={(e) => setConsent(!!e.target.checked)} data-testid="wf-consent" />
              <span>{TEXTE_CONSENT_CONTACT}</span>
            </label>
            {messageOuvert ? (
              <div className="cp-wf-msg">
                <label className="cp-label" htmlFor="wf-message">Ton message</label>
                <textarea id="wf-message" className="cp-input cp-wz-message cp-wf-message" rows={3} value={message}
                          maxLength={MESSAGE_MAX}
                          onChange={(e) => setMessage(bornerMessage(e.target.value))} data-testid="wf-message" />
                <p className="cp-fine cp-wz-compteur">{message.length}/{MESSAGE_MAX}</p>
              </div>
            ) : (
              <button type="button" className="cp-link cp-wz-tap cp-wf-lien" onClick={() => setMessageOuvert(true)} data-testid="wf-modifier-message">
                <SvgIcon name="edit" size={14} /> Modifier le message
              </button>
            )}

            <p className="cp-fine cp-wf-statut" role="status" aria-live="polite" data-testid="wf-statut">
              {maj ? 'Enregistrement…' : (!enAttente && statut === 'enregistre' ? 'Enregistré' : '')}
            </p>
            {erreurMaj ? <p className="cp-error" role="alert" data-testid="wf-erreur-maj">{erreurMaj}</p> : null}
          </div>
        ) : null}
        {child && editable ? (
          <button type="button" className="cp-b cp-wz-cible cp-wf-cta" onClick={continuer} disabled={carteInactive}
                  data-testid="wf-carte-continuer">
            Continuer <SvgIcon name="arrowRight" size={20} />
          </button>
        ) : null}
        {retour(2)}
      </div>
    );
  }

  // ── ÉTAPE 4 : PARTAGE ──────────────────────────────────────────────────────
  return (
    <div className="cp-wf" data-testid="wf-etape-partage">
      <Etapes className="cp-wf-etapes" etape={4} />
      <div className="cp-wf-inviter" data-testid="wf-maintenant">
        <h2 className="cp-wf-titre">Partage ton invitation</h2>
        <p className="cp-wf-aide">Ton ami remplira ses propres informations quand il ouvrira le lien.</p>
      </div>
      {blocsCommuns}
      {child && editable ? maCarte('wf-partage-carte') : null}
      {apercuSimplifie ? <p className="cp-fine cp-wf-simplifie" data-testid="wf-apercu-simplifie">Aperçu simplifié : le lien reste valable.</p> : null}
      {child && editable ? (
        <div className="cp-wf-actions">
          <div className="cp-wf-actions4">
            <button type="button" className="cp-b cp-b--whatsapp cp-wz-cible" onClick={surWhatsApp} disabled={boutonsInactifs} data-testid="wf-whatsapp">
              <SvgIcon name="messageCircle" size={20} /> WhatsApp
            </button>
            <button type="button" className="cp-b cp-b--secondary cp-wz-cible" onClick={surPartager}
                    disabled={boutonsInactifs || (!peutPartager && !peutCarte)} data-testid="wf-partager">
              <SvgIcon name="share" size={20} /> Partager
            </button>
            <button type="button" className="cp-b cp-b--secondary cp-wz-cible" onClick={surCopier} disabled={boutonsInactifs} data-testid="wf-copier">
              <SvgIcon name="link" size={20} /> Copier le lien
            </button>
            <button type="button" className="cp-b cp-b--secondary cp-wz-cible" onClick={surQr} disabled={boutonsInactifs} aria-expanded={qrOuvert} data-testid="wf-qr">
              <SvgIcon name="qrCode" size={20} /> {qrOuvert ? 'Masquer le QR' : 'QR code'}
            </button>
          </div>
          {qrOuvert ? (
            <div className="cp-wf-qr" data-testid="wf-qr-bloc">
              {!enAttente && shareUrl ? (
                <div className="cp-qr-big"><QRCodeSVG value={shareUrl} size={180} level="M" includeMargin={false} /></div>
              ) : <p className="cp-mini" role="status">Enregistrement de ta carte…</p>}
              <p className="cp-fine">Ton ami scanne ce code pour ouvrir ton invitation.</p>
              {/* UX : le serveur accepte le canal « qr » (CANAUX) — un geste explicite, pour que le QR reste
                  affiché le temps du scan au lieu de passer tout de suite à l'inscription. */}
              {!enAttente && shareUrl ? (
                <button type="button" className="cp-b cp-b--secondary cp-wz-cible" onClick={() => enregistrer('qr')}
                        disabled={enregistrement} data-testid="wf-qr-fait">
                  <SvgIcon name="check" size={20} /> C’est fait, mon ami a scanné le QR code
                </button>
              ) : null}
            </div>
          ) : null}
          {enregistrement ? <p className="cp-mini" role="status">Un instant…</p> : null}
          {info ? <p className="cp-mini" role="status" data-testid="wf-info">{info}</p> : null}
          {aReessayer ? (
            <div data-testid="wf-erreur-partage">
              <p className="cp-error" role="alert">Ton partage n’a pas pu être enregistré. Réessaie pour débloquer ton essai.</p>
              <button type="button" className="cp-b cp-b--secondary cp-wz-cible" onClick={() => enregistrer(aReessayer)} disabled={enregistrement} data-testid="wf-reessayer-partage">
                <SvgIcon name="refresh" size={20} /> Réessayer
              </button>
            </div>
          ) : null}
          {erreurMaj ? <p className="cp-error" role="alert" data-testid="wf-erreur-maj">{erreurMaj}</p> : null}
        </div>
      ) : null}
      <button type="button" className="cp-link cp-wz-tap cp-wz-retour" onClick={() => { setInfo(''); setEtape(3); }} data-testid="wf-modifier">
        <SvgIcon name="edit" size={14} /> Modifier
      </button>
    </div>
  );
}
