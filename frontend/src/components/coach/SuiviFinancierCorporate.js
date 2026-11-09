// V657 : bandeau « Suivi financier » (lecture seule) d'un prospect entreprise — contrats + factures
// lus via /api/corporate/prospects/<id>/suivi-financier (super-admin). Rien n'est copié sur la fiche.
import React, { useEffect, useState } from 'react';
import { appel, chf, STATUT_CONTRAT, STATUT_FACTURE, pastille } from '../dashboard/corporateApi';

export default function SuiviFinancierCorporate({ prospectId }) {
  const [contrats, setContrats] = useState(null);
  useEffect(() => {
    let vivant = true;
    if (!prospectId) return undefined;
    appel(`/corporate/prospects/${encodeURIComponent(prospectId)}/suivi-financier`)
      .then(r => { if (vivant) setContrats(r.ok ? (r.data.contrats || []) : []); });
    return () => { vivant = false; };
  }, [prospectId]);
  if (!contrats || contrats.length === 0) return null;
  return (
    <div data-testid="suivi-financier-corporate" style={{ display: 'grid', gap: 6, fontSize: 12 }}>
      {contrats.map(c => (
        <div key={c.id} style={{ padding: '8px 10px', borderRadius: 10, border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.25)' }}>
          <div style={{ fontWeight: 700 }}>
            Corporate <span style={pastille(c.statut === 'signe' ? 'ok' : c.statut === 'devis' ? 'alerte' : '')}>{STATUT_CONTRAT[c.statut]}</span>
            {' '}· {c.places} places × {c.duree_mois} mois · {chf(c.prix_mensuel)}/mois
          </div>
          <div style={{ opacity: 0.8 }}>Facturé {chf(c.facture)} · payé {chf(c.paye)} · dû {chf(c.du)}</div>
          <div style={{ opacity: 0.8 }}>
            {(c.devis || []).map(d => d.numero).join(', ')}
            {(c.factures || []).map(f => ` · ${f.numero} (${STATUT_FACTURE[f.statut] || f.statut})`).join('')}
          </div>
        </div>
      ))}
    </div>
  );
}
