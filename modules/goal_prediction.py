"""Módulo: Predicción de Goles — xG summary + Top 5 marcadores via Poisson"""

from pathlib import Path
import pandas as pd
import streamlit as st
from scipy.stats import poisson

RUTA_PARTIDOS = Path(__file__).parent.parent / "data" / "matches.csv"
_MAXIMO_GOLES = 8


def _cargar_xg(partido: str) -> tuple[float, float, str, str]:
    """Lee xG y nombres de equipo de matches.csv para el partido activo."""
    if partido and RUTA_PARTIDOS.exists():
        try:
            df = pd.read_csv(RUTA_PARTIDOS)
            fila = df[df["partido"] == partido]
            if not fila.empty:
                row = fila.iloc[0]
                return (
                    float(row.get("xg_local", 1.5)),
                    float(row.get("xg_visitante", 1.2)),
                    str(row.get("equipo_local", "Local")),
                    str(row.get("equipo_visitante", "Visitante")),
                )
        except Exception:
            pass
    return 1.5, 1.2, "Local", "Visitante"


def calcular_top_marcadores(xg_local: float, xg_visitante: float, top_n: int = 5) -> list[dict]:
    """Devuelve los N marcadores más probables según la distribución de Poisson conjunta."""
    scores = [
        {
            "marcador": f"{gl}-{gv}",
            "gl": gl,
            "gv": gv,
            "prob": poisson.pmf(gl, xg_local) * poisson.pmf(gv, xg_visitante),
        }
        for gl in range(_MAXIMO_GOLES)
        for gv in range(_MAXIMO_GOLES)
    ]
    scores.sort(key=lambda x: x["prob"], reverse=True)
    return scores[:top_n]


def mostrar() -> None:
    """Renderiza el panel completo de Predicción de Goles."""
    partido   = st.session_state.get("partido_activo", "")
    xg_l, xg_v, nombre_l, nombre_v = _cargar_xg(partido)
    total_xg  = round(xg_l + xg_v, 2)
    top5      = calcular_top_marcadores(xg_l, xg_v)

    # ── Cabecera con partido activo ────────────────────────────────────
    if partido:
        st.markdown(
            f'<div style="font-size:10px;color:#8aaa99;margin-bottom:8px;'
            f'border-left:3px solid #00aa44;padding-left:6px;">{partido}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="font-size:10px;color:#8aaa99;margin-bottom:8px;">'
            'Selecciona un partido en Análisis</div>',
            unsafe_allow_html=True,
        )

    # ── Tarjetas xG ────────────────────────────────────────────────────
    nombre_l_corto = nombre_l[:13] + "…" if len(nombre_l) > 13 else nombre_l
    nombre_v_corto = nombre_v[:13] + "…" if len(nombre_v) > 13 else nombre_v

    st.markdown(f"""
<div style="display:flex;gap:6px;margin-bottom:12px;">
  <div style="flex:1;background:#0d1a10;border:1px solid #1e3a2a;border-radius:8px;
              padding:8px 6px;text-align:center;">
    <div style="font-size:9px;color:#8aaa99;text-transform:uppercase;
                margin-bottom:3px;letter-spacing:.5px;">{nombre_l_corto}</div>
    <div style="font-size:20px;font-weight:800;color:#00aa44;line-height:1.1;">{xg_l}</div>
    <div style="font-size:9px;color:#8aaa99;">xG local</div>
  </div>
  <div style="flex:1;background:#1a1500;border:1px solid #3a2a00;border-radius:8px;
              padding:8px 6px;text-align:center;">
    <div style="font-size:9px;color:#8aaa99;text-transform:uppercase;
                margin-bottom:3px;letter-spacing:.5px;">Total</div>
    <div style="font-size:20px;font-weight:800;color:#ffd700;line-height:1.1;">{total_xg}</div>
    <div style="font-size:9px;color:#8aaa99;">xG total</div>
  </div>
  <div style="flex:1;background:#080d1a;border:1px solid #1a2540;border-radius:8px;
              padding:8px 6px;text-align:center;">
    <div style="font-size:9px;color:#8aaa99;text-transform:uppercase;
                margin-bottom:3px;letter-spacing:.5px;">{nombre_v_corto}</div>
    <div style="font-size:20px;font-weight:800;color:#4499ff;line-height:1.1;">{xg_v}</div>
    <div style="font-size:9px;color:#8aaa99;">xG visitante</div>
  </div>
</div>""", unsafe_allow_html=True)

    # ── Top 5 marcadores ───────────────────────────────────────────────
    st.markdown(
        '<div style="font-size:10px;font-weight:700;color:#00aa44;text-transform:uppercase;'
        'letter-spacing:.8px;margin-bottom:6px;">Top 5 marcadores más probables</div>',
        unsafe_allow_html=True,
    )

    prob_max = top5[0]["prob"] if top5 else 1.0  # normalizar barras al primer resultado

    filas_html = ""
    for i, item in enumerate(top5):
        pct      = round(item["prob"] * 100, 1)
        ancho    = round((item["prob"] / prob_max) * 88)   # barra normalizada, máx 88%

        if i == 0:
            color_barra    = "#ffd700"
            color_marcador = "#ffd700"
            badge = (
                '<span style="margin-left:6px;background:#2a2000;color:#ffd700;'
                'border:1px solid #ffd700;border-radius:3px;font-size:8px;'
                'padding:1px 5px;font-weight:700;vertical-align:middle;">'
                '★ MÁS PROBABLE</span>'
            )
        else:
            if item["gl"] > item["gv"]:
                color_barra = "#00aa44"
            elif item["gl"] < item["gv"]:
                color_barra = "#4499ff"
            else:
                color_barra = "#888888"
            color_marcador = "#cccccc"
            badge = ""

        filas_html += f"""
<div style="margin:5px 0;">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:3px;">
    <span style="font-size:14px;font-weight:700;color:{color_marcador};">{item['marcador']}{badge}</span>
    <span style="font-size:11px;color:#8aaa99;font-weight:600;">{pct}%</span>
  </div>
  <div style="background:#1a2820;border-radius:3px;height:7px;overflow:hidden;">
    <div style="width:{ancho}%;height:100%;background:{color_barra};border-radius:3px;"></div>
  </div>
</div>"""

    st.markdown(filas_html, unsafe_allow_html=True)
