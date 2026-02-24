from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class SceneNavigator(QWidget):
    def __init__(self, steps=None, on_back=None, on_forward=None, parent=None):
        super().__init__(parent)

        self.steps = steps or []
        self.current_step_index = 0

        self.on_back = on_back
        self.on_forward = on_forward

        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(10)

        self.back_btn = QPushButton("← Back")
        self.forward_btn = QPushButton("Forward →")

        self.back_btn.clicked.connect(self._handle_back)
        self.forward_btn.clicked.connect(self._handle_forward)

        # Optional small status text (nice when toolbar is hidden / user uses shortcuts)
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(10)
        self.status_label.setFont(font)

        layout.addWidget(self.back_btn, 0, Qt.AlignLeft)
        layout.addWidget(self.status_label, 1, Qt.AlignCenter)
        layout.addWidget(self.forward_btn, 0, Qt.AlignRight)

        self.setLayout(layout)

        # Basic styling similar “chip-ish” vibe to ProgressIndicator
        self.setStyleSheet("""
            QPushButton {
                padding: 6px 12px;
                border-radius: 6px;
                border: 2px solid #dee2e6;
                background: #e9ecef;
                color: #212529;
                font-weight: bold;
            }
            QPushButton:hover:enabled {
                border-color: #007bff;
            }
            QPushButton:disabled {
                color: #6c757d;
                background: #f1f3f5;
                border-color: #dee2e6;
            }
            QLabel {
                color: #6c757d;
            }
        """)

        self._update_state()

    def set_steps(self, steps):
        """Replace the ordered steps list."""
        self.steps = steps or []
        self.current_step_index = 0
        self._update_state()

    def set_current_step(self, step_name):
        """Sync navigator to current scene name."""
        if step_name in self.steps:
            self.current_step_index = self.steps.index(step_name)
        self._update_state()

    def can_go_back(self):
        return self.current_step_index > 0

    def can_go_forward(self):
        return self.current_step_index < (len(self.steps) - 1)

    def set_back_enabled(self, enabled):
        """Override Back button enabled state (e.g. from MainWindow)."""
        self.back_btn.setEnabled(enabled)

    def set_forward_enabled(self, enabled):
        """Override Forward button enabled state (e.g. from MainWindow)."""
        self.forward_btn.setEnabled(enabled)

    def _update_state(self):
        # Button enabled state is set by MainWindow via set_back_enabled/set_forward_enabled
        # Only update status label here
        if not self.steps:
            self.status_label.setText("")
            return

        current = self.steps[self.current_step_index]
        left = self.steps[self.current_step_index - 1] if self.can_go_back() else ""
        right = self.steps[self.current_step_index + 1] if self.can_go_forward() else ""

        if left and right:
            self.status_label.setText(f"{left}  ←  {current}  →  {right}")
        elif left:
            self.status_label.setText(f"{left}  ←  {current}")
        elif right:
            self.status_label.setText(f"{current}  →  {right}")
        else:
            self.status_label.setText(current)

    def _handle_back(self):
        if self.on_back:
            self.on_back()

    def _handle_forward(self):
        if self.on_forward:
            self.on_forward()
