from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QFileDialog, QLineEdit
from PyQt5.QtCore import pyqtSignal, Qt, QSize
from PyQt5.QtGui import QIcon

try:
    import utils.calc as calc
except ImportError:
    print("Could not import calculations")

class CalculationScene(QWidget):
    data_generated = pyqtSignal(object)  # Signal to emit calculation results

    def __init__(self):
        super().__init__()

        self.csv_path = None
        self.config = None

        layout = QVBoxLayout()

        self.label = QLabel("Calculation Scene")
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)

        self.info_label = QLabel("No CSV or Config loaded.")
        self.info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.info_label)

        # makes button grey and unclickable until both csv and config are loaded
        self.calc_button = QPushButton("Waiting for CSV and Config")
        self.calc_button.setEnabled(False)
        self.calc_button.setStyleSheet("background-color: lightgrey;")
        self.calc_button.clicked.connect(self.run_calculation)
        layout.addWidget(self.calc_button)

    def set_csv_path(self, path):
        self.csv_path = path
        self.update_info()

    def set_config(self, config):
        self.config = config
        self.update_info()

    def update_info(self):
        if self.csv_path and self.config:
            self.info_label.setText(f"CSV: {self.csv_path}\nConfig: {self.config}")

            self.calc_button.setText("Run Calculation")
            self.calc_button.setEnabled(True)
            self.calc_button.setStyleSheet("")  # reset to default style
        elif self.csv_path:
            self.info_label.setText(f"CSV: {self.csv_path}\nConfig: Not loaded")
        elif self.config:
            self.info_label.setText(f"CSV: Not loaded\nConfig: {self.config}")
        else:
            self.info_label.setText("No CSV or Config loaded.")

    def run_calculation(self):
        # Placeholder for the actual calculation logic
        print("Running calculations...")

        try:
            results = calc.perform_calculations(self.csv_path, self.config)

            self.info_label.setText(f"Calculation successful")
            print("Calculation results:", results)

            # Emit the results to signal the main window to start creating the graphs.
            self.data_generated.emit(results)
        except Exception as e:
            self.info_label.setText(f"Calculation failed: {e}")
            print("Calculation error:", e)


        