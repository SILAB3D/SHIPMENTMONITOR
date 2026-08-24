"""El fichero publicado debe ir cifrado y poder abrirse solo con la contraseña."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from monitor import estado as est  # noqa: E402
from monitor.cifrado import cifrar, descifrar  # noqa: E402


def test_ida_y_vuelta():
    objeto = {"envios": {"0012345678": {"campos": {"estado": "EN REPARTO"}}}}
    sobre = cifrar(objeto, "contraseña larga")
    assert descifrar(sobre, "contraseña larga") == objeto
    # el sobre lleva lo justo para poder abrirlo desde el navegador
    assert set(sobre) == {"v", "kdf", "iter", "salt", "iv", "datos"}


def test_no_se_abre_con_otra_clave():
    sobre = cifrar({"a": 1}, "buena")
    with pytest.raises(Exception):
        descifrar(sobre, "mala")


def test_el_fichero_publicado_no_filtra_datos(tmp_path):
    ruta = tmp_path / "datos.json"
    estado = {"envios": {"ALB-99": {"campos": {"destinatario": "FARMACIA SOL"}}}, "eventos": [], "meta": {}}
    est.guardar(estado, ruta=ruta, password="clave-del-panel")

    crudo = ruta.read_text(encoding="utf-8")
    assert "FARMACIA SOL" not in crudo and "ALB-99" not in crudo
    assert json.loads(crudo)["kdf"] == "PBKDF2-SHA256"

    assert est.cargar(ruta=ruta, password="clave-del-panel") == estado
