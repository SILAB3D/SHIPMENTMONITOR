"""El horario de vigilancia, probado caso por caso.

Esta decisión ya falló una vez y no se notó: GitHub dejó de disparar bien el
cron, las pocas ejecuciones que llegaron cayeron de noche, el filtro las
descartó con toda la razón y el monitor pasó un viernes entero sin comprobar
nada. El fallo era invisible porque el job terminaba en verde.

Ahora el horario, además, lo escribe una persona desde el móvil: se puede pedir
un tramo del revés, un día que no existe o un intervalo de cero minutos. Nada de
eso puede dejar al monitor sin vigilar, así que aquí se prueban las dos cosas:
que las cuentas salen y que lo que llega roto se cae al horario de siempre.
"""
from __future__ import annotations

import json

import pytest

from monitor import ajustes as aj
from monitor import horario

LUNES, MARTES, VIERNES, SABADO, DOMINGO = 1, 2, 5, 6, 7
H = lambda h, m=0: h * 60 + m           # noqa: E731  · minutos desde medianoche

DEFECTO = aj.normalizar({})


def config(*horarios) -> dict:
    return aj.normalizar({"horarios": list(horarios)})


# ─────────────────── el horario de siempre ───────────────────

def test_sin_fichero_se_vigila_como_toda_la_vida(tmp_path, monkeypatch):
    """Ni fichero, ni panel, ni nada: lunes a viernes, 8:30 a 17:30."""
    monkeypatch.setenv("AJUSTES_FICHERO", str(tmp_path / "no-existe.json"))
    puesto = aj.cargar()
    assert [h["dias"] for h in puesto["horarios"]] == [[1, 2, 3, 4, 5]]
    assert horario.momentos(LUNES, puesto)[0] == H(8, 30)
    assert horario.momentos(LUNES, puesto)[-1] == H(17, 30)
    assert horario.momentos(SABADO, puesto) == []


def test_el_dia_entero_cabe_en_las_comprobaciones_previstas():
    """De 8:30 a 17:30 deben salir 9 cuartos y 7 horas: 16 comprobaciones."""
    marcas = horario.momentos(LUNES, DEFECTO)
    assert len(marcas) == 16
    assert marcas[:9] == [H(8, 30) + 15 * i for i in range(9)]
    assert marcas[9:] == [H(11, 30) + 60 * i for i in range(7)]


@pytest.mark.parametrize("dia", [LUNES, 2, 3, 4, VIERNES])
def test_entre_semana_se_vigila(dia):
    assert horario.que_hacer(dia, H(9), DEFECTO) == "vigilar"


@pytest.mark.parametrize("dia", [SABADO, DOMINGO])
def test_el_fin_de_semana_no(dia):
    assert horario.que_hacer(dia, H(9), DEFECTO).startswith("salir")


# ─────────────────── a quién se le abre la jornada ───────────────────

@pytest.mark.parametrize("reloj,espera", [
    (H(8, 0), 30),      # media hora antes: merece la pena esperar despierto
    (H(8, 29), 1),
    (H(7, 0), 90),      # hora y media antes: el límite
])
def test_si_falta_poco_para_abrir_se_espera(reloj, espera):
    assert horario.que_hacer(LUNES, reloj, DEFECTO) == f"esperar {espera}"


def test_demasiado_pronto_no_se_espera():
    """Una ejecución de madrugada no puede quedarse ocho horas dormida."""
    assert horario.que_hacer(LUNES, H(3), DEFECTO).startswith("salir")
    assert horario.que_hacer(LUNES, H(6, 59), DEFECTO).startswith("salir")


@pytest.mark.parametrize("reloj,esperado", [
    (H(8, 30), "vigilar"),      # primera comprobación del día
    (H(13, 0), "vigilar"),
    (H(17, 30), "vigilar"),     # la última
    (H(17, 59), "vigilar"),     # un disparo que llegó tarde todavía sirve
    (H(18, 1), "salir"),        # ya no
    (H(20, 51), "salir"),       # como los disparos de noche que servía GitHub
])
def test_la_franja_de_la_jornada(reloj, esperado):
    assert horario.que_hacer(LUNES, reloj, DEFECTO).split()[0] == esperado


