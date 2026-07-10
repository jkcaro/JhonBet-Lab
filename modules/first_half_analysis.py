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

Streamlit instalado: 1.58.0 (ver pip show streamlit). Esa versión soporta
nativamente st.number_input(value=None, placeholder=...) devolviendo None
mientras el campo esté vacío — es el camino usado en todo el módulo para
que "dato ausente" nunca se confunda con "0". No hace falta el fallback de
text_input + validación manual ni un checkbox "sin datos" por bloque.
"""

import os

import anthropic
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

RANGO_OVERROUND = (1.00, 1.25)   # 100 % – 125 %
_UMBRAL_DIFERENCIA_PP = 10.0      # puntos porcentuales para la observación de la comparación real

AVISO_PERMANENTE = (
    "Módulo informativo. Los mercados de 1ª Parte no forman parte del sistema "
    "oficial de señales de BetVision AI y no generan recomendaciones automáticas."
)

# Definición única de los 4 mercados: (clave, título visible, campos [(etiqueta, sufijo_key)], prefijo_key).
# Se usa tanto para renderizar los formularios como para el resumen de estado (leído de
# session_state antes de que los widgets de este mismo rerun se hayan vuelto a instanciar).
_DEFINICIONES_MERCADOS = [
    ("1X2 HT", "Resultado al Descanso (1X2 HT)",
     [("Local", "local"), ("Empate", "empate"), ("Visitante", "visitante")], "fh_1x2"),
    ("O/U 0.5 HT", "Over/Under 0.5 Goles HT",
     [("Over 0.5", "over"), ("Under 0.5", "under")], "fh_ou05"),
    ("O/U 1.5 HT", "Over/Under 1.5 Goles HT",
     [("Over 1.5", "over"), ("Under 1.5", "under")], "fh_ou15"),
    ("Primer en marcar", "Primer Equipo en Marcar",
     [("Local", "local"), ("Visitante", "visitante"), ("Ninguno", "ninguno")], "fh_1marca"),
]

_CAMPOS_STATS = ["pct_marca", "pct_encaja", "pct_marca_primero", "pct_recibe_primero", "goles_030", "goles_3145"]

_PALETA_BARRAS = ["#2563eb", "#f5a623", "#64748b", "#0d9488"]

# ── Configuración Claude API — independiente de modules/claude_analysis.py ────
API_KEY_FH      = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL_FH = "claude-sonnet-4-6"

_PALABRAS_PROHIBIDAS = ["apostar", "no apostar", "recomiendo", "hay valor", "edge", "señal"]

_SYSTEM_PROMPT_FH = f"""Eres un analista de datos deportivos. Describes, en lenguaje llano y
cercano, lo que las cuotas de los mercados de 1ª parte de un partido de fútbol reflejan y cómo
se compara eso con los datos estadísticos que el usuario introdujo sobre cada equipo.

ESTRUCTURA OBLIGATORIA — responde EXACTAMENTE con estos 4 encabezados en markdown, en este
orden, y no añadas ningún otro encabezado ni texto fuera de ellos:

## Resumen
Un párrafo corto (2-4 líneas) con la idea general.

## Qué refleja el mercado
Describe las cuotas y probabilidades normalizadas en lenguaje llano. En vez de "el overround
indica...", escribe algo como "el margen aplicado por la casa es del X%, dentro de lo habitual"
(o "algo más alto de lo habitual" si corresponde).

