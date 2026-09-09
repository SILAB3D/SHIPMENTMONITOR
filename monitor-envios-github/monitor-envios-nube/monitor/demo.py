"""Datos ficticios para probar el panel sin credenciales (`--demo`).

Imita al portal de verdad, no una tabla cualquiera: los estados son los que
usa DinaPaqWeb («PENDIENTE DE ENTREGAR A TIPSA», «LECTURA EN HUB MADRID»,
«REPARTO»…), el recorrido va del paso más antiguo al más reciente y los envíos
llevan remitente y procedencia. Así, lo que se ve en `--demo` es exactamente lo
que se verá con envíos reales, incluidos los casos raros: entrega parcial,
incidencia y un envío recién grabado sin recorrido todavía.
"""
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta

# Cada guion es un envío posible: (estado final, situaciones que lo llevan ahí).
# Los minutos son el hueco desde la situación anterior.
GUIONES = [
    ("ENTREGADO", [
        ("PENDIENTE DE ENTREGAR A TIPSA", "", 0),
        ("TRANSITO", "", 125),
        ("LECTURA EN HUB SEVILLA", "ALCALÁ DE GUADAIRA", 221),
        ("LECTURA EN HUB MADRID", "SAN FERNANDO DE HENARES", 335),
        ("LEIDO EN DESTINO", "", 322),
        ("REPARTO", "", 27),
        ("LECTURA EN AGENCIA DESTINO SALAMANCA 32", "SALAMANCA", 1),
        ("ENTREGADO", "", 90),
    ]),
    ("REPARTO", [
        ("PENDIENTE DE ENTREGAR A TIPSA", "", 0),
        ("TRANSITO", "", 90),
        ("LECTURA EN HUB MADRID", "SAN FERNANDO DE HENARES", 410),
        ("LEIDO EN DESTINO", "", 180),
        ("REPARTO", "", 35),
    ]),
    ("TRANSITO", [
        ("PENDIENTE DE ENTREGAR A TIPSA", "", 0),
        ("TRANSITO", "", 140),
        ("LECTURA EN HUB BAILEN", "BAILÉN", 260),
    ]),
    ("INCIDENCIA: DESTINATARIO AUSENTE", [
        ("PENDIENTE DE ENTREGAR A TIPSA", "", 0),
        ("TRANSITO", "", 110),
        ("LECTURA EN AGENCIA DESTINO TEATINOS 43", "MÁLAGA", 300),
        ("REPARTO", "", 40),
        ("INCIDENCIA: DESTINATARIO AUSENTE", "MÁLAGA", 95),
    ]),
    ("ENTREGA PARCIAL", [
        ("PENDIENTE DE ENTREGAR A TIPSA", "", 0),
        ("TRANSITO", "", 130),
        ("LECTURA EN HUB MADRID", "SAN FERNANDO DE HENARES", 300),
        ("REPARTO", "", 210),
        ("ENTREGA PARCIAL", "", 75),
    ]),
    # Recién grabado: el portal aún no ha escrito ninguna situación. El panel
    # tiene que aguantarlo sin recorrido y sin horas en el diagrama.
    ("PENDIENTE DE ENTREGAR A TIPSA", []),
]

# El «stepper» del portal resume esas situaciones en cuatro hitos con nombre llano
HITOS = ["Documentado", "En camino", "En reparto", "Entregado"]

REMITENTES = ["HOSPITAL SEVERO OCHOA / HEMATOLOGIA", "LAB. VIDAL", "CLINICA NOVA", "SILAB3D"]
DESTINATARIOS = ["EDIFICIO MULTIUSOS I+D+I", "FARMACIA SOL", "SERV. CITOMETRIA USAL", "TALLERES RUIZ"]
ORIGENES = [("LEGANES", "28914"), ("VALENCIA", "46001"), ("SEVILLA", "41001"), ("SALAMANCA", "37007")]
DESTINOS = [("SALAMANCA", "37007"), ("MADRID", "28001"), ("BILBAO", "48001"), ("MÁLAGA", "29010")]


def _marca(momento: datetime) -> str:
    return momento.strftime("%d/%m/%y %H:%M:%S")


def envios_demo(semilla: int = 0, cuantos: int = 6) -> list[dict]:
    rnd = random.Random(semilla)
    ahora = datetime.now()
    envios: list[dict] = []

    for i in range(cuantos):
        estado_final, guion = GUIONES[(i + semilla) % len(GUIONES)]
        alta = ahora - timedelta(days=rnd.randint(0, 5), hours=rnd.randint(0, 20))

        pasos, momento = [], alta
        for estado, lugar, minutos in guion:
            momento += timedelta(minutes=minutos)
            pasos.append({"ts": _marca(momento), "estado": estado, "lugar": lugar})

        # Los hitos se derivan del recorrido, igual que hace el portal
        hitos = []
        for etiqueta, marcas in zip(HITOS, [
            [p for p in pasos if "PENDIENTE" in p["estado"]],
            [p for p in pasos if "TRANSITO" in p["estado"] or "LECTURA" in p["estado"]],
            [p for p in pasos if p["estado"] == "REPARTO"],
            [p for p in pasos if p["estado"].startswith("ENTREGA")],
        ]):
            if marcas:
                hitos.append({"ts": marcas[0]["ts"], "estado": etiqueta})

        origen, cp_origen = ORIGENES[i % len(ORIGENES)]
        destino, cp_destino = DESTINOS[i % len(DESTINOS)]
        campos = {
            "referencia": f"02800102800170251{11800 + i}",
            "fecha": alta.strftime("%d/%m/%y"),
            "estado": estado_final,
            "destinatario": DESTINATARIOS[i % len(DESTINATARIOS)],
            "localidad": destino,
            "remitente": REMITENTES[i % len(REMITENTES)],
            "localidad_origen": origen,
            "cp_origen": cp_origen,
            "ref_cliente": f"CD-CIRCUIT {570000 + i * 37}",
            "bultos": str(rnd.randint(1, 4)),
            "kilos": f"{rnd.uniform(0.5, 18):.2f}",
        }
        if pasos:
            campos["fecha_estado"] = pasos[-1]["ts"]
        if estado_final.startswith("ENTREGA"):
            campos["entrega"] = pasos[-1]["ts"]
        if "INCIDENCIA" in estado_final:
            campos["observaciones"] = "Se reintenta la entrega al día siguiente"

        huella = "|".join(f"{k}={campos[k]}" for k in sorted(campos)) + str(len(pasos))
        envios.append({
            "id": campos["referencia"],
            "campos": campos,
            "pasos": pasos,
            "hitos": hitos,
            "guid": f"DEMO-{i:04d}",
            "crudo": [campos["referencia"], campos["fecha"], estado_final],
            "hash": hashlib.sha1(huella.encode()).hexdigest(),
        })
    return envios
