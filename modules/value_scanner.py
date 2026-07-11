"""Módulo: Escáner de valor — detecta apuestas con edge ≥ 6% usando el modelo Poisson."""

import requests
import streamlit as st
from scipy.stats import poisson

# Reutiliza constantes y lista de ligas de odds_api para mantenerse sincronizado
from modules.odds_api import API_KEY, BASE_URL, LIGAS_BUSQUEDA as LIGAS_SCAN

UMBRAL_EDGE = 6.0  # edge mínimo en puntos porcentuales para mostrar la apuesta
MAX_GOLES   = 9    # límite del modelo Poisson


# ─── Helpers de cuotas ───────────────────────────────────────────────────────

def _todos_precios(bookmakers: list[dict], market_key: str, outcome_name: str) -> list[float]:
    """Devuelve todos los precios disponibles para un outcome dado."""
    precios: list[float] = []
    for bookie in bookmakers:
        for market in bookie.get("markets", []):
            if market["key"] != market_key:
                continue
            for outcome in market["outcomes"]:
                if outcome["name"] == outcome_name:
                    precios.append(float(outcome["price"]))
    return precios


def _mejor_precio_h2h(bookmakers: list[dict], outcome_name: str) -> float:
    """Mejor cuota (máxima) disponible en el mercado H2H para un outcome."""
    return max(_todos_precios(bookmakers, "h2h", outcome_name), default=0.0)


def _mejor_precio_totals(bookmakers: list[dict], side: str, punto: float = 2.5) -> float:
    """Mejor cuota (máxima) para Over/Under en el punto especificado."""
    mejor = 0.0
    for bookie in bookmakers:
        for market in bookie.get("markets", []):
            if market["key"] != "totals":
                continue
            for outcome in market["outcomes"]:
                if (outcome["name"] == side
                        and float(outcome.get("point", 0)) == punto
                        and float(outcome["price"]) > mejor):
                    mejor = float(outcome["price"])
    return mejor


def _prob_implicita_media(precios: list[float]) -> float:
    if not precios:
        return 0.0
    return sum(1.0 / p for p in precios) / len(precios)


# ─── Modelo Poisson ──────────────────────────────────────────────────────────

def _xg_desde_prob(prob_norm: float) -> float:
    return round(max(0.5, min(3.5, prob_norm * 3.2)), 2)


def _poisson(xg_l: float, xg_v: float) -> dict:
    """Calcula probabilidades 1X2 y Over/Under 2.5 con distribución de Poisson."""
    p_l = p_e = p_v = over25 = 0.0
    for h in range(MAX_GOLES):
        for a in range(MAX_GOLES):
            p = poisson.pmf(h, xg_l) * poisson.pmf(a, xg_v)
            if   h > a:  p_l   += p
            elif h == a: p_e   += p
            else:        p_v   += p
            if h + a > 2: over25 += p
    total = (p_l + p_e + p_v) or 1.0
    return {
        "local":     p_l / total,
        "empate":    p_e / total,
        "visitante": p_v / total,
        "over25":    over25,
        "under25":   1.0 - over25,
    }


def _edge(prob_modelo: float, mejor_cuota: float) -> float:
    """Edge en puntos porcentuales: (cuota × P_modelo − 1) × 100."""
    if mejor_cuota <= 1.0:
        return -99.0
    return (mejor_cuota * prob_modelo - 1) * 100.0


# ─── Helpers para los 2 mercados ─────────────────────────────────────────────

def _mejor_precio_btts(bookmakers: list[dict], outcome: str) -> float:
    """Mejor cuota del mercado BTTS ('Yes'/'No')."""
    return max(
        (float(o["price"])
         for b in bookmakers
         for m in b.get("markets", []) if m["key"] == "btts"
         for o in m["outcomes"] if o["name"] == outcome),
        default=0.0,
    )


def _mejor_precio_dc(bookmakers: list[dict], outcome: str) -> float:
    """Mejor cuota del mercado Double Chance ('Home/Draw', 'Away/Draw', 'Home/Away')."""
    return max(
        (float(o["price"])
         for b in bookmakers
         for m in b.get("markets", []) if m["key"] == "doubleChance"
         for o in m["outcomes"] if o["name"] == outcome),
        default=0.0,
    )


def _cuota_dc_de_h2h(cuota_a: float, cuota_b: float) -> float:
    """Aproxima cuota Doble Oportunidad desde dos cuotas H2H (media armónica)."""
    if cuota_a <= 1.0 or cuota_b <= 1.0:
        return 0.0
    return (cuota_a * cuota_b) / (cuota_a + cuota_b)


