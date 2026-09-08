"""Cifra un secreto con la contraseña del panel, para poder publicarlo.

Sirve para el token que deja que el panel arranque la vigilancia por su cuenta.
El repositorio es público, así que el token no puede ir en claro: se guarda
cifrado con la MISMA contraseña que ya protege los datos de los envíos
(CLAVE_PANEL), y el navegador lo descifra al entrar, igual que hace con ellos.

    python herramientas/cifrar_secreto.py docs/disparo.json

Pide el secreto y la contraseña por teclado —no se pasan por la línea de
órdenes, que queda en el historial— y escribe el sobre cifrado.
"""
from __future__ import annotations

import getpass
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from monitor.cifrado import cifrar, descifrar  # noqa: E402


def main() -> int:
    destino = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/disparo.json")
    secreto = getpass.getpass("Token que se va a guardar: ").strip()
    if not secreto:
        print("No has escrito nada."); return 2
    clave = getpass.getpass("Contraseña del panel (CLAVE_PANEL): ").strip()
    if not clave:
        print("Hace falta la contraseña del panel."); return 2

    sobre = cifrar({"token": secreto}, clave)
    # Comprobación de ida y vuelta antes de escribir nada: más vale enterarse
    # aquí que cuando el panel no sepa abrirlo.
    assert descifrar(sobre, clave) == {"token": secreto}

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(sobre, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Escrito {destino} ({destino.stat().st_size} bytes). Ya se puede subir: va cifrado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
