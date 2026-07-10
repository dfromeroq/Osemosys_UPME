#!/usr/bin/env python3
"""Comparador tolerante de resultados OSeMOSYS.

Clasifica diferencias primales pequeñas/degeneradas como warning cuando los KPIs
fuertes son equivalentes. Diseñado para notebook/app/regional/timeslices.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

DEFAULT_TOLERANCES = {
    "objective_value": {"abs": 1e-4, "rel": 1e-8, "level": "fail"},
    "coverage_ratio": {"abs": 1e-9, "rel": 1e-9, "level": "fail"},
    "total_demand": {"abs": 1e-6, "rel": 1e-10, "level": "fail"},
    "total_unmet": {"abs": 1e-6, "rel": 1e-9, "level": "fail"},
    "total_dispatch": {"abs": 1e-5, "rel": 1e-5, "level": "warn"},
}


def _num(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _ok(ref: float, actual: float, abs_tol: float, rel_tol: float) -> tuple[bool, float, float]:
    abs_err = abs(actual - ref)
    rel_err = abs_err / max(abs(ref), 1e-15)
    return abs_err <= abs_tol or rel_err <= rel_tol, abs_err, rel_err


def _dispatch_by(rows: list[dict], keys: tuple[str, ...]) -> dict[tuple, float]:
    out: dict[tuple, float] = {}
    for row in rows or []:
        key = tuple(row.get(k) for k in keys)
        out[key] = out.get(key, 0.0) + _num(row.get("dispatch"))
    return out


def _compare_map(ref: dict[tuple, float], actual: dict[tuple, float], abs_tol: float, rel_tol: float) -> dict:
    keys = set(ref) | set(actual)
    diffs = []
    for key in keys:
        rv = ref.get(key, 0.0)
        av = actual.get(key, 0.0)
        ok, abs_err, rel_err = _ok(rv, av, abs_tol, rel_tol)
        if not ok:
            diffs.append({"key": key, "reference": rv, "actual": av, "abs_error": abs_err, "rel_error": rel_err})
    diffs.sort(key=lambda x: x["abs_error"], reverse=True)
    return {"count": len(diffs), "top": diffs[:20]}


def compare(reference: dict, actual: dict) -> dict:
    failures = []
    warnings = []
    metrics = {}
    for key, spec in DEFAULT_TOLERANCES.items():
        rv = _num(reference.get(key))
        av = _num(actual.get(key))
        ok, abs_err, rel_err = _ok(rv, av, spec["abs"], spec["rel"])
        item = {
            "metric": key,
            "reference": rv,
            "actual": av,
            "abs_error": abs_err,
            "rel_error": rel_err,
            "abs_tol": spec["abs"],
            "rel_tol": spec["rel"],
            "level": spec["level"],
            "ok": ok,
        }
        metrics[key] = item
        if not ok and spec["level"] == "fail":
            failures.append(item)
        elif not ok:
            warnings.append(item)

    # Comparaciones agregadas de dispatch: individual puede diferir por múltiples óptimos.
    dispatch_checks = {}
    ref_dispatch = reference.get("dispatch") or []
    act_dispatch = actual.get("dispatch") or []
    for name, keys in {
        "dispatch_by_year": ("year",),
        "dispatch_by_region_year": ("region_id", "year"),
        "dispatch_by_fuel_year": ("fuel_name", "year"),
        "dispatch_by_tech_fuel_year": ("technology_name", "fuel_name", "year"),
    }.items():
        dispatch_checks[name] = _compare_map(
            _dispatch_by(ref_dispatch, keys),
            _dispatch_by(act_dispatch, keys),
            abs_tol=1e-5,
            rel_tol=1e-6,
        )
        if dispatch_checks[name]["count"]:
            warnings.append({"metric": name, **dispatch_checks[name]})

    status = "PASS" if not failures else "FAIL"
    if status == "PASS" and warnings:
        status = "PASS_WITH_WARNINGS"
    return {
        "status": status,
        "metrics": metrics,
        "failures": failures,
        "warnings": warnings,
        "dispatch_checks": dispatch_checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", type=Path, required=True)
    parser.add_argument("--actual", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = compare(
        json.loads(args.ref.read_text(encoding="utf-8")),
        json.loads(args.actual.read_text(encoding="utf-8")),
    )
    text = json.dumps(result, indent=2, ensure_ascii=False, default=str)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["status"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
