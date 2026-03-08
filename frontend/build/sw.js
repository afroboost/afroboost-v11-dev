// Service Worker pour les notifications push Afroboost
// Ce fichier doit etre a la racine du domaine (public/)

const CACHE_NAME = 'afroboost-v1';

// Installation du Service Worker
self.addEventListener('install', (event) => {
  console.log('[SW] Service Worker installe');
  self.skipWaiting();
});

// Activation
self.addEventListener('activate', (event) => {
  console.log('[SW] Service Worker active');
  event.waitUntil(clients.claim());
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
      // Si pas JSON, utiliser le texte brut
      const text = event.data.text();
      if (text) {
        data.body = text;
      }
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
  
  // Android: priority high pour reveiller l'ecran
  if ('actions' in Notification.prototype) {
    options.actions = [];
  }
  
  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

// Clic sur la notification - Ouvre/focus l'app
self.addEventListener('notificationclick', (event) => {
  console.log('[SW] Clic sur notification');
  
  event.notification.close();
  
  const urlToOpen = event.notification.data?.url || '/';
  
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        // Si une fenetre est deja ouverte, la focus
        for (const client of clientList) {
          if (client.url.includes(self.location.origin) && 'focus' in client) {
            return client.focus();
          }
        }
        // Sinon, ouvrir une nouvelle fenetre
        if (clients.openWindow) {
          return clients.openWindow(urlToOpen);
        }
      })
  );
});

// Fermeture de la notification
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
