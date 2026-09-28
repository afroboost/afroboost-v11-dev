/**
 * V556 — PARRAINAGE V3 « BOULE DE NEIGE » : LE PARCOURS DU FILLEUL.
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
 */
import React, { useEffect, useRef, useState } from 'react';
import SvgIcon from '../SvgIcon';
import {
  MESSAGE_CHAINE_DEFAUT, MESSAGE_MAX, NOM_MAX, bornerMessage, nomAffichable,
  creerInvitationChaine, modifierInvitationChaine, enregistrerPartageChaine,
  verifierApercuNavigateur, lireCleChaine, ecrireCleChaine, lireRefus, messageRefus,
  lienWhatsApp, copier, texteChaine, libelleOccurrence,
} from '../../utils/parrainage';
import './invitationWizard.css'; // V556 : cibles 44 px (cp-wz-tap / cp-wz-cible) et cadre de carte, absents de /duo sinon
import './wizardFilleul.css';

const ETAPES = ['Ton invitation', 'Invite un ami', 'Ton essai'];

function Etapes({ etape }) {
  return (
    <ol className="cp-wz-etapes cp-wf-etapes" aria-label={`Étape ${etape} sur 3`} data-testid="wf-etapes">
      {ETAPES.map((t, i) => {
        const n = i + 1;
        const cls = n === etape ? 'on' : (n < etape ? 'fait' : '');
        return (
          <li key={t} className={cls} aria-current={n === etape ? 'step' : undefined}>
            <span>{n < etape ? <SvgIcon name="check" size={12} strokeWidth="3" /> : n}</span>{t}
          </li>
        );
      })}
    </ol>
  );
}

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

/**
 * @param {string}   token          le jeton du pass reçu (T0)
 * @param {object}   pass           le PassDTO public (chain, course, occurrence…)
 * @param {string}   prenom         le prénom affichable du parrain
 * @param {string}   photo          sa photo autorisée, ou null
 * @param {node}     blocInvitation la séance + l'offre (rendus par InvitationDuo)
 * @param {node}     formulaire     le formulaire d'inscription (rendu par InvitationDuo)
 * @param {function} onPrenom       (prénom saisi à l'étape 2) → préremplit l'inscription
 * @param {number}   retourEtape2   compteur : chaque incrément ramène à l'étape 2 (409 invitation_requise)
 * @param {string}   messageEtape2  message affiché à l'étape 2 après ce retour
 */
