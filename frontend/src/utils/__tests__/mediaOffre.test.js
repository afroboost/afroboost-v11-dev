/** MÉDIAS D'UNE OFFRE — une seule règle de lecture (miniature dédiée prioritaire, champ vidéo = image possible). */
import { analyserMediaUrl, mediaPrincipal, champVideoEstImage } from '../mediaOffre';

describe('analyserMediaUrl (ex-parseMediaUrl d’App.js)', () => {
  test('YouTube / Vimeo / fichier vidéo / Cloudinary vidéo / image / défaut image', () => {
    expect(analyserMediaUrl('https://youtu.be/dQw4w9WgXcQ')).toEqual({ type: 'youtube', id: 'dQw4w9WgXcQ' });
    expect(analyserMediaUrl('https://vimeo.com/12345')).toEqual({ type: 'vimeo', id: '12345' });
    expect(analyserMediaUrl('/api/files/x/video_x.mp4?t=1')).toEqual({ type: 'video', url: '/api/files/x/video_x.mp4?t=1' });
    expect(analyserMediaUrl('https://res.cloudinary.com/d/video/upload/v1/x')).toEqual({ type: 'video', url: 'https://res.cloudinary.com/d/video/upload/v1/x' });
    expect(analyserMediaUrl('/api/files/x/image_x.png')).toEqual({ type: 'image', url: '/api/files/x/image_x.png' });
    expect(analyserMediaUrl('https://cdn.movies.example/a')).toEqual({ type: 'image', url: 'https://cdn.movies.example/a' });
    expect(analyserMediaUrl('')).toBeNull();
    expect(analyserMediaUrl(null)).toBeNull();
  });
});

describe('mediaPrincipal — le cas réel de production', () => {
  test('Fondateurs : un .png dans le champ vidéo, rien d’autre → poster = ce .png, aucune vidéo', () => {
    const o = { thumbnail: '', videoUrl: '/api/files/a/image_a.png', images: [] };
    expect(mediaPrincipal(o)).toEqual({ poster: '/api/files/a/image_a.png', video: '' });
    expect(champVideoEstImage(o)).toBe(true);
  });
  test('vidéo + miniature dédiée : la miniature est le poster, la vidéo reste lisible', () => {
    const o = { thumbnail: 'https://x/mini.jpg', videoUrl: '/api/files/b/video_b.mp4', images: ['https://x/2.jpg'] };
    expect(mediaPrincipal(o)).toEqual({ poster: 'https://x/mini.jpg', video: '/api/files/b/video_b.mp4' });
    expect(champVideoEstImage(o)).toBe(false);
  });
  test('Pulse : miniature = .mp4, images = [.mp4] → vidéo trouvée, aucun poster', () => {
    const o = { thumbnail: '/api/files/c/video_c.mp4', videoUrl: '', images: ['/api/files/c/video_c.mp4'] };
    expect(mediaPrincipal(o)).toEqual({ poster: '', video: '/api/files/c/video_c.mp4' });
  });
  test('vidéo seule : aucun poster, la vidéo', () => {
    expect(mediaPrincipal({ videoUrl: '/api/files/d/video_d.mp4' })).toEqual({ poster: '', video: '/api/files/d/video_d.mp4' });
  });
  test('rien : rien', () => {
    expect(mediaPrincipal({})).toEqual({ poster: '', video: '' });
    expect(mediaPrincipal(null)).toEqual({ poster: '', video: '' });
  });
});
