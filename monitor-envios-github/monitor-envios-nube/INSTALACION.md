# Puesta en marcha en GitHub — paso a paso

Unos 15 minutos, sin instalar nada en tu ordenador. **Coste: 0 €.**

| Pieza | Para qué | Coste |
|---|---|---|
| GitHub Actions | ejecuta la comprobación cada 30 min | gratis e **ilimitado en repositorios públicos** |
| GitHub Pages | sirve el panel por HTTPS | gratis en repositorios públicos |
| Playwright + Chromium | entra al portal como lo harías tú | gratis (Apache 2.0), se instala en el runner |
| Bot de Telegram | avisos al móvil | gratis |
| Tu correo (SMTP) | avisos por email | gratis con la cuenta que ya tienes |
| React + Inter | panel y tipografía, servidos desde tu propio repo | gratis (MIT / SIL OFL) |

> **¿Público? ¿Y mis datos?** El repositorio es público para que Actions y Pages
> salgan gratis, pero los envíos se publican **cifrados** con una contraseña que
> solo conoces tú, y las credenciales del portal viven en los *Secrets*, que no
> son visibles para nadie. Si prefieres repositorio privado, mira la nota del
> final.

---

## 1. Crear el repositorio

1. Entra en <https://github.com/new>.
2. Nombre: por ejemplo `monitor-envios`. Marca **Public**. Crea el repositorio.
3. Sube los ficheros de esta carpeta. Lo más cómodo sin usar git:
   **Add file → Upload files**, arrastra *todo* el contenido (incluida la carpeta
   `.github`) y confirma con **Commit changes**.

   > Si arrastras y no aparece `.github/workflows/monitor.yml`, créalo a mano con
   > **Add file → Create new file**, escribe esa ruta como nombre y pega el
   > contenido del fichero.

Con git sería:

```bash
git init && git add . && git commit -m "monitor de envíos"
git branch -M main
git remote add origin https://github.com/TU-USUARIO/monitor-envios.git
git push -u origin main
```

## 2. Guardar las credenciales como Secrets

**Settings → Secrets and variables → Actions → New repository secret.** Uno por uno:

| Secret | Valor |
|---|---|
| `DINAPAQ_USUARIO` | **el usuario con el que entras al portal**, tal cual lo escribes tú |
| `DINAPAQ_PASSWORD` | tu contraseña del portal |
| `CLAVE_PANEL` | **inventa una contraseña larga**: es la que abrirá el panel y la que cifra los datos |
| `DINAPAQ_CLIENTE` | *solo* si el portal te pide dos códigos en dos casillas separadas (agencia y cliente): el segundo va aquí |

### Usuario + contraseña, o dos códigos

El acceso está preparado para las dos formas que usa este portal, sin que tengas
que configurar nada:

- **Un solo usuario + contraseña** (lo más habitual): pon ese usuario en
  `DINAPAQ_USUARIO` y no crees `DINAPAQ_CLIENTE`. Si tu usuario es la unión de
  agencia y cliente (por ejemplo `02112345`), va entero en `DINAPAQ_USUARIO`.
- **Dos casillas, agencia y cliente**: `DINAPAQ_USUARIO` = agencia y
  `DINAPAQ_CLIENTE` = cliente. Si el portal cambiara a una sola casilla, el
  monitor los une automáticamente.

El monitor localiza el formulario por el campo de contraseña y rellena solo los
campos de ese formulario, así que no se confunde con buscadores ni con otros
inputs de la página, y funciona igual si el login está dentro de un `frame`.
(`DINAPAQ_AGENCIA` sigue valiendo como sinónimo de `DINAPAQ_USUARIO`.)

Apunta bien `CLAVE_PANEL`: si la cambias más adelante, hay que borrar
`docs/datos.json` del repositorio para empezar de cero.

### Avisos (opcional, pero es la gracia)

**Telegram** — lo más cómodo para el móvil:

