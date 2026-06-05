"""Diagnóstico de restricciones innecesarias o redundantes en el modelo OSeMOSYS.

Desactivado por defecto (OSEMOSYS_CONSTRAINT_DIAGNOSTICS=0 en .env).
Activar solo para debug local vía variable de entorno:
    OSEMOSYS_CONSTRAINT_DIAGNOSTICS=1

El reporte se emite por el logger estándar del módulo.
"""
import logging

logger = logging.getLogger(__name__)


def _pval(v):
    """Extrae valor Python de un Param Pyomo (mutable o no-mutable)."""
    return float(v) if not isinstance(v, (int, float)) else v


def diagnose_model_constraints(instance) -> dict:
    """Analiza una ConcreteModel instanciada y reporta restricciones redundantes/triviales.

    Retorna dict con métricas para uso programático; también logea resumen legible.
    """
    m = instance

    regions = list(m.REGION)
    years = list(m.YEAR)
    fuels = list(m.FUEL)
    techs = list(m.TECHNOLOGY)
    modes = list(m.MODE_OF_OPERATION)
    timeslices = list(m.TIMESLICE)

    # ------------------------------------------------------------------ #
    # 1. EnergyBalanceEachTS5 — términos y restricciones triviales
    # ------------------------------------------------------------------ #
    eachts5_total = len(regions) * len(timeslices) * len(fuels) * len(years)
    eachts5_skipped = 0
    eachts5_zero_oar_terms = 0
    eachts5_total_oar_terms = 0

    for r in regions:
        for y in years:
            for f in fuels:
                has_oar = False
                has_iar = False
                for t in techs:
                    for mo in modes:
                        eachts5_total_oar_terms += 1
                        if _pval(m.OutputActivityRatio[r, t, f, mo, y]) == 0:
                            eachts5_zero_oar_terms += 1
                        else:
                            has_oar = True
                        if _pval(m.InputActivityRatio[r, t, f, mo, y]) != 0:
                            has_iar = True

                if not has_oar:
                    for l in timeslices:
                        demand_val = _pval(m.Demand[r, l, f, y])
                        if demand_val == 0 and not has_iar:
                            eachts5_skipped += 1

    # ------------------------------------------------------------------ #
    # 2. EnergyBalanceEachYear4 — restricciones triviales
    # ------------------------------------------------------------------ #
    eachyear4_total = len(regions) * len(fuels) * len(years)
    eachyear4_skipped = 0

    for r in regions:
        for f in fuels:
            for y in years:
                has_oar = any(
                    _pval(m.OutputActivityRatio[r, t, f, mo, y]) != 0
                    for t in techs for mo in modes
                )
                has_iar = any(
                    _pval(m.InputActivityRatio[r, t, f, mo, y]) != 0
                    for t in techs for mo in modes
                )
                acc_demand = _pval(m.AccumulatedAnnualDemand[r, f, y])
                if not has_oar and acc_demand == 0 and not has_iar:
                    eachyear4_skipped += 1

    # ------------------------------------------------------------------ #
    # 3. AnnualEmissionProductionByMode — restricciones con ratio == 0
    # ------------------------------------------------------------------ #
    emissions = list(m.EMISSION)
    emission_total = len(regions) * len(techs) * len(emissions) * len(modes) * len(years)
    emission_zero_ratio = 0

    for r in regions:
        for t in techs:
            for e in emissions:
                for mo in modes:
                    for y in years:
                        if _pval(m.EmissionActivityRatio[r, t, e, mo, y]) == 0:
                            emission_zero_ratio += 1

    # ------------------------------------------------------------------ #
    # 4. PlannedMaintenance — potencialmente redundante si AF == 1
    # ------------------------------------------------------------------ #
    planned_total = len(regions) * len(techs) * len(years)
    planned_redundant = 0

    for r in regions:
        for t in techs:
            for y in years:
                af = _pval(m.AvailabilityFactor[r, t, y])
                if af == 1.0:
                    cf_vals = [_pval(m.CapacityFactor[r, t, l, y]) for l in timeslices]
                    if len(set(cf_vals)) <= 1:
                        planned_redundant += 1

    eachyear4_implied = eachyear4_total - eachyear4_skipped

    def pct(num, den):
        return f"{num / den * 100:.1f}%" if den else "N/A"

    logger.info("=" * 60)
    logger.info("CONSTRAINT DIAGNOSTICS — OSeMOSYS model")
    logger.info("=" * 60)
    logger.info(
        "EnergyBalanceEachTS5:\n"
        f"  Total instancias posibles : {eachts5_total:>10,}\n"
        f"  Skipped (trivial 0>=0)    : {eachts5_skipped:>10,}  ({pct(eachts5_skipped, eachts5_total)})\n"
        f"  Términos OAR==0 filtrados : {eachts5_zero_oar_terms:>10,}  ({pct(eachts5_zero_oar_terms, eachts5_total_oar_terms)} del total de términos)"
    )
    logger.info(
        "EnergyBalanceEachYear4:\n"
        f"  Total instancias posibles : {eachyear4_total:>10,}\n"
        f"  Skipped (trivial 0>=0)    : {eachyear4_skipped:>10,}  ({pct(eachyear4_skipped, eachyear4_total)})\n"
        f"  Activas (potenc. redundan): {eachyear4_implied:>10,}  (redundantes por diseño si EachTS5 binding)"
    )
    logger.info(
        "AnnualEmissionProductionByMode:\n"
        f"  Total instancias          : {emission_total:>10,}\n"
        f"  Ratio == 0 (fuerza var=0) : {emission_zero_ratio:>10,}  ({pct(emission_zero_ratio, emission_total)})\n"
        f"  → Oportunidad: usar Constraint.Skip en vez de '== 0'"
    )
    logger.info(
        "PlannedMaintenance:\n"
        f"  Total instancias          : {planned_total:>10,}\n"
        f"  Potenc. redundantes (AF=1,CF uniforme): {planned_redundant:>6,}  ({pct(planned_redundant, planned_total)})"
    )
    logger.info("=" * 60)

    return {
        "EnergyBalanceEachTS5": {
            "total": eachts5_total,
            "skipped_trivial": eachts5_skipped,
            "zero_oar_terms": eachts5_zero_oar_terms,
            "total_oar_terms": eachts5_total_oar_terms,
        },
        "EnergyBalanceEachYear4": {
            "total": eachyear4_total,
            "skipped_trivial": eachyear4_skipped,
            "active": eachyear4_implied,
        },
        "AnnualEmissionProductionByMode": {
            "total": emission_total,
            "zero_ratio": emission_zero_ratio,
        },
        "PlannedMaintenance": {
            "total": planned_total,
            "potentially_redundant": planned_redundant,
        },
    }
