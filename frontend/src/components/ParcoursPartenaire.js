// ParcoursPartenaire.js — V594 : le parcours simplifié d'un visiteur venu d'un Partenaire.
//
// CE COMPOSANT NE DESSINE RIEN DE NOUVEAU. Il ASSEMBLE des pièces existantes :
//   * `LigneOffre` — LA ligne de « Toutes les offres » (vraie miniature, badge, prix) ;
//   * `FicheOffre` — LE « Détail de l'offre » (grande image, infos, bouton existant) ;
//   * `SessionsModal` — LE calendrier « Sessions », comme le wizard Pass Duo ;
//   * `Etapes`, `ResumeSeance` (parrainage/wizardCommun) et les boutons `cp-b` / `cp-link` ;
//   * le FORMULAIRE ACTUEL de la vitrine, qui n'est pas recopié : App.js le « téléporte »
//     (portail React) dans `slotFormulaire` et n'en montre que les champs de l'étape.
//
// TROIS ÉCRANS COURTS : 1 Séance · 2 Coordonnées (nom, e-mail, WhatsApp) · 3 Validation
// (naissance, conditions, « Réserver gratuitement »). La 4e étape (Confirmation) est
// affichée par l'espace client.
//
// LA SÉANCE N'EST PAS RÉSERVÉE ICI. Elle suit le mécanisme INV-2 existant
// (`course` + `occurrence`) : la redirection après `/checkout/free` la porte jusqu'à
// l'espace client, qui la présélectionne. Les séances proposées sont filtrées par LA
// règle INV-2 (`verdictSeanceInvitation`) : une séance montrée ici est forcément une
// séance que l'espace acceptera.
import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import SvgIcon from './SvgIcon';
import SessionsModal, { normaliserAgenda } from './SessionsModal';
import { LigneOffre, FicheOffre } from './OffresAimants';
import { regrouperOffres } from '../utils/offresAimants';
import useLargeurEcran from '../utils/useLargeurEcran';
import { Etapes, ResumeSeance } from './parrainage/wizardCommun';
import { verdictSeanceInvitation } from '../utils/invitationSeance';
import './parrainage/wizardFilleul.css';
import './parrainage/invitationWizard.css';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;

export const ETAPES_PARCOURS_PARTENAIRE = ['Séance', 'Coordonnées', 'Validation', 'Confirmation'];

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

/** Les champs de l'étape « Coordonnées » sont-ils valides ? (validation native du navigateur) */
export function coordonneesValides(conteneur) {
  if (!conteneur) return false;
  const champs = ['user-name-input', 'user-email-input', 'user-whatsapp-input']
    .map((t) => conteneur.querySelector(`[data-testid="${t}"]`)).filter(Boolean);
  if (champs.length !== 3) return false;
  for (let i = 0; i < champs.length; i += 1) {
    if (!champs[i].checkValidity()) { champs[i].reportValidity(); return false; }
  }
  return true;
}

