"""Módulo: Alertas y Retiradas — carga datos desde data/history.csv"""

import os
from datetime import date
from pathlib import Path
import pandas as pd
import streamlit as st

RUTA_HISTORIAL  = Path(__file__).parent.parent / "data" / "history.csv"
RESULTADOS      = ["Ganado", "Perdido", "Pendiente"]
_COLS_HISTORIAL = ["fecha", "evento", "apuesta", "resultado", "ganancia"]

os.makedirs(RUTA_HISTORIAL.parent, exist_ok=True)
if not RUTA_HISTORIAL.exists():
    pd.DataFrame(columns=_COLS_HISTORIAL).to_csv(RUTA_HISTORIAL, index=False)


@st.cache_data
def cargar_historial() -> pd.DataFrame:
    """Carga el CSV de historial de apuestas."""
    try:
        df = pd.read_csv(RUTA_HISTORIAL)
        df["ganancia"] = pd.to_numeric(df["ganancia"], errors="coerce").fillna(0)
        return df
    except Exception:
        return pd.DataFrame(columns=_COLS_HISTORIAL)


def _ganancia_segun_resultado(resultado: str, valor: float) -> float:
    """
    Convierte el valor introducido por el usuario en la ganancia real a guardar:
      Ganado   →  +valor
      Perdido  →  -valor
      Pendiente→   0
    """
    if resultado == "Ganado":
        return abs(valor)
    if resultado == "Perdido":
        return -abs(valor)
    return 0.0   # Pendiente


def _registrar_apuesta(fecha: str, evento: str, apuesta: str,
                       resultado: str, ganancia: float) -> None:
    """Añade una nueva fila al historial CSV y limpia el caché."""
    nueva = pd.DataFrame([{
        "fecha":     fecha,
        "evento":    evento,
        "apuesta":   apuesta,
        "resultado": resultado,
        "ganancia":  _ganancia_segun_resultado(resultado, ganancia),
    }])
    try:
        df = pd.read_csv(RUTA_HISTORIAL)
        df["ganancia"] = pd.to_numeric(df["ganancia"], errors="coerce").fillna(0)
    except Exception:
        df = pd.DataFrame(columns=_COLS_HISTORIAL)
    df = pd.concat([nueva, df], ignore_index=True)
    df.to_csv(RUTA_HISTORIAL, index=False)
    cargar_historial.clear()


def _actualizar_apuesta(indice: int, resultado: str, ganancia: float) -> None:
    """Actualiza resultado y ganancia de una fila existente en el historial."""
    try:
        df = pd.read_csv(RUTA_HISTORIAL)
        df["ganancia"] = pd.to_numeric(df["ganancia"], errors="coerce").fillna(0)
    except Exception:
        return
    if indice >= len(df):
        return
    df.at[indice, "resultado"] = resultado
    df.at[indice, "ganancia"]  = _ganancia_segun_resultado(resultado, ganancia)
    df.to_csv(RUTA_HISTORIAL, index=False)
    cargar_historial.clear()


def evaluar_estado_bankroll(df: pd.DataFrame) -> tuple[str, list[tuple[str, str]]]:
    """Analiza las últimas apuestas y devuelve estado y alertas."""
    alertas: list[tuple[str, str]] = []
    # Solo consideramos Ganado/Perdido para las alertas (ignoramos Pendiente)
    resueltas = df[df["resultado"].isin(["Ganado", "Perdido"])]["resultado"].head(6).tolist()

    perdidas_seguidas = 0
    for r in resueltas:
        if r == "Perdido":
            perdidas_seguidas += 1
        else:
            break

    if perdidas_seguidas >= 3:
        alertas.append(("peligro",
            f"¡Alerta! {perdidas_seguidas} Pérdidas Seguidas — Pausa y Reevalúa"))

    ganancias_hoy = df[df["resultado"] == "Ganado"]["ganancia"].head(3).sum()
    if ganancias_hoy >= 80:
        alertas.append(("exito", "Objetivo Diario Alcanzado — Retírate"))

    victorias = sum(1 for r in resueltas if r == "Ganado")
    derrotas  = len(resueltas) - victorias

    if perdidas_seguidas >= 3:
        estado = "Riesgo Controlado"
    elif derrotas > victorias:
        estado = "Riesgo Elevado"
    elif victorias >= 4:
        estado = "En Racha Positiva"
    else:
        estado = "Neutral"

    return estado, alertas


