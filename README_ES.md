🌎 Idioma: 🇺🇸 [English](README.md) | 🇨🇱 Español

<div align="center">

# Plataforma Unificada de Análisis de Datos

**Pipeline ETL de producción + dashboard interactivo de analítica**
Consolida 4 fuentes heterogéneas (≈52.000 registros) en un maestro único de usuarios deduplicado y lo convierte en acción con un dashboard de Streamlit.

</div>

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![pandas](https://img.shields.io/badge/pandas-2.x-150458?logo=pandas&logoColor=white)
![NumPy](https://img.shields.io/badge/NumPy-1.24%2B-013243?logo=numpy&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-3.x-003B57?logo=sqlite&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.32%2B-FF4B4B?logo=streamlit&logoColor=white)
![Plotly](https://img.shields.io/badge/Plotly-5.18%2B-3F4F75?logo=plotly&logoColor=white)
![schedule](https://img.shields.io/badge/schedule-1.2+-0FB6E8?logo=clockify&logoColor=white)
![Faker](https://img.shields.io/badge/Faker-22%2B-E989C6?logo=faker&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
<br>
![Status](https://img.shields.io/badge/Estado-Producción--inspired-2ea44f)
![Tests](https://img.shields.io/badge/Tests-81%20scripts%20de%20verificación-2ea44f)
![Etapas](https://img.shields.io/badge/Pipeline-5%20fases-2ea44f)

---

## Índice

- [Descripción general](#descripción-general)
- [¿Por qué este proyecto?](#por-qué-este-proyecto)
- [Características](#características)
- [Arquitectura](#arquitectura)
- [Inicio rápido (demo local)](#inicio-rápido-demo-local)
- [Uso](#uso)
- [Salidas del pipeline](#salidas-del-pipeline)
- [Tests y verificación](#tests-y-verificación)
- [Desafíos de ingeniería](#desafíos-de-ingeniería)
- [Decisiones de diseño](#decisiones-de-diseño)
- [Implementación real](#implementación-real)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Roadmap](#roadmap)
- [Licencia](#licencia)

---

## Descripción general

Las organizaciones acumulan datos de usuarios en sistemas desconectados — plataformas web de registro, herramientas de talleres basadas en formularios, servicios de mensajería/chatbot y exportaciones de videoconferencias. Cada fuente tiene su propio **esquema, codificación, delimitador y peculiaridades de exportación**. Unirlas manualmente es propenso a errores y no escala.

**Plataforma Unificada de Análisis de Datos** lo resuelve con un pipeline ETL modular de cinco fases:

```
Extracción → Transformación → Consolidación → Carga → Analítica
```

Ingiere cuatro fuentes CSV heterogéneas, resuelve la identidad entre fuentes con un **algoritmo de matching de dos pasadas con score de confianza** y entrega un maestro único de usuarios limpio tanto a una **base de datos SQLite** como a un **dashboard interactivo de Streamlit**.

Construido sobre **datos demo sintéticos que replican fielmente distribuciones reales de producción** (≈52.000 usuarios en cuatro fuentes), ejercita los problemas de calidad de datos que rara vez aparecen en tutoriales: campos de texto libre multilínea que rompen los parsers CSV estándar, codificaciones inconsistentes, columnas clave con NULL y reglas de deduplicación que difieren por fuente por razones de negocio legítimas.

> **Diseñado para reutilizarse.** Agregar una nueva fuente requiere solo una subclase de `BaseExtractor` y un mapeo de columnas en `config/mappings.py`. Las capas de transformación, consolidación, carga, analítica y dashboard no requieren cambios.

---

## ¿Por qué este proyecto?

Construido para demostrar **habilidades de extremo a extremo en ingeniería de datos en un escenario realista y no trivial** — una pieza de portafolio para roles de data engineering / data analysis / Python backend.

| Habilidad | Dónde aparece |
|---|---|
| Diseño de pipelines ETL | Arquitectura por fases: Extract → Transform → Consolidate → Load → Analytics |
| Calidad de datos | Detección de codificación, reparación de CSV malformados, normalización de email/fecha/género, manejo de NULL |
| Resolución de identidad | Matching de dos pasadas (email → nombre) con score de confianza y preservación de `UNMATCHED` |
| Patrones de diseño | Clase base abstracta (`BaseExtractor`), patrón strategy (dedup por fuente), dependency inversion (`DataProvider`) |
| Modelado relacional | Esquema SQLite normalizado (3 tablas) con auditoría y conteos de actividad |
| Modelado analítico | Capa de KPIs con dimensiones geográficas / demográficas / de comportamiento, resultado serializable a JSON |
| Desarrollo de dashboards | Streamlit + Plotly con filtros, tabla interactiva, export CSV, mapeo dinámico de colores |
| Disciplina de testing | 81 tests automatizados en 8 scripts de verificación independientes |
| Pensamiento de producción | Cargas idempotentes, rotación de logs, auditoría de ejecuciones, scheduling daemon, degradación elegante |
| Build y empaquetado | Distribución standalone con Nuitka + launcher Tkinter + ZIP opcional |

---

## Características

### Ingeniería de datos
- **Extracción multi-fuente** — subclases modulares de `BaseExtractor` por fuente; reparación de CSV que arregla exportaciones multilínea malformadas *antes* de que el parser las vea.
- **Detección robusta de I/O** — detección automática de codificación (`utf-8-sig` → `latin-1`) y de delimitador (`coma`, `punto y coma`, `pipe`, `tab`).
- **Transformación por fuente** — normalización de email/fecha/género, scoring de calidad y estrategias de deduplicación *específicas por fuente*.
- **Resolución de identidad de dos pasadas** — join por email exacto (confianza ALTA), luego join por nombre normalizado (confianza BAJA); las filas no coincidentes se preservan, no se descartan.
- **Persistencia idempotente** — carga `DELETE + INSERT` a SQLite, por lo que cada ejecución produce una salida idéntica.

### Analítica y visualización
- **Capa de KPIs** (`scripts/analytics.py`) — calcula `total_usuarios`, conteos de participación, tasa de asistencia, distribuciones geográficas y demográficas, desglose de solapamiento entre fuentes y distribución de confianza — todo en un `AnalyticsResult` serializable a JSON.
- **Dashboard interactivo** — Streamlit + Plotly: tarjetas KPI, gráficos, tabla de datos buscable/filtrable con export a CSV, mapeo dinámico de colores para dimensiones categóricas.
- **UI independiente del almacenamiento** — la abstracción `DataProvider` aísla el dashboard de SQLite vs. CSV; cambiar de backend implica implementar una interfaz.

### Producción y operación
- **Auditoría de ejecuciones** — cada corrida queda registrada en la tabla `etl_runs` (duraciones, conteos, warnings, estado).
- **Rotación de logs** — 5 MB por archivo, 5 backups, UTF-8.
- **Scheduling daemon** — ejecutar el pipeline cada N minutos con la librería `schedule`.
- **Degradación elegante** — una fuente que falla nunca aborta el pipeline; cada fase reporta su propio resultado.

---

## Arquitectura

```
┌───────────────────────────────────────────────────────────────┐
│                          data/raw/*.csv                        │
│   registro_rcv.csv  talleres.csv  historial_analizado.csv      │
│   consolidado_asistencia.csv                                   │
└──────────────┬──────────────┬──────────────┬──────────────┬───┘
               ▼              ▼              ▼              ▼
        ┌─────────────────────────────────────────────────────────┐
        │                      EXTRACT (×4)                       │
        │   detección de encoding + delimitador · reparación CSV  │
        │   mapeo de columnas → snake_case                        │
        └──────────────────────────────┬──────────────────────────┘
                                       ▼
        ┌─────────────────────────────────────────────────────────┐
        │                      TRANSFORM (×4)                     │
        │   normalización email / fecha / género · score calidad  │
        │   estrategia de deduplicación por fuente                │
        └──────────────────────────────┬──────────────────────────┘
                                       ▼
        ┌─────────────────────────────────────────────────────────┐
        │                       CONSOLIDATE (1×)                  │
        │   pasada 1: email  → confianza ALTA                    │
        │   pasada 2: nombre → confianza BAJA                    │
        │   flags de participación · conteos · UNMATCHED          │
        └──────────────┬──────────────────────┬───────────────────┘
                       ▼                      ▼
        ┌────────────────────────┐   ┌────────────────────────────┐
        │          LOAD          │   │         ANALYTICS          │
        │  SQLite (idempotente)  │   │  KPIs · distribuciones     │
        │  export CSV maestro    │   │  resultado JSON-serializable│
        │  fila etl_runs        │   │                            │
        └───────────┬────────────┘   └─────────────┬──────────────┘
                    ▼                              ▼
        ┌──────────────────────────────────────────────────────────┐
        │    database/deficit_cero.db  +  DASHBOARD STREAMLIT      │
        └──────────────────────────────────────────────────────────┘
```

### Las 5 fases del pipeline

| Fase | Módulo | Responsabilidad |
|---|---|---|
| **Extract** | `scripts/extractors/*` | Leer CSV, detectar encoding/delimitador, reparar campos multilínea, aplicar mapeo de columnas |
| **Transform** | `scripts/transform.py` | Normalizar emails/fechas/categóricas, validar calidad, deduplicar por fuente |
| **Consolidate** | `scripts/consolidate.py` | Matching de dos pasadas, flags, conteos de actividad |
| **Load** | `scripts/load.py` | Persistencia idempotente SQLite, export CSV, auditoría |
| **Analytics** | `scripts/analytics.py` | Calcular KPIs y distribuciones consumidas por el dashboard |

### Esquema SQLite (3 tablas)

| Tabla | Propósito |
|---|---|
| `usuarios_master` | Una fila por usuario (clave email): demografía, geografía, situación, flags de participación, tasa de asistencia, confianza del match, proveedor de origen |
| `talleres_asistencias` | Detalle por asistencia (registros granulares de sesiones de taller) |
| `etl_runs` | Auditoría de ejecuciones: timestamps, conteos, duración, warnings, estado |

---

## Inicio rápido (demo local)

**Requisitos:** Python 3.10+ · Windows / macOS / Linux

### 1. Instalación

```bash
git clone https://github.com/your-username/unified-data-insights-platform.git
cd unified-data-insights-platform

python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
```

### 2. Obtener los datos demo

`main.py` lee sus fuentes desde `data/raw/*.csv`. Esos archivos están **en gitignore** (los archivos reales de producción nunca entran al repo), por lo que en un clon limpio debes cargar primero los fixtures **demo sintéticos** commiteados:

```bash
# Copiar los fixtures demo a data/raw/ con los nombres exactos que espera el pipeline
copy data\raw\samples\registro_rcv_dummy.csv        data\raw\registro_rcv.csv
copy data\raw\samples\talleres_dummy.csv            data\raw\talleres.csv
copy data\raw\samples\historial_analizado_dummy.csv data\raw\historial_analizado.csv
copy data\raw\samples\consolidado_asistencia_dummy.csv data\raw\consolidado_asistencia.csv
```

> Los fixtures `*_dummy.csv` de `data/raw/samples/` tienen la **misma estructura que producción pero totalmente anónimos** y reproducen los mismos KPIs del dashboard que los datos reales (≈52.020 usuarios, 8.763 inscritos a talleres, 3.150 asistencias, 1.196 usuarios de chatbot).

### 3. Ejecutar el pipeline

```bash
python main.py              # correr una vez (Extract → Transform → Consolidate → Load → Analytics)
```

### 4. Lanzar el dashboard

```bash
streamlit run dashboard/app.py
```

Se abre en **http://localhost:8501**. El dashboard lee desde SQLite y cae al CSV procesado si no está disponible.

---

## Uso

### Modos del pipeline

```bash
python main.py                          # correr una vez y terminar
python main.py --once                   # alias del anterior

python main.py --schedule 30            # modo daemon: cada 30 minutos
python main.py --schedule 60 --now      # correr ahora y luego cada 60 minutos
```

### Dashboard
- **Tarjetas KPI** — total de usuarios, registrados, inscritos a talleres, asistencias, usuarios chatbot, solapamiento multi-fuente.
- **Gráficos** — distribuciones por género, situación habitacional, región/comuna, solapamiento de fuentes, timeline de registros.
- **Tabla de datos** — buscable, filtrable, exportable a CSV.
- **Desglose de confianza** — match HIGH vs LOW, expuesto para auditoría downstream.

### Fuentes

| Fuente | Extractor | Archivo |
|---|---|---|
| Registro web | `RegistroExtractor` | `registro_rcv.csv` |
| Inscripciones a talleres (formularios) | `TalleresExtractor` | `talleres.csv` |
| Conversaciones de chatbot | `MingaExtractor` | `historial_analizado.csv` |
| Asistencia a talleres | `AsistenciaTalleresExtractor` | `consolidado_asistencia.csv` |

---

## Salidas del pipeline

| Artefacto | Ruta | Descripción |
|---|---|---|
| Base de datos SQLite | `database/deficit_cero.db` (WAL) | `usuarios_master`, `talleres_asistencias`, `etl_runs` |
| CSV consolidado | `data/processed/usuarios_master.csv` | Maestro completo de usuarios, UTF-8 BOM |
| Log de ejecución | `logs/etl_YYYYMMDD.log` | Conteos por paso, scores de calidad, warnings |

---

## Tests y verificación

Scripts de verificación standalone e independientes (no pytest) — cada fase es verificable por separado desde la raíz del proyecto, con salida en colores ANSI:

```bash
python verify_phase2.py                 # Extractors            — 5 tests
python verify_phase3.py                 # Transform             — 8 tests
python verify_phase4.py                 # Consolidate           — 10 tests
python verify_phase5.py                 # Load + SQLite         — 10 tests
python verify_phase6.py                 # Full pipeline         — 10 tests
python verify_analytics.py              # Analytics             — 9 tests
python verify_phase7.py                 # Dashboard             — 9 tests
python verify_asistencia_extractor.py   # Extractor asistencia  — 10 tests
```

**81 tests en total** — todos con: `for f in verify_*.py; do python $f; done`

---

## Desafíos de ingeniería

Los problemas no triviales que este proyecto tuvo que resolver — el tipo de problemas que solo aparecen con datos reales.

**Exportaciones CSV malformadas de sistemas basados en formularios**
Las plataformas ExpressionEngine y de chatbot exportan campos de texto libre con saltos de línea literales dentro de celdas entrecomilladas. Los parsers estándar de pandas fallan con `Error tokenizing data: Expected N fields, saw M`. La solución es una capa de reparación pre-pandas en `BaseExtractor` que detecta los límites de registro "votando" por la forma del primer campo entre líneas candidatas, fusiona las líneas continuadas en un único registro lógico y neutraliza comillas internas sin corromper columnas adyacentes.

**Resolución de identidad entre fuentes sin una clave primaria compartida**
Las fuentes no comparten un identificador de usuario común. La capa de consolidación usa una estrategia de dos pasadas — join por email exacto (confianza ALTA), luego join por nombre normalizado (confianza BAJA). Los registros no coincidentes se preservan con un flag `UNMATCHED` en lugar de descartarse, para que la calidad de datos sea auditable downstream.

**Persistencia idempotente con registros clave-NULL**
UPSERT falla con filas que tienen NULL en la clave, porque SQLite permite múltiples NULLs en una columna UNIQUE — los conflictos nunca se detectan y los duplicados se acumulan entre corridas. La capa de carga usa **DELETE + INSERT**, garantizando una salida idéntica en cada ejecución.

**La deduplicación varía según la fuente**
Un usuario puede aparecer legítimamente varias veces en una fuente: múltiples inscripciones a talleres, múltiples conversaciones de chatbot, múltiples filas de asistencia. La deduplicación es por lo tanto *específica por fuente* — con clave en `formulario_entry_id` para talleres, y desactivada para fuentes multi-evento donde colapsar destruiría datos válidos.

---

## Decisiones de diseño

Racional completo en [docs/architecture.md](docs/architecture.md). Opciones clave de un vistazo:

- **DELETE + INSERT en vez de UPSERT** — evita la acumulación silenciosa de duplicados con registros clave-NULL.
- **Reparación CSV pre-pandas** — arregla comillas desbalanceadas antes de que el parser las vea, preservando la alineación de columnas.
- **Matching de dos pasadas con scores de confianza** — preserva las filas no coincidentes en vez de descartarlas, permitiendo análisis de calidad post-hoc.
- **Deduplicación específica por fuente** — una estrategia global colapsaría silenciosamente registros multi-evento legítimos.
- **Abstracción DataProvider** — migrar el dashboard de SQLite a PostgreSQL implica implementar una interfaz, no reescribir código de visualización.
- **Analítica como capa pura de lectura** — `scripts/analytics.py` nunca escribe; los consumidores (dashboard, futura API) leen un `AnalyticsResult` serializable a JSON.

---

## Implementación real

Este repo trae una implementación de inspiración productiva construida originalmente para una **organización chilena de advocacy por vivienda** (Déficit Cero), integrando un sistema de registro web, una plataforma de talleres basada en formularios, un chatbot de vivienda y exportaciones de asistencia en un maestro unificado de ~48.000 registros reales.

El repositorio incluye **datos sintéticos completamente anónimos** que replican esas distribuciones reales, de modo que el pipeline y el dashboard son 100% reproducibles sin exponer información privada.

Ver: [docs/case-study-deficit-cero.md](docs/case-study-deficit-cero.md)

---

## Estructura del proyecto

```
unified-data-insights-platform/
│
├── main.py                        # Punto de entrada del pipeline + CLI (once / daemon)
├── requirements.txt
├── README.md                      # Este archivo  (🇺🇸 English)
├── README_ES.md                   # Español       (🇨🇱 Spanish)
│
├── config/
│   ├── settings.py                # Rutas, encodings, constantes globales
│   └── mappings.py                # Mapeos de columnas + normalizaciones
│
├── scripts/                       # Fases del pipeline
│   ├── extractors/                # Base + 4 extractores de fuente (+ Zoom legacy)
│   │   ├── base_extractor.py      # Reparación CSV, detección de encoding/delimitador
│   │   ├── registro_extractor.py
│   │   ├── talleres_extractor.py
│   │   ├── minga_extractor.py
│   │   └── asistencia_talleres_extractor.py
│   ├── transform.py               # Normalización, validación, dedup por fuente
│   ├── consolidate.py             # Matching de identidad de dos pasadas
│   ├── load.py                    # Persistencia SQLite + export CSV + auditoría
│   ├── analytics.py               # Capa de KPIs / distribuciones
│   ├── scheduler.py               # Wrapper de scheduling daemon
│   └── utils.py                   # Logger y helpers compartidos
│
├── dashboard/
│   └── app.py                     # Dashboard Streamlit (provider SQLite / CSV)
│
├── database/
│   └── deficit_cero.db            # Base de datos SQLite (generada por el pipeline)
│
├── data/
│   ├── raw/                       # CSVs fuente (gitignore; nunca modificados)
│   ├── raw/samples/               # Fixtures demo anónimos (commiteados)
│   └── processed/
│       └── usuarios_master.csv    # Salida consolidada (UTF-8 BOM)
│
├── logs/
│   └── etl_YYYYMMDD.log           # Log rotativo del pipeline
│
├── docs/                          # Arquitectura, diccionario de datos, caso de estudio
│
├── build/
│   └── build_release.ps1          # Empaquetado de release (Nuitka + PyArmor)
│
└── verify_*.py                    # 8 scripts de verificación standalone (81 tests)
```

---

## Roadmap

| Estado | Ítem |
|---|---|
| ✅ Hecho | ETL de cuatro fuentes con estrategias de extracción/transformación por fuente |
| ✅ Hecho | Resolución de identidad de dos pasadas con score de confianza |
| ✅ Hecho | Persistencia idempotente SQLite con auditoría de ejecuciones |
| ✅ Hecho | Capa de KPIs + dashboard Streamlit con abstracción DataProvider |
| ✅ Hecho | 81 tests automatizados en 8 scripts de verificación |
| ✅ Hecho | Build standalone con Nuitka + launcher Tkinter |
| ✅ Hecho | Fixtures demo anónimos que reproducen los KPIs reales |
| 🔄 Planeado | Auto-consolidación de múltiples archivos de exportación desde un directorio vigilado |
| 🔄 Planeado | GitHub Actions para ejecución programada del pipeline |
| 🔄 Planeado | Capa de API REST sobre el módulo de analítica |
| 🔄 Planeado | Backend PostgreSQL para concurrencia y volúmenes 100K+ |

---

## Licencia

MIT — ver el repositorio para más detalles.