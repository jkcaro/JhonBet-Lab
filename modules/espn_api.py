"""
Módulo: ESPN API — partidos de hoy sin necesidad de API key.
Obtiene partidos programados de múltiples ligas y los añade a matches.csv.
"""

import requests
import streamlit as st
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ESPN_BASE    = "https://site.api.espn.com/apis/site/v2/sports/soccer"
TIMEOUT      = 8
RUTA_PARTIDOS = Path(__file__).parent.parent / "data" / "matches.csv"

# Slugs de liga ESPN → nombre para mostrar en la app
LIGAS_ESPN: dict[str, str] = {
    "fifa.world":       "🌍 Mundial 2026",
    "uefa.champions":   "🏆 Champions League",
    "eng.1":            "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League",
    "esp.1":            "🇪🇸 La Liga",
    "esp.2":            "🇪🇸 Segunda División",
    "ger.1":            "🇩🇪 Bundesliga",
    "ita.1":            "🇮🇹 Serie A",
    "fra.1":            "🇫🇷 Ligue 1",
}

# xG por defecto cuando no hay datos históricos disponibles
XG_LOCAL_DEFAULT    = 1.4
XG_VISITANTE_DEFAULT = 1.1


@st.cache_data(ttl=300)   # caché 5 min para no saturar ESPN
def _fetch_liga(slug: str, fecha: str) -> list[dict]:
    """Descarga los eventos de una liga ESPN para la fecha indicada."""
    try:
        resp = requests.get(
            f"{ESPN_BASE}/{slug}/scoreboard",
            params={"dates": fecha, "limit": 100},
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.json().get("events", [])
    except Exception:
        pass
    return []


def obtener_partidos_hoy() -> list[dict]:
    """
    Recorre todas las ligas ESPN y devuelve la lista de partidos de hoy.
    Cada partido incluye:
      liga, partido, equipo_local, equipo_visitante, xg_local, xg_visitante, fuente
    """
    hoy = datetime.now(timezone.utc).strftime("%Y%m%d")
    resultados: list[dict] = []

    for slug, nombre_liga in LIGAS_ESPN.items():
        for evento in _fetch_liga(slug, hoy):
            try:
                comp         = evento["competitions"][0]
                competidores = comp["competitors"]
                local  = next(c for c in competidores if c["homeAway"] == "home")
                visita = next(c for c in competidores if c["homeAway"] == "away")

                nombre_local  = local["team"]["displayName"]
                nombre_visita = visita["team"]["displayName"]

                resultados.append({
                    "liga":             nombre_liga,
                    "partido":          f"{nombre_local} vs {nombre_visita}",
                    "equipo_local":     nombre_local,
                    "equipo_visitante": nombre_visita,
                    "xg_local":         XG_LOCAL_DEFAULT,
                    "xg_visitante":     XG_VISITANTE_DEFAULT,
                    "fuente":           "ESPN",
                })
            except (KeyError, StopIteration, IndexError):
                continue

    return resultados


def actualizar_con_espn() -> tuple[int, str]:
    """
    Descarga partidos de hoy desde ESPN y los añade a matches.csv
    sin eliminar los ya cargados desde The Odds API.
    Devuelve (n_nuevos, mensaje).
    """
    nuevos = obtener_partidos_hoy()
    if not nuevos:
        return 0, "ESPN: no hay partidos disponibles hoy."

    try:
        df_actual = pd.read_csv(RUTA_PARTIDOS)
    except Exception:
        df_actual = pd.DataFrame(columns=["liga","partido","equipo_local","equipo_visitante","xg_local","xg_visitante"])

    # Eliminar fuente ESPN anterior para no duplicar
    if "fuente" in df_actual.columns:
        df_actual = df_actual[df_actual["fuente"] != "ESPN"]
    else:
        df_actual["fuente"] = "OddsAPI"

    df_nuevos = pd.DataFrame(nuevos)
    # Evitar duplicar partidos que ya existen por nombre
    partidos_existentes = set(df_actual["partido"].tolist())
    df_nuevos = df_nuevos[~df_nuevos["partido"].isin(partidos_existentes)]

    if df_nuevos.empty:
        return 0, "ESPN: todos los partidos ya estaban cargados."

    df_final = pd.concat([df_actual, df_nuevos], ignore_index=True)
    df_final.to_csv(RUTA_PARTIDOS, index=False)

    n = len(df_nuevos)
    return n, f"ESPN: {n} partido(s) nuevos añadidos de {len(LIGAS_ESPN)} ligas."
