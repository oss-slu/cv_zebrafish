import json
from os import path
from pathlib import Path

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFileDialog,
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QMessageBox
)

from core.calculations.Driver import run_calculations
from core.parsing.Parser import parse_dlc_csv
from app_platform.paths import default_sample_config, default_sample_csv


class CalculationScene(QWidget):
    data_generated = pyqtSignal(object)  # Signal to emit calculation results

    def __init__(self):
        super().__init__()

        self.default_config = default_sample_config()
        self.default_csv = default_sample_csv()
        self.csv_path = None
        self.config = None
        self.previous_settings = {"csv_path": None, "config": None}
        self.current_session = None

        layout = QVBoxLayout()
        layout.setSpacing(16)

        self.label = QLabel("Calculation Scene")
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)

        self.status_label = QLabel("No CSV or Config loaded.")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Panel to keep selected file paths tidy
        self.files_panel = QFrame()
        self.files_panel.setFrameShape(QFrame.StyledPanel)
        self.files_panel.setObjectName("filesPanel")
        self.files_panel.setStyleSheet(
            "#filesPanel, #filesPanel > * {"
            "border: 1px solid #d0d0d0;"
            "border-radius: 8px;"
            "background-color: #f5f6fa;"
            "}"
        )

        panel_layout = QVBoxLayout(self.files_panel)
        panel_layout.setContentsMargins(12, 12, 12, 12)
        panel_layout.setSpacing(8)

        panel_header = QLabel("Selected Files")
        panel_header.setStyleSheet("font-weight: 600; color: #333;")
        panel_layout.addWidget(panel_header)

        csv_header = QLabel("CSV File")
        csv_header.setStyleSheet("font-weight: 500; color: #555;")
        panel_layout.addWidget(csv_header)

        self.csv_value_label = QLabel("No CSV selected")
        self.csv_value_label.setWordWrap(True)
        self.csv_value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.csv_value_label.setStyleSheet("color: #333;")
        panel_layout.addWidget(self.csv_value_label)

        config_header = QLabel("Config File")
        config_header.setStyleSheet("font-weight: 500; color: #555;")
        panel_layout.addWidget(config_header)

        self.config_value_label = QLabel("No config selected")
        self.config_value_label.setWordWrap(True)
        self.config_value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.config_value_label.setStyleSheet("color: #333;")
        panel_layout.addWidget(self.config_value_label)

        layout.addWidget(self.files_panel)

        # makes button grey and unclickable until both csv and config are loaded
        self.calc_button = QPushButton("Waiting for CSV and Config")
        self.calc_button.setEnabled(False)
        self.calc_button.setStyleSheet("background-color: lightgrey;")
        self.calc_button.clicked.connect(self.calculate)
        layout.addWidget(self.calc_button)

        # adds toggle to switch between using default config or test config
        layout.addWidget(QLabel("Toggle to use test config"), alignment=Qt.AlignCenter)
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

        # same for json config file
        self.config_button = QPushButton("Select Config File (JSON)")
        self.config_button.clicked.connect(self.select_config)
        layout.addWidget(self.config_button)

    def select_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select CSV File", str(Path.cwd()), "CSV Files (*.csv)"
        )
        if path:
            self.set_csv_path(path)

    def select_config(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Config File", str(Path.cwd()), "JSON Files (*.json)"
        )
        if path:
            self.set_config(path)

    def toggle_test(self):
        if self.toggle_button.isChecked():
            self.toggle_button.setToolTip("Using Test Config")

            # Set to test config and CSV paths
            self.set_config(
                str(self.default_config),
                update_info=False,
            )
            self.set_csv_path(
                str(self.default_csv)
            )
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
        self.csv_value_label.setText(self.csv_path or "No CSV selected")
        self.config_value_label.setText(self.config or "No config selected")

        if self.csv_path and self.config:
            self.status_label.setText("Ready to run calculations.")
            self.calc_button.setText("Run Calculation")
            self.calc_button.setEnabled(True)
            self.calc_button.setStyleSheet("")
        else:
            if self.csv_path:
                self.status_label.setText(
                    "CSV selected. Choose a config file to continue."
                )
            elif self.config:
                self.status_label.setText(
                    "Config selected. Choose a CSV file to continue."
                )
            else:
                self.status_label.setText("No CSV or Config loaded.")

            self.calc_button.setText("Waiting for CSV and Config")
            self.calc_button.setEnabled(False)
            self.calc_button.setStyleSheet("background-color: lightgrey;")

    def calculate(self):
        print("Running calculations...")

        # makes sure the files are there. this is redundant but just in case
        if not self.csv_path or not self.config:
            QMessageBox.warning(self, "Missing Files", "Please select both a CSV and Config.")
            return
        
        if self.current_session:
            # adds csv and config to session after checking if the pair doesn't already exist
            if self.current_session.checkExists(self.csv_path, self.config):
                print("CSV + Config pair already in session, not adding.")
            else:
                # adds csv to session after checking if it already exists
                if self.current_session.checkExists(self.csv_path):
                    print("CSV already in session, not adding.")
                else:
                    self.current_session.addCSV(self.csv_path)

                # config will still need to be added, since the pair wasn't found in the session
                self.current_session.addConfigToCSV(self.csv_path, self.config)
                self.current_session.save()

        with open(self.config, "r", encoding="utf-8") as handle:
            config = json.load(handle)
        parsed_points = parse_dlc_csv(self.csv_path, config)

        self.status_label.setText("CSV parsed successfully, running calculations...")

        results = run_calculations(parsed_points, config)

        if results is None:
            print("Calculations failed.")
            self.status_label.setText("Calculation failed.")
            self.data_generated.emit(None)
        else:
            print("Calculations completed successfully.")
            self.status_label.setText("Calculation successful.")

            payload = {
                "results_df": results,
                "config": config,
                "csv_path": self.csv_path,
            }

            # Emit the results to signal the main window to start creating the graphs.
            self.data_generated.emit(payload)

    def load_session(self, session):
        print("Loading session into CalculationScene.")
        self.current_ession = session