export default function ParcoursPartenaire({ offre, offres, courses, analyserMedia, Countdown, etape, onEtape,
  seance, onSeance, onSlotFormulaire, onQuitter }) {
  const [agenda, setAgenda] = useState(null);
  const [calendrier, setCalendrier] = useState(false);
  const [fiche, setFiche] = useState(null);
  const slot = useRef(null);
  const { estMobile } = useLargeurEcran();
  const groupe = useMemo(() => regrouperOffres(Array.isArray(offres) && offres.length ? offres : [offre]), [offres, offre]);

  // UN appel, au montage (dépendance vide : aucune boucle possible).
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
  const brancherSlot = (el) => { slot.current = el; if (onSlotFormulaire) onSlotFormulaire(el); };
  const retour = (n) => (
    <button type="button" className="cp-link cp-wz-tap cp-wz-retour" onClick={() => onEtape(n)} data-testid="pp-retour">
      <SvgIcon name="arrowLeft" size={14} /> Retour
    </button>
  );

  return (
    <div className="cp-root" data-testid="parcours-partenaire"
         style={{ position: 'fixed', inset: 0, zIndex: 900, overflowY: 'auto',
                  background: 'var(--background-color, #000000)' }}>
      <div className="cp-wf" style={{ maxWidth: 520, margin: '0 auto', padding: '16px 16px 32px' }}>
        <Etapes etape={etape} etapes={ETAPES_PARCOURS_PARTENAIRE} className="cp-wf-etapes" testid="pp-etapes" />

        {/* ── ÉCRAN 1 : l'offre (vraie carte existante) + la séance ─────────────── */}
        {etape === 1 ? (
          <div data-testid="pp-etape-seance">
            {offre ? (
              <div data-testid="pp-offre" style={{ margin: '12px 0 4px' }}>
                <LigneOffre offre={offre} mensuelRef={groupe.mensuelRef} analyser={analyserMedia} onOuvrir={setFiche} />
                <button type="button" className="cp-link cp-wz-tap" onClick={() => setFiche({ offres: [offre] })}
                        data-testid="pp-voir-offre">
                  Voir l’offre
                </button>
              </div>
            ) : null}

            <p className="cp-label" style={{ margin: '14px 0 6px' }}>Séance</p>
            {resume ? (
              <ResumeSeance seance={resume} onChanger={() => setCalendrier(true)} testid="pp-seance-resume" />
            ) : (
              <>
                <p className="cp-fine" data-testid="pp-sans-seance" style={{ margin: '0 0 8px' }}>
                  {aucuneSeance
                    ? 'Aucune séance n’est publiée pour le moment : tu la choisiras dans ton espace.'
                    : 'Aucune séance choisie'}
                </p>
                <button type="button" className="cp-b cp-b--secondary cp-wz-cible" onClick={() => setCalendrier(true)}
                        disabled={agenda === null || aucuneSeance} data-testid="pp-seance-choisir">
                  <SvgIcon name="calendar" size={20} /> Choisir ma séance
                </button>
              </>
            )}
            <button type="button" className="cp-b cp-wz-cible cp-wf-cta" style={{ marginTop: 14 }}
                    onClick={() => onEtape(2)} disabled={!seance && !aucuneSeance} data-testid="pp-continuer">
              Continuer <SvgIcon name="arrowRight" size={20} />
            </button>
            <button type="button" className="cp-link cp-wz-tap cp-wz-retour" onClick={onQuitter} data-testid="pp-quitter">
              <SvgIcon name="arrowLeft" size={14} /> Retour
            </button>
          </div>
        ) : null}

        {/* ── ÉCRAN 2 : la séance retenue, en rappel compact ────────────────────── */}
        {etape === 2 && resume ? (
          <div style={{ marginTop: 12 }}>
            <ResumeSeance seance={resume} onChanger={() => onEtape(1)} testid="pp-seance-resume" />
          </div>
        ) : null}

        {/* ── ÉCRANS 2 et 3 : le formulaire ACTUEL, rendu ici par App.js (portail) ── */}
        <div ref={brancherSlot} data-testid="pp-etape-informations"
             style={{ display: etape >= 2 ? 'block' : 'none', marginTop: 12 }} />

        {etape === 2 ? (
          <>
            <button type="button" className="cp-b cp-wz-cible cp-wf-cta"
                    onClick={() => { if (coordonneesValides(slot.current)) onEtape(3); }} data-testid="pp-continuer-coordonnees">
              Continuer <SvgIcon name="arrowRight" size={20} />
            </button>
            {retour(1)}
          </>
        ) : null}
        {etape === 3 ? retour(2) : null}
      </div>

      {/* « Voir l'offre » : LA fiche existante (grande image, infos, bouton). Son bouton
          ne lance rien ici : on est déjà dans le parcours, il referme simplement la fiche. */}
      {fiche ? (
        <FicheOffre
          choix={fiche}
          mensuelRef={groupe.mensuelRef}
          analyser={analyserMedia}
          onChoisir={() => setFiche(null)}
          onFermer={() => setFiche(null)}
          checkoutBusy={false}
          estMobile={estMobile}
          Countdown={Countdown}
          toutesOffres={offres}
        />
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
    </div>
  );
}
