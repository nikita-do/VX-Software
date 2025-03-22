from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import pyqtSignal
import random

# Import the UI class from the 'config_page_ui' module
from dashboard_page_ui import Ui_Form

# Define a custom MainWindow class
class DashboardPage(QWidget):
    # Global Signals Definition
    # monitorControlSignal = pyqtSignal(bool)

    def __init__(self):
        super().__init__()

        # Initialize the UI from the generated 'main_ui' class
        self.ui = Ui_Form()
        self.ui.setupUi(self)


        # # Initialization
        # self.init_signal_slot()


    #--------------------- Initialize Signal-Slot
    # def init_signal_slot(self):
    #     # Connect signals and slots for menu button and side menu
    #     self.ui.pushButton_StartMonitor.clicked.connect(self.pushButton_StartMonitor_Clicked_Cb)


