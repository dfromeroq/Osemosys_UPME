# Certificación `escenario_regional.xlsx` — 2026-07-17

## Entrada y entorno

- Archivo: `C:/Users/Usuario/Downloads/escenario_regional.xlsx`
- SHA-256: `e493eef1ff077b9dacf97a0534e8302710a318635c0d1e5a4535c2ca2fc91c42`
- Hoja: `Parameters` (28.313 filas × 44 columnas)
- HiGHS: `1.15.1`
- Docker Desktop efectivo: 16,7 GB RAM, 12 CPU
- Modelo final: 2.199.291 restricciones, 1.994.100 variables y 8.383.744 no ceros

## Diagnóstico

1. Simplex dual/default entra en una trayectoria numéricamente inestable. A los 900 s
   conservaba alrededor de 15.000 violaciones primales y había alcanzado sumas de
   infactibilidades de hasta `1e15`.
2. `user_bound_scale=-7` no lo corrige.
3. Convertir a cero los 1.057 `ResidualCapacity` con `abs(VALUE)<1e-12` tampoco cambia
   la trayectoria; los valores diminutos no son la causa principal.
4. IPM con crossover converge y la limpieza simplex entrega una base óptima.
5. El conversor Excel directo usaba `dropna(axis=1)` (`how="any"`): una celda vacía
   eliminaba el año completo para un parámetro. En este archivo omitía 2055 en
   `ResidualCapacity` y `TotalAnnualMaxCapacityInvestment`, generando 80 restricciones
   menos que la ruta PostgreSQL.
6. Excel y PostgreSQL también podían diferir en 1 ULP. La normalización final a 12
   cifras significativas (muy inferior a la tolerancia `1e-7`) produce CSV idénticos.
7. Un `maxTimeLimit` sin solución factible se trataba como éxito y materializaba valores
   absurdos. Ahora debe producir `FAILED`, sin fallback duplicado ni persistencia parcial.

## Experimentos regionales

| Experimento | Estado | Solver s | Objetivo | Unmet | Cobertura | Pico RSS |
|---|---:|---:|---:|---:|---:|---:|
| Simplex default, límite 900 s | maxTimeLimit inválido | 894,6 | 41.642.451,95 | 1,7429e13 | 0 | 7.988 MB |
| Simplex + `user_bound_scale=-7` | maxTimeLimit inválido | 900,0 | 13.740.664,89 | 1,2897e10 | 0 | 7.934 MB |
| Simplex + residuales `<1e-12` a cero | maxTimeLimit inválido | 599,9 | 73.100,83 | 3,9796e10 | 0 | 7.921 MB |
| IPM+crossover, entrada previa | optimal | 173,4 | 1.888.233,1073 | 0 | 1 | 9.412 MB |
| CSV final canónico | optimal | 179,8 | 1.887.956,7155588912 | 0 | 1 | 9.373 MB |
| Excel→BD final canónico (job 26) | optimal | 178,6 | 1.887.956,7155588912 | 0 | 1 | 9.417 MB |

Validación independiente de restricciones sobre IPM:

- restricciones evaluadas: 2.199.211;
- errores de evaluación: 0;
- violaciones `>1e-7`: 0;
- violación máxima: `6,808186080176082e-8`;
- variable bounds `>1e-7`: 0;
- unmet: 0;
- cobertura: 1,0.

## Paridad regional Excel ↔ CSV

- 32/32 CSV finales: idénticos byte a byte.
- Comparación de solución: `PASS`, sin warnings.
- Objetivo, demanda, dispatch, unmet y agregaciones: diferencia exacta 0.

Artefacto: `/app/tmp/experiments/regional_current_quantized_parity.json`.

## Regresión nacional

Escenarios cargados:

- escenario 6: `VALIDACIÓN Nacional · Excel` (job 27);
- escenario 11: `VALIDACIÓN Nacional · CSV` (job 28).

Ambos conservaron HiGHS default/simplex y produjeron exactamente:

- objetivo: `1.117.470,2926385326`;
- demanda: `32.969,64562260821`;
- dispatch: `1.302.333,5074714068`;
- unmet: 0;
- cobertura: 1,0.

Comparación: `PASS`, sin warnings y diferencias exactas 0.

## Regresión regional histórica

Escenario 8 con el nuevo default regional:

- estado: optimal;
- solver: 132,1 s;
- objetivo: `1.828.936,3164554725`;
- unmet: 0;
- cobertura: 1,0;
- pico RSS: 9.347 MB.

La diferencia relativa frente al objetivo certificado previo es aproximadamente `3,7e-11`
y corresponde a la cuantización canónica de inputs.
