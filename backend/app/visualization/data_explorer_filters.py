"""Mapping ``chart_type`` → filtros para el Data Explorer.

Cada entrada describe los datos que componen una gráfica. El frontend usa
estos filtros para construir la URL del Data Explorer cuando el usuario hace
click en "Ver Datos de Resultados", de forma que aparezcan exactamente las
filas que el chart agrega/grafica (incluyendo las que se suman bajo una
agrupación).

Forma de cada entrada:
    {
        "variable_names":      list[str],   # variables sumadas
        "technology_prefixes": list[str],   # prefijos para resolver tecnologías (startswith)
        "fuel_prefixes":       list[str],   # opcional — para charts con filtro por FUEL
        "fuel_names":          list[str],   # opcional — IN(...)
        "emission_names":      list[str],   # opcional — IN(...) para emisiones
    }

Cuando un chart no aparece en el dict, ``get_data_explorer_filters`` cae a
defaults derivados de ``CONFIGS[chart_type]``:
    - ``variable_names = [variable_default]``
    - sin restricción adicional.

Mantener este mapping cerca del código que define cada chart para que sea
obvio cuándo agregar/actualizar una entrada.
"""
from __future__ import annotations

from typing import Any

# ── Conjuntos compartidos ───────────────────────────────────────────────────
_DEMANDA_PREFIJOS = [
    "DEMRES", "DEMIND", "DEMTRA", "DEMTER",
    "DEMCON", "DEMAGF", "DEMMIN", "DEMCOQ",
]
_LIQUIDOS_FUELS = ["DSL", "FOL", "GSL", "JET", "LPG"]
_GEI_GASES = ["EMIC02", "EMICH4", "EMIN2O"]
_CONTAMINANTES = [
    "EMIBC", "EMICO", "EMICOVDM", "EMINH3", "EMINOx",
    "EMIPM10", "EMIPM2_5", "EMISOx",
]
_PREFIJOS_IMP_LIQUIDOS = ["IMPDSL", "IMPGSL", "IMPJET", "IMPLPG"]
_PREFIJOS_LIQUIDOS_PROD_IMPORT = _PREFIJOS_IMP_LIQUIDOS + ["UPSREF_CAR", "UPSREF_BAR"]


