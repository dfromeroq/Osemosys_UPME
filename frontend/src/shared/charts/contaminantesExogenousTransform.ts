/**
 * Transformaciones de datos exógenos para Emisiones Contaminantes Criterio.
 *
 * A diferencia de las Refinerías (que inyectan una nueva categoría/serie),
 * aquí los valores exógenos se SUMAN a las series existentes (BC, CO, COVDM,
 * NOx, PM10, PM2_5, SOx).
 *
 * Matching: se quita el prefijo "EMI" del nombre de la serie y se busca
 * la clave correspondiente en los datos exógenos.
 *   Ej: serie "EMIBC" → clave "BC" → lookup en exogenous.data["BC"]
 */
import type {
  ChartDataResponse,
  CompareChartFacetResponse,
  CompareChartResponse,
} from "@/types/domain";
import type { ContaminantesExogenousConfig } from "./contaminantesExogenousTypes";

function stripEmiPrefix(name: string): string {
  return name.startsWith("EMI") ? name.slice(3) : name;
}

/** Construye un Map<jobId, Map<año, Map<contaminante, valor>>> */
function buildExoByJob(
  exogenous: ContaminantesExogenousConfig,
): Map<number, Map<number, Map<string, number>>> {
  const result = new Map<number, Map<number, Map<string, number>>>();
  for (const sc of exogenous.scenarios) {
    const yearMap = new Map<number, Map<string, number>>();
    for (const [pollutantKey, pairs] of Object.entries(sc.data)) {
      for (const [year, val] of pairs) {
        let polMap = yearMap.get(year);
        if (!polMap) {
          polMap = new Map();
          yearMap.set(year, polMap);
        }
        polMap.set(pollutantKey, val);
      }
    }
    result.set(sc.jobId, yearMap);
  }
  return result;
}

function sumExoToSeriesValue(
  seriesName: string,
  year: number,
  exoByJob: Map<number, Map<number, Map<string, number>>> | null,
  jobId: number | undefined,
  currentVal: number | null,
): number | null {
  if (currentVal == null || jobId == null || !exoByJob) return currentVal;
  const yearMap = exoByJob.get(jobId);
  if (!yearMap) return currentVal;
  const polMap = yearMap.get(year);
  if (!polMap) return currentVal;
  const key = stripEmiPrefix(seriesName);
  const exoVal = polMap.get(key);
  return exoVal != null ? currentVal + exoVal : currentVal;
}

// ── Facet ────────────────────────────────────────────────────────────────

export function injectContaminantesExogenousFacet(
  data: CompareChartFacetResponse,
  exogenous: ContaminantesExogenousConfig,
): CompareChartFacetResponse {
  if (!exogenous.active || exogenous.scenarios.length === 0) return data;
  const exoByJob = buildExoByJob(exogenous);
  return {
    ...data,
    facets: data.facets.map((facet) => {
      let changed = false;
      const newSeries = facet.series.map((s) => {
        const newData = s.data.map((val, catIdx) => {
          const year = Number(facet.categories[catIdx]);
          if (!Number.isFinite(year)) return val;
          const summed = sumExoToSeriesValue(s.name, year, exoByJob, facet.job_id, val);
          if (summed !== val) changed = true;
          return summed;
        });
        return { ...s, data: newData };
      });
      if (!changed) return facet;
      return { ...facet, series: newSeries };
    }),
  };
}

// ── By-year / by-year-alt ────────────────────────────────────────────────

export function injectContaminantesExogenousByYear(
  data: CompareChartResponse,
  exogenous: ContaminantesExogenousConfig,
  jobIds: number[],
): CompareChartResponse {
  if (!exogenous.active || exogenous.scenarios.length === 0) return data;
  const exoByJob = buildExoByJob(exogenous);
  const isAltMode = data.subplots.some((sp) => sp.scenario_name);

  return {
    ...data,
    subplots: data.subplots.map((subplot) => {
      let changed = false;
      const newSeries = subplot.series.map((s) => {
        const newData = s.data.map((val, catIdx) => {
          let jobId: number | undefined;
          const year = isAltMode
            ? Number(subplot.categories[catIdx])
            : subplot.year;
          if (!Number.isFinite(year)) return val;
          if (isAltMode) {
            jobId = subplot.year;
          } else {
            jobId = jobIds[catIdx];
          }
          const summed = sumExoToSeriesValue(s.name, year, exoByJob, jobId, val);
          if (summed !== val) changed = true;
          return summed;
        });
        return { ...s, data: newData };
      });
      if (!changed) return subplot;
      return { ...subplot, series: newSeries };
    }),
  };
}

// ── Line-total ───────────────────────────────────────────────────────────

export function injectContaminantesExogenousLineTotal(
  data: ChartDataResponse,
  exogenous: ContaminantesExogenousConfig,
  jobIds: number[],
): ChartDataResponse {
  if (!exogenous.active || exogenous.scenarios.length === 0) return data;
  const exoByJob = buildExoByJob(exogenous);
  return {
    ...data,
    series: data.series.map((s, idx) => {
      const jobId = jobIds[idx];
      if (jobId == null) return s;
      const yearMap = exoByJob.get(jobId);
      if (!yearMap) return s;
      let changed = false;
      const newData = s.data.map((val, catIdx) => {
        if (val == null) return val;
        const year = Number(data.categories[catIdx]);
        if (!Number.isFinite(year)) return val;
        const polMap = yearMap.get(year);
        if (!polMap) return val;
        // Sum ALL pollutant values for this year+jobs into the line-total series
        let totalExo = 0;
        for (const exoVal of polMap.values()) {
          totalExo += exoVal;
        }
        if (totalExo === 0) return val;
        changed = true;
        return val + totalExo;
      });
      if (!changed) return s;
      return { ...s, data: newData };
    }),
  };
}
