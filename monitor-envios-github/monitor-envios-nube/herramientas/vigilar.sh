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
# comprueba el portal ella misma durante horas, con el ritmo que toque. Con que
# GitHub sirva UN disparo por la mañana, el día queda cubierto. Si sirve más, se
# encolan detrás (concurrency lo garantiza) y continúan donde lo dejó la
# anterior. Y «Run workflow» a mano ya no vale para una comprobación suelta:
# arranca la vigilancia del resto del día.
#
# El horario ya no está escrito aquí
# ----------------------------------
# Los días, los tramos y la frecuencia se configuran desde la pestaña Ajustes
# del panel y viven en docs/ajustes.json. Este guion no sabe de horas: pregunta
# a `python -m monitor.horario`, que combina todas las configuraciones activas
# (ver monitor/horario.py). Si el fichero falta o viene roto, ese módulo cae al
# horario de siempre: lunes a viernes, cada 15 min hasta las 10:30 y cada hora
# hasta las 17:30.
#
# Variables para las pruebas: VIGILAR_SOLO_FUNCIONES=1 carga las funciones sin
# ejecutar nada.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail        # -e NO: que falle una comprobación no puede tumbar el día

MAX_MINUTOS=${VIGILAR_MAX_MINUTOS:-320}   # 5 h 20, por debajo del tope de 6 h de GitHub
PYTHON=${VIGILAR_PYTHON:-python}

reloj_ahora() { echo $(( $(TZ=Europe/Madrid date +%-H) * 60 + $(TZ=Europe/Madrid date +%-M) )); }
dia_ahora()   { TZ=Europe/Madrid date +%u; }
hhmm()        { printf '%02d:%02d' $(( $1 / 60 )) $(( $1 % 60 )); }

# Las tres preguntas que el horario contesta. La hora la pone este guion, que es
# quien sabe la de España; el módulo solo hace cuentas con ella.
que_hacer()        { "$PYTHON" -m monitor.horario que-hacer "$1" "$2"; }
siguiente_minuto() { "$PYTHON" -m monitor.horario siguiente "$1" "$2"; }
resumen_horario()  { "$PYTHON" -m monitor.horario resumen "$1"; }

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

# Los ajustes se tocan desde el móvil a cualquier hora, y esta ejecución lleva
# despierta desde por la mañana con la copia que traía el checkout. Antes de
# decidir la siguiente comprobación se trae la de la punta de la rama, que es la
# que acaba de guardar el panel. Se desmonta del índice para no arrastrarla al
# commit de los datos.
refrescar_ajustes() {
  git fetch --quiet origin "${GITHUB_REF_NAME:-main}" 2>/dev/null || return 0
  git checkout --quiet "origin/${GITHUB_REF_NAME:-main}" -- docs/ajustes.json 2>/dev/null || return 0
  git reset --quiet -- docs/ajustes.json 2>/dev/null || true
}

comprobar() {
  echo "── $(TZ=Europe/Madrid date '+%H:%M') · comprobando el portal"
  if "$PYTHON" -m monitor.ejecutar; then fallos=0; else
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

dia=$(dia_ahora)
refrescar_ajustes
resumen_horario "$dia"
read -r accion resto <<< "$(que_hacer "$dia" "$(reloj_ahora)")"
# Si la consulta del horario se rompiera, mejor vigilar de más que pasarse el día
# parado sin que nadie se entere: eso ya ocurrió una vez y costó un viernes.
if [ -z "${accion:-}" ]; then
  echo "::warning::El horario no contestó; se vigila igualmente."
  accion=vigilar
fi

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
    esperar) echo "Todavía no ha abierto la jornada; esperando ${resto} min para empezar."
             sleep $(( resto * 60 )) ;;
  esac
fi

echo "Vigilancia en marcha."

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

  refrescar_ajustes
  ahora=$(reloj_ahora)
  siguiente=$(siguiente_minuto "$(dia_ahora)" "$ahora")
  if [ "$siguiente" = "fin" ]; then
    echo "Hecha la última comprobación del día: jornada terminada."; break
  fi
  if [ -z "$siguiente" ]; then
    echo "::warning::No se pudo consultar el horario; se cierra la jornada."; break
  fi

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
