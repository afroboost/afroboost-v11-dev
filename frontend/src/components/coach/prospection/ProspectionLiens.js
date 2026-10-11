/**
 * V595 — CAMPAGNES → PROSPECTION → LIENS. Un endroit unique pour les liens de prospection.
 *
 * « Tester le lien » demande au SERVEUR si la destination répond (garde anti-réseau
 * interne côté serveur) : seuls la date et le résultat sont notés, le statut ne change
 * pas. Les liens d'essai gratuit / QR qui parlent encore du casque sont VERROUILLÉS
 * « bloqués » par le serveur : l'écran ne peut pas les réactiver. Aucun lien n'est
 * utilisé automatiquement ; aucun bouton « Supprimer » (on archive).
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import SvgIcon from '../../SvgIcon';
import { libellesNiches } from '../../../utils/prospectionStats';
import useNichesProspection from '../../../hooks/useNichesProspection'; // V598 : niches du serveur
import { Titre, Bandeau, EtatLecture, Pastille, Bouton, Puce, DOUX, TEXTE, BORD, champ, heure } from './ui';

export const CATEGORIES_LIEN = [
  { id: 'videos', libelle: 'Vidéos' },
  { id: 'site', libelle: 'Site' },
  { id: 'reservation', libelle: 'Réservation' },
  { id: 'formulaires', libelle: 'Formulaires' },
  { id: 'reseaux', libelle: 'Réseaux sociaux' },
  { id: 'dossiers', libelle: 'Dossiers' },
  { id: 'autres', libelle: 'Autres' },
];
export const STATUTS_LIEN = {
  actif: { libelle: 'Actif', ton: 'vert' },
  a_verifier: { libelle: 'À vérifier', ton: 'ambre' },
  bloque: { libelle: 'Bloqué', ton: 'rouge' },
  archive: { libelle: 'Archivé', ton: 'neutre' },
};
// V598 : { clé: « C — Festivals » } d'après la liste du serveur. `choisissables` = actives,
// plus la niche déjà portée par le lien (même archivée) pour ne jamais la perdre à l'édition.
function libellesDe(niches, actuelle) {
  const tous = libellesNiches(niches);
  const choisissables = { toutes: 'Toutes les niches' };
  niches.forEach((n) => { if ((n.active !== false && !n.supprimee) || n.cle === actuelle) choisissables[n.cle] = tous[n.cle]; });
  return { tous: { ...tous, toutes: 'Toutes les niches' }, choisissables };
}
const VIDE = { nom: '', url: '', categorie: 'site', niche: 'toutes', utilisation: '', statut: 'a_verifier' };

function erreurLisible(e, defaut) {
  const d = e && e.response && e.response.data && e.response.data.detail;
  return typeof d === 'string' ? d : defaut;
}

function Formulaire({ initial, onEnregistrer, onAnnuler, enCours, verrou, niches }) {
  const [f, setF] = useState(initial);
  const maj = (k, v) => setF((p) => (p[k] === v ? p : { ...p, [k]: v }));
  return (
    <form onSubmit={(e) => { e.preventDefault(); onEnregistrer(f); }} data-testid="pl-form"
      style={{ display: 'grid', gap: '8px', padding: '10px', borderRadius: '10px', background: 'rgba(255,255,255,0.03)', border: `1px solid ${BORD}`, marginTop: '8px' }}>
      <input required value={f.nom} onChange={(e) => maj('nom', e.target.value)} style={champ} placeholder="Nom" aria-label="Nom" />
      <input required value={f.url} onChange={(e) => maj('url', e.target.value)} style={champ} placeholder="https://…" aria-label="URL" />
      <div style={{ display: 'grid', gap: '8px', gridTemplateColumns: 'repeat(auto-fill, minmax(min(160px, 100%), 1fr))' }}>
        <select value={f.categorie} onChange={(e) => maj('categorie', e.target.value)} style={champ} aria-label="Catégorie">
          {CATEGORIES_LIEN.map((c) => <option key={c.id} value={c.id} style={{ color: 'black' }}>{c.libelle}</option>)}
        </select>
        <select value={f.niche} onChange={(e) => maj('niche', e.target.value)} style={champ} aria-label="Niche">
          {Object.entries(libellesDe(niches, initial.niche).choisissables).map(([id, l]) => <option key={id} value={id} style={{ color: 'black' }}>{l}</option>)}
        </select>
        <select value={f.statut} onChange={(e) => maj('statut', e.target.value)} style={champ} aria-label="Statut" disabled={!!verrou}>
          {Object.entries(STATUTS_LIEN).map(([id, s]) => <option key={id} value={id} style={{ color: 'black' }}>{s.libelle}</option>)}
        </select>
      </div>
      <input value={f.utilisation || ''} onChange={(e) => maj('utilisation', e.target.value)} style={champ}
        placeholder="Utilisation (ex. e-mail écoles de danse, bio Instagram…)" aria-label="Utilisation" />
      {verrou && <div style={{ fontSize: '11px', color: DOUX }}>Statut verrouillé « Bloqué » : {verrou}</div>}
      <div style={{ display: 'flex', gap: '6px' }}>
        <Bouton type="submit" disabled={enCours}>{enCours ? 'Enregistrement…' : 'Enregistrer'}</Bouton>
        <Bouton discret onClick={onAnnuler}>Annuler</Bouton>
      </div>
    </form>
  );
}

function CarteLien({ lien, onTester, onModifier, test, niches }) {
  const st = STATUTS_LIEN[lien.statut] || STATUTS_LIEN.a_verifier;
  const dt = lien.dernier_test;
  return (
    <div data-testid="pl-lien" style={{ border: `1px solid ${BORD}`, borderRadius: '10px', padding: '9px 11px', minWidth: 0 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}>
        <strong style={{ fontSize: '13px' }}>{lien.nom}</strong>
        <Pastille ton={st.ton} testid="pl-statut">{lien.verrou && <SvgIcon name="lock" size={10} />}{st.libelle}</Pastille>
      </div>
      <a href={lien.url} target="_blank" rel="noopener noreferrer"
        style={{ display: 'block', fontSize: '12px', color: DOUX, wordBreak: 'break-all', marginTop: '4px' }}>{lien.url}</a>
      <div style={{ fontSize: '12px', color: DOUX, marginTop: '4px', lineHeight: 1.5 }}>
        {libellesDe(niches, lien.niche).tous[lien.niche] || '—'}{lien.utilisation ? ` · ${lien.utilisation}` : ''}
        {lien.verrou && <div style={{ color: 'rgb(252,165,165)' }}>Bloqué par le serveur : {lien.verrou}</div>}
        <div>
          Vérifié : {lien.verifie_le ? heure(lien.verifie_le) : 'jamais'}
          {dt && <> · {dt.ok ? 'répond' : 'ne répond pas'}{dt.http ? ` (${dt.http})` : ''}{!dt.ok && dt.motif ? ` — ${dt.motif}` : ''}</>}
        </div>
      </div>
      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '8px' }}>
        <Bouton discret onClick={() => onTester(lien)} disabled={test === lien.id} testid="pl-tester">
          <SvgIcon name="refresh" size={12} /> {test === lien.id ? 'Test…' : 'Tester le lien'}
        </Bouton>
        <Bouton discret onClick={() => onModifier(lien)} testid="pl-modifier"><SvgIcon name="edit" size={12} /> Modifier</Bouton>
      </div>
    </div>
  );
}

export default function ProspectionLiens({ API }) {
  const { niches } = useNichesProspection(API);
  const [liens, setLiens] = useState(null);
  const [erreur, setErreur] = useState('');
  const [filtre, setFiltre] = useState('tous');
  const [edition, setEdition] = useState(null); // null | 'nouveau' | lien
  const [enCours, setEnCours] = useState(false);
  const [test, setTest] = useState('');
  const [info, setInfo] = useState('');

  const charger = useCallback(async () => {
    setErreur('');
    try {
      const tous = [];
      for (let page = 0; page < 20; page += 1) {
        const r = await axios.get(`${API}/prospection-liens`, { params: { limit: 50, offset: page * 50 } });
        const lot = (r.data && r.data.liens) || [];
        tous.push(...lot);
        if (lot.length < 50) break;
      }
      setLiens(tous);
    } catch (e) {
      const code = e && e.response && e.response.status;
      setErreur(code === 401 || code === 403 ? 'Session expirée — reconnectez-vous.' : 'Les liens n’ont pas pu être lus.');
    }
  }, [API]);
  useEffect(() => { charger(); }, [charger]);

  const remplacer = (l) => setLiens((prev) => (prev || []).map((x) => (x.id === l.id ? l : x)));

  const enregistrer = async (f) => {
    setEnCours(true); setInfo('');
    try {
      if (edition === 'nouveau') {
        const r = await axios.post(`${API}/prospection-liens`, f);
        const l = r.data.lien;
        setInfo(l.statut === 'bloque' && l.verrou ? `Enregistré, mais bloqué : ${l.verrou}.` : 'Lien enregistré.');
        await charger();
      } else {
        const corps = { nom: f.nom, url: f.url, categorie: f.categorie, niche: f.niche, utilisation: f.utilisation };
        if (!edition.verrou) corps.statut = f.statut;
        const r = await axios.patch(`${API}/prospection-liens/${encodeURIComponent(edition.id)}`, corps);
        remplacer(r.data.lien);
        setInfo('Lien mis à jour.');
      }
      setEdition(null);
    } catch (e) {
      setInfo(erreurLisible(e, 'Enregistrement refusé.'));
    } finally { setEnCours(false); }
  };

  const tester = async (lien) => {
    setTest(lien.id); setInfo('');
    try {
      const r = await axios.post(`${API}/prospection-liens/${encodeURIComponent(lien.id)}/tester`);
      remplacer(r.data.lien);
    } catch (e) {
      setInfo(erreurLisible(e, 'Test impossible.'));
    } finally { setTest(''); }
  };

  const visibles = useMemo(() => (liens || []).filter((l) => filtre === 'tous' || l.categorie === filtre), [liens, filtre]);
  if (!liens) return <EtatLecture chargement={!erreur} erreur={erreur} onReessayer={charger} />;

  return (
    <section data-testid="prospection-liens" aria-label="Liens de prospection" style={{ color: TEXTE }}>
      <Bandeau ton="rouge" testid="pl-bandeau">
        Les liens d'essai gratuit / QR qui parlent encore du casque sont <strong>bloqués par le serveur</strong>.
        Aucun lien de cette page n'est utilisé automatiquement.
      </Bandeau>
      {info && <div style={{ marginTop: '8px' }}><Bandeau ton="bleu" testid="pl-info">{info}</Bandeau></div>}
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap', alignItems: 'center', marginTop: '12px' }}>
        <div role="group" aria-label="Catégories" style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          <Puce actif={filtre === 'tous'} onClick={() => setFiltre('tous')}>Tous ({liens.length})</Puce>
          {CATEGORIES_LIEN.map((c) => {
            const n = liens.filter((l) => l.categorie === c.id).length;
            return <Puce key={c.id} actif={filtre === c.id} onClick={() => setFiltre(c.id)} testid={`pl-cat-${c.id}`}>{c.libelle} ({n})</Puce>;
          })}
        </div>
        <Bouton onClick={() => setEdition('nouveau')} testid="pl-ajouter">Ajouter un lien</Bouton>
      </div>
      {edition === 'nouveau' && (
        <Formulaire niches={niches} initial={{ ...VIDE, categorie: filtre !== 'tous' ? filtre : 'site' }} enCours={enCours}
          onEnregistrer={enregistrer} onAnnuler={() => setEdition(null)} />
      )}
      {CATEGORIES_LIEN.filter((c) => filtre === 'tous' || c.id === filtre).map((c) => {
        const groupe = visibles.filter((l) => l.categorie === c.id);
        if (!groupe.length) return null;
        return (
          <div key={c.id}>
            <Titre>{c.libelle}</Titre>
            <div style={{ display: 'grid', gap: '8px', gridTemplateColumns: 'repeat(auto-fill, minmax(min(260px, 100%), 1fr))' }}>
              {groupe.map((l) => (edition && edition.id === l.id ? (
                <Formulaire niches={niches} key={l.id} initial={{ nom: l.nom, url: l.url, categorie: l.categorie, niche: l.niche, utilisation: l.utilisation || '', statut: l.statut }}
                  verrou={l.verrou} enCours={enCours} onEnregistrer={enregistrer} onAnnuler={() => setEdition(null)} />
              ) : (
                <CarteLien key={l.id} lien={l} niches={niches} onTester={tester} onModifier={setEdition} test={test} />
              )))}
            </div>
          </div>
        );
      })}
      {visibles.length === 0 && edition !== 'nouveau' && (
        <div data-testid="pl-vide" style={{ marginTop: '14px', fontSize: '13px', color: DOUX }}>
          Aucun lien enregistré{filtre !== 'tous' ? ' dans cette catégorie' : ''}. Utilisez « Ajouter un lien ».
        </div>
      )}
    </section>
  );
}
