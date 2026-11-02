import os
import json

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ============================================================
# FILE SETTINGS
# ============================================================

INPUT_FILE = "data/emg_processed.csv"

OUTPUT_FILE = "data/emg_commands.csv"

CALIBRATION_FILE = "data/emg_calibration.json"


# ============================================================
# SAMPLING SETTINGS
# ============================================================

# Module 1 measured approximately 500 samples/sec.
SAMPLE_RATE = 500


# ============================================================
# CLASSIFICATION SETTINGS
# ============================================================

# 100 samples at 500 Hz = 0.20 seconds
#
# A command must remain valid for approximately 200 ms
# before it is accepted.
CONFIRMATION_SAMPLES = 100


# Smooth the RMS signal.
#
# 10 samples / 500 Hz = 20 ms
SMOOTHING_WINDOW = 10


# One side must be at least 1.25 times stronger than
# the opposite side to produce a directional command.
DOMINANCE_RATIO = 1.25


# ============================================================
# CALIBRATION SETTINGS
# ============================================================

BASELINE_PERCENTILE = 30

ACTIVE_PERCENTILE = 95

# Activation threshold is positioned 35% between
# baseline and active level.
THRESHOLD_POSITION = 0.35


# Release threshold is below activation threshold.
#
# This creates hysteresis and prevents rapid switching.
RELEASE_POSITION = 0.70


# ============================================================
# LOAD DATA
# ============================================================

def load_data():

    if not os.path.exists(INPUT_FILE):

        raise FileNotFoundError(
            f"Input file not found: {INPUT_FILE}"
        )

    df = pd.read_csv(
        INPUT_FILE
    )

    required_columns = [
        "timestamp",
        "left_rms",
        "right_rms"
    ]

    for column in required_columns:

        if column not in df.columns:

            raise ValueError(
                f"Missing required column: {column}"
            )

    left = pd.to_numeric(
        df["left_rms"],
        errors="coerce"
    ).values

    right = pd.to_numeric(
        df["right_rms"],
        errors="coerce"
    ).values

    if np.isnan(left).any():

        raise ValueError(
            "LEFT RMS contains invalid values."
        )

    if np.isnan(right).any():

        raise ValueError(
            "RIGHT RMS contains invalid values."
        )

    return df, left, right


# ============================================================
# SMOOTH RMS
# ============================================================

def smooth_signal(signal):

    window = (
        np.ones(SMOOTHING_WINDOW)
        / SMOOTHING_WINDOW
    )

    return np.convolve(
        signal,
        window,
        mode="same"
    )


# ============================================================
# CALCULATE CALIBRATION
# ============================================================

def calculate_calibration(signal):

    signal = np.asarray(
        signal,
        dtype=float
    )

    baseline = np.percentile(
        signal,
        BASELINE_PERCENTILE
    )

    active = np.percentile(
        signal,
        ACTIVE_PERCENTILE
    )

    # Prevent invalid calibration
    if active <= baseline:

        active = baseline + 1.0

    # --------------------------------------------------------
    # ACTIVATION THRESHOLD
    # --------------------------------------------------------

    threshold = (
        baseline
        + THRESHOLD_POSITION
        * (active - baseline)
    )

    # --------------------------------------------------------
    # RELEASE THRESHOLD
    # --------------------------------------------------------

    release_threshold = (
        baseline
        + RELEASE_POSITION
        * (threshold - baseline)
    )

    return {

        "baseline": float(
            baseline
        ),

        "active_level": float(
            active
        ),

        "threshold": float(
            threshold
        ),

        "release_threshold": float(
            release_threshold
        )
    }


# ============================================================
# CLASSIFY EMG
# ============================================================

