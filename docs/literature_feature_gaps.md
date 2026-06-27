# Literature Feature Gaps vs `cv_zebrafish`

Scope: feature-level comparison against the current `cv_zebrafish` repository (README, docs, and code in `src/`).

## 1) Marigold (PMC11773884) - Missing Features

### 1.1 End-to-end pose tracking pipeline
- In-app frame labeling workflow for creating training datasets.
- In-app model training for custom keypoints.
- In-app inference directly from raw behavioral videos.

### 1.2 Deployment and accessibility model
- Browser-native web app (no install workflow).
- Fully cross-platform browser delivery (ChromeOS-first style deployment).

### 1.3 ML system capabilities
- Integrated neural-network architecture for on-device tracking.
- CPU-oriented, low-resource inference/training optimization pipeline.
- Explicit support for user-defined keypoint sets (up to fixed keypoint count in app workflow).

### 1.4 Experimental format support
- Native single-well and multiwell video tracking from imaging data.
- Robust tracking when foreign objects enter frame during recording (e.g., probe-based assays).

## 2) BonZeb (PMC8047029) - Missing Features

### 2.1 Real-time experimental control
- True online tracking from live camera streams (high-frequency acquisition loops).
- Closed-loop behavioral feedback (stimulus updates driven by current behavior).
- Virtual open-loop stimulus paradigms tied to fish pose/heading.

### 2.2 Stimulus and hardware orchestration
- Built-in visual stimulus library (looming, OMR, prey, phototaxis, flashes, etc.).
- Direct hardware control/integration (projectors, DAQ, Arduino, camera SDK stacks).
- Synchronized multi-device timing infrastructure for real-time experiments.

### 2.3 Advanced tracking modes
- Multi-animal online tracking with identity handling in-group.
- Eye contour/eye angle tracking integrated with tail/heading analysis.
- Head-fixed assay workflows with tail-driven feedback transforms.

### 2.4 Neuro-behavior integration workflows
- Optogenetic stimulation protocols coupled to behavior in the same run.
- Calcium imaging + behavior synchronization workflows.

## 3) ZebraTrack Protocol (PMC11869861) - Missing Features

### 3.1 Adult open-field anxiety workflow
- Adult zebrafish open-field tank acquisition protocol as a first-class workflow.
- Built-in anxiety endpoint package (freezing bouts/duration, meandering, angular velocity, ATA/RTA bundle).

### 3.2 Video-to-endpoint automation
- Native raw video ingestion + preprocessing chain for centroid extraction.
- Scripted background/threshold particle-tracking pipeline embedded in the product.
- One-click endpoint extraction templates equivalent to spreadsheet-driven protocol outputs.

### 3.3 Multi-tank acquisition support
- Explicit simultaneous multi-tank tracking workflow from one camera frame (adult OFT-oriented setup).

## 4) pi-tailtrack (JEB `jeb246335`) - Missing Features

### 4.1 Compact hardware-linked tracker
- Raspberry Pi + Pi NoIR camera self-contained tracking stack.
- Integrated IR illumination + camera + compute package as a reproducible low-cost build.

### 4.2 Real-time head-restrained tracking
- Real-time tail segmentation and skeletonization at >100 Hz for head-restrained larvae.
- Long-duration microscopy-compatible behavioral acquisition designed around constrained prep.

### 4.3 Microscopy-session practicality
- Compact attach/remove design optimized for shared functional microscopy rigs.

## 5) Cross-Source Gap Themes (Consolidated)

### 5.1 Missing "upstream" data capture
- Current app starts from DLC/tabular outputs, not from live/raw imaging workflows.

### 5.2 Missing real-time feedback experimentation
- No closed-loop/open-loop stimulus engine or synchronized hardware control plane.

### 5.3 Missing built-in ML training/inference lifecycle
- No native labeling-training-inference loop for pose models inside the app.

### 5.4 Missing hardware-reference implementations
- No documented low-cost reference build (Pi-based or equivalent) for acquisition+tracking.
