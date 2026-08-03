"""BrainFlow Muse 2 board helpers."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterator

from brainflow.board_shim import BoardIds, BoardShim, BrainFlowInputParams


MUSE_2_BOARD_ID = BoardIds.MUSE_2_BOARD.value


@dataclass
class MuseConnectionOptions:
    """Optional targeting for Muse 2 discovery."""

    serial_number: str | None = None
    mac_address: str | None = None
    # Muse streaming preset; empty lets BrainFlow use its default.
    other_info: str | None = None
    timeout: int = 15


def build_params(options: MuseConnectionOptions | None = None) -> BrainFlowInputParams:
    options = options or MuseConnectionOptions()
    params = BrainFlowInputParams()
    params.timeout = options.timeout
    if options.serial_number:
        params.serial_number = options.serial_number
    if options.mac_address:
        params.mac_address = options.mac_address
    if options.other_info:
        params.other_info = options.other_info
    return params


def create_board(options: MuseConnectionOptions | None = None) -> BoardShim:
    enable_brainflow_logging()
    return BoardShim(MUSE_2_BOARD_ID, build_params(options))


def enable_brainflow_logging(level: int | None = None) -> None:
    if level is None:
        BoardShim.enable_dev_board_logger()
    else:
        BoardShim.set_log_level(level)


def eeg_channel_names(board_id: int = MUSE_2_BOARD_ID) -> list[str]:
    """Human-readable names for EEG channels when BrainFlow exposes them."""
    descr = BoardShim.get_board_descr(board_id)
    names = descr.get("eeg_names")
    if isinstance(names, str):
        return [n.strip() for n in names.split(",") if n.strip()]
    channels = BoardShim.get_eeg_channels(board_id)
    return [f"ch{i}" for i in channels]


@contextmanager
def muse_session(
    options: MuseConnectionOptions | None = None,
    *,
    streamer_params: str | None = None,
) -> Iterator[BoardShim]:
    """Prepare, stream, and always release a Muse 2 session."""
    board = create_board(options)
    board.prepare_session()
    try:
        board.start_stream(450000, streamer_params or "")
        yield board
    finally:
        try:
            board.stop_stream()
        except Exception:
            pass
        try:
            board.release_session()
        except Exception:
            pass


def wait_for_board_data(
    board: BoardShim,
    *,
    timeout_sec: float = 20.0,
    poll_sec: float = 0.1,
    should_stop: Callable[[], bool] | None = None,
):
    """Block until get_board_data returns samples, or timeout/stop.

    Returns the first non-empty matrix, or None.
    """
    import time

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if should_stop and should_stop():
            return None
        data = board.get_board_data()
        if data.size:
            return data
        time.sleep(poll_sec)
    return None
