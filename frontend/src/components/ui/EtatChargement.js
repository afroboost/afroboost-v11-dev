/**
 * P0-SOCLE — LES TROIS AFFICHAGES QUI TUENT LE « ZÉRO MENTEUR ».
 * ==============================================================
 *
 * Un compteur qui affiche `0` alors que la requête n'a pas abouti raconte au
 * coach qu'il n'a aucun contact. C'est faux, et c'est ce que le site fait depuis
 * son premier jour. Trois composants suffisent à y mettre fin :
 *
 *   <Compteur>        « — » pendant le chargement, le nombre après succès,
 *                     un tiret barré signalé après échec. Jamais « 0 » par défaut.
 *   <SectionErreur>   le message d'échec + l'action « Réessayer », qui relance
 *                     UNIQUEMENT la section concernée. Aucun rechargement de page.
 *   <BanniereSession> la sortie honnête quand la preuve d'authentification est
 *                     morte : on le dit, et on propose la reconnexion.
 *
 * COULEURS : aucune valeur codée en dur. Tout passe par `var(--primary-color)` /
 * `var(--primary-rgb)`, afin que la personnalisation du coach s'applique ici
 * comme partout ailleurs (règle absolue du dépôt).
 *
 * ICÔNES : SVG inline avec `stroke="currentColor"`, jamais d'emoji.
 */

import React from 'react';
import { SECTION } from '../../hooks/useChargement';

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const PRIMAIRE_RGB = 'var(--primary-rgb, 217, 28, 210)';

/** Messages orientés ACTION. Aucune trace technique, aucune donnée personnelle. */
const MESSAGES = {
  session: 'Ta session a expiré.',
  droit: 'Accès non autorisé à cette section.',
  reseau: 'Connexion interrompue.',
  serveur: 'Le serveur n\'a pas répondu.',
  introuvable: 'Section indisponible.',
};

export function messagePour(motif) {
  return MESSAGES[motif] || 'Chargement impossible.';
}

function IconeAlerte({ taille = 14 }) {
  return (
    <svg
      width={taille}
      height={taille}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}

function IconeRelance({ taille = 13 }) {
  return (
    <svg
      width={taille}
      height={taille}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <polyline points="23 4 23 10 17 10" />
      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
    </svg>
  );
}

function IconeVerrou({ taille = 14 }) {
  return (
    <svg
      width={taille}
      height={taille}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 9.9-1" />
    </svg>
  );
}

/**
 * UN COMPTEUR QUI NE MENT PAS.
 *
 * @param etat     l'état de la section (`SECTION.*`)
 * @param valeur   la valeur à afficher quand — et seulement quand — elle est connue
 */
export function Compteur({ etat, valeur, titre, 'data-testid': testId }) {
  if (etat === SECTION.CHARGEMENT || etat === SECTION.ATTENTE) {
    return (
      <span
        data-testid={testId}
        data-etat={etat}
        title="Chargement en cours"
        aria-busy="true"
        style={{ opacity: 0.35, letterSpacing: '0.05em' }}
      >
        &mdash;
      </span>
    );
  }

  if (etat === SECTION.ERREUR || etat === SECTION.SESSION) {
    return (
      <span
        data-testid={testId}
        data-etat={etat}
        title={etat === SECTION.SESSION ? MESSAGES.session : 'Donnée indisponible'}
        style={{
          opacity: 0.55,
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px',
          color: 'var(--erreur-color, #f5948b)',
        }}
      >
        <IconeAlerte taille={12} />
        &mdash;
      </span>
    );
  }

  return (
    <span data-testid={testId} data-etat={etat} title={titre}>
      {valeur}
    </span>
  );
}

/**
 * L'ÉCHEC D'UNE SECTION, DIT HONNÊTEMENT, AVEC SA RELANCE.
 * `onReessayer` ne doit relancer QUE cette section — jamais toute l'application.
 */
export function SectionErreur({ motif, onReessayer, quoi, compact, 'data-testid': testId }) {
  const estSession = motif === 'session';
  const message = messagePour(motif);
  const complement = estSession
    ? 'Reconnecte-toi pour la retrouver.'
    : quoi
      ? `Impossible de charger ${quoi}.`
      : '';

  return (
    <div
      data-testid={testId || 'section-erreur'}
      data-motif={motif}
      role="status"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        flexWrap: 'wrap',
        padding: compact ? '8px 10px' : '12px 14px',
        borderRadius: '10px',
        background: `rgba(${PRIMAIRE_RGB}, 0.06)`,
        border: `1px solid rgba(${PRIMAIRE_RGB}, 0.25)`,
        color: 'rgba(255,255,255,0.75)',
        fontSize: compact ? '12px' : '13px',
      }}
    >
      <span style={{ color: PRIMAIRE, display: 'inline-flex', flex: 'none' }}>
        {estSession ? <IconeVerrou /> : <IconeAlerte />}
      </span>
      <span style={{ flex: '1 1 160px', minWidth: 0 }}>
        {message} {complement}
      </span>
      {typeof onReessayer === 'function' && (
        <button
          type="button"
          onClick={onReessayer}
          data-testid="bouton-reessayer"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '5px 11px',
            borderRadius: '8px',
            border: `1px solid rgba(${PRIMAIRE_RGB}, 0.5)`,
            background: `rgba(${PRIMAIRE_RGB}, 0.12)`,
            color: PRIMAIRE,
            fontSize: '12px',
            fontWeight: 600,
            cursor: 'pointer',
            flex: 'none',
          }}
        >
          <IconeRelance />
          Réessayer
        </button>
      )}
    </div>
  );
}

/**
 * LA SESSION EST MORTE — on le dit une fois, en haut de l'écran.
 * `onReconnecter` ouvre la connexion ; il ne recharge JAMAIS la page.
 */
export function BanniereSession({ onReconnecter, 'data-testid': testId }) {
  return (
    <div
      data-testid={testId || 'banniere-session'}
      role="alert"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        flexWrap: 'wrap',
        padding: '14px 16px',
        marginBottom: '16px',
        borderRadius: '12px',
        background: `rgba(${PRIMAIRE_RGB}, 0.1)`,
        border: `1px solid rgba(${PRIMAIRE_RGB}, 0.45)`,
        color: 'rgba(255,255,255,0.9)',
        fontSize: '13.5px',
      }}
    >
      <span style={{ color: PRIMAIRE, display: 'inline-flex', flex: 'none' }}>
        <IconeVerrou taille={18} />
      </span>
      <span style={{ flex: '1 1 220px', minWidth: 0 }}>
        <strong style={{ display: 'block', marginBottom: '2px' }}>Session expirée</strong>
        Tes données sont intactes — il faut simplement te reconnecter pour y accéder de nouveau.
      </span>
      {typeof onReconnecter === 'function' && (
        <button
          type="button"
          onClick={onReconnecter}
          data-testid="bouton-reconnecter"
          style={{
            padding: '8px 16px',
            borderRadius: '9px',
            border: 'none',
            background: PRIMAIRE,
            color: '#fff',
            fontSize: '13px',
            fontWeight: 700,
            cursor: 'pointer',
            flex: 'none',
          }}
        >
          Se reconnecter
        </button>
      )}
    </div>
  );
}

export default { Compteur, SectionErreur, BanniereSession, messagePour };
