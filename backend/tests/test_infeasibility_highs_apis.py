from __future__ import annotations

from pathlib import Path

import pytest

from app.simulation.core.infeasibility_analysis import (
    analyze,
    clear_csv_cache,
    classify_solver_outcome,
    constraint_indices,
    try_compute_dual_ray,
    try_compute_iis,
    try_compute_primal_ray,
    try_feasibility_relaxation,
    values_for_constraint,
)


pytest.importorskip("highspy")


def test_lu3_mapping_preserves_current_and_previous_year(tmp_path: Path) -> None:
    (tmp_path / "TechnologyActivityIncreaseByModeLimit.csv").write_text(
        "REGION,TECHNOLOGY,MODE_OF_OPERATION,YEAR,VALUE\n"
        "COL,TECH,1,2029,0.25\n"
        "COL,TECH,1,2030,0.50\n",
        encoding="utf-8",
    )
    indices = constraint_indices(
        "LU3_TechnologyActivityIncreaseByMode",
        ["COL", "TECH", "1", "2030", "2029"],
    )

    hits = values_for_constraint(
        tmp_path,
        "LU3_TechnologyActivityIncreaseByMode",
        indices,
    )

    assert indices == {
        "REGION": "COL",
        "TECHNOLOGY": "TECH",
        "MODE_OF_OPERATION": "1",
        "YEAR": "2030",
        "PREVIOUS_YEAR": "2029",
    }
    assert len(hits) == 1
    assert hits[0].value == 0.25
    clear_csv_cache()


def _write_lp(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / f"{name}.lp"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("infactible", "INFEASIBLE_CERTIFIED"),
        ("infeasibleOrUnbounded", "UNCLASSIFIED"),
        ("unbounded", "UNBOUNDED_CERTIFIED"),
        ("kNotset", "NUMERICAL_FAILURE"),
        ("maxTimeLimit", "RESOURCE_LIMIT"),
        ("cancelled", "CANCELLED"),
        ("optimal", "OPTIMAL"),
    ],
)
def test_solver_outcome_classification(status: str, expected: str) -> None:
    assert classify_solver_outcome(status).code == expected


def test_highs_dual_ray_is_independently_validated(tmp_path: Path) -> None:
    lp_path = _write_lp(
        tmp_path,
        "dual_ray",
        """Minimize
 obj: x
Subject To
 demand_floor: x >= 1
 capacity_ceiling: x <= 0
Bounds
 x free
End
""",
    )

    report = try_compute_dual_ray(object(), "highs", lp_path=lp_path)

    assert report.available is True
    assert report.validated is True
    assert report.certificate_margin == pytest.approx(1.0)
    assert {row.name for row in report.rows} == {"demand_floor", "capacity_ceiling"}


def test_highs_dual_ray_validation_uses_variable_bounds(tmp_path: Path) -> None:
    lp_path = _write_lp(
        tmp_path,
        "dual_ray_variable_bound",
        """Minimize
 obj: x
Subject To
 demand_floor: x >= 1
Bounds
 x <= 0
End
""",
    )

    report = try_compute_dual_ray(object(), "highs", lp_path=lp_path)

    assert report.available is True
    assert report.validated is True
    assert report.certificate_margin == pytest.approx(1.0)


def test_highs_primal_ray_identifies_unbounded_direction(tmp_path: Path) -> None:
    lp_path = _write_lp(
        tmp_path,
        "primal_ray",
        """Minimize
 obj: - x
Subject To
 floor: x >= 0
Bounds
 x free
End
""",
    )

    report = try_compute_primal_ray("highs", lp_path=lp_path)

    assert report.available is True
    assert report.certificate_type == "primal_ray"
    assert report.method == "highs.getPrimalRay"
    assert report.validated is True
    assert report.certificate_margin == pytest.approx(1.0)
    assert report.variables[0].name == "x"
    assert report.variables[0].direction == pytest.approx(1.0)


def test_highs_feasibility_relaxation_quantifies_required_slack(tmp_path: Path) -> None:
    lp_path = _write_lp(
        tmp_path,
        "relaxation",
        """Minimize
 obj: x
Subject To
 demand_floor: x >= 1
 capacity_ceiling: x <= 0
Bounds
 x free
End
""",
    )

    report = try_feasibility_relaxation(object(), "highs", lp_path=lp_path)

    assert report.available is True
    assert report.solution_value_valid is True
    assert report.objective is not None
    assert len(report.relaxations) == 1
    assert report.relaxations[0].slack == pytest.approx(1.0)
    assert report.relaxations[0].side in {"LB", "UB"}


def test_analyze_does_not_run_iis_for_unbounded_status(tmp_path: Path) -> None:
    lp_path = _write_lp(
        tmp_path,
        "unbounded_skip_iis",
        """Minimize
 obj: - x
Subject To
 floor: x >= 0
Bounds
 x free
End
""",
    )

    report = analyze(
        solution={
            "solver_name": "highs",
            "solver_status": "unbounded",
            "infeasibility_diagnostics": {},
        },
        instance=object(),
        lp_path=lp_path,
    )

    assert report.classification.code == "UNBOUNDED_CERTIFIED"
    assert report.iis.available is False
    assert "No se ejecutó IIS" in (report.iis.unavailable_reason or "")
    assert report.certificate.available is True
    assert report.certificate.certificate_type == "primal_ray"
    assert report.feasibility_relaxation.available is False


