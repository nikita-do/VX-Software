import cbor2
import json
import threading
import queue
import paho.mqtt.client as mqtt

MQTT_CLIENT_ID = "BME_SERVER"

MQTT_TOPICS = {
    "TOPIC_DEVICE": ("device/", 0),  # Device ID topic
    "TOPIC_DEVICE_STATUS": (f"device/$$$/status_online", 1),  # Device online status topic
    "TOPIC_DEVICE_ATTR_FS": (f"device/$$$/attributes/sampling_rate", 1),  # Device sampling rate topic
    "TOPIC_DEVICE_ATTR_N": (f"device/$$$/attributes/sample_batch", 1),  # Device sample batch topic

    "TOPIC_DEVICE_RESP_START": (f"device/$$$/responses/start", 1),  # Device response start topic
    "TOPIC_DEVICE_RESP_RESET": (f"device/$$$/responses/reset", 1),  # Device response reset topic
    "TOPIC_DEVICE_CMD_START": (f"device/$$$/commands/start", 1),  # Device command start topic
    "TOPIC_DEVICE_CMD_RESET": (f"device/$$$/commands/reset", 1),  # Device command reset topic
    "TOPIC_DEVICE_DATA": (f"device/$$$/data", 1),  # Device data topic
    
    "TOPIC_USER_INFO": (f"device/$$$/user", 1),  # Client user info topic
    
    "TOPIC_USER_INFO_ID": (f"device/$$$/user/id", 1),  # Client user ID topic
    "TOPIC_USER_INFO_AGE": (f"device/$$$/user/age", 1),  # Client user age topic
    "TOPIC_USER_INFO_GENDER": (f"device/$$$/user/gender", 1), # Client user gender topic
    "TOPIC_USER_INFO_WEIGHT": (f"device/$$$/user/weight", 1),  # Client user weight topic
    "TOPIC_USER_INFO_HEIGHT": (f"device/$$$/user/height", 1),  # Client user height topic
    "TOPIC_USER_INFO_LOCATION": (f"device/$$$/user/location", 1),  # Client user location topic
}

