"""End of v0.5.2 - Minimal poll.run demo.

Prints UTC time at every minute boundary (+ 500ms offset). Watch the
seconds align to .500 after the first call.

Run:
    poetry run python examples/live/poll_demo.py
"""
from datetime import datetime, timezone

import quantlake.poll as poll


def show_time():
    print(f"It is now {datetime.now(timezone.utc):%H:%M:%S.%f}")


poll.run(show_time, interval="1m", offset_ms=500)
