"""
Paquete de visualización OSeMOSYS.

Contiene colores, configuraciones de gráficas single-escenario
y configuraciones de gráficas de comparación multi-escenario.
"""

from .colors import (
    asignar_grupo,
    COLORES_GRUPOS,
    generar_colores_tecnologias,
    generar_tonos,
    construir_color_map_por_familias,
    _color_por_grupo_fijo,
    _color_electricidad,
    FAMILIAS_TEC,
    COLOR_BASE_FAMILIA,
    COLOR_MAP_PWR,
)
from .configs import CONFIGS
from .configs_comparacion import CONFIGS_COMPARACION, MAPA_SECTOR, COLORES_SECTOR
from .chart_service import (
    build_chart_data,
    build_comparison_data,
    get_result_summary,
    get_chart_catalog,
)
