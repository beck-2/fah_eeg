# fah_eeg — Muse 2 + BrainFlow

Phase 1: collect Muse 2 EEG on a Mac and watch a live band-power spectrogram. Game logic comes later.

## Stack

- **BrainFlow** (`MUSE_2_BOARD` / id 38) — native BLE, no dongle
- **Python 3.11+** (this repo uses 3.13 in `.venv`)
- **pyqtgraph + PyQt6** — live visualization

## Important: use iTerm for BLE

macOS grants Bluetooth per app. Run recording and visualization from **iTerm2** (not Cursor’s terminal or Apple Terminal) so CoreBluetooth can talk to the Muse.

```bash
# From anywhere, launch a command in iTerm with the project venv:
./scripts/run_in_iterm.sh fah-record --seconds 30
./scripts/run_in_iterm.sh fah-spectrogram
```

Or open iTerm yourself, `cd` into this repo, `source .venv/bin/activate`, then run the same commands.

## Setup

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Power on the Muse 2, wear it with good contact, and quit the Muse mobile app if it’s connected.

## Record a session

```bash
./scripts/run_in_iterm.sh fah-record --seconds 60
# → data/sessions/muse2_<utc-timestamp>.csv
```

If discovery fails:

```bash
./scripts/run_in_iterm.sh fah-record --seconds 30 --serial-number Muse-XXXX
```

## Live spectrogram

```bash
./scripts/run_in_iterm.sh fah-spectrogram
# optional: --channel 0..3  (TP9 / AF7 / AF8 / TP10 typically)
```

Shows scrolling log-power for delta / theta / alpha / beta / gamma plus a current bar chart. Close the window to stop the stream.

## Mac Bluetooth checklist

1. Muse powered on and charged  
2. System Settings → Privacy & Security → Bluetooth → allow **iTerm**  
3. Prefer macOS 12.3+  
4. Only one client connected to the Muse at a time  

## Layout

```text
src/fah_eeg/
  board.py             # Muse 2 session helpers
  record.py            # CSV recorder CLI
  viz_spectrogram.py   # live band spectrogram
scripts/run_in_iterm.sh
data/sessions/         # recordings (gitignored)
```
