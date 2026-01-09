from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, Iterable, Tuple

from .models import QuarterCost

PeriodKey = Tuple[int, int, int] | Tuple[int, int] | Tuple[int]


def aggregate_costs(
    costs: Iterable[QuarterCost],
    period: str = "day",
) -> Dict[PeriodKey, float]:
    """Aggregate costs by day, month, or year."""

    totals: Dict[PeriodKey, float] = defaultdict(float)
    for item in costs:
        key = _period_key(item.timestamp, period)
        totals[key] += item.total_cost_eur
    return dict(totals)


def _period_key(timestamp: datetime, period: str) -> PeriodKey:
    if period == "day":
        return (timestamp.year, timestamp.month, timestamp.day)
    if period == "month":
        return (timestamp.year, timestamp.month)
    if period == "year":
        return (timestamp.year,)
    raise ValueError("period must be 'day', 'month', or 'year'")
