from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtWebEngineWidgets import *
import plotly.graph_objects as go
import numpy as np

import sys

class MainWindow(QMainWindow):

    def __init__(self, *args, **kwargs):
        super(MainWindow,self).__init__(*args, **kwargs)

        self.fig = go.Figure()

        trace_num = 10
        point_num = 4000
        for i in range(trace_num):
            self.fig.add_trace(
                go.Scatter(
                        x = np.linspace(0, 1, point_num),
                        y = np.random.randn(point_num)+(i*5)
                )
            )

        self.fig.update_layout(showlegend=False)

        self.browser = QWebEngineView()
        self.browser.setHtml(self.fig.to_html(include_plotlyjs='cdn'))

        self.setCentralWidget(self.browser)

        self.show()

app = QApplication(sys.argv)
window = MainWindow()

app.exec_()
