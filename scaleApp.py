"""ScaleApp window: records every weighing while showing the scales and today's records.

    python scaleApp.py              read the scales listed in config.json
    python scaleApp.py --simulator  read scaleSimulator.py running on this computer
"""
import argparse
import os
import queue
import sys
import tkinter as tk
from datetime import date, datetime
from tkinter import messagebox, ttk

import scaleServer

REFRESH_MS = 200
STALE_READING_SECONDS = 3  # hide the live weight once a scale stops sending

FONT = "Segoe UI"
STATUS_STYLES = {
    "connecting": ("Connecting...", "#9a6700"),
    "connected": ("Connected", "#1a7f37"),
    "disconnected": ("Not connected - retrying", "#cf222e"),
}


class ScaleAppWindow:
    def __init__(self, root, store, readers, unit, new_records):
        self.root = root
        self.store = store
        self.readers = readers
        self.unit = unit
        self.new_records = new_records  # filled by the scale threads, emptied by refresh()
        self.day = date.today()

        root.minsize(560, 460)
        root.protocol("WM_DELETE_WINDOW", self.close)
        ttk.Style().configure("Treeview", font=(FONT, 11), rowheight=26)
        ttk.Style().configure("Treeview.Heading", font=(FONT, 10, "bold"))

        scales = ttk.LabelFrame(root, text="Scales", padding=(12, 6))
        scales.pack(fill="x", padx=12, pady=(12, 6))
        scales.columnconfigure(1, weight=1)
        self.scale_rows = []
        for row, reader in enumerate(readers):
            ttk.Label(scales, text=reader.scale_name, font=(FONT, 13, "bold")).grid(
                row=row, column=0, sticky="w", padx=(0, 16), pady=4)
            status = tk.Label(scales, font=(FONT, 10), anchor="w")
            status.grid(row=row, column=1, sticky="w")
            weight = tk.Label(scales, font=(FONT, 20, "bold"), anchor="e", width=11)
            weight.grid(row=row, column=2, sticky="e")
            state = tk.Label(scales, font=(FONT, 10), anchor="w", width=8, fg="#57606a")
            state.grid(row=row, column=3, sticky="w", padx=(8, 0))
            self.scale_rows.append((reader, status, weight, state))

        self.records_frame = ttk.LabelFrame(root, padding=(12, 6))
        self.records_frame.pack(fill="both", expand=True, padx=12, pady=6)
        columns = [("id", "Record", 130, "w"), ("time", "Time", 90, "center"),
                   ("scale", "Scale", 130, "w"), ("weight", f"Weight ({unit})", 120, "e")]
        self.table = ttk.Treeview(self.records_frame, columns=[c[0] for c in columns],
                                  show="headings", selectmode="browse")
        for column, heading, width, anchor in columns:
            self.table.heading(column, text=heading, anchor=anchor)
            self.table.column(column, width=width, anchor=anchor)
        scrollbar = ttk.Scrollbar(self.records_frame, orient="vertical",
                                  command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        buttons = ttk.Frame(root)
        buttons.pack(fill="x", padx=12, pady=(0, 4))
        ttk.Button(buttons, text="Open today's Excel file",
                   command=self.open_todays_workbook).pack(side="left")
        ttk.Button(buttons, text="Open records folder",
                   command=lambda: os.startfile(store.output_dir)).pack(side="left", padx=8)
        self.message = tk.Label(root, anchor="w", justify="left", font=(FONT, 9),
                                fg="#57606a", wraplength=520)
        self.message.pack(fill="x", padx=12, pady=(0, 10))
        root.bind("<Configure>", lambda e: self.message.configure(
            wraplength=max(200, root.winfo_width() - 24)))

        self.show_day(self.day)
        self.refresh()

    def show_day(self, day):
        self.day = day
        self.table.delete(*self.table.get_children())
        for record in self.store.records_for(day):
            self.add_row(record)
        self.update_count()

    def add_row(self, record):
        # The same record can come from both the journal and the queue at startup.
        if self.table.exists(record["id"]):
            return
        timestamp = datetime.fromisoformat(record["timestamp"])
        self.table.insert("", 0, iid=record["id"], values=(
            record["id"], f"{timestamp:%H:%M:%S}", record["scale"],
            f"{float(record['weight']):.2f}"))

    def update_count(self):
        count = len(self.table.get_children())
        self.records_frame.configure(text=f"Today's weighings ({count})")

    def refresh(self):
        if date.today() != self.day:
            self.show_day(date.today())  # past midnight: start a fresh list
        while True:
            try:
                record = self.new_records.get_nowait()
            except queue.Empty:
                break
            if datetime.fromisoformat(record["timestamp"]).date() == self.day:
                self.add_row(record)
                self.table.selection_set(record["id"])  # highlight the newest weighing
                self.table.see(record["id"])
            self.update_count()

        now = datetime.now()
        for reader, status, weight, state in self.scale_rows:
            text, color = STATUS_STYLES[reader.status]
            status.configure(text=f"● {text}", fg=color)
            last = reader.last_reading
            if last and (now - last[1]).total_seconds() < STALE_READING_SECONDS:
                reading = last[0]
                weight.configure(text=f"{reading.weight:.2f} {self.unit}")
                state.configure(text="stable" if reading.stable else "settling")
            else:
                weight.configure(text="—")
                state.configure(text="")

        blocked = self.store.unsynced_files
        if blocked:
            self.message.configure(
                fg="#9a6700",
                text=f"{', '.join(blocked)} can't be updated right now (is it open in "
                     "Excel?). New weighings are kept safe and will be added once it's "
                     "closed.")
        else:
            self.message.configure(fg="#57606a",
                                   text=f"Records are saved in {self.store.output_dir}")
        self.root.after(REFRESH_MS, self.refresh)

    def sync_periodically(self):
        self.store.sync()
        self.root.after(scaleServer.SYNC_INTERVAL * 1000, self.sync_periodically)

    def open_todays_workbook(self):
        path = self.store.workbook_path(date.today())
        if path.exists():
            os.startfile(path)
        else:
            messagebox.showinfo("No weighings yet", "Nothing has been recorded today yet.",
                                parent=self.root)

    def close(self):
        if not messagebox.askyesno(
                "Close ScaleApp?",
                "Weighings are not recorded while ScaleApp is closed.\n\nClose it anyway?",
                icon="warning", default="no", parent=self.root):
            return
        self.root.configure(cursor="watch")
        self.root.update()
        scaleServer.stop_logging(self.store, self.readers)
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description="Record weighings from the scales.")
    parser.add_argument("--simulator", action="store_true",
                        help="read from scaleSimulator.py instead of the real scales")
    parser.add_argument("--config", default=scaleServer.app_dir() / "config.json",
                        help="settings file (default: config.json next to the program)")
    args = parser.parse_args()

    try:  # sharp text on scaled (high-DPI) screens instead of blurry, stretched text
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (ImportError, AttributeError, OSError):
        pass
    root = tk.Tk()
    root.title("ScaleApp - SIMULATOR" if args.simulator else "ScaleApp")
    root.withdraw()  # stay hidden until everything has started

    def fail(message):
        messagebox.showerror("ScaleApp", message)
        root.destroy()

    try:
        config = scaleServer.load_config(args.config)
        output_dir = scaleServer.output_dir_for(config, args.simulator)
        scaleServer.setup_logging(output_dir, console=sys.stderr is not None)
    except (OSError, ValueError, KeyError) as e:
        return fail(f"Could not read the settings file {args.config}:\n\n{e!r}")

    lock = scaleServer.acquire_single_instance(output_dir)
    if lock is None:
        return fail("ScaleApp is already running.\n\nLook for its window on the taskbar.")

    new_records = queue.Queue()
    try:
        store, readers = scaleServer.start_logging(config, output_dir, args.simulator,
                                                   on_record=new_records.put)
    except (OSError, ValueError, KeyError) as e:
        return fail(f"Could not start. Check the settings file {args.config}:\n\n{e!r}")
    if not readers:
        return fail(f"No scales are enabled in the settings file {args.config}.")

    window = ScaleAppWindow(root, store, readers, config["unit"], new_records)
    window.sync_periodically()
    root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()
