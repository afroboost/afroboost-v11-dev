/**
 * F3 — L'ENTRÉE COMPACTE VERS LA VRAIE PAGE PROFIL SPORDATEUR.
 *
 * On ne reconstruit PAS le profil dans Afroboost. Cette carte montre juste, en
 * une ligne, l'avatar et le nom, avec « Gérer mon profil ». Le clic ouvre la
 * VRAIE page `/rencontre/profile` — celle qui porte déjà Mon profil, Parrainage,
 * Confidentialité, Premium, Boost, la galerie : tout, sans duplication.
 *
 * L'entrée passe par le pont (auto-login) préparé d'avance : on arrive sur la
 * page profil DÉJÀ connecté, sans écran intermédiaire. `next=/profile` dit au
 * pont où atterrir après le login.
 *
 * Compte non lié → « Profil social non encore activé » ; pont indisponible →
 * la carte disparaît discrètement, l'espace reste utilisable.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { prechargerSpordate, entrerDansSpordate } from '../utils/spordateHandoff';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;
const ACCENT = 'var(--primary-color, #D91CD2)';
const CADRE = { background: 'rgba(0,0,0,0.28)', border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.35)', borderRadius: '14px', padding: '14px' };

export default function CarteProfilSpordateur() {
  const [etat, setEtat] = useState('chargement'); // chargement | lie | non_lie | indispo
  const [profil, setProfil] = useState(null);

  useEffect(() => {
    let vivant = true;
    axios.get(`${API}/spordate/unified-profile/me`)
      .then((r) => {
        if (!vivant) return;
        const d = (r && r.data) || {};
        if (d.lie && d.profil) { setProfil(d.profil); setEtat('lie'); }
        else { setEtat('non_lie'); }
      })
      .catch(() => { if (vivant) setEtat('indispo'); });
    return () => { vivant = false; };
  }, []);

  if (etat === 'chargement') {
    return <div data-testid="carte-profil" style={CADRE}><p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '13px', margin: 0 }}>Chargement de ton profil…</p></div>;
  }
  if (etat === 'indispo') return null;

  if (etat === 'non_lie') {
    return (
      <div data-testid="carte-profil" style={CADRE}>
        <p data-testid="carte-non-lie" style={{ color: '#fff', fontSize: '13px', fontWeight: 600, margin: 0 }}>
          Profil social non encore activé
        </p>
      </div>
    );
  }

  const p = profil || {};
  const galerie = Array.isArray(p.photos) ? p.photos.filter(Boolean) : [];
  const avatar = p.photoURL || galerie[0] || null;
  const ouvrir = () => entrerDansSpordate('/profile');
  const survol = () => prechargerSpordate();

  return (
    <button
      type="button" data-testid="carte-profil"
      onClick={ouvrir} onMouseEnter={survol} onFocus={survol} onTouchStart={survol}
      aria-label="Gérer mon profil sur Spordateur"
      style={{ ...CADRE, width: '100%', display: 'flex', alignItems: 'center', gap: '12px',
               cursor: 'pointer', textAlign: 'left', color: '#fff' }}>
      {avatar ? (
        <img data-testid="carte-avatar" src={avatar} alt=""
             style={{ width: '48px', height: '48px', borderRadius: '50%', objectFit: 'cover',
                      border: `2px solid ${ACCENT}`, flexShrink: 0, background: 'rgba(255,255,255,0.05)' }} />
      ) : (
        <div data-testid="carte-avatar-vide" style={{ width: '48px', height: '48px', borderRadius: '50%', flexShrink: 0,
             background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.18)', display: 'flex', alignItems: 'center',
             justifyContent: 'center', color: '#fff', fontSize: '18px', fontWeight: 700 }}>
          {(p.displayName || '?').trim().charAt(0).toUpperCase()}
        </div>
      )}
      <div style={{ minWidth: 0, flex: 1 }}>
        {p.displayName ? (
          <p data-testid="carte-nom" style={{ color: '#fff', fontSize: '15px', fontWeight: 700, margin: 0 }}>{p.displayName}</p>
        ) : null}
        <p style={{ color: ACCENT, fontSize: '12px', margin: '2px 0 0', fontWeight: 600 }}>Gérer mon profil →</p>
      </div>
    </button>
  );
}
