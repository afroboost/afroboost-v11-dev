/**
 * V534 — CARTE « PASS DUO » DU CENTRE PARRAINAGE.
 *
 * Une seule carte, deux visages :
 *   - SANS pass courant : le sélecteur de séance éligible (libellé calculé
 *     depuis `occurrences[]` + `locationName` de GET /config), le choix de
 *     l'offre (V534b : cartes radio depuis `course.offers`, recommandée
 *     présélectionnée mais jamais imposée) et « Créer mon Pass Duo » ;
 *   - AVEC pass courant : l'état du pass — duo Toi / Ton ami, stepper à 4
 *     crans (Verrouillé → En attente → Ami inscrit → Débloqué), cadenas qui
 *     devient un check, billets quand c'est débloqué, et les actions qui ont un
 *     sens dans cet état (Confirmer ma place, Réserver / Recharger, Annuler),
 *     plus l'« Offre actuelle » et le lien discret « Changer d'offre » (V534b :
 *     bottom sheet ≤ 640 px, une seule action, PATCH porté par le parent).
 *
 * Elle ne parle PAS au réseau : le parent (CentreParrainage) porte les appels
 * et lui rend l'état mis à jour depuis la réponse. Pas de `window.confirm` :
 * l'annulation se confirme en ligne, dans la carte.
 */
import React, { useMemo, useState } from 'react';
import ConditionsParticipation from '../ConditionsParticipation'; // V534: mêmes conditions de participation que l'espace abonné (ESSAI-5a-1)
import SvgIcon from '../SvgIcon';
import BilletsDuo from './BilletsDuo';
import { SelecteurOffres, EncartOffre, SheetOffres } from './OffresDuo'; // V534b: l'offre est choisie par le participant
import {
  LIBELLES_STATUT, etapePass, libelleOccurrence, libelleJour, libelleHeure,
  offreDuPass, offresDe, offrePreselectionnee, TEXTE_OFFRE_UTILISEE, NOTE_OFFRE_PASS,
} from '../../utils/parrainage';

/** Texte EXACT du contrat pour un parrain sans séance disponible. */
export const TEXTE_SPONSOR_SANS_SEANCE = 'Ton Pass Duo est prêt, mais tu dois disposer d’une séance pour confirmer ta place.';

const ETAPES = ['Verrouillé', 'En attente', 'Ami inscrit', 'Débloqué'];

/** Le chip d'état d'un pass (partagé avec les listes du Centre). */
export function ChipStatut({ status }) {
  const s = status || 'locked';
  let classe = 'cp-chip';
  let icone = 'lock';
  if (s === 'waiting') { classe += ' cp-chip--wait'; icone = 'hourglass'; }
  else if (s === 'friend_registered') { classe += ' cp-chip--wait'; icone = 'user'; }
  else if (s === 'unlocked' || s === 'used') { classe += ' cp-chip--ok'; icone = 'check'; }
  else if (s === 'expired' || s === 'cancelled') { classe += ' cp-chip--ext'; icone = s === 'expired' ? 'clock' : 'x'; }
  return (
    <span className={classe} data-testid={`chip-${s}`}>
      <SvgIcon name={icone} size={12} strokeWidth="2.5" />
      {LIBELLES_STATUT[s] || s}
    </span>
  );
}

/** Le stepper 4 crans + ses libellés. */
export function Stepper({ status }) {
  const etape = etapePass(status);
  const ferme = status === 'expired' || status === 'cancelled';
  return (
    <>
      <div className="cp-stepper" aria-hidden="true" data-testid="stepper" data-etape={etape}>
        {ETAPES.map((_, i) => <span key={i} className={!ferme && i <= etape ? 'on' : ''} />)}
      </div>
      <div className="cp-steps" aria-hidden="true">
        {ETAPES.map((e, i) => <span key={e} className={!ferme && i === etape ? 'on' : ''}>{e}</span>)}
      </div>
    </>
  );
}

