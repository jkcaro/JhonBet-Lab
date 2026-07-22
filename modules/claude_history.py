"""Módulo: Historial de Análisis Claude — lista, tarjetas y gráficos SCADA por análisis."""

import json
import os
from pathlib import Path
import streamlit as st

from modules import etiquetas_mercado as em
from modules.scada_charts import semaforo_mini_html

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
.hc-card {
    background:var(--bg-tarjeta); border:0; border-left:3px solid var(--borde);
    border-bottom:1px solid var(--borde);
    padding:4px 10px; margin:0;
    display:flex; align-items:center; justify-content:space-between; gap:10px;
    width:100%; max-width:900px; box-sizing:border-box;
}
.hc-left {
    display:flex; align-items:center; gap:8px; min-width:0;
    overflow-x:auto; flex:0 1 auto;
}
.hc-right { display:flex; align-items:center; gap:10px; flex:0 0 auto; }
.hc-partido { font-size:12px; font-weight:700; color:var(--acento-morado); white-space:nowrap; flex:0 0 auto; }
.hc-fecha   { font-size:9px; color:var(--texto-apagado); white-space:nowrap; opacity:.75; flex:0 0 auto; }
.hc-badges  { display:flex; gap:4px; flex-wrap:nowrap; align-items:center; flex:0 0 auto; }
.hc-badge   { font-size:11px; font-weight:600; border-radius:6px; height:18px;
              display:inline-flex; align-items:center;
              padding:0 7px; border:1px solid; white-space:nowrap; flex:0 0 auto; }

@media (max-width: 767px) {
    .hc-card  { flex-direction:column; align-items:flex-start; max-width:100%; gap:6px; }
    .hc-left  { width:100%; }
    .hc-right { width:100%; justify-content:space-between; }
}

/* ── Densidad general de la página: filas compactas — mismo patrón que Historial Dominada ── */
.st-key-hc_lista [data-testid="stVerticalBlock"] { gap:4px !important; }
.st-key-hc_lista [data-testid="stElementContainer"] { margin-bottom:0 !important; }

/* ── Acordeón "Ver análisis completo" — altura mínima, mismo ancho y alineado con la tarjeta ── */
.st-key-hc_lista [data-testid="stExpander"] { margin:0 !important; max-width:900px; }
.st-key-hc_lista [data-testid="stExpander"] summary {
    min-height:0 !important; height:28px !important;
    padding:0 10px !important; font-size:11px !important;
}
.st-key-hc_lista [data-testid="stExpander"] summary svg { width:12px !important; height:12px !important; }
.st-key-hc_lista [data-testid="stExpanderDetails"] { padding:8px !important; }
@media (max-width: 767px) {
    .st-key-hc_lista [data-testid="stExpander"] { max-width:100%; }
}

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
    """Reconstruye el dict 'puntuacion' para panel_sistema_puntos y semáforo."""
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


def _mostrar_scada(entrada: dict, idx: int = 0) -> None:
    """Renderiza los gráficos SCADA en dos columnas para un análisis guardado."""
    from modules.scada_charts import (
        gauge_edge, gauge_confianza, semaforo_html,
        panel_sistema_puntos, barras_probabilidad, donut_ambos_marcan,
        _CSS_COMPACTO,
    )

    st.markdown(_CSS_COMPACTO, unsafe_allow_html=True)

    edge       = float(entrada.get("edge", 0.0))
    confianza  = entrada.get("confianza", "Bajo")
    texto_conf = f"Confianza: {confianza}"
    puntuacion = _reconstruir_puntuacion(entrada)
    datos      = _reconstruir_datos(entrada)

    col_izq, col_der = st.columns(2, gap="medium")

    # ── Columna izquierda: indicadores de señal ──────────────────────
    with col_izq:
        st.plotly_chart(gauge_edge(edge),
                        use_container_width=True, config=_CONFIG_PLOTLY,
                        key=f"hist_edge_{idx}")
        st.plotly_chart(gauge_confianza(texto_conf),
                        use_container_width=True, config=_CONFIG_PLOTLY,
                        key=f"hist_conf_{idx}")
        st.markdown(semaforo_html(edge, puntuacion), unsafe_allow_html=True)

    # ── Columna derecha: puntuación + probabilidades ──────────────────
    with col_der:
        st.markdown(panel_sistema_puntos(puntuacion), unsafe_allow_html=True)

        if datos.get("probabilidades"):
            st.plotly_chart(barras_probabilidad(datos),
                            use_container_width=True, config=_CONFIG_PLOTLY,
                            key=f"hist_barras_{idx}")
            xg_l = float(datos["probabilidades"].get("xg_local",     0) or 0)
            xg_v = float(datos["probabilidades"].get("xg_visitante", 0) or 0)
            if xg_l > 0 and xg_v > 0:
                st.plotly_chart(donut_ambos_marcan(datos),
                                use_container_width=True, config=_CONFIG_PLOTLY,
                                key=f"hist_donut_{idx}")


def mostrar() -> None:
    """Renderiza la página de Historial de Análisis Claude."""
    st.markdown(_CSS, unsafe_allow_html=True)

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
    if filtro:
        _f = filtro.lower()
        historial_vis = [
            e for e in historial
            if _f in e.get("partido",  "").lower()
            or _f in e.get("mercado",  "").lower()
            or _f in em.titulo_mercado(e.get("mercado", "")).lower()
            or _f in e.get("veredicto","").lower()
        ]
    else:
        historial_vis = historial

    if filtro and not historial_vis:
        st.markdown(
            '<div style="background:var(--bg-tarjeta);border:1px solid var(--borde);border-radius:8px;'
            'padding:14px;text-align:center;color:var(--texto-apagado);font-size:12px;margin-top:8px;">'
            'Sin resultados para ese filtro.</div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown("<hr style='border-color:var(--borde);margin:4px 0 10px'>", unsafe_allow_html=True)

    # ── Tarjetas ────────────────────────────────────────────────────────
    with st.container(key="hc_lista"):
        for i, entrada in enumerate(historial_vis):
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

            st.markdown(
                f'<div class="hc-card" style="border-left-color:{col_v};">'
                f'<div class="hc-left">'
                f'<span class="hc-partido">⚽ {partido}</span>'
                f'<div class="hc-badges">'
                f'<span class="hc-badge" style="color:{_PURP};border-color:#a78bfa44;background:#a78bfa11;">{mercado}</span>'
                f'<span class="hc-badge" style="color:{edge_col};border-color:{edge_col}44;background:{edge_col}11;">{em.EDGE_LABEL.capitalize()} {sign_e}{edge}%</span>'
                f'<span class="hc-badge" style="color:var(--texto-apagado);border-color:var(--borde);background:var(--bg-elemento);">{puntos}/5 pts</span>'
                f'<span class="hc-badge" style="color:{col_v};border-color:{col_vb};background:{col_v}11;'
                f'font-size:11px;font-weight:700;">{verdict}</span>'
                f'</div>'
                f'</div>'
                f'<div class="hc-right">'
                f'<span class="hc-fecha">{fecha}</span>'
                f'{semaforo_mini_html(estado_norm)}'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            with st.expander("Ver análisis completo + gráficos SCADA", expanded=False):
                # ── Gráficos SCADA (layout propio 2 columnas) ──
                _mostrar_scada(entrada, idx=i)

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
