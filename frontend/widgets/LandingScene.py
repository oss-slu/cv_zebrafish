from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QPalette, QColor, QFont

class LandingScene(QWidget):
    """
    Landing scene widget showing zebrafish research workflow steps.
    """

    step_clicked = pyqtSignal(str)  # emitted when user clicks a step

    def __init__(self):
        super().__init__()

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
        header.setStyleSheet("color: #1B3A57;")
        topLayout.addWidget(header)

        iconLabel = QLabel()
        iconPixmap = QPixmap("./public/upload-button.png").scaled(
            160, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        iconLabel.setPixmap(iconPixmap)
        iconLabel.setAlignment(Qt.AlignHCenter)
        topLayout.addWidget(iconLabel)

        wrapperLayout.addLayout(topLayout, stretch=3)

        # Bottom half (Progress widgets)
        bottomLayout = QHBoxLayout()
        bottomLayout.setAlignment(Qt.AlignCenter)
        bottomLayout.setSpacing(25)

        self.steps = {
            "CSV_File": "Load CSV File",
            "JSON_File": "Load JSON File",
            "Config": "Generate Config",
            "Calculation": "Run Calculations",
            "Graphs": "View Graphs"
        }

        for name, label in self.steps.items():
            widget = ProgressWidget(label)
            widget.clicked.connect(lambda _, s=name: self.step_clicked.emit(s))
            self.steps[name] = widget
            bottomLayout.addWidget(widget)

        wrapperLayout.addLayout(bottomLayout, stretch=2)

        # Footer
        footer = QLabel("Created by Finn, Nilesh, and Jacob")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #FFF; font-size: 10px; margin-top: 15px;")
        wrapperLayout.addWidget(footer)

        # Apply layout
        self.setLayout(wrapperLayout)

        # Subtle gradient background
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(
                    spread:pad, x1:0, y1:0, x2:1, y2:1,
                    stop:0 #999, stop:1 #333
                );
            }
        """)
        
        self.setAutoFillBackground(True)

    def setCompleted(self, step_name: str, completed: bool = True):
        """
        Update step completion status.
        """
        if step_name in self.steps:
            self.steps[step_name].setCompleted(completed)

class ProgressWidget(QWidget):
    """
    Widget to show progress of a step in the workflow.
    """

    clicked = pyqtSignal()  # signal for clicking on widget

    def __init__(self, step_name: str):
        super().__init__()
        self.completed = False

        self.setFixedSize(160, 120)
        self.setAutoFillBackground(True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)

        # Main layout
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        self.titleLabel = QLabel(step_name)
        self.titleLabel.setAlignment(Qt.AlignCenter)
        self.titleLabel.setWordWrap(True)
        self.titleLabel.setFont(QFont("Arial", 11, QFont.Bold))

        self.checkIcon = QLabel()
        checkPixmap = QPixmap("./public/greencheck.png").scaled(
            32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.checkIcon.setPixmap(checkPixmap)
        self.checkIcon.setAlignment(Qt.AlignTop | Qt.AlignRight)
        self.checkIcon.setVisible(False)

        self.progressLabel = QLabel("In Progress")
        self.progressLabel.setAlignment(Qt.AlignCenter)
        self.progressLabel.setStyleSheet("font-size: 10pt; color: #555;")

        layout.addWidget(self.checkIcon)
        layout.addStretch()
        layout.addWidget(self.titleLabel)
        layout.addWidget(self.progressLabel)
        layout.addStretch()

        self.setLayout(layout)

        # Shadow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)

        # Default appearance
        self.updateStyle()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def setCompleted(self, completed: bool):
        self.completed = completed
        self.updateStyle()

    def updateStyle(self):
        # Set base appearance
        if self.completed:
            bg_color = "#B9F6CA"  # light green
            border_color = "#43A047"
            text_color = "#2E7D32"
            self.checkIcon.setVisible(True)
            self.progressLabel.setText("Completed")
        else:
            bg_color = "#E0E0E0"
            border_color = "#BDBDBD"
            text_color = "#333"
            self.checkIcon.setVisible(False)
            self.progressLabel.setText("In Progress")

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {bg_color};
                border-radius: 12px;
                border: 2px solid {border_color};
            }}
            QWidget:hover {{
                background-color: #F0F0F0;
                border: 2px solid #90CAF9;
            }}
        """)

        # Apply text color separately (so it doesn't change on hover)
        self.titleLabel.setStyleSheet(f"color: {text_color}; font-weight: bold;")
