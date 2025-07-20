import threading
import time
import pandas as pd
import queue
from collections import defaultdict, deque
from pain_assessor import PainAssessor
from packet_processor import PacketProcessor
from mqtt_subscriber import MQTTSubscriber
from data_processor_filters import lowpass_filter, highpass_filter, bandpass_filter, apply_notch_filter, wavelet_denoise

class DataProcessor(threading.Thread):
    def __init__(self, model_path, scaler_path, pca_path, data_provider: PacketProcessor, config_provider: MQTTSubscriber, prediction_window_sec=5):
        """ Initializes the DataProcessor thread. """
        super().__init__(daemon=True)

        self.pain_assessor = PainAssessor(model_path, scaler_path, pca_path, prediction_window_sec)
        self.provider = data_provider
        self.subscriber = config_provider
        self.window_sec = prediction_window_sec

        self.lock = threading.Lock()
        self.running = True

        self.result_queue = queue.Queue(maxsize=100)  # Queue for processed data

        self.raw_buffers = defaultdict(lambda: deque())  
        # @TODO: Optional
        # self.raw_buffers = defaultdict(list)

        self.preprocessed_buffers = defaultdict(lambda: deque())

    def run(self):
        print("[Processor] Data processor thread started.")

        while self.running:
            try:
                # Get the next data packet from the data provider
                # This will block until data is available
                data_packet = self.provider.get_output_queue()
                sampling_rate = self.subscriber.get_sampling_rate()
                location_code = self.subscriber.get_location()
                window_size = round(sampling_rate * self.window_sec)  # e.g., 512 × 5 = 2560

                # Preprocess this data
                processed_data = self.process_data(data_packet, sampling_rate, location_code)
                # Add the preprocessed data to the processed queue
                self.result_queue.put(processed_data)

                # Check if prediction window is ready
                # print(f"[Processor] Preprocessed buffers updated with {len(self.preprocessed_buffers['time'])} samples.")
                if len(self.preprocessed_buffers['time']) >= window_size:
                    timestamp_ns = time.time_ns()
                    pain_assessment = self.pain_assessor.predict_from_buffer(
                        self.preprocessed_buffers, sampling_rate)

                    if pain_assessment is not None:
                        features = self.pain_assessor.get_features()
                        self.result_queue.put({
                            "value": pain_assessment,
                            "time": timestamp_ns,
                            "measurement": "pain_assessment"
                        })

                        if features is not None and not features.empty:
                            row_dict = features.iloc[0].to_dict()
                            processed_dict = {
                                key: float(value) if pd.notnull(value) else None
                                for key, value in row_dict.items()
                            }
                            processed_dict["measurement"] = "features"
                            processed_dict["time"] = timestamp_ns
                            self.result_queue.put(processed_dict)
                        else:
                            print("[Processor] Warning: Features extraction returned empty.")
                    else:
                        print("[Processor] Warning: Pain assessment failed.")

                    # Reset buffers after prediction
                    for sensor in self.preprocessed_buffers:
                        self.preprocessed_buffers[sensor].clear()
                        self.raw_buffers[sensor].clear()

                # @TODO: Optional: Moving prediction window approach
                # Clear only the used portion (you can change this to keep overlap)
                # self.preprocessed_buffers[sensor] = self.preprocessed_buffers[sensor][self.window_size:]
                # self.raw_buffers[sensor] = self.raw_buffers[sensor][self.window_size:]
                # self._input_queue.task_done()

            except Exception as e:
                print(f"[Processor] Error {e}")
                time.sleep(0.1)
                continue

    def process_data(self, data_buffers, sampling_rate, location_code) -> dict:
        """ Preprocesses the raw data buffers and returns preprocessed values. """
        # --- timestamp interpolation ---
        packet_time = data_buffers['t']  # epoch time in milliseconds
        num_samples = len(data_buffers['ir'])

        delta_t = 1000 / sampling_rate  # e.g. ~1.953125 ms for 512 Hz

        # Timestamps in milliseconds
        interpolated_timestamps = [
            packet_time + i * delta_t for i in range(num_samples)
        ]

        # Convert to nanoseconds (for InfluxDB or other purposes)
        interpolated_timestamps_ns = [
            int(ts * 1_000_000) for ts in interpolated_timestamps
        ]

        # Store both timestamp resolutions
        self.preprocessed_buffers['time'].extend(interpolated_timestamps_ns)

        # --- signal processing (as you already implemented) ---
        ppg_avg_list = [
            -1 * (ir + red) / 2
            for ir, red in zip(data_buffers['ir'], data_buffers['red'])
        ]
        
        if location_code == "TW": # Taiwan
            filtered_ppg_avg_list = highpass_filter(
            ppg_avg_list, cutoff=0.5, fs=sampling_rate
            )
            filtered_ecg_list = apply_notch_filter(
                data_buffers['ecg'], fs=sampling_rate, notch_freq=60, Q=5
            )
            filtered_ecg_list = apply_notch_filter(
                filtered_ecg_list, fs=sampling_rate, notch_freq=120, Q=5
            )
            filtered_gsr_list = apply_notch_filter(
                data_buffers['gsr'], fs=sampling_rate, notch_freq=60, Q=5
            )
            filtered_gsr_list = apply_notch_filter(
                filtered_gsr_list, fs=sampling_rate, notch_freq=120, Q=5
            )
        
        elif location_code == "VN": # Vietnam
            filtered_ppg_avg_list = highpass_filter(
            ppg_avg_list, cutoff=0.5, fs=sampling_rate
            )
            filtered_ecg_list = apply_notch_filter(
                data_buffers['ecg'], fs=sampling_rate, notch_freq=50, Q=5
            )
            filtered_ecg_list = apply_notch_filter(
                filtered_ecg_list, fs=sampling_rate, notch_freq=100, Q=5
            )
            filtered_gsr_list = apply_notch_filter(
                data_buffers['gsr'], fs=sampling_rate, notch_freq=50, Q=5
            )
            filtered_gsr_list = apply_notch_filter(
                filtered_gsr_list, fs=sampling_rate, notch_freq=100, Q=5
            )

        # Append all data
        self.preprocessed_buffers['ir'].extend(data_buffers['ir'])
        self.preprocessed_buffers['red'].extend(data_buffers['red'])
        self.preprocessed_buffers['ecg'].extend(filtered_ecg_list)
        self.preprocessed_buffers['gsr'].extend(filtered_gsr_list)
        self.preprocessed_buffers['ppg'].extend(filtered_ppg_avg_list)

        # Check if all buffers have the same length
        buffer_lengths = [len(self.preprocessed_buffers[key]) for key in ['ir', 'red', 'ecg', 'gsr', 'ppg', 'time']]
        if len(set(buffer_lengths)) != 1:
            print(f"[Processor] Warning: Buffer length mismatch: {dict(zip(['ir', 'red', 'ecg', 'gsr', 'ppg', 'time'], buffer_lengths))}")

        # Convert deque to list for output
        processed_dict = {
            key: list(deque_obj)
            for key, deque_obj in self.preprocessed_buffers.items()
        }
        processed_dict["measurement"] = "biosignal"

        return processed_dict

    # def pop_batch(self, max_items=100, timeout=1):
    #     """ Pops a batch of items from the processed queue. """
    #     batch = []
    #     try:
    #         item = self.result_queue.get(timeout=timeout)
    #         batch.append(item)
    #         while not self.result_queue.empty() and len(batch) < max_items:
    #             batch.append(self.result_queue.get_nowait())
    #     except queue.Empty:
    #         pass
    #     return batch
    
    
    # def get_input_queue(self):
    #     return self._input_queue

    def get_output_queue(self) -> dict:
        return self.result_queue.get()
    
    def stop(self):
        self.running = False
        # clear the result queue
        while not self.result_queue.empty():
            self.result_queue.get_nowait()
