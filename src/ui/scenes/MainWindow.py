from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import (
    QMainWindow, QToolBar, QAction, QStackedWidget, QShortcut, QMessageBox
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

        # Create toolbar
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(toolbar)

        # shortcut to close the window
        QShortcut(QKeySequence("Ctrl+W"), self, activated=self.close)

        ### adds scenes ###

        # QStackedWidget to hold scenes
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

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

        # Toolbar buttons
        for name, scene in self.scenes.items():
            action = QAction(name, self)
            action.triggered.connect(
                lambda checked, s=scene: self.stack.setCurrentWidget(s))
            toolbar.addAction(action)

            # sets cursor to hand for valid toolbar actions
            widget = toolbar.widgetForAction(action)
            if widget:
                widget.setCursor(Qt.PointingHandCursor)

        # Show first scene
        self.stack.setCurrentWidget(self.scenes[startScene])

        ### signal handlers ###

        self.scenes["Calculation"].data_generated.connect(self.handle_data)
        self.scenes["Landing"].session_selected.connect(self.loadSession)
        self.scenes["Landing"].create_new_session.connect(self.createSession)

    def loadSession(self, path):
        print("Loading session from:", path)

        self.currentSession = load_session_from_json(path)
        if self.currentSession is None:
            QMessageBox.warning(self, "Bad Session", "Please choose a session.")

            return

        self.scenes["Generate Config"].load_session(self.currentSession)
        self.scenes["Select Configuration"].load_session(self.currentSession)

        self.stack.setCurrentWidget(self.scenes["Select Configuration"])

    def createSession(self, session_name):
        print("Creating new session with config.")

        self.currentSession = Session(session_name)
        self.currentSession.save()

        self.scenes["Generate Config"].load_session(self.currentSession)
        self.scenes["Select Configuration"].load_session(self.currentSession)

        self.stack.setCurrentWidget(self.scenes["Generate Config"])

    def handle_data(self, data):
        print("Data received in MainWindow")
        self.scenes["Graphs"].set_data(data)
        self.stack.setCurrentWidget(self.scenes["Graphs"])

    def toggle_theme(self):
        if self.current_theme == "light":
            self.current_theme = "dark"
        else:
            self.current_theme = "light"

        apply_theme(self, THEMES[self.current_theme])
