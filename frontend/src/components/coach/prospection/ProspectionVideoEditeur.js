/**
 * V596 — PROSPECTION → MÉDIAS : L'ÉDITEUR / EXPORT VIDÉO (chargé à la demande).
 *
 * RÉUTILISE `VideoTrimEditor` tel quel (lecteur, Rejouer, son, timeline, poignées,
 * réglage −/+ au dixième, Réinitialiser, « Capturer cette image comme miniature »)
 * et y ajoute, POUR CET ÉCRAN SEULEMENT :
 *  - le choix du format (Auto / 16:9 / 9:16 / 1:1) et un VRAI cadre, déplaçable,
 *    dessiné sur l'aperçu : ce qui est hors du cadre est assombri et ne sera pas
 *    dans le fichier ;
 *  - « Exporter la vidéo » : un NOUVEAU MP4 (H.264 + AAC) fabriqué dans le
 *    navigateur (utils/videoExport.js) — l'original n'est jamais touché ;
 *  - l'aperçu du vrai fichier (durée, résolution, ratio, taille) AVANT tout envoi,
 *    puis « Enregistrer cette version » (statut « À vérifier », jamais « Validée »)
 *    ou « Remodifier ».
 *
 * Rien n'est envoyé à personne : ce composant range des fichiers, c'est tout.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import VideoTrimEditor from '../../VideoTrimEditor';
import { uploadToCloudinary } from '../../CloudinaryUploadButton';
import { libelleDetection, ratioDepuisDimensions } from '../../../utils/videoRatio';
import { formatTemps } from '../../../utils/videoTrim';
import {
  FORMATS_EXPORT, calculerCadrage, exporterVideo, exportEnCours, exportSupporteIci,
  nomExport, tailleLisible, validerMetadonnees, lireMetadonneesFichier,
} from '../../../utils/videoExport';
import { Bandeau, Bouton, DOUX, TEXTE, BORD } from './ui';

const COULEUR = 'var(--primary-color, #D91CD2)';

const POSITIONS = {
  x: [{ v: 0, l: 'Gauche' }, { v: 0.5, l: 'Centre' }, { v: 1, l: 'Droite' }],
  y: [{ v: 0, l: 'Haut' }, { v: 0.5, l: 'Centre' }, { v: 1, l: 'Bas' }],
};

const erreurLisible = (e, defaut) => {
  const d = e && e.response && e.response.data && e.response.data.detail;
  return typeof d === 'string' ? d : ((e && e.message) || defaut);
};

/**
 * LE CADRE sur l'aperçu. Le lecteur de VideoTrimEditor est en `object-fit:
 * contain` : on recalcule le rectangle RÉEL de l'image dans sa boîte, puis on y
 * place le cadre conservé. Glisser déplace le cadre sur son seul axe libre.
 */
