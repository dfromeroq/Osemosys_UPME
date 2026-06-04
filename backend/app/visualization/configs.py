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
    _color_por_sector_gei,
    _color_por_emision,
    _color_electrolisis,
    _color_h2_produccion,
    _color_h2_consumo,
    _color_bioenergia,
    _color_gas_produccion,
    _color_liquidos_import,
    _color_por_modo,
    _color_ref_import,
)


# Modos de transporte por carretera (sub-filtro "CARRETERA")
ROAD_TRANSPORT_CODES = {"BUS", "MOT", "TCK", "STT", "LDV", "FWD", "TAX", "MIC"}

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
    # "IMPLNG",
    "IMPLPG",
    # "IMPOIL",
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
# AGRUPACIÓN DE TECNOLOGÍAS DEL SECTOR ELÉCTRICO
# ════════════════════════════════════════════════════════════════════════
#
# Algunas tecnologías son variantes de otras y, para las gráficas de
# generación y capacidad instalada del sector eléctrico, conviene mostrarlas
# agrupadas (sumadas) bajo la tecnología "padre". El alias se aplica DESPUÉS
# del filtro (`_filtro_pwr`) y ANTES del groupby/coloreo, para que la suma
# quede consolidada y la leyenda muestre solo el nombre del padre.
#
# Origen → Destino (display = label del destino):
#   PWRSOLRTP_ZNI → PWRSOLRTP   (Solar FV Residencial ZNI → Solar FV GD)
#   PWRJET        → PWRNGS      (Jet Fuel                → Gas Natural)
#   PWRLPG        → PWRNGS      (GLP                     → Gas Natural)
#   PWRNGS_CS     → PWRNGS      (Gas Natural Ciclo Simple → Gas Natural)
#   PWRNGS_CC     → PWRNGS      (Gas Natural Ciclo Combinado → Gas Natural)
#   PWRNGSCCS     → PWRNGS      (Gas Natural+CCS         → Gas Natural)
#   PWRHYDROR_NDC → PWRHYDROR   (Filo de Agua NDC        → Filo de Agua)
#   PWRSTD        → PWRDSL      (Gen Diésel Independiente → Diésel)
PWR_TECH_ALIASES: dict[str, str] = {
    "PWRSOLRTP_ZNI": "PWRSOLRTP",
    "PWRJET": "PWRNGS",
    "PWRLPG": "PWRNGS",
    "PWRNGS_CS": "PWRNGS",
    "PWRNGS_CC": "PWRNGS",
    "PWRNGSCCS": "PWRNGS",
    "PWRHYDROR_NDC": "PWRHYDROR",
    "PWRSTD": "PWRDSL",
}

# Configs (tipo) en los que se aplican los aliases anteriores. Limitamos a los
# tres charts principales del sector eléctrico para no afectar las vistas de
# detalle (líquidos/térmica/factor planta) donde el usuario quiere ver cada
# tecnología por separado.
CONFIGS_CON_ALIAS_PWR: frozenset[str] = frozenset(
    {
        "cap_electricidad",
        "prd_electricidad",
        "elec_produccion",
    }
)


# ════════════════════════════════════════════════════════════════════════
# FILTROS NOMBRADOS (reemplazan los lambdas del original)
# ════════════════════════════════════════════════════════════════════════


TECNOLOGIAS_GAS_CONSUMO = [
    "CTRNGS",
    "DEMAGFNGS",
    "DEMCONSNGS",
    "DEMINDNGSBOI",
    "DEMINDNGSBOICCS",
    "DEMINDNGSBOI_HIG",
    "DEMINDNGSBOI_LOW",
    "DEMINDNGSBOI_MID",
    "DEMINDNGSFUR",
    "DEMINDNGSFURCCS",
    "DEMINDNGSFURCSS",
    "DEMINDNGSFUR_HIG",
    "DEMINDNGSFUR_LOW",
    "DEMINDNGSFUR_MID",
    "DEMMININGS",
    "DEMNGSAUT",
    "DEMRESNGSCKN_HIG",
    "DEMRESNGSCKN_HIG_RUR",
    "DEMRESNGSCKN_HIG_URB",
    "DEMRESNGSCKN_LOW",
    "DEMRESNGSCKN_LOW_RUR",
    "DEMRESNGSCKN_LOW_URB",
    "DEMRESNGSCKN_MID",
    "DEMRESNGSCKN_MID_RUR",
    "DEMRESNGSCKN_MID_URB",
    "DEMRESNGSWHT_FOR_HIG_RUR",
    "DEMRESNGSWHT_FOR_HIG_URB",
    "DEMRESNGSWHT_FOR_LOW_RUR",
    "DEMRESNGSWHT_FOR_LOW_URB",
    "DEMRESNGSWHT_FOR_MID_RUR",
    "DEMRESNGSWHT_FOR_MID_URB",
    "DEMRESNGSWHT_LOW",
    "DEMRESNGSWHT_NAT_HIG_RUR",
    "DEMRESNGSWHT_NAT_HIG_URB",
    "DEMRESNGSWHT_NAT_LOW_RUR",
    "DEMRESNGSWHT_NAT_LOW_URB",
    "DEMTERNGSBOI_LOW",
    "DEMTERNGSCKN_HIG",
    "DEMTERNGSCKN_LOW",
    "DEMTRANGSBUS",
    "DEMTRANGSBUS_ART",
    "DEMTRANGSBUS_BIA",
    "DEMTRANGSBUS_IMU",
    "DEMTRANGSBUS_URB",
    "DEMTRANGSFWD",
    "DEMTRANGSLDV",
    "DEMTRANGSMIC",
    "DEMTRANGSMOT",
    "DEMTRANGSSTT",
    "DEMTRANGSTAX",
    "DEMTRANGSTCK",
    "DEMTRANGSTCK_C2P",
    "DEMTRANGSTCK_CSG",
    "GRDNGSDST",
    "GRDNGSTRN",
    "PWRNGS",
    "PWRNGSCCS",
    "PWRNGS_CC",
    "PWRNGS_CS",
]

COMBUSTIBLES_GAS_CONSUMO = ["NGS002", "NGS"]


def _filtro_gas_consumo(df, **kw):
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_GAS_CONSUMO)]
    # return df[df["FUEL"].isin(COMBUSTIBLES_GAS_CONSUMO)]


TECNOLOGIAS_GAS_PRODUCCION = ["UPSREG", "UPSREG_2", "MINNGS"]


def _filtro_gas_produccion(df, **kw):
    """Tecnologías de producción de gas (UPSREG / MINNGS)."""
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_GAS_PRODUCCION)]


TECNOLOGIAS_GAS_FLUJOS = ["IMPLNG", "EXPNGS"]


def _filtro_gas_flujos(df, **kw):
    """Importaciones y exportaciones de gas natural (IMPLNG, EXPNGS)."""
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_GAS_FLUJOS)]


TECNOLOGIAS_REFINERIAS = ["UPSREF_BAR", "UPSREF_CAR", "UPSREF_REF"]


def _filtro_ref_total(df, **kw):
    """Tecnologías de refinería (UPSREF)."""
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_REFINERIAS)]


TECNOLOGIAS_REFINERIAS_IMPORTACIONES = [
    "UPSREF_BAR",
    "UPSREF_CAR",
    "UPSREF_REF",
    "IMPDSL",
    "IMPGSL",
    "IMPJET",
    "IMPLPG",
]


def _filtro_ref_import(df, **kw):
    """Refinerías + importaciones."""
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_REFINERIAS_IMPORTACIONES)]


TECNOLOGIAS_REFINERIAS_CARTAGENA = ["UPSREF_CAR"]


def _filtro_ref_cartagena(df, **kw):
    """Refinería de Cartagena (UPSREF_CAR)."""
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_REFINERIAS_CARTAGENA)]


TECNOLOGIAS_REFINERIAS_BARRANCABERMEJA = ["UPSREF_BAR"]


def _filtro_ref_barrancabermeja(df, **kw):
    """Refinería de Barrancabermeja (UPSREF_BAR)."""
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_REFINERIAS_BARRANCABERMEJA)]


TECNOLOGIAS_REFINERIAS_BAR_CAR = [
    "UPSREF_BAR",
    "UPSREF_CAR",
]

