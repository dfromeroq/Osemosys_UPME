"""Schemas Pydantic para plantillas de gráficas guardadas y generación de reportes."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


CompareMode = Literal["off", "facet", "by-year", "line-total"]
ViewMode = Literal["column", "line", "area", "pareto", "table"]
BarOrientation = Literal["vertical", "horizontal"]
FacetPlacement = Literal["inline", "stacked"]
FacetLegendMode = Literal["shared", "perFacet"]
FilenameMode = Literal["result", "tags"]
ReportFormat = Literal["png", "svg"]


SyntheticLineStyle = Literal["Solid", "Dash", "Dot", "DashDot", "ShortDash"]
SyntheticMarkerSymbol = Literal[
    "circle", "diamond", "square", "triangle", "triangle-down", "none"
]


class SyntheticSeries(BaseModel):
    """Serie manual de puntos (año, valor) anclada a una plantilla de gráfica.

    Útil para overlays con datos externos (p.ej. resultados de otro estudio)
    sobre gráficas de línea / líneas totales. La unidad/filtros son los mismos
    de la plantilla que la contiene — el usuario es responsable de introducir
    valores coherentes.
    """

    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    #: Nota descriptiva opcional (fuente de datos, supuestos…).
    description: str | None = Field(default=None, max_length=1000)
    #: Si ``False``, la serie está guardada pero no se dibuja. Default True.
    active: bool | None = None
    color: str = Field(min_length=4, max_length=9)
    #: Lista de pares [año, valor]. El frontend los pasa como arrays de 2 elementos.
    data: list[list[float]] = Field(default_factory=list, max_length=200)
    #: Estilo de línea. Default ``ShortDash`` (señal visual de "manual").
    lineStyle: SyntheticLineStyle | None = None
    #: Símbolo del marker. Default ``diamond``.
    markerSymbol: SyntheticMarkerSymbol | None = None
    #: Radio del marker en px. Default 5.
    markerRadius: float | None = Field(default=None, ge=0, le=20)
    #: Grosor de línea en px. Default 2.
    lineWidth: float | None = Field(default=None, ge=0, le=10)


class SavedChartTemplateBase(BaseModel):
    """Campos compartidos entre create/update/public."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    tipo: str = Field(min_length=1, max_length=64)
    un: str = Field(min_length=1, max_length=16)
    #: Unidad del eje Y secundario (eje derecho). ``None`` = sin eje secundario.
    un2: str | None = Field(default=None, min_length=1, max_length=16)
    sub_filtro: str | None = Field(default=None, max_length=64)
    loc: str | None = Field(default=None, max_length=32)
    variable: str | None = Field(default=None, max_length=64)
    agrupar_por: str | None = Field(default=None, max_length=32)
    view_mode: ViewMode | None = None
    compare_mode: CompareMode = "off"
    bar_orientation: BarOrientation | None = None
    facet_placement: FacetPlacement | None = None
    facet_legend_mode: FacetLegendMode | None = None
    num_scenarios: int = Field(default=1, ge=1, le=10)
    legend_title: str | None = Field(default=None, max_length=255)
    filename_mode: FilenameMode | None = None
    report_title: str | None = Field(default=None, max_length=255)
    #: Años a graficar cuando ``compare_mode == "by-year"``. Se ignora en otros modos.
    years_to_plot: list[int] | None = Field(default=None, max_length=20)
    #: Series manuales añadidas como overlay (línea). Se aplican cuando
    #: ``view_mode == "line"`` o ``compare_mode == "line-total"``.
    synthetic_series: list[SyntheticSeries] | None = Field(
        default=None, max_length=20
    )
    #: Cuando ``view_mode == "table"``: muestra solo años cada N (1=todos los años,
    #: 5=cada 5 años…). ``None`` = todos los años. Solo aplica al modo tabla.
    table_period_years: int | None = Field(default=None, ge=1, le=100)
    #: Cuando ``view_mode == "table"``: si ``True`` los valores se muestran
    #: como suma acumulada por serie (útil para "capacidad acumulada", etc.).
    table_cumulative: bool | None = None
    #: Override del orden de las series. Cada string es el ``name`` de una
    #: serie. La primera entrada queda **arriba** del stack (convención del
    #: proyecto). Series no listadas se mantienen al final en el orden natural.
    #: ``None`` = orden natural (devuelto por el backend).
    custom_series_order: list[str] | None = Field(default=None, max_length=200)
    #: Override del valor mínimo del eje Y. ``None`` = auto (default 0 para
    #: gráficos apilados, auto para líneas).
    y_axis_min: float | None = None
    #: Override del valor máximo del eje Y. ``None`` = auto.
    y_axis_max: float | None = None


