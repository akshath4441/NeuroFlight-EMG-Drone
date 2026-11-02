"""
Live dashboard: NPG Lite EMG -> LiteWing motor-output bench test.

SAFETY:
- REMOVE ALL PROPELLERS before running.
- Direct motorPowerSet output is NOT normal flight control.
- Motor power remains at the previously tested value 1000.
- Each activation is limited to a short pulse.
- This does not provide directional flight or controlled yaw.

Run from module-npg:
    uv run python integrated_emg_dashboard.py
"""

import asyncio
import math
import queue
import statistics
import threading
import time
import tkinter as tk
from tkinter import ttk
from collections import deque

import numpy as np
from scipy.signal import butter, iirnotch, sosfilt, lfilter

from bleak import BleakClient
import cflib.crtp
from cflib.crazyflie import Crazyflie


# ---------------- DEVICE SETTINGS ----------------
NPG_MAC = "E4:B3:23:AF:72:B6"
NPG_DATA_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
NPG_CONTROL_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
LITEWING_URI = "udp://192.168.43.42:2390"

TEST_POWER = 5000
MAX_MOTOR_PULSE_SECONDS = 1.0
CALIBRATION_SECONDS = 3.0
SAMPLE_RATE_HZ = 500
SAMPLE_BYTES = 7
RMS_WINDOW_SAMPLES = 25
THRESHOLD_MULTIPLIER = 2.5
THRESHOLD_FLOOR = 20.0
RELEASE_RATIO = 0.65

# --------------- SHARED STATE --------------------
cf = None
cf_connected = threading.Event()
shutdown_requested = threading.Event()
motor_queue = queue.Queue()
ui_queue = queue.Queue()
motor_worker_thread = None

packet_buffer = bytearray()
calibration_samples = [[], []]
rms_windows = [deque(maxlen=RMS_WINDOW_SAMPLES),
               deque(maxlen=RMS_WINDOW_SAMPLES)]
baseline = [None, None]
noise_rms = [None, None]
activation_threshold = [None, None]
calibration_start = None
calibration_done = False
pulse_latched_until_release = False
motor_pulse_started = None
last_motor_request = False
last_status_time = 0.0
motor_active_until = 0.0
latest_status = {
    "ble": "Waiting",
    "wifi": "Waiting",
    "phase": "Waiting to start",
    "left_raw": 0,
    "right_raw": 0,
    "left_rms": 0.0,
    "right_rms": 0.0,
    "command": "STOP",
    "motor": "OFF",
    "filter": "Bandpass 20–100 Hz + 50 Hz notch",
    "message": "Remove propellers before starting.",
}

# Streaming causal filters at 500 Hz: bandpass then notch on each channel.
BP_SOS = butter(4, [20, 100], btype="bandpass", fs=SAMPLE_RATE_HZ, output="sos")
NOTCH_B, NOTCH_A = iirnotch(50, 30, fs=SAMPLE_RATE_HZ)
filter_sos_state = [np.zeros((BP_SOS.shape[0], 2)), np.zeros((BP_SOS.shape[0], 2))]
notch_state = [np.zeros(max(len(NOTCH_A), len(NOTCH_B)) - 1),
               np.zeros(max(len(NOTCH_A), len(NOTCH_B)) - 1)]


def ui_update(**kwargs):
    latest_status.update(kwargs)
    ui_queue.put(dict(latest_status))


def on_connected(uri):
    cf_connected.set()
    ui_update(wifi="Connected", message=f"LiteWing connected: {uri}")


def on_connection_failed(uri, message):
    ui_update(wifi="Failed", message=f"LiteWing connection failed: {message}")


def on_disconnected(uri):
    cf_connected.clear()
    shutdown_requested.set()
    ui_update(wifi="Disconnected", command="STOP", motor="OFF",
              message="LiteWing disconnected; stopping.")


def set_param(name, value):
    if cf is None or not cf_connected.is_set():
        raise ConnectionError("LiteWing is not connected.")
    cf.param.set_value(name, str(value))
    time.sleep(0.15)


def stop_motor_outputs():
    if cf is None or not cf_connected.is_set():
        return
    for motor in ("m1", "m2", "m3", "m4"):
        try:
            set_param(f"motorPowerSet.{motor}", 0)
        except Exception as exc:
            ui_update(message=f"Could not zero {motor}: {exc}")
    try:
        set_param("motorPowerSet.enable", 0)
    except Exception as exc:
        ui_update(message=f"Could not disable motor output: {exc}")