/** Le duo : deux avatars 64 px reliés — Toi / Ton ami. */
function Duo({ pass, initialeParrain }) {
  const s = pass ? pass.status : 'none';
  const amiInscrit = s === 'friend_registered' || s === 'unlocked' || s === 'used';
  const parrainOk = s === 'unlocked' || s === 'used';
  const parrainBloque = s === 'friend_registered';
  const invitee = pass && pass.invitee;
  const initialeAmi = invitee && invitee.first_name ? invitee.first_name.charAt(0).toUpperCase() : '';
  let etatAmi = 'À inviter';
  if (s === 'waiting') etatAmi = 'Invité';
  if (amiInscrit) etatAmi = 'Inscrit';
  let etatToi = 'Prêt';
  if (parrainBloque) etatToi = 'Place à confirmer';
  if (parrainOk) etatToi = 'Billet prêt';
  return (
    <div className="cp-duo" data-testid="duo">
      <div className={parrainBloque ? 'cp-muted' : ''}>
        <div className={`cp-av${parrainOk ? ' cp-av--ok' : ''}`}>{initialeParrain || <SvgIcon name="user" size={28} />}</div>
        <b>Toi</b>
        <small>{etatToi}</small>
      </div>
      <i className={amiInscrit ? 'on' : ''} />
      <div className={amiInscrit ? '' : 'cp-muted'}>
        <div className={`cp-av${amiInscrit ? ' cp-av--ok' : ''}`}>
          {amiInscrit && initialeAmi ? initialeAmi : (amiInscrit ? <SvgIcon name="check" size={28} /> : <SvgIcon name="helpCircle" size={28} />)}
        </div>
        <b>{amiInscrit && invitee && invitee.first_name ? invitee.first_name : 'Ton ami'}</b>
        <small>{etatAmi}</small>
      </div>
    </div>
  );
}

/** Les options du sélecteur : une par occurrence éligible, groupées par cours. */
export function optionsSeances(courses) {
  const liste = Array.isArray(courses) ? courses : [];
  return liste.map((c) => ({
    id: c.id,
    name: c.name || 'Séance',
    options: (Array.isArray(c.occurrences) ? c.occurrences : []).map((iso) => ({
      valeur: `${c.id}|${iso}`,
      libelle: libelleOccurrence(iso, c.locationName),
    })),
  })).filter((g) => g.options.length > 0);
}

