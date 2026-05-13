"""Scan data/{bronze,silver,gold}/ and list Delta tables.

A Delta table is any directory containing a ``_delta_log/`` subdir. Tables can
be nested one level (e.g. ``gold/top10_crypto/5m``) — we report the relative
path from the layer root as the table name.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from deltalake import DeltaTable

LAYERS = ("bronze", "silver", "gold")


@dataclass
class TableInfo:
    layer: str
    name: str          # relative path from layer root, e.g. "top10_crypto/5m"
    path: str          # absolute path
    rows: int | None
    last_update: str | None  # ISO 8601
    symbols: list[str]


def _find_delta_dirs(root: Path) -> list[Path]:
    """Return every directory under root (inclusive) that is a Delta table."""
    if not root.exists():
        return []
    return [p.parent for p in root.rglob("_delta_log") if p.is_dir()]


def _table_symbols(path: Path) -> list[str]:
    """Extract symbol partitions from directory names."""
    return sorted(
        p.name.split("=", 1)[1]
        for p in path.iterdir()
        if p.is_dir() and p.name.startswith("symbol=")
    )


def _table_stats(path: Path) -> tuple[int | None, str | None]:
    """Return (row_count, last_update_iso) reading Delta metadata only."""
    try:
        dt = DeltaTable(str(path))
        rows = None
        try:
            actions = dt.get_add_actions(flatten=True).to_pydict()
            if "num_records" in actions:
                rows = int(sum(v for v in actions["num_records"] if v is not None))
        except Exception:
            rows = None

        history = dt.history(limit=1)
        ts = history[0].get("timestamp") if history else None
        last_update = (
            datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
            if ts is not None
            else None
        )
        return rows, last_update
    except Exception:
        return None, None


def scan(data_root: Path) -> list[TableInfo]:
    """Return every Delta table under data_root/{bronze,silver,gold}/."""
    out: list[TableInfo] = []
    for layer in LAYERS:
        layer_root = data_root / layer
        for table_dir in _find_delta_dirs(layer_root):
            rows, last_update = _table_stats(table_dir)
            out.append(
                TableInfo(
                    layer=layer,
                    name=str(table_dir.relative_to(layer_root)).replace("\\", "/"),
                    path=str(table_dir),
                    rows=rows,
                    last_update=last_update,
                    symbols=_table_symbols(table_dir),
                )
            )
    return out


def tables_for_layer(data_root: Path, layer: str) -> list[TableInfo]:
    if layer not in LAYERS:
        return []
    return [t for t in scan(data_root) if t.layer == layer]


def resolve(data_root: Path, layer: str, name: str) -> Path | None:
    """Return the absolute path of a table, or None if not a valid Delta table."""
    if layer not in LAYERS:
        return None
    candidate = (data_root / layer / name).resolve()
    layer_root = (data_root / layer).resolve()
    # Prevent path traversal outside the layer.
    if not str(candidate).startswith(str(layer_root)):
        return None
    if not DeltaTable.is_deltatable(str(candidate)):
        return None
    return candidate
