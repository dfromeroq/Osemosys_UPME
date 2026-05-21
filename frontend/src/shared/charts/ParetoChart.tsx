import React, { useMemo } from 'react';
import Highcharts from './highchartsSetup';
import {
  CLEAN_EXPORT_OVERRIDES_SINGLE_YAXIS,
  EXPORTING_CONTEXT_BUTTON_DARK,
  INDIVIDUAL_CHART_EXPORT_MENU_ITEMS,
  buildChartExportMenuItems,
  createCleanExportMenuItem,
  onHighchartsExportError,
} from './chartExportingShared';
import { TOOLTIP_BASE_OPTIONS, fmtValue } from './chartTooltips';
import { bumpFontSize, formatAxis3Sig } from './numberFormat';
import HighchartsReact from 'highcharts-react-official';
import type { ParetoChartResponse } from '../../types/domain';
import type { ChartSelection } from './ChartSelector';

interface ParetoChartProps {
  data: ParetoChartResponse;
  serverExport?: { jobId: number; selection: ChartSelection };
  /** Modo amplificado: fuentes +3pt. */
  amplified?: boolean;
  /** Altura explícita del chart en px. */
  chartHeight?: number;
}

export const ParetoChart: React.FC<ParetoChartProps> = ({
  data,
  serverExport,
  amplified = false,
  chartHeight,
}) => {
  const options = useMemo<Highcharts.Options>(() => {
    const n = data.categories.length;
    const dynamicHeight = Math.max(420, Math.min(700, 300 + n * 14));
    const fb = (s: string) => (amplified ? bumpFontSize(s, 3) ?? s : s);

    return {
      chart: {
        height: typeof chartHeight === 'number' ? chartHeight : dynamicHeight,
        style: { fontFamily: 'Verdana, sans-serif' },
        backgroundColor: 'transparent',
      },
      title: {
        text: data.title,
        style: { fontSize: fb('14pt'), fontWeight: 'bold', color: '#f8fafc' },
      },
      xAxis: {
        categories: data.categories,
        crosshair: { color: '#334155' },
        labels: {
          rotation: -45,
          align: 'right',
          style: { color: '#94a3b8', fontSize: fb('11pt') },
        },
        lineColor: '#334155',
        tickColor: '#334155',
      },
      yAxis: [
        {
          min: 0,
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
          min: 0,
          max: 100,
          opposite: true,
          title: {
            text: '% Acumulado',
            style: { color: '#f87171', fontSize: fb('14pt') },
          },
          labels: {
            format: '{value}%',
            style: { color: '#f87171', fontSize: fb('11pt') },
          },
          gridLineWidth: 0,
        },
      ],
      tooltip: {
        ...TOOLTIP_BASE_OPTIONS,
        shared: false,
        formatter(this: Highcharts.TooltipFormatterContextObject) {
          const pt = this.point as Highcharts.Point & { y: number; index: number };
          const color = this.series.color ?? '#3b82f6';
          if (this.series.type === 'column') {
            return `
              <div style="min-width:200px">
                <div style="font-weight:700; color:#f8fafc; margin-bottom:4px">${this.x}</div>
                <div>
                  <span style="color:${color};font-size:14px;line-height:1">●</span>
                  <span style="margin-left:4px">${data.yAxisLabel}</span>:
                  <b style="color:#f8fafc; font-variant-numeric:tabular-nums">${fmtValue(pt.y)}</b>
                </div>
              </div>
            `;
          }
          return `
            <div style="min-width:200px">
              <div style="font-weight:700; color:#f8fafc; margin-bottom:4px">${this.x}</div>
              <div>
                <span style="color:${color};font-size:14px;line-height:1">●</span>
                <span style="margin-left:4px">% Acumulado</span>:
                <b style="color:#f8fafc; font-variant-numeric:tabular-nums">${Highcharts.numberFormat(pt.y, 1, '.', ',')}%</b>
              </div>
            </div>
          `;
        },
      },
      plotOptions: {
        column: { borderWidth: 0, pointPadding: 0.05, groupPadding: 0.1 },
        line: { marker: { enabled: true, radius: 3 } },
      },
      series: [
        {
          type: 'column',
          name: data.yAxisLabel,
          data: data.values,
          yAxis: 0,
          color: '#3b82f6',
        },
        {
          type: 'line',
          name: '% Acumulado',
          data: data.cumulative_percent,
          yAxis: 1,
          color: '#f87171',
          marker: { enabled: true, radius: 3 },
        },
      ] as Highcharts.SeriesOptionsType[],
      exporting: {
        enabled: true,
        sourceWidth: 1920,
        sourceHeight: 1080,
        scale: 1,
        fallbackToExportServer: false,
        error: onHighchartsExportError,
        chartOptions: {
          chart: { backgroundColor: '#FFFFFF' },
          title: { style: { color: '#1e293b', fontSize: '28pt' } },
          xAxis: {
            labels: { style: { color: '#334155', fontSize: '20pt' } },
            lineColor: '#cbd5e1',
            tickColor: '#cbd5e1',
          },
          yAxis: [
            {
              labels: { style: { color: '#334155', fontSize: '20pt' } },
              title: { style: { color: '#334155', fontSize: '28pt' } },
              gridLineColor: '#e2e8f0',
            },
            {
              labels: { style: { color: '#dc2626', fontSize: '20pt' } },
              title: { style: { color: '#dc2626', fontSize: '28pt' } },
              gridLineWidth: 0,
            },
          ],
          legend: { itemStyle: { color: '#334155', fontSize: '20pt' } },
        },
        buttons: {
          contextButton: {
            // Highcharts admite objetos { text, onclick }; los tipos suelen declarar solo string[].
            menuItems: (() => {
              if (!serverExport) {
                return [
                  ...INDIVIDUAL_CHART_EXPORT_MENU_ITEMS,
                  '_separator_',
                  createCleanExportMenuItem('png', CLEAN_EXPORT_OVERRIDES_SINGLE_YAXIS),
                  createCleanExportMenuItem('svg', CLEAN_EXPORT_OVERRIDES_SINGLE_YAXIS),
                ];
              }
              return buildChartExportMenuItems(serverExport);
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
  }, [data, serverExport, amplified, chartHeight]);

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
