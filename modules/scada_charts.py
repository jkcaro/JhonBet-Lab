"""Módulo: Visualizaciones estilo SCADA industrial para análisis de apuestas."""

import math
import plotly.graph_objects as go
import streamlit as st

# ── Paleta industrial ──────────────────────────────────────────────────────────
BG     = "#0e1117"
PANEL  = "#080c14"
GRID   = "#121c2e"
BORDER = "#1a2540"
GREEN  = "#00ff88"
YELLOW = "#f5a623"
RED    = "#ff4444"
GRAY   = "#1e2d45"
TEXT   = "#5a7a9a"
LIGHT  = "#8eb0cc"

_FONT   = dict(family="'Courier New', monospace", color=LIGHT)
_CONFIG = {"displayModeBar": False, "staticPlot": False}

_LAYOUT = dict(
    paper_bgcolor=BG,
    plot_bgcolor=PANEL,
    font=_FONT,
    margin=dict(l=8, r=8, t=28, b=8),
    showlegend=False,
)

_CSS_COMPACTO = """
<style>
/* ── SCADA: layout denso ── */
.tarjeta                    { padding: 10px 12px !important; margin-bottom: 8px !important; }
.titulo-tarjeta             { font-size: 12px !important; margin-bottom: 8px !important; padding-bottom: 5px !important; }
.fila-prob                  { margin: 3px 0 !important; font-size: 11px !important; }
.etiqueta-seccion           { font-size: 11px !important; margin-bottom: 4px !important; }
.alerta-exito, .alerta-peligro { padding: 7px 10px !important; font-size: 11px !important; }
.caja-stat                  { padding: 6px 10px !important; margin: 3px 0 !important; }
.stat-valor                 { font-size: 13px !important; }
.stat-etiqueta              { font-size: 10px !important; }
[data-testid="stMarkdownContainer"] p { font-size: 12px; line-height: 1.4; }
div[data-testid="column"] { gap: 4px !important; }
</style>
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _xg_de_datos(datos: dict) -> tuple[float, float]:
    probs = datos.get("probabilidades", {})
    return float(probs.get("xg_local", 1.5) or 1.5), float(probs.get("xg_visitante", 1.2) or 1.2)


def _prob1x2(datos: dict) -> tuple[float, float, float, str, str, str]:
    """Devuelve (p_l, p_e, p_v, label_l, label_e, label_v) en %."""
    probs = datos.get("probabilidades", {})
    label_l = label_v = ""
    p_l = p_e = p_v = 0.0
    for k, v in probs.items():
        if k in ("xg_local", "xg_visitante", "over_2.5_goles"):
            continue
        try:
            val = float(str(v).replace("%", ""))
        except ValueError:
            continue
        if k == "empate":
            p_e = val
        elif k.startswith("victoria_") and not label_l:
            p_l, label_l = val, k[9:]
        elif k.startswith("victoria_"):
            p_v, label_v = val, k[9:]
    return p_l, p_e, p_v, label_l or "Local", "Empate", label_v or "Visitante"


# ── Semáforo industrial ───────────────────────────────────────────────────────

def semaforo_html(edge: float, puntuacion: dict | None = None) -> str:
    """Semáforo SCADA. Usa el sistema de puntos si está disponible."""
    if puntuacion:
        estado_raw = puntuacion.get("estado", "NO APOSTAR")
        if puntuacion.get("sin_cuota"):
            subtitulo = "SIN CUOTA"
        else:
            subtitulo = f"PUNTOS {puntuacion.get('puntos', 0)}/4"
    else:
        # Fallback al sistema basado en edge
        estado_raw = "APOSTAR" if edge >= 6 else "NO APOSTAR"
        subtitulo  = f"EDGE {edge:+.1f}%"

    # Clase/variable del pulso — SOLO el LED verde activo (APOSTAR) queda
    # "vivo" permanentemente; es la única señal que lo amerita. Los otros
    # 2 estados usan el glow estático de siempre, sin animación.
    clase_g, var_g = "", ""
    if estado_raw == "APOSTAR":
        estado, col_txt = "APOSTAR", GREEN
        r, a, g = "#150404", "#141200", GREEN
        glow_r = glow_a = "none"
        glow_g = f"0 0 10px {GREEN}, 0 0 20px {GREEN}44"
        clase_g, var_g = "jbl-led-pulse", f"--jbl-glow:{GREEN};"
    elif estado_raw == "PRECAUCIÓN":
        estado, col_txt = "PRECAUCIÓN", YELLOW
        r, a, g = "#150404", YELLOW, "#021209"
        glow_r = "none"
        glow_a = f"0 0 10px {YELLOW}, 0 0 20px {YELLOW}44"
        glow_g = "none"
    else:
        estado, col_txt = "NO APOSTAR", RED
        r, a, g = RED, "#141200", "#021209"
        glow_r = f"0 0 10px {RED}, 0 0 20px {RED}44"
        glow_a = glow_g = "none"

    return (
        f'<div class="jbl-fade-in" style="background:{PANEL};border:1px solid {BORDER};border-radius:6px;'
        f'padding:12px 10px;display:flex;flex-direction:column;align-items:center;gap:4px;height:190px;'
        f'justify-content:center;font-family:Courier New,monospace;">'
        f'<div style="font-size:9px;color:{TEXT};letter-spacing:2px;margin-bottom:8px;">SEMÁFORO</div>'
        f'<div style="width:22px;height:22px;border-radius:50%;background:{r};box-shadow:{glow_r};'
        f'border:1px solid {BORDER};"></div>'
        f'<div style="width:4px;height:8px;background:{BORDER};"></div>'
        f'<div style="width:22px;height:22px;border-radius:50%;background:{a};box-shadow:{glow_a};'
        f'border:1px solid {BORDER};"></div>'
        f'<div style="width:4px;height:8px;background:{BORDER};"></div>'
        f'<div class="{clase_g}" style="width:22px;height:22px;border-radius:50%;background:{g};'
        f'box-shadow:{glow_g};border:1px solid {BORDER};{var_g}"></div>'
        f'<div style="font-size:9px;font-weight:700;color:{col_txt};margin-top:10px;letter-spacing:1px;">'
        f'{estado}</div>'
        f'<div style="font-size:8px;color:{TEXT};">{subtitulo}</div>'
        f'</div>'
    )


# ── Donut Ambos Marcan ────────────────────────────────────────────────────────

@st.cache_data
def donut_ambos_marcan(datos: dict) -> go.Figure:
    xg_l, xg_v = _xg_de_datos(datos)
    p_si = (1 - math.exp(-xg_l)) * (1 - math.exp(-xg_v))
    p_no = 1.0 - p_si

    col_si = GREEN if p_si >= 0.5 else GRAY
    col_no = RED   if p_no >= 0.5 else GRAY

    fig = go.Figure(go.Pie(
        labels=["Ambos Marcan — SÍ", "Ambos Marcan — NO"],
        values=[p_si * 100, p_no * 100],
        hole=0.58,
        marker=dict(colors=[col_si, col_no], line=dict(color=BG, width=3)),
        textfont=dict(family="Courier New", size=9, color=BG),
        textinfo="percent",
        hovertemplate="%{label}<br>%{percent:.1%}<extra></extra>",
        direction="clockwise",
    ))
    fig.add_annotation(
        text=f"SÍ<br><b>{p_si*100:.1f}%</b>",
        x=0.5, y=0.5, showarrow=False,
        font=dict(family="Courier New", size=11, color=col_si),
    )
    fig.update_layout(
        **_LAYOUT, height=190,
        title=dict(text="◈ AMBOS MARCAN  (P·Poisson)",
                   font=dict(size=9, color=TEXT, family="Courier New"), x=0.01),
    )
    return fig


# ═══════════════════════════════════════════════════════════════════════════
#  PALETA Y COMPONENTES — rediseño visual estilo DeOP Connect
#  (solo presentación; no recalculan nada, consumen valores ya calculados)
# ═══════════════════════════════════════════════════════════════════════════

DEOP_PETROLEO = "#0d3b4f"
DEOP_DORADO   = "#f5a623"
DEOP_VERDE    = "#16a34a"
DEOP_ROJO     = "#dc2626"
DEOP_GRIS     = "#e2e8f0"
DEOP_TEXTO    = "#5a7a9a"

# ── Paletas por tema (Codere) ──────────────────────────────────────────────
# Los componentes Plotly (gauges, barras) no pueden usar CSS var() — Plotly
# renderiza a SVG con colores ya resueltos en Python. Estas funciones leen
# st.session_state["tema_activo"] y eligen la paleta correspondiente.
# "petroleo"/"dorado": color de marca (bordes/acentos, seguro en cualquier
# fondo). "texto": color de texto de alto contraste sobre "fondo" — NO usar
# "petroleo" para texto, en Codere/Oscuro sería oscuro sobre fondo oscuro.
PALETAS: dict[str, dict[str, str]] = {
    "DeOP Claro":  {"petroleo": "#0d3b4f", "dorado": "#f5a623", "fondo": "#ffffff",  "texto": "#0d3b4f"},
    "DeOP Oscuro": {"petroleo": "#0d3b4f", "dorado": "#f5a623", "fondo": "#1a1a2e",  "texto": "#ffffff"},
    "Codere":      {"petroleo": "#00e676", "dorado": "#00e676", "fondo": "#12121e",  "texto": "#ffffff"},
    "BetVision":   {"petroleo": "#2563EB", "dorado": "#F59E0B", "fondo": "#1E293B",  "texto": "#E2E8F0"},
}


def _paleta_activa() -> dict[str, str]:
    """Paleta del tema visual activo (fallback BetVision si no hay sesión)."""
    return PALETAS.get(st.session_state.get("tema_activo", "BetVision"), PALETAS["BetVision"])


def gauge_donut_gris(valor: float, titulo: str, color: str = DEOP_DORADO,
                      maximo: float = 100.0) -> go.Figure:
    """Donut gris estilo DeOP Connect (CPU/RAM/Disco) para un valor 0-100%."""
    paleta = _paleta_activa()
    valor_clamp = max(0.0, min(float(valor), maximo))
    fig = go.Figure(go.Pie(
        values=[valor_clamp, maximo - valor_clamp],
        hole=0.72,
        marker=dict(colors=[color, DEOP_GRIS], line=dict(color=paleta["fondo"], width=2)),
        textinfo="none",
        hoverinfo="skip",
        direction="clockwise",
        sort=False,
    ))
    fig.add_annotation(
        text=f"<b>{valor_clamp:.0f}%</b>", x=0.5, y=0.56, showarrow=False,
        font=dict(family="Inter, sans-serif", size=22, color=paleta["texto"]),
    )
    fig.add_annotation(
        text=titulo.upper(), x=0.5, y=0.30, showarrow=False,
        font=dict(family="Inter, sans-serif", size=9, color=DEOP_TEXTO),
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=10), height=170, showlegend=False,
    )
    return fig


def semaforo_mini_html(estado: str) -> str:
    """Semáforo compacto de 3 puntos (verde/amarillo/rojo) para filas de lista."""
    if estado == "APOSTAR":
        col_on, idx_on = DEOP_VERDE, 2
    elif estado == "PRECAUCIÓN":
        col_on, idx_on = DEOP_DORADO, 1
    else:
        col_on, idx_on = DEOP_ROJO, 0

    colores = [DEOP_ROJO, DEOP_DORADO, DEOP_VERDE]
    puntos = ""
    for i, col in enumerate(colores):
        activo = i == idx_on
        bg     = col_on if activo else "#e2e8f0"
        glow   = f"box-shadow:0 0 5px {col_on}88;" if activo else ""
        puntos += (
            f'<div style="width:8px;height:8px;border-radius:50%;'
            f'background:{bg};{glow}"></div>'
        )
    return (
        f'<div style="display:flex;flex-direction:column;gap:3px;align-items:center;'
        f'padding:2px;">{puntos}</div>'
    )


def historial_card_css(prefix: str, key: str, incluye_expander: bool = True,
                        max_width: int = 900) -> str:
    """
    CSS compartido de las tarjetas de página de historial (Historial Dominada
    y Estadísticas / Historial Análisis Claude): una sola fila flex-wrap
    (título + badges + [fecha + semáforo]) con `max_width` px — si el
    contenido no cabe en una línea, esa fila puntual envuelve sola, sin
    tocar el resto.

    Cada página instancia esto con su propio prefijo de clase ("dh"/"hc") y
    su propia `key` de st.container() que envuelve el listado, así las
    clases no colisionan entre páginas, pero el CSS base es uno solo: la
    próxima mejora de este patrón se hace aquí una vez, no en cada módulo.
    `max_width` es ajustable por página según cuánto contenido tengan sus
    badges.

    `incluye_expander=False` omite las reglas de `st.expander` y en su
    lugar da al `st.checkbox` de esa página (patrón de lazy-render) el
    mismo left-edge/max-width/aspecto de barra que tendría un expander —
    úsalo si esa página reemplazó el expander nativo por ese patrón.
    """
    if incluye_expander:
        _css_toggle = f"""
