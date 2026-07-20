"""Diagnóstico estructural conservador sobre los CSV finales de OSeMOSYS.

Estas reglas no sustituyen al solver. Sólo emiten hallazgos deterministas cuando
los propios datos demuestran ausencia de una ruta local de suministro o límites
que bloquean a todos los productores conocidos.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class StructuralFinding:
    code: str
    severity: str
    evidence_level: str
    message: str
    dimensions: dict[str, str] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)
    related_parameters: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read(csv_dir: Path, name: str) -> pd.DataFrame:
    path = csv_dir / f"{name}.csv"
    if not path.exists():
        return pd.DataFrame()
    try:
        frame = pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
    if "VALUE" in frame.columns:
        frame["VALUE"] = pd.to_numeric(frame["VALUE"], errors="coerce").fillna(0.0)
    for col in frame.columns:
        if col != "VALUE":
            frame[col] = frame[col].astype(str).str.strip()
    return frame


def _positive_demand_keys(csv_dir: Path) -> dict[tuple[str, str, str], dict[str, float]]:
    demands: dict[tuple[str, str, str], dict[str, float]] = {}

    accumulated = _read(csv_dir, "AccumulatedAnnualDemand")
    if not accumulated.empty:
        for row in accumulated[accumulated["VALUE"] > 0].itertuples(index=False):
            key = (str(row.REGION), str(row.FUEL), str(row.YEAR))
            demands.setdefault(key, {})["accumulated"] = float(row.VALUE)

    specified = _read(csv_dir, "SpecifiedAnnualDemand")
    profiles = _read(csv_dir, "SpecifiedDemandProfile")
    active_profile_keys: set[tuple[str, str, str]] = set()
    if not profiles.empty:
        active_profile_keys = {
            (str(row.REGION), str(row.FUEL), str(row.YEAR))
            for row in profiles[profiles["VALUE"] > 0].itertuples(index=False)
        }
    if not specified.empty:
        for row in specified[specified["VALUE"] > 0].itertuples(index=False):
            key = (str(row.REGION), str(row.FUEL), str(row.YEAR))
            # Demand = annual demand * profile. Un perfil ausente/cero genera
            # demanda matemática cero, aunque es un problema de calidad aparte.
            if key in active_profile_keys:
                demands.setdefault(key, {})["specified"] = float(row.VALUE)
    return demands


def _producer_rows(csv_dir: Path) -> pd.DataFrame:
    output = _read(csv_dir, "OutputActivityRatio")
    required = {"REGION", "TECHNOLOGY", "FUEL", "YEAR", "VALUE"}
    if output.empty or not required.issubset(output.columns):
        return pd.DataFrame(columns=sorted(required))
    return output[output["VALUE"] > 0].copy()


def _lookup_values(frame: pd.DataFrame) -> dict[tuple[str, str, str], float]:
    required = {"REGION", "TECHNOLOGY", "YEAR", "VALUE"}
    if frame.empty or not required.issubset(frame.columns):
        return {}
    return {
        (str(row.REGION), str(row.TECHNOLOGY), str(row.YEAR)): float(row.VALUE)
        for row in frame.itertuples(index=False)
    }


def _blocked_reason_maps(csv_dir: Path) -> tuple[dict, dict, dict]:
    max_capacity = _lookup_values(_read(csv_dir, "TotalAnnualMaxCapacity"))
    availability = _lookup_values(_read(csv_dir, "AvailabilityFactor"))

    capacity_factor = _read(csv_dir, "CapacityFactor")
    all_cf_zero: dict[tuple[str, str, str], bool] = {}
    if not capacity_factor.empty:
        grouped = capacity_factor.groupby(["REGION", "TECHNOLOGY", "YEAR"])["VALUE"]
        all_cf_zero = {
            (str(r), str(t), str(y)): bool((values <= 0).all())
            for (r, t, y), values in grouped
        }
    return max_capacity, availability, all_cf_zero


def _capacity_context(csv_dir: Path) -> dict[str, object]:
    """Carga una vez los datos requeridos para la prueba de capacidad utilizable."""
    capacity_factor = _read(csv_dir, "CapacityFactor")
    all_cf_zero: dict[tuple[str, str, str], bool] = {}
    if not capacity_factor.empty:
        all_cf_zero = {
            (str(region), str(tech), str(year)): bool((values <= 0).all())
            for (region, tech, year), values in capacity_factor.groupby(
                ["REGION", "TECHNOLOGY", "YEAR"]
            )["VALUE"]
        }
    def two_dim(name: str) -> dict[tuple[str, str], float]:
        frame = _read(csv_dir, name)
        if frame.empty:
            return {}
        return {
            (str(row.REGION), str(row.TECHNOLOGY)): float(row.VALUE)
            for row in frame.itertuples(index=False)
        }
    years = _read(csv_dir, "YEAR")
    return {
        "max_capacity": _lookup_values(_read(csv_dir, "TotalAnnualMaxCapacity")),
        "availability": _lookup_values(_read(csv_dir, "AvailabilityFactor")),
        "residual": _lookup_values(_read(csv_dir, "ResidualCapacity")),
        "max_investment": _lookup_values(
            _read(csv_dir, "TotalAnnualMaxCapacityInvestment")
        ),
        "all_cf_zero": all_cf_zero,
        "capacity_to_activity": two_dim("CapacityToActivityUnit"),
        "operational_life": two_dim("OperationalLife"),
        "years": [str(value) for value in years.iloc[:, 0]] if not years.empty else [],
    }


def _usable_capacity_reasons(
    context: dict[str, object], region: str, technology: str, year: str
) -> list[str]:
    """Explica por qué una tecnología no puede aportar actividad en un año.

    Es una prueba conservadora de *ausencia* de capacidad posible: contempla
    capacidad residual, inversiones aún vivas, vida útil, límites explícitos,
    factores y ``CapacityToActivityUnit``. Los parámetros ausentes conservan
    el default OSeMOSYS (sin límite, vida 1, factores/conversión 1).
    """
    key = (region, technology, year)
    max_capacity = context["max_capacity"]
    availability = context["availability"]
    residual = context["residual"]
    max_investment = context["max_investment"]
    all_cf_zero = context["all_cf_zero"]
    capacity_to_activity = context["capacity_to_activity"]
    operational_life_map = context["operational_life"]
    years = context["years"]
    reasons: list[str] = []
    if key in max_capacity and max_capacity[key] <= 0:
        reasons.append("total_max_capacity_zero")
    if key in availability and availability[key] <= 0:
        reasons.append("availability_factor_zero")
    if all_cf_zero.get(key, False):
        reasons.append("all_capacity_factors_zero")
    if capacity_to_activity.get((region, technology), 1.0) <= 0:
        reasons.append("capacity_to_activity_unit_zero")

    try:
        current_year = int(year)
    except ValueError:
        return reasons
    operational_life = operational_life_map.get((region, technology), 1.0)
    possible = residual.get(key, 0.0) > 0
    for raw_year in (years or [year]):
        try:
            investment_year = int(raw_year)
        except ValueError:
            continue
        investment_key = (region, technology, raw_year)
        # CSV ausente para una tupla implica el default sin límite (9,999,999).
        investment_max = max_investment.get(investment_key, 9_999_999.0)
        if (
            investment_year <= current_year
            and current_year - investment_year < operational_life
            and investment_max > 0
        ):
            possible = True
            break
    if not possible:
        reasons.append("no_residual_or_live_investment_path")
    return reasons


def _detect_fuel_reachability(
    root: Path, demands: dict[tuple[str, str, str], dict[str, float]]
) -> list[StructuralFinding]:
    """Cierre de grafo CSV/pandas para detectar ciclos sin fuente primaria.

    Un ``OutputActivityRatio`` local no basta para satisfacer demanda si todos
    sus productores dependen, directa o indirectamente, del mismo ciclo de
    combustibles. Sólo se marca un fuel cuando ningún proceso sin inputs puede
    iniciar una ruta hacia él.
    """
    columns = {"REGION", "TECHNOLOGY", "MODE_OF_OPERATION", "FUEL", "YEAR", "VALUE"}
    inputs = _read(root, "InputActivityRatio")
    outputs = _read(root, "OutputActivityRatio")
    if not columns.issubset(outputs.columns):
        return []
    inputs = inputs[inputs["VALUE"] > 1e-12] if columns.issubset(inputs.columns) else pd.DataFrame(columns=outputs.columns)
    outputs = outputs[outputs["VALUE"] > 1e-12]
    process_inputs: dict[tuple[str, str, str, str], set[str]] = {}
    process_outputs: dict[tuple[str, str, str, str], set[str]] = {}
    for row in inputs.itertuples(index=False):
        key = (str(row.REGION), str(row.TECHNOLOGY), str(row.MODE_OF_OPERATION), str(row.YEAR))
        process_inputs.setdefault(key, set()).add(str(row.FUEL))
    for row in outputs.itertuples(index=False):
        key = (str(row.REGION), str(row.TECHNOLOGY), str(row.MODE_OF_OPERATION), str(row.YEAR))
        process_outputs.setdefault(key, set()).add(str(row.FUEL))

    processes_by_region_year: dict[tuple[str, str], list[tuple[str, str, str, str]]] = {}
    for process in process_outputs:
        processes_by_region_year.setdefault((process[0], process[3]), []).append(process)
    demands_by_region_year: dict[tuple[str, str], list[tuple[str, dict[str, float]]]] = {}
    for (region, fuel, year), demand_values in demands.items():
        demands_by_region_year.setdefault((region, year), []).append((fuel, demand_values))

    findings: list[StructuralFinding] = []
    for (region, year), demanded_fuels in demands_by_region_year.items():
        processes = processes_by_region_year.get((region, year), [])
        if not processes:
            continue
        reachable: set[str] = set()
        primary = 0
        producers_by_fuel: dict[str, list[tuple[str, str, str, str]]] = {}
        for process in processes:
            for output_fuel in process_outputs[process]:
                producers_by_fuel.setdefault(output_fuel, []).append(process)
            if not process_inputs.get(process):
                reachable.update(process_outputs[process])
                primary += 1
        changed = True
        while changed:
            changed = False
            for process in processes:
                if process_inputs.get(process, set()).issubset(reachable):
                    before = len(reachable)
                    reachable.update(process_outputs[process])
                    changed = changed or len(reachable) > before
        for fuel, demand_values in demanded_fuels:
            # Sin productores, la regla DEMAND_WITHOUT_LOCAL_PRODUCER ya da
            # una explicación más directa.
            candidates = producers_by_fuel.get(fuel, [])
            if not candidates or fuel in reachable:
                continue
            findings.append(
                StructuralFinding(
                    code="DEMAND_FUEL_WITHOUT_PRIMARY_INPUT_ROUTE",
                    severity="ERROR",
                    evidence_level="STRUCTURAL",
                    message=(
                        "El fuel demandado sólo se produce mediante rutas que dependen "
                        "de inputs no alcanzables; no existe una fuente primaria local."
                    ),
                    dimensions={"REGION": region, "FUEL": fuel, "YEAR": year},
                    values={
                        "demand": demand_values,
                        "primary_processes": primary,
                        "reachable_fuels": len(reachable),
                        "candidate_processes": [
                            {
                                "TECHNOLOGY": process[1],
                                "MODE_OF_OPERATION": process[2],
                                "required_inputs": sorted(process_inputs.get(process, set())),
                            }
                            for process in candidates[:25]
                        ],
                    },
                    related_parameters=[
                        "AccumulatedAnnualDemand",
                        "SpecifiedAnnualDemand",
                        "SpecifiedDemandProfile",
                        "InputActivityRatio",
                        "OutputActivityRatio",
                    ],
                )
            )
    return findings


def _detect_activity_minimum_capacity_conflicts(root: Path) -> list[StructuralFinding]:
    """Detecta mínimos anuales de actividad físicamente inalcanzables.

    Implementa una cota necesaria, no una aproximación de solución: agrega la
    capacidad residual y las inversiones máximas aún vivas, y la convierte a
    actividad con los factores OSeMOSYS. Un hallazgo prueba infactibilidad para
    esa fila sin necesidad de resolver el LP completo.
    """
    tol = 1e-6
    annual_min = _read(root, "TotalTechnologyAnnualActivityLowerLimit")
    required = {"REGION", "TECHNOLOGY", "YEAR", "VALUE"}
    if annual_min.empty or not required.issubset(annual_min.columns):
        return []
    annual_min = annual_min[annual_min["VALUE"] > tol]
    if annual_min.empty:
        return []

    def by_key(name: str) -> dict[tuple[str, str, str], float]:
        return _lookup_values(_read(root, name))

    residual = by_key("ResidualCapacity")
    max_investment = by_key("TotalAnnualMaxCapacityInvestment")
    max_capacity = by_key("TotalAnnualMaxCapacity")
    availability = by_key("AvailabilityFactor")
    capacity_factor = _read(root, "CapacityFactor")
    year_split = _read(root, "YearSplit")
    c2a_frame = _read(root, "CapacityToActivityUnit")
    life_frame = _read(root, "OperationalLife")
    years_frame = _read(root, "YEAR")
    if years_frame.empty:
        return []
    years = sorted(int(float(value)) for value in years_frame["VALUE"])
    c2a = {
        (str(row.REGION), str(row.TECHNOLOGY)): float(row.VALUE)
        for row in c2a_frame.itertuples(index=False)
    } if {"REGION", "TECHNOLOGY", "VALUE"}.issubset(c2a_frame.columns) else {}
    life = {
        (str(row.REGION), str(row.TECHNOLOGY)): float(row.VALUE)
        for row in life_frame.itertuples(index=False)
    } if {"REGION", "TECHNOLOGY", "VALUE"}.issubset(life_frame.columns) else {}
    cf = {
        (str(row.REGION), str(row.TECHNOLOGY), str(row.TIMESLICE), str(row.YEAR)): float(row.VALUE)
        for row in capacity_factor.itertuples(index=False)
    } if {"REGION", "TECHNOLOGY", "TIMESLICE", "YEAR", "VALUE"}.issubset(capacity_factor.columns) else {}
    split = {
        (str(row.TIMESLICE), str(row.YEAR)): float(row.VALUE)
        for row in year_split.itertuples(index=False)
    } if {"TIMESLICE", "YEAR", "VALUE"}.issubset(year_split.columns) else {}
    timeslices_by_year: dict[str, list[str]] = {}
    for timeslice, year in split:
        timeslices_by_year.setdefault(year, []).append(timeslice)

    findings: list[StructuralFinding] = []
    for row in annual_min.itertuples(index=False):
        region, technology, raw_year = str(row.REGION), str(row.TECHNOLOGY), str(row.YEAR)
        year = int(raw_year)
        operational_life = life.get((region, technology), 1.0)
        new_capacity = 0.0
        for investment_year in years:
            if investment_year > year or year - investment_year >= operational_life:
                continue
            maximum = max_investment.get(
                (region, technology, str(investment_year)), 9_999_999.0
            )
            if maximum >= 9_999_999.0:
                new_capacity = 9_999_999.0
                break
            new_capacity += max(0.0, maximum)
        capacity_upper = min(
            residual.get((region, technology, raw_year), 0.0) + new_capacity,
            max_capacity.get((region, technology, raw_year), 9_999_999.0),
        )
        annual_factor = sum(
            split[(timeslice, raw_year)]
            * cf.get((region, technology, timeslice, raw_year), 1.0)
            for timeslice in timeslices_by_year.get(raw_year, [])
        )
        activity_upper = capacity_upper * c2a.get((region, technology), 1.0)
        activity_upper *= availability.get((region, technology, raw_year), 1.0)
        activity_upper *= annual_factor
        required_activity = float(row.VALUE)
        if required_activity <= activity_upper + tol:
            continue
        gap = required_activity - activity_upper
        findings.append(
            StructuralFinding(
                code="MANDATED_ANNUAL_ACTIVITY_WITHOUT_USABLE_CAPACITY",
                severity="ERROR",
                evidence_level="STRUCTURAL",
                message=(
                    "La actividad anual mínima exigida supera la actividad máxima "
                    "que permiten capacidad residual e inversiones vivas."
                ),
                dimensions={
                    "REGION": region,
                    "TECHNOLOGY": technology,
                    "YEAR": raw_year,
                },
                values={
                    "required_activity": required_activity,
                    "capacity_activity_upper_bound": activity_upper,
                    "capacity_upper_bound": capacity_upper,
                    "gap": gap,
                    "residual_capacity": residual.get((region, technology, raw_year), 0.0),
                    "eligible_max_new_capacity": new_capacity,
                },
                related_parameters=[
                    "TotalTechnologyAnnualActivityLowerLimit",
                    "ResidualCapacity",
                    "TotalAnnualMaxCapacityInvestment",
                    "OperationalLife",
                    "CapacityToActivityUnit",
                    "CapacityFactor",
                    "AvailabilityFactor",
                    "YearSplit",
                ],
            )
        )
    return findings


def _detect_mandated_emission_limit_conflicts(root: Path) -> list[StructuralFinding]:
    """Detecta emisiones mínimas inevitables contra límites anuales.

    Sólo usa actividad mínima de tecnologías cuyos modos activos (observados en
    Input/OutputActivityRatio) tienen una tasa positiva para la emisión. Así no
    se afirma un conflicto cuando existe un modo activo conocido de emisión cero.
    """
    tol, inf = 1e-9, 9_999_999.0
    limits = _read(root, "AnnualEmissionLimit")
    activity_min = _read(root, "TotalTechnologyAnnualActivityLowerLimit")
    emission_ratio = _read(root, "EmissionActivityRatio")
    if any(frame.empty for frame in (limits, activity_min, emission_ratio)):
        return []
    required_limit = {"REGION", "EMISSION", "YEAR", "VALUE"}
    required_activity = {"REGION", "TECHNOLOGY", "YEAR", "VALUE"}
    required_ratio = {"REGION", "TECHNOLOGY", "EMISSION", "YEAR", "MODE_OF_OPERATION", "VALUE"}
    if not required_limit.issubset(limits.columns) or not required_activity.issubset(activity_min.columns) or not required_ratio.issubset(emission_ratio.columns):
        return []

    # ``AnnualActivity`` suma RateOfActivity sobre todo MODE_OF_OPERATION.
    # Por ello el límite sólo demuestra emisiones inevitables si *todos* los
    # modos que la instancia Pyomo carga tienen una tasa positiva; un modo sin
    # tasa explícita usa el default OSeMOSYS cero.
    mode_set = _read(root, "MODE_OF_OPERATION")
    if mode_set.empty or "VALUE" not in mode_set.columns:
        return []
    model_modes = {str(value) for value in mode_set["VALUE"]}
    if not model_modes:
        return []

    ratio_by_key: dict[tuple[str, str, str, str], dict[str, float]] = {}
    for row in emission_ratio.itertuples(index=False):
        key = (str(row.REGION), str(row.TECHNOLOGY), str(row.EMISSION), str(row.YEAR))
        ratio_by_key.setdefault(key, {})[str(row.MODE_OF_OPERATION)] = float(row.VALUE)

    mandatory = activity_min[activity_min["VALUE"] > tol]
    findings: list[StructuralFinding] = []
    for limit in limits.itertuples(index=False):
        cap = float(limit.VALUE)
        if cap >= inf:
            continue
        region, emission, year = str(limit.REGION), str(limit.EMISSION), str(limit.YEAR)
        implied = 0.0
        contributors: list[dict[str, Any]] = []
        for activity in mandatory[(mandatory["REGION"] == region) & (mandatory["YEAR"] == year)].itertuples(index=False):
            technology = str(activity.TECHNOLOGY)
            rates = ratio_by_key.get((region, technology, emission, year), {})
            if any(rates.get(mode, 0.0) <= tol for mode in model_modes):
                continue
            minimum_rate = min(rates[mode] for mode in model_modes)
            contribution = float(activity.VALUE) * minimum_rate
            implied += contribution
            contributors.append({
                "TECHNOLOGY": technology,
                "activity_minimum": float(activity.VALUE),
                "minimum_emission_rate": minimum_rate,
                "minimum_emission": contribution,
            })
        if contributors and implied > cap + tol:
            contributors.sort(key=lambda item: float(item["minimum_emission"]), reverse=True)
            findings.append(StructuralFinding(
                code="ANNUAL_EMISSION_LIMIT_BELOW_MANDATED_MINIMUM",
                severity="ERROR",
                evidence_level="STRUCTURAL",
                message="El límite anual de emisión es menor que las emisiones mínimas inevitables de actividad obligatoria.",
                dimensions={"REGION": region, "EMISSION": emission, "YEAR": year},
                values={
                    "annual_emission_limit": cap,
                    "mandated_emission_lower_bound": implied,
                    "gap": implied - cap,
                    "mandatory_emitting_technologies": len(contributors),
                    "top_contributors": contributors[:10],
                },
                related_parameters=[
                    "AnnualEmissionLimit",
                    "TotalTechnologyAnnualActivityLowerLimit",
                    "EmissionActivityRatio",
                    "InputActivityRatio",
                    "OutputActivityRatio",
                ],
            ))
    return findings


def _detect_propagated_bound_conflicts(root: Path) -> list[StructuralFinding]:
    """Propaga cotas capacidad→actividad anual/horizonte sin resolver el LP."""
    inf, tol = 9_999_999.0, 1e-6
    years_frame = _read(root, "YEAR")
    if years_frame.empty:
        return []
    years = sorted(int(float(value)) for value in years_frame["VALUE"])
    residual = _lookup_values(_read(root, "ResidualCapacity"))
    max_invest = _lookup_values(_read(root, "TotalAnnualMaxCapacityInvestment"))
    max_capacity = _lookup_values(_read(root, "TotalAnnualMaxCapacity"))
    min_capacity = _lookup_values(_read(root, "TotalAnnualMinCapacity"))
    annual_min = _lookup_values(_read(root, "TotalTechnologyAnnualActivityLowerLimit"))
    annual_max = _lookup_values(_read(root, "TotalTechnologyAnnualActivityUpperLimit"))

    def two_dim(name: str) -> dict[tuple[str, str], float]:
        frame = _read(root, name)
        if frame.empty or not {"REGION", "TECHNOLOGY", "VALUE"}.issubset(frame.columns):
            return {}
        return {
            (str(row.REGION), str(row.TECHNOLOGY)): float(row.VALUE)
            for row in frame.itertuples(index=False)
        }

    life = two_dim("OperationalLife")
    c2a = two_dim("CapacityToActivityUnit")
    availability = _lookup_values(_read(root, "AvailabilityFactor"))
    capacity_factor = _read(root, "CapacityFactor")
    year_split = _read(root, "YearSplit")
    split = {
        (str(row.TIMESLICE), str(row.YEAR)): float(row.VALUE)
        for row in year_split.itertuples(index=False)
    } if {"TIMESLICE", "YEAR", "VALUE"}.issubset(year_split.columns) else {}
    cf = {
        (str(row.REGION), str(row.TECHNOLOGY), str(row.TIMESLICE), str(row.YEAR)): float(row.VALUE)
        for row in capacity_factor.itertuples(index=False)
    } if {"REGION", "TECHNOLOGY", "TIMESLICE", "YEAR", "VALUE"}.issubset(capacity_factor.columns) else {}
    timeslices: dict[str, list[str]] = {}
    for timeslice, year in split:
        timeslices.setdefault(year, []).append(timeslice)

    tech_years = set(residual) | set(max_invest) | set(max_capacity) | set(min_capacity) | set(annual_min) | set(annual_max)
    technologies = {(region, tech) for region, tech, _ in tech_years}
    cap_upper: dict[tuple[str, str, str], float] = {}
    activity_upper: dict[tuple[str, str, str], float] = {}
    findings: list[StructuralFinding] = []
    for region, tech in technologies:
        operational_life = life.get((region, tech), 1.0)
        for year in years:
            raw_year = str(year)
            investments = 0.0
            finite = True
            for investment_year in years:
                if investment_year > year or year - investment_year >= operational_life:
                    continue
                maximum = max_invest.get((region, tech, str(investment_year)), inf)
                if maximum >= inf:
                    finite = False
                    break
                investments += max(0.0, maximum)
            upper = max_capacity.get((region, tech, raw_year), inf)
            if finite:
                upper = min(upper, residual.get((region, tech, raw_year), 0.0) + investments)
            cap_upper[(region, tech, raw_year)] = upper
            minimum = min_capacity.get((region, tech, raw_year), 0.0)
            if upper < inf and minimum > upper + tol:
                findings.append(StructuralFinding(
                    code="MIN_TOTAL_CAPACITY_EXCEEDS_REALIZABLE_CAPACITY",
                    severity="ERROR", evidence_level="STRUCTURAL",
                    message="La capacidad total mínima supera residual más todas las inversiones máximas aún vivas.",
                    dimensions={"REGION": region, "TECHNOLOGY": tech, "YEAR": raw_year},
                    values={"required_capacity": minimum, "realizable_capacity_upper": upper, "gap": minimum - upper},
                    related_parameters=["TotalAnnualMinCapacity", "TotalAnnualMaxCapacity", "ResidualCapacity", "TotalAnnualMaxCapacityInvestment", "OperationalLife"],
                ))
            annual_factor = sum(
                split[(ts, raw_year)] * cf.get((region, tech, ts, raw_year), 1.0)
                for ts in timeslices.get(raw_year, [])
            )
            physical = upper * c2a.get((region, tech), 1.0)
            physical *= availability.get((region, tech, raw_year), 1.0) * annual_factor
            activity_upper[(region, tech, raw_year)] = min(
                physical, annual_max.get((region, tech, raw_year), inf)
            )

    horizon_lower = two_dim("TotalTechnologyModelPeriodActivityLowerLimit")
    horizon_upper = two_dim("TotalTechnologyModelPeriodActivityUpperLimit")
    for region, tech in technologies | set(horizon_lower) | set(horizon_upper):
        annual_required = sum(annual_min.get((region, tech, str(year)), 0.0) for year in years)
        maximum_horizon = horizon_upper.get((region, tech), inf)
        if maximum_horizon < inf and annual_required > maximum_horizon + tol:
            findings.append(StructuralFinding(
                code="SUM_ANNUAL_ACTIVITY_MIN_EXCEEDS_HORIZON_ACTIVITY_MAX",
                severity="ERROR", evidence_level="STRUCTURAL",
                message="La suma de mínimos anuales supera el máximo de actividad del horizonte.",
                dimensions={"REGION": region, "TECHNOLOGY": tech},
                values={"annual_minimum_sum": annual_required, "horizon_maximum": maximum_horizon, "gap": annual_required - maximum_horizon},
                related_parameters=["TotalTechnologyAnnualActivityLowerLimit", "TotalTechnologyModelPeriodActivityUpperLimit"],
            ))
        annual_uppers = [activity_upper.get((region, tech, str(year)), inf) for year in years]
        required_horizon = horizon_lower.get((region, tech), 0.0)
        if required_horizon > tol and all(value < inf for value in annual_uppers):
            cumulative_upper = sum(annual_uppers)
            if required_horizon > cumulative_upper + tol:
                findings.append(StructuralFinding(
                    code="HORIZON_ACTIVITY_MIN_EXCEEDS_CUMULATIVE_CAPACITY_ACTIVITY",
                    severity="ERROR", evidence_level="STRUCTURAL",
                    message="El mínimo del horizonte supera la actividad acumulada físicamente alcanzable.",
                    dimensions={"REGION": region, "TECHNOLOGY": tech},
                    values={"required_horizon_activity": required_horizon, "cumulative_activity_upper": cumulative_upper, "gap": required_horizon - cumulative_upper},
                    related_parameters=["TotalTechnologyModelPeriodActivityLowerLimit", "TotalTechnologyAnnualActivityUpperLimit", "ResidualCapacity", "TotalAnnualMaxCapacityInvestment", "OperationalLife", "CapacityFactor", "AvailabilityFactor", "CapacityToActivityUnit", "YearSplit"],
                ))
    return findings


def analyze_structural_infeasibility(csv_dir: str | Path) -> list[StructuralFinding]:
    """Devuelve hallazgos estructurales sin modificar ningún CSV."""
    root = Path(csv_dir)
    findings: list[StructuralFinding] = []

    from app.simulation.core.data_validation import detect_bound_conflicts

    for conflict in detect_bound_conflicts(root):
        findings.append(
            StructuralFinding(
                code="PARAMETER_BOUND_CONFLICT",
                severity="ERROR",
                evidence_level="STRUCTURAL",
                message=(
                    f"{conflict.lower} es mayor que {conflict.upper} para "
                    "las mismas dimensiones."
                ),
                dimensions={key: str(value) for key, value in conflict.key.items()},
                values={
                    "lower_parameter": conflict.lower,
                    "upper_parameter": conflict.upper,
                    "lower_value": conflict.value_lower,
                    "upper_value": conflict.value_upper,
                    "gap": conflict.gap,
                    "severity": conflict.severity,
                },
                related_parameters=[conflict.lower, conflict.upper],
            )
        )

    findings.extend(_detect_activity_minimum_capacity_conflicts(root))
    findings.extend(_detect_mandated_emission_limit_conflicts(root))
    findings.extend(_detect_propagated_bound_conflicts(root))

    demands = _positive_demand_keys(root)
    findings.extend(_detect_fuel_reachability(root, demands))
    producers = _producer_rows(root)
    producers_by_demand_key = {
        (str(region), str(fuel), str(year)): group
        for (region, fuel, year), group in producers.groupby(["REGION", "FUEL", "YEAR"])
    }
    max_capacity, availability, all_cf_zero = _blocked_reason_maps(root)
    capacity_context = _capacity_context(root)
    residual_capacity = _lookup_values(_read(root, "ResidualCapacity"))
    for key in sorted(set(max_capacity) & set(residual_capacity)):
        if residual_capacity[key] <= max_capacity[key] + 1e-9:
            continue
        region, technology, year = key
        findings.append(
            StructuralFinding(
                code="RESIDUAL_CAPACITY_EXCEEDS_MAXIMUM",
                severity="ERROR",
                evidence_level="STRUCTURAL",
                message=(
                    "La capacidad residual por sí sola supera la capacidad total "
                    "máxima permitida."
                ),
                dimensions={
                    "REGION": region,
                    "TECHNOLOGY": technology,
                    "YEAR": year,
                },
                values={
                    "residual_capacity": residual_capacity[key],
                    "total_annual_max_capacity": max_capacity[key],
                    "gap": residual_capacity[key] - max_capacity[key],
                },
                related_parameters=[
                    "ResidualCapacity",
                    "TotalAnnualMaxCapacity",
                ],
            )
        )

    for (region, fuel, year), demand_values in sorted(demands.items()):
        candidates = producers_by_demand_key.get(
            (region, fuel, year), pd.DataFrame(columns=producers.columns)
        )
        dimensions = {"REGION": region, "FUEL": fuel, "YEAR": year}
        if candidates.empty:
            findings.append(
                StructuralFinding(
                    code="DEMAND_WITHOUT_LOCAL_PRODUCER",
                    severity="ERROR",
                    evidence_level="STRUCTURAL",
                    message=(
                        "Existe demanda positiva, pero ningún OutputActivityRatio "
                        "positivo produce localmente este fuel en el año."
                    ),
                    dimensions=dimensions,
                    values={"demand": demand_values},
                    related_parameters=[
                        "SpecifiedAnnualDemand",
                        "SpecifiedDemandProfile",
                        "AccumulatedAnnualDemand",
                        "OutputActivityRatio",
                    ],
                )
            )
            continue

        technologies = sorted(set(candidates["TECHNOLOGY"].astype(str)))
        reasons_by_technology: dict[str, list[str]] = {}
        for technology in technologies:
            key = (region, technology, year)
            reasons: list[str] = []
            # El default de TotalAnnualMaxCapacity es 9,999,999: sólo un valor
            # explícito <= 0 demuestra bloqueo por capacidad total.
            if key in max_capacity and max_capacity[key] <= 0:
                reasons.append("total_max_capacity_zero")
            if key in availability and availability[key] <= 0:
                reasons.append("availability_factor_zero")
            if all_cf_zero.get(key, False):
                reasons.append("all_capacity_factors_zero")
            if reasons:
                reasons_by_technology[technology] = reasons

        if technologies and len(reasons_by_technology) == len(technologies):
            findings.append(
                StructuralFinding(
                    code="DEMAND_WITH_ONLY_BLOCKED_PRODUCERS",
                    severity="ERROR",
                    evidence_level="STRUCTURAL",
                    message=(
                        "Todos los productores locales conocidos del fuel demandado "
                        "están bloqueados por límites/factores explícitos."
                    ),
                    dimensions=dimensions,
                    values={
                        "demand": demand_values,
                        "producer_technologies": technologies,
                        "blocking_reasons": reasons_by_technology,
                    },
                    related_parameters=[
                        "OutputActivityRatio",
                        "TotalAnnualMaxCapacity",
                        "AvailabilityFactor",
                        "CapacityFactor",
                    ],
                )
            )
            continue

        usable_reasons = {
            technology: _usable_capacity_reasons(
                capacity_context, region, technology, year
            )
            for technology in technologies
        }
        if technologies and all(usable_reasons.values()):
            findings.append(
                StructuralFinding(
                    code="DEMAND_WITHOUT_USABLE_CAPACITY_PATH",
                    severity="ERROR",
                    evidence_level="STRUCTURAL",
                    message=(
                        "La demanda tiene productores con OutputActivityRatio, pero "
                        "ninguno tiene capacidad residual o una inversión vigente "
                        "que pueda aportar actividad en ese año."
                    ),
                    dimensions=dimensions,
                    values={
                        "demand": demand_values,
                        "producer_technologies": technologies,
                        "blocking_reasons": usable_reasons,
                    },
                    related_parameters=[
                        "OutputActivityRatio",
                        "ResidualCapacity",
                        "TotalAnnualMaxCapacityInvestment",
                        "OperationalLife",
                        "TotalAnnualMaxCapacity",
                        "AvailabilityFactor",
                        "CapacityFactor",
                        "CapacityToActivityUnit",
                    ],
                )
            )

    min_storage_charge = _read(root, "MinStorageCharge")
    if not min_storage_charge.empty:
        invalid = min_storage_charge[
            (min_storage_charge["VALUE"] < 0) | (min_storage_charge["VALUE"] > 1)
        ]
        for row in invalid.itertuples(index=False):
            findings.append(
                StructuralFinding(
                    code="INVALID_MIN_STORAGE_CHARGE",
                    severity="ERROR",
                    evidence_level="STRUCTURAL",
                    message="MinStorageCharge debe estar entre 0 y 1.",
                    dimensions={
                        "REGION": str(row.REGION),
                        "STORAGE": str(row.STORAGE),
                        "YEAR": str(row.YEAR),
                    },
                    values={"value": float(row.VALUE)},
                    related_parameters=["MinStorageCharge"],
                )
            )

    for rate_name in ("StorageMaxChargeRate", "StorageMaxDischargeRate"):
        rates = _read(root, rate_name)
        if rates.empty:
            continue
        for row in rates[rates["VALUE"] < 0].itertuples(index=False):
            findings.append(
                StructuralFinding(
                    code="NEGATIVE_STORAGE_RATE_LIMIT",
                    severity="ERROR",
                    evidence_level="STRUCTURAL",
                    message=f"{rate_name} no puede ser negativo.",
                    dimensions={
                        "REGION": str(row.REGION),
                        "STORAGE": str(row.STORAGE),
                    },
                    values={"parameter": rate_name, "value": float(row.VALUE)},
                    related_parameters=[rate_name],
                )
            )

    trade = _read(root, "TradeRoute")
    if not trade.empty and {"REGION", "REGION2", "FUEL", "YEAR", "VALUE"}.issubset(trade.columns):
        active_trade = trade[(trade["VALUE"] > 0) & (trade["REGION"] != trade["REGION2"])]
        if not active_trade.empty:
            findings.append(
                StructuralFinding(
                    code="TRADE_ROUTE_NOT_MODELED",
                    severity="WARNING",
                    evidence_level="STRUCTURAL",
                    message=(
                        "Hay rutas interregionales positivas en TradeRoute.csv, pero "
                        "el modelo Pyomo actual no carga ni usa TradeRoute. La "
                        "transmisión declarada no puede cubrir demanda."
                    ),
                    values={"active_route_rows": int(len(active_trade))},
                    related_parameters=["TradeRoute"],
                )
            )

    return findings
