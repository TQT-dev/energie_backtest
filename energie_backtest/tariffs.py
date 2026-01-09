from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

from .models import Tariff, TariffSeries


def read_tariffs_from_csv(
    path: str | Path,
    timestamp_key: str = "timestamp",
    base_price_key: str = "base_price_eur_per_kwh",
    surcharge_key: str = "surcharge_eur_per_kwh",
) -> TariffSeries:
    """Read quarter-hour tariffs from a CSV file."""

    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    return read_tariffs_from_rows(
        rows,
        timestamp_key=timestamp_key,
        base_price_key=base_price_key,
        surcharge_key=surcharge_key,
    )


def read_tariffs_from_rows(
    rows: Iterable[Mapping[str, object]],
    timestamp_key: str = "timestamp",
    base_price_key: str = "base_price_eur_per_kwh",
    surcharge_key: str = "surcharge_eur_per_kwh",
) -> TariffSeries:
    """Read quarter-hour tariffs from dict-like rows."""

    parsed = []
    for row in rows:
        timestamp_value = row[timestamp_key]
        timestamp = _ensure_datetime(timestamp_value)
        base_price = float(row[base_price_key])
        surcharge = float(row.get(surcharge_key, 0.0))
        parsed.append(
            Tariff(
                timestamp=timestamp,
                base_price_eur_per_kwh=base_price,
                surcharge_eur_per_kwh=surcharge,
            )
        )
    return TariffSeries.from_tariffs(parsed)


def _ensure_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"Unsupported timestamp type: {type(value)!r}")
