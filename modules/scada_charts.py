"""Módulo: Visualizaciones estilo SCADA industrial para análisis de apuestas."""

import math
import re
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

def _max_edge(datos: dict) -> float:
    """Mayor edge positivo (%) en edge_por_outcome."""
    mejor = -99.0
    for v in datos.get("edge_por_outcome", {}).values():
        try:
            n = float(str(v).replace("+", "").replace("%", ""))
            if n > mejor:
                mejor = n
        except ValueError:
            pass
    return mejor if mejor > -99.0 else 0.0


def _extraer_confianza_num(texto: str) -> tuple[str, float]:
    """Devuelve (nivel_str, valor_numérico) para el gauge."""
    m = re.search(r'confianza[:\s*_]+\**(alto|medio|bajo)\**', texto, re.IGNORECASE)
    nivel = m.group(1).capitalize() if m else "Bajo"
    return nivel, {"Alto": 85.0, "Medio": 50.0, "Bajo": 18.0}[nivel]


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


# ── Gauge de Edge % ───────────────────────────────────────────────────────────

def gauge_edge(edge: float) -> go.Figure:
    color = GREEN if edge >= 6 else (YELLOW if edge >= 0 else RED)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=round(edge, 1),
        number={"suffix": "%", "font": {"size": 22, "color": color, "family": "Courier New, monospace"},
                "valueformat": "+.1f"},
        title={"text": "EDGE  %", "font": {"size": 10, "color": TEXT, "family": "Courier New, monospace"}},
        gauge={
            "axis": {"range": [-20, 20], "dtick": 5,
                     "tickfont": {"size": 8, "color": TEXT, "family": "Courier New"},
                     "tickcolor": BORDER, "tickwidth": 1},
            "bar": {"color": color, "thickness": 0.22},
            "bgcolor": PANEL,
            "borderwidth": 1, "bordercolor": BORDER,
            "steps": [
                {"range": [-20, 0], "color": "#150404"},
                {"range": [0,   6], "color": "#141200"},
                {"range": [6,  20], "color": "#021209"},
            ],
            "threshold": {"line": {"color": GREEN, "width": 2},
                          "thickness": 0.8, "value": 6},
        },
    ))
    fig.update_layout(**_LAYOUT, height=190,
                      title=dict(text="◈ INDICADOR EDGE  (umbral 6%)", font=dict(size=9, color=TEXT, family="Courier New"), x=0.02))
    return fig


# ── Gauge de Confianza ────────────────────────────────────────────────────────

def gauge_confianza(texto_claude: str) -> go.Figure:
    nivel, valor = _extraer_confianza_num(texto_claude)
    color = GREEN if nivel == "Alto" else (YELLOW if nivel == "Medio" else RED)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=valor,
        number={"suffix": "%", "font": {"size": 22, "color": color, "family": "Courier New, monospace"}},
        title={"text": f"CONFIANZA: {nivel.upper()}",
               "font": {"size": 10, "color": TEXT, "family": "Courier New, monospace"}},
        gauge={
            "axis": {"range": [0, 100], "dtick": 20,
                     "tickfont": {"size": 8, "color": TEXT, "family": "Courier New"},
                     "tickcolor": BORDER, "tickwidth": 1},
            "bar": {"color": color, "thickness": 0.22},
            "bgcolor": PANEL,
            "borderwidth": 1, "bordercolor": BORDER,
            "steps": [
                {"range": [0,  33],  "color": "#150404"},
                {"range": [33, 66],  "color": "#141200"},
                {"range": [66, 100], "color": "#021209"},
            ],
        },
    ))
    fig.update_layout(**_LAYOUT, height=190,
                      title=dict(text="◈ CONFIANZA MODELO", font=dict(size=9, color=TEXT, family="Courier New"), x=0.02))
    return fig


ORANGE = "#ff8c00"   # naranja para VALOR BAJO


# ── Panel Discrepancia BeSoccer vs Codere ─────────────────────────────────────

