/**
 * V620 — UN MÉDIA (vidéo OU image) JOINT À UNE RÉPONSE PARTENAIRE.
 *
 * AUCUNE NOUVELLE BIBLIOTHÈQUE : la liste est celle de l'onglet Prospection → Médias
 * (`GET /prospection-medias`, V595-V601), l'import passe par l'envoi EXISTANT
 * (`uploadToCloudinary` = /api/coach/upload-asset | upload-chunk → /api/files, V418).
 * L'écran ne transmet qu'une RÉFÉRENCE (`media_id` ou `fichier_url`) : le serveur
 * résout l'adresse, la miniature et le titre, et refuse ce qui n'est pas au coach.
 *
 * V625 — PLUSIEURS fichiers (vidéos, images, PDF ; 6 au plus), chacun retirable.
 * Rien ne part d'ici : les fichiers sont enregistrés AVEC le texte (« Enregistrer »),
 * puis affichés dans l'aperçu serveur avant « Confirmer l'envoi ». Dans l'e-mail, chaque
 * fichier est une carte avec un lien (jamais une pièce jointe).
 * Lecture vidéo : jamais d'autoplay. Couleurs : var(--primary-color) / --primary-rgb.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import SvgIcon from '../../SvgIcon';
import { uploadToCloudinary, MESSAGE_PDF_LOURD as MSG_PDF, PDF_MAX_MO as MAX_PDF } from '../../CloudinaryUploadButton';
import { instantApercu } from '../ChoixMedia';

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const RGB = 'var(--primary-rgb, 217, 28, 210)';
const TEXTE = '#fff';
const DOUX = 'rgba(255,255,255,0.68)';
const COURT = { original: 'Original', '16_9': '16:9', '9_16': '9:16', '1_1': '1:1', miniature: 'Image', document: 'PDF' };
const MIME_VIDEO = ['video/mp4', 'video/webm', 'video/quicktime'];
const MIME_IMAGE = ['image/jpeg', 'image/png', 'image/webp'];
const MIME_PDF = 'application/pdf';
const PDF_MAX_MO = MAX_PDF || 20;   // V625 : alignée sur le serveur (V625_PDF_MAX_MO)
const MESSAGE_PDF_LOURD = MSG_PDF || `Ce PDF dépasse la taille maximale autorisée de ${PDF_MAX_MO} Mo.`;
/** V625 — même plafond que le serveur (V625_MEDIAS_MAX). */
export const MAX_FICHIERS = 6;

/** V625 — 1 572 864 -> « 1,5 Mo ». PURE. */
export function tailleLisible(octets) {
  const n = Number(octets);
  if (!Number.isFinite(n) || n <= 0) return '';
  if (n < 1024 * 1024) return `${Math.max(1, Math.round(n / 1024))} Ko`;
  return `${(n / (1024 * 1024)).toFixed(1).replace('.', ',')} Mo`;
}

/** V625 — « 2026-10-19T… » -> « 19/10/2026 ». PURE. */
export function dateLisible(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ''));
  return m ? `${m[3]}/${m[2]}/${m[1]}` : '';
}

/**
 * V625 — LES fichiers d'un brouillon / d'un aperçu / d'un message du fil : la liste
 * `medias` si elle existe, sinon l'ancien `media` seul (V620), sinon aucun. PURE.
 */
export function mediasDe(objet) {
  const o = objet || {};
  if (Array.isArray(o.medias)) return o.medias.filter((m) => m && urlSure(m.url));
  return o.media && urlSure(o.media.url) ? [o.media] : [];
}

const bouton = (plein) => ({
  minHeight: '34px', padding: '6px 12px', borderRadius: '8px', fontSize: '12px', fontWeight: 600,
  cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '6px', color: TEXTE,
  background: plein ? PRIMAIRE : 'rgba(255,255,255,0.07)',
  border: plein ? 'none' : `1px solid rgba(${RGB}, 0.45)`,
});

