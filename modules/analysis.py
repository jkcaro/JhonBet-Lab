"""Módulo: Análisis de Partidos — carga datos desde data/matches.csv"""

import os
import time
from datetime import date as _date
from pathlib import Path
import pandas as pd
import streamlit as st
from scipy.stats import poisson

os.makedirs(Path(__file__).parent.parent / "data", exist_ok=True)

# Rutas absolutas a los CSV
RUTA_PARTIDOS = Path(__file__).parent.parent / "data" / "matches.csv"
RUTA_CUOTAS   = Path(__file__).parent.parent / "data" / "odds.csv"

_COLS_PARTIDOS = [
    "liga", "partido", "equipo_local", "equipo_visitante",
    "xg_local", "xg_visitante", "fuente_xg", "fecha",
]
_COLS_CUOTAS = ["partido", "mercado", "resultado", "codere", "bet365", "betfair"]


def _leer_csv_seguro(ruta: Path, cols_defecto: list[str]) -> pd.DataFrame:
    """Lee un CSV y devuelve un DataFrame vacío (con columnas) si el archivo no existe o está vacío."""
    if not ruta.exists():
        return pd.DataFrame(columns=cols_defecto)
    try:
        df = pd.read_csv(ruta)
        return df if not df.empty else pd.DataFrame(columns=cols_defecto)
    except Exception:
        return pd.DataFrame(columns=cols_defecto)


def cargar_partidos() -> pd.DataFrame:
    """
    Lee matches.csv y filtra partidos de fechas anteriores a hoy.
    Partidos sin columna 'fecha' se conservan (retrocompatibilidad).
    """
    df = _leer_csv_seguro(RUTA_PARTIDOS, _COLS_PARTIDOS)
    if df.empty or "fecha" not in df.columns:
        return df
    hoy = _date.today().isoformat()
    # Conservar filas sin fecha (NaN) y las de hoy en adelante
    mask = df["fecha"].isna() | (df["fecha"] >= hoy)
    return df[mask].reset_index(drop=True)


def _deduplicar_prioridad_manual(df: pd.DataFrame) -> pd.DataFrame:
    """
    Si el mismo partido aparece en datos de API y en entrada manual,
    elimina la versión de API y conserva la manual.

    La comparación usa la primera palabra de equipo_local y equipo_visitante
    (case-insensitive) para detectar coincidencias aunque los nombres difieran
    ligeramente ("CD Mirandés" vs "Mirandés", "Real Valladolid CF" vs "Valladolid").
    """
    if df.empty or "fuente_xg" not in df.columns:
        return df

    manuales = df[df["fuente_xg"] == "manual"]
    if manuales.empty:
        return df

    def _primera(nombre: str) -> str:
        return str(nombre).lower().split()[0] if nombre else ""

    indices_api_a_eliminar: set[int] = set()

    for _, fila_m in manuales.iterrows():
        clave_l = _primera(fila_m["equipo_local"])
        clave_v = _primera(fila_m["equipo_visitante"])

        for idx, fila_api in df.iterrows():
            if str(fila_api.get("fuente_xg", "estimado")) == "manual":
                continue   # no comparar manuales entre sí
            if (_primera(fila_api["equipo_local"])     == clave_l and
                    _primera(fila_api["equipo_visitante"]) == clave_v):
                indices_api_a_eliminar.add(idx)

    return df.drop(list(indices_api_a_eliminar)).reset_index(drop=True)


def _icono_fuente(fuente_xg: str) -> str:
    """Devuelve el emoji que identifica la fuente del xG."""
    return {"manual": "✏️", "api": "📡"}.get(str(fuente_xg), "📊")