def _color_resultado(resultado: str) -> str:
    if resultado == "Ganado":    return "#00aa44"
    if resultado == "Perdido":   return "#ff4455"
    return "#ffd700"   # Pendiente → amarillo


def _formulario_registro():
    """Formulario para registrar una nueva apuesta."""
    st.markdown('<div class="etiqueta-seccion">Registrar nueva apuesta</div>',
                unsafe_allow_html=True)

    with st.form("form_apuesta", clear_on_submit=True):
        col_f, col_e = st.columns([1, 2])
        with col_f:
            fecha = st.text_input("Fecha", value=date.today().strftime("%d/%m/%Y"),
                                  key="reg_fecha")
        with col_e:
            evento = st.text_input("Evento (ej. Real Madrid vs Barcelona)", key="reg_evento")

        col_a, col_r = st.columns([2, 1])
        with col_a:
            apuesta = st.text_input("Tipo de apuesta (ej. Ganador Local)", key="reg_apuesta")
        with col_r:
            resultado = st.selectbox("Resultado", RESULTADOS, key="reg_resultado")

        ganancia = st.number_input(
            "Ganancia/Pérdida (€) — valor positivo (0 si es Pendiente)",
            min_value=0.0, max_value=99999.0, step=1.0, key="reg_ganancia",
        )

        enviado = st.form_submit_button("Registrar Apuesta", use_container_width=True)

    if enviado:
        if not evento.strip() or not apuesta.strip():
            st.warning("Completa el evento y el tipo de apuesta antes de registrar.")
        else:
            _registrar_apuesta(fecha, evento.strip(), apuesta.strip(), resultado, ganancia)
            st.success(f"Apuesta registrada: {evento} — {resultado}")
            st.rerun()

    st.markdown("<hr style='border-color:#2a2f3e;margin:14px 0'>", unsafe_allow_html=True)


def _tabla_historial_con_edicion(df: pd.DataFrame) -> None:
    """
    Renderiza el historial con botones Editar por fila.
    Usa st.columns para que los botones Streamlit funcionen dentro de la tabla.
    """
    # Cabecera
    hdr = st.columns([1.1, 2.2, 1.6, 1.1, 0.9, 0.6])
    for col, label in zip(hdr, ["Fecha", "Evento", "Apuesta", "Resultado", "Ganancia", ""]):
        col.markdown(
            f'<div style="font-size:10px;color:#00aa44;font-weight:700;'
            f'text-transform:uppercase;padding:2px 0;">{label}</div>',
            unsafe_allow_html=True,
        )
    st.markdown("<hr style='border-color:#1e3a2a;margin:3px 0 4px'>", unsafe_allow_html=True)

    editando = st.session_state.get("editando_fila", None)

    for i, (_, fila) in enumerate(df.iterrows()):
        resultado  = fila["resultado"]
        ganancia   = fila["ganancia"]
        col_res    = _color_resultado(resultado)
        signo      = "+" if ganancia > 0 else ""
        gan_txt    = f"{signo}€{abs(ganancia):.0f}" if resultado != "Pendiente" else "—"

        cols = st.columns([1.1, 2.2, 1.6, 1.1, 0.9, 0.6])
        cols[0].markdown(f'<div style="font-size:11px;padding:3px 0;">{fila["fecha"]}</div>',
                         unsafe_allow_html=True)
        cols[1].markdown(f'<div style="font-size:11px;padding:3px 0;">{fila["evento"]}</div>',
                         unsafe_allow_html=True)
        cols[2].markdown(f'<div style="font-size:11px;padding:3px 0;">{fila["apuesta"]}</div>',
                         unsafe_allow_html=True)
        cols[3].markdown(
            f'<div style="font-size:11px;font-weight:700;color:{col_res};padding:3px 0;">'
            f'{resultado}</div>',
            unsafe_allow_html=True,
        )
        cols[4].markdown(
            f'<div style="font-size:11px;font-weight:700;color:'
            f'{"#00aa44" if ganancia > 0 else ("#ff4455" if ganancia < 0 else "#ffd700")}'
            f';padding:3px 0;">{gan_txt}</div>',
            unsafe_allow_html=True,
        )
        if cols[5].button("✏️", key=f"btn_edit_{i}", help="Editar esta apuesta"):
            st.session_state["editando_fila"] = i
            st.rerun()

        # Formulario de edición inline (aparece debajo de la fila seleccionada)
        if editando == i:
            with st.container():
                st.markdown(
                    f'<div style="background:#1a2820;border:1px solid #00aa44;'
                    f'border-radius:6px;padding:10px 12px;margin:4px 0 8px;">'
                    f'<div style="font-size:11px;color:#00aa44;font-weight:700;'
                    f'margin-bottom:8px;">✏️ Editando: {fila["evento"]}</div></div>',
                    unsafe_allow_html=True,
                )
                with st.form(f"form_editar_{i}", clear_on_submit=False):
                    idx_actual = RESULTADOS.index(resultado) if resultado in RESULTADOS else 2
                    nuevo_res  = st.selectbox("Nuevo resultado", RESULTADOS,
                                              index=idx_actual, key=f"edit_res_{i}")
                    nueva_gan  = st.number_input(
                        "Ganancia/Pérdida (€) — valor positivo",
                        min_value=0.0, max_value=99999.0,
                        value=abs(float(ganancia)), step=1.0, key=f"edit_gan_{i}",
                    )
                    col_g, col_c = st.columns(2)
                    guardar   = col_g.form_submit_button("💾 Guardar", use_container_width=True)
                    cancelar  = col_c.form_submit_button("✕ Cancelar", use_container_width=True)

                if guardar:
                    _actualizar_apuesta(i, nuevo_res, nueva_gan)
                    del st.session_state["editando_fila"]
                    st.success("Apuesta actualizada.")
                    st.rerun()
                if cancelar:
                    del st.session_state["editando_fila"]
                    st.rerun()