def panel_discrepancia(datos: dict) -> str:
    """
    Panel SCADA de discrepancia entre el modelo Poisson (BeSoccer/xG) y la cuota Codere.

    Para cada outcome en edge_por_outcome muestra:
      - Probabilidad del modelo  = (1 + edge/100) × prob_impl
      - Probabilidad implícita   = 1 / cuota_codere  (en %)
      - Edge                     = (cuota × P_modelo − 1) × 100
      - Clasificación visual:
          🟢 APUESTA CON VALOR  edge ≥ 6%
          🔴 SIN VALOR          edge < 6%
    """
    edge_dict   = datos.get("edge_por_outcome", {})
    cuotas_dict = datos.get("cuotas_reales", {})

    if not edge_dict:
        return ""

    def _clasif(e: float) -> tuple[str, str, str]:
        if e >= 6: return "🟢", "APUESTA CON VALOR", GREEN
        return          "🔴", "SIN VALOR",          RED

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
        col_edge = GREEN if edge_val >= 6 else RED
        etiqueta = outcome.split("—")[-1].strip() if "—" in outcome else outcome

        cuota_txt = f"{codere:.2f}" if codere > 1.0 else "—"
        prob_model_txt = "—" if prob_model <= 0 else f"{prob_model:.1f}%"
        prob_impl_txt  = "—" if prob_impl  <= 0 else f"{prob_impl:.1f}%"
        span_cuota     = "" if codere <= 1.0 else f' <span style="opacity:.6">@{cuota_txt}</span>'

        filas += (
            f'<tr>'
            f'<td style="color:{LIGHT};font-size:10px;padding:3px 8px;">{etiqueta}</td>'
            f'<td style="color:{GREEN};font-size:10px;font-family:Courier New,monospace;'
            f'padding:3px 8px;text-align:right;">'
            f'{prob_model_txt}</td>'
            f'<td style="color:{TEXT};font-size:10px;font-family:Courier New,monospace;'
            f'padding:3px 8px;text-align:right;">'
            f'{prob_impl_txt}{span_cuota}'
            f'</td>'
            f'<td style="font-size:10px;font-family:Courier New,monospace;'
            f'padding:3px 8px;text-align:right;font-weight:700;color:{col_edge};">'
            f'{edge_val:+.1f}%</td>'
            f'<td style="font-size:10px;padding:3px 8px;white-space:nowrap;color:{col_clasif};">'
            f'{emoji} {label}</td>'
            f'</tr>'
        )

    if not filas:
        return ""

    return (
        f'<div style="background:{PANEL};border:1px solid {BORDER};border-radius:6px;'
        f'padding:10px 14px;margin-bottom:6px;">'
        f'<div style="font-size:9px;color:{TEXT};letter-spacing:2px;'
        f'font-family:Courier New,monospace;margin-bottom:8px;padding-bottom:5px;'
        f'border-bottom:1px solid {BORDER};">◈ DISCREPANCIA BESOCCER vs CODERE</div>'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr>'
        f'<th style="font-size:8px;color:{TEXT};font-family:Courier New;'
        f'padding:2px 8px;text-align:left;">OUTCOME</th>'
        f'<th style="font-size:8px;color:{TEXT};font-family:Courier New;'
        f'padding:2px 8px;text-align:right;">MODELO</th>'
        f'<th style="font-size:8px;color:{TEXT};font-family:Courier New;'
        f'padding:2px 8px;text-align:right;">CODERE</th>'
        f'<th style="font-size:8px;color:{TEXT};font-family:Courier New;'
        f'padding:2px 8px;text-align:right;">EDGE</th>'
        f'<th style="font-size:8px;color:{TEXT};font-family:Courier New;'
        f'padding:2px 8px;">CLASIFICACIÓN</th>'
        f'</tr></thead>'
        f'<tbody>{filas}</tbody>'
        f'</table>'
        f'</div>'
    )


# ── Panel Sistema de Puntos ───────────────────────────────────────────────────

