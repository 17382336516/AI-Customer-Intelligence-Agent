"""Normalize Tianchi Taobao behavior data into a chunk-friendly canonical CSV."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from pathlib import Path

import pandas as pd

TIANCHI_COLUMNS = [
    "user_id",
    "item_id",
    "behavior_type",
    "user_geohash",
    "item_category",
    "time",
]
OUTPUT_COLUMNS = [
    "user_id",
    "item_id",
    "behavior_type",
    "user_geohash",
    "item_category",
    "event_time",
]
BEHAVIOR_MAP = {
    "1": "view",
    "2": "favorite",
    "3": "cart",
    "4": "purchase",
    "pv": "view",
    "view": "view",
    "click": "view",
    "fav": "favorite",
    "favorite": "favorite",
    "collect": "favorite",
    "cart": "cart",
    "buy": "purchase",
    "purchase": "purchase",
    "payment": "purchase",
}


def _text_id(series: pd.Series) -> pd.Series:
    return series.astype("string").str.replace(r"\.0$", "", regex=True).str.strip()


def normalize_chunk(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.rename(columns=lambda value: str(value).strip().lower())

    # Also accepts the UCI Online Retail workbook for local smoke tests only.
    if {"customerid", "stockcode", "invoicedate"}.issubset(frame.columns):
        quantity = pd.to_numeric(frame.get("quantity"), errors="coerce").fillna(0)
        price = pd.to_numeric(frame.get("unitprice"), errors="coerce").fillna(0)
        frame = pd.DataFrame(
            {
                "user_id": frame["customerid"],
                "item_id": frame["stockcode"],
                "behavior_type": "purchase",
                "user_geohash": "",
                "item_category": frame["stockcode"],
                "time": frame["invoicedate"],
                "_valid_sale": (quantity > 0) & (price > 0),
            }
        )
        frame = frame[frame["_valid_sale"]]

    missing = set(TIANCHI_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing source columns: {sorted(missing)}")

    clean = pd.DataFrame()
    clean["user_id"] = _text_id(frame["user_id"])
    clean["item_id"] = _text_id(frame["item_id"])
    clean["behavior_type"] = (
        frame["behavior_type"].astype("string").str.lower().str.strip().map(BEHAVIOR_MAP)
    )
    clean["user_geohash"] = frame["user_geohash"].astype("string").fillna("").str.strip()
    clean["item_category"] = _text_id(frame["item_category"])
    clean["event_time"] = pd.to_datetime(frame["time"], errors="coerce")

    clean = clean.dropna(subset=["user_id", "item_id", "behavior_type", "event_time"])
    clean = clean[(clean["user_id"] != "") & (clean["item_id"] != "")]
    clean = clean.drop_duplicates(
        subset=["user_id", "item_id", "behavior_type", "event_time"], keep="first"
    )
    return clean[OUTPUT_COLUMNS]


def _csv_chunks(path: Path, chunksize: int) -> Iterator[pd.DataFrame]:
    first = pd.read_csv(path, nrows=3)
    known = {str(column).strip().lower() for column in first.columns}
    if {"user_id", "item_id", "behavior_type", "item_category", "time"}.issubset(known):
        yield from pd.read_csv(path, chunksize=chunksize, low_memory=False)
    else:
        yield from pd.read_csv(
            path, names=TIANCHI_COLUMNS, header=None, chunksize=chunksize, low_memory=False
        )


def source_chunks(path: Path, chunksize: int) -> Iterator[pd.DataFrame]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        yield from _csv_chunks(path, chunksize)
    elif suffix in {".xlsx", ".xls"}:
        yield pd.read_excel(path)
    else:
        raise ValueError("Only CSV, XLSX and XLS source files are supported.")


def clean_file(source: Path, output: Path, chunksize: int = 500_000) -> dict[str, int]:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    input_rows = 0
    output_rows = 0
    purchase_rows = 0

    for index, chunk in enumerate(source_chunks(source, chunksize)):
        input_rows += len(chunk)
        clean = normalize_chunk(chunk)
        output_rows += len(clean)
        purchase_rows += int((clean["behavior_type"] == "purchase").sum())
        clean.to_csv(output, mode="a", header=index == 0, index=False, encoding="utf-8")

    stats = {
        "input_rows": input_rows,
        "output_rows": output_rows,
        "purchase_rows": purchase_rows,
    }
    output.with_suffix(".stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean Tianchi behavior data.")
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/taobao_behavior_clean.csv"),
    )
    parser.add_argument("--chunksize", type=int, default=500_000)
    args = parser.parse_args()

    stats = clean_file(args.source, args.output, args.chunksize)
    print(f"Saved: {args.output.resolve()}")
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
