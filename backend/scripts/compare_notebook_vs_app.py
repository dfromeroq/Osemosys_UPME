"""Comparación standalone: genera CSVs con lógica del notebook y resuelve con la app.

NO requiere base de datos. Lee directamente el Excel SAND, genera CSVs
usando las funciones del notebook OPT_YA_20260220, y luego usa el
build_instance + solve_model de la app para verificar paridad.

Uso:
  python scripts/compare_notebook_vs_app.py
  python scripts/compare_notebook_vs_app.py --excel "C:/ruta/al/SAND.xlsm"
  python scripts/compare_notebook_vs_app.py --solver glpk
"""

from __future__ import annotations

import argparse
import itertools
import os
import sys
import tempfile
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_EXCEL = (
    r"C:\Users\SGI SAS\OneDrive - SGI SAS\Documentos\UPME\Codigo Notebook\SAND\SAND_04_02_2026_2.xlsm"
)

# ========================================================================
#  Funciones del notebook (celdas 6-15 de OPT_YA_20260220)
# ========================================================================


def SAND_to_CSV(df, param, path_csv, div):
    df_param = df[df["Parameter"] == param].dropna(axis=1)
    year = df_param.columns[df_param.columns.to_series().apply(pd.to_numeric, errors='coerce').notna()]
    sets = df_param.columns[~df_param.columns.isin(year) & (df_param.columns != 'Parameter')].tolist()

    if "Time indipendent variables" in sets:
        sets.remove("Time indipendent variables")
        df_TUPLES = df_param.drop(['Parameter'], axis=1).rename(columns={"Time indipendent variables": "VALUE"})
        df_param_indexed = pd.DataFrame()
    elif "TIMESLICE" in sets:
        df_param = df_param.reset_index(drop=True)
        df_param_sub = df_param[df_param.index % div == 0].reset_index(drop=True)
        df_param_sub = df_param_sub.set_index(sets).drop(columns='Parameter')

        if param == "CapacityFactor":
            df_param_sub = df_param_sub.reset_index()
            df_agg = df_param.drop(columns=['Parameter'] + sets)
            df_agg['index_col'] = df_agg.index // div
            df_agg = df_agg.groupby('index_col', as_index=False).mean()
            for y in year:
                df_param_sub[y] = df_agg[y]
            df_param_indexed = df_param_sub.set_index(sets)
            index_product = list(product(df_param_indexed.index, year))
            df_TUPLES = pd.DataFrame(index=index_product, columns=['VALUE'])
            for idx in df_TUPLES.index:
                df_TUPLES.at[idx, 'VALUE'] = df_param_indexed.at[idx[0], idx[1]]
            df_TUPLES.reset_index(inplace=True)
            df_TUPLES[['SETS', 'YEAR']] = pd.DataFrame(df_TUPLES['index'].tolist(), index=df_TUPLES.index)
            df_TUPLES[sets] = pd.DataFrame(df_TUPLES['SETS'].tolist(), index=df_TUPLES.index)
            df_TUPLES = df_TUPLES.drop(['index', 'SETS'], axis=1)
            df_TUPLES = df_TUPLES[sets + ['YEAR'] + ['VALUE']]
        else:
            df_param_sub = df_param_sub.loc[~(df_param_sub == 0).all(axis=1)].reset_index()
            df_agg = df_param.drop(columns=['Parameter'] + sets).loc[~(df_param.drop(columns=['Parameter'] + sets) == 0).all(axis=1)]
            df_agg['index_col'] = df_agg.index // div
            df_agg = df_agg.groupby('index_col', as_index=False).sum()
            for y in year:
                df_param_sub[y] = df_agg[y]
            df_param_indexed = df_param_sub.set_index(sets)
            index_product = list(product(df_param_indexed.index, year))
            df_TUPLES = pd.DataFrame(index=index_product, columns=['VALUE'])
            for idx in df_TUPLES.index:
                df_TUPLES.at[idx, 'VALUE'] = df_param_indexed.at[idx[0], idx[1]]
            df_TUPLES.reset_index(inplace=True)
            df_TUPLES[['SETS', 'YEAR']] = pd.DataFrame(df_TUPLES['index'].tolist(), index=df_TUPLES.index)
            df_TUPLES[sets] = pd.DataFrame(df_TUPLES['SETS'].tolist(), index=df_TUPLES.index)
            df_TUPLES = df_TUPLES.drop(['index', 'SETS'], axis=1)
            df_TUPLES = df_TUPLES[sets + ['YEAR'] + ['VALUE']]
    else:
        df_param_indexed = df_param.set_index(sets).drop(columns='Parameter')
        if df_param_indexed.empty:
            df_TUPLES = pd.DataFrame(columns=sets + ['YEAR', 'VALUE'])
        else:
            index_product = list(product(df_param_indexed.index, year))
            df_TUPLES = pd.DataFrame(index=index_product, columns=['VALUE'])
            for idx in df_TUPLES.index:
                df_TUPLES.at[idx, 'VALUE'] = df_param_indexed.at[idx[0], idx[1]]
            df_TUPLES.reset_index(inplace=True)
            df_TUPLES[['SETS', 'YEAR']] = pd.DataFrame(df_TUPLES['index'].tolist(), index=df_TUPLES.index)
            df_TUPLES[sets] = pd.DataFrame(df_TUPLES['SETS'].tolist(), index=df_TUPLES.index)
            df_TUPLES = df_TUPLES.drop(['index', 'SETS'], axis=1)
            df_TUPLES = df_TUPLES[sets + ['YEAR'] + ['VALUE']]
            df_TUPLES = df_TUPLES.dropna(axis=1)

    df_TUPLES.to_csv(os.path.join(path_csv, f"{param}.csv"), index=False)
    return df_param, df_param_indexed, year, df_TUPLES


