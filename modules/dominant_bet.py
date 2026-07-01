"""Módulo: Apuesta Dominada — detecta partidos de dominancia extrema."""

import math
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

os.makedirs(Path(__file__).parent.parent / "data", exist_ok=True)

# ── Umbrales de dominancia ────────────────────────────────────────────────────
DIFF_ELO_MIN      = 10.0
P_VICTORIA_MIN    = 0.76
XG_FAV_MIN        = 2.30
XG_RIVAL_MAX      = 0.60
REGLAS_NECESARIAS = 3

_CUOTA_OVER15_DEFAULT = 1.65
_RUTA_ODDS    = Path(__file__).parent.parent / "data" / "odds.csv"
_RUTA_HIST    = Path(__file__).parent.parent / "data" / "dominant_history.json"

_CSS = """
<style>
.dom-panel { background:#ffffff; border:1px solid #e2e8f0; border-radius:6px;
             padding:10px 14px; margin-bottom:8px;
             font-family:'Courier New',monospace; }
.dom-hdr   { font-size:9px; color:#0d3b4f; font-weight:800; letter-spacing:2px;
             border-bottom:2px solid #f5a623; padding-bottom:5px; margin-bottom:10px; }
</style>"""


# ── Lógica ────────────────────────────────────────────────────────────────────

def detectar_partido_dominante(
    elo_fav: float, elo_rival: float,
    p_victoria: float, xg_fav: float, xg_rival: float,
) -> dict:
    """≥ 3/4 reglas cumplidas → DOMINANTE."""
    reglas = [
        ("ELO diff ≥ 10",      elo_fav - elo_rival >= DIFF_ELO_MIN,  f"{elo_fav - elo_rival:+.0f} pts"),
        ("P(victoria) ≥ 76%",  p_victoria >= P_VICTORIA_MIN,          f"{p_victoria * 100:.1f}%"),
        ("xG favorito ≥ 2.30", xg_fav >= XG_FAV_MIN,                  f"{xg_fav:.2f}"),
        ("xG rival ≤ 0.60",    xg_rival <= XG_RIVAL_MAX,              f"{xg_rival:.2f}"),
    ]
    cumplidas = sum(1 for _, ok, _ in reglas if ok)
    return {
        "es_dominante":     cumplidas >= REGLAS_NECESARIAS,
        "reglas_cumplidas": cumplidas,
        "reglas":           reglas,
    }


def _p_over15(xg_fav: float, xg_rival: float) -> float:
    """P(total goles > 1.5) con Poisson independiente, en %."""
    p_f0 = math.exp(-xg_fav)
    p_r0 = math.exp(-xg_rival)
    p_0  = p_f0 * p_r0
    p_1  = (xg_fav * p_f0) * p_r0 + p_f0 * (xg_rival * p_r0)
    return round((1 - p_0 - p_1) * 100, 1)


def _p_handicap_minus1(xg_fav: float, xg_rival: float) -> float:
    """P(favorito gana por 2+ goles), en %."""
    total = 0.0
    for gf in range(10):
        for gr in range(8):
            if gf - gr >= 2:
                total += (
                    math.exp(-xg_fav)  * xg_fav **gf / math.factorial(gf) *
                    math.exp(-xg_rival) * xg_rival**gr / math.factorial(gr)
                )
    return round(total * 100, 1)


def _top_marcadores(xg_fav: float, xg_rival: float, n: int = 5) -> list[dict]:
    items = [
        {
            "marcador": f"{gf}–{gr}",
            "prob": (math.exp(-xg_fav)  * xg_fav **gf / math.factorial(gf)) *
                    (math.exp(-xg_rival) * xg_rival**gr / math.factorial(gr)),
            "gf": gf, "gr": gr,
        }
        for gf in range(8) for gr in range(6)
    ]
    items.sort(key=lambda x: x["prob"], reverse=True)
    return items[:n]


def _cuota_over15_csv(partido: str) -> float:
    try:
        df   = pd.read_csv(_RUTA_ODDS)
        fila = df[
            (df["partido"] == partido) &
            (df["mercado"].str.contains("1.5", na=False)) &
            (df["resultado"].str.contains("Over", case=False, na=False))
        ]
        if not fila.empty:
            casas = ["codere", "bet365", "betfair"]
            vals  = [float(fila.iloc[0].get(c, 0) or 0) for c in casas]
            valid = [v for v in vals if v > 1.0]
            if valid:
                return max(valid)
    except Exception:
        pass
    return _CUOTA_OVER15_DEFAULT


