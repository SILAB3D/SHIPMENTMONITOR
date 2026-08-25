"""Entrada del monitor: una pasada completa. Es lo que ejecuta GitHub Actions.

    python -m monitor.ejecutar            # consulta real (usa los Secrets)
    python -m monitor.ejecutar --demo     # datos ficticios, para ver el panel
    python -m monitor.ejecutar --sin-avisos
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from monitor import config, estado as est, notificar

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("monitor")


def probar_push() -> int:
    """Comprueba de punta a punta que los avisos llegan al móvil."""
    subs = config.suscripciones()
    if not config.VAPID_PRIVADA:
        log.error("falta el Secret VAPID_PRIVADA (genera el par con «python -m monitor.webpush --generar-claves»)")
        return 2
    if not subs:
        log.error("el Secret PUSH_SUSCRIPCIONES está vacío o no tiene ninguna suscripción válida; "
                  "actívalos en el panel y pega el texto que te da")
        return 2

    log.info("enviando aviso de prueba a %d dispositivo(s)…", len(subs))
    resultado = {}
    notificar._intentar(
        "push",
        lambda: notificar._push({
            "titulo": "✅ Los avisos funcionan",
            "cuerpo": "Este es un aviso de prueba del monitor de envíos.",
            "etiqueta": "prueba",
        }),
        resultado,
    )
    log.info("resultado: %s", resultado)
    return 0 if resultado.get("push") == "ok" else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Una comprobación del portal de envíos")
    ap.add_argument("--demo", action="store_true", help="usa datos ficticios en lugar del portal")
    ap.add_argument("--semilla", type=int, default=0, help="variante de los datos de demostración")
    ap.add_argument("--sin-avisos", action="store_true", help="no envía ningún aviso")
    ap.add_argument("--probar-push", action="store_true",
                    help="manda un aviso de prueba a los dispositivos suscritos y termina")
    args = ap.parse_args()

    if args.probar_push:
        return probar_push()

    if not config.CLAVE_PANEL and not args.demo:
        log.error("Falta el Secret CLAVE_PANEL: sin él no se pueden cifrar los datos publicados")
        return 2

    estado = est.cargar()

    try:
        if args.demo:
            from monitor.demo import envios_demo

            envios = envios_demo(args.semilla)
        else:
            from monitor.scraper import obtener_envios

            envios = asyncio.run(obtener_envios())
    except Exception as e:  # noqa: BLE001
        log.error("no se pudo leer el portal: %s", e)
        est.sellar_meta(estado, error=str(e), envios_leidos=len(estado.get("envios", {})))
        est.guardar(estado)
        if not args.sin_avisos:
            notificar.avisar_error(str(e))
        return 1

    eventos = est.sincronizar(estado, envios)
    est.sellar_meta(estado, envios_leidos=len(envios))
    est.guardar(estado)

    log.info("%d envíos leídos, %d novedad(es)", len(envios), len(eventos))
    if eventos and not args.sin_avisos:
        log.info("avisos enviados: %s", notificar.avisar(eventos))
    for e in eventos:
        log.info("  %s · %s", e["titulo"], e["detalle"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
