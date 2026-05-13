import React, { useEffect, useMemo, useRef, useState } from 'react';
import Highcharts from './highchartsSetup';
import {
  EXPORTING_CONTEXT_BUTTON_DARK,
  buildChartExportMenuItems,
  onHighchartsExportError,
} from './chartExportingShared';
import { buildStackedTooltipOptions } from './chartTooltips';
import {
  createLegendDblclickState,
  dispatchLegendClick,
} from './chartLegendInteractions';
import { bumpFontSize, formatAxis3Sig } from './numberFormat';
import HighchartsReact from 'highcharts-react-official';
import type { ChartDataResponse } from '../../types/domain';
import type { ChartSelection } from './ChartSelector';

interface HighchartsChartProps {
  data: ChartDataResponse;
  /** Barras verticales (predeterminado) u horizontales (`inverted`). */
  barOrientation?: 'vertical' | 'horizontal';
  /** Si se indica, PNG/SVG/CSV se generan en el servidor (no dependen del navegador). */
  serverExport?: { jobId: number; selection: ChartSelection };
  /** 'column' (default) o 'area' para áreas apiladas. */
  stackType?: 'column' | 'area';
  /**
   * Modo "amplificado": útil al abrir un link compartible con la barra
   * lateral colapsada. Sube todas las fuentes +3pt para mejor lectura en
   * pantalla grande.
   */
  amplified?: boolean;
  /** Altura explícita del chart en px. Override del default (500). */
  chartHeight?: number;
  /** Override del valor mínimo del eje Y. ``null``/``undefined`` = auto. */
  yAxisMin?: number | null;
  /** Override del valor máximo del eje Y. ``null``/``undefined`` = auto. */
  yAxisMax?: number | null;
}

