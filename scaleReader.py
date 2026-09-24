"""Reads weights from a scale over TCP and turns them into weighing records."""
import json
import logging
import os
import re
import socket
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

CONNECT_TIMEOUT = 5      # seconds to wait for the converter to accept a connection
READ_TIMEOUT = 1         # how often the read loop checks whether it should stop
RECONNECT_MIN = 1        # first retry delay after a lost connection (seconds)
RECONNECT_MAX = 30       # the retry delay doubles up to this limit
MAX_LINE_LENGTH = 4096   # data without a line ending beyond this size is discarded

LINE_END = re.compile(rb"[\r\n]+")
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


@dataclass
class Reading:
    weight: float
    stable: bool


class LineParser:
    """Extracts the weight and the stable flag from one line of scale output.

    Both patterns come from config.json so they can be adapted to the real
    scale's format on-site without changing code. If weight_pattern has a
    group, the group is used as the weight; otherwise the whole match is.
    """

    def __init__(self, stable_pattern, weight_pattern):
        self.stable_re = re.compile(stable_pattern)
        self.weight_re = re.compile(weight_pattern)

    def parse(self, line):
        match = self.weight_re.search(line)
        if not match:
            return None
        try:
            weight = float(match.group(1) if self.weight_re.groups else match.group(0))
        except ValueError:
            return None
        return Reading(weight, bool(self.stable_re.search(line)))


class WeighingDetector:
    """Turns a stream of readings into one record per load placed on the scale.

    A load starts with a stable reading above zero_threshold and ends when the
    scale settles back to zero. The heaviest stable weight seen in between is
    reported, so adding more items to the pile, or taking them off one at a
    time, still gives the full total.

    With a state_file, the load in progress is saved there, so a load that's
    still on the scale when the program stops (or crashes) is recorded exactly
    once, when the scale is next seen back at zero.
    """

    def __init__(self, zero_threshold, state_file=None):
        self.zero_threshold = zero_threshold
        self.state_file = Path(state_file) if state_file else None
        self.peak = self._load_state()  # (weight, timestamp) of the load on the scale

    def feed(self, reading, timestamp):
        """Returns (weight, timestamp) when a load has been removed, else None."""
        if not reading.stable:
            return None
        if reading.weight <= self.zero_threshold:
            return self.flush()
        if self.peak is None or reading.weight > self.peak[0]:
            self._set_peak((reading.weight, timestamp))
        return None

    def flush(self):
        """Ends the current load (if any) and returns it."""
        completed = self.peak
        if completed is not None:
            self._set_peak(None)
        return completed

    def _set_peak(self, peak):
        self.peak = peak
        if not self.state_file:
            return
        if peak is None:
            self.state_file.unlink(missing_ok=True)
            return
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        temp = self.state_file.with_suffix(".tmp")
        weight, timestamp = peak
        temp.write_text(json.dumps({"weight": weight, "timestamp": timestamp.isoformat()}),
                        encoding="utf-8")
        os.replace(temp, self.state_file)

    def _load_state(self):
        if not self.state_file or not self.state_file.exists():
            return None
        try:
            state = json.loads(self.state_file.read_text(encoding="utf-8"))
            peak = (float(state["weight"]), datetime.fromisoformat(state["timestamp"]))
        except (OSError, ValueError, KeyError) as e:
            log.warning("Ignoring unreadable %s: %s", self.state_file, e)
            return None
        log.info("%s: resuming a load of %s left on the scale at %s",
                 self.state_file.stem, peak[0], f"{peak[1]:%Y-%m-%d %H:%M:%S}")
        return peak


class RawLog:
    """Saves the scale's output exactly as received, one file per scale per day.

    Consecutive identical lines are skipped, since scales repeat the same
    reading many times per second.
    """

    def __init__(self, directory, scale_name):
        self.directory = Path(directory)
        self.scale_name = scale_name
        self._last_line = None

    def write(self, timestamp, raw):
        if raw == self._last_line:
            return
        self._last_line = raw
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{timestamp:%Y-%m-%d}_{self.scale_name}.log"
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{timestamp:%H:%M:%S}.{timestamp.microsecond // 1000:03d}  {raw!r}\n")


class ScaleReader(threading.Thread):
    """Keeps a connection to one scale open and reports each completed weighing.

    Runs in its own thread and reconnects automatically whenever the
    connection drops, so a WiFi hiccup doesn't stop the logging.
    on_record(scale_name, weight, timestamp) is called from this thread.

    status ("connecting", "connected" or "disconnected") and last_reading
    ((Reading, timestamp) or None) can be read from other threads for display.
    """

    def __init__(self, name, host, port, parser, detector, on_record, raw_log=None):
        super().__init__(name=f"scale-{name}", daemon=True)
        self.scale_name = name
        self.host = host
        self.port = port
        self.parser = parser
        self.detector = detector
        self.on_record = on_record
        self.raw_log = raw_log
        self.status = "connecting"
        self.last_reading = None
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        delay = RECONNECT_MIN
        while not self._stop_event.is_set():
            try:
                with self._connect() as sock:
                    log.info("%s: connected to %s:%s", self.scale_name, self.host, self.port)
                    self.status = "connected"
                    delay = RECONNECT_MIN
                    self._read_until_disconnected(sock)
            except OSError as e:
                if not self._stop_event.is_set():
                    log.warning("%s: %s - retrying in %d s",
                                self.scale_name, str(e) or type(e).__name__, delay)
            self.status = "disconnected"
            self.last_reading = None
            if self._stop_event.wait(delay):
                break
            delay = min(delay * 2, RECONNECT_MAX)
        # A load still on the scale stays in the detector's state file and is
        # recorded after the next start, once it's removed.
        log.info("%s: stopped", self.scale_name)

    def _connect(self):
        sock = socket.create_connection((self.host, self.port), timeout=CONNECT_TIMEOUT)
        sock.settimeout(READ_TIMEOUT)
        # Notice a dead link (e.g. the converter lost power) instead of waiting forever.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        if hasattr(socket, "SIO_KEEPALIVE_VALS"):  # Windows: first probe after 10 s idle
            sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 10_000, 3_000))
        return sock

    def _read_until_disconnected(self, sock):
        buffer = b""
        while not self._stop_event.is_set():
            try:
                chunk = sock.recv(1024)
            except socket.timeout:
                continue
            if not chunk:
                raise ConnectionError("connection closed by the device")
            # TCP can split or merge the scale's lines, so only complete lines are
            # handled; the unfinished tail waits in the buffer for the next chunk.
            *lines, buffer = LINE_END.split(buffer + chunk)
            for raw in lines:
                self._handle_line(raw)
            if len(buffer) > MAX_LINE_LENGTH:
                log.warning("%s: no line ending in %d bytes of data, discarding it",
                            self.scale_name, len(buffer))
                buffer = b""

    def _handle_line(self, raw):
        text = CONTROL_CHARS.sub("", raw.decode("ascii", errors="replace")).strip()
        if not text:
            return
        now = datetime.now()
        if self.raw_log:
            self.raw_log.write(now, raw)
        reading = self.parser.parse(text)
        if reading is None:
            log.debug("%s: could not read a weight from %r", self.scale_name, text)
            return
        self.last_reading = (reading, now)
        self._emit(self.detector.feed(reading, now))

    def _emit(self, completed):
        if completed is None:
            return
        weight, timestamp = completed
        try:
            self.on_record(self.scale_name, weight, timestamp)
        except Exception:
            log.exception("%s: failed to save a weighing of %s", self.scale_name, weight)