function FormulaireCreation({ courses, onCreer, occupe, erreur }) {
  const groupes = useMemo(() => optionsSeances(courses), [courses]);
  const premiere = groupes.length ? groupes[0].options[0].valeur : '';
  const [choix, setChoix] = useState(premiere);
  const valeur = choix || premiere;
  const plusieursCours = groupes.length > 1;
  // V534: preuve T1 du parrain — le serveur bloque sa place (`conditions_non_acceptees`)
  // si des conditions sont publiées et non acceptées ; sans conditions publiées, rien n'est exigé.
  const [conditionsOk, setConditionsOk] = useState(false);
  const [conditionsRequises, setConditionsRequises] = useState(false);
  const idxCours = valeur.indexOf('|');
  const coursChoisi = idxCours > 0 ? valeur.slice(0, idxCours) : '';

  // V534b: l'offre du Pass, choisie ici. Le catalogue vient de `course.offers`
  // (GET /config) : la recommandée est présélectionnée mais modifiable ; une
  // seule offre → encart sans sélecteur ; plusieurs sans recommandée → rien de
  // présélectionné et le bouton reste désactivé. `offers` absent (serveur
  // antérieur) → aucun sélecteur, `offer_id` null. Le choix est mémorisé PAR
  // cours (dérivé, sans effet) : changer de séance revient à la présélection.
  const coursObjet = (Array.isArray(courses) ? courses : []).find((c) => c && String(c.id) === String(coursChoisi)) || null;
  const offresConnues = !!(coursObjet && Array.isArray(coursObjet.offers));
  const offres = offresDe(coursObjet);
  const [choixOffre, setChoixOffre] = useState({ cours: '', id: null });
  const offreChoisie = choixOffre.cours === coursChoisi && choixOffre.id != null
    ? choixOffre.id
    : offrePreselectionnee(offres, coursObjet && coursObjet.default_offer_id);
  const offreManquante = offresConnues && (offreChoisie == null || !offres.some((o) => String(o.id) === String(offreChoisie)));

  const creer = () => {
    if (!valeur || occupe) return;
    if (conditionsRequises && !conditionsOk) return;
    if (offreManquante) return;
    const idx = valeur.indexOf('|');
    onCreer(valeur.slice(0, idx), valeur.slice(idx + 1), conditionsOk, offresConnues ? offreChoisie : null);
  };

  if (!groupes.length) {
    return (
      <p className="cp-mini" data-testid="pass-aucune-seance">
        Aucune séance n'est ouverte au Pass Duo pour le moment. Reviens bientôt.
      </p>
    );
  }

  return (
    <>
      <label htmlFor="cp-seance" className="cp-label">Séance</label>
      <select id="cp-seance" className="cp-select" value={valeur} onChange={(e) => setChoix(e.target.value)}
              disabled={occupe} data-testid="pass-select-seance">
        {plusieursCours
          ? groupes.map((g) => (
            <optgroup key={g.id} label={g.name}>
              {g.options.map((o) => <option key={o.valeur} value={o.valeur}>{o.libelle}</option>)}
            </optgroup>
          ))
          : groupes[0].options.map((o) => <option key={o.valeur} value={o.valeur}>{o.libelle}</option>)}
      </select>
      {offresConnues && offres.length === 0 ? (
        <p className="cp-error" role="alert" data-testid="offre-aucune">Aucune offre n'est disponible pour cette séance pour le moment.</p>
      ) : null}
      {offresConnues && offres.length === 1 ? (
        <EncartOffre titre="Offre" offre={offres[0]} testid="offre-encart-creation" note={NOTE_OFFRE_PASS} />
      ) : null}
      {offresConnues && offres.length > 1 ? (
        <SelecteurOffres titre="Choisis ton offre" offres={offres} choix={offreChoisie} name={`cp-creation-${coursChoisi}`}
                         onChoisir={(id) => setChoixOffre({ cours: coursChoisi, id })} disabled={occupe} />
      ) : null}
      <Duo pass={null} />
      <Stepper status="locked" />
      {coursChoisi ? (
        <div className="cp-conditions" data-testid="pass-conditions">
          <ConditionsParticipation courseId={coursChoisi} accepte={conditionsOk}
                                   onChange={setConditionsOk} onRequired={setConditionsRequises} />
        </div>
      ) : null}
      {erreur ? <p className="cp-error" role="alert">{erreur}</p> : null}
      <button type="button" className="cp-b" onClick={creer}
              disabled={occupe || !valeur || (conditionsRequises && !conditionsOk) || offreManquante} data-testid="pass-creer">
        <SvgIcon name="plus" size={20} />
        {occupe ? 'Création…' : 'Créer mon Pass Duo'}
      </button>
      <p className="cp-fine cp-center" style={{ marginTop: 10 }}>Un Pass par séance. L'invitation seule ne débloque rien.</p>
    </>
  );
}

