# Monitor de envíos — lo que queda por hacer a mano

**Actualizado el 25 de agosto de 2026.** Este documento sustituye al PDF
«Monitor de envíos - Guía de puesta en marcha» y a `guia/guia.html`, que se
escribieron antes de convertir la aplicación a avisos push.

Todo lo que se podía dejar hecho está hecho. Lo que queda son las cosas que solo
puedes hacer tú: pulsar botones en GitHub y en tu móvil. **Unos 20 minutos.**

---

## Primero: por qué no te aparecía el workflow

El paso 6 de la guía antigua no fallaba por tu culpa. **GitHub solo lee los
workflows que están en `.github/workflows/` en la raíz del repositorio.**

En tu repositorio `SILAB3D/SHIPMENTMONITOR` el proyecto no está en la raíz: está
metido dos carpetas hacia dentro, en
`monitor-envios-github/monitor-envios-nube/`. El fichero `monitor.yml` estaba,
por tanto, en
`monitor-envios-github/monitor-envios-nube/.github/workflows/monitor.yml`, una
ruta que GitHub ignora por completo. Por eso la pestaña **Actions** estaba vacía:
no había ningún workflow llamado «Monitor de envíos» que ejecutar.

**Ya está resuelto.** He creado `/.github/workflows/monitor.yml` (en la raíz), y
ese sí lo verá GitHub. Entra en la carpeta del proyecto por su cuenta, así que no
he tenido que mover nada de sitio.

Como el proyecto no está en la raíz, **GitHub Pages tampoco puede servirlo desde
la carpeta `/docs`** — esa opción solo mira la raíz. Por eso el workflow publica
ahora el panel él mismo, y en el paso 3 tendrás que poner el origen de Pages en
«GitHub Actions» en vez de «Deploy from a branch».

---

## Qué ha cambiado en la aplicación

Los avisos ya no pasan por Telegram ni por el correo: **van directos a tu móvil**.

- La PWA se suscribe al servicio de push del propio navegador (Google en
  Android/Chrome, Mozilla en Firefox, Apple en iPhone). Es gratis y no hay que
  registrarse en ningún sitio.
- GitHub Actions cifra el aviso y lo empuja a ese servicio, que lo entrega en tu
  teléfono **aunque la app esté cerrada**.
- El contenido del aviso va cifrado de punta a punta: ni Google ni Apple pueden
  leer qué envío es.
- Telegram y el correo siguen ahí como refuerzo opcional. Si no creas sus
  secrets, ni se intentan. Puedes olvidarte de ellos.
- Iconos PNG de verdad (192, 512 y una versión «maskable» para Android),
  `apple-touch-icon` y metadatos de iOS: al instalarla queda como una app normal.

---

## PASO 0 — Subir los cambios

He dejado todo modificado en tu carpeta pero **sin hacer commit**: eso lo
decides tú. Abre PowerShell y revisa antes de subir:

```powershell
cd "d:\Documentos - SSD\SCRIPTS\SHIPMENTMONITOR"
git status
git diff
```

Si te convence:

```powershell
git add -A
git commit -m "Avisos push al movil y workflow en la raiz del repositorio"
git push
```

> **Comprueba que el repositorio es PÚBLICO.** Settings → General → abajo del
> todo, «Danger Zone». Actions y Pages solo son gratis e ilimitados en
> repositorios públicos. Tus datos siguen siendo privados: se publican cifrados
> con `CLAVE_PANEL` y las credenciales viven en los Secrets.

Cuando termine el `push`, entra en la pestaña **Actions**: ya debería aparecer
«Monitor de envíos» en la columna de la izquierda.

---

## PASO 1 — Dar permiso de escritura a Actions

**Settings → Actions → General → Workflow permissions** →
marca **Read and write permissions** → **Save**.

Sin esto el monitor no puede guardar `docs/datos.json`, que es su memoria entre
una ejecución y la siguiente, y el panel se quedaría siempre vacío.

---

## PASO 2 — Crear los Secrets

**Settings → Secrets and variables → Actions → New repository secret.**
Uno por uno (el nombre tal cual, respetando mayúsculas):

| Secret | Qué poner |
|---|---|
| `DINAPAQ_USUARIO` | El usuario con el que entras al portal, tal cual lo escribes tú. |
| `DINAPAQ_PASSWORD` | Tu contraseña del portal. |
| `CLAVE_PANEL` | **Invéntate una contraseña larga.** Abre el panel y cifra los datos. Que sea distinta de la del portal. Apúntala bien. |
| `VAPID_PRIVADA` | La clave privada que verás en `CLAVES-VAPID.txt`, en la raíz del proyecto. Ya está generada. |
| `VAPID_CONTACTO` | `mailto:ivacuaano@gmail.com` — la norma de Web Push exige un contacto. No recibirás correo por ahí. |
| `DINAPAQ_CLIENTE` | **Solo** si el portal te pide dos códigos en casillas separadas (agencia y cliente): el segundo va aquí. Si tu usuario es uno solo, no crees este secret. |

