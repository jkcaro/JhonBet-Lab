"""
Módulo: Estadísticas reales de equipos.

Fuentes de datos (en orden de preferencia):
  1. SofaScore (RapidAPI)       — últimos partidos, lesiones
  2. Football-Data.org          — clasificación, últimos 5, próximos fixtures
  3. Free Football API (RapidAPI) — fuente de respaldo general

Los resultados se combinan y se pasan a Claude AI.
"""

import os
import time
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ─── Clave compartida RapidAPI ────────────────────────────────────────────────
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
TIMEOUT      = 3

# ─── Fuente 2 (nueva): Football-Data.org ──────────────────────────────────────
FD_TOKEN   = os.getenv("FD_TOKEN", "")
FD_BASE    = "https://api.football-data.org/v4"
FD_HEADERS = {"X-Auth-Token": FD_TOKEN}

# Ligas soportadas por Football-Data.org y sus códigos internos
FD_LIGAS: dict[str, str] = {
    "PL": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League",
    "PD": "🇪🇸 La Liga",
    "CL": "🏆 Champions League",
    "SD": "🇪🇸 Segunda División",
}

# ─── Fuente 1: SofaScore ──────────────────────────────────────────────────────
SOFA_HOST = "sofascore.p.rapidapi.com"
SOFA_URL  = f"https://{SOFA_HOST}"
SOFA_HDR  = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": SOFA_HOST}

# ─── Fuente 2: Free Football API (respaldo) ───────────────────────────────────
FREE_HOST = "free-api-live-football-data.p.rapidapi.com"
FREE_URL  = f"https://{FREE_HOST}"
FREE_HDR  = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": FREE_HOST}


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS COMUNES
# ══════════════════════════════════════════════════════════════════════════════

