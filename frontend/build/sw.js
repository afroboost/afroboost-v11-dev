// Service Worker Afroboost — Push Notifications + PWA Install
// IMPORTANT: Changer CACHE_NAME force le reload sur TOUS les appareils

const CACHE_NAME = 'afroboost-v123';
// V123: Pre-cache offline shell pour satisfaire critères d'installation PWA Chrome
// V122: SEO — titre et meta description optimisés pour Google
// V121: Fix PWA install — manifest corrigé, URL propres sans query params
// V120: Notifications push complètes — coach + abonné, badge PWA, toggle dans Chat

// V123: Ressources essentielles à pré-cacher pour le mode offline
// Chrome EXIGE que le SW puisse servir start_url offline pour autoriser l'installation PWA
const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/logo192.png',
  '/logo512.png',
  '/manifest.json'
];

// Installation — pré-cache les ressources essentielles + skip waiting
self.addEventListener('install', (event) => {
  console.log('[SW] V123 install — pre-caching offline shell');
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_URLS);
    }).then(() => self.skipWaiting())
  );
});

// Activation — supprime TOUS les anciens caches (nuclear purge)
self.addEventListener('activate', (event) => {
  console.log("[SW] V123 activate - nuclear purge + claim clients");
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => {
            console.log('[SW] Suppression ancien cache:', name);
            return caches.delete(name);
          })
      );
    }).then(() => clients.claim())
  );
});

// Fetch — network-first pour HTML, cache-first pour static assets
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // API calls — toujours réseau, pas d'interception
  if (url.pathname.startsWith('/api/')) return;

  // HTML pages / navigation — network-first avec fallback cache
  if (event.request.mode === 'navigate' || event.request.headers.get('accept')?.includes('text/html')) {
    event.respondWith(
      fetch(event.request).then((response) => {
        // V123: Mettre à jour le cache avec la dernière version de la page
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      }).catch(() => {
        // Offline: servir depuis le cache, ou fallback sur /index.html (SPA)
        return caches.match(event.request).then((cached) => {
          return cached || caches.match('/index.html');
        });
      })
    );
    return;
  }

  // Static assets (JS/CSS avec hash) — cache-first
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        if (cached) return cached;
        return fetch(event.request).then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return response;
        });
      })
    );
    return;
  }

  // Autres ressources (images, fonts, etc.) — network-first avec cache
  event.respondWith(
    fetch(event.request).then((response) => {
      if (response.ok) {
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
      }
      return response;
    }).catch(() => caches.match(event.request))
  );
});

// V120: Compteur de notifications non lues pour badge PWA
let unreadCount = 0;

// Reception des notifications push
self.addEventListener('push', (event) => {
  console.log('[SW] Notification push recue');

  let data = {
    title: 'Afroboost',
    body: 'Nouveau message de votre coach',
    icon: '/logo192.png',
    badge: '/logo192.png',
    data: { url: '/' }
  };

  if (event.data) {
    try {
      const payload = event.data.json();
      data = {
        title: payload.title || 'Afroboost',
        body: payload.body || payload.message || 'Nouveau message de votre coach',
        icon: payload.icon || '/logo192.png',
        badge: payload.badge || '/logo192.png',
        data: payload.data || { url: '/' }
      };
    } catch (e) {
      const text = event.data.text();
      if (text) data.body = text;
    }
  }

  const options = {
    body: data.body,
    icon: data.icon,
    badge: data.badge,
    vibrate: [200, 100, 200],
    tag: data.data?.type || 'afroboost-chat-sync',
    renotify: true,
    requireInteraction: false,
    silent: false,
    data: data.data
  };

  if ('actions' in Notification.prototype) {
    options.actions = [];
  }

  // V120: Incrementer le badge PWA sur l'icone de l'app
  unreadCount++;
  event.waitUntil(
    Promise.all([
      self.registration.showNotification(data.title, options),
      // Badge API (Chrome 81+, Edge 81+) — affiche un compteur sur l'icone PWA
      navigator.setAppBadge ? navigator.setAppBadge(unreadCount).catch(() => {}) : Promise.resolve()
    ])
  );
});

// Clic sur la notification
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  // V120: Réinitialiser le badge au clic
  unreadCount = Math.max(0, unreadCount - 1);
  if (navigator.clearAppBadge && unreadCount === 0) {
    navigator.clearAppBadge().catch(() => {});
  } else if (navigator.setAppBadge && unreadCount > 0) {
    navigator.setAppBadge(unreadCount).catch(() => {});
  }

  const urlToOpen = event.notification.data?.url || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        for (const client of clientList) {
          if (client.url.includes(self.location.origin) && 'focus' in client) {
            return client.focus();
          }
        }
        if (clients.openWindow) return clients.openWindow(urlToOpen);
      })
  );
});

// Fermeture notification
self.addEventListener('notificationclose', (event) => {
  console.log('[SW] Notification fermee');
});

// Message du client
self.addEventListener('message', (event) => {
  console.log('[SW] Message recu:', event.data);
  // V120: Reset badge quand l'app signale que le chat est ouvert
  if (event.data && event.data.type === 'CLEAR_BADGE') {
    unreadCount = 0;
    if (navigator.clearAppBadge) navigator.clearAppBadge().catch(() => {});
    return;
  }
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
