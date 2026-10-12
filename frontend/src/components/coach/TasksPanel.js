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
  /* V616 — DIVULGATION PROGRESSIVE : 3 tâches d'abord, le reste sur demande ;
     sur téléphone, les filtres se replient derrière « Filtrer ». */
  const [toutes, setToutes] = useState(false);
  const [filtresOuverts, setFiltresOuverts] = useState(false);

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
  const cible = { minHeight: '44px', minWidth: '44px' };
  const aVenir = compteurs.a_venir != null ? compteurs.a_venir
    : taches.filter((t) => t.status !== 'fait' && t.status !== 'annule').length;
  const visibles = toutes ? taches : taches.slice(0, 3);
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

      <style>{`
        .v616-taches-filtres::-webkit-scrollbar { display: none; }
        @media (max-width: 639px) {
          .v616-taches-filtres:not(.ouvert) { display: none !important; }
        }
        @media (min-width: 640px) {
          .v616-taches-filtrer { display: none !important; }
        }
      `}</style>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
        <span style={{ fontSize: '14px', fontWeight: 700, color: '#fff',
                       display: 'inline-flex', alignItems: 'center', gap: '6px', whiteSpace: 'nowrap' }}>
          <SvgIcon name="clipboard" size={15} /> Tâches
        </span>
        <span data-testid="taches-a-venir"
              style={{ fontSize: '12px', color: 'rgba(255,255,255,0.6)', whiteSpace: 'nowrap',
                       overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0 }}>
          · {aVenir} à venir
        </span>
        {(compteurs.en_retard || 0) > 0 && (
          <span data-testid="compteur-retard"
                style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '999px', whiteSpace: 'nowrap',
                         background: TEINTE_PILE.en_retard, fontWeight: 600, color: '#fff' }}>
            {compteurs.en_retard} en retard
          </span>
        )}
        <span style={{ flex: '1 1 auto' }} />
        <button type="button" className="v616-taches-filtrer" data-testid="taches-filtrer"
                aria-expanded={filtresOuverts} onClick={() => setFiltresOuverts((o) => !o)}
                aria-label="Filtrer les tâches"
                style={{ ...bouton, ...cible, padding: '0 10px', display: 'inline-flex', alignItems: 'center', gap: '5px',
                         background: pile ? `rgba(${RGB}, 0.35)` : 'transparent' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
               strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3 5h18M6 12h12M10 19h4" /></svg>
          {pile ? (PILES.find((x) => x.cle === pile) || {}).libelle : 'Filtrer'}
        </button>
        <button type="button" data-testid="nouvelle-tache" onClick={ouvrir}
                style={{ ...bouton, ...cible, padding: '0 12px', background: PRIMAIRE, border: 'none', fontWeight: 600 }}>
          + Ajouter
        </button>
      </div>

      <div className={`v616-taches-filtres${filtresOuverts ? ' ouvert' : ''}`}
           style={{ display: 'flex', flexWrap: 'nowrap', overflowX: 'auto', scrollbarWidth: 'none',
                    gap: '6px', marginBottom: '8px' }}>
        {PILES.map((p) => (
          <button key={p.cle || 'toutes'} type="button" data-testid={`pile-${p.cle || 'toutes'}`}
                  onClick={() => { onChangerPile?.(p.cle); setToutes(false); }}
                  aria-pressed={pile === p.cle}
                  style={{ ...bouton, minHeight: '36px', whiteSpace: 'nowrap',
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
          {visibles.map((t) => {
            const close = t.status === 'fait' || t.status === 'annule';
            return (
              <div key={t.id} data-testid="tache-ligne"
                   style={{ display: 'flex', alignItems: 'center', gap: '8px',
                            minHeight: '44px', boxSizing: 'border-box',
                            padding: '4px 10px 4px 4px', borderRadius: '10px',
                            background: 'rgba(255,255,255,0.05)',
                            /* V616 : bordure fine ; seule la couleur sémantique (retard, terminé) ressort */
                            border: `1px solid ${TEINTE_PILE[t.bucket] || 'rgba(255,255,255,0.06)'}`,
                            opacity: close ? 0.6 : 1 }}>
                <button type="button" data-testid="basculer-tache"
                        aria-label={close ? 'Rouvrir la tâche' : 'Terminer la tâche'}
                        onClick={() => changerStatut(t, close ? 'prevu' : 'fait')}
                        disabled={enCours}
                        style={{ ...bouton, ...cible, padding: 0, background: 'transparent', border: 'none',
                                 display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
                  {/* V616 : icônes SVG (règle du projet), cible tactile 44 px */}
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                       strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
                       style={{ color: close ? 'rgba(255,255,255,0.7)' : PRIMAIRE }}>
                    {close
                      ? <path d="M3 12a9 9 0 1 0 3-6.7M3 4v5h5" />
                      : <><rect x="3.5" y="3.5" width="17" height="17" rx="5" /><path d="M8 12.5l2.7 2.7L16 9.5" /></>}
                  </svg>
                </button>
                <span style={{ fontSize: '13px', color: '#fff', flex: '1 1 auto',
                               minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis',
                               whiteSpace: 'nowrap',
                               textDecoration: t.status === 'fait' ? 'line-through' : 'none' }}
                      title={t.title}>
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
          {taches.length > 3 && (
            <button type="button" data-testid="taches-voir-toutes" onClick={() => setToutes((v) => !v)}
                    style={{ ...bouton, ...cible, alignSelf: 'flex-start', background: 'transparent', border: 'none',
                             color: PRIMAIRE, fontWeight: 600, fontSize: '13px', padding: '0 6px' }}>
              {toutes ? 'Réduire' : `Voir toutes les tâches (${taches.length})`}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
