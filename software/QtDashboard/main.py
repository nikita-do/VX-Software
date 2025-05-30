''' Software v0.2.2:
    Amend:
        SAMPLING_RATE correctly default to max value
        Update ECG DSP pipeline: notch 60Hz -> notch 60Hz -> ButterWorth lowpass 40Hz

'''

import os
import sys
import logging  # Add logging module
import json  # Import JSON for parsing incoming data
import base64  # Import base64 for encoding image

from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QWidget
from PyQt6.QtCore import pyqtSlot, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont  # Import QFont for setting font
import pyqtgraph as pg
import numpy as np
import time
from collections import deque
from data_logger import DataLogger
from mqtt_client import MqttClient

from main_window import Ui_MainWindow  # This comes from the .ui converted file
from dashboard import Ui_Form  # This comes from the .ui converted file

from my_filter import highpass_filter, bandpass_filter, apply_notch_filter, wavelet_denoise  # Import filter functions
from pain_assessment import PainAssessor
SAMPLING_RATE = 512  # Sampling rate in Hz (default: 512 Hz)
SAMPLE_BATCH = 512  # Sample batch (default: 512 samples)
MAX_PLOT_LENGTH = 5.5  # Maximum length of the plot in seconds

# HiveMQ Cloud Credentials
BROKER = os.getenv("MQTT_BROKER", "700be638167b43289186dff783367cc3.s1.eu.hivemq.cloud")
PORT = int(os.getenv("MQTT_PORT", 8883))
USERNAME = os.getenv("MQTT_USERNAME", "ngocdo")
PASSWORD = os.getenv("MQTT_PASSWORD", "Ng19102002")
DEVICE_ID = None  # Device ID for MQTT topics
USER_ID = "USER_1"  # User ID for MQTT topics

# MQTT Subscribe Topics
TOPIC_DEVICE_STATUS = None
TOPIC_DEVICE_ATTR_FS = None
TOPIC_DEVICE_ATTR_N = None
TOPIC_DEVICE_DATA = None
TOPIC_DEVICE_RESP_START = None
TOPIC_DEVICE_RESP_RESET = None
TOPIC_USER_CMD_START = f"host/{USER_ID}/commands/start"
TOPIC_USER_CMD_SAVE = f"host/{USER_ID}/commands/save"
TOPIC_USER_CMD_DURATION = f"host/{USER_ID}/commands/record_length"
TOPIC_USER_CMD_RESET = f"host/{USER_ID}/commands/reset"
TOPIC_USER_INFO = f"host/{USER_ID}/user_info"
TOPIC_USER_SCREENSHOT = f"host/{USER_ID}/screenshot"  # Topic for screenshots
TOPIC_USER_RESP_DURATION = f"host/{USER_ID}/responses/record_length"

# MQTT Publish Topics
TOPIC_DEVICE_CMD_START = None
TOPIC_DEVICE_CMD_RESET = None
TOPIC_HOST_STATUS = f"host/status_online"
TOPIC_USER_DEVICE = f"host/{USER_ID}/device"
TOPIC_USER_RESP_START = f"host/{USER_ID}/responses/start"
TOPIC_USER_MSG = f"host/{USER_ID}/message"