COMBUSTIBLES_REFINERIA_CON_CRUDO = {
    # DSL
    "CONSDSL",
    "COQDSL",
    "CYRDSL",
    "DSL",
    "DSL002",
    "MINIDSL",
    # GSL
    "CONSGSL",
    "COQGSL",
    "CYRGSL",
    "GSL",
    "GSL002",
    "MINIGSL",
    # JET
    "JET",
    # LPG
    "CYRLPG",
    "LPG",
    "LPG002",
    # NGS
    "CONSNGS",
    "CYRNGS",
    "MININGS",
    "NGS",
    "NGS000",
    "NGS002",
    "NGSAUT",
    # ELC
    "AGFELC",
    "CONSELC",
    "CYRELC",
    "ELC",
    "ELC002",
    "ELC003",
    "ELC004",
    "ELCZNI",
    "INDOTH_ELC",
    "MINIELC",
    "NSEELC",
    "RESELC_ZNI",
    # OIL
    "OIL",
    "OIL002",
    "OILPAL",
    "OIL_1LIV",
    "OIL_2MID",
    "OIL_3PES",
}

COMBUSTIBLES_REFINERIA_SIN_CRUDO = COMBUSTIBLES_REFINERIA_CON_CRUDO - {
    "OIL_1LIV",
    "OIL_2MID",
    "OIL_3PES",
}


def _filtro_ref_ambas(df, sub_filtro=None, **kw):
    """Refinerías Cartagena + Barrancabermeja."""

    mask_tech = df["TECHNOLOGY"].isin(TECNOLOGIAS_REFINERIAS_BAR_CAR)

    if sub_filtro == "sin_crudo":
        return df[mask_tech & df["FUEL"].isin(COMBUSTIBLES_REFINERIA_SIN_CRUDO)]

    return df[mask_tech & df["FUEL"].isin(COMBUSTIBLES_REFINERIA_CON_CRUDO)]


TECNOLOGIAS_LIQUIDOS_PRODUCCION_IMPORTACION = [
    "IMPDSL",
    "IMPGSL",
    "IMPJET",
    "IMPLPG",
    "UPSREF_CAR",
    "UPSREF_BAR",
    "EXPDSL",
    "EXPGSL",
    "EXPLPG",
    "EXPJET",
]


def _filtro_liquidos_produccion_importacion(df, **kw):
    """Líquidos: importaciones (DSL, GSL, JET, LPG) + refinerías (CAR, BAR)."""
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_LIQUIDOS_PRODUCCION_IMPORTACION)]


TECNOLOGIAS_EXPORTACION_LIQUIDOS = ["EXPDSL", "EXPGSL", "EXPJET", "EXPLPG"]


def _filtro_export_liquidos(df, **kw):
    """Exportaciones de líquidos (EXPDSL, EXPGSL, EXPJET, EXPLPG)."""
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_EXPORTACION_LIQUIDOS)]


TECNOLOGIAS_IMPORTACION_LIQIDOS = ["IMPDSL", "IMPGSL", "IMPJET", "IMPLPG"]


def _filtro_import_liquidos(df, **kw):
    """Importaciones de líquidos (IMPDSL, IMPGSL, IMPJET, IMPLNG, IMPLPG, IMPOIL)."""
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_IMPORTACION_LIQIDOS)]


TECNOLOGIAS_IMPORTACION_EXPORTACION_CRUDO = ["IMPOIL", "EXPOIL"]


def _filtro_crudo_flujos(df, **kw):
    """Importaciones y exportaciones de crudo (IMPOIL, EXPOIL)."""
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_IMPORTACION_EXPORTACION_CRUDO)]


TECNOLOGIAS_EXPORTACION_CARBON = ["EXPCOA"]


def _filtro_exp_carbon(df, **kw):
    """Exportaciones de carbón (EXPCOA)."""
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_EXPORTACION_CARBON)]


TECNOLOGIAS_RECURSOS_CRUDO = ["MINOIL", "MINOIL_1LIV", "MINOIL_2MID", "MINOIL_3PES"]


def _filtro_recursos_crudo(df, **kw):
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_RECURSOS_CRUDO)]


TECNOLOGIAS_RECURSOS_GAS = ["MINNGS"]


def _filtro_recursos_gas(df, **kw):
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_RECURSOS_GAS)]


TECNOLOGIAS_RECURSOS_CARBON = ["MINCOA", "EXPCOA"]


def _filtro_recursos_carbon(df, **kw):
    """Carbón: tecnologías MINCOA/EXPCOA o combustible COA (excl. EXPCOA)."""
    if "TECHNOLOGY" not in df.columns:
        return df.iloc[0:0]

    mask = df["TECHNOLOGY"].isin(TECNOLOGIAS_RECURSOS_CARBON)

    if "FUEL" in df.columns:
        mask_coa = df["FUEL"] == "COA"
        mask_no_export = ~df["TECHNOLOGY"].isin(TECNOLOGIAS_EXPORTACION_CARBON)
        mask = mask | (mask_coa & mask_no_export)

    return df[mask]


TECNOLOGIAS_REFINERIAS_IMPORTACIONES_LIQUIDOS = [
    "UPSREF_BAR",
    "UPSREF_CAR",
    "IMPDSL",
    "IMPGSL",
    "IMPJET",
    "IMPLPG",
]


def _filtro_ref_produccion_importaciones(df, **kw):
    """Refinerías específicas + importaciones de combustibles líquidos refinados."""
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_REFINERIAS_IMPORTACIONES_LIQUIDOS)]


TECNOLOGIAS_RESIDENCIAL = []


