🌎 Language: 🇺🇸 English | 🇨🇱 [Español](README_ES.md)

<div align="center">

# Unified Data Insights Platform

**Production-grade ETL pipeline + interactive analytics dashboard**
Consolidates 4 heterogeneous sources (≈52,000 records) into a unified, deduplicated user master — then turns it into action with a Streamlit dashboard.

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
![Status](https://img.shields.io/badge/Status-Production--inspired-2ea44f)
![Data Quality](https://img.shields.io/badge/Data%20Quality-Validated-2ea44f)
![Etapas](https://img.shields.io/badge/Pipeline-5%20phases-2ea44f)

---

### 🚀 Live Demo

**Try the deployed dashboard:** [Unified Data Insights Platform — Streamlit](https://unified-data-insights-platform.streamlit.app/)

The live demo runs on fully synthetic data modeled after the structure and distributions of the original production dataset.

---

## Table of Contents

- [Overview](#overview)
- [Why This Project?](#why-this-project)
- [Features](#features)
- [Architecture](#architecture)
- [Quickstart (local demo)](#quickstart-local-demo)
- [Usage](#usage)
- [Pipeline Outputs](#pipeline-outputs)
- [Data Governance & Data Quality](#data-governance--data-quality)
- [Engineering Challenges](#engineering-challenges)
- [Design Decisions](#design-decisions)
- [Real-World Implementation](#real-world-implementation)
- [Project Structure](#project-structure)
- [Roadmap](#roadmap)
- [License](#license)

---

## Overview

Organizations accumulate user data across disconnected systems — web registration platforms, form-based workshop tools, messaging/chatbot services, and video-conference exports. Each source has its own **schema, encoding, delimiter, and export quirks**. Joining them manually is error-prone and does not scale.

**Unified Data Insights Platform** solves this with a modular, five-phase ETL pipeline:

```
Extract → Transform → Consolidate → Load → Analytics
```

It ingests four heterogeneous CSV sources, resolves cross-source identity with a **two-pass, confidence-scored matching algorithm**, and delivers a clean unified user master to both a **SQLite database** and an **interactive Streamlit dashboard**.

Built on **synthetic demo data that faithfully replicates real production distributions** (≈52,000 users across four sources), it exercises the data-quality problems that rarely appear in tutorials: multiline free-text fields that break standard CSV parsers, inconsistent encodings, NULL key columns, and per-source deduplication rules that differ for legitimate business reasons.

> **Designed to be reused.** Adding a new data source requires only a new `BaseExtractor` subclass plus a column mapping in `config/mappings.py`. The transform, consolidate, load, analytics, and dashboard layers need zero changes.

---

## Why This Project?

Built to demonstrate end-to-end Data Engineering skills through a real-world implementation — from heterogeneous source ingestion and data quality challenges to a production-deployed ETL pipeline and interactive analytics dashboard.

The system was developed to solve an actual organizational data problem and remained operational after deployment, consolidating previously fragmented data sources into a unified and reproducible analytics workflow.

It now serves as a portfolio case study for Data Engineering, Data Analytics, and Python Backend roles, with the public repository providing a fully reproducible version built on anonymized synthetic data.

| Skill | Where it appears |
|---|---|
| ETL pipeline design | Phased architecture: Extract → Transform → Consolidate → Load → Analytics |
| Data quality handling | Encoding detection, malformed-CSV repair, email/date/gender normalization, NULL handling |
| Identity resolution | Two-pass matching (email → name) with confidence scoring and `UNMATCHED` preservation |
| Software design patterns | Abstract base class (`BaseExtractor`), strategy pattern (dedup per source), dependency inversion (`DataProvider`) |
| Relational modeling | Normalized SQLite schema (3 tables) with audit trail and activity counts |
| Analytics modeling | KPI layer with geographic / demographic / behavioral dimensions, JSON-serializable result |
| Dashboard development | Streamlit + Plotly with filters, interactive table, CSV export, dynamic color mapping |
| Data governance | Source provenance, identity confidence, unmatched-record preservation, execution auditing, and reproducible loads |
| Production thinking | Idempotent loads, rotating logs, run auditing, daemon scheduling, graceful degradation |
| Build & packaging | Nuitka standalone distribution + Tkinter launcher + optional ZIP release |

---

## Features

### Data Engineering
- **Multi-source extraction** — modular `BaseExtractor` subclasses per source; CSV repair that fixes malformed multiline exports *before* the parser sees them.
- **Robust I/O detection** — automatic encoding detection (`utf-8-sig` → `latin-1`) and delimiter detection (`comma`, `semicolon`, `pipe`, `tab`).
- **Per-source transformation** — email/date/gender normalization, quality scoring, and *source-specific* deduplication strategies.
- **Two-pass identity resolution** — exact email join (HIGH confidence), then normalized name join (LOW confidence); unmatched rows are preserved, not dropped.
- **Idempotent persistence** — `DELETE + INSERT` load to SQLite, so every run yields identical output.

### Analytics & Visualization
- **KPI layer** (`scripts/analytics.py`) — computes `total_usuarios`, participation counts, attendance rate, geographic and demographic distributions, source-overlap breakdown, and a confidence distribution — all in a JSON-serializable `AnalyticsResult`.
- **Interactive dashboard** — Streamlit + Plotly: KPI cards, charts, searchable/filterable data table with CSV export, dynamic color mapping for categorical dimensions.
- **Storage-agnostic UI** — `DataProvider` abstraction isolates the dashboard from SQLite vs. CSV; switching backends means implementing one interface.

### Production & Ops
- Run **auditing** — every execution is registered in the `etl_runs` table (durations, counts, warnings, status).
- **Log rotation** — 5 MB / file, 5 backups, UTF-8.
- **Daemon scheduling** — run the pipeline every N minutes with the `schedule` library.
- **Graceful degradation** — a failing source never aborts the pipeline; each phase reports its own result.

---

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                          data/raw/*.csv                        │
│   registro_rcv.csv  talleres.csv  historial_analizado.csv      │
│   consolidado_asistencia.csv                                   │
└──────────────┬──────────────┬──────────────┬──────────────┬───┘
               ▼              ▼              ▼              ▼
        ┌─────────────────────────────────────────────────────────┐
        │                      EXTRACT (×4)                       │
        │   encoding + delimiter detection · multiline CSV repair │
        │   column mapping → snake_case                           │
        └──────────────────────────────┬──────────────────────────┘
                                       ▼
        ┌─────────────────────────────────────────────────────────┐
        │                      TRANSFORM (×4)                     │
        │   email / date / gender normalization · quality score   │
        │   per-source deduplication strategy                     │
        └──────────────────────────────┬──────────────────────────┘
                                       ▼
        ┌─────────────────────────────────────────────────────────┐
        │                       CONSOLIDATE (1×)                  │
        │   pass 1: email  → HIGH confidence                      │
        │   pass 2: name   → LOW confidence                       │
        │   participation flags · activity counts · UNMATCHED     │
        └──────────────┬──────────────────────┬───────────────────┘
                       ▼                      ▼
        ┌────────────────────────┐   ┌────────────────────────────┐
        │          LOAD          │   │         ANALYTICS          │
        │  SQLite (idempotent)   │   │  KPIs · distributions      │
        │  CSV master export     │   │  JSON-serializable result  │
        │  etl_runs audit row    │   │                            │
        └───────────┬────────────┘   └─────────────┬──────────────┘
                    ▼                              ▼
        ┌──────────────────────────────────────────────────────────┐
        │         database/deficit_cero.db + STREAMLIT DASHBOARD   │
        └──────────────────────────────────────────────────────────┘
```

### The 5 pipeline phases

| Phase | Module | Responsibility |
|---|---|---|
| **Extract** | `scripts/extractors/*` | Read CSV, detect encoding/delimiter, repair multiline fields, apply column mapping |
| **Transform** | `scripts/transform.py` | Normalize emails/dates/categoricals, validate quality, deduplicate per source |
| **Consolidate** | `scripts/consolidate.py` | Two-pass cross-source matching, flags, activity counts |
| **Load** | `scripts/load.py` | Idempotent SQLite persistence, CSV export, run audit |
| **Analytics** | `scripts/analytics.py` | Compute KPIs and distributions consumed by the dashboard |

### SQLite schema (3 tables)

| Table | Purpose |
|---|---|
| `usuarios_master` | One row per user (keyed by email): demographics, geography, situation, participation flags, attendance rate, match confidence, source provenance |
| `talleres_asistencias` | Row-per-attendance detail (granular workshop session records) |
| `etl_runs` | Execution audit: timestamps, counts, duration, warnings, status |

---

## Quickstart (local demo)

**Requirements:** Python 3.10+ · Windows / macOS / Linux

### 1. Install

```bash
git clone https://github.com/your-username/unified-data-insights-platform.git
cd unified-data-insights-platform

python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
```

### 2. Get the demo data

`main.py` reads its sources from `data/raw/*.csv`. Those files are **git-ignored** (private production files never enter the repo), so on a fresh clone you must load the committed **synthetic demo** fixtures first:

```bash
# Copy the demo fixtures into data/raw/ with the exact names the pipeline expects
Copy-Item data\raw\samples\consolidado_asistencia_dummy.csv data\raw\consolidado_asistencia.csv
Copy-Item data\raw\samples\historial_analizado_dummy.csv data\raw\historial_analizado.csv
Copy-Item data\raw\samples\registro_rcv_dummy.csv data\raw\registro_rcv.csv
Copy-Item data\raw\samples\talleres_dummy.csv data\raw\talleres.csv
```

> The `*_dummy.csv` fixtures in `data/raw/samples/` are **byte-identical** to the production structure but fully anonymous, and they reproduce the same dashboard KPIs as the real data (≈52,020 users, 8,763 workshop registrations, 3,150 attendances, 1,196 chatbot users).

### 3. Run the pipeline

```bash
python main.py              # run once (Extract → Transform → Consolidate → Load → Analytics)
```

### 4. Launch the dashboard

```bash
streamlit run dashboard/app.py
```

Opens at **http://localhost:8501**. The dashboard reads from SQLite and falls back to the processed CSV.

---

## Usage

### Pipeline modes

```bash
python main.py                          # run once, then exit
python main.py --once                   # alias of the above

python main.py --schedule 30            # daemon mode: run every 30 minutes
python main.py --schedule 60 --now      # run immediately, then every 60 minutes
```

### Dashboard
- **KPI cards** — total users, registered, workshop registrations, attendances, chatbot users, multi-source overlap.
- **Charts** — distributions by gender, housing situation, region/comuna, source overlap, registration timeline.
- **Data table** — searchable, filterable, exportable to CSV.
- **Confidence breakdown** — HIGH vs LOW match confidence, exposed for downstream auditing.

### Sources

| Source | Extractor | File |
|---|---|---|
| Web registration | `RegistroExtractor` | `registro_rcv.csv` |
| Workshop sign-ups (form-based) | `TalleresExtractor` | `talleres.csv` |
| Chatbot conversations | `MingaExtractor` | `historial_analizado.csv` |
| Workshop attendance | `AsistenciaTalleresExtractor` | `consolidado_asistencia.csv` |

---

## Pipeline Outputs

| Artifact | Path | Description |
|---|---|---|
| SQLite database | `database/deficit_cero.db` (WAL) | `usuarios_master`, `talleres_asistencias`, `etl_runs` |
| Consolidated CSV | `data/processed/usuarios_master.csv` | Full user master, UTF-8 BOM |
| Run log | `logs/etl_YYYYMMDD.log` | Per-step counts, quality scores, warnings |

---

## Data Governance & Data Quality

Data integration is only useful when the resulting dataset is **traceable, reproducible, and safe to consume downstream**. The platform therefore treats data quality as a first-class concern throughout the pipeline rather than as a final validation step.

| Governance concern         | Implementation                                                                                                                                                                                                 |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Source traceability**    | Each consolidated record retains source provenance, allowing downstream analysis to identify where a user's information originated.                                                                            |
| **Identity resolution**    | Cross-source records are matched through a two-pass strategy with explicit confidence levels (`HIGH`, `LOW`, `UNMATCHED`) rather than forcing uncertain matches.                                               |
| **Data normalization**     | Emails, dates, categorical values, gender labels, and other fields are normalized consistently before consolidation.                                                                                           |
| **Deduplication**          | Deduplication rules are defined per source to distinguish genuine duplicate records from legitimate multi-event activity.                                                                                      |
| **Unmatched preservation** | Records that cannot be confidently linked are preserved and explicitly flagged instead of being silently discarded.                                                                                            |
| **Execution auditing**     | Pipeline runs are recorded in the `etl_runs` table with execution status, processing counts, duration, and warnings.                                                                                           |
| **Reproducible loads**     | Idempotent `DELETE + INSERT` persistence ensures repeated pipeline executions produce deterministic database state.                                                                                            |
| **Data isolation**         | Production source files remain outside the public repository, while the portfolio version uses synthetic fixtures that preserve the structure of the real implementation without exposing private information. |
| **Schema consistency**     | Column mappings and normalization rules are centralized in `config/mappings.py`, reducing implicit transformations distributed across the codebase.                                                            |

### Data lineage

The platform maintains a clear lineage from raw operational sources to analytical outputs:

```text
Raw Sources
    │
    ├── Web registrations
    ├── Workshop registrations
    ├── Chatbot interactions
    └── Workshop attendance
            │
            ▼
       Extraction
            │
            ▼
      Normalization
            │
            ▼
    Source-level Dedup
            │
            ▼
    Identity Resolution
      ├── HIGH confidence
      ├── LOW confidence
      └── UNMATCHED
            │
            ▼
     Unified User Master
            │
      ┌─────┴─────┐
      ▼           ▼
   SQLite      CSV Master
      │           │
      └─────┬─────┘
            ▼
       Analytics
            │
            ▼
   Streamlit Dashboard
```

This approach makes the analytical layer **auditable by design**: aggregated KPIs can be traced back to consolidated records, and consolidated records retain the information needed to understand how they were produced.


---

## Engineering Challenges

The non-trivial problems this project had to solve — the kind that only surface with real data.

**Malformed CSV exports from form-based systems**
ExpressionEngine and chatbot platforms export free-text fields with literal newlines inside quoted cells. Standard pandas parsers fail with `Error tokenizing data: Expected N fields, saw M`. The solution is a pre-pandas repair layer in `BaseExtractor` that detects record boundaries by "voting" on the shape of the first field across candidate lines, merges continuation lines into a single logical record, and neutralizes internal quotes without corrupting adjacent columns.

**Cross-source identity resolution without a shared primary key**
Sources don't share a common user identifier. The consolidation layer uses a two-pass strategy — exact email join (HIGH confidence), then normalized name join (LOW confidence). Unmatched records are preserved with an `UNMATCHED` flag instead of silently dropped, so data quality is auditable downstream.

**Idempotent persistence with NULL-keyed records**
UPSERT fails for rows with NULL keys, because SQLite allows multiple NULLs in a UNIQUE column — conflicts are never detected and duplicates accumulate across runs. The load layer uses **DELETE + INSERT**, guaranteeing identical output on every execution.

**Deduplication strategy varies per source**
A user can legitimately appear several times in one source: multiple workshop registrations, multiple chatbot conversations, multiple attendance rows. Deduplication is therefore *source-specific* — keyed on `formulario_entry_id` for workshops, and disabled for multi-event sources where collapsing would destroy valid data.

---

## Design Decisions

Full rationale in [docs/architecture.md](docs/architecture.md). Key choices at a glance:

- **DELETE + INSERT over UPSERT** — avoids silent duplicate accumulation with NULL-keyed records.
- **Pre-pandas CSV repair** — fixes unbalanced quotes before the parser sees them, preserving downstream column alignment.
- **Two-pass matching with confidence scores** — preserves unmatched rows rather than discarding them, enabling post-hoc data-quality analysis.
- **Source-specific deduplication** — one global strategy would silently collapse legitimate multi-event records.
- **DataProvider abstraction** — migrating the dashboard from SQLite to PostgreSQL requires implementing one interface, not rewriting visualization code.
- **Analytics as a pure read layer** — `scripts/analytics.py` never writes; consumers (dashboard, future API) read a JSON-serializable `AnalyticsResult`.

---

## Real-World Implementation

This platform was originally developed and deployed for **Déficit Cero**, a Chilean housing advocacy organization, to consolidate and analyze data from multiple operational sources.

The real implementation integrated four heterogeneous sources — web registrations, workshop registrations, chatbot interactions, and workshop attendance — into a unified data pipeline and analytics dashboard. The resulting ETL pipeline and dashboard were delivered as a functioning internal data solution and used with real organizational data.

This public repository is a **sanitized and reproducible portfolio version** of that implementation. It contains fully synthetic demo data designed to reproduce the structure, data-quality challenges, and representative distributions of the original system, without exposing private organizational information.

The architecture, transformation logic, identity-resolution strategy, analytics layer, and dashboard patterns are therefore grounded in a real-world implementation rather than a purely hypothetical example.

See [docs/case-study-deficit-cero.md](docs/case-study-deficit-cero.md) for the implementation context and engineering decisions.

---

## Project Structure

```
unified-data-insights-platform/
│
├── main.py                        # Pipeline entry point + CLI (once / daemon)
├── requirements.txt
├── README.md                      # This file  (🇺🇸 English)
├── README_ES.md                   # Español     (🇨🇱 Spanish)
│
├── config/
│   ├── settings.py                # Paths, encodings, global constants
│   └── mappings.py                # Column mappings + value normalizations
│
├── scripts/                       # Pipeline phases
│   ├── extractors/                # Base + 4 source extractors (+ legacy Zoom)
│   │   ├── base_extractor.py      # CSV repair, encoding/delimiter detection
│   │   ├── registro_extractor.py
│   │   ├── talleres_extractor.py
│   │   ├── minga_extractor.py
│   │   └── asistencia_talleres_extractor.py
│   ├── transform.py               # Normalization, validation, per-source dedup
│   ├── consolidate.py             # Two-pass identity matching
│   ├── load.py                    # SQLite persistence + CSV export + audit
│   ├── analytics.py               # KPI / distribution layer
│   ├── scheduler.py               # Daemon scheduling wrapper
│   └── utils.py                   # Shared logger and helpers
│
├── dashboard/
│   └── app.py                     # Streamlit dashboard (SQLite / CSV provider)
│
├── database/
│   └── deficit_cero.db            # SQLite database (pipeline-generated)
│
├── data/
│   ├── raw/                       # Source CSVs (git-ignored; never modified)
│   ├── raw/samples/               # Anonymous demo fixtures (committed)
│   └── processed/
│       └── usuarios_master.csv    # Consolidated output (UTF-8 BOM)
│
├── logs/
│   └── etl_YYYYMMDD.log           # Rotating pipeline log
│
├── docs/                          # Architecture, data dictionary, case study
│
├── build/
│   └── build_release.ps1          # Nuitka + PyArmor release packaging
│

```

---

## Roadmap

| Status | Item |
|---|---|
| ✅ Done | Four-source ETL with per-source extraction / transformation strategies |
| ✅ Done | Two-pass identity resolution with confidence scoring |
| ✅ Done | Idempotent SQLite persistence with run auditing |
| ✅ Done | Analytics KPI layer + Streamlit dashboard with DataProvider abstraction |
| ✅ Done | Anonymized demo fixtures reproducing real KPIs |
| 🔄 Planned | Auto-consolidation of multiple export files from a watched directory |
| 🔄 Planned | GitHub Actions for scheduled pipeline execution |
| 🔄 Planned | REST API layer over the analytics module |
| 🔄 Planned | PostgreSQL backend for concurrency and 100K+ volumes |
| 🔄 Planned | Public release packaging and standalone executable distribution
---

## License

MIT — see the repository for details.