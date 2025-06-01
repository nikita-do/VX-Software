import threading
import time
import queue
from collections import defaultdict, deque
from pain_assessor import PainAssessor
from data_processor_filters import lowpass_filter, highpass_filter, bandpass_filter, apply_notch_filter, wavelet_denoise

class DataProcessor(threading.Thread):
    def __init__(self, model_path, scaler_path, pca_path, sampling_rate=512, prediction_window_sec=5):
        """ Initializes the DataProcessor thread. """
        super().__init__(daemon=True)

        self.pain_assessor = PainAssessor(model_path, scaler_path, pca_path)

        self.lock = threading.Lock()
        self.running = True

        self.sampling_rate = sampling_rate
        self.window_size = round(sampling_rate * prediction_window_sec)  # e.g., 512 × 5 = 2560

        self.input_queue = queue.Queue()
        self.processed_queue = queue.Queue()

        self.raw_buffers = defaultdict(lambda: deque([0], maxlen=self.sampling_rate))
        # @TODO: Optional
        # self.raw_buffers = defaultdict(list)

        self.preprocessed_buffers = defaultdict(lambda: deque([0], maxlen=self.window_size))

    def get_input_queue(self):
        return self.input_queue

    def get_output_queue(self):
        return self.processed_queue

    def push(self, data):
        self.input_queue.put(data)

    def run(self):
        print("[Processor] Data processor thread started.")

        while self.running:
            try:
                # @TODO: Get data from the input queue
                data = self.input_queue.get(timeout=1)
                # Extract sensor data from the JSON message
                time_list = data.get("time", [])
                ir_list = data.get("ir", [])
                red_list = data.get("red", [])
                ecg_list = data.get("ecg", [])
                gsr_list = data.get("gsr", [])
                
                # print(f"[Processor] Processing data with {len(time_list)} samples.")
                
                with self.lock:
                    self.raw_buffers['time'].extend(time_list)
                    self.raw_buffers['ir'].extend(ir_list)
                    self.raw_buffers['red'].extend(red_list)
                    self.raw_buffers['ecg'].extend(ecg_list)
                    self.raw_buffers['gsr'].extend(gsr_list)

                    # Preprocess this data
                    self.preprocess_data(self.raw_buffers)

                    # Check if prediction window is ready
                    if len(self.preprocessed_buffers['time']) >= self.window_size:
                        self.predict_and_reset()
            
                self.input_queue.task_done()

            except queue.Empty:
                continue

    def preprocess_data(self, data_buffers):
        """ Preprocesses the raw data buffers and returns preprocessed values. """
        # @TODO: Need to be tested and adjusted

        # Compute PPG Avg and apply filters
        ppg_avg_list = [-1 * (ir + red) / 2 for ir, red in zip(data_buffers['ir'], data_buffers['red'])]

        # Apply filters to PPG data
        filtered_ppg_avg_list = highpass_filter(ppg_avg_list, cutoff=0.5, fs=self.sampling_rate)

        # @Apply filters to ECG data
        filtered_ecg_list = apply_notch_filter(data_buffers['ecg'], fs=self.sampling_rate, notch_freq=60, Q=5)
        filtered_ecg_list = apply_notch_filter(filtered_ecg_list, fs=self.sampling_rate, notch_freq=60*2, Q=5)

        # Apply filters to GSR data
        filtered_gsr_list = apply_notch_filter(data_buffers['gsr'], fs=self.sampling_rate, notch_freq=60, Q=5)
        filtered_gsr_list = apply_notch_filter(filtered_gsr_list, fs=self.sampling_rate, notch_freq=60*2, Q=5)

        # Append preprocessed data to preprocessed buffers
        self.preprocessed_buffers['time'].extend(data_buffers['time'])
        self.preprocessed_buffers['ir'].extend(data_buffers['ir'])
        self.preprocessed_buffers['red'].extend(data_buffers['red'])
        self.preprocessed_buffers['ecg'].extend(filtered_ecg_list)
        self.preprocessed_buffers['gsr'].extend(filtered_gsr_list)
        self.preprocessed_buffers['ppg_avg'].extend(filtered_ppg_avg_list)

        print(f"[Processor] Preprocessed buffers updated with {len(self.preprocessed_buffers['time'])} samples.")


    def predict_and_reset(self):
        """ Predicts pain level and resets the buffers if enough data is available. """
        print("[Processor] Predicting pain level...")
        prediction_result = self.pain_predict(self.preprocessed_buffers)
        print(f"[Processor] -->> Prediction result: {prediction_result}")

        # Reset buffers after prediction
        for sensor in self.preprocessed_buffers:
            self.preprocessed_buffers[sensor].clear()
            # self.raw_buffers[sensor].clear()

        # @TODO: Optional: Moving prediction window approach
        # Clear only the used portion (you can change this to keep overlap)
        # self.preprocessed_buffers[sensor] = self.preprocessed_buffers[sensor][self.window_size:]
        # self.raw_buffers[sensor] = self.raw_buffers[sensor][self.window_size:]

    def pain_predict(self, preprocessed_buffers):
        """ Predicts the pain level based on the preprocessed buffers. """

        roi = self.window_size
        gsr_list  = list(preprocessed_buffers['gsr'])
        ecg_list  = list(preprocessed_buffers['ecg'])
        time_list = list(preprocessed_buffers['time'])

        # Predict pain level using the PainAssessor
        pain_level = self.pain_assessor.predict_from_raw(ecg_list[-roi:], gsr_list[-roi:], time_list[-roi:])
        
        return pain_level

    def pop_batch(self, max_items=100, timeout=1):
        """ Pops a batch of items from the processed queue. """

        batch = []
        try:
            item = self.processed_queue.get(timeout=timeout)
            batch.append(item)
            while not self.processed_queue.empty() and len(batch) < max_items:
                batch.append(self.processed_queue.get_nowait())
        except queue.Empty:
            pass
        return batch
    
    def stop(self):
        self.running = False
