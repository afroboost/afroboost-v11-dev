/**
 * MediaViewer - Lecteur Afroboost Mode Cinéma FINAL
 * Supporte: YouTube, Google Drive, vidéos directes (MP4)
 * Design cinéma, bouton CTA #E91E63
 */
import { useState, useEffect } from 'react';
import axios from 'axios';
import { copyToClipboard } from '../utils/clipboard'; // Fallback mobile robuste

const API = process.env.REACT_APP_BACKEND_URL || '';

// Détecte le type de vidéo
const getVideoType = (url) => {
  if (!url) return 'unknown';
  const lowerUrl = url.toLowerCase();
  
  // YouTube
  if (lowerUrl.includes('youtube.com') || lowerUrl.includes('youtu.be')) {
    return 'youtube';
  }
  
  // Google Drive
  if (lowerUrl.includes('drive.google.com')) {
    return 'gdrive';
  }
  
  // Vidéo directe (MP4, WebM, etc.)
  if (['.mp4', '.webm', '.mov', '.m4v', '.ogv'].some(ext => lowerUrl.includes(ext))) {
    return 'direct';
  }
  
  return 'unknown';
};

// Extrait l'ID YouTube d'une URL
const extractYouTubeId = (url) => {
  if (!url) return null;
  // Format: youtube.com/watch?v=ID
  const watchMatch = url.match(/[?&]v=([a-zA-Z0-9_-]{11})/);
  if (watchMatch) return watchMatch[1];
  // Format: youtu.be/ID
  const shortMatch = url.match(/youtu\.be\/([a-zA-Z0-9_-]{11})/);
  if (shortMatch) return shortMatch[1];
  // Format: youtube.com/embed/ID
  const embedMatch = url.match(/embed\/([a-zA-Z0-9_-]{11})/);
  if (embedMatch) return embedMatch[1];
  return null;
};

// Extrait l'ID Google Drive d'une URL
const extractGoogleDriveId = (url) => {
  if (!url) return null;
  const match = url.match(/\/d\/([a-zA-Z0-9_-]+)/);
  if (match) return match[1];
  const idMatch = url.match(/[?&]id=([a-zA-Z0-9_-]+)/);
  if (idMatch) return idMatch[1];
  return null;
};

