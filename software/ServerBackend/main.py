import os
import threading
from mqtt_subscriber import MQTTSubscriber
from data_processor import DataProcessor
from database_logger import DatabaseLogger

# MQTT and Database Configuration
MQTT_CONFIG = {
    "broker": os.getenv("MQTT_BROKER", "700be638167b43289186dff783367cc3.s1.eu.hivemq.cloud"),
    "port": int(os.getenv("MQTT_PORT", 8883)),
    "username": os.getenv("MQTT_USERNAME", "ngocdo"),
    "password": os.getenv("MQTT_PASSWORD", "Ng19102002"),
    "certificate": "/home/bme662/vital-X/resources/server.pem"
}

INFLUX_CONFIG = {
    "url": "http://localhost:8086",
    "token": os.getenv("INFLUXDB_TOKEN", "TuUAJAXc9vwWcwG-W690wjEyRg3DiOlQ-54I5EVSPcCAPL5gm2dIkqhAQnT3RZ6jY_heDkpfySPFCxUHFoWCcw=="),
    "org": "BME662",
    "bucket": "bme662-db"
}

PROCESSOR_CONFIG = {
    "model_path": "/home/bme662/vital-X/resources/pain_votingclassifier_J.pkl",
    "scaler_path": "/home/bme662/vital-X/resources/scaler.pkl",
    "pca_path": "/home/bme662/vital-X/resources/pca.pkl"
}

class MainServer:
    def __init__(self, mqtt_config, influx_config):
        ''' Initializes the main server with MQTT and Database configurations. '''
        
        # Initialize the data processor and get its queue
        self.processor = DataProcessor(
            model_path=PROCESSOR_CONFIG["model_path"],
            scaler_path=PROCESSOR_CONFIG["scaler_path"],
            pca_path=PROCESSOR_CONFIG["pca_path"],
            sampling_rate=512, 
            prediction_window_sec=5.5
        )
        self.queue = self.processor.get_input_queue()

        # Initialize MQTT subscriber
        self.mqtt_client = MQTTSubscriber(
            broker=mqtt_config["broker"],
            port=mqtt_config["port"],
            username=mqtt_config["username"],
            password=mqtt_config["password"],
            certificate=mqtt_config["certificate"],
            data_queue=self.queue
        )

        # Initialize Database logger
        self.database_logger = DatabaseLogger(
            url=influx_config["url"],
            token=influx_config["token"],
            org=influx_config["org"],
            bucket=influx_config["bucket"],
            data_processor=self.processor
        )

    def start(self):
        print("[System] Starting Main Server Program...")
        self.mqtt_client.start()
        self.processor.start()
        self.database_logger.start()

        try:
            while True:
                pass  # Keep main thread alive
        except KeyboardInterrupt:
            print("\n[System] Shutting down server...")

if __name__ == "__main__":
    server = MainServer(MQTT_CONFIG, INFLUX_CONFIG)
    server.start()
