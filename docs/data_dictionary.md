# Data Dictionary

## Overview

This document describes the consolidated data model used by Unified Data Insights Platform.

The platform integrates information from multiple operational sources and consolidates user records into a master dataset that supports analytics, reporting, and business intelligence processes.

## Reference Implementation

The Unified Data Insights Platform is designed to be source-agnostic and can integrate data from multiple operational systems.

This document describes the reference implementation used during the development of the platform. The included entities, attributes, and business rules represent one real-world deployment and serve as examples of how the platform consolidates user information across heterogeneous data sources.

Specific field names and source systems may vary depending on organizational requirements.

The data model is composed of:

* `usuarios_master`: consolidated user entity.
* `talleres_asistencias`: detailed attendance records for workshops.

---

# Entity Relationship Diagram

```text
usuarios_master
       │
       │ email
       ▼
talleres_asistencias
```

A single user may have multiple attendance records.

Relationship:

```text
usuarios_master (1)
        │
        ▼
talleres_asistencias (N)
```

---

# Table: usuarios_master

## Description

Centralized master table containing consolidated information about each unique user identified across all integrated data sources.

Primary matching is performed using email address.

Secondary matching may be performed using normalized name fields when email information is unavailable.

---

## Primary Key

| Column | Type | Description                                     |
| ------ | ---- | ----------------------------------------------- |
| email  | TEXT | Unique identifier for consolidated user records |

---

## Identity Fields

| Column           | Type | Nullable | Description                                      |
| ---------------- | ---- | -------- | ------------------------------------------------ |
| email            | TEXT | No       | Primary identifier used for entity consolidation |
| match_confidence | TEXT | No       | Confidence level assigned during entity matching |
| nombre_key       | TEXT | Yes      | Normalized matching key derived from user name   |
| member_id_rcv    | TEXT | Yes      | External identifier from source system           |

### Allowed Values

#### match_confidence

| Value     | Description                            |
| --------- | -------------------------------------- |
| HIGH      | Match performed using email            |
| LOW       | Match performed using normalized name  |
| UNMATCHED | Record could not be confidently linked |

---

## Personal Information

| Column           | Type | Nullable | Description          |
| ---------------- | ---- | -------- | -------------------- |
| nombre           | TEXT | Yes      | First name           |
| apellido         | TEXT | Yes      | Last name            |
| genero           | TEXT | Yes      | Gender               |
| fecha_nacimiento | DATE | Yes      | Date of birth        |
| whatsapp         | TEXT | Yes      | Contact phone number |
| nacionalidad     | TEXT | Yes      | Nationality          |

---

## Geographic Information

| Column | Type | Nullable | Description          |
| ------ | ---- | -------- | -------------------- |
| region | TEXT | Yes      | Region               |
| comuna | TEXT | Yes      | Municipality or city |

---

## Housing Profile

| Column                 | Type    | Nullable | Description                                 |
| ---------------------- | ------- | -------- | ------------------------------------------- |
| situacion_habitacional | TEXT    | Yes      | Housing status classification               |
| pertenece_comite       | INTEGER | No       | Indicates membership in a housing committee |
| cuantas_personas_viven | INTEGER | Yes      | Number of people living in household        |
| estado_registro        | TEXT    | Yes      | Registration status                         |

### Boolean Fields

| Value | Meaning |
| ----- | ------- |
| 0     | False   |
| 1     | True    |

---

## Financial Profile

| Column               | Type    | Nullable | Description                    |
| -------------------- | ------- | -------- | ------------------------------ |
| subsidio_recomendado | TEXT    | Yes      | Recommended subsidy category   |
| rsh                  | TEXT    | Yes      | Social registry classification |
| tiene_propiedad      | INTEGER | No       | Indicates property ownership   |
| tiene_subsidio       | INTEGER | No       | Indicates subsidy ownership    |
| ingresos             | TEXT    | Yes      | Income range                   |
| ahorro               | TEXT    | Yes      | Savings range                  |

---

## Participation Indicators

These fields represent user interaction across integrated systems.

| Column             | Type    | Description                               |
| ------------------ | ------- | ----------------------------------------- |
| tiene_registro_web | INTEGER | User exists in registration source        |
| inscrito_taller    | INTEGER | User registered for at least one workshop |
| asistio_taller     | INTEGER | User attended at least one workshop       |
| uso_minga          | INTEGER | User interacted with chatbot platform     |

