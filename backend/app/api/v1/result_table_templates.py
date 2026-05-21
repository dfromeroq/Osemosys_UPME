"""API REST: plantillas globales de tablas de resultados."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.exceptions import ForbiddenError, NotFoundError
from app.db.session import get_db
from app.models import User
from app.schemas.result_table_template import (
    ResultTablePresentationOptionsPublic,
    ResultTableReorderBody,
    ResultTableTemplateCreate,
    ResultTableTemplatePublic,
    ResultTableTemplateUpdate,
)
from app.services.result_table_presentation_options import (
    build_result_table_presentation_options,
)
from app.services.result_table_template_service import ResultTableTemplateService

router = APIRouter(prefix="/result-table-templates")


@router.get("", response_model=list[ResultTableTemplatePublic])
def list_enabled_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ResultTableTemplatePublic]:
    rows = ResultTableTemplateService.list_enabled(db)
    return [ResultTableTemplatePublic.model_validate(r) for r in rows]


@router.get("/manage", response_model=list[ResultTableTemplatePublic])
def list_all_for_manage(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ResultTableTemplatePublic]:
    try:
        rows = ResultTableTemplateService.list_all(db, current_user=current_user)
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(e)
        ) from e
    return [ResultTableTemplatePublic.model_validate(r) for r in rows]


@router.post("/reorder", response_model=list[ResultTableTemplatePublic])
def reorder_templates(
    body: ResultTableReorderBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ResultTableTemplatePublic]:
    try:
        rows = ResultTableTemplateService.reorder(
            db, current_user=current_user, ordered_ids=body.ids
        )
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(e)
        ) from e
    return [ResultTableTemplatePublic.model_validate(r) for r in rows]


@router.get(
    "/presentation-options",
    response_model=ResultTablePresentationOptionsPublic,
)
def get_presentation_options(
    tipo: str = Query(..., min_length=1, max_length=64),
    agrupar_por: str | None = Query(None, max_length=32),
    variable: str | None = Query(None, max_length=64),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResultTablePresentationOptionsPublic:
    try:
        ResultTableTemplateService.require_reports_admin(current_user)
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(e)
        ) from e
    data = build_result_table_presentation_options(
        db,
        tipo=tipo.strip(),
        agrupar_por=agrupar_por,
        variable=variable,
    )
    return ResultTablePresentationOptionsPublic.model_validate(data)


@router.get("/{template_id}", response_model=ResultTableTemplatePublic)
def get_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResultTableTemplatePublic:
    try:
        row = ResultTableTemplateService.get(db, template_id, current_user=current_user)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return ResultTableTemplatePublic.model_validate(row)


@router.post("", response_model=ResultTableTemplatePublic, status_code=201)
def create_template(
    payload: ResultTableTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResultTableTemplatePublic:
    try:
        row = ResultTableTemplateService.create(
            db, current_user=current_user, data=payload.model_dump()
        )
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(e)
        ) from e
    return ResultTableTemplatePublic.model_validate(row)


@router.patch("/{template_id}", response_model=ResultTableTemplatePublic)
def update_template(
    template_id: int,
    payload: ResultTableTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResultTableTemplatePublic:
    data = payload.model_dump(exclude_unset=True)
    try:
        row = ResultTableTemplateService.update(
            db, current_user=current_user, template_id=template_id, data=data
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(e)
        ) from e
    return ResultTableTemplatePublic.model_validate(row)


@router.delete("/{template_id}", status_code=204)
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        ResultTableTemplateService.delete(
            db, current_user=current_user, template_id=template_id
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(e)
        ) from e