# ─── Escáner principal ───────────────────────────────────────────────────────

def _partidos_espn_sin_cuotas() -> list[dict]:
    """
    Devuelve partidos de ESPN que NO tienen cuotas en The Odds API.
    Se muestran en el escáner con edge=None (para análisis manual).
    Solo se ejecuta si ESPN está habilitado en las fuentes de datos.
    """
    if not st.session_state.get("fuente_espn", True):
        return []
    try:
        from modules.espn_api import obtener_partidos_hoy
        return obtener_partidos_hoy()
    except Exception:
        return []


def escanear_valor() -> list[dict]:
    """
    Escanea todas las ligas activas y devuelve oportunidades con edge ≥ UMBRAL_EDGE.
    Fuentes combinadas:
      - The Odds API (con cuotas reales → edge calculable)
      - ESPN (sin cuotas → incluidos para análisis manual, edge = None)
    """
    oportunidades: list[dict] = []
    partidos_con_cuotas: set[str] = set()   # para no duplicar con ESPN

    # ── The Odds API (cuotas reales → edge calculable) ───────────────────────
    if st.session_state.get("fuente_odds", True):
        for nombre_liga, sport_key in LIGAS_SCAN.items():
            try:
                resp = requests.get(
                    f"{BASE_URL}/sports/{sport_key}/odds/",
                    params={
                        "apiKey":     API_KEY,
                        "regions":    "eu",
                        "markets":    "h2h,totals",
                        "oddsFormat": "decimal",
                        "bookmakers": "bet365,betfair_ex_best_odds,codere,betfair_ex_uk",
                    },
                    timeout=10,
                )
                if resp.status_code != 200:
                    continue
                partidos = resp.json()
            except Exception:
                continue

            for p in partidos:
                local  = p["home_team"]
                visita = p["away_team"]

                nombre     = f"{local} vs {visita}"
                bookmakers = p.get("bookmakers", [])
                partidos_con_cuotas.add(nombre)

                p_l_raw = _prob_implicita_media(_todos_precios(bookmakers, "h2h", local))
                p_e_raw = _prob_implicita_media(_todos_precios(bookmakers, "h2h", "Draw"))
                p_v_raw = _prob_implicita_media(_todos_precios(bookmakers, "h2h", visita))
                total   = (p_l_raw + p_e_raw + p_v_raw) or 1.0

                xg_l  = _xg_desde_prob(p_l_raw / total)
                xg_v  = _xg_desde_prob(p_v_raw / total)
                probs = _poisson(xg_l, xg_v)

                for mercado, prob_modelo, mejor_cuota in [
                    ("Victoria Local",     probs["local"],     _mejor_precio_h2h(bookmakers, local)),
                    ("Empate",             probs["empate"],    _mejor_precio_h2h(bookmakers, "Draw")),
                    ("Victoria Visitante", probs["visitante"], _mejor_precio_h2h(bookmakers, visita)),
                    ("Over 2.5 Goles",     probs["over25"],    _mejor_precio_totals(bookmakers, "Over")),
                    ("Under 2.5 Goles",    probs["under25"],   _mejor_precio_totals(bookmakers, "Under")),
                ]:
                    if mejor_cuota <= 1.0:
                        continue
                    edge = _edge(prob_modelo, mejor_cuota)
                    if edge >= UMBRAL_EDGE:
                        oportunidades.append({
                            "Partido":          nombre,
                            "Liga":             nombre_liga,
                            "Mercado":          mercado,
                            "Prob. Modelo":     prob_modelo,
                            "Cuota Disponible": mejor_cuota,
                            "Edge %":           edge,
                            "Fuente":           "OddsAPI",
                        })

    # ── ESPN (partidos sin cuotas → edge estimado con Poisson) ──────────────
    if st.session_state.get("fuente_espn", True):
        for p in _partidos_espn_sin_cuotas():
            nombre = p["partido"]
            if nombre in partidos_con_cuotas:
                continue   # ya fue escaneado con cuotas reales

            xg_l  = float(p.get("xg_local",     1.4))
            xg_v  = float(p.get("xg_visitante", 1.1))
            probs = _poisson(xg_l, xg_v)

            # Sin cuotas de mercado: mostramos probabilidades del modelo
            # solo si alguna supera el 60% (para filtrar partidos sin información)
            max_prob = max(probs["local"], probs["empate"], probs["visitante"])
            if max_prob < 0.55:
                continue

            mejor_resultado = max(
                [("Victoria Local", probs["local"]),
                 ("Empate",         probs["empate"]),
                 ("Victoria Visitante", probs["visitante"])],
                key=lambda x: x[1],
            )
            oportunidades.append({
                "Partido":          nombre,
                "Liga":             p.get("liga", "ESPN"),
                "Mercado":          mejor_resultado[0],
                "Prob. Modelo":     mejor_resultado[1],
                "Cuota Disponible": 0.0,    # sin cuota de mercado
                "Edge %":           0.0,    # edge no calculable sin cuotas
                "Fuente":           "ESPN",
            })

    # Ordenar: primero los que tienen edge real (OddsAPI), luego ESPN
    oportunidades.sort(key=lambda x: (x["Fuente"] != "OddsAPI", -x["Edge %"]))
    return oportunidades


