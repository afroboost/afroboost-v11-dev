// V605 — Page PUBLIQUE de prise de rendez-vous (/rdv/<jeton>), sans compte.
// Le jeton ne donne accès qu'aux créneaux libres de Coach Bassi et à la confirmation.
// Les créneaux viennent de l'agenda existant (calendar_events) ; la disponibilité
// est revérifiée par le serveur au moment exact de la confirmation.
import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;
const ZONE = 'Europe/Zurich';
const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const RGB = 'var(--primary-rgb, 217, 28, 210)';
const TEXTE = 'rgba(255,255,255,0.92)';
const DOUX = 'rgba(255,255,255,0.6)';

const jourDe = (iso) => new Date(iso).toLocaleDateString('fr-CH', { timeZone: ZONE, weekday: 'long', day: 'numeric', month: 'long' });
const cleJour = (iso) => new Date(iso).toLocaleDateString('fr-CA', { timeZone: ZONE });
const heureDe = (iso) => new Date(iso).toLocaleTimeString('fr-CH', { timeZone: ZONE, hour: '2-digit', minute: '2-digit' });

const Coche = () => (
  <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="10" /><path d="M7.5 12.5l3 3 6-6" />
  </svg>
);

const pastille = (actif) => ({
  padding: '10px 12px', borderRadius: '10px', fontSize: '14px', cursor: 'pointer', textAlign: 'center',
  border: `1px solid ${actif ? PRIMAIRE : 'rgba(255,255,255,0.18)'}`,
  background: actif ? `rgba(${RGB}, 0.22)` : 'rgba(255,255,255,0.04)', color: TEXTE,
});

