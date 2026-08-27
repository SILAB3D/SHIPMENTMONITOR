"""Estado del monitor: qué envíos conocemos, qué ha cambiado y qué se publica.

Vive en un único fichero (`docs/datos.json`, cifrado) que hace dos papeles:
memoria entre ejecuciones del workflow y fuente de datos del panel.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from monitor import config
from monitor.cifrado import cifrar, descifrar
from monitor.parser import diferencias


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


VACIO = {"version": 1, "envios": {}, "eventos": [], "meta": {}}


def cargar(ruta: Path | None = None, password: str | None = None) -> dict:
    ruta = ruta or config.FICHERO_DATOS
    password = password if password is not None else config.CLAVE_PANEL
    if not ruta.exists():
        return json.loads(json.dumps(VACIO))
    sobre = json.loads(ruta.read_text(encoding="utf-8"))
    if "datos" not in sobre:            # fichero en claro (modo demo local)
        return sobre

    # La contraseña buena es la recortada, pero un fichero escrito por una
    # versión anterior pudo cifrarse con el valor tal cual venía del Secret,
    # espacios y saltos de línea incluidos. Probamos las dos: si abre con la
    # antigua, `guardar` lo reescribirá ya con la recortada y el problema se
    # arregla solo en esta misma pasada.
    candidatas = [password]
    if password is not None and config.CLAVE_PANEL_CRUDA not in candidatas:
        candidatas.append(config.CLAVE_PANEL_CRUDA)

    for candidata in candidatas:
        try:
            return descifrar(sobre, candidata)
        except Exception:  # noqa: BLE001
            continue

    raise RuntimeError(
        "No se pudo descifrar docs/datos.json: la CLAVE_PANEL no coincide con la que "
        "generó el fichero. Cambia el Secret o borra el fichero para empezar de cero."
    )


def guardar(estado: dict, ruta: Path | None = None, password: str | None = None) -> None:
    ruta = ruta or config.FICHERO_DATOS
    password = password if password is not None else config.CLAVE_PANEL
    ruta.parent.mkdir(parents=True, exist_ok=True)
    contenido = cifrar(estado, password) if password else estado
    ruta.write_text(json.dumps(contenido, ensure_ascii=False, indent=1), encoding="utf-8")


def _resumen(campos: dict) -> str:
    partes = [campos.get(k, "") for k in ("estado", "destinatario", "localidad", "fecha")]
    return " · ".join(p for p in partes if p) or "sin detalles"


def sincronizar(estado: dict, envios: list[dict]) -> list[dict]:
    """Mezcla el listado recién leído y devuelve los eventos nuevos."""
    conocidos: dict = estado.setdefault("envios", {})
    eventos: list[dict] = estado.setdefault("eventos", [])
    primera_vez = not conocidos
    t = ahora()
    nuevos: list[dict] = []
    siguiente_id = max((e["id"] for e in eventos), default=0) + 1

    def anotar(tipo: str, envio_id: str, titulo: str, detalle: str, campos: dict) -> None:
        nonlocal siguiente_id
        ev = {
            "id": siguiente_id,
            "ts": t,
            "tipo": tipo,
            "envio_id": envio_id,
            "titulo": titulo,
            "detalle": detalle,
            "campos": campos,
        }
        siguiente_id += 1
        nuevos.append(ev)
        eventos.insert(0, ev)

    def foto(envio: dict) -> dict:
        """Lo que se guarda de un envío. `pasos` e `hitos` pueden faltar si el
        detalle del portal no se pudo leer: en ese caso no se pisa lo que ya
        teníamos, que sigue siendo mejor que nada."""
        datos = {"campos": envio["campos"], "hash": envio["hash"]}
        for clave in ("pasos", "hitos", "guid"):
            if envio.get(clave):
                datos[clave] = envio[clave]
        return datos

    for envio in envios:
        previo = conocidos.get(envio["id"])
        if previo is None:
            conocidos[envio["id"]] = {
                **foto(envio),
                "visto_primera": t,
                "visto_ultima": t,
            }
            # el primer arranque solo sella la línea base: no se avisa del histórico
            if not primera_vez:
                anotar("nuevo", envio["id"], f"Nuevo envío {envio['id']}", _resumen(envio["campos"]), envio["campos"])
            continue

        previo["visto_ultima"] = t
        if previo["hash"] == envio["hash"]:
            continue

        cambios = diferencias(previo["campos"], envio["campos"])
        pasos_antes = len(previo.get("pasos") or [])
        previo.update(foto(envio))
        pasos_ahora = len(envio.get("pasos") or [])

        # Una lectura nueva en el recorrido (un escaneo en un hub, por ejemplo)
        # puede no mover el «último estado» del listado y aun así ser la novedad
        # que interesa. Se cuenta como cambio y se dice cuál ha sido.
        if pasos_ahora > pasos_antes and envio.get("pasos"):
            ultimo = envio["pasos"][-1]
            lugar = f" ({ultimo['lugar']})" if ultimo.get("lugar") else ""
            cambios.append(("recorrido", "", f"{ultimo.get('estado','')}{lugar} · {ultimo.get('ts','')}"))

        if cambios:
            # Un cambio normal se cuenta «campo: antes → ahora». Los que no
            # tienen «antes» —una lectura nueva en el recorrido— se cuentan sin
            # flecha, que si no salía un «recorrido: — → TRANSITO» ilegible.
            detalle = "; ".join(
                f"{c}: {b or '—'}" if not a else f"{c}: {a} → {b or '—'}"
                for c, a, b in cambios
            )
            anotar("actualizado", envio["id"], f"Envío {envio['id']} actualizado", detalle, envio["campos"])

    del eventos[config.MAX_EVENTOS :]
    return nuevos


def sellar_meta(estado: dict, error: str | None = None, envios_leidos: int = 0) -> None:
    estado["meta"] = {
        "ultima_comprobacion": ahora(),
        "envios_leidos": envios_leidos,
        "error": error,
        "repo": config.REPO,
        "ejecucion": config.EJECUCION_URL,
        "canales": config.canales(),
    }
