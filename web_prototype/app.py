"""CV Zebrafish web prototype (spike for #136).

Run from this folder so the dark theme in .streamlit/config.toml is picked up:
    cd web_prototype
    streamlit run app.py

Mirrors the desktop flow: species selection → load screen → results. The
zebrafish path runs the existing analysis; the mouse path is structure only,
like the desktop Mouse Analysis page (#118).
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapter import (  # noqa: E402
    REPO_ROOT,
    SAMPLE_CSV_PATH,
    analyze_csv_bytes,
    fin_tail_figure,
    load_sample_config,
    summary_table,
)

IMAGES = REPO_ROOT / "assets" / "images"

# Desktop DARK_THEME values (styles/themes.py).
PANEL_MAIN = "#0f0f10"
PANEL_CHROME = "#222226"
CHROME_BUTTON = "#26262a"
CHROME_LINE = "#38383e"
TEXT = "#ececf0"
TEXT_MUTED = "#9c9ca8"
ACCENT = "#90CAF9"

SPECIES = ("Zebrafish", "Mouse")

# Pages: species → zebrafish_load → zebrafish_results, or species → mouse_load → mouse_analysis.
STEPS = {
    "species": "Species",
    "zebrafish_load": "Load",
    "zebrafish_results": "Results",
    "mouse_load": "Load",
    "mouse_analysis": "Results",
}


@st.cache_data
def _data_uri(path: Path) -> str:
    mime = "image/svg+xml" if path.suffix == ".svg" else "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def _go(page: str) -> None:
    st.session_state.page = page


def _reset_to_species() -> None:
    for key in ("species", "result", "file_name", "mouse_file"):
        st.session_state.pop(key, None)
    st.session_state.upload_key = st.session_state.get("upload_key", 0) + 1
    _go("species")


def _style() -> None:
    st.markdown(
        f"""
        <style>
        [data-testid="stHeader"] {{ background: {PANEL_CHROME}; border-bottom: 1px solid {CHROME_LINE}; }}
        [data-testid="stSidebar"] {{ background: {PANEL_CHROME}; border-right: 1px solid {CHROME_LINE}; }}
        [data-testid="stSidebar"] [data-testid="stSidebarContent"] {{ padding-top: 0.5rem; }}
        .block-container {{ padding-top: 3.2rem; max-width: 1100px; }}
        .cvz-brand {{ display:flex; align-items:center; gap:10px; font-weight:600; font-size:1.05rem;
                      color:{TEXT}; margin: 0 0 1.25rem 0.25rem; }}
        .cvz-brand img {{ width:30px; height:30px; }}
        .cvz-step {{ display:flex; align-items:center; gap:12px; padding:8px 10px; border-radius:8px;
                     color:{TEXT_MUTED}; margin-bottom:4px; font-size:0.95rem; }}
        .cvz-step img {{ width:26px; height:26px; opacity:0.55; }}
        .cvz-step.active {{ background:{CHROME_BUTTON}; color:{TEXT}; }}
        .cvz-step.active img {{ opacity:1; }}
        .cvz-step .dot {{ width:26px; text-align:center; font-weight:700; }}
        .cvz-note {{ color:{TEXT_MUTED}; font-size:0.8rem; margin-top:1.5rem; }}
        .cvz-center {{ text-align:center; }}
        .cvz-logo {{ display:block; margin: 6vh auto 0.5rem auto; width:150px; }}
        .cvz-hint {{ text-align:center; font-size:1.35rem; color:{TEXT}; margin-bottom:1rem; }}
        .cvz-title {{ text-align:center; font-weight:700; font-size:1.15rem; margin:0.2rem 0 0.8rem 0; }}
        .cvz-label {{ text-align:center; color:{TEXT}; margin: 18vh 0 0.25rem 0; }}
        .cvz-placeholder {{ border:1px solid {CHROME_LINE}; border-radius:6px; padding:1.5rem;
                            color:{TEXT_MUTED}; text-align:center; margin-bottom:1.25rem; }}
        .stButton > button, .stDownloadButton > button {{ background:{CHROME_BUTTON}; border:1px solid {CHROME_LINE};
                            color:{TEXT}; }}
        .stButton > button:hover, .stDownloadButton > button:hover {{ border-color:{ACCENT}; color:{TEXT}; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _sidebar(page: str) -> None:
    species = st.session_state.get("species")
    icons = {
        "Species": None,
        "Load": "sidebar_verify_dark_{}.svg",
        "Results": "sidebar_view_output_dark_{}.svg",
    }
    current = STEPS[page]
    rows = []
    for label, icon in icons.items():
        active = label == current
        if icon:
            img = f'<img src="{_data_uri(IMAGES / icon.format("active" if active else "inactive"))}">'
        else:
            img = '<span class="dot">1</span>'
        rows.append(f'<div class="cvz-step{" active" if active else ""}">{img}<span>{label}</span></div>')
    with st.sidebar:
        st.markdown(
            f'<div class="cvz-brand"><img src="{_data_uri(IMAGES / "fish1.png")}">CV Zebrafish</div>'
            + "".join(rows)
            + f'<div class="cvz-note">Web prototype (#136){" · " + species if species else ""}</div>',
            unsafe_allow_html=True,
        )


def _back_row(target_label: str = "Back") -> bool:
    return st.button(target_label, key=f"back_{st.session_state.page}", width="content")


def _logo(name: str) -> None:
    st.markdown(f'<img class="cvz-logo" src="{_data_uri(IMAGES / name)}">', unsafe_allow_html=True)


# ----- pages -----

def page_species() -> None:
    st.markdown('<div class="cvz-label">Species</div>', unsafe_allow_html=True)
    _, mid, _ = st.columns([2, 1, 2])
    with mid:
        choice = st.selectbox("Species", SPECIES, index=0, label_visibility="collapsed")
        if st.button("Continue", width="stretch"):
            st.session_state.species = choice
            _go("zebrafish_load" if choice == "Zebrafish" else "mouse_load")
            st.rerun()


def page_zebrafish_load() -> None:
    if _back_row():
        _reset_to_species()
        st.rerun()
    _logo("fish1.png")
    st.markdown('<div class="cvz-hint">+ Load DeepLabCut CSV</div>', unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        upload = st.file_uploader(
            "DeepLabCut CSV", type=["csv"], label_visibility="collapsed",
            key=f"zf_upload_{st.session_state.get('upload_key', 0)}",
        )
        use_sample = st.button("Use the bundled sample file", width="stretch")
        with st.expander("Config (optional)"):
            cfg_upload = st.file_uploader("Config JSON", type=["json"], key="zf_config")
            st.caption("Defaults to the sample BaseConfig.json.")

    if upload is None and not use_sample:
        return

    config = load_sample_config()
    if cfg_upload is not None:
        try:
            config = json.loads(cfg_upload.getvalue())
        except json.JSONDecodeError as exc:
            st.error(f"Config isn't valid JSON: {exc}")
            return

    data, name = (upload.getvalue(), upload.name) if upload is not None else (SAMPLE_CSV_PATH.read_bytes(), SAMPLE_CSV_PATH.name)
    with st.spinner("Running analysis…"):
        result = analyze_csv_bytes(data, config, filename=name)
    if not result.ok:
        for e in result.errors:
            st.error(e)
        return
    st.session_state.result = result
    st.session_state.file_name = name
    _go("zebrafish_results")
    st.rerun()


def page_zebrafish_results() -> None:
    if _back_row("Load another file"):
        st.session_state.pop("result", None)
        st.session_state.upload_key = st.session_state.get("upload_key", 0) + 1
        _go("zebrafish_load")
        st.rerun()

    result = st.session_state.result
    results, config, name = result.results, result.config, st.session_state.file_name
    st.markdown('<div class="cvz-title">Results</div>', unsafe_allow_html=True)
    st.caption(f"{name} · {len(results):,} frames · {results.shape[1]} result columns")
    for w in result.warnings:
        st.warning(w)

    st.subheader("Summary")
    st.dataframe(
        summary_table(results),
        hide_index=True,
        width="stretch",
        column_config={c: st.column_config.NumberColumn(format="%.4g") for c in ("Mean", "Min", "Max")},
    )

    st.subheader("Fin angles + tail distance")
    last = len(results) - 1
    default_end = min(last, (config.get("time_ranges") or [[0, last]])[0][1])
    start, end = st.slider("Frame range", 0, last, (0, default_end))
    fig, fig_warnings = fin_tail_figure(results, {**config, "time_ranges": [[start, end]]})
    for w in fig_warnings:
        st.caption(w)
    if fig is not None:
        fig.update_layout(template="plotly_dark", paper_bgcolor=PANEL_MAIN, plot_bgcolor=PANEL_MAIN)
        st.plotly_chart(fig, width="stretch")

    with st.expander("All result columns"):
        # Some result columns mix numbers and per-bout lists; show those as text.
        display = results.copy()
        for col in display.columns[display.dtypes == object]:
            display[col] = display[col].astype(str)
        st.dataframe(display, width="stretch", height=320)
    st.download_button(
        "Download results CSV",
        results.to_csv(index=False).encode("utf-8"),
        file_name=f"{Path(name).stem}_results.csv",
        mime="text/csv",
    )


def page_mouse_load() -> None:
    if _back_row():
        _reset_to_species()
        st.rerun()
    _logo("mouse.png")
    st.markdown('<div class="cvz-hint">+ Load DLC File</div>', unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        upload = st.file_uploader(
            "DeepLabCut output", type=["h5", "csv"], label_visibility="collapsed",
            key=f"mouse_upload_{st.session_state.get('upload_key', 0)}",
        )
    if upload is not None:
        # TODO(#118-followup): parse the DLC file once the mouse measurements are confirmed.
        st.session_state.mouse_file = upload.name
        _go("mouse_analysis")
        st.rerun()


def page_mouse_analysis() -> None:
    if _back_row():
        _reset_to_species()
        st.rerun()
    st.markdown('<div class="cvz-title">Mouse Analysis</div>', unsafe_allow_html=True)
    st.text_input("DeepLabCut File", st.session_state.mouse_file, disabled=True)
    st.markdown("**Parameters (coming soon)**")
    st.markdown('<div class="cvz-placeholder">&nbsp;</div>', unsafe_allow_html=True)
    st.markdown("**Results**")
    st.markdown(
        '<div class="cvz-placeholder" style="padding:5rem 1rem;">Results will appear here</div>',
        unsafe_allow_html=True,
    )


PAGES = {
    "species": page_species,
    "zebrafish_load": page_zebrafish_load,
    "zebrafish_results": page_zebrafish_results,
    "mouse_load": page_mouse_load,
    "mouse_analysis": page_mouse_analysis,
}

st.set_page_config(page_title="CV Zebrafish", page_icon=str(IMAGES / "fish1.png"), layout="wide")
st.session_state.setdefault("page", "species")
_style()
_sidebar(st.session_state.page)
PAGES[st.session_state.page]()