def SAND_SETS_to_CSV(df, path_csv, div):
    df_param = df[df["Parameter"] == 'YearSplit'].dropna(axis=1).reset_index(drop=True)
    df_param = df_param[df_param.index % div == 0]
    year = df_param.columns[df_param.columns.to_series().apply(pd.to_numeric, errors='coerce').notna()]
    df_year = pd.DataFrame(year, columns=['VALUE'])
    sets = df_param.columns[~df_param.columns.isin(year) & (df_param.columns != 'Parameter')].tolist()

    for s in sets:
        df_set = pd.DataFrame(df_param[s].unique(), columns=['VALUE'])
        df_set.to_csv(os.path.join(path_csv, f"{s}.csv"), index=False)
    df_year.to_csv(os.path.join(path_csv, "YEAR.csv"), index=False)

    df_param = df[df["Parameter"] == 'EmissionActivityRatio'].dropna(axis=1)
    sets = df_param.columns[~df_param.columns.isin(year) & (df_param.columns != 'Parameter')].tolist()
    df_param_indexed = df_param.set_index(sets).drop(columns='Parameter').loc[~(df_param.set_index(sets).drop(columns='Parameter') == 0).all(axis=1)]

    if df_param_indexed.empty:
        df_TUPLES = pd.DataFrame(columns=sets + ['YEAR', 'VALUE'])
    else:
        index_product = list(product(df_param_indexed.index, year))
        df_TUPLES = pd.DataFrame(index=index_product, columns=['VALUE'])
        for idx in df_TUPLES.index:
            df_TUPLES.at[idx, 'VALUE'] = df_param_indexed.at[idx[0], idx[1]]
        df_TUPLES.reset_index(inplace=True)
        df_TUPLES[['SETS', 'YEAR']] = pd.DataFrame(df_TUPLES['index'].tolist(), index=df_TUPLES.index)
        df_TUPLES[sets] = pd.DataFrame(df_TUPLES['SETS'].tolist(), index=df_TUPLES.index)
        df_TUPLES = df_TUPLES.drop(['index', 'SETS'], axis=1)
        df_TUPLES = df_TUPLES[sets + ['YEAR'] + ['VALUE']]

    df_set = pd.DataFrame(df_TUPLES['EMISSION'].unique(), columns=['VALUE'])
    df_set.to_csv(os.path.join(path_csv, 'EMISSION.csv'), index=False)

    df_param = df[df["Parameter"] == 'OutputActivityRatio'].dropna(axis=1)
    sets = df_param.columns[~df_param.columns.isin(year) & (df_param.columns != 'Parameter')].tolist()
    df_param_indexed = df_param.set_index(sets).drop(columns='Parameter').loc[~(df_param.set_index(sets).drop(columns='Parameter') == 0).all(axis=1)]

    if df_param_indexed.empty:
        df_TUPLES = pd.DataFrame(columns=sets + ['YEAR', 'VALUE'])
    else:
        index_product = list(product(df_param_indexed.index, year))
        df_TUPLES = pd.DataFrame(index=index_product, columns=['VALUE'])
        for idx in df_TUPLES.index:
            df_TUPLES.at[idx, 'VALUE'] = df_param_indexed.at[idx[0], idx[1]]
        df_TUPLES.reset_index(inplace=True)
        df_TUPLES[['SETS', 'YEAR']] = pd.DataFrame(df_TUPLES['index'].tolist(), index=df_TUPLES.index)
        df_TUPLES[sets] = pd.DataFrame(df_TUPLES['SETS'].tolist(), index=df_TUPLES.index)
        df_TUPLES = df_TUPLES.drop(['index', 'SETS'], axis=1)
        df_TUPLES = df_TUPLES[sets + ['YEAR'] + ['VALUE']]

    for s in sets:
        df_set = pd.DataFrame(df_TUPLES[s].unique(), columns=['VALUE'])
        df_set.to_csv(os.path.join(path_csv, f"{s}.csv"), index=False)

    df_param = df[df["Parameter"] == 'CapacityToActivityUnit'].dropna(axis=1)
    sets = df_param.columns[~df_param.columns.isin(year) & (df_param.columns != 'Parameter')].tolist()
    sets.remove("Time indipendent variables")
    df_TUPLES = df_param.drop(['Parameter'], axis=1).rename(
        columns={"Time indipendent variables": "VALUE"}
    ).loc[~(df_param.drop(['Parameter'], axis=1).rename(
        columns={"Time indipendent variables": "VALUE"}
    )['VALUE'] == 0)]
    for s in sets:
        df_set = pd.DataFrame(df_TUPLES[s].unique(), columns=['VALUE'])
        df_set.to_csv(os.path.join(path_csv, f"{s}.csv"), index=False)