def calcular_probabilidades_poisson(xg_local: float, xg_visitante: float) -> dict:
    """Calcula probabilidades 1X2 y Over/Under usando distribución de Poisson."""
    maximo_goles = 10
    prob_local = prob_empate = prob_visitante = 0.0

    for goles_local in range(maximo_goles):
        for goles_visitante in range(maximo_goles):
            probabilidad = (
                poisson.pmf(goles_local, xg_local) *
                poisson.pmf(goles_visitante, xg_visitante)
            )
            if goles_local > goles_visitante:
                prob_local += probabilidad
            elif goles_local == goles_visitante:
                prob_empate += probabilidad
            else:
                prob_visitante += probabilidad

    total = prob_local + prob_empate + prob_visitante

    # Over/Under 2.5 goles
    over25 = sum(
        poisson.pmf(h, xg_local) * poisson.pmf(a, xg_visitante)
        for h in range(maximo_goles)
        for a in range(maximo_goles)
        if h + a > 2
    )

    return {
        "local":      round(prob_local / total * 100, 1),
        "empate":     round(prob_empate / total * 100, 1),
        "visitante":  round(prob_visitante / total * 100, 1),
        "over25":     round(over25 * 100, 1),
        "under25":    round((1 - over25) * 100, 1),
    }


def _evaluar_riesgo(prob_local: float, prob_visitante: float) -> tuple[str, str]:
    diferencia = abs(prob_local - prob_visitante)
    if diferencia > 20:
        return "Bajo", "prob-verde"
    elif diferencia > 10:
        return "Moderado", "prob-amarillo"
    else:
        return "Alto", "prob-rojo"


def _recomendacion(nombre_local: str, nombre_visitante: float,
                   prob_local: float, prob_empate: float, prob_visitante: float) -> str:
    if prob_local >= prob_empate and prob_local >= prob_visitante:
        cuota = round(100 / prob_local, 2)
        return f"Victoria {nombre_local} @ {cuota}"
    elif prob_empate >= prob_local and prob_empate >= prob_visitante:
        cuota = round(100 / prob_empate, 2)
        return f"Valor en Empate @ {cuota}"
    else:
        cuota = round(100 / prob_visitante, 2)
        return f"Victoria {nombre_visitante} @ {cuota}"


# Prefijos genéricos que no identifican al equipo
_PREFIJOS_IGNORAR = {
    "cd", "fc", "ud", "rc", "cf", "sc", "rcd", "sd", "ad", "ce",
    "ca", "real", "atletico", "atlético", "deportivo", "sporting",
    "athletic", "club", "de", "la", "el", "los",
}


def _palabras_significativas(nombre: str) -> set[str]:
    """Devuelve las palabras del nombre de equipo que no son prefijos genéricos."""
    return {
        w.lower() for w in nombre.split()
        if w.lower() not in _PREFIJOS_IGNORAR and len(w) > 1
    }


def _equipos_coinciden(nombre_a: str, nombre_b: str) -> bool:
    """True si ambos nombres comparten al menos una palabra significativa."""
    sig_a = _palabras_significativas(nombre_a)
    sig_b = _palabras_significativas(nombre_b)
    return bool(sig_a & sig_b)


def _eliminar_conflictos_csv(ruta: Path, equipo_local: str, equipo_visitante: str) -> int:
    """
    Elimina del CSV todas las filas donde equipo_local O equipo_visitante
    coinciden con el nuevo equipo (comparando palabras significativas).
    Devuelve el número de filas eliminadas.
    """
    try:
        df = pd.read_csv(ruta)
    except Exception:
        return 0

    cols_equipo = [c for c in ["equipo_local", "equipo_visitante", "partido"] if c in df.columns]
    if not cols_equipo:
        return 0

    def _fila_conflicto(row) -> bool:
        eq_l = str(row.get("equipo_local", ""))
        eq_v = str(row.get("equipo_visitante", ""))
        # Conflicto si algún equipo del partido manual aparece en la fila del CSV
        return (
            _equipos_coinciden(equipo_local,    eq_l) or
            _equipos_coinciden(equipo_local,    eq_v) or
            _equipos_coinciden(equipo_visitante, eq_l) or
            _equipos_coinciden(equipo_visitante, eq_v)
        )

    mask = df.apply(_fila_conflicto, axis=1)
    eliminadas = mask.sum()
    df[~mask].to_csv(ruta, index=False)
    return int(eliminadas)