El de las suscripciones (`PUSH_SUSCRIPCIONES`) lo crearás en el paso 5, cuando
el móvil te dé el texto.

> **`CLAVES-VAPID.txt` no se sube al repositorio** — lo he añadido al
> `.gitignore` a propósito. Quien tenga esa clave privada puede mandar
> notificaciones a tus dispositivos. Cópiala al gestor de contraseñas y ya está.

### Opcional: ajustes en la pestaña *Variables* (no en Secrets)

| Variable | Para qué |
|---|---|
| `DINAPAQ_URL_LISTADO` | **Muy recomendable.** Entra al portal a mano, ve a la pantalla de consulta de envíos, copia la URL de la barra de direcciones y pégala aquí. Le ahorra al monitor tener que adivinar la navegación por el menú. |
| `DINAPAQ_DIAS_ATRAS` | Cuántos días de envíos pedir. Por defecto, 7. |
| `DINAPAQ_URL_LOGIN` | Solo si tu portal usa otra dirección de acceso. |

---

## PASO 3 — Encender GitHub Pages (ojo, ha cambiado)

**Settings → Pages → Build and deployment → Source:** elige **GitHub Actions**.

⚠️ **No elijas «Deploy from a branch»**, que era lo que decía la guía antigua. Esa
opción solo sabe servir la raíz o una carpeta `/docs` que cuelgue de la raíz, y
aquí el panel está en `monitor-envios-github/monitor-envios-nube/docs`. Con
«GitHub Actions», es el propio workflow el que lo publica desde donde está.

No hay nada más que rellenar en esa pantalla. La dirección del panel será:

```
https://silab3d.github.io/SHIPMENTMONITOR/
```

---

## PASO 4 — Lanzar la primera comprobación

**Actions → Monitor de envíos → Run workflow → Run workflow.**

Deja la casilla «Enviar solo un aviso de prueba por cada canal configurado» **sin marcar**.

Tarda menos de un minuto. Cuando termine en verde:

- se habrá creado `docs/datos.json` en el repositorio;
- el panel estará publicado en la dirección de arriba;
- **esta primera pasada no avisa de nada**: solo toma la foto inicial. A partir
  de la segunda, solo suenan las novedades.

Si sale en rojo, salta al final de este documento, a «Si algo sale mal».

---

## PASO 5 — Instalar la app en el móvil y activar los avisos

Este es el único paso que hay que hacer **desde el teléfono**, y solo una vez por
dispositivo.

### 5.1 · Instalar

Abre `https://silab3d.github.io/SHIPMENTMONITOR/` en el móvil y escribe tu
`CLAVE_PANEL`. Deja marcado «Recordar en este dispositivo».

- **Android (Chrome):** menú ⋮ → **Instalar aplicación** / *Añadir a pantalla de
  inicio*.
- **iPhone / iPad (Safari):** botón **Compartir** → **Añadir a pantalla de
  inicio**. Hace falta **iOS 16.4 o superior**.

**En iPhone este paso no es opcional.** Safari no deja recibir notificaciones
push desde una pestaña normal: solo desde la app instalada. Si abres el panel en
Safari sin instalarlo, la propia aplicación te lo dirá y no te ofrecerá activar
los avisos.

En Android funciona también sin instalar, pero instálala igualmente: los avisos
son bastante más fiables.

### 5.2 · Activar

**Abre la app desde su icono** (no desde el navegador) y pulsa **Activar
avisos**, arriba del todo. El móvil te pedirá permiso: acéptalo.

Aparecerá un recuadro con un texto largo que empieza por `{"endpoint":"https://…`.
Pulsa **Copiar**.

### 5.3 · Pegarlo en GitHub

Desde el móvil o desde el ordenador, da igual:

**Settings → Secrets and variables → Actions → New repository secret**

- **Name:** `PUSH_SUSCRIPCIONES`
- **Secret:** pega el texto que acabas de copiar.

Vuelve a la app y pulsa **Ya lo he pegado**. La tarjeta se convertirá en una
línea verde: «Avisos activos en este dispositivo».

### 5.4 · ¿Más de un dispositivo?

Repite 5.1–5.3 en cada uno. Al editar `PUSH_SUSCRIPCIONES`, **pega el texto
nuevo en una línea debajo del anterior**, sin borrar lo que ya había. Queda así:

```
{"endpoint":"https://fcm.googleapis.com/…","keys":{…}}
{"endpoint":"https://updates.push.services.mozilla.com/…","keys":{…}}
```

