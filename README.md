# JhonBet Lab

Para habrir por terminal
 cd /home/jhoncaro/proyectos/JhonBet-Lab
source venv/bin/activate
streamlit run app.py



Plataforma de análisis de apuestas deportivas con modelo Poisson/xG, comparación de cuotas en tiempo real y análisis con Claude AI.

-----------------------------------
***********************************


docker build -t jhonbet-lab . && docker run -d -p 8501:8501 -v $(pwd)/data:/app/data --name jhonbet-lab jhonbet-lab


------------------------------------
************************************

In app.py, after clicking "Analizar Partido", show a small debug info box below the match selector that displays the exact data being used for analysis:

- Partido seleccionado
- xG local y xG visitante (con fuente: estimado/manual/API)
- Cuotas cargadas (local, empate, visitante)
- Fuente de datos (The Odds API / Manual BeSoccer / API Real)

Show this in a collapsed expander called "🔍 Ver datos del análisis" so the user can verify before clicking Analizar con Claude AI. All in Spanish.

---

Reiniciar app

C:\Users\jhona\AppData\Local\Programs\Python\Python312\Scripts\streamlit.exe run c:\JhonBet-Lab\app.py

## Requisitos

- Python 3.10 o superior 
- Conexión a internet (para The Odds API y Claude AI)

---

## Instalación

```bash
pip install -r requirements.txt
```

---

## Iniciar la app
----------------------------------
----------------------------------
docker rm -f jhonbet-lab 2>/dev/null; docker run -d -p 8501:8501 -v /home/jhoncaro/proyectos/JhonBet-Lab/data:/app/data --name jhonbet-lab jhonbet-lab

-------------------------------------
-------------------------------------
```bash
streamlit run app.py
```

Se abrirá automáticamente en el navegador en:

```
http://localhost:8501
```

Si no se abre sola, copia esa URL en el navegador manualmente.

---

## Reiniciar la app

### Opción 1 — Desde la terminal

Pulsa `Ctrl + C` en la terminal donde corre la app y vuelve a ejecutar:

```bash
streamlit run app.py
```

### Opción 2 — Desde el navegador

Pulsa `R` con el navegador enfocado en la app, o usa el botón de recarga del navegador (`F5`).

### Opción 3 — Menú de Streamlit

En la esquina superior derecha de la app hay un menú `⋮` → **Rerun**.

---

## Estructura del proyecto

```
JhonBet-Lab/
├── app.py                   # Punto de entrada principal
├── requirements.txt
├── modules/
│   ├── analysis.py          # Análisis de partidos + formulario manual
│   ├── odds_comparison.py   # Comparación de cuotas entre casas
│   ├── predictive_model.py  # Modelo Poisson / xG
│   ├── alerts.py            # Alertas, historial y control de bankroll
│   ├── claude_analysis.py   # Integración con Claude AI
│   ├── odds_api.py          # Conexión con The Odds API
│   └── value_scanner.py     # Escáner de valor (edge > 5%)
├── data/
│   ├── matches.csv          # Partidos disponibles
│   ├── odds.csv             # Cuotas por casa de apuestas
│   └── history.csv          # Historial de apuestas registradas
└── assets/
    └── logo.png             # Logo (opcional)
```

---

## Variables de configuración

| Archivo                      | Variable  | Descripción                           |
| ---------------------------- | --------- | ------------------------------------- |
| `modules/claude_analysis.py` | `API_KEY` | Clave de la API de Anthropic (Claude) |
| `modules/odds_api.py`        | `API_KEY` | Clave de The Odds API                 |

---

## Funcionalidades principales

- **Análisis de partidos** — probabilidades Poisson, riesgo y recomendación
- **Comparación de cuotas** — Codere, Bet365 y Betfair en tiempo real
- **Modelo predictivo** — simulador xG interactivo
- **Claude AI** — análisis adaptado por mercado (1X2, Over/Under, Corners, etc.)
- **Escáner de valor** — detecta edge > 5% en todas las ligas automáticamente
- **Alertas** — pausa por 3 pérdidas seguidas, objetivo diario alcanzado
- **Registro manual** — añade apuestas y partidos directamente desde la app
