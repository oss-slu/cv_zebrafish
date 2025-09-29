import sqlite3 
import pandas as pd
import warnings
import json
import os
import hashlib

# Open (or create) the SQLite database file in the current directory.
connection = sqlite3.connect("CV_Zebrafish.db")

# ------------------------------------------------------------------------------
# Helper: compute a stable content hash of an input file
# ------------------------------------------------------------------------------

# Hash function helper to create a unique ID for each source file. This allows us
# to recognize a file we've ingested before even if its path changes.
# Uses SHA-256 (cryptographically stronger than SHA-1).
def file_hash(filepath, chunk=1024*1024):
    """
    Return the SHA-256 hex digest of the file at `filepath`.
    Reads in chunks to avoid large memory usage.
    Raises FileNotFoundError if the file does not exist.
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"No such file: '{filepath}'")

    hasher = hashlib.sha256()
    # Stream the file to keep memory low for large CSVs
    with open(filepath, 'rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            hasher.update(b)
    return hasher.hexdigest()


# ------------------------------------------------------------------------------
# Schema management: ensure foundational tables exist
# ------------------------------------------------------------------------------

def ensure_source_schema(conn):
    """
    Create the metadata tables if they don't exist:
      - SourceFiles: one row per unique input file (path, hash, size, mtime)
      - Runs:        one row per ingestion run (timestamps, params, FK to source)
    NOTE: This function does NOT create the Fish_Data table; that's created later
    just before writing data to it.
    """
    cur = conn.cursor()

    # Tracks unique source files by file path + SHA-256 hash
    cur.execute("""
    CREATE TABLE IF NOT EXISTS SourceFiles (
        source_file_id INTEGER PRIMARY KEY,
        file_path TEXT UNIQUE,
        SHA256_hash TEXT,
        size_bytes INTEGER,
        mtime REAL,
        added_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # Tracks ingestion runs for provenance and reproducibility
    cur.execute("""
    CREATE TABLE IF NOT EXISTS Runs (
        run_id      INTEGER PRIMARY KEY,
        started_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        finished_at TEXT,
        user        TEXT,
        params_json TEXT,
        source_file_id INTEGER,
        FOREIGN KEY (source_file_id) REFERENCES SourceFiles(source_file_id)
    )""")
    
    conn.commit()
    cur.close()


# ------------------------------------------------------------------------------
# Run lifecycle helpers
# ------------------------------------------------------------------------------

def start_run(conn, csv_path, params_dict):
    """
    Register (if needed) the source file in SourceFiles and RETURN a run_id.

    """
    cur = conn.cursor()

    # Compute file identity
    sha = file_hash(csv_path)
    s = os.stat(csv_path)

    # Ensure a SourceFiles row exists for this file/hash
    cur.execute(
        """INSERT OR IGNORE INTO SourceFiles (file_path, SHA256_hash, size_bytes, mtime, added_at)
           VALUES (?, ?, ?, ?, datetime('now'))""",
        (csv_path, sha, s.st_size, int(s.st_mtime))
    )
    
    # Look up the source_file_id to (ideally) link into Runs
    cur.execute("SELECT source_file_id FROM SourceFiles WHERE SHA256_hash = ?", (sha,))
    source_file_id = cur.fetchone()[0]  

    cur.execute(
    "INSERT INTO Runs (params_json, source_file_id) VALUES (?, ?)",
    (json.dumps(params_dict), source_file_id)
    )

    run_id = cur.lastrowid  

    conn.commit()
    return run_id


def finish_run(conn, run_id):
    """
    Mark a run as finished by setting finished_at to now.
    NOTE: If start_run never inserted a row into Runs, this will do nothing.
    """
    conn.execute("UPDATE Runs SET finished_at=datetime('now') WHERE run_id=?", (run_id,))
    conn.commit()


# Ensure metadata tables exist before proceeding.
ensure_source_schema(connection) 


# ------------------------------------------------------------------------------
# Load & normalize the DLC CSV (3-row header: scorer/bodypart/coord)
# ------------------------------------------------------------------------------

# Read DLC CSV with a 3-level header. This produces a MultiIndex on columns like:
#   (scorer, bodypart, coord)
# Where coord is typically in {x, y, likelihood}.
df = pd.read_csv("Zebrafish_data.csv", header=[0, 1, 2])  # adjust filename/path as needed

# Promote the first logical column to a special ('frame', '', '') key, then separate it out.
cols = list(df.columns)
cols[0] = ('frame', '', '')
df.columns = pd.MultiIndex.from_tuples(cols)

# Extract the frame column; the rest are bodypart/coordinate columns.
frame = df[('frame', '', '')]
measure = df.drop(columns=[('frame', '', '')])

# Collapse the "model/scorer" (level 0) so we keep columns as (bodypart, coord).
# This makes downstream manipulation simpler: we only reason about bodypart & coord.
measure.columns = pd.MultiIndex.from_tuples([(bp, coord) for (_, bp, coord) in measure.columns])

# Define the expected coordinate labels per bodypart
EXPECTED = {'x', 'y', 'likelihood'}

# Validate coordinate labels per bodypart; warn if unexpected labels appear.
bp_to_cords = {}
for bp, cords in measure.columns:
    bp_to_cords.setdefault(bp, set()).add(cords)

# Find any bodyparts that have labels outside the expected set.
bad = {bp: cords - EXPECTED for bp, cords in bp_to_cords.items() if not cords <= EXPECTED}
if bad:
    lines = ["Unexpected coordinate labels found (expected: x, y, likelihood):"]
    for bp, cords in sorted(bad.items()):
        lines.append(f"  {bp}: {', '.join(sorted(cords))}")
    warnings.warn("\n".join(lines))

# Drop any unexpected coordinate columns (keep only x, y, likelihood).
unexpected = sorted({c[1] for c in measure.columns} - EXPECTED)
if unexpected:
    warnings.warn(f"Dropping unexpected coordinate columns: {unexpected}")
    measure = measure.loc[:, [c for c in measure.columns if c[1] in EXPECTED]]

# ------------------------------------------------------------------------------
# Wide -> Long: each row becomes (fish_part, frame, x, y, likelihood)
# ------------------------------------------------------------------------------

# Stack bodypart out of the columns into the index.
# NOTE: pandas has warned about future changes to stack; the 'future_stack' argument
# may be removed in future versions. This works today but consider updating later.
tidy = (
    measure
    .stack(level=0, future_stack=True)   # stacks by bodypart (from columns to rows)
    .rename_axis(index=['row_idx', 'fish_part'])
    .reset_index()
)

# Attach the 'frame' value based on the original row index preserved in row_idx.
tidy['frame'] = frame.iloc[tidy['row_idx']].values

# Ensure the coordinate columns exist even if some were missing in the source.
for col in ['x', 'y', 'likelihood']:
    if col not in tidy.columns:
        tidy[col] = pd.NA

# Restrict to the standardized column order expected by downstream consumers.
tidy = tidy[['fish_part', 'frame', 'x', 'y', 'likelihood']]

# For now, assign a constant fish_id (extend later if you have multiple fish).
tidy.insert(0, 'fish_id', 1)

# ------------------------------------------------------------------------------
# Cleaning: coerce numeric, drop invalid/missing, and clamp likelihood range
# ------------------------------------------------------------------------------

# Convert to numeric; non-numeric become NaN (will be dropped below).
tidy['x'] = pd.to_numeric(tidy['x'], errors='coerce')
tidy['y'] = pd.to_numeric(tidy['y'], errors='coerce')
tidy['likelihood'] = pd.to_numeric(tidy['likelihood'], errors='coerce')

# Drop rows with missing/non-numeric x, y, or likelihood.
before = len(tidy)
tidy = tidy.dropna(subset=['x', 'y', 'likelihood'])
dropped_null = before - len(tidy)
if dropped_null > 0:
    warnings.warn(f"Dropped {dropped_null} rows with null/non-numeric x, y, likelihood.")

# Keep only rows where likelihood is in [0, 1].
mask = (tidy['likelihood'] >= 0) & (tidy['likelihood'] <= 1)
dropped_range = len(tidy) - mask.sum()
if dropped_range > 0:
    warnings.warn(f"Dropped {dropped_range} rows with likelihood outside [0,1].")
tidy = tidy.loc[mask]

# ------------------------------------------------------------------------------
# Run metadata: record parameters and (attempt to) start a run
# ------------------------------------------------------------------------------

# Add any run settings you want to remember for reproducibility.
# Stored as JSON (string) in the Runs table (see NOTE in start_run).
params = {"EXPECTED": list(EXPECTED)}
run_id = start_run(connection, "Zebrafish_data.csv", params)  # NOTE: see start_run comment
tidy.insert(0, 'run_id', run_id)

# ------------------------------------------------------------------------------
# Persist: create Fish_Data if needed, append the cleaned rows, and index
# ------------------------------------------------------------------------------

cursor = connection.cursor()

# Create the analysis table if it doesn't exist.
cursor.execute("""
CREATE TABLE IF NOT EXISTS Fish_Data (
    run_id integer,
    fish_id integer, 
    fish_part text,
    frame integer,
    x real,
    y real,
    likelihood real
)""")

# Append (do not replace) so multiple runs can coexist.
tidy.to_sql("Fish_Data", connection, if_exists="append", index=False, chunksize=100_000)

# Helpful index for common queries: filter by run, bodypart, frame.
connection.execute("CREATE INDEX IF NOT EXISTS ix_fd_run_part_frame ON Fish_Data (run_id, fish_part, frame)")

# Index to quickly list runs by start time.
connection.execute("CREATE INDEX IF NOT EXISTS ix_runs_started ON Runs (started_at DESC)")

connection.commit()

# Attempt to mark the run finished.
# NOTE: If `start_run` didn't insert a Runs row, this UPDATE will have no effect.
finish_run(connection, run_id)

# Always close your connection when you're done.
connection.close()
