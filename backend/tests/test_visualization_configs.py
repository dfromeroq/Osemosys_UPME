"""Tests unitarios para configuraciones de visualización (Fase 1 — backend configs)."""

from __future__ import annotations

import pandas as pd
import pytest

from app.visualization.chart_service import get_chart_catalog
from app.visualization.configs_legacy import CONFIGS, _filtro_solidos_import, _filtro_solidos_flujos
from app.visualization.configs_legacy import _filtro_solidos_extraccion, _filtro_ref_total
from app.visualization.configs_legacy import _filtro_construccion, _filtro_agroforestal
from app.visualization.configs_legacy import _filtro_mineria, _filtro_coquerias
from app.visualization.configs_legacy import _filtro_extraccion_min, _filtro_saf_produccion
from app.visualization.configs_legacy import (
    _filtro_h2,
    _filtro_ups_refinacion,
    _filtro_min_hidrocarburos,
    _filtro_min_carbon,
)


# Configs nuevos del plan de implementación v3 (10 configs)
CONFIGS_PLAN_V3 = {
    "res_uso",
    "ind_uso",
    "tra_uso",
    "ter_uso",
    "elec_produccion",
    "cap_h2",
    "h2_consumo",
    "ups_refinacion",
    "min_hidrocarburos",
    "min_carbon",
}

# Configs nuevos portados en Fase 1
CONFIGS_FASE1 = {
    "solidos_import",
    "solidos_flujos",
    "solidos_extraccion",
    "ref_capacidad",
    "con_total",
    "agf_total",
    "min_total",
    "coq_total",
    "extraccion_min",
    "saf_produccion",
}


def _make_df(technologies: list[str], years: list[int] | None = None) -> pd.DataFrame:
    """DataFrame mínimo con columna TECHNOLOGY (y opcional YEAR, VALUE)."""
    year = years or [2030]
    rows = []
    for tech in technologies:
        for y in year:
            rows.append({"TECHNOLOGY": tech, "YEAR": y, "VALUE": 1.0, "FUEL": "X"})
    return pd.DataFrame(rows)


class TestChartCatalog:
    """Tests para get_chart_catalog."""

    def test_catalog_includes_fase1_configs(self, db_session) -> None:
        """El catálogo debe exponer todos los configs de Fase 1."""
        catalog = get_chart_catalog()
        ids = {item.id for item in catalog}
        for config_id in CONFIGS_FASE1:
            assert config_id in ids, f"Config '{config_id}' no está en el catálogo"

    def test_catalog_includes_plan_v3_configs(self, db_session) -> None:
        """El catálogo debe exponer los 10 configs nuevos del plan v3."""
        catalog = get_chart_catalog()
        ids = {item.id for item in catalog}
        for config_id in CONFIGS_PLAN_V3:
            assert config_id in ids, f"Config '{config_id}' no está en el catálogo"

    def test_catalog_items_have_required_fields(self, db_session) -> None:
        """Cada ítem del catálogo debe tener id, label, variable_default."""
        catalog = get_chart_catalog()
        for item in catalog:
            assert item.id
            assert item.label
            assert item.variable_default in (
                "ProductionByTechnology",
                "UseByTechnology",
                "TotalCapacityAnnual",
                "AnnualEmissions",
                "AnnualTechnologyEmission",
            )


class TestFiltrosSolidos:
    """Tests para filtros de sólidos (carbón)."""

    def test_solidos_import_mincoa_impcoa(self) -> None:
        df = _make_df(["MINCOA1", "IMPCOA2", "MINBAG"])
        out = _filtro_solidos_import(df)
        assert len(out) == 2
        assert set(out["TECHNOLOGY"]) == {"MINCOA1", "IMPCOA2"}

    def test_solidos_flujos_incluye_expcoa(self) -> None:
        df = _make_df(["MINCOA1", "EXPCOA1", "IMPCOA1"])
        out = _filtro_solidos_flujos(df)
        assert len(out) == 3
        assert "EXPCOA1" in set(out["TECHNOLOGY"])

    def test_solidos_extraccion_solo_mincoa(self) -> None:
        df = _make_df(["MINCOA1", "IMPCOA1", "EXPCOA1"])
        out = _filtro_solidos_extraccion(df)
        assert len(out) == 1
        assert out.iloc[0]["TECHNOLOGY"] == "MINCOA1"


class TestFiltrosSectores:
    """Tests para filtros de sectores demanda."""

    def test_construccion_demcon(self) -> None:
        df = _make_df(["DEMCONSDSL", "DEMCONSELC", "DEMINDBOI"])
        out = _filtro_construccion(df)
        assert len(out) == 2
        assert "DEMINDBOI" not in set(out["TECHNOLOGY"])

    def test_agroforestal_demagf(self) -> None:
        df = _make_df(["DEMAGFDSL", "DEMAGFELC", "DEMRESCKNGSL"])
        out = _filtro_agroforestal(df)
        assert len(out) == 2
        assert "DEMRESCKNGSL" not in set(out["TECHNOLOGY"])

    def test_mineria_demmin(self) -> None:
        df = _make_df(["DEMMINIELC", "DEMMINIDSL", "DEMAGFDSL"])
        out = _filtro_mineria(df)
        assert len(out) == 2
        assert "DEMAGFDSL" not in set(out["TECHNOLOGY"])

    def test_coquerias_demcoq(self) -> None:
        df = _make_df(["DEMCOQDSL", "DEMCOQGSL", "DEMINDREF"])
        out = _filtro_coquerias(df)
        assert len(out) == 2
        assert "DEMINDREF" not in set(out["TECHNOLOGY"])


