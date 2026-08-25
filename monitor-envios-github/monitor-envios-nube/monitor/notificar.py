"""Avisos del monitor.

El canal principal es Web Push: el aviso sale de GitHub Actions y aterriza
directamente en el móvil, en la propia PWA, sin pasar por Telegram ni por el
correo. Telegram y email siguen aquí como refuerzo opcional: si no defines sus
Secrets, ni se intentan.
"""
from __future__ import annotations

import logging
import smtplib
import urllib.parse
import urllib.request
from email.message import EmailMessage

from monitor import config, webpush

log = logging.getLogger("avisos")


def texto(eventos: list[dict]) -> str:
    lineas = []
    for e in eventos:
        marca = "🆕" if e["tipo"] == "nuevo" else "🔄"
        lineas.append(f"{marca} {e['titulo']}\n   {e['detalle']}")
    return "\n".join(lineas)


# ─────────────────────────── push (canal principal) ───────────────────────────
def _mensaje_push(eventos: list[dict]) -> dict:
    """Lo que verá la notificación en la pantalla del móvil."""
    if len(eventos) == 1:
        e = eventos[0]
        return {
            "titulo": e["titulo"],
            "cuerpo": e["detalle"],
            "etiqueta": f"envio-{e['envio_id']}",
            "envio_id": e["envio_id"],
        }
    nuevos = sum(1 for e in eventos if e["tipo"] == "nuevo")
    cambios = len(eventos) - nuevos
    partes = []
    if nuevos:
        partes.append(f"{nuevos} envío{'s' if nuevos > 1 else ''} nuevo{'s' if nuevos > 1 else ''}")
    if cambios:
        partes.append(f"{cambios} cambio{'s' if cambios > 1 else ''} de estado")
    return {
        "titulo": f"{len(eventos)} novedades en tus envíos",
        "cuerpo": " y ".join(partes) + ":\n" + "\n".join(f"· {e['titulo']}" for e in eventos[:4]),
        "etiqueta": "resumen",
    }


def _push(mensaje: dict) -> None:
    subs = config.suscripciones()
    if not (config.VAPID_PRIVADA and subs):
        return
    caducadas, fallos, entregados = 0, [], 0
    for sub in subs:
        try:
            webpush.enviar(sub, mensaje, config.VAPID_PRIVADA, config.VAPID_CONTACTO)
            entregados += 1
        except webpush.CaducadaError as e:
            caducadas += 1
            log.warning(
                "una suscripción push ya no vale (%s). Vuelve a activar los avisos en el panel "
                "de ese dispositivo y pega el texto nuevo en el Secret PUSH_SUSCRIPCIONES.", e
            )
        except Exception as e:  # noqa: BLE001
            fallos.append(str(e))
            log.warning("fallo enviando push a %s…: %s", sub["endpoint"][:60], e)

    log.info("push: %d entregado(s), %d caducada(s), %d fallo(s)", entregados, caducadas, len(fallos))
    if not entregados and fallos:
        raise RuntimeError(fallos[0])
    if not entregados and caducadas:
        raise RuntimeError("todas las suscripciones push están caducadas")


# ─────────────────────────── refuerzos opcionales ───────────────────────────
def _telegram(mensaje: str) -> None:
    if not (config.TELEGRAM_TOKEN and config.TELEGRAM_CHAT_ID):
        return
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    datos = urllib.parse.urlencode(
        {"chat_id": config.TELEGRAM_CHAT_ID, "text": mensaje, "disable_web_page_preview": "true"}
    ).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=datos), timeout=25) as r:
        r.read()


def _email(asunto: str, mensaje: str) -> None:
    if not (config.SMTP_HOST and config.EMAIL_DESTINO):
        return
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = config.SMTP_USUARIO or config.EMAIL_DESTINO
    msg["To"] = config.EMAIL_DESTINO
    msg.set_content(mensaje)

    if config.SMTP_PUERTO == 465:
        servidor = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PUERTO, timeout=25)
    else:
        servidor = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PUERTO, timeout=25)
        servidor.starttls()
    with servidor:
        if config.SMTP_USUARIO:
            servidor.login(config.SMTP_USUARIO, config.SMTP_PASSWORD)
        servidor.send_message(msg)


# ─────────────────────────── fachada ───────────────────────────
def _intentar(nombre: str, fn, resultado: dict) -> None:
    try:
        fn()
        resultado[nombre] = "ok"
    except Exception as e:  # noqa: BLE001
        log.warning("fallo enviando por %s: %s", nombre, e)
        resultado[nombre] = f"error: {e}"


def avisar(eventos: list[dict]) -> dict[str, str]:
    if not eventos:
        return {}
    cuerpo = texto(eventos)
    asunto = eventos[0]["titulo"] if len(eventos) == 1 else f"{len(eventos)} novedades en tus envíos"
    resultado: dict[str, str] = {}
    if config.push_ok():
        _intentar("push", lambda: _push(_mensaje_push(eventos)), resultado)
    if config.TELEGRAM_TOKEN and config.TELEGRAM_CHAT_ID:
        _intentar("telegram", lambda: _telegram(cuerpo), resultado)
    if config.SMTP_HOST and config.EMAIL_DESTINO:
        _intentar("email", lambda: _email(asunto, cuerpo), resultado)
    if not resultado:
        log.warning("no hay ningún canal de avisos configurado: la novedad solo se verá en el panel")
    return resultado


def avisar_error(mensaje: str) -> None:
    """Avisa de que el monitor no ha podido leer el portal."""
    corto = mensaje.strip().splitlines()[0][:200] if mensaje.strip() else "motivo desconocido"
    for fn in (
        lambda: _push({"titulo": "⚠️ El monitor no pudo consultar el portal",
                       "cuerpo": corto, "etiqueta": "error", "urgencia": "normal"}),
        lambda: _telegram(f"⚠️ El monitor de envíos no pudo consultar el portal:\n{mensaje}"),
        lambda: _email("⚠️ Monitor de envíos: fallo al consultar", mensaje),
    ):
        try:
            fn()
        except Exception:  # noqa: BLE001
            pass
