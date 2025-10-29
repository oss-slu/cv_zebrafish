from PyQt5.QtWidgets import QMainWindow, QToolBar, QAction, QStackedWidget, QShortcut
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QKeySequence

from frontend.widgets.CSVInputScene import CSVInputScene
from frontend.widgets.JSONInputScene import JSONInputScene
from frontend.widgets.GraphViewerScene import GraphViewerScene
from frontend.widgets.CalculationScene import CalculationScene
from frontend.widgets.ConfigGeneratorScene import ConfigGeneratorScene


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        startScene = "CSV_File"

        ### window property setup ###

        # Sets default main window properties
        self.setWindowTitle("CV Zebrafish")
        self.setMinimumSize(QSize(500, 350))
        self.resize(QSize(1200, 800))

        # Create toolbar
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(toolbar)

        # shortcut to close the window
        QShortcut(QKeySequence("Ctrl+W"), self, activated=self.close)

        # ===================================================================
        ### adds scenes ###

        # QStackedWidget to hold scenes
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        # initializes scenes
        self.scenes = {
            "CSV_File": CSVInputScene(),
            "JSON_File": JSONInputScene(),
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

        # calculation signal handler
        self.scenes["Calculation"].data_generated.connect(self.handle_data)

    def handle_config(self, config):
        print("Config generated.")
        self.scenes["Calculation"].set_config(config)

    def handle_data(self, data):
        print("Data received in MainWindow")
        self.scenes["Graphs"].set_data(data)
        self.stack.setCurrentWidget(self.scenes["Graphs"])
