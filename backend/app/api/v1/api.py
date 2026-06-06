"""Composición de routers para API v1.

Este archivo define el orden y agrupación de endpoints expuestos bajo `/api/v1`.
Mantener esta lista explícita facilita auditoría de superficie API y gobernanza
de versionado.
"""

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    change_requests,
    chart_series_config,
    deletion_log,
    emissions,
    fuels,
    health,
    official_import,
    parameter_values,
    parameters,
    regions,
    result_table_templates,
    saved_chart_templates,
    scenario_tag_assignments,
    scenario_tag_categories,
    scenario_tags,
    simulation_ops,
    scenarios,
    simulations,
    solvers,
    model_parameter_defaults,
    system_settings,
    technologies,
    users,
    visualizations,
    visualization_catalog,
)

router = APIRouter()

router.include_router(health.router, tags=["health"])
router.include_router(auth.router, tags=["auth"])
router.include_router(users.router, tags=["users"])

router.include_router(parameters.router, tags=["parameters"])
router.include_router(regions.router, tags=["regions"])
router.include_router(result_table_templates.router, tags=["result_table_templates"])
router.include_router(chart_series_config.router, tags=["chart_series_config"])
router.include_router(technologies.router, tags=["technologies"])
router.include_router(fuels.router, tags=["fuels"])
router.include_router(emissions.router, tags=["emissions"])
router.include_router(solvers.router, tags=["solvers"])
router.include_router(official_import.router, tags=["official_import"])

router.include_router(scenarios.router, tags=["scenarios"])
router.include_router(scenario_tag_assignments.router, tags=["scenario_tag_assignments"])
router.include_router(scenario_tag_categories.router, tags=["scenario_tag_categories"])
router.include_router(scenario_tags.router, tags=["scenario_tags"])
router.include_router(parameter_values.router, tags=["parameter_values"])
router.include_router(change_requests.router, tags=["change_requests"])
router.include_router(visualizations.router, tags=["visualizations"])
router.include_router(visualization_catalog.router, tags=["visualization_catalog"])
router.include_router(saved_chart_templates.router, tags=["saved_chart_templates"])
router.include_router(saved_chart_templates.reports_router, tags=["saved_reports"])
router.include_router(simulations.router, tags=["simulations"])
router.include_router(simulation_ops.router, tags=["simulation_ops"])
router.include_router(deletion_log.router, tags=["deletion_log"])
router.include_router(system_settings.router, tags=["system_settings"])
router.include_router(
    model_parameter_defaults.router,
    tags=["model_parameter_defaults"],
)


# ============================================================================
# Arquitectura y Consideraciones Técnicas
# ============================================================================
#
# Responsabilidad del módulo:
# - Ser punto único de ensamblaje de routers para versión v1.
#
# Posibles mejoras:
# - Introducir registro dinámico controlado por configuración para features flags.
#
# Riesgos en producción:
# - Cambios de orden/prefix no versionados pueden romper clientes existentes.
#
# Escalabilidad:
# - Sin impacto directo de performance; afecta mantenibilidad y trazabilidad de API.
