"""Configuración: todo llega por variables de entorno (los Secrets del repositorio)."""
from __future__ import annotations

import json
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DOCS = RAIZ / "docs"
CAPTURAS = RAIZ / "capturas"
FICHERO_DATOS = DOCS / "datos.json"


def _int(clave: str, defecto: int) -> int:
    try:
        return int(os.environ.get(clave, defecto))
    except ValueError:
        return defecto


def _bool(clave: str, defecto: bool = False) -> bool:
    return os.environ.get(clave, str(defecto)).strip().lower() in ("1", "true", "si", "sí", "yes", "on")


# --- Acceso al portal (Secrets) ---
URL_LOGIN = os.environ.get("DINAPAQ_URL_LOGIN", "https://dinapaqweb.tipsa-dinapaq.com/DinaPaqWeb/login_web.php")
URL_LISTADO = os.environ.get("DINAPAQ_URL_LISTADO", "")
ENLACE_LISTADO = os.environ.get("DINAPAQ_ENLACE_LISTADO", r"(consulta|listado|relaci[oó]n).*env[ií]o|env[ií]os")
# El portal puede pedir un solo usuario, o código de agencia + código de cliente.
# DINAPAQ_USUARIO es el nombre recomendado; DINAPAQ_AGENCIA se mantiene por
# compatibilidad. Si tu portal usa dos campos, el segundo va en DINAPAQ_CLIENTE.
USUARIO = os.environ.get("DINAPAQ_USUARIO") or os.environ.get("DINAPAQ_AGENCIA", "")
CLIENTE = os.environ.get("DINAPAQ_CLIENTE", "")
PASSWORD = os.environ.get("DINAPAQ_PASSWORD", "")

# Solo si la detección automática falla: selectores CSS de los campos.
SEL_USUARIO = os.environ.get("DINAPAQ_SEL_USUARIO", "")
SEL_CLIENTE = os.environ.get("DINAPAQ_SEL_CLIENTE", "")
SEL_PASSWORD = os.environ.get("DINAPAQ_SEL_PASSWORD", "")
DIAS_ATRAS = _int("DINAPAQ_DIAS_ATRAS", 7)
HEADLESS = _bool("HEADLESS", True)

# --- Cifrado de los datos publicados ---
# Al pegar la contraseña en la caja de Secrets de GitHub es facilísimo colar un
# salto de línea o un espacio al final sin verlo. Eso cambia la clave derivada,
# y el panel rechazaría la contraseña «correcta» que escribes en el móvil.
# Recortamos siempre los espacios de los extremos, y el panel hace lo mismo, así
# que los dos lados derivan exactamente la misma clave.
CLAVE_PANEL_CRUDA = os.environ.get("CLAVE_PANEL", "")
CLAVE_PANEL = CLAVE_PANEL_CRUDA.strip()

# --- Avisos push al propio dispositivo (canal principal) ---
# Par de claves VAPID: la pública vive en docs/push-config.js (la lee la PWA) y
# la privada es un Secret. Se generan una sola vez con:
#     python -m monitor.webpush --generar-claves
VAPID_PRIVADA = os.environ.get("VAPID_PRIVADA", "")
VAPID_CONTACTO = os.environ.get("VAPID_CONTACTO", "mailto:monitor-envios@example.invalid")

# Suscripciones de los dispositivos. El panel te da el texto JSON al activar los
# avisos; se pega en el Secret PUSH_SUSCRIPCIONES. Admite una sola suscripción,
# una lista de varias, o varias separadas por líneas en blanco.
PUSH_SUSCRIPCIONES_CRUDO = os.environ.get("PUSH_SUSCRIPCIONES", "")

# --- Avisos por intermediarios (opcionales; si no pones los Secrets, no se usan) ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PUERTO = _int("SMTP_PUERTO", 587)
SMTP_USUARIO = os.environ.get("SMTP_USUARIO", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
EMAIL_DESTINO = os.environ.get("EMAIL_DESTINO", "")

# --- Contexto del repositorio (lo rellena Actions solo) ---
REPO = os.environ.get("GITHUB_REPOSITORY", "")
EJECUCION_URL = (
    f"https://github.com/{REPO}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}" if REPO else ""
)

# Máximo de eventos que se conservan en el historial publicado
MAX_EVENTOS = _int("MAX_EVENTOS", 300)


def credenciales_ok() -> bool:
    return bool(PASSWORD and (USUARIO or CLIENTE))


def suscripciones() -> list[dict]:
    """Lee PUSH_SUSCRIPCIONES sea cual sea la forma en que se haya pegado.

    Se aceptan tres formatos porque el Secret lo rellena una persona a mano:
    un objeto suelto, una lista JSON, o varios objetos pegados uno detrás de
    otro (uno por dispositivo). Lo que no sea una suscripción válida se ignora
    en silencio: nunca debe tumbar la comprobación del portal.
    """
    crudo = PUSH_SUSCRIPCIONES_CRUDO.strip()
    if not crudo:
        return []

    def validas(candidatos) -> list[dict]:
        salida = []
        for c in candidatos if isinstance(candidatos, list) else [candidatos]:
            if not isinstance(c, dict):
                continue
            claves = c.get("keys")
            if not isinstance(claves, dict):
                continue
            if c.get("endpoint") and claves.get("p256dh") and claves.get("auth"):
                salida.append(c)
        return salida

    try:
        return validas(json.loads(crudo))
    except json.JSONDecodeError:
        pass

    # Varios objetos pegados en bruto: los troceamos contando llaves.
    trozos, profundidad, inicio, en_texto, escapado = [], 0, None, False, False
    for i, ch in enumerate(crudo):
        if en_texto:
            en_texto = not (ch == '"' and not escapado)
            escapado = ch == "\\" and not escapado
            continue
        if ch == '"':
            en_texto, escapado = True, False
        elif ch == "{":
            if profundidad == 0:
                inicio = i
            profundidad += 1
        elif ch == "}":
            profundidad -= 1
            if profundidad == 0 and inicio is not None:
                trozos.append(crudo[inicio : i + 1])
                inicio = None

    encontradas = []
    for t in trozos:
        try:
            encontradas += validas(json.loads(t))
        except json.JSONDecodeError:
            continue
    return encontradas


def push_ok() -> bool:
    return bool(VAPID_PRIVADA and suscripciones())


def canales() -> dict[str, bool]:
    return {
        "push": push_ok(),
        "telegram": bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID),
        "email": bool(SMTP_HOST and EMAIL_DESTINO),
    }
