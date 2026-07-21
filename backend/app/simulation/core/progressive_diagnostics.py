"""Métodos progresivos HiGHS que no forman parte del solve productivo.

Todos operan sobre una copia del LP. Nunca modifican el escenario ni reutilizan
el estado interno del solver que ejecutó la simulación.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from time import perf_counter
from typing import Any, Callable


def _limit(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return value if value > 0 else default


def _family(row_name: str) -> str:
    """Extrae el prefijo Pyomo preservado en el LP simbólico."""
    name = str(row_name or "")
    name = re.sub(r"^(?:c_[elu]_)+", "", name)
    match = re.match(r"([A-Za-z][A-Za-z0-9_]*)[\[(]", name)
    if match:
        return match.group(1)
    match = re.match(r"([A-Za-z][A-Za-z0-9_]*)", name)
    return match.group(1) if match else "UNKNOWN"


def run_highs_presolve_diagnostic(lp_path: str | Path) -> dict[str, Any]:
    """Ejecuta sólo presolve y reporta reducciones; no afirma factibilidad."""
    path = Path(lp_path)
    if not path.is_file():
        return {"available": False, "unavailable_reason": "No hay LP reproducible."}
    try:
        import highspy
    except Exception as exc:  # pragma: no cover
        return {"available": False, "unavailable_reason": f"highspy no disponible: {exc!r}"}
    started = perf_counter()
    limit = _limit("OSEMOSYS_PRESOLVE_DIAGNOSTIC_TIME_LIMIT_SECONDS", 120.0)
    try:
        highs = highspy.Highs()
        highs.setOptionValue("output_flag", False)
        highs.setOptionValue("time_limit", limit)
        read_status = highs.readModel(str(path))
        if read_status != highspy.HighsStatus.kOk:
            return {"available": False, "unavailable_reason": f"readModel={read_status}"}
        before_rows, before_cols = highs.getNumRow(), highs.getNumCol()
        status = highs.presolve()
        model_status = str(highs.getModelStatus())
        presolved = highs.getPresolvedLp()
        elapsed = perf_counter() - started
        conclusive_infeasible = "Infeasible" in model_status
        return {
            "available": status == highspy.HighsStatus.kOk,
            "method": "highs.presolve",
            "status": str(status),
            "model_status": model_status,
            "rows_before": before_rows,
            "columns_before": before_cols,
            "rows_after": int(getattr(presolved, "num_row_", 0)),
            "columns_after": int(getattr(presolved, "num_col_", 0)),
            "infeasible_in_presolve": conclusive_infeasible,
            "evidence_level": "CERTIFIED" if conclusive_infeasible else "QUANTIFIED",
            "elapsed_seconds": elapsed,
            "time_limit_seconds": limit,
            "explanation": (
                "HiGHS detectó la contradicción durante presolve."
                if conclusive_infeasible
                else "Presolve no aisló una contradicción; esto no demuestra factibilidad."
            ),
        }
    except Exception as exc:
        return {
            "available": False,
            "method": "highs.presolve",
            "elapsed_seconds": perf_counter() - started,
            "time_limit_seconds": limit,
            "unavailable_reason": repr(exc),
        }


def run_family_diagnosis(
    lp_path: str | Path,
    *,
    cancel_check: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Ablación y reducción incremental de familias de restricciones.

    ``minimal_family_set`` es minimal por inclusión dentro de los probes
    concluyentes; no es un IIS ni garantiza cardinalidad mínima.
    """
    path = Path(lp_path)
    if not path.is_file():
        return {"available": False, "unavailable_reason": "No hay LP reproducible."}
    try:
        import highspy
        import numpy as np
    except Exception as exc:  # pragma: no cover
        return {"available": False, "unavailable_reason": f"highspy no disponible: {exc!r}"}

    total_limit = _limit("OSEMOSYS_FAMILY_DIAG_TIME_LIMIT_SECONDS", 300.0)
    probe_limit = _limit("OSEMOSYS_FAMILY_DIAG_PROBE_TIME_LIMIT_SECONDS", 30.0)
    try:
        max_probes = max(1, int(os.getenv("OSEMOSYS_FAMILY_DIAG_MAX_PROBES", "24")))
    except ValueError:
        max_probes = 24
    started = perf_counter()
    probes: list[dict[str, Any]] = []
    try:
        highs = highspy.Highs()
        highs.setOptionValue("output_flag", False)
        highs.setOptionValue("presolve", "on")
        highs.setOptionValue("time_limit", probe_limit)
        if highs.readModel(str(path)) != highspy.HighsStatus.kOk:
            return {"available": False, "unavailable_reason": "HiGHS no pudo leer el LP."}
        lp = highs.getLp()
        names = list(lp.row_names_ or [])
        lowers = np.asarray(lp.row_lower_, dtype=float)
        uppers = np.asarray(lp.row_upper_, dtype=float)
        family_rows: dict[str, list[int]] = {}
        for index, name in enumerate(names):
            family_rows.setdefault(_family(name), []).append(index)
        # Familias grandes primero: suelen representar balances/contabilidad.
        families = sorted(family_rows, key=lambda item: (-len(family_rows[item]), item))
        current_active = set(families)

        def probe(active: set[str], label: str) -> str:
            nonlocal current_active
            if cancel_check:
                cancel_check()
            if len(probes) >= max_probes or perf_counter() - started >= total_limit:
                return "BUDGET_EXHAUSTED"
            changed = current_active.symmetric_difference(active)
            indices: list[int] = []
            lower_values: list[float] = []
            upper_values: list[float] = []
            for family in changed:
                enabled = family in active
                for row in family_rows[family]:
                    indices.append(row)
                    lower_values.append(float(lowers[row]) if enabled else -highspy.kHighsInf)
                    upper_values.append(float(uppers[row]) if enabled else highspy.kHighsInf)
            if indices:
                highs.changeRowsBounds(
                    len(indices),
                    np.asarray(indices, dtype=np.int32),
                    np.asarray(lower_values, dtype=float),
                    np.asarray(upper_values, dtype=float),
                )
            current_active = set(active)
            probe_started = perf_counter()
            run_status = highs.run()
            model_status = highs.getModelStatus()
            text = str(model_status)
            if model_status == highspy.HighsModelStatus.kInfeasible:
                outcome = "INFEASIBLE"
            elif model_status in {
                highspy.HighsModelStatus.kOptimal,
                highspy.HighsModelStatus.kUnbounded,
            }:
                outcome = "NOT_INFEASIBLE"
            else:
                outcome = "UNKNOWN"
            probes.append({
                "label": label,
                "active_family_count": len(active),
                "outcome": outcome,
                "solver_status": text,
                "elapsed_seconds": perf_counter() - probe_started,
            })
            return outcome if run_status == highspy.HighsStatus.kOk else "UNKNOWN"

        baseline = probe(set(families), "baseline")
        if baseline != "INFEASIBLE":
            return {
                "available": False,
                "method": "highs.incremental_family_diagnosis_v1",
                "probes": probes,
                "unavailable_reason": "El LP no reprodujo infactibilidad certificada.",
            }

        ablation: list[dict[str, Any]] = []
        # Primero examina hasta 12 familias; el presupuesto evita explosión.
        for family in families[:12]:
            outcome = probe(set(families) - {family}, f"ablate:{family}")
            ablation.append({
                "family": family,
                "row_count": len(family_rows[family]),
                "outcome_without_family": outcome,
                "necessary_for_current_conflict": outcome == "NOT_INFEASIBLE",
            })
            if outcome == "BUDGET_EXHAUSTED":
                break

        # Reducción por eliminación incremental; produce minimalidad por inclusión
        # sólo si alcanza a recorrer todos los candidatos de forma concluyente.
        candidate = set(families)
        reduction_complete = True
        for family in sorted(families, key=lambda item: (len(family_rows[item]), item)):
            outcome = probe(candidate - {family}, f"reduce:{family}")
            if outcome == "INFEASIBLE":
                candidate.remove(family)
            elif outcome in {"UNKNOWN", "BUDGET_EXHAUSTED"}:
                reduction_complete = False
            if outcome == "BUDGET_EXHAUSTED":
                break

        unknown = sum(item["outcome"] == "UNKNOWN" for item in probes)
        return {
            "available": True,
            "method": "highs.incremental_family_diagnosis_v1",
            "evidence_level": "QUANTIFIED",
            "global_certificate": False,
            "family_count": len(families),
            "row_count": len(names),
            "families": [
                {"family": family, "row_count": len(family_rows[family])}
                for family in families
            ],
            "ablation": ablation,
            "minimal_family_set": sorted(candidate),
            "reduction_complete": reduction_complete and unknown == 0,
            "probes": probes,
            "probe_count": len(probes),
            "unknown_probe_count": unknown,
            "elapsed_seconds": perf_counter() - started,
            "time_limit_seconds": total_limit,
            "explanation": (
                "Aislamiento por familias; orienta dónde investigar, pero no sustituye un IIS."
            ),
        }
    except Exception as exc:
        return {
            "available": False,
            "method": "highs.incremental_family_diagnosis_v1",
            "elapsed_seconds": perf_counter() - started,
            "unavailable_reason": repr(exc),
        }
