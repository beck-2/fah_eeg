"""Live Muse feature extraction streamed over localhost UDP for the Godot game."""

from __future__ import annotations

import argparse
import json
import signal
import socket
import sys
import time
from pathlib import Path

import numpy as np
from brainflow.board_shim import BoardShim
from brainflow.data_filter import DataFilter, DetrendOperations, WindowOperations

from fah_eeg.blink import BlinkDetector
from fah_eeg.board import (
    MUSE_2_BOARD_ID,
    MuseConnectionOptions,
    eeg_channel_names,
    muse_session,
    wait_for_board_data,
)
from fah_eeg.pidfile import clear_pid, write_pid
from fah_eeg.session_io import SessionRecorder, default_session_path

BANDS = [
    ("delta", 1.0, 4.0),
    ("theta", 4.0, 8.0),
    ("alpha", 8.0, 13.0),
    ("beta", 13.0, 30.0),
    ("gamma", 30.0, 45.0),
]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 14141


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stream Muse 2 band/blink features to Godot over UDP.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--hz",
        type=float,
        default=60.0,
        help="Feature emit rate for calm/focus packets (default 60). Blink events are immediate.",
    )
    parser.add_argument("--window-sec", type=float, default=1.5)
    parser.add_argument("--serial-number", default=None)
    parser.add_argument("--mac-address", default=None)
    parser.add_argument("--preset", default=None)
    parser.add_argument("--pid-file", type=Path, default=None)
    parser.add_argument(
        "--record",
        action="store_true",
        help="Also write a full CSV session while streaming.",
    )
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--blink-z",
        type=float,
        default=3.8,
        help="BrainFlow detect_peaks_z_score threshold (default 3.8). Lower = more sensitive.",
    )
    parser.add_argument(
        "--blink-refractory",
        type=float,
        default=0.32,
        help="Minimum seconds between blink events (default 0.32).",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="No headset — emit synthetic oscillating features for UI testing.",
    )
    return parser.parse_args(argv)


def band_powers(signal: np.ndarray, sampling_rate: int) -> dict[str, float]:
    if len(signal) < sampling_rate // 2:
        return {name: 0.0 for name, _, _ in BANDS}

    data = signal.astype(np.float64).copy()
    DataFilter.detrend(data, DetrendOperations.CONSTANT.value)
    nfft = DataFilter.get_nearest_power_of_two(sampling_rate)
    overlap = nfft // 2
    try:
        psd = DataFilter.get_psd_welch(
            data,
            nfft,
            overlap,
            sampling_rate,
            WindowOperations.HANNING.value,
        )
    except Exception:
        return {name: 0.0 for name, _, _ in BANDS}

    freqs = np.asarray(psd[1])
    dens = np.asarray(psd[0])
    integrate = getattr(np, "trapezoid", None) or np.trapz
    out: dict[str, float] = {}
    for name, lo, hi in BANDS:
        mask = (freqs >= lo) & (freqs < hi)
        out[name] = float(integrate(dens[mask], freqs[mask])) if np.any(mask) else 0.0
    return out


def relative_bands(powers: dict[str, float]) -> dict[str, float]:
    total = sum(powers.values()) + 1e-18
    return {k: v / total for k, v in powers.items()}


def ema(prev: float | None, value: float, alpha: float) -> float:
    if prev is None:
        return value
    return prev * (1.0 - alpha) + value * alpha


def send_json(sock: socket.socket, host: str, port: int, payload: dict) -> None:
    sock.sendto(json.dumps(payload, separators=(",", ":")).encode("utf-8"), (host, port))


def demo_loop(args: argparse.Namespace) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    stop = {"flag": False}

    def _stop(signum: int, _frame: object) -> None:
        print(f"\nReceived {signal.Signals(signum).name} — stopping demo stream…", flush=True)
        stop["flag"] = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    write_pid(args.pid_file)
    print(f"Demo EEG stream → udp://{args.host}:{args.port} @ {args.hz:g} Hz", flush=True)
    print("Demo blinks ~ every 2.5s", flush=True)
    t0 = time.monotonic()
    interval = 1.0 / max(args.hz, 1.0)
    last_blink_slot = -1
    try:
        while not stop["flag"]:
            t = time.monotonic() - t0
            calm = 0.5 + 0.45 * np.sin(t * 0.7)
            focus = 0.5 + 0.45 * np.sin(t * 1.3 + 1.0)
            slot = int(t / 2.5)
            if slot != last_blink_slot and slot > 0:
                last_blink_slot = slot
                send_json(
                    sock,
                    args.host,
                    args.port,
                    {
                        "type": "blink_event",
                        "ts": time.time(),
                        "demo": True,
                        "blink": 1.0,
                        "blink_z": 6.0,
                        "n": slot,
                    },
                )
                print(f"demo blink #{slot} @ t={t:.2f}s", flush=True)
            send_json(
                sock,
                args.host,
                args.port,
                {
                    "type": "eeg_features",
                    "ts": time.time(),
                    "demo": True,
                    "bands": {
                        "delta": float(0.35 + 0.1 * np.sin(t)),
                        "theta": float(0.2 + 0.05 * np.cos(t * 0.8)),
                        "alpha": float(0.15 + 0.25 * calm),
                        "beta": float(0.15 + 0.25 * focus),
                        "gamma": float(0.05),
                    },
                    "calm": float(np.clip(calm, 0, 1)),
                    "focus": float(np.clip(focus, 0, 1)),
                    "blink": 0.0,
                    "blink_z": 0.0,
                    "channels": {},
                },
            )
            time.sleep(interval)
    finally:
        clear_pid(args.pid_file)
        sock.close()


