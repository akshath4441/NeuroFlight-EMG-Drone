import socket

HOST = "0.0.0.0"
PORT = 2390

print("=" * 60)
print("UDP 2390 LISTENER TEST")
print("=" * 60)
print()
print(f"Listening on UDP port {PORT}...")
print("Waiting for packets from LiteWing...")
print()
print("Press Ctrl+C to stop.")
print()

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((HOST, PORT))
sock.settimeout(10)

try:
    while True:
        try:
            data, address = sock.recvfrom(4096)

            print("PACKET RECEIVED")
            print("-" * 60)
            print("From   :", address)
            print("Bytes  :", len(data))
            print("Data   :", data.hex())
            print()

        except socket.timeout:
            print("No UDP packet received in the last 10 seconds.")

except KeyboardInterrupt:
    print()
    print("Listener stopped.")

finally:
    sock.close()
    print("Socket closed.")