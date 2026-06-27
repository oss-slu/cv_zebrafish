# Literature Report: How Zebrafish Software Defines Macro-Level Behavior

**Prepared for:** CV Zebrafish project  
**Date:** June 2026  
**Focus:** How published tools answer questions like *“Is it swimming?”*, *“Is it turning?”*, *“Is it struggling?”* — and how those labels are tied to **time segments** (bouts, epochs, or frame ranges).

---

## Executive summary

Macro behavior is almost never read directly from raw video. Software typically:

1. **Tracks** the fish (centroid, tail, or multi-keypoint pose).
2. **Segments time** into episodes (bouts, mobility bouts, freezing bouts, stimulus-aligned windows).
3. **Assigns a label** to each segment using thresholds, rules, classifiers, or human annotation.

The dominant larval paradigm is **bout → label** (ZebraZoom: swim / turn / escape). Adult open-field work often uses **mobility threshold → freezing vs exploring**. High-throughput screens often collapse everything to **active vs inactive**, then cluster or classify only when finer ethology is needed.

**CV Zebrafish today** implements two macro-relevant layers: **(a)** fin/tail-peak **swim bouts** (existing pipeline) and **(b)** displacement-gated **active vs rest** (new low-res tab). It does **not** yet auto-label swimming vs turning vs struggling as named maneuver classes.

---

## 1. Ways to define macro behavior (concise taxonomy)

### A. Binary activity states (frame or bout level)
- **Question answered:** “Is anything happening?” / “Is it moving?”
- **Definition:** Displacement or velocity above a floor for ≥ N frames → **active**; otherwise **rest** (or **freezing** in adult assays).
- **Time segments:** Contiguous runs of 0/1 labels; short gaps often merged into one bout.
- **Examples:** EthoVision “mobile” time; ZebraTrack freezing bouts; CV Zebrafish **Active / Rest** tab.
- **Limitation:** Does not distinguish swim vs turn vs struggle—only movement vs not.

### B. Mobility bout, then kinematic maneuver class
- **Question answered:** “What kind of movement is this bout?”
- **Definition:** Detect bout boundaries from tail kinematics, then classify each bout using speed, tail-beat frequency (TBF), bend amplitude, duration.
- **Typical larval labels:**
  - **Swimming** — slow forward swim (low–moderate TBF, sustained forward displacement).
  - **Turning** — routine reorientation (moderate curvature, shorter bout).
  - **Escape / struggling-like** — high-amplitude C-start or escape (high peak TBF, large bend, brief burst); in many papers “struggle” in restraint maps to **erratic high-frequency tail beats** similar to escape kinematics.
- **Time segments:** One label per **bout** `[t_start, t_end]`.
- **Gold standard:** ZebraZoom (Mirat et al., 2013, *Front. Neural Circuits*) — supervised ML on bout features → slow swim, routine turn, escape.

### C. Threshold rules on continuous kinematics (no ML)
- **Question answered:** “When does variable X cross a criterion?”
- **Definition:** Hand-set cutoffs on tail angle, fin angle, head yaw rate, tail distance, speed.
- **Time segments:** Peaks, threshold crossings, or ranges between crossings.
- **Examples:** CV Zebrafish **swim bouts** (`graph_cutoffs`: fin-angle and tail-distance peaks merged into `timeRangeStart_*` / `timeRangeEnd_*`); legacy fin-peak bout finder.
- **Swim vs turn vs struggle (manual mapping):**
  - **Swimming** — sustained periods inside swim bout ranges with moderate fin/tail oscillation.
  - **Turning** — elevated **head yaw** or **tail angle** change within a bout.
  - **Struggling** — often operationalized as **high fin/tail frequency + large tail distance excursions** (user-defined cutoffs; not a built-in enum in CV Zebrafish).

