// =================================================================
// Service Worker Afroboost V141 — ES5 PUR (100% compatible Android)
// Pas de const, let, arrow functions, template literals, ou ES6+
// =================================================================
// RÈGLE D'OR : L'installation du SW ne doit JAMAIS échouer.
// Si le pre-cache rate, on continue. Si les notifs crashent, on continue.
// =================================================================

var CACHE_NAME = 'afroboost-v161';
var SW_VERSION = 161;

var PRECACHE_URLS = [
  '/',
  '/index.html',
  '/logo192.png',
  '/logo512.png',
  '/logo192-maskable.png',
  '/logo512-maskable.png'
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

  // Icônes PWA → NE PAS intercepter — Google Play Services (WebAPK) doit les lire directement
  if (url.pathname.indexOf('/logo') === 0 && url.pathname.indexOf('.png') !== -1) {
    return;
  }

  // favicon → passthrough
  if (url.pathname === '/favicon.ico') {
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
// NOTIFICATIONS PUSH — V161 : Réactivées avec protection try/catch
// -----------------------------------------------------------------
self.addEventListener('push', function(event) {
  try {
    var data = {};
    if (event.data) {
      try {
        data = event.data.json();
      } catch (e) {
        data = { title: 'Afroboost', body: event.data.text() || 'Nouveau message' };
      }
    }

    var title = data.title || 'Afroboost';
    var options = {
      body: data.body || 'Vous avez une nouvelle notification',
      icon: '/logo192.png',
      badge: '/logo192.png',
      vibrate: [200, 100, 200],
      tag: data.tag || 'afroboost-push',
      renotify: true,
      data: {
        url: data.url || '/',
        session_id: data.session_id || null
      }
    };

    event.waitUntil(
      self.registration.showNotification(title, options)
        .catch(function() {
          // Silencieux si showNotification échoue
        })
    );
  } catch (e) {
    // Protection totale — ne jamais crasher le SW
  }
});

self.addEventListener('notificationclick', function(event) {
  try {
    event.notification.close();

    var targetUrl = '/';
    if (event.notification.data && event.notification.data.url) {
      targetUrl = event.notification.data.url;
    }

    event.waitUntil(
      self.clients.matchAll({ type: 'window', includeUncontrolled: true })
        .then(function(clientList) {
          // Si une fenêtre Afroboost est déjà ouverte, la focus
          for (var i = 0; i < clientList.length; i++) {
            var client = clientList[i];
            if (client.url.indexOf('afroboost.com') !== -1 || client.url.indexOf('localhost') !== -1) {
              client.focus();
              client.postMessage({
                type: 'NOTIFICATION_CLICK',
                url: targetUrl,
                session_id: event.notification.data ? event.notification.data.session_id : null
              });
              return;
            }
          }
          // Sinon ouvrir une nouvelle fenêtre
          return self.clients.openWindow(targetUrl);
        })
        .catch(function() {
          // Silencieux
        })
    );
  } catch (e) {
    // Protection totale
  }
});

// -----------------------------------------------------------------
// MESSAGE — Écoute les commandes du client (SKIP_WAITING)
// -----------------------------------------------------------------
self.addEventListener('message', function(event) {
  try {
    if (event.data && event.data.type === 'SKIP_WAITING') {
      self.skipWaiting();
    }
  } catch (e) {
    // Silencieux
  }
});
