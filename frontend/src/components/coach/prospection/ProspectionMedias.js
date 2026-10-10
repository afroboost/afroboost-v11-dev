/**
 * V595 — CAMPAGNES → PROSPECTION → MÉDIAS. Les vidéos de prospection, par niche.
 *
 * CE QUE L'ÉCRAN NE FAIT PAS : il n'envoie rien, ne relie aucune vidéo à un prospect,
 * ne touche à aucun message. Une vidéo enregistrée entre « En cours » (forcé par le
 * serveur) ; la valider est un geste manuel, confirmé en deux temps. Remplacer une
 * vidéo l'ARCHIVE (serveur) : rien n'est jamais supprimé, et il n'existe pas de bouton
 * « Supprimer ».
 *
 * V596 — chaque niche porte ORIGINAL + 16:9 + 9:16 + 1:1 + MINIATURE. L'original
 * est un fichier envoyé tel quel (jamais réencodé) ; « Modifier / exporter » ouvre
 * l'éditeur (chargé À LA DEMANDE : le moteur d'export n'est dans aucune autre page)
 * qui fabrique, DANS LE NAVIGATEUR, un nouveau MP4 enregistré « À vérifier ».
 */
import React, { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { NICHES } from '../../../utils/prospectionStats';
import { uploadToCloudinary } from '../../CloudinaryUploadButton';
import { validerFichierVideo, validerMetadonnees, tailleLisible } from '../../../utils/videoExport';
import { Titre, Bandeau, EtatLecture, Pastille, Bouton, DOUX, TEXTE, BORD, champ, jour } from './ui';

export const STATUTS_MEDIA = {
  en_cours: { libelle: 'En cours', ton: 'ambre' },
  a_verifier: { libelle: 'À vérifier', ton: 'bleu' },
  validee: { libelle: 'Validée', ton: 'vert' },
  archivee: { libelle: 'Archivée', ton: 'neutre' },
};
const FORMATS = [
  { id: 'original', libelle: 'Original' },
  { id: '16_9', libelle: 'Vidéo 16:9' },
  { id: '9_16', libelle: 'Vidéo 9:16' },
  { id: '1_1', libelle: 'Vidéo 1:1' },
  { id: 'miniature', libelle: 'Miniature' },
];
// Les formats qu'on peut saisir comme LIEN PUBLIC (comme avant V596).
const FORMATS_LIEN = FORMATS.filter((f) => f.id !== 'original');

// V596 : l'éditeur et son moteur d'export ne sont chargés qu'à l'ouverture.
const ProspectionVideoEditeur = lazy(() => import('./ProspectionVideoEditeur'));

const estFichier = (m) => !!(m && typeof m.url === 'string' && m.url.indexOf('/api/files/') === 0);
const dureeLisible = (s) => (s > 0 ? `${Number(s).toFixed(1)} s` : '');

/** Ce que le fichier est réellement : nom, durée, résolution, taille. */
function InfosFichier({ fichier }) {
  if (!fichier) return null;
  const morceaux = [
    fichier.nom,
    dureeLisible(fichier.duree),
    fichier.largeur && fichier.hauteur ? `${fichier.largeur} × ${fichier.hauteur}` : '',
    fichier.taille ? tailleLisible(fichier.taille) : '',
  ].filter(Boolean);
  return <div data-testid="pm-fichier-infos">Fichier : <span style={{ color: TEXTE }}>{morceaux.join(' · ')}</span></div>;
}

function erreurLisible(e, defaut) {
  const d = e && e.response && e.response.data && e.response.data.detail;
  return typeof d === 'string' ? d : defaut;
}

/** Statut affiché d'une NICHE : sa vidéo 16:9 actuelle, sinon « En cours » (production). */
export function statutNiche(actuels) {
  const v = actuels['16_9'];
  return v ? v.statut : 'en_cours';
}

function Emplacement({ format, media, onStatut, enCours, onEditer }) {
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
          {estFichier(media) ? (
            <>
              {format.id === 'miniature'
                ? <img src={media.url} alt="Miniature" data-testid={`pm-image-${format.id}`} style={{ marginTop: 6, width: '100%', maxHeight: 160, objectFit: 'contain', borderRadius: 8, background: '#000' }} />
                : <video src={media.url} controls playsInline preload="metadata" data-testid={`pm-lecteur-${format.id}`} style={{ marginTop: 6, width: '100%', maxHeight: 220, borderRadius: 8, background: '#000' }} />}
              <InfosFichier fichier={media.fichier} />
              {media.edition && <div>Extrait : <span style={{ color: TEXTE }}>{media.edition.debut} s → {media.edition.fin} s</span></div>}
            </>
          ) : (
            <div>Lien public : <a href={media.url} target="_blank" rel="noopener noreferrer" style={{ color: TEXTE }}>{media.url}</a></div>
          )}
          {media.notes && <div>Notes : <span style={{ color: TEXTE }}>{media.notes}</span></div>}
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '6px', alignItems: 'center' }}>
            <label style={{ fontSize: '11px' }}>Statut
              <select value={media.statut} disabled={enCours} data-testid={`pm-statut-${format.id}`}
                onChange={(e) => { if (e.target.value === 'validee') setConfirmer(true); else onStatut(media, e.target.value); }}
                style={{ ...champ, width: 'auto', marginLeft: '6px', padding: '4px 8px', fontSize: '12px' }}>
                {Object.entries(STATUTS_MEDIA).map(([id, s]) => <option key={id} value={id} style={{ color: 'black' }}>{s.libelle}</option>)}
              </select>
            </label>
            {onEditer && estFichier(media) && format.id !== 'miniature' && (
              <Bouton discret onClick={() => onEditer(media)} disabled={enCours} testid={`pm-editer-${format.id}`}>
                {format.id === 'original' ? 'Modifier / exporter' : 'Remodifier'}
              </Bouton>
            )}
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
        {FORMATS_LIEN.map((x) => <option key={x.id} value={x.id} style={{ color: 'black' }}>{x.libelle}</option>)}
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

