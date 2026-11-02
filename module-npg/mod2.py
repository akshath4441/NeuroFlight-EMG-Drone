import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scipy.signal import butter
from scipy.signal import sosfiltfilt
from scipy.signal import iirnotch
from scipy.signal import filtfilt


# ============================================================
# FILE SETTINGS
# ============================================================

INPUT_FILE = "data/emg_raw.csv"
OUTPUT_FILE = "data/emg_processed.csv"


# ============================================================
# NPG LITE SAMPLING SETTINGS
# ============================================================

# IMPORTANT:
# Module 1 measured approximately 500 samples/sec.
SAMPLE_RATE = 500


# ============================================================
# EMG FILTER SETTINGS
# ============================================================

# Typical useful EMG frequency range for this project
LOW_CUTOFF = 20
HIGH_CUTOFF = 150

# Electrical mains interference
NOTCH_FREQUENCY = 50
NOTCH_Q = 30

# RMS window
# 50 samples at 500 Hz = 100 ms
RMS_WINDOW = 50


# ============================================================
# BANDPASS FILTER
# ============================================================

def bandpass_filter(signal):

    nyquist = SAMPLE_RATE / 2

    if HIGH_CUTOFF >= nyquist:

        raise ValueError(
            "HIGH_CUTOFF must be below Nyquist frequency."
        )

    sos = butter(
        4,
        [LOW_CUTOFF, HIGH_CUTOFF],
        btype="bandpass",
        fs=SAMPLE_RATE,
        output="sos"
    )

    return sosfiltfilt(
        sos,
        signal
    )


# ============================================================
# 50 Hz NOTCH FILTER
# ============================================================

def notch_filter(signal):

    b, a = iirnotch(
        NOTCH_FREQUENCY,
        NOTCH_Q,
        SAMPLE_RATE
    )

    return filtfilt(
        b,
        a,
        signal
    )


# ============================================================
# COMPLETE EMG PROCESSING
# ============================================================

def process_signal(signal):

    signal = np.asarray(
        signal,
        dtype=float
    )

    # --------------------------------------------------------
    # REMOVE DC OFFSET
    # --------------------------------------------------------

    signal = signal - np.mean(signal)

    # --------------------------------------------------------
    # BANDPASS FILTER
    # --------------------------------------------------------

    signal = bandpass_filter(
        signal
    )

    # --------------------------------------------------------
    # REMOVE 50 Hz MAINS NOISE
    # --------------------------------------------------------

    signal = notch_filter(
        signal
    )

    return signal


# ============================================================
# RMS CALCULATION
# ============================================================

