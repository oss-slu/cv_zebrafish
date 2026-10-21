"""Build a static, in-browser version of the web prototype (stlite).

The output folder is plain HTML + files, the same thing GitHub Pages would host.
The analysis runs in the visitor's browser (Python compiled to WebAssembly), so
uploaded files never leave their computer.

Preview locally (nothing is published):
    python web_prototype/build_static.py
    python -m http.server 8600 --bind 127.0.0.1 --directory web_prototype/_site
    # open http://127.0.0.1:8600
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # Python 3.10 (the project's CI): use the small reader below
    tomllib = None

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
STLITE_VERSION = "1.12.0"

# Paths are relative to the repo root and keep the same layout in the browser, so
# adapter.py's REPO_ROOT / "src" / "data" / "assets" lookups work unchanged.
STATIC_FILES = [
    "web_prototype/app.py",
    "web_prototype/adapter.py",
    "data/samples/csv/correct_format.csv",
    "data/samples/jsons/BaseConfig.json",
    "assets/images/fish1.png",
    "assets/images/mouse.png",
    "assets/images/sidebar_verify_dark_active.svg",
    "assets/images/sidebar_verify_dark_inactive.svg",
    "assets/images/sidebar_view_output_dark_active.svg",
    "assets/images/sidebar_view_output_dark_inactive.svg",
]

# numpy / pandas / pillow are prebuilt in Pyodide; plotly is installed from PyPI, pinned so a new
# release can't silently change or break the published page.
REQUIREMENTS = ["numpy", "pandas", "plotly==7.0.0", "pillow"]  # plotly pinned to the version CI uses


def core_files() -> list[str]:
    """The analysis core (``src/__init__.py`` + ``src/core``), without tests."""
    files = ["src/__init__.py"]
    for path in sorted((REPO / "src" / "core").rglob("*.py")):
        rel = path.relative_to(REPO)
        if "tests" in rel.parts or rel.name.startswith("test_"):
            continue
        files.append(rel.as_posix())
    return files


def _read_simple_toml(text: str) -> dict[str, dict[str, object]]:
    """Enough TOML for our config.toml: [sections] and ``key = "str" | true/false | number``."""
    data: dict[str, dict[str, object]] = {}
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            section = line.split("#", 1)[0].strip()[1:-1].strip()
            data.setdefault(section, {})
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if value.startswith('"'):
            parsed: object = value[1 : value.index('"', 1)]  # '#' inside quotes (colors) is kept
        else:
            value = value.split("#", 1)[0].strip()
            if value in ("true", "false"):
                parsed = value == "true"
            else:
                parsed = float(value) if "." in value else int(value)
        data.setdefault(section, {})[key] = parsed
    return data


def streamlit_config() -> dict[str, object]:
    """Flatten .streamlit/config.toml into stlite's ``{"section.key": value}`` form."""
    text = (HERE / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    data = tomllib.loads(text) if tomllib is not None else _read_simple_toml(text)
    return {f"{section}.{key}": value for section, values in data.items() for key, value in values.items()}


INDEX_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>CV Zebrafish (web prototype)</title>
    <link rel="icon" href="assets/images/fish1.png" />
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@stlite/browser@{version}/build/stlite.css" />
    <style>html, body {{ background: #0f0f10; margin: 0; }}</style>
  </head>
  <body>
    <div id="root"></div>
    <script type="module">
      import {{ mount }} from "https://cdn.jsdelivr.net/npm/@stlite/browser@{version}/build/stlite.js";
      mount(
        {{
          entrypoint: "web_prototype/app.py",
          requirements: {requirements},
          streamlitConfig: {config},
          files: {files},
        }},
        document.getElementById("root"),
      );
    </script>
  </body>
</html>
"""


def build(out: Path) -> list[str]:
    files = core_files() + STATIC_FILES
    if out.exists():
        shutil.rmtree(out)
    for rel in files:
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, dest)
    (out / "index.html").write_text(
        INDEX_HTML.format(
            version=STLITE_VERSION,
            requirements=json.dumps(REQUIREMENTS),
            config=json.dumps(streamlit_config(), indent=2),
            files=json.dumps({rel: {"url": rel} for rel in files}, indent=2),
        ),
        encoding="utf-8",
    )
    # GitHub Pages: serve files as-is (no Jekyll processing of paths like _site).
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return files


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=HERE / "_site", help="Output folder (default: web_prototype/_site)")
    args = parser.parse_args()
    built = build(args.out)
    print(f"Built {len(built)} files + index.html into {args.out}")
