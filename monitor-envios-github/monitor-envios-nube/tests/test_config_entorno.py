"""GitHub Actions define como cadena VACÍA las variables de repositorio que no
existen. Si el valor por defecto no se aplicara en ese caso, el monitor
intentaría navegar a "" y moriría con «Cannot navigate to invalid URL»."""
from __future__ import annotations

import importlib

import pytest

from monitor import config as config_modulo

POR_DEFECTO = "https://dinapaqweb.tipsa-dinapaq.com/DinaPaqWeb/login_web.php"


@pytest.fixture(autouse=True)
def _restaurar():
    yield
    importlib.reload(config_modulo)


def recargar(monkeypatch, **entorno):
    for k, v in entorno.items():
        monkeypatch.setenv(k, v)
    return importlib.reload(config_modulo)


def test_una_variable_vacia_no_pisa_el_valor_por_defecto(monkeypatch):
    """El fallo real: `vars.DINAPAQ_URL_LOGIN` sin definir llega como ''."""
    cfg = recargar(monkeypatch, DINAPAQ_URL_LOGIN="")
    assert cfg.URL_LOGIN == POR_DEFECTO


def test_una_variable_con_solo_espacios_tampoco(monkeypatch):
    cfg = recargar(monkeypatch, DINAPAQ_URL_LOGIN="   \n  ")
    assert cfg.URL_LOGIN == POR_DEFECTO


def test_una_variable_ausente_usa_el_valor_por_defecto(monkeypatch):
    monkeypatch.delenv("DINAPAQ_URL_LOGIN", raising=False)
    assert importlib.reload(config_modulo).URL_LOGIN == POR_DEFECTO


def test_una_variable_con_valor_manda(monkeypatch):
    cfg = recargar(monkeypatch, DINAPAQ_URL_LOGIN="https://otro.portal/acceso.php")
    assert cfg.URL_LOGIN == "https://otro.portal/acceso.php"


def test_se_recortan_los_saltos_de_linea_al_pegar_una_url(monkeypatch):
    cfg = recargar(monkeypatch, DINAPAQ_URL_LOGIN="  https://otro.portal/acceso.php\n")
    assert cfg.URL_LOGIN == "https://otro.portal/acceso.php"


def test_los_numeros_aguantan_la_variable_vacia(monkeypatch):
    cfg = recargar(monkeypatch, DINAPAQ_DIAS_ATRAS="", SMTP_PUERTO="")
    assert cfg.DIAS_ATRAS == 7
    assert cfg.SMTP_PUERTO == 587


def test_un_numero_de_verdad_se_respeta(monkeypatch):
    cfg = recargar(monkeypatch, DINAPAQ_DIAS_ATRAS=" 30 ")
    assert cfg.DIAS_ATRAS == 30


def test_el_usuario_vacio_cae_en_el_nombre_antiguo(monkeypatch):
    """Actions manda DINAPAQ_USUARIO='' si el Secret no existe."""
    cfg = recargar(monkeypatch, DINAPAQ_USUARIO="", DINAPAQ_AGENCIA="02112345")
    assert cfg.USUARIO == "02112345"


def test_como_lo_monta_actions_de_verdad(monkeypatch):
    """Todas las `vars` sin definir llegan vacías a la vez: el caso que falló."""
    for v in ("DINAPAQ_URL_LOGIN", "DINAPAQ_URL_LISTADO", "DINAPAQ_DIAS_ATRAS",
              "DINAPAQ_SEL_USUARIO", "DINAPAQ_SEL_CLIENTE", "DINAPAQ_SEL_PASSWORD"):
        monkeypatch.setenv(v, "")
    cfg = recargar(monkeypatch, DINAPAQ_USUARIO="usuario", DINAPAQ_PASSWORD="secreta")

    assert cfg.URL_LOGIN == POR_DEFECTO      # ← lo que rompía la ejecución
    assert cfg.URL_LISTADO == ""
    assert cfg.DIAS_ATRAS == 7
    assert cfg.credenciales_ok()