def _guardar_historial_dom(d: dict, res: dict, p_o15: float, p_hcp: float,
                           cuota_o15: float, edge_o15: float,
                           estado: str, top5: list) -> None:
    """Guarda el análisis de Apuesta Dominada en data/dominant_history.json."""
    import json
    from datetime import datetime

    top = top5[0] if top5 else {}
    entrada = {
        "fecha_hora":   datetime.now().strftime("%d/%m/%Y %H:%M"),
        "partido":      d["partido"],
        "nom_fav":      d["nom_fav"],
        "nom_riv":      d["nom_riv"],
        "xg_fav":       round(d["xg_fav"],   2),
        "xg_rival":     round(d["xg_rival"],  2),
        "elo_fav":      d["elo_fav"],
        "elo_riv":      d["elo_riv"],
        "p_victoria":   round(d["p_victoria"] * 100, 1),
        "es_dominante": res["es_dominante"],
        "n_ok":         res["reglas_cumplidas"],
        "reglas":       [[lbl, ok, val] for lbl, ok, val in res["reglas"]],
        "p_o15":        p_o15,
        "p_hcp":        p_hcp,
        "cuota_o15":    cuota_o15,
        "edge_o15":     edge_o15,
        "estado":       estado,
        "top_marcador": top.get("marcador", "—"),
        "top_prob":     round(top.get("prob", 0) * 100, 1),
    }
    historial: list = []
    if _RUTA_HIST.exists():
        try:
            import json as _j
            historial = _j.loads(_RUTA_HIST.read_text(encoding="utf-8"))
        except Exception:
            historial = []
    historial.insert(0, entrada)
    try:
        import json as _j
        with open(_RUTA_HIST, "w", encoding="utf-8") as f:
            _j.dump(historial, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        st.warning(f"⚠️ No se pudo guardar: {exc}")


def _leer_datos_sesion() -> dict:
    partido   = st.session_state.get("partido_activo", "")
    probs     = st.session_state.get("probs_partido", {})
    elo_local = float(st.session_state.get("elo_local", 0) or 0)
    elo_visit = float(st.session_state.get("elo_visit", 0) or 0)

    xg_l = float(probs.get("xg_local",     0) or 0)
    xg_v = float(probs.get("xg_visitante", 0) or 0)

    p_victoria = 0.0
    for k, v in probs.items():
        if k.startswith("victoria_"):
            try:
                val = float(str(v).replace("%", "").strip())
                p_victoria = max(p_victoria, val)
            except (ValueError, TypeError):
                pass
    if p_victoria > 1:
        p_victoria /= 100.0

    partes = partido.split(" vs ", 1)
    if xg_l >= xg_v:
        xg_fav, xg_rival = xg_l, xg_v
        elo_fav, elo_riv = elo_local, elo_visit
        nom_fav = partes[0].strip() if partes else "Local"
        nom_riv = partes[1].strip() if len(partes) > 1 else "Visitante"
    else:
        xg_fav, xg_rival = xg_v, xg_l
        elo_fav, elo_riv = elo_visit, elo_local
        nom_fav = partes[1].strip() if len(partes) > 1 else "Visitante"
        nom_riv = partes[0].strip() if partes else "Local"

    return {
        "partido": partido, "nom_fav": nom_fav, "nom_riv": nom_riv,
        "xg_fav": xg_fav,   "xg_rival": xg_rival,
        "elo_fav": elo_fav,  "elo_riv": elo_riv,
        "p_victoria": p_victoria,
        "tiene_datos": bool(partido) and (xg_l > 0 or xg_v > 0),
    }


def _barras_dom(p_o15: float, p_victoria: float, p_handicap: float,
                nom_fav: str) -> go.Figure:
    """Barras horizontales SCADA para Over 1.5 / Victoria / Hándicap -1."""
    BG_     = "#0e1117"
    PANEL_  = "#080c14"
    BORDER_ = "#1a2540"
    GREEN_  = "#00ff88"
    GRAY_   = "#1e2d45"
    TEXT_   = "#5a7a9a"
    LIGHT_  = "#8eb0cc"
    FONT_   = dict(family="'Courier New', monospace", color=LIGHT_)

    labels  = [f"Hándicap −1 {nom_fav[:10]}", f"Victoria {nom_fav[:10]}", "Over 1.5 goles"]
    valores = [p_handicap, p_victoria, p_o15]
    colores = [GREEN_ if v >= 60 else GRAY_ for v in valores]

    fig = go.Figure()
    for lbl, val, col in zip(labels, valores, colores):
        fig.add_trace(go.Bar(
            x=[val], y=[lbl], orientation="h",
            marker=dict(color=col, line=dict(color=BORDER_, width=1)),
            text=f"{val:.1f}%", textposition="inside",
            textfont=dict(family="Courier New", size=9,
                          color=BG_ if col != GRAY_ else LIGHT_),
            showlegend=False,
        ))
        fig.add_trace(go.Bar(
            x=[100 - val], y=[lbl], orientation="h",
            marker=dict(color="#121c2e", line=dict(color=BORDER_, width=1)),
            showlegend=False, hoverinfo="skip",
        ))
    for tick in range(0, 101, 10):
        fig.add_vline(x=tick, line=dict(color=BORDER_, width=1, dash="dot"))

    fig.update_layout(
        paper_bgcolor=BG_, plot_bgcolor=PANEL_, font=FONT_,
        margin=dict(l=8, r=8, t=28, b=8),
        showlegend=False, height=130, barmode="stack",
        title=dict(text="◈ PROBABILIDADES — MERCADOS PRINCIPALES",
                   font=dict(size=9, color=TEXT_, family="Courier New"), x=0.01),
        xaxis=dict(range=[0, 100], showgrid=False, showline=True,
                   linecolor=BORDER_, ticksuffix="%", dtick=20,
                   tickfont=dict(size=8, color=TEXT_, family="Courier New")),
        yaxis=dict(showgrid=False,
                   tickfont=dict(size=9, color=LIGHT_, family="Courier New")),
        bargap=0.35,
    )
    return fig


# ── Renderizado principal ─────────────────────────────────────────────────────

def mostrar() -> None:
    from modules.scada_charts import (
        _CONFIG, _CSS_COMPACTO,
        GREEN, RED, YELLOW,
        donut_ambos_marcan, semaforo_html,
        gauge_donut_gris, tarjeta_veredicto_html,
        DEOP_PETROLEO, DEOP_DORADO,
    )

    st.markdown(_CSS_COMPACTO + _CSS, unsafe_allow_html=True)

    d = _leer_datos_sesion()
    if not d["tiene_datos"]:
        st.markdown(
            '<div class="dom-panel" style="color:#5a7a9a;font-size:12px;">'
            'Selecciona un partido en <b>Análisis de Partidos</b> '
            'para activar la detección de dominancia.</div>',
            unsafe_allow_html=True,
        )
        return

    partido    = d["partido"]
    nom_fav    = d["nom_fav"]
    nom_riv    = d["nom_riv"]
    xg_fav     = d["xg_fav"]
    xg_rival   = d["xg_rival"]
    elo_fav    = d["elo_fav"]
    elo_riv    = d["elo_riv"]
    p_victoria = d["p_victoria"]

    res    = detectar_partido_dominante(elo_fav, elo_riv, p_victoria, xg_fav, xg_rival)
    es_dom = res["es_dominante"]
    n_ok   = res["reglas_cumplidas"]

    # Valores para los gráficos SCADA
    p_o15      = _p_over15(xg_fav, xg_rival)
    p_hcp      = _p_handicap_minus1(xg_fav, xg_rival)
    cuota_o15  = _cuota_over15_csv(partido)
    edge_o15   = round((cuota_o15 * (p_o15 / 100) - 1) * 100, 1)
    conf_nivel = "Alto" if n_ok >= 4 else ("Medio" if n_ok >= 3 else "Bajo")
    conf_pct   = {"Alto": 85.0, "Medio": 50.0, "Bajo": 18.0}[conf_nivel]
    datos_donut = {"probabilidades": {"xg_local": xg_fav, "xg_visitante": xg_rival}}
    if edge_o15 < 6.0:
        _estado_dom = "NO APOSTAR"
    elif es_dom:
        _estado_dom = "APOSTAR"
    elif n_ok >= 2:
        _estado_dom = "PRECAUCIÓN"
    else:
        _estado_dom = "NO APOSTAR"
    punt_dom = {"estado": _estado_dom, "puntos": n_ok}

    # Cabecera
    st.markdown(
        f'<div style="font-size:14px;color:#5a7a9a;margin-bottom:12px;">'
        f'⚽ <span style="color:{DEOP_PETROLEO};font-weight:700;">{partido}</span></div>',
        unsafe_allow_html=True,
    )

    col_izq, col_der = st.columns([1.1, 1], gap="medium")

    # ════════════════════════════════════════════════════════════
    # COLUMNA IZQUIERDA — datos del partido + reglas
    # ════════════════════════════════════════════════════════════
    with col_izq:

        # Tarjetas xG + P(victoria)
        st.markdown(
            f'<div style="display:flex;gap:6px;margin-bottom:10px;">'

            f'<div style="flex:1;background:#f0fdf4;border:1px solid #bbf0cc;'
            f'border-radius:6px;padding:8px 6px;text-align:center;">'
            f'<div style="font-size:9px;color:#5a7a9a;text-transform:uppercase;'
            f'letter-spacing:.5px;margin-bottom:2px;">{nom_fav[:12]}</div>'
            f'<div style="font-size:24px;font-weight:900;color:{GREEN};line-height:1;">'
            f'{xg_fav:.2f}</div>'
            f'<div style="font-size:9px;color:#5a7a9a;">xG favorito</div>'
            f'</div>'

            f'<div style="flex:1;background:#fff9e6;border:1px solid #f5d061;'
            f'border-radius:6px;padding:8px 6px;text-align:center;">'
            f'<div style="font-size:9px;color:#5a7a9a;text-transform:uppercase;'
            f'letter-spacing:.5px;margin-bottom:2px;">P VICTORIA</div>'
            f'<div style="font-size:24px;font-weight:900;color:#b8780f;line-height:1;">'
            f'{p_victoria*100:.1f}%</div>'
            f'<div style="font-size:9px;color:#5a7a9a;">probabilidad</div>'
            f'</div>'

            f'<div style="flex:1;background:#fef2f2;border:1px solid #f3c6c6;'
            f'border-radius:6px;padding:8px 6px;text-align:center;">'
            f'<div style="font-size:9px;color:#5a7a9a;text-transform:uppercase;'
            f'letter-spacing:.5px;margin-bottom:2px;">{nom_riv[:12]}</div>'
            f'<div style="font-size:24px;font-weight:900;color:{RED};line-height:1;">'
            f'{xg_rival:.2f}</div>'
            f'<div style="font-size:9px;color:#5a7a9a;">xG rival</div>'
            f'</div>'

            f'</div>',
            unsafe_allow_html=True,
        )

        # ELO
        diff_elo = elo_fav - elo_riv
        col_elo  = GREEN if diff_elo >= DIFF_ELO_MIN else (YELLOW if diff_elo > 0 else "#5a7a9a")
        if elo_fav == 0 and elo_riv == 0:
            elo_inner = (
                f'<span style="color:#5a7a9a;font-size:10px;">'
                f'ELO no disponible — introdúcelo en Análisis de Partidos</span>'
            )
        else:
            elo_inner = (
                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                f'<span style="font-size:11px;color:#1a2c38;">'
                f'{nom_fav[:13]} <b style="color:#b8780f;">{elo_fav:.0f}</b></span>'
                f'<span style="font-size:14px;font-weight:800;color:{col_elo};">'
                f'Δ {diff_elo:+.0f}</span>'
                f'<span style="font-size:11px;color:#1a2c38;">'
                f'{nom_riv[:13]} <b style="color:{RED};">{elo_riv:.0f}</b></span>'
                f'</div>'
            )
        st.markdown(
            f'<div class="dom-panel">'
            f'<div class="dom-hdr">◈ CLASIFICACIÓN ELO</div>'
            f'{elo_inner}'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Reglas de dominancia
        filas_r = ""
        for label, ok, valor in res["reglas"]:
            col_r = GREEN if ok else RED
            filas_r += (
                f'<div style="display:flex;justify-content:space-between;'
                f'align-items:center;padding:5px 0;border-bottom:1px solid #eef2f5;">'
                f'<span style="font-size:10px;color:#1a2c38;">{"✅" if ok else "❌"} {label}</span>'
                f'<span style="font-size:11px;font-weight:700;color:{col_r};">{valor}</span>'
                f'</div>'
            )
        col_n = GREEN if n_ok >= REGLAS_NECESARIAS else (YELLOW if n_ok == 2 else RED)
        st.markdown(
            f'<div class="dom-panel">'
            f'<div class="dom-hdr">◈ REGLAS DE DOMINANCIA</div>'
            f'{filas_r}'
            f'<div style="margin-top:8px;text-align:right;font-size:10px;color:#5a7a9a;">'
            f'Reglas: <b style="color:{col_n};font-size:16px;">{n_ok}</b>/4'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ── Panel Top 5 Marcadores SCADA ─────────────────────────────────────
        top5     = _top_marcadores(xg_fav, xg_rival)
        prob_max = top5[0]["prob"] if top5 else 1.0
        top_item = top5[0] if top5 else {"marcador": "—", "prob": 0, "gf": 0, "gr": 0}

        top_favorece_fav = top_item["gf"] > top_item["gr"]
        top_pct          = round(top_item["prob"] * 100, 1)

        # Colores del panel según dominancia global
        panel_brd = "#00ff41" if es_dom else "#ff4444"
        panel_glow = f"0 0 8px {panel_brd}55"

        # Semáforo mini (3 círculos verticales: rojo / amarillo / verde)
        _c_r = "#ff4444" if not top_favorece_fav else "#1a0404"
        _c_a = "#f5a623" if (not top_favorece_fav and top_item["gf"] == top_item["gr"]) else "#1a1200"
        _c_g = "#00ff41" if top_favorece_fav else "#021209"
        _gw_r = f"0 0 8px #ff444488" if not top_favorece_fav else "none"
        _gw_g = f"0 0 8px #00ff4188" if top_favorece_fav else "none"
        semaforo_mini = (
            f'<div style="display:flex;flex-direction:column;align-items:center;gap:3px;'
            f'background:#080c14;border:1px solid #1a2540;border-radius:4px;padding:4px 5px;">'
            f'<div style="width:10px;height:10px;border-radius:50%;background:{_c_r};'
            f'box-shadow:{_gw_r};border:1px solid #1a2540;"></div>'
            f'<div style="width:10px;height:10px;border-radius:50%;background:{_c_a};'
            f'border:1px solid #1a2540;"></div>'
            f'<div style="width:10px;height:10px;border-radius:50%;background:{_c_g};'
            f'box-shadow:{_gw_g};border:1px solid #1a2540;"></div>'
            f'</div>'
        )

        # Barras de marcadores
        filas_m = ""
        for i, item in enumerate(top5):
            pct   = round(item["prob"] * 100, 1)
            ancho = round((item["prob"] / prob_max) * 86)
            if i == 0:
                col_bar = "#ffd700"
                col_txt = "#ffd700"
                badge   = (
                    ' <span style="font-size:8px;background:#2a2000;color:#ffd700;'
                    'border:1px solid #ffd700;border-radius:3px;padding:1px 5px;'
                    'font-weight:700;">★ TOP</span>'
                )
            elif item["gf"] > item["gr"]:
                col_bar = "#00ff41"
                col_txt = "#ffffff"
                badge   = ""
            else:
                col_bar = "#555555"
                col_txt = "#999999"
                badge   = ""

            filas_m += (
                f'<div style="margin:5px 0;">'
                f'<div style="display:flex;justify-content:space-between;'
                f'align-items:center;margin-bottom:3px;">'
                f'<span style="font-size:14px;font-weight:700;color:{col_txt};">'
                f'{item["marcador"]}{badge}</span>'
                f'<span style="font-size:11px;color:#8eb0cc;font-weight:600;">{pct}%</span>'
                f'</div>'
                f'<div style="background:#1a1f2e;border-radius:3px;height:8px;'
                f'overflow:hidden;border:1px solid #1a2540;">'
                f'<div style="width:{ancho}%;height:100%;background:{col_bar};'
                f'border-radius:2px;'
                f'box-shadow:0 0 6px {col_bar}66;"></div>'
                f'</div>'
                f'</div>'
            )

        # Línea de conclusión
        if top_favorece_fav:
            concl_col  = "#00ff41"
            concl_ico  = "✅"
            concl_txt  = "FAVORECE AL FAVORITO"
        elif top_item["gf"] == top_item["gr"]:
            concl_col  = "#f5a623"
            concl_ico  = "⚠️"
            concl_txt  = "EMPATE MÁS PROBABLE"
        else:
            concl_col  = "#ff4444"
            concl_ico  = "❌"
            concl_txt  = "FAVORECE AL RIVAL"

        concl_html = (
            f'<div style="margin-top:10px;padding-top:8px;border-top:1px solid #1a2540;'
            f'font-size:11px;color:{concl_col};font-weight:700;'
            f'font-family:Courier New,monospace;">'
            f'Marcador más probable: '
            f'<b style="font-size:13px;">{top_item["marcador"]}</b> '
            f'({top_pct}%) — {concl_txt} {concl_ico}'
            f'</div>'
        )

        st.markdown(
            f'<div style="background:#0d1117;border:2px solid {panel_brd};'
            f'box-shadow:{panel_glow};border-radius:6px;padding:10px 14px;'
            f'margin-bottom:8px;font-family:Courier New,monospace;">'
            f'<div style="display:flex;justify-content:space-between;'
            f'align-items:center;border-bottom:1px solid #1a2540;'
            f'padding-bottom:6px;margin-bottom:10px;">'
            f'<span style="font-size:9px;color:#5a7a9a;letter-spacing:2px;">'
            f'◈ TOP 5 MARCADORES MÁS PROBABLES</span>'
            f'{semaforo_mini}'
            f'</div>'
            f'{filas_m}'
            f'{concl_html}'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ════════════════════════════════════════════════════════════
    # COLUMNA DERECHA — semáforo + veredicto + gráficos SCADA
    # ════════════════════════════════════════════════════════════
    with col_der:

        # 1. Semáforo vertical centrado
        st.markdown(
            f'<div style="display:flex;justify-content:center;padding:8px 0 4px;">'
            f'{semaforo_html(edge_o15, punt_dom)}'
            f'</div>',
            unsafe_allow_html=True,
        )

        # 2. Veredicto grande — tarjeta amarilla DeOP
        label_v = f"{nom_fav} — {top_item['marcador'] if top5 else '—'}" if es_dom else "Sin dominancia clara"
        st.markdown(
            tarjeta_veredicto_html("Apuesta Dominada", label_v, _estado_dom),
            unsafe_allow_html=True,
        )

        # Apuestas recomendadas (solo cuando es dominante)
        if es_dom:
            apuestas = [
                ("⚽ Over 1.5 goles",           f"{p_o15}%",           "cuota ref. {:.2f}".format(cuota_o15)),
                (f"🏆 Victoria {nom_fav[:13]}", f"{p_victoria*100:.1f}%", "favorito claro"),
                ("📉 Hándicap −1 favorito",     f"{p_hcp}%",           "gana por 2+ goles"),
            ]
            filas_ap = ""
            for nom_ap, prob_ap, desc_ap in apuestas:
                filas_ap += (
                    f'<div style="display:flex;justify-content:space-between;'
                    f'align-items:center;padding:6px 0;border-bottom:1px solid #eef2f5;">'
                    f'<div>'
                    f'<div style="font-size:11px;color:#1a2c38;font-weight:600;">{nom_ap}</div>'
                    f'<div style="font-size:9px;color:#5a7a9a;">{desc_ap}</div>'
                    f'</div>'
                    f'<span style="font-size:15px;font-weight:900;color:{GREEN};">{prob_ap}</span>'
                    f'</div>'
                )
            st.markdown(
                f'<div class="dom-panel">'
                f'<div class="dom-hdr">◈ APUESTAS RECOMENDADAS</div>'
                f'{filas_ap}'
                f'</div>',
                unsafe_allow_html=True,
            )

        # 3. Gauge Edge (Over 1.5)
        st.plotly_chart(
            gauge_donut_gris(max(0.0, edge_o15), "Edge %", DEOP_DORADO),
            use_container_width=True, config=_CONFIG, key="dom_gauge_edge",
        )

        # 4. Gauge Confianza (% reglas cumplidas)
        st.plotly_chart(
            gauge_donut_gris(conf_pct, "Confianza %", DEOP_PETROLEO),
            use_container_width=True, config=_CONFIG, key="dom_gauge_conf",
        )

        # 5. Donut BTTS
        st.plotly_chart(
            donut_ambos_marcan(datos_donut),
            use_container_width=True, config=_CONFIG, key="dom_donut",
        )

        # 6. Barras Over 1.5 / Victoria / Hándicap -1
        st.plotly_chart(
            _barras_dom(p_o15, p_victoria * 100, p_hcp, nom_fav),
            use_container_width=True, config=_CONFIG, key="dom_barras",
        )

        # 7. Botón guardar historial
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        if st.button("💾 Guardar en historial", key="btn_guardar_dom",
                     use_container_width=True):
            _guardar_historial_dom(
                d, res, p_o15, p_hcp, cuota_o15, edge_o15,
                _estado_dom, _top_marcadores(xg_fav, xg_rival),
            )
            st.success("✅ Análisis guardado en historial")
