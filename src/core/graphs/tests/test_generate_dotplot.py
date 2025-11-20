#!/usr/bin/env python3
"""
Minimal convenience script to generate a dot-plot using the project's loader + plotter.
This is intentionally short and close to the snippet you provided.
Run from repo root, with your venv active:

python plot_image_generation/generate_dotplot_simple.py

Adjust csv_path / config_path variables in the script or call it with an editor.
"""
import os
import sys

# Ensure package imports find `src/`
sys.path.insert(0, os.path.join(os.getcwd(), "src"))

from core.graphs.data_loader import GraphDataLoader
from core.graphs.loader_bundle import GraphDataBundle
from core.graphs.io import get_output_context
from core.graphs.plots.dotplot import render_dot_plot

# --- Change these if you want different inputs ---
csv_path = "data/samples/csv/calculated_data_enriched.csv"
config_path = "data/samples/jsons/BaseConfig.json"

# Create loader + bundle
loader = GraphDataLoader(csv_path, config_path)
bundle = GraphDataBundle.from_loader(loader)

# choose two numeric series from calculated values
calc = bundle.calculated_values
x = calc.get("tailDistances")
y = calc.get("leftFinAngles")
if x is None or y is None:
    print("Calculated series missing. Available keys:", list(calc.keys()))
    raise SystemExit("Calculated values missing: ensure 'tailDistances' and 'leftFinAngles' exist in the enriched CSV.")

# Get output context (will create Results N under 'results/' unless config['bulk_input'] True)
ctx = get_output_context(bundle.config, base_path="results")

# Render and save PNG + HTML (uses Plotly write_image when available)
try:
    result = render_dot_plot(
        x,
        y,
        name_x="tailDist",
        name_y="leftFinAng",
        units_x="m",
        units_y="deg",
        ctx=ctx,
        filename="tail_vs_leftfin_dotplot",
    )
except ValueError as exc:
    # Common failure: kaleido not installed which raises a ValueError from plotly
    msg = str(exc)
    if "kaleido" in msg.lower():
        print("kaleido not available; falling back to HTML-only output")
        # Try to ensure HTML exists: render figure without ctx and write HTML manually
        fallback = render_dot_plot(x, y, name_x="tailDist", name_y="leftFinAng", units_x="m", units_y="deg", ctx=None)
        output_base = "tail_vs_leftfin_dotplot"
        output_base = output_base.replace(" ", "_")
        html_path = os.path.join(ctx.output_folder, f"{output_base}.html")
        os.makedirs(ctx.output_folder, exist_ok=True)
        fallback.figure.write_html(html_path)
        print(f"Wrote HTML-only plot to: {html_path}")
        print("Install kaleido to enable PNG export: pip install -U kaleido")
        result = fallback
    else:
        raise

print("Wrote plot files to:", ctx.output_folder)
print("Output base name:", result.output_base)
print("Point count:", result.point_count)
