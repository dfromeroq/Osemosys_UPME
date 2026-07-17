"""Orden canónico de los CSV que alimentan el modelo OSeMOSYS.

PostgreSQL no garantiza orden de filas y los IDs cambian al reimportar un
escenario. En un LP degenerado, un orden distinto de sets o coeficientes puede
hacer que el solver elija otra solución óptima. Este módulo elimina esa fuente
de variación sin cambiar valores ni la formulación matemática.
"""

from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Mapping, Sequence

import pandas as pd

logger = logging.getLogger(__name__)

SET_NAMES: tuple[str, ...] = (
    "YEAR",
    "REGION",
    "TECHNOLOGY",
    "FUEL",
    "EMISSION",
    "TIMESLICE",
    "MODE_OF_OPERATION",
    "STORAGE",
    "SEASON",
    "DAYTYPE",
    "DAILYTIMEBRACKET",
    "UDC",
)

_NATURAL_PART_RE = re.compile(r"(\d+(?:\.\d+)?)")
# PostgreSQL DOUBLE PRECISION y pandas pueden serializar el mismo valor de
# origen con diferencias de representación al pasar por DOUBLE PRECISION.
# Doce cifras significativas quedan muy por debajo de las tolerancias del
# modelo (1e-7) y garantizan el mismo LP para Excel y CSV/BD.
CANONICAL_VALUE_SIGNIFICANT_DIGITS = 12


def canonical_scalar_key(value: object) -> tuple:
    """Clave natural, estable y agnóstica del ID de catálogo."""
    if value is None or pd.isna(value):
        return (0, ())
    text = str(value).strip()
    if not text:
        return (0, ())

    parts: list[tuple[int, object]] = []
    for part in _NATURAL_PART_RE.split(text.casefold()):
        if not part:
            continue
        if _NATURAL_PART_RE.fullmatch(part):
            try:
                parts.append((0, float(part)))
                continue
            except ValueError:
                pass
        parts.append((1, part))
    # El texto original resuelve empates como 1, 1.0 o diferencias de case.
    return (1, tuple(parts), text)


def canonical_record_key(
    record: Mapping[str, object],
    dimensions: Sequence[str],
    *,
    include_value: bool = True,
) -> tuple:
    """Clave canónica de una fila de parámetro."""
    key = tuple(canonical_scalar_key(record.get(dim)) for dim in dimensions)
    if include_value:
        key += (canonical_scalar_key(record.get("VALUE")),)
    return key


def canonical_set_values(values: Sequence[object]) -> list[object]:
    """Elimina vacíos/duplicados y ordena un set de forma determinista."""
    unique: dict[str, object] = {}
    for value in values:
        if value is None or pd.isna(value):
            continue
        text = str(value).strip()
        if not text:
            continue
        unique.setdefault(text, value)
    return sorted(unique.values(), key=canonical_scalar_key)


def _canonicalize_numeric_values(df: pd.DataFrame) -> pd.DataFrame:
    """Cuantiza VALUE al nivel común de precisión Excel↔PostgreSQL."""
    if df.empty or "VALUE" not in df.columns:
        return df
    working = df.copy()
    numeric = pd.to_numeric(working["VALUE"], errors="coerce")
    mask = numeric.notna()
    if mask.any():
        working.loc[mask, "VALUE"] = numeric[mask].map(
            lambda value: float(
                format(float(value), f".{CANONICAL_VALUE_SIGNIFICANT_DIGITS}g")
            )
        )
    return working


def _sort_dataframe(df: pd.DataFrame, dimensions: Sequence[str]) -> pd.DataFrame:
    """Ordena con columnas de rango para no materializar dicts por cada fila."""
    if df.empty:
        return df

    working = df.copy()
    rank_columns: list[str] = []
    sort_columns = [*dimensions]
    if "VALUE" in working.columns:
        sort_columns.append("VALUE")

    for index, column in enumerate(sort_columns):
        # Los rangos se calculan sólo sobre valores únicos. Así una matriz de
        # millones de filas mantiene un costo de memoria cercano al de pandas.
        tokens = working[column].astype("string").str.strip().fillna("")
        ordered_tokens = sorted(tokens.unique().tolist(), key=canonical_scalar_key)
        ranks = {token: rank for rank, token in enumerate(ordered_tokens)}
        rank_column = f"__canonical_rank_{index}"
        working[rank_column] = tokens.map(ranks).astype("int64")
        rank_columns.append(rank_column)

    working = working.sort_values(rank_columns, kind="mergesort", na_position="first")
    return working.drop(columns=rank_columns).reset_index(drop=True)


def canonicalize_csv_directory(
    csv_dir: str | Path,
    param_index: Mapping[str, Sequence[str]],
) -> None:
    """Ordena sets y parámetros justo antes de construir la instancia Pyomo.

    Se conservan columnas y se normaliza VALUE a 12 cifras significativas para
    eliminar diferencias de un ULP entre Excel y PostgreSQL. Para parámetros,
    la clave es el orden de dimensiones declarado por OSeMOSYS y VALUE sólo
    actúa como desempate. El resultado no depende del origen ni del orden de
    inserción en PostgreSQL.
    """
    root = Path(csv_dir)

    for set_name in SET_NAMES:
        path = root / f"{set_name}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path)
        if "VALUE" not in df.columns:
            continue
        ordered = canonical_set_values(df["VALUE"].tolist())
        pd.DataFrame({"VALUE": ordered}).to_csv(path, index=False)

    ordered_files = 0
    for param_name, dimensions in sorted(param_index.items()):
        path = root / f"{param_name}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path)
        present_dimensions = [dim for dim in dimensions if dim in df.columns]
        if not present_dimensions:
            continue
        df = _canonicalize_numeric_values(df)
        sorted_df = _sort_dataframe(df, present_dimensions)
        sorted_df.to_csv(path, index=False)
        ordered_files += 1

    logger.info(
        "Orden canónico aplicado en %s (%d parámetros)", root, ordered_files
    )
