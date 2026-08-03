# Game (Godot 4)

Low-latency stack:

```text
Muse 2 → BrainFlow (Python) → band/blink features @ ~30 Hz
       → UDP 127.0.0.1:14141 → Godot 4 (render + levels)
```

## Why this stack

- **BrainFlow stays in Python** — BLE on Mac already works in this repo / iTerm.
- **Godot 4** — fast 2D iteration, free, easy level scenes, good for prototypes that can grow.
- **Localhost UDP** — sub-millisecond hop; game never blocks on BLE.

## Run (demo, no headset)

```bash
# terminal A (prefer iTerm)
./scripts/start_stream.sh --demo

# terminal B
./scripts/start_game.sh
```

## Run (live Muse)

```bash
./scripts/start_stream.sh          # BLE — use iTerm
./scripts/start_game.sh
./scripts/stop_stream.sh           # when done
```

Optional: `./scripts/start_stream.sh --record` also writes a CSV under `data/sessions/`.

## Level 01 — Blink Flash

White screen turns **red for 500ms** on each detected blink (AF7/AF8 EOG spike).

Blink events are sent **immediately** from Python when a sample batch crosses the z-threshold (not waiting for the calm/focus feature tick).

Tune sensitivity:
```bash
./scripts/start_stream.sh --blink-z 3.5    # more sensitive
./scripts/start_stream.sh --blink-z 5.5    # less sensitive
```

## Packet shapes

```json
{
  "type": "eeg_features",
  "ts": 1710000000.0,
  "demo": false,
  "calm": 0.0,
  "focus": 0.0,
  "blink": 0.0,
  "bands": {"delta": 0.4, "theta": 0.2, "alpha": 0.2, "beta": 0.15, "gamma": 0.05},
  "channels": {"TP9": {"alpha": 0.1}, "...": {}}
}
```
