"""
Configuraciones para gráficas de comparación multi-escenario.

Basado en osemosys_src/src/configs_comparacion.py.
Cambio: imports ajustados al paquete backend (app.visualization.colors).
El resto se mantiene sin cambios — no hay lambdas, solo prefijos string.
"""

# ══════════════════════════════════════════════════════════════════════════════
# MAPEO Y COLORES DE SECTOR
# (exclusivo de este módulo — no existe en colors.py)
# ══════════════════════════════════════════════════════════════════════════════

# Prefijo de TECHNOLOGY (6 chars) → nombre formal del sector
MAPA_SECTOR = {
    'DEMRES': 'Residencial',
    'DEMIND': 'Industrial',
    'DEMTRA': 'Transporte',
    'DEMTER': 'Terciario',
    'DEMCON': 'Construcción',
    'DEMAGF': 'Agroforestal',
    'DEMMIN': 'Minería',
    'DEMCOQ': 'Coquerías',
}

# Colores fijos para cada sector (usados cuando agrupacion='SECTOR')
COLORES_SECTOR = {
    'Residencial':              '#58bbf0',
    'Industrial':               '#fe5026',
    'Transporte':               '#fed519',
    'Terciario':                '#38cfd4',
    'Construcción':             '#d62728',
    'Agroforestal':             '#8c564b',
    'Minería':                  '#e377c2',
    'Coquerías':                '#a98800',
    'Generación Electricidad':  '#f5c518',
}


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGS
#
# Campos de cada config:
#
#   titulo_base         str         Texto base del título de la figura
#   figura_base         str         Etiqueta de figura (cuando numero_figura es None)
#   filename_base       str         Nombre base del archivo de salida
#   print_base          str         Texto del encabezado en consola
#
#   prefijo             str|tuple   Prefijo(s) de TECHNOLOGY a filtrar.
#                                   tuple → multi-sector (str.startswith acepta tuplas)
#
#   tiene_sub_filtro    bool        True si el config acepta filtro por modo/uso
#   label_sub_filtro    str|None    Etiqueta del sub_filtro en consola ('Modo', 'Uso')
#   tiene_loc           bool        True si acepta filtro URB/RUR/ZNI
#                                   (solo sector residencial)
#
#   año_historico_unico bool        True  → año histórico tomado solo del primer escenario
#                                   False → todos los años de todos los escenarios
#
#   agrupacion_default  str         Agrupación cuando el usuario no especifica:
#                                   'TECNOLOGIA' | 'COMBUSTIBLE' | 'SECTOR'
#   agrupacion_fija     str|None    None → usuario puede sobreescribir con agrupacion=
#                                   str  → agrupación bloqueada (ignora agrupacion=)
#
#   msg_sin_datos       str         Mensaje cuando el filtro no encuentra datos
#
#   variable_default    str         Nombre de la variable en BD (chart_service la usa)
# ══════════════════════════════════════════════════════════════════════════════