# ─────────────────── el ritmo de la jornada ───────────────────

@pytest.mark.parametrize("ahora", [H(8, 30), H(9, 0), H(10, 15)])
def test_hasta_las_1030_cada_cuarto_de_hora(ahora):
    assert horario.siguiente_minuto(LUNES, ahora, DEFECTO) == ahora + 15


@pytest.mark.parametrize("ahora", [H(10, 30), H(11, 30), H(15, 30)])
def test_desde_las_1030_cada_hora(ahora):
    assert horario.siguiente_minuto(LUNES, ahora, DEFECTO) == ahora + 60


def test_una_hora_a_destiempo_no_descuadra_el_resto_del_dia():
    """Si una comprobación se retrasa, la siguiente vuelve a la hora prevista.

    Antes se sumaba el intervalo a la hora que fuese, así que una ejecución que
    arrancaba a las 15:04 dejaba el resto del día en :04. Ahora el día tiene sus
    horas y una comprobación tardía no las mueve.
    """
    assert horario.siguiente_minuto(LUNES, H(15, 4), DEFECTO) == H(15, 30)


def test_las_1030_cierran_los_cuartos_y_abren_las_horas():
    assert horario.siguiente_minuto(LUNES, H(10, 15), DEFECTO) == H(10, 30)
    assert horario.siguiente_minuto(LUNES, H(10, 30), DEFECTO) == H(11, 30)


def test_la_ultima_del_dia_se_clava_en_el_final_del_tramo():
    """Sin esto, la de las 17:00 saltaría a las 18:00 y no habría cierre."""
    assert horario.siguiente_minuto(LUNES, H(17, 0), DEFECTO) == H(17, 30)
    assert horario.siguiente_minuto(LUNES, H(17, 30), DEFECTO) is None


# ─────────────────── horarios a medida ───────────────────

def test_un_horario_propio_manda_sobre_el_de_siempre():
    puesto = config({"nombre": "Mañanas", "dias": [SABADO],
                     "tramos": [{"desde": "09:00", "hasta": "11:00", "cada": 30}]})
    assert horario.momentos(SABADO, puesto) == [H(9), H(9, 30), H(10), H(10, 30), H(11)]
    assert horario.momentos(LUNES, puesto) == []
    assert horario.que_hacer(LUNES, H(9), puesto).startswith("salir")


def test_varias_configuraciones_se_suman_en_el_mismo_dia():
    """Dos configuraciones que pisan el mismo día no compiten: se juntan."""
    puesto = config(
        {"id": "manana", "nombre": "Mañana", "dias": [LUNES],
         "tramos": [{"desde": "08:00", "hasta": "09:00", "cada": 30}]},
        {"id": "tarde", "nombre": "Tarde", "dias": [LUNES, MARTES],
         "tramos": [{"desde": "16:00", "hasta": "17:00", "cada": 60}]},
    )
    assert horario.momentos(LUNES, puesto) == [H(8), H(8, 30), H(9), H(16), H(17)]
    assert horario.momentos(MARTES, puesto) == [H(16), H(17)]


def test_los_minutos_repetidos_no_se_comprueban_dos_veces():
    puesto = config(
        {"id": "a", "nombre": "A", "dias": [LUNES],
         "tramos": [{"desde": "09:00", "hasta": "10:00", "cada": 30}]},
        {"id": "b", "nombre": "B", "dias": [LUNES],
         "tramos": [{"desde": "09:30", "hasta": "10:30", "cada": 30}]},
    )
    assert horario.momentos(LUNES, puesto) == [H(9), H(9, 30), H(10), H(10, 30)]


def test_una_configuracion_apagada_no_cuenta():
    puesto = config({"nombre": "Sábados", "dias": [SABADO], "activo": False,
                     "tramos": [{"desde": "09:00", "hasta": "11:00", "cada": 30}]})
    assert horario.momentos(SABADO, puesto) == []
    # apagarlas todas equivale a no tener ninguna: no se vigila, no se revienta
    assert horario.que_hacer(SABADO, H(10), puesto).startswith("salir")


