"""
JhonBet Lab — Aplicación principal de análisis de apuestas deportivas.

Esta app permite:
  - Analizar partidos con el modelo Poisson/xG
  - Comparar cuotas entre casas de apuestas
  - Obtener análisis de Claude AI
  - Detectar valor (edge) en el mercado
  - Registrar historial personal de apuestas

Para iniciar:  streamlit run app.py
"""

import json          # Para leer/escribir el archivo de configuración (config.json)
import os
import re
import sys
from datetime import date as _date_today
from pathlib import Path

os.makedirs(Path(__file__).parent / "data", exist_ok=True)

# Añade la carpeta raíz del proyecto al path de Python
# para que los imports como "from modules.analysis import ..." funcionen correctamente
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd   # Librería para manejar datos en tablas (DataFrames)
import streamlit as st  # Framework que convierte código Python en una app web

# ─── Rutas a los archivos de datos ────────────────────────────────────────────
# Usamos Path para que las rutas funcionen en Windows, Mac y Linux
_RUTA_CONFIG    = Path(__file__).parent / "data" / "config.json"   # Configuración del usuario
_RUTA_HISTORIAL = Path(__file__).parent / "data" / "history.csv"   # Historial de apuestas


def _cargar_config() -> dict:
    """
    Lee el archivo config.json y devuelve la configuración guardada.
    Si el archivo no existe o está corrupto, devuelve valores por defecto.
    """
    try:
        with open(_RUTA_CONFIG, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # Si hay cualquier error (archivo no existe, JSON inválido, etc.)
        # devolvemos valores seguros por defecto
        return {"saldo": 200.0}


def _guardar_saldo() -> None:
    """
    Guarda el saldo actual en config.json cuando el usuario lo modifica.
    Se llama automáticamente cuando cambia el campo 'Saldo (€)' del sidebar.
    """
    try:
        config = _cargar_config()
        # Leemos el valor del campo numérico del sidebar
        config["saldo"] = float(st.session_state.get("input_saldo", 200.0))
        with open(_RUTA_CONFIG, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        # Actualizamos también el estado de la sesión para que la UI se refresque
        st.session_state["saldo"] = config["saldo"]
    except Exception:
        pass  # Si falla el guardado, continuamos sin interrumpir la app


def _guardar_tema() -> None:
    """
    Guarda el tema visual seleccionado en config.json.
    Se llama cuando el usuario cambia el selector de tema en el sidebar.
    """
    try:
        config = _cargar_config()
        config["tema"] = st.session_state.get("sel_tema", "DeOP Claro")
        with open(_RUTA_CONFIG, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception:
        pass


_RUTA_PARTIDOS = Path(__file__).parent / "data" / "matches.csv"
_RUTA_CUOTAS   = Path(__file__).parent / "data" / "odds.csv"


def _limpiar_partidos_viejos() -> None:
    """
    Elimina de matches.csv y odds.csv todos los partidos anteriores a hoy.

    Reglas de borrado:
      1. Filas con columna 'fecha' y fecha < hoy  → BORRAR
      2. Filas sin 'fecha' y fuente_xg='estimado' → BORRAR  (datos de API sin sello de fecha)
      3. Filas sin 'fecha' y fuente_xg='manual'   → CONSERVAR (partido manual reciente)

    Imprime en terminal cuántas filas eliminó.
    """
    from datetime import datetime
    hoy_str = datetime.now().date().isoformat()   # p.ej. "2026-06-01"

    if not _RUTA_PARTIDOS.exists():
        print("[Limpieza] matches.csv no existe — sin acción")
        return

    try:
        df = pd.read_csv(_RUTA_PARTIDOS)
    except Exception as exc:
        print(f"[Limpieza] Error al leer matches.csv: {exc}")
        return

    if df.empty:
        print("[Limpieza] matches.csv vacío — sin acción")
        return

    n_original = len(df)
    tiene_fecha  = "fecha" in df.columns
    tiene_fuente = "fuente_xg" in df.columns

    mask_borrar = pd.Series(False, index=df.index)

    # Regla 1: filas con fecha < hoy
    if tiene_fecha:
        fechas = df["fecha"].fillna("").astype(str).str.strip()
        mask_borrar |= (fechas != "") & (fechas < hoy_str)

    # Regla 2: filas estimadas sin fecha (API data de días anteriores sin sello)
    if tiene_fuente:
        es_estimado = df["fuente_xg"].astype(str).str.strip() == "estimado"
        if tiene_fecha:
            sin_fecha = df["fecha"].isna() | (df["fecha"].astype(str).str.strip() == "")
            mask_borrar |= sin_fecha & es_estimado
        else:
            # No existe la columna 'fecha': borrar todos los estimados
            mask_borrar |= es_estimado

    n_borrar = int(mask_borrar.sum())

    if n_borrar == 0:
        print(f"[Limpieza] Sin partidos anteriores a {hoy_str} — matches.csv limpio")
        return

    partidos_borrar = set(df.loc[mask_borrar, "partido"].dropna().tolist())
    df[~mask_borrar].reset_index(drop=True).to_csv(_RUTA_PARTIDOS, index=False)
    print(
        f"[Limpieza] matches.csv: {n_borrar}/{n_original} partido(s) eliminados "
        f"(anteriores a {hoy_str}). Conservados: {n_original - n_borrar}"
    )

    # Eliminar de odds.csv las cuotas de esos mismos partidos
    if not _RUTA_CUOTAS.exists() or not partidos_borrar:
        return
    try:
        df_odds  = pd.read_csv(_RUTA_CUOTAS)
        n_odds   = len(df_odds)
        df_nuevo = df_odds[~df_odds["partido"].isin(partidos_borrar)]
        n_elim   = n_odds - len(df_nuevo)
        if n_elim > 0:
            df_nuevo.reset_index(drop=True).to_csv(_RUTA_CUOTAS, index=False)
            print(
                f"[Limpieza] odds.csv: {n_elim}/{n_odds} filas eliminadas "
                f"({len(partidos_borrar)} partido(s))"
            )
        else:
            print("[Limpieza] odds.csv: sin cuotas huérfanas que eliminar")
    except Exception as exc:
        print(f"[Limpieza] Error al limpiar odds.csv: {exc}")


def _stats_historial() -> dict:
    """
    Lee el historial de apuestas (history.csv) y calcula tres métricas:
      - apuestas_totales: número total de apuestas registradas
      - ganancias_netas:  suma de todas las ganancias/pérdidas en euros
      - racha:            número de victorias consecutivas más recientes

    La racha se calcula desde la apuesta más reciente hacia atrás:
    si las últimas 3 fueron Ganado, Ganado, Ganado → racha = 3.
    Si la más reciente fue Perdido → racha = 0.
    """
    try:
        df = pd.read_csv(_RUTA_HISTORIAL)
        # Convertimos la columna ganancia a número (por si hay texto o vacíos)
        df["ganancia"] = pd.to_numeric(df["ganancia"], errors="coerce").fillna(0)
    except Exception:
        # Si el archivo no existe o está vacío, devolvemos ceros
        return {"apuestas_totales": 0, "ganancias_netas": 0, "racha": 0}

    if df.empty:
        return {"apuestas_totales": 0, "ganancias_netas": 0, "racha": 0}

    total = len(df)                  # Contamos todas las filas del historial
    neto  = int(df["ganancia"].sum())  # Sumamos todas las ganancias (negativas = pérdidas)

    # Calculamos la racha: recorremos los resultados de más reciente a más antiguo
    racha = 0
    for res in df["resultado"].tolist():
        if res == "Ganado":
            racha += 1
        else:
            break  # En cuanto encontramos una derrota, la racha se rompe → paramos

    return {"apuestas_totales": total, "ganancias_netas": neto, "racha": racha}


def _sparkline_svg(valores: list, color: str = "#7c3aed",
                   ancho: int = 78, alto: int = 22) -> str:
    """Genera un SVG sparkline inline desde una lista de valores numéricos."""
    vals = [float(v) for v in valores if v is not None]
    if len(vals) < 2:
        mid = alto // 2
        return (
            f'<svg width="{ancho}" height="{alto}" xmlns="http://www.w3.org/2000/svg">'
            f'<line x1="0" y1="{mid}" x2="{ancho}" y2="{mid}" '
            f'stroke="{color}" stroke-width="1.5" opacity="0.35"/></svg>'
        )
    v_min, v_max = min(vals), max(vals)
    rango = v_max - v_min if v_max != v_min else 1.0
    n = len(vals)
    pts = " ".join(
        f"{round(i/(n-1)*ancho,1)},{round((1-(v-v_min)/rango)*(alto-4)+2,1)}"
        for i, v in enumerate(vals)
    )
    return (
        f'<svg width="{ancho}" height="{alto}" viewBox="0 0 {ancho} {alto}"'
        f' xmlns="http://www.w3.org/2000/svg">'
        f'<polyline points="{pts}" fill="none" stroke="{color}" '
        f'stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>'
        f'</svg>'
    )


def _barra_stats_top() -> None:
    """Renderiza la barra superior de 6 métricas con sparklines."""
    ganancias_serie: list = []
    total = ganadas = perdidas = 0
    neto = 0.0
    try:
        df_h = pd.read_csv(_RUTA_HISTORIAL)
        df_h["ganancia"] = pd.to_numeric(df_h["ganancia"], errors="coerce").fillna(0)
        total    = len(df_h)
        ganadas  = int((df_h["resultado"] == "Ganado").sum())
        perdidas = int((df_h["resultado"] == "Perdido").sum())
        neto     = float(df_h["ganancia"].sum())
        ganancias_serie = df_h["ganancia"].cumsum().tolist()
    except Exception:
        pass

    saldo     = float(st.session_state.get("saldo", 200.0))
    resueltas = ganadas + perdidas

    # ROI real: beneficio_total / stake_total_apostado × 100
    # Para bets Perdido: |ganancia| = stake; para Ganado: |ganancia| ≈ profit (mejor proxy disponible)
    try:
        df_resueltas = pd.read_csv(_RUTA_HISTORIAL)
        df_resueltas["ganancia"] = pd.to_numeric(df_resueltas["ganancia"], errors="coerce").fillna(0)
        mask_res = df_resueltas["resultado"].isin(["Ganado", "Perdido"])
        total_apostado = float(df_resueltas.loc[mask_res, "ganancia"].abs().sum())
    except Exception:
        total_apostado = 0.0

    sin_datos = resueltas < 3
    if sin_datos or total_apostado < 0.01:
        roi      = 0.0
        roi_disp = "Sin datos"
        roi_color = "var(--texto-apagado)"
    else:
        roi       = round(neto / total_apostado * 100, 1)
        roi_disp  = f"{'+'if roi>=0 else ''}{roi}%"
        roi_color = "#16a34a" if roi >= 0 else "#dc2626"

    yield_val  = round(neto / resueltas, 2) if resueltas > 0 else 0.0
    win_rate   = round(ganadas / total * 100, 1) if total > 0 else 0.0
    lose_rate  = round(100 - win_rate, 1) if total > 0 else 0.0

    serie_reciente = ganancias_serie[-20:] if ganancias_serie else [0, 0]
    serie_saldo    = [saldo * 0.88, saldo * 0.92, saldo * 0.96, saldo * 0.98, saldo]
    serie_total    = list(range(1, max(total + 1, 3)))

    yld_color = "#16a34a" if yield_val >= 0 else "#dc2626"
    sign      = lambda v: "+" if v >= 0 else ""

    metricas = [
        ("ROI (30 días)",    roi_disp,                         roi_color, _sparkline_svg(serie_reciente, roi_color)),
        ("Bankroll",         f"€{saldo:.2f}",                  "var(--acento-morado)",  _sparkline_svg(serie_saldo,  "var(--acento-azul)")),
        ("Yield",            f"{sign(yield_val)}{yield_val:.1f}%", yld_color, _sparkline_svg(serie_reciente[-10:] or [0,0], yld_color)),
        ("Apuestas Totales", str(total),                       "var(--acento-morado)",  _sparkline_svg(serie_total,  "var(--texto-apagado)")),
        ("Ganadas",          f"{ganadas} ({win_rate}%)",       "#16a34a",  _sparkline_svg([ganadas]*4 or [0,0], "#16a34a")),
        ("Perdidas",         f"{perdidas} ({lose_rate}%)",     "#dc2626",  _sparkline_svg([perdidas]*4 or [0,0], "#dc2626")),
    ]

    cols = st.columns(6)
    for col, (label, valor, color, spark) in zip(cols, metricas):
        col.markdown(
            f'<div class="stat-card-top">'
            f'<div class="stat-card-label">{label}</div>'
            f'<div class="stat-card-value" style="color:{color};">{valor}</div>'
            f'<div class="stat-card-chart">{spark}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )


# ─── Configuración global de la página ────────────────────────────────────────
# Esta llamada DEBE ser la primera de Streamlit en el script.
# Define el título de la pestaña del navegador, el icono y el layout.
st.set_page_config(
    page_title="JhonBet Lab",
    page_icon="📊",
    layout="wide",                      # Usa todo el ancho de la pantalla
    initial_sidebar_state="auto",        # Desktop: expandido · Mobile: colapsado
)

# ─────────────────────────────────────────────────────────────────────
#  ESTILOS GLOBALES — mínimos, sin imágenes ni posicionamiento absoluto
# ─────────────────────────────────────────────────────────────────────
ESTILOS_CSS = """
<style>
/* ── JhonBet Lab — DeOP Connect Theme ── */
:root {
    --bg:                #f4f6f8;
    --bg-tarjeta:        #ffffff;
    --borde:             #e2e8f0;
    --borde-activo:      #f5a623;
    --texto:             #1a2c38;
    --texto-apagado:     #5a7a9a;
    --acento-verde:      #16a34a;
    --acento-morado:     #0d3b4f;
    --acento-dorado:     #f5a623;
    --acento-dorado-rgb: 245,166,35;
    --acento-azul:       #2563eb;
    --acento-rojo:       #dc2626;
    --bg-elemento:       #f1f5f9;
    --bg-alerta-exito:   #eef6fb;
    --bg-alerta-peligro: #fdecec;
    --bg-alerta-aviso:   #fff7e6;
    --boton-bg:          linear-gradient(135deg, #0d3b4f, #14506b);
    --logo-color:        #0d3b4f;
    --bg-principal:      #f4f6f8;
    --bg-sidebar:        #0d3b4f;
}

/* ── Fondo principal ── */
html, body,
[data-testid="stAppViewContainer"],
[data-testid="stApp"] {
    background-color: #f4f6f8 !important;
    color: #1a2c38 !important;
    font-family: "Inter", "Segoe UI", system-ui, sans-serif !important;
}
[data-testid="stHeader"]     { background-color: #ffffff !important; }
[data-testid="stToolbar"]    { display: none; }
[data-testid="stDecoration"] { display: none; }

/* ── Sidebar — azul petróleo DeOP ── */
[data-testid="stSidebar"],
[data-testid="stSidebar"] > div {
    background-color: #0d3b4f !important;
    border-right: 1px solid #0a2f3f !important;
}

/* ── Botones globales — petróleo/dorado ── */
.stButton > button,
.stFormSubmitButton > button {
    background: linear-gradient(135deg, #0d3b4f, #14506b) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    font-size: 12px !important;
    transition: opacity 0.15s ease !important;
}
.stButton > button:hover,
.stFormSubmitButton > button:hover {
    opacity: 0.85 !important;
    color: #ffffff !important;
}

/* ── Nav buttons del sidebar — altura fija 36px para no saltar al cambiar página ── */
[data-testid="stSidebar"] .stButton {
    margin: 1px 0 !important;
    padding: 0 !important;
    line-height: 1 !important;
}
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    color: #aac4d4 !important;
    border: none !important;
    border-left: 2px solid transparent !important;
    border-radius: 0 6px 6px 0 !important;
    text-align: left !important;
    padding: 0 12px !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    letter-spacing: .2px !important;
    height: 36px !important;
    min-height: 36px !important;
    max-height: 36px !important;
    display: flex !important;
    align-items: center !important;
    width: 100% !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(var(--acento-dorado-rgb),0.14) !important;
    color: var(--acento-dorado) !important;
    border-left-color: var(--acento-dorado) !important;
}

/* ── Categorías del sidebar (estilo DeOP) ── */
.deop-categoria {
    font-size: 9px;
    font-weight: 800;
    color: #6f96aa;
    letter-spacing: 1.6px;
    text-transform: uppercase;
    padding: 10px 10px 4px;
    margin-top: 2px;
}

/* ── Tarjetas ── */
.tarjeta {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 8px;
    box-shadow: 0 1px 3px rgba(13,59,79,0.06);
}
.titulo-tarjeta {
    font-size: 9px;
    font-weight: 700;
    color: #0d3b4f;
    margin-bottom: 10px;
    padding-bottom: 7px;
    border-bottom: 2px solid #f5a623;
    text-transform: uppercase;
    letter-spacing: 1.4px;
}

/* ── Encabezado compacto ── */
.encabezado-principal {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 6px 14px;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.logo-texto   { font-size: 14px; font-weight: 800; color: var(--acento-morado); }
.logo-punto   { color: var(--acento-dorado); }
.info-saldo   { color: #16a34a; font-weight: 700; font-size: 12px; }
.info-usuario { font-size: 10px; color: var(--texto-apagado); }

/* ── Top stats bar ── */
.stat-card-top {
    background: var(--bg-tarjeta);
    border: 1px solid var(--borde);
    border-top: 2px solid var(--acento-dorado);
    border-radius: 8px;
    padding: 10px 12px 8px;
    position: relative;
}
.stat-card-label {
    font-size: 9px;
    color: var(--texto-apagado);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 3px;
}
.stat-card-value {
    font-size: 16px;
    font-weight: 800;
    line-height: 1.1;
    margin-bottom: 3px;
    color: var(--acento-morado);
}
.stat-card-chart { opacity: 0.85; line-height: 0; display: block; }

/* ── Probabilidades ── */
.fila-prob    { display: flex; align-items: center; gap: 6px; margin: 4px 0; font-size: 12px; }
.insignia     { border-radius: 4px; padding: 1px 7px; font-weight: 700; font-size: 11px; background: var(--bg-elemento); color: var(--texto); }
.prob-verde   { color: #16a34a; }
.prob-amarillo{ color: #b8780f; }
.prob-azul    { color: #2563eb; }
.prob-rojo    { color: #dc2626; }
.texto-apagado{ color: var(--texto-apagado); }
.texto-dorado { color: #b8780f; font-weight: 700; }
.texto-azul   { color: #2563eb; }
.texto-rojo   { color: #dc2626; }
.texto-valor  { color: #16a34a; font-weight: 700; }
.etiqueta-seccion { font-size: 10px; font-weight: 700; color: var(--acento-morado); margin-bottom: 6px; text-transform: uppercase; letter-spacing: .8px; }

/* ── Cuota cards ── */
.cuota-card       { background: var(--bg-elemento); border: 1px solid var(--borde); border-radius: 8px; padding: 8px 6px; text-align: center; }
.cuota-card-label { font-size: 10px; color: var(--texto-apagado); text-transform: uppercase; }
.cuota-card-value { font-size: 22px; font-weight: 800; color: var(--acento-morado); line-height: 1.1; }
.cuota-card-sub   { font-size: 10px; color: var(--texto-apagado); }

/* ── Tablas de cuotas ── */
.tabla-cuotas { width: 100%; border-collapse: collapse; font-size: 12px; }
.tabla-cuotas th { color: var(--acento-morado); font-weight: 700; padding: 5px 8px; border-bottom: 1px solid var(--borde); text-align: center; }
.tabla-cuotas th:first-child { text-align: left; }
.tabla-cuotas td { padding: 4px 8px; text-align: center; color: var(--texto); border-bottom: 1px solid var(--borde); }
.tabla-cuotas td:first-child { text-align: left; color: var(--texto-apagado); font-weight: 600; }
.tabla-cuotas tr:hover td { background: var(--bg-elemento); }
.cuota-mejor  { color: #16a34a !important; font-weight: 800; }
.col-resultado{ text-align: left !important; color: var(--texto-apagado); font-weight: 600; }

/* ── Barras predicción ── */
.fila-pred     { margin: 6px 0; }
.pred-etiqueta { font-size: 11px; color: var(--texto-apagado); margin-bottom: 3px; }
.barra-fondo   { background: var(--bg-elemento); border-radius: 4px; height: 20px; overflow: hidden; }
.barra-relleno { height: 100%; border-radius: 3px; display: flex; align-items: center; justify-content: flex-end; padding-right: 8px; font-size: 11px; font-weight: 700; color: #fff; }

/* ── Alertas ── */
.alerta-peligro  { background: var(--bg-alerta-peligro); border: 1px solid #dc2626; border-radius: 6px; padding: 6px 10px; margin: 4px 0; font-size: 12px; color: #b91c1c; }
.alerta-exito    { background: var(--bg-alerta-exito); border: 1px solid #2563eb; border-radius: 6px; padding: 6px 10px; margin: 4px 0; font-size: 12px; color: var(--texto); line-height: 1.65; }
.insignia-estado { display: inline-block; border-radius: 4px; border: 1px solid; padding: 2px 10px; font-size: 11px; font-weight: 700; }

/* ── Historial ── */
.tabla-historial { width: 100%; border-collapse: collapse; font-size: 12px; }
.tabla-historial th { color: var(--acento-morado); padding: 4px 6px; border-bottom: 1px solid var(--borde); text-align: left; }
.tabla-historial td { padding: 4px 6px; border-bottom: 1px solid var(--borde); color: var(--texto); }
.ganado       { color: #16a34a; font-weight: 700; }
.perdido      { color: #dc2626; font-weight: 700; }
.gan-positiva { color: #16a34a; font-weight: 700; }
.gan-negativa { color: #dc2626; font-weight: 700; }

/* ── Stat boxes (sidebar) ── */
.caja-stat    { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); border-radius: 6px; padding: 5px 8px; margin: 2px 0; }
.stat-etiqueta{ font-size: 10px; color: #aac4d4; text-transform: uppercase; }
.stat-valor   { font-size: 14px; font-weight: 700; color: #ffffff; }

/* ── Ocultar controles nativos (desktop) ── */
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapseButton"] button,
[data-testid="collapsedControl"] { display: none !important; }
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }

/* ════════════════════════════════════════════════════════════
   RESPONSIVE — breakpoint mobile 768px
   ════════════════════════════════════════════════════════════ */

/* ── Hamburguesa ☰: mostrar botón nativo de Streamlit en mobile ── */
@media (max-width: 767px) {

  /* Botón CERRAR (dentro del sidebar cuando está abierto) */
  [data-testid="stSidebarCollapseButton"] {
    display: flex !important;
  }
  [data-testid="stSidebarCollapseButton"] button {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    width: 40px !important;
    height: 40px !important;
    background: #0d3b4f !important;
    color: #f4f6f8 !important;
    border: none !important;
    border-radius: 8px !important;
    box-shadow: 0 2px 10px rgba(0,0,0,.45) !important;
    padding: 0 !important;
    cursor: pointer !important;
  }
  [data-testid="stSidebarCollapseButton"] button svg {
    fill: #f4f6f8 !important;
    width: 18px !important;
    height: 18px !important;
  }

  /* Botón ABRIR (fuera del sidebar cuando está cerrado) */
  [data-testid="collapsedControl"] {
    display: flex !important;
    position: fixed !important;
    top: 10px !important;
    left: 10px !important;
    z-index: 99999 !important;
    align-items: center !important;
    justify-content: center !important;
  }
  [data-testid="collapsedControl"] button {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    width: 40px !important;
    height: 40px !important;
    background: #0d3b4f !important;
    color: #f4f6f8 !important;
    border: none !important;
    border-radius: 8px !important;
    box-shadow: 0 2px 10px rgba(0,0,0,.45) !important;
    padding: 0 !important;
    cursor: pointer !important;
  }
  [data-testid="collapsedControl"] button svg {
    fill: #f4f6f8 !important;
    width: 18px !important;
    height: 18px !important;
  }

  /* Sidebar en mobile: overlay con sombra */
  section[data-testid="stSidebar"] {
    position: fixed !important;
    z-index: 9990 !important;
    height: 100dvh !important;
    box-shadow: 4px 0 24px rgba(0,0,0,.5) !important;
  }

  /* Espacio superior en área principal para no tapar el contenido */
  section.main .block-container { padding-top: 3.5rem !important; }
}

/* ── Stat cards: 6 → 2 por fila en mobile ── */
@media (max-width: 767px) {
  [data-testid="column"]:has(.stat-card-top) {
    min-width: calc(50% - 6px) !important;
    max-width: calc(50% - 6px) !important;
    flex: 0 0 calc(50% - 6px) !important;
  }
}

/* ── Gauges Plotly: 3 → 1 por fila en mobile ── */
@media (max-width: 767px) {
  [data-testid="column"]:has([data-testid="stPlotlyChart"]) {
    min-width: 100% !important;
    max-width: 100% !important;
    flex: none !important;
    margin-bottom: 6px !important;
  }
}

/* ── Tablas: scroll horizontal en mobile ── */
@media (max-width: 767px) {
  .tabla-historial,
  .tabla-cuotas {
    display: block !important;
    overflow-x: auto !important;
    -webkit-overflow-scrolling: touch !important;
  }
  .tabla-historial td, .tabla-historial th,
  .tabla-cuotas td,   .tabla-cuotas th {
    white-space: nowrap !important;
  }
}

/* ── .scada-grid (paneles live analysis): ya usa auto-fit minmax(260px,1fr)
      → apila solo en <560px sin CSS extra necesario.               ── */
</style>
"""

st.markdown(ESTILOS_CSS, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────
#  TEMAS VISUALES — estilo DeOP Connect (claro / oscuro)
# ─────────────────────────────────────────────────────────────────────
NOMBRES_TEMAS = ["DeOP Claro", "DeOP Oscuro", "Codere"]

_TEMAS_CSS: dict[str, str] = {
    "DeOP Claro": """
<style>
/* DeOP Claro — blanco + azul petróleo + dorado (default) */
:root {
    --bg-principal:      #f4f6f8;
    --bg-tarjeta:        #ffffff;
    --borde:             #e2e8f0;
    --borde-activo:      #f5a623;
    --texto:             #1a2c38;
    --texto-apagado:     #5a7a9a;
    --acento-verde:      #16a34a;
    --acento-morado:     #0d3b4f;
    --acento-dorado:     #f5a623;
    --acento-dorado-rgb: 245,166,35;
    --acento-azul:       #2563eb;
    --acento-rojo:       #dc2626;
    --bg-elemento:       #f1f5f9;
    --bg-alerta-exito:   #eef6fb;
    --bg-alerta-peligro: #fdecec;
    --bg-alerta-aviso:   #fff7e6;
    --boton-bg:          linear-gradient(135deg, #0d3b4f, #14506b);
    --logo-color:        #0d3b4f;
}
html, body,
[data-testid="stApp"],
[data-testid="stAppViewContainer"] { background-color: #f4f6f8 !important; color: #1a2c38 !important; }
[data-testid="stHeader"]           { background-color: #ffffff !important; }
[data-testid="stSidebar"]          { background-color: #0d3b4f !important; }
[data-testid="metric-container"] { background-color: #ffffff !important; border: 1px solid #e2e8f0 !important; }
</style>""",

    "DeOP Oscuro": """
<style>
/* DeOP Oscuro — mismo layout, superficies oscuras */
:root {
    --bg-principal:      #0c1820;
    --bg-tarjeta:        #122430;
    --borde:             #1d3a47;
    --borde-activo:      #f5a623;
    --texto:             #e6eef2;
    --texto-apagado:     #7fa0b3;
    --acento-verde:      #22c55e;
    --acento-morado:     #4fc3f7;
    --acento-dorado:     #f5a623;
    --acento-dorado-rgb: 245,166,35;
    --acento-azul:       #4fc3f7;
    --acento-rojo:       #ef4444;
    --bg-elemento:       #18303c;
    --bg-alerta-exito:   #0d2230;
    --bg-alerta-peligro: #2a1414;
    --bg-alerta-aviso:   #2a2410;
    --boton-bg:          linear-gradient(135deg, #0d3b4f, #14506b);
    --logo-color:        #f5a623;
}
html, body,
[data-testid="stApp"],
[data-testid="stAppViewContainer"] { background-color: #0c1820 !important; color: #e6eef2 !important; }
[data-testid="stHeader"]           { background-color: #0c1820 !important; }
[data-testid="stSidebar"]          { background-color: #081117 !important; }
.tarjeta { background-color: #122430 !important; border-color: #1d3a47 !important; color: #e6eef2 !important; }
.titulo-tarjeta { color: #f5a623 !important; }
[data-testid="metric-container"] { background-color: #122430 !important; border: 1px solid #1d3a47 !important; }
</style>""",

    "Codere": """
<style>
/* Codere — negro/gris oscuro + verde Codere */
:root {
    --bg-principal:      #12121e;
    --bg-tarjeta:        #1e1e30;
    --borde:             #2a2a3e;
    --borde-activo:      #00e676;
    --texto:             #ffffff;
    --texto-apagado:     #b0b8d0;
    --acento-verde:      #00e676;
    --acento-morado:     #ffffff;
    --acento-dorado:     #00e676;
    --acento-dorado-rgb: 0,230,118;
    --acento-azul:       #00e676;
    --acento-rojo:       #ef4444;
    --bg-elemento:       #252538;
    --bg-alerta-exito:   #0d2818;
    --bg-alerta-peligro: #2a1414;
    --bg-alerta-aviso:   #16241a;
    --boton-bg:          #00e676;
    --logo-color:        #00e676;
}
html, body,
[data-testid="stApp"],
[data-testid="stAppViewContainer"] { background-color: #12121e !important; color: #ffffff !important; }
[data-testid="stHeader"]           { background-color: #12121e !important; }
[data-testid="stSidebar"]          { background-color: #0d0d1a !important; }
.tarjeta {
    background-color: #1e1e30 !important;
    border-color: #2a2a3e !important;
    color: #ffffff !important;
}
.titulo-tarjeta {
    background: #252538 !important;
    color: #00e676 !important;
    border-bottom: 2px solid #00e676 !important;
    margin: -14px -16px 10px -16px !important;
    padding: 8px 16px 7px !important;
    border-radius: 10px 10px 0 0 !important;
}
[data-testid="metric-container"] { background-color: #1e1e30 !important; border: 1px solid #2a2a3e !important; }

/* Botones principales — verde Codere, texto negro (los del sidebar
   conservan su propio estilo transparente por mayor especificidad) */
.stButton > button,
.stFormSubmitButton > button {
    background: #00e676 !important;
    color: #000000 !important;
}
.stButton > button:hover,
.stFormSubmitButton > button:hover {
    background: #00c853 !important;
    opacity: 1 !important;
    color: #000000 !important;
}
[data-testid="stSidebar"] .stButton > button { color: #b0b8d0 !important; }

/* Categorías del sidebar */
.deop-categoria { color: #00e676 !important; }

/* Stat boxes (sidebar) */
.caja-stat  { background: rgba(0,230,118,0.06) !important; border-color: rgba(0,230,118,0.18) !important; }
.stat-valor { color: #ffffff !important; }
</style>""",
}


def _css_tema_activo() -> str:
    """
    Devuelve el bloque CSS del tema actualmente seleccionado.
    Lee primero de session_state; si no existe aún (primera carga),
    lee directamente de config.json para aplicar el tema guardado.
    """
    if "tema_activo" in st.session_state:
        tema = st.session_state["tema_activo"]
    else:
        # Primera carga: leer directamente del config para no esperar a _DEFAULTS
        tema = _cargar_config().get("tema", "DeOP Claro")
        if tema not in NOMBRES_TEMAS:
            # Tema de una versión anterior al rediseño DeOP (ya no existe) → default
            tema = "DeOP Claro"
        st.session_state["tema_activo"] = tema   # pre-inicializar para el resto del render
    return _TEMAS_CSS.get(tema, _TEMAS_CSS["DeOP Claro"])


# Inyectar CSS del tema ANTES de cualquier otro contenido (máxima prioridad)
st.markdown(_css_tema_activo(), unsafe_allow_html=True)

# JS mobile: cerrar sidebar al pulsar fuera (solo mobile, una vez por sesión)
st.markdown(
    '<img src="x" style="display:none;position:absolute;width:0;height:0;" onerror="'
    "(function(){"
    "if(window._jbl_mo)return;window._jbl_mo=1;"
    "document.addEventListener('click',function(ev){"
    "if(window.innerWidth>=768)return;"
    "var sb=document.querySelector('[data-testid=&quot;stSidebar&quot;]');"
    "if(!sb)return;"
    "var r=sb.getBoundingClientRect();if(r.width<10)return;"
    "if(sb.contains(ev.target))return;"
    "var ec=document.querySelector('[data-testid=&quot;collapsedControl&quot;]');"
    "if(ec&&ec.contains(ev.target))return;"
    "var cb=document.querySelector('[data-testid=&quot;stSidebarCollapseButton&quot;] button');"
    "if(cb)cb.click();"
    "},true);"
    "})();"
    '">',
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────────────────────────────
#  ESTADO DE SESIÓN — valores por defecto
# ─────────────────────────────────────────────────────────────────────
# st.session_state es como la "memoria" de la app entre interacciones.
# Streamlit recarga el script completo en cada clic, y session_state
# permite recordar qué página está activa, qué partido se analiza, etc.

_config_inicial = _cargar_config()   # Leemos configuración guardada en disco

# Tema guardado en config.json de una versión anterior (p.ej. "Azul Profesional")
# ya no es válido tras el rediseño DeOP — si no coincide con NOMBRES_TEMAS, usar default.
_tema_guardado = _config_inicial.get("tema", "DeOP Claro")
if _tema_guardado not in NOMBRES_TEMAS:
    _tema_guardado = "DeOP Claro"

# Definimos los valores por defecto de todas las variables de sesión
_DEFAULTS = {
    "pagina_activa":  "Análisis de Partidos",
    "saldo":          _config_inicial.get("saldo", 200.0),
    "tema_activo":    _tema_guardado,
    "analisis_listo":    False,
    "partido_activo":    "",
    "liga_activa":       "",
    "modo_observacion":  True,
}

# Solo inicializamos cada variable si NO existe aún en session_state
# Esto evita resetear valores cuando el usuario interactúa con la app
for clave, valor in _DEFAULTS.items():
    if clave not in st.session_state:
        st.session_state[clave] = valor

# ── Limpieza automática de partidos anteriores a hoy (una vez por día) ────────
_HOY_LIMPIEZA = __import__("datetime").datetime.now().date().isoformat()
if st.session_state.get("_limpieza_fecha") != _HOY_LIMPIEZA:
    _limpiar_partidos_viejos()
    st.session_state["_limpieza_fecha"] = _HOY_LIMPIEZA

# ─────────────────────────────────────────────────────────────────────
#  BARRA LATERAL — navegación y controles globales
# ─────────────────────────────────────────────────────────────────────
# Lista de páginas: cada elemento es (emoji, nombre).
# El nombre es la clave que se guarda en session_state["pagina_activa"].
# Páginas agrupadas en categorías visuales estilo DeOP Connect.
# Ninguna página existente se elimina — solo se reagrupan con subtítulos.
PAGINAS_CATEGORIAS: dict[str, list[tuple[str, str]]] = {
    "ANÁLISIS": [
        ("🏠", "Análisis de Partidos"),        # Dashboard principal rediseñado (DeOP)
        ("➕", "Agregar Partido"),             # Formulario para añadir partido manual
        ("🤖", "Claude AI"),                   # Análisis detallado por mercado (texto completo)
        ("📊", "Comparación de Cuotas"),       # Tabla de cuotas por casa de apuestas
        ("📈", "Modelo Predictivo"),           # Simulador xG con gráficos Plotly
        ("⚡", "Análisis en Vivo"),            # Estadísticas en tiempo real desde Codere
    ],
    "GESTIÓN": [
        ("🔥", "Apuesta Dominada"),            # Detección automática de dominancia extrema
        ("📁", "Historial Dominada"),          # Historial de análisis de Apuesta Dominada
        ("📋", "Historial Análisis Claude"),   # Historial de análisis generados por Claude
    ],
    "ALERTAS": [
        ("🔔", "Alertas y Retiradas"),         # Historial y alertas de bankroll
    ],
}

# Lista plana (mismo orden) — usada para el indicador de página activa.
PAGINAS = [pag for grupo in PAGINAS_CATEGORIAS.values() for pag in grupo]

NOMBRE_USUARIO = "Jhon"   # Nombre mostrado en el encabezado

with st.sidebar:
    # Header del sidebar — DeOP Connect
    logo_path = Path(__file__).parent / "assets" / "logo.png"
    if logo_path.exists():
        st.image(str(logo_path), width=140)
    else:
        st.markdown(
            '<div style="padding:6px 0 12px 0;">'
            '<div style="font-size:9px;font-weight:700;color:var(--acento-dorado);letter-spacing:2.5px;'
            'text-transform:uppercase;margin-bottom:5px;opacity:.9;">Trading Dashboard</div>'
            '<div style="font-size:17px;font-weight:800;line-height:1.1;">'
            '<span style="color:#ffffff;">📊 JhonBet</span>'
            '<span style="color:var(--acento-dorado);"> Lab</span>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    # Indicador de página activa (línea de color)
    _pagina_nav = st.session_state.get("pagina_activa", "Análisis de Partidos")
    _nav_label  = next((f"{i} {n}" for i, n in PAGINAS if n == _pagina_nav), "")
    if _nav_label:
        st.markdown(
            f'<div style="font-size:9px;color:var(--acento-dorado);'
            f'background:rgba(var(--acento-dorado-rgb),.14);'
            f'border-left:2px solid var(--acento-dorado);border-radius:0 4px 4px 0;'
            f'padding:3px 8px;margin-bottom:6px;letter-spacing:.3px;">'
            f'{_nav_label}</div>',
            unsafe_allow_html=True,
        )

    # ── Menú de navegación — todos st.button (mismo DOM, sin salto al cambiar página) ──
    # La key usa solo ASCII para que Streamlit genere una clase CSS predecible:
    # key="nav_analisis_de_partidos" → clase "st-key-nav_analisis_de_partidos"
    # Inyectamos un bloque <style> que pinta el botón activo en dorado sin
    # alterar la estructura DOM (misma altura, mismo margin, mismo wrapper).
    def _nav_key(nombre: str) -> str:
        return "nav_" + re.sub(r"[^a-z0-9]", "_", nombre.lower())

    _clase_activa = _nav_key(_pagina_nav)
    st.markdown(
        f"<style>"
        f".st-key-{_clase_activa} button {{"
        f"  background:rgba(245,166,35,.15) !important;"
        f"  color:#f5a623 !important;"
        f"  border-left-color:#f5a623 !important;"
        f"  font-weight:700 !important;"
        f"}}"
        f"</style>",
        unsafe_allow_html=True,
    )

    for _categoria, _paginas_grupo in PAGINAS_CATEGORIAS.items():
        st.markdown(f'<div class="deop-categoria">{_categoria}</div>', unsafe_allow_html=True)
        for icono, nombre_pagina in _paginas_grupo:
            if st.button(f"{icono}  {nombre_pagina}", key=_nav_key(nombre_pagina),
                         use_container_width=True, type="secondary"):
                st.session_state.pagina_activa = nombre_pagina
                st.rerun()

    st.markdown("<hr style='border-color:var(--borde);margin:6px 0'>", unsafe_allow_html=True)

    # ── Estadísticas personales — 3 columnas con st.columns ──
    _stats   = _stats_historial()
    _gan     = _stats["ganancias_netas"]
    _col_gan = "#1a5c2a" if _gan >= 0 else "#c0001a"
    _gan_txt = f"{'+'if _gan>=0 else ''}€{_gan}"
    _racha_txt = f"{_stats['racha']}W" if _stats["racha"] > 0 else "—"

    _c1, _c2, _c3 = st.columns(3)
    with _c1:
        st.markdown(
            f'<div class="caja-stat"><div class="stat-etiqueta">Apuestas</div>'
            f'<div class="stat-valor" style="color:#d0ead8;">{_stats["apuestas_totales"]}</div></div>',
            unsafe_allow_html=True,
        )
    with _c2:
        st.markdown(
            f'<div class="caja-stat"><div class="stat-etiqueta">Neto</div>'
            f'<div class="stat-valor" style="color:{_col_gan};">{_gan_txt}</div></div>',
            unsafe_allow_html=True,
        )
    with _c3:
        st.markdown(
            f'<div class="caja-stat"><div class="stat-etiqueta">Racha</div>'
            f'<div class="stat-valor" style="color:#00aaff;">{_racha_txt}</div></div>',
            unsafe_allow_html=True,
        )

    # Editor de saldo compacto
    st.number_input(
        "Saldo (€):",
        min_value=0.0, max_value=999999.0,
        value=float(st.session_state["saldo"]),
        step=10.0, key="input_saldo",
        on_change=_guardar_saldo,
    )

    st.markdown("<hr style='border-color:var(--borde);margin:6px 0'>", unsafe_allow_html=True)

    # ── Actualizar partidos reales ──
    if st.button("Actualizar partidos reales", key="btn_actualizar",
                 use_container_width=True, type="secondary"):
        from modules.odds_api import actualizar_datos
        from datetime import datetime as _dt
        with st.spinner("Conectando..."):
            try:
                n, mensaje, stats = actualizar_datos()
                st.cache_data.clear()
                st.session_state["debug_ligas"]   = stats
                st.session_state["debug_mensaje"] = (mensaje, "ok" if n > 0 else "info")
                st.session_state["debug_timestamp"] = _dt.now().strftime("%d/%m/%Y %H:%M:%S")
                st.session_state["debug_total"]    = n
                if n > 0:
                    st.session_state["analisis_listo"] = False
                    st.session_state.pop("claude_analisis", None)
            except RuntimeError as exc:
                st.session_state["debug_mensaje"]  = (str(exc), "error")
                st.session_state.pop("debug_ligas", None)

    # ── Mensaje de resultado ──
    if _dmsg := st.session_state.get("debug_mensaje"):
        _txt, _tipo = _dmsg
        _col = "#1a5c2a" if _tipo == "ok" else ("#c0001a" if _tipo == "error" else "#555555")
        with st.container():
            st.markdown(
                f'<div style="font-size:11px;color:{_col};padding:3px 4px;'
                f'margin:2px 0;border-left:3px solid {_col};padding-left:7px;">'
                f'{_txt}</div>',
                unsafe_allow_html=True,
            )

    # ── Panel de debug colapsable ──────────────────────────────────────────────
    _debug       = st.session_state.get("debug_ligas", [])
    _debug_ts    = st.session_state.get("debug_timestamp", "—")
    _debug_total = st.session_state.get("debug_total", 0)
    _debug_ok    = [r for r in _debug if r["estado"] == "OK"]
    _debug_fail  = [r for r in _debug if r["estado"] != "OK"]

    if _debug:
        with st.expander(
            f"🔧 Debug API · {len(_debug_ok)} liga(s) OK · {_debug_total} partidos",
            expanded=False,
        ):
            st.markdown(
                f'<div style="font-size:10px;color:#888;margin-bottom:6px;">'
                f'Última actualización: <b>{_debug_ts}</b></div>',
                unsafe_allow_html=True,
            )
            # Fuentes de datos y sus resultados
            filas_debug = []
            for row in _debug:
                if row["estado"] == "OK":
                    _ic, _c = "✅", "#1a5c2a"
                    _d = f"{row['partidos']} partidos · xG: estimado desde cuotas"
                else:
                    _ic, _c = "○", "#888888"
                    _d = row["estado"]
                filas_debug.append(
                    f'<div style="font-size:10px;color:{_c};padding:2px 0;">'
                    f'{_ic} <b>{row["liga"]}</b> — {_d}</div>'
                )
            # Añadir ESPN si está en session_state
            _espn_n = st.session_state.get("espn_partidos_cargados", 0)
            if _espn_n:
                filas_debug.append(
                    f'<div style="font-size:10px;color:#4499ff;padding:2px 0;">'
                    f'✅ <b>ESPN</b> — {_espn_n} partidos · xG: valor por defecto</div>'
                )
            # Fuente xG del partido activo
            _fuente_xg_act = st.session_state.get("fuente_xg_activa")
            if _fuente_xg_act:
                _badge_map = {
                    "estimado": "📊 xG: Estimado desde cuotas",
                    "manual":   "✏️ xG: Manual (BeSoccer)",
                    "api":      "📡 xG: API Real",
                }
                filas_debug.append(
                    f'<div style="font-size:10px;color:#ffd700;padding:4px 0 0;">'
                    f'Partido activo → {_badge_map.get(_fuente_xg_act, _fuente_xg_act)}</div>'
                )
            st.markdown("".join(filas_debug), unsafe_allow_html=True)

    # ── Escáner de valor ──
    if st.button("🔍 Escanear valor hoy", key="btn_scan_valor",
                 use_container_width=True, type="secondary"):
        st.session_state["pagina_activa"] = "Escáner de Valor"
        st.session_state["scan_trigger"]  = True
        st.rerun()

    st.markdown("<hr style='border-color:var(--borde);margin:6px 0'>", unsafe_allow_html=True)

    # ── Fuentes de datos ──
    with st.expander("⚙️ Fuentes de datos", expanded=False):
        st.markdown(
            '<div style="font-size:10px;color:#8aaa99;margin-bottom:6px;">'
            'Activa o desactiva cada fuente. Los cambios aplican al escanear y actualizar.</div>',
            unsafe_allow_html=True,
        )
        # Valores por defecto
        for k, v in [("fuente_odds", True), ("fuente_espn", True), ("fuente_logos", True)]:
            if k not in st.session_state:
                st.session_state[k] = v

        st.checkbox("📡 The Odds API (cuotas)",    key="fuente_odds",
                    help="Obtiene partidos y cuotas reales para calcular edge")
        st.checkbox("🏟️ ESPN (partidos adicionales)", key="fuente_espn",
                    help="Añade partidos de ESPN a la lista (sin cuotas)")
        st.checkbox("🖼️ TheSportsDB (logos)",       key="fuente_logos",
                    help="Muestra logos de equipos junto a los nombres")

        # Botón ESPN separado
        if st.session_state.get("fuente_espn", True):
            if st.button("Cargar partidos ESPN", key="btn_espn",
                         use_container_width=True):
                from modules.espn_api import actualizar_con_espn
                with st.spinner("Cargando partidos de ESPN..."):
                    n, msg = actualizar_con_espn()
                if n > 0:
                    st.session_state["espn_partidos_cargados"] = n
                st.success(msg) if n > 0 else st.info(msg)

    st.markdown("<hr style='border-color:var(--borde);margin:6px 0'>", unsafe_allow_html=True)

    # ── Modo Observación ──
    st.markdown("<hr style='border-color:var(--borde);margin:6px 0'>", unsafe_allow_html=True)
    st.toggle(
        "🔬 Modo Observación",
        key="modo_observacion",
        help="Sin dinero real — registra análisis como apuestas virtuales para seguimiento",
    )
    if st.session_state.get("modo_observacion"):
        st.markdown(
            '<div style="font-size:10px;color:#00e676;background:#021209;'
            'border:1px solid #00e676;border-radius:4px;padding:4px 8px;margin-top:4px;">'
            '🔬 Modo activo — sin riesgo real</div>',
            unsafe_allow_html=True,
        )

    # ── Selector de tema ──
    st.markdown(
        '<div style="font-size:10px;color:var(--texto-apagado);font-weight:700;'
        'text-transform:uppercase;letter-spacing:1px;margin-bottom:3px;">Tema Visual</div>',
        unsafe_allow_html=True,
    )

    def _cambiar_tema():
        st.session_state["tema_activo"] = st.session_state["sel_tema"]
        _guardar_tema()
        # No se llama st.rerun() aquí porque Streamlit ya hace rerun al cambiar el widget;
        # el CSS se inyecta al inicio del siguiente render con el nuevo tema.

    idx_actual = NOMBRES_TEMAS.index(st.session_state.get("tema_activo", "DeOP Claro"))
    st.selectbox(
        "Tema:",
        NOMBRES_TEMAS,
        index=idx_actual,
        key="sel_tema",
        label_visibility="collapsed",
        on_change=_cambiar_tema,
    )

# ─────────────────────────────────────────────────────────────────────
#  HEADER — estilo DeOP Connect (logo izq. + iconos der.)
# ─────────────────────────────────────────────────────────────────────
_modo_icono = "☀️" if st.session_state.get("tema_activo") == "DeOP Claro" else "🌙"
st.markdown(
    f'<div style="background:var(--bg-tarjeta);border:1px solid var(--borde);border-radius:8px;'
    f'padding:10px 18px;margin-bottom:10px;display:flex;align-items:center;'
    f'justify-content:space-between;">'
    f'<div style="font-size:17px;font-weight:800;color:var(--acento-morado);letter-spacing:.2px;">'
    f'📊 JhonBet <span style="color:var(--acento-dorado);">Lab</span></div>'
    f'<div style="display:flex;align-items:center;gap:16px;font-size:13px;color:var(--texto-apagado);">'
    f'<span title="Estado de conexión">🟢 Conectado</span>'
    f'<span title="Ayuda">❓</span>'
    f'<span title="Idioma">🌐 ES</span>'
    f'<span title="Modo oscuro / claro">{_modo_icono}</span>'
    f'<span title="Salir" style="color:#dc2626;">⏻</span>'
    f'</div></div>',
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────
#  BARRA SUPERIOR — 6 métricas con sparklines
# ─────────────────────────────────────────────────────────────────────
_barra_stats_top()

# ── Banner Modo Observación ──────────────────────────────────────────────────
if st.session_state.get("modo_observacion"):
    st.markdown(
        '<div style="background:var(--bg-alerta-aviso);border:1px solid var(--acento-dorado);border-radius:8px;'
        'padding:7px 14px;margin-bottom:8px;display:flex;align-items:center;gap:10px;">'
        '<span style="font-size:14px;">🔬</span>'
        '<span style="color:var(--acento-dorado);font-weight:700;font-size:12px;letter-spacing:.5px;">'
        'MODO OBSERVACIÓN ACTIVO — Registrando apuestas virtuales sin dinero real</span>'
        '</div>',
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────
#  ENRUTAMIENTO DE PÁGINAS
# ─────────────────────────────────────────────────────────────────────
pagina = st.session_state["pagina_activa"]

# Importaciones diferidas para evitar cargas innecesarias
if pagina == "Análisis de Partidos":
    from modules.match_dashboard import mostrar as mostrar_dashboard
    mostrar_dashboard()

elif pagina == "Agregar Partido":
    from modules.add_partido import mostrar as mostrar_agregar
    mostrar_agregar()

elif pagina == "Claude AI":
    from modules.claude_analysis import mostrar as mostrar_claude
    st.markdown('<div class="tarjeta">', unsafe_allow_html=True)
    st.markdown('<div class="titulo-tarjeta">🤖 Análisis con Claude AI</div>', unsafe_allow_html=True)
    mostrar_claude()
    st.markdown('</div>', unsafe_allow_html=True)

elif pagina == "Comparación de Cuotas":
    from modules.odds_comparison import mostrar as mostrar_cuotas
    st.markdown('<div class="tarjeta">', unsafe_allow_html=True)
    st.markdown('<div class="titulo-tarjeta">Comparación de Cuotas</div>', unsafe_allow_html=True)
    mostrar_cuotas()
    st.markdown('</div>', unsafe_allow_html=True)

elif pagina == "Modelo Predictivo":
    from modules.predictive_model import mostrar as mostrar_modelo
    col_izq, col_der = st.columns([1, 1])
    with col_izq:
        st.markdown('<div class="tarjeta">', unsafe_allow_html=True)
        st.markdown('<div class="titulo-tarjeta">Modelo Predictivo</div>', unsafe_allow_html=True)
        mostrar_modelo()
        st.markdown('</div>', unsafe_allow_html=True)

elif pagina == "Alertas y Retiradas":
    from modules.alerts import mostrar as mostrar_alertas
    st.markdown('<div class="tarjeta">', unsafe_allow_html=True)
    st.markdown('<div class="titulo-tarjeta">Alertas y Retiradas</div>', unsafe_allow_html=True)
    mostrar_alertas()
    st.markdown('</div>', unsafe_allow_html=True)

elif pagina == "Escáner de Valor":
    from modules.value_scanner import escanear_valor, mostrar_resultados
    import pandas as _pd_scan
    st.markdown('<div class="tarjeta">', unsafe_allow_html=True)
    st.markdown('<div class="titulo-tarjeta">🔍 Escáner de Valor — Hoy</div>', unsafe_allow_html=True)

    # Verificar si matches.csv tiene datos antes de escanear
    _matches_vacio = True
    try:
        _df_check = _pd_scan.read_csv(Path(__file__).parent / "data" / "matches.csv")
        _matches_vacio = _df_check.empty
    except Exception:
        _matches_vacio = True

    if _matches_vacio:
        st.markdown(
            '<div style="color:#ffd700;font-size:12px;padding:10px 0;">'
            '⚠️ No hay partidos cargados.<br>'
            'Pulsa <b>Actualizar partidos reales</b> en el menú lateral primero '
            'para cargar los partidos de hoy desde The Odds API.</div>',
            unsafe_allow_html=True,
        )
    else:
        if st.session_state.pop("scan_trigger", False):
            with st.spinner("Escaneando partidos… puede tardar unos segundos."):
                st.session_state["scan_resultados"] = escanear_valor()

        if "scan_resultados" in st.session_state:
            mostrar_resultados(st.session_state["scan_resultados"])
            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
            if st.button("🔄 Volver a escanear", key="btn_rescan", use_container_width=False):
                with st.spinner("Escaneando…"):
                    st.session_state["scan_resultados"] = escanear_valor()
                st.rerun()
        else:
            st.caption("Pulsa '🔍 Escanear valor hoy' en el menú lateral para iniciar el análisis.")

    st.markdown('</div>', unsafe_allow_html=True)

elif pagina == "Análisis en Vivo":
    from modules.live_analysis import mostrar as mostrar_vivo
    st.markdown('<div class="tarjeta">', unsafe_allow_html=True)
    st.markdown('<div class="titulo-tarjeta">⚡ Análisis en Vivo — Estadísticas Codere</div>',
                unsafe_allow_html=True)
    mostrar_vivo()
    st.markdown('</div>', unsafe_allow_html=True)

elif pagina == "Historial Análisis Claude":
    from modules.claude_history import mostrar as mostrar_historial_claude
    st.markdown('<div class="tarjeta">', unsafe_allow_html=True)
    st.markdown('<div class="titulo-tarjeta">📋 Historial Análisis Claude</div>',
                unsafe_allow_html=True)
    mostrar_historial_claude()
    st.markdown('</div>', unsafe_allow_html=True)

elif pagina == "Apuesta Dominada":
    from modules.dominant_bet import mostrar as mostrar_dominante
    st.markdown('<div class="tarjeta">', unsafe_allow_html=True)
    st.markdown('<div class="titulo-tarjeta">🔥 Apuesta Dominada — Detección de Dominancia Extrema</div>',
                unsafe_allow_html=True)
    mostrar_dominante()
    st.markdown('</div>', unsafe_allow_html=True)

elif pagina == "Historial Dominada":
    from modules.dominant_history import mostrar as mostrar_hist_dom
    st.markdown('<div class="tarjeta">', unsafe_allow_html=True)
    st.markdown('<div class="titulo-tarjeta">📁 Historial — Apuesta Dominada</div>',
                unsafe_allow_html=True)
    mostrar_hist_dom()
    st.markdown('</div>', unsafe_allow_html=True)
