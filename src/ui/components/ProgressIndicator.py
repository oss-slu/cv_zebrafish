from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class ProgressIndicator(QWidget):
    """
    A horizontal progress indicator showing workflow steps.
    Shows completed steps with checkmarks, current step highlighted, and future steps grayed out.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Define the workflow steps in order
        self.steps = [
            "Landing",
            "Generate Config",
            "Select Configuration",
            "Calculation",
            "Graphs",
            "Verify"
        ]
        
        self.current_step_index = 0
        self.step_labels = []
        
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the UI components."""
        layout = QHBoxLayout()
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(5)
        
        # Create labels for each step
        for i, step in enumerate(self.steps):
            # Add arrow between steps (except before first step)
            if i > 0:
                arrow = QLabel("→")
                arrow.setAlignment(Qt.AlignCenter)
                arrow.setStyleSheet("color: #999; font-size: 14px;")
                layout.addWidget(arrow)
            
            # Create step label
            step_label = QLabel(step)
            step_label.setAlignment(Qt.AlignCenter)
            font = QFont()
            font.setPointSize(10)
            step_label.setFont(font)
            
            self.step_labels.append(step_label)
            layout.addWidget(step_label)
        
        self.setLayout(layout)
        self._update_styles()
    
    def set_current_step(self, step_name):
        """
        Update the progress indicator to show the current step.
        
        Args:
            step_name (str): The name of the current step (must match one of the step names)
        """
        if step_name in self.steps:
            self.current_step_index = self.steps.index(step_name)
            self._update_styles()
    
    def _update_styles(self):
        """Update the visual styling of all step labels based on their status."""
        for i, label in enumerate(self.step_labels):
            if i < self.current_step_index:
                # Completed step - green with checkmark
                label.setText(f"✓ {self.steps[i]}")
                label.setStyleSheet("""
                    color: #28a745;
                    font-weight: bold;
                    background-color: #d4edda;
                    border: 2px solid #28a745;
                    border-radius: 5px;
                    padding: 5px 10px;
                """)
            elif i == self.current_step_index:
                # Current step - blue/highlighted
                label.setText(f"● {self.steps[i]}")
                label.setStyleSheet("""
                    color: #007bff;
                    font-weight: bold;
                    background-color: #cfe2ff;
                    border: 2px solid #007bff;
                    border-radius: 5px;
                    padding: 5px 10px;
                """)
            else:
                # Future step - grayed out
                label.setText(f"○ {self.steps[i]}")
                label.setStyleSheet("""
                    color: #6c757d;
                    background-color: #e9ecef;
                    border: 2px solid #dee2e6;
                    border-radius: 5px;
                    padding: 5px 10px;
                """)