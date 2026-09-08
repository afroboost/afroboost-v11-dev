/**
 * F3 — MODIFIER SON PROFIL SPORDATEUR DEPUIS AFROBOOST.
 *
 * Le pendant écriture du panneau read-only (ProfilSocialPartage). Ici on ÉDITE
 * bio, ville et sports — les champs texte que l'éditeur Spordateur lui-même
 * laisse modifier, avec LES MÊMES RÈGLES (bio 300 caractères, sports dans une
 * liste fermée). L'enregistrement part vers `PATCH /api/spordate/unified-profile/me`,
 * qui écrit dans le VRAI `users/{uid}` Spordateur — pas dans un profil parallèle.
 *
 * CE COMPOSANT NE CONNAÎT NI uid, NI secret : l'intercepteur axios global porte
 * l'identité signée, le serveur résout le reste. Il n'écrit jamais rien d'autre
 * que ces trois champs (le serveur re-filtre de toute façon).
 *
 * ⚠️ Le canton n'est PAS éditable : l'éditeur Spordateur ne le modifie pas. Les
 * photos sont un lot séparé. displayName idem.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;
const BIO_MAX = 300;
// Miroir de la liste de l'éditeur Spordateur (AVAILABLE_SPORTS + danses).
const SPORTS = ['Tennis', 'Fitness', 'Running', 'Yoga', 'Crossfit', 'Football', 'Natation', 'Padel', 'Escalade', 'Afroboost', 'Danse', 'Cardio'];
const NIVEAUX = [['beginner', 'Débutant'], ['intermediate', 'Intermédiaire'], ['advanced', 'Avancé']];
const ACCENT = 'var(--primary-color, #D91CD2)';
const CADRE = { background: 'rgba(0,0,0,0.28)', border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.35)', borderRadius: '14px', padding: '18px' };

export default function EditeurProfilSpordateur() {
  const [etat, setEtat] = useState('chargement'); // chargement | pret | non_lie | indispo
  const [bio, setBio] = useState('');
  const [city, setCity] = useState('');
  const [sports, setSports] = useState([]); // [{name, level}]
  const [enCours, setEnCours] = useState(false);
  const [message, setMessage] = useState(null); // {ok, texte}

  useEffect(() => {
    let vivant = true;
    axios.get(`${API}/spordate/unified-profile/me`)
      .then((r) => {
        if (!vivant) return;
        const d = (r && r.data) || {};
        if (d.lie && d.profil) {
          setBio(d.profil.bio || '');
          setCity(d.profil.city || '');
          setSports(Array.isArray(d.profil.sports) ? d.profil.sports.filter((s) => s && s.name) : []);
          setEtat('pret');
        } else { setEtat('non_lie'); }
      })
      .catch(() => { if (vivant) setEtat('indispo'); });
    return () => { vivant = false; };
  }, []);

  const basculerSport = (name) => {
    setSports((prev) => {
      const i = prev.findIndex((s) => s.name === name);
      if (i >= 0) return prev.filter((s) => s.name !== name);
      return [...prev, { name, level: 'beginner' }];
    });
    setMessage(null);
  };
  const changerNiveau = (name, level) => {
    setSports((prev) => prev.map((s) => (s.name === name ? { ...s, level } : s)));
    setMessage(null);
  };

  const enregistrer = async () => {
    if (enCours) return; // §E — un double clic ne produit qu'un envoi
    setEnCours(true); setMessage(null);
    try {
      const r = await axios.patch(`${API}/spordate/unified-profile/me`, {
        profil: { bio: bio.slice(0, BIO_MAX), city: city.trim(), sports },
      });
      const d = (r && r.data) || {};
      if (d.lie && d.profil) {
        setBio(d.profil.bio || '');
        setCity(d.profil.city || '');
        setSports(Array.isArray(d.profil.sports) ? d.profil.sports.filter((s) => s && s.name) : []);
        setMessage({ ok: true, texte: 'Profil enregistré.' });
      } else {
        setMessage({ ok: false, texte: "Ton profil n'est pas relié — rien n'a été enregistré." });
      }
    } catch (e) {
      // Le texte saisi reste à l'écran : on ne perd pas le travail.
      setMessage({ ok: false, texte: "L'enregistrement a échoué. Ton texte est conservé, réessaie." });
    } finally {
      setEnCours(false);
    }
  };

  if (etat === 'chargement') {
    return <div data-testid="editeur-profil" style={CADRE}><p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '13px', margin: 0 }}>Chargement de ton profil…</p></div>;
  }
  if (etat === 'indispo') return null; // dégradation douce
  if (etat === 'non_lie') {
    return (
      <div data-testid="editeur-profil" style={CADRE}>
        <p data-testid="editeur-non-lie" style={{ color: '#fff', fontSize: '14px', fontWeight: 600, margin: '0 0 6px' }}>
          Ton profil social n'est pas encore relié
        </p>
        <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '13px', margin: 0 }}>
          Relie ton compte pour éditer ici ta bio, ta ville et tes sports.
        </p>
      </div>
    );
  }

  const estActif = (name) => sports.some((s) => s.name === name);
  const niveauDe = (name) => (sports.find((s) => s.name === name) || {}).level || 'beginner';

  return (
    <div data-testid="editeur-profil" style={CADRE}>
      <p style={{ color: '#fff', fontSize: '15px', fontWeight: 700, margin: '0 0 12px' }}>Mon profil</p>

      <label style={{ fontSize: '11px', color: 'rgba(255,255,255,0.55)', display: 'block', marginBottom: '4px' }}>Bio</label>
      <textarea
        data-testid="champ-bio" value={bio} maxLength={BIO_MAX}
        onChange={(e) => { setBio(e.target.value); setMessage(null); }}
        rows={4}
        style={{ width: '100%', boxSizing: 'border-box', fontSize: '13px', color: '#fff', padding: '9px 10px', borderRadius: '8px', background: 'rgba(0,0,0,0.32)', border: `1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.4)`, resize: 'vertical', fontFamily: 'inherit' }}
      />
      <p style={{ fontSize: '11px', color: 'rgba(255,255,255,0.4)', textAlign: 'right', margin: '2px 0 12px' }}>{bio.length}/{BIO_MAX}</p>

      <label style={{ fontSize: '11px', color: 'rgba(255,255,255,0.55)', display: 'block', marginBottom: '4px' }}>Ville</label>
      <input
        data-testid="champ-ville" value={city}
        onChange={(e) => { setCity(e.target.value); setMessage(null); }}
        style={{ width: '100%', boxSizing: 'border-box', fontSize: '13px', color: '#fff', padding: '9px 10px', borderRadius: '8px', background: 'rgba(0,0,0,0.32)', border: `1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.4)`, marginBottom: '12px' }}
      />

      <label style={{ fontSize: '11px', color: 'rgba(255,255,255,0.55)', display: 'block', marginBottom: '6px' }}>Sports</label>
      <div data-testid="champ-sports" style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '12px' }}>
        {SPORTS.map((name) => {
          const actif = estActif(name);
          return (
            <div key={name} style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
              <button
                type="button" data-testid={`sport-${name}`}
                onClick={() => basculerSport(name)}
                style={{ fontSize: '12px', padding: '5px 11px', borderRadius: '999px', cursor: 'pointer', color: '#fff',
                         background: actif ? ACCENT : 'transparent',
                         border: `1px solid rgba(var(--primary-rgb, 217, 28, 210), ${actif ? 0.9 : 0.35})` }}>
                {name}
              </button>
              {actif ? (
                <select
                  data-testid={`niveau-${name}`} value={niveauDe(name)}
                  onChange={(e) => changerNiveau(name, e.target.value)}
                  style={{ fontSize: '10px', padding: '2px', borderRadius: '6px', background: 'rgba(0,0,0,0.4)', color: '#fff', border: '1px solid rgba(255,255,255,0.2)' }}>
                  {NIVEAUX.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              ) : null}
            </div>
          );
        })}
      </div>

      <button
        type="button" data-testid="enregistrer-profil"
        onClick={enregistrer} disabled={enCours}
        style={{ width: '100%', minHeight: '44px', borderRadius: '10px', border: 'none', cursor: enCours ? 'default' : 'pointer',
                 background: ACCENT, color: '#fff', fontSize: '14px', fontWeight: 700, opacity: enCours ? 0.6 : 1 }}>
        {enCours ? 'Enregistrement…' : 'Enregistrer'}
      </button>

      {message ? (
        <p data-testid="editeur-message" role="status" style={{ fontSize: '12px', marginTop: '8px', margin: '8px 0 0',
             color: message.ok ? 'rgb(110, 231, 183)' : 'rgb(252, 165, 165)' }}>
          {message.texte}
        </p>
      ) : null}
    </div>
  );
}
