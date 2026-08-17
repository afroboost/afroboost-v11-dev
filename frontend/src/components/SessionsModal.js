import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';

/**
 * SessionsModal — le calendrier des cours et evenements, en fenetre.
 *
 * Trois contraintes du depot ont dicte sa forme, et elles ne sont pas
 * negociables :
 *
 * 1. PORTAIL OBLIGATOIRE. `.fade-in-section` anime en `forwards` laisse un
 *    `transform` permanent, ce qui en fait le bloc conteneur de tout
 *    descendant `position: fixed`. Une modale rendue dedans serait piegee
 *    dans la section. Le depot a deja bute dessus (Publications.js) et l'a
 *    resolu par un portail vers `document.body` : on fait pareil.
 *
 * 2. LE VERROU DE DEFILEMENT DOIT ETRE EN `!important`. `App.css` pose
 *    `overflow-y: auto !important` sur `html, body` ; un `style.overflow =
 *    'hidden'` ordinaire serait ignore. Seule une declaration en ligne avec
 *    priorite `important` gagne. On memorise la position et on la restaure a
 *    la fermeture : c'est ce qui evite de perdre sa place dans la page.
 *
 * 3. AUCUNE DATE NE VIENT DU SERVEUR. Il n'existe pas de route publique qui
 *    expose les occurrences d'un cours ; elles sont donc calculees ici, a
 *    partir des cours deja charges. Un cours portant `date` est PONCTUEL et
 *    n'a qu'une occurrence ; sinon `weekday` le rend hebdomadaire — en
 *    convention JavaScript (dimanche = 0), la meme que `getDay()`.
 */

const JOURS_COURTS = ['dim.', 'lun.', 'mar.', 'mer.', 'jeu.', 'ven.', 'sam.'];
const JOURS_LONGS = ['dimanche', 'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi'];
const MOIS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin',
  'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'];

const ROSE = 'var(--primary-color, #D91CD2)';
const ROSE_RGB = 'var(--primary-rgb, 217, 28, 210)';

/** « 18:30 » et « 18h30 » sont acceptes, comme cote serveur. Sinon 09:00. */
export function lireHeure(brut) {
  const s = String(brut || '').trim().replace('h', ':');
  const m = s.match(/^(\d{1,2})(?::(\d{1,2}))?$/);
  if (!m) return { heure: 9, minute: 0 };
  const h = parseInt(m[1], 10);
  const mn = m[2] ? parseInt(m[2], 10) : 0;
  if (h < 0 || h > 23 || mn < 0 || mn > 59) return { heure: 9, minute: 0 };
  return { heure: h, minute: mn };
}

const memeJour = (a, b) => a.getFullYear() === b.getFullYear()
  && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

const cleJour = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

/**
 * Toutes les occurrences a venir, sur `jours` jours.
 *
 * Un cours ponctuel garde une tolerance de 2 h apres son debut — la meme que
 * le serveur : on ne fait pas disparaitre une seance de la liste a la minute
 * ou elle commence.
 */
export function occurrencesDesCours(cours, jours = 56, maintenant = new Date()) {
  const out = [];
  const limite = new Date(maintenant.getTime() + jours * 86400000);
  (cours || []).forEach((c) => {
    if (!c || c.archived === true || c.visible === false) return;
    const { heure, minute } = lireHeure(c.time);

    if (typeof c.date === 'string' && c.date.trim()) {
      const p = c.date.trim().slice(0, 10).split('-');
      if (p.length !== 3) return;
      const d = new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]), heure, minute);
      if (Number.isNaN(d.getTime())) return;
      if (d.getTime() < maintenant.getTime() - 2 * 3600000) return;
      out.push({ cours: c, quand: d, ponctuel: true });
      return;
    }

    const jsWeekday = Number(c.weekday);
    if (!Number.isInteger(jsWeekday) || jsWeekday < 0 || jsWeekday > 6) return;
    const depart = new Date(maintenant.getFullYear(), maintenant.getMonth(), maintenant.getDate());
    let ecart = jsWeekday - depart.getDay();
    if (ecart < 0) ecart += 7;
    const premier = new Date(depart.getFullYear(), depart.getMonth(), depart.getDate() + ecart, heure, minute);
    for (let d = new Date(premier); d <= limite; d.setDate(d.getDate() + 7)) {
      if (d.getTime() < maintenant.getTime()) continue;
      out.push({ cours: c, quand: new Date(d), ponctuel: false });
    }
  });
  out.sort((a, b) => a.quand - b.quand);
  return out;
}

