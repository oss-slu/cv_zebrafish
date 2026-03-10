from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import (
    QMainWindow, QToolBar, QAction, QStackedWidget, QShortcut, QMessageBox,
    QWidget, QVBoxLayout, QApplication
)
from PyQt5.QtGui import QKeySequence
from pathlib import Path

from src.ui.scenes.LandingScene import LandingScene
from src.ui.scenes.GraphViewerScene import GraphViewerScene, get_graph_names_to_build
from src.ui.scenes.ConfigGeneratorScene import ConfigGeneratorScene
from src.ui.scenes.VerifyScene import VerifyScene
from ui.scenes.ConfigSelectionScene import  ConfigSelectionScene

import src.core.calculations.Driver as calculations
import src.core.parsing.Parser as parser

from src.session.session import *

from styles.themes import apply_theme, THEMES
from src.ui.components.ThemeToggle import ThemeToggle
from src.ui.components.ProgressIndicator import ProgressIndicator
from src.ui.components.SceneNavigator import SceneNavigator

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        startScene = "Landing"

        # light theme by default
        self.current_theme = "light"
        apply_theme(self, THEMES[self.current_theme])

        self.currentSession = None

        ### window property setup ###

        # Sets default main window properties
        self.setWindowTitle("CV Zebrafish")
        # Minimum height bumped ~45% (350 -> ~510) to avoid UI cramping on small resizes.
        self.setMinimumSize(QSize(900, 510))
        self.resize(QSize(1000, 700))

        # shortcut to close the window
        QShortcut(QKeySequence("Ctrl+W"), self, activated=self.close)

        ### adds scenes ###

        self.stack = QStackedWidget()
        self.progress_indicator = ProgressIndicator()

        self.scene_navigator = SceneNavigator(
            steps=self.progress_indicator.steps,
            on_back=self.go_previous_scene,
            on_forward=self.go_next_scene
        )


        # Create a container widget to hold both progress indicator, navigator, and stack
        container = QWidget()
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        container_layout.addWidget(self.scene_navigator)
        container_layout.addWidget(self.progress_indicator)
        container_layout.addWidget(self.stack)
        container.setLayout(container_layout)

        # Set the container as central widget
        self.setCentralWidget(container)

        # initializes scenes
        self.scenes = {
            "Landing":  LandingScene(),
            "Generate Config": ConfigGeneratorScene(),
            "Select Configuration": ConfigSelectionScene(),
            "Graphs": GraphViewerScene(),
            "Verify": VerifyScene(),
        }

        # Add scenes to stack
        for scene in self.scenes.values():
            self.stack.addWidget(scene)

        # Theme toggle button
        self.theme_toggle = ThemeToggle(self, on_toggle=self.toggle_theme)
        self.theme_toggle.reposition()
        self.theme_toggle.show()

        # Show first scene
        self._switch_to_scene(self.scenes[startScene], startScene)

        ### signal handlers ###
        self._verify_last_csv_path = None
        self._calculation_has_run = False
        self._current_scene_name = startScene
        # When the user arrives at Select Configuration, Back should return to where they came from.
        self._select_config_back_target = "Generate Config"

        self.scenes["Landing"].session_selected.connect(self.loadSession)
        self.scenes["Landing"].create_new_session.connect(self.createSession)
        self.scenes["Verify"].csv_selected.connect(self.on_verify_csv_selected)
        self.scenes["Verify"].csv_folder_selected.connect(self.on_verify_folder_selected)
        self.scenes["Verify"].json_selected.connect(self.on_verify_json_selected)
        self.scenes["Verify"].generate_json_requested.connect(self.goToGenerateConfig)
        self.scenes["Generate Config"].config_generated.connect(self.goToSelectConfig)
        self.scenes["Select Configuration"].data_generated.connect(self.handle_data)



    def resizeEvent(self, event):
        """Keep floating controls anchored when window size changes."""
        super().resizeEvent(event)
        if hasattr(self, "theme_toggle") and self.theme_toggle is not None:
            self.theme_toggle.reposition()
            self.theme_toggle.raise_()

    def loadSession(self, path):
        print("Loading session from:", path)

        self.currentSession = load_session_from_json(path)
        if self.currentSession is None:
            QMessageBox.warning(self, "Bad Session", "Please choose a session.")

            return
        
        self.broadcastSession()

        # Resume to last scene (Landing is not resumable; fall back to Verify).
        self._calculation_has_run = bool(getattr(self.currentSession, "calculation_has_run", False))

        target = getattr(self.currentSession, "last_scene", None) or "Verify"
        if target == "Landing" or target not in self.scenes:
            target = "Verify"

        # If the last scene was Graphs, rebuild graphs on load using the last-used CSV+config.
        # (This uses the same pipeline as the Select Configuration \"Run Calculation\" button.)
        if target == "Graphs":
            last_csv = getattr(self.currentSession, "last_csv_path", None)
            last_cfg = getattr(self.currentSession, "last_config_path", None)
            if last_csv and last_cfg:
                config_scene = self.scenes["Select Configuration"]
                config_scene.csv_path = last_csv
                config_scene.config_path = last_cfg
                self._switch_to_scene(config_scene, "Select Configuration")
                config_scene.calculate()
                return
            # No remembered pair; fall back to Verify.
            target = "Verify"

        self._switch_to_scene(self.scenes[target], target)

    def createSession(self, session_name):
        print("Creating new session with config.")

        self.currentSession = Session(session_name)
        self.currentSession.save()

        self.broadcastSession()

        # New sessions start in Verify (Landing is never resumable).
        self._calculation_has_run = False
        self._switch_to_scene(self.scenes["Verify"], "Verify")

    def broadcastSession(self):
        self.scenes["Generate Config"].load_session(self.currentSession)
        self.scenes["Select Configuration"].load_session(self.currentSession)
        self.scenes["Graphs"].load_session(self.currentSession)
    def _has_csv_and_config(self):
        """True if current session has at least one CSV with at least one config."""
        if not self.currentSession:
            return False
        return any(
            len(configs) > 0
            for configs in self.currentSession.csvs.values()
        )

    def _update_navigator(self):
        """Update Back/Forward button state based on current step and completion state."""
        steps = self.progress_indicator.steps
        idx = self.progress_indicator.current_step_index
        current = steps[idx] if 0 <= idx < len(steps) else None

        has_session = self.currentSession is not None
        has_csv_and_config = self._has_csv_and_config()

        can_back = idx > 0
        can_forward = False
        if current == "Landing":
            can_forward = has_session
        elif current == "Verify":
            can_forward = has_csv_and_config
        elif current == "Generate Config":
            can_forward = has_csv_and_config
        elif current == "Select Configuration":
            can_forward = self._calculation_has_run
        elif current == "Graphs":
            can_forward = False

        self.scene_navigator.set_back_enabled(can_back)
        self.scene_navigator.set_forward_enabled(can_forward)

        # Status text should reflect the *actual* forward target (Verify skips Generate Config).
        if not current or not steps:
            self.scene_navigator.set_status_override(None)
            return

        left = steps[idx - 1] if idx > 0 else ""
        right = steps[idx + 1] if idx < (len(steps) - 1) else ""

        if current == "Verify":
            right = "Select Configuration"
        elif current == "Select Configuration":
            # If we jumped here from Verify, show Verify as the back neighbor.
            bt = getattr(self, "_select_config_back_target", None)
            if bt in ("Verify", "Generate Config"):
                left = bt

        if left and right:
            self.scene_navigator.set_status_override(f"{left}  ←  {current}  →  {right}")
        elif left:
            self.scene_navigator.set_status_override(f"{left}  ←  {current}")
        elif right:
            self.scene_navigator.set_status_override(f"{current}  →  {right}")
        else:
            self.scene_navigator.set_status_override(current)

    def handle_data(self, data):
        print("Data received in MainWindow")
        config_scene = self.scenes["Select Configuration"]
        graphs_scene = self.scenes["Graphs"]

        def progress_callback(n, total, graph_name):
            config_scene.set_progress(n, total, graph_name)

        # Folder run: compute graphs across all CSV files and show a CSV dropdown in Graphs.
        if data and isinstance(data, dict) and data.get("csv_files"):
            csv_files = list(data.get("csv_files") or [])
            config = data.get("config") or {}
            config_path = data.get("config_path") or (config.get("config_path") if isinstance(config, dict) else None)
            csv_folder_id = data.get("csv_folder")
            if not csv_files or not isinstance(config, dict):
                QMessageBox.warning(self, "Bad Input", "Folder payload is missing CSV files or config.")
                return
            if not csv_folder_id or not config_path:
                QMessageBox.warning(self, "Bad Input", "Folder payload is missing folder id or config path.")
                return

            # Phase 1: calculations across files
            results_by_csv = {}
            parsed_by_csv = {}

            total_files = len(csv_files)
            for idx, csv_path in enumerate(csv_files, start=1):
                config_scene.set_progress(idx, total_files, f"Calculating: {Path(csv_path).name}")
                try:
                    parsed_points = parser.parse_dlc_csv(csv_path, config)
                    results_df = calculations.run_calculations(parsed_points, config)
                except Exception as exc:
                    config_scene.set_progress(0, 0, "")
                    QMessageBox.warning(self, "Calculation Failed", f"Failed on {csv_path}:\n{exc}")
                    return
                results_by_csv[csv_path] = results_df
                parsed_by_csv[csv_path] = parsed_points

            # Phase 2: build graphs with aggregated progress
            total_graphs = 0
            file_payloads = []
            for csv_path in csv_files:
                payload = {
                    "results_df": results_by_csv[csv_path],
                    "config": config,
                    "csv_path": csv_path,
                    "parsed_points": parsed_by_csv[csv_path],
                }
                names = get_graph_names_to_build(payload)
                total_graphs += len(names)
                file_payloads.append((csv_path, payload))

            if total_graphs <= 0:
                config_scene.set_progress(0, 0, "")
                QMessageBox.warning(self, "No Graphs", "No graphs were requested or available for this config.")
                return

            graphs_by_csv = {}
            done = 0

            for csv_path, payload in file_payloads:
                def progress_callback(_n, _total, graph_name, _csv=csv_path):
                    nonlocal done
                    done += 1
                    config_scene.set_progress(done, total_graphs, f"{Path(_csv).name} — {graph_name}")

                graphs, _cfg = graphs_scene.build_graphs_with_progress(payload, progress_callback)
                if graphs is None:
                    continue
                graphs_by_csv[csv_path] = graphs

            if not graphs_by_csv:
                config_scene.set_progress(0, 0, "")
                QMessageBox.warning(self, "No Graphs", "Graphs could not be generated for this folder.")
                return

            # Persist folder graphs in per-CSV subfolders and record assets in the session.
            try:
                graphs_scene.save_folder_graphs(
                    csv_folder_id=csv_folder_id,
                    csv_files=csv_files,
                    config_path=config_path,
                    graphs_by_csv=graphs_by_csv,
                    config=config,
                )
            except Exception:
                pass

            graphs_scene.set_context(csv_id=csv_folder_id, config_path=config_path, csv_files=csv_files)
            graphs_scene.set_graphs_by_csv(graphs_by_csv, config=config)
            self._calculation_has_run = True
            try:
                if self.currentSession is not None:
                    self.currentSession.calculation_has_run = True
                    self.currentSession.save()
            except Exception:
                pass
            self._switch_to_scene(graphs_scene, "Graphs")
            config_scene.set_progress(0, 0, "")
            return

        if data and isinstance(data, dict) and data.get("results_df") is not None:
            names = get_graph_names_to_build(data)
            total = len(names)
            if total > 0:
                config_scene.set_progress(0, total, "Loading graphs...")
        graphs, config = graphs_scene.build_graphs_with_progress(data, progress_callback)

        if graphs is not None and config is not None:
            config_scene.set_progress(len(graphs), len(graphs), "Loading graphs...")
            QApplication.processEvents()
            graphs_scene.set_graphs(graphs, config=config)
            try:
                graphs_scene.set_context(
                    csv_id=data.get("csv_path") if isinstance(data, dict) else None,
                    config_path=(config.get("config_path") if isinstance(config, dict) else None),
                    csv_files=None,
                )
            except Exception:
                pass
            self._calculation_has_run = True
            # Persist navigation enablement for session resume.
            try:
                if self.currentSession is not None:
                    self.currentSession.calculation_has_run = True
                    self.currentSession.save()
            except Exception:
                pass
            self._switch_to_scene(graphs_scene, "Graphs")
        else:
            graphs_scene.set_data(data)
            self._switch_to_scene(graphs_scene, "Graphs")
        config_scene.set_progress(0, 0, "")

    def on_verify_csv_selected(self, csv_path):
        if not self.currentSession:
            QMessageBox.warning(self, "No Session", "Create or load a session first.")
            return

        # Store for later JSON attachment
        self._verify_last_csv_path = csv_path

        # Only add if not already present
        if not self.currentSession.checkExists(csv_path=csv_path):
            self.currentSession.addCSV(csv_path)
            self.currentSession.save()
        self._update_navigator()

    def on_verify_folder_selected(self, folder_path: str, csv_files):
        if not self.currentSession:
            QMessageBox.warning(self, "No Session", "Create or load a session first.")
            return

        try:
            files = list(csv_files or [])
        except Exception:
            files = []

        if not folder_path or not files:
            QMessageBox.warning(self, "Invalid Folder", "No CSV files were provided for this folder.")
            return

        try:
            self.currentSession.addCSVFolder(folder_path, files)
            self.currentSession.save()
        except Exception as exc:
            QMessageBox.warning(self, "Folder Error", f"Failed to add folder to session:\n{exc}")
            return

        self._update_navigator()

    def on_verify_json_selected(self, json_path):
        if not self.currentSession:
            QMessageBox.warning(self, "No Session", "Create or load a session first.")
            return

        if not self._verify_last_csv_path:
            QMessageBox.warning(
                self,
                "Upload CSV First",
                "Upload a CSV before adding a JSON config."
            )
            return

        csv_path = self._verify_last_csv_path

        if not self.currentSession.checkExists(csv_path=csv_path, config_path=json_path):
            self.currentSession.addConfigToCSV(csv_path, json_path)
            self.currentSession.save()
        self._update_navigator()

    def goToSelectConfig(self):
        self._switch_to_scene(self.scenes["Select Configuration"], "Select Configuration")

    def goToGenerateConfig(self):
        self._switch_to_scene(self.scenes["Generate Config"], "Generate Config")

    def toggle_theme(self):
        if self.current_theme == "light":
            self.current_theme = "dark"
        else:
            self.current_theme = "light"

        apply_theme(self, THEMES[self.current_theme])
    
    """Scene Switch Functions"""
    def go_previous_scene(self):
        steps = self.progress_indicator.steps
        current_name = self.progress_indicator.steps[self.progress_indicator.current_step_index]

        if current_name not in steps:
            return

        # Back from Select Configuration should return to the scene we came from (Verify or Generate Config).
        if current_name == "Select Configuration":
            target = getattr(self, "_select_config_back_target", None)
            if target in self.scenes:
                self._switch_to_scene(self.scenes[target], target)
                return

        i = steps.index(current_name)
        if i <= 0:
            return

        prev_name = steps[i - 1]
        self._switch_to_scene(self.scenes[prev_name], prev_name)

    def go_next_scene(self):
        steps = self.progress_indicator.steps
        idx = self.progress_indicator.current_step_index
        current_name = steps[idx]

        if current_name not in steps:
            return

        # Forward from Verify goes to Select Configuration (skip Generate Config)
        if current_name == "Verify":
            next_name = "Select Configuration"
        elif idx >= len(steps) - 1:
            return
        else:
            next_name = steps[idx + 1]

        has_session = self.currentSession is not None
        has_csv_and_config = self._has_csv_and_config()

        if current_name == "Landing" and not has_session:
            return
        if current_name == "Verify" and not has_csv_and_config:
            return
        if current_name == "Generate Config" and not has_csv_and_config:
            return
        if current_name == "Select Configuration" and not self._calculation_has_run:
            return

        self._switch_to_scene(self.scenes[next_name], next_name)

    def _switch_to_scene(self, scene, scene_name):
        """Switch to a scene and update the progress indicator."""
        prev = getattr(self, "_current_scene_name", None)
        self._current_scene_name = scene_name

        # Remember where we came from when entering Select Configuration.
        if scene_name == "Select Configuration" and prev in ("Verify", "Generate Config"):
            self._select_config_back_target = prev

        self.stack.setCurrentWidget(scene)
        self.progress_indicator.set_current_step(scene_name)
        self.scene_navigator.set_current_step(scene_name)
        self._update_navigator()

        # Persist resume point "as you go" (Landing is intentionally not resumable).
        if self.currentSession is not None and scene_name != "Landing":
            try:
                if getattr(self.currentSession, "last_scene", None) != scene_name:
                    self.currentSession.last_scene = scene_name
                self.currentSession.save()
            except Exception:
                pass