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

class PainAssessor:
    def __init__(self, model_path, scaler_path, pca_path, prediction_window_sec=5.5):
        try:
            self.model = joblib.load(model_path)
            self.scaler = joblib.load(scaler_path)
            self.pca = joblib.load(pca_path)
        except FileNotFoundError as e:
            print('Some of these files are missing: pain_votingclassifier_J.pkl, scaler.pkl, pca.pkl')
            print('Please ensure that all of these files are present in this directory')
            quit()

        # Region of interest in seconds
        self.prediction_window_sec = prediction_window_sec

    # def extract_feature_from_file(self, file_path):
    #     data = pd.read_csv(file_path, header=2)
    #     ecgdata = data['ECG']
    #     gsrdata = data['GSR']
    #     time = data['Time(us)']
    #     return self.extract_feature(ecgdata, gsrdata, time)

    def extract_feature(self, ecg, gsr, sampling_rate):
        try:
            # Initialize feature dictionaries
            gsr_features = {
                'gsr_amp': np.nan,
                'gsr_max': np.nan,
                'gsr_skew': np.nan,
                'gsr_kurt': np.nan,
                'gsr_sd': np.nan,
                'gsr_range': np.nan,
                'gsr_iqr': np.nan,
                'gsr_sdmn': np.nan,
                'gsr_sdsd': np.nan,
            }

            hrv_features = {
                'HRV_MeanNN': np.nan,
                'HRV_SDNN': np.nan,
                'HRV_RMSSD': np.nan,
                'HRV_SDSD': np.nan,
                'HRV_SDRMSSD': np.nan,
                'HRV_pNN50': np.nan,
            }

            # GSR features
            try:
                gsr = nk.eda_phasic(gsr, sampling_rate=sampling_rate, method='cvxeda')
                gsr_phasic = gsr['EDA_Phasic'].values

                gsr_features['gsr_skew'] = skew(gsr_phasic)
                gsr_features['gsr_kurt'] = kurtosis(gsr_phasic, fisher=False)
                gsr_features['gsr_sd'] = np.std(gsr_phasic)
                gsr_features['gsr_range'] = np.ptp(gsr_phasic)
                gsr_features['gsr_iqr'] = np.percentile(gsr_phasic, 75) - np.percentile(gsr_phasic, 25)

                window_size = 512
                if len(gsr_phasic) < window_size:
                    gsr_means = [np.mean(gsr_phasic)]
                    gsr_sds = [np.std(gsr_phasic)]
                else:
                    gsr_means = [np.mean(gsr_phasic[i:i+window_size])
                                for i in range(0, len(gsr_phasic), window_size)]
                    gsr_sds = [np.std(gsr_phasic[i:i+window_size])
                            for i in range(0, len(gsr_phasic), window_size)]

                gsr_features['gsr_sdmn'] = np.std(gsr_means)
                gsr_features['gsr_sdsd'] = np.std(gsr_sds)

            except Exception as e:
                print(f"gsr signal error: {e}")
                return pd.DataFrame()

            # ECG features
            try:
                signals, info = nk.ecg_peaks(ecg, sampling_rate=sampling_rate, correct_artifacts=True)
                peaks = info["ECG_R_Peaks"]
                if len(peaks) < 2:
                    print("Not enough ECG peaks detected.")
                    return pd.DataFrame()
                hrv = nk.hrv_time(peaks, sampling_rate=sampling_rate, show=False)

                hrv_features['HRV_MeanNN'] = hrv['HRV_MeanNN']
                hrv_features['HRV_SDNN'] = hrv['HRV_SDNN']
                hrv_features['HRV_RMSSD'] = hrv['HRV_RMSSD']
                hrv_features['HRV_SDSD'] = hrv['HRV_SDSD']
                hrv_features['HRV_pNN50'] = hrv['HRV_pNN50']
                hrv_features['HRV_SDRMSSD'] = hrv['HRV_SDRMSSD']

            except Exception as e:
                print(f"ecg signal error: {e}")
                return pd.DataFrame()

            # GSR peaks
            try:
                _, neurokit = nk.eda_peaks(gsr_phasic, sampling_rate=sampling_rate, method='neurokit')
                gsr_max_indices = neurokit['SCR_Peaks']
                num_peaks = len(gsr_max_indices)

                if num_peaks == 1:
                    gsr_features['gsr_amp'] = neurokit['SCR_Amplitude'][0]
                    gsr_features['gsr_max'] = gsr_phasic[gsr_max_indices[0]]
                elif num_peaks >= 2:
                    gsr_features['gsr_amp'] = neurokit['SCR_Amplitude'][-1]
                    gsr_features['gsr_max'] = gsr_phasic[gsr_max_indices[-1]]
                else:
                    gsr_features['gsr_amp'] = np.nan
                    gsr_features['gsr_max'] = np.nan
                    print("[DEBUG] No GSR Peak detected!")

            except Exception as e:
                print(f"gsr peaks error: {e}")
                return pd.DataFrame()

            # Assemble all features
            features = {**gsr_features, **hrv_features}
            feature_row = pd.DataFrame([features])

            return feature_row

        except Exception as e:
            print(f"feature extraction error: {e}")
            return pd.DataFrame()
        
    def predict(self, features):
        features_scaled = self.scaler.transform(features)
        features_pca = self.pca.transform(features_scaled)

        predicted_label = self.model.predict(features_pca)
        return predicted_label[0]

    # def predict_from_file(self, file_path):
    #     try:
    #         features = self.extract_feature_from_file(file_path)
    #     except Exception as e:
    #         print(e)
    #         return None
    #     return self.predict(features)
        
    def predict_from_buffer(self, preprocessed_buffers, sampling_rate) -> dict:
        """ Predicts the pain level based on the preprocessed buffers. """

        roi = int(self.prediction_window_sec * sampling_rate)
        gsr_list = list(preprocessed_buffers['gsr'])
        ecg_list = list(preprocessed_buffers['ecg'])

        # Take only the last roi samples
        ecg_segment = ecg_list[-roi:]
        gsr_segment = gsr_list[-roi:]

        # Check for None values in the ROI
        if any(val is None for val in ecg_segment) or any(val is None for val in gsr_segment):
            print("[PainAssessor] Skipping prediction due to None values in the ROI.")
            return None

        try:
            # Extract features
            features = self.extract_feature(ecg_segment, gsr_segment, sampling_rate)
            
            if isinstance(features, pd.DataFrame) and not features.empty:  # adjust this condition if necessary
                # Run prediction
                pain_level = self.predict(features)
                timestamp_ns = time.time_ns()
                print(f"[PainAssessor] Predicted pain level: {pain_level} at timestamp {timestamp_ns}")
                return {"pain_level": pain_level, "timestamp": timestamp_ns}
            else:
                print('[PainAssessor] Missing or invalid feature(s)')
                return None

        except Exception as e:
            print(e)
            return None

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
