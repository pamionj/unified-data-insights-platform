# Déficit Cero — Community Data Pipeline

Sistema ETL de consolidación de datos de usuarios para **Déficit Cero / Red por la Vivienda y la Ciudad**, organización chilena de advocacy habitacional.

Integra cuatro fuentes de datos heterogéneas en un master de usuarios unificado, con dashboard analítico y auditoría completa de cada ejecución.

---

## Tabla de contenidos

- [Contexto del proyecto](#contexto-del-proyecto)
- [Arquitectura del sistema](#arquitectura-del-sistema)
- [Fuentes de datos](#fuentes-de-datos)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Instalación](#instalación)
- [Uso](#uso)
- [Salidas del pipeline](#salidas-del-pipeline)
- [Algoritmo de matching](#algoritmo-de-matching)
- [Dashboard](#dashboard)
- [Verificación y tests](#verificación-y-tests)
- [Decisiones de diseño](#decisiones-de-diseño)
- [Mejoras futuras](#mejoras-futuras)

---

## Contexto del proyecto

Déficit Cero opera múltiples canales de contacto con usuarios: un registro web propio, talleres presenciales/virtuales gestionados desde ExpressionEngine, un chatbot de asesoría habitacional (Minga), y un consolidado de asistencia a talleres. Cada canal genera sus propios datos en formatos distintos, sin integración entre sí.

> **Nota histórica:** El sistema original utilizaba exports de Zoom (`zoom_asistencia.csv`) como fuente de asistencia. Desde la versión 1.1.0, esta fuente fue reemplazada por `consolidado_asistencia.csv`, un consolidado manual de múltiples exports de Zoom que incluye asistentes tanto externos como registrados.

Este pipeline unifica esas cuatro fuentes en una tabla maestra de usuarios (`usuarios_master`) que permite responder preguntas como:

- ¿Cuántos usuarios del registro web se inscribieron a al menos un taller?
- ¿Qué porcentaje de inscritos a talleres efectivamente asistió?
- ¿Qué perfil habitacional tienen los usuarios que usaron el chatbot Minga?
- ¿Cuántos asistentes a talleres no están registrados en la plataforma?

---

## Arquitectura del sistema

```
data/raw/
  registro_rcv.csv          ─┐
  talleres.csv               ├── Extract ──► Transform ──► Consolidate ──► Load
  historial_analizado.csv    ├── (×4)        (×4)          (1 master)      (SQLite + CSV)
  consolidado_asistencia.csv─┘
                                                                              │
                                                                              ▼
                                                                        Analytics
                                                                              │
                                                                              ▼
                                                                        Dashboard
                                                                    (Streamlit)
```

**Flujo de ejecución:**

1. **Extract** — cada extractor lee su CSV, detecta encoding y delimitador, repara campos de texto libre multilínea (común en exports de ExpressionEngine), y aplica el mapeo de columnas definido en `config/mappings.py`.

2. **Transform** — normalización de emails, fechas y género; validación de calidad; deduplicación específica por fuente.

3. **Consolidate** — matching por email (HIGH confidence) y por nombre+apellido (LOW confidence) entre fuentes; cálculo de flags de participación y conteos de actividad.

4. **Load** — persistencia idempotente (DELETE + INSERT) en SQLite; exportación del CSV consolidado; registro de auditoría en `etl_runs`.

5. **Analytics** — cálculo de KPIs sobre el master; disponible tanto para el dashboard como para consultas directas.

---

## Fuentes de datos

| Fuente | Archivo | Email | Descripción |
|---|---|---|---|
| Registro Web | `registro_rcv.csv` | `EMAIL` | Registro principal de la plataforma. Fuente dominante (~48.000 usuarios). |
| Talleres | `talleres.csv` | `MEMBER_EMAIL` | Inscripciones a talleres desde ExpressionEngine. Un usuario puede inscribirse a múltiples talleres. Export multilínea: el campo `PREGUNTAS - RESPUESTAS` ocupa varias líneas por inscripción. |
| Minga (chatbot) | `historial_analizado.csv` | `email_usuario` | Conversaciones analizadas del chatbot de asesoría habitacional. Contiene perfil financiero del usuario (RSH, ingresos, ahorro, subsidio recomendado). |
| Asistencia | `consolidado_asistencia.csv` | `Correo electrónico` | Consolidado de asistencia a talleres (reemplaza el export de Zoom desde v1.1.0). Incluye asistentes externos sin registro previo. |

**Flujo real del negocio:**

```
Registro Web (punto de entrada principal)
    │
    ├── Talleres (inscritos con cuenta en la plataforma)
    │
    └── Minga (requiere cuenta previa en la plataforma)

Asistencia (puede incluir asistentes externos sin registro previo)
```

---

## Estructura del repositorio

```
unified-data-insights-platform/
│
├── main.py                        # Punto de entrada del pipeline
├── requirements.txt
├── README.md
│
├── config/
│   ├── settings.py                # Rutas, encodings, constantes globales
│   └── mappings.py                # Mapeo de columnas, normalización de género y fechas
│
├── scripts/
│   ├── extractors/
│   │   ├── base_extractor.py      # Clase base: lectura, reparación de CSV, mapeo
│   │   ├── registro_extractor.py
│   │   ├── talleres_extractor.py
│   │   ├── minga_extractor.py
│   │   └── zoom_extractor.py
│   ├── transform.py               # Normalización, validación y deduplicación
│   ├── consolidate.py             # Matching multi-fuente y construcción del master
│   ├── load.py                    # Persistencia en SQLite y CSV
│   ├── analytics.py               # Cálculo de KPIs y métricas
│   ├── scheduler.py               # Ejecución periódica (modo daemon)
│   └── utils.py                   # Logger y helpers compartidos
│
├── dashboard/
│   └── app.py                     # Dashboard Streamlit con DataProvider
│
├── database/
│   └── deficit_cero.db            # SQLite (generado por el pipeline)
│
├── data/
│   ├── raw/                       # CSV originales (no modificados por el pipeline)
│   └── processed/
│       └── usuarios_master.csv    # Salida consolidada
│
├── logs/
│   └── etl_YYYYMMDD.log           # Log rotativo por día
│
└── verify_phase*.py               # Scripts de verificación por fase
```

---

## Instalación

**Requisitos:** Python 3.10+ · Windows / macOS / Linux

```bash
# 1. Clonar el repositorio
git clone https://github.com/tu-usuario/unified-data-insights-platform.git
cd unified-data-insights-platform

# 2. Crear y activar entorno virtual
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS / Linux

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Colocar los archivos CSV en data/raw/
#    (ver sección "Fuentes de datos" para los nombres exactos)
```

---

## Uso

### Ejecutar el pipeline una vez

```bash
python main.py
```

Salida esperada:

```
--------------------------------------------------
  Déficit Cero — Community Data Pipeline
  Estado: OK
--------------------------------------------------
  Usuarios en master:    48094
  Filas DB (master):     48094
  Filas DB (asistencia):  294
  Filas CSV:             48094
  Run ID (etl_runs):        42
  Duracion:              38.7s
  Analytics generados:   Si
--------------------------------------------------
```

### Modo programado (daemon)

```bash
python main.py --schedule 60         # cada 60 minutos
python main.py --schedule 30 --now   # ejecutar ahora y luego cada 30 min
```

### Ver el dashboard

```bash
streamlit run dashboard/app.py
```

Abre el navegador en `http://localhost:8501`.

---

## Salidas del pipeline

Cada ejecución genera o actualiza exactamente estos artefactos:

### Base de datos SQLite (`database/deficit_cero.db`)

| Tabla | Descripción |
|---|---|
| `usuarios_master` | Un registro por usuario. Columnas de todas las fuentes, flags de participación y conteos de actividad. |
| `talleres_asistencias` | Un registro por asistencia a taller. Permite auditar participación granular (taller × email × fecha). |
| `etl_runs` | Un registro por ejecución del pipeline. Auditoría de métricas, duración y estado. |

### CSV consolidado (`data/processed/usuarios_master.csv`)

Exportación completa de `usuarios_master` en UTF-8 con BOM (compatible con Excel en español).

### Log del run (`logs/etl_YYYYMMDD.log`)

Log rotativo con cada paso del pipeline: filas por etapa, quality scores, warnings y errores.

---

## Algoritmo de matching

La consolidación cruza las cuatro fuentes en dos pasos:

**Paso 1 — Matching por email (HIGH confidence)**

Join exacto sobre el campo `email` normalizado (lowercase, strip). Cubre el ~90% de los casos. Aplica entre todas las fuentes.

**Paso 2 — Matching por nombre+apellido (LOW confidence)**

Para registros sin email válido o sin coincidencia en el paso 1. Normaliza nombre y apellido (sin tildes, lowercase, strip) y cruza por par. Los registros resultantes se marcan `match_confidence = 'LOW'` en el master.

**Registros sin coincidencia**

Usuarios presentes en una fuente secundaria (Asistencia, Talleres, Minga) pero sin correspondencia en Registro Web se incluyen en el master con `match_confidence = 'UNMATCHED'`. Esto cubre el caso de asistentes externos a talleres que nunca se registraron en la plataforma.

**Flags resultantes por usuario**

| Columna | Fuente | Descripción |
|---|---|---|
| `tiene_registro_web` | Registro | True si existe en registro_rcv |
| `inscrito_taller` | Talleres | True si tiene al menos una inscripción |
| `asistio_taller` | Asistencia | True si aparece en al menos una asistencia |
| `uso_minga` | Minga | True si tiene al menos una conversación |
| `num_talleres_inscritos` | Talleres | Conteo de inscripciones únicas |
| `num_talleres_asistidos` | Asistencia | Conteo de asistencias únicas |
| `tasa_asistencia` | Talleres + Asistencia | `asistidos / inscritos` |

---

## Dashboard

El dashboard Streamlit implementa un patrón `DataProvider` que abstrae la fuente de datos:

- `SQLiteDataProvider` — lee desde `database/deficit_cero.db` (default si existe)
- `CSVDataProvider` — lee desde `data/processed/usuarios_master.csv` (fallback)

**Visualizaciones disponibles:**

- KPI cards: usuarios totales, inscritos, asistidos, usuarios Minga, comunas únicas
- Distribución territorial por región y top comunas
- Distribución por fuente de datos (donut chart)
- Comparativa inscripción vs asistencia a talleres (4 segmentos)
- Distribución por situación habitacional
- Evolución temporal de registros (línea + barras)
- Distribución por género
- Tabla interactiva con filtros por región, fuente y búsqueda de texto
- Exportación a CSV desde el explorador de datos

**Filtros del sidebar:** región, fuente de datos, búsqueda por email o nombre.

---

## Verificación y tests

El proyecto incluye scripts de verificación automatizados por fase:

```bash
python verify_phase2.py     # Extractores (7 tests)
python verify_phase3.py     # Transform (8 tests)
python verify_phase4.py     # Consolidate (10 tests)
python verify_phase5.py     # Load + SQLite (10 tests)
python verify_phase6.py     # Pipeline completo (10 tests)
python verify_analytics.py  # Analytics (9 tests)
python verify_phase7.py     # Dashboard (9 tests)
```

Resultado esperado con datos en `data/raw/`: todos los tests en verde.

---

## Decisiones de diseño

**Idempotencia por DELETE + INSERT**
Cada ejecución del pipeline vacía y recarga las tablas `usuarios_master` y `talleres_asistencias`. Esto garantiza que ejecutar el pipeline dos veces con los mismos datos produce exactamente el mismo resultado, sin duplicados acumulados. La tabla `etl_runs` es la excepción: acumula un registro por ejecución para auditoría.

**Reparación de CSV multilínea en el extractor base**
Los exports de ExpressionEngine (talleres) y del chatbot Minga generan campos de texto libre con saltos de línea dentro de una celda, lo que produce comillas sin cerrar en el CSV físico. El `BaseExtractor` detecta este patrón línea por línea, identifica el inicio de cada registro real por la "forma" del campo ID (numérico, alfanumérico o prefijo+número como ULIDs), y fusiona las líneas de continuación antes de pasarlas a pandas. Los archivos sin este problema (Zoom, Registro) omiten el proceso de reparación por completo.

**DataProvider en el dashboard**
La capa de visualización no accede directamente a SQLite ni al CSV. En su lugar, `DataProvider` es una clase abstracta con implementaciones concretas intercambiables. Esto permite agregar un `PostgreSQLDataProvider` o un `GoogleSheetsDataProvider` en el futuro sin modificar ningún componente de visualización.

**Separación estricta de `data/raw/`**
El pipeline nunca escribe en `data/raw/`. Los CSV originales son inmutables desde la perspectiva del sistema. Todas las salidas van a `data/processed/`, `database/` o `logs/`.

**Matching en dos pasos con niveles de confianza**
El campo `match_confidence` en el master (`HIGH`, `LOW`, `UNMATCHED`) permite al equipo filtrar análisis por calidad del dato. Un dashboard o reporte puede optar por excluir registros `LOW` si necesita alta precisión, o incluirlos si necesita cobertura máxima.

---

## Mejoras futuras

**Matching por MEMBER_ID entre Registro y Talleres**
Ambas fuentes comparten el campo `MEMBER_ID`. Implementarlo como criterio primario de matching (antes que el email) recuperaría usuarios que cambiaron su email entre el registro y la inscripción al taller, mejorando la cobertura estimada de ~89% a ~95%.

**Soporte para múltiples archivos de asistencia (histórico)**
En versiones anteriores a v1.1.0, el sistema procesaba un único `zoom_asistencia.csv` consolidado manualmente entre 25 y 30 exports de Zoom. Desde v1.1.0, la fuente `consolidado_asistencia.csv` ya integra estos datos de forma centralizada. Esta mejora fue implementada como parte de la migración.

**Migración a PostgreSQL**
Con volúmenes superiores a 100.000 usuarios o con necesidad de acceso concurrente desde múltiples procesos, SQLite se sustituye por PostgreSQL. El `DataProvider` del dashboard hace esta migración transparente para la capa de visualización.

**Scheduler en producción**
El modo `--schedule` usa la librería `schedule` en proceso. Para producción se recomienda reemplazarlo por una tarea de GitHub Actions, Windows Task Scheduler, o cron en Linux, delegando la gestión del ciclo de vida del proceso al sistema operativo.
