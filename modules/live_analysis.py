"""
Módulo: Análisis en Vivo — estadísticas en tiempo real + Claude AI.
Dashboard SCADA industrial adaptable a cualquier partido y equipo.
"""

import base64
import json
import os
import re
import streamlit as st
import streamlit.components.v1 as components
import anthropic
from dotenv import load_dotenv

load_dotenv()

API_KEY      = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"

MERCADOS_VIVO = [
    "1X2 (resultado final)",
    "Próximo gol (local / sin gol / visitante)",
    "Over/Under 2.5 Goles",
    "Ambos Marcan",
    "Hándicap en vivo",
    "Corners totales",
    "Tarjetas totales",
    "Resultado al descanso",
]

# ── Paleta DeOP Connect (claro) ────────────────────────────────────────────────
_PANEL  = "#ffffff"
_BORDER = "#e2e8f0"
_GREEN  = "#16a34a"
_YELLOW = "#f5a623"
_RED    = "#dc2626"
_GRAY   = "#e8ecef"
_TEXT   = "#5a7a9a"
_LIGHT  = "#1a2c38"
_GOLD   = "#f5a623"
_BLUE   = "#0d3b4f"
_FONT   = "Inter, sans-serif"

_CSS_VIVO = """
<style>
/* ── DeOP Vivo: grid responsivo ── */
.scada-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 8px;
    margin-bottom: 8px;
}
.scada-panel {
    background: var(--bg-tarjeta);
    border: 1px solid var(--borde);
    border-radius: 8px;
    padding: 10px 12px;
    font-family: 'Inter', sans-serif;
}
.scada-titulo {
    font-size: 10px;
    color: var(--acento-morado);
    font-weight: 800;
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-bottom: 8px;
    padding-bottom: 5px;
    border-bottom: 2px solid var(--acento-dorado);
}
.scada-stat-row {
    display: grid;
    grid-template-columns: 1fr 80px 1fr;
    gap: 4px;
    align-items: center;
    margin: 4px 0;
    font-size: 10px;
}
@media (max-width: 480px) {
    .scada-grid { grid-template-columns: 1fr; }
    .scada-stat-row { grid-template-columns: 1fr 60px 1fr; font-size: 9px; }
}
/* Labels legibles sobre fondo claro (widgets nativos de Streamlit) */
[data-testid="stWidgetLabel"] p {
    color: var(--acento-morado) !important;
    font-weight: 600 !important;
}

/* Inputs numéricos (Minuto, Goles, Posesión, Ataques...) y de texto
   (Partido) — fondo/borde según el tema activo, en vez del fondo oscuro
   por defecto del tema base de Streamlit. */
.stNumberInput input[data-testid="stNumberInputField"],
.stTextInput input {
    background-color: var(--bg-tarjeta) !important;
    border: 1px solid var(--acento-morado) !important;
    color: var(--acento-morado) !important;
}
.stNumberInput input[data-testid="stNumberInputField"]:focus,
.stTextInput input:focus {
    border-color: var(--acento-dorado) !important;
    box-shadow: 0 0 0 1px #f5a62333 !important;
}
.stNumberInput input::placeholder,
.stTextInput input::placeholder {
    color: var(--texto-apagado) !important;
    opacity: 1 !important;
}

/* Botones +/- del number_input — control de "chrome" siempre oscuro con
   ícono blanco (mismo rol que los banners petróleo de otras páginas: no
   seguimos el acento de marca aquí para no perder contraste en Codere,
   donde dorado/petroleo son ambos verde). */
.stNumberInput button,
button[data-testid="stNumberInputStepUp"],
button[data-testid="stNumberInputStepDown"] {
    background-color: #0d3b4f !important;
    border: 1px solid #0d3b4f !important;
    color: #ffffff !important;
}
.stNumberInput button svg,
button[data-testid="stNumberInputStepUp"] svg,
button[data-testid="stNumberInputStepDown"] svg {
    fill: #ffffff !important;
}
</style>
"""


# ── Cancha visual ─────────────────────────────────────────────────────────────

@st.cache_data
def _cancha_b64() -> str:
    """Lee assets/cancha.png y devuelve su contenido en base64 (cacheado)."""
    from pathlib import Path
    ruta = Path(__file__).parent.parent / "assets" / "cancha.png"
    if not ruta.exists():
        return ""
    try:
        return base64.b64encode(ruta.read_bytes()).decode()
    except Exception:
        return ""


