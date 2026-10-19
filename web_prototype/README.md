# Web version feasibility spike (#136)

A time-boxed investigation into whether CV Zebrafish could run as a web app, with a
small working prototype. **This is not a full build.**

## Run the prototype

From the repo root, in the project environment (`environment.yml`):

```bash
pip install -r web_prototype/requirements.txt
cd web_prototype
streamlit run app.py
```

Run it from inside `web_prototype/` so the dark theme in `.streamlit/config.toml` (the
desktop app's colors) is picked up. It opens at http://localhost:8501 and follows the
desktop app's flow, with its logos and sidebar icons:

1. **Species**: choose Zebrafish or Mouse, then Continue.
2. **Zebrafish → Load**: fish logo + "Load DeepLabCut CSV" (or **Use the bundled sample
   file**); an optional config JSON goes under *Config (optional)*.
3. **Zebrafish → Results**: summary table (mean / min / max of fin angles, tail distance,
   head yaw), the existing **fin angles + tail distance** plot with a frame-range slider,
   all result columns, and **Download results CSV**.
4. **Mouse**: mouse logo + "Load DLC File" (`.h5`/`.csv`), then the same placeholder
   layout as the desktop Mouse Analysis page (#118). No mouse analysis exists yet.

Files are processed in memory and a temporary folder; nothing is stored.

### What it covers (it's a sample, not a replacement)

It runs the **same analysis code** as the desktop app (results are identical), but only
shows a small part of what the desktop app offers:

| | Desktop app | Web prototype |
|---|---|---|
| Species selection, mouse placeholder page | ✅ | ✅ |
| Analyze one DeepLabCut CSV | ✅ | ✅ |
| Sessions (create, save, reopen) | ✅ | ❌ |
| Batch runs on a folder of CSVs | ✅ | ❌ |
| Generate Config (pick body parts, custom angles) | ✅ | ❌ (sample config or upload a JSON) |
| Graphs | Dot plots, fin/tail, spines, head plot, custom angle, cross-correlation | Fin/tail only |
| Graph tools (range statistics, export range, compare graphs) | ✅ | Frame-range slider only |
| Save graphs as HTML/PNG | ✅ | ❌ (results CSV download only) |
| Settings (theme, UI scale), console, help | ✅ | Dark theme only |
| Summary table of key measurements | ❌ | ✅ (new) |
| Warns when file body parts don't match the config | ❌ | ✅ (new) |

## No server: browser-only build (GitHub Pages ready)

The same page can also run **entirely in the visitor's browser** using
[stlite](https://github.com/whitphx/stlite) (Streamlit + Python compiled to WebAssembly).
The output is plain static files, so it can be hosted on **GitHub Pages with no server to
set up or maintain**, and uploaded files **never leave the visitor's computer**.

```bash
python web_prototype/build_static.py          # writes web_prototype/_site/
python -m http.server 8600 --bind 127.0.0.1 --directory web_prototype/_site
# open http://127.0.0.1:8600 (private preview: only your computer can reach it)
```

Tested in Chrome, including from a `/cv_zebrafish/` subfolder like a GitHub Pages
project site: first load takes about 10 s (the browser downloads Python once), the sample
analysis takes about 5 s, and results, the plot, the CSV download, and the mouse path
match the server version.

**To publish on GitHub Pages:** push the contents of `_site/` to a `gh-pages` branch
and set *Settings → Pages → Source* to that branch (or use an Actions workflow). On a
personal account the page is **public**: anyone with the link can open it, though it only
contains code and sample data that are already public in this repo. Enabling Pages on
`oss-slu/cv_zebrafish` needs a repo admin.

**Limits of the browser-only build:**
- Only pure-Python / Pyodide-supported packages: numpy, pandas, plotly are fine; PyQt and
  Kaleido image export are not available (not needed by this page).
- Slower than a server for large files, and bounded by browser memory.
- Reading DeepLabCut `.h5` in the browser should be possible via h5py (in Pyodide's
  package list) but was not tested in this spike.
- Plotly is pinned (`build_static.py`) so a new release can't change the published page.

| File | What it is |
|---|---|
| `adapter.py` | Calls the existing core (`parse_dlc_csv` → `run_calculations` → `render_fin_tail`). No web imports, so any framework can use it. |
| `app.py` | The Streamlit page: species → load → results, styled like the desktop app (~290 lines). |
| `.streamlit/config.toml` | Dark theme using the desktop `DARK_THEME` colors. |
| `build_static.py` | Builds the browser-only (stlite) static site into `_site/` for GitHub Pages. |
| `../tests/unit/web/test_web_adapter.py` | Checks the web path gives **identical** results to the desktop pipeline, and that bad files fail with a message. |
| `../tests/unit/web/test_web_app.py` | Clicks through both flows (skipped if Streamlit isn't installed). |
| `../tests/unit/web/test_build_static.py` | Checks the static build contains every analysis module the page imports. |

## Framework comparison

| | Streamlit | Dash | Flask + simple front end |
|---|---|---|---|
| **Ease** | Easiest. Plain Python script; upload, sliders, tables built in. The prototype page is ~290 lines, roughly a quarter of it styling to match the desktop app. | Moderate. Layout + callbacks; more boilerplate, but more control. | Hardest. Routes, HTML/JS, upload handling, plot embedding all hand-written. |
| **Plots** | `st.plotly_chart` shows our existing Plotly figures directly. | Built by Plotly; our figures drop straight into `dcc.Graph`. Best fit for rich interaction (linked plots, range selection). | Possible via `fig.to_json()` + plotly.js, but we write the glue. |
| **Tables** | `st.dataframe`, sortable, built in. | `dash_table` / AG Grid, very capable. | Write our own or add a JS library. |
| **State / workflows** | Script reruns on every interaction; fine for upload → analyze → view, gets awkward for multi-step workflows like sessions. | Explicit callbacks; handles complex multi-step apps well. | Whatever we build. |
| **Hosting** | `streamlit run` anywhere; Streamlit Community Cloud; Docker; **or fully static in the browser via stlite (GitHub Pages)**. | Standard Flask/WSGI app (gunicorn); easy on a university VM or Docker. | Standard Flask/WSGI app. |
| **Team skills** | Python only. | Python only (some CSS for layout). | Python + HTML/CSS/JavaScript. |

**Takeaway:** Streamlit is the fastest way to a usable internal tool. Dash is the better
long-term fit if the web version needs the desktop graph viewer's interactivity (range
statistics, multi-dataset overlay). Flask + front end only makes sense with a dedicated
front-end developer.

## What blocks reuse of current code

Good news first: the analysis core runs without the desktop UI. `parse_dlc_csv` →
`run_calculations` takes ~0.5 s on the 5,351-frame sample, and the web path produces
results **identical** to the desktop pipeline (tested). The plots are already Plotly,
which renders natively in a browser.

Blockers found (most are what #133 is meant to fix):

1. **Graph-building glue lives in the desktop UI.** Turning a results table into figures
   (`build_fin_tail_graphs`, `_iter_*_graphs`, etc.) is in
   `src/ui/main_panels/graph_viewer_widget.py`, which imports PyQt. The prototype copies
   ~30 lines of it into `adapter.fin_tail_figure`. → Move these into `src/core/graphs/` (#133).
2. **The core reads files by path, not data.** `verify_deeplabcut_csv` checks
   `os.path.isfile`, and `GraphDataLoader` takes file paths. Web uploads must be written
   to a temp file first. → Let core functions accept DataFrames/buffers (#133).
3. **Missing body parts fail silently.** If the file doesn't have the body parts the
   config names, the parser fills them with NaN and the analysis "succeeds" with empty
   results (a mouse file with the zebrafish config gave 20 of 21 empty numeric columns).
   The prototype adds a check; the desktop app has the same gap.
4. **The validator can crash on malformed files** (`IndexError`) instead of returning an
   error. The prototype catches it.
5. **Sessions depend on PyQt.** `src/session/session.py` subclasses `QObject`, so the
   web version can't reuse sessions as-is.
6. **A config JSON is required.** The desktop app has a Generate Config dialog (Qt);
   a web version would need its own way to build or choose one.
7. **The analysis is zebrafish-specific.** It computes fin angles, spine, and tail
   distance, reads CSV only (no `.h5`), and has no mouse measurements. **A web version
   does not remove the mouse analysis work**: that code has to be written either way.

## Hosting options and data privacy

| Option | How | Data leaves the lab? | Notes |
|---|---|---|---|
| **GitHub Pages (browser-only)** | `build_static.py` → static files on GitHub Pages; Python runs in each visitor's browser. | **No**, uploads stay in the visitor's browser | **No server to set up or maintain**, free. Page is public on personal/free accounts (contains only code + sample data). ~10 s first load; large files limited by browser memory. |
| **Local** | Run `streamlit run` on a lab computer; open in the browser. | No | Zero cost, no accounts. Same privacy as the desktop app; still needs Python installed. |
| **SLU server** | A university VM behind HTTPS, ideally with SLU login. | Stays within SLU | Needs SLU IT: VM availability, HTTPS, single sign-on, who maintains it. *To confirm with IT.* |
| **Cloud** | Streamlit Community Cloud, Hugging Face Spaces, Render, etc. | Yes, to a third party | Easiest to share. Uploaded research data is processed on someone else's servers. Free tiers may make apps public by default and have memory/CPU limits. |

Privacy questions for the lab before anything is hosted: is unpublished tracking data
allowed on third-party servers? Who should have access, and does it need a login? Should
uploads ever be stored, or only processed and discarded (the prototype stores nothing)?

## Recommendation

1. **Don't replace the desktop app right now.** The desktop app has ~8,700 lines of UI
   (graph viewer alone ~2,000) that a web version would have to rebuild for parity:
   sessions, config generation, batch runs, range statistics, export. The hard part of
   mouse support, the mouse analysis itself, is the same work on either platform.
2. **Land #133 first.** Moving the graph glue and file handling into a UI-independent
   core (blockers 1–4) makes both the desktop app and any web version thin layers over
   the same code. Without it, every web feature means copying code out of PyQt widgets.
3. **If the lab wants a web version, start with a Streamlit mouse-only page, shared as
   a browser-only GitHub Pages site.** A mouse workflow is new, so there's no desktop
   parity to chase. Build it as a Streamlit page on top of the decoupled core and publish
   it with `build_static.py`: **no server setup**, and uploaded data stays in each
   user's browser, which sidesteps most privacy questions. If a public page isn't
   acceptable, run it locally on a lab machine instead. Revisit Dash and SLU hosting only
   if it needs logins, shared storage, or more compute than a browser can give.

**Effort estimate (rough, assuming one or two developers on the current team):**

| Work | Estimate |
|---|---|
| Decoupling for web reuse (#133 blockers 1–4) | ~1 sprint (already planned) |
| Mouse-only Streamlit page: upload DLC CSV/.h5, mouse measurements, plots, export | ~1–2 sprints *after* the client confirms the mouse measurements |
| Hosting as a browser-only GitHub Pages site | Small: build script included; needs Pages enabled on the repo |
| Hosting on an SLU server with login (only if needed) | Unknown; depends on SLU IT |
| Full web replacement of the desktop app | Several sprints; not recommended now |

**Suggested next sprint:** finish #133, get the mouse measurement list from the client,
and ask the lab whether a public browser-only page is acceptable (uploads stay on each
user's computer) or whether the tool must be private.
