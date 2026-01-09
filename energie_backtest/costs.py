from __future__ import annotations

from typing import Iterable, List, Sequence

from .models import ConsumptionRecord, QuarterCost, TariffSeries


def calculate_quarter_costs(
    consumption: Sequence[ConsumptionRecord],
    tariffs: TariffSeries,
    *,
    fallback_tariff_eur_per_kwh: float | None = None,
) -> List[QuarterCost]:
    """Calculate quarter-hour costs by matching consumption with tariffs."""

    results: List[QuarterCost] = []
    for record in consumption:
        tariff = tariffs.get(record.timestamp)
        if tariff is None:
            if fallback_tariff_eur_per_kwh is None:
                raise ValueError(
                    f"Missing tariff for {record.timestamp.isoformat()} and no fallback provided."
                )
            tariff_price = fallback_tariff_eur_per_kwh
        else:
            tariff_price = tariff.total_price_eur_per_kwh
        total_cost = record.consumption_kwh * tariff_price
        results.append(
            QuarterCost(
                timestamp=record.timestamp,
                consumption_kwh=record.consumption_kwh,
                tariff_eur_per_kwh=tariff_price,
                total_cost_eur=total_cost,
            )
        )
    return results


def total_cost(costs: Iterable[QuarterCost]) -> float:
    return sum(item.total_cost_eur for item in costs)
