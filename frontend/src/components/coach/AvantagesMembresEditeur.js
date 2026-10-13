/**
 * V618M — ÉDITEUR « AVANTAGES MEMBRES » + « URGENCE / PLACES » d'un événement payant.
 * Offre par offre (identifiant réel) : Aucun avantage / Gratuit / Réduction % / Prix fixe.
 * Le serveur décide seul du prix ; ici, l'écran du coach et un aperçu du prix membre.
 * Couleurs : jetons du coach (`var(--primary-color)`) ; icônes SVG.
 */
import React, { useState } from 'react';
import SvgIcon from '../SvgIcon';
import { TYPES_AVANTAGE, TEXTE_URGENCE_MAX, prixMembreApercu, chf } from '../../utils/avantagesMembres';

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const rgbaP = (a) => `rgba(var(--primary-rgb, 217, 28, 210), ${a})`;
const champ = { width: '100%', minHeight: 44, borderRadius: 10, padding: '0 12px', boxSizing: 'border-box', fontSize: 15,
  background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.16)', color: 'rgba(255,255,255,0.95)' };
const carte = { padding: 12, borderRadius: 12, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.09)', marginBottom: 10 };
const aide = { fontSize: 12.5, color: 'rgba(255,255,255,0.6)', marginTop: 6 };

