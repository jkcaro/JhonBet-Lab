"""Módulo: Página principal "Análisis de Partidos" — layout estilo DeOP Connect.

Solo presentación: selecciona el partido (reutiliza modules.analysis tal cual)
y dispara los 4 análisis de Claude ya existentes por mercado
(modules.claude_analysis.analizar_4_mercados), sin tocar ninguna fórmula de
cálculo. Las 4 tarjetas, los 3 gauges, el cuadro de info y la tabla de
historial solo presentan datos ya calculados.
"""

import streamlit as st
import anthropic

from modules import analysis as _analysis_mod
from modules import claude_analysis as _ca
from modules import claude_history as _history_mod
from modules.scada_charts import (
    gauge_donut_gris, tarjeta_veredicto_html, panel_info_partido_html,
    tabla_ultimos_analisis_html, semaforo_html, DEOP_DORADO, DEOP_PETROLEO, DEOP_VERDE,
)

_CONF_NUM = {"Alto": 85.0, "Medio": 50.0, "Bajo": 18.0}

_MAPA_CLAVE_P = {"Local": "p_local", "Empate": "p_empate", "Visitante": "p_visitante"}


def _tarjeta_de(mercado: str, resultado: dict) -> str:
    """Construye la tarjeta amarilla para un mercado a partir de su resultado."""
    punt   = resultado["puntuacion"]
    datos_m = resultado["datos"]
    estado = punt.get("estado", "NO APOSTAR")

    if mercado == "Victoria 1X2":
        titulo = "Victoria 1X2"
        v1x2   = datos_m.get("victoria1x2_modelo", {})
        valor  = v1x2.get("mejor_seleccion", "—")
    elif "Ambos Marcan" in mercado:
        titulo = "Ambos Marcan"
        btts   = datos_m.get("btts_si_modelo", {})
        try:
            p_si = float(str(btts.get("p_btts_si", "0%")).replace("%", ""))
        except ValueError:
            p_si = 0.0
        valor = "Sí" if p_si >= 50 else "No"
    elif "Más de 1.5" in mercado or "Mas de 1.5" in mercado:
        titulo = "Más 1.5 Goles"
        p_modelo = datos_m.get("mas15_modelo", {}).get("p_mas15", "—")
        valor    = f"P: {p_modelo} | Edge: {punt.get('edge', 0.0):+.1f}%"
    else:
        titulo = "Menos 1.5 Goles"
        p_modelo = datos_m.get("menos15_modelo", {}).get("p_menos15", "—")
        valor    = f"P: {p_modelo} | Edge: {punt.get('edge', 0.0):+.1f}%"

    return tarjeta_veredicto_html(titulo, valor, estado)


