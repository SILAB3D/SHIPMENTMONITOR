"""La jornada de vigilancia: cuándo se queda despierta y con qué ritmo.

Esta lógica sustituye al filtro horario que dependía del minuto exacto en que
GitHub disparase el cron. Dejó de valer porque GitHub dejó de disparar: de las
comprobaciones pedidas servía entre una y cuatro al día, a la hora que le
parecía. Ahora una sola ejecución cubre la jornada entera, así que estas reglas
son las que deciden si el monitor vigila o no, y merecen pruebas.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

GUION = Path(__file__).resolve().parent.parent / "herramientas" / "vigilar.sh"

LUNES, VIERNES, SABADO, DOMINGO = 1, 5, 6, 7
H = lambda h, m=0: h * 60 + m           # noqa: E731  · minutos desde medianoche


def _llamar(funcion: str, *args) -> str:
    orden = f'VIGILAR_SOLO_FUNCIONES=1; source "{GUION}"; {funcion} {" ".join(map(str, args))}'
    r = subprocess.run(["bash", "-c", orden], capture_output=True, text=True, check=True)
    return r.stdout.strip()


def que_hacer(dia: int, reloj: int) -> str:
    return _llamar("que_hacer", dia, reloj)


def siguiente(reloj: int) -> int:
    return int(_llamar("siguiente_minuto", reloj))


# ─────────────────── a quién se le abre la jornada ───────────────────

@pytest.mark.parametrize("dia", [LUNES, 2, 3, 4, VIERNES])
def test_entre_semana_se_vigila(dia):
    assert que_hacer(dia, H(9)) == "vigilar"


@pytest.mark.parametrize("dia", [SABADO, DOMINGO])
def test_el_fin_de_semana_no(dia):
    assert que_hacer(dia, H(9)).startswith("salir")


@pytest.mark.parametrize("reloj,espera", [
    (H(8, 0), 30),      # media hora antes: merece la pena esperar despierto
    (H(8, 29), 1),
    (H(7, 0), None),    # hora y media antes: aún dentro del margen
])
def test_si_falta_poco_para_las_830_se_espera(reloj, espera):
    r = que_hacer(LUNES, reloj)
    assert r.startswith("esperar")
    if espera is not None:
        assert r.split()[1] == str(espera)


def test_demasiado_pronto_no_se_espera():
    """Una ejecución de madrugada no puede quedarse ocho horas dormida."""
    assert que_hacer(LUNES, H(3)).startswith("salir")
    assert que_hacer(LUNES, H(6, 59)).startswith("salir")


@pytest.mark.parametrize("reloj,esperado", [
    (H(8, 30), "vigilar"),      # primera comprobación del día
    (H(13, 0), "vigilar"),
    (H(17, 30), "vigilar"),     # la última
    (H(17, 59), "vigilar"),     # un disparo que llegó tarde todavía sirve
    (H(18, 1), "salir"),        # ya no
    (H(20, 51), "salir"),       # como los disparos de noche que servía GitHub
])
def test_la_franja_de_la_jornada(reloj, esperado):
    assert que_hacer(LUNES, reloj).split()[0] == esperado


# ─────────────────── el ritmo de la jornada ───────────────────

@pytest.mark.parametrize("ahora", [H(8, 30), H(9, 0), H(10, 15)])
def test_hasta_las_1030_cada_cuarto_de_hora(ahora):
    assert siguiente(ahora) == ahora + 15


@pytest.mark.parametrize("ahora", [H(10, 30), H(11, 30), H(15, 0)])
def test_desde_las_1030_cada_hora(ahora):
    assert siguiente(ahora) == ahora + 60


def test_las_1030_cierran_los_cuartos_y_abren_las_horas():
    assert siguiente(H(10, 15)) == H(10, 30)
    assert siguiente(H(10, 30)) == H(11, 30)


def test_la_ultima_del_dia_se_clava_a_las_1730():
    """Sin esto, la de las 17:00 saltaría a las 18:00 y no habría cierre."""
    assert siguiente(H(17, 0)) == H(17, 30)
    assert siguiente(H(16, 45)) == H(17, 30)      # también desde un hueco raro
    assert siguiente(H(17, 30)) > H(17, 30)       # pasada la última, ya no se clava


def test_el_dia_entero_cabe_en_las_comprobaciones_previstas():
    """De 8:30 a 17:30 deben salir 9 cuartos y 7 horas: 16 comprobaciones."""
    momentos, ahora = [H(8, 30)], H(8, 30)
    while ahora < H(17, 30):
        ahora = siguiente(ahora)
        momentos.append(ahora)
    assert momentos[-1] == H(17, 30)
    assert len(momentos) == 16
    # las nueve primeras, de cuarto en cuarto
    assert momentos[:9] == [H(8, 30) + 15 * i for i in range(9)]
    # el resto, de hora en hora
    assert momentos[9:] == [H(11, 30) + 60 * i for i in range(7)]
