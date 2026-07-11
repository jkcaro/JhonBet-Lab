"""Módulo: Análisis con Claude AI — envía datos estructurados del partido a la API."""

import json
import math
import os
import re
from pathlib import Path
import pandas as pd
import streamlit as st
import anthropic
from dotenv import load_dotenv
from scipy.stats import poisson as poisson_dist

from modules import etiquetas_mercado as em

load_dotenv()

os.makedirs(Path(__file__).parent.parent / "data", exist_ok=True)

API_KEY      = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"

MERCADOS_CLAUDE = [
    "Victoria 1X2",
    "Ambos Marcan — No (BTTS No)",
    "Menos 1.5 Goles",
    "Más de 1.5 Goles",
    "Ambos Marcan — Sí (BTTS Sí)",
]

# ── Instrucciones especializadas por mercado ──────────────────────────────────
_INSTRUCCIONES_MERCADO = {
    "Victoria 1X2": """\
Eres un especialista en el mercado "Victoria 1X2" (resultado del partido).

OBJETIVO: identificar UN único ganador claro entre Local, Empate y Visitante.
Nunca recomiendes dos resultados a la vez ni un "doble" (ej. 1X, X2).

PASO 1 — Probabilidades Poisson (ya calculadas, no recalcules):
- "victoria1x2_modelo.p_local", "p_empate", "p_visitante" son las probabilidades exactas
  del modelo Poisson (suma completa de la matriz de marcadores).

PASO 2 — Edge por resultado:
- Edge = (cuota_real × P_modelo − 1) × 100, calculado para cada uno de los 3 resultados.
- "victoria1x2_modelo.edges" contiene el edge ya calculado de Local/Empate/Visitante.
- "victoria1x2_modelo.mejor_seleccion" y "mejor_edge" indican el resultado con mayor edge.

PASO 3 — Selección única:
- SOLO puedes recomendar el resultado con el edge MÁS ALTO de los tres.
- Si ese edge máximo es < 6%, ningún resultado tiene valor → "No apostar".

PASO 4 — Contexto de forma reciente:
- Usa "forma_reciente_local" y "forma_reciente_visitante" (últimos 5 partidos, W/D/L)
  para matizar la confianza en la selección elegida.
- 3+ victorias recientes del favorito refuerzan la recomendación.
- Forma irregular o racha negativa del favorito reduce la confianza.

NEVER recomiendes más de un resultado.
NEVER recomienda si el edge máximo de los 3 resultados < 6%.
NEVER recomienda si confianza es Baja.""",

    "Ambos Marcan — No (BTTS No)": """\
Eres un especialista en el mercado "Ambos Marcan — No" (BTTS No).

CONDICIÓN PREVIA OBLIGATORIA:
- Solo se recomienda si xG_visitante < 0.8. Si no: "No apostar — xG visitante demasiado alto".

PASO 1 — Cálculo Poisson:
- P(visitante NO marca) = e^(-xG_visitante)
- P(local NO marca)     = e^(-xG_local)
- P(BTTS Sí)  = (1 − e^(-xG_l)) × (1 − e^(-xG_v))
- P(BTTS No)  = 1 − P(BTTS Sí)
- Los datos "btts_no_modelo" ya incluyen estos valores calculados.

PASO 2 — Edge vs cuota:
- Cuota justa = 1 / P(BTTS No). Compara con la cuota de mercado disponible.
- Edge = (cuota_casa × P_modelo − 1) × 100. Solo recomienda si edge ≥ 6%.

PASO 3 — Factores que refuerzan el No:
- xG_visitante < 0.6 → alta probabilidad de que el visitante no marque.
- Defensa local sólida (baja media de goles encajados).
- Visitante en racha de partidos sin marcar.

PASO 4 — Recomendación:
- Si xG_visitante ≥ 0.8: "No apostar — xG visitante {valor} ≥ 0.8, condición no cumplida."
- Si edge ≥ 6% y xG_visitante < 0.8: "APOSTAR: BTTS No @ [cuota]"

NEVER recomienda si xG_visitante ≥ 0.8.
NEVER recomienda si edge < 6%.
NEVER recomienda si confianza es Baja.""",

    "Menos 1.5 Goles": """\
Eres un especialista en el mercado "Menos 1.5 Goles" (Under 1.5).

CÁLCULO POISSON PASO A PASO (muestra cada fórmula con los valores numéricos):

PASO 1 — P(0-0):
  P(0-0) = e^(−xG_local) × e^(−xG_visitante)
  [usa "menos15_modelo.formula_paso1" para el cálculo exacto]

PASO 2 — P(1 gol total):
  P(1-0) = xG_local × e^(−xG_local) × e^(−xG_visitante)   [usa formula_paso2]
  P(0-1) = e^(−xG_local) × xG_visitante × e^(−xG_visitante) [usa formula_paso3]
  P(1 gol) = P(1-0) + P(0-1)

PASO 3 — P(Menos 1.5):
  P(Menos 1.5) = P(0-0) + P(1 gol)
  [usa "menos15_modelo.p_menos15" para el resultado final]
  Cuota justa = 1 / P(Menos 1.5)

PASO 4 — Edge vs cuota:
  Edge = (cuota_casa × P_modelo − 1) × 100. Solo recomienda si edge ≥ 6%.
  Si no hay cuota de mercado, indica la cuota mínima que tendría valor.

PASO 5 — Contexto:
  - xG total > 2.5 → poco favorable (alta probabilidad de goles).
  - xG total < 1.5 → muy favorable. Si "alerta" del modelo lo indica, menciónalo.
  - Defensa sólida de ambos equipos refuerza el mercado.
  - Si "contexto_motivacion" indica sin motivación → partido potencialmente cerrado.

NEVER recomienda si xG_total > 2.5.
NEVER recomienda si edge < 6%.
NEVER recomienda si confianza es Baja.""",

    "Más de 1.5 Goles": """\
Eres un especialista en el mercado "Más de 1.5 Goles" (Over 1.5).

CÁLCULO POISSON PASO A PASO (muestra cada fórmula con los valores numéricos):

PASO 1 — P(0-0):
  P(0-0) = e^(−xG_local) × e^(−xG_visitante)
  [usa "mas15_modelo.formula_paso1" para el cálculo exacto]

PASO 2 — P(1 gol total):
  P(1-0) = xG_local × e^(−xG_local) × e^(−xG_visitante)   [usa formula_paso2]
  P(0-1) = e^(−xG_local) × xG_visitante × e^(−xG_visitante) [usa formula_paso3]
  P(1 gol) = P(1-0) + P(0-1)

PASO 3 — P(Más 1.5):
  P(Más 1.5) = 1 − P(0-0) − P(1 gol)
  [usa "mas15_modelo.p_mas15" para el resultado final]
  Cuota justa = 1 / P(Más 1.5)

PASO 4 — Edge vs cuota:
  Edge = (cuota_casa × P_modelo − 1) × 100. Solo recomienda si edge ≥ 6%.
  Si no hay cuota de mercado, indica la cuota mínima que tendría valor.

PASO 5 — Contexto:
  - xG total > 2.5 → muy favorable (alta probabilidad de superar 1.5 goles).
  - xG total 1.5–2.5 → moderado, evalúa cuota.
  - xG total < 1.5 → NUNCA recomendar.
  - Equipos con tendencia ofensiva y alta media goleadora refuerzan el mercado.

NEVER recomienda si xG_total < 1.5.
NEVER recomienda si edge < 6%.
NEVER recomienda si confianza es Baja.""",

    "Ambos Marcan — Sí (BTTS Sí)": """\
Eres un especialista en el mercado "Ambos Marcan — Sí" (BTTS Sí).

CONDICIÓN PREVIA OBLIGATORIA:
- Solo se recomienda si AMBOS xG son > 1.0. Si alguno < 1.0: "No apostar — xG insuficiente".

PASO 1 — Cálculo Poisson:
- P(local marca ≥ 1)     = 1 − e^(−xG_local)
- P(visitante marca ≥ 1) = 1 − e^(−xG_visitante)
- P(BTTS Sí) = P(local marca) × P(visitante marca)
- Los datos "btts_si_modelo" ya incluyen estos valores calculados.

PASO 2 — Edge vs cuota:
- Cuota justa = 1 / P(BTTS Sí). Compara con la cuota de mercado disponible.
- Edge = (cuota_casa × P_modelo − 1) × 100. Solo recomienda si edge ≥ 6%.

PASO 3 — Factores de ajuste (usa "btts_forma" si disponible):
- Si "ajuste_confianza_si" presente → incrementa confianza.
- Si "ajuste_elo" presente → los xG ya están ajustados.
- Indicadores 🟢/🟡/🔴 de tendencia BTTS de cada equipo.
- Si "alertas" contiene "poca tendencia goleadora" → reduce confianza.

PASO 4 — Recomendación:
- Si algún xG < 1.0: "No apostar — xG {equipo} = {valor} < 1.0, condición no cumplida."
- Si edge ≥ 6% y ambos xG > 1.0: "APOSTAR: BTTS Sí @ [cuota]"

NEVER recomienda si algún xG individual < 1.0.
NEVER recomienda si edge < 6%.
NEVER recomienda si confianza es Baja.""",
}


_RUTA_CUOTAS = Path(__file__).parent.parent / "data" / "odds.csv"
_CASAS       = ["codere", "bet365", "betfair"]

