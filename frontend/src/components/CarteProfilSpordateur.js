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
  const [activationOn, setActivationOn] = useState(false); // F4 dormant par défaut
  // F4 — activation volontaire (État B). La case n'est JAMAIS pré-cochée.
  const [consentOuvert, setConsentOuvert] = useState(false);
  const [consentCoche, setConsentCoche] = useState(false);
  const [activation, setActivation] = useState(false);
  const [masque, setMasque] = useState(false);

  const activer = () => {
    if (!consentCoche || activation) return;
    setActivation(true);
    // Afroboost n'ouvre NI compte NI liaison : il émet un jeton signé attestant
    // identité + consentement, et nous renvoie l'URL du parcours Spordateur.
    axios.post(`${API}/spordate/activate`, { consent: true })
      .then((r) => {
        const url = (r && r.data && r.data.url) || '';
        if (url) { window.location.href = url; }
        else { setActivation(false); }
      })
      .catch(() => { setActivation(false); });
  };

  useEffect(() => {
    let vivant = true;
    // Le drapeau F4 (public) : décide si l'état « non lié » propose l'activation
    // ou reste passif. Lu à part pour ne pas toucher la route de profil.
    axios.get(`${API}/feature-flags`)
      .then((r) => { if (vivant) setActivationOn(!!(r && r.data && r.data.SOCIAL_ACTIVATION_ENABLED)); })
      .catch(() => { /* défaut OFF : carte passive */ });
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
    if (masque) return null;   // « Plus tard » : l'espace reste utilisable (État C)
    // F4 dormant : tant que le drapeau est OFF, on garde l'état passif d'avant.
    if (!activationOn) {
      return (
        <div data-testid="carte-profil" style={CADRE}>
          <p data-testid="carte-non-lie" style={{ color: '#fff', fontSize: '13px', fontWeight: 600, margin: 0 }}>
            Profil social non encore activé
          </p>
        </div>
      );
    }
    return (
      <div data-testid="carte-profil" style={CADRE}>
        <p data-testid="carte-activer-titre" style={{ color: '#fff', fontSize: '14px', fontWeight: 700, margin: '0 0 4px' }}>
          Profil social
        </p>
        <p style={{ color: 'rgba(255,255,255,0.7)', fontSize: '12.5px', lineHeight: 1.45, margin: '0 0 10px' }}>
          Active ton profil social pour utiliser les fonctions communautaires.
        </p>

        {!consentOuvert ? (
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
            <button
              type="button" data-testid="carte-activer"
              onClick={() => setConsentOuvert(true)}
              style={{ padding: '9px 16px', background: ACCENT, color: '#fff', border: 'none',
                       borderRadius: '10px', cursor: 'pointer', fontSize: '13px', fontWeight: 600 }}>
              Activer mon profil social
            </button>
            <button
              type="button" data-testid="carte-plus-tard"
              onClick={() => setMasque(true)}
              style={{ padding: '9px 14px', background: 'transparent', color: 'rgba(255,255,255,0.55)',
                       border: '1px solid rgba(255,255,255,0.14)', borderRadius: '10px', cursor: 'pointer', fontSize: '12.5px' }}>
              Plus tard
            </button>
          </div>
        ) : (
          <div data-testid="carte-consentement">
            <p style={{ color: 'rgba(255,255,255,0.8)', fontSize: '12px', lineHeight: 1.5, margin: '0 0 8px' }}>
              Ton profil social appartient à Spordateur. Il pourra être utilisé dans les fonctions
              sociales / rencontre. Certaines informations deviendront visibles selon les règles de
              confidentialité Spordateur, que tu pourras gérer dans « Confidentialité ». L'activation
              est facultative.
            </p>
            <label style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', cursor: 'pointer', margin: '0 0 12px' }}>
              <input type="checkbox" data-testid="carte-consent-case"
                     checked={consentCoche} onChange={(e) => setConsentCoche(e.target.checked)}
                     style={{ marginTop: '2px', accentColor: '#D91CD2' }} />
              <span style={{ color: '#fff', fontSize: '12.5px', lineHeight: 1.4 }}>
                J'accepte d'activer mon profil social Spordateur.
              </span>
            </label>
            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
              <button
                type="button" data-testid="carte-activer-confirmer"
                onClick={activer} disabled={!consentCoche || activation}
                style={{ padding: '9px 16px', border: 'none', borderRadius: '10px',
                         fontSize: '13px', fontWeight: 600,
                         cursor: (!consentCoche || activation) ? 'not-allowed' : 'pointer',
                         background: (!consentCoche || activation) ? 'rgba(var(--primary-rgb, 217, 28, 210), 0.35)' : ACCENT,
                         color: '#fff', opacity: (!consentCoche || activation) ? 0.7 : 1 }}>
                {activation ? 'Activation…' : 'Activer'}
              </button>
              <button
                type="button" data-testid="carte-consent-annuler"
                onClick={() => { setConsentOuvert(false); setConsentCoche(false); }}
                style={{ padding: '9px 14px', background: 'transparent', color: 'rgba(255,255,255,0.55)',
                         border: '1px solid rgba(255,255,255,0.14)', borderRadius: '10px', cursor: 'pointer', fontSize: '12.5px' }}>
                Annuler
              </button>
            </div>
          </div>
        )}
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
