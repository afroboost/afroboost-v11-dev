/**
 * V610o — DASHBOARD COACH : « AMBASSADEURS » (Invitation & Parrainage).
 *
 * Section REPLIÉE par défaut (design épuré). Une liste courte : prénom, contact (de SA
 * réservation), partages, amis convertis, Boosts, prochain palier, récompenses, VIP ;
 * une recherche ; le détail au clic (filleuls : événement, date, statut, montant, Boost,
 * annulé/remboursé) ; marquer une récompense remise / un Pass Ami utilisé ; régler les
 * paliers. Tout vient du serveur (JWT coach : SES invitations seulement).
 * Couleurs : var(--primary-color) ; icônes SVG.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import SvgIcon from '../SvgIcon';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const rgbaP = (a) => `rgba(var(--primary-rgb, 217, 28, 210), ${a})`;
const pastille = (fond) => ({ fontSize: 12, padding: '3px 9px', borderRadius: 999, background: fond, border: `1px solid ${rgbaP(0.35)}`, whiteSpace: 'nowrap' });
const btn = (principal) => ({ minHeight: 40, padding: '0 14px', borderRadius: 10, cursor: 'pointer', fontWeight: 700, fontSize: 13.5,
  border: principal ? 'none' : `1px solid ${rgbaP(0.4)}`, background: principal ? PRIMAIRE : 'rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.95)' });

function dateCourte(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ''));
  return m ? `${m[3]}.${m[2]}.${m[1]}` : '';
}

/** Actions possibles sur une récompense (le serveur garde la règle). */
export function actionsRecompense(r) {
  if (!r) return [];
  if (r.palier === 'pass_ami') return [r.etat === 'utilise' ? { etat: 'disponible', libelle: 'Remettre disponible' } : { etat: 'utilise', libelle: 'Marquer utilisé' }];
  if (r.palier === 'recompense') return [r.etat === 'remise' ? { etat: 'a_remettre', libelle: 'Remettre « à remettre »' } : { etat: 'remise', libelle: 'Marquer remise' }];
  return [];
}

function Recompenses({ liste, onChanger }) {
  if (!liste || !liste.length) return <span style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.55)' }}>Aucun palier débloqué</span>;
  return (
    <div style={{ display: 'grid', gap: 6 }}>
      {liste.map((r) => (
        <div key={r.id || r.palier} data-testid={`amb-recompense-${r.palier}`} style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={pastille(rgbaP(0.14))}>{r.libelle} · {r.etat_libelle}</span>
          {r.a_verifier ? <span data-testid="amb-a-verifier" style={pastille('rgba(255,170,90,0.18)')}>À vérifier</span> : null}
          {onChanger ? actionsRecompense(r).map((a) => (
            <button key={a.etat} type="button" style={btn(false)} data-testid={`amb-action-${r.palier}-${a.etat}`} onClick={() => onChanger(r, a.etat)}>{a.libelle}</button>
          )) : null}
        </div>
      ))}
    </div>
  );
}

