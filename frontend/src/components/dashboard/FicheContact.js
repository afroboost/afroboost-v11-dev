/**
 * FicheContact — CONTACTS V2, temps 2
 *
 * Plein écran sur mobile, panneau latéral sur desktop — même composant.
 *
 * Elle ne montre QUE ce que les données permettent réellement. Aucun historique
 * n'est inventé : quand une information manque, elle est dite manquante plutôt
 * que remplacée par un tiret décoratif.
 *
 * « Inconnu » ne devient jamais « Autorisé ». C'est la règle du temps 1, et
 * elle se voit ici : le consentement est affiché à part des canaux, avec ses
 * propres mots.
 */
import { useState } from 'react';
import {
  libelleType, libelleStatut, libelleZone, drapeau, nomPays,
} from '../../utils/contactsAffichage';
import { TYPES_CONTACT } from '../../utils/contactType';

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const BORDURE = '1px solid rgba(255,255,255,0.10)';

const MOTS_CONSENT = {
  autorise: { texte: 'Autorisé', couleur: '#4ade80' },
  refuse: { texte: 'Refusé', couleur: '#f87171' },
  inconnu: { texte: 'Inconnu', couleur: 'rgba(255,255,255,0.45)' },
};

export default function FicheContact({ contact, estMobile, onFermer, onClasser }) {
  const [copie, setCopie] = useState('');
  if (!contact) return null;
  const c = contact;
  const canaux = c.canaux || {};
  const cons = c.consentement || {};

  const copier = async (valeur, quoi) => {
    try {
      await navigator.clipboard.writeText(valeur);
      setCopie(quoi);
      setTimeout(() => setCopie(''), 1600);
    } catch (e) { /* le presse-papiers peut être refusé : on ne casse rien */ }
  };

  const section = (titre, contenu) => (
    <div style={{ marginBottom: 18 }}>
      <p style={{ margin: '0 0 8px', color: 'rgba(255,255,255,0.45)', fontSize: 11,
                  textTransform: 'uppercase', letterSpacing: 0.6 }}>{titre}</p>
      {contenu}
    </div>
  );

  const ligne = (etiquette, valeur, action) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0',
                  borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
      <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12, minWidth: 92 }}>{etiquette}</span>
      <span style={{ color: valeur ? '#fff' : 'rgba(255,255,255,0.3)', fontSize: 13,
                     flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {valeur || 'Non renseigné'}
      </span>
      {action}
    </div>
  );

  // LOT 2 — L'ETAT MEMBRE, TEL QUE LE SERVEUR LE CALCULE.
  //
  // `adhesion.statut` est DEDUIT des dates par le serveur a chaque lecture, il
  // n'est jamais stocke (lecon V393 : un `status: active` perime laissait
  // reserver un forfait expire). On l'affiche, on ne le recalcule pas ici —
  // sinon deux verites cohabiteraient, celle du serveur et celle du navigateur.
  const MOTS_ADHESION = {
    active: { texte: 'Membre Afroboost', couleur: PRIMAIRE },
    future: { texte: 'Adhésion à venir', couleur: 'rgba(255,255,255,0.55)' },
    expiree: { texte: 'Adhésion expirée', couleur: 'rgba(255,255,255,0.45)' },
    invalide: { texte: 'Adhésion illisible', couleur: 'rgba(255,255,255,0.45)' },
  };

  const enDateSuisse = (iso) => {
    const v = String(iso || '').slice(0, 10);
    if (v.length !== 10) return '—';
    const [a, m, j] = v.split('-');
    return `${j}.${m}.${a}`;
  };

  const boutonCopier = (valeur, quoi) => valeur ? (
    <button type="button" data-testid={`copier-${quoi}`} onClick={() => copier(valeur, quoi)}
      style={{ padding: '4px 9px', borderRadius: 7, cursor: 'pointer', background: 'transparent',
               border: BORDURE, color: 'rgba(255,255,255,0.6)', fontSize: 11, minHeight: 30 }}>
      {copie === quoi ? 'Copié' : 'Copier'}
    </button>
  ) : null;

  const consentement = (canal, cle) => {
    const m = MOTS_CONSENT[cons[cle]] || MOTS_CONSENT.inconnu;
    return (
      <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0',
                    borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12 }}>{canal}</span>
        <span data-testid={`consent-${cle}`} style={{ color: m.couleur, fontSize: 12.5, fontWeight: 600 }}>
          {m.texte}
        </span>
      </div>
    );
  };

  const dispo = (libelle, ok) => (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0',
                  borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
      <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12 }}>{libelle}</span>
      <span style={{ color: ok ? '#4ade80' : 'rgba(255,255,255,0.3)', fontSize: 12.5 }}>
        {ok ? 'Oui' : 'Non'}
      </span>
    </div>
  );

  return (
    <div
      data-testid="fiche-contact"
      onClick={onFermer}
      style={{ position: 'fixed', inset: 0, zIndex: 9500, background: 'rgba(0,0,0,0.72)',
               display: 'flex', justifyContent: estMobile ? 'center' : 'flex-end' }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: '#0a0a1a', borderLeft: estMobile ? 'none' : BORDURE,
          // Deux valeurs simples plutot qu'une fonction CSS : `min()` n'est
          // pas interprete partout, et s'appuyer sur ce qu'un environnement
          // ne sait pas lire, c'est esperer plutot que savoir.
          width: estMobile ? '100%' : '440px',
          maxWidth: '100%',
          height: '100%', overflowY: 'auto', padding: 18, boxSizing: 'border-box',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
          <div style={{ minWidth: 0 }}>
            <h3 style={{ margin: 0, color: '#fff', fontSize: 17, fontWeight: 800,
                         overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {c.name || 'Sans nom'}
            </h3>
            <p style={{ margin: '4px 0 0', color: 'rgba(255,255,255,0.5)', fontSize: 12 }}>
              {libelleType(c)} · {libelleStatut(c)}
            </p>
          </div>
          <button type="button" data-testid="fiche-fermer" onClick={onFermer} aria-label="Fermer la fiche"
            style={{ background: 'none', border: 'none', color: '#fff', fontSize: 28,
                     lineHeight: 1, cursor: 'pointer', minHeight: 40, minWidth: 40 }}>
            ×
          </button>
        </div>

        {section('Identité', (
          <>
            {ligne('Nom', c.name)}
            {ligne('Email', c.email, boutonCopier(c.email, 'email'))}
            {ligne('Téléphone', c.whatsapp || c.phone, boutonCopier(c.whatsapp || c.phone, 'telephone'))}
            {ligne('Pays', c.pays
              ? `${drapeau(c) ? drapeau(c) + ' ' : ''}${nomPays(c.pays)}`
              : libelleZone(c))}
          </>
        ))}

        {section('Afroboost', (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0' }}>
              <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12, minWidth: 92 }}>Type</span>
              <select
                data-testid="fiche-type"
                aria-label="Type de contact"
                value={c.contact_type || ''}
                onChange={(e) => onClasser && onClasser(c.id, e.target.value)}
                style={{ flex: 1, minHeight: 38, padding: '7px 10px', borderRadius: 8,
                         background: '#12122a', color: '#fff', border: BORDURE,
                         fontSize: 16, outline: 'none' }}
              >
                <option value="">Non classé</option>
                {TYPES_CONTACT.map((t) => <option key={t.valeur} value={t.valeur}>{t.libelle}</option>)}
              </select>
            </div>
            {ligne('Statut', libelleStatut(c))}
            {c.source ? ligne('Source', c.source) : null}
          </>
        ))}

        {/* LOT 2 — ADHESION. La section n'apparait QUE si le serveur a renvoye
            quelque chose : pas d'adhesion, pas de bloc — plutot que d'afficher
            « aucune », qui laisserait croire a une information alors que c'est
            une absence. Aucun appel reseau ici : cette fiche est purement
            presentative, la donnee arrive avec le contact. */}
        {c.adhesion ? section('Adhésion', (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '2px 0 8px' }}>
              <span data-testid="fiche-adhesion-statut" style={{
                fontSize: 13, fontWeight: 700,
                color: (MOTS_ADHESION[c.adhesion.statut] || MOTS_ADHESION.invalide).couleur,
              }}>
                {(MOTS_ADHESION[c.adhesion.statut] || MOTS_ADHESION.invalide).texte}
              </span>
            </div>
            {c.adhesion.statut === 'active'
              ? ligne('Actif jusqu\u2019au', enDateSuisse(c.adhesion.date_fin))
              : ligne('Période', `${enDateSuisse(c.adhesion.date_debut)} \u2192 ${enDateSuisse(c.adhesion.date_fin)}`)}
            {ligne('Origine', c.adhesion.source === 'achat' ? 'Achat en ligne' : 'Saisie manuelle')}
          </>
        )) : null}

        {section('Canaux disponibles', (
          <>
            {dispo('Email', !!canaux.email)}
            {dispo('Téléphone', !!canaux.telephone)}
            {dispo('WhatsApp', !!canaux.whatsapp)}
          </>
        ))}

        {section('Consentement marketing', (
          <>
            <p style={{ margin: '0 0 6px', color: 'rgba(255,255,255,0.35)', fontSize: 10.5, lineHeight: 1.45 }}>
              Disposer d'un canal n'autorise pas à l'utiliser pour une campagne.
              Sans trace d'accord, l'état reste « Inconnu ».
            </p>
            {consentement('Email', 'email')}
            {consentement('WhatsApp', 'whatsapp')}
          </>
        ))}
      </div>
    </div>
  );
}
