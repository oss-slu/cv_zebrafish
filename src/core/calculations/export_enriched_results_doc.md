# `export_enriched_results.py` Overview

`calculations/export_enriched_results.py` is the enriched exporter for the cv_zebrafish pipeline. It keeps the original DeepLabCut (DLC) pose data, all derived metrics, and the bout metadata in one CSV (plus optional JSON) so the new graphing stack can reproduce every legacy Plotly figure without reopening the raw DLC file.

## How it works
1. **Parse the DLC CSV** – `calculations.utils.Parser.parse_dlc_csv` loads every tracked point (spine, fins, tail, head) as pixel-space arrays with confidences.
2. **Run calculations** – `calculations.utils.Driver.run_calculations` produces the standard metrics (`LF_Angle`, `Tail_Distance`, `TailAngle_*`, `HeadYaw`, `timeRangeStart_*`, etc.).
3. **Enrich + merge** – The script:
   - embeds the calculated metrics exactly as in `run_calculation_to_csv.py`;
   - serializes each frame’s spine into `spine_points_json`;
   - appends convenience columns (`HeadPX`, `TailPX`, `videoFile`, `pixel_scale_factor`);
   - flattens the raw DLC points into `Spine_*`, `LeftFin_*`, `RightFin_*`, `Tail_*`, and `DLC_HeadPX/DLC_TailPX` columns so every x/y/conf value survives.
4. **Optional metadata JSON** – When `--extra-json` is provided, the script also writes a manifest that records the config path, video file, scale factors, and canonical time ranges.

## CSV column blocks

| Block | Purpose | Examples |
| --- | --- | --- |
| Calculated metrics | Direct output from `run_calculations`; feeds timelines/head plots. | `Time`, `LF_Angle`, `RF_Angle`, `Tail_Distance`, `TailAngle_0..11`, `HeadYaw`, `HeadX`, `HeadY`, `Tail_Side`, `Furthest_Tail_Point`, `curBoutHeadYaw` |
| Bout metadata | Swim-bout definitions + peak annotations. | `leftFinPeaks`, `rightFinPeaks`, `timeRangeStart_*`, `timeRangeEnd_*` (row 0 stores pairs) |
| Calculated pixel helpers | Convenience fields for overlays + serialized spine. | `HeadPX`, `HeadPY`, `TailPX`, `TailPY`, `spine_points_json`, `videoFile`, `pixel_scale_factor` |
| Raw DLC spine | Exact per-point coordinates/confidences from the DLC CSV. | `Spine_Head_x`, `Spine_BF_conf`, …, `Spine_ET_y` |
| Raw DLC fins | Original fin landmarks. | `LeftFin_LF1_x`, `RightFin_RF2_conf`, etc. |
| Raw DLC tail | Tail landmarks needed for heatmaps/crops. | `Tail_T1_x`, …, `Tail_ET_conf` |
| Raw DLC convenience coords | Head/tail tip readings retained under a distinct prefix to avoid name clashes. | `DLC_HeadPX`, `DLC_HeadPY`, `DLC_TailPX`, `DLC_TailPY`, plus `_PConf` variants |

## Usage

```bash
python calculations/export_enriched_results.py \
  --csv data_schema_validation/sample_inputs/csv/correct_format.csv \
  --config data_schema_validation/sample_inputs/jsons/BaseConfig.json \
  --output calculations/tests/calculated_data_enriched.csv \
  --extra-json calculations/tests/calculated_data_enriched.meta.json
```

The resulting CSV (and optional `.meta.json`) are drop-in replacements for the legacy Bruce artifacts, enabling `plotSpines`, movement overlays, heatmaps, and head plots to run directly on the enriched output.
