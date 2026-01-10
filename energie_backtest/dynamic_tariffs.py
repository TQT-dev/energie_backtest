from __future__ import annotations

from datetime import datetime
from typing import Iterable
from zoneinfo import ZoneInfo

from .models import ConsumptionRecord, Tariff, TariffSeries


def build_tariffs_for_consumption(
    consumption: Iterable[ConsumptionRecord],
    *,
    timezone: str = "Europe/Brussels",
    base_offpeak_eur_per_kwh: float = 0.18,
    base_peak_eur_per_kwh: float = 0.28,
    surcharge_eur_per_kwh: float = 0.02,
    peak_start_hour: int = 7,
    peak_end_hour: int = 22,
) -> TariffSeries:
    tzinfo = ZoneInfo(timezone)
    tariffs = []
    for record in consumption:
        local_dt = record.timestamp.astimezone(tzinfo)
        if _is_peak(local_dt, peak_start_hour, peak_end_hour):
            base_price = base_peak_eur_per_kwh
        else:
            base_price = base_offpeak_eur_per_kwh
        tariffs.append(
            Tariff(
                timestamp=record.timestamp,
                base_price_eur_per_kwh=base_price,
                surcharge_eur_per_kwh=surcharge_eur_per_kwh,
            )
        )
    return TariffSeries.from_tariffs(tariffs)


def peak_share(
    consumption: Iterable[ConsumptionRecord],
    *,
    timezone: str = "Europe/Brussels",
    peak_start_hour: int = 7,
    peak_end_hour: int = 22,
) -> float:
    tzinfo = ZoneInfo(timezone)
    peak_total = 0.0
    overall = 0.0
    for record in consumption:
        local_dt = record.timestamp.astimezone(tzinfo)
        if _is_peak(local_dt, peak_start_hour, peak_end_hour):
            peak_total += record.consumption_kwh
        overall += record.consumption_kwh
    if overall == 0:
        return 0.0
    return peak_total / overall


def _is_peak(local_dt: datetime, peak_start_hour: int, peak_end_hour: int) -> bool:
    return peak_start_hour <= local_dt.hour < peak_end_hour
