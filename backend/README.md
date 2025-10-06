CV_ZEBRAFISH DATABASE - README 

Overview:

This repo ingests DeepLabCut (DLC) CSV output into a SQLite database.
The new DB design adds provenance and reproducibility via run tracking and source file metadata, while keeping a tidy, analysis-ready table for pose points.

What the pipeline does:

-Parse DLC CSV with a 3-row header (header=[0,1,2]), normalize columns, and go wide → long so each row is (bodypart, frame).
-Validate coordinates/likelihoods, drop non-numeric rows, and keep likelihood in [0,1].
-Register the source file (path, SHA-256 hash, size, mtime) and open a run.
-Write rows to Fish_Data tagged with the current run_id.
-Index frequently-queried columns and mark the run finished.

Requirements:

Python 3.9+
pandas, sqlite3
DLC CSV exported with a 3-row header

How to run:

python3 "your_script.py"
Make sure Zebrafish_data.csv is in the working directory (or change the path in the script).

Data flow & validation:

-Reads: pd.read_csv("Zebrafish_data.csv", header=[0,1,2])
-Normalizes columns → (bodypart, coord); keeps only {x,y,likelihood}
-Drops rows where any of x,y,likelihood are NaN or non-numeric
-Keeps only 0 ≤ likelihood ≤ 1
-Writes to SQLite with to_sql(..., if_exists="append")
-Note: The helper file_hash() computes SHA-256 (even though the comment mentions SHA-1). The code and column are correct (SHA-256); the comment was outdated.


What changed vs. the old (PR # 13) DB:

1) Run tracking & provenance 
New: SourceFiles and Runs tables capture which file and which run produced each batch of rows.
Old: No concept of runs or source files.

2) No destructive overwrite 
New: Fish_Data uses if_exists="append" and includes run_id. You can ingest multiple CSVs/runs side-by-side.
Old: to_sql(..., if_exists="replace") would drop/replace the table on every run.

3) Indexes optimized for analysis 
New: (run_id, fish_part, frame) plus Runs(started_at DESC) for quick filtering by run/time.
Old: had (fish_part, frame) and (fish_id, frame); useful, but no run dimension.

4) Reproducibility hooks 
New: params_json allows saving the exact validation settings (e.g., expected columns) used for the run.
Old: No parameter capture.

5) Hashing & file identity 
New: SourceFiles row keyed by SHA256_hash + file_path, providing a stable identity for the data file.
Old: No file metadata.

6) Finish markers 
New: Explicit finish_run() sets finished_at.
Old: Not applicable.


What comes next: 

-Wrap the pipeline in a main() so that the file can be imported for testing without side effects. 
-Expand comments and documentation within code

