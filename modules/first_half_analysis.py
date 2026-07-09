"""Módulo: Análisis Primera Parte — calculadora de mercados HT (1X2, O/U goles, primer marcador).

Módulo standalone y desacoplado del sistema de señales de BetVision AI:
no importa nada de claude_analysis, del modelo Poisson (predictive_model /
match_dashboard), del sistema de puntuación, de dominant_bet ni de
value_scanner. Solo calcula probabilidad implícita, overround y
probabilidad normalizada a partir de cuotas introducidas manualmente.
No calcula edge ni genera veredictos, semáforos, score ni confianza.

Fase 2 añade un análisis descriptivo con Claude API (llamada propia e
independiente — no reutiliza el cliente ni las funciones de
modules/claude_analysis.py) que solo compara, en prosa, lo que el mercado
implica frente a los datos estadísticos introducidos aquí mismo.
"""

import html
import os

import anthropic
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

RANGO_OVERROUND = (1.00, 1.25)   # 100 % – 125 %

AVISO_PERMANENTE = (
    "Módulo informativo. Los mercados de 1ª Parte no forman parte del sistema "
    "oficial de señales de BetVision AI y no generan recomendaciones automáticas."
)

# ── Configuración Claude API — independiente de modules/claude_analysis.py ────
API_KEY_FH      = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL_FH = "claude-sonnet-4-6"

_PALABRAS_PROHIBIDAS = ["apostar", "no apostar", "recomiendo", "hay valor", "edge", "señal"]

_SYSTEM_PROMPT_FH = f"""Eres un analista de datos deportivos especializado en describir mercados
de 1ª parte de fútbol. Tu única tarea es comparar, en prosa neutral y objetiva, lo que las
cuotas del mercado implican (probabilidades normalizadas) frente a lo que muestran los datos
estadísticos introducidos manualmente por el usuario sobre cada equipo.

REGLAS ESTRICTAS E INNEGOCIABLES:
- Tu análisis es puramente DESCRIPTIVO. Señala coincidencias o discrepancias entre mercado y
  datos, nunca sugieras ni insinúes qué hacer con esa información.
- Tienes PROHIBIDO usar, en cualquier forma, conjugación o sinónimo equivalente, estas
  palabras: {", ".join(f'"{p}"' for p in _PALABRAS_PROHIBIDAS)}. Tampoco actúes como si
  estuvieras aconsejando una apuesta.
- No uses semáforos, puntuaciones, niveles de confianza ni veredictos finales.
- No calcules ni menciones ningún edge, ventaja o rentabilidad esperada.
- Si para un mercado o equipo no hay datos suficientes, dilo explícitamente y no lo compares.
- Máximo 250 palabras. Responde siempre en español, en prosa clara y directa."""


def _calcular_mercado(cuotas: dict) -> dict | None:
    """
    cuotas: {etiqueta: cuota} con TODAS las cuotas del mercado ya introducidas (>= 1.01).
    Devuelve implícitas / overround / normalizadas, o None si falta alguna cuota.
    """
    if not cuotas or any(v < 1.01 for v in cuotas.values()):
        return None
    implicitas = {k: 1.0 / v for k, v in cuotas.items()}
    overround = sum(implicitas.values())
    en_rango = RANGO_OVERROUND[0] <= overround <= RANGO_OVERROUND[1]
    normalizadas = {k: p / overround for k, p in implicitas.items()} if en_rango else {}
    return {
        "implicitas": implicitas,
        "overround": overround,
        "en_rango": en_rango,
        "normalizadas": normalizadas,
    }


