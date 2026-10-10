/**
 * V596 — EXPORT VIDÉO DANS LE NAVIGATEUR (Prospection → Médias UNIQUEMENT).
 *
 * Le navigateur du coach décode, découpe, recadre et réencode (H.264 + AAC, MP4).
 * Le serveur ne fait AUCUN calcul vidéo : il reçoit le fichier fini par l'envoi
 * existant (/api/files). Le moteur (Mediabunny, WebCodecs = encodeur matériel du
 * Mac) n'est chargé QUE par `exporterVideo`, via `import()` : il n'alourdit
 * aucune autre page du site.
 *
 * Tout le reste de ce fichier est PUR (testé sans navigateur) : validation,
 * calcul du cadre, dimensions de sortie, débit, nom du fichier.
 */

export const TYPES_VIDEO = ['video/mp4', 'video/quicktime', 'video/webm'];
export const EXTENSIONS_VIDEO = ['mp4', 'mov', 'm4v', 'webm'];
export const TAILLE_MAX_MO = 100;          // plafond de l'envoi existant (upload-chunk)
export const DUREE_MAX_S = 600;            // 10 min : au-delà, l'export navigateur devient déraisonnable
export const EXTRAIT_MIN_S = 0.5;

/** Les formats d'export, et leur taille MAXIMALE (jamais d'agrandissement). */
export const FORMATS_EXPORT = [
  { ratio: 'auto', format: null, libelle: 'Auto', aide: 'Format d’origine, sans recadrage', max: [1920, 1920] },
  { ratio: '16:9', format: '16_9', libelle: 'Horizontal 16:9', aide: 'Paysage, e-mail, YouTube', max: [1920, 1080] },
  { ratio: '9:16', format: '9_16', libelle: 'Vertical 9:16', aide: 'Reel, story, téléphone', max: [1080, 1920] },
  { ratio: '1:1', format: '1_1', libelle: 'Carré 1:1', aide: 'Post carré', max: [1080, 1080] },
];

// H.264 4:2:0 : tailles et décalages PAIRS. `pair` = taille (≥ 2, pair le plus proche
// sans dépasser `max`) ; `decalagePair` = position (≥ 0).
const pair = (n, max = Infinity) => {
  const p = Math.max(2, Math.round(n / 2) * 2);
  return p > max ? Math.max(2, Math.floor(max / 2) * 2) : p;
};
const decalagePair = (n) => Math.max(0, Math.round(n / 2) * 2);
const borner = (x, a, b) => Math.max(a, Math.min(b, x));

const extension = (nom) => {
  const m = /\.([A-Za-z0-9]+)$/.exec(String(nom || ''));
  return m ? m[1].toLowerCase() : '';
};

/** Avant TOUT traitement : type, extension, taille. Renvoie '' si OK, sinon le message. */
export function validerFichierVideo(fichier) {
  if (!fichier) return 'Aucun fichier.';
  const ext = extension(fichier.name);
  if (!EXTENSIONS_VIDEO.includes(ext)) return `Extension non acceptée (.${ext || '?'}). Formats : MP4, MOV, M4V, WEBM.`;
  if (fichier.type && !TYPES_VIDEO.includes(fichier.type)) return `Type de fichier non accepté (${fichier.type}).`;
  if (!(fichier.size > 0)) return 'Fichier vide.';
  if (fichier.size > TAILLE_MAX_MO * 1024 * 1024) {
    return `Fichier trop lourd (${(fichier.size / 1024 / 1024).toFixed(1)} Mo, maximum ${TAILLE_MAX_MO} Mo).`;
  }
  return '';
}

/** Après lecture des métadonnées : durée et dimensions plausibles. */
export function validerMetadonnees({ duree, largeur, hauteur }) {
  if (!(duree > 0)) return 'Durée de la vidéo illisible.';
  if (duree > DUREE_MAX_S) return `Vidéo trop longue (${Math.round(duree)} s, maximum ${DUREE_MAX_S / 60} min).`;
  if (!(largeur > 0) || !(hauteur > 0)) return 'Dimensions de la vidéo illisibles.';
  return '';
}

/** Le ratio numérique d'un format (auto = celui de la source). */
export function ratioNumerique(ratio, largeur, hauteur) {
  if (ratio === '16:9') return 16 / 9;
  if (ratio === '9:16') return 9 / 16;
  if (ratio === '1:1') return 1;
  return largeur / hauteur;
}

