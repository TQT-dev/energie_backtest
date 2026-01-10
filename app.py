from __future__ import annotations

import cgi
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from energie_backtest.costs import calculate_quarter_costs
from energie_backtest.dynamic_tariffs import build_tariffs_for_consumption, peak_share
from energie_backtest.models import ConsumptionRecord
from energie_backtest.reporting import CostReport, build_cost_report
from upload_flow import UploadValidationError, parse_fluvius_upload

APP_ROOT = Path(__file__).resolve().parent


class BacktestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_file("index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/styles.css":
            self._send_file("styles.css", "text/css; charset=utf-8")
            return
        self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/upload":
            self.send_error(404, "Not Found")
            return

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._send_json({"error": "Ongeldig upload formaat."}, status=400)
            return

        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type},
        )
        file_item = form["file"] if "file" in form else None
        if file_item is None or not getattr(file_item, "filename", ""):
            self._send_json({"error": "Geen bestand ontvangen."}, status=400)
            return

        reference_raw = form.getfirst("reference_price", "0.30")
        try:
            reference_price = float(reference_raw)
        except ValueError:
            self._send_json({"error": "Referentieprijs is ongeldig."}, status=400)
            return

        file_bytes = file_item.file.read()
        try:
            parsed_upload = parse_fluvius_upload(file_bytes, file_item.filename)
        except UploadValidationError as exc:
            self._send_json(
                {"error": "Upload validatie mislukt.", "details": exc.user_messages()},
                status=422,
            )
            return

        consumption = [
            ConsumptionRecord(
                timestamp=_parse_timestamp(item["timestamp_utc"]),
                consumption_kwh=float(item["value"]),
            )
            for item in parsed_upload.series
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

        self._send_json({"summary": summary, "monthly": monthly})

    def _send_file(self, filename: str, content_type: str) -> None:
        path = APP_ROOT / filename
        if not path.exists():
            self.send_error(404, "Not Found")
            return
        payload = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _parse_timestamp(raw: str | float) -> datetime:
    if isinstance(raw, datetime):
        return raw
    return datetime.fromisoformat(str(raw))


def _format_monthly(
    costs: dict[tuple[int, int], float],
    reference: dict[tuple[int, int], float],
) -> list[dict[str, object]]:
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


def run(host: str = "0.0.0.0", port: int = 8000) -> None:
    server = HTTPServer((host, port), BacktestHandler)
    print(f"Serving on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
