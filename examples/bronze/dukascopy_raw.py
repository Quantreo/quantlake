"""End of v0.5.3 - Dukascopy raw .bi5 download + parse, no connector.

Shows the URL pattern (month 0-indexed!), LZMA decompression, and the
struct format used to parse the binary records. The integer prices
have to be divided by `price_scale` to get the actual float prices.
For EURUSD, price_scale = 100_000 (5 decimals).

Run:
    poetry run python examples/bronze/dukascopy_raw.py
"""
import lzma
import struct
import urllib.request
from datetime import datetime, timezone

# URL pattern: {base}/{instr}/{YYYY}/{MM-1:02d}/{DD:02d}/{side}_candles_min_1.bi5
# /!\ The month is 0-indexed - January is "00", December is "11".
URL = "https://datafeed.dukascopy.com/datafeed/EURUSD/2024/00/15/BID_candles_min_1.bi5"

# 24-byte record: sec_from_day_start, open, close, low, high, volume
# Big-endian, 5 unsigned ints + 1 float32. Prices are scaled integers.
RECORD = struct.Struct(">IIIIIf")
PRICE_SCALE = 100_000.0  # EURUSD: 5 decimals -> divide raw by 100_000

# 1. Download the binary file.
print(f"GET {URL}")
with urllib.request.urlopen(URL, timeout=30) as r:
    raw = r.read()
print(f"compressed   : {len(raw):,} bytes")

# 2. Decompress (LZMA-alone format).
blob = lzma.decompress(raw, format=lzma.FORMAT_AUTO)
records = len(blob) // RECORD.size
print(f"decompressed : {len(blob):,} bytes  ({records} records of {RECORD.size} bytes)")

# 3. Parse first 3 records, show raw integer prices then decoded floats.
day_start = int(datetime(2024, 1, 15, tzinfo=timezone.utc).timestamp())
print("\nfirst 3 records (raw, then decoded):")
for i in range(3):
    t, o, c, l, h, v = RECORD.unpack_from(blob, i * RECORD.size)
    ts = datetime.fromtimestamp(day_start + t, tz=timezone.utc)
    print(f"  raw : t={t:5d}  o={o:6d}  c={c:6d}  l={l:6d}  h={h:6d}  v={v}")
    print(f"  dec : {ts:%Y-%m-%d %H:%M:%S}  o={o/PRICE_SCALE:.5f}  c={c/PRICE_SCALE:.5f}  l={l/PRICE_SCALE:.5f}  h={h/PRICE_SCALE:.5f}")
