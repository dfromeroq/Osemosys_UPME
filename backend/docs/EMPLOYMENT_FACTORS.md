# Employment Factors Post-Processing

This backend derives direct employment results after an OSeMOSYS simulation has
finished. The employment calculation is ex-post: it does not affect the
optimization objective, constraints, or solver feasibility.

## Source

Employment factors are loaded from:

```text
https://github.com/DEA-GE/colombia-employment-factors
```

The backend uses the package function `get_model_employment_factors()`, which
returns model-ready yearly factors for 2024-2055.

## Technology Mapping

The runtime mapping lives in:

```text
backend/app/services/employment_factors_mapping.yaml
```

Each OSeMOSYS technology maps to one or more employment-factor technologies.
The `multiplier` field is the MW of employment-factor technology represented by
one MW of model technology.

Example:

```yaml
PWRSOLUGE_BAT:
  components:
    - employment_technology: Utility-scale solar PV
      multiplier: 1.0
    - employment_technology: Battery storage (grid)
      multiplier: 0.6
```

For `PWRSOLUGE_BAT`, one MW of model capacity is treated as one MW of
utility-scale solar PV plus 0.6 MW of grid battery storage. The component
employment values are summed into one output row for the model technology.

## Capacity Variables

Only model-period installations from 2025 onwards are counted.

`NewCapacity` is used for construction and manufacturing:

```text
EmploymentConstructionManufacturingDirect =
    NewCapacity_MW * Construction&Manufacturing direct factor
```

`AccumulatedNewCapacity` is used for O&M:

```text
EmploymentOMDirect =
    AccumulatedNewCapacity_MW * O&M direct factor
```

`TotalCapacityAnnual` is intentionally not used. It includes residual capacity
from the last historical year, 2024. Using it would estimate O&M employment for
the whole installed system, while this workflow estimates employment generated
by capacity additions from the optimization period.

## Unit Conversion

OSeMOSYS capacity outputs in this repository are treated as `PJ/year`. The
employment factors use MW. Before applying factors, capacity is converted with:

```text
1 GW = 31.5576 PJ/year
MW = PJ/year * 1000 / 31.5576
```

## FTE Interpretation

The current pipeline keeps only direct employment:

```text
Job_Type == Direct
```

Construction and manufacturing factors use `FTE-year/MW`. The result is total
FTE-years associated with capacity installed in the model year.

O&M factors use `FTE/MW`. The result is annual FTE sustained in that year by
the cumulative new capacity still present in the system.

## Persisted Variables

Derived rows are stored in `osemosys.osemosys_output_param_value` with the same
simulation job id as the rest of the model outputs.

The derived variable names are:

```text
EmploymentConstructionManufacturingDirect
EmploymentOMDirect
```

Rows include region, technology, year, and value. Additional calculation
metadata is stored in `index_json`, including:

- source OSeMOSYS capacity variable;
- factor type;
- job type;
- original capacity in `PJ/year`;
- converted capacity in MW;
- component factor technologies, sources, units, and intermediate employment
  values.
