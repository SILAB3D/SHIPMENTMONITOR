/* Service worker de la PWA.
 *
 * Hace dos cosas:
 *   1) Cascarón offline: el panel abre aunque no haya cobertura. Los datos
 *      (datos.json) siempre van a red, para no enseñar envíos rancios.
 *   2) Avisos push: recibe el mensaje que empuja GitHub Actions y lo enseña en
 *      la pantalla del móvil, con la app cerrada. Es el motivo de que no haga
 *      falta ni Telegram ni email.
 */
<<<<<<< HEAD
const CACHE = 'shipmentmonitor-v7';
=======
const CACHE = 'shipmentmonitor-v10';
>>>>>>> ad579244a2963aaa33e3acb940fb2b8b9b484637
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

/* Solo se toca lo de casa. Antes esto se metía en TODAS las peticiones y, si
   una fallaba, devolvía index.html con `ok: true`; el panel llamaba a la API de
   GitHub, recibía una página HTML donde esperaba JSON y el error que salía
   —«Unexpected token '<'»— no se parecía en nada a «no hay cobertura». Ahora lo
   de fuera (api.github.com, el datos.json del repositorio) pasa de largo, y el
   cascarón cacheado solo sustituye a una navegación. */
self.addEventListener('fetch', e => {
  const pet = e.request;
  if (pet.method !== 'GET') return;
  const url = new URL(pet.url);
  if (url.origin !== self.location.origin) return;                 // nada de fuera
  if (url.pathname.endsWith('/datos.json')) return;                // siempre fresco
  if (url.pathname.endsWith('/disparo.json')) return;
  e.respondWith(
    fetch(pet).catch(() => caches.match(pet).then(
      r => r || (pet.mode === 'navigate' ? caches.match('index.html') : Response.error())
    ))
  );
});

/* ─────────────── recordatorio de que hay que arrancar ───────────────
 *
 * GitHub dejó de servir los disparos programados, así que la jornada la
 * arranca el propio panel al abrirlo. Queda el hueco de las mañanas en que
 * nadie lo abre: para eso está esto. Si el navegador nos despierta (solo lo
 * hace con la app instalada, y cuando le parece) miramos cuándo fue la última
 * comprobación y, si en plena jornada lleva horas parada, avisamos.
 *
 * Es un refuerzo, no una garantía: `periodicsync` es «cuando el navegador
 * quiera». Lo que de verdad arranca el día es abrir la app.
 */
const DATOS_REPO = 'https://raw.githubusercontent.com/SILAB3D/SHIPMENTMONITOR/main/'
                 + 'monitor-envios-github/monitor-envios-nube/docs/datos.json';

async function avisarSiEstaParado(){
  const ahora = new Date(new Date().toLocaleString('en-US', {timeZone: 'Europe/Madrid'}));
  const dia = ahora.getDay(), reloj = ahora.getHours() * 60 + ahora.getMinutes();
  if (dia < 1 || dia > 5 || reloj < 510 || reloj > 1080) return;   // fuera de jornada

  let ts = null;
  try {
    const r = await fetch(DATOS_REPO + '?t=' + Date.now(), {cache: 'no-store'});
    if (r.ok) ts = (await r.json()).ts;
  } catch (_) { return; }
  if (!ts) return;

  const minutos = Math.round((Date.now() - new Date(ts)) / 60000);
  if (minutos <= 90) return;                                        // va al día

  const horas = Math.round(minutos / 60);
  await self.registration.showNotification('El monitor está parado', {
    body: `Lleva ${horas} h sin comprobar el portal. Abre ShipmentMonitor y se pone en marcha solo.`,
    icon: 'icono-notificacion-192.png', badge: 'icono-badge-96.png',
    tag: 'parado', renotify: false,
    data: {url: './'},
    actions: [{action: 'abrir', title: 'Abrir y arrancar'}],
  });
}

self.addEventListener('periodicsync', e => {
  if (e.tag === 'vigilancia') e.waitUntil(avisarSiEstaParado());
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
