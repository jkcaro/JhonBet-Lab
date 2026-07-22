"""
BetVision AI — Aplicación principal de análisis de apuestas deportivas.

Esta app permite:
  - Analizar partidos con el modelo Poisson/xG
  - Comparar cuotas entre casas de apuestas
  - Obtener análisis de Claude AI
  - Detectar valor (edge) en el mercado
  - Registrar historial personal de apuestas

Para iniciar:  streamlit run app.py
"""

import json          # Para leer/escribir el archivo de configuración (config.json)
import logging
import os
import sys
from pathlib import Path

os.makedirs(Path(__file__).parent / "data", exist_ok=True)

logging.basicConfig(
    filename=str(Path.home() / "betvision_debug.log"),
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    force=True,
)

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
_RUTA_ESTADO   = Path(__file__).parent / "data" / "estado_sesion.json"

_CLAVES_SESION = [
    "pagina_activa", "liga_activa", "partido_activo",
    "analisis_listo", "claude_analisis",
    "tema_activo", "modo_observacion", "saldo",
    "fuente_xg_activa", "fuente_odds", "fuente_espn", "fuente_logos",
    # Análisis Primera Parte (modules/first_half_analysis.py) — módulo independiente
    "fh_1x2_local", "fh_1x2_empate", "fh_1x2_visitante",
    "fh_ou05_over", "fh_ou05_under",
    "fh_ou15_over", "fh_ou15_under",
    "fh_1marca_local", "fh_1marca_visitante", "fh_1marca_ninguno",
    "fh_stat_local_nombre", "fh_stat_local_pct_marca", "fh_stat_local_pct_encaja",
    "fh_stat_local_pct_marca_primero", "fh_stat_local_pct_recibe_primero",
    "fh_stat_local_goles_115", "fh_stat_local_goles_1630", "fh_stat_local_goles_3145",
    "fh_stat_visit_nombre", "fh_stat_visit_pct_marca", "fh_stat_visit_pct_encaja",
    "fh_stat_visit_pct_marca_primero", "fh_stat_visit_pct_recibe_primero",
    "fh_stat_visit_goles_115", "fh_stat_visit_goles_1630", "fh_stat_visit_goles_3145",
    "fh_analisis_ia",
]


def _cargar_estado_sesion() -> None:
    if not _RUTA_ESTADO.exists():
        return
    try:
        import json as _json
        with open(_RUTA_ESTADO, "r", encoding="utf-8") as _f:
            _datos = _json.load(_f)
        for _k, _v in _datos.items():
            if _k not in st.session_state:
                st.session_state[_k] = _v
    except Exception:
        pass


def _guardar_estado_sesion() -> None:
    try:
        import json as _json
        _datos = {k: st.session_state[k] for k in _CLAVES_SESION if k in st.session_state}
        _RUTA_ESTADO.parent.mkdir(parents=True, exist_ok=True)
        with open(_RUTA_ESTADO, "w", encoding="utf-8") as _f:
            _json.dump(_datos, _f, ensure_ascii=False, default=str)
    except Exception:
        pass


def _limpiar_estado_sesion() -> None:
    try:
        if _RUTA_ESTADO.exists():
            _RUTA_ESTADO.unlink()
    except Exception:
        pass
    for _k in _CLAVES_SESION:
        st.session_state.pop(_k, None)


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


