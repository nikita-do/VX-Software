# Vital-X Software

Vital-X streams ECG, PPG, and EDA/GSR measurements to a Python backend over MQTT. The backend processes the incoming signals, estimates a pain level, and stores measurements for monitoring and later review.

This repository contains the server backend and presentation materials. The project describes a mobile-friendly web interface hosted separately; its source code is  present `software/vitalx_site/`.

## Demo

[Open or download the demo video](https://dvn-resume.vercel.app/assets/projects/vitallog/demo.mp4) (`assets/output.mp4`).

## System Overview

The device sends CBOR-encoded data through an MQTT broker. The backend subscribes to device topics, decodes and validates packets, and passes the signal batches through preprocessing and pain assessment. Raw and processed signals, extracted features, and pain estimates are written to InfluxDB. Pain and pulse-rate estimates are also published over MQTT. When measurement stops, the logger exports processed data to CSV and attempts an optional Google Drive upload; Drive upload is not verified as ready to use without additional setup.

![Vital-X backend software architecture and processing flow](assets/software-architecture.png)

The MQTT topic map below shows the device, server, and client communication.

![Vital-X MQTT topic map](assets/mqtt-topic.png)

## Remote Device Control

The device is controlled through the [Vital-X web interface](https://vitalx-site.vercel.app/). The device-specific URLs is specified in the `?device=DEVICE_ID` query parameter; replace `DEVICE_ID` with the identifier of the device to control. The interface is used to check device status, submit user information and location, and start or stop data acquisition. Its source code is included but hosted in a separate repository.

## Backend Pipeline

The backend code is in [`software/ServerBackend/`](software/ServerBackend/):

1. `mqtt_subscriber.py` connects to the broker, tracks device status and configuration, decodes CBOR messages, and receives user information.
2. `packet_processor.py` checks packet fields and sample lengths, pads or truncates malformed batch lengths, and handles missing packet IDs. A single missing packet is interpolated; multiple missing packets are represented as missing data.
3. `data_processor.py` converts GSR readings to conductance, filters ECG, PPG, and GSR, estimates pulse rate, and prepares prediction windows.
4. `pain_assessor.py` extracts GSR and HRV features with NeuroKit2 and applies the saved scaler, PCA transform, and voting-classifier model.
5. `database_logger.py` writes raw signals, processed signals, features, and pain estimates to InfluxDB. At the end of a measurement, it exports processed data to CSV and optionally uploads it to Google Drive.
6. `main.py` configures and starts the MQTT subscriber, packet processor, data processor, and database logger.

The prediction window is configured as 5.5 seconds in `main.py`; the thesis describes predictions approximately every five seconds. The project describes the classifier as a five-class ensemble. Classifier training is outside this project's scope.

## Signal Processing and Pain Assessment

The processing below follows the server flow in the thesis (Software Design, p. 18; Signal Preprocessing, p. 22), with implementation-specific settings taken from `data_processor.py` and `data_processor_filters.py`.

### Packet and Signal Preparation

The packet processor checks that incoming `IR`, `RED`, `ECG`, and `GSR` arrays have the expected lengths. The data processor then creates a timestamp for each sample using the device packet time and sampling rate.

The reflective PPG sensor produces inverted waveforms. The backend combines the two optical channels as:

$$
PPG_{avg} = -\frac{IR + RED}{2}
$$

For GSR, the backend converts the sensor voltage to conductance using the voltage-divider relationship implemented in `data_processor.py`:

$$
G_{\mu S} = \frac{10^6}{100{,}000\left(\frac{6600}{V_{mV}} - 1\right)}
$$

Here, the implementation uses a 100 kΩ reference resistance and 6600 mV in the divider expression; multiplying by $10^6$ converts siemens to microsiemens. Conductance is used because it represents the inverse of skin resistance and changes with sweat-related skin response.

### Filter Methodology

The project explains the filter choices as removing slow baseline drift, mains-frequency interference, and faster noise such as motion artifacts while retaining the physiological signal.

| Signal | Method described | Why | Current backend implementation |
| --- | --- | --- | --- |
| ECG | 0.5 Hz high-pass IIR, followed by a 50 Hz (Vietnam) or 60 Hz (Taiwan) FIR notch | Remove baseline drift and local power-line interference | 2nd-order Butterworth high-pass IIR at 0.5 Hz, then a 1025-tap FIR notch. `VN` selects 50 Hz; `TW` and unknown location codes select 60 Hz. |
| PPG | Form the inverted IR/RED average, then 0.5 Hz high-pass IIR and 10 Hz low-pass FIR | Remove baseline wander and attenuate high-frequency noise, including motion artifacts | 2nd-order Butterworth high-pass IIR at 0.5 Hz, then 201-tap FIR low-pass at 10 Hz. |
| GSR/EDA | 3 Hz low-pass FIR | Smooth faster fluctuations while preserving the slower electrodermal response | Convert voltage to conductance, then apply a stateful 513-tap FIR low-pass at 3 Hz. |

The FIR filter states are retained between successive data windows to avoid reinitializing filters at every window boundary. 

#### Why the Backend Uses IIR and FIR

The 2nd-order Butterworth IIR high-pass removes baseline drift efficiently with few coefficients, which suits streaming, but has nonlinear phase. Symmetric FIR low-pass and notch filters are stable and linear-phase, but their tap counts increase computation and delay. At 512 Hz, their group delays are about 1 s for ECG, 195 ms for PPG, and 500 ms for GSR; timestamps are not delay-compensated. 

### Features and Pain Classification

Within `pain_assessor.py`, EDA is decomposed into tonic/phasic components, and the GSR feature set is calculated from the phasic component: peak-to-peak amplitude, maximum, skewness, kurtosis, standard deviation, range, interquartile range, coefficient of variation (SDMN), and standard deviation of successive differences (SDSD).

ECG R-peaks are detected and time-domain HRV features are computed: MeanNN, SDNN, RMSSD, SDSD, and SDRMSSD. These signal features are scaled, projected through the saved PCA transform, and passed to the saved voting-classifier model for each 5.5-second prediction window. Its predicted pain class is published over MQTT and, along with the raw and processed signals and extracted features, written to InfluxDB.

## Run the Backend

### Requirements

- Python and the packages in [`software/ServerBackend/requirements.txt`](software/ServerBackend/requirements.txt)
- An MQTT broker and a Vital-X device publishing the expected device topics
- A reachable InfluxDB instance, organization, bucket, and API token
- The trained model files: `pain_votingclassifier_J.pkl`, `scaler.pkl`, and `pca.pkl`
- The MQTT TLS certificate configured for your broker
- Google Drive OAuth credentials only if Drive export is required

The model files and deployment credentials are not included in this repository. MQTT username/password and the InfluxDB token must be provided through environment variables; the backend exits with an error if they are missing. Configure machine-specific certificate and model paths before running. Never commit live credentials, and rotate any credentials that may already have been exposed in repository history.

### Install

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r software/ServerBackend/requirements.txt
```

Set the MQTT credentials and InfluxDB token in the environment. For example:

```bash
export MQTT_BROKER="your-mqtt-host"
export MQTT_PORT="8883"
export MQTT_USERNAME="your-mqtt-username"
export MQTT_PASSWORD="your-mqtt-password"
export INFLUXDB_TOKEN="your-influxdb-token"
```

Before starting the service, update the InfluxDB URL, organization, and bucket, and point the certificate and model paths in `software/ServerBackend/main.py` to files available on your machine. The code specifies a 512 Hz sampling rate for compatibility with the prediction model.

#### Optional Google Drive Setup

For Drive export, create OAuth client credentials in the Google Cloud Console and enable the Google Drive API. By default, put the downloaded OAuth client JSON at `software/ServerBackend/resources/credentials.json`; the OAuth token is created at `software/ServerBackend/resources/token.json` after the first authorization. Both filenames are ignored by Git. To store either file elsewhere, configure these variables before starting the backend:

```bash
export GOOGLE_CREDENTIALS_PATH="/path/to/google-oauth-client.json"
export GOOGLE_TOKEN_PATH="/path/to/vitalx-drive-token.json"
```

The token parent directory is created automatically. Keep custom credential and token files outside the repository or add their paths to `.gitignore`. Drive authentication alone does not complete the current upload flow: folder initialization is disabled in `database_logger.py`, so enable its `get_or_create_folder()` call before expecting uploads to work.

Start the backend from its directory so its local module imports resolve:

```bash
cd software/ServerBackend
python main.py
```

Stop the service with `Ctrl+C`. The logger writes exported CSV files to `software/ServerBackend/data/`.

## Limitation

The processed signal shows a peak at the beginning of each prediction window. The backend collects fixed, non-overlapping 5.5-second blocks, equivalent to rectangular segmentation, without tapering the signal at block edges. The repeated peak may be a boundary or signal artifact; testing a different window function or overlapping blocks may reduce it, but this has not been verified. Filter state persists across blocks, so the peak should not be assumed to come from resetting the filters. Windowing changes the model input and should be evaluated with recorded data before use.

This is a research prototype, not a clinically validated medical device. The thesis reports that pain-prediction accuracy has not been validated in a clinical setting and identifies ECG lead-off monitoring and real-time pain alerts as unimplemented features.

## See the paper
Ha, Minh-Khue, et al. "VitalLog: Development of a Compact Multimodal Physiological Signal Acquisition System for Tele-Monitoring Applications." Journal of Physics: Conference Series. Vol. 3180. No. 1. IOP Publishing, 2026.