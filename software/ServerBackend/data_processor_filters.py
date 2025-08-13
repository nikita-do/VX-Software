from scipy.signal import butter, filtfilt, iirnotch, lfilter
import pywt
import numpy as np
import neurokit2 as nk

def ecg_nk_filter(data, fs, powerline=50, order=5) :
    ecg = nk.ecg_clean(data, sampling_rate=fs, method="neurokit", lowcut=0.5, highcut=40, powerline=powerline, order=order)
    return ecg

def gsr_nk_filter(data, fs):
    gsr = nk.eda_clean(data, sampling_rate=fs, method="neurokit")
    return gsr

# def powerline_filter(data, fs, powerline=50, order=4):
#     signal = nk.signal_filter(data, method="powerline", sampling_rate=fs, powerline=powerline, order=order)
#     return signal

from scipy.signal import firwin, lfilter, lfilter_zi

def firfilter_bandpass(signal, fs, cutoff, numtaps=101, zi=None):
    nyq = 0.5 * fs
    low, high = cutoff[0] / nyq, cutoff[1] / nyq
    b = firwin(numtaps, [low, high], pass_zero=False)
    if zi is None:
        zi = lfilter_zi(b, [1.0]) * signal[0]
    filtered, zf = lfilter(b, [1.0], signal, zi=zi)
    return filtered, zf

def firfilter_lowpass(signal, fs, cutoff, numtaps=101, zi=None):
    nyq = 0.5 * fs
    normalized_cutoff = cutoff / nyq
    b = firwin(numtaps, normalized_cutoff)
    if zi is None:
        zi = lfilter_zi(b, [1.0]) * signal[0]
    filtered, zf = lfilter(b, [1.0], signal, zi=zi)
    return filtered, zf

def firfilter_highpass(signal, fs, cutoff, numtaps=101, zi=None):
    nyq = 0.5 * fs
    normalized_cutoff = cutoff / nyq
    b = firwin(numtaps, normalized_cutoff, pass_zero=False)
    if zi is None:
        zi = lfilter_zi(b, [1.0]) * signal[0]
    filtered, zf = lfilter(b, [1.0], signal, zi=zi)
    return filtered, zf

def firfilter_notch(signal, fs, notch_freq, notch_width=1.0, numtaps=101, zi=None):
    nyq = 0.5 * fs
    notch_center = notch_freq / nyq
    width = notch_width / nyq
    # Create stop-band from (center - width/2) to (center + width/2)
    low = notch_center - width / 2
    high = notch_center + width / 2
    # Design FIR band-stop (notch) filter
    b = firwin(numtaps, [low, high], pass_zero=True)
    if zi is None:
        zi = lfilter_zi(b, [1.0]) * signal[0]
    filtered, zf = lfilter(b, [1.0], signal, zi=zi)
    return filtered, zf

from scipy.signal import butter, sosfilt, sosfilt_zi, iirnotch, tf2sos

def sosfilt_bandpass(signal, fs, cutoff, order, zi=None):
    nyq = 0.5 * fs
    low, high = cutoff[0] / nyq, cutoff[1] / nyq
    sos = butter(order, [low, high], btype='band', output='sos')
    if zi is None:
        zi = sosfilt_zi(sos) * signal[0]
    filtered, zf = sosfilt(sos, signal, zi=zi)
    return filtered, zf

def sosfilt_lowpass(signal, fs, cutoff, order, zi=None):
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    sos = butter(order, normal_cutoff, btype='low', output='sos')
    if zi is None:
        zi = sosfilt_zi(sos) * signal[0]
    filtered, zf = sosfilt(sos, signal, zi=zi)
    return filtered, zf

def sosfilt_notch(signal, fs, notch_freq=50.0, Q=30.0, zi=None):
    # Design IIR notch filter
    b, a = iirnotch(w0=notch_freq / (0.5 * fs), Q=Q)
    sos = tf2sos(b, a)  # Convert to second-order sections
    if zi is None:
        zi = sosfilt_zi(sos) * signal[0]
    filtered, zf = sosfilt(sos, signal, zi=zi)
    return filtered, zf

def sosfilt_highpass(signal, fs, cutoff, order, zi=None):
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    sos = butter(order, normal_cutoff, btype='high', output='sos')
    if zi is None:
        zi = sosfilt_zi(sos) * signal[0]
    filtered, zf = sosfilt(sos, signal, zi=zi)
    return filtered, zf

def lowpass_filter(data, cutoff=40, fs=100, order=4):
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