def panel_sistema_puntos(puntuacion: dict,
                         condiciones_custom: list | None = None) -> str:
    """
    Panel SCADA del sistema de puntos (0-5).
    condiciones_custom: lista opcional de (label, ok, tipo) para sobreescribir
    las condiciones por defecto (permite reutilizar desde otros módulos).
    """
    puntos    = puntuacion.get("puntos", 0)
    edge      = puntuacion.get("edge", 0.0)
    estado    = puntuacion.get("estado", "NO APOSTAR")

    # Colores según decisión
    if estado == "APOSTAR":
        col_estado = GREEN;  col_gauge = GREEN;  col_bg = "#021209"
    elif estado == "PRECAUCIÓN":
        col_estado = YELLOW; col_gauge = YELLOW; col_bg = "#141200"
    else:
        col_estado = RED;    col_gauge = RED;    col_bg = "#150404"

    pct = int((puntos / 5) * 100)   # 0-100 para la barra CSS

    # ── Gauge vertical ───────────────────────────────────────────────
    gauge = (
        f'<div style="display:flex;flex-direction:column;align-items:center;'
        f'gap:3px;min-width:32px;">'
        f'<div style="font-size:8px;color:{TEXT};font-family:Courier New,monospace;">5</div>'
        f'<div style="width:14px;height:90px;background:{PANEL};border:1px solid {BORDER};'
        f'border-radius:3px;overflow:hidden;display:flex;flex-direction:column;justify-content:flex-end;">'
        # zona verde (pts 4-5 = 80-100%)
        f'<div style="position:absolute;"></div>'
        f'<div style="width:100%;height:{pct}%;background:{col_gauge};'
        f'box-shadow:0 0 6px {col_gauge}66;border-radius:2px 2px 0 0;"></div>'
        f'</div>'
        # marcas de zona
        f'<div style="font-size:8px;color:{TEXT};font-family:Courier New,monospace;">0</div>'
        f'</div>'
        # leyenda de zonas (a la derecha del gauge)
        f'<div style="display:flex;flex-direction:column;justify-content:space-between;'
        f'height:90px;padding:2px 0;margin-left:4px;">'
        f'<div style="font-size:7px;color:{GREEN};font-family:Courier New,monospace;">4-5 ✅</div>'
        f'<div style="font-size:7px;color:{YELLOW};font-family:Courier New,monospace;">2-3 🟡</div>'
        f'<div style="font-size:7px;color:{RED};font-family:Courier New,monospace;">0-1 🔴</div>'
        f'</div>'
    )

    # ── Puntuación central ───────────────────────────────────────────
    score = (
        f'<div style="display:flex;flex-direction:column;align-items:center;gap:2px;'
        f'padding:0 12px;">'
        f'<div style="font-size:38px;font-weight:900;color:{col_gauge};'
        f'font-family:Courier New,monospace;line-height:1;'
        f'text-shadow:0 0 14px {col_gauge}55;">{puntos}</div>'
        f'<div style="font-size:9px;color:{TEXT};font-family:Courier New,monospace;'
        f'letter-spacing:1px;">/ 4 PTS</div>'
        f'<div style="font-size:10px;font-weight:700;color:{col_estado};'
        f'font-family:Courier New,monospace;letter-spacing:1px;margin-top:4px;">'
        f'{estado}</div>'
        f'<div style="font-size:8px;color:{TEXT};margin-top:2px;">'
        f'Edge {edge:+.1f}%</div>'
        f'</div>'
    )

    # ── Condiciones individuales ─────────────────────────────────────
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
        icono  = "✅" if ok else "❌"
        color  = GREEN if ok else (RED if tipo == "base" and not ok else GRAY)
        conds_html += (
            f'<div style="display:flex;align-items:center;gap:5px;margin:2px 0;">'
            f'<span style="font-size:10px;">{icono}</span>'
            f'<span style="font-size:9px;color:{LIGHT};font-family:Courier New,monospace;">'
            f'{label}</span>'
            f'</div>'
        )

    return (
        f'<div style="background:{PANEL};border:1px solid {BORDER};border-radius:6px;'
        f'padding:10px 14px;margin-bottom:6px;">'
        f'<div style="font-size:9px;color:{TEXT};letter-spacing:2px;'
        f'font-family:Courier New,monospace;margin-bottom:8px;padding-bottom:5px;'
        f'border-bottom:1px solid {BORDER};">◈ SISTEMA DE PUNTOS</div>'
        f'<div style="display:flex;align-items:center;gap:4px;">'
        f'{gauge}'
        f'{score}'
        f'<div style="flex:1;padding-left:6px;border-left:1px solid {BORDER};">'
        f'{conds_html}'
        f'</div>'
        f'</div>'
        f'</div>'
    )


