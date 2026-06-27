# UI structure

This document describes how the PyQt interface is organized.

## Vocabulary

| Term | Location | Meaning |
|------|----------|---------|
| **Panel** | `ui/main_panels/*_panel.py` | Full workspace page in the main shell (wraps an inner widget) |
| **Widget / Scene** | `ui/main_panels/*_widget.py`, `ui/popup_panels/*_widget.py` | Primary content for a panel or dialog (`*Scene` classes are legacy naming) |
| **Dialog** | `ui/popup_panels/*_dialog.py` | Modal popup (settings, session picker, config generator) |
| **Component** | `ui/components/` | Reusable controls (pose canvas, sliders, chrome) |
| **Worker** | `ui/workers/` | `QThread` / `QObject` background jobs (DLC, folder runs, video) |

## Main workspace flow

```text
main_window_shell.py
  └── workspace_widget.py
        ├── empty_session_panel.py      (no session open)
        ├── verify_panel.py             (CSV / JSON validation)
        ├── select_run_panel.py         → select_run_widget.py
        ├── view_output_panel.py        → graph_viewer_widget.py
        └── pose_studio_panel.py        (Label / Train / Dataset tabs)
```

## Core vs UI

- **Calculations, graphs, pose, validation** live under `src/core/`.
- **PyQt wiring** lives under `src/ui/` and calls into `core/` — never import UI from core.
- Graph building logic: `core/graphs/graph_builder.py` (used by Graph Viewer and folder pipeline workers).
- DLC training: isolated subprocess via `scripts/run_dlc_step.py` and `ui/workers/pose_subprocess_worker.py`.

## Tests

All unit tests belong under `tests/unit/`, mirroring `src/` (e.g. `tests/unit/core/graphs/`).
