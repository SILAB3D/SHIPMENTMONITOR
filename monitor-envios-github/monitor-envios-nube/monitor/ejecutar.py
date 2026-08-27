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


def probar_avisos() -> int:
    """Manda un aviso de prueba por CADA canal configurado y dice cómo ha ido.

    Es la única forma de saber que Telegram o el correo siguen funcionando sin
    esperar a que cambie un envío de verdad. Sale 0 solo si todos los canales
    configurados han entregado; si no hay ninguno, sale 2, porque un monitor sin
    avisos no sirve de nada.
    """
    canales = config.canales()
    activos = [c for c, ok in canales.items() if ok]
    log.info("canales configurados: %s", ", ".join(activos) or "ninguno")

    if not activos:
        log.error(
            "no hay ningún canal de avisos configurado. Para el push: activa los avisos en el "
            "panel y pega el texto en el Secret PUSH_SUSCRIPCIONES (hace falta también "
            "VAPID_PRIVADA). Para Telegram: TELEGRAM_TOKEN y TELEGRAM_CHAT_ID. Para el correo: "
            "SMTP_HOST y EMAIL_DESTINO."
        )
        return 2

    titulo = "✅ Los avisos funcionan"
    cuerpo = "Este es un aviso de prueba del monitor de envíos. Si lo estás leyendo, este canal está bien."
    resultado: dict[str, str] = {}

    if canales["push"]:
        log.info("enviando push de prueba a %d dispositivo(s)…", len(config.suscripciones()))
        notificar._intentar("push", lambda: notificar._push(
            {"titulo": titulo, "cuerpo": cuerpo, "etiqueta": "prueba"}), resultado)
    if canales["telegram"]:
        notificar._intentar("telegram", lambda: notificar._telegram(f"{titulo}\n{cuerpo}"), resultado)
    if canales["email"]:
        notificar._intentar("email", lambda: notificar._email(titulo, cuerpo), resultado)

    for canal, como in resultado.items():
        (log.info if como == "ok" else log.error)("  %s → %s", canal, como)

    if resultado.get("telegram", "").startswith("error"):
        _pistas_telegram()

    return 0 if all(v == "ok" for v in resultado.values()) else 1


def _pistas_telegram() -> None:
    """Cuando Telegram falla, decir cuál es el TELEGRAM_CHAT_ID que sí vale."""
    chats = notificar.chats_de_telegram()
    if not chats:
        log.error(
            "Telegram no tiene ninguna conversación registrada con este bot. Abre Telegram, "
            "busca tu bot, pulsa «Iniciar» (/start), escríbele cualquier cosa y vuelve a lanzar "
            "esta prueba: entonces podré decirte el TELEGRAM_CHAT_ID correcto."
        )
        return
    log.error("Estos son los chats que han hablado con el bot; el TELEGRAM_CHAT_ID es uno de ellos:")
    for chat in chats:
        log.error("  · %s  (%s%s)", chat["id"], chat["tipo"], f", {chat['nombre']}" if chat["nombre"] else "")
    log.error("Cópialo en el Secret TELEGRAM_CHAT_ID del repositorio y repite la prueba.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Una comprobación del portal de envíos")
    ap.add_argument("--demo", action="store_true", help="usa datos ficticios en lugar del portal")
    ap.add_argument("--semilla", type=int, default=0, help="variante de los datos de demostración")
    ap.add_argument("--sin-avisos", action="store_true", help="no envía ningún aviso")
    ap.add_argument("--probar-avisos", "--probar-push", dest="probar_avisos", action="store_true",
                    help="manda un aviso de prueba por cada canal configurado y termina")
    args = ap.parse_args()

    if args.probar_avisos:
        return probar_avisos()

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
