from PyQt5.QtWidgets import QFrame


def horizontal_separator() -> QFrame:
    line = QFrame()
    line.setObjectName("ChromeSeparator")
    line.setFrameShape(QFrame.NoFrame)
    line.setFixedHeight(1)
    return line