function EtatPass({ pass, initialeParrain, urlEspace, onAnnuler, onConfirmer, onNouveau, onChangerOffre, occupe, erreur }) {
  const [confirmAnnulation, setConfirmAnnulation] = useState(false);
  const [conditionsConfirm, setConditionsConfirm] = useState(false); // V534: preuve T1 au moment de /confirm
  // V534b: changement d'offre — sheet, message (conflit de version), refus du serveur, texte « used »
  const [sheetOffre, setSheetOffre] = useState(false);
  const [messageOffre, setMessageOffre] = useState('');
  const [erreurOffre, setErreurOffre] = useState('');
  const [noteUtilisee, setNoteUtilisee] = useState(false);
  const s = pass.status;
  const course = pass.course || {};
  const quand = libelleOccurrence(pass.occurrence, course.locationName);
  const ouvert = s === 'locked' || s === 'waiting' || s === 'friend_registered';
  const debloque = s === 'unlocked' || s === 'used';
  const ferme = s === 'expired' || s === 'cancelled';
  const bloqueSansSeance = s === 'friend_registered' && pass.blocked_reason === 'sponsor_sans_seance';
  const offre = offreDuPass(pass);
  const offresCatalogue = offresDe(pass);
  // Le lien « Changer d'offre » reste visible pour un pass `used` (il explique) ; jamais pour expiré/annulé.
  // V534c: jamais non plus quand le catalogue ne contient aucune AUTRE offre — un seul choix n'est pas un choix.
  const lienOffre = !!offre && !ferme && typeof onChangerOffre === 'function'
    && offresCatalogue.some((o) => o.id !== offre.id);

  const ouvrirSheet = () => {
    if (s === 'used') { setNoteUtilisee((v) => !v); return; }
    setMessageOffre(''); setErreurOffre(''); setSheetOffre(true);
  };
  const choisirOffre = (offerId) => {
    setErreurOffre('');
    Promise.resolve(onChangerOffre(pass.id, offerId, pass.version)).then((r) => {
      const res = r || {};
      if (res.ok) { setSheetOffre(false); setMessageOffre(''); return; }
      // 409 conflit_version : le parent a rechargé /me UNE fois ; on réaffiche avec le message.
      setMessageOffre(res.conflit ? (res.message || '') : '');
      setErreurOffre(res.conflit ? '' : (res.message || 'Changement impossible pour le moment.'));
    });
  };

  return (
    <>
      <p style={{ marginTop: 6 }} data-testid="pass-seance">
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <SvgIcon name="calendar" size={16} />
          <b>{course.name ? `${course.name} · ` : ''}{quand}</b>
        </span>
      </p>

      {offre ? (
        <EncartOffre titre="Offre actuelle" offre={offre} note={NOTE_OFFRE_PASS} testid="offre-actuelle">
          {lienOffre ? (
            <button type="button" className="cp-link cp-offre-lien" onClick={ouvrirSheet} disabled={occupe} data-testid="offre-changer">
              <SvgIcon name="refresh" size={14} /> Changer d'offre
            </button>
          ) : null}
          {noteUtilisee && s === 'used' ? (
            <p className="cp-mini" role="status" data-testid="offre-utilisee">{TEXTE_OFFRE_UTILISEE}</p>
          ) : null}
        </EncartOffre>
      ) : null}

      {sheetOffre ? (
        <SheetOffres offres={offresCatalogue} actuelleId={offre ? offre.id : null} onChoisir={choisirOffre}
                     onFermer={() => setSheetOffre(false)} occupe={occupe} message={messageOffre} erreur={erreurOffre}
                     titre="Changer d'offre" name={`cp-pass-${pass.id}`} />
      ) : null}

      {debloque ? (
        <div className="cp-roundic cp-roundic--ok" data-testid="pass-rond-ok" style={{ margin: '16px auto 4px' }}>
          <SvgIcon name="check" size={38} strokeWidth="2.5" />
        </div>
      ) : (
        <div className={`cp-roundic${ferme ? ' cp-muted' : ''}`} data-testid="pass-rond-lock" style={{ margin: '16px auto 4px', opacity: ferme ? .5 : 1 }}>
          <SvgIcon name={ferme ? (s === 'expired' ? 'clock' : 'x') : 'lock'} size={38} strokeWidth="2" />
        </div>
      )}

      <Duo pass={pass} initialeParrain={initialeParrain} />
      <Stepper status={s} />

      {s === 'locked' && (
        <p className="cp-mini" data-testid="pass-texte-locked">Partage ton lien ci-dessus : dès que ton ami s'inscrit, vous avez chacun votre billet.</p>
      )}
      {s === 'waiting' && (
        <p className="cp-mini" data-testid="pass-texte-waiting">Ton invitation est partie. Le duo se débloque dès l'inscription de ton ami.</p>
      )}
      {bloqueSansSeance && (
        <div className="cp-notice" data-testid="pass-bloque-sans-seance">
          {TEXTE_SPONSOR_SANS_SEANCE}
        </div>
      )}
      {s === 'friend_registered' && !bloqueSansSeance && (
        <p className="cp-mini" data-testid="pass-texte-friend">Ton ami est inscrit. Confirme ta place pour débloquer les deux billets.</p>
      )}
      {debloque && (
        <>
          <p className="cp-mini cp-center" data-testid="pass-texte-unlocked">
            {s === 'used' ? 'Participation validée : vous étiez là tous les deux.' : 'Vous avez chacun votre billet pour la même séance.'}
          </p>
          <BilletsDuo tickets={pass.tickets} compact />
        </>
      )}
      {ferme && (
        <p className="cp-mini" data-testid="pass-texte-ferme">
          {s === 'expired' ? 'La séance est passée sans inscription de ton ami.' : 'Tu as annulé ce Pass Duo.'}
        </p>
      )}

      {erreur ? <p className="cp-error" role="alert">{erreur}</p> : null}

      {bloqueSansSeance && (
        <>
          {urlEspace ? (
            <a className="cp-b cp-b--secondary" href={urlEspace} data-testid="pass-reserver-recharger">
              <SvgIcon name="creditCard" size={20} /> Réserver / Recharger
            </a>
          ) : null}
          <button type="button" className="cp-b" onClick={() => onConfirmer(pass.id)} disabled={occupe} data-testid="pass-confirmer">
            <SvgIcon name="check" size={20} /> {occupe ? 'Confirmation…' : 'Confirmer ma place'}
          </button>
        </>
      )}
      {s === 'friend_registered' && !bloqueSansSeance && (
        <>
          {/* V534: place bloquée faute d'acceptation des conditions (`conditions_non_acceptees`) :
              la même case que l'espace abonné, puis confirmation avec la preuve. */}
          {pass.blocked_reason === 'conditions_non_acceptees' ? (
            <div className="cp-conditions" data-testid="pass-conditions-confirm">
              <ConditionsParticipation courseId={pass.course && pass.course.id} accepte={conditionsConfirm}
                                       onChange={setConditionsConfirm} />
            </div>
          ) : null}
          <button type="button" className="cp-b" onClick={() => onConfirmer(pass.id, conditionsConfirm)}
                  disabled={occupe || (pass.blocked_reason === 'conditions_non_acceptees' && !conditionsConfirm)} data-testid="pass-confirmer">
            <SvgIcon name="check" size={20} /> {occupe ? 'Confirmation…' : 'Confirmer ma place'}
          </button>
        </>
      )}

      {ouvert && !confirmAnnulation && (
        <button type="button" className="cp-b cp-b--danger" onClick={() => setConfirmAnnulation(true)} disabled={occupe} data-testid="pass-annuler">
          Annuler ce Pass
        </button>
      )}
      {ouvert && confirmAnnulation && (
        <div className="cp-confirm" data-testid="pass-annuler-confirm">
          <p style={{ margin: 0, fontSize: 14 }}>Annuler ce Pass Duo ? Ton ami ne pourra plus s'inscrire avec ce lien.</p>
          <div className="cp-actions">
            <button type="button" className="cp-b cp-b--ghost" onClick={() => setConfirmAnnulation(false)} disabled={occupe}>Garder</button>
            <button type="button" className="cp-b cp-b--danger" onClick={() => { onAnnuler(pass.id); setConfirmAnnulation(false); }} disabled={occupe} data-testid="pass-annuler-oui">
              {occupe ? 'Annulation…' : 'Oui, annuler'}
            </button>
          </div>
        </div>
      )}
      {debloque && (
        <p className="cp-fine cp-center" style={{ marginTop: 10 }}>
          Pour annuler, passe par tes réservations dans ton espace abonné.
        </p>
      )}
      {(ferme || debloque) && onNouveau ? (
        <button type="button" className="cp-b cp-b--ghost" onClick={onNouveau} data-testid="pass-nouveau">
          <SvgIcon name="plus" size={20} /> Créer un nouveau Pass Duo
        </button>
      ) : null}
    </>
  );
}

