"""End of video 2.2 — shared instrument list.

Single source of truth for the symbol universe used across the Binance
arc. Both the historical bootstrap (this module) and the live strategy
(Module 4.3) import from here. One change here, both scripts see it.
"""

from dataclasses import dataclass



# ── top_10_momentum_crypto strategy universe ─────────────────────────────
TOP10 = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT",  "SOLUSDT",  "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
]


# Macro instruments (M5)
@dataclass(frozen=True)
class MacroInstrument:
    """A macro instrument (FX / commodity / index) mapped across sources.

    Dukascopy gives deep spot-ish historical bars; Capital.com gives the
    live CFD feed. Both are normalised into silver/macro_ohlcv on
    Capital's price scale (see applications/historical/macro_silver.py
    introduced in v0.5.4).
    """
    symbol: str         # canonical name (used in bronze/silver/gold partitions)
    duka: str           # Dukascopy instrument code (empty when unavailable)
    capital: str        # Capital.com epic
    price_scale: float  # Dukascopy per-instrument decimal scaling


MACRO_INSTRUMENTS = [
    MacroInstrument("EURUSD", "EURUSD",     "EURUSD",    100_000.0),
    MacroInstrument("GBPUSD", "GBPUSD",     "GBPUSD",    100_000.0),
    MacroInstrument("XAUUSD", "XAUUSD",     "GOLD",        1_000.0),
    MacroInstrument("SPX500", "USA500IDXUSD", "US500",       1_000.0),
    MacroInstrument("WTI",    "LIGHTCMDUSD",  "OIL_CRUDE",   1_000.0),
    # Wheat CFD - no Dukascopy history available; lives on Capital-only.
    MacroInstrument("WHEAT",  "",           "WHEAT",       1_000.0),
]




