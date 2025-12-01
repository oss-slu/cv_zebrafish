# Project Requirements Checklist — CV Zebrafish                                                  
                                                                                                   
## Core Requirements
- [~] Functional without critical bugs
  - Evidence: PyQt entrypoint (`app.py`) drives multiple scenes under `src/ui/scenes`; calculation
    + graph pipelines exist in `src/core/*` with unit tests (`tests/unit/core`, `src/core/graphs/tests`,
    `tests/unit/ui/test_graph_viewer_scene.py`).
  - Gaps: No dependency file to install runtime needs (PyQt5/Plotly/pandas/etc.), no CI, and no
    recent test or end-to-end run recorded in-repo.
- [~] Solves real client problems
  - Evidence: Problem statements and target users captured in `docs/product/PRODUCT_SUMMARY.md`
    and meeting notes under `docs/product/meeting_minutes`.
  - Gaps: No recorded client sign-off or usability feedback on the current build.
- [~] Meets quality standards
  - Evidence: Targeted unit coverage for calculations/graphs/UI as above.
  - Gaps: No CI, lint/type checks, dependency lockfile, or packaging metadata to enforce standards.
- [ ] Documented
  - Evidence: Architecture/how-to docs exist (`docs/architecture`, `docs/howtos`), and in-app flow
    is hinted at in scene code.
  - Gaps: `README.md` is outdated (lists files that do not exist: `configs/`, `requirements.txt`,
    `environment.yml`, `LICENSE`, `AGENTS.md`, `contributing.md`, `package*.json`); architecture
    notes (e.g., `docs/architecture/calculations/README.md`) reference old module paths; no install
    instructions tied to the current `src/` layout or dependency list; no end-user UI walkthrough
    or screenshots.
- [~] Maintainable
  - Evidence: Modular separation across `src/core`, `src/ui`, and `src/data`; unit tests cover key
    modules.
  - Gaps: No packaging/config files (`pyproject.toml`, `setup.cfg`), no dependency pins, no tooling
    config (lint/format/type), and no automated build/test workflow.
- [ ] Follows open source standards
  - Missing: `LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue/PR templates.
- [ ] Deployable
  - Missing: Deployment guide or installer, reproducible environment spec, and packaging/release
    process beyond `python app.py`.
                                                                                                   
  ## Evaluation Criteria                                                                           
### Functionality
- [~] Software works without critical bugs - code and tests exist but are unverified because there
  is no dependency spec or CI run recorded.
- [~] Core features deliver intended value - calculations/validators/graph viewer implemented; no
  confirmed exports/reporting/batch processing in the current tree.
- [~] User experience is functional/usable - PyQt scenes wired with navigation; no recorded
  usability testing or packaged demo build.
                                                                                                   
### Code Quality
- [~] Clean, readable, maintainable code - modular layout and docstrings; needs enforced style,
  packaging, and dependency hygiene.
- [~] Appropriate testing - unit coverage for parser/calculations/graphs/UI; no integration/e2e
  coverage or test reports, and tests are not runnable without a dependency list.
- [ ] Sustainable engineering practices - lacking CI, dependency locking, and release/versioning
  strategy.
                                                                                                   
### Documentation
- [ ] Clear README and setup instructions - README is outdated/misleading about repository contents
  (lists non-existent files/dirs) and provides no actionable dependency install steps.
- [~] Architecture and technical documentation - present but stale in places (e.g., references to
  `Utils/*` paths rather than current `src/core/*` modules); how-tos exist for UI/validation.
- [ ] Open source community documentation - contributor guidelines, code of conduct, and community
  docs are absent.
                                                                                                   
### Client/User Value
- [~] Software solves validated user problems - discovery captured in `docs/product/PRODUCT_SUMMARY.md`
  and meeting notes; need client validation on current build.
- [~] Delivers meaningful value - pipeline and graph viewer exist, but exports/reporting not yet
  delivered or demonstrated.
- [~] Addresses requirements from discovery work - config generator and validators align with
  discovery; traceability checklist still needed.
                                                                                                   
### Open Source Standards
- [ ] Proper licensing - no `LICENSE` file found.
- [ ] Community-ready documentation - missing `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and issue
  templates.
- [ ] Contribution-ready repository structure - no dependency file, CI, or package metadata to
  support contributors.
                                                                                                   
Notes
- Prioritize: (1) create a dependency file (`requirements.txt`/`environment.yml`) and fix README to
  match the actual `src/` layout; (2) add LICENSE + contributor docs; (3) add CI to run the existing
  tests; (4) refresh architecture/how-to docs to align with current modules and add an end-user UI
  guide/screenshots.
