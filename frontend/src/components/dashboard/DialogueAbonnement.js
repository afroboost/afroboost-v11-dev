/**
 * V618i — FENÊTRE DE CONFIRMATION « ABONNEMENT » (suppression, abonnement déjà actif) + annonce.
 *
 * Remplace les `window.confirm` (texte brut, aucun résumé) : le coach voit QUI, QUOI, combien de
 * séances, jusqu'à quand, et ce qui sera conservé, avant de décider. Promesse : `demander(options)`
 * rend l'identifiant du bouton choisi (ou 'annuler'). `annoncer(texte)` affiche un bandeau 5 s
 * (l'ancien `validationMessage` du tableau de bord n'était rendu nulle part).
 *
 * Couleurs : var(--primary-color) uniquement ; aucune icône emoji.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';

const fond = 'rgba(10, 10, 14, 0.72)';

function Dialogue({ titre, lignes, note, boutons, onChoix }) {
  useEffect(() => {
    const echap = (e) => { if (e.key === 'Escape') onChoix('annuler'); };
    window.addEventListener('keydown', echap);
    return () => window.removeEventListener('keydown', echap);
  }, [onChoix]);
  return (
    <div data-testid="dialogue-abonnement" role="dialog" aria-modal="true" aria-label={titre}
         onClick={(e) => { if (e.target === e.currentTarget) onChoix('annuler'); }}
         style={{ position: 'fixed', inset: 0, zIndex: 10000, background: fond, display: 'flex',
           alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div style={{ width: '100%', maxWidth: 440, borderRadius: 16, padding: 20, color: 'rgba(255,255,255,0.95)',
        background: 'rgba(24, 24, 30, 0.98)', border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.35)' }}>
        <h3 style={{ margin: '0 0 12px', fontSize: 17, fontWeight: 800 }}>{titre}</h3>
        {(lignes || []).length > 0 && (
          <dl data-testid="dialogue-abonnement-resume" style={{ margin: 0, display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '6px 12px', fontSize: 14 }}>
            {lignes.map(([cle, valeur], i) => (
              <React.Fragment key={i}>
                <dt style={{ color: 'rgba(255,255,255,0.6)' }}>{cle}</dt>
                <dd style={{ margin: 0, fontWeight: 600, wordBreak: 'break-word' }}>{valeur}</dd>
              </React.Fragment>
            ))}
          </dl>
        )}
        {note && (
          <p data-testid="dialogue-abonnement-note" style={{ margin: '14px 0 0', fontSize: 13, lineHeight: 1.45, color: 'rgba(255,255,255,0.78)' }}>{note}</p>
        )}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'flex-end', marginTop: 18 }}>
          {(boutons || []).map((b) => (
            <button key={b.id} type="button" data-testid={`dialogue-abonnement-${b.id}`} onClick={() => onChoix(b.id)}
                    style={{ padding: '9px 14px', borderRadius: 10, fontSize: 14, fontWeight: 700, cursor: 'pointer',
                      border: b.danger ? '1px solid rgba(239, 68, 68, 0.6)' : '1px solid rgba(255,255,255,0.18)',
                      background: b.danger ? 'rgba(239, 68, 68, 0.22)'
                        : (b.primaire ? 'var(--primary-color, #D91CD2)' : 'rgba(255,255,255,0.06)'),
                      color: 'rgba(255,255,255,0.96)' }}>
              {b.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export function useDialogueAbonnement() {
  const [options, setOptions] = useState(null);
  const [annonce, setAnnonce] = useState('');
  const resoudre = useRef(null);
  const minuteur = useRef(null);
  const demander = useCallback((opts) => new Promise((res) => { resoudre.current = res; setOptions(opts); }), []);
  const choisir = useCallback((id) => {
    const r = resoudre.current;
    resoudre.current = null;
    setOptions(null);
    if (r) r(id);
  }, []);
  const annoncer = useCallback((texte) => {
    setAnnonce(String(texte || ''));
    if (minuteur.current) clearTimeout(minuteur.current);
    minuteur.current = setTimeout(() => setAnnonce(''), 5000);
  }, []);
  useEffect(() => () => { if (minuteur.current) clearTimeout(minuteur.current); }, []);
  const ui = (
    <>
      {options && <Dialogue {...options} onChoix={choisir} />}
      {annonce && (
        <div role="status" data-testid="annonce-abonnement"
             style={{ position: 'fixed', left: 16, right: 16, bottom: 20, zIndex: 10001, margin: '0 auto', maxWidth: 440,
               padding: '12px 16px', borderRadius: 12, fontSize: 14, fontWeight: 600, color: 'rgba(255,255,255,0.96)',
               background: 'rgba(24, 24, 30, 0.97)', border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.5)' }}>
          {annonce}
        </div>
      )}
    </>
  );
  return [ui, demander, annoncer];
}

export function formaterJour(valeur) {
  const m = String(valeur || '').match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : (valeur || '—');
}