export function SectionAvantages({ evt, form, setForm, prixPublic, archivee }) {
  const [autres, setAutres] = useState(false);
  const [ajout, setAjout] = useState('');
  const a = (evt && evt.avantages) || {};
  const liste = form.avantages || [];
  const pris = new Set(liste.map((r) => r.offer_id));
  const choix = (a.offres || []).filter((o) => !pris.has(o.id));
  const choixAutres = (a.autres || []).filter((o) => !pris.has(o.id));
  const majListe = (fn) => setForm((p) => Object.assign({}, p, { avantages: fn(p.avantages || []) }));
  const majLigne = (i, k, v) => majListe((l) => l.map((r, j) => (j === i ? Object.assign({}, r, { [k]: v }) : r)));
  const ajouter = (id) => {
    if (!id) return;
    const o = (a.offres || []).concat(a.autres || []).find((x) => x.id === id);
    if (!o) return;
    majListe((l) => l.concat([{ offer_id: o.id, nom: o.nom, type: 'gratuit', valeur: '', active: (a.offres || []).some((x) => x.id === id) }]));
    setAjout('');
  };
  return (
    <div data-testid="ed-avantages">
      <p style={{ margin: '0 0 12px', fontSize: 13.5, color: 'rgba(255,255,255,0.8)' }}>
        Choisis, pour chaque offre, l'avantage de ses membres sur cet événement. Le serveur vérifie l'abonnement actuel
        de la personne connectée ; un ami invité paie toujours le tarif public.
      </p>
      {evt.membres ? (
        <label data-testid="ed-membres" style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12, cursor: archivee ? 'default' : 'pointer' }}>
          <input type="checkbox" checked={!!form.membres_actif} disabled={archivee} data-testid="ed-membres-case"
                 onChange={(e) => setForm((p) => Object.assign({}, p, { membres_actif: e.target.checked }))}
                 style={{ width: 22, height: 22, accentColor: 'var(--primary-color, #D91CD2)' }} />
          <span style={{ fontWeight: 700 }}>Avantages membres actifs</span>
        </label>
      ) : null}
      {liste.length === 0 ? <p data-testid="ed-avantages-vide" style={aide}>Aucun avantage : tout le monde paie le tarif public.</p> : null}
      {liste.map((r, i) => {
        const pm = r.type !== 'aucun' ? prixMembreApercu(r, prixPublic) : null;
        return (
          <div key={r.offer_id} data-testid={`ed-avantage-${r.offer_id}`} style={carte}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
              <span style={{ fontWeight: 800, fontSize: 14.5 }}>
                {r.nom}{r.active === false ? <span style={{ marginLeft: 6, fontSize: 12, fontWeight: 600, color: 'rgba(255,255,255,0.55)' }}>(offre masquée ou expirée)</span> : null}
              </span>
              <button type="button" aria-label={`Retirer ${r.nom}`} disabled={archivee} data-testid={`ed-avantage-retirer-${r.offer_id}`}
                      onClick={() => majListe((l) => l.filter((x) => x.offer_id !== r.offer_id))}
                      style={{ minWidth: 44, minHeight: 44, borderRadius: 10, background: 'none', border: '1px solid rgba(255,255,255,0.14)', color: 'rgba(255,255,255,0.8)', cursor: 'pointer' }}>
                <SvgIcon name="x" size={16} />
              </button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: r.type === 'reduction' || r.type === 'prix_fixe' ? 'minmax(0,1fr) 120px' : '1fr', gap: 8 }}>
              <select value={r.type} disabled={archivee} data-testid={`ed-avantage-type-${r.offer_id}`} onChange={(e) => majLigne(i, 'type', e.target.value)} style={champ}>
                {TYPES_AVANTAGE.map((t) => <option key={t.valeur} value={t.valeur}>{t.libelle}</option>)}
              </select>
              {r.type === 'reduction' || r.type === 'prix_fixe' ? (
                <div style={{ position: 'relative' }}>
                  <input type="number" inputMode="decimal" min={r.type === 'reduction' ? 1 : 0} max={r.type === 'reduction' ? 100 : 10000}
                         step={r.type === 'reduction' ? 1 : 0.5} value={r.valeur} disabled={archivee}
                         data-testid={`ed-avantage-valeur-${r.offer_id}`} aria-label={r.type === 'reduction' ? 'Réduction en %' : 'Prix membre en CHF'}
                         onChange={(e) => majLigne(i, 'valeur', e.target.value)} style={Object.assign({}, champ, { paddingRight: 44 })} />
                  <span style={{ position: 'absolute', right: 12, top: 12, fontSize: 13, color: 'rgba(255,255,255,0.6)' }}>{r.type === 'reduction' ? '%' : 'CHF'}</span>
                </div>
              ) : null}
            </div>
            {pm != null && Number.isFinite(Number(prixPublic)) ? (
              <div data-testid={`ed-avantage-apercu-${r.offer_id}`} style={aide}>
                Aujourd'hui : {pm === 0 ? 'place offerte (0 CHF)' : `${chf(pm)} au lieu de ${chf(prixPublic)}`}
              </div>
            ) : null}
          </div>
        );
      })}
      {!archivee && (choix.length || choixAutres.length) ? (
        <div style={carte}>
          <label htmlFor="ed-avantage-ajout" style={{ display: 'block', fontSize: 13, fontWeight: 700, marginBottom: 6 }}>+ Ajouter une offre</label>
          <select id="ed-avantage-ajout" value={ajout} data-testid="ed-avantage-ajout" onChange={(e) => { setAjout(e.target.value); ajouter(e.target.value); }} style={champ}>
            <option value="">Choisir une offre…</option>
            {choix.map((o) => <option key={o.id} value={o.id}>{o.nom}</option>)}
            {autres && choixAutres.length ? (
              <optgroup label="Offres masquées ou expirées">
                {choixAutres.map((o) => <option key={o.id} value={o.id}>{o.nom}</option>)}
              </optgroup>
            ) : null}
          </select>
          {choixAutres.length ? (
            <button type="button" data-testid="ed-avantage-autres" onClick={() => setAutres((x) => !x)}
                    style={{ marginTop: 8, minHeight: 36, background: 'none', border: 'none', color: 'rgba(255,255,255,0.7)', textDecoration: 'underline', cursor: 'pointer', fontSize: 13, padding: 0 }}>
              {autres ? 'Masquer les offres masquées ou expirées' : `Voir aussi les offres masquées ou expirées (${choixAutres.length})`}
            </button>
          ) : null}
        </div>
      ) : null}
      <p style={aide}>Une nouvelle règle vaut pour les NOUVELLES réservations. Les paiements déjà faits ne changent jamais.</p>
    </div>
  );
}

