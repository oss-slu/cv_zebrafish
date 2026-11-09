"""Tests for the browser-only static build (spike #136). No Streamlit needed."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

_spec = importlib.util.spec_from_file_location("build_static", REPO_ROOT / "web_prototype" / "build_static.py")
build_static = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_static)


def _files_in_index(index_html: str) -> dict:
    start = index_html.index("files: ") + len("files: ")
    files, _ = json.JSONDecoder().raw_decode(index_html, start)
    return files


def test_build_contains_every_module_the_page_imports(tmp_path):
    out = tmp_path / "site"
    build_static.build(out)

    # Import the adapter in a fresh interpreter so only *its* src.* imports count
    # (other tests in this session load unrelated src modules).
    probe = (
        "import sys, json; from pathlib import Path; "
        f"sys.path.insert(0, {str(REPO_ROOT / 'web_prototype')!r}); import adapter; "
        f"root = Path({str(REPO_ROOT)!r}); "
        "print(json.dumps(sorted(Path(m.__file__).resolve().relative_to(root).as_posix() "
        "for n, m in list(sys.modules.items()) if n.startswith('src.') and getattr(m, '__file__', None))))"
    )
    proc = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, cwd=REPO_ROOT, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    needed = json.loads(proc.stdout.strip().splitlines()[-1])
    assert "src/core/parsing/Parser.py" in needed
    missing = [rel for rel in needed if not (out / rel).is_file()]
    assert not missing, f"static build is missing modules the page imports: {missing}"


def test_index_lists_only_copied_files_and_no_tests(tmp_path):
    out = tmp_path / "site"
    build_static.build(out)
    index = (out / "index.html").read_text(encoding="utf-8")

    assert 'entrypoint: "web_prototype/app.py"' in index
    files = _files_in_index(index)
    assert files, "no files listed"
    for rel, spec in files.items():
        assert spec == {"url": rel}
        assert (out / rel).is_file(), rel
        assert "tests" not in Path(rel).parts and not Path(rel).name.startswith("test_"), rel
    assert (out / ".nojekyll").exists()
