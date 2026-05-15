# Runbook Operativo (Task + Logs)

Este runbook define una primera respuesta para incidentes comunes usando `task` como interfaz principal.

## Prerrequisitos

- Stack levantado con Docker Compose en la raiz del repositorio.
- `go-task` instalado para ejecutar `task ...`.

## Comandos base

```bash
# Estado general y healthcheck
task health

# Logs agregados
task logs

# Logs por servicio
task logs:api
task logs:worker
task logs:frontend
task logs:db
task logs:redis

# Filtro de errores de los ultimos 15 minutos
task logs:errors

# Ventana configurable de logs recientes
task logs:since MIN=30
```

## Playbooks de incidente

### 1) API no levanta / health falla

1. Ejecuta `task health`.
2. Si el health falla, revisa `task logs:api`.
3. Busca errores recientes: `task logs:errors MIN=30`.
4. Verifica base y cola: `task logs:db` y `task logs:redis`.

### 2) Worker no consume cola

1. Revisa estado con `task health`.
2. Sigue logs de worker: `task logs:worker`.
3. Correlaciona con API: `task logs:api`.
4. Filtra errores: `task logs:errors MIN=60`.

### 3) Simulacion queda en FAILED

1. Revisa logs de worker: `task logs:worker`.
2. Busca el contexto en API: `task logs:api`.
3. Ejecuta filtro global: `task logs:errors MIN=60`.
4. Si hay fallas de persistencia o conexion, revisar `task logs:db`.

### 4) Frontend no conecta con API

1. Revisa estado general: `task health`.
2. Sigue logs de frontend: `task logs:frontend`.
3. Correlaciona con API: `task logs:api`.
4. Filtra errores de proxy/autenticacion: `task logs:errors MIN=30`.

## Checklist de triage (<10 minutos)

1. `task health`
2. `task logs:errors MIN=15`
3. `task logs:<servicio_afectado>`
4. `task logs:since MIN=30`

Con estos cuatro pasos deberias tener una hipotesis de causa raiz inicial.
