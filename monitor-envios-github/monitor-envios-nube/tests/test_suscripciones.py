"""El Secret PUSH_SUSCRIPCIONES lo rellena una persona a mano, copiando y
pegando desde el panel. Aquí se comprueba que aguanta las formas razonables de
pegarlo y que la basura no tumba la comprobación del portal."""
from __future__ import annotations

import importlib
import json

import pytest

from monitor import config as config_modulo


def leer(monkeypatch, crudo: str):
    monkeypatch.setenv("PUSH_SUSCRIPCIONES", crudo)
    return importlib.reload(config_modulo).suscripciones()


SUB_A = {"endpoint": "https://fcm.googleapis.com/fcm/send/AAA",
         "keys": {"p256dh": "clave-a", "auth": "auth-a"}}
SUB_B = {"endpoint": "https://updates.push.services.mozilla.com/wpush/v2/BBB",
         "keys": {"p256dh": "clave-b", "auth": "auth-b"}}


@pytest.fixture(autouse=True)
def _limpiar(monkeypatch):
    yield
    importlib.reload(config_modulo)          # deja el módulo como estaba


def test_vacio_no_da_suscripciones(monkeypatch):
    assert leer(monkeypatch, "") == []
    assert leer(monkeypatch, "   \n  ") == []


def test_un_objeto_suelto(monkeypatch):
    assert leer(monkeypatch, json.dumps(SUB_A)) == [SUB_A]


def test_lista_json(monkeypatch):
    assert leer(monkeypatch, json.dumps([SUB_A, SUB_B])) == [SUB_A, SUB_B]


def test_varios_objetos_pegados_uno_detras_de_otro(monkeypatch):
    for separador in ("\n", "\n\n", ",\n", " "):
        crudo = separador.join(json.dumps(s) for s in (SUB_A, SUB_B))
        assert leer(monkeypatch, crudo) == [SUB_A, SUB_B], separador


def test_llaves_dentro_de_las_cadenas_no_confunden_al_troceador(monkeypatch):
    raro = {"endpoint": "https://ejemplo/{no-soy-un-objeto}", "keys": {"p256dh": "x", "auth": "y"}}
    crudo = json.dumps(raro) + "\n" + json.dumps(SUB_A)
    assert leer(monkeypatch, crudo) == [raro, SUB_A]


def test_se_descarta_lo_que_no_es_una_suscripcion(monkeypatch):
    incompleta = {"endpoint": "https://ejemplo/x"}                    # sin keys
    sin_endpoint = {"keys": {"p256dh": "x", "auth": "y"}}
    assert leer(monkeypatch, json.dumps([incompleta, sin_endpoint, SUB_A, "texto", 7])) == [SUB_A]


def test_texto_sin_sentido_no_revienta(monkeypatch):
    assert leer(monkeypatch, "pega aquí tu suscripción") == []
    assert leer(monkeypatch, "{roto") == []


def test_canales_refleja_si_el_push_esta_listo(monkeypatch):
    monkeypatch.setenv("PUSH_SUSCRIPCIONES", json.dumps(SUB_A))
    monkeypatch.setenv("VAPID_PRIVADA", "")
    cfg = importlib.reload(config_modulo)
    assert cfg.canales()["push"] is False        # hay suscripción pero no hay clave

    monkeypatch.setenv("VAPID_PRIVADA", "una-clave")
    cfg = importlib.reload(config_modulo)
    assert cfg.canales()["push"] is True
