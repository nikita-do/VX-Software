from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import pyqtSignal

import serial
import serial.tools.list_ports

# Import the UI class from the 'setting_page_ui' module
from setting_page_ui import Ui_Form

from SerialHandler import SerialHandler

class SettingPage(QWidget):
    '''
        Setting Page Class
    '''

    # Global Signals Definition
    serialConectedSignal = pyqtSignal(bool)

    def __init__(self):
        super().__init__()

        # Initialize the UI from the generated 'main_ui' class
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        
        # Initialize Serial configuration
        self.ui.pushButton_Refresh.setIcon(QIcon("./icon/refresh.svg"))
        self.serialPortInfoListBox = self.ui.comboBox_Port
        self.serialPortBaudListBox = self.ui.comboBox_Baud
        self.currSerialPort = serial.Serial()
        self.ports = serial.tools.list_ports.comports()
        self.isSerialConnected = False

        self.ui.label_DeviceInfor.setWordWrap(True)

        self.fillPortsInfo()

        self.serialHandler = SerialHandler(self.currSerialPort.port, self.currSerialPort.baudrate)

        # Initialization functions
        self.init_signal_slot()

    # Initialize Signal-Slot ---------------------------------------------------------------------#
    def init_signal_slot(self):
        # Connect signals and slots for menu button and side menu
        self.ui.pushButton_Connect.clicked.connect(self.pushButton_Connect_Clicked_Cb)
        self.ui.pushButton_Refresh.clicked.connect(self.fillPortsInfo)
        self.serialPortInfoListBox.currentIndexChanged.connect(self.displayPortInfo)

    # Callback functions -------------------------------------------------------------------------#
    def pushButton_Connect_Clicked_Cb(self):
        '''
            Callback function on Connect Button Clicked event
        '''
        if self.isSerialConnected is False:
            self.openComPort()
        else:
            self.closeComPort()

        return None

    # Serial Communication Utility Functions -----------------------------------------------------#
    def fillPortsInfo(self):
        '''
            Function to fill the available ports information into listbox
        '''
        self.serialPortInfoListBox.clear()
        
        # List all available ports
        self.ports = serial.tools.list_ports.comports()

        # Add available ports in to listbox
        for port in self.ports:
            self.serialPortInfoListBox.addItem(port.name)

        # Set Current Port to the last port
        self.serialPortInfoListBox.setCurrentIndex(len(self.ports) - 1)
        # Display the current selected port information to the Device Information
        self.displayPortInfo()

        return None

    
    def displayPortInfo(self):
        ''' 
            Function to display the Current Port Information
        '''
        blankString = "N/A"

        port = self.ports[self.serialPortInfoListBox.currentIndex()]

        description = port.description if port.description else blankString
        manufacturer = port.manufacturer if port.manufacturer else blankString
        serialNumber = port.serial_number if port.serial_number else blankString
        systemLocation = port.device if port.device else blankString
        vendorId = f"{port.vid:04X}" if port.vid else blankString
        productId = f"{port.pid:04X}" if port.pid else blankString

        listItem = f"{port.name}\n" \
                    f"Description: {description}\n" \
                    f"Manufacturer: {manufacturer}\n" \
                    f"Serial Number: {serialNumber}\n" \
                    f"System Location: {systemLocation}\n" \
                    f"Vendor ID: {vendorId}\n" \
                    f"Product ID: {productId}"
        
        self.ui.label_DeviceInfor.setText(listItem)

        return None
    
    def openComPort(self):
        '''
            Function to Open and Start Serial COM Port reading thread
        '''
        port = self.ports[self.serialPortInfoListBox.currentIndex()]

        self.currSerialPort.port = port.name
        self.currSerialPort.baudrate = int(self.serialPortBaudListBox.currentText())
        self.currSerialPort.bytesize = serial.EIGHTBITS
        self.currSerialPort.parity = serial.PARITY_NONE
        self.currSerialPort.stopbits = serial.STOPBITS_ONE
        self.currSerialPort.timeout = 1
        self.currSerialPort.xonxoff = False
        self.currSerialPort.rtscts = False
        self.currSerialPort.dsrdtr = False

        # Start Serial Port reading thread
        self.serialHandler.update_port(self.currSerialPort.port, self.currSerialPort.baudrate)

        result = self.serialHandler.be_ready()
        if result is True:
            self.serialHandler.start()
            self.serialHandler.serial_port.flush()

            # Emit Connected Signal
            self.isSerialConnected = True
            self.serialHandler.write("connect\n".encode())
        else:
            print("Error open serial port: {}".format(str(result)))
            self.ui.label_DeviceInfor.setText("Error open serial port: {}".format(str(result)))

        return None

    def closeComPort(self):
        '''
            Function to Close the COM Port        
        '''
        self.serialHandler.stop()

        self.ui.pushButton_Connect.setText("Connect")

        self.isSerialConnected = False
        self.serialConectedSignal.emit(self.isSerialConnected)

        return None




