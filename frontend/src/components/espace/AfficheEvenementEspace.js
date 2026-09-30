/**
 * V565 — L'AFFICHE ÉVÉNEMENT DU COACH, EN LIGNE DANS L'ESPACE ABONNÉ.
 *
 * Aucune configuration propre : `evenement` est la projection, calculée par le
 * serveur, du concept du coach de CET abonné (ConceptEditor « Affiche Événement
 * (Popup d'accueil) »). Le média se lit comme sur la vitrine (utils/afficheEvenement).
 *
 * Carte en ligne, jamais une fenêtre : la réservation reste juste dessous.
 * Le X ne masque que dans CE navigateur, pour la session, et pour CETTE affiche
 * (`cle`) : une nouvelle affiche du coach réapparaît. Rien n'est écrit au serveur.
 */
import React, { useState } from 'react';
import { typeMediaAffiche, urlEmbedAffiche, libelleBoutonAffiche } from '../../utils/afficheEvenement';

export const CLE_AFFICHE_FERMEE = 'afroboost_affiche_espace_fermee';

function fermeeDansLaSession(cle) {
  try { return !!cle && window.sessionStorage.getItem(CLE_AFFICHE_FERMEE) === cle; } catch (e) { return false; }
}

const bouton = {
  background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.85)', color: 'white', border: 'none',
  padding: '10px 18px', minHeight: 44, borderRadius: 22, fontSize: '0.85rem', fontWeight: 600,
  cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6,
};

export default function AfficheEvenementEspace({ evenement, onReserver, onOffres }) {
  const cle = evenement && evenement.cle ? String(evenement.cle) : '';
  const [fermee, setFermee] = useState(() => fermeeDansLaSession(cle));
  const media = evenement && evenement.media_url ? String(evenement.media_url) : '';
  if (!media || fermee || fermeeDansLaSession(cle)) return null;

  const type = typeMediaAffiche(media);
  const embed = type === 'embed' ? urlEmbedAffiche(media) : null;
  if (type === 'embed' && !embed) return null;
  const libReserver = libelleBoutonAffiche(evenement.reserve_label, 'Réserver');
  const libOffres = libelleBoutonAffiche(evenement.offers_label, 'Nos offres');
  const fermer = () => {
    try { window.sessionStorage.setItem(CLE_AFFICHE_FERMEE, cle); } catch (e) { /* navigation privée */ }
    setFermee(true);
  };
  const styleMedia = { width: '100%', display: 'block', maxHeight: '70vh', objectFit: 'contain', background: 'black' };

  return (
    <section data-testid="espace-affiche-evenement" data-type={type} aria-label="Événement"
             className="rounded-2xl"
             style={{ position: 'relative', overflow: 'hidden', width: '100%', maxWidth: '100%',
               border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.35)' }}>
      {type === 'embed' ? (
        <div style={{ position: 'relative', width: '100%', aspectRatio: '16 / 9' }}>
          <iframe src={embed} title="Événement" data-testid="espace-affiche-video"
                  style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', border: 0 }}
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                  allowFullScreen />
        </div>
      ) : type === 'video' ? (
        <video src={media} style={styleMedia} autoPlay muted loop playsInline data-testid="espace-affiche-video" />
      ) : (
        <img src={media} alt="Événement" style={styleMedia} data-testid="espace-affiche-image"
             onError={(e) => { e.currentTarget.style.display = 'none'; }} />
      )}
      <button type="button" onClick={fermer} aria-label="Masquer l'événement" data-testid="espace-affiche-fermer"
              style={{ position: 'absolute', top: 8, right: 8, width: 36, height: 36, borderRadius: 18, border: 'none',
                background: 'rgba(0, 0, 0, 0.6)', color: 'white', cursor: 'pointer', display: 'flex',
                alignItems: 'center', justifyContent: 'center' }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
          <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
      {(libReserver && onReserver) || (libOffres && onOffres) ? (
        <div data-testid="espace-affiche-boutons"
             style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center', padding: '12px 12px 14px',
               background: 'rgba(0, 0, 0, 0.55)' }}>
          {libReserver && onReserver ? (
            <button type="button" style={bouton} onClick={onReserver} data-testid="espace-affiche-reserver">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2" /><line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" />
              </svg>
              {libReserver}
            </button>
          ) : null}
          {libOffres && onOffres ? (
            <button type="button" style={{ ...bouton, background: 'rgba(255, 255, 255, 0.14)' }} onClick={onOffres}
                    data-testid="espace-affiche-offres">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
                <line x1="7" y1="7" x2="7.01" y2="7" />
              </svg>
              {libOffres}
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
