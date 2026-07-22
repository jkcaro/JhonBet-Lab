"""Módulo: Historial de Análisis Claude — lista, tarjetas y gráficos SCADA por análisis."""

import json
import os
from pathlib import Path
import streamlit as st

from modules import etiquetas_mercado as em
from modules.scada_charts import (
    historial_card_css, historial_card_html, paginar_lista, controles_paginacion,
)

os.makedirs(Path(__file__).parent.parent / "data", exist_ok=True)

_RUTA = Path(__file__).parent.parent / "data" / "claude_analysis.json"

_GREEN  = "#22c55e"
_YELLOW = "#f59e0b"
_RED    = "#ef4444"
_PURP   = "#a78bfa"

_CONFIG_PLOTLY = {"displayModeBar": False, "staticPlot": False}

_CSS = """
<style>
.hc-resumen { display:flex; gap:10px; margin-bottom:14px; flex-wrap:wrap; }
.hc-stat {
    background:var(--bg-tarjeta); border:1px solid var(--borde); border-radius:8px;
    padding:8px 16px; text-align:center; min-width:90px; flex:1;
}
.hc-stat-val { font-size:18px; font-weight:800; line-height:1.1; }
.hc-stat-lbl { font-size:9px; color:var(--texto-apagado); text-transform:uppercase;
               letter-spacing:1px; margin-top:2px; }
/* ── Botón "Limpiar" — acción destructiva, borde rojo (semántico, fijo) ── */
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {
    background-color: var(--bg-tarjeta) !important;
    color: #dc2626 !important;
    border: 1px solid #dc2626 !important;
}
[data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover {
    background-color: #dc2626 !important;
    color: #ffffff !important;
    border-color: #dc2626 !important;
}

/* ── Inputs nativos — fondo DeOP según tema activo ── */
.stTextInput > div > div,
.stTextInput > div > div > input,
[data-baseweb="input"],
[data-baseweb="input"] > div,
[data-baseweb="input"] input {
    background-color: var(--bg-tarjeta) !important;
    color: var(--texto) !important;
    border: 1px solid var(--borde) !important;
}
.stTextInput > div > div:focus-within,
[data-baseweb="input"]:focus-within {
    border-color: var(--acento-dorado) !important;
    box-shadow: 0 0 0 1px #f5a62333 !important;
}
.stTextArea > div > div,
.stTextArea > div > div > textarea,
[data-baseweb="textarea"],
[data-baseweb="textarea"] > div,
[data-baseweb="textarea"] textarea {
    background-color: var(--bg-tarjeta) !important;
    color: var(--texto) !important;
    border: 1px solid var(--borde) !important;
}
.stSelectbox > div > div,
[data-baseweb="select"] > div {
    background-color: var(--bg-tarjeta) !important;
    color: var(--texto) !important;
    border: 1px solid var(--borde) !important;
}
.stTextInput label,
.stTextArea label,
.stSelectbox label {
    color: var(--texto-apagado) !important;
    font-size: 11px !important;
}
/* Placeholder */
.stTextInput input::placeholder,
.stTextArea textarea::placeholder {
    color: #94a8b8 !important;
    opacity: 1 !important;
}

/* ── Expander — barra DeOP según tema activo ── */
[data-testid="stExpander"] details summary {
    background-color: var(--bg-tarjeta) !important;
    color: var(--acento-morado) !important;
    border: 1px solid var(--borde) !important;
    border-radius: 6px !important;
    padding: 7px 12px !important;
}
[data-testid="stExpander"] details summary:hover {
    background-color: var(--bg-alerta-aviso) !important;
    color: var(--acento-morado) !important;
    border-color: var(--acento-dorado) !important;
}
[data-testid="stExpander"] details summary > span {
    color: inherit !important;
}
[data-testid="stExpander"] details summary svg {
    fill: var(--texto-apagado) !important;
}
[data-testid="stExpander"] details[open] summary {
    border-radius: 6px 6px 0 0 !important;
    border-bottom-color: var(--bg-tarjeta) !important;
}
[data-testid="stExpanderDetails"] {
    background-color: var(--bg-tarjeta) !important;
    border: 1px solid var(--borde) !important;
    border-top: none !important;
    border-radius: 0 0 6px 6px !important;
}
</style>
"""


