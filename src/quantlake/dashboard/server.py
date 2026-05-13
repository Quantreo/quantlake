"""FastAPI app exposing the dashboard API and serving the React build."""
from __future__ import annotations

import math
import os
from dataclasses import asdict
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import catalog, queries

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = Path(os.environ.get("QUANTLAKE_DATA_ROOT", PROJECT_ROOT / "data"))
WORKFLOW_PATH = PROJECT_ROOT / "workflow.yaml"
FRONTEND_DIST = PROJECT_ROOT / "dashboard" / "dist"


def _json_safe(obj):
    """Recursively convert datetime/date and NaN/Inf to JSON-compliant values."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, Decimal):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


app = FastAPI(title="QuantLake Dashboard", version="0.1.0")

# CORS open in dev (Vite on :5173 hitting FastAPI on :8000).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/layers")
def get_layers():
    return {"layers": list(catalog.LAYERS)}


@app.get("/api/workflow")
def get_workflow():
    """Return the parsed workflow.yaml describing the bronze/silver/gold DAG."""
    if not WORKFLOW_PATH.exists():
        return {"sources": {}, "bronze": {}, "silver": {}, "gold": {}}
    with WORKFLOW_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    for layer in ("sources", "bronze", "silver", "gold"):
        data.setdefault(layer, {})
    return data


@app.get("/api/tables/{layer}")
def get_tables(layer: str):
    if layer not in catalog.LAYERS:
        raise HTTPException(status_code=404, detail=f"Unknown layer: {layer}")
    tables = [asdict(t) for t in catalog.tables_for_layer(DATA_ROOT, layer)]
    return {"layer": layer, "tables": tables}


@app.get("/api/tables/{layer}/{name:path}/schema")
def get_schema(layer: str, name: str):
    path = catalog.resolve(DATA_ROOT, layer, name)
    if path is None:
        raise HTTPException(status_code=404, detail="Table not found")
    return {"layer": layer, "name": name, "schema": queries.schema(path)}


def _parse_csv(s: str | None) -> list[str] | None:
    if not s:
        return None
    out = [x.strip() for x in s.split(",") if x.strip()]
    return out or None


@app.get("/api/tables/{layer}/{name:path}/data")
def get_data(
    layer: str,
    name: str,
    symbols: str | None = Query(default=None, description="Comma-separated symbols"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=1000),
    order_by: str | None = Query(default="timestamp"),
    descending: bool = Query(default=True),
    ts_from: str | None = Query(default=None),
    ts_to: str | None = Query(default=None),
):
    path = catalog.resolve(DATA_ROOT, layer, name)
    if path is None:
        raise HTTPException(status_code=404, detail="Table not found")
    payload = queries.page(
        path,
        symbols=_parse_csv(symbols),
        page_num=page,
        page_size=page_size,
        order_by=order_by,
        descending=descending,
        ts_from=ts_from,
        ts_to=ts_to,
    )
    return JSONResponse(_json_safe(payload))


@app.get("/api/tables/{layer}/{name:path}/series")
def get_series(
    layer: str,
    name: str,
    columns: str = Query(..., description="Comma-separated column names"),
    symbols: str | None = Query(default=None, description="Comma-separated symbols"),
    x: str = Query(default="timestamp"),
    max_points: int = Query(default=2000, ge=100, le=10000),
    ts_from: str | None = Query(default=None),
    ts_to: str | None = Query(default=None),
):
    path = catalog.resolve(DATA_ROOT, layer, name)
    if path is None:
        raise HTTPException(status_code=404, detail="Table not found")
    cols = _parse_csv(columns) or []
    payload = queries.series(
        path,
        symbols=_parse_csv(symbols),
        columns=cols,
        x_column=x,
        max_points=max_points,
        ts_from=ts_from,
        ts_to=ts_to,
    )
    return JSONResponse(_json_safe(payload))


@app.get("/api/tables/{layer}/{name:path}/bounds")
def get_bounds(layer: str, name: str, symbol: str | None = Query(default=None)):
    path = catalog.resolve(DATA_ROOT, layer, name)
    if path is None:
        raise HTTPException(status_code=404, detail="Table not found")
    return JSONResponse(_json_safe(queries.time_bounds(path, symbol)))


@app.get("/api/tables/{layer}/{name:path}/stats")
def get_stats(
    layer: str,
    name: str,
    symbols: str | None = Query(default=None),
    ts_from: str | None = Query(default=None),
    ts_to: str | None = Query(default=None),
):
    path = catalog.resolve(DATA_ROOT, layer, name)
    if path is None:
        raise HTTPException(status_code=404, detail="Table not found")
    payload = queries.stats(
        path,
        symbols=_parse_csv(symbols),
        ts_from=ts_from,
        ts_to=ts_to,
    )
    return JSONResponse(_json_safe(payload))


# Serve the React build when it exists (production mode).
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
