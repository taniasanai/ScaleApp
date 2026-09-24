"""ScaleApp: logs every weighing from the industrial scales to a daily Excel file.

    python scaleServer.py              read the scales listed in config.json
    python scaleServer.py --simulator  read scaleSimulator.py running on this computer
    python scaleServer.py --scan       search the network for the scales' converters
"""
import argparse
import json
import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import findScales
from recordStore import RecordStore
from scaleReader import LineParser, RawLog, ScaleReader, WeighingDetector

SYNC_INTERVAL = 30  # seconds between retries of Excel updates that failed (e.g. file open)

log = logging.getLogger("scaleapp")


def app_dir():
    """Folder holding config.json and logFiles: next to the .exe once packaged."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def setup_logging(output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s",
                                  "%Y-%m-%d %H:%M:%S")
    console = logging.StreamHandler()
    log_file = RotatingFileHandler(output_dir / "app.log", maxBytes=1_000_000,
                                   backupCount=5, encoding="utf-8")
    for handler in (console, log_file):
        handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[console, log_file])


def create_readers(config, scales, on_record, output_dir):
    readers = []
    for scale in scales:
        if not scale.get("enabled", True):
            continue
        # A scale can override the default patterns, since the two models may differ.
        parsing = {**config["parsing"], **scale.get("parsing", {})}
        raw_log = RawLog(output_dir / "raw", scale["name"]) if config["save_raw_data"] else None
        readers.append(ScaleReader(
            scale["name"], scale["host"], scale["port"],
            LineParser(parsing["stable_pattern"], parsing["weight_pattern"]),
            WeighingDetector(config["zero_threshold"]),
            on_record, raw_log))
    return readers


def main():
    parser = argparse.ArgumentParser(description="Log weighings from the scales to Excel.")
    parser.add_argument("--simulator", action="store_true",
                        help="read from scaleSimulator.py instead of the real scales")
    parser.add_argument("--scan", nargs="?", const="auto", metavar="NETWORK",
                        help="search a network (default: this computer's) for the scales "
                             "and exit")
    parser.add_argument("--config", type=Path, default=app_dir() / "config.json",
                        help="settings file (default: config.json next to the program)")
    args = parser.parse_args()

    if args.scan:
        findScales.main(None if args.scan == "auto" else args.scan)
        return

    config = json.loads(args.config.read_text(encoding="utf-8"))
    output_dir = app_dir() / config["output_dir"]
    if args.simulator:
        output_dir /= "simulator"  # keep test data away from the real records
    setup_logging(output_dir)

    unit = config["unit"]
    store = RecordStore(output_dir, unit)
    store.sync_recent()

    def save(scale, weight, timestamp):
        store.add(scale, weight, timestamp)
        log.info("%s: recorded %s %s", scale, weight, unit)

    scales = config["simulator_scales"] if args.simulator else config["scales"]
    readers = create_readers(config, scales, save, output_dir)
    if not readers:
        log.error("No scales are enabled in %s", args.config)
        return

    log.info("Logging %s to %s - press Ctrl+C to stop",
             ", ".join(r.scale_name for r in readers), output_dir)
    for reader in readers:
        reader.start()
    try:
        while True:
            time.sleep(SYNC_INTERVAL)
            store.sync()
    except KeyboardInterrupt:
        log.info("Stopping...")
    for reader in readers:
        reader.stop()
    for reader in readers:
        reader.join(timeout=5)
    store.sync()


if __name__ == "__main__":
    main()