# Mapea (mercado CSV, resultado CSV) → clave en el modelo Poisson
_MAPA_PROBS = {
    ("1X2",            "Local"):     "local",
    ("1X2",            "Empate"):    "empate",
    ("1X2",            "Visitante"): "visitante",
    ("Over/Under 2.5", "Over 2.5"):  "over25",
    ("Over/Under 2.5", "Under 2.5"): "under25",
    ("Over/Under 1.5", "Over 1.5"):  "mas15",
    ("Over/Under 1.5", "Under 1.5"): "menos15",
}


def _calcular_poisson_local(xg_l: float, xg_v: float) -> dict:
    N = 9
    p_l = p_e = p_v = over25 = menos15 = 0.0
    for h in range(N):
        for a in range(N):
            p = poisson_dist.pmf(h, xg_l) * poisson_dist.pmf(a, xg_v)
            if   h > a:    p_l    += p
            elif h == a:   p_e    += p
            else:          p_v    += p
            if h + a > 2:  over25  += p
            if h + a <= 1: menos15 += p
    total = (p_l + p_e + p_v) or 1.0
    return {
        "local":    p_l / total,
        "empate":   p_e / total,
        "visitante": p_v / total,
        "over25":   over25,
        "under25":  1.0 - over25,
        "menos15":  menos15,
        "mas15":    1.0 - menos15,
    }


def _enriquecer_con_cuotas(datos: dict) -> dict:
    """
    Lee odds.csv para el partido activo y añade al dict:
      - cuotas_reales: tabla por outcome con precios de cada casa y la mejor cuota
      - edge_por_outcome: edge % = (cuota_casa × P_modelo − 1) × 100
    """
    partido = datos.get("partido", "")
    probs_raw = datos.get("probabilidades", {})
    xg_l = float(probs_raw.get("xg_local") or 0)
    xg_v = float(probs_raw.get("xg_visitante") or 0)

    if not partido or xg_l <= 0 or xg_v <= 0:
        return datos

    try:
        df = pd.read_csv(_RUTA_CUOTAS)
    except Exception:
        return datos

    df_p = df[df["partido"] == partido].copy()
    if df_p.empty:
        return datos

    # ── Tabla de cuotas reales ──
    cuotas_reales = {}
    for _, row in df_p.iterrows():
        precios = {c: float(row.get(c, 0)) for c in _CASAS}
        validos = [v for v in precios.values() if v > 1.0]
        key = f"{row['mercado']} — {row['resultado']}"
        cuotas_reales[key] = {
            **{c: f"{precios[c]:.2f}" if precios[c] > 1.0 else "N/D" for c in _CASAS},
            "mejor_cuota": f"{max(validos):.2f}" if validos else "N/D",
        }
    datos["cuotas_reales"] = cuotas_reales

    # ── Edge por outcome ──
    probs_modelo = _calcular_poisson_local(xg_l, xg_v)
    edges = {}
    for _, row in df_p.iterrows():
        prob_key = _MAPA_PROBS.get((row["mercado"], row["resultado"]))
        if not prob_key:
            continue
        validos = [float(row.get(c, 0)) for c in _CASAS if float(row.get(c, 0)) > 1.0]
        if not validos:
            continue
        mejor = max(validos)
        edge  = (mejor * probs_modelo[prob_key] - 1) * 100.0
        key   = f"{row['mercado']} — {row['resultado']}"
        edges[key] = f"{edge:+.1f}%"

    if edges:
        datos["edge_por_outcome"] = edges

    return datos


def _enriquecer_con_alertas(datos: dict) -> dict:
    """
    Añade al dict una lista de alertas para el analista sobre:
    - Fiabilidad limitada del xG estimado
    - Posible rotación de plantilla por tipo de competición
    """
    alertas: list[str] = []

    # ① Fiabilidad del xG
    if datos.get("probabilidades"):
        alertas.append(
            "XG ESTIMADO — Los valores de xG se derivan de cuotas de mercado, "
            "no de estadísticas de tiros reales. Si hay datos de forma reciente "
            "(estadisticas_forma), deben tener más peso que el modelo Poisson."
        )

    # ② Rotación de plantilla por competición
    liga = datos.get("liga", "").lower()
    palabras_rotacion = [
        "copa", "cup", "coupe", "pokal", "taça",
        "segunda", "serie b", "ligue 2", "league one", "league two",
        "bundesliga 2", "championship", "libertadores", "mls", "friendl",
        "amistoso",
    ]
    if any(p in liga for p in palabras_rotacion):
        alertas.append(
            f"ROTACIÓN — La liga '{datos.get('liga','')}' suele implicar rotación "
            "de jugadores en equipos grandes o menor intensidad competitiva. "
            "Considera bajar un nivel de confianza si el análisis lo sugiere."
        )

    if alertas:
        datos["alertas_analista"] = alertas

    return datos