/* ── Acordeón "Ver detalles" — pegado, mismo ancho y mismo left-edge que la tarjeta ── */
.st-key-{key} [data-testid="stExpander"] {{
    margin:0 !important; width:100% !important;
    max-width:{max_width}px !important; box-sizing:border-box !important;
}}
.st-key-{key} [data-testid="stExpander"] summary {{
    min-height:0 !important; height:32px !important;
    padding:0 12px !important; font-size:11px !important;
}}
.st-key-{key} [data-testid="stExpander"] summary svg {{ width:13px !important; height:13px !important; }}
.st-key-{key} [data-testid="stExpanderDetails"] {{ padding:10px !important; }}
@media (max-width: 767px) {{
    .st-key-{key} [data-testid="stExpander"] {{ max-width:100% !important; }}
}}
"""
    else:
        _css_toggle = f"""
/* ── Checkbox de lazy-render — misma barra/left-edge/ancho que tendría un expander ── */
.st-key-{key} [data-testid="stCheckbox"] {{
    background:var(--bg-tarjeta) !important; border:1px solid var(--borde) !important;
    border-radius:6px; margin:0 !important; width:100% !important;
    max-width:{max_width}px !important; box-sizing:border-box !important;
    padding:6px 12px !important; min-height:32px;
}}
.st-key-{key} [data-testid="stCheckbox"] label {{ font-size:11px !important; }}
@media (max-width: 767px) {{
    .st-key-{key} [data-testid="stCheckbox"] {{ max-width:100% !important; }}
}}
"""

    return f"""
