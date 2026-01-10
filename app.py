from __future__ import annotations

from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from energie_backtest.costs import calculate_quarter_costs
from energie_backtest.dynamic_tariffs import build_tariffs_for_consumption, peak_share
from energie_backtest.models import ConsumptionRecord
from energie_backtest.reporting import CostReport, build_cost_report
from upload_flow import UploadValidationError, parse_fluvius_upload

APP_ROOT = Path(__file__).resolve().parent

app = Flask(__name__, static_folder=None)


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
        reference_price = float(request.form.get("reference_price", "0.30"))
    except ValueError:
        return jsonify({"error": "Referentieprijs is ongeldig."}), 400

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

    tariffs = build_tariffs_for_consumption(consumption)
    costs = calculate_quarter_costs(
        consumption,
        tariffs,
        fallback_tariff_eur_per_kwh=reference_price,
    )
    report = build_cost_report(costs, reference_price, period="month")

    monthly = _format_monthly(report.aggregated_costs, report.aggregated_reference_costs)
    summary = _build_summary(report, monthly, consumption)

    return jsonify(
        {
            "summary": summary,
            "monthly": monthly,
        }
    )


def _parse_timestamp(raw: str | float) -> datetime:
    if isinstance(raw, datetime):
        return raw
    return datetime.fromisoformat(str(raw))


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
) -> dict[str, object]:
    months_count = max(1, len(monthly))
    average_monthly = report.total_cost_eur / months_count
    return {
        "total_cost_eur": round(report.total_cost_eur, 2),
        "reference_cost_eur": round(report.reference_cost_eur, 2),
        "difference_eur": round(report.difference_eur, 2),
        "difference_pct": round(report.difference_pct, 1),
        "average_monthly_cost_eur": round(average_monthly, 2),
        "peak_share_pct": round(peak_share(consumption) * 100.0, 1),
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