El monitor acepta las dos formas: uno detrás de otro como arriba, o una lista
JSON entre corchetes. Lo que no entienda, lo ignora sin protestar.

---

## PASO 6 — Comprobar que el aviso llega

**Actions → Monitor de envíos → Run workflow**, ahora **sí** marcando
**«Enviar solo un aviso de prueba por cada canal configurado»** → **Run workflow**.

Esa prueba manda un aviso por cada canal que tengas puesto (push, Telegram y
correo) y en el log dice, canal por canal, cuál ha llegado y cuál no.

No consulta el portal: manda una notificación y punto. En unos segundos tu móvil
debería enseñar **«✅ Los avisos funcionan»**.

Si llega: ya está todo. El cron corre solo de lunes a viernes —cada cuarto de hora de
8:30 a 10:30 y cada hora hasta las 17:30—, con tu ordenador
apagado, y solo te escribirá cuando haya algo nuevo de verdad.

Si no llega, mira el log de esa ejecución: el paso «Enviar un aviso de prueba por cada canal»
dice exactamente qué ha pasado.

---

## Si algo sale mal

### La ejecución sale en rojo

Abre la ejecución y mira el paso **«Consultar el portal»**:

| Lo que dice el log | Qué hacer |
|---|---|
| *«sigue mostrando el formulario de acceso»* | Las credenciales no le valieron al portal. Revisa `DINAPAQ_USUARIO` y `DINAPAQ_PASSWORD`, y **borra `DINAPAQ_CLIENTE`** si tu portal solo pide un usuario. |
| *«no se reconoció ninguna tabla de envíos»* | Entró bien pero se quedó en otra pantalla, o los títulos de las columnas no coinciden con los que conoce. Define la variable `DINAPAQ_URL_LISTADO`. La ejecución adjunta un artefacto llamado **capturas** con el HTML y una imagen de lo que vio: con eso se ajustan los sinónimos de columna de `monitor/parser.py` en cinco minutos. Se descarga desde la propia página de la ejecución, al final del todo. |
| *«Faltan Secrets»* | Faltan `DINAPAQ_USUARIO` o `DINAPAQ_PASSWORD`. |
| *«No se pudo descifrar docs/datos.json»* | La `CLAVE_PANEL` no coincide con la que generó el fichero. O restauras la contraseña buena, o borras `docs/datos.json` del repositorio para empezar de cero. |

Ese es el único punto con incertidumbre real de todo el proyecto: las pruebas
corren contra un portal de mentira incluido en el código, así que que el monitor
entre bien en el DinaPaqWeb **real** y reconozca sus columnas solo se comprueba
ejecutándolo.

### El panel dice que la CLAVE_PANEL es incorrecta, y la estás copiando bien

Casi siempre es **un salto de línea o un espacio invisible al final del Secret**.
Al pegar la contraseña en la caja de GitHub es facilísimo colar un Intro sin
verlo: el workflow cifra entonces con `tuclave\n` y tú tecleas `tuclave`, que es
una clave distinta.

**Ya no debería volver a pasarte**: tanto el monitor como el panel recortan ahora
los espacios de los extremos, así que los dos lados derivan la misma clave. Y un
fichero que se cifró antes con la contraseña «sucia» se sigue abriendo y se
regraba limpio en la siguiente pasada, sin perder el historial.

Para confirmar qué pasó exactamente, hay una herramienta que lo dice en un
comando. La contraseña se teclea a ciegas y no sale del ordenador:

```powershell
cd "d:\Documentos - SSD\SCRIPTS\SHIPMENTMONITOR\monitor-envios-github\monitor-envios-nube"
.\.venv\Scripts\python.exe herramientas\comprobar_clave.py --url https://silab3d.github.io/SHIPMENTMONITOR/
```

Te dirá cuál de las variantes abre el fichero y, **además, te enseñará el error
del portal** que el monitor dejó guardado dentro — que es justo lo que necesitas
para el apartado anterior.

Si no abre con ninguna variante, entonces el Secret no es esa contraseña: o la
cambiaste después de generar el fichero, o no es la misma que escribes. Se
arregla poniendo en el Secret la contraseña con la que se cifró, o borrando
`docs/datos.json` del repositorio para empezar de cero (pierdes el historial de
novedades, nada más).

### El aviso de prueba no llega al móvil

