"""Endpoints REST para visualización de resultados de simulaciones.

Provee resúmenes, datos para gráficas individuales y datos para
comparación entre múltiples escenarios.
"""

from __future__ import annotations

import io
import logging
from typing import List

from fastapi import APIRouter, Depends, Query, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.visualization import (
    ChartCatalogItem,
    ChartDataResponse,
    CompareChartFacetResponse,
    CompareChartResponse,
    ParetoChartResponse,
    ResultSummaryResponse,
)
from app.services.simulation_service import SimulationService
from app.visualization import chart_service
from app.core.exceptions import NotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/visualizations")


def _safe_export_basename(name: str, max_len: int = 80) -> str:
    clean = "".join(c if c.isalnum() or c in (" ", "_", "-") else "_" for c in name)
    clean = clean.strip()
    if max_len < 1:
        return clean
    return clean[:max_len]


_COMPARE_FACET_FILENAME_MODES = frozenset({"result", "tags"})

# Compatibilidad con clientes antiguos (antes solo existían chart / simulations / …).
_LEGACY_COMPARE_FACET_FILENAME_MODES = frozenset(
    {"chart", "simulations", "simulations_and_tags"}
)


def _normalize_compare_facet_filename_mode(mode: str) -> str:
    m = (mode or "").strip()
    if m in _LEGACY_COMPARE_FACET_FILENAME_MODES:
        return "result"
    return m


def _compare_facet_export_basename(
    facet_payload: CompareChartFacetResponse,
    filename_mode: str,
) -> str:
    """Base del nombre de archivo para export-compare-facet (sin extensión)."""
    facets = [f for f in facet_payload.facets if f.series]
    if not facets:
        return _safe_export_basename(facet_payload.title)
    parts: list[str] = []
    for f in facets:
        sim_fallback = (f.scenario_name or f"job_{f.job_id}").strip()
        result_name = (f.display_name or sim_fallback).strip()
        if filename_mode == "tags":
            tag = (f.scenario_tag_name or "").strip()
            piece = tag if tag else result_name
        else:
            piece = result_name
        parts.append(piece)
    joined = "__".join(parts)
    return _safe_export_basename(joined, max_len=140)


@router.get("/chart-catalog", response_model=list[ChartCatalogItem])
def get_chart_catalog(
    current_user: User = Depends(get_current_user),
) -> list[ChartCatalogItem]:
    """Catálogo estático de gráficas configuradas en el sistema."""
    return chart_service.get_chart_catalog()


