from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import RequestEntityTooLarge

from energie_backtest.costs import calculate_quarter_costs
from energie_backtest.dynamic_tariffs import (
    build_tariffs_for_consumption,
    peak_costs,
    peak_share,
)
from energie_backtest.models import ConsumptionRecord
from energie_backtest.reporting import CostReport, build_cost_report
from upload_flow import UploadValidationError, parse_fluvius_upload

APP_ROOT = Path(__file__).resolve().parent
MAX_UPLOAD_MB = 10

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024


@app.get("/")
def index() -> object:
    return send_from_directory(APP_ROOT, "index.html")


@app.get("/styles.css")
def styles() -> object:
    return send_from_directory(APP_ROOT, "styles.css")


@app.post("/api/upload")
def upload() -> object:
    if "file" not in request.files:
        return jsonify({"error": "Geen bestand ontvangen."}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Bestandsnaam ontbreekt."}), 400

    try:
        reference_price = _parse_float_field("reference_price", default=0.30, minimum=0.0)
        base_offpeak = _parse_float_field("base_offpeak_price", default=0.18, minimum=0.0)
        base_peak = _parse_float_field("base_peak_price", default=0.28, minimum=0.0)
        surcharge = _parse_float_field("surcharge_price", default=0.02, minimum=0.0)
        peak_start_hour = _parse_int_field("peak_start_hour", default=7, minimum=0, maximum=23)
        peak_end_hour = _parse_int_field("peak_end_hour", default=22, minimum=1, maximum=24)
        timezone_name = _parse_timezone(request.form.get("timezone", "Europe/Brussels"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        parsed = parse_fluvius_upload(file.read(), file.filename)
    except UploadValidationError as exc:
        return jsonify({"error": "Upload validatie mislukt.", "details": exc.user_messages()}), 422

    consumption = [
        ConsumptionRecord(
            timestamp=_parse_timestamp(item["timestamp_utc"]),
            consumption_kwh=float(item["value"]),
        )
        for item in parsed.series
    ]

    if peak_end_hour <= peak_start_hour:
        return jsonify({"error": "Piekuren eindigen na het startuur."}), 400

    tariffs = build_tariffs_for_consumption(
        consumption,
        timezone=timezone_name,
        base_offpeak_eur_per_kwh=base_offpeak,
        base_peak_eur_per_kwh=base_peak,
        surcharge_eur_per_kwh=surcharge,
        peak_start_hour=peak_start_hour,
        peak_end_hour=peak_end_hour,
    )
    costs = calculate_quarter_costs(
        consumption,
        tariffs,
        fallback_tariff_eur_per_kwh=reference_price,
    )
    report = build_cost_report(costs, reference_price, period="month")

    monthly = _format_monthly(report.aggregated_costs, report.aggregated_reference_costs)
    peak_cost, offpeak_cost = peak_costs(
        costs,
        timezone=timezone_name,
        peak_start_hour=peak_start_hour,
        peak_end_hour=peak_end_hour,
    )
    summary = _build_summary(
        report,
        monthly,
        consumption,
        peak_cost=peak_cost,
        offpeak_cost=offpeak_cost,
        timezone=timezone_name,
        peak_start_hour=peak_start_hour,
        peak_end_hour=peak_end_hour,
    )

    return jsonify(
        {
            "summary": summary,
            "monthly": monthly,
        }
    )


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(_: RequestEntityTooLarge) -> object:
    return (
        jsonify({"error": f"Bestand is te groot. Maximaal {MAX_UPLOAD_MB} MB toegestaan."}),
        413,
    )


def _parse_timestamp(raw: str | float) -> datetime:
    if isinstance(raw, datetime):
        return raw
    parsed = datetime.fromisoformat(str(raw))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_float_field(
    name: str, *, default: float, minimum: float | None = None, maximum: float | None = None
) -> float:
    raw = request.form.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"Waarde voor {name.replace('_', ' ')} is ongeldig.") from exc
    _validate_range(name, value, minimum, maximum)
    return value


def _parse_int_field(
    name: str, *, default: int, minimum: int | None = None, maximum: int | None = None
) -> int:
    raw = request.form.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"Waarde voor {name.replace('_', ' ')} is ongeldig.") from exc
    _validate_range(name, value, minimum, maximum)
    return value


def _validate_range(
    name: str, value: float, minimum: float | None, maximum: float | None
) -> None:
    if minimum is not None and value < minimum:
        raise ValueError(f"Waarde voor {name.replace('_', ' ')} moet minstens {minimum} zijn.")
    if maximum is not None and value > maximum:
        raise ValueError(f"Waarde voor {name.replace('_', ' ')} mag maximaal {maximum} zijn.")


def _parse_timezone(value: str | None) -> str:
    timezone_name = (value or "").strip() or "Europe/Brussels"
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Onbekende tijdzone opgegeven.") from exc
    return timezone_name


def _format_monthly(costs: dict[tuple[int, int], float], reference: dict[tuple[int, int], float]) -> list[dict[str, object]]:
    formatted = []
    for (year, month), value in sorted(costs.items()):
        reference_value = reference.get((year, month), 0.0)
        formatted.append(
            {
                "period": f"{year}-{month:02d}",
                "cost_eur": round(value, 2),
                "reference_cost_eur": round(reference_value, 2),
            }
        )
    return formatted


def _build_summary(
    report: CostReport,
    monthly: list[dict[str, object]],
    consumption: list[ConsumptionRecord],
    *,
    peak_cost: float,
    offpeak_cost: float,
    timezone: str,
    peak_start_hour: int,
    peak_end_hour: int,
) -> dict[str, object]:
    months_count = max(1, len(monthly))
    average_monthly = report.total_cost_eur / months_count
    return {
        "total_cost_eur": round(report.total_cost_eur, 2),
        "reference_cost_eur": round(report.reference_cost_eur, 2),
        "difference_eur": round(report.difference_eur, 2),
        "difference_pct": round(report.difference_pct, 1),
        "average_monthly_cost_eur": round(average_monthly, 2),
        "peak_share_pct": round(
            peak_share(
                consumption,
                timezone=timezone,
                peak_start_hour=peak_start_hour,
                peak_end_hour=peak_end_hour,
            )
            * 100.0,
            1,
        ),
        "peak_cost_eur": round(peak_cost, 2),
        "offpeak_cost_eur": round(offpeak_cost, 2),
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
