"""Benchmark aislado de HiGHS sobre un archivo .lp existente.

Replica el flujo del notebook (celda 7-8 en notebooks/pruebas.ipynb):
  Highs() -> readModel -> clearSolver -> resetOptions -> setOptionValue -> run()

Uso:
  python scripts/benchmark_highs_lp.py --lp path/to/model.lp --run-label local
  python scripts/benchmark_highs_lp.py --lp model.lp --log-file highs_bench.txt --json-out result.json

Variables de entorno registradas: OMP_NUM_THREADS, OPENBLAS_NUM_THREADS, MKL_NUM_THREADS.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

try:
    import highspy
except ImportError as exc:  # pragma: no cover
    print("highspy no instalado. Ejecuta desde el venv/backend o contenedor worker.", file=sys.stderr)
    raise SystemExit(1) from exc


@dataclass
class HighsPhaseTimings:
    read_model_seconds: float
    presolve_seconds: float | None
    simplex_seconds: float | None
    postsolve_seconds: float | None
    run_seconds: float
    total_seconds: float


@dataclass
class BenchmarkResult:
    run_label: str
    lp_path: str
    lp_size_mb: float
    highs_version: str
    model_status: str
    objective_value: float | None
    simplex_iterations: int | None
    highs_run_time_reported: float | None
    threads_option: object
    env_threads: dict[str, str | None]
    presolve_option: str | None
    timings: HighsPhaseTimings
    log_path: str | None
    phase_from_log: dict[str, float | None]


def _env_threads() -> dict[str, str | None]:
    keys = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    return {k: os.environ.get(k) for k in keys}


def _highs_version() -> str:
    try:
        h = highspy.Highs()
        info = h.version()
        if isinstance(info, str):
            return info
        if isinstance(info, (list, tuple)) and info:
            return str(info[0])
    except Exception:
        pass
    return "unknown"


def parse_highs_log(log_path: Path) -> dict[str, float | None]:
    """Extrae presolve / simplex / postsolve desde log HiGHS (timestamps acumulados)."""
    if not log_path.is_file():
        return {
            "presolve_seconds": None,
            "simplex_seconds": None,
            "postsolve_seconds": None,
            "highs_run_time_reported": None,
            "simplex_iterations": None,
            "lp_rows": None,
            "lp_cols": None,
        }

    text = log_path.read_text(encoding="utf-8", errors="replace")
    result: dict[str, float | None] = {
        "presolve_seconds": None,
        "simplex_seconds": None,
        "postsolve_seconds": None,
        "highs_run_time_reported": None,
        "simplex_iterations": None,
        "lp_rows": None,
        "lp_cols": None,
    }

    dim = re.search(r"LP (?:model )?has (\d+) rows; (\d+) cols", text)
    if dim:
        result["lp_rows"] = float(dim.group(1))
        result["lp_cols"] = float(dim.group(2))

    run_time = re.search(r"HiGHS run time\s*:\s*([\d.]+)", text)
    if run_time:
        result["highs_run_time_reported"] = float(run_time.group(1))

    iters = re.search(r"Simplex\s+iterations:\s*(\d+)", text)
    if iters:
        result["simplex_iterations"] = float(iters.group(1))

    # Primera iteración simplex tras "Solving the presolved LP"
    presolve_end: float | None = None
    simplex_end: float | None = None
    postsolve_start: float | None = None
    postsolve_end: float | None = None

    in_presolved_solve = False
    in_postsolve_solve = False
    for line in text.splitlines():
        if "Solving the presolved LP" in line:
            in_presolved_solve = True
            in_postsolve_solve = False
            continue
        if "Performed postsolve" in line:
            in_presolved_solve = False
            continue
        if "Solving the original LP from the solution after postsolve" in line:
            in_postsolve_solve = True
            continue

        ts = _extract_trailing_seconds(line)
        if ts is None:
            continue

        if in_presolved_solve and _is_simplex_data_line(line):
            if presolve_end is None and re.search(r"^\s+0\s+", line):
                presolve_end = ts
            elif presolve_end is not None:
                simplex_end = ts
        elif in_postsolve_solve and _is_simplex_data_line(line):
            if postsolve_start is None:
                postsolve_start = ts
            postsolve_end = ts

    if presolve_end is not None:
        result["presolve_seconds"] = presolve_end
    if presolve_end is not None and simplex_end is not None:
        result["simplex_seconds"] = max(0.0, simplex_end - presolve_end)
    if postsolve_start is not None and postsolve_end is not None:
        result["postsolve_seconds"] = max(0.0, postsolve_end - postsolve_start)
    elif postsolve_start is not None and run_time:
        total = float(run_time.group(1))
        if simplex_end is not None:
            result["postsolve_seconds"] = max(0.0, total - simplex_end)

    return result


def _is_simplex_data_line(line: str) -> bool:
    return bool(re.match(r"^\s+\d+\s+[\d.eE+-]+", line))


def _extract_trailing_seconds(line: str) -> float | None:
    m = re.search(r"([\d.]+)s\s*$", line.strip())
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def _last_timestamp(line: str) -> float | None:
    return _extract_trailing_seconds(line)


def run_benchmark(
    lp_path: Path,
    *,
    run_label: str,
    primal_tol: float,
    dual_tol: float,
    log_file: Path | None,
    enable_log: bool,
    presolve: str | None = None,
) -> BenchmarkResult:
    lp_path = lp_path.resolve()
    if not lp_path.is_file():
        raise FileNotFoundError(f"LP no encontrado: {lp_path}")

    lp_size_mb = lp_path.stat().st_size / (1024 * 1024)
    version = _highs_version()

    h = highspy.Highs()
    t_total = perf_counter()

    t_read = perf_counter()
    h.readModel(str(lp_path))
    read_seconds = perf_counter() - t_read

    h.clearSolver()
    h.resetOptions()

    if enable_log:
        h.setOptionValue("output_flag", True)
        h.setOptionValue("log_to_console", True)
        if log_file is not None:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            h.setOptionValue("log_file", str(log_file))

    h.setOptionValue("primal_feasibility_tolerance", primal_tol)
    h.setOptionValue("dual_feasibility_tolerance", dual_tol)
    if presolve:
        h.setOptionValue("presolve", presolve)

    t_run = perf_counter()
    h.run()
    run_seconds = perf_counter() - t_run
    total_seconds = perf_counter() - t_total

    status = str(h.getModelStatus())
    objective: float | None
    try:
        objective = float(h.getObjectiveValue())
    except Exception:
        objective = None

    raw_threads = h.getOptionValue("threads")
    threads_option = _json_safe(raw_threads)

    phase_from_log = parse_highs_log(log_file) if log_file else parse_highs_log(Path("__missing__"))

    timings = HighsPhaseTimings(
        read_model_seconds=read_seconds,
        presolve_seconds=phase_from_log.get("presolve_seconds"),
        simplex_seconds=phase_from_log.get("simplex_seconds"),
        postsolve_seconds=phase_from_log.get("postsolve_seconds"),
        run_seconds=run_seconds,
        total_seconds=total_seconds,
    )

    return BenchmarkResult(
        run_label=run_label,
        lp_path=str(lp_path),
        lp_size_mb=round(lp_size_mb, 2),
        highs_version=version,
        model_status=status,
        objective_value=objective,
        simplex_iterations=(
            int(phase_from_log["simplex_iterations"])
            if phase_from_log.get("simplex_iterations") is not None
            else None
        ),
        highs_run_time_reported=phase_from_log.get("highs_run_time_reported"),
        threads_option=threads_option,
        env_threads=_env_threads(),
        presolve_option=presolve,
        timings=timings,
        log_path=str(log_file) if log_file else None,
        phase_from_log=phase_from_log,
    )


def _print_result(result: BenchmarkResult) -> None:
    t = result.timings
    print(f"=== Benchmark HiGHS [{result.run_label}] ===")
    print(f"LP: {result.lp_path} ({result.lp_size_mb} MB)")
    print(f"HiGHS version: {result.highs_version}")
    print(f"Status: {result.model_status}")
    print(f"Objective: {result.objective_value}")
    print(f"Threads option: {result.threads_option}")
    print(f"Env threads: {result.env_threads}")
    if result.presolve_option:
        print(f"Presolve option: {result.presolve_option}")
    print(f"readModel: {t.read_model_seconds:.2f} s")
    print(f"h.run():   {t.run_seconds:.2f} s")
    print(f"Total:     {t.total_seconds:.2f} s")
    if result.highs_run_time_reported is not None:
        print(f"HiGHS run time (log): {result.highs_run_time_reported:.2f} s")
    if result.simplex_iterations is not None:
        print(f"Simplex iterations: {result.simplex_iterations}")
    if t.presolve_seconds is not None:
        print(f"Presolve (log):  {t.presolve_seconds:.2f} s")
    if t.simplex_seconds is not None:
        print(f"Simplex (log):   {t.simplex_seconds:.2f} s")
    if t.postsolve_seconds is not None:
        print(f"Postsolve (log): {t.postsolve_seconds:.2f} s")
    if result.log_path:
        print(f"Log: {result.log_path}")


def _json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "name"):
        return str(value.name)
    return value


def result_to_dict(result: BenchmarkResult) -> dict:
    return _json_safe(asdict(result))


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark HiGHS sobre un .lp (flujo notebook)")
    parser.add_argument("--lp", required=True, type=Path, help="Ruta al archivo .lp")
    parser.add_argument("--run-label", default="default", help="Etiqueta del run (local/docker/omp1)")
    parser.add_argument("--primal-tol", type=float, default=1e-5)
    parser.add_argument("--dual-tol", type=float, default=1e-5)
    parser.add_argument(
        "--presolve",
        choices=("on", "off", "choose"),
        default=None,
        help="Opción HiGHS presolve (default: choose/on automático de HiGHS)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Ruta del log HiGHS (default: tmp/benchmark_logs/<run-label>.txt)",
    )
    parser.add_argument("--no-log", action="store_true", help="No escribir log HiGHS")
    parser.add_argument("--json-out", type=Path, default=None, help="Guardar resultado JSON")
    args = parser.parse_args()

    log_file = None if args.no_log else args.log_file
    if log_file is None and not args.no_log:
        log_file = Path("tmp/benchmark_logs") / f"{args.run_label}.txt"

    result = run_benchmark(
        args.lp,
        run_label=args.run_label,
        primal_tol=args.primal_tol,
        dual_tol=args.dual_tol,
        log_file=log_file,
        enable_log=not args.no_log,
        presolve=args.presolve,
    )
    _print_result(result)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result_to_dict(result), indent=2), encoding="utf-8")
        print(f"JSON: {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
