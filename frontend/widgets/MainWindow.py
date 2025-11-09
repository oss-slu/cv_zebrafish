from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import QMainWindow, QToolBar, QAction, QStackedWidget, QShortcut
from PyQt5.QtGui import QKeySequence

from frontend.widgets.LandingScene import LandingScene
from frontend.widgets.ConfigScene import ConfigScene
from frontend.widgets.GraphViewerScene import GraphViewerScene
from frontend.widgets.CalculationScene import CalculationScene
from .ConfigGeneratorScene import ConfigGeneratorScene
from frontend.widgets.VerifyScene import VerifyScene

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        startScene = "Landing"

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
            "Verify": VerifyScene(),
            "Config": ConfigScene(),
            "Calculation": CalculationScene(),
            "Graphs": GraphViewerScene(),
            "Generate Config": ConfigGeneratorScene()
        }

        # Add scenes to stack
        for scene in self.scenes.values():
            self.stack.addWidget(scene)

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

        #self.scenes["CSV_File"].csv_selected.connect(self.handle_csv)
        #self.scenes["Config"].config_generated.connect(self.handle_config)
        #self.scenes["JSON_File"].json_selected.connect(self.handle_json)

        self.scenes["Landing"].session_selected.connect(self.loadSession)
        self.scenes["Landing"].new_config_requested.connect(self.createSession)
        self.scenes["Landing"].session_selected.connect(self.loadSession)
        self.scenes["Landing"].new_config_requested.connect(self.openConfigGenerator)
        self.scenes["Landing"].create_new_session.connect(self.createSession)

    def openConfigGenerator(self, csv_path):
        print("Opening Config Generator with:", csv_path)
        self.scenes["Generate Config"].set_csv(csv_path)
        self.stack.setCurrentWidget(self.scenes["Generate Config"])

    def handle_csv(self, path):
        print("CSV selected:", path)
        self.scenes["Calculation"].set_csv_path(path)
        self.scenes["Landing"].setCompleted("CSV_File")

    '''
    def handle_json(self, path):
        print("JSON selected:", path)
        self.scenes["Calculation"].set_config(path)
        self.scenes["Landing"].setCompleted("JSON_File")

    def handle_config(self, config):
        print("Config generated.")
        self.scenes["Calculation"].set_config(config)
        self.scenes["Landing"].setCompleted("Config")
    '''

    def handle_data(self, data):
        print("Data received in MainWindow")
        self.scenes["Graphs"].set_data(data)
        self.stack.setCurrentWidget(self.scenes["Graphs"])

    def loadSession(self, path):
        print("Loading session from:", path)
        self.scenes["Calculation"].load_session(path)
        self.stack.setCurrentWidget(self.scenes["Calculation"])

    def createSession(self):
        print("Creating new session with config.")
        self.stack.setCurrentWidget(self.scenes["Generate Config"])