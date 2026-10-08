// ParcoursPartenaire.js — V594 : le parcours simplifié d'un visiteur venu d'un Partenaire.
//
// CE COMPOSANT NE DESSINE RIEN DE NOUVEAU. Il ASSEMBLE des pièces existantes :
//   * `Etapes`, `ResumeSeance` (parrainage/wizardCommun) et les boutons `cp-b` / `cp-link` ;
//   * `VignetteOffre` (OffresAimants) pour rappeler l'offre d'essai ;
//   * `SessionsModal` pour choisir la séance (comme le wizard Pass Duo) ;
//   * le FORMULAIRE ACTUEL de la vitrine, qui n'est pas recopié : App.js le
//     « téléporte » (portail React) dans `slotFormulaire` pendant l'étape 2.
//
// LA SÉANCE N'EST PAS RÉSERVÉE ICI. Elle suit le mécanisme INV-2 existant
// (`course` + `occurrence`) : le bandeau du formulaire l'annonce, la redirection
// après `/checkout/free` la porte jusqu'à l'espace client, qui la présélectionne.
// Les séances proposées sont filtrées par LA règle INV-2 (`verdictSeanceInvitation`) :
// une séance montrée ici est forcément une séance que l'espace acceptera.
import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import SvgIcon from './SvgIcon';
import SessionsModal, { normaliserAgenda } from './SessionsModal';
import { VignetteOffre } from './OffresAimants';
import { Etapes, ResumeSeance } from './parrainage/wizardCommun';
import { verdictSeanceInvitation } from '../utils/invitationSeance';
import './parrainage/wizardFilleul.css';
import './parrainage/invitationWizard.css';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;

export const ETAPES_PARCOURS_PARTENAIRE = ['Séance', 'Informations', 'Confirmation'];

/** Le parcours ne s'ouvre que pour un lien d'essai venu d'un Partenaire. Pur. */
export function lireParcoursPartenaire(search) {
  let q;
  try { q = new URLSearchParams(search != null ? search : (window.location.search || '')); } catch (e) { return null; }
  const offre = String(q.get('offre') || '').trim();
  if (!offre || q.get('reserver') !== '1' || q.get('utm_source') !== 'partenaire') return null;
  return { offre };
}

/** `AAAA-MM-JJTHH:MM` d'une date locale — le format INV-2. Pur. */
export function isoMinute(d) {
  if (!(d instanceof Date) || Number.isNaN(d.getTime())) return '';
  const z = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}T${z(d.getHours())}:${z(d.getMinutes())}`;
}

/** Les occurrences de l'agenda que l'espace client acceptera pour cette offre. Pur. */
export function seancesCompatibles(agenda, offre, cours, maintenant) {
  if (!offre) return [];
  return (Array.isArray(agenda) ? agenda : [])
    .map((o) => ({ ...o, iso: isoMinute(o.quand) }))
    .filter((o) => {
      const v = verdictSeanceInvitation({ offre: offre.id, course: o.id, occurrence: o.iso }, offre, cours, maintenant);
      return !!(v && v.etat === 'ok');
    });
}

export default function ParcoursPartenaire({ offre, courses, analyserMedia, etape, onEtape,
  seance, onSeance, onSlotFormulaire, onQuitter }) {
  const [agenda, setAgenda] = useState(null);
  const [calendrier, setCalendrier] = useState(false);

  // UN appel, au montage (dépendance primitive : aucune boucle possible).
  useEffect(() => {
    let annule = false;
    (async () => {
      try {
        const res = await axios.get(`${API}/sessions/agenda`);
        if (!annule) setAgenda(normaliserAgenda(res && res.data && res.data.occurrences));
      } catch (e) {
        if (!annule) setAgenda([]);
      }
    })();
    return () => { annule = true; };
  }, []);

  const seances = useMemo(() => seancesCompatibles(agenda, offre, courses), [agenda, offre, courses]);
  const aucuneSeance = agenda !== null && seances.length === 0;
  const coursChoisi = seance ? (courses || []).find((c) => c && c.id === seance.course) : null;
  const resume = seance ? {
    occurrence: seance.occurrence,
    nom: (coursChoisi && coursChoisi.name) || '',
    lieu: (coursChoisi && (coursChoisi.locationName || coursChoisi.location)) || '',
  } : null;

  return (
    <div className="cp-root" data-testid="parcours-partenaire"
         style={{ position: 'fixed', inset: 0, zIndex: 900, overflowY: 'auto',
                  background: 'var(--background-color, #000000)' }}>
      <div className="cp-wf" style={{ maxWidth: 560, margin: '0 auto', padding: '16px 16px 40px' }}>
        <Etapes etape={etape} etapes={ETAPES_PARCOURS_PARTENAIRE} className="cp-wf-etapes" testid="pp-etapes" />

        {offre ? (
          <div data-testid="pp-offre" style={{ borderRadius: 16, overflow: 'hidden', margin: '12px 0' }}>
            <VignetteOffre offre={offre} analyser={analyserMedia} hauteur={120} />
            <p className="cp-wf-titre" style={{ margin: '10px 2px 0' }}>{offre.name}</p>
          </div>
        ) : null}

        {etape === 1 ? (
          <div data-testid="pp-etape-seance">
            {resume ? (
              <ResumeSeance seance={resume} onChanger={() => setCalendrier(true)} testid="pp-seance-resume" />
            ) : (
              <button type="button" className="cp-b cp-b--secondary cp-wz-cible" onClick={() => setCalendrier(true)}
                      disabled={agenda === null || aucuneSeance} data-testid="pp-seance-choisir">
                <SvgIcon name="calendar" size={20} /> Choisir ma séance
              </button>
            )}
            {aucuneSeance ? (
              <p className="cp-fine" data-testid="pp-aucune-seance">
                Aucune séance n’est publiée pour le moment : tu la choisiras dans ton espace.
              </p>
            ) : null}
            {calendrier ? (
              <SessionsModal
                open
                onClose={() => setCalendrier(false)}
                occurrencesFournies={seances}
                libelleAction="Choisir cette séance"
                noteAction="Rien n’est encore réservé : tu confirmeras ta place dans ton espace."
                onReserve={(occ) => {
                  if (!occ || !occ.iso) return;
                  onSeance({ offre: offre.id, course: occ.id, occurrence: occ.iso });
                  setCalendrier(false);
                }}
              />
            ) : null}
            <button type="button" className="cp-b cp-wz-cible cp-wf-cta" style={{ marginTop: 16 }}
                    onClick={() => onEtape(2)} disabled={!seance && !aucuneSeance} data-testid="pp-continuer">
              Continuer <SvgIcon name="arrowRight" size={20} />
            </button>
            <button type="button" className="cp-link cp-wz-tap cp-wz-retour" onClick={onQuitter} data-testid="pp-quitter">
              <SvgIcon name="arrowLeft" size={14} /> Retour
            </button>
          </div>
        ) : null}

        {/* Étape 2 : le formulaire ACTUEL est rendu ici par App.js (portail). */}
        <div ref={onSlotFormulaire} data-testid="pp-etape-informations"
             style={{ display: etape === 2 ? 'block' : 'none', marginTop: 8 }} />
        {etape === 2 ? (
          <button type="button" className="cp-link cp-wz-tap cp-wz-retour" onClick={() => onEtape(1)} data-testid="pp-retour">
            <SvgIcon name="arrowLeft" size={14} /> Retour
          </button>
        ) : null}
      </div>
    </div>
  );
}