### D. Supervised machine learning on bout or window features
- **Question answered:** “Which expert-defined class does this episode look like?”
- **Definition:** Train classifier on labeled bouts (speed, TBF, bend count, duration, etc.).
- **Time segments:** Bouts or sliding windows; label per segment.
- **Examples:** ZebraZoom maneuver classifier; Z-LaP Tracker behavioral profiles after DLC tracking.

### E. Unsupervised clustering → discovered “types”
- **Question answered:** “What behavioral modes exist in this dataset?”
- **Definition:** K-means / hierarchical clustering on feature vectors per animal or per bout; clusters interpreted post hoc as “active,” “hyperactive,” “sedentary,” etc.
- **Time segments:** Per-larva summary or per-bout cluster ID.
- **Examples:** Z-LaP Tracker (Puskás et al., 2023, *Sci. Rep.*).

### F. Stimulus-locked epochs (assay-defined behavior)
- **Question answered:** “What happened after the tap / flash / loom?”
- **Definition:** Behavior is defined **relative to stimulus onset** (e.g. 0–1 s post-acoustic = response window).
- **Typical labels:** Acoustic startle, OMR swim, phototaxis run, habituation across trials.
- **Time segments:** Fixed or detected windows aligned to stimulus markers.
- **Examples:** Z-LaP acoustic hyperexcitability; BonZeb closed-loop assays (Severi et al., 2021, *eLife*, PMC8047029).

### G. Assay-specific ethograms (adult / anxiety / social)
- **Question answered:** “Is it exploring, freezing, or thrashing?”
- **Definition:** Arena zones + mobility thresholds + angular velocity (meandering).
- **Typical labels:** **Freezing** (immobility bout), **exploration**, **thigmotaxis** (wall hugging); **struggling** in some protocols = repeated escape-like bursts against confinement.
- **Time segments:** Freezing bouts, zone occupancy epochs.
- **Examples:** ZebraTrack open-field protocol (PMC11869861); ZebraLab / EthoVision adult plugins.

### H. Human annotation (ground truth segments)
- **Question answered:** “What did the experimenter call this?”
- **Definition:** Manual scoring of video clips or bout lists; used to train classifiers or validate automation.
- **Time segments:** Experimenter-drawn start/end times.
- **Role:** ZebraZoom reported ~73–91% agreement between experts and automated maneuver labels.

---

## 2. Mapping common macro labels to operational definitions

| Macro label | How software usually defines it | Typical time unit |
|-------------|----------------------------------|-------------------|
| **Swimming** | Locomotor bout with forward displacement + rhythmic tail beats (TBF in swim band); ZebraZoom “slow forward swim” class | Bout |
| **Resting** | No bout detected; or displacement below mobility threshold | Inter-bout gap or frozen run |
| **Turning** | Reorientation bout: high angular velocity / tail bend without escape kinematics; ZebraZoom “routine turn” | Bout |
| **Struggling / escape** | High peak TBF, large bend amplitude, short burst; erratic multi-direction changes; C-start literature | Short bout (often &lt; 1 s) |
| **Freezing** | Centroid displacement &lt; threshold for ≥ minimum duration (adult OFT) | Immobility bout |
| **Active (generic)** | Any motion above displacement/speed floor | Frame runs or merged bouts |

---

## 3. Tool-by-tool: macro labels and time segments

### ZebraZoom (Mirat et al., 2013)
- **Segments:** Locomotor **bouts** from tail tracking.
- **Labels:** Slow forward **swim**, routine **turn**, **escape** (per bout).
- **Rest:** Implicit between bouts; global **% time swimming**.
- **URL:** https://www.frontiersin.org/journals/neural-circuits/articles/10.3389/fncir.2013.00107/full

### BonZeb (Severi et al., 2021)
- **Segments:** Frame-by-frame pose in **closed-loop** or batch windows.
- **Labels:** Assay-driven (OMR, looming, optomotor) — behavior = pose + stimulus rule, not a fixed swim/turn enum.
- **URL:** https://pmc.ncbi.nlm.nih.gov/articles/PMC8047029/

