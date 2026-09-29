/**
 * INV-2 : l'annonce de la séance d'invitation — une seule implémentation pour
 * les deux écrans du parcours d'essai existant :
 *   - `formulaire` : le formulaire « Vos informations » de la vitrine (App.js),
 *     qui n'a pas de sélecteur de séance ; on y ANNONCE la séance retenue ;
 *   - `espace`     : l'espace participant (SubscriberSpace), où la séance est
 *     PRÉSÉLECTIONNÉE dans la liste existante.
 * Rien n'est réservé ici : aucun bouton, aucune requête.
 */
import React from 'react';
import {
  libelleSeance,
  MESSAGE_SEANCE_INDISPONIBLE,
  MESSAGE_SEANCE_INDISPONIBLE_FORMULAIRE,
} from '../utils/invitationSeance';

const RGB = 'var(--primary-rgb, 217, 28, 210)';

function IconeCalendrier() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ flex: '0 0 auto', marginTop: 1 }}>
      <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
      <line x1="16" y1="2" x2="16" y2="6" />
      <line x1="8" y1="2" x2="8" y2="6" />
      <line x1="3" y1="10" x2="21" y2="10" />
    </svg>
  );
}

/**
 * @param {{ etat: 'ok'|'indisponible', nom?: string, occurrence?: string,
 *           variante?: 'formulaire'|'espace' }} props
 */
export default function InvitationSeanceBandeau({ etat, nom, occurrence, variante = 'espace' }) {
  if (etat === 'indisponible') {
    return (
      <p role="status" data-testid="inv2-seance-indisponible"
        className="text-xs mb-3 px-3 py-2 rounded-lg"
        style={{ background: 'rgba(245,158,11,0.15)', color: '#fbbf24', lineHeight: 1.4 }}>
        {variante === 'formulaire' ? MESSAGE_SEANCE_INDISPONIBLE_FORMULAIRE : MESSAGE_SEANCE_INDISPONIBLE}
      </p>
    );
  }
  if (etat !== 'ok') return null;
  const libelle = libelleSeance(occurrence || '');
  return (
    <div data-testid="inv2-seance-invitation" className="mb-3 px-3 py-2 rounded-lg"
      style={{
        background: `rgba(${RGB}, 0.10)`, border: `1px solid rgba(${RGB}, 0.45)`,
        color: '#fff', display: 'flex', gap: 8, alignItems: 'flex-start', fontSize: 13, lineHeight: 1.4,
      }}>
      <span style={{ color: 'var(--primary-color, #D91CD2)', display: 'inline-flex' }}><IconeCalendrier /></span>
      <span>
        <strong>Séance de ton invitation</strong>
        <br />
        <span data-testid="inv2-seance-libelle">{[nom, libelle].filter(Boolean).join(' — ')}</span>
        {variante === 'formulaire' ? (
          <>
            <br />
            <span style={{ opacity: 0.75, fontSize: 12 }}>Elle sera déjà sélectionnée à l’étape suivante : tu n’auras qu’à confirmer.</span>
          </>
        ) : null}
      </span>
    </div>
  );
}