@router.get("/chart-data/compare", response_model=CompareChartResponse)
def get_comparison_data(
    job_ids: str = Query(..., description="Job IDs separados por coma (max 10)"),
    tipo: str = Query(...),
    un: str = Query("PJ"),
    years_to_plot: str = Query("2024,2030,2050", description="Años a plotear separados por coma"),
    agrupacion: str | None = Query(None),
    sub_filtro: str | None = Query(None),
    loc: str | None = Query(None),
    es_porcentaje: bool = Query(False, description="Si true, normaliza cada año/escenario a 100%"),
    group_by: str = Query("year", description="Agrupación: 'year' (default) o 'scenario' para modo alternativo"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Datos para comparación entre múltiples escenarios."""
    job_id_list = []
    try:
        job_id_list = [int(x.strip()) for x in job_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="job_ids inválidos")
    
    if not job_id_list:
        raise HTTPException(status_code=400, detail="Debe proveer al menos un job_id")
    
    if len(job_id_list) > 10:
        raise HTTPException(status_code=400, detail="Máximo 10 jobs para comparar")
    
    year_list = []
    try:
        year_list = [int(x.strip()) for x in years_to_plot.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="years_to_plot inválidos")
    
    # Validar acceso a todos los jobs
    for jid in job_id_list:
        try:
            job = SimulationService.get_by_id(db, current_user=current_user, job_id=jid)
            if job["status"] != "SUCCEEDED":
                raise HTTPException(
                    status_code=400, detail=f"Job {jid} no está en estado SUCCEEDED"
                )
        except NotFoundError:
            raise HTTPException(status_code=404, detail=f"Job {jid} no encontrado o sin acceso")
    
    try:
        if group_by == "scenario":
            return chart_service.build_comparison_data_by_year_alt(
                db=db,
                job_ids=job_id_list,
                tipo=tipo,
                un=un,
                years_to_plot=year_list,
                agrupacion=agrupacion,
                sub_filtro=sub_filtro,
                loc=loc,
                es_porcentaje_override=es_porcentaje,
            )
        else:
            return chart_service.build_comparison_data(
                db=db,
                job_ids=job_id_list,
                tipo=tipo,
                un=un,
                years_to_plot=year_list,
                agrupacion=agrupacion,
                sub_filtro=sub_filtro,
                loc=loc,
                es_porcentaje_override=es_porcentaje,
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/chart-data/compare-facet", response_model=CompareChartFacetResponse)
def get_comparison_facet_data(
    job_ids: str = Query(..., description="Job IDs separados por coma (max 10)"),
    tipo: str = Query(...),
    un: str = Query("PJ"),
    sub_filtro: str | None = Query(None),
    loc: str | None = Query(None),
    variable: str | None = Query(None),
    agrupar_por: str | None = Query(None, description="Override de agrupación: TECNOLOGIA, FUEL, GROUP"),
    es_porcentaje: bool = Query(False, description="Si true, normaliza cada año a 100%"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Datos para comparación por escenarios completos (un facet por escenario)."""
    job_id_list = _validate_compare_job_ids(job_ids, db, current_user)

    try:
        return chart_service.build_comparison_facet_data(
            db=db,
            job_ids=job_id_list,
            tipo=tipo,
            un=un,
            sub_filtro=sub_filtro,
            loc=loc,
            variable=variable,
            agrupar_por=agrupar_por,
            es_porcentaje_override=es_porcentaje,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/chart-data/compare-line", response_model=ChartDataResponse)
def get_comparison_line_data(
    job_ids: str = Query(..., description="Job IDs separados por coma (max 10)"),
    tipo: str = Query(...),
    un: str = Query("PJ"),
    sub_filtro: str | None = Query(None),
    loc: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Líneas totales multi-escenario consolidadas (todos los escenarios en el mismo eje, X=años)."""
    job_id_list = _validate_compare_job_ids(job_ids, db, current_user)
    try:
        return chart_service.build_comparison_line_data(
            db=db, job_ids=job_id_list, tipo=tipo,
            un=un, sub_filtro=sub_filtro, loc=loc,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _validate_compare_job_ids(
    job_ids: str,
    db: Session,
    current_user: User,
) -> list[int]:
    try:
        job_id_list = [int(x.strip()) for x in job_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="job_ids inválidos")
    if not job_id_list:
        raise HTTPException(status_code=400, detail="Debe proveer al menos un job_id")
    if len(job_id_list) > 10:
        raise HTTPException(status_code=400, detail="Máximo 10 jobs para comparar")
    for jid in job_id_list:
        try:
            job = SimulationService.get_by_id(db, current_user=current_user, job_id=jid)
            if job["status"] != "SUCCEEDED":
                raise HTTPException(
                    status_code=400, detail=f"Job {jid} no está en estado SUCCEEDED"
                )
        except NotFoundError:
            raise HTTPException(status_code=404, detail=f"Job {jid} no encontrado o sin acceso")
    return job_id_list


@router.get("/export-compare-facet")
def export_comparison_facet_image(
    job_ids: str = Query(..., description="Job IDs separados por coma (max 10)"),
    tipo: str = Query(...),
    un: str = Query("PJ"),
    sub_filtro: str | None = Query(None),
    loc: str | None = Query(None),
    variable: str | None = Query(None),
    agrupar_por: str | None = Query(None),
    fmt: str = Query("png", description="png o svg"),
    filename_mode: str = Query(
        "result",
        description=(
            "result=nombre del resultado por faceta; "
            "tags=etiqueta del escenario, o nombre del resultado si no hay etiqueta"
        ),
    ),
    legend_title: str | None = Query(
        None,
        description="Título opcional sobre la leyenda (p. ej. Combustible / tecnología)",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exporta comparación por facetas en una sola imagen (mismo criterio que compare-facet)."""
    if fmt not in ("png", "svg"):
        raise HTTPException(status_code=400, detail="fmt debe ser 'png' o 'svg'")
    filename_mode = _normalize_compare_facet_filename_mode(filename_mode)
    if filename_mode not in _COMPARE_FACET_FILENAME_MODES:
        raise HTTPException(
            status_code=400,
            detail="filename_mode inválido; use result o tags",
        )

    job_id_list = _validate_compare_job_ids(job_ids, db, current_user)

    try:
        facet_payload = chart_service.build_comparison_facet_data(
            db=db,
            job_ids=job_id_list,
            tipo=tipo,
            un=un,
            sub_filtro=sub_filtro,
            loc=loc,
            variable=variable,
            agrupar_por=agrupar_por,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not facet_payload.facets or not any(f.series for f in facet_payload.facets):
        raise HTTPException(status_code=404, detail="Sin datos para exportar con los filtros actuales")

    try:
        img_bytes = chart_service.render_comparison_facet_figure_bytes(
            facet_payload,
            fmt=fmt,
            legend_title=legend_title,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Error renderizando export compare-facet")
        raise HTTPException(status_code=500, detail=str(e))

    base_name = _compare_facet_export_basename(facet_payload, filename_mode)
    ext = "svg" if fmt == "svg" else "png"
    filename = f"{base_name}_facet.{ext}"
    media = "image/svg+xml" if fmt == "svg" else "image/png"
    return StreamingResponse(
        io.BytesIO(img_bytes),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{job_id}/pareto-data", response_model=ParetoChartResponse)
def get_pareto_data(
    job_id: int,
    tipo: str = Query(...),
    un: str = Query("PJ"),
    sub_filtro: str | None = Query(None),
    loc: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Datos de Pareto por tecnología para un escenario (barras desc + % acumulado)."""
    try:
        job = SimulationService.get_by_id(db, current_user=current_user, job_id=job_id)
        if job["status"] != "SUCCEEDED":
            raise HTTPException(status_code=400, detail="Job no está en estado SUCCEEDED")
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Job no encontrado o sin acceso")
    try:
        return chart_service.build_pareto_data(
            db=db, job_id=job["id"], tipo=tipo,
            un=un, sub_filtro=sub_filtro, loc=loc,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{job_id}/result-summary", response_model=ResultSummaryResponse)
def get_result_summary(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """KPIs y resumen general de resultados para un job."""
    try:
        job = SimulationService.get_by_id(db, current_user=current_user, job_id=job_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Job no encontrado o sin acceso")
    
    return chart_service.get_result_summary(
        db,
        job_id=job["id"],
        current_user_id=current_user.id,
    )


@router.get("/{job_id}/chart-data", response_model=ChartDataResponse)
def get_chart_data(
    job_id: int,
    tipo: str = Query(...),
    un: str = Query("PJ"),
    sub_filtro: str | None = Query(None),
    loc: str | None = Query(None),
    variable: str | None = Query(None),
    agrupar_por: str | None = Query(None, description="Override de agrupación: TECNOLOGIA, FUEL, GROUP"),
    es_porcentaje: bool = Query(False, description="Si true, normaliza cada año a 100%"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Datos serializados para una gráfica individual."""
    try:
        job = SimulationService.get_by_id(db, current_user=current_user, job_id=job_id)
        if job["status"] != "SUCCEEDED":
            raise HTTPException(status_code=400, detail="Job no está en estado SUCCEEDED")
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Job no encontrado o sin acceso")

    try:
        return chart_service.build_chart_data(
            db=db,
            job_id=job["id"],
            tipo=tipo,
            un=un,
            sub_filtro=sub_filtro,
            loc=loc,
            variable=variable,
            agrupar_por=agrupar_por,
            es_porcentaje_override=es_porcentaje,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{job_id}/export-chart")
def export_chart(
    job_id: int,
    tipo: str = Query(...),
    un: str = Query("PJ"),
    sub_filtro: str | None = Query(None),
    loc: str | None = Query(None),
    variable: str | None = Query(None),
    agrupar_por: str | None = Query(None),
    fmt: str = Query("png", description="Formato: png, svg, csv o xlsx"),
    view_mode: str = Query(
        "column",
        description=(
            "column (barras apiladas), line (líneas), area (áreas apiladas), "
            "pareto o table; el view_mode afecta el render PNG/SVG"
        ),
    ),
    table_period_years: int | None = Query(
        None,
        ge=1,
        le=100,
        description="Solo cuando view_mode=table: filtra años cada N (5=cada 5 años).",
    ),
    table_cumulative: bool = Query(
        False,
        description="Solo cuando view_mode=table: muestra valores acumulados.",
    ),
    series_order: str | None = Query(
        None,
        description="Lista de nombres de series separados por coma — define el "
                    "orden custom (la primera queda arriba del stack).",
    ),
    y_axis_min: float | None = Query(
        None,
        description="Override del valor mínimo del eje Y. Vacío = auto.",
    ),
    y_axis_max: float | None = Query(
        None,
        description="Override del valor máximo del eje Y. Vacío = auto.",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exporta la gráfica actual como imagen (Matplotlib), CSV o XLSX."""
    if fmt not in ("png", "svg", "csv", "xlsx"):
        raise HTTPException(
            status_code=400, detail="fmt debe ser 'png', 'svg', 'csv' o 'xlsx'"
        )
    if view_mode not in ("column", "line", "area", "pareto", "table"):
        raise HTTPException(
            status_code=400,
            detail="view_mode debe ser 'column', 'line', 'area', 'pareto' o 'table'",
        )
    # XLSX solo aplica a charts con datos tabulables (no Pareto).
    if fmt == "xlsx" and view_mode == "pareto":
        raise HTTPException(
            status_code=400, detail="XLSX no soportado para Pareto"
        )

    try:
        job = SimulationService.get_by_id(db, current_user=current_user, job_id=job_id)
        if job["status"] != "SUCCEEDED":
            raise HTTPException(status_code=400, detail="Job no está en estado SUCCEEDED")
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Job no encontrado o sin acceso")

    # Rama Pareto: usa un dataset y renderer distintos (no hay "series apiladas").
    if view_mode == "pareto":
        try:
            pareto = chart_service.build_pareto_data(
                db=db,
                job_id=job["id"],
                tipo=tipo,
                un=un,
                sub_filtro=sub_filtro,
                loc=loc,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        if not pareto.categories:
            raise HTTPException(
                status_code=404,
                detail="Sin datos para exportar con los filtros actuales",
            )

        base_name = _safe_export_basename(pareto.title)
        if fmt == "csv":
            body = chart_service.pareto_data_to_csv_bytes(pareto)
            filename = f"{base_name}.csv"
            return StreamingResponse(
                io.BytesIO(body),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        img_fmt = "svg" if fmt == "svg" else "png"
        try:
            img_bytes = chart_service.render_pareto_chart_bytes(pareto, fmt=img_fmt)
        except Exception as e:
            logger.exception("Error renderizando Pareto para export")
            raise HTTPException(status_code=500, detail=str(e))

        filename = f"{base_name}.{img_fmt}"
        media = "image/svg+xml" if img_fmt == "svg" else "image/png"
        return StreamingResponse(
            io.BytesIO(img_bytes),
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    try:
        chart = chart_service.build_chart_data(
            db=db,
            job_id=job["id"],
            tipo=tipo,
            un=un,
            sub_filtro=sub_filtro,
            loc=loc,
            variable=variable,
            agrupar_por=agrupar_por,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not chart.series:
        raise HTTPException(status_code=404, detail="Sin datos para exportar con los filtros actuales")

    # Transformaciones específicas del modo tabla — se aplican antes de
    # cualquier serialización (CSV/XLSX/PNG/SVG) para que TODOS los formatos
    # reflejen el mismo dato visible.
    if view_mode == "table":
        if table_cumulative:
            chart_service.apply_cumulative_series(chart)
        if table_period_years and table_period_years >= 2:
            chart_service.apply_period_years(chart, table_period_years)

    # Reorden custom de series — aplica a todos los formatos.
    if series_order:
        order_list = [s.strip() for s in series_order.split(",") if s.strip()]
        if order_list:
            chart_service.reorder_chart_series(chart, order_list)

    base_name = _safe_export_basename(chart.title)
    if fmt == "csv":
        body = chart_service.chart_data_to_csv_bytes(chart)
        filename = f"{base_name}.csv"
        return StreamingResponse(
            io.BytesIO(body),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    if fmt == "xlsx":
        try:
            body = chart_service.chart_data_to_xlsx_bytes(chart)
        except Exception as e:  # pragma: no cover
            logger.exception("Error generando XLSX para export")
            raise HTTPException(status_code=500, detail=str(e))
        filename = f"{base_name}.xlsx"
        return StreamingResponse(
            io.BytesIO(body),
            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    img_fmt = "svg" if fmt == "svg" else "png"
    try:
        img_bytes = chart_service.render_chart_visualization_bytes(
            chart, fmt=img_fmt, view_mode=view_mode,
            y_axis_min=y_axis_min, y_axis_max=y_axis_max,
        )
    except Exception as e:
        logger.exception("Error renderizando gráfica para export")
        raise HTTPException(status_code=500, detail=str(e))

    ext = img_fmt
    filename = f"{base_name}.{ext}"
    media = "image/svg+xml" if img_fmt == "svg" else "image/png"
    return StreamingResponse(
        io.BytesIO(img_bytes),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{job_id}/export-all")
def export_all_charts(
    job_id: int,
    un: str = Query("PJ"),
    fmt: str = Query("svg", description="Formato de imagen: svg o png"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Genera un ZIP con todas las gráficas de un escenario como imágenes SVG o PNG."""
    if fmt not in ("svg", "png"):
        raise HTTPException(status_code=400, detail="fmt debe ser 'svg' o 'png'")

    try:
        job = SimulationService.get_by_id(db, current_user=current_user, job_id=job_id)
        if job["status"] != "SUCCEEDED":
            raise HTTPException(status_code=400, detail="Job no está en estado SUCCEEDED")
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Job no encontrado o sin acceso")

    try:
        zip_bytes = chart_service.export_all_charts_zip(
            db=db, job_id=job["id"], un=un, fmt=fmt,
        )
    except Exception as e:
        logger.exception("Error generando ZIP de gráficas")
        raise HTTPException(status_code=500, detail=str(e))

    scenario_name = job.get("scenario_name") or f"Job_{job_id}"
    safe_name = "".join(c if c.isalnum() or c in (" ", "_", "-") else "_" for c in scenario_name)
    filename = f"Graficas_{safe_name}_{un}.zip"

    return StreamingResponse(
        zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.get("/{job_id}/export-raw")
def export_raw_data(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Genera un archivo Excel con los datos crudos resultantes de la simulación."""
    try:
        job = SimulationService.get_by_id(db, current_user=current_user, job_id=job_id)
        if job["status"] != "SUCCEEDED":
            raise HTTPException(status_code=400, detail="Job no está en estado SUCCEEDED")
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Job no encontrado o sin acceso")

    try:
        excel_bytes = chart_service.export_raw_data_excel(db=db, job_id=job["id"])
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error generando Excel de datos crudos")
        raise HTTPException(status_code=500, detail=str(e))

    scenario_name = job.get("scenario_name") or f"Job_{job_id}"
    safe_name = "".join(c if c.isalnum() or c in (" ", "_", "-") else "_" for c in scenario_name)
    filename = f"Resultados_Crudos_{safe_name}.xlsx"

    return StreamingResponse(
        excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{job_id}/export-csv-bundle")
def export_results_csv_bundle(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """ZIP con un CSV por variable de salida en formato OSeMOSYS estándar."""
    try:
        job = SimulationService.get_by_id(db, current_user=current_user, job_id=job_id)
        if job["status"] != "SUCCEEDED":
            raise HTTPException(status_code=400, detail="Job no está en estado SUCCEEDED")
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Job no encontrado o sin acceso")

    try:
        zip_bytes = chart_service.export_results_csv_zip(db=db, job_id=job["id"])
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error generando ZIP de CSVs por variable")
        raise HTTPException(status_code=500, detail=str(e))

    scenario_name = job.get("scenario_name") or f"Job_{job_id}"
    safe_name = _safe_export_basename(scenario_name)
    filename = f"Resultados_CSV_{safe_name}.zip"

    return StreamingResponse(
        zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
