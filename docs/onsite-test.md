# On-site test with the real scales

The first test of ScaleApp with the real WT1000 and WT3000i. Everything up to now was tested only with `scaleSimulator.py`, which sends the data formats described in the Weightech manuals. This test checks the hardware one layer at a time (network, indicators, converters, app) and saves evidence along the way.

The indicator and converter settings referred to below are in the README, under *Setting up the scales on-site*.

## What you need

**Things to bring**
- The business PC, or a Windows laptop on the same network as the converters (with a network cable or the business WiFi password)
- The `dist\ScaleApp` folder (built with `build.bat`) on a USB stick
- A few items of known weight: ideally a certified test weight, or a sack or container weighed beforehand
- A phone, to photograph indicator settings and anything unexpected

**Access and people**
- **Someone who can change the indicator settings.** Changing the WT1000's P5 requires restarting the indicator. Some WT3000i menus may be behind the calibration seal. If a setting is sealed, call the scale technician: breaking the INMETRO seal is not something to do yourself.
- **The converters' web page login.** USR devices often use `admin`/`admin` by factory default, but it may have been changed.
- **Do not press the "Reload" button** on either converter: it wipes their configuration.
- **The business WiFi name and password**, in case the USR-W610 needs reconfiguring.
- **About 2–3 hours**, at a quiet time so tests don't interrupt real weighings.

## Steps

Each step has a pass condition. Don't move on until it passes.

1. **Find the converters.** Run `ScaleAppConsole.exe --scan` (or `--scan 192.168.0.0/24` for a specific network).
   - **Pass:** two devices appear, sending lines like `0,012.500,000.000,012.500` (WT1000) and `ST,GS,+00012.50  kg` (WT3000i).
   - **Nothing found:** network problem. Check the cable, the WiFi, the IP range, and the Windows firewall.
   - **Found but sends nothing:** the scale isn't in continuous mode. Go to step 2.
   - **Found but sends garbage:** baud rate or parity mismatch. Go to step 3.
2. **Set the indicators.** Photograph the current settings *before* changing anything, so they can be restored. Then apply the README checklist:
   - WT1000: P5 = 5, P2 = 1 (LCD model only)
   - WT3000i: rS1 04 = `StrEAn`, rS1 03 = 0, rS1 08 = `ALL-P`
3. **Set the converters.** On each converter's web page:
   - Make the serial settings match its scale (same baud rate, 8 data bits, no parity, 1 stop bit).
   - Set the work mode to **TCP Server**.
   - Note the IP address and port. Ideally make the IP fixed.
4. **Fill in `config.json`** (next to the `.exe`) with each scale's `host` and `port`.
5. **Run `ScaleApp.exe`.**
   - **Pass:** both scales show "Connected", and the live weight follows what's on each scale.
6. **Weigh the test items.** Try single items, adding more items to a load, and removing items one at a time.
   - **Pass:** each load appears once, in the window and in the Excel file, with the right weight.
7. **Stress it.**
   - Unplug a converter for 30 seconds, then plug it back in. **Pass:** the app reconnects by itself.
   - Open today's Excel file while weighing, then close it. **Pass:** no records are lost.
   - Restart the PC. **Pass:** the app starts by itself (after the `shell:startup` shortcut from the README is set up).
8. **Let it run for a normal business day.** Then compare the Excel file with the business's own notes.

## If something fails, bring back
- **The whole `logFiles` folder.** Most important: `raw\`, which is exactly what the scales sent, and `app.log`. With these, parsing problems can usually be fixed without another visit.
- **`config.json`.**
- **Photos** of the indicator and converter settings.

## Biggest unknowns, most likely first
1. **The WT3000i's output mode.** Its settings list shows `CoMand` next to the option, which looks like the factory setting. In command mode the scale sends nothing unless asked, so it must be changed to `StrEAn`. Changing it may need the technician.
2. **Whether the W610's WiFi signal is reliable** where it's mounted. The W610 also has an Ethernet port if WiFi isn't good enough.
3. **The converters' current configuration.** They're already installed and cabled (see `img/`), so someone may have configured them before. The scan in step 1 shows what state they're in.
