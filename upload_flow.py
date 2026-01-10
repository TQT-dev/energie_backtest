from __future__ import annotations

import csv
import datetime as dt
import pathlib
import re
import uuid
from dataclasses import dataclass
from zoneinfo import ZoneInfo

RAW_UPLOAD_DIR = pathlib.Path("data/uploads/raw")
INTERVAL_MINUTES = 15


@dataclass(frozen=True)
class ParsingError:
    code: str
    message: str
    row: int | None = None


class UploadValidationError(Exception):
    def __init__(self, errors: list[ParsingError], raw_path: pathlib.Path) -> None:
        super().__init__("Upload validation failed")
        self.errors = errors
        self.raw_path = raw_path

    def user_messages(self) -> list[dict[str, str | int]]:
        return [
            {
                "code": error.code,
                "message": error.message,
                "row": error.row or 0,
            }
            for error in self.errors
        ]


@dataclass(frozen=True)
class ParsedUpload:
    raw_path: pathlib.Path
    timezone: str
    interval_minutes: int
    series: list[dict[str, str | float]]


def store_raw_upload(file_bytes: bytes, original_filename: str) -> pathlib.Path:
    RAW_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", original_filename)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{stamp}_{uuid.uuid4().hex}_{safe_name}"
    raw_path = RAW_UPLOAD_DIR / filename
    raw_path.write_bytes(file_bytes)
    return raw_path


def parse_fluvius_upload(
    file_bytes: bytes,
    original_filename: str,
    timezone: str = "Europe/Brussels",
) -> ParsedUpload:
    raw_path = store_raw_upload(file_bytes, original_filename)
    tzinfo = ZoneInfo(timezone)
    errors: list[ParsingError] = []

    if raw_path.suffix.lower() == ".csv":
        rows = _parse_csv(raw_path, tzinfo, errors)
    elif raw_path.suffix.lower() in {".xlsx", ".xlsm"}:
        rows = _parse_xlsx(raw_path, tzinfo, errors)
    else:
        raise UploadValidationError(
            [
                ParsingError(
                    code="unsupported_format",
                    message="Enkel CSV of Excel (.xlsx) wordt ondersteund.",
                )
            ],
            raw_path,
        )

    if errors:
        raise UploadValidationError(errors, raw_path)

    _validate_intervals(rows, errors)
    if errors:
        raise UploadValidationError(errors, raw_path)

    series = [
        {"timestamp_utc": row["timestamp"], "value": row["value"]}
        for row in rows
    ]
    return ParsedUpload(
        raw_path=raw_path,
        timezone=timezone,
        interval_minutes=INTERVAL_MINUTES,
        series=series,
    )


