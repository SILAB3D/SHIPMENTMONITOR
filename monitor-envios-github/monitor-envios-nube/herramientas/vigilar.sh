#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Vigila el portal durante toda la jornada, dentro de UNA SOLA ejecución.
#
# Por qué esto no es un cron normal
# ---------------------------------
# Porque el cron de GitHub dejó de cumplir. Los números de este repositorio, con
# la misma configuración que antes funcionaba:
#
#     miércoles 26  →  20 ejecuciones programadas
#     jueves    27  →   1
#     viernes   28  →   4   (y las cuatro de noche)
#     lunes     31  →   2   (a las 13:59 y a las 20:51)
#
# Se pidieran 12 al día o 44, GitHub servía entre una y cuatro, a la hora que le
# parecía. Es su comportamiento documentado —los eventos `schedule` son «best
# effort» y se retrasan o se descartan cuando la plataforma va cargada— y no hay
# expresión de cron que lo arregle: el problema no es CUÁNDO se pide, es que no
# se sirve.
#
# Así que el disparo deja de marcar el ritmo. Una ejecución se queda despierta y
# comprueba el portal ella misma durante horas, con el ritmo que toque:
#
#     · de 8:30 a 10:30 → cada 15 minutos
#     · de 10:30 a 17:30 → cada hora
#
# Con que GitHub sirva UN disparo por la mañana, el día queda cubierto. Si sirve
# más, se encolan detrás (concurrency lo garantiza) y continúan donde lo dejó la
# anterior. Y «Run workflow» a mano ya no vale para una comprobación suelta:
# arranca la vigilancia del resto del día.
#
# Variables para las pruebas: VIGILAR_SOLO_FUNCIONES=1 carga las funciones sin
# ejecutar nada.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail        # -e NO: que falle una comprobación no puede tumbar el día

INICIO=510              # 8:30, primera comprobación
CUARTOS_HASTA=630       # 10:30, hasta aquí cada cuarto de hora
FIN=1050                # 17:30, última comprobación
ESPERA_ARRANQUE=90      # si faltan menos que esto para las 8:30, se espera
MARGEN_FINAL=30         # se admite arrancar hasta media hora después de las 17:30
MAX_MINUTOS=${VIGILAR_MAX_MINUTOS:-320}   # 5 h 20, por debajo del tope de 6 h de GitHub

reloj_ahora() { echo $(( $(TZ=Europe/Madrid date +%-H) * 60 + $(TZ=Europe/Madrid date +%-M) )); }
dia_ahora()   { TZ=Europe/Madrid date +%u; }
hhmm()        { printf '%02d:%02d' $(( $1 / 60 )) $(( $1 % 60 )); }

# Minuto de la siguiente comprobación. La de las 17:30 se clava siempre: es la
# que cierra el día y no se puede quedar en las 17:00 por redondear.
siguiente_minuto() {
  local ahora=$1 paso
  if [ "$ahora" -lt "$CUARTOS_HASTA" ]; then paso=15; else paso=60; fi
  local siguiente=$(( ahora + paso ))
  if [ "$ahora" -lt "$FIN" ] && [ "$siguiente" -gt "$FIN" ]; then siguiente=$FIN; fi
  echo "$siguiente"
}

# ¿Qué hacer con una ejecución que arranca a esta hora de este día?
#   vigilar | esperar <minutos> | salir <motivo>
que_hacer() {
  local dia=$1 ahora=$2
  if [ "$dia" -gt 5 ]; then echo "salir Fin de semana: no se vigila."; return; fi
  if [ "$ahora" -lt "$INICIO" ]; then
    local faltan=$(( INICIO - ahora ))
    if [ "$faltan" -le "$ESPERA_ARRANQUE" ]; then
      echo "esperar $faltan"
    else
      echo "salir Faltan ${faltan} min para las 8:30: demasiado pronto para quedarse esperando."
    fi
    return
  fi
  if [ "$ahora" -gt $(( FIN + MARGEN_FINAL )) ]; then
    echo "salir Pasada la jornada (última comprobación, las 17:30)."; return
  fi
  echo "vigilar"
}

[ -n "${VIGILAR_SOLO_FUNCIONES:-}" ] && return 0 2>/dev/null || true

# ─────────────────────────── la jornada ───────────────────────────

