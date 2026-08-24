"""Pruebas del parser y de la detección de cambios (sin tocar el portal real)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from monitor import estado as est  # noqa: E402
from monitor.parser import diferencias, extraer_tablas, parse_envios  # noqa: E402

HTML_LISTADO = """
<html><body>
<table border=0><tr><td><img src="logo.gif"></td><td>DinaPaqWeb</td></tr></table>
<table>
  <tr><th>Nº Albarán</th><th>Fecha</th><th>Destinatario</th><th>Población</th>
      <th>Bultos</th><th>Kilos</th><th>Situación</th><th>Observaciones</th></tr>
  <tr><td>0012345678</td><td>20/08/2026</td><td>FARMACIA SOL</td><td>VALENCIA</td>
      <td>2</td><td>3,4</td><td>EN REPARTO</td><td></td></tr>
  <tr><td>0012345679</td><td>21/08/2026</td><td>LAB VIDAL</td><td>MADRID</td>
      <td>1</td><td>0,8</td><td>ENTREGADO</td><td>Recibe: J. PEREZ</td></tr>
  <tr><td>TOTALES</td><td></td><td></td><td></td><td>3</td><td>4,2</td><td></td><td></td></tr>
</table>
</body></html>
"""

HTML_ACTUALIZADO = HTML_LISTADO.replace("EN REPARTO", "ENTREGADO").replace(
    "<tr><td>0012345679</td>",
    "<tr><td>0012345680</td><td>22/08/2026</td><td>OPTICA MAR</td><td>DENIA</td>"
    "<td>1</td><td>1,0</td><td>GRABADO</td><td></td></tr><tr><td>0012345679</td>",
)


def test_parseo_basico():
    envios = parse_envios(HTML_LISTADO)
    assert len(envios) == 2, "debe ignorar la tabla de maquetación y la fila de totales"
    e = envios[0]
    assert e["id"] == "0012345678"
    assert e["campos"]["estado"] == "EN REPARTO"
    assert e["campos"]["destinatario"] == "FARMACIA SOL"
    assert e["campos"]["localidad"] == "VALENCIA"
    assert e["campos"]["bultos"] == "2"


def test_varios_documentos():
    """El portal reparte la pantalla en frames: cada uno llega como documento aparte.

    Un solo `<html>` por delante no debe tapar a los siguientes (lxml se queda
    con el primero si se concatenan en una misma cadena).
    """
    frames = [
        "<html><head><title>DinaPaqWeb</title></head><frameset></frameset></html>",
        "<html><body>Cabecera</body></html>",
        HTML_LISTADO,
    ]
    assert len(extraer_tablas(frames)) == 2, "las tablas de todos los frames"
    envios = parse_envios(frames)
    assert [e["id"] for e in envios] == ["0012345678", "0012345679"]


def test_diferencias():
    cambios = diferencias({"estado": "EN REPARTO"}, {"estado": "ENTREGADO"})
    assert cambios == [("estado", "EN REPARTO", "ENTREGADO")]
    assert diferencias({"estado": "X", "fecha": "1"}, {"estado": "X", "fecha": "2"}) == []


def test_ciclo_completo():
    estado = {"envios": {}, "eventos": []}

    # 1ª pasada: línea base, sin avisos
    assert est.sincronizar(estado, parse_envios(HTML_LISTADO)) == []

    # 2ª pasada: un envío nuevo y un cambio de estado
    eventos = est.sincronizar(estado, parse_envios(HTML_ACTUALIZADO))
    assert sorted(e["tipo"] for e in eventos) == ["actualizado", "nuevo"], eventos
    nuevo = next(e for e in eventos if e["tipo"] == "nuevo")
    assert nuevo["envio_id"] == "0012345680"
    actualizado = next(e for e in eventos if e["tipo"] == "actualizado")
    assert "ENTREGADO" in actualizado["detalle"]

    # 3ª pasada sin cambios: silencio
    assert est.sincronizar(estado, parse_envios(HTML_ACTUALIZADO)) == []
    assert len(estado["envios"]) == 3
    # el historial se conserva, con el más reciente primero
    assert [e["id"] for e in estado["eventos"]] == [2, 1]
