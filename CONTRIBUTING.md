# Contributing to CV Zebrafish

Thanks for your interest in contributing! Please follow these guidelines to keep contributions smooth and predictable.

## Getting Set Up
1) Install dependencies with Conda:
```bash
conda env create -f environment.yml
conda activate cvzebrafish
```
2) Run tests to verify your setup:
```bash
pytest
```

## How to Contribute
- Fork and create a feature branch from `main` (e.g., `feature/your-change`).
- Keep changes focused and incremental. Update docs when behavior or setup changes.
- Add or update tests when fixing bugs or adding features.
- Open a pull request to `main` with:
  - Summary of changes and motivation.
  - Testing performed (`pytest`, manual steps if UI-related).

## Coding Standards
- Python 3.10.
- Prefer small, testable functions and clear naming.
- Run `pytest` before opening a PR.

## Reporting Issues
Use the issue templates:
- Bug report: include steps to reproduce, expected vs. actual behavior, logs/traceback, and environment details.
- Feature request: describe the problem, proposed solution, and acceptance criteria.

## Code of Conduct
By participating, you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md). Report concerns to the maintainers via GitHub issues or direct message.
