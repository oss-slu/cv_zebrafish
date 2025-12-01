# CV Zebrafish

Desktop toolkit for validating DeepLabCut zebrafish CSVs, generating JSON configs, running kinematic calculations, and rendering Plotly graphs through a PyQt UI.

## Quickstart

### Prereqs
- Python 3.10+
- Git
- System packages for Qt (Windows: included with PyQt5 wheels; macOS/Linux may need Qt libraries)

### Setup (Conda)
```bash
conda env create -f environment.yml
conda activate cvzebrafish
```
> `environment.yml` declares Python 3.10 and all app/test dependencies; prefer this over ad-hoc pip installs.

### Run the UI
```bash
python app.py
```
The flow walks through CSV/JSON selection, validation, config generation, calculations, and graph viewing.

### Run tests
```bash
pytest
```

## Project Layout (current)
```text
app.py                         # PyQt entry point (adds src/ to sys.path)
assets/
├── images/                    # UI icons / art
└── sample_data/               # Example configs/CSVs (paired with data/samples)
data/
└── samples/
    ├── csv/                   # DLC CSV fixtures used by UI/tests
    └── jsons/                 # BaseConfig + generated config examples
docs/
├── architecture/              # Calculation/graph design notes
├── howtos/                    # UI + validation how-tos
└── product/                   # Product summary, presentations, meeting minutes
legacy/                        # Bruce pipeline for regression comparisons
src/
├── app_platform/paths.py      # Writable paths/utilities
├── core/
│   ├── calculations/          # Metrics, driver, exports
│   ├── config/configSetup.py  # Config discovery/merging
│   ├── graphs/                # Loader, runner, Plotly plotters (fin/tail, spines)
│   ├── parsing/Parser.py      # DLC CSV parser
│   └── validation/            # CSV/JSON validators + config generator
├── data/                      # DB ingestion helpers
├── session/                   # Session persistence for the UI
└── ui/
    ├── components/            # Shared widgets (sliders, checks, etc.)
    └── scenes/                # Landing, CSV/JSON input, Config Generator, Calculation, Graph Viewer, Verify
tests/
└── unit/                      # Core + UI unit tests (pytest)
```

## Feature Highlights
- **Validation:** CSV/JSON verifiers with structural and likelihood checks.
- **Config generation:** UI scene builds configs from detected body parts and saves JSON.
- **Calculations:** Fin/tail angles, yaw, spine metrics, bout/peak detection, enriched exports.
- **Graphs:** Modular Plotly plotters (fin-tail timelines, spine snapshots) with Kaleido PNG rendering.
- **UI:** Multi-scene PyQt flow with session save/load to resume work.
- **Legacy parity:** Legacy pipeline kept under `legacy/` for comparison.

## Known Gaps / Next Steps
- No dependency lockfile; add `requirements.txt`/`conda-lock` if needed.
- No CI or lint/type tooling; add GitHub Actions to run pytest.
