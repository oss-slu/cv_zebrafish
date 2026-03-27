import json
from os import path

from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QMessageBox,
    QApplication,
)

import src.core.calculations.Driver as calculations
import src.core.parsing.Parser as parser

from src.app_platform.paths import default_sample_config, default_sample_csv
from src.app_platform.paths import images_dir

FOLDER_ICON = images_dir() / "folder-black.svg"


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
        # Calculation Button + Toggle (same row, centered)
        # ===============================
        self.calc_button = QPushButton("Run Calculation")
        self.calc_button.setEnabled(False)
        self.calc_button.setStyleSheet("background-color: lightgrey;")
        self.calc_button.clicked.connect(self.calculate)
        self.toggle_button = QPushButton()
        self.toggle_button.setCheckable(True)
        self.toggle_button.setIconSize(QSize(40, 40))
        self.toggle_button.setToolTip("Use Default Config")
        self.toggle_button.clicked.connect(self.toggle_test)
        toggle_label = QLabel("Toggle to use test config")
        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(self.calc_button)
        button_row.addWidget(self.toggle_button)
        button_row.addWidget(toggle_label)
        button_row.addStretch()
        layout.addLayout(button_row)

        # ===============================
        # Progress bar (under button row)
        # ===============================
        progress_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_label = QLabel("")
        progress_row.addWidget(self.progress_bar, stretch=1)
        progress_row.addWidget(self.progress_label)
        layout.addLayout(progress_row)
        self.progress_bar.hide()
        self.progress_label.hide()

        self.setLayout(layout)

    def _update_calc_button_state(self):
        enabled = bool(self.csv_path and self.config_path)
        self.calc_button.setEnabled(enabled)
        self.calc_button.setStyleSheet("" if enabled else "background-color: lightgrey;")

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
            self.set_progress(0, 0, "")
            return

        print(f"[populate_tree] Populating for session: {self.current_session.name}")
        # Show progress while building the tree (large sessions/folders can take time).
        total_items = 0
        try:
            for _csv_path, configs in (self.current_session.csvs or {}).items():
                total_items += 1  # csv node
                total_items += len(list((configs or {}).keys()))  # config children
        except Exception:
            total_items = 0

        if total_items > 0:
            self.set_progress(0, total_items, "Loading session items...")
        if self.current_session.length() == 0:
            item = QTreeWidgetItem(["(No saved CSVs)", ""])
            item.setDisabled(True)
            self.file_tree.addTopLevelItem(item)
            self.set_progress(0, 0, "")
            return
    
        done = 0
        for csv_path, configs in self.current_session.csvs.items():
            print(f"  - CSV: {csv_path}, configs: {list(configs.keys())}")

            is_folder = False
            n_files = 0
            try:
                is_folder = bool(getattr(self.current_session, "is_folder_csv", lambda _p: False)(csv_path))
                if is_folder:
                    files = self.current_session.get_folder_files(csv_path)
                    n_files = len(files)
            except Exception:
                is_folder = False

            if is_folder:
                folder_name = path.basename(csv_path) or csv_path
                csv_name = f"{folder_name} ({n_files} files)"
            else:
                csv_name = path.basename(csv_path) or csv_path
            csv_item = QTreeWidgetItem([csv_name, ""])
            csv_item.setData(0, Qt.UserRole, csv_path)
            if is_folder:
                csv_item.setIcon(0, QIcon(str(FOLDER_ICON)))

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
                    done += 1
                    if total_items > 0:
                        self.set_progress(done, total_items, "Loading session items...")

            self.file_tree.addTopLevelItem(csv_item)
            csv_item.setExpanded(True)
            done += 1
            if total_items > 0:
                self.set_progress(done, total_items, "Loading session items...")

        self.set_progress(0, 0, "")

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
            # Persist last-used pair for session resume.
            try:
                if self.current_session is not None and self.csv_path and self.config_path:
                    self.current_session.last_csv_path = self.csv_path
                    self.current_session.last_config_path = self.config_path
                    self.current_session.save()
            except Exception:
                pass

        if self.csv_path and self.config_path:
            self.status_label.setText(
                f"Ready: {path.basename(self.csv_path)} + {path.basename(self.config_path)}"
            )

        self._update_calc_button_state()

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
            self._update_calc_button_state()
        else:
            self.toggle_button.setToolTip("Use Default Config")
            self.csv_path = self.previous_settings["csv_path"]
            self.config_path = self.previous_settings["config_path"]
            if self.csv_path and self.config_path:
                self.status_label.setText(
                    f"Ready: {path.basename(self.csv_path)} + {path.basename(self.config_path)}"
                )
                self._update_calc_button_state()
            else:
                self.status_label.setText("Select a CSV and Config to run calculations.")
                self._update_calc_button_state()

    def set_progress(self, n, total, graph_name):
        """Update progress bar and label: [N]/[Total] - [Graph Name]. Call with total=0 to hide."""
        if total <= 0:
            self.progress_bar.hide()
            self.progress_label.hide()
            self.progress_bar.setValue(0)
            self.progress_label.setText("")
            return
        self.progress_bar.show()
        self.progress_label.show()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(int(100 * n / total) if total else 0)
        if graph_name == "Loading graphs...":
            self.progress_label.setText("Loading Graphs...")
        else:
            self.progress_label.setText(f"{n}/{total} - {graph_name}")
        QApplication.processEvents()

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
            # Persist last-used pair for session resume.
            try:
                self.current_session.last_csv_path = self.csv_path
                self.current_session.last_config_path = self.config_path
            except Exception:
                pass
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

        # If this CSV is a folder, emit a folder payload and let MainWindow orchestrate
        # running calculations across all files with aggregated progress.
        try:
            if self.current_session is not None and self.current_session.is_folder_csv(self.csv_path):
                files = self.current_session.get_folder_files(self.csv_path)
                if not files:
                    QMessageBox.warning(self, "Empty Folder", "This folder has no CSV files recorded in the session.")
                    return
                payload = {
                    "csv_folder": self.csv_path,
                    "csv_files": files,
                    "config": config,
                    "config_path": self.config_path,
                }
                self.data_generated.emit(payload)
                return
        except Exception:
            pass

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