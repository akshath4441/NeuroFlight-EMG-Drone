"""
NPG Lite-only simulated drone dashboard.
No LiteWing Wi-Fi, cflib, arming, or motor commands are used.

Install: uv add bleak
Run:     python npg_only_dashboard.py

Parser assumption: BLE notifications are little-endian uint16 values in
left-EMG, right-EMG, optional-extra-channel order. If your device's packet
format differs, retain your original parser in parse_packet().
"""
import asyncio
import math
import queue
import struct
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from collections import deque
from bleak import BleakClient, BleakScanner

NPG_MAC = "E4:B3:23:AF:72:B6"
NPG_DATA_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
NPG_CONTROL_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
SEND_START_COMMAND = False  # Set True only if b"start" is verified for your NPG Lite.
START_COMMAND = b"start"
WINDOW = 50
THRESHOLD = 35.0
events = queue.Queue()
stop_flag = threading.Event()


def parse_packet(data):
    """Assumed packet format: little-endian uint16 channel samples."""
    raw = bytes(data)
    usable = len(raw) - len(raw) % 2
    if usable < 4:
        return None
    vals = struct.unpack("<" + "H" * (usable // 2), raw[:usable])
    return vals[0], vals[1], vals[2] if len(vals) > 2 else None


def ble_thread_main():
    async def runner():
        try:
            events.put(("status", "Searching for NPG Lite…"))
            dev = await BleakScanner.find_device_by_address(NPG_MAC, timeout=12)
            if dev is None:
                events.put(("status", "NPG Lite not found. Check power and Bluetooth."))
                return
            async with BleakClient(dev, timeout=20) as client:
                events.put(("connected", True))
                events.put(("status", "Connected to NPG Lite; waiting for EMG data…"))

                def notification(_sender, data):
                    parsed = parse_packet(data)
                    if parsed is None:
                        events.put(("packet", f"Unparsed packet: {len(data)} bytes"))
                    else:
                        events.put(("emg", parsed))

                await client.start_notify(NPG_DATA_UUID, notification)
                if SEND_START_COMMAND:
                    try:
                        await client.write_gatt_char(NPG_CONTROL_UUID, START_COMMAND, response=False)
                    except Exception as exc:
                        events.put(("status", f"Connected, but NPG start command failed: {exc}"))
                while not stop_flag.is_set() and client.is_connected:
                    await asyncio.sleep(0.2)
                try:
                    await client.stop_notify(NPG_DATA_UUID)
                except Exception:
                    pass
        except Exception as exc:
            events.put(("error", str(exc)))
        finally:
            events.put(("connected", False))
            events.put(("status", "NPG Lite disconnected."))

    asyncio.run(runner())


class App:
    def __init__(self, root):
        self.root = root
        root.title("NPG Lite — Simulated Drone Dashboard")
        root.geometry("880x600")
        root.minsize(720, 520)
        self.left = deque(maxlen=WINDOW)
        self.right = deque(maxlen=WINDOW)
        self.thread = None
        self.threshold = tk.StringVar(value=str(THRESHOLD))
        self.ble_status = tk.StringVar(value="NPG Lite: Disconnected")
        self.status = tk.StringVar(value="Ready. Connect to NPG Lite.")
        self.left_raw = tk.StringVar(value="—")
        self.right_raw = tk.StringVar(value="—")
        self.left_rms = tk.StringVar(value="0.0")
        self.right_rms = tk.StringVar(value="0.0")
        self.packet = tk.StringVar(value="No packets received")
        self.command = tk.StringVar(value="WAITING")
        self.drone = tk.StringVar(value="SIMULATED DRONE: IDLE")
        self.build()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll)

    def build(self):
        base = ttk.Frame(self.root, padding=14)
        base.pack(fill="both", expand=True)
        ttk.Label(base, text="NPG Lite → Simulated Drone", font=("Segoe UI", 19, "bold")).pack(anchor="w")
        ttk.Label(base, text="BLE input only • No LiteWing Wi-Fi • No physical motor commands",
                  foreground="#9a3412").pack(anchor="w", pady=(2, 12))

        conn = ttk.LabelFrame(base, text="NPG Lite connection", padding=10)
        conn.pack(fill="x", pady=(0, 10))
        ttk.Label(conn, textvariable=self.ble_status, font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(conn, text="Connect", command=self.connect).pack(side="right")
        ttk.Button(conn, text="Disconnect", command=self.disconnect).pack(side="right", padx=8)

        sig = ttk.LabelFrame(base, text="Live EMG", padding=10)
        sig.pack(fill="x", pady=(0, 10))
        for i in range(3):
            sig.columnconfigure(i, weight=1)
        for col, label in enumerate(("Left EMG raw", "Right EMG raw", "Packet status")):
            ttk.Label(sig, text=label).grid(row=0, column=col, sticky="w")
        for col, var in enumerate((self.left_raw, self.right_raw, self.packet)):
            ttk.Label(sig, textvariable=var, font=("Consolas", 14), wraplength=240).grid(
                row=1, column=col, sticky="w", pady=(3, 10))
        ttk.Label(sig, text="Left RMS (AC)").grid(row=2, column=0, sticky="w")
        ttk.Label(sig, text="Right RMS (AC)").grid(row=2, column=1, sticky="w")
        ttk.Label(sig, text="Activation threshold").grid(row=2, column=2, sticky="w")
        ttk.Label(sig, textvariable=self.left_rms, font=("Consolas", 14)).grid(row=3, column=0, sticky="w")
        ttk.Label(sig, textvariable=self.right_rms, font=("Consolas", 14)).grid(row=3, column=1, sticky="w")
        row = ttk.Frame(sig)
        row.grid(row=3, column=2, sticky="w")
        ttk.Entry(row, textvariable=self.threshold, width=8).pack(side="left")
        ttk.Button(row, text="Apply", command=self.apply_threshold).pack(side="left", padx=5)

        cmd = ttk.LabelFrame(base, text="Command output (simulation only)", padding=12)
        cmd.pack(fill="both", expand=True, pady=(0, 10))
        ttk.Label(cmd, text="Detected command").pack(anchor="w")
        ttk.Label(cmd, textvariable=self.command, font=("Segoe UI", 25, "bold")).pack(anchor="w", pady=(3, 12))
        ttk.Label(cmd, textvariable=self.drone, font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(cmd, textvariable=self.status, wraplength=800).pack(anchor="w", pady=(12, 0))
        ttk.Label(base, text="Safety: this dashboard displays simulated output only; it cannot arm, spin, or fly the LiteWing.",
                  foreground="#9a3412", wraplength=800).pack(anchor="w")

    def connect(self):
        if self.thread and self.thread.is_alive():
            self.status.set("A connection attempt is already running.")
            return
        stop_flag.clear()
        self.ble_status.set("NPG Lite: Connecting…")
        self.status.set("Connecting to NPG Lite only.")
        self.thread = threading.Thread(target=ble_thread_main, daemon=True)
        self.thread.start()

    def disconnect(self):
        stop_flag.set()
        self.status.set("Disconnect requested…")

    def apply_threshold(self):
        global THRESHOLD
        try:
            val = float(self.threshold.get())
            if not math.isfinite(val) or val <= 0:
                raise ValueError
            THRESHOLD = val
            self.status.set(f"Threshold set to {THRESHOLD:.1f}. Adjust using rest and contraction readings.")
        except ValueError:
            messagebox.showerror("Invalid threshold", "Enter a positive number, e.g. 35.")

    @staticmethod
    def rms_ac(values):
        if len(values) < 5:
            return 0.0
        mean = sum(values) / len(values)
        return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))

    def on_emg(self, item):
        left, right, extra = item
        self.left.append(float(left))
        self.right.append(float(right))
        lr = self.rms_ac(self.left)
        rr = self.rms_ac(self.right)
        self.left_raw.set(str(left))
        self.right_raw.set(str(right))
        self.left_rms.set(f"{lr:.1f}")
        self.right_rms.set(f"{rr:.1f}")
        self.packet.set("Live packets" + (f" • extra={extra}" if extra is not None else ""))

        la, ra = lr >= THRESHOLD, rr >= THRESHOLD
        if la and ra:
            command, drone = "STOP", "SIMULATED DRONE: STOP / HOLD"
        elif la:
            command, drone = "LEFT", "SIMULATED DRONE: LEFT"
        elif ra:
            command, drone = "RIGHT", "SIMULATED DRONE: RIGHT"
        else:
            command, drone = "NO ACTIVATION", "SIMULATED DRONE: IDLE / HOLD"
        self.command.set(command)
        self.drone.set(drone)
        self.status.set(f"EMG updated • threshold={THRESHOLD:.1f} • display only; nothing sent to drone")

    def poll(self):
        try:
            while True:
                kind, value = events.get_nowait()
                if kind == "status":
                    self.status.set(value)
                elif kind == "connected":
                    self.ble_status.set("NPG Lite: Connected" if value else "NPG Lite: Disconnected")
                elif kind == "emg":
                    self.on_emg(value)
                elif kind == "packet":
                    self.packet.set(value)
                elif kind == "error":
                    self.status.set("BLE error: " + value)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def close(self):
        stop_flag.set()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
