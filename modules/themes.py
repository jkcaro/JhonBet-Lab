"""Módulo: Sistema de temas visuales — CSS dinámico con imágenes de fondo."""

import base64
from io import BytesIO
from pathlib import Path

from PIL import Image

RUTA_ASSETS = Path(__file__).parent.parent / "assets"

# ── Definición de temas ───────────────────────────────────────────────────────
# Cada tema define:
#   - Variables CSS (--xx) para componentes: tarjetas, botones, texto, etc.
#   - imagen_fondo / posicion_fondo: imagen de fondo del tema
#   - rgba_app / rgba_sidebar: superposición semitransparente sobre la imagen
#     (alpha más bajo = imagen más visible, más alto = imagen más sutil)

TEMAS: dict[str, dict] = {
    "Élite Oscuro": {
        "--bg-principal":      "#08081A",
        "--bg-sidebar":        "#0E0E24",
        "--bg-tarjeta":        "#12122C",
        "--borde":             "#2A2060",
        "--texto":             "#EDE0FF",
        "--texto-apagado":     "#8070AA",
        "--acento-azul":       "#BB86FC",
        "--acento-dorado":     "#FFD700",
        "--acento-verde":      "#CF6679",
        "--acento-rojo":       "#E74C3C",
        "--bg-elemento":       "#1C1A3C",
        "--bg-alerta-exito":   "#1A0A30",
        "--bg-alerta-peligro": "#2D0F0F",
        "--boton-bg":          "linear-gradient(135deg, #4A235A, #9B59B6)",
        "--logo-color":        "#FFD700",
        "imagen_fondo":        "CR7.0.webp",
        "posicion_fondo":      "right center",
        "rgba_app":            "rgba(8, 8, 26, 0.92)",     # 8% imagen visible
        "rgba_sidebar":        "rgba(14, 14, 36, 0.97)",
    },
    "Verde Deportivo": {
        "--bg-principal":      "#040D08",
        "--bg-sidebar":        "#060F0A",
        "--bg-tarjeta":        "#091A0F",
        "--borde":             "#0F3020",
        "--texto":             "#DAFFF0",
        "--texto-apagado":     "#4A8A60",
        "--acento-azul":       "#00DDFF",
        "--acento-dorado":     "#00FF88",
        "--acento-verde":      "#00FF88",
        "--acento-rojo":       "#FF4466",
        "--bg-elemento":       "#0A1F12",
        "--bg-alerta-exito":   "#041A0A",
        "--bg-alerta-peligro": "#2D0A10",
        "--boton-bg":          "linear-gradient(135deg, #005522, #00AA55)",
        "--logo-color":        "#00FF88",
        "imagen_fondo":        "jugador-futbol-futurista-luces.avif",
        "posicion_fondo":      "center center",
        "rgba_app":            "rgba(4, 13, 8, 0.92)",     # 8% imagen visible
        "rgba_sidebar":        "rgba(6, 15, 10, 0.97)",
    },
    "Azul Profesional": {
        "--bg-principal":      "#090D18",
        "--bg-sidebar":        "#0C1020",
        "--bg-tarjeta":        "#101828",
        "--borde":             "#1A2540",
        "--texto":             "#D0E8FF",
        "--texto-apagado":     "#5A7A9A",
        "--acento-azul":       "#4FC3F7",
        "--acento-dorado":     "#4FC3F7",
        "--acento-verde":      "#00E676",
        "--acento-rojo":       "#EF5350",
        "--bg-elemento":       "#162030",
        "--bg-alerta-exito":   "#0A1A28",
        "--bg-alerta-peligro": "#1A0808",
        "--boton-bg":          "linear-gradient(135deg, #0D2A5A, #1565C0)",
        "--logo-color":        "#4FC3F7",
        "imagen_fondo":        "CR7.jpg",
        "posicion_fondo":      "right bottom",
        "rgba_app":            "rgba(9, 13, 24, 0.92)",    # 8% imagen visible
        "rgba_sidebar":        "rgba(12, 16, 32, 0.97)",
    },
}

NOMBRES_TEMAS = list(TEMAS.keys())
TEMA_DEFAULT  = "Azul Profesional"


# ── Carga de imágenes ─────────────────────────────────────────────────────────

def _imagen_a_base64(nombre: str, max_px: tuple[int, int] = (1400, 900)) -> str | None:
    """
    Carga la imagen desde assets/, la redimensiona y devuelve un data-URI base64.
    Devuelve None si el archivo no existe o Pillow no puede abrirlo.
    """
    ruta = RUTA_ASSETS / nombre
    if not ruta.exists():
        return None
    try:
        with Image.open(ruta) as img:
            modo = "RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB"
            img  = img.convert(modo)
            img.thumbnail(max_px, Image.LANCZOS)
            buf  = BytesIO()
            if modo == "RGBA":
                img.save(buf, format="PNG", optimize=True)
                mime = "image/png"
            else:
                img.save(buf, format="JPEG", quality=75, optimize=True)
                mime = "image/jpeg"
            b64 = base64.b64encode(buf.getvalue()).decode()
            return f"data:{mime};base64,{b64}"
    except Exception as exc:
        print(f"[Temas] No se pudo procesar '{nombre}': {exc}")
        return None


