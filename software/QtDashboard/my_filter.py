from scipy.signal import butter, filtfilt, iirnotch, lfilter
import pywt
import numpy as np

def lowpass_filter(data, cutoff=0.5, fs=100, order=4):
    b, a = butter(order, cutoff, btype='lowpass', fs=fs)
    return filtfilt(b, a, data)

def highpass_filter(data, fs, cutoff=0.5, order=4):
    """
    High-pass filters data using a Butterworth filter.

    Parameters:
        data (list or np.ndarray): Raw signal.
        cutoff (float): Cutoff frequency (Hz).
        fs (float): Sampling rate (Hz).
        order (int): Filter order.

    Returns:
        list: Filtered signal.
    """
    b, a = butter(order, cutoff, btype='highpass', fs = fs)
    return filtfilt(b, a, data)

def bandpass_filter(data, fs, lowcut=0.5, highcut=40, order=4):
    """
    Band-pass filters data using a Butterworth filter.

    Parameters:
        data (list or np.ndarray): Raw signal.
        lowcut (float): Low cutoff frequency (Hz).
        highcut (float): High cutoff frequency (Hz).
        fs (float): Sampling rate (Hz).
        order (int): Filter order.

    Returns:
        list: Filtered signal.
    """
    nyq = 0.5 * fs
    b, a = butter(order, [lowcut / nyq, highcut / nyq], btype='band')
    return lfilter(b, a, data)

def apply_notch_filter(data, fs, notch_freq=50, Q=30):
    """
    Apply a notch filter to remove a specific frequency.

    Parameters:
        data (list or np.ndarray): Input signal.
        fs (int): Sampling rate in Hz.
        notch_freq (float): Notch frequency to remove (default = 50 Hz).
        Q (float): Quality factor (default = 30). Higher = narrower notch.

    Returns:
        list: Filtered signal.
    """
    b, a = iirnotch(w0=notch_freq, Q=Q, fs=fs)
    return filtfilt(b, a, data)

def wavelet_denoise(data, wavelet='sym4', level=3):
    """
    Perform wavelet denoising on the input signal.

    Parameters:
        data (list or np.ndarray): Input signal.
        wavelet (str): Wavelet type (default = 'sym4').
        level (int): Decomposition level (default = 3).

    Returns:
        list: Denoised signal.
    """
    coeffs = pywt.wavedec(data, wavelet, level=level)
    thresholded_coeffs = [coeffs[0]]  # Keep approximation

    for i in range(1, len(coeffs)):
        sigma = np.median(np.abs(coeffs[i])) / 0.6745
        threshold = sigma * np.sqrt(2 * np.log(len(coeffs[i])))
        thresholded = pywt.threshold(coeffs[i], threshold, mode='soft')
        thresholded_coeffs.append(thresholded)

    return pywt.waverec(thresholded_coeffs, wavelet)[:len(data)]
