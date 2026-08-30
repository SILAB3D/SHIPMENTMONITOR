"""El horario de vigilancia, probado caso por caso.

Esta decisión ya falló una vez y no se notó: GitHub dejó de disparar bien el
cron, las pocas ejecuciones que llegaron cayeron de noche, el filtro las
descartó con toda la razón y el monitor pasó un viernes entero sin comprobar
nada. El fallo era invisible porque el job terminaba en verde.

De ahí que la regla viva en un script propio y se pruebe aquí: lunes a viernes,
de 8:30 a 18:00, cada 15 min hasta las 10:30 y cada hora después, contando
siempre desde la ÚLTIMA comprobación y no desde el minuto en que dispare GitHub.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
GUION = RAIZ / "herramientas" / "toca_comprobar.sh"

LUNES, VIERNES, SABADO, DOMINGO = 1, 5, 6, 7


def decidir(dia=VIERNES, reloj=9 * 60, desde=60, evento="schedule", cwd=None) -> bool:
    entorno = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "GITHUB_EVENT_NAME": evento,
        "PRUEBA_DIA": str(dia),
        "PRUEBA_RELOJ": str(reloj),
    }
    if desde is not None:
        entorno["PRUEBA_DESDE"] = str(desde)
    r = subprocess.run(["bash", str(GUION)], capture_output=True, text=True,
                       env=entorno, cwd=str(cwd or RAIZ), check=True)
    assert r.stdout.strip() in ("toca=si", "toca=no"), r.stdout
    return r.stdout.strip() == "toca=si"


# ─────────────────────────── días ───────────────────────────

@pytest.mark.parametrize("dia", [LUNES, 2, 3, 4, VIERNES])
def test_se_vigila_de_lunes_a_viernes(dia):
    assert decidir(dia=dia)


@pytest.mark.parametrize("dia", [SABADO, DOMINGO])
def test_el_fin_de_semana_no(dia):
    assert not decidir(dia=dia)


# ─────────────────────────── horas ───────────────────────────

@pytest.mark.parametrize("reloj,esperado", [
    (8 * 60 + 0,  False),   # 8:00, todavía no
    (8 * 60 + 29, False),   # 8:29
    (8 * 60 + 30, True),    # 8:30, primera del día
    (12 * 60,     True),
    (17 * 60 + 30, True),   # 17:30, la última prevista
    (17 * 60 + 55, True),   # una 17:30 que GitHub sirvió con retraso
    (18 * 60 + 1, False),   # ya no
    (23 * 60,     False),   # como las que dispararon de noche aquel viernes
])
def test_la_franja_del_dia(reloj, esperado):
    assert decidir(reloj=reloj) is esperado


# ─────────────────── cadencia según la franja ───────────────────

@pytest.mark.parametrize("desde,esperado", [(5, False), (12, False), (13, True), (30, True)])
def test_de_830_a_1030_cada_cuarto_de_hora(desde, esperado):
    assert decidir(reloj=9 * 60, desde=desde) is esperado


@pytest.mark.parametrize("desde,esperado", [(15, False), (49, False), (50, True), (75, True)])
def test_a_partir_de_1030_una_por_hora(desde, esperado):
    assert decidir(reloj=12 * 60, desde=desde) is esperado


def test_las_1030_todavia_son_de_cuartos():
    assert decidir(reloj=10 * 60 + 30, desde=15)
    assert decidir(reloj=10 * 60 + 31, desde=15) is False


# ─────────────────── lo que hace robusto el horario ───────────────────

def test_un_disparo_perdido_no_se_arrastra():
    """Si GitHub se salta disparos, el siguiente que llegue comprueba igual.

    Es la diferencia con el diseño anterior, que exigía que el disparo cayera en
    un minuto exacto: allí, un retraso significaba perder la comprobación.
    """
    assert decidir(reloj=11 * 60 + 47, desde=137)


def test_a_mano_se_comprueba_siempre():
    for reloj in (3 * 60, 23 * 60):
        for dia in (DOMINGO, VIERNES):
            assert decidir(dia=dia, reloj=reloj, evento="workflow_dispatch")


def test_sin_fichero_de_datos_se_comprueba(tmp_path):
    """La primera vez no hay marca de tiempo: hay que comprobar, no quedarse quieto."""
    (tmp_path / "docs").mkdir()
    assert decidir(desde=None, cwd=tmp_path)


def test_lee_la_hora_del_fichero_de_datos(tmp_path):
    """La marca va en claro en docs/datos.json; sin ella el horario no funciona."""
    docs = tmp_path / "docs"; docs.mkdir()
    hace_dos_min = datetime.now(timezone.utc) - timedelta(minutes=2)
    (docs / "datos.json").write_text(json.dumps({
        "v": 1, "ts": hace_dos_min.strftime("%Y-%m-%dT%H:%M:%SZ"), "datos": "…"}), encoding="utf-8")
    assert decidir(desde=None, reloj=12 * 60, cwd=tmp_path) is False   # hace 2 min: aún no

    hace_dos_horas = datetime.now(timezone.utc) - timedelta(hours=2)
    (docs / "datos.json").write_text(json.dumps({
        "v": 1, "ts": hace_dos_horas.strftime("%Y-%m-%dT%H:%M:%SZ"), "datos": "…"}), encoding="utf-8")
    assert decidir(desde=None, reloj=12 * 60, cwd=tmp_path) is True


def test_el_fichero_cifrado_de_verdad_trae_la_marca(tmp_path):
    """Comprobación de punta a punta: lo que escribe el monitor lo lee el script."""
    import sys
    sys.path.insert(0, str(RAIZ))
    from monitor.cifrado import cifrar

    docs = tmp_path / "docs"; docs.mkdir()
    (docs / "datos.json").write_text(json.dumps(cifrar({"envios": {}}, "clave")), encoding="utf-8")
    # recién escrito: en la franja horaria todavía no toca
    assert decidir(desde=None, reloj=12 * 60, cwd=tmp_path) is False
