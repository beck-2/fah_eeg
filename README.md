# fah_eeg — Muse 2 + BrainFlow + Godot game

Collect Muse 2 EEG, stream live features, and play low-latency mind-controlled levels.

## Stack

| Layer | Tech | Role |
|---|---|---|
| Acquisition | **BrainFlow** (Python) | Muse 2 BLE → raw EEG |
| Features | `fah-stream` | Band powers, calm/focus/blink @ ~30 Hz |
| Transport | **UDP localhost :14141** | Sub-ms hop to game |
| Game | **Godot 4.7** | Rendering, levels, HUD |

Python owns the headset (proven on Mac/iTerm). Godot owns gameplay and visuals.

## Important: use iTerm for BLE

macOS grants Bluetooth per app. Prefer running Muse scripts from **iTerm2**.

## Setup

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e .
brew install --cask godot   # already installed if you followed along
```

## Play (demo — no headset)

```bash
cd ~/fah_eeg
./scripts/start_stream.sh --demo
./scripts/start_game.sh
# later:
./scripts/stop_stream.sh
```

## Play (live Muse)

```bash
./scripts/start_stream.sh            # or --record to also save CSV
./scripts/start_game.sh
./scripts/stop_stream.sh
```

## Recording / spectrogram

```bash
./scripts/start_record.sh
./scripts/stop_record.sh
./scripts/start_viz.sh
./scripts/stop_viz.sh
./scripts/status.sh
```

## Level 01 — Blink Flash

White screen flashes **red for 500ms** on each blink. Use this to judge detection accuracy before tightening flash duration.

```bash
./scripts/start_stream.sh          # live Muse (iTerm)
./scripts/start_game.sh
# Play Level 01 — Blink Flash
```

Tune: `./scripts/start_stream.sh --blink-z 3.5` (more sensitive) or `--blink-z 5.5`.

## Recording / spectrogram

```text
src/fah_eeg/
  stream.py            # UDP feature streamer (+ --demo)
  record.py / viz_…    # capture tools
game/                  # Godot 4 project
  scripts/eeg_bus.gd   # UDP listener autoload
  scenes/levels/…      # Level 01
scripts/
  start_stream.sh / stop_stream.sh / start_game.sh
  start_record.sh / start_viz.sh / status.sh
```
