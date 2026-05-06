"""
Configuraciones de gráficas single-escenario.

Basado en osemosys_src/src/configs.py con las siguientes mejoras:
  - Imports ajustados al paquete backend (app.visualization.colors)
  - Lambdas reescritas como funciones nombradas (testabilidad)
  - Campo ``variable_default`` en cada config
  - 3 configs nuevos: prd_electricidad, emisiones_total, emisiones_sectorial
"""

from app.visualization.colors import (
    generar_colores_tecnologias,
    _color_por_grupo_fijo,
    _color_electricidad,
    _color_por_sector,
    _color_por_emision,
    _color_electrolisis,
    _color_h2_produccion,
    _color_h2_consumo,
    _color_bioenergia,
    _color_gas_produccion,
    _color_liquidos_import,
    _color_ref_import,
)

# Gases de efecto invernadero a filtrar (EMIC02 con cero, no letra O)
_GEI_GASES = {"EMIC02", "EMICH4", "EMIN2O"}

# Contaminantes criterio
_CONTAMINANTES = {
    "EMIBC",
    "EMICO",
    "EMICOVDM",
    "EMINH3",
    "EMINOx",
    "EMIPM10",
    "EMIPM2_5",
    "EMISOx",
}

# Modos de transporte por carretera (sub-filtro "CARRETERA")
ROAD_TRANSPORT_CODES = {"BUS", "MOT", "TCK", "STT", "LDV", "FWD", "TAX", "MIC"}
_ROAD_TRANSPORT_PATTERN = "|".join(ROAD_TRANSPORT_CODES)

# Importaciones de líquidos (compartido: ref_import, liquidos_prod_import)
_PREFIJOS_IMP_LIQUIDOS = ("IMPDSL", "IMPGSL", "IMPJET", "IMPLPG")
_PREFIJOS_LIQUIDOS_PROD_IMPORT = (
    _PREFIJOS_IMP_LIQUIDOS
    + ("UPSREF_CAR", "UPSREF_BAR")
    + ("EXPDSL", "EXPGSL", "EXPLPG", "EXPJET")
)

_PREFIJOS_EXP_LIQUIDOS = ("EXPDSL", "EXPGSL", "EXPJET", "EXPLPG")

_PREFIJOS_IMP_LIQUIDOS_ALL = (
    "IMPDSL",
    "IMPGSL",
    "IMPJET",
    "IMPLNG",
    "IMPLPG",
    "IMPOIL",
)


# ════════════════════════════════════════════════════════════════════════
# MAPEO DE VARIABLES → TÍTULOS (para capacidad)
# ════════════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════════════
# NOMBRES DE COMBUSTIBLES (código → nombre legible)
# ════════════════════════════════════════════════════════════════════════

NOMBRES_COMBUSTIBLES = {
    "NGS": "Gas Natural",
    "DSL": "Diésel",
    "ELC": "Electricidad",
    "GSL": "Gasolina",
    "COA": "Carbón",
    "LPG": "GLP",
    "WOO": "Leña",
    "BGS": "Biogás",
    "BAG": "Bagazo",
    "HDG": "Hidrógeno",
    "FOL": "Fuel Oil",
    "BDL": "Biodiésel",
    "JETSAF": "Jet Sostenible (SAF)",
    "JET": "Jet A1",
    "WAS": "Residuos/Biomasa",
    "OIL": "Petróleo",
    "AFR": "Residuos Agrícolas/Forestales",
    "SAF": "SAF",
}


TITULOS_VARIABLES_CAPACIDAD = {
    "TotalCapacityAnnual": "Capacidad Total Anual",
    "NewCapacity": "Capacidad Nueva",
    "AccumulatedNewCapacity": "Capacidad Acumulada",
}


# ════════════════════════════════════════════════════════════════════════
# FILTROS NOMBRADOS (reemplazan los lambdas del original)
# ════════════════════════════════════════════════════════════════════════


def _filtro_contiene(df, prefijo: str, sub_filtro=None, **kw):
    """Filtro genérico: TECHNOLOGY *contiene* el texto dado."""
    return df[df["TECHNOLOGY"].str.contains(prefijo)]


def _filtro_pwr(df, **kw):
    """Tecnologías de generación eléctrica (PWR*)."""
    return df[df["TECHNOLOGY"].str.startswith("PWR")]


def _filtro_pwr_liquidos(df, **kw):
    """Generación eléctrica con combustibles líquidos (PWRDSL, PWRFOL, PWRGSL, PWRJET, PWRLPG).

    Filtra por prefijo de TECHNOLOGY porque el campo FUEL en ProductionByTechnology
    contiene el combustible de salida (ELC), no el de entrada.
    """
    return df[
        df["TECHNOLOGY"].str.startswith(
            ("PWRDSL", "PWRFOL", "PWRGSL", "PWRJET", "PWRLPG")
        )
    ]


def _filtro_pwr_termica(df, **kw):
    """Generación eléctrica con combustibles térmicos (PWRNGS, PWRBGS, PWRCOA).

    Filtra por prefijo de TECHNOLOGY porque el campo FUEL en ProductionByTechnology
    contiene el combustible de salida (ELC), no el de entrada.
    """
    return df[df["TECHNOLOGY"].str.startswith(("PWRNGS", "PWRBGS", "PWRCOA"))]


def _filtro_gas_consumo(df, **kw):
    """Tecnologías que usan gas natural (contienen NGS)."""
    return df[df["TECHNOLOGY"].str.contains("NGS")]


def _filtro_gas_produccion(df, **kw):
    """Tecnologías de producción de gas (UPSREG / MINNGS)."""
    return df[
        df["TECHNOLOGY"].str.startswith("UPSREG")
        | df["TECHNOLOGY"].str.startswith("MINNGS")
    ]


def _filtro_ref_total(df, **kw):
    """Tecnologías de refinería (UPSREF)."""
    return df[df["TECHNOLOGY"].str.startswith("UPSREF")]


def _filtro_ref_cartagena(df, **kw):
    """Refinería de Cartagena (UPSREF_CAR)."""
    return df[df["TECHNOLOGY"].str.startswith("UPSREF_CAR")]


def _filtro_ref_barrancabermeja(df, **kw):
    """Refinería de Barrancabermeja (UPSREF_BAR)."""
    return df[df["TECHNOLOGY"].str.startswith("UPSREF_BAR")]


def _filtro_ref_ambas(df, sub_filtro=None, **kw):
    """Refinerías Cartagena + Barrancabermeja (UseByTechnology).

    sub_filtro:
      - None/'con_crudo': FUEL IN (DSL,GSL,JET,LPG,NGS,ELC,OIL,OIL_1LIV,OIL_2MID,OIL_3PES)
      - 'sin_crudo':     FUEL IN (DSL,GSL,JET,LPG,NGS,ELC,OIL) [excluye OIL_*]
    """
    mask_tech = df["TECHNOLOGY"].str.startswith(("UPSREF_CAR", "UPSREF_BAR"))

    if sub_filtro == "sin_crudo":
        # Solo productos refinados (sin crudos)
        mask_fuel = df["FUEL"].isin({"DSL", "GSL", "JET", "LPG", "NGS", "ELC", "OIL"})
        # Excluir crudos (OIL_1LIV, OIL_2MID, OIL_3PES)
        mask_excluir = ~df["FUEL"].str.startswith("OIL_", na=False)
        return df[mask_tech & mask_fuel & mask_excluir]

    # Default: con crudo (incluye todos los combustibles)
    return df[mask_tech]


