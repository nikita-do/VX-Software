import os
from mqtt_subscriber import MQTTSubscriber
from data_processor import DataProcessor
from packet_processor import PacketProcessor
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
    "token": os.getenv("INFLUXDB_TOKEN", "7oDR4z60aoUxju3WAQIZtXxr6z186Zsx5QDghm65e_U-JxQja8ReirzvgDnt9Yy-mN6_oeiDWab9S6rSKYQdrA=="),
    "org": "BME662",
    "bucket": "vitalx"
}

PROCESSOR_CONFIG = {
    "model_path": "/home/bme662/vital-X/resources/pain_votingclassifier_J.pkl",
    "scaler_path": "/home/bme662/vital-X/resources/scaler.pkl",
    "pca_path": "/home/bme662/vital-X/resources/pca.pkl"
}

class MainServer:
    def __init__(self, mqtt_config, influx_config):
        ''' Initializes the main server with MQTT and Database configurations. '''
        self.mqtt_config = mqtt_config
        self.influx_config = influx_config

        # Initialize MQTT subscriber
        self.mqtt_client = MQTTSubscriber(
            broker=self.mqtt_config["broker"],
            port=self.mqtt_config["port"],
            username=self.mqtt_config["username"],
            password=self.mqtt_config["password"],
            certificate=self.mqtt_config["certificate"]
        )

        # Initialize the packet processor and get its queue
        self.packet_processor = PacketProcessor(
            data_provider=self.mqtt_client,
        )

        # Initialize the data processor and push data to its queue
        self.data_processor = DataProcessor(
            model_path=PROCESSOR_CONFIG["model_path"],
            scaler_path=PROCESSOR_CONFIG["scaler_path"],
            pca_path=PROCESSOR_CONFIG["pca_path"],
            data_provider=self.packet_processor,
            config_provider=self.mqtt_client,
            prediction_window_sec=5.5,
        )

        # Initialize Database logger
        self.database_logger = DatabaseLogger(
            url=influx_config["url"],
            token=influx_config["token"],
            org=influx_config["org"],
            bucket=influx_config["bucket"],
            log_data_provider=self.data_processor,
            log_tag_provider=self.mqtt_client
        )
        
    def start(self):
        print("[System] Starting Main Server Program...")
        self.mqtt_client.start()
        self.packet_processor.start()
        self.data_processor.start()
        self.database_logger.start()

        try:
            while True:
                pass  # Keep main thread alive
        except KeyboardInterrupt:
            print("\n[System] Shutting down server...")
            self.mqtt_client.stop()
            self.packet_processor.stop()
            self.data_processor.stop()
            self.database_logger.stop()

if __name__ == "__main__":
    server = MainServer(MQTT_CONFIG, INFLUX_CONFIG)
    server.start()