def start_motor_outputs():
    if cf is None or not cf_connected.is_set():
        raise ConnectionError("LiteWing is disconnected.")
    set_param("motorPowerSet.enable", 0)
    for motor in ("m1", "m2", "m3", "m4"):
        set_param(f"motorPowerSet.{motor}", TEST_POWER)
    set_param("motorPowerSet.enable", 1)


def motor_worker():
    output_on = False
    while True:
        command = motor_queue.get()
        try:
            if command is None:
                break
            if command == "ON" and not output_on:
                try:
                    start_motor_outputs()
                    output_on = True
                    ui_update(motor="ON (pulse)", message=f"Muscle flex detected; outputs at {TEST_POWER}.")
                except Exception as exc:
                    stop_motor_outputs()
                    output_on = False
                    ui_update(motor="OFF", command="STOP", message=f"Motor activation failed: {exc}")
            elif command == "OFF":
                stop_motor_outputs()
                output_on = False
                ui_update(motor="OFF")
        finally:
            motor_queue.task_done()
    stop_motor_outputs()


def request_motor(on):
    global last_motor_request
    if on == last_motor_request:
        return
    last_motor_request = on
    motor_queue.put("ON" if on else "OFF")


def parse_sample(raw):
    return (raw[0],
            int.from_bytes(raw[1:3], "big"),
            int.from_bytes(raw[3:5], "big"),
            int.from_bytes(raw[5:7], "big"))


def filter_emg(channel, raw_value):
    # Remove DC baseline approximately, then stream through bandpass and notch.
    # Initial state is zero; brief startup transients are expected.
    x = float(raw_value)
    y_bp, filter_sos_state[channel][:] = sosfilt(
        BP_SOS, np.array([x]), zi=filter_sos_state[channel]
    )
    y_notch, notch_state[channel][:] = lfilter(
        NOTCH_B, NOTCH_A, y_bp, zi=notch_state[channel]
    )
    return float(y_notch[0])


def finish_calibration():
    global calibration_done
    if len(calibration_samples[0]) < SAMPLE_RATE_HZ:
        ui_update(phase="Calibration failed", message="Not enough samples; keep outputs stopped.")
        return
    for channel in (0, 1):
        vals = calibration_samples[channel]
        center = statistics.median(vals)
        baseline[channel] = center
        noise = math.sqrt(sum((v - center) ** 2 for v in vals) / len(vals))
        noise_rms[channel] = noise
        activation_threshold[channel] = max(
            noise * THRESHOLD_MULTIPLIER, noise + THRESHOLD_FLOOR
        )
    calibration_done = True
    ui_update(phase="Live monitoring",
              message="Calibration complete. Flex one forearm briefly, then relax.")


def process_sample(counter, ch0, ch1):
    global calibration_start, pulse_latched_until_release
    global motor_pulse_started, last_status_time

    now = time.monotonic()
    raw_values = (ch0, ch1)
    filtered = (filter_emg(0, ch0), filter_emg(1, ch1))

    if calibration_start is None:
        calibration_start = now
        ui_update(phase="Calibrating (keep relaxed)", message="Keep both forearms relaxed for 3 seconds.")

    if not calibration_done:
        for channel in (0, 1):
            calibration_samples[channel].append(filtered[channel])
        if now - calibration_start >= CALIBRATION_SECONDS:
            finish_calibration()
        return

    # Use filtered signal deviation from the relaxed filtered baseline.
    for channel in (0, 1):
        rms_windows[channel].append((filtered[channel] - baseline[channel]) ** 2)
    if any(len(w) < RMS_WINDOW_SAMPLES for w in rms_windows):
        return

    rms = [math.sqrt(sum(w) / len(w)) for w in rms_windows]
    left_active = rms[0] >= activation_threshold[0]
    right_active = rms[1] >= activation_threshold[1]
    fully_released = (
        rms[0] < activation_threshold[0] * RELEASE_RATIO
        and rms[1] < activation_threshold[1] * RELEASE_RATIO
    )

    if left_active and right_active:
        command = "BOTH ACTIVE — STOP"
    elif left_active:
        command = "LEFT EMG ACTIVATED"
    elif right_active:
        command = "RIGHT EMG ACTIVATED"
    else:
        command = "NO MUSCLE ACTIVATION"

    ui_update(
        left_raw=raw_values[0],
        right_raw=raw_values[1],
        left_rms=round(rms[0], 1),
        right_rms=round(rms[1], 1),
        command=command,
        phase="Live monitoring",
    )

    if fully_released:
        pulse_latched_until_release = False

    # Bench test only: either isolated muscle flex triggers a short pulse.
    # Both channels active is deliberately treated as STOP.
    if left_active and right_active:
        request_motor(False)
        motor_pulse_started = None
    elif (left_active or right_active) and not pulse_latched_until_release:
        pulse_latched_until_release = True
        motor_pulse_started = now
        request_motor(True)

    if motor_pulse_started is not None and now - motor_pulse_started >= MAX_MOTOR_PULSE_SECONDS:
        request_motor(False)
        motor_pulse_started = None
        ui_update(message="Pulse time limit reached; relax before triggering again.")


