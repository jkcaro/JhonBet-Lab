"""
Módulo: TheSportsDB — logos de equipos sin necesidad de API key.
Descarga y cachea los logos en assets/logos/ para no repetir peticiones.
"""

import base64
import re
import requests
import streamlit as st
from pathlib import Path

# Carpeta local donde se guardan los logos descargados
RUTA_LOGOS = Path(__file__).parent.parent / "assets" / "logos"
RUTA_LOGOS.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://www.thesportsdb.com/api/v1/json/3"
TIMEOUT  = 6  # segundos máximo por petición


def _nombre_archivo(equipo: str) -> str:
    """Convierte el nombre del equipo en un nombre de archivo seguro."""
    limpio = re.sub(r"[^\w\s]", "", equipo.lower()).strip()
    return re.sub(r"\s+", "_", limpio) + ".png"


@st.cache_data(ttl=86400)   # caché de 24 horas para no repetir búsquedas
def _buscar_url_logo(equipo: str) -> str | None:
    """Consulta TheSportsDB y devuelve la URL del escudo del equipo."""
    try:
        resp = requests.get(
            f"{BASE_URL}/searchteams.php",
            params={"t": equipo},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        equipos = (resp.json().get("teams") or [])
        if equipos:
            return equipos[0].get("strTeamBadge")
    except Exception:
        pass
    return None


def obtener_logo_b64(equipo: str) -> str | None:
    """
    Devuelve el logo del equipo codificado en base64.
    Flujo:
      1. Busca en caché local (assets/logos/).
      2. Si no existe, descarga de TheSportsDB y guarda.
      3. Devuelve None si no se puede obtener.
    """
    ruta = RUTA_LOGOS / _nombre_archivo(equipo)

    # Caché local: si el archivo existe, lo leemos directamente
    if ruta.exists():
        try:
            return base64.b64encode(ruta.read_bytes()).decode()
        except Exception:
            pass

    # Descarga
    url = _buscar_url_logo(equipo)
    if not url:
        return None

    try:
        resp = requests.get(url, timeout=TIMEOUT)
        if resp.status_code == 200:
            ruta.write_bytes(resp.content)
            return base64.b64encode(resp.content).decode()
    except Exception:
        pass
    return None


def logo_html(equipo: str, px: int = 22) -> str:
    """
    Devuelve un <img> HTML con el logo del equipo listo para usar en st.markdown().
    Si los logos están desactivados o no se encuentra el equipo, devuelve ''.
    """
    if not st.session_state.get("fuente_logos", True):
        return ""
    b64 = obtener_logo_b64(equipo)
    if b64:
        return (
            f'<img src="data:image/png;base64,{b64}" '
            f'style="width:{px}px;height:{px}px;object-fit:contain;'
            f'vertical-align:middle;margin-right:5px;border-radius:2px;">'
        )
    return ""
