/**
 * F2 — LE PROFIL SOCIAL PARTAGÉ, AFFICHÉ DANS AFROBOOST (LECTURE SEULE).
 *
 * Une même personne ne devrait pas tenir deux profils. Quand son compte
 * afroboost est relié à son compte Spordateur, ce panneau montre — dans
 * l'espace afroboost — le profil social qu'elle tient sur Spordateur : photo,
 * nom, bio, ville, sports.
 *
 * CE COMPOSANT NE FAIT QU'UNE CHOSE : un GET. Il n'écrit rien, ne modifie rien,
 * ne duplique aucune photo (il affiche les URL telles que le serveur les rend).
 * L'identité voyage par l'intercepteur axios global (JWT signé ou jeton abonné) ;
 * ce composant n'ajoute aucun en-tête et ne connaît aucun secret.
 *
 * TROIS ÉTATS, TOUS SAINS :
 *   - lié           -> le profil ;
 *   - non lié       -> une invitation discrète à relier, jamais une erreur ;
 *   - indisponible  -> un message neutre, l'espace afroboost reste utilisable.
 *
 * AUCUN JARGON pour l'utilisateur : ni « uid », ni « bridge », ni « Firestore ».
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

// Couleurs par variables CSS du coach — jamais d'hexa figé (règle projet).
const CADRE = {
  background: 'rgba(0,0,0,0.28)',
  border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.35)',
  borderRadius: '14px',
  padding: '18px',
};
const ACCENT = 'var(--primary-color, #D91CD2)';

function Puce({ children }) {
  return (
    <span style={{
      display: 'inline-block', fontSize: '12px', padding: '4px 10px',
      borderRadius: '999px', marginRight: '6px', marginBottom: '6px',
      color: '#fff', background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.22)',
      border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.4)',
    }}>{children}</span>
  );
}

export default function ProfilSocialPartage() {
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
    return (
      <div data-testid="profil-social" style={CADRE}>
        <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '13px', margin: 0 }}>
          Chargement de ton profil…
        </p>
      </div>
    );
  }

  if (etat === 'indispo') {
    // Dégradation douce : on ne casse pas l'espace, on n'affiche pas d'erreur
    // alarmante pour une fonctionnalité secondaire.
    return null;
  }

  if (etat === 'non_lie') {
    return (
      <div data-testid="profil-social" style={CADRE}>
        <p data-testid="profil-non-lie" style={{ color: '#fff', fontSize: '14px', fontWeight: 600, margin: '0 0 6px' }}>
          Ton profil social n'est pas encore relié
        </p>
        <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '13px', margin: 0 }}>
          Relie ton compte pour retrouver ici ta photo, ta bio et tes sports.
        </p>
      </div>
    );
  }

  // etat === 'lie'
  const p = profil || {};
  const galerie = Array.isArray(p.photos) ? p.photos.filter(Boolean) : [];
  const principale = p.photoURL || galerie[0] || null;
  const lieu = [p.city, p.canton].filter(Boolean).join(', ');
  const sports = Array.isArray(p.sports) ? p.sports.filter((s) => s && s.name) : [];

  return (
    <div data-testid="profil-social" style={CADRE}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
        {principale ? (
          <img
            data-testid="profil-photo"
            src={principale}
            alt={p.displayName || 'Profil'}
            style={{ width: '64px', height: '64px', borderRadius: '50%', objectFit: 'cover',
                     border: `2px solid ${ACCENT}`, flexShrink: 0, background: 'rgba(255,255,255,0.05)' }}
          />
        ) : (
          <div data-testid="profil-photo-vide" style={{
            width: '64px', height: '64px', borderRadius: '50%', flexShrink: 0,
            background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.18)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff', fontSize: '22px', fontWeight: 700,
          }}>{(p.displayName || '?').trim().charAt(0).toUpperCase()}</div>
        )}
        <div style={{ minWidth: 0, flex: 1 }}>
          {p.displayName ? (
            <p data-testid="profil-nom" style={{ color: '#fff', fontSize: '17px', fontWeight: 700, margin: 0 }}>
              {p.displayName}
            </p>
          ) : null}
          {lieu ? (
            <p data-testid="profil-lieu" style={{ color: 'rgba(255,255,255,0.6)', fontSize: '13px', margin: '2px 0 0' }}>
              {lieu}
            </p>
          ) : null}
          {/* Mention discrète, sans jargon : d'où vient ce profil. */}
          <p style={{ color: 'rgba(255,255,255,0.35)', fontSize: '11px', margin: '4px 0 0' }}>
            Profil social partagé
          </p>
        </div>
      </div>

      {p.bio ? (
        <p data-testid="profil-bio" style={{ color: 'rgba(255,255,255,0.85)', fontSize: '13px',
                                             lineHeight: 1.5, margin: '12px 0 0', whiteSpace: 'pre-wrap' }}>
          {p.bio}
        </p>
      ) : null}

      {sports.length > 0 ? (
        <div data-testid="profil-sports" style={{ marginTop: '12px' }}>
          {sports.map((s, i) => (
            <Puce key={`${s.name}-${i}`}>{s.name}{s.level ? ` · ${s.level}` : ''}</Puce>
          ))}
        </div>
      ) : null}

      {galerie.length > 1 ? (
        <div data-testid="profil-galerie" style={{ display: 'flex', gap: '8px', marginTop: '12px', flexWrap: 'wrap' }}>
          {galerie.slice(1, 5).map((url, i) => (
            <img key={i} src={url} alt="" loading="lazy"
                 style={{ width: '52px', height: '52px', borderRadius: '10px', objectFit: 'cover',
                          background: 'rgba(255,255,255,0.05)' }} />
          ))}
        </div>
      ) : null}
    </div>
  );
}
