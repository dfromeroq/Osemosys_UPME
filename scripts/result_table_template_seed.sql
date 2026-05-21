-- Siembra idempotente de plantillas de tabla en página de resultados.
-- Ejecutar DESPUÉS de la migración Alembic 20260517_0024 (columna seed_key + índice único).
-- Esquema: osemosys
--
-- Equivalente a app.result_table_seeds + ensure_result_table_seeds.

INSERT INTO osemosys.result_table_template (
    seed_key, name, display_title, sort_order, is_enabled,
    tipo, un, sub_filtro, loc, variable, agrupar_por, region, timeslice,
    table_period_years, table_cumulative, custom_series_order,
    y_axis_min, y_axis_max, created_by_user_id
) VALUES
(
    'default_elec_produccion',
    'Tabla — Producción de electricidad',
    'Producción de Electricidad - ProductionByTechnology',
    0, true,
    'elec_produccion', 'PJ', NULL, NULL, NULL, 'TECNOLOGIA', NULL, NULL,
    NULL, NULL, NULL,
    NULL, NULL, NULL
),
(
    'default_prd_electricidad',
    'Tabla — Producción eléctrica (%)',
    'Producción de Electricidad - ProductionByTechnology (%)',
    1, true,
    'prd_electricidad', '%', NULL, NULL, NULL, 'TECNOLOGIA', NULL, NULL,
    NULL, NULL, NULL,
    NULL, NULL, NULL
),
(
    'default_cap_electricidad',
    'Tabla — Matriz eléctrica (capacidad)',
    'Matriz Eléctrica (Capacidad) - TotalCapacityAnnual',
    2, true,
    'cap_electricidad', 'GW', NULL, NULL, 'TotalCapacityAnnual', 'TECNOLOGIA', NULL, NULL,
    NULL, NULL, NULL,
    NULL, NULL, NULL
),
(
    'default_factor_planta',
    'Tabla — Factor de planta',
    'Factor de Planta (%)',
    3, true,
    'factor_planta', '%', NULL, NULL, NULL, 'TECNOLOGIA', NULL, NULL,
    NULL, NULL, NULL,
    NULL, NULL, NULL
)
ON CONFLICT (seed_key) DO NOTHING;
