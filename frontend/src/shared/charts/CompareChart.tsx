import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Highcharts from './highchartsSetup';
import {
  EXPORTING_CONTEXT_BUTTON_DARK,
  INDIVIDUAL_CHART_EXPORT_MENU_ITEMS,
  createCleanExportMenuItem,
  onHighchartsExportError,
} from './chartExportingShared';
import { buildStackedSinglePointTooltipOptions } from './chartTooltips';
import { formatAxis3Sig } from './numberFormat';
import {
  createLegendDblclickState,
  dispatchLegendClick,
} from './chartLegendInteractions';
import HighchartsReact from 'highcharts-react-official';
import { simulationApi } from '@/features/simulation/api/simulationApi';
import { CompareExportDropdown } from '@/shared/charts/CompareExportDropdown';
import { downloadBlob } from '@/shared/utils/downloadBlob';
import type { CompareChartResponse } from '../../types/domain';
import type { ChartSelection } from './ChartSelector';

interface CompareChartProps {
  data: CompareChartResponse;
  barOrientation?: 'vertical' | 'horizontal';
  /** Tipo de apilamiento: column (barras) o area (áreas apiladas). Por defecto column. */
  stackType?: 'column' | 'area';
  /** Override del eje Y para todos los subplots. ``null``/undefined = auto. */
  yAxisMin?: number | null;
  yAxisMax?: number | null;
  /** Force all subplots to share the same Y-axis maximum */
  sharedYAxis?: boolean;
  /** Config para exportación PNG servidor (modo comparación por años). */
  serverCompareExport?: {
    jobIds: (string | number)[];
    selection: ChartSelection;
    yearsToPlot: number[];
    isAltMode?: boolean;
    scenarioAliases?: Record<number, string>;
  };
}

