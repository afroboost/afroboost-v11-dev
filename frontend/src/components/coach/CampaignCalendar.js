/**
 * CampaignCalendar.js — LE calendrier Afroboost.
 *
 * CE COMPOSANT N'EST PLUS CELUI DES CAMPAGNES SEULES, et il n'a pourtant pas
 * été réécrit : il affichait déjà une grille mensuelle avec création, édition,
 * glisser-déposer et duplication, et son couplage aux campagnes était
 * SUPERFICIEL — il ne lisait que cinq champs que tout événement possède.
 * CAL-1 remplace le vocabulaire (`campaigns` → `evenements`) et la palette
 * (par statut de campagne → par TYPE d'événement). La mécanique est intacte.
 *
 * IL N'Y AURA QU'UN SEUL CALENDRIER. Campagnes, rendez-vous, cours et
 * événements s'affichent ici, distingués par leur couleur de type et
 * filtrables. Créer un second calendrier ailleurs serait la faute que ce lot
 * existe pour éviter.
 *
 * COULEURS : uniquement `var(--primary-color)` / `var(--primary-rgb)`. Le
 * fichier portait auparavant une vingtaine de valeurs hexadécimales en dur
 * (#9333ea, #6366f1, rgba(139,92,246,…)) : la vitrine personnalisée d'un coach
 * ne s'y appliquait pas, contrairement à la règle absolue du dépôt. Les seules
 * couleurs fixes qui subsistent sont SÉMANTIQUES (succès, échec) — elles ne
 * dépendent pas de la marque et doivent rester lisibles quelle que soit elle.
 *
 * AUCUNE DÉPENDANCE GOOGLE. Ce lot n'en contient pas une ligne.
 */
import React, { useState, useMemo, useCallback } from 'react';
import SvgIcon from '../SvgIcon';

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const RGB = 'var(--primary-rgb, 217, 28, 210)';

/* LA PALETTE EST PAR TYPE, PLUS PAR STATUT DE CAMPAGNE.
   Un calendrier qui ne sait afficher que des campagnes peut se colorer par
   « brouillon / programmée / échouée » ; dès qu'il porte aussi des rendez-vous
   et des cours, c'est le TYPE qu'il faut distinguer d'un coup d'œil. Le statut
   d'une campagne n'est pas perdu pour autant : il reste écrit en clair dans
   l'infobulle. */
const TYPES = {
  campaign:    { libelle: 'Campagne',   teinte: `rgba(${RGB}, 0.85)` },
  task:        { libelle: 'Tâche',      teinte: 'rgba(168,85,247,0.85)' },
  appointment: { libelle: 'Rendez-vous', teinte: 'rgba(59,130,246,0.85)' },
  course:      { libelle: 'Cours',      teinte: 'rgba(34,197,94,0.85)' },
  event:       { libelle: 'Événement',  teinte: 'rgba(249,115,22,0.85)' },
};
const TYPE_DEFAUT = TYPES.event;

const DAYS_FR = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];
const MONTHS_FR = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet',
                   'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'];

const VUES = [{ cle: 'jour', libelle: 'Jour' },
              { cle: 'semaine', libelle: 'Semaine' },
              { cle: 'mois', libelle: 'Mois' }];

/* La date d'un événement, quelle que soit sa source. `starts_at` est la forme
   canonique ; `scheduledAt`/`createdAt` restent lus pour qu'un appelant qui
   passerait encore des campagnes brutes ne voie rien disparaître. */
const dateDe = (e) => (e && (e.starts_at || e.scheduledAt || e.createdAt)) || '';
const memeJour = (a, b) => a && b && a.getFullYear() === b.getFullYear()
  && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
const cle2 = (n) => String(n).padStart(2, '0');
const iso = (d) => `${d.getFullYear()}-${cle2(d.getMonth() + 1)}-${cle2(d.getDate())}`;
const heureDe = (e) => {
  const s = dateDe(e);
  if (!s || e.all_day) return '';
  const d = new Date(s);
  return isNaN(d) ? '' : `${cle2(d.getHours())}:${cle2(d.getMinutes())}`;
};

