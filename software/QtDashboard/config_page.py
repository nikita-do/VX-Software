from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import pyqtSignal

# Import the UI class from the 'config_page_ui' module
from config_page_ui import Ui_Form

# Define a custom MainWindow class
class ConfigPage(QWidget):
    # Global Signals Definition
    bmsConfigSignal = pyqtSignal(bool)

    def __init__(self):
        super().__init__()

        # Initialize the UI from the generated 'main_ui' class
        self.ui = Ui_Form()
        self.ui.setupUi(self)

        #------------- Globally Used variables declaration
        self.CommandQueue = dict()


        #------------- Initialization
        # self.init_signal_slot()

        
    #--------------------- Initialize Signal-Slot
    # def init_signal_slot(self):
    #     # Connect signals and slots for menu button and side menu
    #     self.ui.pushButton_LoadConfig.clicked.connect(self.pushButton_LoadConfig_Clicked_Cb)
    #     self.ui.pushButton_ApplyCellsFetsSettings.clicked.connect(self.pushButton_ApplyCellsFetsSettings_Clicked_Cb)
    #     self.ui.pushButton_ApplyProtectionA.clicked.connect(self.pushButton_ApplyProtectionA_Clicked_Cb)



    #--------------------- Callback Functions
