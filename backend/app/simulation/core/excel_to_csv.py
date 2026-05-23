"""Generación de CSVs OSeMOSYS desde archivo Excel SAND (hoja Parameters).

Reutiliza la lógica del script compare_notebook_vs_app para no duplicar código.
Permite ejecutar el pipeline OSEMOSYS (build_instance → solve → results) sin BD,
pasando solo la ruta del Excel.
"""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_csvs_from_excel(
    excel_path: str | Path,
    csv_dir: str | Path,
    *,
    sheet_name: str = "Parameters",
    div: int = 1,
) -> None:
    """Genera CSVs de sets y parámetros desde un Excel SAND (misma lógica que el notebook).

    Requiere que exista el script compare_notebook_vs_app.py en backend/scripts/.
    Escribe en csv_dir los mismos archivos que run_data_processing (REGION.csv,
    TECHNOLOGY.csv, parámetros, etc.) para poder usar build_instance y el resto del pipeline.

    Parameters
    ----------
    excel_path : str | Path
        Ruta al archivo .xlsm o .xlsx (hoja tipo SAND Parameters).
    csv_dir : str | Path
        Directorio donde se escribirán los CSVs.
    sheet_name : str
        Nombre de la hoja (default "Parameters").
    div : int
        Divisor para muestreo de timeslices (default 1 = todos).
    """
    excel_path = Path(excel_path)
    csv_dir = Path(csv_dir)
    if not excel_path.is_file():
        raise FileNotFoundError(f"No existe el archivo Excel: {excel_path}")

    # Cargar el script compare_notebook_vs_app desde backend/scripts.
    # Layout: backend/app/simulation/core/excel_to_csv.py — subir 4 niveles
    # (parents[3]) para llegar a backend/.
    backend_root = Path(__file__).resolve().parents[3]
    script_path = backend_root / "scripts" / "compare_notebook_vs_app.py"
    if not script_path.is_file():
        raise FileNotFoundError(
            f"No se encontró compare_notebook_vs_app.py en {script_path}. "
            "Necesario para generar CSVs desde Excel."
        )

    spec = importlib.util.spec_from_file_location("compare_notebook_vs_app", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("No se pudo cargar el módulo compare_notebook_vs_app")

    module = importlib.util.module_from_spec(spec)
    # Asegurar que el script puede resolver PROJECT_ROOT y sus imports
    import sys
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    spec.loader.exec_module(module)

    generate_notebook_csvs = getattr(module, "generate_notebook_csvs", None)
    if generate_notebook_csvs is None:
        raise AttributeError("compare_notebook_vs_app no define generate_notebook_csvs")

    os.makedirs(csv_dir, exist_ok=True)
    path_csv = str(csv_dir) + os.sep
    logger.info("Generando CSVs desde Excel %s hacia %s", excel_path, csv_dir)
    generate_notebook_csvs(str(excel_path), path_csv, div=div)
