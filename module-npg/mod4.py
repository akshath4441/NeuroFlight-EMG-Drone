import os
import time
import pandas as pd


# ============================================================
# SETTINGS
# ============================================================

INPUT_FILE = "data/emg_commands.csv"

# How long to wait before printing the next command
# based on the recorded EMG timestamps.
REAL_TIME_PLAYBACK = True

# Safety timeout
COMMAND_TIMEOUT = 1.0


# ============================================================
# LOAD COMMAND DATA
# ============================================================

def load_commands():

    if not os.path.exists(INPUT_FILE):

        print("ERROR: Command file not found.")
        print(f"Expected: {INPUT_FILE}")
        print()
        print("Run Module 1 → Module 2 → Module 3 first.")

        return None

    df = pd.read_csv(INPUT_FILE)

    required_columns = [
        "timestamp",
        "command"
    ]

    for column in required_columns:

        if column not in df.columns:

            print(
                f"ERROR: Missing column: {column}"
            )

            return None

    return df


# ============================================================
# SIMULATED DRONE COMMAND
# ============================================================

def send_drone_command(command):

    if command == "LEFT":

        print(
            "🟢 EMG → LEFT"
            "        | Drone command → ROLL LEFT"
        )

    elif command == "RIGHT":

        print(
            "🔵 EMG → RIGHT"
            "       | Drone command → ROLL RIGHT"
        )

    elif command == "STOP":

        print(
            "⚪ EMG → STOP"
            "        | Drone command → HOVER / STOP"
        )

    else:

        print(
            f"⚠ UNKNOWN COMMAND: {command}"
        )


# ============================================================
# MAIN SIMULATION
# ============================================================

def main():

    print("=" * 70)
    print("MODULE 4 - DRONE COMMAND SIMULATOR")
    print("=" * 70)

    print()
    print("IMPORTANT:")
    print("This version DOES NOT connect to the drone.")
    print("No motor or flight command will be sent.")
    print()

    # --------------------------------------------------------
    # LOAD DATA
    # --------------------------------------------------------

    df = load_commands()

    if df is None:
        return

    print(
        f"Loaded {len(df)} EMG samples."
    )

    print()

    # --------------------------------------------------------
    # COMMAND COUNTS
    # --------------------------------------------------------

    print("COMMAND COUNTS")
    print("----------------")

    print(
        f"LEFT  : {(df['command'] == 'LEFT').sum()}"
    )

    print(
        f"RIGHT : {(df['command'] == 'RIGHT').sum()}"
    )

    print(
        f"STOP  : {(df['command'] == 'STOP').sum()}"
    )

    print()

    # --------------------------------------------------------
    # START
    # --------------------------------------------------------

    print("=" * 70)
    print("STARTING DRONE COMMAND SIMULATION")
    print("=" * 70)

    print()

    previous_command = None
    previous_timestamp = None

    command_start_time = time.time()

    # --------------------------------------------------------
    # PROCESS COMMANDS
    # --------------------------------------------------------

    for _, row in df.iterrows():

        command = str(
            row["command"]
        ).upper()

        timestamp = float(
            row["timestamp"]
        )

        # ----------------------------------------------------
        # PRINT ONLY WHEN COMMAND CHANGES
        # ----------------------------------------------------

        if command != previous_command:

            # Safety check
            if (
                time.time()
                - command_start_time
                > COMMAND_TIMEOUT
                and previous_command is not None
            ):

                print(
                    "⚠ COMMAND TIMEOUT → STOP"
                )

                send_drone_command(
                    "STOP"
                )

            print()

            print(
                f"[{timestamp:.2f}]",
                end=" "
            )

            send_drone_command(
                command
            )

            previous_command = command

            command_start_time = time.time()

        # ----------------------------------------------------
        # REAL-TIME PLAYBACK
        # ----------------------------------------------------

        if (
            REAL_TIME_PLAYBACK
            and previous_timestamp is not None
        ):

            delay = (
                timestamp
                - previous_timestamp
            )

            # Prevent extremely large delays
            delay = max(
                0,
                min(delay, 0.05)
            )

            time.sleep(
                delay
            )

        previous_timestamp = timestamp

    # --------------------------------------------------------
    # FINAL SAFETY STOP
    # --------------------------------------------------------

    print()

    print("=" * 70)
    print("SIMULATION FINISHED")
    print("=" * 70)

    print()

    print(
        "FINAL SAFETY COMMAND → STOP"
    )

    send_drone_command(
        "STOP"
    )

    print()

    print(
        "Module 4 software simulation completed."
    )


# ============================================================
# PROGRAM ENTRY
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print()
        print(
            "Simulation interrupted."
        )

        print(
            "SAFETY COMMAND → STOP"
        )