export function SectionUrgence({ evt, form, setForm, archivee }) {
  const u = form.urgence || {};
  const pris = (evt && evt.urgence && evt.urgence.places_prises) || 0;
  const maj = (k, v) => setForm((p) => Object.assign({}, p, { urgence: Object.assign({}, p.urgence, { [k]: v }) }));
  return (
    <div data-testid="ed-urgence">
      <div style={carte}>
        <label htmlFor="ed-urgence-texte" style={{ display: 'block', fontSize: 13, fontWeight: 700, marginBottom: 6 }}>Texte marketing (badge)</label>
        <input id="ed-urgence-texte" data-testid="ed-urgence-texte" value={u.texte} maxLength={TEXTE_URGENCE_MAX} disabled={archivee}
               placeholder="Ex. 50 PLACES, ÉDITION LIMITÉE, RÉSERVE TÔT" onChange={(e) => maj('texte', e.target.value)} style={champ} />
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: archivee ? 'default' : 'pointer', fontSize: 14 }}>
            <input type="checkbox" checked={!!u.visible} disabled={archivee || !String(u.texte || '').trim()} data-testid="ed-urgence-visible"
                   onChange={(e) => maj('visible', e.target.checked)} style={{ width: 20, height: 20, accentColor: 'var(--primary-color, #D91CD2)' }} />
            Afficher ce texte sur la page
          </label>
          {u.texte ? (
            <button type="button" data-testid="ed-urgence-effacer" disabled={archivee} onClick={() => { maj('texte', ''); maj('visible', false); }}
                    style={{ minHeight: 36, background: 'none', border: 'none', color: 'rgba(255,255,255,0.7)', textDecoration: 'underline', cursor: 'pointer', fontSize: 13 }}>
              Supprimer le texte
            </button>
          ) : null}
        </div>
        <p style={aide}>Ce texte est seulement visuel : il ne limite jamais les réservations.</p>
      </div>
      <div style={carte}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: archivee ? 'default' : 'pointer', fontWeight: 700, fontSize: 14 }}>
          <input type="checkbox" checked={!!u.capacite_limitee} disabled={archivee} data-testid="ed-capacite-case"
                 onChange={(e) => maj('capacite_limitee', e.target.checked)} style={{ width: 22, height: 22, accentColor: 'var(--primary-color, #D91CD2)' }} />
          Limiter réellement le nombre de réservations
        </label>
        {u.capacite_limitee ? (
          <div style={{ marginTop: 10 }}>
            <label htmlFor="ed-capacite-max" style={{ display: 'block', fontSize: 13, marginBottom: 6 }}>Capacité maximum</label>
            <input id="ed-capacite-max" data-testid="ed-capacite-max" type="number" min="1" max="10000" step="1" inputMode="numeric" disabled={archivee}
                   value={u.capacite_max} onChange={(e) => maj('capacite_max', e.target.value)} style={Object.assign({}, champ, { maxWidth: 160 })} />
            <p style={aide}>Au-delà, plus aucune réservation n'est acceptée (page « Complet »). {pris} place{pris > 1 ? 's' : ''} déjà réservée{pris > 1 ? 's' : ''}.</p>
          </div>
        ) : <p style={aide}>Désactivé : aucune limite, toutes les réservations sont acceptées.</p>}
      </div>
      <div style={{ padding: '10px 12px', borderRadius: 10, background: rgbaP(0.1), fontSize: 12.5, color: 'rgba(255,255,255,0.8)' }}>
        <span style={{ color: PRIMAIRE }}>Texte marketing ≠ capacité réelle.</span> « 50 PLACES » n'empêche jamais la 51e réservation ; seule la case ci-dessus le fait.
      </div>
    </div>
  );
}
