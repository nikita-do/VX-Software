import cbor2
import json
import paho.mqtt.client as mqtt
from PyQt6.QtCore import QThread, pyqtSignal

class MqttClient(QThread):
    """
    Handles MQTT communication in a separate thread.
    """
    signal_receivedPayload = pyqtSignal(str, str)  # Define the signal

    signal_statusBar_debugMsg = pyqtSignal(str)  # Define the signal for status messages
    
    signal_rawData = pyqtSignal(dict)  # Define the signal for processed data

    def __init__(self, broker, port, username, password):
        super().__init__()  # Ensure the superclass __init__ is called
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.data_topic = None  # Initialize data topic to None
        self.client = mqtt.Client()
        self.client.username_pw_set(self.username, self.password)
        self.client.tls_set()  # Enables TLS encryption
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def run(self):
        """Connect to the MQTT broker and start the loop."""
        self.client.connect(self.broker, self.port, 60)
        self.client.loop_forever()

    def stop(self):
        """Disconnect the MQTT client and stop the thread."""
        self.client.disconnect()  # Gracefully disconnect the client
        self.client.loop_stop()   # Stop the MQTT loop
        self.quit()               # Stop the thread
        self.wait()               # Wait for the thread to finish
        
    def update_data_topic(self, new_data_topic):
        """Update the data topic and resubscribe to it."""
        self.data_topic = new_data_topic

    def on_connect(self, client, userdata, flags, rc):
        """Callback when the client connects to the broker."""
        if rc == 0:
            self.signal_statusBar_debugMsg.emit("Connected to HiveMQ Cloud!")
            self.client.subscribe("device")  # Subscribe to the data topic
        else:
            self.signal_statusBar_debugMsg.emit(f"Connection failed with code {rc}")

    def on_message(self, client, userdata, msg):
        """Callback when a message is received."""
        topic = msg.topic
        if topic != self.data_topic:
            payload = msg.payload.decode("utf-8") 
        else:
            data = cbor2.loads(msg.payload)
            payload = json.dumps(data, separators=(',', ':'))  # Compact JSON
        self.signal_receivedPayload.emit(topic, payload)

    def publish_message(self, topic, message, qos = 2, retain = False):
        """Publish a message to a specific topic."""
        self.client.publish(topic, message, qos=qos, retain=retain)

    def subscribe_to_topic(self, topic):
        """Subscribe to a specific topic."""
        self.client.subscribe(topic)
        print(f"Subscribed to topic: {topic}")

    