class MQTTSubscriber():
    def __init__(self, broker, port, username, password, certificate):
        self._lock = threading.Lock()

        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.certificate = certificate
        self.packet_queue = queue.Queue(maxsize=100)

        self.subcribed_device_id = "$$$" # subscribed device ID from "device" topic
        self.sampling_rate = None
        self.batch_size = None
        self.measuring = False
        self.online = False
        self.user_info = {}  # Store user info as a dictionary

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
        # Publish backend status as online
        self.client.publish("backend/status_online", payload="true", qos=1, retain=True)

        # Check if a device ID is provided, and subscribe to the topics accordingly
        if self.subcribed_device_id != "$$$":
            for topic, qos in MQTT_TOPICS.values():
                self.client.subscribe(topic)
                print(f"[MQTT] Subscribed to topic: <{topic}> with QoS {qos}")
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
                    with self._lock:
                        # Update the subscribed device ID
                        self.subcribed_device_id = device_id
                    
                    print(f"[MQTT] New device ID received: {self.subcribed_device_id}")

                    # Update the topics with the new device ID
                    self.update_topics(self.subcribed_device_id)
                    for topic, qos in MQTT_TOPICS.values():
                        self.client.subscribe(topic)
                        print(f"[MQTT] Subscribed to topic: <{topic}> with QoS {qos}")
                return
            
            # -> topic /device/<device_ID>/status_online
            elif topic == MQTT_TOPICS["TOPIC_DEVICE_STATUS"][0]:
                device_status = payload.decode('utf-8')
                is_online = None

                if device_status == "true":
                    print("[MQTT] Device is online")
                    is_online = True
                elif device_status == "false":
                    print("[MQTT] Device is offline")
                    is_online = False
                    self.client.publish(MQTT_TOPICS["TOPIC_DEVICE_RESP_START"][0], payload="false", qos=1, retain=True)
                else:
                    print(f"[MQTT] Device Unknown status: {device_status}")

                with self._lock:
                    self.online = is_online
                return
            
            # -> topic /device/<device_ID>/attributes/sampling_rate
            elif topic == MQTT_TOPICS["TOPIC_DEVICE_ATTR_FS"][0]:
                sampling_rate = int(payload.decode("utf-8"))
                print(f"[MQTT] Device sampling rate: {sampling_rate} Hz")

                with self._lock:
                    self.sampling_rate = sampling_rate
                return
            
            # -> topic /device/<device_ID>/attributes/sample_batch
            elif topic == MQTT_TOPICS["TOPIC_DEVICE_ATTR_N"][0]:
                sample_batch = int(payload.decode("utf-8"))
                print(f"[MQTT] Device sample batch: {sample_batch} samples")

                with self._lock:
                    self.batch_size = sample_batch
                return
            
            # -> topic /device/<device_ID>/data
            elif topic == MQTT_TOPICS["TOPIC_DEVICE_DATA"][0]:
                decoded_data = cbor2.loads(payload)
                serialized_data = json.dumps(decoded_data, separators=(',', ':'))
                data = json.loads(serialized_data)

                if isinstance(data, dict):
                    self.packet_queue.put(data)
                else:
                    raise ValueError("[MQTT] Invalid data. Expected a dictionary.")
                return
            
            # -> topic /device/<device_ID>/responses/start
            elif topic == MQTT_TOPICS["TOPIC_DEVICE_RESP_START"][0]:
                device_measure_status = payload.decode("utf-8")
                is_measuring = None

                if device_measure_status == "true":
                    # print("[MQTT] Device is now measuring")
                    is_measuring = True
                elif device_measure_status == "false":
                    # print("[MQTT] Device has stopped measuring")
                    is_measuring = False
                else:
                    print(f"[MQTT] Device measure status unknown: {device_measure_status}")

                with self._lock:
                    self.measuring = is_measuring
                return
            
            elif topic.startswith(MQTT_TOPICS["TOPIC_USER_INFO"][0]):
                # Handle client user info topics
                user_info_key = topic.split("/")[-1]  # Get the last part of the topic
                user_info_value = payload.decode("utf-8")
                print(f"[MQTT] User info received: {user_info_key} = {user_info_value}")
                with self._lock:
                    self.user_info[user_info_key] = user_info_value
                return

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
        self.client.publish("backend/status_online", payload="false", qos=1, retain=True)
        self.client.loop_stop()
        self.client.disconnect()
        print("[MQTT] Disconnected from broker")

    def update_topics(self, device_id):
        """Update the MQTT topics based on the new device ID."""

        self.subcribed_device_id = device_id
        for key, (topic, qos) in MQTT_TOPICS.items():
            MQTT_TOPICS[key] = (topic.replace("$$$", device_id), qos)
        print(f"[MQTT] Updated topics for device ID: {self.subcribed_device_id}")

    def publish_data_link(self, link: str):
        self.client.publish(f"device/{self.subcribed_device_id}/data/file", payload=link, qos=1, retain=False)

    def publish_pain_assessment(self, pain_level: int):
        """Publish the pain assessment result to the MQTT broker."""
        self.client.publish(
            f"device/{self.subcribed_device_id}/pain_level",
            payload=pain_level,
            qos=1,
            retain=False
        )
    
    def publish_pulse_rate(self, pulse_rate: float):
        """Publish the pulse rate to the MQTT broker."""
        self.client.publish(
            f"device/{self.subcribed_device_id}/pulse_rate",
            payload=pulse_rate,
            qos=1,
            retain=False
        )

    def get_output_queue(self) -> dict:
        """Return the data for processing."""
        return self.packet_queue.get()
    
    def get_sampling_rate(self) -> int:
        with self._lock:
            return self.sampling_rate

    def get_batch_size(self) -> int:
        with self._lock:
            return self.batch_size

    def get_device_id(self) -> str:
        with self._lock:
            return self.subcribed_device_id

    def is_device_online(self) -> bool:
        with self._lock:
            return self.online
        
    def is_device_measuring(self) -> bool:
        with self._lock:
            return self.measuring
        
    def get_user_info(self) -> dict:
        with self._lock:
            return self.user_info
        
    def get_location(self) -> str:
        """Get the location code from user info."""
        with self._lock:
            return self.user_info.get("location", "TW") # Default to Taiwan if not set