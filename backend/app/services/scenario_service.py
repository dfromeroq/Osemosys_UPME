"""Servicio de negocio para escenarios y control de permisos.

Este módulo centraliza:
- creación de escenarios (incluyendo plantillas),
- poblado de osemosys_param_value desde defaults (parameter_value),
- administración de permisos por usuario.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import and_, cast, func, insert, literal, or_, select, String
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.db.dialect import osemosys_table as _osemosys_table
from app.models import (
    Emission,
    Fuel,
    OsemosysParamValue,
    Parameter,
    ParameterStorage,
    ParameterValue,
    Region,
    Scenario,
    ScenarioPermission,
    ScenarioTag,
    ScenarioTagCategory,
    ScenarioTagLink,
    Solver,
    Technology,
    UdcSet,
    User,
)
from app.services.scenario_tag_assignment_service import ScenarioTagAssignmentService
from app.repositories.scenario_repository import ScenarioRepository
from app.services.osemosys_param_audit_service import OsemosysParamAuditService, user_actor
from app.services.pagination import build_meta, normalize_pagination
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

# Compatibilidad para tests legacy que hacen monkeypatch de este símbolo.
osemosys_table = _osemosys_table


CLONE_BATCH_SIZE = 500_000


def _eq_or_is_null(column, value):
    """`column = value` o `column IS NULL` según el valor dado.

    Necesario porque en `osemosys_param_value` las dimensiones no usadas son
    NULL y `NULL = NULL` no es verdadero en SQL.
    """
    if value is None:
        return column.is_(None)
    return column == value


def _value_rule_clause(value_col, op: str, val: float | None):
    """Construye la comparación de una regla de año sobre `value`.

    Ops admitidos: `gt`, `lt`, `gte`, `lte`, `eq`, `ne`, `nonzero`, `zero`.
    Devuelve `None` si la op es desconocida o falta `val` para una op que lo requiere.
    """
    op = (op or "").lower()
    if op == "nonzero":
        return value_col != 0
    if op == "zero":
        return value_col == 0
    if val is None:
        return None
    if op == "gt":
        return value_col > val
    if op == "lt":
        return value_col < val
    if op == "gte":
        return value_col >= val
    if op == "lte":
        return value_col <= val
    if op == "eq":
        return value_col == val
    if op == "ne":
        return value_col != val
    return None


def _parse_year_rules(raw: str | None) -> list[tuple[int, str, float | None]]:
    """Parsea `"2025:gt:0.5,2030:nonzero"` a `[(2025,"gt",0.5),(2030,"nonzero",None)]`."""
    if not raw:
        return []
    out: list[tuple[int, str, float | None]] = []
    for part in raw.split(","):
        tokens = [t.strip() for t in part.split(":") if t.strip()]
        if len(tokens) < 2:
            continue
        try:
            year = int(tokens[0])
        except ValueError:
            continue
        op = tokens[1].lower()
        val: float | None = None
        if len(tokens) >= 3:
            try:
                val = float(tokens[2])
            except ValueError:
                val = None
        out.append((year, op, val))
    return out


class ScenarioService:
    """Reglas de negocio para gestión de escenarios OSEMOSYS."""

    @staticmethod
    def _tag_to_dict(tag: ScenarioTag) -> dict:
        """Serializa un ScenarioTag con su categoría anidada."""
        category = tag.category
        return {
            "id": int(tag.id),
            "name": tag.name,
            "color": tag.color,
            "sort_order": int(tag.sort_order),
            "category_id": int(tag.category_id),
            "category": (
                {
                    "id": int(category.id),
                    "name": category.name,
                    "hierarchy_level": int(category.hierarchy_level),
                    "sort_order": int(category.sort_order),
                    "max_tags_per_scenario": category.max_tags_per_scenario,
                    "is_exclusive_combination": bool(category.is_exclusive_combination),
                    "default_color": category.default_color,
                }
                if category is not None
                else None
            ),
        }

    @staticmethod
    def _tags_for_scenario(
        db: Session,
        scenario: Scenario,
        *,
        tags: list[ScenarioTag] | None = None,
    ) -> list[dict]:
        """Lista de tags del escenario ordenada por jerarquía (ascendente)."""
        rows = tags
        if rows is None:
            rows = ScenarioTagAssignmentService.list_tags(db, scenario_id=int(scenario.id))
        return [ScenarioService._tag_to_dict(r) for r in rows]

    @staticmethod
    def _primary_tag_dict(tags_dicts: list[dict]) -> dict | None:
        """Etiqueta "primaria" para compatibilidad con listados legacy.

        Se elige la de menor `hierarchy_level`; dentro del mismo nivel, la de
        menor `sort_order`. Si no hay tags, retorna None.
        """
        if not tags_dicts:
            return None
        def _sort_key(t: dict) -> tuple[int, int, int]:
            cat = t.get("category") or {}
            return (
                int(cat.get("hierarchy_level", 999)),
                int(cat.get("sort_order", 0)),
                int(t.get("sort_order", 0)),
            )
        return sorted(tags_dicts, key=_sort_key)[0]

    @staticmethod
    def _get_permission(db: Session, *, scenario_id: int, current_user: User) -> ScenarioPermission | None:
        permission = ScenarioRepository.get_permission_for_user(
            db, scenario_id=scenario_id, user_id=current_user.id
        )
        if permission is None:
            permission = ScenarioRepository.get_permission_by_identifier(
                db, scenario_id=scenario_id, user_identifier=f"user:{current_user.username}"
            )
        return permission

    @staticmethod
    def _is_scenario_admin(current_user: User) -> bool:
        """Usuario con el rol global de administración de escenarios."""
        return bool(getattr(current_user, "can_manage_scenarios", False))

    @staticmethod
    def _can_view_scenario(scenario: Scenario, *, current_user: User) -> bool:
        if scenario.owner == current_user.username:
            return True
        if ScenarioService._is_scenario_admin(current_user):
            return True
        return scenario.edit_policy in {"OPEN", "RESTRICTED"}

    @staticmethod
    def _effective_access(
        db: Session,
        *,
        scenario: Scenario,
        current_user: User,
    ) -> dict[str, bool]:
        if scenario.owner == current_user.username:
            return {
                "can_view": True,
                "is_owner": True,
                "can_edit_direct": True,
                "can_propose": True,
                "can_manage_values": True,
            }

        # Admin Escenarios: acceso pleno (menos is_owner).
        if ScenarioService._is_scenario_admin(current_user):
            return {
                "can_view": True,
                "is_owner": False,
                "can_edit_direct": True,
                "can_propose": True,
                "can_manage_values": True,
            }

        permission = ScenarioService._get_permission(
            db, scenario_id=int(scenario.id), current_user=current_user
        )

        if scenario.edit_policy == "OPEN":
            return {
                "can_view": True,
                "is_owner": False,
                "can_edit_direct": False,
                "can_propose": True,
                "can_manage_values": True,
            }

        if scenario.edit_policy == "RESTRICTED":
            return {
                "can_view": True,
                "is_owner": False,
                "can_edit_direct": bool(permission and permission.can_edit_direct),
                "can_propose": bool(permission and permission.can_propose),
                "can_manage_values": bool(
                    permission and (permission.can_manage_values or permission.can_edit_direct)
                ),
            }

        return {
            "can_view": False,
            "is_owner": False,
            "can_edit_direct": False,
            "can_propose": False,
            "can_manage_values": False,
        }

    @staticmethod
    def _to_public(
        db: Session,
        *,
        scenario: Scenario,
        current_user: User,
        base_scenario_name: str | None,
        tags: list[ScenarioTag] | None = None,
    ) -> dict:
        tag_dicts = ScenarioService._tags_for_scenario(db, scenario, tags=tags)
        # Solo devolvemos el `summary` del data_quality_warnings (no el detalle
        # completo que puede ser pesado). El detalle se consulta aparte vía
        # GET /scenarios/{id}/data-quality.
        dqw = getattr(scenario, "data_quality_warnings", None) or {}
        data_quality_summary = dqw.get("summary") if isinstance(dqw, dict) else None
        return {
            "id": int(scenario.id),
            "name": scenario.name,
            "description": scenario.description,
            "owner": scenario.owner,
            "base_scenario_id": int(scenario.base_scenario_id) if scenario.base_scenario_id is not None else None,
            "base_scenario_name": base_scenario_name,
            "changed_param_names": list(scenario.changed_param_names or []),
            "edit_policy": scenario.edit_policy,
            "simulation_type": getattr(scenario, "simulation_type", "NATIONAL"),
            "is_template": bool(scenario.is_template),
            "created_at": scenario.created_at,
            "tag": ScenarioService._primary_tag_dict(tag_dicts),
            "tags": tag_dicts,
            "effective_access": ScenarioService._effective_access(
                db, scenario=scenario, current_user=current_user
            ),
            "data_quality_summary": data_quality_summary,
        }

    @staticmethod
    def _track_changed_params(
        scenario: Scenario,
        *,
        param_names: list[str] | tuple[str, ...] | set[str],
    ) -> None:
        """Registra nombres de parámetros modificados en el escenario."""
        existing = list(scenario.changed_param_names or [])
        seen = {name for name in existing if isinstance(name, str)}
        for raw_name in param_names:
            clean_name = str(raw_name or "").strip()
            if not clean_name or clean_name in seen:
                continue
            existing.append(clean_name)
            seen.add(clean_name)
        scenario.changed_param_names = existing

    @staticmethod
    def _clone_data_batched(
        db: Session,
        *,
        source_id: int,
        new_id: int,
        batch_size: int = CLONE_BATCH_SIZE,
        on_batch: callable | None = None,
    ) -> int:
        """Copia osemosys_param_value por lotes usando paginación por cursor.

        Cada lote hace INSERT...SELECT de hasta *batch_size* filas y luego
        COMMIT, evitando transacciones gigantes que saturen la BD o causen
        timeouts en el cliente.
        """
        total = 0
        cursor = 0
        table = OsemosysParamValue.__table__

        while True:
            id_batch_subquery = (
                select(table.c.id)
                .where(table.c.id_scenario == source_id, table.c.id > cursor)
                .order_by(table.c.id)
                .limit(batch_size)
                .subquery()
            )
            max_id_in_batch = db.execute(select(func.max(id_batch_subquery.c.id))).scalar()

            if max_id_in_batch is None:
                break

            clone_select = select(
                literal(new_id),
                table.c.param_name,
                table.c.id_region,
                table.c.id_technology,
                table.c.id_fuel,
                table.c.id_emission,
                table.c.id_timeslice,
                table.c.id_mode_of_operation,
                table.c.id_season,
                table.c.id_daytype,
                table.c.id_dailytimebracket,
                table.c.id_storage_set,
                table.c.id_udc_set,
                table.c.year,
                table.c.value,
            ).where(
                table.c.id_scenario == source_id,
                table.c.id > cursor,
                table.c.id <= max_id_in_batch,
            )

            cnt = db.execute(
                insert(table).from_select(
                    [
                        table.c.id_scenario,
                        table.c.param_name,
                        table.c.id_region,
                        table.c.id_technology,
                        table.c.id_fuel,
                        table.c.id_emission,
                        table.c.id_timeslice,
                        table.c.id_mode_of_operation,
                        table.c.id_season,
                        table.c.id_daytype,
                        table.c.id_dailytimebracket,
                        table.c.id_storage_set,
                        table.c.id_udc_set,
                        table.c.year,
                        table.c.value,
                    ],
                    clone_select,
                )
            ).rowcount

            db.commit()
            total += cnt
            cursor = max_id_in_batch
            logger.info(
                "Lote clonado: %d filas (acumulado: %d)", cnt, total,
            )
            if on_batch is not None:
                on_batch(cnt, total)

        return total

    @staticmethod
    def _populate_osemosys_from_defaults(db: Session, *, target_scenario_id: int) -> int:
        """Copia los defaults de parameter_value a osemosys_param_value para un escenario.

        Hace INSERT...SELECT con JOIN a parameter para resolver param_name.
        Las dimensiones que parameter_value no tiene (timeslice, mode, season, etc.)
        quedan NULL y se completan después por run_notebook_preprocess.
        """
        target_table = OsemosysParamValue.__table__
        pv_table = ParameterValue.__table__
        p_table = Parameter.__table__
        ps_table = ParameterStorage.__table__

        source_select = (
            select(
                literal(target_scenario_id),
                p_table.c.name,
                pv_table.c.id_region,
                pv_table.c.id_technology,
                pv_table.c.id_fuel,
                pv_table.c.id_emission,
                ps_table.c.timesline,
                literal(None),
                ps_table.c.season,
                ps_table.c.daytype,
                ps_table.c.dailytimebracket,
                ps_table.c.id_storage_set,
                literal(None),
                pv_table.c.year,
                pv_table.c.value,
            )
            .select_from(
                pv_table.join(p_table, pv_table.c.id_parameter == p_table.c.id).outerjoin(
                    ps_table, ps_table.c.id_parameter_value == pv_table.c.id
                )
            )
        )

        result = db.execute(
            insert(target_table).from_select(
                [
                    target_table.c.id_scenario,
                    target_table.c.param_name,
                    target_table.c.id_region,
                    target_table.c.id_technology,
                    target_table.c.id_fuel,
                    target_table.c.id_emission,
                    target_table.c.id_timeslice,
                    target_table.c.id_mode_of_operation,
                    target_table.c.id_season,
                    target_table.c.id_daytype,
                    target_table.c.id_dailytimebracket,
                    target_table.c.id_storage_set,
                    target_table.c.id_udc_set,
                    target_table.c.year,
                    target_table.c.value,
                ],
                source_select,
            )
        )
        return result.rowcount

    @staticmethod
    def facets(
        db: Session,
        *,
        current_user: User,
        include_private: bool = False,
    ) -> dict:
        """Valores distintos para alimentar los filtros multiselect del listado.

        Respeta la visibilidad del usuario. ``include_private`` solo se honra
        si el usuario tiene ``can_manage_scenarios=True``.
        """
        honor_private = bool(
            include_private and ScenarioService._is_scenario_admin(current_user)
        )
        return ScenarioRepository.get_facets(
            db,
            current_username=current_user.username,
            include_private=honor_private,
        )

    @staticmethod
    def list(
        db: Session,
        *,
        current_user: User,
        busqueda: str | None,
        owner: str | None,
        edit_policy: str | None,
        permission_scope: str | None,
        cantidad: int | None,
        offset: int | None,
        include_private: bool = False,
        owners: list[str] | None = None,
        edit_policies: list[str] | None = None,
        simulation_types: list[str] | None = None,
        tag_ids: list[int] | None = None,
    ) -> dict:
        """Lista escenarios accesibles para el usuario autenticado.

        ``include_private`` solo se honra si el usuario tiene
        ``can_manage_scenarios=True``; en caso contrario, se ignora y se aplica
        el filtro de visibilidad estándar.
        """
        page, page_size, row_offset = normalize_pagination(offset, cantidad)
        honor_private = bool(
            include_private and ScenarioService._is_scenario_admin(current_user)
        )
        items, total = ScenarioRepository.get_paginated_accessible(
            db,
            current_username=current_user.username,
            busqueda=busqueda,
            owner=owner,
            edit_policy=edit_policy,
            permission_scope=permission_scope,
            row_offset=row_offset,
            limit=page_size,
            include_private=honor_private,
            owners=owners,
            edit_policies=edit_policies,
            simulation_types=simulation_types,
            tag_ids=tag_ids,
        )
        meta = build_meta(page, page_size, total, busqueda)
        # Batch lookup: tags por escenario en un solo query
        scenario_ids = [int(s.id) for s, _ in items]
        tags_by_scenario: dict[int, list[ScenarioTag]] = {sid: [] for sid in scenario_ids}
        if scenario_ids:
            link_rows = db.execute(
                select(ScenarioTagLink.scenario_id, ScenarioTag)
                .join(ScenarioTag, ScenarioTag.id == ScenarioTagLink.tag_id)
                .join(ScenarioTagCategory, ScenarioTagCategory.id == ScenarioTag.category_id)
                .options(joinedload(ScenarioTag.category))
                .where(ScenarioTagLink.scenario_id.in_(scenario_ids))
                .order_by(
                    ScenarioTagCategory.hierarchy_level.asc(),
                    ScenarioTagCategory.sort_order.asc(),
                    ScenarioTag.sort_order.asc(),
                    ScenarioTag.name.asc(),
                )
            ).all()
            for sid, tag in link_rows:
                tags_by_scenario.setdefault(int(sid), []).append(tag)
        return {
            "data": [
                ScenarioService._to_public(
                    db,
                    scenario=scenario,
                    current_user=current_user,
                    base_scenario_name=base_scenario_name,
                    tags=tags_by_scenario.get(int(scenario.id), []),
                )
                for scenario, base_scenario_name in items
            ],
            "meta": meta,
        }

    @staticmethod
    def get_public(db: Session, *, scenario_id: int, current_user: User) -> dict:
        """Retorna un escenario visible al usuario autenticado."""
        scenario, base_scenario_name = ScenarioRepository.get_by_id_with_base_name(db, scenario_id)
        if scenario is None:
            raise NotFoundError("Escenario no encontrado.")
        if not ScenarioService._can_view_scenario(scenario, current_user=current_user):
            raise ForbiddenError("No tienes acceso a este escenario.")
        return ScenarioService._to_public(
            db,
            scenario=scenario,
            current_user=current_user,
            base_scenario_name=base_scenario_name,
        )

    @staticmethod
    def create(
        db: Session,
        *,
        current_user: User,
        name: str,
        description: str | None,
        edit_policy: str,
        is_template: bool,
        simulation_type: str = "NATIONAL",
        processing_mode: str = "STANDARD",
        skip_populate_defaults: bool = False,
        tag_ids: list[int] | None = None,
    ):
        """Crea escenario y configura permisos iniciales del creador.

        Flujo:
            1. Inserta escenario.
            2. Crea permiso total para owner.
            3. Si no es plantilla, copia defaults de parameter_value a osemosys_param_value
               y ejecuta preprocesamiento (completar matrices, UDC, emisiones).
            4. Confirma transacción.

        Args:
            skip_populate_defaults: Si True, no copia defaults ni ejecuta preprocess.
                Usado cuando el flujo import-excel poblará osemosys_param_value directamente.
        """
        resolved_tag_ids: list[int] = []
        if tag_ids:
            unique_ids = list({int(t) for t in tag_ids})
            existing = (
                db.execute(select(ScenarioTag.id).where(ScenarioTag.id.in_(unique_ids)))
                .scalars()
                .all()
            )
            if len(existing) != len(unique_ids):
                raise NotFoundError("Al menos una etiqueta indicada no existe.")
            resolved_tag_ids = [int(x) for x in existing]
        scenario = Scenario(
            name=name,
            description=description,
            owner=current_user.username,
            edit_policy=edit_policy,
            simulation_type=simulation_type,
            processing_mode=processing_mode,
            is_template=is_template,
        )
        db.add(scenario)
        db.flush()
        for tid in resolved_tag_ids:
            db.add(ScenarioTagLink(scenario_id=int(scenario.id), tag_id=tid))

        ScenarioRepository.add_permission(
            db,
            scenario_id=scenario.id,
            user_identifier=f"user:{current_user.username}",
            user_id=current_user.id,
            can_edit_direct=True,
            can_propose=True,
            can_manage_values=True,
        )

        if not is_template and not skip_populate_defaults:
            count = ScenarioService._populate_osemosys_from_defaults(
                db, target_scenario_id=scenario.id
            )
            logger.info("Escenario %s: %d defaults copiados a osemosys_param_value", scenario.id, count)
            if count > 0:
                from app.services.sand_notebook_preprocess import run_notebook_preprocess
                preprocess_stats = run_notebook_preprocess(
                    db,
                    int(scenario.id),
                    filter_by_sets=True,
                    complete_matrices=False,
                    emission_ratios_at_input=False,
                    generate_udc_matrices=False,
                )
                logger.info("Escenario %s: preprocess completado %s", scenario.id, preprocess_stats)

        try:
            db.commit()
        except IntegrityError as e:
            db.rollback()
            raise ConflictError("No se pudo crear el escenario (posible duplicado o conflicto).") from e
        db.refresh(scenario)
        _, base_scenario_name = ScenarioRepository.get_by_id_with_base_name(db, scenario.id)
        return ScenarioService._to_public(
            db,
            scenario=scenario,
            current_user=current_user,
            base_scenario_name=base_scenario_name,
        )

    @staticmethod
    def clone(
        db: Session,
        *,
        source_scenario_id: int,
        current_user: User,
        name: str,
        description: str | None,
        edit_policy: str,
    ) -> dict:
        """Clona un escenario existente con todos sus OsemosysParamValue.

        El usuario debe tener acceso al escenario origen. El nuevo escenario
        pertenece al usuario actual. Los datos se copian con INSERT...SELECT
        para máxima eficiencia.
        """
        source = ScenarioService._require_access(
            db, scenario_id=source_scenario_id, current_user=current_user,
        )

        new_scenario = Scenario(
            name=name,
            description=description,
            owner=current_user.username,
            base_scenario_id=source.id,
            changed_param_names=[],
            edit_policy=edit_policy,
            simulation_type=getattr(source, "simulation_type", "NATIONAL"),
            processing_mode=getattr(source, "processing_mode", "STANDARD"),
            is_template=False,
            udc_config=source.udc_config,
        )
        db.add(new_scenario)
        db.flush()
        # Copia los tags del escenario origen (excluyendo los de categorías
        # con is_exclusive_combination — no copiamos "Oficial"/"Entregado" a un clon).
        source_tag_ids = (
            db.execute(
                select(ScenarioTagLink.tag_id)
                .join(ScenarioTag, ScenarioTag.id == ScenarioTagLink.tag_id)
                .join(ScenarioTagCategory, ScenarioTagCategory.id == ScenarioTag.category_id)
                .where(
                    ScenarioTagLink.scenario_id == source.id,
                    ScenarioTagCategory.is_exclusive_combination.is_(False),
                )
            )
            .scalars()
            .all()
        )
        for tid in source_tag_ids:
            db.add(ScenarioTagLink(scenario_id=int(new_scenario.id), tag_id=int(tid)))

        ScenarioRepository.add_permission(
            db,
            scenario_id=new_scenario.id,
            user_identifier=f"user:{current_user.username}",
            user_id=current_user.id,
            can_edit_direct=True,
            can_propose=True,
            can_manage_values=True,
        )

        try:
            db.commit()
        except IntegrityError as e:
            db.rollback()
            raise ConflictError("No se pudo clonar el escenario (posible duplicado o conflicto).") from e

        count = ScenarioService._clone_data_batched(
            db, source_id=source_scenario_id, new_id=new_scenario.id,
        )
        ScenarioService.sync_catalogs_from_scenario_values(db, scenario_id=int(new_scenario.id))
        logger.info(
            "Escenario %s clonado desde %s: %d filas copiadas",
            new_scenario.id, source_scenario_id, count,
        )

        db.refresh(new_scenario)
        return ScenarioService._to_public(
            db,
            scenario=new_scenario,
            current_user=current_user,
            base_scenario_name=source.name,
        )

    @staticmethod
    def _require_admin(db: Session, *, scenario_id: int, current_user: User):
        """Valida que usuario tenga capacidad administrativa del escenario."""
        scenario = ScenarioRepository.get_by_id(db, scenario_id)
        if not scenario:
            raise NotFoundError("Escenario no encontrado.")

        if scenario.owner == current_user.username:
            return scenario

        if ScenarioService._is_scenario_admin(current_user):
            return scenario

        perm = ScenarioRepository.get_permission_for_user(db, scenario_id=scenario_id, user_id=current_user.id)
        if not perm or not perm.can_edit_direct:
            raise ForbiddenError("No tienes permisos para administrar este escenario.")
        return scenario

    @staticmethod
    def _require_access(db: Session, *, scenario_id: int, current_user: User):
        """Valida acceso básico al escenario según reglas de visibilidad."""
        scenario = ScenarioRepository.get_by_id(db, scenario_id)
        if not scenario:
            raise NotFoundError("Escenario no encontrado.")
        if ScenarioService._can_view_scenario(scenario, current_user=current_user):
            return scenario
        raise ForbiddenError("No tienes acceso a este escenario.")

    @staticmethod
    def _require_manage_values(db: Session, *, scenario_id: int, current_user: User):
        """Valida capacidad de edición de valores del escenario."""
        scenario = ScenarioService._require_access(db, scenario_id=scenario_id, current_user=current_user)
        if scenario.owner == current_user.username:
            return scenario
        if ScenarioService._is_scenario_admin(current_user):
            return scenario
        permission = ScenarioService._get_permission(
            db, scenario_id=scenario_id, current_user=current_user
        )
        if scenario.edit_policy == "OPEN":
            return scenario
        if permission and (permission.can_manage_values or permission.can_edit_direct):
            return scenario
        raise ForbiddenError("No tienes permisos para editar valores de este escenario.")

    @staticmethod
    def _resolve_or_create_catalog_name(db: Session, *, model, name: str | None, label: str) -> int | None:
        cleaned = (name or "").strip()
        if not cleaned:
            return None
        obj = db.execute(select(model).where(model.name == cleaned)).scalar_one_or_none()
        if obj is None:
            try:
                with db.begin_nested():
                    obj = model(name=cleaned)
                    db.add(obj)
                    db.flush()
            except IntegrityError:
                obj = db.execute(select(model).where(model.name == cleaned)).scalar_one_or_none()
                if obj is None:
                    raise
        # Si el catálogo usa soft delete, se reactiva al reutilizarse desde escenario.
        if hasattr(obj, "is_active") and getattr(obj, "is_active") is False:
            setattr(obj, "is_active", True)
            db.flush()
        return int(obj.id)

    @staticmethod
    def _resolve_or_create_catalog_code(db: Session, *, model, code: str | None, label: str) -> int | None:
        cleaned = (code or "").strip()
        if not cleaned:
            return None
        obj = db.execute(select(model).where(model.code == cleaned)).scalar_one_or_none()
        if obj is None:
            try:
                with db.begin_nested():
                    obj = model(code=cleaned)
                    db.add(obj)
                    db.flush()
            except IntegrityError:
                obj = db.execute(select(model).where(model.code == cleaned)).scalar_one_or_none()
                if obj is None:
                    raise
        return int(obj.id)

    @staticmethod
    def _ensure_parameter_exists(db: Session, *, param_name: str) -> str:
        cleaned = str(param_name or "").strip()
        if not cleaned:
            raise ConflictError("El parámetro es obligatorio.")
        obj = db.execute(select(Parameter).where(Parameter.name == cleaned)).scalar_one_or_none()
        if obj is None:
            obj = Parameter(name=cleaned, is_active=True)
            db.add(obj)
            db.flush()
        elif obj.is_active is False:
            obj.is_active = True
            db.flush()
        return cleaned

    @staticmethod
    def _ensure_solver_if_provided(db: Session, *, solver_name: str | None) -> None:
        cleaned = (solver_name or "").strip()
        if not cleaned:
            return
        ScenarioService._resolve_or_create_catalog_name(
            db, model=Solver, name=cleaned, label="Solver"
        )

    @staticmethod
    def sync_catalogs_from_scenario_values(db: Session, *, scenario_id: int) -> None:
        """Sincroniza catálogos globales a partir de valores del escenario.

        - Garantiza que `param_name` de `osemosys_param_value` exista y esté activo en `parameter`.
        - Reactiva catálogos referenciados por ID (region, technology, fuel, emission).
        """
        # 1) Parámetros por nombre desde osemosys_param_value
        param_names = (
            db.execute(
                select(OsemosysParamValue.param_name)
                .where(OsemosysParamValue.id_scenario == scenario_id)
                .distinct()
            )
            .scalars()
            .all()
        )
        for raw_name in param_names:
            clean_name = str(raw_name or "").strip()
            if not clean_name:
                continue
            ScenarioService._ensure_parameter_exists(db, param_name=clean_name)

        # 2) Reactivar entidades referenciadas por IDs del escenario
        id_regions = (
            db.execute(
                select(OsemosysParamValue.id_region)
                .where(
                    OsemosysParamValue.id_scenario == scenario_id,
                    OsemosysParamValue.id_region.is_not(None),
                )
                .distinct()
            )
            .scalars()
            .all()
        )
        id_technologies = (
            db.execute(
                select(OsemosysParamValue.id_technology)
                .where(
                    OsemosysParamValue.id_scenario == scenario_id,
                    OsemosysParamValue.id_technology.is_not(None),
                )
                .distinct()
            )
            .scalars()
            .all()
        )
        id_fuels = (
            db.execute(
                select(OsemosysParamValue.id_fuel)
                .where(
                    OsemosysParamValue.id_scenario == scenario_id,
                    OsemosysParamValue.id_fuel.is_not(None),
                )
                .distinct()
            )
            .scalars()
            .all()
        )
        id_emissions = (
            db.execute(
                select(OsemosysParamValue.id_emission)
                .where(
                    OsemosysParamValue.id_scenario == scenario_id,
                    OsemosysParamValue.id_emission.is_not(None),
                )
                .distinct()
            )
            .scalars()
            .all()
        )

        for model, ids in (
            (Region, id_regions),
            (Technology, id_technologies),
            (Fuel, id_fuels),
            (Emission, id_emissions),
        ):
            if not ids:
                continue
            objects = (
                db.execute(select(model).where(model.id.in_(list(ids))))
                .scalars()
                .all()
            )
            for obj in objects:
                if hasattr(obj, "is_active") and getattr(obj, "is_active") is False:
                    setattr(obj, "is_active", True)
            db.flush()

    @staticmethod
    def list_permissions(db: Session, *, scenario_id: int, current_user: User):
        """Lista permisos del escenario si el usuario es administrador."""
        ScenarioService._require_admin(db, scenario_id=scenario_id, current_user=current_user)
        return ScenarioRepository.list_permissions(db, scenario_id=scenario_id)

    @staticmethod
    def upsert_permission(
        db: Session,
        *,
        scenario_id: int,
        current_user: User,
        user_id: uuid.UUID | None,
        user_identifier: str | None,
        can_edit_direct: bool,
        can_propose: bool,
        can_manage_values: bool,
    ):
        """Crea o actualiza permiso de acceso para un usuario del escenario."""
        ScenarioService._require_admin(db, scenario_id=scenario_id, current_user=current_user)

        identifier = (user_identifier or "").strip()
        if not identifier:
            identifier = f"user:{user_id}"

        resolved_user_id = user_id
        if resolved_user_id is None and identifier.startswith("user:"):
            username = identifier.split(":", maxsplit=1)[1].strip()
            if username:
                target = UserService.get_by_username(db, username=username)
                if target:
                    resolved_user_id = target.id

        perm = ScenarioRepository.get_permission_by_identifier(db, scenario_id=scenario_id, user_identifier=identifier)
        if perm:
            if resolved_user_id is not None:
                perm.user_id = resolved_user_id
            perm.can_edit_direct = can_edit_direct
            perm.can_propose = can_propose
            perm.can_manage_values = can_manage_values
        else:
            perm = ScenarioRepository.add_permission(
                db,
                scenario_id=scenario_id,
                user_identifier=identifier,
                user_id=resolved_user_id,
                can_edit_direct=can_edit_direct,
                can_propose=can_propose,
                can_manage_values=can_manage_values,
            )
        try:
            db.commit()
        except IntegrityError as e:
            db.rollback()
            raise ConflictError("No se pudo crear/actualizar el permiso (posible conflicto).") from e
        db.refresh(perm)
        return perm

    @staticmethod
    def update_metadata(
        db: Session,
        *,
        scenario_id: int,
        current_user: User,
        payload: dict,
    ) -> dict:
        """Actualiza nombre, descripción y/o política del escenario."""
        scenario = ScenarioService._require_admin(db, scenario_id=scenario_id, current_user=current_user)
        new_name = payload.get("name")
        new_description = payload.get("description")
        new_edit_policy = payload.get("edit_policy")
        touched = False

        if new_name is not None:
            clean_name = str(new_name).strip()
            if not clean_name:
                raise ConflictError("El nombre del escenario es obligatorio.")
            if clean_name != scenario.name:
                scenario.name = clean_name
                touched = True

        if new_description is not None:
            clean_description = str(new_description).strip() or None
            if clean_description != scenario.description:
                scenario.description = clean_description
                touched = True

        if new_edit_policy is not None and new_edit_policy != scenario.edit_policy:
            scenario.edit_policy = str(new_edit_policy)
            touched = True

        if "simulation_type" in payload and payload.get("simulation_type") is not None:
            new_simulation_type = str(payload["simulation_type"]).strip() or "NATIONAL"
            if new_simulation_type != scenario.simulation_type:
                scenario.simulation_type = new_simulation_type
                touched = True

        if "tag_ids" in payload:
            raw_ids = payload.get("tag_ids") or []
            ScenarioTagAssignmentService.replace_tags(
                db,
                scenario_id=int(scenario.id),
                tag_ids=[int(t) for t in raw_ids],
            )
            touched = True

        if touched:
            try:
                db.commit()
            except IntegrityError as e:
                db.rollback()
                raise ConflictError("No se pudo actualizar el escenario (posible duplicado o conflicto).") from e
            db.refresh(scenario)

        _, base_scenario_name = ScenarioRepository.get_by_id_with_base_name(db, scenario_id)
        return ScenarioService._to_public(
            db,
            scenario=scenario,
            current_user=current_user,
            base_scenario_name=base_scenario_name,
        )

    @staticmethod
    def list_osemosys_values(
        db: Session,
        *,
        scenario_id: int,
        current_user: User,
        param_name: str | None = None,
        param_name_exact: bool = False,
        year: int | None = None,
        search: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict:
        """Paginación server-side de valores OSeMOSYS con búsqueda global.

        Hace LEFT JOIN con tablas de catálogo para resolver nombres y permitir
        búsqueda ILIKE en todas las columnas visibles (parámetro, región,
        tecnología, combustible, emisión, UDC, año, valor).
        """
        ScenarioService._require_access(db, scenario_id=scenario_id, current_user=current_user)

        query = (
            db.query(
                OsemosysParamValue,
                Region.name.label("region_name"),
                Technology.name.label("technology_name"),
                Fuel.name.label("fuel_name"),
                Emission.name.label("emission_name"),
                UdcSet.code.label("udc_name"),
            )
            .outerjoin(Region, OsemosysParamValue.id_region == Region.id)
            .outerjoin(Technology, OsemosysParamValue.id_technology == Technology.id)
            .outerjoin(Fuel, OsemosysParamValue.id_fuel == Fuel.id)
            .outerjoin(Emission, OsemosysParamValue.id_emission == Emission.id)
            .outerjoin(UdcSet, OsemosysParamValue.id_udc_set == UdcSet.id)
            .filter(OsemosysParamValue.id_scenario == scenario_id)
        )

        if param_name and param_name.strip():
            p = param_name.strip()
            if param_name_exact:
                query = query.filter(OsemosysParamValue.param_name == p)
            else:
                query = query.filter(OsemosysParamValue.param_name.ilike(f"%{p}%"))
        if year is not None:
            query = query.filter(OsemosysParamValue.year == year)

        if search and search.strip():
            term = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    OsemosysParamValue.param_name.ilike(term),
                    Region.name.ilike(term),
                    Technology.name.ilike(term),
                    Fuel.name.ilike(term),
                    Emission.name.ilike(term),
                    UdcSet.code.ilike(term),
                    cast(OsemosysParamValue.year, String).ilike(term),
                    cast(OsemosysParamValue.value, String).ilike(term),
                )
            )

        total = query.count()

        safe_limit = max(1, min(limit, 500))
        safe_offset = max(0, offset)

        rows = (
            query.order_by(
                OsemosysParamValue.param_name.asc(),
                OsemosysParamValue.year.asc(),
                OsemosysParamValue.id.asc(),
            )
            .offset(safe_offset)
            .limit(safe_limit)
            .all()
        )

        items = [
            {
                "id": int(r.OsemosysParamValue.id),
                "id_scenario": int(r.OsemosysParamValue.id_scenario),
                "param_name": str(r.OsemosysParamValue.param_name),
                "region_name": r.region_name,
                "technology_name": r.technology_name,
                "fuel_name": r.fuel_name,
                "emission_name": r.emission_name,
                "udc_name": r.udc_name,
                "year": int(r.OsemosysParamValue.year) if r.OsemosysParamValue.year is not None else None,
                "value": float(r.OsemosysParamValue.value),
            }
            for r in rows
        ]

        return {"items": items, "total": total, "offset": safe_offset, "limit": safe_limit}

    # Sentinel que el frontend envía cuando selecciona la opción "(vacío)".
    NULL_SENTINEL = "__NULL__"

    @staticmethod
    def _wide_filter_clauses(
        *,
        db: Session | None = None,
        scenario_id: int,
        param_name: str | None,
        param_name_exact: bool,
        search: str | None,
        param_names: list[str] | None,
        region_names: list[str] | None,
        technology_names: list[str] | None,
        fuel_names: list[str] | None,
        emission_names: list[str] | None,
        udc_names: list[str] | None,
        year_rules: list[tuple[int, str, float | None]] | None = None,
        skip_column: str | None = None,
    ) -> tuple[list, bool]:
        """Construye las cláusulas WHERE del wide endpoint.

        Devuelve `(clauses, needs_search_joins)`. `skip_column` omite la
        cláusula IN de esa columna — útil al calcular facets "exclude-self"
        para que los valores de la propia columna no se auto-filtren.

        Si se pasan `year_rules` y `db` no es None, se aplican usando la
        estrategia rápida de `_year_rules_clauses`. Si `db` es None, las
        reglas se ignoran (p.ej. en la query de años para evitar trabajo extra).

        Cada lista `*_names` puede contener el sentinel `NULL_SENTINEL` para
        incluir filas donde la columna es NULL; se combina con OR:
        `col IN (...) OR col IS NULL`.

        `year_rules` es una lista de `(year, op, value)` donde `op` ∈
        {gt, lt, gte, lte, eq, ne, nonzero, zero}. Para cada regla se
        requiere que exista al menos una fila del mismo grupo con ese año
        satisfaciendo la comparación (EXISTS correlacionado).
        """
        clauses: list = [OsemosysParamValue.id_scenario == scenario_id]

        if param_name and param_name.strip():
            p = param_name.strip()
            if param_name_exact:
                clauses.append(OsemosysParamValue.param_name == p)
            else:
                clauses.append(OsemosysParamValue.param_name.ilike(f"%{p}%"))

        def _split_null(values: list[str] | None) -> tuple[list[str], bool]:
            """Devuelve `(valores_limpios_sin_null, incluye_null)`."""
            if not values:
                return [], False
            include_null = False
            cleaned: list[str] = []
            for v in values:
                s = (v or "").strip()
                if not s:
                    continue
                if s == ScenarioService.NULL_SENTINEL:
                    include_null = True
                else:
                    cleaned.append(s)
            return cleaned, include_null

        def _column_filter(id_col, values: list[str], include_null: bool, name_col=None, model=None):
            """IN sobre ids (resueltos por nombre) y/o IS NULL según `include_null`."""
            parts = []
            if values:
                if model is not None and name_col is not None:
                    parts.append(
                        id_col.in_(select(model.id).where(name_col.in_(values)))
                    )
                else:
                    parts.append(id_col.in_(values))
            if include_null:
                parts.append(id_col.is_(None))
            if not parts:
                return None
            return or_(*parts)

        # param_name no puede ser NULL (NOT NULL en DB) — pero respetamos la API.
        if skip_column != "param_name":
            vals, include_null = _split_null(param_names)
            c = _column_filter(OsemosysParamValue.param_name, vals, include_null)
            if c is not None:
                clauses.append(c)

        column_specs = [
            ("region", OsemosysParamValue.id_region, Region, Region.name, region_names),
            ("technology", OsemosysParamValue.id_technology, Technology, Technology.name, technology_names),
            ("fuel", OsemosysParamValue.id_fuel, Fuel, Fuel.name, fuel_names),
            ("emission", OsemosysParamValue.id_emission, Emission, Emission.name, emission_names),
            ("udc", OsemosysParamValue.id_udc_set, UdcSet, UdcSet.code, udc_names),
        ]
        for col_key, id_col, model, name_col, raw in column_specs:
            if skip_column == col_key:
                continue
            vals, include_null = _split_null(raw)
            c = _column_filter(id_col, vals, include_null, name_col=name_col, model=model)
            if c is not None:
                clauses.append(c)

        # Reglas sobre años (estrategia rápida: id-IN o intersección en Python).
        if db is not None and year_rules:
            clauses.extend(ScenarioService._year_rules_clauses(db, scenario_id, year_rules))

        needs_search_joins = bool((search or "").strip())
        return clauses, needs_search_joins

    @staticmethod
    def _year_rules_clauses(
        db: Session, scenario_id: int, year_rules: list[tuple[int, str, float | None]] | None
    ) -> list:
        """Clausulas SQL para aplicar reglas sobre años.

        Estrategia:
        - 1 regla: aplica `year` y `value` directamente sobre el query externo.
          Eso evita un self-subquery sobre `osemosys_param_value`, que en
          escenarios grandes obliga a PostgreSQL a resolver millones de ids.
        - N reglas: calcula en Python la intersección de tuplas de dimensiones
          que matchean cada regla, y aplica `OR` de `AND`s (con `_eq_or_is_null`
          para los NULL) para restringir el outer. Más SQL pero evita el
          EXISTS con `IS NOT DISTINCT FROM` que no usa índices en Postgres.
        """
        if not year_rules:
            return []

        # Filtrar reglas inválidas (op desconocida o valor faltante).
        valid: list[tuple[int, str, float | None]] = []
        for year, op, val in year_rules:
            if _value_rule_clause(OsemosysParamValue.value, op, val) is not None:
                valid.append((year, op, val))
        if not valid:
            return []

        if len(valid) == 1:
            year, op, val = valid[0]
            value_clause = _value_rule_clause(OsemosysParamValue.value, op, val)
            return [
                OsemosysParamValue.year == int(year),
                value_clause,
            ]

        # Multi-regla: intersección en Python de tuplas de dimensiones.
        surviving: set[tuple] | None = None
        for year, op, val in valid:
            value_clause = _value_rule_clause(OsemosysParamValue.value, op, val)
            q = (
                db.query(
                    OsemosysParamValue.param_name,
                    OsemosysParamValue.id_region,
                    OsemosysParamValue.id_technology,
                    OsemosysParamValue.id_fuel,
                    OsemosysParamValue.id_emission,
                    OsemosysParamValue.id_timeslice,
                    OsemosysParamValue.id_mode_of_operation,
                    OsemosysParamValue.id_season,
                    OsemosysParamValue.id_daytype,
                    OsemosysParamValue.id_dailytimebracket,
                    OsemosysParamValue.id_storage_set,
                    OsemosysParamValue.id_udc_set,
                )
                .distinct()
                .filter(
                    OsemosysParamValue.id_scenario == scenario_id,
                    OsemosysParamValue.year == int(year),
                    value_clause,
                )
            )
            tuples = {tuple(row) for row in q.all()}
            surviving = tuples if surviving is None else (surviving & tuples)
            if not surviving:
                break

        if not surviving:
            from sqlalchemy import literal
            return [literal(False)]

        conds = []
        for t in surviving:
            conds.append(
                and_(
                    OsemosysParamValue.param_name == t[0],
                    _eq_or_is_null(OsemosysParamValue.id_region, t[1]),
                    _eq_or_is_null(OsemosysParamValue.id_technology, t[2]),
                    _eq_or_is_null(OsemosysParamValue.id_fuel, t[3]),
                    _eq_or_is_null(OsemosysParamValue.id_emission, t[4]),
                    _eq_or_is_null(OsemosysParamValue.id_timeslice, t[5]),
                    _eq_or_is_null(OsemosysParamValue.id_mode_of_operation, t[6]),
                    _eq_or_is_null(OsemosysParamValue.id_season, t[7]),
                    _eq_or_is_null(OsemosysParamValue.id_daytype, t[8]),
                    _eq_or_is_null(OsemosysParamValue.id_dailytimebracket, t[9]),
                    _eq_or_is_null(OsemosysParamValue.id_storage_set, t[10]),
                    _eq_or_is_null(OsemosysParamValue.id_udc_set, t[11]),
                )
            )
        return [or_(*conds)]

    @staticmethod
    def list_osemosys_values_wide(
        db: Session,
        *,
        scenario_id: int,
        current_user: User,
        param_name: str | None = None,
        param_name_exact: bool = False,
        search: str | None = None,
        param_names: list[str] | None = None,
        region_names: list[str] | None = None,
        technology_names: list[str] | None = None,
        fuel_names: list[str] | None = None,
        emission_names: list[str] | None = None,
        udc_names: list[str] | None = None,
        year_rules: list[tuple[int, str, float | None]] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict:
        """Versión pivotada (formato wide) de `list_osemosys_values`.

        Agrupa filas por la tupla completa de dimensiones
        `(param_name, id_region, id_technology, id_fuel, id_emission,
        id_timeslice, id_mode_of_operation, id_season, id_daytype,
        id_dailytimebracket, id_storage_set, id_udc_set)` y expone las
        celdas `{year: {id, value}}` por grupo. `year IS NULL` se mapea a la
        clave `"scalar"`.

        Filtros por columna: `*_names` aplica `IN (...)` combinando con AND
        entre columnas y OR dentro de cada columna.

        Estrategia eficiente (3 queries):
        1. Query de grupos distintos paginados.
        2. Count de grupos distintos.
        3. Query de celdas sólo para los grupos paginados.
        4. Query ligera de años del set filtrado (header consistente entre páginas).
        """
        ScenarioService._require_access(db, scenario_id=scenario_id, current_user=current_user)

        safe_limit = max(1, min(limit, 500))
        safe_offset = max(0, offset)

        group_cols = (
            OsemosysParamValue.param_name,
            OsemosysParamValue.id_region,
            OsemosysParamValue.id_technology,
            OsemosysParamValue.id_fuel,
            OsemosysParamValue.id_emission,
            OsemosysParamValue.id_timeslice,
            OsemosysParamValue.id_mode_of_operation,
            OsemosysParamValue.id_season,
            OsemosysParamValue.id_daytype,
            OsemosysParamValue.id_dailytimebracket,
            OsemosysParamValue.id_storage_set,
            OsemosysParamValue.id_udc_set,
        )

        clauses, needs_search_joins = ScenarioService._wide_filter_clauses(
            db=db,
            scenario_id=scenario_id,
            param_name=param_name,
            param_name_exact=param_name_exact,
            search=search,
            param_names=param_names,
            region_names=region_names,
            technology_names=technology_names,
            fuel_names=fuel_names,
            emission_names=emission_names,
            udc_names=udc_names,
            year_rules=year_rules,
        )
        # Para step 4 (años de surviving groups) NO aplicamos year_rules:
        # se pre-computan las cláusulas sin pasar `db` a year_rules.
        years_clauses, _ = ScenarioService._wide_filter_clauses(
            db=None,  # fuerza skip de year_rules
            scenario_id=scenario_id,
            param_name=param_name,
            param_name_exact=param_name_exact,
            search=search,
            param_names=param_names,
            region_names=region_names,
            technology_names=technology_names,
            fuel_names=fuel_names,
            emission_names=emission_names,
            udc_names=udc_names,
            year_rules=None,
        )
        search_term = (search or "").strip()

        def _apply_filters(q, with_joins: bool, which: str = "main"):
            """`which='main'` usa `clauses` (con year_rules); `which='years'` usa `years_clauses` (sin)."""
            applied = clauses if which == "main" else years_clauses
            q = q.filter(*applied)
            if needs_search_joins and with_joins:
                q = (
                    q.outerjoin(Region, OsemosysParamValue.id_region == Region.id)
                    .outerjoin(Technology, OsemosysParamValue.id_technology == Technology.id)
                    .outerjoin(Fuel, OsemosysParamValue.id_fuel == Fuel.id)
                    .outerjoin(Emission, OsemosysParamValue.id_emission == Emission.id)
                    .outerjoin(UdcSet, OsemosysParamValue.id_udc_set == UdcSet.id)
                )
                term = f"%{search_term}%"
                q = q.filter(
                    or_(
                        OsemosysParamValue.param_name.ilike(term),
                        Region.name.ilike(term),
                        Technology.name.ilike(term),
                        Fuel.name.ilike(term),
                        Emission.name.ilike(term),
                        UdcSet.code.ilike(term),
                    )
                )
            return q

        # 1. Page de grupos distintos
        groups_query = _apply_filters(
            db.query(*group_cols).distinct(), with_joins=needs_search_joins
        )
        group_rows = (
            groups_query.order_by(
                OsemosysParamValue.param_name.asc(),
                OsemosysParamValue.id_region.asc().nulls_last(),
                OsemosysParamValue.id_technology.asc().nulls_last(),
                OsemosysParamValue.id_fuel.asc().nulls_last(),
                OsemosysParamValue.id_emission.asc().nulls_last(),
                OsemosysParamValue.id_udc_set.asc().nulls_last(),
            )
            .offset(safe_offset)
            .limit(safe_limit)
            .all()
        )

        # 2. Count de grupos
        count_subq = _apply_filters(
            db.query(*group_cols).distinct(), with_joins=needs_search_joins
        ).subquery()
        total = db.query(func.count()).select_from(count_subq).scalar() or 0

        # 4. Años y flag escalar (sin year_rules, sólo filtros de dims).
        years_query = _apply_filters(
            db.query(OsemosysParamValue.year).distinct(),
            with_joins=needs_search_joins,
            which="years",
        )
        raw_years = [r[0] for r in years_query.all()]
        has_scalar = any(y is None for y in raw_years)
        years = sorted(y for y in raw_years if y is not None)

        if not group_rows:
            return {
                "items": [],
                "total": int(total),
                "offset": safe_offset,
                "limit": safe_limit,
                "years": years,
                "has_scalar": has_scalar,
            }

        # 3. Celdas para los grupos paginados. Construimos OR de ANDs sobre la tupla.
        group_conditions = []
        for g in group_rows:
            conds = [
                OsemosysParamValue.param_name == g.param_name,
                _eq_or_is_null(OsemosysParamValue.id_region, g.id_region),
                _eq_or_is_null(OsemosysParamValue.id_technology, g.id_technology),
                _eq_or_is_null(OsemosysParamValue.id_fuel, g.id_fuel),
                _eq_or_is_null(OsemosysParamValue.id_emission, g.id_emission),
                _eq_or_is_null(OsemosysParamValue.id_timeslice, g.id_timeslice),
                _eq_or_is_null(OsemosysParamValue.id_mode_of_operation, g.id_mode_of_operation),
                _eq_or_is_null(OsemosysParamValue.id_season, g.id_season),
                _eq_or_is_null(OsemosysParamValue.id_daytype, g.id_daytype),
                _eq_or_is_null(OsemosysParamValue.id_dailytimebracket, g.id_dailytimebracket),
                _eq_or_is_null(OsemosysParamValue.id_storage_set, g.id_storage_set),
                _eq_or_is_null(OsemosysParamValue.id_udc_set, g.id_udc_set),
            ]
            group_conditions.append(and_(*conds))

        cells_rows = (
            db.query(
                OsemosysParamValue,
                Region.name.label("region_name"),
                Technology.name.label("technology_name"),
                Fuel.name.label("fuel_name"),
                Emission.name.label("emission_name"),
                UdcSet.code.label("udc_name"),
            )
            .outerjoin(Region, OsemosysParamValue.id_region == Region.id)
            .outerjoin(Technology, OsemosysParamValue.id_technology == Technology.id)
            .outerjoin(Fuel, OsemosysParamValue.id_fuel == Fuel.id)
            .outerjoin(Emission, OsemosysParamValue.id_emission == Emission.id)
            .outerjoin(UdcSet, OsemosysParamValue.id_udc_set == UdcSet.id)
            .filter(OsemosysParamValue.id_scenario == scenario_id)
            .filter(or_(*group_conditions))
            .all()
        )

        # Pivot en Python respetando el orden de `group_rows`.
        def _group_key(row) -> tuple:
            return (
                row.param_name,
                row.id_region,
                row.id_technology,
                row.id_fuel,
                row.id_emission,
                row.id_timeslice,
                row.id_mode_of_operation,
                row.id_season,
                row.id_daytype,
                row.id_dailytimebracket,
                row.id_storage_set,
                row.id_udc_set,
            )

        groups_map: dict[tuple, dict] = {}
        for r in cells_rows:
            v = r.OsemosysParamValue
            key = _group_key(v)
            g = groups_map.get(key)
            if g is None:
                g = {
                    "param_name": v.param_name,
                    "region_name": r.region_name,
                    "technology_name": r.technology_name,
                    "fuel_name": r.fuel_name,
                    "emission_name": r.emission_name,
                    "udc_name": r.udc_name,
                    "cells": {},
                }
                groups_map[key] = g
            year_key = "scalar" if v.year is None else str(int(v.year))
            g["cells"][year_key] = {"id": int(v.id), "value": float(v.value)}

        items = []
        for g in group_rows:
            key = _group_key(g)
            entry = groups_map.get(key)
            if entry is None:
                continue
            items.append(
                {
                    "group_key": "|".join("" if k is None else str(k) for k in key),
                    **entry,
                }
            )

        return {
            "items": items,
            "total": int(total),
            "offset": safe_offset,
            "limit": safe_limit,
            "years": years,
            "has_scalar": has_scalar,
        }

    @staticmethod
    def list_osemosys_wide_facets(
        db: Session,
        *,
        scenario_id: int,
        current_user: User,
        param_name: str | None = None,
        param_name_exact: bool = False,
        search: str | None = None,
        param_names: list[str] | None = None,
        region_names: list[str] | None = None,
        technology_names: list[str] | None = None,
        fuel_names: list[str] | None = None,
        emission_names: list[str] | None = None,
        udc_names: list[str] | None = None,
        year_rules: list[tuple[int, str, float | None]] | None = None,
        limit_per_column: int = 500,
    ) -> dict:
        """Valores únicos por columna para el popover de filtros (exclude-self).

        Al calcular la lista de una columna, se aplican TODOS los filtros
        activos excepto el de esa misma columna — así el usuario puede agregar
        o quitar valores de esa columna sin que desaparezcan.

        Si la columna tiene filas con id NULL (dimensión no aplicable), se
        prepone el sentinel `__NULL__` a la lista; el frontend lo renderiza
        como "(vacío)".
        """
        ScenarioService._require_access(db, scenario_id=scenario_id, current_user=current_user)

        safe_limit = max(10, min(limit_per_column, 5000))

        def _build_filtered_query(value_col, column_key: str, needs_catalog_join: bool):
            clauses, needs_search_joins = ScenarioService._wide_filter_clauses(
                db=db,
                scenario_id=scenario_id,
                param_name=param_name,
                param_name_exact=param_name_exact,
                search=search,
                param_names=param_names,
                region_names=region_names,
                technology_names=technology_names,
                fuel_names=fuel_names,
                emission_names=emission_names,
                udc_names=udc_names,
                year_rules=year_rules,
                skip_column=column_key,
            )
            q = (
                db.query(value_col)
                .select_from(OsemosysParamValue)
                .distinct()
                .filter(*clauses)
            )
            if needs_search_joins or needs_catalog_join:
                q = (
                    q.outerjoin(Region, OsemosysParamValue.id_region == Region.id)
                    .outerjoin(Technology, OsemosysParamValue.id_technology == Technology.id)
                    .outerjoin(Fuel, OsemosysParamValue.id_fuel == Fuel.id)
                    .outerjoin(Emission, OsemosysParamValue.id_emission == Emission.id)
                    .outerjoin(UdcSet, OsemosysParamValue.id_udc_set == UdcSet.id)
                )
            if needs_search_joins:
                term = f"%{(search or '').strip()}%"
                q = q.filter(
                    or_(
                        OsemosysParamValue.param_name.ilike(term),
                        Region.name.ilike(term),
                        Technology.name.ilike(term),
                        Fuel.name.ilike(term),
                        Emission.name.ilike(term),
                        UdcSet.code.ilike(term),
                    )
                )
            return q

        def _facet(column_key: str, value_col, id_col, needs_catalog_join: bool, can_be_null: bool):
            q_values = _build_filtered_query(value_col, column_key, needs_catalog_join)
            q_values = q_values.filter(value_col.isnot(None)).order_by(value_col.asc()).limit(safe_limit)
            options = [str(r[0]) for r in q_values.all() if r[0] is not None]

            has_null = False
            if can_be_null and id_col is not None:
                # Query 2.0: filter() debe llamarse ANTES de limit().
                q_null = _build_filtered_query(id_col, column_key, needs_catalog_join)
                has_null = q_null.filter(id_col.is_(None)).limit(1).first() is not None
            if has_null:
                options = [ScenarioService.NULL_SENTINEL, *options]
            return options

        return {
            "param_names": _facet(
                "param_name",
                OsemosysParamValue.param_name,
                OsemosysParamValue.param_name,
                needs_catalog_join=False,
                can_be_null=False,  # NOT NULL en DB
            ),
            "region_names": _facet(
                "region", Region.name, OsemosysParamValue.id_region, needs_catalog_join=True, can_be_null=True
            ),
            "technology_names": _facet(
                "technology",
                Technology.name,
                OsemosysParamValue.id_technology,
                needs_catalog_join=True,
                can_be_null=True,
            ),
            "fuel_names": _facet(
                "fuel", Fuel.name, OsemosysParamValue.id_fuel, needs_catalog_join=True, can_be_null=True
            ),
            "emission_names": _facet(
                "emission", Emission.name, OsemosysParamValue.id_emission, needs_catalog_join=True, can_be_null=True
            ),
            "udc_names": _facet(
                "udc", UdcSet.code, OsemosysParamValue.id_udc_set, needs_catalog_join=True, can_be_null=True
            ),
        }

    @staticmethod
    def list_osemosys_param_audit(
        db: Session,
        *,
        scenario_id: int,
        current_user: User,
        param_name: str,
        offset: int = 0,
        limit: int = 50,
    ) -> dict:
        """Historial de auditoría para un `param_name` concreto (más reciente primero)."""
        ScenarioService._require_access(db, scenario_id=scenario_id, current_user=current_user)
        clean = (param_name or "").strip()
        safe_limit = max(1, min(limit, 500))
        safe_offset = max(0, offset)
        rows, total = OsemosysParamAuditService.list_for_param(
            db,
            scenario_id=scenario_id,
            param_name=clean,
            offset=safe_offset,
            limit=safe_limit,
        )
        items = [
            {
                "id": int(r.id),
                "param_name": str(r.param_name),
                "id_osemosys_param_value": int(r.id_osemosys_param_value)
                if r.id_osemosys_param_value is not None
                else None,
                "action": str(r.action),
                "old_value": float(r.old_value) if r.old_value is not None else None,
                "new_value": float(r.new_value) if r.new_value is not None else None,
                "dimensions_json": r.dimensions_json,
                "source": str(r.source),
                "changed_by": str(r.changed_by),
                "created_at": r.created_at,
            }
            for r in rows
        ]
        return {"items": items, "total": total, "offset": safe_offset, "limit": safe_limit}

    @staticmethod
    def ensure_default_reserve_margin_udc(db: Session, *, scenario_id: int) -> None:
        """Inserta valores UDC por defecto tipo 'RESERVEMARGIN' para un escenario.

        - Solo toca parámetros:
          - UDCMultiplierTotalCapacity
          - UDCConstant
          - UDCTag
        - Es idempotente: si ya existen filas con mismas dimensiones, solo actualiza value.
        """

        # Multiplicadores por tecnología (ejemplo RESERVEMARGIN del notebook).
        udc_multiplier_dict: dict[str, float] = {
            "PWRAFR": -1.0,
            "PWRBGS": -1.0,
            "PWRCOA": -1.0,
            "PWRCOACCS": -1.0,
            "PWRCSP": 0.0,
            "PWRDSL": -1.0,
            "PWRFOL": -1.0,
            "PWRGEO": -1.0,
            "PWRHYDDAM": -1.0,
            "PWRHYDROR": 0.0,
            "PWRHYDROR_NDC": 0.0,
            "PWRJET": -1.0,
            "PWRLPG": -1.0,
            "PWRNGS_CC": -1.0,
            "PWRNGS_CS": -1.0,
            "PWRNGSCCS": -1.0,
            "PWRNUC": -1.0,
            "PWRSOLRTP": 0.0,
            "PWRSOLRTP_ZNI": 0.0,
            "PWRSOLUGE": 0.0,
            "PWRSOLUGE_BAT": -1.0,
            "PWRSOLUPE": 0.0,
            "PWRSTD": 0.0,
            "PWRWAS": -1.0,
            "PWRWNDOFS_FIX": -1.0,
            "PWRWNDOFS_FLO": -1.0,
            "PWRWNDONS": -1.0,
            "GRDTYDELC": (1.0 / 0.9) * 1.2,
        }

        # UDCSet: RESERVEMARGIN (se crea si no existe).
        udc = db.execute(select(UdcSet).where(UdcSet.code == "RESERVEMARGIN")).scalar_one_or_none()
        if udc is None:
            udc = UdcSet(code="RESERVEMARGIN", description="Reserva de margen de capacidad (default)")
            db.add(udc)
            db.flush()
        udc_id = int(udc.id)

        # Tecnologías presentes en el catálogo que coinciden con el dict.
        tech_rows = (
            db.execute(select(Technology).where(Technology.name.in_(list(udc_multiplier_dict.keys()))))
            .scalars()
            .all()
        )
        tech_map: dict[str, int] = {t.name: int(t.id) for t in tech_rows}

        # Años activos del escenario (si no hay años, no hacemos nada).
        years = (
            db.execute(
                select(OsemosysParamValue.year)
                .where(
                    OsemosysParamValue.id_scenario == scenario_id,
                    OsemosysParamValue.year.is_not(None),
                )
                .distinct()
            )
            .scalars()
            .all()
        )
        year_list = sorted(int(y) for y in years if y is not None)
        if not year_list:
            return

        # Regiones del catálogo: aplicamos a todas; si alguna región no tiene tecnologías,
        # la restricción queda vacía y no afecta el modelo.
        region_ids = [int(r.id) for r in db.execute(select(Region)).scalars().all()]
        if not region_ids:
            return

        def _upsert(
            *,
            param_name: str,
            value: float,
            id_region: int,
            id_technology: int | None,
            year: int,
            id_udc_set: int,
        ) -> None:
            conds = [
                OsemosysParamValue.id_scenario == scenario_id,
                OsemosysParamValue.param_name == param_name,
                OsemosysParamValue.id_region == id_region,
                OsemosysParamValue.id_udc_set == id_udc_set,
                OsemosysParamValue.year == year,
            ]
            if id_technology is None:
                conds.append(OsemosysParamValue.id_technology.is_(None))
            else:
                conds.append(OsemosysParamValue.id_technology == id_technology)

            stmt = select(OsemosysParamValue).where(and_(*conds))
            obj = db.execute(stmt).scalar_one_or_none()
            if obj:
                obj.value = float(value)
                return
            db.add(
                OsemosysParamValue(
                    id_scenario=scenario_id,
                    param_name=param_name,
                    id_region=id_region,
                    id_technology=id_technology,
                    id_udc_set=id_udc_set,
                    year=year,
                    value=float(value),
                )
            )

        for region_id in region_ids:
            for year in year_list:
                # Constante y tag por región/año (<=, constante 0).
                _upsert(
                    param_name="UDCConstant",
                    value=0.0,
                    id_region=region_id,
                    id_technology=None,
                    year=year,
                    id_udc_set=udc_id,
                )
                _upsert(
                    param_name="UDCTag",
                    value=0.0,
                    id_region=region_id,
                    id_technology=None,
                    year=year,
                    id_udc_set=udc_id,
                )
                # Multiplicadores por tecnología.
                for tech_name, mult in udc_multiplier_dict.items():
                    tech_id = tech_map.get(tech_name)
                    if tech_id is None:
                        continue
                    _upsert(
                        param_name="UDCMultiplierTotalCapacity",
                        value=float(mult),
                        id_region=region_id,
                        id_technology=tech_id,
                        year=year,
                        id_udc_set=udc_id,
                    )

        db.commit()

    @staticmethod
    def _osemosys_value_to_public(db: Session, *, value_id: int) -> dict:
        """Devuelve un dict público de un OsemosysParamValue por ID exacto con JOINs."""
        row = (
            db.query(
                OsemosysParamValue,
                Region.name.label("region_name"),
                Technology.name.label("technology_name"),
                Fuel.name.label("fuel_name"),
                Emission.name.label("emission_name"),
                UdcSet.code.label("udc_name"),
            )
            .outerjoin(Region, OsemosysParamValue.id_region == Region.id)
            .outerjoin(Technology, OsemosysParamValue.id_technology == Technology.id)
            .outerjoin(Fuel, OsemosysParamValue.id_fuel == Fuel.id)
            .outerjoin(Emission, OsemosysParamValue.id_emission == Emission.id)
            .outerjoin(UdcSet, OsemosysParamValue.id_udc_set == UdcSet.id)
            .filter(OsemosysParamValue.id == value_id)
            .one()
        )
        return {
            "id": int(row.OsemosysParamValue.id),
            "id_scenario": int(row.OsemosysParamValue.id_scenario),
            "param_name": str(row.OsemosysParamValue.param_name),
            "region_name": row.region_name,
            "technology_name": row.technology_name,
            "fuel_name": row.fuel_name,
            "emission_name": row.emission_name,
            "udc_name": row.udc_name,
            "year": int(row.OsemosysParamValue.year) if row.OsemosysParamValue.year is not None else None,
            "value": float(row.OsemosysParamValue.value),
        }

    @staticmethod
    def _audit_dimensions_from_public(pub: dict) -> dict:
        return {
            "region_name": pub.get("region_name"),
            "technology_name": pub.get("technology_name"),
            "fuel_name": pub.get("fuel_name"),
            "emission_name": pub.get("emission_name"),
            "udc_name": pub.get("udc_name"),
            "year": pub.get("year"),
        }

    @staticmethod
    def create_osemosys_value(
        db: Session,
        *,
        scenario_id: int,
        current_user: User,
        payload: dict,
    ) -> dict:
        """Crea una fila OSeMOSYS en un escenario."""
        scenario = ScenarioService._require_manage_values(
            db, scenario_id=scenario_id, current_user=current_user
        )
        clean_param_name = ScenarioService._ensure_parameter_exists(
            db, param_name=str(payload.get("param_name") or "")
        )
        id_region = ScenarioService._resolve_or_create_catalog_name(
            db, model=Region, name=payload.get("region_name"), label="Región"
        )
        id_technology = ScenarioService._resolve_or_create_catalog_name(
            db, model=Technology, name=payload.get("technology_name"), label="Tecnología"
        )
        id_fuel = ScenarioService._resolve_or_create_catalog_name(
            db, model=Fuel, name=payload.get("fuel_name"), label="Combustible"
        )
        id_emission = ScenarioService._resolve_or_create_catalog_name(
            db, model=Emission, name=payload.get("emission_name"), label="Emisión"
        )
        ScenarioService._ensure_solver_if_provided(db, solver_name=payload.get("solver_name"))
        udc_code = (payload.get("udc_name") or "").strip() or None
        id_udc_set: int | None = None
        if udc_code:
            obj_udc = db.execute(select(UdcSet).where(UdcSet.code == udc_code)).scalar_one_or_none()
            if obj_udc is None:
                raise NotFoundError(f"UDC no encontrado: {udc_code}")
            id_udc_set = int(obj_udc.id)
        obj = OsemosysParamValue(
            id_scenario=scenario_id,
            param_name=clean_param_name,
            id_region=id_region,
            id_technology=id_technology,
            id_fuel=id_fuel,
            id_emission=id_emission,
            id_udc_set=id_udc_set,
            year=payload.get("year"),
            value=float(payload.get("value")),
        )
        db.add(obj)
        db.flush()
        ScenarioService._track_changed_params(
            scenario, param_names=[clean_param_name]
        )
        pub_ins = ScenarioService._osemosys_value_to_public(db, value_id=int(obj.id))
        OsemosysParamAuditService.append(
            db,
            scenario_id=scenario_id,
            param_name=pub_ins["param_name"],
            id_osemosys_param_value=int(obj.id),
            action="INSERT",
            old_value=None,
            new_value=float(pub_ins["value"]),
            dimensions_json=ScenarioService._audit_dimensions_from_public(pub_ins),
            source="API",
            changed_by=user_actor(current_user),
        )
        try:
            db.commit()
        except IntegrityError as e:
            db.rollback()
            raise ConflictError("No se pudo crear el valor OSeMOSYS (posible duplicado de dimensiones).") from e
        db.refresh(obj)
        return ScenarioService._osemosys_value_to_public(db, value_id=int(obj.id))

    @staticmethod
    def update_osemosys_value(
        db: Session,
        *,
        scenario_id: int,
        value_id: int,
        current_user: User,
        payload: dict,
    ) -> dict:
        """Actualiza una fila OSeMOSYS de escenario."""
        scenario = ScenarioService._require_manage_values(
            db, scenario_id=scenario_id, current_user=current_user
        )
        obj = db.get(OsemosysParamValue, value_id)
        if obj is None or int(obj.id_scenario) != scenario_id:
            raise NotFoundError("Valor OSeMOSYS no encontrado en el escenario.")
        old_pub = ScenarioService._osemosys_value_to_public(db, value_id=value_id)
        previous_param_name = obj.param_name
        obj.param_name = ScenarioService._ensure_parameter_exists(
            db, param_name=str(payload.get("param_name") or "")
        )
        obj.id_region = ScenarioService._resolve_or_create_catalog_name(
            db, model=Region, name=payload.get("region_name"), label="Región"
        )
        obj.id_technology = ScenarioService._resolve_or_create_catalog_name(
            db, model=Technology, name=payload.get("technology_name"), label="Tecnología"
        )
        obj.id_fuel = ScenarioService._resolve_or_create_catalog_name(
            db, model=Fuel, name=payload.get("fuel_name"), label="Combustible"
        )
        obj.id_emission = ScenarioService._resolve_or_create_catalog_name(
            db, model=Emission, name=payload.get("emission_name"), label="Emisión"
        )
        ScenarioService._ensure_solver_if_provided(db, solver_name=payload.get("solver_name"))
        udc_code = (payload.get("udc_name") or "").strip() or None
        if udc_code:
            obj_udc = db.execute(select(UdcSet).where(UdcSet.code == udc_code)).scalar_one_or_none()
            if obj_udc is None:
                raise NotFoundError(f"UDC no encontrado: {udc_code}")
            obj.id_udc_set = int(obj_udc.id)
        else:
            obj.id_udc_set = None
        obj.year = payload.get("year")
        obj.value = float(payload.get("value"))
        ScenarioService._track_changed_params(
            scenario,
            param_names=[previous_param_name, obj.param_name],
        )
        db.flush()
        new_pub = ScenarioService._osemosys_value_to_public(db, value_id=int(obj.id))
        OsemosysParamAuditService.append(
            db,
            scenario_id=scenario_id,
            param_name=new_pub["param_name"],
            id_osemosys_param_value=int(obj.id),
            action="UPDATE",
            old_value=float(old_pub["value"]),
            new_value=float(new_pub["value"]),
            dimensions_json=ScenarioService._audit_dimensions_from_public(new_pub),
            source="API",
            changed_by=user_actor(current_user),
        )
        try:
            db.commit()
        except IntegrityError as e:
            db.rollback()
            raise ConflictError("No se pudo actualizar el valor OSeMOSYS (posible duplicado de dimensiones).") from e
        db.refresh(obj)
        return ScenarioService._osemosys_value_to_public(db, value_id=int(obj.id))

    @staticmethod
    def deactivate_osemosys_value(
        db: Session,
        *,
        scenario_id: int,
        value_id: int,
        current_user: User,
    ) -> None:
        """Desactiva un valor OSeMOSYS eliminándolo del escenario."""
        scenario = ScenarioService._require_manage_values(
            db, scenario_id=scenario_id, current_user=current_user
        )
        obj = db.get(OsemosysParamValue, value_id)
        if obj is None or int(obj.id_scenario) != scenario_id:
            raise NotFoundError("Valor OSeMOSYS no encontrado en el escenario.")
        del_pub = ScenarioService._osemosys_value_to_public(db, value_id=value_id)
        ScenarioService._track_changed_params(scenario, param_names=[obj.param_name])
        OsemosysParamAuditService.append(
            db,
            scenario_id=scenario_id,
            param_name=del_pub["param_name"],
            id_osemosys_param_value=int(value_id),
            action="DELETE",
            old_value=float(del_pub["value"]),
            new_value=None,
            dimensions_json=ScenarioService._audit_dimensions_from_public(del_pub),
            source="API",
            changed_by=user_actor(current_user),
        )
        db.delete(obj)
        db.commit()


# ============================================================================
# Arquitectura y Consideraciones Técnicas
# ============================================================================
#
# Responsabilidad del módulo:
# - Gobernar ciclo de vida de escenarios y su modelo de permisos.
#
# Posibles mejoras:
# - Reemplazar clonación fila-a-fila por inserción bulk para plantillas grandes.
# - Introducir roles explícitos (OWNER, EDITOR, REVIEWER) para legibilidad.
#
# Riesgos en producción:
# - Clonado transaccional de plantillas grandes puede elevar tiempos de respuesta.
# - Permiso `can_edit_direct` como proxy de administración puede ser ambiguo.
#
# Escalabilidad:
# - Principal costo en I/O de BD y tamaño del dataset clonado.
