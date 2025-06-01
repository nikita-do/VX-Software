import cbor2
import json
import time
from enum import Enum
import paho.mqtt.client as mqtt

MQTT_CLIENT_ID = "BME_SERVER"

MQTT_TOPICS = {
    "TOPIC_DEVICE": ("device", 0),  # Device ID topic
    "TOPIC_DEVICE_STATUS": (f"device/$$$/status_online", 1),  # Device online status topic
    "TOPIC_DEVICE_ATTR_FS": (f"device/$$$/attributes/sampling_rate", 1),  # Device sampling rate topic
    "TOPIC_DEVICE_ATTR_N": (f"device/$$$/attributes/sample_batch", 1),  # Device sample batch topic
    "TOPIC_DEVICE_RESP_START": (f"device/$$$/responses/start", 1),  # Device response start topic
    "TOPIC_DEVICE_RESP_RESET": (f"device/$$$/responses/reset", 1),  # Device response reset topic
    "TOPIC_DEVICE_CMD_START": (f"device/$$$/commands/start", 1),  # Device command start topic
    "TOPIC_DEVICE_CMD_RESET": (f"device/$$$/commands/reset", 1),  # Device command reset topic
    "TOPIC_DEVICE_DATA": (f"device/$$$/data", 1)  # Device data topic
}

class MQTTSubscriber:
    def __init__(self, broker, port, username, password, certificate, data_queue):
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.certificate = certificate
        self.data_queue = data_queue # Connected Queue for data processing

        self.subcribed_device_id = "$$$" # Store the subscribed device ID from "device" topic
        self.device_status = False  # Track the device status (online/offline)
        self.device_sampling_rate = 0  # Track the device sampling rate
        self.device_sample_batch = 0  # Track the device sample batch
        self.device_measureing = False  # Track if the device is currently measuring

        # Initialize the MQTT client
        self.client = mqtt.Client()

        # Set the credentials and TLS settings
        self.client.username_pw_set(username, password)
        if certificate:
            self.client.tls_set(certificate)
        else:
            self.client.tls_set()
        self.client.tls_insecure_set(True)

        # Set the callbacks for connection and message handling
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, rc):
        """Callback when the client connects to the broker."""

        print(f"[MQTT] Connected with code {rc}")

        # Check if a device ID is provided, and subscribe to the topics accordingly
        if self.subcribed_device_id != "$$$":
            for topic, qos in MQTT_TOPICS.values():
                self.subscribe_to_topic(topic, qos)
        else:
            # If no device ID is provided, subscribe to the "device" topic
            self.client.subscribe(MQTT_TOPICS["TOPIC_DEVICE"])

    def on_message(self, client, userdata, msg):
        """Callback when a message is received."""

        topic = msg.topic
        payload = msg.payload

        try:
            # Decode the payload based on the topic
            # -> topic /device
            if topic == MQTT_TOPICS["TOPIC_DEVICE"][0]:
                # Handle device ID subscription
                device_id = payload.decode("utf-8")

                # Only update topics if the device ID is updated
                if self.subcribed_device_id != device_id:
                    self.subcribed_device_id = device_id
                    print(f"[MQTT] New device ID received: {self.subcribed_device_id}")
                    # Update the topics with the new device ID
                    self.update_topics(self.subcribed_device_id)
                    # Subscribe to all other topics with the updated device ID
                    for topic, qos in MQTT_TOPICS.values():
                        self.subscribe_to_topic(topic, qos)
                return
            # -> topic /device/<device_ID>/status_online
            elif topic == MQTT_TOPICS["TOPIC_DEVICE_STATUS"][0]:
                # Get the device status from the payload
                device_status = payload.decode('utf-8')
                # Update the device status based on the payload
                if device_status == "true":
                    print("[MQTT] Device is online")
                    self.device_status = True
                elif device_status == "false":
                    print("[MQTT] Device is offline")
                    self.device_status = False
                else:
                    print(f"[MQTT] Device Unknown status: {self.device_status}")
                return
            # -> topic /device/<device_ID>/attributes/sampling_rate
            elif topic == MQTT_TOPICS["TOPIC_DEVICE_ATTR_FS"][0]:
                self.device_sampling_rate = int(payload.decode("utf-8"))
                print(f"[MQTT] Device sampling rate: {self.device_sampling_rate} Hz")
                return
            # -> topic /device/<device_ID>/attributes/sample_batch
            elif topic == MQTT_TOPICS["TOPIC_DEVICE_ATTR_N"][0]:
                self.device_sample_batch = int(payload.decode("utf-8"))
                print(f"[MQTT] Device sample batch: {self.device_sample_batch} samples")
                return
            # -> topic /device/<device_ID>/data
            elif topic == MQTT_TOPICS["TOPIC_DEVICE_DATA"][0]:
                # Decode the payload as CBOR
                decoded_data = cbor2.loads(msg.payload)
                # Decode the payload as Compact JSON
                serialized_data = json.dumps(decoded_data, separators=(',', ':'))
                # Deserialize data to a Python object
                data = json.loads(serialized_data)
                # Check data validity
                if isinstance(data, dict):
                    # self.data_thread.add_data(data)
                    # @TODO: transfer data to processor queue
                    print(f"[MQTT] Validated data with length: {len(data)}")
                    self.data_queue.put(data)
                else:
                    raise ValueError("[MQTT] Invalid data. Expected a dictionary.")
                return
            # -> topic /device/<device_ID>/responses/start
            elif topic == MQTT_TOPICS["TOPIC_DEVICE_RESP_START"][0]:
                # Get the measurement start response
                device_measure_status = msg.payload.decode("utf-8")
                # Update the device measuring status based on the response
                if device_measure_status == "true":
                    self.device_measureing = True
                    print("[MQTT] Device is now measuring")
                elif device_measure_status == "false":
                    self.device_measureing = False
                    print("[MQTT] Device has stopped measuring")
                else:
                    print(f"[MQTT] Device measure status unknown: {device_measure_status}")
                return
            # -> Handle unknown topics
            else:
                print(f"[MQTT] Received message on unknown topic: {topic}")
                return

        except Exception as e:
            print(f"[MQTT] Error parsing message: {e}")

    def start(self):
        """Connect to the MQTT broker and start the loop."""

        self.client.connect(self.broker, self.port)
        self.client.loop_start()
        # @TODO: Consider loop forever to keep the client running
        # self.client.loop_forever()
    
    def stop(self):
        """Stop the MQTT client loop and disconnect."""

        self.client.loop_stop()
        self.client.disconnect()
        print("[MQTT] Disconnected from broker")

    def subscribe_to_topic(self, topic, qos=0):
        """Subscribe to a specific topic."""

        self.client.subscribe(topic)
        print(f"[MQTT] Subscribed to topic: <{topic}> with QoS {qos}")

    def update_topics(self, device_id):
        """Update the MQTT topics based on the new device ID."""

        self.subcribed_device_id = device_id
        for key, (topic, qos) in MQTT_TOPICS.items():
            if "device" in topic:
                MQTT_TOPICS[key] = (topic.replace("$$$", device_id), qos)
        print(f"[MQTT] Updated topics for device ID: {self.subcribed_device_id}")
