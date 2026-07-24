// V224 — Carte d'offre pour le dashboard coach.
import React from 'react';
// V228: seules les fleches d'ordre (▲/▼) restaient en caracteres typographiques.
// Elles n'ont pas d'equivalent parmi les composants locaux definis plus bas
// (ClockIcon/PinIcon/... ), d'ou le recours au jeu partage SvgIcon pour ces
// deux traces uniquement. Les composants locaux restent la reference du fichier.
import SvgIcon from '../SvgIcon';

const PINK = 'var(--primary-color, #D91CD2)';

// V227: detection « ce media est-il une video ? » pour la miniature du dashboard.
// Jusqu'ici la couverture etait TOUJOURS rendue en <img> : un fichier .mp4/.mov
// donnait un cadre vide. La logique de reconnaissance est celle, DURCIE, de
// parseMediaUrl (frontend/src/App.js) : l'extension doit se trouver en FIN DE
// CHEMIN, apres retrait d'une eventuelle chaine de requete (?) ou ancre (#).
// Un `includes('.mov')` naif prendrait une image hebergee sur un domaine
// `cdn.movie...` (ou dans un dossier `/x.movies/`) pour une video et afficherait
// un lecteur noir. parseMediaUrl n'est pas exportee : sa logique est reprise ici
// volontairement, sans import ni modification de App.js.
const V227_VIDEO_EXTENSIONS = ['.mp4', '.webm', '.mov', '.avi', '.m4v', '.ogv'];

function isVideoUrl(url) {
  if (!url || typeof url !== 'string') return false;
  const lowerPath = url.trim().toLowerCase().split('#')[0].split('?')[0];
  return V227_VIDEO_EXTENSIONS.some((ext) => lowerPath.endsWith(ext));
}

// V234 — image d'apercu (« poster ») pour une video hebergee par Cloudinary.
//
// POURQUOI UNE IMAGE PLUTOT QUE LA VIDEO
// La couverture n'a besoin que d'une vignette fixe. Charger la video pour cela
// coute 427 Ko par carte (mesure sur l'offre « Laff Festival ») contre 14 Ko
// pour le poster, sur un ecran qui liste toutes les offres du coach. Cloudinary
// extrait la premiere image cote serveur, ce qui evite aussi de dependre du
// format que le navigateur recoit : `f_auto` sert du WebM a Chrome, dont un
// <video preload="metadata"> n'affiche pas toujours la premiere frame.
//
// TRANSFORMATION
//   so_0    -> image prise a la seconde 0
//   w_400,h_225,c_fill -> 16/9, la geometrie exacte du cadre de rendu
//                         ci-dessous (aspectRatio 16/9 + objectFit cover),
//                         donc aucun recadrage subi
//   f_jpg   -> format fixe, independant du navigateur
// `q_auto,f_auto` est retire au prealable : ces deux directives s'appliquent a
// la LIVRAISON de la video et entrent en conflit avec `f_jpg`.
//
// Renvoie `null` si l'URL n'est pas une video Cloudinary — l'appelant retombe
// alors sur le <video> d'origine (V227), inchange pour les fichiers locaux.
function v234CloudinaryPoster(url) {
  if (!url || typeof url !== 'string') return null;
  if (!url.includes('cloudinary.com') || !url.includes('/video/upload/')) return null;
  return url
    .replace(/\/video\/upload\/(?:q_auto,f_auto\/)?/, '/video/upload/so_0,w_400,h_225,c_fill,f_jpg/')
    .replace(/\.[^.]+$/, '.jpg');
}