/** « AFROBOOST_9_ETUDIANTS_16x9.mp4 » → « AFROBOOST 9 ETUDIANTS 16x9 » (même règle que le serveur). PURE. */
export function titreMedia(nom) {
  const t = String(nom || '').trim().replace(/\.[A-Za-z0-9]{2,4}$/, '').replace(/[_\s]+/g, ' ').trim();
  return t.slice(0, 120) || 'Afroboost';
}

/** Une adresse servie par Afroboost ou en https — jamais autre chose dans un src / href. PURE. */
export function urlSure(u) {
  const v = String(u || '').trim();
  if (/^\/api\/files\/[A-Za-z0-9_-]+\/[A-Za-z0-9._-]+$/.test(v)) return v;
  if (/^https:\/\/[A-Za-z0-9.-]+(:\d+)?\/[^\s"'<>]*$/.test(v)) return v;
  return '';
}

export function dureeLisible(s) {
  const n = Number(s);
  if (!Number.isFinite(n) || n <= 0) return '';
  const m = Math.floor(n / 60);
  const r = Math.round(n % 60);
  return `${m}:${String(r).padStart(2, '0')}`;
}

/**
 * La bibliothèque telle que l'onglet Médias la range → éléments choisissables. PURE.
 * Archivés exclus ; la miniature d'une vidéo = l'image « miniature » non archivée du même original.
 */
export function elementsBibliotheque(medias, niches) {
  const liste = (Array.isArray(medias) ? medias : []).filter((m) => m && m.statut !== 'archivee' && urlSure(m.url));
  const nomNiche = {};
  (Array.isArray(niches) ? niches : []).forEach((n) => { if (n && n.cle) nomNiche[n.cle] = n.nom; });
  const miniatures = {};
  liste.filter((m) => m.format === 'miniature' && m.source_id).forEach((m) => {
    if (!miniatures[m.source_id]) miniatures[m.source_id] = m.url;
  });
  return liste.map((m) => {
    const image = m.format === 'miniature';
    const doc = m.format === 'document';   // V625 : brochure PDF
    const source = m.format === 'original' ? m.id : m.source_id;
    const f = m.fichier || {};
    return {
      media_id: m.id, type: doc ? 'document' : (image ? 'image' : 'video'), url: m.url,
      miniature_url: doc ? null : (image ? m.url : (miniatures[source] || null)),
      titre: titreMedia(f.nom || m.version), format: m.format, duree: doc ? null : (f.duree || null),
      taille: doc ? (f.taille || null) : undefined, date: doc ? (m.created_at || null) : undefined,
      niche_nom: nomNiche[m.niche] || null, public: (m.cible && m.cible.nom) || null,
    };
  });
}

/** Filtre « Tous / Vidéos / Images / Documents » + recherche (titre, niche, public, format). PURE. */
export function filtrerBibliotheque(elements, filtre, recherche) {
  const q = String(recherche || '').trim().toLowerCase();
  return (elements || []).filter((e) => {
    if (filtre === 'video' && e.type !== 'video') return false;
    if (filtre === 'image' && e.type !== 'image') return false;
    if (filtre === 'document' && e.type !== 'document') return false;
    if (!q) return true;
    return [e.titre, e.niche_nom, e.public, COURT[e.format] || e.format]
      .some((v) => String(v || '').toLowerCase().indexOf(q) !== -1);
  });
}

/** La référence que le serveur attend (jamais l'adresse d'un média de la bibliothèque). PURE. */
export function referenceMedia(m) {
  if (!m) return null;
  if (m.media_id) return { media_id: m.media_id };
  return { fichier_url: m.url, miniature_url: m.miniature_url || undefined, duree: m.duree || undefined, nom: m.titre };
}

/** La première « vraie » image d'une vidéo locale, en JPEG. Rien n'est lu sur le réseau. */
function capturerMiniature(fichier) {
  return new Promise((resolve) => {
    let url = '';
    try { url = URL.createObjectURL(fichier); } catch (e) { resolve(null); return; }
    const v = document.createElement('video');
    const fin = (r) => { try { URL.revokeObjectURL(url); } catch (e) { /* ignore */ } resolve(r); };
    const garde = setTimeout(() => fin(null), 15000);
    v.muted = true; v.playsInline = true; v.preload = 'metadata'; v.src = url;
    v.onloadedmetadata = () => { try { v.currentTime = instantApercu(v.duration); } catch (e) { clearTimeout(garde); fin(null); } };
    v.onseeked = () => {
      try {
        const l = Math.min(960, v.videoWidth || 960);
        const h = Math.round(l * ((v.videoHeight || 540) / (v.videoWidth || 960)));
        const c = document.createElement('canvas');
        c.width = l; c.height = h;
        c.getContext('2d').drawImage(v, 0, 0, l, h);
        c.toBlob((b) => { clearTimeout(garde); fin(b ? { blob: b, duree: v.duration } : null); }, 'image/jpeg', 0.85);
      } catch (e) { clearTimeout(garde); fin(null); }
    };
    v.onerror = () => { clearTimeout(garde); fin(null); };
  });
}

function IconeLecture({ taille = 34 }) {
  return (
    <span aria-hidden="true" style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <span style={{ width: taille, height: taille, borderRadius: '50%', background: 'rgba(0,0,0,0.6)',
                     display: 'flex', alignItems: 'center', justifyContent: 'center', color: TEXTE }}>
        <SvgIcon name="play" size={Math.round(taille * 0.5)} />
      </span>
    </span>
  );
}

/** La vignette : l'image, ou un cadre neutre avec ▶ si aucune miniature n'existe. */
export function Vignette({ media, largeur = 96 }) {
  const src = urlSure(media && media.miniature_url);
  const h = Math.round(largeur * 9 / 16);
  if (media && media.type === 'document') {   // V625 : un PDF n'a pas d'image, une icône document
    return (
      <span data-testid="vignette-document"
            style={{ width: largeur, height: h, flex: '0 0 auto', borderRadius: '8px', display: 'flex',
                     alignItems: 'center', justifyContent: 'center', color: TEXTE,
                     background: `rgba(${RGB}, 0.18)`, border: `1px solid rgba(${RGB}, 0.4)` }}>
        <SvgIcon name="fileText" size={Math.max(18, Math.round(largeur / 4))} />
      </span>
    );
  }
  return (
    <span style={{ position: 'relative', width: largeur, height: h, flex: '0 0 auto', borderRadius: '8px', overflow: 'hidden',
                   background: 'rgba(0,0,0,0.55)', display: 'block' }}>
      {src ? <img src={src} alt="" loading="lazy" style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} /> : null}
      {media && media.type === 'video' ? <IconeLecture taille={Math.max(22, Math.round(largeur / 3.4))} /> : null}
      {!src && media && media.type === 'image' ? (
        <span style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: DOUX }}>
          <SvgIcon name="image" size={18} />
        </span>
      ) : null}
    </span>
  );
}

