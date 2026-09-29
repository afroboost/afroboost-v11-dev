/**
 * V558 — LE WIZARD « INVITATION & PARRAINAGE » : LES BRIQUES COMMUNES.
 *
 * Un seul Wizard, quatre étapes, UNE seule visible à la fois :
 *   1 Offre · 2 Séance · 3 Ta carte · 4 Partage.
 * Le parcours du filleul (WizardFilleul, /duo/<token>) et celui de l'abonné
 * (InvitationWizard, espace abonné / /parrainage) rendent EXACTEMENT ces pièces :
 * même stepper, mêmes cartes d'offre, même résumé de séance, même calendrier
 * (SessionsModal, via `occurrencesFournies`). Seules les données changent.
 *
 * Couleurs : jetons --cp-* (issus des couleurs du coach). Icônes : SVG inline.
 */
import React from 'react';
import SvgIcon from '../SvgIcon';
import { libelleJour, libelleHeure } from '../../utils/parrainage';

export const ETAPES_WIZARD = ['Offre', 'Séance', 'Ta carte', 'Partage'];

/** Le stepper « 1 Offre · 2 Séance · 3 Ta carte · 4 Partage ». */
export function Etapes({ etape, className, testid }) {
  return (
    <ol className={`cp-wz-etapes ${className || ''}`.trim()} aria-label={`Étape ${etape} sur ${ETAPES_WIZARD.length}`}
        data-testid={testid || 'wf-etapes'}>
      {ETAPES_WIZARD.map((t, i) => {
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

/** Le badge : le type RÉEL renvoyé par le serveur ; jamais « Pass Duo » par défaut. */
export function libelleTypeInvitation(type) {
  if (type === 'trial') return 'Essai gratuit';
  if (type === 'pass_duo') return 'Pass Duo';
  if (type === 'event_free') return 'Événement';
  if (type === 'parrainage') return 'Parrainage';
  if (type === 'affiliation') return 'Affiliation';
  return 'Invitation';
}

const TEXTES_TYPE = {
  trial: 'Offre à ton ami son premier cours Afroboost.',
  pass_duo: 'Offre à ton ami une place à tes côtés.',
  event_free: 'Offre à ton ami une place à cet événement.',
};

/** Les cartes de l'étape « Offre » si le serveur ne les donne pas : le type du pass seul. */
export function typesDeRepli(typeDuPass) {
  const t = typeDuPass === 'pass_duo' || typeDuPass === 'event_free' ? typeDuPass : 'trial';
  return [{ id: t, libelle: libelleTypeInvitation(t), texte: TEXTES_TYPE[t], recompense: null }];
}

/**
 * Étape 1 — « Qu'est-ce que tu veux offrir à ton ami ? ». Seules les cartes
 * AUTORISÉES (données par le serveur) : jamais de carte fantôme.
 */
export function CartesOffre({ types, choisi, onChoisir, verrouille }) {
  return (
    <div className="cp-wf-offres" role="radiogroup" aria-label="Ce que tu offres à ton ami" data-testid="wf-offres">
      {(types || []).map((t) => {
        const on = t.id === choisi;
        return (
          <button key={t.id} type="button" role="radio" aria-checked={on} disabled={!!verrouille && !on}
                  className={`cp-wf-offre${on ? ' on' : ''}`} onClick={() => onChoisir(t.id)}
                  data-testid={`wf-offre-${t.id}`}>
            <span className="cp-wf-offre-radio" aria-hidden="true">{on ? <SvgIcon name="check" size={14} strokeWidth="3" /> : null}</span>
            <span className="cp-wf-offre-txt">
              <b>{t.libelle || libelleTypeInvitation(t.id)}</b>
              <span>{t.texte}</span>
              {t.recompense ? <span className="cp-wf-offre-recompense" data-testid={`wf-recompense-${t.id}`}>{t.recompense}</span> : null}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** Étape 2 — le résumé compact de la séance choisie : jour, heure, cours, adresse. */
export function ResumeSeance({ seance, titre, onChanger, testid }) {
  if (!seance || !seance.occurrence) return null;
  return (
    <div className="cp-wf-seance" data-testid={testid || 'wf-seance-resume'}>
      <span className="cp-label cp-wf-seance-titre">{titre || 'Séance offerte à ton ami'}</span>
      <p className="cp-wf-seance-quand">
        <SvgIcon name="calendar" size={16} />
        <b>{libelleJour(seance.occurrence)}</b>
        <span>{libelleHeure(seance.occurrence)}</span>
      </p>
      {seance.nom ? <p className="cp-wf-seance-cours">{seance.nom}</p> : null}
      {seance.lieu ? <p className="cp-fine cp-wf-seance-lieu">{seance.lieu}</p> : null}
      {onChanger ? (
        <button type="button" className="cp-link cp-wz-tap" onClick={onChanger} data-testid="wf-seance-changer">
          <SvgIcon name="calendar" size={14} /> Changer de séance
        </button>
      ) : null}
    </div>
  );
}