TECNOLOGIAS_RESIDENCIALES = [
    "DEMRESBGSCKN_MID_RUR",
    "DEMRESELCAIR_HIG",
    "DEMRESELCAIR_LOW",
    "DEMRESELCAIR_PAR_HIG_RUR",
    "DEMRESELCAIR_PAR_LOW_RUR",
    "DEMRESELCAIR_PAR_LOW_URB",
    "DEMRESELCAIR_PAR_MID_RUR",
    "DEMRESELCAIR_PAR_MID_URB",
    "DEMRESELCAIR_POR_HIG_RUR",
    "DEMRESELCAIR_POR_HIG_URB",
    "DEMRESELCAIR_POR_LOW_RUR",
    "DEMRESELCAIR_POR_LOW_URB",
    "DEMRESELCAIR_POR_MID_RUR",
    "DEMRESELCAIR_POR_MID_URB",
    "DEMRESELCAIR_SPL_HIG_RUR",
    "DEMRESELCAIR_SPL_HIG_URB",
    "DEMRESELCAIR_SPL_LOW_RUR",
    "DEMRESELCAIR_SPL_LOW_URB",
    "DEMRESELCAIR_SPL_MID_RUR",
    "DEMRESELCAIR_SPL_MID_URB",
    "DEMRESELCCKN_HIG",
    "DEMRESELCCKN_HIG_RUR",
    "DEMRESELCCKN_HIG_URB",
    "DEMRESELCCKN_LOW",
    "DEMRESELCCKN_LOW_RUR",
    "DEMRESELCCKN_LOW_URB",
    "DEMRESELCCKN_MID",
    "DEMRESELCCKN_MID_RUR",
    "DEMRESELCCKN_MID_URB",
    "DEMRESELCFAN_HIG",
    "DEMRESELCFAN_HIG_RUR",
    "DEMRESELCFAN_HIG_URB",
    "DEMRESELCFAN_LOW",
    "DEMRESELCFAN_LOW_RUR",
    "DEMRESELCFAN_LOW_URB",
    "DEMRESELCFAN_MID",
    "DEMRESELCFAN_MID_RUR",
    "DEMRESELCFAN_MID_URB",
    "DEMRESELCILU_HIG",
    "DEMRESELCILU_HIG_RUR",
    "DEMRESELCILU_HIG_URB",
    "DEMRESELCILU_INC",
    "DEMRESELCILU_INC_RUR",
    "DEMRESELCILU_INC_URB",
    "DEMRESELCILU_LFC",
    "DEMRESELCILU_LFC_RUR",
    "DEMRESELCILU_LFC_URB",
    "DEMRESELCILU_LOW",
    "DEMRESELCILU_LOW_RUR",
    "DEMRESELCILU_LOW_URB",
    "DEMRESELCILU_MID",
    "DEMRESELCILU_MID_RUR",
    "DEMRESELCILU_MID_URB",
    "DEMRESELCOTH_HIG_RUR",
    "DEMRESELCOTH_HIG_URB",
    "DEMRESELCOTH_LOW",
    "DEMRESELCOTH_LOW_RUR",
    "DEMRESELCOTH_LOW_URB",
    "DEMRESELCOTH_MID_RUR",
    "DEMRESELCOTH_MID_URB",
    "DEMRESELCREF_HIG",
    "DEMRESELCREF_HIG_RUR",
    "DEMRESELCREF_HIG_URB",
    "DEMRESELCREF_LOW",
    "DEMRESELCREF_LOW_RUR",
    "DEMRESELCREF_LOW_URB",
    "DEMRESELCREF_MID",
    "DEMRESELCREF_MID_RUR",
    "DEMRESELCREF_MID_URB",
    "DEMRESELCTV_CRT",
    "DEMRESELCTV_CRT_RUR",
    "DEMRESELCTV_CRT_URB",
    "DEMRESELCTV_HIG_RUR",
    "DEMRESELCTV_HIG_URB",
    "DEMRESELCTV_LOW",
    "DEMRESELCTV_LOW_RUR",
    "DEMRESELCTV_LOW_URB",
    "DEMRESELCTV_MID",
    "DEMRESELCTV_MID_RUR",
    "DEMRESELCTV_MID_URB",
    "DEMRESELCWHT_DUC_HIG_RUR",
    "DEMRESELCWHT_DUC_HIG_URB",
    "DEMRESELCWHT_DUC_LOW",
    "DEMRESELCWHT_DUC_LOW_RUR",
    "DEMRESELCWHT_DUC_LOW_URB",
    "DEMRESELCWHT_DUC_MID",
    "DEMRESELCWHT_DUC_MID_RUR",
    "DEMRESELCWHT_DUC_MID_URB",
    "DEMRESELCWHT_PAS_HIG_RUR",
    "DEMRESELCWHT_PAS_HIG_URB",
    "DEMRESELCWHT_PAS_LOW",
    "DEMRESELCWHT_PAS_LOW_RUR",
    "DEMRESELCWHT_PAS_LOW_URB",
    "DEMRESELCWHT_PAS_MID",
    "DEMRESELCWHT_PAS_MID_RUR",
    "DEMRESELCWHT_PAS_MID_URB",
    "DEMRESELCWHT_TAN_HIG_RUR",
    "DEMRESELCWHT_TAN_HIG_URB",
    "DEMRESELCWHT_TAN_LOW",
    "DEMRESELCWHT_TAN_LOW_RUR",
    "DEMRESELCWHT_TAN_LOW_URB",
    "DEMRESELCWHT_TAN_MID",
    "DEMRESELCWHT_TAN_MID_RUR",
    "DEMRESELCWHT_TAN_MID_URB",
    "DEMRESELCWSH_HIG",
    "DEMRESELCWSH_HIG_RUR",
    "DEMRESELCWSH_HIG_URB",
    "DEMRESELCWSH_LOW",
    "DEMRESELCWSH_LOW_RUR",
    "DEMRESELCWSH_LOW_URB",
    "DEMRESELCWSH_MID",
    "DEMRESELCWSH_MID_RUR",
    "DEMRESELCWSH_MID_URB",
    "DEMRESLPGCKN_HIG_RUR",
    "DEMRESLPGCKN_HIG_URB",
    "DEMRESLPGCKN_LOW",
    "DEMRESLPGCKN_LOW_RUR",
    "DEMRESLPGCKN_LOW_URB",
    "DEMRESLPGCKN_MID_RUR",
    "DEMRESLPGCKN_MID_URB",
    "DEMRESNGSCKN_HIG",
    "DEMRESNGSCKN_HIG_RUR",
    "DEMRESNGSCKN_HIG_URB",
    "DEMRESNGSCKN_LOW",
    "DEMRESNGSCKN_LOW_RUR",
    "DEMRESNGSCKN_LOW_URB",
    "DEMRESNGSCKN_MID",
    "DEMRESNGSCKN_MID_RUR",
    "DEMRESNGSCKN_MID_URB",
    "DEMRESNGSWHT_FOR_HIG_RUR",
    "DEMRESNGSWHT_FOR_HIG_URB",
    "DEMRESNGSWHT_FOR_LOW_RUR",
    "DEMRESNGSWHT_FOR_LOW_URB",
    "DEMRESNGSWHT_FOR_MID_RUR",
    "DEMRESNGSWHT_FOR_MID_URB",
    "DEMRESNGSWHT_LOW",
    "DEMRESNGSWHT_NAT_HIG_RUR",
    "DEMRESNGSWHT_NAT_HIG_URB",
    "DEMRESNGSWHT_NAT_LOW_RUR",
    "DEMRESNGSWHT_NAT_LOW_URB",
    "DEMRESWOOCKN_HIG_RUR",
    "DEMRESWOOCKN_HIG_URB",
    "DEMRESWOOCKN_LOW",
    "DEMRESWOOCKN_LOW_RUR",
    "DEMRESWOOCKN_LOW_URB",
    "DEMRESWOOCKN_MID",
    "DEMRESWOOCKN_MID_RUR",
    "DEMRESWOOCKN_MID_URB",
    "DEMRESZNIBGSCKN_MID",
    "DEMRESZNIELCCKN_LOW",
    "DEMRESZNIELC_LOW",
    "DEMRESZNILPGCKN_LOW",
    "DEMRESZNILPGCKN_MID",
    "DEMRESZNIWOOCKN_LOW",
    "DEMRES_MEDPVA_URB",
]


TEC_RES_URB = [t for t in TECNOLOGIAS_RESIDENCIALES if t.endswith("_URB")]
TEC_RES_RUR = [t for t in TECNOLOGIAS_RESIDENCIALES if t.endswith("_RUR")]
TEC_RES_ZNI = [t for t in TECNOLOGIAS_RESIDENCIALES if t.endswith("_ZNI")]


def _filtro_residencial(df, sub_filtro=None, loc=None, **kw):

    mask = df["TECHNOLOGY"].isin(TECNOLOGIAS_RESIDENCIALES)

    if sub_filtro:
        mask &= df["TECHNOLOGY"].isin(
            [t for t in TECNOLOGIAS_RESIDENCIALES if sub_filtro in t]
        )

    if loc == "URB":
        mask &= df["TECHNOLOGY"].isin(TEC_RES_URB)

    elif loc == "RUR":
        mask &= df["TECHNOLOGY"].isin(TEC_RES_RUR)

    elif loc == "ZNI":
        mask &= df["TECHNOLOGY"].isin(TEC_RES_ZNI)

    return df[mask]


