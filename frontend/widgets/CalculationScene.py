import json
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QFileDialog
from PyQt5.QtCore import pyqtSignal, Qt, QSize

import calculations.utils.Driver as calculations
import calculations.utils.Parser as parser

from os import getcwd


class CalculationScene(QWidget):
    data_generated = pyqtSignal(object)  # Signal to emit calculation results

    def __init__(self):
        super().__init__()

        self.csv_path = None
        self.config = None
        self.previous_settings = {"csv_path": None, "config": None}

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
        self.calc_button.clicked.connect(self.calculate)
        layout.addWidget(self.calc_button)

        # adds toggle to switch between using default config or test config
        layout.addWidget(QLabel("Toggle to use test config"),
                         alignment=Qt.AlignCenter)
        self.toggle_button = QPushButton()
        self.toggle_button.setCheckable(True)
        self.toggle_button.setIconSize(QSize(40, 40))
        self.toggle_button.setToolTip("Use Default Config")
        self.toggle_button.clicked.connect(self.toggle_test)
        layout.addWidget(self.toggle_button, alignment=Qt.AlignCenter)

        self.setLayout(layout)

        # buttons to select csv file to be used for calculation
        self.csv_button = QPushButton("Select CSV File")
        self.csv_button.clicked.connect(self.select_csv)
        layout.addWidget(self.csv_button)

        # smae for json config file
        self.config_button = QPushButton("Select Config File (JSON)")
        self.config_button.clicked.connect(self.select_config)
        layout.addWidget(self.config_button)

    def select_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select CSV File", getcwd(), "CSV Files (*.csv)")
        if path:
            self.set_csv_path(path)

    def select_config(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Config File", getcwd(), "JSON Files (*.json)")
        if path:
            self.set_config(path)

    def toggle_test(self):
        if self.toggle_button.isChecked():
            self.toggle_button.setToolTip("Using Test Config")

            # Set to test config and CSV paths
            self.set_config(
                f"{getcwd()}/data_schema_validation/sample_inputs/jsons/BaseConfig.json", update_info=False)
            self.set_csv_path(
                f"{getcwd()}/data_schema_validation/sample_inputs/csv/correct_format.csv")
        else:
            self.toggle_button.setToolTip("Use Default Config")
            self.set_config(self.previous_settings["config"])
            self.set_csv_path(self.previous_settings["csv_path"])

    def set_csv_path(self, path, update_info=True):
        self.previous_settings["csv_path"] = self.csv_path
        self.csv_path = path

        if update_info:
            self.update_info()

    def set_config(self, config, update_info=True):
        self.previous_settings["config"] = self.config
        self.config = config

        if update_info:
            self.update_info()

    def update_info(self):
        if self.csv_path and self.config:
            self.info_label.setText(
                f"CSV: {self.csv_path}\nConfig: {self.config}")

            self.calc_button.setText("Run Calculation")
            self.calc_button.setEnabled(True)
            self.calc_button.setStyleSheet("")  # reset to default style
        elif self.csv_path:
            self.info_label.setText(
                f"CSV: {self.csv_path}\nConfig: Not loaded")
        elif self.config:
            self.info_label.setText(f"CSV: Not loaded\nConfig: {self.config}")
        else:
            self.info_label.setText("No CSV or Config loaded.")

    def calculate(self):
        # Placeholder for the actual calculation logic
        print("Running calculations...")

        config = json.load(open(self.config, 'r'))
        parsed_points = parser.parse_dlc_csv(self.csv_path, config)

        self.info_label.setText(
            f"CSV parsed successfully, running calculations...")

        results = calculations.run_calculations(parsed_points, config)

        if results is None:
            print("Calculations failed.")
            self.info_label.setText(f"Calculation failed")
            self.data_generated.emit(None)
        else:
            print("Calculations completed successfully.")
            self.info_label.setText(f"Calculation successful")

            # Emit the results to signal the main window to start creating the graphs.
            self.data_generated.emit(results)
