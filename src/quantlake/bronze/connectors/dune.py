"""End of v0.6.4 - Dune Analytics generic query connector.

Saved queries hosted on dune.com identified by query_id. The connector
pulls the cached result via dune_client.get_latest_result, applies a
client-side time filter, and renames columns to canonical names if
provided.

Requires DUNE_API_KEY in .env and the dune-client package
(pip install dune-client).
"""
import os
from datetime import datetime

import polars as pl
from dune_client.client import DuneClient

from quantlake.bronze.base import HistoricalConnector
from quantlake.helper import to_utc


class DuneQueryConnector(HistoricalConnector):
    """Generic connector for any Dune Analytics saved query.

    Args:
        query_id: int Dune query id (from dune.com URL).
        table_name: bronze Delta table name.
        timestamp_col: column in the result that holds the event time.
        rename: optional {dune_col: canonical_name} mapping.
        api_key: Dune API key (or DUNE_API_KEY env var).
    """

    def __init__(
        self,
        query_id: int,
        table_name: str,
        timestamp_col: str = "timestamp",
        rename: dict[str, str] | None = None,
        api_key: str | None = None,
    ):
        self.query_id = query_id
        self.TABLE_NAME = table_name
        self.timestamp_col = timestamp_col
        self.rename_map = rename or {}
        self.api_key = api_key or os.getenv("DUNE_API_KEY")
        if not self.api_key:
            raise ValueError("DUNE_API_KEY missing - set it in .env")

    def fetch(self, symbol: str, start: datetime, end: datetime) -> pl.DataFrame:
        client = DuneClient(api_key=self.api_key)
        result = client.get_latest_result(self.query_id)
        rows = result.result.rows

        if not rows:
            return pl.DataFrame(schema={"timestamp": pl.Datetime("us", "UTC")})

        df = pl.DataFrame(rows)

        if self.timestamp_col != "timestamp":
            df = df.rename({self.timestamp_col: "timestamp"})

        # Dune returns "YYYY-MM-DD HH:MM:SS.fff UTC" - strip the suffix.
        if df["timestamp"].dtype == pl.String:
            df = df.with_columns(
                pl.col("timestamp")
                .str.strip_suffix(" UTC")
                .str.to_datetime(format="%Y-%m-%d %H:%M:%S%.f", time_zone="UTC")
                .cast(pl.Datetime("us", "UTC"))
            )
        else:
            df = df.with_columns(pl.col("timestamp").cast(pl.Datetime("us", "UTC")))

        renames = {old: new for old, new in self.rename_map.items()
                   if old in df.columns and new not in df.columns}
        if renames:
            df = df.rename(renames)

        start_utc = to_utc(start)
        end_utc = to_utc(end)
        return df.filter(
            (pl.col("timestamp") >= start_utc) & (pl.col("timestamp") <= end_utc)
        ).sort("timestamp")