CONFIGS_COMPARACION = {

    # ════════════════════════════════════════════════════════════════════════
    # TRANSPORTE  (Figuras 3 y 4)
    # ════════════════════════════════════════════════════════════════════════
    'tra_comparacion': {
        'titulo_base':         'Sector Transporte',
        'figura_base':         'Fig3-4',
        'filename_base':       'Fig_Transporte_Comparacion',
        'print_base':          'TRANSPORTE — COMPARACIÓN POR ESCENARIO',
        'prefijo':             'DEMTRA',
        'tiene_sub_filtro':    True,
        'label_sub_filtro':    'Modo',
        'tiene_loc':           False,
        'año_historico_unico': True,
        'agrupacion_default':  'COMBUSTIBLE',
        'agrupacion_fija':     None,
        'msg_sin_datos':       'Sin tecnologías de transporte (DEMTRA)',
        'variable_default':    'UseByTechnology',
    },

    # ════════════════════════════════════════════════════════════════════════
    # INDUSTRIAL  (Figuras 6 y 7)
    # ════════════════════════════════════════════════════════════════════════
    'ind_comparacion': {
        'titulo_base':         'Sector Industrial',
        'figura_base':         'Fig6-7',
        'filename_base':       'Fig_Industrial_Comparacion',
        'print_base':          'INDUSTRIAL — COMPARACIÓN POR ESCENARIO',
        'prefijo':             'DEMIND',
        'tiene_sub_filtro':    True,
        'label_sub_filtro':    'Uso',
        'tiene_loc':           False,
        'año_historico_unico': True,
        'agrupacion_default':  'COMBUSTIBLE',
        'agrupacion_fija':     None,
        'msg_sin_datos':       'Sin tecnologías industriales (DEMIND)',
        'variable_default':    'UseByTechnology',
    },

    # ════════════════════════════════════════════════════════════════════════
    # RESIDENCIAL  (Figuras 9 y 10)
    # Único sector con soporte de filtro de localización (URB / RUR / ZNI)
    # ════════════════════════════════════════════════════════════════════════
    'res_comparacion': {
        'titulo_base':         'Sector Residencial',
        'figura_base':         'Fig9-10',
        'filename_base':       'Fig_Residencial_Comparacion',
        'print_base':          'RESIDENCIAL — COMPARACIÓN POR ESCENARIO',
        'prefijo':             'DEMRES',
        'tiene_sub_filtro':    True,
        'label_sub_filtro':    'Uso',
        'tiene_loc':           True,              # ← exclusivo del sector residencial
        'año_historico_unico': True,
        'agrupacion_default':  'COMBUSTIBLE',
        'agrupacion_fija':     None,
        'msg_sin_datos':       'Sin tecnologías residenciales (DEMRES)',
        'variable_default':    'UseByTechnology',
    },

    # ════════════════════════════════════════════════════════════════════════
    # TERCIARIO  (Figuras 12 y 13)
    # ════════════════════════════════════════════════════════════════════════
    'ter_comparacion': {
        'titulo_base':         'Sector Terciario',
        'figura_base':         'Fig12-13',
        'filename_base':       'Fig_Terciario_Comparacion',
        'print_base':          'TERCIARIO — COMPARACIÓN POR ESCENARIO',
        'prefijo':             'DEMTER',
        'tiene_sub_filtro':    True,
        'label_sub_filtro':    'Uso',
        'tiene_loc':           False,
        'año_historico_unico': True,
        'agrupacion_default':  'COMBUSTIBLE',
        'agrupacion_fija':     None,
        'msg_sin_datos':       'Sin tecnologías terciarias (DEMTER)',
        'variable_default':    'UseByTechnology',
    },

    # ════════════════════════════════════════════════════════════════════════
    # CONSUMO FINAL — POR COMBUSTIBLE  (Figura 1)
    # Multi-sector: DEMRES + DEMIND + DEMTRA + DEMTER
    # Agrupación siempre por COMBUSTIBLE (fija)
    # ════════════════════════════════════════════════════════════════════════
    'consumo_final_combustible': {
        'titulo_base':         'Consumo Final Total por Combustible',
        'figura_base':         'Fig1',
        'filename_base':       'Fig1_ConsumoFinal_PEN',
        'print_base':          'CONSUMO FINAL TOTAL POR COMBUSTIBLE',
        'prefijo':             ('DEMRES', 'DEMIND', 'DEMTRA', 'DEMTER'),
        'tiene_sub_filtro':    False,
        'label_sub_filtro':    None,
        'tiene_loc':           False,
        'año_historico_unico': True,
        'agrupacion_default':  'COMBUSTIBLE',
        'agrupacion_fija':     'COMBUSTIBLE',     # ← no se puede cambiar
        'msg_sin_datos':       'Sin tecnologías de demanda final (DEM*)',
        'variable_default':    'UseByTechnology',
    },

    # ════════════════════════════════════════════════════════════════════════
    # CONSUMO FINAL — POR SECTOR  (Figura 2)
    # Multi-sector: DEMRES + DEMIND + DEMTRA + DEMTER
    # Agrupación siempre por SECTOR (fija)
    # ════════════════════════════════════════════════════════════════════════
    'consumo_final_sectorial': {
        'titulo_base':         'Consumo Final Sectorial',
        'figura_base':         'Fig2',
        'filename_base':       'Fig2_ConsumoFinal_PEN_Sectorial',
        'print_base':          'CONSUMO FINAL SECTORIAL',
        'prefijo':             ('DEMRES', 'DEMIND', 'DEMTRA', 'DEMTER'),
        'tiene_sub_filtro':    False,
        'label_sub_filtro':    None,
        'tiene_loc':           False,
        'año_historico_unico': True,
        'agrupacion_default':  'SECTOR',
        'agrupacion_fija':     'SECTOR',          # ← no se puede cambiar
        'msg_sin_datos':       'Sin tecnologías de demanda final (DEM*)',
        'variable_default':    'UseByTechnology',
    },
}
