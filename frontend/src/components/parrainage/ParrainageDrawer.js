/**
 * V552 — TIROIR COMMUN DU CENTRE PARRAINAGE (« Mes outils »).
 *
 * UN seul composant pour les quatre raccourcis (Crédits, Pass Duo,
 * Invitations, Historique) : bottom sheet sous 768 px, panneau latéral au-delà.
 * Il ne connaît RIEN du parrainage : il affiche tel quel le bloc complet que le
 * Centre lui passe en `children` — aucune donnée, aucune action supprimée.
 *
 * Il est rendu À CÔTÉ de l'assistant d'invitation, jamais à sa place : ouvrir
 * ou fermer un tiroir ne démonte pas l'assistant (son état est conservé).
 *
 * ACCESSIBILITÉ : role="dialog" + aria-modal + aria-labelledby (le titre),
 * focus posé sur « Fermer » (44 × 44 px), Échap ferme, Tab reste dans le
 * tiroir, fond cliquable ferme, focus rendu au déclencheur à la fermeture.
 *
 * DIALOGUES IMBRIQUÉS : le sheet « Changer d'offre » et le calendrier des
 * séances écoutent aussi Échap. Le tiroir ne réagit que s'il est le dialogue
 * modal LE PLUS HAUT (le dernier du document) : Échap ferme d'abord le sheet.
 *
 * DÉFILEMENT : la classe `cp-scroll-lock` (html + body) bloque le fond. Une
 * classe, pas un style en ligne : le calendrier (SessionsModal) retire ses
 * propres styles en ligne à sa fermeture sans toucher à ce verrou.
 */
import React, { useEffect, useRef } from 'react';
import SvgIcon from '../SvgIcon';

let verrous = 0;
function verrouillerDefilement() {
  verrous += 1;
  if (verrous === 1) {
    document.documentElement.classList.add('cp-scroll-lock');
    document.body.classList.add('cp-scroll-lock');
  }
}
function libererDefilement() {
  verrous = Math.max(0, verrous - 1);
  if (verrous === 0) {
    document.documentElement.classList.remove('cp-scroll-lock');
    document.body.classList.remove('cp-scroll-lock');
  }
}

/** Vrai si `el` est le dialogue modal le plus haut du document. */
export function estDialogueDuDessus(el) {
  if (!el) return false;
  const tous = document.querySelectorAll('[role="dialog"][aria-modal="true"]');
  return tous.length > 0 && tous[tous.length - 1] === el;
}

const FOCUSABLES = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

let compteurIds = 0;

/**
 * @param {string}   titre        titre visible (et nom accessible) du tiroir
 * @param {function} onClose      fermeture (bouton, Échap, fond)
 * @param {Element}  declencheur  le raccourci qui a ouvert le tiroir (focus rendu à la fermeture)
 * @param {string}   outil        identifiant du contenu (data-outil, pour les tests et le style)
 */
export default function ParrainageDrawer({ titre, onClose, declencheur, outil, children }) {
  const panneau = useRef(null);
  const fermer = useRef(null);
  const idTitre = useRef(null);
  if (!idTitre.current) { compteurIds += 1; idTitre.current = `cp-drawer-titre-${compteurIds}`; }
  const surFermer = useRef(onClose);
  surFermer.current = onClose;

  // Montage : verrou du fond + focus sur « Fermer ». Démontage : focus rendu.
  useEffect(() => {
    const retour = declencheur || document.activeElement;
    verrouillerDefilement();
    if (fermer.current) fermer.current.focus({ preventScroll: true });
    return () => {
      libererDefilement();
      if (retour && typeof retour.focus === 'function' && document.contains(retour)) {
        retour.focus({ preventScroll: true });
      }
    };
    // Le déclencheur est lu UNE fois, à l'ouverture.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const surTouche = (e) => {
      if (!estDialogueDuDessus(panneau.current)) return;
      if (e.key === 'Escape') { e.preventDefault(); surFermer.current(); return; }
      if (e.key !== 'Tab') return;
      const liste = Array.from(panneau.current.querySelectorAll(FOCUSABLES));
      if (!liste.length) return;
      const premier = liste[0];
      const dernier = liste[liste.length - 1];
      if (e.shiftKey && document.activeElement === premier) { e.preventDefault(); dernier.focus(); }
      else if (!e.shiftKey && document.activeElement === dernier) { e.preventDefault(); premier.focus(); }
    };
    document.addEventListener('keydown', surTouche);
    return () => document.removeEventListener('keydown', surTouche);
  }, []);

  return (
    <div className="cp-drawer-bg" onClick={() => surFermer.current()} data-testid="parrainage-drawer-fond">
      <div
        ref={panneau}
        className="cp-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby={idTitre.current}
        data-testid="parrainage-drawer"
        data-outil={outil || ''}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="cp-sheet-poignee cp-drawer-poignee" aria-hidden="true" />
        <div className="cp-drawer-tete">
          <h2 className="cp-drawer-titre" id={idTitre.current}>{titre}</h2>
          <button type="button" ref={fermer} className="cp-drawer-fermer" aria-label="Fermer"
                  onClick={() => surFermer.current()} data-testid="drawer-fermer">
            <SvgIcon name="x" size={22} />
          </button>
        </div>
        <div className="cp-drawer-corps">{children}</div>
      </div>
    </div>
  );
}