/** Lit durée et dimensions d'un fichier LOCAL, sans rien envoyer. */
function lireMetadonnees(fichier) {
  return new Promise((res) => {
    const url = URL.createObjectURL(fichier);
    const v = document.createElement('video');
    const finir = (m) => { URL.revokeObjectURL(url); v.removeAttribute('src'); res(m); };
    const minuterie = setTimeout(() => finir(null), 15000);
    v.preload = 'metadata'; v.muted = true;
    v.onloadedmetadata = () => { clearTimeout(minuterie); finir({ duree: Math.round(v.duration * 100) / 100, largeur: v.videoWidth, hauteur: v.videoHeight }); };
    v.onerror = () => { clearTimeout(minuterie); finir(null); };
    v.src = url;
  });
}

/** V596 — ENVOYER L'ORIGINAL : vérifié, envoyé tel quel, enregistré « En cours ». */
function FormulaireOriginal({ niche, API, onFini, onOuvrirEditeur }) {
  const [etat, setEtat] = useState({ phase: '', pct: 0, msg: '' });
  const champRef = useRef(null);
  const choisir = async (e) => {
    const fichier = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!fichier) return;
    const refus = validerFichierVideo(fichier);
    if (refus) { setEtat({ phase: '', pct: 0, msg: refus }); return; }
    setEtat({ phase: 'lecture', pct: 0, msg: '' });
    const meta = await lireMetadonnees(fichier);
    const refusMeta = meta ? validerMetadonnees(meta) : 'Vidéo illisible par le navigateur.';
    if (refusMeta) { setEtat({ phase: '', pct: 0, msg: refusMeta }); return; }
    setEtat({ phase: 'envoi', pct: 0, msg: '' });
    try {
      const r = await uploadToCloudinary(fichier, { folder: 'prospection', onProgress: (pct) => setEtat((p) => ({ ...p, pct: Math.round(pct) })) });
      const rep = await axios.post(`${API}/prospection-medias`, {
        niche, format: 'original', url: r.url, version: 'Original',
        fichier: { nom: fichier.name, duree: meta.duree, largeur: meta.largeur, hauteur: meta.hauteur },
      });
      setEtat({ phase: '', pct: 0, msg: '' });
      onOuvrirEditeur(rep.data.media, fichier, rep.data.archives
        ? 'Original enregistré « En cours ». L’ancien original est archivé (jamais supprimé).'
        : 'Original enregistré « En cours ».');
    } catch (err) {
      setEtat({ phase: '', pct: 0, msg: erreurLisible(err, err && err.message ? err.message : 'Envoi refusé.') });
    }
  };
  const occupe = etat.phase !== '';
  return (
    <div data-testid={`pm-original-${niche}`} style={{ display: 'grid', gap: '8px', marginTop: '8px', padding: '10px', borderRadius: '10px', background: 'rgba(255,255,255,0.03)', border: `1px solid ${BORD}` }}>
      <strong style={{ fontSize: '12px' }}>Envoyer le fichier ORIGINAL</strong>
      <div style={{ fontSize: '11px', color: DOUX }}>MP4, MOV, M4V ou WEBM · 100 Mo et 10 min maximum. Il est conservé tel quel ; les versions 16:9, 9:16 et 1:1 se fabriquent ensuite dans l'éditeur.</div>
      <input ref={champRef} type="file" accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.m4v,.webm" onChange={choisir} disabled={occupe}
        style={{ display: 'none' }} data-testid={`pm-original-champ-${niche}`} />
      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', alignItems: 'center' }}>
        <Bouton onClick={() => champRef.current && champRef.current.click()} disabled={occupe} testid={`pm-original-choisir-${niche}`}>Choisir la vidéo</Bouton>
        <Bouton discret onClick={() => onFini('')} disabled={occupe}>Annuler</Bouton>
        {etat.phase === 'lecture' && <span style={{ fontSize: '12px', color: DOUX }}>Lecture du fichier…</span>}
        {etat.phase === 'envoi' && <span style={{ fontSize: '12px' }} data-testid={`pm-original-envoi-${niche}`}>Envoi… {etat.pct} %</span>}
      </div>
      {etat.msg && <div style={{ fontSize: '12px', color: 'rgb(252,165,165)' }} data-testid={`pm-original-erreur-${niche}`}>{etat.msg}</div>}
    </div>
  );
}

