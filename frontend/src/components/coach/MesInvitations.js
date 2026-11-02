/**
 * V610e — « MES INVITATIONS » (tableau de bord coach, onglet Invitation & partage).
 *
 * La liste des invitations du coach (route EXISTANTE GET /api/referral/campaigns) :
 * miniature, titre, type, statut, date. Deux actions visibles au plus par carte
 * (« Modifier », « Copier le lien ») ; le reste dans « ⋯ » (voir la page,
 * statistiques de la chaîne, archiver). « + Nouvelle invitation » ouvre l'assistant
 * de création EXISTANT. Lecture UNE fois au montage, puis sur un geste.
 */
import React, { useCallback, useEffect, useState } from 'react';
import SvgIcon from '../SvgIcon';
import EditeurInvitation from './EditeurInvitation';
import InvitationModal from './InvitationModal';
import { copier } from '../../utils/parrainage';
import { listerInvitations, masquerInvitation, reactiverInvitation, dupliquerInvitation, donneesLiees, supprimerInvitation, restaurerInvitation, lireChaine, LIBELLES_TYPE, LIBELLES_STATUT } from '../../utils/invitationEdition';

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const rgbaP = (a) => `rgba(var(--primary-rgb, 217, 28, 210), ${a})`;
const btn = (plein) => ({ minHeight: 40, padding: '8px 14px', borderRadius: 10, fontSize: 13.5, fontWeight: 700, cursor: 'pointer',
  display: 'inline-flex', alignItems: 'center', gap: 6, color: 'rgba(255,255,255,0.97)',
  background: plein ? PRIMAIRE : 'rgba(255,255,255,0.07)', border: plein ? 'none' : `1px solid ${rgbaP(0.35)}` });

/**
 * V610g — LA miniature de l'invitation, dans la ligne : 1) celle choisie / capturée
 * (`image_url`), 2) la carte générée si elle s'affiche, 3) sinon seulement le fond violet.
 * Une image qui ne charge pas passe à la suivante (jamais un cadre cassé).
 */
export function sourcesVignette(inv) {
  const l = [];
  if (inv && inv.image_url && inv.image_source !== 'default') l.push(inv.image_url);
  if (inv && inv.card_url) l.push(inv.card_url);
  return l;
}
function Vignette({ inv }) {
  const sources = sourcesVignette(inv);
  const [i, setI] = useState(0);
  const src = sources[i];
  return (
    <div data-testid={`mes-inv-vignette-${inv.id}`} style={{ width: 96, height: 54, borderRadius: 8, overflow: 'hidden', flex: '0 0 auto',
      background: `linear-gradient(135deg, ${rgbaP(0.35)}, ${rgbaP(0.08)})` }}>
      {src ? <img key={src} src={src} alt="" width="96" height="54" loading="lazy" onError={() => setI((x) => x + 1)}
                  style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} /> : null}
    </div>
  );
}

