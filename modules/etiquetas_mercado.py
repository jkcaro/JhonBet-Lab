"""Módulo: Diccionario central de etiquetas visuales de mercados/apuestas.

Nomenclatura Codere para mercados y sus outcomes, terminología BeSoccer para
datos estadísticos (xG, Forma reciente, ELO — ver los módulos que los usan),
y lenguaje común entendible por cualquiera en los títulos.

IMPORTANTE — este módulo NO es fuente de datos ni de claves internas. Las
claves canónicas usadas en el resto de la app para comparaciones
(`if mercado == "Victoria 1X2"`), columnas de CSV (odds.csv, matches.csv) y
JSON persistido (data/claude_analysis.json) NO cambian — siguen siendo
exactamente las mismas de siempre, así los históricos ya guardados se leen
sin migración. Este módulo solo traduce esas claves a texto visible.

Los módulos deben pintar títulos y outcomes de mercado A TRAVÉS de las
funciones de aquí (titulo_mercado / outcome_1x2 / outcome_primer_marcador /
outcome_ou), nunca escribiendo el texto visible a mano.
"""

# ── Títulos de mercado: clave canónica interna (sin cambios) → texto visible ──
TITULOS_MERCADO: dict[str, str] = {
    "1X2":                    "¿Quién gana el partido?",
    "Victoria 1X2":           "¿Quién gana el partido?",
    "Ambos Marcan":           "Marcan Ambos Equipos",
    "Over/Under 1.5":         "Más/Menos Total Goles (línea 1.5)",
    "Over/Under 2.5":         "Más/Menos Total Goles (línea 2.5)",
    "1X2 HT":                 "1ª Parte — ¿Quién gana la primera parte?",
    "Resultado 1T":           "1ª Parte — ¿Quién gana la primera parte?",
    "Resultado al descanso":  "1ª Parte — ¿Quién gana la primera parte?",
    "O/U 0.5 HT":             "1ª Parte — Más/Menos Total Goles (línea 0.5)",
    "O/U 1.5 HT":             "1ª Parte — Más/Menos Total Goles (línea 1.5)",
    "Primer en marcar":       "1ª Parte — Primer Equipo en Marcar",
}

# ── Outcomes de mercados 1X2 (partido completo y HT) ───────────────────────────
# "{local}"/"{visitante}" se sustituyen por el nombre real del equipo si se
# conoce; si no, quedan como "Local"/"Visitante" (fallback ya resuelto por
# quien llama, ver nombre_local/nombre_visit en cada módulo).
OUTCOMES_1X2: dict[str, str] = {
    "Local":     "Gana {local}",
    "Empate":    "Empate",
    "Visitante": "Gana {visitante}",
}

# ── Outcomes de "Primer equipo en marcar" — Codere lo llama "Sin Gol", no "Ninguno" ──
OUTCOMES_PRIMER_MARCADOR: dict[str, str] = {
    "Local":     "{local}",
    "Visitante": "{visitante}",
    "Ninguno":   "Sin Gol",
}

EDGE_LABEL = "ventaja (edge)"


def outcome_1x2(clave_canonica: str, nombre_local: str = "Local", nombre_visit: str = "Visitante") -> str:
    """"Local" -> "Gana España", "Empate" -> "Empate", "Visitante" -> "Gana Bélgica"."""
    plantilla = OUTCOMES_1X2.get(clave_canonica, clave_canonica)
    return plantilla.format(local=nombre_local, visitante=nombre_visit)


def outcome_primer_marcador(clave_canonica: str, nombre_local: str = "Local", nombre_visit: str = "Visitante") -> str:
    """"Local" -> "España", "Visitante" -> "Bélgica", "Ninguno" -> "Sin Gol" (término literal de Codere)."""
    plantilla = OUTCOMES_PRIMER_MARCADOR.get(clave_canonica, clave_canonica)
    return plantilla.format(local=nombre_local, visitante=nombre_visit)


def outcome_ou(etiqueta_canonica: str) -> str:
    """"Over 0.5" -> "Más de 0.5", "Under 1.5" -> "Menos de 1.5" (cualquier línea)."""
    if etiqueta_canonica.startswith("Over"):
        return "Más de" + etiqueta_canonica[len("Over"):]
    if etiqueta_canonica.startswith("Under"):
        return "Menos de" + etiqueta_canonica[len("Under"):]
    return etiqueta_canonica


def titulo_mercado(clave_canonica: str) -> str:
    """Título en lenguaje común (con nombre corto Codere embebido) para una clave canónica de mercado."""
    return TITULOS_MERCADO.get(clave_canonica, clave_canonica)