def _enriquecer_para_mercado(datos: dict, mercado: str) -> dict:
    """Calcula métricas específicas del mercado y las añade al dict de datos."""
    probs_raw = datos.get("probabilidades", {})
    xg_l = float(probs_raw.get("xg_local") or 1.5)
    xg_v = float(probs_raw.get("xg_visitante") or 1.2)

    # ── Helpers ──────────────────────────────────────────────────────────────
    def _mejor_cuota_csv(clave_mercado: str, clave_resultado: str) -> float:
        """Devuelve la mejor cuota real de odds.csv para un outcome concreto."""
        cuotas = datos.get("cuotas_reales", {})
        key = f"{clave_mercado} — {clave_resultado}"
        val = cuotas.get(key, {})
        if not val:
            return 0.0
        try:
            return float(str(val.get("mejor_cuota", "0")).replace("N/D", "0"))
        except (ValueError, TypeError):
            return 0.0

    def _cuota_justa(prob: float) -> str:
        return f"{1/prob:.2f}" if prob > 0.01 else "—"

    def _edge_pct(prob: float, cuota: float) -> float | None:
        if cuota <= 1.0:
            return None
        return (cuota * prob - 1) * 100.0

    # ── VICTORIA 1X2 ────────────────────────────────────────────────────────────
    if mercado == "Victoria 1X2":
        probs_m = _calcular_poisson_local(xg_l, xg_v)
        p_local, p_empate, p_visit = probs_m["local"], probs_m["empate"], probs_m["visitante"]

        c_local  = _mejor_cuota_csv("1X2", "Local")
        c_empate = _mejor_cuota_csv("1X2", "Empate")
        c_visit  = _mejor_cuota_csv("1X2", "Visitante")

        edges_raw = {
            "Local":     _edge_pct(p_local,  c_local),
            "Empate":    _edge_pct(p_empate, c_empate),
            "Visitante": _edge_pct(p_visit,  c_visit),
        }
        edges_validos = {k: v for k, v in edges_raw.items() if v is not None}
        mejor_sel  = max(edges_validos, key=edges_validos.get) if edges_validos else None
        mejor_edge = edges_validos.get(mejor_sel, 0.0) if mejor_sel else 0.0

        nuevo_edge: dict[str, str] = {
            f"Victoria 1X2 — {k}": f"{v:+.1f}%" for k, v in edges_validos.items()
        }

        datos["victoria1x2_modelo"] = {
            "p_local":         f"{p_local*100:.1f}%",
            "p_empate":        f"{p_empate*100:.1f}%",
            "p_visitante":     f"{p_visit*100:.1f}%",
            "cuota_local":     f"{c_local:.2f}"  if c_local  > 1.0 else "N/D",
            "cuota_empate":    f"{c_empate:.2f}" if c_empate > 1.0 else "N/D",
            "cuota_visitante": f"{c_visit:.2f}"  if c_visit  > 1.0 else "N/D",
            "edges":           {k: f"{v:+.1f}%" for k, v in edges_validos.items()},
            "mejor_seleccion": mejor_sel or "—",
            "mejor_edge":      f"{mejor_edge:+.1f}%" if mejor_sel else "—",
            "alerta": (
                f"Mejor edge: {mejor_sel} ({mejor_edge:+.1f}%) ✅ supera el umbral 6%"
                if mejor_sel and mejor_edge >= 6.0 else
                "Ningún resultado supera el umbral de edge 6% ⚠️ — no recomendar"
            ),
        }
        datos["edge_por_outcome"] = nuevo_edge
        cuotas_1x2 = {k: v for k, v in datos.get("cuotas_reales", {}).items() if k.startswith("1X2")}
        if cuotas_1x2:
            datos["cuotas_reales"] = cuotas_1x2

    # ── BTTS NO ───────────────────────────────────────────────────────────────
    elif "Ambos Marcan" in mercado and "No" in mercado:
        p_si = (1 - math.exp(-xg_l)) * (1 - math.exp(-xg_v))
        p_no = 1.0 - p_si
        cond_xg_baja = xg_v < 0.8

        c_no = _mejor_cuota_csv("Ambos Marcan", "No")
        nuevo_edge: dict[str, str] = {}
        e_no = _edge_pct(p_no, c_no)
        if e_no is not None:
            nuevo_edge["Ambos Marcan — No"] = f"{e_no:+.1f}%"

        datos["btts_no_modelo"] = {
            "p_btts_si":        f"{p_si*100:.1f}%",
            "p_btts_no":        f"{p_no*100:.1f}%",
            "cuota_justa_no":   _cuota_justa(p_no),
            "xg_visitante":     xg_v,
            "condicion_xg_baja": cond_xg_baja,
            "alerta_xg_visita": (
                f"xG visitante = {xg_v:.2f} < 0.8 ✅ condición favorable para BTTS No"
                if cond_xg_baja else
                f"xG visitante = {xg_v:.2f} ≥ 0.8 ⚠️ condición NO cumplida — no recomendar"
            ),
        }
        datos["edge_por_outcome"] = nuevo_edge
        cuotas_btts = {k: v for k, v in datos.get("cuotas_reales", {}).items()
                       if "Ambos" in k or "BTTS" in k.upper()}
        if cuotas_btts:
            datos["cuotas_reales"] = cuotas_btts

    # ── BTTS SÍ ───────────────────────────────────────────────────────────────
    elif "Ambos Marcan" in mercado:
        # Ajuste ELO opcional
        xg_l_adj, xg_v_adj = xg_l, xg_v
        elo_l_raw = datos.get("elo_local")
        elo_v_raw = datos.get("elo_visit")
        elo_ajuste_txt = None
        if elo_l_raw and elo_v_raw:
            elo_diff = float(elo_l_raw) - float(elo_v_raw)
            if abs(elo_diff) > 5:
                factor = min(abs(elo_diff) / 400.0, 0.15)
                equipo_fuerte = "local" if elo_diff > 0 else "visitante"
                xg_l_adj = xg_l * (1 + factor if elo_diff > 0 else 1 - factor)
                xg_v_adj = xg_v * (1 - factor if elo_diff > 0 else 1 + factor)
                elo_ajuste_txt = (
                    f"ELO diferencia {abs(elo_diff):.0f} pts a favor del {equipo_fuerte} "
                    f"— xG ajustados: local {xg_l_adj:.3f} / visitante {xg_v_adj:.3f}"
                )

        p_si = (1 - math.exp(-xg_l_adj)) * (1 - math.exp(-xg_v_adj))
        p_no = 1.0 - p_si
        cond_xg_altos = xg_l > 1.0 and xg_v > 1.0

        def _nivel_btts(n: int) -> str:
            if n >= 4: return "🟢 Alta tendencia (4-5/5)"
            if n >= 2: return "🟡 Media (2-3/5)"
            return "🔴 Baja (0-1/5)"

        btts_l5, btts_v5 = datos.get("btts_local_5"), datos.get("btts_visit_5")
        forma_btts: dict = {}
        alertas_btts: list[str] = []
        if btts_l5 is not None:
            forma_btts["btts_local_ultimos_5"] = btts_l5
            forma_btts["indicador_local"] = _nivel_btts(btts_l5)
        if btts_v5 is not None:
            forma_btts["btts_visitante_ultimos_5"] = btts_v5
            forma_btts["indicador_visitante"] = _nivel_btts(btts_v5)
        if btts_l5 is not None and btts_v5 is not None:
            if btts_l5 >= 4 and btts_v5 >= 4:
                forma_btts["ajuste_confianza_si"] = "+15% boost — ambos con alta tendencia BTTS"
                alertas_btts.append("BOOST BTTS: ambos marcaron en 4-5 de sus últimos 5 partidos")
            if btts_l5 <= 1 or btts_v5 <= 1:
                bajos = ([f"local ({btts_l5}/5)"] if btts_l5 <= 1 else []) + \
                        ([f"visitante ({btts_v5}/5)"] if btts_v5 <= 1 else [])
                alertas_btts.append(f"ADVERTENCIA: equipo con poca tendencia goleadora — {', '.join(bajos)}")
        if elo_ajuste_txt:
            forma_btts["ajuste_elo"] = elo_ajuste_txt
        if elo_l_raw and elo_v_raw:
            forma_btts["elo_local"] = float(elo_l_raw)
            forma_btts["elo_visitante"] = float(elo_v_raw)
        if alertas_btts:
            forma_btts["alertas"] = alertas_btts
        if forma_btts:
            datos["btts_forma"] = forma_btts

        c_si = _mejor_cuota_csv("Ambos Marcan", "Si")
        nuevo_edge: dict[str, str] = {}
        e_si = _edge_pct(p_si, c_si)
        if e_si is not None:
            nuevo_edge["Ambos Marcan — Sí"] = f"{e_si:+.1f}%"

        datos["btts_si_modelo"] = {
            "p_btts_si":       f"{p_si*100:.1f}%",
            "p_btts_no":       f"{p_no*100:.1f}%",
            "cuota_justa_si":  _cuota_justa(p_si),
            "xg_local":        xg_l,
            "xg_visitante":    xg_v,
            "condicion_xg_altos": cond_xg_altos,
            "alerta_xg": (
                f"xG local={xg_l:.2f}, visitante={xg_v:.2f} — ambos >1.0 ✅ condición cumplida"
                if cond_xg_altos else
                f"xG local={xg_l:.2f}, visitante={xg_v:.2f} — ⚠️ algún xG <1.0, condición NO cumplida"
            ),
        }
        datos["edge_por_outcome"] = nuevo_edge
        cuotas_btts = {k: v for k, v in datos.get("cuotas_reales", {}).items()
                       if "Ambos" in k or "BTTS" in k.upper()}
        if cuotas_btts:
            datos["cuotas_reales"] = cuotas_btts

    # ── MENOS 1.5 GOLES ───────────────────────────────────────────────────────
    elif "Menos 1.5" in mercado:
        probs_m = _calcular_poisson_local(xg_l, xg_v)
        p_menos15 = probs_m["menos15"]

        p_00  = math.exp(-xg_l) * math.exp(-xg_v)
        p_10  = xg_l * math.exp(-xg_l) * math.exp(-xg_v)
        p_01  = math.exp(-xg_l) * xg_v * math.exp(-xg_v)
        p_1g  = p_10 + p_01
        xg_total = xg_l + xg_v

        c_u15 = _mejor_cuota_csv("Over/Under 1.5", "Under 1.5")
        nuevo_edge: dict[str, str] = {}
        e_u15 = _edge_pct(p_menos15, c_u15)
        if e_u15 is not None:
            nuevo_edge["Menos 1.5 Goles"] = f"{e_u15:+.1f}%"

        datos["menos15_modelo"] = {
            "formula_paso1":       f"P(0-0) = e^(-{xg_l:.2f}) × e^(-{xg_v:.2f}) = {p_00*100:.1f}%",
            "formula_paso2":       f"P(1-0) = {xg_l:.2f}·e^(-{xg_l:.2f}) × e^(-{xg_v:.2f}) = {p_10*100:.1f}%",
            "formula_paso3":       f"P(0-1) = e^(-{xg_l:.2f}) × {xg_v:.2f}·e^(-{xg_v:.2f}) = {p_01*100:.1f}%",
            "p_un_gol":            f"{p_1g*100:.1f}%",
            "p_menos15":           f"{p_menos15*100:.1f}%",
            "p_mas15":             f"{(1-p_menos15)*100:.1f}%",
            "cuota_justa_menos15": _cuota_justa(p_menos15),
            "xg_total":            f"{xg_total:.2f}",
            "alerta": (
                f"xG total = {xg_total:.2f} < 1.5 ✅ muy favorable para Menos 1.5"
                if xg_total < 1.5 else
                f"xG total = {xg_total:.2f} {'< 2.5 🟡 moderado' if xg_total < 2.5 else '≥ 2.5 ⚠️ poco favorable — no recomendar'}"
            ),
        }
        datos["edge_por_outcome"] = nuevo_edge
        cuotas_u15 = {k: v for k, v in datos.get("cuotas_reales", {}).items()
                      if "1.5" in k or "Under" in k.upper()}
        if cuotas_u15:
            datos["cuotas_reales"] = cuotas_u15
        else:
            datos.pop("cuotas_reales", None)

    elif "Más de 1.5" in mercado or "Mas de 1.5" in mercado:
        probs_m = _calcular_poisson_local(xg_l, xg_v)
        p_mas15 = probs_m["mas15"]

        p_00  = math.exp(-xg_l) * math.exp(-xg_v)
        p_10  = xg_l * math.exp(-xg_l) * math.exp(-xg_v)
        p_01  = math.exp(-xg_l) * xg_v * math.exp(-xg_v)
        p_1g  = p_10 + p_01
        xg_total = xg_l + xg_v

        c_o15 = _mejor_cuota_csv("Over/Under 1.5", "Over 1.5")
        nuevo_edge: dict[str, str] = {}
        e_o15 = _edge_pct(p_mas15, c_o15)
        if e_o15 is not None:
            nuevo_edge["Más de 1.5 Goles"] = f"{e_o15:+.1f}%"

        datos["mas15_modelo"] = {
            "formula_paso1":     f"P(0-0) = e^(-{xg_l:.2f}) × e^(-{xg_v:.2f}) = {p_00*100:.1f}%",
            "formula_paso2":     f"P(1-0) = {xg_l:.2f}·e^(-{xg_l:.2f}) × e^(-{xg_v:.2f}) = {p_10*100:.1f}%",
            "formula_paso3":     f"P(0-1) = e^(-{xg_l:.2f}) × {xg_v:.2f}·e^(-{xg_v:.2f}) = {p_01*100:.1f}%",
            "p_un_gol":          f"{p_1g*100:.1f}%",
            "p_menos15":         f"{(1-p_mas15)*100:.1f}%",
            "p_mas15":           f"{p_mas15*100:.1f}%",
            "cuota_justa_mas15": _cuota_justa(p_mas15),
            "xg_total":          f"{xg_total:.2f}",
            "alerta": (
                f"xG total = {xg_total:.2f} > 2.5 ✅ muy favorable para Más de 1.5"
                if xg_total > 2.5 else
                f"xG total = {xg_total:.2f} "
                f"{'> 1.5 🟡 moderado — evalúa la cuota' if xg_total > 1.5 else '≤ 1.5 ⚠️ poco favorable — no recomendar'}"
            ),
        }
        datos["edge_por_outcome"] = nuevo_edge
        cuotas_o15 = {k: v for k, v in datos.get("cuotas_reales", {}).items()
                      if "1.5" in k or "Over" in k.upper()}
        if cuotas_o15:
            datos["cuotas_reales"] = cuotas_o15
        else:
            datos.pop("cuotas_reales", None)

    return datos