def completar_Matrix_Act_Ratio(path_csv, variable):
    df = pd.read_csv(path_csv + variable)
    regions = df["REGION"].unique()
    technologies = pd.read_csv(path_csv + "TECHNOLOGY.csv", dtype=str)["VALUE"].unique()
    fuels = pd.read_csv(path_csv + "FUEL.csv", dtype=str)["VALUE"].unique()
    modes = pd.read_csv(path_csv + "MODE_OF_OPERATION.csv")["VALUE"].unique()
    years = pd.read_csv(path_csv + "YEAR.csv")["VALUE"].unique()

    all_combinations = pd.DataFrame(itertools.product(
        regions, technologies, fuels, modes, years),
        columns=["REGION", "TECHNOLOGY", "FUEL", "MODE_OF_OPERATION", "YEAR"]
    )
    result = all_combinations.merge(df, on=["REGION", "TECHNOLOGY", "MODE_OF_OPERATION", "FUEL", "YEAR"], how="left")
    result.dropna(subset=["VALUE"], inplace=True)
    result.to_csv(path_csv + variable, index=False)


def completar_Matrix_Emission(path_csv, variable):
    df = pd.read_csv(path_csv + variable)
    regions = df["REGION"].unique()
    technologies = pd.read_csv(path_csv + "TECHNOLOGY.csv")["VALUE"].unique()
    emission = pd.read_csv(path_csv + "EMISSION.csv")["VALUE"].unique()
    modes = pd.read_csv(path_csv + "MODE_OF_OPERATION.csv")["VALUE"].unique()
    years = pd.read_csv(path_csv + "YEAR.csv")["VALUE"].unique()

    all_combinations = pd.DataFrame(itertools.product(
        regions, technologies, emission, modes, years),
        columns=["REGION", "TECHNOLOGY", "EMISSION", "MODE_OF_OPERATION", "YEAR"]
    )
    result = all_combinations.merge(df, on=["REGION", "TECHNOLOGY", "EMISSION", "MODE_OF_OPERATION", "YEAR"], how="left")
    result.dropna(subset=["VALUE"], inplace=True)
    result.to_csv(path_csv + variable, index=False)


