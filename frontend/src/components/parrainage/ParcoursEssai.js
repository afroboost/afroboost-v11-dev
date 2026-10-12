/**
 * V607 — ESSAI GRATUIT « MOI D'ABORD → PUIS MON AMI ».
 *
 * Le parcours de l'invité d'une chaîne d'Essai gratuit (campagne d'un coach) :
 *   1. ACCUEIL (wf-essai-accueil) — qui m'invite, ce qu'est Afroboost, la séance
 *      proposée, « Ton premier cours est offert » → je garde ou je change MA
 *      séance (calendrier EXISTANT, séances du serveur) → [Valider ma séance] ;
 *   2. ESSAI PRÊT (wf-essai-pret) — « Pour le débloquer, invite à ton tour une
 *      personne » → [Inviter 1 ami sur WhatsApp]. L'invitation de l'ami est créée
 *      ICI (POST /chain, sans séance : elle hérite de la mienne ; l'ami pourra
 *      changer la sienne de son côté). [Finaliser mon inscription] reste bloqué
 *      tant que le partage n'est pas DÉCLENCHÉ (POST /chain/share) ;
 *   3. INSCRIPTION — le formulaire existant (InvitationDuo garde le POST /join) ;
 *   4. CONFIRMÉ (wf-essai-confirme) — date, heure, lieu, billet, et, facultatif,
 *      [Inviter encore] : V607g, une NOUVELLE invitation (jeton neuf) par ami.
 *
 * L'OBLIGATION RESTE CELLE DU SERVEUR : /join répond 409 `invitation_requise`
 * tant qu'aucun partage n'est enregistré (InvitationDuo ramène alors ici).
 *
 * HONNÊTETÉ : « partage déclenché » (WhatsApp ouvert avec le message prérempli),
 * jamais « envoyé ». AUCUNE BOUCLE : effets sur des primitives, création de
 * l'invitation gardée par une référence (un seul POST en vol).
 * Couleurs : jetons --cp-* (couleurs du coach). Icônes : SVG inline (SvgIcon).
 */
import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import SvgIcon from '../SvgIcon';
import SessionsModal from '../SessionsModal';
import BilletsDuo from './BilletsDuo';
import { CarteInvitation } from './wizardCommun';
import { AutreAppareil } from './WizardFilleul';
import {
  API_PARRAINAGE, MESSAGE_CHAINE_DEFAUT, NOM_MAX, nomAffichable, libelleJour, libelleHeure,
  creerInvitationChaine, modifierInvitationChaine, enregistrerPartageChaine, ecrireCleChaine, lireCleChaine,
  lireOptionsChaine, seancesPourCalendrier, changerSeance, lireRefus, messageRefus, messageRefusSeance,
  lienWhatsApp, copier, profilConnu, texteWhatsAppEssai, PITCH_AFROBOOST, urlEspaceCourant,
  creerInvitationSuivante, // V607g : « Inviter encore » = une NOUVELLE invitation
} from '../../utils/parrainage';
import { suivreInvitation } from '../../utils/invitationSuivi';
import AfroboostAudioPlayer from '../AfroboostAudioPlayer'; // V610k : le mot audio de l'invitation
import './invitationWizard.css';
import './wizardFilleul.css';

/** La séance du pass, au format du choix local. */
function seanceDuPass(pass) {
  const c = (pass && pass.course) || {};
  return { course_id: c.id || '', occurrence: (pass && pass.occurrence) || '', nom: c.name || '', lieu: c.locationName || '' };
}

/** Le message d'un refus du choix de MA séance. */
export function messageRefusMaSeance(refus) {
  const r = refus || {};
  if (r.raison === 'conflit_version') return 'Ton invitation vient de changer : vérifie la séance puis valide à nouveau.';
  if (r.raison === 'invitation_deja_partagee') return 'Ton invitation a déjà été partagée avec cette séance : elle ne change plus.';
  if (r.raison === 'pass_non_modifiable') return 'Cette séance ne peut plus être changée.';
  return messageRefusSeance(r);
}

function LigneSeance({ seance, testid }) {
  if (!seance || !seance.occurrence) return null;
  const heure = libelleHeure(seance.occurrence);
  return (
    <p className="cp-wf-rappel" data-testid={testid || 'wf-rappel-seance'}>
      <SvgIcon name="calendar" size={16} />
      <span>
        {libelleJour(seance.occurrence)}{heure ? ` · ${heure}` : ''}{seance.lieu ? ` · ${seance.lieu}` : ''}
      </span>
    </p>
  );
}

