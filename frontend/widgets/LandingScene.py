from os import path, getcwd, listdir
import json

from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QComboBox,
    QPushButton, QMessageBox, QListWidget, QListWidgetItem, QFrame
)

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QFont


from frontend.widgets.session import getSessionsDir

class LandingScene(QWidget):
    """
    Landing scene for CV Zebrafish session startup and workflow selection.
    Allows users to create new sessions, select existing sessions, view configs,
    and create new configs tied to an existing session.
    """
    session_selected = pyqtSignal(str)        # emit chosen session path
    new_config_requested = pyqtSignal(str)    # emit existing session path for config creation
    create_new_session = pyqtSignal(str)         # start brand-new session

    def __init__(self):
        super().__init__()
        self.current_session_path = None

        # -----------------------------
        # Main layout
        # -----------------------------
        self.mainLayout = QVBoxLayout()
        self.mainLayout.setContentsMargins(40, 30, 40, 30)
        self.mainLayout.setSpacing(20)

        # --- Header and icon ---
        header = QLabel("CV Zebrafish")
        header.setAlignment(Qt.AlignHCenter)
        header.setFont(QFont("Arial", 32, QFont.Bold))
        header.setStyleSheet("color: #eee;")

        icon = QLabel()
        fish_path = path.join(getcwd(), "frontend", "public", "fish3.png")
        pix = QPixmap(fish_path).scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if pix.isNull():
            pix = QPixmap(100, 100)
            pix.fill(Qt.gray)
        icon.setPixmap(pix)
        icon.setAlignment(Qt.AlignCenter)

        self.mainLayout.addWidget(header)
        self.mainLayout.addWidget(icon)

        # -----------------------------
        # Sub-widgets (switchable sections)
        # -----------------------------
        self.startWidget = self._build_start_widget()
        self.sessionWidget = self._build_session_select_widget()
        self.configListWidget = self._build_config_list_widget()
        self.newSessionWidget = self._build_new_session_widget()

        # Initially show only the start widget
        self.mainLayout.addWidget(self.startWidget)
        self.mainLayout.addWidget(self.sessionWidget)
        self.mainLayout.addWidget(self.newSessionWidget)
        self.mainLayout.addWidget(self.configListWidget)
        self.sessionWidget.hide()
        self.configListWidget.hide()
        self.newSessionWidget.hide()

        # Footer
        footer = QLabel("Created by Finn, Nilesh, and Jacob")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #999; font-size: 10px; margin-top: 15px;")
        self.mainLayout.addWidget(footer)

        self.setLayout(self.mainLayout)

    # ===============================================================
    # 1. START SCREEN: "New or Existing Session?"
    # ===============================================================
    def _build_start_widget(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)

        prompt = QLabel("Start a new session or open an existing one?")
        prompt.setStyleSheet("color: #ddd; font-size: 14pt;")
        prompt.setAlignment(Qt.AlignCenter)

        btnRow = QHBoxLayout()
        newBtn = QPushButton("New Session")
        existBtn = QPushButton("Existing Session")
        for b in (newBtn, existBtn):
            b.setFixedWidth(160)
            b.setCursor(Qt.PointingHandCursor)
        btnRow.addWidget(newBtn)
        btnRow.addWidget(existBtn)

        layout.addWidget(prompt)
        layout.addLayout(btnRow)

        newBtn.clicked.connect(self._handle_new_session)
        existBtn.clicked.connect(self._show_session_list)

        return w

    # ===============================================================
    # 2. SESSION SELECT SCREEN: choose which saved session JSON to load
    # ===============================================================
    def _build_session_select_widget(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(15)

        self.sessionDropdown = QComboBox()
        self.sessionDropdown.setFixedWidth(300)

        loadBtn = QPushButton("Load Session")
        loadBtn.setFixedWidth(180)

        backBtn = QPushButton("Back")
        backBtn.setFixedWidth(100)

        layout.addWidget(QLabel("Select an existing session:"))
        layout.addWidget(self.sessionDropdown)
        layout.addWidget(loadBtn)
        layout.addWidget(backBtn)

        loadBtn.clicked.connect(self._load_selected_session)
        backBtn.clicked.connect(self._return_to_start)

        return w

    # ===============================================================
    # 3. CONFIG LIST SCREEN: view configs for selected session
    # ===============================================================
    def _build_config_list_widget(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(10)

        self.sessionLabel = QLabel("")
        self.sessionLabel.setAlignment(Qt.AlignCenter)
        self.sessionLabel.setStyleSheet("color: #ccc; font-size: 12pt;")

        self.configList = QListWidget()
        self.configList.setFixedWidth(400)
        self.configList.setStyleSheet("""
            QListWidget {
                background: #2a2a2a;
                color: #eee;
                border-radius: 6px;
                border: 1px solid #444;
            }
            QListWidget::item:selected { background: #4CAF50; color: white; }
        """)

        # Buttons
        btnRow = QHBoxLayout()
        self.newConfigBtn = QPushButton("New Config")
        self.openConfigBtn = QPushButton("Open Config")
        for b in (self.newConfigBtn, self.openConfigBtn):
            b.setFixedWidth(140)
            b.setCursor(Qt.PointingHandCursor)
        btnRow.addWidget(self.newConfigBtn)
        btnRow.addWidget(self.openConfigBtn)

        layout.addWidget(self.sessionLabel)
        layout.addWidget(QLabel("Available Configurations:"))
        layout.addWidget(self.configList)
        layout.addLayout(btnRow)

        self.newConfigBtn.clicked.connect(self._create_new_config)
        self.openConfigBtn.clicked.connect(self._open_selected_config)

        return w
    
    # ===============================================================
    # 4. NEW SESSION SCREEN: create a new session
    # ===============================================================
    def _build_new_session_widget(self):
        """Sub-scene for creating a new session with a name input."""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(15)

        title = QLabel("Create New Session")
        title.setStyleSheet("color: #ddd; font-size: 16pt; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)

        self.newSessionInput = QComboBox()  # if you want autocompletion from existing names, change to QLineEdit if pure text
        from PyQt5.QtWidgets import QLineEdit
        self.newSessionInput = QLineEdit()
        self.newSessionInput.setPlaceholderText("Enter session name...")
        self.newSessionInput.setFixedWidth(300)
        self.newSessionInput.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                font-size: 11pt;
                border-radius: 6px;
                border: 1px solid #666;
                background-color: #2a2a2a;
                color: #fff;
            }
            QLineEdit:focus {
                border: 1px solid #4CAF50;
            }
        """)

        createBtn = QPushButton("Create Session")
        createBtn.setFixedWidth(180)
        createBtn.setCursor(Qt.PointingHandCursor)

        backBtn = QPushButton("Back")
        backBtn.setFixedWidth(100)
        backBtn.setCursor(Qt.PointingHandCursor)

        layout.addWidget(title)
        layout.addWidget(self.newSessionInput)
        layout.addWidget(createBtn)
        layout.addWidget(backBtn)

        # Connect button signals
        createBtn.clicked.connect(self._confirm_new_session)
        backBtn.clicked.connect(self._return_to_start)

        return w

    # ===============================================================
    # --- Internal Handlers ---
    # ===============================================================

    def _handle_new_session(self):
        """Show name input field for creating a new session."""
        self.startWidget.hide()
        self.newSessionWidget.show()

    def _confirm_new_session(self):
        """Validate and emit signal to create new session."""
        name = self.newSessionInput.text().strip()

        session_names = listdir(getSessionsDir())
        if f"{name}.json" in session_names:
            QMessageBox.warning(self, "Name Exists", "A session with this name already exists. Please choose a different name.")
            return
        
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a valid session name.")
            return
        
        self.newSessionWidget.hide()
        self.create_new_session.emit(name)

    def _show_session_list(self):
        """Display dropdown of existing sessions."""
        sessions = [f for f in listdir(getSessionsDir()) if f.endswith(".json")]

        if not sessions:
            QMessageBox.information(
                self, "No Sessions Found",
                "No saved sessions found. Proceeding to Config Creation."
            )
            self.create_new_session.emit()
            return

        self.sessionDropdown.clear()
        self.sessionDropdown.addItems(sessions)

        self.startWidget.hide()
        self.sessionWidget.show()

    def _load_selected_session(self):
        """Load session and show configs inside."""
        selected = self.sessionDropdown.currentText()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please choose a session first.")
            return

        session_path = path.join(getSessionsDir(), selected)
        self.current_session_path = session_path
        self.session_selected.emit(session_path)

        # Try to read the configs in the JSON file
        self._populate_configs(session_path)

        self.sessionWidget.hide()
        self.configListWidget.show()

    def _populate_configs(self, session_path):
        """Read the session JSON to populate available configs."""
        try:
            with open(session_path, "r") as f:
                session_data = json.load(f)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not read session file:\n{e}")
            return

        configs = session_data.get("configs", [])
        self.configList.clear()
        if not configs:
            self.configList.addItem(QListWidgetItem("(No configs found)"))
            self.configList.setEnabled(False)
            self.openConfigBtn.setEnabled(False)
        else:
            for c in configs:
                item = QListWidgetItem(c)
                self.configList.addItem(item)
            self.configList.setEnabled(True)
            self.openConfigBtn.setEnabled(True)

        self.sessionLabel.setText(f"Session: {path.basename(session_path)}")

    def _create_new_config(self):
        """Direct user to config creation, passing the CSV from session JSON."""
        if not self.current_session_path:
            return

        try:
            with open(self.current_session_path, "r") as f:
                data = json.load(f)
            csv_path = data.get("csv_path", None)
        except Exception:
            csv_path = None

        if csv_path:
            self.new_config_requested.emit(csv_path)
        else:
            QMessageBox.warning(self, "Missing CSV", "This session has no CSV path defined.")

    def _open_selected_config(self):
        """Open existing config (emit its path or signal)."""
        item = self.configList.currentItem()
        if not item or "(No configs found)" in item.text():
            return
        config_name = item.text()
        full_config_path = path.join(path.dirname(self.current_session_path), config_name)
        self.session_selected.emit(full_config_path)

    def _return_to_start(self):
        self.sessionWidget.hide()
        self.startWidget.show()