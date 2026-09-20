"""La jornada de vigilancia de punta a punta: el guion que la lleva.

Esta lógica sustituye al filtro horario que dependía del minuto exacto en que
GitHub disparase el cron. Dejó de valer porque GitHub dejó de disparar: de las
comprobaciones pedidas servía entre una y cuatro al día, a la hora que le
parecía. Ahora una sola ejecución cubre la jornada entera.

Las cuentas del horario —qué días, a qué horas y con qué ritmo— viven en
monitor/horario.py y se prueban en tests/test_horario.py. Aquí se prueba el
guion: que arranca cuando toca, que hace las comprobaciones que el horario dice
y que se para donde debe. Se ejecuta de verdad, con un portal y un git de
mentira y el reloj corriendo a toda velocidad.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
GUION = RAIZ / "herramientas" / "vigilar.sh"
GUION_COMPLETO = GUION.read_text(encoding="utf-8")

H = lambda h, m=0: h * 60 + m           # noqa: E731  · minutos desde medianoche

# El horario de siempre, escrito aquí para que estas pruebas no dependan de lo
# que tenga puesto el panel en docs/ajustes.json.
HORARIO = {
    "horarios": [{
        "id": "jornada", "nombre": "Jornada laboral", "activo": True, "dias": [1, 2, 3, 4, 5],
        "tramos": [{"desde": "08:30", "hasta": "10:30", "cada": 15},
                   {"desde": "10:30", "hasta": "17:30", "cada": 60}],
    }],
}


def _correr(tmp_path, *, evento, hora, minutos_max=320, ajustes=None, dia=1):
    """Ejecuta vigilar.sh con `sleep`, `python` y `git` sustituidos por títeres."""
    falso = tmp_path / "bin"; falso.mkdir()
    registro = tmp_path / "registro.txt"
    # Los caminos que se cuelan DENTRO del guion van en forma de bash: escritos
    # a la de Windows, las barras invertidas se las come el intérprete.
    reg, tmp = registro.as_posix(), tmp_path.as_posix()
    # sleep no duerme: adelanta el reloj falso, que vive en un fichero
    (falso / "sleep").write_text(
        "#!/bin/bash\n"
        f'echo "dormir $1" >> {reg}\n'
        f'echo $(( $(cat {tmp}/reloj) + ($1 / 60) )) > {tmp}/reloj\n', encoding="utf-8")
    # El títere de python hace de monitor.ejecutar, pero las preguntas sobre el
    # horario las pasa al intérprete de verdad: es justo lo que se quiere probar.
    (falso / "python").write_text(
        "#!/bin/bash\n"
        'case "$*" in\n'
        f'  *monitor.horario*) exec "{Path(sys.executable).as_posix()}" "$@" ;;\n'
        "esac\n"
        f'echo "comprobado" >> {reg}\nexit 0\n', encoding="utf-8")
    (falso / "git").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    for f in falso.iterdir():
        f.chmod(0o755)
    (tmp_path / "reloj").write_text(str(hora), encoding="utf-8")
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "datos.json").write_text("{}", encoding="utf-8")
    fichero_ajustes = tmp_path / "ajustes.json"
    fichero_ajustes.write_text(json.dumps(ajustes or HORARIO), encoding="utf-8")

    # el guion pregunta la hora con reloj_ahora(); se la damos del fichero
    guion = GUION_COMPLETO.replace(
        "reloj_ahora() { echo $(( $(TZ=Europe/Madrid date +%-H) * 60 + $(TZ=Europe/Madrid date +%-M) )); }",
        f'reloj_ahora() {{ cat {tmp}/reloj; }}').replace(
        "dia_ahora()   { TZ=Europe/Madrid date +%u; }", f"dia_ahora()   {{ echo {dia}; }}")
    (tmp_path / "vigilar.sh").write_text(guion, encoding="utf-8")

    r = subprocess.run(["bash", str(tmp_path / "vigilar.sh")], capture_output=True, text=True,
                       cwd=str(tmp_path),
                       env={"PATH": f"{falso}:/usr/bin:/bin", "GITHUB_EVENT_NAME": evento,
                            "GITHUB_REF_NAME": "main", "VIGILAR_MAX_MINUTOS": str(minutos_max),
                            "PYTHONPATH": str(RAIZ), "AJUSTES_FICHERO": str(fichero_ajustes),
                            "GITHUB_OUTPUT": (tmp_path / "salida.txt").as_posix(),
                            # en Windows, sin esto el intérprete de verdad no arranca
                            "SYSTEMROOT": r"C:\Windows"})
    hechas = registro.read_text(encoding="utf-8").count("comprobado") if registro.exists() else 0
    return hechas, r.stdout + r.stderr


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
    assert hechas == 3          # 16:00 (a mano), 16:30 y la de cierre de las 17:30


def test_programada_de_madrugada_no_comprueba_nada(tmp_path):
    hechas, salida = _correr(tmp_path, evento="schedule", hora=H(3, 0))
    assert hechas == 0
    assert "demasiado pronto" in salida.lower()


def test_en_fin_de_semana_una_programada_se_va_de_vacio(tmp_path):
    hechas, salida = _correr(tmp_path, evento="schedule", hora=H(10, 0), dia=6)
    assert hechas == 0
    assert "no hay ninguna vigilancia programada" in salida.lower()


# ─────────────────── el horario del panel manda ───────────────────

def test_el_guion_obedece_al_horario_configurado(tmp_path):
    """Un sábado de guardia: el guion no sabe de días ni de horas, los pregunta."""
    guardia = {"horarios": [{
        "id": "g", "nombre": "Guardia del sábado", "activo": True, "dias": [6],
        "tramos": [{"desde": "10:00", "hasta": "12:00", "cada": 30}],
    }]}
    hechas, salida = _correr(tmp_path, evento="schedule", hora=H(10, 0), dia=6,
                             ajustes=guardia, minutos_max=100000)
    assert hechas == 5, salida[-600:]          # 10:00, 10:30, 11:00, 11:30 y 12:00
    assert "Guardia del sábado" in salida
