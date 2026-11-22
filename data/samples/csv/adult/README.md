# Adult zebrafish test fixture

Trimmed DeepLabCut CSVs used by the adult zebrafish tests (#157). The full lab files are ~26 MB each and are **not** committed; they live in the lab Drive folder (`body_points/` and `caudal_fin/`).

Each video has two files from two DLC models:

| File | Model | Body parts |
|------|-------|------------|
| `*_1100000.csv` | body_points | `p0`–`p9` (midline) |
| `*_600000.csv` | caudal_fin | `caudal_fin` |

## Source

| Trimmed file | Original file | Original frames | Frames kept |
|--------------|---------------|-----------------|-------------|
| _to be added_ | M26R body_points | | |
| _to be added_ | M26R caudal_fin | | |

Frames are renumbered from 0 in the trimmed files. Use the same range for both files of a pair.

## Regenerating

```bash
python tools/trim_dlc_csv.py <M26R>_1100000.csv <M26R>_600000.csv \
    --start <first frame> --frames 2000 --out data/samples/csv/adult/
```

The tool refuses pairs with different frame counts and warns if an output is over ~1 MB.
