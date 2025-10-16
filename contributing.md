🧭 Contributing to CV Zebrafish

Thank you for your interest in contributing to CV Zebrafish — a computer vision-based behavioral analysis tool for zebrafish tracking and visualization.
This project is part of the Open Source Software (OSS) course at Saint Louis University, and we welcome contributions from students, researchers, and open-source enthusiasts who want to advance data-driven behavioral analysis.

🛠️ Project Setup

1️⃣ Fork and Clone the Repository

Start by forking the repository and cloning it locally.

git clone https://github.com/<your-username>/cv_zebrafish.git

cd cv_zebrafish

2️⃣ Set Up the Conda Environment

We use Conda to manage dependencies for both DeepLabCut and the PyQt5-based frontend.

Create the environment:

conda env create -f environment.yml


Activate it whenever you work on the project:

conda activate dlc


When you’re finished, deactivate it:

conda deactivate


3️⃣ Running the Application

To start the GUI:

cd frontend

python app.py


This launches the PyQt5-based interface for uploading CSV/JSON files, verifying them, and visualizing zebrafish metrics.

🌱 Branching Workflow

We follow a feature-branch workflow to ensure clean commits and easier PR reviews.

Always branch off the latest main:

git checkout main

git pull origin main

git checkout -b feature/<your-feature-name>


Make your changes and commit frequently with descriptive messages:

feat: add JSON verifier scene

fix: resolve config parameter validation bug

docs: update README with setup steps


Push your branch to GitHub:

git push origin feature/<your-feature-name>

✅ Pull Requests

When you’re ready to submit your work:

Ensure your code runs locally without errors.

Follow PEP 8 style guidelines.

Add docstrings and inline comments for all new functions.

Reference related issue numbers in your PR description, e.g.:

Fixes #14


Include screenshots or logs for any UI or verifier-related updates.

Wait for review by the Tech Lead (Madhuritha Alle) or another reviewer before merging.

🧩 Code Style Guidelines

Use descriptive and consistent function names.

Keep functions short and modular.

Add meaningful docstrings for classes and functions.

Use camelCase for variables in frontend UI code and snake_case for backend logic.

Avoid hardcoding file paths — use relative or configurable paths.


Communication & Collaboration

For questions or discussions, please open a GitHub Issue or comment directly on related Pull Requests.

For internal contributors (SLU OSS team members), coordination happens through private communication channels managed by the Tech Lead.

Tech Lead: @madhuritha22

Client Contact: Dr. Mohini Sengupta

Faculty Advisor: Dr. Daniel Shown


🪧 Good First Issues

If you’re new, here are great places to start:

Add or improve docstrings in calculation and plotting modules.

Write unit tests for CSV/JSON verifiers.

Enhance README with setup screenshots or architecture diagrams.

Refine UI layout in frontend/widgets/.

Help document the outputDisplay and GraphViewer modules.

Labels to look for:

good first issue

documentation

testing

frontend / backend

❤️ Acknowledgments

This project is part of the Open Source Software (OSS) initiative at Saint Louis University (SLU).
It is developed under the guidance of Prof. Daniel Shown with collaboration from Dr. Mohini Sengupta and her lab.
Special thanks to all contributors who continue to make this project more open, accessible, and impactful for the research community.