def mostrar():
    """Renderiza el módulo completo de Alertas y Retiradas."""
    _formulario_registro()

    df_historial = cargar_historial()
    estado, alertas = evaluar_estado_bankroll(df_historial)

    # ── Estado actual ──
    col_etq, col_val = st.columns([1, 2])
    with col_etq:
        st.markdown('<span class="texto-apagado" style="font-size:13px;">Estado Actual:</span>',
                    unsafe_allow_html=True)
    with col_val:
        color_estado = "#ef5350" if "Elevado" in estado else "#00e676"
        st.markdown(
            f'<span class="insignia-estado" style="color:{color_estado};border-color:{color_estado};">'
            f'{estado}</span>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── Alertas ──
    for tipo_alerta, mensaje in alertas:
        icono = "🔴" if tipo_alerta == "peligro" else "✅"
        clase = "alerta-peligro" if tipo_alerta == "peligro" else "alerta-exito"
        st.markdown(f'<div class="{clase}">{icono} {mensaje}</div>', unsafe_allow_html=True)

    # ── Historial con edición ──
    st.markdown('<div class="etiqueta-seccion" style="margin-top:16px;">Historial Reciente</div>',
                unsafe_allow_html=True)

    if df_historial.empty:
        st.caption("Aún no hay apuestas registradas. Usa el formulario para añadir la primera.")
    else:
        _tabla_historial_con_edicion(df_historial)

    # ── Control de Bankroll ──
    st.markdown('<div class="etiqueta-seccion" style="margin-top:18px;">Control de Bankroll</div>',
                unsafe_allow_html=True)

    saldo_actual = st.session_state.get("saldo", 200.0)
    col_izq, col_der = st.columns(2)
    with col_izq:
        porcentaje_stake = st.slider("% Bankroll por apuesta", 1, 10, 2, key="pct_stake")
        stake_sugerido   = round(saldo_actual * porcentaje_stake / 100, 2)
        st.markdown(f'<div class="texto-azul">Stake sugerido: <b>€{stake_sugerido:.2f}</b></div>',
                    unsafe_allow_html=True)
    with col_der:
        limite_perdida = st.slider("Stop-loss diario (€)", 10, 200, 50, key="stop_loss")
        st.markdown(f'<div class="texto-rojo">Detener si pierdes: <b>€{limite_perdida}</b></div>',
                    unsafe_allow_html=True)

    # Resumen estadístico (excluye Pendientes del cálculo)
    total_ganado  = df_historial[df_historial["resultado"] == "Ganado"]["ganancia"].sum()
    total_perdido = df_historial[df_historial["resultado"] == "Perdido"]["ganancia"].sum()
    pendientes    = len(df_historial[df_historial["resultado"] == "Pendiente"])
    neto          = total_ganado + total_perdido

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Ganado",  f"+€{total_ganado:.0f}")
    col2.metric("Total Perdido", f"€{total_perdido:.0f}")
    col3.metric("Neto",          f"€{neto:.0f}")
    col4.metric("Pendientes",    str(pendientes))
