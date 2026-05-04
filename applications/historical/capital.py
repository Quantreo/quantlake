"""End of v0.5.1 - Capital.com REST historical bootstrap.

Writes bronze/capitalcom_ohlcv only. Single-source, resumable, idempotent.
A composite silver (silver/macro_ohlcv mixing Capital + Dukascopy) comes
in v0.5.4.

Re-running is safe (Delta merge on (symbol, timestamp)).

Usage:
    poetry run python applications/historical/capital.py
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import quantlake.bronze.ingest as bronze
from quantlake.bronze.connectors.capital_rest import CapitalComOHLCVRestConnector
from symbols import MACRO_INSTRUMENTS, MacroInstrument

CAPITAL_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
TABLE = CapitalComOHLCVRestConnector.TABLE_NAME


def _resume_start(symbol: str) -> datetime:
    last = bronze.last_bronze_ts(TABLE, symbol)
    return last + timedelta(minutes=1) if last else CAPITAL_START


def _ingest(inst: MacroInstrument, connector: CapitalComOHLCVRestConnector) -> None:
    now = datetime.now(timezone.utc)
    start = _resume_start(inst.symbol)
    if start >= now:
        print(f"[{inst.symbol}] up to date")
        return

    print(f"[{inst.symbol}] {start.isoformat(timespec='minutes')} -> now ({inst.capital})")
    df = connector.fetch(symbol=inst.capital, start=start, end=now)
    if df.is_empty():
        print(f"[{inst.symbol}]   -> no new rows")
        return

    df = bronze.add_partition_columns(df, symbol=inst.symbol)
    bronze.save(df, TABLE)
    print(f"[{inst.symbol}]   -> {len(df):,} rows")


connector = CapitalComOHLCVRestConnector(timeframe="1m")
for inst in MACRO_INSTRUMENTS:
    try:
        _ingest(inst, connector)
    except Exception as e:
        print(f"[{inst.symbol}] ERROR: {e}")
print("\nDone.")






