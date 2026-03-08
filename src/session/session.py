from os import path
import json

from PyQt5.QtCore import pyqtSignal, QObject
from PyQt5.QtWidgets import QMessageBox

from src.app_platform.paths import sessions_dir

class Session(QObject):
    session_updated = pyqtSignal()

    def __init__(self, name):
        super().__init__()
        self.name = name
        self.csvs = {}
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
                configs[config_path].append(graph_path)

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
        all_graphs = []
        for configs in self.csvs.values():
            for graphs in configs.values():
                all_graphs.extend(graphs)
        return all_graphs
    
    def getName(self):
        return self.name
    
    def toDict(self):
        return {
            "name": self.name,
            "csvs": self.csvs,
            "last_scene": getattr(self, "last_scene", "Verify"),
            "calculation_has_run": bool(getattr(self, "calculation_has_run", False)),
            "last_csv_path": getattr(self, "last_csv_path", None),
            "last_config_path": getattr(self, "last_config_path", None),
        }
    
    def length(self):
        return len(self.csvs)

    def save(self):
        file_path = path.join(sessions_dir(), f"{self.name}.json")

        with open(file_path, 'w') as f:
            json.dump(self.toDict(), f, indent=4)

    def checkExists(self, csv_path=None, config_path=None):
        if csv_path in self.csvs and config_path is None:
            return True
        if csv_path and config_path:
            return config_path in self.csvs.get(csv_path, {})

        return config_path in self.getAllConfigs()

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
    # Optional resume point (older session files won't have this).
    last_scene = data.get("last_scene") or "Verify"
    session.last_scene = last_scene
    session.calculation_has_run = bool(data.get("calculation_has_run", False))
    session.last_csv_path = data.get("last_csv_path")
    session.last_config_path = data.get("last_config_path")

    csvs = data.get("csvs", {})
    for csv_path, configs in csvs.items():
        session.addCSV(csv_path)
        for config_path, graphs in configs.items():
            session.addConfigToCSV(csv_path, config_path)
            for graph_path in graphs:
                session.addGraphToConfig(config_path, graph_path)

    return session

def save_session_to_json(session, json_path):
    """Save a session to a JSON file."""
    data = session.toDict()
    try:
        with open(json_path, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        raise ValueError(f"Could not write session file: {e}")