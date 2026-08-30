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
    # el sobre lleva lo justo para poder abrirlo desde el navegador, más la
    # hora en claro que el workflow necesita para saber si toca comprobar
    assert set(sobre) == {"v", "kdf", "iter", "ts", "salt", "iv", "datos"}


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


def test_el_sobre_lleva_la_hora_en_claro():
    """El workflow necesita saber cuándo fue la última comprobación SIN la clave.

    Es lo que le deja decidir si toca comprobar otra vez, y por eso no puede ir
    dentro de lo cifrado. No descubre nada que no se vea ya en la fecha de los
    commits.
    """
    import re
    from datetime import datetime, timezone

    sobre = cifrar({"algo": 1}, "clave")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", sobre["ts"])
    momento = datetime.strptime(sobre["ts"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert abs((datetime.now(timezone.utc) - momento).total_seconds()) < 120
    # y el sobre sigue abriéndose igual
    assert descifrar(sobre, "clave") == {"algo": 1}