export default function RendezVousPublic({ token }) {
  const [etat, setEtat] = useState({ chargement: true, erreur: '', donnees: null });
  const [jour, setJour] = useState('');
  const [creneau, setCreneau] = useState('');
  const [type, setType] = useState('visio');
  const [envoi, setEnvoi] = useState({ enCours: false, erreur: '', confirme: null });

  const charger = () => {
    setEtat((p) => ({ ...p, chargement: true }));
    axios.get(`${API}/public/rdv/${encodeURIComponent(token)}`)
      .then(({ data }) => setEtat({ chargement: false, erreur: '', donnees: data }))
      .catch((e) => setEtat({ chargement: false, donnees: null,
        erreur: (e.response && e.response.status === 404) ? 'Ce lien n’est pas valide.' : 'La page n’a pas pu être chargée.' }));
  };
  useEffect(charger, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  const jours = useMemo(() => {
    const m = {};
    ((etat.donnees && etat.donnees.creneaux) || []).forEach((c) => { (m[cleJour(c)] = m[cleJour(c)] || []).push(c); });
    return Object.entries(m);
  }, [etat.donnees]);
  const heures = (jours.find(([k]) => k === jour) || [null, []])[1];

  const confirmer = async () => {
    setEnvoi({ enCours: true, erreur: '', confirme: null });
    try {
      const { data } = await axios.post(`${API}/public/rdv/${encodeURIComponent(token)}`, { starts_at: creneau, type });
      setEnvoi({ enCours: false, erreur: '', confirme: data.rendez_vous });
    } catch (e) {
      const msg = (e.response && e.response.data && e.response.data.detail) || 'La confirmation a échoué.';
      setEnvoi({ enCours: false, erreur: msg, confirme: null });
      if (e.response && e.response.status === 409) { setCreneau(''); charger(); }
    }
  };

  const confirme = envoi.confirme || (etat.donnees && etat.donnees.deja_reserve);
  const types = (etat.donnees && etat.donnees.types) || [];

  return (
    <div data-testid="rdv-public" style={{ minHeight: '100vh', background: 'rgb(0,0,0)', color: TEXTE, fontFamily: 'inherit',
                                           display: 'flex', justifyContent: 'center', padding: '28px 16px', boxSizing: 'border-box' }}>
      <div style={{ width: '100%', maxWidth: '520px' }}>
        <div style={{ fontWeight: 800, letterSpacing: '0.18em', fontSize: '13px', color: PRIMAIRE }}>AFROBOOST</div>
        <h1 style={{ fontSize: '22px', margin: '8px 0 4px', lineHeight: 1.25 }}>Prendre rendez-vous avec Coach Bassi</h1>
        {etat.donnees && etat.donnees.organisation && (
          <div style={{ fontSize: '13px', color: DOUX }}>Pour {etat.donnees.organisation}</div>
        )}

        {etat.chargement && <p style={{ color: DOUX, marginTop: '24px' }}>Chargement des disponibilités…</p>}
        {etat.erreur && <p data-testid="rdv-erreur" style={{ marginTop: '24px' }}>{etat.erreur}</p>}

        {!etat.chargement && confirme && (
          <div data-testid="rdv-confirme" style={{ marginTop: '28px', padding: '20px', borderRadius: '14px',
                                                    border: `1px solid rgba(${RGB}, 0.5)`, background: `rgba(${RGB}, 0.10)`, textAlign: 'center' }}>
            <div style={{ color: PRIMAIRE }}><Coche /></div>
            <div style={{ fontSize: '18px', fontWeight: 700, marginTop: '8px' }}>Rendez-vous confirmé</div>
            <div style={{ marginTop: '10px', fontSize: '15px', textTransform: 'capitalize' }}>{jourDe(confirme.starts_at)}</div>
            <div style={{ fontSize: '15px' }}>{heureDe(confirme.starts_at)} · {confirme.type_libelle} · {confirme.duree_min} min</div>
            <div style={{ marginTop: '12px', fontSize: '12px', color: DOUX }}>Heure de Suisse. Coach Bassi vous contactera à l’heure prévue.</div>
          </div>
        )}

        {!etat.chargement && !confirme && etat.donnees && (
          <>
            {!jours.length && <p style={{ marginTop: '24px' }}>Aucun créneau disponible pour le moment.</p>}
            {jours.length > 0 && (
              <>
                <div style={{ marginTop: '24px', fontSize: '12px', fontWeight: 700, color: DOUX, letterSpacing: '0.06em' }}>1. CHOISIR LA DATE</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: '8px', marginTop: '8px' }}>
                  {jours.map(([k, liste]) => (
                    <button key={k} type="button" data-testid={`rdv-jour-${k}`} onClick={() => { setJour(k); setCreneau(''); }}
                            style={{ ...pastille(jour === k), textTransform: 'capitalize' }}>{jourDe(liste[0])}</button>
                  ))}
                </div>
              </>
            )}
            {jour && (
              <>
                <div style={{ marginTop: '20px', fontSize: '12px', fontWeight: 700, color: DOUX, letterSpacing: '0.06em' }}>2. CHOISIR L’HEURE</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(76px, 1fr))', gap: '8px', marginTop: '8px' }}>
                  {heures.map((c) => (
                    <button key={c} type="button" data-testid="rdv-heure" onClick={() => setCreneau(c)} style={pastille(creneau === c)}>{heureDe(c)}</button>
                  ))}
                </div>
              </>
            )}
            {creneau && (
              <>
                <div style={{ marginTop: '20px', fontSize: '12px', fontWeight: 700, color: DOUX, letterSpacing: '0.06em' }}>3. TYPE DE RENDEZ-VOUS</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', marginTop: '8px' }}>
                  {types.map((t) => (
                    <button key={t.id} type="button" data-testid={`rdv-type-${t.id}`} onClick={() => setType(t.id)} style={pastille(type === t.id)}>{t.libelle}</button>
                  ))}
                </div>
                <button type="button" data-testid="rdv-confirmer" onClick={confirmer} disabled={envoi.enCours}
                        style={{ marginTop: '22px', width: '100%', padding: '14px', borderRadius: '12px', border: 'none', cursor: 'pointer',
                                 background: PRIMAIRE, color: 'rgb(255,255,255)', fontSize: '15px', fontWeight: 800, letterSpacing: '0.04em',
                                 opacity: envoi.enCours ? 0.6 : 1 }}>
                  {envoi.enCours ? 'Confirmation…' : 'CONFIRMER LE RENDEZ-VOUS'}
                </button>
              </>
            )}
            {envoi.erreur && <p data-testid="rdv-envoi-erreur" style={{ marginTop: '12px', fontSize: '13px' }}>{envoi.erreur}</p>}
            <p style={{ marginTop: '22px', fontSize: '11px', color: DOUX }}>Heures affichées en heure de Suisse (Europe/Zurich). Durée : {(etat.donnees.duree_min || 30)} minutes.</p>
          </>
        )}
      </div>
    </div>
  );
}
