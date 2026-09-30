/**
 * V567 — LES INSCRITS D'UNE SESSION, VUS PAR LE COACH (dans le détail de SessionsModal).
 *
 * Lecture seule : `GET /api/coach/sessions/detail` (JWT coach signé, périmètre du
 * carnet de réservations). Rien n'est calculé ici qui ne vienne du serveur : places
 * réelles, capacité, essai, paiement. Le contact ne s'affiche qu'à la demande.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import SvgIcon from '../SvgIcon';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;
const ROSE = 'var(--primary-color, #D91CD2)';
const ROSE_RGB = 'var(--primary-rgb, 217, 28, 210)';

/** « AAAA-MM-JJTHH:MM » à l'heure LOCALE — la même clé que le serveur. */
export function cleOccurrence(courseId, quand) {
  if (!courseId || !(quand instanceof Date) || Number.isNaN(quand.getTime())) return '';
  const p = (n) => String(n).padStart(2, '0');
  return `${courseId}|${quand.getFullYear()}-${p(quand.getMonth() + 1)}-${p(quand.getDate())}T${p(quand.getHours())}:${p(quand.getMinutes())}`;
}

/** « 12 inscrits » · « 12 / 20 places » · « COMPLET » — jamais une capacité inventée. */
export function libelleInscrits(inscrits, capacite) {
  const n = Number(inscrits) || 0;
  const c = Number(capacite) || 0;
  if (c > 0 && n >= c) return 'Complet';
  if (c > 0) return `${n} / ${c} places`;
  return `${n} inscrit${n > 1 ? 's' : ''}`;
}

export function BadgeInscrits({ inscrits, capacite, testId }) {
  const complet = Number(capacite) > 0 && Number(inscrits) >= Number(capacite);
  return (
    <span data-testid={testId}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11, fontWeight: 700,
            padding: '3px 8px', borderRadius: 999, whiteSpace: 'nowrap', color: '#fff',
            background: complet ? ROSE : `rgba(${ROSE_RGB}, 0.18)`,
            border: `1px solid rgba(${ROSE_RGB}, 0.45)`, textTransform: complet ? 'uppercase' : 'none' }}>
      <SvgIcon name="users" size={12} /> {libelleInscrits(inscrits, capacite)}
    </span>
  );
}