/** Liste compacte des autres passes (le courant est en tête, dans la carte). */
function ListePasses({ passes, courantId, onChoisir }) {
  const autres = passes.filter((p) => p && p.id !== courantId);
  if (!autres.length) return null;
  return (
    <div className="cp-card cp-card--tight" data-testid="passes-liste">
      {autres.map((p) => (
        <button key={p.id} type="button" className="cp-row cp-row--btn" onClick={() => onChoisir(p.id)} data-testid={`passes-item-${p.id}`}>
          <div className="cp-who">
            <div className="cp-av-s"><SvgIcon name="users" size={16} /></div>
            <div>
              <b>{libelleJour(p.occurrence)}{libelleHeure(p.occurrence) ? ` · ${libelleHeure(p.occurrence)}` : ''}</b>
              <small>{p.course && p.course.locationName ? p.course.locationName : (p.course && p.course.name) || ''}</small>
            </div>
          </div>
          <ChipStatut status={p.status} />
        </button>
      ))}
    </div>
  );
}

/**
 * @param {object}   config          `{enabled, courses}` de GET /config
 * @param {object[]} passes          PassDTO[] (récents d'abord)
 * @param {object}   passAffiche     le pass montré dans la carte (ou null)
 * @param {string}   initialeParrain initiale du prénom du parrain
 * @param {string}   urlEspace       `/espace/<code>` pour « Réserver / Recharger »
 * @param {function} onCreer(course_id, occurrence, terms_accepted, offer_id)   V534b: + offer_id (null si serveur sans catalogue)
 * @param {function} onAnnuler(passId)
 * @param {function} onConfirmer(passId)
 * @param {function} onChoisir(passId)
 * @param {function} onChangerOffre(passId, offer_id, version) → Promise<{ok, conflit?, message?}>   V534b
 * @param {boolean}  occupe          un appel est en cours
 * @param {string}   erreur          message d'erreur du dernier appel
 */