TECNOLOGIAS_INDUSTRIALES = [
    "DEMINDAUTBOI",
    "DEMINDAUTFUR",
    "DEMINDBAGBOI",
    "DEMINDBAGBOI_HIG",
    "DEMINDBAGBOI_LOW",
    "DEMINDBAGBOI_MID",
    "DEMINDBAGFUR",
    "DEMINDBAGFURCCS",
    "DEMINDBAGFUR_HIG",
    "DEMINDBAGFUR_LOW",
    "DEMINDBAGFUR_MID",
    "DEMINDBGSBOI_HIG",
    "DEMINDBGSBOI_LOW",
    "DEMINDBGSBOI_MID",
    "DEMINDBGSFUR_HIG",
    "DEMINDBGSFUR_LOW",
    "DEMINDBGSFUR_MID",
    "DEMINDCOABOI",
    "DEMINDCOABOICCS",
    "DEMINDCOABOI_HIG",
    "DEMINDCOABOI_LOW",
    "DEMINDCOABOI_MID",
    "DEMINDCOAFUR",
    "DEMINDCOAFURCCS",
    "DEMINDCOAFUR_HIG",
    "DEMINDCOAFUR_LOW",
    "DEMINDCOAFUR_MID",
    "DEMINDCOAOTH_LOW",
    "DEMINDDSLBOI_HIG",
    "DEMINDDSLBOI_LOW",
    "DEMINDDSLBOI_MID",
    "DEMINDDSLFUR_HIG",
    "DEMINDDSLFUR_LOW",
    "DEMINDDSLFUR_MID",
    "DEMINDELCAIR_HIG",
    "DEMINDELCAIR_LOW",
    "DEMINDELCAIR_MID",
    "DEMINDELCBOI",
    "DEMINDELCBOI_HIG",
    "DEMINDELCBOI_LOW",
    "DEMINDELCBOI_MID",
    "DEMINDELCFUR",
    "DEMINDELCFUR_HIG",
    "DEMINDELCFUR_LOW",
    "DEMINDELCFUR_MID",
    "DEMINDELCILU_HIG",
    "DEMINDELCILU_LOW",
    "DEMINDELCILU_MID",
    "DEMINDELCMPW",
    "DEMINDELCMPW_HIG",
    "DEMINDELCMPW_LOW",
    "DEMINDELCMPW_MID",
    "DEMINDELCOTH_HIG",
    "DEMINDELCOTH_LOW",
    "DEMINDELCOTH_MID",
    "DEMINDELCREF_HIG",
    "DEMINDELCREF_LOW",
    "DEMINDELCREF_MID",
    "DEMINDFOLOTH_LOW",
    "DEMINDHDGBOI",
    "DEMINDHDGBOI_HIG",
    "DEMINDHDGBOI_LOW",
    "DEMINDHDGFUR",
    "DEMINDLPGBOI_HIG",
    "DEMINDLPGBOI_LOW",
    "DEMINDLPGBOI_MID",
    "DEMINDLPGFUR_HIG",
    "DEMINDLPGFUR_LOW",
    "DEMINDLPGFUR_MID",
    "DEMINDNGSBOI",
    "DEMINDNGSBOICCS",
    "DEMINDNGSBOI_HIG",
    "DEMINDNGSBOI_LOW",
    "DEMINDNGSBOI_MID",
    "DEMINDNGSFUR",
    "DEMINDNGSFURCCS",
    "DEMINDNGSFURCSS",
    "DEMINDNGSFUR_HIG",
    "DEMINDNGSFUR_LOW",
    "DEMINDNGSFUR_MID",
    "DEMINDWASBOI_HIG",
    "DEMINDWASBOI_LOW",
    "DEMINDWASBOI_MID",
    "DEMINDWASFUR_HIG",
    "DEMINDWASFUR_LOW",
    "DEMINDWASFUR_MID",
]


def _filtro_industrial(df, sub_filtro=None, **kw):

    mask = df["TECHNOLOGY"].isin(TECNOLOGIAS_INDUSTRIALES)

    if sub_filtro:
        mask &= df["TECHNOLOGY"].isin(
            [t for t in TECNOLOGIAS_INDUSTRIALES if sub_filtro in t]
        )

    return df[mask]


TECNOLOGIAS_TRANSPORTE = [
    "DEMTRADSLBOT",
    "DEMTRADSLBUS",
    "DEMTRADSLBUS_ART",
    "DEMTRADSLBUS_BIA",
    "DEMTRADSLBUS_IMU",
    "DEMTRADSLBUS_URB",
    "DEMTRADSLFWD",
    "DEMTRADSLLDV",
    "DEMTRADSLMIC",
    "DEMTRADSLMOT",
    "DEMTRADSLSHP",
    "DEMTRADSLSTT",
    "DEMTRADSLTAX",
    "DEMTRADSLTCK",
    "DEMTRADSLTCK_C2P",
    "DEMTRADSLTCK_CSG",
    "DEMTRAELCBOT",
    "DEMTRAELCBUS",
    "DEMTRAELCBUS_ART",
    "DEMTRAELCBUS_BIA",
    "DEMTRAELCBUS_IMU",
    "DEMTRAELCBUS_URB",
    "DEMTRAELCFWD",
    "DEMTRAELCLDV",
    "DEMTRAELCMET",
    "DEMTRAELCMIC",
    "DEMTRAELCMOT",
    "DEMTRAELCSTT",
    "DEMTRAELCTAX",
    "DEMTRAELCTCK",
    "DEMTRAELCTCK_C2P",
    "DEMTRAELCTCK_CSG",
    "DEMTRAFOLSHP",
    "DEMTRAGSLBOT",
    "DEMTRAGSLBUS",
    "DEMTRAGSLBUS_ART",
    "DEMTRAGSLBUS_IMU",
    "DEMTRAGSLFWD",
    "DEMTRAGSLLDV",
    "DEMTRAGSLMIC",
    "DEMTRAGSLMOT",
    "DEMTRAGSLSTT",
    "DEMTRAGSLTAX",
    "DEMTRAGSLTCK",
    "DEMTRAGSLTCK_C2P",
    "DEMTRAHDGBUS",
    "DEMTRAHDGBUS_IMU",
    "DEMTRAHDGBUS_URB",
    "DEMTRAHDGFWD",
    "DEMTRAHDGLDV",
    "DEMTRAHDGMIC",
    "DEMTRAHDGMOT",
    "DEMTRAHDGSTT",
    "DEMTRAHDGTAX",
    "DEMTRAHDGTCK",
    "DEMTRAHDGTCK_CSG",
    "DEMTRAHEVFWD",
    "DEMTRAHEVLDV",
    "DEMTRAHYBFWD",
    "DEMTRAHYBLDV",
    "DEMTRAHYBTAX",
    "DEMTRAHYBTCK",
    "DEMTRAJETAIR",
    "DEMTRAJETAVI",
    "DEMTRAJETSAFAVI",
    "DEMTRANGSBUS",
    "DEMTRANGSBUS_ART",
    "DEMTRANGSBUS_BIA",
    "DEMTRANGSBUS_IMU",
    "DEMTRANGSBUS_URB",
    "DEMTRANGSFWD",
    "DEMTRANGSLDV",
    "DEMTRANGSMIC",
    "DEMTRANGSMOT",
    "DEMTRANGSSTT",
    "DEMTRANGSTAX",
    "DEMTRANGSTCK",
    "DEMTRANGSTCK_C2P",
    "DEMTRANGSTCK_CSG",
    "DEMTRAPHEVFWD",
    "DEMTRAPHEVLDV",
    "DEMTRAPHEVTAX",
]

TECNOLOGIAS_TRANSPORTE_CARRETERA = [
    "DEMTRADSLBUS",
    "DEMTRADSLBUS_ART",
    "DEMTRADSLBUS_BIA",
    "DEMTRADSLBUS_IMU",
    "DEMTRADSLBUS_URB",
    "DEMTRADSLFWD",
    "DEMTRADSLLDV",
    "DEMTRADSLMIC",
    "DEMTRADSLMOT",
    "DEMTRADSLSTT",
    "DEMTRADSLTAX",
    "DEMTRADSLTCK",
    "DEMTRADSLTCK_C2P",
    "DEMTRADSLTCK_CSG",
    "DEMTRAELCBUS",
    "DEMTRAELCBUS_ART",
    "DEMTRAELCBUS_BIA",
    "DEMTRAELCBUS_IMU",
    "DEMTRAELCBUS_URB",
    "DEMTRAELCFWD",
    "DEMTRAELCLDV",
    "DEMTRAELCMIC",
    "DEMTRAELCMOT",
    "DEMTRAELCSTT",
    "DEMTRAELCTAX",
    "DEMTRAELCTCK",
    "DEMTRAELCTCK_C2P",
    "DEMTRAELCTCK_CSG",
    "DEMTRAGSLBUS",
    "DEMTRAGSLBUS_ART",
    "DEMTRAGSLBUS_IMU",
    "DEMTRAGSLFWD",
    "DEMTRAGSLLDV",
    "DEMTRAGSLMIC",
    "DEMTRAGSLMOT",
    "DEMTRAGSLSTT",
    "DEMTRAGSLTAX",
    "DEMTRAGSLTCK",
    "DEMTRAGSLTCK_C2P",
    "DEMTRAHDGBUS",
    "DEMTRAHDGBUS_IMU",
    "DEMTRAHDGBUS_URB",
    "DEMTRAHDGFWD",
    "DEMTRAHDGLDV",
    "DEMTRAHDGMIC",
    "DEMTRAHDGMOT",
    "DEMTRAHDGSTT",
    "DEMTRAHDGTAX",
    "DEMTRAHDGTCK",
    "DEMTRAHDGTCK_CSG",
    "DEMTRANGSBUS",
    "DEMTRANGSBUS_ART",
    "DEMTRANGSBUS_BIA",
    "DEMTRANGSBUS_IMU",
    "DEMTRANGSBUS_URB",
    "DEMTRANGSFWD",
    "DEMTRANGSLDV",
    "DEMTRANGSMIC",
    "DEMTRANGSMOT",
    "DEMTRANGSSTT",
    "DEMTRANGSTAX",
    "DEMTRANGSTCK",
    "DEMTRANGSTCK_C2P",
    "DEMTRANGSTCK_CSG",
    "DEMTRAPHEVLDV",
]


