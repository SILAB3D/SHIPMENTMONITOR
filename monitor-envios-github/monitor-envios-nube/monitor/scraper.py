"""Acceso al portal DinaPaqWeb con Playwright, pensado para correr en un runner
de GitHub Actions (máquina limpia en cada ejecución).

Como cada ejecución arranca de cero, la sesión se inicia siempre desde los
Secrets del repositorio: no hay que volver a introducir nada a mano nunca, y por
eso los avisos siguen llegando aunque no tengas ningún equipo encendido.

La navegación evita selectores rígidos: el formulario se localiza por el campo de
contraseña y el listado por el texto del enlace del menú. El portal usa
maquetación antigua, así que se recorren también los `frames`.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta

from playwright.async_api import Frame, Page, async_playwright

from monitor import config
from monitor.parser import parse_envios

log = logging.getLogger("scraper")

RE_BOTON_BUSCAR = re.compile(r"buscar|consultar|aceptar|ver|listar|enviar", re.I)
# Marca entre frames en el HTML que se guarda como artefacto cuando no hay tabla
SEPARADOR_FRAMES = "\n<!-- ---- siguiente frame ---- -->\n"


class PortalError(RuntimeError):
    pass


async def _frame_con_password(page: Page) -> Frame | None:
    for frame in page.frames:
        try:
            if await frame.locator("input[type=password]").count():
                return frame
        except Exception:
            continue
    return None


async def _esperar_frame_con_password(page: Page, ms: int = 15_000) -> Frame | None:
    """Igual que el anterior, pero dando tiempo a que el formulario aparezca.

    DinaPaqWeb no trae el formulario en el HTML: lo pinta ExtJS desde
    `js/login.js` después de cargar la página. Mirar una sola vez nada más
    llegar es una carrera que se pierde casi siempre, y el monitor concluía
    que no había que autenticarse —o, peor, que ya había entrado— cuando en
    realidad seguía en la pantalla de acceso.
    """
    limite = time.monotonic() + ms / 1000
    while True:
        frame = await _frame_con_password(page)
        if frame is not None:
            return frame
        if time.monotonic() >= limite:
            return None
        await page.wait_for_timeout(250)


SELECTOR_TEXTO = (
    "input[type=text], input:not([type]), input[type=tel], "
    "input[type=number], input[type=email]"
)


async def _campos_de_usuario(frame: Frame):
    """Campos de texto del mismo formulario que la contraseña, en orden.

    Se limita al formulario del login para no confundirse con buscadores u otros
    inputs de la página, y sirve igual si el portal pide un solo usuario o dos
    códigos (agencia + cliente).
    """
    formulario = frame.locator("form:has(input[type=password])").first
    if await formulario.count():
        campos = formulario.locator(SELECTOR_TEXTO)
        if await campos.count():
            return campos
    return frame.locator(SELECTOR_TEXTO)


async def _mensaje_de_error(page: Page) -> str:
    """El aviso que enseña el portal cuando el acceso no cuela.

    DinaPaqWeb usa ExtJS, así que el error sale en una ventana flotante
    (`.x-window`) en vez de en el HTML de la página.
    """
    for selector in (".x-window-body", ".x-window", ".error", "#error"):
        try:
            caja = page.locator(selector).first
            if await caja.count() and await caja.is_visible():
                texto = re.sub(r"\s+", " ", (await caja.inner_text()).strip())
                if texto:
                    return texto[:200]
        except Exception:
            continue
    return ""


async def _login(page: Page, frame: Frame) -> None:
    if not config.credenciales_ok():
        raise PortalError(
            "Faltan Secrets: define DINAPAQ_USUARIO (o DINAPAQ_AGENCIA) y DINAPAQ_PASSWORD en el repositorio"
        )

    pwd = frame.locator(config.SEL_PASSWORD or "input[type=password]").first
    valores = [v for v in (config.USUARIO, config.CLIENTE) if v]

    if config.SEL_USUARIO:
        # el usuario tiene selector propio; el segundo campo, si lo hay, también
        await frame.locator(config.SEL_USUARIO).first.fill(valores[0])
        if len(valores) > 1 and config.SEL_CLIENTE:
            await frame.locator(config.SEL_CLIENTE).first.fill(valores[1])
    else:
        campos = await _campos_de_usuario(frame)
        visibles = [i for i in range(await campos.count()) if await campos.nth(i).is_visible()]
        if not visibles:
            raise PortalError("No se encontró ningún campo de usuario junto a la contraseña")
        # un solo hueco y dos códigos: el portal espera agencia y cliente juntos
        if len(visibles) == 1 and len(valores) > 1:
            valores = ["".join(valores)]
        for hueco, valor in zip(visibles, valores):
            await campos.nth(hueco).fill(valor)

    await pwd.fill(config.PASSWORD)

    # ExtJS pinta varios `button` por pantalla (los de las ventanas flotantes que
    # aún no se ven, por ejemplo), así que quedarse con el primero es una
    # lotería. Se busca primero un submit de verdad, luego un botón cuyo texto
    # sea de aceptar, y como último recurso se pulsa Intro.
    for intento in (
        lambda: frame.locator("input[type=submit], button[type=submit]").first,
        lambda: frame.get_by_role("button", name=RE_BOTON_BUSCAR).first,
        lambda: frame.locator("button:visible, .x-btn:visible").first,
    ):
        try:
            boton = intento()
            if await boton.count() and await boton.is_visible():
                await boton.click()
                break
        except Exception:
            continue
    else:
        await pwd.press("Enter")

    await page.wait_for_load_state("networkidle")

    # Aquí no vale mirar una sola vez: si las credenciales no valen, el portal
    # recarga la misma página y ExtJS tarda un momento en repintar el
    # formulario. Comprobando al instante veríamos «no hay formulario» y
    # daríamos el acceso por bueno, para acabar fallando mucho más adelante con
    # un «no se reconoció ninguna tabla» que despista por completo.
    if await _esperar_frame_con_password(page, ms=8_000):
        motivo = await _mensaje_de_error(page)
        raise PortalError(
            "El portal sigue mostrando el formulario de acceso: no aceptó las credenciales.\n"
            + (f"Lo que dice el portal: {motivo}\n" if motivo else "")
            + "Revisa DINAPAQ_USUARIO y DINAPAQ_PASSWORD. Este portal pide «código de agencia + "
              "código de cliente» todo junto como usuario (por ejemplo 02112345); si tienes los "
              "dos números por separado, ponlos unidos en DINAPAQ_USUARIO."
        )


async def _hay_listado(page: Page) -> bool:
    """¿La pantalla actual ya trae envíos reconocibles?"""
    try:
        return bool(parse_envios(await _html_de_todos_los_frames(page)))
    except Exception:  # noqa: BLE001
        return False


async def _ir_al_listado(page: Page) -> None:
    """Busca la pantalla de consulta de envíos por el texto del menú.

    No basta con pulsar el primer enlace que encaje: en estos portales el menú
    suele tener varias entradas parecidas («Envíos», «Consulta de envíos»,
    «Relación de envíos»…) y solo una lleva al listado. Se prueban unas cuantas
    y nos quedamos con la primera que dé envíos de verdad.
    """
    if config.URL_LISTADO:
        if not page.url.startswith(config.URL_LISTADO):
            await page.goto(config.URL_LISTADO, wait_until="domcontentloaded")
        return

    patron = re.compile(config.ENLACE_LISTADO, re.I)
    candidatos: list[tuple[int, str]] = []
    for n_frame, frame in enumerate(page.frames):
        try:
            enlaces = frame.locator("a")
            for i in range(min(await enlaces.count(), 80)):
                texto = re.sub(r"\s+", " ", (await enlaces.nth(i).inner_text()).strip())
                if texto and patron.search(texto):
                    candidatos.append((n_frame, texto))
        except Exception:
            continue

    inicio = page.url
    for n_frame, texto in candidatos[:6]:
        try:
            frames = page.frames
            if n_frame >= len(frames):
                continue
            enlace = frames[n_frame].get_by_role("link", name=texto, exact=True).first
            if not await enlace.count():
                continue
            await enlace.click()
            await page.wait_for_load_state("networkidle")
            await _rellenar_fechas(page)
            if await _hay_listado(page):
                return
            # esa entrada del menú no era: volvemos y probamos la siguiente
            await page.goto(inicio, wait_until="domcontentloaded")
        except Exception:
            try:
                await page.goto(inicio, wait_until="domcontentloaded")
            except Exception:
                return


async def _rellenar_fechas(page: Page) -> None:
    """Si la pantalla de consulta pide un rango de fechas, lo rellena y busca."""
    hasta = datetime.now()
    desde = hasta - timedelta(days=config.DIAS_ATRAS)

    for frame in page.frames:
        try:
            campos = frame.locator("input[type=text], input[type=date]")
            candidatos = []
            for i in range(min(await campos.count(), 30)):
                attr = " ".join(
                    filter(None, [await campos.nth(i).get_attribute("name"), await campos.nth(i).get_attribute("id")])
                ).lower()
                if re.search(r"fec|fech|desde|hasta|ini|fin", attr):
                    candidatos.append((i, attr))
            if not candidatos:
                continue

            for pos, (i, attr) in enumerate(candidatos[:2]):
                valor = desde if (pos == 0 or "desde" in attr or "ini" in attr) else hasta
                tipo = await campos.nth(i).get_attribute("type")
                await campos.nth(i).fill(valor.strftime("%Y-%m-%d" if tipo == "date" else "%d/%m/%Y"))

            botones = frame.locator("input[type=submit], input[type=button], button")
            for i in range(min(await botones.count(), 15)):
                etiqueta = await botones.nth(i).get_attribute("value") or await botones.nth(i).inner_text() or ""
                if RE_BOTON_BUSCAR.search(etiqueta):
                    await botones.nth(i).click()
                    await page.wait_for_load_state("networkidle")
                    return
        except Exception:
            continue


async def _enlaces_visibles(page: Page, tope: int = 60) -> list[str]:
    """Textos de los enlaces del menú, para saber a dónde se podía haber ido."""
    vistos: list[str] = []
    for frame in page.frames:
        try:
            enlaces = frame.locator("a")
            for i in range(min(await enlaces.count(), tope)):
                texto = re.sub(r"\s+", " ", (await enlaces.nth(i).inner_text()).strip())
                if texto and texto not in vistos:
                    vistos.append(texto)
        except Exception:
            continue
    return vistos


def _diagnostico(documentos: list[str], url_final: str, titulo: str, enlaces: list[str],
                 sigue_en_login: bool = False) -> str:
    """Resumen de lo que vio el monitor, para poder arreglarlo sin descargar nada.

    Va dentro del mensaje de error, que acaba en docs/datos.json y por tanto se
    lee desde el propio panel. Antes había que bajarse el artefacto con el HTML
    para saber siquiera en qué pantalla se había quedado.
    """
    from monitor.parser import extraer_tablas, normalizar

    lineas = ["No se reconoció ninguna tabla de envíos.",
              f"Última URL: {url_final}",
              f"Título de la página: {titulo or '(sin título)'}",
              f"Frames: {len(documentos)}"]

    if sigue_en_login:
        # Con diferencia el caso más común, y el que más despista si no se dice:
        # todo lo demás que salga aquí es de la pantalla de acceso, no del portal.
        lineas.append(
            "⚠ SIGUE HABIENDO UN CAMPO DE CONTRASEÑA EN PANTALLA: no se llegó a entrar, "
            "así que lo que ves debajo es la propia página de acceso. Revisa "
            "DINAPAQ_USUARIO y DINAPAQ_PASSWORD antes que ninguna otra cosa."
        )

    tablas = extraer_tablas(documentos)
    if not tablas:
        lineas.append("No hay ninguna tabla en la pantalla: seguramente no se llegó al listado.")
    else:
        lineas.append(f"Tablas encontradas: {len(tablas)}. Sus cabeceras:")
        # las más grandes primero: el listado suele ser la tabla con más filas
        for t in sorted(tablas, key=len, reverse=True)[:4]:
            cabecera = [c for c in (t[0] if t else []) if c][:12]
            lineas.append(f"  · {len(t)} filas → {' | '.join(cabecera) or '(sin cabecera)'}")
        lineas.append(
            "Si alguna de esas es el listado, añade sus títulos de columna a "
            "SINONIMOS en monitor/parser.py."
        )

    if enlaces:
        lineas.append("Enlaces del menú: " + " · ".join(enlaces[:25]))
        lineas.append(
            "Si ves ahí la pantalla de consulta de envíos, entra tú al portal, ábrela "
            "y pon su URL en la variable DINAPAQ_URL_LISTADO."
        )
    return "\n".join(lineas)


async def _html_de_todos_los_frames(page: Page) -> list[str]:
    """El HTML de cada frame por separado: el parser los mira uno a uno."""
    partes = []
    for frame in page.frames:
        try:
            partes.append(await frame.content())
        except Exception:
            continue
    return partes


async def obtener_envios() -> list[dict]:
    """Una pasada completa: entra, navega al listado y devuelve los envíos leídos."""
    async with async_playwright() as pw:
        navegador = await pw.chromium.launch(headless=config.HEADLESS)
        contexto = await navegador.new_context(locale="es-ES", viewport={"width": 1400, "height": 900})
        page = await contexto.new_page()
        page.set_default_timeout(45_000)
        try:
            await page.goto(config.URL_LISTADO or config.URL_LOGIN, wait_until="domcontentloaded")
            # Damos tiempo a que ExtJS pinte el formulario. Si aun así no
            # aparece y tampoco estábamos ya dentro, es un fallo que hay que
            # cantar: antes se seguía adelante en silencio y el error acababa
            # saliendo mucho después, disfrazado de «no hay tabla de envíos».
            frame = await _esperar_frame_con_password(page)
            if frame is not None:
                await _login(page, frame)
            elif not config.URL_LISTADO:
                log.warning(
                    "No apareció ningún campo de contraseña en %s; se sigue por si la sesión ya estaba abierta",
                    page.url,
                )

            await _ir_al_listado(page)
            await _rellenar_fechas(page)
            documentos = await _html_de_todos_los_frames(page)

            envios = parse_envios(documentos)
            if not envios:
                config.CAPTURAS.mkdir(parents=True, exist_ok=True)
                sello = datetime.now().strftime("%Y%m%d-%H%M%S")
                (config.CAPTURAS / f"sin-tabla-{sello}.html").write_text(
                    SEPARADOR_FRAMES.join(documentos), encoding="utf-8"
                )
                try:
                    await page.screenshot(path=str(config.CAPTURAS / f"sin-tabla-{sello}.png"), full_page=True)
                except Exception:  # noqa: BLE001
                    pass

                informe = _diagnostico(
                    documentos, page.url, await page.title(), await _enlaces_visibles(page),
                    sigue_en_login=await _frame_con_password(page) is not None,
                )
                (config.CAPTURAS / f"diagnostico-{sello}.txt").write_text(informe, encoding="utf-8")
                raise PortalError(informe)
            return envios
        finally:
            await contexto.close()
            await navegador.close()