def classify_signal(
    left,
    right,
    left_cal,
    right_cal
):

    commands = []

    # Current accepted command
    current_command = "STOP"

    # Candidate command waiting for confirmation
    pending_command = None

    # Number of consecutive samples supporting candidate
    pending_count = 0

    for left_value, right_value in zip(
        left,
        right
    ):

        # ----------------------------------------------------
        # CHECK ACTIVATION
        # ----------------------------------------------------

        left_active = (
            left_value
            >= left_cal["threshold"]
        )

        right_active = (
            right_value
            >= right_cal["threshold"]
        )

        # ----------------------------------------------------
        # CHECK RELEASE
        # ----------------------------------------------------

        left_released = (
            left_value
            < left_cal["release_threshold"]
        )

        right_released = (
            right_value
            < right_cal["release_threshold"]
        )

        # ----------------------------------------------------
        # DETERMINE REQUESTED COMMAND
        # ----------------------------------------------------

        requested_command = "STOP"

        # ----------------------------------------------------
        # SAFETY CONDITION
        #
        # Both muscles strongly active
        # -> STOP
        # ----------------------------------------------------

        if left_active and right_active:

            requested_command = "STOP"

        # ----------------------------------------------------
        # LEFT
        # ----------------------------------------------------

        elif left_active:

            if (
                left_value
                >= right_value * DOMINANCE_RATIO
            ):

                requested_command = "LEFT"

        # ----------------------------------------------------
        # RIGHT
        # ----------------------------------------------------

        elif right_active:

            if (
                right_value
                >= left_value * DOMINANCE_RATIO
            ):

                requested_command = "RIGHT"

        # ----------------------------------------------------
        # NOTHING STRONG ENOUGH
        # ----------------------------------------------------

        else:

            requested_command = "STOP"

        # ====================================================
        # HYSTERESIS
        # ====================================================

        # If currently LEFT, don't immediately drop LEFT
        # because of a tiny fluctuation.
        if current_command == "LEFT":

            if (
                not left_released
                and requested_command != "RIGHT"
            ):

                requested_command = "LEFT"

        # If currently RIGHT, don't immediately drop RIGHT
        # because of a tiny fluctuation.
        elif current_command == "RIGHT":

            if (
                not right_released
                and requested_command != "LEFT"
            ):

                requested_command = "RIGHT"

        # ====================================================
        # COMMAND CONFIRMATION
        # ====================================================

        if requested_command == pending_command:

            pending_count += 1

        else:

            pending_command = (
                requested_command
            )

            pending_count = 1

        # ----------------------------------------------------
        # ACCEPT COMMAND ONLY AFTER 100 SAMPLES
        # ----------------------------------------------------

        if (
            pending_count
            >= CONFIRMATION_SAMPLES
        ):

            current_command = (
                pending_command
            )

            pending_count = 0

        # ----------------------------------------------------
        # SAVE CURRENT COMMAND
        # ----------------------------------------------------

        commands.append(
            current_command
        )

    return commands


# ============================================================
# SAVE CALIBRATION
# ============================================================

def save_calibration(
    left_cal,
    right_cal
):

    calibration = {

        "sample_rate": SAMPLE_RATE,

        "confirmation_samples":
            CONFIRMATION_SAMPLES,

        "confirmation_time_seconds":
            CONFIRMATION_SAMPLES
            / SAMPLE_RATE,

        "smoothing_window_samples":
            SMOOTHING_WINDOW,

        "dominance_ratio":
            DOMINANCE_RATIO,

        "left":
            left_cal,

        "right":
            right_cal
    }

    # "w" means overwrite existing JSON file.
    with open(
        CALIBRATION_FILE,
        "w"
    ) as file:

        json.dump(
            calibration,
            file,
            indent=4
        )


# ============================================================
# COMMAND SUMMARY
# ============================================================

