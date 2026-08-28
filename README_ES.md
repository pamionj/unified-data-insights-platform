🌎 Idioma: 🇺🇸 [English](README.md) | 🇨🇱 Español

# Unified Data Insights Platform

**Pipeline ETL de nivel producción + dashboard interactivo de analítica** Consolida 4 fuentes heterogéneas (≈52.000 registros) en un maestro de usuarios unificado y sin duplicados, y luego transforma esos datos en información accionable mediante un dashboard en Streamlit.

---

### 🚀 Demo en vivo

**Prueba el dashboard desplegado:** [Unified Data Insights Platform — Streamlit](https://unified-data-insights-platform.streamlit.app/)

La demo en vivo utiliza datos completamente sintéticos, modelados a partir de la estructura y las distribuciones del conjunto de datos original utilizado en producción.

---

## Tabla de contenidos

- [Descripción general](#descripción-general)
- [¿Por qué este proyecto?](#por-qué-este-proyecto)
- [Características](#características)
- [Arquitectura](#arquitectura)
- [Inicio rápido (demo local)](#inicio-rápido-demo-local)
- [Uso](#uso)
- [Resultados del pipeline](#resultados-del-pipeline)
- [Gobernanza y calidad de datos](#gobernanza-y-calidad-de-datos)
- [Desafíos de ingeniería](#desafíos-de-ingeniería)
- [Decisiones de diseño](#decisiones-de-diseño)
- [Implementación en el mundo real](#implementación-en-el-mundo-real)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Roadmap](#roadmap)
- [Licencia](#licencia)

---

## Descripción general

Las organizaciones acumulan datos de usuarios en sistemas desconectados: plataformas de registro web, herramientas de talleres basadas en formularios, servicios de mensajería/chatbots y exportaciones de videoconferencias. Cada fuente tiene sus propias **particularidades de esquema, codificación, delimitador y exportación**. Unirlas manualmente es propenso a errores y no escala.

**Unified Data Insights Platform** resuelve este problema mediante un pipeline ETL modular de cinco fases:

```text
Extract → Transform → Consolidate → Load → Analytics
```

Ingiere cuatro fuentes CSV heterogéneas, resuelve la identidad entre fuentes mediante un **algoritmo de matching de dos pasadas con niveles de confianza**, y entrega un maestro de usuarios limpio y unificado tanto a una **base de datos SQLite** como a un **dashboard interactivo en Streamlit**.

Construido sobre **datos sintéticos de demostración que reproducen fielmente las distribuciones de un entorno real de producción** (≈52.000 usuarios distribuidos en cuatro fuentes), aborda problemas de calidad de datos que rara vez aparecen en tutoriales: campos de texto multilínea que rompen los parsers CSV estándar, codificaciones inconsistentes, columnas clave con valores NULL y reglas de deduplicación que deben variar por fuente debido a requisitos legítimos del negocio.

> **Diseñado para ser reutilizable.** Agregar una nueva fuente de datos requiere únicamente una nueva subclase de `BaseExtractor` junto con su mapeo de columnas en `config/mappings.py`. Las capas de transformación, consolidación, carga, analítica y dashboard no requieren modificaciones.

---

## ¿Por qué este proyecto?

Construido para demostrar habilidades de **Data Engineering de extremo a extremo a través de una implementación real**: desde la ingesta de fuentes heterogéneas y los desafíos de calidad de datos hasta un pipeline ETL desplegado en producción y un dashboard interactivo de analítica.

El sistema fue desarrollado para resolver un problema organizacional real y permaneció operativo después de su despliegue, consolidando fuentes de datos previamente fragmentadas en un flujo de trabajo analítico unificado y reproducible.

Actualmente funciona como un caso de estudio para mi portafolio orientado a roles de Data Engineering, Data Analytics y Python Backend, mientras que el repositorio público proporciona una versión completamente reproducible basada en datos sintéticos anonimizados.

| Habilidad | Dónde aparece |
| --------- | ------------- |
| Diseño de pipelines ETL | Arquitectura por fases: Extract → Transform → Consolidate → Load → Analytics |
| Gestión de calidad de datos | Detección de codificación, reparación de CSV malformados, normalización de email/fecha/género, manejo de NULL |
| Resolución de identidad | Matching de dos pasadas (email → nombre) con niveles de confianza y preservación de `UNMATCHED` |
| Patrones de diseño de software | Clase base abstracta (`BaseExtractor`), patrón Strategy para deduplicación por fuente e inversión de dependencias (`DataProvider`) |
| Modelado relacional | Esquema SQLite normalizado de 3 tablas con trazabilidad de ejecuciones y conteos de actividad |
| Modelado analítico | Capa de KPIs con dimensiones geográficas, demográficas y de comportamiento, con resultados serializables a JSON |
| Desarrollo de dashboards | Streamlit + Plotly con filtros, tabla interactiva, exportación CSV y asignación dinámica de colores |
| Gobernanza de datos | Procedencia de las fuentes, confianza de identidad, preservación de registros no vinculados, auditoría de ejecuciones y cargas reproducibles |
| Consideraciones de producción | Cargas idempotentes, rotación de logs, auditoría de ejecuciones, programación como daemon y degradación controlada |
| Build y empaquetado | Distribución standalone con Nuitka + launcher en Tkinter + release opcional en ZIP |

---

## Características

### Ingeniería de Datos

- **Extracción multi-fuente** — subclases modulares de `BaseExtractor` por fuente; reparación de CSV que corrige exportaciones multilínea malformadas *antes* de que el parser las procese.
- **Detección robusta de I/O** — detección automática de codificación (`utf-8-sig` → `latin-1`) y delimitador (`comma`, `semicolon`, `pipe`, `tab`).
- **Transformación por fuente** — normalización de email/fecha/género, evaluación de calidad y estrategias de deduplicación *específicas por fuente*.
- **Resolución de identidad en dos pasadas** — unión exacta por email (confianza HIGH), seguida de matching por nombre normalizado (confianza LOW); los registros no vinculados se preservan.
- **Persistencia idempotente** — carga mediante `DELETE + INSERT` en SQLite, de modo que cada ejecución produzca un resultado determinista.

### Analítica y visualización

- **Capa de KPIs** (`scripts/analytics.py`) — calcula `total_usuarios`, conteos de participación, tasa de asistencia, distribuciones geográficas y demográficas, superposición entre fuentes y distribución de confianza, todo mediante un `AnalyticsResult` serializable a JSON.
- **Dashboard interactivo** — Streamlit + Plotly: tarjetas KPI, gráficos, tabla de datos con búsqueda y filtros, exportación CSV y asignación dinámica de colores para dimensiones categóricas.
- **Interfaz independiente del almacenamiento** — la abstracción `DataProvider` desacopla el dashboard de SQLite y CSV; cambiar de backend requiere implementar una interfaz, no reescribir las visualizaciones.

### Producción y operaciones

- **Auditoría de ejecuciones** — cada ejecución queda registrada en la tabla `etl_runs` con duración, conteos, advertencias y estado.
- **Rotación de logs** — 5 MB por archivo, 5 respaldos y codificación UTF-8.
- **Programación como daemon** — ejecución automática del pipeline cada N minutos mediante la librería `schedule`.
- **Degradación controlada** — una fuente que falla no aborta todo el pipeline; cada fase reporta su propio resultado.

---

## Arquitectura

```text
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
        │   normalización de email / fecha / género · calidad     │
        │   estrategia de deduplicación por fuente                │
        └──────────────────────────────┬──────────────────────────┘
                                       ▼
        ┌─────────────────────────────────────────────────────────┐
        │                       CONSOLIDATE (1×)                  │
        │   pasada 1: email  → confianza HIGH                     │
        │   pasada 2: nombre → confianza LOW                      │
        │   flags de participación · conteos · UNMATCHED          │
        └──────────────┬──────────────────────┬───────────────────┘
                       ▼                      ▼
        ┌────────────────────────┐   ┌────────────────────────────┐
        │          LOAD          │   │         ANALYTICS          │
        │  SQLite (idempotente)  │   │  KPIs · distribuciones     │
        │  exportación CSV master│   │  resultado serializable    │
        │  auditoría etl_runs    │   │                            │
        └───────────┬────────────┘   └─────────────┬──────────────┘
                    ▼                              ▼
        ┌──────────────────────────────────────────────────────────┐
        │         database/deficit_cero.db + STREAMLIT DASHBOARD   │
        └──────────────────────────────────────────────────────────┘
```

### Las 5 fases del pipeline

| Fase | Módulo | Responsabilidad |
| ---- | ------ | --------------- |
| **Extract** | `scripts/extractors/*` | Leer CSV, detectar codificación/delimitador, reparar campos multilínea y aplicar el mapeo de columnas |
| **Transform** | `scripts/transform.py` | Normalizar emails/fechas/categóricos, validar calidad y deduplicar por fuente |
| **Consolidate** | `scripts/consolidate.py` | Matching de dos pasadas entre fuentes, flags y conteos de actividad |
| **Load** | `scripts/load.py` | Persistencia idempotente en SQLite, exportación CSV y auditoría de ejecución |
| **Analytics** | `scripts/analytics.py` | Calcular KPIs y distribuciones consumidas por el dashboard |

### Esquema SQLite (3 tablas)

| Tabla | Propósito |
| ----- | --------- |
| `usuarios_master` | Una fila por usuario: demografía, geografía, situación habitacional, flags de participación, tasa de asistencia, confianza del matching y procedencia de las fuentes |
| `talleres_asistencias` | Detalle de asistencia por registro (registros granulares de sesiones de talleres) |
| `etl_runs` | Auditoría de ejecuciones: timestamps, conteos, duración, advertencias y estado |

---

## Inicio rápido (demo local)

**Requisitos:** Python 3.10+ · Windows / macOS / Linux

### 1. Instalar

```bash
git clone https://github.com/your-username/unified-data-insights-platform.git
cd unified-data-insights-platform

python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
```

### 2. Cargar los datos de demostración

`main.py` lee sus fuentes desde `data/raw/*.csv`. Estos archivos están **ignorados por Git** (los archivos privados de producción nunca ingresan al repositorio), por lo que después de un clone limpio debes cargar primero los fixtures de **datos sintéticos** incluidos:

```bash
# Copiar los fixtures de demostración a data/raw/ con los nombres exactos
# que espera el pipeline

Copy-Item data\raw\samples\consolidado_asistencia_dummy.csv data\raw\consolidado_asistencia.csv
Copy-Item data\raw\samples\historial_analizado_dummy.csv data\raw\historial_analizado.csv
Copy-Item data\raw\samples\registro_rcv_dummy.csv data\raw\registro_rcv.csv
Copy-Item data\raw\samples\talleres_dummy.csv data\raw\talleres.csv
```

> Los fixtures `*_dummy.csv` ubicados en `data/raw/samples/` son **idénticos a nivel de estructura de bytes** a la estructura utilizada en producción, pero contienen información completamente anónima. Reproducen los mismos KPIs del dashboard que los datos reales (≈52.020 usuarios, 8.763 inscripciones a talleres, 3.150 asistencias y 1.196 usuarios del chatbot).

### 3. Ejecutar el pipeline

```bash
python main.py              # Ejecutar una vez (Extract → Transform → Consolidate → Load → Analytics)
```

### 4. Iniciar el dashboard

```bash
streamlit run dashboard/app.py
```

Se abrirá en **http://localhost:8501**. El dashboard lee desde SQLite y utiliza el CSV procesado como fallback.

---

## Uso

### Modos del pipeline

```bash
python main.py                          # Ejecutar una vez y finalizar
python main.py --once                   # Alias del comando anterior

python main.py --schedule 30            # Modo daemon: ejecutar cada 30 minutos
python main.py --schedule 60 --now      # Ejecutar ahora y luego cada 60 minutos
```

### Dashboard

- **Tarjetas KPI** — total de usuarios, registros, inscripciones a talleres, asistencias, usuarios del chatbot y superposición entre fuentes.
- **Gráficos** — distribuciones por género, situación habitacional, región/comuna, superposición entre fuentes y línea de tiempo de registros.
- **Tabla de datos** — búsqueda, filtros y exportación a CSV.
- **Desglose de confianza** — confianza HIGH frente a LOW, expuesta para auditoría posterior.

### Fuentes

| Fuente | Extractor | Archivo |
| ------ | --------- | ------- |
| Registro web | `RegistroExtractor` | `registro_rcv.csv` |
| Inscripciones a talleres (basadas en formularios) | `TalleresExtractor` | `talleres.csv` |
| Conversaciones del chatbot | `MingaExtractor` | `historial_analizado.csv` |
| Asistencia a talleres | `AsistenciaTalleresExtractor` | `consolidado_asistencia.csv` |

---

## Resultados del pipeline

| Artefacto | Ruta | Descripción |
| --------- | ---- | ----------- |
| Base de datos SQLite | `database/deficit_cero.db` (WAL) | `usuarios_master`, `talleres_asistencias`, `etl_runs` |
| CSV consolidado | `data/processed/usuarios_master.csv` | Maestro completo de usuarios, UTF-8 BOM |
| Log de ejecución | `logs/etl_YYYYMMDD.log` | Conteos por etapa, puntuaciones de calidad y advertencias |

---

## Gobernanza y calidad de datos

La integración de datos solo es útil cuando el conjunto resultante es **trazable, reproducible y seguro para ser consumido por procesos posteriores**. Por ello, la plataforma trata la calidad de los datos como una preocupación de primer nivel a lo largo de todo el pipeline y no como una validación realizada únicamente al final.

| Aspecto de gobernanza | Implementación |
| --------------------- | -------------- |
| **Trazabilidad de fuentes** | Cada registro consolidado conserva información sobre su procedencia, permitiendo identificar qué fuentes contribuyeron a la información de un usuario. |
| **Resolución de identidad** | Los registros entre fuentes se vinculan mediante una estrategia de dos pasadas con niveles explícitos de confianza (`HIGH`, `LOW`, `UNMATCHED`) en lugar de forzar coincidencias inciertas. |
| **Normalización de datos** | Emails, fechas, valores categóricos, etiquetas de género y otros campos se normalizan de manera consistente antes de la consolidación. |
| **Deduplicación** | Las reglas de deduplicación se definen por fuente para distinguir duplicados reales de actividad legítima de múltiples eventos. |
| **Preservación de registros no vinculados** | Los registros que no pueden vincularse con suficiente confianza se preservan y se marcan explícitamente en lugar de descartarse silenciosamente. |
| **Auditoría de ejecuciones** | Las ejecuciones del pipeline se registran en la tabla `etl_runs` con estado, conteos de procesamiento, duración y advertencias. |
| **Cargas reproducibles** | La persistencia idempotente mediante `DELETE + INSERT` garantiza que ejecuciones repetidas del pipeline produzcan un estado determinista de la base de datos. |
| **Aislamiento de datos** | Los archivos fuente de producción permanecen fuera del repositorio público, mientras que la versión de portafolio utiliza fixtures sintéticos que preservan la estructura de la implementación real sin exponer información privada. |
| **Consistencia de esquema** | Los mapeos de columnas y las reglas de normalización se centralizan en `config/mappings.py`, reduciendo transformaciones implícitas distribuidas por el código. |

### Linaje de datos

La plataforma mantiene un linaje claro desde las fuentes operacionales hasta los resultados analíticos:

```text
Fuentes de datos
    │
    ├── Registros web
    ├── Inscripciones a talleres
    ├── Interacciones del chatbot
    └── Asistencia a talleres
            │
            ▼
         Extracción
            │
            ▼
       Normalización
            │
            ▼
  Deduplicación por fuente
            │
            ▼
   Resolución de identidad
      ├── Confianza HIGH
      ├── Confianza LOW
      └── UNMATCHED
            │
            ▼
   Maestro unificado de usuarios
            │
      ┌─────┴─────┐
      ▼           ▼
   SQLite      CSV Master
      │           │
      └─────┬─────┘
            ▼
       Analítica
            │
            ▼
   Dashboard en Streamlit
```

Este enfoque hace que la capa analítica sea **auditable por diseño**: los KPIs agregados pueden rastrearse hasta los registros consolidados, y los registros consolidados conservan la información necesaria para comprender cómo fueron producidos.

---

## Desafíos de ingeniería

Los problemas no triviales que este proyecto tuvo que resolver: aquellos que suelen aparecer únicamente al trabajar con datos reales.

**Exportaciones CSV malformadas provenientes de sistemas basados en formularios**

Las plataformas ExpressionEngine y de chatbot exportan campos de texto libre con saltos de línea literales dentro de celdas entrecomilladas. Los parsers estándar de pandas fallan con errores como `Error tokenizing data: Expected N fields, saw M`. La solución consiste en una capa de reparación previa a pandas dentro de `BaseExtractor`, que detecta los límites de registros mediante una especie de "votación" basada en la estructura del primer campo de las líneas candidatas, fusiona las líneas de continuación en un único registro lógico y neutraliza comillas internas sin corromper las columnas adyacentes.

**Resolución de identidad entre fuentes sin una clave primaria compartida**

Las fuentes no comparten un identificador común de usuario. La capa de consolidación utiliza una estrategia de dos pasadas: coincidencia exacta por email (confianza HIGH), seguida de coincidencia por nombre normalizado (confianza LOW). Los registros no vinculados se preservan con una marca `UNMATCHED` en lugar de descartarse silenciosamente, permitiendo auditar la calidad de los datos posteriormente.

**Persistencia idempotente con registros cuya clave es NULL**

UPSERT falla para registros con claves NULL, porque SQLite permite múltiples valores NULL en una columna UNIQUE: nunca se detectan conflictos y los duplicados se acumulan entre ejecuciones. La capa de carga utiliza **DELETE + INSERT**, garantizando resultados idénticos en cada ejecución.

**La estrategia de deduplicación varía según la fuente**

Un mismo usuario puede aparecer legítimamente varias veces dentro de una fuente: múltiples inscripciones a talleres, múltiples conversaciones en el chatbot o múltiples registros de asistencia. Por ello, la deduplicación es *específica por fuente*: se basa en `formulario_entry_id` para los talleres y se desactiva para fuentes de múltiples eventos donde consolidar filas destruiría actividad válida.

---

## Decisiones de diseño

La justificación completa se encuentra en [docs/architecture.md](docs/architecture.md). Algunas decisiones principales:

- **DELETE + INSERT en lugar de UPSERT** — evita la acumulación silenciosa de duplicados cuando existen claves NULL.
- **Reparación de CSV previa a pandas** — corrige comillas desbalanceadas antes de que el parser procese el archivo, preservando la alineación de columnas.
- **Matching de dos pasadas con niveles de confianza** — preserva los registros no vinculados en lugar de descartarlos, permitiendo un análisis posterior de la calidad de los datos.
- **Deduplicación específica por fuente** — una estrategia global podría colapsar silenciosamente eventos legítimos.
- **Abstracción `DataProvider`** — migrar el dashboard desde SQLite a PostgreSQL requiere implementar una interfaz, no reescribir la lógica de visualización.
- **Analítica como capa de solo lectura** — `scripts/analytics.py` nunca escribe; los consumidores, como el dashboard o una futura API, leen un `AnalyticsResult` serializable a JSON.

---

## Implementación en el mundo real

Esta plataforma fue desarrollada y desplegada originalmente para **Déficit Cero**, una organización chilena de incidencia en temas de vivienda, con el objetivo de consolidar y analizar datos provenientes de múltiples fuentes operacionales.

La implementación real integró cuatro fuentes heterogéneas — registros web, inscripciones a talleres, interacciones de chatbot y asistencia a talleres — en un pipeline de datos unificado y un dashboard de analítica. El pipeline ETL y el dashboard resultantes fueron entregados y quedaron en producción como una solución interna funcional y utilizados con datos reales de la organización.

Este repositorio público es una **versión saneada y reproducible para portafolio** de aquella implementación. Contiene datos de demostración completamente sintéticos diseñados para reproducir la estructura, los desafíos de calidad de datos y distribuciones representativas del sistema original, sin exponer información privada de la organización.

Por lo tanto, la arquitectura, la lógica de transformación, la estrategia de resolución de identidad, la capa analítica y los patrones del dashboard se basan en una implementación real y no en un ejemplo puramente hipotético.

Consulta [docs/case-study-deficit-cero.md](docs/case-study-deficit-cero.md) para conocer el contexto de implementación y las principales decisiones de ingeniería.

---

## Estructura del proyecto

```text
unified-data-insights-platform/
│
├── main.py                        # Punto de entrada del pipeline + CLI (once / daemon)
├── requirements.txt
├── README.md                      # Este archivo (🇺🇸 English)
├── README_ES.md                   # Español     (🇨🇱 Spanish)
│
├── config/
│   ├── settings.py                # Rutas, codificaciones y constantes globales
│   └── mappings.py                # Mapeos de columnas + normalización de valores
│
├── scripts/                       # Fases del pipeline
│   ├── extractors/                # Base + 4 extractores de fuentes (+ Zoom legado)
│   │   ├── base_extractor.py      # Reparación CSV + detección de encoding/delimitador
│   │   ├── registro_extractor.py
│   │   ├── talleres_extractor.py
│   │   ├── minga_extractor.py
│   │   └── asistencia_talleres_extractor.py
│   ├── transform.py               # Normalización, validación y deduplicación por fuente
│   ├── consolidate.py             # Matching de identidad en dos pasadas
│   ├── load.py                    # Persistencia SQLite + exportación CSV + auditoría
│   ├── analytics.py               # Capa de KPI / distribuciones
│   ├── scheduler.py               # Wrapper de programación como daemon
│   └── utils.py                   # Logger y utilidades compartidas
│
├── dashboard/
│   └── app.py                     # Dashboard Streamlit (proveedor SQLite / CSV)
│
├── database/
│   └── deficit_cero.db            # Base de datos SQLite (generada por el pipeline)
│
├── data/
│   ├── raw/                       # CSV de fuentes (ignorados por Git; nunca modificados)
│   ├── raw/samples/               # Fixtures anónimos de demostración (versionados)
│   └── processed/
│       └── usuarios_master.csv    # Resultado consolidado (UTF-8 BOM)
│
├── logs/
│   └── etl_YYYYMMDD.log           # Log rotativo del pipeline
│
├── docs/                          # Arquitectura, diccionario de datos y caso de estudio
│
├── build/
│   └── build_release.ps1          # Empaquetado de release con Nuitka + PyArmor
│
```

---

## Roadmap

| Estado | Item |
| ------ | ---- |
| ✅ Done | ETL de cuatro fuentes con estrategias de extracción y transformación por fuente |
| ✅ Done | Resolución de identidad en dos pasadas con niveles de confianza |
| ✅ Done | Persistencia idempotente en SQLite con auditoría de ejecuciones |
| ✅ Done | Capa analítica de KPIs + dashboard en Streamlit con abstracción `DataProvider` |
| ✅ Done | Fixtures de demostración anonimizados que reproducen los KPIs reales |
| 🔄 Planeado | Consolidación automática de múltiples archivos de exportación desde un directorio monitorizado |
| 🔄 Planeado | GitHub Actions para la ejecución programada del pipeline |
| 🔄 Planeado | Capa REST API sobre el módulo de analítica |
| 🔄 Planeado | Backend PostgreSQL para concurrencia y volúmenes de más de 100K registros |
| 🔄 Planeado | Empaquetado de releases públicos y distribución standalone mediante ejecutable |

---

## Licencia

MIT — consulta el repositorio para más detalles.