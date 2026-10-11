/**
 * V595 — CAMPAGNES → PROSPECTION → MÉDIAS. Les vidéos de prospection, par niche.
 *
 * CE QUE L'ÉCRAN NE FAIT PAS : il n'envoie rien, ne relie aucune vidéo à un prospect,
 * ne touche à aucun message. Une vidéo enregistrée entre « En cours » (forcé par le
 * serveur) ; la valider est un geste manuel, confirmé en deux temps. Remplacer une
 * vidéo l'ARCHIVE (serveur).
 *
 * V597 — DESIGN ÉPURÉ (règle permanente, CLAUDE.md) : six lignes compactes, toutes
 * fermées, une seule ouverte à la fois ; un emplacement vide = « + Ajouter » ; une
 * action principale + « ⋯ » (Détails, Valider, Supprimer) ; l'éditeur s'ouvre dans
 * une FENÊTRE (plein écran sur téléphone). « Supprimer » place UN média dans la
 * Corbeille existante (restaurable), après confirmation.
 *
 * V596 — chaque niche porte ORIGINAL + 16:9 + 9:16 + 1:1 + MINIATURE. L'original
 * est un fichier envoyé tel quel (jamais réencodé) ; « Modifier / exporter » ouvre
 * l'éditeur (chargé À LA DEMANDE : le moteur d'export n'est dans aucune autre page)
 * qui fabrique, DANS LE NAVIGATEUR, un nouveau MP4 enregistré « À vérifier ».
 */
