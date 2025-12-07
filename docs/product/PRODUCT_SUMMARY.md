# CV Zebrafish: Product Summary (Updated)

## Executive Overview
- **Problem:** DeepLabCut zebrafish tracking outputs require manual scripting, validation, and plotting, creating hours of work per dataset and blocking non-programmer researchers.
- **Solution:** CV Zebrafish is a Python/PyQt desktop app that validates DLC CSVs, auto-builds configs, computes kinematic metrics, and renders publication-ready graphs in minutes.
- **Primary users:** Dr. Mohini Sengupta's SLU lab (students and technicians). Secondary: zebrafish behavioral neuroscience labs using DLC; future: other aquatic-organism labs and industry toxicology/pharma.
- **Value:** Time per dataset drops from ~2-3 hours to ~5 minutes; standardized metrics and validation reduce errors; accessible UI removes coding barrier.

## Product Description
### What it does
1) Load DLC CSVs and run structural/likelihood validation.
2) Generate or select JSON configs that map body parts and analysis parameters.
3) Run kinematic calculations (fins, head, tail, spine, bouts, peaks, scaling) on validated data.
4) Render Plotly-based graphs in-app and prepare exports for figures/CSV outputs.

### Key capabilities
- **Data validation (src/core/validation):** CSV and JSON verifiers check column structure, required body parts, types, and likelihood thresholds with actionable error messaging.
- **Config generation (src/core/config + ui/scenes/ConfigGeneratorScene.py):** Detects available body parts from CSV, builds reusable JSON configs, and supports user-tunable thresholds, plot visibility, and video params.
- **Calculation engine (src/core/calculations):**
  - Parser maps DLC CSV columns into structured point arrays.
  - Metrics include fin angles, head yaw, tail side/distance/peaks, spine angles, swim bout detection, and time alignment.
  - Driver orchestrates metrics, scaling, and structured DataFrame outputs; export helpers produce enriched CSVs.
- **Graph and visualization pipeline (src/core/graphs):**
  - Loader bundles calculation results + config; runner orchestrates modular plotters.
  - Implemented plotters: fin/tail angle-and-distance timelines with bout slices and peak markers, spine snapshot selector with confidence handling, and reusable dot-plot helper; default set is driven by config flags (e.g., `shown_outputs.show_angle_and_distance_plot`, `shown_outputs.show_spines`).
  - Plotly + Kaleido pipeline supports on-screen display and static exports.
- **UI/UX (src/ui):**
  - Scenes for Landing, CSV input, JSON input, Config Generator, Calculation, Graph Viewer, and Verify.
  - Calculation scene enforces readiness checks and progress states; Graph Viewer lists available plots, handles resizing, and renders PNGs.
- **Data management:** Optional SQLite persistence and file hashing helpers keep ingestion runs reproducible; sample data and assets are organized under assets/ and data/.

### User workflow
CSV upload -> validation -> config selection/generation -> calculations -> graph rendering -> export.

## Architecture
- **Entry point:** `app.py` launches the PyQt application.
- **UI layer:** `src/ui/scenes` (Landing, CSV/JSON input, Config Generator, Calculation, Graph Viewer, Verify) and shared widgets under `src/ui/components`.
- **Core services:**
  - Parsing: `src/core/parsing/Parser.py` and helpers.
  - Config: `src/core/config/configSetup.py` plus sample/default JSONs.
  - Validation: CSV/JSON verifiers under `src/core/validation`.
  - Calculations: metrics, driver, comparison utilities under `src/core/calculations`.
  - Graphs: data loader, metrics, plot modules, runner, and IO helpers under `src/core/graphs`.
- **Platform utilities:** `src/app_platform/paths.py` centralizes writable paths.
- **Legacy reference:** `legacy/` retains the Bruce workflow for regression comparison.
- **Testing:** `tests/` hosts unit suites for parser, metrics, driver, and validation utilities; graph tests live under `src/core/graphs/tests`.
- **Documentation:** README, docs/architecture (calculation notes and legacy comparisons), docs/howtos (UI and validation), docs/product (presentations and summary).

