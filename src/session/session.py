from os import path
import json

from PyQt5.QtCore import pyqtSignal, QObject

from src.app_platform.paths import sessions_dir

class Session(QObject):
    session_updated = pyqtSignal()

    def __init__(self, name):
        super().__init__()
        self.name = name
        self.csvs = {}
    
    def addCSV(self, csv_path):
        self.csvs[csv_path] = {}

        self.session_updated.emit()

    def addConfigToCSV(self, csv_path, config_path):
        if csv_path in self.csvs:
            self.csvs[csv_path][config_path] = []
        
        self.session_updated.emit()

    def addGraphToConfig(self, config_path, graph_path):
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
        }
    
    def length(self):
        return len(self.csvs)

    def save(self):
        file_path = path.join(sessions_dir(), f"{self.name}.json")

        with open(file_path, 'w') as f:
            json.dump(self.toDict(), f, indent=4)

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

    csvs = data.get("csvs", {})
    for csv_path, cfgs in (csvs or {}).items():
        session.addCSV(csv_path)
        configs = cfgs or []
        for config in configs:
            session.addConfigToCSV(csv_path, config)

    return session

def save_session_to_json(session, json_path):
    """Save a session to a JSON file."""
    data = session.toDict()
    try:
        with open(json_path, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        raise ValueError(f"Could not write session file: {e}")