export const HighchartsChart: React.FC<HighchartsChartProps> = ({
  data,
  barOrientation = 'vertical',
  serverExport,
  stackType = 'column',
  amplified = false,
  chartHeight,
  yAxisMin,
  yAxisMax,
}) => {
  const inverted = barOrientation === 'horizontal';
  const legendDblclickStateRef = useRef(createLegendDblclickState());
  const [hiddenNames, setHiddenNames] = useState<Set<string>>(() => new Set());

  // Si cambia el dataset (nuevo tipo de chart), reseteamos la visibilidad.
  const dataSignature = useMemo(
    () => data.series.map((s) => s.name).join('|'),
    [data.series],
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
    const isArea = stackType === 'area';
    const series = data.series.map((s) => {
      const effectiveType = s.chart_type ?? (isArea ? 'area' : 'column');
      const isLine = effectiveType === 'line';
      return {
        type: effectiveType as 'column' | 'area' | 'line',
        name: s.name,
        data: s.data,
        color: s.color,
        stacking: isLine ? undefined as unknown as 'normal' : 'normal' as const,
        stack: isLine ? undefined as unknown as string : s.stack,
        borderWidth: 0,
        fillOpacity: isArea ? 0.85 : undefined,
        lineWidth: isArea ? 0.5 : (isLine ? 2 : undefined),
        marker: isLine
          ? { enabled: true, radius: 3, symbol: 'circle' }
          : isArea
            ? { enabled: false }
            : undefined,
        visible: !hiddenNames.has(s.name),
      };
    });

    // En modo amplificado: +3pt en todas las fuentes.
    const fb = (s: string) => (amplified ? bumpFontSize(s, 3) ?? s : s);
    // Altura: explícita si se pasó como prop; sino default por orientación.
    const resolvedChartHeight = (typeof chartHeight === 'number')
      ? chartHeight
      : inverted
        ? Math.min(640, 320 + data.categories.length * 16)
        : 500;

    return {
      chart: {
        type: isArea ? 'area' : 'column',
        height: resolvedChartHeight,
        inverted,
        style: { fontFamily: 'Verdana, sans-serif' },
        backgroundColor: 'transparent',
        borderWidth: 0,
        plotBorderWidth: 0,
        plotShadow: false,
      },
      title: {
        text: data.title,
        style: {
          fontSize: fb('22.66px'),
          fontWeight: 'bold',
          color: '#f8fafc',
        },
      },
      xAxis: {
        categories: data.categories,
        crosshair: { color: '#334155' },
        labels: { style: { color: '#94a3b8', fontSize: fb('14.67px') } },
        lineColor: '#334155',
        tickColor: '#334155',
      },
      yAxis: {
        // ``yAxisMin`` (si es número) sobreescribe el ``0`` de stack;
        // ``null`` o no provisto → mantener el default 0 (stacks no
        // tienen sentido bajo cero, salvo override explícito).
        min: typeof yAxisMin === 'number' ? yAxisMin : 0,
        ...(typeof yAxisMax === 'number' ? { max: yAxisMax } : null),
        title: {
          text: data.yAxisLabel,
          style: { color: '#94a3b8', fontSize: fb('22.66px') },
        },
        labels: {
          style: { color: '#94a3b8', fontSize: fb('14.67px') },
          // Mínimo 3 cifras significativas (sin notación científica).
          formatter: function (this: Highcharts.AxisLabelsFormatterContextObject) {
            return formatAxis3Sig(this.value as number);
          },
        },
        gridLineColor: '#334155',
        stackLabels: {
          enabled: true,
          style: {
            fontWeight: 'bold',
            color: '#94a3b8',
            textOutline: 'none',
            fontSize: fb('14.67px'),
          },
          // Highcharts invoca el formatter con `this` como StackItemObject; no usar flecha.
          // Mostrar solo cada 2 categorías (0, 2, 4, …) con 1 decimal máximo.
          // eslint-disable-next-line react-hooks/unsupported-syntax -- API de Highcharts
          formatter: function (this: Highcharts.StackItemObject) {
            if (typeof this.x === 'number' && this.x % 2 !== 0) return '';
            return Highcharts.numberFormat(this.total, 1, '.', ',');
          },
        },
      },
      tooltip: buildStackedTooltipOptions({ unitLabel: data.yAxisLabel }),
      plotOptions: {
        series: {
          events: { legendItemClick },
        },
        column: {
          stacking: 'normal',
          borderWidth: 0,
          dataLabels: { enabled: false },
        },
        area: {
          stacking: 'normal',
          lineWidth: 0.5,
          fillOpacity: 0.85,
          marker: { enabled: false },
          dataLabels: { enabled: false },
        },
        line: {
          marker: { enabled: true, radius: 3 },
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
          title: { style: { color: '#1e293b', fontSize: '22.66px' } },
          xAxis: {
            labels: { style: { color: '#334155', fontSize: '14.67px' } },
            lineColor: '#cbd5e1',
            tickColor: '#cbd5e1',
          },
          yAxis: {
            labels: { style: { color: '#334155', fontSize: '14.67px' } },
            title: { style: { color: '#334155', fontSize: '22.66px' } },
            gridLineColor: '#e2e8f0',
            stackLabels: { style: { color: '#1e293b', fontSize: '14.67px' } },
          },
          legend: { itemStyle: { color: '#334155', fontSize: '14.67px' } },
        },
        buttons: {
          contextButton: {
            // Highcharts admite objetos { text, onclick }; los tipos suelen declarar solo string[].
            menuItems: buildChartExportMenuItems(serverExport) as string[],
            ...EXPORTING_CONTEXT_BUTTON_DARK,
          },
        },
      },
      credits: { enabled: false },
      legend: {
        align: 'center',
        verticalAlign: 'bottom',
        layout: 'horizontal',
        // Invierte el orden de la leyenda respecto al stack: la primera serie
        // (que queda arriba del stack) aparece al final de la leyenda. Así la
        // leyenda se lee de abajo hacia arriba igual que las barras.
        reversed: true,
        itemStyle: { color: '#94a3b8', fontWeight: 'normal', fontSize: fb('14.67px') },
        itemHoverStyle: { color: '#f8fafc' },
      },
    };
    // `handleToggle/handleIsolate/handleRestoreAll` viven en closures estables
    // por componente; sus dependencias reales son `data` (para `handleIsolate`) y
    // `hiddenNames` (para `options.series[i].visible`).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, inverted, serverExport, hiddenNames, stackType, amplified, chartHeight, yAxisMin, yAxisMax]);

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