/** La carte d'un média joint / envoyé. `actions` = boutons en second rang. */
export function CarteMedia({ media, libelle, testid = 'media-joint', actions = null, lien = false }) {
  if (!media || !urlSure(media.url)) return null;
  const doc = media.type === 'document';   // V625
  const video = !doc && media.type !== 'image';
  const details = doc
    ? ['Document PDF', tailleLisible(media.taille), dateLisible(media.date)].filter(Boolean).join(' · ')
    : [media.niche_nom, media.public, COURT[media.format], dureeLisible(media.duree)].filter(Boolean).join(' · ');
  return (
    <div data-testid={testid} data-type={media.type}
         style={{ marginTop: '8px', padding: '8px', borderRadius: '10px', background: 'rgba(0,0,0,0.25)',
                  border: `1px solid rgba(${RGB}, 0.4)`, minWidth: 0 }}>
      <div style={{ fontSize: '10px', fontWeight: 700, letterSpacing: '0.05em', color: DOUX, marginBottom: '6px',
                    display: 'flex', alignItems: 'center', gap: '5px' }}>
        <SvgIcon name={doc ? 'fileText' : (video ? 'video' : 'image')} size={13} />
        {libelle || (doc ? 'DOCUMENT PDF JOINT' : (video ? 'VIDÉO JOINTE' : 'IMAGE JOINTE'))}
      </div>
      <div style={{ display: 'flex', gap: '10px', alignItems: 'center', minWidth: 0 }}>
        <Vignette media={media} />
        <div style={{ minWidth: 0, flex: '1 1 auto' }}>
          <div data-testid={`${testid}-titre`} style={{ fontSize: '12.5px', fontWeight: 600, color: TEXTE,
                                                        overflowWrap: 'anywhere', display: 'flex', gap: '5px', alignItems: 'center' }}>
            {video ? <SvgIcon name="play" size={12} /> : null}<span>{media.titre || 'Afroboost'}</span>
          </div>
          {details ? <div style={{ fontSize: '11px', color: DOUX, marginTop: '2px' }}>{details}</div> : null}
          {lien ? (
            <a href={urlSure(media.url)} target="_blank" rel="noopener noreferrer" data-testid={`${testid}-voir`}
               style={{ fontSize: '11.5px', fontWeight: 600, color: 'color-mix(in srgb, var(--primary-color, #D91CD2) 80%, white)',
                        display: 'inline-block', marginTop: '4px' }}>
              {doc ? 'Voir / télécharger le document' : (video ? 'Voir la vidéo' : 'Voir l’image')}
            </a>
          ) : null}
        </div>
      </div>
      {actions ? <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '8px' }}>{actions}</div> : null}
    </div>
  );
}

