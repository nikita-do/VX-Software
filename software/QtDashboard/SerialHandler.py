import serial
import time
from PyQt6.QtCore import QThread, pyqtSignal

class SerialHandler(QThread):
    data_received = pyqtSignal(bytes)

    def __init__(self, port_name, baud_rate):
        super().__init__()
        self.port_name = port_name
        self.baud_rate = baud_rate
        self.serial_port = serial.Serial()

        self.running = True

    def update_port(self, port_name, baud_rate):
        self.port_name = port_name
        self.baud_rate = baud_rate

    def be_ready(self):
        try:
            self.serial_port = serial.Serial(self.port_name, self.baud_rate, timeout=None)
            if self.serial_port.is_open:
                self.running = True
                return True
        except serial.SerialException as err:
            return err

    def write(self, data):
        self.serial_port.write(data)

    def run(self):
        try:
            while self.running:
                if self.serial_port.in_waiting > 0:
                    data = self.serial_port.read_all()
                    
                    self.data_received.emit(data)
                    
        except serial.SerialException as e:
            print(f"Serial error: {e}")
        finally:
            if self.serial_port.is_open:
                self.serial_port.close()

    def stop(self):
        self.running = False
        self.serial_port.close()
