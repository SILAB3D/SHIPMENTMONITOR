"""Un salto de línea invisible al final del Secret CLAVE_PANEL hacía que el
panel rechazara la contraseña correcta. Aquí se fija ese comportamiento."""
from __future__ import annotations

import importlib
import json

import pytest

from monitor import config as config_modulo
from monitor.cifrado import cifrar, descifrar


@pytest.fixture(autouse=True)
def _restaurar():
    yield
    importlib.reload(config_modulo)


def recargar(monkeypatch, valor: str):
    monkeypatch.setenv("CLAVE_PANEL", valor)
    cfg = importlib.reload(config_modulo)
    import monitor.estado as estado_modulo

    return cfg, importlib.reload(estado_modulo)


@pytest.mark.parametrize("sucia", ["secreta\n", "secreta\r\n", " secreta ", "secreta  ", "\tsecreta"])
def test_la_clave_se_recorta_venga_como_venga(monkeypatch, sucia):
    cfg, _ = recargar(monkeypatch, sucia)
    assert cfg.CLAVE_PANEL == "secreta"
    assert cfg.CLAVE_PANEL_CRUDA == sucia


def test_el_panel_abre_lo_que_cifra_el_workflow(monkeypatch, tmp_path):
    """Lo que se escribe con el Secret sucio se abre con lo que el usuario teclea."""
    cfg, estado = recargar(monkeypatch, "secreta\n")
    fichero = tmp_path / "datos.json"
    estado.guardar({"version": 1, "envios": {"A1": {}}, "eventos": [], "meta": {}}, ruta=fichero)

    sobre = json.loads(fichero.read_text(encoding="utf-8"))
    assert descifrar(sobre, "secreta")["envios"] == {"A1": {}}      # lo que teclea el usuario


def test_un_fichero_antiguo_cifrado_con_la_clave_sucia_sigue_abriendo(monkeypatch, tmp_path):
    """Compatibilidad: los datos que ya estaban publicados no se pierden."""
    fichero = tmp_path / "datos.json"
    antiguo = {"version": 1, "envios": {"VIEJO": {}}, "eventos": [], "meta": {}}
    fichero.write_text(json.dumps(cifrar(antiguo, "secreta\n")), encoding="utf-8")

    cfg, estado = recargar(monkeypatch, "secreta\n")
    assert estado.cargar(ruta=fichero)["envios"] == {"VIEJO": {}}


def test_al_reguardarlo_queda_ya_con_la_clave_limpia(monkeypatch, tmp_path):
    """El arreglo se aplica solo en la siguiente pasada del monitor."""
    fichero = tmp_path / "datos.json"
    fichero.write_text(json.dumps(cifrar({"envios": {"VIEJO": {}}}, "secreta\n")), encoding="utf-8")

    cfg, estado = recargar(monkeypatch, "secreta\n")
    recuperado = estado.cargar(ruta=fichero)
    estado.guardar(recuperado, ruta=fichero)

    sobre = json.loads(fichero.read_text(encoding="utf-8"))
    assert descifrar(sobre, "secreta")["envios"] == {"VIEJO": {}}   # ya abre con la limpia


def test_una_clave_de_verdad_distinta_sigue_fallando(monkeypatch, tmp_path):
    """El recorte no puede convertirse en un coladero."""
    fichero = tmp_path / "datos.json"
    fichero.write_text(json.dumps(cifrar({"envios": {}}, "la-buena")), encoding="utf-8")

    cfg, estado = recargar(monkeypatch, "otra-distinta")
    with pytest.raises(RuntimeError, match="No se pudo descifrar"):
        estado.cargar(ruta=fichero)
