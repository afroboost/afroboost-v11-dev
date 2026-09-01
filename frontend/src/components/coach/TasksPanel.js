/**
 * TasksPanel.js — LES TÂCHES AFROBOOST (CAL-2).
 *
 * CE N'EST PAS UN SECOND CALENDRIER, et ce n'est pas non plus un second
 * stockage : une tâche est un événement de `calendar_events` portant
 * `event_type: "task"`. La cocher ici la coche dans la grille, sans aucune
 * synchronisation — c'est le même document.
 *
 * POURQUOI UNE LISTE À CÔTÉ DE LA GRILLE. Une tâche EN RETARD est par
 * définition dans le passé : la grille du calendrier, bornée à la période
 * affichée, la masquerait précisément le jour où elle compte le plus. La liste
 * répond donc à la question que la grille ne peut pas poser — « qu'est-ce qui
 * traîne ? » — et rien de plus.
 *
 * COULEURS : `var(--primary-color)` / `var(--primary-rgb)` uniquement. Les
 * seules valeurs fixes sont sémantiques (retard, terminé) et doivent rester
 * lisibles quelle que soit la couleur du coach.
 *
 * AUCUN GOOGLE.
 */
import React, { useState, useCallback } from 'react';
import axios from 'axios';
import SvgIcon from '../SvgIcon';

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const RGB = 'var(--primary-rgb, 217, 28, 210)';

const PILES = [
  { cle: '', libelle: 'Toutes' },
  { cle: 'aujourdhui', libelle: "Aujourd'hui" },
  { cle: 'en_retard', libelle: 'En retard' },
  { cle: 'a_venir', libelle: 'À venir' },
  { cle: 'terminees', libelle: 'Terminées' },
];

/* Le retard est la SEULE information qu'on souligne par une couleur fixe :
   elle doit alerter quelle que soit la marque du coach. */
const TEINTE_PILE = {
  en_retard: 'rgba(239,68,68,0.9)',
  terminees: 'rgba(148,163,184,0.7)',
};

const PRIORITES = [
  { cle: 'basse', libelle: 'Basse' },
  { cle: 'normale', libelle: 'Normale' },
  { cle: 'haute', libelle: 'Haute' },
];

const cle2 = (n) => String(n).padStart(2, '0');
const lisible = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return '';
  return `${cle2(d.getDate())}/${cle2(d.getMonth() + 1)} ${cle2(d.getHours())}:${cle2(d.getMinutes())}`;
};
/* `datetime-local` ne comprend ni le fuseau ni les secondes. */
const pourChamp = (d) =>
  `${d.getFullYear()}-${cle2(d.getMonth() + 1)}-${cle2(d.getDate())}T${cle2(d.getHours())}:${cle2(d.getMinutes())}`;

