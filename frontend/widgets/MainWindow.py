from PyQt5.QtWidgets import QMainWindow, QToolBar, QAction, QStackedWidget, QShortcut
from PyQt5.QtCore import QSize
from PyQt5.QtGui import QKeySequence

from widgets.SampleScenes import SampleScene1, SampleScene2


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        ### window property setup ###

        # Sets default main window properties
        self.setWindowTitle("CV Zebrafish")
        self.setFixedSize(QSize(800, 600))
        self.setMinimumSize(QSize(400, 400))
        self.setMaximumSize(QSize(800, 600))

        # Create toolbar
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(toolbar)

        QShortcut(QKeySequence("Ctrl+W"), self, activated=self.close)


        ### adds scenes ###

        # QStackedWidget to hold scenes
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        # initializes scenes
        self.scenes = {
            "Input": SampleScene1(),
            "View": SampleScene2(),
        }

        # Add scenes to stack
        for scene in self.scenes.values():
            self.stack.addWidget(scene)

        # Toolbar buttons
        for name, scene in self.scenes.items():
            action = QAction(name, self)
            action.triggered.connect(lambda checked, s=scene: self.stack.setCurrentWidget(s))
            toolbar.addAction(action)

        # Show first scene
        self.stack.setCurrentWidget(self.scenes["Input"])

        ### signal handlers ###

        # connects text field in scene 1 to label in scene 2
        self.scenes["Input"].input_field.textChanged.connect(self.scenes["View"].update_label)