"""Avisos desde el workflow: Telegram y email. Ninguno de los dos cuesta nada."""
from __future__ import annotations

import logging
import smtplib
import urllib.parse
import urllib.request
from email.message import EmailMessage

from monitor import config

log = logging.getLogger("avisos")


def texto(eventos: list[dict]) -> str:
    lineas = []
    for e in eventos:
        marca = "🆕" if e["tipo"] == "nuevo" else "🔄"
        lineas.append(f"{marca} {e['titulo']}\n   {e['detalle']}")
    return "\n".join(lineas)


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


def avisar(eventos: list[dict]) -> dict[str, str]:
    if not eventos:
        return {}
    cuerpo = texto(eventos)
    asunto = eventos[0]["titulo"] if len(eventos) == 1 else f"{len(eventos)} novedades en tus envíos"
    resultado = {}
    for nombre, fn in (("telegram", lambda: _telegram(cuerpo)), ("email", lambda: _email(asunto, cuerpo))):
        try:
            fn()
            resultado[nombre] = "ok"
        except Exception as e:  # noqa: BLE001
            log.warning("fallo enviando por %s: %s", nombre, e)
            resultado[nombre] = f"error: {e}"
    return resultado


def avisar_error(mensaje: str) -> None:
    """Avisa de que el monitor no ha podido leer el portal."""
    for fn in (lambda: _telegram(f"⚠️ El monitor de envíos no pudo consultar el portal:\n{mensaje}"),
               lambda: _email("⚠️ Monitor de envíos: fallo al consultar", mensaje)):
        try:
            fn()
        except Exception:  # noqa: BLE001
            pass
