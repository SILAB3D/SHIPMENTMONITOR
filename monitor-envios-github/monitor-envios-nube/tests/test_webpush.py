"""El cifrado de los avisos push tiene que salir byte a byte como manda la norma.

Si esto falla, los móviles reciben basura y no muestran nada.
"""
from __future__ import annotations

import base64
import hmac
import json
import os
import struct

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils as asym_utils
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand

from monitor import webpush as wp


# ─────────── el lado del navegador, escrito aquí para poder comprobar ───────────
def descifrar(cuerpo: bytes, ua_privada: ec.EllipticCurvePrivateKey, auth: bytes) -> bytes:
    sal, _rs, largo_id = cuerpo[:16], struct.unpack("!I", cuerpo[16:20])[0], cuerpo[20]
    as_publica = cuerpo[21 : 21 + largo_id]
    cifrado = cuerpo[21 + largo_id :]

    ua_publica = ua_privada.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    compartido = ua_privada.exchange(
        ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(wp.CURVA, as_publica)
    )

    def hkdf(s: bytes, ikm: bytes, info: bytes, n: int) -> bytes:
        prk = hmac.new(s, ikm, "sha256").digest()
        return HKDFExpand(algorithm=hashes.SHA256(), length=n, info=info).derive(prk)

    ikm = hkdf(auth, compartido, b"WebPush: info\x00" + ua_publica + as_publica, 32)
    cek = hkdf(sal, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = hkdf(sal, ikm, b"Content-Encoding: nonce\x00", 12)
    claro = AESGCM(cek).decrypt(nonce, cifrado, None)
    return claro.rstrip(b"\x02")


# ─────────────────────────── pruebas ───────────────────────────
def test_ida_y_vuelta_del_cifrado():
    ua = ec.generate_private_key(wp.CURVA)

    p256dh = wp.b64u(
        ua.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
    )
    auth = os.urandom(16)
    mensaje = json.dumps({"titulo": "Envío 12345 actualizado", "detalle": "En reparto · Málaga"},
                         ensure_ascii=False).encode()

    cuerpo = wp.cifrar_payload(mensaje, p256dh, wp.b64u(auth))
    assert descifrar(cuerpo, ua, auth) == mensaje


def test_vector_de_ejemplo_del_rfc_8291():
    """RFC 8291, apéndice A: mismas claves y misma sal ⇒ mismo cuerpo cifrado."""
    texto = b"When I grow up, I want to be a watermelon"
    p256dh = "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
    auth = "BTBZMqHH6r4Tts7J_aSIgg"
    efimera = ec.derive_private_key(
        int.from_bytes(wp.deb64u("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"), wp.CURVA
    )
    sal = wp.deb64u("DGv6ra1nlYgDCS1FRnbzlw")
    esperado = (
        "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vC"
        "YLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXL"
        "WyouBWLVWGNWQexSgSxsj_Qulcy4a-fN"
    )
    cuerpo = wp.cifrar_payload(texto, p256dh, auth, efimera=efimera, sal=sal)
    assert wp.b64u(cuerpo) == esperado


def test_el_jwt_vapid_va_firmado_y_dirigido_al_servicio_correcto():
    privada, publica = wp.generar_claves()
    jwt, k = wp._jwt_vapid("https://fcm.googleapis.com/fcm/send/abc123", privada, "mailto:yo@ejemplo.es")
    assert k == publica

    cabecera_b64, reclamos_b64, firma_b64 = jwt.split(".")
    reclamos = json.loads(wp.deb64u(reclamos_b64))
    assert reclamos["aud"] == "https://fcm.googleapis.com"
    assert reclamos["sub"] == "mailto:yo@ejemplo.es"
    assert reclamos["exp"] > 0

    firma = wp.deb64u(firma_b64)
    der = asym_utils.encode_dss_signature(
        int.from_bytes(firma[:32], "big"), int.from_bytes(firma[32:], "big")
    )
    pub = ec.EllipticCurvePublicKey.from_encoded_point(wp.CURVA, wp.deb64u(publica))
    pub.verify(der, f"{cabecera_b64}.{reclamos_b64}".encode(), ec.ECDSA(hashes.SHA256()))


def test_base64url_sin_relleno_de_ida_y_vuelta():
    for n in range(1, 40):
        crudo = os.urandom(n)
        codificado = wp.b64u(crudo)
        assert "=" not in codificado
        assert wp.deb64u(codificado) == crudo
