// =================================================================
// Service Worker Afroboost V141 — ES5 PUR (100% compatible Android)
// Pas de const, let, arrow functions, template literals, ou ES6+
// =================================================================
// RÈGLE D'OR : L'installation du SW ne doit JAMAIS échouer.
// Si le pre-cache rate, on continue. Si les notifs crashent, on continue.
// =================================================================

// V347 : le cache etait reste bloque sur v342 pendant V343, V344, V345 et V346 —
// les appareils deja installes (mobile en particulier) continuaient donc de servir
// un ancien bundle malgre quatre deploiements reussis. On le bumpe pour forcer
// tous les clients a recharger. A BUMPER A CHAQUE VERSION TOUCHANT LE FRONT.
// V359 : le cache etait reste sur v347 pendant V348 a V358 — onze versions.
// L'index.html en cache reference l'ANCIEN hash de bundle, et comme /static/ est
// servi en cache-first, l'ancien JS restait epingle : c'est ce qui explique que le
// mobile ne pouvait ni supprimer un media (V356/V357) ni garder un vocal au
// rechargement (V358), alors que le correctif etait en ligne depuis longtemps.
// Bumper CACHE_NAME purge l'ancien cache a l'activation et force tous les appareils
// a recharger. A BUMPER A CHAQUE VERSION TOUCHANT LE FRONT.
var CACHE_NAME = 'afroboost-v665'; // V659-V661 : installation PWA, notifications abonne, destination du push
                                   // -> sans ce bump, un appareil deja installe garderait l'ancien
                                   // bundle et continuerait d'envoyer l'instant du clic comme date.
var SW_VERSION = 272;

