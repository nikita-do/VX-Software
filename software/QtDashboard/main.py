#--------------------------------------------------------------------------------------------------
#   Description: Main Window
#   Run bellow commdand for UI Auto generating
#       ./ui_gen.bat
#--------------------------------------------------------------------------------------------------

import sys
import struct
import zlib
from PyQt6.QtWidgets import QMainWindow, QApplication, QLabel, QListWidgetItem, QWidget, QGridLayout, QHBoxLayout
from PyQt6.QtCore import Qt, QSize, QByteArray, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QFont

from enum import Enum
import time

# Import the UI class from the 'main_ui' module
from main_ui import Ui_MainWindow
from dashboard_page import DashboardPage
from config_page import ConfigPage
from setting_page import SettingPage

#--------------------------------------------------------------------------------------------------
#                                       CONSTANT VARIABLES
#--------------------------------------------------------------------------------------------------


#--------------------------------------------------------------------------------------------------
#                                       MAIN WINDOWN CLASS
#--------------------------------------------------------------------------------------------------
class MainWindow(QMainWindow):
    '''
        MainWindow Class
    '''
    # Global Signals Definition
    deviceConnectedSignal = pyqtSignal(bool)

    def __init__(self):
        super().__init__()

        # Global variables
        self.isDeviceConnected = False

        # Initialize the UI from the generated UI classes
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.ConfigPage = ConfigPage()
        self.ui.page_Configuration = self.ConfigPage

        self.SettingPage = SettingPage()
        self.ui.page_Settings = self.SettingPage
        
        self.DashboardPage = DashboardPage()
        self.ui.page_Dashboard = self.DashboardPage

        #------------- Set main window properties
        self.setWindowIcon(QIcon("./icon/Logo.png"))
        self.setWindowTitle("Vital-X Dashboard")

        # Set minimum size (width, height)
        self.setMinimumSize(1280, 720)

        #------------- Initialize UI elements
        self.title_label = self.ui.title_label
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        self.title_label.setFont(font)
        self.title_label.setText("Vital-X Dashboard")

        self.title_icon = self.ui.title_icon
        self.title_icon.setText("")
        self.title_icon.setPixmap(QPixmap("./icon/Logo.png"))
        self.title_icon.setScaledContents(True)

        self.side_menu = self.ui.listWidget
        self.side_menu.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.side_menu_icon_only = self.ui.listWidget_icon_only
        self.side_menu_icon_only.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.side_menu_icon_only.hide()

        self.menu_btn = self.ui.menu_btn
        self.menu_btn.setText("")
        self.menu_btn.setIcon(QIcon("./icon/close.svg"))
        self.menu_btn.setIconSize(QSize(30, 30))
        self.menu_btn.setCheckable(True)
        self.menu_btn.setChecked(False)

        self.main_content = self.ui.stackedWidget

        #------------- Initialize a status bar
        self.status = self.statusBar()

        # Create a QWidget to hold the icon and label
        self.status_widget = QWidget()
        self.status_layout = QHBoxLayout()
        self.status_widget.setLayout(self.status_layout)

        # Create a QLabel for the text
        self.label_ConnectStatus = QLabel("Device not Connected")

        # Create a QLabel for the icon
        self.label_ConnectStatusIcon = QLabel()
        self.label_ConnectStatusIcon.setPixmap(QPixmap("./icon/disconnected_radio_button.svg"))

        # Add the icon and text labels to the self.status_layout
        self.status_layout.addWidget(self.label_ConnectStatus)
        self.status_layout.addWidget(self.label_ConnectStatusIcon)

        # Add spacing between icon and text (optional)
        self.status_layout.setSpacing(5)

        # Add the status widget to the status bar
        self.status.addPermanentWidget(self.status_widget)

        #------------- Define a list of menu items with names and icons
        self.menu_list = [
            {
                "name": "Dashboard",
                "icon": "./icon/dashboard.svg",
                "page": self.ui.page_Dashboard
            },
            {
                "name": "Monitoring",
                "icon": "./icon/reports.svg",
                "page": self.ui.page_Monitoring
            },
            {
                "name": "Control",
                "icon": "./icon/control.svg",
                "page": self.ui.page_Control
            },
            {
                "name": "Configuration",
                "icon": "./icon/configuration.svg",
                "page": self.ui.page_Configuration
            },
            {
                "name": "Settings",
                "icon": "./icon/settings.svg",
                "page": self.ui.page_Settings
            },
            {
                "name": "About",
                "icon": "./icon/about.svg",
                "page": self.ui.page_About
            },
        ]

        #------------- Initialize the UI elements and slots
        self.init_list_widget()
        self.init_stackwidget()
        self.init_signal_slot()

        #------------- Globally Used variables declaration


    def init_list_widget(self):
        # Initialize the side menu and side menu with icons only
        self.side_menu_icon_only.clear()
        self.side_menu.clear()

        for menu in self.menu_list:
            # Set items for the side menu with icons only
            item = QListWidgetItem()
            item.setIcon(QIcon(menu.get("icon")))
            item.setSizeHint(QSize(40, 40))
            self.side_menu_icon_only.addItem(item)
            self.side_menu_icon_only.setCurrentRow(0)

            # Set items for the side menu with icons and text
            item_new = QListWidgetItem()
            item_new.setIcon(QIcon(menu.get("icon")))
            item_new.setText(menu.get("name"))
            self.side_menu.addItem(item_new)
            self.side_menu.setCurrentRow(0)

    def init_stackwidget(self):
        # Initialize the stack widget with content pages
        widget_list = self.main_content.findChildren(QWidget)
        for widget in widget_list:
            self.main_content.removeWidget(widget)

        for menu in self.menu_list:
            page = menu.get("page")
            self.main_content.addWidget(page)

    def button_icon_change(self, status):
        # Change the menu button icon based on its status
        if status:
            self.menu_btn.setIcon(QIcon("./icon/open.svg"))
        else:
            self.menu_btn.setIcon(QIcon("./icon/close.svg"))

    def init_signal_slot(self):
        '''
            Function to Initialize Signal-Slot
        '''
        # Connect signals and slots for menu button and side menu
        self.menu_btn.toggled['bool'].connect(self.side_menu.setHidden)
        self.menu_btn.toggled['bool'].connect(self.title_label.setHidden)
        self.menu_btn.toggled['bool'].connect(self.side_menu_icon_only.setVisible)
        self.menu_btn.toggled['bool'].connect(self.title_icon.setHidden)

        # Connect signals and slots for switching between menu items
        self.side_menu.currentRowChanged['int'].connect(self.main_content.setCurrentIndex)
        self.side_menu_icon_only.currentRowChanged['int'].connect(self.main_content.setCurrentIndex)
        self.side_menu.currentRowChanged['int'].connect(self.side_menu_icon_only.setCurrentRow)
        self.side_menu_icon_only.currentRowChanged['int'].connect(self.side_menu.setCurrentRow)
        self.menu_btn.toggled.connect(self.button_icon_change)

        # self.deviceConnectedSignal.connect(self.onDeviceConnectedSignal)
        # self.SettingPage.serialConectedSignal.connect(self.onDeviceConnectedSignal)
        # self.SettingPage.serialHandler.data_received.connect(self.readSerialData)
        # self.DashboardPage.monitorControlSignal.connect(self.onMonitorControlSignal)
        # self.ConfigPage.bmsConfigSignal.connect(self.onBmsConfigSignal)


#--------------------------------------------------------------------------------------------------
#       MAIN PROGRAM
#--------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    app = QApplication(sys.argv)

    # Load style file
    with open("style.qss") as f:
        style_str = f.read()

    app.setStyleSheet(style_str)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