def _guardar_partido_manual(
    equipo_local: str, equipo_visitante: str, liga: str,
    cuota_local: float, cuota_empate: float, cuota_visitante: float,
    xg_local: float, xg_visitante: float,
    cuota_btts_si: float = 0.0, cuota_btts_no: float = 0.0,
    cuota_1t_local: float = 0.0, cuota_1t_empate: float = 0.0, cuota_1t_visitante: float = 0.0,
    btts_local_5: int | None = None, btts_visit_5: int | None = None,
    elo_local: float | None = None, elo_visit: float | None = None,
    motivacion: str = "", ultimo_partido: str = "No",
    cuota_o15: float = 0.0, cuota_u15: float = 0.0,
    forma_local: str = "", forma_visitante: str = "",
) -> None:
    """
    Guarda el partido manual.
    ANTES de guardar: elimina cualquier versión API conflictiva en ambos CSVs
    comparando por palabras significativas del nombre del equipo.
    """
    nombre = f"{equipo_local} vs {equipo_visitante}"

    # ── Eliminar versiones API conflictivas ──────────────────────────────────
    n_matches = _eliminar_conflictos_csv(RUTA_PARTIDOS, equipo_local, equipo_visitante)
    n_odds    = _eliminar_conflictos_csv(RUTA_CUOTAS,   equipo_local, equipo_visitante)
    print(f"[Manual] Conflictos eliminados → matches: {n_matches}, odds: {n_odds}")

    # ── matches.csv ──
    df_p = _leer_csv_seguro(RUTA_PARTIDOS, _COLS_PARTIDOS)
    nueva_fila = pd.DataFrame([{
        "liga":             liga,
        "partido":          nombre,
        "equipo_local":     equipo_local,
        "equipo_visitante": equipo_visitante,
        "xg_local":         xg_local,
        "xg_visitante":     xg_visitante,
        "fuente_xg":        "manual",
        "btts_local_5":     btts_local_5 if btts_local_5 is not None else "",
        "btts_visit_5":     btts_visit_5 if btts_visit_5 is not None else "",
        "elo_local":        elo_local if elo_local is not None else "",
        "elo_visit":        elo_visit if elo_visit is not None else "",
        "motivacion":       motivacion,
        "ultimo_partido":   ultimo_partido,
        "forma_local":      forma_local,
        "forma_visitante":  forma_visitante,
        "fecha":            _date.today().isoformat(),
    }])
    pd.concat([nueva_fila, df_p], ignore_index=True).to_csv(RUTA_PARTIDOS, index=False)

    # ── odds.csv ──
    df_c = _leer_csv_seguro(RUTA_CUOTAS, _COLS_CUOTAS)
    df_c = df_c[df_c["partido"] != nombre]

    filas = [
        {"partido": nombre, "mercado": "1X2", "resultado": "Local",
         "codere": cuota_local,     "bet365": cuota_local,     "betfair": cuota_local},
        {"partido": nombre, "mercado": "1X2", "resultado": "Empate",
         "codere": cuota_empate,    "bet365": cuota_empate,    "betfair": cuota_empate},
        {"partido": nombre, "mercado": "1X2", "resultado": "Visitante",
         "codere": cuota_visitante, "bet365": cuota_visitante, "betfair": cuota_visitante},
    ]
    # Ambos Marcan — solo si se introdujo la cuota (> 1.01)
    if cuota_btts_si > 1.01:
        filas.append({"partido": nombre, "mercado": "Ambos Marcan", "resultado": "Si",
                      "codere": cuota_btts_si, "bet365": cuota_btts_si, "betfair": cuota_btts_si})
    if cuota_btts_no > 1.01:
        filas.append({"partido": nombre, "mercado": "Ambos Marcan", "resultado": "No",
                      "codere": cuota_btts_no, "bet365": cuota_btts_no, "betfair": cuota_btts_no})
    # Resultado 1T — solo si se introdujo la cuota (> 1.01)
    if cuota_1t_local > 1.01:
        filas.append({"partido": nombre, "mercado": "Resultado 1T", "resultado": "Local",
                      "codere": cuota_1t_local, "bet365": cuota_1t_local, "betfair": cuota_1t_local})
    if cuota_1t_empate > 1.01:
        filas.append({"partido": nombre, "mercado": "Resultado 1T", "resultado": "Empate",
                      "codere": cuota_1t_empate, "bet365": cuota_1t_empate, "betfair": cuota_1t_empate})
    if cuota_1t_visitante > 1.01:
        filas.append({"partido": nombre, "mercado": "Resultado 1T", "resultado": "Visitante",
                      "codere": cuota_1t_visitante, "bet365": cuota_1t_visitante, "betfair": cuota_1t_visitante})
    # Over / Under 1.5 Goles
    if cuota_o15 > 1.01:
        filas.append({"partido": nombre, "mercado": "Over/Under 1.5", "resultado": "Over 1.5",
                      "codere": cuota_o15, "bet365": cuota_o15, "betfair": cuota_o15})
    if cuota_u15 > 1.01:
        filas.append({"partido": nombre, "mercado": "Over/Under 1.5", "resultado": "Under 1.5",
                      "codere": cuota_u15, "bet365": cuota_u15, "betfair": cuota_u15})

    pd.concat([pd.DataFrame(filas), df_c], ignore_index=True).to_csv(RUTA_CUOTAS, index=False)
    st.cache_data.clear()


