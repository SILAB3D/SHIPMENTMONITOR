"""El acceso al portal debe funcionar tanto si pide un único usuario como si
pide código de agencia + código de cliente, y también dentro de frames.

Se levanta un portal de mentira en local y se ejecuta el scraper de verdad
contra él (Playwright incluido).
"""
import asyncio
import functools
import importlib
import os
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

playwright = pytest.importorskip("playwright.async_api")

from monitor import config  # noqa: E402
from monitor.scraper import PortalError, obtener_envios  # noqa: E402


@pytest.fixture(scope="module")
def portal():
    """Sirve tests/portal en un puerto libre mientras dure el módulo."""
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(Path(__file__).parent / "portal"))
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{servidor.server_port}"
    servidor.shutdown()


def _configurar(**variables):
    """Reescribe el entorno y recarga la configuración del monitor."""
    for clave in [k for k in os.environ if k.startswith("DINAPAQ_")]:
        del os.environ[clave]
    os.environ.update({k: v for k, v in variables.items() if v})
    importlib.reload(config)


def _entrar() -> list[dict]:
    return asyncio.run(obtener_envios())


def test_portal_con_un_solo_usuario(portal):
    _configurar(
        DINAPAQ_URL_LOGIN=f"{portal}/simple/login.html",
        DINAPAQ_USUARIO="USR-1",
        DINAPAQ_PASSWORD="secreta",
    )
    envios = _entrar()
    assert [e["id"] for e in envios] == ["0012345678", "0012345679"]
    assert envios[0]["campos"]["estado"] == "EN REPARTO"


def test_portal_con_agencia_y_cliente(portal):
    _configurar(
        DINAPAQ_URL_LOGIN=f"{portal}/dos_codigos/login.html",
        DINAPAQ_AGENCIA="021",
        DINAPAQ_CLIENTE="12345",
        DINAPAQ_PASSWORD="secreta",
    )
    assert len(_entrar()) == 2


def test_dos_codigos_en_un_unico_campo(portal):
    """Si el portal solo ofrece un hueco, agencia y cliente van juntos."""
    _configurar(
        DINAPAQ_URL_LOGIN=f"{portal}/simple/login.html",
        DINAPAQ_AGENCIA="021",
        DINAPAQ_CLIENTE="12345",
        DINAPAQ_PASSWORD="secreta",
    )
    assert len(_entrar()) == 2


def test_login_dentro_de_frames(portal):
    _configurar(
        DINAPAQ_URL_LOGIN=f"{portal}/con_frames/index.html",
        DINAPAQ_USUARIO="USR-1",
        DINAPAQ_PASSWORD="secreta",
    )
    assert len(_entrar()) == 2


def test_credenciales_incorrectas(portal):
    _configurar(
        DINAPAQ_URL_LOGIN=f"{portal}/simple/login.html",
        DINAPAQ_USUARIO="USR-1",
        DINAPAQ_PASSWORD="equivocada",
    )
    with pytest.raises(PortalError, match="formulario de acceso"):
        _entrar()


def test_sin_credenciales(portal):
    _configurar(DINAPAQ_URL_LOGIN=f"{portal}/simple/login.html")
    with pytest.raises(PortalError, match="Faltan Secrets"):
        _entrar()
