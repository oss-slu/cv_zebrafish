# Local setup notes (pip + venv)

Notes for installing CV Zebrafish without Conda, and for fixing a fresh environment when `pytest` or PNG graphs misbehave. The Conda path in the README is still the primary one.

**Last verified:** Nov 2026, macOS 15.6 (Apple Silicon), Homebrew `python@3.10` (3.10.19), clean venv

- `pip install -r requirements.txt && pip install -e .` installs without errors
- `pytest --ignore=tests/unit/web`: **332 passed**
- `python app.py` starts and stays running (checked with `QT_QPA_PLATFORM=offscreen`)
- `from PyQt5.QtWebEngineWidgets import QWebEngineView` works, so interactive graphs are available


## Steps

```bash
python3.10 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .                 # tests import the `cvzebrafish` package
pytest --ignore=tests/unit/web   # web tests need web_prototype/requirements.txt
python app.py
```

No `brew install qt` is needed: PyQt5 and PyQtWebEngine wheels bundle Qt on macOS.


## Why the pins

| Package | Pinned | Why |
|---------|--------|-----|
| plotly | 5.24.1 | Plotly 7 refuses Kaleido 0.2.x ("Image export requires the Kaleido package, v1.0.0 or greater"). Plotly 6.0–6.3 still export with Kaleido 0.2.1, but 6.3 prints a deprecation warning, so the pin stays on 5.x |
| kaleido | 0.2.1 | Kaleido 1.x spawned headless Chrome and **hung** on `fig.write_image` / `pio.to_image` (spine plot tests never finished) |

Do **not** `pip install -U kaleido` on Plotly 5.x, which pulls Kaleido 1.x and brings the hang back.

`environment.yml` does not pin these. If a Conda install hangs on PNG export, check `python-kaleido`'s version and pin `python-kaleido=0.2.1` and `plotly=5.24.1`.


## Things to know

- **`setup.py` `install_requires` is incomplete.** `pip install -e .` alone does not pull scipy, opencv, matplotlib, pillow, openpyxl, PyQtWebEngine or pytest-qt. Install `requirements.txt` first.
- **PyQtWebEngine is optional at runtime.** Without it the app still runs, but graphs show "Interactive graphs require PyQtWebEngine" instead of the zoom/pan/hover view (`src/ui/components/InteractiveGraph.py`).
- **Python version.** 3.10 matches `environment.yml` and is the version verified here. Other versions are untested.
- **OpenCV is unpinned.** The verified install resolved `opencv-python` 5.1.0 and all tests passed. Pin `<5` if a 5.x release causes trouble.
- **Qt font warning** on launch (`missing font family "Segoe UI Symbol"`) is harmless; it's a Windows font.
