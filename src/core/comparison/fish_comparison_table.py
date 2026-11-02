"""Build, filter and export the fish-to-fish comparison table.

Mean and median values come from the shared summary statistics (issue #132), so
the table always matches the single-fish results.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Union

import pandas as pd

from src.core.analysis.summary_statistics import compute_summary_statistics_df
from src.core.comparison.fish_data import LoadedFish

FIXED_COLUMNS = ["Parameter", "Unit", "Statistic"]
STATISTICS = ("mean", "median")


def get_parameter_names(fish_list: Sequence[LoadedFish]) -> List[str]:
    """Return every summarized parameter across the fish, in first-seen order."""
    return _ordered_parameters(_summarize_fish(fish_list).values())


def build_comparison_table(
    fish_list: Sequence[LoadedFish],
    parameters: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """
    Build a table with one mean row and one median row per parameter.

    Args:
        fish_list: Fish to include, in column order.
        parameters: Parameters to include (default: all available).

    Returns:
        DataFrame with columns Parameter, Unit, Statistic, then one column per
        fish label. A fish without data for a parameter gets NaN.

    Raises:
        ValueError: If fish labels are not unique or clash with a fixed column.
    """
    labels = [fish.label for fish in fish_list]
    if len(set(labels)) != len(labels):
        raise ValueError("Fish labels must be unique.")
    if set(labels) & set(FIXED_COLUMNS):
        raise ValueError(f"Fish labels cannot be named {', '.join(FIXED_COLUMNS)}.")

    summaries = _summarize_fish(fish_list)
    parameter_names = (
        list(parameters) if parameters is not None else _ordered_parameters(summaries.values())
    )

    rows = []
    for parameter in parameter_names:
        unit = _first_unit(summaries.values(), parameter)
        for statistic in STATISTICS:
            row = {"Parameter": parameter, "Unit": unit, "Statistic": statistic}
            for label, summary in summaries.items():
                row[label] = (
                    float(summary.at[parameter, statistic])
                    if parameter in summary.index
                    else float("nan")
                )
            rows.append(row)
    return pd.DataFrame(rows, columns=FIXED_COLUMNS + labels)


def export_comparison_table(
    table: pd.DataFrame,
    fish_list: Sequence[LoadedFish],
    output_path: Union[str, Path],
) -> Path:
    """
    Write the comparison table to a ``.csv`` or ``.xlsx`` file.

    Two header rows ("Fish ID" and "Source file") are written above the data so
    each fish column is traceable. CSV files use a UTF-8 BOM so Excel opens them
    correctly.

    Raises:
        ValueError: For an unsupported file extension or a table column with no
            matching fish.
    """
    path = Path(output_path)
    fish_by_label = {fish.label: fish for fish in fish_list}
    labels = [column for column in table.columns if column not in FIXED_COLUMNS]
    missing = [label for label in labels if label not in fish_by_label]
    if missing:
        raise ValueError(f"No fish found for table columns: {', '.join(missing)}")

    header_rows = [
        {"Parameter": "Fish ID", **{label: fish_by_label[label].fish_id for label in labels}},
        {
            "Parameter": "Source file",
            **{label: fish_by_label[label].source_file for label in labels},
        },
    ]
    export_frame = pd.concat(
        [pd.DataFrame(header_rows, columns=table.columns), table.astype(object)],
        ignore_index=True,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        export_frame.to_csv(path, index=False, encoding="utf-8-sig")
    elif suffix == ".xlsx":
        export_frame.to_excel(path, index=False)
    else:
        raise ValueError(f"Unsupported export format '{path.suffix}'; use .csv or .xlsx")
    return path


def _summarize_fish(fish_list: Sequence[LoadedFish]) -> Dict[str, pd.DataFrame]:
    """Return label -> summary statistics indexed by parameter name."""
    return {
        fish.label: compute_summary_statistics_df(fish.results).set_index("parameter")
        for fish in fish_list
    }


def _ordered_parameters(summaries: Iterable[pd.DataFrame]) -> List[str]:
    names: List[str] = []
    for summary in summaries:
        for parameter in summary.index:
            if parameter not in names:
                names.append(parameter)
    return names


def _first_unit(summaries: Iterable[pd.DataFrame], parameter: str) -> str:
    """Return the first non-empty unit found for a parameter."""
    for summary in summaries:
        if parameter in summary.index:
            unit = summary.at[parameter, "units"]
            if pd.notna(unit) and str(unit):
                return str(unit)
    return ""