# Skill: Trabajar en BetVision AI

## Entorno
- Proyecto en WSL: /home/jhoncaro/proyectos/JhonBet-Lab — trabajar SIEMPRE desde WSL, nunca PowerShell
- venv en ./venv — activar antes de python/streamlit
- Screenshots con Playwright SÍ son viables sin sudo: chrome-headless-shell falla por libs faltantes (libnspr4, libnss3, libnssutil3, libasound.so.2 — confirmar con `ldd` sobre el binario en ~/.cache/ms-playwright/). Se resuelve con `apt-get download <paquete>` (no requiere root) + `dpkg-deb -x <deb> <dir>` + lanzar Chromium con `LD_LIBRARY_PATH=<dir>/usr/lib/x86_64-linux-gnu` apuntando ahí. Útil para medir alineación/bounding boxes real (Playwright `.bounding_box()`), no solo mirar la captura. Esto NO reemplaza la verificación final del usuario — es evidencia previa, no el visto bueno.
- Matar streamlits propios al terminar (pkill -f streamlit)

## Arquitectura
- Capa visual separada de capa de datos: etiquetas via modules/etiquetas_mercado.py; claves canónicas (MERCADOS_CLAUDE, fh_*, CSVs) NUNCA se renombran
- Módulo Primera Parte independiente: no importa del sistema de señales
- Credenciales/tokens SOLO en .streamlit/secrets.toml (gitignored)

## Trampas conocidas
- estado_sesion.json puede fosilizar valores de código viejo (bug ceros fantasma) — ante bug "imposible" tras fix correcto, revisar el JSON persistido
- Dato ausente ≠ 0: campos vacíos son None y se pintan "—", jamás 0
- st.columns impone anchos rígidos: para layouts compactos, HTML+flexbox propio

## Método de trabajo
- Ante un bug: DIAGNÓSTICO con evidencia antes de tocar código; mostrar la causa raíz
- Al terminar: py_compile + pyflakes + demostrar el resultado (render/output real), no "aplicado"
- Commits descriptivos; cambios de riesgo en commits separados
- Responder siempre en español
