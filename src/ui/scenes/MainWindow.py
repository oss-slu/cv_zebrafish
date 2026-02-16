from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import (
    QMainWindow, QToolBar, QAction, QStackedWidget, QShortcut, QMessageBox,
    QWidget, QVBoxLayout
)
from PyQt5.QtGui import QKeySequence

from src.ui.scenes.LandingScene import LandingScene
from src.ui.scenes.GraphViewerScene import GraphViewerScene
from src.ui.scenes.CalculationScene import CalculationScene
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
            "Calculation": CalculationScene(),
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


        self.scenes["Landing"].session_selected.connect(self.loadSession)
        self.scenes["Landing"].create_new_session.connect(self.createSession)
        self.scenes["Verify"].csv_selected.connect(self.on_verify_csv_selected)
        self.scenes["Verify"].json_selected.connect(self.on_verify_json_selected)
        self.scenes["Verify"].generate_json_requested.connect(self.goToGenerateConfig)
        self.scenes["Generate Config"].config_generated.connect(self.goToSelectConfig)
        self.scenes["Select Configuration"].setCalculationScene(self.scenes["Calculation"])
        self.scenes["Calculation"].data_generated.connect(self.handle_data)



    def loadSession(self, path):
        print("Loading session from:", path)

        self.currentSession = load_session_from_json(path)
        if self.currentSession is None:
            QMessageBox.warning(self, "Bad Session", "Please choose a session.")

            return
        
        self.broadcastSession()

        self._switch_to_scene(self.scenes["Select Configuration"], "Select Configuration")

    def createSession(self, session_name):
        print("Creating new session with config.")

        self.currentSession = Session(session_name)
        self.currentSession.save()

        self.broadcastSession()

        self._switch_to_scene(self.scenes["Generate Config"], "Generate Config")

    def broadcastSession(self):
        self.scenes["Generate Config"].load_session(self.currentSession)
        self.scenes["Select Configuration"].load_session(self.currentSession)
        self.scenes["Calculation"].load_session(self.currentSession)
        self.scenes["Graphs"].load_session(self.currentSession)
        
    def handle_data(self, data):
        print("Data received in MainWindow")
        self.scenes["Graphs"].set_data(data)
        self._switch_to_scene(self.scenes["Graphs"], "Graphs")

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
        current_name = self.progress_indicator.steps[self.progress_indicator.current_step_index]

        if current_name not in steps:
            return

        i = steps.index(current_name)
        if i >= len(steps) - 1:
            return

        next_name = steps[i + 1]
        self._switch_to_scene(self.scenes[next_name], next_name)

    def _switch_to_scene(self, scene, scene_name):
        """Switch to a scene and update the progress indicator."""
        self.stack.setCurrentWidget(scene)
        self.progress_indicator.set_current_step(scene_name)
        self.scene_navigator.set_current_step(scene_name)