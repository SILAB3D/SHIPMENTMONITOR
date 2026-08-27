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


DETALLE_HTML = """
<html><body><div id="content">
 <div><div id="stepper" class="stepper stepper--horizontal">
  <div>
   <div class="stepper-item"><span>23/07/2026 08:47</span><div><img><div></div></div>
     <div><div><span class="step-title">Entregado</span><button class="toggleButton">+</button></div></div></div>
   <div class="stepper-item"><span>23/07/2026 07:16</span>
     <div><div><span class="step-title">En reparto</span></div></div></div>
   <div class="stepper-item"><span>22/07/2026 16:11</span>
     <div><div><span class="step-title">En camino</span></div></div></div>
   <div class="stepper-item"><span>22/07/2026 14:09</span>
     <div><div><span class="step-title">Documentado</span></div></div></div>
  </div></div></div>
 <div class="panel-datos-resto mdl-grid">
   <div class="mdl-cell color-accent">Remitente</div><div class="mdl-cell">HOSPITAL X</div>
 </div>
 <div class="panel-datos-resto mdl-grid">
  <table class="mdl-data-table tabla">
   <thead><tr><th></th><th>Bultos: 1</th></tr></thead>
   <thead><tr><th>FECHA/HORA</th><th>ESTADO</th><th>POBLACIÓN</th><th>Leidos</th><th>Dif.</th></tr></thead>
   <tbody>
    <tr><td>23/07/26 08:47</td>
        <td class="ellipsis"><span class="mdl-tooltip">ENTREGADO</span><span>ENTREGADO</span></td>
        <td class="ellipsis"><span class="mdl-tooltip"></span><span></span></td><td><span></span></td><td><span></span></td></tr>
    <tr><td>23/07/26 07:17</td>
        <td class="ellipsis"><span class="mdl-tooltip">LECTURA EN AGENCIA DESTINO SALAMANCA 32</span><span>LECTURA EN AGENCIA DESTINO SALAMANCA 32</span></td>
        <td class="ellipsis"><span class="mdl-tooltip">SALAMANCA</span><span>SALAMANCA</span></td><td><span>1</span></td><td><span>0</span></td></tr>
    <tr><td>22/07/26 14:09</td>
        <td class="ellipsis"><span class="mdl-tooltip">PENDIENTE DE ENTREGAR A TIPSA</span><span>PENDIENTE DE ENTREGAR A TIPSA</span></td>
        <td class="ellipsis"><span class="mdl-tooltip"></span><span></span></td><td><span></span></td><td><span></span></td></tr>
   </tbody>
  </table>
 </div>
</div></body></html>
"""


class PortalFalso(ThreadingHTTPServer):
    """Servidor con los interruptores que necesitan las pruebas."""
    allow_reuse_address = True
    filas = FILAS
    por_pagina = 100          # cuántas filas devuelve por tanda
    total_declarado = None    # si se fija, se miente en «total»
    respuesta_login = None    # si se fija, se devuelve tal cual (texto crudo)
    detalle = DETALLE_HTML    # HTML que sirve detalle_envio.php
    codificacion = "utf-8"    # el portal real usa ISO-8859-1
    peticiones: list[dict] = []


class Manejador(BaseHTTPRequestHandler):
    def log_message(self, *_):  # silencio en la salida de pytest
        pass

    def _responder(self, cuerpo: str, codigo: int = 200, tipo: str = "application/json") -> None:
        # El portal real sirve las pantallas en ISO-8859-1 y NO lo dice en la
        # cabecera, solo en un <meta> del HTML. Se imita para que las pruebas
        # cubran de verdad la decodificación.
        datos = cuerpo.encode(getattr(self.server, "codificacion", "utf-8"), "replace")
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        if not self.headers.get("Cookie"):
            self.send_header("Set-Cookie", "PHPSESSID=falsa123; path=/")
        self.end_headers()
        self.wfile.write(datos)

    def do_GET(self):  # noqa: N802
        if "detalle_envio.php" in self.path:
            self.server.peticiones.append({"ruta": self.path, "campos": {}})
            return self._responder(self.server.detalle, tipo="text/html")
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
    # 120 envíos DISTINTOS: el albarán es lo que los identifica
    portal.filas = [dict(FILAS[0], V_ALBARAN=f"{7000000 + i}") for i in range(120)]
    portal.por_pagina = 50
    _configurar(DINAPAQ_URL_LOGIN=portal.url, DINAPAQ_USUARIO=USUARIO_BUENO,
                DINAPAQ_PASSWORD=PASSWORD_BUENA, DINAPAQ_LEER_DETALLE="false")
    envios = _entrar()
    consultas = [p for p in portal.peticiones if "consulta" in p["ruta"]]
    assert len(consultas) == 3          # 50 + 50 + 20
    assert len(envios) == 120