def _enriquecer_con_stats(datos: dict) -> dict:
    """Añade estadísticas de forma reales. Timeout total de 10s (2 equipos × 2 fuentes × 3s/req)."""
    import concurrent.futures
    try:
        from modules.football_stats import obtener_stats_partido
        partido = datos.get("partido", "")
        if not partido:
            return datos
        # Sin 'with' para que shutdown(wait=False) no bloquee al salir por timeout
        _pool   = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        _future = _pool.submit(obtener_stats_partido, partido)
        try:
            stats = _future.result(timeout=10)
            if stats:
                datos["estadisticas_forma"] = stats
        except concurrent.futures.TimeoutError:
            print("[ClaudeAnalysis] Stats timeout — continuando sin estadísticas de forma")
        finally:
            _pool.shutdown(wait=False)   # no espera el hilo background
    except Exception as exc:
        print(f"[ClaudeAnalysis] No se pudieron obtener stats: {exc}")
    return datos


def _construir_contexto_dinamico(datos_partido: dict) -> str:
    """
    Construye el bloque "CAMPOS CLAVE EN LOS DATOS" + alertas del analista
    según los campos presentes en datos_partido. Es independiente del mercado
    — usado por analizar_con_claude().
    """
    # Construir contexto dinámico según los datos disponibles
    bloques: list[str] = []

    if "cuotas_reales" in datos_partido:
        bloques.append(
            '- "cuotas_reales": cuotas actuales de Codere, Bet365 y Betfair con la mejor disponible.'
        )
    if "cuotas_ambos_marcan_manual" in datos_partido:
        btts_m = datos_partido["cuotas_ambos_marcan_manual"]
        si_txt = f"{btts_m.get('Si','—')}" if "Si" in btts_m else "—"
        no_txt = f"{btts_m.get('No','—')}" if "No" in btts_m else "—"
        bloques.append(
            f'- "cuotas_ambos_marcan_manual": cuotas reales de Ambos Marcan introducidas manualmente.\n'
            f'  Sí: {si_txt}  |  No: {no_txt}\n'
            f'  Úsalas para calcular el edge cuando el mercado sea "Ambos Marcan (Sí/No)".'
        )
    if "contexto_motivacion" in datos_partido:
        mot = datos_partido["contexto_motivacion"]
        ult = datos_partido.get("ultimo_partido_temporada", "")
        ult_txt = f"  Último partido de temporada: {ult}." if ult else ""
        bloques.append(
            f'- "contexto_motivacion": motivación en juego = "{mot}".{ult_txt}\n'
            f'  Si "sin motivación" → reduce confianza (partido sin tensión competitiva).\n'
            f'  Si "último partido temporada" → alta rotación posible, baja confianza.'
        )
    if "btts_forma" in datos_partido:
        bf = datos_partido["btts_forma"]
        ind_l = bf.get("indicador_local", "—")
        ind_v = bf.get("indicador_visitante", "—")
        bloques.append(
            f'- "btts_forma": datos de forma BTTS e ELO de los últimos 5 partidos.\n'
            f'  Tendencia local: {ind_l}  |  Tendencia visitante: {ind_v}\n'
            '  REGLAS:\n'
            '  - Si "ajuste_confianza_si" presente → sube la confianza en "Ambos Marcan Sí"\n'
            '  - Si "alertas" contiene "poca tendencia goleadora" → baja confianza en Sí\n'
            '  - Si "ajuste_elo" presente → los xG ya están ajustados por ELO; úsalos\n'
            '  - Menciona los indicadores de tendencia (🟢/🟡/🔴) en el punto 2 del análisis'
        )
    if "cuotas_resultado_1t_manual" in datos_partido:
        c1t = datos_partido["cuotas_resultado_1t_manual"]
        bloques.append(
            f'- "cuotas_resultado_1t_manual": cuotas del mercado Resultado 1ª Parte introducidas manualmente.\n'
            f'  Local 1T: {c1t.get("Local","—")}  |  Empate 1T: {c1t.get("Empate","—")}  |  Visitante 1T: {c1t.get("Visitante","—")}\n'
            f'  Úsalas para calcular el edge en el mercado "Resultado 1ª Parte (1X2)".'
        )
    if datos_partido.get("fuente_xg") == "manual":
        bloques.append(
            '- NOTA: los xG de este partido fueron introducidos manualmente (BeSoccer u otra fuente).\n'
            '  Son más fiables que los estimados desde cuotas. Dales mayor peso en el análisis.'
        )
    if "edge_por_outcome" in datos_partido:
        bloques.append(
            '- "edge_por_outcome": edge % = (cuota_casa × P_modelo − 1) × 100.\n'
            '  Edge ≥ 6% = APUESTA CON VALOR. Edge < 6% = SIN VALOR.\n'
            '  Si el edge es < 6% en todos los outcomes del mercado, recomienda NO apostar.'
        )
    if datos_partido.get("forma_reciente_local") or datos_partido.get("forma_reciente_visitante"):
        fl = datos_partido.get("forma_reciente_local", "—")
        fv = datos_partido.get("forma_reciente_visitante", "—")
        bloques.append(
            f'- Forma reciente (últimos 5, W=ganado / D=empate / L=perdido):\n'
            f'  Local: {fl}  |  Visitante: {fv}\n'
            '  Úsala para matizar la confianza: racha positiva del favorito refuerza la '
            'recomendación, racha irregular o negativa la reduce.'
        )
    for clave_modelo in ("victoria1x2_modelo", "btts_no_modelo", "btts_si_modelo", "menos15_modelo", "mas15_modelo"):
        if clave_modelo in datos_partido:
            bloques.append(
                f'- "{clave_modelo}": cálculo Poisson completo ya realizado para este mercado.\n'
                f'  Úsalo directamente en el análisis — no recalcules, muestra los valores incluidos.'
            )
    if "estadisticas_forma" in datos_partido:
        bloques.append(
            '- "estadisticas_forma": datos reales combinados de SofaScore y Football-Data.org.\n'
            '  Incluye por equipo:\n'
            '    · forma: últimos 5 resultados (G=ganado, E=empate, P=perdido)\n'
            '    · goles_a_favor_media y goles_en_contra_media por partido\n'
            '    · rendimiento_local y rendimiento_visitante\n'
            '    · lesiones_actuales: jugadores lesionados (SofaScore)\n'
            '    · clasificacion: posición en liga, puntos, forma reciente (Football-Data.org)\n'
            '    · proximos_partidos: próximos 3 fixtures (Football-Data.org)\n'
            '  REGLAS DE USO:\n'
            '    - Si hay lesionados clave, menciónalos y baja la confianza\n'
            '    - Si un equipo está en mala racha (3+ derrotas seguidas), penaliza su probabilidad\n'
            '    - Usa la clasificación para contextualizar si el equipo está bajo presión'
        )

    contexto = ""
    if bloques:
        contexto = "\nCAMPOS CLAVE EN LOS DATOS:\n" + "\n".join(bloques) + "\n"

    # Bloque de alertas para el analista
    alertas_txt = ""
    alertas = datos_partido.get("alertas_analista", [])
    if alertas:
        items = "\n".join(f"  • {a}" for a in alertas)
        alertas_txt = f"""
⚠️ ALERTAS DEL SISTEMA — lee antes de analizar:
{items}

Estas alertas deben reflejarse explícitamente en tu respuesta:
- Si el xG es estimado → menciona en el punto 2 que las probabilidades son orientativas.
- Si hay riesgo de rotación → indícalo en el nivel de confianza del punto 4.
"""
    return contexto + alertas_txt


