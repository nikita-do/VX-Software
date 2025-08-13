import threading
import time
import pandas as pd
import queue
from collections import defaultdict, deque
from pain_assessor import PainAssessor
from packet_processor import PacketProcessor
from mqtt_subscriber import MQTTSubscriber
from data_processor_filters import firfilter_lowpass, sosfilt_highpass, gsr_nk_filter
from scipy.signal import find_peaks

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

        self.ppg_hp_filter_state = None  # State for PPG FIR filter
        self.ppg_lp_filter_state = None 
        self.ecg_hp_filter_state = None
        self.ecg_lp_filter_state = None
        self.ecg_n2_filter_state = None
        self.gsr_filter_state = None

        self.sampling_rate = None  # Initialize sampling rate

    def run(self):
        print("[Processor] Data processor thread started.")

        while self.running:
            try:
                while self.sampling_rate is None:
                    print("[Processor] Waiting for sampling rate from subscriber...")
                    time.sleep(0.5)
                    self.sampling_rate = self.subscriber.get_sampling_rate()
                # location_code = self.subscriber.get_location()
                window_size = round(self.sampling_rate * self.window_sec)  # e.g., 512 × 5 = 2560

                # Preprocess this data
                raw_data, processed_data = self.process_data(self.sampling_rate, window_size)
                # Add the preprocessed data to the processed queue
                self.result_queue.put(processed_data)
                # Add the raw data to the processed queue
                self.result_queue.put(raw_data)

                # Check if prediction window is ready
                # print(f"[Processor] Preprocessed buffers updated with {len(self.preprocessed_buffers['time'])} samples.")
                timestamp_ns = time.time_ns()
                pain_assessment = self.pain_assessor.predict_from_buffer(
                    self.preprocessed_buffers, self.sampling_rate)
                
                if pain_assessment is not None:
                    self.subscriber.publish_pain_assessment(int(pain_assessment))

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
                for sensor in self.raw_buffers:
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

    def process_data(self, sampling_rate, window_size) -> dict:
        """ Preprocesses the raw data buffers and returns preprocessed values. """
        # --- timestamp interpolation ---

        while len(self.raw_buffers['time']) < window_size:
            data_packet = self.provider.get_output_queue()

            packet_time = data_packet['t']  # epoch time in milliseconds
            num_samples = len(data_packet['ir'])

            delta_t = 1000 / sampling_rate  # e.g. ~1.953125 ms for 512 Hz

            # Timestamps in milliseconds
            interpolated_timestamps = [
                packet_time + i * delta_t for i in range(num_samples)
            ]

            # Convert to nanoseconds (for InfluxDB)
            interpolated_timestamps_ns = [
                int(ts * 1_000_000) for ts in interpolated_timestamps
            ]

            # Append all data
            self.raw_buffers['time'].extend(interpolated_timestamps_ns)
            self.raw_buffers['ir'].extend(data_packet['ir'])
            self.raw_buffers['red'].extend(data_packet['red'])
            self.raw_buffers['ecg'].extend(data_packet['ecg'])
            self.raw_buffers['gsr'].extend(data_packet['gsr'])

        # --- signal processing (as you already implemented) ---
        self.preprocessed_buffers['time'].extend(self.raw_buffers['time'])

        # Calculate G_theory_uS for GSR (Galvanic Skin Response)
        # Avoid division by zero and handle empty buffers
        G_theory_uS = []
        for gsr in self.raw_buffers['gsr']:
            try:
                val = 1 / (100e3 * (6600 / gsr - 1)) * 1e6 if gsr != 0 else 0 # Convert to microSiemens
            except ZeroDivisionError:
                val = 0
            G_theory_uS.append(val)

        ppg_avg_list = [
            -1 * (ir + red) / 2
            for ir, red in zip(self.raw_buffers['ir'], self.raw_buffers['red'])
        ]

        # Apply bandpass filter to PPG data
        highpass_ppg_avg_list, self.ppg_hp_filter_state = sosfilt_highpass(
        ppg_avg_list, cutoff=0.5, fs=sampling_rate, order=2, zi=self.ppg_hp_filter_state
        )

        filtered_ppg_avg_list, self.ppg_lp_filter_state = firfilter_lowpass(
            highpass_ppg_avg_list, cutoff=7, fs=sampling_rate, numtaps=201, zi=self.ppg_lp_filter_state
        )

        highpass_ecg_list, self.ecg_hp_filter_state = sosfilt_highpass(
            self.raw_buffers['ecg'], cutoff=0.5, fs=sampling_rate, order=2, zi=self.ecg_hp_filter_state
        )

        filtered_ecg_list, self.ecg_lp_filter_state = firfilter_lowpass(
            highpass_ecg_list, cutoff=40, fs=sampling_rate, numtaps=201, zi=self.ecg_lp_filter_state
        )

        filtered_gsr_list = gsr_nk_filter(
            G_theory_uS, fs=sampling_rate
        )

        # Calculate pulse rate from filtered PPG signal
        def calculate_pulse_rate(ppg_signal, fs):

            # If the magnitude of PPG is too small, skip calculation
            if max(ppg_signal) - min(ppg_signal) < 50:
                return None
            # Find peaks in the PPG signal (heart beats)
            peaks, _ = find_peaks(ppg_signal, distance=int(0.4 * fs))  # at least 0.4s between beats (~150 bpm max)
            if len(peaks) < 2:
                return None  # Not enough peaks to calculate rate

            # Calculate RR intervals (in seconds)
            rr_intervals = [(peaks[i+1] - peaks[i]) / fs for i in range(len(peaks)-1)]
            if not rr_intervals:
                return None

            avg_rr = sum(rr_intervals) / len(rr_intervals)
            pulse_rate = 60.0 / avg_rr if avg_rr > 0 else None
            return pulse_rate

        pulse_rate = calculate_pulse_rate(filtered_ppg_avg_list, sampling_rate)
        if pulse_rate is not None:
            print(f"[Processor] Calculated pulse rate: {pulse_rate:.2f} bpm")
            self.subscriber.publish_pulse_rate(pulse_rate)
        else:
            print("[Processor] Warning: Unable to calculate pulse rate.")
            self.subscriber.publish_pulse_rate("None")

        self.preprocessed_buffers['ecg'].extend(filtered_ecg_list)
        self.preprocessed_buffers['gsr'].extend(filtered_gsr_list)
        self.preprocessed_buffers['ppg'].extend(filtered_ppg_avg_list)

        # Check if all buffers have the same length
        buffer_lengths = [len(self.preprocessed_buffers[key]) for key in ['ecg', 'gsr', 'ppg', 'time']]
        if len(set(buffer_lengths)) != 1:
            print(f"[Processor] Warning: Buffer length mismatch: {dict(zip(['ecg', 'gsr', 'ppg', 'time'], buffer_lengths))}")

        # Convert deque to list for output
        raw_dict = {
            key: list(deque_obj)
            for key, deque_obj in self.raw_buffers.items()
        }
        raw_dict["measurement"] = "raw_biosignal"

        processed_dict = {
            key: list(deque_obj)
            for key, deque_obj in self.preprocessed_buffers.items()
        }
        processed_dict["measurement"] = "processed_biosignal"

        return raw_dict, processed_dict

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