function Carte({ inv, onModifier, onRafraichir }) {
  const [menu, setMenu] = useState(false);
  const [retour, setRetour] = useState('');
  const [stats, setStats] = useState(null);
  const quand = [inv.date_label, inv.time_label].filter(Boolean).join(' · ');
  const actif = inv.status === 'active';
  const copierLien = () => copier(inv.share_url).then((ok) => setRetour(ok ? 'Lien copié' : 'Copie impossible'));
  const voirStats = () => {
    setMenu(false);
    lireChaine(inv.id).then((c) => {
      const gens = {};
      (c.noeuds || []).forEach((n) => { gens[n.generation] = (gens[n.generation] || 0) + 1; });
      setStats({ total: c.total || 0, gens });
    }).catch(() => setStats({ total: null, gens: {} }));
  };
  // V610h — Masquer (hors ligne, rien supprimé) / Réactiver (mêmes ids, même lien).
  const [confirmerMasque, setConfirmerMasque] = useState(false);
  const [occupe, setOccupe] = useState(false);
  const masquee = inv.status === 'hidden';
  const detailErreur = (e, defaut) => {
    const d = e && e.response && e.response.data && e.response.data.detail;
    return typeof d === 'string' ? d : defaut;
  };
  const masquer = () => {
    setConfirmerMasque(false); setOccupe(true); setRetour('');
    masquerInvitation(inv.id).then(onRafraichir).catch((e) => setRetour(detailErreur(e, 'Masquage impossible.'))).finally(() => setOccupe(false));
  };
  const reactiver = () => {
    setMenu(false); setOccupe(true); setRetour('');
    reactiverInvitation(inv.id).then(onRafraichir).catch((e) => setRetour(detailErreur(e, 'Réactivation impossible.'))).finally(() => setOccupe(false));
  };
  // V610k — SUPPRIMER : toujours logique (archivée, restaurable) ; on dit si des données existent.
  // V610k : le menu ouvert est amené dans l'écran (une fois, à l'ouverture) — dernière carte comprise.
  const refMenu = useCallback((el) => { if (el && el.scrollIntoView) { try { el.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); } catch (e) { /* ignore */ } } }, []);
  const [suppression, setSuppression] = useState(null);     // null | { donnees } (confirmation ouverte)
  const ouvrirSuppression = () => {
    setMenu(false); setRetour('');
    setSuppression({ donnees: null });
    donneesLiees(inv.id).then((d) => setSuppression({ donnees: d })).catch(() => setSuppression({ donnees: { a_des_donnees: true } }));
  };
  const supprimer = () => {
    setSuppression(null); setOccupe(true);
    supprimerInvitation(inv.id).then(onRafraichir).catch((e) => setRetour(detailErreur(e, 'Suppression impossible.'))).finally(() => setOccupe(false));
  };
  const dupliquer = () => {
    setMenu(false); setOccupe(true); setRetour('');
    dupliquerInvitation(inv.id).then((copie) => { onRafraichir(); if (copie && copie.id) onModifier(copie.id); })
      .catch((e) => setRetour(detailErreur(e, 'Duplication impossible.'))).finally(() => setOccupe(false));
  };
  return (
    <div data-testid={`mes-inv-${inv.id}`} style={{ display: 'flex', gap: 12, padding: 12, borderRadius: 14, background: 'rgba(255,255,255,0.04)', minWidth: 0, boxSizing: 'border-box',
      border: '1px solid rgba(255,255,255,0.09)', position: 'relative', flexWrap: 'wrap' }}>
      <Vignette key={`${inv.image_url || ""}|${inv.version || 0}`} inv={inv} />
      <div style={{ flex: '1 1 180px', minWidth: 0 }}>
        <div style={{ fontWeight: 800, fontSize: 15, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{inv.title || LIBELLES_TYPE[inv.type]}</div>
        <div style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.6)' }}>
          {LIBELLES_TYPE[inv.type] || inv.type} · <span data-testid={`mes-inv-statut-${inv.id}`} style={{ color: actif ? PRIMAIRE : 'rgba(255,255,255,0.7)', fontWeight: 700 }}>{LIBELLES_STATUT[inv.status] || inv.status}</span>
          {quand ? ` · ${quand}` : ''}
        </div>
        {stats ? (
          <div data-testid={`mes-inv-stats-${inv.id}`} style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.75)', marginTop: 4 }}>
            {stats.total == null ? 'Statistiques indisponibles.' : `${stats.total} participant(s) via les liens personnels`}
            {stats.total ? ` — ${Object.keys(stats.gens).sort().map((g) => `génération ${g} : ${stats.gens[g]}`).join(', ')}` : ''}
          </div>
        ) : null}
        {retour ? <div role="status" style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.75)', marginTop: 4 }}>{retour}</div> : null}
        {confirmerMasque ? (
          <div role="alertdialog" data-testid={`mes-inv-masquer-confirmation-${inv.id}`} style={{ marginTop: 8, padding: 10, borderRadius: 10, background: rgbaP(0.1), border: `1px solid ${rgbaP(0.3)}`, fontSize: 13 }}>
            <div style={{ fontWeight: 700, marginBottom: 4 }}>Masquer cet événement ?</div>
            <div style={{ color: 'rgba(255,255,255,0.8)', marginBottom: 8 }}>Il ne sera plus visible ni réservable, mais les réservations, paiements, statistiques et liens existants seront conservés.</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button type="button" style={btn(false)} onClick={() => setConfirmerMasque(false)}>Annuler</button>
              <button type="button" style={btn(true)} onClick={masquer} disabled={occupe} data-testid={`mes-inv-masquer-ok-${inv.id}`}>Masquer</button>
            </div>
          </div>
        ) : null}
        {suppression ? (
          <div role="alertdialog" data-testid={`mes-inv-supprimer-confirmation-${inv.id}`} style={{ marginTop: 8, padding: 10, borderRadius: 10, background: 'rgba(255,120,110,0.08)', border: '1px solid rgba(255,140,130,0.35)', fontSize: 13 }}>
            <div style={{ fontWeight: 700, marginBottom: 4 }}>Supprimer cette invitation ?</div>
            <div style={{ color: 'rgba(255,255,255,0.8)', marginBottom: 6 }}>Elle ne sera plus visible dans Mes invitations. Les données historiques nécessaires seront conservées.</div>
            {suppression.donnees && suppression.donnees.a_des_donnees ? (
              <div data-testid={`mes-inv-supprimer-donnees-${inv.id}`} style={{ color: 'rgba(255,220,180,0.95)', marginBottom: 8 }}>
                Cette invitation contient des données. Elle sera archivée plutôt que supprimée définitivement.
              </div>
            ) : null}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button type="button" style={btn(false)} onClick={() => setSuppression(null)} data-testid={`mes-inv-supprimer-annuler-${inv.id}`}>Annuler</button>
              <button type="button" onClick={supprimer} disabled={occupe || !suppression.donnees} data-testid={`mes-inv-supprimer-ok-${inv.id}`}
                      style={Object.assign(btn(false), { background: 'rgba(220,60,50,0.9)', border: 'none', color: 'rgba(255,255,255,1)' })}>Supprimer</button>
            </div>
          </div>
        ) : null}
      </div>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginLeft: 'auto' }}>
        {masquee ? (
          <button type="button" style={btn(true)} onClick={reactiver} disabled={occupe} data-testid={`mes-inv-reactiver-${inv.id}`}><SvgIcon name="eye" size={15} /> Réactiver</button>
        ) : (
          <button type="button" style={btn(true)} onClick={() => onModifier(inv.id)} data-testid={`mes-inv-modifier-${inv.id}`}><SvgIcon name="edit" size={15} /> Modifier</button>
        )}
        {actif && inv.share_url ? <button type="button" style={btn(false)} onClick={copierLien} aria-label="Copier le lien"><SvgIcon name="link" size={15} /></button> : null}
        <button type="button" style={btn(false)} onClick={() => setMenu((m) => !m)} aria-expanded={menu} aria-label="Plus d'actions" data-testid={`mes-inv-plus-${inv.id}`}>
          <SvgIcon name="moreHorizontal" size={16} />
        </button>
      </div>
      {menu ? (
        // V610k : le menu s'ouvre DANS la carte (sous les boutons) — jamais coupé par le panneau,
        // quelle que soit la place de la carte ; cibles tactiles de 44 px.
        <div role="menu" ref={refMenu}
             style={{ flex: '1 1 100%', minWidth: 0, width: '100%', boxSizing: 'border-box', display: 'grid',
               gridTemplateColumns: 'repeat(auto-fit, minmax(min(150px, 100%), 1fr))', gap: 2,
               padding: 6, borderRadius: 12, background: 'rgb(26,10,31)', border: `1px solid ${rgbaP(0.35)}` }}>
          {actif && inv.share_url ? (
            <a role="menuitem" href={inv.share_url} target="_blank" rel="noopener noreferrer" onClick={() => setMenu(false)}
               style={{ minHeight: 44, boxSizing: 'border-box', display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', color: 'rgba(255,255,255,0.92)', textDecoration: 'none', fontSize: 14 }}>
              <SvgIcon name="externalLink" size={15} /> Voir la page
            </a>
          ) : null}
          {masquee ? (
            <button type="button" role="menuitem" onClick={() => { setMenu(false); onModifier(inv.id); }} data-testid={`mes-inv-modifier-menu-${inv.id}`}
                    style={{ width: '100%', minHeight: 44, display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', background: 'none', border: 'none', color: 'rgba(255,255,255,0.92)', fontSize: 14, cursor: 'pointer' }}>
              <SvgIcon name="edit" size={15} /> Modifier
            </button>
          ) : null}
          <button type="button" role="menuitem" onClick={dupliquer} disabled={occupe} data-testid={`mes-inv-dupliquer-${inv.id}`}
                  style={{ width: '100%', minHeight: 44, display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', background: 'none', border: 'none', color: 'rgba(255,255,255,0.92)', fontSize: 14, cursor: 'pointer' }}>
            <SvgIcon name="copy" size={15} /> Dupliquer
          </button>
          {actif ? (
            <button type="button" role="menuitem" onClick={() => { setMenu(false); setConfirmerMasque(true); }} data-testid={`mes-inv-masquer-${inv.id}`}
                    style={{ width: '100%', minHeight: 44, display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', background: 'none', border: 'none', color: 'rgba(255,255,255,0.92)', fontSize: 14, cursor: 'pointer' }}>
              <SvgIcon name="eyeOff" size={15} /> Masquer
            </button>
          ) : null}
          <button type="button" role="menuitem" onClick={voirStats} data-testid={`mes-inv-stats-bouton-${inv.id}`}
                  style={{ width: '100%', minHeight: 44, display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', background: 'none', border: 'none', color: 'rgba(255,255,255,0.92)', fontSize: 14, cursor: 'pointer' }}>
            <SvgIcon name="barChart" size={15} /> Statistiques
          </button>
          <button type="button" role="menuitem" onClick={ouvrirSuppression} data-testid={`mes-inv-supprimer-${inv.id}`}
                  style={{ width: '100%', minHeight: 44, display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', background: 'none', border: 'none', color: 'rgba(255,180,170,0.95)', fontSize: 14, cursor: 'pointer' }}>
            <SvgIcon name="trash" size={15} /> Supprimer
          </button>
        </div>
      ) : null}
    </div>
  );
}

/** V610k — la CORBEILLE : invitations supprimées / archivées (rien n'est effacé). Repliée ;
 *  chargée seulement à l'ouverture ; « Restaurer » les remet en BROUILLON (jamais republiées). */
function Corbeille({ version, onRestaure }) {
  const [ouvert, setOuvert] = useState(false);
  const [liste, setListe] = useState(null);
  const [retour, setRetour] = useState('');
  useEffect(() => {
    if (!ouvert) return undefined;
    let vivant = true;
    listerInvitations(true).then((l) => { if (vivant) setListe(l.filter((x) => x.status === 'archived')); }).catch(() => { if (vivant) setListe([]); });
    return () => { vivant = false; };
  }, [ouvert, version]);
  const restaurer = (id) => {
    setRetour('');
    restaurerInvitation(id).then(() => { setRetour('Invitation restaurée en brouillon.'); onRestaure(); })
      .catch((e) => setRetour((e && e.response && typeof e.response.data?.detail === 'string') ? e.response.data.detail : 'Restauration impossible.'));
  };
  return (
    <div data-testid="mes-inv-corbeille" style={{ marginTop: 14, borderTop: '1px solid rgba(255,255,255,0.08)' }}>
      <button type="button" onClick={() => setOuvert((v) => !v)} aria-expanded={ouvert} data-testid="mes-inv-corbeille-bouton"
              style={{ width: '100%', minHeight: 44, display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'none', border: 'none',
                color: 'rgba(255,255,255,0.7)', fontSize: 14, cursor: 'pointer', padding: '8px 0' }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}><SvgIcon name="trash" size={15} /> Corbeille</span>
        <SvgIcon name={ouvert ? 'arrowUp' : 'arrowDown'} size={15} />
      </button>
      {ouvert ? (
        <div style={{ display: 'grid', gap: 8, paddingBottom: 8 }}>
          {liste === null ? <p style={{ margin: 0, fontSize: 13, color: 'rgba(255,255,255,0.6)' }}>Chargement…</p> : null}
          {liste && liste.length === 0 ? <p style={{ margin: 0, fontSize: 13, color: 'rgba(255,255,255,0.6)' }}>La corbeille est vide.</p> : null}
          {(liste || []).map((x) => (
            <div key={x.id} data-testid={`mes-inv-corbeille-${x.id}`} style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', padding: '8px 10px', borderRadius: 10, background: 'rgba(255,255,255,0.03)' }}>
              <span style={{ flex: '1 1 160px', minWidth: 0, fontSize: 13.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {x.title || LIBELLES_TYPE[x.type]} <span style={{ color: 'rgba(255,255,255,0.5)' }}>· {LIBELLES_TYPE[x.type] || x.type}</span>
              </span>
              <button type="button" style={btn(false)} onClick={() => restaurer(x.id)} data-testid={`mes-inv-restaurer-${x.id}`}>Restaurer en brouillon</button>
            </div>
          ))}
          {retour ? <p role="status" style={{ margin: 0, fontSize: 13, color: 'rgba(255,255,255,0.75)' }}>{retour}</p> : null}
        </div>
      ) : null}
    </div>
  );
}

export default function MesInvitations({ API, onPartenaires }) {
  const [liste, setListe] = useState(null);
  const [erreur, setErreur] = useState('');
  const [edition, setEdition] = useState(null);
  const [creation, setCreation] = useState(false);
  const [versionListe, setVersionListe] = useState(0);
  const charger = useCallback(() => {
    setVersionListe((v) => v + 1);
    listerInvitations().then((l) => { setListe(l); setErreur(''); })
      .catch((e) => setErreur((e && e.response && (e.response.status === 401 || e.response.status === 403))
        ? 'Reconnecte-toi pour voir tes invitations.' : 'Invitations indisponibles pour le moment.'));
  }, []);
  useEffect(() => { charger(); }, [charger]);

  return (
    <div data-testid="mes-invitations" style={{ marginBottom: 16, color: 'rgba(255,255,255,0.96)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontWeight: 800, fontSize: 17 }}>Mes invitations</div>
          <div style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.6)' }}>Modifie textes, médias, date et tarifs sans rien casser des liens déjà partagés.</div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          {onPartenaires && (
            <button type="button" style={btn(false)} onClick={onPartenaires} data-testid="mes-inv-partenaires">
              <SvgIcon name="users" size={15} /> Partenaires
            </button>
          )}
          <button type="button" style={btn(true)} onClick={() => setCreation(true)} data-testid="mes-inv-nouvelle"><SvgIcon name="plus" size={15} /> Nouvelle invitation</button>
        </div>
      </div>
      {erreur ? <p role="alert" style={{ color: 'rgba(255,200,190,0.95)', fontSize: 14 }}>{erreur}</p> : null}
      {liste === null && !erreur ? <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: 14 }}>Chargement…</p> : null}
      {liste && liste.length === 0 ? <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: 14 }}>Aucune invitation pour le moment.</p> : null}
      {/* V610k : colonne bornée à la largeur disponible (avant : à 360 px la grille prenait la
          largeur du contenu — 404 px dans 314 — et le panneau rognait le bord droit des cartes). */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)', gap: 10 }}>
        {(liste || []).map((inv) => <Carte key={inv.id} inv={inv} onModifier={setEdition} onRafraichir={charger} />)}
      </div>
      <Corbeille version={versionListe} onRestaure={charger} />
      {edition ? <EditeurInvitation invitationId={edition} onClose={() => { setEdition(null); charger(); }} onEnregistre={charger} /> : null}
      {creation ? <InvitationModal isOpen={creation} API={API} onClose={() => { setCreation(false); charger(); }} /> : null}
    </div>
  );
}