def print_command_summary(
    commands
):

    total = len(commands)

    left_count = commands.count(
        "LEFT"
    )

    right_count = commands.count(
        "RIGHT"
    )

    stop_count = commands.count(
        "STOP"
    )

    print()
    print("=" * 70)
    print("COMMAND SUMMARY")
    print("=" * 70)

    print(
        f"LEFT samples  : {left_count}"
    )

    print(
        f"RIGHT samples : {right_count}"
    )

    print(
        f"STOP samples  : {stop_count}"
    )

    print(
        f"Total samples : {total}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("MODULE 3 - EMG CLASSIFICATION & CALIBRATION")
    print("=" * 70)

    print()

    # ========================================================
    # LOAD DATA
    # ========================================================

    print(
        "Loading processed EMG..."
    )

    df, left_rms, right_rms = load_data()

    print(
        f"Samples loaded: {len(df)}"
    )

    # ========================================================
    # RECORDING INFORMATION
    # ========================================================

    timestamps = pd.to_numeric(
        df["timestamp"],
        errors="coerce"
    ).values

    actual_duration = (
        timestamps[-1]
        - timestamps[0]
    )

    print(
        f"Recording duration: "
        f"{actual_duration:.3f} seconds"
    )

    print(
        f"Processing sample rate: "
        f"{SAMPLE_RATE} Hz"
    )

    print(
        f"Command confirmation: "
        f"{CONFIRMATION_SAMPLES} samples"
    )

    print(
        f"Confirmation time: "
        f"{CONFIRMATION_SAMPLES / SAMPLE_RATE:.3f} seconds"
    )

    # ========================================================
    # SMOOTHING
    # ========================================================

    print()
    print(
        "Smoothing RMS signals..."
    )

    left_smooth = smooth_signal(
        left_rms
    )

    right_smooth = smooth_signal(
        right_rms
    )

    # ========================================================
    # CALIBRATION
    # ========================================================

    print(
        "Calculating LEFT calibration..."
    )

    left_cal = calculate_calibration(
        left_smooth
    )

    print(
        "Calculating RIGHT calibration..."
    )

    right_cal = calculate_calibration(
        right_smooth
    )

    # ========================================================
    # DISPLAY CALIBRATION
    # ========================================================

    print()
    print("=" * 70)
    print("CALIBRATION RESULTS")
    print("=" * 70)

    print()
    print("LEFT")
    print("----")

    print(
        f"Baseline          : "
        f"{left_cal['baseline']:.2f}"
    )

    print(
        f"Active level      : "
        f"{left_cal['active_level']:.2f}"
    )

    print(
        f"Activation        : "
        f"{left_cal['threshold']:.2f}"
    )

    print(
        f"Release           : "
        f"{left_cal['release_threshold']:.2f}"
    )

    print()
    print("RIGHT")
    print("-----")

    print(
        f"Baseline          : "
        f"{right_cal['baseline']:.2f}"
    )

    print(
        f"Active level      : "
        f"{right_cal['active_level']:.2f}"
    )

    print(
        f"Activation        : "
        f"{right_cal['threshold']:.2f}"
    )

    print(
        f"Release           : "
        f"{right_cal['release_threshold']:.2f}"
    )

    # ========================================================
    # CLASSIFICATION
    # ========================================================

    print()
    print(
        "Classifying EMG commands..."
    )

    commands = classify_signal(
        left_smooth,
        right_smooth,
        left_cal,
        right_cal
    )

    # ========================================================
    # SAVE FILES
    # ========================================================

    os.makedirs(
        "data",
        exist_ok=True
    )

    save_calibration(
        left_cal,
        right_cal
    )

    df["left_rms_smooth"] = (
        left_smooth
    )

    df["right_rms_smooth"] = (
        right_smooth
    )

    df["command"] = commands

    df.to_csv(
        OUTPUT_FILE,
        index=False
    )

    # ========================================================
    # SUMMARY
    # ========================================================

    print_command_summary(
        commands
    )

    print()

    print(
        f"Command output:"
        f" {OUTPUT_FILE}"
    )

    print(
        f"Calibration file:"
        f" {CALIBRATION_FILE}"
    )

    # ========================================================
    # CREATE TIME AXIS
    # ========================================================

    # Use the actual recorded timestamps rather than
    # assuming the recording started at time zero.

    time_axis = (
        timestamps
        - timestamps[0]
    )

    # ========================================================
    # CLASSIFICATION GRAPH
    # ========================================================

    plt.figure(
        figsize=(14, 7)
    )

    plt.plot(
        time_axis,
        left_smooth,
        label="LEFT RMS"
    )

    plt.plot(
        time_axis,
        right_smooth,
        label="RIGHT RMS"
    )

    # --------------------------------------------------------
    # THRESHOLDS
    # --------------------------------------------------------

    plt.axhline(
        left_cal["threshold"],
        linestyle="--",
        label="LEFT activation"
    )

    plt.axhline(
        right_cal["threshold"],
        linestyle="--",
        label="RIGHT activation"
    )

    plt.axhline(
        left_cal["release_threshold"],
        linestyle=":",
        label="LEFT release"
    )

    plt.axhline(
        right_cal["release_threshold"],
        linestyle=":",
        label="RIGHT release"
    )

    # ========================================================
    # SHADE COMMAND AREAS
    # ========================================================

    if len(commands) > 0:

        previous_command = commands[0]

        start_index = 0

        for i in range(
            1,
            len(commands)
        ):

            if commands[i] != previous_command:

                if previous_command != "STOP":

                    plt.axvspan(
                        time_axis[start_index],
                        time_axis[i],
                        alpha=0.15
                    )

                start_index = i

                previous_command = (
                    commands[i]
                )

        # ----------------------------------------------------
        # LAST COMMAND
        # ----------------------------------------------------

        if previous_command != "STOP":

            plt.axvspan(
                time_axis[start_index],
                time_axis[-1],
                alpha=0.15
            )

    # ========================================================
    # GRAPH LABELS
    # ========================================================

    plt.xlabel(
        "Time (seconds)"
    )

    plt.ylabel(
        "RMS"
    )

    plt.title(
        "Module 3 - EMG Command Classification"
    )

    plt.legend()

    plt.grid()

    plt.tight_layout()

    # ========================================================
    # DISPLAY
    # ========================================================

    print()
    print(
        "Displaying classification graph..."
    )

    plt.show()

    # ========================================================
    # FINISH
    # ========================================================

    print()
    print("=" * 70)
    print(
        "MODULE 3 COMPLETED SUCCESSFULLY"
    )
    print("=" * 70)


# ============================================================
# PROGRAM ENTRY
# ============================================================

if __name__ == "__main__":

    main()