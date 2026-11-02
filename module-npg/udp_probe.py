import time
import cflib.crtp
from cflib.crazyflie import Crazyflie

DRONE_URI = "udp://192.168.43.42:2390"

print("=" * 60)
print("LITEWING TEST 2 - STABILIZED COMMANDER")
print("=" * 60)
print()
print("PROPELLERS MUST BE REMOVED")
print("NO TAKEOFF")
print("NO FLIGHT")
print("ZERO THRUST ONLY")
print()

input("Press ENTER to continue...")

cflib.crtp.init_drivers()

cf = Crazyflie()
connected = False


def on_connected(uri):
    global connected
    connected = True
    print("\nCONNECTED:", uri)


def on_connection_failed(uri, msg):
    print("\nCONNECTION FAILED:", msg)


def on_connection_lost(uri, msg):
    print("\nCONNECTION LOST:", msg)


cf.connected.add_callback(on_connected)
cf.connection_failed.add_callback(on_connection_failed)
cf.connection_lost.add_callback(on_connection_lost)

print("Connecting...")
cf.open_link(DRONE_URI)

for _ in range(30):
    if connected:
        break
    time.sleep(0.5)

if not connected:
    print("ERROR: Could not connect.")
    raise SystemExit

print("\nWaiting for firmware...")
time.sleep(5)

print("\n" + "=" * 60)
print("PHASE 1 - ZERO COMMAND")
print("=" * 60)

for _ in range(50):
    cf.commander.send_setpoint(
        0.0,
        0.0,
        0.0,
        0
    )
    time.sleep(0.02)

print("Zero commands sent.")

print("\n" + "=" * 60)
print("PHASE 2 - SMALL ROLL COMMAND")
print("=" * 60)

print("Roll = +5 degrees")
print("Pitch = 0")
print("Yaw = 0")
print("Thrust = 0")

for _ in range(50):
    cf.commander.send_setpoint(
        5.0,
        0.0,
        0.0,
        0
    )
    time.sleep(0.02)

print("Roll commands sent.")

print("\n" + "=" * 60)
print("PHASE 3 - SMALL PITCH COMMAND")
print("=" * 60)

print("Roll = 0")
print("Pitch = +5 degrees")
print("Yaw = 0")
print("Thrust = 0")

for _ in range(50):
    cf.commander.send_setpoint(
        0.0,
        5.0,
        0.0,
        0
    )
    time.sleep(0.02)

print("Pitch commands sent.")

print("\n" + "=" * 60)
print("PHASE 4 - RETURN TO ZERO")
print("=" * 60)

for _ in range(50):
    cf.commander.send_setpoint(
        0.0,
        0.0,
        0.0,
        0
    )
    time.sleep(0.02)

print("Zero command restored.")

print("\n" + "=" * 60)
print("TEST 2 COMPLETE")
print("=" * 60)
print()
print("No thrust was intentionally sent.")
print("No takeoff was attempted.")

cf.close_link()