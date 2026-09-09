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


# ─────────────────── la jornada de punta a punta ───────────────────
# Se ejecuta el guion de verdad, con un portal y un git de mentira y el reloj
# corriendo a toda velocidad, para ver que el bucle hace lo que dice.

GUION_COMPLETO = GUION.read_text(encoding="utf-8")


def _correr(tmp_path, *, evento, hora, minutos_max=320, pasos_esperados=None):
    """Ejecuta vigilar.sh con `sleep`, `python` y `git` sustituidos por títeres."""
    falso = tmp_path / "bin"; falso.mkdir()
    registro = tmp_path / "registro.txt"
    # sleep no duerme: adelanta el reloj falso, que vive en un fichero
    (falso / "sleep").write_text(
        "#!/bin/bash\n"
        f'echo "dormir $1" >> {registro}\n'
        f'echo $(( $(cat {tmp_path}/reloj) + ($1 / 60) )) > {tmp_path}/reloj\n', encoding="utf-8")
    (falso / "python").write_text(f'#!/bin/bash\necho "comprobado" >> {registro}\nexit 0\n', encoding="utf-8")
    (falso / "git").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    for f in falso.iterdir():
        f.chmod(0o755)
    (tmp_path / "reloj").write_text(str(hora), encoding="utf-8")
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "datos.json").write_text("{}", encoding="utf-8")

    # el guion pregunta la hora con reloj_ahora(); se la damos del fichero
    guion = GUION_COMPLETO.replace(
        "reloj_ahora() { echo $(( $(TZ=Europe/Madrid date +%-H) * 60 + $(TZ=Europe/Madrid date +%-M) )); }",
        f'reloj_ahora() {{ cat {tmp_path}/reloj; }}').replace(
        "dia_ahora()   { TZ=Europe/Madrid date +%u; }", "dia_ahora()   { echo 1; }")
    (tmp_path / "vigilar.sh").write_text(guion, encoding="utf-8")

    r = subprocess.run(["bash", str(tmp_path / "vigilar.sh")], capture_output=True, text=True,
                       cwd=str(tmp_path),
                       env={"PATH": f"{falso}:/usr/bin:/bin", "GITHUB_EVENT_NAME": evento,
                            "GITHUB_REF_NAME": "main", "VIGILAR_MAX_MINUTOS": str(minutos_max)})
    hechas = registro.read_text(encoding="utf-8").count("comprobado") if registro.exists() else 0
    return hechas, r.stdout


def test_una_jornada_completa_hace_las_16_comprobaciones(tmp_path):
    """Arrancando a las 8:30 y sin tope, el día entero sale de una sola ejecución."""
    hechas, salida = _correr(tmp_path, evento="schedule", hora=H(8, 30), minutos_max=100000)
    assert hechas == 16, salida[-600:]
    assert "jornada terminada" in salida


def test_el_tope_de_horas_corta_y_deja_el_relevo(tmp_path):
    hechas, salida = _correr(tmp_path, evento="schedule", hora=H(8, 30), minutos_max=60)
    assert 1 <= hechas < 16
    assert "lo retoma la siguiente" in salida


def test_a_mano_de_madrugada_comprueba_una_vez_y_para(tmp_path):
    hechas, salida = _correr(tmp_path, evento="workflow_dispatch", hora=H(3, 0))
    assert hechas == 1
    assert "No hay jornada que vigilar" in salida


def test_a_mano_en_jornada_comprueba_y_se_queda(tmp_path):
    hechas, _ = _correr(tmp_path, evento="workflow_dispatch", hora=H(16, 0), minutos_max=100000)
    assert hechas == 3          # 16:00 (a mano), 17:00 y la de cierre de las 17:30


def test_programada_de_madrugada_no_comprueba_nada(tmp_path):
    hechas, salida = _correr(tmp_path, evento="schedule", hora=H(3, 0))
    assert hechas == 0
    assert "demasiado pronto" in salida.lower()
