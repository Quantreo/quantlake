"""End of video 2.2 — shared instrument list.

Single source of truth for the symbol universe used across the Binance
arc. Both the historical bootstrap (this module) and the live strategy
(Module 4.3) import from here. One change here, both scripts see it.
"""

# ── top_10_momentum_crypto strategy universe ─────────────────────────────
TOP10 = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT",  "SOLUSDT",  "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
]
