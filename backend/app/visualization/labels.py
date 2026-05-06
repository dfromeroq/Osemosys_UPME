"""
labels.py — Diccionario de nombres para visualización (OSeMOSYS Colombia).

Mapea códigos de tecnología → display_name legible y corto para gráficas.

Uso directo:
    from app.visualization.labels import get_label

    series_name = get_label("DEMINDCOABOI_LOW")
    # → "Ind. Carbón Caldera (Baja)"

Jerarquía de resolución de get_label(code):
    1. Búsqueda exacta en DISPLAY_NAMES
    2. Generación dinámica basada en los segmentos del código
    3. Fallback al código original (sin crash)

El diccionario DISPLAY_NAMES fue construido a partir del archivo
diccionario_osemosys_v2_xlsx_-_Diccionario_v2.csv y cubre ~700 tecnologías.
"""

from __future__ import annotations

# ══════════════════════════════════════════════════════════════════════════
# 1. DICCIONARIOS DE APOYO PARA GENERACIÓN DINÁMICA
# ══════════════════════════════════════════════════════════════════════════

# Prefijo de categoría → abreviatura para gráfica
_CAT_PREFIX: dict[str, str] = {
    "DEMRES": "Res.",
    "DEMIND": "Ind.",
    "DEMTRA": "Tra.",
    "DEMTER": "Ter.",
    "DEMCON": "Constr.",
    "DEMAGF": "Agric.",
    "DEMCOQ": "Coque",
    "DEMCYR": "Ref.",
    "DEM": "Dem.",
    "PWRCOG": "Cogener.",
    "PWR": "Gen.",
    "MIN": "Ext.",
    "GRD": "Red",
    "IMP": "Imp.",
    "EXP": "Exp.",
    "BACKSTOP": "Backup",
    "LND": "Tierra",
}

# Energético embebido en código → label corto
_ENERGETICO: dict[str, str] = {
    "DSL": "Diésel",
    "ELC": "Elec.",
    "GSL": "Gasolina",
    "NGS": "GN",
    "LPG": "GLP",
    "WOO": "Leña",
    "BGS": "Biogás",
    "BAG": "Bagazo",
    "COA": "Carbón",
    "HDG": "H₂",
    "HYD": "Hidroeléctrica",
    "SOL": "Solar",
    "WND": "Eólica",
    "ONW": "Eól.Ter.",
    "OFW": "Eól.Mar.",
    "FOL": "F.Oil",
    "JET": "Jet",
    "BDL": "Biodiésel",
    "BET": "Bioetanol",
    "SAF": "SAF",
    "BJS": "JET-SAF",
    "GEO": "Geotérm.",
    "WAS": "Residuos/Biomasa",
    "OIL": "Petróleo",
    "OIL_1LIV": "Crudo liviano",
    "OIL_2MID": "Crudo intermedio",
    "OIL_3PES": "Crudo pesado",
    "MINOIL": "Crudo",
    "MINOIL_1LIV": "Crudo liviano",
    "MINOIL_2MID": "Crudo intermedio",
    "MINOIL_3PES": "Crudo pesado",
    "URN": "Nuclear",
    "AFR": "Res.Agr.",
    "OPL": "Palma",
    "BIO": "Biomasa",
    "LNG": "GNL",
    "SGC": "Caña",
    "BMET": "Biometano",
    "BBG": "Bio-GSL",
    "BDB": "Bio-DSL",
    "BGB": "Bio-GBE",
    "CSP": "CSP",
    "NGS": "GN",
    "NUC": "Nuclear",
    "UGE": "Fotv. Gran Escala",
    "STD": "Diésel Independiente",
}

# Tecnología de uso → label corto
_USO: dict[str, str] = {
    "BOI": "Caldera",
    "FUR": "Horno",
    "BOT": "Bote",
    "BUS": "Bus",
    "MOT": "Moto",
    "TAX": "Taxi",
    "TCK": "Camión",
    "LDV": "Veh.Lig.",
    "FWD": "4x4",
    "MIC": "Microbús",
    "SHP": "Barco",
    "STT": "Semirrem.",
    "AIR": "AC",
    "ILU": "Ilum.",
    "REF": "Refrig.",
    "CKN": "Estufa",
    "MPW": "Motor",
    "WHT": "Cal.Agua",
    "TV": "TV",
    "WSH": "Lavadora",
    "AVI": "Aviac.",
    "MET": "Metro",
    "STO": "Almac.",
    "RTP": "FV Techo",
    "TYD": "T&D",
    "DST": "T&D",
    "CC": "CC",
    "CS": "CS",
    "SMR": "SMR",
    "REG": "Regasif.",
    "ACL": "Aclimat.",
    "OTH": "Otros",
    "DATA": "DataCtr.",
    "FAN": "Ventil.",
    "PEM": "PEM",
    "ALK": "Alcalino",
    "BAT": "Batería",
    "COG": "Cogener.",
}

# Eficiencia → label corto
_EFIC: dict[str, str] = {
    "_LOW": "(Baja)",
    "_MID": "(Media)",
    "_HIG": "(Alta)",
}

# Área/Subtipo → label corto
_AREA: dict[str, str] = {
    "_RUR": "Rural",
    "_URB": "Urb.",
    "_ZNI": "ZNI",
    "_IMU": "Intermunic.",
    "_ART": "Artic.",
    "_BIA": "Biartic.",
    "_CEN": "Central",
    "_SPL": "Split",
    "_AUC": "Autoc.",
    "_FIX": "Fija",
    "_FLO": "Flotante",
    "_UGE": "Gran esc.",
    "_UPE": "Peq.esc.",
    "_NDC": "No CDC",
    "_IND": "Ind.",
    "_C2P": "5.5t",
    "_CSG": "12t",
    "_ORG": "Org.",
    "_OFS": "Offshore",
    "_ONS": "Onshore",
    "_BAT": "+Bat.",
    "_CCS": "+CCS",
    "_HEV": "HEV",
    "_PHE": "PHEV",
}

# Grupos COLORES_GRUPOS → label legible para comparaciones por combustible
_GRUPO: dict[str, str] = {
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
    "HDG002": "Hidrógeno (ind.)",
    "FOL": "Fuel Oil",
    "BDL": "Biodiésel",
    "JETSAF": "Jet Sostenible (SAF)",
    "JET": "Jet Fuel (Queroseno)",
    "WAS": "Residuos/Biomasa",
    "OIL": "Petróleo",
    "OIL_1LIV": "Crudo liviano",
    "OIL_2MID": "Crudo intermedio",
    "OIL_3PES": "Crudo pesado",
    "MINOIL": "Crudo",
    "MINOIL_1LIV": "Crudo liviano",
    "MINOIL_2MID": "Crudo intermedio",
    "MINOIL_3PES": "Crudo pesado",
    "AFR": "Res. Agr./Forest.",
    "SAF": "SAF",
    "BJS": "JET-SAF",
    "OPL": "Aceite de Palma",
    "SGC": "Caña de Azúcar",
    "AUT": "Autoconsumo",
    "PHEV": "PHEV",
    "HEV": "HEV",
    "DEMCON": "Construcción",
    "DEMAGF": "Agric. y Pesca",
    "DEMMIN": "Minería",
    "DEMCOQ": "Coque",
}

