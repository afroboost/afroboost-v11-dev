/**
 * V551 — PARRAINAGE V2 : L'ASSISTANT D'INVITATION DU MEMBRE.
 *
 * V558 — LE MÊME WIZARD QUE LE PARCOURS DU FILLEUL (briques de wizardCommun) :
 *   1 Offre (« Qu'est-ce que tu veux offrir à ton ami ? ») · 2 Séance (le
 *   calendrier EXISTANT, SessionsModal, puis le résumé compact et l'offre du
 *   cours) · 3 Ta carte (tes informations + message + aperçu, « Créer ») ·
 *   4 Partage (« Ton invitation est prête »). Une modification d'invitation
 *   existante n'ouvre que « Ta carte ». Ce qui suit décrit V551 (données, réseau).
 *
 * TROIS ÉTAPES, JAMAIS UNE DE PLUS (mobile d'abord) :
 *   1. « Ton invitation » — photo + nom préremplis (profil Spordateur lié,
 *      sinon l'identité de GET /invitation, sinon « Afroboost » (V558 : jamais « Un membre »),
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
import SessionsModal from '../SessionsModal'; // V558 — le calendrier EXISTANT
import { Etapes, CartesOffre, ResumeSeance, CarteInvitation, typesDeRepli, etapesNecessaires } from './wizardCommun'; // V558 / V560 — le MÊME Wizard
import './invitationWizard.css';
import './wizardFilleul.css'; // V558 : cartes d'offre et résumé de séance (classes cp-wf-*)
import {
  API_PARRAINAGE, enteteParrain, lireInvitation, identitePreremplie, messagePrerempli, corpsInvitation,
  modifierInvitation, nomAffichable, bornerMessage, texteWhatsAppInvitation, lienWhatsApp, copier, partager,
  NOM_NEUTRE, MESSAGE_MAX, NOM_MAX, avecCampagne, seancesPourCalendrier,
} from '../../utils/parrainage';

/** V558 — le type offert par un membre : son Pass Duo (aucun programme exposé ici). */
const TYPES_MEMBRE = typesDeRepli('pass_duo');

