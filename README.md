# STRATOS — Alpine F1 Race Intelligence & Next-Race Prediction System

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Testing: pytest](https://img.shields.io/badge/testing-pytest-yellow.svg)](https://docs.pytest.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**STRATOS** is a functional, research-grade Formula 1 historical analysis and next-race prediction system exclusively focused on **BWT Alpine Formula One Team** (and its Enstone heritage: Renault/Lotus).

Designed for race engineers, strategists, and motorsport data scientists, STRATOS combines **official session telemetry**, **clean-lap normalization**, **fuel-corrected tyre degradation modeling**, a **leakage-free multi-stage predictive engine**, and an **explainability framework** with a high-density **Streamlit cockpit**.

---

## Key Pillars

1. **Alpine-Centric Empirical Intelligence**: Tracks BWT Alpine F1 Team from 2021 through 2026, while providing toggleable historical context for the Enstone heritage eras (Renault 2016–2020, Lotus 2012–2015).
2. **Authentic Relational & Columnar Storage**:
   - `stratos.db`: SQLite database (WAL mode, foreign keys, 12 tables) storing events, sessions, classification results, pit stops, race control messages, predictions, experiments, and source provenance.
   - Partitioned Parquet store (`data/processed/`): Columnar partition format for laps, track weather, and car telemetry.
   - Provenance Registry: Validates data sources (FastF1, Alpine Official Media, FIA regulations) with SHA-256 checksums and quality warning logs.
3. **Formula 1 Performance Metrics**:
   - Clean-lap filtering (excluding SC, VSC, yellow flags, in/out laps, pace outliers > 107%).
   - Fuel-corrected tyre degradation regression at $0.055\,\text{s/lap}$ burn rate.
   - Qualifying performance & speed trap deltas.
   - Intra-team teammate battles (Pierre Gasly vs Esteban Ocon / Jack Doohan).
   - Classified reliability rates & mechanical failure tracking.
4. **Leakage-Free Multi-Stage Prediction Engine**:
   - Four temporal stages: `PRE_WEEKEND`, `POST_PRACTICE`, `POST_QUALIFYING`, `PRE_RACE`.
   - Feature extractor enforces strict temporal cutoffs to eliminate future data leakage.
   - Outputs: Expected finishing position, 90% confidence intervals, discretized 20-position Gaussian probability distributions, and championship points probabilities.
   - Benchmark models: Baseline comparisons against Last Race Heuristic, Season Average, and Grid Position.
5. **Engineering Explainability & Auditing**:
   - Feature attributions (+/- delta positions) quantifying pace, grid, circuit characteristics, and weather impacts.
   - Operational driver rationales, uncertainty flags, midfield competitor benchmarks, and historical precedent analogues.
   - Markdown race engineer briefings and automated evaluation against actual race results.
6. **Functional Streamlit Cockpit**:
   - High-contrast, dark motorsport theme (`#0284c7` Alpine Blue, `#ec4899` BWT Pink, `#0b1120` Carbon Dark).
   - Strictly **four primary navigation views** with zero mock or decorative controls:
     1. **OVERVIEW**: Executive cockpit with next Grand Prix discovery, form trend badges, active forecast, and historical trajectory.
     2. **TEAM ANALYSIS**: Season filters, Enstone heritage toggle, competitor midfield benchmarking, intra-team battles, and tyre degradation curves.
     3. **NEXT RACE**: Grand Prix selector, temporal stage cutoff, driver selector, interactive engineering overrides, 20-position probability distribution chart, and downloadable briefing reports.
     4. **HISTORY & DATA**: Historical race archive, live FastF1 ingestion pipeline, prediction verification matrix, backtest experiments, CSV exports, and online database backups.

---

## System Architecture

```text
                                  [ FastF1 & FIA Timing Sources ]
                                                │
                                    Ingestion Pipeline & Validator
                                                │
                     ┌──────────────────────────┴──────────────────────────┐
                     ▼                                                     ▼
           SQLite Relational DB                                 Parquet Columnar Store
             (data/stratos.db)                                     (data/processed/)
          - 12 Relational Tables                                - Partitioned Laps
          - Integrity & Provenance                              - Weather & Telemetry
                     │                                                     │
                     └──────────────────────────┬──────────────────────────┘
                                                │
                                  Alpine Performance Metrics
                                  - Clean Pace & Fuel Deg ($0.055s/lap)
                                  - Teammate Battles & Field Benchmarks
                                                │
                               ┌────────────────┴────────────────┐
                               ▼                                 ▼
                     Multi-Stage Predictor             Explainability Engine
                     - 4 Temporal Cutoffs              - Feature Attributions
                     - 90% Intervals                   - Rival Benchmarks
                     - Discretized Distributions       - Precedent Analogues
                               │                                 │
                               └────────────────┬────────────────┘
                                                │
                                                ▼
                                    STRATOS Streamlit Cockpit
                             ┌─────────────────────────────────────┐
                             │  OVERVIEW   │  TEAM ANALYSIS        │
                             ├─────────────┼───────────────────────┤
                             │  NEXT RACE  │  HISTORY & DATA       │
                             └─────────────────────────────────────┘
```

---

## Repository Structure

```text
stratos-motorsport-ai/
├── app.py                         # Top-level Streamlit Cockpit Application
├── configs/
│   └── default.yaml               # Model defaults, cutoffs, and cache configuration
├── data/
│   ├── stratos.db                 # SQLite relational database (WAL mode, 12 tables)
│   ├── processed/                 # Partitioned Parquet storage (laps, weather, telemetry)
│   ├── backups/                   # Timestamped online atomic database backups
│   └── cache/                     # FastF1 disk cache (git-ignored)
├── scripts/
│   ├── inspect_race.py            # FastF1 session inspection and data validation utility
│   ├── run_agents.py              # Deliberative multi-agent strategy scenario runner
│   └── simulate_strategy.py       # Kinematics forward simulation and strategy optimizer
├── src/
│   └── stratos/
│       ├── alpine/
│       │   ├── caveats.py         # Technical regulation eras & telemetry proxy caveats
│       │   ├── comparator.py      # AlpinePerformanceComparator (rival & field benchmarking)
│       │   ├── identity.py        # Alpine brand vs Enstone heritage resolver & driver registry
│       │   └── metrics.py         # Clean pace, fuel-corrected deg, qualifying & pit loss
│       ├── dashboard/
│       │   ├── charts.py          # Reusable Plotly chart generators
│       │   ├── styles.py          # Cockpit design tokens, dark CSS & typography
│       │   └── views/
│       │       ├── __init__.py    # Dashboard view exports
│       │       ├── history_data.py# History, Ingestion, Predictions & Backup View
│       │       ├── next_race.py   # Multi-Stage Prediction & Explainability View
│       │       ├── overview.py    # Executive Alpine Cockpit View
│       │       └── team_analysis.py# Competitor Benchmarks & Teammate Battle View
│       ├── explainability/
│       │   └── explainer.py       # PredictionExplainer, Evaluator & Markdown Report Generator
│       ├── ingestion/
│       │   ├── pipeline.py        # Incremental FastF1 ingestion pipeline
│       │   ├── registry.py        # DataSourceRegistry with SHA-256 integrity checks
│       │   └── validator.py       # DataValidator & clean-lap outlier filter
│       ├── prediction/
│       │   ├── backtesting.py     # Chronological walk-forward backtester
│       │   ├── features.py        # Leakage-free temporal feature extractor
│       │   ├── models.py          # StratosRaceForecaster (intervals & distributions)
│       │   └── schedule.py        # NextEventDetector for upcoming Grand Prix
│       └── storage/
│           ├── database.py        # StratosDB (SQLite WAL, foreign keys, 12 tables)
│           ├── parquet_store.py   # ParquetStore (partitioned columnar storage)
│           └── sample_data.py     # Multi-season historical data seeder (2021–2026)
└── tests/
    ├── test_alpine_caveats.py     # Technical regulation era tests
    ├── test_alpine_comparator.py  # Comparator & benchmarking tests
    ├── test_alpine_identity.py    # Team identity & driver resolution tests
    ├── test_alpine_metrics.py     # Pace, deg, and reliability metric tests
    ├── test_explainability.py     # Explainer, feature attribution & report tests
    ├── test_ingestion.py          # Data ingestion and clean lap validator tests
    ├── test_prediction_models.py  # Forecaster, intervals & distributions tests
    ├── test_prediction_schedule.py# Schedule detection & feature extractor tests
    ├── test_storage.py            # SQLite schema, transactions & backup tests
    └── test_stratos_cockpit.py    # Cockpit 4-view integration test suite
```

---

## Installation & Setup

STRATOS requires **Python 3.11+**.

### 1. Clone & Setup Environment

```bash
# Using uv (recommended)
uv venv .venv --python 3.12
.venv\Scripts\activate      # Windows
# source .venv/bin/activate # Linux / macOS

# Or using standard python
python -m venv .venv
.venv\Scripts\activate      # Windows
```

### 2. Install Package

```bash
pip install -e ".[dev]"
```

---

## Launching the Streamlit Cockpit

Launch the cockpit locally:

```bash
streamlit run app.py
```

The application runs in your default browser at `http://localhost:8501`.

### Cockpit Navigation Guide

| Section | Description | Key Interactive Capabilities |
| :--- | :--- | :--- |
| **OVERVIEW** | Executive race intelligence cockpit | Auto-discovery of next upcoming GP, 5-race recent form badge, active race forecast card, multi-season performance trajectory chart, data provenance status. If the DB is fresh, a 1-click seeder populates multi-season history. |
| **TEAM ANALYSIS** | Detailed team & rival analytics | Season selector (2021–2026), Enstone heritage toggle (Alpine vs Renault/Lotus), Midfield constructor benchmarking with rival filter, Intra-team battle (Gasly vs Ocon), fuel-corrected tyre deg curves, pit stop execution histogram, and technical regulation era caveats. |
| **NEXT RACE** | Multi-stage prediction engine | Grand Prix picker, 4 temporal stages (`PRE_WEEKEND`, `POST_PRACTICE`, `POST_QUALIFYING`, `PRE_RACE`), driver selector, engineer overrides (grid position, track temp, rain probability, practice pace delta), working "Generate & Save Forecast" button, 20-position discretized Gaussian distribution chart, feature attribution waterfall, rival benchmarking, uncertainty factors, and downloadable Markdown briefing reports. |
| **HISTORY & DATA** | Archival data & provenance hub | 5 sub-tabs: 1) Historical race classification archive with driver breakdown; 2) Live FastF1 ingestion runner with provenance sources & SHA-256 checks; 3) Prediction verification matrix with auto-evaluator; 4) Walk-forward backtest experiments; 5) Non-blocking online database backups & CSV table exports. |

