/**
 * V595 — CAMPAGNES → PROSPECTION → MÉDIAS. Les vidéos de prospection, par niche.
 *
 * CE QUE L'ÉCRAN NE FAIT PAS : il n'envoie rien, ne relie aucune vidéo à un prospect,
 * ne touche à aucun message. Une vidéo enregistrée entre « En cours » (forcé par le
 * serveur) ; la valider est un geste manuel, confirmé en deux temps. Remplacer une
 * vidéo l'ARCHIVE (serveur) : rien n'est jamais supprimé, et il n'existe pas de bouton
 * « Supprimer ».
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { NICHES } from '../../../utils/prospectionStats';
import { Titre, Bandeau, EtatLecture, Pastille, Bouton, DOUX, TEXTE, BORD, champ, jour } from './ui';

export const STATUTS_MEDIA = {
  en_cours: { libelle: 'En cours', ton: 'ambre' },
  a_verifier: { libelle: 'À vérifier', ton: 'bleu' },
  validee: { libelle: 'Validée', ton: 'vert' },
  archivee: { libelle: 'Archivée', ton: 'neutre' },
};
const FORMATS = [
  { id: '16_9', libelle: 'Vidéo 16:9' },
  { id: '9_16', libelle: 'Vidéo 9:16' },
  { id: 'miniature', libelle: 'Miniature' },
];

function erreurLisible(e, defaut) {
  const d = e && e.response && e.response.data && e.response.data.detail;
  return typeof d === 'string' ? d : defaut;
}

/** Statut affiché d'une NICHE : sa vidéo 16:9 actuelle, sinon « En cours » (production). */
export function statutNiche(actuels) {
  const v = actuels['16_9'];
  return v ? v.statut : 'en_cours';
}

function Emplacement({ format, media, onStatut, enCours }) {
  const [confirmer, setConfirmer] = useState(false);
  return (
    <div data-testid={`pm-emplacement-${format.id}`} style={{ border: `1px solid ${BORD}`, borderRadius: '10px', padding: '8px 10px', minWidth: 0 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}>
        <strong style={{ fontSize: '12px' }}>{format.libelle}</strong>
        {media ? <Pastille ton={STATUTS_MEDIA[media.statut].ton}>{STATUTS_MEDIA[media.statut].libelle}</Pastille>
          : <Pastille ton="ambre">En cours</Pastille>}
      </div>
      {media ? (
        <div style={{ fontSize: '12px', color: DOUX, marginTop: '6px', lineHeight: 1.5, wordBreak: 'break-word' }}>
          <div>Version : <span style={{ color: TEXTE }}>{media.version || '—'}</span> · {jour(media.created_at)}</div>
          <div>Lien public : <a href={media.url} target="_blank" rel="noopener noreferrer" style={{ color: TEXTE }}>{media.url}</a></div>
          {media.notes && <div>Notes : <span style={{ color: TEXTE }}>{media.notes}</span></div>}
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '6px', alignItems: 'center' }}>
            <label style={{ fontSize: '11px' }}>Statut
              <select value={media.statut} disabled={enCours} data-testid={`pm-statut-${format.id}`}
                onChange={(e) => { if (e.target.value === 'validee') setConfirmer(true); else onStatut(media, e.target.value); }}
                style={{ ...champ, width: 'auto', marginLeft: '6px', padding: '4px 8px', fontSize: '12px' }}>
                {Object.entries(STATUTS_MEDIA).map(([id, s]) => <option key={id} value={id} style={{ color: 'black' }}>{s.libelle}</option>)}
              </select>
            </label>
          </div>
          {confirmer && (
            <div style={{ marginTop: '6px', display: 'flex', gap: '6px', flexWrap: 'wrap', alignItems: 'center' }}>
              <span style={{ color: TEXTE }}>Valider cette vidéo pour la niche ? (aucun envoi ne part)</span>
              <Bouton onClick={() => { setConfirmer(false); onStatut(media, 'validee'); }} testid={`pm-confirmer-${format.id}`}>Confirmer</Bouton>
              <Bouton discret onClick={() => setConfirmer(false)}>Annuler</Bouton>
            </div>
          )}
        </div>
      ) : (
        <div style={{ fontSize: '12px', color: DOUX, marginTop: '6px' }}>Aucune vidéo enregistrée.</div>
      )}
    </div>
  );
}

