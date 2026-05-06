"""Importación de escenarios desde ZIP con CSV OSeMOSYS procesados."""

from __future__ import annotations

import csv
import shutil
import zipfile
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.models import (
    Dailytimebracket,
    Daytype,
    Emission,
    Fuel,
    ModeOfOperation,
    OsemosysParamValue,
    Region,
    Scenario,
    ScenarioPermission,
    Season,
    StorageSet,
    Technology,
    Timeslice,
    UdcSet,
    User,
)
from app.services.scenario_service import ScenarioService
from app.simulation.core.data_processing import PARAM_INDEX

_REQUIRED_SET_CSVS = (
    "YEAR.csv",
    "REGION.csv",
    "TECHNOLOGY.csv",
    "TIMESLICE.csv",
    "MODE_OF_OPERATION.csv",
)
_DEMAND_CSV_OPTIONS = ("SpecifiedAnnualDemand.csv", "AccumulatedAnnualDemand.csv")
_ACTIVITY_RATIO_CSV_OPTIONS = ("OutputActivityRatio.csv", "InputActivityRatio.csv")

_SET_MODELS: dict[str, tuple[type, str]] = {
    "REGION": (Region, "name"),
    "TECHNOLOGY": (Technology, "name"),
    "FUEL": (Fuel, "name"),
    "EMISSION": (Emission, "name"),
    "TIMESLICE": (Timeslice, "code"),
    "MODE_OF_OPERATION": (ModeOfOperation, "code"),
    "SEASON": (Season, "code"),
    "DAYTYPE": (Daytype, "code"),
    "DAILYTIMEBRACKET": (Dailytimebracket, "code"),
    "STORAGE": (StorageSet, "code"),
    "UDC": (UdcSet, "code"),
}

_DIMENSION_FIELD_MAP = {
    "REGION": "id_region",
    "TECHNOLOGY": "id_technology",
    "FUEL": "id_fuel",
    "EMISSION": "id_emission",
    "TIMESLICE": "id_timeslice",
    "MODE_OF_OPERATION": "id_mode_of_operation",
    "SEASON": "id_season",
    "DAYTYPE": "id_daytype",
    "DAILYTIMEBRACKET": "id_dailytimebracket",
    "STORAGE": "id_storage_set",
    "UDC": "id_udc_set",
}


def find_csv_root(extract_root: Path) -> Path | None:
    required = set(_REQUIRED_SET_CSVS)
    candidates = [extract_root, *[path for path in extract_root.rglob("*") if path.is_dir()]]
    for candidate in candidates:
        csv_names = {path.name for path in candidate.glob("*.csv")}
        if required.issubset(csv_names):
            return candidate
    return None


def validate_csv_root(csv_root: Path) -> list[str]:
    csv_names = {path.name for path in csv_root.glob("*.csv")}
    missing_sets = [name for name in _REQUIRED_SET_CSVS if name not in csv_names]
    errors: list[str] = []

    if missing_sets:
        errors.append("Faltan CSV base requeridos: " + ", ".join(missing_sets) + ".")

    if not any(name in csv_names for name in _DEMAND_CSV_OPTIONS):
        errors.append(
            "Falta al menos un CSV de demanda: " + " o ".join(_DEMAND_CSV_OPTIONS) + "."
        )

    if not any(name in csv_names for name in _ACTIVITY_RATIO_CSV_OPTIONS):
        errors.append(
            "Falta al menos un CSV de activity ratio: " + " o ".join(_ACTIVITY_RATIO_CSV_OPTIONS) + "."
        )

    param_csv_names = {f"{param_name}.csv" for param_name in PARAM_INDEX}
    if not any(name in csv_names for name in param_csv_names):
        errors.append("No se encontraron CSV de parámetros OSeMOSYS reconocidos.")

    return errors


def extract_zip_to_dir(upload: UploadFile, target_dir: Path) -> None:
    try:
        with zipfile.ZipFile(upload.file) as zf:
            for member in zf.infolist():
                member_path = Path(member.filename)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise ConflictError("El ZIP contiene rutas no válidas.")
                if member.is_dir():
                    continue
                out_path = target_dir / member_path
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, out_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
    except zipfile.BadZipFile as exc:
        raise ConflictError("El archivo cargado no es un ZIP válido.") from exc