def test_un_horario_de_24_horas_no_se_sale_del_dia():
    puesto = config({"nombre": "Siempre", "dias": [LUNES],
                     "tramos": [{"desde": "00:00", "hasta": "24:00", "cada": 360}]})
    marcas = horario.momentos(LUNES, puesto)
    assert marcas[0] == 0 and marcas[-1] == 24 * 60
    assert horario.que_hacer(LUNES, H(3), puesto) == "vigilar"


# ─────────────────── lo que llega roto ───────────────────

@pytest.mark.parametrize("crudo", [
    {"horarios": []},                                        # sin ninguno
    {"horarios": [{"nombre": "X", "dias": [], "tramos": []}]},
    {"horarios": [{"nombre": "X", "dias": [9], "tramos": [{"desde": "08:00", "hasta": "09:00"}]}]},
    {"horarios": [{"nombre": "X", "dias": [1], "tramos": [{"desde": "10:00", "hasta": "09:00"}]}]},
    {"horarios": [{"nombre": "X", "dias": [1], "tramos": [{"desde": "no", "hasta": "tampoco"}]}]},
    {"horarios": "esto no es una lista"},
    "esto no es ni un objeto",
])
def test_lo_que_no_se_entiende_cae_al_horario_de_siempre(crudo):
    puesto = aj.normalizar(crudo)
    assert puesto["horarios"] == DEFECTO["horarios"]


def test_un_fichero_ilegible_no_tumba_la_vigilancia(tmp_path, monkeypatch):
    roto = tmp_path / "ajustes.json"
    roto.write_text("{esto no es json", encoding="utf-8")
    monkeypatch.setenv("AJUSTES_FICHERO", str(roto))
    assert aj.cargar()["horarios"] == DEFECTO["horarios"]


def test_el_intervalo_se_queda_dentro_de_lo_razonable():
    """Un «cada 0 min» sería un bucle cerrado; un «cada 3 días», no vigilar."""
    puesto = config({"nombre": "X", "dias": [LUNES],
                     "tramos": [{"desde": "09:00", "hasta": "10:00", "cada": 0}]})
    assert puesto["horarios"][0]["tramos"][0]["cada"] == aj.MIN_CADA
    puesto = config({"nombre": "X", "dias": [LUNES],
                     "tramos": [{"desde": "09:00", "hasta": "10:00", "cada": 99999}]})
    assert puesto["horarios"][0]["tramos"][0]["cada"] == aj.MAX_CADA


def test_dos_configuraciones_con_el_mismo_id_no_se_pisan():
    puesto = config(
        {"id": "x", "nombre": "Una", "dias": [LUNES], "tramos": [{"desde": "09:00", "hasta": "10:00"}]},
        {"id": "x", "nombre": "Otra", "dias": [MARTES], "tramos": [{"desde": "09:00", "hasta": "10:00"}]},
    )
    ids = [h["id"] for h in puesto["horarios"]]
    assert len(set(ids)) == 2


# ─────────────────── ida y vuelta por el fichero ───────────────────

def test_lo_que_guarda_el_panel_es_lo_que_lee_el_monitor(tmp_path, monkeypatch):
    fichero = tmp_path / "ajustes.json"
    monkeypatch.setenv("AJUSTES_FICHERO", str(fichero))
    aj.guardar({"horarios": [{"id": "g", "nombre": "Guardias", "dias": [SABADO, DOMINGO],
                              "tramos": [{"desde": "10:00", "hasta": "12:00", "cada": 60}]}],
                "avisos": {"actualizado": False}})
    leido = aj.cargar()
    assert leido["horarios"][0]["nombre"] == "Guardias"
    assert horario.momentos(DOMINGO, leido) == [H(10), H(11), H(12)]
    assert leido["avisos"]["actualizado"] is False
    assert leido["avisos"]["incidencia"] is True       # lo que no se toca sigue encendido
    assert json.loads(fichero.read_text(encoding="utf-8"))["version"] == 1