var PRECACHE_URLS = [
  '/',
  '/index.html',
  '/logo192.png',
  '/logo512.png',
  '/logo192-maskable.png',
  '/logo512-maskable.png',
  '/notification-badge-96.png'
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

  // V205: Ne pas cacher les requêtes POST/PUT/DELETE (Cache API ne supporte que GET)
  if (event.request.method !== 'GET') {
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

    // -----------------------------------------------------------------
    // PUSH-UI — LE SERVEUR PEUT ENFIN DECIDER DE L'APPARENCE
    // -----------------------------------------------------------------
    // Jusqu'ici TOUT etait code en dur ici. server.py le disait deja mot pour
    // mot : « Le Service Worker code ses propres valeurs en dur et ignore
    // celles-ci ». Consequence concrete : un rappel de cours ne pouvait pas
    // proposer « Reserver maintenant » plutot que « Voir », ni se distinguer
    // d'un message de chat sur l'ecran verrouille.
    //
    // Chaque option devient donc SURCHARGEABLE PAR LE PAYLOAD, avec la valeur
    // d'aujourd'hui pour defaut : un push qui n'envoie rien de plus est rendu
    // EXACTEMENT comme avant ce lot. Rien n'est retire, tout devient optionnel.
    //
    // Les valeurs recues sont VERIFIEES avant usage : un `actions` mal forme
    // ferait echouer showNotification() en entier, et la notification ne
    // s'afficherait pas du tout. On retombe alors sur les actions par defaut.
    var actions = [
      { action: 'open', title: 'Voir' },
      { action: 'close', title: 'Fermer' }
    ];
    if (Object.prototype.toString.call(data.actions) === '[object Array]') {
      var propres = [];
      for (var iAct = 0; iAct < data.actions.length && propres.length < 2; iAct++) {
        var act = data.actions[iAct];
        if (act && typeof act.action === 'string' && act.action
            && typeof act.title === 'string' && act.title) {
          propres.push({ action: act.action, title: String(act.title).slice(0, 40) });
        }
      }
      if (propres.length) { actions = propres; }
    }
    var vibration = [200, 100, 200];
    if (Object.prototype.toString.call(data.vibrate) === '[object Array]'
        && data.vibrate.length) {
      var propreVib = [];
      for (var iVib = 0; iVib < data.vibrate.length && propreVib.length < 8; iVib++) {
        var ms = data.vibrate[iVib];
        if (typeof ms === 'number' && isFinite(ms) && ms >= 0 && ms <= 5000) {
          propreVib.push(ms);
        }
      }
      if (propreVib.length) { vibration = propreVib; }
    }
    var options = {
      body: data.body || 'Vous avez une nouvelle notification',
      icon: '/logo192.png',
      // V445 — LE CARRE BLANC DANS LA BARRE DE STATUT ANDROID.
      //
      // `badge` est la PETITE icone (barre de statut, coin de la notification).
      // Android ne l'affiche JAMAIS en couleur : il n'en garde que le canal
      // ALPHA et repeint chaque pixel non transparent avec la teinte du systeme
      // — blanc sur le volet sombre de Samsung.
      //
      // Or `/logo192.png` est le logo couleur sur fond noir OPAQUE : mesure du
      // 16/08/2026, 36 864 pixels sur 36 864 ont alpha = 255, aucun transparent.
      // Sa silhouette est donc un carre plein, et Android affichait exactement
      // ca : un carre blanc. Le fichier n'etait pas casse — il etait juste du
      // mauvais TYPE pour cet emplacement.
      //
      // `/notification-badge-96.png` est la silhouette du meme « A », EXTRAITE
      // de logo512.png (l'asset officiel, aucun redessin) : blanc sur fond
      // transparent, masque plein pour rester lisible a 24 dp. Le test
      // tests/test_v445_icone_notification.py la regenere depuis le logo et
      // verifie qu'elle correspond au fichier livre, octet pour octet.
      //
      // `icon` reste le logo COULEUR : c'est la grande icone, elle, rendue
      // telle quelle. Les deux emplacements n'ont pas les memes contraintes.
      badge: '/notification-badge-96.png',
      vibrate: vibration,
      // Le tag REGROUPE : deux push de MEME tag s'ecrasent au lieu de s'empiler.
      // Le defaut commun est conserve mot pour mot ; le serveur peut desormais
      // en poser un par cours, pour qu'un rappel n'ecrase jamais un message.
      tag: data.tag || 'afroboost-push',
      // `renotify` refait sonner/vibrer quand un push REMPLACE le precedent.
      // Vrai par defaut, comme avant ; seul un `false` explicite le desactive.
      renotify: data.renotify !== false,
      // `silent: false` EXPLICITE. `silent: true` couperait son ET vibration.
      // A l'inverse, aucune option web ne FORCE le son sur Android : c'est le
      // canal de notification du systeme qui tranche, jamais la page. On peut
      // demander a ne pas etre silencieux ; on ne peut pas imposer le volume.
      silent: false,
      // V274: message riche cliquable (façon WhatsApp/Instagram) — deux actions
      requireInteraction: data.requireInteraction === true,
      actions: actions,
      data: {
        // V274: url par defaut ouvre le chat ; le backend peut la surcharger.
        url: data.url || '/?openChat=true',
        session_id: data.session_id || null
      }
    };
    // `image` (grande banniere) n'existe pas partout : Chrome/Android l'affiche,
    // Firefox et iOS l'ignorent SANS erreur. On ne la pose que si le serveur en
    // envoie une — une cle inconnue reste sans effet, jamais un echec de rendu.
    if (typeof data.image === 'string' && data.image) {
      options.image = data.image;
    }

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

// -----------------------------------------------------------------
// P1-a — LA ROTATION D'ENDPOINT SE DECLARE ELLE-MEME
// -----------------------------------------------------------------
// FCM fait tourner l'endpoint d'un navigateur en permanence. Sans ce
// gestionnaire, Afroboost apprenait le nouvel endpoint SEULEMENT au prochain
// chargement du dashboard : entre les deux, tout push partait vers l'ancien,
// que FCM accepte encore silencieusement. Mesure du 18/08/2026 : 196 endpoints
// enregistres pour un ou deux appareils reels, dont 185 encore actifs.
//
// `pushsubscriptionchange` est le mecanisme PREVU PAR LA SPECIFICATION pour ce
// cas precis, et il etait absent. Le Service Worker est le seul a connaitre le
// couple (ancien endpoint, nouveau endpoint) : c'est donc lui qui le declare.
// Le serveur ne devine rien.
//
// `oldSubscription` n'est pas fourni par tous les navigateurs : on l'envoie
// quand il existe, et son absence n'empeche jamais l'enregistrement du nouveau.
// Si `newSubscription` manque, on se reabonne avec la MEME cle applicative que
// l'ancienne — aucune permission n'est redemandee, la spec l'interdit ici.
self.addEventListener('pushsubscriptionchange', function(event) {
  event.waitUntil(
    (function () {
      var ancien = event.oldSubscription ? event.oldSubscription.endpoint : null;
      var pNouveau = event.newSubscription
        ? Promise.resolve(event.newSubscription)
        : self.registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: event.oldSubscription
              && event.oldSubscription.options
              && event.oldSubscription.options.applicationServerKey
          });
      return pNouveau.then(function (nouveau) {
        if (!nouveau) return;
        // L'identifiant du proprietaire est celui pose au dernier
        // enregistrement : le Service Worker n'a pas de session.
        return caches.open('afroboost-push-owner').then(function (c) {
          return c.match('owner').then(function (r) {
            return (r ? r.text() : Promise.resolve('')).then(function (pid) {
              if (!pid) return;
              return fetch('/api/push/subscribe', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  participant_id: pid,
                  subscription: nouveau.toJSON(),
                  previous_endpoint: ancien
                })
              });
            });
          });
        });
      });
    })().catch(function () { /* jamais casser le Service Worker */ })
  );
});

