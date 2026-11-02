
import time
import cflib.crtp
from cflib.crazyflie import Crazyflie

DRONE_URI = "udp://192.168.43.42:2390"

# Keep the previously tested low power.
TEST_POWER = 1000
TEST_SECONDS = 10.0

cf = None
connected = False


def on_connected(uri):
    global connected
    connected = True
    print("CONNECTED:", uri)


def on_failed(uri, message):
    print("CONNECTION FAILED:", message)


def set_param(name, value):
    cf.param.set_value(name, str(value))
    time.sleep(0.15)


def stop_outputs():
    """Attempt to zero every motor and disable direct output."""
    if cf is None or not connected:
        return

    for motor in ("m1", "m2", "m3", "m4"):
        try:
            set_param(f"motorPowerSet.{motor}", 0)
        except Exception as exc:
            print(f"Warning: could not zero {motor}: {exc}")

    try:
        set_param("motorPowerSet.enable", 0)
    except Exception as exc:
        print("Warning: could not disable motor output:", exc)


try:
    print("=" * 55)
    print("LITEWING 2-SECOND MOTOR DIAGNOSTIC")
    print("=" * 55)
    print("REMOVE ALL PROPELLERS.")
    print("Keep the drone secured on a stable surface.")
    print("No takeoff or flight commands will be sent.")
    input("\nPress ENTER when ready...")

    cflib.crtp.init_drivers()
    cf = Crazyflie(rw_cache="./cache")

    cf.connected.add_callback(on_connected)
    cf.connection_failed.add_callback(on_failed)

    print("\nConnecting...")
    cf.open_link(DRONE_URI)

    for _ in range(30):
        if connected:
            break
        time.sleep(0.5)

    if not connected:
        raise TimeoutError("LiteWing connection timed out.")

    print("\nWaiting for firmware parameters...")
    time.sleep(8)

    print("\nInitial motor-output values:")
    for motor in ("m1", "m2", "m3", "m4"):
        print(motor, "=", cf.param.get_value(
            f"motorPowerSet.{motor}"
        ))

    print("\nThis test activates all four direct motor outputs.")
    print("Duration:", TEST_SECONDS, "seconds")
    print("Power value:", TEST_POWER)
    input("Press ENTER to start...")

    # Ensure motor outputs start at zero.
    for motor in ("m1", "m2", "m3", "m4"):
        set_param(f"motorPowerSet.{motor}", 0)

    set_param("motorPowerSet.enable", 1)

    try:
        for motor in ("m1", "m2", "m3", "m4"):
            set_param(f"motorPowerSet.{motor}", TEST_POWER)

        print("\nMotor-output test running...")
        time.sleep(TEST_SECONDS)

    finally:
        print("\nStopping motor outputs...")
        stop_outputs()

    print("Test finished.")

finally:
    if cf is not None:
        try:
            stop_outputs()
            cf.close_link()
        except Exception as exc:
            print("Cleanup warning:", exc)

    print("Program ended.")