function Detail({ ligne, onFermer, onRecharger }) {
  const [d, setD] = useState(null);
  const [erreur, setErreur] = useState('');
  useEffect(() => {
    let vivant = true;
    axios.get(`${BACKEND_URL}/api/ambassadeur/coach/${encodeURIComponent(ligne.id)}`, { timeout: 20000 })
      .then((r) => { if (vivant) setD(r.data); })
      .catch(() => { if (vivant) setErreur('Détail indisponible pour le moment.'); });
    return () => { vivant = false; };
  }, [ligne.id]);
  const changer = (r, etat) => {
    axios.post(`${BACKEND_URL}/api/ambassadeur/coach/recompense`, { id: r.id, etat }, { timeout: 20000 })
      .then((x) => {
        setD((prev) => Object.assign({}, prev, { recompenses: prev.recompenses.map((y) => (y.id === r.id ? Object.assign({}, y, x.data) : y)) }));
        onRecharger();
      })
      .catch(() => setErreur('Changement impossible.'));
  };
  return (
    <div role="dialog" aria-label={`Ambassadeur ${ligne.prenom}`} data-testid="amb-detail"
         style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(0,0,0,0.6)', display: 'flex', justifyContent: 'center', alignItems: 'flex-end' }}
         onClick={(e) => { if (e.target === e.currentTarget) onFermer(); }}>
      <div style={{ width: '100%', maxWidth: 560, maxHeight: '88vh', overflowY: 'auto', background: 'rgb(18,10,24)', borderRadius: '18px 18px 0 0',
        padding: 16, boxSizing: 'border-box', color: 'rgba(255,255,255,0.95)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <strong style={{ fontSize: 17 }}>{ligne.prenom || 'Ambassadeur'}</strong>
          {ligne.progression && ligne.progression.vip ? <span style={pastille(PRIMAIRE)}>Ambassadeur VIP</span> : null}
          <button type="button" onClick={onFermer} aria-label="Fermer" data-testid="amb-detail-fermer"
                  style={{ marginLeft: 'auto', width: 40, height: 40, borderRadius: 999, border: 'none', background: 'rgba(255,255,255,0.08)', color: 'inherit', cursor: 'pointer' }}>
            <SvgIcon name="x" size={18} />
          </button>
        </div>
        {erreur ? <p role="alert" style={{ color: 'rgba(255,190,180,1)' }}>{erreur}</p> : null}
        {!d ? <p style={{ color: 'rgba(255,255,255,0.6)' }}>Chargement…</p> : (
          <>
            <h3 style={{ fontSize: 13, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'rgba(255,255,255,0.6)', margin: '6px 0' }}>Récompenses</h3>
            <Recompenses liste={d.recompenses} onChanger={changer} />
            <h3 style={{ fontSize: 13, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'rgba(255,255,255,0.6)', margin: '14px 0 6px' }}>Invités</h3>
            {!d.filleuls.length ? <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: 14 }}>Aucun ami n’a encore réservé par son lien.</p> : null}
            <div style={{ display: 'grid', gap: 8 }}>
              {d.filleuls.map((f, i) => (
                <div key={i} data-testid="amb-filleul" style={{ padding: 10, borderRadius: 12, background: 'rgba(255,255,255,0.05)', fontSize: 13.5 }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <strong>{f.prenom || 'Ami'}</strong>
                    <span style={{ color: 'rgba(255,255,255,0.7)' }}>{f.evenement}{f.date ? ` · ${dateCourte(f.date)}` : ''}</span>
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
                    <span style={pastille('rgba(255,255,255,0.06)')}>{f.reservation_confirmee ? 'Réservation confirmée' : 'Réservation introuvable'}</span>
                    {f.montant ? <span style={pastille('rgba(255,255,255,0.06)')}>{`${f.montant} CHF`}</span> : null}
                    <span style={pastille(f.boost ? rgbaP(0.2) : 'rgba(255,255,255,0.06)')}>{f.boost ? 'Boost attribué' : 'Pas de Boost'}</span>
                    {f.annule_ou_rembourse ? <span style={pastille('rgba(255,170,90,0.18)')}>{f.raison === 'remboursement_stripe' ? 'Remboursé' : 'Annulé'}</span> : null}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Reglages({ onFermer }) {
  const [cfg, setCfg] = useState(null);
  const [msg, setMsg] = useState('');
  const [activites, setActivites] = useState([]);
  useEffect(() => {
    axios.get(`${BACKEND_URL}/api/ambassadeur/coach-config`, { timeout: 20000 }).then((r) => setCfg(r.data)).catch(() => setMsg('Réglages indisponibles.'));
    // Les activités compatibles du Pass Ami : les invitations ACTIVES du coach (jamais toutes d'office).
    axios.get(`${BACKEND_URL}/api/referral/campaigns`, { timeout: 20000 })
      .then((r) => setActivites(((r && r.data && r.data.items) || []).filter((x) => x && x.status === 'active').map((x) => ({ id: x.id, titre: x.title || 'Invitation' }))))
      .catch(() => {});
  }, []);
  const basculerActivite = (id) => setCfg((x) => {
    const l = (x.pass_ami && x.pass_ami.activites) || [];
    return Object.assign({}, x, { pass_ami: Object.assign({}, x.pass_ami, { activites: l.indexOf(id) >= 0 ? l.filter((a) => a !== id) : l.concat([id]) }) });
  });
  if (!cfg) return <p style={{ fontSize: 13.5, color: 'rgba(255,255,255,0.6)' }}>{msg || 'Chargement…'}</p>;
  const majPalier = (cle, champ, v) => setCfg((p) => Object.assign({}, p, { paliers: p.paliers.map((x) => (x.cle === cle ? Object.assign({}, x, { [champ]: v }) : x)) }));
  const enregistrer = () => {
    setMsg('');
    axios.put(`${BACKEND_URL}/api/ambassadeur/coach-config`, { paliers: cfg.paliers.map((p) => ({ cle: p.cle, seuil: Number(p.seuil), libelle: p.libelle })),
      message_places: cfg.message_places, pass_ami: cfg.pass_ami }, { timeout: 20000 })
      .then((r) => { setCfg(r.data); setMsg('Réglages enregistrés.'); })
      .catch((e) => setMsg((e && e.response && e.response.data && e.response.data.detail) || 'Enregistrement impossible.'));
  };
  const champ = { minHeight: 40, borderRadius: 10, padding: '0 10px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', color: 'inherit', boxSizing: 'border-box' };
  return (
    <div data-testid="amb-reglages" style={{ display: 'grid', gap: 10, padding: 12, borderRadius: 12, background: 'rgba(255,255,255,0.04)' }}>
      {cfg.paliers.map((p) => (
        <div key={p.cle} style={{ display: 'grid', gridTemplateColumns: '84px minmax(0, 1fr)', gap: 8, alignItems: 'center' }}>
          <input type="number" min={1} aria-label={`Seuil ${p.libelle}`} value={p.seuil} onChange={(e) => majPalier(p.cle, 'seuil', e.target.value)} style={champ} data-testid={`amb-seuil-${p.cle}`} />
          <input aria-label={`Libellé ${p.cle}`} value={p.libelle} maxLength={40} onChange={(e) => majPalier(p.cle, 'libelle', e.target.value)} style={champ} />
        </div>
      ))}
      <label style={{ fontSize: 13, color: 'rgba(255,255,255,0.7)' }}>Message des invitations (marketing, aucune limite technique)
        <input value={cfg.message_places} maxLength={30} onChange={(e) => setCfg((x) => Object.assign({}, x, { message_places: e.target.value }))} style={Object.assign({}, champ, { width: '100%', marginTop: 4 })} data-testid="amb-message-places" />
      </label>
      <fieldset style={{ border: 'none', margin: 0, padding: 0 }} data-testid="amb-pass-activites">
        <legend style={{ fontSize: 13, color: 'rgba(255,255,255,0.7)', marginBottom: 4 }}>Pass Ami : activités compatibles</legend>
        {!activites.length ? <span style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.55)' }}>Aucune invitation active.</span> : null}
        {activites.map((a) => (
          <label key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 8, minHeight: 36, fontSize: 13.5 }}>
            <input type="checkbox" checked={((cfg.pass_ami && cfg.pass_ami.activites) || []).indexOf(a.id) >= 0} onChange={() => basculerActivite(a.id)} />
            <span style={{ overflowWrap: 'anywhere' }}>{a.titre}</span>
          </label>
        ))}
      </fieldset>
      <label style={{ fontSize: 13, color: 'rgba(255,255,255,0.7)' }}>Pass Ami : expiration (facultatif)
        <input type="date" value={(cfg.pass_ami && cfg.pass_ami.expire_le) || ''} onChange={(e) => setCfg((x) => Object.assign({}, x, { pass_ami: Object.assign({}, x.pass_ami, { expire_le: e.target.value || null }) }))}
               style={Object.assign({}, champ, { width: '100%', marginTop: 4 })} />
      </label>
      <p style={{ margin: 0, fontSize: 12.5, color: 'rgba(255,255,255,0.6)' }}>Avantage filleul : désactivé (préparé pour plus tard). Aucune remise n’est appliquée.</p>
      {msg ? <p role="status" style={{ margin: 0, fontSize: 13 }}>{msg}</p> : null}
      <div style={{ display: 'flex', gap: 8 }}>
        <button type="button" style={btn(true)} onClick={enregistrer} data-testid="amb-reglages-enregistrer">Enregistrer</button>
        <button type="button" style={btn(false)} onClick={onFermer}>Fermer</button>
      </div>
    </div>
  );
}

export default function AmbassadeursCoach() {
  const [ouvert, setOuvert] = useState(false);
  const [donnees, setDonnees] = useState(null);
  const [q, setQ] = useState('');
  const [erreur, setErreur] = useState('');
  const [detail, setDetail] = useState(null);
  const [reglages, setReglages] = useState(false);
  const [tour, setTour] = useState(0);
  useEffect(() => {
    if (!ouvert) return undefined;
    let vivant = true;
    const t = setTimeout(() => {
      axios.get(`${BACKEND_URL}/api/ambassadeur/coach`, { params: q.trim() ? { q: q.trim() } : {}, timeout: 20000 })
        .then((r) => { if (vivant) { setDonnees(r.data); setErreur(''); } })
        .catch(() => { if (vivant) setErreur('Liste indisponible pour le moment.'); });
    }, q ? 300 : 0);
    return () => { vivant = false; clearTimeout(t); };
  }, [ouvert, q, tour]);
  const liste = (donnees && donnees.ambassadeurs) || [];
  return (
    <section data-testid="ambassadeurs-coach" style={{ marginTop: 16, borderRadius: 16, border: `1px solid ${rgbaP(0.3)}`, background: 'rgba(255,255,255,0.03)' }}>
      <button type="button" onClick={() => setOuvert((v) => !v)} aria-expanded={ouvert} data-testid="ambassadeurs-ouvrir"
              style={{ width: '100%', minHeight: 52, padding: '0 14px', display: 'flex', alignItems: 'center', gap: 8, background: 'none', border: 'none', color: 'rgba(255,255,255,0.96)', cursor: 'pointer', fontWeight: 800, fontSize: 15 }}>
        <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name="fire" size={18} /></span> Ambassadeurs
        {donnees ? <span style={Object.assign(pastille(rgbaP(0.14)), { marginLeft: 6 })}>{donnees.total}</span> : null}
        <span style={{ marginLeft: 'auto', display: 'inline-flex' }}><SvgIcon name={ouvert ? 'arrowUp' : 'arrowDown'} size={16} /></span>
      </button>
      {ouvert ? (
        <div style={{ padding: '0 14px 14px' }}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher (prénom, e-mail, téléphone)" aria-label="Rechercher un ambassadeur"
                   data-testid="ambassadeurs-recherche"
                   style={{ flex: 1, minWidth: 0, minHeight: 42, borderRadius: 10, padding: '0 12px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', color: 'inherit' }} />
            <button type="button" style={btn(false)} onClick={() => setReglages((v) => !v)} data-testid="ambassadeurs-reglages" aria-label="Réglages des paliers">
              <SvgIcon name="settings" size={16} />
            </button>
          </div>
          {reglages ? <Reglages onFermer={() => { setReglages(false); setTour((n) => n + 1); }} /> : null}
          {erreur ? <p role="alert" style={{ color: 'rgba(255,190,180,1)', fontSize: 14 }}>{erreur}</p> : null}
          {donnees && !liste.length ? (
            <p data-testid="ambassadeurs-vide" style={{ color: 'rgba(255,255,255,0.65)', fontSize: 14, margin: '6px 0 0' }}>
              Aucun ambassadeur pour le moment : chaque participant confirmé reçoit son lien personnel.
            </p>
          ) : null}
          <div style={{ display: 'grid', gap: 8 }}>
            {liste.map((l) => (
              <button key={l.id} type="button" onClick={() => setDetail(l)} data-testid={`ambassadeur-${l.id}`}
                      style={{ textAlign: 'left', padding: 12, borderRadius: 12, background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)', color: 'inherit', cursor: 'pointer' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <strong>{l.prenom || 'Ambassadeur'}</strong>
                  {l.contact && (l.contact.email || l.contact.whatsapp) ? (
                    <span style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.65)', overflowWrap: 'anywhere' }}>{[l.contact.email, l.contact.whatsapp].filter(Boolean).join(' · ')}</span>
                  ) : null}
                  {l.progression && l.progression.vip ? <span style={pastille(PRIMAIRE)}>VIP</span> : null}
                  {(l.recompenses || []).some((r) => r.a_verifier) ? <span style={pastille('rgba(255,170,90,0.18)')}>À vérifier</span> : null}
                </div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8, fontSize: 12.5 }}>
                  <span style={pastille(rgbaP(0.2))} data-testid="ambassadeur-boosts">{l.convertis} Boost{l.convertis > 1 ? 's' : ''}</span>
                  <span style={pastille('rgba(255,255,255,0.06)')}>{l.partages} partage{l.partages > 1 ? 's' : ''}</span>
                  {l.progression && l.progression.prochain
                    ? <span style={pastille('rgba(255,255,255,0.06)')}>{`Encore ${l.progression.prochain.restant} → ${l.progression.prochain.libelle}`}</span> : null}
                  {(l.recompenses || []).map((r) => <span key={r.palier} style={pastille(rgbaP(0.12))}>{r.libelle} · {r.etat_libelle}</span>)}
                </div>
              </button>
            ))}
          </div>
        </div>
      ) : null}
      {detail ? <Detail ligne={detail} onFermer={() => setDetail(null)} onRecharger={() => setTour((n) => n + 1)} /> : null}
    </section>
  );
}
