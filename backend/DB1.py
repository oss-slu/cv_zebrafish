import sqlite3 
import pandas as pd

#reads the first 3 rows as header as DLC outputs csv files like that)
df = pd.read_csv("Zebrafish_data.csv", header=[0,1,2])

# 2) treat first triplet as frame, then drop model level
cols = list(df.columns)
cols[0] = ('frame','','')
df.columns = pd.MultiIndex.from_tuples(cols)
frame = df[('frame','','')]
measure = df.drop(columns=[('frame','','')])
# drop the model name (level 0), keep (bodypart, coord)
measure.columns = pd.MultiIndex.from_tuples([(bp, coord) for (_, bp, coord) in measure.columns])


#I feel that there is an error somewhere in this section or how the cvs is read and organized. Will contunue to take a look and simplfiy this implementation. 
# 3) Wide to long (one row per bodypart per frame)
tidy = (measure
        .stack(level=0, future_stack = True)         # stack by bodypart (apperenrly will be removed by pandas soon.. will update this is just a start!)
        .rename_axis(index=['row_idx', 'fish_part'])
        .reset_index()  
)      # get row_idx and fish_part as columns
tidy['frame'] = frame.iloc[tidy['row_idx']].values
tidy = tidy[['fish_part','frame','x','y','likelihood']]
tidy.insert(0, 'fish_id', 1)                     # set or compute fish_id as needed





connection = sqlite3.connect("CV_Zebrafish.db")
cursor = connection.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS Fish_Data (
               fish_id integer, 
               fish_part text,
               frame integer,
               x real,
               y real,
               likelihood real) """)

tidy.to_sql("Fish_Data", connection, if_exists="append", index=False, chunksize=100_000, method="multi")
connection.execute("CREATE INDEX IF NOT EXISTS ix_fd_part_frame ON Fish_Data (fish_part, frame)")
connection.execute("CREATE INDEX IF NOT EXISTS ix_fd_fish_frame ON Fish_Data (fish_id, frame)")
connection.commit()
connection.close()





















    





