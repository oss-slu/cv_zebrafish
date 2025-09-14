from PyQt5.QtWidgets import QMainWindow
from PyQt5.QtCore import QSize, Qt

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Sets default main window properties
        self.setWindowTitle("CV Zebrafish")
        self.setFixedSize(QSize(800, 600))
        