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
import sys
from datetime import date as _date_today
from pathlib import Path

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
        config["tema"] = st.session_state.get("sel_tema", "Azul Profesional")
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
        roi_color = "#8889aa"
    else:
        roi       = round(neto / total_apostado * 100, 1)
        roi_disp  = f"{'+'if roi>=0 else ''}{roi}%"
        roi_color = "#22c55e" if roi >= 0 else "#ef4444"

    yield_val  = round(neto / resueltas, 2) if resueltas > 0 else 0.0
    win_rate   = round(ganadas / total * 100, 1) if total > 0 else 0.0
    lose_rate  = round(100 - win_rate, 1) if total > 0 else 0.0

    serie_reciente = ganancias_serie[-20:] if ganancias_serie else [0, 0]
    serie_saldo    = [saldo * 0.88, saldo * 0.92, saldo * 0.96, saldo * 0.98, saldo]
    serie_total    = list(range(1, max(total + 1, 3)))

    yld_color = "#22c55e" if yield_val >= 0 else "#ef4444"
    sign      = lambda v: "+" if v >= 0 else ""

    metricas = [
        ("ROI (30 días)",    roi_disp,                         roi_color, _sparkline_svg(serie_reciente, roi_color)),
        ("Bankroll",         f"€{saldo:.2f}",                  "#ffffff",  _sparkline_svg(serie_saldo,  "#3b82f6")),
        ("Yield",            f"{sign(yield_val)}{yield_val:.1f}%", yld_color, _sparkline_svg(serie_reciente[-10:] or [0,0], yld_color)),
        ("Apuestas Totales", str(total),                       "#e8e8f0",  _sparkline_svg(serie_total,  "#8889aa")),
        ("Ganadas",          f"{ganadas} ({win_rate}%)",       "#22c55e",  _sparkline_svg([ganadas]*4 or [0,0], "#22c55e")),
        ("Perdidas",         f"{perdidas} ({lose_rate}%)",     "#ef4444",  _sparkline_svg([perdidas]*4 or [0,0], "#ef4444")),
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
    initial_sidebar_state="expanded",   # El sidebar empieza visible
)

