import asyncio
import csv
import os
import struct
import time

from bleak import BleakClient


# ============================================================
# NPG LITE SETTINGS
# ============================================================

DEVICE_ADDRESS = "E4:B3:23:AF:72:B6"

DATA_CHAR_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
CONTROL_CHAR_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"

# IMPORTANT:
# We are now using REAL elapsed time.
# We are NOT assuming 250 samples/sec.
RECORD_TIME = 30

OUTPUT_FILE = "data/emg_raw.csv"


# ============================================================
# DATA STORAGE
# ============================================================

data_log = []

packet_count = 0
sample_count = 0

last_counter = None
missing_samples = 0

recording = False


# ============================================================
# PARSE BLE PACKET
# ============================================================

def parse_packet(data: bytearray):

    samples = []

    # Each sample:
    #
    # 1 byte  = sample counter
    # 2 bytes = Channel 0
    # 2 bytes = Channel 1
    # 2 bytes = Channel 2
    #
    # Total = 7 bytes/sample

    SAMPLE_SIZE = 7

    if len(data) % SAMPLE_SIZE != 0:
        print(
            f"WARNING: Unexpected packet size: "
            f"{len(data)} bytes"
        )

    complete_samples = len(data) // SAMPLE_SIZE

    for i in range(complete_samples):

        offset = i * SAMPLE_SIZE

        counter = data[offset]

        ch0 = struct.unpack(
            ">H",
            data[offset + 1:offset + 3]
        )[0]

        ch1 = struct.unpack(
            ">H",
            data[offset + 3:offset + 5]
        )[0]

        ch2 = struct.unpack(
            ">H",
            data[offset + 5:offset + 7]
        )[0]

        samples.append(
            (counter, ch0, ch1, ch2)
        )

    return samples


# ============================================================
# BLE DATA CALLBACK
# ============================================================

def handle_data(sender, data):

    global packet_count
    global sample_count
    global last_counter
    global missing_samples

    # Ignore data after recording has finished
    if not recording:
        return

    packet_count += 1

    samples = parse_packet(data)

    for counter, ch0, ch1, ch2 in samples:

        # ----------------------------------------------------
        # CHECK SAMPLE COUNTER
        # ----------------------------------------------------

        if last_counter is not None:

            expected_counter = (
                last_counter + 1
            ) % 256

            if counter != expected_counter:

                difference = (
                    counter - expected_counter
                ) % 256

                missing_samples += difference

        last_counter = counter

        # ----------------------------------------------------
        # STORE SAMPLE
        # ----------------------------------------------------

        timestamp = time.time()

        data_log.append(
            [
                timestamp,
                counter,
                ch0,
                ch1,
                ch2
            ]
        )

        sample_count += 1

    # --------------------------------------------------------
    # PROGRESS DISPLAY
    # --------------------------------------------------------

    if packet_count % 25 == 0:

        print(
            f"Samples: {sample_count:6d} | "
            f"Packets: {packet_count:5d}"
        )


# ============================================================
# MAIN
# ============================================================