def _filtro_transporte(df, sub_filtro=None, **kw):

    mask = df["TECHNOLOGY"].isin(TECNOLOGIAS_TRANSPORTE)

    if sub_filtro == "CARRETERA":
        mask &= df["TECHNOLOGY"].isin(TECNOLOGIAS_TRANSPORTE_CARRETERA)

    elif sub_filtro:
        mask &= df["TECHNOLOGY"].isin(
            [t for t in TECNOLOGIAS_TRANSPORTE if sub_filtro in t]
        )

    return df[mask]


TECNOLOGIAS_TRANSPORTE_POR_MODO = [
    # ROAD (carretera)
    "DEMTRADSLBUS",
    "DEMTRADSLBUS_ART",
    "DEMTRADSLBUS_BIA",
    "DEMTRADSLBUS_IMU",
    "DEMTRADSLBUS_URB",
    "DEMTRADSLFWD",
    "DEMTRADSLLDV",
    "DEMTRADSLMIC",
    "DEMTRADSLMOT",
    "DEMTRADSLSTT",
    "DEMTRADSLTAX",
    "DEMTRADSLTCK",
    "DEMTRADSLTCK_C2P",
    "DEMTRADSLTCK_CSG",
    "DEMTRAELCBUS",
    "DEMTRAELCBUS_ART",
    "DEMTRAELCBUS_BIA",
    "DEMTRAELCBUS_IMU",
    "DEMTRAELCBUS_URB",
    "DEMTRAELCFWD",
    "DEMTRAELCLDV",
    "DEMTRAELCMET",
    "DEMTRAELCMIC",
    "DEMTRAELCMOT",
    "DEMTRAELCSTT",
    "DEMTRAELCTAX",
    "DEMTRAELCTCK",
    "DEMTRAELCTCK_C2P",
    "DEMTRAELCTCK_CSG",
    "DEMTRAGSLBUS",
    "DEMTRAGSLBUS_ART",
    "DEMTRAGSLBUS_IMU",
    "DEMTRAGSLFWD",
    "DEMTRAGSLLDV",
    "DEMTRAGSLMIC",
    "DEMTRAGSLMOT",
    "DEMTRAGSLSTT",
    "DEMTRAGSLTAX",
    "DEMTRAGSLTCK",
    "DEMTRAGSLTCK_C2P",
    "DEMTRAHDGBUS",
    "DEMTRAHDGBUS_IMU",
    "DEMTRAHDGBUS_URB",
    "DEMTRAHDGFWD",
    "DEMTRAHDGLDV",
    "DEMTRAHDGMIC",
    "DEMTRAHDGMOT",
    "DEMTRAHDGSTT",
    "DEMTRAHDGTAX",
    "DEMTRAHDGTCK",
    "DEMTRAHDGTCK_CSG",
    "DEMTRANGSBUS",
    "DEMTRANGSBUS_ART",
    "DEMTRANGSBUS_BIA",
    "DEMTRANGSBUS_IMU",
    "DEMTRANGSBUS_URB",
    "DEMTRANGSFWD",
    "DEMTRANGSLDV",
    "DEMTRANGSMIC",
    "DEMTRANGSMOT",
    "DEMTRANGSSTT",
    "DEMTRANGSTAX",
    "DEMTRANGSTCK",
    "DEMTRANGSTCK_C2P",
    "DEMTRANGSTCK_CSG",
    # OTROS MODOS
    "DEMTRAHEVFWD",
    "DEMTRAHEVLDV",
    "DEMTRAHYBFWD",
    "DEMTRAHYBLDV",
    "DEMTRAHYBTAX",
    "DEMTRAHYBTCK",
    # AVIACIÓN
    "DEMTRAJETAIR",
    "DEMTRAJETAVI",
    "DEMTRAJETSAFAVI",
    # FERROCARRIL / METRO
    "DEMTRAELCMET",
    # MARÍTIMO
    "DEMTRAFOLSHP",
]


def _filtro_transporte_por_modo(df, **kw):
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_TRANSPORTE)]


TECNOLOGIAS_TERCIARIO = [
    "DEMTERBGSCKN_HIG",
    "DEMTERBGSCKN_LOW",
    "DEMTERBGSCKN_MID",
    "DEMTERELCACL_HIG",
    "DEMTERELCACL_LOW",
    "DEMTERELCACL_MID",
    "DEMTERELCAIR_CEN_HIG",
    "DEMTERELCAIR_CEN_LOW",
    "DEMTERELCAIR_CEN_MID",
    "DEMTERELCAIR_HIG",
    "DEMTERELCAIR_LOW",
    "DEMTERELCAIR_SPL_HIG",
    "DEMTERELCAIR_SPL_LOW",
    "DEMTERELCAIR_SPL_MID",
    "DEMTERELCBOI",
    "DEMTERELCCKN_HIG",
    "DEMTERELCCKN_LOW",
    "DEMTERELCCKN_MID",
    "DEMTERELCDATA",
    "DEMTERELCFAN_HIG",
    "DEMTERELCFAN_LOW",
    "DEMTERELCFAN_MID",
    "DEMTERELCILU_CIA",
    "DEMTERELCILU_HAL",
    "DEMTERELCILU_HIG",
    "DEMTERELCILU_LFC",
    "DEMTERELCILU_LOW",
    "DEMTERELCILU_MID",
    "DEMTERELCILU_VAP",
    "DEMTERELCMPW_HIG",
    "DEMTERELCMPW_LOW",
    "DEMTERELCMPW_MID",
    "DEMTERELCOTH",
    "DEMTERELCOTH_HIG",
    "DEMTERELCOTH_LOW",
    "DEMTERELCOTH_MID",
    "DEMTERELCREF_AUC_HIG",
    "DEMTERELCREF_AUC_LOW",
    "DEMTERELCREF_AUC_MID",
    "DEMTERELCREF_CEN_HIG",
    "DEMTERELCREF_CEN_LOW",
    "DEMTERELCREF_CEN_MID",
    "DEMTERELCREF_HIG",
    "DEMTERELCREF_LOW",
    "DEMTERHDGCKN",
    "DEMTERLGPCKN_LOW",
    "DEMTERLPGCKN_HIG",
    "DEMTERLPGCKN_MID",
    "DEMTERNGSBOI_LOW",
    "DEMTERNGSCKN_HIG",
    "DEMTERNGSCKN_LOW",
]


def _filtro_terciario(df, sub_filtro=None, **kw):
    mask = df["TECHNOLOGY"].isin(TECNOLOGIAS_TERCIARIO)

    if sub_filtro:
        mask &= df["TECHNOLOGY"].isin(
            [t for t in TECNOLOGIAS_TERCIARIO if sub_filtro in t]
        )

    return df[mask]


TECNOLOGIAS_PWR = [
    "PWRAFR",
    "PWRAFRCCS",
    "PWRBGS",
    "PWRCOA",
    "PWRCOACCS",
    "PWRCOG",
    "PWRCOGBAG",
    "PWRCOGCOF",
    "PWRCOGHUS",
    "PWRCOGMAZ",
    "PWRCOGRAQ",
    "PWRCOGRCE",
    "PWRCSP",
    "PWRDAM",
    "PWRDSL",
    "PWRDST",
    "PWRFOIL",
    "PWRGEO",
    "PWRHYDDAM",
    "PWRHYDROR",
    "PWRHYDROR_NDC",
    "PWRJET",
    "PWRLPG",
    "PWRNGS",
    "PWRNGSCCS",
    "PWRNGS_CC",
    "PWRNGS_CS",
    "PWRNUC",
    "PWROFIXW",
    "PWROFLOW",
    "PWRONW",
    "PWRROR",
    "PWRSOL",
    "PWRSOLBAT",
    "PWRSOLRTP",
    "PWRSOLRTP_IND",
    "PWRSOLRTP_ZNI",
    "PWRSOLUGE",
    "PWRSOLUGE_BAT",
    "PWRSOLUPE",
    "PWRSTD",
    "PWRWAS",
    "PWRWAS002",
    "PWRWASAGR",
    "PWRWNDOFS_FIX",
    "PWRWNDOFS_FLO",
    "PWRWNDONS",
    "PWRWOO",
    "PWRWOOCCS",
]