# ══════════════════════════════════════════════════════════════════════════
# 2. DICCIONARIO ESTÁTICO (generado del CSV)
#    Cubre todos los códigos del diccionario_osemosys_v2.
#    Formato: "CÓDIGO": "Display Name"
# ══════════════════════════════════════════════════════════════════════════

DISPLAY_NAMES: dict[str, str] = {
    # ── Combustibles (lookup exacto — sin afectar abreviaturas en techs largas) ──
    "ELC": "Electricidad",
    "NGS": "Gas Natural",
    "DSL": "Diésel",
    "GSL": "Gasolina",
    "LPG": "GLP",
    "WOO": "Leña",
    "BGS": "Biogás",
    "BAG": "Bagazo",
    "HDG": "Hidrógeno",
    "COA": "Carbón",
    "FOL": "Fuel Oil",
    "BDL": "Biodiésel",
    "JETSAF": "Jet Sostenible (SAF)",
    "JET": "Jet Fuel (Queroseno)",
    "WAS": "Residuos/Biomasa",
    "OIL": "Petróleo",
    "AFR": "Res. Agrícolas/Forestales",
    "SAF": "SAF",
    "HDG002": "Hidrógeno",
    # ── Tipos de emisión ──────────────────────────────────────────────────
    "EMIC02": "CO₂",
    "EMICH4": "CH₄",
    "EMIN2O": "N₂O",
    "EMIBC": "Black Carbon",
    "EMICO": "CO",
    "EMICOVDM": "COV",
    "EMINH3": "NH₃",
    # ``NOx`` / ``SOx`` con "x" literal (no Unicode subscript ₓ U+2093):
    # la fuente Nunito y muchas otras carecen del glyph y aparece como □.
    "EMINOx": "NOx",
    "EMIPM10": "PM10",
    "EMIPM2_5": "PM2.5",
    "EMISOx": "SOx",
    # ── Backstop ──────────────────────────────────────────────────────────
    "BACKSTOP 1": "Backup 1",
    "BACKSTOP 2": "Backup 2",
    "BACKSTOP_1": "Backup 1",
    "BACKSTOP_2": "Backup 2",
    # ── Red / Distribución ────────────────────────────────────────────────
    "BBDDST": "T&D Bio-DSL",
    "BBGDST": "T&D Bio-GSL",
    "BDLTYD": "T&D Biodiésel",
    "BETTYD": "T&D Bioetanol",
    "COADST": "T&D Carbón",
    "CTRNGS": "Transp. GN (constr.)",
    "GRDCOADST": "Red Carbón T&D",
    "GRDHDGTRN": "Red H₂ Ducto",
    "GRDLPGDST": "Red GLP T&D",
    "GRDNGSDST": "Red GN T&D",
    "GRDNGSTRN": "Red GN T&D",
    "GRDTYDELC": "Red Elec. T&D",
    "GRDZNIELC": "Red Elec. ZNI",
    "HDGDST": "Transp. H₂ Carretera",
    # ── Importaciones / Exportaciones ─────────────────────────────────────
    "IMPDSL": "Imp. Diésel",
    "IMPFOL": "Imp. Fuel Oil",
    "IMPGSL": "Imp. Gasolina",
    "IMPJET": "Imp. Jet A1",
    "IMPLNG": "Imp. GNL",
    "IMPLPG": "Imp. GLP",
    "IMPOIL": "Imp. Petróleo",
    "IMPURN": "Imp. Uranio",
    "EXPOIL": "Exp. Petróleo",
    # ── Extracción / Recursos ─────────────────────────────────────────────
    "MINCOA": "Ext. Carbón",
    "MINCSP": "Pot. CSP",
    "MINDAM": "Pot. Hidro (Em.)",
    "MINGEO": "Recursos Geotérm.",
    "MINLND": "Tierra Cultivable",
    "MINLPG": "Ext. GLP",
    "MINNGS": "Gas Natural Nacional",
    "MINOFW": "Pot. Eól.Mar.",
    "MINOFW_FIX": "Pot. Eól.Mar. Fijo",
    "MINOFW_FLO": "Pot. Eól.Mar. Flot.",
    "MINOIL": "Ext. Petróleo",
    "MINOIL_1LIV": "Ext. Petróleo Liv.",
    "MINOIL_2MID": "Ext. Petróleo Med.",
    "MINOIL_3PES": "Ext. Petróleo Pes.",
    "MINONW": "Pot. Eól.Ter.",
    "MINOPL": "Extracción Aceite de Palma",
    "MINROR": "Pot. Hidro (ROR)",
    "MINSGC": "Caña de Azúcar",
    "MINBAG": "Extracción Bagazo de Caña",
    "MINBG": "Extracción Bagazo de Caña",
    "MINSOL": "Pot. Solar FV",
    "MINSOL_RTP": "Pot. Solar Techo",
    "MINURN": "Prod. Uranio",
    "MINWAS": "Recolección Residuos Sólidos",
    "MINWAS_ORG": "Recolección Residuos Orgánicos",
    "MINWAT": "Agua Disponible",
    "MINWOO": "Extracción Madera/Leña",
    "LNDAGR001": "Tierra Caña",
    "LNDAGR002": "Tierra Cacao",
    "LNDAGR003": "Tierra Café",
    "LNDAGR004": "Tierra Arroz",
    # ── Generación Eléctrica ──────────────────────────────────────────────
    "PWRAFR": "Biomasa (AFR)",
    "PWRAFRCCS": "Biomasa AFR+CCS",
    "PWRBGS": "Biogás",
    "PWRCOA": "Carbón",
    "PWRCOACCS": "Carbón+CCS",
    "PWRCOG": "Cogeneración",
    "PWRCOGBAG": "Cogener. Bagazo",
    "PWRCOGCOF": "Cogener. Café",
    "PWRCOGHUS": "Cogener. Cacao",
    "PWRCOGMAZ": "Cogener. Hojarasca",
    "PWRCOGRAQ": "Cogener. Raquis",
    "PWRCOGRCE": "Cogener. Arroz",
    "PWRCSP": "CSP",
    "PWRDAM": "Hidroeléctrica Embalse",
    "PWRDSL": "Diésel",
    "PWRDST": "Distrib. Elec.",
    "PWRFOL": "Fuel Oil",
    "PWRGEO": "Geotérmica",
    "PWRHYDDAM": "Hidroeléctrica Embalse",
    "PWRHYDROR": "Hidroeléctrica Filo de Agua",
    "PWRHYDROR_NDC": "Hidroeléctrica Filo de Agua (NDC)",
    "PWRJET": "Jet Fuel",
    "PWRLPG": "Gas Licuado (GLP)",
    "PWRNGS": "Gas Natural",
    "PWRNGSCCS": "Gas Natural+CCS",
    "PWRNGS_CC": "Gas Natural Ciclo Combinado",
    "PWRNGS_CS": "Gas Natural Ciclo Simple",
    "PWRNUC": "Nuclear",
    "PWROFIXW": "Eólica Offshore Fija",
    "PWRWNDOFS_FIX": "Eólica Offshore Fija",
    "PWRWNDOFS_FLO": "Eólica Offshore Flotante",
    "PWROFLOW": "Eólica Offshore Flotante",
    "PWRONW": "Eólica Onshore",
    "PWRWNDONS": "Eólica Onshore",
    "PWRROR": "Hidroeléctrica Filo de Agua",
    "PWRSOL": "Solar FV",
    "PWRSOLBAT": "Solar FV Utility + Bateria",
    "PWRSOLRTP": "Solar FV Residencial (RTP)",
    "PWRSOLRTP_IND": "Solar FV RTP Ind.",
    "PWRSOLRTP_ZNI": "Solar FV Residencial ZNI",
    "PWRSOLUGE": "Solar FV Utility Gran Escala",
    "PWRSOLUGE_BAT": "Solar FV Utility + Bateria",
    "PWRSOLUPE": "Solar FV Utility Pequeña Escala",
    "PWRWAS": "Gen. RSU",
    # ── Demanda: Agricultura y Pesca ──────────────────────────────────────
    "DEMAGFDSL": "Agric. Diésel",
    "DEMAGFELC": "Agric. Elec.",
    "DEMAGFGSL": "Agric. Gasolina",
    "DEMAGFNGS": "Agric. GN",
    "DEMAGFTER": "Agric. Térm.",
    "DEMAGFWOO": "Agric. Leña",
    # ── Demanda: Construcción ─────────────────────────────────────────────
    "DEMCONSDSL": "Constr. Diésel",
    "DEMCONSELC": "Constr. Elec.",
    "DEMCONSGSL": "Constr. Gasolina",
    "DEMCONSNGS": "Constr. GN",
    # ── Demanda: Coque ────────────────────────────────────────────────────
    "DEMCOQDSL": "Coque Diésel",
    "DEMCOQGSL": "Coque Gasolina",
    "DEMCYRDSL": "Ref.+Coque Diésel",
    "DEMCYRELC": "Ref.+Coque Elec.",
    "DEMCYRGSL": "Ref.+Coque Gasolina",
    "DEMCYRLPG": "Ref.+Coque GLP",
    # ── Demanda: Industrial — Bagazo ──────────────────────────────────────
    "DEMINDAUTBOI": "Ind. Autocons. Caldera",
    "DEMINDAUTFUR": "Ind. Autocons. Horno",
    "DEMINDBAGBOI": "Ind. Bagazo Caldera",
    "DEMINDBAGBOI_HIG": "Ind. Bagazo Caldera (Alta)",
    "DEMINDBAGBOI_LOW": "Ind. Bagazo Caldera (Baja)",
    "DEMINDBAGBOI_MID": "Ind. Bagazo Caldera (Media)",
    "DEMINDBAGFUR": "Ind. Bagazo Horno",
    "DEMINDBAGFURCCS": "Ind. Bagazo Horno+CCS",
    "DEMINDBAGFUR_HIG": "Ind. Bagazo Horno (Alta)",
    "DEMINDBAGFUR_LOW": "Ind. Bagazo Horno (Baja)",
    "DEMINDBAGFUR_MID": "Ind. Bagazo Horno (Media)",
    # ── Demanda: Industrial — Biogás ──────────────────────────────────────
    "DEMINDBGSBOI_HIG": "Ind. Biogás Caldera (Alta)",
    "DEMINDBGSBOI_LOW": "Ind. Biogás Caldera (Baja)",
    "DEMINDBGSBOI_MID": "Ind. Biogás Caldera (Media)",
    "DEMINDBGSFUR_HIG": "Ind. Biogás Horno (Alta)",
    "DEMINDBGSFUR_LOW": "Ind. Biogás Horno (Baja)",
    "DEMINDBGSFUR_MID": "Ind. Biogás Horno (Media)",
    # ── Demanda: Industrial — Carbón ──────────────────────────────────────
    "DEMINDCOABOI": "Ind. Carbón Caldera",
    "DEMINDCOABOICCS": "Ind. Carbón Caldera+CCS",
    "DEMINDCOABOI_HIG": "Ind. Carbón Caldera (Alta)",
    "DEMINDCOABOI_LOW": "Ind. Carbón Caldera (Baja)",
    "DEMINDCOABOI_MID": "Ind. Carbón Caldera (Media)",
    "DEMINDCOAFUR": "Ind. Carbón Horno",
    "DEMINDCOAFURCCS": "Ind. Carbón Horno+CCS",
    "DEMINDCOAFUR_HIG": "Ind. Carbón Horno (Alta)",
    "DEMINDCOAFUR_LOW": "Ind. Carbón Horno (Baja)",
    "DEMINDCOAFUR_MID": "Ind. Carbón Horno (Media)",
    "DEMINDCOAOTH_LOW": "Ind. Carbón Otros (Baja)",
    # ── Demanda: Industrial — Diésel ──────────────────────────────────────
    "DEMINDDSLBOI_HIG": "Ind. Diésel Caldera (Alta)",
    "DEMINDDSLBOI_LOW": "Ind. Diésel Caldera (Baja)",
    "DEMINDDSLBOI_MID": "Ind. Diésel Caldera (Media)",
    "DEMINDDSLFUR_HIG": "Ind. Diésel Horno (Alta)",
    "DEMINDDSLFUR_LOW": "Ind. Diésel Horno (Baja)",
    "DEMINDDSLFUR_MID": "Ind. Diésel Horno (Media)",
    # ── Demanda: Industrial — Electricidad ────────────────────────────────
    "DEMINDELCAIR_HIG": "Ind. Elec. AC (Alta)",
    "DEMINDELCAIR_LOW": "Ind. Elec. AC (Baja)",
    "DEMINDELCAIR_MID": "Ind. Elec. AC (Media)",
    "DEMINDELCBOI": "Ind. Elec. Caldera",
    "DEMINDELCBOI_HIG": "Ind. Elec. Caldera (Alta)",
    "DEMINDELCBOI_LOW": "Ind. Elec. Caldera (Baja)",
    "DEMINDELCBOI_MID": "Ind. Elec. Caldera (Media)",
    "DEMINDELCFUR": "Ind. Elec. Horno",
    "DEMINDELCFUR_HIG": "Ind. Elec. Horno (Alta)",
    "DEMINDELCFUR_LOW": "Ind. Elec. Horno (Baja)",
    "DEMINDELCFUR_MID": "Ind. Elec. Horno (Media)",
    "DEMINDELCILU_HIG": "Ind. Elec. Ilum. (Alta)",
    "DEMINDELCILU_LOW": "Ind. Elec. Ilum. (Baja)",
    "DEMINDELCILU_MID": "Ind. Elec. Ilum. (Media)",
    "DEMINDELCMPW": "Ind. Elec. Motor",
    "DEMINDELCMPW_HIG": "Ind. Elec. Motor (Alta)",
    "DEMINDELCMPW_LOW": "Ind. Elec. Motor (Baja)",
    "DEMINDELCMPW_MID": "Ind. Elec. Motor (Media)",
    "DEMINDELCOTH_HIG": "Ind. Elec. Otros (Alta)",
    "DEMINDELCOTH_LOW": "Ind. Elec. Otros (Baja)",
    "DEMINDELCOTH_MID": "Ind. Elec. Otros (Media)",
    "DEMINDELCREF_HIG": "Ind. Elec. Refrig. (Alta)",
    "DEMINDELCREF_LOW": "Ind. Elec. Refrig. (Baja)",
    "DEMINDELCREF_MID": "Ind. Elec. Refrig. (Media)",
    # ── Demanda: Industrial — Fuel Oil ────────────────────────────────────
    "DEMINDFOLOTH_LOW": "Ind. F.Oil Otros (Baja)",
    # ── Demanda: Industrial — Hidrógeno ───────────────────────────────────
    "DEMINDHDGBOI": "Ind. H₂ Caldera",
    "DEMINDHDGBOI_HIG": "Ind. H₂ Caldera (Alta)",
    "DEMINDHDGBOI_LOW": "Ind. H₂ Caldera (Baja)",
    "DEMINDHDGFUR": "Ind. H₂ Horno",
    # ── Demanda: Industrial — GLP ─────────────────────────────────────────
    "DEMINDLPGBOI_HIG": "Ind. GLP Caldera (Alta)",
    "DEMINDLPGBOI_LOW": "Ind. GLP Caldera (Baja)",
    "DEMINDLPGBOI_MID": "Ind. GLP Caldera (Media)",
    "DEMINDLPGFUR_HIG": "Ind. GLP Horno (Alta)",
    "DEMINDLPGFUR_LOW": "Ind. GLP Horno (Baja)",
    "DEMINDLPGFUR_MID": "Ind. GLP Horno (Media)",
    # ── Demanda: Industrial — Gas Natural ─────────────────────────────────
    "DEMINDNGSBOI": "Ind. GN Caldera",
    "DEMINDNGSBOICCS": "Ind. GN Caldera+CCS",
    "DEMINDNGSBOI_HIG": "Ind. GN Caldera (Alta)",
    "DEMINDNGSBOI_LOW": "Ind. GN Caldera (Baja)",
    "DEMINDNGSBOI_MID": "Ind. GN Caldera (Media)",
    "DEMINDNGSFUR": "Ind. GN Horno",
    "DEMINDNGSFURCCS": "Ind. GN Horno+CCS",
    "DEMINDNGSFURCSS": "Ind. GN Horno+CCS",
    "DEMINDNGSFUR_HIG": "Ind. GN Horno (Alta)",
    "DEMINDNGSFUR_LOW": "Ind. GN Horno (Baja)",
    "DEMINDNGSFUR_MID": "Ind. GN Horno (Media)",
    # ── Demanda: Industrial — Residuos ────────────────────────────────────
    "DEMINDWASBOI_HIG": "Residuos/Biomasa",
    "DEMINDWASBOI_MID": "Residuos/Biomasa",
    "DEMINDWASBOI_LOW": "Residuos/Biomasa",
    "DEMINDWASFUR_HIG": "Residuos Sólidos",
    "DEMINDWASFUR_LOW": "Residuos Sólidos",
    "DEMINDWASFUR_MID": "Residuos Sólidos",
    # ── Demanda: Residencial — Electricidad ───────────────────────────────
    "DEMRESELCAIR_HIG": "Res. Elec. AC (Alta)",
    "DEMRESELCAIR_LOW": "Res. Elec. AC (Baja)",
    "DEMRESELCAIR_MID": "Res. Elec. AC (Media)",
    "DEMRESELCAIR_PAR_HIG": "Res. Elec. AC Pared (Alta)",
    "DEMRESELCAIR_PAR_LOW": "Res. Elec. AC Pared (Baja)",
    "DEMRESELCAIR_PAR_MID": "Res. Elec. AC Pared (Media)",
    "DEMRESELCAIR_POR_HIG": "Res. Elec. AC Portátil (Alta)",
    "DEMRESELCAIR_POR_LOW": "Res. Elec. AC Portátil (Baja)",
    "DEMRESELCAIR_POR_MID": "Res. Elec. AC Portátil (Media)",
    "DEMRESELCAIR_SPL_HIG": "Res. Elec. AC Split (Alta)",
    "DEMRESELCAIR_SPL_LOW": "Res. Elec. AC Split (Baja)",
    "DEMRESELCAIR_SPL_MID": "Res. Elec. AC Split (Media)",
    "DEMRESELCAIR_HIG_RUR": "Res. Elec. AC (Alta) Rural",
    "DEMRESELCAIR_HIG_URB": "Res. Elec. AC (Alta) Urb.",
    "DEMRESELCAIR_LOW_RUR": "Res. Elec. AC (Baja) Rural",
    "DEMRESELCAIR_LOW_URB": "Res. Elec. AC (Baja) Urb.",
    "DEMRESELCAIR_MID_RUR": "Res. Elec. AC (Media) Rural",
    "DEMRESELCAIR_MID_URB": "Res. Elec. AC (Media) Urb.",
    "DEMRESELCCKN_HIG": "Res. Elec. Estufa (Alta)",
    "DEMRESELCCKN_LOW": "Res. Elec. Estufa (Baja)",
    "DEMRESELCCKN_MID": "Res. Elec. Estufa (Media)",
    "DEMRESELCCKN_HIG_RUR": "Res. Elec. Estufa (Alta) Rural",
    "DEMRESELCCKN_HIG_URB": "Res. Elec. Estufa (Alta) Urb.",
    "DEMRESELCCKN_LOW_RUR": "Res. Elec. Estufa (Baja) Rural",
    "DEMRESELCCKN_LOW_URB": "Res. Elec. Estufa (Baja) Urb.",
    "DEMRESELCCKN_MID_RUR": "Res. Elec. Estufa (Media) Rural",
    "DEMRESELCCKN_MID_URB": "Res. Elec. Estufa (Media) Urb.",
    "DEMRESELCILU_HIG": "Res. Elec. Ilum. (Alta)",
    "DEMRESELCILU_LOW": "Res. Elec. Ilum. (Baja)",
    "DEMRESELCILU_MID": "Res. Elec. Ilum. (Media)",
    "DEMRESELCILU_HIG_RUR": "Res. Elec. Ilum. (Alta) Rural",
    "DEMRESELCILU_HIG_URB": "Res. Elec. Ilum. (Alta) Urb.",
    "DEMRESELCILU_LOW_RUR": "Res. Elec. Ilum. (Baja) Rural",
    "DEMRESELCILU_LOW_URB": "Res. Elec. Ilum. (Baja) Urb.",
    "DEMRESELCILU_MID_RUR": "Res. Elec. Ilum. (Media) Rural",
    "DEMRESELCILU_MID_URB": "Res. Elec. Ilum. (Media) Urb.",
    "DEMRESELCOTH_HIG": "Res. Elec. Otros (Alta)",
    "DEMRESELCOTH_LOW": "Res. Elec. Otros (Baja)",
    "DEMRESELCOTH_MID": "Res. Elec. Otros (Media)",
    "DEMRESELCOTH_HIG_RUR": "Res. Elec. Otros (Alta) Rural",
    "DEMRESELCOTH_HIG_URB": "Res. Elec. Otros (Alta) Urb.",
    "DEMRESELCOTH_LOW_RUR": "Res. Elec. Otros (Baja) Rural",
    "DEMRESELCOTH_LOW_URB": "Res. Elec. Otros (Baja) Urb.",
    "DEMRESELCOTH_MID_RUR": "Res. Elec. Otros (Media) Rural",
    "DEMRESELCOTH_MID_URB": "Res. Elec. Otros (Media) Urb.",
    "DEMRESELCREF_HIG": "Res. Elec. Refrig. (Alta)",
    "DEMRESELCREF_LOW": "Res. Elec. Refrig. (Baja)",
    "DEMRESELCREF_MID": "Res. Elec. Refrig. (Media)",
    "DEMRESELCREF_HIG_RUR": "Res. Elec. Refrig. (Alta) Rural",
    "DEMRESELCREF_HIG_URB": "Res. Elec. Refrig. (Alta) Urb.",
    "DEMRESELCREF_LOW_RUR": "Res. Elec. Refrig. (Baja) Rural",
    "DEMRESELCREF_LOW_URB": "Res. Elec. Refrig. (Baja) Urb.",
    "DEMRESELCREF_MID_RUR": "Res. Elec. Refrig. (Media) Rural",
    "DEMRESELCREF_MID_URB": "Res. Elec. Refrig. (Media) Urb.",
    "DEMRESELCTV_HIG": "Res. Elec. TV (Alta)",
    "DEMRESELCTV_LOW": "Res. Elec. TV (Baja)",
    "DEMRESELCTV_MID": "Res. Elec. TV (Media)",
    "DEMRESELCTV_CRT": "Res. Elec. TV CRT",
    "DEMRESELCTV_HIG_RUR": "Res. Elec. TV (Alta) Rural",
    "DEMRESELCTV_HIG_URB": "Res. Elec. TV (Alta) Urb.",
    "DEMRESELCTV_LOW_RUR": "Res. Elec. TV (Baja) Rural",
    "DEMRESELCTV_LOW_URB": "Res. Elec. TV (Baja) Urb.",
    "DEMRESELCTV_MID_RUR": "Res. Elec. TV (Media) Rural",
    "DEMRESELCTV_MID_URB": "Res. Elec. TV (Media) Urb.",
    "DEMRESELCWSH_HIG": "Res. Elec. Lavadora (Alta)",
    "DEMRESELCWSH_LOW": "Res. Elec. Lavadora (Baja)",
    "DEMRESELCWSH_MID": "Res. Elec. Lavadora (Media)",
    "DEMRESELCWSH_HIG_RUR": "Res. Elec. Lavadora (Alta) Rural",
    "DEMRESELCWSH_HIG_URB": "Res. Elec. Lavadora (Alta) Urb.",
    "DEMRESELCWSH_LOW_RUR": "Res. Elec. Lavadora (Baja) Rural",
    "DEMRESELCWSH_LOW_URB": "Res. Elec. Lavadora (Baja) Urb.",
    "DEMRESELCWSH_MID_RUR": "Res. Elec. Lavadora (Media) Rural",
    "DEMRESELCWSH_MID_URB": "Res. Elec. Lavadora (Media) Urb.",
    # ── Demanda: Residencial — Cal. de Agua ───────────────────────────────
    "DEMRESELCWHT_HIG": "Res. Elec. Cal.Agua (Alta)",
    "DEMRESELCWHT_LOW": "Res. Elec. Cal.Agua (Baja)",
    "DEMRESELCWHT_MID": "Res. Elec. Cal.Agua (Media)",
    "DEMRESELCWHT_DUC_HIG": "Res. Elec. Ducha (Alta)",
    "DEMRESELCWHT_DUC_LOW": "Res. Elec. Ducha (Baja)",
    "DEMRESELCWHT_DUC_MID": "Res. Elec. Ducha (Media)",
    "DEMRESELCWHT_PAS_HIG": "Res. Elec. Cal.Agua Paso (Alta)",
    "DEMRESELCWHT_PAS_LOW": "Res. Elec. Cal.Agua Paso (Baja)",
    "DEMRESELCWHT_PAS_MID": "Res. Elec. Cal.Agua Paso (Media)",
    "DEMRESELCWHT_TAN_HIG": "Res. Elec. Cal.Agua Tanque (Alta)",
    "DEMRESELCWHT_TAN_LOW": "Res. Elec. Cal.Agua Tanque (Baja)",
    "DEMRESELCWHT_TAN_MID": "Res. Elec. Cal.Agua Tanque (Media)",
    "DEMRESGASWHT_HIG": "Res. Gas Cal.Agua (Alta)",
    "DEMRESGASWHT_LOW": "Res. Gas Cal.Agua (Baja)",
    "DEMRESGASWHT_MID": "Res. Gas Cal.Agua (Media)",
    "DEMRESLPGWHT_HIG": "Res. GLP Cal.Agua (Alta)",
    "DEMRESLPGWHT_LOW": "Res. GLP Cal.Agua (Baja)",
    "DEMRESLPGWHT_MID": "Res. GLP Cal.Agua (Media)",
    "DEMRESSOLWHT_HIG": "Res. Solar Cal.Agua (Alta)",
    "DEMRESSOLWHT_LOW": "Res. Solar Cal.Agua (Baja)",
    "DEMRESSOLWHT_MID": "Res. Solar Cal.Agua (Media)",
    # ── Demanda: Residencial — GLP/GN/Biogás Estufa ───────────────────────
    "DEMRESBGSCKN_HIG": "Res. Biogás Estufa (Alta)",
    "DEMRESBGSCKN_LOW": "Res. Biogás Estufa (Baja)",
    "DEMRESBGSCKN_MID": "Res. Biogás Estufa (Media)",
    "DEMRESLPGCKN_HIG": "Res. GLP Estufa (Alta)",
    "DEMRESLPGCKN_LOW": "Res. GLP Estufa (Baja)",
    "DEMRESLPGCKN_MID": "Res. GLP Estufa (Media)",
    "DEMRESLPGCKN_HIG_RUR": "Res. GLP Estufa (Alta) Rural",
    "DEMRESLPGCKN_HIG_URB": "Res. GLP Estufa (Alta) Urb.",
    "DEMRESLPGCKN_LOW_RUR": "Res. GLP Estufa (Baja) Rural",
    "DEMRESLPGCKN_LOW_URB": "Res. GLP Estufa (Baja) Urb.",
    "DEMRESLPGCKN_MID_RUR": "Res. GLP Estufa (Media) Rural",
    "DEMRESLPGCKN_MID_URB": "Res. GLP Estufa (Media) Urb.",
    "DEMRESNGSCKN_HIG": "Res. GN Estufa (Alta)",
    "DEMRESNGSCKN_LOW": "Res. GN Estufa (Baja)",
    "DEMRESNGSCKN_MID": "Res. GN Estufa (Media)",
    "DEMRESNGSCKN_HIG_RUR": "Res. GN Estufa (Alta) Rural",
    "DEMRESNGSCKN_HIG_URB": "Res. GN Estufa (Alta) Urb.",
    "DEMRESNGSCKN_LOW_RUR": "Res. GN Estufa (Baja) Rural",
    "DEMRESNGSCKN_LOW_URB": "Res. GN Estufa (Baja) Urb.",
    "DEMRESNGSCKN_MID_RUR": "Res. GN Estufa (Media) Rural",
    "DEMRESNGSCKN_MID_URB": "Res. GN Estufa (Media) Urb.",
    # ── Demanda: Residencial — Leña ───────────────────────────────────────
    "DEMRESWOOCKN_HIG": "Res. Leña Estufa (Alta)",
    "DEMRESWOOCKN_LOW": "Res. Leña Estufa (Baja)",
    "DEMRESWOOCKN_MID": "Res. Leña Estufa (Media)",
    "DEMRESWOOCKN_HIG_RUR": "Res. Leña Estufa (Alta) Rural",
    "DEMRESWOOCKN_HIG_URB": "Res. Leña Estufa (Alta) Urb.",
    "DEMRESWOOCKN_LOW_RUR": "Res. Leña Estufa (Baja) Rural",
    "DEMRESWOOCKN_LOW_URB": "Res. Leña Estufa (Baja) Urb.",
    "DEMRESWOOCKN_MID_RUR": "Res. Leña Estufa (Media) Rural",
    "DEMRESWOOCKN_MID_URB": "Res. Leña Estufa (Media) Urb.",
    # ── Demanda: Residencial — ZNI ────────────────────────────────────────
    "DEMRESZNIBGSCKN_MID": "Res. ZNI Biogás Estufa (Media)",
    "DEMRESZNIELCCKN_LOW": "Res. ZNI Elec. Estufa (Baja)",
    "DEMRESZNIELC_LOW": "Res. ZNI Elec. Otros (Baja)",
    "DEMRESZNILPGCKN_LOW": "Res. ZNI GLP Estufa (Baja)",
    "DEMRESZNILPGCKN_MID": "Res. ZNI GLP Estufa (Media)",
    "DEMRESZNIWOOCKN_LOW": "Res. ZNI Leña Estufa (Baja)",
    "DEMRES_MEDPVA_URB": "Res. Solar Autocons. Urb.",
    # ── Demanda: Terciario — Biogás ───────────────────────────────────────
    "DEMTERBGSCKN_HIG": "Ter. Biogás Estufa (Alta)",
    "DEMTERBGSCKN_LOW": "Ter. Biogás Estufa (Baja)",
    "DEMTERBGSCKN_MID": "Ter. Biogás Estufa (Media)",
    # ── Demanda: Terciario — Electricidad ─────────────────────────────────
    "DEMTERELCACL_HIG": "Ter. Elec. Aclimat. (Alta)",
    "DEMTERELCACL_LOW": "Ter. Elec. Aclimat. (Baja)",
    "DEMTERELCACL_MID": "Ter. Elec. Aclimat. (Media)",
    "DEMTERELCAIR_CEN_HIG": "Ter. Elec. AC Central (Alta)",
    "DEMTERELCAIR_CEN_LOW": "Ter. Elec. AC Central (Baja)",
    "DEMTERELCAIR_CEN_MID": "Ter. Elec. AC Central (Media)",
    "DEMTERELCAIR_HIG": "Ter. Elec. AC (Alta)",
    "DEMTERELCAIR_LOW": "Ter. Elec. AC (Baja)",
    "DEMTERELCAIR_SPL_HIG": "Ter. Elec. AC Split (Alta)",
    "DEMTERELCAIR_SPL_LOW": "Ter. Elec. AC Split (Baja)",
    "DEMTERELCAIR_SPL_MID": "Ter. Elec. AC Split (Media)",
    "DEMTERELCBOI": "Ter. Elec. Caldera",
    "DEMTERELCCKN_HIG": "Ter. Elec. Estufa (Alta)",
    "DEMTERELCCKN_LOW": "Ter. Elec. Estufa (Baja)",
    "DEMTERELCCKN_MID": "Ter. Elec. Estufa (Media)",
    "DEMTERELCDATA": "Ter. Elec. DataCtr.",
    "DEMTERELCFAN_HIG": "Ter. Elec. Ventil. (Alta)",
    "DEMTERELCFAN_LOW": "Ter. Elec. Ventil. (Baja)",
    "DEMTERELCFAN_MID": "Ter. Elec. Ventil. (Media)",
    "DEMTERELCILU_CIA": "Ter. Elec. Ilum. Cinta",
    "DEMTERELCILU_HAL": "Ter. Elec. Ilum. Halóg.",
    "DEMTERELCILU_HIG": "Ter. Elec. Ilum. (Alta)",
    "DEMTERELCILU_LFC": "Ter. Elec. Ilum. LFC",
    "DEMTERELCILU_LOW": "Ter. Elec. Ilum. (Baja)",
    "DEMTERELCILU_MID": "Ter. Elec. Ilum. (Media)",
    "DEMTERELCILU_VAP": "Ter. Elec. Ilum. Vapor",
    "DEMTERELCMPW_HIG": "Ter. Elec. Motor (Alta)",
    "DEMTERELCMPW_LOW": "Ter. Elec. Motor (Baja)",
    "DEMTERELCMPW_MID": "Ter. Elec. Motor (Media)",
    "DEMTERELCOTH": "Ter. Elec. Otros",
    "DEMTERELCOTH_HIG": "Ter. Elec. Otros (Alta)",
    "DEMTERELCOTH_LOW": "Ter. Elec. Otros (Baja)",
    "DEMTERELCOTH_MID": "Ter. Elec. Otros (Media)",
    "DEMTERELCREF_AUC_HIG": "Ter. Elec. Refrig. Autoc. (Alta)",
    "DEMTERELCREF_AUC_LOW": "Ter. Elec. Refrig. Autoc. (Baja)",
    "DEMTERELCREF_AUC_MID": "Ter. Elec. Refrig. Autoc. (Media)",
    "DEMTERELCREF_CEN_HIG": "Ter. Elec. Refrig. Central (Alta)",
    "DEMTERELCREF_CEN_LOW": "Ter. Elec. Refrig. Central (Baja)",
    "DEMTERELCREF_CEN_MID": "Ter. Elec. Refrig. Central (Media)",
    "DEMTERELCREF_HIG": "Ter. Elec. Refrig. (Alta)",
    "DEMTERELCREF_LOW": "Ter. Elec. Refrig. (Baja)",
    # ── Demanda: Terciario — Hidrógeno / GLP / GN ────────────────────────
    "DEMTERHDGCKN": "Ter. H₂ Estufa",
    "DEMTERLGPCKN_LOW": "Ter. GLP Estufa (Baja)",
    "DEMTERLPGCKN_HIG": "Ter. GLP Estufa (Alta)",
    "DEMTERLPGCKN_LOW": "Ter. GLP Estufa (Baja)",
    "DEMTERLPGCKN_MID": "Ter. GLP Estufa (Media)",
    "DEMTERNGSBOI_LOW": "Ter. GN Caldera (Baja)",
    "DEMTERNGSCKN_HIG": "Ter. GN Estufa (Alta)",
    "DEMTERNGSCKN_LOW": "Ter. GN Estufa (Baja)",
    # ── Demanda: Transporte — Diésel ──────────────────────────────────────
    "DEMTRADSLBOT": "Tra. Diésel Bote",
    "DEMTRADSLBUS": "Tra. Diésel Bus",
    "DEMTRADSLBUS_ART": "Tra. Diésel Bus Artic.",
    "DEMTRADSLBUS_BIA": "Tra. Diésel Bus Biartic.",
    "DEMTRADSLBUS_IMU": "Tra. Diésel Bus Intermunic.",
    "DEMTRADSLBUS_URB": "Tra. Diésel Bus Urb.",
    "DEMTRADSLFWD": "Tra. Diésel 4x4",
    "DEMTRADSLLDV": "Tra. Diésel Veh.Lig.",
    "DEMTRADSLMIC": "Tra. Diésel Microbús",
    "DEMTRADSLMOT": "Tra. Diésel Moto",
    "DEMTRADSLSHP": "Tra. Diésel Barco",
    "DEMTRADSLSTT": "Tra. Diésel Semirrem.",
    "DEMTRADSLTAX": "Tra. Diésel Taxi",
    "DEMTRADSLTCK": "Tra. Diésel Camión",
    "DEMTRADSLTCK_C2P": "Tra. Diésel Cam. 5.5t",
    "DEMTRADSLTCK_CSG": "Tra. Diésel Cam. 12t",
    # ── Demanda: Transporte — Electricidad ────────────────────────────────
    "DEMTRAELCBOT": "Tra. Elec. Bote",
    "DEMTRAELCBUS": "Tra. Elec. Bus",
    "DEMTRAELCBUS_ART": "Tra. Elec. Bus Artic.",
    "DEMTRAELCBUS_BIA": "Tra. Elec. Bus Biartic.",
    "DEMTRAELCBUS_IMU": "Tra. Elec. Bus Intermunic.",
    "DEMTRAELCBUS_URB": "Tra. Elec. Bus Urb.",
    "DEMTRAELCFWD": "Tra. BEV 4x4",
    "DEMTRAELCLDV": "Tra. BEV Veh.Lig.",
    "DEMTRAELCMET": "Tra. Elec. Metro",
    "DEMTRAELCMIC": "Tra. Elec. Microbús",
    "DEMTRAELCMOT": "Tra. Elec. Moto",
    "DEMTRAELCSTT": "Tra. BEV Semirrem.",
    "DEMTRAELCTAX": "Tra. Elec. Taxi",
    "DEMTRAELCTCK": "Tra. BEV Camión",
    "DEMTRAELCTCK_C2P": "Tra. BEV Cam. 5.5t",
    "DEMTRAELCTCK_CSG": "Tra. BEV Cam. 12t",
    # ── Demanda: Transporte — Fuel Oil ────────────────────────────────────
    "DEMTRAFOLSHP": "Tra. F.Oil Barco",
    # ── Demanda: Transporte — Gasolina ────────────────────────────────────
    "DEMTRAGSLBOT": "Tra. Gasolina Bote",
    "DEMTRAGSLBUS": "Tra. Gasolina Bus",
    "DEMTRAGSLBUS_ART": "Tra. Gasolina Bus Artic.",
    "DEMTRAGSLBUS_IMU": "Tra. Gasolina Bus Intermunic.",
    "DEMTRAGSLFWD": "Tra. Gasolina 4x4",
    "DEMTRAGSLLDV": "Tra. Gasolina Veh.Lig.",
    "DEMTRAGSLMIC": "Tra. Gasolina Microbús",
    "DEMTRAGSLMOT": "Tra. Gasolina Moto",
    "DEMTRAGSLSTT": "Tra. Gasolina Semirrem.",
    "DEMTRAGSLTAX": "Tra. Gasolina Taxi",
    "DEMTRAGSLTCK": "Tra. Gasolina Camión",
    "DEMTRAGSLTCK_C2P": "Tra. Gasolina Cam. 5.5t",
    # ── Demanda: Transporte — Hidrógeno ───────────────────────────────────
    "DEMTRAHDGBUS": "Tra. H₂ Bus",
    "DEMTRAHDGBUS_IMU": "Tra. H₂ Bus Intermunic.",
    "DEMTRAHDGBUS_URB": "Tra. H₂ Bus Urb.",
    "DEMTRAHDGFWD": "Tra. FCEV 4x4",
    "DEMTRAHDGLDV": "Tra. FCEV Veh.Lig.",
    "DEMTRAHDGMIC": "Tra. H₂ Microbús",
    "DEMTRAHDGMOT": "Tra. H₂ Moto",
    "DEMTRAHDGSTT": "Tra. FCEV Semirrem.",
    "DEMTRAHDGTAX": "Tra. H₂ Taxi",
    "DEMTRAHDGTCK": "Tra. FCEV Camión",
    "DEMTRAHDGTCK_CSG": "Tra. FCEV Cam. 12t",
    # ── Demanda: Transporte — Híbridos ────────────────────────────────────
    "DEMTRAHEVFWD": "Tra. HEV 4x4 (Diésel)",
    "DEMTRAHEVLDV": "Tra. HEV Veh.Lig. (GSL)",
    "DEMTRAHYBFWD": "Tra. PHEV 4x4",
    "DEMTRAHYBLDV": "Tra. PHEV Veh.Lig.",
    "DEMTRAHYBTAX": "Tra. PHEV Taxi",
    "DEMTRAHYBTCK": "Tra. PHEV Camión",
    "DEMTRAPHEVFWD": "Tra. PHEV 4x4",
    "DEMTRAPHEVLDV": "Tra. PHEV Veh.Lig.",
    "DEMTRAPHEVTAX": "Tra. PHEV Taxi",
    # ── Demanda: Transporte — Jet / GN / Mezclas ──────────────────────────
    "DEMTRAJETAIR": "Jet Fuel (Queroseno)",
    "DEMTRAJETAVI": "Jet Fuel (Queroseno)",
    "DEMTRAJETSAFAVI": "Jet Sostenible (SAF)",
    "DEMTRANGSBUS": "Tra. GN Bus",
    "DEMTRANGSBUS_ART": "Tra. GN Bus Artic.",
    "DEMTRANGSBUS_BIA": "Tra. GN Bus Biartic.",
    "DEMTRANGSBUS_IMU": "Tra. GN Bus Intermunic.",
    "DEMTRANGSBUS_URB": "Tra. GN Bus Urb.",
    "DEMTRANGSFWD": "Tra. GN 4x4",
    "DEMTRANGSLDV": "Tra. GN Veh.Lig.",
    "DEMTRANGSMIC": "Tra. GN Microbús",
    "DEMTRANGSMOT": "Tra. GN Moto",
    "DEMTRANGSSTT": "Tra. GN Semirrem.",
    "DEMTRANGSTAX": "Tra. GN Taxi",
    "DEMTRANGSTCK": "Tra. GN Camión",
    "DEMTRANGSTCK_C2P": "Tra. GN Cam. 5.5t",
    "DEMTRANGSTCK_CSG": "Tra. GN Cam. 12t",
    # ── Refinerias ────────────────────────────────────────
    "UPSREG": "Importación Gas Natural",
    "UPSREF_BAR": "Refinería Barrancabermeja",
    "UPSREF_CAR": "Refinería Cartagena",
    # ── UPSTREAM y Refinación ─────────────────
    "UPSALK": "Electrólisis Alcalina",
    "UPSPEM": "Electrólisis PEM",
    "UPSSMR": "Reformado Vapor (SMR)",
    "UPSSMRCCS": "Reformado Vapor + CCS (H₂ azul)",
    "UPSSAF": "SAF Hidroprocesado",
    "UPSHDGRST": "Estaciones de Servicio H₂",
    "UPSBJS": "Mezcla JET-SAF",
    "UPSATJ": "Planta Alcohol a Jet",
    # ── H₂ — etiquetas finales para leyenda (sobre-escriben las anteriores) ──
    # Cada serie tiene su propia etiqueta para que la leyenda sea distinguible.
    "DEMDERHDG": "H₂ Petroquímica (derivados)",
    "DEMINDHDGBOI_HIG": "H₂ Industria - Caldera Alta",
    "DEMINDHDGBOI_LOW": "H₂ Industria - Caldera Baja",
    "DEMINDHDGFUR": "H₂ Industria - Horno",
    "DEMTRAHDGTCK_CSG": "H₂ Tractocamión",
    "DEMTRAHDGSTT": "H₂ Semitractor (FCEV)",
    "DEMTRAHDGBUS_IMU": "H₂ Bus Intermunicipal",
    "DEMTRAHDGBUS_URB": "H₂ Bus Urbano",
    "DEMTRAHDGMIC": "H₂ Microbús",
    "DEMTRAHDGFWD": "H₂ Vehículo 4x4",
    "DEMTRAHDGLDV": "H₂ Vehículo Ligero (FCEV)",
    "DEMTRAHDGTAX": "H₂ Taxi",
    # Demanda de exportación: pseudo-demanda que el modelo debe cumplir y que
    # se "despacha" mediante UPSHDGRST en la cara upstream.
    "DEMEXPHDG": "Exportación H₂",
}


