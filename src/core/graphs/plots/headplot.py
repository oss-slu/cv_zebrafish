from __future__ import annotations

import math
import os
import webbrowser
from dataclasses import dataclass
from typing import Sequence, Optional

import plotly.graph_objects as go

from ..io import OutputContext


@dataclass(frozen=True)
class HeadPlotResult:
    """Metadata returned after rendering a head plot."""
    figures: list[go.Figure]
    labels: list[str]
    output_base: Optional[str]


def rotate_point(origin: tuple[float, float], point: tuple[float, float], angle_deg: float) -> tuple[float, float]:
    """Rotate a point around an origin by a given angle in degrees."""
    ox, oy = origin
    px, py = point
    angle_rad = math.radians(angle_deg)
    qx = ox + math.cos(angle_rad) * (px - ox) - math.sin(angle_rad) * (py - oy)
    qy = oy + math.sin(angle_rad) * (px - ox) + math.cos(angle_rad) * (py - oy)
    return qx, qy


def plot_head(
    head_yaw: Sequence[float],
    left_fin_values: Sequence[float],
    right_fin_values: Sequence[float],
    time_ranges: Sequence[tuple[int, int]],
    head_settings: dict,
    cutoffs: dict,
    ctx: Optional[OutputContext] = None,
    open_plot: bool = False,
) -> HeadPlotResult:
    """
    Plot head frames at fin peaks with optional tabbed HTML output.
    """
    left_fin_cutoff = cutoffs["left_fin_angle"]
    right_fin_cutoff = cutoffs["right_fin_angle"]

    draw_offset = head_settings["plot_draw_offset"]
    remove_synced_peaks = head_settings["ignore_synchronized_fin_peaks"]
    sync_time_range = head_settings["sync_fin_peaks_range"]
    use_right_side_finpeaks = head_settings["fin_peaks_for_right_fin"]
    split_by_bout = head_settings["split_plots_by_bout"]

    head_rows_by_bout = []
    fin_values = right_fin_values if use_right_side_finpeaks else left_fin_values
    cutoff = right_fin_cutoff if use_right_side_finpeaks else left_fin_cutoff
    opposing_fin_values = left_fin_values if use_right_side_finpeaks else right_fin_values
    opposing_cutoff = left_fin_cutoff if use_right_side_finpeaks else right_fin_cutoff

    for start_index, end_index in time_ranges:
        current_head_rows = [start_index]
        on_peak = False
        current_max_val = 0
        current_max_index = 0
        for i in range(start_index, end_index + 1):
            if not on_peak and fin_values[i] > cutoff:
                current_max_val = fin_values[i]
                current_max_index = i
                on_peak = True
            elif on_peak and fin_values[i] > cutoff:
                if fin_values[i] > current_max_val:
                    current_max_val = fin_values[i]
                    current_max_index = i
            elif on_peak and fin_values[i] <= cutoff:
                valid_point = True
                if remove_synced_peaks:
                    for j in range(max(0, current_max_index - sync_time_range), min(current_max_index + sync_time_range, end_index)):
                        if opposing_fin_values[j] > opposing_cutoff:
                            valid_point = False
                if valid_point:
                    current_head_rows.append(current_max_index)
                on_peak = False
        head_rows_by_bout.append(current_head_rows)

    head_x_points = [-0.5, 0, 0.5, 0, 0, 0]
    head_y_points = [-1, 0, -1, 0, -5, -10]
    origin = (head_x_points[1], head_y_points[1])

    figures = []
    labels = []
    output_base = None

    if split_by_bout:
        for bout_num, head_rows in enumerate(head_rows_by_bout):
            fig = go.Figure()
            fig.update_yaxes(scaleanchor="x", scaleratio=1, visible=False)
            fig.update_xaxes(constrain="domain", visible=False)
            fig.update_layout(showlegend=False, title="Head Plot")

            current_offset = 0
            for row in head_rows:
                new_head_x = []
                new_head_y = []
                for px, py in zip(head_x_points, head_y_points):
                    nx, ny = rotate_point(origin, (px, py), -head_yaw[row])
                    new_head_x.append(nx + current_offset)
                    new_head_y.append(ny)
                current_offset += draw_offset
                fig.add_trace(go.Scatter(x=new_head_x, y=new_head_y, mode='lines', line=dict(color="black")))
            figures.append(fig)
            start, end = time_ranges[bout_num]
            label = f"head_plot_range_[{start},_{end}]"
            labels.append(label)

            if ctx:
                html_path = os.path.join(ctx.output_folder, f"{label}.html")
                png_path = os.path.join(ctx.output_folder, f"{label}.png")
                fig.write_html(html_path)
                try:
                    fig.write_image(png_path)
                except Exception as e:
                    print(f"Warning: Could not write PNG for {label}: {e}")
                    print("Hint: Upgrade plotly and kaleido: pip install -U plotly kaleido")
                output_base = "head_plot"

        if ctx:
            tabs_html = f"""
            <html>
            <head>
            <style>
            body {{ font-family: sans-serif; background-color: #f9f9f9; }}
            #tabs {{ margin-bottom: 10px; }}
            .tab-button {{ padding: 10px 16px; cursor: pointer; display: inline-block; background-color: #eee; border: 1px solid #ccc; border-bottom: none; margin-right: 5px; border-radius: 6px 6px 0 0; font-weight: bold; }}
            .tab-button.active {{ background-color: #fff; border-bottom: 1px solid #fff; }}
            .tab {{ display: none; }}
            .tab.active {{ display: block; }}
            </style>
            </head>
            <body>
            <div id="tabs">
            """
            for i, label in enumerate(labels):
                active_class = "active" if i == 0 else ""
                tabs_html += f'<div class="tab-button {active_class}" onclick="showTab({i})">{label}</div>'
            tabs_html += '</div>'
            for i, fig in enumerate(figures):
                fig_html = fig.to_html(include_plotlyjs=(i == 0), full_html=False)
                active_style = "active" if i == 0 else ""
                tabs_html += f'<div class="tab {active_style}">{fig_html}</div>'
            tabs_html += """
            <script>
            function showTab(index) {
                const tabs = document.getElementsByClassName('tab');
                const buttons = document.getElementsByClassName('tab-button');
                for (let i = 0; i < tabs.length; i++) {
                    tabs[i].classList.remove('active');
                    buttons[i].classList.remove('active');
                }
                tabs[index].classList.add('active');
                buttons[index].classList.add('active');
            }
            </script>
            </body>
            </html>
            """
            tabs_path = os.path.join(ctx.output_folder, "head_plots_tabbed.html")
            with open(tabs_path, 'w', encoding='utf-8') as f:
                f.write(tabs_html)
            if open_plot:
                webbrowser.open(tabs_path)
    else:
        fig = go.Figure()
        fig.update_layout(showlegend=False, title="Head Plot")
        current_offset = 0
        for head_rows in head_rows_by_bout:
            for row in head_rows:
                new_head_x = []
                new_head_y = []
                for px, py in zip(head_x_points, head_y_points):
                    nx, ny = rotate_point(origin, (px, py), -head_yaw[row])
                    new_head_x.append(nx + current_offset)
                    new_head_y.append(ny)
                current_offset += draw_offset
                fig.add_trace(go.Scatter(x=new_head_x, y=new_head_y, mode='lines', line=dict(color="black")))
        if ctx:
            html_path = os.path.join(ctx.output_folder, "head_plot_plotly.html")
            png_path = os.path.join(ctx.output_folder, "head_plot.png")
            fig.write_html(html_path)
            try:
                fig.write_image(png_path)
            except Exception as e:
                print(f"Warning: Could not write PNG: {e}")
                print("Hint: Upgrade plotly and kaleido: pip install -U plotly kaleido")
            output_base = "head_plot"
        if open_plot:
            fig.show()

    return HeadPlotResult(figures=figures, labels=labels, output_base=output_base)
  


    