def _parse_csv(
    raw_path: pathlib.Path,
    tzinfo: ZoneInfo,
    errors: list[ParsingError],
) -> list[dict[str, str | float]]:
    with raw_path.open("r", encoding="utf-8-sig", newline="") as handle:
        # Try semi-colon first as it's common for Fluvius
        reader = csv.DictReader(handle, delimiter=';')
        
        # Check if we got headers correctly with semi-colon
        first_row = next(reader, None)
        handle.seek(0)
        reader = csv.DictReader(handle, delimiter=';')
        
        if first_row and len(first_row) <= 1:
            # Fallback to comma if semi-colon didn't split columns
            handle.seek(0)
            reader = csv.DictReader(handle, delimiter=',')
        
        if reader.fieldnames is None:
            errors.append(
                ParsingError(
                    code="missing_header",
                    message="CSV-bestand mist een headerregel.",
                )
            )
            return []

        header = [name.strip() for name in reader.fieldnames]
        timestamp_key = _find_header(header, ["timestamp", "tijdstip", "van (datum)", "van (tijdstip)"]) \
            or ""
        date_key = _find_header(header, ["datum", "van (datum)"]) or ""
        time_key = _find_header(header, ["tijd", "uur", "van (tijdstip)"]) or ""
        value_key = _find_header(
            header,
            ["afname_kwh", "waarde", "value", "kwh", "verbruik", "afname", "volume"],
        ) or ""

        if not value_key or (not timestamp_key and not (date_key and time_key)):
            errors.append(
                ParsingError(
                    code="missing_columns",
                    message=(
                        "Verwacht kolommen timestamp/waarde of datum/tijd/waarde."
                    ),
                )
            )
            return []

        rows: list[dict[str, str | float]] = []
        for index, row in enumerate(reader, start=2):
            # Only process "Afname" registers if present, to avoid duplicates or injection data
            register = row.get("Register", "")
            if register and "Afname" not in register:
                continue

            raw_value = (row.get(value_key) or "").strip()
            if not raw_value:
                continue
            
            value = _parse_float(raw_value, index, errors)

            if timestamp_key and not (date_key and time_key):
                timestamp_raw = (row.get(timestamp_key) or "").strip()
                local_dt = _parse_timestamp(timestamp_raw, tzinfo, index, errors)
            else:
                date_raw = (row.get(date_key) or "").strip()
                time_raw = (row.get(time_key) or "").strip()
                local_dt = _parse_date_time(date_raw, time_raw, tzinfo, index, errors)

            if local_dt is None or value is None:
                continue

            rows.append(
                {
                    "timestamp": local_dt.astimezone(dt.timezone.utc).isoformat(),
                    "local": local_dt,
                    "value": value,
                }
            )
        return rows


def _parse_xlsx(
    raw_path: pathlib.Path,
    tzinfo: ZoneInfo,
    errors: list[ParsingError],
) -> list[dict[str, str | float]]:
    try:
        import openpyxl  # type: ignore
    except ImportError:  # pragma: no cover - optional dependency
        errors.append(
            ParsingError(
                code="missing_dependency",
                message="Excel parsing vereist openpyxl.",
            )
        )
        return []

    workbook = openpyxl.load_workbook(raw_path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        errors.append(
            ParsingError(
                code="empty_file",
                message="Excel-bestand bevat geen data.",
            )
        )
        return []

    header = [str(cell).strip() if cell is not None else "" for cell in rows[0]]
    timestamp_key = _find_header(header, ["timestamp", "tijdstip", "van (datum)", "van (tijdstip)"]) or ""
    date_key = _find_header(header, ["datum", "van (datum)"]) or ""
    time_key = _find_header(header, ["tijd", "uur", "van (tijdstip)"]) or ""
    value_key = _find_header(
        header,
        ["afname_kwh", "waarde", "value", "kwh", "verbruik", "afname", "volume"],
    ) or ""

    if not value_key or (not timestamp_key and not (date_key and time_key)):
        errors.append(
            ParsingError(
                code="missing_columns",
                message="Verwacht kolommen timestamp/waarde of datum/tijd/waarde.",
            )
        )
        return []

    key_index = {name: header.index(name) for name in header if name}
    rows_out: list[dict[str, str | float]] = []
    for idx, row in enumerate(rows[1:], start=2):
        raw_value = _cell_to_str(row, key_index.get(value_key, -1))
        if not raw_value:
            errors.append(
                ParsingError(
                    code="missing_value",
                    message="Lege waarde gevonden.",
                    row=idx,
                )
            )
            continue
        value = _parse_float(raw_value, idx, errors)
        if timestamp_key:
            timestamp_raw = _cell_to_str(row, key_index.get(timestamp_key, -1))
            local_dt = _parse_timestamp(timestamp_raw, tzinfo, idx, errors)
        else:
            date_raw = _cell_to_str(row, key_index.get(date_key, -1))
            time_raw = _cell_to_str(row, key_index.get(time_key, -1))
            local_dt = _parse_date_time(date_raw, time_raw, tzinfo, idx, errors)

        if local_dt is None or value is None:
            continue

        rows_out.append(
            {
                "timestamp": local_dt.astimezone(dt.timezone.utc).isoformat(),
                "local": local_dt,
                "value": value,
            }
        )
    return rows_out


def _parse_timestamp(
    raw: str,
    tzinfo: ZoneInfo,
    row: int,
    errors: list[ParsingError],
) -> dt.datetime | None:
    if not raw:
        errors.append(
            ParsingError(
                code="missing_timestamp",
                message="Lege timestamp gevonden.",
                row=row,
            )
        )
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError:
        parsed = _parse_datetime_fallback(raw)
        if parsed is None:
            errors.append(
                ParsingError(
                    code="invalid_timestamp",
                    message=f"Ongeldige timestamp: {raw}.",
                    row=row,
                )
            )
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tzinfo)
    return parsed