const dateCourte = (iso) => {
  const d = new Date(iso);
  if (!iso || Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('fr-CH', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
};

function Participant({ p }) {
  const [contact, setContact] = useState(false);
  const aContact = !!(p.email || p.whatsapp);
  return (
    <li data-testid={`inscrit-${p.id}`}
        style={{ padding: '10px 12px', borderRadius: 12, background: 'rgba(255,255,255,0.04)',
          border: '1px solid rgba(255,255,255,0.08)', minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', minWidth: 0 }}>
        <span style={{ color: '#fff', fontWeight: 700, fontSize: 14, overflowWrap: 'anywhere' }}>{p.nom}</span>
        {p.essai ? (
          <span data-testid={`inscrit-essai-${p.id}`}
                style={{ fontSize: 10, fontWeight: 800, letterSpacing: '0.06em', padding: '2px 7px', borderRadius: 999,
                  background: `rgba(${ROSE_RGB}, 0.22)`, color: '#fff' }}>ESSAI</span>
        ) : null}
        <span style={{ marginLeft: 'auto', fontSize: 11, color: 'rgba(255,255,255,0.7)' }}>{p.statut}</span>
      </div>
      <div style={{ marginTop: 4, fontSize: 12, color: 'rgba(255,255,255,0.65)', overflowWrap: 'anywhere' }}
           data-testid={`inscrit-infos-${p.id}`}>
        {[p.places > 1 ? `${p.places} places` : '1 place', p.offre, p.forfait ? `(${p.forfait})` : '', p.paiement]
          .filter(Boolean).join(' · ')}
      </div>
      {Array.isArray(p.accompagnants) && p.accompagnants.length ? (
        <div style={{ marginTop: 2, fontSize: 12, color: 'rgba(255,255,255,0.55)' }}>Avec : {p.accompagnants.join(', ')}</div>
      ) : null}
      <div style={{ marginTop: 2, fontSize: 11, color: 'rgba(255,255,255,0.45)' }}>Réservé le {dateCourte(p.reserve_le)}</div>
      {aContact ? (
        contact ? (
          <div data-testid={`inscrit-contact-${p.id}`} style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 2, fontSize: 12 }}>
            {p.email ? <a href={`mailto:${p.email}`} style={{ color: ROSE, overflowWrap: 'anywhere' }}>{p.email}</a> : null}
            {p.whatsapp ? <a href={`https://wa.me/${String(p.whatsapp).replace(/[^\d]/g, '')}`} target="_blank" rel="noreferrer"
                             style={{ color: ROSE }}>{p.whatsapp}</a> : null}
          </div>
        ) : (
          <button type="button" onClick={() => setContact(true)} data-testid={`inscrit-voir-contact-${p.id}`}
                  style={{ marginTop: 6, background: 'none', border: 'none', padding: 0, color: ROSE, fontSize: 12,
                    cursor: 'pointer', minHeight: 32 }}>
            Voir le contact
          </button>
        )
      ) : null}
    </li>
  );
}

export default function InscritsSession({ courseId, quand }) {
  const cle = cleOccurrence(courseId, quand);
  const [etat, setEtat] = useState({ chargement: true, erreur: '', data: null });
  const [annulOuvert, setAnnulOuvert] = useState(false);

  useEffect(() => {
    if (!cle) return undefined;
    let vivant = true;
    setEtat({ chargement: true, erreur: '', data: null });
    axios.get(`${API}/coach/sessions/detail`, { params: { course_id: cle.split('|')[0], occurrence: cle.split('|')[1] } })
      .then((r) => { if (vivant) setEtat({ chargement: false, erreur: '', data: r.data }); })
      .catch((e) => {
        if (!vivant) return;
        const s = e && e.response && e.response.status;
        setEtat({ chargement: false, data: null,
          erreur: s === 403 || s === 401 ? 'Connecte-toi en coach pour voir les inscrits.' : 'Inscrits indisponibles pour le moment.' });
      });
    return () => { vivant = false; };
  }, [cle]);

  if (!cle) return null;
  if (etat.chargement) return <p data-testid="inscrits-chargement" style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12 }}>Chargement des inscrits…</p>;
  if (etat.erreur) return <p data-testid="inscrits-erreur" style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12 }}>{etat.erreur}</p>;
  const d = etat.data || {};
  const participants = Array.isArray(d.participants) ? d.participants : [];
  const annulations = Array.isArray(d.annulations) ? d.annulations : [];
  return (
    <section data-testid="inscrits-session" style={{ marginBottom: 16, minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
        <BadgeInscrits inscrits={d.inscrits} capacite={d.capacite} testId="inscrits-total" />
        {d.restantes != null && !d.complet ? (
          <span data-testid="inscrits-restantes" style={{ fontSize: 12, color: 'rgba(255,255,255,0.7)' }}>
            {d.restantes} place{d.restantes > 1 ? 's' : ''} restante{d.restantes > 1 ? 's' : ''}
          </span>
        ) : null}
      </div>
      {participants.length === 0 ? (
        <p data-testid="inscrits-vide" style={{ color: 'rgba(255,255,255,0.55)', fontSize: 13 }}>Aucun inscrit pour le moment.</p>
      ) : (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)', gap: 8 }}
            data-testid="inscrits-liste">
          {participants.map((p) => <Participant key={p.id || p.nom} p={p} />)}
        </ul>
      )}
      {d.tronque ? <p style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', marginTop: 6 }}>Liste limitée aux 50 premières réservations.</p> : null}
      {annulations.length ? (
        <div style={{ marginTop: 10 }}>
          <button type="button" onClick={() => setAnnulOuvert((x) => !x)} aria-expanded={annulOuvert}
                  data-testid="inscrits-annulations-toggle"
                  style={{ background: 'none', border: 'none', padding: 0, color: 'rgba(255,255,255,0.7)', fontSize: 12,
                    cursor: 'pointer', minHeight: 32, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <SvgIcon name={annulOuvert ? 'arrowUp' : 'arrowDown'} size={14} /> Annulations ({annulations.length})
          </button>
          {annulOuvert ? (
            <ul data-testid="inscrits-annulations" style={{ listStyle: 'none', margin: '6px 0 0', padding: 0, display: 'grid', gap: 4 }}>
              {annulations.map((a, i) => (
                <li key={i} style={{ fontSize: 12, color: 'rgba(255,255,255,0.55)' }}>
                  {a.nom} · {a.places > 1 ? `${a.places} places` : '1 place'} · annulé le {dateCourte(a.le)}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
