/**
 * V610o — « TON IMPACT AFROBOOST » : Boosts CUMULÉS, prochain palier, paliers débloqués,
 * « +1 Boost ! » (interne seulement : aucun e-mail, aucun WhatsApp).
 *
 * Données : le SERVEUR (`/api/ambassadeur/mon-impact` — session d'espace — ou
 * `/api/ambassadeur/impact/session/<cs>` — paiement confirmé). Rien n'est calculé ici :
 * aucun faux compteur, aucune place restante inventée.
 * « Vu » : mémoire locale (le dernier Boost / palier montré), jamais une donnée serveur.
 * Couleurs : var(--primary-color) ; icônes SVG.
 */
import React, { useEffect, useState } from 'react';
import SvgIcon from './SvgIcon';

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const rgbaP = (a) => `rgba(var(--primary-rgb, 217, 28, 210), ${a})`;
const CLE_VU = 'af_boost_vu';

const PHRASES_PALIER = {
  pass_ami: 'Ton Pass Ami est débloqué !',
  recompense: 'Ta récompense Afroboost est débloquée !',
  vip: 'Tu deviens Ambassadeur VIP !',
};

function lireVu() {
  try { return JSON.parse(window.localStorage.getItem(CLE_VU) || 'null') || {}; } catch (e) { return {}; }
}
function ecrireVu(v) {
  try { window.localStorage.setItem(CLE_VU, JSON.stringify(v)); } catch (e) { /* ignore */ }
}

/** Les nouveautés depuis la dernière visite : Boosts récents et paliers débloqués. */
export function nouveautes(impact, vu) {
  const i = impact || {};
  const v = vu || {};
  const vus = new Set(Array.isArray(v.boosts) ? v.boosts : []);
  const palVus = new Set(Array.isArray(v.paliers) ? v.paliers : []);
  return {
    boosts: (Array.isArray(i.recents) ? i.recents : []).filter((b) => b && b.id && !vus.has(b.id)),
    paliers: (Array.isArray(i.recompenses) ? i.recompenses : []).filter((r) => r && r.palier && !palVus.has(r.palier)),
  };
}

export default function ImpactAfroboost({ impact, compact = false, onPartager, testid = 'impact-afroboost' }) {
  const [annonces, setAnnonces] = useState({ boosts: [], paliers: [] });
  useEffect(() => {
    if (!impact || compact) return;
    const n = nouveautes(impact, lireVu());
    if (!n.boosts.length && !n.paliers.length) return;
    setAnnonces(n);
    ecrireVu({ boosts: (impact.recents || []).map((b) => b.id), paliers: (impact.recompenses || []).map((r) => r.palier) });
  }, [impact, compact]);
  if (!impact || !impact.progression) return null;
  const p = impact.progression;
  const prochain = p.prochain;
  const cible = prochain ? prochain.seuil : p.boosts;
  const pct = cible ? Math.min(100, Math.round((p.boosts / cible) * 100)) : 100;
  const amis = Number(impact.amis || p.boosts || 0);
  return (
    <div data-testid={testid} style={{ marginTop: '14px', padding: compact ? '12px' : '16px 14px', borderRadius: '16px', textAlign: 'left',
      background: 'rgba(255,255,255,0.05)', border: `1px solid ${rgbaP(0.35)}` }}>
      {annonces.boosts.slice(0, 2).map((b) => (
        <p key={b.id} data-testid="impact-plus-un" role="status" style={{ margin: '0 0 8px', padding: '8px 10px', borderRadius: 10, background: rgbaP(0.18), fontSize: '14px' }}>
          <strong style={{ color: PRIMAIRE }}>+1 Boost !</strong> {b.prenom ? `${b.prenom} vient de rejoindre Afroboost grâce à ton invitation.` : 'Un ami vient de rejoindre Afroboost grâce à ton invitation.'}
        </p>
      ))}
      {annonces.paliers.map((r) => (
        <p key={r.palier} data-testid={`impact-palier-${r.palier}`} role="status" style={{ margin: '0 0 8px', padding: '8px 10px', borderRadius: 10, background: rgbaP(0.24), fontSize: '14px', fontWeight: 700, display: 'flex', gap: 8, alignItems: 'center' }}>
          <SvgIcon name={r.palier === 'vip' ? 'fire' : 'gift'} size={16} /> {PHRASES_PALIER[r.palier] || `${r.libelle} débloqué !`}
        </p>
      ))}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 800, fontSize: compact ? '15px' : '16px', color: 'rgba(255,255,255,0.97)' }}>
        <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name="fire" size={compact ? 18 : 20} /></span> Ton impact Afroboost
        {p.vip ? <span data-testid="impact-vip" style={{ marginLeft: 'auto', fontSize: '12px', padding: '3px 10px', borderRadius: 999, background: PRIMAIRE }}>Ambassadeur VIP</span> : null}
      </div>
      {amis > 0 ? (
        <p data-testid="impact-amis" style={{ margin: '6px 0 0', fontSize: '14px', color: 'rgba(255,255,255,0.88)' }}>
          {amis > 1 ? `${amis} amis ont rejoint grâce à toi` : '1 ami a rejoint grâce à toi'}
        </p>
      ) : null}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '10px' }}>
        <span data-testid="impact-compteur" style={{ fontWeight: 800, fontSize: '15px', whiteSpace: 'nowrap', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name="fire" size={15} /></span>
          {prochain ? `${p.boosts} / ${prochain.seuil} Boosts` : `${p.boosts} Boosts`}
        </span>
        <div role="progressbar" aria-valuemin={0} aria-valuemax={cible} aria-valuenow={p.boosts} style={{ flex: 1, height: 8, borderRadius: 99, background: 'rgba(255,255,255,0.1)', overflow: 'hidden' }}>
          <div style={{ width: `${pct}%`, height: '100%', background: PRIMAIRE }} />
        </div>
      </div>
      {prochain ? (
        <p data-testid="impact-prochain" style={{ margin: '8px 0 0', fontSize: '13.5px', color: 'rgba(255,255,255,0.82)', display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
          Encore {prochain.restant} {prochain.restant > 1 ? 'amis' : 'ami'} pour débloquer :
          <strong style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}><SvgIcon name={prochain.cle === 'vip' ? 'fire' : 'gift'} size={14} /> {prochain.libelle}</strong>
        </p>
      ) : null}
      {!compact && Array.isArray(impact.recompenses) && impact.recompenses.length ? (
        <div data-testid="impact-recompenses" style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
          {impact.recompenses.map((r) => (
            <span key={r.palier} style={{ fontSize: '12.5px', padding: '4px 10px', borderRadius: 999, background: rgbaP(0.16), border: `1px solid ${rgbaP(0.4)}` }}>
              {r.libelle}{r.etat_libelle ? ` · ${r.etat_libelle}` : ''}
            </span>
          ))}
        </div>
      ) : null}
      {typeof onPartager === 'function' ? (
        <button type="button" data-testid="impact-partager" onClick={onPartager}
                style={{ width: '100%', minHeight: '50px', marginTop: '12px', borderRadius: '14px', border: 'none', background: PRIMAIRE, color: 'rgba(255,255,255,1)',
                  fontWeight: 800, fontSize: '16px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '8px', cursor: 'pointer' }}>
          <SvgIcon name="share" size={18} /> Partager et inviter
        </button>
      ) : null}
    </div>
  );
}
