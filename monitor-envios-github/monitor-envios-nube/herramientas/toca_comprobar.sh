#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# ¿Toca comprobar el portal ahora mismo?
#
# Vive en un fichero aparte, y no dentro del workflow, para poder probarlo: esta
# decisión ya falló una vez en silencio —GitHub dejó de disparar bien el cron y
# el monitor estuvo un viernes entero sin comprobar nada— y un fallo mudo no
# puede repetirse sin que salte una prueba.
#
# El horario se define por el HUECO entre comprobaciones, no por el minuto en
# que GitHub dispare. GitHub retrasa y se salta ejecuciones cuando va cargado,
# así que el cron dispara de más (cada cuarto de hora) y aquí se decide:
#
#   · lunes a viernes, de 8:30 a 18:00 (hora de España)
#   · hasta las 10:30 → una comprobación cada 15 min
#   · a partir de las 10:30 → una cada hora
#
# Escribe «toca=si|no» en $GITHUB_OUTPUT (o en la salida, si se ejecuta a mano)
# y explica el motivo por la salida de error, que es lo que se lee en el log.
#
# Para las pruebas se pueden forzar los tres datos de entrada:
#   PRUEBA_DIA (1 lunes … 7 domingo), PRUEBA_RELOJ (minutos desde medianoche),
#   PRUEBA_DESDE (minutos desde la última comprobación).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

FRANJA_INICIO=510     # 8:30
FRANJA_CUARTOS=630    # 10:30, hasta aquí se comprueba cada cuarto de hora
FRANJA_FIN=1080       # 18:00 (media hora de margen sobre la última, la de 17:30)
HUECO_CUARTOS=13      # margen abajo: un disparo un pelín adelantado sigue valiendo
HUECO_HORA=50

dia=${PRUEBA_DIA:-$(TZ=Europe/Madrid date +%u)}
if [ -n "${PRUEBA_RELOJ:-}" ]; then
  reloj=$PRUEBA_RELOJ
else
  reloj=$(( $(TZ=Europe/Madrid date +%-H) * 60 + $(TZ=Europe/Madrid date +%-M) ))
fi

if [ -n "${PRUEBA_DESDE:-}" ]; then
  desde=$PRUEBA_DESDE
  ultima="(forzada en la prueba)"
else
  # La marca de tiempo va en claro dentro del fichero de datos justo para esto:
  # así se sabe cuándo fue la última comprobación sin necesidad de la clave.
  ultima=$(jq -r '.ts // empty' docs/datos.json 2>/dev/null || true)
  if [ -n "$ultima" ]; then
    desde=$(( ( $(date -u +%s) - $(date -u -d "$ultima" +%s) ) / 60 ))
  else
    desde=99999
    ultima="(no hay marca: se comprueba)"
  fi
fi

if [ "$reloj" -le "$FRANJA_CUARTOS" ]; then
  hueco=$HUECO_CUARTOS; franja="8:30 a 10:30, una comprobación cada 15 min"
else
  hueco=$HUECO_HORA;    franja="10:30 a 17:30, una comprobación por hora"
fi

toca=si
motivo="Franja de $franja."
if [ "${GITHUB_EVENT_NAME:-manual}" != "schedule" ]; then
  motivo="Lanzada a mano: se comprueba sea la hora que sea."
elif [ "$dia" -gt 5 ]; then
  toca=no; motivo="Fin de semana: no se vigila."
elif [ "$reloj" -lt "$FRANJA_INICIO" ]; then
  toca=no; motivo="Antes de las 8:30: todavía no toca."
elif [ "$reloj" -gt "$FRANJA_FIN" ]; then
  toca=no; motivo="Pasadas las 18:00: por hoy hemos terminado."
elif [ "$desde" -lt "$hueco" ]; then
  toca=no
  motivo="Hace solo ${desde} min de la anterior; en esta franja se comprueba cada ${hueco} min."
fi

printf 'Reloj de España: día %s, %02d:%02d. Última comprobación hace %s min (%s).\n' \
  "$dia" $(( reloj / 60 )) $(( reloj % 60 )) "$desde" "$ultima" >&2
printf '%s\n' "$motivo" >&2
echo "toca=$toca" >> "${GITHUB_OUTPUT:-/dev/stdout}"