# ── Mapping principal ───────────────────────────────────────────────────────
DATA_EXPLORER_FILTERS: dict[str, dict[str, Any]] = {
    # ── ELÉCTRICO ──────────────────────────────────────────────────────────
    "elec_produccion": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": ["PWR"],
    },
    "prd_electricidad": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": ["PWR"],
    },
    "cap_electricidad": {
        "variable_names": ["TotalCapacityAnnual"],
        "technology_prefixes": ["PWR"],
    },
    "factor_planta": {
        "variable_names": ["TotalCapacityAnnual", "ProductionByTechnology"],
        "technology_prefixes": ["PWR"],
    },

    # ── DEMANDA ────────────────────────────────────────────────────────────
    "dem_consumo_combustible": {
        "variable_names": ["UseByTechnology"],
        "technology_prefixes": _DEMANDA_PREFIJOS,
    },
    "dem_consumo_liquidos": {
        "variable_names": ["UseByTechnology"],
        "technology_prefixes": _DEMANDA_PREFIJOS,
        "fuel_names": _LIQUIDOS_FUELS,
    },
    "dem_consumo_liquidos_total": {
        "variable_names": ["UseByTechnology"],
        "technology_prefixes": _DEMANDA_PREFIJOS,
        "fuel_names": _LIQUIDOS_FUELS,
    },
    "res_total": {
        "variable_names": ["UseByTechnology"],
        "technology_prefixes": ["DEMRES"],
    },
    "res_uso": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": ["DEMRES"],
    },
    "ind_total": {
        "variable_names": ["UseByTechnology"],
        "technology_prefixes": ["DEMIND"],
    },
    "ind_uso": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": ["DEMIND"],
    },
    "tra_total": {
        "variable_names": ["UseByTechnology"],
        "technology_prefixes": ["DEMTRA"],
    },
    "tra_uso": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": ["DEMTRA"],
    },
    "ter_total": {
        "variable_names": ["UseByTechnology"],
        "technology_prefixes": ["DEMTER"],
    },
    "ter_uso": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": ["DEMTER"],
    },
    "con_total": {
        "variable_names": ["UseByTechnology"],
        "technology_prefixes": ["DEMCON"],
    },
    "agf_total": {
        "variable_names": ["UseByTechnology"],
        "technology_prefixes": ["DEMAGF"],
    },
    "min_total": {
        "variable_names": ["UseByTechnology"],
        "technology_prefixes": ["DEMMIN"],
    },
    "coq_total": {
        "variable_names": ["UseByTechnology"],
        "technology_prefixes": ["DEMCOQ"],
    },
    "otros_total": {
        "variable_names": ["UseByTechnology"],
        "technology_prefixes": _DEMANDA_PREFIJOS,
    },

    # ── CAPACIDADES ────────────────────────────────────────────────────────
    "cap_industrial": {
        "variable_names": ["TotalCapacityAnnual"],
        "technology_prefixes": ["DEMIND"],
    },
    "cap_transporte": {
        "variable_names": ["TotalCapacityAnnual"],
        "technology_prefixes": ["DEMTRA"],
    },
    "cap_terciario": {
        "variable_names": ["TotalCapacityAnnual"],
        "technology_prefixes": ["DEMTER"],
    },
    "cap_otros": {
        "variable_names": ["TotalCapacityAnnual"],
        "technology_prefixes": ["DEMRES", "DEMCON", "DEMAGF", "DEMMIN", "DEMCOQ"],
    },
    "ref_capacidad": {
        "variable_names": ["TotalCapacityAnnual"],
        "technology_prefixes": ["UPSREF"],
    },
    "cap_h2": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": ["UPSALK", "UPSPEM"],
    },
    "cap_electrolisis_verde": {
        "variable_names": ["TotalCapacityAnnual"],
        "technology_prefixes": ["UPSALK", "UPSPEM"],
    },

    # ── UPSTREAM & REFINACIÓN ──────────────────────────────────────────────
    "gas_consumo": {
        "variable_names": ["UseByTechnology"],
        "fuel_prefixes": ["NGS"],
    },
    "gas_produccion": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": ["UPSREG", "MINNGS"],
    },
    "gas_capacidad": {
        "variable_names": ["TotalCapacityAnnual"],
        "technology_prefixes": ["UPSREG", "MINNGS"],
    },
    "gas_import_export": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": ["IMPLNG", "EXPNGS"],
    },
    "ref_total": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": ["UPSREF"],
    },
    "ref_consumo": {
        "variable_names": ["UseByTechnology"],
        "technology_prefixes": ["UPSREF"],
    },
    "ref_import": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": ["UPSREF"] + _PREFIJOS_IMP_LIQUIDOS,
    },
    "ref_cartagena": {
        "variable_names": ["UseByTechnology"],
        "technology_prefixes": ["UPSREF_CAR"],
    },
    "ref_barrancabermeja": {
        "variable_names": ["UseByTechnology"],
        "technology_prefixes": ["UPSREF_BAR"],
    },
    "liquidos_prod_import": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": _PREFIJOS_LIQUIDOS_PROD_IMPORT,
    },
    "ups_refinacion": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": ["UPSSAF", "UPSALK", "UPSPEM"],
    },
    "saf_produccion": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": ["UPSSAF", "UPSBJS"],
    },

    # ── HIDRÓGENO ──────────────────────────────────────────────────────────
    "h2_consumo": {
        "variable_names": ["UseByTechnology"],
        "fuel_names": ["HDG", "HDG002"],
    },

    # ── MINERÍA / EXTRACCIÓN ───────────────────────────────────────────────
    "min_hidrocarburos": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": ["MINOIL", "MINNGS"],
    },
    "min_carbon": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": ["MINCOA"],
    },
    "extraccion_min": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": ["MINBAG", "MINOPL", "MINWAS", "MINAFR", "MINSGC", "MINWOO", "MINCOA"],
    },
    "solidos_extraccion": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": ["MINCOA"],
    },
    "solidos_import": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": ["MINCOA", "IMPCOA"],
    },
    "solidos_flujos": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": ["MINCOA", "IMPCOA", "EXPCOA"],
    },
    "exp_carbon": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": ["EXPCOA"],
    },
    "oferta_bioenergia": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": ["MINWAS", "MINOPL", "MINSGC", "MINWOO", "MINBAG"],
    },

    # ── COMERCIO EXTERIOR ──────────────────────────────────────────────────
    "imp_exp_crudo": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": ["IMPOIL", "EXPOIL"],
    },
    "ref_produccion_importaciones": {
        "variable_names": ["ProductionByTechnology"],
        "technology_prefixes": ["UPSREF_CAR", "UPSREF_BAR", "IMPDSL", "IMPGSL", "IMPJET", "IMPLPG"],
    },
    "elec_consumo_liquidos": {
        "variable_names": ["UseByTechnology"],
        "technology_prefixes": ["PWRDSL", "PWRFOL", "PWRGSL", "PWRJET", "PWRLPG"],
    },
    "exp_liquidos_gas": {
        "variable_names": ["ProductionByTechnology", "UseByTechnology"],
        "technology_prefixes": ["EXPDSL", "EXPGSL", "EXPJET", "EXPLPG", "EXPNGS"],
    },

    # ── EMISIONES ──────────────────────────────────────────────────────────
    "emisiones_total": {
        "variable_names": ["AnnualEmissions"],
    },
    "emisiones_sectorial": {
        "variable_names": ["AnnualTechnologyEmission"],
    },
    "emisiones_gei": {
        "variable_names": ["AnnualTechnologyEmission"],
        "emission_names": _GEI_GASES,
    },
    "emisiones_contaminantes": {
        "variable_names": ["AnnualTechnologyEmission"],
        "emission_names": _CONTAMINANTES,
    },
    "emisiones_contaminantes_pct": {
        "variable_names": ["AnnualTechnologyEmission"],
        "emission_names": _CONTAMINANTES,
    },
}


def get_data_explorer_filters(chart_type: str, variable_default: str | None = None) -> dict[str, Any]:
    """Devuelve los filtros para abrir el Data Explorer desde un chart.

    Si no hay entrada explícita para ``chart_type``, retorna un dict con
    ``variable_names = [variable_default]`` (si se pasó). El frontend siempre
    recibe al menos la lista de variables que el chart consume.
    """
    entry = DATA_EXPLORER_FILTERS.get(chart_type)
    if entry is not None:
        return entry

    fallback: dict[str, Any] = {}
    if variable_default:
        fallback["variable_names"] = [variable_default]
    return fallback
