"""CSV-only, conservative supplementary infeasibility diagnostics.

This module deliberately performs no optimization or solver calls.  Its only
certificates are direct algebraic contradictions already present in structural
findings (a lower bound greater than an upper bound).
"""
from __future__ import annotations

import csv
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

_MAX_REPRESENTATIVES = 100


def _report(method: str, evidence_level: str, available: bool, explanation: str,
            how_to_use: str, **values: Any) -> dict[str, Any]:
    return {"method": method, "evidence_level": evidence_level,
            "available": available, "explanation": explanation,
            "how_to_use": how_to_use, **values}


def _finding_dict(finding: Any) -> dict[str, Any]:
    if isinstance(finding, dict):
        return finding
    converter = getattr(finding, "to_dict", None)
    return converter() if callable(converter) else {
        "code": getattr(finding, "code", "UNKNOWN"),
        "dimensions": getattr(finding, "dimensions", {}) or {},
        "values": getattr(finding, "values", {}) or {},
    }


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _witnesses(findings: Iterable[Any]) -> list[dict[str, Any]]:
    """Build only witnesses whose two scalar inequalities prove L > U."""
    result: list[dict[str, Any]] = []
    for raw in findings:
        finding = _finding_dict(raw)
        code, values = finding.get("code"), finding.get("values", {}) or {}
        if code == "PARAMETER_BOUND_CONFLICT":
            lower, upper = _number(values.get("lower_value")), _number(values.get("upper_value"))
            lower_name = str(values.get("lower_parameter", "lower_bound"))
            upper_name = str(values.get("upper_parameter", "upper_bound"))
        elif code == "MANDATED_ANNUAL_ACTIVITY_WITHOUT_USABLE_CAPACITY":
            lower, upper = _number(values.get("required_activity")), _number(values.get("capacity_activity_upper_bound"))
            lower_name, upper_name = "TotalTechnologyAnnualActivityLowerLimit", "capacity_activity_upper_bound"
        else:
            continue
        if lower is None or upper is None or lower <= upper:
            continue
        dimensions = {str(k): str(v) for k, v in (finding.get("dimensions", {}) or {}).items()}
        result.append({
            "finding_code": code, "dimensions": dimensions, "lower": lower, "upper": upper,
            "gap": lower - upper, "certified": True,
            "constraints": [
                {"symbolic": f"x >= {lower}", "source": lower_name},
                {"symbolic": f"x <= {upper}", "source": upper_name},
            ],
        })
    return result


def _iter_rows(root: Path, name: str) -> Iterable[dict[str, str]]:
    """Stream a CSV so diagnostics never duplicate a large parameter in RAM."""
    path = root / f"{name}.csv"
    if not path.is_file():
        return
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                yield {
                    str(key).strip(): str(value).strip()
                    for key, value in row.items()
                    if key is not None
                }
    except (OSError, csv.Error, UnicodeError):
        return


def _read_rows(root: Path, name: str) -> list[dict[str, str]]:
    return list(_iter_rows(root, name))


def _positive_demands(root: Path) -> tuple[set[tuple[str, str, str]], bool]:
    available = (root / "AccumulatedAnnualDemand.csv").exists() or (root / "SpecifiedAnnualDemand.csv").exists()
    demands: set[tuple[str, str, str]] = set()
    for name in ("AccumulatedAnnualDemand", "SpecifiedAnnualDemand"):
        for row in _iter_rows(root, name):
            if (_number(row.get("VALUE")) or 0) > 0:
                demands.add((row.get("REGION", ""), row.get("FUEL", ""), row.get("YEAR", "")))
    return demands, available


