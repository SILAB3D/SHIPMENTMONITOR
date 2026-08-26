"""Diagnostica por qué el panel no acepta tu CLAVE_PANEL.

Prueba tu contraseña y sus variantes «sucias» habituales contra el fichero de
datos publicado, y te dice exactamente cuál abre. De paso enseña lo que el
monitor dejó escrito dentro: cuándo fue la última comprobación, cuántos envíos
leyó y, si falló, el error del portal.

La contraseña se pide por teclado y no se ve al escribirla: no queda en el
historial de la consola ni se manda a ningún sitio. Todo pasa en tu ordenador.

    python herramientas/comprobar_clave.py
    python herramientas/comprobar_clave.py --url https://silab3d.github.io/SHIPMENTMONITOR/
    python herramientas/comprobar_clave.py --fichero docs/datos.json
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from monitor.cifrado import descifrar  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent


def variantes(pw: str) -> list[tuple[str, str]]:
    """Formas en que la misma contraseña puede haber acabado en el Secret."""
    vistas: dict[str, str] = {}
    for etiqueta, valor in [
        ("tal cual la has escrito", pw),
        ("sin espacios en los extremos", pw.strip()),
        ("con un salto de línea al final", pw + "\n"),
        ("con un salto de línea Windows al final", pw + "\r\n"),
        ("con un espacio al final", pw + " "),
        ("con un espacio al principio", " " + pw),
        ("con un espacio de teclado móvil al final", pw + " "),
    ]:
        vistas.setdefault(valor, etiqueta)
    return [(etiqueta, valor) for valor, etiqueta in vistas.items()]


def cargar_sobre(args) -> dict:
    if args.url:
        url = args.url.rstrip("/") + "/datos.json" if not args.url.endswith(".json") else args.url
        print(f"Descargando {url}…")
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    ruta = Path(args.fichero) if args.fichero else RAIZ / "docs" / "datos.json"
    if not ruta.exists():
        sys.exit(
            f"No encuentro {ruta}.\n"
            "Usa --url con la dirección de tu panel, o --fichero con la ruta del datos.json."
        )
    print(f"Leyendo {ruta}…")
    return json.loads(ruta.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Comprueba tu CLAVE_PANEL contra los datos publicados")
    ap.add_argument("--url", help="dirección del panel publicado (GitHub Pages)")
    ap.add_argument("--fichero", help="ruta a un datos.json local")
    ap.add_argument("--clave", help="la contraseña, en vez de teclearla "
                                    "(cuidado: queda en el historial de la consola)")
    args = ap.parse_args()

    sobre = cargar_sobre(args)
    if "datos" not in sobre:
        print("\nEste fichero NO está cifrado (es un volcado de demostración en claro).")
        print("Si es el que sirve tu panel, bórralo: el workflow generará uno de verdad.")
        return 1

    pw = args.clave or getpass.getpass("\nEscribe tu CLAVE_PANEL (no se verá al teclearla): ")
    if not pw:
        return 2

    print()
    acertada = None
    for etiqueta, valor in variantes(pw):
        try:
            datos = descifrar(sobre, valor)
        except Exception:  # noqa: BLE001
            print(f"  ✗ {etiqueta}")
            continue
        print(f"  ✓ {etiqueta}   ← ESTA ES")
        acertada = (etiqueta, valor, datos)
        break

    if not acertada:
        print(
            "\nNinguna variante abre el fichero. Entonces el Secret CLAVE_PANEL del\n"
            "repositorio no es esta contraseña: se cambió después de generar el fichero,\n"
            "o el que escribes no es el mismo. Arréglalo de una de estas dos formas:\n"
            "  · pon en el Secret la contraseña con la que se cifró, o\n"
            "  · borra docs/datos.json del repositorio y deja que el monitor empiece\n"
            "    de cero con la contraseña nueva (pierdes el historial, nada más)."
        )
        return 1

    etiqueta, _, datos = acertada
    if etiqueta != "tal cual la has escrito":
        print(
            "\n⚠  Tu contraseña es correcta, pero en el Secret se coló algo invisible\n"
            f"   ({etiqueta}). Por eso el panel la rechazaba.\n"
            "   Arréglalo: Settings → Secrets → CLAVE_PANEL → Update, borra el contenido\n"
            "   entero y escríbela de nuevo sin pulsar Intro al final."
        )

    meta = datos.get("meta") or {}
    envios = datos.get("envios") or {}
    print("\n─── lo que hay guardado dentro ───")
    print(f"  última comprobación : {meta.get('ultima_comprobacion') or '—'}")
    print(f"  envíos conocidos    : {len(envios)}")
    print(f"  envíos leídos       : {meta.get('envios_leidos', '—')}")
    print(f"  eventos guardados   : {len(datos.get('eventos') or [])}")
    canales = [k for k, v in (meta.get("canales") or {}).items() if v]
    print(f"  avisos activos      : {', '.join(canales) or 'ninguno todavía'}")
    if meta.get("error"):
        print("\n  ⚠  LA ÚLTIMA COMPROBACIÓN FALLÓ. El portal dijo:\n")
        for linea in str(meta["error"]).splitlines():
            print(f"     {linea}")
    else:
        print("\n  La última comprobación salió bien.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