def _filtro_liquidos_produccion_importacion(df, **kw):
    """Líquidos: importaciones (DSL, GSL, JET, LPG) + refinerías (CAR, BAR)."""
    return df[df["TECHNOLOGY"].str.startswith(_PREFIJOS_LIQUIDOS_PROD_IMPORT)]


def _filtro_export_liquidos(df, **kw):
    """Exportaciones de líquidos (EXPDSL, EXPGSL, EXPJET, EXPLPG)."""
    return df[df["TECHNOLOGY"].str.startswith(_PREFIJOS_EXP_LIQUIDOS)]


def _filtro_import_liquidos(df, **kw):
    """Importaciones de líquidos (IMPDSL, IMPGSL, IMPJET, IMPLNG, IMPLPG, IMPOIL)."""
    return df[df["TECHNOLOGY"].str.startswith(_PREFIJOS_IMP_LIQUIDOS_ALL)]


def _filtro_demanda_exportaciones_liquidos(df, **kw):
    """Sectores de demanda + exportaciones de líquidos.

    Sectores de demanda: DEMRES, DEMIND, DEMTRA, DEMTER, DEMCON, DEMAGF, DEMCOQ
    Exportaciones: EXPDSL, EXPGSL, EXPJET, EXPLPG
    Combustibles: DSL, FOL, GSL, JET, LPG
    """
    if "TECHNOLOGY" not in df.columns:
        return df.iloc[0:0]

    demanda_mask = df["TECHNOLOGY"].str.startswith(
        ("DEMRES", "DEMIND", "DEMTRA", "DEMTER", "DEMCON", "DEMAGF", "DEMCOQ")
    )
    export_mask = df["TECHNOLOGY"].str.startswith(
        ("EXPDSL", "EXPGSL", "EXPJET", "EXPLPG")
    )

    df = df[demanda_mask | export_mask]

    if "FUEL" not in df.columns:
        return df.iloc[0:0]
    return df[df["FUEL"].isin({"DSL", "FOL", "GSL", "JET", "LPG"})]


def _filtro_ref_import(df, **kw):
    """Refinerías + importaciones."""
    return df[
        df["TECHNOLOGY"].str.startswith("UPSREF")
        | df["TECHNOLOGY"].str.startswith(_PREFIJOS_IMP_LIQUIDOS)
    ]


def _filtro_residencial(df, sub_filtro=None, loc=None, **kw):
    """
    Filtro para tecnologías residenciales con lógica URB/RUR/ZNI.

    sub_filtro : str | None  → ej. 'CKN', 'WHT', 'AIR'
    loc        : str | None  → 'URB', 'RUR', 'ZNI'
    """
    mask = df["TECHNOLOGY"].str.startswith("DEMRES")

    if sub_filtro:
        mask &= df["TECHNOLOGY"].str.contains(sub_filtro)

    if loc == "URB":
        mask &= ~df["TECHNOLOGY"].str.contains("RUR")
        mask &= ~df["TECHNOLOGY"].str.contains("ZNI")
    elif loc == "RUR":
        mask &= df["TECHNOLOGY"].str.contains("RUR")
        mask &= ~df["TECHNOLOGY"].str.contains("ZNI")
    elif loc == "ZNI":
        mask &= ~df["TECHNOLOGY"].str.contains("RUR")
        mask &= df["TECHNOLOGY"].str.contains("ZNI")

    return df[mask]


def _filtro_prefijo_con_sub(df, prefijo: str, sub_filtro=None, **kw):
    """Filtro genérico: startswith(prefijo) + contains(sub_filtro)."""
    mask = df["TECHNOLOGY"].str.startswith(prefijo)
    if sub_filtro:
        mask &= df["TECHNOLOGY"].str.contains(sub_filtro)
    return df[mask]


def _filtro_industrial(df, sub_filtro=None, **kw):
    return _filtro_prefijo_con_sub(df, "DEMIND", sub_filtro)


def _filtro_transporte(df, sub_filtro=None, **kw):
    mask = df["TECHNOLOGY"].str.startswith("DEMTRA")
    if sub_filtro == "CARRETERA":
        road_mask = df["TECHNOLOGY"].str.contains(_ROAD_TRANSPORT_PATTERN, regex=True)
        mask &= road_mask
    elif sub_filtro:
        mask &= df["TECHNOLOGY"].str.contains(sub_filtro)
    return df[mask]


def _filtro_terciario(df, sub_filtro=None, **kw):
    return _filtro_prefijo_con_sub(df, "DEMTER", sub_filtro)


def _filtro_otros(df, sub_filtro=None, **kw):
    if sub_filtro:
        return df[df["TECHNOLOGY"].str.startswith(sub_filtro)]
    return df.iloc[0:0]


def _filtro_construccion(df, sub_filtro=None, **kw):
    return _filtro_prefijo_con_sub(df, "DEMCON", sub_filtro)


def _filtro_agroforestal(df, sub_filtro=None, **kw):
    return _filtro_prefijo_con_sub(df, "DEMAGF", sub_filtro)


def _filtro_mineria(df, sub_filtro=None, **kw):
    return _filtro_prefijo_con_sub(df, "DEMMIN", sub_filtro)


def _filtro_coquerias(df, sub_filtro=None, **kw):
    return _filtro_prefijo_con_sub(df, "DEMCOQ", sub_filtro)


def _filtro_demanda_por_combustible(df, sub_filtro=None, **kw):
    """Todos los sectores de demanda, filtrados por columna FUEL via sub_filtro.

    El filtro usa ``str.startswith`` porque los códigos FUEL en la BD pueden
    tener sufijos numéricos (ej. ELC002, NGS002, LPG002) que deben agruparse
    bajo el código base (ELC, NGS, LPG).
    """
    prefijos = (
        "DEMRES",
        "DEMIND",
        "DEMTRA",
        "DEMTER",
        "DEMCON",
        "DEMAGF",
        "DEMMIN",
        "DEMCOQ",
    )
    df = df[df["TECHNOLOGY"].str.startswith(prefijos)]
    if sub_filtro and "FUEL" in df.columns:
        df = df[df["FUEL"].str.startswith(sub_filtro)]
    return df


def _filtro_solidos_extraccion(df, **kw):
    return df[df["TECHNOLOGY"].str.startswith("MINCOA")]