def _filtro_pwr(df, **kw):
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_PWR)]


TECNOLOGIAS_PWR_LIQUIDOS = ["PWRDSL", "PWRFOIL", "PWRGSL", "PWRJET", "PWRLPG"]


def _filtro_pwr_liquidos(df, **kw):
    """Generación eléctrica con combustibles líquidos (PWRDSL, PWRFOL, PWRGSL, PWRJET, PWRLPG).

    Filtra por prefijo de TECHNOLOGY porque el campo FUEL en ProductionByTechnology
    contiene el combustible de salida (ELC), no el de entrada.
    """
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_PWR_LIQUIDOS)]


TECNOLOGIAS_PWR_TERMICAS = [
    "PWRNGS",
    "PWRNGSCCS",
    "PWRNGS_CC",
    "PWRNGS_CS",
    "PWRBGS",
    "PWRCOA",
    "PWRCOACCS",
]


def _filtro_pwr_termica(df, **kw):
    """Generación eléctrica con combustibles térmicos (PWRNGS, PWRBGS, PWRCOA).

    Filtra por prefijo de TECHNOLOGY porque el campo FUEL en ProductionByTechnology
    contiene el combustible de salida (ELC), no el de entrada.
    """
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_PWR_TERMICAS)]


TECNOLOGIAS_CONSTRUCCION = [
    "DEMCONSDSL",
    "DEMCONSELC",
    "DEMCONSGSL",
    "DEMCONSNGS",
]


def _filtro_construccion(df, sub_filtro=None, **kw):
    mask = df["TECHNOLOGY"].isin(TECNOLOGIAS_CONSTRUCCION)

    if sub_filtro:
        mask &= df["TECHNOLOGY"].isin(
            [t for t in TECNOLOGIAS_CONSTRUCCION if sub_filtro in t]
        )

    return df[mask]


TECNOLOGIAS_AGROFORESTAL = [
    "DEMAGFDSL",
    "DEMAGFELC",
    "DEMAGFGSL",
    "DEMAGFNGS",
    "DEMAGFTER",
    "DEMAGFWOO",
]


def _filtro_agroforestal(df, sub_filtro=None, **kw):
    mask = df["TECHNOLOGY"].isin(TECNOLOGIAS_AGROFORESTAL)

    if sub_filtro:
        mask &= df["TECHNOLOGY"].isin(
            [t for t in TECNOLOGIAS_AGROFORESTAL if sub_filtro in t]
        )

    return df[mask]


TECNOLOGIAS_MINERIA = [
    "DEMMINIDSL",
    "DEMMINIELC",
    "DEMMINIGSL",
    "DEMMININGS",
]


def _filtro_mineria(df, sub_filtro=None, **kw):
    mask = df["TECHNOLOGY"].isin(TECNOLOGIAS_MINERIA)

    if sub_filtro:
        mask &= df["TECHNOLOGY"].isin(
            [t for t in TECNOLOGIAS_MINERIA if sub_filtro in t]
        )

    return df[mask]


TECNOLOGIAS_COQUERIAS = [
    "DEMCOQDSL",
    "DEMCOQGSL",
]


def _filtro_coquerias(df, sub_filtro=None, **kw):
    mask = df["TECHNOLOGY"].isin(TECNOLOGIAS_COQUERIAS)

    if sub_filtro:
        mask &= df["TECHNOLOGY"].isin(
            [t for t in TECNOLOGIAS_COQUERIAS if sub_filtro in t]
        )

    return df[mask]


TECNOLOGIAS_IMPORTACION_SOLIDOS = ["MINCOA", "IMPCOA"]


def _filtro_solidos_import(df, **kw):
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_IMPORTACION_SOLIDOS)]


TECNOLOGIAS_IMPORTACION_EXPORTACION_SOLIDOS = ["MINCOA", "IMPCOA", "EXPCOA"]


def _filtro_solidos_flujos(df, **kw):
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_IMPORTACION_EXPORTACION_SOLIDOS)]


TECNOLOGIAS_EXTRACCION_SOLIDOS = ["MINCOA"]


def _filtro_solidos_extraccion(df, **kw):
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_EXTRACCION_SOLIDOS)]


TECNOLOGIAS_EXTRACCION_MINERIA = [
    "MINBAG",
    "MINOPL",
    "MINWAS",
    "MINWAS_ORG",
    "MINAFR",
    "MINSGC",
    "MINWOO",
    "MINCOA",
]


def _filtro_extraccion_min(df, **kw):
    """Tecnologías de extracción: bagazo, petróleo, residuos, biocombustibles, carbón."""
    return df[df["TECHNOLOGY"].isin((TECNOLOGIAS_EXTRACCION_MINERIA))]


TECNOLOGIAS_PRODUCCION_SAF = ["UPSSAF", "UPSBJS", "UPSATJ"]


def _filtro_saf_produccion(df, **kw):
    return df[df["TECHNOLOGY"].isin((TECNOLOGIAS_PRODUCCION_SAF))]


COMBUSTIBLES_H2 = ["HDG", "HDG002"]

TECNOLOGIAS_H2_EXCLUIR = [
    "UPSHDGRST",
    "DEMTRAHDGTAX",
]


def _filtro_h2(df, **kw):
    if "FUEL" not in df.columns:
        return df.iloc[0:0]

    return df[
        df["FUEL"].isin(COMBUSTIBLES_H2)
        & ~df["TECHNOLOGY"].isin(TECNOLOGIAS_H2_EXCLUIR)
    ]


TECNOLOGIAS_ELECTROLISIS_VERDE = ["UPSALK", "UPSPEM"]


def _filtro_electrolisis_verde(df, **kw):
    """Electrolizadores para producción de hidrógeno verde (UPSALK, UPSPEM)."""
    return df[df["TECHNOLOGY"].isin((TECNOLOGIAS_ELECTROLISIS_VERDE))]


TECNOLOGIAS_H2_PRODUCCION_VERDE_AZUL_GRIS = ["UPSSMR", "UPSSMRCCS", "UPSPEM", "UPSALK"]


def _filtro_h2_verde_azul_gris(df, **kw):
    """Producción de H2: UPSSMR, UPSSMRCCS, UPSPEM, UPSALK."""
    return df[df["TECHNOLOGY"].isin((TECNOLOGIAS_H2_PRODUCCION_VERDE_AZUL_GRIS))]


TECNOLOGIAS_UPSTREAM_REFINACION = ["UPSSAF", "UPSALK", "UPSPEM"]


def _filtro_ups_refinacion(df, **kw):
    """Upstream refinación: UPSSAF, UPSALK, UPSPEM (biocombustibles e hidrógeno)."""
    return df[df["TECHNOLOGY"].isin((TECNOLOGIAS_UPSTREAM_REFINACION))]


TECNOLOGIAS_MINERIA_HIDROCARBUROS = [
    "MINOIL",
    "MINOIL_1LIV",
    "MINOIL_2MID",
    "MINOIL_3PES",
    "MINNGS",
]


def _filtro_min_hidrocarburos(df, **kw):
    """Minería petróleo y gas (MINOIL, MINNGS)."""
    return df[df["TECHNOLOGY"].isin((TECNOLOGIAS_MINERIA_HIDROCARBUROS))]


TECNOLOGIAS_MINERIA_CARBON = ["MINCOA"]


def _filtro_min_carbon(df, **kw):
    """Minería carbón (MINCOA)."""
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_MINERIA_CARBON)]


TECNOLOGIAS_OFERTA_BIOENERGIA = [
    "MINWAS",
    "MINWAS_ORG",
    "MINOPL",
    "MINSGC",
    "MINWOO",
    "MINBAG",
]


def _filtro_oferta_bioenergia(df, **kw):
    """Oferta bioenergía: residuos sólidos, palma, orgánica, caña, madera."""
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_OFERTA_BIOENERGIA)]


COMBUSTIBLES_GEI = [
    "EMIC02",
    "EMICH4",
    "EMIN2O",
]


def _filtro_gei(df, **kw):
    if "FUEL" not in df.columns:
        return df.iloc[0:0]

    return df[df["FUEL"].isin(COMBUSTIBLES_GEI)]


