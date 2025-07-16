import time
import threading
from datetime import datetime
from mqtt_subscriber import MQTTSubscriber
from data_processor import DataProcessor

from influxdb_client import InfluxDBClient, Point, WriteOptions
import csv
import os

def generate_influx_points(data_dict, tags=None):
    """
    Generate InfluxDB Point objects for biosignal measurement with each sensor as a separate field.

    Parameters:
        data_dict (dict): Dictionary containing sensor keys and timestamps, plus a 'measurement' key.
        tags (dict): Optional dict of tags to add to each Point.

    Returns:
        list of Point: List of InfluxDB Point objects.
    """
    points = []

    measurement_name = data_dict.get("measurement")
    print(f"[InfluxDBLogger] Using measurement name: {measurement_name}")

    # Find a key that contains array data
    data_keys = [
        k for k in data_dict.keys()
        if k not in ("measurement", "timestamp_ns", "timestamp_ms")
    ]

    if not data_keys:
        raise ValueError("No data fields found in data_dict to determine number of points.")

    num_points = len(data_dict[data_keys[0]])
    print(f"[InfluxDBLogger] Determined num_points: {num_points}")

    for idx in range(num_points):
        timestamp_ns = None
        if "timestamp_ns" in data_dict:
            timestamp_ns = data_dict["timestamp_ns"][idx]
            print(f"[InfluxDBLogger] Using timestamp_ns: {timestamp_ns} for index {idx}")

        point = Point(measurement_name)

        if tags:
            for tag_key, tag_val in tags.items():
                point = point.tag(tag_key, str(tag_val))
                print(f"[InfluxDBLogger] Added tag {tag_key}={tag_val}")

        for key, values in data_dict.items():
            if key in ("timestamp_ns", "measurement"):
                continue
            value = values[idx]
            point = point.field(key, float(value))
            print(f"[InfluxDBLogger] Added field {key}={value}")

        if timestamp_ns is not None:
            point = point.time(timestamp_ns, write_precision="ns")
            print(f"[InfluxDBLogger] Set time for point: {timestamp_ns}")

        points.append(point)
        print(f"[InfluxDBLogger] Appended point for index {idx}")

    print(f"[InfluxDBLogger] Finished generating {len(points)} points.")
    return points

class DatabaseLogger(threading.Thread):
    def __init__(self, url, token, org, bucket, log_data_provider: DataProcessor, log_tag_provider: MQTTSubscriber):
        super().__init__(daemon=True)

        self.running = True

        # csv file management
        self.csv_file = None
        self.output_writer = None

        # Initialize InfluxDB client
        self.client = InfluxDBClient(url=url, token=token, org=org)
        # Set up the write API with batch options
        self.write_api = self.client.write_api(
            # write_options=WriteOptions(batch_size=500, flush_interval=1000)
            write_options=WriteOptions(write_type="synchronous")
        )

        # Store the bucket and organization
        self.bucket = bucket
        self.org = org
        self.processor = log_data_provider
        self.subscriber = log_tag_provider

    # def _log_to_influxdb(self, data):
    #     try:
    #         point = (
    #             Point("sensor_prediction")
    #             .tag("sensor", data["sensor"])
    #             .field("prediction", float(data["prediction"]))
    #             .field("samples", data["num_samples"])
    #             .time(data["timestamp"])
    #         )
    #         self.write_api.write(bucket=self.influx_bucket, record=point)
    #         print(f"[InfluxDBLogger] Logged prediction for {data['sensor']}")
    #     except Exception as e:
    #         print(f"[InfluxDBLogger] Error: {e}")

    def run(self):
        print("[DatabaseLogger] Thread started.")

        while self.running:
            try:
                result = self.processor.get_output_queue()
                user_info = self.subscriber.get_user_info()

                points = generate_influx_points(result, tags=user_info)
                
                is_measuring = self.subscriber.is_device_measuring()
                if is_measuring:
                    if result.get("measurement") == "pain_assessment":
                        # If it's a pain assessment, generate a CSV file
                        self._log_to_csv(result, tags=user_info)
                else:
                    # close the CSV file
                    self.close_csv_file()

                self.write_api.write(bucket=self.bucket, org=self.org, record=points)
                print(f"[DatabaseLogger] {datetime.now()} → Wrote {len(points)} points")
            except Exception as e:
                print(f"[DatabaseLogger] Error {e}")
                time.sleep(0.1)
                continue

    def _log_to_csv(self, data, tags=None):
        try:
            if self.csv_file is None or self.csv_file.closed:
                filename = datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv"
                self.csv_file = open(filename, mode="a", newline="")
                self.output_writer = csv.writer(self.csv_file)

                # Write tags as first row
                if tags:
                    tag_row = [f"{k}={v}" for k, v in tags.items()]
                    self.output_writer.writerow(tag_row)
                else:
                    self.output_writer.writerow([])

                # Write header
                fieldnames = [k for k in data.keys() if k != "measurement"]
                self.output_writer.writerow(fieldnames)

                print(f"[DatabaseLogger] CSV file '{filename}' created with header.")
            else:
                fieldnames = [k for k in data.keys() if k != "measurement"]

            # Write new rows
            num_rows = len(data[fieldnames[0]]) if fieldnames else 0
            for idx in range(num_rows):
                row = [data[key][idx] for key in fieldnames]
                self.output_writer.writerow(row)

            self.csv_file.flush()
            print(f"[DatabaseLogger] Wrote {num_rows} rows to CSV file.")

        except Exception as e:
            print(f"[DatabaseLogger] Error writing to CSV: {e}")

    def close_csv_file(self):
        """Close the CSV file if it is open."""
        if self.csv_file and not self.csv_file.closed:
            self.csv_file.close()
            print("[DatabaseLogger] Closed CSV file successfully.")
        else:
            print("[DatabaseLogger] No CSV file to close or it is already closed.")
   
    def stop(self):
        self.running = False
        self.client.close()  # Close InfluxDB client
        self.close_csv_file()  # Close csv file if it was opened
        
        # Close csv file if it was opened


