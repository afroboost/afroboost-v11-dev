// Service Worker Afroboost V57 — Nuclear cache-bust + Push Notifications
// IMPORTANT: Changer CACHE_NAME force le reload sur TOUS les appareils

const CACHE_NAME = 'afroboost-v87';
// V87: Campagnes Multicanal & Chat Temps Réel — timezone fix, son notification, anti-doublon

// Installation — skip waiting pour activer immédiatement
self.addEventListener('install', (event) => {
  console.log('[SW] V54 installe — skip waiting');
  self.skipWaiting();
});

// Activation — supprime TOUS les anciens caches (nuclear purge)
self.addEventListener('activate', (event) => {
  console.log('[SW] V54 active — nuclear purge caches');
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

  // API calls — toujours réseau
  if (url.pathname.startsWith('/api/')) return;

  // HTML pages — toujours réseau (force reload)
  if (event.request.mode === 'navigate' || event.request.headers.get('accept')?.includes('text/html')) {
    event.respondWith(
      fetch(event.request).catch(() => caches.match(event.request))
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
});

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
    tag: 'afroboost-chat-sync',
    renotify: true,
    requireInteraction: false,
    silent: false,
    data: data.data
  };

  if ('actions' in Notification.prototype) {
    options.actions = [];
  }

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

// Clic sur la notification
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
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
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
// V78 deploy trigger
