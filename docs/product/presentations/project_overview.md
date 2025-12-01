# CV Zebrafish Project Overview

## Purpose and Problem
- Behavioral neuroscience labs need to convert DeepLabCut (DLC) zebrafish tracking CSVs into interpretable, publication-ready visuals.
- Current workflow demands manual Python scripting, error-prone validation, and hours per dataset.
- Non-programmer researchers are blocked by tooling complexity and inconsistent outputs.

## Value Proposition
- Shrinks analysis time from hours to minutes via guided UI.
- Automates DLC data validation and configuration generation to prevent bad inputs.
- Standardizes kinematic metrics and plots so results are reproducible and comparable across experiments.

## Target Users and Stakeholders
- Primary: Dr. Mohini Sengupta's SLU bio lab researchers and students.
- Secondary: Zebrafish behavioral neuroscience community using DLC.
- Future: Other aquatic organism labs and potential industry toxicology/pharma users.

## Product at a Glance
- Desktop PyQt application that ingests DLC CSVs, validates structure/likelihoods, generates JSON configs, runs kinematic calculations, and presents Plotly-based visualizations.
- Runs locally without network requirements; cross-platform via Python 3.10 + Conda/venv.

## User Journey
1) Select DLC CSV -> automated CSV structure and likelihood checks.
2) Generate or load JSON config (auto-detects body parts, customizable thresholds/plots).
3) Run calculations (fin angles, head yaw, tail and spine metrics, swim bout detection, peak detection).
4) Review graphs in-app; export-ready figures (PNG via Kaleido) and CSV outputs (export in progress).

## Core Features
- **Data Validation:** CSV/JSON verifiers catch malformed DLC exports and schema issues with clear guidance.
- **Config Generator:** Auto-builds reusable configs from detected body parts; supports parameter tweaks and persistence.
- **Kinematic Engine:** Metrics for pectoral fins, head yaw, tail side/distance/peaks, spine angles, bout ranges; orchestrated by Driver with robust parser.
- **Visualization Layer:** Plotly figures rendered in Graph Viewer scene; supports multiple plot types with responsive layout (full plot set finishing in next iteration).
- **Data Management:** Normalizes inputs into SQLite with hashing for reproducibility; tracks runs and artifacts.

## Architecture and Stack
- Layered design: PyQt UI scenes -> validation layer -> calculation engine -> visualization adapters.
- Key technologies: Python 3.10, PyQt5/WebEngine, NumPy/Pandas/SciPy, Plotly (+Kaleido), OpenCV, DeepLabCut compatibility, SQLite persistence.
- Config-driven workflow enables reproducibility and batch reuse; modular components ease testing and extension.

## Current State (This Iteration)
- Stable PyQt UI with linked scenes (CSV/JSON input, Config Generator, Calculation, Graph Viewer) and polished layouts.
- Validated CSV/JSON pipelines with unit tests; sample inputs for quick verification.
- Calculation engine integrated end-to-end (Parser -> Metrics -> Driver) with tests for fin, tail, spine, yaw, bouts, peaks, and scaling.
- Graph Viewer infrastructure ready; connecting full figure set and exports is underway.
- Documentation: README, product summary, architecture notes, how-tos, and contributing guidelines.

## Technical Decisions and Rationale
- **Python-first:** Aligns with DLC ecosystem and lab familiarity; accelerates scientific computing tasks.
- **PyQt desktop:** Offline-friendly, performant for large CSVs, native UX without browser constraints.
- **Plotly + Kaleido:** Delivers interactive-quality plots with static export capability for publications.
- **Modularity:** Separate validation/calculation/viz layers for maintainability and parallel development.
- **Config JSONs:** Encapsulate experiment parameters for reproducibility and sharable templates.

## Evidence of Value
- Time savings: ~2-3 hours -> ~5 minutes per dataset (validation + metrics + plots).
- Consistency: Automated validation and standardized metrics reduce manual errors and variability.
- Accessibility: Point-and-click flow enables non-programmers to generate scientific outputs.

## Roadmap Highlights (Next Iteration)
- Complete plot generation suite (angle/distance, spine, movement tracks, heatmaps) wired to calculation outputs.
- Export pipeline for CSV metrics and graph images; optional report generation.
- Usability testing with Sengupta Lab; incorporate feedback into UI polish and defaults.
- Batch processing and additional statistics for comparative studies.

## Investment Case
- High-impact, low-risk: foundation (validation + calculations + UI) is done; remaining work is scoped, low unknowns.
- Immediate adoption: Client lab ready to use once graph/export features land; clear ROI in researcher hours.
- Extensible platform: Positioned for multi-species expansion, community contributions, and potential grant alignment.

## Team and Process
- Team: Tech Lead (Madhuritha Alle), Developers (Nilesh, Jacob, Finn), Client (Dr. Sengupta), Faculty Advisor (Dr. Shown).
- Process: Agile-style iterations, feature branches with code review, unit tests on core modules, documented workflows.