def test_no_se_repiten_los_envios_entre_tramos(portal):
    """Al preguntar mes a mes, un envío no puede colarse dos veces."""
    _configurar(DINAPAQ_URL_LOGIN=portal.url, DINAPAQ_USUARIO=USUARIO_BUENO,
                DINAPAQ_PASSWORD=PASSWORD_BUENA, DINAPAQ_LEER_DETALLE="false")
    envios = _entrar()
    assert len(envios) == len({e["id"] for e in envios}) == 2


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


# ─────────────────────── recorrido de cada envío ───────────────────────

def test_lee_el_recorrido_del_envio(portal):
    _configurar(DINAPAQ_URL_LOGIN=portal.url, DINAPAQ_USUARIO=USUARIO_BUENO,
                DINAPAQ_PASSWORD=PASSWORD_BUENA)
    envios = _entrar()

    # Los hitos llegan del más antiguo al más reciente, no como los pinta el portal
    hitos = envios[0]["hitos"]
    assert [h["estado"] for h in hitos] == ["Documentado", "En camino", "En reparto", "Entregado"]
    assert hitos[0]["ts"] == "22/07/2026 14:09"

    # Y la tabla de situaciones, con su población y sin el texto duplicado del tooltip
    pasos = envios[0]["pasos"]
    assert [p["estado"] for p in pasos] == [
        "PENDIENTE DE ENTREGAR A TIPSA",
        "LECTURA EN AGENCIA DESTINO SALAMANCA 32",
        "ENTREGADO",
    ]
    assert pasos[1]["lugar"] == "SALAMANCA"
    assert pasos[-1]["ts"] == "23/07/26 08:47"


def test_una_lectura_nueva_cuenta_como_novedad(portal):
    """Un escaneo en un hub no cambia el «último estado», pero es una novedad."""
    from monitor import estado as est

    _configurar(DINAPAQ_URL_LOGIN=portal.url, DINAPAQ_USUARIO=USUARIO_BUENO,
                DINAPAQ_PASSWORD=PASSWORD_BUENA)
    envios = _entrar()
    memoria = {"version": 1, "envios": {}, "eventos": [], "meta": {}}
    est.sincronizar(memoria, envios)          # línea base

    # Mismo estado en el listado, pero una lectura más en el recorrido
    portal.detalle = DETALLE_HTML.replace(
        "<tbody>\n    <tr><td>23/07/26 08:47</td>",
        "<tbody>\n    <tr><td>23/07/26 09:30</td>"
        "<td class=\"ellipsis\"><span>LECTURA EN HUB MADRID</span></td>"
        "<td class=\"ellipsis\"><span>MADRID</span></td><td><span>1</span></td><td><span>0</span></td></tr>"
        "\n    <tr><td>23/07/26 08:47</td>")
    eventos = est.sincronizar(memoria, _entrar())

    assert len(eventos) == 2                   # los dos envíos del listado
    assert "LECTURA EN HUB MADRID (MADRID)" in eventos[0]["detalle"]


def test_si_el_detalle_falla_el_envio_sigue_valiendo(portal):
    portal.detalle = "<html><body>vaya</body></html>"
    _configurar(DINAPAQ_URL_LOGIN=portal.url, DINAPAQ_USUARIO=USUARIO_BUENO,
                DINAPAQ_PASSWORD=PASSWORD_BUENA)
    envios = _entrar()
    assert len(envios) == 2
    assert envios[0]["campos"]["estado"] == "EN REPARTO"
    assert envios[0].get("pasos") == []


