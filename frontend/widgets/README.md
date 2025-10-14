# GraphViewerScene

## Overview
GraphViewerScene is a PyQt5 widget for displaying Plotly graphs as static images within a GUI.
It provides a simple, scrollable interface with a sidebar of graph names and a main display area that renders the selected figure.

This component is designed for integration into larger applications (e.g., analysis dashboards or visualization tools).
It also includes graceful handling of empty or error states such as “No graphs available” or “Failed to render.”

---------------------------------------------

## Structure

GraphViewerScene (QWidget)
│
├── QListWidget self.list
│     ↳ Displays graph names in a vertical list
│
├── QScrollArea self.scroll
│     └── QLabel self.image_label
│           ↳ Displays the static PNG of the selected graph
│
├── Dict[str, go.Figure] self._graphs
│     ↳ Holds Plotly Figure objects currently loaded
│
└── Core Methods:
      • set_graphs(graphs)
      • add_graph(name, figure)
      • _show_graph(name)
      • _show_empty_state(message)

---------------------------------------------

## Usage

1. Instantiate the widget

from GraphViewerScene import GraphViewerScene
viewer = GraphViewerScene()

2. Load graphs

Option A — Set multiple graphs at once

import plotly.graph_objs as go

graphs = {
    "Line Plot": go.Figure(go.Scatter(x=[1, 2, 3], y=[3, 1, 4])),
    "Bar Chart": go.Figure(go.Bar(x=["A", "B", "C"], y=[5, 2, 7]))
}
viewer.set_graphs(graphs)

Option B — Add graphs one by one

fig = go.Figure(go.Scatter(x=[0, 1, 2], y=[4, 1, 3]))
viewer.add_graph("Example Graph", fig)

3. Embed into your PyQt window

---------------------------------------------

## Behavior Summary

State | Behavior
------|----------
No graphs loaded | Sidebar disabled, message “No graphs available” shown
Graphs loaded | Sidebar lists all graphs; clicking one displays it
Missing graph | Shows “Missing graph” message
Render failure | Displays a clear kaleido error message
Window resized | Graph automatically rescales to fit width

---------------------------------------------

## Requirements

pip install pyqt5 plotly kaleido

Dependencies:
- PyQt5 → GUI framework
- Plotly → For creating figures
- Kaleido → Converts Plotly figures to PNG for static rendering

---------------------------------------------

## Quick Test Script

To verify the widget works both when empty and with data, create a file named run_graph_viewer.py:

import sys
from PyQt5.QtWidgets import QApplication
import plotly.graph_objs as go
from GraphViewerScene import GraphViewerScene

app = QApplication(sys.argv)

viewer = GraphViewerScene()

# Uncomment this block to test populated state
graphs = {
    "Sample Line": go.Figure(go.Scatter(x=[1, 2, 3], y=[2, 1, 4], mode="lines+markers")),
    "Sample Bars": go.Figure(go.Bar(x=["A", "B", "C"], y=[5, 2, 6]))
}
viewer.set_graphs(graphs)

viewer.resize(1000, 700)
viewer.show()
sys.exit(app.exec_())

Run:
python run_graph_viewer.py

---------------------------------------------

## File Summary

File | Description
------|-------------
GraphViewerScene.py | Main PyQt widget for viewing Plotly graphs
run_graph_viewer.py | Optional standalone demo for quick testing
README.txt | This documentation file

---------------------------------------------

## Notes

- The viewer scales images dynamically as the window resizes.
- If Kaleido isn’t installed, the viewer will display a clear message rather than crashing.
- The sidebar disables automatically when no graphs are loaded.
- Works with the math-model → graph-generation pipeline by simply calling something like:

viewer.graphs = "generated_graphs"
viewer.refresh()

