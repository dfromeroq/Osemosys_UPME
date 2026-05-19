"""Tests unitarios de ``app.visualization.regional.transform_regional_df``.

Cubre los 3 casos del requerimiento regional (acumulado nacional, agrupar por
región, filtrar por región) y los edge cases de transmisión interregional y
modelos NATIONAL.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.visualization.regional import (
    extract_region,
    is_interregional_transmission,
    strip_region,
    transform_regional_df,
)


# ──────────────────────────────────────────────────────────────────────────
# Helpers de detección
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "code, expected",
    [
        ("AN_PWRDIST", "AN"),
        ("CA_DEMRES_URB", "CA"),
        ("SO_UPSREF1", "SO"),
        ("NE_GRDNGSDST", "NE"),
        # Sin prefijo válido
        ("PWRDIST", None),
        ("", None),
        ("X", None),
        ("XX_FOO", None),       # XX no está en REGIONAL_PREFIXES
        ("AN-PWRDIST", None),   # separador no es '_'
        # Transmisión interregional → None
        ("TRNELC_AN_NE", None),
        ("TRN_CA_SO", None),
        ("TRNNGS_CA_NE", None),
        ("TRNOIL_AN_CA_1LIV", None),
    ],
)
def test_extract_region(code, expected):
    assert extract_region(code) == expected


@pytest.mark.parametrize(
    "code, expected",
    [
        ("TRNELC_AN_NE", True),
        ("TRNNGS_CA_NE", True),
        ("TRNOIL_AN_CA_1LIV", True),
        ("TRNOIL_NE_AN_2MED", True),
        ("TRN_CA_AN", True),
        ("TRN_CA_CA", True),
        # No transmisión
        ("AN_PWRDIST", False),
        ("PWRDIST", False),
        ("", False),
        ("TRN", False),
        ("TRNELC", False),
    ],
)
def test_is_interregional_transmission(code, expected):
    assert is_interregional_transmission(code) is expected


@pytest.mark.parametrize(
    "code, expected",
    [
        ("AN_PWRDIST", "PWRDIST"),
        ("CA_DEMRES_URB", "DEMRES_URB"),
        # Sin prefijo: se mantiene
        ("PWRDIST", "PWRDIST"),
        ("XX_FOO", "XX_FOO"),
        # Transmisión: se mantiene (no se debe destruir su nombre)
        ("TRNELC_AN_NE", "TRNELC_AN_NE"),
        ("TRN_CA_AN", "TRN_CA_AN"),
    ],
)
def test_strip_region(code, expected):
    assert strip_region(code) == expected


# ──────────────────────────────────────────────────────────────────────────
# transform_regional_df — casos integrales
# ──────────────────────────────────────────────────────────────────────────


def _make_df():
    """DataFrame de prueba con mezcla: 3 regiones × 1 tecnología + transmisión."""
    return pd.DataFrame(
        [
            {"TECHNOLOGY": "AN_PWRDIST", "FUEL": "ELC", "YEAR": 2025, "VALUE": 10.0},
            {"TECHNOLOGY": "CA_PWRDIST", "FUEL": "ELC", "YEAR": 2025, "VALUE": 20.0},
            {"TECHNOLOGY": "SO_PWRDIST", "FUEL": "ELC", "YEAR": 2025, "VALUE": 30.0},
            # Transmisión interregional: debe ser excluida en los 3 casos
            {"TECHNOLOGY": "TRNELC_AN_NE", "FUEL": "ELC", "YEAR": 2025, "VALUE": 99.0},
            {"TECHNOLOGY": "TRN_CA_SO", "FUEL": "ELC", "YEAR": 2025, "VALUE": 88.0},
        ]
    )


def test_caso_a_acumulado_nacional_strip_prefijos():
    """Sin filtro ni agrupación → strip prefijos y el groupby posterior los suma."""
    df = transform_regional_df(_make_df(), region_filter=None, agrupar_por=None)

    # Transmisión excluida
    assert "TRNELC_AN_NE" not in df["TECHNOLOGY"].tolist()
    assert "TRN_CA_SO" not in df["TECHNOLOGY"].tolist()
    # Prefijos eliminados
    assert set(df["TECHNOLOGY"].unique()) == {"PWRDIST"}
    # Suma natural por groupby (el caller hará el sum); aquí solo verificamos
    # que las 3 filas siguen presentes para que groupby pueda colapsarlas.
    assert len(df) == 3
    assert df["VALUE"].sum() == pytest.approx(60.0)


def test_caso_b_filtro_region_especifica():
    """region_filter='AN' → solo filas AN, sin prefijo, sin transmisión."""
    df = transform_regional_df(_make_df(), region_filter="AN", agrupar_por=None)

    assert len(df) == 1
    assert df.iloc[0]["TECHNOLOGY"] == "PWRDIST"
    assert df.iloc[0]["VALUE"] == 10.0
    assert "TRNELC_AN_NE" not in df["TECHNOLOGY"].tolist()


def test_caso_c_agrupar_por_region():
    """agrupar_por='REGION' → columna REGION con prefijo, transmisión excluida."""
    df = transform_regional_df(_make_df(), region_filter=None, agrupar_por="REGION")

    assert "REGION" in df.columns
    assert set(df["REGION"].unique()) == {"AN", "CA", "SO"}
    # Transmisión interregional ausente
    assert "TRNELC_AN_NE" not in df["TECHNOLOGY"].tolist()
    # Tecnología base sin prefijo
    assert set(df["TECHNOLOGY"].unique()) == {"PWRDIST"}
    # Cada región conserva su valor independiente para el groupby posterior
    assert df.loc[df["REGION"] == "AN", "VALUE"].sum() == 10.0
    assert df.loc[df["REGION"] == "CA", "VALUE"].sum() == 20.0
    assert df.loc[df["REGION"] == "SO", "VALUE"].sum() == 30.0


def test_caso_c_descarta_filas_sin_prefijo_valido():
    """En modo REGION, filas sin prefijo regional válido se descartan
    (no encajan en ninguna de las 7 series)."""
    df = pd.DataFrame(
        [
            {"TECHNOLOGY": "AN_PWRDIST", "YEAR": 2025, "VALUE": 1.0},
            {"TECHNOLOGY": "GLOBALTECH", "YEAR": 2025, "VALUE": 999.0},
        ]
    )
    out = transform_regional_df(df, region_filter=None, agrupar_por="REGION")
    assert len(out) == 1
    assert out.iloc[0]["REGION"] == "AN"


def test_caso_a_preserva_tecnologias_sin_prefijo():
    """En acumulado nacional, una tecnología global (sin prefijo) pasa intacta."""
    df = pd.DataFrame(
        [
            {"TECHNOLOGY": "AN_PWRDIST", "YEAR": 2025, "VALUE": 10.0},
            {"TECHNOLOGY": "GLOBALTECH", "YEAR": 2025, "VALUE": 5.0},
        ]
    )
    out = transform_regional_df(df, region_filter=None, agrupar_por=None)
    techs = set(out["TECHNOLOGY"].tolist())
    assert techs == {"PWRDIST", "GLOBALTECH"}


def test_compat_national_sin_prefijos_pasa_intacto():
    """Job NATIONAL: ninguna fila tiene prefijo → no se transforma destructivamente."""
    df = pd.DataFrame(
        [
            {"TECHNOLOGY": "PWRDIST", "YEAR": 2025, "VALUE": 10.0},
            {"TECHNOLOGY": "DEMRES_URB", "YEAR": 2025, "VALUE": 20.0},
        ]
    )
    out = transform_regional_df(df, region_filter=None, agrupar_por=None)
    assert set(out["TECHNOLOGY"].tolist()) == {"PWRDIST", "DEMRES_URB"}
    assert out["VALUE"].sum() == 30.0


def test_empty_df_es_idempotente():
    df = pd.DataFrame(columns=["TECHNOLOGY", "YEAR", "VALUE"])
    out = transform_regional_df(df, region_filter=None, agrupar_por="REGION")
    assert out.empty


def test_df_solo_transmision_queda_vacio():
    df = pd.DataFrame(
        [
            {"TECHNOLOGY": "TRNELC_AN_NE", "YEAR": 2025, "VALUE": 1.0},
            {"TECHNOLOGY": "TRN_CA_SO", "YEAR": 2025, "VALUE": 2.0},
        ]
    )
    out = transform_regional_df(df, region_filter=None, agrupar_por=None)
    assert out.empty


def test_region_filter_invalido_se_comporta_como_acumulado():
    """region_filter='XX' (no en REGIONAL_PREFIXES) → cae a caso (a)."""
    df = _make_df()
    out = transform_regional_df(df, region_filter="XX", agrupar_por=None)
    # No es filtro → strip de todos
    assert set(out["TECHNOLOGY"].unique()) == {"PWRDIST"}


# ──────────────────────────────────────────────────────────────────────────
# transform_regional_df — strip de FUEL
# ──────────────────────────────────────────────────────────────────────────


def _make_df_fuel_prefijado():
    """DataFrame con FUEL también prefijado (como llegan los outputs REGIONAL)."""
    return pd.DataFrame(
        [
            {"TECHNOLOGY": "AN_PWRDIST", "FUEL": "AN_ELC003", "YEAR": 2025, "VALUE": 10.0},
            {"TECHNOLOGY": "CA_PWRDIST", "FUEL": "CA_ELC003", "YEAR": 2025, "VALUE": 20.0},
            {"TECHNOLOGY": "SE_DEMRES_URB", "FUEL": "SE_RESILU_URB", "YEAR": 2025, "VALUE": 30.0},
        ]
    )


def test_caso_a_strippea_fuel():
    """Acumulado nacional: FUEL pierde el prefijo regional."""
    out = transform_regional_df(
        _make_df_fuel_prefijado(), region_filter=None, agrupar_por=None
    )
    assert set(out["FUEL"].unique()) == {"ELC003", "RESILU_URB"}


def test_caso_b_strippea_fuel():
    """Filtro por región: FUEL queda strippeado en las filas que sobreviven."""
    out = transform_regional_df(
        _make_df_fuel_prefijado(), region_filter="AN", agrupar_por=None
    )
    assert len(out) == 1
    assert out.iloc[0]["FUEL"] == "ELC003"


def test_caso_c_strippea_fuel():
    """Agrupar por región: FUEL strippeado y columna REGION presente."""
    out = transform_regional_df(
        _make_df_fuel_prefijado(), region_filter=None, agrupar_por="REGION"
    )
    assert "REGION" in out.columns
    assert set(out["FUEL"].unique()) == {"ELC003", "RESILU_URB"}
    assert set(out["REGION"].unique()) == {"AN", "CA", "SE"}


def test_strip_fuel_idempotente_global():
    """FUELs sin prefijo regional (OIL, EMICO2, SAF) se preservan intactos."""
    df = pd.DataFrame(
        [
            {"TECHNOLOGY": "AN_PWRDIST", "FUEL": "OIL", "YEAR": 2025, "VALUE": 1.0},
            {"TECHNOLOGY": "CA_PWRDIST", "FUEL": "EMICO2", "YEAR": 2025, "VALUE": 2.0},
            {"TECHNOLOGY": "SE_PWRDIST", "FUEL": "SAF", "YEAR": 2025, "VALUE": 3.0},
        ]
    )
    out = transform_regional_df(df, region_filter=None, agrupar_por=None)
    assert set(out["FUEL"].unique()) == {"OIL", "EMICO2", "SAF"}


def test_df_sin_columna_fuel_no_falla():
    """DataFrames sin columna FUEL (típico de AnnualEmissions) no rompen."""
    df = pd.DataFrame(
        [
            {"TECHNOLOGY": "AN_PWRDIST", "YEAR": 2025, "VALUE": 1.0},
            {"TECHNOLOGY": "CA_PWRDIST", "YEAR": 2025, "VALUE": 2.0},
        ]
    )
    out = transform_regional_df(df, region_filter=None, agrupar_por=None)
    assert "FUEL" not in out.columns
    assert set(out["TECHNOLOGY"].unique()) == {"PWRDIST"}