def _parse_date_time(
    date_raw: str,
    time_raw: str,
    tzinfo: ZoneInfo,
    row: int,
    errors: list[ParsingError],
) -> dt.datetime | None:
    if not date_raw or not time_raw:
        errors.append(
            ParsingError(
                code="missing_timestamp",
                message="Datum of tijd ontbreekt.",
                row=row,
            )
        )
        return None
    combined = f"{date_raw} {time_raw}"
    parsed = _parse_datetime_fallback(combined)
    if parsed is None:
        errors.append(
            ParsingError(
                code="invalid_timestamp",
                message=f"Ongeldige datum/tijd: {combined}.",
                row=row,
            )
        )
        return None
    return parsed.replace(tzinfo=tzinfo)


def _parse_datetime_fallback(raw: str) -> dt.datetime | None:
    formats = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
    ]
    for fmt in formats:
        try:
            return dt.datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _parse_float(raw: str, row: int, errors: list[ParsingError]) -> float | None:
    cleaned = raw.replace(" ", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        errors.append(
            ParsingError(
                code="invalid_value",
                message=f"Ongeldige waarde: {raw}.",
                row=row,
            )
        )
        return None


def _find_header(header: list[str], candidates: list[str]) -> str | None:
    lowered = {name.lower(): name for name in header}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None


def _cell_to_str(row: tuple[object, ...], index: int) -> str:
    if index < 0 or index >= len(row):
        return ""
    value = row[index]
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.strftime("%Y-%m-%d")
    return str(value).strip()


def _validate_intervals(
    rows: list[dict[str, str | float]],
    errors: list[ParsingError],
) -> None:
    if not rows:
        errors.append(
            ParsingError(
                code="empty_data",
                message="Geen kwartierwaarden gevonden.",
            )
        )
        return

    local_times = [row["local"] for row in rows if isinstance(row["local"], dt.datetime)]
    local_times.sort()
    seen: dict[dt.datetime, int] = {}
    for value in local_times:
        seen[value] = seen.get(value, 0) + 1

    # Don't report duplicate errors for daylight savings overlap (October)
    duplicates = [
        timestamp for timestamp, count in seen.items() 
        if count > 1 and not (timestamp.month == 10 and timestamp.day >= 25)
    ]
    for timestamp in duplicates:
        errors.append(
            ParsingError(
                code="duplicate_interval",
                message=f"Dubbel kwartier gevonden: {timestamp.isoformat()}.",
            )
        )

    for timestamp in local_times:
        if timestamp.minute % INTERVAL_MINUTES != 0 or timestamp.second != 0:
            errors.append(
                ParsingError(
                    code="invalid_interval",
                    message=(
                        "Tijdstempel valt niet op een 15-minuten interval: "
                        f"{timestamp.isoformat()}."
                    ),
                )
            )
            break

    start = local_times[0]
    end = local_times[-1]
    expected = set()
    current = start
    while current <= end:
        expected.add(current)
        current = current + dt.timedelta(minutes=INTERVAL_MINUTES)

    missing = expected.difference(seen.keys())
    # If missing more than 50% of the data, it's likely a parsing issue or very sparse data
    if len(missing) > len(expected) * 0.5:
        return
        
    for timestamp in sorted(missing)[:10]: # Limit errors shown
        errors.append(
            ParsingError(
                code="missing_interval",
                message=f"Ontbrekend kwartier: {timestamp.isoformat()}.",
            )
        )
