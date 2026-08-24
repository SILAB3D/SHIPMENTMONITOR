"""Configuración: todo llega por variables de entorno (los Secrets del repositorio)."""
from __future__ import annotations

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
CLAVE_PANEL = os.environ.get("CLAVE_PANEL", "")

# --- Avisos ---
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


def canales() -> dict[str, bool]:
    return {
        "telegram": bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID),
        "email": bool(SMTP_HOST and EMAIL_DESTINO),
    }
