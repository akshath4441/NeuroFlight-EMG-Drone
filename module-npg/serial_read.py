import time
import cflib.crtp
from cflib.crazyflie import Crazyflie


DRONE_URI = "udp://192.168.43.42:2390"

connected = False


def on_connected(uri):
    global connected
    connected = True

    print()
    print("=" * 70)
    print("LITEWING CONNECTED")
    print("=" * 70)
    print(f"URI: {uri}")
    print("Connection successful.")


def on_connection_failed(uri, message):
    print()
    print("LITEWING CONNECTION FAILED")
    print(f"URI: {uri}")
    print(f"Reason: {message}")


def on_connection_lost(uri, message):
    print()
    print("LITEWING CONNECTION LOST")
    print(f"Reason: {message}")


print("=" * 70)
print("LITEWING MOTOR TEST")
print("=" * 70)

print()
print("SAFETY CHECK")
print("- Propellers MUST be removed")
print("- Drone must be on a stable surface")
print("- Keep hands away from motors")
print("- NO takeoff")
print("- NO movement")
print("- VERY SHORT motor test only")
print()

input("Confirm propellers are removed, then press ENTER...")

print()
print("Initializing cflib...")

cflib.crtp.init_drivers()

cf = Crazyflie()

cf.connected.add_callback(on_connected)
cf.connection_failed.add_callback(on_connection_failed)
cf.connection_lost.add_callback(on_connection_lost)

print(f"Connecting to {DRONE_URI}...")

cf.open_link(DRONE_URI)

print("Waiting for LiteWing connection...")

# Give the connection callback enough time.
time.sleep(10)

if not connected:
    print()
    print("=" * 70)
    print("CONNECTION NOT CONFIRMED")
    print("=" * 70)
    print("No motor command will be sent.")

    try:
        cf.close_link()
    except Exception:
        pass

    raise SystemExit(1)


print()
print("=" * 70)
print("READY FOR MOTOR TEST")
print("=" * 70)

print()
print("The following test will:")
print("1. Send minimum documented thrust")
print("2. Maintain it for 0.5 seconds")
print("3. Send STOP")
print()

input("Press ENTER to start the motor test...")

try:

    print()
    print(">>> MOTOR TEST STARTING")
    print(">>> THRUST = 10001")
    print(">>> DURATION = 0.5 seconds")

    # Minimum documented thrust setpoint.
    cf.commander.send_setpoint(
        0.0,      # roll
        0.0,      # pitch
        0.0,      # yaw rate
        10001     # minimum thrust
    )

    time.sleep(0.5)

    print(">>> SENDING MOTOR STOP")

    cf.commander.send_stop_setpoint()

    # Give the stop packet time to reach LiteWing.
    time.sleep(0.5)

    print()
    print("=" * 70)
    print("MOTOR TEST FINISHED")
    print("=" * 70)

except KeyboardInterrupt:

    print()
    print("CTRL+C DETECTED")
    print("Sending emergency motor STOP...")

    try:
        cf.commander.send_stop_setpoint()
    except Exception:
        pass

finally:

    print()
    print("Closing LiteWing connection...")

    try:
        cf.close_link()
    except Exception:
        pass

    print("Done.")