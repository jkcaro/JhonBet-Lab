"""Módulo: Historial de Análisis Claude — lista, tarjetas y gráficos SCADA por análisis."""

import json
from pathlib import Path
import streamlit as st

_RUTA = Path(__file__).parent.parent / "data" / "claude_analysis.json"

_GREEN  = "#22c55e"
_YELLOW = "#f59e0b"
_RED    = "#ef4444"
_PURP   = "#a78bfa"
_PANEL  = "#080c14"
_BORDE  = "#1e1e38"
_TEXT   = "#5a7a9a"
_LIGHT  = "#8889aa"

_CONFIG_PLOTLY = {"displayModeBar": False, "staticPlot": False}

_CSS = """
<style>
.hc-resumen { display:flex; gap:10px; margin-bottom:14px; flex-wrap:wrap; }
.hc-stat {
    background:#12121e; border:1px solid #1e1e38; border-radius:8px;
    padding:8px 16px; text-align:center; min-width:90px; flex:1;
}
.hc-stat-val { font-size:18px; font-weight:800; line-height:1.1; }
.hc-stat-lbl { font-size:9px; color:#5a7a9a; text-transform:uppercase;
               letter-spacing:1px; margin-top:2px; }
.hc-card {
    background:#12121e; border:1px solid #1e1e38; border-radius:10px;
    padding:12px 14px; margin-bottom:6px; border-left:3px solid #2a2a55;
}
.hc-partido { font-size:13px; font-weight:700; color:#e8e8f0; }
.hc-fecha   { font-size:10px; color:#5a7a9a; white-space:nowrap; }
.hc-badges  { display:flex; gap:6px; flex-wrap:wrap; margin-top:6px; align-items:center; }
.hc-badge   { font-size:10px; font-weight:600; border-radius:4px;
              padding:2px 8px; border:1px solid; white-space:nowrap; }

/* ── Inputs nativos — fondo oscuro ── */
.stTextInput > div > div,
.stTextInput > div > div > input,
[data-baseweb="input"],
[data-baseweb="input"] > div,
[data-baseweb="input"] input {
    background-color: #1a1a2e !important;
    color: #e8e8f0 !important;
    border: 1px solid #333 !important;
}
.stTextInput > div > div:focus-within,
[data-baseweb="input"]:focus-within {
    border-color: #7c3aed !important;
    box-shadow: 0 0 0 1px #7c3aed33 !important;
}
.stTextArea > div > div,
.stTextArea > div > div > textarea,
[data-baseweb="textarea"],
[data-baseweb="textarea"] > div,
[data-baseweb="textarea"] textarea {
    background-color: #1a1a2e !important;
    color: #e8e8f0 !important;
    border: 1px solid #333 !important;
}
.stSelectbox > div > div,
[data-baseweb="select"] > div {
    background-color: #1a1a2e !important;
    color: #e8e8f0 !important;
    border: 1px solid #333 !important;
}
.stTextInput label,
.stTextArea label,
.stSelectbox label {
    color: #5a7a9a !important;
    font-size: 11px !important;
}
/* Placeholder */
.stTextInput input::placeholder,
.stTextArea textarea::placeholder {
    color: #5a7a9a !important;
    opacity: 1 !important;
}

/* ── Expander — barra oscura ── */
[data-testid="stExpander"] details summary {
    background-color: #0d1117 !important;
    color: #8889aa !important;
    border: 1px solid #1e1e38 !important;
    border-radius: 6px !important;
    padding: 7px 12px !important;
}
[data-testid="stExpander"] details summary:hover {
    background-color: #12121e !important;
    color: #e8e8f0 !important;
    border-color: #2a2a55 !important;
}
[data-testid="stExpander"] details summary > span {
    color: inherit !important;
}
[data-testid="stExpander"] details summary svg {
    fill: #5a7a9a !important;
}
[data-testid="stExpander"] details[open] summary {
    border-radius: 6px 6px 0 0 !important;
    border-bottom-color: #0d1117 !important;
}
[data-testid="stExpanderDetails"] {
    background-color: #0a0a18 !important;
    border: 1px solid #1e1e38 !important;
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
        '<div style="font-size:9px;color:#5a7a9a;letter-spacing:2px;'
        'font-family:Courier New,monospace;margin-bottom:10px;">'
        '◈ HISTORIAL DE ANÁLISIS — CLAUDE AI</div>',
        unsafe_allow_html=True,
    )

    if not historial:
        st.markdown(
            '<div style="background:#12121e;border:1px solid #1e1e38;border-radius:8px;'
            'padding:24px;text-align:center;color:#5a7a9a;font-size:13px;">'
            'Sin análisis guardados aún.<br>'
            '<span style="font-size:11px;opacity:.6">'
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
        f'<div class="hc-stat"><div class="hc-stat-val" style="color:#e8e8f0;">{total}</div>'
        f'<div class="hc-stat-lbl">Total</div></div>'
        f'<div class="hc-stat"><div class="hc-stat-val" style="color:{_GREEN};">{apostados}</div>'
        f'<div class="hc-stat-lbl">Apostados</div></div>'
        f'<div class="hc-stat"><div class="hc-stat-val" style="color:{_YELLOW};">{precauc}</div>'
        f'<div class="hc-stat-lbl">Precaución</div></div>'
        f'<div class="hc-stat"><div class="hc-stat-val" style="color:{_RED};">{no_ap}</div>'
        f'<div class="hc-stat-lbl">No apostar</div></div>'
        f'<div class="hc-stat"><div class="hc-stat-val" style="color:{edge_col};">{sign}{edge_prom}%</div>'
        f'<div class="hc-stat-lbl">Edge prom.</div></div>'
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
                     help="Eliminar todo el historial"):
            try:
                _RUTA.write_text("[]", encoding="utf-8")
                st.rerun()
            except Exception as exc:
                st.error(f"Error al limpiar: {exc}")

    # Aplicar filtro
    if filtro:
        _f = filtro.lower()
        historial_vis = [
            e for e in historial
            if _f in e.get("partido",  "").lower()
            or _f in e.get("mercado",  "").lower()
            or _f in e.get("veredicto","").lower()
        ]
    else:
        historial_vis = historial

    if filtro and not historial_vis:
        st.markdown(
            '<div style="background:#12121e;border:1px solid #1e1e38;border-radius:8px;'
            'padding:14px;text-align:center;color:#5a7a9a;font-size:12px;margin-top:8px;">'
            'Sin resultados para ese filtro.</div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown("<hr style='border-color:#1e1e38;margin:4px 0 10px'>", unsafe_allow_html=True)

    # ── Tarjetas ────────────────────────────────────────────────────────
    for i, entrada in enumerate(historial_vis):
        partido = entrada.get("partido",  "Partido desconocido")
        fecha   = entrada.get("fecha_hora", "—")
        mercado = entrada.get("mercado",  "—")
        edge    = float(entrada.get("edge", 0.0))
        puntos  = entrada.get("puntos",  0)
        verdict = entrada.get("veredicto", "NO APOSTAR")
        texto   = entrada.get("texto_analisis", "Sin texto guardado.")

        col_v, col_vb = _color_veredicto(verdict)
        edge_col = _GREEN if edge >= 6 else (_YELLOW if edge >= 3 else _RED)
        sign_e   = "+" if edge >= 0 else ""

        st.markdown(
            f'<div class="hc-card">'
            f'<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;">'
            f'<span class="hc-partido">⚽ {partido}</span>'
            f'<span class="hc-fecha">{fecha}</span>'
            f'</div>'
            f'<div class="hc-badges">'
            f'<span class="hc-badge" style="color:{_PURP};border-color:#3b2f8a;background:rgba(124,58,237,.1);">{mercado}</span>'
            f'<span class="hc-badge" style="color:{edge_col};border-color:{edge_col}44;background:{edge_col}11;">Edge {sign_e}{edge}%</span>'
            f'<span class="hc-badge" style="color:#8889aa;border-color:#2a2a55;background:#16162a;">{puntos}/5 pts</span>'
            f'<span class="hc-badge" style="color:{col_v};border-color:{col_vb};background:{col_v}11;'
            f'font-size:11px;font-weight:700;">{verdict}</span>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        with st.expander("Ver análisis completo + gráficos SCADA", expanded=False):
            # ── Gráficos SCADA (layout propio 2 columnas) ──
            _mostrar_scada(entrada, idx=i)

            st.markdown(
                '<hr style="border-color:#1e1e38;margin:10px 0 8px">',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div style="font-size:9px;color:#5a7a9a;letter-spacing:1.5px;'
                'font-family:Courier New,monospace;margin-bottom:8px;">'
                '◈ ANÁLISIS CLAUDE</div>',
                unsafe_allow_html=True,
            )

            # ── Texto en dos columnas con caja ──
            secciones = texto.split("\n\n---\n\n")
            mitad     = max(1, len(secciones) // 2)
            txt_izq   = "\n\n---\n\n".join(secciones[:mitad])
            txt_der   = "\n\n---\n\n".join(secciones[mitad:]) if len(secciones) > 1 else ""

            _estilo_caja = (
                "background:#0a0a18;border:1px solid #1e1e38;border-radius:8px;"
                "padding:14px 16px;height:100%;"
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
