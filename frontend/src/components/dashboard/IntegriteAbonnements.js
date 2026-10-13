/**
 * V618 — « PLUSIEURS ABONNEMENTS ACTIFS DÉTECTÉS — À VÉRIFIER » (Codes promo, coach).
 *
 * Le serveur (résolveur canonique, `/api/abonnements/integrite`, LECTURE SEULE) dit quels clients
 * ont plusieurs abonnements actuels en même temps. Rien n'est choisi ni modifié automatiquement :
 * le coach tranche (par exemple en clôturant l'abonnement qui n'est plus l'actuel).
 * Aucun conflit -> rien n'est affiché. Couleurs : var(--primary-color) ; icônes SVG.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import SvgIcon from '../SvgIcon';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

export default function IntegriteAbonnements({ rafraichir }) {
  const [etat, setEtat] = useState(null);
  useEffect(() => {
    let vivant = true;
    axios.get(`${BACKEND_URL}/api/abonnements/integrite`, { timeout: 20000 })
      .then((r) => {
        if (!vivant || !r || !r.data) return;
        const n = Number(r.data.clients_conflit_multi_actifs || 0);
        const codes = (r.data.conflits || []).map((c) => (c.codes || []).join(' + '));
        const cle = `${n}|${codes.join(',')}`;
        setEtat((prev) => (prev && prev.cle === cle ? prev : { cle, n, codes }));
      })
      .catch(() => { /* facultatif : rien n'est affiché */ });
    return () => { vivant = false; };
  }, [rafraichir]);
  if (!etat || !etat.n) return null;
  return (
    <div role="status" data-testid="integrite-abonnements"
         style={{ margin: '0 0 14px', padding: '12px 14px', borderRadius: 12, background: 'rgba(251,191,36,0.10)',
           border: '1px solid rgba(251,191,36,0.45)', color: 'rgba(255,255,255,0.95)', fontSize: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 800 }}>
        <SvgIcon name="warning" size={16} /> Plusieurs abonnements actifs détectés — à vérifier ({etat.n})
      </div>
      <p style={{ margin: '6px 0 0', fontSize: 13, color: 'rgba(255,255,255,0.8)' }}>
        Pour ces clients, aucun abonnement n’est choisi automatiquement (place offerte d’événement refusée,
        e-mail d’accès avec un bouton par abonnement). Indique lequel est l’actuel en clôturant l’autre.
      </p>
      <ul style={{ margin: '6px 0 0', paddingLeft: 18, fontSize: 13 }}>
        {etat.codes.slice(0, 10).map((c) => <li key={c} data-testid="integrite-conflit">{c}</li>)}
      </ul>
    </div>
  );
}