# ── Semáforo industrial ───────────────────────────────────────────────────────

def semaforo_html(edge: float, puntuacion: dict | None = None) -> str:
    """Semáforo SCADA. Usa el sistema de puntos si está disponible."""
    if puntuacion:
        estado_raw = puntuacion.get("estado", "NO APOSTAR")
        subtitulo  = f"PUNTOS {puntuacion.get('puntos', 0)}/5"
    else:
        # Fallback al sistema basado en edge
        estado_raw = "APOSTAR" if edge >= 6 else "NO APOSTAR"
        subtitulo  = f"EDGE {edge:+.1f}%"

    if estado_raw == "APOSTAR":
        estado, col_txt = "APOSTAR", GREEN
        r, a, g = "#150404", "#141200", GREEN
        glow_r = glow_a = "none"
        glow_g = f"0 0 10px {GREEN}, 0 0 20px {GREEN}44"
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
        f'<div style="background:{PANEL};border:1px solid {BORDER};border-radius:6px;'
        f'padding:12px 10px;display:flex;flex-direction:column;align-items:center;gap:4px;height:190px;'
        f'justify-content:center;font-family:Courier New,monospace;">'
        f'<div style="font-size:9px;color:{TEXT};letter-spacing:2px;margin-bottom:8px;">SEMÁFORO</div>'
        f'<div style="width:22px;height:22px;border-radius:50%;background:{r};box-shadow:{glow_r};'
        f'border:1px solid {BORDER};"></div>'
        f'<div style="width:4px;height:8px;background:{BORDER};"></div>'
        f'<div style="width:22px;height:22px;border-radius:50%;background:{a};box-shadow:{glow_a};'
        f'border:1px solid {BORDER};"></div>'
        f'<div style="width:4px;height:8px;background:{BORDER};"></div>'
        f'<div style="width:22px;height:22px;border-radius:50%;background:{g};box-shadow:{glow_g};'
        f'border:1px solid {BORDER};"></div>'
        f'<div style="font-size:9px;font-weight:700;color:{col_txt};margin-top:10px;letter-spacing:1px;">'
        f'{estado}</div>'
        f'<div style="font-size:8px;color:{TEXT};">{subtitulo}</div>'
        f'</div>'
    )


# ── Barras SCADA de probabilidades ────────────────────────────────────────────

def barras_probabilidad(datos: dict) -> go.Figure:
    p_l, p_e, p_v, lbl_l, lbl_e, lbl_v = _prob1x2(datos)
    edges = datos.get("edge_por_outcome", {})

    def _tiene_valor(label: str) -> bool:
        for k, v in edges.items():
            try:
                if label.lower() in k.lower() and float(str(v).replace("+","").replace("%","")) >= 10:
                    return True
            except ValueError:
                pass
        return False

    labels = [lbl_v[:14], lbl_e, lbl_l[:14]]
    valores = [p_v, p_e, p_l]
    colores = [GREEN if _tiene_valor(lb) else GRAY for lb in [lbl_v, lbl_e, lbl_l]]

    fig = go.Figure()
    for i, (lbl, val, col) in enumerate(zip(labels, valores, colores)):
        fig.add_trace(go.Bar(
            x=[val], y=[lbl], orientation="h",
            marker=dict(color=col, line=dict(color=BORDER, width=1)),
            text=f"{val:.1f}%", textposition="inside",
            textfont=dict(family="Courier New", size=9, color=BG if col != GRAY else LIGHT),
            showlegend=False, name=lbl,
        ))
        # Fondo vacío (segmentos a 100%)
        fig.add_trace(go.Bar(
            x=[100 - val], y=[lbl], orientation="h",
            marker=dict(color=GRID, line=dict(color=BORDER, width=1)),
            showlegend=False, name="", hoverinfo="skip",
        ))

    # Líneas de cuadrícula cada 10%
    for tick in range(0, 101, 10):
        fig.add_vline(x=tick, line=dict(color=BORDER, width=1, dash="dot"))

    fig.update_layout(
        **_LAYOUT, height=120, barmode="stack",
        title=dict(text="◈ PROBABILIDADES 1X2  (verde = valor detectado)",
                   font=dict(size=9, color=TEXT, family="Courier New"), x=0.01),
        xaxis=dict(range=[0, 100], tickfont=dict(size=8, color=TEXT, family="Courier New"),
                   showgrid=False, showline=True, linecolor=BORDER, ticksuffix="%", dtick=20),
        yaxis=dict(tickfont=dict(size=9, color=LIGHT, family="Courier New"), showgrid=False),
        bargap=0.35,
    )
    return fig