class SavedChartTemplateCreate(SavedChartTemplateBase):
    @model_validator(mode="after")
    def _check_scenarios_vs_mode(self):
        if self.compare_mode == "off" and self.num_scenarios != 1:
            raise ValueError("Con compare_mode='off' debe haber exactamente 1 escenario.")
        if self.compare_mode in ("facet", "by-year", "line-total") and self.num_scenarios < 2:
            raise ValueError(
                f"Con compare_mode='{self.compare_mode}' se requieren al menos 2 escenarios."
            )
        if self.compare_mode == "by-year" and (
            not self.years_to_plot or len(self.years_to_plot) == 0
        ):
            raise ValueError(
                "Con compare_mode='by-year' debe incluirse al menos un año en years_to_plot."
            )
        return self


class SavedChartTemplateUpdate(BaseModel):
    """Actualización parcial: nombre, descripción, visibilidad y/o título en reportes."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    is_public: bool | None = None
    #: Título al renderizar en reportes. Enviar "" o null limpia el override.
    report_title: str | None = Field(default=None, max_length=255)
    #: Tipo de trazo (column / line / area / pareto / table). Cambiarlo desde
    #: el reporte permite alternar entre formatos sin editar toda la plantilla.
    view_mode: ViewMode | None = None
    #: Solo aplica si ``view_mode == "table"``. Enviar ``null`` resetea.
    table_period_years: int | None = Field(default=None, ge=1, le=100)
    table_cumulative: bool | None = None
    #: Override del orden de series y rango del eje Y. Mismos campos que en
    #: ``SavedChartTemplateBase`` — opcionales en update.
    custom_series_order: list[str] | None = Field(default=None, max_length=200)
    y_axis_min: float | None = None
    y_axis_max: float | None = None

    @model_validator(mode="after")
    def _any_field(self):
        if (
            self.name is None
            and self.description is None
            and self.is_public is None
            and self.report_title is None
            and self.view_mode is None
            and self.table_period_years is None
            and self.table_cumulative is None
            and self.custom_series_order is None
            and self.y_axis_min is None
            and self.y_axis_max is None
        ):
            raise ValueError(
                "Debes enviar al menos un campo a actualizar."
            )
        return self


class SavedChartTemplatePublic(SavedChartTemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    is_public: bool = False
    owner_username: str | None = None
    is_owner: bool = True
    is_favorite: bool = False


# ---------------------------------------------------------------------------
# Generación de reportes
# ---------------------------------------------------------------------------


class ReportTemplateItem(BaseModel):
    """Un ítem del reporte: plantilla + job_ids asignados."""

    template_id: int
    job_ids: list[int] = Field(min_length=1, max_length=10)
    #: Alias del escenario a agregar al título cuando la gráfica es single
    #: y vive en un reporte multi-escenario (e.g. "Alto"). Ignorado si null.
    scenario_alias_for_title: str | None = Field(default=None, max_length=120)


class ReportCategoryExportSub(BaseModel):
    """Sub-categoría con sus ítems (para export estructurado)."""

    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=120)
    items: list[ReportTemplateItem] = Field(default_factory=list)


class ReportCategoryExport(BaseModel):
    """Categoría (nivel superior) con sus ítems y subcategorías opcionales."""

    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=120)
    items: list[ReportTemplateItem] = Field(default_factory=list)
    subcategories: list[ReportCategoryExportSub] = Field(default_factory=list)


class ReportRequest(BaseModel):
    """Lista de plantillas con sus escenarios y formato de salida.

    Dos modos de export:
      - Plano (``organize_by_category=False``): se envía ``items`` y se produce
        un ZIP con ``01_nombre.ext``, ``02_nombre.ext``, etc.
      - Estructurado (``organize_by_category=True``): se envía ``categories``
        con su árbol y el ZIP queda como
        ``01_Categoria/[01_Sub/]01_nombre.ext``.
    """

    items: list[ReportTemplateItem] = Field(default_factory=list, max_length=200)
    fmt: ReportFormat = "png"
    report_name: str | None = Field(default=None, max_length=120)
    organize_by_category: bool = False
    categories: list[ReportCategoryExport] | None = None
    #: Alias por job_id solo para este export; no muta ``SimulationJob.display_name``.
    #: Claves como str (JSON); el service convierte a int al aplicar.
    job_display_overrides: dict[str, str] | None = None
    #: Rango de años: filtra las categorías-año del chart antes de renderizar.
    #: ``None`` en cualquier extremo = sin tope por ese lado.
    year_from: int | None = Field(default=None, ge=1900, le=2200)
    year_to: int | None = Field(default=None, ge=1900, le=2200)


# ---------------------------------------------------------------------------
# Layout persistido del reporte (override manual)
# ---------------------------------------------------------------------------


class ReportLayoutSubcategory(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=120)
    items: list[int] = Field(default_factory=list)


class ReportLayoutCategory(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=120)
    items: list[int] = Field(default_factory=list)
    subcategories: list[ReportLayoutSubcategory] = Field(default_factory=list)


SubcategoryDisplay = Literal["tabs", "accordions"]


class ReportLayout(BaseModel):
    categories: list[ReportLayoutCategory] = Field(default_factory=list)
    #: Cómo se muestran las subcategorías en el dashboard:
    #:   - ``"tabs"`` (default): pestañas seleccionables (una visible).
    #:   - ``"accordions"``: secciones desplegables apiladas verticalmente
    #:     (todas abiertas por defecto).
    subcategory_display: SubcategoryDisplay = "tabs"


# ---------------------------------------------------------------------------
# Reportes guardados (colecciones de plantillas con nombre y descripción)
# ---------------------------------------------------------------------------


class ReportSavedBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    fmt: ReportFormat = "png"
    items: list[int] = Field(
        description="Lista ordenada de IDs de saved_chart_template.",
        min_length=1,
        max_length=100,
    )
    #: Override manual de categorías. ``None`` = usar auto-layout (frontend).
    layout: ReportLayout | None = None
    #: Alias por escenario global (0-based). Cada string corresponde al slot i.
    #: Null o lista vacía = sin aliases.
    scenario_aliases: list[str] | None = Field(default=None, max_length=20)
    #: Job IDs por defecto por slot (0-based). ``None`` en una posición = slot
    #: sin asignar. Lista vacía o null = sin defaults.
    default_job_ids: list[int | None] | None = Field(default=None, max_length=20)
    #: Rango de años persistido. ``None`` = sin filtro por ese lado.
    year_from: int | None = Field(default=None, ge=1900, le=2200)
    year_to: int | None = Field(default=None, ge=1900, le=2200)


class ReportSavedCreate(ReportSavedBase):
    pass


class ReportSavedUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    fmt: ReportFormat | None = None
    items: list[int] | None = Field(default=None, min_length=1, max_length=100)
    is_public: bool | None = None
    #: Solo aplica si el usuario tiene permiso (``can_manage_catalogs``).
    is_official: bool | None = None
    #: Enviar ``None`` mantiene el layout actual; enviar objeto lo reemplaza;
    #: se permite ``{"categories": []}`` explícitamente para resetear a auto.
    #: Si quieres restaurar auto, envía ``{"layout": null}`` en JSON con ``exclude_none=False``
    #: (nuestro endpoint detecta la ausencia vs. ``null`` vía ``model_fields_set``).
    layout: ReportLayout | None = None
    scenario_aliases: list[str] | None = Field(default=None, max_length=20)
    default_job_ids: list[int | None] | None = Field(default=None, max_length=20)
    year_from: int | None = Field(default=None, ge=1900, le=2200)
    year_to: int | None = Field(default=None, ge=1900, le=2200)


class ReportSavedPublic(ReportSavedBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    is_public: bool = False
    is_official: bool = False
    owner_username: str | None = None
    is_owner: bool = True
    is_favorite: bool = False


class SavedFavoritePatch(BaseModel):
    """Payload para toggle de favorito (chart o report)."""

    is_favorite: bool
