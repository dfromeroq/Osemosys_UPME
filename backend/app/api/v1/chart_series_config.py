"""API: configuración global de series por tipo de gráfica."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.exceptions import ConflictError, NotFoundError
from app.db.session import get_db
from app.models import User
from app.schemas.chart_series_config import (
    ChartSeriesConfigCreate,
    ChartSeriesConfigPublic,
    ChartSeriesConfigUpdate,
    ChartSeriesPopulateBody,
    ChartSeriesReorderBody,
    ChartTypeInfoPublic,
)
from app.services.chart_series_config_service import (
    chart_types_catalog,
    create_config,
    delete_config,
    list_configs,
    normalize_agrupar_por,
    populate_all_chart_types,
    populate_chart_type,
    reorder_configs,
    require_reports_admin,
    update_config,
)
from app.visualization.configs import CONFIGS
from app.visualization.configs_comparacion import CONFIGS_COMPARACION

router = APIRouter(prefix="/chart-series-config")


def _default_agrupar_for_tipo(tipo_key: str) -> str | None:
    if tipo_key in CONFIGS:
        return CONFIGS[tipo_key].get("agrupar_por")
    if tipo_key in CONFIGS_COMPARACION:
        c = CONFIGS_COMPARACION[tipo_key]
        return c.get("agrupacion_fija") or c.get("agrupacion_default")
    return None


def _serialize_rows(rows: list) -> list[ChartSeriesConfigPublic]:
    return [ChartSeriesConfigPublic.model_validate(r) for r in rows]


@router.get("/chart-types", response_model=list[ChartTypeInfoPublic])
def list_chart_types(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ChartTypeInfoPublic]:
    require_reports_admin(current_user)
    return [ChartTypeInfoPublic.model_validate(x) for x in chart_types_catalog()]


@router.get("", response_model=list[ChartSeriesConfigPublic])
def list_series_for_chart(
    tipo: str = Query(..., min_length=1, max_length=64),
    agrupar_por: str = Query(..., min_length=1, max_length=32),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ChartSeriesConfigPublic]:
    require_reports_admin(current_user)
    rows = list_configs(db, tipo=tipo, agrupar_por=agrupar_por)
    return _serialize_rows(rows)


@router.post("/populate", response_model=list[ChartSeriesConfigPublic])
def populate_one(
    body: ChartSeriesPopulateBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ChartSeriesConfigPublic]:
    require_reports_admin(current_user)
    try:
        populate_chart_type(
            db,
            tipo=body.tipo,
            agrupar_por=body.agrupar_por,
            variable=body.variable,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    ap = normalize_agrupar_por(body.agrupar_por, _default_agrupar_for_tipo(body.tipo.strip()))
    rows = list_configs(db, tipo=body.tipo.strip(), agrupar_por=ap)
    return _serialize_rows(rows)


@router.post("/populate-all", response_model=dict)
def populate_all(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    require_reports_admin(current_user)
    n = populate_all_chart_types(db)
    return {"inserted_rows": n}


@router.post("/row", response_model=ChartSeriesConfigPublic, status_code=201)
def create_row(
    body: ChartSeriesConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChartSeriesConfigPublic:
    try:
        row = create_config(
            db,
            tipo=body.tipo,
            agrupar_por=body.agrupar_por,
            cfg_default_agrupar=_default_agrupar_for_tipo(body.tipo.strip()),
            series_code=body.series_code,
            display_name=body.display_name,
            color=body.color,
            hidden=body.hidden,
            sort_index=body.sort_index,
            group_key=body.group_key,
            notes=body.notes,
            current_user=current_user,
        )
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return ChartSeriesConfigPublic.model_validate(row)


@router.patch("/{row_id}", response_model=ChartSeriesConfigPublic)
def patch_row(
    row_id: int,
    body: ChartSeriesConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChartSeriesConfigPublic:
    data = body.model_dump(exclude_unset=True)
    try:
        row = update_config(db, row_id=row_id, data=data, current_user=current_user)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return ChartSeriesConfigPublic.model_validate(row)


@router.delete("/{row_id}", status_code=204)
def remove_row(
    row_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        delete_config(db, row_id=row_id, current_user=current_user)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/reorder", response_model=list[ChartSeriesConfigPublic])
def reorder(
    body: ChartSeriesReorderBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ChartSeriesConfigPublic]:
    try:
        rows = reorder_configs(
            db, ordered_ids=body.ids, current_user=current_user
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return _serialize_rows(rows)
