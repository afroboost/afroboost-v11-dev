/**
 * V595 — les données de Vue d'ensemble et Résultats, chargées UNE fois.
 *
 * Uniquement des GET existants : toutes les pages de `/partner-prospects` (50 par
 * page, règle du dépôt), les rendez-vous de `/calendar-events` (fenêtres de 60 jours,
 * la route est bornée à 62) et les compteurs de `/prospect-inbound` (`limit=1`).
 * Aucun POST, aucun PATCH : ouvrir ces écrans ne change rien en base.
 *
 * Les deux écrans partagent le même chargement (promesse gardée 60 s) : passer de
 * l'un à l'autre ne relit pas 398 fiches. ANTI-BOUCLE (V305) : un seul effet, sans
 * dépendance d'objet ; « Actualiser » est un clic, jamais un minuteur.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';

const PAGE = 50;
const PAGES_MAX = 40;            // 2 000 fiches : bien au-delà des 398 d'aujourd'hui
const RDV_DEBUT = '2026-08-01';  // CAL-3 (planifier un rendez-vous prospect) n'existe pas avant
const FENETRE_JOURS = 60;
const GARDE_MS = 60000;

let enCours = null;
let lu = 0;

async function toutesLesFiches(API) {
  const fiches = [];
  let total = null;
  for (let page = 0; page < PAGES_MAX; page += 1) {
    const r = await axios.get(`${API}/partner-prospects`, { params: { limit: PAGE, offset: page * PAGE } });
    const d = (r && r.data) || {};
    const lot = Array.isArray(d.prospects) ? d.prospects : [];
    if (total === null && typeof d.total === 'number') total = d.total;
    fiches.push(...lot);
    if (lot.length < PAGE || (total !== null && fiches.length >= total)) break;
  }
  return { fiches, total: total === null ? fiches.length : total };
}

async function rendezVous(API) {
  const evenements = [];
  const fin = Date.now() + 365 * 86400000;
  for (let t = Date.parse(`${RDV_DEBUT}T00:00:00Z`); t < fin; t += FENETRE_JOURS * 86400000) {
    const de = new Date(t).toISOString();
    const a = new Date(Math.min(t + FENETRE_JOURS * 86400000, fin)).toISOString();
    const r = await axios.get(`${API}/calendar-events`, { params: { from: de, to: a } });
    const lot = (r && r.data && Array.isArray(r.data.events)) ? r.data.events : [];
    lot.forEach((e) => { if (e && e.event_type === 'appointment' && e.prospect_id) evenements.push(e); });
  }
  const vus = new Set();
  return evenements.filter((e) => (vus.has(e.id) ? false : (vus.add(e.id), true)));
}

async function conversations(API) {
  const r = await axios.get(`${API}/prospect-inbound`, { params: { limit: 1 } });
  const d = (r && r.data) || {};
  return { total: Number(d.conversations_total) || 0, compteurs: d.conversations_counts || {} };
}

function charger(API, forcer) {
  if (!forcer && enCours && Date.now() - lu < GARDE_MS) return enCours;
  lu = Date.now();
  enCours = (async () => {
    const [f, rdv, conv] = await Promise.all([
      toutesLesFiches(API),
      rendezVous(API).catch(() => null),       // un calendrier illisible n'efface pas les fiches
      conversations(API).catch(() => null),
    ]);
    return { ...f, rdv, conversations: conv, lu_a: new Date().toISOString() };
  })();
  enCours.catch(() => { enCours = null; });
  return enCours;
}

export default function useProspectionDonnees(API) {
  const [etat, setEtat] = useState({ chargement: true, erreur: '', donnees: null });

  const lancer = useCallback((forcer) => {
    setEtat((prev) => (prev.chargement && !prev.erreur ? prev : { ...prev, chargement: true, erreur: '' }));
    charger(API, forcer).then(
      (donnees) => setEtat({ chargement: false, erreur: '', donnees }),
      (e) => {
        const code = e && e.response && e.response.status;
        setEtat({ chargement: false, donnees: null,
          erreur: code === 401 || code === 403
            ? 'Session expirée — reconnectez-vous pour voir les chiffres.'
            : 'Les données de prospection n’ont pas pu être lues. Réessayez.' });
      });
  }, [API]);

  useEffect(() => { lancer(false); }, [lancer]);
  return { ...etat, actualiser: () => lancer(true) };
}