def _kpi_cards_virtual() -> None:
    """Fila de 6 tarjetas KPI grandes calculadas desde virtual_bets.csv con sparklines Plotly."""
    import plotly.graph_objects as go
    from datetime import datetime, timedelta

    _RUTA_VB = Path(__file__).parent / "data" / "virtual_bets.csv"

    total = ganadas = perdidas = 0
    neto = roi_30d = yield_val = win_rate = 0.0
    serie_acum: list = []
    serie_acum_30: list = []

    def _cargar_df_virtual() -> "pd.DataFrame":
        """Carga virtual_bets.csv; si está vacío usa history.csv mapeando columnas."""
        df = pd.read_csv(_RUTA_VB)
        if df.empty or len(df) == 0:
            raise ValueError("vacío")
        df["pl_virtual"]    = pd.to_numeric(df["pl_virtual"],    errors="coerce").fillna(0)
        df["stake_virtual"] = pd.to_numeric(df["stake_virtual"], errors="coerce").fillna(0)
        df["fecha"]         = pd.to_datetime(df["fecha"],        errors="coerce")
        return df

    def _cargar_df_history() -> "pd.DataFrame":
        """Fallback: lee history.csv mapeando 'ganancia' → 'pl_virtual'."""
        df = pd.read_csv(_RUTA_HISTORIAL)
        df = df.rename(columns={"ganancia": "pl_virtual"})
        df["pl_virtual"]    = pd.to_numeric(df["pl_virtual"],    errors="coerce").fillna(0)
        df["stake_virtual"] = df["pl_virtual"].abs()   # proxy: stake ≈ |ganancia|
        df["fecha"]         = pd.to_datetime(df["fecha"], errors="coerce", dayfirst=True)
        return df

    try:
        try:
            df = _cargar_df_virtual()
        except Exception:
            df = _cargar_df_history()

        total    = len(df)
        ganadas  = int((df["resultado"] == "Ganado").sum())
        perdidas = int((df["resultado"] == "Perdido").sum())
        neto     = float(df["pl_virtual"].sum())
        resueltas = ganadas + perdidas
        win_rate  = round(ganadas / resueltas * 100, 1) if resueltas > 0 else 0.0

        total_stake = float(df["stake_virtual"].sum())
        yield_val   = round(neto / total_stake * 100, 1) if total_stake > 0.01 else 0.0

        hace_30   = datetime.now() - timedelta(days=30)
        df_30     = df[df["fecha"] >= hace_30]
        pl_30     = float(df_30["pl_virtual"].sum())
        sk_30     = float(df_30["stake_virtual"].sum())
        roi_30d   = round(pl_30 / sk_30 * 100, 1) if sk_30 > 0.01 else 0.0

        serie_acum    = df["pl_virtual"].cumsum().tolist()
        serie_acum_30 = df_30["pl_virtual"].cumsum().tolist() if not df_30.empty else []
    except Exception:
        pass

    if len(serie_acum) < 2:
        serie_acum = [0.0, 0.0]
    if len(serie_acum_30) < 2:
        serie_acum_30 = [0.0, 0.0]

    def _spark(serie: list, color: str, fill: str) -> go.Figure:
        y = [float(v) for v in serie]
        fig = go.Figure(go.Scatter(
            x=list(range(len(y))), y=y,
            mode="lines",
            line=dict(color=color, width=1.8),
            fill="tozeroy", fillcolor=fill,
        ))
        fig.update_layout(
            margin=dict(l=0, r=0, t=0, b=0),
            height=52,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(visible=False, fixedrange=True),
            yaxis=dict(visible=False, fixedrange=True),
            showlegend=False,
        )
        return fig

    def _vc(v: float) -> str:
        return "#16A34A" if v >= 0 else "#EF4444"

    def _s(v: float) -> str:
        return "+" if v >= 0 else ""

    sin_datos = total == 0
    kpis = [
        {
            "icono": "📈", "bg": "#1E3A5F",
            "label": "ROI 30 días", "sub": "últimos 30 días",
            "valor": f"{_s(roi_30d)}{roi_30d:.1f}%" if not sin_datos else "—",
            "color_val": _vc(roi_30d),
            "serie": serie_acum_30, "spark_c": _vc(roi_30d),
            "fill": f"rgba({'22,163,74' if roi_30d>=0 else '239,68,68'},0.15)",
        },
        {
            "icono": "💰", "bg": "#14291A",
            "label": "Beneficio Neto", "sub": "P&L acumulado",
            "valor": f"{_s(neto)}€{neto:.2f}" if not sin_datos else "—",
            "color_val": _vc(neto),
            "serie": serie_acum, "spark_c": _vc(neto),
            "fill": f"rgba({'22,163,74' if neto>=0 else '239,68,68'},0.15)",
        },
        {
            "icono": "🎯", "bg": "#1E1A3F",
            "label": "Win Rate", "sub": f"{ganadas}G · {perdidas}P",
            "valor": f"{win_rate:.1f}%" if not sin_datos else "—",
            "color_val": "#60A5FA",
            "serie": serie_acum, "spark_c": "#7C3AED",
            "fill": "rgba(124,58,237,0.15)",
        },
        {
            "icono": "📊", "bg": "#2A2010",
            "label": "Yield", "sub": "rendimiento/apuesta",
            "valor": f"{_s(yield_val)}{yield_val:.1f}%" if not sin_datos else "—",
            "color_val": _vc(yield_val),
            "serie": serie_acum, "spark_c": "#F59E0B",
            "fill": "rgba(245,158,11,0.15)",
        },
        {
            "icono": "🎰", "bg": "#102030",
            "label": "Apuestas Totales", "sub": "apuestas virtuales",
            "valor": str(total),
            "color_val": "#60A5FA",
            "serie": list(range(1, max(total + 1, 3))), "spark_c": "#60A5FA",
            "fill": "rgba(96,165,250,0.15)",
        },
        {
            "icono": "📉", "bg": "#2A1010",
            "label": "Pérdidas", "sub": f"{100 - win_rate:.1f}% del total" if not sin_datos else "sin datos",
            "valor": str(perdidas),
            "color_val": "#EF4444",
            "serie": [float(perdidas)] * max(total, 2), "spark_c": "#EF4444",
            "fill": "rgba(239,68,68,0.15)",
        },
    ]

    st.markdown("""
<style>
.kpi-vb-card {
    background: var(--bg-tarjeta, #1E293B);
    border: 1px solid var(--borde, #334155);
    border-radius: 10px 10px 0 0;
    padding: 14px 10px 8px;
    text-align: center;
    border-bottom: none;
}
.kpi-vb-ring {
    width: 44px; height: 44px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 20px; margin: 0 auto 8px;
}
.kpi-vb-val {
    font-family: "Poppins", sans-serif;
    font-size: 21px; font-weight: 700; line-height: 1.1; margin-bottom: 3px;
}
.kpi-vb-label {
    font-size: 9.5px; font-weight: 700;
    color: var(--texto-apagado, #94A3B8);
    text-transform: uppercase; letter-spacing: 1px; margin-bottom: 2px;
}
.kpi-vb-sub {
    font-size: 9px; color: var(--texto-apagado, #94A3B8);
}
/* el plotly chart debajo cierra visualmente la tarjeta */
div[data-testid="stVerticalBlock"] > div:has(.kpi-vb-card) + div > div[data-testid="stPlotlyChart"] > div {
    border: 1px solid var(--borde, #334155);
    border-top: none;
    border-radius: 0 0 10px 10px;
    overflow: hidden;
}
</style>
""", unsafe_allow_html=True)

    cols = st.columns(6)
    for col, k in zip(cols, kpis):
        with col:
            st.markdown(
                f'<div class="kpi-vb-card">'
                f'<div class="kpi-vb-ring" style="background:{k["bg"]};">{k["icono"]}</div>'
                f'<div class="kpi-vb-val" style="color:{k["color_val"]};">{k["valor"]}</div>'
                f'<div class="kpi-vb-label">{k["label"]}</div>'
                f'<div class="kpi-vb-sub">{k["sub"]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            st.plotly_chart(
                _spark(k["serie"], k["spark_c"], k["fill"]),
                use_container_width=True,
                config={"displayModeBar": False},
                key=f"kpi_vb_{k['label'].replace(' ', '_')}",
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

    cards_html = "".join(
        f'<div class="stat-card-top">'
        f'<div class="stat-card-label">{label}</div>'
        f'<div class="stat-card-value" style="color:{color};">{valor}</div>'
        f'<div class="stat-card-chart">{spark}</div>'
        f'</div>'
        for label, valor, color, spark in metricas
    )
    st.markdown(f'<div class="stats-row">{cards_html}</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────
#  PANTALLA DE LOGIN — bloquea toda la app
# ─────────────────────────────────────────────────────────────────────
def _render_login_page() -> None:
    """
    Renderiza la pantalla completa de login y llama st.stop().
    Panel izquierdo: tarjeta oscura con formulario.
    Panel derecho: imagen del estadio a pantalla completa.
    """
    import base64 as _b64
    import bcrypt as _bcrypt

    # Imagen estadio → base64 para CSS background-image
    _img_path = Path(__file__).parent / "assets" / "estadio-jugadores.png"
    _img_css = ""
    if _img_path.exists():
        _img_b64_str = _b64.b64encode(_img_path.read_bytes()).decode()
        _img_css = (
            f'.login-panel-right{{background-image:url("data:image/png;base64,{_img_b64_str}");'
            f'background-size:cover;background-position:center;}}'
        )

    st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Poppins:wght@600;700&display=swap');
/* ── Ocultar chrome de Streamlit ── */
[data-testid="stSidebar"],[data-testid="stHeader"],
[data-testid="stToolbar"],[data-testid="stDecoration"]{{display:none!important;}}
section[data-testid="stMain"]{{padding:0!important;}}
[data-testid="stMainBlockContainer"],.block-container{{
    padding:0!important;max-width:100%!important;width:100%!important;
}}
/* ── Columnas full-viewport ── */
[data-testid="stHorizontalBlock"]{{
    gap:0!important;min-height:100vh!important;align-items:stretch!important;
}}
/* Panel izquierdo */
[data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:nth-child(1){{
    background:#0F172A!important;padding:0!important;min-height:100vh!important;
}}
[data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:nth-child(1)>[data-testid="stVerticalBlock"]{{
    min-height:100vh!important;display:flex!important;
    flex-direction:column!important;justify-content:center!important;
    padding:48px!important;box-sizing:border-box!important;max-width:480px!important;
}}
/* Panel derecho */
[data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:nth-child(2){{
    padding:0!important;min-height:100vh!important;
}}
[data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:nth-child(2)>[data-testid="stVerticalBlock"]{{
    min-height:100vh!important;padding:0!important;
}}
/* ── Inputs ── */
[data-testid="stTextInput"]>div>div{{
    background:#1E293B!important;border:1px solid #334155!important;
    border-radius:8px!important;color:#E2E8F0!important;
}}
[data-testid="stTextInput"] input{{
    color:#E2E8F0!important;font-size:14px!important;background:transparent!important;
    font-family:Inter,sans-serif!important;
}}
[data-testid="stTextInput"] input::placeholder{{color:#475569!important;}}
[data-testid="stTextInput"] label{{
    color:#64748B!important;font-size:12px!important;font-weight:500!important;
    font-family:Inter,sans-serif!important;
}}
[data-testid="stTextInput"]>div>div:focus-within{{
    border-color:#2563EB!important;box-shadow:0 0 0 3px rgba(37,99,235,.15)!important;
}}
/* ── Checkbox Recordarme ── */
[data-testid="stCheckbox"] label span{{
    color:#64748B!important;font-size:13px!important;font-family:Inter,sans-serif!important;
}}
/* ── Botón Iniciar sesión ── */
.st-key-_btn_login_gate>button{{
    background:linear-gradient(135deg,#2563EB,#1D4ED8)!important;
    color:#fff!important;border:none!important;border-radius:10px!important;
    height:48px!important;font-size:15px!important;font-weight:600!important;
    width:100%!important;margin-top:4px!important;
    letter-spacing:.3px!important;cursor:pointer!important;
    font-family:Inter,sans-serif!important;transition:opacity .15s!important;
}}
.st-key-_btn_login_gate>button:hover{{opacity:.88!important;}}
/* ── Imagen panel derecho ── */
{_img_css}
.login-panel-right{{min-height:100vh;width:100%;position:relative;}}
.login-panel-right-overlay{{
    position:absolute;inset:0;
    background:linear-gradient(135deg,rgba(15,23,42,.3) 0%,rgba(15,23,42,.05) 100%);
}}
</style>
""", unsafe_allow_html=True)

    col_izq, col_der = st.columns(2)

    # ── Panel derecho: estadio ──────────────────────────────────────
    with col_der:
        st.markdown(
            '<div class="login-panel-right">'
            '<div class="login-panel-right-overlay"></div>'
            '</div>',
            unsafe_allow_html=True,
        )

    # ── Panel izquierdo: formulario ─────────────────────────────────
    with col_izq:
        # Logo
        st.markdown(
            '<div style="display:flex;align-items:center;gap:18px;margin-bottom:56px;">'
            '<span style="font-size:52px;line-height:1;">⚽</span>'
            '<div>'
            '<div style="font-family:Poppins,sans-serif;font-size:46px;font-weight:700;'
            'color:#fff;line-height:1.05;letter-spacing:-1px;">'
            'BETVISION <span style="color:#F59E0B;">AI</span></div>'
            '<div style="font-size:13px;color:rgba(255,255,255,.4);letter-spacing:3.5px;'
            'text-transform:uppercase;margin-top:6px;">Professional Analytics</div>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        # Encabezado
        st.markdown(
            '<h1 style="font-family:Poppins,sans-serif;font-size:36px;font-weight:700;'
            'color:#F1F5F9;margin:0 0 12px;line-height:1.2;">Bienvenido de vuelta</h1>'
            '<p style="font-size:18px;color:#64748B;margin:0 0 36px;'
            'font-family:Inter,sans-serif;">Inicia sesión en tu cuenta</p>',
            unsafe_allow_html=True,
        )

        # Formulario
        _li_email    = st.text_input("Correo / Usuario", placeholder="jhon@betvision.com",
                                     key="_inp_email_gate")
        _li_password = st.text_input("Contraseña", type="password", placeholder="••••••••",
                                     key="_inp_pw_gate")
        _li_remember = st.checkbox("Recordarme", key="_chk_remember_gate")
        _li_submit   = st.button("Iniciar sesión", use_container_width=True,
                                 key="_btn_login_gate", type="primary")

        # Botones sociales decorativos (deshabilitados)
        st.markdown("""
<div style="display:flex;align-items:center;gap:12px;margin:22px 0 16px;">
  <div style="flex:1;height:1px;background:#1E293B;"></div>
  <span style="font-size:12px;color:#475569;white-space:nowrap;font-family:Inter,sans-serif;">
    o continúa con</span>
  <div style="flex:1;height:1px;background:#1E293B;"></div>
</div>
<div style="display:flex;gap:10px;">
  <button disabled title="Próximamente"
    style="flex:1;height:44px;background:#1E293B;border:1px solid #334155;
    border-radius:8px;color:#475569;font-size:12px;cursor:not-allowed;
    display:flex;align-items:center;justify-content:center;gap:8px;
    font-family:Inter,sans-serif;opacity:.7;">
    <svg width="15" height="15" viewBox="0 0 24 24">
      <path fill="#475569" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
      <path fill="#475569" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
      <path fill="#475569" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
      <path fill="#475569" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
    </svg>
    Google — Próximamente
  </button>
  <button disabled title="Próximamente"
    style="flex:1;height:44px;background:#1E293B;border:1px solid #334155;
    border-radius:8px;color:#475569;font-size:12px;cursor:not-allowed;
    display:flex;align-items:center;justify-content:center;gap:8px;
    font-family:Inter,sans-serif;opacity:.7;">
    <svg width="15" height="15" viewBox="0 0 21 21">
      <rect x="1" y="1" width="9" height="9" fill="#475569"/>
      <rect x="11" y="1" width="9" height="9" fill="#475569"/>
      <rect x="1" y="11" width="9" height="9" fill="#475569"/>
      <rect x="11" y="11" width="9" height="9" fill="#475569"/>
    </svg>
    Microsoft — Próximamente
  </button>
</div>
""", unsafe_allow_html=True)

        # ── Lógica de autenticación ─────────────────────────────────
        if _li_submit:
            _login_ok = False
            try:
                _uname  = st.secrets["auth"]["username"]
                _email  = st.secrets["auth"]["email"]
                _stored = st.secrets["auth"]["hashed_password"].encode()
                _typed  = _li_email.strip().lower()
                logging.info("LOGIN: typed=%r uname=%r email=%r match=%s",
                             _typed, _uname.lower(), _email.lower(),
                             _typed in (_uname.lower(), _email.lower()))
                if _typed in (_uname.lower(), _email.lower()):
                    _login_ok = _bcrypt.checkpw(_li_password.encode(), _stored)
                    logging.info("LOGIN: bcrypt_ok=%s stored_prefix=%r",
                                 _login_ok, _stored[:10])
            except Exception:
                logging.exception("LOGIN: bcrypt block exception")

            if _login_ok:
                # Claves que stauth 0.4.x espera en session_state
                st.session_state['authentication_status'] = True
                st.session_state['username']              = st.secrets["auth"]["username"]
                st.session_state['name']                  = st.secrets["auth"]["name"]
                st.session_state['email']                 = st.secrets["auth"]["email"]
                st.session_state['roles']                 = None
                st.session_state['logout']                = None
                # Persistir cookie — siempre si hay authenticator
                # "Recordarme" controla expiry: 30 días vs sólo la sesión actual
                if _authenticator is not None:
                    try:
                        if not _li_remember:
                            _authenticator.cookie_controller.cookie_model.cookie_expiry_days = 0
                        _authenticator.cookie_controller.set_cookie()
                        logging.info("LOGIN: set_cookie OK")
                    except Exception:
                        logging.exception("LOGIN: set_cookie FAILED")
                st.rerun()
            else:
                if _li_email or _li_password:
                    st.markdown(
                        '<div style="background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.35);'
                        'border-radius:8px;padding:10px 14px;margin-top:10px;'
                        'font-size:13px;color:#EF4444;font-family:Inter,sans-serif;">'
                        '⚠️ Correo o contraseña incorrectos.</div>',
                        unsafe_allow_html=True,
                    )

    st.stop()


# ─── Configuración global de la página ────────────────────────────────────────
# Esta llamada DEBE ser la primera de Streamlit en el script.
# Define el título de la pestaña del navegador, el icono y el layout.
st.set_page_config(
    page_title="BetVision AI",
    page_icon="📊",
    layout="wide",                      # Usa todo el ancho de la pantalla
    initial_sidebar_state="auto",        # Desktop: expandido · Mobile: colapsado
)

# ─── Puerta de autenticación ───────────────────────────────────────────────────
# Inicializa streamlit-authenticator y restaura sesión desde cookie si existe.
# login(location='unrendered') lee st.context.cookies y setea authentication_status
# sin renderizar ningún formulario — DEBE llamarse antes del st.stop().
_authenticator = None
try:
    import streamlit_authenticator as stauth
    _auth_creds = {
        "usernames": {
            st.secrets["auth"]["username"]: {
                "name":     st.secrets["auth"]["name"],
                "email":    st.secrets["auth"]["email"],
                "password": st.secrets["auth"]["hashed_password"],
            }
        }
    }
    _authenticator = stauth.Authenticate(
        _auth_creds,
        cookie_name=st.secrets["cookie"]["name"],
        cookie_key=st.secrets["cookie"]["key"],
        cookie_expiry_days=float(st.secrets["cookie"]["expiry_days"]),
        login_sleep_time=0,  # stauth por defecto duerme 0.7 s en cada login() — lo eliminamos
    )
    # Solo restaurar desde cookie si no estamos ya autenticados en esta sesión.
    # stauth.login() sobreescribiría authentication_status a None si no hay cookie,
    # destruyendo el True que el formulario manual ya estableció en el rerun anterior.
    if st.session_state.get("authentication_status") is not True:
        _authenticator.login(location='unrendered')

except Exception as _auth_exc:
    st.exception(_auth_exc)
    st.stop()

if st.session_state.get("authentication_status") is not True:
    _render_login_page()   # → inyecta CSS + UI + lógica, termina con st.stop()

# ─────────────────────────────────────────────────────────────────────
#  ESTILOS GLOBALES — mínimos, sin imágenes ni posicionamiento absoluto
# ─────────────────────────────────────────────────────────────────────
ESTILOS_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Poppins:wght@600;700&display=swap');

/* ── BetVision AI — DeOP Connect Theme ── */
:root {
    --font-titulo: "Poppins", "Segoe UI", system-ui, sans-serif;
    --font-texto:  "Inter",   "Segoe UI", system-ui, sans-serif;
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
    font-family: var(--font-texto) !important;
}

/* ── Tipografía: Poppins SemiBold en títulos, Inter en texto ── */
h1, h2, h3, h4, h5, h6,
.titulo-tarjeta,
[data-testid="stHeadingWithActionElements"],
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3 {
    font-family: var(--font-titulo) !important;
    font-weight: 600 !important;
}
body, p, label, input, select, textarea, button,
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li {
    font-family: var(--font-texto) !important;
}

[data-testid="stHeader"]     { display: none !important; height: 0 !important; }
[data-testid="stToolbar"]    { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }

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

/* ── Nav buttons del sidebar ── */
[data-testid="stSidebar"] .stButton {
    margin: 1px 0 !important;
    padding: 0 6px !important;
    line-height: 1 !important;
}
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    color: #aac4d4 !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0 12px 0 14px !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    letter-spacing: .2px !important;
    height: 40px !important;
    min-height: 40px !important;
    max-height: 40px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
    text-align: left !important;
    width: 100% !important;
    transition: background 0.15s ease, color 0.15s ease !important;
}
/* div interno (stMarkdownContainer en Streamlit 1.58) */
[data-testid="stSidebar"] .stButton > button > div {
    text-align: left !important;
    margin: 0 !important;
    width: auto !important;
}
[data-testid="stSidebar"] .stButton > button > div[data-testid="stMarkdownContainer"] {
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
    text-align: left !important;
    width: auto !important;
    margin: 0 !important;
}
[data-testid="stSidebar"] .stButton > button p {
    text-align: left !important;
    margin: 0 !important;
    line-height: 1 !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.07) !important;
    color: #ffffff !important;
    opacity: 1 !important;
}

/* ── Categorías del sidebar (estilo DeOP) ── */
.deop-categoria {
    font-size: 9px;
    font-weight: 800;
    color: #6f96aa;
    letter-spacing: 1.6px;
    text-transform: uppercase;
    padding: 10px 10px 3px 18px;
    margin-top: 4px;
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

/* ── Stats row: CSS grid — fiable en todos los browsers ── */
.stats-row {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 8px;
    margin-bottom: 8px;
}

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
/* Streamlit 1.58: stExpandSidebarButton ES el <button> de abrir; stSidebarCollapseButton = cerrar */
[data-testid="stSidebarCollapseButton"],
[data-testid="stExpandSidebarButton"]   { display: none !important; }
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }

/* ════════════════════════════════════════════════════════════
   RESPONSIVE — breakpoint mobile 768px
   ════════════════════════════════════════════════════════════ */

@media (max-width: 767px) {

  /* ── Stats row: 2 columnas (CSS grid, sin :has()) ── */
  .stats-row { grid-template-columns: repeat(2, 1fr) !important; gap: 6px !important; }

  /* ── stHeader: position:absolute z-index:999990, en temas oscuros = barra negra.
        Lo hacemos transparente y sin interceptar clics. ── */
  [data-testid="stHeader"] {
    background: transparent !important;
    box-shadow: none !important;
    pointer-events: none !important;
  }

  /* ── Hamburguesa: creada en document.body vía component JS (escapa stApp overflow:hidden) ── */

  /* ── Botón CERRAR sidebar (stSidebarCollapseButton, dentro del sidebar) ── */
  [data-testid="stSidebarCollapseButton"] { display: flex !important; }
  button[data-testid="stSidebarCollapseButton"],
  [data-testid="stSidebarCollapseButton"] button {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    width: 40px !important;
    height: 40px !important;
    background: rgba(245,166,35,.15) !important;
    color: #f4f6f8 !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0 !important;
    cursor: pointer !important;
  }
  [data-testid="stSidebarCollapseButton"] span,
  [data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"] {
    color: #f4f6f8 !important;
    font-size: 22px !important;
  }

  /* ── Gauges Plotly: 3 → 1 por fila ── */
  [data-testid="stColumn"]:has([data-testid="stPlotlyChart"]) {
    min-width: 100% !important;
    max-width: 100% !important;
    flex: none !important;
    margin-bottom: 6px !important;
  }

  /* ── Tablas: scroll horizontal ── */
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

/* ── Expander global — paleta del tema activo ── */
[data-testid="stExpander"] {
    background: var(--bg-tarjeta) !important;
    border: 1px solid var(--borde) !important;
}
[data-testid="stExpander"] summary {
    background: var(--bg-tarjeta) !important;
    color: var(--texto) !important;
}
[data-testid="stExpander"] > div {
    background: var(--bg-tarjeta) !important;
}

/* ── Inputs globales — paleta del tema activo ── */
[data-testid="stSelectbox"] > div > div {
    background: var(--bg-tarjeta) !important;
    border: 1px solid var(--borde) !important;
    color: var(--texto) !important;
}
[data-testid="stSelectbox"] > div > div > div {
    color: var(--texto) !important;
}
input[data-testid="stNumberInputField"],
[data-testid="stTextInput"] input {
    background: var(--bg-tarjeta) !important;
    border: 1px solid var(--borde) !important;
    color: var(--texto) !important;
}

/* ── Header nativo completamente oculto — hero en área de contenido ── */
section[data-testid="stMain"] {
    padding-top: 0 !important;
    margin-top: 0 !important;
}
[data-testid="stMainBlockContainer"],
.block-container {
    padding-top: 0 !important;
    margin-top: 0 !important;
    overflow-x: hidden !important;
}
</style>
"""

st.markdown(ESTILOS_CSS, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────
#  TEMAS VISUALES — estilo DeOP Connect (claro / oscuro)
# ─────────────────────────────────────────────────────────────────────
NOMBRES_TEMAS = ["DeOP Claro", "DeOP Oscuro", "Codere", "BetVision"]

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
    --acento-verde-rgb:  22,163,74;
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
    --acento-verde-rgb:  34,197,94;
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

    "BetVision": """
<style>
/* BetVision AI — azul profundo + naranja inteligente */
:root {
    --bg-principal:      #0F172A;
    --bg-tarjeta:        #1E293B;
    --borde:             #334155;
    --borde-activo:      #2563EB;
    --texto:             #E2E8F0;
    --texto-apagado:     #94A3B8;
    --acento-verde:      #16A34A;
    --acento-verde-rgb:  22,163,74;
    --acento-morado:     #60A5FA;
    --acento-dorado:     #F59E0B;
    --acento-dorado-rgb: 245,158,11;
    --acento-azul:       #2563EB;
    --acento-rojo:       #EF4444;
    --bg-elemento:       #0F172A;
    --bg-alerta-exito:   #052e16;
    --bg-alerta-peligro: #450a0a;
    --bg-alerta-aviso:   #422006;
    --boton-bg:          linear-gradient(135deg, #2563EB, #1D4ED8);
    --logo-color:        #2563EB;
}
html, body,
[data-testid="stApp"],
[data-testid="stAppViewContainer"] { background-color: #0F172A !important; color: #E2E8F0 !important; }
[data-testid="stHeader"]           { background-color: #0F172A !important; }
[data-testid="stSidebar"]          { background-color: #102B3F !important; }
.tarjeta {
    background-color: #1E293B !important;
    border-color: #334155 !important;
    color: #E2E8F0 !important;
}
.titulo-tarjeta {
    background: #1E293B !important;
    color: #60A5FA !important;
    border-bottom: 2px solid #2563EB !important;
    margin: -14px -16px 10px -16px !important;
    padding: 8px 16px 7px !important;
    border-radius: 10px 10px 0 0 !important;
}
[data-testid="metric-container"] { background-color: #1E293B !important; border: 1px solid #334155 !important; }
.stButton > button,
.stFormSubmitButton > button {
    background: linear-gradient(135deg, #2563EB, #1D4ED8) !important;
    color: #ffffff !important;
}
.stButton > button:hover,
.stFormSubmitButton > button:hover {
    background: #1D4ED8 !important;
    opacity: 1 !important;
    color: #ffffff !important;
}
.deop-categoria { color: #2563EB !important; }
.caja-stat  { background: rgba(37,99,235,0.08) !important; border-color: rgba(37,99,235,0.25) !important; }
.stat-valor { color: #E2E8F0 !important; }
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
    --acento-verde-rgb:  0,230,118;
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

# Hamburguesa mobile via component HTML (srcdoc = mismo origen → parent.document accesible).
# stApp tiene position:absolute + overflow:hidden que atrapa position:fixed de sus hijos,
# por eso el botón se crea en parent.document.body (fuera del clip).
import streamlit.components.v1 as _stc
_stc.html("""
<script>
(function(){
  var p = window.parent;
  if (!p || !p.document) return;
  if (p.innerWidth >= 768) return;

  function _init(){
    // Siempre eliminar y recrear #jbl-hbg: en cada re-run de Streamlit React
    // desmonta y remonta los elementos del DOM, así que cualquier referencia
    // a nb capturada en un closure anterior queda obsoleta (nodo detached).
    var old = p.document.getElementById('jbl-hbg');
    if (old) old.parentNode.removeChild(old);

    var nb = p.document.querySelector('[data-testid="stExpandSidebarButton"]');
    if (!nb) { setTimeout(_init, 400); return; }

    var btn = p.document.createElement('button');
    btn.id = 'jbl-hbg';
    btn.textContent = '☰';
    btn.style.cssText =
      'position:fixed;top:10px;left:10px;z-index:9999999;' +
      'width:44px;height:44px;background:#0d3b4f;color:#f4f6f8;border:none;' +
      'border-radius:8px;font-size:20px;cursor:pointer;' +
      'display:flex;align-items:center;justify-content:center;' +
      'box-shadow:0 2px 10px rgba(0,0,0,.45);';

    // Late binding: buscar nb fresco en cada clic (no capturar referencia)
    btn.onclick = function(){
      var n = p.document.querySelector('[data-testid="stExpandSidebarButton"]');
      if (n) n.click();
    };
    p.document.body.appendChild(btn);

    // MutationObserver: desconectar el anterior y crear uno nuevo con sb fresco
    if (p._jbl_mo) { p._jbl_mo.disconnect(); }
    var sb = p.document.querySelector('[data-testid="stSidebar"]');
    if (sb) {
      p._jbl_mo = new MutationObserver(function(){
        var b = p.document.getElementById('jbl-hbg');
        if (b) b.style.display = (sb.getAttribute('aria-expanded') === 'true') ? 'none' : 'flex';
      });
      p._jbl_mo.observe(sb, {attributes: true});
    }

    // Listener "click fuera = cerrar sidebar": solo añadir UNA vez (flag en parent.window)
    if (!p._jbl_cl) {
      p._jbl_cl = function(ev){
        if (p.innerWidth >= 768) return;
        var s = p.document.querySelector('[data-testid="stSidebar"]');
        if (!s || s.getAttribute('aria-expanded') === 'false') return;
        if (s.contains(ev.target)) return;
        var h = p.document.getElementById('jbl-hbg');
        if (h && h.contains(ev.target)) return;
        var cb = p.document.querySelector('[data-testid="stSidebarCollapseButton"]');
        if (cb) cb.click();
      };
      p.document.addEventListener('click', p._jbl_cl, true);
    }
  }

  setTimeout(_init, 800);
})();
</script>
""", height=0, scrolling=False)

# Forzar padding-top:0 en el bloque principal desde el iframe (JS en contexto del padre).
_stc.html("""
<script>
(function(){
  var p = window.parent;
  if (!p || !p.document) return;
  function _fix(){
    if (!p.document.getElementById('jbl-notop')) {
      var s = p.document.createElement('style');
      s.id = 'jbl-notop';
      s.textContent =
        'section[data-testid="stMain"]{padding-top:0!important;}' +
        '[data-testid="stMainBlockContainer"]{padding-top:0!important;}' +
        '.block-container{padding-top:0!important;}';
      p.document.head.appendChild(s);
    }
    var m = p.document.querySelector('section[data-testid="stMain"]');
    if (m) { m.style.setProperty('padding-top','0','important'); }
    var bc = p.document.querySelector('[data-testid="stMainBlockContainer"]') ||
             p.document.querySelector('.block-container');
    if (bc) { bc.style.setProperty('padding-top','0','important'); }
  }
  _fix();
  setTimeout(_fix, 400);
  setTimeout(_fix, 1200);
})();
</script>
""", height=0, scrolling=False)


# ─────────────────────────────────────────────────────────────────────
#  ESTADO DE SESIÓN — valores por defecto
# ─────────────────────────────────────────────────────────────────────
# st.session_state es como la "memoria" de la app entre interacciones.
# Streamlit recarga el script completo en cada clic, y session_state
# permite recordar qué página está activa, qué partido se analiza, etc.

_config_inicial = _cargar_config()   # Leemos configuración guardada en disco

# Tema guardado en config.json de una versión anterior (p.ej. "Azul Profesional")
# ya no es válido tras el rediseño DeOP — si no coincide con NOMBRES_TEMAS, usar default.
_tema_guardado = _config_inicial.get("tema", "BetVision")
if _tema_guardado not in NOMBRES_TEMAS:
    _tema_guardado = "BetVision"

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

# Restaurar estado persistido ANTES de aplicar defaults (el archivo tiene prioridad)
_cargar_estado_sesion()

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
        ("⚽", "Análisis Primera Parte"),      # Calculadora de mercados HT — módulo independiente
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
    # ── Logo BetVision AI ───────────────────────────────────────────────
    st.markdown(
        '<div style="padding:18px 4px 14px 4px;">'
        '<div style="font-size:21px;font-weight:700;line-height:1;margin-bottom:5px;">'
        '<span style="color:#ffffff;">⚽ BetVision</span>'
        '<span style="color:var(--acento-dorado,#F59E0B);"> AI</span>'
        '</div>'
        '<div style="font-size:9px;font-weight:600;color:rgba(255,255,255,.38);'
        'letter-spacing:2.5px;text-transform:uppercase;">Professional Football Analytics</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── Mapeo fijo ruta→key ASCII (sin acentos, sin espacios) ──────────
    _NAV_KEYS: dict[str, str] = {
        "Análisis de Partidos":   "nav_dashboard",
        "Análisis Primera Parte": "nav_primera_parte",
        "Agregar Partido":        "nav_analisis",
        "Claude AI":              "nav_nuevo",
        "Modelo Predictivo":      "nav_prediccion",
        "Comparación de Cuotas":  "nav_cuotas",
        "Análisis en Vivo":       "nav_vivo",
        "Apuesta Dominada":       "nav_apuestas",
        "Historial Dominada":     "nav_historial",
        "Historial Análisis Claude": "nav_stats",
        "Alertas y Retiradas":    "nav_alertas",
        "Configuración":          "nav_config",
    }

    # ── CSS botón activo ─────────────────────────────────────────────────
    # El reset base usa [data-testid='stSidebar'] .stButton > button (especificidad 0,1,1,1).
    # Añadimos .stButton al selector activo → 0,1,2,1: siempre gana aunque ambos tengan !important.
    _pagina_nav   = st.session_state.get("pagina_activa", "Análisis de Partidos")
    _key_activo   = _NAV_KEYS.get(_pagina_nav, "nav_dashboard")
    _css_activo = (
        f"[data-testid='stSidebar'] .st-key-{_key_activo} .stButton > button {{"
        f"  background: #2563EB !important;"
        f"  color: #ffffff !important;"
        f"  font-weight: 600 !important;"
        f"  border-radius: 8px !important;"
        f"  opacity: 1 !important;"
        f"}}"
        f"[data-testid='stSidebar'] .st-key-{_key_activo} .stButton > button p {{"
        f"  color: #ffffff !important;"
        f"}}"
        f"[data-testid='stSidebar'] .st-key-{_key_activo} .stButton > button:hover {{"
        f"  background: #1D4ED8 !important;"
        f"}}"
    )
    st.markdown(f"<style>{_css_activo}</style>", unsafe_allow_html=True)

    # ── Iconos SVG Lucide via CSS ::before ─────────────────────────────
    def _svg_uri(inner: str) -> str:
        full = (
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'"
            " fill='none' stroke='rgba(255,255,255,.72)'"
            " stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>"
            + inner + "</svg>"
        )
        encoded = full.replace("%", "%25").replace("<", "%3C").replace(">", "%3E").replace('"', "%22").replace("#", "%23")
        return f"url(\"data:image/svg+xml,{encoded}\")"

    _NAV_ICONS: dict[str, str] = {
        "nav_dashboard":   _svg_uri("<path d='M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z'/><polyline points='9 22 9 12 15 12 15 22'/>"),
        "nav_primera_parte": _svg_uri("<circle cx='12' cy='12' r='10'/><path d='M12 2a15.3 15.3 0 0 0 0 20'/><path d='M2 12h20'/>"),
        "nav_analisis":    _svg_uri("<line x1='18' y1='20' x2='18' y2='10'/><line x1='12' y1='20' x2='12' y2='4'/><line x1='6' y1='20' x2='6' y2='14'/>"),
        "nav_nuevo":       _svg_uri("<path d='M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z'/>"),
        "nav_prediccion":  _svg_uri("<circle cx='12' cy='12' r='10'/><circle cx='12' cy='12' r='6'/><circle cx='12' cy='12' r='2'/>"),
        "nav_cuotas":      _svg_uri("<polyline points='22 7 13.5 15.5 8.5 10.5 2 17'/><polyline points='16 7 22 7 22 13'/>"),
        "nav_vivo":        _svg_uri("<polygon points='13 2 3 14 12 14 11 22 21 10 12 10 13 2'/>"),
        "nav_apuestas":    _svg_uri("<polygon points='12 2 2 7 12 12 22 7 12 2'/><polyline points='2 17 12 22 22 17'/><polyline points='2 12 12 17 22 12'/>"),
        "nav_historial":   _svg_uri("<path d='M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z'/>"),
        "nav_stats":       _svg_uri("<path d='M3 3v18h18'/><path d='m19 9-5 5-4-4-3 3'/>"),
        "nav_alertas":     _svg_uri("<path d='M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9'/><path d='M10.3 21a1.94 1.94 0 0 0 3.4 0'/>"),
        "nav_config":      _svg_uri("<circle cx='12' cy='12' r='3'/><path d='M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z'/>"),
    }

    _icon_css = "".join(
        f"[data-testid='stSidebar'] .st-key-{k} button p::before{{"
        f"content:'';display:inline-block;width:14px;height:14px;"
        f"margin-right:8px;vertical-align:middle;flex-shrink:0;"
        f"background:{v} no-repeat center/contain;}}"
        for k, v in _NAV_ICONS.items()
    )
    st.markdown(f"<style>{_icon_css}</style>", unsafe_allow_html=True)

    # ── Grupo 1 — Análisis ──────────────────────────────────────────────
    st.markdown('<div class="deop-categoria">ANÁLISIS</div>', unsafe_allow_html=True)
    _NAV_G1 = [
        ("Dashboard",             "Análisis de Partidos"),
        ("Análisis Primera Parte", "Análisis Primera Parte"),
        ("Análisis de Partidos",  "Agregar Partido"),
        ("Nuevo Análisis",        "Claude AI"),
        ("Predicción con IA",     "Modelo Predictivo"),
        ("Comparación de Cuotas", "Comparación de Cuotas"),
        ("Análisis en Vivo",      "Análisis en Vivo"),
    ]
    for _lbl, _ruta in _NAV_G1:
        if st.button(_lbl, key=_NAV_KEYS[_ruta],
                     use_container_width=True, type="secondary"):
            st.session_state.pagina_activa = _ruta
            st.rerun()

    # ── Grupo 2 — Gestión ───────────────────────────────────────────────
    st.markdown('<div class="deop-categoria">GESTIÓN</div>', unsafe_allow_html=True)
    _NAV_G2 = [
        ("Apuestas",      "Apuesta Dominada"),
        ("Historial",     "Historial Dominada"),
        ("Estadísticas",  "Historial Análisis Claude"),
        ("Alertas",       "Alertas y Retiradas"),
        ("Configuración", "Configuración"),
    ]
    for _lbl, _ruta in _NAV_G2:
        if st.button(_lbl, key=_NAV_KEYS[_ruta],
                     use_container_width=True, type="secondary"):
            st.session_state.pagina_activa = _ruta
            st.rerun()

    st.markdown(
        '<hr style="border:none;border-top:1px solid rgba(255,255,255,.08);margin:6px 0">',
        unsafe_allow_html=True,
    )

    # ── Estadísticas personales ─────────────────────────────────────────
    _stats     = _stats_historial()
    _gan       = _stats["ganancias_netas"]
    _col_gan   = "#16A34A" if _gan >= 0 else "#EF4444"
    _gan_txt   = f"{'+'if _gan>=0 else ''}€{_gan}"
    _racha_txt = f"{_stats['racha']}W" if _stats["racha"] > 0 else "—"

    _c1, _c2, _c3 = st.columns(3)
    with _c1:
        st.markdown(
            f'<div class="caja-stat"><div class="stat-etiqueta">Apuestas</div>'
            f'<div class="stat-valor" style="color:#E2E8F0;">{_stats["apuestas_totales"]}</div></div>',
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
            f'<div class="stat-valor" style="color:#60A5FA;">{_racha_txt}</div></div>',
            unsafe_allow_html=True,
        )

    st.number_input(
        "Saldo (€):",
        min_value=0.0, max_value=999999.0,
        value=float(st.session_state["saldo"]),
        step=10.0, key="input_saldo",
        on_change=_guardar_saldo,
    )

    st.markdown(
        '<hr style="border:none;border-top:1px solid rgba(255,255,255,.08);margin:6px 0">',
        unsafe_allow_html=True,
    )

    # ── Actualizar partidos reales ──────────────────────────────────────
    if st.button("🔄 Actualizar partidos", key="btn_actualizar",
                 use_container_width=True, type="secondary"):
        from modules.odds_api import actualizar_datos
        from datetime import datetime as _dt
        with st.spinner("Conectando..."):
            try:
                n, mensaje, stats = actualizar_datos()
                st.cache_data.clear()
                st.session_state["debug_ligas"]      = stats
                st.session_state["debug_mensaje"]    = (mensaje, "ok" if n > 0 else "info")
                st.session_state["debug_timestamp"]  = _dt.now().strftime("%d/%m/%Y %H:%M:%S")
                st.session_state["debug_total"]      = n
                if n > 0:
                    st.session_state["analisis_listo"] = False
                    st.session_state.pop("claude_analisis", None)
            except RuntimeError as exc:
                st.session_state["debug_mensaje"] = (str(exc), "error")
                st.session_state.pop("debug_ligas", None)

    if _dmsg := st.session_state.get("debug_mensaje"):
        _txt, _tipo = _dmsg
        _col = "#16A34A" if _tipo == "ok" else ("#EF4444" if _tipo == "error" else "#555555")
        st.markdown(
            f'<div style="font-size:11px;color:{_col};padding:3px 4px;'
            f'margin:2px 0;border-left:3px solid {_col};padding-left:7px;">'
            f'{_txt}</div>',
            unsafe_allow_html=True,
        )

    _debug       = st.session_state.get("debug_ligas", [])
    _debug_ts    = st.session_state.get("debug_timestamp", "—")
    _debug_total = st.session_state.get("debug_total", 0)
    _debug_ok    = [r for r in _debug if r["estado"] == "OK"]

    if _debug:
        with st.expander(
            f"🔧 Debug API · {len(_debug_ok)} OK · {_debug_total} partidos",
            expanded=False,
        ):
            st.markdown(
                f'<div style="font-size:10px;color:#888;margin-bottom:6px;">'
                f'Última actualización: <b>{_debug_ts}</b></div>',
                unsafe_allow_html=True,
            )
            filas_debug = []
            for row in _debug:
                if row["estado"] == "OK":
                    _ic, _c = "✅", "#16A34A"
                    _d = f"{row['partidos']} partidos"
                else:
                    _ic, _c = "○", "#888888"
                    _d = row["estado"]
                filas_debug.append(
                    f'<div style="font-size:10px;color:{_c};padding:2px 0;">'
                    f'{_ic} <b>{row["liga"]}</b> — {_d}</div>'
                )
            _espn_n = st.session_state.get("espn_partidos_cargados", 0)
            if _espn_n:
                filas_debug.append(
                    f'<div style="font-size:10px;color:#60A5FA;padding:2px 0;">'
                    f'✅ <b>ESPN</b> — {_espn_n} partidos</div>'
                )
            _fuente_xg_act = st.session_state.get("fuente_xg_activa")
            if _fuente_xg_act:
                _badge_map = {
                    "estimado": "📊 xG: Estimado",
                    "manual":   "✏️ xG: Manual",
                    "api":      "📡 xG: API",
                }
                filas_debug.append(
                    f'<div style="font-size:10px;color:#F59E0B;padding:4px 0 0;">'
                    f'Partido activo → {_badge_map.get(_fuente_xg_act, _fuente_xg_act)}</div>'
                )
            st.markdown("".join(filas_debug), unsafe_allow_html=True)

    if st.button("🔍 Escanear valor hoy", key="btn_scan_valor",
                 use_container_width=True, type="secondary"):
        st.session_state["pagina_activa"] = "Escáner de Valor"
        st.session_state["scan_trigger"]  = True
        st.rerun()

    if st.button("🗑️ Nuevo análisis", key="btn_nuevo_analisis",
                 use_container_width=True, type="secondary",
                 help="Limpia el análisis actual y el estado guardado"):
        _limpiar_estado_sesion()
        st.rerun()

    st.markdown(
        '<hr style="border:none;border-top:1px solid rgba(255,255,255,.08);margin:6px 0">',
        unsafe_allow_html=True,
    )

    with st.expander("⚙️ Fuentes de datos", expanded=False):
        st.markdown(
            '<div style="font-size:10px;color:#94A3B8;margin-bottom:6px;">'
            'Activa o desactiva cada fuente.</div>',
            unsafe_allow_html=True,
        )
        for k, v in [("fuente_odds", True), ("fuente_espn", True), ("fuente_logos", True)]:
            if k not in st.session_state:
                st.session_state[k] = v
        st.checkbox("📡 The Odds API (cuotas)",       key="fuente_odds",
                    help="Obtiene partidos y cuotas reales para calcular edge")
        st.checkbox("🏟️ ESPN (partidos adicionales)", key="fuente_espn",
                    help="Añade partidos de ESPN a la lista (sin cuotas)")
        st.checkbox("🖼️ TheSportsDB (logos)",         key="fuente_logos",
                    help="Muestra logos de equipos junto a los nombres")
        if st.session_state.get("fuente_espn", True):
            if st.button("Cargar partidos ESPN", key="btn_espn",
                         use_container_width=True):
                from modules.espn_api import actualizar_con_espn
                with st.spinner("Cargando partidos de ESPN..."):
                    n, msg = actualizar_con_espn()
                if n > 0:
                    st.session_state["espn_partidos_cargados"] = n
                st.success(msg) if n > 0 else st.info(msg)

    st.markdown(
        '<hr style="border:none;border-top:1px solid rgba(255,255,255,.08);margin:6px 0">',
        unsafe_allow_html=True,
    )

    st.toggle(
        "🔬 Modo Observación",
        key="modo_observacion",
        help="Sin dinero real — registra análisis como apuestas virtuales para seguimiento",
    )
    if st.session_state.get("modo_observacion"):
        st.markdown(
            '<div style="font-size:10px;color:#16A34A;background:rgba(22,163,74,.08);'
            'border:1px solid rgba(22,163,74,.3);border-radius:4px;padding:4px 8px;margin-top:4px;">'
            '🔬 Modo activo — sin riesgo real</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div style="font-size:10px;color:rgba(255,255,255,.4);font-weight:600;'
        'text-transform:uppercase;letter-spacing:1px;margin:8px 0 3px 0;">Tema Visual</div>',
        unsafe_allow_html=True,
    )

    def _cambiar_tema():
        st.session_state["tema_activo"] = st.session_state["sel_tema"]
        _guardar_tema()

    idx_actual = NOMBRES_TEMAS.index(st.session_state.get("tema_activo", "BetVision"))
    st.selectbox(
        "Tema:",
        NOMBRES_TEMAS,
        index=idx_actual,
        key="sel_tema",
        label_visibility="collapsed",
        on_change=_cambiar_tema,
    )

    # ── Tarjeta de perfil ───────────────────────────────────────────────
    st.markdown(
        '<div style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);'
        'border-radius:10px;padding:12px 14px;margin-top:14px;">'
        '<div style="display:flex;align-items:center;gap:10px;">'
        '<div style="width:40px;height:40px;border-radius:50%;'
        'background:linear-gradient(135deg,var(--acento-azul,#2563EB),#1D4ED8);'
        'display:flex;align-items:center;justify-content:center;'
        'font-size:14px;font-weight:700;color:#fff;flex-shrink:0;'
        'letter-spacing:-.5px;">JB</div>'
        '<div style="flex:1;min-width:0;">'
        '<div style="display:flex;align-items:center;gap:6px;margin-bottom:3px;">'
        '<span style="color:#E2E8F0;font-size:13px;font-weight:600;'
        'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">JhonBet</span>'
        '<span style="background:var(--acento-azul,#2563EB);color:#fff;'
        'font-size:9px;font-weight:700;letter-spacing:.8px;'
        'padding:1px 6px;border-radius:3px;flex-shrink:0;">PRO</span>'
        '</div>'
        '<div style="color:rgba(255,255,255,0.4);font-size:10px;font-weight:400;">'
        'Plan Profesional</div>'
        '</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────
#  HERO BANNER — imagen de estadio + degradado + título + botones
# ─────────────────────────────────────────────────────────────────────
# background-image via <style> + clase CSS (DOMPurify sanitiza data: URIs
# en atributos style inline pero los permite dentro de bloques <style>)
import base64 as _b64mod
_estadio_path = Path(__file__).parent / "assets" / "estadio-jugadores.png"


@st.cache_data
def _leer_imagen_b64(ruta: str) -> str:
    """Lee y codifica en base64 una imagen — se ejecuta en TODAS las páginas
    (el hero banner está antes del enrutamiento), cachear evita releer el
    archivo y recodificarlo en cada rerun."""
    return _b64mod.b64encode(Path(ruta).read_bytes()).decode()


if _estadio_path.exists():
    _estadio_b64 = _leer_imagen_b64(str(_estadio_path))
    st.markdown(
        f'<style>.jbl-hero{{background-image:url("data:image/png;base64,{_estadio_b64}");'
        f'background-size:cover;background-position:center;}}</style>',
        unsafe_allow_html=True,
    )

st.markdown(
    f'<div class="jbl-hero" style="margin:0 -3rem 20px;width:calc(100% + 6rem);min-height:320px;'
    f'position:relative;overflow:hidden;background-color:#0F172A;">'
    # gradient overlay
    f'<div style="position:absolute;inset:0;'
    f'background:linear-gradient(90deg,rgba(8,12,25,0.93) 0%,rgba(8,12,25,0.68) 45%,rgba(8,12,25,0.12) 100%);"></div>'
    # content
    f'<div style="position:relative;z-index:2;padding:56px 52px 52px;max-width:600px;">'
    # BETVISION AI title
    f'<div style="font-family:Poppins,sans-serif;font-size:40px;font-weight:700;color:#ffffff;'
    f'line-height:1.1;letter-spacing:-0.5px;margin-bottom:10px;">'
    f'BETVISION <span style="color:#F59E0B;">AI</span></div>'
    # subtitle
    f'<div style="font-size:10px;font-weight:700;color:rgba(255,255,255,0.5);'
    f'letter-spacing:3.5px;text-transform:uppercase;margin-bottom:14px;">'
    f'PROFESSIONAL FOOTBALL ANALYTICS</div>'
    # tagline
    f'<div style="font-size:16px;font-style:italic;color:rgba(255,255,255,0.78);margin-bottom:32px;">'
    f'Analyze. Predict. Win.</div>'
    f'</div>'
    f'</div>',
    unsafe_allow_html=True,
)

_hero_c1, _hero_c2, _hero_c3 = st.columns([1, 1, 5])
with _hero_c1:
    if st.button("⚽ Analizar con IA", key="hero_btn_ia", use_container_width=True):
        st.session_state["pagina_activa"] = "Claude AI"
        st.rerun()
with _hero_c2:
    if st.button("📊 Ver Dashboard", key="hero_btn_dashboard", use_container_width=True):
        st.session_state["pagina_activa"] = "Análisis de Partidos"
        st.rerun()

# ─────────────────────────────────────────────────────────────────────
#  KPI CARDS — virtual_bets.csv (ROI, Beneficio, Win Rate, Yield, Total, Pérdidas)
# ─────────────────────────────────────────────────────────────────────
_kpi_cards_virtual()

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

elif pagina == "Análisis Primera Parte":
    from modules.first_half_analysis import mostrar as mostrar_primera_parte
    mostrar_primera_parte()

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

elif pagina == "Configuración":
    st.markdown(
        '<div style="max-width:520px;margin:60px auto;text-align:center;">'
        '<div style="font-size:48px;margin-bottom:16px;">⚙️</div>'
        '<div style="font-size:22px;font-weight:700;color:var(--texto);margin-bottom:8px;">'
        'Configuración</div>'
        '<div style="font-size:14px;color:var(--texto-apagado);">'
        'Próximamente — ajustes de cuenta, preferencias y notificaciones.</div>'
        '</div>',
        unsafe_allow_html=True,
    )

# ── Guardar estado de trabajo al final de cada ejecución ──────────────────────
_guardar_estado_sesion()
