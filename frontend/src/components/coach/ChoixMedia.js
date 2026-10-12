/**
 * V610e — CHOISIR UN MÉDIA (vidéo / audio) pour une invitation, sans jamais saisir
 * d'adresse technique : le média actuel (prévisualisable), la bibliothèque du coach
 * (ses imports + ses vidéos Médias), l'import d'un nouveau fichier (progression,
 * doublon réutilisé par le serveur), remplacer, retirer.
 *
 * Lecture : TOUJOURS au clic (preload « none »), jamais d'autoplay.
 * Couleurs : var(--primary-color) / rgba(var(--primary-rgb)) et gris neutres.
 */
import React, { useRef, useState } from 'react';
import SvgIcon from '../SvgIcon';
import { lireMediasCoach, importerMedia } from '../../utils/invitationEdition';
import AfroboostAudioPlayer from '../AfroboostAudioPlayer'; // V610g : plus de lecteur audio natif

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const rgbaP = (a) => `rgba(var(--primary-rgb, 217, 28, 210), ${a})`;
const bouton = (plein) => ({
  minHeight: 40, padding: '8px 12px', borderRadius: 10, fontSize: 13.5, fontWeight: 600, cursor: 'pointer',
  display: 'inline-flex', alignItems: 'center', gap: 6, color: 'rgba(255,255,255,0.96)',
  background: plein ? PRIMAIRE : 'rgba(255,255,255,0.07)', border: plein ? 'none' : `1px solid ${rgbaP(0.35)}`,
});

