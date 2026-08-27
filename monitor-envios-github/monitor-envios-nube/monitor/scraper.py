"""Cliente del portal DinaPaqWeb (TIPSA-Dinapaq).

Por qué esto ya no usa un navegador
-----------------------------------
La primera versión manejaba el portal con Playwright, como si fuera una persona:
rellenaba el formulario, pulsaba «Aceptar» y leía la tabla de la pantalla. Con
este portal eso NO puede funcionar, y conviene dejar escrito por qué para que a
nadie le tiente volver atrás:

* El formulario lo pinta ExtJS 2 con `monitorValid: true` y el botón lleva
  `formBind: true`. Es decir, «Aceptar» nace **deshabilitado** y solo se activa
  cuando la tarea de validación de ExtJS —que corre cada 200 ms— ve los campos
  llenos. Rellenar con Playwright y pulsar acto seguido pulsaba un botón muerto.
* El manejador del botón no envía nada: abre un cuadro de progreso y programa el
  envío con `setTimeout(..., 3000)`. Tres segundos después hace una petición
  AJAX a `ajax/ajax_login.php`. No hay navegación de por medio.
* Con acceso correcto, la página **no cambia**: sigue mostrando el formulario y
  abre el listado en una ventana nueva con `window.open('consulta_envios.php')`.
  Por eso la comprobación «¿sigue habiendo un campo de contraseña?» daba siempre
  «credenciales rechazadas», tanto si entrábamos como si no.

Debajo de ExtJS, el portal es una API JSON limpia y estable desde 2008:

    POST ajax/ajax_login.php           -> {"success":bool, "errors":{"msg":...}}
    POST ajax/ajax_consulta_envios.php -> {"total":n, "datos":[...], "success":bool}

Hablamos con ella directamente. Sale más rápido (sin Chromium que instalar en
cada ejecución), es determinista y, cuando algo falla, el portal nos dice en
castellano qué pasa en lugar de tener que adivinarlo de una captura.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin

import requests

from monitor import config

log = logging.getLogger("scraper")

TIEMPO_ESPERA = 45          # segundos por petición
POR_PAGINA = 200            # el portal pagina; pedimos tandas grandes
MAX_PAGINAS = 25            # tope de seguridad: 5.000 envíos

CABECERAS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "es-ES,es;q=0.9",
}

# Campo del JSON del portal -> nombre canónico que usan el panel y estado.py.
# Los nombres canónicos son los mismos que ya reconocía el parser de HTML, así
# que el panel y el historial siguen funcionando sin tocar nada.
CAMPOS = {
    "D_FECHA": "fecha",
    "V_NOM_EST": "estado",
    "D_FEC_HORA_EST": "fecha_estado",
    "V_NOM_DES": "destinatario",
    "V_POB_DES": "localidad",
    "V_NOM_ORI": "remitente",
    "V_POB_ORI": "localidad_origen",
    "V_CP_ORI": "cp_origen",
    "V_REF": "ref_cliente",
    "I_BUL": "bultos",
    "F_PESO_ORI": "kilos",
    "V_OBS": "observaciones",
}

# Un envío se da por entregado cuando su último estado lo dice.
RE_ENTREGADO = re.compile(r"entreg", re.I)


class PortalError(RuntimeError):
    pass


def _base(url_login: str) -> str:
    """La carpeta del portal, a partir de la URL de acceso.

    De `https://…/DinaPaqWeb/login_web.php` sale `https://…/DinaPaqWeb/`, que es
    donde cuelgan `ajax/…` y `consulta_envios.php`.
    """
    return urljoin(url_login, ".")


def _texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return re.sub(r"\s+", " ", str(valor)).strip()


def _cuerpo(respuesta: requests.Response) -> str:
    """El texto de la respuesta, decodificado sin destrozar los acentos.

    El portal es de 2008 y sus páginas de error salen en ISO-8859-1 sin declarar
    `charset`. En ese caso `requests` supone ISO-8859-1 unas veces y UTF-8 otras,
    y el mensaje del portal llega ilegible («No hay sesiÃ³n registrada»)
    justo cuando más falta hace entenderlo. Aquí se prueba en orden: lo que diga
    la cabecera, UTF-8, y luego las codificaciones latinas.
    """
    declarado = ""
    if coincidencia := re.search(r"charset=([\w-]+)", respuesta.headers.get("Content-Type", ""), re.I):
        declarado = coincidencia.group(1)
    for codificacion in (declarado, "utf-8", "cp1252", "latin-1"):
        if not codificacion:
            continue
        try:
            return respuesta.content.decode(codificacion)
        except (UnicodeDecodeError, LookupError):
            continue
    return respuesta.content.decode("utf-8", "replace")


def _json_o_error(respuesta: requests.Response, que: str) -> dict:
    """Interpreta la respuesta del portal, que no siempre es JSON limpio."""
    if respuesta.status_code == 401:
        raise PortalError(
            f"El portal respondió 401 al {que}: la sesión no se ha registrado. "
            "Suele significar que el acceso no llegó a completarse."
        )
    cuerpo = _cuerpo(respuesta).strip()
    if not cuerpo:
        raise PortalError(f"El portal devolvió una respuesta vacía al {que} (HTTP {respuesta.status_code}).")
    try:
        return json.loads(cuerpo)
    except json.JSONDecodeError:
        # Cuando la sesión caduca, el portal contesta con HTML («No hay sesión
        # registrada») en vez de JSON. Enseñarlo recortado ayuda muchísimo.
        limpio = re.sub(r"<[^>]+>", " ", cuerpo)
        limpio = re.sub(r"\s+", " ", limpio).strip()
        raise PortalError(
            f"El portal no devolvió JSON al {que} (HTTP {respuesta.status_code}). "
            f"Esto es lo que contestó: {limpio[:300] or '(sin texto)'}"
        )


def _abrir_sesion() -> tuple[requests.Session, str]:
    """Entra en el portal y devuelve la sesión ya autenticada."""
    if not config.credenciales_ok():
        raise PortalError(
            "Faltan Secrets: define DINAPAQ_USUARIO (o DINAPAQ_AGENCIA) y DINAPAQ_PASSWORD "
            "en Settings → Secrets and variables → Actions."
        )

    base = _base(config.URL_LOGIN)
    sesion = requests.Session()
    sesion.headers.update(CABECERAS)

    # Visitar el login primero: así el portal nos da la cookie de sesión PHP
    # antes de mandarle las credenciales, igual que haría un navegador.
    try:
        sesion.get(config.URL_LOGIN, timeout=TIEMPO_ESPERA)
    except requests.RequestException as e:
        raise PortalError(f"No se pudo abrir {config.URL_LOGIN}: {e}") from e

    # El usuario de este portal es «código de agencia + código de cliente» todo
    # junto. Si vienen en dos Secrets distintos, se pegan aquí.
    usuario = (config.USUARIO or "") + (config.CLIENTE or "")

    try:
        respuesta = sesion.post(
            urljoin(base, "ajax/ajax_login.php"),
            data={
                "usuario": usuario,
                "password": config.PASSWORD,
                "conectadep": "",
                "departamento": "",
            },
            headers={"Referer": config.URL_LOGIN},
            timeout=TIEMPO_ESPERA,
        )
    except requests.RequestException as e:
        raise PortalError(f"No se pudo enviar el acceso al portal: {e}") from e

    datos = _json_o_error(respuesta, "acceder")
    if not datos.get("success"):
        motivo = ""
        if isinstance(datos.get("errors"), dict):
            motivo = _texto(datos["errors"].get("msg"))
        raise PortalError(
            "El portal ha rechazado las credenciales."
            + (f" Dice: «{motivo}»." if motivo else "")
            + " Revisa los Secrets DINAPAQ_USUARIO y DINAPAQ_PASSWORD. El usuario es el "
              "código de agencia y el de cliente escritos seguidos (por ejemplo 02112345)."
        )

    log.info("acceso al portal correcto")
    return sesion, base


def _pedir_pagina(sesion: requests.Session, base: str, inicio: int, desde: str, hasta: str) -> dict:
    """Una tanda del listado, con los mismos parámetros que manda el portal."""
    parametros = {
        # Los que arma `AplicarFiltros()` en js/consulta_envios.js
        "fechaini": desde,
        "fechafin": hasta,
        "filtrocampo": -1,        # sin filtro de texto
        "filtro": "",
        "estados": "TODOS",       # todos los estados, como el check «Todos»
        "aplicafecha": "true",    # sí, aplica el rango de fechas
        # Paginación y orden del store de ExtJS
        "start": inicio,
        "limit": POR_PAGINA,
        "sort": "V_ALBARAN",
        "dir": "ASC",
    }
    try:
        respuesta = sesion.post(
            urljoin(base, "ajax/ajax_consulta_envios.php"),
            data=parametros,
            headers={"Referer": urljoin(base, "consulta_envios.php")},
            timeout=TIEMPO_ESPERA,
        )
    except requests.RequestException as e:
        raise PortalError(f"No se pudo consultar el listado de envíos: {e}") from e

    datos = _json_o_error(respuesta, "consultar los envíos")
    if datos.get("success") is False:
        motivo = ""
        if isinstance(datos.get("errors"), dict):
            motivo = _texto(datos["errors"].get("msg"))
        raise PortalError(f"El portal rechazó la consulta de envíos{f': «{motivo}»' if motivo else ''}.")
    return datos


def _identificador(fila: dict) -> str:
    """Número de envío completo: cargo + origen + albarán.

    Es como lo compone el propio portal para enlazar el albarán escaneado, y
    evita que dos agencias distintas con el mismo número de albarán se pisen.
    """
    partes = [_texto(fila.get(k)) for k in ("V_COD_AGE_CARGO", "V_COD_AGE_ORI", "V_ALBARAN")]
    completo = "".join(partes)
    return completo or _texto(fila.get("V_ALBARAN")) or _texto(fila.get("U_GUID"))


def _a_envio(fila: dict) -> dict:
    campos: dict[str, str] = {}
    for origen, canonico in CAMPOS.items():
        valor = _texto(fila.get(origen))
        if valor:
            campos[canonico] = valor

    referencia = _identificador(fila)
    campos["referencia"] = referencia

    # «Entrega» solo tiene sentido cuando el envío está entregado; si no, la
    # fecha del último estado ya sale como «fecha_estado».
    if RE_ENTREGADO.search(campos.get("estado", "")):
        campos["entrega"] = campos.get("fecha_estado", "")

    # El hash decide si un envío ha cambiado. Se calcula sobre los campos
    # canónicos ordenados, no sobre el JSON crudo: así, si el portal añade una
    # columna nueva que no nos interesa, no lo tomamos por una actualización.
    huella = "|".join(f"{k}={campos[k]}" for k in sorted(campos))
    return {
        "id": referencia,
        "campos": campos,
        "crudo": [campos.get(k, "") for k in ("referencia", "fecha", "estado", "destinatario", "localidad")],
        "hash": hashlib.sha1(huella.encode("utf-8")).hexdigest(),
    }


def leer_envios() -> list[dict]:
    """Una pasada completa: entra, pide el listado y devuelve los envíos."""
    sesion, base = _abrir_sesion()

    hasta = datetime.now()
    desde = hasta - timedelta(days=config.DIAS_ATRAS)
    f_desde, f_hasta = desde.strftime("%d/%m/%Y"), hasta.strftime("%d/%m/%Y")
    log.info("consultando envíos del %s al %s", f_desde, f_hasta)

    filas: list[dict] = []
    total = None
    for pagina in range(MAX_PAGINAS):
        datos = _pedir_pagina(sesion, base, len(filas), f_desde, f_hasta)
        tanda = datos.get("datos") or []
        if total is None:
            try:
                total = int(datos.get("total") or 0)
            except (TypeError, ValueError):
                total = 0
        filas.extend(tanda)
        if not tanda or len(filas) >= total:
            break
    else:
        log.warning("se alcanzó el tope de %d páginas; puede faltar histórico", MAX_PAGINAS)

    log.info("el portal declara %s envío(s); leídos %d", total, len(filas))

    if not filas:
        if total == 0:
            # No es un fallo: puede que simplemente no haya envíos en el rango.
            log.info("no hay envíos en el rango de fechas consultado")
            return []
        raise PortalError(
            f"El portal dice tener {total} envíos pero no ha devuelto ninguno. "
            "Puede que haya cambiado el formato de la respuesta de "
            "ajax/ajax_consulta_envios.php."
        )

    envios = [_a_envio(f) for f in filas if _identificador(f)]
    if not envios:
        raise PortalError(
            "Se recibieron filas del portal pero ninguna trae número de albarán "
            "(V_ALBARAN). Seguramente han cambiado los nombres de los campos; "
            f"la primera fila trae estas claves: {sorted(filas[0])[:20]}"
        )
    return envios


async def obtener_envios() -> list[dict]:
    """Fachada asíncrona, para no cambiar quien ya la llamaba con `asyncio.run`."""
    return leer_envios()