self.addEventListener('notificationclick', function(event) {
  try {
    event.notification.close();

    // V274: bouton "Fermer" — on ferme simplement, sans ouvrir le site.
    if (event.action === 'close') {
      return;
    }

    var targetUrl = '/?openChat=true';
    if (event.notification.data && event.notification.data.url) {
      targetUrl = event.notification.data.url;
    }

    // ---------------------------------------------------------------
    // PUSH-CLIC — LA DESTINATION EST ABSOLUE, LE CHEMIN NE L'EST PAS
    // ---------------------------------------------------------------
    // Le serveur envoie une url ABSOLUE (`rv2_lien_espace` rend
    // « https://afroboost.com/espace/<CODE> »), alors que la notification du
    // chat en envoie une RELATIVE (« /?openChat=true »). Les deux doivent se
    // comparer et se suivre de la meme facon : on les ramene donc toutes a une
    // url absolue, une bonne fois, ici.
    var cible = targetUrl;
    var cibleChemin = targetUrl;
    try {
      var u = new URL(targetUrl, self.location.origin);
      cible = u.href;
      cibleChemin = u.pathname + u.search;
    } catch (e) { /* url illisible : on garde la chaine telle quelle */ }

    // Deux notifications ont DEJA leur chemin, eprouve, et il ne passe pas par
    // une navigation : la prospection (READ-P2 evite expressement de recharger
    // le tableau de bord) et l'ouverture du chat. Pour toutes les AUTRES — un
    // rappel de cours, par exemple — la notification vise une PAGE : il faut y
    // aller, sinon on ramene juste l'onglet au premier plan.
    var parMessage = (cible.indexOf('prospection=1') !== -1
                      || cible.indexOf('openChat') !== -1);

    event.waitUntil(
      self.clients.matchAll({ type: 'window', includeUncontrolled: true })
        .then(function(clientList) {
          // Si une fenêtre Afroboost est déjà ouverte, la focus
          for (var i = 0; i < clientList.length; i++) {
            var client = clientList[i];
            if (client.url.indexOf('afroboost.com') !== -1 || client.url.indexOf('localhost') !== -1) {
              var message = {
                type: 'NOTIFICATION_CLICK',
                url: cible,
                session_id: event.notification.data ? event.notification.data.session_id : null
              };
              // `navigate()` emmene la fenetre DEJA OUVERTE sur la page visee,
              // sans dependre d'un gestionnaire cote React. Il n'existe pas
              // partout et echoue sur un client non controle : on retombe alors
              // sur le message, qui est le chemin d'hier.
              if (!parMessage && client.url !== cible && typeof client.navigate === 'function') {
                return client.navigate(cible)
                  .then(function (c) { return (c || client).focus(); })
                  .catch(function () {
                    client.focus();
                    client.postMessage(message);
                  });
              }
              client.focus();
              client.postMessage(message);
              return;
            }
          }
          // Sinon ouvrir une nouvelle fenêtre
          return self.clients.openWindow(cible);
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
