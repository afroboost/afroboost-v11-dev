/**
 * V598 — LES NICHES DE PROSPECTION, une seule source de vérité : `/prospection-niches`.
 *
 * Médias, Liens, Vue d'ensemble et Résultats lisent la MÊME liste. Une niche a un
 * `id` stable, une `cle` (ce que médias / liens enregistrent : « A »…« F » pour les
 * six d'origine, l'id pour une niche créée), un `nom` modifiable, un `ordre` et
 * `active`. La lettre affichée se déduit de l'ordre (lettreNiche).
 *
 * Lecture partagée (promesse gardée 60 s, comme useProspectionDonnees) ; tant que
 * le serveur n'a pas répondu — ou s'il échoue — les six niches d'origine servent de
 * repli : l'écran reste lisible. ANTI-BOUCLE (V305) : un seul effet, sans dépendance d'objet.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { NICHES } from '../utils/prospectionStats';

const GARDE_MS = 60000;
let enCours = null;
let lu = 0;

export const NICHES_REPLI = NICHES.map((n, i) => ({ id: n.id, cle: n.id, nom: n.libelle, ordre: i + 1, active: true, origine: true }));

/** Oublier la liste gardée (après une création, un renommage, un archivage). */
export function invaliderNiches() { enCours = null; lu = 0; }

function lire(API) {
  if (!enCours || Date.now() - lu > GARDE_MS) {
    lu = Date.now();
    enCours = axios.get(`${API}/prospection-niches`).then((r) => {
      const liste = (r && r.data && Array.isArray(r.data.niches)) ? r.data.niches : null;
      if (!liste || !liste.length) throw new Error('liste vide');
      return liste;
    }).catch((e) => { enCours = null; throw e; });
  }
  return enCours;
}

export default function useNichesProspection(API) {
  const [niches, setNiches] = useState(NICHES_REPLI);
  const [erreur, setErreur] = useState('');
  const charger = useCallback(async (forcer) => {
    if (forcer) invaliderNiches();
    try {
      const liste = await lire(API);
      setNiches((p) => (JSON.stringify(p) === JSON.stringify(liste) ? p : liste));
      setErreur('');
    } catch (e) {
      setErreur('Les niches n’ont pas pu être lues — affichage des six niches d’origine.');
    }
  }, [API]);
  useEffect(() => { charger(false); }, [charger]);
  return { niches, erreur, recharger: () => charger(true) };
}