def _filtro_oferta_bioenergia(df, **kw):
    """Oferta bioenergía: residuos sólidos, palma, orgánica, caña, madera."""
    return df[
        df["TECHNOLOGY"].str.startswith("MINWAS")
        | df["TECHNOLOGY"].str.startswith("MINOPL")
        | df["TECHNOLOGY"].str.startswith("MINWAS_ORG")
        | df["TECHNOLOGY"].str.startswith("MINSGC")
        | df["TECHNOLOGY"].str.startswith("MINWOO")
        | df["TECHNOLOGY"].str.startswith("MINBAG")
    ]


_H2_EXCLUIR = {"UPSHDGRST"}


def _filtro_h2(df, **kw):
    """Tecnologías que producen/consumen hidrógeno (FUEL=HDG/HDG002),
    excluyendo estaciones de despacho/distribución."""
    if "FUEL" not in df.columns:
        return df.iloc[0:0]
    mask_fuel = (df["FUEL"] == "HDG") | (df["FUEL"] == "HDG002")
    mask_excluir = ~df["TECHNOLOGY"].isin(_H2_EXCLUIR)
    return df[mask_fuel & mask_excluir]


def _filtro_ups_refinacion(df, **kw):
    """Upstream refinación: UPSSAF, UPSALK, UPSPEM (biocombustibles e hidrógeno)."""
    return df[
        df["TECHNOLOGY"].str.startswith("UPSSAF")
        | df["TECHNOLOGY"].str.startswith("UPSALK")
        | df["TECHNOLOGY"].str.startswith("UPSPEM")
    ]


def _filtro_electrolisis_verde(df, **kw):
    """Electrolizadores para producción de hidrógeno verde (UPSALK, UPSPEM)."""
    return df[
        df["TECHNOLOGY"].str.startswith("UPSALK")
        | df["TECHNOLOGY"].str.startswith("UPSPEM")
    ]


def _map_h2_verde_azul_gris(tech):
    """Map technology to H2 verde/azul/gris label."""
    t = str(tech)
    if t.startswith("UPSPEM") or t.startswith("UPSALK"):
        return "Hidrógeno verde"
    elif t.startswith("UPSSMRCCS"):
        return "Hidrógeno azul"
    elif t.startswith("UPSSMR"):
        return "Hidrógeno gris"
    return t


def _filtro_h2_verde_azul_gris(df, **kw):
    """Producción de H2: UPSSMR, UPSSMRCCS, UPSPEM, UPSALK."""
    return df[
        df["TECHNOLOGY"].str.startswith("UPSSMR")
        | df["TECHNOLOGY"].str.startswith("UPSPEM")
        | df["TECHNOLOGY"].str.startswith("UPSALK")
    ]


def _color_h2_verde_azul_gris(df, color_col):
    """Verde → H2 verde, Azul → H2 azul, Gris → H2 gris."""
    palette = {
        "Hidrógeno verde": "#10b981",
        "Hidrógeno azul": "#3b82f6",
        "Hidrógeno gris": "#6b7280",
    }
    colors, order = [], []
    for cat in sorted(df[color_col].unique()):
        order.append(cat)
        colors.append(palette.get(cat, "#999999"))
    return colors, order


def _filtro_min_hidrocarburos(df, **kw):
    """Minería petróleo y gas (MINOIL, MINNGS)."""
    return df[
        df["TECHNOLOGY"].str.startswith("MINOIL")
        | df["TECHNOLOGY"].str.startswith("MINNGS")
    ]


def _filtro_min_carbon(df, **kw):
    """Minería carbón (MINCOA)."""
    return df[df["TECHNOLOGY"].str.startswith("MINCOA")]


def _filtro_solidos_import(df, **kw):
    return df[
        df["TECHNOLOGY"].str.startswith("MINCOA")
        | df["TECHNOLOGY"].str.startswith("IMPCOA")
    ]


def _filtro_solidos_flujos(df, **kw):
    return df[
        df["TECHNOLOGY"].str.startswith("MINCOA")
        | df["TECHNOLOGY"].str.startswith("IMPCOA")
        | df["TECHNOLOGY"].str.startswith("EXPCOA")
    ]


def _filtro_saf_produccion(df, **kw):
    return df[
        df["TECHNOLOGY"].str.startswith("UPSSAF")
        | df["TECHNOLOGY"].str.startswith("UPSBJS")
        | df["TECHNOLOGY"].str.startswith("UPSATJ")
    ]


def _filtro_por_fuel_set(df, fuel_set: set, **kw):
    if "FUEL" not in df.columns:
        return df.iloc[0:0]
    return df[df["FUEL"].isin(fuel_set)]


def _filtro_consumo_liquidos(df, **kw):
    """Filtrar sectores de demanda por combustibles líquidos (DSL, FOL, GSL, JET, LPG).

    Sectores de demanda: DEMRES, DEMIND, DEMTRA, DEMTER, DEMCON, DEMAGF, DEMCOQ
    Combustibles: DSL, FOL, GSL, JET, LPG
    """
    if "TECHNOLOGY" not in df.columns:
        return df.iloc[0:0]

    demanda_mask = df["TECHNOLOGY"].str.startswith(
        ("DEMRES", "DEMIND", "DEMTRA", "DEMTER", "DEMCON", "DEMAGF", "DEMCOQ")
    )

    df = df[demanda_mask]

    if "FUEL" not in df.columns:
        return df.iloc[0:0]
    return df[df["FUEL"].isin({"DSL", "FOL", "GSL", "JET", "LPG"})]


def _filtro_liquidos_total(df, **kw):
    """Filtrar demanda por combustibles líquidos (DSL, FOL, GSL, JET, LPG)
    en todos los sectores: demanda + generación eléctrica.

    Sectores de demanda: DEMRES, DEMIND, DEMTRA, DEMTER, DEMCON, DEMAGF, DEMCOQ
    Generación eléctrica: PWRDSL, PWRFOIL, PWRJET, PWRLPG
    """
    if "TECHNOLOGY" not in df.columns:
        return df.iloc[0:0]

    demanda_mask = df["TECHNOLOGY"].str.startswith(
        ("DEMRES", "DEMIND", "DEMTRA", "DEMTER", "DEMCON", "DEMAGF", "DEMCOQ")
    )
    electrico_mask = df["TECHNOLOGY"].str.startswith(
        ("PWRDSL", "PWRFOL", "PWRJET", "PWRLPG")
    )

    df = df[demanda_mask | electrico_mask]

    if "FUEL" not in df.columns:
        return df.iloc[0:0]
    return df[df["FUEL"].isin({"DSL", "FOL", "GSL", "JET", "LPG"})]


def _filtro_gei(df, **kw):
    return _filtro_por_fuel_set(df, _GEI_GASES)


def _filtro_contaminantes(df, **kw):
    return _filtro_por_fuel_set(df, _CONTAMINANTES)


def _filtro_extraccion_min(df, **kw):
    """Tecnologías de extracción: bagazo, petróleo, residuos, biocombustibles, carbón."""
    return df[
        df["TECHNOLOGY"].str.startswith(
            (
                "MINBAG",
                "MINOPL",
                "MINWAS",
                "MINWAS_ORG",
                "MINAFR",
                "MINSGC",
                "MINWOO",
                "MINCOA",
            )
        )
    ]


