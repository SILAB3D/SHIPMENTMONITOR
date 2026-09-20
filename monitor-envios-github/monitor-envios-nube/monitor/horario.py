"""Cuándo toca comprobar el portal, a partir de los horarios del panel.

Esta decisión vivía en `herramientas/vigilar.sh`, con las horas escritas a mano
dentro del guion. Desde que el horario se configura desde el panel hay que
saber combinar varias configuraciones —«jornada laboral» más «guardia del
sábado por la mañana», por ejemplo—, y eso en bash era pedir un disgusto. El
guion sigue llevando la jornada, pero las cuentas las pregunta aquí.

El día entero se resuelve de una vez: a partir de los tramos de las
configuraciones activas para ese día se calcula la LISTA de minutos en los que
se comprueba. Todo lo demás —si hay jornada, cuándo empieza, cuál es la
siguiente comprobación— sale de mirar esa lista, que es mucho más fácil de
comprobar que una cadena de condiciones.

Reglas de un tramo «de 8:30 a 10:30 cada 15 min»: se comprueba a las 8:30, 8:45…
y SIEMPRE en el minuto final del tramo, las 10:30, aunque no cuadre con el
intervalo. El cierre del tramo es la comprobación que dice cómo se ha quedado la
cosa; sin clavarla, un tramo que acabase a las 17:30 cerraría a las 17:00.
"""
from __future__ import annotations

import argparse
import sys

from monitor import ajustes as aj

ESPERA_ARRANQUE = 90     # minutos que merece la pena esperar despierto a que abra la jornada
MARGEN_FINAL = 30        # se admite arrancar hasta media hora después de la última comprobación

DIAS = {1: "lunes", 2: "martes", 3: "miércoles", 4: "jueves",
        5: "viernes", 6: "sábado", 7: "domingo"}


def momentos(dia: int, ajustes: dict | None = None) -> list[int]:
    """Los minutos del día en los que toca comprobar, en orden y sin repetir."""
    ajustes = ajustes or aj.cargar()
    marcas: set[int] = set()
    for horario in ajustes["horarios"]:
        if not horario["activo"] or dia not in horario["dias"]:
            continue
        for tramo in horario["tramos"]:
            desde, hasta = aj.minutos(tramo["desde"]), aj.minutos(tramo["hasta"])
            cada = tramo["cada"]
            marca = desde
            while marca < hasta:
                marcas.add(marca)
                marca += cada
            marcas.add(hasta)            # el cierre del tramo, siempre
    return sorted(marcas)


def siguiente_minuto(dia: int, ahora: int, ajustes: dict | None = None) -> int | None:
    """La siguiente comprobación de HOY después de `ahora`, o None si ya no hay."""
    for marca in momentos(dia, ajustes):
        if marca > ahora:
            return marca
    return None


def que_hacer(dia: int, ahora: int, ajustes: dict | None = None) -> str:
    """Qué hacer con una ejecución que arranca a esta hora de este día.

    Devuelve «vigilar», «esperar <minutos>» o «salir <motivo>», que es lo que
    entiende vigilar.sh.
    """
    ajustes = ajustes or aj.cargar()
    marcas = momentos(dia, ajustes)
    if not marcas:
        return f"salir Hoy ({DIAS.get(dia, dia)}) no hay ninguna vigilancia programada."

    primera, ultima = marcas[0], marcas[-1]
    if ahora < primera:
        faltan = primera - ahora
        if faltan <= ESPERA_ARRANQUE:
            return f"esperar {faltan}"
        return (f"salir Faltan {faltan} min para las {aj.reloj(primera)}: "
                "demasiado pronto para quedarse esperando.")
    if ahora > ultima + MARGEN_FINAL:
        return f"salir Pasada la jornada (última comprobación, las {aj.reloj(ultima)})."
    return "vigilar"


def resumen(dia: int, ajustes: dict | None = None) -> str:
    """Una línea para el log: qué se va a hacer hoy y con qué ritmo."""
    ajustes = ajustes or aj.cargar()
    partes = []
    for horario in ajustes["horarios"]:
        if not horario["activo"] or dia not in horario["dias"]:
            continue
        ritmos = ", ".join(
            f"{t['desde']}–{t['hasta']} cada {t['cada']} min" for t in horario["tramos"])
        partes.append(f"{horario['nombre']}: {ritmos}")
    if not partes:
        return f"Hoy ({DIAS.get(dia, dia)}) no se vigila."
    cuantas = len(momentos(dia, ajustes))
    return f"Hoy ({DIAS.get(dia, dia)}) · " + " · ".join(partes) + f" · {cuantas} comprobaciones"


def main(argv: list[str] | None = None) -> int:
    """El horario desde la línea de órdenes, que es como lo consulta vigilar.sh.

        python -m monitor.horario que-hacer <dia> <reloj>
        python -m monitor.horario siguiente <dia> <reloj>
        python -m monitor.horario resumen   <dia>

    El día (1 lunes … 7 domingo) y el reloj (minutos desde medianoche) los pasa
    el guion, que es quien sabe la hora de España; así este módulo no depende de
    la zona horaria de la máquina.
    """
    ap = argparse.ArgumentParser(description="Horario de vigilancia del monitor")
    ap.add_argument("orden", choices=["que-hacer", "siguiente", "resumen", "momentos"])
    ap.add_argument("dia", type=int)
    ap.add_argument("reloj", type=int, nargs="?", default=0)
    args = ap.parse_args(argv)

    ajustes = aj.cargar()
    if args.orden == "que-hacer":
        print(que_hacer(args.dia, args.reloj, ajustes))
    elif args.orden == "siguiente":
        marca = siguiente_minuto(args.dia, args.reloj, ajustes)
        # «fin» y no una línea vacía: el guion tiene que distinguir «hoy ya no
        # hay más» de «esta orden se ha roto y no ha contestado nada».
        print("fin" if marca is None else marca)
    elif args.orden == "momentos":
        print(" ".join(aj.reloj(m) for m in momentos(args.dia, ajustes)))
    else:
        print(resumen(args.dia, ajustes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
