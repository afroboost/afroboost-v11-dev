/**
 * V559 — ACCÈS « DEVENIR CRÉATEUR » / « DASHBOARD CRÉATEUR » DE L'ESPACE ABONNÉ.
 *
 * Même gabarit que la carte Parrainage (voisine), dans la même zone. Le libellé
 * suit le statut RENDU PAR LE SERVEUR (une lecture au montage, sans dépendance
 * objet) ; le contenu s'ouvre dans le tiroir commun du parrainage
 * (ParrainageDrawer) — l'espace créateur est le MÊME composant que côté coach.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import SvgIcon from '../SvgIcon';
import ParrainageDrawer from '../parrainage/ParrainageDrawer';
import EspaceCreateur from './EspaceCreateur';
import { lireCreateur, libelleAccesCreateur } from '../../utils/createur';
import '../parrainage/parrainage.css';

const PANEL = 'rgba(255,255,255,0.04)';
const BORDER = 'rgba(255,255,255,0.08)';

export default function CarteCreateur({ entetes, demandeOuverture }) {
  const [statut, setStatut] = useState('');
  const [ouvert, setOuvert] = useState(false);
  const declencheur = useRef(null);
  const entetesRef = useRef(entetes);
  entetesRef.current = entetes;

  useEffect(() => {
    let vivant = true;
    lireCreateur(entetesRef.current)
      .then((d) => { if (vivant && d) setStatut(String(d.statut || 'none')); })
      .catch(() => { /* carte discrète : le tiroir dira quoi faire */ });
    return () => { vivant = false; };
  }, []);

  // V560 : le menu rapide ouvre le tiroir (compteur = primitive, aucun objet en dépendance).
  useEffect(() => { if (demandeOuverture > 0) setOuvert(true); }, [demandeOuverture]);

  const surStatut = useCallback((s) => setStatut((prev) => (prev === s ? prev : String(s || 'none'))), []);
  const libelle = libelleAccesCreateur(statut);
  return (
    <>
      <section className="rounded-2xl p-5 cr-acces" data-testid="carte-createur"
               style={{ background: PANEL, border: `1px solid ${BORDER}` }}>
        <p className="text-white/60 text-xs uppercase tracking-wider mb-1">Programme Créateur</p>
        <h2 className="text-lg font-bold" style={{ margin: '0 0 6px' }}>
          {statut === 'approved' ? 'Suis tes revenus et tes filleuls.' : 'Recommande Afroboost et gagne une commission.'}
        </h2>
        <p className="text-sm" style={{ color: 'rgba(255,255,255,0.7)', margin: '0 0 10px' }}>
          {statut === 'pending'
            ? 'Ta demande est en cours d’examen.'
            : 'Une commission sur les achats payés réalisés grâce à ton lien personnel.'}
        </p>
        <button
          type="button"
          ref={declencheur}
          onClick={() => setOuvert(true)}
          aria-haspopup="dialog"
          data-testid="carte-createur-ouvrir"
          className="w-full py-2.5 rounded-xl text-sm font-semibold transition-transform active:scale-95 inline-flex items-center justify-center gap-2"
          style={{
            color: 'white', minHeight: 44, border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.45)',
            background: statut === 'approved'
              ? 'linear-gradient(135deg, var(--primary-color, #D91CD2), var(--secondary-color, #8b5cf6))'
              : 'transparent',
          }}
        >
          <SvgIcon name={statut === 'approved' ? 'barChart' : 'star'} size={16} /> {libelle}
        </button>
      </section>
      {ouvert ? (
        <div className="cp-root">
          <ParrainageDrawer titre={libelle} outil="createur" declencheur={declencheur.current} onClose={() => setOuvert(false)}>
            <EspaceCreateur entetes={entetesRef.current} onStatut={surStatut} />
          </ParrainageDrawer>
        </div>
      ) : null}
    </>
  );
}
