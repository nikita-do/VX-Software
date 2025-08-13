import queue
import threading
import time
from mqtt_subscriber import MQTTSubscriber

class PacketProcessor(threading.Thread):
    def __init__(self, data_provider: MQTTSubscriber):
        """ Initializes the PacketProcessor thread. """
        super().__init__(daemon=True)
        self.running = True

        self.data_queue = queue.Queue(maxsize=100) 

        self.subscriber = data_provider

        self.last_packet = None

    def run(self):
        """
        Main loop: continuously process packets from _packet_queue
        """
        while self.running:
            try:
                raw_packet = self.subscriber.get_output_queue()
                batch_size = self.subscriber.get_batch_size()

                # Validate the packet data
                validated_packet = self.validate_data(raw_packet, batch_size)
                if validated_packet is None:
                    print("[PacketProcessor] Invalid packet data, skipping.")
                    continue

                # Handle packet loss and interpolation
                if self.last_packet is not None:
                    packet_id_diff = validated_packet["id"] - self.last_packet["id"]
                    if packet_id_diff > 1:
                        missing_packets = self.handle_packet_loss(self.last_packet, validated_packet, packet_id_diff - 1)
                        for missing in missing_packets:
                            if missing is not None:
                                self.data_queue.put(missing)
                                print(f"[PacketProcessor] Inserted virtual packet ID {missing['id']}.")
                            else:
                                print("[PacketProcessor] Inserted None for missing packet.")

                # Add the current packet to the queue
                self.data_queue.put(validated_packet)
                self.last_packet = validated_packet

            except Exception as e:
                print(f"[PacketProcessor] Error {e}")
                time.sleep(0.1)
                continue

    def validate_data(self, data, expected_length=512):
        """
        Validate the incoming JSON packet:
        - Check required fields.
        - Check array lengths are consistent.
        - Ensure arrays match expected_length, pad or truncate if necessary.
        """

        packet_id = data.get("id", None)
        timestamp = data.get("t", None)
        ir_list = data.get("ir", [])
        red_list = data.get("red", [])
        ecg_list = data.get("ecg", [])
        gsr_list = data.get("gsr", [])

        if packet_id is None:
            print("[PacketProcessor] Missing packet id.")
            return None

        if not all(isinstance(lst, list) for lst in [ir_list, red_list, ecg_list, gsr_list]):
            print("[PacketProcessor] Invalid data format. One or more signals are not lists.")
            return None

        if not isinstance(timestamp, int):
            print(f"[PacketProcessor] Invalid timestamp type: {type(timestamp)}. Expected int.")
            return None

        # Check that all signals have the same length
        lengths = list(map(len, [ir_list, red_list, ecg_list, gsr_list]))
        if len(set(lengths)) != 1:
            print(f"[PacketProcessor] Mismatched signal lengths: {lengths}")
            return None

        original_length = lengths[0]

        # Pad or truncate signals to match expected_length
        if original_length < expected_length:
            pad_length = expected_length - original_length
            print(f"[PacketProcessor] Packet {packet_id}: Data too short ({original_length} samples). Padding with last value.")

            def pad(lst):
                if len(lst) == 0:
                    return [None] * expected_length
                return lst + [lst[-1]] * pad_length

            ir_list = pad(ir_list)
            red_list = pad(red_list)
            ecg_list = pad(ecg_list)
            gsr_list = pad(gsr_list)

        elif original_length > expected_length:
            print(f"[PacketProcessor] Packet {packet_id}: Data too long ({original_length} samples). Truncating to {expected_length}.")
            ir_list = ir_list[:expected_length]
            red_list = red_list[:expected_length]
            ecg_list = ecg_list[:expected_length]
            gsr_list = gsr_list[:expected_length]

        return {
            "id": packet_id,
            "t": timestamp,
            "ir": ir_list,
            "red": red_list,
            "ecg": ecg_list,
            "gsr": gsr_list
        }


    def handle_packet_loss(self, prev_packet, next_packet, num_missing):
        """
        Handle missing packets:
        - If only 1 missing → interpolate a virtual packet.
        - If >1 missing → insert None packets.
        """
        virtual_packets = []

        if num_missing == 1:
            alpha = 0.5
            print(f"[PacketProcessor] Interpolating virtual packet between "
                  f"ID {prev_packet['id']} and ID {next_packet['id']}.")

            virtual_packet = {
                "id": prev_packet["id"] + 1,
                "ir": [(1 - alpha) * p + alpha * n
                       for p, n in zip(prev_packet["ir"], next_packet["ir"])],
                "red": [(1 - alpha) * p + alpha * n
                        for p, n in zip(prev_packet["red"], next_packet["red"])],
                "ecg": prev_packet["ecg"].copy(),
                "gsr": [(1 - alpha) * p + alpha * n
                        for p, n in zip(prev_packet["gsr"], next_packet["gsr"])]
            }
            virtual_packets.append(virtual_packet)

        else:
            print(f"[PacketProcessor] More than 1 packet missing ({num_missing}). "
                  f"Inserting None for each missing packet.")
            for k in range(num_missing):
                virtual_packets.append(None)

        return virtual_packets

    def get_output_queue(self) -> dict:
        """ Returns the output queue for processed data. """
        return self.data_queue.get()

    def stop(self):
        self.running = False
        # clear the queue
        while not self.data_queue.empty():
            self.data_queue.get_nowait()