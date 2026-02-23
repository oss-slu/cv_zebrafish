from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import (
    QMainWindow, QToolBar, QAction, QStackedWidget, QShortcut, QMessageBox,
    QWidget, QVBoxLayout, QApplication
)
from PyQt5.QtGui import QKeySequence

from src.ui.scenes.LandingScene import LandingScene
from src.ui.scenes.GraphViewerScene import GraphViewerScene, get_graph_names_to_build
from src.ui.scenes.ConfigGeneratorScene import ConfigGeneratorScene
from src.ui.scenes.VerifyScene import VerifyScene
from ui.scenes.ConfigSelectionScene import  ConfigSelectionScene

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
        self.setMinimumSize(QSize(900, 350))
        self.resize(QSize(1000, 700))

        # shortcut to close the window
        QShortcut(QKeySequence("Ctrl+W"), self, activated=self.close)

        ### adds scenes ###

        # QStackedWidget to hold scenes



        ##CHANGED _______________________
        #self.stack = QStackedWidget()
        #self.setCentralWidget(self.stack)
        ## ADDED
        # QStackedWidget to hold scenes
        self.stack = QStackedWidget()

        # Create progress indicator
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
        #_______________________________




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
        self._update_navigator()

        ### signal handlers ###
        self._verify_last_csv_path = None
        self._calculation_has_run = False
        self._generate_config_visited = False

        self.scenes["Landing"].session_selected.connect(self.loadSession)
        self.scenes["Landing"].create_new_session.connect(self.createSession)
        self.scenes["Verify"].csv_selected.connect(self.on_verify_csv_selected)
        self.scenes["Verify"].json_selected.connect(self.on_verify_json_selected)
        self.scenes["Verify"].generate_json_requested.connect(self.goToGenerateConfig)
        self.scenes["Generate Config"].config_generated.connect(self.goToSelectConfig)
        self.scenes["Select Configuration"].data_generated.connect(self.handle_data)



    def loadSession(self, path):
        print("Loading session from:", path)

        self.currentSession = load_session_from_json(path)
        if self.currentSession is None:
            QMessageBox.warning(self, "Bad Session", "Please choose a session.")

            return
        
        self.broadcastSession()

        self._switch_to_scene(self.scenes["Select Configuration"], "Select Configuration")
        self._update_navigator()

    def createSession(self, session_name):
        print("Creating new session with config.")

        self.currentSession = Session(session_name)
        self.currentSession.save()

        self.broadcastSession()

        self._switch_to_scene(self.scenes["Generate Config"], "Generate Config")
        self._generate_config_visited = True
        self._update_navigator()

    def broadcastSession(self):
        self.scenes["Generate Config"].load_session(self.currentSession)
        self.scenes["Select Configuration"].load_session(self.currentSession)
        self.scenes["Graphs"].load_session(self.currentSession)
        self._update_navigator()

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

    def handle_data(self, data):
        print("Data received in MainWindow")
        config_scene = self.scenes["Select Configuration"]
        graphs_scene = self.scenes["Graphs"]

        def progress_callback(n, total, graph_name):
            config_scene.set_progress(n, total, graph_name)

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
            self._calculation_has_run = True
            self._switch_to_scene(graphs_scene, "Graphs")
        else:
            graphs_scene.set_data(data)
            self._switch_to_scene(graphs_scene, "Graphs")
        config_scene.set_progress(0, 0, "")
        self._update_navigator()

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
        self.stack.setCurrentWidget(scene)
        self.progress_indicator.set_current_step(scene_name)
        self.scene_navigator.set_current_step(scene_name)
        self._update_navigator()