def analizar_con_claude(datos_partido: dict, mercado: str) -> str:
    """
    Envía datos del partido a Claude con instrucciones adaptadas al mercado.
    "mercado" sigue siendo la clave canónica (MERCADOS_CLAUDE) para el lookup
    en _INSTRUCCIONES_MERCADO y para el campo persistido — mercado_visible
    solo sustituye el texto libre del prompt (nomenclatura Codere), nunca las
    claves internas.
    """
    client = anthropic.Anthropic(api_key=API_KEY)

    _fallback           = next(iter(_INSTRUCCIONES_MERCADO.values()))
    instrucciones       = _INSTRUCCIONES_MERCADO.get(mercado, _fallback)
    contexto_y_alertas  = _construir_contexto_dinamico(datos_partido)
    mercado_visible     = em.titulo_mercado(mercado)

    prompt = f"""Eres un analista especialista en apuestas deportivas, experto en los mercados
"Ambos Marcan" y "Resultado 1ª Parte". Tu análisis es cuantitativo, riguroso y siempre
basado en los datos proporcionados.

Mercado a analizar: **{mercado_visible}**

{instrucciones}
{contexto_y_alertas}
REGLAS OBLIGATORIAS — esto es dinero real, sé estricto:
- Si el edge calculado es < 6%: la recomendación DEBE ser "No apostar".
- Si la confianza es Baja: la recomendación DEBE ser "No apostar".
- Nunca inventes cuotas; usa solo las de "cuotas_reales" si están disponibles.
- El stake máximo es el 2% del bankroll del usuario.
- El bloque VEREDICTO FINAL es obligatorio y debe coincidir exactamente con la
  recomendación del punto 3 — nunca lo omitas ni lo contradigas.

Estructura tu respuesta EXACTAMENTE en estos 4 puntos, y SIEMPRE termina con el
bloque de veredicto final (sin ningún texto después de él):
1. Valoración del partido — xG de cada equipo, favorito, forma reciente si disponible
2. Análisis "{mercado_visible}" — cálculo paso a paso de probabilidades, edge y cuotas reales
3. Recomendación — "APOSTAR: [opción] @ [cuota]" O "No apostar — [motivo concreto]"
4. Confianza: Alto / Medio / Bajo — con justificación en una línea

Después del punto 4, añade EXACTAMENTE este bloque (sustituye los valores entre []):
=== VEREDICTO FINAL ===
MERCADO: {mercado_visible}
SELECCIÓN: [resultado único recomendado, o "Ninguno"]
CUOTA: [X.XX, o "—" si no apuestas]
EDGE: [X.X%, o "—" si no apuestas]
DECISIÓN: APOSTAR ✅ / NO APOSTAR ❌
RAZÓN: [1 línea concreta]

Datos del partido:
{json.dumps(datos_partido, indent=2, ensure_ascii=False)}

Responde en español. Sé conciso y directo. No añadas advertencias genéricas."""

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
        timeout=45.0,
    )
    return message.content[0].text


def _normalizar_formato(texto: str) -> str:
    """Convierte encabezados markdown (#, ##, ###) a negritas de tamaño normal."""
    return re.sub(r'^#{1,3} (.+)$', r'**\1**', texto, flags=re.MULTILINE)


# ─── Filtros de recomendación ─────────────────────────────────────────────────

def _extraer_edge_desde_texto(texto: str) -> float:
    """
    Fallback: extrae el edge % desde la línea "EDGE:" del bloque estructurado
    "=== VEREDICTO FINAL ===" que Claude debe incluir siempre al final de su
    respuesta. Se usa cuando odds.csv no tiene cuotas reales para el mercado
    analizado (p.ej. "Más/Menos 1.5 Goles", que nunca tienen cuota real en
    odds.csv) y por tanto edge_por_outcome queda vacío.

    Anclado al campo estructurado en vez de escanear todo el texto libre:
    así se evita capturar por error un edge mencionado en otro paso del
    cálculo que no sea la conclusión final de Claude.
    """
    if not texto:
        return 0.0
    m = re.search(r'EDGE:\s*\[?([+\-]?\d{1,3}(?:[.,]\d+)?)\s*%', texto, re.IGNORECASE)
    if not m:
        return 0.0
    try:
        valor = float(m.group(1).replace(",", "."))
    except ValueError:
        return 0.0
    return round(valor, 1) if valor > 0 else 0.0


def _max_edge(datos: dict) -> float | None:
    """
    Devuelve el edge máximo de edge_por_outcome, incluyendo valores negativos.
    Un edge de -5 % es un dato real (cuota mala), no ausencia de dato.
    Devuelve None solo si no existe ninguna entrada en edge_por_outcome
    (p.ej. mercado sin cuota en odds.csv).
    """
    edges = datos.get("edge_por_outcome", {})
    if not edges:
        return None
    valores = []
    for v in edges.values():
        try:
            valores.append(float(str(v).replace("+", "").replace("%", "")))
        except ValueError:
            pass
    return max(valores) if valores else None


def _prob_seleccion_modelo(datos: dict) -> float | None:
    """
    Probabilidad (0-100) que el propio modelo Poisson asigna al resultado
    que quedó seleccionado como argmax(edge) en este mercado.

    Para "Victoria 1X2" (3 resultados posibles) usa la probabilidad del
    resultado en "mejor_seleccion". Para mercados binarios (BTTS Sí/No,
    Más/Menos 1.5) usa la probabilidad del propio lado que se está evaluando,
    ya que ahí el edge solo se calcula para una dirección.

    Devuelve None si no hay un modelo calculado para este mercado.
    """
    def _pct(s) -> float | None:
        try:
            return float(str(s).replace("%", "").replace("+", "").strip())
        except (ValueError, TypeError):
            return None

    v1x2 = datos.get("victoria1x2_modelo")
    if v1x2:
        sel  = v1x2.get("mejor_seleccion")
        mapa = {"Local": "p_local", "Empate": "p_empate", "Visitante": "p_visitante"}
        return _pct(v1x2.get(mapa[sel])) if sel in mapa else None

    for clave, campo in (
        ("btts_no_modelo", "p_btts_no"),
        ("btts_si_modelo", "p_btts_si"),
        ("menos15_modelo", "p_menos15"),
        ("mas15_modelo",   "p_mas15"),
    ):
        if clave in datos:
            return _pct(datos[clave].get(campo))
    return None


def _calcular_confianza(edge: float, puntos: int) -> str:
    """
    Confianza calculada de forma independiente (NO autoevaluada por Claude):
      · ALTO  — edge ≥ 15% y puntos ≥ 4
      · MEDIO — edge ≥ 6%  y puntos ≥ 3
      · BAJO  — cualquier otro caso
    """
    if edge >= 15.0 and puntos >= 4:
        return "Alto"
    if edge >= 6.0 and puntos >= 3:
        return "Medio"
    return "Bajo"


def _calcular_puntuacion(texto_claude: str, datos: dict) -> dict:
    """
    Calcula la puntuación del sistema de decisión (0-4 puntos).

    Condición base (obligatoria):
      · Edge ≥ 6% — si no se cumple, resultado automático NO APOSTAR.
      · El edge se toma de edge_por_outcome; si está vacío (no hay cuota real
        en odds.csv para ese mercado, p.ej. "Más/Menos 1.5 Goles") se usa como
        fallback el edge que Claude reporta en su bloque "VEREDICTO FINAL".

    Puntos:
      · xG fuente manual (BeSoccer): +2 pts
      · BTTS local últimos 5 ≥ 3:   +1 pt
      · BTTS visitante últimos 5 ≥ 3: +1 pt
      · (motivación "sin motivación": −1 pt)

    Confianza — calculada de forma independiente con _calcular_confianza()
    a partir de edge y puntos (ya NO se parsea del texto de Claude).
    xG de fuente manual (BeSoccer) eleva el piso de confianza a Medio — nunca
    se considera Bajo cuando el dato proviene de una fuente verificada a mano.

    Decisión final (dinero real):
      · Edge < 6%             → NO APOSTAR 🔴
      · Edge ≥ 6% y pts ≥ 4  → APOSTAR ✅ (confianza Baja solo añade advertencia visual)
      · Edge ≥ 6% y pts == 3  → PRECAUCIÓN 🟡 (Modo Observación)
      · Edge ≥ 6% y pts ≤ 2   → NO APOSTAR 🔴

    Reglas de cordura (bajan un APOSTAR a PRECAUCIÓN, nunca lo suben):
      · Edge por encima del umbral de ruido → probable error de input, no valor real.
        Umbral 25% si el xG es manual (BeSoccer); 12% si es estimado desde cuotas,
        porque ahí la probabilidad del modelo ya deriva de las mismas cuotas que
        se comparan contra sí mismas (circularidad → edges grandes = ruido casi seguro).
      · La señal argmax(edge) apunta a un resultado con probabilidad del propio
        modelo < 35% → se está apostando contra el resultado más probable según
        el propio modelo (p.ej. Canadá al 24.8% en vez de Marruecos al 51.7%).
        Esto nunca puede salir en verde, como máximo PRECAUCIÓN.
    """
    edge_calculado = _max_edge(datos)
    # sin_cuota=True → no hay fila en odds.csv para este mercado.
    # El edge del texto de Claude es solo referencia informativa; NUNCA determina
    # la recomendación (evita falsos APOSTAR cuando el edge numérico es negativo o nulo).
    sin_cuota = edge_calculado is None
    edge = edge_calculado if edge_calculado is not None else 0.0
    fuente = datos.get("fuente_xg", "estimado")

    btts_l5 = datos.get("btts_local_5")
    btts_v5 = datos.get("btts_visit_5")

    motivacion = datos.get("contexto_motivacion", "")
    cond_sin_motivacion = bool(motivacion and "sin motivación" in motivacion.lower())

    # Sin cuota real no hay base para recomendar, aunque el edge calculado sea 0.
    cond_edge_base  = (not sin_cuota) and edge >= 6.0
    cond_xg_manual  = fuente == "manual" or bool(datos.get("besoccer_manual"))
    cond_btts_local = btts_l5 is not None and int(btts_l5) >= 3
    cond_btts_visit = btts_v5 is not None and int(btts_v5) >= 3

    puntos = 0
    if cond_xg_manual:  puntos += 2
    if cond_btts_local: puntos += 1
    if cond_btts_visit: puntos += 1
    if cond_sin_motivacion: puntos = max(0, puntos - 1)   # −1 pt sin motivación

    confianza = _calcular_confianza(edge, puntos)

    # Piso de confianza: xG manual (BeSoccer) nunca se considera Bajo.
    if cond_xg_manual and confianza == "Bajo":
        confianza = "Medio"

    cond_confianza  = confianza in ("Alto", "Medio")

    if not cond_edge_base:
        estado   = "NO APOSTAR"
        decision = "rojo"
    elif puntos >= 4:
        estado   = "APOSTAR"
        decision = "verde"
    elif puntos == 3:
        estado   = "PRECAUCIÓN"
        decision = "amarillo"
    else:
        estado   = "NO APOSTAR"
        decision = "rojo"

    # ── Reglas de cordura: nunca suben el veredicto, solo lo bajan ───────────
    umbral_ruido    = 25.0 if cond_xg_manual else 12.0
    cond_edge_ruido = (not sin_cuota) and edge > umbral_ruido

    prob_seleccion = _prob_seleccion_modelo(datos)
    cond_prob_baja = prob_seleccion is not None and prob_seleccion < 35.0

    motivo_cordura = None
    if estado == "APOSTAR" and (cond_edge_ruido or cond_prob_baja):
        estado   = "PRECAUCIÓN"
        decision = "amarillo"
        if cond_edge_ruido:
            fuente_txt = "xG manual" if cond_xg_manual else "xG estimado"
            motivo_cordura = f"{em.EDGE_LABEL.capitalize()} inusualmente alta (+{edge:.1f}%) con {fuente_txt} — probable ruido"
        else:
            motivo_cordura = "Señal contra el resultado más probable del modelo"

    return {
        "puntos":          puntos,
        "edge":            edge,
        "sin_cuota":       sin_cuota,      # True = no hay cuota en odds.csv; mostrar "Sin cuota"
        "confianza":       confianza,
        "cond_edge_base":      cond_edge_base,
        "cond_xg_manual":      cond_xg_manual,
        "cond_btts_local":     cond_btts_local,
        "cond_btts_visit":     cond_btts_visit,
        "cond_confianza":      cond_confianza,
        "cond_sin_motivacion": cond_sin_motivacion,
        "cond_edge_ruido":     cond_edge_ruido,
        "cond_prob_baja":      cond_prob_baja,
        "prob_seleccion":      prob_seleccion,
        "motivo_cordura":      motivo_cordura,
        "btts_local_5":    btts_l5,
        "btts_visit_5":    btts_v5,
        "estado":          estado,
        "decision":        decision,   # "verde" | "amarillo" | "rojo"
    }