# ─── Renderizado ─────────────────────────────────────────────────────────────

def mostrar_resultados(resultados: list[dict]) -> None:
    """Renderiza la tabla de oportunidades de valor en Streamlit."""
    if not resultados:
        st.markdown(
            '<div class="alerta-peligro" style="text-align:center;">'
            f'No se detectaron apuestas con edge &gt; {UMBRAL_EDGE:.0f}% hoy. '
            'El mercado está bien calibrado o no hay partidos con valor.</div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f'<div style="font-size:13px;color:var(--texto-apagado);margin-bottom:12px;">'
        f'<span style="color:#16a34a;font-weight:700;">{len(resultados)}</span> '
        f'apuesta(s) con valor detectado (edge &gt; {UMBRAL_EDGE:.0f}%)</div>',
        unsafe_allow_html=True,
    )

    # Logos (solo si TheSportsDB está habilitado)
    try:
        from modules.sports_db import logo_html as _logo
    except Exception:
        def _logo(nombre, px=18): return ""

    n_odds = sum(1 for r in resultados if r.get("Fuente") == "OddsAPI")
    n_espn = len(resultados) - n_odds

    resumen = f'<span style="color:#16a34a;font-weight:700;">{n_odds}</span> con edge real'
    if n_espn:
        resumen += f' · <span style="color:var(--acento-azul);">{n_espn}</span> ESPN (sin cuotas)'
    st.markdown(
        f'<div style="font-size:12px;color:var(--texto-apagado);margin-bottom:8px;">{resumen}</div>',
        unsafe_allow_html=True,
    )

    filas_html = ""
    for r in resultados:
        edge     = r["Edge %"]
        prob_pct = r["Prob. Modelo"] * 100
        cuota    = r["Cuota Disponible"]
        fuente   = r.get("Fuente", "OddsAPI")

        if fuente == "ESPN":
            color_edge = "var(--acento-azul)"
            cuota_txt  = "Sin cuota"
            edge_txt   = "ESPN"
        else:
            # Verde para edge alto, naranja para medio, azul-petróleo para bajo
            color_edge = "#16a34a" if edge >= 15 else ("#f39c12" if edge >= 10 else "var(--acento-azul)")
            cuota_txt  = f"{cuota:.2f}"
            edge_txt   = f"+{edge:.1f}%"

        # Logos de ambos equipos
        equipos = r["Partido"].split(" vs ", 1)
        logo_l  = _logo(equipos[0].strip(), 18) if len(equipos) > 0 else ""
        logo_v  = _logo(equipos[1].strip(), 18) if len(equipos) > 1 else ""
        partido_html = (
            f"{logo_l}{equipos[0]} "
            f"<span style='color:var(--texto-apagado);'>vs</span> "
            f"{logo_v}{equipos[1]}"
        ) if len(equipos) > 1 else r["Partido"]

        filas_html += (
            f"<tr>"
            f"<td style='text-align:left;color:var(--texto);'>{partido_html}</td>"
            f"<td style='color:var(--texto-apagado);font-size:11px;'>{r['Liga']}</td>"
            f"<td style='color:var(--texto);font-weight:600;'>{r['Mercado']}</td>"
            f"<td style='color:var(--acento-azul);'>{prob_pct:.1f}%</td>"
            f"<td style='color:var(--acento-dorado);font-weight:700;'>{cuota_txt}</td>"
            f"<td style='color:{color_edge};font-weight:700;'>{edge_txt}</td>"
            f"</tr>"
        )

    st.markdown(f"""
<table class="tabla-historial" style="width:100%;">
  <thead>
    <tr>
      <th style="text-align:left;">Partido</th>
      <th>Liga</th>
      <th>Mercado recomendado</th>
      <th>Prob. Modelo</th>
      <th>Cuota Disponible</th>
      <th>Edge %</th>
    </tr>
  </thead>
  <tbody>{filas_html}</tbody>
</table>
""", unsafe_allow_html=True)
