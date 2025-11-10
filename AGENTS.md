# Repository Guidelines

## Project Structure & Module Organization
- Backend services live in `backend/` and analytics engines in `calculations/`; frontend UI code stays under `frontend/`.
- The `cv_zebrafish` tree hosts the new implementation, while `../codes` holds the legacy reference pipeline—leave the latter untouched aside from analysis.
- Visualization helpers are in `graphing/`, validation logic in `data_schema_validation/`, and new shared utilities should land in `calculations/utils/`.

## Build, Test, and Development Commands
- `python app.py` runs the backend entry point for local iteration.
- `npm install && npm run dev` (from `frontend/`) launches the UI with hot reload; `npm run build` emits production assets.
- `pytest` from the repo root executes analytics and schema suites; append `-k pattern` for targeted runs.

## Coding Style & Naming Conventions
- Follow PEP 8 for Python (4-space indents, snake_case, concise module docstrings for exported APIs).
- Frontend code uses the repo ESLint/Prettier setup; run `npm run lint` before committing.
- Configuration files stay JSON/YAML with lower_snake_case keys and minimal inline comments.

## Testing Guidelines
- Name tests `test_<behavior>` and keep fixtures beside their suites (e.g., `calculations/tests/fixtures/`).
- Use `pytest --cov=calculations --cov=data_schema_validation` to confirm coverage after significant changes.
- Document manual checks or attach sample artefacts in PRs when touching visualization pathways.
- When validating end-to-end CSV processing, prefer the canonical fixtures `data_schema_validation/sample_inputs/csv/correct_format.csv` and `data_schema_validation/sample_inputs/jsons/BaseConfig.json`.

## Commit & Pull Request Guidelines
- Use `type: summary` commit messages (e.g., `feat: add bout detection helper`) and group related edits.
- PRs should outline the behavior change, list verification steps (tests, screenshots), and link issues when relevant.

## Legacy Bruce Pipeline (Reference)
- `codes/main.py` loads `configs/BaseConfig.json` via a hard-coded Windows path, creates `results/` or `bulk_results/`, and runs single or batch CSV calculations before delegating to the output module.
- `utils/configSetup.py` optionally resets `LastConfig.json`; `mainFuncs.py` maps DeepLabCut columns and supplies vector math; `mainCalculation.py` assembles numpy arrays for fin/tail metrics (note the typo that prevents 3-point fin angles from persisting).
- `utils/outputDisplay.py` manages a global `outputsDict`, mirrors logs to `log.txt`, builds Excel summaries, and emits Plotly/OpenCV visuals (spine overlays, fin/tail/head charts, movement tracks, heatmaps, head-orientation tabs).
- Sample assets live in `codes/input_data/`; generated artefacts accumulate under `codes/results/Results N` or `bulk_results/Results N`.
- Pain points driving the rewrite: absolute Windows paths, heavy global state, tightly coupled computation and plotting, and side-effect-driven APIs that resist testing.