def _tabla_html(cuotas: dict, resultado: dict) -> str:
    """Genera la tabla Resultado | Cuota | Prob. implícita | Prob. ajustada."""
    filas = ""
    for etiqueta, cuota in cuotas.items():
        implicita = resultado["implicitas"][etiqueta]
        ajustada = resultado["normalizadas"].get(etiqueta)
        ajustada_txt = f"{ajustada * 100:.1f}%" if ajustada is not None else "—"
        filas += (
            f'<tr><td class="col-resultado">{etiqueta}</td>'
            f'<td>{cuota:.2f}</td>'
            f'<td>{implicita * 100:.1f}%</td>'
            f'<td>{ajustada_txt}</td></tr>'
        )
    return (
        '<table class="tabla-cuotas"><thead><tr>'
        '<th>Resultado</th><th>Cuota</th><th>Prob. implícita</th><th>Prob. ajustada</th>'
        '</tr></thead><tbody>' + filas + '</tbody></table>'
    )


def _seccion_mercado(titulo: str, campos: list[tuple[str, str]], key_prefix: str) -> dict | None:
    """
    Renderiza el formulario de cuotas de un mercado y su tabla de probabilidades.
    campos: lista de (etiqueta, sufijo_key). Devuelve el resultado de
    _calcular_mercado (o None) para el panel comparativo.
    """
    st.markdown(f'<div class="titulo-tarjeta">{titulo}</div>', unsafe_allow_html=True)

    cols = st.columns(len(campos))
    cuotas_introducidas: dict = {}
    for col, (etiqueta, sufijo) in zip(cols, campos):
        key = f"{key_prefix}_{sufijo}"
        with col:
            cuota = st.number_input(
                etiqueta, min_value=0.0, max_value=100.0,
                value=st.session_state.get(key, 0.0), step=0.01, key=key,
                help="Deja en 0 si no tienes esta cuota",
            )
        if cuota >= 1.01:
            cuotas_introducidas[etiqueta] = cuota

    if len(cuotas_introducidas) < len(campos):
        st.caption("Introduce todas las cuotas del mercado para calcular probabilidades.")
        return None

    resultado = _calcular_mercado(cuotas_introducidas)
    if resultado is None:
        return None
    resultado["cuotas"] = cuotas_introducidas

    if not resultado["en_rango"]:
        st.markdown(
            '<div class="alerta-peligro">⚠️ Revisar cuotas introducidas '
            f'(overround {resultado["overround"] * 100:.1f}%, fuera del rango 100–125%)</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(_tabla_html(cuotas_introducidas, resultado), unsafe_allow_html=True)

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    return resultado


def _seccion_stats_equipo(nombre_default: str, key_prefix: str) -> dict:
    """Bloque de datos estadísticos opcionales por equipo (fuente manual: BeSoccer/Flashscore/SofaScore)."""
    nombre = st.text_input(
        "Nombre del equipo",
        value=st.session_state.get(f"{key_prefix}_nombre", nombre_default),
        key=f"{key_prefix}_nombre",
    )

    col_a, col_b = st.columns(2)
    with col_a:
        pct_marca = st.number_input(
            "% partidos marcando en 1ª parte", min_value=0, max_value=100,
            value=st.session_state.get(f"{key_prefix}_pct_marca", 0),
            step=1, key=f"{key_prefix}_pct_marca",
        )
        pct_marca_primero = st.number_input(
            "% partidos que marca primero", min_value=0, max_value=100,
            value=st.session_state.get(f"{key_prefix}_pct_marca_primero", 0),
            step=1, key=f"{key_prefix}_pct_marca_primero",
        )
        goles_030 = st.number_input(
            "Goles en primeros 30'", min_value=0, max_value=50,
            value=st.session_state.get(f"{key_prefix}_goles_030", 0),
            step=1, key=f"{key_prefix}_goles_030",
        )
    with col_b:
        pct_encaja = st.number_input(
            "% partidos encajando en 1ª parte", min_value=0, max_value=100,
            value=st.session_state.get(f"{key_prefix}_pct_encaja", 0),
            step=1, key=f"{key_prefix}_pct_encaja",
        )
        pct_recibe_primero = st.number_input(
            "% partidos que recibe primero", min_value=0, max_value=100,
            value=st.session_state.get(f"{key_prefix}_pct_recibe_primero", 0),
            step=1, key=f"{key_prefix}_pct_recibe_primero",
        )
        goles_3145 = st.number_input(
            "Goles en minutos 31'-45'", min_value=0, max_value=50,
            value=st.session_state.get(f"{key_prefix}_goles_3145", 0),
            step=1, key=f"{key_prefix}_goles_3145",
        )

    return {
        "nombre": nombre,
        "pct_marca": pct_marca,
        "pct_encaja": pct_encaja,
        "pct_marca_primero": pct_marca_primero,
        "pct_recibe_primero": pct_recibe_primero,
        "goles_030": goles_030,
        "goles_3145": goles_3145,
    }


def _panel_comparativo(resultados_mercados: dict, stats_local: dict, stats_visit: dict) -> None:
    """Panel descriptivo Mercado vs Datos — sin veredictos ni cálculo de edge."""
    st.markdown('<div class="titulo-tarjeta">📊 Mercado vs Datos</div>', unsafe_allow_html=True)
    col_mercado, col_datos = st.columns(2)

    with col_mercado:
        st.markdown(
            '<div class="etiqueta-seccion">Probabilidades normalizadas (mercado)</div>',
            unsafe_allow_html=True,
        )
        for titulo, resultado in resultados_mercados.items():
            if resultado is None or not resultado["en_rango"]:
                st.markdown(
                    f'<div class="fila-prob"><span class="texto-apagado">{titulo}:</span> '
                    f'<span class="texto-apagado">sin datos válidos</span></div>',
                    unsafe_allow_html=True,
                )
                continue
            partes = " · ".join(f"{k} {v * 100:.1f}%" for k, v in resultado["normalizadas"].items())
            st.markdown(
                f'<div class="fila-prob"><span class="texto-apagado">{titulo}:</span> <span>{partes}</span></div>',
                unsafe_allow_html=True,
            )

    with col_datos:
        st.markdown(
            '<div class="etiqueta-seccion">Datos estadísticos introducidos</div>',
            unsafe_allow_html=True,
        )
        for stats in (stats_local, stats_visit):
            st.markdown(
                f'<div class="fila-prob" style="margin-top:6px;"><b>{stats["nombre"]}</b></div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="fila-prob"><span class="texto-apagado">Marca en 1ªP:</span> '
                f'<span>{stats["pct_marca"]}%</span> · '
                f'<span class="texto-apagado">Encaja en 1ªP:</span> <span>{stats["pct_encaja"]}%</span></div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="fila-prob"><span class="texto-apagado">Marca primero:</span> '
                f'<span>{stats["pct_marca_primero"]}%</span> · '
                f'<span class="texto-apagado">Recibe primero:</span> <span>{stats["pct_recibe_primero"]}%</span></div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="fila-prob"><span class="texto-apagado">Goles 0-30\':</span> '
                f'<span>{stats["goles_030"]}</span> · '
                f'<span class="texto-apagado">Goles 31-45\':</span> <span>{stats["goles_3145"]}</span></div>',
                unsafe_allow_html=True,
            )


def _stats_rellenados(stats: dict) -> dict:
    """Devuelve solo los campos estadísticos que el usuario realmente rellenó (valor > 0)."""
    campos = {
        "% marca en 1ª parte":  stats["pct_marca"],
        "% encaja en 1ª parte": stats["pct_encaja"],
        "% marca primero":      stats["pct_marca_primero"],
        "% recibe primero":     stats["pct_recibe_primero"],
        "goles 0-30'":          stats["goles_030"],
        "goles 31-45'":         stats["goles_3145"],
    }
    return {k: v for k, v in campos.items() if v}


def _construir_prompt_ia(resultados_mercados: dict, stats_local: dict, stats_visit: dict) -> str:
    """
    Arma el mensaje de usuario para Claude con: cuotas + probabilidades normalizadas de
    los mercados válidos, datos estadísticos rellenados por equipo, y — solo si ya existen
    en session_state por haber usado el análisis principal — xG y forma reciente del
    partido como contexto adicional opcional. Solo lee session_state, no importa módulos.
    """
    bloques_mercado = []
    for titulo, resultado in resultados_mercados.items():
        if resultado is None or not resultado.get("en_rango"):
            continue
        cuotas_txt = ", ".join(f"{k} @ {v:.2f}" for k, v in resultado["cuotas"].items())
        norm_txt   = ", ".join(f"{k} {v * 100:.1f}%" for k, v in resultado["normalizadas"].items())
        bloques_mercado.append(
            f"- {titulo}: cuotas ({cuotas_txt}) · overround {resultado['overround'] * 100:.1f}% "
            f"· probabilidad normalizada ({norm_txt})"
        )

    bloques_stats = []
    for stats in (stats_local, stats_visit):
        rellenos = _stats_rellenados(stats)
        if rellenos:
            datos_txt = ", ".join(f"{k}: {v}" for k, v in rellenos.items())
            bloques_stats.append(f"- {stats['nombre']}: {datos_txt}")

    contexto_extra = []
    probs_partido = st.session_state.get("probs_partido", {})
    xg_local = probs_partido.get("xg_local")
    xg_visit = probs_partido.get("xg_visitante")
    if xg_local is not None and xg_visit is not None:
        contexto_extra.append(f"- xG del partido completo (análisis principal): local {xg_local}, visitante {xg_visit}")
    forma_local = st.session_state.get("claude_forma_local")
    forma_visit = st.session_state.get("claude_forma_visit")
    if forma_local and forma_visit:
        contexto_extra.append(f"- Forma reciente (análisis principal): local {forma_local}, visitante {forma_visit}")

    partes = ["MERCADOS DE 1ª PARTE (cuotas y probabilidades normalizadas):"]
    partes += bloques_mercado if bloques_mercado else ["(ninguno con overround válido)"]
    partes.append("\nDATOS ESTADÍSTICOS POR EQUIPO (introducidos manualmente por el usuario):")
    partes += bloques_stats if bloques_stats else ["(sin datos estadísticos introducidos)"]
    if contexto_extra:
        partes.append("\nCONTEXTO ADICIONAL OPCIONAL (partido completo, solo informativo):")
        partes += contexto_extra

    return "\n".join(partes)


def _analisis_ia_primera_parte(resultados_mercados: dict, stats_local: dict, stats_visit: dict) -> str:
    """
    Llama a Claude API (cliente propio, independiente de modules/claude_analysis.py)
    para obtener un análisis descriptivo de discrepancias entre mercado y datos.
    No calcula ni permite edge, semáforo, score, confianza ni veredictos de apuesta.
    """
    if not API_KEY_FH:
        raise RuntimeError("Falta configurar ANTHROPIC_API_KEY.")

    client = anthropic.Anthropic(api_key=API_KEY_FH)
    prompt_usuario = _construir_prompt_ia(resultados_mercados, stats_local, stats_visit)

    message = client.messages.create(
        model=CLAUDE_MODEL_FH,
        max_tokens=500,
        system=_SYSTEM_PROMPT_FH,
        messages=[{"role": "user", "content": prompt_usuario}],
        timeout=45.0,
    )
    return message.content[0].text


def _seccion_analisis_ia(resultados_mercados: dict, stats_local: dict, stats_visit: dict) -> None:
    """Botón + resultado del análisis descriptivo con IA (Fase 2)."""
    st.markdown('<div class="titulo-tarjeta">🧠 Análisis Descriptivo con IA</div>', unsafe_allow_html=True)

    hay_mercado_valido = any(
        r is not None and r.get("en_rango") for r in resultados_mercados.values()
    )
    if not hay_mercado_valido:
        st.caption(
            "Introduce al menos un mercado completo con cuotas válidas "
            "(overround 100–125%) para habilitar el análisis con IA."
        )

    if st.button("🧠 Analizar con IA", key="btn_fh_analizar_ia",
                 use_container_width=True, disabled=not hay_mercado_valido):
        with st.spinner("Analizando discrepancias entre mercado y datos…"):
            try:
                texto = _analisis_ia_primera_parte(resultados_mercados, stats_local, stats_visit)
                st.session_state["fh_analisis_ia"] = texto
            except anthropic.AuthenticationError:
                st.session_state.pop("fh_analisis_ia", None)
                st.error("⚠️ API key de Claude inválida o no configurada. Revisa ANTHROPIC_API_KEY.")
            except Exception:
                st.session_state.pop("fh_analisis_ia", None)
                st.error("⚠️ No se pudo completar el análisis con IA en este momento. Inténtalo de nuevo.")

    analisis_guardado = st.session_state.get("fh_analisis_ia")
    if analisis_guardado:
        texto_seguro = html.escape(analisis_guardado).replace("\n", "<br>")
        st.markdown(
            f'<div class="alerta-exito" style="white-space:pre-wrap;line-height:1.7;">{texto_seguro}</div>',
            unsafe_allow_html=True,
        )


def mostrar() -> None:
    """Renderiza el módulo completo de Análisis Primera Parte."""
    st.markdown(f'<div class="alerta-exito">ℹ️ {AVISO_PERMANENTE}</div>', unsafe_allow_html=True)

    st.markdown('<div class="tarjeta">', unsafe_allow_html=True)
    res_1x2 = _seccion_mercado(
        "Resultado al Descanso (1X2 HT)",
        [("Local", "local"), ("Empate", "empate"), ("Visitante", "visitante")],
        "fh_1x2",
    )
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="tarjeta">', unsafe_allow_html=True)
    res_ou05 = _seccion_mercado(
        "Over/Under 0.5 Goles HT",
        [("Over 0.5", "over"), ("Under 0.5", "under")],
        "fh_ou05",
    )
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="tarjeta">', unsafe_allow_html=True)
    res_ou15 = _seccion_mercado(
        "Over/Under 1.5 Goles HT",
        [("Over 1.5", "over"), ("Under 1.5", "under")],
        "fh_ou15",
    )
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="tarjeta">', unsafe_allow_html=True)
    res_1marca = _seccion_mercado(
        "Primer Equipo en Marcar",
        [("Local", "local"), ("Visitante", "visitante"), ("Ninguno", "ninguno")],
        "fh_1marca",
    )
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="tarjeta">', unsafe_allow_html=True)
    st.markdown(
        '<div class="titulo-tarjeta">Datos Estadísticos por Equipo (opcional)</div>',
        unsafe_allow_html=True,
    )
    st.caption("Fuente manual: BeSoccer / Flashscore / SofaScore")
    col_l, col_v = st.columns(2)
    with col_l:
        stats_local = _seccion_stats_equipo("Local", "fh_stat_local")
    with col_v:
        stats_visit = _seccion_stats_equipo("Visitante", "fh_stat_visit")
    st.markdown('</div>', unsafe_allow_html=True)

    resultados_mercados = {
        "1X2 HT": res_1x2,
        "O/U 0.5 HT": res_ou05,
        "O/U 1.5 HT": res_ou15,
        "Primer en marcar": res_1marca,
    }

    st.markdown('<div class="tarjeta">', unsafe_allow_html=True)
    _panel_comparativo(resultados_mercados, stats_local, stats_visit)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="tarjeta">', unsafe_allow_html=True)
    _seccion_analisis_ia(resultados_mercados, stats_local, stats_visit)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(f'<div class="alerta-exito">ℹ️ {AVISO_PERMANENTE}</div>', unsafe_allow_html=True)
