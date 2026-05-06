"""Schemas Pydantic para visualización de resultados OSeMOSYS.

Define los contratos de request/response para los endpoints de gráficas:
single-scenario, multi-scenario (comparación), catálogo de charts y
resumen de resultados.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.scenario import ScenarioTagPublic


# ---------------------------------------------------------------------------
# Schemas para gráficas single-scenario
# ---------------------------------------------------------------------------

class ChartSeries(BaseModel):
    """Una serie individual dentro de una gráfica (e.g. una tecnología)."""

    name: str
    #: ``None`` representa "no hay dato aquí" — produce un *gap* en líneas
    #: y "no hay barra" en columnas/áreas. Se usa cuando se unifica el eje X
    #: entre facets de distinto rango de años o cuando una serie sintética
    #: tiene huecos.
    data: list[float | None]
    color: str
    stack: str | None = None
    #: True si la serie es manual (overlay agregado por el usuario sobre una
    #: gráfica de líneas/áreas). Permite al renderer aplicar estilo distintivo.
    is_synthetic: bool | None = None
    #: Estilo de línea — coincide con ``SyntheticSeries.lineStyle``.
    #:   "Solid" | "Dash" | "Dot" | "DashDot" | "ShortDash"
    lineStyle: str | None = None
    #: Símbolo de marker — coincide con ``SyntheticSeries.markerSymbol``.
    #:   "circle" | "diamond" | "square" | "triangle" | "triangle-down" | "none"
    markerSymbol: str | None = None
    #: Radio del marker en px. None = default del renderer.
    markerRadius: float | None = None
    #: Grosor de línea en px. None = default del renderer.
    lineWidth: float | None = None


class ChartDataResponse(BaseModel):
    """Respuesta completa para un chart de un solo escenario."""

    categories: list[str]
    series: list[ChartSeries]
    title: str
    yAxisLabel: str


# ---------------------------------------------------------------------------
# Schemas para gráficas de comparación multi-escenario
# ---------------------------------------------------------------------------

class SubplotData(BaseModel):
    """Un subplot en comparación. 
    
    Para modo 'by-year': year = año, categories = escenarios.
    Para modo 'by-year-alt': year = job_id, scenario_name = nombre, categories = años.
    """

    year: int
    scenario_name: str | None = None
    categories: list[str]
    series: list[ChartSeries]


class CompareChartResponse(BaseModel):
    """Respuesta completa para un chart de comparación multi-escenario."""

    title: str
    subplots: list[SubplotData]
    yAxisLabel: str


class FacetData(BaseModel):
    """Datos de un facet (escenario completo) en comparación facet."""

    scenario_name: str
    job_id: int
    #: Alias de corrida (`simulation_job.display_name`), si existe.
    display_name: str | None = None
    #: Nombre de la etiqueta del escenario (`scenario_tag.name`), si existe.
    scenario_tag_name: str | None = None
    categories: list[str]
    series: list[ChartSeries]


class CompareChartFacetResponse(BaseModel):
    """Respuesta para comparación por escenarios completos (facets)."""

    title: str
    facets: list[FacetData]
    yAxisLabel: str


# ---------------------------------------------------------------------------
# Catálogo de gráficas disponibles
# ---------------------------------------------------------------------------

class ParetoChartResponse(BaseModel):
    """Respuesta para gráfica Pareto por tecnología (barras + % acumulado)."""

    categories: list[str]
    values: list[float]
    cumulative_percent: list[float]
    title: str
    yAxisLabel: str


class DataExplorerFilters(BaseModel):
    """Filtros que reproducen las filas que un chart agrega.

    Consumido por el botón "Ver Datos de Resultados" en cada chart para
    abrir el Data Explorer ya filtrado a las filas que el chart suma/grafica.
    """

    variable_names: list[str] = []
    technology_prefixes: list[str] = []
    fuel_prefixes: list[str] = []
    fuel_names: list[str] = []
    emission_names: list[str] = []


class ChartCatalogItem(BaseModel):
    """Metadatos de un tipo de gráfica disponible en el sistema."""

    id: str
    label: str
    variable_default: str
    has_sub_filtro: bool = False
    has_loc: bool = False
    sub_filtros: list[str] | None = None
    es_capacidad: bool = False
    soporta_pareto: bool = False
    data_explorer_filters: DataExplorerFilters | None = None


# ---------------------------------------------------------------------------
# Resumen de resultados de simulación (KPIs)
# ---------------------------------------------------------------------------

class ResultSummaryResponse(BaseModel):
    """Resumen ligero de una corrida exitosa para el header de visualización."""

    job_id: int
    scenario_id: int | None = None
    scenario_name: str | None = None
    scenario_tag: ScenarioTagPublic | None = None
    scenario_tags: list[ScenarioTagPublic] = []
    display_name: str | None = None
    solver_name: str
    solver_status: str
    objective_value: float
    coverage_ratio: float
    total_demand: float
    total_dispatch: float
    total_unmet: float
    total_co2: float = 0.0
    #: Visibilidad del resultado (público: lo ven todos; privado: solo dueño).
    is_public: bool = True
    #: True si el usuario actual lo marcó como favorito.
    is_favorite: bool = False
    #: True si el job terminó SUCCEEDED pero el solver reportó infactibilidad.
    is_infeasible_result: bool = False
    #: Username del dueño (para mostrar en tablas comparativas).
    owner_username: str | None = None
