

import os
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

# --- Output initialization ---
def init_output_folder(config):
    base_path = config.get("results_path", "results")
    os.makedirs(base_path, exist_ok=True)
    output_folder = os.path.join(base_path, "output_v1")
    os.makedirs(output_folder, exist_ok=True)
    return output_folder

# --- Excel export ---
def save_results_to_excel(df, output_folder):
    file_path = os.path.join(output_folder, "results.xlsx")
    df.to_excel(file_path, index=False)
    print(f"[INFO] Results saved to {file_path}")

# --- Plotting functions ---
def plot_fin_and_tail(df, output_folder, config):
    fig = go.Figure()
    if config.get("show_left_fin_angle", True):
        fig.add_trace(go.Scatter(x=df["Time"], y=df["LF_Angle"], mode="lines", name="Left Fin Angle"))
    if config.get("show_right_fin_angle", True):
        fig.add_trace(go.Scatter(x=df["Time"], y=df["RF_Angle"], mode="lines", name="Right Fin Angle"))
    if config.get("show_tail_distance", True) and "Tail_Distance" in df:
        fig.add_trace(go.Scatter(x=df["Time"], y=df["Tail_Distance"], mode="lines", name="Tail Distance"))
    fig.update_layout(title="Fin Angles and Tail Distance", xaxis_title="Frame", yaxis_title="Angle/Distance")
    file_path = os.path.join(output_folder, "fin_and_tail_plotly.png")
    pio.write_image(fig, file_path)
    html_path = os.path.join(output_folder, "fin_and_tail_plotly.html")
    fig.write_html(html_path)
    print(f"[INFO] Plot saved to {file_path} and {html_path}")

def plot_head_yaw(df, output_folder, config):
    if "HeadYaw" in df:
        fig = go.Figure(go.Scatter(x=df["Time"], y=df["HeadYaw"], mode="lines", name="Head Yaw"))
        fig.update_layout(title="Head Yaw Over Time", xaxis_title="Frame", yaxis_title="Yaw (deg)")
        file_path = os.path.join(output_folder, "head_yaw_plotly.png")
        pio.write_image(fig, file_path)
        html_path = os.path.join(output_folder, "head_yaw_plotly.html")
        fig.write_html(html_path)
        print(f"[INFO] Head yaw plot saved to {file_path} and {html_path}")

def plot_spines(df, output_folder, config):
    # Example for plotting segments of spine angles if present in df columns
    for col in df.columns:
        if col.startswith("TailAngle_"):
            fig = go.Figure(go.Scatter(x=df["Time"], y=df[col], mode="lines", name=col))
            fig.update_layout(title=f"{col} Over Time", xaxis_title="Frame", yaxis_title="Angle (deg)")
            file_path = os.path.join(output_folder, f"{col}_plotly.png")
            html_path = os.path.join(output_folder, f"{col}_plotly.html")
            pio.write_image(fig, file_path)
            fig.write_html(html_path)
            print(f"[INFO] {col} plot saved to {file_path} and {html_path}")

# --- Main output/graph routine ---
def make_outputs(df, config):
    output_folder = init_output_folder(config)
    if config.get("save_excel", True):
        save_results_to_excel(df, output_folder)
    if config.get("show_fin_and_tail", True):
        plot_fin_and_tail(df, output_folder, config)
    if config.get("show_head_yaw", True):
        plot_head_yaw(df, output_folder, config)
    if config.get("show_spines", True):
        plot_spines(df, output_folder, config)
    print("[INFO] All requested outputs have been generated.")

# --- You can extend this for more graph options! ---



