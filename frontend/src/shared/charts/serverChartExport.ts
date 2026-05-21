import { simulationApi } from '@/features/simulation/api/simulationApi';
import { downloadBlob } from '@/shared/utils/downloadBlob';
import type { ChartSelection } from './ChartSelector';

/**
 * Descarga PNG/SVG/CSV/XLSX generados en el servidor, sin offline-exporting.
 *
 * ``tableExportFilters`` (opcional) restringe la exportación cuando
 * ``view_mode === 'table'`` a un subconjunto de series y/o años elegidos en la UI.
 */
export async function downloadChartFromServer(
  jobId: number,
  selection: ChartSelection,
  fmt: 'png' | 'svg' | 'csv' | 'xlsx',
  tableExportFilters?: {
    series?: string[];
    years?: (string | number)[];
  },
): Promise<void> {
  const { blob, filename } = await simulationApi.exportChart(
    jobId,
    selection,
    fmt,
    tableExportFilters,
  );
  downloadBlob(blob, filename);
}
