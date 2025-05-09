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

def extract_feature(file_path):
    try:
        data = pd.read_csv(file_path, header=2)
        ecgdata = data['ECG']
        gsrdata = data['GSR']
        time = data['Time(us)']

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
            print(f"gsr peaks error {file_path}: {e}")


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

def preload_model():
    try:
        model = joblib.load("pain_votingclassifier_J.pkl")
        scaler = joblib.load("scaler.pkl")
        pca = joblib.load("pca.pkl")
        return model, scaler, pca
    except FileNotFoundError as e:
        print('Some of these files are missing: pain_votingclassifier_J.pkl, scaler.pkl, pca.pkl')
        print('Please ensure that all of these files are present in this directory')
        quit()
        #return None, None, None

def predict(file_path):
    features = extract_feature(file_path)

    if features.empty:
        print("something wrong")
    else:
        print("okok")

    features_scaled = scaler.transform(features)
    features_pca = pca.transform(features_scaled)

    predicted_label = model.predict(features_pca)
    return predicted_label[0]

def main():
    model, scaler, pca = preload_model()

    root = tk.Tk()
    root.withdraw()
    data_file_path = filedialog.askopenfilename(title="chose a csv file", filetypes=[("CSV files", "*.csv")])

    pain_level = predict(data_file_path)
    print(f"predicted pain level: {pain_level}")

if __name__ == '__main__':
    main()

