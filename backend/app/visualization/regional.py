"""Adaptación del pipeline de visualización al modelo OSeMOSYS Regional.

En modo ``simulation_type = 'REGIONAL'``, la columna ``TECHNOLOGY`` de
``osemosys_output_param_value`` lleva un prefijo geográfico de 2 letras
(ej. ``AN_PWRDIST``). Este módulo centraliza:

* Las 7 regiones del SIN: ``AN, CA, IN, NE, OR, SE, SO``.
* Etiquetas legibles y paleta de colores dedicada.
* Detección de tecnologías de transmisión interregional (``TRN*_XX_YY``),
  que NO siguen el patrón estándar de prefijo único.
* ``transform_regional_df``: aplica las 3 vistas regionales
  (acumulado nacional, agrupar por región, filtrar por región específica)
  sobre el DataFrame que ``chart_service.py`` ya cargó y filtró.

El módulo NO conoce nada de SQLAlchemy ni FastAPI: solo manipula DataFrames.
El Result Data Explorer (``output-values/wide``) NO debe llamar a estas
funciones — muestra los nombres crudos tal cual salen de la BD.
"""

from __future__ import annotations

import re

import pandas as pd


# ──────────────────────────────────────────────────────────────────────────
# 1. Constantes
# ──────────────────────────────────────────────────────────────────────────

REGIONAL_PREFIXES: frozenset[str] = frozenset({"AN", "CA", "IN", "NE", "OR", "SE", "SO"})

REGION_LABELS: dict[str, str] = {
    "AN": "Antioquia",
    "CA": "Caribe",
    "IN": "Interior",
    "NE": "Noreste",
    "OR": "Oriente",
    "SE": "Suroriente",
    "SO": "Suroccidente",
}

# Paleta colorblind-friendly (7 colores distinguibles).
REGION_COLORS: dict[str, str] = {
    "AN": "#E63946",
    "CA": "#00B4D8",
    "IN": "#2A9D8F",
    "NE": "#F4A261",
    "OR": "#9D4EDD",
    "SE": "#FFB703",
    "SO": "#6A994E",
}

# Tecnologías de transmisión interregional.
# Cubre: TRN_XX_YY, TRNELC_XX_YY, TRNNGS_XX_YY, TRNOIL_XX_YY_(1LIV|2MED|3PES), …
_INTERREG_RE = re.compile(
    r"^TRN(?:[A-Z]{0,5})?_[A-Z]{2}_[A-Z]{2}(?:_[0-9A-Z]+)?$"
)


# ──────────────────────────────────────────────────────────────────────────
# 2. Helpers de detección/parsing (puros, testeables)
# ──────────────────────────────────────────────────────────────────────────


def is_interregional_transmission(code: str) -> bool:
    """``True`` si el código es una tecnología que conecta dos regiones."""
    return bool(_INTERREG_RE.match(code or ""))


def extract_region(code: str) -> str | None:
    """Devuelve el prefijo regional (``'AN'..'SO'``) o ``None``.

    Devuelve ``None`` para tecnologías de transmisión interregional y para
    códigos sin prefijo válido (compat. con modelos Nacionales).
    """
    if not code or len(code) < 4 or code[2] != "_":
        return None
    if is_interregional_transmission(code):
        return None
    prefix = code[:2]
    return prefix if prefix in REGIONAL_PREFIXES else None


def strip_region(code: str) -> str:
    """Quita el prefijo regional si es válido; conserva el resto intacto.

    Las tecnologías interregionales o sin prefijo se devuelven sin cambios.
    """
    region = extract_region(code)
    return code[3:] if region else code


# ──────────────────────────────────────────────────────────────────────────
# 3. Transformador principal
# ──────────────────────────────────────────────────────────────────────────


def transform_regional_df(
    df: pd.DataFrame,
    *,
    region_filter: str | None,
    agrupar_por: str | None,
) -> pd.DataFrame:
    """Aplica las 3 vistas regionales al DataFrame.

    Casos:

    (a) ``region_filter=None`` y ``agrupar_por != 'REGION'``
        → ACUMULADO NACIONAL: excluye transmisión interregional; quita
        prefijos de TECHNOLOGY y FUEL. El ``groupby`` final de
        ``chart_service`` colapsará las 7 regiones bajo la tecnología base.

    (b) ``region_filter in REGIONAL_PREFIXES``
        → FILTRO REGIONAL: deja solo filas con ese prefijo; excluye
        transmisión interregional; quita prefijos de TECHNOLOGY y FUEL para
        preservar los colores y leyendas estándar.

    (c) ``agrupar_por == 'REGION'``
        → AGRUPACIÓN POR REGIÓN: excluye transmisión interregional; añade
        columna ``REGION`` con el prefijo; quita prefijos de TECHNOLOGY y
        FUEL; ``chart_service`` usará la columna ``REGION`` como ``COLOR``.

    Filas cuya ``TECHNOLOGY`` no tiene prefijo válido se conservan en el
    caso (a) (compat. con tecnologías "globales" que pudieran existir en
    un job REGIONAL). El strip de FUEL es idempotente: códigos sin prefijo
    regional válido (``OIL``, ``EMICO2``, ``SAF``…) se preservan intactos.
    """
    if df.empty or "TECHNOLOGY" not in df.columns:
        return df

    tech = df["TECHNOLOGY"].astype(str)

    # Excluir transmisión interregional en los 3 casos (fase 1).
    mask_interreg = tech.map(is_interregional_transmission)
    df = df.loc[~mask_interreg].copy()
    if df.empty:
        return df
    tech = df["TECHNOLOGY"].astype(str)

    region_series = tech.map(extract_region)

    # Strip FUEL común a los 3 casos. Los outputs regionales traen FUEL
    # también prefijado (p. ej. ``SE_ELC003``, ``CA_RESILU_URB``); los
    # filtros y agrupaciones por FUEL del chart_service asumen códigos sin
    # prefijo. ``strip_region`` es idempotente para FUELs globales.
    if "FUEL" in df.columns:
        df["FUEL"] = df["FUEL"].astype(str).map(strip_region)

    # Caso (c): agrupar por región
    if agrupar_por == "REGION":
        df["REGION"] = region_series
        df = df.dropna(subset=["REGION"]).copy()
        df["TECHNOLOGY"] = df["TECHNOLOGY"].astype(str).map(strip_region)
        return df

    # Caso (b): filtrar por región específica
    if region_filter and region_filter in REGIONAL_PREFIXES:
        df = df.loc[region_series == region_filter].copy()
        df["TECHNOLOGY"] = df["TECHNOLOGY"].astype(str).map(strip_region)
        return df

    # Caso (a): acumulado nacional por defecto
    df["TECHNOLOGY"] = tech.map(strip_region)
    return df
