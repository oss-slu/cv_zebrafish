import sqlite3 
import pandas as pd
import warnings

# reads the first 3 rows as header as DLC outputs csv files like that)
df = pd.read_csv("Zebrafish_data.csv", header=[0,1,2])

# treat first triplet as frame, then drop model level
cols = list(df.columns)
cols[0] = ('frame','','')
df.columns = pd.MultiIndex.from_tuples(cols)

frame = df[('frame','','')]
measure = df.drop(columns=[('frame','','')])

# drop the model name (level 0), keep (bodypart, coord)
measure.columns = pd.MultiIndex.from_tuples([(bp, coord) for (_, bp, coord) in measure.columns])

# validate coord labels and filter unexpected ones
EXPECTED = {'x', 'y', 'likelihood'}

# warn per bodypart if unexpected coord labels found
bp_to_cords = {}
for bp, cords in measure.columns:
        bp_to_cords.setdefault(bp, set()).add(cords)

bad = {bp: cords - EXPECTED for bp, cords in bp_to_cords.items() if not cords <= EXPECTED}
if bad:
        lines = ["Unexpected coordinate labels found (expected: x, y, likelihood):"]
        for bp, cords in sorted(bad.items()):
                lines.append(f"  {bp}: {', '.join(sorted(cords))}")
        warnings.warn("\n".join(lines))

# drop unexpected coord columns
unexpected = sorted({c[1] for c in measure.columns} - EXPECTED)
if unexpected:
    warnings.warn(f"⚠️ Dropping unexpected coordinate columns: {unexpected}")
    measure = measure.loc[:, [c for c in measure.columns if c[1] in EXPECTED]]

# 3) Wide to long (one row per bodypart per frame)
tidy = (measure
        .stack(level=0, future_stack = True)         # stack by bodypart (apperenrly will be removed by pandas soon.. will update this is just a start!)
        .rename_axis(index=['row_idx', 'fish_part'])
        .reset_index()  
)      

# get row_idx and fish_part as columns
tidy['frame'] = frame.iloc[tidy['row_idx']].values

# ensure columns exist even if some cords are missing
for col in ['x','y','likelihood']:
    if col not in tidy.columns:
        tidy[col] = pd.NA

tidy = tidy[['fish_part','frame','x','y','likelihood']]
tidy.insert(0, 'fish_id', 1)                     # set or compute fish_id as needed

# ensures all numeric and drop rows with nulls (non-numeric)
tidy['x'] = pd.to_numeric(tidy['x'], errors='coerce')
tidy['y'] = pd.to_numeric(tidy['y'], errors='coerce')
tidy['likelihood'] = pd.to_numeric(tidy['likelihood'], errors='coerce')

# drops rows with missing or non numeric data 
before = len(tidy)
tidy = tidy.dropna(subset=['x','y','likelihood'])
dropped_null = before - len(tidy)
if dropped_null > 0:
    warnings.warn(f"Dropped {dropped_null} rows with null/non-numeric x, y, likelihood.")

# keep only rows with 0 ≤ likelihood ≤ 1
mask = (tidy['likelihood'] >= 0) & (tidy['likelihood'] <= 1)
dropped_range = len(tidy) - mask.sum()
if dropped_range > 0:
    warnings.warn(f"Dropped {dropped_range} rows with likelihood outside [0,1].")
tidy = tidy.loc[mask]

#db 
connection = sqlite3.connect("CV_Zebrafish.db")
cursor = connection.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS Fish_Data (
               fish_id integer, 
               fish_part text,
               frame integer,
               x real,
               y real,
               likelihood real) """)

tidy.to_sql("Fish_Data", connection, if_exists="replace", index=False, chunksize=100_000)
connection.execute("CREATE INDEX IF NOT EXISTS ix_fd_part_frame ON Fish_Data (fish_part, frame)")
connection.execute("CREATE INDEX IF NOT EXISTS ix_fd_fish_frame ON Fish_Data (fish_id, frame)")
connection.commit()
connection.close()
