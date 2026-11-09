// V657 : page publique du lien privé d'une entreprise (/entreprise/<jeton>).
// Inscription d'un·e employé·e à 0 CHF, billet + QR d'entrée. Aucune autre page n'est concernée.
import React, { useEffect, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import SvgIcon from './SvgIcon';

const API = (process.env.REACT_APP_BACKEND_URL || '') + '/api';
const NOMS_MOIS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'];
const libelleMois = (m) => { const [a, mm] = String(m || '').split('-'); return (NOMS_MOIS[Number(mm) - 1] || m) + ' ' + (a || ''); };
const libelleDate = (iso) => {
  const m = String(iso || '').match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  return m ? `${m[3]}.${m[2]}.${m[1]} à ${m[4]}h${m[5]}` : '';
};

const page = { minHeight: '100vh', background: 'rgb(8,4,12)', color: '#fff', padding: '24px 16px', boxSizing: 'border-box' };
const boite = { maxWidth: 520, margin: '0 auto' };
const champ = { width: '100%', boxSizing: 'border-box', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 10, color: '#fff', padding: '11px 12px', fontSize: 15 };
const bouton = { width: '100%', background: 'var(--primary-color, #D91CD2)', border: 'none', borderRadius: 12, color: '#fff', padding: '13px', fontSize: 16, fontWeight: 700, cursor: 'pointer' };

const CorporateInvitation = ({ token }) => {
  const [info, setInfo] = useState(null);
  const [erreur, setErreur] = useState('');
  const [mois, setMois] = useState('');
  const [f, setF] = useState({ nom: '', email: '', whatsapp: '', terms_accepted: false });
  const [envoi, setEnvoi] = useState(false);
  const [msg, setMsg] = useState('');
  const [billet, setBillet] = useState(null);

  useEffect(() => {
    let vivant = true;
    fetch(`${API}/corporate/invitation/${encodeURIComponent(token)}`)
      .then(r => r.json().then(d => ({ ok: r.ok, d })))
      .then(({ ok, d }) => {
        if (!vivant) return;
        if (!ok) { setErreur((d && d.detail) || 'Invitation introuvable.'); return; }
        setInfo(d);
        const premiere = (d.editions || []).find(e => e.statut === 'planifiee' && e.inscriptions_ouvertes && e.places_restantes > 0);
        if (premiere) setMois(premiere.mois);
      })
      .catch(() => { if (vivant) setErreur('Connexion impossible. Réessaie.'); });
    return () => { vivant = false; };
  }, [token]);

  const inscrire = async (e) => {
    e.preventDefault();
    if (envoi) return;
    setEnvoi(true); setMsg('');
    try {
      const r = await fetch(`${API}/corporate/invitation/${encodeURIComponent(token)}/inscription`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...f, mois }),
      });
      const d = await r.json().catch(() => ({}));
      if (r.ok) setBillet(d); else setMsg(typeof d.detail === 'string' ? d.detail : 'Inscription impossible.');
    } catch (err) {
      setMsg('Connexion impossible. Réessaie.');
    } finally {
      setEnvoi(false);
    }
  };

  if (erreur) return <div style={page}><div style={boite}><h1 style={{ fontSize: 20 }}>Afroboost Corporate</h1><p data-testid="corp-public-erreur">{erreur}</p></div></div>;
  if (!info) return <div style={page} />;
  if (billet) {
    return (
      <div style={page}><div style={{ ...boite, textAlign: 'center' }} data-testid="corp-public-billet">
        <div style={{ color: 'var(--primary-color, #D91CD2)', display: 'inline-flex' }}><SvgIcon name="ticket" size={36} /></div>
        <h1 style={{ fontSize: 22, margin: '8px 0' }}>Ta place est réservée</h1>
        <p style={{ color: 'rgba(255,255,255,0.75)' }}>{billet.reservation?.courseName} — {libelleDate(billet.reservation?.datetime)}{billet.lieu ? ' · ' + billet.lieu : ''}</p>
        <p style={{ fontWeight: 700 }}>0 CHF · offert par {info.entreprise}</p>
        <div style={{ background: '#fff', padding: 12, borderRadius: 12, display: 'inline-block', margin: '8px 0' }}>
          <QRCodeSVG value={billet.reservation?.reservationCode || ''} size={180} level="M" />
        </div>
        <p style={{ fontFamily: 'monospace', fontSize: 18 }} data-testid="corp-public-code">{billet.reservation?.reservationCode}</p>
        <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: 13 }}>Présente ce QR code à l’entrée. Une confirmation t’est aussi envoyée par e-mail.</p>
      </div></div>
    );
  }
  const eds = info.editions || [];
  const choisie = eds.find(e => e.mois === mois);
  return (
    <div style={page}>
      <div style={boite}>
        <div style={{ color: 'var(--primary-color, #D91CD2)', fontWeight: 700, letterSpacing: '0.06em', fontSize: 12 }}>AFROBOOST CORPORATE</div>
        <h1 style={{ fontSize: 24, margin: '6px 0 4px' }} data-testid="corp-public-entreprise">{info.entreprise}</h1>
        <p style={{ color: 'rgba(255,255,255,0.7)', margin: '0 0 16px', fontSize: 14 }}>
          {info.places_par_edition} places offertes par édition. Une place par personne et par édition. Changements possibles jusqu’à {info.delai_modif_heures} h avant ; une place non utilisée est perdue.
        </p>
        <div role="radiogroup" aria-label="Édition" style={{ display: 'grid', gap: 8, marginBottom: 16 }}>
          {eds.map(e => {
            const dispo = e.statut === 'planifiee' && e.inscriptions_ouvertes && e.places_restantes > 0;
            return (
              <button key={e.mois} type="button" role="radio" aria-checked={mois === e.mois} disabled={!dispo}
                onClick={() => setMois(e.mois)} data-testid={'corp-edition-' + e.mois}
                style={{ textAlign: 'left', padding: '10px 12px', borderRadius: 12, cursor: dispo ? 'pointer' : 'default', color: '#fff',
                  background: mois === e.mois ? 'rgba(var(--primary-rgb, 217, 28, 210), 0.18)' : 'rgba(255,255,255,0.04)',
                  border: mois === e.mois ? '1px solid var(--primary-color, #D91CD2)' : '1px solid rgba(255,255,255,0.1)', opacity: dispo || e.statut !== 'planifiee' ? 1 : 0.6 }}>
                <div style={{ fontWeight: 600, textTransform: 'capitalize' }}>{libelleMois(e.mois)}</div>
                <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.65)' }}>
                  {e.statut === 'planifiee'
                    ? `${libelleDate(e.date)}${e.lieu ? ' · ' + e.lieu : ''} · ${e.inscriptions_ouvertes ? e.places_restantes + ' place(s) restante(s)' : 'inscriptions closes'}`
                    : 'À planifier — date et lieu bientôt confirmés'}
                </div>
              </button>
            );
          })}
        </div>
        {choisie && choisie.statut === 'planifiee' && choisie.inscriptions_ouvertes && choisie.places_restantes > 0 ? (
          <form onSubmit={inscrire} style={{ display: 'grid', gap: 10 }} data-testid="corp-public-form">
            <input style={champ} required placeholder="Prénom et nom" aria-label="Prénom et nom" value={f.nom} onChange={e => { const v = e.target.value; setF(p => ({ ...p, nom: v })); }} />
            <input style={champ} required type="email" placeholder="E-mail (personnel ou professionnel)" aria-label="E-mail" value={f.email} onChange={e => { const v = e.target.value; setF(p => ({ ...p, email: v })); }} />
            <input style={champ} placeholder="WhatsApp (facultatif)" aria-label="WhatsApp" value={f.whatsapp} onChange={e => { const v = e.target.value; setF(p => ({ ...p, whatsapp: v })); }} />
            <label style={{ display: 'flex', gap: 8, fontSize: 13, color: 'rgba(255,255,255,0.75)', alignItems: 'flex-start' }}>
              <input type="checkbox" checked={f.terms_accepted} onChange={e => { const v = e.target.checked; setF(p => ({ ...p, terms_accepted: v })); }} />
              J’accepte les conditions de participation.
            </label>
            <button type="submit" style={{ ...bouton, opacity: envoi ? 0.7 : 1 }} disabled={envoi} data-testid="corp-public-inscrire">Réserver ma place (0 CHF)</button>
            {msg && <p role="alert" style={{ margin: 0, color: 'rgba(255,255,255,0.9)' }} data-testid="corp-public-msg">{msg}</p>}
          </form>
        ) : (
          <p style={{ color: 'rgba(255,255,255,0.65)', fontSize: 14 }}>Aucune édition ouverte aux inscriptions pour le moment.</p>
        )}
      </div>
    </div>
  );
};

export default CorporateInvitation;