export default function PassDuoCard({
  config, passes, passAffiche, initialeParrain, urlEspace,
  onCreer, onAnnuler, onConfirmer, onChoisir, onChangerOffre, occupe, erreur,
}) {
  const [creation, setCreation] = useState(false);
  const liste = Array.isArray(passes) ? passes : [];
  const montrerFormulaire = !passAffiche || creation;

  return (
    <>
      <div className={`cp-card${passAffiche && !montrerFormulaire ? ' cp-card--current' : ''}`} data-testid="pass-duo-card"
           data-status={passAffiche && !montrerFormulaire ? passAffiche.status : 'none'}>
        <div className="cp-prog">
          <h3 className="cp-h3"><SvgIcon name="users" size={20} />Pass Duo Afroboost</h3>
          {passAffiche && !montrerFormulaire ? <ChipStatut status={passAffiche.status} /> : <ChipStatut status="locked" />}
        </div>
        <p>Choisis une séance, invite un ami : dès son inscription, vous avez chacun votre billet.</p>

        {montrerFormulaire ? (
          <>
            <FormulaireCreation courses={config && config.courses} onCreer={(c, o, t, of) => { setCreation(false); onCreer(c, o, t, of); }} occupe={occupe} erreur={erreur} />
            {passAffiche ? (
              <button type="button" className="cp-link" onClick={() => setCreation(false)} style={{ marginTop: 12 }}>
                <SvgIcon name="arrowLeft" size={14} /> Revenir à mon Pass
              </button>
            ) : null}
          </>
        ) : (
          <EtatPass
            pass={passAffiche}
            initialeParrain={initialeParrain}
            urlEspace={urlEspace}
            onAnnuler={onAnnuler}
            onConfirmer={onConfirmer}
            onNouveau={() => setCreation(true)}
            onChangerOffre={onChangerOffre}
            occupe={occupe}
            erreur={erreur}
          />
        )}
      </div>
      {liste.length > 1 ? <ListePasses passes={liste} courantId={passAffiche ? passAffiche.id : null} onChoisir={(id) => { setCreation(false); onChoisir(id); }} /> : null}
    </>
  );
}
