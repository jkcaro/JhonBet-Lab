"""
Módulo: Análisis en Vivo — estadísticas en tiempo real + Claude AI.
Dashboard SCADA industrial adaptable a cualquier partido y equipo.
"""

import json
import os
import re
import streamlit as st
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

# ── Paleta SCADA ──────────────────────────────────────────────────────────────
_PANEL  = "#080c14"
_BORDER = "#1a2540"
_GREEN  = "#00ff88"
_YELLOW = "#f5a623"
_RED    = "#ff4444"
_GRAY   = "#1e2d45"
_TEXT   = "#5a7a9a"
_LIGHT  = "#8eb0cc"
_GOLD   = "#ffd700"
_BLUE   = "#4499ff"
_FONT   = "Courier New, monospace"

_CSS_VIVO = """
<style>
/* ── SCADA Vivo: grid responsivo ── */
.scada-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 8px;
    margin-bottom: 8px;
}
.scada-panel {
    background: #080c14;
    border: 1px solid #1a2540;
    border-radius: 6px;
    padding: 10px 12px;
    font-family: 'Courier New', monospace;
}
.scada-titulo {
    font-size: 9px;
    color: #5a7a9a;
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-bottom: 8px;
    padding-bottom: 5px;
    border-bottom: 1px solid #1a2540;
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
</style>
"""


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
        f'<div style="font-size:30px;font-weight:900;color:#fff;line-height:1;">'
        f'{goles_l}</div>'
        f'</div>'
        # Separador
        f'<div style="font-size:20px;color:{_TEXT};">—</div>'
        # Visitante
        f'<div style="flex:1;text-align:left;">'
        f'<div style="font-size:10px;color:{_BLUE};letter-spacing:1px;'
        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
        f'{nombre_v[:14]}</div>'
        f'<div style="font-size:30px;font-weight:900;color:#fff;line-height:1;">'
        f'{goles_v}</div>'
        f'</div>'
        f'</div>'
        f'<div style="font-size:11px;color:{_GREEN};font-weight:700;'
        f'letter-spacing:2px;">⏱ {minuto}\'</div>'
        f'</div>'
    )


def _semaforo_vivo(decision: str) -> str:
    """Semáforo SCADA basado en la decisión detectada en el texto de Claude."""
    if decision == "apostar":
        estado, col = "APOSTAR", _GREEN
        r = "#150404"; a = "#141200"; g = _GREEN
        gr = ga = "none"; gg = f"0 0 10px {_GREEN}, 0 0 20px {_GREEN}44"
    elif decision == "esperar":
        estado, col = "ESPERAR", _YELLOW
        r = "#150404"; a = _YELLOW; g = "#021209"
        gr = "none"; ga = f"0 0 10px {_YELLOW}, 0 0 20px {_YELLOW}44"; gg = "none"
    else:
        estado, col = "NO APOSTAR", _RED
        r = _RED; a = "#141200"; g = "#021209"
        gr = f"0 0 10px {_RED}, 0 0 20px {_RED}44"; ga = gg = "none"

    circ = (
        f'<div style="width:20px;height:20px;border-radius:50%;background:{r};'
        f'box-shadow:{gr};border:1px solid {_BORDER};"></div>'
        f'<div style="width:3px;height:7px;background:{_BORDER};"></div>'
        f'<div style="width:20px;height:20px;border-radius:50%;background:{a};'
        f'box-shadow:{ga};border:1px solid {_BORDER};"></div>'
        f'<div style="width:3px;height:7px;background:{_BORDER};"></div>'
        f'<div style="width:20px;height:20px;border-radius:50%;background:{g};'
        f'box-shadow:{gg};border:1px solid {_BORDER};"></div>'
    )
    return (
        f'<div class="scada-panel" style="display:flex;flex-direction:column;'
        f'align-items:center;justify-content:center;min-height:140px;">'
        f'<div class="scada-titulo" style="text-align:center;">◈ SEMÁFORO</div>'
        f'<div style="display:flex;flex-direction:column;align-items:center;gap:3px;">'
        f'{circ}'
        f'</div>'
        f'<div style="font-size:10px;font-weight:700;color:{col};'
        f'letter-spacing:1px;margin-top:8px;">{estado}</div>'
        f'</div>'
    )


def _panel_momentum(momentum: float, nombre_l: str, nombre_v: str) -> str:
    """Barra de momentum -10→+10 con indicador dinámico."""
    pct_pos   = ((momentum + 10) / 20) * 100      # 0-100 en la barra CSS
    col_bar   = _GREEN if momentum > 0 else (_RED if momentum < 0 else _GRAY)
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
        f'<div class="scada-panel">'
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
        f'<div style="width:100%;height:16px;background:{_GRAY};border-radius:3px;'
        f'border:1px solid {_BORDER};overflow:hidden;position:relative;">'
        f'<div style="position:absolute;top:0;height:100%;'
        f'left:{fill_left};width:{fill_width};'
        f'background:{col_bar};opacity:.8;"></div>'
        f'<div style="position:absolute;top:0;left:50%;width:2px;height:100%;'
        f'background:{_BORDER};"></div>'
        f'<div style="position:absolute;top:1px;left:{indicator_left};'
        f'width:4px;height:14px;background:{col_bar};border-radius:2px;'
        f'transform:translateX(-50%);box-shadow:0 0 6px {col_bar}88;"></div>'
        f'</div>'
        f'<div style="font-size:9px;color:{col_bar};text-align:center;margin-top:4px;'
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

    st.markdown(_CSS_VIVO, unsafe_allow_html=True)

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

    # ── Partido activo ────────────────────────────────────────────────────────
    partido = st.session_state.get("partido_activo", "")
    liga    = st.session_state.get("liga_activa", "")

    if partido:
        st.markdown(
            f'<div style="font-size:13px;color:var(--texto-apagado);margin-bottom:10px;">'
            f'Partido cargado: <span style="color:var(--texto);font-weight:700;">'
            f'{partido}</span>'
            f'&nbsp;·&nbsp;<span style="color:var(--acento-azul);">{liga}</span></div>',
            unsafe_allow_html=True,
        )
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

    # ── Botón ─────────────────────────────────────────────────────────────────
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    analizar = st.button("⚡ Analizar en vivo con Claude AI",
                         key="btn_vivo", use_container_width=True)

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