/** Version de l'invitation portée par un pass (0 si jamais personnalisée). */
function versionInvitation(p) {
  return Number(p && p.invitation && p.invitation.version) || 0;
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
  const [kind, setKind] = useState(TYPES_MEMBRE[0].id);   // V558 : étape « Offre »
  const [calendrier, setCalendrier] = useState(false);    // V558 : étape « Séance »
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

  // V560 : LA carte unique (photo, prénom, type, séance, lieu), rendue en direct.
  const coursCarte = creation
    ? ((Array.isArray(courses) ? courses : []).find((x) => x && String(x.id) === String(choix.coursChoisi)) || {})
    : ((pass && pass.course) || {});
  const apercu = (
    <CarteInvitation testid="wizard-apercu" prenom={nomValide} photo={photo} type="pass_duo"
                     occurrence={creation ? choix.occurrence : pass && pass.occurrence}
                     cours={coursCarte.name} lieu={coursCarte.locationName || coursCarte.location} />
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
    // Invitation du coach : `referral_campaign` seulement si /parrainage?campagne= l'a porté.
    axios.post(`${API_PARRAINAGE}/pass`, avecCampagne(corps, contexte && contexte.campagne), { headers: enteteParrain() })
      .then((r) => {
        const dto = r && r.data;
        // V562 — RÈGLE EXISTANTE (serveur) : UN Pass Duo actif par parrain et par séance.
        // Une NOUVELLE invitation sur une séance déjà prise n'adopte pas l'ancien pass.
        if (creationForcee && dto && dto.deja_existant) {
          setErreur(seanceVisible ? 'Pass Duo déjà utilisé pour cette séance. Choisis une autre séance.'
            : 'Pass Duo déjà utilisé pour cette séance');
          setEtape(2);
          return;
        }
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
  // V562 — WIZARD DYNAMIQUE : une étape sans décision est choisie d'office et cachée.
  // Séance : montrée s'il y a ≥ 2 séances, ou une vraie décision d'offre (≥ 2 offres,
  // ou aucune offre valable : l'écran doit le dire).
  const nbSeances = (choix.groupes || []).reduce((n, g) => n + ((g && g.options) || []).length, 0);
  const decisionOffreCours = !!choix.offresConnues && (choix.offres || []).length !== 1;
  const plan = etapesNecessaires({ nbOffres: TYPES_MEMBRE.length, nbSeances, decisionSeance: decisionOffreCours });
  const NUMERO = { offre: 1, seance: 2, carte: 3 };
  const visibles = plan.ids.filter((id) => id !== 'partage').map((id) => NUMERO[id]);
  const seanceVisible = visibles.indexOf(2) >= 0;

  if (!creation && !edition) {
    return (
      <div className="cp-card cp-card--current" data-testid="inviter-un-ami">
        {/* V560 : l'étape « Partage » du MÊME Wizard — une carte, quatre boutons, « Modifier ». */}
        <Etapes etape={plan.libelles.length} etapes={plan.libelles} className="cp-wf-etapes" testid="wizard-etapes" />
        <div data-testid="wizard-prete">
          <h3 className="cp-wf-titre">Partage ton invitation</h3>
          <p className="cp-wf-aide" data-testid="wizard-partage-aide">
            Ton ami remplira ses propres informations quand il ouvrira le lien.
          </p>
          {apercu}
        </div>
        <div className="cp-wf-actions4">
          <button type="button" className="cp-b cp-b--whatsapp cp-wz-cible" onClick={surWhatsApp} disabled={!lien} data-testid="inviter-whatsapp">
            <SvgIcon name="messageCircle" size={20} /> WhatsApp
          </button>
          <button type="button" className="cp-b cp-b--secondary cp-wz-cible" onClick={surPartager} disabled={!lien} data-testid="inviter-partager">
            <SvgIcon name="share" size={20} /> Partager
          </button>
          <button type="button" className="cp-b cp-b--secondary cp-wz-cible" onClick={surCopier} disabled={!lien} data-testid="inviter-copier">
            <SvgIcon name="link" size={20} /> Copier le lien
          </button>
          {typeof onQr === 'function' ? (
            <button type="button" className="cp-b cp-b--secondary cp-wz-cible cp-wz-tap" onClick={() => onQr(pass, lien)} disabled={!lien} data-testid="inviter-qr">
              <SvgIcon name="qrCode" size={20} /> QR code
            </button>
          ) : null}
        </div>
        {feedback ? <p className="cp-ok-text" role="status" data-testid="inviter-feedback">{feedback}</p> : null}
        {erreur ? <p className="cp-error" role="alert">{erreur}</p> : null}
        <button type="button" className="cp-link cp-wz-tap cp-wz-retour" onClick={() => { reinitialiser(); setEdition(true); }}
                disabled={occupe} data-testid="wizard-modifier">
          <SvgIcon name="edit" size={14} /> Modifier
        </button>
      </div>
    );
  }

  // ── Création (Offre · Séance · Ta carte) ou modification (Ta carte seule) ──
  if (creation && !choix.groupes.length) {
    return (
      <div className="cp-card" data-testid="invitation-wizard">
        <p className="cp-mini" data-testid="pass-aucune-seance">
          Aucune séance n'est ouverte au Pass Duo pour le moment. Reviens bientôt.
        </p>
      </div>
    );
  }

  // Une modification n'ouvre que « Ta carte » : la séance se change dans la carte du Pass (V539b).
  const etapeAffichee = creation ? (visibles.indexOf(etape) >= 0 ? etape : visibles[0]) : 3;
  const position = visibles.indexOf(etapeAffichee);
  const seanceOk = !!choix.valeur && !choix.offreManquante && (!conditionsRequises || conditionsOk);
  const carteOk = !nomRefuse;
  const peutContinuer = etapeAffichee === 1 ? !!kind : (etapeAffichee === 2 ? seanceOk : carteOk);
  const suivant = () => { if (!peutContinuer) return; setEtape(visibles[Math.min(visibles.length - 1, position + 1)]); };
  const precedent = () => setEtape(visibles[Math.max(0, position - 1)]);
  const coursObjet = (Array.isArray(courses) ? courses : []).find((x) => x && String(x.id) === String(choix.coursChoisi)) || {};
  const seanceChoisie = choix.occurrence
    ? { occurrence: choix.occurrence, nom: coursObjet.name || '', lieu: coursObjet.locationName || coursObjet.location || '' }
    : null;
  const seancesCal = seancesPourCalendrier((Array.isArray(courses) ? courses : []).map((c) => ({
    course_id: c && c.id, name: c && c.name, location: c && (c.locationName || c.location), occurrences: c && c.occurrences,
  })));

  return (
    <div className="cp-card" data-testid="invitation-wizard" data-mode={creation ? 'creation' : 'edition'}>
      <Etapes etape={plan.ids.indexOf(Object.keys(NUMERO).find((k) => NUMERO[k] === etapeAffichee)) + 1}
              etapes={plan.libelles} className="cp-wf-etapes" testid="wizard-etapes" />

      {etapeAffichee === 1 ? (
        <div data-testid="wizard-etape-1">
          <h3 className="cp-wf-titre" data-testid="wizard-offre-titre">Que veux-tu partager ?</h3>
          <p className="cp-wf-aide">Choisis ce que tu veux proposer à ton ami.</p>
          <CartesOffre types={TYPES_MEMBRE} choisi={kind} onChoisir={setKind} />
        </div>
      ) : null}

      {etapeAffichee === 2 ? (
        <div data-testid="wizard-etape-2">
          <h3 className="cp-wf-titre" data-testid="wizard-seance-titre">Choisis la séance de ton ami</h3>
          <p className="cp-wf-aide">Sélectionne la séance que ton ami recevra avec ton invitation.</p>
          <ResumeSeance seance={seanceChoisie} onChanger={() => setCalendrier(true)} />
          {!seanceChoisie ? (
            <button type="button" className="cp-b cp-b--secondary cp-wz-cible" onClick={() => setCalendrier(true)}
                    data-testid="wf-seance-choisir">
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
                if (occ && occ.id && occ.iso) choix.setChoix(`${occ.id}|${occ.iso}`);
                setCalendrier(false);
              }}
            />
          ) : null}
          <ChampsSeanceOffre choix={choix} occupe={occupe} sansSelecteurSeance />
          {choix.coursChoisi ? (
            <div className="cp-conditions" data-testid="pass-conditions">
              <ConditionsParticipation courseId={choix.coursChoisi} accepte={conditionsOk}
                                       onChange={setConditionsOk} onRequired={setConditionsRequises} />
            </div>
          ) : null}
        </div>
      ) : null}

      {etapeAffichee === 3 ? (
        <div data-testid="wizard-etape-3">
          <h3 className="cp-wf-titre" data-testid="wizard-carte-titre">Personnalise ton invitation</h3>
          <p className="cp-wf-aide">Ton ami verra que l’invitation vient de toi.</p>
          {/* V562 : séance unique choisie d'office — ses conditions se valident ici. */}
          {creation && !seanceVisible && choix.coursChoisi ? (
            <div className="cp-conditions" data-testid="pass-conditions">
              <ConditionsParticipation courseId={choix.coursChoisi} accepte={conditionsOk}
                                       onChange={setConditionsOk} onRequired={setConditionsRequises} />
            </div>
          ) : null}
          {apercu}
          {/* V560 : la carte ci-dessus montre déjà photo et prénom — ici, seulement les champs. */}
          <div className="cp-wz-edition" data-testid="wizard-identite-edition">
            <label htmlFor="cp-wz-nom" className="cp-label">Ton prénom</label>
            <input id="cp-wz-nom" className="cp-input" maxLength={NOM_MAX} value={nomBrut}
                   placeholder="Ton prénom" autoComplete="given-name"
                   onChange={(e) => setNomSaisi(e.target.value)} data-testid="wizard-champ-nom" />
            {nomRefuse ? (
              <p className="cp-error" role="alert" data-testid="wizard-nom-refuse">Écris un prénom, pas une adresse e-mail.</p>
            ) : null}
            {prerempli.photo ? (
              <>
                <span className="cp-label">Ta photo</span>
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
              </>
            ) : null}
            <p className="cp-fine">Ce changement ne concerne que cette invitation : ton profil ne bouge pas.</p>
          </div>
          {identiteOuverte || edition ? (
            <>
              <label htmlFor="cp-wz-message" className="cp-label">Ton message</label>
              <textarea id="cp-wz-message" className="cp-input cp-wz-message" rows={3} maxLength={MESSAGE_MAX}
                        value={message} onChange={(e) => setMessageSaisi(bornerMessage(e.target.value))}
                        data-testid="wizard-message" />
              <p className="cp-fine cp-wz-compteur" data-testid="wizard-compteur">{message.length}/{MESSAGE_MAX}</p>
            </>
          ) : (
            <button type="button" className="cp-link cp-wz-tap" onClick={() => setIdentiteOuverte(true)} data-testid="wizard-modifier-message">
              <SvgIcon name="edit" size={14} /> Modifier le message
            </button>
          )}
          {creation ? (
            <p className="cp-fine cp-center">Un Pass par séance. L'invitation seule ne débloque rien.</p>
          ) : null}
        </div>
      ) : null}

      {erreur ? <p className="cp-error" role="alert" data-testid="wizard-erreur">{erreur}</p> : null}

      <div className="cp-wz-nav">
        {creation && position > 0 ? (
          <button type="button" className="cp-b cp-b--ghost cp-wz-cible" onClick={precedent} disabled={occupe} data-testid="wizard-precedent">
            <SvgIcon name="arrowLeft" size={18} /> Retour
          </button>
        ) : null}
        {creation && etapeAffichee !== 3 ? (
          <button type="button" className="cp-b cp-wz-cible" onClick={suivant} disabled={occupe || !peutContinuer} data-testid="wizard-suivant">
            Continuer <SvgIcon name="arrowRight" size={18} />
          </button>
        ) : creation ? (
          <button type="button" className="cp-b cp-wz-cible" onClick={creer} disabled={occupe || !seanceOk || !carteOk} data-testid="wizard-creer">
            {occupe ? 'Un instant…' : 'Continuer vers le partage'} <SvgIcon name="arrowRight" size={18} />
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
