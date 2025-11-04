# CV_Zebrafish

### Python Environment

You can use Conda or a virtual environment created with `python -m venv`.

#### Option A: pip / venv

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
pip install -r requirements.txt
```

#### Option B: Conda

```bash
conda env create -f environment.yml
conda activate dlc
```

Deactivate the environment with `deactivate` (venv) or `conda deactivate` when you finish.

### Running the app

From the repository root, run:

```bash
python app.py
```

## License
This project is licensed under the [MIT License](./LICENSE) — see the file for details.