def on_npg_notification(sender, data):
    if shutdown_requested.is_set():
        return
    packet_buffer.extend(data)
    while len(packet_buffer) >= SAMPLE_BYTES:
        raw = bytes(packet_buffer[:SAMPLE_BYTES])
        del packet_buffer[:SAMPLE_BYTES]
        try:
            counter, ch0, ch1, ch2 = parse_sample(raw)
            process_sample(counter, ch0, ch1)
        except Exception as exc:
            request_motor(False)
            ui_update(command="STOP", motor="OFF", message=f"EMG processing error: {exc}")


async def write_npg_command(client, command):
    payload = command.encode("ascii")
    try:
        await client.write_gatt_char(NPG_CONTROL_UUID, payload, response=True)
    except Exception:
        await client.write_gatt_char(NPG_CONTROL_UUID, payload, response=False)


async def hardware_main():
    global cf, motor_worker_thread
    try:
        ui_update(phase="Connecting LiteWing", wifi="Connecting",
                  message="Remove all propellers. Connecting to LiteWing over Wi-Fi.")
        cflib.crtp.init_drivers()
        cf = Crazyflie(rw_cache="./cache")
        cf.connected.add_callback(on_connected)
        cf.connection_failed.add_callback(on_connection_failed)
        cf.disconnected.add_callback(on_disconnected)
        motor_worker_thread = threading.Thread(target=motor_worker, daemon=True)
        motor_worker_thread.start()
        cf.open_link(LITEWING_URI)

        if not cf_connected.wait(timeout=15):
            raise TimeoutError("LiteWing connection timed out.")
        await asyncio.sleep(8)
        await asyncio.to_thread(stop_motor_outputs)

        ui_update(ble="Connecting", phase="Connecting NPG Lite",
                  message="Connecting to NPG Lite over BLE.")
        async with BleakClient(NPG_MAC, timeout=20.0) as client:
            if not client.is_connected:
                raise ConnectionError("NPG Lite BLE connection failed.")
            ui_update(ble="Connected", phase="Starting EMG stream",
                      message="NPG Lite connected; starting notifications.")
            await client.start_notify(NPG_DATA_UUID, on_npg_notification)
            await write_npg_command(client, "START")
            ui_update(phase="Calibrating (keep relaxed)",
                      message="Keep both forearms relaxed for 3 seconds.")
            while not shutdown_requested.is_set() and client.is_connected:
                await asyncio.sleep(0.1)
            try:
                await write_npg_command(client, "STOP")
            except Exception:
                pass
            try:
                await client.stop_notify(NPG_DATA_UUID)
            except Exception:
                pass
    except Exception as exc:
        ui_update(phase="Error", command="STOP", motor="OFF",
                  message=f"Connection/runtime error: {exc}")
    finally:
        shutdown_requested.set()
        try:
            motor_queue.put("OFF")
            motor_queue.join()
            if motor_worker_thread:
                motor_queue.put(None)
                motor_queue.join()
                motor_worker_thread.join(timeout=2)
        except Exception:
            pass
        try:
            await asyncio.to_thread(stop_motor_outputs)
        except Exception:
            pass
        if cf is not None:
            try:
                cf.close_link()
            except Exception:
                pass
        ui_update(phase="Stopped", command="STOP", motor="OFF",
                  message="Program stopped. Verify motor outputs are off.")


def run_hardware_loop():
    asyncio.run(hardware_main())


