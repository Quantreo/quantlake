import lzma, struct, urllib.request

URL = "https://datafeed.dukascopy.com/datafeed/USDJPY/2024/00/15/BID_candles_min_1.bi5"
RECORD = struct.Struct(">IIIIIf")

with urllib.request.urlopen(URL) as r:
    raw = r.read()
blob = lzma.decompress(raw, format=lzma.FORMAT_AUTO)
t, o, c, l, h, v = RECORD.unpack_from(blob, 0)
print(f"raw close = {c}")   # par exemple 145820