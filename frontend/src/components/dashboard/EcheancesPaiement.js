/**
 * V617 — RAPPELS INTERNES « paiement restant à encaisser » (coach uniquement).
 *
 * Lit `GET /discount-codes/echeances` : abonnements ACTUELS dont il reste un
 * montant à encaisser et dont l'échéance tombe dans 7 jours ou est dépassée.
 * Aucun prélèvement : un paiement manuel (TWINT, espèces…) ne donne aucun mandat.
 *
 * V648 — le coach peut envoyer un rappel depuis une ligne, après aperçu et confirmation
 * (`RappelPaiement.js`). Rien ne part sans son clic, et le serveur revérifie tout.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { RappelPaiementDialog, RappelPaiementReglages, dateCH, LIBELLES_STATUT } from './RappelPaiement';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

function BoutonReglages({ onClick }) {
  return (
    <button type="button" onClick={onClick} data-testid="v648-ouvrir-reglages"
      className="text-xs text-white/60 hover:text-white underline">
      Rappel du deuxième paiement
    </button>
  );
}

function ActionRappel({ rappel, onOuvrir }) {
  const etat = rappel.rappel_envoi;
  if (!etat) return null;
  const dernier = etat.dernier && etat.dernier.echeance === rappel.prochaine_echeance ? etat.dernier : null;
  if (dernier?.statut === 'envoye') {
    return <span className="text-white/70" data-testid={`v648-envoye-${rappel.code}`}>Rappel envoyé le {dateCH(dernier.envoye_le)}</span>;
  }
  if (!etat.possible) {
    return <span className="text-white/50" data-testid={`v648-bloque-${rappel.code}`}>{etat.message}</span>;
  }
  return (
    <>
      {dernier && <span className="text-white/70" data-testid={`v648-statut-${rappel.code}`}>{LIBELLES_STATUT[dernier.statut] || dernier.statut}</span>}
      <button type="button" onClick={() => onOuvrir(rappel)} data-testid={`v648-rappel-${rappel.code}`}
        className="px-2.5 py-1 rounded-md font-semibold"
        style={{ border: '1px solid var(--primary-color, #D91CD2)', color: 'var(--primary-color, #D91CD2)' }}>
        {dernier?.statut === 'incertain' ? 'Vérifier le rappel' : 'Envoyer le rappel'}
      </button>
    </>
  );
}

export default function EcheancesPaiement({ rafraichir = 0 }) {
  const [rappels, setRappels] = useState([]);
  const [cible, setCible] = useState(null);
  const [reglagesOuverts, setReglagesOuverts] = useState(false);
  const [relecture, setRelecture] = useState(0);
  useEffect(() => {
    let vivant = true;
    axios.get(`${API}/discount-codes/echeances`)
      .then((r) => { if (vivant) setRappels(Array.isArray(r?.data?.rappels) ? r.data.rappels : []); })
      .catch(() => { if (vivant) setRappels([]); });
    return () => { vivant = false; };
  }, [rafraichir, relecture]);

  const fenetres = (
    <>
      <RappelPaiementDialog rappel={cible} ouvert={!!cible} onFermer={() => setCible(null)}
        onEnvoye={() => setRelecture((n) => n + 1)} />
      <RappelPaiementReglages ouvert={reglagesOuverts} onFermer={() => setReglagesOuverts(false)} />
    </>
  );

  if (!rappels.length) {
    return (
      <div className="mb-4 text-right" data-testid="v648-reglages-seuls">
        <BoutonReglages onClick={() => setReglagesOuverts(true)} />
        {fenetres}
      </div>
    );
  }
  return (
    <section data-testid="v617-echeances" className="mb-4 rounded-lg p-3"
      style={{ border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.35)', background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.08)' }}>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
        <p className="text-white text-sm font-semibold inline-flex items-center gap-2">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="9" /><polyline points="12 7 12 12 15 14" />
          </svg>
          Paiements à encaisser ({rappels.length})
        </p>
        <BoutonReglages onClick={() => setReglagesOuverts(true)} />
      </div>
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
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2">
              <ActionRappel rappel={r} onOuvrir={setCible} />
            </div>
          </li>
        ))}
      </ul>
      <p className="text-white/40 text-[11px] mt-2">
        Rien n'est prélevé. Aucun message ne part sans ta confirmation.
      </p>
      {fenetres}
    </section>
  );
}
