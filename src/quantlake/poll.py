"""End of v0.5.2 - Aligned polling loop for REST-based flows.

Symmetric to live.run (M4) but for sources that pull instead of push.
A timeframe-aligned scheduler that fires a user-provided task function.

The task body lives in the application script - poll.run is a clock,
not a framework. Error handling lives in the task (per-symbol try/except
in fx.py, etc.), so poll.run stays minimal.
"""
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from quantlake.helper import TF_SECONDS


def run(task: Callable[[], None], interval: str = "1m", offset_ms: int = 500) -> None:
    """Call ``task`` immediately, then at every ``interval`` boundary
    (+ offset_ms delay). interval must be a key of TF_SECONDS.
    """
    tf_sec = TF_SECONDS[interval]
    print(f"Polling loop started - interval={interval}")

    task()  # fire once on launch so we don't wait the first interval
    while True:
        now = datetime.now(timezone.utc)
        next_open = (int(now.timestamp()) // tf_sec + 1) * tf_sec
        target = datetime.fromtimestamp(next_open, tz=timezone.utc) + timedelta(milliseconds=offset_ms)
        sleep_sec = (target - datetime.now(timezone.utc)).total_seconds()
        if sleep_sec > 0:
            time.sleep(sleep_sec)
        task()
