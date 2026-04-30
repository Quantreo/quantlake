from abc import ABC, abstractmethod
from datetime import datetime
from typing import AsyncIterator

import polars as pl


class HistoricalConnector(ABC):

    TABLE_NAME: str

    @abstractmethod
    def fetch(self, symbol: str, start: datetime, end: datetime) -> pl.DataFrame:
        """Fetch historical data and return a normalized DataFrame.

        Guaranteed columns: timestamp (Datetime UTC, no nulls).
        All other columns are source-dependent.
        """


class StreamConnector(ABC):

    TABLE_NAME: str

    @abstractmethod
    async def stream(self, symbols: list[str]) -> AsyncIterator[dict]:
        """Stream live data for multiple symbols over a single connection.

        Yields one dict per closed candle/event. Guaranteed keys:
          - timestamp   : datetime UTC (candle close time)
          - ingested_at : datetime UTC (moment the message was received)
          - symbol      : str
        All other keys are source-dependent.
        """