const MediaViewer = ({ slug }) => {
  const [media, setMedia] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadMedia = async () => {
      try {
        console.log('[MediaViewer] Chargement du slug:', slug);
        const response = await axios.get(`${API}/api/media/${slug}`);
        console.log('[MediaViewer] Données reçues:', JSON.stringify(response.data));
        setMedia(response.data);
      } catch (err) {
        console.error('[MediaViewer] Erreur:', err);
        setError(err.response?.data?.detail || 'Média non trouvé');
      } finally {
        setLoading(false);
      }
    };
    if (slug) loadMedia();
  }, [slug]);

  // État de chargement
  if (loading) {
    return (
      <div style={styles.loadingContainer}>
        <div style={styles.spinner}></div>
        <p style={styles.loadingText}>Chargement...</p>
      </div>
    );
  }

  // État d'erreur
  if (error) {
    return (
      <div style={styles.errorContainer}>
        <p style={styles.errorText}>{error}</p>
        <a href="https://afroboosteur.com" style={styles.errorLink}>Retour à l'accueil</a>
      </div>
    );
  }

  // Protection
  if (!media) {
    return (
      <div style={styles.errorContainer}>
        <p style={styles.errorText}>Données non disponibles</p>
        <a href="https://afroboosteur.com" style={styles.errorLink}>Retour à l'accueil</a>
      </div>
    );
  }

  // Détecter le type de vidéo et générer l'URL d'embed
  const videoType = getVideoType(media.video_url);
  let embedUrl = null;
  let thumbnailUrl = media.thumbnail || media.custom_thumbnail;

  if (videoType === 'youtube') {
    const ytId = media.youtube_id || extractYouTubeId(media.video_url);
    if (ytId) {
      embedUrl = `https://www.youtube.com/embed/${ytId}?modestbranding=1&rel=0`;
      if (!thumbnailUrl) {
        thumbnailUrl = `https://img.youtube.com/vi/${ytId}/maxresdefault.jpg`;
      }
    }
  } else if (videoType === 'gdrive') {
    const driveId = extractGoogleDriveId(media.video_url);
    if (driveId) {
      embedUrl = `https://drive.google.com/file/d/${driveId}/preview`;
    }
  }

  return (
    <div style={styles.page}>
      {/* Header */}
      <header style={styles.header}>
        <a href="https://afroboosteur.com" style={styles.logo}>
          <span style={styles.logoIcon}>🎧</span>
          <span style={styles.logoText}>Afroboost</span>
        </a>
      </header>

      {/* Main Content */}
      <main style={styles.main}>
        {/* Titre */}
        <h1 style={styles.title} data-testid="media-title">{media.title || 'Vidéo Afroboost'}</h1>

        {/* Lecteur Vidéo */}
        <div style={styles.videoWrapper} data-testid="video-container">
          {embedUrl ? (
            <iframe
              src={embedUrl}
              title={media.title || 'Vidéo Afroboost'}
              style={styles.videoIframe}
              frameBorder="0"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen"
              allowFullScreen
              data-testid={videoType === 'youtube' ? 'youtube-player' : 'google-drive-player'}
            />
          ) : videoType === 'direct' ? (
            <video
              src={media.video_url}
              poster={thumbnailUrl}
              style={styles.videoPlayer}
              controls
              controlsList="nodownload"
              playsInline
              data-testid="html5-video"
            >
              Votre navigateur ne supporte pas la lecture vidéo.
            </video>
          ) : (
            /* Fallback: lien vers la vidéo originale */
            <a href={media.video_url} target="_blank" rel="noopener noreferrer" style={styles.fallbackLink}>
              <div style={{...styles.thumbnailContainer, backgroundImage: thumbnailUrl ? `url(${thumbnailUrl})` : 'none'}}>
                <div style={styles.playOverlay}>
                  <svg width="80" height="80" viewBox="0 0 80 80" fill="none">
                    <circle cx="40" cy="40" r="38" fill="#E91E63" fillOpacity="0.95"/>
                    <path d="M32 25L58 40L32 55V25Z" fill="white"/>
                  </svg>
                  <p style={{color: '#fff', marginTop: 10}}>Cliquez pour voir la vidéo</p>
                </div>
              </div>
            </a>
          )}
        </div>

        {/* Description */}
        {media.description && media.description.trim() !== '' && (
          <p style={styles.description} data-testid="media-description">
            {media.description}
          </p>
        )}

        {/* Bouton CTA ROSE #E91E63 */}
        {media.cta_text && media.cta_link && (
          <div style={styles.ctaContainer} data-testid="cta-section">
            <a
              href={media.cta_link}
              target="_blank"
              rel="noopener noreferrer"
              style={styles.ctaButton}
              data-testid="cta-button"
            >
              {media.cta_text}
            </a>
          </div>
        )}

        {/* Partage */}
        <div style={styles.shareSection}>
          <button
            onClick={async () => {
              const shareUrl = `https://afroboosteur.com/#/v/${media.slug}`;
              const result = await copyToClipboard(shareUrl);
              if (result.success) alert('Lien copié !');
              else alert('Impossible de copier le lien. Copiez-le manuellement : ' + shareUrl);
            }}
            style={styles.shareButton}
            data-testid="copy-link-btn"
          >
            📋 Copier le lien
          </button>
          <a
            href={`https://wa.me/?text=${encodeURIComponent((media.title || 'Vidéo') + '\nhttps://afroboosteur.com/#/v/' + media.slug)}`}
            target="_blank"
            rel="noopener noreferrer"
            style={styles.whatsappButton}
            data-testid="whatsapp-share-btn"
          >
            WhatsApp
          </a>
        </div>
      </main>

      {/* Footer */}
      <footer style={styles.footer}>
        © Afroboost 2025
      </footer>
    </div>
  );
};

