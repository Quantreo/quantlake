"""Read Delta tables for the dashboard via DuckDB (schema + paginated data)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
from deltalake import DeltaTable

_NUMERIC_DTYPES = {
    "TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT",
    "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT",
    "FLOAT", "DOUBLE", "DECIMAL",
}


def _connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute("INSTALL delta; LOAD delta;")
    # Force UTC so timestamp columns are never re-rendered in the server's
    # local timezone. The whole medallion is UTC by convention.
    con.execute("SET TimeZone='UTC';")
    return con


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _is_numeric(dtype_str: str) -> bool:
    s = dtype_str.upper()
    return any(n in s for n in _NUMERIC_DTYPES)


def _clean_dtype(raw: str) -> str:
    """Turn 'PrimitiveType("double")' into 'double'."""
    if raw.startswith("PrimitiveType(") and raw.endswith(")"):
        return raw[len("PrimitiveType("): -1].strip('"')
    return raw


def schema(table_path: Path) -> list[dict[str, Any]]:
    """Return column metadata: [{column, dtype, numeric}]."""
    dt = DeltaTable(str(table_path))
    fields = dt.schema().fields
    result = []
    for f in fields:
        dtype = _clean_dtype(str(f.type))
        result.append({"column": f.name, "dtype": dtype, "numeric": _is_numeric(dtype)})
    return result


def _filter_clause(
    symbols: list[str] | None,
    ts_from: str | None = None,
    ts_to: str | None = None,
    ts_col: str = "timestamp",
) -> tuple[str, list[Any]]:
    conds: list[str] = []
    params: list[Any] = []
    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        conds.append(f"symbol IN ({placeholders})")
        params.extend(symbols)
    if ts_from:
        conds.append(f"{_quote_ident(ts_col)} >= CAST(? AS TIMESTAMP)")
        params.append(ts_from)
    if ts_to:
        conds.append(f"{_quote_ident(ts_col)} <= CAST(? AS TIMESTAMP)")
        params.append(ts_to)
    if not conds:
        return "", []
    return "WHERE " + " AND ".join(conds), params


def row_count(
    table_path: Path,
    symbols: list[str] | None = None,
    ts_from: str | None = None,
    ts_to: str | None = None,
) -> int:
    con = _connect()
    where, params = _filter_clause(symbols, ts_from, ts_to)
    sql = f"SELECT COUNT(*) FROM delta_scan('{table_path}') {where}"
    return int(con.execute(sql, params).fetchone()[0])


def page(
    table_path: Path,
    *,
    symbols: list[str] | None = None,
    columns: list[str] | None = None,
    page_num: int = 1,
    page_size: int = 50,
    order_by: str | None = "timestamp",
    descending: bool = True,
    ts_from: str | None = None,
    ts_to: str | None = None,
) -> dict[str, Any]:
    """Return a paginated slice ordered by order_by (default: timestamp DESC)."""
    con = _connect()
    all_cols = [f["column"] for f in schema(table_path)]

    if columns:
        selected = [c for c in columns if c in all_cols]
    else:
        selected = all_cols
    if not selected:
        selected = all_cols

    cols_sql = ", ".join(_quote_ident(c) for c in selected)
    where, params = _filter_clause(symbols, ts_from, ts_to)

    order_col = order_by if order_by in all_cols else all_cols[0]
    direction = "DESC" if descending else "ASC"
    offset = max(0, (page_num - 1) * page_size)

    sql = (
        f"SELECT {cols_sql} FROM delta_scan('{table_path}') "
        f"{where} ORDER BY {_quote_ident(order_col)} {direction} "
        f"LIMIT {int(page_size)} OFFSET {int(offset)}"
    )
    rows = con.execute(sql, params).fetchall()
    data = [dict(zip(selected, r)) for r in rows]

    return {
        "columns": selected,
        "rows": data,
        "page": page_num,
        "page_size": page_size,
        "total": row_count(table_path, symbols, ts_from, ts_to),
    }


def series(
    table_path: Path,
    *,
    symbols: list[str] | None = None,
    columns: list[str],
    x_column: str = "timestamp",
    max_points: int = 2000,
    ts_from: str | None = None,
    ts_to: str | None = None,
) -> dict[str, Any]:
    """Return downsampled time series data for chart rendering.

    Downsamples server-side by selecting every Nth row per symbol so charts
    stay responsive on multi-million row tables.
    """
    all_cols = [f["column"] for f in schema(table_path)]
    selected = [c for c in columns if c in all_cols]
    if not selected or x_column not in all_cols:
        return {"x": x_column, "columns": selected, "points": [], "symbols": []}

    con = _connect()
    where, params = _filter_clause(symbols, ts_from, ts_to, ts_col=x_column)
    total = row_count(table_path, symbols, ts_from, ts_to)
    # Downsample stride is per symbol so we don't drop entire symbols.
    per_symbol = max(1, total // max(1, len(symbols) if symbols else 1))
    stride = max(1, per_symbol // max_points)

    xq = _quote_ident(x_column)
    sym_cols = ", symbol" if symbols else ""
    partition = " PARTITION BY symbol" if symbols else ""

    cols_sql = ", ".join(_quote_ident(c) for c in [x_column, *selected])
    sql = (
        f"WITH src AS ("
        f"  SELECT {cols_sql}{sym_cols}, "
        f"    row_number() OVER ({partition} ORDER BY {xq}) AS rn"
        f"  FROM delta_scan('{table_path}') {where}"
        f") SELECT {cols_sql}{sym_cols} FROM src WHERE rn % {int(stride)} = 0 ORDER BY {xq}"
    )
    rows = con.execute(sql, params).fetchall()
    keys = [x_column, *selected] + (["symbol"] if symbols else [])
    points = [dict(zip(keys, r)) for r in rows]

    return {
        "x": x_column,
        "columns": selected,
        "symbols": symbols or [],
        "points": points,
        "total": total,
    }


def time_bounds(table_path: Path, symbol: str | None = None, x_column: str = "timestamp") -> dict[str, Any]:
    """Return min/max timestamp for a table (optionally filtered by symbol)."""
    all_cols = [f["column"] for f in schema(table_path)]
    if x_column not in all_cols:
        return {"min": None, "max": None}
    con = _connect()
    symbols = [symbol] if symbol else None
    where, params = _filter_clause(symbols)
    sql = (
        f"SELECT MIN({_quote_ident(x_column)}), MAX({_quote_ident(x_column)}) "
        f"FROM delta_scan('{table_path}') {where}"
    )
    row = con.execute(sql, params).fetchone()
    return {"min": row[0], "max": row[1]}


def stats(
    table_path: Path,
    *,
    symbols: list[str] | None = None,
    ts_from: str | None = None,
    ts_to: str | None = None,
) -> dict[str, Any]:
    """Compute per-column statistics.

    Tries DuckDB SUMMARIZE first (fast path). On some gold tables SUMMARIZE
    overflows STDDEV_SAMP on columns with large magnitudes — we then fall back
    to a manual per-column aggregation that casts to DOUBLE before stddev.
    """
    con = _connect()
    where, params = _filter_clause(symbols, ts_from, ts_to)
    inner_sql = f"SELECT * FROM delta_scan('{table_path}') {where}"

    cols = schema(table_path)
    col_names = [c["column"] for c in cols]

    try:
        cur = con.execute(f"SUMMARIZE {inner_sql}", params)
        rows = cur.fetchall()
        fields = [d[0] for d in cur.description]
        out = []
        for r in rows:
            rec = dict(zip(fields, r))
            out.append({
                "column": rec.get("column_name"),
                "dtype": rec.get("column_type"),
                "count": rec.get("count"),
                "null_percentage": rec.get("null_percentage"),
                "min": rec.get("min"),
                "max": rec.get("max"),
                "avg": rec.get("avg"),
                "std": rec.get("std"),
                "q25": rec.get("q25"),
                "q50": rec.get("q50"),
                "q75": rec.get("q75"),
                "approx_unique": rec.get("approx_unique"),
            })
        return {"columns": col_names, "stats": out}
    except duckdb.OutOfRangeException:
        return {"columns": col_names, "stats": _stats_manual(con, inner_sql, params, cols)}


def _stats_manual(
    con: duckdb.DuckDBPyConnection,
    inner_sql: str,
    params: list[Any],
    cols: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Per-column stats with DOUBLE casts to dodge SUMMARIZE overflow.

    Built as one big SELECT so we pay a single scan regardless of column count.
    """
    total_row = con.execute(f"SELECT COUNT(*) FROM ({inner_sql}) s", params).fetchone()
    total = int(total_row[0]) if total_row else 0

    exprs: list[str] = []
    for c in cols:
        q = _quote_ident(c["column"])
        numeric = c["numeric"]
        exprs.append(f"COUNT({q})")
        if numeric:
            qd = f"CAST({q} AS DOUBLE)"
            exprs += [
                f"MIN({qd})", f"MAX({qd})", f"AVG({qd})",
                f"STDDEV_SAMP({qd})",
                f"approx_quantile({qd}, 0.25)",
                f"approx_quantile({qd}, 0.50)",
                f"approx_quantile({qd}, 0.75)",
            ]
        else:
            exprs += [f"MIN({q})", f"MAX({q})", "NULL", "NULL", "NULL", "NULL", "NULL"]
        exprs.append(f"approx_count_distinct({q})")

    sql = f"SELECT {', '.join(exprs)} FROM ({inner_sql}) s"
    step = 9  # count, min, max, avg, std, q25, q50, q75, approx_unique
    try:
        row = con.execute(sql, params).fetchone()
        chunks = [list(row[i * step:(i + 1) * step]) for i in range(len(cols))]
    except duckdb.OutOfRangeException:
        # Combined query failed — retry column by column, skipping std on overflow.
        chunks = [_stats_one_column(con, inner_sql, params, c) for c in cols]

    out = []
    for c, chunk in zip(cols, chunks):
        count, mn, mx, avg, std, q25, q50, q75, approx = chunk
        null_pct = None
        if total and count is not None:
            null_pct = (1 - (count / total)) * 100
        out.append({
            "column": c["column"],
            "dtype": c["dtype"],
            "count": count,
            "null_percentage": null_pct,
            "min": mn,
            "max": mx,
            "avg": avg,
            "std": std,
            "q25": q25,
            "q50": q50,
            "q75": q75,
            "approx_unique": approx,
        })
    return out