# ─────────────────────────────────────────────────────────────────────
#  ESTILOS GLOBALES — mínimos, sin imágenes ni posicionamiento absoluto
# ─────────────────────────────────────────────────────────────────────
ESTILOS_CSS = """
<style>
/* ── JhonBet Lab — Trading Dashboard Theme ── */
:root {
    --bg:                #0b0b14;
    --bg-tarjeta:        #12121e;
    --borde:             #1e1e38;
    --borde-activo:      #7c3aed;
    --texto:             #e8e8f0;
    --texto-apagado:     #8889aa;
    --acento-verde:      #22c55e;
    --acento-morado:     #7c3aed;
    --acento-dorado:     #f59e0b;
    --acento-azul:       #3b82f6;
    --acento-rojo:       #ef4444;
    --bg-elemento:       #16162a;
    --bg-alerta-exito:   #060d1a;
    --bg-alerta-peligro: #150508;
    --boton-bg:          #7c3aed;
    --logo-color:        #7c3aed;
    --bg-principal:      #0b0b14;
}

/* ── Fondo principal ── */
html, body,
[data-testid="stAppViewContainer"],
[data-testid="stApp"] {
    background-color: #0b0b14 !important;
    color: #e8e8f0 !important;
    font-family: "Inter", "Segoe UI", system-ui, sans-serif !important;
}
[data-testid="stHeader"]     { background-color: #0b0b14 !important; }
[data-testid="stToolbar"]    { display: none; }
[data-testid="stDecoration"] { display: none; }

/* ── Sidebar ── */
[data-testid="stSidebar"],
[data-testid="stSidebar"] > div {
    background-color: #0f0f1e !important;
    border-right: 1px solid #1e1e38 !important;
}

/* ── Botones globales — púrpura ── */
.stButton > button,
.stFormSubmitButton > button {
    background: linear-gradient(135deg, #5b21b6, #7c3aed) !important;
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

/* ── Nav buttons del sidebar — estilo sutil ── */
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    color: #8889aa !important;
    border: none !important;
    border-left: 2px solid transparent !important;
    border-radius: 0 6px 6px 0 !important;
    text-align: left !important;
    padding: 7px 12px !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    letter-spacing: .2px !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(124,58,237,0.12) !important;
    color: #d8b4fe !important;
    border-left-color: #7c3aed !important;
}

/* ── Tarjetas ── */
.tarjeta {
    background: linear-gradient(145deg, #13132000, #0f0f1e);
    background-color: #12121e;
    border: 1px solid #1e1e38;
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 8px;
}
.titulo-tarjeta {
    font-size: 9px;
    font-weight: 700;
    color: #8889aa;
    margin-bottom: 10px;
    padding-bottom: 7px;
    border-bottom: 1px solid #1e1e38;
    text-transform: uppercase;
    letter-spacing: 1.4px;
}

/* ── Encabezado compacto ── */
.encabezado-principal {
    background: linear-gradient(135deg, #12121e 0%, #1a1a2e 100%);
    border: 1px solid #1e1e38;
    border-radius: 8px;
    padding: 6px 14px;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.logo-texto   { font-size: 14px; font-weight: 800; color: #a78bfa; }
.logo-punto   { color: #f59e0b; }
.info-saldo   { color: #22c55e; font-weight: 700; font-size: 12px; }
.info-usuario { font-size: 10px; color: #8889aa; }

/* ── Top stats bar ── */
.stat-card-top {
    background: #12121e;
    border: 1px solid #1e1e38;
    border-top: 2px solid #2e2e55;
    border-radius: 8px;
    padding: 10px 12px 8px;
    position: relative;
}
.stat-card-label {
    font-size: 9px;
    color: #8889aa;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 3px;
}
.stat-card-value {
    font-size: 16px;
    font-weight: 800;
    line-height: 1.1;
    margin-bottom: 3px;
    color: #ffffff;
}
.stat-card-chart { opacity: 0.75; line-height: 0; display: block; }

/* ── Probabilidades ── */
.fila-prob    { display: flex; align-items: center; gap: 6px; margin: 4px 0; font-size: 12px; }
.insignia     { border-radius: 4px; padding: 1px 7px; font-weight: 700; font-size: 11px; background: #16162a; }
.prob-verde   { color: #22c55e; }
.prob-amarillo{ color: #f59e0b; }
.prob-azul    { color: #3b82f6; }
.prob-rojo    { color: #ef4444; }
.texto-apagado{ color: #8889aa; }
.texto-dorado { color: #f59e0b; font-weight: 700; }
.texto-azul   { color: #3b82f6; }
.texto-rojo   { color: #ef4444; }
.texto-valor  { color: #22c55e; font-weight: 700; }
.etiqueta-seccion { font-size: 10px; font-weight: 700; color: #a78bfa; margin-bottom: 6px; text-transform: uppercase; letter-spacing: .8px; }

/* ── Cuota cards ── */
.cuota-card       { background: #16162a; border: 1px solid #3b2f8a; border-radius: 8px; padding: 8px 6px; text-align: center; }
.cuota-card-label { font-size: 10px; color: #8889aa; text-transform: uppercase; }
.cuota-card-value { font-size: 22px; font-weight: 800; color: #a78bfa; line-height: 1.1; }
.cuota-card-sub   { font-size: 10px; color: #8889aa; }

/* ── Tablas de cuotas ── */
.tabla-cuotas { width: 100%; border-collapse: collapse; font-size: 12px; }
.tabla-cuotas th { color: #a78bfa; font-weight: 700; padding: 5px 8px; border-bottom: 1px solid #1e1e38; text-align: center; }
.tabla-cuotas th:first-child { text-align: left; }
.tabla-cuotas td { padding: 4px 8px; text-align: center; color: #e8e8f0; border-bottom: 1px solid #16162a; }
.tabla-cuotas td:first-child { text-align: left; color: #8889aa; font-weight: 600; }
.tabla-cuotas tr:hover td { background: #16162a; }
.cuota-mejor  { color: #22c55e !important; font-weight: 800; }
.col-resultado{ text-align: left !important; color: #8889aa; font-weight: 600; }

/* ── Barras predicción ── */
.fila-pred     { margin: 6px 0; }
.pred-etiqueta { font-size: 11px; color: #8889aa; margin-bottom: 3px; }
.barra-fondo   { background: #16162a; border-radius: 4px; height: 20px; overflow: hidden; }
.barra-relleno { height: 100%; border-radius: 3px; display: flex; align-items: center; justify-content: flex-end; padding-right: 8px; font-size: 11px; font-weight: 700; color: #fff; }

/* ── Alertas ── */
.alerta-peligro  { background: #16040a; border: 1px solid #ef4444; border-radius: 6px; padding: 6px 10px; margin: 4px 0; font-size: 12px; color: #ef4444; }
.alerta-exito    { background: #060d1a; border: 1px solid #3b82f6; border-radius: 6px; padding: 6px 10px; margin: 4px 0; font-size: 12px; color: #e8e8f0; line-height: 1.65; }
.insignia-estado { display: inline-block; border-radius: 4px; border: 1px solid; padding: 2px 10px; font-size: 11px; font-weight: 700; }

/* ── Historial ── */
.tabla-historial { width: 100%; border-collapse: collapse; font-size: 12px; }
.tabla-historial th { color: #a78bfa; padding: 4px 6px; border-bottom: 1px solid #1e1e38; text-align: left; }
.tabla-historial td { padding: 4px 6px; border-bottom: 1px solid #16162a; color: #e8e8f0; }
.ganado       { color: #22c55e; font-weight: 700; }
.perdido      { color: #ef4444; font-weight: 700; }
.gan-positiva { color: #22c55e; font-weight: 700; }
.gan-negativa { color: #ef4444; font-weight: 700; }

/* ── Stat boxes (sidebar) ── */
.caja-stat    { background: #16162a; border: 1px solid #1e1e38; border-radius: 6px; padding: 5px 8px; margin: 2px 0; }
.stat-etiqueta{ font-size: 10px; color: #8889aa; text-transform: uppercase; }
.stat-valor   { font-size: 14px; font-weight: 700; }

/* ── Ocultar controles nativos ── */
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapseButton"] button,
[data-testid="collapsedControl"] { display: none !important; }
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
</style>
"""

