"""Módulo: Comparación de Cuotas — carga datos desde data/odds.csv"""

from pathlib import Path
import pandas as pd
import streamlit as st

RUTA_CUOTAS = Path(__file__).parent.parent / "data" / "odds.csv"

CASAS_APUESTAS = ["codere", "bet365", "betfair"]
NOMBRE_CASAS   = {"codere": "Codere", "bet365": "Bet365", "betfair": "Betfair"}
COLOR_CASAS    = {"codere": "#00e676", "bet365": "#4fc3f7", "betfair": "#f39c12"}


_COLS_CUOTAS = ["partido", "mercado", "resultado", "codere", "bet365", "betfair"]


@st.cache_data(ttl=30)
def cargar_cuotas() -> pd.DataFrame:
    """
    Carga odds.csv y lo devuelve como DataFrame.
    Si el archivo no existe o está vacío, devuelve un DataFrame vacío con las columnas correctas.
    """
    if not RUTA_CUOTAS.exists():
        return pd.DataFrame(columns=_COLS_CUOTAS)
    try:
        df = pd.read_csv(RUTA_CUOTAS)
        return df if not df.empty else pd.DataFrame(columns=_COLS_CUOTAS)
    except Exception:
        return pd.DataFrame(columns=_COLS_CUOTAS)


def _obtener_mercado_clave(mercado_sesion: str) -> str:
    """Mapea el nombre del mercado Claude al formato de columna en el CSV."""
    m = mercado_sesion.lower()
    if "ambos" in m:
        return "Ambos Marcan"
    if "1ª parte" in m or "primera parte" in m or "1t" in m:
        return "Resultado 1T"
    if "1.5" in m:
        return "Over/Under 1.5"
    if "2.5" in m:
        return "Over/Under 2.5"
    return "1X2"


def _detectar_valor(cuotas_fila: pd.Series, umbral: float = 1.75) -> bool:
    """Devuelve True si alguna cuota supera el umbral de valor."""
    for casa in CASAS_APUESTAS:
        if float(cuotas_fila.get(casa, 0)) >= umbral:
            return True
    return False