def _get(url_base: str, headers: dict, endpoint: str, params: dict = None) -> object:
    """Llamada GET genérica. Devuelve None si falla."""
    try:
        r = requests.get(
            f"{url_base}{endpoint}",
            headers=headers,
            params=params or {},
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return r.json()
        print(f"[FootballStats] {endpoint} → HTTP {r.status_code}")
    except Exception as exc:
        print(f"[FootballStats] Error {endpoint}: {exc}")
    return None


def _extraer_lista(data: object, *claves: str) -> list:
    """Busca una lista dentro de un dict probando varias claves."""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for k in claves:
        v = data.get(k)
        if isinstance(v, list) and v:
            return v
        if isinstance(v, dict):
            for k2 in claves:
                v2 = v.get(k2)
                if isinstance(v2, list) and v2:
                    return v2
    return []


def _resumen_forma(resultados: list, condicion: list) -> dict:
    """Genera el dict de estadísticas de forma a partir de listas G/E/P y L/V."""
    loc = [r for r, c in zip(resultados, condicion) if c == "L"]
    vis = [r for r, c in zip(resultados, condicion) if c == "V"]

    def res(lst):
        if not lst:
            return "Sin datos"
        return f"{lst.count('G')}V {lst.count('E')}E {lst.count('P')}D de {len(lst)}"

    n = len(resultados) or 1
    return {
        "forma":                 " - ".join(resultados) if resultados else "Sin datos",
        "victorias":             resultados.count("G"),
        "empates":               resultados.count("E"),
        "derrotas":              resultados.count("P"),
        "rendimiento_local":     res(loc),
        "rendimiento_visitante": res(vis),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  FUENTE 1 — SOFASCORE
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def _sofa_buscar_id(nombre: str) -> int | None:
    """Busca el ID de equipo en SofaScore por nombre. Caché 1 hora."""
    data = _get(SOFA_URL, SOFA_HDR, "/teams/search", {"name": nombre})
    if not data:
        return None
    equipos = _extraer_lista(data, "teams", "results", "data")
    for e in equipos:
        if isinstance(e, dict):
            eid = e.get("id") or e.get("team_id")
            if eid:
                return int(eid)
    return None


@st.cache_data(ttl=1800)
def _sofa_partidos_recientes(team_id: int, n: int = 5) -> list[dict]:
    """Devuelve los últimos n partidos de SofaScore. Caché 30 min."""
    # SofaScore pagina los eventos; page 0 = más recientes
    data = _get(SOFA_URL, SOFA_HDR, f"/teams/{team_id}/events/last/0")
    if not data:
        return []
    eventos = _extraer_lista(data, "events", "data", "results")
    # Filtrar solo partidos finalizados
    finalizados = [
        e for e in eventos
        if isinstance(e, dict)
        and str(e.get("status", {}).get("type", "finished")).lower()
        in {"finished", "ft", "ended", "after extra time", "after penalties"}
    ]
    return (finalizados or eventos)[:n]


@st.cache_data(ttl=900)   # lesiones: caché 15 min (cambian con más frecuencia)
def _sofa_lesiones(team_id: int) -> list[dict]:
    """Obtiene lesiones actuales del equipo desde SofaScore."""
    data = _get(SOFA_URL, SOFA_HDR, f"/teams/{team_id}/injuries")
    if not data:
        return []
    return _extraer_lista(data, "injuries", "data", "results")


def _sofa_calcular_forma(eventos: list[dict], nombre: str) -> dict:
    """Calcula estadísticas de forma a partir de eventos de SofaScore."""
    resultados, goles_fav, goles_con, condicion = [], [], [], []

    for e in eventos:
        home = e.get("homeTeam", {})
        away = e.get("awayTeam", {})
        h_name = home.get("name", "") or home.get("shortName", "")
        a_name = away.get("name", "") or away.get("shortName", "")

        h_goles = int((e.get("homeScore") or {}).get("current", 0) or 0)
        a_goles = int((e.get("awayScore") or {}).get("current", 0) or 0)

        es_local = nombre.lower() in h_name.lower() if h_name else True
        condicion.append("L" if es_local else "V")

        mios, rival = (h_goles, a_goles) if es_local else (a_goles, h_goles)
        goles_fav.append(mios)
        goles_con.append(rival)

        resultados.append("G" if mios > rival else ("E" if mios == rival else "P"))

    n = len(resultados) or 1
    stats = _resumen_forma(resultados, condicion)
    stats.update({
        "goles_a_favor_media":   round(sum(goles_fav) / n, 1),
        "goles_en_contra_media": round(sum(goles_con) / n, 1),
    })
    return stats


def _sofa_formatear_lesiones(lesiones: list[dict]) -> list[str]:
    """Convierte la lista de lesiones en textos legibles en español."""
    resultado = []
    for l in lesiones[:5]:   # máximo 5 para no saturar el prompt de Claude
        jugador  = (l.get("player") or {}).get("name", "Desconocido")
        tipo     = l.get("injury") or l.get("injuryType") or "Lesión"
        retorno  = l.get("returnDate") or l.get("expectedReturn") or "Sin fecha"
        resultado.append(f"{jugador} — {tipo} (vuelta estimada: {retorno})")
    return resultado


def _obtener_stats_sofa(nombre: str) -> dict | None:
    """
    Intenta obtener las estadísticas completas desde SofaScore.
    Devuelve None si no encuentra el equipo o no hay datos.
    """
    team_id = _sofa_buscar_id(nombre)
    if not team_id:
        return None

    print(f"[SofaScore] '{nombre}' → team_id={team_id}")

    eventos = _sofa_partidos_recientes(team_id)
    if not eventos:
        return None

    print(f"[SofaScore] '{nombre}' → {len(eventos)} partido(s) reciente(s)")

    forma     = _sofa_calcular_forma(eventos, nombre)
    lesiones  = _sofa_lesiones(team_id)
    les_texto = _sofa_formatear_lesiones(lesiones)

    stats = {
        "nombre":  nombre,
        "team_id": team_id,
        "fuente":  "SofaScore",
        **forma,
    }
    if les_texto:
        stats["lesiones_actuales"] = les_texto
    else:
        stats["lesiones_actuales"] = ["Sin lesiones reportadas"]

    return stats


# ══════════════════════════════════════════════════════════════════════════════
#  FUENTE 2 — FREE FOOTBALL API (respaldo)
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def _free_buscar_id(nombre: str) -> int | None:
    data = _get(FREE_URL, FREE_HDR, "/football-get-all-search-data", {"q": nombre})
    if not data:
        return None
    equipos = _extraer_lista(data, "teams", "team", "response", "data", "results", "items")
    for item in equipos:
        if not isinstance(item, dict):
            continue
        team = item.get("team") if "team" in item else item
        if not isinstance(team, dict):
            continue
        tid = team.get("team_id") or team.get("teamId") or team.get("id")
        if tid:
            return int(tid)
    return None


@st.cache_data(ttl=1800)
def _free_partidos_recientes(team_id: int, n: int = 5) -> list[dict]:
    data = _get(FREE_URL, FREE_HDR, "/football-get-all-team-matches",
                {"teamid": team_id, "pagenumber": 1})
    if not data:
        return []
    partidos = _extraer_lista(data, "matches", "fixtures", "response", "data", "results", "items")
    estados = {"finished", "ft", "full-time", "played", "completed", "aet", "pen", "1", "2", "3"}
    finalizados = [
        p for p in partidos
        if isinstance(p, dict)
        and str(p.get("status", p.get("matchStatus", "finished"))).lower()
        in estados | {""}
    ]
    return (finalizados or partidos)[:n]


def _free_calcular_forma(partidos: list[dict], nombre: str) -> dict:
    resultados, goles_fav, goles_con, condicion = [], [], [], []

    for p in partidos:
        home_raw = p.get("homeTeam") or p.get("home_team") or p.get("home") or {}
        away_raw = p.get("awayTeam") or p.get("away_team") or p.get("away") or {}

        def _nom(obj):
            if isinstance(obj, str): return obj
            if isinstance(obj, dict):
                return obj.get("name") or obj.get("teamName") or obj.get("shortName") or ""
            return ""

        h_name = _nom(home_raw)
        a_name = _nom(away_raw)

        score = p.get("score") or p.get("result") or p.get("goals") or p.get("fullTime") or {}
        if isinstance(score, str):
            partes = score.replace(" ", "").split("-")
            try: h_g, a_g = int(partes[0]), int(partes[1])
            except: h_g = a_g = 0
        elif isinstance(score, dict):
            h_g = int(score.get("home", score.get("homeScore", score.get("homeGoals", 0))) or 0)
            a_g = int(score.get("away", score.get("awayScore", score.get("awayGoals", 0))) or 0)
        else:
            h_g = a_g = 0

        es_local = nombre.lower() in h_name.lower() if h_name else True
        condicion.append("L" if es_local else "V")
        mios, rival = (h_g, a_g) if es_local else (a_g, h_g)
        goles_fav.append(mios)
        goles_con.append(rival)
        resultados.append("G" if mios > rival else ("E" if mios == rival else "P"))

    n = len(resultados) or 1
    stats = _resumen_forma(resultados, condicion)
    stats.update({
        "goles_a_favor_media":   round(sum(goles_fav) / n, 1),
        "goles_en_contra_media": round(sum(goles_con) / n, 1),
    })
    return stats


def _obtener_stats_free(nombre: str) -> dict | None:
    team_id = _free_buscar_id(nombre)
    if not team_id:
        return None
    print(f"[FreeAPI] '{nombre}' → team_id={team_id}")
    partidos = _free_partidos_recientes(team_id)
    if not partidos:
        return None
    print(f"[FreeAPI] '{nombre}' → {len(partidos)} partido(s)")
    forma = _free_calcular_forma(partidos, nombre)
    return {
        "nombre":  nombre,
        "team_id": team_id,
        "fuente":  "FreeFootballAPI",
        "lesiones_actuales": ["Datos de lesiones no disponibles en esta fuente"],
        **forma,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  FUENTE 2 — FOOTBALL-DATA.ORG
#  Plan gratuito: 10 peticiones/minuto → usamos time.sleep(6) entre llamadas.
#  Datos: clasificación, últimos 5 partidos, próximos fixtures.
# ══════════════════════════════════════════════════════════════════════════════

def _fd_get(endpoint: str, params: dict = None) -> object:
    """
    Llamada GET a Football-Data.org.
    Maneja rate limit (429) durmiendo 12 s y reintentando una vez.
    """
    try:
        r = requests.get(
            f"{FD_BASE}{endpoint}",
            headers=FD_HEADERS,
            params=params or {},
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429:          # rate limit superado
            print("[FD] Rate limit → esperando 12 s y reintentando...")
            time.sleep(12)
            r = requests.get(f"{FD_BASE}{endpoint}", headers=FD_HEADERS,
                             params=params or {}, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.json()
        print(f"[FD] {endpoint} → HTTP {r.status_code}")
    except Exception as exc:
        print(f"[FD] Error {endpoint}: {exc}")
    return None


# Diccionario de traducción: nombre en español → nombre en inglés
# (Football-Data.org usa nombres en inglés)
_TRADUCCIONES: dict[str, str] = {
    # Selecciones nacionales
    "alemania":       "Germany",
    "francia":        "France",
    "españa":         "Spain",
    "italia":         "Italy",
    "portugal":       "Portugal",
    "holanda":        "Netherlands",
    "países bajos":   "Netherlands",
    "bélgica":        "Belgium",
    "suiza":          "Switzerland",
    "austria":        "Austria",
    "polonia":        "Poland",
    "ucrania":        "Ukraine",
    "rusia":          "Russia",
    "dinamarca":      "Denmark",
    "suecia":         "Sweden",
    "noruega":        "Norway",
    "finlandia":      "Finland",
    "escocia":        "Scotland",
    "gales":          "Wales",
    "irlanda":        "Ireland",
    "hungría":        "Hungary",
    "república checa": "Czech Republic",
    "chequia":        "Czech Republic",
    "eslovaquia":     "Slovakia",
    "rumanía":        "Romania",
    "serbia":         "Serbia",
    "croacia":        "Croatia",
    "eslovenia":      "Slovenia",
    "turquía":        "Turkey",
    "grecia":         "Greece",
    "albania":        "Albania",
    "georgia":        "Georgia",
    "marruecos":      "Morocco",
    "senegal":        "Senegal",
    "argelia":        "Algeria",
    "egipto":         "Egypt",
    "ghana":          "Ghana",
    "camerún":        "Cameroon",
    "nigeria":        "Nigeria",
    "costa de marfil": "Ivory Coast",
    "sudáfrica":      "South Africa",
    "arabia saudí":   "Saudi Arabia",
    "japón":          "Japan",
    "corea del sur":  "South Korea",
    "australia":      "Australia",
    "nueva zelanda":  "New Zealand",
    "estados unidos": "USA",
    "eeuu":           "USA",
    "méxico":         "Mexico",
    "argentina":      "Argentina",
    "brasil":         "Brazil",
    "colombia":       "Colombia",
    "uruguay":        "Uruguay",
    "chile":          "Chile",
    "perú":           "Peru",
    "venezuela":      "Venezuela",
    "ecuador":        "Ecuador",
    "paraguay":       "Paraguay",
    "bolivia":        "Bolivia",
    # Clubes con nombre diferente en español
    "athletic":       "Athletic Club",
    "atlético":       "Atlético",
}


def _traducir(nombre: str) -> str:
    """Devuelve el nombre en inglés si existe traducción; si no, devuelve el original."""
    return _TRADUCCIONES.get(nombre.lower(), nombre)


def _nombres_a_probar(nombre: str) -> list[str]:
    """
    Genera la lista de variantes a buscar para un equipo:
    primero el nombre traducido (exacto), luego el original.
    """
    traducido = _traducir(nombre)
    variantes = [traducido]
    if traducido.lower() != nombre.lower():
        variantes.append(nombre)
    return variantes


def _coincide(nombre_buscado: str, nombre_api: str, short_api: str = "") -> bool:
    """
    Comprueba si un nombre de equipo coincide con los datos de la API.
    Primero búsqueda exacta, luego parcial.
    """
    nb = nombre_buscado.lower().strip()
    na = nombre_api.lower().strip()
    ns = short_api.lower().strip()
    # Exacta
    if nb == na or nb == ns:
        return True
    # Parcial: el nombre buscado contiene al de la API o viceversa
    if nb in na or na in nb:
        return True
    if ns and (nb in ns or ns in nb):
        return True
    return False


@st.cache_data(ttl=3600)
def _fd_buscar_equipo(nombre: str) -> tuple[int | None, str | None]:
    """
    Busca un equipo en Football-Data.org.
    Devuelve (team_id, codigo_liga) o (None, None) si no se encuentra.

    Estrategia:
      1. Traduce el nombre del español al inglés si existe traducción.
      2. Busca con /teams?search= (coincidencia exacta primero, parcial después).
      3. Si falla, recorre cada liga conocida buscando por nombre.
    """
    variantes = _nombres_a_probar(nombre)

    for variante in variantes:
        data = _fd_get("/teams", {"search": variante})
        if not data:
            time.sleep(6)
            continue

        equipos = data.get("teams", [])

        # Paso 1: coincidencia exacta
        for e in equipos:
            if not isinstance(e, dict):
                continue
            if _coincide(variante, e.get("name", ""), e.get("shortName", "")):
                liga_code = None
                for comp in e.get("runningCompetitions", []):
                    if comp.get("code") in FD_LIGAS:
                        liga_code = comp["code"]
                        break
                return e["id"], liga_code

        # Paso 2: primera coincidencia parcial de la lista
        if equipos and isinstance(equipos[0], dict):
            e = equipos[0]
            liga_code = None
            for comp in e.get("runningCompetitions", []):
                if comp.get("code") in FD_LIGAS:
                    liga_code = comp["code"]
                    break
            return e["id"], liga_code

        time.sleep(6)

    # Paso 3: recorrer el roster de cada liga conocida
    for codigo in FD_LIGAS:
        data = _fd_get(f"/competitions/{codigo}/teams")
        if data:
            for e in (data.get("teams") or []):
                for variante in variantes:
                    if _coincide(variante, e.get("name", ""), e.get("shortName", "")):
                        return e["id"], codigo
        time.sleep(6)

    return None, None


@st.cache_data(ttl=1800)
def _fd_ultimos_partidos(team_id: int, n: int = 5) -> list[dict]:
    """Últimos n partidos finalizados del equipo desde Football-Data.org."""
    data = _fd_get(f"/teams/{team_id}/matches",
                   {"status": "FINISHED", "limit": n})
    if not data:
        return []
    # La API devuelve los más recientes al final → invertimos
    partidos = data.get("matches", [])
    return list(reversed(partidos))[:n]


@st.cache_data(ttl=3600)
def _fd_proximos_partidos(team_id: int, n: int = 3) -> list[str]:
    """Próximos n partidos programados del equipo."""
    data = _fd_get(f"/teams/{team_id}/matches",
                   {"status": "SCHEDULED", "limit": n})
    if not data:
        return []
    resultado = []
    for m in data.get("matches", [])[:n]:
        home  = m.get("homeTeam", {}).get("name", "?")
        away  = m.get("awayTeam", {}).get("name", "?")
        fecha = m.get("utcDate", "")[:10]
        comp  = m.get("competition", {}).get("name", "")
        resultado.append(f"{home} vs {away}  ({comp}, {fecha})")
    return resultado


@st.cache_data(ttl=3600)
def _fd_clasificacion(liga_code: str, team_id: int) -> dict:
    """Posición del equipo en la tabla de su liga."""
    if not liga_code:
        return {}
    data = _fd_get(f"/competitions/{liga_code}/standings")
    if not data:
        return {}
    for tabla in data.get("standings", []):
        if tabla.get("type") == "TOTAL":
            for fila in tabla.get("table", []):
                if fila.get("team", {}).get("id") == team_id:
                    return {
                        "posicion":      fila.get("position"),
                        "puntos":        fila.get("points"),
                        "partidos":      fila.get("playedGames"),
                        "ganados":       fila.get("won"),
                        "empatados":     fila.get("draw"),
                        "perdidos":      fila.get("lost"),
                        "goles_favor":   fila.get("goalsFor"),
                        "goles_contra":  fila.get("goalsAgainst"),
                        "diferencia":    fila.get("goalDifference"),
                        "forma_liga":    fila.get("form", ""),
                    }
    return {}


def _fd_calcular_forma(partidos: list[dict], team_id: int) -> dict:
    """Calcula estadísticas de forma a partir de partidos de Football-Data.org."""
    resultados, goles_fav, goles_con, condicion = [], [], [], []

    for m in partidos:
        home_id  = m.get("homeTeam", {}).get("id")
        es_local = home_id == team_id
        condicion.append("L" if es_local else "V")

        ft = m.get("score", {}).get("fullTime", {})
        h_g = int(ft.get("home") or 0)
        a_g = int(ft.get("away") or 0)

        mios, rival = (h_g, a_g) if es_local else (a_g, h_g)
        goles_fav.append(mios)
        goles_con.append(rival)
        resultados.append("G" if mios > rival else ("E" if mios == rival else "P"))

    n      = len(resultados) or 1
    stats  = _resumen_forma(resultados, condicion)
    stats.update({
        "goles_a_favor_media":   round(sum(goles_fav) / n, 1),
        "goles_en_contra_media": round(sum(goles_con) / n, 1),
    })
    return stats


def _obtener_stats_fd(nombre: str) -> dict | None:
    """
    Obtiene datos completos de Football-Data.org para un equipo:
    clasificación actual, últimos 5 partidos y próximos 3 fixtures.
    Devuelve None si el equipo no se encuentra.
    """
    team_id, liga_code = _fd_buscar_equipo(nombre)
    if not team_id:
        return None

    print(f"[FD] '{nombre}' → team_id={team_id}, liga={liga_code}")

    time.sleep(6)   # pausa antes de la siguiente llamada
    partidos = _fd_ultimos_partidos(team_id)

    time.sleep(6)
    proximos = _fd_proximos_partidos(team_id)

    time.sleep(6)
    clasificacion = _fd_clasificacion(liga_code, team_id) if liga_code else {}

    stats: dict = {
        "nombre":  nombre,
        "team_id": team_id,
        "fuente":  "Football-Data.org",
    }

    if partidos:
        stats.update(_fd_calcular_forma(partidos, team_id))

    if clasificacion:
        stats["clasificacion"] = clasificacion

    if proximos:
        stats["proximos_partidos"] = proximos
    else:
        stats["proximos_partidos"] = ["Sin fixtures próximos disponibles"]

    if not partidos and not clasificacion:
        return None    # datos insuficientes, no vale la pena devolver

    return stats


# ══════════════════════════════════════════════════════════════════════════════
#  FUNCIÓN PRINCIPAL — intenta SofaScore, cae a Free API si falla
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
#  FUENTE ESPN — SEGUNDA DIVISIÓN (esp.2)
#  Football-Data.org no incluye la SD en el plan gratuito.
#  ESPN API es gratuita y no requiere clave.
#  Endpoint: https://site.api.espn.com/apis/site/v2/sports/soccer/esp.2/teams/{slug}/schedule
# ══════════════════════════════════════════════════════════════════════════════

ESPN_BASE_SD = "https://site.api.espn.com/apis/site/v2/sports/soccer/esp.2/teams"

# IDs numéricos reales obtenidos de ESPN API (/esp.2/teams)
# Formato: nombre en español (minúsculas) → ID numérico ESPN
_ESPN_SD_IDS: dict[str, int] = {
    # Zaragoza
    "zaragoza":                       91,
    "real zaragoza":                  91,
    # Málaga
    "málaga":                         99,
    "malaga":                         99,
    "málaga cf":                      99,
    # Córdoba
    "córdoba":                        8447,
    "cordoba":                        8447,
    "córdoba cf":                     8447,
    # Huesca
    "huesca":                         5413,
    "sd huesca":                      5413,
    # Burgos
    "burgos":                         12597,
    "burgos cf":                      12597,
    # Eibar
    "eibar":                          3752,
    "sd eibar":                       3752,
    # Almería
    "almería":                        6832,
    "almeria":                        6832,
    "ud almería":                     6832,
    # Valladolid
    "valladolid":                     95,
    "real valladolid":                95,
    "real valladolid cf":             95,
    # Castellón
    "castellón":                      4438,
    "castellon":                      4438,
    "cd castellón":                   4438,
    # Cádiz
    "cádiz":                          3842,
    "cadiz":                          3842,
    "cádiz cf":                       3842,
    # Racing Santander
    "racing":                         87,
    "racing santander":               87,
    "real racing club de santander":  87,
    "racing de santander":            87,
    # Andorra
    "andorra":                        20179,
    "fc andorra":                     20179,
    # Leganés
    "leganés":                        17534,
    "leganes":                        17534,
    "cd leganés":                     17534,
    # Mirandés
    "mirandés":                       4515,
    "mirandes":                       4515,
    "cd mirandés":                    4515,
    # Deportivo La Coruña
    "deportivo":                      90,
    "deportivo la coruña":            90,
    "deportivo la coruna":            90,
    # Las Palmas
    "las palmas":                     98,
    "ud las palmas":                  98,
    # Resto de equipos actuales en SD
    "albacete":                       2737,
    "ceuta":                          5404,
    "cultural leonesa":               10629,
    "granada":                        3747,
    "real sociedad ii":               20983,
    "real sociedad b":                20983,
    "sporting gijón":                 3788,
    "sporting gijon":                 3788,
}


def _espn_id_sd(nombre: str) -> int | None:
    """Devuelve el ID numérico ESPN para un equipo de Segunda División, o None si no está mapeado."""
    return _ESPN_SD_IDS.get(nombre.lower().strip())


@st.cache_data(ttl=1800)
def _espn_sd_schedule(team_id: int) -> list[dict]:
    """Descarga el calendario del equipo desde ESPN Segunda División usando su ID numérico. Caché 30 min."""
    try:
        r = requests.get(
            f"{ESPN_BASE_SD}/{team_id}/schedule",
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return r.json().get("events", [])
        print(f"[ESPN-SD] ID={team_id} → HTTP {r.status_code}")
    except Exception as exc:
        print(f"[ESPN-SD] Error ID={team_id}: {exc}")
    return []


def _espn_sd_calcular_forma(eventos: list[dict], nombre: str) -> dict:
    """
    Calcula estadísticas de forma a partir de eventos ESPN.
    Solo procesa los últimos 5 partidos ya finalizados.
    """
    resultados, goles_fav, goles_con, condicion = [], [], [], []

    for evento in eventos:
        try:
            comp        = evento["competitions"][0]
            completado  = comp.get("status", {}).get("type", {}).get("completed", False)
            if not completado:
                continue

            competidores = comp["competitors"]
            local  = next(c for c in competidores if c["homeAway"] == "home")
            visita = next(c for c in competidores if c["homeAway"] == "away")

            nombre_local  = local["team"]["displayName"]
            nombre_visita = visita["team"]["displayName"]

            goles_l = int(local.get("score",  "0") or 0)
            goles_v = int(visita.get("score", "0") or 0)

            es_local = nombre.lower() in nombre_local.lower()
            condicion.append("L" if es_local else "V")

            mios, rival = (goles_l, goles_v) if es_local else (goles_v, goles_l)
            goles_fav.append(mios)
            goles_con.append(rival)
            resultados.append("G" if mios > rival else ("E" if mios == rival else "P"))

            if len(resultados) >= 5:
                break
        except (KeyError, StopIteration, ValueError, TypeError):
            continue

    n     = len(resultados) or 1
    stats = _resumen_forma(resultados, condicion)
    stats.update({
        "goles_a_favor_media":   round(sum(goles_fav) / n, 1),
        "goles_en_contra_media": round(sum(goles_con) / n, 1),
    })
    return stats


def _obtener_stats_espn_sd(nombre: str) -> dict | None:
    """
    Obtiene estadísticas de forma de un equipo de Segunda División vía ESPN.
    Usa IDs numéricos reales obtenidos de la API de ESPN.
    Devuelve None si el equipo no está en el mapeo o la API no responde.
    """
    team_id = _espn_id_sd(nombre)
    if not team_id:
        return None

    print(f"[ESPN-SD] '{nombre}' → team_id={team_id}")
    eventos = _espn_sd_schedule(team_id)

    # Filtrar solo finalizados y tomar los últimos 5 (vienen en orden cronológico)
    finalizados = [
        e for e in eventos
        if e.get("competitions", [{}])[0]
           .get("status", {}).get("type", {}).get("completed", False)
    ]
    ultimos = list(reversed(finalizados))[:5]

    if not ultimos:
        return None

    print(f"[ESPN-SD] '{nombre}' → {len(ultimos)} partido(s) finalizados")
    forma = _espn_sd_calcular_forma(ultimos, nombre)

    return {
        "nombre": nombre,
        "fuente": "ESPN Segunda División",
        **forma,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  FUNCIÓN PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def obtener_stats_partido(partido: str) -> dict:
    """
    Devuelve estadísticas de ambos equipos.

    Cadena de fuentes:
      1. Football-Data.org — PL, La Liga, CL, Bundesliga, Serie A, Ligue 1
      2. ESPN Segunda División — equipos de esp.2 no disponibles en FD gratuito
      3. Sin datos — si ninguna fuente responde

    SofaScore y Free Football API desactivadas (error 403 — sin suscripción activa).
    """
    if " vs " not in partido:
        return {}

    local_nombre, visita_nombre = [p.strip() for p in partido.split(" vs ", 1)]
    resultado: dict = {}

    for nombre, clave in [
        (local_nombre,  "equipo_local"),
        (visita_nombre, "equipo_visitante"),
    ]:
        # ── 1. Football-Data.org (ligas principales) ──────────────────────
        stats = _obtener_stats_fd(nombre)

        # ── 2. ESPN Segunda División (si FD no lo encontró) ───────────────
        if stats is None:
            stats = _obtener_stats_espn_sd(nombre)

        # ── Sin datos disponibles ─────────────────────────────────────────
        if stats is None:
            stats = {
                "nombre": nombre,
                "nota":   f"'{nombre}' no encontrado en ninguna fuente disponible",
                "fuente": "ninguna",
            }

        resultado[clave] = stats

    return resultado
