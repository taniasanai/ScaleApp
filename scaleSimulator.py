"""Pretends to be the two scales so scaleServer.py can be tested without hardware.

Each fake scale listens on its own port and streams readings the way a real
scale does: a steady zero while empty, unstable values while a load settles,
the same stable value repeated while it sits there, and sometimes more items
added on top before everything is removed. Data is sent in irregular chunks
(lines split in two, several lines at once) to test the logger's buffering.

    python scaleSimulator.py            normal speed
    python scaleSimulator.py --fast     10x faster, for quick tests
    python scaleSimulator.py --flaky    also drop the connection now and then
"""
import argparse
import random
import socket
import threading
import time

HOST = "127.0.0.1"

# (name, port, stable format, unstable format), following the Weightech manuals.
SCALES = [
    # WT1000 (LED/LCD), P5=5: stability flag (0 stable, 1 unstable), gross, tare, net.
    ("FakeWT1000", 4001, "0,{0:07.3f},000.000,{0:07.3f}", "1,{0:07.3f},000.000,{0:07.3f}"),
    # WT3000-I, full format in continuous transmission: status, gross/net, weight, unit.
    ("FakeWT3000i", 4002, "ST,GS,{0:+09.2f}  kg", "US,GS,{0:+09.2f}  kg"),
]


def hold(weight, count):
    for _ in range(count):
        yield weight, True


def settle(start, end, steps=6):
    """Unstable readings wobbling from start towards end."""
    for i in range(1, steps + 1):
        progress = i / steps
        wobble = (end - start) * random.uniform(-0.1, 0.1) * (1 - progress)
        yield start + (end - start) * progress + wobble, False


def weighing_cycle(name):
    """Yields (weight, stable) readings for one customer's load, start to finish."""
    yield from hold(0.0, random.randint(5, 20))
    weight = round(random.uniform(5, 500), 1)
    yield from settle(0.0, weight)
    yield from hold(weight, random.randint(5, 15))
    if random.random() < 0.4:  # more items of the same material added on top
        added = round(random.uniform(5, 100), 1)
        yield from settle(weight, weight + added)
        weight = round(weight + added, 1)
        yield from hold(weight, random.randint(5, 15))
    print(f"{name}: load of {weight:.2f} kg is being removed - expect it to be recorded")
    yield from settle(weight, 0.0)


def endless_weighings(name):
    while True:
        yield from weighing_cycle(name)


def stream(conn, readings, name, stable_format, unstable_format, interval, flaky):
    pending = b""
    for weight, stable in readings:
        if flaky and random.random() < 0.01:
            print(f"{name}: simulating a dropped connection")
            return
        line = (stable_format if stable else unstable_format).format(weight)
        pending += f"{line}\r\n".encode()
        if random.random() < 0.2:
            continue  # send together with the next line
        cut = random.randint(1, len(pending)) if random.random() < 0.2 else len(pending)
        conn.sendall(pending[:cut])
        pending = pending[cut:]
        time.sleep(interval)


def serve(name, port, stable_format, unstable_format, interval, flaky):
    server = socket.create_server((HOST, port))
    print(f"{name} listening on {HOST}:{port}")
    # Like a real scale, weighing carries on where it was when the connection drops.
    readings = endless_weighings(name)
    while True:
        conn, (address, client_port) = server.accept()
        print(f"{name}: logger connected from {address}:{client_port}")
        try:
            with conn:
                stream(conn, readings, name, stable_format, unstable_format, interval, flaky)
        except OSError as e:
            print(f"{name}: logger disconnected ({e})")


def main():
    parser = argparse.ArgumentParser(description="Simulate the scales for testing.")
    parser.add_argument("--fast", action="store_true", help="send readings 10x faster")
    parser.add_argument("--flaky", action="store_true", help="randomly drop connections")
    args = parser.parse_args()
    interval = 0.03 if args.fast else 0.3

    for scale in SCALES:
        threading.Thread(target=serve, args=(*scale, interval, args.flaky), daemon=True).start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