# ── Donut Ambos Marcan ────────────────────────────────────────────────────────

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


# ── Gauge P(0-0) para mercados Sin Goles ─────────────────────────────────────

def gauge_p00(datos: dict) -> go.Figure:
    """
    Velocímetro SCADA que muestra P(0-0) calculada con Poisson.
    Escala 0-50%: rojo (0-15% → muy improbable), amarillo (15-30%), verde (30%+).
    """
    sg = datos.get("sin_goles_calculado", {})
    try:
        pct = float(str(sg.get("probabilidad_00", "0")).replace("%", ""))
    except ValueError:
        pct = 0.0

    xg_l = sg.get("xg_local", "?")
    xg_v = sg.get("xg_visitante", "?")
    formula = f"e^(-{xg_l}) × e^(-{xg_v})"

    color = GREEN if pct >= 30 else (YELLOW if pct >= 15 else RED)

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=round(pct, 1),
        number={"suffix": "%", "font": {"size": 22, "color": color, "family": "Courier New, monospace"}},
        title={"text": f"P(0-0)<br><span style='font-size:9px'>{formula}</span>",
               "font": {"size": 10, "color": TEXT, "family": "Courier New, monospace"}},
        gauge={
            "axis": {"range": [0, 50], "dtick": 10,
                     "tickfont": {"size": 8, "color": TEXT, "family": "Courier New"},
                     "tickcolor": BORDER, "tickwidth": 1, "ticksuffix": "%"},
            "bar": {"color": color, "thickness": 0.22},
            "bgcolor": PANEL,
            "borderwidth": 1, "bordercolor": BORDER,
            "steps": [
                {"range": [0,  15], "color": "#150404"},   # rojo: muy improbable
                {"range": [15, 30], "color": "#141200"},   # amarillo: posible
                {"range": [30, 50], "color": "#021209"},   # verde: valor posible
            ],
            "threshold": {"line": {"color": YELLOW, "width": 2},
                          "thickness": 0.8, "value": 15},  # línea umbral 15%
        },
    ))
    fig.update_layout(**_LAYOUT, height=190,
                      title=dict(text="◈ P(0-0)  POISSON",
                                 font=dict(size=9, color=TEXT, family="Courier New"), x=0.02))
    return fig


# ── Dashboard principal ───────────────────────────────────────────────────────