function FormulaireAjout({ niche, onFini, API }) {
  const [f, setF] = useState({ format: '16_9', url: '', version: '', notes: '' });
  const [envoi, setEnvoi] = useState(false);
  const [msg, setMsg] = useState('');
  const maj = (k, v) => setF((p) => (p[k] === v ? p : { ...p, [k]: v }));
  const enregistrer = async (e) => {
    e.preventDefault();
    setEnvoi(true); setMsg('');
    try {
      const r = await axios.post(`${API}/prospection-medias`, { niche, ...f });
      onFini(r.data && r.data.archives ? `Enregistrée « En cours ». L'ancienne vidéo est archivée.` : 'Enregistrée « En cours ».');
    } catch (err) {
      setMsg(erreurLisible(err, 'Enregistrement refusé.'));
    } finally { setEnvoi(false); }
  };
  return (
    <form onSubmit={enregistrer} data-testid={`pm-form-${niche}`}
      style={{ display: 'grid', gap: '8px', marginTop: '8px', padding: '10px', borderRadius: '10px', background: 'rgba(255,255,255,0.03)', border: `1px solid ${BORD}` }}>
      <select value={f.format} onChange={(e) => maj('format', e.target.value)} style={champ} aria-label="Format">
        {FORMATS.map((x) => <option key={x.id} value={x.id} style={{ color: 'black' }}>{x.libelle}</option>)}
      </select>
      <input required value={f.url} onChange={(e) => maj('url', e.target.value)} style={champ}
        placeholder="Lien public (YouTube non répertorié recommandé) — https://…" aria-label="Lien public" />
      <input value={f.version} onChange={(e) => maj('version', e.target.value)} style={champ} placeholder="Version (ex. V1)" aria-label="Version" />
      <textarea value={f.notes} onChange={(e) => maj('notes', e.target.value)} style={{ ...champ, minHeight: '54px' }} placeholder="Notes" aria-label="Notes" />
      <div style={{ fontSize: '11px', color: DOUX }}>La vidéo entre « En cours ». Si une vidéo occupe déjà ce format, elle est archivée (jamais supprimée).</div>
      {msg && <div style={{ fontSize: '12px', color: 'rgb(252,165,165)' }}>{msg}</div>}
      <div style={{ display: 'flex', gap: '6px' }}>
        <Bouton type="submit" disabled={envoi}>{envoi ? 'Enregistrement…' : 'Enregistrer'}</Bouton>
        <Bouton discret onClick={() => onFini('')}>Annuler</Bouton>
      </div>
    </form>
  );
}