guardar() {
  # datos.json es un volcado generado, no código: fusionarlo línea a línea no
  # tiene sentido. Nos colocamos sobre la punta remota y escribimos encima
  # nuestra versión, que es la lectura más reciente del portal.
  [ -f docs/datos.json ] || { echo "  (no se generó docs/datos.json)"; return 0; }
  local intento
  for intento in 1 2 3; do
    git fetch --quiet origin "+refs/heads/${GITHUB_REF_NAME}:refs/remotes/origin/${GITHUB_REF_NAME}"
    git reset --quiet --mixed "origin/${GITHUB_REF_NAME}"
    # -f a propósito: el .gitignore esconde este fichero para que los datos de
    # demostración no se suban por descuido; aquí es justo lo que hay que guardar.
    git add -f docs/datos.json
    if git diff --staged --quiet; then echo "  sin cambios que guardar"; return 0; fi
    git commit --quiet -m "datos: $(date -u +%Y-%m-%dT%H:%MZ)"
    if git push --quiet origin "HEAD:${GITHUB_REF_NAME}"; then echo "  datos guardados"; return 0; fi
    echo "  otra ejecución se adelantó; reintento ${intento} de 3"
  done
  echo "::warning::No se pudieron guardar los datos tras 3 intentos."
}

comprobar() {
  echo "── $(TZ=Europe/Madrid date '+%H:%M') · comprobando el portal"
  if python -m monitor.ejecutar; then fallos=0; else
    fallos=$(( fallos + 1 ))
    echo "::warning::La comprobación falló (van ${fallos} seguidas)."
  fi
  guardar
}

arranque=$(date +%s)
fallos=0
comprobaciones=0
evento=${GITHUB_EVENT_NAME:-manual}

cerrar() {
  echo "Jornada cerrada: ${comprobaciones} comprobación(es), ${fallos} fallo(s) seguidos al final."
  { echo "comprobaciones=${comprobaciones}"; echo "fallos=${fallos}"; } >> "${GITHUB_OUTPUT:-/dev/stdout}"
  exit 0
}

read -r accion resto <<< "$(que_hacer "$(dia_ahora)" "$(reloj_ahora)")"

# Lanzada a mano se comprueba SIEMPRE, sea la hora que sea: si alguien pulsa el
# botón es porque quiere mirar el portal ahora, no dentro de doce horas. Si
# además cae en jornada, se queda vigilando el resto del día.
if [ "$evento" != "schedule" ]; then
  echo "Lanzada a mano: se comprueba ahora mismo."
  comprobar
  comprobaciones=1
  if [ "$accion" != "vigilar" ]; then echo "$resto No hay jornada que vigilar."; cerrar; fi
else
  case "$accion" in
    salir)   echo "$resto"; cerrar ;;
    esperar) echo "Aún no son las 8:30; esperando ${resto} min para empezar la jornada."
             sleep $(( resto * 60 )) ;;
  esac
fi

echo "Vigilancia en marcha. Hoy: cada 15 min hasta las 10:30 y cada hora hasta las 17:30."

# Una comprobación por vuelta, y a dormir hasta la siguiente. Si la ejecución
# venía lanzada a mano ya se comprobó antes de entrar aquí, así que esa primera
# vuelta se salta la comprobación y va directa a esperar.
saltar=$comprobaciones
while true; do
  if [ "$saltar" -eq 0 ]; then
    comprobar
    comprobaciones=$(( comprobaciones + 1 ))
  fi
  saltar=0

  ahora=$(reloj_ahora)
  if [ "$ahora" -ge "$FIN" ]; then
    echo "Hecha la comprobación de las $(hhmm "$FIN"): jornada terminada."; break
  fi

  siguiente=$(siguiente_minuto "$ahora")
  espera=$(( (siguiente - ahora) * 60 ))
  transcurrido=$(( ( $(date +%s) - arranque ) / 60 ))
  if [ $(( transcurrido + (espera / 60) )) -ge "$MAX_MINUTOS" ]; then
    echo "Tope de $((MAX_MINUTOS / 60)) h de esta ejecución: lo retoma la siguiente."
    break
  fi

  echo "   siguiente comprobación a las $(hhmm "$siguiente") (en $(( espera / 60 )) min)"
  sleep "$espera"
done

cerrar