def completar_Matrix_Cost(path_csv, variable):
    df = pd.read_csv(path_csv + variable)
    regions = df["REGION"].unique()
    technologies = pd.read_csv(path_csv + "TECHNOLOGY.csv")["VALUE"].unique()
    modes = pd.read_csv(path_csv + "MODE_OF_OPERATION.csv")["VALUE"].unique()
    years = pd.read_csv(path_csv + "YEAR.csv")["VALUE"].unique()

    all_combinations = pd.DataFrame(itertools.product(
        regions, technologies, modes, years),
        columns=["REGION", "TECHNOLOGY", "MODE_OF_OPERATION", "YEAR"]
    )
    result = all_combinations.merge(df, on=["REGION", "TECHNOLOGY", "MODE_OF_OPERATION", "YEAR"], how="left")
    result.dropna(subset=["VALUE"], inplace=True)
    result.to_csv(path_csv + variable, index=False)


def process_and_save_emission_ratios(emission_activity_path, input_activity_path, output_path, path_csv):
    df_emission = pd.read_csv(path_csv + emission_activity_path)
    df_input = pd.read_csv(path_csv + input_activity_path)

    keys = ['REGION', 'TECHNOLOGY', 'MODE_OF_OPERATION', 'YEAR']
    for df in (df_emission, df_input):
        for k in keys:
            if k in df.columns:
                df[k] = df[k].astype(str).str.strip()

    merged = pd.merge(
        df_emission, df_input,
        on=['REGION', 'TECHNOLOGY', 'MODE_OF_OPERATION', 'YEAR'],
        how='left'
    ).query("VALUE_x != 0 and VALUE_y != 0").assign(
        VALUE=lambda x: x['VALUE_x'] * x['VALUE_y']
    )
    drop_cols = [c for c in ['VALUE_x', 'VALUE_y', 'FUEL'] if c in merged.columns]
    merged = merged.drop(columns=drop_cols)

    merged_unique = merged.groupby(
        ['REGION', 'TECHNOLOGY', 'EMISSION', 'MODE_OF_OPERATION', 'YEAR'],
        as_index=False
    ).agg({'VALUE': 'first'})

    final_merged = pd.merge(
        df_emission, merged_unique,
        on=['REGION', 'TECHNOLOGY', 'EMISSION', 'MODE_OF_OPERATION', 'YEAR'],
        how='left', suffixes=('_df1', '_df4')
    ).assign(
        VALUE=lambda x: x.apply(
            lambda row: row['VALUE_df4']
            if pd.notnull(row['VALUE_df4']) and row['VALUE_df1'] != row['VALUE_df4']
            else row['VALUE_df1'],
            axis=1
        )
    ).loc[:, ['REGION', 'TECHNOLOGY', 'EMISSION', 'MODE_OF_OPERATION', 'YEAR', 'VALUE']]

    final_merged.to_csv(path_csv + output_path, index=False)


def filter_params_by_sets(path_csv, df_colombia):
    paramter_list = df_colombia["Parameter"].unique()
    for p in paramter_list:
        fpath = path_csv + p + ".csv"
        if not os.path.exists(fpath):
            continue
        df_prueba = pd.read_csv(fpath)
        sets_cols = df_prueba.columns.drop('VALUE')
        if 'REGION2' in sets_cols:
            sets_cols = df_prueba.columns.drop(['REGION2', 'VALUE'])
        for s in sets_cols:
            set_fpath = path_csv + s + ".csv"
            if os.path.exists(set_fpath):
                df_sets = pd.read_csv(set_fpath)
                df_prueba = df_prueba[df_prueba[s].isin(df_sets.VALUE.tolist())]
        df_prueba.to_csv(fpath, index=False)