def mostrar_dashboard(texto_claude: str, datos: dict, mercado: str,
                      puntuacion: dict | None = None) -> None:
    """Renderiza el dashboard SCADA completo para el análisis actual."""

    st.markdown(_CSS_COMPACTO, unsafe_allow_html=True)

    edge = _max_edge(datos)

    # ── Gauge Edge ──
    st.plotly_chart(gauge_edge(edge), use_container_width=True, config=_CONFIG)
    # ── Gauge Confianza ──
    st.plotly_chart(gauge_confianza(texto_claude), use_container_width=True, config=_CONFIG)
    # ── Semáforo ──
    st.markdown(semaforo_html(edge, puntuacion), unsafe_allow_html=True)

    # ── Panel discrepancia BeSoccer vs Codere ──
    html_discrepancia = panel_discrepancia(datos)
    if html_discrepancia:
        st.markdown(html_discrepancia, unsafe_allow_html=True)

    # ── Panel sistema de puntos ──
    if puntuacion:
        st.markdown(panel_sistema_puntos(puntuacion), unsafe_allow_html=True)

    # ── Fila 2: Barras de probabilidad ──
    if datos.get("probabilidades"):
        st.plotly_chart(barras_probabilidad(datos), use_container_width=True, config=_CONFIG)

    # ── Gauge P(0-0) para mercados Sin Goles ──
    es_sin_goles = "Sin Goles" in mercado or "0-0" in mercado or "Sin Goleador" in mercado
    if es_sin_goles and datos.get("sin_goles_calculado"):
        sg = datos["sin_goles_calculado"]
        st.plotly_chart(gauge_p00(datos), use_container_width=True, config=_CONFIG)
        advertencia = sg.get("advertencia")
        if advertencia:
            st.markdown(
                f'<div class="alerta-peligro" style="font-size:12px;">{advertencia}</div>',
                unsafe_allow_html=True,
            )
        st.markdown(
            f'<div style="font-family:Courier New,monospace;font-size:12px;'
            f'background:{PANEL};border:1px solid {BORDER};border-radius:6px;'
            f'padding:10px 14px;margin-top:6px;">'
            f'<div style="color:{TEXT};font-size:9px;letter-spacing:1px;'
            f'margin-bottom:6px;">FÓRMULA POISSON</div>'
            f'<div style="color:{GREEN};font-size:13px;font-weight:700;">'
            f'{sg.get("formula", "—")}</div>'
            f'<div style="margin-top:8px;font-size:10px;color:{LIGHT};">'
            f'Cuota justa: <b style="color:{YELLOW};">{sg.get("cuota_justa_modelo","—")}</b>'
            f'&nbsp;&nbsp;|&nbsp;&nbsp;'
            f'Local 1º: <b>{sg.get("p_local_marca_1ro","—")}</b>'
            f'&nbsp;&nbsp;|&nbsp;&nbsp;'
            f'Visitante 1º: <b>{sg.get("p_visitante_marca_1ro","—")}</b>'
            f'&nbsp;&nbsp;|&nbsp;&nbsp;'
            f'Nadie marca: <b style="color:{GREEN};">{sg.get("p_nadie_marca","—")}</b>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

    # ── Donut solo para Ambos Marcan ──
    if "Ambos Marcan" in mercado:
        xg_l, xg_v = _xg_de_datos(datos)
        if xg_l > 0 and xg_v > 0:
            st.plotly_chart(donut_ambos_marcan(datos), use_container_width=True, config=_CONFIG)
            cuotas    = datos.get("cuotas_reales", {})
            edge_dict = datos.get("edge_por_outcome", {})

            def _color_edge(key: str) -> str:
                try:
                    raw = str(edge_dict.get(key, "0")).replace("+", "").replace("%", "")
                    return GREEN if float(raw or 0) >= 10 else RED
                except (ValueError, TypeError):
                    return GRAY

            if cuotas:
                filas_html = ""
                for k, v in cuotas.items():
                    cuota_val = v.get("mejor_cuota", "—")
                    edge_val  = edge_dict.get(k, "—")
                    col_edge  = _color_edge(k)
                    filas_html += (
                        f"<tr>"
                        f"<td style='color:{LIGHT};font-size:10px;padding:3px 8px;'>{k}</td>"
                        f"<td style='color:{GREEN};font-size:10px;font-family:Courier New;"
                        f"padding:3px 8px;'>{cuota_val}</td>"
                        f"<td style='font-size:10px;font-family:Courier New;"
                        f"padding:3px 8px;color:{col_edge};'>{edge_val}</td>"
                        f"</tr>"
                    )
                st.markdown(
                    f'<table style="width:100%;border-collapse:collapse;background:{PANEL};">'
                    f'<thead><tr>'
                    f'<th style="font-size:9px;color:{TEXT};font-family:Courier New;'
                    f'padding:3px 8px;text-align:left;">OUTCOME</th>'
                    f'<th style="font-size:9px;color:{TEXT};font-family:Courier New;'
                    f'padding:3px 8px;">CUOTA</th>'
                    f'<th style="font-size:9px;color:{TEXT};font-family:Courier New;'
                    f'padding:3px 8px;">EDGE</th>'
                    f'</tr></thead><tbody>{filas_html}</tbody></table>',
                    unsafe_allow_html=True,
                )


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


def gauge_donut_gris(valor: float, titulo: str, color: str = DEOP_DORADO,
                      maximo: float = 100.0) -> go.Figure:
    """Donut gris estilo DeOP Connect (CPU/RAM/Disco) para un valor 0-100%."""
    valor_clamp = max(0.0, min(float(valor), maximo))
    fig = go.Figure(go.Pie(
        values=[valor_clamp, maximo - valor_clamp],
        hole=0.72,
        marker=dict(colors=[color, DEOP_GRIS], line=dict(color="#ffffff", width=2)),
        textinfo="none",
        hoverinfo="skip",
        direction="clockwise",
        sort=False,
    ))
    fig.add_annotation(
        text=f"<b>{valor_clamp:.0f}%</b>", x=0.5, y=0.56, showarrow=False,
        font=dict(family="Inter, sans-serif", size=22, color=DEOP_PETROLEO),
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


def tarjeta_veredicto_html(titulo: str, valor_texto: str, estado: str) -> str:
    """Tarjeta amarilla estilo DeOP (triángulo de alerta) con semáforo de estado."""
    if estado == "APOSTAR":
        col, icono = DEOP_VERDE, "🟢"
    elif estado == "PRECAUCIÓN":
        col, icono = DEOP_DORADO, "🟡"
    else:
        col, icono = DEOP_ROJO, "🔴"
    return (
        f'<div style="background:#fff9e6;border:1px solid #f5d061;border-left:5px solid {col};'
        f'border-radius:8px;padding:12px 14px;margin-bottom:8px;min-height:96px;">'
        f'<div style="font-size:11px;color:#7a6a2a;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:.6px;margin-bottom:4px;">⚠️ {titulo}</div>'
        f'<div style="font-size:15px;font-weight:800;color:#3a2f00;margin-bottom:6px;">{valor_texto}</div>'
        f'<div style="display:inline-block;background:{col}1a;border:1px solid {col};border-radius:5px;'
        f'padding:2px 10px;font-size:11px;font-weight:800;color:{col};">{icono} {estado}</div>'
        f'</div>'
    )


def panel_info_partido_html(datos: dict) -> str:
    """Cuadro de información del partido: equipos, xG, ELO, forma reciente."""
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
        f'border-bottom:1px solid #eef2f5;">{label}</td>'
        f'<td style="padding:5px 10px;font-weight:700;color:{DEOP_PETROLEO};font-size:12px;'
        f'border-bottom:1px solid #eef2f5;">{valor}</td></tr>'
        for label, valor in filas
    )
    return (
        f'<div style="background:#ffffff;border:1px solid {DEOP_GRIS};border-radius:8px;'
        f'padding:6px 4px;margin-bottom:8px;">'
        f'<div style="font-size:10px;color:{DEOP_PETROLEO};font-weight:800;letter-spacing:1px;'
        f'padding:6px 10px;text-transform:uppercase;border-bottom:2px solid {DEOP_DORADO};">'
        f'◈ Información del Partido</div>'
        f'<table style="width:100%;border-collapse:collapse;">{filas_html}</table>'
        f'</div>'
    )


def tabla_ultimos_analisis_html(registros: list, limite: int = 8) -> str:
    """Tabla HTML de los últimos partidos analizados con su veredicto."""
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
            f'<td style="padding:5px 10px;font-size:11px;color:{DEOP_PETROLEO};font-weight:600;">'
            f'{r.get("partido", "—")}</td>'
            f'<td style="padding:5px 10px;font-size:11px;color:{DEOP_TEXTO};">{r.get("mercado", "—")}</td>'
            f'<td style="padding:5px 10px;font-size:11px;font-weight:700;color:{col};">'
            f'{r.get("veredicto", "—")}</td>'
            f'<td style="padding:5px 10px;font-size:10px;color:#8aaa99;white-space:nowrap;">'
            f'{r.get("fecha_hora", "—")}</td>'
            f'</tr>'
        )
    return (
        f'<div style="background:#ffffff;border:1px solid {DEOP_GRIS};border-radius:8px;'
        f'padding:6px 4px;margin-bottom:8px;">'
        f'<div style="font-size:10px;color:{DEOP_PETROLEO};font-weight:800;letter-spacing:1px;'
        f'padding:6px 10px;text-transform:uppercase;border-bottom:2px solid {DEOP_DORADO};">'
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