st.markdown(ESTILOS_CSS, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────
#  TEMAS VISUALES — definidos directamente en app.py
# ─────────────────────────────────────────────────────────────────────
NOMBRES_TEMAS = ["Élite Oscuro", "Verde Deportivo", "Azul Profesional"]

_TEMAS_CSS: dict[str, str] = {
    "Élite Oscuro": """
<style>
/* Élite Oscuro — acentos dorados, fondo negro puro */
:root {
    --bg-principal:      #000000;
    --bg-tarjeta:        #0f0e0a;
    --borde:             #3a2a00;
    --borde-activo:      #FFD700;
    --texto-apagado:     #888866;
    --acento-verde:      #FFD700;
    --acento-dorado:     #FFD700;
    --acento-azul:       #ffaa00;
    --acento-rojo:       #ff4444;
    --bg-elemento:       #141200;
    --bg-alerta-exito:   #100e00;
    --bg-alerta-peligro: #120404;
    --boton-bg:          linear-gradient(135deg, #5a4a00, #aa8800);
    --logo-color:        #FFD700;
}
html, body,
[data-testid="stApp"],
[data-testid="stAppViewContainer"] { background-color: #000000 !important; color: #ffffff !important; }
[data-testid="stHeader"]           { background-color: #000000 !important; }
[data-testid="stSidebar"]          { background-color: #1a1a0a !important; }
.stButton > button, .stFormSubmitButton > button {
    background: linear-gradient(135deg, #5a4a00, #aa8800) !important;
    color: #000000 !important; border-color: #FFD70088 !important;
}
[data-testid="metric-container"] { background-color: #0f0e0a !important; border: 1px solid #3a2a00 !important; }
</style>""",

    "Verde Deportivo": """
<style>
/* Verde Deportivo — acentos verde neón, fondo negro puro */
:root {
    --bg-principal:      #000000;
    --bg-tarjeta:        #090f09;
    --borde:             #0f3020;
    --borde-activo:      #00ff88;
    --texto-apagado:     #4a8a60;
    --acento-verde:      #00ff88;
    --acento-dorado:     #00ff88;
    --acento-azul:       #00ddff;
    --acento-rojo:       #ff4466;
    --bg-elemento:       #05120a;
    --bg-alerta-exito:   #021008;
    --bg-alerta-peligro: #120408;
    --boton-bg:          linear-gradient(135deg, #005522, #00aa55);
    --logo-color:        #00ff88;
}
html, body,
[data-testid="stApp"],
[data-testid="stAppViewContainer"] { background-color: #000000 !important; color: #ffffff !important; }
[data-testid="stHeader"]           { background-color: #000000 !important; }
[data-testid="stSidebar"]          { background-color: #0a1a0a !important; }
.stButton > button, .stFormSubmitButton > button {
    background: linear-gradient(135deg, #005522, #00aa55) !important;
    color: #000000 !important; border-color: #00ff8888 !important;
}
[data-testid="metric-container"] { background-color: #05120a !important; border: 1px solid #0f3020 !important; }
</style>""",

    "Azul Profesional": """
<style>
/* Azul Profesional — Trading Dashboard, navy + morado */
:root {
    --bg-principal:      #0b0b14;
    --bg-tarjeta:        #12121e;
    --borde:             #1e1e38;
    --borde-activo:      #7c3aed;
    --texto-apagado:     #8889aa;
    --acento-verde:      #22c55e;
    --acento-morado:     #7c3aed;
    --acento-dorado:     #f59e0b;
    --acento-azul:       #3b82f6;
    --acento-rojo:       #ef4444;
    --bg-elemento:       #16162a;
    --bg-alerta-exito:   #060d1a;
    --bg-alerta-peligro: #150508;
    --boton-bg:          linear-gradient(135deg, #5b21b6, #7c3aed);
    --logo-color:        #a78bfa;
}
html, body,
[data-testid="stApp"],
[data-testid="stAppViewContainer"] { background-color: #0b0b14 !important; color: #e8e8f0 !important; }
[data-testid="stHeader"]           { background-color: #0b0b14 !important; }
[data-testid="stSidebar"]          { background-color: #0f0f1e !important; }
.stButton > button, .stFormSubmitButton > button {
    background: linear-gradient(135deg, #5b21b6, #7c3aed) !important;
    color: #ffffff !important;
}
[data-testid="metric-container"] { background-color: #12121e !important; border: 1px solid #1e1e38 !important; }
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
        tema = _cargar_config().get("tema", "Azul Profesional")
        st.session_state["tema_activo"] = tema   # pre-inicializar para el resto del render
    return _TEMAS_CSS.get(tema, _TEMAS_CSS["Azul Profesional"])


# Inyectar CSS del tema ANTES de cualquier otro contenido (máxima prioridad)
st.markdown(_css_tema_activo(), unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────
#  ESTADO DE SESIÓN — valores por defecto
# ─────────────────────────────────────────────────────────────────────
# st.session_state es como la "memoria" de la app entre interacciones.
# Streamlit recarga el script completo en cada clic, y session_state
# permite recordar qué página está activa, qué partido se analiza, etc.

_config_inicial = _cargar_config()   # Leemos configuración guardada en disco

# Definimos los valores por defecto de todas las variables de sesión
_DEFAULTS = {
    "pagina_activa":  "Análisis de Partidos",
    "saldo":          _config_inicial.get("saldo", 200.0),
    "tema_activo":    _config_inicial.get("tema", "Azul Profesional"),
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
PAGINAS = [
    ("🏠", "Análisis de Partidos"),        # Módulo principal de análisis
    ("📊", "Comparación de Cuotas"),       # Tabla de cuotas por casa de apuestas
    ("🤖", "Modelo Predictivo"),           # Simulador xG con gráficos Plotly
    ("🔔", "Alertas y Retiradas"),         # Historial y alertas de bankroll
    ("⚡", "Análisis en Vivo"),            # Estadísticas en tiempo real desde Codere
    ("📋", "Historial Análisis Claude"),   # Historial de análisis generados por Claude
    ("🔥", "Apuesta Dominada"),            # Detección automática de dominancia extrema
    ("📁", "Historial Dominada"),          # Historial de análisis de Apuesta Dominada
]

NOMBRE_USUARIO = "Jhon"   # Nombre mostrado en el encabezado

with st.sidebar:
    # Header del sidebar — Trading Dashboard
    logo_path = Path(__file__).parent / "assets" / "logo.png"
    if logo_path.exists():
        st.image(str(logo_path), width=140)
    else:
        st.markdown(
            '<div style="padding:6px 0 12px 0;">'
            '<div style="font-size:9px;font-weight:700;color:#7c3aed;letter-spacing:2.5px;'
            'text-transform:uppercase;margin-bottom:5px;opacity:.85;">Trading Dashboard</div>'
            '<div style="font-size:17px;font-weight:800;line-height:1.1;">'
            '<span style="color:#a78bfa;">📊 JhonBet</span>'
            '<span style="color:#f59e0b;"> Lab</span>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    # Indicador de página activa (línea de color)
    _pagina_nav = st.session_state.get("pagina_activa", "Análisis de Partidos")
    _nav_label  = next((f"{i} {n}" for i, n in PAGINAS if n == _pagina_nav), "")
    if _nav_label:
        st.markdown(
            f'<div style="font-size:9px;color:#a78bfa;background:rgba(124,58,237,.12);'
            f'border-left:2px solid #7c3aed;border-radius:0 4px 4px 0;'
            f'padding:3px 8px;margin-bottom:6px;letter-spacing:.3px;">'
            f'{_nav_label}</div>',
            unsafe_allow_html=True,
        )

    # Menú de navegación
    for icono, nombre_pagina in PAGINAS:
        if st.button(f"{icono}  {nombre_pagina}", key=f"nav_{nombre_pagina}",
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

    idx_actual = NOMBRES_TEMAS.index(st.session_state.get("tema_activo", "Azul Profesional"))
    st.selectbox(
        "Tema:",
        NOMBRES_TEMAS,
        index=idx_actual,
        key="sel_tema",
        label_visibility="collapsed",
        on_change=_cambiar_tema,
    )

# ─────────────────────────────────────────────────────────────────────
#  BARRA SUPERIOR — 6 métricas con sparklines
# ─────────────────────────────────────────────────────────────────────
_barra_stats_top()

# ── Banner Modo Observación ──────────────────────────────────────────────────
if st.session_state.get("modo_observacion"):
    st.markdown(
        '<div style="background:#0d0b1e;border:1px solid #7c3aed;border-radius:8px;'
        'padding:7px 14px;margin-bottom:8px;display:flex;align-items:center;gap:10px;">'
        '<span style="font-size:14px;">🔬</span>'
        '<span style="color:#a78bfa;font-weight:700;font-size:12px;letter-spacing:.5px;">'
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
    from modules.analysis        import mostrar as mostrar_analisis
    from modules.odds_comparison import mostrar as mostrar_cuotas
    from modules.predictive_model import mostrar as mostrar_modelo

    # Fila superior: 3 columnas
    col_analisis, col_cuotas, col_modelo = st.columns([1.1, 1.1, 0.9])

    with col_analisis:
        st.markdown('<div class="tarjeta">', unsafe_allow_html=True)
        st.markdown('<div class="titulo-tarjeta">Análisis de Partidos</div>', unsafe_allow_html=True)
        mostrar_analisis()
        st.markdown('</div>', unsafe_allow_html=True)

    with col_cuotas:
        st.markdown('<div class="tarjeta">', unsafe_allow_html=True)
        st.markdown('<div class="titulo-tarjeta">Comparación de Cuotas</div>', unsafe_allow_html=True)
        mostrar_cuotas()
        st.markdown('</div>', unsafe_allow_html=True)

    with col_modelo:
        st.markdown('<div class="tarjeta">', unsafe_allow_html=True)
        st.markdown('<div class="titulo-tarjeta">Modelo Predictivo</div>', unsafe_allow_html=True)
        mostrar_modelo()
        st.markdown('</div>', unsafe_allow_html=True)

    # Fila inferior: Claude AI (ancho completo para dashboard de dos columnas)
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
