# Client Request Notes (latest meeting)

- Graph editing & analysis: allow lookup of x/y values on points, set/adjust graph points, find local/global minima and maxima over ranges, zoom/focus on specific ranges, export ranged data to Excel, and capture clickable points in order for later calculations.
- Configurability: make graph generation configurable in the GUI and JSON (e.g., include/exclude fin angles or spine data based on user choice).
- Multiple CSV support: load multiple CSVs per session, view separate graphs per file, and optionally superimpose graphs across CSVs with color keys to distinguish fish; needs code to blend datasets.
- Media: include a zebrafish silhouette/picture in the experience.
- UX/installation: aim for an easy-to-launch, visually appealing app (installable/icon to click); consider broader student usability.
- Generalization: stakeholders want the tool to ingest arbitrary tabular data (CSV/XLS/XLSX/Excel) and normalize schemas so graphs can be produced beyond this research context; need to clarify feasible schema mapping vs. format-driven auto-parsing.
- File formats: question about CSV vs XLS/XLSX parity; desire a normalization layer for any tabular format.
- Parameter transparency: stakeholders want a list of all parameters once graphs are available.
- Persistence: they expect to save/download graphs and record CSV locations plus parameter sets per output (sessions), potentially in a database to revisit experiments quickly.
- Timeline expectation: quoted ~1 month (two sprints) to deliver viewable, downloadable, interactive graphs.