# Cache en memoria: la imagen se convierte una sola vez por sesión
_cache_img: dict[str, str | None] = {}


def _img(nombre: str) -> str | None:
    if nombre not in _cache_img:
        _cache_img[nombre] = _imagen_a_base64(nombre)
    return _cache_img[nombre]


# ── Generador de CSS ──────────────────────────────────────────────────────────

def css_tema(nombre_tema: str = "") -> str:
    """
    Devuelve un bloque <style> con las variables CSS del tema seleccionado.
    Aplica colores, fondos de tarjeta, botones y fondo de pantalla.
    Sin imágenes de fondo para evitar problemas de rendimiento/z-index.
    """
    t = TEMAS.get(nombre_tema, TEMAS[TEMA_DEFAULT])

    # Solo extraemos las variables CSS (claves que empiezan con --)
    vars_css = "\n".join(
        f"    {k}: {v};"
        for k, v in t.items() if k.startswith("--")
    )

    bg       = t.get("--bg-principal", "#0a0f1a")
    bg_card  = t.get("--bg-tarjeta",   "#111820")
    borde    = t.get("--borde",        "#1e3a2a")
    verde    = t.get("--acento-verde", "#00aa44")
    boton    = t.get("--boton-bg",     "#00aa44")

    return f"""<style>
:root {{
{vars_css}
}}

/* ── Fondo principal del tema ── */
html, body,
[data-testid="stApp"],
[data-testid="stAppViewContainer"] {{
    background-color: {bg} !important;
    color: var(--texto) !important;
}}
[data-testid="stHeader"] {{
    background-color: {bg} !important;
}}

/* ── Tarjetas con color del tema ── */
.tarjeta {{
    background-color: {bg_card} !important;
    border-color: {borde} !important;
}}

/* ── Botones con color del tema ── */
.stButton > button,
.stFormSubmitButton > button {{
    background: {boton} !important;
    color: #ffffff !important;
    border-color: {verde}88 !important;
}}
</style>"""


def css_tema_unused(nombre_tema: str) -> str:
    """Versión con imágenes de fondo — archivada."""
    """
    Devuelve un bloque <style> para inyectar con st.markdown().

    Estrategia de fondos múltiples CSS:
      background: <overlay-rgba>, url("imagen") cover center / no-repeat fixed;
      La primera capa (overlay) va ENCIMA de la imagen.
      Todo ocurre en el mismo elemento — sin z-index, sin pseudo-elementos,
      sin overflow ni problemas de capas con Streamlit.
    """
    t = TEMAS.get(nombre_tema, TEMAS[TEMA_DEFAULT])

    # Bloque :root con variables CSS del tema
    vars_css = "\n".join(
        f"    {k}: {v};" for k, v in t.items() if k.startswith("--")
    )

    uri          = _img(t.get("imagen_fondo", ""))
    posicion     = t.get("posicion_fondo", "center center")
    # Overlay muy opaco → imagen apenas visible (~8%)
    rgba_app     = t.get("rgba_app",     "rgba(10,15,26,0.92)")
    rgba_sidebar = t.get("rgba_sidebar", "rgba(6,12,18,0.97)")

    if uri:
        bg_app = (
            f"linear-gradient({rgba_app},{rgba_app}),"
            f'url("{uri}") {posicion} / cover no-repeat fixed'
        )
        bg_sidebar = (
            f"linear-gradient({rgba_sidebar},{rgba_sidebar}),"
            f'url("{uri}") {posicion} / cover no-repeat fixed'
        )
    else:
        bg_app     = rgba_app
        bg_sidebar = rgba_sidebar

    return f"""<style>
:root {{
{vars_css}
}}

/* ── Fondos del tema ── */
html, body {{ background-color: var(--bg-principal) !important; }}

[data-testid="stApp"],
[data-testid="stAppViewContainer"] {{
    background: {bg_app} !important;
    background-color: transparent !important;
}}
[data-testid="stHeader"] {{
    background: {bg_app} !important;
    background-color: transparent !important;
}}
[data-testid="stSidebar"] {{
    background: {bg_sidebar} !important;
    background-color: transparent !important;
}}

/* ── Sin backdrop-filter: evita stacking context en dropdowns ── */
[data-testid="stSidebar"],
[data-testid="stApp"],
[data-testid="stAppViewContainer"],
.tarjeta {{
    backdrop-filter: none !important;
    -webkit-backdrop-filter: none !important;
}}

/* ── Dropdowns siempre al frente ── */
[data-baseweb="popover"], [data-baseweb="menu"],
div[role="listbox"], div[role="tooltip"] {{
    z-index: 99999 !important;
}}
</style>"""
