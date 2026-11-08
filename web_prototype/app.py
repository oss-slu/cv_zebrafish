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
    AnalysisResult,
    FishColorMap,
    LoadedFish,
    analyze_csv_bytes,
    analyze_fish_files,
    build_comparison_table,
    build_overlay_figure,
    comparison_table_csv_bytes,
    fin_tail_figure,
    get_parameter_names,
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

# stlite (the browser-only / GitHub Pages build) runs Python as WebAssembly in the browser.
IN_BROWSER = sys.platform == "emscripten"
PROTOTYPE_NOTE = (
    "Prototype for issue #136 · covers one zebrafish analysis · "
    + ("files you upload stay in your browser" if IN_BROWSER
       else "files are processed by the computer running this app and not stored")
)

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
    for key in ("species", "result", "file_name", "mouse_file", "loaded_fish"):
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
    st.markdown(f'<div class="cvz-center cvz-note">{PROTOTYPE_NOTE}</div>', unsafe_allow_html=True)


def page_zebrafish_load() -> None:
    if _back_row():
        _reset_to_species()
        st.rerun()
    _logo("fish1.png")
    st.markdown('<div class="cvz-hint">+ Load DeepLabCut CSV</div>', unsafe_allow_html=True)

    existing = st.session_state.get("loaded_fish", [])
    if existing:
        st.info(f"Session currently has {len(existing)} fish ({', '.join(f.label for f in existing)}). Upload more to add them.")

    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        uploads = st.file_uploader(
            "DeepLabCut CSV(s)",
            type=["csv"],
            accept_multiple_files=True,
            label_visibility="collapsed",
            key=f"zf_upload_{st.session_state.get('upload_key', 0)}",
        )

        run_uploads = False
        if uploads:
            st.caption(f"{len(uploads)} file(s) selected: {', '.join(u.name for u in uploads)}")
            st.caption("Tip: Hold Ctrl/Cmd in the file chooser or drag & drop multiple CSVs to select several at once.")
            run_uploads = st.button("Run Analysis", type="primary", width="stretch")

        use_sample = st.button("Use the bundled sample file", width="stretch")
        use_sample_multi = st.button("Use sample files (2-fish comparison demo)", width="stretch")

        with st.expander("Config (optional)"):
            cfg_upload = st.file_uploader("Config JSON", type=["json"], key="zf_config")
            st.caption("Defaults to the sample BaseConfig.json.")

    if not run_uploads and not use_sample and not use_sample_multi:
        return

    config = load_sample_config()
    if cfg_upload is not None:
        try:
            config = json.loads(cfg_upload.getvalue())
        except json.JSONDecodeError as exc:
            st.error(f"Config isn't valid JSON: {exc}")
            return

    if use_sample and not run_uploads and not use_sample_multi:
        files = [(SAMPLE_CSV_PATH.name, SAMPLE_CSV_PATH.read_bytes())]
    elif use_sample_multi:
        raw = SAMPLE_CSV_PATH.read_bytes()
        files = [("fish1_control.csv", raw), ("fish2_treated.csv", raw)]
    else:
        files = [(u.name, u.getvalue()) for u in (uploads or [])]

    with st.spinner("Running analysis…"):
        loaded_fish, failures = analyze_fish_files(
            files, config, existing_fish=existing
        )

    for fname, errors in failures:
        st.error(f"Failed to load {fname}: " + " ".join(errors))

    if not loaded_fish:
        return

    st.session_state.loaded_fish = loaded_fish
    st.session_state.result = AnalysisResult(
        ok=True,
        results=loaded_fish[0].results,
        config=config,
        warnings=loaded_fish[0].warnings,
    )
    st.session_state.file_name = loaded_fish[0].source_file
    _go("zebrafish_results")
    st.rerun()


