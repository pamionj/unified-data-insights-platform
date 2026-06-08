🌎 Idioma:
🇺🇸 [English](README.md) | 🇨🇱 Español

# Plataforma Unificada de Análisis de Datos

## Descripción general

Unified Data Insights Platform o Plataforma Unificada de Análisis de Datos es una solución modular de ETL y análisis diseñada para consolidar, normalizar y analizar datos de múltiples fuentes digitales.

La plataforma está dirigida a organizaciones que necesitan unificar información fragmentada, automatizar los flujos de trabajo de procesamiento de datos y generar información útil mediante paneles de control e informes.

El proyecto sigue una arquitectura escalable basada en las mejores prácticas de ingeniería de datos, lo que permite incorporar nuevas fuentes de datos con cambios mínimos en el flujo de trabajo principal.

---

## Características principales

### Integración de datos

* Ingesta de múltiples fuentes
* Canalizaciones de datos basadas en CSV
* Arquitectura de extractor modular
* Conectores de origen extensibles

### Procesamiento de datos

* Limpieza de datos
* Normalización de esquemas
* Eliminación de duplicados de registros
* Resolución de identidades
* Validación de datos

### Almacenamiento de datos

* Conjunto de datos maestro consolidado
* Capa de persistencia SQLite
* Arquitectura preparada para la migración a PostgreSQL

### Análisis

* Generación de KPI
* Métricas agregadas
* Análisis de la interacción del usuario
* Análisis de la distribución geográfica
* Seguimiento de la participación

### Visualización

* Paneles interactivos
* Herramientas de filtrado y exploración
* Métricas de nivel ejecutivo
* Informes de inteligencia empresarial

---

## Estado actual del desarrollo

### Fase 1: Arquitectura y mapeo de datos

* [x] Mapeo de procesos de negocio
* [x] Identificación de fuentes
* [x] Arquitectura de datos inicial
* [x] Diseño del flujo de datos

### Fase 2 – Desarrollo ETL

* [ ] Capa de extracción
* [ ] Capa de transformación
* [ ] Motor de consolidación
* [ ] Controles de calidad de datos

### Fase 3 – Analítica

* [ ] Generación de KPI
* [ ] Motor de métricas
* [ ] Modelos de agregación

### Fase 4 – Panel de control

* [ ] Aplicación Streamlit
* [ ] Visualizaciones interactivas
* [ ] Filtrado e informes

### Fase 5 – Automatización

* [ ] Planificador
* [ ] Actualización automática
* [ ] Documentación operativa

---

## Arquitectura propuesta

```texto
Fuentes de datos

│

▼
Capa de extracción

│

▼
Capa de transformación

│

▼
Conjunto de datos maestro

│

▼
Base de datos SQLite

│

▼
Motor analítico

│
▼
Panel de control e informes
```

---

## Fuentes de datos planificadas

### Registro de usuarios

Perfil de usuario e información demográfica.

### Registros de eventos

Inscripciones a cursos, talleres y eventos.

### Interacciones con el chatbot

Historial de conversaciones y métricas de participación.

### Asistencia a eventos

Registros de participación en eventos virtuales.

### Encuestas y sondeos

Futura integración para el análisis de la retroalimentación de la audiencia.

--

## Tecnologías utilizadas

| Componente | Tecnología |

| --------------- | ------------ |

| Lenguaje | Python |

| Procesamiento de datos | Pandas |

| Base de datos | SQLite |

| Visualización | Streamlit |

| Gráficos | Plotly |

| Automatización | Programación |

| Control de versiones | Git y GitHub |

---

## Estructura del repositorio

```texto
plataforma unificada de análisis de datos/
├── documentación/
├── datos/
├── base de datos/
├── scripts/
├── panel de control/
├── configuración/
├── registros/
├── pruebas/
├── README.md
└── .gitignore
```

---

## Hoja de ruta

### Versión 1.0

* Pipeline ETL de múltiples fuentes
* Generación de conjunto de datos maestro
* Integración con SQLite
* Panel de control de KPI

### Versión 1.1

* Motor de coincidencia avanzado
* Integración de asistencia
* Monitoreo de la calidad de los datos

### Versión 1.2

* Integración de encuestas y sondeos
* Análisis de tendencias históricas
* Informes automatizados

### Versión 2.0

* Compatibilidad con PostgreSQL
* Capa API
* Implementación en la nube
* Autenticación de usuarios

---

## Licencia

Este repositorio está destinado a fines educativos, de investigación y para la creación de portafolios profesionales.

---

## Autor

Pablo Amion

Estudiante de Ingeniería | Análisis de Datos | Automatización | Ingeniería de Datos