export default function WizardFilleul({
  token, pass, prenom, photo, blocInvitation, formulaire, onPrenom, retourEtape2, messageEtape2,
}) {
  const dejaPartagee = !!(pass && pass.chain && pass.chain.shared === true);
  const [etape, setEtape] = useState(dejaPartagee ? 3 : 1);
  const [child, setChild] = useState(null);
  const [editKey, setEditKey] = useState(() => lireCleChaine(token));
  const [creation, setCreation] = useState(false);
  const [erreurCreation, setErreurCreation] = useState('');
  const [nom, setNom] = useState('');
  const [message, setMessage] = useState('');
  const [messageOuvert, setMessageOuvert] = useState(false);
  const [maj, setMaj] = useState(false);
  const [erreurMaj, setErreurMaj] = useState('');
  const [verif, setVerif] = useState({ cle: '', ok: false, file: null }); // contrôle navigateur
  const [carteKo, setCarteKo] = useState(false);
  const [enregistrement, setEnregistrement] = useState(false);
  const [aReessayer, setAReessayer] = useState(''); // canal dont l'enregistrement a échoué
  const [info, setInfo] = useState('');
  const [avis, setAvis] = useState(''); // message venu d'InvitationDuo (409 invitation_requise)
  const enVol = useRef(false);

  // 409 invitation_requise au join → retour à l'étape 2 (vérité serveur).
  useEffect(() => {
    if (!retourEtape2) return;
    setEtape(2);
    setAvis(messageEtape2 || messageRefus('invitation_requise'));
  }, [retourEtape2, messageEtape2]);

  const poserChild = (c) => {
    if (!c || !c.share_url) return;
    setChild(c);
    setNom(nomAffichable(c.display_name) || '');
    setMessage(typeof c.message === 'string' && c.message.trim() ? bornerMessage(c.message) : MESSAGE_CHAINE_DEFAUT);
    setCarteKo(false);
  };

  // ÉTAPE 2 : l'invitation enfant est créée (ou relue, idempotent) AVANT tout partage.
  const aUnChild = !!child;
  const creer = () => {
    if (enVol.current) return;
    enVol.current = true;
    setCreation(true); setErreurCreation('');
    creerInvitationChaine({ token, message: MESSAGE_CHAINE_DEFAUT })
      .then((r) => {
        const d = (r && r.data) || {};
        if (d.edit_key) { ecrireCleChaine(token, d.edit_key); setEditKey(String(d.edit_key)); }
        poserChild(d.child ? Object.assign({}, d.child, d.preview ? { preview: d.preview } : {}) : null);
        if (!d.child) setErreurCreation(messageErreurChaine({}));
      })
      .catch((e) => { setErreurCreation(messageErreurChaine(lireRefus(e))); })
      .finally(() => { enVol.current = false; setCreation(false); });
  };
  useEffect(() => {
    if (etape === 2 && !aUnChild) creer();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [etape, aUnChild, token]);

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

  const preparation = creation || !child || verif.cle !== cleVerif;
  // L'aperçu serveur voyage à côté de `child` (réponse POST/PATCH) : on le range dessus.
  // Absent (serveur ancien) : on ne pénalise pas, seul le contrôle navigateur tranche.
  const serveurOk = !(child && child.preview && child.preview.ok === false);
  const apercuSimplifie = !preparation && (!verif.ok || !serveurOk || carteKo);

  const nomValide = nomAffichable(nom);
  const nomChild = child ? (nomAffichable(child.display_name) || '') : '';
  const msgChild = child ? ((typeof child.message === 'string' && child.message.trim()) ? bornerMessage(child.message) : MESSAGE_CHAINE_DEFAUT) : '';
  const modifie = !!child && (nom.trim() !== nomChild || message !== msgChild);
  const editable = !!editKey;
  // V556 : sans la clé de CET appareil, le serveur refuse le partage (403) — on le dit.
  const boutonsInactifs = preparation || modifie || enregistrement || maj || !editable;

  const mettreAJour = () => {
    if (!child || !editable || maj) return;
    if (nom.trim() && !nomValide) { setErreurMaj('Indique un prénom (sans adresse e-mail).'); return; }
    setMaj(true); setErreurMaj('');
    modifierInvitationChaine({ token, editKey, display_name: nom, message })
      .then((r) => {
        const d = (r && r.data) || {};
        if (d.child) poserChild(Object.assign({}, d.child, d.preview ? { preview: d.preview } : {}));
        setInfo('Ta carte est à jour.');
      })
      .catch((e) => {
        const refus = lireRefus(e);
        if (refus.status === 403) setEditKey('');
        setErreurMaj(messageErreurChaine(refus));
      })
      .finally(() => setMaj(false));
  };

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
        if (typeof onPrenom === 'function' && nomValide) onPrenom(nomValide);
        setEtape(3);
      })
      .catch(() => { setAReessayer(channel); })
      .finally(() => setEnregistrement(false));
  };

  const texte = texteChaine(message, shareUrl);
  const surWhatsApp = () => {
    if (boutonsInactifs || !shareUrl) return;
    window.open(lienWhatsApp(texte), '_blank', 'noopener'); // synchrone : geste utilisateur
    enregistrer('whatsapp');
  };
  const nav = typeof navigator !== 'undefined' ? navigator : null;
  const peutPartager = !!(nav && typeof nav.share === 'function');
  let peutCarte = false;
  if (peutPartager && verif.file && typeof nav.canShare === 'function') {
    try { peutCarte = !!nav.canShare({ files: [verif.file] }); } catch (e) { peutCarte = false; }
  }
  const apresShare = (channel) => (p) => Promise.resolve(p)
    .then(() => enregistrer(channel))
    .catch((e) => {
      if (e && e.name === 'AbortError') return; // annulé : rien
      setInfo('Le partage n’a pas abouti. Essaie WhatsApp ou copie le lien.');
    });
  const surPartagerCarte = () => {
    if (boutonsInactifs || !peutCarte) return;
    let p;
    try { p = nav.share({ files: [verif.file], text: texte }); } catch (e) { p = Promise.reject(e); }
    apresShare('share_image')(p);
  };
  const surPartager = () => {
    if (boutonsInactifs || !peutPartager) return;
    let p;
    try { p = nav.share({ title: 'Afroboost', text: message, url: shareUrl }); } catch (e) { p = Promise.reject(e); }
    apresShare('share')(p);
  };
  const surCopier = () => {
    if (boutonsInactifs || !shareUrl) return;
    copier(shareUrl).then((ok) => {
      if (ok) { setInfo('Lien copié'); enregistrer('copy'); } else setInfo('Copie impossible : réessaie ou choisis WhatsApp.');
    });
  };

  // ── ÉTAPE 1 ────────────────────────────────────────────────────────────────
  if (etape === 1) {
    return (
      <div className="cp-wf" data-testid="wf-etape-1">
        <Etapes etape={1} />
        <div className="cp-wf-qui">
          {photo ? (
            <div className="cp-av cp-wz-av cp-wf-av"><img src={photo} alt="" data-testid="invitation-photo" /></div>
          ) : (
            <div className="cp-av cp-wf-av" aria-hidden="true">{(prenom || '?').charAt(0).toUpperCase()}</div>
          )}
          <div className="cp-wf-qui-txt">
            <span className="cp-chip">Pass Duo</span>
            <h1 className="cp-h1 cp-wf-h1" data-testid="invitation-de">{prenom} t'invite à découvrir Afroboost.</h1>
          </div>
        </div>
        <p className="cp-lead cp-wf-lead">Pour débloquer ton essai gratuit, invite à ton tour un ami.</p>
        {blocInvitation}
        {/* collant en bas d'écran : [Continuer] est visible dès le premier écran */}
        <button type="button" className="cp-b cp-wz-cible cp-wf-cta" onClick={() => setEtape(2)} data-testid="wf-continuer">
          Continuer <SvgIcon name="arrowRight" size={20} />
        </button>
      </div>
    );
  }

  // ── ÉTAPE 3 ────────────────────────────────────────────────────────────────
  if (etape === 3) {
    const c = (pass && pass.course) || {};
    return (
      <div className="cp-wf" data-testid="wf-etape-3">
        <Etapes etape={3} />
        <div className="cp-wf-ok" role="status">
          <span className="cp-wf-ok-ic"><SvgIcon name="check" size={22} strokeWidth="2.5" /></span>
          <div>
            <b>Invitation prête</b>
            <p>Ton essai gratuit est maintenant débloqué.</p>
          </div>
        </div>
        <p className="cp-wf-rappel" data-testid="wf-rappel-seance">
          <SvgIcon name="calendar" size={16} />
          <span>{c.name ? `${c.name} · ` : ''}{libelleOccurrence(pass && pass.occurrence, c.locationName)}</span>
        </p>
        {formulaire}
        <button type="button" className="cp-link cp-wz-tap cp-wf-encore" onClick={() => { setInfo(''); setEtape(2); }} data-testid="wf-partager-encore">
          <SvgIcon name="share" size={14} /> Partager encore
        </button>
      </div>
    );
  }

  // ── ÉTAPE 2 ────────────────────────────────────────────────────────────────
  return (
    <div className="cp-wf" data-testid="wf-etape-2">
      <Etapes etape={2} />
      <h2 className="cp-wf-titre">Invite un ami</h2>
      <p className="cp-mini cp-wf-sous">Ton ami reçoit la même invitation que toi : un essai gratuit, à deux.</p>
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

      {child && cardUrl && !carteKo ? (
        <div className="cp-wz-carte cp-wf-carte" data-testid="wf-carte">
          <img src={cardUrl} alt="La carte d'invitation que ton ami verra" onError={() => setCarteKo(true)} />
        </div>
      ) : null}
      {apercuSimplifie ? <p className="cp-fine cp-wf-simplifie" data-testid="wf-apercu-simplifie">Aperçu simplifié : le lien reste valable.</p> : null}

      {child ? (
        <div className="cp-wf-perso">
          <label className="cp-label" htmlFor="wf-nom">Ton prénom (sur ta carte)</label>
          <input id="wf-nom" className="cp-input" value={nom} maxLength={NOM_MAX} disabled={!editable} placeholder="Ex. : Henri"
                 onChange={(e) => setNom(e.target.value.slice(0, NOM_MAX))} autoComplete="given-name" data-testid="wf-nom" />
          {editable && !nomChild ? (
            <p className="cp-fine" data-testid="wf-astuce-prenom">Ajoute ton prénom : ton ami verra « {nomValide || 'Henri'} t'invite » sur la carte.</p>
          ) : null}
          {messageOuvert ? (
            <>
              <label className="cp-label" htmlFor="wf-message">Ton message</label>
              <textarea id="wf-message" className="cp-input cp-wz-message cp-wf-message" rows={3} value={message}
                        maxLength={MESSAGE_MAX} disabled={!editable}
                        onChange={(e) => setMessage(bornerMessage(e.target.value))} data-testid="wf-message" />
              <p className="cp-fine cp-wz-compteur">{message.length}/{MESSAGE_MAX}</p>
            </>
          ) : (
            <button type="button" className="cp-link cp-wz-tap cp-wf-lien" onClick={() => setMessageOuvert(true)} data-testid="wf-modifier-message">
              <SvgIcon name="edit" size={14} /> Modifier le message
            </button>
          )}
          {!editable ? <p className="cp-fine">Ton invitation a été préparée sur un autre appareil : termine ton parcours depuis celui-ci.</p> : null}
          {modifie && editable ? (
            <button type="button" className="cp-b cp-b--secondary cp-wz-cible" onClick={mettreAJour} disabled={maj} data-testid="wf-mettre-a-jour">
              <SvgIcon name="refresh" size={20} /> {maj ? 'Mise à jour…' : 'Mettre à jour ma carte'}
            </button>
          ) : null}
          {erreurMaj ? <p className="cp-error" role="alert" data-testid="wf-erreur-maj">{erreurMaj}</p> : null}
        </div>
      ) : null}

      {child ? (
        <div className="cp-wf-actions">
          <button type="button" className="cp-b cp-b--whatsapp cp-wz-cible" onClick={surWhatsApp} disabled={boutonsInactifs} data-testid="wf-whatsapp">
            <SvgIcon name="messageCircle" size={20} /> WhatsApp
          </button>
          {peutCarte ? (
            <button type="button" className="cp-b cp-wz-cible" onClick={surPartagerCarte} disabled={boutonsInactifs} data-testid="wf-partager-carte">
              <SvgIcon name="image" size={20} /> Partager avec la carte
            </button>
          ) : null}
          <div className="cp-share cp-wf-share">
            {peutPartager ? (
              <button type="button" className="cp-b cp-b--secondary cp-wz-cible" onClick={surPartager} disabled={boutonsInactifs} data-testid="wf-partager">
                <SvgIcon name="share" size={20} /> Partager
              </button>
            ) : null}
            <button type="button" className={`cp-b cp-b--secondary cp-wz-cible${peutPartager ? '' : ' cp-wf-seul'}`} onClick={surCopier} disabled={boutonsInactifs} data-testid="wf-copier">
              <SvgIcon name="link" size={20} /> Copier le lien
            </button>
          </div>
          {modifie && editable ? <p className="cp-fine" data-testid="wf-valider-avant">Mets à jour ta carte avant de la partager.</p> : null}
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
        </div>
      ) : null}

      <button type="button" className="cp-link cp-wz-tap cp-wz-retour" onClick={() => setEtape(1)} data-testid="wf-retour">
        <SvgIcon name="arrowLeft" size={14} /> Retour
      </button>
    </div>
  );
}