def _graph_report(root: Path) -> dict[str, Any]:
    graph_available = (root / "InputActivityRatio.csv").exists() or (root / "OutputActivityRatio.csv").exists()
    processes_in: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    processes_out: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    for name, target in (("InputActivityRatio", processes_in), ("OutputActivityRatio", processes_out)):
        for row in _iter_rows(root, name):
            if (_number(row.get("VALUE")) or 0) > 0:
                target[(row.get("REGION", ""), row.get("TECHNOLOGY", ""), row.get("MODE_OF_OPERATION", ""), row.get("YEAR", ""))].add(row.get("FUEL", ""))
    nodes: set[tuple[str, str, str]] = set()
    edges: set[tuple[tuple[str, str, str], tuple[str, str, str]]] = set()
    reachable: set[tuple[str, str, str]] = set()
    for key, produced in processes_out.items():
        region, _, _, year = key
        outs = {(region, fuel, year) for fuel in produced}
        ins = {(region, fuel, year) for fuel in processes_in.get(key, set())}
        nodes |= outs | ins
        if not ins:
            reachable |= outs
        for source in ins:
            for target in outs:
                edges.add((source, target))
    changed = True
    while changed:
        changed = False
        for key, produced in processes_out.items():
            region, _, _, year = key
            required = {(region, fuel, year) for fuel in processes_in.get(key, set())}
            made = {(region, fuel, year) for fuel in produced}
            if required.issubset(reachable) and not made.issubset(reachable):
                reachable |= made; changed = True
    demands, demand_available = _positive_demands(root)
    unreachable = [{"REGION": r, "FUEL": f, "YEAR": y}
                   for r, f, y in sorted(demands - reachable)]
    degree: Counter[tuple[str, str, str]] = Counter()
    for source, target in edges:
        degree[source] += 1; degree[target] += 1
    ranked = [{"REGION": key[0], "FUEL": key[1], "YEAR": key[2], "degree": value}
              for key, value in sorted(degree.items(), key=lambda item: (-item[1], item[0]))[:_MAX_REPRESENTATIVES]]
    return _report("csv_fuel_dependency_graph", "STRUCTURAL", graph_available,
                   "La alcanzabilidad verifica la topología. No se presenta un corte mínimo de capacidad porque esta fase no calcula capacidades físicas.",
                   "Revise fuels demandados inalcanzables y nodos de alto grado; confirme cualquier cuello de botella con límites de capacidad.",
                   node_count=len(nodes), edge_count=len(edges), demand_files_available=demand_available,
                   unreachable_demanded_fuels=unreachable[:_MAX_REPRESENTATIVES],
                   unreachable_demanded_fuel_count=len(unreachable), topological_bottlenecks=ranked)


def _numerical(root: Path) -> dict[str, Any]:
    all_files = sorted(root.glob("*.csv")) if root.is_dir() else []
    files: list[Path] = []
    for path in all_files:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                fields = next(csv.reader(handle), [])
            normalized_fields = [str(field).strip().upper() for field in fields]
            # Los archivos de conjuntos también usan una única columna VALUE,
            # pero contienen códigos y no coeficientes numéricos.
            if "VALUE" in normalized_fields and len(normalized_fields) > 1:
                files.append(path)
        except (OSError, csv.Error, UnicodeError):
            continue
    total = finite = nan = inf = missing = invalid = near_zero = 0
    nonzero: list[float] = []
    invalid_by_file: Counter[str] = Counter()
    problem_examples: list[dict[str, str]] = []
    for path in files:
        for row in _iter_rows(root, path.stem):
            if "VALUE" not in row:
                continue
            total += 1
            raw_value = str(row["VALUE"]).strip()
            if not raw_value:
                missing += 1
                continue
            try: value = float(raw_value)
            except (TypeError, ValueError):
                invalid += 1
                invalid_by_file[path.name] += 1
                if len(problem_examples) < _MAX_REPRESENTATIVES:
                    problem_examples.append({"file": path.name, "value": raw_value, "kind": "INVALID"})
                continue
            if math.isnan(value):
                nan += 1
                if len(problem_examples) < _MAX_REPRESENTATIVES:
                    problem_examples.append({"file": path.name, "value": raw_value, "kind": "NAN"})
                continue
            if math.isinf(value):
                inf += 1
                if len(problem_examples) < _MAX_REPRESENTATIVES:
                    problem_examples.append({"file": path.name, "value": raw_value, "kind": "INFINITE"})
                continue
            finite += 1
            if value != 0: nonzero.append(abs(value))
            if 0 < abs(value) < 1e-9: near_zero += 1
    minimum, maximum = (min(nonzero), max(nonzero)) if nonzero else (None, None)
    orders = (
        math.log10(maximum) - math.log10(minimum)
        if minimum not in (None, 0) and maximum not in (None, 0)
        else None
    )
    ratio = (10.0 ** orders) if orders is not None and orders <= 308 else None
    return _report("csv_value_numerical_scan", "OBSERVATIONAL", bool(files),
                   "Escanea valores CSV. El rango global puede incluir cotas centinela intencionales y no demuestra una infactibilidad numérica.",
                   "Revise primero NaN, infinitos y valores inválidos. Inspeccione cada parámetro antes de reescalar; nunca reescale todos los CSV usando sólo este agregado.",
                   csv_file_count=len(files), value_count=total, finite_count=finite,
                   missing_count=missing, invalid_count=invalid, nan_count=nan,
                   inf_count=inf, nonzero_min=minimum, nonzero_max=maximum, dynamic_range=ratio,
                   dynamic_range_orders_of_magnitude=orders, near_zero_count=near_zero,
                   dynamic_range_flag=bool(orders is not None and orders >= 9),
                   invalid_by_file=dict(invalid_by_file.most_common()),
                   problem_examples=problem_examples)