def mostrar():
    """Renderiza el módulo de Comparación de Cuotas con tabla CASA / 1 / X / 2 / MEJOR."""
    df_cuotas = cargar_cuotas()

    partido_activo = st.session_state.get("partido_activo", "")
    # Usa el mercado Claude activo; si aún no se ha analizado, muestra 1X2 base
    mercado_claude = st.session_state.get("claude_mercado_activo",
                     st.session_state.get("claude_mercado", ""))
    mercado_clave  = _obtener_mercado_clave(mercado_claude)

    filtro = (df_cuotas["partido"] == partido_activo) & (df_cuotas["mercado"] == mercado_clave)
    df_filtrado = df_cuotas[filtro].copy()

    if df_filtrado.empty:
        if df_cuotas.empty:
            st.warning(
                "⚠️ No hay cuotas cargadas. "
                "Pulsa **Actualizar partidos reales** en la barra lateral para obtener cuotas de The Odds API.",
                icon=None,
            )
            return
        df_filtrado = df_cuotas[df_cuotas["mercado"] == "1X2"].head(3).copy()
        mercado_clave = "1X2"
        if partido_activo:
            st.caption(f"Sin cuotas para '{partido_activo}' ({mercado_clave}). Mostrando datos disponibles.")

    # Construir mapa resultado → cuotas por casa
    # Filas: Local, Empate, Visitante  →  columnas encabezado: 1, X, 2
    etiquetas_col = {"Local": "1", "Empate": "X", "Visitante": "2"}
    resultados_orden = ["Local", "Empate", "Visitante"]

    # {resultado: {casa: cuota}}
    datos: dict[str, dict[str, float]] = {r: {} for r in resultados_orden}
    for _, fila in df_filtrado.iterrows():
        res = fila.get("resultado", "")
        if res in datos:
            for casa in CASAS_APUESTAS:
                datos[res][casa] = float(fila.get(casa, 0))

    # Mejor cuota por resultado (para resaltar en verde)
    mejor_por_resultado: dict[str, float] = {}
    for res, cuotas_res in datos.items():
        validos = [v for v in cuotas_res.values() if v > 1.0]
        mejor_por_resultado[res] = max(validos) if validos else 0.0

    # Mejor cuota global
    mejor_global = {"res": "", "casa": "", "valor": 0.0}
    for res, cuotas_res in datos.items():
        for casa, val in cuotas_res.items():
            if val > mejor_global["valor"]:
                mejor_global = {"res": res, "casa": NOMBRE_CASAS[casa], "valor": val}

    # ── Tarjetas de cuota grande: LOCAL / EMPATE / VISITANTE ──
    cols = st.columns(3)
    etiq_display = {"Local": "LOCAL", "Empate": "EMPATE", "Visitante": "VISITANTE"}
    col_labels    = {"Local": "1", "Empate": "X", "Visitante": "2"}
    for idx, res in enumerate(resultados_orden):
        mejor_val = mejor_por_resultado.get(res, 0.0)
        with cols[idx]:
            borde_color = "#00ff88" if mejor_val > 0 and res == mejor_global["res"] else "rgba(0,255,136,0.18)"
            st.markdown(
                f'<div class="cuota-card" style="border-color:{borde_color};">'
                f'<div class="cuota-card-label">{etiq_display[res]} ({col_labels[res]})</div>'
                f'<div class="cuota-card-value">'
                f'{"—" if mejor_val == 0 else f"{mejor_val:.2f}"}'
                f'</div>'
                f'<div class="cuota-card-sub">'
                f'{mejor_global["casa"] if res == mejor_global["res"] else " "}'
                f'</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── Tabla CASA / 1 / X / 2 / MEJOR ──
    filas_html = ""
    for casa in CASAS_APUESTAS:
        nombre_casa = NOMBRE_CASAS[casa]
        celdas = ""
        mejor_en_fila = 0.0
        mejor_res_fila = ""
        for res in resultados_orden:
            val = datos[res].get(casa, 0.0)
            es_mejor_col = (val > 0 and val == mejor_por_resultado.get(res, 0))
            cel_style = 'class="cuota-mejor"' if es_mejor_col else 'style="color:#8aaaa0;"'
            val_str   = f"{val:.2f}" if val > 0 else "—"
            celdas   += f"<td {cel_style}>{val_str}</td>"
            if val > mejor_en_fila:
                mejor_en_fila, mejor_res_fila = val, col_labels[res]

        mejor_html = (
            f'<span style="color:#00ff88;font-weight:800;">{mejor_en_fila:.2f}</span>'
            f'<span style="color:#4a7060;font-size:9px;"> @{mejor_res_fila}</span>'
            if mejor_en_fila > 0 else "—"
        )
        filas_html += (
            f"<tr><td style='color:#00ff88;font-weight:700;font-size:10px;"
            f"letter-spacing:0.5px;text-transform:uppercase;padding:4px 8px;'>"
            f"{nombre_casa}</td>{celdas}"
            f"<td style='padding:4px 8px;'>{mejor_html}</td></tr>"
        )

    hay_valor = mejor_global["valor"] >= 1.75
    badge = (
        f'<span style="color:#00ff88;font-size:10px;font-weight:700;">✦ VALOR DETECTADO</span>'
        if hay_valor else
        f'<span style="color:#4a7060;font-size:10px;">Sin valor claro</span>'
    )

    st.markdown(f"""
<table class="tabla-cuotas">
  <thead>
    <tr>
      <th style="text-align:left;">CASA</th>
      <th>1</th><th>X</th><th>2</th>
      <th style="color:#ffd700;">MEJOR</th>
    </tr>
  </thead>
  <tbody>{filas_html}</tbody>
</table>
<div style="margin-top:8px;display:flex;align-items:center;justify-content:space-between;">
  <span style="color:#4a7060;font-size:10px;">
    Mejor: <b style="color:#ffd700;">{mejor_global['casa']} — {mejor_global['res']} @ {mejor_global['valor']:.2f}</b>
  </span>
  {badge}
</div>
""", unsafe_allow_html=True)