/**
 * LE CADRE CONSERVÉ, en pixels de la source, et la taille du fichier final.
 *
 * `position` ∈ [0, 1] le long de l'axe où le cadre peut bouger :
 * 0 = gauche (ou haut), 0,5 = centre, 1 = droite (ou bas).
 * Le cadre REMPLIT le format choisi (aucune bande noire) ; la sortie ne dépasse
 * jamais le maximum du format, ni la taille réelle du cadre (pas d'agrandissement).
 */
export function calculerCadrage(largeur, hauteur, ratio, position = 0.5) {
  const W = Math.round(Number(largeur)); const H = Math.round(Number(hauteur));
  if (!(W > 0) || !(H > 0)) return null;
  const fmt = FORMATS_EXPORT.find((f) => f.ratio === ratio) || FORMATS_EXPORT[0];
  const p = borner(Number.isFinite(Number(position)) ? Number(position) : 0.5, 0, 1);
  let cadre = { gauche: 0, haut: 0, largeur: pair(W, W), hauteur: pair(H, H) };
  let axe = null;
  if (fmt.ratio !== 'auto') {
    const r = ratioNumerique(fmt.ratio, W, H);
    if (W / H > r + 1e-6) {                       // source plus large : on coupe à gauche / droite
      const l = pair(Math.min(W, H * r), W);
      cadre = { gauche: decalagePair((W - l) * p), haut: 0, largeur: l, hauteur: pair(H, H) };
      axe = 'x';
    } else if (W / H < r - 1e-6) {                // source plus haute : on coupe en haut / en bas
      const h = pair(Math.min(H, W / r), H);
      cadre = { gauche: 0, haut: decalagePair((H - h) * p), largeur: pair(W, W), hauteur: h };
      axe = 'y';
    }
    cadre.gauche = Math.min(cadre.gauche, Math.floor((W - cadre.largeur) / 2) * 2);
    cadre.haut = Math.min(cadre.haut, Math.floor((H - cadre.hauteur) / 2) * 2);
  }
  const [maxL, maxH] = fmt.ratio === 'auto' ? (W >= H ? [1920, 1080] : [1080, 1920]) : fmt.max;
  const echelle = Math.min(1, maxL / cadre.largeur, maxH / cadre.hauteur);
  return {
    ratio: fmt.ratio, axe, position: p, cadre,
    sortie: { largeur: pair(cadre.largeur * echelle, cadre.largeur), hauteur: pair(cadre.hauteur * echelle, cadre.hauteur) },
  };
}

/** Débit vidéo visé : ≈ 4 Mbit/s en 1080p, borné (qualité correcte, fichier raisonnable). */
export function debitVideo(largeur, hauteur) {
  return Math.round(borner(largeur * hauteur * 2, 1500000, 5000000));
}

/** « festival_9x16.mp4 » à partir du nom de l'original. */
export function nomExport(nomOriginal, ratio) {
  const base = String(nomOriginal || 'video').replace(/\.[A-Za-z0-9]+$/, '')
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[^A-Za-z0-9_-]+/g, '_').replace(/_+/g, '_').replace(/^_|_$/g, '')
    .slice(0, 80) || 'video';
  const suffixe = ratio === 'auto' ? 'export' : String(ratio).replace(':', 'x');
  return `${base}_${suffixe}.mp4`;
}

export const tailleLisible = (o) => (o >= 1024 * 1024 ? `${(o / 1024 / 1024).toFixed(1)} Mo` : `${Math.max(1, Math.round(o / 1024))} Ko`);

/**
 * Peut-on exporter ICI ? Sur téléphone : non (l'encodage lourd n'est pas imposé).
 * Renvoie { ok, raison }.
 */
export function exportSupporteIci(env = (typeof window !== 'undefined' ? window : {})) {
  const ua = (env.navigator && env.navigator.userAgent) || '';
  const mobile = /Android|iPhone|iPad|iPod|Mobile/i.test(ua)
    || (typeof env.matchMedia === 'function' && env.matchMedia('(pointer: coarse)').matches && (env.innerWidth || 0) < 1024);
  if (mobile) return { ok: false, raison: 'Export vidéo recommandé sur ordinateur.' };
  if (typeof env.VideoEncoder === 'undefined' || typeof env.VideoDecoder === 'undefined') {
    return { ok: false, raison: 'Ce navigateur ne sait pas encoder la vidéo. Utilise Chrome ou Safari récent sur ordinateur.' };
  }
  return { ok: true, raison: '' };
}

