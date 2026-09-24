# ScaleApp
Retrieve and save data from industrial scales into an Excel file.

## Case scenario & Problem
The stakeholder operates a business that buys materials on a large scale. For that, they have two industrial scales that weigh the materials; therefore, they can pay accordingly to the amount being offered.

The user must handle client interactions, store materials, pay the seller, and track transaction history daily. To ensure they always have the correct data for all transactions, the user requested a simple desktop system that reads and automatically saves all scale inputs for their records.

The computer and scales are not physically placed close to each other. Having that in mind, an Ethernet connection would be a better solution than a simple COM connection through RS-232 wires. 

## The hardware
The stakeholder has two WeighTech industrial scales: WT1000 and WT3000i. (More details: https://www.weightech.com.br/)

The first one uses an RS-232 to connect to the WiFi through a USR-W610 converter device. The second one connects to a USR-TCP232-306 device using RS-232 and Ethernet wires.

## The software
The serial-to-network converters act as TCP servers: each one exposes its scale's RS-232 output on a network port. The system connects to both scales, keeps reading their output, and records one entry per weighing (a load placed on the scale, settled, and removed) in an Excel file for that day. A network scan helps find the converters' IP addresses during setup.

- **One record per weighing.** A weighing starts with a stable weight above `zero_threshold` and ends when the scale returns to zero. The highest stable weight in between is recorded, so adding items to the pile, or removing them one at a time, still gives the full total.
- **One Excel file per day** (`logFiles/scale_data_YYYY-MM-DD.xlsx`) with the record ID, date, time, scale and weight, plus empty Seller, Material and Notes columns for the user. New rows are only appended, so anything typed in those columns is kept.
- **No lost records.** Each record is first saved to `logFiles/journal/` and then copied to Excel. If the Excel file is open when a weighing happens, the row is added once the file is closed.
- **Loads on the scale when the program closes** are saved in `logFiles/state/` and recorded once, after the next start, when the scale returns to zero.
- **Automatic reconnection** when a scale's connection drops.
- **Raw capture.** Everything each scale sends is saved to `logFiles/raw/`, to check the real data format when the scales are first connected.

| File | Purpose |
|---|---|
| `scaleApp.py` | Main program: window with each scale's status and live weight, today's weighings, and buttons to open the Excel file and records folder |
| `scaleServer.py` | The same without a window (console), plus the network scan (`--scan`) |
| `scaleReader.py` | Scale connection, data parsing and weighing detection |
| `recordStore.py` | Journal and daily Excel files |
| `findScales.py` | Network scan for the converters |
| `scaleSimulator.py` | Two fake scales for testing without hardware |
| `config.json` | Settings (see below) |

# How to run
Requires Python 3.10+.

```
pip install -r requirements.txt
```

**With the simulator** (no hardware needed), in two terminals:
```
python scaleSimulator.py          # add --fast for 10x speed, --flaky to drop connections
python scaleApp.py --simulator    # records go to logFiles/simulator/
```

**With the real scales:**
1. Find the converters: `python scaleServer.py --scan` (or `--scan 192.168.0.0/24` for a specific network). It lists open devices and a sample of what they send.
2. Put each scale's `host` and `port` in `config.json`.
3. Run `python scaleApp.py` (or `python scaleServer.py` for the console version, stopped with Ctrl+C). Only one copy can run at a time.
4. Open `logFiles/raw/` to see the scales' actual output. If weighings aren't being recorded, adjust the `parsing` patterns to match it.

**Tests:** `python -m unittest discover -s tests -t .`

## Settings (`config.json`)
| Setting | Meaning |
|---|---|
| `scales` | Name, IP address (`host`), `port` and `enabled` for each real scale. A scale can have its own `parsing` block if its format differs. |
| `simulator_scales` | The same for the simulator (used with `--simulator`) |
| `parsing.stable_pattern` | Regular expression found only in stable readings (default `ST`) |
| `parsing.weight_pattern` | Regular expression for the weight; the first match in each line is used, or its first group if it has one |
| `zero_threshold` | Weights at or below this count as an empty scale |
| `unit` | Unit shown in the Excel header |
| `output_dir` | Where records and logs are saved |
| `save_raw_data` | Save the scales' raw output to `logFiles/raw/` |

The parsing in `config.json` follows the Weightech technical manuals, but hasn't been checked against the real scales yet:

| Scale | Output format (from the manual) | Parsing |
|---|---|---|
| WT3000i | `ST,GS,+0012.345  kg` (stable) / `US,GS,...` (unstable) | Default: `ST` means stable, first number is the weight |
| WT1000 (LED and LCD, same protocol) | `0,010.000,000.200,009.800`: stability flag (`0` stable, `1` unstable), gross, tare, net | Own `parsing` block: lines starting with `0,` are stable, the **net** weight (4th field) is recorded. To record gross instead, set its `weight_pattern` to `^[01],\\s*([-+]?[\\d.]+)`. |

## Setting up the scales on-site
The indicators and converters must be configured as below, or the app receives nothing or unreadable data. The indicator settings come from the Weightech technical manuals.

**WT1000** (hold `FUNC` for 5 seconds to open the user settings; `ACUM.` selects the parameter and `TARA` changes its value)
- **P5 = 5**: continuous transmission, full mode with gross, tare and net. The indicator must be restarted after changing P5.
- **P3**: baud rate (1 = 9600, 2 = 4800, 3 = 2400, 4 = 1200). It always uses 8 data bits, no parity, 1 stop bit.
- **P2 = 1** (LCD model only): never switch off automatically.

**WT3000i** (menu `rS1`)
- **rS1 04 = `StrEAn`**: continuous transmission. The factory setting appears to be `CoMand`, where the scale sends nothing unless asked. `Auto` doesn't work either, because it never sends the return to zero.
- **rS1 03 = 0**: displayed value, full format with ST/US. Formats 3–8 are "simple" formats without ST/US and won't work.
- **rS1 08 = `ALL-P`**: transmit all the time, so the window can show the weight while it settles.
- **rS1 05 = 4**: 4 readings per second is enough.
- **rS1 01 / rS1 02**: baud rate and `n81` (no parity, 8 data bits, 1 stop bit).

**Converters (USR-W610 and USR-TCP232-306)**, on each converter's web configuration page:
- The serial settings must match its scale: same baud rate, 8 data bits, no parity, 1 stop bit.
- The work mode must be **TCP Server**. Note the IP address and port, and put them in `config.json`. A fixed IP address stops the address from changing.

**Check:** run `python scaleServer.py --scan`. Each scale should appear with a sample like the ones in the table above. Then weigh a few known items and compare them with the Excel file.