# ========================================================================
#  UDC (celdas 18-20 del notebook)
# ========================================================================

def crear_csv_UDC(udc_list, path_csv):
    pd.DataFrame({"VALUE": udc_list}).to_csv(
        os.path.join(path_csv, "UDC.csv"), index=False,
    )


def crear_UDCMultiplier(path_csv, multiplier_type, valor_default=0):
    af = pd.read_csv(path_csv + "AvailabilityFactor.csv")
    udc = pd.read_csv(path_csv + "UDC.csv")
    udc["UDC"] = udc["VALUE"].astype(str)
    udc = udc[["UDC"]]
    af["_tmp"] = 1
    udc["_tmp"] = 1
    df = af.merge(udc, on="_tmp").drop(columns="_tmp")
    df["VALUE"] = valor_default
    df = df[["REGION", "TECHNOLOGY", "UDC", "YEAR", "VALUE"]]
    df.to_csv(path_csv + f"UDCMultiplier{multiplier_type}.csv", index=False)


def crear_UDC_parametros(path_csv, valor_constant_default=0.0, valor_tag_default=2.0):
    region = pd.read_csv(path_csv + "REGION.csv")
    udc = pd.read_csv(path_csv + "UDC.csv")
    year = pd.read_csv(path_csv + "YEAR.csv")

    region["REGION"] = region["VALUE"].astype(str)
    udc["UDC"] = udc["VALUE"].astype(str)
    year["YEAR"] = year["VALUE"].astype(int)
    region = region[["REGION"]]
    udc = udc[["UDC"]]
    year = year[["YEAR"]]
    region["_tmp"] = 1
    udc["_tmp"] = 1
    year["_tmp"] = 1

    df_constant = region.merge(udc, on="_tmp").merge(year, on="_tmp").drop(columns="_tmp")
    df_constant["VALUE"] = valor_constant_default
    df_constant[["REGION", "UDC", "YEAR", "VALUE"]].to_csv(
        path_csv + "UDCConstant.csv", index=False,
    )

    region["_tmp"] = 1
    udc["_tmp"] = 1
    df_tag = region.merge(udc, on="_tmp").drop(columns="_tmp")
    df_tag["VALUE"] = valor_tag_default
    df_tag[["REGION", "UDC", "VALUE"]].to_csv(path_csv + "UDCTag.csv", index=False)


def actualizar_UDCMultiplier(multiplier_type, path_csv, tech_multiplier_dict):
    archivo = f"UDCMultiplier{multiplier_type}.csv"
    fpath = path_csv + archivo
    df = pd.read_csv(fpath)
    mask = df["TECHNOLOGY"].isin(tech_multiplier_dict.keys())
    df.loc[mask, "VALUE"] = df.loc[mask, "TECHNOLOGY"].map(tech_multiplier_dict).astype(float)
    df.to_csv(fpath, index=False)


def actualizar_UDCTag(valor, path_csv):
    fpath = path_csv + "UDCTag.csv"
    df = pd.read_csv(fpath)
    df["VALUE"] = float(valor)
    df.to_csv(fpath, index=False)


UDC_RESERVE_MARGIN_DICT = {
    "PWRAFR": -1.0, "PWRBGS": -1.0, "PWRCOA": -1.0, "PWRCOACCS": -1.0,
    "PWRCSP": 0.0, "PWRDSL": -1.0, "PWRFOIL": -1.0, "PWRGEO": -1.0,
    "PWRHYDDAM": -1.0, "PWRHYDROR": 0.0, "PWRHYDROR_NDC": 0.0,
    "PWRJET": -1.0, "PWRLPG": -1.0, "PWRNGS_CC": -1.0, "PWRNGS_CS": -1.0,
    "PWRNGSCCS": -1.0, "PWRNUC": -1.0, "PWRSOLRTP": 0.0,
    "PWRSOLRTP_ZNI": 0.0, "PWRSOLUGE": 0.0, "PWRSOLUGE_BAT": -1.0,
    "PWRSOLUPE": 0.0, "PWRSTD": 0.0, "PWRWAS": -1.0,
    "PWRWNDOFS_FIX": -1.0, "PWRWNDOFS_FLO": -1.0, "PWRWNDONS": -1.0,
    "GRDTYDELC": (1.0 / 0.9) * 1.2,
}


