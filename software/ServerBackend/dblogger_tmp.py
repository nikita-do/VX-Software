import threading
import queue
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

class InfluxDBLogger(threading.Thread):
    def __init__(self, result_queue, influx_url, token, org, bucket):
        super().__init__(daemon=True)
        self.result_queue = result_queue
        self.running = True

        self.influx_bucket = bucket
        self.write_api = InfluxDBClient(
            url=influx_url,
            token=token,
            org=org
        ).write_api(write_options=SYNCHRONOUS)

    def run(self):
        print("[InfluxDBLogger] Thread started.")
        while self.running:
            try:
                data = self.result_queue.get(timeout=1)
                self._log_to_influxdb(data)
                self.result_queue.task_done()

            except queue.Empty:
                continue

    def _log_to_influxdb(self, data):
        try:
            point = (
                Point("sensor_prediction")
                .tag("sensor", data["sensor"])
                .field("prediction", float(data["prediction"]))
                .field("samples", data["num_samples"])
                .time(data["timestamp"])
            )
            self.write_api.write(bucket=self.influx_bucket, record=point)
            print(f"[InfluxDBLogger] Logged prediction for {data['sensor']}")
        except Exception as e:
            print(f"[InfluxDBLogger] Error: {e}")

    def stop(self):
        self.running = False
