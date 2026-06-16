"""Módulo: Integración con The Odds API — partidos y cuotas reales."""

import os
import requests
import pandas as pd
import streamlit as st
from datetime import date, datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

os.makedirs(Path(__file__).parent.parent / "data", exist_ok=True)

API_KEY  = os.getenv("ODDS_API_KEY", "")
BASE_URL = "https://api.the-odds-api.com/v4"

LIGAS = {
    "🏆 Champions League":  "soccer_uefa_champs_league",
    "🌍 Mundial 2026":      "soccer_fifa_world_cup",
    "🌍 Amistosos Int.":    "soccer_international_friendlies",
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League":   "soccer_epl",
    "🇪🇸 La Liga":           "soccer_spain_la_liga",
    "🇪🇸 Segunda División":  "soccer_spain_segunda_division",
    "🇩🇪 Bundesliga":        "soccer_germany_bundesliga",
    "🇮🇹 Serie A":           "soccer_italy_serie_a",
    "🇫🇷 Ligue 1":           "soccer_france_ligue_one",
}

# Claves de casas en The Odds API → columna en el CSV
CASAS_API = {
    "codere":               "codere",
    "bet365":               "bet365",
    "betfair_ex_best_odds": "betfair",
    "betfair_ex_uk":        "betfair",
}
BOOKMAKERS_PARAM = "codere,bet365,betfair_ex_best_odds,betfair_ex_uk"

RUTA_PARTIDOS = Path(__file__).parent.parent / "data" / "matches.csv"
RUTA_CUOTAS   = Path(__file__).parent.parent / "data" / "odds.csv"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _fecha_hoy() -> str:
    """Fecha de hoy en formato YYYY-MM-DD (hora local)."""
    return date.today().isoformat()


def _es_hoy(commence_time: str) -> bool:
    """
    Devuelve True si el commence_time del partido corresponde a hoy (hora local).
    commence_time llega en formato ISO-8601 UTC, p.ej. '2026-06-01T19:00:00Z'.
    """
    if not commence_time:
        return True  # si no hay fecha, incluir por defecto
    try:
        dt_utc = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
        return dt_utc.astimezone().date() == date.today()
    except (ValueError, AttributeError):
        return True


def _filtrar_hoy(partidos: list[dict]) -> list[dict]:
    """Filtra la lista de partidos de la API para quedarse solo con los de hoy."""
    return [p for p in partidos if _es_hoy(p.get("commence_time", ""))]


def _prob_media(precios: list[float]) -> float:
    if not precios:
        return 0.0
    return sum(1.0 / p for p in precios) / len(precios)


def _xg_desde_prob(prob_norm: float) -> float:
    """Estima xG a partir de la probabilidad normalizada de victoria."""
    return round(max(0.5, min(3.5, prob_norm * 3.2)), 1)


