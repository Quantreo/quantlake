from abc import ABC, abstractmethod
from datetime import datetime

import polars as pl


class HistoricalConnector(ABC):

    TABLE_NAME: str

    @abstractmethod
    def fetch(self, symbol: str, start: datetime, end: datetime) -> pl.DataFrame:
        """Fetch historical data and return a normalized DataFrame.

        Guaranteed columns: timestamp (Datetime UTC, no nulls).
        All other columns are source-dependent.
        """