export default function TasksPanel({ API = '', taches = [], compteurs = {},
                                     pile = '', onChangerPile, onRecharger }) {
  const [ouvertCreation, setOuvertCreation] = useState(false);
  const [titre, setTitre] = useState('');
  const [echeance, setEcheance] = useState('');
  const [priorite, setPriorite] = useState('normale');
  const [enCours, setEnCours] = useState(false);
  const [message, setMessage] = useState(null);

  const base = `${API}/api`;

  const ouvrir = useCallback(() => {
    const dans1h = new Date(Date.now() + 60 * 60 * 1000);
    setEcheance(pourChamp(dans1h));
    setTitre(''); setPriorite('normale'); setMessage(null);
    setOuvertCreation(true);
  }, []);

  const creer = useCallback(async () => {
    if (!titre.trim() || !echeance) {
      setMessage({ type: 'erreur', texte: 'Un titre et une échéance sont nécessaires.' });
      return;
    }
    setEnCours(true); setMessage(null);
    try {
      await axios.post(`${base}/calendar-events`, {
        title: titre.trim(),
        starts_at: new Date(echeance).toISOString(),
        event_type: 'task',
        priority: priorite,
      });
      setOuvertCreation(false); setTitre('');
      onRecharger?.();
    } catch (e) {
      setMessage({ type: 'erreur', texte: 'Création refusée par le serveur.' });
    } finally {
      setEnCours(false);
    }
  }, [base, titre, echeance, priorite, onRecharger]);

  /* Terminer et rouvrir passent par la MÊME route et le MÊME champ : le statut.
     Une route « terminer » dédiée aurait fini par diverger de celle-ci. */
  const changerStatut = useCallback(async (tache, statut) => {
    setEnCours(true); setMessage(null);
    try {
      await axios.patch(`${base}/calendar-events/${tache.id}`, { status: statut });
      onRecharger?.();
    } catch (e) {
      setMessage({ type: 'erreur', texte: 'Modification refusée par le serveur.' });
    } finally {
      setEnCours(false);
    }
  }, [base, onRecharger]);

  const bouton = {
    background: `rgba(${RGB}, 0.18)`, border: `1px solid rgba(${RGB}, 0.35)`,
    color: '#fff', borderRadius: '8px', padding: '4px 10px', fontSize: '11px',
    cursor: 'pointer', flexShrink: 0,
  };
  const champ = {
    background: 'rgba(255,255,255,0.06)', border: `1px solid rgba(${RGB}, 0.3)`,
    color: '#fff', borderRadius: '8px', padding: '6px 8px', fontSize: '12px',
    boxSizing: 'border-box',
  };

  return (
    <div data-testid="panneau-taches"
         style={{ marginBottom: '16px', padding: '10px 12px', borderRadius: '12px',
                  background: 'rgba(255,255,255,0.02)',
                  border: `1px solid rgba(${RGB}, 0.2)`,
                  boxSizing: 'border-box', width: '100%', maxWidth: '100%',
                  overflow: 'hidden' }}>

      <div style={{ display: 'flex', alignItems: 'center', gap: '8px',
                    flexWrap: 'wrap', marginBottom: '8px' }}>
        <span style={{ fontSize: '13px', fontWeight: 700, color: '#fff',
                       display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
          <SvgIcon name="clipboard" size={14} /> Tâches
        </span>
        {(compteurs.en_retard || 0) > 0 && (
          <span data-testid="compteur-retard"
                style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '999px',
                         background: TEINTE_PILE.en_retard, fontWeight: 600, color: '#fff' }}>
            {compteurs.en_retard} en retard
          </span>
        )}
        <span style={{ flex: '1 1 auto' }} />
        <button type="button" data-testid="nouvelle-tache" onClick={ouvrir}
                style={{ ...bouton, background: PRIMAIRE, border: 'none', fontWeight: 600 }}>
          + Tâche
        </button>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '8px' }}>
        {PILES.map((p) => (
          <button key={p.cle || 'toutes'} type="button" data-testid={`pile-${p.cle || 'toutes'}`}
                  onClick={() => onChangerPile?.(p.cle)}
                  style={{ ...bouton,
                           background: pile === p.cle ? PRIMAIRE : `rgba(${RGB}, 0.12)`,
                           fontWeight: pile === p.cle ? 700 : 400 }}>
            {p.libelle}{p.cle && compteurs[p.cle] ? ` (${compteurs[p.cle]})` : ''}
          </button>
        ))}
      </div>

      {ouvertCreation && (
        <div data-testid="formulaire-tache"
             style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '10px',
                      padding: '8px', borderRadius: '8px', background: `rgba(${RGB}, 0.08)` }}>
          <input data-testid="tache-titre" value={titre} placeholder="Que faut-il faire ?"
                 onChange={(e) => setTitre(e.target.value)}
                 style={{ ...champ, flex: '2 1 200px' }} />
          <input data-testid="tache-echeance" type="datetime-local" value={echeance}
                 onChange={(e) => setEcheance(e.target.value)}
                 style={{ ...champ, flex: '1 1 160px' }} />
          <select data-testid="tache-priorite" value={priorite}
                  onChange={(e) => setPriorite(e.target.value)}
                  style={{ ...champ, flex: '0 1 110px' }}>
            {PRIORITES.map((p) => <option key={p.cle} value={p.cle}>{p.libelle}</option>)}
          </select>
          <button type="button" data-testid="tache-enregistrer" onClick={creer} disabled={enCours}
                  style={{ ...bouton, background: PRIMAIRE, border: 'none', fontWeight: 600 }}>
            {enCours ? '…' : 'Ajouter'}
          </button>
          <button type="button" data-testid="tache-annuler" onClick={() => setOuvertCreation(false)}
                  style={bouton}>Annuler</button>
        </div>
      )}

      {message && (
        <div data-testid="message-tache"
             style={{ fontSize: '12px', padding: '6px 8px', borderRadius: '8px',
                      marginBottom: '8px', background: 'rgba(239,68,68,0.16)', color: '#fff' }}>
          {message.texte}
        </div>
      )}

      {taches.length === 0 ? (
        <div data-testid="taches-vide"
             style={{ fontSize: '12px', color: 'rgba(255,255,255,0.5)', padding: '6px 0' }}>
          Aucune tâche{pile ? ' dans cette vue' : ''}.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
          {taches.map((t) => {
            const close = t.status === 'fait' || t.status === 'annule';
            return (
              <div key={t.id} data-testid="tache-ligne"
                   style={{ display: 'flex', alignItems: 'center', gap: '8px',
                            padding: '6px 8px', borderRadius: '8px',
                            background: 'rgba(255,255,255,0.05)',
                            borderLeft: `3px solid ${TEINTE_PILE[t.bucket] || PRIMAIRE}`,
                            opacity: close ? 0.6 : 1 }}>
                <button type="button" data-testid="basculer-tache"
                        aria-label={close ? 'Rouvrir la tâche' : 'Terminer la tâche'}
                        onClick={() => changerStatut(t, close ? 'prevu' : 'fait')}
                        disabled={enCours}
                        style={{ ...bouton, padding: '2px 7px' }}>
                  {close ? '↺' : '✓'}
                </button>
                <span style={{ fontSize: '12px', color: '#fff', flex: '1 1 auto',
                               minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis',
                               whiteSpace: 'nowrap',
                               textDecoration: t.status === 'fait' ? 'line-through' : 'none' }}>
                  {t.title}
                </span>
                {t.priority === 'haute' && (
                  <span data-testid="priorite-haute"
                        style={{ fontSize: '10px', padding: '1px 6px', borderRadius: '999px',
                                 background: `rgba(${RGB}, 0.3)`, color: '#fff' }}>haute</span>
                )}
                <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.55)',
                               whiteSpace: 'nowrap' }}>{lisible(t.starts_at)}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