# ── Mercados del dashboard principal (rediseño DeOP) ──────────────────────────
MERCADOS_DASHBOARD = [
    "Victoria 1X2",
    "Ambos Marcan — Sí (BTTS Sí)",
    "Más de 1.5 Goles",
    "Menos 1.5 Goles",
]

def _banner_decision(texto_claude: str, datos: dict,
                     puntuacion: dict | None = None) -> str:
    """
    Genera el HTML del banner APOSTAR / PRECAUCIÓN / NO APOSTAR.
    Usa el sistema de puntos (0-4) si está disponible.
    """
    if puntuacion is None:
        puntuacion = _calcular_puntuacion(texto_claude, datos)

    estado    = puntuacion["estado"]
    puntos    = puntuacion["puntos"]
    edge      = puntuacion["edge"]
    confianza = puntuacion["confianza"]
    saldo     = float(st.session_state.get("saldo", 200.0))
    stake_max = round(saldo * 0.02, 2)

    stake_txt = (
        f'&nbsp;·&nbsp;Stake máx: <b>€{stake_max:.2f}</b>'
        f'<span style="opacity:.6"> (2 % de €{saldo:.0f})</span>'
    )

    # Fondos vía var(--bg-alerta-*) — ya definidas por tema en app.py (claras
    # en DeOP Claro, oscuras/tinte en DeOP Oscuro y Codere). Los colores de
    # borde/encabezado (verde/dorado/rojo) se mantienen literales — son el
    # código semáforo de 3 vías, no deben colapsar entre sí en Codere.
    if estado == "APOSTAR":
        modo_obs  = st.session_state.get("modo_observacion", False)
        etiqueta  = "📝 REGISTRAR VIRTUAL" if modo_obs else "✅ APOSTAR"
        aviso_confianza = (
            '<div style="font-size:11px;color:#b8780f;margin-top:4px;">'
            '⚠️ Confianza Baja — verifica manualmente antes de apostar dinero real.</div>'
            if confianza == "Bajo" else ""
        )
        return (
            f'<div style="background:var(--bg-alerta-exito);border:2px solid #16a34a;border-radius:8px;'
            f'padding:10px 16px;margin:10px 0;">'
            f'<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">'
            f'<span style="color:#16a34a;font-size:17px;font-weight:800;">{etiqueta}</span>'
            f'<span style="color:var(--texto);font-size:12px;">'
            f'{em.EDGE_LABEL.capitalize()}: <b style="color:#16a34a;">+{edge:.1f}%</b>'
            f'&nbsp;·&nbsp;Puntos: <b style="color:#16a34a;">{puntos}/4</b>'
            f'&nbsp;·&nbsp;Confianza: <b>{confianza}</b>'
            f'{stake_txt}</span></div>'
            f'{aviso_confianza}</div>'
        )

    if estado == "PRECAUCIÓN":
        motivo_cordura = puntuacion.get("motivo_cordura")
        aviso_cordura = (
            f'<div style="font-size:11px;color:#b8780f;margin-top:4px;">⚠️ {motivo_cordura}</div>'
            if motivo_cordura else ""
        )
        return (
            f'<div style="background:var(--bg-alerta-aviso);border:2px solid #f5a623;border-radius:8px;'
            f'padding:10px 16px;margin:10px 0;">'
            f'<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">'
            f'<span style="color:#b8780f;font-size:17px;font-weight:800;">🟡 PRECAUCIÓN</span>'
            f'<span style="color:var(--texto);font-size:12px;">'
            f'{em.EDGE_LABEL.capitalize()}: <b style="color:#b8780f;">+{edge:.1f}%</b>'
            f'&nbsp;·&nbsp;Puntos: <b style="color:#b8780f;">{puntos}/4</b>'
            f'&nbsp;·&nbsp;Confianza: <b>{confianza}</b>'
            f'{stake_txt}</span></div>'
            f'{aviso_cordura}</div>'
        )

    # NO APOSTAR
    razones: list[str] = []
    if not puntuacion["cond_edge_base"]:
        if puntuacion.get("sin_cuota"):
            razones.append(f"faltan cuotas para calcular {em.EDGE_LABEL}")
        else:
            razones.append(f"{em.EDGE_LABEL} {edge:.1f}% &lt; 6%")
    elif puntos <= 2:
        razones.append(f"puntuación {puntos}/4 insuficiente")
    if confianza == "Bajo":
        razones.append("confianza Baja")

    return (
        f'<div style="background:var(--bg-alerta-peligro);border:2px solid #dc2626;border-radius:8px;'
        f'padding:10px 16px;margin:10px 0;display:flex;align-items:center;gap:12px;flex-wrap:wrap;">'
        f'<span style="color:#dc2626;font-size:17px;font-weight:800;">❌ NO APOSTAR</span>'
        f'<span style="color:var(--texto);font-size:12px;">'
        f'{" &nbsp;·&nbsp; ".join(razones) if razones else "condiciones no cumplidas"}'
        f'{stake_txt}</span></div>'
    )


_RUTA_HIST_CLAUDE = Path(__file__).parent.parent / "data" / "claude_analysis.json"


def _guardar_historial_claude(datos: dict, puntuacion: dict, texto: str) -> None:
    """Guarda el análisis generado en data/claude_analysis.json."""
    import math
    from datetime import datetime

    probs = datos.get("probabilidades", {})
    xg_l  = float(probs.get("xg_local",     1.5) or 1.5)
    xg_v  = float(probs.get("xg_visitante", 1.2) or 1.2)
    btts_si = round((1 - math.exp(-xg_l)) * (1 - math.exp(-xg_v)) * 100, 1)

    partido = datos.get("partido", "")
    partes  = partido.split(" vs ", 1)
    eq_l    = partes[0].strip() if len(partes) > 0 else "Local"
    eq_v    = partes[1].strip() if len(partes) > 1 else "Visitante"

    entrada = {
        "fecha_hora":      datetime.now().strftime("%d/%m/%Y %H:%M"),
        "partido":         partido,
        "mercado":         datos.get("mercado", ""),
        "edge":            round(puntuacion.get("edge", 0.0), 1),
        "puntos":          puntuacion.get("puntos", 0),
        "veredicto":       puntuacion.get("estado", "NO APOSTAR"),
        "texto_analisis":  texto,
        # Datos para gráficos SCADA
        "confianza":       puntuacion.get("confianza", "Bajo"),
        "equipo_local":    eq_l,
        "equipo_visitante": eq_v,
        "xg_local":        xg_l,
        "xg_visitante":    xg_v,
        "prob_btts_si":    btts_si,
        "prob_btts_no":    round(100 - btts_si, 1),
        "probabilidades":  {k: v for k, v in probs.items()},
        "puntuacion_scada": {
            k: v for k, v in puntuacion.items()
            if isinstance(v, (int, float, bool, str))
        },
    }
    historial: list = []
    if _RUTA_HIST_CLAUDE.exists():
        try:
            with open(_RUTA_HIST_CLAUDE, "r", encoding="utf-8") as f:
                historial = json.load(f)
        except Exception:
            historial = []
    historial.insert(0, entrada)
    try:
        with open(_RUTA_HIST_CLAUDE, "w", encoding="utf-8") as f:
            json.dump(historial, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"[HistorialClaude] Error al guardar: {exc}")


_RUTA_VIRTUAL = Path(__file__).parent.parent / "data" / "virtual_bets.csv"
_COLS_VIRTUAL  = ["fecha", "partido", "mercado", "cuota", "stake_virtual",
                  "edge_pct", "puntos_sistema", "confianza", "resultado", "pl_virtual"]


