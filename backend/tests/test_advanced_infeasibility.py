from __future__ import annotations

import json
from pathlib import Path

from app.simulation.core.advanced_infeasibility import run_advanced_diagnostic_suite


def _write(root: Path, name: str, contents: str) -> None:
    (root / f"{name}.csv").write_text(contents, encoding="utf-8")


def test_suite_certifies_only_exact_scalar_witnesses_and_is_json_serializable(tmp_path: Path) -> None:
    _write(tmp_path, "InputActivityRatio", "REGION,TECHNOLOGY,MODE_OF_OPERATION,FUEL,YEAR,VALUE\nR,GEN,1,GAS,2030,1\n")
    _write(tmp_path, "OutputActivityRatio", "REGION,TECHNOLOGY,MODE_OF_OPERATION,FUEL,YEAR,VALUE\nR,GEN,1,ELC,2030,1\n")
    _write(tmp_path, "AccumulatedAnnualDemand", "REGION,FUEL,YEAR,VALUE\nR,ELC,2030,2\n")
    _write(tmp_path, "Numbers", "KEY,VALUE\na,1e-12\nb,1e3\nc,nan\n")
    findings = [
        {"code": "PARAMETER_BOUND_CONFLICT", "dimensions": {"REGION": "R", "TECHNOLOGY": "GEN", "YEAR": "2030"}, "values": {"lower_parameter": "Min", "upper_parameter": "Max", "lower_value": 5, "upper_value": 3}},
        {"code": "MANDATED_ANNUAL_ACTIVITY_WITHOUT_USABLE_CAPACITY", "dimensions": {"REGION": "R", "TECHNOLOGY": "GEN", "YEAR": "2031"}, "values": {"required_activity": 4, "capacity_activity_upper_bound": 1}},
        {"code": "OTHER", "dimensions": {"REGION": "R", "YEAR": "2030"}, "values": {}},
    ]

    result = run_advanced_diagnostic_suite(tmp_path, findings)

    assert set(result) == {"reduced_core", "hierarchical_isolation", "selective_relaxation", "bound_propagation", "baseline_comparison", "iis_enumeration", "maxfs_mcs", "quickxplain", "decomposition", "graph_bottleneck", "numerical"}
    assert all({"method", "evidence_level", "available", "explanation", "how_to_use"} <= set(report) for report in result.values())
    assert result["reduced_core"]["witness_count"] == 2
    witness = result["reduced_core"]["witnesses"][0]
    assert witness["certified"] is True and witness["gap"] == 2
    assert len(witness["constraints"]) == 2
    assert result["iis_enumeration"]["cores"][0]["irreducible_algebraically"] is True
    assert result["maxfs_mcs"]["correction_count"] == 4
    assert result["graph_bottleneck"]["node_count"] == 2
    assert result["numerical"]["dynamic_range_flag"] is True
    assert result["baseline_comparison"]["available"] is False
    json.dumps(result)


def test_baseline_compares_csv_key_values(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"; baseline.mkdir()
    _write(tmp_path, "ResidualCapacity", "REGION,TECHNOLOGY,YEAR,VALUE\nR,T,2030,2\n")
    _write(baseline, "ResidualCapacity", "REGION,TECHNOLOGY,YEAR,VALUE\nR,T,2030,1\n")

    result = run_advanced_diagnostic_suite(tmp_path, [], baseline)

    comparison = result["baseline_comparison"]
    assert comparison["available"] is True
    assert comparison["difference_count"] == 1
    assert comparison["differences"][0]["current_value"] == "2"
