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
![Tests](https://img.shields.io/badge/Tests-81%20verification%20scripts-2ea44f)
![Etapas](https://img.shields.io/badge/Pipeline-5%20phases-2ea44f)

---

## Table of Contents

- [Overview](#overview)
- [Why This Project?](#why-this-project)
- [Features](#features)
- [Architecture](#architecture)
- [Quickstart (local demo)](#quickstart-local-demo)
- [Usage](#usage)
- [Pipeline Outputs](#pipeline-outputs)
- [Testing & Verification](#testing--verification)
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

Built to demonstrate **end-to-end Data Engineering skills in a realistic, non-trivial setting** — a portfolio piece for data engineering / data analysis / Python backend roles.

| Skill | Where it appears |
|---|---|
| ETL pipeline design | Phased architecture: Extract → Transform → Consolidate → Load → Analytics |
| Data quality handling | Encoding detection, malformed-CSV repair, email/date/gender normalization, NULL handling |
| Identity resolution | Two-pass matching (email → name) with confidence scoring and `UNMATCHED` preservation |
| Software design patterns | Abstract base class (`BaseExtractor`), strategy pattern (dedup per source), dependency inversion (`DataProvider`) |
| Relational modeling | Normalized SQLite schema (3 tables) with audit trail and activity counts |
| Analytics modeling | KPI layer with geographic / demographic / behavioral dimensions, JSON-serializable result |
| Dashboard development | Streamlit + Plotly with filters, interactive table, CSV export, dynamic color mapping |
| Testing discipline | 81 automated tests across 8 standalone verification scripts |
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

## Testing & Verification

Standalone, dependency-free verification scripts (not pytest) — each phase is independently verifiable from the project root with ANSI-colored output:

```bash
python verify_phase2.py                 # Extractors            — 5 tests
python verify_phase3.py                 # Transform             — 8 tests
python verify_phase4.py                 # Consolidate           — 10 tests
python verify_phase5.py                 # Load + SQLite         — 10 tests
python verify_phase6.py                 # Full pipeline         — 10 tests
python verify_analytics.py              # Analytics             — 9 tests
python verify_phase7.py                 # Dashboard             — 9 tests
python verify_asistencia_extractor.py   # Attendance extractor  — 10 tests
```

**81 tests total** — run all with: `for f in verify_*.py; do python $f; done`

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

This repo ships a production-inspired implementation originally built for a **Chilean housing advocacy organization** (Déficit Cero), integrating a web registration system, a form-based workshop platform, a housing chatbot, and attendance exports into a unified user master of ~48,000 real records.

The repository ships with fully **anonymized synthetic data** that replicates those real distributions, so the pipeline and dashboard are fully reproducible without exposing private information.

See: [docs/case-study-deficit-cero.md](docs/case-study-deficit-cero.md)

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
└── verify_*.py                    # 8 standalone verification scripts (81 tests)
```

---

## Roadmap

| Status | Item |
|---|---|
| ✅ Done | Four-source ETL with per-source extraction / transformation strategies |
| ✅ Done | Two-pass identity resolution with confidence scoring |
| ✅ Done | Idempotent SQLite persistence with run auditing |
| ✅ Done | Analytics KPI layer + Streamlit dashboard with DataProvider abstraction |
| ✅ Done | 81 automated tests across 8 verification scripts |
| ✅ Done | Nuitka standalone build + Tkinter launcher |
| ✅ Done | Anonymized demo fixtures reproducing real KPIs |
| 🔄 Planned | Auto-consolidation of multiple export files from a watched directory |
| 🔄 Planned | GitHub Actions for scheduled pipeline execution |
| 🔄 Planned | REST API layer over the analytics module |
| 🔄 Planned | PostgreSQL backend for concurrency and 100K+ volumes |

---

## License

MIT — see the repository for details.