def _baseline(root: Path, baseline_csv_dir: str | Path | None) -> dict[str, Any]:
    if baseline_csv_dir is None or not Path(baseline_csv_dir).is_dir():
        return _report("csv_key_value_baseline_comparison", "OBSERVATIONAL", False,
                       "No se proporcionaron CSV de un escenario de referencia.", "Indique un escenario comparable; si también es infactible, use el resultado sólo como comparación observacional.", unavailable_reason="Escenario de referencia ausente o no disponible.")
    base = Path(baseline_csv_dir); differences: list[dict[str, Any]] = []; count = 0
    current_files = {p.name for p in root.glob("*.csv")}; baseline_files = {p.name for p in base.glob("*.csv")}
    compared_files = 0
    skipped_large_files: list[str] = []
    max_file_bytes = 64 * 1024 * 1024
    for filename in sorted(current_files & baseline_files):
        current_path, baseline_path = root / filename, base / filename
        if current_path.stat().st_size > max_file_bytes or baseline_path.stat().st_size > max_file_bytes:
            skipped_large_files.append(filename)
            continue
        compared_files += 1
        def keyed(rows: list[dict[str, str]]) -> dict[tuple[tuple[str, str], ...], str]:
            return {tuple(sorted((k, v) for k, v in row.items() if k != "VALUE")): row.get("VALUE", "") for row in rows}
        now, old = keyed(_read_rows(root, Path(filename).stem)), keyed(_read_rows(base, Path(filename).stem))
        for key in set(now) | set(old):
            if now.get(key) != old.get(key):
                count += 1
                if len(differences) < _MAX_REPRESENTATIVES:
                    differences.append({"file": filename, "key": dict(key), "current_value": now.get(key), "baseline_value": old.get(key)})
    return _report("csv_key_value_baseline_comparison", "OBSERVATIONAL", True,
                   "Las diferencias son cambios de datos, no una prueba de causalidad ni de infactibilidad.", "Use las claves modificadas para focalizar la revisión y valide cada hipótesis en una nueva corrida.",
                   compared_file_count=compared_files, skipped_large_files=skipped_large_files,
                   comparison_complete=not skipped_large_files, difference_count=count, differences=differences)