FUELS_CONTAMINANTES = [
    "EMIBC",
    "EMICO",
    "EMICOVDM",
    "EMINH3",
    "EMINOx",
    "EMIPM10",
    "EMIPM2_5",
    "EMISOx",
]


def _filtro_contaminantes(df, **kw):
    if "FUEL" not in df.columns:
        return df.iloc[0:0]

    return df[df["FUEL"].isin(FUELS_CONTAMINANTES)]


TECNOLOGIAS_DEMANDA = (
    TECNOLOGIAS_RESIDENCIALES
    + TECNOLOGIAS_INDUSTRIALES
    + TECNOLOGIAS_TRANSPORTE
    + TECNOLOGIAS_TERCIARIO
    + TECNOLOGIAS_CONSTRUCCION
    + TECNOLOGIAS_AGROFORESTAL
    + TECNOLOGIAS_MINERIA
    + TECNOLOGIAS_COQUERIAS
)


def _filtro_demanda_por_combustible(df, sub_filtro=None, **kw):
    mask = df["TECHNOLOGY"].isin(TECNOLOGIAS_DEMANDA)

    if sub_filtro and "FUEL" in df.columns:
        mask &= df["FUEL"] == sub_filtro

    return df[mask]


FUELS_LIQUIDOS = [
    "DSL002",
    "FOL",
    "GSL002",
    "JET",
    "LPG002",
]


def _filtro_consumo_liquidos(df, **kw):
    if "TECHNOLOGY" not in df.columns or "FUEL" not in df.columns:
        return df.iloc[0:0]

    return df[
        df["TECHNOLOGY"].isin(TECNOLOGIAS_DEMANDA) & df["FUEL"].isin(FUELS_LIQUIDOS)
    ]


TECNOLOGIAS_PWR_LIQUIDOS_TOTAL = [
    "PWRDSL",
    "PWRFOIL",
    "PWRJET",
    "PWRLPG",
]

FUELS_LIQUIDOS = [
    "DSL",
    "FOL",
    "GSL",
    "JET",
    "LPG",
]


def _filtro_liquidos_total(df, **kw):
    if "TECHNOLOGY" not in df.columns or "FUEL" not in df.columns:
        return df.iloc[0:0]

    return df[
        df["TECHNOLOGY"].isin(TECNOLOGIAS_DEMANDA + TECNOLOGIAS_PWR_LIQUIDOS)
        & df["FUEL"].isin(FUELS_LIQUIDOS)
    ]


TECNOLOGIAS_EXPORTACION_LIQUIDOS = [
    "EXPDSL",
    "EXPGSL",
    "EXPJET",
    "EXPLPG",
]

TECNOLOGIAS_DEMANDA_EXPORTACION_LIQUIDOS = (
    TECNOLOGIAS_DEMANDA + TECNOLOGIAS_EXPORTACION_LIQUIDOS
)


def _filtro_demanda_exportaciones_liquidos(df, **kw):
    if "TECHNOLOGY" not in df.columns or "FUEL" not in df.columns:
        return df.iloc[0:0]

    return df[
        df["TECHNOLOGY"].isin(TECNOLOGIAS_DEMANDA_EXPORTACION_LIQUIDOS)
        & df["FUEL"].isin(FUELS_LIQUIDOS)
    ]


TECNOLOGIAS_PETROLEO_CRUDO = ["MINOIL", "MINOIL_1LIV", "MINOIL_2MID", "MINOIL_3PES"]


def _filtro_min_oil(df, **kw):
    """Minería petróleo crudo (MINOIL)."""
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_PETROLEO_CRUDO)]


TECNOLOGIAS_IMPORTACION_PETROLEO_CRUDO = ["IMPOIL"]


def _filtro_imp_oil(df, **kw):
    """Importación de petróleo crudo (IMPOIL)."""
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_IMPORTACION_PETROLEO_CRUDO)]


TECNOLOGIAS_EXPORTACION_PETROLEO = ["EXPOIL"]


def _filtro_exp_oil(df, **kw):
    """Exportación de petróleo crudo (EXPOIL)."""
    return df[df["TECHNOLOGY"].isin(TECNOLOGIAS_EXPORTACION_PETROLEO)]


###########################################################################################################


def _filtro_contiene(df, prefijo: str, sub_filtro=None, **kw):
    """Filtro genérico: TECHNOLOGY *contiene* el texto dado."""
    return df[df["TECHNOLOGY"].str.contains(prefijo)]


def _filtro_otros(df, sub_filtro=None, **kw):
    if sub_filtro:
        return df[df["TECHNOLOGY"].str.startswith(sub_filtro)]
    return df.iloc[0:0]


def _filtro_prefijo_con_sub(df, prefijo: str, sub_filtro=None, **kw):
    """Filtro genérico: startswith(prefijo) + contains(sub_filtro)."""
    mask = df["TECHNOLOGY"].str.startswith(prefijo)
    if sub_filtro:
        mask &= df["TECHNOLOGY"].str.contains(sub_filtro)
    return df[mask]


def _map_electrolisis_verde(tech):
    """Map electrolyzer technologies to unified 'Electrólisis Verde' label."""
    t = str(tech)
    if t.startswith("UPSALK") or t.startswith("UPSPEM"):
        return "Hidrógeno Verde"
    return t


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


def _map_h2_consumo_grupo(tech):
    """Agrupa tecnologías de consumo de H₂ del transporte pesado y residuos sólidos."""
    t = str(tech)
    if t in ("DEMTRAHDGSTT", "DEMTRAHDGTCK_CSG"):
        return "Transporte pesado"
    if t in (
        "DEMINDWASBOI_HIG",
        "DEMINDWASBOI_MID",
        "DEMINDWASBOI_LOW",
        "DEMINDWASFUR_HIG",
        "DEMINDWASFUR_LOW",
        "DEMINDWASFUR_MID",
    ):
        return "Residuos Sólidos"
    return t


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