def _llamar_api(sport_key: str) -> list[dict]:
    url = f"{BASE_URL}/sports/{sport_key}/odds/"
    params = {
        "apiKey":     API_KEY,
        "regions":    "eu",
        "markets":    "h2h,totals",
        "oddsFormat": "decimal",
        "bookmakers": BOOKMAKERS_PARAM,
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _extraer_h2h(bookmakers: list[dict]) -> dict[str, dict[str, float]]:
    """Devuelve {nombre_outcome: {columna_csv: precio}} para el mercado H2H."""
    resultado: dict[str, dict[str, float]] = {}
    for bookie in bookmakers:
        col = CASAS_API.get(bookie["key"])
        if not col:
            continue
        for market in bookie.get("markets", []):
            if market["key"] != "h2h":
                continue
            for outcome in market["outcomes"]:
                name  = outcome["name"]
                precio = float(outcome["price"])
                if name not in resultado:
                    resultado[name] = {}
                # Guardar el mejor precio si hay varias claves para la misma casa
                if col not in resultado[name] or precio > resultado[name][col]:
                    resultado[name][col] = precio
    return resultado


def _extraer_totals_25(bookmakers: list[dict]) -> dict[str, dict[str, float]]:
    """Devuelve {"Over": {col: precio}, "Under": {col: precio}} para el total 2.5."""
    resultado: dict[str, dict[str, float]] = {"Over": {}, "Under": {}}
    for bookie in bookmakers:
        col = CASAS_API.get(bookie["key"])
        if not col:
            continue
        for market in bookie.get("markets", []):
            if market["key"] != "totals":
                continue
            for outcome in market["outcomes"]:
                if float(outcome.get("point", 0)) != 2.5:
                    continue
                name  = outcome["name"]   # "Over" o "Under"
                precio = float(outcome["price"])
                if name in resultado:
                    if col not in resultado[name] or precio > resultado[name][col]:
                        resultado[name][col] = precio
    return resultado


# ─── Función principal ────────────────────────────────────────────────────────

def actualizar_datos() -> tuple[int, str, list[dict]]:
    """
    Descarga partidos de todas las ligas desde The Odds API.
    Sobreescribe matches.csv y odds.csv con los datos reales.
    Devuelve (n_partidos, mensaje, stats_por_liga).
    Lanza RuntimeError si la API falla por autenticación.
    """
    filas_partidos: list[dict] = []
    filas_cuotas:   list[dict] = []
    stats_ligas:    list[dict] = []   # {"liga", "partidos", "estado"}

    for nombre_liga, sport_key in LIGAS.items():
        try:
            partidos = _llamar_api(sport_key)
        except requests.HTTPError as exc:
            codigo = exc.response.status_code if exc.response else 0
            if codigo == 401:
                raise RuntimeError(
                    "Error de autenticación (401). Verifica la clave de API."
                ) from exc
            # Cualquier otro error HTTP (422, 404, 429, etc.) — omitir silenciosamente
            stats_ligas.append({"liga": nombre_liga, "partidos": 0, "estado": "Sin partidos hoy"})
            continue
        except Exception:
            # Error de red o cualquier otro — omitir silenciosamente
            stats_ligas.append({"liga": nombre_liga, "partidos": 0, "estado": "Sin partidos hoy"})
            continue

        # Filtrar solo partidos de hoy
        partidos = _filtrar_hoy(partidos)

        n_liga = len(partidos)
        if n_liga:
            stats_ligas.append({"liga": nombre_liga, "partidos": n_liga, "estado": "OK"})
            print(f"[OddsAPI] {nombre_liga:<22} → {n_liga} partido(s) hoy")
        else:
            stats_ligas.append({"liga": nombre_liga, "partidos": 0, "estado": "Sin partidos hoy"})
            print(f"[OddsAPI] {nombre_liga:<22} → Sin partidos hoy")

        hoy_str = _fecha_hoy()
        for p in partidos:
            local  = p["home_team"]
            visita = p["away_team"]
            nombre = f"{local} vs {visita}"
            bookmakers = p.get("bookmakers", [])

            h2h    = _extraer_h2h(bookmakers)
            totals = _extraer_totals_25(bookmakers)

            def precio_h2h(outcome: str, col: str) -> float:
                return h2h.get(outcome, {}).get(col, 0.0)

            def precio_total(side: str, col: str) -> float:
                return totals.get(side, {}).get(col, 0.0)

            # Cuotas 1X2
            for resultado_csv, outcome_key in [
                ("Local",     local),
                ("Empate",    "Draw"),
                ("Visitante", visita),
            ]:
                filas_cuotas.append({
                    "partido":   nombre,
                    "mercado":   "1X2",
                    "resultado": resultado_csv,
                    "codere":    precio_h2h(outcome_key, "codere"),
                    "bet365":    precio_h2h(outcome_key, "bet365"),
                    "betfair":   precio_h2h(outcome_key, "betfair"),
                })

            # Cuotas Over/Under 2.5
            for resultado_csv, side in [("Over 2.5", "Over"), ("Under 2.5", "Under")]:
                filas_cuotas.append({
                    "partido":   nombre,
                    "mercado":   "Over/Under 2.5",
                    "resultado": resultado_csv,
                    "codere":    precio_total(side, "codere"),
                    "bet365":    precio_total(side, "bet365"),
                    "betfair":   precio_total(side, "betfair"),
                })

            # xG estimado desde probabilidades implícitas normalizadas
            p_l = _prob_media(list(h2h.get(local,  {}).values()))
            p_v = _prob_media(list(h2h.get(visita, {}).values()))
            p_e = _prob_media(list(h2h.get("Draw", {}).values()))
            total_prob = (p_l + p_v + p_e) or 1.0

            filas_partidos.append({
                "liga":             nombre_liga,
                "partido":          nombre,
                "equipo_local":     local,
                "equipo_visitante": visita,
                "xg_local":         _xg_desde_prob(p_l / total_prob),
                "xg_visitante":     _xg_desde_prob(p_v / total_prob),
                "fuente_xg":        "estimado",
                "fecha":            hoy_str,
            })

    n = len(filas_partidos)
    print(f"[OddsAPI] Total: {n} partido(s) guardado(s)")

    if n == 0:
        return 0, "No hay partidos programados hoy en ninguna liga.", stats_ligas

    pd.DataFrame(filas_partidos).to_csv(RUTA_PARTIDOS, index=False)
    pd.DataFrame(filas_cuotas).to_csv(RUTA_CUOTAS,    index=False)

    return n, f"{n} partido(s) actualizado(s) con datos reales.", stats_ligas


# ─── Búsqueda de equipos ──────────────────────────────────────────────────────

LIGAS_BUSQUEDA = {
    "🏆 Champions League":  "soccer_uefa_champs_league",
    "🌍 Mundial 2026":      "soccer_fifa_world_cup",
    "🌍 Amistosos Int.":    "soccer_international_friendlies",
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League":   "soccer_epl",
    "🇪🇸 La Liga":           "soccer_spain_la_liga",
    "🇪🇸 Segunda División":  "soccer_spain_segunda_division",
    "🇩🇪 Bundesliga":        "soccer_germany_bundesliga",
    "🇮🇹 Serie A":           "soccer_italy_serie_a",
    "🇫🇷 Ligue 1":           "soccer_france_ligue_one",
}


@st.cache_data(ttl=300)
def _todos_partidos_hoy() -> list[dict]:
    """Descarga todos los partidos disponibles hoy en las ligas principales (caché 5 min)."""
    todos: list[dict] = []

    for nombre_liga, sport_key in LIGAS_BUSQUEDA.items():
        try:
            resp = requests.get(
                f"{BASE_URL}/sports/{sport_key}/odds/",
                params={
                    "apiKey":     API_KEY,
                    "regions":    "eu",
                    "markets":    "h2h",
                    "oddsFormat": "decimal",
                    "bookmakers": "bet365,betfair_ex_best_odds,codere",
                },
                timeout=10,
            )
            if resp.status_code != 200:
                continue

            for p in _filtrar_hoy(resp.json()):
                local  = p["home_team"]
                visita = p["away_team"]

                # Acumular precios por outcome de todos los bookmakers
                acum: dict[str, list[float]] = {}
                for bookie in p.get("bookmakers", []):
                    for market in bookie.get("markets", []):
                        if market["key"] != "h2h":
                            continue
                        for outcome in market["outcomes"]:
                            acum.setdefault(outcome["name"], []).append(float(outcome["price"]))

                def avg(lst: list[float]) -> float:
                    return round(sum(lst) / len(lst), 2) if lst else 0.0

                todos.append({
                    "label":            f"{local} vs {visita} ({nombre_liga})",
                    "equipo_local":     local,
                    "equipo_visitante": visita,
                    "liga":             nombre_liga,
                    "cuota_local":      avg(acum.get(local,  [])),
                    "cuota_empate":     avg(acum.get("Draw", [])),
                    "cuota_visitante":  avg(acum.get(visita, [])),
                })
        except Exception:
            continue

    return todos


def buscar_por_equipo(termino: str) -> list[dict]:
    """Filtra los partidos de hoy que contengan el término en algún equipo (máx. 20)."""
    t = termino.lower()
    coincidencias = [
        p for p in _todos_partidos_hoy()
        if t in p["equipo_local"].lower() or t in p["equipo_visitante"].lower()
    ]
    return coincidencias[:20]
