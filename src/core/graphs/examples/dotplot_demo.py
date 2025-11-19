"""
Example runner that generates a dot plot via the modular pipeline.

Usage:
    python -m src.core.graphs.examples.dotplot_demo --csv data/samples/csv/calculated_data_enriched.csv --config assets/sample_data/jsons/BaseConfig.json
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from ..data_loader import GraphDataLoader
from ..io import OutputContext
from ..loader_bundle import GraphDataBundle
from ..plots.dotplot import render_dot_plot
from ..runner import Plotter, run_all_graphs


def dot_plotter_factory(x_key: str, y_key: str, name_x: str, name_y: str, units_x: str, units_y: str) -> Plotter:
    """
    Create a plotter closure that pulls two calculated series and renders a dot plot.
    """

    def plotter(bundle: GraphDataBundle, ctx: Optional[OutputContext]):
        calc = bundle.calculated_values
        render_dot_plot(
            calc[x_key],
            calc[y_key],
            name_x=name_x,
            name_y=name_y,
            units_x=units_x,
            units_y=units_y,
            ctx=ctx,
            open_plot=bundle.config.get("open_plots", False),
        )
        return {}

    return plotter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a dot plot using the modular graph pipeline.")
    parser.add_argument("--csv", required=True, help="Path to enriched CSV (e.g., data/samples/csv/calculated_data_enriched.csv)")
    parser.add_argument("--config", required=True, help="Path to config JSON (e.g., assets/sample_data/jsons/BaseConfig.json)")
    parser.add_argument("--x-series", default="tailDistances", help="Key from calculated_values for x data")
    parser.add_argument("--y-series", default="leftFinAngles", help="Key from calculated_values for y data")
    parser.add_argument("--name-x", default="Tail Distance", help="Label for x axis")
    parser.add_argument("--name-y", default="Left Fin Angle", help="Label for y axis")
    parser.add_argument("--units-x", default="m", help="Units label for x axis")
    parser.add_argument("--units-y", default="deg", help="Units label for y axis")
    return parser.parse_args()


def ensure_example_output_context() -> OutputContext:
    output_dir = Path(__file__).resolve().parent / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "dotplot_demo.log"
    return OutputContext(output_folder=str(output_dir), log_path=str(log_path))


def main():
    args = parse_args()
    loader = GraphDataLoader(csv_path=args.csv, config_path=args.config)
    bundle = GraphDataBundle.from_loader(loader)
    plotter = dot_plotter_factory(args.x_series, args.y_series, args.name_x, args.name_y, args.units_x, args.units_y)
    ctx = ensure_example_output_context()
    run_all_graphs(bundle, plotters=[plotter], ctx=ctx)


if __name__ == "__main__":
    main()