export default function ProspectionMedias({ API }) {
  const [medias, setMedias] = useState(null);
  const [erreur, setErreur] = useState('');
  const [ajout, setAjout] = useState('');
  const [info, setInfo] = useState('');
  const [enCours, setEnCours] = useState(false);
  const [archivesOuvert, setArchivesOuvert] = useState({});

  const charger = useCallback(async () => {
    setErreur('');
    try {
      const tous = [];
      for (let page = 0; page < 20; page += 1) {
        const r = await axios.get(`${API}/prospection-medias`, { params: { limit: 50, offset: page * 50 } });
        const lot = (r.data && r.data.medias) || [];
        tous.push(...lot);
        if (lot.length < 50) break;
      }
      setMedias(tous);
    } catch (e) {
      const code = e && e.response && e.response.status;
      setErreur(code === 401 || code === 403 ? 'Session expirée — reconnectez-vous.' : 'Les médias n’ont pas pu être lus.');
    }
  }, [API]);
  useEffect(() => { charger(); }, [charger]);

  const parNiche = useMemo(() => {
    const m = {};
    NICHES.forEach((n) => { m[n.id] = { actuels: {}, archives: [] }; });
    (medias || []).forEach((d) => {
      const g = m[d.niche];
      if (!g) return;
      if (d.statut === 'archivee') g.archives.push(d);
      else if (!g.actuels[d.format]) g.actuels[d.format] = d;
    });
    return m;
  }, [medias]);

  const changerStatut = async (media, statut) => {
    setEnCours(true); setInfo('');
    try {
      await axios.patch(`${API}/prospection-medias/${encodeURIComponent(media.id)}`, { statut });
      await charger();
    } catch (e) {
      setInfo(erreurLisible(e, 'Changement refusé.'));
    } finally { setEnCours(false); }
  };

  if (!medias) return <EtatLecture chargement={!erreur} erreur={erreur} onReessayer={charger} />;
  const validees = (medias || []).filter((d) => d.statut === 'validee').length;

  return (
    <section data-testid="prospection-medias" aria-label="Médias de prospection" style={{ color: TEXTE }}>
      <Bandeau ton="ambre" testid="pm-bandeau">
        Toutes les vidéos de prospection sont <strong>en cours de refonte</strong>. Aucune vidéo n'est envoyée
        ni associée automatiquement à un prospect. Vidéos validées : <strong data-testid="pm-validees">{validees}</strong>.
      </Bandeau>
      {info && <div style={{ marginTop: '8px' }}><Bandeau ton="bleu">{info}</Bandeau></div>}
      {NICHES.map((n) => {
        const g = parNiche[n.id];
        const st = STATUTS_MEDIA[statutNiche(g.actuels)];
        return (
          <div key={n.id} data-testid={`pm-niche-${n.id}`}>
            <Titre droite={<Pastille ton={st.ton} testid={`pm-statut-niche-${n.id}`}>{st.libelle}</Pastille>}>{n.id} — {n.libelle}</Titre>
            <div style={{ display: 'grid', gap: '8px', gridTemplateColumns: 'repeat(auto-fill, minmax(min(220px, 100%), 1fr))' }}>
              {FORMATS.map((fmt) => <Emplacement key={fmt.id} format={fmt} media={g.actuels[fmt.id]} onStatut={changerStatut} enCours={enCours} />)}
            </div>
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '8px' }}>
              <Bouton discret onClick={() => setAjout(ajout === n.id ? '' : n.id)} testid={`pm-ajouter-${n.id}`}>Ajouter / remplacer une vidéo</Bouton>
              {g.archives.length > 0 && (
                <Bouton discret onClick={() => setArchivesOuvert((p) => ({ ...p, [n.id]: !p[n.id] }))}>Archives ({g.archives.length})</Bouton>
              )}
            </div>
            {ajout === n.id && <FormulaireAjout API={API} niche={n.id} onFini={(m) => { setAjout(''); if (m) { setInfo(m); charger(); } }} />}
            {archivesOuvert[n.id] && (
              <ul style={{ margin: '8px 0 0', paddingLeft: '18px', fontSize: '12px', color: DOUX }}>
                {g.archives.map((a) => (
                  <li key={a.id} style={{ wordBreak: 'break-word' }}>
                    {(FORMATS.find((x) => x.id === a.format) || {}).libelle} · {a.version || '—'} · {jour(a.created_at)} ·{' '}
                    <a href={a.url} target="_blank" rel="noopener noreferrer" style={{ color: TEXTE }}>{a.url}</a>
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
      <div style={{ marginTop: '16px', fontSize: '11px', color: DOUX }}>
        Plus tard : prospect → niche → vidéo validée 16:9 de la niche. Ce lien n'est pas branché : aucune vidéo ne part chez un prospect.
      </div>
    </section>
  );
}
