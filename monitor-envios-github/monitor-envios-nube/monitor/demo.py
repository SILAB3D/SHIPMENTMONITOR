"""Datos ficticios para probar el panel sin credenciales (`--demo`)."""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from monitor.parser import parse_envios

ESTADOS = ["Grabado", "En tránsito", "En reparto", "Entregado", "Incidencia: ausente"]
DESTINOS = ["Farmacia Sol", "Lab. Vidal", "Clínica Nova", "Talleres Ruiz", "Óptica Mar"]
CIUDADES = ["Valencia", "Madrid", "Sevilla", "Bilbao", "Denia"]

PLANTILLA = """
<html><body><table>
<tr><th>Albarán</th><th>Fecha</th><th>Destinatario</th><th>Localidad</th>
    <th>Bultos</th><th>Kilos</th><th>Estado</th><th>Observaciones</th></tr>
{filas}
</table></body></html>
"""


def envios_demo(semilla: int = 0, cuantos: int = 8) -> list[dict]:
    rnd = random.Random(semilla)
    filas = []
    for i in range(cuantos):
        estado = ESTADOS[min(int(rnd.random() * 3) + (semilla % 3), len(ESTADOS) - 1)]
        fecha = (datetime.now() - timedelta(days=rnd.randint(0, 5))).strftime("%d/%m/%Y")
        obs = "Reintento mañana" if estado.startswith("Incidencia") else ""
        filas.append(
            "<tr>"
            + "".join(
                f"<td>{v}</td>"
                for v in (
                    f"DEM{4200 + i}", fecha, DESTINOS[i % len(DESTINOS)], CIUDADES[i % len(CIUDADES)],
                    rnd.randint(1, 4), f"{rnd.uniform(0.5, 18):.1f}", estado, obs,
                )
            )
            + "</tr>"
        )
    return parse_envios(PLANTILLA.format(filas="".join(filas)))