def run_advanced_diagnostic_suite(csv_dir: str | Path, structural_findings: Iterable[Any], baseline_csv_dir: str | Path | None = None) -> dict[str, Any]:
    """Return bounded, JSON-serializable reports without changing CSVs or solving."""
    root = Path(csv_dir)
    findings = [_finding_dict(item) for item in structural_findings]
    witnesses = _witnesses(findings)
    representative = witnesses[:_MAX_REPRESENTATIVES]
    code_counts = Counter(str(item.get("code", "UNKNOWN")) for item in findings)
    grouped: dict[str, dict[str, dict[str, dict[str, list[dict[str, Any]]]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    )
    for witness in representative:
        d = witness["dimensions"]
        grouped[witness["finding_code"]][d.get("REGION", "UNSPECIFIED")][d.get("YEAR", "UNSPECIFIED")][d.get("TECHNOLOGY", d.get("FUEL", "UNSPECIFIED"))].append(witness)
    common = dict(witness_count=len(witnesses), witnesses=representative)
    reports = {
        "reduced_core": _report("direct_scalar_bound_reduction", "CERTIFIED" if witnesses else "NONE", True, "Cada núcleo listado contiene una variable escalar cuya cota inferior es mayor que la superior.", "Revise una de las dos cotas del testigo; no modifique ambas automáticamente.", **common),
        "hierarchical_isolation": _report("hierarchical_exact_witness_grouping", "CERTIFIED" if witnesses else "NONE", True, "Agrupa testigos reducidos certificados; la agrupación no añade una prueba nueva.", "Navegue por código, región, año y tecnología/fuel para priorizar y asignar la revisión.", hierarchy=dict(grouped)), 
        "selective_relaxation": _report("analytical_single_bound_relaxations", "CERTIFIED" if witnesses else "NONE", True, "Las alternativas reparan únicamente cada contradicción escalar y nunca se aplican automáticamente.", "Elija reducir el mínimo o aumentar el máximo sólo después de revisar la regla de negocio y las unidades.", alternatives=[{"dimensions": w["dimensions"], "gap": w["gap"], "alternatives": [{"action": "decrease_lower_to_upper", "new_lower": w["upper"], "change": -w["gap"]}, {"action": "increase_upper_to_lower", "new_upper": w["lower"], "change": w["gap"]}]} for w in representative], witness_count=len(witnesses)),
        "bound_propagation": _report("structural_finding_summary", "STRUCTURAL", True, "Consolida los hallazgos producidos por la propagación capacidad→actividad→horizonte y sus parámetros declarados.", "Siga la cadena de parámetros y vuelva a ejecutar la auditoría estructural después de editar una copia.", finding_code_counts=dict(sorted(code_counts.items())), chains=[{"code": f.get("code"), "dimensions": f.get("dimensions", {}), "related_parameters": f.get("related_parameters", [])} for f in findings[:_MAX_REPRESENTATIVES]], finding_count=len(findings)),
        "baseline_comparison": _baseline(root, baseline_csv_dir),
        "iis_enumeration": _report("enumerate_exact_two_constraint_cores", "CERTIFIED" if witnesses else "NONE", True, "Cada núcleo es algebraicamente irreducible: al retirar cualquiera de las dos desigualdades queda una semirrecta factible.", "Trátelos como IIS locales exactos; no constituyen una enumeración de todos los IIS del modelo global.", core_count=len(witnesses), cores=[{**w, "irreducible_algebraically": True} for w in representative]),
        "maxfs_mcs": _report("analytical_singleton_corrections", "CERTIFIED" if witnesses else "NONE", True, "Cada alternativa corrige un miembro de un núcleo local de dos restricciones; no se afirma optimalidad MaxFS/MCS global.", "Úselo sólo para comparar opciones locales de reparación y valide nuevamente el modelo completo.", correction_count=2 * len(witnesses), corrections=[{"dimensions": w["dimensions"], "singleton_corrections": [w["constraints"][0]["source"], w["constraints"][1]["source"]]} for w in representative]),
        "quickxplain": _report("analytical_quickxplain_equivalent_reduced_core", "CERTIFIED" if witnesses else "NONE", True, "Equivalente analítico de QuickXplain sobre un núcleo escalar ya reducido; no es QuickXplain sobre el LP global.", "La certificación aplica únicamente a la pareja mostrada.", certified_core_count=len(witnesses), cores=representative),
        "decomposition": _report("finding_count_decomposition", "STRUCTURAL", True, "Las celdas agrupan hallazgos; sólo una celda con testigos certificados se marca localmente infactible.", "Priorice región-año con testigos certificados antes que agregados meramente observacionales.", cells=[{"REGION": r, "YEAR": y, "finding_count": sum(1 for f in findings if (f.get("dimensions", {}) or {}).get("REGION") == r and (f.get("dimensions", {}) or {}).get("YEAR") == y), "certified_witness_count": sum(1 for w in witnesses if w["dimensions"].get("REGION") == r and w["dimensions"].get("YEAR") == y), "certified_locally_infeasible": any(w["dimensions"].get("REGION") == r and w["dimensions"].get("YEAR") == y for w in witnesses)} for r, y in sorted({((f.get("dimensions", {}) or {}).get("REGION", "UNSPECIFIED"), (f.get("dimensions", {}) or {}).get("YEAR", "UNSPECIFIED")) for f in findings})][:_MAX_REPRESENTATIVES]),
        "graph_bottleneck": _graph_report(root), "numerical": _numerical(root),
    }
    return reports