/** Une adresse servie par Afroboost ou en https — jamais autre chose dans un lecteur. */
export function urlMediaSure(u) {
  const v = String(u || '').trim();
  if (/^\/api\/files\/[A-Za-z0-9_-]+\/[A-Za-z0-9._-]+$/.test(v)) return v;
  if (/^https:\/\/[A-Za-z0-9.-]+(:\d+)?\/[^\s"'<>]*$/.test(v)) return v;
  return '';
}

function Lecteur({ type, url, testid }) {
  const sur = urlMediaSure(url);
  if (!sur) return null;
  return type === 'video'
    ? <video data-testid={testid} src={sur} controls playsInline preload="none" controlsList="nodownload noremoteplayback"
             style={{ display: 'block', width: '100%', maxHeight: 260, objectFit: 'contain', borderRadius: 10, background: 'rgb(0,0,0)' }} />
    : <AfroboostAudioPlayer src={sur} testidAudio={testid} compact />;
}

function taille(o) {
  const n = Number(o);
  if (!Number.isFinite(n) || n <= 0) return '';
  return n >= 1048576 ? `${(n / 1048576).toFixed(1)} Mo` : `${Math.round(n / 1024)} Ko`;
}

export default function ChoixMedia({ type, valeur, onChange, libelle, aide, testid, onOuvrirOutil = null }) {
  const [biblio, setBiblio] = useState(null);       // null = fermée ; [] = ouverte
  const [chargement, setChargement] = useState(false);
  const [progres, setProgres] = useState(null);
  const [erreur, setErreur] = useState('');
  const [apercu, setApercu] = useState('');
  const entree = useRef(null);
  const id = testid || `media-${type}`;
  const actuel = urlMediaSure(valeur);

  const ouvrirBiblio = () => {
    if (biblio) { setBiblio(null); return; }
    setChargement(true); setErreur('');
    lireMediasCoach(type).then((l) => setBiblio(l)).catch(() => setErreur('Bibliothèque indisponible pour le moment.'))
      .finally(() => setChargement(false));
  };
  const surFichier = async (e) => {
    const f = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!f) return;
    setErreur(''); setProgres(0);
    try {
      const r = await importerMedia(f, type, setProgres);
      onChange(r.url);
      setBiblio(null);
      if (r.doublon) setErreur('Ce fichier était déjà dans ta bibliothèque : il est réutilisé.');
    } catch (err) {
      const d = err && err.response && err.response.data && err.response.data.detail;
      setErreur(typeof d === 'string' ? d : (err && err.message) || "L'import n'a pas abouti.");
    } finally { setProgres(null); }
  };

  return (
    <div data-testid={id} style={{ padding: 12, borderRadius: 12, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', marginBottom: 12 }}>
      <div style={{ fontWeight: 700, fontSize: 14, color: 'rgba(255,255,255,0.95)', marginBottom: 2 }}>{libelle}</div>
      {aide ? <div style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.6)', marginBottom: 8 }}>{aide}</div> : null}
      {actuel ? <Lecteur type={type} url={actuel} testid={`${id}-actuel`} />
        : <div data-testid={`${id}-vide`} style={{ fontSize: 13, color: 'rgba(255,255,255,0.55)', padding: '6px 0' }}>Aucun média choisi.</div>}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
        <button type="button" style={bouton(false)} onClick={ouvrirBiblio} data-testid={`${id}-biblio`} aria-expanded={!!biblio}>
          <SvgIcon name="layers" size={15} /> {biblio ? 'Fermer la bibliothèque' : 'Bibliothèque'}
        </button>
        <button type="button" style={bouton(false)} onClick={() => entree.current && entree.current.click()} data-testid={`${id}-importer`} disabled={progres !== null}>
          <SvgIcon name="upload" size={15} /> {actuel ? 'Remplacer' : 'Importer'}
        </button>
        {actuel && type === 'video' && onOuvrirOutil ? (
          <button type="button" style={bouton(false)} onClick={() => onOuvrirOutil(actuel)} data-testid={`${id}-outil`}>
            <SvgIcon name="edit" size={15} /> Découper / Modifier / exporter
          </button>
        ) : null}
        {actuel ? (
          <button type="button" style={bouton(false)} onClick={() => onChange(null)} data-testid={`${id}-retirer`}>
            <SvgIcon name="trash" size={15} /> Retirer
          </button>
        ) : null}
        <input ref={entree} type="file" hidden accept={type === 'video' ? 'video/mp4,video/webm,video/quicktime' : 'audio/mpeg,audio/mp4,audio/aac,audio/wav,audio/ogg'}
               onChange={surFichier} data-testid={`${id}-fichier`} />
      </div>
      {progres !== null ? (
        <div data-testid={`${id}-progres`} style={{ marginTop: 10, height: 8, borderRadius: 99, background: 'rgba(255,255,255,0.1)', overflow: 'hidden' }}>
          <div style={{ width: `${progres}%`, height: '100%', background: PRIMAIRE }} />
        </div>
      ) : null}
      {chargement ? <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.6)', marginTop: 8 }}>Chargement…</div> : null}
      {erreur ? <div role="status" data-testid={`${id}-message`} style={{ fontSize: 13, color: 'rgba(255,200,190,0.95)', marginTop: 8 }}>{erreur}</div> : null}
      {biblio ? (
        <div data-testid={`${id}-liste`} style={{ marginTop: 10, display: 'grid', gap: 8, maxHeight: 360, overflowY: 'auto' }}>
          {biblio.length === 0 ? <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.6)' }}>Aucun média de ce type pour le moment : importe-en un.</div> : null}
          {biblio.map((m) => (
            <div key={m.url} style={{ padding: 10, borderRadius: 10, background: m.url === actuel ? rgbaP(0.16) : 'rgba(255,255,255,0.05)',
              border: m.url === actuel ? `1px solid ${PRIMAIRE}` : '1px solid rgba(255,255,255,0.08)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <span style={{ flex: '1 1 160px', minWidth: 0, fontSize: 13.5, color: 'rgba(255,255,255,0.92)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {m.nom || 'Média'} <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12 }}>{taille(m.taille)}</span>
                </span>
                <button type="button" style={bouton(false)} onClick={() => setApercu(apercu === m.url ? '' : m.url)}>
                  <SvgIcon name="play" size={14} /> {apercu === m.url ? 'Masquer' : 'Voir'}
                </button>
                <button type="button" style={bouton(true)} onClick={() => { onChange(m.url); setBiblio(null); setApercu(''); }}
                        data-testid={`${id}-choisir`}>
                  {m.url === actuel ? 'Choisi' : 'Choisir'}
                </button>
              </div>
              {apercu === m.url ? <div style={{ marginTop: 8 }}><Lecteur type={type} url={m.url} /></div> : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