1. Habla con [@BotFather](https://t.me/BotFather) → `/newbot` → te da un token.
2. Escríbele algo a tu bot recién creado.
3. Abre `https://api.telegram.org/bot<TOKEN>/getUpdates` y copia el número de `chat.id`.
4. Crea los secrets `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID`.

**Email** — crea `SMTP_HOST`, `SMTP_PUERTO`, `SMTP_USUARIO`, `SMTP_PASSWORD` y
`EMAIL_DESTINO`. Con Gmail: `smtp.gmail.com`, puerto `587`, y como contraseña una
**contraseña de aplicación** de Google (no la de tu cuenta).

### Ajustes opcionales

En la pestaña **Variables** (al lado de Secrets), no en Secrets:

| Variable | Para qué |
|---|---|
| `DINAPAQ_URL_LISTADO` | URL directa de la pantalla de consulta de envíos. **Muy recomendable**: navega a mano hasta ella, copia la URL de la barra y pégala aquí. |
| `DINAPAQ_DIAS_ATRAS` | cuántos días de envíos pedir (7 por defecto) |
| `DINAPAQ_URL_LOGIN` | solo si tu portal usa otra dirección de acceso |
| `DINAPAQ_SEL_USUARIO`, `DINAPAQ_SEL_CLIENTE`, `DINAPAQ_SEL_PASSWORD` | selectores CSS de los campos, solo si algún día la detección automática fallara (p. ej. `input[name=usuario]`) |

## 3. Encender Actions y Pages

- **Settings → Actions → General → Workflow permissions**: marca
  **Read and write permissions** y guarda. (Hace falta para que el monitor pueda
  guardar los datos en el repositorio.)
- **Settings → Pages → Build and deployment**: en *Source* elige **Deploy from a
  branch**, rama `main` y carpeta **`/docs`**. Guarda.

Tu panel quedará en `https://TU-USUARIO.github.io/monitor-envios/`.

## 4. Primera comprobación

**Actions → Monitor de envíos → Run workflow**. Tarda un par de minutos (instala
Chromium). Cuando termine en verde:

- Se habrá creado `docs/datos.json` en el repositorio.
- Esa primera pasada **no avisa de nada**: solo toma la foto inicial. A partir de
  la segunda, solo suenan las novedades.

### Si sale en rojo

Abre la ejecución y mira el paso «Consultar el portal»:

| Mensaje | Qué hacer |
|---|---|
| «sigue mostrando el formulario de acceso» | Las credenciales no le valieron al portal. Revisa `DINAPAQ_USUARIO` y `DINAPAQ_PASSWORD`, y borra `DINAPAQ_CLIENTE` si tu portal solo pide un usuario. |
| «no se reconoció ninguna tabla de envíos» | Entró bien, pero se quedó en otra pantalla. Define `DINAPAQ_URL_LISTADO`. En la ejecución se adjunta un artefacto **capturas** con el HTML y una imagen de lo que vio: con eso se ajustan las columnas en `monitor/parser.py`. |
| «Faltan Secrets» | Faltan `DINAPAQ_USUARIO` o `DINAPAQ_PASSWORD`. |

## 5. Abrir el panel

Entra en `https://TU-USUARIO.github.io/monitor-envios/` y escribe la
`CLAVE_PANEL`. Deja marcado «Recordar en este dispositivo» y no volverá a
pedírtela en ese navegador.

**Instalarlo como app**: en Chrome/Edge, icono de instalar en la barra de
direcciones; en el móvil, «Añadir a pantalla de inicio». Queda con su icono y a
pantalla completa.

**Avisos en el propio dispositivo**: pulsa «Activar avisos» dentro del panel; te
notificará las novedades que hayan llegado desde tu última visita. Para enterarte
estés donde estés, con la app cerrada, el canal bueno es Telegram.

## 6. Cambiar la frecuencia

En `.github/workflows/monitor.yml`, la línea del cron:

```yaml
    - cron: '*/30 * * * *'     # cada 30 minutos
```

Ejemplos: `0 * * * *` cada hora; `*/15 8-20 * * 1-5` cada 15 min en horario
laboral (la hora del cron es **UTC**: en España, resta 1 h en invierno y 2 en
verano). GitHub ejecuta los cron cuando tiene hueco, así que puede retrasarse
unos minutos; para vigilar envíos da igual.

## 7. Mantenimiento

- **Nada que actualizar**: cada ejecución instala lo que necesita.
- GitHub **desactiva los cron** de un repositorio que pasa 60 días sin actividad.
  Como el monitor va guardando `docs/datos.json`, es raro que ocurra; si pasa,
  recibirás un aviso por correo y se reactiva con un clic desde la pestaña
  Actions.
- Para dejar de vigilar temporalmente: **Actions → Monitor de envíos → ··· →
  Disable workflow**.
- Para empezar de cero: borra `docs/datos.json` del repositorio.

## 8. Preguntas rápidas

**¿Alguien podría ver mis envíos?** El fichero publicado es un bloque cifrado con
AES-256-GCM y una clave derivada de tu contraseña con PBKDF2 (200 000
iteraciones). Sin esa contraseña no hay nada legible. Aun así, usa una
contraseña larga y distinta de la del portal.

**¿Y mi contraseña del portal?** Está en los Secrets de GitHub, cifrada y solo
accesible desde el workflow; ni siquiera aparece en los logs. No se escribe en
ningún fichero del repositorio.

**¿Puedo tener el repositorio privado?** Sí, pero entonces Actions tiene 2 000
minutos gratis al mes (una pasada cada 30 min se los come) y Pages en privado
pide plan de pago. La alternativa gratuita es repositorio privado + [Cloudflare
Pages](https://pages.cloudflare.com) apuntando a la carpeta `docs/`.

**¿Puedo forzar una comprobación desde el móvil?** Sí: en la app de GitHub o
desde la web, **Actions → Monitor de envíos → Run workflow**.
