import React, { useEffect, useMemo, useRef, useState } from 'react';
import Highcharts from './highchartsSetup';
import {
  EXPORTING_CONTEXT_BUTTON_DARK,
  INDIVIDUAL_CHART_EXPORT_MENU_ITEMS,
  onHighchartsExportError,
} from './chartExportingShared';
import { buildStackedSinglePointTooltipOptions } from './chartTooltips';
import { formatAxis3Sig } from './numberFormat';
import {
  createLegendDblclickState,
  dispatchLegendClick,
} from './chartLegendInteractions';
import HighchartsReact from 'highcharts-react-official';
import type { CompareChartResponse } from '../../types/domain';

interface CompareChartProps {
  data: CompareChartResponse;
  barOrientation?: 'vertical' | 'horizontal';
  /** Override del eje Y para todos los subplots. ``null``/undefined = auto. */
  yAxisMin?: number | null;
  yAxisMax?: number | null;
  /** Force all subplots to share the same Y-axis maximum */
  sharedYAxis?: boolean;
}

export const CompareChart: React.FC<CompareChartProps> = ({
  data,
  barOrientation = 'vertical',
  yAxisMin,
  yAxisMax,
  sharedYAxis = false,
}) => {
  const inverted = barOrientation === 'horizontal';
  const legendDblclickStateRef = useRef(createLegendDblclickState());

  const allSeriesNames = useMemo(() => {
    const names = new Set<string>();
    data.subplots.forEach((sp) => sp.series.forEach((s) => names.add(s.name)));
    return Array.from(names);
  }, [data.subplots]);

  const sharedYAxisMax = useMemo(() => {
    if (!sharedYAxis) return 0;
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
  }, [data.subplots, sharedYAxis]);

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
    const series: Highcharts.SeriesColumnOptions[] = [];

    const widthPerSubplot = 100 / (numSubplots || 1);

    data.subplots.forEach((subplot, idx) => {
      const leftStr = `${idx * widthPerSubplot}%`;
      const rightMargin = numSubplots > 1 && idx < numSubplots - 1 ? 2 : 0;
      const widthStr = `${widthPerSubplot - rightMargin}%`;

      xAxis.push({
        id: `x-${idx}`,
        categories: subplot.categories,
        title: {
          text: subplot.scenario_name || subplot.year.toString(),
          style: { color: '#94a3b8', fontWeight: 'bold' },
        },
        width: widthStr,
        left: leftStr,
        // Mismo top/height que el yAxis para que el eje X quede alineado y
        // deje espacio a la leyenda en la parte inferior.
        top: '0%',
        height: '86%',
        offset: 0,
        labels: { style: { color: '#94a3b8', fontSize: '13px' } },
        lineColor: '#334155',
        tickColor: '#334155',
      });

      yAxis.push({
        id: `y-${idx}`,
        title: {
          text: idx === 0 ? data.yAxisLabel : null,
          style: { color: '#94a3b8', fontSize: '14px' },
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
          : (sharedYAxis && sharedYAxisMax > 0 ? sharedYAxisMax : null),
        // Grid lines always visible on all charts for visual reference
        gridLineColor: '#334155',
        gridLineWidth: 1,
        // Only show ticks on first subplot when Y-axis is shared
        tickWidth: (!sharedYAxis || idx === 0) ? 1 : 0,
        tickLength: (!sharedYAxis || idx === 0) ? 6 : 0,
        tickColor: (!sharedYAxis || idx === 0) ? '#64748b' : 'transparent',
        // Y-axis line always visible (provides chart boundaries between scenarios)
        lineWidth: 1,
        lineColor: '#64748b',
        labels: {
          // Only show labels on first subplot when Y-axis is shared
          enabled: !sharedYAxis || idx === 0,
          style: { color: '#94a3b8', fontSize: '13px' },
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
            fontSize: '10px',
          },
          // eslint-disable-next-line react-hooks/unsupported-syntax -- API de Highcharts (`this`)
          formatter: function (this: Highcharts.StackItemObject) {
            return Highcharts.numberFormat(this.total, 2, '.', ',');
          },
        },
      });

      subplot.series.forEach((s) => {
        series.push({
          type: 'column',
          name: s.name,
          data: s.data,
          color: s.color,
          xAxis: `x-${idx}`,
          yAxis: `y-${idx}`,
          stacking: 'normal',
          borderWidth: 0,
          showInLegend: idx === 0,
          visible: !hiddenNames.has(s.name),
          custom: { 
            subplotYear: subplot.year,
            scenarioName: subplot.scenario_name || null,
          },
        });
      });
    });

    return {
      chart: {
        type: 'column',
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
        style: { fontSize: '16px', fontWeight: 'bold', color: '#f8fafc' },
      },
      xAxis,
      yAxis,
      tooltip: buildStackedSinglePointTooltipOptions({
        unitLabel: data.yAxisLabel,
        headerPrefix: (ctx) => {
          const userOptions = ctx.series.userOptions as { 
            custom?: { subplotYear?: number | string;
                       scenarioName?: string }
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
          chart: { backgroundColor: '#FFFFFF' },
          title: { style: { color: '#1e293b', fontSize: '28px' } },
          legend: { itemStyle: { color: '#334155', fontSize: '20px' } },
        },
        buttons: {
          contextButton: {
            menuItems: [...INDIVIDUAL_CHART_EXPORT_MENU_ITEMS],
            ...EXPORTING_CONTEXT_BUTTON_DARK,
          },
        },
      },
      credits: { enabled: false },
      legend: {
        align: 'center',
        verticalAlign: 'bottom',
        layout: 'horizontal',
        itemStyle: { color: '#94a3b8', fontWeight: 'normal', fontSize: '13px' },
        itemHoverStyle: { color: '#f8fafc' },
      },
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, inverted, hiddenNames, yAxisMin, yAxisMax, sharedYAxisMax]);

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
