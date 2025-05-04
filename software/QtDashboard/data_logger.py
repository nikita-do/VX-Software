import csv
import os
import pandas as pd

from PyQt6.QtCore import pyqtSignal, QThread, QMutex, QWaitCondition

class DataLogger(QThread):
    signal_statusBar_debugMsg = pyqtSignal(str)  # Define the signal for status messages

    def __init__(self):
        super().__init__()
        self.csv_file = None
        self.output_writer = None
        self.filename = None
        self.is_logging = False
        self.data_queue = []  # Queue to store data batches
        self.mutex = QMutex()  # Mutex for thread-safe access to the queue
        self.condition = QWaitCondition()  # Condition to wait for new data
        self.running = True  # Control flag for the thread

    def run(self):
        """Thread execution loop for logging data."""
        while self.running:
            self.mutex.lock()
            if not self.data_queue:
                self.condition.wait(self.mutex)  # Wait for new data
            if not self.running:  # Exit if the thread is stopped
                self.mutex.unlock()
                break
            data_batch = self.data_queue.pop(0)  # Get the first batch
            self.mutex.unlock()

            # Write the batch to the CSV file
            if self.is_logging and self.output_writer:
                self.output_writer.writerows(data_batch)
                self.signal_statusBar_debugMsg.emit(f"✅ Logged {len(data_batch)} rows to {self.filename}")

    def start_logging(self, filename, user_info):
        """Start logging data to the specified CSV file."""
        if os.path.exists(filename):
            os.remove(filename)  # Delete the file
            self.signal_statusBar_debugMsg.emit(f"File '{filename}' has been deleted.")
        self.filename = filename
        self.csv_file = open(filename, "a", newline="")
        self.output_writer = csv.writer(self.csv_file)

        if isinstance(user_info, dict):
            self.output_writer.writerow(["ID", "Gender", "Age", "Weight", "Height"])  # or add "Weight"
            self.output_writer.writerow([
                user_info.get("id", ""),
                user_info.get("gender", ""),
                user_info.get("age", ""),
                user_info.get("weight", ""),
                user_info.get("height", "")
            ])
            self.output_writer.writerow([])  # Blank row
        else:
            print("⚠️ Invalid user_info format, expected a dict.")

        self.output_writer.writerow(["Time(us)", "GSR", "ECG", "IR Channel", "Red Channel", "PPG"])
        self.is_logging = True
        self.signal_statusBar_debugMsg.emit(f"Logging started, file saved as: {filename}")

    def stop_logging(self):
        """Stop logging and close the CSV file."""
        self.is_logging = False
        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
            self.signal_statusBar_debugMsg.emit("Logging stopped. File closed successfully.")
        
        # Call the new function to remove duplicates and sort data
        self.remove_duplicates_and_sort(self.filename)

    def remove_duplicates_and_sort(self, filename):
        """Remove duplicates and sort data in the specified CSV file."""
        if filename and os.path.exists(filename):
            # Read all lines to preserve the first 3 rows
            with open(filename, "r") as f:
                all_lines = f.readlines()

            # Extract the first 3 rows (header/info) and the rest as data
            header_lines = all_lines[:3]
            data_lines = all_lines[3:]

            # Use pandas to process only the data portion
            from io import StringIO
            data_str = "".join(data_lines)
            df = pd.read_csv(StringIO(data_str))

            # Remove duplicates and sort by the first column
            df = df.drop_duplicates()
            df = df.sort_values(by=df.columns[0], ascending=True)

            # Save the cleaned file back
            with open(filename, "w", newline="") as f:
                f.writelines(header_lines)  # Write the original top 3 lines
                df.to_csv(f, index=False)   # Append the cleaned/sorted data

            self.signal_statusBar_debugMsg.emit(f"✅ Cleaned data (from row 4+) saved to {filename}")
            print(f"✅ Cleaned data (from row 4+) saved to {filename}")

    def write_batch_to_csv(self, time_list, gsr_list, ecg_list, ir_list, red_list, ppg_avg_list):
        """Queue a batch of sensor readings for logging."""
        rows = list(zip(time_list, gsr_list, ecg_list, ir_list, red_list, ppg_avg_list))
        self.mutex.lock()
        self.data_queue.append(rows)
        self.condition.wakeAll()  # Notify the thread that new data is available
        self.mutex.unlock()

    def stop(self):
        """Stop the thread and clean up resources."""
        self.running = False
        self.condition.wakeAll()  # Wake the thread to exit the loop
        self.wait()  # Wait for the thread to finish