/**
 * @param {string}   token          le jeton du pass reçu
 * @param {object}   pass           le PassPublicDTO (course, occurrence, version, chain…)
 * @param {string}   prenom / photo l'invitant (affichables)
 * @param {node}     formulaire     le formulaire d'inscription (InvitationDuo)
 * @param {object}   resultat       la réponse du join (succès) ou null
 * @param {function} onPass         (dto) → InvitationDuo remplace sa copie du pass
 * @param {function} onPrenom       (prénom saisi) → préremplit l'inscription
 * @param {number}   retourPartage  compteur : chaque incrément ramène à « Essai prêt » (409 invitation_requise)
 * @param {string}   messagePartage le message affiché après ce retour
 */
export default function ParcoursEssai({
  token, pass, prenom, photo, formulaire, resultat, onPass, onPrenom, retourPartage, messagePartage,
}) {
  const chainePub = (pass && pass.chain) || {};
  const [ecran, setEcran] = useState(() => (chainePub.exists || chainePub.shared ? 'pret' : 'accueil'));
  const [partage, setPartage] = useState(!!chainePub.shared);
  const [choix, setChoix] = useState(() => seanceDuPass(pass));
  const [opts, setOpts] = useState(null);
  const [calendrier, setCalendrier] = useState(false);
  const [validation, setValidation] = useState(false);
  const [erreurSeance, setErreurSeance] = useState('');
  const [child, setChild] = useState(null);
  const [editKey, setEditKey] = useState(() => lireCleChaine(token));
  const [creation, setCreation] = useState(false);
  const [erreurCreation, setErreurCreation] = useState('');
  const [profil] = useState(() => profilConnu());
  const [nom, setNom] = useState(() => profil.prenom || '');
  const [enregistrement, setEnregistrement] = useState(false);
  const [aReessayer, setAReessayer] = useState('');
  const [info, setInfo] = useState('');
  const [avis, setAvis] = useState('');
  const enVol = useRef(false);
  // V610k — le MOT AUDIO de l'invitation (s'il existe) : UN lecteur, monté dès l'accueil (caché),
  // lancé PENDANT le clic « Valider ma séance » (geste utilisateur : condition du son sur
  // Safari / Chrome). Une seule tentative automatique par arrivée ; jamais en boucle ;
  // refus du navigateur -> le lecteur reste visible avec « Écouter le message ».
  const audioUrl = (pass && typeof pass.audio_url === 'string' && /^(\/api\/files\/|https:\/\/)/.test(pass.audio_url)) ? pass.audio_url : '';
  const audioRef = useRef(null);
  const audioTente = useRef(false);
  const lancerAudio = () => {
    if (!audioUrl || audioTente.current || !audioRef.current) return;
    audioTente.current = true;
    audioRef.current.lire().catch(() => { /* bloqué : le lecteur visible prend le relais */ });
  };
  const childRef = useRef(null);
  childRef.current = child;

  // Lien ouvert : une fois par jeton (le serveur ne compte qu'une fois par appareil).
  useEffect(() => { suivreInvitation(token, 'lien_ouvert'); }, [token]);

  // Les séances proposables (liste du SERVEUR) : une lecture au montage.
  useEffect(() => {
    let vivant = true;
    lireOptionsChaine({ token })
      .then((r) => { if (vivant) setOpts(((r && r.data) || {}).seances || []); })
      .catch(() => { if (vivant) setOpts([]); });
    return () => { vivant = false; };
  }, [token]);

  // 409 invitation_requise au join → retour à « Essai prêt » (vérité serveur).
  useEffect(() => {
    if (!retourPartage) return;
    setEcran('pret');
    setPartage(false);
    setAvis(messagePartage || messageRefus('invitation_requise'));
  }, [retourPartage, messagePartage]);

  // ── Création (ou relecture idempotente) de l'invitation de mon ami ──
  const creer = () => {
    if (enVol.current) return;
    enVol.current = true;
    setCreation(true); setErreurCreation('');
    const n = nomAffichable(nom);
    creerInvitationChaine({ token, message: MESSAGE_CHAINE_DEFAUT, display_name: n || undefined })
      .then((r) => {
        const d = (r && r.data) || {};
        if (d.edit_key) { ecrireCleChaine(token, d.edit_key); setEditKey(String(d.edit_key)); }
        if (d.child && d.child.share_url) setChild(d.child);
        else setErreurCreation('Ton invitation ne se prépare pas pour le moment. Réessaie dans un instant.');
      })
      .catch((e) => {
        const r = lireRefus(e);
        setErreurCreation(r.status === 429 ? 'Trop de tentatives. Réessaie dans un instant.'
          : (r.raison === 'chaine_en_attente' ? messageRefus('chaine_en_attente')
            : 'Ton invitation ne se prépare pas pour le moment. Réessaie dans un instant.'));
      })
      .finally(() => { enVol.current = false; setCreation(false); });
  };
  const aUnChild = !!child;
  const confirme = !!resultat;
  const surPret = ecran === 'pret' && !confirme;
  useEffect(() => {
    if (surPret) suivreInvitation(token, 'etape_invitation_atteinte');
  }, [surPret, token]);
  useEffect(() => {
    if (surPret && !aUnChild) creer();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [surPret, aUnChild, token]);

  // V610k : arrivée DIRECTE sur « Ton essai est prêt » (page rechargée, lien rouvert) : une
  // tentative sans geste — souvent refusée par le navigateur, le lecteur visible suffit alors.
  useEffect(() => {
    if (surPret && audioUrl && !audioTente.current) {
      const t = setTimeout(lancerAudio, 0);
      return () => clearTimeout(t);
    }
    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [surPret, audioUrl]);
  // UN SEUL lecteur, en PREMIER enfant (même clé) de l'accueil ET de « Ton essai est prêt » :
  // React garde le même élément audio d'un écran à l'autre (la lecture lancée au clic continue).
  const blocAudio = audioUrl && !confirme ? (
    <div key="wf-audio-essai" data-testid="wf-audio-essai" style={{ display: surPret ? 'block' : 'none', margin: '0 0 12px' }}>
      <AfroboostAudioPlayer ref={audioRef} src={audioUrl} preload="auto" compact
                            titre={prenom ? `Un mot de ${prenom}` : 'Un mot pour toi'}
                            testidAudio="wf-audio-essai-audio" testidBouton="wf-audio-essai-bouton" />
    </div>
  ) : null;

  // ── 1. Valider MA séance ──
  const seancesCal = seancesPourCalendrier(opts);
  const plusieurs = seancesCal.length > 1;
  const valider = (choixForce) => {
    if (validation) return;
    setErreurSeance('');
    lancerAudio();                                   // V610k : DANS le geste de l'utilisateur
    const c = (choixForce && choixForce.occurrence) ? choixForce : choix;
    const actuelle = seanceDuPass(pass);
    const change = c.occurrence && (c.occurrence !== actuelle.occurrence
      || (c.course_id && c.course_id !== actuelle.course_id));
    if (!change) {
      suivreInvitation(token, 'seance_choisie');
      setEcran('pret');
      return;
    }
    setValidation(true);
    changerSeance({ token, occurrence: c.occurrence, course_id: c.course_id, version: pass && pass.version })
      .then((r) => {
        const d = (r && r.data) || {};
        if (typeof onPass === 'function' && d.occurrence) onPass(d);
        suivreInvitation(token, 'seance_choisie');
        setEcran('pret');
      })
      .catch((e) => {
        const refus = lireRefus(e);
        // V610k : on reste sur l'accueil -> le message ne joue pas en coulisse ; il repartira
        // au prochain « Valider ma séance ».
        if (audioRef.current) audioRef.current.pause();
        audioTente.current = false;
        setErreurSeance(messageRefusMaSeance(refus));
        if (refus.raison === 'conflit_version') {
          // UNE relecture du pass (version à jour), jamais en boucle.
          axios.get(`${API_PARRAINAGE}/pass/${encodeURIComponent(token)}`, { timeout: 10000 })
            .then((rr) => { const d = (rr && rr.data) || {}; if (typeof onPass === 'function' && d.version) onPass(d); })
            .catch(() => {});
        }
      })
      .finally(() => setValidation(false));
  };

  // ── 2. Partage ──
  const enregistrer = (channel) => {
    setEnregistrement(true); setAReessayer('');
    return enregistrerPartageChaine({ token, channel })
      .then((r) => {
        const d = (r && r.data) || {};
        if (d.child && d.child.share_url) setChild((prev) => Object.assign({}, prev || {}, d.child));
        setAvis('');
        const n = nomAffichable(nom);
        if (typeof onPrenom === 'function' && n) onPrenom(n);
        setPartage(true);
      })
      .catch(() => { setAReessayer(channel); })
      .finally(() => setEnregistrement(false));
  };

  const texteDe = (c) => texteWhatsAppEssai({
    prenom: nomAffichable(nom) || (c && c.display_name) || '',
    occurrence: c && c.occurrence,
    lieu: c && c.course && c.course.locationName,
    url: c && c.share_url,
  });
  // Le prénom saisi n'est pas encore sur la carte de l'ami → enregistré AVANT le partage.
  const nomAEnregistrer = () => {
    const n = nomAffichable(nom);
    return !!(n && child && n !== nomAffichable(child.display_name));
  };
  const preparerEnfant = () => {
    if (!nomAEnregistrer()) return Promise.resolve(childRef.current);
    return modifierInvitationChaine({ token, editKey, display_name: nomAffichable(nom), message: (child && child.message) || MESSAGE_CHAINE_DEFAUT })
      .then((r) => {
        const d = (r && r.data) || {};
        const suivant = Object.assign({}, childRef.current || {}, d.child || {}, { display_name: nomAffichable(nom) });
        childRef.current = suivant;
        setChild(suivant);
        return suivant;
      });
  };
  const inactif = creation || enregistrement || !child || !editKey;

  /**
   * WhatsApp s'ouvre DANS le geste (sinon le navigateur bloque la fenêtre) :
   * lien prêt → ouverture directe ; prénom à enregistrer → fenêtre vide ouverte
   * tout de suite, adresse posée après l'enregistrement (fermée s'il échoue).
   */
  const surWhatsApp = () => {
    if (inactif || !child.share_url) return;
    setInfo('');
    if (!nomAEnregistrer()) {
      window.open(lienWhatsApp(texteDe(child)), '_blank', 'noopener');
      suivreInvitation(token, 'partage_whatsapp_declenche');
      enregistrer('whatsapp');
      return;
    }
    let fen = null;
    try { fen = window.open('', '_blank'); } catch (e) { fen = null; }
    if (fen) { try { fen.opener = null; } catch (e) { /* ignore */ } }
    preparerEnfant()
      .then((c) => {
        if (!fen) { setInfo('Ton prénom est enregistré. Touche encore « Inviter 1 ami sur WhatsApp ».'); return; }
        try { fen.location.href = lienWhatsApp(texteDe(c)); } catch (e) { /* ignore */ }
        suivreInvitation(token, 'partage_whatsapp_declenche');
        enregistrer('whatsapp');
      })
      .catch(() => {
        if (fen) { try { fen.close(); } catch (e) { /* ignore */ } }
        setInfo('Ton prénom n’a pas pu être enregistré. Vérifie-le ou efface-le, puis réessaie.');
      });
  };
  const nav = typeof navigator !== 'undefined' ? navigator : null;
  const peutPartager = !!(nav && typeof nav.share === 'function');
  const surAutrement = () => {
    if (inactif || !child.share_url) return;
    setInfo('');
    preparerEnfant()
      .then((c) => {
        const texte = texteDe(c);
        if (peutPartager) {
          return nav.share({ title: 'Afroboost', text: texte })
            .then(() => { suivreInvitation(token, 'partage_autre_declenche'); return enregistrer('share'); })
            .catch((e) => {
              if (e && e.name === 'AbortError') return;
              if (e && e.name === 'NotAllowedError') { setInfo('Touche encore « Partager autrement ».'); return; }
              setInfo('Le partage n’a pas abouti. Essaie WhatsApp.');
            });
        }
        return copier(texte).then((ok) => {
          if (!ok) { setInfo('Copie impossible : essaie WhatsApp.'); return undefined; }
          setInfo('Message et lien copiés : colle-les à ton ami.');
          suivreInvitation(token, 'partage_autre_declenche');
          return enregistrer('copy');
        });
      })
      .catch(() => setInfo('Ton prénom n’a pas pu être enregistré. Vérifie-le ou efface-le, puis réessaie.'));
  };

  // ── V607g — « INVITER ENCORE » : chaque ami reçoit SON lien (jamais le même) ──
  // Facultatif, après la confirmation. Le serveur crée une invitation neuve
  // (POST /chain/next) — ou rend la dernière jamais partagée (double clic).
  const [encore, setEncore] = useState(null);
  const [encoreEnCours, setEncoreEnCours] = useState(false);
  const [nbEncore, setNbEncore] = useState(0);
  const encoreVol = useRef(false);
  const partagerEncore = (c) => enregistrerPartageChaine({ token, channel: 'whatsapp', childToken: c.share_token })
    .then((r) => {
      const d = (r && r.data) || {};
      setEncore(Object.assign({}, c, d.child || {}, { shared: true }));
      setNbEncore((n) => n + 1);
      setInfo('Nouvelle invitation partagée : ton ami a son propre lien.');
    })
    .catch(() => setInfo('Ton partage n’a pas pu être enregistré. Réessaie.'));
  const surEncore = () => {
    if (encoreVol.current || !editKey) return;
    setInfo('');
    if (encore && !encore.shared && encore.share_url) {
      window.open(lienWhatsApp(texteDe(encore)), '_blank', 'noopener');
      suivreInvitation(token, 'partage_whatsapp_declenche');
      partagerEncore(encore);
      return;
    }
    encoreVol.current = true;
    setEncoreEnCours(true);
    let fen = null;
    try { fen = window.open('', '_blank'); } catch (e) { fen = null; }
    if (fen) { try { fen.opener = null; } catch (e) { /* ignore */ } }
    creerInvitationSuivante({ token })
      .then((r) => {
        const c = ((r && r.data) || {}).child;
        if (!c || !c.share_url) throw new Error('sans_lien');
        setEncore(c);
        if (!fen) { setInfo('Ta nouvelle invitation est prête. Touche encore « Inviter encore ».'); return undefined; }
        try { fen.location.href = lienWhatsApp(texteDe(c)); } catch (e) { /* ignore */ }
        suivreInvitation(token, 'partage_whatsapp_declenche');
        return partagerEncore(c);
      })
      .catch((e) => {
        if (fen) { try { fen.close(); } catch (x) { /* ignore */ } }
        const refus = lireRefus(e);
        setInfo(refus.raison === 'invitations_ouvertes_max'
          ? 'Tu as déjà plusieurs invitations en attente : attends qu’un ami s’inscrive.'
          : 'Impossible de créer une nouvelle invitation pour le moment. Réessaie plus tard.');
      })
      .finally(() => { encoreVol.current = false; setEncoreEnCours(false); });
  };

  const maSeance = seanceDuPass(pass);

  // ── 4. CONFIRMÉ ─────────────────────────────────────────────────────────
  if (confirme) {
    const c = (resultat && resultat.course) || (pass && pass.course) || {};
    const occ = (resultat && resultat.occurrence) || (pass && pass.occurrence);
    const heure = libelleHeure(occ);
    const espace = urlEspaceCourant();
    return (
      <div className="cp-wf" data-testid="wf-essai-confirme">
        <div className="cp-state" style={{ paddingTop: 10 }}>
          <div className="cp-roundic cp-roundic--ok"><SvgIcon name="check" size={38} strokeWidth="2.5" /></div>
          <h1 className="cp-h1 cp-center">Ton essai est <em className="cp-em">confirmé</em> !</h1>
        </div>
        <div className="cp-card" data-testid="wf-essai-confirme-seance">
          {c.name ? <div className="cp-eyebrow" style={{ marginTop: 0 }}>{c.name}</div> : null}
          <h3 className="cp-h3" style={{ marginTop: 4 }}>
            <SvgIcon name="calendar" size={20} /> {libelleJour(occ)}{heure ? ` · ${heure}` : ''}
          </h3>
          {c.locationName ? (
            <p style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              <SvgIcon name="mapPin" size={16} /> {c.locationName}
              {c.mapsUrl && /^https?:\/\//i.test(c.mapsUrl) ? (
                <a className="cp-link cp-wz-tap" href={c.mapsUrl} target="_blank" rel="noopener noreferrer">
                  Itinéraire <SvgIcon name="externalLink" size={14} />
                </a>
              ) : null}
            </p>
          ) : null}
        </div>
        <BilletsDuo tickets={(resultat && resultat.tickets) || []} vue="ami" />
        <p className="cp-center cp-fine">Tu recevras aussi ton billet par e-mail.</p>
        {editKey ? (
          <div className="cp-wf-encore-bloc">
            <p className="cp-wf-aide" style={{ marginTop: 12 }}>Tu peux inviter d’autres amis si tu veux.</p>
            <button type="button" className="cp-b cp-b--secondary cp-wz-cible" onClick={surEncore}
                    disabled={encoreEnCours} data-testid="wf-inviter-encore">
              <SvgIcon name="messageCircle" size={20} /> {encoreEnCours ? 'Un instant…' : 'Inviter encore'}
            </button>
            {nbEncore ? <p className="cp-fine" data-testid="wf-encore-compte">{nbEncore > 1 ? `${nbEncore} nouvelles invitations partagées` : '1 nouvelle invitation partagée'}</p> : null}
            {info ? <p className="cp-mini" role="status" data-testid="wf-info">{info}</p> : null}
          </div>
        ) : null}
        <a className="cp-b cp-b--ghost" href={espace || '/'} data-testid="invitation-retour-espace" style={{ marginTop: 12 }}>
          <SvgIcon name="arrowLeft" size={18} /> {espace ? 'Retour à mon espace' : 'Retour à l’accueil'}
        </a>
      </div>
    );
  }

  // ── 3. INSCRIPTION ──────────────────────────────────────────────────────
  if (ecran === 'inscription' && partage) {
    return (
      <div className="cp-wf" data-testid="wf-inscription">
        <h2 className="cp-wf-titre">Finalise ton inscription</h2>
        <LigneSeance seance={maSeance} />
        {editKey ? formulaire : <AutreAppareil />}
        <button type="button" className="cp-link cp-wz-tap cp-wz-retour" onClick={() => setEcran('pret')} data-testid="wf-retour">
          <SvgIcon name="arrowLeft" size={14} /> Retour
        </button>
      </div>
    );
  }

  // ── 2. ESSAI PRÊT : inviter 1 ami ───────────────────────────────────────
  if (ecran === 'pret' || ecran === 'inscription') {
    return (
      <div className="cp-wf" data-testid="wf-essai-pret">
        {blocAudio}
        <h2 className="cp-wf-titre">Ton essai est prêt !</h2>
        <LigneSeance seance={maSeance} />
        <p className="cp-wf-aide" data-testid="wf-essai-pret-texte">
          Pour le débloquer, invite à ton tour une personne à découvrir Afroboost.
        </p>
        {avis ? <p className="cp-notice" role="alert" data-testid="wf-avis">{avis}</p> : null}
        {erreurCreation ? (
          <div data-testid="wf-erreur-creation">
            <p className="cp-error" role="alert">{erreurCreation}</p>
            <button type="button" className="cp-b cp-b--secondary cp-wz-cible" onClick={creer} data-testid="wf-reessayer-creation">
              <SvgIcon name="refresh" size={20} /> Réessayer
            </button>
          </div>
        ) : null}
        {!erreurCreation && creation ? (
          <p className="cp-mini cp-wf-prep" role="status" data-testid="wf-preparation">
            <span className="cp-spinner cp-wf-spin" aria-hidden="true" /> Préparation de ton invitation…
          </p>
        ) : null}
        {child && !editKey ? <AutreAppareil /> : null}
        {child && editKey ? (
          <>
            <label className="cp-label" htmlFor="wf-nom">Ton prénom</label>
            <input id="wf-nom" className="cp-input" value={nom} maxLength={NOM_MAX} placeholder="Ex. : Henri"
                   onChange={(e) => setNom(e.target.value.slice(0, NOM_MAX))} autoComplete="given-name" data-testid="wf-nom" />
            <p className="cp-fine">Ton ami verra que l’invitation vient de toi.</p>
            <button type="button" className="cp-b cp-b--whatsapp cp-wz-cible" onClick={surWhatsApp} disabled={inactif}
                    data-testid="wf-inviter-whatsapp" style={{ marginTop: 12 }}>
              <SvgIcon name="messageCircle" size={20} /> Inviter 1 ami sur WhatsApp
            </button>
            <p className="cp-fine" data-testid="wf-texte-lien">Ton ami recevra son propre lien d’invitation.</p>
            <button type="button" className="cp-link cp-wz-tap" onClick={surAutrement} disabled={inactif}
                    data-testid="wf-partager-autrement">
              <SvgIcon name={peutPartager ? 'share' : 'link'} size={14} /> {peutPartager ? 'Partager autrement' : 'Copier le message'}
            </button>
          </>
        ) : null}
        {enregistrement ? <p className="cp-mini" role="status">Un instant…</p> : null}
        {info ? <p className="cp-mini" role="status" data-testid="wf-info">{info}</p> : null}
        {aReessayer ? (
          <div data-testid="wf-erreur-partage">
            <p className="cp-error" role="alert">Ton partage n’a pas pu être enregistré. Réessaie pour débloquer ton essai.</p>
            <button type="button" className="cp-b cp-b--secondary cp-wz-cible" onClick={() => enregistrer(aReessayer)}
                    disabled={enregistrement} data-testid="wf-reessayer-partage">
              <SvgIcon name="refresh" size={20} /> Réessayer
            </button>
          </div>
        ) : null}
        {partage ? (
          <p className="cp-ok-text" role="status" data-testid="wf-partage-ok">
            Invitation partagée. Tu peux finaliser ton inscription.
          </p>
        ) : null}
        <button type="button" className="cp-b cp-wz-cible cp-wf-cta" onClick={() => { setInfo(''); setEcran('inscription'); }}
                disabled={!partage} aria-disabled={!partage} data-testid="wf-finaliser">
          Finaliser mon inscription <SvgIcon name="arrowRight" size={20} />
        </button>
        {!chainePub.exists && !partage ? (
          <button type="button" className="cp-link cp-wz-tap cp-wz-retour" onClick={() => setEcran('accueil')} data-testid="wf-retour">
            <SvgIcon name="arrowLeft" size={14} /> Changer ma séance
          </button>
        ) : null}
      </div>
    );
  }

  // ── 1. ACCUEIL : qui m'invite, Afroboost, MA séance ─────────────────────
  return (
    <div className="cp-wf" data-testid="wf-essai-accueil">
      {blocAudio}
      <CarteInvitation testid="wf-invitation-recue" prenom={prenom} photo={photo} type="trial"
                       occurrence={choix.occurrence} cours={choix.nom} lieu={choix.lieu} />
      <p className="cp-wf-rappel" data-testid="wf-pitch">
        <SvgIcon name="headphones" size={16} /> <span>{PITCH_AFROBOOST}</span>
      </p>
      <p className="cp-wf-rappel" data-testid="wf-offert">
        <SvgIcon name="gift" size={16} /> <span>Ton premier cours est offert.</span>
      </p>
      {plusieurs ? (
        <button type="button" className="cp-link cp-wz-tap" onClick={() => { setErreurSeance(''); setCalendrier(true); }}
                data-testid="wf-ma-seance-changer">
          <SvgIcon name="calendar" size={14} /> Choisir une autre date
        </button>
      ) : null}
      {erreurSeance ? <p className="cp-error" role="alert" data-testid="wf-seance-erreur">{erreurSeance}</p> : null}
      {calendrier ? (
        <SessionsModal
          open
          onClose={() => setCalendrier(false)}
          occurrencesFournies={seancesCal}
          libelleAction="Valider ma séance"
          noteAction="C’est ta séance d’essai : tu passes directement à ton essai."
          onReserve={(occ) => {
            if (!occ || !occ.iso) return;
            // V610k : choisir ICI vaut validation — plus de retour à l'accueil pour revalider.
            const nouveau = { course_id: occ.id, occurrence: occ.iso, nom: occ.nom || '', lieu: occ.lieu || '' };
            setChoix(nouveau);
            setErreurSeance(''); setCalendrier(false);
            valider(nouveau);
          }}
        />
      ) : null}
      <button type="button" className="cp-b cp-wz-cible cp-wf-cta" onClick={() => valider()} disabled={validation || !choix.occurrence}
              data-testid="wf-valider-seance">
        {validation ? 'Un instant…' : 'Valider ma séance'} <SvgIcon name="arrowRight" size={20} />
      </button>
      <p className="cp-wf-regle" data-testid="wf-regle-essai">
        <SvgIcon name="info" size={14} /> L’essai gratuit est disponible une seule fois par personne.
      </p>
    </div>
  );
}