def _panel_cancha_html(
    nombre_l: str, nombre_v: str,
    goles_l: int, goles_v: int,
    pos_l: int, pos_v: int,
    tiro_l: int, tiro_v: int,
    b64: str,
) -> str:
    """HTML completo del panel de cancha con overlays CSS (para components.html)."""
    if not b64:
        return ""

    pos_total = pos_l + pos_v
    if pos_total == 0:
        pos_l_pct, pos_v_pct = 50, 50
    else:
        pos_l_pct = round(pos_l / pos_total * 100)
        pos_v_pct = 100 - pos_l_pct

    nl = nombre_l[:13]
    nv = nombre_v[:13]

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:transparent;overflow:hidden}}
.wrap{{
    position:relative;width:400px;max-width:100%;height:250px;
    border-radius:10px;overflow:hidden;font-family:Inter,sans-serif;
}}
.bg{{
    position:absolute;inset:0;
    background-image:url('data:image/png;base64,{b64}');
    background-size:cover;background-position:center;
}}
.dim{{position:absolute;inset:0;background:rgba(0,0,0,.20)}}
.score{{
    position:absolute;top:10px;left:50%;transform:translateX(-50%);
    background:rgba(0,0,0,.72);border-radius:8px;padding:4px 16px;
    color:#fff;font-size:20px;font-weight:900;letter-spacing:2px;white-space:nowrap;
}}
.local{{
    position:absolute;left:14px;top:50%;transform:translateY(-50%);text-align:center;
}}
.visit{{
    position:absolute;right:14px;top:50%;transform:translateY(-50%);text-align:center;
}}
.circ-l,.circ-v{{
    width:52px;height:52px;border-radius:50%;
    border:3px solid rgba(255,255,255,.6);
    display:flex;align-items:center;justify-content:center;
    font-size:22px;font-weight:900;color:#fff;margin:0 auto;
}}
.circ-l{{background:#16a34a;box-shadow:0 0 14px rgba(22,163,74,.65)}}
.circ-v{{background:#dc2626;box-shadow:0 0 14px rgba(220,38,38,.65)}}
.tnm{{
    color:#fff;font-size:10px;font-weight:700;
    text-shadow:0 1px 3px rgba(0,0,0,.9);margin-top:5px;
    max-width:76px;line-height:1.2;
}}
.lbl{{
    position:absolute;top:10px;
    color:#fff;font-size:9px;font-weight:700;
    letter-spacing:.8px;text-transform:uppercase;
    text-shadow:0 1px 3px rgba(0,0,0,.9);opacity:.85;
}}
.lbl-l{{left:14px}}.lbl-v{{right:14px}}
.pos-bar{{position:absolute;bottom:0;left:0;right:0;height:26px;display:flex}}
.pos-l{{
    width:{pos_l_pct}%;background:rgba(22,163,74,.80);
    display:flex;align-items:center;justify-content:center;
    font-size:11px;font-weight:800;color:#fff;
}}
.pos-v{{
    width:{pos_v_pct}%;background:rgba(37,99,235,.80);
    display:flex;align-items:center;justify-content:center;
    font-size:11px;font-weight:800;color:#fff;
}}
</style>
</head>
<body>
<div class="wrap">
  <div class="bg"></div>
  <div class="dim"></div>
  <div class="lbl lbl-l">Tiros</div>
  <div class="lbl lbl-v">Tiros</div>
  <div class="score">{goles_l} &mdash; {goles_v}</div>
  <div class="local">
    <div class="circ-l">{tiro_l}</div>
    <div class="tnm">{nl}</div>
  </div>
  <div class="visit">
    <div class="circ-v">{tiro_v}</div>
    <div class="tnm">{nv}</div>
  </div>
  <div class="pos-bar">
    <div class="pos-l">{pos_l_pct}%</div>
    <div class="pos-v">{pos_v_pct}%</div>
  </div>
</div>
</body>
</html>"""


# ── Cálculos ──────────────────────────────────────────────────────────────────

def _calcular_momentum(pos_l: int, pos_v: int,
                       atq_l: int, atq_v: int,
                       tiro_l: int, tiro_v: int) -> float:
    """
    Fórmula: ((pos_l-50)*0.3 + (atq_l-atq_v)*2 + (tiro_l-tiro_v)*3) / 10
    Resultado entre -10 (dominio visitante) y +10 (dominio local).
    """
    raw = ((pos_l - 50) * 0.3 + (atq_l - atq_v) * 2 + (tiro_l - tiro_v) * 3) / 10.0
    return max(-10.0, min(10.0, raw))


def _campos_rellenos(stats: dict) -> int:
    """Devuelve el número de pares de estadísticas con al menos un valor > 0."""
    count = 0
    for v in stats.values():
        if isinstance(v, dict):
            if (v.get("local") or 0) > 0 or (v.get("visitante") or 0) > 0:
                count += 1
    return count


def _detectar_decision(texto: str) -> str:
    """
    Lee el texto de Claude y detecta la recomendación.
    Prioridad: "no apostar" > "esperar" > "apostar"
    Devuelve: "apostar" | "esperar" | "no_apostar"
    """
    t = texto.lower()
    # Patrones de NO apostar (verificar antes que "apostar" para evitar falsos positivos)
    no_patterns = ["no apostar", "no recomiendo apostar", "evitar apostar",
                   "no es recomendable apostar", "abstenerse"]
    for p in no_patterns:
        if p in t:
            return "no_apostar"
    # Patrones de espera/precaución
    wait_patterns = ["esperar", "espera ", "aguardar", "precaución",
                     "cautela", "no actuar", "observar"]
    for p in wait_patterns:
        if p in t:
            return "esperar"
    # Patrones de apostar
    bet_patterns = ["apostar", "recomiendo apostar", "valor en apostar",
                    "apuesta a", "recomendación: apostar"]
    for p in bet_patterns:
        if p in t:
            return "apostar"
    return "esperar"   # por defecto: cautela


# ── Componentes HTML SCADA ────────────────────────────────────────────────────

def _panel_marcador(nombre_l: str, nombre_v: str,
                    goles_l: int, goles_v: int, minuto: int) -> str:
    """Panel central con marcador, nombres y minuto."""
    return (
        f'<div class="scada-panel" style="text-align:center;">'
        f'<div class="scada-titulo">◈ MARCADOR EN VIVO</div>'
        f'<div style="display:flex;justify-content:center;align-items:center;gap:12px;'
        f'margin:6px 0 4px;">'
        # Local
        f'<div style="flex:1;text-align:right;">'
        f'<div style="font-size:10px;color:{_GOLD};letter-spacing:1px;'
        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
        f'{nombre_l[:14]}</div>'
        f'<div style="font-size:30px;font-weight:900;color:#0d3b4f;line-height:1;">'
        f'{goles_l}</div>'
        f'</div>'
        # Separador
        f'<div style="font-size:20px;color:{_TEXT};">—</div>'
        # Visitante
        f'<div style="flex:1;text-align:left;">'
        f'<div style="font-size:10px;color:{_BLUE};letter-spacing:1px;'
        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
        f'{nombre_v[:14]}</div>'
        f'<div style="font-size:30px;font-weight:900;color:#0d3b4f;line-height:1;">'
        f'{goles_v}</div>'
        f'</div>'
        f'</div>'
        f'<div style="font-size:11px;color:{_GREEN};font-weight:700;'
        f'letter-spacing:2px;">⏱ {minuto}\'</div>'
        f'</div>'
    )


_MAPA_DECISION_ESTADO = {
    "apostar":    "APOSTAR",
    "esperar":    "PRECAUCIÓN",
    "no_apostar": "NO APOSTAR",
}


def _semaforo_vivo(decision: str) -> str:
    """
    Semáforo estilo DeOP Connect — reutiliza semaforo_mini_html() de
    scada_charts.py, envuelto en card blanca. Solo mapea el vocabulario de
    _detectar_decision() ("apostar"/"esperar"/"no_apostar") al vocabulario
    de estado ("APOSTAR"/"PRECAUCIÓN"/"NO APOSTAR") que espera el helper —
    no modifica _detectar_decision() ni su lógica.
    """
    from modules.scada_charts import semaforo_mini_html

    estado = _MAPA_DECISION_ESTADO.get(decision, "NO APOSTAR")
    col    = {"APOSTAR": _GREEN, "PRECAUCIÓN": _YELLOW, "NO APOSTAR": _RED}[estado]

    return (
        f'<div class="scada-panel" style="display:flex;flex-direction:column;'
        f'align-items:center;justify-content:center;min-height:140px;">'
        f'<div class="scada-titulo" style="text-align:center;">◈ SEMÁFORO</div>'
        f'{semaforo_mini_html(estado)}'
        f'<div style="font-size:10px;font-weight:700;color:{col};'
        f'letter-spacing:1px;margin-top:8px;">{estado}</div>'
        f'</div>'
    )


def _panel_momentum(momentum: float, nombre_l: str, nombre_v: str) -> str:
    """
    Barra de momentum -10→+10 con indicador dinámico — misma visualización
    direccional de siempre, recoloreada a DeOP claro: barra hacia Local en
    azul petróleo, barra hacia Visitante en rojo/naranja, texto del equipo
    dominante en dorado, panel blanco con borde petróleo.
    """
    _COL_LOCAL = "#0d3b4f"
    _COL_VISIT = "#e74c3c"
    _COL_DOMINANTE = "#f5a623"

    pct_pos   = ((momentum + 10) / 20) * 100      # 0-100 en la barra CSS
    col_bar   = _COL_LOCAL if momentum > 0 else (_COL_VISIT if momentum < 0 else _GRAY)
    dominante = nombre_l if momentum > 0 else (nombre_v if momentum < 0 else "Equilibrado")
    abs_m     = abs(momentum)

    # Pre-calcular posición y ancho del relleno (crece desde el centro)
    if momentum > 0:
        fill_left  = "50%"
        fill_width = f"{pct_pos - 50:.1f}%"
    elif momentum < 0:
        fill_left  = f"{pct_pos:.1f}%"
        fill_width = f"{50 - pct_pos:.1f}%"
    else:
        fill_left  = "50%"
        fill_width = "0%"

    indicator_left = f"{pct_pos:.1f}%"

    return (
        f'<div class="scada-panel" style="border-color:#0d3b4f;">'
        f'<div class="scada-titulo">◈ MOMENTUM  '
        f'<span style="color:{col_bar};font-weight:700;">{momentum:+.1f}</span>'
        f' / 10</div>'
        f'<div style="position:relative;margin:8px 0;">'
        f'<div style="display:flex;justify-content:space-between;font-size:8px;'
        f'color:{_TEXT};margin-bottom:3px;">'
        f'<span>{nombre_v[:12]}</span>'
        f'<span>Equilibrado</span>'
        f'<span>{nombre_l[:12]}</span>'
        f'</div>'
        f'<div style="width:100%;height:16px;background:#e8ecef;border-radius:3px;'
        f'border:1px solid {_BORDER};overflow:hidden;position:relative;">'
        f'<div style="position:absolute;top:0;height:100%;'
        f'left:{fill_left};width:{fill_width};'
        f'background:{col_bar};opacity:.9;"></div>'
        f'<div style="position:absolute;top:0;left:50%;width:2px;height:100%;'
        f'background:{_BORDER};"></div>'
        f'<div style="position:absolute;top:1px;left:{indicator_left};'
        f'width:4px;height:14px;background:{col_bar};border-radius:2px;'
        f'transform:translateX(-50%);box-shadow:0 0 4px {col_bar}88;"></div>'
        f'</div>'
        f'<div style="font-size:9px;color:{_COL_DOMINANTE};text-align:center;margin-top:4px;'
        f'font-weight:700;">{dominante} · {abs_m:.1f} pts</div>'
        f'</div>'
        f'</div>'
    )


def _barra_stat(val_l: int, val_v: int, col_l: str, col_v: str) -> str:
    """Mini barra comparativa izquierda/derecha centrada para una estadística."""
    total = val_l + val_v
    if total == 0:
        pct_l = pct_v = 50
    else:
        pct_l = int(val_l / total * 100)
        pct_v = 100 - pct_l
    return (
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:2px;'
        f'height:10px;border-radius:2px;overflow:hidden;">'
        f'<div style="background:{col_l};width:{pct_l}%;margin-left:auto;'
        f'border-radius:2px 0 0 2px;opacity:.85;"></div>'
        f'<div style="background:{col_v};width:{pct_v}%;'
        f'border-radius:0 2px 2px 0;opacity:.85;"></div>'
        f'</div>'
    )


def _panel_estadisticas(stats: dict, nombre_l: str, nombre_v: str) -> str:
    """Panel de comparativa de estadísticas con barras horizontales."""
    etiquetas = {
        "posesion_%":         ("Posesión", "%"),
        "ataques_peligrosos": ("Ataques peligrosos", ""),
        "ataques_totales":    ("Ataques totales", ""),
        "corners":            ("Corners", ""),
        "tiros_a_puerta":     ("Tiros a puerta", ""),
        "faltas_cometidas":   ("Faltas", ""),
    }
    filas = ""
    for key, (etq, sfx) in etiquetas.items():
        datos = stats.get(key, {})
        vl = datos.get("local", 0) or 0
        vv = datos.get("visitante", 0) or 0
        if vl == 0 and vv == 0:
            continue   # omitir stats sin datos
        col_l = _GOLD if vl >= vv else _GRAY
        col_v = _BLUE if vv > vl else _GRAY
        barra = _barra_stat(vl, vv, col_l if vl >= vv else _GRAY,
                            col_v if vv > vl else _GRAY)
        filas += (
            f'<div class="scada-stat-row">'
            f'<div style="text-align:right;color:{col_l};font-weight:{"700" if vl>vv else "400"};">'
            f'{vl}{sfx}</div>'
            f'<div style="text-align:center;">'
            f'<div style="font-size:8px;color:{_TEXT};margin-bottom:2px;">{etq}</div>'
            f'{barra}'
            f'</div>'
            f'<div style="text-align:left;color:{col_v};font-weight:{"700" if vv>vl else "400"};">'
            f'{vv}{sfx}</div>'
            f'</div>'
        )

    if not filas:
        filas = f'<div style="color:{_TEXT};font-size:10px;text-align:center;">Sin datos</div>'

    return (
        f'<div class="scada-panel">'
        f'<div class="scada-titulo">◈ ESTADÍSTICAS COMPARADAS</div>'
        f'<div style="display:flex;justify-content:space-between;font-size:9px;'
        f'color:{_TEXT};margin-bottom:6px;">'
        f'<span style="color:{_GOLD};">{nombre_l[:16]}</span>'
        f'<span style="color:{_BLUE};">{nombre_v[:16]}</span>'
        f'</div>'
        f'{filas}'
        f'</div>'
    )


def _panel_sin_datos() -> str:
    return (
        f'<div style="background:{_PANEL};border:1px solid {_YELLOW};'
        f'border-radius:6px;padding:14px 16px;margin:8px 0;'
        f'font-family:{_FONT};">'
        f'<div style="font-size:11px;color:{_YELLOW};font-weight:700;'
        f'letter-spacing:1px;margin-bottom:6px;">⚠️ SIN DATOS SUFICIENTES</div>'
        f'<div style="font-size:10px;color:{_LIGHT};line-height:1.5;">'
        f'Rellena al menos <b>3 campos de estadísticas</b> (posesión, ataques, '
        f'tiros, corners o faltas) antes de analizar.<br>'
        f'El dashboard SCADA se activa automáticamente cuando hay datos disponibles.'
        f'</div>'
        f'</div>'
    )


# ── Dashboard completo ────────────────────────────────────────────────────────

def _dashboard_scada(texto_claude: str, stats: dict,
                     partido: str, minuto: int,
                     goles_l: int, goles_v: int) -> None:
    """Renderiza el dashboard SCADA completo después del análisis."""
    nombre_l = partido.split(" vs ")[0].strip() if " vs " in partido else "Local"
    nombre_v = partido.split(" vs ")[1].strip() if " vs " in partido else "Visitante"

    pos_l  = (stats.get("posesion_%",         {}) or {}).get("local",     0) or 0
    pos_v  = (stats.get("posesion_%",         {}) or {}).get("visitante", 0) or 0
    atq_l  = (stats.get("ataques_peligrosos", {}) or {}).get("local",     0) or 0
    atq_v  = (stats.get("ataques_peligrosos", {}) or {}).get("visitante", 0) or 0
    tiro_l = (stats.get("tiros_a_puerta",     {}) or {}).get("local",     0) or 0
    tiro_v = (stats.get("tiros_a_puerta",     {}) or {}).get("visitante", 0) or 0

    momentum = _calcular_momentum(pos_l, pos_v, atq_l, atq_v, tiro_l, tiro_v)
    decision = _detectar_decision(texto_claude)

    # ── Fila 1: Marcador + Semáforo ──────────────────────────────────────────
    st.markdown(
        f'<div class="scada-grid">'
        f'{_panel_marcador(nombre_l, nombre_v, goles_l, goles_v, minuto)}'
        f'{_semaforo_vivo(decision)}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Fila 2: Momentum (ancho completo) ─────────────────────────────────────
    st.markdown(_panel_momentum(momentum, nombre_l, nombre_v), unsafe_allow_html=True)

    # ── Fila 3: Estadísticas comparadas ──────────────────────────────────────
    st.markdown(_panel_estadisticas(stats, nombre_l, nombre_v), unsafe_allow_html=True)


# ── Prompt y Claude ───────────────────────────────────────────────────────────

def _construir_prompt(partido: str, minuto: int, goles_l: int, goles_v: int,
                      stats: dict, mercado: str, datos_previa: dict) -> str:
    contexto_previo = ""
    if datos_previa:
        contexto_previo = (
            f"\nDATOS PRE-PARTIDO (modelo Poisson):\n"
            f"{json.dumps(datos_previa, indent=2, ensure_ascii=False)}\n"
        )

    return f"""Eres un analista experto en apuestas deportivas en tiempo real (in-play).

Partido: {partido}
Minuto: {minuto}'
Resultado actual: {goles_l} - {goles_v}
Mercado a analizar: {mercado}
{contexto_previo}
ESTADÍSTICAS EN VIVO (fuente: Codere):
{json.dumps(stats, indent=2, ensure_ascii=False)}

Analiza esta situación en tiempo real y responde en 4 puntos:
1. Lectura del partido: ¿quién domina según las estadísticas? Compara con las \
probabilidades pre-partido si están disponibles.
2. Momentum y tendencia: ¿está cambiando el control del partido? ¿Qué equipo tiene \
más amenaza?
3. Recomendación in-play para el mercado "{mercado}": indica claramente si \
"APOSTAR", "ESPERAR" o "NO APOSTAR", con el motivo y cuota mínima orientativa.
4. Confianza: Alto / Medio / Bajo — justifica considerando el minuto y la volatilidad.

Responde en español, directo. Máximo 250 palabras."""


def _analizar_en_vivo(partido: str, minuto: int, goles_l: int, goles_v: int,
                      stats: dict, mercado: str, datos_previa: dict) -> str:
    client = anthropic.Anthropic(api_key=API_KEY)
    prompt = _construir_prompt(partido, minuto, goles_l, goles_v,
                               stats, mercado, datos_previa)
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def _normalizar_formato(texto: str) -> str:
    return re.sub(r'^#{1,3} (.+)$', r'**\1**', texto, flags=re.MULTILINE)


# ── UI principal ──────────────────────────────────────────────────────────────

def _fila_stat(label: str, key_l: str, key_v: str,
               max_val: int = 100, step: int = 1,
               sufijo: str = "") -> tuple[int, int]:
    """Fila de estadística local / visitante."""
    col_etq, col_l, col_v = st.columns([1.4, 1, 1])
    with col_etq:
        st.markdown(
            f'<div style="font-size:12px;color:var(--texto-apagado);padding-top:8px;">'
            f'{label}{" " + sufijo if sufijo else ""}</div>',
            unsafe_allow_html=True,
        )
    with col_l:
        val_l = st.number_input("Local", min_value=0, max_value=max_val,
                                step=step, key=key_l, label_visibility="collapsed")
    with col_v:
        val_v = st.number_input("Visitante", min_value=0, max_value=max_val,
                                step=step, key=key_v, label_visibility="collapsed")
    return int(val_l), int(val_v)


def mostrar() -> None:
    """Renderiza el módulo completo de Análisis en Vivo."""
    from modules.scada_charts import panel_info_partido_html
    from modules.claude_analysis import _datos_desde_sesion as _datos_previa_sesion

    # CSS inyectado desde el inicio (no solo tras analizar) para que los
    # labels nativos ("Partido", "Mercado in-play:", "Minuto", etc.) sean
    # legibles también en el formulario, antes de tener resultados.
    st.markdown(_CSS_VIVO, unsafe_allow_html=True)

    # ── Partido activo ────────────────────────────────────────────────────────
    partido = st.session_state.get("partido_activo", "")
    liga    = st.session_state.get("liga_activa", "")

    if partido:
        st.markdown(
            f'<div style="font-size:13px;color:#5a7a9a;margin-bottom:10px;">'
            f'Partido cargado: <span style="color:#0d3b4f;font-weight:700;">'
            f'{partido}</span>'
            f'&nbsp;·&nbsp;<span style="color:#0d3b4f;">{liga}</span></div>',
            unsafe_allow_html=True,
        )

        _datos_previa = _datos_previa_sesion()
        if _datos_previa:
            with st.expander("🔍 Ver datos del partido", expanded=False):
                st.markdown(panel_info_partido_html(_datos_previa), unsafe_allow_html=True)
    else:
        st.info("Selecciona y analiza un partido primero. "
                "También puedes introducir el nombre manualmente.")
        partido = st.text_input(
            "Partido (Ej: Real Madrid vs Barcelona)",
            key="vivo_partido_manual",
        )

    # ── Mercado ───────────────────────────────────────────────────────────────
    mercado = st.selectbox("Mercado in-play:", MERCADOS_VIVO, key="vivo_mercado")

    st.markdown("<hr style='border-color:var(--borde);margin:12px 0'>",
                unsafe_allow_html=True)

    # ── Marcador y minuto ─────────────────────────────────────────────────────
    st.markdown(
        '<div style="font-size:12px;font-weight:700;color:var(--texto);'
        'margin-bottom:6px;">Resultado actual</div>',
        unsafe_allow_html=True,
    )
    col_min, col_gl, col_sep, col_gv = st.columns([1.2, 1, 0.3, 1])
    with col_min:
        minuto = st.number_input("Minuto", min_value=1, max_value=120,
                                 value=45, step=1, key="vivo_minuto")
    with col_gl:
        goles_l = st.number_input("Goles local", min_value=0, max_value=20,
                                  step=1, key="vivo_goles_l")
    with col_sep:
        st.markdown(
            '<div style="text-align:center;font-size:20px;padding-top:22px;">—</div>',
            unsafe_allow_html=True,
        )
    with col_gv:
        goles_v = st.number_input("Goles visitante", min_value=0, max_value=20,
                                  step=1, key="vivo_goles_v")

    st.markdown("<hr style='border-color:var(--borde);margin:12px 0'>",
                unsafe_allow_html=True)

    # ── Cabecera de columnas ──────────────────────────────────────────────────
    _, col_h_l, col_h_v = st.columns([1.4, 1, 1])
    nombre_l = partido.split(" vs ")[0].strip() if " vs " in partido else "Local"
    nombre_v = partido.split(" vs ")[1].strip() if " vs " in partido else "Visitante"
    with col_h_l:
        st.markdown(
            f'<div style="font-size:11px;font-weight:700;color:var(--acento-dorado);'
            f'text-align:center;">{nombre_l[:18]}</div>',
            unsafe_allow_html=True,
        )
    with col_h_v:
        st.markdown(
            f'<div style="font-size:11px;font-weight:700;color:var(--acento-azul);'
            f'text-align:center;">{nombre_v[:18]}</div>',
            unsafe_allow_html=True,
        )

    # ── Estadísticas ─────────────────────────────────────────────────────────
    pos_l,  pos_v  = _fila_stat("Posesión",           "vivo_pos_l",  "vivo_pos_v",  100, 1,  "%")
    atq_l,  atq_v  = _fila_stat("Ataques peligrosos", "vivo_ap_l",   "vivo_ap_v",   200, 1)
    tat_l,  tat_v  = _fila_stat("Ataques totales",    "vivo_at_l",   "vivo_at_v",   400, 1)
    cor_l,  cor_v  = _fila_stat("Corners",            "vivo_cor_l",  "vivo_cor_v",   30, 1)
    tiro_l, tiro_v = _fila_stat("Tiros a puerta",     "vivo_tp_l",   "vivo_tp_v",    30, 1)
    fal_l,  fal_v  = _fila_stat("Faltas",             "vivo_fal_l",  "vivo_fal_v",   30, 1)

    # ── Botón + panel cancha ─────────────────────────────────────────────────
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    col_form_bot, col_cancha_panel = st.columns([1.15, 1])
    with col_form_bot:
        analizar = st.button("⚡ Analizar en vivo con Claude AI",
                             key="btn_vivo", use_container_width=True)
    with col_cancha_panel:
        _b64 = _cancha_b64()
        if _b64:
            components.html(
                _panel_cancha_html(
                    nombre_l, nombre_v,
                    int(goles_l), int(goles_v),
                    int(pos_l), int(pos_v),
                    int(tiro_l), int(tiro_v),
                    _b64,
                ),
                height=265,
                scrolling=False,
            )

    # ── Lógica de análisis ────────────────────────────────────────────────────
    if analizar:
        if not partido.strip():
            st.warning("Introduce el nombre del partido antes de analizar.")
            return

        stats = {
            "posesion_%":            {"local": pos_l,  "visitante": pos_v},
            "ataques_peligrosos":    {"local": atq_l,  "visitante": atq_v},
            "ataques_totales":       {"local": tat_l,  "visitante": tat_v},
            "corners":               {"local": cor_l,  "visitante": cor_v},
            "tiros_a_puerta":        {"local": tiro_l, "visitante": tiro_v},
            "faltas_cometidas":      {"local": fal_l,  "visitante": fal_v},
        }

        # Validar mínimo 3 campos rellenos
        if _campos_rellenos(stats) < 3:
            st.markdown(_panel_sin_datos(), unsafe_allow_html=True)
            return

        datos_previa: dict = {}
        if st.session_state.get("analisis_listo") and st.session_state.get("probs_partido"):
            datos_previa = {
                "probabilidades_modelo": st.session_state["probs_partido"],
                "mejor_cuota_previa":    st.session_state.get("mejor_cuota_partido", ""),
            }

        with st.spinner("Claude analizando la situación en vivo..."):
            try:
                resultado = _analizar_en_vivo(
                    partido, int(minuto), goles_l, goles_v,
                    stats, mercado, datos_previa,
                )
                st.session_state["vivo_analisis"]    = resultado
                st.session_state["vivo_stats"]       = stats
                st.session_state["vivo_minuto_snap"] = int(minuto)
                st.session_state["vivo_snap_gl"]     = goles_l
                st.session_state["vivo_snap_gv"]     = goles_v
                st.session_state["vivo_partido_snap"] = partido
            except anthropic.AuthenticationError:
                st.error("API key inválida.")
                return
            except Exception as exc:
                st.error(f"Error al conectar con Claude: {exc}")
                return

    # ── Dashboard SCADA + análisis ────────────────────────────────────────────
    if resultado := st.session_state.get("vivo_analisis"):
        stats_snap   = st.session_state.get("vivo_stats", {})
        minuto_snap  = st.session_state.get("vivo_minuto_snap", minuto)
        gl_snap      = st.session_state.get("vivo_snap_gl", goles_l)
        gv_snap      = st.session_state.get("vivo_snap_gv", goles_v)
        partido_snap = st.session_state.get("vivo_partido_snap", partido)

        st.markdown(
            f'<div style="font-size:10px;color:var(--texto-apagado);margin:10px 0 4px;">'
            f'Análisis generado · Minuto {minuto_snap}\'</div>',
            unsafe_allow_html=True,
        )

        # Dashboard SCADA
        _dashboard_scada(resultado, stats_snap, partido_snap,
                         minuto_snap, gl_snap, gv_snap)

        st.markdown("<hr style='border-color:var(--borde);margin:10px 0'>",
                    unsafe_allow_html=True)

        # Texto del análisis de Claude
        st.markdown(
            f'<div class="alerta-exito" style="font-size:12px;line-height:1.7;">'
            f'{_normalizar_formato(resultado)}</div>',
            unsafe_allow_html=True,
        )

        if st.button("🗑️ Limpiar análisis", key="btn_vivo_clear",
                     use_container_width=False):
            for k in ("vivo_analisis", "vivo_stats", "vivo_minuto_snap",
                      "vivo_snap_gl", "vivo_snap_gv", "vivo_partido_snap"):
                st.session_state.pop(k, None)
            st.rerun()
