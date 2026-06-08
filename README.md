🌎 Language:
🇺🇸 English | 🇨🇱 [Español](README_ES.md)

# Unified Data Insights Platform

## Overview

Unified Data Insights Platform is a modular ETL and analytics solution designed to consolidate, normalize and analyze data from multiple digital sources.

The platform is intended for organizations that need to unify fragmented information, automate data processing workflows and generate actionable insights through dashboards and reporting.

The project follows a scalable architecture based on Data Engineering best practices, allowing new data sources to be incorporated with minimal changes to the core pipeline.

---

## Key Features

### Data Integration

* Multi-source ingestion
* CSV-based data pipelines
* Modular extractor architecture
* Extensible source connectors

### Data Processing

* Data cleaning
* Schema normalization
* Record deduplication
* Identity resolution
* Data validation

### Data Storage

* Consolidated master dataset
* SQLite persistence layer
* Future-ready architecture for PostgreSQL migration

### Analytics

* KPI generation
* Aggregated metrics
* User engagement analysis
* Geographic distribution analysis
* Participation tracking

### Visualization

* Interactive dashboards
* Filtering and exploration tools
* Executive-level metrics
* Business intelligence reporting

---

## Current Development Status

### Phase 1 – Data Architecture and Mapping

* [x] Business process mapping
* [x] Source identification
* [x] Initial data architecture
* [x] Data flow design

### Phase 2 – ETL Development

* [ ] Extract layer
* [ ] Transformation layer
* [ ] Consolidation engine
* [ ] Data quality controls

### Phase 3 – Analytics

* [ ] KPI generation
* [ ] Metrics engine
* [ ] Aggregation models

### Phase 4 – Dashboard

* [ ] Streamlit application
* [ ] Interactive visualizations
* [ ] Filtering and reporting

### Phase 5 – Automation

* [ ] Scheduler
* [ ] Automated refresh
* [ ] Operational documentation

---

## Proposed Architecture

```text
Data Sources
     │
     ▼
Extract Layer
     │
     ▼
Transform Layer
     │
     ▼
Master Dataset
     │
     ▼
SQLite Database
     │
     ▼
Analytics Engine
     │
     ▼
Dashboard & Reporting
```

---

## Planned Data Sources

### User Registration

User profile and demographic information.

### Event Registrations

Registrations for courses, workshops and events.

### Chatbot Interactions

Conversation history and engagement metrics.

### Event Attendance

Participation records from virtual events.

### Surveys and Polls

Future integration for audience feedback analysis.

---

## Technology Stack

| Component       | Technology   |
| --------------- | ------------ |
| Language        | Python       |
| Data Processing | Pandas       |
| Database        | SQLite       |
| Visualization   | Streamlit    |
| Charts          | Plotly       |
| Automation      | Schedule     |
| Version Control | Git & GitHub |

---

## Repository Structure

```text
unified-data-insights-platform/

├── docs/
├── data/
├── database/
├── scripts/
├── dashboard/
├── config/
├── logs/
├── tests/
├── README.md
└── .gitignore
```

---

## Roadmap

### Version 1.0

* Multi-source ETL pipeline
* Master dataset generation
* SQLite integration
* KPI dashboard

### Version 1.1

* Advanced matching engine
* Attendance integration
* Data quality monitoring

### Version 1.2

* Survey and poll integration
* Historical trend analysis
* Automated reporting

### Version 2.0

* PostgreSQL support
* API layer
* Cloud deployment
* User authentication

---

## License

This repository is intended for educational, research and professional portfolio purposes.

---

## Author

Pablo Amion

Information Engineering Student
Data Analytics | Automation | Data Engineering