def _filtro_por_fuel_set(df, fuel_set: set, **kw):
    if "FUEL" not in df.columns:
        return df.iloc[0:0]
    return df[df["FUEL"].isin(fuel_set)]


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
    "gas_capacidad": {
        "titulo_base": "Gas Natural — Capacidad de Extracción y Regasificación",
        "figura_base": "Figura 22",
        "filename_base": "Fig22_Capacidad_Gas",
        "print_base": "CAPACIDAD DE GAS NATURAL",
        "filtro": _filtro_gas_produccion,
        "msg_sin_datos": "Sin datos de extracción o regasificación de gas (MINNGS/UPSREG)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": _color_gas_produccion,
        "es_capacidad": True,
        "variable_default": "TotalCapacityAnnual",
    },
    "gas_import_export": {
        "titulo": "Gas Natural — Importaciones y Exportaciones",
        "figura": "Figura 23",
        "filename": "Fig23_Imp_Exp_Gas",
        "print": "GAS NATURAL: IMPORTACIONES Y EXPORTACIONES",
        "filtro": _filtro_gas_flujos,
        "msg_sin_datos": "Sin datos de importación/exportación de gas (IMPLNG/EXPNGS)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": _color_gas_produccion,
        "variable_default": "ProductionByTechnology",
        "allowedGroupings": ["TECNOLOGIA", "FUEL"],
        "soportaPareto": True,
        "soportaPorcentaje": True,
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
    "imp_exp_crudo": {
        "titulo": "Crudo - Importaciones y Exportaciones - ProductionByTechnology",
        "figura": "Figura 20",
        "filename": "Fig20_Imp_Exp_Crudo",
        "print": "CRUDO: IMPORTACIONES Y EXPORTACIONES",
        "filtro": _filtro_crudo_flujos,
        "msg_sin_datos": "Sin datos de importación/exportación de crudo (IMPOIL/EXPOIL)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": _color_liquidos_import,
        "variable_default": "ProductionByTechnology",
        "allowedGroupings": ["TECNOLOGIA", "FUEL"],
        "soportaPareto": True,
        "soportaPorcentaje": True,
    },
    "exp_carbon": {
        "titulo": "Carbón - Exportación - ProductionByTechnology",
        "figura": "Figura CAR-EXP",
        "filename": "Fig_Carbon_Export",
        "print": "CARBÓN: EXPORTACIÓN",
        "filtro": _filtro_exp_carbon,
        "msg_sin_datos": "Sin exportaciones de carbón (EXPCOA)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": _color_liquidos_import,
        "variable_default": "ProductionByTechnology",
        "allowedGroupings": ["TECNOLOGIA", "FUEL"],
        "soportaPareto": True,
        "soportaPorcentaje": True,
    },
    "ref_produccion_importaciones": {
        "titulo": "Refinerías + Importaciones de Líquidos - ProductionByTechnology",
        "figura": "Figura REF-IMP-LIQ",
        "filename": "Fig_Ref_Imp_Liquidos",
        "print": "REFINERÍAS + IMPORTACIONES DE LÍQUIDOS",
        "filtro": _filtro_ref_produccion_importaciones,
        "msg_sin_datos": "Sin datos de refinerías o importaciones de líquidos",
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
        "allowedGroupings": ["TECNOLOGIA", "FUEL", "TRANSPORTE_GRUPO"],
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
        "allowedGroupings": ["TECNOLOGIA", "FUEL", "TRANSPORTE_GRUPO"],
        "color_fn": generar_colores_tecnologias,
        "variable_default": "ProductionByTechnology",
    },
    "tra_por_modo": {
        "titulo": "Sector Transporte - Consumo Por Modo - UseByTechnology",
        "figura": "Figura X",
        "filename": "Tra_Por_Modo",
        "print": "SECTOR TRANSPORTE (POR MODO)",
        "filtro": _filtro_transporte_por_modo,
        "msg_sin_datos": "Sin tecnologías de transporte (DEMTRA)",
        "agrupar_por": "MODO",
        "color_fn": _color_por_modo,
        "variable_default": "UseByTechnology",
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
        "unidad_factor_por_tecnologia": {
            "kton": {
                # "UPSSMR": 0.12,
                # "UPSSMRCCS": 0.12,
                "UPSALK": 0.12,
                "UPSPEM": 0.12,
            }
        },
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
        "unidad_factor_por_tecnologia": {
            "kton": {
                "UPSALK": 0.12,
                "UPSPEM": 0.12,
            }
        },
    },
    "h2_consumo": {
        "titulo": "Hidrógeno - Consumo - UseByTechnology",
        "figura": "Figura 33",
        "filename": "Fig33_Consumo_H2",
        "print": "CONSUMO DE HIDRÓGENO",
        "filtro": _filtro_h2,
        "msg_sin_datos": "Sin tecnologías que consumen hidrógeno (FUEL=HDG/HDG002)",
        "agrupar_por": "H2_CONSUMO",
        "color_fn": _color_h2_consumo,
        "variable_default": "UseByTechnology",
        "unidad_factor_por_tecnologia": {
            "kton": {
                "DEMTRAHDGSTT": 0.12,
                "DEMTRAHDGTCK_CSG": 0.12,
                "UPSHDGRST": 0.12,
                "UPSSAF": 0.12,
                "DEMDERHDG": 0.12,
                "DEMINDHDGFUR": 0.12,
                "DEMEXPHDG": 0.12,
            }
        },
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
        "unidad_factor_por_tecnologia": {
            "kton": {
                "UPSALK": 0.12,
                "UPSPEM": 0.12,
                "UPSSMR": 0.12,
                "UPSSMRCCS": 0.12,
            }
        },
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
        "unidad_factor_por_tecnologia": {
            "kton": {
                "MINWOO": 0.016993,
                "MINBAG": 0.014743,
                "MINWAS_ORG": 0.017,
                "MINWAS": 0.0085,
                "MINOPL": 0.0352,
                "MINSGC": 0.0267,
            },
        },
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
        "color_fn": _color_por_sector_gei,
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
    "elec_consumo_liquidos": {
        "titulo": "Consumo de Líquidos - Sector Eléctrico",
        "figura": "Figura ELEC-CONS-LIQ",
        "filename": "Fig_Electrico_Consumo_Liquidos",
        "print": "SECTOR ELÉCTRICO: CONSUMO DE LÍQUIDOS",
        "filtro": _filtro_pwr_liquidos,
        "msg_sin_datos": "Sin consumo de líquidos en generación eléctrica",
        "agrupar_por": "FUEL",
        "color_fn": _color_por_grupo_fijo,
        "variable_default": "UseByTechnology",
        "allowedGroupings": ["TECNOLOGIA", "FUEL"],
        "soportaPareto": True,
        "soportaPorcentaje": True,
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
    # ═══════════════════════════════════════════════════════════════════════
    # PETRÓLEO CRUDO — MINERÍA E IMPORTACIÓN
    # ═══════════════════════════════════════════════════════════════════════
    "min_oil": {
        "titulo": "Producción de Petróleo Crudo - ProductionByTechnology",
        "figura": "Figura MIN-OIL",
        "filename": "Fig_Min_Oil",
        "print": "PRODUCCIÓN DE PETRÓLEO CRUDO (MINOIL)",
        "filtro": _filtro_min_oil,
        "msg_sin_datos": "Sin datos de extracción de petróleo crudo (MINOIL)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": generar_colores_tecnologias,
        "variable_default": "ProductionByTechnology",
        "allowedGroupings": ["TECNOLOGIA", "FUEL"],
        "soportaPareto": True,
    },
    "imp_oil": {
        "titulo": "Importación de Petróleo Crudo - ProductionByTechnology",
        "figura": "Figura IMP-OIL",
        "filename": "Fig_Imp_Oil",
        "print": "IMPORTACIÓN DE PETRÓLEO CRUDO (IMPOIL)",
        "filtro": _filtro_imp_oil,
        "msg_sin_datos": "Sin datos de importación de petróleo crudo (IMPOIL)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": _color_liquidos_import,
        "variable_default": "ProductionByTechnology",
        "allowedGroupings": ["TECNOLOGIA", "FUEL"],
        "soportaPareto": True,
    },
    "exp_oil_consumo": {
        "titulo": "Exportaciones — Petróleo - UseByTechnology",
        "figura": "Figura EXP-OIL-USE",
        "filename": "Fig_Exp_Oil_Use",
        "print": "EXPORTACIONES DE PETRÓLEO (UseByTechnology)",
        "filtro": _filtro_exp_oil,
        "msg_sin_datos": "Sin datos de exportación de petróleo crudo (EXPOIL)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": _color_liquidos_import,
        "variable_default": "UseByTechnology",
        "allowedGroupings": ["TECNOLOGIA", "FUEL"],
        "soportaPareto": True,
    },
    # ═══════════════════════════════════════════════════════════════════════
    # RECURSOS Y RESERVAS
    # ═══════════════════════════════════════════════════════════════════════
    "recursos_vs_demanda": {
        "titulo": "Recursos y reservas vs Demanda (Crudo)",
        "figura": "Recursos y reservas vs Demanda (Crudo)",
        "filename": "Recursos_Reservas_vs_Demanda_Crudo",
        "print": "RECURSOS Y RESERVAS VS DEMANDA (CRUDO)",
        "filtro": _filtro_recursos_crudo,
        "msg_sin_datos": "Sin datos de extracción de petróleo (MINOIL)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": None,
        "variable_default": "ProductionByTechnology",
    },
    "recursos_vs_demanda_gas": {
        "titulo": "Recursos y reservas vs Demanda (Gas Natural)",
        "figura": "Recursos y reservas vs Demanda (Gas Natural)",
        "filename": "Recursos_Reservas_vs_Demanda_Gas",
        "print": "RECURSOS Y RESERVAS VS DEMANDA (GAS NATURAL)",
        "filtro": _filtro_recursos_gas,
        "msg_sin_datos": "Sin datos de extracción de gas natural (MINNGS)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": None,
        "variable_default": "ProductionByTechnology",
    },
    "recursos_vs_demanda_carbon": {
        "titulo": "Recursos y reservas vs Demanda (Carbón)",
        "figura": "Recursos y reservas vs Demanda (Carbón)",
        "filename": "Recursos_Reservas_vs_Demanda_Carbon",
        "print": "RECURSOS Y RESERVAS VS DEMANDA (CARBÓN)",
        "filtro": _filtro_recursos_carbon,
        "msg_sin_datos": "Sin datos de carbón (COA/EXPCOA/MINCOA)",
        "agrupar_por": "TECNOLOGIA",
        "color_fn": None,
        "variable_default": "UseByTechnology",
    },
}
