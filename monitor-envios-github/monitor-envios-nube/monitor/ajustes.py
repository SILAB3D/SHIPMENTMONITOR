"""Los ajustes que se tocan desde el panel: cuándo se vigila y de qué se avisa.

Por qué un fichero en el repositorio y no unas variables de entorno
------------------------------------------------------------------
Los Secrets y las Variables del repositorio solo se cambian entrando en GitHub
desde un ordenador, y estos dos ajustes —el horario de vigilancia y qué avisos
quieres recibir— son justo los que apetece cambiar desde el móvil, un domingo,
sin abrir nada. Así que viven en `docs/ajustes.json`, en claro (ni el horario ni
las casillas de los avisos son un secreto) y dentro del propio repositorio:

  · lo lee el monitor en cada ejecución (este módulo),
  · lo lee el panel para pintar la pestaña de Ajustes,
  · y lo escribe el panel disparando el workflow «Guardar los ajustes», que es
    el que tiene permiso para hacer commit. El token que publica el panel solo
    puede lanzar workflows, así que nunca toca el repositorio directamente.

Todo lo que entra se normaliza aquí (`normalizar`). Un fichero a medias, con un
día imposible o un tramo del revés no puede dejar al monitor sin vigilar: lo que
no se entiende se descarta y, si no queda nada en pie, se usa el horario de
siempre.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from monitor import config

FICHERO = config.DOCS / "ajustes.json"

# Qué se comprueba, de cuánto en cuánto. Es el horario de toda la vida del
# monitor, y el que se usa mientras nadie toque nada en el panel.
HORARIO_DEFECTO = {
    "id": "jornada",
    "nombre": "Jornada laboral",
    "activo": True,
    "dias": [1, 2, 3, 4, 5],
    "tramos": [
        {"desde": "08:30", "hasta": "10:30", "cada": 15},
        {"desde": "10:30", "hasta": "17:30", "cada": 60},
    ],
}

# Las clases de aviso que se pueden encender y apagar. La clave es la que viaja
# en el fichero; el texto es el que enseña el panel.
CLASES_AVISO = {
    "nuevo": "Envíos nuevos",
    "actualizado": "Cambios de estado",
    "incidencia": "Incidencias",
    "entrega": "Entregas",
    "error": "Fallos del monitor",
    "panel": "Avisos del panel abierto",
}

CANALES = ("push", "telegram", "email")

DEFECTO: dict = {
    "version": 1,
    "horarios": [HORARIO_DEFECTO],
    "avisos": {clave: True for clave in CLASES_AVISO},
    "canales": {canal: True for canal in CANALES},
}

MIN_CADA, MAX_CADA = 5, 720          # de cinco minutos a doce horas
RELOJ = re.compile(r"^(\d{1,2}):(\d{2})$")


# ─────────────────────────── horas ───────────────────────────
def minutos(hhmm: str | int | None) -> int | None:
    """«08:30» → 510. Devuelve None si no hay forma de entenderlo."""
    if isinstance(hhmm, int):
        return hhmm if 0 <= hhmm <= 24 * 60 else None
    m = RELOJ.match(str(hhmm or "").strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 24 or mi > 59 or h * 60 + mi > 24 * 60:
        return None
    return h * 60 + mi


def reloj(minuto: int) -> str:
    """510 → «08:30»."""
    return f"{minuto // 60:02d}:{minuto % 60:02d}"


# ─────────────────────────── normalización ───────────────────────────
def _tramo(crudo) -> dict | None:
    if not isinstance(crudo, dict):
        return None
    desde, hasta = minutos(crudo.get("desde")), minutos(crudo.get("hasta"))
    if desde is None or hasta is None or hasta <= desde:
        return None
    try:
        cada = int(crudo.get("cada", 60))
    except (TypeError, ValueError):
        return None
    cada = max(MIN_CADA, min(cada, MAX_CADA))
    return {"desde": reloj(desde), "hasta": reloj(hasta), "cada": cada}


def _horario(crudo, indice: int) -> dict | None:
    if not isinstance(crudo, dict):
        return None
    dias = []
    for d in crudo.get("dias") or []:
        try:
            d = int(d)
        except (TypeError, ValueError):
            continue
        if 1 <= d <= 7 and d not in dias:
            dias.append(d)
    tramos = [t for t in (_tramo(t) for t in crudo.get("tramos") or []) if t]
    if not dias or not tramos:
        return None
    ident = str(crudo.get("id") or "").strip() or f"h{indice + 1}"
    return {
        "id": ident[:40],
        "nombre": (str(crudo.get("nombre") or "").strip() or "Sin nombre")[:60],
        "activo": crudo.get("activo", True) is not False,
        "dias": sorted(dias),
        "tramos": sorted(tramos, key=lambda t: t["desde"]),
    }


def normalizar(crudo) -> dict:
    """Deja los ajustes en la forma que espera el resto del programa.

    Nunca levanta una excepción ni devuelve algo inservible: si el fichero viene
    roto se cae al horario de siempre y a todos los avisos encendidos, que es lo
    que hacía el monitor antes de que esto se pudiera configurar.
    """
    crudo = crudo if isinstance(crudo, dict) else {}

    horarios, ids = [], set()
    for i, h in enumerate(crudo.get("horarios") or []):
        limpio = _horario(h, i)
        if not limpio:
            continue
        while limpio["id"] in ids:               # dos configuraciones con el mismo id
            limpio["id"] += "_"
        ids.add(limpio["id"])
        horarios.append(limpio)
    if not horarios:
        horarios = [json.loads(json.dumps(HORARIO_DEFECTO))]

    avisos = dict(DEFECTO["avisos"])
    for clave, valor in (crudo.get("avisos") or {}).items():
        if clave in avisos:
            avisos[clave] = valor is not False

    canales = dict(DEFECTO["canales"])
    for clave, valor in (crudo.get("canales") or {}).items():
        if clave in canales:
            canales[clave] = valor is not False

    limpio = {"version": 1, "horarios": horarios, "avisos": avisos, "canales": canales}
    if crudo.get("actualizado"):
        limpio["actualizado"] = str(crudo["actualizado"])[:40]
    return limpio


# ─────────────────────────── fichero ───────────────────────────
def ruta() -> Path:
    """El fichero de ajustes; AJUSTES_FICHERO lo desvía (lo usan las pruebas)."""
    return Path(os.environ.get("AJUSTES_FICHERO") or FICHERO)


def cargar(desde: Path | None = None) -> dict:
    fichero = Path(desde) if desde else ruta()
    try:
        return normalizar(json.loads(fichero.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 · fichero ausente, roto o ilegible: valores de siempre
        return normalizar({})


def guardar(ajustes: dict, destino: Path | None = None) -> dict:
    fichero = Path(destino) if destino else ruta()
    limpio = normalizar(ajustes)
    fichero.parent.mkdir(parents=True, exist_ok=True)
    fichero.write_text(json.dumps(limpio, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return limpio


# ─────────────────────────── avisos ───────────────────────────
# Mismas palabras que usa el panel para colocar un envío en el diagrama; si
# cambian ahí, cambian aquí (docs/index.html, analizarEstado).
_INCIDENCIA = re.compile(
    r"incid|ausen|rehus|devuel|falt|error|retenid|aduan|direccion erronea|no localiz|"
    r"extravi|siniestr|anulad|parcial|mal clasificad")
_ENTREGA = re.compile(r"entregad|entrega realizada|entrega parcial")
_INICIAL = re.compile(r"pendiente de entregar|pendiente de recogida")


def _sin_acentos(texto: str) -> str:
    import unicodedata

    plano = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in plano if not unicodedata.combining(c)).lower()


def clase(evento: dict) -> str:
    """De qué clase es el aviso de este evento: la que se enciende y se apaga.

    Un envío recién grabado es «nuevo» aunque su estado diga otra cosa. Y de los
    cambios de estado se separan los dos que importan de verdad —una incidencia
    y la entrega—, para poder recibir solo esos y silenciar el goteo del resto.
    """
    if evento.get("tipo") == "nuevo":
        return "nuevo"
    texto = _sin_acentos((evento.get("campos") or {}).get("estado", "") or evento.get("detalle", ""))
    if _INCIDENCIA.search(texto):
        return "incidencia"
    if _ENTREGA.search(texto) and not _INICIAL.search(texto):
        return "entrega"
    return "actualizado"


def filtrar(eventos: list[dict], ajustes: dict | None = None) -> list[dict]:
    """Los eventos de los que sí hay que avisar, según lo elegido en el panel."""
    avisos = (ajustes or cargar())["avisos"]
    return [e for e in eventos if avisos.get(clase(e), True)]


def aviso_activo(clave: str, ajustes: dict | None = None) -> bool:
    return bool((ajustes or cargar())["avisos"].get(clave, True))


def canal_activo(canal: str, ajustes: dict | None = None) -> bool:
    return bool((ajustes or cargar())["canales"].get(canal, True))


# ─────────────────────────── línea de órdenes ───────────────────────────
def main(argv: list[str] | None = None) -> int:
    """`python -m monitor.ajustes --guardar` lee el JSON de la entrada estándar.

    Es lo que ejecuta el workflow «Guardar los ajustes» con lo que manda el
    panel: normaliza, escribe el fichero y devuelve 1 si lo recibido no tenía
    nada aprovechable, para que el commit no llegue a hacerse.
    """
    ap = argparse.ArgumentParser(description="Ajustes del monitor")
    ap.add_argument("--guardar", action="store_true",
                    help="lee un JSON de ajustes por la entrada estándar y lo escribe")
    ap.add_argument("--ver", action="store_true", help="enseña los ajustes en vigor")
    args = ap.parse_args(argv)

    if args.guardar:
        crudo = sys.stdin.read().strip()
        try:
            recibido = json.loads(crudo)
        except json.JSONDecodeError as e:
            print(f"Los ajustes recibidos no son JSON válido: {e}", file=sys.stderr)
            return 1
        if not isinstance(recibido, dict) or not (recibido.get("horarios") or recibido.get("avisos")):
            print("Los ajustes recibidos no traen ni horarios ni avisos; no se guarda nada.",
                  file=sys.stderr)
            return 1
        limpio = guardar(recibido)
        print(json.dumps(limpio, ensure_ascii=False, indent=1))
        return 0

    print(json.dumps(cargar(), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