class CsvScenarioImportService:
    """Convierte un directorio CSV procesado en un escenario persistido."""

    @staticmethod
    def _normalize_row(row: dict[str, str | None]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for raw_key, raw_value in row.items():
            key = str(raw_key or "").strip().upper().replace("\ufeff", "")
            if not key:
                continue
            normalized[key] = str(raw_value or "").strip()
        return normalized

    @staticmethod
    def _iter_csv_rows(path: Path) -> list[dict[str, str]]:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            return [CsvScenarioImportService._normalize_row(row) for row in reader]

    @staticmethod
    def _iter_set_values(path: Path) -> list[str]:
        rows = CsvScenarioImportService._iter_csv_rows(path)
        values: list[str] = []
        for row in rows:
            raw = row.get("VALUE")
            if raw is None and row:
                raw = next(iter(row.values()))
            clean = str(raw or "").strip()
            if clean:
                values.append(clean)
        return values

    @staticmethod
    def _resolve_catalog_value(
        db: Session,
        *,
        dim_name: str,
        raw_value: str | None,
        lookups: dict[str, dict[str, int]],
    ) -> int | None:
        clean = str(raw_value or "").strip()
        if not clean:
            return None

        dim_lookup = lookups.setdefault(dim_name, {})
        existing = dim_lookup.get(clean)
        if existing is not None:
            return existing

        model, key_attr = _SET_MODELS[dim_name]
        if key_attr == "name":
            resolved = ScenarioService._resolve_or_create_catalog_name(
                db, model=model, name=clean, label=dim_name
            )
        else:
            resolved = ScenarioService._resolve_or_create_catalog_code(
                db, model=model, code=clean, label=dim_name
            )
        if resolved is None:
            return None
        dim_lookup[clean] = resolved
        return resolved

    @staticmethod
    def _load_catalog_sets(db: Session, *, csv_root: Path) -> dict[str, dict[str, int]]:
        lookups: dict[str, dict[str, int]] = {}
        for set_name, (model, key_attr) in _SET_MODELS.items():
            csv_path = csv_root / f"{set_name}.csv"
            if not csv_path.exists():
                continue
            lookups[set_name] = {}
            for value in CsvScenarioImportService._iter_set_values(csv_path):
                if key_attr == "name":
                    resolved = ScenarioService._resolve_or_create_catalog_name(
                        db, model=model, name=value, label=set_name
                    )
                else:
                    resolved = ScenarioService._resolve_or_create_catalog_code(
                        db, model=model, code=value, label=set_name
                    )
                if resolved is not None:
                    lookups[set_name][value] = resolved
        return lookups

    @staticmethod
    def _parse_year(raw_value: str | None) -> int | None:
        clean = str(raw_value or "").strip()
        if not clean:
            return None
        try:
            return int(float(clean))
        except ValueError as exc:
            raise ConflictError(f"Año inválido en CSV: {clean}") from exc

    @staticmethod
    def _parse_value(raw_value: str | None, *, param_name: str) -> float:
        clean = str(raw_value or "").strip()
        if not clean:
            raise ConflictError(f"El CSV {param_name}.csv tiene una fila sin VALUE.")
        try:
            return float(clean)
        except ValueError as exc:
            raise ConflictError(f"VALUE inválido en {param_name}.csv: {clean}") from exc

    @staticmethod
    def _read_param_rows(
        db: Session,
        *,
        csv_root: Path,
        scenario_id: int,
        lookups: dict[str, dict[str, int]],
    ) -> list[OsemosysParamValue]:
        dedup: dict[tuple, OsemosysParamValue] = {}

        for param_name, dimensions in sorted(PARAM_INDEX.items()):
            csv_path = csv_root / f"{param_name}.csv"
            if not csv_path.exists():
                continue
            ScenarioService._ensure_parameter_exists(db, param_name=param_name)
            for row in CsvScenarioImportService._iter_csv_rows(csv_path):
                value = CsvScenarioImportService._parse_value(row.get("VALUE"), param_name=param_name)
                payload = {
                    "id_scenario": scenario_id,
                    "param_name": param_name,
                    "id_region": None,
                    "id_technology": None,
                    "id_fuel": None,
                    "id_emission": None,
                    "id_timeslice": None,
                    "id_mode_of_operation": None,
                    "id_season": None,
                    "id_daytype": None,
                    "id_dailytimebracket": None,
                    "id_storage_set": None,
                    "id_udc_set": None,
                    "year": None,
                    "value": value,
                }

                for dimension in dimensions:
                    if dimension == "YEAR":
                        payload["year"] = CsvScenarioImportService._parse_year(row.get("YEAR"))
                        continue
                    field_name = _DIMENSION_FIELD_MAP.get(dimension)
                    if field_name is None:
                        continue
                    payload[field_name] = CsvScenarioImportService._resolve_catalog_value(
                        db,
                        dim_name=dimension,
                        raw_value=row.get(dimension),
                        lookups=lookups,
                    )

                dedup_key = (
                    payload["param_name"],
                    payload["id_region"],
                    payload["id_technology"],
                    payload["id_fuel"],
                    payload["id_emission"],
                    payload["id_timeslice"],
                    payload["id_mode_of_operation"],
                    payload["id_season"],
                    payload["id_daytype"],
                    payload["id_dailytimebracket"],
                    payload["id_storage_set"],
                    payload["id_udc_set"],
                    payload["year"],
                )
                dedup[dedup_key] = OsemosysParamValue(**payload)

        return list(dedup.values())

    @staticmethod
    def _cleanup_failed_scenario(db: Session, *, scenario_id: int) -> None:
        db.query(OsemosysParamValue).filter(OsemosysParamValue.id_scenario == scenario_id).delete()
        db.query(ScenarioPermission).filter(ScenarioPermission.id_scenario == scenario_id).delete()
        scenario = db.get(Scenario, scenario_id)
        if scenario is not None:
            db.delete(scenario)
        db.commit()

    @staticmethod
    def import_from_directory(
        db: Session,
        *,
        current_user: User,
        csv_root: Path,
        scenario_name: str,
        description: str | None,
        edit_policy: str,
        simulation_type: str,
        tag_ids: list[int] | None = None,
    ) -> dict:
        validation_errors = validate_csv_root(csv_root)
        if validation_errors:
            raise ConflictError(" ".join(validation_errors))

        created = ScenarioService.create(
            db,
            current_user=current_user,
            name=scenario_name.strip(),
            description=(description.strip() if description else None),
            edit_policy=edit_policy,
            is_template=False,
            simulation_type=simulation_type,
            processing_mode="PREPROCESSED_CSV",
            skip_populate_defaults=True,
            tag_ids=tag_ids or [],
        )
        scenario_id = int(created["id"])

        try:
            lookups = CsvScenarioImportService._load_catalog_sets(db, csv_root=csv_root)
            rows = CsvScenarioImportService._read_param_rows(
                db,
                csv_root=csv_root,
                scenario_id=scenario_id,
                lookups=lookups,
            )
            for start in range(0, len(rows), 5000):
                db.add_all(rows[start:start + 5000])
                db.flush()
            ScenarioService.sync_catalogs_from_scenario_values(db, scenario_id=scenario_id)
            db.commit()
        except Exception:
            db.rollback()
            CsvScenarioImportService._cleanup_failed_scenario(db, scenario_id=scenario_id)
            raise

        # Validación de calidad de datos post-import: detecta bound conflicts
        # y dead years, aplica la exclusión de años muertos y persiste los
        # warnings en scenario.data_quality_warnings.
        try:
            from app.simulation.core import data_validation as dv
            dv.validate_and_persist(
                db,
                scenario_id=scenario_id,
                detected_during="import",
                apply_dead_years=True,
            )
        except Exception:  # pragma: no cover - defensive
            db.rollback()
            import logging
            logging.getLogger(__name__).warning(
                "data_validation post-import (CSV) fallo", exc_info=True,
            )

        return ScenarioService.get_public(db, scenario_id=scenario_id, current_user=current_user)
