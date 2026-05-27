import React, { useEffect, useMemo, useRef, useState } from 'react';
import Highcharts from './highchartsSetup';
import { downloadChartFromServer } from './serverChartExport';
import {
  CLEAN_EXPORT_OVERRIDES_SINGLE_YAXIS,
  EXPORTING_CONTEXT_BUTTON_DARK,
  INDIVIDUAL_CHART_EXPORT_MENU_ITEMS,
  buildCleanExportOverridesMultiYAxis,
  createCleanExportMenuItem,
  onHighchartsExportError,
} from './chartExportingShared';
import { buildLineTooltipOptions } from './chartTooltips';
import { bumpFontSize, formatAxis3Sig } from './numberFormat';
import { getUnitConversionRatio } from './unitConversion';
import {
  createLegendDblclickState,
  dispatchLegendClick,
} from './chartLegendInteractions';
import HighchartsReact from 'highcharts-react-official';
import type { ChartDataResponse, SyntheticSeries } from '../../types/domain';
import type { ChartSelection } from './ChartSelector';

interface LineChartProps {
  data: ChartDataResponse;
  serverExport?: { jobId: number; selection: ChartSelection };
  /**
   * Series manuales overlay (año, valor). Se dibujan como línea punteada con
   * markers para distinguirlas de las series simuladas.
   */
  syntheticSeries?: SyntheticSeries[] | undefined;
  /** Modo amplificado: fuentes +3pt. */
  amplified?: boolean;
  /** Altura explícita del chart en px. */
  chartHeight?: number;
  /** Override mínimo del eje Y. ``null``/``undefined`` = auto (típicamente 0). */
  yAxisMin?: number | null;
  /** Override máximo del eje Y. ``null``/``undefined`` = auto. */
  yAxisMax?: number | null;
}

