# Graph Data Loader Plan

## Objectives
- Provide a single, well documented entry point that supplies every graph module with validated metrics, bout ranges, and runtime configuration details.
- Decouple CSV parsing logic from visualization code so future changes to calculated outputs only touch the data layer.
- Surface consistent data contracts (dataclasses or dictionaries) that keep plotting code free of ad hoc column lookups.

## Scope & Inputs
- Primary source: calculations/tests/calculated_data.csv containing per frame metrics plus aggregated row zero metadata.
- Supporting source: selected runtime config file (default config/BaseConfig.json) for video path, pixel scale, and plotting thresholds.
- Optional artefacts: cached video frame reader, file paths to exported HTML or PNG assets for provenance tracking.

## Architecture Overview
1. Module path: graphing/data_loader.py exporting a GraphDataLoader class and supporting dataclasses (BoutRange, TimeSeriesFrame, SpineFrame, PixelTrack).
2. Loader lifecycle:
   - initialized with paths to the CSV and config, plus optional overrides (e.g., custom column map).
   - load() performs IO once, caches parsed structures, and exposes accessor helpers.
3. Error handling: explicit exceptions for missing columns, malformed bout ranges, or inconsistent array lengths; include guidance in the message for remediation.

## Implementation Phases
1. **Foundation**
   - Create module skeleton with docstrings, GraphDataLoader stub, and dataclass definitions.
   - Add typing aliases for column names and structured return types.
2. **CSV Parsing Helpers**
   - Implement a private reader that ingests the CSV via pandas or csv module, coerces numeric columns, and preserves frame order.
   - Build utilities that extract row zero aggregates: timeRangeStart_*, timeRangeEnd_*, serialized peak lists, spine or trajectory JSON blobs.
   - Validate required columns (Time, LF_Angle, RF_Angle, HeadYaw, Tail_Distance, TailAngle_*). Provide fallbacks or informative errors when absent.
3. **Config Ingestion**
   - Load the designated config JSON, pluck video path, pixel_scale_factor, graph cutoffs, and store them on the loader for downstream consumers.
   - Allow overrides via constructor kwargs so tests can inject synthetic config data.
4. **Domain Assembly**
   - Convert parsed bout indices into BoutRange objects with precalculated durations and frame counts.
   - Wrap per frame metrics in TimeSeriesFrame dataclasses; ensure boolean or categorical fields (Tail_Side, Furthest_Tail_Point) remain accessible.
   - Deserialize spine arrays into SpineFrame structures (list of points with x, y, confidence) and pixel trajectories into PixelTrack objects.
5. **Accessor API**
   - iter_frames(bout=None): yield TimeSeriesFrame items, optionally filtered by BoutRange.
   - get_bouts(): return ordered list of BoutRange instances.
   - get_fin_peaks(side, bout=None): supply peak indices aligned to bouts.
   - get_spines(bout=None) and get_pixel_tracks(bout=None): return lists keyed by frame for plotting.
   - get_config() exposes immutable view of config values needed by graphs.
6. **Testing & Tooling**
   - Add unit tests under graphing/tests/test_data_loader.py with fixture CSVs covering happy path and error cases (missing columns, empty bouts).
   - Include doctests or example usage in module docstring to guide graph developers.

## Documentation & Handoff
- Update graphing/README.md (or create if missing) to describe how to initialize and use GraphDataLoader.
- Embed inline comments only where parsing logic is non obvious (e.g., explanation of row zero aggregates).
- Outline expected CSV schema in the doc so analytics engineers know which exports are mandatory for plotting.

## Risks & Mitigations
- Missing spine or pixel data: loader should degrade gracefully by raising a specific exception that plotting code can catch to skip unsupported graphs.
- Large CSV files: use lazy iterators or chunked pandas reads if file sizes spike; cache only the columns required by each accessor.
- Schema drift: centralize column names in a constants block so updates occur in one place and add tests that lock the schema.

## Acceptance Criteria
- Graph modules can obtain per bout time series, spine snapshots, peak lists, and config metadata exclusively through GraphDataLoader.
- Loader raises informative errors when prerequisite data is absent and never silently returns partial results.
- Tests cover parsing, bout reconstruction, config loading, and representative failure scenarios.
