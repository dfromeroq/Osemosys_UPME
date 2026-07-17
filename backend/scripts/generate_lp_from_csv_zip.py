"""Genera un .lp desde CSV.zip (mismo flujo regional del notebook)."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.simulation.core.data_processing import (  # noqa: E402
    apply_light_csv_preprocess,
    get_processing_result_from_csv_dir,
)
from app.simulation.core.instance_builder import build_instance  # noqa: E402
from app.simulation.core.model_definition import create_abstract_model  # noqa: E402
from app.simulation.core.solver import write_lp_file  # noqa: E402


def csv_dir_from_zip(csv_zip: Path, work_dir: Path) -> Path:
    csv_dir = work_dir / "csv"
    extract_to = work_dir / "_zip_extract"
    extract_to.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(csv_zip, "r") as zf:
        zf.extractall(extract_to)
    nested = extract_to / "CSV"
    if not nested.is_dir():
        raise FileNotFoundError(f"No se encontró carpeta CSV/ dentro de {csv_zip}")
    csv_dir.mkdir(parents=True, exist_ok=True)
    for item in nested.iterdir():
        shutil.move(str(item), str(csv_dir / item.name))
    shutil.rmtree(extract_to)
    return csv_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera model.lp desde CSV.zip")
    parser.add_argument(
        "--csv-zip",
        type=Path,
        default=PROJECT_ROOT.parent / "CSV.zip",
        help="Ruta a CSV.zip",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT_ROOT / "tmp" / "benchmark" / "model.lp",
        help="Ruta de salida del .lp",
    )
    args = parser.parse_args()

    if not args.csv_zip.is_file():
        print(f"CSV.zip no encontrado: {args.csv_zip}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="gen_lp_") as tmp:
        work = Path(tmp)
        csv_dir = csv_dir_from_zip(args.csv_zip, work)
        apply_light_csv_preprocess(str(csv_dir))
        proc = get_processing_result_from_csv_dir(str(csv_dir))
        print(f"has_storage={proc.has_storage} has_udc={proc.has_udc}")

        model = create_abstract_model(
            has_storage=proc.has_storage,
            has_udc=proc.has_udc,
        )
        t0 = perf_counter()
        instance = build_instance(
            model,
            str(csv_dir),
            has_storage=proc.has_storage,
            has_udc=proc.has_udc,
        )
        print(f"build_instance: {perf_counter() - t0:.1f} s")

        t1 = perf_counter()
        write_lp_file(instance, args.out)
        print(f"write_lp: {perf_counter() - t1:.1f} s")
        print(f"LP escrito: {args.out} ({args.out.stat().st_size / (1024*1024):.2f} MB)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
