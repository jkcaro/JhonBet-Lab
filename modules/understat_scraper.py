"""
Módulo: Scraper de xG desde understat.com
Obtiene xG de partidos jugados y estadísticas BTTS de los últimos 5 partidos
buscando por nombre de equipo en las principales ligas europeas.
"""

import json
import re
import html as _html
from datetime import datetime
from typing import Optional
import requests
from bs4 import BeautifulSoup

# ─── Configuración ────────────────────────────────────────────────────────────

LIGAS_UNDERSTAT = ["La_liga", "EPL", "Bundesliga", "Serie_A", "Ligue_1"]

_HOY = datetime.now()
TEMPORADA_ACTUAL: int = _HOY.year if _HOY.month >= 7 else _HOY.year - 1

BASE_URL = "https://understat.com"
TIMEOUT  = 12
HEADERS  = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Palabras que se ignoran al comparar nombres de equipo
_STOP_PALABRAS = {
    "fc", "cf", "sc", "ac", "rc", "cd", "ud", "rcd", "sd", "ca",
    "de", "la", "el", "los", "the", "united", "city", "club",
    "athletic", "atletico", "atlético", "real", "deportivo", "sporting",
}


# ─── Utilidades internas ──────────────────────────────────────────────────────

def _extraer_json_script(soup: BeautifulSoup, variable: str):
    """
    Extrae y deserializa el JSON embebido en los <script> de understat.
    Los datos se almacenan como: var nombre = JSON.parse('...json...')
    """
    patron = re.compile(
        rf"var\s+{re.escape(variable)}\s*=\s*JSON\.parse\('(.+?)'\)",
        re.DOTALL,
    )
    for script in soup.find_all("script"):
        texto = script.string or ""
        m = patron.search(texto)
        if m:
            raw = _html.unescape(m.group(1))
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue
    return None


def _palabras_significativas(nombre: str) -> set:
    """Palabras del nombre de equipo que no son prefijos/sufijos genéricos."""
    tokens = re.split(r"[\s\-_./]+", nombre.lower())
    return {t for t in tokens if t not in _STOP_PALABRAS and len(t) > 2}


def _equipos_coinciden(nombre_a: str, nombre_b: str) -> bool:
    """True si los dos nombres de equipo comparten al menos una palabra significativa."""
    pa = _palabras_significativas(nombre_a)
    pb = _palabras_significativas(nombre_b)
    if pa & pb:
        return True
    # Comprobación adicional: uno contiene al otro (ej. "Madrid" en "Real Madrid")
    a_norm = nombre_a.lower().strip()
    b_norm = nombre_b.lower().strip()
    return a_norm in b_norm or b_norm in a_norm


