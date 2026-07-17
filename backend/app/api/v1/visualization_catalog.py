"""API de administración del catálogo de visualización."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.exceptions import ConflictError, NotFoundError
from app.db.session import get_db
from app.models import User
from app.schemas.visualization_catalog import (
    CatalogFormOptionsPublic,
    ChartConfigCreate,
    ChartConfigDetail,
    ChartConfigPublic,
    ChartConfigUpdate,
    ColorPaletteCreate,
    ColorPalettePublic,
    ColorPaletteUpdate,
    FilterGroupCreate,
    FilterGroupPublic,
    FilterGroupUpdate,
    FilterMembersImport,
    FilterMembersReplace,
    LabelCreate,
    LabelPagePublic,
    LabelPublic,
    LabelUpdate,
    MenuModulePublic,
    ResolvedFilterGroupPublic,
)
from app.services import visualization_catalog_service as svc

router = APIRouter(prefix="/visualization-catalog")


def _http_from_service(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    raise exc


@router.get("/form-options", response_model=CatalogFormOptionsPublic)
def read_form_options(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    return svc.get_form_options(db)


@router.get("/menu", response_model=list[MenuModulePublic])
def read_menu(db: Session = Depends(get_db)) -> list:
    return svc.get_menu(db)


# ── Filter groups ────────────────────────────────────────────────────────────


@router.get("/filter-groups", response_model=list[FilterGroupPublic])
def read_filter_groups(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list:
    return svc.list_filter_groups(db)


@router.post("/filter-groups", response_model=FilterGroupPublic, status_code=201)
def post_filter_group(
    body: FilterGroupCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FilterGroupPublic:
    try:
        return svc.create_filter_group(
            db, data=body.model_dump(), current_user=user
        )
    except (NotFoundError, ConflictError) as exc:
        raise _http_from_service(exc) from exc


@router.get("/filter-groups/{code}", response_model=FilterGroupPublic)
def read_filter_group(
    code: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> FilterGroupPublic:
    try:
        return svc.get_filter_group(db, code=code)
    except NotFoundError as exc:
        raise _http_from_service(exc) from exc


@router.get("/filter-groups/{code}/resolved", response_model=ResolvedFilterGroupPublic)
def read_filter_group_resolved(
    code: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ResolvedFilterGroupPublic:
    try:
        return svc.resolve_filter_group(db, code=code)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/filter-groups/{code}", response_model=FilterGroupPublic)
def patch_filter_group(
    code: str,
    body: FilterGroupUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FilterGroupPublic:
    try:
        return svc.update_filter_group(
            db, code=code, data=body.model_dump(exclude_unset=True), current_user=user
        )
    except NotFoundError as exc:
        raise _http_from_service(exc) from exc


@router.delete("/filter-groups/{code}", status_code=status.HTTP_204_NO_CONTENT)
def delete_filter_group(
    code: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    try:
        svc.delete_filter_group(db, code=code, current_user=user)
    except (NotFoundError, ConflictError) as exc:
        raise _http_from_service(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/filter-groups/{code}/members", response_model=FilterGroupPublic)
def put_filter_group_members(
    code: str,
    body: FilterMembersReplace,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FilterGroupPublic:
    try:
        return svc.replace_filter_group_members(
            db,
            code=code,
            members=[m.model_dump() for m in body.members],
            current_user=user,
        )
    except NotFoundError as exc:
        raise _http_from_service(exc) from exc


@router.post("/filter-groups/{code}/members/import", response_model=FilterGroupPublic)
def post_filter_group_members_import(
    code: str,
    body: FilterMembersImport,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FilterGroupPublic:
    try:
        return svc.import_filter_group_members(
            db, code=code, text=body.text, mode=body.mode, current_user=user
        )
    except NotFoundError as exc:
        raise _http_from_service(exc) from exc


# ── Labels ───────────────────────────────────────────────────────────────────


@router.get("/labels", response_model=LabelPagePublic)
def read_labels_paged(
    category: str | None = Query(None),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    return svc.list_labels(db, category=category, q=q, page=page, page_size=page_size)


@router.post("/labels", response_model=LabelPublic, status_code=201)
def post_label(
    body: LabelCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LabelPublic:
    try:
        return svc.create_label(db, data=body.model_dump(), current_user=user)
    except ConflictError as exc:
        raise _http_from_service(exc) from exc


@router.patch("/labels/{row_id}", response_model=LabelPublic)
def patch_label(
    row_id: int,
    body: LabelUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LabelPublic:
    try:
        return svc.update_label(
            db, row_id=row_id, data=body.model_dump(exclude_unset=True), current_user=user
        )
    except NotFoundError as exc:
        raise _http_from_service(exc) from exc


@router.delete("/labels/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_label(
    row_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    try:
        svc.delete_label(db, row_id=row_id, current_user=user)
    except NotFoundError as exc:
        raise _http_from_service(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Colors ───────────────────────────────────────────────────────────────────


@router.get("/colors", response_model=list[ColorPalettePublic])
def read_colors(
    group: str | None = Query(None),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list:
    return svc.list_colors(db, group=group)


@router.post("/colors", response_model=ColorPalettePublic, status_code=201)
def post_color(
    body: ColorPaletteCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ColorPalettePublic:
    try:
        return svc.create_color(db, data=body.model_dump(), current_user=user)
    except ConflictError as exc:
        raise _http_from_service(exc) from exc


@router.patch("/colors/{row_id}", response_model=ColorPalettePublic)
def patch_color(
    row_id: int,
    body: ColorPaletteUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ColorPalettePublic:
    try:
        return svc.update_color(
            db, row_id=row_id, data=body.model_dump(exclude_unset=True), current_user=user
        )
    except NotFoundError as exc:
        raise _http_from_service(exc) from exc


@router.delete("/colors/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_color(
    row_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    try:
        svc.delete_color(db, row_id=row_id, current_user=user)
    except NotFoundError as exc:
        raise _http_from_service(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Chart configs ────────────────────────────────────────────────────────────


@router.get("/chart-configs", response_model=list[ChartConfigPublic])
def read_chart_configs(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list:
    return svc.list_chart_configs(db)


@router.get("/chart-configs/{tipo}", response_model=ChartConfigDetail)
def read_chart_config(
    tipo: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ChartConfigDetail:
    try:
        return svc.get_chart_config(db, tipo=tipo)
    except NotFoundError as exc:
        raise _http_from_service(exc) from exc


@router.post("/chart-configs", response_model=ChartConfigDetail, status_code=201)
def post_chart_config(
    body: ChartConfigCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChartConfigDetail:
    try:
        return svc.create_chart_config(db, data=body.model_dump(), current_user=user)
    except ConflictError as exc:
        raise _http_from_service(exc) from exc


@router.patch("/chart-configs/{tipo}", response_model=ChartConfigDetail)
def patch_chart_config(
    tipo: str,
    body: ChartConfigUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChartConfigDetail:
    try:
        return svc.update_chart_config(
            db, tipo=tipo, data=body.model_dump(exclude_unset=True), current_user=user
        )
    except NotFoundError as exc:
        raise _http_from_service(exc) from exc


@router.delete("/chart-configs/{tipo}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chart_config(
    tipo: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    try:
        svc.delete_chart_config(db, tipo=tipo, current_user=user)
    except NotFoundError as exc:
        raise _http_from_service(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/repopulate")
def post_repopulate(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return svc.repopulate_catalog(db, current_user=user)
