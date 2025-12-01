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
- [x] Documented
  - Evidence: Architecture/how-to docs exist (`docs/architecture`, `docs/howtos`), in-app flow is
    hinted at in scene code, and `README.md` is now refreshed with accurate layout, Conda setup, and
    run/test instructions.
- [~] Maintainable
  - Evidence: Modular separation across `src/core`, `src/ui`, and `src/data`; unit tests cover key
    modules.
  - Gaps: No packaging/config files (`pyproject.toml`, `setup.cfg`), no dependency pins, no tooling
    config (lint/format/type), and no automated build/test workflow.
- [~] Follows open source standards
  - Evidence: `LICENSE` (MIT), `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue/PR templates, and PR
    template added.
  - Gaps: No CI, no package metadata, and no contribution automation.
- [~] Deployable
  - Evidence: `environment.yml` and README run instructions.
  - Gaps: No installer or packaging/release process beyond `python app.py`.
                                                                                                   
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
- [x] Clear README and setup instructions - README reflects current layout, Conda setup, and run/test
  steps.
- [~] Architecture and technical documentation - present but stale in places (e.g., references to
  `Utils/*` paths rather than current `src/core/*` modules); how-tos exist for UI/validation.
- [x] Open source community documentation - contributor guidelines, code of conduct, and templates
  added.
                                                                                                   
### Client/User Value
- [~] Software solves validated user problems - discovery captured in `docs/product/PRODUCT_SUMMARY.md`
  and meeting notes; need client validation on current build.
- [~] Delivers meaningful value - pipeline and graph viewer exist, but exports/reporting not yet
  delivered or demonstrated.
- [~] Addresses requirements from discovery work - config generator and validators align with
  discovery; traceability checklist still needed.
                                                                                                   
### Open Source Standards
- [x] Proper licensing - `LICENSE` (MIT) added.
- [x] Community-ready documentation - `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue templates, and
  PR template added.
- [~] Contribution-ready repository structure - `environment.yml` (planned/assumed); still missing CI
  and package metadata for contributors.
                                                                                                   
Notes
- Prioritize: (1) add CI to run tests and linters; (2) add packaging metadata (`pyproject.toml` or
  similar) and a dependency lock if needed; (3) refresh architecture/how-to docs and add an end-user
  UI guide/screenshots; (4) consider installer/packaging for deployment.