/**
 * Durée et dimensions d'un fichier LOCAL, lues dans le conteneur MP4 lui-même.
 * Pas de <video> : un lecteur vidéo est suspendu par Chrome quand l'onglet passe
 * en arrière-plan (« stalled »), ce qui faisait échouer la lecture. Chargé à la
 * demande, comme l'export. Renvoie null si le fichier est illisible.
 */
export async function lireMetadonneesFichier(fichier) {
  let input = null;
  try {
    const mb = await import('mediabunny');
    input = new mb.Input({ source: new mb.BlobSource(fichier), formats: mb.ALL_FORMATS });
    const piste = await input.getPrimaryVideoTrack();
    if (!piste) return null;
    const duree = await input.computeDuration();
    return { duree: Math.round(duree * 100) / 100, largeur: piste.displayWidth, hauteur: piste.displayHeight };
  } catch (e) {
    return null;
  } finally {
    try { if (input && input.dispose) input.dispose(); } catch (err) { /* déjà libéré */ }
  }
}

// UN SEUL EXPORT À LA FOIS (tout l'onglet).
let exportActif = null;
export const exportEnCours = () => !!exportActif;

/**
 * L'EXPORT. `source` = un File/Blob local, ou une URL /api/files (même origine).
 * Renvoie { blob, duree } ou lève une erreur LISIBLE. `annulation.annuler()`
 * arrête proprement (ConversionCanceledError → message « Export annulé »).
 */
export async function exporterVideo({ source, debut, fin, reglage, onProgress, annulation }) {
  if (exportActif) throw new Error('Un export est déjà en cours.');
  const jeton = {};
  exportActif = jeton;
  let input = null;
  let conversion = null;
  try {
    const mb = await import('mediabunny');
    if (!(await mb.canEncodeAudio('aac'))) {
      const aac = await import('@mediabunny/aac-encoder');
      aac.registerAacEncoder();
    }
    const { largeur, hauteur } = reglage.sortie;
    if (!(await mb.canEncodeVideo('avc', { width: largeur, height: hauteur }))) {
      throw new Error('Ce navigateur ne sait pas encoder en H.264 à cette taille.');
    }
    input = new mb.Input({
      source: typeof source === 'string' ? new mb.UrlSource(source) : new mb.BlobSource(source),
      formats: mb.ALL_FORMATS,
    });
    const output = new mb.Output({ format: new mb.Mp4OutputFormat({ fastStart: 'in-memory' }), target: new mb.BufferTarget() });
    const c = reglage.cadre;
    conversion = await mb.Conversion.init({
      input, output,
      trim: { start: debut, end: fin },
      video: {
        crop: { left: c.gauche, top: c.haut, width: c.largeur, height: c.hauteur },
        width: largeur, height: hauteur, fit: 'fill',
        codec: 'avc', bitrate: debitVideo(largeur, hauteur), keyFrameInterval: 2, forceTranscode: true,
      },
      audio: { codec: 'aac', bitrate: 128000 },
      showWarnings: false,
    });
    if (!conversion.isValid) {
      const raisons = (conversion.discardedTracks || []).map((d) => d.reason).join(', ');
      throw new Error(`Export impossible avec ce fichier${raisons ? ` (${raisons})` : ''}.`);
    }
    if (annulation) annulation.annuler = () => conversion.cancel();
    conversion.onProgress = (p) => { if (onProgress) onProgress(Math.round(borner(p, 0, 1) * 100)); };
    await conversion.execute();
    const buffer = output.target.buffer;
    if (!buffer || !buffer.byteLength) throw new Error('Export vide.');
    return { blob: new Blob([buffer], { type: 'video/mp4' }), duree: Math.round((fin - debut) * 100) / 100 };
  } catch (e) {
    if (e && (e.name === 'ConversionCanceledError' || /cancel/i.test(e.message || ''))) throw new Error('Export annulé.');
    if (e && (e.name === 'QuotaExceededError' || e instanceof RangeError || /memory|mémoire/i.test(e.message || ''))) {
      throw new Error('Mémoire insuffisante pour cet export. Ferme d’autres onglets ou raccourcis l’extrait.');
    }
    throw (e instanceof Error ? e : new Error('Export impossible.'));
  } finally {
    // Libération : le décodeur, les tampons et le verrou, quoi qu'il arrive.
    try { if (input && input.dispose) input.dispose(); } catch (err) { /* déjà libéré */ }
    if (annulation) annulation.annuler = null;
    if (exportActif === jeton) exportActif = null;
  }
}