## Technology Stack
- Python 3.10, PyQt5/WebEngine for desktop UI, NumPy/Pandas/SciPy for computation, Plotly (+ Kaleido) for visualization, OpenCV where needed for image ops, SQLite for persistence, DeepLabCut compatibility.
- Environment management via `environment.yml` (conda) or `python -m venv` + `pip install -r environment.yml` equivalent; PyQt5, pandas, numpy, scipy, plotly, kaleido, opencv, matplotlib, pillow, openpyxl, pytest/pytest-qt included.

## Current State (December 2025)
- Multi-scene PyQt UI wired end-to-end from file selection through calculations and graph viewing.
- CSV/JSON validation flows integrated with sample inputs and unit coverage.
- Calculation pipeline (Parser -> Metrics -> Driver) produces fin, tail, spine, yaw, bout, and peak metrics with scaling and enriched export helpers.
- Modular graph pipeline online with default plotters for fin/tail angle-distance timelines and spine snapshots (plus dot-plot helper for reuse); config-driven shown_outputs toggles plot selection; runner and output context manage saving.
- Documentation refreshed (README, architecture notes, how-tos); product overview prepared for presentations.
- Latest client asks captured in `docs/product/meeting_minutes/client_request_notes.md` (graph editing/local extrema, ranged exports, clickable points, multi-CSV overlays, tabular-format normalization, zebrafish silhouette, installable UX).

### In progress / next up
- Broader plot coverage (movement tracks, heatmaps) and UI affordances for choosing plots; zebra fish silhouette/art integration.
- Export UX for graph images and calculation CSVs directly from the UI, including ranged-export to Excel and downloadable graphs.
- Usability polish (installable launcher/icon, student-friendly styling) from lab feedback; accessibility tweaks for non-technical users.
- Foundations for multi-CSV sessions and graph overlays (color-keyed), clickable point capture, and configurable inclusion of fin/spine series in the GUI/JSON.
- Exploration of format normalization (CSV/XLS/XLSX) and schema mapping to generalize beyond the current DLC layout.

## Business Value and ROI
- Time saved: ~2.5 hours per dataset (validation + metrics + plotting) translating to ~$100 saved per dataset at $40/hour; 50 datasets/year yields ~$5k annual labor savings for a single lab.
- Quality and reproducibility: automated validation plus standardized metrics reduce human error and ensure consistent analysis.
- Accessibility: point-and-click workflow opens analysis to students and technicians without Python expertise.

## Risks and Mitigations
- **Live demo risk:** Include cached screenshots/PNGs via the Graph Viewer if Plotly export fails.
- **Data quality risk:** Validators enforce schema/likelihood thresholds; clear error messaging guides fixes.
- **Adoption risk:** Iterative UI testing with Sengupta Lab and default configs tailored to DLC exports reduce onboarding friction.

## Team and Process
- Tech Lead: Madhuritha Alle; Developers: Nilesh, Jacob, Finn; Client: Dr. Mohini Sengupta; Faculty Advisor: Dr. Daniel Shown.
- Workflow: Agile-style iterations, feature branches with code review, unit tests on core modules, documented contribution and runbooks.

## Roadmap
- **Short term (next iteration):** Finish plot suite, finalize export pipeline (CSV + PNG/SVG + ranged Excel), clickable point capture/local extrema tools, client parameter list export, incorporate beta feedback; keep two-sprint target for interactive downloadable graphs.
- **Medium term (6-12 months):** Multi-CSV sessions with overlays, batch runs, comparative stats, advanced visualizations (heatmaps, movement tracks), packaged installer/app icon, UX polish with zebrafish silhouette/art.
- **Long term (1-3 years):** Format/schema normalization for arbitrary tabular inputs, multi-species support, behavior classification with ML, cloud/shared datasets, plugin ecosystem and community contributions.

## Appendix
- **System requirements:** Python 3.10; Windows 10+/macOS 10.14+/Ubuntu 20.04+; 4 GB RAM (8 GB recommended); ~500 MB disk plus dataset storage.
- **Inputs/outputs:** Inputs: DLC CSV, JSON config; Outputs: enriched metric CSVs, Plotly PNG/SVG (via Kaleido), future report files.
- **Repository snapshot:** `app.py`, `src/` (app_platform, core/{calculations, config, graphs, parsing, validation}, data, ui, session), `docs/`, `assets/`, `tests/`, `legacy/`, `environment.yml`.
