import pandas as pd
import joblib
import tkinter as tk
from tkinter import filedialog
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report
import os
import pandas as pd
import numpy as np
import neurokit2 as nk
import cvxopt
from scipy.stats import skew, kurtosis

# Implementation according to Wien Wien
# Run this file seperately for testing:
#   python pain_assessment.py 
#
# Usage example in main() 

class PainAssessor:
    def __init__(self):
        try:
            self.model = joblib.load("pain_votingclassifier_J.pkl")
            self.scaler = joblib.load("scaler.pkl")
            self.pca = joblib.load("pca.pkl")
        except FileNotFoundError as e:
            print('Some of these files are missing: pain_votingclassifier_J.pkl, scaler.pkl, pca.pkl')
            print('Please ensure that all of these files are present in this directory')
            quit()

        # Region of interest in seconds
        self.roi_length = 5.5

    def extract_feature_from_file(self, file_path):
        data = pd.read_csv(file_path, header=2)
        ecgdata = data['ECG']
        gsrdata = data['GSR']
        time = data['Time(us)']
        return self.extract_feature(ecgdata, gsrdata, time)

    def extract_feature(self, ecg, gsr, time):
        ecgdata = ecg
        gsrdata = gsr
        try:
            gsr_amp = gsr_max = gsr_skew = gsr_kurt = gsr_sd = gsr_range = gsr_iqr = np.nan
            gsr_sdmn = gsr_sdsd = hrv_mean_nn = hrv_sdnn = hrv_rmssd = hrv_sdsd = hrv_sdrmssd = np.nan

            # gsr signal
            try:
                gsr = nk.eda_phasic(gsrdata, sampling_rate=512, method='cvxeda')
                gsr_phasic = gsr['EDA_Phasic'].values

                gsr_skew = skew(gsr_phasic)
                gsr_kurt = kurtosis(gsr_phasic)
                gsr_sd = np.std(gsr_phasic)
                gsr_range = np.ptp(gsr_phasic)
                gsr_iqr = np.percentile(gsr_phasic, 75) - np.percentile(gsr_phasic, 25)

                window_size = 512
                gsr_means = [np.mean(gsr_phasic[i:i+window_size]) for i in range(0, len(gsr_phasic), window_size)]
                gsr_sds = [np.std(gsr_phasic[i:i+window_size]) for i in range(0, len(gsr_phasic), window_size)]
                gsr_sdmn = np.std(gsr_means)
                gsr_sdsd = np.std(gsr_sds)
            except Exception as e:
                print(f"gsr signal error: {e}")
                return None

            # ecg signal
            try:
                peaks, _ = nk.ecg_peaks(ecgdata, sampling_rate=512, correct_artifacts=True)
                hrv = nk.hrv_time(peaks, sampling_rate=512, show=False)

                hrv_mean_nn = hrv['HRV_MeanNN']
                hrv_sdnn = hrv['HRV_SDNN']
                hrv_rmssd = hrv['HRV_RMSSD']
                hrv_sdsd = hrv['HRV_SDSD']
                hrv_pnn50 = hrv['HRV_pNN50']
                hrv_sdrmssd = hrv['HRV_SDRMSSD']
            except Exception as e:
                print(f"ecg signal error: {e}")
                return None

            # gsr peaks
            try:
                _, neurokit = nk.eda_peaks(gsr_phasic, sampling_rate=512, method='neurokit')
                gsr_max_indices = neurokit['SCR_Peaks']
                num_peaks = len(gsr_max_indices)

                if num_peaks == 1:
                    gsr_amp = neurokit['SCR_Amplitude'][0]
                    gsr_max = gsr_phasic[gsr_max_indices[0]]
                elif num_peaks >= 2:
                    gsr_amp = neurokit['SCR_Amplitude'][-1]
                    gsr_max = gsr_phasic[gsr_max_indices[-1]]
            except Exception as e:
                print(f"gsr peaks error: {e}")
                return None


            feature_row = pd.DataFrame([{
                'gsr_amp': gsr_amp,
                'gsr_max': gsr_max,
                'gsr_skew': gsr_skew,
                'gsr_kurt': gsr_kurt,
                'gsr_sd': gsr_sd,
                'gsr_range': gsr_range,
                'gsr_iqr': gsr_iqr,
                'gsr_sdmn': gsr_sdmn,
                'gsr_sdsd': gsr_sdsd,
                'HRV_MeanNN': hrv_mean_nn,
                'HRV_SDNN': hrv_sdnn,
                'HRV_RMSSD': hrv_rmssd,
                'HRV_SDSD': hrv_sdsd,
                'HRV_SDRMSSD': hrv_sdrmssd,
            }])

            return feature_row

        except Exception as e:
            print(f"feature extraction error from file {file_path}: {e}")
            return pd.DataFrame()

    def predict_from_file(self, file_path):
        try:
            features = self.extract_feature_from_file(file_path)
        except Exception as e:
            print(e)
            return None
        return self.predict(features)

    def predict_from_raw(self, ecg, gsr, time):
        try:
            features = self.extract_feature(ecg, gsr, time)
        except Exception as e:
            print(e)
            return None
        return self.predict(features)

    def predict(self, features):
        if isinstance(features, pd.DataFrame):
            features_scaled = self.scaler.transform(features)
            features_pca = self.pca.transform(features_scaled)

            predicted_label = self.model.predict(features_pca)
            return predicted_label[0]
        else:
            print('Missing feature(s)')
            return None

    def _up_sampling_all(self, time, gsr, ecg, ppg, current_fs, up_fs):
        upSamplingRateFactor = up_fs / current_fs
        roi_samples = int(current_fs * self.roi_length)                

        new_time = newTime = np.linspace(0, roi_length * 1000, roi_samples * upSamplingRateFactor)
        new_gsr = self.up_sampling(gsr, roi_samples, upSamplingRateFactor)
        new_ecg = self.up_sampling(ecg, roi_samples, upSamplingRateFactor)
        new_ppg = self.up_sampling(ppg, roi_samples, upSamplingRateFactor)
        return new_time, new_gsr, new_ecg, new_ppg

    def _up_sampling(self, data, roi_samples, upSamplingRateFactor):
        new_data = np.zeros(roi_samples * upSamplingRateFactor)
        for i in range(roi_samples):
            new_data[i * upSamplingRateFactor:(i + 1) * upSamplingRateFactor] = data[i]

    def _crop_data(self, data, fs):
        roi_samples = int(fs * self.roi_length)                
        return data[0:roi_samples]


if __name__ == '__main__':
    pain_assessor = PainAssessor()

    #root = tk.Tk()
    #root.withdraw()
    #data_file_path = filedialog.askopenfilename(title="chose a csv file", filetypes=[("CSV files", "*.csv")])
    data_file_path = 'data/0_30_2025-05-21_11-36-56.csv'

    pain_level = pain_assessor.predict_from_file(data_file_path)
    if pain_level != None:
        print(f"predicted pain level: {pain_level}")
    else:
        print("No emotion")

