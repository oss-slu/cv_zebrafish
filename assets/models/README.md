# Bundled pretrained models

Drop fully trained DeepLabCut runs here so Pose Studio can seed an empty project
without manual import.

## Layout

Each **subfolder** is one importable run, for example:

```
assets/models/
  session2_3-lab-seed/     # current local seed (from Session2_3)
    weights.pt             # required (~92 MB; gitignored)
    manifest.json          # metadata for the Model tree label
    pytorch_config.yaml    # optional DLC companion
```

Alternatively, point the folder at a DLC train directory that contains
`snapshot-*.pt` under `dlc-models-pytorch/**/train/`.

## Current seed

`session2_3-lab-seed/` was copied from the newest archived run in **Session2_3**
(`20260701-023712`, Train 100 frames, best epoch 30). Replace this folder when
the lab has a dedicated release model.

If `weights.pt` is missing (fresh clone without local assets), first-run seeding
is skipped until you drop a valid run here or use **Upload model** on the Model tab.

## When copies happen

On session open, `install_bundled_model_if_empty()` copies the first valid
subfolder into `pose_projects/<id>/models/runs/<run_id>/` **only when** the
project has:

- no saved runs under `models/runs/`, and
- no snapshots yet in `models/dlc_work/`.

`.pt` weight files are **gitignored** (too large). Keep `manifest.json` and this
README in the repo so the drop-in layout stays documented.
