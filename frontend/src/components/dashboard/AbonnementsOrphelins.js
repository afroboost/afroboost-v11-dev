/**
 * V618i — « ABONNEMENTS SANS CODE » (Codes promo, coach).
 *
 * Avant V618i, « Supprimer » ne retirait que la FICHE du code : ses abonnements restaient actifs,
 * invisibles dans la liste mais encore utilisables. Ce bloc les montre (serveur : SON périmètre,
 * JWT strict) pour que le coach les supprime LUI-MÊME, avec la même confirmation que partout.
 * Rien n'est supprimé automatiquement. Replié par défaut ; masqué s'il n'y a rien.
 */
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import SvgIcon from '../SvgIcon';
import { useDialogueAbonnement, formaterJour } from './DialogueAbonnement';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

export default function AbonnementsOrphelins({ rafraichir }) {
  const [liste, setListe] = useState(null);
  const [tour, setTour] = useState(0);
  const [dialogueUi, demander, annoncer] = useDialogueAbonnement();

  useEffect(() => {
    let vivant = true;
    axios.get(`${BACKEND_URL}/api/abonnements/orphelins`, { timeout: 20000 })
      .then((r) => {
        if (!vivant) return;
        const l = (r && r.data && Array.isArray(r.data.orphelins)) ? r.data.orphelins : [];
        const cle = l.map((x) => x.id).join(',');
        // Aucune boucle : même contenu -> même objet (V305).
        setListe((prev) => (prev && prev.cle === cle ? prev : { cle, items: l }));
      })
      .catch(() => { /* facultatif : rien n'est affiché */ });
    return () => { vivant = false; };
  }, [rafraichir, tour]);

  const supprimer = useCallback(async (o) => {
    const choix = await demander({
      titre: 'Supprimer cet abonnement ?',
      lignes: [
        ['Client', o.email || '—'],
        ['Abonnement', o.abonnement || o.code || '—'],
        ['Séances restantes', o.seances_restantes == null ? '—' : String(o.seances_restantes)],
        ['Expiration', o.expiration ? formaterJour(o.expiration) : '—'],
      ],
      note: "Les paiements et réservations passés seront conservés pour l'historique, mais cet abonnement ne sera plus utilisable.",
      boutons: [
        { id: 'annuler', label: 'Annuler' },
        { id: 'supprimer', label: "Supprimer définitivement l'abonnement", danger: true },
      ],
    });
    if (choix !== 'supprimer') return;
    try {
      const r = await axios.delete(`${BACKEND_URL}/api/abonnements/${encodeURIComponent(o.id)}`);
      const d = (r && r.data) || {};
      annoncer(d.abonnement_actuel_apres
        ? `Abonnement supprimé. Abonnement actuel du client : ${d.abonnement_actuel_apres}.`
        : "Abonnement supprimé. Le client n'a plus d'abonnement actuel.");
    } catch (e) {
      const det = e && e.response && e.response.data && e.response.data.detail;
      annoncer(`Suppression impossible : ${typeof det === 'string' ? det : 'réessaie dans un instant.'}`);
    }
    setTour((t) => t + 1);   // relire le SERVEUR, jamais un simple masquage
  }, [demander, annoncer]);

  if (!liste || !liste.items.length) return dialogueUi;
  return (
    <>
      {dialogueUi}
      <details data-testid="abonnements-orphelins"
               style={{ margin: '0 0 14px', padding: '10px 14px', borderRadius: 12, background: 'rgba(255,255,255,0.04)',
                 border: '1px solid rgba(255,255,255,0.12)', color: 'rgba(255,255,255,0.92)', fontSize: 14 }}>
        <summary style={{ cursor: 'pointer', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
          <SvgIcon name="warning" size={16} /> Abonnements sans code ({liste.items.length})
        </summary>
        <p style={{ margin: '8px 0 10px', fontSize: 13, color: 'rgba(255,255,255,0.72)' }}>
          Leur code a été supprimé avant cette mise à jour, mais l’abonnement est resté actif. Supprime ceux qui ne
          doivent plus servir.
        </p>
        {liste.items.map((o) => (
          <div key={o.id} data-testid={`orphelin-${o.id}`}
               style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap',
                 padding: '8px 0', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 700 }}>{o.code}{o.courant ? ' · actuel' : ''}</div>
              <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.65)', wordBreak: 'break-word' }}>
                {o.email} · {o.seances_restantes ?? '?'} séance(s) · fin {o.expiration ? formaterJour(o.expiration) : '—'}
              </div>
            </div>
            <button type="button" data-testid={`supprimer-orphelin-${o.id}`} onClick={() => supprimer(o)}
                    style={{ padding: '6px 12px', borderRadius: 8, fontSize: 13, fontWeight: 700, cursor: 'pointer',
                      border: '1px solid rgba(239, 68, 68, 0.55)', background: 'rgba(239, 68, 68, 0.18)', color: 'rgba(255,255,255,0.95)' }}>
              Supprimer
            </button>
          </div>
        ))}
      </details>
    </>
  );
}
