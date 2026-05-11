# Contributing to CV Zebrafish

Thank you for your interest in contributing to CV Zebrafish! This guide will help you get started quickly and avoid common pitfalls.

---

## Table of Contents

- [Getting Started](#getting-started)
- [How to Contribute](#how-to-contribute)
- [Pull Request Process](#pull-request-process)
- [Code Style](#code-style)
- [Communication Norms](#communication-norms)
- [Known Architecture Notes](#known-architecture-notes)

---

## Getting Started

1. Fork the repository and clone your fork:

```bash
git clone https://github.com/your-username/cv_zebrafish.git
cd cv_zebrafish
```

2. Create the Conda environment:

```bash
conda env create -f environment.yml
conda activate cvzebrafish
```

3. Run the app to confirm setup:

```bash
python app.py
```

4. Run the test suite:

```bash
pytest
```

If all tests pass and the app opens, you are ready to contribute.

---

## How to Contribute

### Pick an Issue

- Browse [open issues](https://github.com/oss-slu/cv_zebrafish/issues) and look for ones labeled `good first issue` or `help wanted`
- Comment on the issue to let others know you are working on it
- If you have a new idea, open an issue first before starting work so it can be discussed

### Create a Branch

```bash
git checkout -b your-branch-name
```

Use a descriptive branch name that references the issue, for example:
`feature/issue-95-auto-select-config` or `fix/issue-91-loading-bar`

---

## Pull Request Process

1. Make sure all existing tests pass before submitting:

```bash
pytest
```

2. Add tests for any new functionality where applicable
3. Keep your PR focused — one issue per PR where possible
4. Write a clear PR description covering:
   - What the change does
   - Why it was needed
   - How to test it
   - Any known limitations
5. Submit your PR and request a review from the tech lead
6. Address review feedback promptly — PRs that go stale for more than two weeks may be closed

> **Important:** If your work touches shared UI files (especially anything in `src/ui/main_panels/`, `src/ui/popup_panels/`, or `src/ui/main_window_shell.py`), flag this in the group channel before starting. Large structural UI changes can create merge conflicts for other contributors. The norm is: communicate first, then code.

---

## Code Style

- Follow existing patterns in the file you are editing
- Use descriptive variable and function names
- Add docstrings to new classes and public methods
- Keep functions focused — if a function is doing more than one thing, consider splitting it
- No unused imports
- PyQt5 conventions: connect signals in `__init__`, keep UI logic in the UI layer and business logic in `src/core/`

---

## Communication Norms

- Large structural changes must be communicated to the team before starting work — not after a PR is open
- If your branch will touch the same files as another open PR, coordinate with that contributor first to avoid merge conflicts
- If you are stuck, ask — do not spend more than a day blocked without reaching out

---

## Known Architecture Notes

### Shell and panel architecture
The UI uses a shell-and-panel architecture introduced in Spring 2026. All main workflow panels live under `src/ui/main_panels/` and modal dialogs live under `src/ui/popup_panels/`. The old `src/ui/scenes/` folder no longer exists — do not recreate it.

### Session persistence
Session files are stored under `data/sessions/` which is gitignored. The session registry at `data/local/session_registry.json` uses atomic writes via `tempfile` + `os.replace`. Do not simplify this to a direct write.

### Session routing
The logic for deciding which panel to show when a session loads lives in `_resume_workspace_from_session` in `src/ui/main_window_shell.py`. New session → Verify. Existing session with CSVs but no config → Verify + Generate Config dialog. Existing session with any config → Select & Run.

### UI scaling
All layout values should use `scaled_px()` from `styles/ui_scale.py` rather than hardcoded integers. Font sizes in stylesheets are scaled automatically via `scale_stylesheet()`. Do not hardcode px values in new UI code.

### Background workers
All calculations run off the UI thread via workers in `src/ui/workers/`. Do not run heavy computation directly in the UI layer — use the existing worker pattern.

---

## Questions?

Open an issue or reach out through the project's OSS-SLU channel. We are happy to help new contributors get oriented.