export const CompareChart: React.FC<CompareChartProps> = ({
  data,
  barOrientation = 'vertical',
  stackType = 'column',
  yAxisMin,
  yAxisMax,
  sharedYAxis = false,
  serverCompareExport,
}) => {
  const isArea = stackType === 'area';
  const inverted = barOrientation === 'horizontal' && !isArea;
  const legendDblclickStateRef = useRef(createLegendDblclickState());
  const [exportBusy, setExportBusy] = useState(false);
  const [exportXlsxBusy, setExportXlsxBusy] = useState(false);

  const allSeriesNames = useMemo(() => {
    const names = new Set<string>();
    data.subplots.forEach((sp) => sp.series.forEach((s) => names.add(s.name)));
    return Array.from(names);
  }, [data.subplots]);

  const isByYearAltMode =
    data.subplots.length > 0 && !!data.subplots[0]?.scenario_name;

  // En modo alternativo (por escenarios), siempre forzar eje Y compartido
  // para garantizar que todos los subplots usen la misma escala.
  const effectiveSharedYAxis = sharedYAxis || isByYearAltMode;

  const globalMaxRaw = useMemo(() => {
    if (!effectiveSharedYAxis) return 0;
    let globalMax = 0;
    data.subplots.forEach((subplot) => {
      const categoryCount = subplot.categories.length;
      for (let i = 0; i < categoryCount; i += 1) {
        const stackTotal = subplot.series.reduce((acc, serie) => {
          const point = serie.data[i];
          return acc + (typeof point === 'number' ? point : 0);
        }, 0);
        if (stackTotal > globalMax) globalMax = stackTotal;
      }
    });
    return globalMax;
  }, [data.subplots, effectiveSharedYAxis]);

  const sharedTickInterval = useMemo(() => {
    if (!effectiveSharedYAxis || globalMaxRaw <= 0) return undefined;
    const targetTicks = 5;
    const roughInterval = globalMaxRaw / targetTicks;
    if (roughInterval <= 0) return undefined;
    const magnitude = Math.pow(10, Math.floor(Math.log10(roughInterval)));
    const normalized = roughInterval / magnitude;
    if (normalized <= 1.5) return magnitude;
    if (normalized <= 3.5) return 2 * magnitude;
    if (normalized <= 7.5) return 5 * magnitude;
    return 10 * magnitude;
  }, [globalMaxRaw, effectiveSharedYAxis]);

  const sharedYAxisMax = useMemo(() => {
    if (!effectiveSharedYAxis || globalMaxRaw <= 0) return 0;
    if (sharedTickInterval === undefined) return globalMaxRaw;
    return Math.ceil(globalMaxRaw / sharedTickInterval) * sharedTickInterval;
  }, [globalMaxRaw, sharedTickInterval, effectiveSharedYAxis]);
  const [hiddenNames, setHiddenNames] = useState<Set<string>>(() => new Set());
  const dataSignature = allSeriesNames.join('|');
  useEffect(() => {
    setHiddenNames(new Set());
    legendDblclickStateRef.current.isolatedName = null;
  }, [dataSignature]);

  const handleToggle = (name: string) => {
    setHiddenNames((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };
  const handleIsolate = (name: string) => {
    setHiddenNames(new Set(allSeriesNames.filter((n) => n !== name)));
  };
  const handleRestoreAll = () => setHiddenNames(new Set());

  const handleExportComparePngServer = useCallback(async () => {
    if (!serverCompareExport || serverCompareExport.jobIds.length < 2) return;
    setExportBusy(true);
    try {
      const sel = serverCompareExport.selection;
      const payload: Parameters<typeof simulationApi.exportCompareByYear>[0] = {
        job_ids: serverCompareExport.jobIds.join(','),
        tipo: sel.tipo,
        un: sel.un,
        years_to_plot: serverCompareExport.yearsToPlot.join(','),
      };
      if (serverCompareExport.isAltMode) payload.group_by = 'scenario';
      if (sel.sub_filtro) payload.sub_filtro = sel.sub_filtro;
      if (sel.loc) payload.loc = sel.loc;
      if (sel.agrupar_por) payload.agrupacion = sel.agrupar_por;
      if (sel.viewMode === 'porcentaje') payload.es_porcentaje = 'true';
      if (sel.viewMode && sel.viewMode !== 'column') payload.view_mode = sel.viewMode;
      if (sel.region && sel.agrupar_por !== 'REGION') {
        payload.region = sel.region;
      }
      if (serverCompareExport.scenarioAliases && Object.keys(serverCompareExport.scenarioAliases).some(k => serverCompareExport.scenarioAliases![Number(k)]?.trim())) {
        payload.job_display_overrides = JSON.stringify(serverCompareExport.scenarioAliases);
      }
      if (hiddenNames.size > 0) {
        payload.hidden_series = Array.from(hiddenNames).join(',');
      }
      const { blob, filename } = await simulationApi.exportCompareByYear(payload, 'png');
      downloadBlob(blob, filename);
    } catch (err) {
      console.error(err);
      let msg = 'No se pudo generar el PNG en el servidor.';
      if (err && typeof err === 'object' && 'response' in err) {
        const resp = (err as any).response;
        if (resp?.data instanceof Blob) {
          try {
            const text = await resp.data.text();
            const parsed = JSON.parse(text);
            if (parsed.detail) msg = parsed.detail;
          } catch {}
        } else if (resp?.data?.detail) {
          msg = resp.data.detail;
        }
      }
      window.alert(msg);
    } finally {
      setExportBusy(false);
    }
  }, [serverCompareExport, hiddenNames]);

  const handleExportCompareXlsxServer = useCallback(async () => {
    if (!serverCompareExport || serverCompareExport.jobIds.length < 2) return;
    setExportXlsxBusy(true);
    try {
      const sel = serverCompareExport.selection;
      const payload: Parameters<typeof simulationApi.exportCompareXlsx>[0] = {
        job_ids: serverCompareExport.jobIds.join(','),
        tipo: sel.tipo,
        un: sel.un,
        compare_mode: serverCompareExport.isAltMode ? 'by-year-alt' : 'by-year',
        years_to_plot: serverCompareExport.yearsToPlot.join(','),
      };
      if (sel.sub_filtro) payload.sub_filtro = sel.sub_filtro;
      if (sel.loc) payload.loc = sel.loc;
      if (sel.agrupar_por) payload.agrupar_por = sel.agrupar_por;
      if (sel.viewMode === 'porcentaje') payload.es_porcentaje = 'true';
      if (sel.viewMode && sel.viewMode !== 'column' && sel.viewMode !== 'porcentaje') {
        payload.view_mode = sel.viewMode;
      }
      if (sel.region && sel.agrupar_por !== 'REGION') {
        payload.region = sel.region;
      }
      if (typeof yAxisMin === 'number') payload.y_axis_min = yAxisMin;
      if (typeof yAxisMax === 'number') payload.y_axis_max = yAxisMax;
      if (sel.customSeriesOrder && sel.customSeriesOrder.length > 0) {
        payload.series_order = sel.customSeriesOrder.join(',');
      }
      if (serverCompareExport.scenarioAliases && Object.keys(serverCompareExport.scenarioAliases).some(k => serverCompareExport.scenarioAliases![Number(k)]?.trim())) {
        payload.job_display_overrides = JSON.stringify(serverCompareExport.scenarioAliases);
      }
      if (hiddenNames.size > 0) {
        payload.hidden_series = Array.from(hiddenNames).join(',');
      }
      const { blob, filename } = await simulationApi.exportCompareXlsx(payload);
      downloadBlob(blob, filename);
    } catch (err) {
      console.error(err);
      let msg = 'No se pudo generar el XLSX en el servidor.';
      if (err && typeof err === 'object' && 'response' in err) {
        const resp = (err as { response?: { data?: Blob | { detail?: string } } }).response;
        if (resp?.data instanceof Blob) {
          try {
            const text = await resp.data.text();
            const parsed = JSON.parse(text) as { detail?: string };
            if (parsed.detail) msg = parsed.detail;
          } catch { /* ignore */ }
        } else if (resp?.data && typeof resp.data === 'object' && 'detail' in resp.data) {
          msg = String(resp.data.detail);
        }
      }
      window.alert(msg);
    } finally {
      setExportXlsxBusy(false);
    }
  }, [serverCompareExport, hiddenNames, yAxisMin, yAxisMax]);

  const compareExportOptions = useMemo(() => {
    if (!serverCompareExport || serverCompareExport.jobIds.length < 2) return [];
    return [
      {
        id: 'png',
        label: 'PNG (servidor)',
        busyLabel: 'Generando PNG…',
        busy: exportBusy,
        onClick: () => handleExportComparePngServer(),
      },
      {
        id: 'xlsx',
        label: 'XLSX',
        busyLabel: 'Generando XLSX…',
        busy: exportXlsxBusy,
        onClick: () => handleExportCompareXlsxServer(),
      },
    ];
  }, [serverCompareExport, exportBusy, exportXlsxBusy]);

  const options = useMemo<Highcharts.Options>(() => {
    const legendItemClick = function (this: Highcharts.Series): boolean {
      dispatchLegendClick(legendDblclickStateRef.current, this.name, {
        onToggle: handleToggle,
        onIsolate: handleIsolate,
        onRestoreAll: handleRestoreAll,
      });
      return false;
    };
    const numSubplots = data.subplots.length;

    const xAxis: Highcharts.XAxisOptions[] = [];
    const yAxis: Highcharts.YAxisOptions[] = [];
    const series: Highcharts.SeriesOptionsType[] = [];

    const GAP_PCT = 2;
    const totalGap = (numSubplots - 1) * GAP_PCT;
    const subplotWidth = (100 - totalGap) / numSubplots;
    const legendNamesSeen = new Set<string>();

    data.subplots.forEach((subplot, idx) => {
      const leftStr = `${idx * (subplotWidth + GAP_PCT)}%`;
      const widthStr = `${subplotWidth}%`;

      xAxis.push({
        id: `x-${idx}`,
        categories: subplot.categories,
        title: {
          text: subplot.scenario_name || subplot.year.toString(),
          style: { color: '#94a3b8', fontWeight: 'bold', fontSize: '14pt' },
        },
        width: widthStr,
        left: leftStr,
        // Mismo top/height que el yAxis para que el eje X quede alineado y
        // deje espacio a la leyenda en la parte inferior.
        top: '0%',
        height: '86%',
        offset: 0,
        labels: { style: { color: '#94a3b8', fontSize: '11pt' } },
        lineColor: '#334155',
        tickColor: '#334155',
        ...{ tickWidth: 2, tickLength: 10 },
      });

      yAxis.push({
        id: `y-${idx}`,
        title: {
          text: idx === 0 ? data.yAxisLabel : null,
          style: { color: '#94a3b8', fontSize: '14pt' },
        },
        width: widthStr,
        left: leftStr,
        // Reservamos el 14% inferior para la leyenda (en multi-axis los yAxis no
        // ceden espacio automáticamente a la leyenda cuando se fija width/left).
        top: '0%',
        height: '86%',
        min: typeof yAxisMin === 'number' ? yAxisMin : 0,
        // Use shared maximum if enabled, otherwise use individual yAxisMax
        max: typeof yAxisMax === 'number'
          ? yAxisMax
          : (effectiveSharedYAxis && sharedYAxisMax > 0 ? sharedYAxisMax : null),
        ...(effectiveSharedYAxis && sharedYAxisMax > 0 && sharedTickInterval !== undefined
          ? { tickInterval: sharedTickInterval }
          : {}),
        ...(effectiveSharedYAxis ? { endOnTick: false } : {}),
        // Grid lines always visible on all charts for visual reference
        gridLineColor: '#334155',
        gridLineWidth: 1,
        // Only show ticks on first subplot when Y-axis is shared
        tickWidth: (!effectiveSharedYAxis || idx === 0) ? 1 : 0,
        tickLength: (!effectiveSharedYAxis || idx === 0) ? 6 : 0,
        tickColor: (!effectiveSharedYAxis || idx === 0) ? '#64748b' : 'transparent',
        // Y-axis line always visible (provides chart boundaries between scenarios)
        // lineWidth: 1,
        lineWidth: idx === 0 ? 1 : 0,
        lineColor: '#64748b',
        labels: {
          // Only show labels on first subplot when Y-axis is shared
          enabled: !effectiveSharedYAxis || idx === 0,
          style: { color: '#94a3b8', fontSize: '11pt' },
          formatter: function (this: Highcharts.AxisLabelsFormatterContextObject) {
            return formatAxis3Sig(this.value as number);
          },
        },
        stackLabels: {
          enabled: true,
          style: {
            fontWeight: 'bold',
            color: '#94a3b8',
            textOutline: 'none',
            fontSize: '11pt',
          },
          // eslint-disable-next-line react-hooks/unsupported-syntax -- API de Highcharts (`this`)
          formatter: function (this: Highcharts.StackItemObject) {
            return Highcharts.numberFormat(this.total, 2, '.', ',');
          },
        },
      });

      subplot.series.forEach((s) => {
        const isNew = !legendNamesSeen.has(s.name);
        if (isNew) legendNamesSeen.add(s.name);
        const base: Highcharts.SeriesOptionsType = {
          type: isArea ? 'area' : 'column',
          name: s.name,
          data: s.data,
          color: s.color,
          xAxis: `x-${idx}`,
          yAxis: `y-${idx}`,
          stacking: 'normal' as const,
          showInLegend: isNew,
          visible: !hiddenNames.has(s.name),
          custom: {
            subplotYear: subplot.year,
            scenarioName: subplot.scenario_name || null,
          },
        } as Highcharts.SeriesOptionsType;
        if (isArea) {
          Object.assign(base, {
            fillOpacity: 0.85,
            lineWidth: 0.5,
            marker: { enabled: false },
          });
        } else {
          Object.assign(base, { borderWidth: 0 });
        }
        series.push(base);
      });
    });

    const exportChartYAxisOptions = (() => {
      const GAP_PCT = 2;
      const totalGap = (numSubplots - 1) * GAP_PCT;
      const subplotWidth = (100 - totalGap) / numSubplots;
      return data.subplots.map((sp, idx) => {
        const leftStr = `${idx * (subplotWidth + GAP_PCT)}%`;
        const widthStr = `${subplotWidth}%`;
        return {
          left: leftStr,
          width: widthStr,
          top: '0%',
          height: '86%',
          ...(effectiveSharedYAxis && sharedYAxisMax > 0 ? {
            min: 0,
            max: sharedYAxisMax,
            ...(sharedTickInterval !== undefined ? { tickInterval: sharedTickInterval } : {}),
            endOnTick: false,
          } : {}),
          gridLineColor: '#e2e8f0',
          gridLineWidth: 1,
          lineWidth: (!effectiveSharedYAxis || idx === 0) ? 1 : 0,
          lineColor: (!effectiveSharedYAxis || idx === 0) ? '#64748b' : 'transparent',
          tickWidth: (!effectiveSharedYAxis || idx === 0) ? 1 : 0,
          tickLength: (!effectiveSharedYAxis || idx === 0) ? 6 : 0,
          tickColor: (!effectiveSharedYAxis || idx === 0) ? '#64748b' : 'transparent',
          labels: {
            enabled: !effectiveSharedYAxis || idx === 0,
            style: { color: '#334155', fontSize: '20pt' },
          },
          title: {
            text: idx === 0 ? data.yAxisLabel : null,
            style: { color: '#334155', fontSize: '28pt' },
          },
          stackLabels: {
            enabled: true,
            style: {
              fontWeight: 'normal',
              color: '#1e293b',
              textOutline: 'none',
              fontSize: '20pt',
            },
          },
        };
      });
    })();

    const cleanExportOverrides: Partial<Highcharts.Options> = {
      title: { text: '' },
      yAxis: exportChartYAxisOptions.map(cfg => ({
        ...cfg,
        stackLabels: { enabled: false },
      })),
      plotOptions: { series: { dataLabels: { enabled: false } } },
    };

    return {
      chart: {
        type: isArea ? 'area' : 'column',
        height: inverted ? 620 : 550,
        inverted,
        style: { fontFamily: 'Verdana, sans-serif' },
        backgroundColor: 'transparent',
        borderWidth: 0,
        plotBorderWidth: 0,
        plotShadow: false,
      },
      title: {
        text: data.title,
        style: { fontSize: '14pt', fontWeight: 'bold', color: '#f8fafc' },
      },
      xAxis,
      yAxis,
      tooltip: buildStackedSinglePointTooltipOptions({
        unitLabel: data.yAxisLabel,
        headerPrefix: (ctx) => {
          const userOptions = ctx.series.userOptions as {
            custom?: {
              subplotYear?: number | string;
              scenarioName?: string
            }
          };
          // Para modo alternativo, mostrar nombre del escenario
          if (userOptions.custom?.scenarioName) {
            return userOptions.custom.scenarioName;
          }
          const year = userOptions.custom?.subplotYear;
          return year != null ? String(year) : null;
        },
      }),
      plotOptions: {
        series: {
          events: { legendItemClick },
        },
        column: {
          stacking: 'normal',
          borderWidth: 0,
          dataLabels: { enabled: false },
          ...{ pointWidth: 50, pointPadding: 0.2, groupPadding: 0.5 },
        },
        area: {
          stacking: 'normal',
          lineWidth: 0.5,
          fillOpacity: 0.85,
          marker: { enabled: false },
          dataLabels: { enabled: false },
        },
      },
      series: series as Highcharts.SeriesOptionsType[],
      exporting: {
        enabled: true,
        sourceWidth: 1920,
        sourceHeight: 1080,
        scale: 1,
        fallbackToExportServer: false,
        error: onHighchartsExportError,
        chartOptions: {
          chart: { backgroundColor: '#FFFFFF', spacingTop: 50 },
          title: { style: { color: '#1e293b', fontSize: '28pt' } },
          legend: { itemStyle: { color: '#334155', fontSize: '20pt' } },
          // X-axis overrides for export — matching HighchartsChart.tsx pattern
          xAxis: data.subplots.map(() => ({
            labels: {
              style: { color: '#334155', fontSize: '20pt' },
            },
            title: {
              style: { color: '#334155', fontSize: '28pt', fontWeight: 'normal' },
            },
            lineColor: '#cbd5e1',
            tickColor: '#cbd5e1',
          })),
          // Preserve Y-axis configuration for all subplots during export
          yAxis: exportChartYAxisOptions,
        },
        buttons: {
          contextButton: {
            menuItems: [
              ...INDIVIDUAL_CHART_EXPORT_MENU_ITEMS,
              '_separator_',
              createCleanExportMenuItem('png', cleanExportOverrides),
              createCleanExportMenuItem('svg', cleanExportOverrides),
            ] as unknown as string[],
            ...EXPORTING_CONTEXT_BUTTON_DARK,
          },
        },
      },
      credits: { enabled: false },
      legend: {
        align: 'center',
        verticalAlign: 'bottom',
        layout: 'horizontal',
        itemStyle: { color: '#94a3b8', fontWeight: 'normal', fontSize: '11pt' },
        itemHoverStyle: { color: '#f8fafc' },
      },
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, inverted, hiddenNames, yAxisMin, yAxisMax, sharedYAxisMax, effectiveSharedYAxis, isByYearAltMode, isArea]);

  return (
    <div style={{ width: '100%' }}>
      <HighchartsReact
        highcharts={Highcharts}
        options={options}
        containerProps={{ style: { width: '100%' } }}
      />
      {compareExportOptions.length > 0 ? (
        <div className="mt-2 flex justify-end">
          <CompareExportDropdown
            disabled={exportBusy || exportXlsxBusy}
            options={compareExportOptions}
          />
        </div>
      ) : null}
    </div>
  );
};