def _cuota_val(prefill: dict, key: str, default: float) -> float:
    """Devuelve la cuota del prefill si es ≥ 1.01, si no el valor por defecto."""
    v = float(prefill.get(key) or 0)
    return v if v >= 1.01 else default


def _mensaje_partido_manual() -> None:
    """Muestra el mensaje de resultado (éxito/error) tras guardar un partido manual.

    El formulario que genera este mensaje es la página "Agregar Partido"
    (modules/add_partido.py), enlazada desde el sidebar bajo "Análisis de Partidos".
    """
    # ── Mensaje de resultado (éxito desaparece a los 5 s) ────────────────────
    if msg := st.session_state.get("msg_partido_manual"):
        if msg["tipo"] == "success":
            _ph = st.empty()
            _ph.success(msg["texto"])
            _restante = 5.0 - (time.time() - msg.get("created_at", time.time()))
            if _restante <= 0:
                st.session_state.pop("msg_partido_manual", None)
                _ph.empty()
            else:
                time.sleep(_restante)
                st.session_state.pop("msg_partido_manual", None)
                st.rerun()
        elif msg["tipo"] == "warning":
            st.warning(msg["texto"])
        else:
            st.error(msg["texto"])


def mostrar():
    """Renderiza el módulo completo de Análisis de Partidos."""
    df_raw      = cargar_partidos()
    df_partidos = _deduplicar_prioridad_manual(df_raw)   # manual tiene prioridad sobre API

    # ── Pre-seleccionar partido recién guardado ───────────────────────────────
    # Se hace ANTES de instanciar cualquier widget: escribir en session_state
    # antes de st.selectbox es seguro y fuerza el valor inicial del dropdown.
    recien_guardado = st.session_state.pop("partido_recien_guardado", None)
    if recien_guardado:
        fila_nueva = df_partidos[df_partidos["partido"] == recien_guardado]
        if not fila_nueva.empty:
            fuente_nueva = str(fila_nueva.iloc[0].get("fuente_xg", "estimado") or "estimado")
            st.session_state["sel_liga"]    = fila_nueva.iloc[0]["liga"]
            st.session_state["sel_partido"] = f"{recien_guardado} {_icono_fuente(fuente_nueva)}"

    ligas_disponibles = df_partidos["liga"].unique().tolist()

    if not ligas_disponibles:
        st.info(
            "No hay partidos cargados para hoy. "
            "Pulsa **Actualizar partidos reales** en el panel izquierdo "
            "o añade uno manualmente:"
        )
        _mensaje_partido_manual()
        return

    _col_liga, _col_partido = st.columns(2)
    with _col_liga:
        liga_elegida = st.selectbox("Liga:", ligas_disponibles, key="sel_liga")

    # Partidos de la liga seleccionada con icono de fuente
    df_liga = df_partidos[df_partidos["liga"] == liga_elegida].copy()

    tiene_fuente = "fuente_xg" in df_liga.columns
    if tiene_fuente:
        df_liga["_display"] = df_liga.apply(
            lambda r: f"{r['partido']} {_icono_fuente(r.get('fuente_xg','estimado'))}",
            axis=1,
        )
    else:
        df_liga["_display"] = df_liga["partido"]

    opciones_display = df_liga["_display"].tolist()
    opciones_real    = df_liga["partido"].tolist()

    if not opciones_display:
        st.info("Esta liga no tiene partidos. Selecciona otra liga o añade uno manualmente:")
        _mensaje_partido_manual()
        return

    with _col_partido:
        display_elegido = st.selectbox("Partido:", opciones_display, key="sel_partido")

    # Recuperar el nombre real del partido (sin icono) a partir de la selección
    try:
        idx_sel = opciones_display.index(display_elegido)
        partido_elegido = opciones_real[idx_sel]
    except (ValueError, IndexError):
        partido_elegido = display_elegido

    analizar = st.button("🧠 Analizar con IA", key="btn_analizar", use_container_width=True)

    # Guardar selección en estado de sesión para los otros módulos
    if analizar:
        st.session_state.partido_activo = partido_elegido
        st.session_state.liga_activa    = liga_elegida
        st.session_state.analisis_listo = True

    if not st.session_state.get("analisis_listo"):
        st.caption("Selecciona un partido y pulsa Analizar.")
        _mensaje_partido_manual()
        return

    # ── Buscar fila del partido por nombre exacto O palabras significativas ──
    partido_activo = st.session_state.partido_activo

    # 1) Búsqueda exacta
    _df_fila = df_partidos[df_partidos["partido"] == partido_activo].copy()

    # 2) Si no hay coincidencia exacta, buscar por palabras significativas
    if _df_fila.empty and " vs " in partido_activo:
        _eq_l_act, _eq_v_act = [p.strip() for p in partido_activo.split(" vs ", 1)]
        _mask = df_partidos.apply(
            lambda r: (
                _equipos_coinciden(_eq_l_act, str(r.get("equipo_local", ""))) and
                _equipos_coinciden(_eq_v_act, str(r.get("equipo_visitante", "")))
            ),
            axis=1,
        )
        _df_fila = df_partidos[_mask].copy()
        if not _df_fila.empty:
            print(f"[Analizar] Coincidencia fuzzy: '{partido_activo}' → '{_df_fila.iloc[0]['partido']}'")

    # 3) Si aún hay duplicados, priorizar manual > api > estimado
    if "fuente_xg" in _df_fila.columns and len(_df_fila) > 1:
        _orden = {"manual": 0, "api": 1, "estimado": 2}
        _df_fila = _df_fila.sort_values(
            "fuente_xg",
            key=lambda s: s.map(lambda v: _orden.get(str(v).lower(), 99)),
        )

    if _df_fila.empty:
        st.error(f"No se encontró '{partido_activo}' en matches.csv.")
        return

    fila = _df_fila.iloc[0]

    # ── Imprimir en terminal la fila exacta que se usa ────────────────────────
    print(
        f"[Analizar] Fila seleccionada:\n"
        f"  partido   = {fila['partido']}\n"
        f"  local     = {fila['equipo_local']}\n"
        f"  visitante = {fila['equipo_visitante']}\n"
        f"  xg_local  = {fila['xg_local']}\n"
        f"  xg_visit  = {fila['xg_visitante']}\n"
        f"  fuente_xg = {fila.get('fuente_xg', 'N/A')}"
    )
    xg_local     = float(fila["xg_local"])
    xg_visitante = float(fila["xg_visitante"])
    nombre_local  = fila["equipo_local"]
    nombre_visit  = fila["equipo_visitante"]
    fuente_xg     = str(fila.get("fuente_xg", "estimado") or "estimado").strip()

    probs = calcular_probabilidades_poisson(xg_local, xg_visitante)
    nivel_riesgo, clase_riesgo = _evaluar_riesgo(probs["local"], probs["visitante"])
    recomendacion = _recomendacion(nombre_local, nombre_visit,
                                   probs["local"], probs["empate"], probs["visitante"])
    tendencia = (f"{nombre_visit} en buena racha"
                 if probs["visitante"] > probs["local"]
                 else f"{nombre_local} favorito claro")

    # ── Leer cuotas del CSV (Ambos Marcan y Resultado 1T) ────────────────────
    btts_cuotas: dict = {}
    cuotas_1t: dict = {}
    try:
        _df_odds = _leer_csv_seguro(RUTA_CUOTAS, _COLS_CUOTAS)
        _df_match_odds = _df_odds[_df_odds["partido"] == st.session_state.partido_activo]

        for _, _row in _df_match_odds[_df_match_odds["mercado"] == "Ambos Marcan"].iterrows():
            res = str(_row.get("resultado", "")).strip()
            mejor = max(
                (float(_row.get(c, 0)) for c in ["codere", "bet365", "betfair"]
                 if float(_row.get(c, 0)) > 1.0),
                default=0.0,
            )
            if mejor > 0 and res in ("Si", "No"):
                btts_cuotas[res] = round(mejor, 2)

        for _, _row in _df_match_odds[_df_match_odds["mercado"] == "Resultado 1T"].iterrows():
            res = str(_row.get("resultado", "")).strip()
            mejor = max(
                (float(_row.get(c, 0)) for c in ["codere", "bet365", "betfair"]
                 if float(_row.get(c, 0)) > 1.0),
                default=0.0,
            )
            if mejor > 0 and res in ("Local", "Empate", "Visitante"):
                cuotas_1t[res] = round(mejor, 2)
    except Exception:
        pass

    # ── Leer columnas de forma BTTS y ELO (solo existen en partidos manuales) ──
    def _opt_int(key: str, lo: int = 0, hi: int = 5) -> int | None:
        v = fila.get(key)
        try:
            vi = int(float(v))
            return vi if lo <= vi <= hi else None
        except (ValueError, TypeError):
            return None

    def _opt_float(key: str) -> float | None:
        v = fila.get(key)
        try:
            vf = float(v)
            return vf if vf == vf else None  # NaN != NaN — celda vacía en el CSV
        except (ValueError, TypeError):
            return None

    def _opt_str(key: str) -> str:
        # Celda vacía de CSV llega como NaN (float); "nan" or "" es truthy y
        # se colaría como texto literal si no se filtra el NaN explícitamente.
        v = fila.get(key, "")
        if v is None or v != v:
            return ""
        return str(v).strip()

    # ── Persistir en session_state para Claude ─────────────────────────────────
    st.session_state["fuente_xg_activa"]    = fuente_xg
    st.session_state["btts_cuotas_manual"]  = btts_cuotas
    st.session_state["cuotas_1t_manual"]    = cuotas_1t
    st.session_state["btts_local_5"]        = _opt_int("btts_local_5")
    st.session_state["btts_visit_5"]        = _opt_int("btts_visit_5")
    st.session_state["elo_local"]           = _opt_float("elo_local")
    st.session_state["elo_visit"]           = _opt_float("elo_visit")
    # Contexto de motivación (vacío si no es partido manual)
    _mot_raw = _opt_str("motivacion")
    _ult_raw = _opt_str("ultimo_partido")
    st.session_state["motivacion_partido"]       = _mot_raw or None
    st.session_state["ultimo_partido_temporada"] = _ult_raw if _ult_raw == "Sí" else None
    # Forma reciente cargada desde Football-Data.org al añadir el partido (si la hay) —
    # prefill editable de los campos "Forma reciente" en la página Claude AI.
    st.session_state["forma_reciente_local_csv"] = _opt_str("forma_local")
    st.session_state["forma_reciente_visit_csv"] = _opt_str("forma_visitante")
    st.session_state["probs_partido"] = {
        f"victoria_{nombre_local}": f"{probs['local']}%",
        "empate":                    f"{probs['empate']}%",
        f"victoria_{nombre_visit}":  f"{probs['visitante']}%",
        "over_2.5_goles":            f"{probs['over25']}%",
        "xg_local":                  xg_local,
        "xg_visitante":              xg_visitante,
    }
    st.session_state["mejor_cuota_partido"] = recomendacion
    st.session_state.pop("claude_analisis", None)

    # ── Debug: fila CSV exacta usada en el análisis ────────────────────────────
    _BADGE = {"estimado": ("📊", "#5a7a9a"), "manual": ("✏️", "#ffd700"), "api": ("📡", "#00aa44")}
    _icono_d, _color_d = _BADGE.get(fuente_xg, _BADGE["estimado"])

    _btts_debug = ""
    if btts_cuotas:
        si_txt = f"Sí {btts_cuotas['Si']}" if "Si" in btts_cuotas else ""
        no_txt = f"No {btts_cuotas['No']}" if "No" in btts_cuotas else ""
        _btts_debug = f" · BTTS: {si_txt} / {no_txt}"

    _1t_debug = ""
    if cuotas_1t:
        partes_1t = []
        if "Local"     in cuotas_1t: partes_1t.append(f"L {cuotas_1t['Local']}")
        if "Empate"    in cuotas_1t: partes_1t.append(f"E {cuotas_1t['Empate']}")
        if "Visitante" in cuotas_1t: partes_1t.append(f"V {cuotas_1t['Visitante']}")
        _1t_debug = f" · 1T: {' / '.join(partes_1t)}"

    st.markdown(
        f'<div style="font-size:11px;background:#1a2820;border:1px solid #1e3a2a;'
        f'border-radius:5px;padding:6px 10px;margin:4px 0 8px;">'
        f'📍 Fila CSV: <b>{nombre_local} vs {nombre_visit}</b>'
        f' · xG <b>{xg_local}</b> / <b>{xg_visitante}</b>'
        f' · {_icono_d} <span style="color:{_color_d};">{fuente_xg.capitalize()}</span>'
        f'{_btts_debug}{_1t_debug}'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown(f"""
<div style="margin-top:14px;">
  <div class="etiqueta-seccion">Probabilidades:</div>
  <div class="fila-prob">
    <span>•</span><span>{nombre_local}</span>
    <span class="insignia prob-amarillo">{probs['local']}%</span>
    <span class="texto-apagado">— Empate</span>
    <span class="insignia prob-azul">{probs['empate']}%</span>
  </div>
  <div class="fila-prob">
    <span>•</span><span>{nombre_visit}</span>
    <span class="insignia prob-rojo">{probs['visitante']}%</span>
  </div>
  <div class="fila-prob" style="margin-top:8px;">
    <span class="texto-apagado">• Tendencia:</span>
    <span>{tendencia}</span>
  </div>
  <div class="fila-prob">
    <span class="texto-apagado">• Riesgo:</span>
    <span class="insignia {clase_riesgo}">{nivel_riesgo}</span>
  </div>
  <div class="fila-prob" style="margin-top:4px;">
    <span class="texto-apagado">• Recomendado:</span>
    <span class="texto-dorado">{recomendacion}</span>
  </div>
</div>
""", unsafe_allow_html=True)

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    _mensaje_partido_manual()