def live_loop(args: argparse.Namespace) -> None:
    sampling_rate = BoardShim.get_sampling_rate(MUSE_2_BOARD_ID)
    eeg_channels = BoardShim.get_eeg_channels(MUSE_2_BOARD_ID)
    names = eeg_channel_names()
    window_samples = int(args.window_sec * sampling_rate)
    options = MuseConnectionOptions(
        serial_number=args.serial_number,
        mac_address=args.mac_address,
        other_info=args.preset,
    )
    out = (args.out or default_session_path("muse2_stream")).resolve() if args.record else None

    name_to_ch = {
        (names[i] if i < len(names) else f"ch{c}"): c for i, c in enumerate(eeg_channels)
    }
    front_chs = [name_to_ch[n] for n in ("AF7", "AF8") if n in name_to_ch]
    if len(front_chs) < 2:
        front_chs = list(eeg_channels[1:3]) if len(eeg_channels) >= 3 else list(eeg_channels)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 64 * 1024)
    except OSError:
        pass

    stop = {"flag": False}

    def _stop(signum: int, _frame: object) -> None:
        print(f"\nReceived {signal.Signals(signum).name} — stopping stream…", flush=True)
        stop["flag"] = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    write_pid(args.pid_file)

    buffers = {ch: np.zeros(0, dtype=np.float64) for ch in eeg_channels}
    detector = BlinkDetector(
        sampling_rate=sampling_rate,
        threshold=args.blink_z,
        refractory_sec=args.blink_refractory,
    )
    calm_s: float | None = None
    focus_s: float | None = None
    interval = 1.0 / max(args.hz, 1.0)
    next_emit = time.monotonic()
    blink_count = 0

    print(f"Connecting Muse 2 for game stream → udp://{args.host}:{args.port}", flush=True)
    print(
        "Blink: BrainFlow notch + bandpass(0.5–10Hz) + detect_peaks_z_score "
        f"thr={args.blink_z:g} refractory={args.blink_refractory:g}s "
        f"front={[names[eeg_channels.index(c)] if c in eeg_channels else c for c in front_chs]}",
        flush=True,
    )
    recorder: SessionRecorder | None = None
    try:
        with muse_session(options) as board:
            first = wait_for_board_data(
                board,
                timeout_sec=25.0,
                should_stop=lambda: stop["flag"],
            )
            if first is None or not first.size:
                raise RuntimeError("No samples received from Muse 2.")
            if out is not None:
                recorder = SessionRecorder(out)
                recorder.write_matrix(first)
                print(f"Also recording CSV → {out}", flush=True)

            for ch in eeg_channels:
                buffers[ch] = first[ch].astype(np.float64).copy()

            af7_i, af8_i = front_chs[0], front_chs[1] if len(front_chs) > 1 else front_chs[0]
            detector.push_channels(first[af7_i], first[af8_i], time.monotonic())

            print("Streaming · blink events immediate · features @{:.0f} Hz".format(args.hz), flush=True)

            while not stop["flag"]:
                data = board.get_board_data()
                now = time.monotonic()

                if data.size:
                    if recorder is not None:
                        recorder.write_matrix(data)
                    for ch in eeg_channels:
                        buffers[ch] = np.concatenate([buffers[ch], data[ch]])
                        if len(buffers[ch]) > window_samples * 3:
                            buffers[ch] = buffers[ch][-window_samples * 3 :]

                    fired, score = detector.push_channels(data[af7_i], data[af8_i], now)
                    if fired:
                        blink_count += 1
                        send_json(
                            sock,
                            args.host,
                            args.port,
                            {
                                "type": "blink_event",
                                "ts": time.time(),
                                "demo": False,
                                "blink": 1.0,
                                "blink_z": score,
                                "n": blink_count,
                            },
                        )
                        print(f"blink #{blink_count} score={score:.2f}", flush=True)

                if now >= next_emit:
                    next_emit = now + interval
                    if all(len(buffers[ch]) >= window_samples for ch in eeg_channels):
                        post_idx = (
                            [eeg_channels[0], eeg_channels[3]]
                            if len(eeg_channels) >= 4
                            else list(eeg_channels)
                        )
                        post = np.mean([buffers[ch][-window_samples:] for ch in post_idx], axis=0)
                        front = np.mean([buffers[ch][-window_samples:] for ch in front_chs], axis=0)
                        post_rel = relative_bands(band_powers(post, sampling_rate))
                        front_rel = relative_bands(band_powers(front, sampling_rate))
                        raw_calm = float(np.clip(post_rel["alpha"] / 0.25, 0.0, 1.0))
                        raw_focus = float(np.clip(front_rel["beta"] / 0.20, 0.0, 1.0))
                        calm_s = ema(calm_s, raw_calm, 0.15)
                        focus_s = ema(focus_s, raw_focus, 0.15)
                        send_json(
                            sock,
                            args.host,
                            args.port,
                            {
                                "type": "eeg_features",
                                "ts": time.time(),
                                "demo": False,
                                "bands": post_rel,
                                "calm": float(calm_s if calm_s is not None else raw_calm),
                                "focus": float(focus_s if focus_s is not None else raw_focus),
                                "blink": 0.0,
                                "blink_z": 0.0,
                                "blinks": blink_count,
                                "samples": int(recorder.samples_written) if recorder else 0,
                            },
                        )

                if not data.size:
                    time.sleep(0.002)
    finally:
        if recorder is not None:
            print(f"Wrote {recorder.samples_written} samples → {out}", flush=True)
            recorder.close()
        clear_pid(args.pid_file)
        sock.close()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.demo:
            demo_loop(args)
        else:
            live_loop(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
