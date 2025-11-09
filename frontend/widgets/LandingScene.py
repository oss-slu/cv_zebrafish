from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QComboBox,
    QPushButton, QGraphicsDropShadowEffect, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QColor, QFont
from os import path, getcwd, listdir

# --- Constants (you can define these later) ---
SESSIONS_DIR = path.join(getcwd(), "sessions")  # folder for JSON sessions/configs

class LandingScene(QWidget):
    """
    Landing scene for CV Zebrafish session startup and workflow selection.
    """
    session_selected = pyqtSignal(str)        # emit chosen session path
    new_config_requested = pyqtSignal()       # trigger config creation
    step_clicked = pyqtSignal(str)            # for later progress step selection

    def __init__(self):
        super().__init__()

        self.selected_config = None

        # Layout setup
        mainLayout = QVBoxLayout()
        mainLayout.setContentsMargins(40, 30, 40, 30)
        mainLayout.setSpacing(20)

        # Header and icon
        header = QLabel("CV Zebrafish")
        header.setAlignment(Qt.AlignHCenter)
        header.setFont(QFont("Arial", 32, QFont.Bold))
        header.setStyleSheet("color: #eee;")

        icon = QLabel()
        fish_path = path.join(getcwd(), "frontend", "public", "fish3.png")
        pix = QPixmap(fish_path).scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        icon.setPixmap(pix if not pix.isNull() else QPixmap(100, 100))
        icon.setAlignment(Qt.AlignCenter)

        mainLayout.addWidget(header)
        mainLayout.addWidget(icon)

        # --- Session selection UI ---
        sessionBox = QVBoxLayout()
        sessionBox.setAlignment(Qt.AlignCenter)

        chooseLabel = QLabel("Start a new session or use an existing one?")
        chooseLabel.setStyleSheet("color: #ddd; font-size: 14pt;")
        chooseLabel.setAlignment(Qt.AlignCenter)
        sessionBox.addWidget(chooseLabel)

        buttonLayout = QHBoxLayout()
        buttonLayout.setSpacing(15)
        newBtn = QPushButton("New Session")
        newBtn.setFixedWidth(160)
        existBtn = QPushButton("Existing Session")
        existBtn.setFixedWidth(160)
        buttonLayout.addWidget(newBtn)
        buttonLayout.addWidget(existBtn)
        sessionBox.addLayout(buttonLayout)
        mainLayout.addLayout(sessionBox)

        # --- Existing session selection ---
        self.dropdownLayout = QVBoxLayout()
        self.dropdownLayout.setAlignment(Qt.AlignCenter)
        self.dropdownLayout.setSpacing(10)
        self.dropdownLayout.setContentsMargins(0, 15, 0, 15)

        self.configDropdown = QComboBox()
        self.configDropdown.setFixedWidth(250)
        self.configDropdown.hide()
        self.dropdownLayout.addWidget(self.configDropdown)

        self.confirmBtn = QPushButton("Load Session")
        self.confirmBtn.setFixedWidth(180)
        self.confirmBtn.hide()
        self.dropdownLayout.addWidget(self.confirmBtn)
        mainLayout.addLayout(self.dropdownLayout)

        # Footer
        footer = QLabel("Created by Finn, Nilesh, and Jacob")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #999; font-size: 10px; margin-top: 15px;")
        mainLayout.addWidget(footer)

        self.setLayout(mainLayout)

        # --- Connect signals ---
        newBtn.clicked.connect(self._start_new_session)
        existBtn.clicked.connect(self._show_existing_sessions)
        self.confirmBtn.clicked.connect(self._load_selected_session)

    # --------------------------
    # Internal behavior
    # --------------------------

    def _start_new_session(self):
        """If no session exists, go directly to config creation."""
        self.new_config_requested.emit()

    def _show_existing_sessions(self):
        """Display dropdown of existing session JSONs."""
        configs = [f for f in listdir(SESSIONS_DIR) if f.endswith(".json")]
        if not configs:
            QMessageBox.information(
                self, "No Sessions Found",
                "No saved sessions were found. Proceeding to Config Creation."
            )
            self.new_config_requested.emit()
            return

        self.configDropdown.clear()
        self.configDropdown.addItems(configs)
        self.configDropdown.show()
        self.confirmBtn.show()

    def _load_selected_session(self):
        """Emit selected config path for loading."""
        selected = self.configDropdown.currentText()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please choose a session first.")
            return

        full_path = path.join(SESSIONS_DIR, selected)
        self.session_selected.emit(full_path)
