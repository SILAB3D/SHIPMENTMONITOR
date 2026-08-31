/* Service worker de la PWA.
 *
 * Hace dos cosas:
 *   1) Cascarón offline: el panel abre aunque no haya cobertura. Los datos
 *      (datos.json) siempre van a red, para no enseñar envíos rancios.
 *   2) Avisos push: recibe el mensaje que empuja GitHub Actions y lo enseña en
 *      la pantalla del móvil, con la app cerrada. Es el motivo de que no haga
 *      falta ni Telegram ni email.
 */
const CACHE = 'shipmentmonitor-v7';
const BASICOS = [
  './', 'index.html', 'icono.svg', 'icono-192.png', 'icono-512.png',
  'icono-notificacion-192.png', 'icono-badge-96.png',
  'manifest.webmanifest', 'push-config.js',
  'vendor/react.js', 'vendor/react-dom.js', 'vendor/babel.js',
  'vendor/fuentes/inter-latin-wght-normal.woff2',
];

self.addEventListener('install', e => {
  // addAll es todo-o-nada; si un fichero opcional falla no queremos quedarnos
  // sin service worker, así que los pedimos de uno en uno.
  e.waitUntil(
    caches.open(CACHE)
      .then(c => Promise.all(BASICOS.map(u => c.add(u).catch(() => {}))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  if (new URL(e.request.url).pathname.endsWith('/datos.json')) return;   // siempre fresco
  e.respondWith(
    fetch(e.request).catch(() => caches.match(e.request).then(r => r || caches.match('index.html')))
  );
});

/* ─────────────────────────── avisos push ─────────────────────────── */

self.addEventListener('push', e => {
  // El navegador exige enseñar SIEMPRE una notificación al recibir un push: si
  // no lo hacemos, acaba revocando el permiso. Por eso hay valores de reserva.
  let m = {};
  try { m = e.data ? e.data.json() : {}; } catch (_) { m = {titulo: e.data && e.data.text()}; }

  const titulo = m.titulo || 'Novedad en tus envíos';
  const opciones = {
    body: m.cuerpo || 'Abre el panel para ver el detalle.',
    // Sin fondo: el icono cuadrado naranja quedaba como un pegote sobre la
    // sombra de notificación. El badge (el iconito de la barra de estado)
    // Android lo reduce a silueta, así que va en blanco y transparente.
    icon: 'icono-notificacion-192.png',
    badge: 'icono-badge-96.png',
    tag: m.etiqueta || 'shipmentmonitor',
    renotify: true,
    timestamp: Date.now(),
    data: {url: m.url || './', envio_id: m.envio_id || null},
    actions: [{action: 'abrir', title: 'Ver el panel'}],
  };
  e.waitUntil(self.registration.showNotification(titulo, opciones));
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const destino = new URL((e.notification.data && e.notification.data.url) || './', self.location.href).href;
  e.waitUntil(
    clients.matchAll({type: 'window', includeUncontrolled: true}).then(lista => {
      const abierta = lista.find(c => c.url.startsWith(self.registration.scope) && 'focus' in c);
      if (abierta) { abierta.postMessage({tipo: 'aviso-abierto'}); return abierta.focus(); }
      return clients.openWindow(destino);
    })
  );
});

/* El servicio de push puede rotar la suscripción por su cuenta. Cuando pasa, la
   vieja deja de funcionar: nos resuscribimos y avisamos al panel para que te
   pida pegar la nueva en el Secret. */
self.addEventListener('pushsubscriptionchange', e => {
  e.waitUntil((async () => {
    const anterior = e.oldSubscription || await self.registration.pushManager.getSubscription();
    const clave = (anterior && anterior.options && anterior.options.applicationServerKey) || null;
    if (!clave) return;
    const nueva = await self.registration.pushManager.subscribe({
      userVisibleOnly: true, applicationServerKey: clave,
    });
    const ventanas = await clients.matchAll({type: 'window', includeUncontrolled: true});
    ventanas.forEach(c => c.postMessage({tipo: 'suscripcion-renovada', suscripcion: nueva.toJSON()}));
  })());
});
