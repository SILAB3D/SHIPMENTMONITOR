"""Extracción de la tabla de envíos del HTML del portal.

El portal es un PHP clásico y su maquetación puede cambiar, así que aquí no se
usan selectores rígidos: se buscan todas las tablas, se elige la que más pinta
tiene de ser el listado y se mapean sus cabeceras a nombres canónicos por
palabras clave. Si algún día cambian los títulos de las columnas, basta con
añadir sinónimos en SINONIMOS.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable

from bs4 import BeautifulSoup

# Nombre canónico -> palabras clave que pueden aparecer en la cabecera
SINONIMOS: dict[str, tuple[str, ...]] = {
    "referencia": ("albaran", "n albaran", "envio", "expedicion", "referencia", "ref", "numero", "n envio"),
    "fecha": ("fecha", "f envio", "f grabacion", "alta"),
    "estado": ("estado", "situacion", "status", "ultimo estado"),
    "destinatario": ("destinatario", "consignatario", "nombre", "cliente destino"),
    "localidad": ("localidad", "poblacion", "destino", "ciudad", "plaza"),
    "provincia": ("provincia",),
    "cp": ("cp", "codigo postal", "c postal"),
    "bultos": ("bultos", "n bultos", "paquetes"),
    "kilos": ("kilos", "peso", "kg"),
    "reembolso": ("reembolso", "rembolso"),
    "observaciones": ("observaciones", "incidencia", "notas", "obs"),
    "entrega": ("entrega", "fecha entrega", "f entrega", "receptor"),
}

# Estas columnas, si cambian, se consideran "actualización" del envío
CAMPOS_VIGILADOS = ("estado", "fecha_estado", "entrega", "observaciones", "localidad", "bultos", "kilos")


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9 ]+", " ", texto.lower())
    return re.sub(r"\s+", " ", texto).strip()


def _texto(celda) -> str:
    return re.sub(r"\s+", " ", celda.get_text(" ", strip=True)).strip()


def _canonico(cabecera: str) -> str | None:
    n = normalizar(cabecera)
    if not n:
        return None
    mejor, mejor_long = None, 0
    for canon, claves in SINONIMOS.items():
        for clave in claves:
            if clave == n or re.search(rf"\b{re.escape(clave)}\b", n):
                if len(clave) > mejor_long:
                    mejor, mejor_long = canon, len(clave)
    return mejor


def extraer_tablas(html: str | Iterable[str]) -> list[list[list[str]]]:
    """Tablas de un documento, o de varios (el portal reparte la pantalla en frames).

    Cada documento se parsea por separado a propósito: lxml solo conserva el
    primer `<html>` de una cadena, así que concatenar el HTML de los frames
    perdería justo el que trae el listado.
    """
    documentos = [html] if isinstance(html, str) else list(html)
    tablas = []
    for documento in documentos:
        sopa = BeautifulSoup(documento, "lxml")
        for tabla in sopa.find_all("table"):
            # ignorar tablas que solo sirven de maquetación y contienen otras tablas
            if tabla.find("table"):
                continue
            filas = []
            for tr in tabla.find_all("tr"):
                celdas = [_texto(td) for td in tr.find_all(["td", "th"])]
                if any(c for c in celdas):
                    filas.append(celdas)
            if filas:
                tablas.append(filas)
    return tablas


def _puntuar(filas: list[list[str]]) -> int:
    if len(filas) < 2:
        return 0
    ancho = max(len(f) for f in filas)
    if ancho < 3:
        return 0
    reconocidas = sum(1 for c in filas[0] if _canonico(c))
    return reconocidas * 100 + len(filas) * ancho


def elegir_tabla(tablas: list[list[list[str]]]) -> list[list[str]] | None:
    candidatas = [(t, _puntuar(t)) for t in tablas]
    candidatas = [(t, p) for t, p in candidatas if p > 0]
    if not candidatas:
        return None
    return max(candidatas, key=lambda x: x[1])[0]


def parse_envios(html: str | Iterable[str]) -> list[dict]:
    """Devuelve una lista de envíos: {'id', 'hash', 'campos': {...}, 'crudo': [...]}.

    Acepta un HTML o el de varios frames; se queda con la tabla que más pinta
    tenga de ser el listado, venga del documento que venga.
    """
    tabla = elegir_tabla(extraer_tablas(html))
    if not tabla:
        return []

    cabeceras = tabla[0]
    mapa: dict[int, str] = {}
    for i, cab in enumerate(cabeceras):
        canon = _canonico(cab)
        if canon and canon not in mapa.values():
            mapa[i] = canon

    envios: list[dict] = []
    for fila in tabla[1:]:
        if not any(c.strip() for c in fila):
            continue
        campos: dict[str, str] = {}
        for i, valor in enumerate(fila):
            clave = mapa.get(i)
            if clave:
                campos[clave] = valor
            elif i < len(cabeceras) and cabeceras[i].strip():
                campos.setdefault(f"extra:{cabeceras[i].strip()}", valor)

        ref = campos.get("referencia", "").strip()
        if not ref:
            # sin columna de referencia identificable: usamos la fila entera
            ref = hashlib.sha1("|".join(fila).encode()).hexdigest()[:12]
        # descartar filas de totales / pies de tabla
        if normalizar(ref) in ("total", "totales", ""):
            continue

        envios.append(
            {
                "id": ref,
                "campos": campos,
                "crudo": fila,
                "hash": hashlib.sha1("|".join(fila).encode()).hexdigest(),
            }
        )
    return envios


def diferencias(antes: dict, ahora: dict) -> list[tuple[str, str, str]]:
    """Cambios en los campos vigilados: [(campo, valor_antes, valor_ahora)]."""
    cambios = []
    for campo in CAMPOS_VIGILADOS:
        a, b = (antes.get(campo) or "").strip(), (ahora.get(campo) or "").strip()
        if a != b and (a or b):
            cambios.append((campo, a, b))
    return cambios