def test_analyze_combines_classification_certificate_relaxation_and_iis(
    tmp_path: Path,
) -> None:
    lp_path = _write_lp(
        tmp_path,
        "combined",
        """Minimize
 obj: x
Subject To
 demand_floor: x >= 1
 capacity_ceiling: x <= 0
Bounds
 x free
End
""",
    )
    phases: list[str] = []

    report = analyze(
        solution={
            "solver_name": "highs",
            "solver_status": "infeasible",
            "infeasibility_diagnostics": {},
        },
        instance=object(),
        lp_path=lp_path,
        on_phase=phases.append,
    )

    assert phases == [
        "classify",
        "dual_ray",
        "feasibility_relaxation",
        "iis",
    ]
    assert report.classification.code == "INFEASIBLE_CERTIFIED"
    assert report.certificate.validated is True
    assert report.feasibility_relaxation.available is True
    assert report.iis.available is True
    assert report.iis.irreducible is True


def test_highs_iis_is_irreducible_with_two_independent_conflicts(tmp_path: Path) -> None:
    lp_path = _write_lp(
        tmp_path,
        "two_conflicts",
        """Minimize
 obj: x + y
Subject To
 x_floor: x >= 1
 x_ceiling: x <= 0
 y_floor: y >= 2
 y_ceiling: y <= 1
Bounds
 x free
 y free
End
""",
    )

    report = try_compute_iis(object(), "highs", lp_path=lp_path)

    assert report.available is True
    assert report.method == "highs.getIis.irreducible"
    assert report.irreducible is True
    assert report.timed_out is False
    assert report.elapsed_seconds is not None
    assert report.time_limit_seconds is not None
    assert report.time_limit_seconds > 0
    assert len(report.constraint_names) == 2
    assert set(report.constraint_names) in (
        {"x_floor", "x_ceiling"},
        {"y_floor", "y_ceiling"},
    )
    assert len(report.variable_names) == 1


def test_highs_iis_uses_existing_lp_without_pyomo_instance(tmp_path: Path) -> None:
    lp_path = _write_lp(
        tmp_path,
        "lp_only_iis",
        """Minimize
 obj: x
Subject To
 floor: x >= 1
 ceiling: x <= 0
Bounds
 x free
End
""",
    )

    report = try_compute_iis(None, "highs", lp_path=lp_path)

    assert report.available is True
    assert report.irreducible is True
    assert set(report.constraint_names) == {"floor", "ceiling"}


def test_highs_iis_preserves_boxed_variable_bound_conflict(tmp_path: Path) -> None:
    lp_path = _write_lp(
        tmp_path,
        "boxed_bound",
        """Minimize
 obj: x
Subject To
 anchor: x = 0
Bounds
 1 <= x <= 0
End
""",
    )

    report = try_compute_iis(object(), "highs", lp_path=lp_path)

    assert report.available is True
    assert report.constraint_names == []
    assert report.variable_names == ["x"]
    assert report.bound_conflicts == [
        {"name": "x", "side": "LB"},
        {"name": "x", "side": "UB"},
    ]


def test_highs_iis_does_not_label_timeout_subsystem_as_irreducible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lp_path = _write_lp(
        tmp_path,
        "two_conflicts_timeout",
        """Minimize
 obj: x + y
Subject To
 x_floor: x >= 1
 x_ceiling: x <= 0
 y_floor: y >= 2
 y_ceiling: y <= 1
Bounds
 x free
 y free
End
""",
    )
    monkeypatch.setenv("OSEMOSYS_IIS_TIME_LIMIT_SECONDS", "1e-12")

    report = try_compute_iis(object(), "highs", lp_path=lp_path)

    assert report.available is False
    assert report.irreducible is False
    assert report.timed_out is True
    assert report.method == "highs.solve_before_iis"
    assert report.constraint_names == []
    assert report.unavailable_reason is not None
    assert "No se ejecutó IIS" in report.unavailable_reason


@pytest.mark.parametrize(
    ("name", "lp_body", "expected_status"),
    [
        (
            "feasible",
            """Minimize
 obj: x
Subject To
 floor: x >= 1
 ceiling: x <= 2
Bounds
 x free
End
""",
            "kOptimal",
        ),
        (
            "unbounded",
            """Minimize
 obj: - x
Subject To
 floor: x >= 0
Bounds
 x free
End
""",
            "kUnbounded",
        ),
    ],
)
def test_highs_iis_requires_certified_infeasibility(
    tmp_path: Path,
    name: str,
    lp_body: str,
    expected_status: str,
) -> None:
    report = try_compute_iis(
        object(),
        "highs",
        lp_path=_write_lp(tmp_path, name, lp_body),
    )

    assert report.available is False
    assert report.constraint_names == []
    assert report.variable_names == []
    assert report.unavailable_reason is not None
    assert "no certificó infactibilidad" in report.unavailable_reason
    assert expected_status in report.unavailable_reason
