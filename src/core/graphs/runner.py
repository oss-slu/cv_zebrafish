"""
Graph runner/orchestrator for the modular plotting pipeline.

This runner is deliberately independent of the legacy `outputDisplay` module.
Plot modules can be passed in and invoked here as they come online.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional

from .io import OutputContext, get_output_context
from .loader_bundle import GraphDataBundle
from .plots import render_fin_tail, render_spines

# A plotter accepts the bundle + output context and returns arbitrary metadata.
Plotter = Callable[[GraphDataBundle, Optional[OutputContext]], Dict[str, Any]]


def run_all_graphs(
    bundle: GraphDataBundle,
    plotters: Optional[Iterable[Plotter]] = None,
    ctx: Optional[OutputContext] = None,
) -> Dict[str, Any]:
    """
    Entry point for graph generation in the modular pipeline.

    Args:
        bundle: Structured data from the loader.
        plotters: Iterable of callables (bundle, ctx) -> metadata. Each plotter
                  is responsible for saving its own figures using the ctx.
        ctx: Optional output context override. If None, a standard results folder is used.

    Returns:
        results: Dict containing metadata from all plotters with keys like 'plot_name_1', 'plot_name_2', etc.
    """
    results: Dict[str, Any] = {}
    active_ctx: Optional[OutputContext] = ctx or get_output_context(bundle.config)

    active_plotters: List[Plotter] = list(plotters) if plotters is not None else get_default_plotters(bundle)

    if not active_plotters:
        return results  # No plots requested.

    for idx, plot_fn in enumerate(active_plotters):
        metadata = plot_fn(bundle, active_ctx)
        plot_name = getattr(plot_fn, '__name__', f'plot_{idx}')
        results[plot_name] = metadata

    return results


def get_default_plotters(bundle: GraphDataBundle) -> List[Plotter]:
    """
    Determine which plotters to run based on the bundle's config.

    Currently wires angle/distance plots and spine snapshots. Extend as new plot
    modules come online.
    """
    config = bundle.config or {}
    shown = config.get("shown_outputs", {})
    plotters: List[Plotter] = []
    if shown.get("show_angle_and_distance_plot", False):
        plotters.append(render_fin_tail)
    if shown.get("show_spines", False):
        plotters.append(render_spines)
    return plotters


__all__ = ["run_all_graphs", "Plotter", "get_default_plotters"]