def _get_soup(url: str) -> Optional[BeautifulSoup]:
    """GET con manejo de errores. Devuelve BeautifulSoup o None."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        return BeautifulSoup(resp.content, "html.parser")
    except requests.exceptions.Timeout:
        print(f"[understat] Timeout al conectar con {url}")
    except requests.exceptions.HTTPError as e:
        print(f"[understat] Error HTTP {e.response.status_code} en {url}")
    except requests.exceptions.RequestException as e:
        print(f"[understat] Error de red en {url}: {e}")
    return None


def _safe_float(valor, defecto: float = 0.0) -> float:
    """Convierte a float sin lanzar excepción."""
    try:
        return float(valor or 0)
    except (ValueError, TypeError):
        return defecto


def _safe_int(valor, defecto: int = 0) -> int:
    """Convierte a int sin lanzar excepción."""
    try:
        return int(valor or 0)
    except (ValueError, TypeError):
        return defecto


# ─── Lógica de scraping ───────────────────────────────────────────────────────

def _datos_equipo_en_liga(
    nombre_equipo: str, liga: str, temporada: int
) -> Optional[dict]:
    """
    Busca el equipo dentro de una liga específica de understat.
    Devuelve el dict de datos del equipo o None si no se encuentra.

    El dict incluye:
      - equipo, liga, temporada
      - btts_ultimos_5: partidos BTTS en los últimos 5
      - xg_media_ataque: xG generado medio (todos los partidos disponibles)
      - xg_media_defensa: xG cedido medio
      - partidos_recientes: lista de dicts con historial completo del equipo
    """
    # Paso 1 — Página de liga: obtener nombre exacto del equipo en understat
    soup_liga = _get_soup(f"{BASE_URL}/league/{liga}/{temporada}")
    if soup_liga is None:
        return None

    teams_data = _extraer_json_script(soup_liga, "teamsData")
    if not teams_data:
        return None

    titulo_exacto: Optional[str] = None
    for titulo in teams_data.keys():
        if _equipos_coinciden(nombre_equipo, titulo):
            titulo_exacto = titulo
            break

    if titulo_exacto is None:
        return None  # equipo no encontrado en esta liga

    # Paso 2 — Página del equipo: historial de partidos
    slug = titulo_exacto.replace(" ", "_")
    soup_equipo = _get_soup(f"{BASE_URL}/team/{slug}/{temporada}")
    if soup_equipo is None:
        return None

    dates_data = _extraer_json_script(soup_equipo, "datesData")
    if not dates_data:
        return None

    # Filtrar solo partidos con resultado
    jugados = [m for m in dates_data if m.get("isResult")]
    if not jugados:
        return None

    # Procesar todo el historial disponible
    partidos: list[dict] = []
    for m in jugados:
        es_local = _equipos_coinciden(titulo_exacto, m["h"]["title"])
        xg_h = _safe_float(m.get("xG", {}).get("h"))
        xg_a = _safe_float(m.get("xG", {}).get("a"))
        goles_h = _safe_int(m.get("goals", {}).get("h"))
        goles_a = _safe_int(m.get("goals", {}).get("a"))

        xg_favor  = xg_h if es_local else xg_a
        xg_contra = xg_a if es_local else xg_h
        goles_favor  = goles_h if es_local else goles_a
        goles_contra = goles_a if es_local else goles_h
        btts = goles_favor > 0 and goles_contra > 0

        partidos.append({
            "rival":        m["a"]["title"] if es_local else m["h"]["title"],
            "es_local":     es_local,
            "goles_favor":  goles_favor,
            "goles_contra": goles_contra,
            "xg_favor":     round(xg_favor, 2),
            "xg_contra":    round(xg_contra, 2),
            "btts":         btts,
            "fecha":        (m.get("datetime") or "")[:10],
        })

    # Estadísticas de los últimos 5 partidos
    ultimos_5 = partidos[-5:]
    btts_count = sum(1 for p in ultimos_5 if p["btts"])

    # xG media (todos los partidos disponibles)
    n = len(partidos)
    xg_ataque_media  = round(sum(p["xg_favor"]  for p in partidos) / n, 2) if n else 0.0
    xg_defensa_media = round(sum(p["xg_contra"] for p in partidos) / n, 2) if n else 0.0

    return {
        "equipo":             titulo_exacto,
        "liga":               liga,
        "temporada":          temporada,
        "btts_ultimos_5":     btts_count,
        "xg_media_ataque":    xg_ataque_media,
        "xg_media_defensa":   xg_defensa_media,
        "partidos_recientes": partidos,   # historial completo, más reciente al final
    }


# ─── API pública ──────────────────────────────────────────────────────────────

def buscar_equipo_en_understat(
    nombre: str, temporada: Optional[int] = None
) -> Optional[dict]:
    """
    Busca el equipo en todas las ligas soportadas de understat.com.

    Parámetros:
        nombre    — nombre del equipo (se busca por similitud)
        temporada — año de inicio de temporada (ej. 2024 para 2024/25).
                    Si se omite, usa la temporada actual.

    Retorna un dict con:
        equipo, liga, temporada,
        btts_ultimos_5, xg_media_ataque, xg_media_defensa,
        partidos_recientes
    O None si no se encuentra en ninguna liga.
    """
    temporada = temporada or TEMPORADA_ACTUAL
    for liga in LIGAS_UNDERSTAT:
        datos = _datos_equipo_en_liga(nombre, liga, temporada)
        if datos is not None:
            return datos
    return None


def obtener_xg_partido(
    equipo_local: str,
    equipo_visitante: str,
    temporada: Optional[int] = None,
) -> dict:
    """
    Obtiene los xG para el partido entre equipo_local y equipo_visitante.

    Estrategia:
      1. Busca el partido exacto en el historial del equipo local.
         Si se jugó, devuelve los xG reales del partido.
      2. Si no se jugó todavía (partido futuro), devuelve los xG medios
         de la forma reciente de cada equipo como estimación.
      3. Siempre intenta obtener los datos BTTS de los últimos 5 partidos.

    Retorna:
        {
          "xg_local":         float | None,
          "xg_visitante":     float | None,
          "btts_local_5":     int | None,    — partidos BTTS de los últimos 5
          "btts_visitante_5": int | None,
          "partido_exacto":   bool,          — True si se encontró el partido jugado
          "fuente":           str,
          "error":            str | None,
        }
    """
    temporada = temporada or TEMPORADA_ACTUAL
    resultado: dict = {
        "xg_local":         None,
        "xg_visitante":     None,
        "btts_local_5":     None,
        "btts_visitante_5": None,
        "partido_exacto":   False,
        "fuente":           "understat.com",
        "error":            None,
    }

    datos_local     = buscar_equipo_en_understat(equipo_local,     temporada)
    datos_visitante = buscar_equipo_en_understat(equipo_visitante, temporada)

    if datos_local is None and datos_visitante is None:
        resultado["error"] = (
            f"Equipos '{equipo_local}' y '{equipo_visitante}' no encontrados "
            "en understat.com. Solo cubre EPL, La Liga, Bundesliga, Serie A y Ligue 1."
        )
        return resultado

    # BTTS de los últimos 5 — siempre que se encuentre el equipo
    if datos_local:
        resultado["btts_local_5"] = datos_local["btts_ultimos_5"]
    if datos_visitante:
        resultado["btts_visitante_5"] = datos_visitante["btts_ultimos_5"]

    # Buscar el partido exacto en el historial del equipo local
    if datos_local:
        for partido in reversed(datos_local["partidos_recientes"]):
            if _equipos_coinciden(partido["rival"], equipo_visitante):
                if partido["es_local"]:
                    resultado["xg_local"]     = partido["xg_favor"]
                    resultado["xg_visitante"] = partido["xg_contra"]
                else:
                    # El equipo buscado era visitante en ese partido: invertir roles
                    resultado["xg_local"]     = partido["xg_contra"]
                    resultado["xg_visitante"] = partido["xg_favor"]
                resultado["partido_exacto"] = True
                resultado["fuente"] = "understat.com (partido real)"
                break

    # Sin partido exacto: usar xG medios como estimación
    if not resultado["partido_exacto"]:
        if datos_local:
            resultado["xg_local"] = datos_local["xg_media_ataque"]
        if datos_visitante:
            resultado["xg_visitante"] = datos_visitante["xg_media_ataque"]
        if datos_local or datos_visitante:
            resultado["fuente"] = "understat.com (estimado — forma reciente)"

    return resultado


def obtener_xg_para_formulario(
    equipo_local: str, equipo_visitante: str
) -> dict:
    """
    Función de conveniencia para el formulario de análisis de la app.
    Llama a obtener_xg_partido y devuelve un dict simplificado con
    valores listos para rellenar los campos del formulario.

    Retorna:
        {
          "xg_local":      float,
          "xg_visitante":  float,
          "btts_local_5":  int | None,
          "btts_visita_5": int | None,
          "mensaje":       str,    — texto para mostrar al usuario
          "exito":         bool,
        }
    """
    try:
        datos = obtener_xg_partido(equipo_local, equipo_visitante)
    except Exception as exc:
        return {
            "xg_local":     1.5,
            "xg_visitante": 1.2,
            "btts_local_5":  None,
            "btts_visita_5": None,
            "mensaje":  f"Error inesperado al consultar understat: {exc}",
            "exito":    False,
        }

    if datos.get("error"):
        return {
            "xg_local":     1.5,
            "xg_visitante": 1.2,
            "btts_local_5":  None,
            "btts_visita_5": None,
            "mensaje":  datos["error"],
            "exito":    False,
        }

    xg_l = datos["xg_local"]     or 1.5
    xg_v = datos["xg_visitante"] or 1.2

    tipo = "partido real" if datos["partido_exacto"] else "estimado (forma reciente)"

    partes_btts: list[str] = []
    if datos["btts_local_5"] is not None:
        partes_btts.append(f"BTTS local: {datos['btts_local_5']}/5")
    if datos["btts_visitante_5"] is not None:
        partes_btts.append(f"BTTS visit.: {datos['btts_visitante_5']}/5")

    msg = f"✅ xG obtenido desde understat ({tipo}) — {xg_l} / {xg_v}"
    if partes_btts:
        msg += f" · {', '.join(partes_btts)}"

    return {
        "xg_local":     round(xg_l, 2),
        "xg_visitante": round(xg_v, 2),
        "btts_local_5":  datos["btts_local_5"],
        "btts_visita_5": datos["btts_visitante_5"],
        "mensaje":  msg,
        "exito":    True,
    }
