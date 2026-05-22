/**
 * Transformaciones de datos exógenos para gráficas de comparación.
 *
 * Tres modos:
 *   1. Facet / by-year / by-year-alt → inyecta "Refinerías" como nueva categoría (barra apilada)
 *   2. Line-total → suma datos exógenos a la línea de cada escenario
 */
import type {
  ChartDataResponse,
  CompareChartFacetResponse,
  CompareChartResponse,
  ExogenousDataConfig,
} from "@/types/domain";

/**
 * Inyecta datos exógenos como nueva serie "Refinerías" en cada facet.
 */
export function injectExogenousDataFacet(
  data: CompareChartFacetResponse,
  exogenous: ExogenousDataConfig,
): CompareChartFacetResponse {
  if (!exogenous.active || exogenous.scenarios.length === 0) return data;
  return {
    ...data,
    facets: data.facets.map((facet) => {
      const exoEntry = exogenous.scenarios.find(
        (s) => s.jobId === facet.job_id,
      );
      if (!exoEntry || exoEntry.data.length === 0) return facet;
      const exoMap = new Map(exoEntry.data);
      const refineriesData = facet.categories.map((cat) => {
        const year = Number(cat);
        if (!Number.isFinite(year)) return null;
        const val = exoMap.get(year);
        return val != null ? val : null;
      });
      if (refineriesData.every((v) => v == null)) return facet;
      return {
        ...facet,
        series: [
          ...facet.series,
          {
            name: exogenous.categoryLabel,
            data: refineriesData,
            color: exogenous.color,
            stack: "default",
          },
        ],
      };
    }),
  };
}

/**
 * Inyecta datos exógenos como nueva serie "Refinerías" en cada subplot.
 *
 * Soporta tanto by-year (isAltMode=false) como by-year-alt (isAltMode=true).
 */
export function injectExogenousDataByYear(
  data: CompareChartResponse,
  exogenous: ExogenousDataConfig,
  jobIds: number[],
): CompareChartResponse {
  if (!exogenous.active || exogenous.scenarios.length === 0) return data;

  const isAltMode = data.subplots.some((sp) => sp.scenario_name);
  const exoByJobId = new Map(
    exogenous.scenarios.map((s) => [s.jobId, new Map(s.data)]),
  );

  return {
    ...data,
    subplots: data.subplots.map((subplot) => {
      let refineriesData: (number | null)[];

      if (isAltMode) {
        const jid = subplot.year;
        const exoMap = exoByJobId.get(jid);
        if (!exoMap) return subplot;
        refineriesData = subplot.categories.map((cat) => {
          const year = Number(cat);
          if (!Number.isFinite(year)) return null;
          const val = exoMap.get(year);
          return val != null ? val : null;
        });
      } else {
        refineriesData = subplot.categories.map((_name, idx) => {
          const jid: number | undefined = jobIds[idx];
          const exoMap = jid != null ? exoByJobId.get(jid) : undefined;
          if (!exoMap) return null;
          const val = exoMap.get(subplot.year);
          return val != null ? val : null;
        });
      }

      if (refineriesData.every((v) => v == null)) return subplot;
      return {
        ...subplot,
        series: [
          ...subplot.series,
          {
            name: exogenous.categoryLabel,
            data: refineriesData,
            color: exogenous.color,
            stack: "default",
          },
        ],
      };
    }),
  };
}

/**
 * Inyecta datos exógenos SUMMADOS a la línea de cada escenario.
 * NO crea una categoría separada.
 */
export function injectExogenousDataLineTotal(
  data: ChartDataResponse,
  exogenous: ExogenousDataConfig,
  jobIds: number[],
): ChartDataResponse {
  if (!exogenous.active || exogenous.scenarios.length === 0) return data;

  const exoByJobId = new Map(
    exogenous.scenarios.map((s) => [s.jobId, new Map(s.data)]),
  );

  return {
    ...data,
    series: data.series.map((s, idx) => {
      const jid: number | undefined = jobIds[idx];
      const exoMap = jid != null ? exoByJobId.get(jid) : undefined;
      if (!exoMap) return s;
      return {
        ...s,
        data: s.data.map((val, catIdx) => {
          if (val == null) return val;
          const year = Number(data.categories[catIdx]);
          if (!Number.isFinite(year)) return val;
          const exoVal = exoMap.get(year);
          return exoVal != null ? val + exoVal : val;
        }),
      };
    }),
  };
}