class DataProcessingThread(QThread):
    signal_status_msg = pyqtSignal(str)
    signal_prediction = pyqtSignal(int)  # Signal to emit pain prediction results
    # signal_reset_series = pyqtSignal()  # Signal to reset all series values

    def __init__(self, ecg_curve, ppg_curve, gsr_curve, data_logger):
        super().__init__()
        from queue import Queue  # Use thread-safe queue
        self.data_queue = Queue()  # Thread-safe queue for incoming data
        self.running = True
        self.ecg_curve = ecg_curve
        self.ppg_curve = ppg_curve
        self.gsr_curve = gsr_curve
        self.data_logger = data_logger  # Pass the DataLogger instance
        
        self.maxlen = round(SAMPLE_BATCH * MAX_PLOT_LENGTH)  # Maximum length for deque, rounded to the nearest integer
        self.time_series = deque([0], self.maxlen)  # Time series for plotting
        self.ir_series = deque([0], self.maxlen)  # IR channel series
        self.red_series = deque([0], self.maxlen)
        self.ecg_series = deque([0], self.maxlen)  # ECG series
        self.gsr_series = deque([0], self.maxlen)  # GSR series
        self.ppg_series = deque([0], self.maxlen)  # PPG series

        # self.signal_reset_series.emit()  # Emit signal to reset series during initialization
        self.pain_assessor = PainAssessor()

    def add_data(self, data):
        self.data_queue.put(data)  # Thread-safe addition

    def stop(self):
        self.running = False
        self.wait()

    def _pain_prediction(self):
        # region of interest = 5.5 seconds of samples
        roi = int(SAMPLING_RATE * 5.5)
        gsr_list  = list(self.gsr_series)
        ecg_list  = list(self.ecg_series)
        time_list = list(self.time_series)

        # Predict pain level using the PainAssessor
        pain_level = self.pain_assessor.predict_from_raw(ecg_list[-roi:], gsr_list[-roi:], time_list[-roi:])
        # Emit the predicted pain level
        self.signal_prediction.emit(pain_level)
        print(f"[DEBUG] Predicted pain level emitted: {pain_level}")

    def _plot_missing_data(self, time_list):
        # Plot missing data with placeholder values
        time_increment = self.time_series[-1] - self.time_series[-2]
        extended_time = [self.time_series[-1] + (i + 1) * time_increment for i in range(len(time_list))]
        placeholder_data = [0] * len(time_list)

        self.ecg_curve.setData(
            np.concatenate([np.array(self.time_series), np.array(extended_time)]),
            np.concatenate([np.array(self.ecg_series), np.array(placeholder_data)]),
            pen='k'
        )
        self.ppg_curve.setData(
            np.concatenate([np.array(self.time_series), np.array(extended_time)]),
            np.concatenate([np.array(self.ppg_series), np.array(placeholder_data)]),
            pen='k'
        )
        self.gsr_curve.setData(
            np.concatenate([np.array(self.time_series), np.array(extended_time)]),
            np.concatenate([np.array(self.gsr_series), np.array(placeholder_data)]),
            pen='k'
        )

    def _process_valid_data(self, time_list, ir_list, red_list, ecg_list, gsr_list):
        # Compute PPG Avg and apply filters
        ppg_avg_list = [-1 * (ir + red) / 2 for ir, red in zip(ir_list, red_list)]

        filtered_ppg_avg_list = highpass_filter(ppg_avg_list, cutoff=0.5, fs=SAMPLING_RATE)
        filtered_ecg_list = ecg_list
        filtered_ecg_list = apply_notch_filter(filtered_ecg_list, fs=SAMPLING_RATE, notch_freq=60, Q=5)
        filtered_ecg_list = apply_notch_filter(filtered_ecg_list, fs=SAMPLING_RATE, notch_freq=60*2, Q=5)
        filtered_gsr_list = gsr_list
        filtered_gsr_list = apply_notch_filter(filtered_gsr_list, fs=SAMPLING_RATE, notch_freq=60, Q=5)
        filtered_gsr_list = apply_notch_filter(filtered_gsr_list, fs=SAMPLING_RATE, notch_freq=60*2, Q=5)

        # Extend the series with the new data
        self.time_series.extend(time_list)
        self.ir_series.extend(ir_list)
        self.red_series.extend(red_list)
        self.ecg_series.extend(filtered_ecg_list)
        self.gsr_series.extend(filtered_gsr_list)
        self.ppg_series.extend(filtered_ppg_avg_list)

        # Convert time to seconds for plotting
        time_in_ms = np.array(self.time_series) / 1000.0

        # Update plots
        self.ecg_curve.setData(time_in_ms, np.array(self.ecg_series), pen='r')
        self.ppg_curve.setData(time_in_ms, np.array(self.ppg_series), pen='b')
        self.gsr_curve.setData(time_in_ms, np.array(self.gsr_series), pen='m')

        # Predict and log data to csv for every 5.5s length of data
        if len(self.ecg_series) >= self.maxlen:
            # Start prediction Pain Assessor
            self._pain_prediction()

        # Log data to CSV if logging is active
        if self.data_logger.is_logging:
            self.data_logger.write_batch_to_csv(
                time_list, filtered_gsr_list, filtered_ecg_list,
                ir_list, red_list, filtered_ppg_avg_list
            )

    def process_and_plot_data(self, data):
        # Extract sensor data from the JSON message
        time_list = data.get("time", [])
        ir_list = data.get("ir", [])
        red_list = data.get("red", [])
        ecg_list = data.get("ecg", [])
        gsr_list = data.get("gsr", [])

        # Ensure they are lists and have the same length
        if not all(isinstance(lst, list) for lst in [time_list, ir_list, red_list, ecg_list, gsr_list]) or \
           not all(len(lst) == len(time_list) for lst in [ir_list, red_list, ecg_list, gsr_list]):
            self.signal_status_msg.emit("❌ Invalid or mismatched data format.")
            return

        # Check if the first element of the time list is not larger than the last element in the time_series
        if time_list[0] <= self.time_series[-1]:
            self._plot_missing_data(time_list)
            print("❌ Error: Time series is not in ascending order. Data not added.")
        else:
            self._process_valid_data(time_list, ir_list, red_list, ecg_list, gsr_list)

    def run(self):
        while self.running:
            if not self.data_queue.empty():
                data = self.data_queue.get()  # Thread-safe access
                self.process_and_plot_data(data)

