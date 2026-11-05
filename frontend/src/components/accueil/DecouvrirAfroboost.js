/**
 * V645.4k — « DÉCOUVRIR AFROBOOST » — panneau gauche du viewer de publications.
 *
 * PC UNIQUEMENT. Quand une publication est agrandie, le grand panneau noir à
 * gauche de la vidéo était presque vide (auteur + légende). On y met ce qui
 * transforme un spectateur en participant : la PROCHAINE séance réellement
 * réservable, puis les offres.
 *
 * AUCUNE DONNÉE INVENTÉE :
 *  - les séances viennent de `GET /api/sessions/agenda`, la source de vérité du
 *    calendrier (même route que SessionsModal). Elle applique déjà le fuseau
 *    Europe/Zurich, écarte le passé, saute `dates_annulees`, et ne montre
 *    qu'une séance ouverte par au moins une offre publique. On n'y recalcule
 *    donc RIEN — recalculer localement est précisément ce qui a produit, par le
 *    passé, des réservations datées de l'instant du clic.
 *  - les offres viennent de la liste déjà chargée par la vitrine, avec les
 *    mêmes critères qu'ailleurs : essai gratuit = `familleOffre === OFFERT`,
 *    offre mise en avant = l'aimant portant un compte à rebours, sinon le
 *    premier aimant (identique à la carte « offre du moment » de l'accueil).
 *
 * PLACES RESTANTES : volontairement absentes. Aucune route PUBLIQUE ne les
 * expose par séance (capacité et inscrits sont réservés au coach, 403 sinon) et
 * le dépôt interdit d'afficher une capacité devinée. Le jour où une route
 * publique existera, il suffira de renseigner `places` sur l'occurrence.
 *
 * Le conteneur parent (`lightbox-auteur`) porte déjà `stopPropagation` : les
 * clics d'ici ne ferment pas le viewer et n'atteignent pas la vidéo.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { normaliserAgenda, regrouperSeancesPhysiques } from '../SessionsModal';
import {
  FAMILLE, familleOffre, prixAffiche, badgeOffre, regrouperOffres, promesseCourte,
} from '../../utils/offresAimants';

const COULEUR = 'var(--primary-color, #D91CD2)';
const RGB = 'var(--primary-rgb, 217, 28, 210)';

// `body` porte une couleur sombre : tout texte qui hérite deviendrait noir sur
// noir. Chaque bloc de texte pose donc sa couleur explicitement.
const CARTE = {
  border: '1px solid rgba(255,255,255,0.12)',
  borderRadius: 14,
  background: 'rgba(255,255,255,0.03)',
  padding: '10px 12px',
};
const BOUTON_PLEIN = {
  width: '100%', minHeight: 38, marginTop: 9,
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 7,
  borderRadius: 999, border: 'none', background: COULEUR,
  color: 'var(--on-primary, #fff)', fontSize: 13.5, fontWeight: 700,
  cursor: 'pointer', padding: '0 14px',
};
const BOUTON_LEGER = {
  ...BOUTON_PLEIN,
  background: `rgba(${RGB}, 0.08)`,
  border: `1px solid rgba(${RGB}, 0.5)`,
  color: '#fff', fontWeight: 600,
};
const SURTITRE = {
  margin: '0 0 6px', color: 'rgba(255,255,255,0.45)',
  fontSize: 10.5, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase',
};

/** « Mercredi 5 novembre · 18:45 » en Europe/Zurich. */
export function libelleSeance(quand) {
  if (!(quand instanceof Date) || Number.isNaN(quand.getTime())) return '';
  const opt = { timeZone: 'Europe/Zurich' };
  const jour = quand.toLocaleDateString('fr-CH', { ...opt, weekday: 'long', day: 'numeric', month: 'long' });
  const heure = quand.toLocaleTimeString('fr-CH', { ...opt, hour: '2-digit', minute: '2-digit' });
  return `${jour.charAt(0).toUpperCase()}${jour.slice(1)} · ${heure}`;
}

/** L'offre mise en avant : même règle que la carte « offre du moment ». */
export function offreVedette(offres) {
  const groupes = regrouperOffres(offres || []);
  const aimant = (groupes.aimants || []).filter(
    (a) => a && a.offre && a.offre.countdown_enabled && a.offre.countdown_date,
  )[0] || (groupes.aimants || [])[0] || null;
  return aimant ? { offre: aimant.offre, badge: aimant.badge || badgeOffre(aimant.offre, groupes.mensuelRef, offres), mensuelRef: groupes.mensuelRef } : null;
}

export function offreEssai(offres) {
  return (offres || []).find((o) => familleOffre(o) === FAMILLE.OFFERT) || null;
}

function LigneInfo({ children }) {
  return (
    <p style={{ margin: '3px 0 0', color: 'rgba(255,255,255,0.62)', fontSize: 12.5, lineHeight: 1.45 }}>
      {children}
    </p>
  );
}

