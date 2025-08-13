import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

import pandas as pd
import joblib
from sklearn.metrics import classification_report
import pandas as pd
import numpy as np
import neurokit2 as nk
from scipy.stats import skew, kurtosis
import time
from threading import Lock
import queue
from scipy.stats import iqr

class PainAssessor:
    def __init__(self, model_path, scaler_path, pca_path, prediction_window_sec=5.5):
        try:
            self.model = joblib.load(model_path)
            self.scaler = joblib.load(scaler_path)
            self.pca = joblib.load(pca_path)
        except FileNotFoundError as e:
            print('[PainAssessor] Some of these files are missing: pain_votingclassifier_J.pkl, scaler.pkl, pca.pkl')
            print('[PainAssessor] Please ensure that all of these files are present in this directory')
            quit()
        
        # Region of interest in seconds
        self.prediction_window_sec = prediction_window_sec
        self.lock = Lock()
        self.features = queue.Queue(maxsize=100)  # Queue for storing features

    # def extract_feature_from_file(self, file_path):
    #     data = pd.read_csv(file_path, header=2)
    #     ecgdata = data['ECG']
    #     gsrdata = data['GSR']
    #     time = data['Time(us)']
    #     return self.extract_feature(ecgdata, gsrdata, time)

    def extract_feature(self, ecg, gsr, sampling_rate):
        try:
            # === Preprocess ECG and GSR ===
            ecg_cleaned = nk.ecg_clean(ecg, sampling_rate=sampling_rate)
            gsr_cleaned = nk.eda_clean(gsr, sampling_rate=sampling_rate)
            eda_signals, info = nk.eda_process(gsr_cleaned, sampling_rate=sampling_rate)
            gsr_phasic = eda_signals["EDA_Phasic"]

            # === Extract GSR Features ===
            gsr_features = {
                'gsr_amp': np.ptp(gsr_phasic),  # peak-to-peak (amplitude)
                'gsr_max': np.max(gsr_phasic),
                'gsr_skew': skew(gsr_phasic),
                'gsr_kurt': kurtosis(gsr_phasic),
                'gsr_sd': np.std(gsr_phasic),
                'gsr_range': np.max(gsr_phasic) - np.min(gsr_phasic),
                'gsr_iqr': iqr(gsr_phasic),
                'gsr_sdmn': np.std(gsr_phasic) / np.mean(gsr_phasic) if np.mean(gsr_phasic) != 0 else np.nan,
                'gsr_sdsd': np.std(np.diff(gsr_phasic)),
            }

            # === Extract ECG Features (HRV) ===
            try:
                # Use NeuroKit to extract HRV features
                ecg_signals, info = nk.ecg_process(ecg_cleaned, sampling_rate=sampling_rate)
                hrv = nk.hrv_time(ecg_signals['ECG_R_Peaks'], sampling_rate=sampling_rate, show=False)
                hrv_features = {
                    'HRV_MeanNN': hrv['HRV_MeanNN'].values[0],
                    'HRV_SDNN': hrv['HRV_SDNN'].values[0],
                    'HRV_RMSSD': hrv['HRV_RMSSD'].values[0],
                    'HRV_SDSD': hrv['HRV_SDSD'].values[0],
                    'HRV_SDRMSSD': hrv['HRV_SDNN'].values[0] / hrv['HRV_RMSSD'].values[0] if hrv['HRV_RMSSD'].values[0] != 0 else np.nan,
                }
            except Exception as e:
                print(f"[HRV Extraction Error]: {e}")
                hrv_features = {k: np.nan for k in [
                    'HRV_MeanNN', 'HRV_SDNN', 'HRV_RMSSD', 'HRV_SDSD', 'HRV_SDRMSSD'
                ]}

            # === Combine All Features ===
            all_features = {**gsr_features, **hrv_features}
            return pd.DataFrame([all_features])

        except Exception as e:
            print(f"[Feature Extraction Error]: {e}")
            # Return NaN dataframe in case of failure
            empty_features = {**gsr_features, **hrv_features}
            return pd.DataFrame([empty_features])
        
    def predict(self, features):
        features_scaled = self.scaler.transform(features)
        features_pca = self.pca.transform(features_scaled)

        predicted_label = self.model.predict(features_pca)
        return predicted_label[0]
        
    def predict_from_buffer(self, preprocessed_buffers, sampling_rate) -> int:
        """ Predicts the pain level based on the preprocessed buffers. """

        roi = int(self.prediction_window_sec * sampling_rate)
        gsr_list = list(preprocessed_buffers['gsr'])
        ecg_list = list(preprocessed_buffers['ecg'])

        # Take only the last roi samples
        ecg_segment = ecg_list[-roi:]
        gsr_segment = gsr_list[-roi:]

        # Check for None values in the ROI
        if any(val is np.nan for val in ecg_segment) or any(val is np.nan for val in gsr_segment):
            print("[PainAssessor] Skipping prediction due to None values in the ROI.")
            return None

        try:
            # Extract features
            features = self.extract_feature(ecg_segment, gsr_segment, sampling_rate)
            
            if isinstance(features, pd.DataFrame) and not features.empty:  # adjust this condition if necessary
                # Run prediction
                pain_level = self.predict(features)
                print(f"[PainAssessor] Predicted pain level: {pain_level}")
                with self.lock:
                    self.features.put(features)
                return pain_level
            else:
                print('[PainAssessor] Missing or invalid feature(s)')
                return None

        except Exception as e:
            print(e)
            return None
        
    
    # def predict_from_file(self, file_path):
    #     try:
    #         features = self.extract_feature_from_file(file_path)
    #     except Exception as e:
    #         print(e)
    #         return None
    #     return self.predict(features)

    # def _up_sampling_all(self, time, gsr, ecg, ppg, current_fs, up_fs):
    #     upSamplingRateFactor = up_fs / current_fs
    #     roi_samples = int(current_fs * self.prediction_window_sec)                

    #     new_time = newTime = np.linspace(0, self.prediction_window_sec * 1000, roi_samples * upSamplingRateFactor)
    #     new_gsr = self.up_sampling(gsr, roi_samples, upSamplingRateFactor)
    #     new_ecg = self.up_sampling(ecg, roi_samples, upSamplingRateFactor)
    #     new_ppg = self.up_sampling(ppg, roi_samples, upSamplingRateFactor)
    #     return new_time, new_gsr, new_ecg, new_ppg

    # def _up_sampling(self, data, roi_samples, upSamplingRateFactor):
    #     new_data = np.zeros(roi_samples * upSamplingRateFactor)
    #     for i in range(roi_samples):
    #         new_data[i * upSamplingRateFactor:(i + 1) * upSamplingRateFactor] = data[i]

    # def _crop_data(self, data, fs):
    #     roi_samples = int(fs * self.prediction_window_sec)                
    #     return data[0:roi_samples]

    def get_features(self):
        """
        Returns the features queue.
        This can be used to retrieve the features for further processing or analysis.
        """
        with self.lock:
            return self.features.get()