class TestFiltrosExtraccion:
    """Tests para filtro de extracción MIN*."""

    def test_extraccion_min_prefijos_validados(self) -> None:
        techs = ["MINBAG", "MINOPL", "MINWAS", "MINWAS_ORG", "MINAFR", "MINSGC", "MINWOO", "MINCOA"]
        df = _make_df(techs)
        out = _filtro_extraccion_min(df)
        assert len(out) == 8
        assert set(out["TECHNOLOGY"]) == set(techs)

    def test_extraccion_min_excluye_otros(self) -> None:
        df = _make_df(["MINBAG", "PWRCOA", "DEMCONSDSL"])
        out = _filtro_extraccion_min(df)
        assert len(out) == 1
        assert out.iloc[0]["TECHNOLOGY"] == "MINBAG"


class TestFiltroRefineria:
    """Tests para ref_capacidad (UPSREF)."""

    def test_ref_capacidad_upsref(self) -> None:
        df = _make_df(["UPSREFDSL", "UPSREFGSL", "IMPLPG1"])
        out = _filtro_ref_total(df)
        assert len(out) == 2
        assert "IMPLPG1" not in set(out["TECHNOLOGY"])


class TestFiltroSaf:
    """Tests para producción SAF."""

    def test_saf_produccion_upssaf_upsbjs(self) -> None:
        df = _make_df(["UPSSAF1", "UPSBJS1", "UPSREFDSL"])
        out = _filtro_saf_produccion(df)
        assert len(out) == 2
        assert "UPSREFDSL" not in set(out["TECHNOLOGY"])


class TestFiltroH2:
    """Tests para filtro H2 (por FUEL, no TECHNOLOGY)."""

    def test_filtro_h2_sin_fuel_retorna_vacio(self) -> None:
        df = pd.DataFrame({"TECHNOLOGY": ["UPSALK"], "YEAR": [2030], "VALUE": [1.0]})
        out = _filtro_h2(df)
        assert out.empty

    def test_filtro_h2_con_hdg_hdg002(self) -> None:
        df = pd.DataFrame([
            {"TECHNOLOGY": "UPSALK", "FUEL": "HDG", "YEAR": 2030, "VALUE": 1.0},
            {"TECHNOLOGY": "UPSSMRCCS", "FUEL": "HDG002", "YEAR": 2030, "VALUE": 1.0},
            {"TECHNOLOGY": "UPSREF", "FUEL": "DSL", "YEAR": 2030, "VALUE": 1.0},
        ])
        out = _filtro_h2(df)
        assert len(out) == 2
        assert set(out["FUEL"]) == {"HDG", "HDG002"}


class TestFiltroUpsRefinacion:
    """Tests para upstream refinación (UPSSAF, UPSALK, UPSPEM)."""

    def test_ups_refinacion_upssaf_upsalk_upspem(self) -> None:
        df = _make_df(["UPSSAF1", "UPSALK1", "UPSPEM1", "UPSREF1", "MINNGS1"])
        out = _filtro_ups_refinacion(df)
        assert len(out) == 3
        assert "UPSREF1" not in set(out["TECHNOLOGY"])
        assert "MINNGS1" not in set(out["TECHNOLOGY"])


class TestFiltroMinHidrocarburos:
    """Tests para minería petróleo y gas (MINOIL, MINNGS)."""

    def test_min_hidrocarburos_minoil_minngs(self) -> None:
        df = _make_df(["MINOIL1", "MINNGS1", "MINCOA1"])
        out = _filtro_min_hidrocarburos(df)
        assert len(out) == 2
        assert "MINCOA1" not in set(out["TECHNOLOGY"])


class TestFiltroMinCarbon:
    """Tests para minería carbón (MINCOA)."""

    def test_min_carbon_mincoa(self) -> None:
        df = _make_df(["MINCOA1", "IMPCOA1", "MINOIL1"])
        out = _filtro_min_carbon(df)
        assert len(out) == 1
        assert out.iloc[0]["TECHNOLOGY"] == "MINCOA1"


class TestConfigsIntegrity:
    """Integridad de CONFIGS: campos obligatorios."""

    @pytest.mark.parametrize("config_id", list(CONFIGS_FASE1) + list(CONFIGS_PLAN_V3))
    def test_config_has_required_fields(self, config_id: str) -> None:
        cfg = CONFIGS[config_id]
        assert "variable_default" in cfg
        assert "agrupar_por" in cfg
        assert "msg_sin_datos" in cfg
        if cfg.get("filtro"):
            assert callable(cfg["filtro"])