// Styles - Mode Cinéma avec CTA #E91E63
const styles = {
  page: {
    minHeight: '100vh',
    backgroundColor: '#0c0014',
    color: '#FFFFFF',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif',
    display: 'flex',
    flexDirection: 'column',
  },
  loadingContainer: {
    minHeight: '100vh',
    backgroundColor: '#0c0014',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
  },
  spinner: {
    width: '40px',
    height: '40px',
    border: '3px solid #333',
    borderTopColor: '#E91E63',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
  },
  loadingText: {
    color: '#FFFFFF',
    marginTop: '15px',
    fontSize: '16px',
  },
  errorContainer: {
    minHeight: '100vh',
    backgroundColor: '#0c0014',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '20px',
  },
  errorText: {
    color: '#ff6b6b',
    fontSize: '18px',
    marginBottom: '20px',
  },
  errorLink: {
    color: '#E91E63',
    textDecoration: 'none',
  },
  header: {
    backgroundColor: '#E91E63',
    padding: '12px 20px',
    textAlign: 'center',
  },
  logo: {
    color: '#FFFFFF',
    textDecoration: 'none',
    display: 'inline-flex',
    alignItems: 'center',
    gap: '8px',
  },
  logoIcon: {
    fontSize: '22px',
  },
  logoText: {
    fontSize: '20px',
    fontWeight: 'bold',
  },
  main: {
    flex: 1,
    maxWidth: '900px',
    width: '100%',
    margin: '0 auto',
    padding: '25px 15px',
  },
  title: {
    fontSize: '24px',
    fontWeight: 'bold',
    textAlign: 'center',
    marginBottom: '20px',
    lineHeight: '1.3',
    color: '#FFFFFF',
  },
  videoWrapper: {
    position: 'relative',
    width: '100%',
    aspectRatio: '16 / 9',
    backgroundColor: '#000',
    borderRadius: '12px',
    overflow: 'hidden',
    boxShadow: '0 0 30px rgba(233, 30, 99, 0.3)',
  },
  videoIframe: {
    position: 'absolute',
    top: 0,
    left: 0,
    width: '100%',
    height: '100%',
    border: 'none',
  },
  videoPlayer: {
    width: '100%',
    height: '100%',
    objectFit: 'cover',
  },
  fallbackLink: {
    display: 'block',
    width: '100%',
    height: '100%',
  },
  thumbnailContainer: {
    width: '100%',
    height: '100%',
    backgroundSize: 'cover',
    backgroundPosition: 'center',
    backgroundColor: '#1a1a2e',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  playOverlay: {
    textAlign: 'center',
  },
  description: {
    fontSize: '16px',
    lineHeight: '1.7',
    color: '#FFFFFF',
    textAlign: 'center',
    marginTop: '25px',
    marginBottom: '25px',
    whiteSpace: 'pre-wrap',
    padding: '0 10px',
  },
  ctaContainer: {
    textAlign: 'center',
    marginBottom: '35px',
  },
  ctaButton: {
    display: 'inline-block',
    padding: '20px 55px',
    backgroundColor: '#E91E63',
    color: '#FFFFFF',
    textDecoration: 'none',
    borderRadius: '50px',
    fontSize: '18px',
    fontWeight: 'bold',
    boxShadow: '0 6px 25px rgba(233, 30, 99, 0.5)',
    textTransform: 'uppercase',
    letterSpacing: '1px',
  },
  shareSection: {
    display: 'flex',
    justifyContent: 'center',
    gap: '10px',
    flexWrap: 'wrap',
    paddingTop: '20px',
    borderTop: '1px solid #333',
  },
  shareButton: {
    padding: '10px 20px',
    backgroundColor: '#1a1a1a',
    color: '#FFFFFF',
    border: '1px solid #333',
    borderRadius: '8px',
    cursor: 'pointer',
    fontSize: '14px',
  },
  whatsappButton: {
    padding: '10px 20px',
    backgroundColor: '#25D366',
    color: '#FFFFFF',
    textDecoration: 'none',
    borderRadius: '8px',
    fontSize: '14px',
  },
  footer: {
    textAlign: 'center',
    padding: '20px',
    color: '#666',
    fontSize: '12px',
  },
};

export default MediaViewer;