def _stats_one_column(
    con: duckdb.DuckDBPyConnection,
    inner_sql: str,
    params: list[Any],
    col: dict[str, Any],
) -> list[Any]:
    """Compute the 9 stats for a single column; on overflow, drop std only."""
    q = _quote_ident(col["column"])
    numeric = col["numeric"]
    if numeric:
        qd = f"CAST({q} AS DOUBLE)"
        num_exprs = [
            f"COUNT({q})", f"MIN({qd})", f"MAX({qd})", f"AVG({qd})",
            f"STDDEV_SAMP({qd})",
            f"approx_quantile({qd}, 0.25)",
            f"approx_quantile({qd}, 0.50)",
            f"approx_quantile({qd}, 0.75)",
            f"approx_count_distinct({q})",
        ]
    else:
        num_exprs = [
            f"COUNT({q})", f"MIN({q})", f"MAX({q})", "NULL",
            "NULL", "NULL", "NULL", "NULL",
            f"approx_count_distinct({q})",
        ]
    sql = f"SELECT {', '.join(num_exprs)} FROM ({inner_sql}) s"
    try:
        return list(con.execute(sql, params).fetchone())
    except duckdb.OutOfRangeException:
        # Retry without stddev — everything else is safe.
        safe = list(num_exprs)
        safe[4] = "NULL"
        sql2 = f"SELECT {', '.join(safe)} FROM ({inner_sql}) s"
        try:
            return list(con.execute(sql2, params).fetchone())
        except Exception:
            return [None] * 9