### Indicator Values

| Value | Meaning                 |
| ----- | ----------------------- |
| 0     | No interaction detected |
| 1     | Interaction detected    |

---

## Aggregated Metrics

| Column                   | Type    | Description                                            |
| ------------------------ | ------- | ------------------------------------------------------ |
| num_talleres_inscritos   | INTEGER | Total workshop registrations                           |
| num_talleres_asistidos   | INTEGER | Total workshop attendances                             |
| num_conversaciones_minga | INTEGER | Total chatbot conversations                            |
| tasa_asistencia          | REAL    | Attendance ratio between registrations and attendances |

### Formula

```text
tasa_asistencia =
num_talleres_asistidos /
num_talleres_inscritos
```

---

## Metadata

| Column                | Type     | Description                                         |
| --------------------- | -------- | --------------------------------------------------- |
| fuentes               | TEXT     | Source systems contributing to consolidated profile |
| fecha_primer_registro | DATETIME | Earliest detected interaction                       |
| fecha_etl             | DATETIME | ETL execution timestamp                             |

---

# Table: talleres_asistencias

## Description

Stores detailed attendance records for workshops. Each record represents a single participation event (taller × email × fecha).

> **Nota histórica:** Esta tabla reemplaza `zoom_asistencias` desde la versión 1.1.0. La fuente de datos cambió de exports de Zoom a `consolidado_asistencia.csv`.

---

## Primary Key

| Column | Type    | Description                          |
| ------ | ------- | ------------------------------------ |
| id     | INTEGER | Auto-increment attendance identifier |

---

## Foreign Key

| Column | References             |
| ------ | ---------------------- |
| email  | usuarios_master(email) |

---

## Columns

| Column           | Type     | Nullable | Description                         |
| ---------------- | -------- | -------- | ----------------------------------- |
| id               | INTEGER  | No       | Unique attendance identifier        |
| email            | TEXT     | Yes      | Consolidated user email             |
| nombre_asistente | TEXT     | Yes      | Participant display name            |
| nombre_key       | TEXT     | Yes      | Normalized matching key             |
| taller_entry_id  | TEXT     | Yes      | Workshop enrollment identifier      |
| taller_titulo    | TEXT     | Yes      | Workshop title                      |
| fecha_taller     | TEXT     | Yes      | Workshop date                       |
| match_confidence | TEXT     | Yes      | Matching confidence level           |
| archivo_origen   | TEXT     | Yes      | Source CSV file name                |
| fecha_etl        | DATETIME | No       | ETL execution timestamp             |

---

# Business Rules

## User Consolidation

Users are consolidated according to the following priority:

1. Exact email match.
2. Normalized first name + last name match.
3. Unmatched records remain isolated.

---

## Confidence Levels

### HIGH

Assigned when records share the same email address.

### LOW

Assigned when records are matched using normalized names.

### UNMATCHED

Assigned when no reliable relationship can be established.

---

# Data Quality Rules

## Email Standardization

* Emails are converted to lowercase.
* Leading and trailing spaces are removed.

## Name Standardization

* Names are normalized before matching.
* Accents and casing differences may be removed during processing.

## Duplicate Prevention

* The master table enforces uniqueness through the email primary key.

## Traceability

* Every ETL execution records a timestamp.
* Attendance records preserve the original source file through `archivo_origen`.

---

# Indexes

## usuarios_master

| Index          | Column           |
| -------------- | ---------------- |
| idx_region     | region           |
| idx_comuna     | comuna           |
| idx_confidence | match_confidence |
| idx_nombre_key | nombre_key       |

## talleres_asistencias

| Index            | Column     |
| ---------------- | ---------- |
| idx_ta_email     | email      |
| idx_ta_nombre_key| nombre_key |
| idx_ta_taller_id | taller_entry_id |
| idx_ta_confidence| match_confidence |

---

# Analytical Purpose

The consolidated data model supports:

* User segmentation.
* Participation analysis.
* Attendance tracking.
* Territorial reporting.
* Service utilization analysis.
* KPI generation.
* Dashboard visualization.
