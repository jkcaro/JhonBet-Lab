"""Módulo: Historial Apuesta Dominada."""

import json
from pathlib import Path
import streamlit as st

from modules.scada_charts import (
    historial_card_css, historial_card_html, paginar_lista, controles_paginacion,
)

_RUTA = Path(__file__).parent.parent / "data" / "dominant_history.json"

_GREEN  = "#22c55e"
_YELLOW = "#f59e0b"
_RED    = "#ef4444"
_LIGHT  = "#8eb0cc"

_CSS = """
<style>
.dh-resumen { display:flex; gap:10px; margin-bottom:14px; flex-wrap:wrap; }
.dh-stat {
    background:var(--bg-tarjeta); border:1px solid var(--borde); border-radius:8px;
    padding:8px 16px; text-align:center; min-width:90px; flex:1;
}
.dh-stat-val { font-size:18px; font-weight:800; line-height:1.1; }
.dh-stat-lbl { font-size:9px; color:var(--texto-apagado); text-transform:uppercase;
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


def _color_estado(estado: str) -> tuple[str, str]:
    e = estado.upper()
    if "APOSTAR" in e and "NO" not in e:
        return _GREEN, "#1a4a2a"
    if "PRECAUCIÓN" in e or "PRECAUCION" in e:
        return _YELLOW, "#4a3a00"
    return _RED, "#4a1010"


def _detalle_reglas(reglas: list) -> str:
    filas = ""
    for item in reglas:
        lbl, ok, val = item[0], item[1], item[2]
        col = _GREEN if ok else _RED
        ico = "✅" if ok else "❌"
        filas += (
            f'<div style="display:flex;justify-content:space-between;'
            f'align-items:center;padding:4px 0;border-bottom:1px solid #1e1e38;">'
            f'<span style="font-size:11px;color:{_LIGHT};">{ico} {lbl}</span>'
            f'<span style="font-size:11px;font-weight:700;color:{col};">{val}</span>'
            f'</div>'
        )
    return filas


def mostrar() -> None:
    from modules.scada_charts import _paleta_activa

    paleta = _paleta_activa()
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(historial_card_css("dh", "dh_lista"), unsafe_allow_html=True)

    historial = _cargar()

    st.markdown(
        '<div style="font-size:10px;color:var(--acento-morado);font-weight:800;letter-spacing:2px;'
        'margin-bottom:10px;">'
        '◈ HISTORIAL — APUESTA DOMINADA</div>',
        unsafe_allow_html=True,
    )

    if not historial:
        st.markdown(
            '<div style="background:var(--bg-tarjeta);border:1px solid var(--borde);border-radius:8px;'
            'padding:24px;text-align:center;color:var(--texto-apagado);font-size:13px;">'
            'Sin análisis guardados aún.<br>'
            '<span style="font-size:11px;opacity:.7">'
            'Pulsa "💾 Guardar en historial" en Apuesta Dominada para registrar un análisis.</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    # ── Resumen ──────────────────────────────────────────────────────────────
    total     = len(historial)
    dominante = sum(1 for e in historial if e.get("es_dominante"))
    apostados = sum(1 for e in historial if "APOSTAR" in e.get("estado", "") and "NO" not in e.get("estado", ""))
    no_ap     = sum(1 for e in historial if "NO APOSTAR" in e.get("estado", ""))
    edges     = [e.get("edge_o15", 0.0) for e in historial if isinstance(e.get("edge_o15"), (int, float))]
    edge_prom = round(sum(edges) / len(edges), 1) if edges else 0.0
    edge_col  = _GREEN if edge_prom >= 6 else (_YELLOW if edge_prom >= 0 else _RED)
    sign      = "+" if edge_prom >= 0 else ""

    st.markdown(
        f'<div class="dh-resumen">'
        f'<div class="dh-stat"><div class="dh-stat-val" style="color:var(--acento-morado);">{total}</div>'
        f'<div class="dh-stat-lbl">Total</div></div>'
        f'<div class="dh-stat"><div class="dh-stat-val" style="color:{_GREEN};">{dominante}</div>'
        f'<div class="dh-stat-lbl">Dominantes</div></div>'
        f'<div class="dh-stat"><div class="dh-stat-val" style="color:{_GREEN};">{apostados}</div>'
        f'<div class="dh-stat-lbl">Apostados</div></div>'
        f'<div class="dh-stat"><div class="dh-stat-val" style="color:{_RED};">{no_ap}</div>'
        f'<div class="dh-stat-lbl">No apostar</div></div>'
        f'<div class="dh-stat"><div class="dh-stat-val" style="color:{edge_col};">{sign}{edge_prom}%</div>'
        f'<div class="dh-stat-lbl">Edge O1.5 prom.</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Botón limpiar ────────────────────────────────────────────────────────
    _, col_btn = st.columns([5, 1])
    with col_btn:
        if st.button("🗑 Limpiar", key="btn_limpiar_dh", use_container_width=True,
                     type="primary", help="Eliminar todo el historial"):
            try:
                _RUTA.write_text("[]", encoding="utf-8")
                st.rerun()
            except Exception as exc:
                st.error(f"Error al limpiar: {exc}")

    st.markdown("<hr style='border-color:var(--borde);margin:2px 0 10px'>", unsafe_allow_html=True)

    # ── Paginación preventiva — reutiliza el mismo paginador de Estadísticas.
    # El contenido de estos expanders es HTML plano (sin Plotly), así que hoy
    # no hay coste de render que reducir; solo evita que la lista siga
    # creciendo sin límite a futuro ──
    pagina_items, pagina_actual, total_paginas = paginar_lista(
        historial, key="dh_pagina", por_pagina=15
    )
    controles_paginacion("dh_pagina", pagina_actual, total_paginas, sufijo="_top")

    # ── Tarjetas ─────────────────────────────────────────────────────────────
    with st.container(key="dh_lista"):
        for i, entrada in enumerate(pagina_items):
            partido   = entrada.get("partido",    "Partido desconocido")
            fecha     = entrada.get("fecha_hora", "—")
            nom_fav   = entrada.get("nom_fav",    "Favorito")
            nom_riv   = entrada.get("nom_riv",    "Rival")
            estado    = entrada.get("estado",     "NO APOSTAR")
            n_ok      = entrada.get("n_ok",       0)
            es_dom    = entrada.get("es_dominante", False)
            edge_o15  = float(entrada.get("edge_o15",  0.0))
            p_o15     = float(entrada.get("p_o15",     0.0))
            p_hcp     = float(entrada.get("p_hcp",     0.0))
            p_vic     = float(entrada.get("p_victoria", 0.0))
            xg_fav    = float(entrada.get("xg_fav",    0.0))
            xg_rival  = float(entrada.get("xg_rival",  0.0))
            cuota_o15 = float(entrada.get("cuota_o15", 1.65))
            top_m     = entrada.get("top_marcador", "—")
            top_p     = float(entrada.get("top_prob", 0.0))
            reglas    = entrada.get("reglas", [])

            col_v, col_vb = _color_estado(estado)
            edge_col  = _GREEN if edge_o15 >= 6 else (_YELLOW if edge_o15 >= 0 else _RED)
            sign_e    = "+" if edge_o15 >= 0 else ""
            dom_col   = _GREEN if es_dom else _RED
            dom_txt   = "DOMINANTE" if es_dom else "NO DOMINANTE"
            estado_norm = ("APOSTAR" if "APOSTAR" in estado.upper() and "NO" not in estado.upper()
                           else "PRECAUCIÓN" if "PRECAUC" in estado.upper()
                           else "NO APOSTAR")

            badges_html = (
                f'<span class="dh-badge" style="color:{dom_col};border-color:{dom_col}44;background:{dom_col}11;">🔥 {dom_txt}</span>'
                f'<span class="dh-badge" style="color:var(--texto-apagado);border-color:var(--borde);background:var(--bg-elemento);">{n_ok}/4 reglas</span>'
                f'<span class="dh-badge" style="color:{edge_col};border-color:{edge_col}44;background:{edge_col}11;">O1.5 {sign_e}{edge_o15}%</span>'
                f'<span class="dh-badge" style="color:{col_v};border-color:{col_vb};background:{col_v}11;'
                f'font-size:11px;font-weight:700;">{estado}</span>'
            )
            st.markdown(
                historial_card_html(
                    "dh", color_borde=col_v, partido=partido, fecha=fecha,
                    estado_norm=estado_norm, badges_html=badges_html,
                ),
                unsafe_allow_html=True,
            )

            with st.expander("Ver detalles", expanded=False):
                col_izq, col_der = st.columns(2, gap="medium")

                with col_izq:
                    # xG y probabilidades
                    st.markdown(
                        f'<div style="background:var(--bg-tarjeta);border:1px solid var(--borde);border-radius:6px;'
                        f'padding:10px 14px;margin-bottom:8px;">'
                        f'<div style="font-size:10px;color:var(--acento-morado);font-weight:800;letter-spacing:2px;'
                        f'border-bottom:2px solid var(--acento-dorado);padding-bottom:5px;margin-bottom:8px;">'
                        f'◈ DATOS DEL PARTIDO</div>'
                        f'<div style="display:flex;gap:8px;margin-bottom:10px;">'
                        f'<div style="flex:1;text-align:center;">'
                        f'<div style="font-size:9px;color:var(--texto-apagado);text-transform:uppercase;">{nom_fav[:12]}</div>'
                        f'<div style="font-size:22px;font-weight:900;color:{_GREEN};">{xg_fav:.2f}</div>'
                        f'<div style="font-size:9px;color:var(--texto-apagado);">xG fav</div></div>'
                        f'<div style="flex:1;text-align:center;">'
                        f'<div style="font-size:9px;color:var(--texto-apagado);text-transform:uppercase;">P victoria</div>'
                        f'<div style="font-size:22px;font-weight:900;color:#b8780f;">{p_vic:.1f}%</div>'
                        f'<div style="font-size:9px;color:var(--texto-apagado);">probabilidad</div></div>'
                        f'<div style="flex:1;text-align:center;">'
                        f'<div style="font-size:9px;color:var(--texto-apagado);text-transform:uppercase;">{nom_riv[:12]}</div>'
                        f'<div style="font-size:22px;font-weight:900;color:{_RED};">{xg_rival:.2f}</div>'
                        f'<div style="font-size:9px;color:var(--texto-apagado);">xG rival</div></div>'
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    # Reglas
                    st.markdown(
                        f'<div style="background:var(--bg-tarjeta);border:1px solid var(--borde);border-radius:6px;'
                        f'padding:10px 14px;">'
                        f'<div style="font-size:10px;color:var(--acento-morado);font-weight:800;letter-spacing:2px;'
                        f'border-bottom:2px solid var(--acento-dorado);padding-bottom:5px;margin-bottom:8px;">'
                        f'◈ REGLAS DE DOMINANCIA</div>'
                        f'{_detalle_reglas(reglas)}'
                        f'<div style="margin-top:8px;text-align:right;font-size:10px;color:var(--texto-apagado);">'
                        f'Reglas: <b style="color:{"#22c55e" if n_ok >= 3 else "#f59e0b"};font-size:16px;">{n_ok}</b>/4'
                        f'</div></div>',
                        unsafe_allow_html=True,
                    )

                with col_der:
                    edge_col2 = _GREEN if edge_o15 >= 6 else (_YELLOW if edge_o15 >= 0 else _RED)
                    st.markdown(
                        f'<div style="background:var(--bg-tarjeta);border:1px solid var(--borde);border-radius:6px;'
                        f'padding:10px 14px;margin-bottom:8px;">'
                        f'<div style="font-size:10px;color:var(--acento-morado);font-weight:800;letter-spacing:2px;'
                        f'border-bottom:2px solid var(--acento-dorado);padding-bottom:5px;margin-bottom:8px;">'
                        f'◈ MERCADOS</div>'
                        f'<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--borde);">'
                        f'<span style="font-size:11px;color:{paleta["texto"]};">Over 1.5 goles</span>'
                        f'<span style="font-size:13px;font-weight:700;color:{_GREEN};">{p_o15:.1f}%</span></div>'
                        f'<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--borde);">'
                        f'<span style="font-size:11px;color:{paleta["texto"]};">Victoria {nom_fav[:12]}</span>'
                        f'<span style="font-size:13px;font-weight:700;color:{_GREEN};">{p_vic:.1f}%</span></div>'
                        f'<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--borde);">'
                        f'<span style="font-size:11px;color:{paleta["texto"]};">Hándicap −1</span>'
                        f'<span style="font-size:13px;font-weight:700;color:{_GREEN};">{p_hcp:.1f}%</span></div>'
                        f'<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--borde);">'
                        f'<span style="font-size:11px;color:{paleta["texto"]};">Cuota O1.5</span>'
                        f'<span style="font-size:13px;font-weight:700;color:#b8780f;">{cuota_o15:.2f}</span></div>'
                        f'<div style="display:flex;justify-content:space-between;padding:5px 0;">'
                        f'<span style="font-size:11px;color:{paleta["texto"]};">Edge O1.5</span>'
                        f'<span style="font-size:13px;font-weight:700;color:{edge_col2};">{sign_e}{edge_o15:.1f}%</span></div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    # Marcador más probable
                    st.markdown(
                        f'<div style="background:var(--bg-tarjeta);border:1px solid var(--borde);border-radius:6px;'
                        f'padding:10px 14px;text-align:center;">'
                        f'<div style="font-size:10px;color:var(--acento-morado);font-weight:800;letter-spacing:2px;margin-bottom:8px;">'
                        f'◈ MARCADOR MÁS PROBABLE</div>'
                        f'<div style="font-size:36px;font-weight:900;color:#b8780f;">{top_m}</div>'
                        f'<div style="font-size:11px;color:var(--texto-apagado);margin-top:4px;">{top_p:.1f}% probabilidad</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    # Veredicto
                    st.markdown(
                        f'<div style="background:var(--bg-tarjeta);border:2px solid {col_v};border-radius:6px;'
                        f'padding:12px;text-align:center;margin-top:8px;">'
                        f'<div style="font-size:20px;font-weight:900;color:{col_v};">{estado}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

    controles_paginacion("dh_pagina", pagina_actual, total_paginas, sufijo="_bottom")
