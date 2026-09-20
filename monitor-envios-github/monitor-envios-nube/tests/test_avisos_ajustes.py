"""Qué avisos salen del monitor y cuáles se quedan en el panel.

Apagar un aviso en Ajustes tiene que silenciar el empujón al móvil SIN dejar de
apuntar la novedad: el historial y las tarjetas del panel se ven igual. Y como
lo que se apaga son clases de novedad —incidencias, entregas, cambios sueltos—,
lo primero que hay que probar es que cada evento se clasifica donde debe.
"""
from __future__ import annotations

import pytest

from monitor import ajustes as aj
from monitor import notificar


def evento(tipo="actualizado", estado="", detalle="") -> dict:
    return {"id": 1, "tipo": tipo, "envio_id": "A1", "titulo": "t",
            "detalle": detalle, "campos": {"estado": estado}}


# ─────────────────── de qué clase es cada novedad ───────────────────

@pytest.mark.parametrize("estado,esperada", [
    ("TRANSITO", "actualizado"),
    ("EN REPARTO", "actualizado"),
    ("ENTREGADO", "entrega"),
    ("Entrega realizada", "entrega"),
    ("INCIDENCIA: AUSENTE", "incidencia"),
    ("DEVUELTO AL REMITENTE", "incidencia"),
    ("Entrega parcial", "incidencia"),        # ha llegado, pero no entero
    ("LECTURA EN HUB MADRID", "actualizado"),
])
def test_cada_cambio_de_estado_va_a_su_clase(estado, esperada):
    assert aj.clase(evento(estado=estado)) == esperada


def test_un_envio_nuevo_es_nuevo_aunque_su_estado_diga_otra_cosa():
    """DinaPaqWeb llama «PENDIENTE DE ENTREGAR A TIPSA» a un envío recién grabado."""
    assert aj.clase(evento(tipo="nuevo", estado="PENDIENTE DE ENTREGAR A TIPSA")) == "nuevo"
    assert aj.clase(evento(estado="PENDIENTE DE ENTREGAR A TIPSA")) == "actualizado"


def test_sin_estado_se_mira_el_detalle():
    assert aj.clase(evento(estado="", detalle="estado: TRANSITO → ENTREGADO")) == "entrega"


# ─────────────────── el filtro ───────────────────

def test_por_defecto_no_se_silencia_nada():
    eventos = [evento(tipo="nuevo"), evento(estado="ENTREGADO"), evento(estado="INCIDENCIA")]
    assert aj.filtrar(eventos, aj.normalizar({})) == eventos


def test_apagar_una_clase_silencia_solo_esa():
    puesto = aj.normalizar({"avisos": {"actualizado": False}})
    eventos = [evento(estado="TRANSITO"), evento(estado="ENTREGADO"), evento(tipo="nuevo")]
    quedan = [aj.clase(e) for e in aj.filtrar(eventos, puesto)]
    assert quedan == ["entrega", "nuevo"]


def test_se_puede_dejar_solo_lo_urgente():
    puesto = aj.normalizar({"avisos": {"actualizado": False, "entrega": False, "nuevo": False}})
    eventos = [evento(estado="TRANSITO"), evento(estado="ENTREGADO"),
               evento(estado="INCIDENCIA: AUSENTE"), evento(tipo="nuevo")]
    assert [aj.clase(e) for e in aj.filtrar(eventos, puesto)] == ["incidencia"]


# ─────────────────── lo que llega a los canales ───────────────────

def test_no_se_manda_nada_si_todas_las_novedades_estan_apagadas(monkeypatch, tmp_path):
    fichero = tmp_path / "ajustes.json"
    monkeypatch.setenv("AJUSTES_FICHERO", str(fichero))
    aj.guardar({"avisos": {clave: False for clave in aj.CLASES_AVISO}})
    monkeypatch.setattr(notificar.config, "push_ok", lambda: True)
    monkeypatch.setattr(notificar, "_push", lambda *_: pytest.fail("no debía enviarse nada"))
    assert notificar.avisar([evento(estado="TRANSITO")]) == {}


def test_un_canal_apagado_no_se_usa_aunque_este_configurado(monkeypatch, tmp_path):
    fichero = tmp_path / "ajustes.json"
    monkeypatch.setenv("AJUSTES_FICHERO", str(fichero))
    aj.guardar({"canales": {"push": False}})
    monkeypatch.setattr(notificar.config, "push_ok", lambda: True)
    monkeypatch.setattr(notificar, "_push", lambda *_: pytest.fail("el push estaba apagado"))
    monkeypatch.setattr(notificar.config, "TELEGRAM_TOKEN", "t")
    monkeypatch.setattr(notificar.config, "TELEGRAM_CHAT_ID", "c")
    enviados = []
    monkeypatch.setattr(notificar, "_telegram", lambda cuerpo: enviados.append(cuerpo))
    resultado = notificar.avisar([evento(estado="TRANSITO")])
    assert resultado == {"telegram": "ok"} and len(enviados) == 1


def test_los_fallos_del_monitor_tambien_se_pueden_silenciar(monkeypatch, tmp_path):
    fichero = tmp_path / "ajustes.json"
    monkeypatch.setenv("AJUSTES_FICHERO", str(fichero))
    aj.guardar({"avisos": {"error": False}})
    monkeypatch.setattr(notificar, "_push", lambda *_: pytest.fail("no debía avisar del fallo"))
    monkeypatch.setattr(notificar, "_telegram", lambda *_: pytest.fail("no debía avisar del fallo"))
    monkeypatch.setattr(notificar, "_email", lambda *_: pytest.fail("no debía avisar del fallo"))
    notificar.avisar_error("el portal no contesta")
