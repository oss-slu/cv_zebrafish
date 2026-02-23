import json
from os import getcwd, path
from pathlib import Path

from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtWidgets import (
    QFileDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QMessageBox,
)

import src.core.calculations.Driver as calculations
import src.core.parsing.Parser as parser

from src.session.session import save_session_to_json

from src.app_platform.paths import sessions_dir, default_sample_config, default_sample_csv


class ConfigSelectionScene(QWidget):
    """
    Scene that allows users to run calculations on zebrafish data.
    Displays saved CSVs/configs from the current session and allows new ones to be added.
    """
    data_generated = pyqtSignal(object)  # emits calculation results

    def __init__(self):
        super().__init__()

        self.current_session = None
        self.csv_path = None
        self.config_path = None
        self.previous_settings = {"csv_path": None, "config_path": None}

        # --- Layout setup ---
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        header = QLabel("Select Configuration")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("font-size: 18pt; font-weight: bold;")
        layout.addWidget(header)

        self.status_label = QLabel("Select a CSV and Config to run calculations.")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # ===============================
        # Session File Tree
        # ===============================
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(["CSV Files", "Configurations"])
        self.file_tree.setColumnCount(2)
        self.file_tree.setColumnWidth(0, 200)
        self.file_tree.setStyleSheet("""
            QTreeWidget {
                background-color: #f9f9f9;
                border: 1px solid #aaa;
                border-radius: 8px;
                color: black;
            }
            QTreeWidget::item:selected {
                background-color: #4CAF50;
                color: black;
            }
        """)
        self.file_tree.itemClicked.connect(self.handle_tree_click)
        layout.addWidget(self.file_tree)

        # ===============================
        # Calculation Button
        # ===============================
        self.calc_button = QPushButton("Run Calculation")
        self.calc_button.setEnabled(False)
        self.calc_button.setStyleSheet("background-color: lightgrey;")
        self.calc_button.clicked.connect(self.calculate)
        layout.addWidget(self.calc_button, alignment=Qt.AlignCenter)

        # Toggle to use test config (default sample CSV + config)
        layout.addWidget(QLabel("Toggle to use test config"), alignment=Qt.AlignCenter)
        self.toggle_button = QPushButton()
        self.toggle_button.setCheckable(True)
        self.toggle_button.setIconSize(QSize(40, 40))
        self.toggle_button.setToolTip("Use Default Config")
        self.toggle_button.clicked.connect(self.toggle_test)
        layout.addWidget(self.toggle_button, alignment=Qt.AlignCenter)

        self.setLayout(layout)

    # ==============================================================
    # Session Integration
    # ==============================================================

    def load_session(self, session):
        """Load a Session object and populate the tree view."""
        self.current_session = session
        print(f"[load_session] Loaded session: {session.name}")
        print(f"[load_session] Session CSVs: {list(session.csvs.keys())}")

        # refresh tree on session updates
        self.current_session.session_updated.connect(self.populate_tree)

        # initial population
        self.populate_tree()

    def populate_tree(self):
        """Populate the QTreeWidget with CSVs and Configs from the session."""
        self.file_tree.clear()

        if not self.current_session:
            print("[populate_tree] No session loaded.")
            return

        print(f"[populate_tree] Populating for session: {self.current_session.name}")
        csvs = self.current_session.getAllCSVs()

        if self.current_session.length() == 0:
            item = QTreeWidgetItem(["(No saved CSVs)", ""])
            item.setDisabled(True)
            self.file_tree.addTopLevelItem(item)
            return
    
        for csv_path, configs in self.current_session.csvs.items():
            print(f"  - CSV: {csv_path}, configs: {list(configs.keys())}")

            csv_name = path.basename(csv_path) or csv_path
            csv_item = QTreeWidgetItem([csv_name, ""])
            csv_item.setData(0, Qt.UserRole, csv_path)

            if not configs:
                placeholder = QTreeWidgetItem(["", "(No configs)"])
                placeholder.setDisabled(True)
                csv_item.addChild(placeholder)
            else:
                for cfg in configs.keys():
                    cfg_name = path.basename(cfg) or cfg
                    cfg_item = QTreeWidgetItem(["", cfg_name])
                    cfg_item.setData(1, Qt.UserRole, cfg)
                    csv_item.addChild(cfg_item)

            self.file_tree.addTopLevelItem(csv_item)
            csv_item.setExpanded(True)

    def handle_tree_click(self, item, column):
        """Handle user clicking a CSV or config in the tree."""
        csv_data = item.data(0, Qt.UserRole)
        cfg_data = item.data(1, Qt.UserRole)

        if csv_data and not cfg_data:
            # clicked a CSV node
            self.csv_path = csv_data
            self.config_path = None
            self.status_label.setText(f"Selected CSV: {path.basename(csv_data)}")
        elif cfg_data:
            # clicked a config child node
            self.config_path = cfg_data
            parent = item.parent()
            if parent:
                self.csv_path = parent.data(0, Qt.UserRole)
            self.status_label.setText(
                f"Selected: {path.basename(self.csv_path)} + {path.basename(self.config_path)}"
            )

        """Update button state based on current selections."""
        if self.csv_path and self.config_path:
            self.calc_button.setEnabled(True)
            self.calc_button.setStyleSheet("")
            self.status_label.setText(
                f"Ready: {path.basename(self.csv_path)} + {path.basename(self.config_path)}"
            )
        else:
            self.calc_button.setEnabled(False)
            self.calc_button.setStyleSheet("background-color: lightgrey;")

    def toggle_test(self):
        """Switch between test config (default sample files) and tree selection."""
        if self.toggle_button.isChecked():
            self.toggle_button.setToolTip("Using Test Config")
            self.previous_settings["csv_path"] = self.csv_path
            self.previous_settings["config_path"] = self.config_path
            self.csv_path = str(default_sample_csv())
            self.config_path = str(default_sample_config())
            self.status_label.setText(
                "Using test config: correct_format.csv + BaseConfig.json"
            )
            self.calc_button.setEnabled(True)
            self.calc_button.setStyleSheet("")
        else:
            self.toggle_button.setToolTip("Use Default Config")
            self.csv_path = self.previous_settings["csv_path"]
            self.config_path = self.previous_settings["config_path"]
            if self.csv_path and self.config_path:
                self.status_label.setText(
                    f"Ready: {path.basename(self.csv_path)} + {path.basename(self.config_path)}"
                )
                self.calc_button.setEnabled(True)
                self.calc_button.setStyleSheet("")
            else:
                self.status_label.setText("Select a CSV and Config to run calculations.")
                self.calc_button.setEnabled(False)
                self.calc_button.setStyleSheet("background-color: lightgrey;")

    # ==============================================================
    # Calculation Logic
    # ==============================================================

    def calculate(self):
        """Run the calculation pipeline and emit data_generated with the payload."""
        if not self.csv_path or not self.config_path:
            QMessageBox.warning(
                self, "Missing Files", "Please select both a CSV and Config."
            )
            return

        if self.current_session:
            if self.current_session.checkExists(
                csv_path=self.csv_path, config_path=self.config_path
            ):
                print("CSV + Config pair already in session.")
            else:
                if not self.current_session.checkExists(self.csv_path):
                    self.current_session.addCSV(self.csv_path)
                self.current_session.addConfigToCSV(self.csv_path, self.config_path)
                self.current_session.save()

        with open(self.config_path, "r", encoding="utf-8") as handle:
            config = json.load(handle)
        config["config_path"] = self.config_path

        self.status_label.setText("CSV parsed successfully, running calculations...")

        parsed_points = parser.parse_dlc_csv(self.csv_path, config)
        results = calculations.run_calculations(parsed_points, config)

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
                "parsed_points": parsed_points,
            }
            self.data_generated.emit(payload)