# ========================================================================
#  Pipeline completo: SAND Excel → CSVs → build_instance → solve
# ========================================================================

def generate_notebook_csvs(excel_path: str, csv_dir: str, div: int = 1) -> None:
    """Genera CSVs exactamente como lo hace el notebook."""
    path_csv = csv_dir + os.sep

    print(f"  Leyendo Excel SAND: {excel_path}")
    df_colombia = pd.read_excel(excel_path, sheet_name='Parameters')
    for col in df_colombia.select_dtypes(include="object").columns:
        df_colombia[col] = df_colombia[col].str.strip()
    print(f"  Parámetros encontrados: {len(df_colombia['Parameter'].unique())}")

    print("  Generando sets...")
    SAND_SETS_to_CSV(df_colombia, path_csv, 96 / div)

    print("  Generando parámetros...")
    df_parametros = df_colombia["Parameter"].unique()
    for p in df_parametros:
        SAND_to_CSV(df_colombia, p, path_csv, 96 / div)

    print("  Filtrando parámetros por sets...")
    filter_params_by_sets(path_csv, df_colombia)

    print("  Completando matrices (ActivityRatio)...")
    completar_Matrix_Act_Ratio(path_csv, 'InputActivityRatio.csv')
    completar_Matrix_Act_Ratio(path_csv, 'OutputActivityRatio.csv')

    if os.path.exists(path_csv + "EMISSION.csv"):
        print("  Completando matriz (EmissionActivityRatio)...")
        completar_Matrix_Emission(path_csv, 'EmissionActivityRatio.csv')

    print("  Completando matriz (VariableCost)...")
    completar_Matrix_Cost(path_csv, 'VariableCost.csv')

    if os.path.exists(path_csv + "EMISSION.csv"):
        print("  Procesando emisiones a la entrada...")
        process_and_save_emission_ratios(
            'EmissionActivityRatio.csv',
            'InputActivityRatio.csv',
            'EmissionActivityRatio.csv',
            path_csv,
        )

    ## UDC de margen de reserva desactivada 
    # print("  Generando UDC...")
    # crear_csv_UDC(["UDC_Margin"], path_csv)
    # for mtype in ["TotalCapacity", "NewCapacity", "Activity"]:
    #     crear_UDCMultiplier(path_csv, mtype, valor_default=0)
    # crear_UDC_parametros(path_csv, valor_constant_default=0.0, valor_tag_default=2.0)
    # actualizar_UDCMultiplier("TotalCapacity", path_csv, UDC_RESERVE_MARGIN_DICT)
    # actualizar_UDCTag(0, path_csv)

    csv_files = [f for f in os.listdir(csv_dir) if f.endswith('.csv')]
    print(f"  Total CSVs generados: {len(csv_files)}")


