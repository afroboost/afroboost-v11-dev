/**
 * V607 — L'APERÇU EN DIRECT de « Ta carte » : ce que l'invité verra, recalculé à
 * chaque frappe depuis le formulaire (`apercuDepuisFormulaire`, pur). AUCUN appel
 * réseau. La carte image définitive (1200×630, serveur) reste à l'étape « Partage ».
 *
 * Adapté au TYPE : « Offert » (essai), « Gratuit » (événement gratuit), le prix
 * ACTIF + son palier (événement payant), rien pour le Pass Duo. Jamais « 0 CHF ».
 * Couleurs : var(--primary-color) / rgba(var(--primary-rgb)) seulement ; icônes SVG.
 */
import React from 'react';
import SvgIcon from '../SvgIcon';

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const rgbaP = (a) => `rgba(var(--primary-rgb, 217, 28, 210), ${a})`;

function maj(t) {
  const s = String(t || '');
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : '';
}

export default function ApercuInvitation({ apercu }) {
  const a = apercu || {};
  const quand = [maj(a.date_label), a.time_label].filter(Boolean).join(' · ');
  const fond = a.image_url && /^(https:\/\/|\/(?!\/))/.test(a.image_url) ? a.image_url : '';
  return (
    <div data-testid="inv-apercu-direct" aria-label="Aperçu de ta carte" style={{ marginBottom: '16px' }}>
      <div style={{ fontSize: '12px', color: 'rgba(255,255,255,0.6)', margin: '0 0 6px', display: 'flex', alignItems: 'center', gap: '6px' }}>
        <SvgIcon name="eye" size={14} /> Aperçu en direct
      </div>
      <div style={{
        position: 'relative', width: '100%', aspectRatio: '1200 / 630', borderRadius: '12px', overflow: 'hidden',
        background: fond ? `linear-gradient(90deg, rgba(10,4,16,0.88) 0%, rgba(10,4,16,0.55) 60%, rgba(10,4,16,0.25) 100%), url("${fond}") center / cover`
          : `linear-gradient(135deg, rgba(10,4,16,1) 0%, ${rgbaP(0.45)} 100%)`,
        border: `1px solid ${rgbaP(0.3)}`, boxSizing: 'border-box', padding: '4.5% 6%', color: 'rgba(255,255,255,0.98)',
        display: 'flex', flexDirection: 'column',
      }}>
        <div style={{ fontSize: 'clamp(9px, 2.4vw, 13px)', fontWeight: 800, letterSpacing: '0.04em', color: PRIMAIRE }}>
          AFROBOOST <span style={{ fontWeight: 400, color: 'rgba(255,255,255,0.75)' }}>Invitation</span>
        </div>
        <div data-testid="inv-apercu-inviteur" style={{ fontSize: 'clamp(9px, 2.3vw, 13px)', fontWeight: 700, marginTop: '4%' }}>
          {a.prenom ? `${a.prenom} t'invite` : "On t'invite"}
        </div>
        <div data-testid="inv-apercu-titre" style={{ fontSize: 'clamp(13px, 4vw, 22px)', fontWeight: 800, lineHeight: 1.15, marginTop: '2%',
          overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
          {a.titre}
        </div>
        {a.sous_titre ? <div style={{ fontSize: 'clamp(9px, 2.3vw, 13px)', color: 'rgba(255,255,255,0.8)', marginTop: '1%' }}>{a.sous_titre}</div> : null}
        {quand ? <div data-testid="inv-apercu-quand" style={{ fontSize: 'clamp(9px, 2.4vw, 13px)', fontWeight: 700, color: 'rgba(255,255,255,0.92)', marginTop: '2%' }}>{quand}</div> : null}
        {a.lieu ? <div data-testid="inv-apercu-lieu" style={{ fontSize: 'clamp(9px, 2.2vw, 12px)', color: 'rgba(255,255,255,0.8)' }}>{a.lieu}</div> : null}
        <div style={{ marginTop: 'auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
          {a.mention_prix ? (
            <span data-testid="inv-apercu-prix" style={{ background: 'rgba(255,255,255,0.96)', color: 'rgba(30,10,40,1)', borderRadius: '999px',
              padding: '3px 10px', fontSize: 'clamp(9px, 2.3vw, 13px)', fontWeight: 800, whiteSpace: 'nowrap' }}>{a.mention_prix}</span>
          ) : <span />}
          <span style={{ background: PRIMAIRE, borderRadius: '999px', padding: '4px 12px', fontSize: 'clamp(9px, 2.3vw, 13px)', fontWeight: 800,
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '60%' }}>{a.cta}</span>
        </div>
      </div>
      {(a.message || a.video_url || a.audio_url || (a.paliers && a.paliers.length > 1)) ? (
        <div style={{ marginTop: '8px', fontSize: '12.5px', color: 'rgba(255,255,255,0.75)', display: 'grid', gap: '4px' }}>
          {a.message ? <div data-testid="inv-apercu-message">« {a.message} »</div> : null}
          {a.paliers && a.paliers.length > 1 ? (
            <div data-testid="inv-apercu-paliers">{a.paliers.map((p) => `${p.libelle} ${p.prix} CHF${p.actif ? ' (actif)' : ''}`).join(' · ')}</div>
          ) : null}
          {a.video_url ? <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><SvgIcon name="video" size={14} /> Vidéo d'ambiance sur la page</div> : null}
          {a.audio_url ? <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><SvgIcon name="volume2" size={14} /> Un mot audio, à écouter au clic</div> : null}
        </div>
      ) : null}
    </div>
  );
}
