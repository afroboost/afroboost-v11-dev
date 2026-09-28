/**
 * V551 — PARRAINAGE V2 : L'ASSISTANT D'INVITATION DU MEMBRE.
 *
 * TROIS ÉTAPES, JAMAIS UNE DE PLUS (mobile d'abord) :
 *   1. « Ton invitation » — photo + nom préremplis (profil Spordateur lié,
 *      sinon l'identité de GET /invitation, sinon « Un membre Afroboost »),
 *      « Modifier » pour CETTE invitation seulement, et — à la création — le
 *      petit sélecteur séance/offre EXISTANT (useChoixSeance / ChampsSeanceOffre
 *      de PassDuoCard, jamais un second formulaire) ;
 *   2. « Personnaliser » — le message (≤ 280, compteur), prérempli ;
 *   3. « Aperçu & partager » — l'aperçu réel, puis WhatsApp (prioritaire),
 *      Partager, Copier le lien ; le QR reste une action secondaire.
 *
 * UN PASS OUVERT EXISTE DÉJÀ → on n'en crée JAMAIS un autre : « Ton invitation
 * est prête » + partage + « Modifier » (PUT /pass/{id}/invitation). Le jeton
 * ne change pas ; le `share_url` renvoyé (qui peut porter `?v=`) est celui
 * qu'on partage ensuite.
 *
 * CE QUE L'ASSISTANT NE FAIT JAMAIS : écrire dans un profil (unified-profile
 * est LU, jamais PATCHé), afficher un e-mail comme nom, téléverser une photo.
 *
 * RÉSEAU : une lecture au montage (GET /invitation + GET unified-profile, en
 * parallèle, en-tête `enteteParrain()`), puis uniquement sur geste (POST ou
 * PUT). Le parent reçoit le PassDTO renvoyé (`onPass`) et journalise les
 * partages (`onJournal`).
 *
 * V552 — LA VRAIE CARTE : quand le pass porte `card_url` (l'og:image exacte,
 * …/api/share/duo/<jeton>/carte.jpg?v=<version>), l'aperçu MONTRE cette image
 * (ratio 1200:630) puis titre, message et séance. Sans pass ou sans card_url,
 * l'aperçu reconstruit reste, avec « La carte finale est générée à l'envoi ».
 * Image en erreur → retour à l'aperçu reconstruit (jamais d'image cassée).
 * Les petites actions (Modifier, QR…) ont une cible tactile ≥ 44 px
 * (invitationWizard.css, classes `cp-wz-tap` / `cp-wz-cible`).
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import SvgIcon from '../SvgIcon';
import ConditionsParticipation from '../ConditionsParticipation';
import { useChoixSeance, ChampsSeanceOffre } from './PassDuoCard';
import './invitationWizard.css';
import {
  API_PARRAINAGE, enteteParrain, lireInvitation, identitePreremplie, messagePrerempli, corpsInvitation,
  modifierInvitation, nomAffichable, bornerMessage, texteWhatsAppInvitation, lienWhatsApp, copier, partager,
  libelleOccurrence, offreDuPass, NOM_NEUTRE, MESSAGE_MAX, NOM_MAX,
} from '../../utils/parrainage';

const ETAPES = ['Ton invitation', 'Personnaliser', 'Aperçu & partager'];

/** Le lien sans protocole, pour l'afficher comme un code. */
function lienCourt(url) {
  return String(url || '').replace(/^https?:\/\//, '');
}

/** Version de l'invitation portée par un pass (0 si jamais personnalisée). */
function versionInvitation(p) {
  return Number(p && p.invitation && p.invitation.version) || 0;
}

/** L'avatar : la photo si elle existe, sinon l'initiale (ou l'icône pour le nom neutre). */
function Avatar({ photo, nom, taille }) {
  const initiale = nom ? nom.charAt(0).toUpperCase() : '';
  return (
    <div className="cp-av cp-wz-av" style={taille ? { width: taille, height: taille } : undefined}>
      {photo
        ? <img src={photo} alt="" data-testid="wizard-photo" />
        : <span data-testid="wizard-initiale">{initiale || <SvgIcon name="user" size={26} />}</span>}
    </div>
  );
}

/** V552 — la carte du pass (card_url), si le serveur l'a fournie en https. */
function carteDuPass(p) {
  const u = p && typeof p.card_url === 'string' ? p.card_url.trim() : '';
  return /^https:\/\//i.test(u) ? u : '';
}

/**
 * L'aperçu tel que l'ami le verra (titre, message, séance, offre, visuel).
 * V552 : `carte` (card_url) = l'og:image exacte, montrée telle quelle ; si elle
 * échoue au chargement, on retombe sur le visuel reconstruit.
 */
export function ApercuInvitation({ nom, photo, message, seance, offre, image, carte }) {
  const affiche = nom || NOM_NEUTRE;
  const [carteEnEchec, setCarteEnEchec] = useState(''); // l'URL qui a échoué (une chaîne, jamais un objet)
  const carteVisible = !!carte && carteEnEchec !== carte;
  return (
    <div className="cp-apercu" data-testid="wizard-apercu" data-carte={carteVisible ? 'vraie' : 'reconstruite'}>
      {carteVisible ? (
        <div className="cp-wz-carte">
          <img src={carte} alt="Aperçu de ton invitation" width="1200" height="630" decoding="async"
               onError={() => setCarteEnEchec(carte)} data-testid="wizard-apercu-carte" />
        </div>
      ) : (
        <div className="cp-apercu-visuel">
          {image
            ? <img src={image} alt="" data-testid="wizard-apercu-image" />
            : <div className="cp-apercu-visuel-defaut" aria-hidden="true"><SvgIcon name="users" size={40} /></div>}
        </div>
      )}
      <div className="cp-apercu-corps">
        <div className="cp-apercu-qui">
          <Avatar photo={photo} nom={nom} taille={40} />
          <b>{affiche} t'invite à Afroboost</b>
        </div>
        {message ? <p className="cp-apercu-message">{message}</p> : null}
        {seance ? (
          <p className="cp-apercu-seance"><SvgIcon name="calendar" size={14} /> {seance}</p>
        ) : null}
        {offre ? (
          <p className="cp-apercu-seance"><SvgIcon name="gift" size={14} /> {offre}</p>
        ) : null}
        {!carteVisible ? (
          <p className="cp-apercu-seance cp-wz-carte-a-venir" data-testid="wizard-carte-a-venir">
            La carte finale est générée à l'envoi
          </p>
        ) : null}
      </div>
    </div>
  );
}

/**
 * @param {object[]} courses        les cours éligibles de GET /config
 * @param {object}   passOuvert     le pass ouvert connu du parent (ou null)
 * @param {object}   contexte       `{course, occurrence, offer}` (URL de /parrainage)
 * @param {boolean}  creationForcee le parent demande un NOUVEAU pass (après un pass débloqué/fermé)
 * @param {function} onRetour       quitter la création forcée
 * @param {function} onPass(dto)    PassDTO renvoyé par POST /pass ou PUT /invitation
 * @param {function} onJournal(pass, channel)  journal des partages (POST /invitations côté parent)
 * @param {function} onQr(pass, url)           ouvrir le QR (action secondaire)
 */
export default function InvitationWizard({
  courses, passOuvert, contexte, creationForcee, onRetour, onPass, onJournal, onQr,
}) {
  const [donnees, setDonnees] = useState(null); // null = lecture en cours
  const [passLocal, setPassLocal] = useState(null);
  const [edition, setEdition] = useState(false);
  const [etape, setEtape] = useState(1);
  const [identiteOuverte, setIdentiteOuverte] = useState(false);
  const [nomSaisi, setNomSaisi] = useState(null);       // null = prérempli
  const [photoRetiree, setPhotoRetiree] = useState(false);
  const [messageSaisi, setMessageSaisi] = useState(null); // null = prérempli
  const [conditionsOk, setConditionsOk] = useState(false);
  const [conditionsRequises, setConditionsRequises] = useState(false);
  const [occupe, setOccupe] = useState(false);
  const [erreur, setErreur] = useState('');
  const [feedback, setFeedback] = useState('');
  const choix = useChoixSeance(courses, contexte);

  // UNE lecture au montage, jamais relancée (aucune dépendance objet).
  useEffect(() => {
    let vivant = true;
    lireInvitation(enteteParrain()).then((d) => { if (vivant) setDonnees(d); });
    return () => { vivant = false; };
  }, []);

  useEffect(() => {
    if (!feedback) return undefined;
    const t = setTimeout(() => setFeedback(''), 2600);
    return () => clearTimeout(t);
  }, [feedback]);

  if (!donnees) {
    return (
      <div className="cp-card" data-testid="wizard-chargement">
        <p className="cp-mini">Ton invitation se prépare…</p>
      </div>
    );
  }

  // Le pass ouvert : celui du parent, sinon celui de /invitation. Entre deux
  // copies du MÊME pass, la plus récente invitation gagne (le parent garde les
  // statuts à jour, la réponse du PUT porte le nouveau `share_url`).
  let pass = passOuvert || null;
  if (passLocal && (!pass || pass.id === passLocal.id)) {
    if (!pass || versionInvitation(passLocal) > versionInvitation(pass)) pass = passLocal;
  }
  if (!pass) pass = passLocal || donnees.pass || null;
  const creation = !pass || !!creationForcee;
  const passRef = creation ? null : pass;

  const prerempli = identitePreremplie({ pass: passRef, profil: donnees.profil, identity: donnees.identity });
  const nomBrut = nomSaisi != null ? nomSaisi : prerempli.nom;
  const nomValide = nomAffichable(nomBrut);
  const nomRefuse = nomSaisi != null && nomSaisi.trim() !== '' && !nomValide;
  const photo = photoRetiree ? null : prerempli.photo;
  const message = messageSaisi != null ? messageSaisi : messagePrerempli({ pass: passRef, default_message: donnees.default_message });

  // Séance / offre montrées dans l'aperçu.
  let seance = '';
  let offreNom = '';
  let offreImage = '';
  if (creation) {
    const c = (Array.isArray(courses) ? courses : []).find((x) => x && String(x.id) === String(choix.coursChoisi)) || {};
    seance = choix.occurrence ? `${c.name ? `${c.name} · ` : ''}${libelleOccurrence(choix.occurrence, c.locationName)}` : '';
    const o = choix.offres.find((x) => String(x.id) === String(choix.offreChoisie));
    offreNom = o ? o.name : '';
    offreImage = (o && (o.image_url || o.image)) || c.image_url || c.image || '';
  } else {
    const c = pass.course || {};
    seance = `${c.name ? `${c.name} · ` : ''}${libelleOccurrence(pass.occurrence, c.locationName)}`;
    const o = offreDuPass(pass);
    offreNom = o ? o.name : '';
    offreImage = (o && (o.image_url || o.image)) || c.image_url || c.image || '';
  }
  const image = donnees.image_url || offreImage || '';
  // V552 : la carte réelle du pass. Repli sur celle de GET /invitation → pass
  // seulement si c'est le MÊME pass à la MÊME version (jamais une carte périmée).
  let carte = passRef ? carteDuPass(passRef) : '';
  if (!carte && passRef && donnees.pass && donnees.pass.id === passRef.id
      && versionInvitation(donnees.pass) === versionInvitation(passRef)) {
    carte = carteDuPass(donnees.pass);
  }
  const apercu = (
    <ApercuInvitation key={carte || 'reconstruit'} nom={nomValide} photo={photo} message={message}
                      seance={seance} offre={offreNom} image={image} carte={carte} />
  );

  const reinitialiser = () => {
    setEtape(1); setIdentiteOuverte(false); setNomSaisi(null); setPhotoRetiree(false); setMessageSaisi(null);
    setErreur('');
  };

  // ── Partage (pass existant) ────────────────────────────────────────────────
  const lien = pass ? (pass.share_url || pass.invite_url || '') : '';
  const journal = (canal) => { if (typeof onJournal === 'function') onJournal(pass, canal); };
  const surWhatsApp = () => {
    if (!lien) return;
    window.open(lienWhatsApp(texteWhatsAppInvitation(pass, message)), '_blank', 'noopener');
    journal('whatsapp');
  };
  const surPartager = () => {
    if (!lien) return;
    partager({ title: `${nomValide || NOM_NEUTRE} t'invite à Afroboost`, text: message || '', url: lien })
      .then((r) => {
        if (!r.ok) return;
        if (r.methode === 'copie') setFeedback('Lien copié');
        journal(r.methode === 'copie' ? 'copy' : 'share');
      });
  };
  const surCopier = () => {
    if (!lien) return;
    copier(lien).then((ok) => {
      setFeedback(ok ? 'Lien copié' : 'Copie impossible : sélectionne le lien à la main');
      if (ok) journal('copy');
    });
  };

  // ── Écritures ─────────────────────────────────────────────────────────────
  const invitation = () => corpsInvitation({ nom: nomBrut, photo, message });

  const creer = () => {
    if (occupe || !choix.valeur || choix.offreManquante) return;
    if (conditionsRequises && !conditionsOk) return;
    setOccupe(true); setErreur('');
    const corps = { course_id: choix.coursChoisi, occurrence: choix.occurrence, terms_accepted: conditionsOk === true };
    if (choix.offresConnues && choix.offreChoisie) corps.offer_id = choix.offreChoisie;
    corps.invitation = invitation();
    axios.post(`${API_PARRAINAGE}/pass`, corps, { headers: enteteParrain() })
      .then((r) => {
        const dto = r && r.data;
        if (dto && dto.id) {
          setPassLocal(dto);
          if (typeof onPass === 'function') onPass(dto);
        }
        reinitialiser();
        setFeedback(dto && dto.deja_existant ? 'Tu as déjà un Pass Duo pour cette séance' : 'Ton invitation est prête');
      })
      .catch((e) => {
        const s = e && e.response && e.response.status;
        const detail = String((e && e.response && e.response.data && e.response.data.detail) || '');
        setErreur(s === 400 && /^offre_/.test(detail)
          ? 'Cette offre n’est plus disponible pour cette séance. Choisis-en une autre.'
          : s === 400 ? 'Cette séance n’est pas ouverte au Pass Duo.'
            : s === 422 ? 'Ce nom ou ce message n’est pas accepté. Corrige-le puis réessaie.'
              : s === 429 ? 'Trop de tentatives. Réessaie dans un instant.'
                : 'Création impossible pour le moment.');
      })
      .finally(() => setOccupe(false));
  };

  const enregistrer = () => {
    if (occupe || !pass) return;
    setOccupe(true); setErreur('');
    modifierInvitation({ passId: pass.id, invitation: invitation(), headers: enteteParrain() })
      .then((r) => {
        const dto = r && r.data;
        if (dto && dto.id) {
          setPassLocal(dto);
          if (typeof onPass === 'function') onPass(dto);
        }
        reinitialiser(); setEdition(false);
        setFeedback('Invitation mise à jour');
      })
      .catch((e) => {
        const s = e && e.response && e.response.status;
        setErreur(s === 409 ? 'Ce Pass ne peut plus être modifié.'
          : s === 422 || s === 400 ? 'Ce nom ou ce message n’est pas accepté. Corrige-le puis réessaie.'
            : s === 403 || s === 404 ? 'Cette invitation n’est pas la tienne.'
              : 'Modification impossible pour le moment.');
      })
      .finally(() => setOccupe(false));
  };

  // ── Pass existant, hors édition : « Ton invitation est prête » ─────────────
  if (!creation && !edition) {
    return (
      <div className="cp-card cp-card--current" data-testid="inviter-un-ami">
        <div data-testid="wizard-prete">
          <div className="cp-prog">
            <h3 className="cp-h3"><SvgIcon name="check" size={20} />Ton invitation est prête</h3>
            <button type="button" className="cp-link cp-wz-tap" onClick={() => { reinitialiser(); setEdition(true); }}
                    disabled={occupe} data-testid="wizard-modifier">
              <SvgIcon name="edit" size={14} /> Modifier
            </button>
          </div>
          {apercu}
        </div>
        <div className="cp-code">
          <div>
            <small>Mon lien d'invitation</small>
            {lienCourt(lien)}
          </div>
          <button type="button" className="cp-iconbtn cp-wz-tap" onClick={surCopier} aria-label="Copier le lien" data-testid="inviter-copier-icone">
            <SvgIcon name="copy" size={22} />
          </button>
        </div>
        <button type="button" className="cp-b cp-b--whatsapp cp-wz-cible" onClick={surWhatsApp} disabled={!lien} data-testid="inviter-whatsapp">
          <SvgIcon name="send" size={20} />Envoyer sur WhatsApp
        </button>
        <div className="cp-share cp-share--2">
          <button type="button" className="cp-b cp-b--secondary cp-wz-cible" onClick={surPartager} disabled={!lien} data-testid="inviter-partager">
            <SvgIcon name="share" size={20} />Partager
          </button>
          <button type="button" className="cp-b cp-b--secondary cp-wz-cible" onClick={surCopier} disabled={!lien} data-testid="inviter-copier">
            <SvgIcon name="copy" size={20} />Copier le lien
          </button>
        </div>
        {typeof onQr === 'function' ? (
          <button type="button" className="cp-link cp-wz-qr cp-wz-tap" onClick={() => onQr(pass, lien)} disabled={!lien} data-testid="inviter-qr">
            <SvgIcon name="qrCode" size={14} /> Afficher le QR code
          </button>
        ) : null}
        {feedback ? <p className="cp-ok-text" role="status" data-testid="inviter-feedback">{feedback}</p> : null}
        {erreur ? <p className="cp-error" role="alert">{erreur}</p> : null}
        <p className="cp-mini">Ton ami profite d'un essai gratuit. Le lien ne contient jamais ton e-mail.</p>
      </div>
    );
  }

  // ── Création (ou édition) en 3 étapes ─────────────────────────────────────
  if (creation && !choix.groupes.length) {
    return (
      <div className="cp-card" data-testid="invitation-wizard">
        <p className="cp-mini" data-testid="pass-aucune-seance">
          Aucune séance n'est ouverte au Pass Duo pour le moment. Reviens bientôt.
        </p>
      </div>
    );
  }

  const etape1Ok = !nomRefuse && (!creation || (!!choix.valeur && !choix.offreManquante && (!conditionsRequises || conditionsOk)));
  const suivant = () => { if (etape === 1 && !etape1Ok) return; setEtape((e) => Math.min(3, e + 1)); };
  const precedent = () => setEtape((e) => Math.max(1, e - 1));

  return (
    <div className="cp-card" data-testid="invitation-wizard" data-mode={creation ? 'creation' : 'edition'}>
      <ol className="cp-wz-etapes" data-testid="wizard-etapes" aria-label="Étapes de ton invitation">
        {ETAPES.map((libelle, i) => (
          <li key={libelle} className={i + 1 === etape ? 'on' : (i + 1 < etape ? 'fait' : '')}
              aria-current={i + 1 === etape ? 'step' : undefined}>
            <span>{i + 1}</span>{libelle}
          </li>
        ))}
      </ol>

      {etape === 1 ? (
        <div data-testid="wizard-etape-1">
          <div className="cp-wz-identite">
            <Avatar photo={photo} nom={nomValide} />
            <div className="cp-wz-identite-nom">
              <small>Invitation de</small>
              <b data-testid="wizard-nom">{nomValide || NOM_NEUTRE}</b>
            </div>
            {!identiteOuverte && !edition ? (
              <button type="button" className="cp-link cp-wz-tap" onClick={() => setIdentiteOuverte(true)} data-testid="wizard-modifier-identite">
                <SvgIcon name="edit" size={14} /> Modifier
              </button>
            ) : null}
          </div>
          {identiteOuverte || edition ? (
            <div className="cp-wz-edition" data-testid="wizard-identite-edition">
              <label htmlFor="cp-wz-nom" className="cp-label">Nom affiché sur cette invitation</label>
              <input id="cp-wz-nom" className="cp-input" maxLength={NOM_MAX} value={nomBrut}
                     placeholder={NOM_NEUTRE} autoComplete="off"
                     onChange={(e) => setNomSaisi(e.target.value)} data-testid="wizard-champ-nom" />
              {nomRefuse ? (
                <p className="cp-error" role="alert" data-testid="wizard-nom-refuse">Écris un prénom, pas une adresse e-mail.</p>
              ) : null}
              {prerempli.photo ? (
                <div className="cp-wz-choix" role="group" aria-label="Photo de l'invitation">
                  <button type="button" className={`cp-b cp-b--small cp-wz-cible ${photoRetiree ? 'cp-b--ghost' : 'cp-b--secondary'}`}
                          aria-pressed={!photoRetiree} onClick={() => setPhotoRetiree(false)} data-testid="wizard-photo-garder">
                    <SvgIcon name="image" size={16} /> Garder la photo
                  </button>
                  <button type="button" className={`cp-b cp-b--small cp-wz-cible ${photoRetiree ? 'cp-b--secondary' : 'cp-b--ghost'}`}
                          aria-pressed={photoRetiree} onClick={() => setPhotoRetiree(true)} data-testid="wizard-photo-retirer">
                    <SvgIcon name="x" size={16} /> Retirer la photo
                  </button>
                </div>
              ) : null}
              <p className="cp-fine">Ce changement ne concerne que cette invitation : ton profil ne bouge pas.</p>
            </div>
          ) : null}
          {creation ? (
            <>
              <ChampsSeanceOffre choix={choix} occupe={occupe} />
              {choix.coursChoisi ? (
                <div className="cp-conditions" data-testid="pass-conditions">
                  <ConditionsParticipation courseId={choix.coursChoisi} accepte={conditionsOk}
                                           onChange={setConditionsOk} onRequired={setConditionsRequises} />
                </div>
              ) : null}
            </>
          ) : null}
        </div>
      ) : null}

      {etape === 2 ? (
        <div data-testid="wizard-etape-2">
          <label htmlFor="cp-wz-message" className="cp-label">Ton message</label>
          <textarea id="cp-wz-message" className="cp-input cp-wz-message" rows={4} maxLength={MESSAGE_MAX}
                    value={message} onChange={(e) => setMessageSaisi(bornerMessage(e.target.value))}
                    data-testid="wizard-message" />
          <p className="cp-fine cp-wz-compteur" data-testid="wizard-compteur">{message.length}/{MESSAGE_MAX}</p>
        </div>
      ) : null}

      {etape === 3 ? (
        <div data-testid="wizard-etape-3">
          {apercu}
          {creation ? (
            <p className="cp-fine cp-center">Un Pass par séance. L'invitation seule ne débloque rien.</p>
          ) : null}
        </div>
      ) : null}

      {erreur ? <p className="cp-error" role="alert" data-testid="wizard-erreur">{erreur}</p> : null}

      <div className="cp-wz-nav">
        {etape > 1 ? (
          <button type="button" className="cp-b cp-b--ghost cp-wz-cible" onClick={precedent} disabled={occupe} data-testid="wizard-precedent">
            <SvgIcon name="arrowLeft" size={18} /> Retour
          </button>
        ) : null}
        {etape < 3 ? (
          <button type="button" className="cp-b cp-wz-cible" onClick={suivant} disabled={occupe || (etape === 1 && !etape1Ok)} data-testid="wizard-suivant">
            Continuer <SvgIcon name="arrowRight" size={18} />
          </button>
        ) : creation ? (
          <button type="button" className="cp-b cp-wz-cible" onClick={creer} disabled={occupe || !etape1Ok} data-testid="wizard-creer">
            <SvgIcon name="send" size={20} /> {occupe ? 'Création…' : 'Créer mon invitation'}
          </button>
        ) : (
          <button type="button" className="cp-b cp-wz-cible" onClick={enregistrer} disabled={occupe || nomRefuse} data-testid="wizard-enregistrer">
            <SvgIcon name="check" size={20} /> {occupe ? 'Enregistrement…' : 'Enregistrer'}
          </button>
        )}
      </div>
      {!creation ? (
        <button type="button" className="cp-link cp-wz-retour cp-wz-tap" onClick={() => { reinitialiser(); setEdition(false); }}
                disabled={occupe} data-testid="wizard-annuler">
          <SvgIcon name="arrowLeft" size={14} /> Garder mon invitation telle quelle
        </button>
      ) : null}
      {creation && creationForcee && pass && typeof onRetour === 'function' ? (
        <button type="button" className="cp-link cp-wz-retour cp-wz-tap" onClick={() => { reinitialiser(); onRetour(); }}
                disabled={occupe} data-testid="wizard-retour-pass">
          <SvgIcon name="arrowLeft" size={14} /> Revenir à mon invitation
        </button>
      ) : null}
    </div>
  );
}
