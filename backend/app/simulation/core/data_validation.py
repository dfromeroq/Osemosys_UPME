"""Detección y manejo de conflictos de calidad de datos en CSVs OSeMOSYS.

Centraliza la lógica que antes vivía dispersa entre `data_processing.py`
(reconciliación silenciosa de bounds, exclusión de dead_years) y permite
que los 3 modos de entrada (Excel, CSV-dir, BD) emitan los mismos warnings
y apliquen las mismas correcciones.

Reglas:

- **Bound conflicts** (`Min > Max` en pares lower/upper):
  - Severidad ``numeric_precision`` si ``gap < NUMERIC_PRECISION_TOL`` (1e-4).
  - Severidad ``real_conflict`` en otro caso.
  - **Nunca se corrige silenciosamente.** Sólo se reporta. Para corregir,
    llamar explícitamente ``apply_bound_fix_numeric_precision`` (auto-fix
    sólo de los ``numeric_precision``: el ``lower`` toma el valor del
    ``upper`` — i.e. se mantiene el mayor de los dos).

- **Dead years** (años inactivos):
  - Un año se considera dead si TODOS sus timeslices tienen ``YearSplit=0``.
  - Permite al modelador acortar el horizonte desde los datos.
  - Se aplica automáticamente en todos los modos vía
    ``apply_dead_year_exclusion``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


# Tolerancia para clasificar un gap como "precisión decimal" (vs conflicto real).
# Configurada para gap absoluto < 1e-4 (dato real ≪ 1e-4 sería sospechoso de
# error de captura; precision flotante de DOUBLE PRECISION suele ser ≪ 1e-9).
NUMERIC_PRECISION_TOL: float = 1e-4


# Pares (lower, upper) con el mismo índice. Si se agregan nuevos pares al
# modelo OSeMOSYS, registrarlos aquí.
BOUND_PAIRS: tuple[tuple[str, str], ...] = (
    (
        "TotalTechnologyAnnualActivityLowerLimit",
        "TotalTechnologyAnnualActivityUpperLimit",
    ),
    ("TotalAnnualMinCapacity", "TotalAnnualMaxCapacity"),
    (
        "TotalAnnualMinCapacityInvestment",
        "TotalAnnualMaxCapacityInvestment",
    ),
)


# ====================================================================
#  Estructuras de datos
# ====================================================================

@dataclass
class BoundConflict:
    """Una tupla `(lower, upper, key)` donde `value_lower > value_upper`."""

    lower: str
    upper: str
    key: dict[str, object]
    value_lower: float
    value_upper: float
    gap: float
    severity: str  # "numeric_precision" | "real_conflict"

    def to_dict(self) -> dict:
        return {
            "lower": self.lower,
            "upper": self.upper,
            "key": self.key,
            "value_lower": self.value_lower,
            "value_upper": self.value_upper,
            "gap": self.gap,
            "severity": self.severity,
        }


@dataclass
class YearExclusion:
    """Año excluido del horizonte porque TODOS sus YearSplit son 0."""

    year: int
    reason: str  # "YearSplit_all_zero"
    n_timeslices_zero: int
    n_timeslices_total: int

    def to_dict(self) -> dict:
        return {
            "year": self.year,
            "reason": self.reason,
            "n_timeslices_zero": self.n_timeslices_zero,
            "n_timeslices_total": self.n_timeslices_total,
        }


@dataclass
class DataQualityReport:
    """Reporte agregado de calidad de datos producido durante el procesamiento."""

    bound_conflicts: list[BoundConflict] = field(default_factory=list)
    year_exclusions: list[YearExclusion] = field(default_factory=list)
    detected_at: str = ""
    detected_during: str = ""  # "excel" | "csv" | "db" | "import" | "manual"

    def has_warnings(self) -> bool:
        return bool(self.bound_conflicts or self.year_exclusions)

    def n_real_conflicts(self) -> int:
        return sum(1 for c in self.bound_conflicts if c.severity == "real_conflict")

    def n_numeric_precision(self) -> int:
        return sum(
            1 for c in self.bound_conflicts if c.severity == "numeric_precision"
        )

    def to_dict(self) -> dict:
        return {
            "bound_conflicts": [c.to_dict() for c in self.bound_conflicts],
            "year_exclusions": [y.to_dict() for y in self.year_exclusions],
            "detected_at": self.detected_at,
            "detected_during": self.detected_during,
            "summary": {
                "n_bound_conflicts": len(self.bound_conflicts),
                "n_bound_real_conflict": self.n_real_conflicts(),
                "n_bound_numeric_precision": self.n_numeric_precision(),
                "n_year_exclusions": len(self.year_exclusions),
            },
        }

    @classmethod
    def from_dict(cls, d: dict | None) -> "DataQualityReport":
        if not d:
            return cls()
        return cls(
            bound_conflicts=[
                BoundConflict(**c) for c in d.get("bound_conflicts", [])
            ],
            year_exclusions=[
                YearExclusion(**y) for y in d.get("year_exclusions", [])
            ],
            detected_at=d.get("detected_at", ""),
            detected_during=d.get("detected_during", ""),
        )


# ====================================================================
#  Detección
# ====================================================================

def _classify_severity(
    gap: float, *, tol: float = NUMERIC_PRECISION_TOL
) -> str:
    return "numeric_precision" if abs(gap) < tol else "real_conflict"


def detect_bound_conflicts(
    csv_dir: str | Path, *, tol: float = NUMERIC_PRECISION_TOL
) -> list[BoundConflict]:
    """Detecta tuplas donde `lower > upper` en cada par registrado en BOUND_PAIRS.

    Lee directamente los CSVs (mismo formato producido por Excel/CSV/BD).
    No modifica nada.
    """
    csv_dir = Path(csv_dir)
    conflicts: list[BoundConflict] = []
    for lower_name, upper_name in BOUND_PAIRS:
        lp = csv_dir / f"{lower_name}.csv"
        up = csv_dir / f"{upper_name}.csv"
        if not (lp.exists() and up.exists()):
            continue
        df_l = pd.read_csv(lp)
        df_u = pd.read_csv(up)
        if df_l.empty or df_u.empty:
            continue
        if "VALUE" not in df_l.columns or "VALUE" not in df_u.columns:
            continue
        # Las dimensiones (claves) son todas las columnas excepto VALUE.
        key_cols = [c for c in df_l.columns if c != "VALUE"]
        # Asegurar tipos consistentes en YEAR y otros enteros para el merge.
        for c in key_cols:
            if c == "YEAR":
                df_l[c] = pd.to_numeric(df_l[c], errors="coerce").astype("Int64")
                df_u[c] = pd.to_numeric(df_u[c], errors="coerce").astype("Int64")
            else:
                df_l[c] = df_l[c].astype(str)
                df_u[c] = df_u[c].astype(str)
        merged = df_l.merge(df_u, on=key_cols, suffixes=("_LOW", "_UPP"))
        violating = merged[merged["VALUE_LOW"] > merged["VALUE_UPP"]]
        for _, row in violating.iterrows():
            gap = float(row["VALUE_LOW"]) - float(row["VALUE_UPP"])
            key = {}
            for c in key_cols:
                v = row[c]
                # Convertir a tipos JSON-friendly
                if isinstance(v, (pd._libs.missing.NAType, type(None))):
                    key[c] = None
                elif hasattr(v, "item"):  # numpy scalars
                    key[c] = v.item()
                else:
                    key[c] = v
            conflicts.append(
                BoundConflict(
                    lower=lower_name,
                    upper=upper_name,
                    key=key,
                    value_lower=float(row["VALUE_LOW"]),
                    value_upper=float(row["VALUE_UPP"]),
                    gap=gap,
                    severity=_classify_severity(gap, tol=tol),
                )
            )
    return conflicts


def detect_dead_years(csv_dir: str | Path) -> list[YearExclusion]:
    """Detecta años cuya suma de YearSplit en TODOS los timeslices es 0.

    Sólo si TODOS los timeslices tienen YearSplit=0 el año se marca como dead.
    Si algunos son 0 pero no todos, NO se elimina (se respeta la voluntad del
    modelador de que ese año tenga al menos un timeslice activo).
    """
    csv_dir = Path(csv_dir)
    ys_path = csv_dir / "YearSplit.csv"
    if not ys_path.exists():
        return []
    df = pd.read_csv(ys_path)
    if df.empty:
        return []
    if "YEAR" not in df.columns or "VALUE" not in df.columns:
        return []

    df["VALUE"] = pd.to_numeric(df["VALUE"], errors="coerce").fillna(0.0)
    df["YEAR"] = pd.to_numeric(df["YEAR"], errors="coerce").astype("Int64")

    grp = df.groupby("YEAR").agg(
        n_total=("VALUE", "size"),
        n_zero=("VALUE", lambda v: int((v == 0.0).sum())),
    ).reset_index()

    exclusions: list[YearExclusion] = []
    for _, row in grp.iterrows():
        n_total = int(row["n_total"])
        n_zero = int(row["n_zero"])
        # Sólo si TODOS los timeslices son 0
        if n_total > 0 and n_zero == n_total:
            exclusions.append(
                YearExclusion(
                    year=int(row["YEAR"]),
                    reason="YearSplit_all_zero",
                    n_timeslices_zero=n_zero,
                    n_timeslices_total=n_total,
                )
            )
    return exclusions


def build_report(
    csv_dir: str | Path,
    *,
    detected_during: str,
    tol: float = NUMERIC_PRECISION_TOL,
) -> DataQualityReport:
    """Detección end-to-end. Devuelve el reporte sin aplicar fixes."""
    return DataQualityReport(
        bound_conflicts=detect_bound_conflicts(csv_dir, tol=tol),
        year_exclusions=detect_dead_years(csv_dir),
        detected_at=datetime.now(timezone.utc).isoformat(),
        detected_during=detected_during,
    )


# ====================================================================
#  Aplicación de correcciones
# ====================================================================

def apply_dead_year_exclusion(
    csv_dir: str | Path, exclusions: list[YearExclusion]
) -> int:
    """Elimina los años muertos del CSV YEAR.csv y de todos los CSVs que tengan
    columna YEAR.

    Esta operación SÍ se aplica automáticamente en los 3 modos (Excel/CSV/BD)
    para mantener consistencia: un año dead en YearSplit no debe permanecer en
    los demás parámetros.

    Returns
    -------
    int: número de archivos modificados.
    """
    if not exclusions:
        return 0
    csv_dir = Path(csv_dir)
    dead = {e.year for e in exclusions}

    n_modified = 0

    # 1. YEAR.csv
    year_csv = csv_dir / "YEAR.csv"
    if year_csv.exists():
        df = pd.read_csv(year_csv)
        if not df.empty and "VALUE" in df.columns:
            df["VALUE"] = pd.to_numeric(df["VALUE"], errors="coerce").astype("Int64")
            before = len(df)
            df = df[~df["VALUE"].isin(dead)]
            if len(df) < before:
                df.to_csv(year_csv, index=False)
                n_modified += 1

    # 2. Todos los CSVs (de parámetros o aux) que tengan columna YEAR
    for csv_path in csv_dir.glob("*.csv"):
        if csv_path.name == "YEAR.csv":
            continue
        try:
            # Sólo abrir el archivo si sospechamos que tiene YEAR
            head = pd.read_csv(csv_path, nrows=0)
        except Exception:
            continue
        if "YEAR" not in head.columns:
            continue
        df = pd.read_csv(csv_path)
        if df.empty or "YEAR" not in df.columns:
            continue
        df["YEAR"] = pd.to_numeric(df["YEAR"], errors="coerce").astype("Int64")
        before = len(df)
        df = df[~df["YEAR"].isin(dead)]
        if len(df) < before:
            df.to_csv(csv_path, index=False)
            n_modified += 1

    return n_modified


def apply_bound_fix_numeric_precision(
    csv_dir: str | Path, conflicts: list[BoundConflict]
) -> int:
    """Auto-fix sólo de los conflicts con severity='numeric_precision'.

    Estrategia: el ``lower`` toma el valor del ``upper`` (es decir, se mantiene
    el mayor de los dos valores). Conserva la cota superior intacta y sube el
    inferior al mismo nivel.

    NUNCA toca conflicts ``real_conflict`` — esos requieren intervención del
    usuario.

    Returns
    -------
    int: número de tuplas corregidas.
    """
    if not conflicts:
        return 0
    csv_dir = Path(csv_dir)
    fixable = [c for c in conflicts if c.severity == "numeric_precision"]
    if not fixable:
        return 0

    # Agrupar por archivo lower
    by_lower: dict[str, list[BoundConflict]] = {}
    for c in fixable:
        by_lower.setdefault(c.lower, []).append(c)

    n_fixed = 0
    for lower_name, group in by_lower.items():
        lp = csv_dir / f"{lower_name}.csv"
        if not lp.exists():
            continue
        df = pd.read_csv(lp)
        if df.empty or "VALUE" not in df.columns:
            continue
        # Preparar tipado para matching exacto
        for col in df.columns:
            if col == "YEAR":
                df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
            elif col != "VALUE":
                df[col] = df[col].astype(str)
        for c in group:
            mask = pd.Series([True] * len(df))
            for k, v in c.key.items():
                if k not in df.columns:
                    mask = pd.Series([False] * len(df))
                    break
                if k == "YEAR":
                    target = int(v) if v is not None else None
                    mask &= df[k] == target
                else:
                    mask &= df[k] == str(v)
            if mask.any():
                df.loc[mask, "VALUE"] = c.value_upper  # mantener el mayor
                n_fixed += int(mask.sum())
        df.to_csv(lp, index=False)
    return n_fixed


# ====================================================================
#  Helpers de logging / visualización
# ====================================================================

def log_report(report: DataQualityReport, *, source: str = "") -> None:
    """Imprime el reporte vía logger.warning con el detalle más relevante."""
    if not report.has_warnings():
        return
    suffix = f" [{source}]" if source else ""
    if report.bound_conflicts:
        logger.warning(
            "Bound conflicts detectados%s: %d total (%d real_conflict, %d numeric_precision)",
            suffix,
            len(report.bound_conflicts),
            report.n_real_conflicts(),
            report.n_numeric_precision(),
        )
        for c in report.bound_conflicts[:10]:
            logger.warning(
                "  %s vs %s key=%s lower=%s upper=%s gap=%.4e (%s)",
                c.lower, c.upper, c.key, c.value_lower, c.value_upper,
                c.gap, c.severity,
            )
    if report.year_exclusions:
        logger.warning(
            "Años excluidos del horizonte%s (todos los timeslices con YearSplit=0): %s",
            suffix,
            [e.year for e in report.year_exclusions],
        )


# ====================================================================
#  Operaciones BD-nativas (queries SQL directas, no requieren CSV)
# ====================================================================
#
#  Las funciones `*_db` operan sobre `osemosys.osemosys_param_value` y
#  `osemosys.scenario` directamente vía SQL. Son mucho más rápidas que el
#  flujo CSV porque evitan exportar todo el escenario a archivos sólo para
#  detectar/corregir conflictos.

def detect_bound_conflicts_db(
    db, scenario_id: int, *, tol: float = NUMERIC_PRECISION_TOL
) -> list[BoundConflict]:
    """Detecta tuplas con `lower > upper` para los pares en BOUND_PAIRS.

    Hace UN JOIN por par sobre osemosys_param_value, mucho más rápido que
    exportar CSVs y detectar después.
    """
    from sqlalchemy import text

    sql = text(
        """
        SELECT
          r.name AS region,
          t.name AS technology,
          l.year,
          l.value AS value_lower,
          u.value AS value_upper
        FROM osemosys.osemosys_param_value l
        JOIN osemosys.osemosys_param_value u
          ON u.id_scenario = l.id_scenario
         AND u.param_name = :upper_name
         AND u.id_region = l.id_region
         AND u.id_technology = l.id_technology
         AND u.year IS NOT DISTINCT FROM l.year
        JOIN osemosys.region r ON r.id = l.id_region
        JOIN osemosys.technology t ON t.id = l.id_technology
        WHERE l.id_scenario = :scenario_id
          AND l.param_name = :lower_name
          AND l.value > u.value
        """
    )
    out: list[BoundConflict] = []
    for lower_name, upper_name in BOUND_PAIRS:
        rows = db.execute(
            sql,
            {
                "scenario_id": scenario_id,
                "lower_name": lower_name,
                "upper_name": upper_name,
            },
        ).all()
        for r in rows:
            gap = float(r.value_lower) - float(r.value_upper)
            key = {"REGION": r.region, "TECHNOLOGY": r.technology}
            if r.year is not None:
                key["YEAR"] = int(r.year)
            out.append(
                BoundConflict(
                    lower=lower_name,
                    upper=upper_name,
                    key=key,
                    value_lower=float(r.value_lower),
                    value_upper=float(r.value_upper),
                    gap=gap,
                    severity=_classify_severity(gap, tol=tol),
                )
            )
    return out


def detect_dead_years_db(db, scenario_id: int) -> list[YearExclusion]:
    """Detecta años cuya suma de YearSplit en TODOS los timeslices es 0."""
    from sqlalchemy import text

    sql = text(
        """
        SELECT
          year,
          COUNT(*) AS n_total,
          SUM(CASE WHEN value = 0 THEN 1 ELSE 0 END) AS n_zero
        FROM osemosys.osemosys_param_value
        WHERE id_scenario = :scenario_id
          AND param_name = 'YearSplit'
          AND year IS NOT NULL
        GROUP BY year
        HAVING SUM(CASE WHEN value <> 0 THEN 1 ELSE 0 END) = 0
        ORDER BY year
        """
    )
    rows = db.execute(sql, {"scenario_id": scenario_id}).all()
    return [
        YearExclusion(
            year=int(r.year),
            reason="YearSplit_all_zero",
            n_timeslices_zero=int(r.n_zero),
            n_timeslices_total=int(r.n_total),
        )
        for r in rows
    ]


def build_report_db(
    db,
    scenario_id: int,
    *,
    detected_during: str,
    tol: float = NUMERIC_PRECISION_TOL,
) -> DataQualityReport:
    """Detección end-to-end leyendo directamente de BD."""
    return DataQualityReport(
        bound_conflicts=detect_bound_conflicts_db(db, scenario_id, tol=tol),
        year_exclusions=detect_dead_years_db(db, scenario_id),
        detected_at=datetime.now(timezone.utc).isoformat(),
        detected_during=detected_during,
    )


def apply_dead_year_exclusion_db(
    db, scenario_id: int, exclusions: list[YearExclusion]
) -> int:
    """Elimina todas las filas de osemosys_param_value para esos años.

    Retorna el número de filas afectadas.
    """
    if not exclusions:
        return 0
    from sqlalchemy import text

    years = [int(e.year) for e in exclusions]
    res = db.execute(
        text(
            """
            DELETE FROM osemosys.osemosys_param_value
            WHERE id_scenario = :scenario_id
              AND year = ANY(:years)
            """
        ),
        {"scenario_id": scenario_id, "years": years},
    )
    n = res.rowcount or 0
    logger.info(
        "apply_dead_year_exclusion_db: scenario=%s, years=%s, rows_deleted=%s",
        scenario_id, years, n,
    )
    return n


def apply_bound_fix_numeric_precision_db(
    db, scenario_id: int, conflicts: list[BoundConflict]
) -> int:
    """Auto-fix sólo de los conflicts numeric_precision: el lower toma el valor del upper.

    UPDATE directo sobre osemosys_param_value. Retorna número de filas afectadas.
    """
    if not conflicts:
        return 0
    fixable = [c for c in conflicts if c.severity == "numeric_precision"]
    if not fixable:
        return 0

    from sqlalchemy import text

    sql = text(
        """
        UPDATE osemosys.osemosys_param_value v
        SET value = :new_value
        FROM osemosys.region r, osemosys.technology t
        WHERE v.id_scenario = :scenario_id
          AND v.param_name = :lower_name
          AND v.id_region = r.id AND r.name = :region
          AND v.id_technology = t.id AND t.name = :technology
          AND v.year IS NOT DISTINCT FROM :year
        """
    )
    n_total = 0
    for c in fixable:
        params = {
            "scenario_id": scenario_id,
            "lower_name": c.lower,
            "region": c.key.get("REGION"),
            "technology": c.key.get("TECHNOLOGY"),
            "year": c.key.get("YEAR"),
            "new_value": float(c.value_upper),
        }
        res = db.execute(sql, params)
        n_total += res.rowcount or 0
    logger.info(
        "apply_bound_fix_numeric_precision_db: scenario=%s, n_fixed=%s",
        scenario_id, n_total,
    )
    return n_total


def persist_warnings(db, scenario_id: int, report: DataQualityReport) -> None:
    """Guarda el reporte en `scenario.data_quality_warnings` (UPDATE)."""
    from sqlalchemy import text
    import json

    db.execute(
        text(
            """
            UPDATE osemosys.scenario
            SET data_quality_warnings = CAST(:payload AS jsonb)
            WHERE id = :scenario_id
            """
        ),
        {
            "scenario_id": scenario_id,
            "payload": json.dumps(report.to_dict()),
        },
    )


def validate_and_persist(
    db,
    scenario_id: int,
    *,
    detected_during: str,
    apply_dead_years: bool = True,
    tol: float = NUMERIC_PRECISION_TOL,
) -> DataQualityReport:
    """End-to-end de validación para el flujo de import.

    1. Detecta conflicts y dead_years.
    2. Si `apply_dead_years` (default True): aplica DELETE en BD para esos años.
    3. Persiste el reporte en scenario.data_quality_warnings (preservando el
       histórico de year_exclusions).
    4. Hace `db.commit()`.

    Retorna el reporte tal como quedó persistido.
    """
    report = build_report_db(
        db, scenario_id, detected_during=detected_during, tol=tol
    )
    if apply_dead_years and report.year_exclusions:
        apply_dead_year_exclusion_db(db, scenario_id, report.year_exclusions)
    persist_warnings(db, scenario_id, report)
    db.commit()
    log_report(report, source=f"scenario={scenario_id}")
    return report


# ====================================================================
#  Helpers de visualización
# ====================================================================

def report_to_dataframes(
    report: DataQualityReport,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Convierte el reporte a 2 DataFrames legibles para inspección en notebook.

    Returns
    -------
    (df_bound_conflicts, df_year_exclusions)
    """
    bc_rows = []
    for c in report.bound_conflicts:
        row = {
            "lower": c.lower,
            "upper": c.upper,
            "value_lower": c.value_lower,
            "value_upper": c.value_upper,
            "gap": c.gap,
            "severity": c.severity,
        }
        for k, v in c.key.items():
            row[k] = v
        bc_rows.append(row)
    df_bc = pd.DataFrame(bc_rows)

    df_ye = pd.DataFrame([y.to_dict() for y in report.year_exclusions])
    return df_bc, df_ye
