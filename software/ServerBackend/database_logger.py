import time
import threading
from datetime import datetime
from influxdb_client import InfluxDBClient, Point, WriteOptions

class DatabaseLogger(threading.Thread):
    def __init__(self, url, token, org, bucket, data_processor):
        super().__init__(daemon=True)

        self.running = True
        self.result_queue = data_processor.get_output_queue()

        # Initialize InfluxDB client
        self.client = InfluxDBClient(url=url, token=token, org=org)
        # Set up the write API with batch options
        self.write_api = self.client.write_api(
            write_options=WriteOptions(batch_size=500, flush_interval=1000)
        )

        # Store the bucket and organization
        self.bucket = bucket
        self.org = org
        self.processor = data_processor

    def run(self):
        print("[DatabaseLogger] Thread started.")
        while self.running:
            try:
                batch = self.processor.pop_batch()
                if not batch:
                    continue

                points = [
                    Point("biosignal")
                    .tag("sensor", sensor)
                    .field("value", value)
                    .time(ts)
                    for sensor, value, ts in batch
                ]

                self.write_api.write(bucket=self.bucket, org=self.org, record=points)
                print(f"[DatabaseLogger] {datetime.now()} → Wrote {len(points)} points")
            except Exception as e:
                print(f"[DatabaseLogger] Error {e}")
                time.sleep(1)

    def stop(self):
        self.running = False