## Qué dicen los datos
- Si el usuario introdujo datos estadísticos: esta debe ser la sección MÁS EXTENSA de toda la
  respuesta. Contrasta cada dato, número a número, contra la probabilidad de mercado
  correspondiente (por ejemplo: "el mercado sitúa a [equipo] marcando primero en un X%, mientras
  que su historial reciente lo sitúa en Y%").
- Si NO se introdujo ningún dato estadístico: dilo explícitamente ("no se introdujeron datos
  estadísticos para este partido") y describe en 2-3 líneas qué aportaría esa información si
  estuviera disponible.

## Limitaciones
Qué datos faltan y qué limita el análisis — por ejemplo, si solo hay xG del partido completo,
aclara que ese dato no debe extrapolarse directamente al descanso. Menciona qué mercados o
equipos se quedaron sin datos suficientes para comparar, si aplica.

REGLAS ESTRICTAS E INNEGOCIABLES:
- Tu análisis es puramente DESCRIPTIVO. Señala coincidencias o discrepancias entre mercado y
  datos, nunca sugieras ni insinúes qué hacer con esa información.
- Tienes PROHIBIDO usar, en cualquier forma, conjugación o sinónimo equivalente, estas
  palabras: {", ".join(f'"{p}"' for p in _PALABRAS_PROHIBIDAS)}. Tampoco actúes como si
  estuvieras aconsejando una apuesta.
- No uses semáforos, puntuaciones, niveles de confianza ni veredictos finales.
- No calcules ni menciones ningún edge, ventaja o rentabilidad esperada.
- Máximo 300 palabras en total. Responde siempre en español, en prosa clara y directa."""


# ── CSS scoped del módulo (no toca estilos globales de otras páginas) ─────────
_CSS_FH = """
<style>
.fh-tarjeta.tarjeta { padding: 10px 12px !important; margin-bottom: 6px !important; }
.fh-tarjeta .titulo-tarjeta { margin-bottom: 7px !important; padding-bottom: 5px !important; }
.fh-compact .fila-prob { margin: 3px 0 !important; }
</style>
"""


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


def _leer_cuotas_mercado(campos: list[tuple[str, str]], key_prefix: str) -> dict:
    """Lee de session_state las cuotas ya introducidas (>= 1.01) de un mercado. Ausente ≠ 0."""
    cuotas = {}
    for etiqueta, sufijo in campos:
        v = st.session_state.get(f"{key_prefix}_{sufijo}")
        if v is not None and v >= 1.01:
            cuotas[etiqueta] = v
    return cuotas


def _resultado_mercado(campos: list[tuple[str, str]], key_prefix: str) -> dict | None:
    """
    Calcula el resultado de un mercado leyendo session_state (sin renderizar widgets).
    Devuelve None si falta alguna cuota. Se usa tanto para el resumen de estado como,
    tras renderizar los inputs, dentro de _seccion_mercado.
    """
    cuotas = _leer_cuotas_mercado(campos, key_prefix)
    if len(cuotas) < len(campos):
        return None
    resultado = _calcular_mercado(cuotas)
    if resultado is not None:
        resultado["cuotas"] = cuotas
    return resultado


def _barra_probabilidad(etiqueta: str, pct: float, cuota: float, implicita_pct: float, color: str) -> str:
    """Tarjeta con porcentaje grande + barra horizontal proporcional (sustituye la tabla)."""
    ancho = max(5, min(int(round(pct)), 100))
    return (
        '<div class="cuota-card">'
        f'<div class="cuota-card-label">{etiqueta}</div>'
        f'<div class="cuota-card-value">{pct:.1f}%</div>'
        f'<div class="barra-fondo" style="height:7px;margin:5px 0 4px;">'
        f'<div class="barra-relleno" style="width:{ancho}%;background:{color};height:7px;"></div>'
        '</div>'
        f'<div class="cuota-card-sub">cuota {cuota:.2f} · impl. {implicita_pct:.1f}%</div>'
        '</div>'
    )


def _tarjetas_probabilidad(resultado: dict) -> None:
    """Fila de tarjetas (una por resultado) con barra proporcional y porcentaje grande."""
    outcomes = list(resultado["normalizadas"].items())
    cols = st.columns(len(outcomes))
    for i, (col, (etiqueta, prob)) in enumerate(zip(cols, outcomes)):
        cuota     = resultado["cuotas"][etiqueta]
        implicita = resultado["implicitas"][etiqueta] * 100
        color     = _PALETA_BARRAS[i % len(_PALETA_BARRAS)]
        with col:
            st.markdown(
                _barra_probabilidad(etiqueta, prob * 100, cuota, implicita, color),
                unsafe_allow_html=True,
            )


def _seccion_mercado(titulo: str, campos: list[tuple[str, str]], key_prefix: str) -> dict | None:
    """
    Renderiza — en una sola fila con st.columns — el formulario de cuotas de un mercado,
    y sus tarjetas de probabilidad inmediatamente debajo (misma tarjeta, no en otra sección).
    campos: lista de (etiqueta, sufijo_key). Devuelve el resultado de _resultado_mercado
    para el resumen de estado y el panel comparativo.
    """
    st.markdown(f'<div class="titulo-tarjeta">{titulo}</div>', unsafe_allow_html=True)

    cols = st.columns(len(campos))
    for col, (etiqueta, sufijo) in zip(cols, campos):
        key = f"{key_prefix}_{sufijo}"
        with col:
            st.number_input(
                etiqueta, min_value=0.0, max_value=100.0,
                value=st.session_state.get(key), step=0.01, key=key,
                placeholder="—", help="Cuota decimal (ej. 2.05). Vacío si no la tienes.",
            )

    resultado = _resultado_mercado(campos, key_prefix)
    if resultado is None:
        st.caption("Introduce todas las cuotas del mercado para calcular probabilidades.")
        return None

    if not resultado["en_rango"]:
        st.markdown(
            '<div class="alerta-peligro">⚠️ Revisar cuotas introducidas '
            f'(overround {resultado["overround"] * 100:.1f}%, fuera del rango 100–125%)</div>',
            unsafe_allow_html=True,
        )
    else:
        _tarjetas_probabilidad(resultado)

    return resultado


def _seccion_stats_equipo(nombre_default: str, key_prefix: str) -> dict:
    """
    Bloque de datos estadísticos opcionales por equipo (fuente manual: BeSoccer/Flashscore/SofaScore).
    Un campo sin rellenar queda en None (dato ausente ≠ 0): placeholder "—", value=None nativo de
    Streamlit 1.58 — sin valor por defecto en 0.
    """
    nombre = st.text_input(
        "Nombre del equipo",
        value=st.session_state.get(f"{key_prefix}_nombre", nombre_default),
        key=f"{key_prefix}_nombre",
    )

    col_a, col_b = st.columns(2)
    with col_a:
        pct_marca = st.number_input(
            "% partidos marcando en 1ª parte", min_value=0, max_value=100,
            value=st.session_state.get(f"{key_prefix}_pct_marca"),
            step=1, key=f"{key_prefix}_pct_marca", placeholder="—",
        )
        pct_marca_primero = st.number_input(
            "% partidos que marca primero", min_value=0, max_value=100,
            value=st.session_state.get(f"{key_prefix}_pct_marca_primero"),
            step=1, key=f"{key_prefix}_pct_marca_primero", placeholder="—",
        )
        goles_030 = st.number_input(
            "Goles en primeros 30'", min_value=0, max_value=50,
            value=st.session_state.get(f"{key_prefix}_goles_030"),
            step=1, key=f"{key_prefix}_goles_030", placeholder="—",
        )
    with col_b:
        pct_encaja = st.number_input(
            "% partidos encajando en 1ª parte", min_value=0, max_value=100,
            value=st.session_state.get(f"{key_prefix}_pct_encaja"),
            step=1, key=f"{key_prefix}_pct_encaja", placeholder="—",
        )
        pct_recibe_primero = st.number_input(
            "% partidos que recibe primero", min_value=0, max_value=100,
            value=st.session_state.get(f"{key_prefix}_pct_recibe_primero"),
            step=1, key=f"{key_prefix}_pct_recibe_primero", placeholder="—",
        )
        goles_3145 = st.number_input(
            "Goles en minutos 31'-45'", min_value=0, max_value=50,
            value=st.session_state.get(f"{key_prefix}_goles_3145"),
            step=1, key=f"{key_prefix}_goles_3145", placeholder="—",
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


def _stats_completitud(prefix_local: str, prefix_visit: str) -> str:
    """"Sin introducir" / "Parciales (N/12)" / "Completos" según cuántos de los 12 campos hay."""
    total_campos = len(_CAMPOS_STATS) * 2
    rellenos = sum(
        1
        for prefix in (prefix_local, prefix_visit)
        for campo in _CAMPOS_STATS
        if st.session_state.get(f"{prefix}_{campo}") is not None
    )
    if rellenos == 0:
        return "Sin introducir"
    if rellenos == total_campos:
        return "Completos"
    return f"Parciales ({rellenos}/{total_campos})"


def _resumen_estado(resultados_mercados: dict) -> None:
    """Tarjeta compacta de estado al inicio de la página."""
    total     = len(resultados_mercados)
    completos = sum(1 for r in resultados_mercados.values() if r is not None)
    validos   = sum(1 for r in resultados_mercados.values() if r is not None and r["en_rango"])
    estado_datos = _stats_completitud("fh_stat_local", "fh_stat_visit")
    estado_ia    = "Generado" if st.session_state.get("fh_analisis_ia") else "Pendiente"

    st.markdown(
        '<div class="tarjeta fh-tarjeta" style="display:flex;flex-wrap:wrap;gap:16px;align-items:center;">'
        f'<div><span class="texto-apagado">Mercados con cuotas introducidas:</span> <b>{completos}/{total}</b></div>'
        f'<div><span class="texto-apagado">Mercados válidos:</span> <b>{validos}/{total}</b></div>'
        f'<div><span class="texto-apagado">Datos estadísticos:</span> <b>{estado_datos}</b></div>'
        f'<div><span class="texto-apagado">Análisis IA:</span> <b>{estado_ia}</b></div>'
        '</div>',
        unsafe_allow_html=True,
    )


def _fmt_valor(v, sufijo: str = "") -> str:
    """Dato ausente ≠ 0: se muestra como “— Sin datos introducidos”; un 0 real se muestra como 0."""
    if v is None:
        return '<span class="texto-apagado" style="font-style:italic;">— Sin datos introducidos</span>'
    return f"{v}{sufijo}"


def _observacion_diferencia(prob_mercado_pct: float, dato_pct) -> str:
    """Regla determinista y descriptiva — nunca una recomendación. dato_pct puede ser None."""
    if dato_pct is None:
        return "Sin datos históricos para comparar"
    diferencia = dato_pct - prob_mercado_pct
    if abs(diferencia) > _UMBRAL_DIFERENCIA_PP:
        direccion = "superior" if diferencia > 0 else "inferior"
        return f"Los datos históricos muestran una tendencia {direccion} a la reflejada por el mercado"
    return "Mercado e historial apuntan en la misma dirección"


def _fila_comparacion_real(etiqueta: str, prob_mercado_pct: float, dato_pct) -> str:
    """Fila de la tabla Mercado | Histórico | Observación. dato_pct puede ser None (sin dato)."""
    observacion = _observacion_diferencia(prob_mercado_pct, dato_pct)
    dato_txt = f"{dato_pct:.0f}%" if dato_pct is not None else "—"
    return (
        f'<tr><td class="col-resultado">{etiqueta}</td>'
        f'<td>{prob_mercado_pct:.1f}%</td>'
        f'<td>{dato_txt}</td>'
        f'<td style="text-align:left;">{observacion}</td></tr>'
    )


def _filas_comparacion_primer_marcador(res_1marca: dict | None, stats_local: dict, stats_visit: dict) -> list[str]:
    """Cruce directo: prob. normalizada de "Local/Visitante marca primero" vs "% marca primero"."""
    if res_1marca is None or not res_1marca["en_rango"]:
        return []
    filas = []
    for stats, outcome in ((stats_local, "Local"), (stats_visit, "Visitante")):
        prob_mercado = res_1marca["normalizadas"].get(outcome)
        if prob_mercado is None:
            continue
        etiqueta = f'{stats["nombre"]} — marca primero'
        filas.append(_fila_comparacion_real(etiqueta, prob_mercado * 100, stats["pct_marca_primero"]))
    return filas


def _filas_comparacion_ou05(res_ou05: dict | None, stats_local: dict, stats_visit: dict) -> list[str]:
    """Equivalente para O/U 0.5 HT: prob. normalizada de "Over 0.5" vs "% marca en 1ª parte" por equipo."""
    if res_ou05 is None or not res_ou05["en_rango"]:
        return []
    prob_mercado = res_ou05["normalizadas"].get("Over 0.5")
    if prob_mercado is None:
        return []
    filas = []
    for stats in (stats_local, stats_visit):
        etiqueta = f'{stats["nombre"]} — anota en la 1ª parte'
        filas.append(_fila_comparacion_real(etiqueta, prob_mercado * 100, stats["pct_marca"]))
    return filas


def _panel_comparativo(resultados_mercados: dict, stats_local: dict, stats_visit: dict) -> None:
    """Panel descriptivo Mercado vs Datos — sin veredictos ni cálculo de edge."""
    st.markdown('<div class="titulo-tarjeta">📊 Mercado vs Datos</div>', unsafe_allow_html=True)
    st.markdown('<div class="fh-compact">', unsafe_allow_html=True)
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
                f'<div class="fila-prob" style="margin-top:4px;"><b>{stats["nombre"]}</b></div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="fila-prob"><span class="texto-apagado">Marca en 1ªP:</span> '
                f'{_fmt_valor(stats["pct_marca"], "%")} · '
                f'<span class="texto-apagado">Encaja en 1ªP:</span> {_fmt_valor(stats["pct_encaja"], "%")}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="fila-prob"><span class="texto-apagado">Marca primero:</span> '
                f'{_fmt_valor(stats["pct_marca_primero"], "%")} · '
                f'<span class="texto-apagado">Recibe primero:</span> {_fmt_valor(stats["pct_recibe_primero"], "%")}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="fila-prob"><span class="texto-apagado">Goles 0-30\':</span> '
                f'{_fmt_valor(stats["goles_030"])} · '
                f'<span class="texto-apagado">Goles 31-45\':</span> {_fmt_valor(stats["goles_3145"])}</div>',
                unsafe_allow_html=True,
            )
    st.markdown('</div>', unsafe_allow_html=True)   # cierre .fh-compact

    # ── Comparación real: tabla Mercado | Histórico | Observación ────────────
    filas_cmp = (
        _filas_comparacion_primer_marcador(resultados_mercados.get("Primer en marcar"), stats_local, stats_visit)
        + _filas_comparacion_ou05(resultados_mercados.get("O/U 0.5 HT"), stats_local, stats_visit)
    )

    st.markdown(
        '<div class="etiqueta-seccion" style="margin-top:8px;">Comparación real — Mercado vs Datos</div>',
        unsafe_allow_html=True,
    )
    if filas_cmp:
        st.markdown(
            '<table class="tabla-cuotas"><thead><tr>'
            '<th>Comparación</th><th>Mercado</th><th>Histórico</th><th>Observación</th>'
            '</tr></thead><tbody>' + "".join(filas_cmp) + '</tbody></table>',
            unsafe_allow_html=True,
        )
    else:
        st.caption(
            "Introduce cuotas válidas en 'Primer equipo en marcar' o 'O/U 0.5 HT' "
            "para ver la comparación real."
        )


def _stats_rellenados(stats: dict) -> dict:
    """Campos estadísticos realmente rellenados por el usuario (None = ausente; 0 explícito SÍ cuenta)."""
    campos = {
        "% marca en 1ª parte":  stats["pct_marca"],
        "% encaja en 1ª parte": stats["pct_encaja"],
        "% marca primero":      stats["pct_marca_primero"],
        "% recibe primero":     stats["pct_recibe_primero"],
        "goles 0-30'":          stats["goles_030"],
        "goles 31-45'":         stats["goles_3145"],
    }
    return {k: v for k, v in campos.items() if v is not None}


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
        max_tokens=650,
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

    if st.button("🧠 Generar análisis IA", key="btn_fh_analizar_ia",
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
        # Cabecera decorativa: markup fijo y de confianza (no viene de la IA) -> unsafe_allow_html seguro.
        st.markdown(
            '<div style="background:var(--bg-elemento);border:1px solid var(--borde);'
            'border-radius:8px;padding:12px 14px 4px;margin-top:6px;">'
            '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">'
            '<span style="font-size:16px;">🧠</span>'
            '<span style="font-size:11px;font-weight:700;color:var(--acento-morado);'
            'text-transform:uppercase;letter-spacing:1px;">Análisis descriptivo IA</span>'
            '</div></div>',
            unsafe_allow_html=True,
        )
        # Contenido de la IA: st.markdown SIN unsafe_allow_html -> los "## " se pintan como
        # encabezados reales y cualquier HTML/script que la IA pudiera reflejar queda sanitizado
        # por el renderer de Streamlit (no se ejecuta, se muestra como texto si acaso).
        st.markdown(analisis_guardado)


def mostrar() -> None:
    """Renderiza el módulo completo de Análisis Primera Parte."""
    st.markdown(_CSS_FH, unsafe_allow_html=True)
    st.markdown(f'<div class="alerta-exito">ℹ️ {AVISO_PERMANENTE}</div>', unsafe_allow_html=True)

    # Resumen de estado — leído de session_state antes de renderizar los widgets de abajo.
    resultados_preview = {
        clave: _resultado_mercado(campos, prefix)
        for clave, _titulo, campos, prefix in _DEFINICIONES_MERCADOS
    }
    _resumen_estado(resultados_preview)

    resultados_mercados: dict = {}
    for clave, titulo_seccion, campos, prefix in _DEFINICIONES_MERCADOS:
        st.markdown('<div class="tarjeta fh-tarjeta">', unsafe_allow_html=True)
        resultados_mercados[clave] = _seccion_mercado(titulo_seccion, campos, prefix)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="tarjeta fh-tarjeta">', unsafe_allow_html=True)
    st.markdown(
        '<div class="titulo-tarjeta">Datos Estadísticos por Equipo (opcional)</div>',
        unsafe_allow_html=True,
    )
    st.caption("Fuente manual: BeSoccer / Flashscore / SofaScore")
    col_l, col_v = st.columns(2)
    with col_l:
        with st.expander("📊 Datos estadísticos — Local", expanded=False):
            stats_local = _seccion_stats_equipo("Local", "fh_stat_local")
    with col_v:
        with st.expander("📊 Datos estadísticos — Visitante", expanded=False):
            stats_visit = _seccion_stats_equipo("Visitante", "fh_stat_visit")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="tarjeta fh-tarjeta">', unsafe_allow_html=True)
    _panel_comparativo(resultados_mercados, stats_local, stats_visit)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="tarjeta fh-tarjeta">', unsafe_allow_html=True)
    _seccion_analisis_ia(resultados_mercados, stats_local, stats_visit)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(f'<div class="alerta-exito">ℹ️ {AVISO_PERMANENTE}</div>', unsafe_allow_html=True)
