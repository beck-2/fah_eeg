#!/usr/bin/env bash
# Tiny smoke test: can we open a GUI window from this venv?
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
python - <<'PY'
import traceback
print("smoke: opening plot window", flush=True)
import matplotlib
for backend in ("QtAgg", "TkAgg", "MacOSX"):
    try:
        matplotlib.use(backend, force=True)
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        ax.set_title(f"GUI OK — {backend}")
        ax.plot([0, 1, 2], [0, 1, 0])
        print(f"showing with {backend}", flush=True)
        plt.show()
        print(f"closed {backend}", flush=True)
        break
    except Exception:
        print(f"backend {backend} failed:", flush=True)
        traceback.print_exc()
else:
    raise SystemExit("no GUI backend worked")
PY
