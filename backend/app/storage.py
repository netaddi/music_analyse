from __future__ import annotations

import json
import math
from pathlib import Path

from app.config import settings
from app.schemas import AnalysisReport


def ensure_storage_dirs() -> None:
    for path in (settings.data_dir, settings.upload_dir, settings.report_dir):
        path.mkdir(parents=True, exist_ok=True)


def report_path(report_id: str) -> Path:
    return settings.report_dir / f"{report_id}.json"


def save_report(report: AnalysisReport) -> Path:
    ensure_storage_dirs()
    path = report_path(report.report_id)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path


def _normalize_chart_values(payload: dict) -> bool:
    changed = False
    charts = payload.get("charts")
    if not isinstance(charts, dict):
        return changed

    for chart in charts.values():
        if not isinstance(chart, dict):
            continue
        series_list = chart.get("series")
        if not isinstance(series_list, list):
            continue
        for series in series_list:
            if not isinstance(series, dict):
                continue
            values = series.get("values")
            if not isinstance(values, list):
                continue

            normalized_values: list[float] = []
            for value in values:
                if value is None:
                    normalized_values.append(0.0)
                    changed = True
                    continue
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    numeric = float(value)
                    if math.isfinite(numeric):
                        normalized_values.append(numeric)
                    else:
                        normalized_values.append(0.0)
                        changed = True
                    continue

                normalized_values.append(0.0)
                changed = True

            series["values"] = normalized_values

    return changed


def load_report(report_id: str) -> AnalysisReport | None:
    path = report_path(report_id)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if _normalize_chart_values(payload):
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return AnalysisReport.model_validate(payload)
