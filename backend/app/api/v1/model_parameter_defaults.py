"""API admin: defaults versionados del modelo OSeMOSYS."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_model_defaults_manager
from app.db.session import get_db
from app.models import User
from app.repositories.user_repository import UserRepository
from app.schemas.model_parameter_default import (
    ModelDefaultCatalogResponse,
    ModelDefaultCatalogRowPublic,
    ModelDefaultVersionCreate,
    ModelDefaultVersionCreateResponse,
    ModelDefaultVersionDetailPublic,
    ModelDefaultVersionListResponse,
    ModelDefaultVersionSummaryPublic,
)
from app.services.model_parameter_defaults_service import ModelParameterDefaultsService

router = APIRouter(prefix="/admin/model-parameter-defaults")


def _catalog_rows_to_public(
    rows: list,
) -> list[ModelDefaultCatalogRowPublic]:
    return [
        ModelDefaultCatalogRowPublic(
            param_key=r.param_key,
            pyomo_name=r.pyomo_name,
            index_dims=r.index_dims,
            category=r.category,
            description=r.description,
            value_type=r.value_type,
            min_value=r.min_value,
            max_value=r.max_value,
            requires_storage=r.requires_storage,
            requires_udc=r.requires_udc,
            value=r.value,
        )
        for r in rows
    ]


@router.get("/catalog", response_model=ModelDefaultCatalogResponse)
def get_catalog(
    db: Session = Depends(get_db),
    _: User = Depends(get_model_defaults_manager),
    version_id: int | None = Query(default=None),
) -> ModelDefaultCatalogResponse:
    active_id = ModelParameterDefaultsService.get_active_version_id(db)
    vid = version_id if version_id is not None else active_id
    rows = ModelParameterDefaultsService.list_catalog_with_values(db, version_id=vid)
    return ModelDefaultCatalogResponse(
        version_id=vid,
        is_active=vid == active_id,
        rows=_catalog_rows_to_public(rows),
    )


@router.get("/versions", response_model=ModelDefaultVersionListResponse)
def list_versions(
    db: Session = Depends(get_db),
    _: User = Depends(get_model_defaults_manager),
    limit: int = Query(default=50, ge=1, le=200),
) -> ModelDefaultVersionListResponse:
    active_id = ModelParameterDefaultsService.get_active_version_id(db)
    versions = ModelParameterDefaultsService.list_versions(db, limit=limit)
    return ModelDefaultVersionListResponse(
        active_version_id=active_id,
        versions=[
            ModelDefaultVersionSummaryPublic(
                id=v.id,
                created_at=v.created_at,  # type: ignore[arg-type]
                created_by_username=v.created_by_username,
                comment=v.comment,
                is_active=v.is_active,
            )
            for v in versions
        ],
    )


@router.get("/versions/{version_id}", response_model=ModelDefaultVersionDetailPublic)
def get_version_detail(
    version_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_model_defaults_manager),
) -> ModelDefaultVersionDetailPublic:
    try:
        version, _values = ModelParameterDefaultsService.get_version_detail(db, version_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    active_id = ModelParameterDefaultsService.get_active_version_id(db)
    username: str | None = None
    if version.created_by is not None:
        user = UserRepository.get_by_id(db, version.created_by)
        if user is not None:
            username = user.username

    rows = ModelParameterDefaultsService.list_catalog_with_values(db, version_id=version_id)
    return ModelDefaultVersionDetailPublic(
        id=version.id,
        created_at=version.created_at,  # type: ignore[arg-type]
        created_by_username=username,
        comment=version.comment,
        is_active=version.id == active_id,
        items=_catalog_rows_to_public(rows),
    )


@router.post("/versions", response_model=ModelDefaultVersionCreateResponse)
def create_version(
    payload: ModelDefaultVersionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_model_defaults_manager),
) -> ModelDefaultVersionCreateResponse:
    try:
        new_id = ModelParameterDefaultsService.create_version_from_items(
            db,
            items=[item.model_dump() for item in payload.items],
            user_id=current_user.id,
            comment=payload.comment,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    active_id = ModelParameterDefaultsService.get_active_version_id(db)
    return ModelDefaultVersionCreateResponse(
        version_id=new_id,
        active_version_id=active_id,
    )
