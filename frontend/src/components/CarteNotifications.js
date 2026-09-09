import React, { useCallback, useEffect, useState } from 'react';
import {
  etatNotifications, assurerAbonnementPush, activerNotifications,
} from '../services/pushNotificationService';

/**
 * 🔔 CarteNotifications — l'état des notifications, et le bouton qui les active.
 *
 * POURQUOI ELLE EXISTE. L'abonnement push d'un téléphone est révoqué
 * régulièrement par le service de push (réponse `410`). Le serveur le
 * désactivait bien, mais rien, côté application, ne le recréait : l'appareil
 * devenait injoignable en silence, et la seule issue connue était d'aller
 * fouiller les réglages de Chrome. Ce n'est pas une expérience acceptable.
 *
 * CE QU'ELLE FAIT, ET DANS CET ORDRE :
 *   1. au montage, elle RÉCONCILIE sans rien demander — si la permission est
 *      déjà accordée et que l'abonnement a disparu, il est recréé et réenregistré ;
 *   2. si la permission n'a jamais été demandée, elle propose un bouton, et
 *      c'est LE CLIC qui ouvre la demande native (les navigateurs l'exigent) ;
 *   3. si elle a été refusée, elle le dit UNE fois et n'insiste plus jamais.
 *
 * Aucun jargon à l'écran : ni endpoint, ni service worker, ni VAPID.
 */
export default function CarteNotifications({ participantId, role, email }) {
  const [etat, setEtat] = useState('inconnu');
  const [occupe, setOccupe] = useState(false);

  // Réconciliation silencieuse. N'ouvre AUCUNE popup : sans permission déjà
  // accordée, elle se contente de rendre l'état.
  useEffect(() => {
    let vivant = true;
    (async () => {
      const e = etatNotifications();
      if (!vivant) return;
      if (e !== 'granted') { setEtat(e); return; }
      const r = await assurerAbonnementPush({ participantId, role, email });
      if (vivant) setEtat(r.abonne ? 'ok' : 'granted_sans_abonnement');
    })();
    return () => { vivant = false; };
  }, [participantId, role, email]);

  const activer = useCallback(async () => {
    if (occupe) return;
    setOccupe(true);
    try {
      const r = await activerNotifications({ participantId, role, email });
      setEtat(r.abonne ? 'ok' : (r.etat === 'granted' ? 'granted_sans_abonnement' : r.etat));
    } finally {
      setOccupe(false);
    }
  }, [occupe, participantId, role, email]);

  if (etat === 'inconnu' || etat === 'non_supporte') return null;

  const CADRE = {
    border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.28)',
    borderRadius: 12, padding: 14, marginBottom: 16,
    background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.06)',
  };
  const cloche = (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
         stroke="var(--primary-color, #D91CD2)" strokeWidth="1.8"
         strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );

  if (etat === 'ok') {
    return (
      <div style={CADRE} data-testid="carte-notifications">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {cloche}
          <span style={{ color: '#fff', fontSize: 13, fontWeight: 600 }}>
            Notifications activées
          </span>
        </div>
        <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12, margin: '6px 0 0', lineHeight: 1.4 }}>
          Tu recevras les rappels de cours sur cet appareil.
        </p>
      </div>
    );
  }

  if (etat === 'denied') {
    // On le dit UNE fois, sans bouton : redemander est impossible, et insister
    // ne ferait qu'agacer.
    return (
      <div style={CADRE} data-testid="carte-notifications">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {cloche}
          <span style={{ color: '#fff', fontSize: 13, fontWeight: 600 }}>
            Notifications désactivées sur cet appareil
          </span>
        </div>
        <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12, margin: '6px 0 0', lineHeight: 1.4 }}>
          Tu peux les réautoriser depuis les réglages de ton navigateur pour ce site.
        </p>
      </div>
    );
  }

  // 'default' (jamais demandé) ou 'granted_sans_abonnement' (permission
  // accordée mais l'abonnement n'a pas pu être recréé — un clic le retente).
  const premiere = etat === 'default';
  return (
    <div style={CADRE} data-testid="carte-notifications">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        {cloche}
        <span style={{ color: '#fff', fontSize: 13, fontWeight: 600 }}>
          {premiere ? 'Activer les notifications' : 'Réactiver les notifications'}
        </span>
      </div>
      <p style={{ color: 'rgba(255,255,255,0.7)', fontSize: 12, margin: '0 0 10px', lineHeight: 1.4 }}>
        Reçois les rappels de cours et les informations importantes directement sur ton téléphone.
      </p>
      <button
        type="button"
        onClick={activer}
        disabled={occupe}
        data-testid="carte-notifications-activer"
        aria-label={premiere ? 'Activer les notifications' : 'Réactiver les notifications'}
        style={{
          padding: '9px 18px', borderRadius: 10, border: 'none', cursor: occupe ? 'wait' : 'pointer',
          background: 'var(--primary-color, #D91CD2)', color: '#fff',
          fontSize: 13, fontWeight: 700, opacity: occupe ? 0.7 : 1,
        }}
      >
        {occupe ? 'Activation…' : (premiere ? 'Activer les notifications' : 'Réactiver')}
      </button>
    </div>
  );
}
