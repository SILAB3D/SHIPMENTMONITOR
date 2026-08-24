# Monitor de envíos TIPSA / DinaPaqWeb

Vigila el portal DinaPaqWeb, detecta **envíos nuevos** y **cambios en los que ya
seguías**, y avisa por **Telegram** y **email**. El panel es una PWA instalable
en móvil y escritorio.

No se ejecuta en tu ordenador: **vive entero en GitHub**. Un workflow de GitHub
Actions entra al portal cada 30 minutos y publica los datos; GitHub Pages sirve
el panel. No hay nada que instalar ni que dejar encendido.

👉 **Para ponerlo en marcha: [INSTALACION.md](INSTALACION.md)** — 15 minutos, coste 0 €.

```
   ⏱ cada 30 min (cron de GitHub Actions)
        │
        ▼
┌──────────────────┐   Playwright    ┌──────────────┐
│ runner de GitHub │ ──────────────► │  DinaPaqWeb  │
│  (Ubuntu)        │ ◄────────────── │   (portal)   │
└────────┬─────────┘   listado HTML  └──────────────┘
         │ compara con lo que ya sabía
         ├─────────────► Telegram / email  (novedades)
         │
         ▼ docs/datos.json  (cifrado con TU contraseña)
┌──────────────────┐
│  GitHub Pages    │  ← PWA: descarga el fichero y lo descifra en tu navegador
└──────────────────┘
```

## Por qué así

- **Siempre vigilando.** El cron corre en los servidores de GitHub: tu ordenador
  puede estar apagado. La sesión del portal se inicia sola en cada pasada usando
  los Secrets, así que no hay que volver a introducir credenciales nunca.
- **Gratis de verdad.** GitHub Actions es ilimitado en repositorios públicos y
  Pages también; Telegram y tu correo de siempre no cuestan nada.
- **Privado aunque el repositorio sea público.** Los datos de tus envíos se
  publican cifrados con AES-GCM y una contraseña que solo conoces tú
  (`CLAVE_PANEL`). El panel los descifra en el navegador con WebCrypto. Las
  credenciales del portal viven en los Secrets del repositorio y nunca se
  escriben en ningún fichero.

## El panel

- Acceso con la contraseña del panel, con opción de recordarla en el dispositivo.
- Una tarjeta por envío con referencia, destinatario, localidad, fecha, bultos,
  kilos, estado y un **diagrama de 4 pasos** (Grabado → Tránsito → Reparto →
  Entrega) que marca dónde está y pinta en rojo las incidencias.
- «Ver detalle» despliega todos los campos leídos del portal y el historial de
  cambios de ese envío.
- Filtros, buscador y panel de novedades. Tonos naranja, modo claro y oscuro
  automáticos, y sin solapamientos entre 320 px y pantalla completa.
- Instalable como aplicación desde Chrome/Edge/Safari, en escritorio y móvil.

## Qué se considera «novedad»

Una referencia que no estaba, o un cambio en alguno de estos campos:

```python
CAMPOS_VIGILADOS = ("estado", "entrega", "observaciones", "localidad", "bultos", "kilos")
```

Está en `monitor/parser.py`. La primera ejecución solo sella la línea base: no
avisa del histórico.

## Estructura

```
.github/workflows/monitor.yml   el cron y todo el proceso
monitor/
  ejecutar.py    entrada: una pasada completa
  scraper.py     Playwright: login y navegación por el portal
  parser.py      HTML → lista de envíos (columnas por palabras clave)
  estado.py      memoria entre ejecuciones y cálculo de novedades
  cifrado.py     AES-GCM + PBKDF2 (compatible con WebCrypto)
  notificar.py   Telegram y email
  demo.py        datos ficticios para probar
docs/            la PWA que publica GitHub Pages (+ datos.json cifrado)
tests/           pruebas:  python -m pytest tests -q
```

## Probarlo en local antes de subirlo

Solo para desarrollo; en producción nunca hace falta:

```bash
pip install -r requirements.txt
CLAVE_PANEL=prueba python -m monitor.ejecutar --demo --sin-avisos
python -m http.server 8899 --directory docs      # abre http://localhost:8899
```

## Ajustes

| Dónde | Qué |
|---|---|
| `cron` en `monitor.yml` | frecuencia (por defecto `*/30`) |
| Variable `DINAPAQ_URL_LISTADO` | URL directa de la pantalla de consulta |
| Variable `DINAPAQ_DIAS_ATRAS` | cuántos días de envíos pedir |
| `SINONIMOS` en `parser.py` | nombres de columna que sabe reconocer |
| Secrets `DINAPAQ_USUARIO` / `DINAPAQ_CLIENTE` | usuario del portal; el segundo solo si te pide dos códigos |

## Consideraciones

- El monitor usa **tus credenciales** y hace lo mismo que harías tú mirando la
  pantalla. Conviene revisar las condiciones de uso del portal antes de dejarlo
  corriendo indefinidamente.
- Cada 30 minutos es de sobra y no carga su servidor. Bajar de 15 no aporta:
  GitHub ejecuta los cron cuando puede y puede retrasarlos unos minutos.
- Si TIPSA te da acceso a su **web service** de cliente, merece la pena cambiar
  `scraper.py` por llamadas a la API: el resto (novedades, avisos, panel) sigue
  igual mientras `obtener_envios()` devuelva la misma lista de diccionarios.
