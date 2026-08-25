"""Genera los PNG del icono a partir del mismo dibujo que docs/icono.svg.

Android necesita PNG de verdad: el SVG le vale para el atajo, pero no para el
icono ni el «badge» de las notificaciones. Se dibuja aquí a mano, con zlib y
nada más, para no meter Pillow ni cairosvg en el proyecto.

    python herramientas/generar_iconos.py
"""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
MUESTREO = 4                       # antialiasing por supermuestreo

NARANJA_CLARO = (0xFB, 0x92, 0x3C)
NARANJA = (0xEA, 0x58, 0x0C)
BLANCO = (0xFF, 0xFF, 0xFF)

# El dibujo se define sobre un lienzo de 192×192, igual que el SVG.
LADO_BASE = 192.0
RADIO_ESQUINA = 42.0
GROSOR = 10.0

HEXAGONO = [(96, 42), (150, 68), (150, 124), (96, 150), (42, 124), (42, 68)]
LINEAS = [[(42, 68), (96, 94), (150, 68)], [(96, 94), (96, 150)]]
INSIGNIA = ((150.0, 50.0), 17.0, 7.0)


def _dist_segmento(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    vx, vy = bx - ax, by - ay
    largo2 = vx * vx + vy * vy
    t = 0.0 if largo2 == 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / largo2))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def _segmentos() -> list[tuple[float, float, float, float]]:
    segs = [(HEXAGONO[i][0], HEXAGONO[i][1], HEXAGONO[(i + 1) % 6][0], HEXAGONO[(i + 1) % 6][1])
            for i in range(6)]
    for linea in LINEAS:
        segs += [(linea[i][0], linea[i][1], linea[i + 1][0], linea[i + 1][1])
                 for i in range(len(linea) - 1)]
    return segs


SEGMENTOS = _segmentos()


def _dentro_rect_redondeado(x: float, y: float, lado: float, radio: float) -> bool:
    cx = min(max(x, radio), lado - radio)
    cy = min(max(y, radio), lado - radio)
    return math.hypot(x - cx, y - cy) <= radio


def _color_en(x: float, y: float, lado: float, escala: float, desplazamiento: float,
              fondo_completo: bool) -> tuple[int, int, int, int]:
    """Color de un punto del lienzo final, en coordenadas de píxel."""
    if not (fondo_completo or _dentro_rect_redondeado(x, y, lado, RADIO_ESQUINA * lado / LADO_BASE)):
        return (0, 0, 0, 0)

    # Fondo: degradado diagonal, como el linearGradient del SVG.
    t = min(1.0, max(0.0, (x + y) / (2 * lado)))
    r, g, b = (int(round(a + (c - a) * t)) for a, c in zip(NARANJA_CLARO, NARANJA))

    # El dibujo va en coordenadas 0..192; lo llevamos a las del lienzo.
    dx = (x - desplazamiento) / escala
    dy = (y - desplazamiento) / escala

    cen, radio_ext, radio_int = INSIGNIA
    d_insignia = math.hypot(dx - cen[0], dy - cen[1])
    if d_insignia <= radio_int:
        return (*NARANJA, 255)
    if d_insignia <= radio_ext:
        return (*BLANCO, 255)

    if min(_dist_segmento(dx, dy, *s) for s in SEGMENTOS) <= GROSOR / 2:
        return (*BLANCO, 255)
    return (r, g, b, 255)


def dibujar(lado: int, margen: float = 0.0, fondo_completo: bool = True) -> bytes:
    """Devuelve las filas RGBA del icono. `margen` deja aire para los maskable."""
    escala = lado * (1 - 2 * margen) / LADO_BASE
    desplazamiento = lado * margen
    filas = bytearray()
    paso = 1.0 / MUESTREO
    for py in range(lado):
        filas.append(0)                                   # filtro PNG «None»
        for px in range(lado):
            acc = [0, 0, 0, 0]
            for sy in range(MUESTREO):
                for sx in range(MUESTREO):
                    c = _color_en(px + (sx + 0.5) * paso, py + (sy + 0.5) * paso,
                                  float(lado), escala, desplazamiento, fondo_completo)
                    for i in range(4):
                        acc[i] += c[i]
            n = MUESTREO * MUESTREO
            filas += bytes(v // n for v in acc)
    return bytes(filas)


def escribir_png(ruta: Path, lado: int, crudo: bytes) -> None:
    def trozo(tipo: bytes, datos: bytes) -> bytes:
        return (struct.pack("!I", len(datos)) + tipo + datos
                + struct.pack("!I", zlib.crc32(tipo + datos) & 0xFFFFFFFF))

    cabecera = struct.pack("!2I5B", lado, lado, 8, 6, 0, 0, 0)   # RGBA de 8 bits
    ruta.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + trozo(b"IHDR", cabecera)
        + trozo(b"IDAT", zlib.compress(crudo, 9))
        + trozo(b"IEND", b"")
    )
    print(f"  {ruta.name}  ({ruta.stat().st_size / 1024:.1f} kB)")


def main() -> None:
    print("Generando iconos en docs/…")
    for lado in (192, 512):
        escribir_png(DOCS / f"icono-{lado}.png", lado, dibujar(lado, fondo_completo=False))
    # Maskable: Android recorta hasta un 20% por cada lado, así que el dibujo se
    # encoge y el degradado ocupa todo el cuadrado, sin esquinas redondeadas.
    escribir_png(DOCS / "icono-maskable-512.png", 512,
                 dibujar(512, margen=0.14, fondo_completo=True))


if __name__ == "__main__":
    main()
