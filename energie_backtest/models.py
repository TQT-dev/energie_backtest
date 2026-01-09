from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, Mapping


@dataclass(frozen=True)
class Tariff:
    """Tariff per quarter-hour, including base market price and surcharge."""

    timestamp: datetime
    base_price_eur_per_kwh: float
    surcharge_eur_per_kwh: float = 0.0

    @property
    def total_price_eur_per_kwh(self) -> float:
        return self.base_price_eur_per_kwh + self.surcharge_eur_per_kwh


@dataclass(frozen=True)
class ConsumptionRecord:
    """Consumption per quarter-hour."""

    timestamp: datetime
    consumption_kwh: float


@dataclass(frozen=True)
class QuarterCost:
    """Computed cost for a quarter-hour period."""

    timestamp: datetime
    consumption_kwh: float
    tariff_eur_per_kwh: float
    total_cost_eur: float


@dataclass(frozen=True)
class TariffSeries:
    """Lookup table for tariffs keyed by quarter-hour timestamp."""

    tariffs: Dict[datetime, Tariff]

    def get(self, timestamp: datetime) -> Tariff | None:
        return self.tariffs.get(timestamp)

    @classmethod
    def from_tariffs(cls, tariffs: Iterable[Tariff]) -> "TariffSeries":
        return cls({tariff.timestamp: tariff for tariff in tariffs})

    @classmethod
    def from_rows(
        cls,
        rows: Iterable[Mapping[str, object]],
        timestamp_key: str = "timestamp",
        base_price_key: str = "base_price_eur_per_kwh",
        surcharge_key: str = "surcharge_eur_per_kwh",
    ) -> "TariffSeries":
        parsed: Dict[datetime, Tariff] = {}
        for row in rows:
            timestamp_value = row[timestamp_key]
            timestamp = _ensure_datetime(timestamp_value)
            base_price = float(row[base_price_key])
            surcharge = float(row.get(surcharge_key, 0.0))
            parsed[timestamp] = Tariff(
                timestamp=timestamp,
                base_price_eur_per_kwh=base_price,
                surcharge_eur_per_kwh=surcharge,
            )
        return cls(parsed)


def _ensure_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"Unsupported timestamp type: {type(value)!r}")