# ════════════════════════════════════════════════════════════════════════
# CONFIGS — VERSIÓN OPTIMIZADA
# ════════════════════════════════════════════════════════════════════════

CONFIGS = {
    # ═══════════════════════════════════════════════════════════════════
    # GAS
    # ═══════════════════════════════════════════════════════════════════
    "gas_consumo": {
        "titulo": "Gas Natural - UseByTechnology",
        "figura": "Figura 23",
        "filename": "Fig23_Consumo_Gas",
        "print": "CONSUMO DE GAS NATURAL",
        "filtro": _filtro_gas_consumo,
        "msg_sin_datos": "Sin tecnologías que usan gas (NGS)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "variable_default": "UseByTechnology",
    },
    "gas_produccion": {
        "titulo": "Gas Natural - ProductionByTechnology",
        "figura": "Figura 22",
        "filename": "Fig22_Produccion_Gas",
        "print": "PRODUCCIÓN DE GAS NATURAL",
        "filtro": _filtro_gas_produccion,
        "msg_sin_datos": "Sin tecnologías de producción (UPSREG / MINNGS)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": _color_gas_produccion,
        "variable_default": "ProductionByTechnology",
    },
    # ═══════════════════════════════════════════════════════════════════
    # REFINERÍAS
    # ═══════════════════════════════════════════════════════════════════
    "ref_total": {
        "titulo": "Refinerías - ProductionByTechnology",
        "figura": "Figura 24",
        "filename": "Fig24_Ref_Total",
        "print": "REFINERÍAS",
        "filtro": _filtro_ref_total,
        "msg_sin_datos": "Sin tecnologías de refinería (UPSREF)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "variable_default": "ProductionByTechnology",
    },
    "ref_import": {
        "titulo": "Refinerías - Importaciones - ProductionByTechnology",
        "figura": "Figura 25",
        "filename": "Fig25_Ref_Import",
        "print": "REFINERÍAS + IMPORTACIONES",
        "filtro": _filtro_ref_import,
        "msg_sin_datos": "Sin tecnologías de refinería/importación",
        "agrupar_por": "TECNOLOGIA",
        # Para refinerías separamos en (refinería × combustible) y aplicamos
        # una gama por refinería (un color base por refinería, un tono por
        # combustible). Las importaciones (IMP*) conservan su color fijo.
        "split_refineries_by_fuel": True,
        "color_fn": _color_ref_import,
        "variable_default": "ProductionByTechnology",
    },
    "ref_consumo": {
        "titulo": "Refinerías - Consumo Total por Tecnología",
        "figura": "Figura REF-CONSUMO",
        "filename": "Fig_Ref_Consumo",
        "print": "REFINERÍAS - CONSUMO TOTAL",
        "filtro": _filtro_ref_total,
        "msg_sin_datos": "Sin tecnologías de refinería (UPSREF)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "variable_default": "UseByTechnology",
    },
    "ref_cartagena": {
        "titulo": "Refinería de Cartagena - UseByTechnology",
        "figura": "Figura REF-CART",
        "filename": "Fig_Ref_Cartagena",
        "print": "REFINERÍA DE CARTAGENA",
        "filtro": _filtro_ref_cartagena,
        "msg_sin_datos": "Sin tecnologías de refinería de Cartagena (UPSREF_CAR)",
        "agrupar_por": "FUEL",
        "color_fn": _color_por_grupo_fijo,
        "variable_default": "UseByTechnology",
    },
    "ref_barrancabermeja": {
        "titulo": "Refinería de Barrancabermeja - UseByTechnology",
        "figura": "Figura REF-BAR",
        "filename": "Fig_Ref_Barrancabermeja",
        "print": "REFINERÍA DE BARRANCABERMEJA",
        "filtro": _filtro_ref_barrancabermeja,
        "msg_sin_datos": "Sin tecnologías de refinería de Barrancabermeja (UPSREF_BAR)",
        "agrupar_por": "FUEL",
        "color_fn": _color_por_grupo_fijo,
        "variable_default": "UseByTechnology",
    },
    "ref_ambas": {
        "titulo": "Refinerías (Cartagena + Barrancabermeja) - UseByTechnology",
        "figura": "Figura REF-AMB",
        "filename": "Fig_Ref_Ambas",
        "print": "REFINERÍAS (CARTAGENA + BARRANCABERMEJA)",
        "filtro": _filtro_ref_ambas,
        "msg_sin_datos": "Sin tecnologías de refinería (UPSREF_CAR / UPSREF_BAR)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "allowedGroupings": ["TECNOLOGIA", "FUEL"],
        "variable_default": "UseByTechnology",
        "has_sub": True,
        "sub_filtro_label": "Crudo",
        "sub_filtros": ["con_crudo", "sin_crudo"],
    },
    "liquidos_prod_import": {
        "titulo": "Líquidos - Producción + Importación - ProductionByTechnology",
        "figura": "Figura LIQ-PROD",
        "filename": "Fig_Liquidos_Prod_Import",
        "print": "LÍQUIDOS: PRODUCCIÓN + IMPORTACIÓN",
        "filtro": _filtro_liquidos_produccion_importacion,
        "msg_sin_datos": "Sin tecnologías de líquidos (IMPDSL/IMPGSL/IMPJET/IMPLPG/UPSREF_CAR/UPSREF_BAR)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": _color_liquidos_import,
        "variable_default": "ProductionByTechnology",
    },
    "exp_liquidos": {
        "titulo": "Líquidos - Exportación - ProductionByTechnology",
        "figura": "Figura LIQ-EXP",
        "filename": "Fig_Liquidos_Export",
        "print": "LÍQUIDOS: EXPORTACIÓN",
        "filtro": _filtro_export_liquidos,
        "msg_sin_datos": "Sin exportaciones de líquidos (EXPDSL/EXPGSL/EXPJET/EXPLPG)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": _color_liquidos_import,
        "variable_default": "ProductionByTechnology",
        "allowedGroupings": ["TECNOLOGIA", "FUEL"],
        "soportaPareto": True,
        "soportaPorcentaje": True,
    },
    "imp_liquidos": {
        "titulo": "Líquidos - Importación - ProductionByTechnology",
        "figura": "Figura LIQ-IMP",
        "filename": "Fig_Liquidos_Import",
        "print": "LÍQUIDOS: IMPORTACIÓN",
        "filtro": _filtro_import_liquidos,
        "msg_sin_datos": "Sin importaciones de líquidos (IMPDSL/IMPGSL/IMPJET/IMPLNG/IMPLPG/IMPOIL)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": _color_liquidos_import,
        "variable_default": "ProductionByTechnology",
        "allowedGroupings": ["TECNOLOGIA", "FUEL"],
        "soportaPareto": True,
        "soportaPorcentaje": True,
    },
    # ═══════════════════════════════════════════════════════════════════
    # RESIDENCIAL
    # ═══════════════════════════════════════════════════════════════════
    "res_total": {
        "titulo": "Sector Residencial - Consumo Total - UseByTechnology",
        "figura": "Figura 30",
        "filename": "Fig30_Residencial_Total",
        "print": "SECTOR RESIDENCIAL (TOTAL)",
        "filtro": _filtro_residencial,
        "msg_sin_datos": "Sin tecnologías residenciales (DEMRES)",
        "agrupar_por": "TECNOLOGIA",
        "allowedGroupings": ["TECNOLOGIA", "FUEL"],
        "color_fn": generar_colores_tecnologias,
        "variable_default": "UseByTechnology",
    },
    "res_uso": {
        "titulo": "Sector Residencial - ProductionByTechnology",
        "figura": "Figura 31",
        "filename": "Fig31_Residencial_Uso",
        "print": "SECTOR RESIDENCIAL (POR USO)",
        "filtro": _filtro_residencial,
        "msg_sin_datos": "Sin tecnologías residenciales (DEMRES)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "variable_default": "ProductionByTechnology",
    },
    # ═══════════════════════════════════════════════════════════════════
    # INDUSTRIAL
    # ═══════════════════════════════════════════════════════════════════
    "ind_total": {
        "titulo": "Sector Industrial - Consumo Total - UseByTechnology",
        "figura": "Figura 40",
        "filename": "Fig40_Industrial_Total",
        "print": "SECTOR INDUSTRIAL (TOTAL)",
        "filtro": _filtro_industrial,
        "msg_sin_datos": "Sin tecnologías industriales (DEMIND)",
        "agrupar_por": "TECNOLOGIA",
        "allowedGroupings": ["TECNOLOGIA", "FUEL"],
        "color_fn": generar_colores_tecnologias,
        "variable_default": "UseByTechnology",
    },
    "ind_uso": {
        "titulo": "Sector Industrial - ProductionByTechnology",
        "figura": "Figura 41",
        "filename": "Fig41_Industrial_Uso",
        "print": "SECTOR INDUSTRIAL (POR USO)",
        "filtro": _filtro_industrial,
        "msg_sin_datos": "Sin tecnologías industriales (DEMIND)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "variable_default": "ProductionByTechnology",
    },
    # ═══════════════════════════════════════════════════════════════════
    # TRANSPORTE
    # ═══════════════════════════════════════════════════════════════════
    "tra_total": {
        "titulo": "Sector Transporte - Consumo Total - UseByTechnology",
        "figura": "Figura 50",
        "filename": "Fig50_Transporte_Total",
        "print": "SECTOR TRANSPORTE (TOTAL)",
        "filtro": _filtro_transporte,
        "msg_sin_datos": "Sin tecnologías de transporte (DEMTRA)",
        "agrupar_por": "TECNOLOGIA",
        "allowedGroupings": ["TECNOLOGIA", "FUEL"],
        "color_fn": generar_colores_tecnologias,
        "variable_default": "UseByTechnology",
    },
    "tra_uso": {
        "titulo": "Sector Transporte - ProductionByTechnology",
        "figura": "Figura 51",
        "filename": "Fig51_Transporte_Uso",
        "print": "SECTOR TRANSPORTE (POR USO)",
        "filtro": _filtro_transporte,
        "msg_sin_datos": "Sin tecnologías de transporte (DEMTRA)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "variable_default": "ProductionByTechnology",
    },
    # ═══════════════════════════════════════════════════════════════════
    # TERCIARIO
    # ═══════════════════════════════════════════════════════════════════
    "ter_total": {
        "titulo": "Sector Terciario - Consumo Total - UseByTechnology",
        "figura": "Figura 60",
        "filename": "Fig60_Terciario_Total",
        "print": "SECTOR TERCIARIO (TOTAL)",
        "filtro": _filtro_terciario,
        "msg_sin_datos": "Sin tecnologías terciarias (DEMTER)",
        "agrupar_por": "TECNOLOGIA",
        "allowedGroupings": ["TECNOLOGIA", "FUEL"],
        "color_fn": generar_colores_tecnologias,
        "variable_default": "UseByTechnology",
    },
    "ter_uso": {
        "titulo": "Sector Terciario - ProductionByTechnology",
        "figura": "Figura 61",
        "filename": "Fig61_Terciario_Uso",
        "print": "SECTOR TERCIARIO (POR USO)",
        "filtro": _filtro_terciario,
        "msg_sin_datos": "Sin tecnologías terciarias (DEMTER)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "variable_default": "ProductionByTechnology",
    },
    # ═══════════════════════════════════════════════════════════════════
    # OTROS SECTORES
    # ═══════════════════════════════════════════════════════════════════
    "otros_total": {
        "titulo": "Otros Sectores - Consumo Total - UseByTechnology",
        "figura": "Figura 70",
        "filename": "Fig70_Otros_Total",
        "print": "OTROS SECTORES",
        "filtro": _filtro_otros,
        "msg_sin_datos": "Sin tecnologías para el sector especificado",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "variable_default": "UseByTechnology",
    },
    # ═══════════════════════════════════════════════════════════════════
    # CAPACIDAD — CONFIGS UNIFICADOS (1 por sector)
    # ═══════════════════════════════════════════════════════════════════
    "cap_electricidad": {
        "titulo_base": "Matriz Eléctrica (Capacidad) - TotalCapacityAnnual",
        "figura_base": "CAP-ELEC",
        "filename_base": "Cap_Electricidad",
        "print_base": "CAPACIDAD - MATRIZ ELÉCTRICA",
        "filtro": _filtro_pwr,
        "msg_sin_datos": "Sin tecnologías de generación eléctrica (PWR)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": _color_electricidad,
        "es_capacidad": True,
        "variable_default": "TotalCapacityAnnual",
    },
    "cap_industrial": {
        "titulo_base": "Sector Industrial (Capacidad) - TotalCapacityAnnual",
        "figura_base": "CAP-IND",
        "filename_base": "Cap_Industrial",
        "print_base": "CAPACIDAD - SECTOR INDUSTRIAL",
        "filtro": _filtro_industrial,
        "msg_sin_datos": "Sin tecnologías industriales (DEMIND)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "es_capacidad": True,
        "variable_default": "TotalCapacityAnnual",
    },
    "cap_transporte": {
        "titulo_base": "Sector Transporte (Capacidad) - TotalCapacityAnnual",
        "figura_base": "CAP-TRA",
        "filename_base": "Cap_Transporte",
        "print_base": "CAPACIDAD - SECTOR TRANSPORTE",
        "filtro": _filtro_transporte,
        "msg_sin_datos": "Sin tecnologías de transporte (DEMTRA)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "es_capacidad": True,
        "variable_default": "TotalCapacityAnnual",
    },
    "cap_terciario": {
        "titulo_base": "Sector Terciario (Capacidad) - TotalCapacityAnnual",
        "figura_base": "CAP-TER",
        "filename_base": "Cap_Terciario",
        "print_base": "CAPACIDAD - SECTOR TERCIARIO",
        "filtro": _filtro_terciario,
        "msg_sin_datos": "Sin tecnologías terciarias (DEMTER)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "es_capacidad": True,
        "variable_default": "TotalCapacityAnnual",
    },
    "cap_otros": {
        "titulo_base": "Otros Sectores (Capacidad) - TotalCapacityAnnual",
        "figura_base": "CAP-OTROS",
        "filename_base": "Cap_Otros",
        "print_base": "CAPACIDAD - OTROS SECTORES",
        "filtro": _filtro_otros,
        "msg_sin_datos": "Sin tecnologías para el sector especificado",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "es_capacidad": True,
        "variable_default": "TotalCapacityAnnual",
    },
    # ═══════════════════════════════════════════════════════════════════
    # NUEVOS CONFIGS (Paso 1 — plan de implementación)
    # ═══════════════════════════════════════════════════════════════════
    "prd_electricidad": {
        "titulo_base": "Producción de Electricidad - ProductionByTechnology (%)",
        "figura_base": "PRD-ELEC",
        "filename_base": "Prd_Electricidad",
        "print_base": "PRODUCCIÓN ELÉCTRICA",
        "filtro": _filtro_pwr,
        "msg_sin_datos": "Sin tecnologías de generación eléctrica (PWR)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": _color_electricidad,
        "es_porcentaje": True,
        "variable_default": "ProductionByTechnology",
    },
    "elec_produccion": {
        "titulo": "Producción de Electricidad - ProductionByTechnology",
        "figura": "Figura 21",
        "filename": "Fig21_Produccion_Electricidad",
        "print": "PRODUCCIÓN DE ELECTRICIDAD",
        "filtro": _filtro_pwr,
        "msg_sin_datos": "Sin tecnologías de generación eléctrica (PWR)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": _color_electricidad,
        "variable_default": "ProductionByTechnology",
    },
    "factor_planta": {
        "titulo": "Factor de Planta - Generación Eléctrica",
        "figura": "FAC-PLT",
        "filename": "Factor_Planta",
        "print": "FACTOR DE PLANTA",
        "es_factor_planta": True,
        "filtro": _filtro_pwr,
        "msg_sin_datos": "Sin datos de capacidad o producción eléctrica (PWR)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": _color_electricidad,
        "variable_default": "TotalCapacityAnnual",
    },
    "elec_produccion_liquidos": {
        "titulo": "Generación Líquidos - ProductionByTechnology",
        "figura": "Figura ELEC-LIQ",
        "filename": "Fig_Elec_Liquidos",
        "print": "GENERACIÓN LÍQUIDOS",
        "filtro": _filtro_pwr_liquidos,
        "msg_sin_datos": "Sin generación eléctrica con combustibles líquidos (DSL/FOL/GSL/JET/LPG)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": _color_electricidad,
        "variable_default": "ProductionByTechnology",
        "soportaPareto": True,
        "soportaPorcentaje": True,
        "allowedGroupings": ["TECNOLOGIA", "FUEL"],
    },
    "elec_cap_liquidos": {
        "titulo_base": "Matriz Líquidos (Capacidad) - TotalCapacityAnnual",
        "figura_base": "CAP-ELEC-LIQ",
        "filename_base": "Cap_Elec_Liquidos",
        "print_base": "CAPACIDAD - LÍQUIDOS",
        "filtro": _filtro_pwr_liquidos,
        "msg_sin_datos": "Sin generación eléctrica con combustibles líquidos (DSL/FOL/GSL/JET/LPG)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": _color_electricidad,
        "es_capacidad": True,
        "variable_default": "TotalCapacityAnnual",
    },
    "elec_fp_liquidos": {
        "titulo": "Factor de Planta - Líquidos",
        "figura": "FAC-PLT-LIQ",
        "filename": "Factor_Planta_Liquidos",
        "print": "FACTOR DE PLANTA - LÍQUIDOS",
        "es_factor_planta": True,
        "filtro": _filtro_pwr_liquidos,
        "msg_sin_datos": "Sin datos de capacidad o producción para líquidos (PWR + DSL/FOL/GSL/JET/LPG)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": _color_electricidad,
        "variable_default": "TotalCapacityAnnual",
    },
    "elec_produccion_termica": {
        "titulo": "Generación Térmica - ProductionByTechnology",
        "figura": "Figura ELEC-TER",
        "filename": "Fig_Elec_Termica",
        "print": "GENERACIÓN TÉRMICA",
        "filtro": _filtro_pwr_termica,
        "msg_sin_datos": "Sin generación eléctrica con combustibles térmicos (NGS/BGS/COA)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": _color_electricidad,
        "variable_default": "ProductionByTechnology",
        "soportaPareto": True,
        "soportaPorcentaje": True,
        "allowedGroupings": ["TECNOLOGIA", "FUEL"],
    },
    "elec_cap_termica": {
        "titulo_base": "Matriz Térmica (Capacidad) - TotalCapacityAnnual",
        "figura_base": "CAP-ELEC-TER",
        "filename_base": "Cap_Elec_Termica",
        "print_base": "CAPACIDAD - TÉRMICA",
        "filtro": _filtro_pwr_termica,
        "msg_sin_datos": "Sin generación eléctrica con combustibles térmicos (NGS/BGS/COA)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": _color_electricidad,
        "es_capacidad": True,
        "variable_default": "TotalCapacityAnnual",
    },
    "elec_fp_termica": {
        "titulo": "Factor de Planta - Térmica",
        "figura": "FAC-PLT-TER",
        "filename": "Factor_Planta_Termica",
        "print": "FACTOR DE PLANTA - TÉRMICA",
        "es_factor_planta": True,
        "filtro": _filtro_pwr_termica,
        "msg_sin_datos": "Sin datos de capacidad o producción para térmica (PWR + NGS/BGS/COA)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": _color_electricidad,
        "variable_default": "TotalCapacityAnnual",
    },
    "con_total": {
        "titulo": "Sector Construcción - Consumo Total - UseByTechnology",
        "figura": "Figura 11",
        "filename": "Fig11_Construccion_Total",
        "print": "SECTOR CONSTRUCCIÓN",
        "filtro": _filtro_construccion,
        "msg_sin_datos": "Sin tecnologías de construcción (DEMCON)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "variable_default": "UseByTechnology",
    },
    "agf_total": {
        "titulo": "Sector Agroforestal - Consumo Total - UseByTechnology",
        "figura": "Figura 22",
        "filename": "Fig22_Agroforestal_Total",
        "print": "SECTOR AGROFORESTAL",
        "filtro": _filtro_agroforestal,
        "msg_sin_datos": "Sin tecnologías agroforestales (DEMAGF)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "variable_default": "UseByTechnology",
    },
    "min_total": {
        "titulo": "Sector Minería - Consumo Total - UseByTechnology",
        "figura": "Figura 24",
        "filename": "Fig24_Mineria_Total",
        "print": "SECTOR MINERÍA",
        "filtro": _filtro_mineria,
        "msg_sin_datos": "Sin tecnologías de minería (DEMMIN)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "variable_default": "UseByTechnology",
    },
    "coq_total": {
        "titulo": "Sector Coquerías - Consumo Total - UseByTechnology",
        "figura": "Figura 10",
        "filename": "Fig10_Coquerias_Total",
        "print": "SECTOR COQUERÍAS",
        "filtro": _filtro_coquerias,
        "msg_sin_datos": "Sin tecnologías de coquerías (DEMCOQ)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "variable_default": "UseByTechnology",
    },
    "solidos_import": {
        "titulo": "Sólidos - Importación - ProductionByTechnology",
        "figura": "Figura 23",
        "filename": "Fig23_Produccion_Solidos",
        "print": "PRODUCCIÓN E IMPORTACIÓN DE SÓLIDOS",
        "filtro": _filtro_solidos_import,
        "msg_sin_datos": "Sin tecnologías de sólidos (MINCOA / IMPCOA)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "variable_default": "ProductionByTechnology",
    },
    "solidos_flujos": {
        "titulo": "Sólidos - Importación/Exportación - ProductionByTechnology",
        "figura": "Figura 26",
        "filename": "Fig26_Import_Export_Solidos",
        "print": "FLUJOS DE SÓLIDOS",
        "filtro": _filtro_solidos_flujos,
        "msg_sin_datos": "Sin tecnologías de sólidos (MINCOA / IMPCOA / EXPCOA)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "variable_default": "ProductionByTechnology",
    },
    "solidos_extraccion": {
        "titulo": "Sólidos - Extracción - ProductionByTechnology",
        "figura": "Figura 25",
        "filename": "Fig25_Extraccion_Solidos",
        "print": "EXTRACCIÓN DE SÓLIDOS",
        "filtro": _filtro_solidos_extraccion,
        "msg_sin_datos": "Sin tecnologías de minería de sólidos (MINCOA)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "variable_default": "ProductionByTechnology",
    },
    "extraccion_min": {
        "titulo": "Minería - Extracción - ProductionByTechnology",
        "figura": "Figura 44",
        "filename": "Fig44_Extraccion_MIN",
        "print": "EXTRACCIÓN",
        "filtro": _filtro_extraccion_min,
        "msg_sin_datos": "Sin tecnologías de extracción (MIN*)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "variable_default": "ProductionByTechnology",
    },
    "ref_capacidad": {
        "titulo_base": "Capacidad de Refinación por Derivado",
        "figura_base": "Figura 27",
        "filename_base": "Fig27_Refineria_Capacidad",
        "print_base": "CAPACIDAD DE REFINERÍA",
        "filtro": _filtro_ref_total,
        "msg_sin_datos": "Sin tecnologías de refinería (UPSREF)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "es_capacidad": True,
        "variable_default": "TotalCapacityAnnual",
    },
    "saf_produccion": {
        "titulo": "SAF - Producción - ProductionByTechnology",
        "figura": "Figura 47",
        "filename": "Fig47_Produccion_SAF",
        "print": "PRODUCCIÓN SAF",
        "filtro": _filtro_saf_produccion,
        "msg_sin_datos": "Sin tecnologías SAF (UPSSAF / UPSBJS)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "variable_default": "ProductionByTechnology",
    },
    "cap_h2": {
        "titulo": "Hidrógeno - ProductionByTechnology",
        "figura": "Figura 32",
        "filename": "Fig32_Produccion_H2",
        "print": "PRODUCCIÓN DE HIDRÓGENO",
        "filtro": _filtro_h2,
        "msg_sin_datos": "Sin tecnologías que producen hidrógeno (FUEL=HDG/HDG002)",
        "agrupar_por": "TECNOLOGIA",
        # Paleta dedicada — verde para electrólisis (UPSALK/UPSPEM), gris para
        # SMR sin captura (UPSSMR), azul para SMR con CCS (UPSSMRCCS).
        "color_fn": _color_h2_produccion,
        "variable_default": "ProductionByTechnology",
    },
    "cap_electrolisis_verde": {
        "titulo_base": "Capacidad Total de Electrólisis Verde",
        "figura_base": "CAP-ELEC-VERDE",
        "filename_base": "Cap_Electrolisis_Verde",
        "print_base": "CAPACIDAD - ELECTRÓLISIS VERDE",
        "filtro": _filtro_electrolisis_verde,
        "msg_sin_datos": "Sin electrolizadores (UPSALK / UPSPEM)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": _color_electrolisis,
        "es_capacidad": True,
        "variable_default": "TotalCapacityAnnual",
    },
    "h2_consumo": {
        "titulo": "Hidrógeno - Consumo - UseByTechnology",
        "figura": "Figura 33",
        "filename": "Fig33_Consumo_H2",
        "print": "CONSUMO DE HIDRÓGENO",
        "filtro": _filtro_h2,
        "msg_sin_datos": "Sin tecnologías que consumen hidrógeno (FUEL=HDG/HDG002)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": _color_h2_consumo,
        "variable_default": "UseByTechnology",
    },
    "h2_produccion_verde": {
        "titulo": "Hidrógeno Producción (Verde/Azul/Gris) - ProductionByTechnology",
        "figura": "Figura H2-V1",
        "filename": "Fig_H2_Produccion_Verde",
        "print": "PRODUCCIÓN DE HIDRÓGENO (VERDE/AZUL/GRIS)",
        "filtro": _filtro_h2_verde_azul_gris,
        "msg_sin_datos": "Sin tecnologías UPSSMR/UPSSMRCCS/UPSPEM/UPSALK",
        "agrupar_por": "H2_PRODUCCION",
        "color_fn": _color_h2_verde_azul_gris,
        "variable_default": "ProductionByTechnology",
    },
    "ups_refinacion": {
        "titulo": "Upstream Refinación - ProductionByTechnology",
        "figura": "Figura 48",
        "filename": "Fig48_Upstream_Refinacion",
        "print": "UPSTREAM REFINACIÓN",
        "filtro": _filtro_ups_refinacion,
        "msg_sin_datos": "Sin tecnologías de upstream refinación (UPSSAF/UPSALK/UPSPEM)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "variable_default": "ProductionByTechnology",
    },
    "min_hidrocarburos": {
        "titulo": "Minería Hidrocarburos - ProductionByTechnology",
        "figura": "Figura 49",
        "filename": "Fig49_Mineria_Hidrocarburos",
        "print": "MINERÍA PETRÓLEO Y GAS",
        "filtro": _filtro_min_hidrocarburos,
        "msg_sin_datos": "Sin tecnologías de minería petróleo/gas (MINOIL/MINNGS)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "variable_default": "ProductionByTechnology",
    },
    "min_carbon": {
        "titulo": "Minería Carbón - ProductionByTechnology",
        "figura": "Figura 53",
        "filename": "Fig53_Mineria_Carbon",
        "print": "MINERÍA CARBÓN",
        "filtro": _filtro_min_carbon,
        "msg_sin_datos": "Sin tecnologías de minería de carbón (MINCOA)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "variable_default": "ProductionByTechnology",
    },
    "oferta_bioenergia": {
        "titulo": "Oferta Bioenergía - ProductionByTechnology",
        "figura": "Figura BIOENERGIA",
        "filename": "Fig_Bioenergia",
        "print": "OFERTA BIOENERGÍA",
        "filtro": _filtro_oferta_bioenergia,
        "msg_sin_datos": "Sin tecnologías de bioenergía",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": _color_bioenergia,
        "variable_default": "ProductionByTechnology",
    },
    "emisiones_total": {
        "titulo": "Emisiones - Total Anual - AnnualEmissions",
        "es_emision": True,
        "figura": "EMI-TOT",
        "filename": "Emisiones_Total",
        "print": "EMISIONES TOTALES",
        "filtro": None,
        "msg_sin_datos": "Sin datos de emisiones",
        "agrupar_por": "YEAR",
        "color_fn": None,
        "usa_columnas_tipadas": True,
        "variable_default": "AnnualEmissions",
    },
    "emisiones_sectorial": {
        "titulo": "Emisiones - Por Sector - AnnualTechnologyEmission",
        "es_emision": True,
        "figura": "EMI-SEC",
        "filename": "Emisiones_Sectorial",
        "print": "EMISIONES SECTORIALES",
        "filtro": None,
        "msg_sin_datos": "Sin datos de emisiones por tecnología",
        "agrupar_por": "SECTOR",
        "color_fn": _color_por_sector,
        "variable_default": "AnnualTechnologyEmission",
    },
    "emisiones_gei": {
        "titulo": "Emisiones GEI por Sector - AnnualTechnologyEmission",
        "es_emision": True,
        "figura": "EMI-GEI",
        "filename": "Emisiones_GEI",
        "print": "EMISIONES GEI POR SECTOR",
        "filtro": _filtro_gei,
        "msg_sin_datos": "Sin datos de emisiones GEI (EMIC02, EMICH4, EMIN2O)",
        "agrupar_por": "SECTOR",
        "color_fn": _color_por_sector,
        "variable_default": "AnnualTechnologyEmission",
    },
    "emisiones_contaminantes": {
        "titulo": "Emisiones Contaminantes Criterio - AnnualTechnologyEmission",
        "es_emision": True,
        "es_emision_kt": True,
        "figura": "EMI-CONT",
        "filename": "Emisiones_Contaminantes",
        "print": "EMISIONES CONTAMINANTES CRITERIO",
        "filtro": _filtro_contaminantes,
        "msg_sin_datos": "Sin datos de contaminantes criterio",
        "agrupar_por": "EMISION",
        "color_fn": _color_por_emision,
        "variable_default": "AnnualTechnologyEmission",
    },
    "emisiones_contaminantes_pct": {
        "titulo_base": "Emisiones Contaminantes Criterio (%)",
        "es_emision": True,
        "es_emision_kt": True,
        "es_porcentaje": True,
        "figura": "EMI-CONT-PCT",
        "filename": "Emisiones_Contaminantes_Pct",
        "print": "EMISIONES CONTAMINANTES CRITERIO (%)",
        "filtro": _filtro_contaminantes,
        "msg_sin_datos": "Sin datos de contaminantes criterio",
        "agrupar_por": "EMISION",
        "color_fn": _color_por_emision,
        "variable_default": "AnnualTechnologyEmission",
    },
    # ═══════════════════════════════════════════════════════════════════════════
    # CONSUMO POR COMBUSTIBLE — TODOS LOS SECTORES
    # ═══════════════════════════════════════════════════════════════════════════
    "dem_consumo_combustible": {
        "titulo": "Consumo por Sector ",
        "figura": "Figura DEM-COMB",
        "filename": "DEM_Consumo_Por_Combustible",
        "print": "CONSUMO POR COMBUSTIBLE — TODOS LOS SECTORES",
        "filtro": _filtro_demanda_por_combustible,
        "msg_sin_datos": "Sin tecnologías de demanda para el combustible seleccionado",
        "agrupar_por": "SECTOR",
        "color_fn": _color_por_sector,
        "tiene_sub_filtro": True,
        "label_sub_filtro": "Combustible",
        "variable_default": "UseByTechnology",
    },
    "dem_consumo_liquidos": {
        "titulo": "Consumo de Líquidos - Sectores de Demanda",
        "figura": "Figura LIQ-DEM",
        "filename": "DEM_Liquidos",
        "print": "CONSUMO DE LÍQUIDOS",
        "filtro": _filtro_consumo_liquidos,
        "msg_sin_datos": "Sin consumo de líquidos (DSL/FOL/GSL/JET/LPG)",
        "agrupar_por": "FUEL",
        "color_fn": _color_por_grupo_fijo,
        "variable_default": "UseByTechnology",
    },
    "dem_consumo_liquidos_total": {
        "titulo": "Consumo de Líquidos - Sectores de Demanda + Sector Eléctrico",
        "figura": "Figura LIQ-TOTAL",
        "filename": "DEM_Liquidos_Total",
        "print": "CONSUMO DE LÍQUIDOS — TODOS LOS SECTORES",
        "filtro": _filtro_liquidos_total,
        "msg_sin_datos": "Sin consumo de líquidos en demanda o generación eléctrica",
        "agrupar_por": "FUEL",
        "color_fn": _color_por_grupo_fijo,
        "variable_default": "UseByTechnology",
    },
    "dem_consumo_liquidos_exp_prod": {
        "titulo": "Producción de Líquidos — Demanda y Exportaciones",
        "figura": "Figura LIQ-DEM-EXP-PROD",
        "filename": "DEM_Liquidos_Demanda_Export_Prod",
        "print": "PRODUCCIÓN DE LÍQUIDOS — DEMANDA Y EXPORTACIONES",
        "filtro": _filtro_demanda_exportaciones_liquidos,
        "msg_sin_datos": "Sin producción de líquidos para demanda o exportaciones",
        "agrupar_por": "FUEL",
        "color_fn": _color_por_grupo_fijo,
        "variable_default": "ProductionByTechnology",
    },
    "dem_consumo_liquidos_exp_use": {
        "titulo": "Consumo de Líquidos — Demanda y Exportaciones",
        "figura": "Figura LIQ-DEM-EXP",
        "filename": "DEM_Liquidos_Demanda_Export",
        "print": "CONSUMO DE LÍQUIDOS — DEMANDA Y EXPORTACIONES",
        "filtro": _filtro_demanda_exportaciones_liquidos,
        "msg_sin_datos": "Sin consumo de líquidos en demanda o exportaciones",
        "agrupar_por": "FUEL",
        "color_fn": _color_por_grupo_fijo,
        "variable_default": "UseByTechnology",
    },
}
