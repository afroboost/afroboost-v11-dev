/**
 * V560 — MENU RAPIDE DE L'ESPACE ABONNÉ : des raccourcis compacts (icône + mot
 * court), au plus deux lignes, pour ne plus faire défiler une page trop longue.
 * Il ne décide de rien : chaque entrée reçoit son action du parent, et une
 * entrée indisponible n'est simplement pas passée.
 */
import React from 'react';
import SvgIcon from '../SvgIcon';

export default function MenuRapide({ entrees }) {
  const liste = (entrees || []).filter(Boolean);
  if (!liste.length) return null;
  return (
    <nav aria-label="Menu rapide" data-testid="menu-rapide"
         style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(88px, 1fr))', gap: 8 }}>
      {liste.map((e) => (
        <button key={e.id} type="button" onClick={(ev) => e.onClick(ev.currentTarget)} data-testid={`menu-rapide-${e.id}`}
                className="rounded-xl text-xs font-semibold transition-transform active:scale-95"
                style={{
                  minHeight: 56, padding: '8px 6px', display: 'flex', flexDirection: 'column', alignItems: 'center',
                  justifyContent: 'center', gap: 4, color: 'rgba(255,255,255,0.92)', cursor: 'pointer',
                  background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.35)',
                }}>
          <span style={{ color: 'var(--primary-color, #D91CD2)', display: 'inline-flex' }}><SvgIcon name={e.icone} size={18} /></span>
          <span>{e.libelle}</span>
        </button>
      ))}
    </nav>
  );
}
