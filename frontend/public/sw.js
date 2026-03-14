// Service Worker Afroboost V124 — ES5 compatible pour tous les mobiles
// IMPORTANT: Changer CACHE_NAME force le reload sur TOUS les appareils
// V124: Réécriture complète en ES5 (pas de const/let/arrow/optional chaining)
// pour compatibilité maximale avec les anciens navigateurs mobiles

var CACHE_NAME = 'afroboost-v129';

// V128: Pre-cache résilient — l'installation du SW ne doit JAMAIS échouer
// Sinon l'ancien SW cassé (V120 avec syntaxe ES6) reste actif = écran noir
var PRECACHE_URLS = [
  '/',
  '/index.html',
  '/logo192.png',
  '/logo512.png',
  '/manifest.json'
];

// Installation — TOUJOURS réussir, même si le pre-cache échoue
self.addEventListener('install', function(event) {
  console.log('[SW] V128 install — resilient pre-cache');
  event.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      // V128: Cache chaque URL individuellement — si une échoue, les autres continuent
      var promises = PRECACHE_URLS.map(function(url) {
        return cache.add(url).catch(function(err) {
          console.warn('[SW] Pre-cache échoué pour ' + url + ':', err);
          // On continue quand même — ne PAS rejeter la Promise
        });
      });
      return Promise.all(promises);
    }).catch(function(err) {
      // V128: Même si tout le cache échoue, on installe quand même le SW
      console.warn('[SW] Cache open échoué, installation continue:', err);
    }).then(function() {
      return self.skipWaiting();
    })
  );
});

// Activation — supprime TOUS les anciens caches + prend le contrôle immédiat
self.addEventListener('activate', function(event) {
  console.log('[SW] V128 activate — nuclear purge + claim');
  event.waitUntil(
    caches.keys().then(function(cacheNames) {
      return Promise.all(
        cacheNames
          .filter(function(name) { return name !== CACHE_NAME; })
          .map(function(name) {
            console.log('[SW] Suppression ancien cache:', name);
            return caches.delete(name);
          })
      );
    }).then(function() {
      return clients.claim();
    })
  );
});

// Fetch — network-first pour HTML, cache-first pour static assets
self.addEventListener('fetch', function(event) {
  var url = new URL(event.request.url);

  // API calls — toujours réseau
  if (url.pathname.startsWith('/api/')) return;

  // HTML pages / navigation — network-first avec fallback cache
  var acceptHeader = event.request.headers.get('accept') || '';
  if (event.request.mode === 'navigate' || acceptHeader.indexOf('text/html') !== -1) {
    event.respondWith(
      fetch(event.request).then(function(response) {
        if (response.ok) {
          var clone = response.clone();
          caches.open(CACHE_NAME).then(function(cache) { cache.put(event.request, clone); });
        }
        return response;
      }).catch(function() {
        return caches.match(event.request).then(function(cached) {
          return cached || caches.match('/index.html');
        });
      })
    );
    return;
  }

  // Static assets (JS/CSS avec hash) — cache-first
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then(function(cached) {
        if (cached) return cached;
        return fetch(event.request).then(function(response) {
          if (response.ok) {
            var clone = response.clone();
            caches.open(CACHE_NAME).then(function(cache) { cache.put(event.request, clone); });
          }
          return response;
        });
      })
    );
    return;
  }

  // Autres ressources — network-first avec cache
  event.respondWith(
    fetch(event.request).then(function(response) {
      if (response.ok) {
        var clone = response.clone();
        caches.open(CACHE_NAME).then(function(cache) { cache.put(event.request, clone); });
      }
      return response;
    }).catch(function() {
      return caches.match(event.request);
    })
  );
});

// Compteur de notifications non lues pour badge PWA
var unreadCount = 0;

// Reception des notifications push
self.addEventListener('push', function(event) {
  console.log('[SW] Notification push recue');

  var data = {
    title: 'Afroboost',
    body: 'Nouveau message de votre coach',
    icon: '/logo192.png',
    badge: '/logo192.png',
    data: { url: '/' }
  };

  if (event.data) {
    try {
      var payload = event.data.json();
      data = {
        title: payload.title || 'Afroboost',
        body: payload.body || payload.message || 'Nouveau message de votre coach',
        icon: payload.icon || '/logo192.png',
        badge: payload.badge || '/logo192.png',
        data: payload.data || { url: '/' }
      };
    } catch (e) {
      var text = event.data.text();
      if (text) data.body = text;
    }
  }

  var options = {
    body: data.body,
    icon: data.icon,
    badge: data.badge,
    vibrate: [200, 100, 200],
    tag: (data.data && data.data.type) ? data.data.type : 'afroboost-chat-sync',
    renotify: true,
    requireInteraction: false,
    silent: false,
    data: data.data
  };

  if ('actions' in Notification.prototype) {
    options.actions = [];
  }

  unreadCount++;
  event.waitUntil(
    Promise.all([
      self.registration.showNotification(data.title, options),
      navigator.setAppBadge ? navigator.setAppBadge(unreadCount).catch(function() {}) : Promise.resolve()
    ])
  );
});

// Clic sur la notification
self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  unreadCount = Math.max(0, unreadCount - 1);
  if (navigator.clearAppBadge && unreadCount === 0) {
    navigator.clearAppBadge().catch(function() {});
  } else if (navigator.setAppBadge && unreadCount > 0) {
    navigator.setAppBadge(unreadCount).catch(function() {});
  }

  var notifData = event.notification.data || {};
  var urlToOpen = notifData.url || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then(function(clientList) {
        for (var i = 0; i < clientList.length; i++) {
          var client = clientList[i];
          if (client.url.indexOf(self.location.origin) !== -1 && 'focus' in client) {
            return client.focus();
          }
        }
        if (clients.openWindow) return clients.openWindow(urlToOpen);
      })
  );
});

// Fermeture notification
self.addEventListener('notificationclose', function(event) {
  console.log('[SW] Notification fermee');
});

// Message du client
self.addEventListener('message', function(event) {
  console.log('[SW] Message recu:', event.data);
  if (event.data && event.data.type === 'CLEAR_BADGE') {
    unreadCount = 0;
    if (navigator.clearAppBadge) navigator.clearAppBadge().catch(function() {});
    return;
  }
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
