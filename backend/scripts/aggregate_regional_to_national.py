"""Agrega resultados regionalizados a totales nacionales para comparación.

Lee el bundle de CSV producido por ``GET /visualizations/{job_id}/export-csv-bundle``
(o cualquier directorio con CSV en formato OSeMOSYS estándar) y reescribe cada
archivo sumando las filas que comparten dimensiones una vez removido el prefijo
regional de ``TECHNOLOGY`` y ``FUEL``.

Prefijos reconocidos
--------------------
Regionales (2 letras + ``_``)
    ``NE_``, ``AN_``, ``SO_``, ``OR_``, ``CA_``, ``IN_``, ``SE_``
        Se remueven antes de agrupar; ``NE_PWRCOA`` → ``PWRCOA``.

Transporte interregional
    Tecnologías ``TRN_*``, ``TRNELC_*``, ``TRNNGS_*``, ``TRNOIL_*`` representan
    flujos *entre* regiones. Por defecto se eliminan porque no existen en el
    modelo nacional. Con ``--include-transport`` se conservan colapsadas en
    una sola categoría (``TRN_INTER``, ``TRNELC_INTER`` …) y se suman.

Códigos sin prefijo regional (combustibles primarios, etc.) se mantienen
intactos.

Uso
---
    python aggregate_regional_to_national.py \\
        --input  /ruta/Resultados_CSV_*.zip \\
        --output /ruta/salida_nacional

    python aggregate_regional_to_national.py \\
        --input  /ruta/carpeta_csvs/ \\
        --output /ruta/salida_nacional \\
        --include-transport

Compara contra otro bundle nacional:

    python aggregate_regional_to_national.py \\
        --input regionalizado.zip \\
        --output aggr_nacional \\
        --compare-against /ruta/nacional_bundle/
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sys
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import TextIO

import pandas as pd

# Prefijos regionales codificados en TECHNOLOGY / FUEL.
REGION_PREFIXES: tuple[str, ...] = ("NE", "AN", "SO", "OR", "CA", "IN", "SE")

# Prefijos de tecnologías de transporte interregional (más largo primero para
# el regex — TRNELC/TRNNGS/TRNOIL son sub-tipos específicos de TRN).
TRANSPORT_PREFIXES: tuple[str, ...] = ("TRNELC", "TRNNGS", "TRNOIL", "TRN")

_REGION_RE = re.compile(r"^(" + "|".join(REGION_PREFIXES) + r")_(?P<rest>.+)$")
_TRANSPORT_RE = re.compile(r"^(" + "|".join(TRANSPORT_PREFIXES) + r")(_|$)")

# Dimensiones que pueden aparecer como columnas de código en los CSV.
CODE_COLUMNS: tuple[str, ...] = ("TECHNOLOGY", "FUEL")
# Columnas que NO se agrupan (numéricas / VALUE).
VALUE_COLUMN = "VALUE"


def strip_region_prefix(code: str) -> str:
    """Elimina el prefijo regional de un código si está presente."""
    if not code:
        return code
    m = _REGION_RE.match(code)
    if m is None:
        return code
    return m.group("rest")


def transport_group(code: str) -> str | None:
    """Si ``code`` es de transporte interregional, devuelve la categoría base.

    Ej: ``TRNELC_AN_NE`` → ``TRNELC_INTER``, ``TRN_CA_NE`` → ``TRN_INTER``,
    ``TRNOIL_OR_NE_3PES`` → ``TRNOIL_INTER_3PES`` (conserva sufijo no-regional).
    """
    m = _TRANSPORT_RE.match(code)
    if m is None:
        return None
    head = m.group(1)
    rest = code[len(head):].lstrip("_")
    # Tokens después del prefijo: descartar los que son prefijos regionales.
    tokens = [t for t in rest.split("_") if t]
    kept = [t for t in tokens if t not in REGION_PREFIXES]
    if kept:
        return f"{head}_INTER_" + "_".join(kept)
    return f"{head}_INTER"


def is_transport(code: str) -> bool:
    return _TRANSPORT_RE.match(code) is not None


def normalize_code(code: str, *, include_transport: bool) -> str | None:
    """Devuelve el código nacional o ``None`` si la fila debe descartarse."""
    if not isinstance(code, str) or not code:
        return code
    if is_transport(code):
        return transport_group(code) if include_transport else None
    return strip_region_prefix(code)


def _aggregate_df(
    df: pd.DataFrame, *, include_transport: bool
) -> tuple[pd.DataFrame, int, int]:
    """Normaliza códigos y agrupa sumando VALUE.

    Devuelve (df_resultado, filas_in, filas_dropped_por_transporte).
    """
    rows_in = len(df)
    if df.empty:
        return df, rows_in, 0

    # Identifica columnas de código presentes y normaliza.
    present_code_cols = [c for c in CODE_COLUMNS if c in df.columns]
    dropped = 0
    for col in present_code_cols:
        normalized = df[col].astype("string").map(
            lambda v, _it=include_transport: normalize_code(v, include_transport=_it)
        )
        mask_drop = normalized.isna() & df[col].notna()
        dropped += int(mask_drop.sum())
        df = df.loc[~mask_drop].copy()
        df[col] = normalized.loc[~mask_drop]

    if df.empty or VALUE_COLUMN not in df.columns:
        return df, rows_in, dropped

    # Agrupa por todas las dimensiones excepto VALUE.
    group_cols = [c for c in df.columns if c != VALUE_COLUMN]
    # to_numeric tolerante con strings.
    df[VALUE_COLUMN] = pd.to_numeric(df[VALUE_COLUMN], errors="coerce")
    df = df.dropna(subset=[VALUE_COLUMN])

    if not group_cols:
        out = pd.DataFrame({VALUE_COLUMN: [df[VALUE_COLUMN].sum()]})
    else:
        out = (
            df.groupby(group_cols, dropna=False, sort=False, as_index=False)[
                VALUE_COLUMN
            ]
            .sum()
        )
    return out, rows_in, dropped


def _iter_input_csvs(input_path: Path) -> Iterable[tuple[str, pd.DataFrame]]:
    """Itera (nombre_csv, dataframe) desde un ZIP o un directorio."""
    if input_path.is_dir():
        for csv_path in sorted(input_path.glob("*.csv")):
            yield csv_path.name, pd.read_csv(csv_path)
        return

    if input_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(input_path) as zf:
            members = sorted(
                m for m in zf.namelist() if m.lower().endswith(".csv") and not m.endswith("/")
            )
            for member in members:
                with zf.open(member) as fp:
                    name = Path(member).name
                    yield name, pd.read_csv(fp)
        return

    raise SystemExit(f"Entrada no reconocida: {input_path} (esperado .zip o directorio)")


def _write_csv(df: pd.DataFrame, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(target, index=False)


def _print_summary(rows: list[dict[str, int | str]], stream: TextIO) -> None:
    if not rows:
        return
    cols = ["file", "rows_in", "rows_out", "dropped_transport"]
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
    header = "  ".join(c.ljust(widths[c]) for c in cols)
    print(header, file=stream)
    print("  ".join("-" * widths[c] for c in cols), file=stream)
    for r in rows:
        print("  ".join(str(r[c]).ljust(widths[c]) for c in cols), file=stream)


def aggregate(
    input_path: Path,
    output_path: Path,
    *,
    include_transport: bool,
    skip_empty: bool = True,
) -> list[dict[str, int | str]]:
    """Procesa todos los CSV de ``input_path`` y los reescribe en ``output_path``.

    Devuelve un resumen por archivo (filas in/out, descartes de transporte).
    """
    summary: list[dict[str, int | str]] = []
    output_path.mkdir(parents=True, exist_ok=True)

    for name, df in _iter_input_csvs(input_path):
        agg, rows_in, dropped = _aggregate_df(df, include_transport=include_transport)
        rows_out = len(agg)
        if skip_empty and rows_out == 0:
            summary.append(
                dict(file=name, rows_in=rows_in, rows_out=0, dropped_transport=dropped)
            )
            continue
        _write_csv(agg, output_path / name)
        summary.append(
            dict(file=name, rows_in=rows_in, rows_out=rows_out, dropped_transport=dropped)
        )
    return summary


def compare_against(
    aggregated_dir: Path, national_input: Path
) -> list[dict[str, str | float]]:
    """Compara totales por (variable, año) entre la agregación y un bundle nacional."""
    differences: list[dict[str, str | float]] = []

    if not aggregated_dir.is_dir():
        raise SystemExit(f"Directorio agregado inválido: {aggregated_dir}")

    nat_files: dict[str, pd.DataFrame] = {}
    for name, df in _iter_input_csvs(national_input):
        nat_files[name] = df

    for csv_path in sorted(aggregated_dir.glob("*.csv")):
        name = csv_path.name
        if name not in nat_files:
            continue
        agg = pd.read_csv(csv_path)
        nat = nat_files[name]
        if VALUE_COLUMN not in agg.columns or VALUE_COLUMN not in nat.columns:
            continue
        agg_by_year = (
            agg.groupby("YEAR", as_index=False)[VALUE_COLUMN].sum()
            if "YEAR" in agg.columns
            else pd.DataFrame({"YEAR": ["TOTAL"], VALUE_COLUMN: [agg[VALUE_COLUMN].sum()]})
        )
        nat_by_year = (
            nat.groupby("YEAR", as_index=False)[VALUE_COLUMN].sum()
            if "YEAR" in nat.columns
            else pd.DataFrame({"YEAR": ["TOTAL"], VALUE_COLUMN: [nat[VALUE_COLUMN].sum()]})
        )
        merged = agg_by_year.merge(
            nat_by_year, on="YEAR", how="outer", suffixes=("_agg", "_nat")
        ).fillna(0)
        for _, row in merged.iterrows():
            a = float(row[f"{VALUE_COLUMN}_agg"])
            n = float(row[f"{VALUE_COLUMN}_nat"])
            diff = a - n
            pct = (diff / n * 100.0) if n else float("nan")
            differences.append(
                dict(
                    file=name,
                    year=row["YEAR"],
                    agg=a,
                    nat=n,
                    diff=diff,
                    pct=pct,
                )
            )
    return differences


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="ZIP exportado por la app o carpeta con CSVs en formato OSeMOSYS.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Directorio donde se escriben los CSV nacionales agregados.",
    )
    parser.add_argument(
        "--include-transport",
        action="store_true",
        help="Conserva tecnologías TRN* colapsadas en categorías '*_INTER' (por defecto se descartan).",
    )
    parser.add_argument(
        "--compare-against",
        type=Path,
        default=None,
        help="Opcional: ZIP o carpeta del bundle nacional para diff por (archivo, año).",
    )
    parser.add_argument(
        "--diff-output",
        type=Path,
        default=None,
        help="CSV de salida para el diff (default: <output>/_diff_vs_nacional.csv).",
    )
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"Entrada no encontrada: {args.input}", file=sys.stderr)
        return 2

    summary = aggregate(
        args.input,
        args.output,
        include_transport=args.include_transport,
    )
    print(f"\nAgregación → {args.output} ({len(summary)} archivos)\n")
    _print_summary(summary, sys.stdout)

    if args.compare_against is not None:
        if not args.compare_against.exists():
            print(f"\n--compare-against no encontrado: {args.compare_against}", file=sys.stderr)
            return 2
        diff_rows = compare_against(args.output, args.compare_against)
        diff_path = args.diff_output or (args.output / "_diff_vs_nacional.csv")
        pd.DataFrame(diff_rows).to_csv(diff_path, index=False)
        print(f"\nDiff por (archivo, año) → {diff_path} ({len(diff_rows)} filas)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