def _guardar_apuesta_virtual(datos: dict, puntuacion: dict, texto_claude: str) -> None:
    """Guarda la apuesta virtual en data/virtual_bets.csv."""
    from datetime import date as _date
    m = (re.search(r'CUOTA:\s*([\d]+[.,][\d]+)', texto_claude) or
         re.search(r'@\s*([\d]+[.,][\d]+)', texto_claude))
    try:
        cuota_rec = float(m.group(1).replace(",", ".")) if m else 2.0
    except (ValueError, IndexError):
        cuota_rec = 2.0

    saldo      = float(st.session_state.get("saldo", 200.0))
    stake      = round(saldo * 0.02, 2)
    edge_val   = puntuacion.get("edge", 0.0)
    confianza  = puntuacion.get("confianza", "Bajo")

    nueva = {
        "fecha":          _date.today().strftime("%d/%m/%Y"),
        "partido":        datos.get("partido", ""),
        "mercado":        datos.get("mercado", ""),
        "cuota":          round(cuota_rec, 2),
        "stake_virtual":  stake,
        "edge_pct":       f"{edge_val:.1f}%",
        "puntos_sistema": puntuacion.get("puntos", 0),
        "confianza":      confianza,
        "resultado":      "Pendiente",
        "pl_virtual":     0.0,
    }
    try:
        if _RUTA_VIRTUAL.exists():
            df = pd.read_csv(_RUTA_VIRTUAL)
        else:
            df = pd.DataFrame(columns=_COLS_VIRTUAL)
        pd.concat([df, pd.DataFrame([nueva])], ignore_index=True).to_csv(
            _RUTA_VIRTUAL, index=False
        )
    except Exception as exc:
        print(f"[VirtualBets] Error al guardar: {exc}")