def run_app_solver(csv_dir: str, solver_name: str = "glpk") -> dict:
    """Usa build_instance y solve_model de la app para resolver."""
    from app.simulation.core.instance_builder import build_instance
    from app.simulation.core.model_definition import create_abstract_model
    from app.simulation.core.solver import solve_model

    has_storage = all(
        os.path.exists(os.path.join(csv_dir, f"{s}.csv"))
        for s in ["STORAGE", "SEASON", "DAYTYPE", "DAILYTIMEBRACKET"]
    )
    has_udc = os.path.exists(os.path.join(csv_dir, "UDC.csv"))

    print(f"  has_storage={has_storage}, has_udc={has_udc}")

    print("  Creando AbstractModel...")
    model = create_abstract_model(has_storage=has_storage, has_udc=has_udc)

    print("  Construyendo instancia via DataPortal...")
    instance = build_instance(model, csv_dir, has_storage=has_storage, has_udc=has_udc)

    print(f"  Resolviendo con {solver_name}...")
    result = solve_model(instance, solver_name=solver_name)

    import pyomo.environ as pyo
    obj = 0.0
    try:
        obj = float(pyo.value(instance.OBJ))
    except Exception:
        pass

    print(f"\n{'='*60}")
    print(f"  Solver:   {result['solver_name']}")
    print(f"  Status:   {result['solver_status']}")
    print(f"  Objetivo: {obj:,.2f}")
    print(f"{'='*60}")

    return {"instance": instance, "solver_result": result, "objective": obj}


def compare_csvs(notebook_dir: str, label: str = "notebook") -> None:
    """Muestra estadísticas de los CSVs generados."""
    csv_files = sorted(f for f in os.listdir(notebook_dir) if f.endswith('.csv'))
    print(f"\n  CSVs en {label}: {len(csv_files)}")

    sets_info = []
    params_info = []
    for f in csv_files:
        df = pd.read_csv(os.path.join(notebook_dir, f))
        if len(df.columns) == 1 and df.columns[0] == "VALUE":
            sets_info.append((f, len(df)))
        else:
            non_null = df["VALUE"].notna().sum() if "VALUE" in df.columns else len(df)
            params_info.append((f, len(df), non_null))

    print(f"\n  Sets:")
    for name, count in sets_info:
        print(f"    {name:<35s} {count:>6d} elementos")

    print(f"\n  Parámetros (top 20 por filas):")
    params_info.sort(key=lambda x: -x[1])
    for name, total, non_null in params_info[:20]:
        print(f"    {name:<45s} {total:>8d} filas ({non_null:>8d} con valor)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Comparar notebook vs app: SAND Excel → CSVs → solve",
    )
    parser.add_argument(
        "--excel", type=Path, default=Path(DEFAULT_EXCEL),
        help=f"Ruta al archivo SAND .xlsm (default: {DEFAULT_EXCEL})",
    )
    parser.add_argument(
        "--solver", choices=("highs", "glpk"), default="glpk",
        help="Solver a usar (default: glpk)",
    )
    parser.add_argument(
        "--keep-csvs", action="store_true",
        help="Mantener CSVs temporales en backend/tmp/comparison_csvs/",
    )
    args = parser.parse_args()

    if not args.excel.is_file():
        print(f"[ERROR] No existe el archivo Excel: {args.excel}")
        return 1

    if args.keep_csvs:
        csv_dir = str(PROJECT_ROOT / "tmp" / "comparison_csvs")
        os.makedirs(csv_dir, exist_ok=True)
    else:
        _tmpdir = tempfile.mkdtemp(prefix="notebook_csvs_")
        csv_dir = _tmpdir

    try:
        print(f"\n{'='*60}")
        print("PASO 1: Generar CSVs con lógica del notebook")
        print(f"{'='*60}")
        generate_notebook_csvs(str(args.excel), csv_dir)
        compare_csvs(csv_dir, "notebook")

        print(f"\n{'='*60}")
        print("PASO 2: Resolver con build_instance + solve_model de la app")
        print(f"{'='*60}")
        result = run_app_solver(csv_dir, solver_name=args.solver)

        if result["solver_result"]["solver_status"].lower() == "optimal":
            print("\n*** RESULTADO: Solución óptima encontrada ***")
            print("  Los CSVs generados por el notebook son compatibles con la app.")
            print(f"  Valor objetivo: {result['objective']:,.2f}")
        else:
            print(f"\n*** RESULTADO: Solver terminó con status {result['solver_result']['solver_status']} ***")

        if args.keep_csvs:
            print(f"\n  CSVs guardados en: {csv_dir}")

    finally:
        if not args.keep_csvs and '_tmpdir' in locals():
            import shutil
            shutil.rmtree(_tmpdir, ignore_errors=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
