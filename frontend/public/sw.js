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
var CACHE_NAME = 'afroboost-v467'; // SECURITY-S1 : le front change (App — /auth/me renouvelle le jeton meme quand le modal ne monte pas ; CoachDashboard — l'effet des notifications ne se remonte plus a chaque ecriture de chatSessions) — sans ce bump, un navigateur en repli de cache garderait le bundle ou le jeton meurt tous les 7 jours et ou le minuteur de 10 s n'atteint jamais son echeance // // SECURITY-S0 : le front change (CoachLoginModal — l'entree par le cookie stocke enfin le JWT) — sans ce bump, un navigateur en repli de cache garderait le bundle qui ouvre le tableau de bord avec une session NON SIGNEE, laissant la moitie des sections en 403 et le kill-switch des drapeaux inaccessible // // CHAT-LOOP3 : le front change (CRMSection — gardes sur les sondages 30 s et 15 s ; MessagesWhatsApp — garde sur /private/nonlus ; CoachDashboard — l'appel immediat des notifications est garde) — sans ce bump, un navigateur en repli de cache garderait le bundle qui emet encore les 4 requetes toutes les 30 s onglet cache, et le risque de boucle loadConversations -> setChatSessions -> remontage resterait ouvert // // CHAT-LOOP2 : le front change (CoachDashboard — garde de visibilite sur les 5 derniers sondages, dont /private/nonlus a 5 s) — sans ce bump, un navigateur en repli de cache garderait precisement le bundle qui emet les 17 280 requetes/jour qu'on vient de supprimer // // CHAT-LOOP1 : le front change (CoachDashboard — suppression de la boucle qui emettait une requete par conversation toutes les 5 s ; GroupChatModule — garde de visibilite) — sans ce bump, un navigateur en repli de cache garderait precisement le bundle qui produit les 126 660 requetes/jour qu'on vient de supprimer // // P1.2-UXFINAL : le front change (OnboardingTunnel — intro partenaire + « Lire plus » + code diagnostic ; ChatWidget — ecran de fin partenaire) — sans ce bump, un telephone dont la navigation retombe sur le cache garderait l'ancien bundle : un partenaire continuerait a lire « On te confirme ton cours d'essai sur WhatsApp », et une coupure resterait sans code diagnostic, donc sans preuve // // N2 : le front change (SubscriberSpace — lieu, itineraire, marqueur AUJOURD'HUI, et la raison du refus d'annulation a la place d'un bouton gris muet) — sans ce bump, un participant garderait un ecran qui ne dit toujours pas OU venir // ESSAI-7 : le front change (App — redirection vers /espace/<CODE> apres l'octroi ; SubscriberSpace — la reservation passe en tete) — sans ce bump, un navigateur garderait l'ancien bundle : le code repartirait dans la reponse du serveur SANS que personne ne soit emmene le choisir, et `session_booked` ne serait jamais emis // AUTO-PRESENCE : le front change (ChatWidget — liste des attendus + bouton Absent) — sans ce bump, le telephone du coach garderait un Bilan sans aucun moyen de declarer une absence, alors que l'automate compterait tout le monde present // // FUNNEL ESSAI etape 1 : App.js change (4 evenements de mesure) — sans ce bump, un navigateur garderait l'ancien bundle et n'emettrait AUCUN evenement, la baseline serait vide sans qu'on le sache // // LOT R : le front change (SubscriberSpace) — sans ce bump, un abonne garderait un espace qui ignore le bouton de recharge // TERRAIN EVENT : le front change (ChatWidget, QRScanner) — sans ce bump, le telephone du coach garderait l'ancien bundle a la porte de l'event : pas d'alerte essai, pas de casque au scan, pas de signature // LOT 3b : le front change (OfferWizard, CoachDashboard, App) — sans ce bump, un navigateur garderait l'ancien bundle, qui n'envoie PAS les dates d'occurrence et ne verrait donc jamais son tarif membre // LOT 2.1 : la case adhesion est desactivee sur une offre gratuite (OfferWizard, CoachDashboard) // LOT 2 FIX : CoachDashboard change (startEditOffer relit les deux cases) // LOT 2 : le front change (OfferWizard, FicheContact, Contacts) // LOT 1 : le front change (ChatWidget, App, BookingPanel)
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
      vibrate: [200, 100, 200],
      tag: data.tag || 'afroboost-push',
      renotify: true,
      // V274: message riche cliquable (façon WhatsApp/Instagram) — deux actions
      requireInteraction: false,
      actions: [
        { action: 'open', title: 'Voir' },
        { action: 'close', title: 'Fermer' }
      ],
      data: {
        // V274: url par defaut ouvre le chat ; le backend peut la surcharger.
        url: data.url || '/?openChat=true',
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