def page_zebrafish_results() -> None:
    c_back, c_add = st.columns([1, 1])
    with c_back:
        if st.button("Load another file", key="back_zebrafish_results"):
            st.session_state.pop("result", None)
            st.session_state.pop("loaded_fish", None)
            st.session_state.upload_key = st.session_state.get("upload_key", 0) + 1
            _go("zebrafish_load")
            st.rerun()
    with c_add:
        if st.button("+ Add more fish to comparison"):
            st.session_state.upload_key = st.session_state.get("upload_key", 0) + 1
            _go("zebrafish_load")
            st.rerun()

    loaded_fish: list[LoadedFish] = st.session_state.get("loaded_fish", [])
    if not loaded_fish and "result" in st.session_state:
        res = st.session_state.result
        loaded_fish = [
            LoadedFish(
                fish_id="fish_1",
                label=Path(st.session_state.file_name).stem,
                source_file=st.session_state.file_name,
                results=res.results,
                warnings=res.warnings,
            )
        ]
        st.session_state.loaded_fish = loaded_fish

    if not loaded_fish:
        st.info("No fish data loaded.")
        return

    config = st.session_state.result.config if "result" in st.session_state else load_sample_config()

    st.markdown('<div class="cvz-title">Results</div>', unsafe_allow_html=True)

    if len(loaded_fish) == 1:
        fish = loaded_fish[0]
        results = fish.results
        st.caption(f"{fish.source_file} · {len(results):,} frames · {results.shape[1]} result columns")
        for w in fish.warnings:
            st.warning(w)

        st.subheader("Summary")
        st.dataframe(
            summary_table(results),
            hide_index=True,
            width="stretch",
            column_config={
                "mean": st.column_config.NumberColumn("Mean", format="%.4g"),
                "median": st.column_config.NumberColumn("Median", format="%.4g"),
                "parameter": st.column_config.TextColumn("Parameter"),
                "units": st.column_config.TextColumn("Units"),
            },
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
            display = results.copy()
            for col in display.columns[display.dtypes == object]:
                display[col] = display[col].astype(str)
            st.dataframe(display, width="stretch", height=320)

        st.download_button(
            "Download results CSV",
            results.to_csv(index=False).encode("utf-8"),
            file_name=f"{Path(fish.source_file).stem}_results.csv",
            mime="text/csv",
        )
    else:
        st.caption(f"{len(loaded_fish)} fish loaded for analysis and comparison")
        tab_comparison, tab_individual = st.tabs(["Comparison", "Individual Fish"])

        with tab_comparison:
            with st.expander("Loaded Fish & Labels", expanded=True):
                labels_changed = False
                for i, fish in enumerate(list(loaded_fish)):
                    c_label, c_file, c_del = st.columns([3, 4, 1])
                    new_val = c_label.text_input(
                        f"Label for {fish.fish_id}",
                        value=fish.label,
                        key=f"fish_lbl_{fish.fish_id}",
                        label_visibility="collapsed",
                    )
                    if new_val and new_val != fish.label:
                        fish.label = new_val
                        labels_changed = True
                    c_file.caption(f"{fish.source_file} ({len(fish.results):,} frames)")
                    if c_del.button("Remove", key=f"del_{fish.fish_id}"):
                        loaded_fish.remove(fish)
                        st.session_state.loaded_fish = loaded_fish
                        st.rerun()
                if labels_changed:
                    st.session_state.loaded_fish = loaded_fish

            if not loaded_fish:
                st.info("All fish were removed. Load new files to continue.")
                return

            st.subheader("Fish Comparison Table")
            all_labels = [f.label for f in loaded_fish]
            selected_labels = st.multiselect(
                "Filter fish",
                options=all_labels,
                default=all_labels,
                key="comp_fish_filter",
            )
            fish_to_compare = [f for f in loaded_fish if f.label in selected_labels]

            if not fish_to_compare:
                st.warning("Select at least one fish to view comparison.")
            else:
                avail_params = get_parameter_names(fish_to_compare)
                selected_params = st.multiselect(
                    "Filter parameters",
                    options=avail_params,
                    default=avail_params,
                    key="comp_param_filter",
                )
                if not selected_params:
                    st.warning("Select at least one parameter to view.")
                else:
                    comp_table = build_comparison_table(fish_to_compare, selected_params)
                    st.dataframe(
                        comp_table,
                        hide_index=True,
                        width="stretch",
                    )
                    csv_bytes = comparison_table_csv_bytes(comp_table, fish_to_compare)
                    st.download_button(
                        "Download comparison CSV",
                        csv_bytes,
                        file_name="fish_comparison.csv",
                        mime="text/csv",
                    )

            st.subheader("Signal Overlay Plot")
            if fish_to_compare:
                plotable_signals = ["LF_Angle", "RF_Angle", "Tail_Distance", "HeadYaw"]
                overlay_param = st.selectbox("Select signal trace", options=plotable_signals, key="overlay_param")
                cmap = FishColorMap()
                overlay_fig = build_overlay_figure(fish_to_compare, overlay_param, cmap)
                overlay_fig.update_layout(
                    template="plotly_dark",
                    paper_bgcolor=PANEL_MAIN,
                    plot_bgcolor=PANEL_MAIN,
                )
                st.plotly_chart(overlay_fig, width="stretch")

        with tab_individual:
            fish_options = {f.label: f for f in loaded_fish}
            chosen_label = st.selectbox("Select fish to view", options=list(fish_options.keys()))
            chosen_fish = fish_options[chosen_label]
            ind_results = chosen_fish.results

            st.caption(f"{chosen_fish.source_file} · {len(ind_results):,} frames · {ind_results.shape[1]} result columns")
            for w in chosen_fish.warnings:
                st.warning(w)

            st.subheader("Summary")
            st.dataframe(
                summary_table(ind_results),
                hide_index=True,
                width="stretch",
                column_config={
                    "mean": st.column_config.NumberColumn("Mean", format="%.4g"),
                    "median": st.column_config.NumberColumn("Median", format="%.4g"),
                    "parameter": st.column_config.TextColumn("Parameter"),
                    "units": st.column_config.TextColumn("Units"),
                },
            )

            st.subheader("Fin angles + tail distance")
            last = len(ind_results) - 1
            default_end = min(last, (config.get("time_ranges") or [[0, last]])[0][1])
            start, end = st.slider("Frame range", 0, last, (0, default_end), key=f"range_{chosen_fish.fish_id}")
            fig, fig_warnings = fin_tail_figure(ind_results, {**config, "time_ranges": [[start, end]]})
            for w in fig_warnings:
                st.caption(w)
            if fig is not None:
                fig.update_layout(template="plotly_dark", paper_bgcolor=PANEL_MAIN, plot_bgcolor=PANEL_MAIN)
                st.plotly_chart(fig, width="stretch")

            with st.expander("All result columns"):
                display = ind_results.copy()
                for col in display.columns[display.dtypes == object]:
                    display[col] = display[col].astype(str)
                st.dataframe(display, width="stretch", height=320)

            st.download_button(
                f"Download {chosen_fish.label} results CSV",
                ind_results.to_csv(index=False).encode("utf-8"),
                file_name=f"{Path(chosen_fish.source_file).stem}_results.csv",
                mime="text/csv",
                key=f"dl_{chosen_fish.fish_id}",
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