| Síntoma | Causa habitual |
|---|---|
| El log dice «el Secret PUSH_SUSCRIPCIONES está vacío o no tiene ninguna suscripción válida» | El texto se pegó a medias, o se pegó otra cosa. Vuelve al paso 5.2 y cópialo entero. |
| El log dice «suscripción caducada» | El navegador rotó la suscripción. Abre la app, la tarjeta de avisos te pedirá pegar la nueva. Es normal que pase de tanto en tanto. |
| En el iPhone no aparece el botón «Activar avisos» | No has abierto la app **desde su icono**, o no llegaste a instalarla. Safari no da push desde una pestaña. |
| El log dice «ok» pero no ves nada | Mira el ahorro de batería y el «No molestar» del teléfono. En Android, ajustes de la app instalada → Notificaciones. |
| El navegador dice «Registration failed - push service error» al pulsar «Activar avisos» | Estás en **Brave**, que trae desactivado el servicio de push de Google. Ve a `brave://settings/privacy`, activa **«Usar los servicios de Google para la mensajería push»** y reinicia el navegador. En Chrome o Edge funciona sin tocar nada. |

### El aviso de Telegram no llega

Lanza **Run workflow** con la casilla de prueba marcada y mira el log del paso
«Enviar un aviso de prueba por cada canal»: el monitor traduce lo que conteste
Telegram y, si hace falta, te dice cuál es el `TELEGRAM_CHAT_ID` bueno.

| Lo que dice el log | Qué pasa |
|---|---|
| «the bot can't send messages to the bot» | En `TELEGRAM_CHAT_ID` está el id del **propio bot** (el número que va delante de los dos puntos del token), no el de tu chat. El log te lista los chats buenos justo debajo. |
| «bot can't initiate conversation with a user» o «chat not found» | Nunca le has escrito al bot. Ábrelo en Telegram, pulsa **Iniciar** (`/start`), mándale cualquier cosa y repite la prueba. |
| «Telegram no tiene ninguna conversación registrada con este bot» | Lo mismo: escríbele una vez al bot y vuelve a lanzar la prueba, y entonces sí podrá decirte el id. |
| Un 401 o un 404 | El `TELEGRAM_TOKEN` no vale. Pídeselo otra vez a **@BotFather**. |

### Falla un paso que ya habías arreglado

**Actions ejecuta el workflow tal como estaba en el commit que disparó la
ejecución, no como está ahora en `main`.** Si arreglas el fichero y subes el
cambio, las ejecuciones que ya estaban disparadas siguen usando la versión
vieja, y verás fallar algo que ya no existe en tu código.

Para saber si te está pasando: abre el log del paso y mira las órdenes que
aparecen. Si no coinciden con lo que pone tu `monitor.yml` actual, es esto.

La solución es simplemente **lanzar una ejecución nueva** desde
Actions → Monitor de envíos → Run workflow. Esa sí usará el fichero al día.

### Los pasos siguen sin salir

El workflow no aparece → confirma que el fichero `.github/workflows/monitor.yml`
existe **en la raíz** del repositorio en GitHub (no dentro de
`monitor-envios-github/`), y que el `push` del paso 0 llegó a subirse.

---

## Cosas menores que puedes hacer cuando quieras

- **Borrar `monitor-envios-github.zip`** de la raíz del repositorio: son 742 kB
  de una copia antigua del proyecto que ya no sirve para nada.
- **Borrar el PDF y la carpeta `guia/`**: describen la versión anterior, la de
  Telegram, y ahora contradicen a este documento.
- **Cambiar la frecuencia:** en `.github/workflows/monitor.yml`, la línea
  `- cron: '0 6-17 * * *'` (en UTC), y el paso «¿Toca comprobar a esta hora?»
  acota la franja en hora de España. GitHub retrasa los
  cron en horas punta de todas formas.
- **Dejar de vigilar un rato:** Actions → Monitor de envíos → menú ⋯ →
  *Disable workflow*.

> GitHub desactiva solo los cron de los repositorios sin actividad durante 60
> días. Como el monitor hace commits cada vez que cambia algo, en la práctica no
> se llega a dar. Si pasara, recibirás un aviso por correo de GitHub y se
> reactiva con un clic.

---

## Para probarlo en tu ordenador sin tocar GitHub

Sigue funcionando igual que antes:

```powershell
cd "d:\Documentos - SSD\SCRIPTS\SHIPMENTMONITOR\monitor-envios-github\monitor-envios-nube"

$env:CLAVE_PANEL = "prueba"
.\.venv\Scripts\python.exe -m monitor.ejecutar --demo --sin-avisos
.\.venv\Scripts\python.exe -m monitor.ejecutar --demo --semilla 1 --sin-avisos

.\.venv\Scripts\python.exe -m http.server 8899 --directory docs
```

Abre `http://localhost:8899` y escribe `prueba`. Ctrl+C para parar.

**Borra `docs\datos.json` antes de volver a subir nada**, o la primera ejecución
real fallará al no poder descifrarlo con tu `CLAVE_PANEL`:

```powershell
Remove-Item docs\datos.json
```

Los avisos push **no** se pueden probar así: el navegador exige HTTPS, y
`localhost` no tiene un servicio de push detrás. Se prueban desde GitHub, con el
paso 6.