# ══════════════════════════════════════════════════════════════════════════
# 3. FUNCIÓN PRINCIPAL DE RESOLUCIÓN
# ══════════════════════════════════════════════════════════════════════════


def _dynamic_label(code: str) -> str:
    """
    Genera un label dinámico para códigos no registrados en DISPLAY_NAMES.
    Descompone el código en sus partes y construye un nombre legible.

    Se aplica solo como fallback cuando el código no está en el diccionario.
    """
    # Intentar label de grupo (NGS, DSL, ELC…)
    if code in _GRUPO:
        return _GRUPO[code]

    parts: list[str] = []
    rest = code

    # Detectar sufijos de eficiencia y área (en orden inverso de especificidad)
    suffix_label = ""
    area_label = ""

    for suffix, label in _EFIC.items():
        if rest.endswith(suffix):
            suffix_label = label
            rest = rest[: -len(suffix)]
            break

    for suffix, label in _AREA.items():
        if rest.endswith(suffix):
            area_label = label
            rest = rest[: -len(suffix)]
            break

    # Detectar categoría por prefijo
    for prefix, abbr in _CAT_PREFIX.items():
        if rest.startswith(prefix):
            parts.append(abbr)
            rest = rest[len(prefix) :]
            break

    # Detectar energético
    for eng_code, eng_label in _ENERGETICO.items():
        if rest.startswith(eng_code):
            parts.append(eng_label)
            rest = rest[len(eng_code) :]
            break

    # Detectar tecnología de uso
    for uso_code, uso_label in _USO.items():
        if rest.startswith(uso_code) or rest == uso_code:
            parts.append(uso_label)
            break

    if area_label:
        parts.append(area_label)
    if suffix_label:
        parts.append(suffix_label)

    result = " ".join(parts).strip()
    return result if result else code  # fallback final: código original