---

## Prediction Stages & Leakage Prevention

STRATOS guarantees **zero future data leakage** by strictly binding feature availability to the session temporal cutoff:

```text
Stage               Permitted Data Inputs
───────────────────────────────────────────────────────────────────────────
1. PRE_WEEKEND      Season baseline, rolling form, circuit history, weather forecast.
2. POST_PRACTICE    + FP1/FP2/FP3 long-run clean pace, fuel-corrected deg slopes.
3. POST_QUALIFYING  + Official Q1/Q2/Q3 lap times, grid position, teammate delta.
4. PRE_RACE         + Formation lap track surface temp, confirmed starting compound.
```

---

## Testing & Quality Assurance

All 130+ unit, integration, and cockpit tests execute **100% offline without network calls or external data dependencies**:

```bash
# Run complete test suite
pytest -v

# Run cockpit view integration tests
pytest tests/test_stratos_cockpit.py -v

# Verify code style and linting (0 errors)
ruff check .
```

---

## Provenance & Grounded Data Sources

Every statistic, result, and prediction in STRATOS is grounded in authentic sources:
- **FastF1 Python Library**: Official F1 live timing, sector times, telemetry, tyre compounds, and meteorological logs.
- **BWT Alpine F1 Team Official Media**: Factory releases, technical updates, and driver statements from Enstone & Viry-Châtillon.
- **Formula 1 Official Classification**: Official FIA race classifications, steward bulletins, and sporting regulations.

---

## License

STRATOS is licensed under the MIT License.