def test_se_puede_apagar_la_lectura_del_detalle(portal):
    _configurar(DINAPAQ_URL_LOGIN=portal.url, DINAPAQ_USUARIO=USUARIO_BUENO,
                DINAPAQ_PASSWORD=PASSWORD_BUENA, DINAPAQ_LEER_DETALLE="false")
    _entrar()
    assert not [p for p in portal.peticiones if "detalle_envio" in p["ruta"]]


# ─────────────────── el rango nunca puede cruzar de mes ───────────────────
# `ajax_consulta_envios.php` devuelve CERO envíos, sin dar error, si el rango
# pisa dos meses naturales. Es el fallo más traicionero del portal: haría que el
# monitor se quedara ciego los primeros días de cada mes.

def test_los_tramos_no_cruzan_de_mes():
    from datetime import datetime as dt
    tramos = scraper._tramos_mensuales(dt(2026, 4, 25), dt(2026, 5, 5))
    assert [(a.strftime("%d/%m"), b.strftime("%d/%m")) for a, b in tramos] == [
        ("25/04", "30/04"), ("01/05", "05/05")]
    assert all(a.month == b.month and a.year == b.year for a, b in tramos)


def test_un_tramo_dentro_del_mismo_mes_no_se_parte():
    from datetime import datetime as dt
    assert len(scraper._tramos_mensuales(dt(2026, 5, 3), dt(2026, 5, 28))) == 1


def test_los_tramos_cubren_el_cambio_de_ano():
    from datetime import datetime as dt
    tramos = scraper._tramos_mensuales(dt(2025, 12, 28), dt(2026, 1, 4))
    assert [(a.strftime("%d/%m/%Y"), b.strftime("%d/%m/%Y")) for a, b in tramos] == [
        ("28/12/2025", "31/12/2025"), ("01/01/2026", "04/01/2026")]


def test_se_pregunta_una_vez_por_mes(portal, monkeypatch):
    """Con una ventana que cruza de mes hay que hacer dos consultas, no una."""
    import monitor.scraper as sc
    _configurar(DINAPAQ_URL_LOGIN=portal.url, DINAPAQ_USUARIO=USUARIO_BUENO,
                DINAPAQ_PASSWORD=PASSWORD_BUENA, DINAPAQ_DIAS_ATRAS=5,
                DINAPAQ_LEER_DETALLE="false")

    class FechaFalsa(sc.datetime):
        @classmethod
        def now(cls):
            return sc.datetime(2026, 5, 3, 10, 0)   # 3 de mayo: la ventana entra en abril

    monkeypatch.setattr(sc, "datetime", FechaFalsa)
    _entrar()

    consultas = [p["campos"] for p in portal.peticiones if "consulta" in p["ruta"]]
    rangos = {(c["fechaini"], c["fechafin"]) for c in consultas}
    assert rangos == {("28/04/2026", "30/04/2026"), ("01/05/2026", "03/05/2026")}


def test_los_acentos_del_portal_llegan_enteros(portal):
    """El portal responde en ISO-8859-1 sin declararlo en la cabecera HTTP.

    Si se decodificara como UTF-8 a las bravas, «ALCALÁ DE GUADAIRA» acabaría
    como «ALCALÃ DE GUADAIRA» en los avisos del móvil.
    """
    portal.codificacion = "iso-8859-1"
    portal.detalle = DETALLE_HTML.replace(
        "<span>SALAMANCA</span>", "<span>ALCALÁ DE GUADAIRA</span>").replace(
        '<meta charset="utf-8">', "")
    portal.detalle = ('<html><head><meta http-equiv="Content-Type" '
                      'content="text/html; charset=ISO-8859-1"></head>' + portal.detalle)
    _configurar(DINAPAQ_URL_LOGIN=portal.url, DINAPAQ_USUARIO=USUARIO_BUENO,
                DINAPAQ_PASSWORD=PASSWORD_BUENA)
    pasos = _entrar()[0]["pasos"]
    assert any(p["lugar"] == "ALCALÁ DE GUADAIRA" for p in pasos)
