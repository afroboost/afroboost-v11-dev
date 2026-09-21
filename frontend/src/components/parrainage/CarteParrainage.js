/**
 * V534 — CARTE « PARRAINAGE » DE L'ESPACE ABONNÉ.
 *
 * Même gabarit que ses voisines (`rounded-2xl p-5`, panneau et bordure de
 * SubscriberSpace), placée entre « Mon QR Code » et « Mes prochaines
 * séances » avec `order: 0` — donc TOUJOURS après les cartes ESSAI-7
 * (`order: -1`) et la confirmation P2-UX (`order: -2`), qu'elle ne touche pas.
 *
 * Deux boutons, une seule destination : le Centre (/parrainage). Aucun appel
 * réseau ici — la carte n'apparaît que si le parent sait le programme ouvert.
 */
import React from 'react';
import SvgIcon from '../SvgIcon';

const PANEL = 'rgba(255,255,255,0.04)';
const BORDER = 'rgba(255,255,255,0.08)';

export default function CarteParrainage({ enabled }) {
  if (!enabled) return null;
  const aller = () => { window.location.href = '/parrainage'; };
  return (
    <section
      className="rounded-2xl p-5"
      data-testid="carte-parrainage"
      style={{ order: 0, background: PANEL, border: `1px solid ${BORDER}` }}
    >
      <p className="text-white/60 text-xs uppercase tracking-wider mb-1">Parrainage</p>
      <h2 className="text-lg font-bold" style={{ margin: '0 0 6px' }}>Invite un ami et viens à deux.</h2>
      <div className="flex items-center gap-2 text-sm" style={{ color: 'rgba(255,255,255,0.8)', margin: '10px 0' }}>
        <span style={{
          width: 28, height: 28, borderRadius: '50%', flex: 'none', display: 'grid', placeItems: 'center',
          border: '1px solid var(--primary-color, #D91CD2)', background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.18)',
          color: 'var(--primary-color, #D91CD2)',
        }}>
          <SvgIcon name="users" size={14} />
        </span>
        <span>Ton ami profite d'un essai gratuit, vous avez chacun votre billet.</span>
      </div>
      <div className="grid grid-cols-2 gap-2 mt-2">
        <button
          type="button"
          onClick={aller}
          data-testid="carte-parrainage-inviter"
          className="py-2.5 rounded-xl text-sm font-semibold transition-transform active:scale-95"
          style={{
            color: 'white', border: 'none',
            background: 'linear-gradient(135deg, var(--primary-color, #D91CD2), var(--secondary-color, #8b5cf6))',
          }}
        >
          Inviter un ami
        </button>
        <button
          type="button"
          onClick={aller}
          data-testid="carte-parrainage-voir"
          className="py-2.5 rounded-xl text-sm font-semibold transition-transform active:scale-95"
          style={{
            color: 'white', background: 'transparent',
            border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.45)',
          }}
        >
          Voir mon Parrainage
        </button>
      </div>
    </section>
  );
}