def _cargar() -> list[dict]:
    if not _RUTA.exists():
        return []
    try:
        data = json.loads(_RUTA.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _color_veredicto(v: str) -> tuple[str, str]:
    v = v.upper()
    if "APOSTAR" in v and "NO" not in v:
        return _GREEN,  "#1a4a2a"
    if "PRECAUCIÓN" in v or "PRECAUCION" in v:
        return _YELLOW, "#4a3a00"
    return _RED, "#4a1010"


def _reconstruir_datos(entrada: dict) -> dict:
    """Reconstruye el dict 'datos' necesario para los gráficos SCADA."""
    probs = dict(entrada.get("probabilidades", {}))
    # Asegurar que xg_local/xg_visitante estén en probabilidades
    if "xg_local" not in probs:
        probs["xg_local"]     = entrada.get("xg_local",     1.5)
        probs["xg_visitante"] = entrada.get("xg_visitante", 1.2)
    return {
        "partido":        entrada.get("partido", ""),
        "mercado":        entrada.get("mercado", ""),
        "probabilidades": probs,
        "edge_por_outcome": {},
    }


def _reconstruir_puntuacion(entrada: dict) -> dict:
    """Reconstruye el dict 'puntuacion' para semáforo, gauges y tarjeta de veredicto."""
    base = dict(entrada.get("puntuacion_scada", {}))
    # Garantizar campos mínimos
    base.setdefault("puntos",          entrada.get("puntos", 0))
    base.setdefault("edge",            entrada.get("edge",   0.0))
    base.setdefault("estado",          entrada.get("veredicto", "NO APOSTAR"))
    base.setdefault("confianza",       entrada.get("confianza", "Bajo"))
    base.setdefault("cond_edge_base",  entrada.get("edge", 0.0) >= 6)
    base.setdefault("cond_xg_manual",  False)
    base.setdefault("cond_btts_local", False)
    base.setdefault("cond_btts_visit", False)
    base.setdefault("cond_confianza",  entrada.get("confianza", "Bajo") in ("Alto", "Medio"))
    base.setdefault("decision",
        "verde" if "APOSTAR" in base["estado"] and "NO" not in base["estado"]
        else "amarillo" if "PRECAUCIÓN" in base["estado"].upper()
        else "rojo"
    )
    return base


_CONF_NUM = {"Alto": 85.0, "Medio": 50.0, "Bajo": 18.0}


def _mostrar_scada(entrada: dict, idx: int = 0) -> None:
    """
    Renderiza el análisis guardado con los MISMOS componentes que la vista
    en vivo de "Analizar con IA" (modules/claude_analysis.py, fila1/2/3) —
    mismos datos del JSON, solo cambia el render (gauges de aguja/panel
    terminal viejos -> donuts/tarjetas DeOP). Todos los paneles nuevos ya
    degradan solos a "—"/"sin datos" cuando falta un campo (verificado:
    victoria1x2_modelo, elo_local/visit y forma_reciente_* nunca se
    guardaron en el historial, ni en registros viejos ni nuevos — no es
    incompatibilidad de época, es una limitación estructural del guardado
    ya cubierta por el propio diseño de esos paneles).
    """
    from modules.scada_charts import (
        semaforo_html, gauge_donut_gris, gauge_puntos_deop,
        tarjeta_veredicto_html, tabla_edges, barras_probabilidad_deop,
        donut_ambos_marcan, panel_xg_comparativo, panel_forma_reciente,
        panel_balanza_elo, _CSS_COMPACTO, _paleta_activa,
    )

    paleta     = _paleta_activa()
    puntuacion = _reconstruir_puntuacion(entrada)
    datos      = _reconstruir_datos(entrada)

    edge      = float(puntuacion.get("edge", 0.0))
    puntos    = puntuacion.get("puntos", 0)
    confianza = puntuacion.get("confianza", "Bajo")
    confianza_pct = _CONF_NUM.get(confianza, 18.0)
    mercado   = entrada.get("mercado", "")
    sign      = "+" if edge >= 0 else ""

    st.markdown(_CSS_COMPACTO, unsafe_allow_html=True)

    # ── Fila 1 — semáforo + tarjeta de veredicto + gauges edge/confianza/puntos ──
    col_luz, col_ver, col_g1, col_g2, col_g3 = st.columns([0.8, 1.6, 1, 1, 1])
    with col_luz:
        st.markdown(semaforo_html(edge, puntuacion), unsafe_allow_html=True)
    with col_ver:
        st.markdown(
            tarjeta_veredicto_html(
                em.titulo_mercado(mercado) if mercado else "Análisis guardado",
                f"{em.EDGE_LABEL.capitalize()}: {sign}{edge:.1f}%  ·  "
                f"Puntos: {puntos}/4  ·  Confianza: {confianza}",
                puntuacion.get("estado", "NO APOSTAR"),
            ),
            unsafe_allow_html=True,
        )
    with col_g1:
        st.plotly_chart(gauge_donut_gris(max(0.0, edge), f"{em.EDGE_LABEL.capitalize()} %", paleta["dorado"]),
                        use_container_width=True, config=_CONFIG_PLOTLY, key=f"hist_gauge_edge_{idx}")
    with col_g2:
        st.plotly_chart(gauge_donut_gris(confianza_pct, "Confianza %", paleta["petroleo"]),
                        use_container_width=True, config=_CONFIG_PLOTLY, key=f"hist_gauge_conf_{idx}")
    with col_g3:
        st.plotly_chart(gauge_puntos_deop(puntos, color=paleta["dorado"]),
                        use_container_width=True, config=_CONFIG_PLOTLY, key=f"hist_gauge_pts_{idx}")

    # ── Fila 2 — tabla de edges + barras 1X2 + donut BTTS ──────────────────────
    col_tabla, col_barras, col_donut = st.columns(3)
    with col_tabla:
        html_tabla = tabla_edges(datos)
        if html_tabla:
            st.markdown(html_tabla, unsafe_allow_html=True)
        else:
            st.caption("Tabla de edges no disponible para este análisis.")
    with col_barras:
        if datos.get("probabilidades"):
            st.plotly_chart(barras_probabilidad_deop(datos),
                            use_container_width=True, config=_CONFIG_PLOTLY, key=f"hist_barras_{idx}")
    with col_donut:
        xg_l = float(datos["probabilidades"].get("xg_local",     0) or 0)
        xg_v = float(datos["probabilidades"].get("xg_visitante", 0) or 0)
        if xg_l > 0 and xg_v > 0:
            st.plotly_chart(donut_ambos_marcan(datos),
                            use_container_width=True, config=_CONFIG_PLOTLY, key=f"hist_donut_{idx}")

    # ── Fila 3 — xG comparativo + forma reciente + balanza ELO ────────────────
    col_xg, col_forma, col_elo = st.columns(3)
    with col_xg:
        st.markdown(panel_xg_comparativo(datos), unsafe_allow_html=True)
    with col_forma:
        st.markdown(panel_forma_reciente(datos), unsafe_allow_html=True)
    with col_elo:
        st.markdown(panel_balanza_elo(datos), unsafe_allow_html=True)


def mostrar() -> None:
    """Renderiza la página de Historial de Análisis Claude."""
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(
        historial_card_css("hc", "hc_lista", incluye_expander=False, max_width=750),
        unsafe_allow_html=True,
    )

    historial = _cargar()

    st.markdown(
        '<div style="font-size:10px;color:var(--acento-morado);font-weight:800;letter-spacing:2px;'
        'margin-bottom:10px;">'
        '◈ HISTORIAL DE ANÁLISIS — CLAUDE AI</div>',
        unsafe_allow_html=True,
    )

    if not historial:
        st.markdown(
            '<div style="background:var(--bg-tarjeta);border:1px solid var(--borde);border-radius:8px;'
            'padding:24px;text-align:center;color:var(--texto-apagado);font-size:13px;">'
            'Sin análisis guardados aún.<br>'
            '<span style="font-size:11px;opacity:.7">'
            'Pulsa "Analizar con Claude AI" para generar el primer análisis.</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    # ── Resumen ─────────────────────────────────────────────────────────
    total     = len(historial)
    apostados = sum(1 for e in historial
                    if "APOSTAR" in e.get("veredicto", "").upper()
                    and "NO" not in e.get("veredicto", "").upper())
    no_ap     = sum(1 for e in historial if "NO APOSTAR" in e.get("veredicto", "").upper())
    precauc   = total - apostados - no_ap
    edges     = [e.get("edge", 0.0) for e in historial if isinstance(e.get("edge"), (int, float))]
    edge_prom = round(sum(edges) / len(edges), 1) if edges else 0.0
    edge_col  = _GREEN if edge_prom >= 6 else (_YELLOW if edge_prom >= 0 else _RED)
    sign      = "+" if edge_prom >= 0 else ""

    st.markdown(
        f'<div class="hc-resumen">'
        f'<div class="hc-stat"><div class="hc-stat-val" style="color:var(--acento-morado);">{total}</div>'
        f'<div class="hc-stat-lbl">Total</div></div>'
        f'<div class="hc-stat"><div class="hc-stat-val" style="color:{_GREEN};">{apostados}</div>'
        f'<div class="hc-stat-lbl">Apostados</div></div>'
        f'<div class="hc-stat"><div class="hc-stat-val" style="color:{_YELLOW};">{precauc}</div>'
        f'<div class="hc-stat-lbl">Precaución</div></div>'
        f'<div class="hc-stat"><div class="hc-stat-val" style="color:{_RED};">{no_ap}</div>'
        f'<div class="hc-stat-lbl">No apostar</div></div>'
        f'<div class="hc-stat"><div class="hc-stat-val" style="color:{edge_col};">{sign}{edge_prom}%</div>'
        f'<div class="hc-stat-lbl">Ventaja prom.</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Barra filtro + botón limpiar ────────────────────────────────────
    col_filtro, col_btn = st.columns([4, 1])
    with col_filtro:
        filtro = st.text_input(
            "",
            key="hc_filtro",
            placeholder="🔍 Buscar por partido, mercado o veredicto...",
            label_visibility="collapsed",
        )
    with col_btn:
        if st.button("🗑 Limpiar", key="btn_limpiar_hc", use_container_width=True,
                     type="primary", help="Eliminar todo el historial"):
            try:
                _RUTA.write_text("[]", encoding="utf-8")
                st.rerun()
            except Exception as exc:
                st.error(f"Error al limpiar: {exc}")

    # Aplicar filtro — compara tanto contra la clave canónica guardada como
    # contra el texto visible nuevo, para que el usuario pueda buscar con
    # cualquiera de los dos (p.ej. "1X2" o "quién gana").
    # Cada entrada viaja junto a su índice ORIGINAL (posición en el JSON tal
    # cual está en disco) — ese índice es la clave estable de session_state
    # para el toggle "abierto/cerrado" de cada tarjeta, y no cambia aunque
    # el filtro de texto o la página actual reduzcan qué se muestra.
    historial_con_idx = list(enumerate(historial))

    if filtro:
        _f = filtro.lower()
        historial_vis = [
            (idx, e) for idx, e in historial_con_idx
            if _f in e.get("partido",  "").lower()
            or _f in e.get("mercado",  "").lower()
            or _f in em.titulo_mercado(e.get("mercado", "")).lower()
            or _f in e.get("veredicto","").lower()
        ]
    else:
        historial_vis = historial_con_idx

    if filtro and not historial_vis:
        st.markdown(
            '<div style="background:var(--bg-tarjeta);border:1px solid var(--borde);border-radius:8px;'
            'padding:14px;text-align:center;color:var(--texto-apagado);font-size:12px;margin-top:8px;">'
            'Sin resultados para ese filtro.</div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown("<hr style='border-color:var(--borde);margin:4px 0 10px'>", unsafe_allow_html=True)

    # ── Paginación — evita construir las 4 gráficas SCADA de TODOS los
    # registros en cada rerun; solo se procesan los de la página actual ──
    pagina_items, pagina_actual, total_paginas = paginar_lista(
        historial_vis, key="hc_pagina", por_pagina=15
    )
    controles_paginacion("hc_pagina", pagina_actual, total_paginas, sufijo="_top")

    # ── Tarjetas ────────────────────────────────────────────────────────
    with st.container(key="hc_lista"):
        for idx, entrada in pagina_items:
            partido = entrada.get("partido",  "Partido desconocido")
            fecha   = entrada.get("fecha_hora", "—")
            # "mercado" guardado es la clave canónica (compatibilidad con el JSON ya
            # persistido) — em.titulo_mercado() la traduce SOLO para mostrarla.
            mercado_raw = entrada.get("mercado") or ""
            mercado     = em.titulo_mercado(mercado_raw) if mercado_raw else "—"
            edge    = float(entrada.get("edge", 0.0))
            puntos  = entrada.get("puntos",  0)
            verdict = entrada.get("veredicto", "NO APOSTAR")
            texto   = entrada.get("texto_analisis", "Sin texto guardado.")

            col_v, col_vb = _color_veredicto(verdict)
            edge_col = _GREEN if edge >= 6 else (_YELLOW if edge >= 3 else _RED)
            sign_e   = "+" if edge >= 0 else ""

            estado_norm = ("APOSTAR" if "APOSTAR" in verdict.upper() and "NO" not in verdict.upper()
                           else "PRECAUCIÓN" if "PRECAUC" in verdict.upper()
                           else "NO APOSTAR")

            badges_html = (
                f'<span class="hc-badge" style="color:{_PURP};border-color:#a78bfa44;background:#a78bfa11;">{mercado}</span>'
                f'<span class="hc-badge" style="color:{edge_col};border-color:{edge_col}44;background:{edge_col}11;">{em.EDGE_LABEL.capitalize()} {sign_e}{edge}%</span>'
                f'<span class="hc-badge" style="color:var(--texto-apagado);border-color:var(--borde);background:var(--bg-elemento);">{puntos}/5 pts</span>'
                f'<span class="hc-badge" style="color:{col_v};border-color:{col_vb};background:{col_v}11;'
                f'font-size:11px;font-weight:700;">{verdict}</span>'
            )
            st.markdown(
                historial_card_html(
                    "hc", color_borde=col_v, partido=partido, fecha=fecha,
                    estado_norm=estado_norm, badges_html=badges_html,
                ),
                unsafe_allow_html=True,
            )

            # Lazy render: `with st.expander()` NO es perezoso — su contenido se
            # ejecuta en cada rerun aunque esté colapsado (confirmado en la Fase 1
            # de medición: 314 gráficos Plotly construidos con 0 expanders abiertos).
            # Con un checkbox + session_state, _mostrar_scada() y el texto de Claude
            # solo se construyen cuando el usuario efectivamente lo pidió.
            abierto = st.checkbox(
                "📊 Ver análisis completo + gráficos SCADA",
                key=f"hc_abierto_{idx}",
            )
            if abierto:
                with st.container(border=True):
                    # ── Gráficos SCADA (layout propio 2 columnas) ──
                    _mostrar_scada(entrada, idx=idx)

                    st.markdown(
                        '<hr style="border-color:var(--borde);margin:10px 0 8px">',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        '<div style="font-size:10px;color:var(--acento-morado);font-weight:800;letter-spacing:1.5px;'
                        'margin-bottom:8px;">'
                        '◈ ANÁLISIS CLAUDE</div>',
                        unsafe_allow_html=True,
                    )

                    # ── Texto en dos columnas con caja ──
                    secciones = texto.split("\n\n---\n\n")
                    mitad     = max(1, len(secciones) // 2)
                    txt_izq   = "\n\n---\n\n".join(secciones[:mitad])
                    txt_der   = "\n\n---\n\n".join(secciones[mitad:]) if len(secciones) > 1 else ""

                    _estilo_caja = (
                        "background:var(--bg-tarjeta);border:1px solid var(--borde);border-radius:8px;"
                        "padding:14px 16px;height:100%;color:var(--texto);"
                    )
                    col_txt_izq, col_txt_der = st.columns(2, gap="medium")
                    with col_txt_izq:
                        st.markdown(
                            f'<div style="{_estilo_caja}">', unsafe_allow_html=True
                        )
                        st.markdown(txt_izq)
                        st.markdown("</div>", unsafe_allow_html=True)
                    with col_txt_der:
                        if txt_der:
                            st.markdown(
                                f'<div style="{_estilo_caja}">', unsafe_allow_html=True
                            )
                            st.markdown(txt_der)
                            st.markdown("</div>", unsafe_allow_html=True)

    controles_paginacion("hc_pagina", pagina_actual, total_paginas, sufijo="_bottom")
