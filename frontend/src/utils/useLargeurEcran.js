/**
 * useLargeurEcran — CONTACTS V2, temps 2
 *
 * Le dépôt n'utilise aucune media query (0 occurrence dans ContactsManager) :
 * tout y est du style en ligne. Plutôt que d'introduire une feuille CSS pour
 * un seul écran, on lit la largeur et on choisit le rendu — ce qui a
 * l'avantage d'être testable, là où une media query ne l'est pas.
 */
import { useState, useEffect } from 'react';

export const SEUIL_MOBILE = 720;

export default function useLargeurEcran() {
  const lire = () => (typeof window !== 'undefined' ? window.innerWidth : 1024);
  const [largeur, setLargeur] = useState(lire);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    let attente = null;
    const onResize = () => {
      // On ne re-rend pas à chaque pixel : le redimensionnement d'un mobile
      // qui ouvre son clavier déclencherait des dizaines de rendus.
      if (attente) clearTimeout(attente);
      attente = setTimeout(() => setLargeur(window.innerWidth), 120);
    };
    window.addEventListener('resize', onResize);
    return () => { window.removeEventListener('resize', onResize); if (attente) clearTimeout(attente); };
  }, []);

  return { largeur, estMobile: largeur < SEUIL_MOBILE };
}