function Fenetre({ onFermer, children }) {
  useEffect(() => {
    const echap = (e) => { if (e.key === 'Escape') onFermer(); };
    window.addEventListener('keydown', echap);
    return () => window.removeEventListener('keydown', echap);
  }, [onFermer]);
  return (
    <div role="dialog" aria-modal="true" aria-label="Ajouter un média" data-testid="media-fenetre"
         onClick={(e) => { if (e.target === e.currentTarget) onFermer(); }}
         style={{ position: 'fixed', inset: 0, zIndex: 10050, background: 'rgba(0,0,0,0.7)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 'min(16px, 3vw)' }}>
      <div style={{ width: '100%', maxWidth: '640px', maxHeight: '100%', display: 'flex', flexDirection: 'column',
                    background: 'rgb(18,18,24)', borderRadius: '14px', border: `1px solid rgba(${RGB}, 0.45)`,
                    boxSizing: 'border-box', overflow: 'hidden' }}>
        {children}
      </div>
    </div>
  );
}

function Bibliotheque({ API, onChoisir, choisis }) {
  const [etat, setEtat] = useState({ chargement: true, erreur: '', elements: [] });
  const [filtre, setFiltre] = useState('tous');
  const [recherche, setRecherche] = useState('');
  useEffect(() => {
    let vivant = true;
    Promise.all([
      axios.get(`${API}/prospection-medias`, { params: { limit: 50, offset: 0 } }),
      axios.get(`${API}/prospection-niches`).catch(() => ({ data: {} })),
    ]).then(([m, n]) => {
      if (!vivant) return;
      setEtat({ chargement: false, erreur: '',
                elements: elementsBibliotheque((m && m.data && m.data.medias) || [], (n && n.data && n.data.niches) || []) });
    }).catch(() => { if (vivant) setEtat({ chargement: false, erreur: 'Bibliothèque indisponible pour le moment.', elements: [] }); });
    return () => { vivant = false; };
  }, [API]);
  const visibles = useMemo(() => filtrerBibliotheque(etat.elements, filtre, recherche), [etat.elements, filtre, recherche]);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', minHeight: 0, flex: '1 1 auto' }}>
      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', alignItems: 'center' }}>
        {[['tous', 'Tous'], ['video', 'Vidéos'], ['image', 'Images'], ['document', 'Documents']].map(([k, l]) => (
          <button key={k} type="button" data-testid={`media-filtre-${k}`} aria-pressed={filtre === k}
                  onClick={() => setFiltre(k)}
                  style={{ ...bouton(filtre === k), minHeight: '30px', padding: '4px 11px', borderRadius: '999px' }}>{l}</button>
        ))}
        <label style={{ flex: '1 1 160px', minWidth: 0, display: 'flex', alignItems: 'center', gap: '6px', color: DOUX,
                        padding: '0 9px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.18)', background: 'rgba(0,0,0,0.3)' }}>
          <SvgIcon name="search" size={14} />
          <input type="search" value={recherche} onChange={(e) => setRecherche(e.target.value)} placeholder="Rechercher"
                 data-testid="media-recherche" aria-label="Rechercher un média"
                 style={{ flex: '1 1 auto', minWidth: 0, height: '32px', background: 'transparent', border: 'none', outline: 'none',
                          color: TEXTE, fontSize: '13px' }} />
        </label>
      </div>
      {etat.chargement ? <div style={{ fontSize: '12.5px', color: DOUX }}>Chargement de la bibliothèque…</div> : null}
      {etat.erreur ? <div role="status" style={{ fontSize: '12.5px', color: 'rgb(252,165,165)' }}>{etat.erreur}</div> : null}
      {!etat.chargement && !etat.erreur && !visibles.length ? (
        <div data-testid="media-vide" style={{ fontSize: '12.5px', color: DOUX }}>Aucun média ne correspond.</div>
      ) : null}
      <div data-testid="media-liste" style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)', gap: '6px', overflowY: 'auto', minHeight: 0 }}>
        {visibles.map((e) => {
          const choisi = (choisis || []).indexOf(e.media_id) !== -1;
          return (
            <div key={e.media_id} data-testid="media-element" data-type={e.type}
                 style={{ display: 'flex', gap: '10px', alignItems: 'center', padding: '7px', borderRadius: '10px', minWidth: 0,
                          background: choisi ? `rgba(${RGB}, 0.16)` : 'rgba(255,255,255,0.04)',
                          border: `1px solid ${choisi ? PRIMAIRE : 'rgba(255,255,255,0.08)'}` }}>
              <Vignette media={e} largeur={88} />
              <div style={{ minWidth: 0, flex: '1 1 auto' }}>
                <div style={{ fontSize: '12.5px', fontWeight: 600, color: TEXTE, overflowWrap: 'anywhere' }}>{e.titre}</div>
                <div style={{ fontSize: '11px', color: DOUX, marginTop: '2px' }}>
                  {e.type === 'document'
                    ? ['Document PDF', tailleLisible(e.taille), dateLisible(e.date)].filter(Boolean).join(' · ')
                    : [e.public || e.niche_nom, COURT[e.format] || e.format, dureeLisible(e.duree)].filter(Boolean).join(' · ')}
                </div>
              </div>
              <button type="button" data-testid="media-choisir" disabled={choisi} onClick={() => onChoisir([e])}
                      style={{ ...bouton(true), flex: '0 0 auto', opacity: choisi ? 0.6 : 1 }}>
                {choisi ? 'Choisi' : 'Choisir'}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** V625 — le type d'un fichier local, ou null s'il n'est pas pris en charge. PURE. */
export function typeFichier(f) {
  const t = (f && f.type) || '';
  if (MIME_VIDEO.indexOf(t) !== -1) return 'video';
  if (MIME_IMAGE.indexOf(t) !== -1) return 'image';
  if (t === MIME_PDF) return 'document';
  return null;
}

/** V625 — contrôle AVANT tout envoi : type, taille du PDF, nombre. Rend un message ou ''. PURE. */
export function refusFichiers(fichiers, place) {
  const liste = Array.from(fichiers || []);
  if (!liste.length) return '';
  if (liste.length > place) {
    return place > 0 ? `Encore ${place} fichier${place > 1 ? 's' : ''} au plus pour cette réponse (${MAX_FICHIERS} au total).`
      : `${MAX_FICHIERS} fichiers au plus par réponse.`;
  }
  if (liste.some((f) => !typeFichier(f))) return 'Choisis une vidéo MP4, WebM ou MOV, une image JPEG, PNG, WebP, ou un PDF.';
  if (liste.some((f) => typeFichier(f) === 'document' && f.size > PDF_MAX_MO * 1024 * 1024)) return MESSAGE_PDF_LOURD;
  return '';
}

function Importer({ onChoisir, place }) {
  const entree = useRef(null);
  const [etat, setEtat] = useState({ phase: '', pct: 0, msg: '', rang: 0, total: 0 });
  const surFichier = async (ev) => {
    const fichiers = Array.from((ev.target.files) || []);
    ev.target.value = '';
    if (!fichiers.length) return;
    const refus = refusFichiers(fichiers, place);
    if (refus) {
      setEtat({ phase: '', pct: 0, msg: refus, rang: 0, total: 0 });
      return;
    }
    const prets = [];
    try {
      for (let i = 0; i < fichiers.length; i += 1) {
        const f = fichiers[i];
        const type = typeFichier(f);
        const video = type === 'video';
        let mini = null;
        if (video) { setEtat({ phase: 'lecture', pct: 0, msg: '', rang: i + 1, total: fichiers.length }); mini = await capturerMiniature(f); }
        setEtat({ phase: 'envoi', pct: 0, msg: '', rang: i + 1, total: fichiers.length });
        const r = await uploadToCloudinary(f, { onProgress: (p) => setEtat((s) => ({ ...s, pct: Math.round(p) })) });
        let miniatureUrl = type === 'image' ? r.url : null;
        if (video && mini && mini.blob) {
          try {
            const jpg = new File([mini.blob], `${titreMedia(f.name).replace(/\s+/g, '_')}_miniature.jpg`, { type: 'image/jpeg' });
            miniatureUrl = (await uploadToCloudinary(jpg)).url;
          } catch (e) { miniatureUrl = null; /* la vidéo part sans miniature : carte ▶ seule */ }
        }
        prets.push({ media_id: null, origine: 'import', type, url: r.url,
                     miniature_url: miniatureUrl, titre: titreMedia(f.name),
                     taille: type === 'document' ? f.size : undefined,
                     duree: video && mini && Number.isFinite(mini.duree) ? Math.round(mini.duree * 10) / 10 : null });
      }
      setEtat({ phase: '', pct: 0, msg: '', rang: 0, total: 0 });
      onChoisir(prets);
    } catch (e) {
      const d = e && e.response && e.response.data && e.response.data.detail;
      setEtat({ phase: '', pct: 0, rang: 0, total: 0,
                msg: typeof d === 'string' ? d : ((e && e.message) || "L'import n'a pas abouti.") });
      if (prets.length) onChoisir(prets, true);   // ceux déjà envoyés restent joints
    }
  };
  const occupe = etat.phase !== '';
  return (
    <div style={{ display: 'grid', gap: '10px' }}>
      <div style={{ fontSize: '12.5px', color: DOUX, lineHeight: 1.5 }}>
        Le fichier est envoyé comme dans l’onglet Médias : vidéo (MP4, MOV, WebM), image, ou PDF
        ({PDF_MAX_MO} Mo au plus). Tu peux en choisir plusieurs. Ils sont joints à cette réponse,
        sans modifier ta bibliothèque.
      </div>
      <input ref={entree} type="file" hidden multiple data-testid="media-fichier"
             accept={MIME_VIDEO.concat(MIME_IMAGE, [MIME_PDF]).join(',')} onChange={surFichier} />
      <div>
        <button type="button" data-testid="media-importer-video" disabled={occupe}
                onClick={() => entree.current && entree.current.click()} style={{ ...bouton(true), opacity: occupe ? 0.6 : 1 }}>
          <SvgIcon name="upload" size={14} /> Importer une vidéo, une image ou un PDF
        </button>
      </div>
      {etat.total > 1 && occupe ? (
        <div data-testid="media-rang" style={{ fontSize: '12px', color: DOUX }}>Fichier {etat.rang} sur {etat.total}</div>
      ) : null}
      {etat.phase === 'lecture' ? <div style={{ fontSize: '12px', color: DOUX }}>Lecture de la vidéo…</div> : null}
      {etat.phase === 'envoi' ? (
        <div data-testid="media-progres" style={{ height: '8px', borderRadius: '99px', background: 'rgba(255,255,255,0.1)', overflow: 'hidden' }}>
          <div style={{ width: `${etat.pct}%`, height: '100%', background: PRIMAIRE }} />
        </div>
      ) : null}
      {etat.msg ? <div role="status" data-testid="media-import-erreur" style={{ fontSize: '12px', color: 'rgb(252,165,165)' }}>{etat.msg}</div> : null}
    </div>
  );
}

/**
 * V625 — les fichiers joints (une carte chacun, « Retirer ») + « Ajouter un média » /
 * « Ajouter un autre fichier ». `valeur` : la liste (un ancien objet seul est accepté) ;
 * `onChange(liste)` — jamais null, une liste vide quand tout est retiré.
 */
export default function MediaReponse({ API, valeur, onChange, desactive = false }) {
  const [ouvert, setOuvert] = useState(false);
  const [onglet, setOnglet] = useState('bibliotheque');
  const liste = Array.isArray(valeur) ? valeur.filter(Boolean) : (valeur ? [valeur] : []);
  const place = MAX_FICHIERS - liste.length;
  const ajouter = (nouveaux, garderOuvert) => {
    const vus = {};
    liste.forEach((m) => { vus[m.media_id || m.url] = true; });
    const ajout = (nouveaux || []).filter((m) => m && !vus[m.media_id || m.url]);
    onChange(liste.concat(ajout).slice(0, MAX_FICHIERS));
    if (!garderOuvert) setOuvert(false);
  };
  const retirer = (i) => onChange(liste.filter((_, j) => j !== i));
  return (
    <div data-testid="media-reponse">
      {liste.length ? (
        <div data-testid="medias-joints" style={{ display: 'grid', gap: '2px' }}>
          {liste.map((m, i) => (
            <CarteMedia key={`${m.media_id || m.url}-${i}`} media={m} actions={(
              <button type="button" data-testid="media-retirer" disabled={desactive} onClick={() => retirer(i)}
                      aria-label={`Retirer ${m.titre || 'ce fichier'}`} style={bouton(false)}>
                <SvgIcon name="trash" size={13} /> Retirer
              </button>
            )} />
          ))}
        </div>
      ) : null}
      {place > 0 ? (
        <button type="button" data-testid={liste.length ? 'ajouter-autre-fichier' : 'ajouter-media'} disabled={desactive}
                onClick={() => setOuvert(true)} style={{ ...bouton(false), marginTop: '7px' }}>
          <SvgIcon name={liste.length ? 'plus' : 'paperclip'} size={14} />
          {liste.length ? ' Ajouter un autre fichier' : ' Ajouter un média'}
        </button>
      ) : (
        <div data-testid="medias-plein" style={{ fontSize: '11.5px', color: DOUX, marginTop: '6px' }}>
          {MAX_FICHIERS} fichiers au plus par réponse.
        </div>
      )}
      {ouvert ? (
        <Fenetre onFermer={() => setOuvert(false)}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '12px 14px',
                        borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
            <strong style={{ flex: '1 1 auto', fontSize: '14px', color: TEXTE }}>Ajouter un média</strong>
            <button type="button" aria-label="Fermer" data-testid="media-fermer" onClick={() => setOuvert(false)}
                    style={{ ...bouton(false), minHeight: '32px', padding: '4px 8px' }}>
              <SvgIcon name="close" size={15} />
            </button>
          </div>
          <div role="tablist" style={{ display: 'flex', gap: '6px', padding: '10px 14px 0' }}>
            {[['bibliotheque', 'Bibliothèque'], ['importer', 'Importer']].map(([k, l]) => (
              <button key={k} type="button" role="tab" aria-selected={onglet === k} data-testid={`media-onglet-${k}`}
                      onClick={() => setOnglet(k)} style={bouton(onglet === k)}>{l}</button>
            ))}
          </div>
          <div style={{ padding: '12px 14px 14px', display: 'flex', flexDirection: 'column', minHeight: 0, flex: '1 1 auto', overflow: 'hidden' }}>
            {onglet === 'bibliotheque'
              ? <Bibliotheque API={API} onChoisir={ajouter} choisis={liste.map((m) => m.media_id).filter(Boolean)} />
              : <Importer onChoisir={ajouter} place={place} />}
          </div>
        </Fenetre>
      ) : null}
    </div>
  );
}
