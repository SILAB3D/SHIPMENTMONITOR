"""Acceso al portal y lectura del listado, contra un DinaPaqWeb de mentira.

El portal real es una API JSON detrás de ExtJS (ver monitor/scraper.py). Aquí se
levanta un servidor que imita sus dos únicos extremos —`ajax/ajax_login.php` y
`ajax/ajax_consulta_envios.php`— y se ejecuta el scraper de verdad contra él.
Así se cubren el acceso, la paginación, los errores del portal y el mapeo de
campos sin depender de la red ni de las credenciales reales.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from monitor import config  # noqa: E402
from monitor import scraper  # noqa: E402

USUARIO_BUENO = "02112345"
PASSWORD_BUENA = "secreta"

# Dos filas con la forma exacta que devuelve ajax_consulta_envios.php
FILAS = [
    {
        "V_COD_AGE_CARGO": "02", "V_COD_AGE_ORI": "1", "V_ALBARAN": "2345678",
        "V_NOM_ORI": "SILAB3D", "V_CP_ORI": "46001", "V_DIR_ORI": "C/ MAYOR 1",
        "V_POB_ORI": "VALENCIA", "V_NOM_DES": "FARMACIA SOL", "V_POB_DES": "MADRID",
        "V_NOM_EST": "EN REPARTO", "D_FEC_HORA_EST": "26/08/2026 09:12",
        "V_REF": "PED-1001", "F_PESO_ORI": 3.4, "I_BUL": 2, "D_FECHA": "25/08/2026",
        "V_OBS": "", "U_GUID": "AAA-111", "V_URL_POD": "",
    },
    {
        "V_COD_AGE_CARGO": "02", "V_COD_AGE_ORI": "1", "V_ALBARAN": "2345679",
        "V_NOM_ORI": "SILAB3D", "V_CP_ORI": "46001", "V_DIR_ORI": "C/ MAYOR 1",
        "V_POB_ORI": "VALENCIA", "V_NOM_DES": "LAB VIDAL", "V_POB_DES": "BILBAO",
        "V_NOM_EST": "ENTREGADO", "D_FEC_HORA_EST": "26/08/2026 11:40",
        "V_REF": "PED-1002", "F_PESO_ORI": 0.8, "I_BUL": 1, "D_FECHA": "25/08/2026",
        "V_OBS": "Recibe: J. PEREZ", "U_GUID": "AAA-222", "V_URL_POD": "",
    },
]


class PortalFalso(ThreadingHTTPServer):
    """Servidor con los interruptores que necesitan las pruebas."""
    allow_reuse_address = True
    filas = FILAS
    por_pagina = 100          # cuántas filas devuelve por tanda
    total_declarado = None    # si se fija, se miente en «total»
    respuesta_login = None    # si se fija, se devuelve tal cual (texto crudo)
    peticiones: list[dict] = []


class Manejador(BaseHTTPRequestHandler):
    def log_message(self, *_):  # silencio en la salida de pytest
        pass

    def _responder(self, cuerpo: str, codigo: int = 200, tipo: str = "application/json") -> None:
        datos = cuerpo.encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        if not self.headers.get("Cookie"):
            self.send_header("Set-Cookie", "PHPSESSID=falsa123; path=/")
        self.end_headers()
        self.wfile.write(datos)

    def do_GET(self):  # noqa: N802
        self._responder("<html><body>login</body></html>", tipo="text/html")

    def do_POST(self):  # noqa: N802
        largo = int(self.headers.get("Content-Length") or 0)
        campos = {k: v[0] for k, v in parse_qs(self.rfile.read(largo).decode("utf-8")).items()}
        self.server.peticiones.append({"ruta": self.path, "campos": campos})

        if self.path.endswith("ajax_login.php"):
            if self.server.respuesta_login is not None:
                return self._responder(self.server.respuesta_login, tipo="text/html")
            bien = campos.get("usuario") == USUARIO_BUENO and campos.get("password") == PASSWORD_BUENA
            if bien:
                return self._responder(json.dumps({"success": True, "errors": {"msg": ""}}))
            return self._responder(json.dumps(
                {"success": False, "errors": {"msg": "Usuario o contraseña incorrectos"}}))

        if self.path.endswith("ajax_consulta_envios.php"):
            inicio = int(campos.get("start") or 0)
            limite = min(int(campos.get("limit") or 15), self.server.por_pagina)
            filas = self.server.filas[inicio : inicio + limite]
            total = self.server.total_declarado
            if total is None:
                total = len(self.server.filas)
            return self._responder(json.dumps({
                "success": True, "errors": {"msg": ""},
                "total": total, "datos": filas, "URLPOD": "", "URLFirma": "",
            }))

        self._responder("no encontrado", codigo=404, tipo="text/plain")


@pytest.fixture
def portal():
    servidor = PortalFalso(("127.0.0.1", 0), Manejador)
    servidor.peticiones = []
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    servidor.url = f"http://127.0.0.1:{servidor.server_port}/DinaPaqWeb/login_web.php"
    yield servidor
    servidor.shutdown()
    servidor.server_close()


def _configurar(**variables):
    """Reescribe el entorno y recarga configuración y scraper."""
    for clave in [k for k in os.environ if k.startswith("DINAPAQ_")]:
        del os.environ[clave]
    os.environ.update({k: str(v) for k, v in variables.items() if v not in (None, "")})
    importlib.reload(config)
    importlib.reload(scraper)


def _entrar() -> list[dict]:
    return asyncio.run(scraper.obtener_envios())


def test_lee_los_envios(portal):
    _configurar(DINAPAQ_URL_LOGIN=portal.url, DINAPAQ_USUARIO=USUARIO_BUENO,
                DINAPAQ_PASSWORD=PASSWORD_BUENA)
    envios = _entrar()
    assert [e["id"] for e in envios] == ["0212345678", "0212345679"]
    primero = envios[0]["campos"]
    assert primero["estado"] == "EN REPARTO"
    assert primero["destinatario"] == "FARMACIA SOL"
    assert primero["localidad"] == "MADRID"
    assert primero["fecha"] == "25/08/2026"
    assert primero["bultos"] == "2"       # los enteros no salen como «2.0»
    assert primero["kilos"] == "3.4"
    assert "entrega" not in primero       # aún no está entregado
    assert envios[1]["campos"]["entrega"] == "26/08/2026 11:40"


def test_agencia_y_cliente_van_pegados(portal):
    """El portal pide agencia y cliente escritos seguidos en un único campo."""
    _configurar(DINAPAQ_URL_LOGIN=portal.url, DINAPAQ_AGENCIA="021",
                DINAPAQ_CLIENTE="12345", DINAPAQ_PASSWORD=PASSWORD_BUENA)
    assert len(_entrar()) == 2
    assert portal.peticiones[0]["campos"]["usuario"] == USUARIO_BUENO


def test_manda_los_filtros_que_espera_el_portal(portal):
    _configurar(DINAPAQ_URL_LOGIN=portal.url, DINAPAQ_USUARIO=USUARIO_BUENO,
                DINAPAQ_PASSWORD=PASSWORD_BUENA, DINAPAQ_DIAS_ATRAS=7)
    _entrar()
    consulta = portal.peticiones[1]["campos"]
    assert consulta["estados"] == "TODOS"
    assert consulta["aplicafecha"] == "true"
    assert consulta["filtrocampo"] == "-1"
    # dd/mm/aaaa, que es el formato que fija inc/lang/ext-fecha-ddmm.js
    assert len(consulta["fechaini"].split("/")) == 3
    assert consulta["fechaini"][2] == "/" and consulta["fechafin"][5] == "/"


def test_pagina_hasta_traerlos_todos(portal):
    portal.filas = FILAS * 60          # 120 filas
    portal.por_pagina = 50
    _configurar(DINAPAQ_URL_LOGIN=portal.url, DINAPAQ_USUARIO=USUARIO_BUENO,
                DINAPAQ_PASSWORD=PASSWORD_BUENA)
    envios = _entrar()
    # los ids se repiten, pero se han pedido las tres tandas
    consultas = [p for p in portal.peticiones if "consulta" in p["ruta"]]
    assert len(consultas) == 3
    assert len(envios) == 120


def test_credenciales_rechazadas(portal):
    _configurar(DINAPAQ_URL_LOGIN=portal.url, DINAPAQ_USUARIO=USUARIO_BUENO,
                DINAPAQ_PASSWORD="equivocada")
    with pytest.raises(scraper.PortalError, match="rechazado las credenciales"):
        _entrar()


def test_el_motivo_del_portal_llega_al_mensaje(portal):
    _configurar(DINAPAQ_URL_LOGIN=portal.url, DINAPAQ_USUARIO=USUARIO_BUENO,
                DINAPAQ_PASSWORD="equivocada")
    with pytest.raises(scraper.PortalError, match="Usuario o contraseña incorrectos"):
        _entrar()


def test_respuesta_que_no_es_json(portal):
    """Si la sesión caduca, el portal contesta HTML; hay que decirlo claro."""
    portal.respuesta_login = "<html><body>No hay sesión registrada</body></html>"
    _configurar(DINAPAQ_URL_LOGIN=portal.url, DINAPAQ_USUARIO=USUARIO_BUENO,
                DINAPAQ_PASSWORD=PASSWORD_BUENA)
    with pytest.raises(scraper.PortalError, match="No hay sesión registrada"):
        _entrar()


def test_sin_envios_no_es_un_fallo(portal):
    portal.filas = []
    _configurar(DINAPAQ_URL_LOGIN=portal.url, DINAPAQ_USUARIO=USUARIO_BUENO,
                DINAPAQ_PASSWORD=PASSWORD_BUENA)
    assert _entrar() == []


def test_sin_credenciales(portal):
    _configurar(DINAPAQ_URL_LOGIN=portal.url)
    with pytest.raises(scraper.PortalError, match="Faltan Secrets"):
        _entrar()
