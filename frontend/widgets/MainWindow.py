from PyQt5.QtWidgets import QMainWindow, QToolBar, QAction, QStackedWidget, QShortcut
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QKeySequence

from widgets.SampleScenes import SampleScene2
from widgets.CSVInputScene import CSVInputScene
from widgets.ConfigScene import ConfigScene
from widgets.CSVInputScene import CSVInputScene
from widgets.GraphViewerScene import GraphViewerScene 

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        startScene = "File"

        ### window property setup ###

        # Sets default main window properties
        self.setWindowTitle("CV Zebrafish")
        self.setMinimumSize(QSize(400, 400))
        self.setMaximumSize(QSize(800, 600))

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
            "File": CSVInputScene(),
            "Config": ConfigScene(),
            "View": SampleScene2(),
            "Graphs": GraphViewerScene(),
        }

        # Add scenes to stack
        for scene in self.scenes.values():
            self.stack.addWidget(scene)

        # Toolbar buttons
        for name, scene in self.scenes.items():
            action = QAction(name, self)
            action.triggered.connect(lambda checked, s=scene: self.stack.setCurrentWidget(s))
            toolbar.addAction(action)
            
            # sets cursor to hand for valid toolbar actions
            widget = toolbar.widgetForAction(action)
            if widget:
                widget.setCursor(Qt.PointingHandCursor)


        # Show first scene
        self.stack.setCurrentWidget(self.scenes[startScene])

        ### signal handlers ###

        self.scenes["File"].csv_selected.connect(self.handle_csv)
        self.scenes["Config"].config_generated.connect(self.handle_config)

    def handle_csv(self, path):
        print("CSV selected:", path)

    def handle_config(self, config):
        print("Config generated:", config)