import React, { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import { lettreNiche } from '../../../utils/prospectionStats';
import useNichesProspection from '../../../hooks/useNichesProspection'; // V598 : niches du serveur (ajout, renommage, archivage)
import { uploadToCloudinary } from '../../CloudinaryUploadButton';
import { validerFichierVideo, validerMetadonnees, tailleLisible, lireMetadonneesFichier } from '../../../utils/videoExport';
import { EtatLecture, Pastille, Bouton, DOUX, TEXTE, BORD, champ, jour } from './ui';

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
const dureeCourte = (s) => {
  if (!(s > 0)) return '';
  const t = Math.round(s);
  return `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`;
};
// Libellés COURTS des emplacements (la ligne d'un média reste lisible sur téléphone).
const COURT = { original: 'Original', '16_9': '16:9', '9_16': '9:16', '1_1': '1:1', miniature: 'Miniature' };
const RATIO_DU_FORMAT = { '16_9': '16:9', '9_16': '9:16', '1_1': '1:1' };

function erreurLisible(e, defaut) {
  const d = e && e.response && e.response.data && e.response.data.detail;
  return typeof d === 'string' ? d : defaut;
}

/**
 * Statut affiché d'une NICHE. V597 : « Validée » si sa vidéo 16:9 l'est ; sinon
 * « À vérifier » dès qu'un de ses médias attend ta décision ; sinon « En cours ».
 */
export function statutNiche(actuels) {
  const v = actuels['16_9'];
  if (v && v.statut === 'validee') return 'validee';
  if (Object.values(actuels).some((m) => m && m.statut === 'a_verifier')) return 'a_verifier';
  return 'en_cours';
}

// --- Icônes SVG inline (règle du projet : jamais d'emoji comme icône) ---------
const Icone = ({ d, taille = 16 }) => (
  <svg width={taille} height={taille} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>
);
const CHEVRON = <path d="M9 6l6 6-6 6" />;
const POINTS = <><circle cx="5" cy="12" r="1.5" /><circle cx="12" cy="12" r="1.5" /><circle cx="19" cy="12" r="1.5" /></>;
const PLUS = <><path d="M12 5v14" /><path d="M5 12h14" /></>;
const CORBEILLE = <><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M19 6l-1 14H6L5 6" /></>;

const boutonIcone = {
  width: 32, height: 32, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  borderRadius: 9, border: `1px solid ${BORD}`, background: 'transparent', color: TEXTE, cursor: 'pointer', flexShrink: 0,
};

/** Fenêtre de confirmation (portée sur <body>) : jamais de suppression sans « Supprimer ». */
function Confirmation({ titre, texte, libelleOk, onOk, onAnnuler, enCours }) {
  return createPortal(
    <div role="dialog" aria-modal="true" aria-label={titre} data-testid="pm-confirmation"
      onMouseDown={(e) => { if (e.target === e.currentTarget && !enCours) onAnnuler(); }}
      style={{ position: 'fixed', inset: 0, zIndex: 10100, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div style={{ width: 'min(400px, 100%)', background: '#14101b', border: `1px solid ${BORD}`, borderRadius: 14, padding: 18, color: TEXTE }}>
        <div style={{ fontSize: 15, fontWeight: 700 }}>{titre}</div>
        {texte && <div style={{ fontSize: 12, color: DOUX, marginTop: 6, lineHeight: 1.5 }}>{texte}</div>}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
          <Bouton discret onClick={onAnnuler} disabled={enCours} testid="pm-confirmation-annuler">Annuler</Bouton>
          <Bouton onClick={onOk} disabled={enCours} testid="pm-confirmation-ok">{enCours ? '…' : libelleOk}</Bouton>
        </div>
      </div>
    </div>,
    document.body,
  );
}

/** Menu « ⋯ » : les actions secondaires, cachées jusqu'au clic. */
function MenuPlus({ actions, testid }) {
  const [ouvert, setOuvert] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!ouvert) return undefined;
    const fermer = (e) => { if (ref.current && !ref.current.contains(e.target)) setOuvert(false); };
    document.addEventListener('mousedown', fermer);
    return () => document.removeEventListener('mousedown', fermer);
  }, [ouvert]);
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button type="button" aria-label="Plus d'actions" aria-haspopup="menu" aria-expanded={ouvert} data-testid={testid}
        onClick={() => setOuvert((o) => !o)} style={boutonIcone}><Icone d={POINTS} /></button>
      {ouvert && (
        <div role="menu" style={{ position: 'absolute', right: 0, top: 36, zIndex: 20, minWidth: 150, background: '#1b1524', border: `1px solid ${BORD}`, borderRadius: 10, padding: 4, boxShadow: '0 8px 24px rgba(0,0,0,0.45)' }}>
          {actions.map((a) => (
            <button key={a.libelle} type="button" role="menuitem" data-testid={a.testid}
              onClick={() => { setOuvert(false); a.onClick(); }}
              style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%', padding: '8px 10px', border: 'none', borderRadius: 7, background: 'transparent', color: a.danger ? 'rgb(252,165,165)' : TEXTE, fontSize: 12, cursor: 'pointer', textAlign: 'left' }}>
              {a.icone && <Icone d={a.icone} taille={14} />}{a.libelle}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** Aperçu minuscule : l'image elle-même, ou la 1re image de la vidéo. */
function Vignette({ media, format }) {
  const style = { width: 64, height: 40, objectFit: 'cover', borderRadius: 6, background: '#000', flexShrink: 0, display: 'block' };
  if (!estFichier(media)) return <div style={{ ...style, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, color: DOUX }}>Lien</div>;
  if (format === 'miniature') return <img src={media.url} alt="" style={style} data-testid={`pm-image-${format}`} />;
  return <video src={`${media.url}#t=1`} muted playsInline preload="metadata" style={style} data-testid={`pm-lecteur-${format}`} />;
}

/** Les détails techniques : affichés seulement à la demande (« Détails »). */
function Details({ media, onStatut, enCours }) {
  const f = media.fichier || {};
  const lignes = [
    ['Fichier', f.nom],
    ['Résolution', f.largeur && f.hauteur ? `${f.largeur} × ${f.hauteur}` : ''],
    ['Durée', f.duree ? `${Number(f.duree).toFixed(1)} s` : ''],
    ['Taille', f.taille ? tailleLisible(f.taille) : ''],
    ['Extrait', media.edition ? `${media.edition.debut} s → ${media.edition.fin} s` : ''],
    ['Version', media.version],
    ['Ajouté le', jour(media.created_at)],
    ['Lien', estFichier(media) ? '' : media.url],
    ['Notes', media.notes],
  ].filter(([, v]) => v);
  return (
    <div data-testid={`pm-details-${media.format}`} style={{ marginTop: 8, padding: 10, borderRadius: 8, background: 'rgba(255,255,255,0.03)', fontSize: 11, color: DOUX, display: 'grid', gap: 3, wordBreak: 'break-word' }}>
      {estFichier(media) && media.format !== 'miniature' && (
        <video src={media.url} controls playsInline preload="metadata" style={{ width: '100%', maxHeight: 260, borderRadius: 8, background: '#000', marginBottom: 6 }} data-testid={`pm-lecteur-complet-${media.format}`} />
      )}
      {lignes.map(([k, v]) => <div key={k}>{k} : <span style={{ color: TEXTE }}>{v}</span></div>)}
      <label style={{ marginTop: 4 }}>Statut
        <select value={media.statut} disabled={enCours} data-testid={`pm-statut-${media.format}`}
          onChange={(e) => onStatut(media, e.target.value)}
          style={{ ...champ, width: 'auto', marginLeft: 6, padding: '3px 8px', fontSize: 12 }}>
          {Object.entries(STATUTS_MEDIA).filter(([id]) => id !== 'validee' || media.statut === 'validee')
            .map(([id, s]) => <option key={id} value={id} style={{ color: 'black' }}>{s.libelle}</option>)}
        </select>
      </label>
    </div>
  );
}

/**
 * UN EMPLACEMENT d'une niche. Vide : « + Ajouter ». Rempli : vignette, format,
 * durée, statut, UNE action principale + « ⋯ » (Détails, Valider, Supprimer).
 */
function Emplacement({ format, media, enCours, onEditer, onAjouter, onStatut, onValider, onSupprimer }) {
  const [details, setDetails] = useState(false);
  const ligne = { display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 };
  const carte = { border: `1px solid ${BORD}`, borderRadius: 10, padding: '8px 10px', minWidth: 0 };
  if (!media) {
    return (
      <div data-testid={`pm-emplacement-${format.id}`} style={{ ...carte, ...ligne, justifyContent: 'space-between', borderStyle: 'dashed' }}>
        <strong style={{ fontSize: 12, color: DOUX }}>{COURT[format.id]}</strong>
        <button type="button" onClick={() => onAjouter(format.id)} disabled={enCours} data-testid={`pm-ajouter-${format.id}`}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 4, border: 'none', background: 'transparent', color: 'var(--primary-color, #D91CD2)', fontSize: 12, fontWeight: 700, cursor: 'pointer', padding: 4 }}>
          <Icone d={PLUS} taille={14} />Ajouter
        </button>
      </div>
    );
  }
  const st = STATUTS_MEDIA[media.statut] || STATUTS_MEDIA.en_cours;
  const duree = dureeCourte(media.fichier && media.fichier.duree);
  const principal = estFichier(media)
    ? { libelle: format.id === 'original' ? 'Modifier' : (format.id === 'miniature' ? 'Changer' : 'Remodifier'), onClick: () => onEditer(media) }
    : { libelle: 'Ouvrir', href: media.url };
  const actions = [
    { libelle: details ? 'Masquer les détails' : 'Détails', onClick: () => setDetails((d) => !d), testid: `pm-menu-details-${format.id}` },
    ...(media.statut !== 'validee' && format.id !== 'original' ? [{ libelle: 'Valider', onClick: () => onValider(media), testid: `pm-menu-valider-${format.id}` }] : []),
    { libelle: 'Supprimer', icone: CORBEILLE, danger: true, onClick: () => onSupprimer(media), testid: `pm-menu-supprimer-${format.id}` },
  ];
  return (
    <div data-testid={`pm-emplacement-${format.id}`} style={carte}>
      <div style={ligne}>
        <Vignette media={media} format={format.id} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: 12, fontWeight: 700 }}>{COURT[format.id]}{duree && <span style={{ color: DOUX, fontWeight: 500 }}> · {duree}</span>}</div>
          <div style={{ marginTop: 3 }}><Pastille ton={st.ton}>{st.libelle}</Pastille></div>
        </div>
        {principal.href
          ? <a href={principal.href} target="_blank" rel="noopener noreferrer" style={{ fontSize: 12, color: TEXTE }}>{principal.libelle}</a>
          : <Bouton discret onClick={principal.onClick} disabled={enCours} testid={`pm-editer-${format.id}`}>{principal.libelle}</Bouton>}
        <MenuPlus actions={actions} testid={`pm-menu-${format.id}`} />
      </div>
      {details && <Details media={media} onStatut={onStatut} enCours={enCours} />}
    </div>
  );
}

/** L'éditeur dans une FENÊTRE (plein écran sur téléphone) : la page Médias ne s'allonge plus.
 *  z-index 10050 : AU-DESSUS des boutons fixes du tableau de bord (« Vue Visiteur », « Déconnexion » = 9999). */
function FenetreEditeur({ children, onFermer, bloque }) {
  useEffect(() => {
    const avant = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const touche = (e) => { if (e.key === 'Escape' && !bloque) onFermer(); };
    document.addEventListener('keydown', touche);
    return () => { document.body.style.overflow = avant; document.removeEventListener('keydown', touche); };
  }, [onFermer, bloque]);
  return createPortal(
    <div role="dialog" aria-modal="true" aria-label="Éditeur vidéo" data-testid="pm-fenetre-editeur" className="pm-fenetre"
      style={{ position: 'fixed', inset: 0, zIndex: 10050, background: 'rgba(0,0,0,0.78)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <style>{`
        .pm-fenetre-boite{width:min(1180px,96vw);max-height:94vh;overflow:auto;border-radius:16px;background:#0f0b15;border:1px solid ${BORD}}
        @media (max-width:640px){.pm-fenetre-boite{width:100vw;height:100vh;max-height:100vh;border-radius:0;border:none}}
      `}</style>
      <div className="pm-fenetre-boite">{children}</div>
    </div>,
    document.body,
  );
}

function FormulaireAjout({ niche, onFini, API, formatInitial = '16_9' }) {
  const [f, setF] = useState({ format: formatInitial, url: '', version: '', notes: '' });
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
    const meta = await lireMetadonneesFichier(fichier);
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

/** V598 — petite fenêtre « Nom de la niche » (créer ou renommer). */
function FenetreNomNiche({ titre, initial = '', libelleOk, onOk, onAnnuler }) {
  const [nom, setNom] = useState(initial);
  const [envoi, setEnvoi] = useState(false);
  const [msg, setMsg] = useState('');
  const valider = async (e) => {
    e.preventDefault();
    const propre = nom.trim();
    if (propre.length < 2) { setMsg('2 caractères minimum.'); return; }
    setEnvoi(true); setMsg('');
    try { await onOk(propre); } catch (err) { setMsg(erreurLisible(err, 'Enregistrement refusé.')); setEnvoi(false); }
  };
  return createPortal(
    <div role="dialog" aria-modal="true" aria-label={titre} data-testid="pm-fenetre-niche"
      onMouseDown={(e) => { if (e.target === e.currentTarget && !envoi) onAnnuler(); }}
      style={{ position: 'fixed', inset: 0, zIndex: 10100, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <form onSubmit={valider} style={{ width: 'min(400px, 100%)', background: '#14101b', border: `1px solid ${BORD}`, borderRadius: 14, padding: 18, color: TEXTE, display: 'grid', gap: 10 }}>
        <div style={{ fontSize: 15, fontWeight: 700 }}>{titre}</div>
        <label style={{ fontSize: 12, color: DOUX, display: 'grid', gap: 6 }}>Nom de la niche
          <input autoFocus value={nom} maxLength={60} onChange={(e) => setNom(e.target.value)} style={champ}
            placeholder="ex. Personnes âgées / seniors" data-testid="pm-niche-nom" />
        </label>
        {msg && <div style={{ fontSize: 12, color: 'rgb(252,165,165)' }} data-testid="pm-niche-erreur">{msg}</div>}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Bouton discret onClick={onAnnuler} disabled={envoi} testid="pm-niche-annuler">Annuler</Bouton>
          <Bouton type="submit" disabled={envoi} testid="pm-niche-ok">{envoi ? '…' : libelleOk}</Bouton>
        </div>
      </form>
    </div>,
    document.body,
  );
}

export default function ProspectionMedias({ API }) {
  const [medias, setMedias] = useState(null);
  const [erreur, setErreur] = useState('');
  const [info, setInfo] = useState('');
  const [enCours, setEnCours] = useState(false);
  // V597 — DESIGN ÉPURÉ : toutes les niches FERMÉES au chargement, une seule ouverte à la fois.
  const [ouverte, setOuverte] = useState('');
  const [ajout, setAjout] = useState(null);                    // { niche, format, mode: 'fichier' | 'lien' }
  const [archivesOuvert, setArchivesOuvert] = useState(false);
  const [editeur, setEditeur] = useState(null);                // { niche, original, fichierLocal, edition, ratio }
  const [aConfirmer, setAConfirmer] = useState(null);          // { type: 'supprimer' | 'valider', media } | { type: 'archiver_niche' | 'supprimer_niche', niche }
  // V598 : la liste des niches vient du serveur ; création / renommage dans une petite fenêtre.
  const { niches, recharger: rechargerNiches } = useNichesProspection(API);
  const [fenetreNiche, setFenetreNiche] = useState(null);      // { type: 'creer' | 'renommer', niche }
  const [nichesArchiveesOuvert, setNichesArchiveesOuvert] = useState(false);

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
    niches.forEach((n) => { m[n.cle] = { actuels: {}, archives: [] }; });
    (medias || []).forEach((d) => {
      const g = m[d.niche];
      if (!g) return;
      if (d.statut === 'archivee') g.archives.push(d);
      else if (!g.actuels[d.format]) g.actuels[d.format] = d;
    });
    return m;
  }, [medias, niches]);
  const lettreDeCle = useMemo(() => niches.reduce((m, n) => ({ ...m, [n.cle]: lettreNiche(n.ordre) }), {}), [niches]);

  const changerStatut = async (media, statut) => {
    if (statut === 'validee') { setAConfirmer({ type: 'valider', media }); return; }
    setEnCours(true); setInfo('');
    try {
      await axios.patch(`${API}/prospection-medias/${encodeURIComponent(media.id)}`, { statut });
      await charger();
    } catch (e) {
      setInfo(erreurLisible(e, 'Changement refusé.'));
    } finally { setEnCours(false); }
  };

  // V597 : la confirmation fait l'action — « Valider » (statut) ou « Supprimer » (Corbeille).
  const confirmer = async () => {
    const { type, media, niche } = aConfirmer;
    setEnCours(true); setInfo('');
    try {
      if (type === 'archiver_niche' || type === 'reactiver_niche') {
        await axios.patch(`${API}/prospection-niches/${encodeURIComponent(niche.id)}`, { active: type === 'reactiver_niche' });
        setInfo(type === 'archiver_niche' ? `Niche « ${niche.nom} » archivée. Ses médias sont conservés.` : `Niche « ${niche.nom} » réactivée.`);
        if (type === 'archiver_niche') setOuverte('');
        setAConfirmer(null);
        await rechargerNiches();
        return;
      }
      if (type === 'supprimer_niche') {
        await axios.delete(`${API}/prospection-niches/${encodeURIComponent(niche.id)}`);
        setInfo(`Niche « ${niche.nom} » placée dans la Corbeille (restaurable). Ses prospects, médias et liens sont conservés.`);
        setOuverte('');
        setAConfirmer(null);
        await rechargerNiches();
        return;
      }
      if (type === 'supprimer') {
        await axios.delete(`${API}/prospection-medias/${encodeURIComponent(media.id)}`);
        setInfo(`${COURT[media.format]} placé dans la Corbeille (restaurable). Les autres versions ne sont pas touchées.`);
      } else {
        await axios.patch(`${API}/prospection-medias/${encodeURIComponent(media.id)}`, { statut: 'validee' });
      }
      setAConfirmer(null);
      await charger();
    } catch (e) {
      setInfo(erreurLisible(e, type === 'valider' ? 'Validation refusée.' : (type === 'archiver_niche' || type === 'reactiver_niche' ? 'Changement refusé.' : 'Suppression refusée.')));
      setAConfirmer(null);
    } finally { setEnCours(false); }
  };

  // Ouvrir l'éditeur sur un ORIGINAL, ou sur l'original d'un export / d'une miniature.
  const ouvrirEditeur = (media, ratio = null) => {
    if (media.format === 'original') { setEditeur({ niche: media.niche, original: media, fichierLocal: null, edition: null, ratio }); return; }
    const original = (medias || []).find((d) => d.id === media.source_id);
    if (!original) { setInfo('L’original de cette version est introuvable (supprimé ?). Ajoute un original pour la refaire.'); return; }
    setEditeur({ niche: media.niche, original, fichierLocal: null, edition: media.edition || null, ratio: null });
  };

  // « + Ajouter » : avec un original, on fabrique la version dans l'éditeur ; sans, on l'ajoute.
  const ajouter = (niche, format) => {
    const original = parNiche[niche].actuels.original;
    if (format !== 'original' && original && estFichier(original)) {
      ouvrirEditeur(original, RATIO_DU_FORMAT[format] || null);
      return;
    }
    setAjout({ niche, format, mode: format === 'original' || !original ? 'fichier' : 'lien' });
  };

  const basculer = (id) => { setOuverte((o) => (o === id ? '' : id)); setAjout(null); setArchivesOuvert(false); };

  // V598 : créer / renommer — la fenêtre attend la réponse du serveur, puis se ferme.
  const enregistrerNiche = async (nom) => {
    const f = fenetreNiche;
    if (f.type === 'creer') {
      await axios.post(`${API}/prospection-niches`, { nom });
      setInfo(`Niche « ${nom} » ajoutée. Elle est vide : aucun prospect, message ni lien n'a été créé.`);
    } else {
      await axios.patch(`${API}/prospection-niches/${encodeURIComponent(f.niche.id)}`, { nom });
      setInfo(`Niche renommée en « ${nom} ». Ses médias restent reliés.`);
    }
    setFenetreNiche(null);
    await rechargerNiches();
  };
  // V600 : une niche dans la Corbeille n'apparaît ni dans les actives, ni dans les archivées.
  const nichesActives = niches.filter((n) => n.active !== false && !n.supprimee);
  const nichesArchivees = niches.filter((n) => n.active === false && !n.supprimee);
  /* V600 — avant de supprimer, les VRAIS comptes (prospects, médias, liens) viennent du serveur. */
  const demanderSuppressionNiche = async (n) => {
    setInfo('');
    try {
      const r = await axios.get(`${API}/prospection-niches/${encodeURIComponent(n.id)}/contenu`);
      setAConfirmer({ type: 'supprimer_niche', niche: n, contenu: (r.data && r.data.contenu) || { prospects: 0, medias: 0, liens: 0 } });
    } catch (e) {
      setInfo(erreurLisible(e, 'Impossible de lire le contenu de la niche.'));
    }
  };

  if (!medias) return <EtatLecture chargement={!erreur} erreur={erreur} onReessayer={charger} />;
  const validees = (medias || []).filter((d) => d.statut === 'validee').length;

  return (
    <section data-testid="prospection-medias" aria-label="Médias de prospection" style={{ color: TEXTE }}>
      <div data-testid="pm-bandeau" style={{ fontSize: 12, color: DOUX, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        <span style={{ width: 7, height: 7, borderRadius: 4, background: 'rgb(252,211,77)', flexShrink: 0 }} />
        Vidéos en refonte · aucun envoi automatique · validées : <strong data-testid="pm-validees" style={{ color: TEXTE }}>{validees}</strong>
      </div>
      {info && <div data-testid="pm-info" style={{ marginTop: 8, fontSize: 12, padding: '6px 10px', borderRadius: 8, background: 'rgba(147,197,253,0.10)', border: '1px solid rgba(147,197,253,0.35)' }}>{info}</div>}

      <div style={{ marginTop: 10, border: `1px solid ${BORD}`, borderRadius: 12, overflow: 'hidden' }}>
        {nichesActives.map((n, i) => {
          const g = parNiche[n.cle] || { actuels: {}, archives: [] };
          const lettre = lettreNiche(n.ordre);
          const st = STATUTS_MEDIA[statutNiche(g.actuels)];
          const presents = Object.values(g.actuels);
          const aVerifier = presents.filter((m) => m.statut === 'a_verifier').length;
          const ouvert = ouverte === n.cle;
          const actionsNiche = [
            { libelle: 'Renommer', onClick: () => setFenetreNiche({ type: 'renommer', niche: n }), testid: `pm-niche-renommer-${lettre}` },
            { libelle: 'Archiver', onClick: () => setAConfirmer({ type: 'archiver_niche', niche: n }), testid: `pm-niche-archiver-${lettre}` },
            // V600 : Supprimer = Corbeille, pour TOUTE niche ; son contenu n'est jamais supprimé.
            { libelle: 'Supprimer', icone: CORBEILLE, danger: true, onClick: () => demanderSuppressionNiche(n), testid: `pm-niche-supprimer-${lettre}` },
          ];
          return (
            <div key={n.id} data-testid={`pm-niche-${lettre}`} style={{ borderTop: i ? `1px solid ${BORD}` : 'none' }}>
              <div style={{ display: 'flex', alignItems: 'center', background: ouvert ? 'rgba(var(--primary-rgb, 217, 28, 210), 0.08)' : 'transparent' }}>
                <button type="button" onClick={() => basculer(n.cle)} aria-expanded={ouvert} data-testid={`pm-niche-ligne-${lettre}`}
                  style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: 10, padding: '11px 6px 11px 12px', background: 'transparent', border: 'none', color: TEXTE, cursor: 'pointer', textAlign: 'left' }}>
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span style={{ fontSize: 13, fontWeight: 700 }} data-testid={`pm-nom-${lettre}`}>{lettre} — {n.nom}</span>
                    <span style={{ display: 'block', fontSize: 11, color: DOUX, marginTop: 2 }} data-testid={`pm-resume-${lettre}`}>
                      {presents.length ? `${presents.length} média${presents.length > 1 ? 's' : ''}${aVerifier ? ` · ${aVerifier} à vérifier` : ''}` : 'Aucun média'}
                    </span>
                  </span>
                  <Pastille ton={st.ton} testid={`pm-statut-niche-${lettre}`}>{st.libelle}</Pastille>
                  <span style={{ display: 'inline-flex', transition: 'transform .15s', transform: ouvert ? 'rotate(90deg)' : 'none', color: DOUX }}><Icone d={CHEVRON} /></span>
                </button>
                <div style={{ padding: '0 10px 0 2px' }}><MenuPlus actions={actionsNiche} testid={`pm-niche-menu-${lettre}`} /></div>
              </div>
              {ouvert && (
                <div data-testid={`pm-contenu-${lettre}`} style={{ padding: '4px 12px 12px' }}>
                  <div style={{ display: 'grid', gap: 8, gridTemplateColumns: 'repeat(auto-fill, minmax(min(300px, 100%), 1fr))' }}>
                    {FORMATS.map((fmt) => (
                      <Emplacement key={fmt.id} format={fmt} media={g.actuels[fmt.id]} enCours={enCours}
                        onEditer={(m) => ouvrirEditeur(m)} onAjouter={(f) => ajouter(n.cle, f)} onStatut={changerStatut}
                        onValider={(m) => setAConfirmer({ type: 'valider', media: m })}
                        onSupprimer={(m) => setAConfirmer({ type: 'supprimer', media: m })} />
                    ))}
                  </div>
                  {ajout && ajout.niche === n.cle && (
                    <div style={{ marginTop: 8 }}>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }} role="group" aria-label="Type d'ajout">
                        <Bouton discret={ajout.mode !== 'fichier'} onClick={() => setAjout((a) => ({ ...a, mode: 'fichier' }))} testid={`pm-mode-fichier-${lettre}`}>Fichier original</Bouton>
                        {ajout.format !== 'original' && <Bouton discret={ajout.mode !== 'lien'} onClick={() => setAjout((a) => ({ ...a, mode: 'lien' }))} testid={`pm-mode-lien-${lettre}`}>Lien public</Bouton>}
                      </div>
                      {ajout.mode === 'fichier'
                        ? <FormulaireOriginal API={API} niche={n.cle}
                            onFini={(m) => { setAjout(null); if (m) { setInfo(m); charger(); } }}
                            onOuvrirEditeur={(original, fichierLocal, m) => { setAjout(null); setInfo(m); charger(); setEditeur({ niche: n.cle, original, fichierLocal, edition: null, ratio: null }); }} />
                        : <FormulaireAjout API={API} niche={n.cle} formatInitial={ajout.format}
                            onFini={(m) => { setAjout(null); if (m) { setInfo(m); charger(); } }} />}
                    </div>
                  )}
                  {g.archives.length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      <button type="button" onClick={() => setArchivesOuvert((a) => !a)} data-testid={`pm-archives-${lettre}`}
                        style={{ border: 'none', background: 'transparent', color: DOUX, fontSize: 11, cursor: 'pointer', padding: 0, textDecoration: 'underline' }}>
                        {archivesOuvert ? 'Masquer les archives' : `Archives (${g.archives.length})`}
                      </button>
                      {archivesOuvert && (
                        <ul style={{ margin: '6px 0 0', paddingLeft: 18, fontSize: 11, color: DOUX }}>
                          {g.archives.map((a) => (
                            <li key={a.id} style={{ wordBreak: 'break-word' }}>
                              {COURT[a.format]} · {a.version || '—'} · {jour(a.created_at)} ·{' '}
                              <a href={a.url} target="_blank" rel="noopener noreferrer" style={{ color: TEXTE }}>ouvrir</a>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'center', marginTop: 8 }}>
        <button type="button" onClick={() => setFenetreNiche({ type: 'creer' })} data-testid="pm-niche-ajouter"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 4, border: 'none', background: 'transparent', color: 'var(--primary-color, #D91CD2)', fontSize: 12, fontWeight: 700, cursor: 'pointer', padding: '4px 0' }}>
          <Icone d={PLUS} taille={14} />Ajouter une niche
        </button>
        {nichesArchivees.length > 0 && (
          <button type="button" onClick={() => setNichesArchiveesOuvert((o) => !o)} data-testid="pm-niches-archivees"
            style={{ border: 'none', background: 'transparent', color: DOUX, fontSize: 11, cursor: 'pointer', padding: 0, textDecoration: 'underline' }}>
            {nichesArchiveesOuvert ? 'Masquer les niches archivées' : `Niches archivées (${nichesArchivees.length})`}
          </button>
        )}
      </div>
      {nichesArchiveesOuvert && nichesArchivees.length > 0 && (
        <div style={{ marginTop: 6, display: 'grid', gap: 4 }} data-testid="pm-liste-archivees">
          {nichesArchivees.map((n) => {
            const nb = Object.keys((parNiche[n.cle] || { actuels: {} }).actuels).length;
            return (
              <div key={n.id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: DOUX, padding: '6px 10px', border: `1px dashed ${BORD}`, borderRadius: 8 }}>
                <span style={{ flex: 1, minWidth: 0 }}>{lettreNiche(n.ordre)} — {n.nom} · {nb ? `${nb} média${nb > 1 ? 's' : ''} conservé${nb > 1 ? 's' : ''}` : 'vide'}</span>
                <Bouton discret onClick={() => setAConfirmer({ type: 'reactiver_niche', niche: n })} testid={`pm-niche-reactiver-${lettreNiche(n.ordre)}`}>Réactiver</Bouton>
              </div>
            );
          })}
        </div>
      )}

      {fenetreNiche && (
        <FenetreNomNiche
          titre={fenetreNiche.type === 'creer' ? 'Ajouter une niche' : 'Renommer la niche'}
          initial={fenetreNiche.type === 'renommer' ? fenetreNiche.niche.nom : ''}
          libelleOk={fenetreNiche.type === 'creer' ? 'Créer' : 'Renommer'}
          onOk={enregistrerNiche} onAnnuler={() => setFenetreNiche(null)} />
      )}

      {editeur && (
        <FenetreEditeur onFermer={() => setEditeur(null)}>
          <Suspense fallback={<div style={{ padding: 20, fontSize: 12, color: DOUX }} data-testid="pm-editeur-chargement">Chargement de l'éditeur vidéo…</div>}>
            <ProspectionVideoEditeur API={API} niche={editeur.niche} original={editeur.original} fichierLocal={editeur.fichierLocal}
              editionInitiale={editeur.edition} ratioInitial={editeur.ratio} enFenetre
              nicheLibelle={(() => { const n = niches.find((x) => x.cle === editeur.niche); return n ? `${lettreNiche(n.ordre)} — ${n.nom}` : ''; })()}
              onFermer={() => setEditeur(null)}
              onEnregistre={(m) => { setInfo(m); charger(); }} />
          </Suspense>
        </FenetreEditeur>
      )}

      {aConfirmer && (
        <Confirmation
          titre={aConfirmer.type === 'supprimer_niche' ? `Supprimer « ${aConfirmer.niche.nom} » ?`
            : { supprimer: 'Supprimer ce média ?', valider: 'Valider cette vidéo ?', archiver_niche: 'Archiver cette niche ?', reactiver_niche: 'Réactiver cette niche ?' }[aConfirmer.type]}
          texte={{
            supprimer: () => `${COURT[aConfirmer.media.format]} de la niche ${lettreDeCle[aConfirmer.media.niche] || ''} part dans la Corbeille (restaurable). Les autres versions et le fichier d'origine ne sont pas touchés.`,
            valider: () => 'Elle devient la vidéo validée de ce format pour la niche. Aucun envoi ne part.',
            archiver_niche: () => `« ${aConfirmer.niche.nom} » disparaît de la liste. Ses médias et liens sont conservés ; tu peux la réactiver.`,
            reactiver_niche: () => `« ${aConfirmer.niche.nom} » revient dans la liste, avec ses médias.`,
            supprimer_niche: () => {
              const c = aConfirmer.contenu || {};
              const pl = (n, mot) => `${n} ${mot}${n > 1 ? 's' : ''}`;
              return `Cette niche contient : ${pl(c.prospects || 0, 'prospect')}, ${pl(c.medias || 0, 'média')}, ${pl(c.liens || 0, 'lien')}. `
                + 'Elle sera retirée de la prospection active et placée dans la Corbeille. '
                + 'Les prospects, médias et historiques ne seront pas supprimés.';
            },
          }[aConfirmer.type]()}
          libelleOk={{ supprimer: 'Supprimer', valider: 'Valider', archiver_niche: 'Archiver', reactiver_niche: 'Réactiver', supprimer_niche: 'Supprimer la niche' }[aConfirmer.type]}
          enCours={enCours} onOk={confirmer} onAnnuler={() => setAConfirmer(null)} />
      )}
    </section>
  );
}