def calculate_rms(signal):

    squared = signal ** 2

    window = (
        np.ones(RMS_WINDOW)
        / RMS_WINDOW
    )

    rms = np.sqrt(
        np.convolve(
            squared,
            window,
            mode="same"
        )
    )

    return rms


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("MODULE 2 - EMG SIGNAL PROCESSING")
    print("=" * 70)

    print()

    # ========================================================
    # CHECK INPUT FILE
    # ========================================================

    if not os.path.exists(INPUT_FILE):

        print(
            "ERROR: Raw EMG file not found."
        )

        print(
            f"Expected: {INPUT_FILE}"
        )

        print(
            "Run Module 1 first."
        )

        return

    # ========================================================
    # LOAD DATA
    # ========================================================

    print(
        "Loading raw EMG data..."
    )

    df = pd.read_csv(
        INPUT_FILE
    )

    if len(df) == 0:

        print(
            "ERROR: No samples found."
        )

        return

    print(
        f"Samples loaded: {len(df)}"
    )

    # ========================================================
    # CHECK COLUMNS
    # ========================================================

    required_columns = [
        "timestamp",
        "counter",
        "left_emg",
        "right_emg"
    ]

    for column in required_columns:

        if column not in df.columns:

            print(
                f"ERROR: Missing column: {column}"
            )

            return

    # ========================================================
    # LOAD LEFT / RIGHT EMG
    # ========================================================

    left_raw = pd.to_numeric(
        df["left_emg"],
        errors="coerce"
    ).values

    right_raw = pd.to_numeric(
        df["right_emg"],
        errors="coerce"
    ).values

    if np.isnan(left_raw).any():

        print(
            "ERROR: Invalid LEFT EMG values."
        )

        return

    if np.isnan(right_raw).any():

        print(
            "ERROR: Invalid RIGHT EMG values."
        )

        return

    # ========================================================
    # MEASURE ACTUAL DURATION
    # ========================================================

    timestamps = pd.to_numeric(
        df["timestamp"],
        errors="coerce"
    ).values

    actual_duration = (
        timestamps[-1]
        - timestamps[0]
    )

    actual_sample_rate = (
        (len(df) - 1)
        / actual_duration
    )

    print()
    print("RECORDING INFORMATION")
    print("----------------------")

    print(
        f"Samples             : {len(df)}"
    )

    print(
        f"Duration            : "
        f"{actual_duration:.3f} seconds"
    )

    print(
        f"Measured sample rate: "
        f"{actual_sample_rate:.2f} Hz"
    )

    print(
        f"Processing sample rate: "
        f"{SAMPLE_RATE} Hz"
    )

    # ========================================================
    # PROCESS LEFT EMG
    # ========================================================

    print()
    print(
        "Processing LEFT EMG..."
    )

    left_filtered = process_signal(
        left_raw
    )

    left_rms = calculate_rms(
        left_filtered
    )

    # ========================================================
    # PROCESS RIGHT EMG
    # ========================================================

    print(
        "Processing RIGHT EMG..."
    )

    right_filtered = process_signal(
        right_raw
    )

    right_rms = calculate_rms(
        right_filtered
    )

    # ========================================================
    # ADD PROCESSED DATA
    # ========================================================

    df["left_filtered"] = (
        left_filtered
    )

    df["left_rms"] = (
        left_rms
    )

    df["right_filtered"] = (
        right_filtered
    )

    df["right_rms"] = (
        right_rms
    )

    # ========================================================
    # SAVE PROCESSED FILE
    # ========================================================

    os.makedirs(
        "data",
        exist_ok=True
    )

    df.to_csv(
        OUTPUT_FILE,
        index=False
    )

    # ========================================================
    # PRINT STATISTICS
    # ========================================================

    print()
    print("=" * 70)
    print("EMG PROCESSING COMPLETE")
    print("=" * 70)

    print()

    print(
        f"Output file: {OUTPUT_FILE}"
    )

    print()

    print("LEFT EMG")
    print("--------")

    print(
        f"Raw minimum : "
        f"{left_raw.min():.2f}"
    )

    print(
        f"Raw maximum : "
        f"{left_raw.max():.2f}"
    )

    print(
        f"RMS minimum : "
        f"{left_rms.min():.4f}"
    )

    print(
        f"RMS maximum : "
        f"{left_rms.max():.4f}"
    )

    print(
        f"RMS mean    : "
        f"{left_rms.mean():.4f}"
    )

    print()

    print("RIGHT EMG")
    print("---------")

    print(
        f"Raw minimum : "
        f"{right_raw.min():.2f}"
    )

    print(
        f"Raw maximum : "
        f"{right_raw.max():.2f}"
    )

    print(
        f"RMS minimum : "
        f"{right_rms.min():.4f}"
    )

    print(
        f"RMS maximum : "
        f"{right_rms.max():.4f}"
    )

    print(
        f"RMS mean    : "
        f"{right_rms.mean():.4f}"
    )

    # ========================================================
    # CREATE TIME AXIS
    # ========================================================

    time_axis = np.arange(
        len(df)
    ) / SAMPLE_RATE

    # ========================================================
    # GRAPH 1 - RAW EMG
    # ========================================================

    plt.figure(
        figsize=(12, 5)
    )

    plt.plot(
        time_axis,
        left_raw,
        label="Left raw"
    )

    plt.plot(
        time_axis,
        right_raw,
        label="Right raw"
    )

    plt.xlabel(
        "Time (seconds)"
    )

    plt.ylabel(
        "ADC value"
    )

    plt.title(
        "Raw NPG Lite EMG"
    )

    plt.legend()

    plt.grid()

    plt.tight_layout()

    # ========================================================
    # GRAPH 2 - FILTERED EMG
    # ========================================================

    plt.figure(
        figsize=(12, 5)
    )

    plt.plot(
        time_axis,
        left_filtered,
        label="Left filtered"
    )

    plt.plot(
        time_axis,
        right_filtered,
        label="Right filtered"
    )

    plt.xlabel(
        "Time (seconds)"
    )

    plt.ylabel(
        "Filtered EMG"
    )

    plt.title(
        "Filtered EMG - 20 to 150 Hz"
    )

    plt.legend()

    plt.grid()

    plt.tight_layout()

    # ========================================================
    # GRAPH 3 - RMS
    # ========================================================

    plt.figure(
        figsize=(12, 5)
    )

    plt.plot(
        time_axis,
        left_rms,
        label="LEFT EMG RMS"
    )

    plt.plot(
        time_axis,
        right_rms,
        label="RIGHT EMG RMS"
    )

    plt.xlabel(
        "Time (seconds)"
    )

    plt.ylabel(
        "RMS"
    )

    plt.title(
        "Muscle Contraction Detection"
    )

    plt.legend()

    plt.grid()

    plt.tight_layout()

    # ========================================================
    # SHOW GRAPHS
    # ========================================================

    print()
    print(
        "Displaying EMG graphs..."
    )

    plt.show()

    # ========================================================
    # FINISH
    # ========================================================

    print()
    print("=" * 70)
    print(
        "MODULE 2 COMPLETED SUCCESSFULLY"
    )
    print("=" * 70)


# ============================================================
# PROGRAM ENTRY
# ============================================================

if __name__ == "__main__":

    main()