<style>
.{prefix}-card {{
    background:var(--bg-tarjeta); border:1px solid var(--borde); border-radius:10px;
    border-left:3px solid var(--borde);
    padding:12px 14px; margin:0;
    width:100%; max-width:{max_width}px; box-sizing:border-box;
}}
.{prefix}-row {{
    display:flex; flex-wrap:wrap; align-items:center; gap:10px;
}}
.{prefix}-partido {{
    font-size:13px; font-weight:700; color:var(--acento-morado);
    white-space:nowrap; flex:0 0 auto;
}}
.{prefix}-badges {{
    display:flex; gap:6px; flex-wrap:wrap; align-items:center;
    flex:1 1 auto; min-width:0;
}}
.{prefix}-badge {{
    font-size:11px; font-weight:600; border-radius:6px; height:22px;
    display:inline-flex; align-items:center;
    padding:0 9px; border:1px solid; white-space:nowrap;
}}
.{prefix}-right {{
    display:flex; align-items:center; gap:10px; flex:0 0 auto; margin-left:auto;
}}
.{prefix}-fecha {{ font-size:10px; color:var(--texto-apagado); white-space:nowrap; opacity:.75; }}

@media (max-width: 767px) {{
    .{prefix}-right {{ width:100%; justify-content:space-between; margin-left:0; }}
}}