export default function DecouvrirAfroboost({ API, offres, onSeance, onOffre, onToutesLesOffres, onProgramme }) {
  const [seances, setSeances] = useState(null); // null = en cours, [] = aucune

  useEffect(() => {
    let vivant = true;
    (async () => {
      try {
        const r = await axios.get(`${API}/sessions/agenda`, { params: { days: 60 } });
        const brut = (r && r.data && r.data.occurrences) || [];
        if (vivant) setSeances(regrouperSeancesPhysiques(normaliserAgenda(brut))); // V647 : même nom que le calendrier
      } catch (e) {
        // Agenda indisponible : on n'invente aucune date, on propose le programme.
        if (vivant) setSeances([]);
      }
    })();
    return () => { vivant = false; };
  }, [API]);

  const prochaine = Array.isArray(seances) ? seances[0] : null;
  // Plusieurs cours peuvent partager le MÊME créneau : proposer « une autre
  // séance » à l'identique n'aurait aucun sens. On cherche donc le prochain
  // horaire réellement différent.
  const suivante = prochaine
    ? (seances || []).find((s) => s.quand.getTime() !== prochaine.quand.getTime()) || null
    : null;
  const essai = offreEssai(offres);
  const vedette = offreVedette(offres);
  // Ne pas proposer deux fois la même offre.
  const vedetteOffre = vedette && (!essai || vedette.offre.id !== essai.id) ? vedette : null;

  return (
    <div data-testid="decouvrir-afroboost" style={{ marginBottom: 12 }}>
      <p style={SURTITRE}>Découvrir Afroboost</p>

      {/* A — PROCHAIN COURS */}
      <div style={CARTE} data-testid="decouvrir-prochain-cours">
        {seances === null ? (
          <p style={{ margin: 0, color: 'rgba(255,255,255,0.5)', fontSize: 12.5 }}>Recherche de la prochaine séance…</p>
        ) : prochaine ? (
          <>
            <p style={{ margin: 0, color: '#fff', fontSize: 14.5, fontWeight: 700, lineHeight: 1.3 }}>
              {prochaine.nom}
            </p>
            <LigneInfo>
              <span data-testid="decouvrir-quand" style={{ color: COULEUR, fontWeight: 700 }}>
                {libelleSeance(prochaine.quand)}
              </span>
            </LigneInfo>
            {prochaine.lieu ? <LigneInfo>{prochaine.lieu}</LigneInfo> : null}
            {prochaine.places != null ? (
              <LigneInfo>{prochaine.places > 0 ? `${prochaine.places} places restantes` : 'Complet'}</LigneInfo>
            ) : null}
            <button
              type="button"
              style={BOUTON_PLEIN}
              data-testid="decouvrir-reserver"
              onClick={() => onSeance && onSeance(prochaine)}
            >
              Réserver ma place
            </button>
            {suivante ? (
              <button
                type="button"
                data-testid="decouvrir-autre-seance"
                onClick={() => onSeance && onSeance(suivante)}
                style={{
                  marginTop: 8, width: '100%', padding: 0, border: 'none', background: 'none',
                  color: 'rgba(255,255,255,0.55)', fontSize: 12, textDecoration: 'underline',
                  cursor: 'pointer', textAlign: 'center',
                }}
              >
                Une autre séance : {libelleSeance(suivante.quand)}
              </button>
            ) : null}
          </>
        ) : (
          <>
            <p style={{ margin: 0, color: '#fff', fontSize: 14, fontWeight: 600 }}>Aucune séance annoncée pour l'instant.</p>
            <button type="button" style={BOUTON_LEGER} data-testid="decouvrir-programme" onClick={() => onProgramme && onProgramme()}>
              Voir le programme
            </button>
          </>
        )}
      </div>

      {/* B — OFFRES */}
      {(essai || vedetteOffre) && (
        <div style={{ ...CARTE, marginTop: 8 }} data-testid="decouvrir-offres">
          {essai ? (
            <button
              type="button"
              data-testid="decouvrir-essai"
              onClick={() => onOffre && onOffre(essai)}
              style={{
                width: '100%', textAlign: 'left', padding: '9px 11px', borderRadius: 12,
                border: `1px solid rgba(${RGB}, 0.45)`, background: `rgba(${RGB}, 0.10)`,
                color: '#fff', cursor: 'pointer',
              }}
            >
              <span style={{ display: 'block', fontSize: 10.5, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: COULEUR }}>
                Premier cours offert
              </span>
              <span style={{ display: 'block', marginTop: 2, fontSize: 13.5, fontWeight: 700, color: '#fff' }}>{essai.name}</span>
            </button>
          ) : null}

          {vedetteOffre ? (
            <button
              type="button"
              data-testid="decouvrir-offre-vedette"
              onClick={() => onOffre && onOffre(vedetteOffre.offre)}
              style={{
                width: '100%', textAlign: 'left', marginTop: essai ? 8 : 0,
                padding: '9px 11px', borderRadius: 12,
                border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.04)',
                color: '#fff', cursor: 'pointer',
              }}
            >
              {vedetteOffre.badge ? (
                <span style={{ display: 'block', fontSize: 10.5, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'rgba(255,255,255,0.5)' }}>
                  {vedetteOffre.badge}
                </span>
              ) : null}
              <span style={{ display: 'flex', alignItems: 'baseline', gap: 7, marginTop: 2 }}>
                <span style={{ fontSize: 13.5, fontWeight: 700, color: '#fff' }}>{vedetteOffre.offre.name}</span>
                <span style={{ fontSize: 14, fontWeight: 800, color: COULEUR, whiteSpace: 'nowrap', marginLeft: 'auto' }}>
                  {prixAffiche(vedetteOffre.offre).montant}
                </span>
              </span>
              {promesseCourte(vedetteOffre.offre) ? (
                <span style={{ display: 'block', marginTop: 3, color: 'rgba(255,255,255,0.55)', fontSize: 12, lineHeight: 1.4 }}>
                  {promesseCourte(vedetteOffre.offre)}
                </span>
              ) : null}
            </button>
          ) : null}

          <button type="button" style={BOUTON_LEGER} data-testid="decouvrir-toutes-offres" onClick={() => onToutesLesOffres && onToutesLesOffres()}>
            Voir toutes les offres
          </button>
        </div>
      )}
    </div>
  );
}