export function CadrageSuperposition({ largeur, hauteur, reglage, onPosition }) {
  const boiteRef = useRef(null);
  const [boite, setBoite] = useState({ l: 0, h: 0 });
  const glisse = useRef(null);

  useEffect(() => {
    const el = boiteRef.current;
    if (!el) return undefined;
    const mesurer = () => {
      const r = el.getBoundingClientRect();
      setBoite((p) => (Math.abs(p.l - r.width) < 0.5 && Math.abs(p.h - r.height) < 0.5 ? p : { l: r.width, h: r.height }));
    };
    mesurer();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(mesurer);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  if (!reglage || !(largeur > 0) || !(hauteur > 0)) return null;
  const echelle = boite.l && boite.h ? Math.min(boite.l / largeur, boite.h / hauteur) : 0;
  const img = { l: largeur * echelle, h: hauteur * echelle };
  const ox = (boite.l - img.l) / 2; const oy = (boite.h - img.h) / 2;
  const c = reglage.cadre;
  const rect = { x: ox + c.gauche * echelle, y: oy + c.haut * echelle, l: c.largeur * echelle, h: c.hauteur * echelle };
  const axe = reglage.axe;
  const libre = axe === 'x' ? img.l - rect.l : (axe === 'y' ? img.h - rect.h : 0);

  const debut = (e) => {
    if (!axe || libre <= 0) return;
    e.preventDefault();
    glisse.current = { depart: axe === 'x' ? e.clientX : e.clientY, position: reglage.position };
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
  };
  const bouge = (e) => {
    if (!glisse.current) return;
    const delta = (axe === 'x' ? e.clientX : e.clientY) - glisse.current.depart;
    onPosition(Math.max(0, Math.min(1, glisse.current.position + delta / libre)));
  };
  const fin = () => { glisse.current = null; };
  const masque = { position: 'absolute', background: 'rgba(0,0,0,0.62)', pointerEvents: 'none' };

  return (
    <div ref={boiteRef} data-testid="pve-cadrage" style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
      {echelle > 0 && (
        <>
          <div style={{ ...masque, left: ox, top: oy, width: Math.max(0, rect.x - ox), height: img.h }} />
          <div style={{ ...masque, left: rect.x + rect.l, top: oy, width: Math.max(0, ox + img.l - rect.x - rect.l), height: img.h }} />
          <div style={{ ...masque, left: rect.x, top: oy, width: rect.l, height: Math.max(0, rect.y - oy) }} />
          <div style={{ ...masque, left: rect.x, top: rect.y + rect.h, width: rect.l, height: Math.max(0, oy + img.h - rect.y - rect.h) }} />
          <div
            data-testid="pve-cadre"
            role={axe ? 'slider' : undefined}
            aria-label={axe ? 'Position du cadrage' : undefined}
            aria-valuemin={axe ? 0 : undefined} aria-valuemax={axe ? 100 : undefined}
            aria-valuenow={axe ? Math.round(reglage.position * 100) : undefined}
            onPointerDown={debut} onPointerMove={bouge} onPointerUp={fin} onPointerCancel={fin}
            style={{
              position: 'absolute', left: rect.x, top: rect.y, width: rect.l, height: rect.h,
              border: `2px solid ${COULEUR}`, boxSizing: 'border-box', borderRadius: 4,
              pointerEvents: axe ? 'auto' : 'none', cursor: axe === 'x' ? 'ew-resize' : (axe === 'y' ? 'ns-resize' : 'default'),
              touchAction: 'none',
            }}
          />
        </>
      )}
    </div>
  );
}

/** La miniature = la frame capturée, RECADRÉE comme l'export (même cadre). */
async function recadrerMiniature(blob, cadre) {
  if (typeof createImageBitmap !== 'function' || !cadre) return blob;
  const bmp = await createImageBitmap(blob);
  try {
    const canvas = document.createElement('canvas');
    canvas.width = cadre.largeur; canvas.height = cadre.hauteur;
    canvas.getContext('2d').drawImage(bmp, cadre.gauche, cadre.haut, cadre.largeur, cadre.hauteur, 0, 0, cadre.largeur, cadre.hauteur);
    return await new Promise((res) => canvas.toBlob((b) => res(b || blob), 'image/jpeg', 0.9));
  } finally { if (bmp.close) bmp.close(); }
}

export default function ProspectionVideoEditeur({ API, niche, original, fichierLocal = null, editionInitiale = null, onFermer, onEnregistre }) {
  const support = useMemo(() => exportSupporteIci(), []);
  // L'aperçu lit le fichier LOCAL s'il vient d'être choisi (immédiat), sinon l'original enregistré.
  const urlLocale = useMemo(() => (fichierLocal ? URL.createObjectURL(fichierLocal) : ''), [fichierLocal]);
  const urlSource = urlLocale || original.url;
  const nomOriginal = (original.fichier && original.fichier.nom) || 'video.mp4';

  const [meta, setMeta] = useState(null);
  const [trim, setTrim] = useState(editionInitiale ? { start: editionInitiale.debut, end: editionInitiale.fin } : null);
  const [ratio, setRatio] = useState(editionInitiale ? editionInitiale.ratio : 'auto');
  const [position, setPosition] = useState(editionInitiale ? editionInitiale.position : 0.5);
  const [miniature, setMiniature] = useState({ url: '', etat: '' });
  const [exp, setExp] = useState({ etat: 'pret', pct: 0, erreur: '' });
  const [resultat, setResultat] = useState(null);       // { blob, url, duree, largeur, hauteur, taille }
  const [envoi, setEnvoi] = useState({ etat: '', pct: 0, erreur: '' });
  const annulation = useRef({ annuler: null });
  const urlsAPurger = useRef([]);

  const garderUrl = (u) => { if (u) urlsAPurger.current.push(u); return u; };
  // Libération mémoire à la fermeture : blobs, aperçus, export en cours.
  useEffect(() => () => {
    if (annulation.current.annuler) { try { annulation.current.annuler(); } catch (e) { /* ignore */ } }
    urlsAPurger.current.forEach((u) => { try { URL.revokeObjectURL(u); } catch (e) { /* ignore */ } });
    if (urlLocale) URL.revokeObjectURL(urlLocale);
  }, [urlLocale]);

  const erreurMeta = meta ? validerMetadonnees(meta) : '';
  const reglage = useMemo(() => (meta ? calculerCadrage(meta.largeur, meta.hauteur, ratio, position) : null), [meta, ratio, position]);
  const debut = trim ? trim.start : 0;
  const fin = trim ? trim.end : (meta ? meta.duree : 0);
  const formatCible = ratio === 'auto' && reglage
    ? (FORMATS_EXPORT.find((f) => f.ratio === ratioDepuisDimensions(reglage.sortie.largeur, reglage.sortie.hauteur)) || {}).format
    : (FORMATS_EXPORT.find((f) => f.ratio === ratio) || {}).format;

  const onMetadata = useCallback(({ duration, width, height }) => {
    setMeta((p) => (p && p.duree === duration && p.largeur === width && p.hauteur === height ? p : { duree: duration, largeur: width, hauteur: height }));
  }, []);

  const capturerMiniature = async (blob) => {
    setMiniature({ url: '', etat: 'envoi' });
    try {
      const recadree = await recadrerMiniature(blob, reglage && reglage.cadre);
      const apercu = garderUrl(URL.createObjectURL(recadree));
      setMiniature({ url: apercu, etat: 'envoi' });
      const fichier = new File([recadree], nomExport(nomOriginal, 'miniature').replace('.mp4', '.jpg'), { type: 'image/jpeg' });
      const r = await uploadToCloudinary(fichier, { folder: 'prospection' });
      await axios.post(`${API}/prospection-medias`, {
        niche, format: 'miniature', url: r.url, source_id: original.id,
        fichier: { nom: fichier.name }, version: 'Miniature',
      });
      setMiniature({ url: apercu, etat: 'ok' });
    } catch (e) {
      setMiniature((p) => ({ ...p, etat: erreurLisible(e, 'Miniature non enregistrée.') }));
    }
  };

  const exporter = async () => {
    if (!reglage || exportEnCours()) return;
    setExp({ etat: 'encours', pct: 0, erreur: '' });
    try {
      const r = await exporterVideo({
        source: fichierLocal || original.url, debut, fin, reglage,
        onProgress: (pct) => setExp((p) => (p.pct === pct ? p : { ...p, pct })),
        annulation: annulation.current,
      });
      const url = garderUrl(URL.createObjectURL(r.blob));
      // Les caractéristiques affichées sont lues DANS le fichier produit (pas déduites des réglages).
      const m = await lireMetadonneesFichier(r.blob);
      if (!m) throw new Error('Le fichier exporté est illisible : export refusé.');
      setResultat({ blob: r.blob, url, duree: m.duree, largeur: m.largeur, hauteur: m.hauteur, taille: r.blob.size });
      setExp({ etat: 'fini', pct: 100, erreur: '' });
    } catch (e) {
      setExp({ etat: 'echec', pct: 0, erreur: erreurLisible(e, 'Export impossible.') });
    }
  };
  const annulerExport = () => { if (annulation.current.annuler) annulation.current.annuler(); };

  const remodifier = () => {
    if (resultat && resultat.url) { try { URL.revokeObjectURL(resultat.url); } catch (e) { /* ignore */ } }
    setResultat(null); setExp({ etat: 'pret', pct: 0, erreur: '' }); setEnvoi({ etat: '', pct: 0, erreur: '' });
  };

  const enregistrer = async () => {
    if (!resultat || !formatCible) return;
    setEnvoi({ etat: 'envoi', pct: 0, erreur: '' });
    try {
      const nom = nomExport(nomOriginal, ratio === 'auto' ? ratioDepuisDimensions(resultat.largeur, resultat.hauteur) : ratio);
      const fichier = new File([resultat.blob], nom, { type: 'video/mp4' });
      const r = await uploadToCloudinary(fichier, { folder: 'prospection', onProgress: (pct) => setEnvoi((p) => ({ ...p, pct: Math.round(pct) })) });
      const c = reglage.cadre;
      const rep = await axios.post(`${API}/prospection-medias`, {
        niche, format: formatCible, url: r.url, origine: 'export', source_id: original.id,
        version: `Export ${ratio === 'auto' ? 'auto' : ratio}`,
        edition: { debut, fin, ratio, position: reglage.position, cadre: { gauche: c.gauche, haut: c.haut, largeur: c.largeur, hauteur: c.hauteur } },
        fichier: { nom, duree: resultat.duree, largeur: resultat.largeur, hauteur: resultat.hauteur },
      });
      setEnvoi({ etat: 'ok', pct: 100, erreur: '' });
      onEnregistre(rep.data && rep.data.archives
        ? `Version ${ratio} enregistrée « À vérifier ». L'ancienne version de ce format est archivée (jamais supprimée).`
        : `Version ${ratio} enregistrée « À vérifier ».`);
    } catch (e) {
      setEnvoi({ etat: 'echec', pct: 0, erreur: erreurLisible(e, 'Enregistrement refusé.') });
    }
  };

  const enExport = exp.etat === 'encours';
  const bloque = enExport || envoi.etat === 'envoi';

  return (
    <div data-testid="pve-editeur" style={{ marginTop: '8px', padding: '12px', borderRadius: '12px', background: 'rgba(255,255,255,0.03)', border: `1px solid ${BORD}`, color: TEXTE, display: 'grid', gap: '10px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <strong style={{ fontSize: 13 }}>Modifier / exporter — {nomOriginal}</strong>
        <Bouton discret onClick={onFermer} disabled={bloque} testid="pve-fermer">Fermer</Bouton>
      </div>
      {!support.ok && <Bandeau ton="ambre" testid="pve-mobile">{support.raison} Tu peux consulter la vidéo ici ; l'export se fait depuis un ordinateur.</Bandeau>}
      {erreurMeta && <Bandeau ton="rouge" testid="pve-erreur-meta">{erreurMeta}</Bandeau>}

      {resultat ? (
        <ApercuFinal resultat={resultat} ratio={ratio} envoi={envoi}
          onEnregistrer={enregistrer} onRemodifier={remodifier} formatCible={formatCible} />
      ) : (
        <>
          <VideoTrimEditor
            videoUrl={urlSource}
            trimStart={trim ? trim.start : null}
            trimEnd={trim ? trim.end : null}
            aspectRatio="auto"
            thumbnail={miniature.url}
            onTrimChange={(t) => setTrim(t)}
            onThumbnailCapture={capturerMiniature}
            onMetadata={onMetadata}
            hauteurMax="360px"
            superposition={ratio !== 'auto' && meta ? (
              <CadrageSuperposition largeur={meta.largeur} hauteur={meta.hauteur} reglage={reglage} onPosition={setPosition} />
            ) : null}
            complement={(
              <div style={{ display: 'grid', gap: 10 }}>
                {miniature.etat && miniature.etat !== 'ok' && (
                  <div style={{ fontSize: 11, color: miniature.etat === 'envoi' ? DOUX : 'rgb(252,165,165)' }} data-testid="pve-miniature-etat">
                    {miniature.etat === 'envoi' ? 'Envoi de la miniature…' : miniature.etat}
                  </div>
                )}
                {miniature.etat === 'ok' && <div style={{ fontSize: 11, color: DOUX }} data-testid="pve-miniature-ok">Miniature enregistrée (recadrée comme l'export). Tu peux en capturer une autre à tout moment.</div>}

                <div style={{ padding: 10, borderRadius: 10, background: 'rgba(255,255,255,0.05)' }} data-testid="pve-formats">
                  <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>Format du fichier exporté</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 6 }}>
                    {FORMATS_EXPORT.map((f) => (
                      <label key={f.ratio} style={{ display: 'flex', gap: 6, alignItems: 'flex-start', fontSize: 12, cursor: 'pointer', padding: 6, borderRadius: 8, border: `1px solid ${ratio === f.ratio ? COULEUR : BORD}` }}>
                        <input type="radio" name={`pve-ratio-${niche}`} checked={ratio === f.ratio} disabled={bloque}
                          onChange={() => { setRatio(f.ratio); setPosition(0.5); }} data-testid={`pve-ratio-${f.ratio}`} style={{ accentColor: COULEUR, marginTop: 2 }} />
                        <span><b>{f.libelle}</b><br /><span style={{ color: DOUX, fontSize: 11 }}>{f.aide}</span></span>
                      </label>
                    ))}
                  </div>
                  {meta && (
                    <div style={{ fontSize: 11, color: DOUX, marginTop: 6 }} data-testid="pve-detection">
                      Dimensions détectées : {libelleDetection(meta.largeur, meta.hauteur) || `${meta.largeur} × ${meta.hauteur}`}
                    </div>
                  )}
                  {reglage && reglage.axe && (
                    <div style={{ marginTop: 8 }}>
                      <div style={{ fontSize: 11, color: DOUX, marginBottom: 4 }}>Cadrage — glisse le cadre sur l'image, ou :</div>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        {POSITIONS[reglage.axe].map((p) => (
                          <Bouton key={p.l} discret={Math.abs(position - p.v) > 0.001} onClick={() => setPosition(p.v)} disabled={bloque} testid={`pve-pos-${p.l}`}>{p.l}</Bouton>
                        ))}
                      </div>
                    </div>
                  )}
                  {reglage && (
                    <div style={{ fontSize: 12, marginTop: 8, lineHeight: 1.5 }} data-testid="pve-sortie">
                      Fichier final : <b>{reglage.sortie.largeur} × {reglage.sortie.hauteur}</b> · {formatTemps(Math.max(0, fin - debut))} ({(Math.max(0, fin - debut)).toFixed(1)} s)
                      {reglage.ratio !== 'auto' && (reglage.sortie.largeur < (FORMATS_EXPORT.find((f) => f.ratio === ratio) || { max: [0] }).max[0]) && (
                        <div style={{ fontSize: 11, color: DOUX }}>Résolution réelle de la zone conservée : la vidéo n'est jamais agrandie.</div>
                      )}
                      {reglage.axe && <div style={{ fontSize: 11, color: DOUX }}>La zone assombrie sur l'aperçu ne sera pas dans le fichier.</div>}
                    </div>
                  )}
                </div>

                {support.ok && (
                  <div style={{ display: 'grid', gap: 6 }}>
                    {enExport ? (
                      <>
                        <div data-testid="pve-export-en-cours" style={{ fontSize: 13, fontWeight: 700 }}>Export en cours… {exp.pct} %</div>
                        <div style={{ height: 6, borderRadius: 3, background: 'rgba(255,255,255,0.12)' }}>
                          <div style={{ width: `${exp.pct}%`, height: 6, borderRadius: 3, background: COULEUR }} />
                        </div>
                        <div style={{ fontSize: 11, color: DOUX }}>Garde cet onglet ouvert ; le reste du site reste utilisable dans un autre onglet.</div>
                        <Bouton discret onClick={annulerExport} testid="pve-annuler-export">Annuler l'export</Bouton>
                      </>
                    ) : (
                      <Bouton onClick={exporter} disabled={!reglage || !!erreurMeta || bloque || !formatCible} testid="pve-exporter">Exporter la vidéo</Bouton>
                    )}
                    {ratio === 'auto' && reglage && !formatCible && <div style={{ fontSize: 11, color: DOUX }}>Format d'origine non standard : choisis 16:9, 9:16 ou 1:1.</div>}
                    {exp.erreur && <div style={{ fontSize: 12, color: 'rgb(252,165,165)' }} data-testid="pve-export-erreur">{exp.erreur}</div>}
                  </div>
                )}
              </div>
            )}
          />
        </>
      )}
    </div>
  );
}

function ApercuFinal({ resultat, ratio, envoi, onEnregistrer, onRemodifier, formatCible }) {
  const lu = resultat.largeur > 0;
  return (
    <div data-testid="pve-apercu-final" style={{ display: 'grid', gap: 10 }}>
      <Bandeau ton="vert">Export terminé. Voici le VRAI fichier final — rien n'est enregistré tant que tu ne cliques pas sur « Enregistrer cette version ».</Bandeau>
      <div style={{ background: '#000', borderRadius: 10, display: 'flex', justifyContent: 'center', overflow: 'hidden' }}>
        <video
          src={resultat.url} controls playsInline preload="metadata" data-testid="pve-video-finale"
          style={{ maxWidth: '100%', maxHeight: '420px', display: 'block' }}
        />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '2px 12px', fontSize: 12 }} data-testid="pve-final-infos">
        <span>Durée : <b data-testid="pve-final-duree">{resultat.duree.toFixed(1)} s</b></span>
        <span>Résolution : <b data-testid="pve-final-resolution">{lu ? `${resultat.largeur} × ${resultat.hauteur}` : '…'}</b></span>
        <span>Ratio : <b data-testid="pve-final-ratio">{lu ? ratioDepuisDimensions(resultat.largeur, resultat.hauteur) : ratio}</b></span>
        <span>Taille : <b data-testid="pve-final-taille">{tailleLisible(resultat.taille)}</b></span>
      </div>
      {envoi.etat === 'envoi' && <div style={{ fontSize: 12 }} data-testid="pve-envoi">Envoi du fichier… {envoi.pct} %</div>}
      {envoi.erreur && <div style={{ fontSize: 12, color: 'rgb(252,165,165)' }} data-testid="pve-envoi-erreur">{envoi.erreur}</div>}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Bouton onClick={onEnregistrer} disabled={!lu || !formatCible || envoi.etat === 'envoi' || envoi.etat === 'ok'} testid="pve-enregistrer">Enregistrer cette version</Bouton>
        <Bouton discret onClick={onRemodifier} disabled={envoi.etat === 'envoi'} testid="pve-remodifier">Remodifier</Bouton>
      </div>
      <div style={{ fontSize: 11, color: DOUX }}>Une version enregistrée entre « À vérifier ». Tu la valides ensuite toi-même.</div>
    </div>
  );
}
