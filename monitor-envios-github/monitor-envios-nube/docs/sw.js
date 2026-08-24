/* Service worker: cascarón offline. Los datos (datos.json) siempre van a red. */
const CACHE = 'monitor-envios-v2';
const BASICOS = [
  './', 'index.html', 'icono.svg', 'manifest.webmanifest',
  'vendor/react.js', 'vendor/react-dom.js', 'vendor/babel.js',
  'vendor/fuentes/inter-latin-wght-normal.woff2',
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(BASICOS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  if (new URL(e.request.url).pathname.endsWith('/datos.json')) return;   // siempre fresco
  e.respondWith(
    fetch(e.request).catch(() => caches.match(e.request).then(r => r || caches.match('index.html')))
  );
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(clients.matchAll({type:'window', includeUncontrolled:true}).then(lista => {
    const abierta = lista.find(c => 'focus' in c);
    return abierta ? abierta.focus() : clients.openWindow('./');
  }));
});