async def main():

    global recording

    print("=" * 70)
    print("NPG LITE - EMG ACQUISITION")
    print("=" * 70)

    print()
    print("Channel 0 / A0 -> LEFT FOREARM")
    print("Channel 1 / A1 -> RIGHT FOREARM")
    print("Channel 2 / A2 -> UNUSED")

    print()
    print(f"Recording duration : {RECORD_TIME} seconds")
    print("Sampling rate      : determined from timestamps")
    print()
    print("Device:", DEVICE_ADDRESS)

    print()
    print("Connecting to NPG Lite...")

    try:

        async with BleakClient(
            DEVICE_ADDRESS
        ) as client:

            # =================================================
            # CONNECTION CHECK
            # =================================================

            if not client.is_connected:

                print(
                    "ERROR: Could not connect to NPG Lite."
                )

                return

            print("Connected successfully.")

            # =================================================
            # START BLE NOTIFICATIONS
            # =================================================

            try:

                await client.start_notify(
                    DATA_CHAR_UUID,
                    handle_data
                )

                print(
                    "BLE notifications started."
                )

            except Exception as error:

                print(
                    "ERROR: Could not start BLE notification."
                )

                print(error)

                return

            # =================================================
            # START NPG LITE STREAM
            # =================================================

            try:

                await client.write_gatt_char(
                    CONTROL_CHAR_UUID,
                    b"START"
                )

                print(
                    "START command sent."
                )

            except Exception as error:

                print(
                    "ERROR: Could not send START command."
                )

                print(error)

                await client.stop_notify(
                    DATA_CHAR_UUID
                )

                return

            # =================================================
            # RECORDING START
            # =================================================

            print()
            print("=" * 70)
            print("RECORDING STARTED")
            print("=" * 70)

            print()
            print("CALIBRATION PROTOCOL")
            print("--------------------")
            print("0-5 sec   : Both arms RELAXED")
            print("5-10 sec  : LEFT contractions")
            print("10-15 sec : Both arms RELAXED")
            print("15-20 sec : RIGHT contractions")
            print("20-25 sec : Both arms RELAXED")
            print("25-30 sec : LEFT / RIGHT contractions")
            print()
            print("Use moderate, repeatable contractions.")
            print("Do NOT use maximum force.")
            print()

            # -------------------------------------------------
            # START REAL-TIME RECORDING TIMER
            # -------------------------------------------------

            recording = True

            start_time = time.time()

            # -------------------------------------------------
            # RECORD FOR EXACTLY 30 REAL SECONDS
            # -------------------------------------------------

            while True:

                elapsed = time.time() - start_time

                if elapsed >= RECORD_TIME:
                    break

                await asyncio.sleep(0.01)

            # =================================================
            # STOP RECORDING
            # =================================================

            recording = False

            print()
            print(
                "30 seconds elapsed."
            )

            # =================================================
            # STOP NPG LITE
            # =================================================

            try:

                await client.write_gatt_char(
                    CONTROL_CHAR_UUID,
                    b"STOP"
                )

                print(
                    "STOP command sent."
                )

            except Exception as error:

                print(
                    "WARNING: Could not send STOP command."
                )

                print(error)

            # =================================================
            # STOP BLE NOTIFICATIONS
            # =================================================

            try:

                await client.stop_notify(
                    DATA_CHAR_UUID
                )

                print(
                    "BLE notifications stopped."
                )

            except Exception:

                pass

    except Exception as error:

        recording = False

        print()
        print("=" * 70)
        print("NPG LITE CONNECTION ERROR")
        print("=" * 70)

        print(error)

        return

    # =========================================================
    # CHECK DATA
    # =========================================================

    print()
    print("=" * 70)
    print("RECORDING FINISHED")
    print("=" * 70)

    print(
        f"Samples collected : {len(data_log)}"
    )

    print(
        f"BLE packets       : {packet_count}"
    )

    print(
        f"Missing samples   : {missing_samples}"
    )

    # =========================================================
    # CALCULATE ACTUAL RECORDING DURATION
    # =========================================================

    actual_duration = 0

    if len(data_log) >= 2:

        first_timestamp = data_log[0][0]
        last_timestamp = data_log[-1][0]

        actual_duration = (
            last_timestamp - first_timestamp
        )

    # =========================================================
    # CALCULATE ACTUAL SAMPLE RATE
    # =========================================================

    actual_sample_rate = 0

    if actual_duration > 0:

        actual_sample_rate = (
            (len(data_log) - 1)
            / actual_duration
        )

    # =========================================================
    # SAVE CSV
    # =========================================================

    if len(data_log) == 0:

        print()
        print(
            "ERROR: No EMG samples received."
        )

        return

    os.makedirs(
        "data",
        exist_ok=True
    )

    with open(
        OUTPUT_FILE,
        "w",
        newline=""
    ) as file:

        writer = csv.writer(file)

        writer.writerow(
            [
                "timestamp",
                "counter",
                "left_emg",
                "right_emg",
                "unused_ch2"
            ]
        )

        writer.writerows(
            data_log
        )

    # =========================================================
    # FINAL SUMMARY
    # =========================================================

    print()
    print("=" * 70)
    print("RECORDING SUMMARY")
    print("=" * 70)

    print(
        f"Samples saved        : {len(data_log)}"
    )

    print(
        f"BLE packets          : {packet_count}"
    )

    print(
        f"Missing samples      : {missing_samples}"
    )

    print(
        f"Measured duration    : "
        f"{actual_duration:.3f} seconds"
    )

    print(
        f"Measured sample rate : "
        f"{actual_sample_rate:.2f} samples/sec"
    )

    print(
        f"Output file          : {OUTPUT_FILE}"
    )

    print()

    if (
        29.0 <= actual_duration <= 31.0
    ):

        print(
            "SUCCESS: Recording duration is approximately 30 seconds."
        )

    else:

        print(
            "WARNING: Recording duration is outside the expected range."
        )

    print()
    print(
        "Module 1 completed successfully."
    )


# ============================================================
# PROGRAM ENTRY
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        recording = False

        print()
        print(
            "Recording interrupted by user."
        )