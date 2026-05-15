import Highcharts from './highchartsSetup';

/**
 * Formateo consistente de valores numéricos para tooltips:
 * - 0 exacto -> "0"
 * - |v| < 0.01 (pero != 0) -> notación científica (p.ej. 3.45e-5)
 * - resto -> 2 decimales con separador de miles
 */
export function fmtValue(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—';
  if (v === 0) return '0';
  const abs = Math.abs(v);
  if (abs < 0.01) return v.toExponential(2);
  return Highcharts.numberFormat(v, 2, '.', ',');
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** La unidad "%" ya es participación: no tiene sentido mostrar otro % encima. */
function unitIsAlreadyPercent(label: string): boolean {
  const trimmed = label.trim().toLowerCase();
  return (
    trimmed === '%' ||
    trimmed === 'porcentaje' ||
    trimmed === 'percentage' ||
    trimmed.includes('%')
  );
}

/** Opciones base (estilo) que todos los tooltips comparten. */
export const TOOLTIP_BASE_OPTIONS: Highcharts.TooltipOptions = {
  useHTML: true,
  backgroundColor: 'rgba(15, 23, 42, 0.96)',
  borderColor: '#334155',
  borderRadius: 8,
  borderWidth: 1,
  shadow: false,
  padding: 10,
  style: {
    color: '#e2e8f0',
    fontSize: '20pt',  // tooltip más legible en pantallas grandes
    pointerEvents: 'auto',
  },
};

type StackedTooltipOptions = {
  unitLabel: string;
  /** Si true, filtra los puntos al mismo eje Y del punto activo (para multi-subplots). */
  scopeByYAxis?: boolean;
  /** Extrae un prefijo de cabecera a partir del punto activo (p.ej. año del subplot). */
  headerPrefix?: (ctx: Highcharts.TooltipFormatterContextObject) => string | null;
};

/**
 * Tooltip para gráficas de barras apiladas.
 *
 * Comportamiento:
 * - Respeta el orden del stack (orden de series-definición) para que el usuario
 *   identifique inequívocamente color/posición con la entrada del tooltip.
 * - Filtra series con valor 0 exacto (valores no-cero se muestran siempre; muy pequeños van en notación científica).
 * - Muestra el total del stack una sola vez en el header.
 * - Calcula % de participación por serie respecto al total.
 */
export function buildStackedTooltipOptions(
  opts: StackedTooltipOptions,
): Highcharts.TooltipOptions {
  const { unitLabel, scopeByYAxis = false, headerPrefix } = opts;
  const hidePercent = unitIsAlreadyPercent(unitLabel);
  return {
    ...TOOLTIP_BASE_OPTIONS,
    shared: true,
    // Highcharts invoca con `this` como context; no usar arrow function.
    formatter: function (this: Highcharts.TooltipFormatterContextObject): string {
      let points = this.points ?? [];
      if (scopeByYAxis && this.point) {
        const targetYAxis = this.point.series.yAxis;
        points = points.filter((p) => p.series.yAxis === targetYAxis);
      }

      // El `point.total` (stackTotal) es igual en todos los puntos del mismo stack,
      // así que lo leemos antes de filtrar para no perderlo si el hover cae sobre un 0.
      const firstPoint = points[0]?.point as (Highcharts.Point & { total?: number }) | undefined;
      const stackTotal =
        firstPoint && typeof firstPoint.total === 'number'
          ? firstPoint.total
          : points.reduce((acc, p) => acc + (p.y ?? 0), 0);

      const visible = points.filter((p) => (p.y ?? 0) !== 0);

      const prefix = headerPrefix ? headerPrefix(this) : null;
      const xLabel = String(this.x ?? '');
      const header = prefix ? `${prefix} · ${xLabel}` : xLabel;
      const colspan = hidePercent ? 2 : 3;

      const rows = visible
        .map((p) => {
          const y = p.y ?? 0;
          let pctCell = '';
          if (!hidePercent) {
            const pct = stackTotal ? (y / stackTotal) * 100 : 0;
            const pctLabel = Math.abs(pct) < 0.05 ? '<0.1%' : `${pct.toFixed(1)}%`;
            pctCell = `<td style="padding:2px 0 2px 10px; text-align:right; color:#94a3b8; font-variant-numeric:tabular-nums; white-space:nowrap">${pctLabel}</td>`;
          }
          return `<tr>
            <td style="padding:2px 10px 2px 0; white-space:nowrap">
              <span style="color:${p.color};font-size:20px;line-height:1">●</span>
              <span style="margin-left:4px">${escapeHtml(p.series.name)}</span>
            </td>
            <td style="padding:2px 0; text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap">
              <b style="color:#f8fafc">${fmtValue(y)}</b> <span style="color:#94a3b8">${escapeHtml(unitLabel)}</span>
            </td>
            ${pctCell}
          </tr>`;
        })
        .join('');

      const emptyRow = visible.length === 0
        ? `<tr><td style="padding:4px 0; color:#94a3b8" colspan="${colspan}"><i>Sin contribuciones distintas de 0</i></td></tr>`
        : '';

      const totalLine = hidePercent
        ? ''
        : `<div style="color:#94a3b8; margin-bottom:6px">Total: <b style="color:#f8fafc">${fmtValue(stackTotal)}</b> ${escapeHtml(unitLabel)}</div>`;

      return `
        <div style="min-width:260px">
          <div style="font-weight:700; font-size:14px; color:#f8fafc; margin-bottom:${hidePercent ? '6' : '2'}px">${escapeHtml(header)}</div>
          ${totalLine}
          <table style="border-collapse:collapse; font-size:11px">${rows}${emptyRow}</table>
        </div>
      `;
    },
  };
}

type LineTooltipOptions = {
  unitLabel: string;
};

/**
 * Tooltip para gráficas de líneas (no apiladas).
 *
 * Comportamiento:
 * - Ordena series descendentemente por valor absoluto en el punto activo
 *   (en líneas sí tiene lógica: magnitudes comparables directamente, no hay stack).
 * - Filtra series con valor 0 exacto.
 *
 * TODO: Opción "mostrar delta vs año anterior" (flag de preferencia de usuario).
 * Implementación original conservada abajo comentada por si queremos reactivarla
 * como toggle:
 *
 *   const activeIndex = this.point?.index ?? points[0]?.point?.index ?? 0;
 *   const categories = (points[0]?.series.xAxis as Highcharts.Axis | undefined)
 *     ?.categories as (string | number)[] | undefined;
 *   const prevCategory =
 *     activeIndex > 0 && categories ? categories[activeIndex - 1] : null;
 *   // …en cada fila…
 *   const dataArr = p.series.data as Array<Highcharts.Point & { y: number | null }>;
 *   const prevPoint = activeIndex > 0 ? dataArr[activeIndex - 1] : null;
 *   const prevY = prevPoint?.y ?? null;
 *   const hasDelta = prevY != null && prevCategory != null;
 *   const delta = hasDelta ? y - (prevY as number) : 0;
 *   const sign = delta > 0 ? '▲ +' : delta < 0 ? '▼ ' : '';
 *   const deltaColor = delta > 0 ? '#4ade80' : delta < 0 ? '#f87171' : '#94a3b8';
 *   const deltaLine = hasDelta
 *     ? `<div style="font-size:10px; color:#94a3b8; margin-top:1px">
 *          vs ${escapeHtml(String(prevCategory))}:
 *          <span style="color:${deltaColor}">${sign}${fmtValue(Math.abs(delta))}</span>
 *        </div>`
 *     : '';
 */
export function buildLineTooltipOptions(
  opts: LineTooltipOptions,
): Highcharts.TooltipOptions {
  const { unitLabel } = opts;
  return {
    ...TOOLTIP_BASE_OPTIONS,
    shared: true,
    formatter: function (this: Highcharts.TooltipFormatterContextObject): string {
      const points = this.points ?? [];
      const visible = points
        .filter((p) => (p.y ?? 0) !== 0)
        .slice()
        .sort((a, b) => Math.abs(b.y ?? 0) - Math.abs(a.y ?? 0));

      const rows = visible
        .map((p) => {
          const y = p.y ?? 0;
          return `<tr>
            <td style="padding:2px 10px 2px 0; vertical-align:top; white-space:nowrap">
              <span style="color:${p.color};font-size:20px;line-height:1">●</span>
              <span style="margin-left:4px">${escapeHtml(p.series.name)}</span>
            </td>
            <td style="padding:2px 0; text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap">
              <b style="color:#f8fafc">${fmtValue(y)}</b> <span style="color:#94a3b8">${escapeHtml(unitLabel)}</span>
            </td>
          </tr>`;
        })
        .join('');

      const emptyRow = visible.length === 0
        ? `<tr><td style="padding:4px 0; color:#94a3b8" colspan="2"><i>Sin valores distintos de 0</i></td></tr>`
        : '';

      return `
        <div style="min-width:220px">
          <div style="font-weight:700; font-size:14px; color:#f8fafc; margin-bottom:6px">${escapeHtml(String(this.x ?? ''))}</div>
          <table style="border-collapse:collapse; font-size:11px">${rows}${emptyRow}</table>
        </div>
      `;
    },
  };
}

type SinglePointStackedOptions = {
  unitLabel: string;
  headerPrefix?: (ctx: Highcharts.TooltipFormatterContextObject) => string | null;
};

/**
 * Tooltip de un solo punto para apiladas (útil cuando `shared` no tiene sentido,
 * p.ej. subplots en grid donde cada subplot muestra su propio año).
 * Incluye valor, % del stack y total del stack.
 */
export function buildStackedSinglePointTooltipOptions(
  opts: SinglePointStackedOptions,
): Highcharts.TooltipOptions {
  const { unitLabel, headerPrefix } = opts;
  const hidePercent = unitIsAlreadyPercent(unitLabel);
  return {
    ...TOOLTIP_BASE_OPTIONS,
    shared: false,
    formatter: function (this: Highcharts.TooltipFormatterContextObject): string {
      const point = this.point as Highcharts.Point & { total?: number; color?: string };
      const y = point.y ?? 0;
      const stackTotal = typeof point.total === 'number' ? point.total : y;
      const prefix = headerPrefix ? headerPrefix(this) : null;
      const xLabel = String(this.x ?? '');
      const header = prefix ? `${prefix} · ${xLabel}` : xLabel;
      const color = point.color ?? this.series.color ?? '#60a5fa';

      let pctInline = '';
      let totalLine = '';
      if (!hidePercent) {
        const pct = stackTotal ? (y / stackTotal) * 100 : 0;
        const pctLabel = Math.abs(pct) < 0.05 ? '<0.1%' : `${pct.toFixed(1)}%`;
        pctInline = `<span style="color:#94a3b8"> (${pctLabel})</span>`;
        totalLine = `<div style="color:#94a3b8">Total: <b style="color:#f8fafc">${fmtValue(stackTotal)}</b> ${escapeHtml(unitLabel)}</div>`;
      }

      return `
        <div style="min-width:220px">
          <div style="font-weight:700; font-size:14px; color:#f8fafc; margin-bottom:4px">${escapeHtml(header)}</div>
          <div style="margin-bottom:4px">
            <span style="color:${color};font-size:20px;line-height:1">●</span>
            <span style="margin-left:4px">${escapeHtml(this.series.name)}</span>:
            <b style="color:#f8fafc">${fmtValue(y)}</b> <span style="color:#94a3b8">${escapeHtml(unitLabel)}</span>
            ${pctInline}
          </div>
          ${totalLine}
        </div>
      `;
    },
  };
}