def _panel_apuestas_virtuales() -> None:
    """Panel de estadísticas de apuestas virtuales (≥ 14 días de datos)."""
    if not _RUTA_VIRTUAL.exists():
        st.info("Sin apuestas virtuales aún. Registra análisis con el botón azul.")
        return
    try:
        df = pd.read_csv(_RUTA_VIRTUAL)
    except Exception:
        return
    if df.empty:
        st.info("Sin apuestas virtuales registradas.")
        return

    # Normalizar nombre de columna resultado (soporta ambas versiones)
    if "resultado_predicho" in df.columns and "resultado" not in df.columns:
        df = df.rename(columns={"resultado_predicho": "resultado"})

    total     = len(df)
    ganadas   = len(df[df["resultado"] == "Ganado"])
    perdidas  = len(df[df["resultado"] == "Perdido"])
    pend      = len(df[df["resultado"] == "Pendiente"])
    resueltas = ganadas + perdidas

    pct_acierto = round(ganadas / resueltas * 100, 1) if resueltas > 0 else 0.0

    # P&L real: usar pl_virtual si existe; si no, calcularlo desde cuota y stake
    if "pl_virtual" in df.columns:
        df["pl_virtual"] = pd.to_numeric(df["pl_virtual"], errors="coerce").fillna(0)
        roi_bruto = float(df["pl_virtual"].sum())
    else:
        roi_bruto = 0.0
        df["stake_virtual"] = pd.to_numeric(df.get("stake_virtual", 4.0), errors="coerce").fillna(4.0)
        for _, row in df[df["resultado"].isin(["Ganado", "Perdido"])].iterrows():
            s = float(row.get("stake_virtual", 4.0) or 4.0)
            try:
                c = float(row.get("cuota", 2.0) or 2.0)
            except (ValueError, TypeError):
                c = 2.0
            roi_bruto += (c - 1) * s if row["resultado"] == "Ganado" else -s

    total_apostado = float(df.loc[df["resultado"].isin(["Ganado","Perdido"]),
                                  "stake_virtual"].abs().sum()) if "stake_virtual" in df.columns else max(resueltas * 4.0, 1.0)
    roi_pct = round(roi_bruto / max(total_apostado, 0.01) * 100, 1) if resueltas > 0 else 0.0

    col_est = "#16a34a" if roi_bruto >= 0 else "#dc2626"
    st.markdown(
        f'<div style="background:var(--bg-tarjeta);border:1px solid var(--borde);'
        f'border-left:5px solid var(--acento-dorado);'
        f'border-radius:8px;padding:12px 14px;margin:8px 0;">'
        f'<div style="font-size:10px;color:var(--acento-morado);font-weight:800;letter-spacing:1px;'
        f'text-transform:uppercase;margin-bottom:8px;padding-bottom:5px;'
        f'border-bottom:1px solid var(--borde);">◈ Modo Observación — Estadísticas Virtuales</div>'
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;">'
        f'<div style="text-align:center;">'
        f'<div style="font-size:18px;font-weight:800;color:var(--acento-morado);">{total}</div>'
        f'<div style="font-size:9px;color:var(--texto-apagado);text-transform:uppercase;">Total</div></div>'
        f'<div style="text-align:center;">'
        f'<div style="font-size:18px;font-weight:800;color:#16a34a;">{pct_acierto}%</div>'
        f'<div style="font-size:9px;color:var(--texto-apagado);text-transform:uppercase;">Acierto</div></div>'
        f'<div style="text-align:center;">'
        f'<div style="font-size:18px;font-weight:800;color:{col_est};">{roi_pct:+.1f}%</div>'
        f'<div style="font-size:9px;color:var(--texto-apagado);text-transform:uppercase;">ROI</div></div>'
        f'<div style="text-align:center;">'
        f'<div style="font-size:18px;font-weight:800;color:{col_est};">€{roi_bruto:+.2f}</div>'
        f'<div style="font-size:9px;color:var(--texto-apagado);text-transform:uppercase;">Beneficio</div></div>'
        f'</div>'
        f'<div style="font-size:11px;color:var(--texto-apagado);margin-top:8px;">'
        f'{pend} pendientes · {ganadas}G / {perdidas}P de {resueltas} resueltas</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _datos_desde_sesion() -> dict:
    """Construye el diccionario de datos desde el estado de sesión."""
    if not st.session_state.get("analisis_listo"):
        return {}

    datos = {
        "partido": st.session_state.get("partido_activo", ""),
        "liga":    st.session_state.get("liga_activa", ""),
        "mercado": st.session_state.get("claude_mercado", ""),
    }

    if probs := st.session_state.get("probs_partido"):
        datos["probabilidades"] = probs
    if cuotas := st.session_state.get("mejor_cuota_partido"):
        datos["mejor_cuota"] = cuotas
    # Cuotas Ambos Marcan introducidas manualmente (si existen)
    if btts := st.session_state.get("btts_cuotas_manual"):
        datos["cuotas_ambos_marcan_manual"] = btts
    # Cuotas Resultado 1ª Parte introducidas manualmente (si existen)
    if c1t := st.session_state.get("cuotas_1t_manual"):
        datos["cuotas_resultado_1t_manual"] = c1t
    # Fuente del xG activo
    if fuente := st.session_state.get("fuente_xg_activa"):
        datos["fuente_xg"] = fuente
    # Datos de forma BTTS y ELO (opcionales, solo en partidos manuales)
    for campo in ("btts_local_5", "btts_visit_5", "elo_local", "elo_visit"):
        val = st.session_state.get(campo)
        if val is not None:
            datos[campo] = val
    # Contexto de motivación del partido
    if mot := st.session_state.get("motivacion_partido"):
        datos["contexto_motivacion"] = mot
    if ult := st.session_state.get("ultimo_partido_temporada"):
        datos["ultimo_partido_temporada"] = ult

    return datos


def mostrar():
    """Renderiza el módulo de análisis con Claude — estilo DeOP Connect."""
    from modules.scada_charts import (
        _CONFIG, _CSS_COMPACTO,
        semaforo_html, gauge_donut_gris, gauge_puntos_deop,
        panel_info_partido_html,
        barras_probabilidad_deop, donut_ambos_marcan,
        tabla_edges, panel_xg_comparativo, panel_forma_reciente, panel_balanza_elo,
        DEOP_PETROLEO, _paleta_activa,
    )
    from modules.goal_prediction import mostrar as _mostrar_goles_panel

    paleta = _paleta_activa()

    st.markdown(_CSS_COMPACTO, unsafe_allow_html=True)

    def _limpiar_analisis() -> None:
        st.session_state.pop("claude_analisis",   None)
        st.session_state.pop("claude_puntuacion", None)

    # ══════════════════════════════════════════════════════════════════════════
    # CONTROLES — selector de mercado, partido activo, formulario de análisis
    # ══════════════════════════════════════════════════════════════════════════
    # format_func solo cambia el texto mostrado en el desplegable (nomenclatura
    # Codere) — el valor devuelto/guardado en session_state["claude_mercado"]
    # sigue siendo la clave canónica exacta de MERCADOS_CLAUDE, así que no
    # afecta ningún lookup, comparación ni lo que se persiste en el historial.
    mercado = st.selectbox(
        "Tipo de mercado:",
        MERCADOS_CLAUDE,
        key="claude_mercado",
        format_func=em.titulo_mercado,
        on_change=_limpiar_analisis,
    )

    datos = _datos_desde_sesion()

    if not datos:
        st.markdown(
            '<div style="color:#8aaa99;font-size:13px;padding:12px 0;">'
            'Selecciona un partido en <b>Análisis de Partidos</b> '
            'para activar el análisis con Claude AI.</div>',
            unsafe_allow_html=True,
        )
        return

    partido = datos.get("partido", "")
    st.markdown(
        f'<div style="background:{DEOP_PETROLEO};border-radius:8px;'
        f'padding:10px 18px;margin-bottom:10px;display:flex;align-items:center;'
        f'justify-content:space-between;">'
        f'<span style="color:#ffffff;font-size:15px;font-weight:800;'
        f'letter-spacing:.3px;">⚽ {partido}</span>'
        f'<span style="color:{paleta["dorado"]};font-size:11px;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:1px;">Partido en análisis</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    with st.expander("⚽ Predicción de Goles", expanded=False):
        _mostrar_goles_panel()

    saldo     = float(st.session_state.get("saldo", 200.0))
    stake_max = round(saldo * 0.02, 2)
    st.markdown(
        f'<div style="font-size:12px;color:{paleta["texto"]};margin-bottom:8px;">'
        f'Stake máx.: <b style="color:{paleta["dorado"]};">€{stake_max:.2f}</b>'
        f'&nbsp;<span style="opacity:.6">(2% de €{saldo:.0f})</span></div>',
        unsafe_allow_html=True,
    )

    with st.expander("🔍 Ver datos del análisis", expanded=False):
        st.markdown(panel_info_partido_html(datos), unsafe_allow_html=True)

    col_fl, col_fv = st.columns(2)
    with col_fl:
        forma_local = st.text_input(
            "Forma reciente local (últimos 5)*",
            value=st.session_state.get("forma_reciente_local_csv", ""),
            placeholder="Ej: W,W,D,L,W", key="claude_forma_local",
        )
    with col_fv:
        forma_visit = st.text_input(
            "Forma reciente visitante (últimos 5)*",
            value=st.session_state.get("forma_reciente_visit_csv", ""),
            placeholder="Ej: L,D,W,W,L", key="claude_forma_visit",
        )
    _forma_completa = bool(forma_local.strip()) and bool(forma_visit.strip())
    if not _forma_completa:
        st.caption("⚠️ Completa la forma reciente de ambos equipos para habilitar el análisis.")

    if st.button("🤖 Analizar con Claude AI", key="btn_claude",
                 use_container_width=True, disabled=not _forma_completa):
        _analisis_ok = False
        _status = st.empty()
        with st.spinner(f"Analizando «{em.titulo_mercado(mercado)}»…"):
            try:
                datos["forma_reciente_local"]      = forma_local.strip()
                datos["forma_reciente_visitante"]  = forma_visit.strip()
                _status.caption("⏳ Cargando cuotas…")
                datos_c  = _enriquecer_con_cuotas(datos)
                _status.caption("⏳ Obteniendo estadísticas (máx. 8s)…")
                datos_c  = _enriquecer_con_stats(datos_c)
                _status.caption("⏳ Preparando datos para Claude…")
                datos_c  = _enriquecer_con_alertas(datos_c)
                datos_c  = _enriquecer_para_mercado(datos_c, mercado)
                _status.caption("⏳ Llamando a Claude AI (máx. 45s)…")
                analisis = analizar_con_claude(datos_c, mercado)
                _status.caption("⏳ Calculando puntuación…")
                # _calcular_puntuacion ya aplica el fallback de edge (lee
                # "EDGE:" del bloque VEREDICTO FINAL si no hay cuota real
                # en odds.csv) y devuelve estado/decision ya consistentes.
                _punt    = _calcular_puntuacion(analisis, datos_c)
                _edge_val = float(_punt.get("edge") or 0.0)
                st.session_state["claude_analisis"]       = analisis
                st.session_state["claude_datos_analisis"] = datos_c
                st.session_state["claude_mercado_activo"] = mercado
                st.session_state["claude_puntuacion"]     = _punt
                st.session_state["claude_edge_pct"]       = _edge_val
                # Almacenar por mercado para que el gauge recuerde al cambiar
                st.session_state[f"claude_edge_{mercado}"] = _edge_val
                _analisis_ok = True
                _status.empty()
                try:
                    _guardar_historial_claude(datos_c, _punt, analisis)
                except Exception as _e_hist:
                    st.warning(f"⚠️ No se pudo guardar en historial: {_e_hist}")
            except anthropic.AuthenticationError:
                _status.empty()
                st.error("API key inválida. Verifica la key en modules/claude_analysis.py")
            except Exception as exc:
                _status.empty()
                st.error(f"Error en el análisis: {exc}")
        # st.rerun() fuera del spinner para que Streamlit lo procese limpio
        if _analisis_ok:
            st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # RESULTADOS — presentación HMI/SCADA en filas, sin texto largo visible
    # ══════════════════════════════════════════════════════════════════════════
    resultado       = st.session_state.get("claude_analisis")
    datos_guardados = st.session_state.get("claude_datos_analisis", {})
    mercado_activo  = st.session_state.get("claude_mercado_activo", mercado)
    puntuacion      = st.session_state.get("claude_puntuacion") or (
        _calcular_puntuacion(resultado, datos_guardados) if resultado else None
    )

    if not resultado or not puntuacion:
        return

    edge_der = float(puntuacion.get("edge") or 0.0)
    pts      = puntuacion.get("puntos", 0)
    conf     = puntuacion.get("confianza", "Bajo")
    _CONF_NUM = {"Alto": 85.0, "Medio": 50.0, "Bajo": 18.0}
    confianza_pct = _CONF_NUM.get(conf, 18.0)

    st.markdown(
        f'<div style="font-size:10px;color:{paleta["texto"]};font-weight:800;'
        f'letter-spacing:2px;text-transform:uppercase;margin:14px 0 8px;">'
        f'◈ {em.titulo_mercado(mercado_activo)}</div>',
        unsafe_allow_html=True,
    )

    # ── Fila 1 — semáforo + banner (veredicto y motivo) + gauges edge/confianza/puntos ──
    col_luz, col_sem, col_g1, col_g2, col_g3 = st.columns([0.8, 1.6, 1, 1, 1])
    with col_luz:
        st.markdown(semaforo_html(edge_der, puntuacion), unsafe_allow_html=True)
    with col_sem:
        st.markdown(
            _banner_decision(resultado, datos_guardados, puntuacion),
            unsafe_allow_html=True,
        )
    with col_g1:
        st.plotly_chart(gauge_donut_gris(max(0.0, edge_der), f"{em.EDGE_LABEL.capitalize()} %", paleta["dorado"]),
                        use_container_width=True, config=_CONFIG, key="fila1_gauge_edge")
    with col_g2:
        st.plotly_chart(gauge_donut_gris(confianza_pct, "Confianza %", paleta["petroleo"]),
                        use_container_width=True, config=_CONFIG, key="fila1_gauge_conf")
    with col_g3:
        st.plotly_chart(gauge_puntos_deop(pts, color=paleta["dorado"]),
                        use_container_width=True, config=_CONFIG, key="fila1_gauge_pts")

    # ── Fila 2 — tabla de edges + barras 1X2 + donut BTTS ──────────────────────
    col_tabla, col_barras, col_donut = st.columns(3)
    with col_tabla:
        html_tabla = tabla_edges(datos_guardados)
        if html_tabla:
            st.markdown(html_tabla, unsafe_allow_html=True)
        else:
            st.caption("Tabla de edges no disponible para este mercado.")
    with col_barras:
        if datos_guardados.get("probabilidades"):
            st.plotly_chart(barras_probabilidad_deop(datos_guardados),
                            use_container_width=True, config=_CONFIG, key="fila2_barras")
    with col_donut:
        _probs_raw = datos_guardados.get("probabilidades", {})
        try:
            _xg_l = float(_probs_raw.get("xg_local") or 0)
            _xg_v = float(_probs_raw.get("xg_visitante") or 0)
        except (ValueError, TypeError):
            _xg_l = _xg_v = 0.0
        if _xg_l > 0 and _xg_v > 0:
            st.plotly_chart(donut_ambos_marcan(datos_guardados),
                            use_container_width=True, config=_CONFIG, key="fila2_donut")

    # ── Fila 3 — xG comparativo + forma reciente + balanza ELO ────────────────
    col_xg, col_forma, col_elo = st.columns(3)
    with col_xg:
        st.markdown(panel_xg_comparativo(datos_guardados), unsafe_allow_html=True)
    with col_forma:
        st.markdown(panel_forma_reciente(datos_guardados), unsafe_allow_html=True)
    with col_elo:
        st.markdown(panel_balanza_elo(datos_guardados), unsafe_allow_html=True)

    # Apuesta virtual (modo observación)
    if st.session_state.get("modo_observacion"):
        if puntuacion.get("estado") == "APOSTAR":
            if st.button("📝 Registrar como apuesta virtual",
                         key="btn_virtual", use_container_width=True):
                _guardar_apuesta_virtual(datos_guardados, puntuacion, resultado)
                st.success("✅ Apuesta virtual registrada en data/virtual_bets.csv")
        _panel_apuestas_virtuales()

    # ── Informe completo — texto íntegro de Claude, oculto por defecto ─────────
    # Sin unsafe_allow_html (mismo criterio que first_half_analysis.py): el texto
    # es contenido generado por el LLM y puede reflejar entrada del usuario (p.ej.
    # nombres de equipo) — el renderer de markdown de Streamlit ya interpreta
    # **negrita**/listas y sanea cualquier HTML/script embebido sin ejecutarlo.
    with st.expander("📋 Informe completo", expanded=False):
        st.markdown(_normalizar_formato(resultado))
