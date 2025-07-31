import socket
import threading
import time
import pandas as pd
from datetime import datetime
import re
import ipaddress


# ---------------- CONFIGURATION ----------------
mode = "simulator"   # ⬅️ Set to "real" when connecting to actual scales

# Real device IPs (used only when mode="real")
REAL_SCALES = [
    ("192.168.1.100", 4001, "WT1000"),
    ("192.168.1.101", 4001, "WT3000i")
]

# Simulator IP/port (used only when mode="simulator")
SIMULATOR = ("127.0.0.1", 4001, "FakeScale")


# ---------------- NETWORK SCAN (real devices only) ----------------
def find_network_devices(network="192.168.1.0/24"):
    ports = [23, 4001, 4002, 8080, 502, 4196]
    found_devices = []
    print(f"Scanning network {network} ...")
    for ip in ipaddress.IPv4Network(network, False):
        for port in ports:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            if sock.connect_ex((str(ip), port)) == 0:
                print(f"Found device at {ip}:{port}")
                found_devices.append((str(ip), port))
            sock.close()
    return found_devices


# ---------------- SCALE READER CLASS ----------------
class ScaleReader:
    def __init__(self, ip, port, name):
        self.ip = ip
        self.port = port
        self.name = name
        self.socket = None
        self.running = False
        self.stable_weights = []

    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(3)
            self.socket.connect((self.ip, self.port))
            print(f"Connected to {self.name} at {self.ip}:{self.port}")
            return True
        except Exception as e:
            print(f"Failed to connect to {self.name}: {e}")
            return False

    def parse_weight(self, data):
        patterns = [
            r'ST.*?([+-]?\d+\.?\d*)',
            r'([+-]?\d+\.?\d*).*?ST',
            r'([+-]?\d+\.?\d*)\s*kg.*?ST',
        ]
        for p in patterns:
            m = re.search(p, data)
            if m:
                try:
                    return float(m.group(1)), True
                except ValueError:
                    continue
        return None, False

    def read_continuous(self, duration=1):
        if not self.connect():
            return
        self.running = True
        end_time = time.time() + duration * 60
        while self.running and time.time() < end_time:
            try:
                raw = self.socket.recv(1024).decode(errors='ignore').strip()
                if raw:
                    print(f"RAW → {self.name}: {repr(raw)}")
                    weight, stable = self.parse_weight(raw)
                    if weight is not None and stable:
                        self.stable_weights.append({
                            'timestamp': datetime.now(),
                            'scale': self.name,
                            'weight': weight,
                            'raw_data': raw
                        })
                        print(f"Check {self.name}: {weight} kg")
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Error {self.name}: {e}")
                break
            time.sleep(0.2)
        self.socket.close()
        print(f"Disconnected from {self.name}")

    def stop(self):
        self.running = False


# ---------------- MAIN ----------------
def main():
    # Select device list based on mode
    if mode == "simulator":
        print("Running in SIMULATOR mode")
        scales = [ScaleReader(*SIMULATOR)]
        found = []
    else:
        print("Running in REAL DEVICE mode")
        scales = [ScaleReader(ip, port, name) for ip, port, name in REAL_SCALES]
        found = find_network_devices("192.168.1.0/24")

        if found:
            print(f"Devices detected: {found}")

    # Start reading threads
    threads = []
    for s in scales:
        t = threading.Thread(target=s.read_continuous, args=(1,))  # 1 minute test
        t.start()
        threads.append(t)

    # Wait for threads
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        for s in scales:
            s.stop()

    # Save results
    all_data = []
    for s in scales:
        all_data.extend(s.stable_weights)

    if all_data:
        df = pd.DataFrame(all_data)
        filename = f"logFiles\scale_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        df.to_excel(filename, index=False)
        print(f"Data saved to {filename}")
    else:
        print("No stable readings captured.")


if __name__ == "__main__":
    main()
