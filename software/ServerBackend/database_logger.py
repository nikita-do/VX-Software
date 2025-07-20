import time
import threading
from datetime import datetime, timezone
from mqtt_subscriber import MQTTSubscriber
from data_processor import DataProcessor
from drive_uploader import DriveUploader

from influxdb_client import InfluxDBClient, Point, WriteOptions
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

    if measurement_name == "biosignal":
        # Find a key that contains array data
        data_keys = [
            k for k in data_dict.keys()
            if k not in ("measurement", "time")
        ]

        num_points = len(data_dict[data_keys[0]])
        # print(f"[InfluxDBLogger] Determined num_points: {num_points}")

        for idx in range(num_points):
            time = None
            if "time" in data_dict:
                time = data_dict["time"][idx]

            point = Point(measurement_name)

            if tags is not None:
                for tag_key, tag_val in tags.items():
                    point = point.tag(tag_key, str(tag_val))

            for key in data_keys:
                value = data_dict[key][idx]
                point = point.field(key, float(value))

            if time is not None:
                point = point.time(time, write_precision="ns")

            points.append(point)

    elif measurement_name == "features":
        point = Point(measurement_name)

        if tags is not None:
            for tag_key, tag_val in tags.items():
                point = point.tag(tag_key, str(tag_val))

        for key, value in data_dict.items():
            if key not in ("measurement", "time"):
                try:
                    point = point.field(key, float(value))
                except Exception as e:
                    print(f"[DatabaseLogger] Could not add field {key}: {e}")

        if "time" in data_dict:
            point = point.time(data_dict["time"], write_precision="ns")

        points.append(point)

    elif measurement_name == "pain_assessment":
        point = Point(measurement_name)

        if tags is not None:
            for tag_key, tag_val in tags.items():
                point = point.tag(tag_key, str(tag_val))
        
        point = point.field("value", float(data_dict["value"]))
        point = point.time(data_dict["time"], write_precision="ns")
    
        points.append(point)
        
    else:
        print(f"[InfluxDBLogger] Unknown measurement type: {measurement_name}. No points generated.")
    # print(f"[InfluxDBLogger] Finished generating {len(points)} points.")
    return points

class DatabaseLogger(threading.Thread):
    def __init__(self, url, token, org, bucket, data_provider: DataProcessor, tag_provider: MQTTSubscriber):
        super().__init__(daemon=True)

        self.running = True
        self.start_time = None

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
        self.processor = data_provider
        self.subscriber = tag_provider
        # Initialize Drive uploader
        self.drive_uploader = DriveUploader()

    def run(self):
        print("[DatabaseLogger] Thread started.")
        last_measuring_state = False
        self.start_time = None

        # Ensure the uploader is authenticated and folder is created
        if self.drive_uploader is not None:
            try:
                self.drive_uploader.authenticate()
                # self.drive_uploader.get_or_create_folder()
                print("[DatabaseLogger] Google Drive uploader initialized.")
            except Exception as e:
                print(f"[DatabaseLogger] Error initializing Google Drive uploader: {e}")
                self.drive_uploader = None

        while self.running:
            try:
                is_measuring = self.subscriber.is_device_measuring()
                # is_online = self.subscriber.is_device_online()

                if is_measuring:
                    result = self.processor.get_output_queue()

                    if not last_measuring_state:
                        # Device just started measuring
                        dt = datetime.fromtimestamp(
                            result["time"][0] / 1e9,
                            tz=timezone.utc
                        )
                        self.start_time = dt.isoformat().replace("+00:00", "Z")
                        print(f"[DatabaseLogger] Measurement started at {self.start_time}")
                        last_measuring_state = True

                    # Process and write data
                    user_info = self.subscriber.get_user_info()
                    points = generate_influx_points(result, tags=user_info)
                    try:
                        self.write_api.write(bucket=self.bucket, org=self.org, record=points)
                        print(f"[DatabaseLogger] Data written to InfluxDB for measurement: {result['measurement']}")
                    except Exception as e:
                        print(f"[DatabaseLogger] Error writing to InfluxDB: {e}")
                        continue

                else:
                    if last_measuring_state:
                        # Device just stopped measuring
                        stop_dt = datetime.now(timezone.utc)
                        end_time_str = stop_dt.isoformat().replace("+00:00", "Z")

                        data_path = self.save_csv_from_influx(
                            start_time=self.start_time,
                            end_time=end_time_str,
                            filename= None  # Use default filename based on timestamp
                        )
                        print("[DatabaseLogger] Measurement stopped. Data saved to CSV.")

                        # Optionally, upload to Google Drive
                        if self.drive_uploader is not None and data_path is not None:
                            view_link = self.drive_uploader.upload_file(
                                filepath = data_path
                            )

                            self.subscriber.publish_data_link(link=view_link)
                            print("[DatabaseLogger] Data uploaded to Google Drive and link published to MQTT.")

                        else:
                            print("[DatabaseLogger] Google Drive uploader not available or data path is None.")

                        last_measuring_state = False
                        self.start_time = None  # reset for next session

                time.sleep(0.05)

            except Exception as e:
                print(f"[DatabaseLogger] Error: {e}")
                time.sleep(0.1)

    def save_csv_from_influx(self, start_time, end_time, filename=None):
        """
        Save data from InfluxDB to a CSV file within the specified time range.
        If filename is not provided, it will be generated based on the current timestamp.
        """
        # Ensure the 'data' directory exists
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(data_dir, exist_ok=True)
        if filename is not None:
            filename = os.path.join(data_dir, filename)
        else:
            filename = os.path.join(data_dir, datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv")

        if start_time is None:
            start_time = "-1h"  # Default to last hour if no start_time is set

        if end_time is None:
            end_time = datetime.now(timezone.utc).isoformat()

        query = f"""
        from(bucket: "{self.bucket}")
            |> range(start: {start_time}, stop: {end_time})
            |> filter(fn: (r) => r["_measurement"] == "biosignal")
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        """

        try:
            result = self.client.query_api().query_data_frame(query)
            if result.empty:
                print("[DatabaseLogger] No data found in specified time range.")
                return
            result.to_csv(filename, index=False)
            print(f"[DatabaseLogger] Data saved to {filename}")
            return filename
        except Exception as e:
            print(f"[DatabaseLogger] Error saving data to CSV: {e}")
            return None

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
   
    def stop(self):
        self.running = False
        if self.start_time is not None:
            print(f"[DatabaseLogger] Stopping logger. Saving data from {self.start_time} to now.")
            self.save_csv_from_influx(self.start_time, None, None)
        self.client.close()  # Close InfluxDB client
        
        # Close csv file if it was opened


