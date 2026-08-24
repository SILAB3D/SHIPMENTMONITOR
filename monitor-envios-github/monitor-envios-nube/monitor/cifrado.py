"""Cifrado del fichero de datos.

El repositorio es público (para que GitHub Pages y Actions salgan gratis), así
que los datos de los envíos nunca se guardan en claro: se cifran con una
contraseña que solo conoces tú (Secret `CLAVE_PANEL`) y se descifran en el
navegador con WebCrypto al entrar en el panel.

Formato del sobre, pensado para poder abrirse desde JavaScript sin librerías:

    {"v":1, "kdf":"PBKDF2-SHA256", "iter":200000,
     "salt":"<base64>", "iv":"<base64>", "datos":"<base64 AES-GCM>"}
"""
from __future__ import annotations

import base64
import json
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERACIONES = 200_000


def _clave(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERACIONES)
    return kdf.derive(password.encode("utf-8"))


def _b64(datos: bytes) -> str:
    return base64.b64encode(datos).decode()


def cifrar(objeto, password: str) -> dict:
    salt, iv = os.urandom(16), os.urandom(12)
    texto = json.dumps(objeto, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    cifrado = AESGCM(_clave(password, salt)).encrypt(iv, texto, None)
    return {
        "v": 1,
        "kdf": "PBKDF2-SHA256",
        "iter": ITERACIONES,
        "salt": _b64(salt),
        "iv": _b64(iv),
        "datos": _b64(cifrado),
    }


def descifrar(sobre: dict, password: str):
    salt = base64.b64decode(sobre["salt"])
    iv = base64.b64decode(sobre["iv"])
    cifrado = base64.b64decode(sobre["datos"])
    claro = AESGCM(_clave(password, salt)).decrypt(iv, cifrado, None)
    return json.loads(claro.decode("utf-8"))
