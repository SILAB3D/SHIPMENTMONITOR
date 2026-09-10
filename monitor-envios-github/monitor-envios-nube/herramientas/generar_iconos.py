"""Genera los PNG del icono a partir del mismo dibujo que docs/icono.svg.

La marca es un tubo de muestra: tapón, cuerpo y el líquido a media altura, que
es lo que de verdad viaja en estos envíos. Arriba a la derecha, el punto de
vigilancia: el monitor mirando. Se lee igual a 512 px que a 96, que es lo que
Android deja para el «badge» de las notificaciones.

Android necesita PNG de verdad: el SVG le vale para el atajo, pero no para el
icono ni el badge. Se dibuja aquí a mano, con zlib y nada más, para no meter
Pillow ni cairosvg en el proyecto.

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
GROSOR = 9.0

CX = 88.0                          # eje del tubo
RADIO_CUERPO = 19.0                # media anchura del cuerpo (al eje del trazo)
TOPE = 60.0                        # donde arrancan las paredes, bajo el tapón
HOMBRO = 138.0                     # centro del arco del fondo
HUECO = RADIO_CUERPO - GROSOR / 2             # media anchura por dentro del vidrio
HOLGURA = 3.0                                 # aire entre el vidrio y el líquido
RADIO_LIQUIDO = HUECO - HOLGURA

TAPON = (61.0, 34.0, 115.0, 56.0, 7.0)        # x0, y0, x1, y1, radio
NIVEL = 104.0                                 # altura de la superficie del líquido
BURBUJAS = ((82.0, 121.0, 3.0), (94.0, 132.0, 2.4))
PUNTO = ((152.0, 54.0), 15.0, 6.0)            # centro, radio exterior, hueco

TINTA, VACIO = "tinta", "vacio"


def _dist_contorno(x: float, y: float) -> float:
    """Distancia al contorno del tubo, exacta: dos paredes y un semicírculo.

    Se resuelve con fórmula en vez de trocear el arco en segmentos porque esto
    se evalúa 16 veces por píxel y el icono grande tiene 512×512.
    """
    if y > HOMBRO:                                     # el fondo redondo
        return abs(math.hypot(x - CX, y - HOMBRO) - RADIO_CUERPO)
    if y >= TOPE:                                      # las paredes
        return min(abs(x - (CX - RADIO_CUERPO)), abs(x - (CX + RADIO_CUERPO)))
    return min(math.hypot(x - (CX - RADIO_CUERPO), y - TOPE),   # los extremos
               math.hypot(x - (CX + RADIO_CUERPO), y - TOPE))


def _dentro_rect_redondeado(x: float, y: float, lado: float, radio: float) -> bool:
    cx = min(max(x, radio), lado - radio)
    cy = min(max(y, radio), lado - radio)
    return math.hypot(x - cx, y - cy) <= radio


def _dentro_rr(x: float, y: float, x0: float, y0: float, x1: float, y1: float,
               radio: float) -> bool:
    cx = min(max(x, x0 + radio), x1 - radio)
    cy = min(max(y, y0 + radio), y1 - radio)
    return math.hypot(x - cx, y - cy) <= radio


def _en_el_liquido(x: float, y: float) -> bool:
    """La muestra: de la superficie hacia abajo, sin llegar a tocar el vidrio."""
    if y < NIVEL or abs(x - CX) > RADIO_LIQUIDO:
        return False
    if y <= HOMBRO:
        return True
    return math.hypot(x - CX, y - HOMBRO) <= RADIO_LIQUIDO


def _que_hay(x: float, y: float) -> str | None:
    """Qué toca pintar en ese punto del dibujo (coordenadas 0..192)."""
    centro, fuera, dentro = PUNTO
    d = math.hypot(x - centro[0], y - centro[1])
    if d <= dentro:
        return VACIO
    if d <= fuera:
        return TINTA

    if _dentro_rr(x, y, *TAPON):
        return TINTA

    for bx, by, br in BURBUJAS:                        # las burbujas, antes que el líquido
        if math.hypot(x - bx, y - by) <= br:
            return VACIO

    if _en_el_liquido(x, y):
        return TINTA

    if _dist_contorno(x, y) <= GROSOR / 2:
        return TINTA
    return None


def _color_en(x: float, y: float, lado: float, escala: float, desplazamiento: float,
              fondo_completo: bool) -> tuple[int, int, int, int]:
    """Color de un punto del lienzo final, en coordenadas de píxel."""
    if not (fondo_completo or _dentro_rect_redondeado(x, y, lado, RADIO_ESQUINA * lado / LADO_BASE)):
        return (0, 0, 0, 0)

    # Fondo: degradado diagonal, como el linearGradient del SVG.
    t = min(1.0, max(0.0, (x + y) / (2 * lado)))
    fondo = tuple(int(round(a + (c - a) * t)) for a, c in zip(NARANJA_CLARO, NARANJA))

    que = _que_hay((x - desplazamiento) / escala, (y - desplazamiento) / escala)
    if que == TINTA:
        return (*BLANCO, 255)
    return (*fondo, 255)          # VACIO y «nada» enseñan el degradado


def _color_suelto(x: float, y: float, escala: float, desplazamiento: float,
                  tinta: tuple[int, int, int]) -> tuple[int, int, int, int]:
    """Igual que `_color_en`, pero sin fondo: solo el dibujo, en un color.

    Es lo que necesitan las notificaciones del móvil. Android pinta el icono
    sobre la sombra de notificación —clara u oscura según el tema— y un cuadrado
    naranja ahí queda como un pegote; con el fondo transparente se integra. Para
    el «badge» además da igual el color: Android se queda solo con la silueta
    (el canal alfa) y la tiñe él.
    """
    que = _que_hay((x - desplazamiento) / escala, (y - desplazamiento) / escala)
    return (*tinta, 255) if que == TINTA else (0, 0, 0, 0)


def dibujar(lado: int, margen: float = 0.0, fondo_completo: bool = True,
            sin_fondo: tuple[int, int, int] | None = None) -> bytes:
    """Devuelve las filas RGBA del icono. `margen` deja aire para los maskable.

    Con `sin_fondo` se pinta solo el dibujo, en ese color y sobre transparente.
    """
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
                    xx, yy = px + (sx + 0.5) * paso, py + (sy + 0.5) * paso
                    if sin_fondo is None:
                        c = _color_en(xx, yy, float(lado), escala, desplazamiento, fondo_completo)
                    else:
                        c = _color_suelto(xx, yy, escala, desplazamiento, sin_fondo)
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

    # Notificaciones del móvil: sin fondo. El icono va en naranja, que se lee
    # igual de bien en tema claro y en oscuro; el badge en blanco, porque
    # Android solo mira la silueta.
    escribir_png(DOCS / "icono-notificacion-192.png", 192,
                 dibujar(192, margen=0.06, sin_fondo=NARANJA))
    escribir_png(DOCS / "icono-badge-96.png", 96,
                 dibujar(96, margen=0.06, sin_fondo=BLANCO))


if __name__ == "__main__":
    main()
