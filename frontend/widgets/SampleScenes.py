from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QLineEdit
from PyQt5.QtCore import pyqtSlot

class SampleScene1(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        layout.addWidget(QLabel("This is Scene One"))
        
        self.label = QLabel("Enter text (updates Scene 2 live):")
        self.input_field = QLineEdit("hi there! this live text is viewable in the View scene. click the View button above to see.")

        layout.addWidget(self.label)
        layout.addWidget(self.input_field)
        self.setLayout(layout)

class SampleScene2(QWidget):
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()
        self.label = QLabel("This is Scene Two")
        layout.addWidget(self.label)
        self.setLayout(layout)
    
    @pyqtSlot(str)
    def update_label(self, message):
        self.label.setText(message)
