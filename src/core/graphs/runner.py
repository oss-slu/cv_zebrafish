"""
Graph runner/orchestrator for the modular plotting pipeline.

This runner is deliberately independent of the legacy `outputDisplay` module.
Plot modules can be passed in and invoked here as they come online.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional

from .io import OutputContext, get_output_context
from .loader_bundle import GraphDataBundle

# A plotter accepts the bundle + output context and returns arbitrary metadata.
Plotter = Callable[[GraphDataBundle, Optional[OutputContext]], Dict[str, Any]]


def run_all_graphs(bundle: GraphDataBundle, plotters: Optional[Iterable[Plotter]] = None) -> List[dict]:
    """
    Entry point for graph generation in the modular pipeline.

    Args:
        bundle: Structured data from the loader.
        plotters: Iterable of callables (bundle, ctx) -> metadata. Each plotter
                  is responsible for saving its own figures using the ctx.

    Returns:
        results_list: One dict per bout (initialized empty here, plotters can mutate/extend).
    """
    results_list: List[dict] = [{} for _ in range(len(bundle.time_ranges))]
    ctx: Optional[OutputContext] = get_output_context(bundle.config)

    if not plotters:
        return results_list  # No plots requested yet.

    for plot_fn in plotters:
        plot_fn(bundle, ctx)

    return results_list


__all__ = ["run_all_graphs", "Plotter"]