def get_label(code: str) -> str:
    """
    Retorna el display_name para un código de tecnología OSeMOSYS.

    Parámetros
    ----------
    code : str
        Código de tecnología (ej: "DEMINDCOABOI_LOW", "PWRSOLRTP", "NGS").

    Retorna
    -------
    str
        Nombre legible para mostrar en gráficas.
        Nunca lanza excepción: retorna el código original si no hay mapeo.

    Ejemplos
    --------
    >>> get_label("DEMINDCOABOI_LOW")
    'Ind. Carbón Caldera (Baja)'
    >>> get_label("PWRSOLRTP_ZNI")
    'Solar FV Techo ZNI'
    >>> get_label("NGS")
    'Gas Natural'
    >>> get_label("CODIGO_DESCONOCIDO")
    'CODIGO_DESCONOCIDO'
    """
    if not code:
        return code

    # 1. Búsqueda exacta
    label = DISPLAY_NAMES.get(code)
    if label:
        return label

    # 2. Búsqueda en grupos de combustible (para agrupación COMBUSTIBLE)
    label = _GRUPO.get(code)
    if label:
        return label

    # 3. Generación dinámica
    return _dynamic_label(code)


def get_labels_batch(codes: list[str]) -> dict[str, str]:
    """
    Versión batch de get_label para mayor eficiencia cuando se procesan
    muchos códigos a la vez.

    Retorna un dict {codigo: display_name}.
    """
    return {code: get_label(code) for code in codes}
