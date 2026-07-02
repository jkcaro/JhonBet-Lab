"""Módulo: Página "Agregar Partido" — formulario completo estilo DeOP Connect.

Duplica el contenido del modal _dialogo_partido_manual() de analysis.py pero
como página normal (sin @st.dialog). El modal original sigue intacto en
analysis.py para no romper nada; simplemente ya no se llama desde el sidebar.
"""

import streamlit as st

from modules.analysis import _guardar_partido_manual, _cuota_val


# ── Sección de cabecera estilo DeOP ─────────────────────────────────────────
def _sec(titulo: str, opcional: bool = False) -> None:
    sfx = ' <span style="font-weight:400;opacity:.55;font-size:8px;">(opcional)</span>' if opcional else ""
    st.markdown(
        f'<div style="font-size:9px;font-weight:700;color:#0d3b4f;text-transform:uppercase;'
        f'letter-spacing:1.5px;margin:12px 0 4px 0;padding-bottom:3px;'
        f'border-bottom:1px solid #e2e8f0;">{titulo}{sfx}</div>',
        unsafe_allow_html=True,
    )


def mostrar() -> None:
    """Renderiza la página 'Agregar Partido' con layout DeOP Connect."""

    # ── CSS propio de la página ──────────────────────────────────────────────
    st.markdown(
        """
<style>
/* ── Inputs de la página Agregar Partido — tema DeOP claro ── */
div[data-testid="stAppViewContainer"] .stTextInput > div > div > input,
div[data-testid="stAppViewContainer"] .stNumberInput > div > div > input {
    background: #ffffff !important;
    border: 1px solid #d0dde8 !important;
    border-radius: 6px !important;
    color: #1a2c38 !important;
    font-size: 13px !important;
}
div[data-testid="stAppViewContainer"] .stTextInput > div > div > input:focus,
div[data-testid="stAppViewContainer"] .stNumberInput > div > div > input:focus {
    border-color: #f5a623 !important;
    box-shadow: 0 0 0 2px rgba(245,166,35,.18) !important;
}
div[data-testid="stAppViewContainer"] .stSelectbox > div > div {
    background: #ffffff !important;
    border: 1px solid #d0dde8 !important;
    border-radius: 6px !important;
    color: #1a2c38 !important;
    font-size: 13px !important;
}
div[data-testid="stAppViewContainer"] .stSelectbox > div > div:focus-within {
    border-color: #f5a623 !important;
}
</style>
""",
        unsafe_allow_html=True,
    )

    # ── Banner petróleo ──────────────────────────────────────────────────────
    st.markdown(
        '<div style="background:#0d3b4f;border-radius:8px;padding:12px 20px;'
        'margin-bottom:16px;display:flex;align-items:center;gap:12px;">'
        '<span style="font-size:20px;">⚽</span>'
        '<div>'
        '<div style="font-size:15px;font-weight:800;color:#ffffff;letter-spacing:.3px;">'
        'Nuevo Partido</div>'
        '<div style="font-size:11px;color:#aac4d4;margin-top:2px;">'
        'Busca en The Odds API o completa los datos manualmente</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── BÚSQUEDA EN THE ODDS API ─────────────────────────────────────────────
    _sec("Buscar equipo en The Odds API")
    col_t, col_b = st.columns([3, 1])
    with col_t:
        termino = st.text_input(
            "Equipo", placeholder="Ej: Real Madrid",
            key="pm_buscar", label_visibility="collapsed",
        )
    with col_b:
        buscar_click = st.button("🔍 Buscar", key="btn_buscar_equipo_pag",
                                 use_container_width=True)

    if buscar_click:
        if termino.strip():
            from modules.odds_api import buscar_por_equipo
            with st.spinner("Buscando partidos en The Odds API..."):
                resultados_api = buscar_por_equipo(termino.strip())
            st.session_state["pm_resultados"] = resultados_api
            for k in ("pm_match_sel", "pm_prefill"):
                st.session_state.pop(k, None)
        else:
            st.warning("Escribe el nombre de un equipo antes de buscar.")

    resultados_api = st.session_state.get("pm_resultados")
    if resultados_api is not None:
        if not resultados_api:
            st.caption("Sin resultados para ese equipo hoy.")
        else:
            opciones = ["-- Selecciona un partido --"] + [r["label"] for r in resultados_api]
            sel_label = st.selectbox("Partidos encontrados:", opciones, key="pm_sel_label")
            if sel_label != "-- Selecciona un partido --":
                if st.session_state.get("pm_match_sel") != sel_label:
                    idx = opciones.index(sel_label) - 1
                    st.session_state["pm_match_sel"] = sel_label
                    st.session_state["pm_prefill"]   = resultados_api[idx]
                    for k in ("pm_local", "pm_visitante", "pm_liga",
                              "pm_cl", "pm_ce", "pm_cv"):
                        st.session_state.pop(k, None)

    st.markdown("<hr style='border-color:#e2e8f0;margin:8px 0 4px'>",
                unsafe_allow_html=True)
    prefill = st.session_state.get("pm_prefill", {})

    # ── FILA 1 · Equipos + Liga (2 columnas: local|visitante / liga) ─────────
    _sec("Partido")
    col_lv, col_liga = st.columns([2, 1])
    with col_lv:
        col_l, col_v = st.columns(2)
        with col_l:
            equipo_local = st.text_input(
                "🏠 Equipo Local", value=prefill.get("equipo_local", ""),
                placeholder="Ej: Real Madrid", key="pm_local",
            )
        with col_v:
            equipo_visitante = st.text_input(
                "✈️ Equipo Visitante", value=prefill.get("equipo_visitante", ""),
                placeholder="Ej: Barcelona", key="pm_visitante",
            )
    with col_liga:
        liga = st.text_input(
            "🏆 Liga / Competición", value=prefill.get("liga", ""),
            placeholder="Ej: La Liga", key="pm_liga",
        )

    # ── FILA 2 · Cuotas 1X2 + xG ────────────────────────────────────────────
    _sec("Cuotas 1X2  ·  xG esperado")
    col_cl, col_ce, col_cv, col_xl, col_xv = st.columns(5)
    with col_cl:
        cuota_local = st.number_input(
            "Cuota 1 (Local)", min_value=1.01, max_value=100.0,
            value=_cuota_val(prefill, "cuota_local", 2.00), step=0.05, key="pm_cl",
        )
    with col_ce:
        cuota_empate = st.number_input(
            "Cuota X (Empate)", min_value=1.01, max_value=100.0,
            value=_cuota_val(prefill, "cuota_empate", 3.20), step=0.05, key="pm_ce",
        )
    with col_cv:
        cuota_visitante = st.number_input(
            "Cuota 2 (Visit.)", min_value=1.01, max_value=100.0,
            value=_cuota_val(prefill, "cuota_visitante", 3.50), step=0.05, key="pm_cv",
        )
    with col_xl:
        xg_local = st.number_input(
            "xG Local", min_value=0.1, max_value=5.0, value=1.5, step=0.1, key="pm_xgl",
        )
    with col_xv:
        xg_visitante = st.number_input(
            "xG Visitante", min_value=0.1, max_value=5.0, value=1.2, step=0.1, key="pm_xgv",
        )

    # ── DATOS ADICIONALES (colapsados) ────────────────────────────────────────
    with st.expander("➕ Datos adicionales (opcional)", expanded=False):

        _sec("Cuotas Ambos Marcan", opcional=True)
        col_si, col_no = st.columns(2)
        with col_si:
            cuota_btts_si = st.number_input(
                "Ambos Marcan — Sí", min_value=0.0, max_value=100.0,
                value=0.0, step=0.05, key="pm_btts_si",
                help="Deja en 0 si no tienes esta cuota",
            )
        with col_no:
            cuota_btts_no = st.number_input(
                "Ambos Marcan — No", min_value=0.0, max_value=100.0,
                value=0.0, step=0.05, key="pm_btts_no",
                help="Deja en 0 si no tienes esta cuota",
            )

        _sec("Cuotas Resultado 1ª Parte", opcional=True)
        col_1tl, col_1te, col_1tv = st.columns(3)
        with col_1tl:
            cuota_1t_local = st.number_input(
                "Local 1T", min_value=0.0, max_value=100.0,
                value=0.0, step=0.05, key="pm_1t_local",
                help="Deja en 0 si no tienes esta cuota",
            )
        with col_1te:
            cuota_1t_empate = st.number_input(
                "Empate 1T", min_value=0.0, max_value=100.0,
                value=0.0, step=0.05, key="pm_1t_empate",
                help="Deja en 0 si no tienes esta cuota",
            )
        with col_1tv:
            cuota_1t_visitante = st.number_input(
                "Visitante 1T", min_value=0.0, max_value=100.0,
                value=0.0, step=0.05, key="pm_1t_visitante",
                help="Deja en 0 si no tienes esta cuota",
            )

        _sec("Forma últimos 5  ·  ELO (BeSoccer)", opcional=True)
        col_bl5, col_bv5, col_el, col_ev = st.columns(4)
        with col_bl5:
            btts_local_5 = st.number_input(
                "BTTS local (últ. 5)", min_value=0, max_value=5, value=None, step=1,
                key="pm_btts_l5",
                help="Partidos de los últimos 5 con Ambos Marcan — local",
            )
        with col_bv5:
            btts_visit_5 = st.number_input(
                "BTTS visit. (últ. 5)", min_value=0, max_value=5, value=None, step=1,
                key="pm_btts_v5",
                help="Partidos de los últimos 5 con Ambos Marcan — visitante",
            )
        with col_el:
            elo_local = st.number_input(
                "ELO local", min_value=0, max_value=3000, value=None, step=1,
                key="pm_elo_l",
                help="ELO del equipo local (BeSoccer)",
            )
        with col_ev:
            elo_visit = st.number_input(
                "ELO visitante", min_value=0, max_value=3000, value=None, step=1,
                key="pm_elo_v",
                help="ELO del equipo visitante (BeSoccer)",
            )

        _sec("Contexto del partido (BeSoccer)", opcional=True)
        col_mot, col_ult = st.columns(2)
        with col_mot:
            motivacion = st.selectbox(
                "¿Partido con algo en juego?",
                ["No sé / Sin datos", "Sí — ascenso/descenso", "Parcialmente",
                 "No — sin motivación"],
                key="pm_motivacion",
            )
        with col_ult:
            ultimo_partido = st.selectbox(
                "¿Último partido de temporada?",
                ["No sé / Sin datos", "No", "Sí"],
                key="pm_ultimo_partido",
            )

        if "sin motivación" in st.session_state.get("pm_motivacion", "").lower():
            st.markdown(
                '<div style="font-size:10px;color:#b8780f;background:#fff7e6;'
                'border:1px solid #f5a623;border-radius:5px;padding:5px 10px;margin-top:4px;">'
                '⚠️ Partido sin motivación — se restará 1 punto del sistema de puntuación</div>',
                unsafe_allow_html=True,
            )
        if st.session_state.get("pm_ultimo_partido") == "Sí":
            st.markdown(
                '<div style="font-size:10px;color:#b8780f;background:#fff7e6;'
                'border:1px solid #f5a623;border-radius:5px;padding:5px 10px;margin-top:4px;">'
                '⚠️ Último partido de temporada — alta rotación posible</div>',
                unsafe_allow_html=True,
            )

    # Leer valores del expander desde session_state (en caso de que esté cerrado)
    cuota_btts_si      = st.session_state.get("pm_btts_si",        0.0)
    cuota_btts_no      = st.session_state.get("pm_btts_no",        0.0)
    cuota_1t_local     = st.session_state.get("pm_1t_local",       0.0)
    cuota_1t_empate    = st.session_state.get("pm_1t_empate",      0.0)
    cuota_1t_visitante = st.session_state.get("pm_1t_visitante",   0.0)
    btts_local_5       = st.session_state.get("pm_btts_l5",        None)
    btts_visit_5       = st.session_state.get("pm_btts_v5",        None)
    elo_local          = st.session_state.get("pm_elo_l",          None)
    elo_visit          = st.session_state.get("pm_elo_v",          None)
    motivacion         = st.session_state.get("pm_motivacion",     "No sé / Sin datos")
    ultimo_partido     = st.session_state.get("pm_ultimo_partido", "No sé / Sin datos")

    # ── BOTONES DE ACCIÓN ────────────────────────────────────────────────────
    st.markdown("<hr style='border-color:#e2e8f0;margin:14px 0 10px'>",
                unsafe_allow_html=True)
    col_guardar, col_cancelar = st.columns([5, 1])
    with col_guardar:
        guardar = st.button(
            "💾  Guardar Partido", key="btn_agregar_manual_pag",
            use_container_width=True, type="primary",
        )
    with col_cancelar:
        if st.button("✖ Cancelar", key="btn_cancelar_manual_pag",
                     use_container_width=True,
                     help="Volver a Análisis de Partidos sin guardar"):
            _limpiar_form()
            st.session_state["pagina_activa"] = "Análisis de Partidos"
            st.rerun()

    if guardar:
        if not equipo_local.strip() or not equipo_visitante.strip() or not liga.strip():
            st.error("⚠️ Completa equipo local, equipo visitante y liga antes de guardar.")
        else:
            _guardar_partido_manual(
                equipo_local.strip(), equipo_visitante.strip(), liga.strip(),
                cuota_local, cuota_empate, cuota_visitante,
                xg_local, xg_visitante,
                cuota_btts_si, cuota_btts_no,
                cuota_1t_local, cuota_1t_empate, cuota_1t_visitante,
                btts_local_5, btts_visit_5, elo_local, elo_visit,
                motivacion, ultimo_partido,
            )
            nombre = f"{equipo_local.strip()} vs {equipo_visitante.strip()}"
            guardado_msg = f"✅ '{nombre}' añadido correctamente."
            if cuota_btts_si > 1.01 or cuota_btts_no > 1.01:
                guardado_msg += " BTTS guardado."
            if cuota_1t_local > 1.01 or cuota_1t_empate > 1.01 or cuota_1t_visitante > 1.01:
                guardado_msg += " 1ª Parte guardada."
            if any(v is not None for v in (btts_local_5, btts_visit_5, elo_local, elo_visit)):
                guardado_msg += " Forma/ELO guardados."

            st.session_state["partido_recien_guardado"] = nombre
            st.session_state["msg_partido_manual"] = {
                "texto":      guardado_msg,
                "tipo":       "success",
                "created_at": __import__("time").time(),
            }
            _limpiar_form()
            st.session_state["pagina_activa"] = "Análisis de Partidos"
            st.rerun()


def _limpiar_form() -> None:
    """Limpia las claves del formulario del session_state."""
    for k in (
        "pm_local", "pm_visitante", "pm_liga", "pm_cl", "pm_ce", "pm_cv",
        "pm_xgl", "pm_xgv", "pm_btts_si", "pm_btts_no",
        "pm_1t_local", "pm_1t_empate", "pm_1t_visitante",
        "pm_btts_l5", "pm_btts_v5", "pm_elo_l", "pm_elo_v",
        "pm_motivacion", "pm_ultimo_partido",
        "pm_prefill", "pm_resultados", "pm_match_sel",
        "pm_sel_label", "pm_buscar",
    ):
        st.session_state.pop(k, None)