// V226: icones SVG extraites en petits composants locaux (a la place des
// emoji ⏱/📍/👥) — memes traces que la carte publique (App.js), reutilisees
// a plusieurs endroits de cette carte plutot que recopiees inline. `color`
// est parametrable (gris #aaa par defaut, valeur de marque possible pour un
// usage cliquable ailleurs) ; `ClockIcon` n'est pas encore consommee dans
// cette carte (la duree n'y est pour l'instant qu'affichee en texte) mais
// fait partie du meme jeu d'icones que le pin et les personnes.
// V227: la couleur par defaut passe de #aaa a #ccc. Une revue V226 avait releve
// que l'icone etait tracee en #aaa alors que le texte qu'elle accompagne est en
// #ccc : invisible tant que les pictogrammes etaient des emoji colores, visible
// des qu'ils deviennent des traces monochromes. Les deux sont desormais alignes.
// Le pin garde une couleur de marque explicite (voir son usage plus bas).
const ICON_PROPS = { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round' };

function ClockIcon({ color = '#ccc' }) {
  return (
    <svg {...ICON_PROPS} stroke={color}>
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}

function PinIcon({ color = '#ccc' }) {
  return (
    <svg {...ICON_PROPS} stroke={color}>
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  );
}

function PeopleIcon({ color = '#ccc' }) {
  return (
    <svg {...ICON_PROPS} stroke={color}>
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}

// V227: la serie d'icones extraite en V226 (ClockIcon/PinIcon/PeopleIcon) est
// completee ici plutot que de recopier du balisage SVG dans le rendu. `size`
// permet de reutiliser le meme trace pour une ligne meta (14px) et pour le
// placeholder de couverture (32px), sans dupliquer le composant.
function PencilIcon({ color = '#fff', size = 14 }) {
  return (
    <svg {...ICON_PROPS} width={size} height={size} stroke={color}>
      {/* V228: trace aligne sur SvgIcon.edit (Feather "edit", cadre + crayon)
          plutot que le "edit-3" d'origine (`M12 20h9` + crayon), pour que ce
          fichier de reference n'affiche pas deux dessins differents pour la
          meme action "Modifier". Voir SvgIcon.js pour le detail du choix. */}
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  );
}

function CopyIcon({ color = '#fff', size = 14 }) {
  return (
    <svg {...ICON_PROPS} width={size} height={size} stroke={color}>
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

function TrashIcon({ color = '#ef4444', size = 14 }) {
  return (
    <svg {...ICON_PROPS} width={size} height={size} stroke={color}>
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6" />
      <path d="M14 11v6" />
      <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
  );
}

function LockIcon({ color = '#888', size = 14 }) {
  return (
    <svg {...ICON_PROPS} width={size} height={size} stroke={color}>
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}

function HeadphonesIcon({ color = '#aaa', size = 32 }) {
  return (
    <svg {...ICON_PROPS} width={size} height={size} stroke={color}>
      <path d="M3 18v-6a9 9 0 0 1 18 0v6" />
      <path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3z" />
      <path d="M3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z" />
    </svg>
  );
}

export default function OfferCard({
  offer,
  onEdit,
  onDuplicate,
  onDelete,
  onToggleVisible,
  // V224: props OPTIONNELLES et non cassantes.
  // canDelete absent => true (comportement anterieur inchange).
  canDelete = true,
  // V224: reorganisation. Les boutons n'apparaissent que si le parent fournit
  // les callbacks (masques par exemple quand une recherche filtre la grille).
  onMoveUp,
  onMoveDown,
  canMoveUp = false,
  canMoveDown = false,
  // V226: glisser-deposer. Props OPTIONNELLES : un montage qui ne les passe pas
  // obtient exactement la carte d'avant (draggable=false, aucun handler, curseur
  // par defaut, bordure et opacite inchangees).
  draggable = false,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
  isDragging = false,
  isDragOver = false
}) {
  // V234: `offer.videoUrl` entre dans la chaine de reprise. C'est la CAUSE
  // RACINE de l'absence d'apercu signalee : une offre dont la seule illustration
  // est une video (images vides, thumbnail vide) donnait `cover = ''` et
  // tombait sur le placeholder casque — le <video> de V227 n'etait jamais
  // atteint. L'ordre de priorite existant est inchange : une image explicite
  // passe toujours avant la video.
  const cover = (offer.images || []).find(Boolean) || offer.thumbnail || offer.videoUrl || '';
  const v234CoverIsVideo = Boolean(cover) && isVideoUrl(cover);
  const v234Poster = v234CoverIsVideo ? v234CloudinaryPoster(cover) : null;
  const isVisible = offer.visible !== false;
  // V224: garde coherente avec les autres lignes meta (on n'affiche rien plutot
  // que « undefined CHF » quand le champ est absent).
  const hasPrice = offer.price !== null && offer.price !== undefined && offer.price !== '';

  return (
    <div
      className="transition-all"
      // V226: la carte n'est glissable que si le parent l'autorise explicitement.
      draggable={draggable}
      data-offer-id={offer.id}
      onDragStart={draggable && onDragStart ? (e) => onDragStart(e, offer) : undefined}
      // V226: onDragOver/onDrop restent actifs meme sur une carte non glissable :
      // une carte doit pouvoir servir de CIBLE de depot sans etre elle-meme
      // deplacable (offre d'un autre coach, par exemple).
      onDragOver={onDragOver ? (e) => onDragOver(e, offer) : undefined}
      onDrop={onDrop ? (e) => onDrop(e, offer) : undefined}
      onDragEnd={onDragEnd ? (e) => onDragEnd(e, offer) : undefined}
      style={{
        background: '#1a1a2e',
        // V226: retour visuel sur la cible survolee. La largeur reste a 1px et
        // le halo est un box-shadow : aucun decalage de mise en page au survol.
        border: `1px solid ${isDragOver ? PINK : 'rgba(var(--primary-rgb, 217, 28, 210), 0.2)'}`,
        boxShadow: isDragOver ? `0 0 0 2px rgba(var(--primary-rgb, 217, 28, 210), 0.45)` : 'none',
        borderRadius: '12px',
        overflow: 'hidden',
        // V226: grab au repos, grabbing pendant le deplacement.
        cursor: draggable ? (isDragging ? 'grabbing' : 'grab') : 'default',
        opacity: isDragging ? 0.5 : 1
      }}
    >
      {/* V227: une couverture video est rendue en <video> autoplay muet et non
          plus en <img> (qui n'affichait qu'un cadre vide). Le cas image est
          strictement inchange. */}
      {v234Poster ? (
        /* V234: video Cloudinary — vignette servie par le CDN (14 Ko) au lieu
           de la video entiere (427 Ko) autoplayee. `onError` retombe sur le
           fond neutre plutot que d'afficher une icone d'image cassee, au cas ou
           Cloudinary ne saurait pas extraire de frame. */
        <img
          src={v234Poster}
          alt={offer.name}
          style={{ width: '100%', aspectRatio: '16 / 9', objectFit: 'cover', background: '#0a0a0f' }}
          loading="lazy"
          onError={(e) => { e.currentTarget.style.visibility = 'hidden'; }}
        />
      ) : v234CoverIsVideo ? (
        <video
          src={cover}
          style={{ width: '100%', aspectRatio: '16 / 9', objectFit: 'cover', background: '#0a0a0f' }}
          autoPlay
          muted
          loop
          playsInline
          preload="metadata"
        />
      ) : cover ? (
        <img src={cover} alt={offer.name} style={{ width: '100%', aspectRatio: '16 / 9', objectFit: 'cover' }} />
      ) : (
        /* V227: 🎧 remplace par HeadphonesIcon — meme encombrement (32px). */
        <div style={{ width: '100%', aspectRatio: '16 / 9', background: '#0a0a0f', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><HeadphonesIcon /></div>
      )}

      <div style={{ padding: '14px' }}>
        <h3 className="text-white font-semibold text-sm mb-2">{offer.name}</h3>

        <div className="flex items-center gap-2 mb-2">
          <span
            className="text-xs px-2 py-0.5 rounded-full"
            style={{
              background: isVisible ? 'rgba(34,197,94,0.15)' : 'rgba(120,120,120,0.15)',
              color: isVisible ? '#22c55e' : '#888'
            }}
          >
            {isVisible ? 'Active' : 'Masquee'}
          </span>
          <button type="button" onClick={() => onToggleVisible(offer)} className="text-xs" style={{ color: PINK }}>
            {isVisible ? 'Masquer' : 'Activer'}
          </button>
          {/* V224: affordance « offre protegee » reprise de l'ancien rendu en liste */}
          {!canDelete && (
            <span
              className="text-xs px-2 py-0.5 rounded-full inline-flex items-center gap-1"
              style={{ background: 'rgba(120,120,120,0.15)', color: '#888' }}
              title="Vous ne pouvez supprimer que vos propres offres"
            >
              {/* V227: 🔒 remplace par LockIcon, teinte sur la couleur du texte porteur */}
              <LockIcon color="#888" />
              Protégée
            </span>
          )}
        </div>

        {offer.description && (
          <p className="text-xs mb-2" style={{ color: '#aaa' }}>
            {offer.description.length > 110 ? offer.description.slice(0, 110) + '…' : offer.description}
          </p>
        )}

        {/* V224: chaque ligne meta se masque si sa donnee est absente */}
        <p className="text-xs" style={{ color: '#ccc' }}>
          {/* V224: le nom n'est plus repete ici, il est deja affiche en titre */}
          {[hasPrice ? `${offer.price} CHF` : null, offer.duration_minutes ? `${offer.duration_minutes} min` : null]
            .filter(Boolean).join(' · ')}
        </p>
        {/* V226: 📍 remplace par PinIcon — meme condition de masquage inchangee. */}
        {/* V227: le pin est trace en couleur de marque (#D91CD2), seul accent
            colore des lignes meta — les autres icones suivent le texte (#ccc). */}
        {offer.location && (
          <p className="text-xs mt-1 flex items-center gap-1" style={{ color: '#ccc' }}>
            <PinIcon color={PINK} />
            {offer.location}
          </p>
        )}
        {/* V224 (revue finale): capacite, et non compteur. Le rendu precedent
            ecrivait un « 0/ » en dur — il n'existe aucun champ participants_count
            cote backend pour l'alimenter. Cohérent avec la carte publique
            (App.js). Le comptage reel des inscrits est un chantier separe. */}
        {/* V226: 👥 remplace par PeopleIcon — `!= null` (et non la veracite)
            conserve : un 0 est une valeur legitime. */}
        {offer.max_participants != null && (
          <p className="text-xs mt-1 flex items-center gap-1" style={{ color: '#ccc' }}>
            <PeopleIcon />
            {offer.max_participants} places
          </p>
        )}

        <div className="flex gap-2 mt-3">
          {/* V227: ✏️ et 📋 remplaces par PencilIcon / CopyIcon */}
          <button type="button" onClick={() => onEdit(offer)} className="flex-1 text-xs py-2 rounded-lg inline-flex items-center justify-center gap-1.5" style={{ background: PINK, color: '#fff' }}><PencilIcon />Modifier</button>
          <button type="button" onClick={() => onDuplicate(offer)} title="Dupliquer" className="text-xs py-2 px-3 rounded-lg inline-flex items-center justify-center" style={{ background: '#0a0a0f', border: '1px solid #333', color: '#fff' }}><CopyIcon /></button>
          {/* V224: bouton Supprimer estompe et desactive pour une offre d'un autre coach */}
          <button
            type="button"
            onClick={() => onDelete(offer.id)}
            disabled={!canDelete}
            title={canDelete ? 'Supprimer' : 'Vous ne pouvez supprimer que vos propres offres'}
            className="text-xs py-2 px-3 rounded-lg inline-flex items-center justify-center"
            style={{
              background: '#0a0a0f',
              border: '1px solid #333',
              color: canDelete ? '#ef4444' : '#666',
              opacity: canDelete ? 1 : 0.4,
              cursor: canDelete ? 'pointer' : 'not-allowed'
            }}
          >
            {/* V227: 🗑️ / 🔒 remplaces par TrashIcon / LockIcon — chaque trace
                reprend la couleur deja calculee pour le texte du bouton. */}
            {canDelete ? <TrashIcon color="#ef4444" /> : <LockIcon color="#666" />}
          </button>
        </div>

        {/* V224: reorganisation de l'ordre d'affichage (champ `position`) */}
        {/* V227: les fleches sont MASQUEES a partir de 768px (md:hidden), pas
            supprimees — le bloc reste rendu. Sur desktop, le glisser-deposer
            cable en V226 prend le relais ; sur mobile les fleches restent le
            seul chemin, le drag & drop HTML5 ne repondant pas au doigt. */}
        {(onMoveUp || onMoveDown) && (
          <div className="flex md:hidden items-center gap-2 mt-2">
            <span className="text-xs" style={{ color: '#777' }}>Ordre</span>
            <button
              type="button"
              onClick={() => onMoveUp && onMoveUp(offer)}
              disabled={!canMoveUp}
              title="Monter cette offre"
              aria-label="Monter cette offre"
              className="text-xs py-1 px-2 rounded-lg inline-flex items-center justify-center"
              style={{
                background: '#0a0a0f',
                border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.2)',
                color: '#fff',
                opacity: canMoveUp ? 1 : 0.3,
                cursor: canMoveUp ? 'pointer' : 'not-allowed'
              }}
            ><SvgIcon name="arrowUp" size={14} /></button>
            <button
              type="button"
              onClick={() => onMoveDown && onMoveDown(offer)}
              disabled={!canMoveDown}
              title="Descendre cette offre"
              aria-label="Descendre cette offre"
              className="text-xs py-1 px-2 rounded-lg inline-flex items-center justify-center"
              style={{
                background: '#0a0a0f',
                border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.2)',
                color: '#fff',
                opacity: canMoveDown ? 1 : 0.3,
                cursor: canMoveDown ? 'pointer' : 'not-allowed'
              }}
            ><SvgIcon name="arrowDown" size={14} /></button>
          </div>
        )}
      </div>
    </div>
  );
}
