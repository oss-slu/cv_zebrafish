from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QFont

from os import listdir, path

from src.app_platform.paths import images_dir, sessions_dir

IMAGES_DIR = images_dir()
sessions_dir = sessions_dir()

print("Sessions directory:", sessions_dir)


class LandingScene(QWidget):
    """
    Landing scene widget showing zebrafish research workflow steps.
    """
    session_selected = pyqtSignal(str)      # load existing session or config
    create_new_session = pyqtSignal(str)    # start brand-new session
    step_clicked = pyqtSignal(str)  # emitted when user clicks a step

    def __init__(self):
        super().__init__()
        self.current_session_path = None

        # Main wrapper layout
        wrapperLayout = QVBoxLayout()
        wrapperLayout.setContentsMargins(40, 30, 40, 30)
        wrapperLayout.setSpacing(20)

        # Top half (Header + Icon)
        topLayout = QVBoxLayout()
        topLayout.setAlignment(Qt.AlignCenter)

        header = QLabel("CV Zebrafish")
        header.setAlignment(Qt.AlignHCenter)
        header.setFont(QFont("Arial", 32, QFont.Bold))
        header.setStyleSheet("color: #eee;")
        topLayout.addWidget(header)

        iconLabel = QLabel()
        fish_path = IMAGES_DIR / "fish3.png"

        pixmap = QPixmap(str(fish_path)).scaled(
            150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        if pixmap.isNull():
            print(f"Warning: could not load image {fish_path}")
            pixmap = QPixmap(100, 100)
            pixmap.fill(Qt.gray)

        iconLabel.setPixmap(pixmap)
        iconLabel.setAlignment(Qt.AlignHCenter)
        topLayout.addWidget(iconLabel)

        wrapperLayout.addLayout(topLayout, stretch=3)

        # -----------------------------
        # Sub-widgets (switchable sections)
        # -----------------------------
        self.startWidget = self._build_start_widget()
        self.sessionWidget = self._build_session_select_widget()
        self.newSessionWidget = self._build_new_session_widget()

        # Initially show only the start widget
        wrapperLayout.addWidget(self.startWidget)
        wrapperLayout.addWidget(self.sessionWidget)
        wrapperLayout.addWidget(self.newSessionWidget)

        self.sessionWidget.hide()
        self.newSessionWidget.hide()
        
        # Footer
        footer = QLabel("Created by Finn, Nilesh, and Jacob")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #FFF; font-size: 10px; margin-top: 15px;")
        wrapperLayout.addWidget(footer)

        # Apply layout
        self.setLayout(wrapperLayout)

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
    
    def _handle_new_session(self):
        """Show name input field for creating a new session."""
        self.startWidget.hide()
        self.newSessionWidget.show()

    def _confirm_new_session(self):
        """Validate and emit signal to create new session."""
        name = self.newSessionInput.text().strip()

        session_names = listdir(sessions_dir())
        if f"{name}.json" in session_names:
            QMessageBox.warning(self, "Name Exists", "A session with this name already exists. Please choose a different name.")
            return
        
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a valid session name.")
            return
        
        self.newSessionWidget.hide()
        self.create_new_session.emit(name)

        self._return_to_start()

    def _show_session_list(self):
        """Display dropdown of existing sessions."""
        sessions = [f for f in listdir(sessions_dir()) if f.endswith(".json")]

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

        session_path = path.join(sessions_dir(), selected)
        self.current_session_path = session_path

        print("Loading session from:", session_path)
        self.session_selected.emit(session_path)

        self._return_to_start()

    def _return_to_start(self):
        self.sessionWidget.hide()
        self.startWidget.show()
        self.newSessionWidget.hide()