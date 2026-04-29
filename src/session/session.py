from os import path
import json
from pathlib import Path

from PyQt5.QtCore import pyqtSignal, QObject
from PyQt5.QtWidgets import QMessageBox

from app_platform.paths import (
    SESSION_JSON_FILENAME,
    resolve_folder_graphs_asset_paths,
    resolve_graph_asset_path,
    session_bundle_dir,
)

class Session(QObject):
    session_updated = pyqtSignal()

    def __init__(self, name):
        super().__init__()
        self.name = name
        # Absolute path of the JSON this session was loaded from / last saved to (see save()).
        self.json_path = None
        self.csvs = {}
        # Folder CSVs: folder_path -> [csv_file_paths]
        self.csv_folders = {}
        # Folder graph outputs: folder_path -> config_path -> csv_file_path -> [graph_asset_paths]
        self.folder_graphs = {}
        # Persisted UI resume point (Landing is intentionally not resumable).
        self.last_scene = "Verify"
        # Persisted UI capability flag used for navigation enablement on resume.
        self.calculation_has_run = False
        # Persisted “last used” calculation inputs (so we can rebuild graphs on reopen).
        self.last_csv_path = None
        self.last_config_path = None
    
    def addCSV(self, csv_path):
        if not path.exists(csv_path):
            print(f"[Session] CSV path does not exist: {csv_path}")
            return

        # Idempotent: never overwrite an existing CSV entry, because that would
        # wipe any configs/graphs already attached to it (losing progress).
        if csv_path not in self.csvs:
            self.csvs[csv_path] = {}
            self.session_updated.emit()

    def addCSVFolder(self, folder_path: str, csv_files: list[str]):
        """Register a folder of CSVs as a single CSV input ID."""
        if not folder_path or not path.exists(folder_path):
            print(f"[Session] Folder path does not exist: {folder_path}")
            return
        # Store file list in stable order
        files = [f for f in (csv_files or []) if f and path.exists(f)]
        self.csv_folders[folder_path] = files
        if folder_path not in self.csvs:
            self.csvs[folder_path] = {}
        self.session_updated.emit()

    def is_folder_csv(self, csv_id: str) -> bool:
        return csv_id in (self.csv_folders or {})

    def get_folder_files(self, csv_id: str) -> list[str]:
        return list((self.csv_folders or {}).get(csv_id, []) or [])

    def addFolderGraph(self, folder_path: str, config_path: str, csv_file_path: str, graph_asset_path: str):
        """Record a graph output for one CSV inside a folder run."""
        if not folder_path or not config_path or not csv_file_path or not graph_asset_path:
            return
        if not path.exists(graph_asset_path):
            print(f"[Session] Graph asset path does not exist: {graph_asset_path}")
            return

        fg = self.folder_graphs.setdefault(folder_path, {})
        cfg_bucket = fg.setdefault(config_path, {})
        assets = cfg_bucket.setdefault(csv_file_path, [])
        if graph_asset_path not in assets:
            assets.append(graph_asset_path)
            self.session_updated.emit()

    def getFolderGraphs(self, folder_path: str, config_path: str):
        """Return {csv_file_path: [graph_asset_paths]} for this folder+config."""
        return dict(((self.folder_graphs or {}).get(folder_path, {}) or {}).get(config_path, {}) or {})
        
    def addConfigToCSV(self, csv_path, config_path):
        if not path.exists(config_path):
            print(f"[Session] Config path does not exist: {config_path}")
            return

        # Be permissive: ensure the CSV node exists, then attach config.
        if csv_path not in self.csvs:
            self.csvs[csv_path] = {}

        if config_path not in self.csvs[csv_path]:
            self.csvs[csv_path][config_path] = []
            self.session_updated.emit()

    def addGraphToConfig(self, config_path, graph_path):
        if not path.exists(graph_path):
            print(f"[Session] Graph path does not exist: {graph_path}")
            return
        
        for _, configs in self.csvs.items():
            if config_path in configs:
                graphs = configs[config_path]
                # Avoid duplicates when recalculations re-save the same asset path.
                if graph_path not in graphs:
                    graphs.append(graph_path)
                    self.session_updated.emit()

    def getConfigsForCSV(self, csv_path):
        return self.csvs.get(csv_path, {})

    def getAllCSVs(self):
        return list(self.csvs.keys())
    
    def getAllConfigs(self):
        all_configs = []
        for configs in self.csvs.values():
            all_configs.extend(configs.keys())
        return all_configs
    
    def getGraphsForConfig(self, config_path):
        for _, configs in self.csvs.items():
            if config_path in configs:
                return configs[config_path]
        return []
    
    def getAllGraphs(self):
        # Unique, stable order
        all_graphs = []
        seen = set()
        for configs in self.csvs.values():
            for graphs in configs.values():
                for g in graphs:
                    if g in seen:
                        continue
                    seen.add(g)
                    all_graphs.append(g)
        return all_graphs

    def has_saved_graph_assets(self) -> bool:
        """True if session JSON records any graph file paths (PNG/HTML) under csvs or folder_graphs."""
        for configs in (self.csvs or {}).values():
            for graphs in (configs or {}).values():
                if graphs:
                    return True
        for _folder, cfgs in (self.folder_graphs or {}).items():
            for _cfg, per_csv in (cfgs or {}).items():
                for _csv, assets in (per_csv or {}).items():
                    if assets:
                        return True
        return False

    def getName(self):
        return self.name
    
    def toDict(self):
        # When saving, dedupe graph path lists so session files don't grow endlessly.
        deduped_csvs = {}
        for csv_path, configs in (self.csvs or {}).items():
            deduped_configs = {}
            for config_path, graphs in (configs or {}).items():
                unique_graphs = []
                seen = set()
                for g in (graphs or []):
                    if g in seen:
                        continue
                    seen.add(g)
                    unique_graphs.append(g)
                deduped_configs[config_path] = unique_graphs
            deduped_csvs[csv_path] = deduped_configs

        deduped_folder_graphs = {}
        for folder_path, cfgs in (self.folder_graphs or {}).items():
            dedup_cfgs = {}
            for config_path, per_csv in (cfgs or {}).items():
                dedup_per_csv = {}
                for csv_file, assets in (per_csv or {}).items():
                    uniq = []
                    seen = set()
                    for a in (assets or []):
                        if a in seen:
                            continue
                        seen.add(a)
                        uniq.append(a)
                    dedup_per_csv[csv_file] = uniq
                dedup_cfgs[config_path] = dedup_per_csv
            deduped_folder_graphs[folder_path] = dedup_cfgs

        return {
            "name": self.name,
            "csvs": deduped_csvs,
            "csv_folders": dict(self.csv_folders or {}),
            "folder_graphs": deduped_folder_graphs,
            "last_scene": getattr(self, "last_scene", "Verify"),
            "calculation_has_run": bool(getattr(self, "calculation_has_run", False)),
            "last_csv_path": getattr(self, "last_csv_path", None),
            "last_config_path": getattr(self, "last_config_path", None),
        }
    
    def length(self):
        return len(self.csvs)

    def save(self):
        if getattr(self, "json_path", None):
            file_path = self.json_path
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        else:
            bundle = session_bundle_dir(self.name)
            bundle.mkdir(parents=True, exist_ok=True)
            fp = bundle / SESSION_JSON_FILENAME
            file_path = path.normpath(path.abspath(str(fp)))
            self.json_path = file_path

        with open(file_path, 'w') as f:
            json.dump(self.toDict(), f, indent=4)

    def checkExists(self, csv_path=None, config_path=None):
        if csv_path in self.csvs and config_path is None:
            return True
        if csv_path and config_path:
            return config_path in self.csvs.get(csv_path, {})

        return config_path in self.getAllConfigs()

    def removeConfigFromCSV(self, csv_path: str, config_path: str) -> None:
        """Detach one JSON config (and its graph paths) from a CSV row; prune folder_graphs."""
        if not csv_path or not config_path:
            return
        row = self.csvs.get(csv_path)
        if not row or config_path not in row:
            return
        del row[config_path]
        fg = self.folder_graphs or {}
        if csv_path in fg and config_path in fg[csv_path]:
            del fg[csv_path][config_path]
            if not fg[csv_path]:
                del fg[csv_path]
        if getattr(self, "last_csv_path", None) == csv_path and getattr(
            self, "last_config_path", None
        ) == config_path:
            self.last_config_path = None
        self.session_updated.emit()

    def removeCSV(self, csv_path: str) -> None:
        """Remove a CSV (or folder) row and all attached configs / folder graph records."""
        if not csv_path:
            return
        if csv_path in self.csvs:
            del self.csvs[csv_path]
        cf = self.csv_folders or {}
        if csv_path in cf:
            del self.csv_folders[csv_path]
        fg = self.folder_graphs or {}
        if csv_path in fg:
            del fg[csv_path]
        if getattr(self, "last_csv_path", None) == csv_path:
            self.last_csv_path = None
            self.last_config_path = None
        self.session_updated.emit()

