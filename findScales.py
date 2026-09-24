"""Searches the local network for the scales' serial-to-network converters.

The converters (USR-W610 and USR-TCP232-306) accept TCP connections on a
configurable port. This checks every address in the network for ports such
devices commonly use and shows a sample of what each one sends, which helps
tell the two scales apart. Stop the logger first: the converters may accept
only one connection at a time.

    python findScales.py                 scan this computer's network
    python findScales.py 192.168.0.0/24  scan a specific network
"""
import ipaddress
import socket
import sys
from concurrent.futures import ThreadPoolExecutor

PORTS = [23, 502, 4001, 4002, 4196, 8080, 8899]
CONNECT_TIMEOUT = 0.5
SAMPLE_TIMEOUT = 2
WORKERS = 128


def local_network():
    """Guesses the /24 network this computer is on."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("10.255.255.255", 1))  # sends nothing; just selects the outgoing interface
        ip = s.getsockname()[0]
    if ip.startswith(("0.", "127.")):
        raise OSError("this computer doesn't seem to be connected to a network")
    return ipaddress.IPv4Network(f"{ip}/24", strict=False)


def probe(ip, port):
    """Returns a sample of what ip:port sends (b"" if nothing), or None if it's closed."""
    try:
        with socket.create_connection((ip, port), timeout=CONNECT_TIMEOUT) as sock:
            sock.settimeout(SAMPLE_TIMEOUT)
            try:
                return sock.recv(200)
            except socket.timeout:
                return b""
    except OSError:
        return None


def scan(network):
    """Returns (ip, port, sample) for every open port found in the network."""
    targets = [(str(ip), port) for ip in network.hosts() for port in PORTS]
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        samples = pool.map(lambda target: probe(*target), targets)
        return [(ip, port, sample) for (ip, port), sample in zip(targets, samples)
                if sample is not None]


def main(network=None):
    network = ipaddress.IPv4Network(network, strict=False) if network else local_network()
    print(f"Scanning {network} on ports {', '.join(map(str, PORTS))} ...")
    found = scan(network)
    if not found:
        print("No devices found. Check that the converters are powered on and on the "
              "same network as this computer.")
        return
    print("Found:")
    for ip, port, sample in found:
        detail = f"sends {sample!r}" if sample else f"sent nothing within {SAMPLE_TIMEOUT} s"
        print(f"  {ip}:{port}  {detail}")
    print("Devices sending weights are likely the scales. Put their address and port "
          "in config.json.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
