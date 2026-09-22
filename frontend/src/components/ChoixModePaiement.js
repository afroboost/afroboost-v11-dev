// V535 — « CHOISIS TON MODE DE PAIEMENT » : paiement intégral OU en 2 fois.
//
// Rendu SEULEMENT pour une offre qui laisse le choix (`offreAvecChoixPaiement`).
// Aucune option n'est présélectionnée : le fractionné n'est jamais choisi en
// silence. Les montants sont dérivés de l'offre ; le serveur les recalcule.
// Icônes SVG, couleurs via var(--primary-color) uniquement.
import React, { useState } from 'react';
import { optionsPaiement } from '../utils/modePaiement';

export default function ChoixModePaiement({ offre, prix, onChoisir, onFermer, occupe = false, titre = 'Choisis ton mode de paiement' }) {
  const [mode, setMode] = useState('');
  const options = optionsPaiement(offre, prix);
  if (!options) return null;
  const lignes = [options.integral, options.deuxFois];
  return (
    <div data-testid="choix-mode-paiement" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <p className="text-white text-sm" style={{ opacity: 0.85, lineHeight: 1.5, margin: 0 }}>
        {titre}
      </p>
      <div role="radiogroup" aria-label={titre} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {lignes.map((o) => {
          const choisi = mode === o.mode;
          return (
            <label key={o.mode} data-testid={`mode-paiement-${o.mode}`} data-choisi={choisi ? '1' : '0'}
              style={{
                display: 'flex', alignItems: 'flex-start', gap: 12, cursor: occupe ? 'not-allowed' : 'pointer',
                padding: '12px 14px', borderRadius: 14,
                border: `1px solid ${choisi ? 'var(--primary-color, #D91CD2)' : 'rgba(var(--primary-rgb, 217, 28, 210), 0.35)'}`,
                background: choisi ? 'rgba(var(--primary-rgb, 217, 28, 210), 0.14)' : 'rgba(255,255,255,0.03)',
              }}>
              <input type="radio" name="mode-paiement" value={o.mode} checked={choisi} disabled={occupe}
                onChange={() => setMode(o.mode)}
                style={{ marginTop: 3, accentColor: 'var(--primary-color, #D91CD2)' }} />
              <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <span className="text-white font-semibold text-sm">{o.titre}</span>
                <span className="text-white text-xs" style={{ opacity: 0.75 }}>{o.detail}</span>
              </span>
            </label>
          );
        })}
      </div>
      <p className="text-white text-xs" style={{ opacity: 0.6, margin: 0 }}>
        Total identique dans les deux cas : {options.total.toFixed(2).replace('.', ',')} CHF.
      </p>
      <button type="button" disabled={!mode || occupe} onClick={() => onChoisir(mode)}
        data-testid="mode-paiement-continuer"
        className="w-full py-3 rounded-lg btn-primary"
        style={{ opacity: !mode || occupe ? 0.5 : 1 }}>
        {occupe ? 'Redirection…' : 'Continuer vers le paiement'}
      </button>
      {onFermer ? (
        <button type="button" onClick={onFermer} disabled={occupe} data-testid="mode-paiement-annuler"
          className="w-full py-2 rounded-lg text-white text-sm" style={{ background: 'transparent', border: '1px solid rgba(255,255,255,0.15)' }}>
          Annuler
        </button>
      ) : null}
    </div>
  );
}
