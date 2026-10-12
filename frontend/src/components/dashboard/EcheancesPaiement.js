/**
 * V617 — RAPPELS INTERNES « paiement restant à encaisser » (coach uniquement).
 *
 * Lit `GET /discount-codes/echeances` : abonnements ACTUELS dont il reste un
 * montant à encaisser et dont l'échéance tombe dans 7 jours ou est dépassée.
 * Aucun e-mail, aucun WhatsApp, aucun prélèvement : un paiement manuel (TWINT,
 * espèces…) ne donne aucun mandat. C'est un aide-mémoire, rien de plus.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

const dateCH = (iso) => {
  const [a, m, j] = String(iso || '').slice(0, 10).split('-');
  return a && m && j ? `${j}.${m}.${a}` : iso || '';
};

export default function EcheancesPaiement({ rafraichir = 0 }) {
  const [rappels, setRappels] = useState([]);
  useEffect(() => {
    let vivant = true;
    axios.get(`${API}/discount-codes/echeances`)
      .then((r) => { if (vivant) setRappels(Array.isArray(r?.data?.rappels) ? r.data.rappels : []); })
      .catch(() => { if (vivant) setRappels([]); });
    return () => { vivant = false; };
  }, [rafraichir]);

  if (!rappels.length) return null;
  return (
    <section data-testid="v617-echeances" className="mb-4 rounded-lg p-3"
      style={{ border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.35)', background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.08)' }}>
      <p className="text-white text-sm font-semibold mb-2 inline-flex items-center gap-2">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="9" /><polyline points="12 7 12 12 15 14" />
        </svg>
        Paiements à encaisser ({rappels.length})
      </p>
      <ul className="space-y-2">
        {rappels.map((r) => (
          <li key={r.subscription_id || r.code} data-testid={`v617-rappel-${r.code}`}
            className="text-xs rounded-md px-3 py-2" style={{ background: 'rgba(0,0,0,0.35)' }}>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="text-white font-semibold">{r.nom}</span>
              {r.paiement_suivant && <span className="text-white/70">Paiement {r.paiement_suivant}</span>}
              <span style={{ color: 'var(--primary-color, #D91CD2)', fontWeight: 600 }}>
                {Number(r.reste_a_payer).toFixed(2)} {r.devise || 'CHF'} restant
              </span>
              <span className={r.en_retard ? 'text-red-400 font-semibold' : 'text-white/70'}>
                {r.en_retard ? 'En retard — échéance ' : 'Échéance : '}{dateCH(r.prochaine_echeance)}
              </span>
              <span className="text-white/40 font-mono">{r.code}</span>
            </div>
            {r.note_interne && <p className="text-white/50 mt-1">Note interne : {r.note_interne}</p>}
          </li>
        ))}
      </ul>
      <p className="text-white/40 text-[11px] mt-2">
        Rappel interne : aucun message n'est envoyé au client et aucun montant n'est prélevé automatiquement.
      </p>
    </section>
  );
}
