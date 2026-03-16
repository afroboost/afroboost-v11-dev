"""
MEDIA HANDLER - Module pour la gestion des médias YouTube/Google Drive
Détecte et transforme les liens médias pour l'affichage dans le chat.
"""

import re
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# === PATTERNS REGEX ===
YOUTUBE_PATTERNS = [
    re.compile(r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})(?:[?&]|$)'),
    re.compile(r'youtube\.com/embed/([a-zA-Z0-9_-]{11})'),
    re.compile(r'youtube\.com/shorts/([a-zA-Z0-9_-]{11})')
]

GOOGLE_DRIVE_FILE_PATTERN = re.compile(r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)')
GOOGLE_DRIVE_OPEN_PATTERN = re.compile(r'drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)')


def get_media_type(url: str) -> Dict[str, Any]:
    """
    Détecte le type de média d'une URL.
    
    Returns:
        dict avec type, video_id/file_id, embed_url, thumbnail_url, direct_url
    """
    if not url or not isinstance(url, str):
        return {"type": "unknown", "error": "URL invalide"}
    
    url = url.strip()
    
    # === YOUTUBE ===
    for pattern in YOUTUBE_PATTERNS:
        match = pattern.search(url)
        if match:
            video_id = match.group(1)
            return {
                "type": "youtube",
                "platform": "youtube",
                "video_id": video_id,
                "direct_url": f"https://www.youtube.com/watch?v={video_id}",
                "embed_url": f"https://www.youtube.com/embed/{video_id}?rel=0&modestbranding=1&mute=1&playsinline=1",
                "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
            }
    
    # === GOOGLE DRIVE ===
    for pattern in [GOOGLE_DRIVE_FILE_PATTERN, GOOGLE_DRIVE_OPEN_PATTERN]:
        match = pattern.search(url)
        if match:
            file_id = match.group(1)
            return {
                "type": "drive",
                "platform": "google_drive",
                "file_id": file_id,
                "direct_url": f"https://lh3.googleusercontent.com/d/{file_id}=w1000",
                "thumbnail_url": f"https://drive.google.com/thumbnail?id={file_id}&sz=w400",
                "embed_url": f"https://drive.google.com/file/d/{file_id}/preview"
            }
    
    # Log si lien Drive mal formaté (contient drive.google mais pas reconnu)
    if 'drive.google.com' in url.lower():
        logger.warning(f"[MEDIA] Lien Drive non reconnu: {url[:100]}")
    
    # === IMAGE DIRECTE ===
    image_extensions = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg']
    ext = url.split('.')[-1].lower().split('?')[0] if '.' in url else ''
    if ext in image_extensions:
        return {
            "type": "image",
            "platform": "direct",
            "direct_url": url,
            "thumbnail_url": url
        }
    
    # === VIDÉO DIRECTE ===
    video_extensions = ['mp4', 'webm', 'ogg', 'mov']
    if ext in video_extensions:
        return {
            "type": "video",
            "platform": "direct",
            "direct_url": url
        }
    
    return {"type": "link", "platform": "unknown", "direct_url": url}


def extract_youtube_id(url: str) -> Optional[str]:
    """Extrait l'ID d'une vidéo YouTube."""
    result = get_media_type(url)
    return result.get("video_id") if result.get("type") == "youtube" else None


def drive_to_direct_url(share_url: str) -> Optional[str]:
    """Transforme un lien Drive de partage en lien direct."""
    result = get_media_type(share_url)
    return result.get("direct_url") if result.get("type") == "drive" else None


def detect_media_in_text(text: str) -> Optional[Dict[str, Any]]:
    """
    Scanne un texte pour trouver le premier lien média (YouTube/Drive/Image).
    Retourne les infos du média trouvé ou None.
    """
    if not text:
        return None
    
    # Pattern URL générique
    url_pattern = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')
    urls = url_pattern.findall(text)
    
    for url in urls:
        media_info = get_media_type(url)
        if media_info.get("type") in ["youtube", "drive", "image", "video"]:
            media_info["original_url"] = url
            return media_info
    
    return None


def is_media_url(url: str) -> bool:
    """Vérifie si une URL est un média supporté."""
    result = get_media_type(url)
    return result.get("type") in ["youtube", "drive", "image", "video"]
