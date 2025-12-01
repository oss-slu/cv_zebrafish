# CV Zebrafish Boardroom Presentation — Slide-by-Slide Outline

Use this as a prompt/structure for the AI agent to build a polished, 10–30 minute deck that satisfies the presentation requirements. Each slide lists purpose, key content, and evidence/assets to include.

## Style Guide (AI-Friendly)
- **Tone:** Confident, concise, plain-English for mixed technical/non-technical audience.
- **Visuals:** Product screenshots only; clean white/light background; consistent accent color (deep blue/teal) matching zebrafish theme; minimal text per slide.
- **Typography:** Sans-serif, large headings, short bullets (≤ 6 words where possible).
- **Narrative Flow:** Problem → Value → Demo → Proof → Roadmap → Ask.
- **Fallbacks:** If live demo is risky, rely on pre-captured screenshots for each key scene.

## 1. Title & Team (+ Brief Project Description)
- **Purpose:** Establish credibility and audience context.
- **Content:** Project name, brief description (“Python/PyQt app that validates DLC zebrafish CSVs, auto-builds configs, runs kinematic metrics, and renders Plotly graphs in minutes”), team members/roles, client/advisor, date.
- **Evidence/Assets:** Concise subtitle (“Automating DeepLabCut zebrafish analysis in minutes”).
- **Images:** Single product screenshot (Landing scene) as subtle background or sidebar.

## 2. Problem & Stakes
- **Purpose:** Why this matters for the audience.
- **Content:** Manual DLC analysis is slow/error-prone (2–3 hours per dataset), blocks non-programmers, risks inconsistency.
- **Evidence/Assets:** Time comparison (2–3h → ~5m); impacted users (Sengupta Lab students/techs; secondary labs).
- **Images:** None required (text focus).

## 3. Value Proposition
- **Purpose:** How we solve the problem.
- **Content:** Validate DLC CSVs, auto-build configs, run kinematic metrics, render publication-ready graphs fast.
- **Evidence/Assets:** Before/after workflow bullets; reduced errors + accessible UI.
- **Images:** One product screenshot (e.g., Config Generator or Graph Viewer) as visual anchor.

## 4. User Workflow (High-Level)
- **Purpose:** Make the flow tangible.
- **Content:** CSV upload → validation → config selection/generation → calculations → graph rendering → export.
- **Evidence/Assets:** Reference scenes in UI.
- **Images:** Small strip of UI screenshots to illustrate each step (Landing, CSV input, Config Generator, Calculation, Graph Viewer).

## 5. Demo Overview (What You’ll Show)
- **Purpose:** Set expectations for the live demo/screenshots.
- **Content:** Which scenes/features will be shown (Landing, CSV/JSON input, Config Generator, Calculation progress, Graph Viewer).
- **Evidence/Assets:** Fallback note for screenshots if live demo hiccups.
- **Images:** Contact sheet of the 3–4 demo screenshots you’ll use.

## 6. Product Demo (Screens)
- **Purpose:** Show, don’t tell.
- **Content:** Sequence of UI screenshots:
  1) CSV/JSON validation with errors/warnings,
  2) Config Generator with body-part detection,
  3) Calculation progress/status,
  4) Graph Viewer (fin/tail angle-distance timelines, spines snapshots), exports.
- **Evidence/Assets:** Highlight config-driven shown_outputs toggles; Kaleido PNG rendering.
- **Images:** Full-size annotated product screenshots for each step; graph output PNGs captured from the app.

## 7. Work Accomplished (Iteration)
- **Purpose:** Demonstrate progress this iteration.
- **Content:** New/updated features (graph plotters, config generation, validation UX), refreshed docs/README, environment.yml, OSS files.
- **Evidence/Assets:** Before/after notes; unit tests for graphs/UI; cite files where relevant.
- **Images:** A couple of iteration-specific UI screenshots (e.g., new graph view, updated config generator).

## 8. Technical Decisions (Plain-English)
- **Purpose:** Non-technical clarity on why choices were made.
- **Content:** PyQt desktop (offline, lab-friendly), Plotly+Kaleido for exportable graphs, modular graphs runner (config-driven plot selection), validators for schema/likelihood, SQLite helper for reproducibility.
- **Evidence/Assets:** Brief architecture sketch (app.py → scenes → core pipelines).
- **Images:** Optional single architecture screenshot if available; otherwise none.

## 9. Challenges & Mitigations
- **Purpose:** Show ownership of risks.
- **Content:** Plot rendering reliability (fallback screenshots), DLC schema variance (validators + config generator), usability for non-coders (guided scenes), demo risk handling.
- **Evidence/Assets:** Notes from meeting minutes; mitigation bullets.
- **Images:** None required (keep text clear).

## 10. Results & Value
- **Purpose:** Quantify impact.
- **Content:** Time saved (~2.5h → ~5m); standardized metrics; accessibility for students/techs.
- **Evidence/Assets:** ROI estimate (~$5k/year per lab at 50 datasets); screenshots of outputs.
- **Images:** Graph output PNG from the app; optional single ROI stat overlay (text-based).

## 11. Future Vision (Roadmap)
- **Purpose:** What the next investment unlocks.
- **Content:** Short-term: finish plot suite (movement tracks/heatmaps), export UX (PNG/SVG/Excel ranges), clickable points/local extrema, installer. Medium-term: multi-CSV overlays, batch runs, formatted exports, UI polish. Long-term: multi-species, ML behavior classification, schema normalization, cloud/share.
- **Evidence/Assets:** Phased list; client asks from meeting notes.
- **Images:** Optional small UI mock/screenshot for a future plot if available; otherwise text only.

## 12. Investment Case
- **Purpose:** Why to fund another iteration.
- **Content:** Proven end-to-end pipeline + docs + env; clear roadmap; team delivery track record; meaningful time/quality gains.
- **Evidence/Assets:** Tie savings to stakeholder outcomes; note OSS readiness (MIT license, contributing, CoC).
- **Images:** None required; keep it concise.

## 13. Team & Process
- **Purpose:** Show collaboration credibility.
- **Content:** Roles (Tech Lead, Developers), workflow (feature branches, code review, unit tests, product docs), coordination with client/advisor.
- **Evidence/Assets:** Brief nod to testing (`pytest` suites for parser/metrics/graphs/UI).
- **Images:** Optional team screenshot/avatar grid; otherwise text only.

## 14. Risks & Mitigations (Forward-Looking)
- **Purpose:** Preempt concerns.
- **Content:** Demo risk (offline assets), adoption (UX polish, installer), data quality (validators/configs), CI gap (plan to add GH Actions).
- **Evidence/Assets:** Specific next actions per risk.
- **Images:** None required.

## 15. Call to Action & Close
- **Purpose:** End decisively.
- **Content:** Ask for approval of next iteration scope/funding; invite questions; thank audience.
- **Evidence/Assets:** Link to repo, environment.yml for reproducibility; mention backup demo materials.
- **Images:** One clean product screenshot (e.g., Graph Viewer) as background; otherwise minimal.

## Appendix Slides (Optional Backup)
- Screenshots of Graph Viewer outputs (fin/tail, spines).
- Sample config JSON snippet and validation errors.
- Architecture diagram (app → scenes → core pipelines).
- Test summary (unit suites present; CI planned).
- **Images:** High-res product screenshots only (graphs/UI); no generated diagrams/tables.
