"""Módulo: Modelo Predictivo Poisson/xG — carga datos desde data/matches.csv"""

from pathlib import Path
import pandas as pd
import streamlit as st
from scipy.stats import poisson

from modules import etiquetas_mercado as em

RUTA_PARTIDOS = Path(__file__).parent.parent / "data" / "matches.csv"
MAXIMO_GOLES  = 10


_COLS_PARTIDOS = ["liga", "partido", "equipo_local", "equipo_visitante",
                  "xg_local", "xg_visitante", "fuente_xg"]


@st.cache_data(ttl=30)
def cargar_partidos() -> pd.DataFrame:
    """Carga matches.csv de forma segura. Devuelve DataFrame vacío si el archivo no existe o está vacío."""
    if not RUTA_PARTIDOS.exists():
        return pd.DataFrame(columns=_COLS_PARTIDOS)
    try:
        df = pd.read_csv(RUTA_PARTIDOS)
        return df if not df.empty else pd.DataFrame(columns=_COLS_PARTIDOS)
    except Exception:
        return pd.DataFrame(columns=_COLS_PARTIDOS)


def calcular_prediccion_completa(xg_local: float, xg_visitante: float) -> dict:
    """Genera predicciones completas usando modelo de Poisson para dos equipos."""
    matriz = {
        (gl, gv): poisson.pmf(gl, xg_local) * poisson.pmf(gv, xg_visitante)
        for gl in range(MAXIMO_GOLES)
        for gv in range(MAXIMO_GOLES)
    }

    prob_over25   = sum(p for (gl, gv), p in matriz.items() if gl + gv > 2)
    prob_over15   = sum(p for (gl, gv), p in matriz.items() if gl + gv > 1)
    prob_btts     = sum(p for (gl, gv), p in matriz.items() if gl > 0 and gv > 0)
    prob_local    = sum(p for (gl, gv), p in matriz.items() if gl > gv)
    prob_empate   = sum(p for (gl, gv), p in matriz.items() if gl == gv)
    prob_visit    = sum(p for (gl, gv), p in matriz.items() if gl < gv)

    # Resultado exacto más probable
    resultado_mas_probable = max(matriz, key=matriz.get)
    prob_resultado = matriz[resultado_mas_probable]

    return {
        "over25":            round(prob_over25 * 100, 1),
        "under25":           round((1 - prob_over25) * 100, 1),
        "over15":            round(prob_over15 * 100, 1),
        "under15":           round((1 - prob_over15) * 100, 1),
        "ambos_marcan":      round(prob_btts * 100, 1),
        "victoria_local":    round(prob_local * 100, 1),
        "empate":            round(prob_empate * 100, 1),
        "victoria_visitante":round(prob_visit * 100, 1),
        "resultado_exacto":  f"{resultado_mas_probable[0]}-{resultado_mas_probable[1]}",
        "prob_resultado":    round(prob_resultado * 100, 1),
    }


def _barra_prediccion(etiqueta: str, porcentaje: float, color: str) -> str:
    """Genera HTML de una barra de progreso con porcentaje."""
    ancho = max(5, min(int(porcentaje), 100))
    return f"""
<div class="fila-pred">
  <div class="pred-etiqueta">• {etiqueta}</div>
  <div class="barra-fondo">
    <div class="barra-relleno" style="width:{ancho}%;background:{color};">
      {porcentaje}%
    </div>
  </div>
</div>"""


def mostrar():
    """Renderiza el módulo completo del Modelo Predictivo."""
    df_partidos  = cargar_partidos()
    partido_activo = st.session_state.get("partido_activo", "Real Madrid vs Barcelona")

    filtro = df_partidos["partido"] == partido_activo
    if filtro.any():
        fila = df_partidos[filtro].iloc[0]
        xg_local, xg_visitante = float(fila["xg_local"]), float(fila["xg_visitante"])
    else:
        xg_local, xg_visitante = 2.1, 1.8

    pred = calcular_prediccion_completa(xg_local, xg_visitante)

    nombre_local = partido_activo.split(" vs ")[0].strip() if " vs " in partido_activo else "Local"
    nombre_visit = partido_activo.split(" vs ")[1].strip() if " vs " in partido_activo else "Visitante"

    label_exacto = f"{pred['resultado_exacto']} (más probable)"
    barras_html = (
        _barra_prediccion(f"{em.outcome_ou('Over 2.5')} — Total Goles",  pred["over25"],         "#00c853") +
        _barra_prediccion(f"{em.outcome_ou('Over 1.5')} — Total Goles",  pred["over15"],         "#00e5ff") +
        _barra_prediccion(em.titulo_mercado("Ambos Marcan"),             pred["ambos_marcan"],   "#6a1b9a") +
        _barra_prediccion(em.outcome_1x2("Local", nombre_local, nombre_visit),    pred["victoria_local"], "#e65100") +
        _barra_prediccion("Empate",                                      pred["empate"],         "#1565c0") +
        _barra_prediccion(label_exacto,              pred["prob_resultado"], "#78909c")
    )

    nota_valor = ""
    if pred["over25"] >= 60:
        nota_valor = f'<div class="texto-apagado" style="margin-top:10px;font-size:12px;">• Valor para {em.outcome_ou("Over 2.5")} si cuota ≥ 1.75</div>'
    elif pred["over15"] >= 75:
        nota_valor = f'<div class="texto-apagado" style="margin-top:10px;font-size:12px;">• Valor para {em.outcome_ou("Over 1.5")} si cuota ≥ 1.35</div>'

    st.markdown(
        f'<div style="font-size:11px;color:#aab;margin-bottom:10px;">• Pronóstico Poisson / xG</div>',
        unsafe_allow_html=True,
    )
    st.markdown(barras_html + nota_valor, unsafe_allow_html=True)

    # Simulador xG interactivo (xG = goles esperados)
    with st.expander("Simulador xG personalizado (goles esperados)"):
        col_i, col_d = st.columns(2)
        with col_i:
            xg_sim_local = st.slider(f"xG {nombre_local}", 0.5, 4.0, float(xg_local), 0.1, key="sim_local")
        with col_d:
            xg_sim_visit = st.slider(f"xG {nombre_visit}", 0.5, 4.0, float(xg_visitante), 0.1, key="sim_visit")

        pred_sim = calcular_prediccion_completa(xg_sim_local, xg_sim_visit)

        col1, col2, col3 = st.columns(3)
        col1.metric(em.outcome_1x2("Local", nombre_local, nombre_visit),     f"{pred_sim['victoria_local']}%")
        col2.metric("Empate",                                                f"{pred_sim['empate']}%")
        col3.metric(em.outcome_1x2("Visitante", nombre_local, nombre_visit), f"{pred_sim['victoria_visitante']}%")

        col4, col5, col6 = st.columns(3)
        col4.metric(em.outcome_ou("Over 2.5"),        f"{pred_sim['over25']}%")
        col5.metric(em.outcome_ou("Over 1.5"),        f"{pred_sim['over15']}%")
        col6.metric(em.titulo_mercado("Ambos Marcan"), f"{pred_sim['ambos_marcan']}%")

        st.caption(
            f"Resultado más probable: **{pred_sim['resultado_exacto']}** "
            f"({pred_sim['prob_resultado']}% de probabilidad)"
        )
