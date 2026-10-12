/**
 * V610m — « MES ÉVÉNEMENTS » DANS L'ESPACE : la réservation d'un événement (payé, ou
 * inscription gratuite) avec SON bouton « Inviter mes amis ».
 *
 * La liste vient du SERVEUR (POST /api/invitation/relais/mes-evenements, session d'espace
 * prouvée par le code e-mail) : seulement les événements À VENIR de la personne connectée,
 * avec son lien personnel. Les places OFFERTES (membres 8 mois) ont déjà leur carte
 * (EvenementsOfferts) : elles ne sont pas répétées ici. Rien sans session : aucun bloc.
 * Couleurs : var(--primary-color) ; icônes SVG.
 */
import React, { useEffect, useState } from 'react';
import SvgIcon from './SvgIcon';
import InviterMesAmis from './InviterMesAmis';
import { quandEvenement } from './EvenementsOfferts';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const rgbaP = (a) => `rgba(var(--primary-rgb, 217, 28, 210), ${a})`;

export default function MesEvenementsInvitation({ accessCode, jetonEspace, slug, offresDejaAffichees }) {
  const [liste, setListe] = useState([]);
  const [ouvert, setOuvert] = useState('');
  const code = String(accessCode || '');
  const jeton = String(jetonEspace || '');
  const membre = String(slug || '');
  useEffect(() => {
    if (!code || !jeton) return undefined;
    let vivant = true;
    fetch(`${BACKEND_URL}/api/invitation/relais/mes-evenements`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'x-espace-token': jeton },
      body: JSON.stringify({ code, slug: membre }),
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!vivant || !d || !Array.isArray(d.evenements)) return;
        const l = d.evenements.filter((e) => e && e.relais && e.relais.jeton);
        setListe((prev) => (JSON.stringify(prev) === JSON.stringify(l) ? prev : l));
      })
      .catch(() => { /* facultatif : rien n'est affiché */ });
    return () => { vivant = false; };
  }, [code, jeton, membre]);

  const dejaLa = new Set((Array.isArray(offresDejaAffichees) ? offresDejaAffichees : []).map((e) => String((e && e.offer_id) || '')));
  const visibles = liste.filter((e) => !dejaLa.has(String(e.offer_id || '')));
  if (!visibles.length) return null;
  return (
    <div data-testid="mes-evenements">
      {visibles.map((e) => (
        <div key={e.relais.jeton} data-testid={`mes-evenements-${e.relais.jeton}`} style={{ marginTop: '14px', padding: '14px', borderRadius: '16px',
          background: rgbaP(0.1), border: `1px solid ${rgbaP(0.35)}`, textAlign: 'left' }}>
          <div style={{ fontWeight: 800, fontSize: '15px', color: 'rgba(255,255,255,0.97)' }}>{e.titre}</div>
          <p style={{ margin: '4px 0 6px', fontSize: '13.5px', color: 'rgba(255,255,255,0.8)' }}>
            {quandEvenement(e.occurrence)}{e.lieu ? ` · ${e.lieu}` : ''}
          </p>
          <p data-testid="mes-evenements-confirme" style={{ margin: '0 0 10px', display: 'flex', alignItems: 'center', gap: 6, fontSize: '14px', fontWeight: 700, color: 'rgba(255,255,255,0.95)' }}>
            <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name="check" size={16} /></span> Ta place est réservée
          </p>
          {ouvert === e.relais.jeton ? (
            <InviterMesAmis relaisInitial={e.relais} />
          ) : (
            <button type="button" data-testid="mes-evenements-inviter" onClick={() => setOuvert(e.relais.jeton)}
                    style={{ width: '100%', minHeight: '48px', borderRadius: '12px', border: 'none', background: PRIMAIRE, color: 'rgba(255,255,255,1)',
                      fontWeight: 800, fontSize: '15px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '8px', cursor: 'pointer' }}>
              <SvgIcon name="send" size={18} /> Inviter mes amis
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
