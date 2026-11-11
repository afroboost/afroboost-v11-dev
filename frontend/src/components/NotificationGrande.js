import React, { useCallback, useEffect, useState } from 'react';
import {
  TYPES, actionDe, aMontrer, texteComplet, titreDe, typeDe,
} from '../utils/notificationGrande';

/**
 * V659 — LA GRANDE FENÊTRE DE NOTIFICATION, pour l'abonné ET pour le coach.
 *
 * CE QU'ELLE REMPLACE. Une vignette de 384 px, collée en haut à droite, texte
 * à 12 px, et le message COUPÉ À 60 CARACTÈRES suivi de « … ». Sur un
 * téléphone, on voyait le début d'une phrase et rien d'autre : il fallait
 * deviner. Quatre pouvaient s'empiler.
 *
 * CE QU'ELLE FAIT. Un panneau large (94 % de l'écran, jusqu'à 85 % de la
 * hauteur), le texte ENTIER à 16 px, une icône qui dit le sujet, un bouton
 * d'action large quand une destination existe, une fermeture visible, le
 * défilement à l'intérieur si c'est long, et les encoches respectées
 * (`env(safe-area-inset-*)`).
 *
 * UN SEUL COMPOSANT POUR LES DEUX RÔLES. Le coach et l'abonné reçoivent des
 * contenus différents, pas deux interfaces différentes : dupliquer aurait créé
 * deux endroits à corriger le jour où l'une des deux a un défaut.
 *
 * CE QU'ELLE NE PRÉTEND PAS FAIRE. Les bannières du système (celles qui
 * s'affichent quand l'application est fermée) appartiennent à iOS et Android :
 * leur taille ne se pilote pas depuis une page web. Cette fenêtre est celle
 * d'Afroboost, à l'intérieur de l'application.
 */
const PICTO = {
  [TYPES.cours]: 'M8 2v4M16 2v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z',
  [TYPES.reservation]: 'm20 6-11 11-5-5',
  [TYPES.abonnement]: 'M3 10h18M5 6h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z',
  [TYPES.paiement]: 'M12 1v22M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6',
  [TYPES.message]: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z',
  [TYPES.info]: 'M12 16v-4M12 8h.01M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z',
};

export default function NotificationGrande({ file, onLue, onFermer, onAction }) {
  const [fermee, setFermee] = useState(null);
  const notif = aMontrer(file);
  const id = notif && (notif.id || notif.key);

  // Une nouvelle notification rouvre la fenêtre : on ne reste pas fermé sur
  // une notification qu'on n'a jamais vue.
  useEffect(() => { setFermee(null); }, [id]);

  const fermer = useCallback(() => {
    setFermee(id);
    if (notif && typeof onLue === 'function') onLue(notif);
    if (typeof onFermer === 'function') onFermer(notif);
  }, [id, notif, onLue, onFermer]);

  if (!notif || fermee === id) return null;

  const C = 'var(--primary-color, #D91CD2)';
  const t = typeDe(notif);
  const action = actionDe(notif);
  const texte = texteComplet(notif);

  const agir = () => {
    if (typeof onAction === 'function') onAction(notif, action);
    if (action && typeof action.onClick === 'function') action.onClick(notif);
    else if (action && action.href) window.location.assign(action.href);
    fermer();
  };

  return (
    <div
      role="dialog" aria-modal="true" aria-labelledby="af-notif-titre"
      data-testid="notification-grande"
      onClick={(e) => { if (e.target === e.currentTarget) fermer(); }}
      style={{
        position: 'fixed', inset: 0, zIndex: 10050,
        background: 'rgba(0,0,0,.66)', backdropFilter: 'blur(5px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 'max(14px, env(safe-area-inset-top)) 3vw max(14px, env(safe-area-inset-bottom))',
      }}
    >
      <div
        style={{
          width: 'min(94vw, 520px)', maxHeight: '85vh',
          display: 'flex', flexDirection: 'column',
          background: 'linear-gradient(160deg,#141018,#0b0b0f)',
          border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), .32)',
          borderRadius: 22, color: '#fff', overflow: 'hidden',
          boxShadow: '0 24px 70px rgba(0,0,0,.6)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 13, padding: '20px 18px 12px' }}>
          <span style={{ flexShrink: 0, width: 42, height: 42, borderRadius: 13,
                         background: 'rgba(var(--primary-rgb, 217, 28, 210), .16)',
                         display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke={C}
                 strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d={PICTO[t] || PICTO[TYPES.info]} />
            </svg>
          </span>
          <h2 id="af-notif-titre" data-testid="notification-grande-titre"
              style={{ margin: 0, fontSize: '1.08rem', fontWeight: 800, lineHeight: 1.3, flex: 1, minWidth: 0 }}>
            {titreDe(notif)}
          </h2>
          <button type="button" onClick={fermer} aria-label="Fermer la notification"
            data-testid="notification-grande-fermer"
            style={{ flexShrink: 0, width: 38, height: 38, borderRadius: 999, border: 0,
                     background: 'rgba(255,255,255,.09)', color: '#fff', cursor: 'pointer', padding: 0 }}>
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 strokeWidth="2.5" strokeLinecap="round" style={{ display: 'block', margin: '0 auto' }}>
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div data-testid="notification-grande-texte"
             style={{ padding: '0 18px 16px', overflowY: 'auto', flex: '1 1 auto',
                      fontSize: 16, lineHeight: 1.6, color: 'rgba(255,255,255,.9)',
                      whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
          {texte}
        </div>

        <div style={{ padding: '0 18px max(16px, env(safe-area-inset-bottom))',
                      display: 'grid', gap: 9, flexShrink: 0 }}>
          {action && (
            <button type="button" onClick={agir} data-testid="notification-grande-action"
              style={{ width: '100%', minHeight: 52, border: 0, borderRadius: 15,
                       background: C, color: '#fff', fontWeight: 800, fontSize: 16.5, cursor: 'pointer' }}>
              {action.libelle}
            </button>
          )}
          <button type="button" onClick={fermer}
            style={{ width: '100%', minHeight: 44, background: 'transparent',
                     border: '1px solid rgba(255,255,255,.17)', borderRadius: 13,
                     color: 'rgba(255,255,255,.72)', fontSize: 15, cursor: 'pointer' }}>
            Fermer
          </button>
        </div>
      </div>
    </div>
  );
}
