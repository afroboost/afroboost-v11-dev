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
/**
 * V669 — CE QU'ON DIT QUAND ÇA N'A PAS MARCHÉ.
 *
 * Chaque cas a sa cause ET son geste. Un « réessaie » générique sur un iPhone
 * non installé serait faux : là-bas, aucun réessai ne peut aboutir tant que
 * l'application n'est pas sur l'écran d'accueil — c'est une règle d'Apple.
 * PURE : aucun effet, testable seule.
 */
export function messageEchec(r) {
  const etat = (r && r.etat) || '';
  const motif = (r && r.motif) || '';
  if (etat === 'non_supporte') {
    return "Sur iPhone, les rappels n'arrivent que depuis l'application installée : "
      + "ajoute d'abord Afroboost à ton écran d'accueil, puis rouvre-la par son icône.";
  }
  if (etat === 'denied') {
    return 'Les notifications sont bloquées pour ce site. Autorise-les dans les réglages '
      + 'de ton navigateur (ou de ton téléphone), puis reviens ici.';
  }
  if (etat === 'default') {
    return "La demande d'autorisation est restée sans réponse. Touche « Réactiver », "
      + 'puis choisis « Autoriser ».';
  }
  if (motif === 'vapid_absente') {
    return 'Le service de rappels est momentanément indisponible. Réessaie dans un instant.';
  }
  return "La réactivation n'a pas abouti. Réessaie, et si cela persiste préviens ton coach.";
}

export default function CarteNotifications({ participantId, role, email }) {
  const [etat, setEtat] = useState('inconnu');
  // V669 — ce que le dernier clic a produit. `confirme` n'est posé QUE sur un
  // abonnement réellement créé ; `echec` porte une explication utile.
  const [confirme, setConfirme] = useState(false);
  const [echec, setEchec] = useState(null);
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

  // =====================================================================
  // V669 — « RÉACTIVER » DISAIT LE RÉSULTAT À PERSONNE
  // =====================================================================
  //
  // DÉFAUT REPRODUIT dans un vrai navigateur (11/11/2026). Au clic, la carte
  // revenait IDENTIQUE au caractère près, sans un mot :
  //     avant : « Reçois les rappels de cours | Activer »
  //     après : « Reçois les rappels de cours | Activer »
  // `assurerAbonnementPush` calcule pourtant un `motif` d'échec — il était
  // JETÉ. Et en cas de SUCCÈS la carte disparaissait sans rien confirmer.
  // Des deux côtés, la personne voyait « rien ne se passe ».
  //
  // ON NE MONTRE « ACTIVÉS » QUE SI L'ABONNEMENT EXISTE VRAIMENT (`r.abonne`).
  // Une permission accordée sans abonnement n'est PAS un succès : annoncer le
  // contraire serait une fausse confirmation, et la personne ne recevrait
  // jamais ses rappels en croyant le contraire.
  const activer = useCallback(async () => {
    if (occupe) return;
    setOccupe(true);
    setEchec(null);
    try {
      const r = await activerNotifications({ participantId, role, email });
      setEtat(r.abonne ? 'ok' : (r.etat === 'granted' ? 'granted_sans_abonnement' : r.etat));
      if (r.abonne) {
        setConfirme(true);
      } else {
        setEchec(messageEchec(r));
      }
    } catch (err) {
      setEchec("La réactivation n'a pas abouti. Réessaie dans un instant.");
    } finally {
      setOccupe(false);
    }
  }, [occupe, participantId, role, email]);

  // V548 : quand tout fonctionne, la carte ne montre RIEN — la réconciliation
  // ci-dessus a déjà tourné, silencieusement. Elle n'apparaît que lorsqu'une
  // action de l'abonné est nécessaire, et alors en UNE ligne compacte.
  // V669 — LA CONFIRMATION EXISTE ENFIN. Elle n'apparaît qu'après un succès
  // CONSTATÉ, et seulement si c'est ce clic-ci qui l'a produit : la
  // réconciliation silencieuse du début, elle, ne doit toujours rien afficher.
  if (confirme) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
                    border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.28)',
                    borderRadius: 12, padding: '10px 12px',
                    background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.06)' }}
           data-testid="carte-notifications-confirme">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
             stroke="var(--primary-color, #D91CD2)" strokeWidth="2.2"
             strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
             style={{ flexShrink: 0 }}>
          <path d="M20 6 9 17l-5-5" />
        </svg>
        <span style={{ color: '#fff', fontSize: 13, fontWeight: 600 }}>Rappels activés</span>
      </div>
    );
  }

  if (etat === 'inconnu' || etat === 'non_supporte' || etat === 'ok') {
    // Un échec sur un appareil qui ne SAIT PAS recevoir de notifications doit
    // quand même s'expliquer — sinon le clic reste sans réponse.
    if (!echec) return null;
  }

  const CADRE = {
    display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
    border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.28)',
    borderRadius: 12, padding: '10px 12px',
    background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.06)',
  };
  const cloche = (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
         stroke="var(--primary-color, #D91CD2)" strokeWidth="1.8"
         strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
         style={{ flexShrink: 0 }}>
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );

  if (etat === 'denied') {
    // Redemander est impossible (le navigateur l'interdit) : une ligne qui
    // dit OÙ agir, sans bouton inutile.
    return (
      <div style={CADRE} data-testid="carte-notifications">
        {cloche}
        <span style={{ flex: '1 1 180px', minWidth: 0, color: 'rgba(255,255,255,0.8)', fontSize: 12, lineHeight: 1.4 }}>
          Notifications désactivées : réautorise-les dans les réglages de ton navigateur pour recevoir les rappels.
        </span>
      </div>
    );
  }

  // 'default' (jamais demandé) ou 'granted_sans_abonnement' (permission
  // accordée mais l'abonnement n'a pas pu être recréé — un clic le retente).
  const premiere = etat === 'default';
  // V669 — l'explication de l'échec, s'il y en a eu un.
  const ligneEchec = echec ? (
    <span data-testid="carte-notifications-echec"
          style={{ flex: '1 1 100%', color: 'rgba(255,255,255,0.78)', fontSize: 12,
                   lineHeight: 1.45, marginTop: 2 }}>
      {echec}
    </span>
  ) : null;
  return (
    <div style={CADRE} data-testid="carte-notifications">
      {cloche}
      <span style={{ flex: '1 1 160px', minWidth: 0, color: '#fff', fontSize: 13, fontWeight: 600, lineHeight: 1.3 }}>
        {premiere ? 'Reçois les rappels de cours' : 'Rappels de cours à réactiver'}
      </span>
      <button
        type="button"
        onClick={activer}
        disabled={occupe}
        data-testid="carte-notifications-activer"
        aria-label={premiere ? 'Activer les notifications' : 'Réactiver les notifications'}
        style={{
          padding: '8px 14px', borderRadius: 10, border: 'none', cursor: occupe ? 'wait' : 'pointer',
          background: 'var(--primary-color, #D91CD2)', color: '#fff',
          fontSize: 13, fontWeight: 700, opacity: occupe ? 0.7 : 1, flexShrink: 0,
        }}
      >
        {occupe ? 'Activation…' : (premiere ? 'Activer' : 'Réactiver')}
      </button>
      {ligneEchec}
    </div>
  );
}