### Z-LaP Tracker (Puskás et al., 2023)
- **Segments:** DLC keypoint trajectories in well plates; trial windows.
- **Labels:** Activity level, acoustic response, habituation; **behavioral profiles** via clustering (macro types discovered, not always named swim/turn).
- **URL:** https://pmc.ncbi.nlm.nih.gov/articles/PMC9950053/

### Marigold (2025, BMC Bioinformatics)
- **Segments:** User-defined keypoint tracks over time.
- **Labels:** Downstream analysis; tool focuses on pose, not built-in maneuver taxonomy.
- **URL:** https://link.springer.com/article/10.1186/s12859-025-06042-2

### EthoVision XT / ZebraLab (commercial)
- **Segments:** **Mobility bouts** (velocity &gt; threshold for minimum duration).
- **Labels:** Mobile vs immobile; plugins add zone-based **freezing**, thigmotaxis, path shape.
- **Comparison:** Frontiers in Bioengineering (2024) — https://doi.org/10.3389/fbioe.2024.1461264

### ZebraTrack (adult open field, PMC11869861)
- **Segments:** **Freezing bouts**, path epochs, annulus occupancy.
- **Labels:** Freezing, meandering, angular velocity bands — anxiety-oriented macro endpoints.

### StrIPETrack (2026, *Biol. Open*)
- **Segments:** ROI occupancy over time.
- **Labels:** Activity level (macro); extensible to maze arms.

---

## 4. CV Zebrafish: what the app does vs macro maneuver labels

| Capability | Where in app | Macro behavior meaning |
|------------|--------------|------------------------|
| **Swim bouts** | Config `graph_cutoffs` + `timeRangeStart_*` columns; fin/tail/spine plots sliced by bout | Approximates “**episodes of coordinated locomotion**” — not classified into swim vs turn |
| **Active / rest** | Config **Low-Res Analysis** + graph **Active / Rest** tab | “**Is it moving**” (displacement-gated) — not swim vs struggle |
| **Distance & speed** | **Numerical Outputs** tab | How far / how fast for chosen bodypart — does not assign ethology labels |
| **Fin / tail angles, head yaw** | Standard graphs + cross-correlation | Raw kinematics you can **threshold manually** to approximate turning or burst escape |
| **Swim / turn / struggle classes** | *Not implemented* | Would need bout-level rules or ML on top of existing metrics (ZebraZoom-style next step) |

---

## 5. Practical recommendation for adding swim / turn / struggle

To align with literature and your macro goals:

1. **Keep bout segmentation** (already have fin/tail bout ranges + active/rest).
2. **Per bout, compute features:** mean speed, peak tail angle, fin peak count, bout duration, head yaw change.
3. **Label with rules or classifier:**
   - **Swim** — duration &gt; T, moderate speed, rhythmic fin peaks.
   - **Turn** — large **head yaw** or tail angle change, moderate duration.
   - **Struggle / escape** — short bout, high peak speed or tail distance, high fin peak rate.
4. **Expose** labeled intervals `[start_frame, end_frame, class]` on a new graph tab with tunable thresholds (same pattern as Active / Rest).

---

## 6. Primary references

- Mirat, O., et al. (2013). ZebraZoom. *Front. Neural Circuits* 7:107. https://doi.org/10.3389/fncir.2013.00107  
- Severi, K. E., et al. (2021). BonZeb. *eLife* (PMC8047029).  
- Puskás et al. (2023). Z-LaP Tracker. *Sci. Rep.* (PMC9950053).  
- Marigold (2025). *BMC Bioinformatics* (PMC11773884).  
- ZebraTrack protocol (2025). PMC11869861.  
- StrIPETrack (2026). PMID 41943926.  
- ZebraZoom kinematic definitions: https://github.com/oliviermirat/ZebraZoomDocumentation  