class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        os.makedirs("data", exist_ok=True)  # Create the 'data' folder if it doesn't exist
        self.setupUi(self)

        # Initialize DEVICE_ID as None initially
        self.device_id = None

        # Start MQTT thread
        self.mqtt = MqttClient(BROKER, PORT, USERNAME, PASSWORD)
        self.mqtt.signal_receivedPayload.connect(self.handle_mqtt_msg)  # Connect to the signal
        self.mqtt.signal_statusBar_debugMsg.connect(self.show_statusBar_msg)
        self.mqtt.start()

        # Start DataLogger thread
        self.data_logger = DataLogger()
        self.data_logger.signal_statusBar_debugMsg.connect(self.show_statusBar_msg)
        self.data_logger.start()  # Start the DataLogger thread

        self.button_read_start.setEnabled(False)  # Disable button until online
        self.button_read_stop.setEnabled(False)  # Disable button until online
        self.button_read_start.clicked.connect(lambda: self.mqtt.publish_message(TOPIC_DEVICE_CMD_START, "true"))  # Start reading and publishing data
        self.button_read_stop.clicked.connect(lambda: self.mqtt.publish_message(TOPIC_DEVICE_CMD_START, "false"))  # Stop reading and publishing data

        # Connect the button to the save file dialog
        # self.button_save.clicked.connect(self.save_csv_on_toggle)

        # Initialize the hidden dashboard window
        self.dashboard_window = QWidget()
        self.dashboard_ui = Ui_Form()
        self.dashboard_ui.setupUi(self.dashboard_window)
        self._initialize_dashboard_graphs()

        # Set the font size for the text_receivedPayload
        self.text_receivedPayload.setFont(QFont('Arial', 16))  # Set font for the text area

        # Initialize data processing thread
        self.data_thread = DataProcessingThread(self.ecg_curve, self.ppg_curve, self.gsr_curve, self.data_logger)
        self.data_thread.signal_status_msg.connect(self.show_statusBar_msg)
        self.data_thread.start()

        # Connect button_save toggled signal to a slot
        self.button_save_start.setEnabled(False)  # Disable button until online
        self.button_save_stop.setEnabled(False)  # Disable button until online
        self.button_save_start.clicked.connect(self.handle_save_start)
        self.button_save_stop.clicked.connect(self.handle_save_stop)

        # Add permanent widgets to the status bar
        self.elapsed_time = 0
        self.elapsed_time_label = QLabel("elapsed logging time: ...")
        self.statusBar().addPermanentWidget(self.elapsed_time_label)

        # Initialize a single timer for elapsed time updates
        self.elapsed_time_timer = QTimer()
        self.elapsed_time_timer.timeout.connect(self._update_logging_status)

        # Initialize message queue for status messages
        self.message_queue = deque()
        self.message_timer = QTimer()
        self.message_timer.timeout.connect(self._process_message_queue)
        self.message_timer.start(1000)  # Process messages every 1 second

        self.mqtt.publish_message(TOPIC_HOST_STATUS, "true", retain=True)  # Send online status to the device

        # Connect button_waveform to toggle the dashboard visibility
        self.button_waveform.clicked.connect(self._toggle_dashboard_visibility)

        # Initialize save duration
        self.save_duration = 30 # Save duration in seconds
        self.user_info = {}  # Dictionary to store user info
        self.user_info['id'] = 0

        self.read_timer = QTimer()  # Timer to handle auto toggle of read_stop and read_start
        self.read_timer.timeout.connect(self._auto_toggle_read_buttons)
        self.read_elapsed_time = 0  # Track elapsed time since read_start

    def _initialize_dashboard_graphs(self):
        """Initialize graphs in the dashboard window."""
        self.ecg_graph = pg.PlotWidget(labels={'left': 'Amplitude', 'bottom': 'Time [ms]'}, background='w')
        self.dashboard_ui.plotLayout_ecg.addWidget(self.ecg_graph)
        self.ecg_curve = self.ecg_graph.plot()
        self.ecg_graph.showGrid(x=True, y=True)

        self.ppg_graph = pg.PlotWidget(labels={'left': 'Amplitude', 'bottom': 'Time [ms]'}, background='w')
        self.dashboard_ui.plotLayout_ppg.addWidget(self.ppg_graph)
        self.ppg_curve = self.ppg_graph.plot()
        self.ppg_graph.showGrid(x=True, y=True)

        self.gsr_graph = pg.PlotWidget(labels={'left': 'Amplitude', 'bottom': 'Time [ms]'}, background='w')
        self.dashboard_ui.plotLayout_gsr.addWidget(self.gsr_graph)
        self.gsr_curve = self.gsr_graph.plot()
        self.gsr_graph.showGrid(x=True, y=True)

    def _toggle_dashboard_visibility(self):
        """Toggle the visibility of the dashboard window."""
        if self.dashboard_window.isVisible():
            self.dashboard_window.hide()
        else:
            self.dashboard_window.show()
            
    def _update_logging_status(self):
        self.elapsed_time += 1  # Calculate elapsed time in seconds
        self.mqtt.publish_message(f"{TOPIC_USER_MSG}/time_elapsed", str(self.elapsed_time))  # Send elapsed time to the device
        self.elapsed_time_label.setText(f"elapsed logging time: {self.elapsed_time} seconds")
        if self.save_duration is not None and self.elapsed_time >= self.save_duration:
            self.handle_save_stop()

    def _process_message_queue(self):
        if self.message_queue:
            self.message_queue.popleft()

    def _set_online_state(self):
        self.label_status_icon.setText("🟢 Online")
        self.button_read_start.setEnabled(True)
        self.mqtt.publish_message(f"{TOPIC_USER_DEVICE}/status", "true", retain = True)  # Send device online status to the user

    def _set_offline_state(self):
        self.label_status_icon.setText("🔴 Offline")
        self.button_read_start.setEnabled(False)
        self.button_read_stop.setEnabled(False)
        self.button_save_start.setEnabled(False)
        self.button_save_stop.setEnabled(False)
        self.mqtt.publish_message(f"{TOPIC_USER_DEVICE}/status", "false")  # Send device offline status to the user

    def handle_read_start(self):
        self.mqtt.publish_message(TOPIC_USER_RESP_START, "true", retain=True)  
        self.label_read_status.setText("reading...")
        self.button_read_stop.setEnabled(True)  # Enable stop button
        self.button_read_start.setEnabled(False)  # Disable start button
        self.data_thread.__init__(self.ecg_curve, self.ppg_curve, self.gsr_curve, self.data_logger) # Reinitialize the data processing thread
        # Connect the data processing thread to the data logger
        # @TODO: This should be done in the constructor of DataProcessingThread
        self.data_thread.signal_prediction.connect(self.on_prediction_result)
        self.button_save_start.setEnabled(True)  # Enable save button
        self.read_timer.start(1000)  # Check every second

    def handle_read_stop(self):
        self.mqtt.publish_message(TOPIC_USER_RESP_START, "false", retain=True)  
        self.label_read_status.setText("stopped")
        self.button_read_start.setEnabled(True)  # Enable start button
        self.button_read_stop.setEnabled(False)  # Disable stop button
        self.button_save_start.setEnabled(False)
        self.button_save_stop.setEnabled(False)
        # self.data_thread.signal_reset_series.emit()  # Signal to reset all series values
        self.button_save_stop.click()
        self.read_timer.stop()  # Stop the timer
        
    def handle_save_start(self):
        default_filename = os.path.join(
            "data", 
            f"{self.user_info['id']}_{self.save_duration}_{time.strftime('%Y-%m-%d_%H-%M-%S')}.csv"
        )
        print(f"🧾 User Info: {self.user_info}")
        self.data_logger.start_logging(default_filename, self.user_info)  # Start logging to the selected file
        self.elapsed_time_timer.start(1000)  # Start the timer to update elapsed time every second
        self.mqtt.publish_message(f"{TOPIC_USER_MSG}/status", "saving...") # Send saving message to the device
        self.label_save_status.setText("saving...")
        self.button_save_start.setEnabled(False)  # Enable save button
        self.button_save_stop.setEnabled(True)  # Disable stop button

        # if self.save_duration is not None:
        #     QTimer.singleShot(self.save_duration * 1000, self.handle_save_stop)
        
    def handle_save_stop(self):
        self.data_logger.stop_logging()  # Stop logging
        self.elapsed_time_timer.stop()  # Stop the timer
        self.elapsed_time = 0  # Reset elapsed time
        self.label_save_status.setText("stopped")
        self.button_save_start.setEnabled(True)
        self.button_save_stop.setEnabled(False)
        self.mqtt.publish_message(f"{TOPIC_USER_MSG}/status", "stop saving") # Send stop saving msg to the device

    def _auto_toggle_read_buttons(self):
        self.read_elapsed_time += 1
        self.mqtt.publish_message(f"{TOPIC_USER_MSG}/time_elapsed_since_last_restart", str(self.read_elapsed_time))  # Send elapsed time to the device 

        if self.read_elapsed_time % 5 == 0:
            screenshot = self.dashboard_window.grab()  # Capture the screenshot of the dashboard window
            screenshot_path = os.path.join("data", f"screenshot.png")
            screenshot.save(screenshot_path)  # Save the screenshot to a file

            with open(screenshot_path, "rb") as file:
                screenshot_data = file.read()  # Read the screenshot file as binary data
                encoded_data = base64.b64encode(screenshot_data).decode('utf-8')  # Encode to base64

            # Publish the base64-encoded screenshot data over MQTT
            self.mqtt.publish_message(TOPIC_USER_SCREENSHOT, encoded_data)
        """Automatically toggle read_stop and read_start after 300 seconds if no logging is running."""
        if self.read_elapsed_time >= 300 and not self.data_logger.is_logging:
            self.mqtt.publish_message(TOPIC_DEVICE_CMD_START, "false") 
            self.mqtt.publish_message(f"{TOPIC_USER_MSG}/status", "restarting...") # Send stop saving msg to the device
            time.sleep(3)  # Wait for 3 seconds before toggling back
            self.mqtt.publish_message(TOPIC_DEVICE_CMD_START, "true")
            self.read_elapsed_time = 0  # Reset elapsed time
            print("Auto toggled read buttons after 5 minutes.")
            self.mqtt.publish_message(f"{TOPIC_USER_MSG}/status", "reading...") # Send stop saving msg to the device

    # --------------- MQTT Signal Handler ---------------
    @pyqtSlot(str, str)
    def handle_mqtt_msg(self, topic, payload):  # Update the received payload in the UI
        # @TODO: This should be printed to the console for debug, not UI
        # Get current timestamp
        # timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")

        # # Format the log line with timestamp
        # log_line = f"[{timestamp}] Topic: {topic}\nPayload: {payload}\n"

        # # Append to UI
        # self.text_receivedPayload.appendPlainText(log_line)
        # self.text_receivedPayload.verticalScrollBar().setValue(
        #     self.text_receivedPayload.verticalScrollBar().maximum()
        # )
        
        if topic == "device":
            # Receive device_id from the "device" topic
            # self.device_id = payload.strip()  # Update device_id
            self.device_id = 'VX_CEA36A'
            self.label_device_name.setText(self.device_id)  # Update the UI

            # Update MQTT topics dynamically
            global TOPIC_DEVICE_STATUS, TOPIC_DEVICE_DATA, TOPIC_DEVICE_RESP_START, TOPIC_DEVICE_CMD_START, TOPIC_DEVICE_ATTR_FS, TOPIC_DEVICE_ATTR_N, TOPIC_DEVICE_CMD_RESET, TOPIC_DEVICE_RESP_RESET
            TOPIC_DEVICE_STATUS = f"device/{self.device_id}/status_online"
            TOPIC_DEVICE_ATTR_FS = f"device/{self.device_id}/attributes/sampling_rate" 
            TOPIC_DEVICE_ATTR_N = f"device/{self.device_id}/attributes/sample_batch" 
            TOPIC_DEVICE_DATA = f"device/{self.device_id}/data"
            TOPIC_DEVICE_RESP_START = f"device/{self.device_id}/responses/start"
            TOPIC_DEVICE_RESP_RESET = f"device/{self.device_id}/responses/reset"
            TOPIC_DEVICE_CMD_START = f"device/{self.device_id}/commands/start"
            TOPIC_DEVICE_CMD_RESET = f"device/{self.device_id}/commands/reset"

            # Resubscribe to updated topics
            updated_topics = [
                (TOPIC_DEVICE_STATUS, 1),
                (TOPIC_DEVICE_DATA, 2),
                (TOPIC_DEVICE_RESP_START, 1),
                (TOPIC_DEVICE_RESP_RESET, 1),
                (TOPIC_USER_CMD_START, 1),
                (TOPIC_USER_CMD_SAVE, 1),
                (TOPIC_USER_CMD_DURATION, 1),
                (TOPIC_USER_CMD_RESET, 1),
                (TOPIC_USER_RESP_DURATION, 1),
                (f"{TOPIC_USER_INFO}/#", 1),
                (TOPIC_DEVICE_ATTR_FS, 1),
                (TOPIC_DEVICE_ATTR_N, 1),
            ]
            self.mqtt.subscribe_to_topic(updated_topics)
            self.mqtt.update_data_topic(TOPIC_DEVICE_DATA)  # Update the data topic in the MQTT client

            # Notify the user
            self.show_statusBar_msg(f"Device ID updated to: {self.device_id}")
            self.mqtt.publish_message(f"{TOPIC_USER_DEVICE}/name", self.device_id, retain=True)

        elif topic == TOPIC_DEVICE_STATUS:
            if payload.lower() == "true":
                self._set_online_state()
            elif payload.lower() == "false":
                self._set_offline_state()

        elif topic == TOPIC_USER_CMD_DURATION:
            # Handle save duration from the user
            try:
                self.show_statusBar_msg(f"Save duration set to: {payload} seconds")
                self.mqtt.publish_message(TOPIC_USER_RESP_DURATION, payload, qos = 1, retain=True)  # Send response back to the user
                self.save_duration = int(payload)  # Convert payload to integer
                self.label_duration_value.setText(f"{self.save_duration} seconds")
                
            except ValueError:
                self.show_statusBar_msg("❌ Invalid save duration value received")

        elif topic == TOPIC_USER_CMD_START:
            if payload.lower() == "true":
                self.button_read_start.click()  # Trigger read start
            elif payload.lower() == "false":
                self.button_read_stop.click()  # Trigger read start

        elif topic == TOPIC_USER_CMD_SAVE:
            if payload.lower() == "true":
                self.button_save_start.click()
            elif payload.lower() == "false":
                self.button_save_stop.click()
        
        elif topic == TOPIC_USER_CMD_RESET:
            if payload.lower() == "true":
                self.mqtt.publish_message(TOPIC_DEVICE_CMD_RESET, "true", qos = 1)  # Send command to the device

        elif topic == TOPIC_DEVICE_RESP_START:
            if payload.lower() == "true":
                self.handle_read_start()
            elif payload.lower() == "false":
                self.handle_read_stop()
        
        elif topic == TOPIC_DEVICE_RESP_RESET:
            if payload.lower() == "true":
                self.mqtt.publish_message(f"{TOPIC_USER_MSG}/status", "reset WiFi credentials...")

        elif topic == TOPIC_DEVICE_ATTR_FS:
            global SAMPLING_RATE
            SAMPLING_RATE = int(payload)  # Update the sampling rate
            print(f"Sampling rate updated to: {SAMPLING_RATE} Hz")

        elif topic == TOPIC_DEVICE_ATTR_N:
            global SAMPLE_BATCH
            SAMPLE_BATCH = int(payload)  # Update the sampling rate
            print(f"Number of samples per batch updated to: {SAMPLE_BATCH} Hz")

        elif topic == TOPIC_DEVICE_DATA:
            data = json.loads(payload)
            if isinstance(data, dict):  # Ensure it's a dictionary
                self.data_thread.add_data(data)
            else:
                raise ValueError("Received data is not a dictionary")
            # Pass data to the processing thread

        elif topic.startswith(f"{TOPIC_USER_INFO}/"):
            key = topic.split("/")[-1]  # Extract the last part of the topic as the key
            self.user_info[key] = payload  # Store the payload in the user_info dictionary
            print(f"User info updated: {key} = {payload}")  # Log the update

            # Update the corresponding label
            if key == "id":
                self.label_id_value.setText(payload)
            elif key == "age":
                self.label_age_value.setText(payload)
            elif key == "gender":
                self.label_gender_value.setText(payload)
            elif key == "weight":
                self.label_weight_value.setText(payload)
            elif key == "height":
                self.label_height_value.setText(payload)

        else:
            # Handle other topics as needed
            self.show_statusBar_msg(f"Unhandled topic: {topic}")

    @pyqtSlot(str)
    def show_statusBar_msg(self, message):
        logging.info(f"Status Bar Message: {message}")  # Use logging instead of print
        self.message_queue.append(message)  # Add message to the queue
        # Show temporary message in the status bar for 1 second
        self.statusBar().showMessage(message)
        QTimer.singleShot(1000, lambda: self.statusBar().clearMessage())
    
    @pyqtSlot(int)
    def on_prediction_result(self, pain_level):
        """Handle the prediction result from the data processing thread."""

        # Get current timestamp
        timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")

        print('[DEBUG] on_prediction_result called with pain_level:', pain_level)

        if pain_level != None:
            print('Predicted pain level: {}'.format(pain_level))
            self.text_receivedPayload.appendPlainText('[{}] Predicted pain level: {}'.format(timestamp, pain_level))
        else:
            print('Pain level not predictable')
            self.text_receivedPayload.appendPlainText('[{}] Pain level not predictable'.format(timestamp))

        self.text_receivedPayload.verticalScrollBar().setValue(
            self.text_receivedPayload.verticalScrollBar().maximum()
        )

    def closeEvent(self, event):
        """Ensure all resources are cleaned up on close."""
        # Publish the last will message explicitly before closing
        self.mqtt.publish_message(TOPIC_HOST_STATUS, "false", retain=True)
        self.mqtt.publish_message(f"{TOPIC_USER_DEVICE}/status", "false", retain=True)
        self.mqtt.publish_message(TOPIC_DEVICE_CMD_START, "false")
        self.mqtt.publish_message(TOPIC_USER_RESP_START, "false")

        # Stop all threads and timers
        self.data_logger.stop()
        self.data_thread.stop()
        self.mqtt.stop()
        self.elapsed_time_timer.stop()
        self.read_timer.stop()
        self.message_timer.stop()
        self.message_queue.clear()  # Clear any remaining messages

        super().closeEvent(event)

app = QApplication(sys.argv)
window = MainWindow()
window.show()
sys.exit(app.exec())
