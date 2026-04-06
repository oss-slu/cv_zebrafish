from pathlib import Path
import sys

from PyQt5.QtWidgets import QApplication

SRC_ROOT = Path(__file__).resolve().parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ui.main_window_shell import MainShellWindow

app = QApplication(sys.argv)
window = MainShellWindow()
window.show()
app.exec()
