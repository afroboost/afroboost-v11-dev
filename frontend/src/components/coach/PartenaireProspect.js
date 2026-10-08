// PartenaireProspect.js — V592 (Partenaire B1) : « Activer comme partenaire »
// depuis la fiche d'un prospect.
//
// CE COMPOSANT NE FABRIQUE RIEN DE NOUVEAU. Le lien, le QR, son téléchargement
// et les statistiques sont ceux du système Partenaire existant
// (`LienPartenaire`, `partnerLink.js`, `/partners/{slug}/stats`). Il ne fait
// que deux appels : lire le partenaire lié, et l'activer.
//
// L'ACTIVATION EST IDEMPOTENTE CÔTÉ SERVEUR (index `prospect_id_unique`) : un
// double clic rend le même partenaire. Le bouton se désactive quand même
// pendant l'appel, par politesse.
//
// AUCUNE BOUCLE : l'effet dépend de deux CHAÎNES (`API`, `prospectId`), jamais
// d'un objet ; le parent n'est prévenu que si le pointeur change vraiment.
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { LienPartenaire } from './PartnerApplications';
import { p2bSuggererSlug, p2bSlugValide } from '../../utils/partnerLink';

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const RGB = 'var(--primary-rgb, 217, 28, 210)';

const detailErreur = (err, repli) => {
  const d = err && err.response && err.response.data && err.response.data.detail;
  return typeof d === 'string' && d ? d : repli;
};

export default function PartenaireProspect({ API, prospectId, organisation, onActive }) {
  const [etat, setEtat] = useState('chargement'); // chargement | aucun | actif | erreur
  const [partenaire, setPartenaire] = useState(null);
  const [slug, setSlug] = useState(() => p2bSuggererSlug(organisation));
  const [enCours, setEnCours] = useState(false);
  const [message, setMessage] = useState('');

  const lire = useCallback(async () => {
    setEtat('chargement');
    try {
      const { data } = await axios.get(
        `${API}/partner-prospects/${encodeURIComponent(prospectId)}/partner`);
      const p = data && data.partner;
      setPartenaire(p || null);
      setEtat(p && p.partner_slug ? 'actif' : 'aucun');
    } catch (e) {
      setEtat('erreur');
    }
  }, [API, prospectId]);

  useEffect(() => { lire(); }, [lire]);

  const activer = async () => {
    if (enCours) return;
    setMessage('');
    if (!p2bSlugValide(slug)) {
      setMessage('Identifiant invalide : 3 à 40 caractères, lettres minuscules, chiffres et « _ ».');
      return;
    }
    setEnCours(true);
    try {
      const { data } = await axios.post(
        `${API}/partner-prospects/${encodeURIComponent(prospectId)}/activate-partner`,
        { partner_slug: slug });
      const p = data && data.partner;
      if (p && p.partner_slug) {
        setPartenaire(p);
        setEtat('actif');
        if (onActive) onActive(p);
      }
    } catch (err) {
      setMessage(detailErreur(err, "L'activation n'a pas abouti. Rien n'a été créé, réessayez."));
    } finally {
      setEnCours(false);
    }
  };

  if (etat === 'chargement') {
    return <div style={{ fontSize: '12px', opacity: 0.6 }}>Chargement…</div>;
  }
  if (etat === 'erreur') {
    return (
      <div data-testid="partenaire-erreur" style={{ fontSize: '12px', opacity: 0.8 }}>
        Statut Partenaire momentanément indisponible.{' '}
        <button type="button" onClick={lire}
                style={{ background: 'none', border: 'none', color: PRIMAIRE,
                         cursor: 'pointer', fontSize: '12px', padding: 0 }}>
          Réessayer
        </button>
      </div>
    );
  }

  if (etat === 'actif' && partenaire) {
    return (
      <div data-testid="partenaire-actif">
        <span style={{
          display: 'inline-flex', alignItems: 'center', gap: '6px',
          padding: '4px 10px', borderRadius: '999px', fontSize: '11px', fontWeight: 800,
          letterSpacing: '0.04em', color: '#fff',
          background: `rgba(${RGB}, 0.22)`, border: `1px solid rgba(${RGB}, 0.55)`,
        }}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polyline points="20 6 9 17 4 12" />
          </svg>
          PARTENAIRE ACTIF
        </span>
        <LienPartenaire slug={partenaire.partner_slug} API={API} />
      </div>
    );
  }

  return (
    <div data-testid="partenaire-a-activer">
      <label style={{ display: 'block', fontSize: '11px', opacity: 0.7, marginBottom: '4px' }}>
        Identifiant du lien (modifiable)
      </label>
      <input
        data-testid="partenaire-slug"
        value={slug}
        onChange={(e) => setSlug(e.target.value.trim().toLowerCase())}
        maxLength={40}
        style={{
          width: '100%', boxSizing: 'border-box', padding: '8px 10px', borderRadius: '8px',
          background: 'rgba(255,255,255,0.06)', border: `1px solid rgba(${RGB}, 0.35)`,
          color: '#fff', fontFamily: 'monospace', fontSize: '13px', marginBottom: '8px',
        }}
      />
      <button
        type="button"
        data-testid="activer-partenaire"
        onClick={activer}
        disabled={enCours}
        style={{
          width: '100%', padding: '10px', borderRadius: '8px', border: 'none',
          background: PRIMAIRE, color: '#fff', fontWeight: 700, fontSize: '13px',
          cursor: enCours ? 'default' : 'pointer', opacity: enCours ? 0.6 : 1,
        }}
      >
        {enCours ? 'Activation…' : 'Activer comme partenaire'}
      </button>
      {message && (
        <div data-testid="partenaire-message"
             style={{ marginTop: '6px', fontSize: '12px', color: '#ff8a80' }}>
          {message}
        </div>
      )}
    </div>
  );
}
