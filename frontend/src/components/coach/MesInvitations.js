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
import { listerInvitations, archiverInvitation, lireChaine, LIBELLES_TYPE, LIBELLES_STATUT } from '../../utils/invitationEdition';

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const rgbaP = (a) => `rgba(var(--primary-rgb, 217, 28, 210), ${a})`;
const btn = (plein) => ({ minHeight: 40, padding: '8px 14px', borderRadius: 10, fontSize: 13.5, fontWeight: 700, cursor: 'pointer',
  display: 'inline-flex', alignItems: 'center', gap: 6, color: 'rgba(255,255,255,0.97)',
  background: plein ? PRIMAIRE : 'rgba(255,255,255,0.07)', border: plein ? 'none' : `1px solid ${rgbaP(0.35)}` });

function Carte({ inv, onModifier, onRafraichir }) {
  const [menu, setMenu] = useState(false);
  const [retour, setRetour] = useState('');
  const [stats, setStats] = useState(null);
  const vignette = inv.image_url || inv.card_url;
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
  const [confirmerArchive, setConfirmerArchive] = useState(false);
  const archiver = () => {
    setConfirmerArchive(false);
    archiverInvitation(inv.id).then(onRafraichir).catch(() => setRetour('Archivage impossible.'));
  };
  return (
    <div data-testid={`mes-inv-${inv.id}`} style={{ display: 'flex', gap: 12, padding: 12, borderRadius: 14, background: 'rgba(255,255,255,0.04)',
      border: '1px solid rgba(255,255,255,0.09)', position: 'relative', flexWrap: 'wrap' }}>
      <div style={{ width: 96, height: 50, borderRadius: 8, overflow: 'hidden', background: rgbaP(0.15), flex: '0 0 auto' }}>
        {vignette ? <img src={vignette} alt="" width="96" height="50" loading="lazy" style={{ width: '100%', height: '100%', objectFit: 'cover' }} /> : null}
      </div>
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
        {confirmerArchive ? (
          <div role="alertdialog" style={{ marginTop: 8, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', fontSize: 13 }}>
            <span>Archiver ? Son lien ne s'ouvrira plus.</span>
            <button type="button" style={btn(false)} onClick={() => setConfirmerArchive(false)}>Annuler</button>
            <button type="button" style={btn(true)} onClick={archiver} data-testid={`mes-inv-archiver-ok-${inv.id}`}>Archiver</button>
          </div>
        ) : null}
      </div>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginLeft: 'auto' }}>
        <button type="button" style={btn(true)} onClick={() => onModifier(inv.id)} data-testid={`mes-inv-modifier-${inv.id}`}><SvgIcon name="edit" size={15} /> Modifier</button>
        {actif && inv.share_url ? <button type="button" style={btn(false)} onClick={copierLien} aria-label="Copier le lien"><SvgIcon name="link" size={15} /></button> : null}
        <button type="button" style={btn(false)} onClick={() => setMenu((m) => !m)} aria-expanded={menu} aria-label="Plus d'actions" data-testid={`mes-inv-plus-${inv.id}`}>
          <SvgIcon name="moreHorizontal" size={16} />
        </button>
      </div>
      {menu ? (
        <div role="menu" style={{ position: 'absolute', right: 12, top: 58, zIndex: 5, minWidth: 210, padding: 6, borderRadius: 12,
          background: 'rgb(26,10,31)', border: `1px solid ${rgbaP(0.35)}`, boxShadow: '0 10px 30px rgba(0,0,0,0.5)' }}>
          {actif && inv.share_url ? (
            <a role="menuitem" href={inv.share_url} target="_blank" rel="noopener noreferrer" onClick={() => setMenu(false)}
               style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', color: 'rgba(255,255,255,0.92)', textDecoration: 'none', fontSize: 14 }}>
              <SvgIcon name="externalLink" size={15} /> Voir la page
            </a>
          ) : null}
          <button type="button" role="menuitem" onClick={voirStats} data-testid={`mes-inv-stats-bouton-${inv.id}`}
                  style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', background: 'none', border: 'none', color: 'rgba(255,255,255,0.92)', fontSize: 14, cursor: 'pointer' }}>
            <SvgIcon name="barChart" size={15} /> Statistiques
          </button>
          <button type="button" role="menuitem" onClick={() => { setMenu(false); setConfirmerArchive(true); }} data-testid={`mes-inv-archiver-${inv.id}`}
                  style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', background: 'none', border: 'none', color: 'rgba(255,180,170,0.95)', fontSize: 14, cursor: 'pointer' }}>
            <SvgIcon name="archive" size={15} /> Archiver
          </button>
        </div>
      ) : null}
    </div>
  );
}

export default function MesInvitations({ API }) {
  const [liste, setListe] = useState(null);
  const [erreur, setErreur] = useState('');
  const [edition, setEdition] = useState(null);
  const [creation, setCreation] = useState(false);
  const charger = useCallback(() => {
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
        <button type="button" style={btn(true)} onClick={() => setCreation(true)} data-testid="mes-inv-nouvelle"><SvgIcon name="plus" size={15} /> Nouvelle invitation</button>
      </div>
      {erreur ? <p role="alert" style={{ color: 'rgba(255,200,190,0.95)', fontSize: 14 }}>{erreur}</p> : null}
      {liste === null && !erreur ? <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: 14 }}>Chargement…</p> : null}
      {liste && liste.length === 0 ? <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: 14 }}>Aucune invitation pour le moment.</p> : null}
      <div style={{ display: 'grid', gap: 10 }}>
        {(liste || []).map((inv) => <Carte key={inv.id} inv={inv} onModifier={setEdition} onRafraichir={charger} />)}
      </div>
      {edition ? <EditeurInvitation invitationId={edition} onClose={() => { setEdition(null); charger(); }} onEnregistre={charger} /> : null}
      {creation ? <InvitationModal isOpen={creation} API={API} onClose={() => { setCreation(false); charger(); }} /> : null}
    </div>
  );
}