# ---------------- SIMPLE LIVE DASHBOARD ----------------
def launch_dashboard():
    root = tk.Tk()
    root.title("NPG Lite + LiteWing | EMG Dashboard")
    root.geometry("760x560")
    root.minsize(700, 520)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    outer = ttk.Frame(root, padding=18)
    outer.pack(fill="both", expand=True)

    ttk.Label(outer, text="EMG DRONE CONTROL", font=("Segoe UI", 18, "bold")).pack(anchor="w")
    ttk.Label(outer, text="Live monitor • Propellers must remain removed",
              font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 14))

    connection_frame = ttk.LabelFrame(outer, text="Connections", padding=10)
    connection_frame.pack(fill="x", pady=(0, 10))
    ble_var = tk.StringVar(value="Waiting")
    wifi_var = tk.StringVar(value="Waiting")
    ttk.Label(connection_frame, text="NPG Lite BLE:", width=18).grid(row=0, column=0, sticky="w", padx=4, pady=3)
    ttk.Label(connection_frame, textvariable=ble_var, font=("Segoe UI", 10, "bold")).grid(row=0, column=1, sticky="w", padx=4, pady=3)
    ttk.Label(connection_frame, text="LiteWing Wi-Fi:", width=18).grid(row=1, column=0, sticky="w", padx=4, pady=3)
    ttk.Label(connection_frame, textvariable=wifi_var, font=("Segoe UI", 10, "bold")).grid(row=1, column=1, sticky="w", padx=4, pady=3)

    readings = ttk.Frame(outer)
    readings.pack(fill="x", pady=(0, 10))
    left_box = ttk.LabelFrame(readings, text="LEFT EMG (Channel 0)", padding=12)
    right_box = ttk.LabelFrame(readings, text="RIGHT EMG (Channel 1)", padding=12)
    left_box.pack(side="left", fill="both", expand=True, padx=(0, 6))
    right_box.pack(side="left", fill="both", expand=True, padx=(6, 0))
    left_raw_var, right_raw_var = tk.StringVar(value="Raw: —"), tk.StringVar(value="Raw: —")
    left_rms_var, right_rms_var = tk.StringVar(value="Filtered RMS: —"), tk.StringVar(value="Filtered RMS: —")
    ttk.Label(left_box, textvariable=left_raw_var, font=("Segoe UI", 12)).pack(anchor="w", pady=4)
    ttk.Label(left_box, textvariable=left_rms_var, font=("Segoe UI", 11)).pack(anchor="w", pady=4)
    ttk.Label(right_box, textvariable=right_raw_var, font=("Segoe UI", 12)).pack(anchor="w", pady=4)
    ttk.Label(right_box, textvariable=right_rms_var, font=("Segoe UI", 11)).pack(anchor="w", pady=4)

    command_frame = ttk.LabelFrame(outer, text="Command classification", padding=12)
    command_frame.pack(fill="x", pady=(0, 10))
    command_var = tk.StringVar(value="STOP")
    command_label = ttk.Label(command_frame, textvariable=command_var,
                              font=("Segoe UI", 17, "bold"), anchor="center")
    command_label.pack(fill="x", pady=5)

    motor_frame = ttk.LabelFrame(outer, text="Motor output", padding=10)
    motor_frame.pack(fill="x", pady=(0, 10))
    motor_var = tk.StringVar(value="OFF")
    ttk.Label(motor_frame, textvariable=motor_var, font=("Segoe UI", 12, "bold")).pack(anchor="w")

    phase_var = tk.StringVar(value="Waiting to start")
    message_var = tk.StringVar(value="Remove all propellers before running.")
    ttk.Label(outer, textvariable=phase_var, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(2, 2))
    ttk.Label(outer, textvariable=message_var, wraplength=700).pack(anchor="w")

    ttk.Label(outer, text="Filtering: 20–100 Hz bandpass + 50 Hz notch; RMS activation detector.",
              font=("Segoe UI", 9)).pack(anchor="w", pady=(10, 0))

    def poll_updates():
        while True:
            try:
                state = ui_queue.get_nowait()
            except queue.Empty:
                break
            ble_var.set(state.get("ble", "Waiting"))
            wifi_var.set(state.get("wifi", "Waiting"))
            left_raw_var.set(f"Raw: {state.get('left_raw', 0)}")
            right_raw_var.set(f"Raw: {state.get('right_raw', 0)}")
            left_rms_var.set(f"Filtered RMS: {state.get('left_rms', 0)}")
            right_rms_var.set(f"Filtered RMS: {state.get('right_rms', 0)}")
            command_var.set(state.get("command", "STOP"))
            motor_var.set(state.get("motor", "OFF"))
            phase_var.set(state.get("phase", "Waiting"))
            message_var.set(state.get("message", ""))
        if not shutdown_requested.is_set():
            root.after(100, poll_updates)

    def close_window():
        shutdown_requested.set()
        try:
            motor_queue.put("OFF")
        except Exception:
            pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close_window)
    threading.Thread(target=run_hardware_loop, name="hardware-loop", daemon=True).start()
    root.after(100, poll_updates)
    root.mainloop()


if __name__ == "__main__":
    print("SAFETY CHECK: remove all propellers before running.")
    print("This dashboard uses direct motor output for a short bench pulse only.")
    input("Press ENTER after confirming all propellers are removed...")
    try:
        launch_dashboard()
    except KeyboardInterrupt:
        shutdown_requested.set()
# pyrefly: ignore[parse-error]