def mostrar() -> None:
    """Renderiza la página 'Análisis de Partidos' con el layout DeOP Connect."""

    # ── CSS: expander/selectbox/botón del formulario de selección — 36px máx ──
    # Scopeado por key al expander "Seleccionar partido" (no al expander
    # "⚙️ Fuentes de datos" del sidebar ni a otros botones de la página,
    # como "Analizar con Claude AI").
    st.markdown(
        """
<style>
/* Header del expander (el banner negro "🔍 Seleccionar partido") */
.st-key-expander_seleccionar_partido summary {
    min-height: 36px !important;
    max-height: 36px !important;
    height: 36px !important;
    padding-top: 0 !important;
    padding-bottom: 0 !important;
}

/* Selectbox Liga / Partido */
.st-key-expander_seleccionar_partido [data-testid="stSelectbox"] [data-baseweb="select"] > div {
    min-height: 36px !important;
    max-height: 36px !important;
    padding-top: 0 !important;
    padding-bottom: 0 !important;
}
.st-key-expander_seleccionar_partido [data-testid="stSelectbox"] [data-baseweb="select"] > div > div {
    padding: 2px 8px !important;
}

/* Botón "Analizar Partido" */
.st-key-expander_seleccionar_partido [data-testid="stButton"] > button {
    height: 36px !important;
    min-height: 36px !important;
    max-height: 36px !important;
    padding: 3px 16px !important;
    font-size: 13px !important;
    font-weight: 700 !important;
}

/* Espaciado entre bloques (Liga → Partido → botón) — de 16px a 4px */
.st-key-expander_seleccionar_partido div[data-testid="stVerticalBlock"] {
    gap: 4px !important;
}

/* Label pegado al control — de 4px a 1px */
.st-key-expander_seleccionar_partido [data-testid="stWidgetLabel"] {
    margin-bottom: 1px !important;
}

/* Labels legibles sobre fondo claro (p. ej. "Liga:", "Partido:", "Forma reciente...") */
[data-testid="stWidgetLabel"] p {
    color: #0d3b4f !important;
    font-weight: 600 !important;
}
</style>
""",
        unsafe_allow_html=True,
    )

    with st.expander(
        "🔍 Seleccionar partido",
        expanded=not bool(st.session_state.get("analisis_listo")),
        key="expander_seleccionar_partido",
    ):
        _analysis_mod.mostrar()

    datos = _ca._datos_desde_sesion()

    if not datos:
        st.markdown(
            '<div style="color:#8aaa99;font-size:13px;padding:12px 0;">'
            'Selecciona un partido arriba y pulsa <b>Analizar Partido</b> '
            'para activar el dashboard.</div>',
            unsafe_allow_html=True,
        )
        return

    partido = datos.get("partido", "")

    filiales = _ca._detectar_filiales(partido)
    if filiales:
        for equipo in filiales:
            st.markdown(
                f'<div style="background:#1a0404;border:2px solid #ef5350;'
                f'border-radius:8px;padding:10px 16px;margin:4px 0;'
                f'font-size:13px;font-weight:700;color:#ef5350;">'
                f'⛔ Equipo filial — análisis bloqueado: <b>{equipo}</b></div>',
                unsafe_allow_html=True,
            )
        return

    # ── Banner petróleo: partido activo ────────────────────────────────────────
    st.markdown(
        f'<div style="background:{DEOP_PETROLEO};border-radius:8px;'
        f'padding:10px 18px;margin-bottom:10px;display:flex;align-items:center;'
        f'justify-content:space-between;">'
        f'<span style="color:#ffffff;font-size:15px;font-weight:800;'
        f'letter-spacing:.3px;">⚽ {partido}</span>'
        f'<span style="color:{DEOP_DORADO};font-size:11px;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:1px;">Partido en análisis</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Forma reciente + botón único de análisis ───────────────────────────────
    col_fl, col_fv = st.columns(2)
    with col_fl:
        forma_local = st.text_input(
            "Forma reciente local (últimos 5)*",
            placeholder="Ej: W,W,D,L,W", key="dash_forma_local",
        )
    with col_fv:
        forma_visit = st.text_input(
            "Forma reciente visitante (últimos 5)*",
            placeholder="Ej: L,D,W,W,L", key="dash_forma_visit",
        )
    # Se guardan en `datos` siempre (no solo al pulsar Analizar) para que el
    # cuadro de info del partido los muestre incluso antes/después del rerun.
    datos["forma_reciente_local"]     = forma_local.strip()
    datos["forma_reciente_visitante"] = forma_visit.strip()

    _forma_completa = bool(forma_local.strip()) and bool(forma_visit.strip())
    if not _forma_completa:
        st.caption("⚠️ Completa la forma reciente de ambos equipos para habilitar el análisis.")

    if st.button("🤖 Analizar con Claude AI (4 mercados)", key="btn_analizar_dashboard",
                 use_container_width=True, disabled=not _forma_completa):
        _status = st.empty()
        _ok = False
        with st.spinner("Analizando 4 mercados con Claude AI…"):
            try:
                _status.caption("⏳ Analizando 4 mercados (Victoria 1X2, Ambos Marcan, Más/Menos 1.5)…")
                resultados = _ca.analizar_4_mercados(datos)
                st.session_state["match_dashboard_resultados"] = resultados
                st.session_state["match_dashboard_partido"]    = partido
                for mercado, r in resultados.items():
                    try:
                        _ca._guardar_historial_claude(r["datos"], r["puntuacion"], r["texto"])
                    except Exception as _e_hist:
                        st.warning(f"⚠️ No se pudo guardar historial de '{mercado}': {_e_hist}")
                _ok = True
                _status.empty()
            except anthropic.AuthenticationError:
                _status.empty()
                st.error("API key inválida. Verifica ANTHROPIC_API_KEY.")
            except Exception as exc:
                _status.empty()
                st.error(f"Error en el análisis: {exc}")
        if _ok:
            st.rerun()

    resultados = st.session_state.get("match_dashboard_resultados")
    partido_analizado = st.session_state.get("match_dashboard_partido")

    if not resultados or partido_analizado != partido:
        st.caption("Pulsa **Analizar con Claude AI** para generar los 4 veredictos de este partido.")
        return

    # ── 4 tarjetas amarillas + semáforo circular de cada mercado ────────────────
    cols_cards = st.columns(4)
    for col, mercado in zip(cols_cards, _ca.MERCADOS_DASHBOARD):
        with col:
            st.markdown(_tarjeta_de(mercado, resultados[mercado]), unsafe_allow_html=True)
            _punt_m = resultados[mercado]["puntuacion"]
            st.markdown(semaforo_html(_punt_m.get("edge", 0.0), _punt_m), unsafe_allow_html=True)

    # ── 3 gauges donut grises ───────────────────────────────────────────────────
    edge_max     = max((r["puntuacion"].get("edge", 0.0) for r in resultados.values()), default=0.0)
    mercado_top  = max(resultados, key=lambda m: resultados[m]["puntuacion"].get("edge", 0.0))
    confianza_top = resultados[mercado_top]["puntuacion"].get("confianza", "Bajo")
    confianza_pct = _CONF_NUM.get(confianza_top, 18.0)

    v1x2       = resultados["Victoria 1X2"]["datos"].get("victoria1x2_modelo", {})
    mejor_sel  = v1x2.get("mejor_seleccion", "")
    clave_p    = _MAPA_CLAVE_P.get(mejor_sel, "")
    try:
        p_victoria = float(str(v1x2.get(clave_p, "0%")).replace("%", "")) if clave_p else 0.0
    except ValueError:
        p_victoria = 0.0

    cols_gauges = st.columns(3)
    with cols_gauges[0]:
        st.plotly_chart(gauge_donut_gris(max(0.0, edge_max), "Edge %", DEOP_DORADO),
                        use_container_width=True, config={"displayModeBar": False}, key="dash_gauge_edge")
    with cols_gauges[1]:
        st.plotly_chart(gauge_donut_gris(confianza_pct, "Confianza %", DEOP_PETROLEO),
                        use_container_width=True, config={"displayModeBar": False}, key="dash_gauge_conf")
    with cols_gauges[2]:
        st.plotly_chart(gauge_donut_gris(p_victoria, "P(Victoria) %", DEOP_VERDE),
                        use_container_width=True, config={"displayModeBar": False}, key="dash_gauge_pvic")

    # ── Cuadro info partido + tabla últimos análisis ────────────────────────────
    col_info, col_tabla = st.columns([1, 1.3])
    with col_info:
        st.markdown(panel_info_partido_html(datos), unsafe_allow_html=True)
    with col_tabla:
        st.markdown(tabla_ultimos_analisis_html(_history_mod._cargar(), limite=8),
                    unsafe_allow_html=True)
