import socket
import time
import random

HOST = '127.0.0.1'  # Local testing
PORT = 4001

# Data patterns with placeholders for weight
patterns = [
    "ST,{:+.2f}",           # Matches r'ST.*?([+-]?\d+\.?\d*)'
    "{:+.2f},ST",           # Matches r'([+-]?\d+\.?\d*).*?ST'
    "{:+.2f} kg ST",        # Matches r'([+-]?\d+\.?\d*)\s*kg.*?ST'
]

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((HOST, PORT))
server.listen(1)
print(f"✅ Fake scale (patterned) running on {HOST}:{PORT}... Waiting for connection.")

conn, addr = server.accept()
print(f"✅ Logger connected from {addr}")

while True:
    weight = random.uniform(5, 50)  # Generate a fake weight
    # Choose a random format
    message = random.choice(patterns).format(weight)
    data = f"{message}\r\n"

    print(f"📤 Sending: {data.strip()}")
    conn.sendall(data.encode())
    time.sleep(2)  # Send every 2 seconds