.st-key-{key} [data-testid="stVerticalBlock"] {{ gap:8px !important; }}
.st-key-{key} [data-testid="stElementContainer"] {{ margin-bottom:0 !important; }}
{_css_toggle}</style>
"""


def historial_card_html(prefix: str, *, color_borde: str, partido: str,
                         fecha: str, estado_norm: str, badges_html: str) -> str:
    """
    Tarjeta de una sola fila flex (título + badges + [fecha + semáforo]),
    usando las clases generadas por historial_card_css() con el mismo
    `prefix`. `badges_html` ya viene renderizado por el llamador (el
    contenido de los badges es específico de cada página).

    La fila es flex-wrap: si título+badges+fecha caben en el max_width de
    la página, queda en una sola línea compacta; si algún registro puntual
    tiene un nombre de equipo muy largo y no cabe, esa fila concreta
    envuelve a una segunda línea sola — sin necesidad de dos layouts
    distintos ni de decidirlo a mano por página.
    """
    return (
        f'<div class="{prefix}-card" style="border-left-color:{color_borde};">'
        f'<div class="{prefix}-row">'
        f'<span class="{prefix}-partido">⚽ {partido}</span>'
        f'<div class="{prefix}-badges">{badges_html}</div>'
        f'<div class="{prefix}-right">'
        f'<span class="{prefix}-fecha">{fecha}</span>'
        f'{semaforo_mini_html(estado_norm)}'
        f'</div>'
        f'</div>'
        f'</div>'
    )


def paginar_lista(lista: list, key: str, por_pagina: int = 15) -> tuple[list, int, int]:
    """
    Pagina `lista` en bloques de `por_pagina`. Guarda la página actual en
    st.session_state[key] para que sobreviva entre reruns. Si la lista se
    encoge (p.ej. por un filtro de texto) y la página guardada queda fuera
    de rango, se recorta automáticamente a la última página válida.

    Devuelve (subset_de_esta_pagina, pagina_actual, total_paginas) — el
    llamador solo itera sobre `subset_de_esta_pagina` y pinta los controles
    con controles_paginacion() usando los otros dos valores.
    """
    total = len(lista)
    total_paginas = max(1, -(-total // por_pagina))  # ceil division
    pagina_actual = st.session_state.get(key, 1)
    pagina_actual = min(max(1, pagina_actual), total_paginas)
    st.session_state[key] = pagina_actual
    ini = (pagina_actual - 1) * por_pagina
    return lista[ini:ini + por_pagina], pagina_actual, total_paginas


def controles_paginacion(key: str, pagina_actual: int, total_paginas: int,
                          sufijo: str = "") -> None:
    """
    Botones Anterior/Siguiente + indicador 'Página X de Y'. No hace nada si
    cabe todo en 1 página. `sufijo` permite pintar los controles dos veces
    (arriba y abajo de la lista) sin chocar los widget keys — ambas
    instancias leen/escriben el mismo `key` de session_state, así que
    quedan sincronizadas.
    """
    if total_paginas <= 1:
        return
    col_prev, col_ind, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.button("⬅ Anterior", key=f"{key}{sufijo}_prev", use_container_width=True,
                     disabled=pagina_actual <= 1):
            st.session_state[key] = pagina_actual - 1
            st.rerun()
    with col_ind:
        st.markdown(
            f'<div style="text-align:center;font-size:12px;color:var(--texto-apagado);'
            f'padding-top:7px;">Página {pagina_actual} de {total_paginas}</div>',
            unsafe_allow_html=True,
        )
    with col_next:
        if st.button("Siguiente ➡", key=f"{key}{sufijo}_next", use_container_width=True,
                     disabled=pagina_actual >= total_paginas):
            st.session_state[key] = pagina_actual + 1
            st.rerun()


def tarjeta_veredicto_html(titulo: str, valor_texto: str, estado: str) -> str:
    """
    Tarjeta de veredicto estilo DeOP con semáforo de estado. El color de
    estado (verde/dorado/rojo) se mantiene literal en los 3 temas — es un
    código semáforo de 3 vías (APOSTAR/PRECAUCIÓN/NO APOSTAR) y perdería su
    significado si "dorado" colapsara al mismo verde que "APOSTAR" en Codere.
    Fondo/texto sí siguen la paleta activa.
    """
    paleta = _paleta_activa()
    if estado == "APOSTAR":
        col, icono = DEOP_VERDE, "🟢"
    elif estado == "PRECAUCIÓN":
        col, icono = DEOP_DORADO, "🟡"
    else:
        col, icono = DEOP_ROJO, "🔴"
    return (
        f'<div class="jbl-fade-in" style="background:{paleta["fondo"]};border:1px solid {DEOP_GRIS};border-left:5px solid {col};'
        f'border-radius:8px;padding:12px 14px;margin-bottom:8px;min-height:96px;">'
        f'<div style="font-size:11px;color:{DEOP_TEXTO};font-weight:700;text-transform:uppercase;'
        f'letter-spacing:.6px;margin-bottom:4px;">⚠️ {titulo}</div>'
        f'<div style="font-size:15px;font-weight:800;color:{paleta["texto"]};margin-bottom:6px;">{valor_texto}</div>'
        f'<div style="display:inline-block;background:{col}1a;border:1px solid {col};border-radius:5px;'
        f'padding:2px 10px;font-size:11px;font-weight:800;color:{col};">{icono} {estado}</div>'
        f'</div>'
    )


def panel_info_partido_html(datos: dict) -> str:
    """Cuadro de información del partido: equipos, xG, ELO, forma reciente."""
    paleta  = _paleta_activa()
    probs   = datos.get("probabilidades", {})
    filas = [
        ("Partido",                  datos.get("partido", "—")),
        ("Liga",                     datos.get("liga", "—")),
        ("xG Local",                 probs.get("xg_local", "—")),
        ("xG Visitante",             probs.get("xg_visitante", "—")),
        ("ELO Local",                datos.get("elo_local", "—")),
        ("ELO Visitante",            datos.get("elo_visit", "—")),
        ("Forma Local (últ. 5)",     datos.get("forma_reciente_local", "—")),
        ("Forma Visitante (últ. 5)", datos.get("forma_reciente_visitante", "—")),
    ]
    filas_html = "".join(
        f'<tr><td style="padding:5px 10px;color:{DEOP_TEXTO};font-size:11px;'
        f'border-bottom:1px solid {DEOP_GRIS};">{label}</td>'
        f'<td style="padding:5px 10px;font-weight:700;color:{paleta["texto"]};font-size:12px;'
        f'border-bottom:1px solid {DEOP_GRIS};">{valor}</td></tr>'
        for label, valor in filas
    )
    return (
        f'<div style="background:{paleta["fondo"]};border:1px solid {DEOP_GRIS};border-radius:8px;'
        f'padding:6px 4px;margin-bottom:8px;">'
        f'<div style="font-size:10px;color:{paleta["texto"]};font-weight:800;letter-spacing:1px;'
        f'padding:6px 10px;text-transform:uppercase;border-bottom:2px solid {paleta["dorado"]};">'
        f'◈ Información del Partido</div>'
        f'<table style="width:100%;border-collapse:collapse;">{filas_html}</table>'
        f'</div>'
    )


def tabla_ultimos_analisis_html(registros: list, limite: int = 8) -> str:
    """Tabla HTML de los últimos partidos analizados con su veredicto."""
    paleta = _paleta_activa()
    if not registros:
        return (
            '<div style="color:#8aaa99;font-size:12px;padding:10px 0;">'
            'Aún no hay análisis registrados.</div>'
        )
    filas_html = ""
    for r in registros[:limite]:
        estado = str(r.get("veredicto", "NO APOSTAR")).upper()
        if "APOSTAR" in estado and "NO" not in estado:
            col = DEOP_VERDE
        elif "PRECAUCIÓN" in estado or "PRECAUCION" in estado:
            col = DEOP_DORADO
        else:
            col = DEOP_ROJO
        filas_html += (
            f'<tr>'
            f'<td style="padding:5px 10px;font-size:11px;color:{paleta["texto"]};font-weight:600;">'
            f'{r.get("partido", "—")}</td>'
            f'<td style="padding:5px 10px;font-size:11px;color:{DEOP_TEXTO};">{r.get("mercado", "—")}</td>'
            f'<td style="padding:5px 10px;font-size:11px;font-weight:700;color:{col};">'
            f'{r.get("veredicto", "—")}</td>'
            f'<td style="padding:5px 10px;font-size:10px;color:#8aaa99;white-space:nowrap;">'
            f'{r.get("fecha_hora", "—")}</td>'
            f'</tr>'
        )
    return (
        f'<div style="background:{paleta["fondo"]};border:1px solid {DEOP_GRIS};border-radius:8px;'
        f'padding:6px 4px;margin-bottom:8px;">'
        f'<div style="font-size:10px;color:{paleta["texto"]};font-weight:800;letter-spacing:1px;'
        f'padding:6px 10px;text-transform:uppercase;border-bottom:2px solid {paleta["dorado"]};">'
        f'◈ Últimos Partidos Analizados</div>'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr>'
        f'<th style="text-align:left;font-size:9px;color:{DEOP_TEXTO};padding:4px 10px;">PARTIDO</th>'
        f'<th style="text-align:left;font-size:9px;color:{DEOP_TEXTO};padding:4px 10px;">MERCADO</th>'
        f'<th style="text-align:left;font-size:9px;color:{DEOP_TEXTO};padding:4px 10px;">VEREDICTO</th>'
        f'<th style="text-align:left;font-size:9px;color:{DEOP_TEXTO};padding:4px 10px;">FECHA</th>'
        f'</tr></thead><tbody>{filas_html}</tbody></table>'
        f'</div>'
    )


def panel_sistema_puntos_deop(puntuacion: dict,
                              condiciones_custom: list | None = None) -> str:
    """
    Panel de sistema de puntos estilo DeOP Connect (card blanca, borde
    petróleo izquierdo): gauge vertical + condiciones con ✅/❌.
    """
    paleta = _paleta_activa()
    puntos = puntuacion.get("puntos", 0)
    edge   = puntuacion.get("edge", 0.0)
    estado = puntuacion.get("estado", "NO APOSTAR")

    if estado == "APOSTAR":
        col_estado = DEOP_VERDE
    elif estado == "PRECAUCIÓN":
        col_estado = DEOP_DORADO
    else:
        col_estado = DEOP_ROJO

    pct = int((puntos / 4) * 100)

    gauge = (
        f'<div style="display:flex;flex-direction:column;align-items:center;'
        f'gap:3px;min-width:32px;">'
        f'<div style="font-size:8px;color:{DEOP_TEXTO};">4</div>'
        f'<div style="width:14px;height:90px;background:{DEOP_GRIS};border:1px solid {DEOP_GRIS};'
        f'border-radius:3px;overflow:hidden;display:flex;flex-direction:column;justify-content:flex-end;">'
        f'<div style="width:100%;height:{pct}%;background:{col_estado};border-radius:2px 2px 0 0;"></div>'
        f'</div>'
        f'<div style="font-size:8px;color:{DEOP_TEXTO};">0</div>'
        f'</div>'
        f'<div style="display:flex;flex-direction:column;justify-content:space-between;'
        f'height:90px;padding:2px 0;margin-left:4px;">'
        f'<div style="font-size:7px;color:{DEOP_VERDE};">4 ✅</div>'
        f'<div style="font-size:7px;color:{DEOP_DORADO};">3 🟡</div>'
        f'<div style="font-size:7px;color:{DEOP_ROJO};">0-2 🔴</div>'
        f'</div>'
    )

    score = (
        f'<div style="display:flex;flex-direction:column;align-items:center;gap:2px;'
        f'padding:0 12px;">'
        f'<div style="font-size:38px;font-weight:900;color:{col_estado};line-height:1;">{puntos}</div>'
        f'<div style="font-size:9px;color:{DEOP_TEXTO};letter-spacing:1px;">/ 4 PTS</div>'
        f'<div style="font-size:10px;font-weight:700;color:{col_estado};letter-spacing:1px;'
        f'margin-top:4px;">{estado}</div>'
        f'<div style="font-size:8px;color:{DEOP_TEXTO};margin-top:2px;">Edge {edge:+.1f}%</div>'
        f'</div>'
    )

    if condiciones_custom is not None:
        condiciones = condiciones_custom
    else:
        condiciones = [
            (f"Edge ≥ 6% ({edge:+.1f}%)",        puntuacion.get("cond_edge_base",  False), "base"),
            ("xG Manual BeSoccer  +2 pts",        puntuacion.get("cond_xg_manual",  False), "pts"),
            (f"BTTS Local ≥ 3/5   +1 pt",         puntuacion.get("cond_btts_local", False), "pts"),
            (f"BTTS Visit. ≥ 3/5  +1 pt",         puntuacion.get("cond_btts_visit", False), "pts"),
            ("Confianza Medio/Alto (informativo)", puntuacion.get("cond_confianza",  False), "info"),
        ]

    conds_html = ""
    for label, ok, tipo in condiciones:
        icono = "✅" if ok else "❌"
        color = DEOP_VERDE if ok else (DEOP_ROJO if tipo == "base" and not ok else DEOP_TEXTO)
        conds_html += (
            f'<div style="display:flex;align-items:center;gap:5px;margin:2px 0;">'
            f'<span style="font-size:10px;">{icono}</span>'
            f'<span style="font-size:11px;color:{color};">{label}</span>'
            f'</div>'
        )

    return (
        f'<div style="background:{paleta["fondo"]};border:1px solid {DEOP_GRIS};'
        f'border-left:5px solid {paleta["petroleo"]};border-radius:8px;padding:12px 14px;'
        f'margin-bottom:8px;">'
        f'<div style="font-size:10px;color:{paleta["texto"]};font-weight:800;letter-spacing:1px;'
        f'text-transform:uppercase;margin-bottom:8px;padding-bottom:5px;'
        f'border-bottom:1px solid {DEOP_GRIS};">◈ Sistema de Puntos</div>'
        f'<div style="display:flex;align-items:center;gap:4px;">'
        f'{gauge}'
        f'{score}'
        f'<div style="flex:1;padding-left:6px;border-left:1px solid {DEOP_GRIS};">'
        f'{conds_html}'
        f'</div>'
        f'</div>'
        f'</div>'
    )


def barras_probabilidad_deop(datos: dict) -> go.Figure:
    """Barras horizontales 1X2 (colores claros) — extrae probabilidades/edge vía _prob1x2()."""
    paleta = _paleta_activa()
    p_l, p_e, p_v, lbl_l, lbl_e, lbl_v = _prob1x2(datos)
    edges = datos.get("edge_por_outcome", {})

    def _tiene_valor(label: str) -> bool:
        for k, v in edges.items():
            try:
                if label.lower() in k.lower() and float(str(v).replace("+", "").replace("%", "")) >= 10:
                    return True
            except ValueError:
                pass
        return False

    labels  = [lbl_v[:14], lbl_e, lbl_l[:14]]
    valores = [p_v, p_e, p_l]
    colores = [DEOP_VERDE if _tiene_valor(lb) else DEOP_GRIS for lb in [lbl_v, lbl_e, lbl_l]]

    fig = go.Figure()
    for lbl, val, col in zip(labels, valores, colores):
        fig.add_trace(go.Bar(
            x=[val], y=[lbl], orientation="h",
            marker=dict(color=col, line=dict(color=paleta["fondo"], width=1)),
            text=f"{val:.1f}%", textposition="inside",
            textfont=dict(family="Inter, sans-serif", size=10,
                          color="#ffffff" if col != DEOP_GRIS else DEOP_TEXTO),
            showlegend=False, name=lbl,
        ))
        fig.add_trace(go.Bar(
            x=[100 - val], y=[lbl], orientation="h",
            marker=dict(color="#f1f5f9", line=dict(color=paleta["fondo"], width=1)),
            showlegend=False, name="", hoverinfo="skip",
        ))

    for tick in range(0, 101, 10):
        fig.add_vline(x=tick, line=dict(color=DEOP_GRIS, width=1, dash="dot"))

    fig.update_layout(
        paper_bgcolor=paleta["fondo"], plot_bgcolor=paleta["fondo"],
        font=dict(family="Inter, sans-serif", color=DEOP_TEXTO),
        margin=dict(l=8, r=8, t=28, b=8), showlegend=False,
        height=120, barmode="stack",
        title=dict(text="Probabilidades 1X2  (verde = valor detectado)",
                   font=dict(size=10, color=paleta["texto"], family="Inter, sans-serif"), x=0.01),
        xaxis=dict(range=[0, 100], tickfont=dict(size=9, color=DEOP_TEXTO, family="Inter, sans-serif"),
                   showgrid=False, showline=True, linecolor=DEOP_GRIS, ticksuffix="%", dtick=20),
        yaxis=dict(tickfont=dict(size=10, color=paleta["texto"], family="Inter, sans-serif"), showgrid=False),
        bargap=0.35,
    )
    return fig


def panel_discrepancia_deop(datos: dict) -> str:
    """
    Tabla de discrepancia BeSoccer vs Codere estilo DeOP Connect (misma
    clase .tabla-cuotas del resto de la app).
    """
    paleta      = _paleta_activa()
    edge_dict   = datos.get("edge_por_outcome", {})
    cuotas_dict = datos.get("cuotas_reales", {})

    if not edge_dict:
        return ""

    def _clasif(e: float) -> tuple[str, str, str]:
        if e >= 6:
            return "🟢", "APUESTA CON VALOR", DEOP_VERDE
        return "🔴", "SIN VALOR", DEOP_ROJO

    def _codere_cuota(key: str) -> float:
        entry = cuotas_dict.get(key, {})
        for campo in ("codere", "mejor_cuota"):
            try:
                v = float(str(entry.get(campo, "0")).replace("N/D", "0"))
                if v > 1.0:
                    return v
            except (ValueError, TypeError):
                pass
        return 0.0

    filas = ""
    for outcome, edge_str in edge_dict.items():
        try:
            edge_val = float(str(edge_str).replace("+", "").replace("%", ""))
        except ValueError:
            continue

        codere     = _codere_cuota(outcome)
        prob_impl  = (1.0 / codere * 100.0) if codere > 1.0 else 0.0
        prob_model = prob_impl * (1 + edge_val / 100)

        emoji, label, col_clasif = _clasif(edge_val)
        col_edge = DEOP_VERDE if edge_val >= 6 else DEOP_ROJO
        etiqueta = outcome.split("—")[-1].strip() if "—" in outcome else outcome

        cuota_txt      = f"{codere:.2f}" if codere > 1.0 else "—"
        prob_model_txt = "—" if prob_model <= 0 else f"{prob_model:.1f}%"
        prob_impl_txt  = "—" if prob_impl  <= 0 else f"{prob_impl:.1f}%"
        span_cuota     = "" if codere <= 1.0 else f' <span style="opacity:.6">@{cuota_txt}</span>'

        filas += (
            f'<tr>'
            f'<td>{etiqueta}</td>'
            f'<td style="color:{DEOP_VERDE};font-weight:700;">{prob_model_txt}</td>'
            f'<td>{prob_impl_txt}{span_cuota}</td>'
            f'<td style="font-weight:800;color:{col_edge};">{edge_val:+.1f}%</td>'
            f'<td style="color:{col_clasif};white-space:nowrap;">{emoji} {label}</td>'
            f'</tr>'
        )

    if not filas:
        return ""

    return (
        f'<div style="background:{paleta["fondo"]};border:1px solid {DEOP_GRIS};border-radius:8px;'
        f'padding:10px 12px;margin-bottom:8px;">'
        f'<div style="font-size:10px;color:{paleta["texto"]};font-weight:800;letter-spacing:1px;'
        f'text-transform:uppercase;margin-bottom:8px;padding-bottom:5px;'
        f'border-bottom:2px solid {paleta["dorado"]};">◈ Discrepancia Modelo vs Cuota Real</div>'
        f'<table class="tabla-cuotas">'
        f'<thead><tr>'
        f'<th style="text-align:left;">Outcome</th><th>Modelo</th><th>Cuota real</th>'
        f'<th>Edge</th><th>Clasificación</th>'
        f'</tr></thead>'
        f'<tbody>{filas}</tbody>'
        f'</table>'
        f'</div>'
    )


# ═══════════════════════════════════════════════════════════════════════════
#  PANELES HMI ADICIONALES — Tabla de edges, xG, forma reciente, balanza ELO
#  (estilo DeOP Connect; consumen solo campos estructurados ya calculados)
# ═══════════════════════════════════════════════════════════════════════════

def gauge_puntos_deop(puntos: int, maximo: int = 4, color: str = DEOP_DORADO) -> go.Figure:
    """Donut estilo DeOP Connect para el sistema de puntos (0-4 pts, sin sufijo %)."""
    paleta = _paleta_activa()
    valor_clamp = max(0, min(int(puntos), maximo))
    fig = go.Figure(go.Pie(
        values=[valor_clamp, maximo - valor_clamp],
        hole=0.72,
        marker=dict(colors=[color, DEOP_GRIS], line=dict(color=paleta["fondo"], width=2)),
        textinfo="none",
        hoverinfo="skip",
        direction="clockwise",
        sort=False,
    ))
    fig.add_annotation(
        text=f"<b>{valor_clamp}/{maximo}</b>", x=0.5, y=0.56, showarrow=False,
        font=dict(family="Inter, sans-serif", size=20, color=paleta["texto"]),
    )
    fig.add_annotation(
        text="PUNTOS", x=0.5, y=0.30, showarrow=False,
        font=dict(family="Inter, sans-serif", size=9, color=DEOP_TEXTO),
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=10), height=170, showlegend=False,
    )
    return fig


def _equipos_de_partido(datos: dict) -> tuple[str, str]:
    """Nombres de local/visitante a partir de datos['partido'] ('Local vs Visitante')."""
    partido = datos.get("partido", "Local vs Visitante")
    partes  = partido.split(" vs ", 1)
    nombre_l = partes[0].strip() if len(partes) > 0 else "Local"
    nombre_v = partes[1].strip() if len(partes) > 1 else "Visitante"
    return nombre_l, nombre_v


def tabla_edges(datos: dict) -> str:
    """
    Tabla HMI de los 3 resultados de "Victoria 1X2" (Local/Empate/Visitante)
    con P.Modelo, cuota y edge — leídos directamente de
    datos["victoria1x2_modelo"] (mismos campos estructurados que ya usan los
    gauges), sin parsear el texto de Claude. Resalta la fila de
    "mejor_seleccion" (el resultado elegido por argmax(edge)).

    Devuelve "" si el mercado analizado no generó victoria1x2_modelo (p.ej.
    mercados BTTS o Más/Menos 1.5 Goles).
    """
    paleta = _paleta_activa()
    modelo = datos.get("victoria1x2_modelo")
    if not modelo:
        return ""

    nombre_l, nombre_v = _equipos_de_partido(datos)
    seleccion = modelo.get("mejor_seleccion", "—")
    edges     = modelo.get("edges", {})

    filas_def = [
        ("Local",     nombre_l,   modelo.get("p_local",      "—"), modelo.get("cuota_local",     "N/D")),
        ("Empate",    "Empate",   modelo.get("p_empate",     "—"), modelo.get("cuota_empate",    "N/D")),
        ("Visitante", nombre_v,   modelo.get("p_visitante",  "—"), modelo.get("cuota_visitante", "N/D")),
    ]

    filas_html = ""
    for clave, etiqueta, p_modelo, cuota in filas_def:
        edge_str = edges.get(clave, "—")
        try:
            edge_val = float(str(edge_str).replace("+", "").replace("%", ""))
            col_edge = DEOP_VERDE if edge_val >= 0 else DEOP_ROJO
            edge_txt = f"{edge_val:+.1f}%"
        except ValueError:
            col_edge = DEOP_TEXTO
            edge_txt = "—"

        es_sel       = clave == seleccion
        estilo_fila  = (
            f'background:{paleta["dorado"]}22;border-left:3px solid {paleta["dorado"]};'
            if es_sel else 'border-left:3px solid transparent;'
        )
        marca_sel = " ⭐" if es_sel else ""
        filas_html += (
            f'<tr style="{estilo_fila}">'
            f'<td style="font-weight:{700 if es_sel else 400};">{etiqueta}{marca_sel}</td>'
            f'<td>{p_modelo}</td>'
            f'<td>{cuota}</td>'
            f'<td style="font-weight:800;color:{col_edge};">{edge_txt}</td>'
            f'</tr>'
        )

    return (
        f'<div style="background:{paleta["fondo"]};border:1px solid {DEOP_GRIS};border-radius:8px;'
        f'padding:10px 12px;margin-bottom:8px;">'
        f'<div style="font-size:10px;color:{paleta["texto"]};font-weight:800;letter-spacing:1px;'
        f'text-transform:uppercase;margin-bottom:8px;padding-bottom:5px;'
        f'border-bottom:2px solid {paleta["dorado"]};">◈ Tabla de Ventajas — ¿Quién gana el partido?</div>'
        f'<table class="tabla-cuotas">'
        f'<thead><tr>'
        f'<th style="text-align:left;">Resultado</th><th>P.Modelo</th><th>Cuota</th><th>Ventaja</th>'
        f'</tr></thead>'
        f'<tbody>{filas_html}</tbody>'
        f'</table>'
        f'</div>'
    )


def panel_xg_comparativo(datos: dict) -> str:
    """
    Panel HMI con dos displays numéricos grandes (xG local/visitante) y una
    barra horizontal comparativa. Lee xG de datos["probabilidades"] vía
    _xg_de_datos() — mismo campo estructurado que ya usa el donut BTTS.
    """
    paleta = _paleta_activa()
    xg_l, xg_v = _xg_de_datos(datos)
    nombre_l, nombre_v = _equipos_de_partido(datos)

    total  = xg_l + xg_v
    pct_l  = (xg_l / total * 100) if total > 0 else 50.0
    pct_v  = 100 - pct_l
    col_l  = DEOP_VERDE if xg_l >= xg_v else DEOP_TEXTO
    col_v  = DEOP_VERDE if xg_v > xg_l  else DEOP_TEXTO

    return (
        f'<div style="background:{paleta["fondo"]};border:1px solid {DEOP_GRIS};border-radius:8px;'
        f'padding:10px 12px;margin-bottom:8px;">'
        f'<div style="font-size:10px;color:{paleta["texto"]};font-weight:800;letter-spacing:1px;'
        f'text-transform:uppercase;margin-bottom:10px;padding-bottom:5px;'
        f'border-bottom:2px solid {paleta["dorado"]};">◈ xG Comparativo</div>'
        f'<div style="display:flex;justify-content:space-around;margin-bottom:10px;">'
        f'<div style="text-align:center;">'
        f'<div style="font-size:11px;color:{paleta["texto"]};">{nombre_l}</div>'
        f'<div style="font-size:30px;font-weight:900;color:{col_l};font-family:Inter,sans-serif;">{xg_l:.2f}</div>'
        f'</div>'
        f'<div style="text-align:center;">'
        f'<div style="font-size:11px;color:{paleta["texto"]};">{nombre_v}</div>'
        f'<div style="font-size:30px;font-weight:900;color:{col_v};font-family:Inter,sans-serif;">{xg_v:.2f}</div>'
        f'</div>'
        f'</div>'
        f'<div style="display:flex;height:10px;border-radius:5px;overflow:hidden;background:{DEOP_GRIS};">'
        f'<div style="width:{pct_l:.1f}%;background:{col_l};"></div>'
        f'<div style="width:{pct_v:.1f}%;background:{col_v};"></div>'
        f'</div>'
        f'</div>'
    )


def panel_forma_reciente(datos: dict) -> str:
    """
    Panel HMI de forma reciente: 5 LEDs circulares por equipo
    (verde=W, gris=D, rojo=L) con la etiqueta del equipo encima.
    Lee datos["forma_reciente_local"] / datos["forma_reciente_visitante"]
    (cadenas "W,D,L,W,W" ya introducidas en el formulario de análisis).
    """
    paleta = _paleta_activa()
    nombre_l, nombre_v = _equipos_de_partido(datos)

    def _parse(campo: str) -> list[str]:
        crudo = str(datos.get(campo, "") or "")
        return [r.strip().upper() for r in crudo.split(",") if r.strip()]

    forma_l = _parse("forma_reciente_local")
    forma_v = _parse("forma_reciente_visitante")

    colores_led = {"W": DEOP_VERDE, "D": DEOP_GRIS, "L": DEOP_ROJO}

    def _leds(forma: list[str]) -> str:
        items = (forma + ["—"] * 5)[:5]
        html = ""
        for r in items:
            col   = colores_led.get(r, "#cbd5e1")
            letra = r if r in colores_led else ""
            html += (
                f'<div style="width:20px;height:20px;border-radius:50%;background:{col};'
                f'display:flex;align-items:center;justify-content:center;'
                f'font-size:9px;font-weight:800;color:#ffffff;'
                f'box-shadow:0 0 5px {col}88;">{letra}</div>'
            )
        return f'<div style="display:flex;gap:5px;">{html}</div>'

    return (
        f'<div style="background:{paleta["fondo"]};border:1px solid {DEOP_GRIS};border-radius:8px;'
        f'padding:10px 12px;margin-bottom:8px;">'
        f'<div style="font-size:10px;color:{paleta["texto"]};font-weight:800;letter-spacing:1px;'
        f'text-transform:uppercase;margin-bottom:10px;padding-bottom:5px;'
        f'border-bottom:2px solid {paleta["dorado"]};">◈ Forma Reciente (últimos 5)</div>'
        f'<div style="display:flex;flex-direction:column;gap:10px;">'
        f'<div><div style="font-size:11px;color:{paleta["texto"]};font-weight:700;margin-bottom:4px;">'
        f'{nombre_l}</div>{_leds(forma_l)}</div>'
        f'<div><div style="font-size:11px;color:{paleta["texto"]};font-weight:700;margin-bottom:4px;">'
        f'{nombre_v}</div>{_leds(forma_v)}</div>'
        f'</div>'
        f'</div>'
    )


def panel_balanza_elo(datos: dict) -> str:
    """
    Panel HMI tipo balanza: barra horizontal con un marcador que se desplaza
    hacia el equipo favorecido por la diferencia de ELO.
    Lee datos["elo_local"] / datos["elo_visit"] (opcionales — solo existen en
    partidos con datos manuales). Si faltan, muestra estado "sin datos".
    """
    paleta = _paleta_activa()
    nombre_l, nombre_v = _equipos_de_partido(datos)
    elo_l = datos.get("elo_local")
    elo_v = datos.get("elo_visit")

    if elo_l is None or elo_v is None:
        contenido = (
            f'<div style="font-size:11px;color:{DEOP_TEXTO};padding:26px 0;text-align:center;">'
            f'Sin datos ELO para este partido</div>'
        )
    else:
        elo_l, elo_v = float(elo_l), float(elo_v)
        diff      = elo_l - elo_v
        rango     = 30.0  # ± puntos ELO que cubren todo el ancho visual de la barra
        pos       = 50.0 + max(-50.0, min(50.0, (diff / rango) * 50.0))
        favorito  = nombre_l if diff > 0 else (nombre_v if diff < 0 else "Equilibrado")
        col_favorito = DEOP_VERDE if abs(diff) > 1 else DEOP_TEXTO
        etiqueta_diff = "" if favorito == "Equilibrado" else f" (+{abs(diff):.0f})"

        contenido = (
            f'<div style="display:flex;justify-content:space-between;font-size:11px;'
            f'color:{paleta["texto"]};margin-bottom:6px;">'
            f'<span>{nombre_l} <b>{elo_l:.0f}</b></span>'
            f'<span>{nombre_v} <b>{elo_v:.0f}</b></span>'
            f'</div>'
            f'<div style="position:relative;height:10px;background:{DEOP_GRIS};border-radius:5px;margin:14px 0 8px;">'
            f'<div style="position:absolute;left:50%;top:-4px;width:1px;height:18px;'
            f'background:{paleta["texto"]};opacity:.4;"></div>'
            f'<div style="position:absolute;left:{pos:.1f}%;top:-5px;width:12px;height:20px;'
            f'transform:translateX(-50%);background:{paleta["dorado"]};border-radius:3px;'
            f'box-shadow:0 0 6px {paleta["dorado"]}88;"></div>'
            f'</div>'
            f'<div style="text-align:center;font-size:11px;font-weight:700;color:{col_favorito};">'
            f'Favorito ELO: {favorito}{etiqueta_diff}</div>'
        )

    return (
        f'<div style="background:{paleta["fondo"]};border:1px solid {DEOP_GRIS};border-radius:8px;'
        f'padding:10px 12px;margin-bottom:8px;">'
        f'<div style="font-size:10px;color:{paleta["texto"]};font-weight:800;letter-spacing:1px;'
        f'text-transform:uppercase;margin-bottom:8px;padding-bottom:5px;'
        f'border-bottom:2px solid {paleta["dorado"]};">◈ Balanza ELO</div>'
        f'{contenido}'
        f'</div>'
    )