const SessionsModal = ({ open, onClose, courses = [], onReserve }) => {
  const [mois, setMois] = useState(() => {
    const n = new Date();
    return new Date(n.getFullYear(), n.getMonth(), 1);
  });
  const [jourChoisi, setJourChoisi] = useState(null);
  const [detail, setDetail] = useState(null);
  const boite = useRef(null);
  const positionY = useRef(0);

  const occurrences = useMemo(() => occurrencesDesCours(courses), [courses]);

  const parJour = useMemo(() => {
    const m = new Map();
    occurrences.forEach((o) => {
      const k = cleJour(o.quand);
      if (!m.has(k)) m.set(k, []);
      m.get(k).push(o);
    });
    return m;
  }, [occurrences]);

  const fermer = useCallback(() => {
    setDetail(null);
    onClose();
  }, [onClose]);

  // Escape — le depot n'a pas de hook partage, on reprend le seul motif
  // existant (Publications.js), a l'identique.
  useEffect(() => {
    if (!open) return undefined;
    const surTouche = (e) => { if (e.key === 'Escape') fermer(); };
    window.addEventListener('keydown', surTouche);
    return () => window.removeEventListener('keydown', surTouche);
  }, [open, fermer]);

  // Verrou de defilement. `!important` est indispensable : App.css impose
  // `overflow-y: auto !important` sur html et body. On memorise la position
  // et on la rend telle quelle a la fermeture.
  useEffect(() => {
    if (!open) return undefined;
    positionY.current = window.scrollY || window.pageYOffset || 0;
    const html = document.documentElement;
    const corps = document.body;
    html.style.setProperty('overflow', 'hidden', 'important');
    corps.style.setProperty('overflow', 'hidden', 'important');
    return () => {
      html.style.removeProperty('overflow');
      corps.style.removeProperty('overflow');
      window.scrollTo(0, positionY.current);
    };
  }, [open]);

  // A l'ouverture, on se place sur le premier jour qui a quelque chose.
  useEffect(() => {
    if (!open) return;
    setDetail(null);
    const premiere = occurrences[0];
    if (premiere) {
      setJourChoisi(cleJour(premiere.quand));
      setMois(new Date(premiere.quand.getFullYear(), premiere.quand.getMonth(), 1));
    } else {
      setJourChoisi(null);
    }
  }, [open, occurrences]);

  useEffect(() => {
    if (open && boite.current) boite.current.focus();
  }, [open]);

  if (!open) return null;

  const aujourdHui = new Date();
  const premierDuMois = new Date(mois.getFullYear(), mois.getMonth(), 1);
  const decalage = (premierDuMois.getDay() + 6) % 7;   // grille commencant le lundi
  const nbJours = new Date(mois.getFullYear(), mois.getMonth() + 1, 0).getDate();
  const cases = [];
  for (let i = 0; i < decalage; i += 1) cases.push(null);
  for (let j = 1; j <= nbJours; j += 1) cases.push(new Date(mois.getFullYear(), mois.getMonth(), j));

  const duJour = jourChoisi ? (parJour.get(jourChoisi) || []) : [];

  const contenu = (
    <div
      onClick={fermer}
      data-testid="sessions-modal"
      style={{
        position: 'fixed', inset: 0, zIndex: 2147483000,
        background: 'rgba(0,0,0,0.85)',
        backdropFilter: 'blur(6px)', WebkitBackdropFilter: 'blur(6px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        /* Une gouttiere fine : sur telephone la fenetre occupe presque tout
           l'ecran, sur desktop elle reste une boite centree que la largeur
           maximale empeche de s'etaler. Aucun point de rupture — le depot
           n'en utilise sur aucun de ses overlays, et les unites fluides
           suffisent. */
        padding: 12
      }}
    >
      <div
        ref={boite}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label="Calendrier des sessions"
        onClick={(e) => e.stopPropagation()}
        className="glass neon-border"
        data-testid="sessions-modal-boite"
        style={{
          width: '100%',
          maxWidth: 560,
          /* Mobile : presque plein ecran, ancre en bas, coins arrondis en haut.
             Desktop : la marge automatique le recentre et il ne colle plus au
             bas. Une seule regle fluide, aucun point de rupture — c'est la
             convention du depot. */
          maxHeight: 'min(92vh, 860px)',
          height: 'auto',
          borderRadius: 20,
          display: 'flex', flexDirection: 'column',
          overflow: 'hidden',
          outline: 'none',
          animation: 'modalSlideIn 0.28s ease-out'
        }}
      >
        {/* En-tete */}
        <div style={{
          padding: '14px 16px 12px', flexShrink: 0,
          borderBottom: '1px solid rgba(255,255,255,0.08)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
            <h2 style={{ color: '#fff', fontSize: 16, fontWeight: 700, margin: 0 }}>
              {detail ? 'Détail de la session' : 'Sessions'}
            </h2>
            <button
              type="button"
              onClick={fermer}
              aria-label="Fermer"
              data-testid="sessions-fermer"
              style={{
                width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
                background: 'rgba(0,0,0,0.6)', border: 'none', color: '#fff',
                cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center'
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        </div>

        {/* Corps defilant */}
        <div className="sessions-scrollbar" style={{ overflowY: 'auto', padding: '14px 16px 20px', flex: 1 }}>
          {detail ? (
            <DetailSession
              occ={detail}
              onRetour={() => setDetail(null)}
              onReserve={() => { const c = detail.cours; fermer(); setTimeout(() => onReserve && onReserve(c), 60); }}
            />
          ) : occurrences.length === 0 ? (
            <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: 13, textAlign: 'center', padding: '24px 0' }}
               data-testid="sessions-vide">
              Aucune session programmée pour le moment.
            </p>
          ) : (
            <>
              {/* Navigation de mois */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                <BoutonMois
                  sens="précédent"
                  onClick={() => setMois(new Date(mois.getFullYear(), mois.getMonth() - 1, 1))}
                />
                <span style={{ color: '#fff', fontSize: 14, fontWeight: 600, textTransform: 'capitalize' }}
                      data-testid="sessions-mois">
                  {MOIS[mois.getMonth()]} {mois.getFullYear()}
                </span>
                <BoutonMois
                  sens="suivant"
                  onClick={() => setMois(new Date(mois.getFullYear(), mois.getMonth() + 1, 1))}
                />
              </div>

              {/* Grille */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 4, marginBottom: 14 }}>
                {['L', 'M', 'M', 'J', 'V', 'S', 'D'].map((j, i) => (
                  <div key={i} style={{ textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.4)', paddingBottom: 4 }}>{j}</div>
                ))}
                {cases.map((d, i) => {
                  if (!d) return <div key={`v${i}`} />;
                  const k = cleJour(d);
                  const combien = (parJour.get(k) || []).length;
                  const actif = k === jourChoisi;
                  const passe = d < new Date(aujourdHui.getFullYear(), aujourdHui.getMonth(), aujourdHui.getDate());
                  return (
                    <button
                      key={k}
                      type="button"
                      disabled={combien === 0}
                      onClick={() => setJourChoisi(k)}
                      data-testid={combien > 0 ? `sessions-jour-${k}` : undefined}
                      aria-label={`${d.getDate()} ${MOIS[d.getMonth()]}${combien ? ` — ${combien} session${combien > 1 ? 's' : ''}` : ''}`}
                      style={{
                        aspectRatio: '1 / 1', minHeight: 34, borderRadius: 8, position: 'relative',
                        border: memeJour(d, aujourdHui) ? `1px solid rgba(${ROSE_RGB}, 0.6)` : '1px solid transparent',
                        background: actif ? `rgba(${ROSE_RGB}, 0.28)` : (combien ? 'rgba(255,255,255,0.06)' : 'transparent'),
                        color: combien ? '#fff' : 'rgba(255,255,255,0.25)',
                        opacity: passe ? 0.35 : 1,
                        fontSize: 13, cursor: combien ? 'pointer' : 'default', padding: 0
                      }}
                    >
                      {d.getDate()}
                      {combien > 0 && (
                        <span style={{
                          position: 'absolute', bottom: 4, left: '50%', transform: 'translateX(-50%)',
                          width: 4, height: 4, borderRadius: '50%', background: ROSE
                        }} />
                      )}
                    </button>
                  );
                })}
              </div>

              {/* Sessions du jour choisi */}
              {duJour.length === 0 ? (
                <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12, textAlign: 'center', padding: '8px 0' }}>
                  Choisis un jour marqué d&rsquo;un point.
                </p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {duJour.map((o, i) => (
                    <button
                      key={`${o.cours.id}-${o.quand.getTime()}`}
                      type="button"
                      onClick={() => setDetail(o)}
                      data-testid={`sessions-occurrence-${i}`}
                      className="card-gradient"
                      style={{
                        textAlign: 'left', border: '1px solid rgba(255,255,255,0.07)',
                        borderRadius: 12, padding: '12px 14px', cursor: 'pointer', width: '100%'
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                        <span style={{ color: ROSE, fontSize: 15, fontWeight: 700 }}>
                          {String(o.quand.getHours()).padStart(2, '0')}:{String(o.quand.getMinutes()).padStart(2, '0')}
                        </span>
                        <span style={{ color: '#fff', fontSize: 14, fontWeight: 600 }}>
                          {o.cours.name || 'Séance'}
                        </span>
                      </div>
                      {(o.cours.locationName || o.cours.location) && (
                        <div style={{ color: 'rgba(255,255,255,0.55)', fontSize: 12, marginTop: 3 }}>
                          {o.cours.locationName || o.cours.location}
                        </div>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );

  return createPortal(contenu, document.body);
};

const BoutonMois = ({ sens, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    aria-label={`Mois ${sens}`}
    data-testid={`sessions-mois-${sens === 'suivant' ? 'suivant' : 'precedent'}`}
    style={{
      width: 30, height: 30, borderRadius: 8, background: 'rgba(255,255,255,0.06)',
      border: '1px solid rgba(255,255,255,0.1)', color: '#fff', cursor: 'pointer',
      display: 'flex', alignItems: 'center', justifyContent: 'center'
    }}
  >
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
         style={{ transform: sens === 'suivant' ? 'none' : 'rotate(180deg)' }}>
      <polyline points="9 18 15 12 9 6" />
    </svg>
  </button>
);

const DetailSession = ({ occ, onRetour, onReserve }) => {
  const d = occ.quand;
  const lieu = occ.cours.locationName || occ.cours.location || '';
  return (
    <div data-testid="sessions-detail">
      <button
        type="button"
        onClick={onRetour}
        data-testid="sessions-retour"
        style={{
          background: 'none', border: 'none', color: 'rgba(255,255,255,0.6)',
          fontSize: 12, cursor: 'pointer', padding: '0 0 12px', display: 'flex', alignItems: 'center', gap: 6
        }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="15 18 9 12 15 6" />
        </svg>
        Retour au calendrier
      </button>

      <h3 style={{ color: '#fff', fontSize: 18, fontWeight: 700, margin: '0 0 10px' }}>
        {occ.cours.name || 'Séance'}
      </h3>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 18 }}>
        <Ligne libelle="Quand">
          {JOURS_LONGS[d.getDay()]} {d.getDate()} {MOIS[d.getMonth()]} {d.getFullYear()}
          {' · '}
          <span style={{ color: ROSE, fontWeight: 700 }}>
            {String(d.getHours()).padStart(2, '0')}:{String(d.getMinutes()).padStart(2, '0')}
          </span>
        </Ligne>
        {lieu && <Ligne libelle="Où">{lieu}</Ligne>}
        <Ligne libelle="Type">
          {occ.ponctuel ? 'Événement — date unique' : `Chaque ${JOURS_LONGS[d.getDay()]}`}
        </Ligne>
      </div>

      <button
        type="button"
        onClick={onReserve}
        className="btn-primary"
        data-testid="sessions-reserver"
        style={{
          width: '100%', padding: '13px 16px', borderRadius: 12, border: 'none',
          color: '#fff', fontSize: 15, fontWeight: 700, cursor: 'pointer'
        }}
      >
        Réserver
      </button>
      <p style={{ color: 'rgba(255,255,255,0.45)', fontSize: 11, textAlign: 'center', marginTop: 10 }}>
        Tu choisiras tes dates après la réservation, dans ton espace.
      </p>
    </div>
  );
};

const Ligne = ({ libelle, children }) => (
  <div style={{ display: 'flex', gap: 10, fontSize: 13 }}>
    <span style={{ color: 'rgba(255,255,255,0.45)', minWidth: 52, flexShrink: 0 }}>{libelle}</span>
    <span style={{ color: 'rgba(255,255,255,0.85)' }}>{children}</span>
  </div>
);

export default SessionsModal;