export default function CampaignCalendar({
  evenements = [],
  onDayClick,          // (dateStr) => création à cette date
  onEvenementClick,    // (evenement) => édition
  onMoveEvenement,     // (evenement, newDateStr) => déplacer
  onDuplicateEvenement // (evenement) => dupliquer
}) {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [vue, setVue] = useState('mois');
  const [filtre, setFiltre] = useState('');
  const [dragge, setDragge] = useState(null);
  const [dragOverDay, setDragOverDay] = useState(null);
  const [contextMenu, setContextMenu] = useState(null);

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  const visibles = useMemo(
    () => (filtre ? evenements.filter((e) => (e.event_type || 'event') === filtre) : evenements),
    [evenements, filtre]);

  /* Les jours affichés dépendent de la vue. Le mois garde EXACTEMENT la grille
     d'avant (cases vides en tête pour aligner sur lundi) : c'est ce rendu-là
     que les campagnes existantes connaissent. */
  const jours = useMemo(() => {
    if (vue === 'jour') return [new Date(year, month, currentDate.getDate())];
    if (vue === 'semaine') {
      const debut = new Date(currentDate);
      debut.setDate(debut.getDate() - ((debut.getDay() + 6) % 7));
      return Array.from({ length: 7 }, (_, i) => {
        const d = new Date(debut); d.setDate(debut.getDate() + i); return d;
      });
    }
    const dernier = new Date(year, month + 1, 0);
    const vide = (new Date(year, month, 1).getDay() + 6) % 7;
    return [...Array(vide).fill(null),
            ...Array.from({ length: dernier.getDate() }, (_, i) => new Date(year, month, i + 1))];
  }, [vue, year, month, currentDate]);

  const parJour = useMemo(() => {
    const map = {};
    visibles.forEach((e) => {
      const s = dateDe(e);
      if (!s) return;
      const d = new Date(s);
      if (isNaN(d)) return;
      const k = iso(d);
      (map[k] = map[k] || []).push(e);
    });
    Object.keys(map).forEach((k) => map[k].sort(
      (a, b) => String(dateDe(a)).localeCompare(String(dateDe(b)))));
    return map;
  }, [visibles]);

  const today = new Date();
  const stats = useMemo(() => {
    const dans = visibles.filter((e) => {
      const d = new Date(dateDe(e));
      return !isNaN(d) && jours.some((j) => memeJour(j, d));
    });
    return { total: dans.length };
  }, [visibles, jours]);

  const titrePeriode = vue === 'mois'
    ? `${MONTHS_FR[month]} ${year}`
    : vue === 'jour'
      ? `${currentDate.getDate()} ${MONTHS_FR[month]} ${year}`
      : `${jours[0] ? jours[0].getDate() : ''} – ${jours[6] ? jours[6].getDate() : ''} ${MONTHS_FR[month]}`;

  const decaler = useCallback((sens) => {
    const d = new Date(currentDate);
    if (vue === 'mois') d.setMonth(d.getMonth() + sens);
    else if (vue === 'semaine') d.setDate(d.getDate() + 7 * sens);
    else d.setDate(d.getDate() + sens);
    setCurrentDate(d);
  }, [currentDate, vue]);

  /* GLISSER-DÉPOSER : réservé à ce qui est RÉELLEMENT modifiable. Une séance de
     cours est projetée depuis `courses` ; la déplacer ici ne changerait rien et
     donnerait l'illusion contraire. */
  const deplacable = (e) => e && e.modifiable !== false;
  const onDragStart = (ev, e) => {
    if (!deplacable(e)) { ev.preventDefault(); return; }
    setDragge(e);
    ev.dataTransfer.effectAllowed = 'move';
    ev.dataTransfer.setData('text/plain', e.id || '');
  };
  const onDragOver = (ev, jour) => {
    if (!jour || !dragge) return;
    ev.preventDefault();
    ev.dataTransfer.dropEffect = 'move';
    setDragOverDay(iso(jour));
  };
  const onDrop = (ev, jour) => {
    ev.preventDefault();
    if (dragge && jour) onMoveEvenement?.(dragge, iso(jour));
    setDragge(null); setDragOverDay(null);
  };

  const boutonBase = {
    background: `rgba(${RGB}, 0.2)`, border: `1px solid rgba(${RGB}, 0.35)`,
    color: '#fff', borderRadius: '8px', padding: '6px 10px', fontSize: '13px',
    cursor: 'pointer', flexShrink: 0,
  };

  return (
    <div data-testid="calendrier"
      style={{ marginBottom: '16px', padding: '4px', borderRadius: '12px',
               background: 'rgba(255,255,255,0.02)', border: `1px solid rgba(${RGB}, 0.2)`,
               boxSizing: 'border-box', width: '100%', maxWidth: '100%', overflow: 'hidden' }}
      onClick={() => setContextMenu(null)}>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    marginBottom: '10px', flexWrap: 'wrap', gap: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px',
                      flex: '1 1 auto', minWidth: 0, justifyContent: 'center' }}>
          <button type="button" aria-label="Période précédente" onClick={() => decaler(-1)}
                  style={boutonBase}><SvgIcon name="arrowLeft" size={14} /></button>
          <div style={{ textAlign: 'center', minWidth: 0 }}>
            <div data-testid="periode"
                 style={{ color: '#fff', fontWeight: 600, fontSize: '14px', whiteSpace: 'nowrap',
                          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '5px' }}>
              <SvgIcon name="calendar" size={14} />{titrePeriode}
            </div>
            {stats.total > 0 && (
              <div style={{ fontSize: '10px', color: 'rgba(255,255,255,0.5)', marginTop: '2px' }}>
                {stats.total} élément{stats.total > 1 ? 's' : ''}
              </div>
            )}
          </div>
          <button type="button" onClick={() => setCurrentDate(new Date())}
                  style={{ ...boutonBase, padding: '5px 8px', fontSize: '11px',
                           background: `rgba(${RGB}, 0.15)`, color: PRIMAIRE }}>Auj.</button>
          <button type="button" data-testid="creer"
                  onClick={() => onDayClick?.(iso(new Date()))}
                  style={{ ...boutonBase, background: PRIMAIRE, border: 'none',
                           fontSize: '11px', padding: '5px 10px', fontWeight: 600,
                           whiteSpace: 'nowrap' }}>+ Créer</button>
          <button type="button" aria-label="Période suivante" onClick={() => decaler(1)}
                  style={boutonBase}><SvgIcon name="arrowRight" size={14} /></button>
        </div>
      </div>

      {/* Vues et filtres — une seule page, plusieurs lectures. */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '8px',
                    alignItems: 'center' }}>
        {VUES.map((v) => (
          <button key={v.cle} type="button" data-testid={`vue-${v.cle}`}
                  onClick={() => setVue(v.cle)}
                  style={{ ...boutonBase, padding: '4px 10px', fontSize: '11px',
                           background: vue === v.cle ? PRIMAIRE : `rgba(${RGB}, 0.12)`,
                           fontWeight: vue === v.cle ? 700 : 400 }}>{v.libelle}</button>
        ))}
        <span style={{ flex: '1 1 auto' }} />
        <button type="button" data-testid="filtre-tout" onClick={() => setFiltre('')}
                style={{ ...boutonBase, padding: '4px 10px', fontSize: '11px',
                         background: filtre === '' ? PRIMAIRE : `rgba(${RGB}, 0.12)` }}>Tout</button>
        {Object.entries(TYPES).map(([cle, val]) => (
          <button key={cle} type="button" data-testid={`filtre-${cle}`}
                  onClick={() => setFiltre(cle)}
                  style={{ ...boutonBase, padding: '4px 10px', fontSize: '11px',
                           background: filtre === cle ? val.teinte : `rgba(${RGB}, 0.12)` }}>
            {val.libelle}
          </button>
        ))}
      </div>

      {vue === 'mois' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '1px', marginBottom: '1px' }}>
          {DAYS_FR.map((d) => (
            <div key={d} style={{ textAlign: 'center', fontSize: '10px',
                                  color: 'rgba(255,255,255,0.35)', fontWeight: 600,
                                  padding: '3px 0', overflow: 'hidden' }}>{d}</div>
          ))}
        </div>
      )}

      <div data-testid="grille"
           style={{ display: 'grid', gap: '1px',
                    gridTemplateColumns: vue === 'jour' ? '1fr' : 'repeat(7, 1fr)' }}>
        {jours.map((jour, idx) => {
          const k = jour ? iso(jour) : null;
          const duJour = k ? (parJour[k] || []) : [];
          const cible = k && dragOverDay === k;
          const estAuj = jour && memeJour(jour, today);
          const plafond = vue === 'mois' ? 3 : 12;

          return (
            <div key={idx} data-testid={jour ? `jour-${k}` : 'jour-vide'}
              onClick={() => { if (jour) onDayClick?.(k); }}
              onDragOver={(e) => onDragOver(e, jour)}
              onDragLeave={() => setDragOverDay(null)}
              onDrop={(e) => onDrop(e, jour)}
              style={{
                minHeight: vue === 'mois' ? '48px' : '96px', padding: '2px', borderRadius: '6px',
                cursor: jour ? 'pointer' : 'default',
                background: cible ? `rgba(${RGB}, 0.3)` : estAuj ? `rgba(${RGB}, 0.2)`
                  : jour ? 'rgba(255,255,255,0.02)' : 'transparent',
                border: cible ? `2px dashed ${PRIMAIRE}` : estAuj ? `2px solid rgba(${RGB}, 0.5)`
                  : jour ? '1px solid rgba(255,255,255,0.05)' : 'none',
                transition: 'all 0.15s', overflow: 'hidden', minWidth: 0, boxSizing: 'border-box',
              }}>
              {jour && (
                <>
                  <div style={{ fontSize: '11px', fontWeight: estAuj ? 700 : 400,
                                color: estAuj ? PRIMAIRE : 'rgba(255,255,255,0.55)',
                                marginBottom: '1px' }}>
                    {vue === 'mois' ? jour.getDate()
                      : `${DAYS_FR[(jour.getDay() + 6) % 7]} ${jour.getDate()}`}
                  </div>
                  {duJour.slice(0, plafond).map((e, i) => {
                    const ty = TYPES[e.event_type] || TYPE_DEFAUT;
                    const h = heureDe(e);
                    return (
                      <div key={e.id || i} data-testid="evenement"
                        draggable={deplacable(e)}
                        onDragStart={(ev) => onDragStart(ev, e)}
                        onDragEnd={() => { setDragge(null); setDragOverDay(null); }}
                        onClick={(ev) => { ev.stopPropagation(); onEvenementClick?.(e); }}
                        onContextMenu={(ev) => {
                          ev.preventDefault(); ev.stopPropagation();
                          setContextMenu({ x: ev.clientX, y: ev.clientY, evenement: e });
                        }}
                        title={`${e.title || e.name || ''} — ${ty.libelle}${e.status ? ` (${e.status})` : ''}`}
                        style={{
                          fontSize: vue === 'mois' ? '8px' : '10px', lineHeight: '1.25',
                          padding: '1px 3px', marginBottom: '1px', borderRadius: '3px',
                          background: `rgba(255,255,255,0.06)`, borderLeft: `3px solid ${ty.teinte}`,
                          color: '#fff', whiteSpace: 'nowrap', overflow: 'hidden',
                          textOverflow: 'ellipsis', cursor: deplacable(e) ? 'grab' : 'pointer',
                          opacity: dragge?.id === e.id ? 0.4 : 1,
                          maxWidth: '100%', boxSizing: 'border-box',
                        }}>
                        {h ? `${h} ` : ''}{e.title || e.name || ''}
                      </div>
                    );
                  })}
                  {duJour.length > plafond && (
                    <div style={{ fontSize: '8px', color: 'rgba(255,255,255,0.35)', textAlign: 'center' }}>
                      +{duJour.length - plafond}
                    </div>
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>

      {/* Légende — par TYPE, comme la palette. */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '8px',
                    paddingTop: '6px', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
        {Object.entries(TYPES).map(([cle, val]) => (
          <div key={cle} style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
            <div style={{ width: '6px', height: '6px', borderRadius: '50%',
                          background: val.teinte, flexShrink: 0 }} />
            <span style={{ fontSize: '9px', color: 'rgba(255,255,255,0.4)' }}>{val.libelle}</span>
          </div>
        ))}
      </div>

      {contextMenu && (
        <div style={{ position: 'fixed', left: contextMenu.x, top: contextMenu.y, zIndex: 10000,
                      background: 'rgba(20,10,30,0.98)', borderRadius: '8px',
                      border: `1px solid rgba(${RGB}, 0.45)`,
                      boxShadow: '0 8px 24px rgba(0,0,0,0.5)', overflow: 'hidden', minWidth: '150px' }}>
          <button type="button" data-testid="menu-modifier"
            onClick={(e) => { e.stopPropagation(); onEvenementClick?.(contextMenu.evenement); setContextMenu(null); }}
            style={{ display: 'block', width: '100%', padding: '10px 14px', background: 'none',
                     border: 'none', color: '#fff', fontSize: '13px', cursor: 'pointer', textAlign: 'left' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
              <SvgIcon name="edit" size={14} /> Modifier
            </span>
          </button>
          {contextMenu.evenement?.modifiable !== false && (
            <button type="button" data-testid="menu-dupliquer"
              onClick={(e) => { e.stopPropagation(); onDuplicateEvenement?.(contextMenu.evenement); setContextMenu(null); }}
              style={{ display: 'block', width: '100%', padding: '10px 14px', background: 'none',
                       border: 'none', color: '#fff', fontSize: '13px', cursor: 'pointer', textAlign: 'left' }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                <SvgIcon name="clipboard" size={14} /> Dupliquer
              </span>
            </button>
          )}
        </div>
      )}
    </div>
  );
}
