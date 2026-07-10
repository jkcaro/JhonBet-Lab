"""Módulo: Integración con Football-Data.org API v4 — partidos y forma reciente.

Independiente: no importa odds_api, espn_api, analysis, claude_analysis ni
ningún otro módulo del proyecto. Solo lee el token y expone funciones puras
de solo lectura (peticiones HTTP + cálculo de forma reciente).

Token — st.secrets["football_data"]["token"]:
  - Local: ya configurado en .streamlit/secrets.toml (sección [football_data]).
  - Streamlit Cloud: ese archivo NO se sube al repo (está en .gitignore) ni se
    comparte con el deployment — hay que replicar la misma sección
    [football_data]\ntoken = "..." en Settings → Secrets del proyecto en
    Streamlit Cloud, si no todas las funciones de este módulo caerán al
    fallback de "no configurado" (ver _token()/FootballDataError más abajo).

Plan gratuito de Football-Data.org: 10 llamadas/minuto. Todas las funciones
públicas usan st.cache_data(ttl=3600) — 1h de caché — para que, en uso normal
de la app, un mismo partido/equipo no dispare más de una llamada real por
hora, muy por debajo del límite.

Manejo de errores: ninguna función deja escapar una excepción "cruda" de
requests — todo error de red, 403 o límite excedido se traduce a
FootballDataError con un mensaje amigable en español. Quien llama a este
módulo debe capturar FootballDataError y hacer fallback a entrada manual;
la app nunca debe romperse por un fallo de esta API.
"""

import requests
import streamlit as st

BASE_URL = "https://api.football-data.org/v4"
TIMEOUT  = 10

# Competiciones soportadas → código Football-Data.org.
# Se empieza solo con el Mundial; añadir más entradas aquí cuando se necesiten
# (p.ej. "🏆 Champions League": "CL", "🇪🇸 La Liga": "PD").
COMPETICIONES: dict[str, str] = {
    "🌍 Mundial 2026": "WC",
}


class FootballDataError(Exception):
    """Error controlado de la API — el mensaje ya está listo para mostrar en la UI."""


def _token() -> str:
    try:
        return st.secrets["football_data"]["token"]
    except Exception:
        return ""


def _get(path: str, params: dict | None = None) -> dict:
    """GET autenticado a Football-Data.org. Traduce cualquier fallo a FootballDataError."""
    token = _token()
    if not token:
        raise FootballDataError(
            "Football-Data.org no está configurado (falta el token en secrets)."
        )

    try:
        resp = requests.get(
            f"{BASE_URL}{path}",
            headers={"X-Auth-Token": token},
            params=params,
            timeout=TIMEOUT,
        )
    except requests.exceptions.RequestException as exc:
        raise FootballDataError(
            "Sin conexión con Football-Data.org. Usa la entrada manual."
        ) from exc

    if resp.status_code == 403:
        raise FootballDataError(
            "Football-Data.org rechazó la petición (403) — token inválido o "
            "sin acceso a esta competición en el plan actual."
        )
    if resp.status_code == 429:
        raise FootballDataError(
            "Límite de peticiones de Football-Data.org alcanzado "
            "(plan gratuito: 10/min). Espera un minuto e inténtalo de nuevo."
        )
    if resp.status_code != 200:
        raise FootballDataError(
            f"Football-Data.org respondió con un error ({resp.status_code}). "
            "Usa la entrada manual."
        )

    try:
        return resp.json()
    except ValueError as exc:
        raise FootballDataError("Respuesta inválida de Football-Data.org.") from exc


@st.cache_data(ttl=3600)
def partidos_por_competicion(codigo: str, status: str = "SCHEDULED") -> list[dict]:
    """
    Partidos próximos/programados de una competición (por defecto status=SCHEDULED,
    que Football-Data.org resuelve como "aún no jugados").

    Devuelve una lista de dicts simplificados:
      {id, fecha (ISO-8601 UTC), fase, local, local_id, visitante, visitante_id}

    Los cruces de fases futuras sin equipos decididos (homeTeam/awayTeam nulos,
    p.ej. semifinales antes de que se jueguen los cuartos) se omiten.

    Lanza FootballDataError si la API falla — quien llama debe capturarla.
    Cacheado 1h (st.cache_data no cachea excepciones: un fallo no bloquea
    reintentos posteriores).
    """
    data = _get(f"/competitions/{codigo}/matches", params={"status": status})

    partidos = []
    for m in data.get("matches", []):
        home = m.get("homeTeam") or {}
        away = m.get("awayTeam") or {}
        if not home.get("name") or not away.get("name"):
            continue
        partidos.append({
            "id":           m.get("id"),
            "fecha":        m.get("utcDate", ""),
            "fase":         m.get("stage", ""),
            "local":        home.get("name"),
            "local_id":     home.get("id"),
            "visitante":    away.get("name"),
            "visitante_id": away.get("id"),
        })
    return partidos


@st.cache_data(ttl=3600)
def forma_reciente_equipo(team_id: int, n: int = 5) -> str:
    """
    Últimos n resultados finalizados de un equipo, desde SU perspectiva
    (gane como local o visitante, "W" es victoria de ese equipo, no del local
    del partido). Devuelve una cadena "W,D,L,W,W" en orden cronológico
    (el más antiguo primero, el más reciente al final) — mismo formato que
    esperan los campos "Forma reciente" de modules/claude_analysis.py.

    Partidos sin resultado registrado (score.winner ausente) se omiten.
    Lanza FootballDataError si la API falla.
    """
    data = _get(f"/teams/{team_id}/matches", params={"status": "FINISHED", "limit": n})
    partidos = data.get("matches", [])
    partidos = sorted(partidos, key=lambda m: m.get("utcDate", ""))[-n:]

    resultados = []
    for m in partidos:
        ganador = (m.get("score") or {}).get("winner")
        if ganador is None:
            continue
        es_local = (m.get("homeTeam") or {}).get("id") == team_id
        if ganador == "DRAW":
            resultados.append("D")
        elif (ganador == "HOME_TEAM") == es_local:
            resultados.append("W")
        else:
            resultados.append("L")
    return ",".join(resultados)