def _session_resolved_path(stored: str, session_name: str) -> str:
    """Prefer a path that exists under the current repo clone, else *stored*."""
    if not stored:
        return stored
    r = resolve_graph_asset_path(stored, session_name)
    if r:
        return r
    r = resolve_graph_asset_path(stored, None)
    return r or stored


def load_session_from_json(json_path):
    """Load a session from a JSON file."""
    try:
        with open(json_path, "r") as f:
            data = json.load(f)
    except Exception as e:
        raise ValueError(f"Could not read session file: {e}")

    session_name = data.get("name", "UnnamedSession")
    if session_name == "UnnamedSession":
        raise ValueError("Session file is missing a valid name.")

    session = Session(session_name)
    session.json_path = path.normpath(path.abspath(str(json_path)))
    # Optional resume point (older session files won't have this).
    last_scene = data.get("last_scene") or "Verify"
    session.last_scene = last_scene
    session.calculation_has_run = bool(data.get("calculation_has_run", False))
    lcsv = data.get("last_csv_path")
    session.last_csv_path = _session_resolved_path(lcsv, session_name) if lcsv else None
    lcfg = data.get("last_config_path")
    session.last_config_path = _session_resolved_path(lcfg, session_name) if lcfg else None
    session.csv_folders = data.get("csv_folders") or {}
    session.folder_graphs = resolve_folder_graphs_asset_paths(
        data.get("folder_graphs") or {}, session_name
    )

    csvs = data.get("csvs", {})
    for csv_path, configs in csvs.items():
        csv_id = _session_resolved_path(csv_path, session_name)
        session.addCSV(csv_id)
        for config_path, graphs in configs.items():
            cfg_id = _session_resolved_path(config_path, session_name)
            session.addConfigToCSV(csv_id, cfg_id)
            for graph_path in graphs:
                resolved = resolve_graph_asset_path(graph_path, session_name)
                if resolved:
                    session.addGraphToConfig(cfg_id, resolved)

    return session

def save_session_to_json(session, json_path):
    """Save a session to a JSON file."""
    data = session.toDict()
    try:
        with open(json_path, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        raise ValueError(f"Could not write session file: {e}")
    session.json_path = path.normpath(path.abspath(str(json_path)))