export default function ProspectionMedias({ API }) {
  const [medias, setMedias] = useState(null);
  const [erreur, setErreur] = useState('');
  const [ajout, setAjout] = useState('');
  const [info, setInfo] = useState('');
  const [enCours, setEnCours] = useState(false);
  const [archivesOuvert, setArchivesOuvert] = useState({});
  const [mode, setMode] = useState('fichier');                 // V596 : « fichier » (original) | « lien »
  const [editeur, setEditeur] = useState(null);                // { niche, original, fichierLocal, edition }

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

  // V596 : ouvrir l'éditeur sur un ORIGINAL, ou sur l'original d'un export (« Remodifier »).
  const ouvrirEditeur = (media) => {
    if (media.format === 'original') { setEditeur({ niche: media.niche, original: media, fichierLocal: null, edition: null }); return; }
    const original = (medias || []).find((d) => d.id === media.source_id);
    if (!original) { setInfo('L’original de cette version est introuvable.'); return; }
    setEditeur({ niche: media.niche, original, fichierLocal: null, edition: media.edition || null });
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
              {FORMATS.map((fmt) => <Emplacement key={fmt.id} format={fmt} media={g.actuels[fmt.id]} onStatut={changerStatut} enCours={enCours || !!editeur} onEditer={ouvrirEditeur} />)}
            </div>
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '8px' }}>
              <Bouton discret onClick={() => setAjout(ajout === n.id ? '' : n.id)} testid={`pm-ajouter-${n.id}`}>Ajouter / remplacer une vidéo</Bouton>
              {g.archives.length > 0 && (
                <Bouton discret onClick={() => setArchivesOuvert((p) => ({ ...p, [n.id]: !p[n.id] }))}>Archives ({g.archives.length})</Bouton>
              )}
            </div>
            {ajout === n.id && (
              <div style={{ marginTop: '8px' }}>
                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }} role="group" aria-label="Type d'ajout">
                  <Bouton discret={mode !== 'fichier'} onClick={() => setMode('fichier')} testid={`pm-mode-fichier-${n.id}`}>Fichier original</Bouton>
                  <Bouton discret={mode !== 'lien'} onClick={() => setMode('lien')} testid={`pm-mode-lien-${n.id}`}>Lien public</Bouton>
                </div>
                {mode === 'fichier'
                  ? <FormulaireOriginal API={API} niche={n.id}
                      onFini={(m) => { setAjout(''); if (m) { setInfo(m); charger(); } }}
                      onOuvrirEditeur={(original, fichierLocal, m) => { setAjout(''); setInfo(m); charger(); setEditeur({ niche: n.id, original, fichierLocal, edition: null }); }} />
                  : <FormulaireAjout API={API} niche={n.id} onFini={(m) => { setAjout(''); if (m) { setInfo(m); charger(); } }} />}
              </div>
            )}
            {editeur && editeur.niche === n.id && (
              <Suspense fallback={<div style={{ marginTop: '8px', fontSize: '12px', color: DOUX }} data-testid="pm-editeur-chargement">Chargement de l'éditeur vidéo…</div>}>
                <ProspectionVideoEditeur API={API} niche={n.id} original={editeur.original} fichierLocal={editeur.fichierLocal}
                  editionInitiale={editeur.edition}
                  onFermer={() => setEditeur(null)}
                  onEnregistre={(m) => { setInfo(m); charger(); }} />
              </Suspense>
            )}
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
