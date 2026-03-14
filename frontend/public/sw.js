// =================================================================
// Service Worker Afroboost V138 — ES5 PUR (100% compatible Android)
// Pas de const, let, arrow functions, template literals, ou ES6+
// =================================================================
// RÈGLE D'OR : L'installation du SW ne doit JAMAIS échouer.
// Si le pre-cache rate, on continue. Si les notifs crashent, on continue.
// =================================================================

var CACHE_NAME = 'afroboost-v139';
var SW_VERSION = 139;

var PRECACHE_URLS = [
  '/',
  '/index.html',
  '/logo192.png',
  '/logo512.png'
];

// -----------------------------------------------------------------
// INSTALL — Résilient : chaque URL est tentée seule, échec = ignoré
// -----------------------------------------------------------------
self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(function(cache) {
        var promises = [];
        for (var i = 0; i < PRECACHE_URLS.length; i++) {
          (function(url) {
            promises.push(
              fetch(url, { cache: 'no-store' })
                .then(function(resp) {
                  if (resp && resp.ok) {
                    return cache.put(url, resp);
                  }
                })
                .catch(function() {
                  // Échec silencieux — on continue
                })
            );
          })(PRECACHE_URLS[i]);
        }
        return Promise.all(promises);
      })
      .catch(function() {
        // Même si caches.open échoue, on installe quand même
      })
      .then(function() {
        return self.skipWaiting();
      })
  );
});

// -----------------------------------------------------------------
// ACTIVATE — Purge tous les anciens caches + prend le contrôle
// -----------------------------------------------------------------
self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys()
      .then(function(names) {
        var deletions = [];
        for (var i = 0; i < names.length; i++) {
          if (names[i] !== CACHE_NAME) {
            deletions.push(caches.delete(names[i]));
          }
        }
        return Promise.all(deletions);
      })
      .then(function() {
        return self.clients.claim();
      })
      .then(function() {
        return self.clients.matchAll({ type: 'window' });
      })
      .then(function(allClients) {
        if (allClients && allClients.length > 0) {
          for (var i = 0; i < allClients.length; i++) {
            try {
              allClients[i].postMessage({ type: 'SW_UPDATED', version: CACHE_NAME });
            } catch (e) {
              // Silencieux
            }
          }
        }
      })
      .catch(function() {
        // Erreur d'activation non-bloquante
      })
  );
});

// -----------------------------------------------------------------
// FETCH — Network-first pour HTML et manifest, cache-first pour static
// -----------------------------------------------------------------
self.addEventListener('fetch', function(event) {
  var url;
  try {
    url = new URL(event.request.url);
  } catch (e) {
    return;
  }

  // API → toujours réseau, pas de cache
  if (url.pathname.indexOf('/api/') === 0) {
    return;
  }

  // manifest.json → NE PAS intercepter — Chrome doit le lire directement du serveur
  if (url.pathname === '/manifest.json') {
    return;
  }

  // Navigation / HTML → network-first
  var accept = '';
  try { accept = event.request.headers.get('accept') || ''; } catch (e) {}
  if (event.request.mode === 'navigate' || accept.indexOf('text/html') !== -1) {
    event.respondWith(
      fetch(event.request)
        .then(function(response) {
          if (response && response.ok) {
            var clone = response.clone();
            caches.open(CACHE_NAME).then(function(cache) {
              cache.put(event.request, clone);
            });
          }
          return response;
        })
        .catch(function() {
          return caches.match(event.request).then(function(cached) {
            return cached || caches.match('/index.html');
          });
        })
    );
    return;
  }

  // Static assets (/static/) → cache-first (fichiers hashés)
  if (url.pathname.indexOf('/static/') === 0) {
    event.respondWith(
      caches.match(event.request).then(function(cached) {
        if (cached) { return cached; }
        return fetch(event.request).then(function(response) {
          if (response && response.ok) {
            var clone = response.clone();
            caches.open(CACHE_NAME).then(function(cache) {
              cache.put(event.request, clone);
            });
          }
          return response;
        });
      })
    );
    return;
  }

  // Tout le reste → network-first avec fallback cache
  event.respondWith(
    fetch(event.request)
      .then(function(response) {
        if (response && response.ok) {
          var clone = response.clone();
          caches.open(CACHE_NAME).then(function(cache) {
            cache.put(event.request, clone);
          });
        }
        return response;
      })
      .catch(function() {
        return caches.match(event.request);
      })
  );
});

// -----------------------------------------------------------------
// NOTIFICATIONS — Isolées dans try/catch, ne bloquent JAMAIS le SW
// -----------------------------------------------------------------
var unreadCount = 0;

// Push
try {
  self.addEventListener('push', function(event) {
    var data = {
      title: 'Afroboost',
      body: 'Nouveau message',
      icon: '/logo192.png',
      badge: '/logo192.png',
      data: { url: '/' }
    };

    try {
      if (event.data) {
        var payload = event.data.json();
        data.title = payload.title || data.title;
        data.body = payload.body || payload.message || data.body;
        data.icon = payload.icon || data.icon;
        data.badge = payload.badge || data.badge;
        data.data = payload.data || data.data;
      }
    } catch (e) {
      try {
        var text = event.data.text();
        if (text) { data.body = text; }
      } catch (e2) {}
    }

    unreadCount = unreadCount + 1;

    event.waitUntil(
      self.registration.showNotification(data.title, {
        body: data.body,
        icon: data.icon,
        badge: data.badge,
        vibrate: [200, 100, 200],
        tag: 'afroboost-notif',
        renotify: true,
        data: data.data
      }).catch(function() {})
    );
  });
} catch (e) {
  // Push non supporté — silencieux
}

// Notification click
try {
  self.addEventListener('notificationclick', function(event) {
    try { event.notification.close(); } catch (e) {}
    unreadCount = Math.max(0, unreadCount - 1);

    var targetUrl = '/';
    try {
      if (event.notification.data && event.notification.data.url) {
        targetUrl = event.notification.data.url;
      }
    } catch (e) {}

    event.waitUntil(
      self.clients.matchAll({ type: 'window', includeUncontrolled: true })
        .then(function(clientList) {
          for (var i = 0; i < clientList.length; i++) {
            try {
              if (clientList[i].url.indexOf(self.location.origin) !== -1) {
                return clientList[i].focus();
              }
            } catch (e) {}
          }
          try {
            return self.clients.openWindow(targetUrl);
          } catch (e) {}
        })
        .catch(function() {})
    );
  });
} catch (e) {
  // Notification click non supporté — silencieux
}

// Notification close
try {
  self.addEventListener('notificationclose', function() {});
} catch (e) {}

// -----------------------------------------------------------------
// MESSAGE — Écoute les commandes du client (SKIP_WAITING, CLEAR_BADGE)
// -----------------------------------------------------------------
self.addEventListener('message', function(event) {
  try {
    if (event.data && event.data.type === 'SKIP_WAITING') {
      self.skipWaiting();
    }
    if (event.data && event.data.type === 'CLEAR_BADGE') {
      unreadCount = 0;
    }
  } catch (e) {
    // Silencieux
  }
});