export const LineChart: React.FC<LineChartProps> = ({
  data,
  serverExport,
  syntheticSeries,
  amplified = false,
  chartHeight,
  yAxisMin,
  yAxisMax,
}) => {
  const legendDblclickStateRef = useRef(createLegendDblclickState());
  const [hiddenNames, setHiddenNames] = useState<Set<string>>(() => new Set());

  const secondaryAxisMax = useMemo(() => {
    if (!data.yAxisLabelSecondary) return null;
    const primaryMax = Math.max(
      0,
      ...data.series.flatMap((s) => s.data).filter((v): v is number => typeof v === 'number'),
    );
    if (primaryMax <= 0) return null;
    const ratio = getUnitConversionRatio(data.yAxisLabel, data.yAxisLabelSecondary);
    if (ratio == null) return null;
    return +(primaryMax * ratio).toPrecision(3);
  }, [data.yAxisLabel, data.yAxisLabelSecondary, data.series]);

  const dataSignature = useMemo(
    () =>
      [
        ...data.series.map((s) => s.name),
        ...(syntheticSeries ?? []).map((s) => `@${s.name}`),
      ].join('|'),
    [data.series, syntheticSeries],
  );
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
    setHiddenNames(new Set(data.series.map((s) => s.name).filter((n) => n !== name)));
  };
  const handleRestoreAll = () => setHiddenNames(new Set());

  const options = useMemo<Highcharts.Options>(() => {
    const legendItemClick = function (this: Highcharts.Series): boolean {
      dispatchLegendClick(legendDblclickStateRef.current, this.name, {
        onToggle: handleToggle,
        onIsolate: handleIsolate,
        onRestoreAll: handleRestoreAll,
      });
      return false;
    };
    const series = data.series.map((s) => ({
      type: 'line' as const,
      name: s.name,
      data: s.data,
      color: s.color,
      marker: { enabled: true, radius: 3 },
      visible: !hiddenNames.has(s.name),
    }));

    // Overlay de series manuales. Se mapea cada (año, valor) al índice de la
    // categoría que coincide con ese año. Puntos sin categoría coincidente se
    // omiten silenciosamente. Estilo: línea punteada + markers más grandes.
    if (syntheticSeries && syntheticSeries.length > 0) {
      const yearIndex = new Map<number, number>();
      data.categories.forEach((cat, idx) => {
        const year = Number(cat);
        if (Number.isFinite(year)) yearIndex.set(year, idx);
      });
      for (const s of syntheticSeries) {
        const mapped: Array<[number, number]> = [];
        for (const [year, value] of s.data) {
          const idx = yearIndex.get(year);
          if (idx != null) mapped.push([idx, value]);
        }
        if (mapped.length === 0) continue;
        const markerSymbol = s.markerSymbol ?? 'diamond';
        const markerRadius = s.markerRadius ?? 5;
        const markerEnabled = markerSymbol !== 'none';
        const dashStyle = (s.lineStyle ?? 'ShortDash') as Highcharts.DashStyleValue;
        const lineWidth = s.lineWidth ?? 2;
        series.push({
          type: 'line' as const,
          name: s.name,
          data: mapped as unknown as number[],
          color: s.color,
          marker: markerEnabled
            ? { enabled: true, radius: markerRadius, symbol: markerSymbol }
            : { enabled: false, radius: 0 },
          dashStyle,
          lineWidth,
          visible: !hiddenNames.has(s.name),
        } as unknown as (typeof series)[number]);
      }
    }

    const fb = (s: string) => (amplified ? bumpFontSize(s, 3) ?? s : s);
    return {
      chart: {
        type: 'line',
        height: typeof chartHeight === 'number' ? chartHeight : 500,
        style: { fontFamily: 'Verdana, sans-serif' },
        backgroundColor: 'transparent',
      },
      title: {
        text: data.title,
        style: {
          fontSize: fb('14pt'),
          fontWeight: 'bold',
          color: '#f8fafc',
        },
      },
      xAxis: {
        categories: data.categories,
        crosshair: { color: '#334155' },
        labels: { style: { color: '#94a3b8', fontSize: fb('11pt') } },
        lineColor: '#334155',
        tickColor: '#334155',
      },
      yAxis: data.yAxisLabelSecondary
        ? [
            {
              ...(typeof yAxisMin === 'number' ? { min: yAxisMin } : null),
              ...(typeof yAxisMax === 'number' ? { max: yAxisMax } : null),
              title: {
                text: data.yAxisLabel,
                style: { color: '#94a3b8', fontSize: fb('14pt') },
              },
              labels: {
                style: { color: '#94a3b8', fontSize: fb('11pt') },
                formatter: function (this: Highcharts.AxisLabelsFormatterContextObject) {
                  return formatAxis3Sig(this.value as number);
                },
              },
              gridLineColor: '#334155',
            },
            {
              opposite: true,
              title: {
                text: data.yAxisLabelSecondary,
                style: { color: '#94a3b8', fontSize: fb('14pt') },
              },
              labels: {
                style: { color: '#94a3b8', fontSize: fb('11pt') },
                formatter: function (this: Highcharts.AxisLabelsFormatterContextObject) {
                  return formatAxis3Sig(this.value as number);
                },
              },
              gridLineColor: '#334155',
              gridLineWidth: 0,
              lineWidth: 1,
              lineColor: '#334155',
              linkedTo: 0,
              min: 0,
              ...(secondaryAxisMax != null ? { max: secondaryAxisMax } : null),
            },
          ]
        : {
            // Líneas: default = auto (a diferencia de columnas/áreas apiladas
            // que sí fuerzan ``min: 0``). Esto mantiene consistencia con el
            // export matplotlib (``_render_line_chart``), que tampoco fuerza 0.
            // Si el usuario quiere 0 explícitamente, lo configura en yAxisMin.
            ...(typeof yAxisMin === 'number' ? { min: yAxisMin } : null),
            ...(typeof yAxisMax === 'number' ? { max: yAxisMax } : null),
            title: {
              text: data.yAxisLabel,
              style: { color: '#94a3b8', fontSize: fb('14pt') },
            },
            labels: {
              style: { color: '#94a3b8', fontSize: fb('11pt') },
              // Mínimo 3 cifras significativas (sin notación científica).
              formatter: function (this: Highcharts.AxisLabelsFormatterContextObject) {
                return formatAxis3Sig(this.value as number);
              },
            },
            gridLineColor: '#334155',
          },
      tooltip: buildLineTooltipOptions({
        unitLabel: data.yAxisLabel,
        ...(data.yAxisLabelSecondary ? { secondaryUnitLabel: data.yAxisLabelSecondary } : null),
      }),
      plotOptions: {
        series: {
          events: { legendItemClick },
        },
        line: {
          dataLabels: { enabled: false },
          marker: { enabled: true, radius: 3 },
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
          xAxis: {
            labels: { style: { color: '#334155', fontSize: '20pt' } },
            lineColor: '#cbd5e1',
            tickColor: '#cbd5e1',
          },
          yAxis: data.yAxisLabelSecondary
            ? [
                {
                  labels: { style: { color: '#334155', fontSize: '20pt' } },
                  title: { style: { color: '#334155', fontSize: '28pt' } },
                  gridLineColor: '#e2e8f0',
                  lineWidth: 1,
                  lineColor: '#334155',
                },
                {
                  labels: { style: { color: '#334155', fontSize: '20pt' } },
                  title: { style: { color: '#334155', fontSize: '28pt' } },
                  gridLineColor: '#e2e8f0',
                  lineWidth: 1,
                  lineColor: '#334155',
                  opposite: true,
                },
              ]
            : {
                labels: { style: { color: '#334155', fontSize: '20pt' } },
                title: { style: { color: '#334155', fontSize: '28pt' } },
                gridLineColor: '#e2e8f0',
              },
          legend: { itemStyle: { color: '#334155', fontSize: '20pt' } },
        },
        buttons: {
          contextButton: {
            // Highcharts admite objetos { text, onclick }; los tipos suelen declarar solo string[].
            menuItems: (() => {
              if (!serverExport) {
                const cleanOverrides = data.yAxisLabelSecondary
                  ? buildCleanExportOverridesMultiYAxis(2)
                  : CLEAN_EXPORT_OVERRIDES_SINGLE_YAXIS;
                return [
                  ...INDIVIDUAL_CHART_EXPORT_MENU_ITEMS,
                  '_separator_',
                  createCleanExportMenuItem('png', cleanOverrides),
                  createCleanExportMenuItem('svg', cleanOverrides),
                ];
              }
              const { jobId, selection } = serverExport;
              const runServer = (fmt: "png" | "svg" | "csv", opts?: { clean?: boolean }) => {
                const hiddenSeries = Array.from(hiddenNames);
                void downloadChartFromServer(jobId, selection, fmt, { ...opts, hiddenSeries }).catch((e: unknown) => {
                  console.error(e);
                  window.alert("No se pudo descargar desde el servidor.");
                });
              };
              return [
                { text: "Descargar PNG", onclick: () => runServer("png") },
                { text: "Descargar SVG", onclick: () => runServer("svg") },
                { text: "Descargar CSV", onclick: () => runServer("csv") },
                "_separator_",
                { text: "Descargar PNG (limpia)", onclick: () => runServer("png", { clean: true }) },
                { text: "Descargar SVG (limpia)", onclick: () => runServer("svg", { clean: true }) },
              ];
            })() as unknown as string[],
            ...EXPORTING_CONTEXT_BUTTON_DARK,
          },
        },
      },
      credits: { enabled: false },
      legend: {
        align: 'center',
        verticalAlign: 'bottom',
        layout: 'horizontal',
        itemStyle: { color: '#94a3b8', fontWeight: 'normal', fontSize: fb('11pt') },
        itemHoverStyle: { color: '#f8fafc' },
      },
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, serverExport, hiddenNames, syntheticSeries, amplified, chartHeight, yAxisMin, yAxisMax, secondaryAxisMax]);

  return (
    <div style={{ width: '100%' }}>
      <HighchartsReact
        highcharts={Highcharts}
        options={options}
        containerProps={{ style: { width: '100%' } }}
      />
    </div>
  );
};
