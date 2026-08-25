"""Web Push: avisos que llegan al móvil sin Telegram, sin email y sin servidor.

El navegador (la PWA) se suscribe al servicio de push de su propio fabricante
—FCM en Chrome/Android, Mozilla en Firefox, Apple en iOS/Safari— y devuelve una
«suscripción»: una URL secreta y dos claves. El workflow de GitHub Actions usa
esa suscripción para empujar el aviso directamente al dispositivo.

Todo se hace aquí a mano con `cryptography`, que ya era dependencia del
proyecto, para no añadir librerías nuevas al workflow:

  * RFC 8291 — cifrado del mensaje (aes128gcm sobre ECDH P-256 + HKDF).
  * RFC 8188 — empaquetado del cuerpo cifrado.
  * RFC 8292 — VAPID: un JWT ES256 que identifica a *este* monitor ante el
    servicio de push, para que nadie más pueda usar tus suscripciones.

Generar el par de claves VAPID (una sola vez en la vida del proyecto):

    python -m monitor.webpush --generar-claves
"""
from __future__ import annotations

import base64
import hmac
import json
import os
import struct
import time
import urllib.error
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils as asym_utils
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand

CURVA = ec.SECP256R1()
TTL_JWT = 12 * 3600          # validez del token VAPID; el máximo que admite la norma es 24 h
TTL_PUSH = 12 * 3600         # cuánto guarda el servicio el aviso si el móvil está apagado


# ─────────────────────────── base64url ───────────────────────────
def b64u(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).decode().rstrip("=")


def deb64u(texto: str) -> bytes:
    texto = texto.strip().replace("-", "+").replace("_", "/")
    return base64.b64decode(texto + "=" * (-len(texto) % 4))


# ─────────────────────────── claves ───────────────────────────
def generar_claves() -> tuple[str, str]:
    """Devuelve (privada_b64url, publica_b64url) para los Secrets VAPID."""
    priv = ec.generate_private_key(CURVA)
    privada = priv.private_numbers().private_value.to_bytes(32, "big")
    publica = priv.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return b64u(privada), b64u(publica)


def _cargar_privada(privada_b64u: str) -> ec.EllipticCurvePrivateKey:
    return ec.derive_private_key(int.from_bytes(deb64u(privada_b64u), "big"), CURVA)


def _publica_de(privada: ec.EllipticCurvePrivateKey) -> bytes:
    return privada.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )


# ─────────────────────────── VAPID (RFC 8292) ───────────────────────────
def _jwt_vapid(endpoint: str, privada_b64u: str, contacto: str) -> tuple[str, str]:
    privada = _cargar_privada(privada_b64u)
    partes = urllib.parse.urlsplit(endpoint)
    reclamos = {
        "aud": f"{partes.scheme}://{partes.netloc}",
        "exp": int(time.time()) + TTL_JWT,
        "sub": contacto,
    }
    cabecera = {"typ": "JWT", "alg": "ES256"}
    sin_firma = ".".join(
        b64u(json.dumps(o, separators=(",", ":")).encode()) for o in (cabecera, reclamos)
    )
    der = privada.sign(sin_firma.encode(), ec.ECDSA(hashes.SHA256()))
    r, s = asym_utils.decode_dss_signature(der)          # el JWT quiere r||s en crudo, no DER
    firma = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return f"{sin_firma}.{b64u(firma)}", b64u(_publica_de(privada))


# ─────────────────────────── cifrado (RFC 8291) ───────────────────────────
def _hkdf(sal: bytes, ikm: bytes, info: bytes, largo: int) -> bytes:
    prk = hmac.new(sal, ikm, "sha256").digest()          # HKDF-Extract
    return HKDFExpand(algorithm=hashes.SHA256(), length=largo, info=info).derive(prk)


def cifrar_payload(texto: bytes, p256dh_b64u: str, auth_b64u: str,
                   efimera: ec.EllipticCurvePrivateKey | None = None,
                   sal: bytes | None = None) -> bytes:
    """Devuelve el cuerpo aes128gcm listo para enviar al endpoint.

    `efimera` y `sal` solo se fijan desde las pruebas, para poder comparar el
    resultado con el vector de ejemplo del RFC 8291.
    """
    ua_publica_bytes = deb64u(p256dh_b64u)
    secreto_auth = deb64u(auth_b64u)
    ua_publica = ec.EllipticCurvePublicKey.from_encoded_point(CURVA, ua_publica_bytes)

    efimera = efimera or ec.generate_private_key(CURVA)
    as_publica = _publica_de(efimera)
    compartido = efimera.exchange(ec.ECDH(), ua_publica)

    # Primer HKDF: mezcla el secreto ECDH con el «auth» de la suscripción.
    info_clave = b"WebPush: info\x00" + ua_publica_bytes + as_publica
    ikm = _hkdf(secreto_auth, compartido, info_clave, 32)

    sal = sal or os.urandom(16)
    cek = _hkdf(sal, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(sal, ikm, b"Content-Encoding: nonce\x00", 12)

    # 0x02 marca «último registro»: mandamos siempre el mensaje en uno solo.
    cifrado = AESGCM(cek).encrypt(nonce, texto + b"\x02", None)
    cabecera = sal + struct.pack("!IB", 4096, len(as_publica)) + as_publica
    return cabecera + cifrado


# ─────────────────────────── envío ───────────────────────────
class CaducadaError(Exception):
    """El servicio de push dice que esa suscripción ya no existe (404 / 410)."""


def enviar(suscripcion: dict, mensaje: dict, privada_b64u: str, contacto: str,
           urgencia: str = "high", timeout: int = 25) -> None:
    """Empuja un aviso a un dispositivo. `mensaje` viaja cifrado de punta a punta."""
    endpoint = suscripcion["endpoint"]
    claves = suscripcion.get("keys") or {}
    cuerpo = cifrar_payload(
        json.dumps(mensaje, ensure_ascii=False).encode("utf-8"), claves["p256dh"], claves["auth"]
    )
    jwt, publica = _jwt_vapid(endpoint, privada_b64u, contacto)
    peticion = urllib.request.Request(
        endpoint,
        data=cuerpo,
        method="POST",
        headers={
            "Authorization": f"vapid t={jwt}, k={publica}",
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(cuerpo)),
            "TTL": str(TTL_PUSH),
            "Urgency": urgencia,
        },
    )
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as r:
            r.read()
    except urllib.error.HTTPError as e:
        detalle = ""
        try:
            detalle = e.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001
            pass
        if e.code in (404, 410):
            raise CaducadaError(f"suscripción caducada ({e.code}) {detalle}".strip()) from e
        raise RuntimeError(f"el servicio de push respondió {e.code}: {detalle}") from e


def _cli() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Utilidades de Web Push")
    ap.add_argument("--generar-claves", action="store_true", help="crea un par VAPID nuevo")
    args = ap.parse_args()
    if args.generar_claves:
        privada, publica = generar_claves()
        print("VAPID_PRIVADA (Secret del repositorio, no la enseñes a nadie):")
        print(f"  {privada}\n")
        print("VAPID_PUBLICA (va en docs/push-config.js, es pública):")
        print(f"  {publica}")
    else:
        ap.print_help()


if __name__ == "__main__":
    _cli()
