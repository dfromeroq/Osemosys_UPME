"""
Colores para gráficas OSeMOSYS.

Basado en osemosys_src/src/colors.py, pero sin dependencias de
matplotlib ni numpy — usa solo colorsys (stdlib).
"""

import colorsys


# ══════════════════════════════════════════════════════════════════════════
# Utilidades internas de conversión de color (reemplazan matplotlib)
# ══════════════════════════════════════════════════════════════════════════


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    """Convierte '#RRGGBB' → (r, g, b) en rango [0, 1]."""
    h = hex_color.lstrip("#")
    return (
        int(h[0:2], 16) / 255.0,
        int(h[2:4], 16) / 255.0,
        int(h[4:6], 16) / 255.0,
    )


def _rgb_to_hex(r: float, g: float, b: float) -> str:
    """Convierte (r, g, b) en rango [0, 1] → '#rrggbb'."""
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Restringe *value* al rango [lo, hi] (reemplaza np.clip)."""
    return max(lo, min(hi, value))


# ══════════════════════════════════════════════════════════════════════════
# 1. COLORES PARA ELECTRICIDAD (POR FAMILIAS)
# ══════════════════════════════════════════════════════════════════════════

FAMILIAS_TEC = {
    "SOLAR": [
        "PWRSOLRTP",
        "PWRSOLRTP_ZNI",
        "PWRSOLUGE",
        "PWRSOLUGE_BAT",
        "PWRSOLUPE",
    ],
    "HIDRO": [
        "PWRHYDDAM",
        "PWRHYDROR",
        "PWRHYDROR_NDC",
    ],
    "EOLICA": [
        "PWRWNDONS",
        "PWRWNDOFS_FIX",
        "PWRWNDOFS_FLO",
    ],
    "TERMICA_FOSIL": [
        "PWRCOA",
        "PWRCOACCS",
        # ``PWRNGS`` es la tecnología consolidada que aparece en charts donde
        # se aplica ``PWR_TECH_ALIASES`` (cap_electricidad / prd_electricidad
        # / elec_produccion). Agrupa NGS_CC + NGS_CS + NGSCCS + JET + LPG.
        # En el resto de charts NGS_CC/NGS_CS/NGSCCS/JET/LPG conservan su
        # color individual.
        "PWRNGS",
        "PWRNGS_CC",
        "PWRNGS_CS",
        "PWRNGSCCS",
        "PWRDSL",
        "PWRFOL",
        "PWRJET",
        "PWRLPG",
    ],
    "NUCLEAR": [
        "PWRNUC",
    ],
    "BIOMASA_RESIDUOS": [
        "PWRAFR",
        "PWRBGS",
        "PWRWAS",
    ],
    "OTRAS": [
        "PWRCSP",
        "PWRGEO",
        "PWRSTD",
    ],
}

COLOR_BASE_FAMILIA = {
    "SOLAR": "#FDB813",  # amarillo solar intenso
    "HIDRO": "#1F77B4",  # azul hidro
    "EOLICA": "#2CA02C",  # verde eólico
    "TERMICA_FOSIL": "#2B2B2B",  # casi negro (carbón/gas)
    "NUCLEAR": "#7B3F98",  # violeta nuclear
    "BIOMASA_RESIDUOS": "#8C6D31",
    "OTRAS": "#17BECF",  # cian técnico
}


def generar_tonos(color_hex: str, n: int) -> list[str]:
    """Genera *n* tonos de un color base variando luminosidad."""
    color_hex = color_hex.lstrip("#")
    r, g, b = (int(color_hex[i : i + 2], 16) / 255 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)

    tonos: list[str] = []
    for i in range(n):
        # Luminosidad controlada
        li = 0.35 + 0.35 * i / max(1, n - 1)

        # Mantener saturación baja para térmicas
        si = s if s < 0.2 else min(1.0, s * 1.05)

        ri, gi, bi = colorsys.hls_to_rgb(h, li, si)
        tonos.append(f"#{int(ri * 255):02x}{int(gi * 255):02x}{int(bi * 255):02x}")

    return tonos


def construir_color_map_por_familias(
    familias: dict[str, list[str]],
    colores_base: dict[str, str],
) -> dict[str, str]:
    """Construye mapeo tecnología → color basado en familias."""
    color_map: dict[str, str] = {}

    for familia, tecnologias in familias.items():
        base_color = colores_base[familia]
        tonos = generar_tonos(base_color, len(tecnologias))

        for tech, color in zip(tecnologias, tonos):
            color_map[tech] = color

    return color_map


# MAPA DE COLORES PARA ELECTRICIDAD
COLOR_MAP_PWR = construir_color_map_por_familias(
    FAMILIAS_TEC,
    COLOR_BASE_FAMILIA,
)

# Swap de colores entre Solar Rooftop (RTP) y Solar Utility + Batería.
# Decisión de producto: el color oscuro original de RTP queda asignado a la
# tecnología con baterías; RTP toma el tono más claro que tenía la BAT.
_orig_rtp = COLOR_MAP_PWR["PWRSOLRTP"]
_orig_bat = COLOR_MAP_PWR["PWRSOLUGE_BAT"]
COLOR_MAP_PWR["PWRSOLRTP"] = _orig_bat
COLOR_MAP_PWR["PWRSOLUGE_BAT"] = _orig_rtp
del _orig_rtp, _orig_bat

# Override colores de tecnologías eléctricas con paleta explícita
COLOR_MAP_PWR["PWRGEO"] = "#ff0001"
COLOR_MAP_PWR["PWRWNDOFS_FIX"] = "#e2c5fe"
COLOR_MAP_PWR["PWRWNDOFS_FLO"] = "#e2c5fe"
COLOR_MAP_PWR["PWRWNDONS"] = "#7031a0"
COLOR_MAP_PWR["PWRSOLRTP"] = "#ffc000"
COLOR_MAP_PWR["PWRSOLRTP_ZNI"] = "#cc9b00"
COLOR_MAP_PWR["PWRSOLUGE_BAT"] = "#ff9901"
COLOR_MAP_PWR["PWRSOLUPE"] = "#feefa2"
COLOR_MAP_PWR["PWRSOLUGE"] = "#feefa2"
COLOR_MAP_PWR["PWRHYDROR"] = "#9dc2e6"
COLOR_MAP_PWR["PWRHYDROR_NDC"] = "#9dc2e6"
COLOR_MAP_PWR["PWRHYDDAM"] = "#4572c5"
for _tech in ("PWRCOA", "PWRCOACCS", "PWRNGS_CC", "PWRNGS_CS",
              "PWRNGSCCS", "PWRDSL", "PWRFOL", "PWRJET", "PWRLPG"):
    COLOR_MAP_PWR[_tech] = "#777071"
del _tech

_TECHS_CLASIFICADAS: frozenset[str] = frozenset(
    t for fam in FAMILIAS_TEC.values() for t in fam
)


# ══════════════════════════════════════════════════════════════════════════
# 2. COLORES PARA OTROS SECTORES (POR COMBUSTIBLE)
# ══════════════════════════════════════════════════════════════════════════

COLORES_GRUPOS = {
    "NGS": "#d9d9d9",
    # JETSAF debe ir ANTES de "JET" para que asignar_grupo("JETSAF") no
    # haga match con "JET" (substring) antes de llegar a la clave específica.
    "JETSAF": "#00ba55",
    "JET": "#375e67",
    "BGS": "#2a7e29",
    "BDL": "#d62728",
    "WAS": "#9467bd",
    "WOO": "#ff9901",
    "GSL": "#abbdd9",
    "COA": "#000000",
    "ELC": "#ffd519",
    "BAG": "#70ad47",
    "DSL": "#415e89",
    "LPG": "#4c98d9",
    "FOL": "#98df8a",
    "AUT": "#ff9896",
    # Crudos (FUEL en UseByTechnology para refinerías).
    # Deben ir ANTES de "OIL" para que asignar_grupo haga match específico
    # (itera por orden de inserción y "OIL" in "OIL_1LIV" sería True).
    "OIL_3PES": "#1f2937",  # Crudo pesado — gris muy oscuro
    "OIL_2MID": "#4b5563",  # Crudo intermedio — gris medio
    "OIL_1LIV": "#9ca3af",  # Crudo liviano — gris claro
    "OIL": "#000000",
    "PHEV": "#c5b0d5",
    "HEV": "#f7b6d2",
    "SAF": "#00ba55",
    "BJS": "#e5c494",
    "OPL": "#b3b3b3",
    "AFR": "#fbb4ae",
    "SGC": "#b3cde3",
    # Hidrógeno (HDG002 debe ir antes que HDG para asignar_grupo)
    "HDG002": "#01ffff",
    "HDG": "#01ffff",
    # Petróleos/crudos (orden específico: más largo primero; escala de grises)
    "MINOIL_3PES": "#2d2d2d",  # Crudo pesado - gris oscuro
    "MINOIL_2MID": "#5c5c5c",  # Crudo intermedio - gris medio
    "MINOIL_1LIV": "#8c8c8c",  # Crudo liviano - gris claro
    "MINOIL": "#b0b0b0",  # Petróleo/crudo genérico - gris muy claro
    
    # Sectores pequeños (fallback cuando no hay combustible en nombre)
    "DEMCON": "#6c757d",
    "DEMAGF": "#28a745",
    "DEMMIN": "#fd7e14",
    "DEMCOQ": "#6f42c1",

    # Transporte — grupos para agrupación TRANSPORTE_GRUPO
    "Motos":       "#e6194b",
    "Livianos":    "#3cb44b",
    "Buses":       "#ffe119",
    "Microbuses":  "#911eb4",
    "Carga":       "#46f0f0",
    "Barcos":      "#f032e6",
    "Metro":       "#008080",
    "Aviación":    "#e6beff",
    "Otros":       "#808080",
}


def asignar_grupo(nombre: str) -> str:
    """Retorna la clave del combustible que aparece dentro de *nombre*."""
    for grupo in COLORES_GRUPOS:
        if grupo in nombre:
            return grupo
    return "OTRO"


def generar_colores_tecnologias(df, columna: str = "COLOR"):
    """Genera paleta de colores agrupada por combustible base.

    Usa solo colorsys (stdlib) en lugar de matplotlib/numpy.
    """
    df = df.copy()
    df["GRUPO"] = df[columna].apply(asignar_grupo)
    color_dict: dict[str, str] = {}
    orden_final: list[str] = []

    for grupo in sorted(df["GRUPO"].unique()):
        subitems = sorted(df[df["GRUPO"] == grupo][columna].unique())
        base_color = COLORES_GRUPOS.get(grupo, "#999999")
        rgb = _hex_to_rgb(base_color)
        h, l, s = colorsys.rgb_to_hls(*rgb)
        n = len(subitems)

        for i, item in enumerate(subitems):
            if n <= 3:
                factor = 0.6 + 0.2 * (i / max(n - 1, 1))
                l_adj = _clamp(l * factor)
                new_rgb = colorsys.hls_to_rgb(h, l_adj, s)
            else:
                hue_shift = (i / n) * 0.15
                lightness_shift = 0.45 + 0.4 * (i / (n - 1))
                new_rgb = colorsys.hls_to_rgb((h + hue_shift) % 1.0, lightness_shift, s)

            # Clamp each channel to [0, 1] then convert to hex
            clamped = tuple(_clamp(c) for c in new_rgb)
            color_dict[item] = _rgb_to_hex(*clamped)
            orden_final.append(item)

    return [color_dict[c] for c in orden_final], orden_final


_COLOR_FALLBACK = "#999999"


def _ordered_color_list(
    color_dict: dict[str, str], df, columna: str
) -> tuple[list[str], list[str]]:
    """Orden preservado de un dict de colores, con fallback para desconocidos."""
    grupos_set = set(df[columna].dropna().unique())
    orden = [k for k in color_dict if k in grupos_set]
    for g in grupos_set:
        if g not in color_dict:
            orden.append(g)
    return [color_dict.get(g, _COLOR_FALLBACK) for g in orden], orden


def _color_por_sector(df, columna: str = "COLOR"):
    """Paleta fija según COLORES_SECTOR — para gráficas agrupadas por sector."""
    from app.visualization.configs_comparacion import COLORES_SECTOR  # lazy: evita circular
    return _ordered_color_list(COLORES_SECTOR, df, columna)


# ══════════════════════════════════════════════════════════════════════════
# 4. COLORES PARA TIPOS DE EMISIÓN (contaminantes y GEI)
# ══════════════════════════════════════════════════════════════════════════

COLORES_EMISIONES = {
    "EMIC02":    "#e67e22",  # CO₂ - naranja
    "EMICH4":    "#e74c3c",  # CH₄ - rojo
    "EMIN2O":    "#8e44ad",  # N₂O - morado
    "EMIBC":     "#2c3e50",  # Black Carbon - gris muy oscuro
    "EMICO":     "#e91e8c",  # CO - magenta/fucsia
    "EMICOVDM":  "#7f7f7f",  # COV - gris
    "EMINH3":    "#aec7e8",  # NH₃ - azul claro
    "EMINOx":    "#7b3f00",  # NOx - marrón
    "EMIPM10":   "#ff69b4",  # PM10 - rosa
    "EMIPM2_5":  "#d62728",  # PM2.5 - rojo medio
    "EMISOx":    "#9467bd",  # SOx - violeta
}


def _color_por_emision(df, columna: str = "COLOR"):
    """Paleta fija por tipo de emisión (GEI y contaminantes criterio)."""
    return _ordered_color_list(COLORES_EMISIONES, df, columna)


def _color_por_grupo_fijo(df, columna: str = "COLOR"):
    """Paleta fija según COLORES_GRUPOS — para gas y refinerías."""
    grupos_presentes = df[columna].unique()
    colores = [COLORES_GRUPOS.get(g, _COLOR_FALLBACK) for g in grupos_presentes]
    return colores, list(grupos_presentes)


# ══════════════════════════════════════════════════════════════════════════
# 5. PALETAS FIJAS POR TECNOLOGÍA (gráficas con tecnologías específicas)
# ══════════════════════════════════════════════════════════════════════════

# Electrólisis (H₂ verde). Los electrolizadores siempre van en tonos verdes.
COLOR_MAP_ELECTROLISIS: dict[str, str] = {
    "UPSALK": "#16a34a",  # Electrólisis Alcalina — verde medio
    "UPSPEM": "#22c55e",  # Electrólisis PEM — verde claro
}

# Producción de H₂ por tipo (clasificación cromática del H₂):
#   • verde  → electrólisis con renovables (UPSALK, UPSPEM)
#   • azul   → SMR con captura (UPSSMRCCS)
#   • gris   → SMR sin captura (UPSSMR)
COLOR_MAP_PRODUCCION_H2: dict[str, str] = {
    # H₂ verde
    "UPSALK":    "#16a34a",  # Electrólisis Alcalina — verde medio
    "UPSPEM":    "#22c55e",  # Electrólisis PEM — verde claro
    # H₂ azul
    "UPSSMRCCS": "#1d4ed8",  # SMR + CCS — azul oscuro
    # H₂ gris
    "UPSSMR":    "#6b7280",  # SMR sin captura — gris medio
}

# Consumo de H₂ por sector/uso. Paleta categórica (cool=industria,
# warm=transporte) — el color NO codifica green/blue (eso aplica solo a
# producción) sino el sector que demanda el H₂.
COLOR_MAP_H2_CONSUMO: dict[str, str] = {
    # ── Industria / Petroquímica (cool tones) ─────────────────────────────
    "DEMDERHDG":         "#831843",  # H₂ Petroquímica (derivados) — magenta oscuro
    "DEMINDHDGBOI_HIG":  "#1e40af",  # Industria caldera alta — azul oscuro
    "DEMINDHDGBOI_LOW":  "#3b82f6",  # Industria caldera baja — azul medio
    "DEMINDHDGFUR":      "#06b6d4",  # Industria horno — cian
    # ── Transporte (warm tones — gama rojo→amarillo dorado) ───────────────
    "DEMTRAHDGTCK_CSG":  "#dc2626",  # Tractocamión — rojo intenso
    "DEMTRAHDGSTT":      "#ef4444",  # Semitractor (FCEV) — rojo
    "DEMTRAHDGBUS_IMU":  "#f97316",  # Bus intermunicipal — naranja
    "DEMTRAHDGBUS_URB":  "#fb923c",  # Bus urbano — naranja claro
    "DEMTRAHDGMIC":      "#f59e0b",  # Microbús — ámbar
    "DEMTRAHDGFWD":      "#fbbf24",  # Vehículo 4x4 — amarillo-ámbar
    "DEMTRAHDGLDV":      "#facc15",  # Vehículo ligero (FCEV) — amarillo
    "DEMTRAHDGTAX":      "#eab308",  # Taxi — amarillo dorado
    # ── Otros usos ────────────────────────────────────────────────────────
    "UPSHDGRST":         "#7c3aed",  # Exportación H₂ (upstream) — violeta vibrante
    "DEMEXPHDG":         "#a78bfa",  # Exportación H₂ (demanda)  — violeta claro
    # Las técnicas de producción pueden aparecer también en UseByTechnology
    # (consumo eléctrico de los electrolizadores). Mantenemos los colores de
    # producción para que la lectura sea consistente entre los dos charts.
    "UPSALK":    "#16a34a",  # verde medio
    "UPSPEM":    "#22c55e",  # verde claro
    "UPSSMR":    "#6b7280",  # gris
    "UPSSMRCCS": "#1d4ed8",  # azul oscuro
    # SAF (no es H₂ puro pero a veces aparece en filtros relacionados)
    "UPSSAF":    "#a3e635",  # lima — diferenciado del verde de electrólisis
}

COLOR_MAP_BIOENERGIA: dict[str, str] = {
    "MINBAG":     "#217a28",  # Bagazo de Caña — verde oscuro
    "MINWAS":     "#7030a0",  # Residuos Sólidos — morado
    "MINOPL":     "#f4a096",  # Aceite de Palma (biodiésel) — salmón
    "MINWAS_ORG": "#c0b0e8",  # Residuos Orgánicos — lavanda
    "MINSGC":     "#c8dc1a",  # Caña de Azúcar (bioetanol) — amarillo-verde
    "MINWOO":     "#8b4513",  # Madera / Leña — marrón oscuro
}

COLOR_MAP_GAS_PROD: dict[str, str] = {
    "MINNGS":  "#4472c4",  # Gas Natural Nacional — azul
    "UPSREG":  "#e85020",  # Importación de Gas Natural — rojo-naranja
    "IMPLNG":  "#c44e52",  # Importación GNL — rojo
    "EXPNGS":  "#4c72b0",  # Exportación Gas Natural — azul
}

COLOR_MAP_LIQUIDOS_IMPORT: dict[str, str] = {
    "IMPDSL":     "#3050b0",  # Importación Diésel — azul marino
    "IMPGSL":     "#e04010",  # Importación Gasolina — rojo-naranja
    "IMPJET":     "#1a7a3a",  # Importación Jet Fuel — verde oscuro
    "IMPLPG":     "#7030a0",  # Importación GLP — morado
    "UPSREF_BAR": "#f5a61e",  # Refinería Barrancabermeja — naranja
    "UPSREF_CAR": "#00bcd4",  # Refinería Cartagena — cian
    # Exportaciones (pueden aparecer en variantes del filtro)
    "EXPDSL":     "#6080d0",
    "EXPGSL":     "#f07050",
    "EXPJET":     "#4aaa6a",
    "EXPLPG":     "#a060c0",
    "IMPOIL":     "#8B4513",  # Importación Petróleo — marrón
    "EXPOIL":     "#CD853F",  # Exportación Petróleo — marrón claro
}


def _make_color_fn_fija(color_map: dict[str, str]):
    """Devuelve una función color_fn que usa un mapa tecnología → color fijo."""
    def _fn(df, columna: str = "COLOR"):
        return _ordered_color_list(color_map, df, columna)
    return _fn


_color_electrolisis    = _make_color_fn_fija(COLOR_MAP_ELECTROLISIS)
_color_h2_produccion   = _make_color_fn_fija(COLOR_MAP_PRODUCCION_H2)
_color_h2_consumo      = _make_color_fn_fija(COLOR_MAP_H2_CONSUMO)
_color_bioenergia      = _make_color_fn_fija(COLOR_MAP_BIOENERGIA)
_color_gas_produccion  = _make_color_fn_fija(COLOR_MAP_GAS_PROD)
_color_liquidos_import = _make_color_fn_fija(COLOR_MAP_LIQUIDOS_IMPORT)


# Paleta fija para agrupación TRANSPORTE_GRUPO
_color_transporte_grupo = _make_color_fn_fija(COLORES_GRUPOS)


# ══════════════════════════════════════════════════════════════════════════
# 3. FUNCIÓN ESPECÍFICA PARA ELECTRICIDAD
# ══════════════════════════════════════════════════════════════════════════


def _color_electricidad(df, columna: str = "COLOR"):
    """
    Aplica colores por familias a tecnologías de generación eléctrica.

    Usa COLOR_MAP_PWR que agrupa tecnologías por familia
    (Solar, Hidro, Eólica, Térmica Fósil, Nuclear, Biomasa, Otras).
    """
    tecnologias_presentes = df[columna].unique()

    # Orden de stack para gráficas del sector eléctrico, **de abajo a arriba**:
    #   viento → solar → hídrica → nuclear → térmicas (fósiles) → biomasa → otras.
    # Highcharts (convención por defecto) y nuestros renders matplotlib
    # apilan la PRIMERA serie en la parte de ARRIBA del stack. Por tanto,
    # para que viento aparezca abajo, la lista se enumera en orden inverso
    # (térmicas primero = top; eólica última visible = bottom).
    orden_familias = [
        "OTRAS",
        "BIOMASA_RESIDUOS",
        "TERMICA_FOSIL",
        "NUCLEAR",
        "HIDRO",
        "SOLAR",
        "EOLICA",
    ]

    # Crear orden basado en familias
    orden_final: list[str] = []
    for familia in orden_familias:
        techs_familia = [t for t in FAMILIAS_TEC[familia] if t in tecnologias_presentes]
        orden_final.extend(sorted(techs_familia))

    techs_no_clasificadas = [
        t for t in tecnologias_presentes if t not in _TECHS_CLASIFICADAS
    ]
    orden_final.extend(sorted(techs_no_clasificadas))

    # Generar lista de colores en el orden correcto
    colores = [COLOR_MAP_PWR.get(t, "#CCCCCC") for t in orden_final]

    return colores, orden_final


# ══════════════════════════════════════════════════════════════════════════
# 4. CHART "ref_import" — REFINERÍAS (gama por refinería × combustible)
# ══════════════════════════════════════════════════════════════════════════
#
# Cada refinería tiene un color base (alta saturación, distinto entre sí) y
# cada combustible producido por esa refinería usa una gama (tono) de ese color
# base. Las importaciones conservan su color fijo de ``COLOR_MAP_LIQUIDOS_IMPORT``.
#
# Para modificar los colores manualmente: editar este diccionario.
#   • Cambiar la clave de una refinería → cambia su gama (color base).
#   • Cambiar la lista de FUELS_REF_ORDER → cambia el orden y, por tanto, la
#     intensidad asignada a cada combustible (más tarde en la lista = tono más
#     claro). Cuanto más alto el índice del fuel, más claro el tono.

REF_GAMA_BASE: dict[str, str] = {
    # Cartagena → azul saturado profundo.
    "UPSREF_CAR": "#0d3a8c",
    # Barrancabermeja → rojo carmín saturado (alto contraste con el azul).
    "UPSREF_BAR": "#b8001d",
}

# Orden esperado de combustibles producidos por una refinería. Determina la
# variación de luminosidad: el primero de la lista usa el tono más oscuro,
# el último el más claro. Combustibles no listados se agregan al final por
# orden alfabético.
FUELS_REF_ORDER: list[str] = [
    "DSL",   # Diésel
    "GSL",   # Gasolina
    "JET",   # Jet Fuel
    "LPG",   # GLP
    "FUO",   # Fuel Oil
    "OIL",   # Crudo / nafta
    "NGS",   # Gas natural
]


#: Orden de stack vertical de las refinerías de **abajo hacia arriba**.
#: La convención visual sigue a Highcharts: el PRIMER elemento del array de
#: series queda arriba. Así que insertamos las series en color_map en orden
#: top→bottom, y este listado se interpreta bottom→top para la lógica humana.
REF_STACK_BOTTOM_TO_TOP: list[str] = [
    "UPSREF_CAR",   # Cartagena → abajo
    "UPSREF_BAR",   # Barrancabermeja → al medio
]


def _color_ref_import(df, columna: str = "COLOR"):
    """Color function para ``ref_import``.

    Acepta valores de COLOR de tres formas:
      • ``IMP*`` → color fijo desde ``COLOR_MAP_LIQUIDOS_IMPORT``.
      • ``UPSREF_XXX::FUEL`` → tono de la gama de esa refinería.
      • ``UPSREF_XXX`` (sin fuel) → color base de la refinería.

    Orden de stack (abajo → arriba): según ``REF_STACK_ORDER`` para refinerías
    y luego las importaciones (IMP*).
    """
    grupos = list(df[columna].unique())

    # Particiona por refinería para asignar un tono distinto a cada fuel.
    refs_to_fuels: dict[str, list[str]] = {}
    for g in grupos:
        if "::" in g:
            ref_id, fuel = g.split("::", 1)
            if ref_id.startswith("UPSREF"):
                refs_to_fuels.setdefault(ref_id, []).append(fuel)

    # En Highcharts, el primer elemento de series[] queda en la parte de arriba.
    # ``REF_STACK_BOTTOM_TO_TOP`` lista las refinerías de abajo hacia arriba —
    # así que para insertar en color_map en orden top→bottom, lo recorremos en
    # reverso. Otras refinerías no listadas se agregan al final (más abajo).
    ordered_ref_ids: list[str] = []
    for r in reversed(REF_STACK_BOTTOM_TO_TOP):
        if r in refs_to_fuels:
            ordered_ref_ids.append(r)
    for r in refs_to_fuels.keys():
        if r not in ordered_ref_ids:
            ordered_ref_ids.append(r)

    color_map: dict[str, str] = {}
    # Importaciones primero → quedan arriba. El usuario las quiere encima de
    # las refinerías. Solo poblamos las claves que existan en grupos.
    for g in grupos:
        if g in COLOR_MAP_LIQUIDOS_IMPORT and not g.startswith("UPSREF"):
            color_map[g] = COLOR_MAP_LIQUIDOS_IMPORT[g]
    for ref_id in ordered_ref_ids:
        fuels = refs_to_fuels[ref_id]
        base = REF_GAMA_BASE.get(ref_id, COLOR_MAP_LIQUIDOS_IMPORT.get(ref_id, "#999999"))
        ordered_fuels: list[str] = []
        seen: set[str] = set()
        # Primero los fuels del orden canónico que estén presentes
        for f in FUELS_REF_ORDER:
            if f in fuels and f not in seen:
                ordered_fuels.append(f)
                seen.add(f)
        # Luego los no listados, alfabético
        for f in sorted(fuels):
            if f not in seen:
                ordered_fuels.append(f)
                seen.add(f)
        tonos = generar_tonos(base, max(2, len(ordered_fuels)))
        # Tomamos los tonos del medio/oscuro hacia el más claro para mantener
        # contraste fuerte; saltamos el más claro extremo.
        for i, f in enumerate(ordered_fuels):
            color_map[f"{ref_id}::{f}"] = tonos[i % len(tonos)]
        # Color base sin fuel (defensivo) → tono más oscuro.
        color_map[ref_id] = tonos[0]

    # Cualquier serie restante (no importación, no refinería listada) se
    # agrega al final con un color fallback gris.
    for g in grupos:
        if g not in color_map:
            color_map[g] = "#999999"

    return _ordered_color_list(color_map, df, columna)
